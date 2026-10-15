"""Ventas, relaciones entre facturas y las vistas de proveedores y clientes (paso 8).

Puertas del paso 8 que viven aqui, sobre el almacen entero (importar,
tipar, casar, evaluar y las caches):

- la via de entrada decide el sentido, y un documento de la via de salida
  que no emite BM Support BV queda Bloqueado (A8);
- un abono que acredita entero deja la original acreditada, y uno parcial le
  baja lo pendiente; lo propuesto no mueve nada hasta que una persona lo
  confirma;
- una factura sustituida o corregida sale de los totales, de la caja y del
  IVA;
- B4 no salta con una pareja confirmada;
- que Exact y el PDF de una venta digan cosas distintas es una discrepancia
  (M3);
- lo pendiente de un proveedor (o de un cliente) es la suma de lo pendiente de
  sus facturas abiertas.

La V1 no crea facturas ni borradores: las de venta solo se importan de Exact
o se leen de su PDF.
"""

from __future__ import annotations

import json
import random
import sqlite3

import pytest
from conftest import (
    CUENTA_PROPIA,
    RAIZ,
    cuentas_propias,
    factura_de,
    persona,
)

from bms_agent import (
    campos,
    config,
    consultas,
    flujo_caja,
    hallazgos,
    ingesta,
    relaciones,
    servicios,
)
from bms_agent.almacen import transaccion, usuario_sistema
from bms_agent.almacen.documentos import registrar_documento
from bms_agent.almacen.extracciones import leer_registro, registrar_extraccion
from bms_agent.importadores.registrar import importar_fichero
from bms_agent.legado import registros_legado
from bms_agent.permisos import usuario_por_nombre

IMPORTACION = RAIZ / "tests" / "fixtures" / "importacion"
EXACT_PROVEEDORES = IMPORTACION / "exact-proveedores-v1.csv"
EXACT_CLIENTES = IMPORTACION / "exact-clientes-v1.csv"
OBJETOS = IMPORTACION / "maestro_csv-objetos-v1.csv"
VENTAS = IMPORTACION / "exact-facturas_venta-v1.csv"
EMPRESA = "BM Support BV"
HAVEN, HAVEN_BTW = "Havenbedrijf Rotterdam BV", "NL009999999B01"
VAN_DIJK, VAN_DIJK_BTW = "Bouwtechniek Van Dijk BV", "NL001234567B01"
MOTIVO = "Visto con el documento delante"


# ------------------------------------------------------------ constructores

def _linea(descripcion: str, cantidad: str, tarifa: str, importe: str, *,
           objeto: str | None = None, iva: str = "21%") -> dict:
    return {"description": descripcion, "quantity_raw": cantidad, "unit": "uur",
            "unit_rate_raw": tarifa, "line_total_raw": importe, "vat_rate_raw": iva,
            "location": objeto, "employee_name": None, "work_date": None, "week_number": None,
            "period_start": None, "period_end": None, "order_reference_raw": None,
            "rate_type_raw": None}


