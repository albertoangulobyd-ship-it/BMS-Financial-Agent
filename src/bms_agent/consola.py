"""La consola interna minima: lo que sirve serve.py en /consola.

Tres ficheros estaticos (pagina, script y estilo, en consola_assets.py) y
nada mas: la pagina no lleva ningun dato. Lo pide despues a /api/v2 con el
token de la persona, y lo pinta como texto.

Las cabeceras son las que hacen de la consola algo que otra web no puede
usar: no se deja meter en un marco (un clic robado no puede marcar nada como
revisado), solo ejecuta el script propio (un `<script>` que llegue dentro de
un dato no corre aunque alguien lo pintase mal) y solo habla con el propio
servidor.
"""

from __future__ import annotations

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


def fichero(ruta: str) -> tuple[str, bytes] | None:
    """El tipo y el contenido de un fichero de la consola, o None si la ruta no es suya."""
    encontrado = FICHEROS.get(ruta)
    if encontrado is None:
        return None
    tipo, texto = encontrado
    return tipo, texto.encode("utf-8")
