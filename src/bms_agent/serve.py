"""Servidor local de desarrollo: datos del panel y ejecucion bajo demanda.

Existe para que un sitio web propio pueda desarrollarse contra datos reales
sin esperar a que haya base de datos ni API desplegada.

COSAS QUE NO SON NEGOCIABLES EN ESTE FICHERO:

1. Escucha SOLO en 127.0.0.1. No acepta 0.0.0.0 ni una IP de red. Un
   endpoint que lanza al agente cuesta dinero en cada llamada: expuesto a
   una red, cualquiera que encuentre la URL puede vaciar el saldo de la API
   pulsando un boton en bucle. Esto es un servidor de desarrollo, no el
   camino a produccion.

2. La ejecucion es un TRABAJO, no una llamada sincrona. Extraer cincuenta
   facturas tarda minutos: el navegador no espera, pregunta. Se lanza, se
   devuelve un identificador y se consulta el estado. Y solo una a la vez:
   dos clics seguidos serian dos extracciones concurrentes sobre la misma
   carpeta, o sea el doble de gasto por nada.

3. Escuchar en 127.0.0.1 no basta, porque el navegador de quien lo usa
   tambien visita otras webs. Por eso:

   - El Host tiene que ser 127.0.0.1:<puerto> o localhost:<puerto>. Una web
     que hace rebotar su DNS hacia 127.0.0.1 llega con su propio Host y se
     la rechaza: sin esto podria leer /api/datos, IBAN incluidos.
   - El Origin se compara entero (esquema, host y puerto), nunca por prefijo:
     "http://localhost.attacker.example" empieza por "http://localhost".
   - Un POST necesita la cabecera X-BMS-Token y cuerpo JSON. Un formulario
     de otra web no puede poner ninguna de las dos cosas, asi que no puede
     lanzar pasadas que se pagan. El token es aleatorio en cada arranque, se
     imprime al arrancar y va dentro de la pagina local que sirve "/".
"""

from __future__ import annotations

import hmac
import html
import json
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import config
from .almacen import preparar, ruta_por_defecto
from .auditoria import anclar
from .cache import CONSERVAR
from .dashboard import construir_datos
from .documents import iter_pdfs
from .extract import ResultadoPasada, extraer_pasada
from .pricing import estimate_cost
from .report import load_records

HOSTS_LOCALES = ("127.0.0.1", "localhost")
CABECERA_TOKEN = "X-BMS-Token"
# El unico POST que hay no necesita cuerpo; esto solo impide que alguien
# tenga el hilo ocupado leyendo megas.
MAX_CUERPO = 4096


def nuevo_token() -> str:
    """Token de esta ejecucion del servidor. Muere con el proceso."""
    return secrets.token_urlsafe(32)


def normalizar_origen(texto: str | None) -> str | None:
    """Un Origin como 'esquema://host:puerto', o None si no es un origen valido.

    El puerto se escribe siempre, aunque sea el de defecto, para que
    "http://localhost" y "http://localhost:80" se comparen como lo que son,
    el mismo origen. Un Origin con ruta, usuario o consulta no es un Origin.
    """
    if not texto:
        return None
    try:
        partes = urlsplit(texto.strip())
        puerto = partes.port
    except ValueError:
        return None
    if partes.scheme not in ("http", "https") or not partes.hostname:
        return None
    if partes.username or partes.password or partes.path not in ("", "/"):
        return None
    if partes.query or partes.fragment:
        return None
    if puerto is None:
        puerto = 443 if partes.scheme == "https" else 80
    return f"{partes.scheme}://{partes.hostname.lower()}:{puerto}"


def origenes_permitidos(puerto: int, extra: list[str] | tuple[str, ...] = ()) -> frozenset[str]:
    """Los origenes que pueden leer y llamar: la propia pagina y los declarados.

    Un origen extra tiene que ser local (127.0.0.1 o localhost). Uno remoto
    permitiria a una web de fuera leer los datos del panel con el navegador
    de quien tiene el servidor abierto, que es justo lo que se quiere evitar.
    """
    permitidos = {f"http://{host}:{puerto}" for host in HOSTS_LOCALES}
    for crudo in extra:
        origen = normalizar_origen(crudo)
        if origen is None:
            raise ValueError(f"origen no valido: {crudo!r}")
        if urlsplit(origen).hostname not in HOSTS_LOCALES:
            raise ValueError(f"solo se admiten origenes locales, no {crudo!r}")
        permitidos.add(origen)
    return frozenset(permitidos)


