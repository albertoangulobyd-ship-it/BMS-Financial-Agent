"""Deteccion de anomalias sobre el historico.

Esto es lo que una factura mirada de una en una no puede ver. Y es donde un
falso positivo cuesta mas que un hueco: una alerta que salta siempre se acaba
ignorando, y entonces se pierden tambien las buenas.
"""

from __future__ import annotations

from decimal import Decimal

from bms_agent.dashboard import (
    construir_alertas,
    construir_filas,
    detectar_cambios_de_tarifa,
    detectar_duplicados,
    detectar_ibanes,
    detectar_periodos_repetidos,
    por_mes,
    por_proveedor,
)


def factura(nombre, proveedor="Van Dijk BV", numero="2026-001", fecha="2026-09-15",
            total="1.000,00", iban="NL02ABNA0123456789", inicio="2026-09-07",
            fin="2026-09-13", lineas=None):
    return {
        "source_name": nombre,
        "extraction": {
            "supplier_name": proveedor, "invoice_number": numero,
            "invoice_date": fecha, "service_period_start": inicio,
            "service_period_end": fin, "total_incl_vat_raw": total,
            "subtotal_excl_vat_raw": total, "vat_amount_raw": "0,00",
            "vat_rate_raw": None, "vat_regime": "reverse_charged",
            "iban": iban, "lines": lineas if lineas is not None else [],
            "low_confidence_fields": [], "document_notes": None,
        },
    }


def linea(desc, ubicacion, tarifa, cantidad="8,00"):
    return {"description": desc, "location": ubicacion, "unit": "uur",
            "quantity_raw": cantidad, "unit_rate_raw": tarifa,
            "line_total_raw": "100,00", "week_number": 37}


# --- B2: numero repetido ---

def test_el_mismo_numero_dos_veces_es_critico() -> None:
    filas = construir_filas([factura("a.pdf"), factura("b.pdf")])
    alertas = detectar_duplicados(filas)
    assert [a.regla for a in alertas] == ["B2"]
    assert alertas[0].severidad == "critico"


def test_el_mismo_numero_de_otro_proveedor_no_es_duplicado() -> None:
    """Dos autonomos pueden numerar igual. No es una anomalia."""
    filas = construir_filas([factura("a.pdf"), factura("b.pdf", proveedor="De Vries")])
    assert detectar_duplicados(filas) == []


# --- B3: duplicado por contenido ---

def test_mismo_importe_pocos_dias_y_numero_distinto_se_marca() -> None:
    filas = construir_filas([
        factura("a.pdf", numero="2026-001", fecha="2026-09-01"),
        factura("b.pdf", numero="2026-014", fecha="2026-09-08"),
    ])
    alertas = [a for a in detectar_duplicados(filas) if a.regla == "B3"]
    assert len(alertas) == 1
    assert "7 dias" in alertas[0].detalle


def test_mismo_importe_pero_meses_despues_no_se_marca() -> None:
    """Un autonomo con tarifa fija factura lo mismo cada mes. Es lo normal."""
    filas = construir_filas([
        factura("a.pdf", numero="2026-001", fecha="2026-07-01", inicio="2026-06-01", fin="2026-06-30"),
        factura("b.pdf", numero="2026-014", fecha="2026-09-01", inicio="2026-08-01", fin="2026-08-31"),
    ])
    assert [a for a in detectar_duplicados(filas) if a.regla == "B3"] == []


def test_importes_distintos_no_se_marcan() -> None:
    filas = construir_filas([
        factura("a.pdf", numero="2026-001", fecha="2026-09-01", total="1.000,00"),
        factura("b.pdf", numero="2026-014", fecha="2026-09-03", total="2.500,00"),
    ])
    assert [a for a in detectar_duplicados(filas) if a.regla == "B3"] == []


# --- B4: periodo repetido ---

def test_la_misma_semana_facturada_dos_veces_es_critico() -> None:
    alertas = detectar_periodos_repetidos(construir_filas([
        factura("a.pdf", numero="2026-001", total="1.000,00"),
        factura("b.pdf", numero="2026-002", total="1.400,00"),
    ]))
    assert len(alertas) == 1
    assert alertas[0].regla == "B4" and alertas[0].severidad == "critico"


def test_periodos_distintos_no_se_marcan() -> None:
    assert detectar_periodos_repetidos(construir_filas([
        factura("a.pdf", numero="1", inicio="2026-09-07", fin="2026-09-13"),
        factura("b.pdf", numero="2", inicio="2026-09-14", fin="2026-09-20"),
    ])) == []


