"""El motor de reglas, regla a regla, sobre instantaneas hechas a mano.

Las reglas son funciones puras: estos tests no abren ninguna base. Cada
caso construye las facturas que necesita (con los valores ya en enteros,
como los deja el almacen) y mira el resultado y la clave del hallazgo. El
catalogo se compara con la tabla del §7 de la especificacion, y el motor con
lo que dicen checks.py y dashboard.py del contrato v1 sobre las fixtures.
"""

from __future__ import annotations

import dataclasses
import random
from datetime import date

import pytest

from bms_agent.reglas import catalogo, motor
from bms_agent.reglas.base import (
    Factura,
    Instantanea,
    Linea,
    Politica,
    Relacion,
    TramoIva,
)

HOY = date(2026, 10, 14)


def linea(id_: int = 1, orden: int = 1, **cambios) -> Linea:
    valores = dict(
        id=id_, orden=orden, descripcion_doc="Montagewerk, locatie Rijnhaven",
        objeto_doc="Rijnhaven", unidad="hora", cantidad_mil=8000, tarifa_e4=425000,
        importe_cent=34000, tipo_iva_pb=None, fecha_inicio=None, fecha_fin=None,
        fecha_trabajo=None, objeto="doc:rijnhaven", ilegibles=frozenset())
    valores.update(cambios)
    return Linea(**valores)


def factura(id_: int = 1, **cambios) -> Factura:
    valores = dict(
        id=id_, sentido="entrante", tipo="factura", numero=f"2026-{id_:03d}",
        numero_norm=f"2026{id_:03d}", parte="btw:NL001234567B01", parte_nombre="Van Dijk BV",
        proveedor_id=None, cliente_id=None, emisor_nombre_doc="Van Dijk BV",
        emisor_kvk_doc="87654321", emisor_btw_doc="NL001234567B01", receptor_nombre_doc=None,
        receptor_btw_doc=None, fecha_factura=date(2026, 9, 15),
        periodo_inicio=date(2026, 9, 7), periodo_fin=date(2026, 9, 13), base_cent=34000,
        iva_cent=7140, total_cent=41140, tipo_iva_pb=2100, tratamiento_iva="estandar",
        iban_doc="NL02 ABNA 0123 4567 89", moneda=None, anulada=False, fusionada_en_id=None,
        lineas=(linea(id_ * 10),), desglose=(), ilegibles=frozenset(),
        no_solicitados=frozenset())
    valores.update(cambios)
    return Factura(**valores)


def instantanea(*facturas: Factura, relaciones=(), politica=None) -> Instantanea:
    return Instantanea(hoy=HOY, politica=politica or Politica(), facturas=tuple(facturas),
                       relaciones=tuple(relaciones))


def evaluar(regla_id: str, *facturas: Factura, relaciones=()) -> list:
    return list(catalogo.regla(regla_id).evaluar(instantanea(*facturas, relaciones=relaciones)))


def uno(regla_id: str, f: Factura):
    [resultado] = [r for r in evaluar(regla_id, f) if r.fila_id == f.id]
    return resultado


# --- el catalogo es el del §7 ---

