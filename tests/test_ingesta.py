"""ingesta.py: de la extraccion guardada a la factura tipada, sin API y sin adivinar.

La direccion la pone la via de entrada; los literales se leen con
parsing.py y lo ilegible queda vacio y dudoso; una factura en otra moneda
no deja importes; volver a tipar no hace nada; una extraccion nueva no pisa
lo que una persona corrigio.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from conftest import FIXTURES_V1, TARIFAS_V1, factura_de, persona
from test_extraccion_pasada import PDF, ClienteFalso

from bms_agent import campos, ingesta
from bms_agent.almacen import preparar, transaccion, usuario_sistema
from bms_agent.almacen.documentos import registrar_documento
from bms_agent.almacen.extracciones import leer_registro, registrar_extraccion
from bms_agent.almacen.unidades import sha256_bytes
from bms_agent.campos import Persona
from bms_agent.importadores.extracciones import importar_out
from bms_agent.importadores.tarifas import sembrar_tarifas
from bms_agent.legado import registros_resueltos


def _f(conn, numero):
    return dict(conn.execute("SELECT * FROM factura WHERE numero = ?", (numero,)).fetchone())


def _lineas(conn, factura_id):
    return [dict(f) for f in conn.execute(
        "SELECT * FROM factura_linea WHERE factura_id = ? ORDER BY orden", (factura_id,))]


def _p(conn, tabla, fila_id, campo):
    return campos.procedencia(conn, tabla, fila_id).get(campo)


def test_las_siete_fixtures_quedan_tipadas(tipado) -> None:
    conn = tipado.conn
    f = _f(conn, "2026-4471")
    assert (f["sentido"], f["tipo"], f["origen"]) == ("entrante", "factura", "extraccion")
    assert (f["base_cent"], f["iva_cent"], f["total_cent"], f["tipo_iva_pb"]) == (
        239900, 50379, 290279, 2100)
    assert (f["fecha_factura"], f["periodo_inicio"], f["periodo_fin"]) == (
        "2026-09-15", "2026-08-31", "2026-09-06")
    assert (f["tratamiento_iva"], f["numero_norm"], f["iban_doc"]) == (
        "estandar", "20264471", "NL02 ABNA 0123 4567 89")
    assert f["proveedor_id"] is None                 # no hay maestro: nada se crea solo
    lineas = _lineas(conn, f["id"])
    assert [(l["orden"], l["cantidad_mil"], l["tarifa_e4"], l["importe_cent"], l["unidad"],
             l["tipo_servicio"], l["objeto_doc"], l["semana_doc"]) for l in lineas] == [
        (1, 37500, 425000, 159375, "hora", "montagewerk", "Rijnhaven", 36),
        (2, 16000, 440000, 70400, "hora", "montagewerk", "Schiedam", 36),
        (3, 4500, 225000, 10125, "hora", "reisuren", "Schiedam", 36)]
    imputaciones = conn.execute(
        "SELECT linea_id, horas_mil, tarifa_e4, importe_cent, tipo_servicio FROM factura_imputacion "
        "WHERE factura_id = ? ORDER BY id", (f["id"],)).fetchall()
    assert [tuple(i) for i in imputaciones] == [
        (l["id"], l["cantidad_mil"], l["tarifa_e4"], l["importe_cent"], l["tipo_servicio"])
        for l in lineas]
    assert conn.execute("SELECT count(*) FROM factura").fetchone()[0] == 7
    assert conn.execute("SELECT count(*) FROM factura_iva").fetchone()[0] == 0    # v1 no lo pide
    assert campos.verificar_controladas(conn) == []


def test_un_documento_nunca_crea_un_maestro_ni_una_cuenta(tipado) -> None:
    """La factura con el texto inyectado (03) no cambia nada fuera de su propia fila."""
    conn = tipado.conn
    for tabla in ("proveedor", "cliente", "contacto", "recurso", "alias", "objeto"):
        assert conn.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0] == 0, tabla
    f = _f(conn, "2026-0912")
    assert f["iban_doc"] == "NL75 INGB 0002 4456 89"           # el de la cabecera, como texto
    assert "NL91 ABNA 0417 1643 00" in f["notas_doc"]           # lo inyectado, en las notas


def test_la_fecha_neerlandesa_se_lee_y_el_literal_se_guarda(tipado) -> None:
    conn = tipado.conn
    f = _f(conn, "2026-112")
    p = _p(conn, "factura", f["id"], "fecha_factura")
    assert f["fecha_factura"] == "2026-09-13"
    assert (p["valor_original_crudo"], p["dudoso"]) == ("13-09-2026", 0)


def test_una_factura_en_dolares_no_deja_importes(tipado) -> None:
    conn = tipado.conn
    f = _f(conn, "NW-2026-0042")
    assert (f["base_cent"], f["iva_cent"], f["total_cent"], f["moneda_doc"]) == (None, None, None, "USD")
    p = _p(conn, "factura", f["id"], "total_cent")
    assert (p["valor_original_crudo"], p["dudoso"], p["valor_actual"]) == ("$2,500.00", 0, None)
    [linea] = _lineas(conn, f["id"])
    assert (linea["tarifa_e4"], linea["importe_cent"], linea["cantidad_mil"], linea["unidad"]) == (
        None, None, 20000, "hora")


def test_un_abono_se_reconoce_por_el_signo(tipado) -> None:
    conn = tipado.conn
    f = _f(conn, "CN-2026-031")
    assert (f["tipo"], f["total_cent"]) == ("nota_credito", -12251)
    assert _p(conn, "factura", f["id"], "tipo")["fuente"] == "calculado"


def test_uren_es_hora_y_stuk_no(tipado) -> None:
    conn = tipado.conn
    f = _f(conn, "B-2026-077")
    assert [(l["unidad"], l["cantidad_mil"]) for l in _lineas(conn, f["id"])] == [
        ("hora", 24000), ("stuk", 1000)]
    horas = [i[0] for i in conn.execute(
        "SELECT horas_mil FROM factura_imputacion WHERE factura_id = ? ORDER BY id", (f["id"],))]
    assert horas == [24000, None]


def _registro(nombre: str, **cambios) -> dict:
    registro = json.loads((FIXTURES_V1 / f"{nombre}.json").read_text(encoding="utf-8"))
    extraccion = cambios.pop("extraction", {})
    registro.update(cambios)
    registro["extraction"].update(extraccion)
    return registro


def test_lo_ilegible_y_lo_dudoso_quedan_marcados(almacen, out_v1) -> None:
    registro = _registro("01-limpia", extraction={
        "subtotal_excl_vat_raw": "12.34,567",
        "low_confidence_fields": ["vat_number", "lines[1].unit_rate_raw"]})
    (out_v1 / "01-limpia.json").write_text(json.dumps(registro, indent=2), encoding="utf-8")
    importar_out(almacen, out_v1, None)
    ingesta.tipar_pendientes(almacen.conn)
    conn = almacen.conn
    f = _f(conn, "2026-4471")
    base = _p(conn, "factura", f["id"], "base_cent")
    assert (f["base_cent"], base["dudoso"], base["valor_original_crudo"]) == (None, 1, "12.34,567")
    assert _p(conn, "factura", f["id"], "emisor_btw_doc")["dudoso"] == 1
    assert _p(conn, "factura", f["id"], "iban_doc")["dudoso"] == 0
    lineas = _lineas(conn, f["id"])
    assert [_p(conn, "factura_linea", l["id"], "tarifa_e4")["dudoso"] for l in lineas] == [0, 1, 0]
    assert campos.estado_campo(_p(conn, "factura", f["id"], "emisor_btw_doc")).dudoso


def test_volver_a_tipar_no_hace_nada(tipado) -> None:
    conn = tipado.conn
    eventos = conn.execute("SELECT count(*) FROM evento").fetchone()[0]
    assert {t.accion for t in ingesta.tipar_pendientes(conn)} == {"sin_cambios"}
    assert conn.execute("SELECT count(*) FROM evento").fetchone()[0] == eventos


def _documento_por_ruta(almacen, ruta: str, registro: dict) -> int:
    conn = almacen.conn
    contenido = json.dumps(registro, indent=2, ensure_ascii=False)
    with transaccion(conn):
        actor = usuario_sistema(conn, "extractor")
        documento = registrar_documento(
            almacen, sha256=registro["source_sha256"], contenido=None,
            nombre_original=registro["source_name"], tipo_mime="application/pdf", origen="manual",
            ruta_declarada=ruta, recibido_en=None, recibido_fuente="desconocido", actor=actor)
        registrar_extraccion(conn, leer_registro(contenido), documento_id=documento.id,
                             via="api", actor=actor)
    return documento.id


def test_la_direccion_la_pone_la_via_de_entrada(almacen) -> None:
    """El mismo contenido entra como venta por la via de salida, diga lo que diga."""
    registro = _registro("01-limpia", source_sha256="a" * 64, source_name="venta.pdf")
    documento = _documento_por_ruta(almacen, "saliente", registro)
    banco = _documento_por_ruta(almacen, "banco", _registro("02-sin-kvk-btw-verlegd",
                                                            source_sha256="b" * 64))
    resultados = {t.documento_id: t for t in ingesta.tipar_pendientes(almacen.conn)}
    assert resultados[documento].accion == "creada"
    assert resultados[banco].accion == "omitido"
    fila = almacen.conn.execute("SELECT * FROM factura WHERE documento_id = ?", (documento,)).fetchone()
    assert (fila["sentido"], fila["proveedor_id"]) == ("saliente", None)
    assert _p(almacen.conn, "factura", fila["id"], "sentido")["fuente_ref"] == "ruta:saliente"


def test_una_extraccion_nueva_no_pisa_lo_corregido(tipado, out_v1) -> None:
    conn = tipado.conn
    ana = persona(conn, "Ana", "administracion")
    f = factura_de(conn, "2026-4471")
    campos.fijar(conn, "factura", f, {"total_cent": Decimal("2902.80")}, Persona(ana, "lectura mala"))
    campos.fijar(conn, "factura", f, {"referencia_pago": "RF-9"}, Persona(ana))

    nueva = _registro("01-limpia", model="claude-opus-5-5", extracted_at="2026-10-01T08:00:00+00:00",
                      extraction={"total_incl_vat_raw": "2.902,99", "payment_reference": "RF-1",
                                  "supplier_address": "Havenstraat 16, Rotterdam"})
    nueva["extraction"]["lines"] = nueva["extraction"]["lines"][:2]
    (out_v1 / "01-limpia-z.json").write_text(json.dumps(nueva, indent=2), encoding="utf-8")
    importar_out(tipado, out_v1, None)
    [actualizada] = [t for t in ingesta.tipar_pendientes(conn) if t.accion == "actualizada"]
    assert actualizada.factura_id == f

    fila = campos.leer(conn, "factura", f)
    assert fila["total_cent"] == 290280 and fila["referencia_pago"] == "RF-9"
    assert fila["emisor_direccion_doc"] == "Havenstraat 16, Rotterdam"
    total = _p(conn, "factura", f, "total_cent")
    assert (total["valor_automatico"], total["fuente"]) == (290299, "manual_correccion")
    assert campos.estado_campo(total).sin_resolver
    lineas = _lineas(conn, f)
    assert [l["retirada_en"] is None for l in lineas] == [True, True, False]
    retirada = conn.execute("SELECT retirada_en FROM factura_imputacion WHERE linea_id = ?",
                            (lineas[2]["id"],)).fetchone()[0]
    assert retirada is not None

    [resuelto] = [r for r in registros_resueltos(conn) if r["source_name"] == "01-limpia.pdf"]
    assert resuelto["model"] == "claude-opus-5-5"
    x = resuelto["extraction"]
    assert (x["total_incl_vat_raw"], x["payment_reference"], x["supplier_address"]) == (
        "2902.80", "RF-9", "Havenstraat 16, Rotterdam")
    assert len(x["lines"]) == 2 and x["lines"][0]["line_total_raw"] == "1.593,75"
    assert campos.verificar_controladas(conn) == []


def test_una_linea_editada_que_desaparece_se_conserva(tipado, out_v1) -> None:
    conn = tipado.conn
    ana = persona(conn, "Ana", "administracion")
    f = factura_de(conn, "2026-4471")
    tercera = _lineas(conn, f)[2]["id"]
    campos.fijar(conn, "factura_linea", tercera, {"descripcion_doc": "Reisuren Schiedam"},
                 Persona(ana, "mas claro"))
    nueva = _registro("01-limpia", extracted_at="2026-10-01T08:00:00+00:00")
    nueva["extraction"]["lines"] = nueva["extraction"]["lines"][:2]
    (out_v1 / "01-limpia-z.json").write_text(json.dumps(nueva, indent=2), encoding="utf-8")
    importar_out(tipado, out_v1, None)
    [actualizada] = [t for t in ingesta.tipar_pendientes(conn) if t.accion == "actualizada"]
    assert "se conservan" in actualizada.detalle
    assert _lineas(conn, f)[2]["retirada_en"] is None


def test_una_extraccion_v2_llena_lo_que_v1_no_pedia(almacen) -> None:
    registro = _registro("01-limpia", source_sha256="c" * 64, source_name="v2.pdf",
                         schema_version="2")
    x = registro["extraction"]
    x.update(document_type="credit_note", currency_raw="EUR", recipient_name="BM Support BV",
             recipient_vat_number="NL009999999B01", supplier_contact_person="P. Jansen",
             recipient_contact_person="t.a.v. administratie", payment_terms_raw="30 dagen",
             related_invoices=None,
             references=[{"label": "PO-nummer", "value": "PO 2026-17"},
                         {"label": "Project", "value": "RH-3"}],
             vat_breakdown=[{"rate_raw": "21%", "base_raw": "2.399,00", "vat_raw": "503,79"}])
    for linea in x["lines"]:
        linea.update(employee_name="Piet", work_date="2026-09-01", order_reference_raw=None,
                     rate_type_raw="Avond", vat_rate_raw="21%")
    x["lines"][0]["order_reference_raw"] = "PO 2026-17"
    documento = _documento_por_ruta(almacen, "entrante", registro)
    [tipado] = [t for t in ingesta.tipar_pendientes(almacen.conn) if t.documento_id == documento]
    conn = almacen.conn
    f = dict(conn.execute("SELECT * FROM factura WHERE id = ?", (tipado.factura_id,)).fetchone())
    assert (f["tipo"], f["moneda_doc"], f["receptor_nombre_doc"], f["contacto_nombre_doc"],
            f["condiciones_pago_doc"]) == ("nota_credito", "EUR", "BM Support BV", "P. Jansen",
                                           "30 dagen")
    referencias = conn.execute(
        "SELECT etiqueta_doc, valor_doc, valor_norm, clase, linea_id FROM factura_referencia "
        "WHERE factura_id = ? ORDER BY id", (f["id"],)).fetchall()
    lineas = _lineas(conn, f["id"])
    assert [tuple(r) for r in referencias] == [
        ("PO-nummer", "PO 2026-17", "PO202617", "po", None),
        ("Project", "RH-3", "RH3", "proyecto", None),
        (None, "PO 2026-17", "PO202617", "otra", lineas[0]["id"])]
    [iva] = conn.execute("SELECT * FROM factura_iva WHERE factura_id = ?", (f["id"],)).fetchall()
    assert (iva["tipo_iva_pb"], iva["base_cent"], iva["cuota_cent"]) == (2100, 239900, 50379)
    assert (lineas[0]["recurso_doc"], lineas[0]["fecha_trabajo"], lineas[0]["semana_iso"],
            lineas[0]["tipo_turno_doc"], lineas[0]["tipo_iva_pb"]) == (
        "Piet", "2026-09-01", "2026-W36", "Avond", 2100)
    turno = conn.execute("SELECT tipo_turno FROM factura_imputacion WHERE linea_id = ?",
                         (lineas[0]["id"],)).fetchone()[0]
    assert turno == "avond"


def test_la_semilla_de_tarifas_imputa_cada_linea_a_su_objeto(tipado) -> None:
    conn = tipado.conn
    r = sembrar_tarifas(conn, TARIFAS_V1)
    assert (r.clientes_nuevos, r.objetos_nuevos, r.tarifas_nuevas, r.avisos) == (2, 3, 5, [])
    objetos = {f["codigo"]: (f["id"], f["cliente_id"]) for f in conn.execute("SELECT * FROM objeto")}
    clientes = {f["nombre"]: f["id"] for f in conn.execute("SELECT * FROM cliente")}
    assert objetos["Rijnhaven"][1] == objetos["Waalhaven"][1] == clientes["Havenbedrijf Rotterdam BV"]
    assert objetos["Schiedam"][1] == clientes["Bouwgroep Schiedam VOF"]
    sin_objeto = conn.execute(
        "SELECT l.objeto_doc FROM factura_imputacion AS i JOIN factura_linea AS l ON l.id = i.linea_id "
        "WHERE i.objeto_id IS NULL").fetchall()
    assert [f[0] for f in sin_objeto] == [None]                 # solo la linea sin locatie (07)
    tarifa = conn.execute(
        "SELECT t.tarifa_e4, t.unidad, t.sentido FROM tarifa_acordada AS t JOIN objeto AS o "
        "ON o.id = t.objeto_id WHERE o.codigo = 'Waalhaven' AND t.tipo_servicio = 'staalconstructie'"
    ).fetchone()
    assert tuple(tarifa) == (740000, "hora", "venta")
    politica = conn.execute("SELECT fichero, sha256 FROM politica_version").fetchone()
    assert (politica["fichero"], politica["sha256"]) == ("tarifas.yaml", r.sha256)
    # Otra vez el mismo fichero: nada.
    eventos = conn.execute("SELECT count(*) FROM evento").fetchone()[0]
    otra = sembrar_tarifas(conn, TARIFAS_V1)
    assert (otra.nueva_politica, otra.clientes_nuevos, otra.objetos_nuevos, otra.tarifas_nuevas,
            otra.tarifas_cambiadas, otra.imputaciones_resueltas) == (False, 0, 0, 0, 0, 0)
    assert conn.execute("SELECT count(*) FROM evento").fetchone()[0] == eventos


def test_una_tarifa_cambiada_en_el_fichero_se_actualiza(tipado, tmp_path) -> None:
    conn = tipado.conn
    sembrar_tarifas(conn, TARIFAS_V1)
    cambiado = tmp_path / "tarifas.yaml"
    cambiado.write_text(TARIFAS_V1.read_text(encoding="utf-8").replace('"74,00"', '"76,50"'),
                        encoding="utf-8")
    r = sembrar_tarifas(conn, cambiado)
    assert (r.nueva_politica, r.tarifas_cambiadas, r.tarifas_nuevas) == (True, 1, 0)
    # (La pasada con que termina la semilla apunta tambien los pesos de la prioridad.)
    def versiones() -> int:
        return conn.execute("SELECT count(*) FROM politica_version WHERE fichero = "
                            "'tarifas.yaml'").fetchone()[0]

    assert versiones() == 2
    # Volver el mismo dia al fichero anterior lo pone en vigor otra vez: las tarifas y
    # politica_version dicen lo mismo.
    r = sembrar_tarifas(conn, TARIFAS_V1)
    assert (r.nueva_politica, r.tarifas_cambiadas) == (True, 1)
    assert versiones() == 3
    from bms_agent import politica

    assert politica.vigente(conn, "tarifas.yaml")["sha256"] == r.sha256


def test_extract_tipa_lo_que_extrae(tmp_path, monkeypatch, capsys) -> None:
    import anthropic

    from bms_agent.almacen import ruta_por_defecto
    from bms_agent.cli import main

    pdfs = tmp_path / "facturas"
    pdfs.mkdir()
    (pdfs / "a.pdf").write_bytes(PDF)
    cliente = ClienteFalso()
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: cliente)
    assert main(["extract", str(pdfs), "--out", str(tmp_path / "out")]) == 0
    assert "Facturas tipadas: 1 nuevas" in capsys.readouterr().out
    with preparar(ruta_por_defecto()) as almacen:
        fila = almacen.conn.execute("SELECT * FROM factura").fetchone()
        assert (fila["numero"], fila["total_cent"], fila["sentido"]) == ("2026-001", 12100, "entrante")
        documento = almacen.conn.execute("SELECT sha256 FROM documento").fetchone()[0]
        assert documento == sha256_bytes(PDF)


def test_el_boton_del_servidor_tipa_lo_que_extrae(tmp_path, monkeypatch) -> None:
    from bms_agent.serve import Agente

    pdfs = tmp_path / "facturas"
    pdfs.mkdir()
    (pdfs / "a.pdf").write_bytes(PDF)
    db = tmp_path / "datos" / "bms.sqlite3"
    agente = Agente(pdfs, tmp_path / "out", db)
    monkeypatch.setattr(agente, "_cliente", lambda: ClienteFalso())
    agente._ejecutar()
    assert agente.estado["estado"] == "terminado"
    with preparar(db) as almacen:
        assert almacen.conn.execute("SELECT count(*) FROM factura").fetchone()[0] == 1


def test_importar_out_y_ingestar_por_la_cli(tmp_path, out_v1, capsys) -> None:
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["ingestar", "--db", str(db)]) == 1                # sin almacen
    assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(tmp_path / "no"),
                 "--db", str(db)]) == 0
    assert "Facturas tipadas: 7 nuevas" in capsys.readouterr().out
    assert main(["ingestar", "--db", str(db)]) == 0
    assert "0 nuevas, 0 con una extraccion nueva, 7 sin cambios" in capsys.readouterr().out
    assert main(["sembrar", "--tarifas", str(TARIFAS_V1), "--db", str(db)]) == 0
    assert "imputaciones resueltas 9" in capsys.readouterr().out
    assert main(["sembrar", "--tarifas", str(tmp_path / "no.yaml"), "--db", str(db)]) == 1
    assert main(["db", "verificar", "--db", str(db)]) == 0


@pytest.mark.parametrize("lector, crudo, valor, dudoso", [
    (ingesta.IMPORTE, "8.740,00", Decimal("8740.00"), False),
    (ingesta.IMPORTE, "12.34,567", None, True),
    (ingesta.IMPORTE, None, None, False),
    (ingesta.FECHA, "13-09-2026", __import__("datetime").date(2026, 9, 13), False),
    (ingesta.FECHA, "05/06/26", None, True),
    (ingesta.PORCENTAJE, "21%", Decimal("21"), False),
    (ingesta.ENTERO, 36, 36, False),
    (ingesta.ENTERO, "36", 36, False),
    (ingesta.ENTERO, True, None, True),
    (ingesta.BOOLEANO, "si", None, True),
    (ingesta.REGIMEN_IVA, "reverse_charged", "autoliquidacion", False),
    (ingesta.REGIMEN_IVA, "otro", None, True),
    (ingesta.TEXTO, 12, None, True),
])
def test_leer_un_literal(lector, crudo, valor, dudoso) -> None:
    leido = ingesta.leer_literal(lector, crudo)
    assert (leido.valor, leido.dudoso, leido.crudo) == (valor, dudoso, crudo)


def test_el_dinero_de_otra_moneda_no_se_lee() -> None:
    leido = ingesta.leer_literal(ingesta.IMPORTE, "2.500,00", en_euros=False)
    assert (leido.valor, leido.dudoso, leido.crudo) == (None, False, "2.500,00")


def test_tipar_sembrar_y_leer_del_almacen_no_llaman_a_la_api(out_v1, tmp_path) -> None:
    """En un proceso donde `import anthropic` lanza: ingestar, sembrar, export, panel e informe."""
    from test_migracion_out import _sin_api

    db = tmp_path / "datos" / "bms.sqlite3"
    for argumentos in (
        ("importar-out", "--out", str(out_v1), "--pdfs", str(tmp_path / "no"), "--db", str(db)),
        ("ingestar", "--db", str(db)),
        ("sembrar", "--tarifas", str(TARIFAS_V1), "--db", str(db)),
        ("export", "--out", str(out_v1), "--db", str(db), "--file", str(tmp_path / "d.json")),
        ("panel", "--out", str(out_v1), "--db", str(db), "--file", str(tmp_path / "p.html")),
        ("report", "--out", str(out_v1), "--db", str(db), "--file", str(tmp_path / "r.html")),
        ("usuario", "crear", "Ana", "--rol", "consulta", "--db", str(db)),
        ("db", "verificar", "--db", str(db)),
    ):
        proceso = _sin_api(*argumentos)
        assert proceso.returncode == 0, (argumentos, proceso.stdout, proceso.stderr)


# --- correcciones de la revision del paso 2 ---

def _reextraer(almacen, out_v1, nombre: str, registro: dict) -> list:
    (out_v1 / nombre).write_text(json.dumps(registro, indent=2), encoding="utf-8")
    importar_out(almacen, out_v1, None)
    return ingesta.tipar_pendientes(almacen.conn)


def _filas(conn, tabla, factura_id, columnas):
    return [tuple(f) for f in conn.execute(
        f"SELECT {columnas} FROM {tabla} WHERE factura_id = ? ORDER BY id", (factura_id,))]


def test_una_linea_excluida_sigue_excluida_tras_otra_extraccion(tipado, out_v1) -> None:
    conn = tipado.conn
    ana = persona(conn, "Ana", "administracion")
    f = factura_de(conn, "2026-4471")
    segunda = _lineas(conn, f)[1]["id"]
    campos.retirar(conn, "factura_linea", segunda, Persona(ana, "no se factura"))
    antes = _filas(conn, "factura_linea", f, "id, orden, descripcion_doc, huella_linea, retirada_en")
    imputaciones = _filas(conn, "factura_imputacion", f, "id, linea_id, retirada_en")

    nueva = _registro("01-limpia", model="claude-opus-5-5", extracted_at="2026-10-01T08:00:00+00:00")
    [actualizada] = [t for t in _reextraer(tipado, out_v1, "01-limpia-z.json", nueva)
                     if t.accion == "actualizada"]
    assert actualizada.factura_id == f
    # Ni vuelve la excluida, ni se corre ninguna, ni aparece una cuarta.
    assert _filas(conn, "factura_linea", f,
                  "id, orden, descripcion_doc, huella_linea, retirada_en") == antes
    assert _filas(conn, "factura_imputacion", f, "id, linea_id, retirada_en") == imputaciones
    [resuelto] = [r for r in registros_resueltos(conn) if r["source_name"] == "01-limpia.pdf"]
    assert [l["description"] for l in resuelto["extraction"]["lines"]] == [
        "Montagewerk, locatie Rijnhaven", "Reisuren, locatie Schiedam"]
    assert campos.verificar_controladas(conn) == []


def _v2(sha: str, extraido: str, referencias: list, desglose: list, lineas: int = 3,
        referencia_de_linea: dict | None = None) -> dict:
    registro = _registro("01-limpia", source_sha256=sha, source_name="v2.pdf", schema_version="2",
                         extracted_at=extraido)
    x = registro["extraction"]
    x.update(document_type="invoice", currency_raw="EUR", recipient_name=None,
             recipient_vat_number=None, supplier_contact_person=None,
             recipient_contact_person=None, payment_terms_raw=None, related_invoices=None,
             references=referencias, vat_breakdown=desglose)
    x["lines"] = x["lines"][:lineas]
    for indice, linea in enumerate(x["lines"]):
        linea.update(employee_name=None, work_date=None, rate_type_raw=None, vat_rate_raw="21%",
                     order_reference_raw=(referencia_de_linea or {}).get(indice))
    return registro


def _otra_extraccion(almacen, documento_id: int, registro: dict) -> None:
    conn = almacen.conn
    with transaccion(conn):
        registrar_extraccion(conn, leer_registro(json.dumps(registro, indent=2)),
                             documento_id=documento_id, via="api",
                             actor=usuario_sistema(conn, "extractor"))


def test_una_referencia_y_un_iva_editados_no_corren_a_los_demas(almacen) -> None:
    conn = almacen.conn
    referencias = [{"label": "Kenmerk", "value": "A-1"}, {"label": "Kenmerk", "value": "B-2"}]
    desglose = [{"rate_raw": "21%", "base_raw": "2.000,00", "vat_raw": "420,00"},
                {"rate_raw": "9%", "base_raw": "399,00", "vat_raw": "35,91"}]
    documento = _documento_por_ruta(
        almacen, "entrante", _v2("e" * 64, "2026-10-01T08:00:00+00:00", referencias, desglose))
    [tipado] = [t for t in ingesta.tipar_pendientes(conn) if t.documento_id == documento]
    f = tipado.factura_id
    ana = persona(conn, "Ana", "administracion")
    primera = _filas(conn, "factura_referencia", f, "id")[0][0]
    campos.fijar(conn, "factura_referencia", primera, {"clase": "po"}, Persona(ana, "es la PO"))
    iva = _filas(conn, "factura_iva", f, "id")[0][0]
    campos.fijar(conn, "factura_iva", iva, {"rubrica": "1a"}, Persona(ana))

    _otra_extraccion(almacen, documento,
                     _v2("e" * 64, "2026-10-02T08:00:00+00:00", referencias, desglose))
    assert [t.accion for t in ingesta.tipar_pendientes(conn) if t.documento_id == documento] == [
        "actualizada"]
    assert _filas(conn, "factura_referencia", f, "valor_doc, clase, retirada_en") == [
        ("A-1", "po", None), ("B-2", "ref_cliente", None)]
    assert _filas(conn, "factura_iva", f, "tipo_iva_pb, base_cent, rubrica, retirada_en") == [
        (2100, 200000, "1a", None), (900, 39900, None, None)]
    assert campos.verificar_controladas(conn) == []


def test_una_referencia_de_linea_va_a_la_linea_con_la_que_caso(almacen) -> None:
    """Con huecos en orden (una linea que se fue y volvio), la referencia no se pierde."""
    conn = almacen.conn
    documento = _documento_por_ruta(almacen, "entrante",
                                    _v2("f" * 64, "2026-10-01T08:00:00+00:00", [], []))
    ingesta.tipar_pendientes(conn)
    _otra_extraccion(almacen, documento,
                     _v2("f" * 64, "2026-10-02T08:00:00+00:00", [], [], lineas=2))
    ingesta.tipar_pendientes(conn)
    _otra_extraccion(almacen, documento,
                     _v2("f" * 64, "2026-10-03T08:00:00+00:00", [], [],
                         referencia_de_linea={2: "PO 2026-17"}))
    ingesta.tipar_pendientes(conn)
    f = conn.execute("SELECT id FROM factura WHERE documento_id = ?", (documento,)).fetchone()[0]
    activas = [l for l in _lineas(conn, f) if l["retirada_en"] is None]
    assert [l["orden"] for l in activas] == [1, 2, 4]
    [referencia] = conn.execute("SELECT linea_id FROM factura_referencia WHERE factura_id = ?",
                                (f,)).fetchall()
    assert referencia[0] == activas[2]["id"]


def test_una_tarifa_numerica_en_el_yaml_se_siembra(tipado, tmp_path) -> None:
    from bms_agent.facturacion import cargar_tarifas

    fichero = tmp_path / "tarifas.yaml"
    fichero.write_text("obras:\n  Rijnhaven:\n    cliente: Haven BV\n"
                       "tarifas:\n  - {obra: Rijnhaven, trabajo: montagewerk, tarifa: 62.5}\n",
                       encoding="utf-8")
    assert cargar_tarifas(str(fichero)).tarifas[("rijnhaven", "montagewerk")] == Decimal("62.5")
    r = sembrar_tarifas(tipado.conn, fichero)
    assert (r.tarifas_nuevas, r.avisos) == (1, [])
    tarifa = tipado.conn.execute("SELECT id, tarifa_e4 FROM tarifa_acordada").fetchone()
    assert tarifa["tarifa_e4"] == 625000
    assert _p(tipado.conn, "tarifa_acordada", tarifa["id"], "tarifa_e4")[
        "valor_original_crudo"] == "62.5"


def test_importar_out_es_una_sola_transaccion(tmp_path, out_v1, monkeypatch) -> None:
    """Importar y tipar van juntos: si la orden falla al final, no queda nada a medias."""
    from bms_agent.cli import main

    original = ingesta.tipar_pendientes

    def tipar_y_fallar(conn):
        original(conn)
        raise RuntimeError("se fue la luz")

    monkeypatch.setattr(ingesta, "tipar_pendientes", tipar_y_fallar)
    db = tmp_path / "datos" / "bms.sqlite3"
    with pytest.raises(RuntimeError):
        main(["importar-out", "--out", str(out_v1), "--pdfs", str(tmp_path / "no"), "--db", str(db)])
    with preparar(db) as almacen:
        conn = almacen.conn
        assert conn.execute("SELECT count(*) FROM extraccion").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM factura").fetchone()[0] == 0