def _documento(sha: str, *, numero: str, base: str, iva: str, total: str, lineas: list[dict],
               emisor: str = EMPRESA, emisor_btw: str | None = None, receptor: str = HAVEN,
               receptor_btw: str | None = HAVEN_BTW, fecha: str = "2026-10-01",
               desde: str = "2026-09-01", hasta: str = "2026-09-30", tipo: str = "invoice",
               citadas: tuple[tuple[str, str], ...] = (), iban: str | None = None,
               vence: str | None = None) -> dict:
    """Una extraccion v2 como la escribiria el extractor (el modelo solo transcribe).

    `citadas` son las facturas que nombra el documento: (numero, relacion que enuncia).
    """
    extraccion = {
        "document_type": tipo, "supplier_name": emisor, "supplier_address": None,
        "kvk_number": None, "vat_number": emisor_btw, "supplier_contact_person": None,
        "recipient_name": receptor, "recipient_vat_number": receptor_btw,
        "recipient_contact_person": None, "invoice_number": numero, "invoice_date": fecha,
        "service_period_start": desde, "service_period_end": hasta,
        "related_invoices": [{"invoice_number": n, "invoice_date": None,
                              "relation_text": f"{r} factuur {n}", "stated_relation": r}
                             for n, r in citadas],
        "references": [], "lines": lineas, "currency_raw": "EUR",
        "subtotal_excl_vat_raw": base, "vat_rate_raw": "21%", "vat_amount_raw": iva,
        "total_incl_vat_raw": total, "vat_breakdown": [], "vat_regime": "standard",
        "kor_mentioned": False, "reverse_charge_mentioned": False, "iban": iban,
        "payment_reference": None, "payment_terms_raw": None, "due_date": vence,
        "low_confidence_fields": [], "document_notes": None,
    }
    return {"source_sha256": sha * (64 // len(sha)), "source_name": f"{numero}.pdf",
            "model": config.DEFAULT_MODEL, "prompt_version": config.PROMPT_VERSION,
            "schema_version": config.SCHEMA_VERSION, "extracted_at": "2026-10-02T08:00:00+00:00",
            "request_id": f"req_{numero}", "usage": {"input_tokens": 1, "output_tokens": 1},
            "extraction": extraccion}


def _entrar(almacen, ruta: str, registro: dict, *, recalcular: bool = True) -> int:
    """El documento entra por una via (entrante o saliente), se tipa y se recalcula."""
    conn = almacen.conn
    contenido = json.dumps(registro, indent=2, ensure_ascii=False)
    with transaccion(conn):
        actor = usuario_sistema(conn, "extractor")
        documento = registrar_documento(
            almacen, sha256=registro["source_sha256"], contenido=None,
            nombre_original=registro["source_name"], tipo_mime="application/pdf",
            origen="carpeta", ruta_declarada=ruta, recibido_en=None,
            recibido_fuente="desconocido", actor=actor)
        registrar_extraccion(conn, leer_registro(contenido), documento_id=documento.id,
                             via="api", actor=actor)
    [tipado] = [t for t in ingesta.tipar_pendientes(conn) if t.documento_id == documento.id]
    if recalcular:
        hallazgos.recalcular(conn)
    return tipado.factura_id


def _copia_de_v2026_0101(sha: str, total: str = "5.149,76", **cambios) -> dict:
    """El PDF de la venta V2026-0101 de Exact, como lo leeria el extractor."""
    return _documento(sha, numero="V2026-0101", base="4.256,00", iva="893,76", total=total,
                      lineas=[_linea("Montagewerk, locatie Rijnhaven", "40", "62,00", "2.480,00",
                                     objeto="Rijnhaven"),
                              _linea("Staalconstructie, locatie Waalhaven", "24", "74,00",
                                     "1.776,00", objeto="Waalhaven")],
                      iban=CUENTA_PROPIA, vence="2026-10-31", **cambios)


def _ana(conn) -> int:
    return usuario_por_nombre(conn, "Ana")


def _orden(conn, nombre: str, datos: dict) -> servicios.Diferencia:
    return servicios.ejecutar(conn, nombre, datos, usuario_id=_ana(conn))


def _estado(conn, factura_id: int) -> tuple:
    return tuple(conn.execute("SELECT estado_pago, pendiente_cent, nivel FROM factura_estado "
                              "WHERE factura_id = ?", (factura_id,)).fetchone())


def _hallazgos(conn, regla: str, factura_id: int | None = None, *,
               estados: tuple[str, ...] = ("abierto",)) -> list:
    filas = conn.execute(
        f"SELECT * FROM hallazgo WHERE regla = ? AND estado IN ({', '.join('?' * len(estados))}) "
        "ORDER BY id", (regla, *estados)).fetchall()
    if factura_id is None:
        return filas
    return [h for h in filas if h["factura_id"] == factura_id or factura_id in {
        f[0] for f in conn.execute("SELECT fila_id FROM hallazgo_objetivo WHERE hallazgo_id = ? "
                                   "AND tabla = 'factura'", (h["id"],))}]


def _relacion(conn, origen_id: int, destino_id: int):
    return conn.execute("SELECT * FROM factura_relacion WHERE origen_id = ? AND destino_id = ? "
                        "ORDER BY id DESC", (origen_id, destino_id)).fetchone()


def _confirmar(conn, relacion, **datos) -> servicios.Diferencia:
    return _orden(conn, "confirmar_relacion", {"relacion_id": relacion["id"],
                                               "rev": relacion["rev"], "motivo": MOTIVO,
                                               **datos})


def _limpio(conn) -> None:
    assert campos.verificar_controladas(conn) == []
    assert hallazgos.verificar(conn) == []


@pytest.fixture
def ventas(almacen):
    """Los clientes y los Objetos del maestro y el listado de ventas de Exact, con las cuentas
    propias de BM Support BV cargadas. Ana lo puede todo."""
    conn = almacen.conn
    ana = persona(conn, "Ana", "administrador")
    cuentas_propias(almacen, ana)
    importar_fichero(almacen, "exact", "clientes", EXACT_CLIENTES, lanzado_por=ana)
    importar_fichero(almacen, "maestro_csv", "objetos", OBJETOS, lanzado_por=ana)
    importar_fichero(almacen, "exact", "facturas_venta", VENTAS, lanzado_por=ana)
    return almacen


@pytest.fixture
def compras(tipado):
    """Las siete facturas v1 de compra, el maestro de proveedores de Exact y las cuentas
    propias. Ana lo puede todo."""
    conn = tipado.conn
    ana = persona(conn, "Ana", "administrador")
    cuentas_propias(tipado, ana)
    importar_fichero(tipado, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana)
    return tipado


# ============================================================ las ventas de Exact

def test_las_ventas_de_exact_entran_con_su_cliente_sus_lineas_y_su_objeto(ventas) -> None:
    conn = ventas.conn
    facturas = {f["numero"]: f for f in conn.execute("SELECT * FROM factura ORDER BY id")}
    assert set(facturas) == {"V2026-0101", "V2026-0102", "C2026-0005"}
    assert {(f["sentido"], f["origen"], f["fuente_externa"]) for f in facturas.values()} == {
        ("saliente", "exact", "exact")}
    v101, v102, abono = facturas["V2026-0101"], facturas["V2026-0102"], facturas["C2026-0005"]
    clientes = dict(conn.execute("SELECT exact_id, id FROM cliente"))
    assert (v101["cliente_id"], v102["cliente_id"], abono["cliente_id"]) == (
        clientes["10001"], clientes["10002"], clientes["10001"])
    assert (v101["id_externo"], v101["base_cent"], v101["iva_cent"], v101["total_cent"],
            v101["fecha_vencimiento"], v101["plazo_pago_dias"]) == (
        "70:V2026-0101", 425600, 89376, 514976, "2026-10-31", 30)
    assert (abono["tipo"], abono["total_cent"], v102["tratamiento_iva"]) == (
        "nota_credito", -30008, "autoliquidacion")
    # El centro de coste o el proyecto de cada linea es su Objeto.
    objetos = dict(conn.execute("SELECT id, codigo FROM objeto"))
    imputaciones = conn.execute(
        "SELECT l.orden, i.objeto_id, i.horas_mil, i.importe_cent FROM factura_imputacion i "
        "JOIN factura_linea l ON l.id = i.linea_id WHERE i.factura_id = ? ORDER BY l.orden",
        (v101["id"],)).fetchall()
    assert [(o, objetos.get(ob), h, c) for o, ob, h, c in imputaciones] == [
        (1, "Rijnhaven", 40000, 248000), (2, "Waalhaven", 24000, 177600)]
    [iva] = conn.execute("SELECT tipo_iva_pb, base_cent, cuota_cent FROM factura_iva "
                         "WHERE factura_id = ?", (v101["id"],)).fetchall()
    assert tuple(iva) == (2100, 425600, 89376)
    assert conn.execute("SELECT valor_doc, clase FROM factura_referencia WHERE factura_id = ?",
                        (v101["id"],)).fetchall()[0][0] == "PO-4500123"
    # La factura que cita el abono es una propuesta (de Exact) que no mueve nada todavia.
    relacion = _relacion(conn, abono["id"], v101["id"])
    assert (relacion["tipo"], relacion["estado"], relacion["fuente"]) == (
        "acredita", "propuesta", "exact")
    assert _estado(conn, v101["id"])[:2] == ("pendiente", 514976)
    # R5 es uno por relacion, sobre las dos facturas.
    [r5] = _hallazgos(conn, "R5")
    assert _hallazgos(conn, "R5", v101["id"]) == _hallazgos(conn, "R5", abono["id"]) == [r5]
    assert _hallazgos(conn, "R4", abono["id"])
    # Las ventas de Exact no se leen con el modelo: no tienen documento ni A8.
    assert not _hallazgos(conn, "A8") and not _hallazgos(conn, "Q4")
    _limpio(conn)


def test_importar_otra_vez_el_listado_de_ventas_no_hace_nada(ventas) -> None:
    conn = ventas.conn
    antes = [tuple(f) for f in conn.execute("SELECT * FROM factura ORDER BY id")]
    eventos = conn.execute("SELECT count(*) FROM evento").fetchone()[0]
    r = importar_fichero(ventas, "exact", "facturas_venta", VENTAS, lanzado_por=_ana(conn))
    assert [lote.repetida for lote in r.lotes] == [True]
    assert [tuple(f) for f in conn.execute("SELECT * FROM factura ORDER BY id")] == antes
    # Solo la pasada del motor, que no cambia nada.
    assert conn.execute("SELECT count(*) FROM factura_relacion").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM evento").fetchone()[0] - eventos <= 2


@pytest.mark.parametrize("cambio, motivo", [
    (lambda t: t.replace(";10002;Bouwgroep", ";10009;Bouwgroep"), "10009"),
    (lambda t: t.replace("Verlegd;;;EUR", "Verlegd;;;USD"), "USD"),
    (lambda t: t.replace("01-10-2026;31-10-2026;10001;Havenbedrijf Rotterdam BV;NL009999999B01;"
                         "M. Visser;30 dagen;01-09-2026;30-09-2026;Normaal;PO-4500123;;EUR;"
                         "4.256,00;893,76;5.149,76;2",
                         "01-10-2026;31-10-2026;10001;Havenbedrijf Rotterdam BV;NL009999999B01;"
                         "M. Visser;30 dagen;01-09-2026;30-09-2026;Normaal;PO-4500123;;EUR;"
                         "4.256,00;893,76;5.150,76;2"), "otro total"),
    (lambda t: t.replace("Waalhaven;Piet;01-09-2026;30-09-2026;24;uur;74,00;1.776,00",
                         "Waalhaven;Piet;01-09-2026;30-09-2026;24;uur;74,00;1.776,0x"), "1.776,0x"),
])
def test_un_listado_de_ventas_entra_entero_o_no_entra(almacen, tmp_path, cambio, motivo) -> None:
    """Un cliente que no esta, otra moneda, filas que no dicen lo mismo de la cabecera o una
    fila ilegible rechazan el fichero entero: un listado a medias daria por no facturado lo
    que si lo esta."""
    conn = almacen.conn
    ana = persona(conn, "Ana", "administrador")
    importar_fichero(almacen, "exact", "clientes", EXACT_CLIENTES, lanzado_por=ana)
    texto = VENTAS.read_text(encoding="utf-8-sig")
    roto = cambio(texto)
    assert roto != texto
    fichero = tmp_path / "ventas.csv"
    fichero.write_text(roto, encoding="utf-8")
    r = importar_fichero(almacen, "exact", "facturas_venta", fichero, lanzado_por=ana)
    [lote] = r.lotes
    assert lote.estado == "rechazada" and lote.aceptadas == 0
    assert any(motivo in rechazo.motivo for rechazo in lote.rechazos), lote.rechazos
    assert conn.execute("SELECT count(*) FROM factura").fetchone()[0] == 0
    assert _hallazgos(conn, "Z2")


# ============================================================ puerta: abonos

def test_un_abono_parcial_confirmado_baja_lo_pendiente_de_la_original(ventas) -> None:
    """El abono de Exact por 300,08 sobre V2026-0101: propuesto no mueve nada; confirmado,
    la original debe 300,08 menos y el abono queda gastado entero."""
    conn = ventas.conn
    v101, abono = factura_de(conn, "V2026-0101"), factura_de(conn, "C2026-0005")
    cliente = conn.execute("SELECT cliente_id FROM factura WHERE id = ?", (v101,)).fetchone()[0]
    antes = consultas.cliente(conn, cliente)
    diferencia = _confirmar(conn, _relacion(conn, abono, v101))
    assert _estado(conn, v101)[:2] == ("pendiente", 514976 - 30008)
    assert _estado(conn, abono)[:2] == ("acreditada", 0)
    saldo = conn.execute("SELECT acreditado_cent, pendiente_cent FROM v_factura_saldo "
                         "WHERE factura_id = ?", (v101,)).fetchone()
    assert tuple(saldo) == (30008, 514976 - 30008)
    # Lo propuesto (R5) y el abono sin relacion (R4) se cierran solos.
    assert {(h["regla"], h["tipo"]) for h in diferencia.hallazgos.get("cerrados", [])} >= {
        ("R4", "cerrado_automatico"), ("R5", "cerrado_automatico")}
    assert not _hallazgos(conn, "R4") and not _hallazgos(conn, "R5")
    # El cliente debe lo mismo que antes (el abono sin aplicar ya restaba), y la caja espera
    # de V2026-0101 lo que queda y nada del abono.
    despues = consultas.cliente(conn, cliente)
    assert despues["pendiente_cent"] == antes["pendiente_cent"] == 514976 - 30008
    assert [f["id"] for f in despues["abiertas_detalle"]] == [v101]
    partidas, _movidos = flujo_caja.datos(conn)
    assert {p.factura_id: p.importe_cent for p in partidas if p.factura_id in (v101, abono)} \
        == {v101: 514976 - 30008}
    # Las dos siguen en lo facturado y en el IVA, cada una en su fecha: se compensan.
    assert despues["siempre_facturado"]["total_cent"] == 514976 - 30008
    assert {f[0] for f in conn.execute("SELECT factura_id FROM v_iva_vigente")} >= {v101, abono}
    _limpio(conn)


def test_un_abono_que_cubre_la_factura_la_deja_acreditada(compras) -> None:
    """Van Dijk manda un abono de toda la 2026-4471 que la nombra: la extraccion lo propone y,
    confirmado, la original queda acreditada (no se paga ni se espera)."""
    conn = compras.conn
    original = factura_de(conn, "2026-4471")
    abono = _entrar(compras, "entrante", _documento(
        "c1", numero="CN-2026-040", base="-2.399,00", iva="-503,79", total="-2.902,79",
        emisor=VAN_DIJK, emisor_btw=VAN_DIJK_BTW, receptor=EMPRESA, receptor_btw=None,
        fecha="2026-09-25", desde="2026-08-31", hasta="2026-09-06", tipo="credit_note",
        citadas=(("2026-4471", "credits"),),
        lineas=[_linea("Creditering factuur 2026-4471", "1", "-2.399,00", "-2.399,00")]))
    relacion = _relacion(conn, abono, original)
    assert (relacion["tipo"], relacion["estado"], relacion["fuente"]) == (
        "acredita", "propuesta", "extraccion")
    assert "2026-4471" in relacion["evidencia_doc"]
    # Propuesta: no mueve nada. La original sigue pendiente entera, y R5 lo dice.
    assert _estado(conn, original)[:2] == ("pendiente", 290279)
    assert _hallazgos(conn, "R5", original)
    _confirmar(conn, relacion)
    assert _estado(conn, original)[:2] == ("acreditada", 0)
    assert _estado(conn, abono)[:2] == ("acreditada", 0)
    proveedor = conn.execute("SELECT proveedor_id FROM factura WHERE id = ?",
                             (original,)).fetchone()[0]
    vista = consultas.proveedor(conn, proveedor)
    assert original not in {f["id"] for f in vista["abiertas_detalle"]}
    assert {f["id"]: f["estado_pago"] for f in vista["historial"]}[original] == "acreditada"
    partidas, _movidos = flujo_caja.datos(conn)
    assert not {original, abono} & {p.factura_id for p in partidas}
    assert not _hallazgos(conn, "R2") and not _hallazgos(conn, "R5")
    _limpio(conn)


def test_un_abono_parcial_enlazado_a_mano_baja_lo_pendiente(compras) -> None:
    """El abono v1 de la 01 (CN-2026-031, 122,51) no dice a que factura abona (R4): una
    persona lo enlaza y la original debe 122,51 menos."""
    conn = compras.conn
    original, abono = factura_de(conn, "2026-4471"), factura_de(conn, "CN-2026-031")
    assert _hallazgos(conn, "R4", abono)
    _orden(conn, "enlazar_facturas", {"origen_id": abono, "destino_id": original,
                                      "tipo": "acredita", "motivo": MOTIVO})
    relacion = _relacion(conn, abono, original)
    assert (relacion["estado"], relacion["fuente"], relacion["importe_cent"]) == (
        "confirmada", "manual", None)
    assert _estado(conn, original)[:2] == ("pendiente", 290279 - 12251)
    assert _estado(conn, abono)[:2] == ("acreditada", 0)
    assert not _hallazgos(conn, "R4")
    # Retirarla deja todo como estaba (no se borra nada).
    relacion = _relacion(conn, abono, original)
    _orden(conn, "retirar_relacion", {"relacion_id": relacion["id"], "rev": relacion["rev"],
                                      "motivo": "Era el abono de otra factura"})
    assert _estado(conn, original)[:2] == ("pendiente", 290279)
    assert _hallazgos(conn, "R4", abono)
    assert conn.execute("SELECT count(*) FROM factura_relacion").fetchone()[0] == 1
    _limpio(conn)


def test_los_abonos_no_le_quitan_a_una_factura_mas_de_lo_que_vale(compras) -> None:
    """Un abono por mas de lo que queda no se enlaza; y dos abonos que juntos pasan de la
    original dan R2, que no se anula ni se cierra solo."""
    conn = compras.conn
    original, parcial = factura_de(conn, "2026-4471"), factura_de(conn, "CN-2026-031")
    with pytest.raises(relaciones.RelacionNoValida, match="no da para"):
        _orden(conn, "enlazar_facturas", {"origen_id": parcial, "destino_id": original,
                                          "tipo": "acredita", "importe": "500,00",
                                          "motivo": MOTIVO})
    entero = _entrar(compras, "entrante", _documento(
        "c2", numero="CN-2026-041", base="-2.399,00", iva="-503,79", total="-2.902,79",
        emisor=VAN_DIJK, emisor_btw=VAN_DIJK_BTW, receptor=EMPRESA, receptor_btw=None,
        fecha="2026-09-25", desde="2026-08-31", hasta="2026-09-06", tipo="credit_note",
        lineas=[_linea("Creditering", "1", "-2.399,00", "-2.399,00")]))
    for abono in (parcial, entero):
        _orden(conn, "enlazar_facturas", {"origen_id": abono, "destino_id": original,
                                          "tipo": "acredita", "motivo": MOTIVO})
    [r2] = _hallazgos(conn, "R2", original)
    assert json.loads(r2["valores_json"])["acreditado_cent"] == 290279 + 12251
    assert (r2["pegajosa"], r2["anulable"]) == (1, 0)


# ============================================================ puerta: sustituida o corregida

def _sustituta(compras, sha: str = "d1", *, citar: bool = True) -> int:
    """Van Dijk manda otra factura del mismo periodo y Objeto que la 2026-4471; con `citar`,
    el documento dice que la sustituye."""
    return _entrar(compras, "entrante", _documento(
        sha, numero="2026-4471-B", base="2.000,00", iva="420,00", total="2.420,00",
        emisor=VAN_DIJK, emisor_btw=VAN_DIJK_BTW, receptor=EMPRESA, receptor_btw=None,
        fecha="2026-09-20", desde="2026-08-31", hasta="2026-09-06",
        tipo="replacement_invoice", citadas=(("2026-4471", "replaces"),) if citar else (),
        iban="NL02 ABNA 0123 4567 89",
        lineas=[_linea("Montagewerk, locatie Rijnhaven", "40", "50,00", "2.000,00",
                       objeto="Rijnhaven")]))


def _proveedor_totales(conn, proveedor_id: int) -> tuple:
    return tuple(conn.execute("SELECT facturas, base_cent, iva_cent, total_cent FROM "
                              "v_proveedor_totales WHERE proveedor_id = ?",
                              (proveedor_id,)).fetchone())


@pytest.mark.parametrize("como", ["confirmar", "sustituye", "corrige"])
def test_la_factura_sustituida_o_corregida_sale_de_los_totales_la_caja_y_el_iva(
        compras, como) -> None:
    conn = compras.conn
    original, nueva = factura_de(conn, "2026-4471"), _sustituta(compras, citar=como == "confirmar")
    proveedor = conn.execute("SELECT proveedor_id FROM factura WHERE id = ?",
                             (original,)).fetchone()[0]
    assert conn.execute("SELECT proveedor_id FROM factura WHERE id = ?",
                        (nueva,)).fetchone()[0] == proveedor
    # Las dos cuentan mientras nadie confirma nada: es lo que dicen los documentos.
    assert _proveedor_totales(conn, proveedor) == (3, 239900 - 10125 + 200000,
                                                   50379 - 2126 + 42000,
                                                   290279 - 12251 + 242000)
    [b4] = _hallazgos(conn, "B4", original)
    assert _hallazgos(conn, "B4", nueva) == [b4]
    if como == "confirmar":
        diferencia = _confirmar(conn, _relacion(conn, nueva, original))
    else:
        diferencia = _orden(conn, "enlazar_facturas", {"origen_id": nueva, "destino_id": original,
                                                       "tipo": como, "motivo": MOTIVO})
    # Fuera de los totales (la vista, la del proveedor y la Diferencia de la orden)...
    assert _proveedor_totales(conn, proveedor) == (2, 200000 - 10125, 42000 - 2126,
                                                   242000 - 12251)
    vista = consultas.proveedor(conn, proveedor)
    assert vista["siempre_facturado"]["total_cent"] == 242000 - 12251
    assert original not in {f["id"] for f in vista["abiertas_detalle"]}
    [historial] = [f for f in vista["historial"] if f["id"] == original]
    assert (historial["cuenta"], historial["sustituida"], historial["estado_pago"]) == (
        False, True, "anulada")
    assert {"entidad": "proveedor", "id": proveedor, "campo": "total_cent",
            "antes": 290279 - 12251 + 242000, "despues": 242000 - 12251} in diferencia.totales
    assert not conn.execute("SELECT 1 FROM v_imputacion_vigente WHERE factura_id = ?",
                            (original,)).fetchall()
    # ... de la caja ...
    partidas, _movidos = flujo_caja.datos(conn)
    ids = {p.factura_id for p in partidas}
    assert original not in ids and nueva in ids
    assert _estado(conn, original)[:2] == ("anulada", 0)
    # ... y del IVA: ni en el IVA que cuenta ni en las reglas de IVA.
    assert {f[0] for f in conn.execute("SELECT factura_id FROM v_iva_vigente")} >= {nueva}
    assert original not in {f[0] for f in conn.execute("SELECT factura_id FROM v_iva_vigente")}
    [d3] = conn.execute("SELECT resultado FROM evaluacion WHERE regla = 'D3' AND tabla = "
                        "'factura' AND fila_id = ?", (original,)).fetchall()
    assert d3[0] == "no_aplica"
    # B4 no salta con la pareja confirmada: quien la confirma lo cierra en la misma orden.
    assert conn.execute("SELECT estado FROM hallazgo WHERE id = ?", (b4["id"],)).fetchone()[0] \
        == "resuelto"
    assert {"B4"} <= {h["regla"] for h in diferencia.hallazgos.get("cerrados", [])}
    hallazgos.recalcular(conn)
    assert not _hallazgos(conn, "B4", nueva, estados=("abierto", "desaparecido"))
    # R3: la original sigue sin anular ni abonar en los libros y la nueva tambien esta
    # pendiente: se pagaria dos veces. Bloquea hasta que una persona anule la original.
    [r3] = _hallazgos(conn, "R3", nueva)
    assert r3["severidad"] == "bloqueo" and _estado(conn, nueva)[2] == "bloqueada"
    _orden(conn, "anular_factura", {"factura_id": original, "rev": _rev(conn, original),
                                    "motivo": "Sustituida por la 2026-4471-B, anulada en Exact"})
    assert conn.execute("SELECT estado FROM hallazgo WHERE id = ?", (r3["id"],)).fetchone()[0] \
        == "desaparecido"
    _limpio(conn)


def _rev(conn, factura_id: int) -> int:
    return conn.execute("SELECT rev FROM factura WHERE id = ?", (factura_id,)).fetchone()[0]


def test_una_relacion_cualquiera_no_calla_un_duplicado(compras) -> None:
    """'relacionada' no dice que una abone, corrija o sustituya a la otra: no explica que se
    cobre dos veces el mismo periodo, y B4 sigue."""
    conn = compras.conn
    original, nueva = factura_de(conn, "2026-4471"), _sustituta(compras)
    relacion = _relacion(conn, nueva, original)
    _orden(conn, "rechazar_relacion", {"relacion_id": relacion["id"], "rev": relacion["rev"],
                                       "motivo": "No la sustituye: son dos trabajos"})
    _orden(conn, "enlazar_facturas", {"origen_id": nueva, "destino_id": original,
                                      "tipo": "relacionada", "motivo": MOTIVO})
    assert _hallazgos(conn, "B4", original)
    assert _estado(conn, original)[:2] == ("pendiente", 290279)
    # Lo rechazado no se vuelve a proponer.
    hallazgos.recalcular(conn)
    assert conn.execute("SELECT count(*) FROM factura_relacion WHERE estado = 'propuesta'"
                        ).fetchone()[0] == 0


def test_lo_propuesto_solo_lo_confirma_una_persona(compras) -> None:
    """La base no deja que el sistema confirme una relacion, ni que una persona proponga."""
    conn = compras.conn
    original, nueva = factura_de(conn, "2026-4471"), _sustituta(compras)
    relacion = _relacion(conn, nueva, original)
    motor = campos.Automatico("calculado", usuario_sistema(conn, "motor"))
    with pytest.raises(sqlite3.IntegrityError, match="anular_acreditar"):
        campos.fijar(conn, "factura_relacion", relacion["id"], {"estado": "confirmada"}, motor)
    dora = persona(conn, "Dora", "consulta")
    with pytest.raises(servicios.PermisoDenegado):
        servicios.ejecutar(conn, "confirmar_relacion", {
            "relacion_id": relacion["id"], "rev": relacion["rev"], "motivo": MOTIVO},
            usuario_id=dora)
    assert _relacion(conn, nueva, original)["estado"] == "propuesta"
    # Otra contraparte no: callaria un duplicado o bajaria un saldo que no es suyo.
    with pytest.raises(relaciones.RelacionNoValida, match="misma contraparte"):
        _orden(conn, "enlazar_facturas", {"origen_id": nueva, "destino_id": factura_de(
            conn, "2026-018"), "tipo": "sustituye", "motivo": MOTIVO})
    # Una compra y una venta no se relacionan: lo dice la orden y, por debajo, la base.
    venta = _entrar(compras, "saliente", _documento(
        "a9", numero="V2026-0600", base="500,00", iva="105,00", total="605,00",
        lineas=[_linea("Montagewerk", "10", "50,00", "500,00")], iban=CUENTA_PROPIA))
    with pytest.raises(relaciones.RelacionNoValida, match="una compra y una venta"):
        _orden(conn, "enlazar_facturas", {"origen_id": venta, "destino_id": original,
                                          "tipo": "relacionada", "motivo": MOTIVO})
    with pytest.raises(sqlite3.IntegrityError, match="mismo sentido"):
        campos.crear(conn, "factura_relacion", {
            "origen_id": venta, "destino_id": original, "tipo": "relacionada",
            "estado": "confirmada"}, campos.Persona(_ana(conn), MOTIVO))


# ============================================================ puerta: Exact frente al PDF

def test_el_pdf_de_una_venta_de_exact_se_une_a_ella_y_lo_distinto_es_una_discrepancia(
        ventas) -> None:
    conn = ventas.conn
    v101 = factura_de(conn, "V2026-0101")
    copia = _entrar(ventas, "saliente", _copia_de_v2026_0101("e1", total="5.159,76"))
    fila = conn.execute("SELECT * FROM factura WHERE id = ?", (copia,)).fetchone()
    # Cuenta la de Exact: el PDF es su copia (misma via, numero y cliente) y sale de todo.
    assert (fila["sentido"], fila["origen"], fila["fusionada_en_id"]) == (
        "saliente", "extraccion", v101)
    assert campos.procedencia(conn, "factura", copia)["fusionada_en_id"]["fuente"] == "calculado"
    [m3] = _hallazgos(conn, "M3", v101)
    assert _hallazgos(conn, "M3", copia) == [m3]
    assert (m3["severidad"], m3["calidad"], m3["anulable"]) == ("retencion", "discrepancia", 1)
    assert json.loads(m3["valores_json"])["distintos"] == {"total_cent": [514976, 515976]}
    assert conn.execute("SELECT calidad FROM factura_estado WHERE factura_id = ?",
                        (v101,)).fetchone()[0] == "discrepancia"
    cliente = fila["cliente_id"]
    assert consultas.cliente(conn, cliente)["siempre_facturado"]["facturas"] == 2   # 0101 y abono
    _limpio(conn)


def test_una_copia_igual_no_es_una_discrepancia(ventas) -> None:
    conn = ventas.conn
    v101 = factura_de(conn, "V2026-0101")
    copia = _entrar(ventas, "saliente", _copia_de_v2026_0101("e3"))
    assert conn.execute("SELECT fusionada_en_id FROM factura WHERE id = ?",
                        (copia,)).fetchone()[0] == v101
    assert not _hallazgos(conn, "M3")
    # La copia lleva una cuenta de la empresa: F10 no tiene nada que decir.
    assert not _hallazgos(conn, "F10")


def test_una_persona_deshace_la_union_de_una_copia_y_no_se_vuelve_a_unir(ventas) -> None:
    conn = ventas.conn
    v101 = factura_de(conn, "V2026-0101")
    copia = _entrar(ventas, "saliente", _copia_de_v2026_0101("e5"))
    assert conn.execute("SELECT fusionada_en_id FROM factura WHERE id = ?",
                        (copia,)).fetchone()[0] == v101
    _orden(conn, "deshacer_fusion", {"factura_id": copia, "rev": _rev(conn, copia),
                                     "motivo": "No es la copia: es otro envio del cliente"})
    hallazgos.recalcular(conn)
    assert conn.execute("SELECT fusionada_en_id FROM factura WHERE id = ?",
                        (copia,)).fetchone()[0] is None
    assert campos.procedencia(conn, "factura", copia)["fusionada_en_id"]["fuente"] \
        == "manual_correccion"
    # Con el mismo numero que la de Exact y sin unir, M3 lo sigue diciendo (se anula si
    # procede); y V7 ve la venta repetida.
    assert _hallazgos(conn, "M3", copia) and _hallazgos(conn, "V7", copia)
    with pytest.raises(servicios.DatosNoValidos, match="no esta fusionada"):
        _orden(conn, "deshacer_fusion", {"factura_id": copia, "rev": _rev(conn, copia),
                                         "motivo": "Otra vez, por si acaso"})
    _limpio(conn)


def test_un_pdf_con_el_numero_de_una_venta_de_exact_y_otro_cliente_es_una_discrepancia(
        ventas) -> None:
    conn = ventas.conn
    v101 = factura_de(conn, "V2026-0101")
    suelta = _entrar(ventas, "saliente", _copia_de_v2026_0101(
        "e4", receptor="Bouwgroep Schiedam VOF", receptor_btw="NL008888888B01"))
    assert conn.execute("SELECT fusionada_en_id FROM factura WHERE id = ?",
                        (suelta,)).fetchone()[0] is None
    [m3] = _hallazgos(conn, "M3", suelta)
    assert _hallazgos(conn, "M3", v101) == [m3]
    assert set(json.loads(m3["valores_json"])["distintos"]) == {"parte"}


# ============================================================ puerta: la via decide el sentido

def test_la_via_decide_el_sentido_y_una_venta_que_no_emite_bms_queda_bloqueada(compras) -> None:
    """El mismo documento de Van Dijk: por la via de compras es una compra; dejado en la
    carpeta de ventas es una venta mal encaminada, Bloqueada por A8. Lo que diga el
    documento (o el modelo) no cambia el sentido."""
    conn = compras.conn
    lineas = [_linea("Montagewerk, locatie Rijnhaven", "10", "50,00", "500,00")]
    datos = dict(numero="2026-5000", base="500,00", iva="105,00", total="605,00", lineas=lineas,
                 emisor=VAN_DIJK, emisor_btw=VAN_DIJK_BTW, receptor=EMPRESA, receptor_btw=None)
    compra = _entrar(compras, "entrante", _documento("f1", **datos))
    venta = _entrar(compras, "saliente", _documento("f2", **datos))
    sentidos = dict(conn.execute("SELECT id, sentido FROM factura WHERE id IN (?, ?)",
                                 (compra, venta)))
    assert sentidos == {compra: "entrante", venta: "saliente"}
    assert campos.procedencia(conn, "factura", venta)["sentido"]["fuente_ref"] == "ruta:saliente"
    [a8] = _hallazgos(conn, "A8", venta)
    assert a8["severidad"] == "bloqueo" and "mal encaminada" in a8["detalle"]
    assert _estado(conn, venta)[2] == "bloqueada"
    assert not _hallazgos(conn, "A8", compra)
    # Una venta que emite BM Support BV no esta mal encaminada.
    buena = _entrar(compras, "saliente", _documento(
        "f3", numero="V2026-0200", base="500,00", iva="105,00", total="605,00", lineas=lineas,
        iban=CUENTA_PROPIA))
    assert not _hallazgos(conn, "A8", buena)
    assert conn.execute("SELECT sentido FROM factura WHERE id = ?", (buena,)).fetchone()[0] \
        == "saliente"
    # El panel de siempre es de compras: una venta no entra en sus registros.
    nombres = {r["source_name"] for r in registros_legado(conn)}
    assert "2026-5000.pdf" in nombres and "V2026-0200.pdf" not in nombres


def test_extract_con_salientes_guarda_aparte_y_entra_por_la_via_de_salida(
        tmp_path, monkeypatch, capsys) -> None:
    """`extract --salientes`: las extracciones van a out/salientes y el documento entra como
    saliente; `importar-out` vuelve a leer esa carpeta por la misma via. El cliente falso
    devuelve una factura de Van Dijk: en la via de salida, mal encaminada."""
    import anthropic
    from test_extraccion_pasada import PDF, ClienteFalso

    from bms_agent.almacen import preparar
    from bms_agent.cli import main

    pdfs = tmp_path / "ventas"
    pdfs.mkdir()
    (pdfs / "a.pdf").write_bytes(PDF)
    cliente = ClienteFalso()
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: cliente)
    db = tmp_path / "datos" / "bms.sqlite3"
    out = tmp_path / "out"
    assert main(["extract", str(pdfs), "--salientes", "--out", str(out), "--db", str(db)]) == 0
    assert "Via de salida" in capsys.readouterr().out
    assert cliente.llamadas == 1
    assert not list(out.glob("*.json")) and len(list((out / "salientes").glob("*.json"))) == 1

    def comprobar(ruta_db) -> None:
        with preparar(ruta_db) as almacen:
            conn = almacen.conn
            assert conn.execute("SELECT ruta_declarada FROM documento").fetchone()[0] \
                == "saliente"
            factura = conn.execute("SELECT id, sentido FROM factura").fetchone()
            assert factura["sentido"] == "saliente"
            [a8] = _hallazgos(conn, "A8", factura["id"])
            assert a8["severidad"] == "bloqueo"

    comprobar(db)
    otra = tmp_path / "otra" / "bms.sqlite3"
    assert main(["importar-out", "--out", str(out), "--db", str(otra)]) == 0
    assert f"{out / 'salientes'}/" in capsys.readouterr().out
    comprobar(otra)
    assert cliente.llamadas == 1
    # Lo pagado por la via de salida tambien cuenta en lo gastado.
    assert main(["coste", "--out", str(out)]) == 0
    assert "documentos leidos                 1" in capsys.readouterr().out