# id: severidad (entrante), severidad saliente, anulable, pegajosa, segunda firma, prioridad
CATALOGO_SPEC = {
    "Q1": ("retencion", None, False, False, False, "otra"),
    "Q2": ("retencion", None, False, False, False, "otra"),
    "Q3": ("aviso", None, True, False, False, "otra"),
    "Q4": ("aviso", None, True, False, False, "otra"),
    "X1": ("bloqueo", None, False, True, False, "otra"),
    # Paso 6: la edicion de una linea que la lectura nueva no pudo casar.
    "M2": ("retencion", None, True, False, False, "otra"),
    "Z1": ("aviso", None, False, False, False, "otra"),
    "Z2": ("retencion", None, False, False, False, "otra"),
    "A0": ("retencion", None, False, False, False, "otra"),
    "A2": ("retencion", None, True, False, False, "otra"),
    "A5": ("bloqueo", None, False, False, False, "otra"),
    # Paso 5: A7 es pegajosa entera (la especificacion: solo por btw-id y KvK; registro).
    "A7": ("retencion", None, True, True, False, "otra"),
    "A8": ("retencion", None, True, False, False, "otra"),
    "B2": ("bloqueo", None, True, True, True, "duplicado_exacto"),
    "B3": ("retencion", None, True, True, False, "duplicado"),
    "B4": ("retencion", None, True, True, False, "duplicado"),
    "D1": ("bloqueo", "retencion", False, False, False, "otra"),
    "D2": ("bloqueo", "retencion", False, False, False, "otra"),
    "D2b": ("bloqueo", "retencion", True, False, False, "otra"),
    "D3": ("bloqueo", None, False, False, False, "iva_dura"),
    "D4": ("bloqueo", None, False, False, False, "otra"),
    "E1": ("retencion", None, True, False, False, "iva_blanda"),
    "E2": ("retencion", None, True, True, False, "iva_blanda"),
    "E3": ("bloqueo", None, False, False, False, "iva_dura"),
    "E4": ("bloqueo", None, False, False, False, "iva_dura"),
    "F0": ("retencion", None, False, True, False, "iban"),
    "F1": ("bloqueo", None, False, True, False, "iban"),
    "F2": ("bloqueo", None, False, True, False, "iban"),
    "F3": ("bloqueo", None, False, True, False, "iban"),
    "F4": ("bloqueo", None, False, True, False, "iban"),
    "F5": ("bloqueo", None, False, True, False, "iban"),
    "F6": ("bloqueo", None, False, True, False, "iban"),
    "F7": ("bloqueo", None, False, True, False, "iban"),
    "F8": ("bloqueo", None, False, True, False, "iban"),
    "F9": ("aviso", None, False, True, False, "iban"),
    # Paso 7: los pagos.
    "K1": ("aviso", None, True, False, False, "dias_vencida"),
    "K2": ("retencion", "aviso", False, True, False, "otra"),
    "K3": ("aviso", None, True, False, False, "otra"),
    "K4": ("bloqueo", None, False, True, False, "duplicado"),
    "K5": ("retencion", None, False, True, False, "otra"),
    "K6": ("bloqueo", None, False, True, False, "otra"),
    "K7": ("aviso", None, True, False, False, "otra"),
    "K8": ("retencion", None, False, False, False, "otra"),
    "G3": ("retencion", None, True, False, False, "planning"),
    "U1": ("aviso", None, True, False, False, "otra"),
}
# Donde vive cada hallazgo que no es de una factura (paso 5).
AMBITOS = {"Z1": "importacion", "Z2": "importacion", "F0": "importacion", "F5": "proveedor",
           "F6": "proveedor", "F8": "proveedor", "F9": "proveedor",
           "F7": "movimiento", "K6": "importacion", "K7": "movimiento"}
# Los avisos que abren una excepcion (spec §7: "+ exception"); F4 escala.
CREAN_EXCEPCION = {"Q3", "U1", "F4", "K1"}


def test_el_catalogo_es_el_del_paragrafo_7() -> None:
    assert [r.id for r in catalogo.CATALOGO] == list(CATALOGO_SPEC)
    for regla in catalogo.CATALOGO:
        assert (regla.severidad, regla.severidad_saliente, regla.anulable, regla.pegajosa,
                regla.segunda_firma, regla.entrada_prioridad) == CATALOGO_SPEC[regla.id], regla.id
        assert regla.titulo and regla.descripcion and regla.calidad
        assert regla.ambito == AMBITOS.get(regla.id, "factura"), regla.id
        assert regla.crea_excepcion == (regla.id in CREAN_EXCEPCION), regla.id


def test_lo_que_no_se_anula_nunca_es_la_lista_de_la_decision_12() -> None:
    for regla_id in ("F1", "F2", "F7", "X1", "E3", "E4", "K2", "K4", "K6", "R2", "R3"):
        assert catalogo.nunca_anulable(regla_id, "entrante")
        assert catalogo.nunca_anulable(regla_id, "saliente")
    for regla_id in ("D2", "D3", "D4", "D6"):
        assert catalogo.nunca_anulable(regla_id, "entrante")
        assert not catalogo.nunca_anulable(regla_id, "saliente")
    for regla_id in ("B3", "B4", "D2b", "G3", "B2"):
        assert not catalogo.nunca_anulable(regla_id, "entrante")
    for regla in catalogo.CATALOGO:
        for sentido in ("entrante", "saliente"):
            if catalogo.nunca_anulable(regla.id, sentido):
                assert not regla.anulable_para(sentido), regla.id


def test_las_familias_pegajosas_son_las_de_la_decision_11() -> None:
    """IBAN, duplicados y la moneda no se cierran solos; la aritmetica si. Del paso 5, el
    cambio de regimen (E2) y el de los datos de un proveedor (A7) tampoco (spec §7); del
    paso 7, las anomalias de pago: K2, K4, K5 y K6."""
    for regla in catalogo.CATALOGO:
        assert regla.pegajosa == (regla.familia in ("bancaria", "unicidad")
                                  or regla.id in ("X1", "E2", "A7", "K2", "K4", "K5", "K6")), \
            regla.id


def test_el_hash_del_catalogo_cambia_con_su_metadato() -> None:
    otro = tuple(dataclasses.replace(r, severidad="aviso") if r.id == "D4" else r
                 for r in catalogo.CATALOGO)
    assert catalogo.sha256() == catalogo.sha256(catalogo.CATALOGO)
    assert catalogo.sha256(otro) != catalogo.sha256()


