"""La linea de comandos en castellano: el uso, la ayuda y los errores de argparse.

argparse escribe en ingles lo suyo ("usage:", "show this help message and
exit", "the following arguments are required"), y quien usa la CLI lee lo
demas en castellano: un error a medias en otro idioma es el que no se
entiende. Sin tocar el modulo argparse (lo usan otros, pytest entre ellos):
un ArgumentParser propio pone sus textos, y los errores que argparse ya ha
escrito se traducen por su forma antes de ensenarlos.

Los subcomandos heredan la clase: add_subparsers crea los suyos con
type(self).
"""

from __future__ import annotations

import argparse
import functools
import re
import sys
from typing import Any, NoReturn

USO = "uso: "
AYUDA = "muestra esta ayuda y sale"

# Los nombres de tipo que argparse ensena en "invalid int value".
_TIPOS = {"int": "un numero entero", "float": "un numero", "date": "una fecha"}

# Los mensajes de argparse (3.11). "argument X: ..." envuelve a cualquiera de
# ellos: `traducir` lo quita antes y traduce lo de dentro.
_TRADUCCIONES: tuple[tuple[re.Pattern[str], Any], ...] = (
    (re.compile(r"the following arguments are required: (.+)"),
     lambda m: f"faltan argumentos: {m[1]}"),
    (re.compile(r"one of the arguments (.+) is required"),
     lambda m: f"hace falta uno de estos argumentos: {m[1]}"),
    (re.compile(r"invalid choice: (.+?) \(choose from (.+)\)"),
     lambda m: f"{m[1]} no es ninguna de las posibles ({m[2]})"),
    (re.compile(r"invalid (\w+) value: (.+)"),
     lambda m: f"{m[2]} no es {_TIPOS.get(m[1], 'un valor valido (' + m[1] + ')')}"),
    (re.compile(r"unrecognized arguments: (.+)"),
     lambda m: f"no se conocen estos argumentos: {m[1]}"),
    (re.compile(r"expected one argument"), lambda m: "le falta su valor"),
    (re.compile(r"expected at most one argument"), lambda m: "lleva un valor como mucho"),
    (re.compile(r"expected at least one argument"), lambda m: "lleva un valor al menos"),
    (re.compile(r"expected (\d+) arguments?"), lambda m: f"lleva {m[1]} valores"),
    (re.compile(r"not allowed with argument (.+)"),
     lambda m: f"no se puede usar junto con {m[1]}"),
    (re.compile(r"ambiguous option: (.+) could match (.+)"),
     lambda m: f"{m[1]} puede ser {m[2]}: escribelo entero"),
    (re.compile(r"ignored explicit argument (.+)"),
     lambda m: f"no lleva valor y se le ha dado {m[1]}"),
)
_ARGUMENTO = re.compile(r"argument (.+?): (.+)", re.DOTALL)


def traducir(mensaje: str) -> str:
    """Un error de argparse en castellano; el que no se reconoce se queda como estaba."""
    argumento = _ARGUMENTO.fullmatch(mensaje)
    if argumento is not None:
        return f"el argumento {argumento[1]}: {traducir(argumento[2])}"
    for patron, texto in _TRADUCCIONES:
        encontrado = patron.fullmatch(mensaje)
        if encontrado is not None:
            return texto(encontrado)
    return mensaje


@functools.lru_cache(maxsize=None)
def _en_castellano(formatter: type[argparse.HelpFormatter]) -> type[argparse.HelpFormatter]:
    """El formatter que se pidio, con "uso: " en vez de "usage: "."""

    class Castellano(formatter):  # type: ignore[valid-type, misc]
        def add_usage(self, usage: Any, actions: Any, groups: Any,
                      prefix: str | None = None) -> None:
            super().add_usage(usage, actions, groups, USO if prefix is None else prefix)

    Castellano.__name__ = f"{formatter.__name__}EnCastellano"
    return Castellano


class Parser(argparse.ArgumentParser):
    """Un ArgumentParser que ensena su uso, su ayuda y sus errores en castellano."""

    def __init__(self, *args: Any, formatter_class: type[argparse.HelpFormatter] =
                 argparse.HelpFormatter, add_help: bool = True, **kwargs: Any) -> None:
        super().__init__(*args, formatter_class=_en_castellano(formatter_class),
                         add_help=False, **kwargs)
        self._positionals.title = "argumentos"
        self._optionals.title = "opciones"
        if add_help:
            prefijo = self.prefix_chars[0]
            self.add_argument(prefijo + "h", prefijo * 2 + "help", action="help",
                              default=argparse.SUPPRESS, help=AYUDA)

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {traducir(message)}\n")
