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
   paga, aprueba un pago ni presenta el BTW. Desde la revision final,
   /api/datos (el contrato v1, con cada IBAN entero) pide lo mismo que
   /api/v2: un token personal con ver_facturas, y desde un origen declarado
   con --origen sale con los IBAN enmascarados.

5. Paso 13, el entorno de Docker (docker/). Dentro de un contenedor,
   127.0.0.1 es el del propio contenedor y no se puede llegar a el desde
   fuera, asi que alli se escucha en 0.0.0.0 (`--contenedor`), y solo alli:
   fuera de un contenedor se niega. Lo que protege entonces es la red: el
   contenedor de la consola esta en una red interna sin salida, y el unico
   puerto publicado lo esta en el 127.0.0.1 del ordenador del dueno. El Host
   sigue teniendo que ser 127.0.0.1 o localhost. En ese modo la consola no
   lee PDF (no tiene clave ni salida a internet): lo hace el lector, que se
   arranca a proposito.

   Con la base de prueba (demo.sqlite3, paso 13), cada pagina lleva una banda
   fija de DATOS DE PRUEBA y cada respuesta la cabecera X-BMS-Entorno: demo.

6. Paso 14, la instalacion nativa de Windows (docs/instalacion-nativa.md). La
   consola corre con su propio programa, sin red (el cortafuegos de Windows), y
   sigue escuchando solo en 127.0.0.1. Tampoco lee PDF (los lee el lector, con
   leer-facturas). Y pinta arriba una banda roja si la ultima comprobacion de
   aislamiento de algun papel fallo, falta o es vieja (`aislamiento`, que se lee
   en cada pagina): trabajar con datos de verdad sin saber que estan aislados no
   se hace a ciegas.

7. Paso 15, la app local (/app, app_local.py): lo construido de frontend/, servido
   desde una lista blanca de los ficheros de web/ (nunca una ruta de la peticion
   juntada con una carpeta), con su propia politica de contenido (un nonce por
   respuesta para los estilos de las bibliotecas) y las mismas comprobaciones de
   Host y Origin. Las bandas de prueba y de aislamiento las pone el servidor, en
   neerlandes e ingles. /consola sigue como estaba: es la de reserva.