# --- Q1 ---

def test_q1_completa_es_ok() -> None:
    assert uno("Q1", factura()).resultado == "ok"


@pytest.mark.parametrize("cambios, severidad, falta", [
    ({"numero": None, "numero_norm": None}, "bloqueo", "número"),
    ({"total_cent": None}, "bloqueo", "total"),
    ({"emisor_nombre_doc": None, "emisor_btw_doc": None, "emisor_kvk_doc": None, "parte": None},
     "bloqueo", "contraparte"),
    ({"fecha_factura": None}, "retencion", "fecha de factura"),
    ({"base_cent": None}, "retencion", "base imponible"),
    ({"iva_cent": None, "tratamiento_iva": None}, "retencion", "IVA o régimen"),
])
def test_q1_bloquea_sin_numero_total_o_contraparte_y_retiene_lo_demas(cambios, severidad,
                                                                      falta) -> None:
    r = uno("Q1", factura(**cambios))
    assert r.resultado == "fallo" and r.severidad == severidad
    assert falta in r.detalle


def test_q1_el_periodo_puede_venir_de_las_lineas() -> None:
    lineas = (linea(1, fecha_inicio=date(2026, 9, 7), fecha_fin=date(2026, 9, 13)),)
    assert uno("Q1", factura(periodo_inicio=None, periodo_fin=None, lineas=lineas)).resultado == "ok"
    sin = uno("Q1", factura(periodo_inicio=None, periodo_fin=None))
    assert sin.resultado == "fallo" and sin.severidad == "retencion"


def test_q1_un_literal_ilegible_no_es_un_campo_que_falta() -> None:
    """Esta en el papel y no se pudo leer: eso es Q2, no Q1."""
    r = uno("Q1", factura(total_cent=None, ilegibles=frozenset({"total_cent"})))
    assert r.resultado == "ok"


def test_q1_lo_que_v1_no_pidio_es_sin_datos_y_no_un_fallo() -> None:
    """Lo no pedido va en su propia clave: no tapa lo que si se comprobo (como E4)."""
    venta = factura(sentido="saliente", emisor_nombre_doc="BM Support BV", parte=None,
                    no_solicitados=frozenset({"receptor_nombre_doc", "receptor_btw_doc"}))
    resultados = {r.clave_hallazgo: r.resultado for r in evaluar("Q1", venta)}
    assert resultados == {"Q1|factura:1": "ok", "Q1|factura:1|contraparte": "sin_datos"}
    sin_fecha = dataclasses.replace(venta, fecha_factura=None)
    resultados = {r.clave_hallazgo: r for r in evaluar("Q1", sin_fecha)}
    assert resultados["Q1|factura:1"].resultado == "fallo"
    assert resultados["Q1|factura:1"].detalle == "Falta fecha de factura."
    assert resultados["Q1|factura:1|contraparte"].resultado == "sin_datos"
    pedida = dataclasses.replace(venta, no_solicitados=frozenset())
    assert uno("Q1", pedida).resultado == "fallo"


# --- X1 ---

@pytest.mark.parametrize("cambios, resultado", [
    ({}, "ok"),
    ({"moneda": "USD", "base_cent": None, "iva_cent": None, "total_cent": None,
      "ilegibles": frozenset({"base_cent", "iva_cent", "total_cent"})}, "fallo"),
    ({"base_cent": None, "iva_cent": None, "total_cent": None, "lineas": ()}, "sin_datos"),
    ({"base_cent": None, "iva_cent": None, "total_cent": None, "lineas": (),
      "ilegibles": frozenset({"total_cent"})}, "sin_datos"),
])
def test_x1(cambios, resultado) -> None:
    assert uno("X1", factura(**cambios)).resultado == resultado


def test_x1_en_dolares_dice_la_moneda_y_bloquea() -> None:
    r = uno("X1", factura(moneda="USD"))
    assert "USD" in r.detalle and r.valores == {"moneda": "USD"}
    [h] = motor.agrupar([r], instantanea(factura(moneda="USD")))
    assert h.severidad == "bloqueo" and h.clave == "X1|factura:1"


# --- D1 ---

def test_d1_desglose_completo() -> None:
    assert uno("D1", factura()).resultado == "ok"
    traslado = factura(tratamiento_iva="autoliquidacion", tipo_iva_pb=None, iva_cent=0)
    assert uno("D1", traslado).resultado == "ok"


@pytest.mark.parametrize("cambios, falta", [
    ({"lineas": ()}, "líneas"),
    ({"lineas": (linea(1, cantidad_mil=None),)}, "cantidad de la línea 1"),
    ({"lineas": (linea(1, tarifa_e4=None),)}, "tarifa de la línea 1"),
    ({"tipo_iva_pb": None}, "tipo de IVA"),
    ({"iva_cent": None}, "importe de IVA"),
    ({"base_cent": None}, "base imponible"),
])
def test_d1_falta_algo_del_desglose(cambios, falta) -> None:
    r = uno("D1", factura(**cambios))
    assert r.resultado == "fallo" and falta in r.detalle


