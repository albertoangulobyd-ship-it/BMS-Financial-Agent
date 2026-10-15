"""Lectura de extracciones de cualquier version del esquema con la forma de la ultima.

Una extraccion guardada no se reescribe nunca: es la evidencia de lo que el
modelo leyo. Cuando el esquema crece (v2 anade el tipo de documento, las
referencias, el receptor, el desglose de IVA...), las extracciones v1 se
leen "subidas" a la forma v2 al vuelo: las claves nuevas aparecen con valor
vacio y quedan apuntadas como "no solicitado en v1".

La diferencia importa. Un campo que el documento no trae es un hallazgo
(Q1: falta el receptor); un campo que nadie le pidio al modelo no dice nada
del documento, y una regla que lo necesita da sin_datos, nunca un fallo ni
un ok. Leerlo como "no esta en el documento" llenaria el historico de
faltas que no son.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

NO_SOLICITADO_V1 = "no solicitado en v1"

# Lo que el esquema v2 pide y el v1 no (spec §10). Las rutas de linea van
# como "lines[].campo".
CAMPOS_V2_CABECERA: tuple[str, ...] = (
    "document_type", "related_invoices", "currency_raw", "supplier_contact_person",
    "recipient_name", "recipient_vat_number", "recipient_contact_person", "references",
    "payment_terms_raw", "vat_breakdown",
)
CAMPOS_V2_LINEA: tuple[str, ...] = (
    "employee_name", "work_date", "order_reference_raw", "rate_type_raw", "vat_rate_raw",
)

VERSIONES = ("1", "2")


@dataclass(frozen=True)
class ExtraccionLeida:
    """Una extraccion con la forma v2, sin tocar la guardada."""

    datos: dict[str, Any]
    schema_version: str
    no_solicitados: frozenset[str]

    def solicitado(self, ruta: str) -> bool:
        """Si se le pidio al modelo. Una ruta de linea va como 'lines[].work_date'."""
        return ruta not in self.no_solicitados

    def estado(self, ruta: str) -> str:
        """'no solicitado en v1', 'vacio' o 'presente', para una clave de cabecera."""
        if not self.solicitado(ruta):
            return NO_SOLICITADO_V1
        valor = self.datos.get(ruta)
        return "vacio" if valor in (None, "", []) else "presente"


def no_solicitados(schema_version: str) -> frozenset[str]:
    """Las rutas que una version no pidio al modelo."""
    if str(schema_version) == "1":
        return frozenset(CAMPOS_V2_CABECERA) | frozenset(f"lines[].{c}" for c in CAMPOS_V2_LINEA)
    if str(schema_version) == "2":
        return frozenset()
    raise ValueError(f"no se sabe leer el esquema de extraccion {schema_version!r}")


def leer(extraccion: dict[str, Any], schema_version: str) -> ExtraccionLeida:
    """La extraccion (el objeto 'extraction' del registro) con la forma v2.

    Devuelve una copia: el registro guardado no cambia. Una clave que v1 no
    pidio queda a None (tambien las listas: una lista vacia diria "se pidio
    y no habia ninguna").
    """
    version = str(schema_version)
    faltan = no_solicitados(version)
    datos = copy.deepcopy(extraccion if isinstance(extraccion, dict) else {})
    if version == "1":
        for clave in CAMPOS_V2_CABECERA:
            datos.setdefault(clave, None)
        lineas = datos.get("lines")
        if isinstance(lineas, list):
            for linea in lineas:
                if isinstance(linea, dict):
                    for clave in CAMPOS_V2_LINEA:
                        linea.setdefault(clave, None)
    return ExtraccionLeida(datos=datos, schema_version=version, no_solicitados=faltan)


def leer_registro(registro: dict[str, Any]) -> ExtraccionLeida:
    """Lo mismo, desde el registro entero (el JSON de out/ o de la tabla extraccion)."""
    return leer(registro.get("extraction") or {}, str(registro.get("schema_version")))