"""

from __future__ import annotations

import hmac
import html
import json
import secrets
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from . import app_local, btw, config, consola, consultas, permisos, relaciones, servicios
from .almacen import preparar, ruta_por_defecto
from .auditoria import AnclasDeOtraBase, anclar
from .cache import CONSERVAR
from .dashboard import construir_datos
from .documents import iter_pdfs
from .extract import ResultadoPasada
from .ingesta import ingestar_pasada
from .legado import leer_registros
from .pricing import estimate_cost

HOSTS_LOCALES = ("127.0.0.1", "localhost")
CABECERA_TOKEN = "X-BMS-Token"
CABECERA_CONTRATO = "X-BMS-Contrato"
CABECERA_ENTORNO = "X-BMS-Entorno"
LOCAL = "127.0.0.1"
TODAS = "0.0.0.0"
# Lo que deja Docker (y Podman) en todo contenedor. Fuera de uno no existen.
MARCAS_CONTENEDOR = (Path("/.dockerenv"), Path("/run/.containerenv"))

# Paso 12: las lecturas de /api/v2, con los parametros que admite cada una. Un
# parametro que no esta en la lista es un 400 en todas: el filtro mal escrito
# no se ignora en silencio (_leer_v2 lo comprueba antes de contestar). La
# busqueda los comprueba ella misma (consultas.FILTROS).
LECTURAS_V2 = (
    ("/api/v2/contrato", ()),
    ("/api/v2/yo", ()),
    ("/api/v2/panel", ()),
    ("/api/v2/buscar", ("ver consultas.FILTROS: /api/v2/contrato",)),
    ("/api/v2/facturas", ("nivel",)),
    ("/api/v2/facturas/N", ()),
    ("/api/v2/facturas/N/historial", ()),
    ("/api/v2/facturas/N/original", ()),
    ("/api/v2/excepciones", ()),
    ("/api/v2/personas", ()),
    ("/api/v2/recursos", ()),
    ("/api/v2/proveedores", ()),
    ("/api/v2/proveedores/N", ()),
    ("/api/v2/clientes", ()),
    ("/api/v2/clientes/N", ()),
    ("/api/v2/objetos", ()),
    ("/api/v2/objetos/N", ("desde", "hasta")),
    ("/api/v2/ordenes", ()),
    ("/api/v2/ordenes/N", ()),
    ("/api/v2/relaciones", ()),
    ("/api/v2/btw", ()),
    ("/api/v2/btw/AAAA-TN", ()),
    ("/api/v2/btw/AAAA-TN/hoja", ()),
    ("/api/v2/btw/AAAA-TN/hoja.csv", ()),
    ("/api/v2/flujo", ("desde", "hasta")),
    ("/api/v2/fuentes", ()),
    ("/api/v2/cuentas", ()),
    ("/api/v2/acciones", ()),
    ("/api/v2/exportar", ()),
)
_BUSCAR = "/api/v2/buscar"
_PARAMETROS_V2 = {ruta: parametros for ruta, parametros in LECTURAS_V2}


def ruta_documentada(partes: list[str]) -> str:
    """La ruta de LECTURAS_V2 de una peticion: los ids son N y el trimestre AAAA-TN."""
    plantilla = ["N" if p.isdigit() else p for p in partes]
    if len(plantilla) >= 2 and plantilla[0] == "btw":
        plantilla[1] = "AAAA-TN"
    return "/api/v2/" + "/".join(plantilla)


def parametros_admitidos(consulta: dict[str, list[str]],
                         admitidos: tuple[str, ...]) -> dict[str, str]:
    """Los parametros de una lectura, uno por nombre. ValueError (un 400) si trae uno que la
    ruta no admite o uno repetido: ignorarlo daria una respuesta que no es la pedida.

    Uno admitido pero vacio (`?nivel=`, lo que deja un formulario sin rellenar)
    es como no ponerlo: asi se leia antes de guardar los valores vacios.
    """
    raros = sorted(set(consulta) - set(admitidos))
    if raros:
        raise ValueError(f"parametro desconocido: {', '.join(raros)}"
                         + (f" (admite {', '.join(admitidos)})" if admitidos
                            else " (no admite ninguno)"))
    salida = {}
    for nombre, valores in consulta.items():
        if len(valores) != 1:
            raise ValueError(f"{nombre}: lleva un valor")
        if valores[0].strip():
            salida[nombre] = valores[0]
    return salida


def nivel_pedido(datos: dict[str, str]) -> str | None:
    """El `nivel` de /api/v2/facturas, o None (todas); uno que no es un nivel, ValueError (antes
    daba una lista vacia, como si no hubiera ninguna factura de ese nivel)."""
    from .dominio import Prioridad

    nivel = datos.get("nivel", "").strip()
    if not nivel:
        return None
    if nivel not in Prioridad.valores():
        raise ValueError(f"nivel: {nivel!r} no es ninguno de {', '.join(Prioridad.valores())}")
    return nivel


# El POST de ejecutar no necesita cuerpo; esto solo impide que alguien
# tenga el hilo ocupado leyendo megas. Una orden de la consola lleva sus datos
# (una nota, un reparto de una linea) y cabe en 64 KiB.
MAX_CUERPO = 4096
MAX_CUERPO_V2 = 65536


def en_contenedor(marcas: tuple[Path, ...] = MARCAS_CONTENEDOR) -> bool:
    """Si el proceso corre dentro de un contenedor (Docker o Podman)."""
    return any(m.exists() for m in marcas)


def interfaz_permitida(interfaz: str, *, contenedor: bool | None = None) -> str:
    """Donde escuchar: 127.0.0.1 siempre; 0.0.0.0 solo dentro de un contenedor.

    Fuera de un contenedor, 0.0.0.0 es la red de la casa o de la oficina, y
    un servidor que lanza pasadas que se pagan no se expone ahi.
    """
    if interfaz == LOCAL:
        return interfaz
    if interfaz != TODAS:
        raise ValueError(f"solo se escucha en {LOCAL} (o en {TODAS} dentro de un contenedor), "
                         f"no en {interfaz!r}")
    if not (en_contenedor() if contenedor is None else contenedor):
        raise ValueError(f"{TODAS} solo dentro de un contenedor: fuera de el seria abrir el "
                         "servidor a toda la red")
    return interfaz


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
        self, carpeta_pdf: Path, carpeta_salida: Path, ruta_db: Path | None = None,
        *, lectura: bool = True,
    ) -> None:
        self.carpeta_pdf = carpeta_pdf
        self.carpeta_salida = carpeta_salida
        self.ruta_db = ruta_db
        self.lectura = lectura
        self._cerrojo = threading.Lock()
        self._estado = Ejecucion()

    @property
    def estado(self) -> dict[str, Any]:
        return self._estado.a_dict()

    def lanzar(self) -> tuple[bool, str]:
        """Arranca una pasada si no hay otra en curso (y si este servidor lee PDF)."""
        if not self.lectura:
            return False, ("Aqui no se leen PDF: los lee el lector, que se arranca a proposito "
                           "(leer-facturas.bat, en Docker y en la instalacion nativa).")
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

        from . import nativo

        nativo.exigir_lectura_si_nativa()
        return anthropic.Anthropic(api_key=config.clave_api())

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
                _anclar(almacen.conn, almacen.ruta_anclas)

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


def _anclar(conn: sqlite3.Connection, ruta: Path) -> None:
    """Ancla lo hecho; si el fichero de anclas es de otra base, lo dice y sigue (cli._anclar)."""
    try:
        anclar(conn, ruta)
    except AnclasDeOtraBase as exc:
        print(f"  AVISO: {exc}")


def _nombre_de_descarga(nombre: str | None, sha256: str) -> str:
    """El nombre con que se guarda un original: el suyo, sin nada que rompa la cabecera
    (comillas, barras, caracteres de control ni nada fuera de ASCII); si no queda nada, su
    hash."""
    limpio = "".join(c for c in (nombre or "") if c.isascii() and (c.isalnum() or c in "._- "))
    limpio = limpio.strip(" .")
    return limpio[:120] or f"{sha256[:12]}.pdf"


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
{banda}<h1>bms-agent, servidor local</h1>
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
    aislamiento: Callable[[], list[str]] | None = None
    demo: bool = False
    app_web: app_local.App = app_local.App(None)

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
        if self.demo:
            self.send_header(CABECERA_ENTORNO, "demo")
        if getattr(self, "_contrato_v2", False):
            # Paso 12: cada respuesta de /api/v2 dice con que version del contrato
            # se escribio (docs/integracion-web.md, "El contrato v2").
            self.send_header(CABECERA_CONTRATO, consultas.CONTRATO_V2)
        if cors:
            self._cors()
        self.end_headers()
        self.wfile.write(datos)

    def _de_otro_origen(self) -> bool:
        """Si la peticion viene de un origen declarado con --origen y no de la propia pagina.

        La consola se sirve desde el mismo origen que la API, y un navegador no
        manda Origin en un GET a su propio origen. Un sitio propio en otro
        puerto si lo manda: ese sitio lee el contrato, pero no ve un IBAN entero
        ni da ordenes (verificar un IBAN o marcar un pago se firma en la
        consola). Sin Origin (curl, un script) no hay navegador de por medio y
        cuenta como la consola.
        """
        origen = normalizar_origen(self.headers.get("Origin"))
        return origen is not None and origen not in {
            f"http://{host}:{self.puerto}" for host in HOSTS_LOCALES}

    def _json(self, codigo: int, cuerpo: dict[str, Any], cors: bool = True) -> None:
        if getattr(self, "_contrato_v2", False) and self._de_otro_origen():
            cuerpo = consultas.sin_ibanes(cuerpo)
        datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        self._enviar(codigo, datos, "application/json; charset=utf-8", cors=cors)

    def _rechazada(self) -> bool:
        """Host y Origin, en toda peticion. True si ya se ha contestado que no.

        Una peticion rechazada no lleva cabeceras CORS: el navegador de la web
        que la hizo no puede leer ni la respuesta de error.
        """
        if not host_permitido(self.headers.get("Host"), self.puerto):
            self._json(421, {"error": "host no permitido", "codigo": "host_no_permitido"},
                       cors=False)
            return True
        origen = self.headers.get("Origin")
        if origen is not None and not origen_permitido(origen, self.origenes):
            self._json(403, {"error": "origen no permitido", "codigo": "origen_no_permitido"},
                       cors=False)
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
        self._contrato_v2 = False
        if self._rechazada():
            return
        ruta = self.path.split("?", 1)[0].rstrip("/")
        if ruta == "":
            self._pagina()
        elif ruta == app_local.RUTA:
            self._app_pagina()
        elif ruta.startswith(app_local.PREFIJO_FICHEROS):
            self._app_fichero(ruta)
        elif consola.fichero(ruta) is not None:
            self._consola(ruta)
        elif ruta.startswith("/api/v2/"):
            self._leer_v2(ruta)
        elif ruta == "/api/datos":
            self._datos_v1()
        elif ruta == "/api/ejecucion":
            self._json(200, self.agente.estado)
        else:
            self._json(404, {"error": "no existe", "codigo": "no_existe"})

    def _pagina(self) -> None:
        """La pagina local, con el token dentro. Solo la lee el mismo origen.

        No puede ir dentro de un marco de otra web: alli un clic robado en el
        boton lanzaria una pasada que se paga.
        """
        banda = (f'<p style="background:#a4161a;color:#fff;padding:.4rem .8rem;'
                 f'font-weight:700">{consola.TEXTO_DEMO}</p>\n' if self.demo else "")
        problemas = self._problemas_aislamiento()
        if problemas:
            banda += (f'<p style="background:#a4161a;color:#fff;padding:.4rem .8rem;'
                      f'font-weight:700">{html.escape(consola.texto_aislamiento(problemas))}'
                      '</p>\n')
        datos = PAGINA_LOCAL.format(token=html.escape(self.token), banda=banda).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if self.demo:
            self.send_header(CABECERA_ENTORNO, "demo")
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
            self._json(415, {"error": "el cuerpo tiene que ser application/json",
                             "codigo": "tipo_no_admitido"})
            return None
        try:
            largo = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._json(400, {"error": "Content-Length no valido", "codigo": "invalido"})
            return None
        if largo < 0 or largo > maximo:
            self._json(413, {"error": "cuerpo demasiado grande", "codigo": "demasiado_grande"})
            return None
        crudo = self.rfile.read(largo) if largo else b""
        try:
            cuerpo = json.loads(crudo or b"{}", parse_float=_sin_floats)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            cuerpo = None
        if not isinstance(cuerpo, dict):
            self._json(400, {"error": "el cuerpo tiene que ser un objeto JSON (sin numeros con "
                                      "decimales: los importes van como texto)",
                             "codigo": "invalido"})
            return None
        return cuerpo

    def do_POST(self) -> None:  # noqa: N802
        self._contrato_v2 = False
        if self._rechazada():
            return
        ruta = self.path.split("?", 1)[0].rstrip("/")
        if ruta == "/api/v2/acciones":
            self._accion_v2()
            return
        if ruta != "/api/ejecutar":
            self._json(404, {"error": "no existe", "codigo": "no_existe"})
            return
        if not hmac.compare_digest(
            self.headers.get(CABECERA_TOKEN, "").encode("utf-8"), self.token.encode("utf-8")
        ):
            self._json(403, {"error": f"falta la cabecera {CABECERA_TOKEN} o no es valida",
                             "codigo": "no_autenticado"})
            return
        if self._cuerpo_json(MAX_CUERPO) is None:
            return

        lanzada, mensaje = self.agente.lanzar()
        self._json(202 if lanzada else 409, {"lanzada": lanzada, "mensaje": mensaje})

    # ---- consola y /api/v2

    def _problemas_aislamiento(self) -> list[str]:
        """Lo que falla o falta del aislamiento (instalacion nativa); vacio fuera de ella."""
        return list(self.aislamiento()) if self.aislamiento is not None else []

    def _consola(self, ruta: str) -> None:
        tipo, datos = consola.fichero(ruta, demo=self.demo,
                                      aislamiento=self._problemas_aislamiento())
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        if self.demo:
            self.send_header(CABECERA_ENTORNO, "demo")
        for nombre, valor in consola.cabeceras().items():
            self.send_header(nombre, valor)
        self.end_headers()
        self.wfile.write(datos)

    # ---- la app local (paso 15)

    def _enviar_con(self, codigo: int, tipo: str, datos: bytes, cabeceras: dict[str, str]) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        if self.demo:
            self.send_header(CABECERA_ENTORNO, "demo")
        for nombre, valor in cabeceras.items():
            self.send_header(nombre, valor)
        self.end_headers()
        self.wfile.write(datos)

    def _app_pagina(self) -> None:
        """index.html con su nonce y sus bandas. Sin construir, lo dice y manda a /consola."""
        nonce = app_local.nuevo_nonce()
        try:
            datos = app_local.pagina(self.app_web, nonce=nonce, demo=self.demo,
                                     aislamiento=self._problemas_aislamiento())
        except app_local.AppMalConstruida:
            self._enviar_con(503, "text/plain; charset=utf-8", app_local.SIN_CONSTRUIR,
                             {**app_local.cabeceras_pagina(nonce)})
            return
        self._enviar_con(200, "text/html; charset=utf-8", datos,
                         app_local.cabeceras_pagina(nonce))

    def _app_fichero(self, ruta: str) -> None:
        """Un fichero de la lista blanca, por su nombre exacto; cualquier otra cosa, 404."""
        fichero = self.app_web.ficheros.get(ruta)
        if fichero is None:
            self._json(404, {"error": "no existe", "codigo": "no_existe"}, cors=False)
            return
        self._enviar_con(200, fichero.tipo, fichero.datos, app_local.cabeceras_fichero())

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
            self._json(401, {"error": f"falta un token personal valido en {CABECERA_TOKEN}",
                             "codigo": "no_autenticado"})
        return usuario_id

    def _datos_v1(self) -> None:
        """El contrato v1 (el panel de siempre), con la misma puerta que /api/v2.

        Lleva cada factura con su IBAN entero: sin token cualquier proceso del
        ordenador (otro usuario de Windows, un programa cualquiera) lo leia
        entero, y un origen declarado con --origen tambien, aunque /api/v2 se
        lo enmascara. Ahora pide el token personal de alguien con ver_facturas
        y, desde un origen declarado, sale con los IBAN enmascarados. Desde la
        consola (el mismo origen) sigue siendo byte a byte la foto de
        referencia. Del almacen, con los valores corregidos; de out/ solo si no
        hay facturas en el almacen.
        """
        with self._almacen() as almacen:
            conn = almacen.conn
            usuario_id = self._persona(conn, "GET /api/datos")
            if usuario_id is None:
                return
            try:
                permisos.exigir(conn, usuario_id, "ver_facturas", accion="GET /api/datos")
            except permisos.PermisoDenegado as exc:
                self._json(403, {"error": str(exc), "codigo": servicios.codigo_de_error(exc)})
                return
        lectura = leer_registros(self.carpeta_salida, self.ruta_db or ruta_por_defecto())
        cuerpo = construir_datos(lectura.registros)
        if self._de_otro_origen():
            cuerpo = consultas.sin_ibanes(cuerpo)
        self._json(200, cuerpo)

    def _leer_v2(self, ruta: str) -> None:
        """Las lecturas de la consola: piden un token personal con ver_facturas."""
        self._contrato_v2 = True
        consulta = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        with self._almacen() as almacen:
            conn = almacen.conn
            usuario_id = self._persona(conn, f"GET {ruta}")
            if usuario_id is None:
                return
            try:
                permisos.exigir(conn, usuario_id, "ver_facturas", accion=f"GET {ruta}")
            except permisos.PermisoDenegado as exc:
                self._json(403, {"error": str(exc), "codigo": servicios.codigo_de_error(exc)})
                return
            partes = ruta.split("/")[3:]
            try:
                documentada = ruta_documentada(partes)
                datos: dict[str, str] = {}
                if documentada in _PARAMETROS_V2 and documentada != _BUSCAR:
                    datos = parametros_admitidos(consulta, _PARAMETROS_V2[documentada])
                if self._descarga(almacen, usuario_id, partes):
                    return
                if self._leer_paso_12(conn, partes, consulta, datos):
                    return
                if partes == ["yo"]:
                    fila = conn.execute("SELECT nombre FROM usuario WHERE id = ?",
                                        (usuario_id,)).fetchone()
                    self._json(200, {"id": usuario_id, "nombre": fila["nombre"],
                                     "permisos": sorted(permisos.permisos_de(conn, usuario_id))})
                elif partes == ["facturas"]:
                    self._json(200, {"facturas": consultas.listado(
                        conn, nivel=nivel_pedido(datos))})
                elif len(partes) == 2 and partes[0] == "facturas" and partes[1].isdigit():
                    self._json(200, {"factura": consultas.detalle(conn, int(partes[1]))})
                elif partes == ["excepciones"]:
                    self._json(200, {"excepciones": consultas.excepciones_abiertas(conn)})
                elif partes == ["personas"]:
                    self._json(200, {"personas": consultas.personas(conn)})
                elif partes == ["recursos"]:
                    self._json(200, {"recursos": consultas.recursos(conn)})
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
                        self._json(404, {"error": str(exc), "codigo": "no_existe"})
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
                    self._json(404, {"error": "no existe", "codigo": "no_existe"})
            except LookupError as exc:
                self._json(404, {"error": str(exc), "codigo": "no_existe"})
            except ValueError as exc:
                # Un filtro o un parametro que no se entiende (FiltroNoValido es uno).
                self._json(400, {"error": str(exc), "codigo": "invalido"})

    def _descarga(self, almacen: Any, usuario_id: int, partes: list[str]) -> bool:
        """Lo que se descarga como fichero: el original de una factura y la hoja del BTW.

        Los dos llevan sus bytes tal cual (el original es la evidencia; la hoja,
        lo que se hashea y se anota al presentar), como adjunto y sin CORS:
        solo la consola, nunca un sitio de otro origen. Abrir un original
        queda en la auditoria (documento_abierto, documentos.abrir); hojearlo
        a mano dentro de datos/documentos/ no. True si la ruta era una de ellas.
        """
        from .almacen.documentos import DocumentoCorrupto, abrir

        original = (len(partes) == 3 and partes[0] == "facturas" and partes[1].isdigit()
                    and partes[2] == "original")
        hoja = len(partes) == 3 and partes[0] == "btw" and partes[2] == "hoja.csv"
        if not (original or hoja):
            return False
        if self._de_otro_origen():
            self._json(403, {"error": "un fichero solo se descarga desde la consola",
                             "codigo": "otro_origen"},
                       cors=False)
            return True
        conn = almacen.conn
        if hoja:
            ano, numero = btw.leer_etiqueta(partes[1])
            contenido = btw.hoja(conn, ano, numero).en_bytes()
            nombre, tipo = f"btw-{btw.etiqueta(ano, numero)}.csv", "text/csv; charset=utf-8"
        else:
            fila = conn.execute(
                "SELECT d.id, d.nombre_original, d.tipo_mime, d.sha256 FROM factura AS f "
                "JOIN documento AS d ON d.id = f.documento_id WHERE f.id = ?",
                (int(partes[1]),)).fetchone()
            if fila is None:
                raise LookupError(f"la factura {partes[1]} no tiene documento (llego de otro "
                                  "sistema)")
            try:
                contenido = abrir(almacen, fila["id"], actor=usuario_id, usuario_id=usuario_id,
                                  motivo=f"descargado desde la consola (factura {partes[1]})")
            except DocumentoCorrupto as exc:
                raise LookupError(str(exc)) from None
            nombre = _nombre_de_descarga(fila["nombre_original"], fila["sha256"])
            tipo = fila["tipo_mime"]
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(contenido)))
        self.send_header("Content-Disposition", f'attachment; filename="{nombre}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
        if self.demo:
            self.send_header(CABECERA_ENTORNO, "demo")
        self.end_headers()
        self.wfile.write(contenido)
        return True

    def _leer_paso_12(self, conn: Any, partes: list[str], consulta: dict[str, list[str]],
                      datos: dict[str, str]) -> bool:
        """Las lecturas del paso 12: el panel, la busqueda, la historia de una factura, los
        Objetos con su economia, el flujo de caja, el contrato y el export entero. True si la
        ruta era una de ellas (y ya se contesto). `datos` son sus parametros, ya comprobados
        contra LECTURAS_V2."""
        from datetime import date as _date

        def fecha(nombre: str) -> _date | None:
            if nombre not in datos:
                return None
            try:
                return _date.fromisoformat(datos[nombre])
            except ValueError:
                raise ValueError(f"{nombre}: {datos[nombre]!r} no es una fecha AAAA-MM-DD") from None

        if partes == ["contrato"]:
            self._json(200, {"contrato": consultas.CONTRATO_V2,
                             "lecturas": [{"ruta": r, "parametros": list(p)}
                                          for r, p in LECTURAS_V2],
                             "filtros": consultas.filtros(),
                             "ordenes": "POST /api/v2/acciones (GET /api/v2/acciones las lista)"})
        elif partes == ["panel"]:
            self._json(200, {"panel": consultas.panel(conn)})
        elif partes == ["buscar"]:
            self._json(200, {"busqueda": consultas.buscar(conn, consulta)})
        elif len(partes) == 3 and partes[0] == "facturas" and partes[1].isdigit() \
                and partes[2] == "historial":
            self._json(200, {"historial": consultas.historial_factura(conn, int(partes[1]))})
        elif partes == ["objetos"]:
            self._json(200, consultas.objetos_resumen(conn))
        elif len(partes) == 2 and partes[0] == "objetos" and partes[1].isdigit():
            self._json(200, {"objeto": consultas.objeto(
                conn, int(partes[1]), desde=fecha("desde"), hasta=fecha("hasta"))})
        elif partes == ["flujo"]:
            from . import flujo_caja
            from .almacen import reloj_de

            self._json(200, {"flujo_caja": flujo_caja.flujo(
                conn, reloj_de(conn).hoy(), desde=fecha("desde"), hasta=fecha("hasta"))})
        elif partes == ["exportar"]:
            self._json(200, consultas.exportar_v2(conn))
        else:
            return False
        return True

    def _accion_v2(self) -> None:
        """Una orden de una persona: su token, su permiso y todo en una transaccion.

        Solo desde la consola (o sin navegador): un sitio de otro origen lee, pero
        no verifica un IBAN, no marca un pago ni anula un aviso con el token de
        quien lo tenga (_de_otro_origen).
        """
        self._contrato_v2 = True
        if self._de_otro_origen():
            self._json(403, {"error": "las ordenes se dan desde la consola, no desde otro "
                                      "origen", "codigo": "otro_origen"})
            return
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
                             + (f"; no lleva {', '.join(sobran)}" if sobran else ""),
                             "codigo": "invalido"})
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
                self._json(codigo, {"error": str(exc), "tipo": type(exc).__name__,
                                    "codigo": servicios.codigo_de_error(exc)})
                return
            if almacen.ruta_anclas is not None:
                _anclar(conn, almacen.ruta_anclas)
        self._json(200, {"ok": True, "diferencia": diferencia.a_dict()})

    def log_message(self, formato: str, *args: Any) -> None:
        # Como el de la biblioteca: la linea de la peticion la escribe quien pide, y sus
        # caracteres de control no llegan a la terminal (terminal.py).
        texto = (formato % args).translate(self._control_char_table)
        print(f"  {self.address_string()} {texto}")


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
    interfaz: str = LOCAL,
    lectura: bool = True,
    aislamiento: Callable[[], list[str]] | None = None,
    carpeta_web: str | Path | None = None,
) -> ThreadingHTTPServer:
    """Crea el servidor ya escuchando en 127.0.0.1, sin atender todavia.

    Con puerto 0 el sistema elige uno libre; el Host y los origenes se
    calculan con el puerto real. Los tests lo usan asi, con un agente falso.
    `interfaz` 0.0.0.0 solo dentro de un contenedor (interfaz_permitida), y
    `lectura` False deja el boton de lanzar una pasada sin efecto. `aislamiento`
    (instalacion nativa) da lo que falla del aislamiento, para la banda roja.
    `carpeta_web` es la app construida (por defecto, la del paquete): se lee una vez,
    aqui, y es la lista blanca de /app.
    """
    from .demo import es_demo

    interfaz = interfaz_permitida(interfaz)
    agente = agente or Agente(
        Path(carpeta_pdf), Path(carpeta_salida), Path(ruta_db) if ruta_db else None,
        lectura=lectura,
    )
    servidor = ThreadingHTTPServer((interfaz, puerto), Manejador)
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
        "demo": es_demo(Path(ruta_db) if ruta_db else ruta_por_defecto()),
        "aislamiento": staticmethod(aislamiento) if aislamiento is not None else None,
        "app_web": app_local.cargar(Path(carpeta_web) if carpeta_web else app_local.CARPETA_WEB),
    })
    return servidor


def servir(
    carpeta_pdf: str | Path = "facturas",
    carpeta_salida: str | Path = "out",
    puerto: int = 8765,
    origenes_extra: list[str] | tuple[str, ...] = (),
    ruta_db: str | Path | None = None,
    contenedor: bool = False,
    lectura: bool | None = None,
    aislamiento: Callable[[], list[str]] | None = None,
) -> None:
    """Arranca el servidor local. Solo 127.0.0.1, a proposito; dentro de un contenedor
    (`contenedor`), en 0.0.0.0 y sin leer PDF. En la instalacion nativa, sin leer PDF
    (`lectura` False) y con la banda del aislamiento."""
    servidor = crear_servidor(
        carpeta_pdf, carpeta_salida, puerto, origenes_extra=origenes_extra, ruta_db=ruta_db,
        interfaz=TODAS if contenedor else LOCAL,
        lectura=(not contenedor) if lectura is None else lectura, aislamiento=aislamiento,
    )
    manejador = servidor.RequestHandlerClass
    puerto_real = servidor.server_address[1]
    if manejador.demo:
        print(f"*** {consola.TEXTO_DEMO} ***")
    if aislamiento is not None and aislamiento():
        print(f"*** {consola.texto_aislamiento(aislamiento())} ***")
    print(f"Servidor de desarrollo en http://127.0.0.1:{puerto_real}")
    print("  GET  /                pagina local con el boton de ejecutar")
    print("  GET  /api/datos       datos del panel (con un token personal, como /api/v2)")
    print("  GET  /api/ejecucion   estado de la ultima pasada")
    print(f"  POST /api/ejecutar    lanza una pasada (JSON y cabecera {CABECERA_TOKEN})")
    print("  GET  /app             la app local (se entra con el token personal)")
    print("  GET  /consola         la consola de antes, de reserva (el mismo token)")
    print("  GET  /api/v2/...      panel, busqueda, facturas, ficha e historia, excepciones, "
          "proveedores, clientes, ordenes de compra, Objetos, BTW, flujo de caja y el "
          f"export entero (token personal; contrato {consultas.CONTRATO_V2}: /api/v2/contrato)")
    print("  POST /api/v2/acciones las ordenes de las personas (token personal)")
    print(f"\n{CABECERA_TOKEN}: {manejador.token}")
    print("  Cambia en cada arranque. La pagina local ya lo lleva dentro.")
    print("\nOrigenes admitidos: " + ", ".join(sorted(manejador.origenes)))
    print(f"\nLee PDF de {carpeta_pdf}/ y guarda extracciones en {carpeta_salida}/"
          f" y en el almacen {ruta_db or ruta_por_defecto()}")
    if contenedor:
        print("Dentro del contenedor escucha en 0.0.0.0; desde fuera solo se llega por el "
              "127.0.0.1 del ordenador (el puerto que publica docker compose). Aqui no se "
              "leen PDF: lo hace el lector.\n")
    else:
        print("Solo escucha en 127.0.0.1. No es un servidor de produccion.\n")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nParado.")
        servidor.shutdown()
    finally:
        servidor.server_close()
