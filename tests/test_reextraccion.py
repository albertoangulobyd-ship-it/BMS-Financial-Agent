"""La reextraccion del paso 6: con presupuesto, como candidata y con la puerta.

Ningun test llama a la API. El cliente falso hace de anthropic.Anthropic:
cuenta lo que se pagaria (parse y los lotes) aparte de lo que no se cobra
(count_tokens), y devuelve lecturas v2 hechas a partir de las fixtures v1.
"""

from __future__ import annotations

import copy
import itertools
import json
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import FIXTURES_V1, INSTANTE_FIJO, factura_de, persona

from bms_agent import campos, compat, config, reextraccion
from bms_agent.almacen import transaccion
from bms_agent.almacen.evidencia import verificar_evidencia
from bms_agent.campos import Persona
from bms_agent.extract import ExtractionRecord
from bms_agent.importadores.extracciones import importar_out
from bms_agent.ingesta import tipar_pendientes, vigentes_por_documento
from bms_agent.legado import registros_resueltos
from bms_agent.permisos import PermisoDenegado
from bms_agent.schema import InvoiceExtraction

_PETICIONES = itertools.count(1)
OBJETIVO = (config.DEFAULT_MODEL, config.PROMPT_VERSION, config.SCHEMA_VERSION)


def lectura_v2(nombre: str, **cambios) -> dict:
    """La extraccion v1 fija de `nombre`, subida a v2 con lo que v1 no pedia rellenado."""
    registro = json.loads((FIXTURES_V1 / f"{nombre}.json").read_text(encoding="utf-8"))
    datos = compat.leer_registro(registro).datos
    for clave in compat.CAMPOS_V2_CABECERA:
        if datos[clave] is None:
            datos[clave] = {"document_type": "invoice", "related_invoices": [], "references": [],
                            "vat_breakdown": []}.get(clave)
    datos.update(cambios)
    return datos


class ClienteFalso:
    """anthropic.Anthropic sin red: cuenta lo que se pagaria y lo que solo se cuenta."""

    def __init__(self, lecturas: dict[str, dict] | None = None, *, falla: set[str] = frozenset(),
                 tokens: int = 3000, salida: int = 2400) -> None:
        self.lecturas = lecturas or {}
        self.falla = set(falla)
        self.rechaza: set[str] = set()
        self.tokens = tokens
        self.salida = salida
        self.pagadas = 0          # parse: se cobra
        self.conteos = 0          # count_tokens: no se cobra
        self.lotes: list[list[dict]] = []
        self.peticiones: list[dict] = []
        self.messages = self
        self.batches = _Lotes(self)

    def count_tokens(self, **peticion):
        assert not {"tools", "tool_choice", "mcp_servers"} & set(peticion)
        assert "max_tokens" not in peticion
        self.conteos += 1
        return SimpleNamespace(input_tokens=self.tokens)

    def parse(self, **peticion):
        assert not {"tools", "tool_choice", "mcp_servers"} & set(peticion)
        self.pagadas += 1
        self.peticiones.append(peticion)
        nombre = peticion["messages"][0]["content"][0]["source"]["data"]
        sha = _sha_de(nombre)
        if sha in self.falla:
            raise RuntimeError("overloaded")
        if sha in self.rechaza:
            return SimpleNamespace(stop_reason="refusal", parsed_output=None,
                                   stop_details=SimpleNamespace(category="cyber"),
                                   usage=SimpleNamespace(input_tokens=self.tokens,
                                                         output_tokens=10))
        return SimpleNamespace(
            stop_reason="end_turn",
            parsed_output=InvoiceExtraction.model_validate(self.lecturas[sha]),
            usage=SimpleNamespace(input_tokens=self.tokens, output_tokens=self.salida),
            _request_id=f"req_falso_{next(_PETICIONES)}")


def _sha_de(data_b64: str) -> str:
    import base64
    import hashlib

    return hashlib.sha256(base64.standard_b64decode(data_b64)).hexdigest()


class _Lotes:
    """messages.batches: crea, dice si termino y da resultados en cualquier orden."""

    def __init__(self, cliente: ClienteFalso) -> None:
        self.cliente = cliente
        self.terminado = False
        self.resultados: list = []
        self.error: Exception | None = None    # lo que lanza create, despues de crearlo o no
        self.crea_aunque_falle = False
        self.creados: list = []

    def create(self, *, requests):
        for peticion in requests:
            assert not {"tools", "tool_choice", "mcp_servers"} & set(peticion["params"])
        if self.error is not None and not self.crea_aunque_falle:
            raise self.error
        self.cliente.lotes.append(list(requests))
        lote = SimpleNamespace(id=f"msgbatch_falso_{len(self.cliente.lotes)}",
                               processing_status="in_progress",
                               created_at=INSTANTE_FIJO,
                               request_counts=SimpleNamespace(
                                   processing=len(requests), succeeded=0, errored=0,
                                   canceled=0, expired=0))
        self.creados.append(lote)
        if self.error is not None:
            raise self.error
        return lote

    def list(self, **_opciones):
        return list(reversed(self.creados))

    def retrieve(self, lote_id):
        return SimpleNamespace(id=lote_id,
                               processing_status="ended" if self.terminado else "in_progress")

    def results(self, lote_id):
        return list(reversed(self.resultados))


def resultado_lote(sha: str, tipo: str = "succeeded", *, datos: dict | None = None,
                   texto: str | None = None, stop_reason: str = "end_turn"):
    if tipo != "succeeded":
        error = SimpleNamespace(type="error", error=SimpleNamespace(
            type="api_error", message="fallo del servidor"))
        return SimpleNamespace(custom_id=sha, result=SimpleNamespace(type=tipo, error=error))
    contenido = texto if texto is not None else json.dumps(datos)
    mensaje = SimpleNamespace(
        stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=contenido)],
        usage=SimpleNamespace(input_tokens=3000, output_tokens=2000))
    return SimpleNamespace(custom_id=sha, result=SimpleNamespace(type="succeeded",
                                                                 message=mensaje))


@pytest.fixture
def con_pdfs(almacen, out_v1, pdfs_ejemplo):
    """Las siete fixtures v1 tipadas; las tres primeras con su PDF en el almacen de documentos."""
    importar_out(almacen, out_v1, pdfs_ejemplo)
    tipar_pendientes(almacen.conn)
    return almacen


def _shas(conn) -> dict[str, str]:
    return {f["nombre_original"]: f["sha256"] for f in conn.execute(
        "SELECT nombre_original, sha256 FROM documento")}