# --- F3: mas de un IBAN ---

def test_dos_ibanes_del_mismo_proveedor_es_critico() -> None:
    alertas = detectar_ibanes([
        factura("a.pdf", numero="1", iban="NL02ABNA0123456789"),
        factura("b.pdf", numero="2", iban="NL91ABNA0417164300"),
    ])
    assert len(alertas) == 1
    assert alertas[0].regla == "F3" and alertas[0].severidad == "critico"
    assert "telefonica" in alertas[0].detalle


def test_el_mismo_iban_con_espacios_distintos_no_es_un_cambio() -> None:
    """NL02 ABNA ... y NL02ABNA... son la misma cuenta."""
    assert detectar_ibanes([
        factura("a.pdf", numero="1", iban="NL02 ABNA 0123 4567 89"),
        factura("b.pdf", numero="2", iban="nl02abna0123456789"),
    ]) == []


# --- G3: cambio de tarifa ---

def test_la_misma_tarea_a_dos_tarifas_en_facturas_distintas_se_marca() -> None:
    alertas = detectar_cambios_de_tarifa([
        factura("a.pdf", numero="1", lineas=[linea("Montagewerk, locatie X", "Schiedam", "42,50")]),
        factura("b.pdf", numero="2", lineas=[linea("Montagewerk, locatie X", "Schiedam", "58,00")]),
    ])
    assert len(alertas) == 1
    assert alertas[0].regla == "G3"
    assert "42,50" in alertas[0].detalle.replace(".", ",") or "42.50" in alertas[0].detalle


def test_horas_de_viaje_y_de_trabajo_no_son_un_cambio_de_tarifa() -> None:
    """El falso positivo que haria inutil esta alerta.

    Montaje a 44 y horas de viaje a 22,50 en la misma obra es lo normal,
    no una anomalia.
    """
    alertas = detectar_cambios_de_tarifa([
        factura("a.pdf", numero="1", lineas=[
            linea("Montagewerk, locatie Schiedam", "Schiedam", "44,00"),
            linea("Reisuren, locatie Schiedam", "Schiedam", "22,50"),
        ]),
    ])
    assert alertas == []


def test_dos_tarifas_dentro_de_una_sola_factura_no_se_marcan() -> None:
    """Hace falta ver dos facturas para hablar de un cambio."""
    alertas = detectar_cambios_de_tarifa([
        factura("a.pdf", numero="1", lineas=[
            linea("Montagewerk", "Schiedam", "44,00"),
            linea("Montagewerk", "Schiedam", "48,00"),
        ]),
    ])
    assert alertas == []


def test_la_misma_tarifa_en_varias_facturas_no_se_marca() -> None:
    assert detectar_cambios_de_tarifa([
        factura("a.pdf", numero="1", lineas=[linea("Montagewerk", "Schiedam", "44,00")]),
        factura("b.pdf", numero="2", lineas=[linea("Montagewerk", "Schiedam", "44,00")]),
    ]) == []


# --- agregados ---

def test_la_serie_mensual_rellena_los_meses_vacios() -> None:
    """Un hueco de gasto tiene que verse como hueco, no desaparecer del eje."""
    filas = construir_filas([
        factura("a.pdf", numero="1", fecha="2026-01-15"),
        factura("b.pdf", numero="2", fecha="2026-04-10"),
    ])
    meses = por_mes(filas)
    assert [m["mes"] for m in meses] == ["2026-01", "2026-02", "2026-03", "2026-04"]
    assert meses[1]["total"] == Decimal(0)


def test_el_ranking_de_proveedores_va_por_importe() -> None:
    filas = construir_filas([
        factura("a.pdf", proveedor="Pequeno", numero="1", total="100,00"),
        factura("b.pdf", proveedor="Grande", numero="2", total="9.000,00"),
    ])
    assert [p["proveedor"] for p in por_proveedor(filas)] == ["Grande", "Pequeno"]


def test_las_alertas_criticas_salen_antes_que_los_avisos() -> None:
    registros = [
        factura("a.pdf", numero="2026-001", iban="NL02ABNA0123456789"),
        factura("b.pdf", numero="2026-001", iban="NL91ABNA0417164300"),
    ]
    alertas = construir_alertas(construir_filas(registros), registros)
    assert alertas[0].severidad == "critico"
    assert {a.regla for a in alertas if a.severidad == "critico"} >= {"B2", "B4", "F3"}


def test_un_historico_vacio_no_rompe_nada() -> None:
    assert construir_filas([]) == []
    assert por_mes([]) == []
    assert construir_alertas([], []) == []