def test_d1_bloquea_una_compra_y_retiene_una_venta() -> None:
    compra, venta = factura(1, lineas=()), factura(2, sentido="saliente", lineas=())
    severidades = {h.fila_id: h.severidad for h in motor.agrupar(
        evaluar("D1", compra, venta), instantanea(compra, venta))}
    assert severidades == {1: "bloqueo", 2: "retencion"}


def test_d1_con_el_tipo_en_las_lineas_o_en_el_desglose_no_falta() -> None:
    en_lineas = factura(tipo_iva_pb=None, lineas=(linea(1, tipo_iva_pb=2100),))
    con_desglose = factura(tipo_iva_pb=None, desglose=(TramoIva(1, 2100, 34000, 7140),))
    assert uno("D1", en_lineas).resultado == "ok"
    assert uno("D1", con_desglose).resultado == "ok"


# --- D2 y D2b ---

def _tres_lineas(diferencia_cent: int) -> Factura:
    lineas = tuple(linea(i, i, importe_cent=10000) for i in (1, 2, 3))
    return factura(base_cent=30000 + diferencia_cent, lineas=lineas)


def test_d2_un_centimo_por_linea_y_dos_por_factura() -> None:
    assert uno("D2", _tres_lineas(5)).resultado == "ok"
    r = uno("D2", _tres_lineas(6))
    assert r.resultado == "fallo"
    assert r.detalle == "Las líneas suman 300,00 y la base dice 300,06."


def test_d2_sin_base_o_con_una_linea_ilegible_es_sin_datos() -> None:
    assert uno("D2", factura(base_cent=None)).resultado == "sin_datos"
    assert uno("D2", factura(lineas=(linea(1, importe_cent=None),))).resultado == "sin_datos"
    assert uno("D2", factura(lineas=())).resultado == "sin_datos"


def test_d2b_marca_la_linea_que_no_cuadra() -> None:
    lineas = (linea(1, 1), linea(2, 2, importe_cent=34100))
    r = uno("D2b", factura(lineas=lineas, base_cent=68100))
    assert r.resultado == "fallo"
    assert r.detalle == "linea 2: 8 x 42,50 deberia dar 340,00 y pone 341,00"
    assert [(o.tabla, o.fila_id) for o in r.objetivos] == [("factura_linea", 2)]


def test_d2b_sin_ninguna_linea_completa_es_sin_datos() -> None:
    assert uno("D2b", factura(lineas=(linea(1, tarifa_e4=None),))).resultado == "sin_datos"


# --- D3, D4, E3, E4 ---

def test_d3_la_cuota_por_el_tipo() -> None:
    assert uno("D3", factura()).detalle == "340,00 al 21% = 71,40."
    assert uno("D3", factura(iva_cent=7142)).resultado == "ok"
    mala = uno("D3", factura(iva_cent=7143))
    assert mala.resultado == "fallo" and "Al 21% deberían ser 71,40" in mala.detalle


def test_d3_no_aplica_con_iva_trasladado_o_kor() -> None:
    for tratamiento in ("autoliquidacion", "kor"):
        assert uno("D3", factura(tratamiento_iva=tratamiento)).resultado == "no_aplica"


def test_d3_con_desglose_mira_cada_tipo() -> None:
    desglose = (TramoIva(1, 2100, 20000, 4200), TramoIva(2, 900, 10000, 950))
    r = uno("D3", factura(desglose=desglose))
    assert r.resultado == "fallo" and "Al 9%" in r.detalle
    assert [(o.tabla, o.fila_id) for o in r.objetivos] == [("factura_iva", 2)]
    bueno = (TramoIva(1, 2100, 20000, 4200), TramoIva(2, 900, 10000, 900))
    assert uno("D3", factura(desglose=bueno)).resultado == "ok"


def test_d4() -> None:
    assert uno("D4", factura(total_cent=41142)).resultado == "ok"
    r = uno("D4", factura(total_cent=41143))
    assert r.resultado == "fallo"
    assert r.detalle == "Base y cuota suman 411,40 y el total dice 411,43."
    assert uno("D4", factura(iva_cent=None)).resultado == "sin_datos"


def test_e3_kor_con_iva_bloquea() -> None:
    kor = factura(tratamiento_iva="kor", tipo_iva_pb=None)
    assert uno("E3", kor).resultado == "fallo"
    assert uno("E3", dataclasses.replace(kor, iva_cent=0, total_cent=34000)).resultado == "ok"
    # Sin cuota impresa, lo que el total pasa de la base es IVA cobrado.
    oculta = dataclasses.replace(kor, iva_cent=None, total_cent=41140)
    assert uno("E3", oculta).resultado == "fallo"
    assert uno("E3", factura()).resultado == "no_aplica"