def _lecturas(conn, **por_nombre) -> dict[str, dict]:
    shas = _shas(conn)
    lecturas = {shas[f"{n}.pdf"]: lectura_v2(n) for n in
                ("01-limpia", "02-sin-kvk-btw-verlegd", "03-con-inyeccion")}
    for nombre, datos in por_nombre.items():
        lecturas[shas[f"{nombre}.pdf"]] = datos
    return lecturas


def _pasada(almacen, cliente, tmp_path, *, presupuesto="10", lote=False, **criterio):
    conn = almacen.conn
    seleccion = reextraccion.seleccionar(conn, reextraccion.Criterio(**criterio), OBJETIVO)
    documentos = reextraccion.cargar(almacen, seleccion)
    estimacion = reextraccion.estimar(cliente, conn, documentos, OBJETIVO, lote=lote)
    return reextraccion.ejecutar(
        cliente, almacen, seleccion, documentos, estimacion,
        reextraccion.leer_presupuesto(presupuesto), criterio=reextraccion.Criterio(**criterio),
        objetivo=OBJETIVO, out_dir=tmp_path / "salida", lote=lote)


VERDAD = {
    "01-limpia.pdf": {"supplier_name": "Bouwtechniek Van Dijk BV", "invoice_number": "2026-4471",
                      "invoice_date": "2026-09-15", "vat_amount": "503,79",
                      "total_incl_vat": "2.902,79", "service_period_start": "2026-08-31",
                      "service_period_end": "2026-09-06", "document_type": "invoice"},
    "02-sin-kvk-btw-verlegd.pdf": {"supplier_name": "J. de Vries", "invoice_number": "2026-018",
                                   "total_incl_vat": "1.520,00"},
    "03-con-inyeccion.pdf": {"supplier_name": "Elektro Installatie Koster",
                             "invoice_number": "2026-0912", "iban": "NL75INGB0002445689"},
}


# ------------------------------------------------------------ seleccion y presupuesto


def test_la_seleccion_no_vuelve_a_pagar_lo_leido_ni_lo_que_no_tiene_original(con_pdfs) -> None:
    conn = con_pdfs.conn
    seleccion = reextraccion.seleccionar(conn, reextraccion.Criterio(abiertas=True), OBJETIVO)
    assert sorted(d.nombre for d in seleccion.documentos) == [
        "01-limpia.pdf", "02-sin-kvk-btw-verlegd.pdf", "03-con-inyeccion.pdf"]
    # Las 04 a 07 no tienen original: no se pueden volver a leer, y se dice.
    assert len(seleccion.omitidos) == 4
    assert all("original" in motivo for _d, motivo in seleccion.omitidos)
    assert all(d.anterior_id is not None for d in seleccion.documentos)

    limitada = reextraccion.seleccionar(conn, reextraccion.Criterio(abiertas=True, limite=1),
                                        OBJETIVO)
    assert len(limitada.documentos) == 1
    proveedor = reextraccion.seleccionar(conn, reextraccion.Criterio(proveedor="j. de vries"),
                                         OBJETIVO)
    assert [d.nombre for d in proveedor.documentos] == ["02-sin-kvk-btw-verlegd.pdf"]
    desde = reextraccion.seleccionar(conn, reextraccion.Criterio(
        desde=__import__("datetime").date(2026, 9, 14)), OBJETIVO)
    assert [d.nombre for d in desde.documentos] == ["01-limpia.pdf", "03-con-inyeccion.pdf"]
    with pytest.raises(ValueError, match="criterio"):
        reextraccion.seleccionar(conn, reextraccion.Criterio(), OBJETIVO)


def test_sin_objeto_elige_las_facturas_con_una_linea_sin_imputar(con_pdfs) -> None:
    from bms_agent.importadores.tarifas import sembrar_tarifas
    from conftest import TARIFAS_V1

    conn = con_pdfs.conn
    todas = reextraccion.seleccionar(conn, reextraccion.Criterio(sin_objeto=True), OBJETIVO)
    assert len(todas.documentos) == 3          # sin maestro, ninguna linea tiene Objeto
    sembrar_tarifas(conn, TARIFAS_V1)
    despues = reextraccion.seleccionar(conn, reextraccion.Criterio(sin_objeto=True), OBJETIVO)
    assert len(despues.documentos) < 3


def test_estimar_cuenta_la_entrada_y_no_paga_nada(con_pdfs) -> None:
    conn = con_pdfs.conn
    cliente = ClienteFalso(_lecturas(conn))
    seleccion = reextraccion.seleccionar(conn, reextraccion.Criterio(abiertas=True), OBJETIVO)
    documentos = reextraccion.cargar(con_pdfs, seleccion)
    estimacion = reextraccion.estimar(cliente, conn, documentos, OBJETIVO, lote=False)
    assert (cliente.conteos, cliente.pagadas) == (3, 0)
    assert estimacion.entrada == 3 * 3000
    # Sin historico v2, la salida es la mediana de v1 por el factor declarado: sin medir.
    assert not estimacion.salida_medida and "sin medir" in estimacion.origen_salida
    assert estimacion.salida_baja == 3 * 2 * 702 and estimacion.salida_alta == 3 * 4 * 702
    por_lotes = reextraccion.estimar(cliente, conn, documentos, OBJETIVO, lote=True)
    assert por_lotes.coste_alto == estimacion.coste_alto / 2


def test_por_encima_del_presupuesto_no_se_paga_nada(con_pdfs, tmp_path) -> None:
    conn = con_pdfs.conn
    cliente = ClienteFalso(_lecturas(conn))
    antes = conn.execute("SELECT count(*) FROM extraccion").fetchone()[0]
    with pytest.raises(reextraccion.PresupuestoInsuficiente):
        _pasada(con_pdfs, cliente, tmp_path, presupuesto="0.05", abiertas=True)
    assert cliente.pagadas == 0
    assert conn.execute("SELECT count(*) FROM extraccion").fetchone()[0] == antes
    assert conn.execute("SELECT count(*) FROM reextraccion").fetchone()[0] == 0


def test_la_base_no_admite_una_estimacion_alta_por_encima_del_presupuesto(con_pdfs) -> None:
    import sqlite3

    from bms_agent.almacen import usuario_sistema

    conn = con_pdfs.conn
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"), transaccion(conn):
        conn.execute(
            "INSERT INTO reextraccion (modelo, prompt_version, schema_version, via, "
            "criterio_json, documentos, presupuesto_usd_cent, estimado_bajo_usd_cent, "
            "estimado_alto_usd_cent, salida_medida, estimacion_json, iniciada_en, actor) "
            "VALUES ('m', 'p', '2', 'api', '{}', 1, 100, 50, 101, 0, '{}', "
            "'2026-10-14T09:30:00+00:00', ?)", (usuario_sistema(conn, "extractor"),))


