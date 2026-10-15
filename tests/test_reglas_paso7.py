"""Las reglas del paso 7 (K1-K8, F7 y X1 sobre el banco), regla a regla, sin base.

Las instantaneas llevan, ademas de lo del paso 5, los extractos y
movimientos del banco, lo pagado de cada factura (aplicaciones), los
beneficiarios conocidos y los dias en que una factura estuvo Bloqueada. Los
constructores de aqui los usa tambien test_pureza_reglas.py.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal

from test_reglas import HOY
from test_reglas_paso5 import (
    K_HEREDADA,
    K_RECHAZADA,
    compra,
    cuenta,
    de,
    evento,
    lote,
    lotes,
    maestros,
    persona_decide,
    resultados,
)

from bms_agent.reglas import catalogo
from bms_agent.reglas.instantanea import tramos_bloqueados
from bms_agent.reglas.base import (
    Aplicacion,
    Bloqueo,
    Extracto,
    Factura,
    Instantanea,
    Movimiento,
    PagadoExact,
    Politica,
)
from bms_agent.reglas.pagos import roturas, saldo, tolerancia_cent

PROPIA = "NL60INGB0009988776"
OTRA_PROPIA = "NL93RABO0987654321"
BELASTINGDIENST = "NL86INGB0002445588"
SIN_REGISTRAR = "NL03RABO0312456789"


# ------------------------------------------------------------ constructores

def movimiento(id_: int, importe: int | None, fecha: date = date(2026, 10, 12), *,
               iban: str | None = K_HEREDADA, nombre: str | None = "Van Dijk BV",
               referencia: str | None = "FACTUUR2026001", extracto: int = 2,
               moneda: str = "EUR", cuenta: str = PROPIA) -> Movimiento:
    return Movimiento(id_, extracto, cuenta, fecha, importe, moneda, iban, nombre, referencia)


def extracto(id_: int, secuencia: int | None, inicial: int | None, final: int | None,
             desde: date, hasta: date, *, cuenta: str = PROPIA, con_saldos: bool = True,
             importacion: int = 5) -> Extracto:
    return Extracto(id_, importacion, cuenta, secuencia, inicial, final, desde, hasta,
                    con_saldos)


def aplicacion(id_: int, factura_id: int, importe: int, *, movimiento_id: int | None = None,
               fecha: date = date(2026, 10, 12), fuente: str = "banco",
               metodo: str = "automatica", estado: str = "confirmada") -> Aplicacion:
    if fuente == "banco" and movimiento_id is None:
        movimiento_id = id_
    return Aplicacion(id_, factura_id, movimiento_id, importe, fecha, fuente, metodo, estado)


EXTRACTOS = (
    extracto(1, 100, 0, 100000, date(2026, 9, 1), date(2026, 9, 30)),
    extracto(2, 101, 100000, 58860, date(2026, 10, 1), date(2026, 10, 13)),
)


def pagada(f: Factura, *aplicaciones_: Aplicacion, tolerancia: int = 0) -> Factura:
    """La factura con lo pagado como lo calcula la instantanea (reglas.pagos.saldo)."""
    s = saldo(f.total_cent, [a for a in aplicaciones_ if a.factura_id == f.id], tolerancia)
    return dataclasses.replace(f, pagado_cent=s.pagado_cent, fuente_pago=s.fuente,
                               pagada=s.pagada)


def banco(*facturas: Factura, movimientos: tuple[Movimiento, ...] = (),
          aplicaciones: tuple[Aplicacion, ...] = (), extractos: tuple[Extracto, ...] = EXTRACTOS,
          bloqueos: tuple[Bloqueo, ...] = (), politica: Politica | None = None,
          con_lotes=None, beneficiarios: frozenset[str] = frozenset({BELASTINGDIENST}),
          ) -> Instantanea:
    politica = politica or Politica(empresa_ibans=(OTRA_PROPIA, PROPIA))
    inst = maestros(*(pagada(f, *aplicaciones) for f in facturas), politica=politica)
    return dataclasses.replace(
        inst, movimientos=movimientos, aplicaciones=aplicaciones, extractos=extractos,
        bloqueos=bloqueos, beneficiarios=beneficiarios,
        lotes=con_lotes if con_lotes is not None else inst.lotes)


def venta(id_: int, **cambios) -> Factura:
    valores = dict(sentido="saliente", cliente_id=3, parte="cliente:3", proveedor_id=None,
                   emisor_nombre_doc="BM Support BV", receptor_nombre_doc="Havenbedrijf")
    valores.update(cambios)
    return compra(id_, **valores)


VENCIDA = date(2026, 10, 1)


# ------------------------------------------------------------ el saldo

def test_el_saldo_lo_da_la_fuente_que_manda() -> None:
    def a(importe, fuente, estado="confirmada"):
        return aplicacion(1, 1, importe, fuente=fuente, estado=estado,
                          metodo="manual" if fuente == "manual" else "automatica")

    assert saldo(41140, [], 0) == (41140, 0, None, 0, 41140, False)
    # Lo manual vale hasta que llega Exact, y Exact hasta que llega el banco.
    assert saldo(41140, [a(41140, "manual")], 0).pagada
    assert saldo(41140, [a(41140, "manual"), a(20000, "exact")], 0)[1:] == (
        20000, "exact", 1, 21140, False)
    s = saldo(41140, [a(41140, "manual"), a(41140, "exact"), a(20000, "banco")], 0)
    assert (s.fuente, s.pagado_cent, s.pendiente_cent, s.pagada) == ("banco", 20000, 21140, False)
    # Una propuesta o una retirada no cuentan.
    no_cuentan = [a(41140, "banco", "propuesta"), a(41140, "banco", "retirada")]
    assert saldo(41140, no_cuentan, 0).fuente is None
    # La tolerancia: por defecto al centimo.
    assert not saldo(41140, [a(41139, "banco")], 0).pagada
    assert saldo(41140, [a(41139, "banco")], 1).pagada
    assert tolerancia_cent(Decimal("0.00")) == 0 and tolerancia_cent(Decimal("0.05")) == 5


# ------------------------------------------------------------ K1

def test_k1_una_compra_vencida_sin_pagar_avisa_y_abre_excepcion() -> None:
    inst = banco(compra(1, vencimiento=VENCIDA), compra(2, vencimiento=HOY),
                 compra(3, vencimiento=VENCIDA))
    [r] = de("K1", inst, 1)
    assert (r.resultado, r.valores["pendiente_cent"]) == ("fallo", 41140)
    assert "2026-10-01" in r.detalle and "pagar" in r.detalle
    assert de("K1", inst, 2) == []                     # vence hoy: todavia no
    regla = catalogo.regla("K1")
    assert (regla.severidad, regla.crea_excepcion, regla.anulable) == ("aviso", True, True)


def test_k1_lo_que_esta_pagado_no_esta_vencido_y_un_parcial_si() -> None:
    entera = aplicacion(1, 1, 41140)
    parcial = aplicacion(2, 2, 20000)
    inst = banco(compra(1, vencimiento=VENCIDA), compra(2, vencimiento=VENCIDA),
                 aplicaciones=(entera, parcial))
    assert de("K1", inst, 1) == []
    [r] = de("K1", inst, 2)
    assert r.valores["pendiente_cent"] == 21140


def test_k1_una_venta_cuenta_como_vencida_pasados_los_dias_de_la_politica() -> None:
    inst = banco(venta(1, vencimiento=date(2026, 9, 30)), venta(2, vencimiento=date(2026, 9, 29)))
    assert de("K1", inst, 1) == []                     # 14 dias justos
    [r] = de("K1", inst, 2)
    assert "cobrar" in r.detalle and r.valores["limite_dias"] == 14


def test_k1_sin_un_extracto_que_cubra_desde_la_factura_no_se_sabe() -> None:
    antigua = compra(1, vencimiento=VENCIDA, fecha_factura=date(2026, 8, 1))
    [r] = de("K1", banco(antigua), 1)
    assert r.resultado == "sin_datos"
    sin_banco = banco(compra(2, vencimiento=VENCIDA), extractos=(),
                      con_lotes=lotes()[:4])
    assert [r.resultado for r in de("K1", sin_banco, 2)] == ["sin_datos"]
    # Un banco pasado de su frescura tampoco lo dice.
    viejo = (*lotes()[:4], lote(5, "banco", "extracto", exportado=date(2026, 10, 5)))
    assert [r.resultado for r in de("K1", banco(compra(3, vencimiento=VENCIDA),
                                                con_lotes=viejo), 3)] == ["sin_datos"]
    # Con un Exact de pagos al dia si se sabe, aunque los extractos empiecen despues.
    con_exact = (*lotes(), lote(6, "exact", "pagos_exact", exportado=date(2026, 10, 13)))
    [r] = de("K1", banco(antigua, con_lotes=con_exact), 1)
    assert r.resultado == "fallo"


# ------------------------------------------------------------ K2

def test_k2_un_pago_parcial_deja_el_saldo_y_retiene() -> None:
    inst = banco(compra(1), compra(2), compra(3), aplicaciones=(
        aplicacion(1, 1, 20000), aplicacion(2, 2, 41140), aplicacion(3, 3, 50000)))
    [r] = de("K2", inst, 1)
    assert (r.resultado, r.valores["pendiente_cent"], r.valores["fuente"]) == (
        "fallo", 21140, "banco")
    assert "parcial" in r.detalle
    assert de("K2", inst, 2) == []                     # pagada entera
    [mas] = de("K2", inst, 3)
    assert "de más" in mas.detalle and mas.valores["pendiente_cent"] == -8860
    regla = catalogo.regla("K2")
    assert (regla.severidad_para("entrante"), regla.severidad_para("saliente")) == (
        "retencion", "aviso")
    assert catalogo.nunca_anulable("K2", "entrante") and regla.pegajosa


def test_k2_sin_total_en_euros_no_se_puede_comparar() -> None:
    inst = banco(compra(1, total_cent=None, moneda="USD"),
                 aplicaciones=(aplicacion(1, 1, 20000, fuente="manual", metodo="manual"),))
    assert [r.resultado for r in de("K2", inst, 1)] == ["sin_datos"]


# ------------------------------------------------------------ K3

def test_k3_una_marca_a_mano_sin_rastro_en_el_banco() -> None:
    def manual(id_, factura_id, fecha):
        return aplicacion(id_, factura_id, 41140, fuente="manual", metodo="manual", fecha=fecha)

    inst = banco(compra(1), compra(2), compra(3), aplicaciones=(
        manual(1, 1, date(2026, 10, 1)),
        manual(2, 2, date(2026, 10, 10)),                       # aun dentro de los 7 dias
        manual(3, 3, date(2026, 10, 1)), aplicacion(4, 3, 41140)))   # el banco lo trae
    [r] = de("K3", inst, 1)
    assert r.resultado == "fallo" and r.valores["fecha_pago"] == "2026-10-01"
    assert de("K3", inst, 2) == [] and de("K3", inst, 3) == []
    # Sin extractos que lleguen a los dias siguientes al pago, no se sabe.
    corto = (extracto(1, 100, 0, 100000, date(2026, 9, 1), date(2026, 10, 3)),)
    assert [r.resultado for r in de("K3", banco(compra(1), extractos=corto, aplicaciones=(
        manual(1, 1, date(2026, 10, 1)),)), 1)] == ["sin_datos"]


# ------------------------------------------------------------ K4

def test_k4_dos_cargos_iguales_a_la_misma_cuenta_y_referencia_son_un_pago_doble() -> None:
    movs = (movimiento(1, -41140, date(2026, 10, 1)), movimiento(2, -41140, date(2026, 10, 12)),
            movimiento(3, -41140, date(2026, 11, 13)),            # 32 dias despues: otro mes
            movimiento(4, -100, date(2026, 10, 1), iban=BELASTINGDIENST, referencia="BTW"),
            movimiento(5, -100, date(2026, 10, 2), iban=BELASTINGDIENST, referencia="BTW"),
            movimiento(6, -500, date(2026, 10, 2), referencia=None),
            movimiento(7, -500, date(2026, 10, 3), referencia=None))
    inst = banco(compra(1), movimientos=movs, aplicaciones=(aplicacion(1, 1, 41140),))
    k4 = resultados("K4", inst)
    assert sorted(r.fila_id for r in k4 if r.tabla == "movimiento") == [1, 2]
    [uno, dos] = [r for r in k4 if r.tabla == "movimiento"]
    assert uno.grupo == dos.grupo == "pago_doble:1"
    assert ("factura", 1) in {(o.tabla, o.fila_id) for o in uno.objetivos}
    regla = catalogo.regla("K4")
    assert (regla.severidad, regla.pegajosa) == ("bloqueo", True)
    assert catalogo.nunca_anulable("K4", "entrante")


def test_k4_una_factura_pagada_de_mas_con_dos_cargos() -> None:
    inst = banco(compra(1), compra(2), aplicaciones=(
        aplicacion(1, 1, 41140), aplicacion(2, 1, 41140),
        aplicacion(3, 2, 20000), aplicacion(4, 2, 21140)))        # dos parciales que cuadran
    [r] = [r for r in resultados("K4", inst) if r.tabla == "factura"]
    assert (r.fila_id, r.valores["pagado_cent"], r.valores["movimientos"]) == (1, 82280, [1, 2])


# ------------------------------------------------------------ K5

def test_k5_pagada_mientras_estaba_bloqueada() -> None:
    bloqueos = (Bloqueo(1, "F3", date(2026, 10, 10), None),
                Bloqueo(2, "B2", date(2026, 10, 1), date(2026, 10, 5)))
    inst = banco(compra(1), compra(2), bloqueos=bloqueos, aplicaciones=(
        aplicacion(1, 1, 41140, fecha=date(2026, 10, 12)),
        aplicacion(2, 2, 41140, fecha=date(2026, 10, 6)),
        aplicacion(3, 2, 100, fecha=date(2026, 10, 5), estado="propuesta")))
    [r] = de("K5", inst, 1)
    assert (r.valores["reglas"], r.clave) == (["F3"], "aplicacion:1")
    assert de("K5", inst, 2) == []           # se pago el dia despues; la propuesta no cuenta
    regla = catalogo.regla("K5")
    assert (regla.severidad, regla.anulable, regla.pegajosa) == ("retencion", False, True)


# ------------------------------------------------------------ K6

def test_k6_la_cadena_de_extractos() -> None:
    sigue = (extracto(1, 100, 0, 1000, date(2026, 9, 1), date(2026, 9, 30)),
             extracto(2, 101, 1000, 500, date(2026, 10, 1), date(2026, 10, 13)))
    assert roturas(sigue) == {}
    hueco = (*sigue, extracto(3, 103, 500, 400, date(2026, 10, 14), date(2026, 10, 14)))
    [(roto, motivo)] = roturas(hueco)[PROPIA]
    assert roto.id == 3 and "103" in motivo
    saldo_malo = (*sigue, extracto(3, 102, 600, 400, date(2026, 10, 14), date(2026, 10, 14)))
    assert "abre con 6,00" in roturas(saldo_malo)[PROPIA][0][1]
    # Volver a 1 con el ano, si los saldos siguen, no rompe nada; un CSV sin saldos no cuenta.
    ano = (extracto(1, 365, 0, 1000, date(2026, 12, 31), date(2026, 12, 31)),
           extracto(2, 1, 1000, 900, date(2027, 1, 1), date(2027, 1, 1)),
           extracto(3, None, None, None, date(2027, 1, 2), date(2027, 1, 5), con_saldos=False))
    assert roturas(ano) == {}


def test_k6_un_numero_repetido_o_cero_lo_deciden_los_saldos() -> None:
    """Paginas de un MT940 (el mismo :28C:) y el 00000 de ING: no rompen si los saldos
    encadenan; si no encadenan, si (revision del paso 7)."""
    paginas = (extracto(1, 101, 10000, 9900, date(2026, 10, 12), date(2026, 10, 12)),
               extracto(2, 101, 9900, 9800, date(2026, 10, 12), date(2026, 10, 12)),
               extracto(3, 102, 9800, 9700, date(2026, 10, 13), date(2026, 10, 13)))
    assert roturas(paginas) == {}
    ceros = (extracto(1, 0, 10000, 9900, date(2026, 10, 12), date(2026, 10, 12)),
             extracto(2, 0, 9900, 9800, date(2026, 10, 13), date(2026, 10, 13)))
    assert roturas(ceros) == {}
    [(roto, motivo)] = roturas((*ceros, extracto(3, 0, 5000, 4900, date(2026, 10, 14),
                                                 date(2026, 10, 14))))[PROPIA]
    assert roto.id == 3 and "abre con" in motivo and "numero" not in motivo
    # Un salto de verdad sigue siendo una rotura aunque los saldos encadenen.
    assert roturas((*paginas, extracto(4, 104, 9700, 9700, date(2026, 10, 14),
                                       date(2026, 10, 14))))[PROPIA][0][0].id == 4


def test_k6_bloquea_el_extracto_y_lo_pagado_desde_la_rotura() -> None:
    extractos = (extracto(1, 100, 0, 100000, date(2026, 9, 1), date(2026, 9, 30), importacion=7),
                 extracto(2, 102, 100000, 58860, date(2026, 10, 1), date(2026, 10, 13),
                          importacion=8),
                 extracto(3, None, None, None, date(2026, 10, 1), date(2026, 10, 13),
                          cuenta=OTRA_PROPIA, con_saldos=False, importacion=9))
    movs = (movimiento(1, -41140, date(2026, 9, 20), extracto=1),
            movimiento(2, -41140, date(2026, 10, 12), extracto=2),
            movimiento(3, -41140, date(2026, 10, 12), extracto=3, cuenta=OTRA_PROPIA))
    inst = banco(compra(1), compra(2), compra(3), movimientos=movs, extractos=extractos,
                 aplicaciones=(aplicacion(1, 1, 41140), aplicacion(2, 2, 41140),
                               aplicacion(3, 3, 41140)))
    k6 = resultados("K6", inst)
    assert {(r.tabla, r.fila_id, r.clave) for r in k6} == {
        ("importacion", 8, "extracto:2"), ("factura", 2, "")}
    assert catalogo.regla("K6").severidad == "bloqueo"
    assert catalogo.nunca_anulable("K6", "entrante")


# ------------------------------------------------------------ K7 y K8

def test_k7_un_movimiento_sin_casar_pasados_los_dias() -> None:
    movs = (movimiento(1, -41140, date(2026, 10, 1)),
            movimiento(2, -41140, date(2026, 10, 10)),               # todavia no
            movimiento(3, -41140, date(2026, 10, 1)),                # casado del todo
            movimiento(4, -100, date(2026, 10, 1), iban=BELASTINGDIENST),
            movimiento(5, 10000, date(2026, 10, 1), iban=OTRA_PROPIA),    # traspaso propio
            movimiento(6, -41140, date(2026, 10, 1)),                # solo propuesto
            movimiento(7, None, date(2026, 10, 1), moneda="USD"))
    inst = banco(compra(1), compra(2), movimientos=movs, aplicaciones=(
        aplicacion(3, 1, 41140, movimiento_id=3),
        aplicacion(6, 2, 41140, movimiento_id=6, metodo="propuesta", estado="propuesta")))
    assert sorted(r.fila_id for r in resultados("K7", inst)) == [1, 6]
    [r] = de("K7", inst, 1)
    assert r.tabla == "movimiento" and r.valores["sin_casar_cent"] == -41140


def test_k8_el_banco_y_exact_no_dicen_lo_mismo() -> None:
    inst = banco(compra(1), compra(2), aplicaciones=(
        aplicacion(1, 1, 41140), aplicacion(2, 1, 30000, fuente="exact"),
        aplicacion(3, 2, 41140), aplicacion(4, 2, 41140, fuente="exact")))
    [r] = resultados("K8", inst)
    assert (r.fila_id, r.valores) == (1, {"banco_cent": 41140, "exact_cent": 30000})


# ------------------------------------------------------------ F7 y X1

def test_f7_un_cargo_a_un_proveedor_a_una_cuenta_que_no_es_pagable() -> None:
    movs = (movimiento(1, -41140, iban=K_RECHAZADA),             # casado, a una rechazada
            movimiento(2, -41140, iban=K_HEREDADA),              # a la pagable: bien
            movimiento(3, -41140, iban=SIN_REGISTRAR),           # casado, a una que no esta
            movimiento(4, -500, iban=K_RECHAZADA),               # sin casar, pero es suya
            movimiento(5, -100, iban=BELASTINGDIENST),
            movimiento(6, -41140, iban=None))
    inst = banco(compra(1), compra(2), compra(3), compra(6), movimientos=movs, aplicaciones=(
        aplicacion(1, 1, 41140), aplicacion(2, 2, 41140),
        aplicacion(3, 3, 41140, metodo="propuesta", estado="propuesta"),
        aplicacion(6, 6, 41140)))
    por_movimiento = {r.fila_id: r for r in resultados("F7", inst)}
    assert set(por_movimiento) == {1, 3, 4, 6}
    assert por_movimiento[1].resultado == "fallo" and "rechazada" in por_movimiento[1].detalle
    assert "no está registrada" in por_movimiento[3].detalle
    assert por_movimiento[6].resultado == "sin_datos"
    assert ("factura", 1) in {(o.tabla, o.fila_id) for o in por_movimiento[1].objetivos}
    regla = catalogo.regla("F7")
    assert (regla.severidad, regla.pegajosa, regla.ambito) == ("bloqueo", True, "movimiento")


def test_x1_un_movimiento_en_otra_moneda() -> None:
    inst = banco(compra(1), movimientos=(movimiento(1, None, moneda="USD"),
                                         movimiento(2, -100)))
    [r] = [r for r in resultados("X1", inst) if r.tabla == "movimiento"]
    assert (r.fila_id, r.resultado, r.valores) == (1, "fallo", {"moneda": "USD"})


# ------------------------------------------------------------ revision del paso 7

def test_k4_la_ventana_se_cuenta_desde_el_primer_cargo() -> None:
    """Tres cargos cada 20 dias no son un grupo de tres: el tercero esta a 40 del primero."""
    movs = (movimiento(1, -41140, date(2026, 8, 1)), movimiento(2, -41140, date(2026, 8, 21)),
            movimiento(3, -41140, date(2026, 9, 10)))
    k4 = [r for r in resultados("K4", banco(compra(1), movimientos=movs)) if r.tabla == "movimiento"]
    assert sorted(r.fila_id for r in k4) == [1, 2]


def test_k4_dos_cargos_al_mismo_proveedor_en_dos_cuentas_suyas() -> None:
    """La misma parte, no la misma cuenta: K_HEREDADA y K_RECHAZADA son las dos de Van Dijk."""
    movs = (movimiento(1, -41140, date(2026, 10, 5), iban=K_HEREDADA),
            movimiento(2, -41140, date(2026, 10, 9), iban=K_RECHAZADA),
            movimiento(3, -41140, date(2026, 10, 9), iban=SIN_REGISTRAR, referencia="OTRA"),
            movimiento(4, -41140, date(2026, 10, 10), iban="NL53RABO0333444555",
                       referencia="OTRA"))
    k4 = [r for r in resultados("K4", banco(compra(1), movimientos=movs)) if r.tabla == "movimiento"]
    assert sorted(r.fila_id for r in k4) == [1, 2]
    assert k4[0].valores["parte"] == "proveedor:1"
    assert k4[0].valores["ibans"] == sorted([K_HEREDADA, K_RECHAZADA])


def test_k5_un_bloqueo_desaparecido_ya_no_es_bloqueada() -> None:
    """Desaparecido pone la factura en Atencion (prioridad.py), no en Bloqueada: un pago
    despues no es K5; si el hallazgo se reabre, vuelve a contar."""
    tramos = tramos_bloqueados([
        (1, "abierto", date(2026, 10, 1)), (1, "desaparecido", date(2026, 10, 3)),
        (1, "abierto", date(2026, 10, 8)), (2, "abierto", date(2026, 10, 2)),
        (2, "aceptado", date(2026, 10, 4))])
    assert tramos == {1: [(date(2026, 10, 1), date(2026, 10, 3)), (date(2026, 10, 8), None)],
                      2: [(date(2026, 10, 2), date(2026, 10, 4))]}
    bloqueos = tuple(Bloqueo(1, "F3", desde, hasta) for desde, hasta in tramos[1])
    inst = banco(compra(1), bloqueos=bloqueos, aplicaciones=(
        aplicacion(1, 1, 100, fecha=date(2026, 10, 5)),
        aplicacion(2, 1, 100, fecha=date(2026, 10, 9))))
    assert [r.valores["fecha_pago"] for r in de("K5", inst, 1)] == ["2026-10-09"]


def test_f7_mira_si_la_cuenta_era_pagable_el_dia_del_cargo() -> None:
    """Un cargo a una cuenta pagable ese dia no es F7 porque despues saliera de Exact; uno de
    despues si. Un rechazo de una persona cuenta aunque llegue despues (revision del paso 7)."""
    heredada = cuenta(1, K_HEREDADA, evento(1, "baseline", importacion=1),
                      evento(2, "visto_en_exact", importacion=1),
                      evento(3, "ausente_en_exact", "2026-10-12T08:00:00+00:00", importacion=2))
    rechazada = cuenta(4, K_RECHAZADA, evento(10, "baseline", importacion=1),
                       evento(11, "visto_en_exact", importacion=1),
                       persona_decide(12, "rechazada", "2026-10-12T09:00:00+00:00"))
    movs = (movimiento(1, -41140, date(2026, 9, 10), iban=K_HEREDADA),
            movimiento(2, -41140, date(2026, 10, 13), iban=K_HEREDADA),
            movimiento(3, -41140, date(2026, 8, 1), iban=K_HEREDADA),     # antes del registro
            movimiento(4, -41140, date(2026, 9, 10), iban=K_RECHAZADA))
    inst = dataclasses.replace(
        banco(compra(1), compra(2), compra(3), compra(4), movimientos=movs, aplicaciones=(
            aplicacion(1, 1, 41140), aplicacion(2, 2, 41140), aplicacion(3, 3, 41140),
            aplicacion(4, 4, 41140))),
        cuentas=(heredada, rechazada))
    por_movimiento = {r.fila_id: r for r in resultados("F7", inst)}
    assert set(por_movimiento) == {2, 4}
    assert "con un cambio sin verificar" in por_movimiento[2].detalle
    assert "rechazada" in por_movimiento[4].detalle


def test_k1_y_k3_no_dicen_sin_pagar_sobre_una_rotura_de_la_cadena() -> None:
    """Falta el extracto 101: lo vencido o pagado a mano esos dias puede estar en el que
    falta (K6). Y la cobertura es por cuenta (revision del paso 7)."""
    rota = (extracto(1, 100, 0, 100000, date(2026, 9, 1), date(2026, 9, 30)),
            extracto(2, 102, 100000, 58860, date(2026, 10, 5), date(2026, 10, 13)))
    manual = aplicacion(1, 2, 41140, fuente="manual", metodo="manual", fecha=date(2026, 10, 2))
    vencida = compra(1, vencimiento=VENCIDA, fecha_factura=date(2026, 9, 15))
    inst = banco(vencida, compra(2), extractos=rota, aplicaciones=(manual,))
    [k1] = de("K1", inst, 1)
    assert k1.resultado == "sin_datos"
    [k3] = de("K3", inst, 2)
    assert k3.resultado == "sin_datos" and "K6" in k3.detalle
    # Con la cadena entera, si se sabe.
    sigue = (extracto(1, 100, 0, 100000, date(2026, 9, 1), date(2026, 9, 30)),
             extracto(2, 101, 100000, 58860, date(2026, 10, 1), date(2026, 10, 13)))
    entera = banco(vencida, compra(2), extractos=sigue, aplicaciones=(manual,))
    assert [r.resultado for r in de("K1", entera, 1)] == ["fallo"]
    assert [r.resultado for r in de("K3", entera, 2)] == ["fallo"]
    # Otra cuenta propia con extractos solo desde octubre: lo de septiembre no se sabe.
    otra = (*sigue, extracto(3, 1, 0, 0, date(2026, 10, 5), date(2026, 10, 13),
                             cuenta=OTRA_PROPIA))
    assert [r.resultado for r in de("K1", banco(vencida, extractos=otra), 1)] == ["sin_datos"]


def test_k8_exact_dice_cero_y_el_banco_pagado() -> None:
    """Abierta en Exact y pagada en el banco: K8, comparando con lo que el banco habia pagado
    el dia de la foto de Exact (revision del paso 7)."""
    pagos = (aplicacion(1, 1, 41140, fecha=date(2026, 10, 12)),
             aplicacion(2, 2, 41140, fecha=date(2026, 10, 12)))
    inst = dataclasses.replace(
        banco(compra(1), compra(2), aplicaciones=pagos),
        exact_pagado=(PagadoExact(1, 0, date(2026, 10, 13)),        # despues del pago
                      PagadoExact(2, 0, date(2026, 10, 11))))       # antes: no lo sabia
    [r] = resultados("K8", inst)
    assert (r.fila_id, r.valores) == (1, {"banco_cent": 41140, "exact_cent": 0})


# ------------------------------------------------------------ para la prueba de pureza

def escenarios() -> list[Instantanea]:
    """Instantaneas que pasan por cada rama de las reglas del paso 7 (test_pureza_reglas)."""
    movs = (movimiento(1, -41140, date(2026, 10, 1)), movimiento(2, -41140, date(2026, 10, 12)),
            movimiento(3, -41140, iban=K_RECHAZADA), movimiento(4, -500, iban=K_RECHAZADA),
            movimiento(5, -100, iban=BELASTINGDIENST), movimiento(6, -41140, iban=None),
            movimiento(7, None, moneda="USD"), movimiento(8, 1000, date(2026, 10, 1)),
            movimiento(9, -41140, date(2026, 9, 20), extracto=1))
    apps = (aplicacion(1, 1, 41140, movimiento_id=1), aplicacion(2, 1, 41140, movimiento_id=2),
            aplicacion(3, 2, 20000, movimiento_id=3),
            aplicacion(4, 3, 41140, fuente="manual", metodo="manual", fecha=date(2026, 10, 1)),
            aplicacion(5, 4, 30000, fuente="exact", movimiento_id=None),
            aplicacion(6, 4, 41140, movimiento_id=6),
            aplicacion(7, 5, 100, metodo="propuesta", estado="propuesta", movimiento_id=9),
            aplicacion(8, 7, 41140, movimiento_id=9))
    facturas = (compra(1, vencimiento=VENCIDA), compra(2, vencimiento=VENCIDA),
                compra(3), compra(4), compra(5, total_cent=None, moneda="USD"),
                compra(6, vencimiento=VENCIDA, fecha_factura=date(2026, 8, 1)),
                compra(7), venta(8, vencimiento=date(2026, 9, 1)),
                compra(9, anulada=True))
    rota = (*EXTRACTOS, extracto(3, 103, 0, 10, date(2026, 10, 14), date(2026, 10, 14)))
    bloqueos = (Bloqueo(1, "F3", date(2026, 10, 10), None),
                Bloqueo(2, "B2", date(2026, 10, 1), date(2026, 10, 5)))
    con_exact = (*lotes(), lote(6, "exact", "pagos_exact", exportado=date(2026, 10, 13)))
    return [
        banco(*facturas, movimientos=movs, aplicaciones=apps, extractos=rota,
              bloqueos=bloqueos),
        banco(*facturas, movimientos=movs, aplicaciones=apps, con_lotes=con_exact),
        banco(*facturas, movimientos=movs, aplicaciones=apps, extractos=(),
              con_lotes=lotes()[:4]),
        dataclasses.replace(banco(*facturas, movimientos=movs, aplicaciones=apps),
                            cuentas=(), lotes=()),
        # Exact dice cero de la 4 y lo que pago la 1 (K8 con la foto de Exact).
        dataclasses.replace(banco(*facturas, movimientos=movs, aplicaciones=apps),
                            exact_pagado=(PagadoExact(4, 0, date(2026, 10, 13)),
                                          PagadoExact(1, 82280, date(2026, 10, 13)))),
    ]
