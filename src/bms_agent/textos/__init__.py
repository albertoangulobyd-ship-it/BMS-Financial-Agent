"""Los textos de la app local en neerlandes y en ingles (paso 15).

La app de la oficina (frontend/) no ensena nunca los textos en espanol que
devuelve la API (`titulo`, `detalle`, `etiqueta`, `fuente_texto`, `motivos`):
esos se quedan para la CLI y la auditoria. Lo que ensena sale de dos
catalogos, nl.json y en.json, con las mismas claves: de cada regla, su
titulo, lo que significa, lo que hay que hacer y una plantilla para su
detalle; de cada categoria, campo, fuente, estado, prioridad, accion, rol y
permiso, su nombre.

El detalle de un hallazgo no se traduce del espanol: se escribe otra vez
desde sus `valores` (los mismos enteros y textos que la regla comparo y que
van en su huella), con una plantilla. Asi el texto en neerlandes dice lo que
dicen los datos, no lo que dijo una frase.

El lenguaje de las plantillas esta en LEEME.md. Este modulo es la referencia:
la app lo implementa otra vez en TypeScript y se prueba contra los mismos
casos (casos.json, que escribe scripts/generar_casos_textos.py con las reglas
de verdad). Todo es puro y sin floats: un importe se escribe con aritmetica
de enteros, como en el resto del sistema.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

IDIOMAS = ("nl", "en")
CARPETA = Path(__file__).resolve().parent

# Lo que se pinta donde no hay nada: la raya. Un hueco en blanco se leeria como
# un texto cortado; un cero, como un importe.
VACIO = "—"

# Los formatos escriben un valor; las transformaciones lo cambian antes (van delante:
# {lineas_cent|suma|dinero}).
FORMATOS = ("texto", "dinero", "tarifa", "horas", "pct", "fecha", "trimestre", "iban",
            "codigo")
TRANSFORMACIONES = ("cuenta", "suma", "abs")
FILTROS = FORMATOS + TRANSFORMACIONES

# {{ y }} son llaves literales; un marcador es {ruta} o {ruta|filtro}. La ruta
# son claves separadas por puntos; un segmento de cifras indexa una lista.
_TROZO = re.compile(r"\{\{|\}\}|\{([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*)((?:\|[a-z]+)*)\}")
_NUMERO = re.compile(r"(-?)(\d+)(?:/(\d+))?")
_FECHA = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_IBAN = re.compile(r"[A-Za-z0-9]+")
_TRIMESTRE = re.compile(r"(\d{4})-T([1-4])")
_FALTA = object()


@dataclass(frozen=True)
class Pintado:
    """Un texto ya escrito y las rutas que la plantilla pedia y los valores no traian.

    `faltan` no es un error para quien lee (ve una raya), pero si para los
    tests: una plantilla que pide una clave que su regla no da esta mal.
    """

    texto: str
    faltan: tuple[str, ...] = ()


# ------------------------------------------------------------ catalogos

@lru_cache(maxsize=len(IDIOMAS))
def catalogo(idioma: str) -> dict[str, Any]:
    """El catalogo de un idioma (nl o en), leido una vez."""
    if idioma not in IDIOMAS:
        raise ValueError(f"idioma {idioma!r}: solo {', '.join(IDIOMAS)}")
    return json.loads((CARPETA / f"{idioma}.json").read_text(encoding="utf-8"))


def casos() -> dict[str, Any]:
    """Los casos de referencia del renderizador (casos.json)."""
    return json.loads((CARPETA / "casos.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------ numeros

def _miles(cifras: str) -> str:
    """'1234567' es '1.234.567': el punto de millares de la empresa."""
    grupos = []
    while len(cifras) > 3:
        grupos.insert(0, cifras[-3:])
        cifras = cifras[:-3]
    grupos.insert(0, cifras)
    return ".".join(grupos)


def _escala(valor: int, escala: int, minimo: int) -> str:
    """Un entero en unidades de 10**-escala, con coma decimal y sin ceros de mas.

    Quedan al menos `minimo` decimales: un importe siempre lleva dos (12,50),
    unas horas ninguno si son enteras (8).
    """
    signo = "-" if valor < 0 else ""
    entero, resto = divmod(abs(valor), 10 ** escala)
    decimales = str(resto).zfill(escala).rstrip("0").ljust(minimo, "0") if escala else ""
    return signo + _miles(str(entero)) + ("," + decimales if decimales else "")


def _entero_de(valor: Any) -> int | None:
    """Un entero, o un texto que lo es ('181350', o una fraccion '181351/2' redondeada a la
    unidad, la mitad lejos de cero). None si no es un numero: un bool tampoco lo es."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if not isinstance(valor, str):
        return None
    partes = _NUMERO.fullmatch(valor.strip())
    if partes is None:
        return None
    signo, numerador, denominador = partes.groups()
    numerador_, divisor = int(numerador), int(denominador or 1)
    if divisor == 0:
        return None
    cociente, resto = divmod(numerador_, divisor)
    if 2 * resto >= divisor and resto:
        cociente += 1
    return -cociente if signo else cociente