def test_e4_cuota_y_btw_del_receptor_son_dos_resultados() -> None:
    traslado = factura(tratamiento_iva="autoliquidacion", tipo_iva_pb=None, iva_cent=0,
                       total_cent=34000, receptor_btw_doc="NL009999999B01")
    resultados = {r.clave: r.resultado for r in evaluar("E4", traslado)}
    assert resultados == {"cuota": "ok", "btw_receptor": "ok"}
    cobra = dataclasses.replace(traslado, iva_cent=7140, total_cent=41140)
    assert {r.clave: r.resultado for r in evaluar("E4", cobra)}["cuota"] == "fallo"
    sin_btw = dataclasses.replace(traslado, receptor_btw_doc=None)
    assert {r.clave: r.resultado for r in evaluar("E4", sin_btw)}["btw_receptor"] == "fallo"
    v1 = dataclasses.replace(sin_btw, no_solicitados=frozenset({"receptor_btw_doc"}))
    assert {r.clave: r.resultado for r in evaluar("E4", v1)} == {
        "cuota": "ok", "btw_receptor": "sin_datos"}
    claves = sorted(r.clave_hallazgo for r in evaluar("E4", cobra))
    assert claves == ["E4|factura:1|btw_receptor", "E4|factura:1|cuota"]


# --- F1 ---

@pytest.mark.parametrize("iban, resultado", [
    ("NL02 ABNA 0123 4567 89", "ok"),
    ("NL02ABNA0123456788", "fallo"),
    (None, "sin_datos"),
])
def test_f1(iban, resultado) -> None:
    assert uno("F1", factura(iban_doc=iban)).resultado == resultado


# --- B2, B3, B4 ---

def test_b2_mismo_numero_de_la_misma_contraparte_es_un_hallazgo_de_grupo() -> None:
    a, b = factura(1, numero="2026-001", numero_norm="2026001"), \
        factura(2, numero="2026 001", numero_norm="2026001", total_cent=50000)
    otra = factura(3, numero="2026-001", numero_norm="2026001", parte="btw:NL002345678B01")
    resultados = evaluar("B2", a, b, otra)
    assert {r.fila_id: r.resultado for r in resultados} == {1: "fallo", 2: "fallo", 3: "ok"}
    [h] = motor.agrupar(resultados, instantanea(a, b, otra))
    assert h.clave == "B2|grupo:1"      # la primera factura del grupo: no cambia al resolverse
    assert (h.tabla, h.fila_id, h.facturas) == ("factura", 2, (1, 2))
    assert h.severidad == "bloqueo"


def test_b2_una_relacion_confirmada_o_una_fusion_no_es_duplicado() -> None:
    a, b = factura(1, numero_norm="X1"), factura(2, numero_norm="X1")
    assert {r.resultado for r in evaluar("B2", a, b, relaciones=[Relacion(2, 1, "sustituye")])} \
        == {"ok"}
    fusionada = dataclasses.replace(b, fusionada_en_id=1)
    assert {r.fila_id: r.resultado for r in evaluar("B2", a, fusionada)} == {
        1: "ok", 2: "no_aplica"}


def test_b2_sin_contraparte_no_agrupa_con_nadie() -> None:
    a = factura(1, parte=None, numero_norm="X1")
    b = factura(2, parte=None, numero_norm="X1")
    assert {r.resultado for r in evaluar("B2", a, b)} == {"sin_datos"}


def test_b3_mismo_importe_pocos_dias_otro_numero() -> None:
    a = factura(1, fecha_factura=date(2026, 9, 1))
    b = factura(2, fecha_factura=date(2026, 9, 15), total_cent=41141)
    resultados = evaluar("B3", a, b)
    assert {r.fila_id: r.resultado for r in resultados} == {1: "fallo", 2: "fallo"}
    [h] = motor.agrupar(resultados, instantanea(a, b))
    assert h.clave == "B3|par:1-2" and h.severidad == "retencion"
    lejos = dataclasses.replace(b, fecha_factura=date(2026, 9, 16))
    assert {r.resultado for r in evaluar("B3", a, lejos)} == {"ok"}
    otro_importe = dataclasses.replace(b, total_cent=41142)
    assert {r.resultado for r in evaluar("B3", a, otro_importe)} == {"ok"}


def test_b3_dos_semanas_distintas_al_mismo_importe_no_son_duplicado() -> None:
    a = factura(1, fecha_factura=date(2026, 9, 8), periodo_inicio=date(2026, 8, 31),
                periodo_fin=date(2026, 9, 6))
    b = factura(2, fecha_factura=date(2026, 9, 15))
    assert {r.resultado for r in evaluar("B3", a, b)} == {"ok"}


