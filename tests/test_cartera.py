"""Las lecturas nuevas del motor para Cuentas por cobrar, por pagar y Documentos (paso 16).

Puertas del paso 16 que viven aqui:

- la cartera (GET /api/v2/cartera) dice lo mismo que el panel al centimo: sus
  `totales` son `panel.dinero_entra` (o `dinero_sale`) y salen de las mismas
  partidas; los tramos de antiguedad y las empresas suman lo pendiente, lo
  vencido son los tramos de 1 dia en adelante, y retenido mas sin retener es
  el total. Sobre la base de prueba en varias fechas, para que cada tramo
  tenga algo, y sobre el banco de las fixtures v1 antes y despues de una orden;
- lo pendiente de una empresa en la cartera es lo de su vista menos sus abonos
  sin enlazar, que la cartera da aparte: la documentacion decia que "por
  cobrar" llevaba los abonos de los proveedores y el codigo no los cuenta;
- los pagos propuestos que esperan a una persona, con las tres coincidencias,
  y las lineas del banco sin casar, con sus filtros;
- la carpeta de un cliente o un proveedor: los documentos que el sistema ya le
  enlaza (originales de facturas y abonos, justificantes de pagos, hojas de PO
  y de sus modificaciones), y la descarga auditada de cualquiera
  (documento_abierto), solo desde la app o la consola;
- en la ficha de una parte, su KvK, su correo de facturacion y sus contactos;
  en la busqueda, el filtro `tipo`;
- todo pide ver_facturas, y desde un origen declarado sale sin un IBAN entero.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import date, datetime, timedelta

import pytest
from conftest import (
    CUENTA_PROPIA,
    OTRA_CUENTA_PROPIA,
    RAIZ,
    apunte,
    camt053,
    cuentas_propias,
    factura_de,
    importar_camt,
    persona,
)
from test_consola import AgenteFalso, _pedir
from test_demo import base_demo  # noqa: F401 (la base de prueba, por modulo)
from test_pagos import (  # noqa: F401 (fixture)
    DESCONOCIDA,
    EXACT_PROVEEDORES,
    SMIT,
    VAN_DIJK,
    banco,
)

from bms_agent import consultas, flujo_caja, permisos, servicios
from bms_agent.almacen import preparar
from bms_agent.almacen.documentos import registrar_documento
from bms_agent.almacen.unidades import sha256_bytes
from bms_agent.cli import main
from bms_agent.importadores.registrar import importar_fichero
from bms_agent.permisos import usuario_por_nombre
from bms_agent.reloj import RelojFijo
from bms_agent.serve import CABECERA_CONTRATO, CABECERA_TOKEN, LECTURAS_V2, crear_servidor

IMPORTACION = RAIZ / "tests" / "fixtures" / "importacion"
SITIO = "http://localhost:5173"
_IBAN_ENTERO = re.compile(r"\b[A-Z]{2}\d{2}[A-Z]{4}\d{10}\b|\b[A-Z]{2}\d{2}(?: [A-Z0-9]{4}){3}")
MOTIVO = "Pagada desde la caja, recibo en la carpeta"


def _sin_floats(valor, camino="") -> list[str]:
    if isinstance(valor, float):
        return [camino]
    if isinstance(valor, dict):
        return [c for k, v in valor.items() for c in _sin_floats(v, f"{camino}.{k}")]
    if isinstance(valor, list):
        return [c for i, v in enumerate(valor) for c in _sin_floats(v, f"{camino}[{i}]")]
    return []


def _comprobar_cartera(conn, sentido: str) -> dict:
    """Las sumas que la pantalla da por buenas, contra el panel."""
    bloque = "dinero_entra" if sentido == "saliente" else "dinero_sale"
    panel = consultas.panel(conn)
    c = consultas.cartera(conn, sentido)
    t = c["totales"]
    # La tarjeta del inicio y la cabecera de la pantalla, al centimo.
    assert t == panel[bloque]
    assert c["movido_mes_cent"] == panel["caja"][
        "cobrado_mes_cent" if sentido == "saliente" else "pagado_mes_cent"]
    assert c["fechas"] == panel["caja"]["fechas"]
    # Los tramos suman lo pendiente y lo vencido es lo de 1 dia en adelante.
    tramos = {r["clave"]: r for r in c["tramos"]}
    assert list(tramos) == ["al_corriente", "1_30", "31_60", "61_90", "mas_de_90", "sin_fecha"]
    assert sum(r["importe_cent"] for r in c["tramos"]) == t["pendiente_cent"]
    assert sum(r["facturas"] for r in c["tramos"]) == t["facturas"]
    vencidos = ("1_30", "31_60", "61_90", "mas_de_90")
    assert sum(tramos[k]["importe_cent"] for k in vencidos) == t["vencido_cent"]
    assert sum(tramos[k]["facturas"] for k in vencidos) == t["vencidas"]
    assert tramos["sin_fecha"]["importe_cent"] == t["sin_fecha_cent"]
    # Las empresas suman lo pendiente, lo vencido y las facturas.
    partes = c["partes"]
    assert sum(p["pendiente_cent"] for p in partes) == t["pendiente_cent"]
    assert sum(p["vencido_cent"] for p in partes) == t["vencido_cent"]
    assert sum(p["facturas"] for p in partes) == t["facturas"]
    assert sum(p["vencidas"] for p in partes) == t["vencidas"]
    assert len({p["id"] for p in partes}) == len(partes)
    # La fila sin empresa del maestro, si la hay, va al final.
    assert all(p["id"] is not None for p in partes[:-1])
    # Lo retenido y lo libre son el total, y las empresas suman lo retenido.
    assert c["retenido"]["importe_cent"] + c["sin_retener"]["importe_cent"] == t["pendiente_cent"]
    assert c["retenido"]["facturas"] + c["sin_retener"]["facturas"] == t["facturas"]
    assert sum(p["retenido_cent"] for p in partes) == c["retenido"]["importe_cent"]
    for p in partes:
        assert (p["mas_antigua_dias"] is None) == (p["vencido_cent"] == 0 and p["vencidas"] == 0)
        assert p["pendiente"] == consultas._euros(p["pendiente_cent"])
    # Cada importe en enteros, con su texto al lado.
    assert _sin_floats(c) == []
    for r in c["tramos"]:
        assert r["importe"] == consultas._euros(r["importe_cent"])
    return c


def _abrir(ruta, fecha: str):
    return preparar(ruta, reloj=RelojFijo(datetime.fromisoformat(f"{fecha}T09:30:00+00:00")))


# ============================================================ la cartera es el panel

@pytest.mark.parametrize("fecha", ["2026-10-14", "2026-11-20", "2027-01-31"])
def test_la_cartera_dice_lo_mismo_que_el_panel_al_centimo(base_demo, fecha) -> None:  # noqa: F811
    """Sobre la base de prueba, el dia que se creo y despues: las mismas facturas envejecen
    y pasan de tramo, y las sumas siguen cuadrando."""
    ruta, _resumen = base_demo
    with _abrir(ruta, fecha) as almacen:
        for sentido in ("saliente", "entrante"):
            c = _comprobar_cartera(almacen.conn, sentido)
            assert c["sentido"] == sentido and c["hoy"] == fecha
            assert c["totales"]["facturas"] > 0


def test_los_tramos_de_la_base_de_prueba_se_llenan_con_los_dias(base_demo) -> None:  # noqa: F811
    ruta, _resumen = base_demo
    llenos = set()
    for fecha in ("2026-10-14", "2026-11-20", "2027-01-31"):
        with _abrir(ruta, fecha) as almacen:
            for sentido in ("saliente", "entrante"):
                c = consultas.cartera(almacen.conn, sentido)
                llenos |= {r["clave"] for r in c["tramos"] if r["facturas"]}
    assert {"al_corriente", "61_90", "mas_de_90"} <= llenos
    assert len(llenos) >= 4


def test_una_empresa_es_su_vista_menos_sus_abonos_sin_enlazar(base_demo) -> None:  # noqa: F811
    """La vista de una parte resta sus abonos sin enlazar (lo que la acredita es suyo, R4);
    la cartera, como el panel, solo cuenta deudas y los da aparte. Las dos cifras se
    explican una con la otra: no hay una tercera."""
    ruta, _resumen = base_demo
    with _abrir(ruta, "2026-10-14") as almacen:
        conn = almacen.conn
        for sentido, lista in (("saliente", consultas.clientes(conn)),
                               ("entrante", consultas.proveedores(conn))):
            c = consultas.cartera(conn, sentido)
            por_id = {p["id"]: p for p in c["partes"]}
            abonos = c["abonos_sin_enlazar"]
            assert abonos["importe_cent"] == sum(a["pendiente_cent"] for a in abonos["lista"])
            assert all(a["pendiente_cent"] < 0 for a in abonos["lista"])
            for fila in lista:
                suya = por_id.get(fila["id"], {"pendiente_cent": 0, "vencido_cent": 0})
                abonado = sum(a["pendiente_cent"] for a in abonos["lista"]
                              if a["parte_id"] == fila["id"])
                assert fila["pendiente_cent"] == suya["pendiente_cent"] + abonado, fila["nombre"]
                assert fila["vencido_cent"] == suya["vencido_cent"], fila["nombre"]
        # La base de prueba lleva un abono de un proveedor sin enlazar: no es "por cobrar".
        entrante = consultas.cartera(conn, "entrante")["abonos_sin_enlazar"]
        saliente = consultas.cartera(conn, "saliente")
        assert entrante["facturas"] >= 1
        ids = {a["id"] for a in entrante["lista"]}
        assert not ids & {p.factura_id for p in flujo_caja.datos(conn)[0]}
        assert saliente["totales"] == consultas.panel(conn)["dinero_entra"]


def test_los_tramos_cubren_cada_dia_y_abren_la_busqueda_que_les_toca() -> None:
    casos = {-30: "al_corriente", 0: "al_corriente", 1: "1_30", 30: "1_30", 31: "31_60",
             60: "31_60", 61: "61_90", 90: "61_90", 91: "mas_de_90", 4000: "mas_de_90",
             None: "sin_fecha"}
    for dias, clave in casos.items():
        assert consultas.tramo_de(dias) == clave, dias
    hoy = date(2026, 10, 14)
    for clave, desde, hasta in consultas.TRAMOS:
        vence_desde, vence_hasta = consultas._limites_tramo(hoy, desde, hasta)
        for dias in range(-5, 200):
            vence = hoy - timedelta(days=dias)
            dentro = ((vence_desde is None or vence.isoformat() >= vence_desde)
                      and (vence_hasta is None or vence.isoformat() <= vence_hasta))
            assert dentro == (consultas.tramo_de(dias) == clave), (clave, dias)


def test_el_sentido_de_la_cartera_es_obligatorio() -> None:
    for malo in (None, "", "  ", "ventas", "SALIENTE"):
        with pytest.raises(consultas.FiltroNoValido):
            consultas.sentido_cartera(malo)
    assert consultas.sentido_cartera("entrante") == "entrante"


# ============================================================ el banco: propuestas y sin casar

def _con_banco(banco) -> None:  # noqa: F811
    """Un extracto con un pago que se casa solo (Van Dijk), uno que se propone (Smit), un
    ingreso y un cargo que no casan con nada, y un traspaso a otra cuenta propia."""
    conn = banco.conn
    importar_camt(banco, usuario_por_nombre(conn, "Ana"), camt053(
        apunte("-2902.79", iban=VAN_DIJK, nombre="Bouwtechniek Van Dijk BV",
               concepto="Factuur 2026-4471"),
        apunte("-653.40", "2026-10-13", iban=SMIT, nombre="Loodgietersbedrijf Smit",
               concepto="Factuur 2026-112"),
        apunte("500.00", iban=DESCONOCIDA, nombre="Iemand Onbekend", concepto="Storting"),
        apunte("-75.00", "2026-10-13", nombre="Garage Demo", concepto="Onderhoud bus"),
        apunte("-1000.00", iban=OTRA_CUENTA_PROPIA, nombre="BM Support BV",
               concepto="Naar spaarrekening")))


def test_lo_que_espera_a_una_persona_y_lo_que_no_casa(banco) -> None:  # noqa: F811
    conn = banco.conn
    _con_banco(banco)
    entrante = _comprobar_cartera(conn, "entrante")
    saliente = _comprobar_cartera(conn, "saliente")
    assert entrante["por_confirmar"] == {"pagos": 1, "importe_cent": 65340, "importe": "653,40"}
    assert saliente["por_confirmar"]["pagos"] == 0
    # Un ingreso sin casar es de cobrar; un cargo, de pagar. El traspaso a la cuenta de
    # ahorro no paga nada: ni sale.
    assert saliente["sin_casar"] == {"movimientos": 1, "importe_cent": 50000,
                                     "importe": "500,00"}
    assert entrante["sin_casar"] == {"movimientos": 1, "importe_cent": 7500, "importe": "75,00"}

    [p] = consultas.propuestas_pago(conn)
    assert consultas.propuestas_pago(conn, "entrante") == [p]
    assert consultas.propuestas_pago(conn, "saliente") == []
    with pytest.raises(consultas.FiltroNoValido):
        consultas.propuestas_pago(conn, "compras")
    smit = factura_de(conn, "2026-112")
    assert (p["lado"], p["importe_cent"], p["fecha_pago"], p["regla"]) == (
        "pago", 65340, "2026-10-13", "referencia+importe")
    assert p["coincidencias"] == {"referencia": True, "importe": True, "contraparte": False}
    assert p["factura"]["id"] == smit and p["factura"]["numero"] == "2026-112"
    assert p["factura"]["pendiente_cent"] == 65340          # una propuesta no paga nada
    assert p["factura"]["estado_pago"] in ("pendiente", "vencida")
    m = p["movimiento"]
    assert (m["importe_cent"], m["contraparte"], m["contraparte_iban"], m["concepto"]) == (
        -65340, "Loodgietersbedrijf Smit", SMIT, "Factuur 2026-112")
    rev = conn.execute("SELECT rev FROM aplicacion_pago WHERE id = ?", (p["id"],)).fetchone()[0]
    assert p["rev"] == rev

    # Una persona la confirma: sale de por confirmar y baja lo pendiente, y todo sigue
    # cuadrando con el panel.
    antes = entrante["totales"]["pendiente_cent"]
    servicios.ejecutar(conn, "confirmar_pago", {"aplicacion_id": p["id"], "rev": p["rev"]},
                       usuario_id=usuario_por_nombre(conn, "Ana"))
    despues = _comprobar_cartera(conn, "entrante")
    assert despues["por_confirmar"]["pagos"] == 0
    assert despues["totales"]["pendiente_cent"] == antes - 65340
    assert consultas.propuestas_pago(conn) == []


def test_las_lineas_del_banco_sin_casar_y_sus_filtros(banco) -> None:  # noqa: F811
    conn = banco.conn
    _con_banco(banco)
    m = consultas.movimientos_banco(conn)
    assert m["total"] == 2 and m["filtros"] == {"sin_casar": "si"}
    assert [r["importe_cent"] for r in m["lista"]] == [-7500, 50000]   # la mas reciente primero
    assert all(r["abierto"] and r["resto_cent"] == r["importe_cent"] for r in m["lista"])
    assert m["entradas"] == {"movimientos": 1, "importe_cent": 50000, "importe": "500,00",
                             "sin_casar_cent": 50000, "sin_casar": "500,00"}
    assert m["salidas"]["sin_casar_cent"] == -7500
    [ingreso] = consultas.movimientos_banco(conn, {"signo": "entrada"})["lista"]
    assert (ingreso["contraparte"], ingreso["contraparte_iban"], ingreso["cuenta_propia_iban"]
            ) == ("Iemand Onbekend", DESCONOCIDA, CUENTA_PROPIA)
    assert ingreso["dias"] == 2 and ingreso["propia"] is False
    assert [r["contraparte"] for r in consultas.movimientos_banco(
        conn, {"texto": "GARAGE"})["lista"]] == ["Garage Demo"]
    assert [r["contraparte"] for r in consultas.movimientos_banco(
        conn, {"texto": "storting"})["lista"]] == ["Iemand Onbekend"]
    assert consultas.movimientos_banco(conn, {"desde": "2026-10-13"})["total"] == 1
    assert consultas.movimientos_banco(conn, {"hasta": "2026-10-12"})["total"] == 1
    limitada = consultas.movimientos_banco(conn, {"limite": "1"})
    assert limitada["total"] == 2 and len(limitada["lista"]) == 1
    # Todas: lo casado queda a cero, lo propuesto tambien (espera a una persona) y el
    # traspaso entre cuentas propias se dice.
    todas = consultas.movimientos_banco(conn, {"sin_casar": "no"})
    assert todas["total"] == 5
    por_iban = {r["contraparte_iban"]: r for r in todas["lista"]}
    assert (por_iban[VAN_DIJK]["resto_cent"], por_iban[VAN_DIJK]["confirmadas"],
            por_iban[VAN_DIJK]["abierto"]) == (0, 1, False)
    assert (por_iban[SMIT]["resto_cent"], por_iban[SMIT]["propuestas"]) == (0, 1)
    assert por_iban[OTRA_CUENTA_PROPIA]["propia"] is True
    assert por_iban[OTRA_CUENTA_PROPIA]["abierto"] is False
    for malo in ({"signo": "arriba"}, {"limite": "0"}, {"limite": "1001"}, {"desde": "ayer"},
                 {"sin_casar": "quizas"}, {"cuenta": "x"}):
        with pytest.raises(consultas.FiltroNoValido):
            consultas.movimientos_banco(conn, malo)


def test_lo_retenido_es_lo_que_bloquea_o_retiene(banco) -> None:  # noqa: F811
    """Comprobado por otro camino: los hallazgos activos de cada factura, leidos de las
    tablas, y su nivel. Un aviso (K1, vencida) no retiene."""
    conn = banco.conn
    _con_banco(banco)
    c = consultas.cartera(conn, "entrante")
    retienen = {f for (f,) in conn.execute(
        "SELECT h.factura_id FROM hallazgo h WHERE h.estado IN ('abierto', 'desaparecido') "
        "AND h.severidad IN ('bloqueo', 'retencion') AND h.factura_id IS NOT NULL "
        "UNION SELECT o.fila_id FROM hallazgo_objetivo o JOIN hallazgo h ON h.id = o.hallazgo_id "
        "WHERE o.tabla = 'factura' AND h.estado IN ('abierto', 'desaparecido') "
        "AND h.severidad IN ('bloqueo', 'retencion') "
        "UNION SELECT factura_id FROM factura_estado WHERE nivel = 'bloqueada'")}
    partidas = [p for p in flujo_caja.datos(conn)[0] if p.direccion == flujo_caja.SALIDA]
    assert c["retenido"]["importe_cent"] == sum(p.importe_cent for p in partidas
                                                if p.factura_id in retienen)
    assert c["retenido"]["facturas"] > 0 and c["sin_retener"]["facturas"] > 0


# ============================================================ la API y el archivo

@pytest.fixture
def archivo(tmp_path, out_v1, pdfs_ejemplo):
    """Un almacen en disco: las siete v1 (tres con su PDF), los maestros de Exact (con
    contactos), un extracto del banco, un pago a mano con el extracto de justificante y una
    PO con su hoja y una modificacion con la suya. Ana lo puede todo, Dora solo lee y Nadie
    no puede ver facturas."""
    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(pdfs_ejemplo),
                 "--db", str(db)]) == 0
    with preparar(db) as almacen:
        conn = almacen.conn
        ana = persona(conn, "Ana", "administrador")
        dora = persona(conn, "Dora", "consulta")
        permisos.crear_rol(conn, "solo_notas", ["anadir_informacion"])
        nadie = persona(conn, "Nadie")
        permisos.asignar_rol(conn, nadie, "solo_notas")
        cuentas_propias(almacen, ana)
        for fuente, tipo, fichero in (("exact", "proveedores", EXACT_PROVEEDORES),
                                      ("exact", "clientes", IMPORTACION / "exact-clientes-v1.csv"),
                                      ("maestro_csv", "contactos",
                                       IMPORTACION / "maestro_csv-contactos-v1.csv")):
            importar_fichero(almacen, fuente, tipo, fichero, lanzado_por=ana)
        importar_camt(almacen, ana, camt053(
            apunte("-653.40", "2026-10-13", iban=SMIT, nombre="Loodgietersbedrijf Smit",
                   concepto="Factuur 2026-112"),
            apunte("500.00", iban=DESCONOCIDA, nombre="Iemand Onbekend", concepto="Storting")))
        extracto = conn.execute("SELECT documento_id FROM importacion WHERE fuente = 'banco'"
                                ).fetchone()[0]
        f018 = factura_de(conn, "2026-018")
        rev = conn.execute("SELECT rev FROM factura WHERE id = ?", (f018,)).fetchone()[0]
        servicios.ejecutar(conn, "marcar_pagada", {
            "factura_id": f018, "rev": rev, "motivo": MOTIVO, "fecha_pago": "2026-10-01",
            "evidencia_documento_id": extracto}, usuario_id=ana)
        proveedor = conn.execute("SELECT proveedor_id FROM factura WHERE numero = '2026-4471'"
                                 ).fetchone()[0]
        hojas = []
        for nombre in ("PO-4500.pdf", "PO-4500-wijziging.pdf"):
            contenido = f"%PDF-1.4 hoja {nombre}".encode()
            hojas.append(registrar_documento(
                almacen, sha256=sha256_bytes(contenido), contenido=contenido,
                nombre_original=nombre, tipo_mime="application/pdf", origen="manual",
                ruta_declarada="maestro", recibido_en=None, recibido_fuente="desconocido",
                actor=ana, usuario_id=ana).id)
        po = servicios.ejecutar(conn, "registrar_po", {
            "numero": "PO-4500", "lado": "proveedor", "parte_id": proveedor, "valor": "5000",
            "fecha_emision": "2026-09-01", "documento_id": hojas[0],
            "motivo": "Hoja firmada"}, usuario_id=ana)
        po_id = conn.execute("SELECT id FROM orden_compra WHERE numero = 'PO-4500'").fetchone()[0]
        servicios.ejecutar(conn, "modificar_po", {
            "orden_compra_id": po_id, "valor": "6000", "fecha": "2026-10-01",
            "documento_id": hojas[1], "motivo": "Ampliada por el cliente"}, usuario_id=ana)
        assert po is not None
        tokens = {n: permisos.emitir_token(conn, u) for n, u in
                  (("ana", ana), ("dora", dora), ("nadie", nadie))}
        ids = {"proveedor": proveedor, "f018": f018, "extracto": extracto, "hojas": hojas,
               "po": po_id,
               "proveedor_018": conn.execute("SELECT proveedor_id FROM factura WHERE id = ?",
                                             (f018,)).fetchone()[0]}
    srv = crear_servidor(tmp_path / "facturas", tmp_path / "vacio", 0, token="token-servidor",
                         agente=AgenteFalso(), ruta_db=db, origenes_extra=[SITIO])
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05},
                     daemon=True).start()
    try:
        yield srv.server_address[1], tokens, db, ids
    finally:
        srv.shutdown()
        srv.server_close()


def _leer(puerto: int, ruta: str, token: str | None, **cabeceras):
    pedidas = {**({CABECERA_TOKEN: token} if token else {}), **cabeceras}
    estado, cabeceras_r, datos = _pedir(puerto, "GET", ruta, pedidas)
    try:
        cuerpo = json.loads(datos) if datos else None
    except (json.JSONDecodeError, UnicodeDecodeError):
        cuerpo = datos
    return estado, cabeceras_r, cuerpo


def test_las_lecturas_nuevas_por_la_api(archivo) -> None:
    puerto, tokens, db, ids = archivo
    dora = tokens["dora"]
    estado, cabeceras, contrato = _leer(puerto, "/api/v2/contrato", dora)
    assert estado == 200 and cabeceras[CABECERA_CONTRATO.lower()] == consultas.CONTRATO_V2 == "2.2"
    rutas = {r["ruta"] for r in contrato["lecturas"]}
    assert {"/api/v2/cartera", "/api/v2/pagos/propuestas", "/api/v2/movimientos",
            "/api/v2/clientes/N/documentos", "/api/v2/proveedores/N/documentos",
            "/api/v2/documentos/N/original"} <= rutas
    # La cartera por la API es la de Python y la del panel (Dora solo lee: le basta).
    _e, _c, panel = _leer(puerto, "/api/v2/panel", dora)
    for sentido, bloque in (("entrante", "dinero_sale"), ("saliente", "dinero_entra")):
        estado, _c, r = _leer(puerto, f"/api/v2/cartera?sentido={sentido}", dora)
        assert estado == 200 and r["cartera"]["totales"] == panel["panel"][bloque]
        with preparar(db) as almacen:
            assert r["cartera"] == json.loads(json.dumps(consultas.cartera(almacen.conn,
                                                                           sentido)))
    for ruta, codigo in (("/api/v2/cartera", 400), ("/api/v2/cartera?sentido=", 400),
                         ("/api/v2/cartera?sentido=ventas", 400),
                         ("/api/v2/cartera?sentido=entrante&sentido=saliente", 400),
                         ("/api/v2/pagos/propuestas?sentido=x", 400),
                         ("/api/v2/movimientos?signo=x", 400),
                         ("/api/v2/movimientos?limite=0", 400),
                         ("/api/v2/clientes/999/documentos", 404),
                         ("/api/v2/proveedores/999/documentos", 404),
                         ("/api/v2/documentos/999/original", 404),
                         ("/api/v2/documentos/99999999999999999999999/original", 404),
                         ("/api/v2/facturas/99999999999999999999999", 404)):
        estado, _c, cuerpo = _leer(puerto, ruta, dora)
        assert estado == codigo, (ruta, estado, cuerpo)
        assert cuerpo["codigo"] == ("invalido" if codigo == 400 else "no_existe"), ruta
    estado, _c, r = _leer(puerto, "/api/v2/pagos/propuestas", dora)
    assert estado == 200 and [p["factura"]["numero"] for p in r["propuestas"]] == ["2026-112"]
    estado, _c, r = _leer(puerto, "/api/v2/movimientos?signo=entrada", dora)
    assert estado == 200 and r["movimientos"]["total"] == 1
    assert r["movimientos"]["lista"][0]["contraparte_iban"] == DESCONOCIDA
    # Sin token, 401; sin ver_facturas, 403: tambien la descarga.
    nuevas = ["/api/v2/cartera?sentido=entrante", "/api/v2/pagos/propuestas",
              "/api/v2/movimientos", f"/api/v2/proveedores/{ids['proveedor']}/documentos",
              f"/api/v2/documentos/{ids['extracto']}/original"]
    for ruta in nuevas:
        assert _leer(puerto, ruta, None)[0] == 401, ruta
        estado, _c, cuerpo = _leer(puerto, ruta, tokens["nadie"])
        assert estado == 403 and cuerpo["codigo"] == "sin_permiso", ruta


def test_desde_otro_origen_las_lecturas_nuevas_no_llevan_un_iban(archivo) -> None:
    puerto, tokens, _db, ids = archivo
    for ruta in ("/api/v2/pagos/propuestas", "/api/v2/movimientos?sin_casar=no",
                 "/api/v2/cartera?sentido=entrante",
                 f"/api/v2/proveedores/{ids['proveedor']}",
                 f"/api/v2/proveedores/{ids['proveedor']}/documentos"):
        estado, cabeceras, cuerpo = _pedir(puerto, "GET", ruta,
                                           {CABECERA_TOKEN: tokens["dora"], "Origin": SITIO})
        assert estado == 200 and cabeceras["access-control-allow-origin"] == SITIO, ruta
        assert not _IBAN_ENTERO.search(cuerpo.decode("utf-8")), ruta
    # La app (el mismo origen) los ve enteros: es donde se trabaja con el banco.
    _e, _c, cuerpo = _pedir(puerto, "GET", "/api/v2/movimientos?sin_casar=no",
                            {CABECERA_TOKEN: tokens["dora"]})
    assert SMIT in cuerpo.decode("utf-8") and CUENTA_PROPIA in cuerpo.decode("utf-8")
    _e, _c, cuerpo = _pedir(puerto, "GET", "/api/v2/movimientos?sin_casar=no",
                            {CABECERA_TOKEN: tokens["dora"], "Origin": SITIO})
    assert "NL..6789" in cuerpo.decode("utf-8")


def test_la_carpeta_de_un_proveedor(archivo) -> None:
    puerto, tokens, db, ids = archivo
    estado, _c, r = _leer(puerto, f"/api/v2/proveedores/{ids['proveedor']}/documentos",
                          tokens["dora"])
    assert estado == 200
    carpeta = r["documentos"]
    assert carpeta["parte"]["tabla"] == "proveedor" and carpeta["parte"]["id"] == ids["proveedor"]
    assert carpeta["total"] == len(carpeta["documentos"])
    por_tipo = {}
    for d in carpeta["documentos"]:
        por_tipo.setdefault(d["tipo"], []).append(d)
        assert set(d) >= {"id", "tipo", "fecha", "numero", "bytes", "nombre", "tipo_mime",
                          "guardado", "vinculo", "importe_cent", "importe", "estado_pago"}
        assert d["tipo"] in consultas.TIPOS_DOCUMENTO
    assert {"factura_compra", "orden_compra", "modificacion_po"} <= set(por_tipo)
    [hoja] = por_tipo["orden_compra"]
    assert (hoja["id"], hoja["numero"], hoja["fecha"], hoja["importe_cent"], hoja["nombre"]) == (
        ids["hojas"][0], "PO-4500", "2026-09-01", 500000, "PO-4500.pdf")
    assert hoja["vinculo"] == {"tabla": "orden_compra", "id": ids["po"],
                               "orden_compra_id": ids["po"]}
    [cambio] = por_tipo["modificacion_po"]
    assert (cambio["id"], cambio["fecha"], cambio["importe_cent"]) == (
        ids["hojas"][1], "2026-10-01", 600000)
    [factura] = [d for d in por_tipo["factura_compra"] if d["numero"] == "2026-4471"]
    assert factura["guardado"] is True and factura["bytes"] > 0
    assert factura["vinculo"]["tabla"] == "factura"
    assert factura["estado_pago"] in ("pendiente", "vencida")       # el reloj es el de verdad
    fechas = [d["fecha"] for d in carpeta["documentos"] if d["fecha"]]
    assert fechas == sorted(fechas, reverse=True)
    # El justificante del pago a mano va en la carpeta del proveedor de esa factura.
    estado, _c, r = _leer(puerto, f"/api/v2/proveedores/{ids['proveedor_018']}/documentos",
                          tokens["dora"])
    [justificante] = [d for d in r["documentos"]["documentos"] if d["tipo"] == "justificante_pago"]
    assert justificante["id"] == ids["extracto"] and justificante["fecha"] == "2026-10-01"
    assert justificante["vinculo"]["factura_id"] == ids["f018"]
    assert justificante["vinculo"]["fuente"] == "manual"
    # La lista dice cuantos tiene cada carpeta, los mismos.
    _e, _c, lista = _leer(puerto, "/api/v2/proveedores", tokens["dora"])
    [fila] = [p for p in lista["proveedores"] if p["id"] == ids["proveedor"]]
    assert fila["documentos"] == carpeta["total"]


def test_un_documento_se_descarga_auditado_y_solo_desde_la_app(archivo) -> None:
    puerto, tokens, db, ids = archivo
    with preparar(db) as almacen:
        guardados = almacen.conn.execute(
            "SELECT id, sha256 FROM documento WHERE ruta_cas IS NOT NULL ORDER BY id").fetchall()
        sin_original = almacen.conn.execute(
            "SELECT id FROM documento WHERE ruta_cas IS NULL ORDER BY id LIMIT 1").fetchone()[0]
    assert {ids["extracto"], *ids["hojas"]} <= {g["id"] for g in guardados}
    for documento in (ids["extracto"], ids["hojas"][0]):
        ruta = f"/api/v2/documentos/{documento}/original"
        estado, cabeceras, cuerpo = _pedir(puerto, "GET", ruta, {CABECERA_TOKEN: tokens["dora"]})
        sha = {g["id"]: g["sha256"] for g in guardados}[documento]
        assert estado == 200 and hashlib.sha256(cuerpo).hexdigest() == sha
        assert cabeceras["content-disposition"].startswith("attachment;")
        assert cabeceras["content-security-policy"] == "default-src 'none'; sandbox"
        assert cabeceras["x-content-type-options"] == "nosniff"
        assert cabeceras["cache-control"] == "no-store"
        assert "access-control-allow-origin" not in cabeceras
        # Desde un sitio declarado, no: ni los bytes ni la cabecera CORS.
        estado, cabeceras, cuerpo = _pedir(puerto, "GET", ruta, {
            CABECERA_TOKEN: tokens["dora"], "Origin": SITIO})
        assert estado == 403 and json.loads(cuerpo)["codigo"] == "otro_origen"
        assert "access-control-allow-origin" not in cabeceras
    estado, _c, cuerpo = _leer(puerto, f"/api/v2/documentos/{sin_original}/original",
                               tokens["dora"])
    assert estado == 404 and cuerpo["codigo"] == "no_existe"
    with preparar(db) as almacen:
        dora = usuario_por_nombre(almacen.conn, "Dora")
        abiertos = almacen.conn.execute(
            "SELECT usuario_id, fila_id, resultado, motivo FROM evento "
            "WHERE tipo = 'documento_abierto' ORDER BY id").fetchall()
    assert [(a["usuario_id"], a["fila_id"], a["resultado"]) for a in abiertos] == [
        (dora, ids["extracto"], "ok"), (dora, ids["hojas"][0], "ok"),
        (dora, sin_original, "error")]
    assert abiertos[0]["motivo"] == f"descargado desde la consola (documento {ids['extracto']})"


def test_la_ficha_de_una_parte_trae_lo_del_maestro(archivo) -> None:
    puerto, tokens, _db, ids = archivo
    _e, _c, r = _leer(puerto, f"/api/v2/proveedores/{ids['proveedor']}", tokens["dora"])
    v = r["proveedor"]
    assert (v["kvk"], v["email_facturacion"], v["direccion"]) == (
        "87654321", "facturen@vandijk.example", "Havenstraat 12, 3011 AA, Rotterdam")
    assert [(c["nombre"], c["email"], c["funcion"], c["activo"]) for c in v["contactos"]] == [
        ("Marieke de Boer", "m.deboer@vandijk.example", "Crediteurenadministratie", True)]
    assert [o["numero"] for o in v["ordenes_compra"]] == ["PO-4500"]
    assert v["documentos"] >= 4
    _e, _c, r = _leer(puerto, "/api/v2/clientes", tokens["dora"])
    cliente = next(c for c in r["clientes"] if c["exact_id"] == "10001")
    _e, _c, r = _leer(puerto, f"/api/v2/clientes/{cliente['id']}", tokens["dora"])
    v = r["cliente"]
    # El maestro de clientes no guarda correo ni direccion: null, nunca un texto inventado.
    assert v["email_facturacion"] is None and v["direccion"] is None and v["kvk"]
    assert [c["nombre"] for c in v["contactos"]] == ["Sara Jansen"]
    assert v["objetos"] == [] and v["ordenes_compra"] == [] and v["documentos"] == 0
    # Un contacto inactivo sale, detras, marcado.
    otro = next(c for c in _leer(puerto, "/api/v2/clientes", tokens["dora"])[2]["clientes"]
                if c["exact_id"] == "10002")
    v = _leer(puerto, f"/api/v2/clientes/{otro['id']}", tokens["dora"])[2]["cliente"]
    assert [(c["nombre"], c["activo"]) for c in v["contactos"]] == [("Oud contact", False)]


def test_la_busqueda_filtra_por_tipo(archivo) -> None:
    puerto, tokens, _db, _ids = archivo
    _e, _c, r = _leer(puerto, "/api/v2/buscar?tipo=nota_credito", tokens["dora"])
    assert [f["numero"] for f in r["busqueda"]["facturas"]] == ["CN-2026-031"]
    _e, _c, r = _leer(puerto, "/api/v2/buscar?tipo=factura", tokens["dora"])
    assert r["busqueda"]["total"] == 6 and all(f["tipo"] == "factura"
                                              for f in r["busqueda"]["facturas"])
    _e, _c, r = _leer(puerto, "/api/v2/buscar?tipo=factura,nota_credito", tokens["dora"])
    assert r["busqueda"]["total"] == 7
    estado, _c, cuerpo = _leer(puerto, "/api/v2/buscar?tipo=contrato", tokens["dora"])
    assert estado == 400 and cuerpo["codigo"] == "invalido"


def test_cada_lectura_nueva_esta_en_la_lista_y_rechaza_lo_que_no_admite(archivo) -> None:
    puerto, tokens, _db, _ids = archivo
    nuevas = [r for r, _p in LECTURAS_V2 if r.startswith(("/api/v2/cartera", "/api/v2/pagos",
                                                          "/api/v2/movimientos"))
              or r.endswith(("/documentos", "/documentos/N/original"))]
    assert len(nuevas) == 6
    for ruta in nuevas:
        ejemplo = ruta.replace("/N/", "/1/").replace("/N", "/1")
        estado, _c, cuerpo = _leer(puerto, f"{ejemplo}?cosa=1", tokens["dora"])
        assert estado == 400 and "cosa" in cuerpo["error"], ruta
