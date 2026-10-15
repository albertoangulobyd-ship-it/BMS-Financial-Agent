"""Las reglas del paso 8 (R1-R5, V7, F10, M3) y lo que mueven las relaciones, sin base.

Las instantaneas llevan, ademas de lo de los pasos anteriores, las
relaciones confirmadas (`relaciones`), las propuestas (`propuestas`) y las
facturas que nombra cada documento (`citas`). Lo que mueven las confirmadas
(lo acreditado, la que sustituye) lo pone `con_efectos` como lo pone
instantanea.construir. Los constructores de aqui los usa tambien
test_pureza_reglas.py.
"""

from __future__ import annotations

import dataclasses
from datetime import date

from test_reglas import HOY, factura, linea
from test_reglas_paso7 import OTRA_PROPIA, PROPIA, aplicacion

from bms_agent.reglas import catalogo
from bms_agent.reglas.base import Cita, Factura, Instantanea, Politica, Relacion, fuera_de_juego
from bms_agent.reglas.pagos import saldo
from bms_agent.reglas.relaciones import SIN_EFECTO, efectos

POLITICA = Politica(empresa_ibans=(OTRA_PROPIA, PROPIA))


# ------------------------------------------------------------ constructores

def venta(id_: int, **cambios) -> Factura:
    """Una venta al cliente 3 (Havenbedrijf), resuelta, sin IBAN impreso."""
    valores = dict(sentido="saliente", cliente_id=3, parte="cliente:3", proveedor_id=None,
                   parte_nombre="Havenbedrijf", emisor_nombre_doc="BM Support BV",
                   emisor_btw_doc=None, emisor_kvk_doc=None, receptor_nombre_doc="Havenbedrijf",
                   receptor_btw_doc="NL009999999B01", iban_doc=None)
    valores.update(cambios)
    return factura(id_, **valores)