def test_b4_periodos_que_se_pisan_por_objeto() -> None:
    a = factura(1, total_cent=41140)
    b = factura(2, total_cent=99999, periodo_inicio=date(2026, 9, 10),
                periodo_fin=date(2026, 9, 20))
    resultados = evaluar("B4", a, b)
    [h] = motor.agrupar(resultados, instantanea(a, b))
    assert "solapan 4 día(s)" in h.detalle and h.clave == "B4|par:1-2"
    otra_obra = dataclasses.replace(b, lineas=(linea(20, objeto="doc:schiedam",
                                                     objeto_doc="Schiedam"),))
    assert {r.resultado for r in evaluar("B4", a, otra_obra)} == {"ok"}
    sin_obra = dataclasses.replace(b, lineas=(linea(20, objeto=None, objeto_doc=None),))
    assert {r.resultado for r in evaluar("B4", a, sin_obra)} == {"fallo"}


def test_b4_un_abono_o_una_relacion_confirmada_no_son_cobrar_dos_veces() -> None:
    a = factura(1)
    abono = factura(2, tipo="nota_credito", total_cent=-12251)
    assert {r.fila_id: r.resultado for r in evaluar("B4", a, abono)} == {1: "ok", 2: "no_aplica"}
    b = factura(3, total_cent=99999)
    assert {r.resultado for r in evaluar("B4", a, b, relaciones=[Relacion(3, 1, "corrige")])} \
        == {"ok"}


# --- G3 ---

def _con_tarifa(id_: int, fecha: date, tarifa_e4: int, **cambios) -> Factura:
    return factura(id_, fecha_factura=fecha, lineas=(linea(id_ * 10, tarifa_e4=tarifa_e4,
                                                           **cambios),))


def test_g3_una_subida_senala_las_facturas_nuevas() -> None:
    facturas = [_con_tarifa(1, date(2026, 3, 5), 425000), _con_tarifa(2, date(2026, 6, 5), 580000),
                _con_tarifa(3, date(2026, 7, 5), 580000)]
    resultados = evaluar("G3", *facturas)
    assert {r.fila_id: r.resultado for r in resultados} == {1: "ok", 2: "fallo", 3: "fallo"}
    [h] = motor.agrupar(resultados, instantanea(*facturas))
    assert h.fila_id == 3 and h.facturas == (2, 3) and h.severidad == "retencion"
    assert "venía a 42,50 y después a 58,00" in h.detalle


def test_g3_no_compara_otro_trabajo_otra_unidad_ni_dentro_de_una_factura() -> None:
    viaje = _con_tarifa(2, date(2026, 6, 5), 225000, descripcion_doc="Reisuren, locatie X")
    pieza = _con_tarifa(3, date(2026, 6, 5), 580000, unidad="stuk")
    base = _con_tarifa(1, date(2026, 3, 5), 425000)
    assert {r.resultado for r in evaluar("G3", base, viaje, pieza)} == {"ok"}
    dos = factura(4, lineas=(linea(41, tarifa_e4=425000), linea(42, 2, tarifa_e4=580000)))
    assert {r.resultado for r in evaluar("G3", dos)} == {"ok"}


def test_g3_una_factura_sin_fecha_no_es_la_referencia() -> None:
    """Sin fecha no se sabe si vino antes: no fija la tarifa buena ni senala a las demas."""
    sin_fecha = factura(1, fecha_factura=None,
                        lineas=(linea(10, tarifa_e4=500000, importe_cent=40000),))
    enero, febrero = (_con_tarifa(2, date(2026, 1, 1), 425000),
                      _con_tarifa(3, date(2026, 2, 1), 425000))
    resultados = {r.fila_id: r for r in evaluar("G3", sin_fecha, enero, febrero)}
    assert {i: r.resultado for i, r in resultados.items()} == {
        1: "sin_datos", 2: "ok", 3: "ok"}
    assert "fecha" in resultados[1].detalle
    assert not any("0000" in r.detalle for r in resultados.values())


def test_g3_solo_mira_compras() -> None:
    venta = _con_tarifa(1, date(2026, 3, 5), 425000, )
    assert uno("G3", dataclasses.replace(venta, sentido="saliente")).resultado == "no_aplica"


# --- el motor ---