def test_una_lectura_dudosa_no_se_vuelve_critica_por_contagio() -> None:
    """La severidad es del motivo, no de la fila.

    Una factura con la aritmetica mal Y una lectura dudosa tiene un problema
    critico y un aviso, no dos criticos. Si no, el recuento de criticas se
    infla y deja de servir para decidir que no se paga.
    """
    registro = factura("a.pdf", total="9.999,99")
    registro["extraction"]["subtotal_excl_vat_raw"] = "1.000,00"
    registro["extraction"]["vat_amount_raw"] = "0,00"
    registro["extraction"]["low_confidence_fields"] = ["kvk_number"]

    filas = construir_filas([registro])
    alertas = construir_alertas(filas, [registro])

    criticas = [a for a in alertas if a.severidad == "critico"]
    revisar = [a for a in alertas if a.severidad == "revisar"]
    assert any("Total" in a.titulo for a in criticas)
    assert any("dudosa" in a.titulo for a in revisar)
    assert not any("dudosa" in a.titulo for a in criticas)


def test_una_factura_solo_con_lectura_dudosa_no_es_critica() -> None:
    registro = factura("a.pdf")
    registro["extraction"]["low_confidence_fields"] = ["kvk_number"]
    fila = construir_filas([registro])[0]
    assert fila.estado == "revisar"
    assert fila.fallos == []


def test_el_iban_habitual_no_convierte_todo_el_historico_en_sospechoso() -> None:
    """Solo se verifica la factura con la cuenta rara, no las veinte anteriores."""
    registros = [factura(f"h{i}.pdf", numero=str(i), iban="NL02ABNA0123456789")
                 for i in range(5)]
    registros.append(factura("rara.pdf", numero="99", iban="NL91ABNA0417164300"))

    alertas = detectar_ibanes(registros)

    assert len(alertas) == 1
    assert alertas[0].facturas == ["rara.pdf"]
    assert "NL02ABNA0123456789" in alertas[0].detalle


def test_una_factura_duplicada_no_sale_verde_en_la_tabla() -> None:
    """El panel no puede decir critico arriba y ok en la fila."""
    from bms_agent.dashboard import construir_datos

    registros = [factura("a.pdf", numero="2026-001"), factura("b.pdf", numero="2026-001")]
    datos = construir_datos(registros)

    assert all(f["estado"] == "critico" for f in datos["filas"])
    assert datos["totales"]["criticas"] == 2


def test_los_periodos_que_solapan_se_detectan_aunque_el_texto_no_coincida() -> None:
    """Del 7 al 13 solapa con del 1 al 10, y los textos no se parecen en nada."""
    alertas = detectar_periodos_repetidos(construir_filas([
        factura("a.pdf", numero="1", inicio="2026-09-07", fin="2026-09-13"),
        factura("b.pdf", numero="2", inicio="2026-09-01", fin="2026-09-10"),
    ]))
    assert len(alertas) == 1
    assert alertas[0].regla == "B4"
    assert "solapan 4 dia" in alertas[0].detalle


def test_periodos_consecutivos_no_solapan() -> None:
    assert detectar_periodos_repetidos(construir_filas([
        factura("a.pdf", numero="1", inicio="2026-09-01", fin="2026-09-07"),
        factura("b.pdf", numero="2", inicio="2026-09-08", fin="2026-09-14"),
    ])) == []


def test_el_iban_se_agrupa_por_btw_id_no_por_nombre() -> None:
    """El mismo autonomo escrito de dos formas sigue siendo el mismo.

    Un cambio de IBAN acompanado de un cambio de nombre es justo la forma que
    toma el fraude cuando alguien se esfuerza.
    """
    a = factura("a.pdf", proveedor="J. de Vries", numero="1", iban="NL02ABNA0123456789")
    b = factura("b.pdf", proveedor="De Vries Montage", numero="2", iban="NL91ABNA0417164300")
    a["extraction"]["vat_number"] = "NL002345678B01"
    b["extraction"]["vat_number"] = "NL002345678B01"

    alertas = detectar_ibanes([a, b])

    assert len(alertas) == 1 and alertas[0].regla == "F3"


def test_los_agregados_van_en_base_imponible_no_en_total_con_iva() -> None:
    """Comparar regimenes por el total premia al regimen, no al gasto."""
    con_iva = factura("a.pdf", numero="1", total="1.210,00")
    con_iva["extraction"]["subtotal_excl_vat_raw"] = "1.000,00"
    con_iva["extraction"]["vat_amount_raw"] = "210,00"
    con_iva["extraction"]["vat_regime"] = "standard"

    trasladado = factura("b.pdf", proveedor="Otro", numero="2", total="1.000,00")
    trasladado["extraction"]["subtotal_excl_vat_raw"] = "1.000,00"

    ranking = por_proveedor(construir_filas([con_iva, trasladado]))
    assert {p["total"] for p in ranking} == {Decimal("1000.00")}