def dinero(cent: int) -> str:
    """Centimos como se lee un importe en la empresa: € 1.234,56 (y € -1.234,56).

    Entre el euro y la cifra va un espacio que no se parte (U+00A0): sin el, una frase
    larga dejaba el euro al final de una linea y el importe en la siguiente."""
    return "€\u00a0" + _escala(cent, 2, 2)


def tarifa(e4: int) -> str:
    """Diezmilesimas de euro: € 42,50, o € 42,505 si la tarifa lleva mas decimales."""
    return "€\u00a0" + _escala(e4, 4, 2)


def horas(mil: int) -> str:
    """Milesimas (de hora o de cualquier cantidad): 37,5; 8; 1.234,25."""
    return _escala(mil, 3, 0)


def pct(pb: int) -> str:
    """Puntos basicos como porcentaje: 2100 es 21%, 8599 es 85,99%."""
    return _escala(pb, 2, 0) + "%"


_NUMERICOS = {"dinero": dinero, "tarifa": tarifa, "horas": horas, "pct": pct}


def fecha(iso: str) -> str:
    """'2026-10-16' (o un instante que empieza asi) es 16-10-2026; otra cosa, tal cual."""
    partes = _FECHA.match(iso)
    if partes is None:
        return iso
    ano, mes, dia = partes.groups()
    return f"{dia}-{mes}-{ano}"


def trimestre(etiqueta: str) -> str:
    """'2026-T3' (la etiqueta del BTW en la API, en espanol) es 'Q3 2026', que se lee igual en
    neerlandes y en ingles; otra cosa, tal cual."""
    partes = _TRIMESTRE.fullmatch(etiqueta)
    if partes is None:
        return etiqueta
    ano, numero = partes.groups()
    return f"Q{numero} {ano}"


def iban(texto: str) -> str:
    """Un IBAN en grupos de cuatro: NL91 ABNA 0417 1643 00.

    Uno ya enmascarado (NL..4300, lo que sale hacia otro origen) se deja tal
    cual: agruparlo inventaria cifras que no se ven.
    """
    compacto = "".join(texto.split())
    if not _IBAN.fullmatch(compacto):
        return texto
    compacto = compacto.upper()
    return " ".join(compacto[i:i + 4] for i in range(0, len(compacto), 4))


# ------------------------------------------------------------ plantillas

def marcadores(plantilla: str) -> list[tuple[str, tuple[str, ...]]]:
    """Las (ruta, filtros) de una plantilla, en orden. Sin filtro, es ('texto',)."""
    return [(m.group(1), _filtros(m.group(2))) for m in _TROZO.finditer(plantilla)
            if m.group(1) is not None]


def _filtros(trozo: str | None) -> tuple[str, ...]:
    filtros = tuple(f for f in (trozo or "").split("|") if f)
    return filtros or ("texto",)


def _buscar(valores: Any, ruta: str) -> Any:
    """El valor de una ruta ('periodos.0.1'), o _FALTA si no esta."""
    actual = valores
    for segmento in ruta.split("."):
        if isinstance(actual, Mapping) and segmento in actual:
            actual = actual[segmento]
        elif (isinstance(actual, Sequence) and not isinstance(actual, str)
              and segmento.isdigit() and int(segmento) < len(actual)):
            actual = actual[int(segmento)]
        else:
            return _FALTA
    return actual


def _transformar(valor: Any, filtro: str) -> Any:
    """cuenta, suma y abs: cambian el valor antes de escribirlo (None si no se puede)."""
    if filtro == "cuenta":
        if isinstance(valor, (Mapping, list, tuple)):
            return len(valor)
        return _entero_de(valor)
    if filtro == "suma":
        if not isinstance(valor, (list, tuple)):
            return _entero_de(valor)
        numeros = [_entero_de(v) for v in valor]
        return None if any(n is None for n in numeros) else sum(numeros)
    if isinstance(valor, (list, tuple)):
        return [_transformar(v, filtro) for v in valor]
    numero = _entero_de(valor)
    return None if numero is None else abs(numero)


def _uno(valor: Any, formato: str, idioma: str, ruta: str, faltan: list[str]) -> str:
    """Un valor que no es una lista, con su formato."""
    if valor is None:
        return VACIO
    if isinstance(valor, Mapping):
        faltan.append(ruta)
        return VACIO
    if formato in _NUMERICOS:
        numero = _entero_de(valor)
        if numero is not None:
            return _NUMERICOS[formato](numero)
    elif formato == "fecha" and isinstance(valor, str):
        return fecha(valor)
    elif formato == "trimestre" and isinstance(valor, str):
        return trimestre(valor)
    elif formato == "iban" and isinstance(valor, str):
        return iban(valor)
    elif formato == "codigo" and isinstance(valor, str):
        codigos = catalogo(idioma).get("codigos", {})
        if valor in codigos:
            return codigos[valor]
        faltan.append(f"codigo:{valor}")
        return valor
    if isinstance(valor, bool):
        return catalogo(idioma)["comun"]["si" if valor else "no"]
    return str(valor)