def _variado() -> list[Factura]:
    """Un poco de todo: duplicados, periodos que se pisan, tarifas que cambian y errores."""
    return [
        factura(1),
        factura(2, numero_norm="2026001", total_cent=41143),
        factura(3, fecha_factura=date(2026, 9, 20), periodo_inicio=date(2026, 9, 10),
                periodo_fin=date(2026, 9, 17), lineas=(linea(30, tarifa_e4=440000),
                                                       linea(31, 2, importe_cent=1)),
                base_cent=34001),
        factura(4, parte="btw:NL002345678B01", iban_doc="NL00XXXX", moneda="USD"),
        factura(5, tratamiento_iva="kor", numero=None, numero_norm=None),
        factura(6, anulada=True),
        factura(7, numero_norm="2026001", base_cent=44000, iva_cent=8500, total_cent=52500,
                lineas=(linea(70, importe_cent=34000), linea(71, 2, importe_cent=10000,
                                                             cantidad_mil=1000,
                                                             tarifa_e4=1000000)),
                desglose=(TramoIva(70, 2100, 34000, 7140), TramoIva(71, 900, 10000, 1360))),
        factura(8, numero_norm="2026001", fecha_factura=date(2026, 9, 16)),
    ]


# Relaciones confirmadas: la 8 sustituye a la 1 (no son duplicado entre si) y
# la 3 corrige a la 2.
_RELACIONES = (Relacion(8, 1, "sustituye"), Relacion(3, 2, "corrige"))


def test_los_resultados_salen_en_un_orden_fijo() -> None:
    resultados = motor.evaluar(instantanea(*_variado(), relaciones=_RELACIONES))
    posicion = {r.id: i for i, r in enumerate(catalogo.CATALOGO)}
    claves = [(posicion[r.regla], r.tabla, r.fila_id, r.grupo or "", r.clave) for r in resultados]
    assert claves == sorted(claves)


def test_barajar_la_entrada_no_cambia_nada() -> None:
    """Ni los resultados ni los hallazgos dependen del orden de facturas, lineas, tramos y relaciones."""
    entrada = instantanea(*_variado(), relaciones=_RELACIONES)
    original = motor.evaluar(entrada)
    fallan = {r.regla for r in original if r.resultado == "fallo"}
    assert {"B2", "B3", "B4", "D3"} <= fallan
    azar = random.Random(20261014)
    for _ in range(5):
        facturas = [dataclasses.replace(f, lineas=tuple(azar.sample(f.lineas, len(f.lineas))),
                                        desglose=tuple(azar.sample(f.desglose, len(f.desglose))))
                    for f in _variado()]
        azar.shuffle(facturas)
        relaciones = azar.sample(_RELACIONES, len(_RELACIONES))
        barajada = motor.evaluar(instantanea(*facturas, relaciones=relaciones))
        assert barajada == original
        assert motor.agrupar(barajada, instantanea(*facturas, relaciones=relaciones)) == \
            motor.agrupar(original, entrada)


def test_dos_resultados_con_la_misma_clave_son_un_error_de_la_regla() -> None:
    def doble(inst):
        f = inst.facturas[0]
        return [motor.Resultado("D4", "factura", f.id, "ok", "a"),
                motor.Resultado("D4", "factura", f.id, "ok", "b")]

    regla = dataclasses.replace(catalogo.regla("D4"), evaluar=doble)
    with pytest.raises(motor.ResultadoDuplicado):
        motor.evaluar(instantanea(factura()), (regla,))


def test_la_huella_cambia_con_los_valores_las_fuentes_la_politica_y_la_version() -> None:
    regla = catalogo.regla("D4")
    base = motor.huella(regla, {"total_cent": 1}, {"factura:1:total_cent": "extraccion"},
                        Politica())
    assert base == motor.huella(regla, {"total_cent": 1},
                                {"factura:1:total_cent": "extraccion"}, Politica())
    assert base != motor.huella(regla, {"total_cent": 2},
                                {"factura:1:total_cent": "extraccion"}, Politica())
    assert base != motor.huella(regla, {"total_cent": 1},
                                {"factura:1:total_cent": "manual_correccion"}, Politica())
    floja = dataclasses.replace(Politica(), tolerancia_factura=Politica().tolerancia_factura * 10)
    assert base != motor.huella(regla, {"total_cent": 1},
                                {"factura:1:total_cent": "extraccion"}, floja)
    # Un parametro que la regla no usa no entra en su huella.
    otra_ventana = dataclasses.replace(Politica(), ventana_duplicado_dias=30)
    assert base == motor.huella(regla, {"total_cent": 1},
                                {"factura:1:total_cent": "extraccion"}, otra_ventana)
    nueva = dataclasses.replace(regla, version=2)
    assert base != motor.huella(nueva, {"total_cent": 1},
                                {"factura:1:total_cent": "extraccion"}, Politica())
    with pytest.raises(TypeError):
        motor.huella(regla, {"total": 1.5}, {}, Politica())