def origen_permitido(origen: str | None, permitidos: frozenset[str]) -> bool:
    """Coincidencia exacta tras normalizar. "null" y lo malformado no pasan."""
    normalizado = normalizar_origen(origen)
    return normalizado is not None and normalizado in permitidos


def host_permitido(host: str | None, puerto: int) -> bool:
    """El Host de la peticion es este servidor y no otro nombre que apunta aqui."""
    if not host or any(c in host for c in "@/\\?#"):
        return False
    try:
        partes = urlsplit("//" + host.strip())
        puerto_pedido = partes.port
    except ValueError:
        return False
    if (partes.hostname or "").lower() not in HOSTS_LOCALES:
        return False
    return (puerto_pedido if puerto_pedido is not None else 80) == puerto


@dataclass
class Ejecucion:
    """Estado de una pasada del agente. Lo consulta el navegador."""

    estado: str = "inactivo"  # inactivo | corriendo | terminado | error
    total: int = 0
    pasada: ResultadoPasada = field(default_factory=ResultadoPasada)
    mensaje: str = ""
    iniciada: str | None = None
    terminada: str | None = None

    def a_dict(self) -> dict[str, Any]:
        p = self.pasada
        coste = estimate_cost(config.model_id(), p.tokens_entrada, p.tokens_salida)
        return {
            "estado": self.estado,
            "total": self.total,
            "procesadas": p.extraidas,
            "reutilizadas": p.reutilizadas,
            "fallidas": p.fallidas,
            "coste": float(coste) if coste is not None else None,
            "mensaje": self.mensaje,
            "iniciada": self.iniciada,
            "terminada": self.terminada,
            "errores": p.errores[-10:],
        }


class Agente:
    """Encapsula la ejecucion, con cerrojo para que no haya dos a la vez.

    Cada pasada escribe en out/ y en el almacen, como `extract`. La conexion
    al almacen se abre dentro del hilo de la pasada y se cierra al acabar:
    una conexion de sqlite3 no se comparte entre hilos.
    """

    def __init__(
        self, carpeta_pdf: Path, carpeta_salida: Path, ruta_db: Path | None = None
    ) -> None:
        self.carpeta_pdf = carpeta_pdf
        self.carpeta_salida = carpeta_salida
        self.ruta_db = ruta_db
        self._cerrojo = threading.Lock()
        self._estado = Ejecucion()

    @property
    def estado(self) -> dict[str, Any]:
        return self._estado.a_dict()

    def lanzar(self) -> tuple[bool, str]:
        """Arranca una pasada si no hay otra en curso."""
        if not self._cerrojo.acquire(blocking=False):
            return False, "Ya hay una ejecucion en curso."
        hilo = threading.Thread(target=self._correr, daemon=True)
        hilo.start()
        return True, "Ejecucion lanzada."

    def _correr(self) -> None:
        try:
            self._ejecutar()
        except Exception as exc:  # una pasada que falla no tumba el servidor
            self._estado.estado = "error"
            self._estado.mensaje = f"{type(exc).__name__}: {exc}"
            self._estado.terminada = _ahora()
        finally:
            self._cerrojo.release()

    def _cliente(self) -> Any:
        import anthropic

        return anthropic.Anthropic()

    def _ejecutar(self) -> None:
        pdfs = list(iter_pdfs(self.carpeta_pdf))
        self._estado = Ejecucion(
            estado="corriendo", total=len(pdfs), iniciada=_ahora(),
            mensaje=f"Leyendo {len(pdfs)} documentos con {config.model_id()}",
        )
        if not pdfs:
            self._estado.estado = "terminado"
            self._estado.mensaje = f"No hay PDF en {self.carpeta_pdf}/"
            self._estado.terminada = _ahora()
            return

        estado = self._estado

        def avance(_tipo: str, _nombre: str, _detalle: str) -> None:
            estado.mensaje = f"{estado.pasada.total} de {estado.total}"

        # La misma politica que `extract`: lo ya leido no se vuelve a pagar
        # aunque haya cambiado el modelo o la version. El almacen se abre
        # antes de llamar a nadie: si no se puede, la pasada no gasta nada.
        with preparar(self.ruta_db) as almacen:
            extraer_pasada(
                self._cliente(), pdfs, self.carpeta_salida, model=config.model_id(),
                politica=CONSERVAR, informar=avance, resultado=estado.pasada,
                almacen=almacen,
            )
            if almacen.ruta_anclas is not None:
                anclar(almacen.conn, almacen.ruta_anclas)

        p = estado.pasada
        estado.estado = "terminado"
        estado.terminada = _ahora()
        estado.mensaje = (
            f"{p.extraidas} leidas, {p.reutilizadas} reutilizadas, "
            f"{p.fallidas} con problemas"
        )
        if p.sin_almacen:
            estado.mensaje += f", {p.sin_almacen} sin guardar en el almacen (estan en out/)"


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