# ============================================================ reglas de venta sobre el almacen

def test_la_aritmetica_de_una_venta_retiene_y_la_de_una_compra_bloquea(compras) -> None:
    """D2 (las lineas suman la base) bloquea una compra y retiene una venta (§7)."""
    conn = compras.conn
    lineas = [_linea("Montagewerk", "10", "50,00", "500,00"),
              _linea("Montagewerk", "2", "50,00", "100,00")]
    datos = dict(base="700,00", iva="147,00", total="847,00", lineas=lineas)
    venta = _entrar(compras, "saliente", _documento("a7", numero="V2026-0300", iban=CUENTA_PROPIA,
                                                    **datos))
    compra = _entrar(compras, "entrante", _documento(
        "a8", numero="2026-5001", emisor=VAN_DIJK, emisor_btw=VAN_DIJK_BTW, receptor=EMPRESA,
        receptor_btw=None, **datos))
    [d2_venta] = _hallazgos(conn, "D2", venta)
    [d2_compra] = _hallazgos(conn, "D2", compra)
    assert (d2_venta["severidad"], d2_compra["severidad"]) == ("retencion", "bloqueo")
    assert _estado(conn, venta)[2] != "bloqueada" and _estado(conn, compra)[2] == "bloqueada"


def test_facturar_dos_veces_a_un_cliente_es_v7_y_no_b2(compras) -> None:
    conn = compras.conn
    lineas = [_linea("Montagewerk", "10", "50,00", "500,00")]
    datos = dict(numero="V2026-0400", base="500,00", iva="105,00", total="605,00", lineas=lineas,
                 iban=CUENTA_PROPIA)
    a = _entrar(compras, "saliente", _documento("b5", **datos))
    b = _entrar(compras, "saliente", _documento("b6", **datos))
    v7 = _hallazgos(conn, "V7", a)
    assert v7 and _hallazgos(conn, "V7", b) == v7
    assert {h["severidad"] for h in v7} == {"retencion"}
    assert not _hallazgos(conn, "B2", a) and not _hallazgos(conn, "B3", a)