def test_las_unidades_que_no_son_horas_no_desaparecen_en_silencio() -> None:
    reg = factura("a.pdf", lineas=[
        {"description": "Montage", "location": "X", "unit": "uur",
         "quantity_raw": "8,00", "unit_rate_raw": "40,00", "line_total_raw": "320,00"},
        {"description": "Materiaal", "location": "X", "unit": "stuk",
         "quantity_raw": "12,00", "unit_rate_raw": "5,00", "line_total_raw": "60,00"},
    ])
    fila = construir_filas([reg])[0]
    assert fila.horas == Decimal("8.00")
    assert fila.otras_unidades == ["stuk"]


def test_la_matriz_muestra_las_semanas_sin_facturas_como_hueco() -> None:
    """Una semana sin factura es el dato, no la ausencia de dato."""
    from bms_agent.dashboard import matriz_semanal

    def con_semana(nombre, numero, semana, fin):
        return factura(nombre, numero=numero, inicio=fin, fin=fin,
                       lineas=[{"description": "Montage", "location": "X", "unit": "uur",
                                "quantity_raw": "8,00", "unit_rate_raw": "40,00",
                                "line_total_raw": "320,00", "week_number": semana}])

    m = matriz_semanal(construir_filas([
        con_semana("a.pdf", "1", 35, "2026-08-28"),
        con_semana("b.pdf", "2", 39, "2026-09-25"),
    ]))
    assert m["semanas"] == [f"2026-W{n}" for n in range(35, 40)]
    celdas = m["proveedores"][0]["celdas"]
    assert "2026-W36" not in celdas and "2026-W37" not in celdas


def test_la_matriz_marca_la_semana_con_dos_facturas() -> None:
    from bms_agent.dashboard import matriz_semanal

    def con_semana(nombre, numero):
        return factura(nombre, numero=numero, inicio="2026-09-07", fin="2026-09-13",
                       lineas=[{"description": "Montage", "location": "X", "unit": "uur",
                                "quantity_raw": "8,00", "unit_rate_raw": "40,00",
                                "line_total_raw": "320,00", "week_number": 37}])

    m = matriz_semanal(construir_filas([con_semana("a.pdf", "1"), con_semana("b.pdf", "2")]))
    assert m["proveedores"][0]["celdas"]["2026-W37"]["n"] == 2


def test_un_cambio_de_banco_real_no_acusa_al_historico_correcto() -> None:
    """La cuenta de referencia es la mas antigua, no la mas repetida.

    Si un proveedor cambia de banco y luego manda veinte facturas con la
    cuenta nueva, la frecuencia convertiria la nueva en "habitual" y marcaria
    como sospechosas las antiguas, que son las correctas.
    """
    viejas = [factura(f"v{i}.pdf", numero=f"v{i}", fecha=f"2026-0{i+1}-05",
                      iban="NL02ABNA0123456789") for i in range(2)]
    nuevas = [factura(f"n{i}.pdf", numero=f"n{i}", fecha=f"2026-0{i+5}-05",
                      iban="NL91ABNA0417164300") for i in range(4)]

    alertas = detectar_ibanes(viejas + nuevas)

    assert len(alertas) == 1
    assert sorted(alertas[0].facturas) == ["n0.pdf", "n1.pdf", "n2.pdf", "n3.pdf"]
    assert "NL02ABNA0123456789" in alertas[0].detalle


def test_una_subida_de_tarifa_senala_las_nuevas_no_las_viejas() -> None:
    def con_tarifa(nombre, fecha, tarifa):
        return factura(nombre, numero=nombre, fecha=fecha,
                       lineas=[linea("Montagewerk", "Schiedam", tarifa)])

    alertas = detectar_cambios_de_tarifa([
        con_tarifa("a.pdf", "2026-03-05", "42,50"),
        con_tarifa("b.pdf", "2026-06-05", "58,00"),
        con_tarifa("c.pdf", "2026-07-05", "58,00"),
        con_tarifa("d.pdf", "2026-08-05", "58,00"),
    ])

    assert len(alertas) == 1
    assert sorted(alertas[0].facturas) == ["b.pdf", "c.pdf", "d.pdf"]


