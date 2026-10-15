"""Lo que sale del almacen es lo que salia de out/.

La puerta del paso 1: construir_datos(registros_legado(db)) es igual que
construir_datos(load_records(out)) sobre las fixtures v1, y las dos son la
foto de referencia byte a byte.

La del paso 2: lo mismo a traves de registros_resueltos, que saca cada
valor de la factura tipada; y una correccion hecha en el almacen llega al
panel, al informe y a la exportacion sin tocar checks.py ni dashboard.py.
"""

from __future__ import annotations

import json
from collections import Counter

import pytest
from conftest import GOLDEN, TARIFAS_V1

from bms_agent.dashboard import construir_datos
from bms_agent.importadores.extracciones import importar_out
from bms_agent.legado import registros_legado
from bms_agent.report import load_records


def _escribir(out, nombre: str, base: str, **cambios) -> dict:
    registro = json.loads((out / f"{base}.json").read_text(encoding="utf-8"))
    extraccion = cambios.pop("extraction", {})
    registro.update(cambios)
    registro["extraction"].update(extraccion)
    (out / nombre).write_text(json.dumps(registro, indent=2, ensure_ascii=False), encoding="utf-8")
    return registro


def _serializar(datos: dict) -> str:
    return json.dumps(datos, ensure_ascii=False, indent=2) + "\n"


def test_el_panel_desde_el_almacen_es_el_panel_desde_out(almacen, out_v1, pdfs_ejemplo) -> None:
    importar_out(almacen, out_v1, pdfs_ejemplo)
    desde_almacen = construir_datos(registros_legado(almacen.conn), tarifas_path=str(TARIFAS_V1))
    desde_out = construir_datos(load_records(out_v1), tarifas_path=str(TARIFAS_V1))
    assert desde_almacen == desde_out
    foto = (GOLDEN / "construir_datos_v1.json").read_text(encoding="utf-8")
    assert _serializar(desde_almacen) == foto


def test_los_registros_son_los_mismos_diccionarios(almacen, out_v1) -> None:
    importar_out(almacen, out_v1, None)
    clave = lambda r: r["source_sha256"]   # noqa: E731
    assert sorted(registros_legado(almacen.conn), key=clave) == sorted(
        load_records(out_v1), key=clave)


def test_con_varias_extracciones_vale_la_misma_vigente_que_en_out(almacen, out_v1) -> None:
    """La regla de load_records (la mas reciente; en empate, la ultima) es la del almacen."""
    for nombre, cuando in (("02-sin-kvk-btw-verlegd", "2026-10-02T00:00:00+00:00"),
                           ("06-fecha-nl", None)):
        registro = json.loads((out_v1 / f"{nombre}.json").read_text(encoding="utf-8"))
        registro["model"] = "claude-opus-5-5"
        registro["extraction"]["payment_reference"] = f"otra lectura de {nombre}"
        if cuando:
            registro["extracted_at"] = cuando
        (out_v1 / f"{nombre}-z.json").write_text(
            json.dumps(registro, indent=2, ensure_ascii=False), encoding="utf-8")

    importar_out(almacen, out_v1, None)
    vigentes = registros_legado(almacen.conn)
    assert sorted(vigentes, key=lambda r: r["source_sha256"]) == sorted(
        load_records(out_v1), key=lambda r: r["source_sha256"])
    assert len(vigentes) == 7
    referencias = {r["source_name"]: r["extraction"]["payment_reference"] for r in vigentes}
    # La 02 tiene una lectura mas reciente; la 06 empata, y gana el fichero que
    # va despues por nombre ("06-fecha-nl-z" va antes que "06-fecha-nl."): la original.
    assert referencias["02-sin-kvk-btw-verlegd.pdf"] == "otra lectura de 02-sin-kvk-btw-verlegd"
    assert referencias["06-fecha-nl.pdf"] != "otra lectura de 06-fecha-nl"
    assert Counter(json.dumps(r, sort_keys=True) for r in registros_legado(
        almacen.conn, todas=True)) == Counter(
        json.dumps(r, sort_keys=True) for r in load_records(out_v1, todas=True))


