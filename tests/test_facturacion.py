"""Proyeccion de facturacion a clientes.

Lo que se prueba aqui no es una factura: es una estimacion de lo que se
podria cobrar, calculada desde lo que los autonomos han facturado. Los tests
fijan sobre todo que sea HONESTA sobre lo que no sabe.
"""

from __future__ import annotations

from decimal import Decimal

from bms_agent.facturacion import Tarifas, cargar_tarifas, proyectar


def compra(nombre, obra="Rijnhaven", trabajo="Montagewerk, locatie Rijnhaven",
           horas="10,00", coste="40,00", unidad="uur", semana=37,
           proveedor="Van Dijk BV"):
    return {
        "source_name": nombre,
        "extraction": {
            "supplier_name": proveedor,
            "lines": [{
                "description": trabajo, "location": obra, "unit": unidad,
                "quantity_raw": horas, "unit_rate_raw": coste,
                "line_total_raw": "400,00", "week_number": semana,
            }],
        },
    }


TARIFAS = Tarifas(
    margen_por_defecto=Decimal("0.35"),
    obras={"rijnhaven": "Havenbedrijf Rotterdam BV"},
    tarifas={("rijnhaven", "montagewerk"): Decimal("62.00")},
    no_facturable={"reisuren"},
)


def test_una_tarifa_pactada_gana_sobre_el_margen() -> None:
    r = proyectar([compra("a.pdf")], TARIFAS)
    linea = r["propuestas"][0]["lineas"][0]
    assert linea["tarifa_venta"] == 62.00
    assert linea["origen_tarifa"] == "tabla"
    assert linea["venta"] == 620.00


def test_sin_tarifa_pactada_se_aplica_el_margen_sobre_el_coste() -> None:
    r = proyectar([compra("a.pdf", trabajo="Sloopwerk, locatie Rijnhaven")], TARIFAS)
    linea = r["propuestas"][0]["lineas"][0]
    # 40,00 de coste con 35% de margen dan 54,00.
    assert linea["tarifa_venta"] == 54.00
    assert linea["origen_tarifa"] == "margen"


def test_una_obra_sin_cliente_se_marca_y_no_se_esconde() -> None:
    """La factura de compra dice la obra, no de quien es."""
    r = proyectar([compra("a.pdf", obra="Maashaven")], TARIFAS)

    assert r["sin_mapear"] == ["Maashaven"]
    propuesta = r["propuestas"][0]
    assert propuesta["cliente"].startswith("(obra sin cliente")
    assert any("no tiene cliente asignado" in a for a in propuesta["avisos"])


def test_las_horas_de_viaje_no_se_refacturan() -> None:
    """Se pagan al autonomo y no se cobran al cliente. Y queda dicho."""
    r = proyectar([
        compra("a.pdf", trabajo="Montagewerk, locatie Rijnhaven"),
        compra("b.pdf", trabajo="Reisuren, locatie Rijnhaven", horas="4,00"),
    ], TARIFAS)

    trabajos = {l["trabajo"] for p in r["propuestas"] for l in p["lineas"]}
    assert "reisuren" not in trabajos
    assert r["no_facturable"] == [{"trabajo": "reisuren", "horas": 4.0}]


def test_lo_que_no_se_factura_por_horas_queda_fuera() -> None:
    """Material en piezas no se proyecta con una tarifa por hora."""
    r = proyectar([compra("a.pdf", unidad="stuk")], TARIFAS)
    assert r["propuestas"] == []


def test_se_agrupa_por_cliente_obra_y_semana() -> None:
    r = proyectar([
        compra("a.pdf", semana=37), compra("b.pdf", semana=37),
        compra("c.pdf", semana=38),
    ], TARIFAS)

    assert len(r["propuestas"]) == 2
    semana37 = next(p for p in r["propuestas"] if p["semana"] == "W37")
    assert semana37["horas"] == 20.0
    assert len(semana37["facturas_origen"]) == 2


def test_un_coste_por_hora_que_varia_dentro_del_grupo_se_avisa() -> None:
    """Dos autonomos a precios distintos por el mismo trabajo y semana."""
    r = proyectar([
        compra("a.pdf", coste="40,00", proveedor="Van Dijk"),
        compra("b.pdf", coste="52,00", proveedor="De Vries"),
    ], TARIFAS)

    assert any("varia" in a for a in r["propuestas"][0]["avisos"])


def test_el_margen_se_calcula_sobre_la_venta() -> None:
    r = proyectar([compra("a.pdf")], TARIFAS)
    p = r["propuestas"][0]
    assert p["coste"] == 400.00 and p["venta"] == 620.00
    assert p["margen"] == 220.00
    assert round(p["margen_pct"], 1) == 35.5


def test_sin_tabla_de_tarifas_la_proyeccion_lo_declara() -> None:
    """No se finge que hay precios cuando nadie los ha puesto."""
    r = proyectar([compra("a.pdf")], Tarifas())
    assert r["configurada"] is False
    assert r["sin_mapear"] == ["Rijnhaven"]


def test_la_tabla_de_ejemplo_se_lee() -> None:
    t = cargar_tarifas("config/tarifas.ejemplo.yaml")
    assert t.configurada
    assert t.cliente_de("Rijnhaven") == "Havenbedrijf Rotterdam BV"
    assert t.cliente_de("RIJNHAVEN") == "Havenbedrijf Rotterdam BV"
    assert t.tarifa_de("Schiedam", "Elektrawerk") == Decimal("68.00")
    assert not t.es_facturable("Reisuren")


def test_un_fichero_de_tarifas_que_no_existe_no_rompe_nada() -> None:
    t = cargar_tarifas("config/no-existe.yaml")
    assert t.configurada is False
    assert t.margen_por_defecto == Decimal("0.35")


def test_sin_registros_no_hay_propuestas() -> None:
    r = proyectar([], TARIFAS)
    assert r["propuestas"] == []
    assert r["totales"]["propuestas"] == 0