def test_una_venta_con_un_iban_que_no_es_de_la_empresa_retiene_f10(compras) -> None:
    conn = compras.conn
    lineas = [_linea("Montagewerk", "10", "50,00", "500,00")]
    datos = dict(base="500,00", iva="105,00", total="605,00", lineas=lineas)
    ajena = _entrar(compras, "saliente", _documento("b7", numero="V2026-0500",
                                                    iban="NL02 ABNA 0123 4567 89", **datos))
    propia = _entrar(compras, "saliente", _documento("b8", numero="V2026-0501",
                                                     iban=CUENTA_PROPIA, **datos))
    [f10] = _hallazgos(conn, "F10", ajena)
    assert (f10["severidad"], f10["pegajosa"], f10["anulable"]) == ("retencion", 1, 0)
    assert not _hallazgos(conn, "F10", propia)
    # Ninguna cuenta de ningun documento entra en el registro de cuentas.
    assert conn.execute("SELECT count(*) FROM cuenta_bancaria WHERE iban = 'NL02ABNA0123456789' "
                        "AND titular <> 'proveedor'").fetchone()[0] == 0


# ============================================================ las vistas de proveedor y cliente

def _pagar(conn, factura_id: int, **datos) -> None:
    _orden(conn, "marcar_pagada", {"factura_id": factura_id, "rev": _rev(conn, factura_id),
                                   "motivo": "Pagada por transferencia, justificante archivado",
                                   **datos})