def test_el_orden_es_el_de_out_tambien_con_varias_extracciones(almacen, out_v1) -> None:
    """Sin ordenar nada: construir_datos lista las facturas de B2 en el orden en que llegan.

    08-reenvio es la 01 con otro PDF (B2 salta) y zz-01 una lectura mas
    reciente de la 01 en un fichero que va el ultimo: en out/ la 01 sale
    detras de la 08, aunque su documento entrara antes en el almacen.
    """
    _escribir(out_v1, "08-reenvio.json", "01-limpia", source_sha256="8" * 64,
              source_name="08-reenvio.pdf")
    _escribir(out_v1, "zz-01.json", "01-limpia", model="claude-opus-5-5",
              extracted_at="2026-10-01T08:00:00+00:00", extraction={"payment_reference": "ZZ"})
    importar_out(almacen, out_v1, None)

    assert registros_legado(almacen.conn) == load_records(out_v1)
    assert registros_legado(almacen.conn, todas=True) == load_records(out_v1, todas=True)
    desde_almacen = construir_datos(registros_legado(almacen.conn), tarifas_path=str(TARIFAS_V1))
    desde_out = construir_datos(load_records(out_v1), tarifas_path=str(TARIFAS_V1))
    assert desde_almacen == desde_out
    assert [r["source_name"] for r in registros_legado(almacen.conn)][-2:] == [
        "08-reenvio.pdf", "01-limpia.pdf"]


def test_con_fechas_raras_vale_la_regla_de_load_records(almacen, out_v1) -> None:
    """registros_legado aplica la regla de load_records (el texto); la vista, el instante.

    Las dos coinciden con lo que escribe el extractor (UTC con +00:00). Con
    un extracted_at que no es ISO, o con otro offset, load_records compara
    texto: 'sin fecha' gana a '2026-...', y '09:00+02:00' (07:00 UTC) a
    '08:00+00:00'. registros_legado da lo mismo, para que la puerta valga
    con cualquier out/; la vista del almacen ordena por el instante.
    """
    _escribir(out_v1, "01-limpia-b.json", "01-limpia", extracted_at="sin fecha",
              extraction={"payment_reference": "SIN-FECHA"})
    _escribir(out_v1, "02-a.json", "02-sin-kvk-btw-verlegd",
              extracted_at="2026-10-01T09:00:00+02:00", extraction={"payment_reference": "A"})
    _escribir(out_v1, "02-b.json", "02-sin-kvk-btw-verlegd",
              extracted_at="2026-10-01T08:00:00+00:00", extraction={"payment_reference": "B"})
    importar_out(almacen, out_v1, None)

    assert registros_legado(almacen.conn) == load_records(out_v1)
    legado = {r["source_name"]: r["extraction"]["payment_reference"]
              for r in registros_legado(almacen.conn)}
    assert (legado["01-limpia.pdf"], legado["02-sin-kvk-btw-verlegd.pdf"]) == ("SIN-FECHA", "A")

    vista = {f[0]: json.loads(f[1])["extraction"]["payment_reference"] for f in almacen.conn.execute(
        "SELECT d.nombre_original, v.contenido_json FROM v_extraccion_vigente AS v "
        "JOIN documento AS d ON d.id = v.documento_id")}
    assert vista["01-limpia.pdf"] != "SIN-FECHA"         # sin instante, queda la ISO
    assert vista["02-sin-kvk-btw-verlegd.pdf"] == "B"    # 08:00 UTC es despues de 07:00 UTC



# --- paso 2: registros_resueltos ---

def test_la_foto_no_cambia_a_traves_de_registros_resueltos(tipado) -> None:
    from bms_agent.legado import registros_resueltos

    datos = construir_datos(registros_resueltos(tipado.conn), tarifas_path=str(TARIFAS_V1))
    assert _serializar(datos) == (GOLDEN / "construir_datos_v1.json").read_text(encoding="utf-8")


def test_sin_correcciones_los_resueltos_son_los_de_siempre(tipado) -> None:
    from bms_agent.legado import registros_resueltos

    assert registros_resueltos(tipado.conn) == registros_legado(tipado.conn)


