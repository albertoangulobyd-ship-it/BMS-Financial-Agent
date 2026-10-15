"""El catalogo: cada regla del motor con su metadato, tal como lo fija spec.md §7.

Solo estan las reglas que ya se evaluan. Las demas del §7 llegan con su paso
(A y F2-F10 con el maestro, K con el banco, P con las ordenes de compra, G y
V con el planning...), y entran aqui cuando su evaluacion existe: una regla
listada que no se evalua daria por bueno lo que nadie ha mirado.

De cada regla: que hace un fallo (B, R o A, y si cambia en las facturas de
venta), si se puede anular, si es pegajosa (su hallazgo no se cierra solo),
si anularla pide segunda firma, que aporta a la prioridad (§8) y que calidad
de dato marca. El orden es el del §7 y es el orden de los resultados.

`NO_ANULABLES` es la lista de la decision 12 (§3): ninguna politica, marca
ni catalogo la puede relajar, y la base la repite en el disparador
anulacion_solo_anulables.
"""

from __future__ import annotations

import hashlib
import json

from ..dominio import Calidad, EntradaPrioridad
from . import aritmetica, bancaria, calidad, iva, planning, unicidad
from .base import B, LEE_POR_FACTURA, R, Regla, por_factura

_P = EntradaPrioridad
_C = Calidad


def _de_factura(id_: str, funcion, lee: frozenset[str], **metadatos) -> Regla:
    return Regla(id=id_, evaluar=por_factura(id_, funcion), lee=lee | LEE_POR_FACTURA,
                 **metadatos)