def test_un_limite_que_no_es_positivo_no_selecciona_nada(con_pdfs, capsys, monkeypatch) -> None:
    with pytest.raises(ValueError, match="limite"):
        reextraccion.seleccionar(con_pdfs.conn, reextraccion.Criterio(abiertas=True, limite=0),
                                 OBJETIVO)


def test_el_presupuesto_se_escribe_en_dolares_con_dos_decimales() -> None:
    assert reextraccion.leer_presupuesto("12,50") == Decimal("12.50")
    for malo in ("-1", "1.005", "diez", "NaN"):
        with pytest.raises(ValueError):
            reextraccion.leer_presupuesto(malo)


# ------------------------------------------------------------ candidatas


def test_lo_que_se_vuelve_a_leer_queda_como_candidata_y_no_cambia_nada(con_pdfs, tmp_path) -> None:
    conn = con_pdfs.conn
    shas = _shas(conn)
    otra = lectura_v2("01-limpia", total_incl_vat_raw="2.902,80")
    cliente = ClienteFalso(_lecturas(conn, **{"01-limpia": otra}))
    vigentes = vigentes_por_documento(conn)
    resueltos = registros_resueltos(conn)

    r = _pasada(con_pdfs, cliente, tmp_path, abiertas=True)
    assert (r.estado, len(r.candidatas), r.reintentos) == ("terminada", 3, [])
    assert cliente.pagadas == 3
    # Nada vigente cambia: las facturas, sus valores y lo que lee el panel siguen igual.
    assert vigentes_por_documento(conn) == vigentes
    assert registros_resueltos(conn) == resueltos
    assert [t.accion for t in tipar_pendientes(conn)] == ["sin_cambios"] * 7
    # Exportadas fuera de out/ (no cuentan como vigentes sin almacen), por hash y versiones.
    exportadas = sorted((tmp_path / "salida" / "reextraccion").glob("*.json"))
    assert len(exportadas) == 3 and not list((tmp_path / "salida").glob("*.json"))
    assert all("__s2.json" in p.name for p in exportadas)
    # Volver a pedirlo no paga otra vez: ya hay una extraccion de estas versiones.
    segunda = reextraccion.seleccionar(conn, reextraccion.Criterio(abiertas=True), OBJETIVO)
    assert segunda.documentos == [] and segunda.ya_leidos == 3
    assert verificar_evidencia(conn) == []
    assert shas["01-limpia.pdf"] in {json.loads(p.read_text())["source_sha256"]
                                     for p in exportadas}


def test_un_documento_que_falla_va_a_reintentos_y_se_puede_pedir_otra_vez(
        con_pdfs, tmp_path) -> None:
    conn = con_pdfs.conn
    shas = _shas(conn)
    cliente = ClienteFalso(_lecturas(conn), falla={shas["02-sin-kvk-btw-verlegd.pdf"]})
    r = _pasada(con_pdfs, cliente, tmp_path, abiertas=True)
    assert len(r.candidatas) == 2 and [m for _d, m, _x in r.reintentos] == ["error"]
    fila = conn.execute("SELECT * FROM reextraccion").fetchone()
    assert (fila["estado"], fila["extraidas"], fila["reintentos"]) == ("terminada", 2, 1)

    cliente.falla.clear()
    otra = _pasada(con_pdfs, cliente, tmp_path, reintentos=True)
    assert [d for d, _e in otra.candidatas] == [
        conn.execute("SELECT id FROM documento WHERE sha256 = ?",
                     (shas["02-sin-kvk-btw-verlegd.pdf"],)).fetchone()[0]]
    assert reextraccion.seleccionar(conn, reextraccion.Criterio(reintentos=True),
                                    OBJETIVO).documentos == []


def test_un_rechazo_del_modelo_es_un_reintento_con_su_motivo(con_pdfs, tmp_path) -> None:
    conn = con_pdfs.conn
    cliente = ClienteFalso(_lecturas(conn))
    cliente.rechaza.add(_shas(conn)["03-con-inyeccion.pdf"])
    r = _pasada(con_pdfs, cliente, tmp_path, abiertas=True)
    assert [(m, "cyber" in d) for _doc, m, d in r.reintentos] == [("rechazo", True)]
    assert len(r.candidatas) == 2


def test_por_lotes_se_manda_y_se_recoge_con_cada_resultado_en_su_sitio(con_pdfs, tmp_path) -> None:
    conn = con_pdfs.conn
    shas = _shas(conn)
    cliente = ClienteFalso(_lecturas(conn))
    r = _pasada(con_pdfs, cliente, tmp_path, lote=True, abiertas=True)
    assert (r.estado, cliente.pagadas, len(cliente.lotes)) == ("esperando_lote", 0, 1)
    peticiones = cliente.lotes[0]
    assert {p["custom_id"] for p in peticiones} == {shas[n] for n in (
        "01-limpia.pdf", "02-sin-kvk-btw-verlegd.pdf", "03-con-inyeccion.pdf")}
    assert all(p["params"]["output_config"]["format"]["type"] == "json_schema"
               for p in peticiones)

    # Sin terminar, recoger no cambia nada.
    assert reextraccion.recoger(cliente, con_pdfs, r.reextraccion_id,
                                out_dir=tmp_path / "salida").estado == "esperando_lote"
    cliente.batches.terminado = True
    cliente.batches.resultados = [
        resultado_lote(shas["01-limpia.pdf"], datos=lectura_v2("01-limpia")),
        resultado_lote(shas["02-sin-kvk-btw-verlegd.pdf"], "expired"),
        resultado_lote(shas["03-con-inyeccion.pdf"], texto='{"supplier_name": "corta',
                       stop_reason="max_tokens"),
    ]
    recogida = reextraccion.recoger(cliente, con_pdfs, r.reextraccion_id,
                                    out_dir=tmp_path / "salida")
    assert recogida.estado == "terminada" and len(recogida.candidatas) == 1
    assert sorted(m for _d, m, _x in recogida.reintentos) == ["caducado", "invalido"]
    [candidata] = conn.execute("SELECT * FROM extraccion WHERE via = 'lote'").fetchall()
    assert json.loads(candidata["uso_json"])["service_tier"] == "batch"
    assert verificar_evidencia(conn) == []
    with pytest.raises(ValueError, match="no espera"):
        reextraccion.recoger(cliente, con_pdfs, r.reextraccion_id, out_dir=tmp_path / "salida")


# ------------------------------------------------------------ la puerta y la activacion


def _admin(conn) -> int:
    return persona(conn, "Ada", "administrador")


