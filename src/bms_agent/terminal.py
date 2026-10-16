"""Texto que no manda en la terminal de quien lo lee.

Lo que se ensena en la CLI viene de documentos y ficheros de terceros: el
nombre del proveedor, el numero de factura, las notas, el concepto de un
movimiento del banco, o un mensaje de una regla que los cita. Si uno de ellos
lleva caracteres de control, la terminal los obedece: una secuencia ESC puede
subir el cursor y borrar la linea de una factura Bloqueada, escribir un "ok"
falso, cambiar el titulo de la ventana o, en las terminales que admiten OSC 52
(Windows Terminal entre ellas), escribir en el portapapeles, por ejemplo un
IBAN distinto del que la persona cree copiar. Los cambios de direccion de
Unicode (bidi) hacen que un texto se vea en otro orden del que es.

Por eso todo lo que sale por la CLI pasa por `sin_control` (SalidaSegura
envuelve stdout y stderr en cli.main), y los textos que se guardan en las
tablas tipadas tambien (campos.a_columna): se sustituyen por U+FFFD, que se
ve. El salto de linea y el tabulador se quedan. La evidencia original
(el JSON de la extraccion, el fichero importado) no se toca.
"""

from __future__ import annotations

import re
from typing import Any, TextIO

# C0 menos el tabulador y el salto de linea, DEL, C1, y los controles de direccion
# de Unicode (LRE, RLE, PDF, LRO, RLO, LRI, RLI, FSI, PDI).
_CONTROL = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f‪-‮⁦-⁩]")
VISIBLE = "�"


def sin_control(texto: str) -> str:
    """El texto con cada caracter de control (salvo salto de linea y tabulador) a la vista."""
    return _CONTROL.sub(VISIBLE, texto)


class SalidaSegura:
    """Un flujo de texto (stdout, stderr) que escribe sin caracteres de control.

    Lo demas (buffer, flush, encoding, isatty) es el del flujo que envuelve.
    """

    def __init__(self, flujo: TextIO) -> None:
        self._flujo = flujo

    def write(self, texto: str) -> int:
        return self._flujo.write(sin_control(texto))

    def writelines(self, lineas: Any) -> None:
        for linea in lineas:
            self.write(linea)

    def __getattr__(self, nombre: str) -> Any:
        return getattr(self._flujo, nombre)