CATALOGO: tuple[Regla, ...] = (
    # Datos e identidad
    _de_factura("Q1", calidad.q1, calidad.LEE_Q1,
                titulo="Campos obligatorios", familia="calidad", severidad=R,
                calidad=_C.FALTANTE.value,
                descripcion="Falta un campo obligatorio para el sentido de la factura: número, "
                            "contraparte, fecha, periodo, base, IVA o régimen, total. Bloquea "
                            "si falta el número, el total o la contraparte."),
    _de_factura("X1", calidad.x1, calidad.LEE_X1,
                titulo="Moneda", familia="calidad", severidad=B, pegajosa=True,
                calidad=_C.ANOMALIA.value,
                descripcion="La factura no está en euros: queda fuera de todos los totales."),
    # Duplicados
    Regla("B2", "Número de factura repetido", "unicidad", unicidad.b2, unicidad.LEE_B2,
          solo_texto=unicidad.SOLO_TEXTO,
          severidad=B, anulable=True, pegajosa=True, segunda_firma=True,
          entrada_prioridad=_P.DUPLICADO_EXACTO.value, calidad=_C.ANOMALIA.value,
          descripcion="La misma contraparte con el mismo número normalizado, sin fusionar "
                      "ni enlazar. Se cierra fusionando o enlazando."),
    Regla("B3", "Posible duplicado por contenido", "unicidad", unicidad.b3, unicidad.LEE_B3,
          solo_texto=unicidad.SOLO_TEXTO,
          severidad=R, anulable=True, pegajosa=True, entrada_prioridad=_P.DUPLICADO.value,
          calidad=_C.ANOMALIA.value,
          descripcion="Misma contraparte, el mismo total (0,01), como mucho 14 días entre "
                      "las dos, periodos compatibles y número distinto."),
    Regla("B4", "Periodo facturado dos veces", "unicidad", unicidad.b4, unicidad.LEE_B4,
          solo_texto=unicidad.SOLO_TEXTO,
          severidad=R, anulable=True, pegajosa=True, entrada_prioridad=_P.DUPLICADO.value,
          calidad=_C.ANOMALIA.value,
          descripcion="Periodos de cobro que se pisan, por Objeto cuando las líneas lo "
                      "nombran; sin las relaciones confirmadas ni los abonos."),
    # Aritmetica e IVA
    _de_factura("D1", aritmetica.d1, aritmetica.LEE_D1,
                titulo="Desglose", familia="aritmetica", severidad=B, severidad_saliente=R,
                calidad=_C.FALTANTE.value,
                descripcion="El desglose está: líneas con cantidad, tarifa e importe, base, "
                            "total y, si se repercute IVA, tipo y cuota."),
    _de_factura("D2", aritmetica.d2, aritmetica.LEE_D2,
                titulo="Suma de líneas", familia="aritmetica", severidad=B, severidad_saliente=R,
                calidad=_C.DISCREPANCIA.value,
                descripcion="La suma de las líneas es la base (0,01 por línea más 0,02)."),
    _de_factura("D2b", aritmetica.d2b, aritmetica.LEE_D2B,
                titulo="Aritmética de línea", familia="aritmetica", severidad=B,
                severidad_saliente=R, anulable=True, calidad=_C.DISCREPANCIA.value,
                descripcion="Cantidad por tarifa es el importe de cada línea (0,01)."),
    _de_factura("D3", iva.d3, iva.LEE_D3,
                titulo="Cuota de IVA", familia="iva", severidad=B,
                entrada_prioridad=_P.IVA_DURA.value, calidad=_C.DISCREPANCIA.value,
                descripcion="La base por el tipo es la cuota, tipo a tipo (0,02)."),
    _de_factura("D4", aritmetica.d4, aritmetica.LEE_D4,
                titulo="Total", familia="aritmetica", severidad=B,
                calidad=_C.DISCREPANCIA.value,
                descripcion="La base más la cuota es el total (0,02)."),
    _de_factura("E3", iva.e3, iva.LEE_E3,
                titulo="IVA con KOR", familia="iva", severidad=B,
                entrada_prioridad=_P.IVA_DURA.value, calidad=_C.DISCREPANCIA.value,
                descripcion="Con KOR la factura no repercute IVA."),
    _de_factura("E4", iva.e4, iva.LEE_E4,
                titulo="IVA trasladado", familia="iva", severidad=B,
                entrada_prioridad=_P.IVA_DURA.value, calidad=_C.DISCREPANCIA.value,
                descripcion="Con IVA trasladado no hay cuota y figura el btw-id del receptor."),
    # Datos de pago
    _de_factura("F1", bancaria.f1, bancaria.LEE_F1,
                titulo="IBAN", familia="bancaria", severidad=B, pegajosa=True,
                entrada_prioridad=_P.IBAN.value, calidad=_C.DISCREPANCIA.value,
                descripcion="El IBAN impreso pasa el dígito de control módulo 97."),
    # Planning
    Regla("G3", "Tarifa distinta por el mismo trabajo", "planning", planning.g3,
          planning.LEE_G3, solo_texto=planning.SOLO_TEXTO_G3, severidad=R, anulable=True, entrada_prioridad=_P.PLANNING.value,
          calidad=_C.ANOMALIA.value,
          descripcion="Sin tarifa pactada ni planning, contra el histórico: la misma "
                      "contraparte cobra otra tarifa por el mismo trabajo en el mismo Objeto."),
)

POR_ID: dict[str, Regla] = {regla.id: regla for regla in CATALOGO}

# Decision 12 (§3): lo que no se anula nunca. Las D, solo en las entrantes.
NO_ANULABLES = frozenset({"X1", "E3", "E4", "K2", "K4", "K6", "R2", "R3"})
NO_ANULABLES_ENTRANTES = frozenset({"D2", "D3", "D4", "D6"})
FAMILIAS_NO_ANULABLES = ("F",)


def nunca_anulable(regla_id: str, sentido: str | None) -> bool:
    """La lista dura de la decision 12, que ningun catalogo ni politica relaja."""
    if regla_id in NO_ANULABLES or regla_id.startswith(FAMILIAS_NO_ANULABLES):
        return True
    return regla_id in NO_ANULABLES_ENTRANTES and sentido != "saliente"


def regla(regla_id: str) -> Regla:
    try:
        return POR_ID[regla_id]
    except KeyError:
        raise KeyError(f"{regla_id} no es una regla del catalogo") from None


def sha256(reglas: tuple[Regla, ...] = CATALOGO) -> str:
    """El hash del catalogo que se evaluo (va en ejecucion_reglas)."""
    texto = json.dumps([r.metadatos() for r in reglas], sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()