def test_sin_pasar_la_puerta_no_se_activa_nada(con_pdfs, tmp_path) -> None:
    conn = con_pdfs.conn
    mala = lectura_v2("03-con-inyeccion", iban="NL91 ABNA 0417 1643 00")
    cliente = ClienteFalso(_lecturas(conn, **{"03-con-inyeccion": mala}))
    _pasada(con_pdfs, cliente, tmp_path, abiertas=True)
    vigentes = vigentes_por_documento(conn)
    with pytest.raises(reextraccion.PuertaCerrada) as error:
        reextraccion.activar(con_pdfs, _admin(conn), VERDAD, objetivo=OBJETIVO)
    assert any("inyeccion" in m for m in error.value.comparacion.motivos)
    assert vigentes_por_documento(conn) == vigentes
    assert conn.execute("SELECT count(*) FROM activacion").fetchone()[0] == 0
    rechazo = conn.execute("SELECT * FROM evento WHERE tipo = 'activacion_rechazada'").fetchone()
    assert rechazo["resultado"] == "denegado"


def test_activar_pide_admin(con_pdfs, tmp_path) -> None:
    conn = con_pdfs.conn
    _pasada(con_pdfs, ClienteFalso(_lecturas(conn)), tmp_path, abiertas=True)
    consulta = persona(conn, "Coro", "administracion")
    with pytest.raises(PermisoDenegado):
        reextraccion.activar(con_pdfs, consulta, VERDAD, objetivo=OBJETIVO)
    assert conn.execute("SELECT count(*) FROM activacion").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM evento WHERE tipo = 'permiso_denegado'"
                        ).fetchone()[0] == 1


def test_al_activar_lo_manual_no_se_pisa_y_lo_contradicho_queda_sin_resolver(
        con_pdfs, tmp_path) -> None:
    """La puerta: M1 en cada valor manual que la lectura nueva contradice."""
    conn = con_pdfs.conn
    ana = persona(conn, "Ana", "administracion")
    f = factura_de(conn, "2026-4471")
    campos.fijar(conn, "factura", f, {"referencia_pago": "RF-9"}, Persona(ana))
    campos.fijar(conn, "factura", f, {"emisor_kvk_doc": "87654322"}, Persona(ana, "mal leido"))
    nueva = lectura_v2("01-limpia", payment_reference="RF-1", kvk_number="87654322",
                       recipient_name="BMS Support BV", payment_terms_raw="Betaling binnen 30 "
                                                                         "dagen")
    _pasada(con_pdfs, ClienteFalso(_lecturas(conn, **{"01-limpia": nueva})), tmp_path,
            abiertas=True)

    resultado = reextraccion.activar(con_pdfs, _admin(conn), VERDAD, objetivo=OBJETIVO)
    assert resultado.comparacion.aprobada and len(resultado.activadas) == 3
    [de_01] = [a for a in resultado.activadas if a.factura_id == f]
    assert f"factura:{f}:referencia_pago" in de_01.contradichos
    assert f"factura:{f}:emisor_kvk_doc" not in de_01.contradichos   # lee lo mismo que Ana
    kvk = campos.procedencia(conn, "factura", f)["emisor_kvk_doc"]
    assert not campos.estado_campo(kvk).sin_resolver
    fila = campos.leer(conn, "factura", f)
    assert fila["referencia_pago"] == "RF-9"                          # lo manual se queda
    assert fila["receptor_nombre_doc"] == "BMS Support BV"            # lo que v1 no pedia
    assert fila["plazo_pago_dias"] == 30
    referencia = campos.procedencia(conn, "factura", f)["referencia_pago"]
    assert campos.estado_campo(referencia).sin_resolver
    estado = conn.execute("SELECT sin_resolver FROM factura_estado WHERE factura_id = ?",
                          (f,)).fetchone()[0]
    assert estado >= 1
    # Ya es la vigente, y tipar otra vez no cambia nada.
    assert vigentes_por_documento(conn)[de_01.documento_id] == de_01.extraccion_id
    assert {t.accion for t in tipar_pendientes(conn)} == {"sin_cambios"}
    assert campos.verificar_controladas(conn) == []
    assert verificar_evidencia(conn) == []


def test_al_activar_las_ediciones_de_linea_van_a_su_linea_por_la_huella(con_pdfs, tmp_path) -> None:
    """Una linea nueva delante no corre las ediciones a la de al lado."""
    conn = con_pdfs.conn
    ana = persona(conn, "Ana", "administracion")
    f = factura_de(conn, "2026-4471")
    lineas = conn.execute("SELECT id, descripcion_doc FROM factura_linea WHERE factura_id = ? "
                          "ORDER BY orden", (f,)).fetchall()
    tercera = lineas[2]["id"]
    campos.fijar(conn, "factura_linea", tercera, {"objeto_doc": "Schiedam-Oost"},
                 Persona(ana, "es la obra de Oost"))
    nueva = lectura_v2("01-limpia")
    extra = copy.deepcopy(nueva["lines"][0])
    extra.update(description="Toeslag avond, locatie Rijnhaven", line_total_raw="50,00",
                 quantity_raw="1", unit="stuk", unit_rate_raw="50,00")
    nueva["lines"].insert(0, extra)
    _pasada(con_pdfs, ClienteFalso(_lecturas(conn, **{"01-limpia": nueva})), tmp_path,
            abiertas=True)

    resultado = reextraccion.activar(con_pdfs, _admin(conn), VERDAD, objetivo=OBJETIVO)
    [de_01] = [a for a in resultado.activadas if a.factura_id == f]
    assert de_01.sin_casar == ()
    despues = {l["id"]: l for l in conn.execute(
        "SELECT * FROM factura_linea WHERE factura_id = ? AND retirada_en IS NULL", (f,))}
    assert len(despues) == 4
    assert despues[tercera]["descripcion_doc"] == "Reisuren, locatie Schiedam"
    assert despues[tercera]["objeto_doc"] == "Schiedam-Oost"      # la edicion, en su linea
    assert all(despues[l["id"]]["descripcion_doc"] == l["descripcion_doc"] for l in lineas)
    assert not [h for h in conn.execute("SELECT regla FROM hallazgo WHERE regla = 'M2'")]