def _proveedor_de(conn, numero: str) -> int:
    return conn.execute("SELECT proveedor_id FROM factura WHERE numero = ?",
                        (numero,)).fetchone()[0]


def test_la_vista_de_un_proveedor(compras) -> None:
    """§3: pendiente y vencido, del ano y de siempre, lo pagado, por Objeto, historial de
    facturas y pagos, cuentas (registro e impresas), importe tipico, plazo de pago y retrasos,
    y avisos activos."""
    conn = compras.conn
    van_dijk = _proveedor_de(conn, "2026-4471")
    original, abono = factura_de(conn, "2026-4471"), factura_de(conn, "CN-2026-031")
    vista = consultas.proveedor(conn, van_dijk)
    assert (vista["nombre"], vista["exact_id"], vista["hoy"]) == (VAN_DIJK, "20001",
                                                                   "2026-10-14")
    assert (vista["facturas"], vista["abiertas"], vista["pendiente_cent"]) == (
        2, 2, 290279 - 12251)
    assert vista["siempre_facturado"] == vista["ano_facturado"] == {
        "facturas": 2, "base_cent": 239900 - 10125, "iva_cent": 50379 - 2126,
        "total_cent": 290279 - 12251, "base": "2.297,75", "total": "2.780,28"}
    assert (vista["siempre_pagado_cent"], vista["ano_pagado_cent"]) == (0, 0)
    # Lo gastado por Objeto mas lo que no tiene Objeto es la base de lo que cuenta.
    assert sum(o["importe_cent"] for o in vista["por_objeto"]) == 239900 - 10125
    assert sum(o["horas_mil"] for o in vista["por_objeto"]) > 0
    # El registro de cuentas (heredada del primer Exact) y lo que imprimen sus facturas.
    [cuenta] = vista["ibanes"]["registro"]
    assert (cuenta["iban"], cuenta["estado"], cuenta["pagable"]) == (
        "NL02ABNA0123456789", "heredada", True)
    assert [i["iban"] for i in vista["ibanes"]["impresos"]] == ["NL02ABNA0123456789"]
    assert vista["importe_tipico"]["facturas"] == 1 and vista["importe_tipico"][
        "media_cent"] == 239900
    assert {h["regla"] for h in vista["avisos"]["hallazgos"]} >= {"R4"}
    assert [f["id"] for f in vista["historial"]] == sorted(
        [original, abono], key=lambda i: conn.execute(
            "SELECT fecha_factura FROM factura WHERE id = ?", (i,)).fetchone()[0], reverse=True)
    # Pagada el dia de hoy, antes de vencer: cuenta para el plazo y no llega tarde.
    _pagar(conn, original)
    vista = consultas.proveedor(conn, van_dijk)
    assert (vista["pendiente_cent"], vista["siempre_pagado_cent"], vista["ano_pagado_cent"]) == (
        -12251, 290279, 290279)
    assert [p["factura_id"] for p in vista["pagos"]] == [original]
    plazo = vista["plazo_de_pago"]
    assert (plazo["pagadas"], plazo["media_dias"], plazo["tarde"]) == (1, 29, 0)
    # Smit: vencida, pagada hoy, llega tarde.
    smit, f_smit = _proveedor_de(conn, "2026-112"), factura_de(conn, "2026-112")
    vence = conn.execute("SELECT vencimiento FROM factura_estado WHERE factura_id = ?",
                         (f_smit,)).fetchone()[0]
    assert consultas.proveedor(conn, smit)["vencido_cent"] == 65340
    _pagar(conn, f_smit)
    [tarde] = consultas.proveedor(conn, smit)["plazo_de_pago"]["retrasos"]
    assert (tarde["factura_id"], tarde["vencimiento"], tarde["pagada_el"]) == (
        f_smit, vence, "2026-10-14")
    with pytest.raises(LookupError):
        consultas.proveedor(conn, 999)


