"""La app local de BMS (paso 15): lo que sirve serve.py en /app.

La app se escribe en frontend/ (React y TypeScript) y se construye aqui, en web/: una
pagina (index.html) y sus ficheros (assets/, con el hash en el nombre). Lo construido va
en git porque las instalaciones de Windows y de Docker no tienen Node; web/fuente.json
lleva la huella de lo que entro en la construccion, y tests/test_app_local.py falla si
alguien cambio el frontend sin volver a construir.

Lo que la hace segura, igual que la consola (consola.py):

- Se sirve SOLO lo que hay en web/, por una lista blanca que se hace al arrancar con los
  ficheros que existen (un diccionario de nombre exacto). Ninguna ruta de una peticion se
  junta nunca con una carpeta: "/app/assets/../x" no esta en el diccionario y es un 404.
- La politica de contenido solo deja el script y el estilo propios, las fuentes propias y
  hablar con el propio servidor. Un dato que traiga HTML no puede ejecutar nada aunque
  alguien lo pintara mal, y la app no lo pinta nunca como HTML (textContent de React).
  Ademas Trusted Types: una asignacion a innerHTML, aunque la hubiera, falla.
- Los <style> que meten dos bibliotecas (el bloqueo del scroll de los menus y de la hoja
  del movil) llevan un nonce nuevo en cada respuesta, que va en la CSP y en
  <meta name="bms-nonce">. Sin el, la CSP los bloquearia; con 'unsafe-inline', pasaria
  cualquier estilo inyectado.
- No se deja meter en un marco (un clic robado no puede dar una orden) ni manda Referer.

Con la base de prueba, la pagina lleva arriba la banda de TESTGEGEVENS · TEST DATA, y en
la instalacion nativa la banda roja del aislamiento si falla: las pone el servidor (como
en /consola), asi que se ven aunque el script no cargue. La app esta en neerlandes e
ingles, asi que las bandas tambien; el texto de los problemas del aislamiento (que se lee
de un fichero que se puede escribir) no se copia: se dice que papel falla, escapado.
"""

from __future__ import annotations

import html
import re
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

CARPETA_WEB = Path(__file__).parent / "web"
RUTA = "/app"
PREFIJO_FICHEROS = "/app/assets/"

# Los unicos tipos que se sirven; un fichero de otra extension en web/assets no entra en
# la lista blanca (un .map, un .html que alguien dejara alli).
TIPOS: dict[str, str] = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".woff2": "font/woff2",
    ".svg": "image/svg+xml",
}
# Un nombre como los que da Vite (index-CaxJXgyI.js): letras, cifras, punto, guion y
# guion bajo, sin empezar por punto.
NOMBRE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")

CACHE_PAGINA = "no-store"
# Los ficheros llevan su hash en el nombre: uno nuevo es otro nombre, asi que se pueden
# guardar para siempre.
CACHE_FICHERO = "public, max-age=31536000, immutable"

MARCA_NONCE = "<!--bms:nonce-->"
MARCA_BANDAS = "<!--bms:bandas-->"

TEXTO_DEMO = ("TESTGEGEVENS · TEST DATA — testdatabase, alles is verzonnen · test database, "
              "everything is made up")
TITULO_DEMO = "TESTGEGEVENS · "
TITULO_AISLAMIENTO = "ISOLATIE · "

# Los papeles de la instalacion nativa (aislamiento.ROLES), dichos en neerlandes e ingles.
PAPELES: dict[str, tuple[str, str]] = {
    "consola": ("console", "console"),
    "lector": ("pdf-lezer", "PDF reader"),
    "salida": ("uitgang", "exit proxy"),
    "orden": ("opdrachten", "commands"),
}


@dataclass(frozen=True)
class Fichero:
    tipo: str
    datos: bytes


@dataclass(frozen=True)
class App:
    """Lo construido, leido una vez al arrancar el servidor."""

    indice: bytes | None
    ficheros: Mapping[str, Fichero] = field(default_factory=dict)


class AppMalConstruida(ValueError):
    """El index.html no lleva las marcas donde el servidor pone el nonce y las bandas."""


def cargar(carpeta: Path = CARPETA_WEB) -> App:
    """La lista blanca: index.html y cada fichero de assets/ con un tipo conocido.

    Se hace con lo que existe, no con lo que se pide: un enlace simbolico, una
    subcarpeta, un nombre raro o una extension que no esta en TIPOS se quedan fuera.
    Sin construir (sin index.html), `indice` es None y /app lo dice.
    """
    indice = carpeta / "index.html"
    ficheros: dict[str, Fichero] = {}
    assets = carpeta / "assets"
    if assets.is_dir() and not assets.is_symlink():
        for ruta in sorted(assets.iterdir()):
            tipo = TIPOS.get(ruta.suffix.lower())
            if (tipo is None or ruta.is_symlink() or not ruta.is_file()
                    or not NOMBRE.fullmatch(ruta.name)):
                continue
            ficheros[PREFIJO_FICHEROS + ruta.name] = Fichero(tipo, ruta.read_bytes())
    leido = indice.read_bytes() if indice.is_file() and not indice.is_symlink() else None
    return App(leido, ficheros)


def nuevo_nonce() -> str:
    """Un nonce por respuesta: 144 bits, en base64url (lo que admite la CSP)."""
    return secrets.token_urlsafe(18)


def politica_contenido(nonce: str | None = None) -> str:
    """La CSP de la app. Con `nonce`, el de la pagina para los <style> de las bibliotecas."""
    estilo = f"style-src 'self' 'nonce-{nonce}'" if nonce else "style-src 'self'"
    return ("default-src 'none'; script-src 'self'; " + estilo + "; font-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'none'; require-trusted-types-for 'script'; "
            "trusted-types 'none'")