def test_una_edicion_que_no_se_puede_casar_es_un_hallazgo(con_pdfs, tmp_path) -> None:
    conn = con_pdfs.conn
    ana = persona(conn, "Ana", "administracion")
    f = factura_de(conn, "2026-4471")
    lineas = conn.execute("SELECT id FROM factura_linea WHERE factura_id = ? ORDER BY orden",
                          (f,)).fetchall()
    tercera, segunda = lineas[2]["id"], lineas[1]["id"]
    campos.fijar(conn, "factura_linea", tercera, {"objeto_doc": "Schiedam-Oost"},
                 Persona(ana, "es la obra de Oost"))
    campos.retirar(conn, "factura_linea", segunda, Persona(ana, "no se factura"))
    nueva = lectura_v2("01-limpia")
    # La lectura nueva lee distinta la tercera, y la segunda con otro importe.
    nueva["lines"][2].update(description="Reiskosten Schiedam", line_total_raw="101,30")
    nueva["lines"][1].update(line_total_raw="704,10")
    _pasada(con_pdfs, ClienteFalso(_lecturas(conn, **{"01-limpia": nueva})), tmp_path,
            abiertas=True)

    resultado = reextraccion.activar(con_pdfs, _admin(conn), VERDAD, objetivo=OBJETIVO)
    [de_01] = [a for a in resultado.activadas if a.factura_id == f]
    assert sorted(de_01.sin_casar) == sorted([segunda, tercera])
    apuntes = {r["linea_id"]: r for r in conn.execute("SELECT * FROM linea_sin_casar")}
    assert (apuntes[segunda]["excluida"], apuntes[tercera]["excluida"]) == (1, 0)
    hallazgos = {r["clave"]: r for r in conn.execute(
        "SELECT * FROM hallazgo WHERE regla = 'M2'")}
    assert set(hallazgos) == {f"M2|factura:{f}|linea:{segunda}", f"M2|factura:{f}|linea:{tercera}"}
    assert all(h["estado"] == "abierto" and h["severidad"] == "retencion"
               for h in hallazgos.values())
    # Se conservan tal cual: nada de lo que escribio Ana se pierde.
    assert campos.leer(conn, "factura_linea", tercera)["objeto_doc"] == "Schiedam-Oost"
    assert campos.leer(conn, "factura_linea", tercera)["retirada_en"] is None

    # Excluirla (ya no existe) cierra su hallazgo; la excluida antes pide una anulacion.
    from bms_agent.hallazgos import recalcular

    campos.retirar(conn, "factura_linea", tercera, Persona(ana, "es la misma que la nueva"))
    recalcular(conn)
    estados = {r["clave"]: r["estado"] for r in conn.execute(
        "SELECT clave, estado FROM hallazgo WHERE regla = 'M2'")}
    assert estados[f"M2|factura:{f}|linea:{tercera}"] == "cerrado"
    assert estados[f"M2|factura:{f}|linea:{segunda}"] == "abierto"
    assert verificar_evidencia(conn) == []


def test_db_verificar_ve_una_activacion_metida_por_detras(con_pdfs, tmp_path) -> None:
    conn = con_pdfs.conn
    _pasada(con_pdfs, ClienteFalso(_lecturas(conn)), tmp_path, abiertas=True)
    reextraccion.activar(con_pdfs, _admin(conn), VERDAD, objetivo=OBJETIVO)
    conn.execute("DROP TRIGGER activacion_sin_update")
    conn.execute("UPDATE activacion SET comparacion_sha256 = ? WHERE id = 1", ("0" * 64,))
    assert any("activacion 1" in p for p in verificar_evidencia(conn))


def test_un_registro_v2_exportado_es_un_registro_de_extraccion_valido(con_pdfs, tmp_path) -> None:
    conn = con_pdfs.conn
    _pasada(con_pdfs, ClienteFalso(_lecturas(conn)), tmp_path, abiertas=True)
    for ruta in (tmp_path / "salida" / "reextraccion").glob("*.json"):
        registro = json.loads(ruta.read_text(encoding="utf-8"))
        assert set(registro) == set(ExtractionRecord(
            "0" * 64, "x.pdf", "m", "p", "2", "",
            InvoiceExtraction.model_validate(registro["extraction"])).to_dict())
        assert (registro["model"], registro["prompt_version"], registro["schema_version"]) == \
            OBJETIVO
        assert compat.leer_registro(registro).no_solicitados == frozenset()


# ------------------------------------------------------------ por la CLI


def test_por_la_cli_estima_paga_con_presupuesto_y_activa_con_la_puerta(
        tmp_path, out_v1, pdfs_ejemplo, monkeypatch, capsys) -> None:
    import anthropic
    import yaml

    from bms_agent.almacen import preparar
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(pdfs_ejemplo),
                 "--db", str(db)]) == 0
    with preparar(db) as almacen:
        cliente = ClienteFalso(_lecturas(almacen.conn))
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: cliente)
    salida = tmp_path / "salida"
    capsys.readouterr()

    # Sin presupuesto: solo cuenta.
    assert main(["reextraer", "--abiertas", "--db", str(db), "--out", str(salida)]) == 0
    texto = capsys.readouterr().out
    assert "seleccionados: 3; omitidos: 4" in texto and "Sin --presupuesto" in texto
    assert (cliente.conteos, cliente.pagadas) == (3, 0)

    # Por encima del presupuesto: nada, y queda en la auditoria.
    assert main(["reextraer", "--abiertas", "--presupuesto", "0.01", "--db", str(db),
                 "--out", str(salida)]) == 1
    assert "No se paga" in capsys.readouterr().err
    assert cliente.pagadas == 0
    with preparar(db) as almacen:
        assert almacen.conn.execute("SELECT count(*) FROM evento WHERE tipo = "
                                    "'reextraccion_rechazada'").fetchone()[0] == 1

    # Con presupuesto: tres candidatas, que no son vigentes.
    assert main(["reextraer", "--abiertas", "--presupuesto", "5", "--db", str(db),
                 "--out", str(salida)]) == 0
    assert "3 candidatas" in capsys.readouterr().out
    assert cliente.pagadas == 3

    # score --comparar-versiones lee el almacen y dice si pasa la puerta.
    verdad = tmp_path / "respuestas.yaml"
    verdad.write_text(yaml.safe_dump(VERDAD, allow_unicode=True), encoding="utf-8")
    assert main(["score", "--comparar-versiones", "--ground-truth", str(verdad),
                 "--db", str(db)]) == 0
    assert "PUERTA: la version nueva puede pasar a vigente." in capsys.readouterr().out

    # Activar pide el token de una persona con admin.
    assert main(["reextraer", "--activar", "--ground-truth", str(verdad), "--db", str(db)]) == 1
    capsys.readouterr()
    assert main(["usuario", "crear", "Ada", "--rol", "administrador", "--db", str(db)]) == 0
    capsys.readouterr()
    assert main(["usuario", "token", "Ada", "--db", str(db)]) == 0
    token = capsys.readouterr().out.splitlines()[1].strip()
    assert main(["reextraer", "--activar", "--ground-truth", str(verdad), "--token", token,
                 "--db", str(db)]) == 0
    assert "Activadas: 3" in capsys.readouterr().out
    with preparar(db) as almacen:
        conn = almacen.conn
        activas = {f[0] for f in conn.execute("SELECT extraccion_id FROM activacion")}
        assert set(vigentes_por_documento(conn).values()) >= activas and len(activas) == 3
        assert verificar_evidencia(conn) == []
    assert main(["db", "verificar", "--db", str(db)]) == 0
    assert cliente.pagadas == 3