def test_b3_no_salta_entre_semanas_distintas_al_mismo_importe() -> None:
    """Un autonomo con tarifa fija factura lo mismo cada semana."""
    a = factura("a.pdf", numero="1", fecha="2026-09-08",
                inicio="2026-08-31", fin="2026-09-06")
    b = factura("b.pdf", numero="2", fecha="2026-09-15",
                inicio="2026-09-07", fin="2026-09-13")
    assert [x for x in detectar_duplicados(construir_filas([a, b])) if x.regla == "B3"] == []


def test_b3_si_salta_cuando_los_periodos_se_pisan() -> None:
    a = factura("a.pdf", numero="1", fecha="2026-09-08",
                inicio="2026-09-07", fin="2026-09-13")
    b = factura("b.pdf", numero="2", fecha="2026-09-15",
                inicio="2026-09-07", fin="2026-09-13")
    assert [x for x in detectar_duplicados(construir_filas([a, b])) if x.regla == "B3"]


def test_una_nota_de_credito_no_es_periodo_facturado_dos_veces() -> None:
    a = factura("a.pdf", numero="1", total="1.000,00")
    b = factura("b.pdf", numero="2-C", total="-1.000,00")
    assert detectar_periodos_repetidos(construir_filas([a, b])) == []


def test_una_fecha_en_formato_neerlandes_no_tumba_el_panel() -> None:
    """parse_iso_date acepta 13-09-2026 a proposito; el panel debe aguantarlo."""
    from bms_agent.dashboard import construir_datos

    a = factura("a.pdf", numero="1", fecha="13-09-2026")
    b = factura("b.pdf", numero="2", fecha="2026-08-30")
    datos = construir_datos([a, b])

    assert [f["orden"] for f in datos["filas"]] == ["2026-09-13", "2026-08-30"]
    assert [m["mes"] for m in datos["por_mes"]] == ["2026-08", "2026-09"]


def test_la_semana_52_facturada_en_enero_va_al_ano_anterior() -> None:
    from bms_agent.dashboard import matriz_semanal

    reg = factura("a.pdf", numero="1", fecha="2026-01-06",
                  inicio="2025-12-22", fin="2025-12-28",
                  lineas=[{"description": "Montage", "location": "X", "unit": "uur",
                           "quantity_raw": "8,00", "unit_rate_raw": "40,00",
                           "line_total_raw": "320,00", "week_number": 52}])
    m = matriz_semanal(construir_filas([reg]))
    assert "2025-W52" in m["proveedores"][0]["celdas"]


def test_una_semana_53_imposible_no_lanza_excepcion() -> None:
    from bms_agent.dashboard import matriz_semanal

    reg = factura("a.pdf", numero="1", fecha="2026-06-10",
                  inicio="2026-06-01", fin="2026-06-07",
                  lineas=[{"description": "Montage", "location": "X", "unit": "uur",
                           "quantity_raw": "8,00", "unit_rate_raw": "40,00",
                           "line_total_raw": "320,00", "week_number": 53}])
    m = matriz_semanal(construir_filas([reg]))   # 2026 tiene 53 semanas ISO
    assert m["semanas"]


def test_b4_ve_el_periodo_aunque_solo_este_en_las_lineas() -> None:
    def sin_cabecera(nombre, numero):
        reg = factura(nombre, numero=numero, inicio=None, fin=None,
                      lineas=[{"description": "Montage", "location": "X", "unit": "uur",
                               "quantity_raw": "8,00", "unit_rate_raw": "40,00",
                               "line_total_raw": "320,00", "week_number": 37,
                               "period_start": "2026-09-07", "period_end": "2026-09-13"}])
        reg["extraction"]["service_period_start"] = None
        reg["extraction"]["service_period_end"] = None
        return reg

    alertas = detectar_periodos_repetidos(
        construir_filas([sin_cabecera("a.pdf", "1"), sin_cabecera("b.pdf", "2")]))
    assert len(alertas) == 1 and alertas[0].regla == "B4"


def test_g3_vigila_tambien_las_lineas_sin_obra() -> None:
    def sin_obra(nombre, tarifa):
        return factura(nombre, numero=nombre, lineas=[
            {"description": "Montagewerk", "location": None, "unit": "uur",
             "quantity_raw": "8,00", "unit_rate_raw": tarifa, "line_total_raw": "320,00"}])

    alertas = detectar_cambios_de_tarifa([sin_obra("a.pdf", "40,00"), sin_obra("b.pdf", "55,00")])
    assert len(alertas) == 1 and alertas[0].regla == "G3"
