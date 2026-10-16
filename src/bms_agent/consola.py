"""La consola interna minima: lo que sirve serve.py en /consola.

Tres ficheros estaticos (pagina, script y estilo, en consola_assets.py) y
nada mas: la pagina no lleva ningun dato. Lo pide despues a /api/v2 con el
token de la persona, y lo pinta como texto.

Las cabeceras son las que hacen de la consola algo que otra web no puede
usar: no se deja meter en un marco (un clic robado no puede marcar nada como
revisado), solo ejecuta el script propio (un `<script>` que llegue dentro de
un dato no corre aunque alguien lo pintase mal) y solo habla con el propio
servidor.

Con la base de prueba (paso 13) la pagina lleva arriba una banda fija de
DATOS DE PRUEBA, puesta por el servidor y no por el script: se ve aunque el
script no cargue, y ningun dato la puede quitar.

En la instalacion nativa de Windows (paso 14) lleva ademas una banda roja si la
comprobacion de aislamiento de algun papel falla, falta o es vieja. La pone el
servidor igual que la de prueba. Su texto sale de datos/aislamiento.json, un
fichero que se puede escribir: va escapado.
"""

from __future__ import annotations

import html
from collections.abc import Sequence

from .consola_assets import ESTILO, PAGINA, SCRIPT

POLITICA_CONTENIDO = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)

FICHEROS: dict[str, tuple[str, str]] = {
    "/consola": ("text/html; charset=utf-8", PAGINA),
    "/consola.js": ("text/javascript; charset=utf-8", SCRIPT),
    "/consola.css": ("text/css; charset=utf-8", ESTILO),
}


def cabeceras() -> dict[str, str]:
    """Las cabeceras de seguridad de cada fichero de la consola."""
    return {
        "Content-Security-Policy": POLITICA_CONTENIDO,
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
    }


TEXTO_DEMO = ("DATOS DE PRUEBA: esta es la base de prueba (demo.sqlite3). Todo lo que se ve "
              "es ficticio; nada de aquí es real ni pasa a la base de verdad.")
BANDA_DEMO = f'<div id="datos-de-prueba" class="datos-de-prueba" role="alert">{TEXTO_DEMO}</div>'


def texto_aislamiento(problemas: Sequence[str]) -> str:
    """Lo que dice la banda roja del aislamiento."""
    return ("AISLAMIENTO SIN COMPROBAR O CON FALLOS: " + "; ".join(problemas) + ". Ejecuta "
            "comprobar.bat (en el escritorio, «BMS Finanzas - Comprobar aislamiento») y no "
            "trabajes con datos de verdad hasta que salga todo en verde.")


def banda_aislamiento(problemas: Sequence[str]) -> str:
    return (f'<div id="aislamiento" class="aislamiento-falla" role="alert">'
            f'{html.escape(texto_aislamiento(problemas))}</div>')


def fichero(ruta: str, *, demo: bool = False, aislamiento: Sequence[str] = ()
            ) -> tuple[str, bytes] | None:
    """El tipo y el contenido de un fichero de la consola, o None si la ruta no es suya.

    Con `demo`, la pagina lleva la banda de DATOS DE PRUEBA justo despues de
    abrir el body y el titulo lo dice tambien (se ve en la pestana). Con
    `aislamiento` (lo que falla), la banda roja del aislamiento, detras de la de
    prueba si la hay.
    """
    encontrado = FICHEROS.get(ruta)
    if encontrado is None:
        return None
    tipo, texto = encontrado
    if ruta == "/consola":
        bandas = ([BANDA_DEMO] if demo else []) + (
            [banda_aislamiento(aislamiento)] if aislamiento else [])
        if bandas:
            texto = texto.replace("<body>\n", "<body>\n" + "\n".join(bandas) + "\n", 1)
        if aislamiento:
            texto = texto.replace("<title>", "<title>SIN AISLAMIENTO · ", 1)
        if demo:
            texto = texto.replace("<title>", "<title>DATOS DE PRUEBA · ", 1)
    return tipo, texto.encode("utf-8")