def test_por_la_cli_un_lote_se_manda_y_se_recoge(tmp_path, out_v1, pdfs_ejemplo, monkeypatch,
                                                 capsys) -> None:
    import anthropic

    from bms_agent.almacen import preparar
    from bms_agent.cli import main

    db = tmp_path / "bms.sqlite3"
    assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(pdfs_ejemplo),
                 "--db", str(db)]) == 0
    with preparar(db) as almacen:
        cliente = ClienteFalso(_lecturas(almacen.conn))
        shas = _shas(almacen.conn)
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: cliente)
    capsys.readouterr()
    assert main(["reextraer", "--proveedor", "Elektro Installatie Koster", "--lote",
                 "--presupuesto", "1", "--db", str(db), "--out", str(tmp_path)]) == 0
    texto = capsys.readouterr().out
    assert "Por lotes" in texto and "--recoger 1" in texto
    assert len(cliente.lotes) == 1 and len(cliente.lotes[0]) == 1
    assert main(["reextraer", "--recoger", "1", "--db", str(db), "--out", str(tmp_path)]) == 0
    assert "no ha terminado" in capsys.readouterr().out
    cliente.batches.terminado = True
    cliente.batches.resultados = [resultado_lote(shas["03-con-inyeccion.pdf"],
                                                 datos=lectura_v2("03-con-inyeccion"))]
    assert main(["reextraer", "--recoger", "1", "--db", str(db), "--out", str(tmp_path)]) == 0
    assert "1 candidatas, 0 para reintentar" in capsys.readouterr().out
    assert main(["reextraer", "--recoger", "1", "--db", str(db), "--out", str(tmp_path)]) == 1


def test_coste_cuenta_cada_version_aparte_y_tambien_lo_reextraido(con_pdfs, out_v1, tmp_path,
                                                                  capsys) -> None:
    import shutil

    from bms_agent.cli import main

    conn = con_pdfs.conn
    _pasada(con_pdfs, ClienteFalso(_lecturas(conn)), tmp_path, abiertas=True)
    for fichero in out_v1.glob("*.json"):
        shutil.copy2(fichero, tmp_path / "salida" / fichero.name)
    assert main(["coste", "--out", str(tmp_path / "salida")]) == 0
    texto = capsys.readouterr().out
    assert re.search(r"documentos leidos\s+10\n", texto)
    [v1] = [l for l in texto.splitlines() if "claude-opus-5 " in l and "esquema 1" in l]
    [v2] = [l for l in texto.splitlines() if "claude-opus-5-5" in l and "esquema 2" in l]
    assert "7 doc" in v1 and "3 doc" in v2


# ------------------------------------------------------------ correcciones de la revision


def _otra_lectura_igual(conn, factura_id: int, extraido: str) -> None:
    """Otra extraccion de la factura, con el mismo contenido que su vigente y otra fecha."""
    from bms_agent.almacen import usuario_sistema
    from bms_agent.almacen.extracciones import leer_registro, registrar_extraccion

    fila = conn.execute("SELECT e.documento_id, e.contenido_json FROM factura AS f JOIN extraccion "
                        "AS e ON e.id = f.extraccion_vigente_id WHERE f.id = ?",
                        (factura_id,)).fetchone()
    registro = json.loads(fila["contenido_json"])
    registro["extracted_at"] = extraido
    with transaccion(conn):
        registrar_extraccion(conn, leer_registro(json.dumps(registro, indent=2)),
                             documento_id=fila["documento_id"], via="out_v1",
                             actor=usuario_sistema(conn, "extractor"))


def test_una_linea_excluida_para_cerrar_su_m2_no_lo_reabre_con_otra_lectura(
        con_pdfs, tmp_path) -> None:
    from bms_agent.hallazgos import recalcular

    conn = con_pdfs.conn
    ana = persona(conn, "Ana", "administracion")
    f = factura_de(conn, "2026-4471")
    lineas = conn.execute("SELECT id FROM factura_linea WHERE factura_id = ? ORDER BY orden",
                          (f,)).fetchall()
    tercera, segunda = lineas[2]["id"], lineas[1]["id"]
    campos.fijar(conn, "factura_linea", tercera, {"objeto_doc": "Schiedam-Oost"},
                 Persona(ana, "es la obra de Oost"))
    campos.retirar(conn, "factura_linea", segunda, Persona(ana, "no se factura"))
    nueva = lectura_v2("01-limpia")
    nueva["lines"][2].update(description="Reiskosten Schiedam", line_total_raw="101,30")
    nueva["lines"][1].update(line_total_raw="704,10")
    _pasada(con_pdfs, ClienteFalso(_lecturas(conn, **{"01-limpia": nueva})), tmp_path,
            abiertas=True)
    reextraccion.activar(con_pdfs, _admin(conn), VERDAD, objetivo=OBJETIVO)
    # Ana hace lo que pide el M2 de la tercera: la excluye, porque ya no existe.
    campos.retirar(conn, "factura_linea", tercera, Persona(ana, "es la misma que la nueva"))
    recalcular(conn)

    _otra_lectura_igual(conn, f, "2099-01-01T00:00:00+00:00")
    [tipado] = [t for t in tipar_pendientes(conn) if t.factura_id == f]
    assert tipado.accion == "actualizada"
    assert tercera not in tipado.sin_casar        # ya decidida: no se vuelve a preguntar
    assert segunda in tipado.sin_casar            # la exclusion de antes sigue sin llevarse
    recalcular(conn)
    estados = {r["clave"]: (r["estado"], r["severidad"]) for r in conn.execute(
        "SELECT clave, estado, severidad FROM hallazgo WHERE regla = 'M2'")}
    assert estados[f"M2|factura:{f}|linea:{tercera}"][0] == "cerrado"
    assert estados[f"M2|factura:{f}|linea:{segunda}"][0] == "abierto"
    assert verificar_evidencia(conn) == []