def test_la_vista_de_un_cliente(ventas) -> None:
    """§4: lo que debe, lo facturado por Objeto (con las horas), su historial y sus avisos."""
    conn = ventas.conn
    haven = conn.execute("SELECT id FROM cliente WHERE exact_id = '10001'").fetchone()[0]
    _confirmar(conn, _relacion(conn, factura_de(conn, "C2026-0005"),
                               factura_de(conn, "V2026-0101")))
    vista = consultas.cliente(conn, haven)
    assert (vista["facturas"], vista["pendiente_cent"], vista["vencido_cent"]) == (
        2, 514976 - 30008, 0)
    por_objeto = {o["objeto"]: (o["importe_cent"], o["horas_mil"]) for o in vista["por_objeto"]}
    # Rijnhaven: 40 horas facturadas y 4 abonadas.
    assert por_objeto == {"Rijnhaven": (248000 - 24800, 36000), "Waalhaven": (177600, 24000)}
    assert "ibanes" not in vista
    assert not vista["avisos"]["hallazgos"] or all(
        h["regla"] != "R5" for h in vista["avisos"]["hallazgos"])
    lista = {c["id"]: c for c in consultas.clientes(conn)}
    assert lista[haven]["pendiente_cent"] == vista["pendiente_cent"]


@pytest.mark.parametrize("semilla", range(6))
def test_lo_pendiente_de_cada_parte_es_la_suma_de_sus_facturas_abiertas(compras, semilla) -> None:
    """Propiedad: con pagos parciales, pagos de mas, abonos enlazados y sustituciones al azar,
    lo pendiente de cada proveedor y cliente es la suma de lo pendiente de sus facturas
    abiertas, en la vista, en su lista, en la cache de estado y en la vista SQL."""
    conn = compras.conn
    ana = _ana(conn)
    importar_fichero(compras, "exact", "clientes", EXACT_CLIENTES, lanzado_por=ana)
    importar_fichero(compras, "exact", "facturas_venta", VENTAS, lanzado_por=ana)
    azar = random.Random(semilla)
    if azar.random() < 0.6:
        _orden(conn, "enlazar_facturas", {"origen_id": factura_de(conn, "CN-2026-031"),
                                          "destino_id": factura_de(conn, "2026-4471"),
                                          "tipo": "acredita", "motivo": MOTIVO})
    if azar.random() < 0.6:
        _confirmar(conn, _relacion(conn, factura_de(conn, "C2026-0005"),
                                   factura_de(conn, "V2026-0101")))
    if azar.random() < 0.5:
        _sustituta(compras, citar=False)
        _orden(conn, "enlazar_facturas", {"origen_id": factura_de(conn, "2026-4471-B"),
                                          "destino_id": factura_de(conn, "2026-4471"),
                                          "tipo": azar.choice(["sustituye", "corrige"]),
                                          "motivo": MOTIVO})
    for numero in ("2026-018", "2026-0912", "B-2026-077", "2026-112", "V2026-0102"):
        eleccion = azar.choice(["nada", "parcial", "entera", "de_mas"])
        f = factura_de(conn, numero)
        total = conn.execute("SELECT total_cent FROM factura WHERE id = ?", (f,)).fetchone()[0]
        if eleccion == "parcial":
            _pagar(conn, f, importe=f"{azar.randint(1, total - 1) / 100:.2f}")
        elif eleccion == "entera":
            _pagar(conn, f)
        elif eleccion == "de_mas":
            _pagar(conn, f, importe=f"{(total + 1000) / 100:.2f}")
    estado = {f[0]: (f[1], f[2]) for f in conn.execute(
        "SELECT factura_id, estado_pago, pendiente_cent FROM factura_estado")}
    for tabla, columna, de_todas, vista_sql in (
            ("proveedor", "proveedor_id", consultas.proveedores, "v_proveedor_totales"),
            ("cliente", "cliente_id", consultas.clientes, "v_cliente_totales")):
        sql = dict(conn.execute(f"SELECT {columna}, pendiente_cent FROM {vista_sql}"))
        parte_de = dict(conn.execute(f"SELECT id, {columna} FROM factura"))
        for resumen in de_todas(conn):
            parte_id = resumen["id"]
            vista = getattr(consultas, tabla)(conn, parte_id)
            abiertas = sum(f["pendiente_cent"] for f in vista["abiertas_detalle"])
            # Una factura en otra moneda (X1) no tiene importe: no suma en ningun sitio.
            cache = sum(p for f, (e, p) in estado.items() if e in ("pendiente", "vencida")
                        and p is not None and parte_de[f] == parte_id)
            assert vista["pendiente_cent"] == abiertas == cache == resumen["pendiente_cent"], (
                tabla, parte_id)
            assert sql.get(parte_id, 0) == vista["pendiente_cent"], (tabla, parte_id)
            vencidas = sum(f["pendiente_cent"] for f in vista["abiertas_detalle"]
                           if f["estado_pago"] == "vencida")
            assert vista["vencido_cent"] == vencidas