def test_con_varias_extracciones_los_resueltos_siguen_a_la_vigente(almacen, out_v1) -> None:
    from bms_agent.ingesta import tipar_pendientes
    from bms_agent.legado import registros_resueltos

    _escribir(out_v1, "08-reenvio.json", "01-limpia", source_sha256="8" * 64,
              source_name="08-reenvio.pdf")
    _escribir(out_v1, "zz-01.json", "01-limpia", model="claude-opus-5-5",
              extracted_at="2026-10-01T08:00:00+00:00",
              extraction={"payment_reference": "ZZ", "invoice_date": "15-09-2026"})
    importar_out(almacen, out_v1, None)
    tipar_pendientes(almacen.conn)
    assert registros_resueltos(almacen.conn) == load_records(out_v1)
    # Llega otra lectura despues de tipar: hasta volver a tipar, la de antes.
    _escribir(out_v1, "zzz-02.json", "02-sin-kvk-btw-verlegd", extracted_at="2026-10-02T08:00:00+00:00",
              extraction={"supplier_name": "J. de Vries Timmerwerken"})
    importar_out(almacen, out_v1, None)
    tipar_pendientes(almacen.conn)
    assert registros_resueltos(almacen.conn) == load_records(out_v1)


def test_una_correccion_llega_al_panel(tipado) -> None:
    from decimal import Decimal

    from conftest import factura_de, persona

    from bms_agent import campos
    from bms_agent.campos import Persona
    from bms_agent.legado import registros_resueltos

    conn = tipado.conn
    ana = persona(conn, "Ana", "administracion")
    antes = construir_datos(registros_resueltos(conn), tarifas_path=str(TARIFAS_V1))
    f = factura_de(conn, "2026-112")
    campos.fijar(conn, "factura", f, {"total_cent": Decimal("700.00"),
                                      "fecha_factura": "2026-09-14"},
                 Persona(ana, "la imprimimos mal"))
    despues = construir_datos(registros_resueltos(conn), tarifas_path=str(TARIFAS_V1))
    fila = next(r for r in despues["filas"] if r["numero"] == "2026-112")
    assert (fila["total"], fila["fecha"], fila["estado"]) == (700.0, "2026-09-14", "critico")
    assert any(m.startswith("Total:") for m in fila["motivos"])           # D4 lo ve
    assert despues["totales"]["importe"] == round(antes["totales"]["importe"] - 653.40 + 700.0, 2)


def test_un_campo_dudoso_verificado_deja_de_avisar(almacen, out_v1) -> None:
    from conftest import factura_de, persona

    from bms_agent import campos
    from bms_agent.campos import Persona
    from bms_agent.ingesta import tipar_pendientes
    from bms_agent.legado import registros_resueltos

    _escribir(out_v1, "01-limpia.json", "01-limpia", extraction={"low_confidence_fields": ["iban"]})
    importar_out(almacen, out_v1, None)
    tipar_pendientes(almacen.conn)
    conn = almacen.conn

    def avisos():
        datos = construir_datos(registros_resueltos(conn), tarifas_path=str(TARIFAS_V1))
        return next(r for r in datos["filas"] if r["numero"] == "2026-4471")["motivos"]

    assert "Lectura dudosa en iban" in avisos()
    campos.verificar_campos(conn, "factura", factura_de(conn, "2026-4471"), ["iban_doc"],
                            Persona(persona(conn, "Ana", "administracion")))
    assert "Lectura dudosa en iban" not in avisos()


def test_un_documento_sin_tipar_no_desaparece(almacen, out_v1) -> None:
    from bms_agent.legado import registros_resueltos, sin_tipar

    importar_out(almacen, out_v1, None)
    assert sin_tipar(almacen.conn) == 7
    assert registros_resueltos(almacen.conn) == registros_legado(almacen.conn)


@pytest.mark.parametrize("texto", [
    "0", "1", "-1", "8740", "8740.00", "0.01", "-101.25", "42.5", "42.125", "-42.125",
    "1042.125", "37.5", "0.0001", "12345678.9012", "999.999", "1000.001",
])
def test_un_valor_corregido_se_escribe_como_parse_amount_lo_lee(texto) -> None:
    from decimal import Decimal

    from bms_agent.legado import literal_decimal
    from bms_agent.parsing import parse_amount

    valor = Decimal(texto)
    assert parse_amount(literal_decimal(valor)) == valor


