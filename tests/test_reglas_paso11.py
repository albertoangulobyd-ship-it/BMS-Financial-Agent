"""Las reglas del paso 11 sin base: el IVA de cada factura y los trimestres presentados.

Las instantaneas llevan, ademas de lo de los pasos anteriores, los trimestres
del BTW ya presentados con lo que se declaro de cada factura (`periodos_btw`)
y los clientes con su marca de si se les puede facturar con IVA trasladado
(`verlegd_elegible`). Hoy es el 2026-10-14 (test_reglas.HOY): el tercer
trimestre de 2026 ya acabo. Puertas del paso 11 que viven aqui:

- una factura que llega tarde a un trimestre presentado da C4 (y tambien una
  que cambio despues o que ya no cuenta alli);
- un abono de un trimestre posterior no reabre el trimestre presentado;
- E0, E7 y el aviso del umbral de la KOR (E5).

Los constructores y `escenarios()` los usa tambien test_pureza_reglas.py.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest
from test_reglas import HOY, factura, linea
from test_reglas_paso8 import venta

from bms_agent.reglas import catalogo
from bms_agent.reglas.base import (
    FALLO,
    SIN_DATOS,
    Factura,
    Instantanea,
    Parte,
    PeriodoBtw,
    Politica,
    TramoIva,
)
from bms_agent.reglas.iva import (
    FUERA_UE,
    NACIONAL,
    UE,
    LineaIva,
    huella_de_factura,
    huella_iva,
    lineas_iva,
    pais_iva,
)

PRESENTADO = date(2026, 10, 10)


# ------------------------------------------------------------ constructores

def cliente(id_: int = 3, elegible: bool | None = None) -> Parte:
    """Un cliente del maestro con (o sin) la marca verlegd_elegible."""
    return Parte(id_, "cliente", f"Cliente {id_}", frozenset({f"cliente {id_}"}), None, None,
                 None, True, verlegd_elegible=elegible)


def kor(id_: int, fecha: date, base: int, proveedor: int = 7, **cambios) -> Factura:
    """Una compra sin IVA de un proveedor con KOR."""
    valores = dict(proveedor_id=proveedor, parte=f"proveedor:{proveedor}",
                   tratamiento_iva="kor", tipo_iva_pb=None, iva_cent=0, base_cent=base,
                   total_cent=base, fecha_factura=fecha, numero_norm=f"K{id_}",
                   lineas=(linea(id_ * 10, importe_cent=base),))
    valores.update(cambios)
    return factura(id_, **valores)


def presentado(*declaradas: Factura, ano: int = 2026, trimestre: int = 3,
               en: date = PRESENTADO) -> PeriodoBtw:
    """Un trimestre presentado con lo que se declaro de esas facturas (sus huellas de hoy)."""
    return PeriodoBtw(ano, trimestre, en,
                      tuple(sorted((f.id, huella_de_factura(f)) for f in declaradas)))


def inst(*facturas: Factura, clientes=(), periodos=(), politica: Politica | None = None,
         hoy: date = HOY) -> Instantanea:
    return Instantanea(hoy=hoy, politica=politica or Politica(), facturas=tuple(facturas),
                       clientes=tuple(clientes), periodos_btw=tuple(periodos))


def resultados(regla_id: str, instantanea: Instantanea) -> list:
    return list(catalogo.regla(regla_id).evaluar(instantanea))


def de(regla_id: str, instantanea: Instantanea, fila_id: int, tabla: str = "factura") -> list:
    return [r for r in resultados(regla_id, instantanea)
            if r.fila_id == fila_id and r.tabla == tabla]


# ------------------------------------------------------------ lineas de IVA y huella

def test_las_lineas_de_iva_son_el_desglose_o_la_cabecera() -> None:
    cabecera = factura(1)
    assert lineas_iva(cabecera) == (LineaIva("estandar", 2100, 34000, 7140),)
    mixta = factura(2, desglose=(TramoIva(21, 0, 5000, 0, "autoliquidacion"),
                                 TramoIva(20, 2100, 20000, 4200)))
    # En el orden del desglose (por id), con el tratamiento de la fila si lo tiene.
    assert lineas_iva(mixta) == (LineaIva("estandar", 2100, 20000, 4200),
                                 LineaIva("autoliquidacion", 0, 5000, 0))


@pytest.mark.parametrize("btw, pais", [
    (None, NACIONAL), ("", NACIONAL), ("NL001234567B01", NACIONAL), ("nl 0012.34567.b01", NACIONAL),
    ("DE123456789", UE), ("EL123456789", UE), ("BE0123456789", UE),
    ("GB123456789", FUERA_UE), ("CHE-123.456.789", FUERA_UE), ("123456789", NACIONAL),
])
def test_de_donde_es_la_contraparte_por_su_btw_id(btw, pais) -> None:
    assert pais_iva(btw) == pais


def test_la_huella_es_lo_declarado_y_no_la_fecha_ni_el_orden() -> None:
    a = factura(1, desglose=(TramoIva(10, 2100, 20000, 4200), TramoIva(11, 900, 10000, 900)))
    otro_orden = dataclasses.replace(a, desglose=(TramoIva(12, 900, 10000, 900),
                                                  TramoIva(13, 2100, 20000, 4200)))
    otro_dia = dataclasses.replace(a, fecha_factura=date(2026, 7, 1))
    assert huella_de_factura(a) == huella_de_factura(otro_orden) == huella_de_factura(otro_dia)
    assert huella_de_factura(a) != huella_de_factura(
        dataclasses.replace(a, desglose=(TramoIva(10, 2100, 20001, 4200),
                                         TramoIva(11, 900, 10000, 900))))
    assert huella_de_factura(factura(2)) != huella_de_factura(factura(2, tratamiento_iva="kor"))
    assert huella_de_factura(factura(2)) != huella_de_factura(venta(2))


def test_el_pais_solo_cuenta_en_la_huella_con_iva_trasladado() -> None:
    linea_ = [LineaIva("estandar", 2100, 100, 21)]
    assert huella_iva("entrante", NACIONAL, linea_) == huella_iva("entrante", UE, linea_)
    trasladada = [LineaIva("autoliquidacion", None, 100, None)]
    assert huella_iva("entrante", NACIONAL, trasladada) != huella_iva("entrante", UE, trasladada)


# ------------------------------------------------------------ E0

@pytest.mark.parametrize("cambios, faltan", [
    (dict(tratamiento_iva=None), None),
    (dict(tratamiento_iva="desconocido"), None),
    (dict(tipo_iva_pb=None), ["tipo_iva_pb"]),
    (dict(iva_cent=None), ["iva_cent"]),
    (dict(tipo_iva_pb=None, iva_cent=None), ["tipo_iva_pb", "iva_cent"]),
])
def test_e0_falta_el_tratamiento_el_tipo_o_la_cuota(cambios, faltan) -> None:
    [r] = de("E0", inst(factura(1, **cambios)), 1)
    assert r.resultado == FALLO
    if faltan is None:
        assert r.valores == {"tratamiento_iva": cambios["tratamiento_iva"]}
        assert [o.campo for o in r.objetivos] == ["tratamiento_iva"]
    else:
        assert r.valores == {"faltan": faltan}
        assert [o.campo for o in r.objetivos] == faltan


@pytest.mark.parametrize("cambios", [
    dict(),
    # El tipo en todas las lineas basta.
    dict(tipo_iva_pb=None, lineas=(linea(10, tipo_iva_pb=2100), linea(11, 2, tipo_iva_pb=900))),
    # Ilegible no es que falte (eso es Q2).
    dict(tipo_iva_pb=None, iva_cent=None, ilegibles=frozenset({"tipo_iva_pb", "iva_cent"})),
    # Sin IVA normal no hay tipo ni cuota que pedir.
    dict(tratamiento_iva="kor", tipo_iva_pb=None, iva_cent=None),
    dict(tratamiento_iva="autoliquidacion", tipo_iva_pb=None, iva_cent=None),
    # Una factura en otra moneda la mira X1, y una anulada no dice nada.
    dict(moneda="USD", tratamiento_iva=None),
    dict(anulada=True, tratamiento_iva=None),
])
def test_e0_no_dice_nada(cambios) -> None:
    assert de("E0", inst(factura(1, **cambios)), 1) == []


def test_e0_con_una_linea_sin_tipo_si_falta() -> None:
    f = factura(1, tipo_iva_pb=None, lineas=(linea(10, tipo_iva_pb=2100), linea(11, 2)))
    [r] = de("E0", inst(f), 1)
    assert r.valores == {"faltan": ["tipo_iva_pb"]}


def test_e0_mira_las_filas_con_iva_normal_del_desglose() -> None:
    completa = factura(1, desglose=(TramoIva(10, 2100, 20000, 4200),
                                    TramoIva(11, None, 5000, None, "autoliquidacion")))
    assert de("E0", inst(completa), 1) == []
    incompleta = factura(2, desglose=(TramoIva(20, 2100, 20000, None), TramoIva(21, 900, 1, 0),
                                      TramoIva(22, None, 100, 9)))
    [r] = de("E0", inst(incompleta), 2)
    assert r.valores == {"tramos": [[2100, 20000, None], [None, 100, 9]]}
    assert [(o.tabla, o.fila_id) for o in r.objetivos] == [("factura_iva", 20),
                                                           ("factura_iva", 22)]


# ------------------------------------------------------------ E7

def test_e7_un_tipo_que_no_es_de_la_lista() -> None:
    raro = factura(1, tipo_iva_pb=1900, iva_cent=6460)
    [r] = de("E7", inst(raro), 1)
    assert (r.resultado, r.clave, r.valores) == (FALLO, "tipo", {"tipos": [1900]})
    en_linea = factura(2, lineas=(linea(20, tipo_iva_pb=600),))
    assert [r.valores for r in de("E7", inst(en_linea), 2)] == [{"tipos": [600]}]
    for tipo in (0, 900, 2100):
        assert de("E7", inst(factura(3, tipo_iva_pb=tipo)), 3) == []
    # La lista es de la politica.
    politica = Politica(iva_tipos_habituales_pb=(0, 900, 1900, 2100))
    assert de("E7", inst(raro, politica=politica), 1) == []


@pytest.mark.parametrize("tratamiento, tipo", [("autoliquidacion", None), ("tipo_cero", 0),
                                               ("estandar", 0)])
def test_e7_una_venta_sin_iva_pide_un_cliente_marcado(tratamiento, tipo) -> None:
    v = venta(1, tratamiento_iva=tratamiento, tipo_iva_pb=tipo, iva_cent=0, total_cent=34000)
    assert de("E7", inst(v, clientes=[cliente(3, True)]), 1) == []
    for marca in (False, None):
        [r] = de("E7", inst(v, clientes=[cliente(3, marca)]), 1)
        assert (r.resultado, r.clave) == (FALLO, "tratamiento")
        assert r.valores == {"tratamiento_iva": tratamiento, "cliente_id": 3}
    # Un cliente que no esta en el maestro tampoco esta marcado.
    assert [r.clave for r in de("E7", inst(v), 1)] == ["tratamiento"]
    [r] = de("E7", inst(dataclasses.replace(v, cliente_id=None, parte=None)), 1)
    assert (r.resultado, r.clave) == (SIN_DATOS, "tratamiento")


def test_e7_no_mira_el_tratamiento_de_una_compra_ni_una_venta_con_iva() -> None:
    compra = factura(1, tratamiento_iva="autoliquidacion", tipo_iva_pb=None, iva_cent=0)
    assert de("E7", inst(compra), 1) == []
    assert de("E7", inst(venta(2), clientes=[cliente(3, False)]), 2) == []


# ------------------------------------------------------------ E5

def test_e5_avisa_al_llegar_al_porcentaje_del_umbral() -> None:
    debajo = [kor(1, date(2026, 2, 1), 1_000_000), kor(2, date(2026, 5, 1), 799_999)]
    assert resultados("E5", inst(*debajo)) == []
    llega = [*debajo, kor(3, date(2026, 6, 1), 1)]
    [r] = resultados("E5", inst(*llega))
    assert (r.tabla, r.fila_id, r.resultado, r.clave) == ("proveedor", 7, FALLO, "2026")
    assert r.valores == {"ano": 2026, "umbral_cent": 2_000_000, "aviso_pct": 90,
                         "pasado": False}
    assert [(o.tabla, o.fila_id, o.papel) for o in r.objetivos] == [("factura", 3,
                                                                       "relacionado")]
    # Pasado el umbral la evidencia cambia; la factura que cruzo el aviso sigue siendo la 3.
    [r] = resultados("E5", inst(*llega, kor(4, date(2026, 9, 1), 300_000)))
    assert r.valores["pasado"] is True
    assert r.objetivos[0].fila_id == 3


def test_e5_solo_el_ano_de_hoy_lo_que_cuenta_y_quien_sigue_con_kor() -> None:
    base = [kor(1, date(2026, 2, 1), 1_000_000), kor(2, date(2026, 5, 1), 800_000)]
    assert len(resultados("E5", inst(*base))) == 1
    # El ano pasado no cuenta.
    assert resultados("E5", inst(*base, hoy=date(2027, 1, 5))) == []
    # Un abono resta (y si vuelve a pasar, la relacionada es la que lo hizo pasar de nuevo);
    # una anulada o en otra moneda no cuenta.
    abono = kor(3, date(2026, 6, 1), -10, tipo="nota_credito")
    assert resultados("E5", inst(*base, abono)) == []
    [r] = resultados("E5", inst(*base, abono, kor(4, date(2026, 7, 1), 10)))
    assert r.objetivos[0].fila_id == 4
    for cambios in (dict(anulada=True), dict(moneda="USD")):
        assert resultados("E5", inst(base[0], kor(2, date(2026, 5, 1), 800_000,
                                                  **cambios))) == []
    # Si su ultima factura del ano ya trae IVA, dejo la KOR: no hay nada que avisar.
    con_iva = factura(5, proveedor_id=7, parte="proveedor:7", fecha_factura=date(2026, 9, 1))
    assert resultados("E5", inst(*base, con_iva)) == []
    # Otro proveedor lleva su propia cuenta; el porcentaje es de la politica.
    otro = [kor(6, date(2026, 3, 1), 1_000_000, proveedor=8)]
    politica = Politica(kor_aviso_pct=50)
    assert [r.fila_id for r in resultados("E5", inst(*base, *otro, politica=politica))] \
        == [7, 8]


# ------------------------------------------------------------ C4

def test_c4_sin_trimestres_presentados_no_dice_nada() -> None:
    assert resultados("C4", inst(factura(1))) == []


def test_c4_lo_declarado_tal_cual_no_dice_nada() -> None:
    f, v = factura(1), venta(2)
    assert resultados("C4", inst(f, v, periodos=[presentado(f, v)])) == []


def test_c4_una_factura_tardia_en_un_trimestre_presentado() -> None:
    """Puerta: una factura que llega despues de presentar su trimestre da C4."""
    declarada, tarde = factura(1), factura(2, numero_norm="X2", fecha_factura=date(2026, 8, 3))
    [r] = resultados("C4", inst(declarada, tarde, periodos=[presentado(declarada)]))
    assert (r.fila_id, r.resultado, r.clave) == (2, FALLO, "2026-T3")
    assert r.valores == {"trimestre": "2026-T3", "motivo": "tarde", "declarada": None,
                         "ahora": huella_de_factura(tarde)}
    assert "2026-10-10" in r.detalle
    regla = catalogo.regla("C4")
    assert (regla.severidad, regla.anulable) == ("aviso", True)


def test_c4_una_factura_que_cambio_o_ya_no_cuenta_alli() -> None:
    a, b, c, d = factura(1), factura(2), factura(3), factura(4)
    periodo = presentado(a, b, c, d)
    ahora = [dataclasses.replace(a, base_cent=34100, iva_cent=7161, total_cent=41261),
             dataclasses.replace(b, anulada=True),
             dataclasses.replace(c, fecha_factura=date(2026, 10, 2)),
             dataclasses.replace(d, sustituida_por=9)]
    salida = {r.fila_id: r.valores["motivo"]
              for r in resultados("C4", inst(*ahora, periodos=[periodo]))}
    assert salida == {1: "cambio", 2: "fuera", 3: "fuera", 4: "fuera"}
    # Cambiar el dia dentro del trimestre no cambia lo declarado.
    mismo = dataclasses.replace(a, fecha_factura=date(2026, 7, 1))
    assert resultados("C4", inst(mismo, periodos=[periodo])) == []


def test_c4_un_abono_de_un_trimestre_posterior_no_reabre_el_presentado() -> None:
    """Puerta: el abono cuenta en su trimestre; el presentado sigue siendo lo que era."""
    original = factura(1)
    abono = factura(2, tipo="nota_credito", fecha_factura=date(2026, 11, 3), base_cent=-34000,
                    iva_cent=-7140, total_cent=-41140)
    assert resultados("C4", inst(original, abono, periodos=[presentado(original)])) == []
    # Presentado tambien el cuarto trimestre sin el, el abono si llega tarde alli.
    cuarto = presentado(ano=2026, trimestre=4, en=date(2027, 1, 20))
    [r] = resultados("C4", inst(original, abono, periodos=[presentado(original), cuarto],
                                hoy=date(2027, 1, 25)))
    assert (r.fila_id, r.clave, r.valores["motivo"]) == (2, "2026-T4", "tarde")


def test_c4_no_mira_otra_moneda_ni_los_trimestres_sin_presentar() -> None:
    dolares = factura(1, moneda="USD")
    octubre = factura(2, fecha_factura=date(2026, 10, 5))
    sin_fecha = factura(3, fecha_factura=None)
    assert resultados("C4", inst(dolares, octubre, sin_fecha, periodos=[presentado()])) == []


# ------------------------------------------------------------ escenarios de pureza

def escenarios() -> list[Instantanea]:
    """Instantaneas que pasan por cada rama de las reglas del paso 11 (test_pureza_reglas)."""
    mixta = factura(100, desglose=(TramoIva(1000, 2100, 20000, 4200),
                                   TramoIva(1001, None, 5000, None, "autoliquidacion"),
                                   TramoIva(1002, 900, 1000, None)))
    traslado_ue = factura(101, tratamiento_iva="autoliquidacion", tipo_iva_pb=None, iva_cent=0,
                          emisor_btw_doc="DE123456789")
    ventas = [venta(102, tratamiento_iva="autoliquidacion", tipo_iva_pb=None, iva_cent=0),
              venta(103, tratamiento_iva="tipo_cero", tipo_iva_pb=0, iva_cent=0, cliente_id=4),
              venta(104, lineas=(linea(1040, tipo_iva_pb=0),)),
              venta(105, tratamiento_iva="tipo_cero", tipo_iva_pb=0, cliente_id=None,
                    parte=None)]
    cabeceras = [factura(106, tratamiento_iva=None), factura(107, tipo_iva_pb=None,
                                                             iva_cent=None),
                 factura(108, tipo_iva_pb=None, lineas=(linea(1080, tipo_iva_pb=2100),)),
                 factura(109, tipo_iva_pb=1900), factura(110, moneda="USD")]
    declaradas = [factura(111), traslado_ue, venta(112), venta(114)]
    tarde = factura(113, numero_norm="T113", fecha_factura=date(2026, 8, 1))
    cambiada = dataclasses.replace(declaradas[0], base_cent=1)
    movida = dataclasses.replace(declaradas[2], fecha_factura=date(2026, 10, 1))
    kor_ = [kor(120, date(2026, 1, 10), 1_500_000), kor(121, date(2026, 6, 1), 600_000),
            kor(122, date(2026, 7, 1), 100_000, proveedor=8), factura(123, proveedor_id=9),
            kor(124, date(2025, 12, 1), 1_900_000, proveedor=9)]
    return [
        inst(mixta, traslado_ue, *ventas, *cabeceras, *kor_,
             clientes=[cliente(3, True), cliente(4, False)]),
        inst(cambiada, traslado_ue, movida, declaradas[3], tarde, mixta,
             periodos=[presentado(*declaradas, mixta),
                       presentado(ano=2026, trimestre=2, en=date(2026, 7, 20))]),
    ]