# ============================================================ CLI, API y consola

def test_las_vistas_y_las_relaciones_por_la_cli(tmp_path, capsys) -> None:
    from bms_agent import permisos
    from bms_agent.almacen import preparar
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    with preparar(db) as almacen:
        ana = persona(almacen.conn, "Ana", "administrador")
        token = permisos.emitir_token(almacen.conn, ana)
    for fuente, tipo, fichero in (("exact", "clientes", EXACT_CLIENTES),
                                  ("maestro_csv", "objetos", OBJETOS),
                                  ("exact", "facturas_venta", VENTAS)):
        assert main(["importar", fuente, tipo, str(fichero), "--token", token,
                     "--db", str(db)]) in (0, 1)
    salida = capsys.readouterr().out
    assert "4 fila(s) del fichero dan 3 factura(s)" in salida
    assert main(["relaciones", "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    assert "acredita" in salida and "C2026-0005" in salida and "V2026-0101" in salida
    assert main(["clientes", "--db", str(db)]) == 0
    assert "Havenbedrijf Rotterdam BV" in capsys.readouterr().out
    assert main(["relaciones", "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    with preparar(db) as almacen:
        conn = almacen.conn
        haven = conn.execute("SELECT id FROM cliente WHERE exact_id = '10001'").fetchone()[0]
        relacion = conn.execute("SELECT id, rev FROM factura_relacion").fetchone()
    assert "--relacion-id N --rev R" in salida
    assert main(["accion", "confirmar_relacion", "--relacion-id", str(relacion[0]),
                 "--rev", str(relacion[1]), "--motivo", MOTIVO, "--token", token,
                 "--db", str(db)]) == 0
    capsys.readouterr()
    assert main(["cliente", str(haven), "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    assert "pendiente      4.849,68" in salida and "Rijnhaven" in salida
    assert main(["cliente", str(haven), "--json", "--db", str(db)]) == 0
    assert json.loads(capsys.readouterr().out)["pendiente_cent"] == 484968
    assert main(["proveedor", "999", "--db", str(db)]) == 1
    assert main(["relaciones", "--db", str(db)]) == 0
    assert "No hay relaciones por confirmar" in capsys.readouterr().out
    assert main(["db", "verificar", "--db", str(db)]) == 0


GUION = "<script>alert('xss')</script>"


@pytest.fixture
def servidor_ventas(tmp_path):
    """El servidor de verdad sobre un almacen con las ventas de Exact; el nombre del cliente
    lleva HTML que se ejecutaria."""
    import threading

    from test_consola import AgenteFalso

    from bms_agent import permisos
    from bms_agent.almacen import preparar
    from bms_agent.serve import crear_servidor

    db = tmp_path / "datos" / "bms.sqlite3"
    clientes = tmp_path / "clientes.csv"
    clientes.write_text(EXACT_CLIENTES.read_text(encoding="utf-8-sig").replace(
        "10001;Havenbedrijf Rotterdam BV;", f"10001;Havenbedrijf {GUION} BV;"), encoding="utf-8")
    with preparar(db) as almacen:
        conn = almacen.conn
        ana = persona(conn, "Ana", "administrador")
        carla = persona(conn, "Carla", "consulta")
        importar_fichero(almacen, "exact", "clientes", clientes, lanzado_por=ana)
        importar_fichero(almacen, "maestro_csv", "objetos", OBJETOS, lanzado_por=ana)
        importar_fichero(almacen, "exact", "facturas_venta", VENTAS, lanzado_por=ana)
        tokens = {"ana": permisos.emitir_token(conn, ana),
                  "carla": permisos.emitir_token(conn, carla)}
        haven = conn.execute("SELECT id FROM cliente WHERE exact_id = '10001'").fetchone()[0]
    srv = crear_servidor(tmp_path / "facturas", tmp_path / "out", 0, token="token-del-servidor",
                         agente=AgenteFalso(), ruta_db=db)
    hilo = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    hilo.start()
    try:
        yield srv.server_address[1], tokens, haven, db
    finally:
        srv.shutdown()
        srv.server_close()


def test_las_vistas_y_las_relaciones_por_la_api(servidor_ventas) -> None:
    from test_consola import _leer, _orden, _pedir

    puerto, tokens, haven, _db = servidor_ventas
    estado, _c, datos = _leer(puerto, "/api/v2/clientes", tokens["carla"])
    assert estado == 200
    assert {c["id"]: c["pendiente_cent"] for c in datos["clientes"]}[haven] == 514976 - 30008
    estado, _c, datos = _leer(puerto, f"/api/v2/clientes/{haven}", tokens["carla"])
    assert estado == 200 and datos["cliente"]["nombre"] == f"Havenbedrijf {GUION} BV"
    # Waalhaven no entro (el maestro de Objetos lo ata al cliente por su nombre de antes): su
    # linea queda sin Objeto, y la vista lo dice en vez de esconderla.
    assert {o["objeto"] for o in datos["cliente"]["por_objeto"]} == {"Rijnhaven",
                                                                    "(sin Objeto)"}
    assert _leer(puerto, "/api/v2/clientes/999", tokens["carla"])[0] == 404
    assert _leer(puerto, "/api/v2/proveedores", tokens["carla"])[2] == {"proveedores": []}
    assert _leer(puerto, "/api/v2/proveedores/1", tokens["carla"])[0] == 404
    assert _pedir(puerto, "GET", "/api/v2/clientes")[0] == 401
    estado, _c, datos = _leer(puerto, "/api/v2/relaciones", tokens["carla"])
    [propuesta] = datos["relaciones"]
    assert (propuesta["tipo"], propuesta["fuente"]) == ("acredita", "exact")
    # Carla solo consulta: no confirma. Ana si.
    cuerpo = {"accion": "confirmar_relacion", "datos": {
        "relacion_id": propuesta["id"], "rev": propuesta["rev"], "motivo": MOTIVO}}
    assert _orden(puerto, tokens["carla"], cuerpo)[0] == 403
    estado, respuesta = _orden(puerto, tokens["ana"], cuerpo)
    assert estado == 200, respuesta
    assert _leer(puerto, "/api/v2/relaciones", tokens["ana"])[2] == {"relaciones": []}
    _e, _c, datos = _leer(puerto, f"/api/v2/clientes/{haven}", tokens["ana"])
    assert datos["cliente"]["pendiente_cent"] == 514976 - 30008
    estado, _c, ficha = _leer(puerto, f"/api/v2/facturas/{propuesta['destino_id']}",
                              tokens["ana"])
    [relacion] = ficha["factura"]["relaciones"]
    assert (relacion["estado"], relacion["papel"]) == ("confirmada", "destino")


def test_la_consola_pinta_la_vista_de_un_cliente_como_texto(servidor_ventas, tmp_path) -> None:
    """El nombre del cliente lleva <script>: la vista, la lista y las relaciones de la ficha se
    pintan como texto (nada de innerHTML; ningun elemento script)."""
    import shutil
    import subprocess

    from test_consola import DOM_DE_PRUEBA, _leer

    from bms_agent import consola_assets

    if shutil.which("node") is None:
        pytest.skip("sin node no se ejecuta el script")
    puerto, tokens, haven, _db = servidor_ventas
    _e, _c, vista = _leer(puerto, f"/api/v2/clientes/{haven}", tokens["ana"])
    _e, _c, lista = _leer(puerto, "/api/v2/clientes", tokens["ana"])
    _e, _c, relaciones_ = _leer(puerto, "/api/v2/relaciones", tokens["ana"])
    _e, _c, ficha = _leer(puerto, f"/api/v2/facturas/{relaciones_['relaciones'][0]['destino_id']}",
                          tokens["ana"])
    datos = tmp_path / "datos.json"
    datos.write_text(json.dumps({"vista": vista["cliente"], "lista": lista["clientes"],
                                 "ficha": ficha["factura"]}), encoding="utf-8")
    script = tmp_path / "consola.js"
    script.write_text(consola_assets.SCRIPT, encoding="utf-8")
    prefijo = DOM_DE_PRUEBA.split("const ficha = new Elemento")[0]
    prueba = tmp_path / "prueba.js"
    prueba.write_text(prefijo + r"""
const vista = new Elemento('div');
window.BMSConsola.pintarParte(vista, 'clientes', datos.vista);
const partes = new Elemento('div');
window.BMSConsola.pintarPartes(partes, [], datos.lista);
const ficha = new Elemento('div');
window.BMSConsola.pintarDetalle(ficha, datos.ficha);
process.stdout.write(JSON.stringify({
  etiquetas: [...new Set(creados.map(e => e.tagName))], vista: vista.textContent,
  partes: partes.textContent, ficha: ficha.textContent,
}));
""", encoding="utf-8")
    proceso = subprocess.run(["node", str(prueba), str(datos), str(script)],
                             capture_output=True, text=True, timeout=60)
    assert proceso.returncode == 0, proceso.stderr
    resultado = json.loads(proceso.stdout)
    assert "SCRIPT" not in resultado["etiquetas"]
    assert f"Havenbedrijf {GUION} BV" in resultado["vista"]
    assert f"Havenbedrijf {GUION} BV" in resultado["partes"]
    assert "Rijnhaven" in resultado["vista"] and "Relaciones" in resultado["ficha"]
    assert "acredita" in resultado["ficha"] and "Confirmar" in resultado["ficha"]


def test_un_listado_nuevo_de_exact_pone_al_dia_la_venta_y_sus_lineas(ventas, tmp_path) -> None:
    """La misma venta en un listado posterior: lo que cambio se actualiza (como dice Exact), la
    linea que ya no viene se retira con su imputacion, y nada se duplica."""
    conn = ventas.conn
    v101 = factura_de(conn, "V2026-0101")
    filas = VENTAS.read_text(encoding="utf-8-sig").splitlines()
    cabecera, primera = filas[0], filas[1]
    nueva = primera.replace("4.256,00;893,76;5.149,76", "2.480,00;520,80;3.000,80")
    fichero = tmp_path / "ventas-2.csv"
    fichero.write_text("\n".join([cabecera, nueva]) + "\n", encoding="utf-8")
    r = importar_fichero(ventas, "exact", "facturas_venta", fichero, lanzado_por=_ana(conn))
    assert [lote.estado for lote in r.lotes] == ["aceptada"]
    fila = conn.execute("SELECT * FROM factura WHERE id = ?", (v101,)).fetchone()
    assert (fila["base_cent"], fila["total_cent"]) == (248000, 300080)
    assert campos.procedencia(conn, "factura", v101)["total_cent"]["fuente"] == "importacion"
    vivas = conn.execute("SELECT orden FROM factura_linea WHERE factura_id = ? AND retirada_en "
                         "IS NULL", (v101,)).fetchall()
    assert [v[0] for v in vivas] == [1]
    assert conn.execute("SELECT count(*) FROM factura_imputacion WHERE factura_id = ? AND "
                        "retirada_en IS NULL", (v101,)).fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM factura WHERE origen = 'exact'").fetchone()[0] == 3
    # Lo de Exact no lo corrige una persona aqui: se corrige en Exact.
    with pytest.raises(campos.CampoDeOtroSistema):
        _orden(conn, "fijar_campo", {"tabla": "factura", "fila_id": v101, "campo": "total_cent",
                                     "valor": "3000,00", "rev": _rev(conn, v101),
                                     "motivo": MOTIVO})
    _limpio(conn)