def abono(id_: int, total: int = -41140, **cambios) -> Factura:
    valores = dict(tipo="nota_credito", base_cent=total * 34000 // 41140,
                   iva_cent=total - total * 34000 // 41140, total_cent=total,
                   lineas=(linea(id_ * 10, importe_cent=total * 34000 // 41140),))
    valores.update(cambios)
    return factura(id_, **valores)


def con_efectos(facturas, relaciones=(), aplicaciones=(), tolerancia: int = 0) -> list[Factura]:
    """Las facturas con lo que mueven las relaciones confirmadas y lo pagado (como construir)."""
    totales = {f.id: f.total_cent for f in facturas}
    movido = efectos(relaciones, totales)
    salida = []
    for f in facturas:
        e = movido.get(f.id, SIN_EFECTO)
        propias = [a for a in aplicaciones if a.factura_id == f.id]
        f = dataclasses.replace(f, acreditado_cent=e.acreditado_cent,
                                sustituida_por=e.sustituida_por)
        if propias or e.acreditado_cent:
            s = saldo(f.total_cent, propias, tolerancia, e.acreditado_cent)
            f = dataclasses.replace(f, pagado_cent=s.pagado_cent, fuente_pago=s.fuente,
                                    pagada=s.pagada)
        salida.append(f)
    return salida


def inst(*facturas: Factura, relaciones=(), propuestas=(), citas=(), aplicaciones=(),
         politica: Politica | None = None) -> Instantanea:
    return Instantanea(hoy=HOY, politica=politica or POLITICA,
                       facturas=tuple(con_efectos(facturas, relaciones, aplicaciones)),
                       relaciones=tuple(relaciones), propuestas=tuple(propuestas),
                       citas=tuple(citas), aplicaciones=tuple(aplicaciones))


def resultados(regla_id: str, instantanea: Instantanea) -> list:
    return list(catalogo.regla(regla_id).evaluar(instantanea))


def de(regla_id: str, instantanea: Instantanea, fila_id: int) -> list:
    return [r for r in resultados(regla_id, instantanea) if r.fila_id == fila_id]


# ------------------------------------------------------------ lo que mueven

def test_un_abono_entero_acredita_y_uno_parcial_baja_lo_pendiente() -> None:
    totales = {1: 41140, 2: -41140, 3: -10000, 4: 41140}
    entero = efectos([Relacion(2, 1, "acredita")], totales)
    assert entero[1].acreditado_cent == 41140 and entero[2].acreditado_cent == -41140
    parcial = efectos([Relacion(3, 4, "acredita")], totales)
    assert parcial[4].acreditado_cent == 10000
    # Con importe, el de la relacion (en el signo de la original).
    assert efectos([Relacion(2, 1, "acredita", importe_cent=5000)], totales)[1] == (
        5000, None, False)
    assert efectos([Relacion(2, 1, "anula")], totales)[1].anulada_por_abono
    # Sustituida: por la de id menor si fueran varias. Relacionada: nada.
    assert efectos([Relacion(9, 1, "sustituye"), Relacion(7, 1, "corrige")],
                   totales)[1].sustituida_por == 7
    assert efectos([Relacion(4, 1, "relacionada")], totales) == {}
    # El saldo con lo acreditado: saldada (sin pago) o con lo que queda.
    acreditada = saldo(41140, [], 0, 41140)
    assert acreditada.pagada and acreditada.fuente is None and acreditada.pendiente_cent == 0
    assert saldo(41140, [], 0, 10000).pendiente_cent == 31140
    assert not saldo(41140, [], 0, 10000).pagada


def test_la_sustituida_sale_de_juego_y_de_las_reglas() -> None:
    [original, nueva] = con_efectos([factura(1), factura(2, numero_norm="NUEVA")],
                                    [Relacion(2, 1, "sustituye")])
    assert fuera_de_juego(original) and not fuera_de_juego(nueva)
    # B4 no ve el par: la original ya no cuenta (la puerta: B4 no salta con un par confirmado).
    pisadas = inst(factura(1), factura(2, numero_norm="OTRA", total_cent=50000),
                   relaciones=[Relacion(2, 1, "corrige")])
    assert not [r for r in resultados("B4", pisadas) if r.resultado == "fallo"]
    sin_relacion = inst(factura(1), factura(2, numero_norm="OTRA", total_cent=50000))
    assert [r for r in resultados("B4", sin_relacion) if r.resultado == "fallo"]


# ------------------------------------------------------------ R1

def test_r1_un_abono_que_nombra_una_factura_que_no_esta() -> None:
    nota = abono(5)
    citas = [Cita(1, 5, "2026-999", "2026999", "credits")]
    [r] = de("R1", inst(factura(1), nota, citas=citas), 5)
    assert (r.resultado, r.clave, r.valores["encontradas"]) == ("fallo", "cita:1", [])
    # La encuentra (misma contraparte, mismo numero): nada.
    assert not de("R1", inst(factura(1), nota, citas=[Cita(1, 5, "2026-001", "2026001",
                                                           "credits")]), 5)
    # Repetida: no se sabe cual.
    repetidas = inst(factura(1), factura(2, numero_norm="2026001"), nota,
                     citas=[Cita(1, 5, "2026-001", "2026001", "credits")])
    [r] = de("R1", repetidas, 5)
    assert r.valores["encontradas"] == [1, 2]
    # Sin numero legible o sin contraparte: sin datos.
    [r] = de("R1", inst(nota, citas=[Cita(2, 5, None, None, "credits")]), 5)
    assert r.resultado == "sin_datos"
    sin_parte = abono(6, parte=None)
    [r] = de("R1", inst(sin_parte, citas=[Cita(3, 6, "X", "X", "credits")]), 6)
    assert r.resultado == "sin_datos"
    # Una factura que solo menciona otra no pide nada; una que la sustituye si.
    assert not de("R1", inst(factura(7), citas=[Cita(4, 7, "Y", "Y", "refers_to")]), 7)
    [r] = de("R1", inst(factura(7), citas=[Cita(4, 7, "Y", "Y", "replaces")]), 7)
    assert r.resultado == "fallo"


# ------------------------------------------------------------ R2

def test_r2_los_abonos_no_le_quitan_a_una_factura_mas_de_lo_que_vale() -> None:
    dos = inst(factura(1), abono(2), abono(3, -10000),
               relaciones=[Relacion(2, 1, "acredita"), Relacion(3, 1, "acredita")])
    [r] = de("R2", dos, 1)
    assert (r.resultado, r.clave, r.valores["acreditado_cent"]) == ("fallo", "acreditado",
                                                                     51140)
    # Un abono aplicado a dos facturas por mas de lo que vale.
    gastado = inst(factura(1), factura(4, numero_norm="X4"), abono(2, -10000),
                   relaciones=[Relacion(2, 1, "acredita", importe_cent=8000),
                               Relacion(2, 4, "acredita", importe_cent=8000)])
    [r] = de("R2", gastado, 2)
    assert (r.clave, r.valores["aplicado_cent"]) == ("aplicado", 16000)
    assert not de("R2", inst(factura(1), abono(2), relaciones=[Relacion(2, 1, "acredita")]), 1)
    [r] = de("R2", inst(factura(1, total_cent=None), abono(2),
                        relaciones=[Relacion(2, 1, "acredita")]), 1)
    assert r.resultado == "sin_datos"


# ------------------------------------------------------------ R3

def test_r3_la_original_y_la_que_la_sustituye_no_se_pagan_las_dos() -> None:
    relacion = [Relacion(2, 1, "sustituye")]
    pendientes = inst(factura(1), factura(2, numero_norm="N2"), relaciones=relacion)
    [a, b] = resultados("R3", pendientes)
    assert {a.fila_id, b.fila_id} == {1, 2} and a.grupo == "par:1-2"
    assert catalogo.regla("R3").severidad == "bloqueo"
    # Anulada la original, ya no.
    assert not resultados("R3", inst(factura(1, anulada=True), factura(2, numero_norm="N2"),
                                     relaciones=relacion))
    # Las dos pagadas.
    pagos = [aplicacion(1, 1, 41140), aplicacion(2, 2, 41140)]
    assert len(resultados("R3", inst(factura(1), factura(2, numero_norm="N2"),
                                     relaciones=relacion, aplicaciones=pagos))) == 2
    # Una pagada y la otra no: lo normal (se pago la nueva).
    assert not resultados("R3", inst(factura(1), factura(2, numero_norm="N2"),
                                     relaciones=relacion, aplicaciones=pagos[1:]))


# ------------------------------------------------------------ R4 y R5

def test_r4_un_abono_sin_relacion_confirmada_y_r5_lo_propuesto_espera() -> None:
    sin = inst(factura(1), abono(2))
    [r] = de("R4", sin, 2)
    assert (r.resultado, r.severidad or catalogo.regla("R4").severidad) == ("fallo", "aviso")
    con = inst(factura(1), abono(2), relaciones=[Relacion(2, 1, "acredita")])
    assert not de("R4", con, 2)
    # Lo propuesto no cuenta para R4 (no mueve nada) y es R5 en las dos facturas.
    propuesta = Relacion(2, 1, "acredita", id=7, fuente="exact")
    pendiente = inst(factura(1), abono(2), propuestas=[propuesta])
    assert de("R4", pendiente, 2)
    r5 = resultados("R5", pendiente)
    assert {r.fila_id for r in r5} == {1, 2} and {r.grupo for r in r5} == {"relacion:7"}
    assert "Exact propone" in r5[0].detalle
    # No mueve nada: el saldo de la original no cambia.
    assert pendiente.facturas[0].acreditado_cent == 0
    # Con el origen fuera de juego, no se pide nada.
    assert not resultados("R5", inst(factura(1), abono(2, anulada=True),
                                     propuestas=[propuesta]))


# ------------------------------------------------------------ V7

def test_v7_facturar_dos_veces_a_un_cliente() -> None:
    dos = inst(venta(1, numero_norm="V1"), venta(2, numero_norm="V1"))
    fallos = [r for r in resultados("V7", dos) if r.resultado == "fallo"]
    assert {r.fila_id for r in fallos} == {1, 2} and fallos[0].valores["caso"] == "numero"
    mismo_importe = inst(venta(1, numero_norm="V1"),
                         venta(2, numero_norm="V2", fecha_factura=date(2026, 9, 20)))
    fallos = [r for r in resultados("V7", mismo_importe) if r.resultado == "fallo"]
    assert fallos and fallos[0].valores["caso"] == "importe"
    # Explicado por una relacion confirmada entre las dos.
    explicado = inst(venta(1, numero_norm="V1"),
                     venta(2, numero_norm="V2", fecha_factura=date(2026, 9, 20)),
                     relaciones=[Relacion(2, 1, "corrige")])
    assert not [r for r in resultados("V7", explicado) if r.resultado == "fallo"]
    # Sin cliente: sin datos. Las compras son de B2 y B3, que en las ventas no aplican.
    [r] = resultados("V7", inst(venta(1, parte=None)))
    assert r.resultado == "sin_datos"
    assert not resultados("V7", inst(factura(1), factura(2, numero_norm="2026001")))
    assert {r.resultado for r in resultados("B2", dos)} == {"no_aplica"}
    assert {r.resultado for r in resultados("B3", dos)} == {"no_aplica"}


# ------------------------------------------------------------ F10

def test_f10_una_venta_que_lleva_un_iban_que_no_es_de_la_empresa() -> None:
    [r] = resultados("F10", inst(venta(1, iban_doc="NL02 ABNA 0123 4567 89")))
    assert (r.resultado, r.valores["iban"]) == ("fallo", "NL02ABNA0123456789")
    assert not resultados("F10", inst(venta(1, iban_doc=PROPIA)))
    assert not resultados("F10", inst(venta(1)))
    [r] = resultados("F10", inst(venta(1, iban_doc=PROPIA), politica=Politica()))
    assert r.resultado == "sin_datos"
    # Las compras llevan el IBAN del proveedor: no son de F10.
    assert not resultados("F10", inst(factura(1)))


# ------------------------------------------------------------ M3

def test_m3_la_venta_de_exact_y_su_pdf_no_dicen_lo_mismo() -> None:
    exact = venta(1, origen="exact")
    copia = venta(2, numero_norm=exact.numero_norm, fusionada_en_id=1, total_cent=41150)
    fallos = resultados("M3", inst(exact, copia))
    assert {r.fila_id for r in fallos} == {1, 2} and fallos[0].grupo == "copia:2"
    assert fallos[0].valores["distintos"] == {"total_cent": [41140, 41150]}
    # Igual: nada. Fusionada en una que no es de Exact: no es su copia.
    assert not resultados("M3", inst(exact, dataclasses.replace(copia, total_cent=41140)))
    assert not resultados("M3", inst(venta(1), copia))
    # Con el mismo numero y sin unir (el cliente del PDF es otro): tambien.
    suelta = venta(3, numero_norm=exact.numero_norm, parte="cliente:9")
    fallos = resultados("M3", inst(exact, suelta))
    assert fallos and fallos[0].valores["distintos"] == {"parte": ["cliente:3", "cliente:9"]}


def test_a8_no_mira_el_emisor_de_una_venta_de_exact() -> None:
    """Exact no imprime emisor: una venta suya no esta mal encaminada."""
    assert not resultados("A8", inst(venta(1, origen="exact", emisor_nombre_doc=None)))
    assert resultados("A8", inst(venta(1, emisor_nombre_doc="Van Dijk BV",
                                       emisor_btw_doc="NL001234567B01")))


# ------------------------------------------------------------ escenarios de pureza

def escenarios() -> list[Instantanea]:
    """Instantaneas que pasan por cada rama de las reglas del paso 8 (test_pureza_reglas)."""
    exact = venta(1, origen="exact")
    copia = venta(2, numero_norm=exact.numero_norm, fusionada_en_id=1, total_cent=41150)
    suelta = venta(3, numero_norm=exact.numero_norm, parte="cliente:9")
    dobles = [venta(4, numero_norm="V4"), venta(5, numero_norm="V4"),
              venta(6, numero_norm="V6", fecha_factura=date(2026, 9, 20), periodo_inicio=None,
                    periodo_fin=None,
                    lineas=(linea(60, fecha_inicio=date(2026, 9, 7),
                                  fecha_fin=date(2026, 9, 13)),
                            linea(61, fecha_trabajo=date(2026, 9, 8)))),
              venta(7, parte=None, iban_doc="NL02 ABNA 0123 4567 89")]
    compras = [factura(10), abono(11), abono(12, -10000), factura(13, numero_norm="N13"),
               abono(14, parte=None), factura(15, total_cent=None, numero_norm="N15"),
               abono(16)]
    relaciones = [Relacion(11, 10, "acredita", id=1), Relacion(12, 10, "acredita", id=2),
                  Relacion(13, 10, "sustituye", id=3), Relacion(16, 15, "acredita", id=4)]
    propuestas = [Relacion(14, 10, "acredita", id=5, fuente="extraccion"),
                  Relacion(16, 13, "acredita", id=6, fuente="exact")]
    citas = [Cita(1, 11, "2026-999", "2026999", "credits"), Cita(2, 12, None, None, "credits"),
             Cita(3, 14, "2026-010", "2026010", "credits"),
             Cita(4, 13, "2026-010", "2026010", "replaces"),
             Cita(5, 13, "Z", "Z", "refers_to")]
    return [
        inst(exact, copia, suelta, *dobles, *compras, relaciones=relaciones,
             propuestas=propuestas, citas=citas),
        inst(exact, copia, *dobles, politica=Politica()),
    ]