def _pintar(valor: Any, filtros: tuple[str, ...], idioma: str, ruta: str,
            faltan: list[str]) -> str:
    """Las transformaciones en orden y despues el formato (el ultimo filtro, o texto)."""
    *antes, ultimo = filtros
    if ultimo in TRANSFORMACIONES:
        antes, ultimo = [*antes, ultimo], "texto"
    malos = [f for f in antes if f not in TRANSFORMACIONES]
    if malos or ultimo not in FORMATOS:
        faltan.extend(f"filtro:{f}" for f in (*malos, ultimo) if f not in FILTROS
                      or f in malos)
        return VACIO
    for filtro in antes:
        valor = _transformar(valor, filtro)
    if isinstance(valor, (list, tuple)):
        if not valor:
            return VACIO
        return ", ".join(_uno(v, ultimo, idioma, ruta, faltan) for v in valor)
    return _uno(valor, ultimo, idioma, ruta, faltan)


def pintar(plantilla: str, valores: Mapping[str, Any] | None, idioma: str) -> Pintado:
    """La plantilla con cada marcador sustituido, y lo que faltaba."""
    if idioma not in IDIOMAS:
        raise ValueError(f"idioma {idioma!r}: solo {', '.join(IDIOMAS)}")
    valores = valores or {}
    faltan: list[str] = []

    def sustituir(m: re.Match[str]) -> str:
        trozo = m.group(0)
        if trozo == "{{":
            return "{"
        if trozo == "}}":
            return "}"
        ruta = m.group(1)
        valor = _buscar(valores, ruta)
        if valor is _FALTA:
            faltan.append(ruta)
            return VACIO
        return _pintar(valor, _filtros(m.group(2)), idioma, ruta, faltan)

    return Pintado(_TROZO.sub(sustituir, plantilla), tuple(faltan))


def renderizar(plantilla: str, valores: Mapping[str, Any] | None, idioma: str) -> str:
    """Solo el texto (lo que falta sale como una raya)."""
    return pintar(plantilla, valores, idioma).texto


# ------------------------------------------------------------ variantes

def _texto_crudo(valor: Any) -> str:
    """Como se compara un valor en una condicion clave=valor: true/false, cifras o el texto."""
    if isinstance(valor, bool):
        return "true" if valor else "false"
    return str(valor)


def cumple(condicion: str, valores: Mapping[str, Any]) -> bool:
    """Una condicion de una variante: 'ruta' (esta y no es null ni una lista vacia),
    '!ruta' (lo contrario) o 'ruta=valor' (su texto crudo es ese)."""
    if condicion.startswith("!"):
        return not cumple(condicion[1:], valores)
    ruta, igual, esperado = condicion.partition("=")
    valor = _buscar(valores, ruta)
    if valor is _FALTA or valor is None or (isinstance(valor, (list, tuple)) and not valor):
        return False
    return _texto_crudo(valor) == esperado if igual else True


def _vale(trozo: Mapping[str, Any], valores: Mapping[str, Any]) -> bool:
    return all(cumple(c, valores) for c in trozo.get("cuando", ()))


def elegir(variantes: Sequence[Mapping[str, Any]],
           valores: Mapping[str, Any] | None) -> tuple[int, list[str]]:
    """La primera variante que vale, con su posicion y las plantillas que escribe.

    Una variante vale si se cumplen todas sus condiciones (`cuando`). Una con
    `partes` escribe cada parte que vale, en orden y separadas por un
    espacio (A2: el btw-id, el KvK y el nombre, los que difieran); si no vale
    ninguna parte, la variante no vale. La ultima es un `texto` sin
    condiciones (lo exige el test del catalogo), asi que siempre hay una.
    """
    valores = valores or {}
    for i, variante in enumerate(variantes):
        if not _vale(variante, valores):
            continue
        if "partes" not in variante:
            return i, [variante["texto"]]
        partes = [p["texto"] for p in variante["partes"] if _vale(p, valores)]
        if partes:
            return i, partes
    raise LookupError("ninguna variante vale y la ultima deberia valer siempre")


def detalle(regla: str, resultado: str, valores: Mapping[str, Any] | None,
            idioma: str) -> Pintado:
    """El detalle de un resultado de una regla (fallo o sin_datos), en un idioma.

    Una regla sin plantilla para ese resultado da su significado: nunca el
    espanol de la API.
    """
    texto = catalogo(idioma)["reglas"][regla]
    variantes = texto["detalle"].get(resultado)
    if not variantes:
        return Pintado(texto["significa"])
    _i, plantillas = elegir(variantes, valores)
    pintados = [pintar(p, valores, idioma) for p in plantillas]
    return Pintado(" ".join(p.texto for p in pintados),
                   tuple(f for p in pintados for f in p.faltan))