def _comunes(nonce: str | None) -> dict[str, str]:
    return {
        "Content-Security-Policy": politica_contenido(nonce),
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
    }


def cabeceras_pagina(nonce: str) -> dict[str, str]:
    """Las de index.html: no se guarda (cada respuesta lleva su nonce y sus bandas)."""
    return {**_comunes(nonce), "Cache-Control": CACHE_PAGINA}


def cabeceras_fichero() -> dict[str, str]:
    """Las de un fichero de assets/: se guarda para siempre (su nombre lleva su hash)."""
    return {**_comunes(None), "Cache-Control": CACHE_FICHERO}


def papeles_con_problemas(problemas: Sequence[str]) -> list[str]:
    """Los papeles que nombran los problemas del aislamiento ("consola: sin comprobar"),
    en el orden de PAPELES; uno que no se conoce no se copia (el texto viene de un
    fichero que se puede escribir)."""
    vistos = {texto.split(":", 1)[0].strip() for texto in problemas}
    return [papel for papel in PAPELES if papel in vistos]


# Lo que le pasa a un papel, para la pastilla de la app (components/status-pill.tsx, grupo
# aislamiento): correcto, una prueba que falla, sin comprobar o comprobado hace demasiado
# (o con una fecha que no vale).
ESTADOS_AISLAMIENTO = ("correcto", "falla", "sin_comprobar", "caducada")


def _clase_de_problema(resto: str) -> str:
    """La clase de un problema por como empieza el texto que escribe
    aislamiento.problemas_de ("sin comprobar", "FALLA (...)", "comprobado por ultima
    vez...", "la fecha de la comprobacion no vale"). Solo se mira el principio: el detalle
    de una prueba que falla sale de un fichero que se puede escribir y no se copia. Uno que
    no se reconoce es una prueba que falla (nunca pasa por correcto)."""
    if resto.startswith("sin comprobar"):
        return "sin_comprobar"
    if resto.startswith("comprobado por ultima vez") or resto.startswith("la fecha de la comprobacion"):
        return "caducada"
    return "falla"


def estados_de_papeles(problemas: Sequence[str]) -> dict[str, str]:
    """El estado de cada papel (ESTADOS_AISLAMIENTO), en el orden de PAPELES. Un problema
    que no nombra ningun papel conocido deja a todos en "falla": no se sabe cual va bien,
    y es la misma regla que la banda roja (con algun problema no hay verde)."""
    clases: dict[str, str] = {}
    for texto in problemas:
        papel, _, resto = texto.partition(":")
        papel = papel.strip()
        if papel in PAPELES and papel not in clases:
            clases[papel] = _clase_de_problema(resto.strip())
    if problemas and not clases:
        return {papel: "falla" for papel in PAPELES}
    return {papel: clases.get(papel, "correcto") for papel in PAPELES}


def texto_aislamiento(problemas: Sequence[str]) -> str:
    """La banda roja, en neerlandes e ingles."""
    papeles = papeles_con_problemas(problemas)
    nl = ", ".join(PAPELES[p][0] for p in papeles)
    en = ", ".join(PAPELES[p][1] for p in papeles)
    return ("ISOLATIE NIET GECONTROLEERD OF MISLUKT" + (f" ({nl})" if nl else "")
            + ": draai comprobar.bat en werk niet met echte gegevens tot alles groen is. · "
            "ISOLATION NOT CHECKED OR FAILED" + (f" ({en})" if en else "")
            + ": run comprobar.bat and do not work with real data until everything is green.")


def bandas(*, demo: bool, aislamiento: Sequence[str]) -> str:
    """Las bandas que van al principio del body, escapadas."""
    salida = []
    if demo:
        salida.append('<p id="datos-de-prueba" class="bms-banda bms-banda-prueba" role="alert">'
                      f"{html.escape(TEXTO_DEMO)}</p>")
    if aislamiento:
        salida.append('<p id="aislamiento" class="bms-banda bms-banda-aislamiento" role="alert">'
                      f"{html.escape(texto_aislamiento(aislamiento))}</p>")
    return "\n".join(salida)


def pagina(app: App, *, nonce: str, demo: bool = False,
           aislamiento: Sequence[str] = ()) -> bytes:
    """El index.html de esta respuesta: con su nonce, sus bandas y el titulo que lo dice.

    AppMalConstruida si el index.html no es el de frontend/ (sin sus dos marcas): mejor un
    error que una pagina sin la banda de prueba.
    """
    if app.indice is None:
        raise AppMalConstruida("la app no esta construida (falta web/index.html)")
    texto = app.indice.decode("utf-8")
    if texto.count(MARCA_NONCE) != 1 or texto.count(MARCA_BANDAS) != 1:
        raise AppMalConstruida("web/index.html no lleva las marcas del servidor")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", nonce):
        raise ValueError("nonce no valido")
    texto = texto.replace(MARCA_NONCE, f'<meta name="bms-nonce" content="{nonce}">')
    texto = texto.replace(MARCA_BANDAS, bandas(demo=demo, aislamiento=aislamiento))
    if aislamiento:
        texto = texto.replace("<title>", "<title>" + TITULO_AISLAMIENTO, 1)
    if demo:
        texto = texto.replace("<title>", "<title>" + TITULO_DEMO, 1)
    return texto.encode("utf-8")


SIN_CONSTRUIR = ("De app is niet gebouwd (src/bms_agent/web ontbreekt). Gebruik de oude console "
                 "op /consola. · The app is not built (src/bms_agent/web is missing). Use the "
                 "old console at /consola.\n").encode("utf-8")
