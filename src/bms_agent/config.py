"""Ajustes del extractor.

El modelo es configurable a proposito. Medir si un modelo mas barato
mantiene la precision es una de las salidas de la fase 0, y esa es una
decision con datos, no una suposicion de diseno.

El modelo por defecto cambio a claude-opus-5-5 en la misma pasada que el
esquema v2 (spec §10): cada documento que se vuelva a leer se paga una vez,
con el modelo y el esquema nuevos a la vez, y no dos. Lo ya extraido no se
vuelve a pagar al cambiar estas versiones (politica CONSERVAR de cache.py);
volver a leerlo es `bms-agent reextraer`, con presupuesto.
"""

from __future__ import annotations

import os

# Version del prompt y del esquema. Se guardan con cada extraccion para
# poder saber, meses despues, por que una factura se leyo mal.
PROMPT_VERSION = "extract/2026-10-15.1"
SCHEMA_VERSION = "2"

DEFAULT_MODEL = "claude-opus-5-5"

# Margen amplio: una factura con muchas lineas produce un JSON largo, y en
# Opus 5.5 el razonamiento, que no se puede apagar, cuenta dentro de este
# limite.
DEFAULT_MAX_TOKENS = 16000

# El esfuerzo se fija siempre, no se deja al valor por defecto del modelo:
# Opus 5.5 piensa siempre y su esfuerzo por defecto es medium, pero un valor
# implicito puede cambiar con el modelo y moveria el coste y la precision sin
# que nada lo dijera. Se cambia con BMS_EXTRACT_EFFORT y se vuelve a medir.
DEFAULT_EFFORT = "medium"
ESFUERZOS = ("low", "medium", "high", "xhigh", "max")


def model_id() -> str:
    return os.environ.get("BMS_EXTRACT_MODEL", DEFAULT_MODEL)


def max_tokens() -> int:
    return int(os.environ.get("BMS_EXTRACT_MAX_TOKENS", DEFAULT_MAX_TOKENS))


def effort() -> str:
    """El esfuerzo de la extraccion. Un valor que la API no admite se rechaza aqui, antes de pagar."""
    valor = os.environ.get("BMS_EXTRACT_EFFORT", DEFAULT_EFFORT).strip().lower()
    if valor not in ESFUERZOS:
        raise ValueError(
            f"BMS_EXTRACT_EFFORT={valor!r} no es un esfuerzo valido ({', '.join(ESFUERZOS)})"
        )
    return valor


# Paso 13: en el entorno de Docker la clave de la API no va en una variable de
# entorno ni en la imagen: es un secreto de Docker, un fichero que solo ve el
# contenedor del lector. Esta variable dice donde esta el fichero, no la clave.
VARIABLE_FICHERO_CLAVE = "BMS_CLAVE_API_FICHERO"


class ClaveNoValida(ValueError):
    """El fichero de la clave no existe, esta vacio o no parece una clave de la API."""


def _texto_de_la_clave(contenido: bytes) -> str:
    """El texto del fichero de la clave, como lo guarde Windows.

    El Bloc de notas guarda en UTF-8 con BOM en versiones viejas de Windows 10,
    y en UTF-16 con "Unicode"; Windows PowerShell 5.1 escribe UTF-16 con `>` o
    Out-File. El BOM dice cual es; sin BOM, UTF-8. str.strip() no quita el BOM
    (U+FEFF), por eso no basta con leer en UTF-8.
    """
    if contenido.startswith((b"\xff\xfe", b"\xfe\xff")):
        return contenido.decode("utf-16")
    return contenido.decode("utf-8-sig")


def parece_una_clave(clave: str) -> bool:
    """Si el texto tiene la forma de una clave de la API: sk-ant- y nada de espacios."""
    return bool(clave) and clave.startswith("sk-ant-") and not any(c.isspace() for c in clave)


def clave_api() -> str | None:
    """La clave de la API para el cliente de Anthropic, o None para que la busque el (en
    ANTHROPIC_API_KEY, como hasta ahora).

    Si BMS_CLAVE_API_FICHERO dice un fichero, la clave es su contenido sin
    espacios. Un fichero que falta o no tiene una clave se dice aqui, antes de
    ninguna llamada, y el mensaje nunca lleva la clave ni un trozo de ella.

    En la instalacion nativa de Windows (paso 14) la clave esta cifrada con DPAPI y
    solo la descifra el lector (nativo.clave_del_lector); alli no se acepta un
    fichero de texto ni se deja al SDK buscarla en una variable: no habria clave en
    claro en ningun sitio, y con una variable la habria.
    """
    from . import nativo

    instalacion = nativo.instalacion_actual()
    ruta = os.environ.get(VARIABLE_FICHERO_CLAVE)
    if instalacion is not None:
        if ruta:
            raise ClaveNoValida("en la instalacion nativa la clave va cifrada (clave.bat), no en "
                                f"un fichero: quita la variable {VARIABLE_FICHERO_CLAVE}")
        return nativo.clave_del_lector(instalacion)
    if not ruta:
        return None
    try:
        with open(ruta, "rb") as fichero:
            clave = _texto_de_la_clave(fichero.read()).strip()
    except OSError as exc:
        raise ClaveNoValida(f"no se puede leer el fichero de la clave {ruta}: "
                            f"{exc.strerror or exc}") from None
    except UnicodeDecodeError:
        raise ClaveNoValida(f"el fichero de la clave {ruta} no es texto: guardalo como texto "
                            "UTF-8 (en el Bloc de notas, Guardar como, Codificacion UTF-8)"
                            ) from None
    if not clave:
        raise ClaveNoValida(f"el fichero de la clave {ruta} esta vacio")
    if not parece_una_clave(clave):
        raise ClaveNoValida(f"lo que hay en {ruta} no parece una clave de la API de Anthropic "
                            "(empieza por sk-ant- y va en una sola linea)")
    return clave
