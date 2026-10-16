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

4. Desde el paso 4, /api/v2 y la consola (/consola). Ahi X-BMS-Token es el
   token personal de quien usa la consola (permisos.emitir_token; la base
   guarda solo su hash): dice quien es, y cada lectura pide ver_facturas y
   cada orden su permiso (servicios.py). Las mismas comprobaciones de Host,
   Origin, cabecera y JSON valen para todo. Ninguna orden crea una factura,
   paga, aprueba un pago ni presenta el BTW.
"""

from __future__ import annotations

import hmac
import html
import json
import secrets
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from . import btw, config, consola, consultas, permisos, relaciones, servicios
from .almacen import preparar, ruta_por_defecto
from .auditoria import anclar
from .cache import CONSERVAR
from .dashboard import construir_datos
from .documents import iter_pdfs
from .extract import ResultadoPasada
from .ingesta import ingestar_pasada
from .legado import leer_registros
from .pricing import estimate_cost

HOSTS_LOCALES = ("127.0.0.1", "localhost")
CABECERA_TOKEN = "X-BMS-Token"
# El POST de ejecutar no necesita cuerpo; esto solo impide que alguien
# tenga el hilo ocupado leyendo megas. Una orden de la consola lleva sus datos
# (una nota, un reparto de una linea) y cabe en 64 KiB.
MAX_CUERPO = 4096
MAX_CUERPO_V2 = 65536


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
            _pasada, ingesta = ingestar_pasada(
                self._cliente(), pdfs, self.carpeta_salida, almacen=almacen,
                model=config.model_id(), politica=CONSERVAR, informar=avance,
                resultado_pasada=estado.pasada,
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
        if ingesta.errores:
            estado.mensaje += f", {len(ingesta.errores)} sin tipar"
            p.errores.extend(f"documento {t.documento_id}: {t.detalle}" for t in ingesta.errores)


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
    ruta_db: Path | None = None
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
        elif consola.fichero(ruta) is not None:
            self._consola(ruta)
        elif ruta.startswith("/api/v2/"):
            self._leer_v2(ruta)
        elif ruta == "/api/datos":
            # Del almacen, con los valores corregidos; de out/ solo si no hay almacen.
            lectura = leer_registros(self.carpeta_salida, self.ruta_db or ruta_por_defecto())
            self._json(200, construir_datos(lectura.registros))
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

    def _cuerpo_json(self, maximo: int) -> dict[str, Any] | None:
        """El cuerpo de un POST: application/json, un objeto, de un tamano razonable.

        Contesta el error y devuelve None si no lo es.
        """
        if self.headers.get_content_type() != "application/json":
            self._json(415, {"error": "el cuerpo tiene que ser application/json"})
            return None
        try:
            largo = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._json(400, {"error": "Content-Length no valido"})
            return None
        if largo < 0 or largo > maximo:
            self._json(413, {"error": "cuerpo demasiado grande"})
            return None
        crudo = self.rfile.read(largo) if largo else b""
        try:
            cuerpo = json.loads(crudo or b"{}", parse_float=_sin_floats)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            cuerpo = None
        if not isinstance(cuerpo, dict):
            self._json(400, {"error": "el cuerpo tiene que ser un objeto JSON (sin numeros con "
                                      "decimales: los importes van como texto)"})
            return None
        return cuerpo

    def do_POST(self) -> None:  # noqa: N802
        if self._rechazada():
            return
        ruta = self.path.split("?", 1)[0].rstrip("/")
        if ruta == "/api/v2/acciones":
            self._accion_v2()
            return
        if ruta != "/api/ejecutar":
            self._json(404, {"error": "no existe"})
            return
        if not hmac.compare_digest(
            self.headers.get(CABECERA_TOKEN, "").encode("utf-8"), self.token.encode("utf-8")
        ):
            self._json(403, {"error": f"falta la cabecera {CABECERA_TOKEN} o no es valida"})
            return
        if self._cuerpo_json(MAX_CUERPO) is None:
            return

        lanzada, mensaje = self.agente.lanzar()
        self._json(202 if lanzada else 409, {"lanzada": lanzada, "mensaje": mensaje})

    # ---- consola y /api/v2

    def _consola(self, ruta: str) -> None:
        tipo, datos = consola.fichero(ruta)
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        for nombre, valor in consola.cabeceras().items():
            self.send_header(nombre, valor)
        self.end_headers()
        self.wfile.write(datos)

    def _almacen(self) -> Any:
        return preparar(self.ruta_db or ruta_por_defecto())

    def _persona(self, conn: Any, accion: str) -> int | None:
        """La persona del token personal. Si no hay o no vale, contesta 401.

        Solo se audita un token que llega y no vale. Una peticion sin token
        no escribe nada: un <img src> de cualquier web llega sin Origin y sin
        token, y si cada una dejara un evento, cualquier pagina podria llenar
        la auditoria. Poner X-BMS-Token desde otra web pide una consulta CORS
        previa, que ya se rechaza por su Origin.
        """
        token = self.headers.get(CABECERA_TOKEN)
        usuario_id = permisos.usuario_por_token(conn, token)
        if usuario_id is None:
            if token:
                permisos.registrar_denegacion(conn, permisos.PermisoDenegado(
                    None, "ver_facturas", "token personal no valido", accion))
            self._json(401, {"error": f"falta un token personal valido en {CABECERA_TOKEN}"})
        return usuario_id

    def _leer_v2(self, ruta: str) -> None:
        """Las lecturas de la consola: piden un token personal con ver_facturas."""
        consulta = parse_qs(urlsplit(self.path).query)
        with self._almacen() as almacen:
            conn = almacen.conn
            usuario_id = self._persona(conn, f"GET {ruta}")
            if usuario_id is None:
                return
            try:
                permisos.exigir(conn, usuario_id, "ver_facturas", accion=f"GET {ruta}")
            except permisos.PermisoDenegado as exc:
                self._json(403, {"error": str(exc)})
                return
            partes = ruta.split("/")[3:]
            try:
                if partes == ["yo"]:
                    fila = conn.execute("SELECT nombre FROM usuario WHERE id = ?",
                                        (usuario_id,)).fetchone()
                    self._json(200, {"id": usuario_id, "nombre": fila["nombre"],
                                     "permisos": sorted(permisos.permisos_de(conn, usuario_id))})
                elif partes == ["facturas"]:
                    nivel = (consulta.get("nivel") or [None])[0]
                    self._json(200, {"facturas": consultas.listado(conn, nivel=nivel)})
                elif len(partes) == 2 and partes[0] == "facturas" and partes[1].isdigit():
                    self._json(200, {"factura": consultas.detalle(conn, int(partes[1]))})
                elif partes == ["excepciones"]:
                    self._json(200, {"excepciones": consultas.excepciones_abiertas(conn)})
                elif partes == ["personas"]:
                    self._json(200, {"personas": consultas.personas(conn)})
                elif partes == ["objetos"]:
                    self._json(200, {"objetos": consultas.objetos(conn)})
                elif len(partes) == 2 and partes[0] == "objetos" and partes[1].isdigit():
                    self._json(200, {"objeto": consultas.objeto(conn, int(partes[1]))})
                elif partes == ["ordenes"]:
                    self._json(200, {"ordenes": consultas.ordenes_compra(conn)})
                elif len(partes) == 2 and partes[0] == "ordenes" and partes[1].isdigit():
                    self._json(200, {"orden": consultas.orden_compra(conn, int(partes[1]))})
                elif partes == ["fuentes"]:
                    self._json(200, {"fuentes": consultas.fuentes(conn)})
                elif partes == ["cuentas"]:
                    self._json(200, {"cuentas": consultas.cuentas(conn)})
                elif partes == ["proveedores"]:
                    self._json(200, {"proveedores": consultas.proveedores(conn)})
                elif len(partes) == 2 and partes[0] == "proveedores" and partes[1].isdigit():
                    self._json(200, {"proveedor": consultas.proveedor(conn, int(partes[1]))})
                elif partes == ["clientes"]:
                    self._json(200, {"clientes": consultas.clientes(conn)})
                elif len(partes) == 2 and partes[0] == "clientes" and partes[1].isdigit():
                    self._json(200, {"cliente": consultas.cliente(conn, int(partes[1]))})
                elif partes == ["relaciones"]:
                    self._json(200, {"relaciones": relaciones.propuestas(conn)})
                elif partes == ["btw"]:
                    self._json(200, {"btw": btw.resumen(conn)})
                elif len(partes) in (2, 3) and partes[0] == "btw" and partes[2:] in ([], ["hoja"]):
                    try:
                        ano, numero = btw.leer_etiqueta(partes[1])
                    except ValueError as exc:
                        self._json(404, {"error": str(exc)})
                        return
                    if partes[2:] == ["hoja"]:
                        hoja = btw.hoja(conn, ano, numero)
                        self._json(200, {"trimestre": btw.etiqueta(ano, numero),
                                         "sha256": hoja.sha256, "texto": hoja.texto})
                    else:
                        self._json(200, {"trimestre": btw.trimestre(conn, ano, numero)})
                elif partes == ["acciones"]:
                    self._json(200, {"acciones": [
                        {"nombre": a.nombre, "permiso": a.permiso, "descripcion": a.descripcion,
                         "motivo": a.motivo, "parametros": [
                             {"nombre": p.nombre, "tipo": p.tipo, "obligatorio": p.obligatorio}
                             for p in a.parametros]}
                        for a in servicios.ACCIONES.values()]})
                else:
                    self._json(404, {"error": "no existe"})
            except LookupError as exc:
                self._json(404, {"error": str(exc)})

    def _accion_v2(self) -> None:
        """Una orden de una persona: su token, su permiso y todo en una transaccion."""
        cuerpo = self._cuerpo_json(MAX_CUERPO_V2)
        if cuerpo is None:
            return
        nombre = cuerpo.get("accion")
        datos = cuerpo.get("datos") or {}
        sobran = sorted(set(cuerpo) - {"accion", "peticion_id", "datos"})
        if not isinstance(nombre, str) or not isinstance(datos, dict) or sobran:
            # La segunda firma ya no viaja aqui con el token de otra persona: es una
            # orden suya (firmar_anulacion), desde su propia sesion.
            self._json(400, {"error": "una orden es {accion, peticion_id, datos}"
                             + (f"; no lleva {', '.join(sobran)}" if sobran else "")})
            return
        with self._almacen() as almacen:
            conn = almacen.conn
            usuario_id = self._persona(conn, nombre)
            if usuario_id is None:
                return
            try:
                diferencia = servicios.ejecutar(
                    conn, nombre, datos, usuario_id=usuario_id,
                    peticion_id=cuerpo.get("peticion_id"))
            except Exception as exc:  # cada error de la orden tiene su codigo
                codigo = _codigo_de(exc)
                if codigo is None:
                    raise
                self._json(codigo, {"error": str(exc), "tipo": type(exc).__name__})
                return
            if almacen.ruta_anclas is not None:
                anclar(conn, almacen.ruta_anclas)
        self._json(200, {"ok": True, "diferencia": diferencia.a_dict()})

    def log_message(self, formato: str, *args: Any) -> None:
        print(f"  {self.address_string()} {formato % args}")


def _sin_floats(texto: str) -> Any:
    """Un numero con decimales en JSON llega como float y pierde centimos: no se admite."""
    raise ValueError(f"numero con decimales {texto}: los importes van como texto")


def _codigo_de(error: Exception) -> int | None:
    """El codigo HTTP de un error de una orden, o None si es un fallo de verdad."""
    from .btw import EstadoNoValido as EstadoBtw
    from .campos import CampoDeOtroSistema, CampoNoEditable, Conflicto, FaltaMotivo
    from .estados import NoSube
    from .excepciones import BloqueoAbierto, EstadoNoValido as EstadoExcepcion
    from .hallazgos import EstadoNoValido as EstadoHallazgo, NoAnulable
    from .pagos import PagoNoValido
    from .revision import NoRevisable

    if isinstance(error, permisos.PermisoDenegado):
        return 403
    if isinstance(error, sqlite3.IntegrityError):
        # Lo que la base no admite (una clave que no existe, un disparador): la
        # orden choca con el estado del almacen, no es un fallo del servidor.
        return 409
    if isinstance(error, (Conflicto, servicios.PeticionRepetida)):
        return 409
    if isinstance(error, (BloqueoAbierto, EstadoExcepcion, EstadoHallazgo, NoAnulable,
                          NoRevisable, NoSube, CampoDeOtroSistema, CampoNoEditable,
                          PagoNoValido, EstadoBtw)):
        return 409
    if isinstance(error, LookupError):
        return 404
    if isinstance(error, (FaltaMotivo, servicios.AccionDesconocida, servicios.DatosNoValidos,
                          ValueError, TypeError)):
        return 400
    return None


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
        "ruta_db": Path(ruta_db) if ruta_db else getattr(agente, "ruta_db", None),
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
    print("  GET  /api/datos       datos del panel (del almacen; de out/ si no hay almacen)")
    print("  GET  /api/ejecucion   estado de la ultima pasada")
    print(f"  POST /api/ejecutar    lanza una pasada (JSON y cabecera {CABECERA_TOKEN})")
    print("  GET  /consola         consola interna (se entra con el token personal)")
    print("  GET  /api/v2/...      facturas, ficha, excepciones, proveedores, clientes, "
          "ordenes de compra, Objetos, BTW (token personal)")
    print("  POST /api/v2/acciones las ordenes de las personas (token personal)")
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