# --- quien lee del almacen ---

def _crear_almacen(tmp_path, out_v1):
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(tmp_path / "no"),
                 "--db", str(db)]) == 0
    return db


def test_export_lee_del_almacen_y_lo_dice(tmp_path, out_v1, capsys) -> None:
    from bms_agent.cli import main

    db = _crear_almacen(tmp_path, out_v1)
    capsys.readouterr()
    destino = tmp_path / "datos.json"
    assert main(["export", "--out", str(out_v1), "--db", str(db), "--file", str(destino),
                 "--tarifas", str(TARIFAS_V1)]) == 0
    assert f"Leyendo del almacen {db}" in capsys.readouterr().out
    foto = (GOLDEN / "construir_datos_v1.json").read_text(encoding="utf-8")
    assert json.loads(destino.read_text(encoding="utf-8")) == json.loads(foto)


def test_sin_almacen_se_lee_out_y_se_dice(tmp_path, out_v1, capsys) -> None:
    from bms_agent.cli import main

    destino = tmp_path / "datos.json"
    db = tmp_path / "no-hay" / "bms.sqlite3"
    assert main(["export", "--out", str(out_v1), "--db", str(db), "--file", str(destino),
                 "--tarifas", str(TARIFAS_V1)]) == 0
    salida = capsys.readouterr().out
    assert f"No hay almacen en {db}" in salida and "sin correcciones" in salida
    assert not db.exists()
    assert json.loads(destino.read_text(encoding="utf-8")) == json.loads(
        (GOLDEN / "construir_datos_v1.json").read_text(encoding="utf-8"))


def test_panel_e_informe_ensenan_lo_corregido(tmp_path, out_v1, capsys) -> None:
    from decimal import Decimal

    from conftest import factura_de

    from bms_agent import campos, permisos
    from bms_agent.almacen import preparar
    from bms_agent.campos import Persona
    from bms_agent.cli import main

    db = _crear_almacen(tmp_path, out_v1)
    with preparar(db) as almacen:
        conn = almacen.conn
        permisos.asegurar_roles_base(conn)
        ana = permisos.crear_usuario(conn, "Ana")
        permisos.asignar_rol(conn, ana, "administracion")
        campos.fijar(conn, "factura", factura_de(conn, "2026-4471"),
                     {"emisor_nombre_doc": "Van Dijk Corregido BV",
                      "total_cent": Decimal("2902.79")}, Persona(ana, "nombre del maestro"))
    panel, informe = tmp_path / "panel.html", tmp_path / "informe.html"
    assert main(["panel", "--out", str(out_v1), "--db", str(db), "--file", str(panel),
                 "--tarifas", str(TARIFAS_V1)]) == 0
    assert main(["report", "--out", str(out_v1), "--db", str(db), "--file", str(informe)]) == 0
    assert main(["simulador", "--out", str(out_v1), "--db", str(db),
                 "--file", str(tmp_path / "sim.html"), "--tarifas", str(TARIFAS_V1)]) == 0
    assert "Van Dijk Corregido BV" in panel.read_text(encoding="utf-8")
    assert "Van Dijk Corregido BV" in informe.read_text(encoding="utf-8")
    assert capsys.readouterr().out.count("Leyendo del almacen") == 3


def test_api_datos_lee_del_almacen(tmp_path, out_v1) -> None:
    import http.client
    import threading

    from bms_agent.almacen import preparar
    from bms_agent.legado import registros_resueltos
    from bms_agent.serve import crear_servidor

    db = _crear_almacen(tmp_path, out_v1)
    srv = crear_servidor(tmp_path / "facturas", tmp_path / "vacio", 0, ruta_db=db)
    hilo = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    hilo.start()
    try:
        puerto = srv.server_address[1]
        conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=5)
        conexion.request("GET", "/api/datos", headers={"Host": f"127.0.0.1:{puerto}"})
        cuerpo = json.loads(conexion.getresponse().read())
        conexion.close()
    finally:
        srv.shutdown()
        srv.server_close()
    with preparar(db) as almacen:
        esperado = construir_datos(registros_resueltos(almacen.conn))
    assert cuerpo == json.loads(json.dumps(esperado)) and len(cuerpo["filas"]) == 7