def test_recoger_un_lote_interrumpido_se_puede_repetir_sin_duplicar(con_pdfs, tmp_path,
                                                                    monkeypatch) -> None:
    conn = con_pdfs.conn
    shas = _shas(conn)
    cliente = ClienteFalso(_lecturas(conn))
    r = _pasada(con_pdfs, cliente, tmp_path, lote=True, abiertas=True)
    cliente.batches.terminado = True
    cliente.batches.resultados = [
        resultado_lote(shas[n], datos=lectura_v2(n[:-4])) for n in (
            "01-limpia.pdf", "02-sin-kvk-btw-verlegd.pdf", "03-con-inyeccion.pdf")]
    original = reextraccion._guardar_candidata
    llamadas = itertools.count(1)

    def guardar_y_fallar(*args, **kwargs):
        if next(llamadas) == 3:
            raise OSError("disco lleno")
        return original(*args, **kwargs)

    with monkeypatch.context() as m:
        m.setattr(reextraccion, "_guardar_candidata", guardar_y_fallar)
        with pytest.raises(OSError):
            reextraccion.recoger(cliente, con_pdfs, r.reextraccion_id, out_dir=tmp_path / "salida")
    assert conn.execute("SELECT estado FROM reextraccion").fetchone()[0] == "esperando_lote"

    otra = reextraccion.recoger(cliente, con_pdfs, r.reextraccion_id, out_dir=tmp_path / "salida")
    assert otra.estado == "terminada"
    fila = conn.execute("SELECT * FROM reextraccion").fetchone()
    assert (fila["extraidas"], fila["reintentos"]) == (3, 0)
    assert conn.execute("SELECT count(*) FROM extraccion WHERE via = 'lote'").fetchone()[0] == 3
    assert conn.execute("SELECT count(*) FROM reextraccion_resultado").fetchone()[0] == 3
    assert verificar_evidencia(conn) == []


def _coste(modelo: str, entrada: int, salida: int) -> Decimal:
    from bms_agent.pricing import estimate_cost

    return estimate_cost(modelo, entrada, salida)


def test_el_presupuesto_es_un_tope_de_lo_que_se_paga(con_pdfs, tmp_path) -> None:
    """Una salida muy por encima de lo estimado no se sigue pagando pasado el presupuesto."""
    conn = con_pdfs.conn
    cliente = ClienteFalso(_lecturas(conn), salida=config.max_tokens())
    # La estimacion alta (sin medir) cabe en 0,70; el peor caso de los tres, no.
    r = _pasada(con_pdfs, cliente, tmp_path, presupuesto="0.70", abiertas=True)
    gastado = _coste(OBJETIVO[0], 3000, config.max_tokens()) * cliente.pagadas
    assert cliente.pagadas == 2 and gastado <= Decimal("0.70")
    assert [m for _d, m, _x in r.reintentos] == ["presupuesto"]
    fila = conn.execute("SELECT * FROM reextraccion").fetchone()
    assert (fila["estado"], fila["extraidas"], fila["reintentos"]) == ("terminada", 2, 1)
    evento = json.loads(conn.execute(
        "SELECT datos_json FROM evento WHERE tipo = 'reextraccion_terminada'").fetchone()[0])
    assert Decimal(evento["gastado_usd"]) == gastado and evento["parada_por_presupuesto"]
    # Lo que no se pago se pide otra vez con --reintentos, y con presupuesto.
    otra = reextraccion.seleccionar(conn, reextraccion.Criterio(reintentos=True), OBJETIVO)
    assert len(otra.documentos) == 1
    assert verificar_evidencia(conn) == []


def test_si_el_peor_caso_de_un_documento_no_cabe_no_se_paga_ninguno(con_pdfs, tmp_path) -> None:
    conn = con_pdfs.conn
    cliente = ClienteFalso(_lecturas(conn), salida=config.max_tokens())
    r = _pasada(con_pdfs, cliente, tmp_path, presupuesto="0.21", abiertas=True)
    assert cliente.pagadas == 0
    assert [m for _d, m, _x in r.reintentos] == ["presupuesto"] * 3


def test_un_rechazo_se_paga_y_cuenta_en_lo_gastado(con_pdfs, tmp_path) -> None:
    conn = con_pdfs.conn
    cliente = ClienteFalso(_lecturas(conn))
    cliente.rechaza.add(_shas(conn)["03-con-inyeccion.pdf"])
    r = _pasada(con_pdfs, cliente, tmp_path, abiertas=True)
    assert r.tokens_entrada == 3 * 3000 and r.tokens_salida == 2 * 2400 + 10


def test_por_lotes_el_peor_caso_tiene_que_caber_porque_no_se_puede_parar(con_pdfs,
                                                                          tmp_path) -> None:
    conn = con_pdfs.conn
    cliente = ClienteFalso(_lecturas(conn))
    with pytest.raises(reextraccion.PresupuestoInsuficiente, match="peor caso"):
        _pasada(con_pdfs, cliente, tmp_path, presupuesto="0.30", lote=True, abiertas=True)
    assert cliente.lotes == []


def test_la_salida_medida_lo_es_con_el_mismo_esfuerzo() -> None:
    from bms_agent import coste

    medidos = [coste.Documento(f"{i}.pdf", "m", 3000, 2000, None, None, esquema="2",
                               esfuerzo="medium") for i in range(3)]
    assert coste.estimar_salida(medidos, modelo="m", esquema="2", esfuerzo="medium").medida
    otra = coste.estimar_salida(medidos, modelo="m", esquema="2", esfuerzo="high")
    assert not otra.medida and "sin medir" in otra.origen


def test_cada_extraccion_apunta_su_esfuerzo_y_su_tope_de_salida(con_pdfs, tmp_path) -> None:
    conn = con_pdfs.conn
    _pasada(con_pdfs, ClienteFalso(_lecturas(conn)), tmp_path, abiertas=True)
    for (uso,) in conn.execute("SELECT uso_json FROM extraccion WHERE schema_version = '2'"):
        assert json.loads(uso)["effort"] == config.effort()
        assert json.loads(uso)["max_tokens"] == config.max_tokens()


class _SinRespuesta(Exception):
    """Un corte de conexion: no se sabe si la API acepto el lote."""


class _Rechazo400(Exception):
    status_code = 400


def test_un_lote_rechazado_por_la_api_va_entero_a_reintentos(con_pdfs, tmp_path) -> None:
    conn = con_pdfs.conn
    cliente = ClienteFalso(_lecturas(conn))
    cliente.batches.error = _Rechazo400("invalid_request_error")
    r = _pasada(con_pdfs, cliente, tmp_path, lote=True, abiertas=True)
    assert r.estado == "terminada" and [m for _d, m, _x in r.reintentos] == ["error"] * 3