PAGINA_LOCAL = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="bms-token" content="{token}">
<title>bms-agent local</title>
<style>
body{{font:15px/1.5 system-ui,sans-serif;margin:2rem auto;max-width:42rem;padding:0 1rem;color:#141a23}}
button{{font:inherit;padding:.5rem 1rem;cursor:pointer}}
pre{{background:#f3f5f8;padding:1rem;overflow:auto}}
</style>
</head>
<body>
<h1>bms-agent, servidor local</h1>
<p>Lanzar una pasada lee los PDF nuevos y <strong>gasta créditos de la API</strong>.
Lo ya leído se reutiliza sin coste.</p>
<p><button id="ejecutar" type="button">Lanzar una pasada</button></p>
<pre id="estado">...</pre>
<script>
const token = document.querySelector('meta[name="bms-token"]').content;
const salida = document.getElementById('estado');
async function pintar() {{
  const r = await fetch('/api/ejecucion');
  salida.textContent = JSON.stringify(await r.json(), null, 2);
}}
document.getElementById('ejecutar').addEventListener('click', async () => {{
  const r = await fetch('/api/ejecutar', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json', 'X-BMS-Token': token}},
    body: '{{}}',
  }});
  salida.textContent = JSON.stringify(await r.json(), null, 2);
}});
pintar();
setInterval(pintar, 2000);
</script>
</body>
</html>
"""


class Manejador(BaseHTTPRequestHandler):
    agente: Agente
    carpeta_salida: Path
    token: str
    puerto: int
    origenes: frozenset[str]

    def _cors(self) -> None:
        origen = self.headers.get("Origin")
        self.send_header("Vary", "Origin")
        if origen_permitido(origen, self.origenes):
            self.send_header("Access-Control-Allow-Origin", origen)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", f"Content-Type, {CABECERA_TOKEN}")

    def _enviar(self, codigo: int, datos: bytes, tipo: str, cors: bool = True) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cors:
            self._cors()
        self.end_headers()
        self.wfile.write(datos)

    def _json(self, codigo: int, cuerpo: dict[str, Any], cors: bool = True) -> None:
        datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        self._enviar(codigo, datos, "application/json; charset=utf-8", cors=cors)

    def _rechazada(self) -> bool:
        """Host y Origin, en toda peticion. True si ya se ha contestado que no.

        Una peticion rechazada no lleva cabeceras CORS: el navegador de la web
        que la hizo no puede leer ni la respuesta de error.
        """
        if not host_permitido(self.headers.get("Host"), self.puerto):
            self._json(421, {"error": "host no permitido"}, cors=False)
            return True
        origen = self.headers.get("Origin")
        if origen is not None and not origen_permitido(origen, self.origenes):
            self._json(403, {"error": "origen no permitido"}, cors=False)
            return True
        return False

    def do_OPTIONS(self) -> None:  # noqa: N802
        if self._rechazada():
            return
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self._rechazada():
            return
        ruta = self.path.split("?", 1)[0].rstrip("/")
        if ruta == "":
            self._pagina()
        elif ruta == "/api/datos":
            registros = load_records(self.carpeta_salida)
            self._json(200, construir_datos(registros))
        elif ruta == "/api/ejecucion":
            self._json(200, self.agente.estado)
        else:
            self._json(404, {"error": "no existe"})

    def _pagina(self) -> None:
        """La pagina local, con el token dentro. Solo la lee el mismo origen.

        No puede ir dentro de un marco de otra web: alli un clic robado en el
        boton lanzaria una pasada que se paga.
        """
        datos = PAGINA_LOCAL.format(token=html.escape(self.token)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )
        self.end_headers()
        self.wfile.write(datos)

    def do_POST(self) -> None:  # noqa: N802
        if self._rechazada():
            return
        if self.path.split("?", 1)[0].rstrip("/") != "/api/ejecutar":
            self._json(404, {"error": "no existe"})
            return
        if not hmac.compare_digest(
            self.headers.get(CABECERA_TOKEN, "").encode("utf-8"), self.token.encode("utf-8")
        ):
            self._json(403, {"error": f"falta la cabecera {CABECERA_TOKEN} o no es valida"})
            return
        if self.headers.get_content_type() != "application/json":
            self._json(415, {"error": "el cuerpo tiene que ser application/json"})
            return
        try:
            largo = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._json(400, {"error": "Content-Length no valido"})
            return
        if largo < 0 or largo > MAX_CUERPO:
            self._json(413, {"error": "cuerpo demasiado grande"})
            return
        crudo = self.rfile.read(largo) if largo else b""
        try:
            cuerpo = json.loads(crudo or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            cuerpo = None
        if not isinstance(cuerpo, dict):
            self._json(400, {"error": "el cuerpo tiene que ser un objeto JSON"})
            return

        lanzada, mensaje = self.agente.lanzar()
        self._json(202 if lanzada else 409, {"lanzada": lanzada, "mensaje": mensaje})

    def log_message(self, formato: str, *args: Any) -> None:
        print(f"  {self.address_string()} {formato % args}")


def crear_servidor(
    carpeta_pdf: str | Path = "facturas",
    carpeta_salida: str | Path = "out",
    puerto: int = 8765,
    *,
    origenes_extra: list[str] | tuple[str, ...] = (),
    token: str | None = None,
    agente: Agente | None = None,
    ruta_db: str | Path | None = None,
) -> ThreadingHTTPServer:
    """Crea el servidor ya escuchando en 127.0.0.1, sin atender todavia.

    Con puerto 0 el sistema elige uno libre; el Host y los origenes se
    calculan con el puerto real. Los tests lo usan asi, con un agente falso.
    """
    agente = agente or Agente(
        Path(carpeta_pdf), Path(carpeta_salida), Path(ruta_db) if ruta_db else None
    )
    servidor = ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
    puerto_real = servidor.server_address[1]
    try:
        permitidos = origenes_permitidos(puerto_real, list(origenes_extra))
    except ValueError:
        servidor.server_close()
        raise
    servidor.RequestHandlerClass = type("ManejadorConfigurado", (Manejador,), {
        "agente": agente,
        "carpeta_salida": Path(carpeta_salida),
        "token": token or nuevo_token(),
        "puerto": puerto_real,
        "origenes": permitidos,
    })
    return servidor


def servir(
    carpeta_pdf: str | Path = "facturas",
    carpeta_salida: str | Path = "out",
    puerto: int = 8765,
    origenes_extra: list[str] | tuple[str, ...] = (),
    ruta_db: str | Path | None = None,
) -> None:
    """Arranca el servidor local. Solo 127.0.0.1, a proposito."""
    servidor = crear_servidor(
        carpeta_pdf, carpeta_salida, puerto, origenes_extra=origenes_extra, ruta_db=ruta_db
    )
    manejador = servidor.RequestHandlerClass
    puerto_real = servidor.server_address[1]
    print(f"Servidor de desarrollo en http://127.0.0.1:{puerto_real}")
    print("  GET  /                pagina local con el boton de ejecutar")
    print("  GET  /api/datos       datos del panel")
    print("  GET  /api/ejecucion   estado de la ultima pasada")
    print(f"  POST /api/ejecutar    lanza una pasada (JSON y cabecera {CABECERA_TOKEN})")
    print(f"\n{CABECERA_TOKEN}: {manejador.token}")
    print("  Cambia en cada arranque. La pagina local ya lo lleva dentro.")
    print("\nOrigenes admitidos: " + ", ".join(sorted(manejador.origenes)))
    print(f"\nLee PDF de {carpeta_pdf}/ y guarda extracciones en {carpeta_salida}/"
          f" y en el almacen {ruta_db or ruta_por_defecto()}")
    print("Solo escucha en 127.0.0.1. No es un servidor de produccion.\n")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nParado.")
        servidor.shutdown()
    finally:
        servidor.server_close()