def test_cada_regla_dice_de_que_columnas_sale_su_huella() -> None:
    assert motor.campos_de_fuente(catalogo.regla("D4")) == {
        "factura": ("base_cent", "iva_cent", "total_cent")}
    assert motor.campos_de_fuente(catalogo.regla("D2")) == {
        "factura": ("base_cent",), "factura_linea": ("importe_cent",)}
    assert "moneda_doc" in motor.campos_de_fuente(catalogo.regla("X1"))["factura"]


# --- el motor y el contrato v1 dicen lo mismo ---

_ESTADO_V1 = {"sin datos": "sin_datos", "no aplica": "no_aplica"}
_MISMO_TEXTO = ("X1", "D2", "D2b", "D4", "F1", "E3", "E4")


def _sin_ceros(texto: str) -> str:
    """La cantidad sin ceros de mas: el almacen guarda 37,50 horas como 37500 milesimas."""
    import re
    from decimal import Decimal

    from bms_agent.reglas.base import compacto

    return re.sub(r"\b\d+\.\d+(?= x )", lambda m: str(compacto(Decimal(m.group(0)))), texto)


def _comparar_con_v1(conn) -> list[tuple[str, str]]:
    """Cada resultado del motor contra el de checks.py para la misma factura.

    X1, D2, D2b, D4, F1, E3 y la cuota de E4 tienen que coincidir en el
    resultado y en el texto, tambien cuando fallan; en D2b el texto se
    compara sin los ceros de mas de la cantidad, que el almacen no guarda.
    D3 solo en el resultado (en el v1, la KOR con IVA sale como E3/E4 en vez
    de D3). Devuelve lo que se comparo, como (regla, resultado).
    """
    from bms_agent.checks import run_checks
    from bms_agent.legado import registros_resueltos
    from bms_agent.reglas.instantanea import construir

    por_numero = {r["extraction"]["invoice_number"]: run_checks(r["extraction"])
                  for r in registros_resueltos(conn)}
    numero_de = {f["id"]: f["numero"] for f in conn.execute("SELECT id, numero FROM factura")}
    comparadas = []
    for r in motor.evaluar(construir(conn, hoy=HOY)):
        legado = {c.rule: c for c in por_numero[numero_de[r.fila_id]]}
        if r.regla not in legado or r.regla not in _MISMO_TEXTO + ("D3",):
            continue
        if r.regla == "E4" and r.clave != "cuota":
            continue
        v1 = legado[r.regla]
        assert _ESTADO_V1.get(v1.status, v1.status) == r.resultado, (r.regla, r.fila_id)
        if r.regla in _MISMO_TEXTO:
            esperado = _sin_ceros(v1.detail) if r.regla == "D2b" else v1.detail
            assert r.detalle == esperado, (r.regla, r.fila_id)
        comparadas.append((r.regla, r.resultado))
    return comparadas


def test_el_motor_y_el_contrato_v1_dicen_lo_mismo_de_cada_fixture(tipado) -> None:
    """Las mismas comprobaciones de fondo: el mismo resultado sobre las siete fixtures."""
    comparadas = _comparar_con_v1(tipado.conn)
    assert len(comparadas) == 7 * 6 and ("X1", "fallo") in comparadas


_LINEA_MAL = [{"description": "Montagewerk, locatie Rijnhaven", "quantity_raw": "37,50",
               "unit": "uur", "unit_rate_raw": "42,50", "line_total_raw": "1.600,00",
               "location": "Rijnhaven", "week_number": 36, "period_start": None,
               "period_end": None}]


def test_el_motor_y_el_contrato_v1_dicen_lo_mismo_de_cada_fallo(almacen, tmp_path) -> None:
    """Las fixtures casi no fallan: una extraccion hecha a mano para cada fallo, y el mismo texto."""
    from test_hallazgos import _cargar, _registro

    _cargar(almacen, tmp_path / "out",
            _registro("d2", invoice_number="D2-1", subtotal_excl_vat_raw="2.400,00",
                      vat_amount_raw="504,00", total_incl_vat_raw="2.904,00"),
            _registro("d2b", invoice_number="D2B-1", lines=_LINEA_MAL,
                      subtotal_excl_vat_raw="1.600,00", vat_amount_raw="336,00",
                      total_incl_vat_raw="1.936,00"),
            _registro("d4", invoice_number="D4-1", total_incl_vat_raw="2.903,79"),
            _registro("f1", invoice_number="F1-1", iban="NL02ABNA0123456788"),
            _registro("e3", invoice_number="E3-1", vat_regime="kor_exempt", kor_mentioned=True),
            _registro("e4", invoice_number="E4-1", vat_regime="reverse_charged",
                      reverse_charge_mentioned=True))
    fallos = {regla for regla, resultado in _comparar_con_v1(almacen.conn)
              if resultado == "fallo"}
    # El de X1 ya sale en las fixtures (la factura en dolares).
    assert fallos == {"D2", "D2b", "D4", "F1", "E3", "E4"}