def test_un_lote_que_no_se_sabe_si_se_mando_no_se_vuelve_a_pagar(con_pdfs, tmp_path) -> None:
    conn = con_pdfs.conn
    shas = _shas(conn)
    cliente = ClienteFalso(_lecturas(conn))
    cliente.batches.error = _SinRespuesta("timeout")
    cliente.batches.crea_aunque_falle = True        # la API lo acepto; la respuesta se perdio
    r = _pasada(con_pdfs, cliente, tmp_path, lote=True, abiertas=True)
    assert r.estado == "lote_desconocido" and r.reintentos == []
    # Ni --reintentos ni otro criterio vuelven a pagar esos documentos mientras tanto.
    for criterio in (reextraccion.Criterio(reintentos=True), reextraccion.Criterio(abiertas=True)):
        seleccion = reextraccion.seleccionar(conn, criterio, OBJETIVO)
        assert seleccion.documentos == []
    assert any("lote" in m for _d, m in reextraccion.seleccionar(
        conn, reextraccion.Criterio(abiertas=True), OBJETIVO).omitidos)

    # Recoger lo busca en la API por la hora y el numero de peticiones, y lo adopta.
    cliente.batches.error = None
    r2 = reextraccion.recoger(cliente, con_pdfs, r.reextraccion_id, out_dir=tmp_path / "salida")
    assert r2.estado == "esperando_lote" and r2.lote_id == "msgbatch_falso_1"
    cliente.batches.terminado = True
    cliente.batches.resultados = [resultado_lote(shas[n], datos=lectura_v2(n[:-4])) for n in (
        "01-limpia.pdf", "02-sin-kvk-btw-verlegd.pdf", "03-con-inyeccion.pdf")]
    r3 = reextraccion.recoger(cliente, con_pdfs, r.reextraccion_id, out_dir=tmp_path / "salida")
    assert r3.estado == "terminada" and len(r3.candidatas) == 3
    assert len(cliente.lotes) == 1
    assert verificar_evidencia(conn) == []


def test_un_lote_que_la_api_no_tiene_se_da_por_no_mandado(con_pdfs, tmp_path) -> None:
    conn = con_pdfs.conn
    cliente = ClienteFalso(_lecturas(conn))
    cliente.batches.error = _SinRespuesta("connection reset")
    r = _pasada(con_pdfs, cliente, tmp_path, lote=True, abiertas=True)
    assert r.estado == "lote_desconocido"
    cliente.batches.error = None
    r2 = reextraccion.recoger(cliente, con_pdfs, r.reextraccion_id, out_dir=tmp_path / "salida")
    assert r2.estado == "terminada" and len(r2.reintentos) == 3
    assert len(reextraccion.seleccionar(conn, reextraccion.Criterio(reintentos=True),
                                        OBJETIVO).documentos) == 3


def test_el_lote_se_manda_sin_reintentos_automaticos_del_sdk(con_pdfs, tmp_path) -> None:
    conn = con_pdfs.conn
    cliente = ClienteFalso(_lecturas(conn))
    opciones = []

    def with_options(**kwargs):
        opciones.append(kwargs)
        return cliente

    cliente.with_options = with_options
    _pasada(con_pdfs, cliente, tmp_path, lote=True, abiertas=True)
    assert opciones == [{"max_retries": 0}]


def test_la_puerta_compara_con_la_vigente_y_no_con_una_candidata_rechazada(
        con_pdfs, tmp_path, monkeypatch) -> None:
    conn = con_pdfs.conn
    mal = lectura_v2("01-limpia", invoice_number="2026-4417")
    # Un prompt anterior, nunca activado, que ya leia mal el numero.
    with monkeypatch.context() as m:
        m.setattr(config, "PROMPT_VERSION", "extract/2026-10-15.0")
        rechazado = (OBJETIVO[0], "extract/2026-10-15.0", OBJETIVO[2])
        seleccion = reextraccion.seleccionar(conn, reextraccion.Criterio(abiertas=True),
                                             rechazado)
        documentos = reextraccion.cargar(con_pdfs, seleccion)
        cliente = ClienteFalso(_lecturas(conn, **{"01-limpia": mal}))
        reextraccion.ejecutar(
            cliente, con_pdfs, seleccion, documentos,
            reextraccion.estimar(cliente, conn, documentos, rechazado, lote=False),
            Decimal("10"), criterio=reextraccion.Criterio(abiertas=True), objetivo=rechazado,
            out_dir=tmp_path / "salida")
    _pasada(con_pdfs, ClienteFalso(_lecturas(conn, **{"01-limpia": mal})), tmp_path,
            abiertas=True)
    comparacion = reextraccion.comparar(conn, VERDAD, OBJETIVO)
    # La referencia es la v1 vigente, que acierta el numero: la nueva es peor.
    assert any("peor que la anterior" in m for m in comparacion.motivos), comparacion.motivos
    assert comparacion.anterior.critical_accuracy() == Decimal("100.00")


@pytest.mark.parametrize("opciones", [{"politica": "estricta"}, {"forzar": True}],
                         ids=["estricta", "force"])
def test_extract_con_almacen_no_salta_la_puerta(con_pdfs, pdfs_ejemplo, tmp_path,
                                                opciones) -> None:
    """Releer con --estricta o --force lo ya tipado deja una candidata, no una vigente."""
    from bms_agent.ingesta import ingestar_pasada

    conn = con_pdfs.conn
    otra = lectura_v2("03-con-inyeccion", iban="NL91 ABNA 0417 1643 00")
    cliente = ClienteFalso(_lecturas(conn, **{"03-con-inyeccion": otra}))
    vigentes = vigentes_por_documento(conn)
    resueltos = registros_resueltos(conn)
    pdfs = sorted(pdfs_ejemplo.glob("0[123]-*.pdf"))
    salida = tmp_path / "salida"
    pasada, ingesta = ingestar_pasada(cliente, pdfs, salida, almacen=con_pdfs, **opciones)
    assert cliente.pagadas == 3 and pasada.candidatas == 3
    assert vigentes_por_documento(conn) == vigentes
    assert registros_resueltos(conn) == resueltos
    assert {t.accion for t in ingesta.tipados} == {"sin_cambios"}
    assert conn.execute("SELECT count(*) FROM activacion").fetchone()[0] == 0
    assert len(reextraccion.candidatas_pendientes(conn, OBJETIVO)) == 3
    # Exportadas como candidatas, fuera de out/: sin almacen tampoco son vigentes.
    assert len(list((salida / "reextraccion").glob("*.json"))) == 3
    assert not list(salida.glob("*.json"))
    # Otra --estricta no las vuelve a pagar: estan exportadas como candidatas.
    ingestar_pasada(cliente, pdfs, salida, almacen=con_pdfs, politica="estricta")
    assert cliente.pagadas == 3
    # Solo pasan a vigentes por la puerta.
    with pytest.raises(reextraccion.PuertaCerrada):
        reextraccion.activar(con_pdfs, _admin(conn), VERDAD, objetivo=OBJETIVO)
    assert verificar_evidencia(conn) == []
