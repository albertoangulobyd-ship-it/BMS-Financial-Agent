"""Los hallazgos en el almacen: deteccion, ciclo de vida, pegajosos y anulaciones.

Cada caso parte de extracciones v1 escritas a mano (la 01 de ejemplo con lo
que haga falta cambiado), las importa y las tipa como la orden de verdad, y
corrige con campos.py como lo haria una persona. Asi lo que se prueba es la
cadena entera: extraccion, valores tipados, instantanea, reglas, hallazgos.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import random
import sqlite3
from datetime import date
from decimal import Decimal

import pytest
from conftest import FIXTURES_V1, TARIFAS_V1, factura_de, persona

from bms_agent import campos, hallazgos, ingesta
from bms_agent.almacen import preparar, transaccion, usuario_sistema
from bms_agent.almacen.evidencia import verificar_evidencia
from bms_agent.auditoria import registrar, verificar_cadena
from bms_agent.campos import Automatico, FaltaMotivo, Persona
from bms_agent.importadores.extracciones import importar_out
from bms_agent.permisos import PermisoDenegado, SeparacionDeFunciones
from bms_agent.reglas import catalogo, instantanea

MOTIVO = "Comprobado con el proveedor por telefono"


def _registro(nombre: str, *, sha: str | None = None, **extraccion) -> dict:
    registro = json.loads((FIXTURES_V1 / "01-limpia.json").read_text(encoding="utf-8"))
    registro["source_name"] = f"{nombre}.pdf"
    registro["source_sha256"] = sha or hashlib.sha256(f"prueba:{nombre}".encode()).hexdigest()
    registro["extraction"].update(extraccion)
    return registro


def _cargar(almacen, carpeta, *registros: dict) -> None:
    carpeta.mkdir(exist_ok=True)
    for registro in registros:
        destino = carpeta / f"{registro['source_name']}-{registro['extracted_at'][:10]}.json"
        destino.write_text(json.dumps(registro, indent=2), encoding="utf-8")
    importar_out(almacen, carpeta, None)
    assert not [t for t in ingesta.tipar_pendientes(almacen.conn) if t.accion == "error"]


def _hallazgo(conn, clave_empieza: str):
    filas = conn.execute("SELECT * FROM hallazgo WHERE clave LIKE ? ORDER BY id",
                         (f"{clave_empieza}%",)).fetchall()
    assert len(filas) == 1, [f["clave"] for f in filas]
    return filas[0]


def _de_factura(conn, regla: str, factura_id: int):
    return _hallazgo(conn, f"{regla}|factura:{factura_id}")


def _eventos(conn, hallazgo_id: int) -> list[tuple]:
    return [(e["tipo"], e["estado"]) for e in hallazgos.historia(conn, hallazgo_id)]


def _cuentas(conn) -> dict[str, int]:
    return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ("hallazgo", "hallazgo_evento", "hallazgo_objetivo", "evaluacion",
                      "anulacion", "ejecucion_reglas", "evento")}


# Las reglas de factura del paso 5: escriben solo lo que objetan (registro, paso 5).
SOLO_OBJECIONES = {"Q2", "Q3", "Q4", "A0", "A2", "A5", "A7", "A8", "E1", "E2", "F2", "F3", "F4",
                   "U1", "M2"}


# Una factura de Van Dijk con otro numero, otro total y un periodo que se pisa
# con el de la 01 (31-08 a 06-09), en la misma obra (Rijnhaven).
SOLAPADA = dict(
    invoice_number="2026-4480", invoice_date="2026-09-30", service_period_start="2026-09-03",
    service_period_end="2026-09-09", subtotal_excl_vat_raw="425,00", vat_amount_raw="89,25",
    total_incl_vat_raw="514,25",
    lines=[{"description": "Montagewerk, locatie Rijnhaven", "quantity_raw": "10,00",
            "unit": "uur", "unit_rate_raw": "42,50", "line_total_raw": "425,00",
            "location": "Rijnhaven", "week_number": 36, "period_start": None,
            "period_end": None}],
)


@pytest.fixture
def pares(almacen, tmp_path):
    """La 01 y una que se pisa con ella: un B4 abierto."""
    _cargar(almacen, tmp_path / "out", _registro("a"), _registro("b", **SOLAPADA))
    hallazgos.recalcular(almacen.conn)
    return almacen


# --- detectar ---

def test_una_pasada_detecta_cada_fallo_con_su_causa(tipado) -> None:
    conn = tipado.conn
    diferencia = hallazgos.recalcular(conn)
    usd = factura_de(conn, "NW-2026-0042")
    x1 = _de_factura(conn, "X1", usd)
    assert (x1["estado"], x1["severidad"], x1["pegajosa"], x1["anulable"]) == (
        "abierto", "bloqueo", 1, 0)
    assert x1["factura_id"] == usd and len(x1["huella"]) == 64
    assert json.loads(x1["valores_json"]) == {"moneda": "USD"}
    objetivos = {(o["tabla"], o["fila_id"], o["campo"], o["papel"]) for o in conn.execute(
        "SELECT * FROM hallazgo_objetivo WHERE hallazgo_id = ?", (x1["id"],))}
    assert ("factura", usd, "moneda_doc", "principal") in objetivos
    # La causa es el ultimo evento que toco la factura: su tipado.
    tipado_ = conn.execute("SELECT max(evento_id) FROM cambio_campo WHERE factura_id = ?",
                           (usd,)).fetchone()[0]
    [detectado] = hallazgos.historia(conn, x1["id"])
    assert (detectado["tipo"], detectado["causa_evento_id"]) == ("detectado", tipado_)
    # Paso 5: ademas de X1, el aviso de inyeccion de la 03 (Q3) y el de cada factura cuyo
    # original no esta guardado (Q4: el out/ de prueba no trae los PDF).
    assert {t.tipo for t in diferencia.transiciones} == {"detectado"}
    assert sorted(t.regla for t in diferencia.transiciones) == ["Q3", *["Q4"] * 7, "X1"]

    ejecucion = conn.execute("SELECT * FROM ejecucion_reglas").fetchone()
    assert (ejecucion["motivo"], ejecucion["hoy"]) == ("manual", "2026-10-14")
    assert ejecucion["terminada_en"] is not None and ejecucion["actor"] == usuario_sistema(
        conn, "motor")
    assert ejecucion["catalogo_sha256"] == catalogo.sha256()
    assert json.loads(ejecucion["resumen_json"])["pendientes"] == {"abierto": 9}


def test_la_cache_tiene_un_resultado_por_regla_y_fila_tambien_los_que_pasan(tipado) -> None:
    conn = tipado.conn
    diferencia = hallazgos.recalcular(conn)
    filas = conn.execute("SELECT * FROM evaluacion").fetchall()
    assert len(filas) == sum(diferencia.evaluaciones.values())
    assert {f["resultado"] for f in filas} == {"ok", "fallo", "sin_datos", "no_aplica"}
    for f in filas:
        if f["resultado"] in ("ok", "no_aplica"):
            assert f["valores_json"] is None
        if f["resultado"] == "fallo":
            assert f["valores_json"] is not None
    reglas_por_factura = {f["fila_id"]: set() for f in filas}
    for f in filas:
        reglas_por_factura[f["fila_id"]].add(f["regla"])
    # Las reglas de factura de los pasos 3 y 4 escriben todo resultado; las del paso 5 solo
    # lo que objetan (un fallo o un sin_datos), y las de entidad no van por factura.
    completas = {r.id for r in catalogo.CATALOGO if r.ambito == "factura"} - SOLO_OBJECIONES
    assert all(r >= completas for r in reglas_por_factura.values())
    assert not {f["resultado"] for f in filas if f["regla"] in SOLO_OBJECIONES} - {
        "fallo", "sin_datos"}
    fallos = {f["regla"]: f["clave"] for f in filas if f["resultado"] == "fallo"}
    assert fallos["X1"] == _hallazgo(conn, "X1")["clave"]


def test_recalcular_dos_veces_no_crea_nada_dos_veces(tipado) -> None:
    conn = tipado.conn
    hallazgos.recalcular(conn)
    antes = _cuentas(conn)
    ids = [f[0] for f in conn.execute("SELECT id FROM evaluacion ORDER BY id")]
    segunda = hallazgos.recalcular(conn)
    despues = _cuentas(conn)
    assert segunda.transiciones == [] and not segunda.retenidos
    assert {**antes, "ejecucion_reglas": antes["ejecucion_reglas"] + 1} == despues
    # La cache solo reescribe lo que cambia: nada.
    assert [f[0] for f in conn.execute("SELECT id FROM evaluacion ORDER BY id")] == ids


def test_barajar_la_entrada_da_las_mismas_huellas(pares, tmp_path) -> None:
    conn = pares.conn
    _cargar(pares, tmp_path / "out", _registro("c", total_incl_vat_raw="2.903,79"),
            _registro("d", invoice_number="2026-4471"), _registro("e", invoice_number="2026-7"))
    # Relaciones confirmadas (B2, B3 y B4 las leen) y un desglose con dos tipos, uno mal (D3).
    ana = persona(conn, "Ana", "administracion")
    a = conn.execute("SELECT min(id) FROM factura").fetchone()[0]
    b, e = factura_de(conn, "2026-4480"), factura_de(conn, "2026-7")
    campos.crear(conn, "factura_relacion", {"origen_id": e, "destino_id": b, "tipo": "corrige",
                                            "estado": "confirmada"}, Persona(ana, MOTIVO))
    campos.crear(conn, "factura_relacion", {"origen_id": e, "destino_id": a,
                                            "tipo": "relacionada", "estado": "confirmada"},
                 Persona(ana, MOTIVO))
    for tipo, base_, cuota in (("21", "2000.00", "420.00"), ("9", "399.00", "40.00")):
        campos.crear(conn, "factura_iva", {"factura_id": e, "tipo_iva_pb": Decimal(tipo),
                                           "base_cent": Decimal(base_),
                                           "cuota_cent": Decimal(cuota)},
                     Persona(ana, MOTIVO))
    hallazgos.recalcular(conn)
    guardadas = {f["clave"]: f["huella"] for f in conn.execute("SELECT clave, huella FROM hallazgo")}
    assert {c.split("|")[0] for c in guardadas} >= {"B2", "B4", "D3", "D4"}

    base = instantanea.construir(conn, hoy=date(2026, 10, 14))
    assert len(base.relaciones) == 2 and max(len(f.desglose) for f in base.facturas) == 2
    calculadas = [(d.clave, h) for d, h in hallazgos.calcular(conn, base)]
    assert dict(calculadas) == guardadas
    azar = random.Random(7)
    for _ in range(5):
        facturas = [dataclasses.replace(f, lineas=tuple(azar.sample(f.lineas, len(f.lineas))),
                                        desglose=tuple(azar.sample(f.desglose, len(f.desglose))))
                    for f in base.facturas]
        azar.shuffle(facturas)
        barajada = dataclasses.replace(base, facturas=tuple(facturas), relaciones=tuple(
            azar.sample(base.relaciones, len(base.relaciones))))
        assert [(d.clave, h) for d, h in hallazgos.calcular(conn, barajada)] == calculadas


# --- cerrar, desaparecer, reabrir ---

def test_una_correccion_que_arregla_d4_lo_cierra_con_su_causa(almacen, tmp_path) -> None:
    conn = almacen.conn
    _cargar(almacen, tmp_path / "out", _registro("a", total_incl_vat_raw="2.903,79"))
    hallazgos.recalcular(conn)
    f = factura_de(conn, "2026-4471")
    d4 = _de_factura(conn, "D4", f)
    assert d4["estado"] == "abierto" and d4["pegajosa"] == 0
    ana = persona(conn, "Ana", "administracion")
    orden = campos.fijar(conn, "factura", f, {"total_cent": Decimal("2902.79")},
                         Persona(ana, "El total es 2.902,79: el PDF lo dice"))
    diferencia = hallazgos.recalcular(conn)
    d4 = _de_factura(conn, "D4", f)
    assert d4["estado"] == "cerrado"
    ultimo = hallazgos.historia(conn, d4["id"])[-1]
    assert (ultimo["tipo"], ultimo["causa_evento_id"]) == ("cerrado_automatico", orden.evento_id)
    assert [(t.tipo, t.causa_evento_id) for t in diferencia.transiciones] == [
        ("cerrado_automatico", orden.evento_id)]


def test_un_hallazgo_pegajoso_no_se_cierra_solo(almacen, tmp_path) -> None:
    conn = almacen.conn
    _cargar(almacen, tmp_path / "out", _registro("a"),
            _registro("b", invoice_date="2026-09-16"))
    hallazgos.recalcular(conn)
    b2 = _hallazgo(conn, "B2")
    assert b2["estado"] == "abierto" and b2["pegajosa"] == 1
    a, b = sorted(f[0] for f in conn.execute("SELECT id FROM factura"))
    assert b2["fila_id"] == b      # la que llego despues duplica a la otra

    ana = persona(conn, "Ana", "administracion")
    orden = campos.fijar(conn, "factura", b, {"numero": "2026-4471-B"},
                         Persona(ana, "El numero lleva una B que no se leyo"))
    hallazgos.recalcular(conn)
    b2 = _hallazgo(conn, "B2")
    assert b2["estado"] == "desaparecido"
    assert hallazgos.historia(conn, b2["id"])[-1]["causa_evento_id"] == orden.evento_id
    # Sigue pendiente, pasada tras pasada, hasta que una persona lo cierre.
    assert hallazgos.recalcular(conn).transiciones == []
    assert _hallazgo(conn, "B2")["estado"] == "desaparecido"
    assert b2["id"] in [h["id"] for h in hallazgos.pendientes(conn, factura_id=a)]
    # Y la base tampoco deja cerrarlo solo.
    with pytest.raises(sqlite3.IntegrityError, match="pegajosa"):
        with transaccion(conn):
            conn.execute("INSERT INTO hallazgo_evento (hallazgo_id, tipo, estado, huella, "
                         "ejecucion_id, en) VALUES (?, 'cerrado_automatico', 'cerrado', ?, 1, "
                         "'2026-10-14T09:30:00+00:00')", (b2["id"], b2["huella"]))

    with pytest.raises(FaltaMotivo):
        hallazgos.resolver(conn, b2["id"], Persona(ana))
    hallazgos.resolver(conn, b2["id"], Persona(ana, "Reenvio con otro numero, confirmado"))
    b2 = _hallazgo(conn, "B2")
    assert b2["estado"] == "resuelto"
    assert _eventos(conn, b2["id"]) == [("detectado", "abierto"),
                                        ("desaparecido", "desaparecido"),
                                        ("resuelto", "resuelto")]
    resuelto = conn.execute("SELECT * FROM evento WHERE tipo = 'hallazgo_resuelto'").fetchone()
    assert (resuelto["usuario_id"], resuelto["fila_id"]) == (ana, b2["id"])

    # Si la condicion vuelve (se deshace la correccion), se reabre. El B3 que
    # aparecio mientras los numeros eran distintos (mismo importe, un dia de
    # diferencia) desaparece, y tambien se queda pendiente.
    campos.fijar(conn, "factura", b, {"numero": "2026-4471"}, Persona(ana, "Me equivoque"))
    diferencia = hallazgos.recalcular(conn)
    assert _hallazgo(conn, "B2")["estado"] == "abierto"
    assert sorted((t.regla, t.tipo) for t in diferencia.transiciones) == [
        ("B2", "reabierto"), ("B3", "desaparecido")]
    assert _hallazgo(conn, "B3")["estado"] == "desaparecido"


def test_q1_de_una_venta_v1_se_cierra_al_corregir_lo_que_faltaba(almacen) -> None:
    """La contraparte que v1 no pidio no retiene el hallazgo de la fecha que si falto."""
    from test_ingesta import _documento_por_ruta

    conn = almacen.conn
    _documento_por_ruta(almacen, "saliente", _registro("venta", invoice_date=None))
    assert [t.accion for t in ingesta.tipar_pendientes(conn)] == ["creada"]
    hallazgos.recalcular(conn)
    venta = conn.execute("SELECT id FROM factura").fetchone()[0]
    q1 = _hallazgo(conn, f"Q1|factura:{venta}")
    assert (q1["clave"], q1["estado"], q1["detalle"]) == (
        f"Q1|factura:{venta}", "abierto", "Falta fecha de factura.")
    ana = persona(conn, "Ana", "administracion")
    orden = campos.fijar(conn, "factura", venta, {"fecha_factura": date(2026, 9, 30)},
                         Persona(ana, "La fecha esta en el PDF"))
    diferencia = hallazgos.recalcular(conn)
    assert diferencia.retenidos == []
    assert [(t.clave, t.tipo, t.causa_evento_id) for t in diferencia.transiciones] == [
        (q1["clave"], "cerrado_automatico", orden.evento_id)]
    assert _hallazgo(conn, f"Q1|factura:{venta}")["estado"] == "cerrado"
    # Lo que no se pidio sigue diciendose, en su propia clave.
    assert conn.execute("SELECT resultado FROM evaluacion WHERE clave = ?",
                        (f"Q1|factura:{venta}|contraparte",)).fetchone()[0] == "sin_datos"


def test_solo_se_resuelve_a_mano_lo_que_ha_desaparecido(pares) -> None:
    conn = pares.conn
    b4 = _hallazgo(conn, "B4")
    ana = persona(conn, "Ana", "administracion")
    with pytest.raises(hallazgos.EstadoNoValido):
        hallazgos.resolver(conn, b4["id"], Persona(ana, "Ya esta, no hace falta"))
    consulta = persona(conn, "Carla", "consulta")
    with pytest.raises(PermisoDenegado):
        hallazgos.resolver(conn, b4["id"], Persona(consulta, "Ya esta, no hace falta"))


def test_un_sin_datos_no_cierra_nada(almacen, tmp_path) -> None:
    """Si el total deja de leerse, D4 no ha podido mirar: el hallazgo se queda como estaba."""
    conn = almacen.conn
    _cargar(almacen, tmp_path / "out", _registro("a", total_incl_vat_raw="2.903,79"))
    hallazgos.recalcular(conn)
    d4 = _de_factura(conn, "D4", factura_de(conn, "2026-4471"))
    ilegible = _registro("a", total_incl_vat_raw="12.34,567", model="claude-opus-5-5",
                         extracted_at="2026-10-01T08:00:00+00:00")
    _cargar(almacen, tmp_path / "out", ilegible)
    diferencia = hallazgos.recalcular(conn)
    assert d4["clave"] in diferencia.retenidos
    assert _hallazgo(conn, "D4")["estado"] == "abierto"
    assert conn.execute("SELECT resultado FROM evaluacion WHERE clave = ?",
                        (d4["clave"],)).fetchone()[0] == "sin_datos"


def test_simular_dice_lo_que_cambiaria_sin_escribir_nada(almacen, tmp_path) -> None:
    conn = almacen.conn
    _cargar(almacen, tmp_path / "out", _registro("a", total_incl_vat_raw="2.903,79"))
    hallazgos.recalcular(conn)
    f = factura_de(conn, "2026-4471")
    ana = persona(conn, "Ana", "administracion")
    campos.fijar(conn, "factura", f, {"total_cent": Decimal("2902.79")}, Persona(ana, "Lectura"))
    antes = _cuentas(conn)
    simulada = hallazgos.recalcular(conn, simular=True)
    assert simulada.simulada and [t.tipo for t in simulada.transiciones] == ["cerrado_automatico"]
    assert _cuentas(conn) == antes
    assert _de_factura(conn, "D4", f)["estado"] == "abierto"
    real = hallazgos.recalcular(conn)
    assert [(t.clave, t.tipo) for t in real.transiciones] == [
        (t.clave, t.tipo) for t in simulada.transiciones]


# Otra factura de Van Dijk en Rijnhaven, despues, con la hora a 45,00 (la 01 la cobra a 42,50).
SUBIDA = dict(
    invoice_number="2026-5000", invoice_date="2026-10-05", service_period_start="2026-09-28",
    service_period_end="2026-10-04", subtotal_excl_vat_raw="450,00", vat_amount_raw="94,50",
    total_incl_vat_raw="544,50",
    lines=[{"description": "Montagewerk, locatie Rijnhaven", "quantity_raw": "10,00",
            "unit": "uur", "unit_rate_raw": "45,00", "line_total_raw": "450,00",
            "location": "Rijnhaven", "week_number": 40, "period_start": None,
            "period_end": None}],
)


def test_resolver_los_maestros_no_abre_ni_cierra_ningun_hallazgo(almacen, tmp_path) -> None:
    """La identidad y la evidencia de un hallazgo no dependen de lo resuelto que este.

    Dar de alta el proveedor o sembrar los Objetos cambia como se llama la
    contraparte o la obra ("btw:..." pasa a "proveedor:1", "doc:rijnhaven" a
    "objeto:1"), pero no el duplicado ni la tarifa: ningun hallazgo se cierra,
    ninguno nace, y las anulaciones siguen valiendo (decision 10).
    """
    from bms_agent.importadores.tarifas import sembrar_tarifas
    from bms_agent.ingesta import reconciliar_referencias

    conn = almacen.conn
    _cargar(almacen, tmp_path / "out", _registro("a"),
            _registro("b", invoice_date="2026-09-16"), _registro("c", **SUBIDA))
    hallazgos.recalcular(conn)
    sin_resolver = instantanea.construir(conn, hoy=date(2026, 10, 14))
    assert {f.parte for f in sin_resolver.facturas} == {"btw:NL001234567B01"}
    assert all(l.objeto.startswith("doc:") for f in sin_resolver.facturas for l in f.lineas)
    antes = {f["clave"]: f["estado"] for f in conn.execute("SELECT clave, estado FROM hallazgo")}
    assert {c.split("|")[0] for c in antes} == {"B2", "B4", "G3", "Q4"}
    ana = persona(conn, "Ana", "administracion")
    for clave in antes:
        hallazgos.anular(conn, _hallazgo(conn, clave)["id"], Persona(ana, MOTIVO))

    campos.crear(conn, "proveedor", {"nombre": "Bouwtechniek Van Dijk BV",
                                     "btw_id": "NL001234567B01"},
                 Automatico("maestro", usuario_sistema(conn, "importador")))
    with transaccion(conn):
        assert reconciliar_referencias(conn) > 0
    assert sembrar_tarifas(conn, TARIFAS_V1).recalculo.transiciones == []
    assert hallazgos.recalcular(conn).transiciones == []
    instantanea_ = instantanea.construir(conn, hoy=date(2026, 10, 14))
    assert {f.parte for f in instantanea_.facturas} == {"proveedor:1"}
    assert all(l.objeto.startswith("objeto:") for f in instantanea_.facturas for l in f.lineas)
    despues = {f["clave"]: f["estado"] for f in conn.execute("SELECT clave, estado FROM hallazgo")}
    assert despues == dict.fromkeys(antes, "aceptado")


# --- anular ---

def test_una_anulacion_vale_mientras_la_huella_sea_la_anulada(pares) -> None:
    conn = pares.conn
    b4 = _hallazgo(conn, "B4")
    assert (b4["estado"], b4["anulable"], b4["pegajosa"]) == ("abierto", 1, 1)
    ana = persona(conn, "Ana", "administracion")
    anulacion = hallazgos.anular(conn, b4["id"], Persona(ana, "Son dos cuadrillas distintas"))
    fila = conn.execute("SELECT * FROM anulacion WHERE id = ?", (anulacion,)).fetchone()
    assert (fila["huella"], fila["usuario_id"], fila["autoaprobada"]) == (b4["huella"], ana, 0)
    assert _hallazgo(conn, "B4")["estado"] == "aceptado"
    assert hallazgos.recalcular(conn).transiciones == []
    assert _hallazgo(conn, "B4")["estado"] == "aceptado"

    # Otra evidencia (el periodo cambia y se sigue pisando): la anulacion deja de valer.
    b = factura_de(conn, "2026-4480")
    campos.fijar(conn, "factura", b, {"periodo_fin": date(2026, 9, 8)},
                 Persona(ana, "El periodo acaba el 8"))
    diferencia = hallazgos.recalcular(conn)
    reabierto = _hallazgo(conn, "B4")
    assert reabierto["estado"] == "abierto" and reabierto["huella"] != fila["huella"]
    assert [(t.tipo, t.nota) for t in diferencia.transiciones] == [
        ("reabierto", "la evidencia cambio")]

    # Si vuelve exactamente la evidencia anulada, la anulacion vuelve a valer.
    campos.fijar(conn, "factura", b, {"periodo_fin": date(2026, 9, 9)},
                 Persona(ana, "No, acaba el 9"))
    diferencia = hallazgos.recalcular(conn)
    assert _hallazgo(conn, "B4")["estado"] == "aceptado"
    [vuelta] = diferencia.transiciones
    assert (vuelta.tipo, vuelta.causa_evento_id) == ("aceptado", fila["evento_id"])
    assert _eventos(conn, b4["id"]) == [
        ("detectado", "abierto"), ("aceptado", "aceptado"), ("reabierto", "abierto"),
        ("aceptado", "aceptado")]
    assert hallazgos.verificar(conn) == [] and verificar_evidencia(conn) == []


def test_un_reabierto_deja_abierto_y_la_anulacion_vuelve_con_su_evento(pares) -> None:
    """Si vuelve la condicion con la evidencia anulada: reabierto y despues aceptado, de quien firmo."""
    conn = pares.conn
    b4 = _hallazgo(conn, "B4")
    ana = persona(conn, "Ana", "administracion")
    hallazgos.anular(conn, b4["id"], Persona(ana, "Son dos cuadrillas distintas"))
    b = factura_de(conn, "2026-4480")
    campos.fijar(conn, "factura", b, {"periodo_inicio": date(2026, 9, 7)},
                 Persona(ana, "Empieza el 7"))
    hallazgos.recalcular(conn)
    assert _hallazgo(conn, "B4")["estado"] == "desaparecido"
    campos.fijar(conn, "factura", b, {"periodo_inicio": date(2026, 9, 3)},
                 Persona(ana, "No, empieza el 3"))
    diferencia = hallazgos.recalcular(conn)
    assert [(t.tipo, t.estado_anterior, t.estado) for t in diferencia.transiciones] == [
        ("reabierto", "desaparecido", "abierto"), ("aceptado", "abierto", "aceptado")]
    ultimo = hallazgos.historia(conn, b4["id"])[-1]
    assert (ultimo["tipo"], ultimo["usuario_id"]) == ("aceptado", ana)
    assert hallazgos.verificar(conn) == [] and verificar_evidencia(conn) == []


def test_una_anulacion_vence(pares, reloj) -> None:
    conn = pares.conn
    b4 = _hallazgo(conn, "B4")
    ana = persona(conn, "Ana", "administracion")
    with pytest.raises(ValueError, match="vencido"):
        hallazgos.anular(conn, b4["id"], Persona(ana, MOTIVO), vigente_hasta="2026-10-13")
    hallazgos.anular(conn, b4["id"], Persona(ana, MOTIVO), vigente_hasta=date(2026, 10, 15))
    reloj.avanzar(days=1)
    assert hallazgos.recalcular(conn).transiciones == []
    reloj.avanzar(days=1)
    [vencida] = hallazgos.recalcular(conn).transiciones
    assert (vencida.tipo, vencida.nota) == ("reabierto", "la anulacion ha vencido")
    assert _hallazgo(conn, "B4")["estado"] == "abierto"


def test_acortar_el_plazo_de_una_anulacion_hace_que_venza(pares, reloj) -> None:
    """Vale la ultima anulacion: una anterior sin plazo no la sobrevive."""
    conn = pares.conn
    b4 = _hallazgo(conn, "B4")
    ana = persona(conn, "Ana", "administracion")
    hallazgos.anular(conn, b4["id"], Persona(ana, MOTIVO))
    hallazgos.anular(conn, b4["id"], Persona(ana, "Solo hasta manana, luego revisar"),
                     vigente_hasta=date(2026, 10, 15))
    reloj.avanzar(days=1)
    assert hallazgos.recalcular(conn).transiciones == []
    reloj.avanzar(days=4)
    [vencida] = hallazgos.recalcular(conn).transiciones
    assert (vencida.tipo, vencida.nota) == ("reabierto", "la anulacion ha vencido")
    assert _hallazgo(conn, "B4")["estado"] == "abierto"
    assert hallazgos.verificar(conn) == []


def test_una_anulacion_no_vuelve_si_quien_la_firmo_ya_no_puede_anular(pares, reloj) -> None:
    """El evento aceptado nuevo seria de esa persona: si ya no tiene el permiso, queda abierto."""
    from bms_agent import permisos

    conn = pares.conn
    b4 = _hallazgo(conn, "B4")
    ana = persona(conn, "Ana", "administracion")
    bea = persona(conn, "Bea", "administracion")
    hallazgos.anular(conn, b4["id"], Persona(ana, "Son dos cuadrillas distintas"))
    b = factura_de(conn, "2026-4480")
    campos.fijar(conn, "factura", b, {"periodo_fin": date(2026, 9, 8)},
                 Persona(bea, "Acaba el 8"))
    assert [t.tipo for t in hallazgos.recalcular(conn).transiciones] == ["reabierto"]
    reloj.avanzar(minutes=1)
    permisos.cerrar_rol(conn, ana, "administracion")
    reloj.avanzar(minutes=1)
    campos.fijar(conn, "factura", b, {"periodo_fin": date(2026, 9, 9)},
                 Persona(bea, "Acaba el 9"))
    assert [t.tipo for t in hallazgos.recalcular(conn).transiciones] == ["cambio_evidencia"]
    assert _hallazgo(conn, "B4")["estado"] == "abierto"
    # Ni la base lo admite: aceptar es de alguien que puede anular cuando se acepta.
    anulacion = conn.execute("SELECT * FROM anulacion").fetchone()
    with pytest.raises(sqlite3.IntegrityError, match="anulacion vigente"):
        with transaccion(conn):
            conn.execute("INSERT INTO hallazgo_evento (hallazgo_id, tipo, estado, huella, "
                         "causa_evento_id, usuario_id, en) VALUES (?, 'aceptado', 'aceptado', "
                         "?, ?, ?, '2026-10-14T09:33:00+00:00')",
                         (b4["id"], anulacion["huella"], anulacion["evento_id"], ana))


def test_anular_pide_el_permiso_y_un_motivo_de_diez_caracteres(pares) -> None:
    conn = pares.conn
    b4 = _hallazgo(conn, "B4")
    carla = persona(conn, "Carla", "consulta")
    denegados = conn.execute("SELECT count(*) FROM evento WHERE tipo = 'permiso_denegado'")
    antes = denegados.fetchone()[0]
    with pytest.raises(PermisoDenegado):
        hallazgos.anular(conn, b4["id"], Persona(carla, MOTIVO))
    assert conn.execute("SELECT count(*) FROM evento WHERE tipo = 'permiso_denegado'"
                        ).fetchone()[0] == antes + 1
    ana = persona(conn, "Ana", "administracion")
    for motivo in (None, "", "ok", "  revisado "):
        with pytest.raises(FaltaMotivo):
            hallazgos.anular(conn, b4["id"], Persona(ana, motivo))
    assert conn.execute("SELECT count(*) FROM anulacion").fetchone()[0] == 0
    hallazgos.anular(conn, b4["id"], Persona(ana, "1234567890"))


def test_lo_que_no_se_anula_no_se_anula(almacen, tmp_path) -> None:
    conn = almacen.conn
    _cargar(almacen, tmp_path / "out",
            _registro("a", iban="NL02ABNA0123456788", total_incl_vat_raw="2.903,79"))
    hallazgos.recalcular(conn)
    f = factura_de(conn, "2026-4471")
    ana = persona(conn, "Ana", "administracion")
    for regla in ("F1", "D4"):
        h = _de_factura(conn, regla, f)
        assert h["anulable"] == 0
        with pytest.raises(hallazgos.NoAnulable):
            hallazgos.anular(conn, h["id"], Persona(ana, MOTIVO))
        # Tampoco por detras, ni cambiando la marca: la lista dura esta en la base.
        conn.execute("DROP TRIGGER hallazgo_guarda_update")
        conn.execute("DROP TRIGGER hallazgo_clasificacion")
        conn.execute("UPDATE hallazgo SET anulable = 1 WHERE id = ?", (h["id"],))
        with pytest.raises(sqlite3.IntegrityError, match="no se puede anular"):
            with transaccion(conn):
                evento = registrar(conn, tipo="hallazgo_anulado", actor=ana, usuario_id=ana)
                conn.execute(
                    "INSERT INTO anulacion (hallazgo_id, huella, motivo, usuario_id, en, "
                    "evento_id) VALUES (?, ?, ?, ?, '2026-10-14T09:30:00+00:00', ?)",
                    (h["id"], h["huella"], MOTIVO, ana, evento))
        conn.execute("UPDATE hallazgo SET anulable = 0 WHERE id = ?", (h["id"],))
        from bms_agent.almacen.migrar import disponibles

        sql = next(m.sql for m in disponibles() if m.version == 3)
        for disparador in ("hallazgo_guarda_update", "hallazgo_clasificacion"):
            inicio = sql.index(f"CREATE TRIGGER {disparador}")
            conn.executescript(sql[inicio:sql.index("END;", inicio) + 4])


def test_la_base_solo_admite_anular_la_huella_actual_y_con_permiso(pares) -> None:
    conn = pares.conn
    b4 = _hallazgo(conn, "B4")
    ana = persona(conn, "Ana", "administracion")
    carla = persona(conn, "Carla", "consulta")
    for usuario, huella, error in ((ana, "0" * 64, "evidencia actual"),
                                   (carla, b4["huella"], "anular_aviso")):
        with pytest.raises(sqlite3.IntegrityError, match=error):
            with transaccion(conn):
                evento = registrar(conn, tipo="hallazgo_anulado", actor=usuario,
                                   usuario_id=usuario)
                conn.execute(
                    "INSERT INTO anulacion (hallazgo_id, huella, motivo, usuario_id, en, "
                    "evento_id) VALUES (?, ?, ?, ?, '2026-10-14T09:30:00+00:00', ?)",
                    (b4["id"], huella, MOTIVO, usuario, evento))
    # Ni aceptado sin su anulacion, ni un estado que no diga su ultimo evento.
    with pytest.raises(sqlite3.IntegrityError, match="anulacion"):
        with transaccion(conn):
            evento = registrar(conn, tipo="hallazgo_anulado", actor=ana, usuario_id=ana)
            conn.execute("INSERT INTO hallazgo_evento (hallazgo_id, tipo, estado, huella, "
                         "causa_evento_id, usuario_id, en) VALUES (?, 'aceptado', 'aceptado', "
                         "?, ?, ?, '2026-10-14T09:30:00+00:00')",
                         (b4["id"], b4["huella"], evento, ana))
    with pytest.raises(sqlite3.IntegrityError, match="ultimo evento"):
        conn.execute("UPDATE hallazgo SET estado = 'resuelto' WHERE id = ?", (b4["id"],))


def test_la_segunda_firma(almacen, tmp_path) -> None:
    """B2 pide segunda firma si hay otra persona que pueda darla; si no, queda autoaprobada."""
    conn = almacen.conn
    _cargar(almacen, tmp_path / "out", _registro("a"),
            _registro("b", invoice_date="2026-09-16"))
    hallazgos.recalcular(conn)
    b2 = _hallazgo(conn, "B2")
    ana = persona(conn, "Ana", "administracion")
    sola = hallazgos.anular(conn, b2["id"], Persona(ana, MOTIVO))
    assert conn.execute("SELECT autoaprobada FROM anulacion WHERE id = ?", (sola,)).fetchone()[0]

    bea = persona(conn, "Bea", "administracion")
    with pytest.raises(SeparacionDeFunciones, match="segunda firma"):
        hallazgos.anular(conn, b2["id"], Persona(ana, MOTIVO))
    with pytest.raises(SeparacionDeFunciones):
        hallazgos.anular(conn, b2["id"], Persona(ana, MOTIVO), segunda_firma=Persona(ana))
    carla = persona(conn, "Carla", "consulta")
    with pytest.raises(PermisoDenegado):
        hallazgos.anular(conn, b2["id"], Persona(ana, MOTIVO), segunda_firma=Persona(carla))
    firmada = hallazgos.anular(conn, b2["id"], Persona(ana, MOTIVO),
                               segunda_firma=Persona(bea, "Lo he visto con Ana", "pet-bea-1"))
    fila = conn.execute("SELECT * FROM anulacion WHERE id = ?", (firmada,)).fetchone()
    assert (fila["autoaprobada"], fila["segunda_firma_usuario_id"]) == (0, bea)
    # La segunda firma es un acto de Bea: su propio evento, justo antes del de Ana.
    firma = conn.execute("SELECT * FROM evento WHERE id = ?", (fila["evento_id"] - 1,)).fetchone()
    assert (firma["tipo"], firma["actor"], firma["usuario_id"], firma["peticion_id"],
            firma["fila_id"]) == ("hallazgo_segunda_firma", bea, bea, "pet-bea-1", b2["id"])
    assert hallazgos.verificar(conn) == [] and verificar_evidencia(conn) == []


def test_la_segunda_firma_mira_todas_las_facturas_del_hallazgo(almacen, tmp_path) -> None:
    """Un B4 cuya principal es pequena y la relacionada de 50.000 euros pide segunda firma."""
    grande = dict(subtotal_excl_vat_raw="50.000,00", vat_amount_raw="10.500,00",
                  total_incl_vat_raw="60.500,00",
                  lines=[{"description": "Montagewerk, locatie Rijnhaven",
                          "quantity_raw": "1000,00", "unit": "uur", "unit_rate_raw": "50,00",
                          "line_total_raw": "50.000,00", "location": "Rijnhaven",
                          "week_number": 36, "period_start": None, "period_end": None}])
    conn = almacen.conn
    _cargar(almacen, tmp_path / "out", _registro("a", **grande), _registro("b", **SOLAPADA))
    hallazgos.recalcular(conn)
    b4 = _hallazgo(conn, "B4")
    principal = conn.execute("SELECT base_cent FROM factura WHERE id = ?",
                             (b4["factura_id"],)).fetchone()[0]
    assert principal < hallazgos.IMPORTE_SEGUNDA_FIRMA_CENT
    assert hallazgos.requiere_segunda_firma(conn, b4)
    ana = persona(conn, "Ana", "administracion")
    bea = persona(conn, "Bea", "administracion")
    with pytest.raises(SeparacionDeFunciones, match="segunda firma"):
        hallazgos.anular(conn, b4["id"], Persona(ana, "Son dos cuadrillas distintas"))
    hallazgos.anular(conn, b4["id"], Persona(ana, "Son dos cuadrillas distintas"),
                     segunda_firma=Persona(bea))


def test_la_segunda_firma_no_es_un_id_que_escribe_la_primera(almacen, tmp_path) -> None:
    """Sin el evento de la segunda persona, la base no admite su firma."""
    conn = almacen.conn
    _cargar(almacen, tmp_path / "out", _registro("a"),
            _registro("b", invoice_date="2026-09-16"))
    hallazgos.recalcular(conn)
    b2 = _hallazgo(conn, "B2")
    ana = persona(conn, "Ana", "administracion")
    bea = persona(conn, "Bea", "administracion")
    with pytest.raises(sqlite3.IntegrityError, match="propia orden"):
        with transaccion(conn):
            evento = registrar(conn, tipo="hallazgo_anulado", actor=ana, usuario_id=ana,
                               tabla="hallazgo", fila_id=b2["id"])
            conn.execute(
                "INSERT INTO anulacion (hallazgo_id, huella, motivo, usuario_id, en, "
                "segunda_firma_usuario_id, segunda_firma_en, evento_id) VALUES "
                "(?, ?, ?, ?, '2026-10-14T09:30:00+00:00', ?, '2026-10-14T09:30:00+00:00', ?)",
                (b2["id"], b2["huella"], MOTIVO, ana, bea, evento))


# --- verificar ---

def test_verificar_ve_un_hallazgo_o_una_anulacion_tocados_por_detras(pares) -> None:
    conn = pares.conn
    b4 = _hallazgo(conn, "B4")
    ana = persona(conn, "Ana", "administracion")
    anulacion = hallazgos.anular(conn, b4["id"], Persona(ana, MOTIVO))
    assert hallazgos.verificar(conn) == [] and verificar_evidencia(conn) == []

    conn.execute("DROP TRIGGER hallazgo_guarda_update")
    conn.execute("UPDATE hallazgo SET estado = 'resuelto' WHERE id = ?", (b4["id"],))
    assert any("ultimo evento" in p for p in hallazgos.verificar(conn))

    conn.execute("DROP TRIGGER anulacion_sin_update")
    conn.execute("UPDATE anulacion SET motivo = 'otro motivo cualquiera' WHERE id = ?",
                 (anulacion,))
    assert any("anulacion" in p for p in verificar_evidencia(conn))

    conn.execute("DROP TRIGGER hallazgo_evento_de_persona")
    with transaccion(conn):
        conn.execute("INSERT INTO hallazgo_evento (hallazgo_id, tipo, estado, huella, "
                     "causa_evento_id, usuario_id, en) VALUES (?, 'aceptado', 'aceptado', ?, "
                     "1, ?, '2026-10-14T09:30:00+00:00')", (b4["id"], b4["huella"], ana))
    assert any("no hay una orden suya" in p for p in hallazgos.verificar(conn))
    assert verificar_cadena(conn).ok


def test_a_aceptado_solo_se_llega_con_una_anulacion(almacen, tmp_path) -> None:
    """Un reabierto deja el hallazgo abierto: no hay camino a aceptado sin anulacion."""
    conn = almacen.conn
    _cargar(almacen, tmp_path / "out", _registro("a", total_incl_vat_raw="2.903,79"))
    hallazgos.recalcular(conn)
    d4 = _hallazgo(conn, "D4")
    assert d4["anulable"] == 0
    ejecucion = conn.execute("SELECT max(id) FROM ejecucion_reglas").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        with transaccion(conn):
            for tipo, estado in (("cerrado_automatico", "cerrado"), ("reabierto", "aceptado")):
                conn.execute("INSERT INTO hallazgo_evento (hallazgo_id, tipo, estado, huella, "
                             "ejecucion_id, en) VALUES (?, ?, ?, ?, ?, "
                             "'2026-10-14T09:31:00+00:00')",
                             (d4["id"], tipo, estado, d4["huella"], ejecucion))
    assert _hallazgo(conn, "D4")["estado"] == "abierto"

    # Un aceptado de una persona sin su anulacion, con el disparador quitado:
    # db verificar lo ve.
    ana = persona(conn, "Ana", "administracion")
    conn.execute("DROP TRIGGER hallazgo_evento_de_persona")
    with transaccion(conn):
        orden = registrar(conn, tipo="hallazgo_anulado", actor=ana, usuario_id=ana,
                          tabla="hallazgo", fila_id=d4["id"])
        conn.execute("INSERT INTO hallazgo_evento (hallazgo_id, tipo, estado, huella, "
                     "causa_evento_id, usuario_id, en) VALUES (?, 'aceptado', 'aceptado', ?, "
                     "?, ?, '2026-10-14T09:31:00+00:00')", (d4["id"], d4["huella"], orden, ana))
        conn.execute("UPDATE hallazgo SET estado = 'aceptado' WHERE id = ?", (d4["id"],))
    problemas = hallazgos.verificar(conn)
    assert any("aceptado" in p and "no hay una anulacion" in p for p in problemas), problemas


def test_la_marca_pegajosa_y_la_severidad_no_se_tocan_por_detras(almacen, tmp_path) -> None:
    conn = almacen.conn
    _cargar(almacen, tmp_path / "out", _registro("a"),
            _registro("b", invoice_date="2026-09-16"))
    hallazgos.recalcular(conn)
    b2 = _hallazgo(conn, "B2")
    for cambio in ("pegajosa = 0", "anulable = 0", "severidad = 'aviso'"):
        with pytest.raises(sqlite3.IntegrityError, match="version de la regla"):
            conn.execute(f"UPDATE hallazgo SET {cambio} WHERE id = ?", (b2["id"],))

    # Sin el disparador: db verificar lo ve, la segunda firma se sigue pidiendo
    # y el motor no deja que el duplicado se cierre solo.
    conn.execute("DROP TRIGGER hallazgo_clasificacion")
    conn.execute("UPDATE hallazgo SET pegajosa = 0, severidad = 'aviso' WHERE id = ?",
                 (b2["id"],))
    problemas = hallazgos.verificar(conn)
    assert any("pegajosa" in p for p in problemas), problemas
    conn.execute("UPDATE hallazgo SET pegajosa = 1 WHERE id = ?", (b2["id"],))
    problemas = hallazgos.verificar(conn)
    assert any("mas leve" in p for p in problemas), problemas
    assert any("la que da el motor" in p for p in problemas), problemas
    assert hallazgos.requiere_segunda_firma(conn, _hallazgo(conn, "B2"))
    conn.execute("UPDATE hallazgo SET pegajosa = 0, severidad = 'bloqueo' WHERE id = ?",
                 (b2["id"],))
    ana = persona(conn, "Ana", "administracion")
    b = max(f[0] for f in conn.execute("SELECT id FROM factura"))
    campos.fijar(conn, "factura", b, {"numero": "2026-9999"}, Persona(ana, "Otro numero"))
    [b2_] = [t for t in hallazgos.recalcular(conn).transiciones if t.regla == "B2"]
    assert (b2_.tipo, b2_.estado) == ("desaparecido", "desaparecido")


# --- las ordenes recalculan al terminar ---

def _ejecuciones(db) -> list[str]:
    with preparar(db) as almacen:
        return [f[0] for f in almacen.conn.execute(
            "SELECT motivo FROM ejecucion_reglas ORDER BY id")]


def test_cada_orden_de_entrada_termina_recalculando(tmp_path, out_v1, capsys) -> None:
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(tmp_path / "no"),
                 "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    assert "Reglas: " in salida and "Hallazgos: 9 nuevos" in salida      # X1, Q3 y 7 Q4
    assert main(["ingestar", "--db", str(db)]) == 0
    assert main(["sembrar", "--tarifas", str(TARIFAS_V1), "--db", str(db)]) == 0
    assert _ejecuciones(db) == ["importacion", "ingesta", "importacion"]
    with preparar(db) as almacen:
        x1 = _hallazgo(almacen.conn, "X1")
        assert x1["estado"] == "abierto" and len(hallazgos.historia(almacen.conn, x1["id"])) == 1
    assert main(["db", "verificar", "--db", str(db)]) == 0


def test_recalcular_por_la_cli(tmp_path, out_v1, capsys) -> None:
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["recalcular", "--db", str(db)]) == 1          # sin almacen
    assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(tmp_path / "no"),
                 "--db", str(db)]) == 0
    capsys.readouterr()
    assert main(["recalcular", "--simular", "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    assert "Simulacion: no se ha escrito nada" in salida and "9 abiertos" in salida
    assert _ejecuciones(db) == ["importacion"]
    assert main(["recalcular", "--diaria", "--db", str(db)]) == 0
    assert "Hallazgos: ninguno cambia" in capsys.readouterr().out
    assert _ejecuciones(db) == ["importacion", "diaria"]
    assert main(["recalcular", "--db", str(db)]) == 0
    assert _ejecuciones(db)[-1] == "manual"
    assert main(["db", "verificar", "--db", str(db)]) == 0


def test_importar_out_que_falla_al_recalcular_no_deja_nada(tmp_path, out_v1, monkeypatch) -> None:
    from bms_agent.cli import main

    def fallar(*_a, **_k):
        raise RuntimeError("el motor se cayo")

    monkeypatch.setattr(hallazgos, "recalcular", fallar)
    db = tmp_path / "datos" / "bms.sqlite3"
    with pytest.raises(RuntimeError):
        main(["importar-out", "--out", str(out_v1), "--pdfs", str(tmp_path / "no"),
              "--db", str(db)])
    with preparar(db) as almacen:
        assert almacen.conn.execute("SELECT count(*) FROM factura").fetchone()[0] == 0


def test_extract_y_el_servidor_recalculan_al_terminar(tmp_path, monkeypatch) -> None:
    import anthropic
    from test_extraccion_pasada import PDF, ClienteFalso

    from bms_agent.almacen import ruta_por_defecto
    from bms_agent.cli import main
    from bms_agent.serve import Agente

    pdfs = tmp_path / "facturas"
    pdfs.mkdir()
    (pdfs / "a.pdf").write_bytes(PDF)
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: ClienteFalso())
    assert main(["extract", str(pdfs), "--out", str(tmp_path / "out")]) == 0
    assert _ejecuciones(ruta_por_defecto()) == ["ingesta"]

    db = tmp_path / "otra" / "bms.sqlite3"
    agente = Agente(pdfs, tmp_path / "out2", db)
    monkeypatch.setattr(agente, "_cliente", lambda: ClienteFalso())
    agente._ejecutar()
    assert _ejecuciones(db) == ["ingesta"]


def test_el_motor_no_llama_a_la_api(tmp_path, out_v1) -> None:
    """En un proceso donde `import anthropic` lanza: importar, recalcular y verificar."""
    from test_migracion_out import _sin_api

    db = tmp_path / "datos" / "bms.sqlite3"
    for argumentos in (
        ("importar-out", "--out", str(out_v1), "--pdfs", str(tmp_path / "no"), "--db", str(db)),
        ("recalcular", "--simular", "--db", str(db)),
        ("recalcular", "--db", str(db)),
        ("db", "verificar", "--db", str(db)),
    ):
        proceso = _sin_api(*argumentos)
        assert proceso.returncode == 0, (argumentos, proceso.stdout, proceso.stderr)


def test_el_dominio_de_los_hallazgos_es_el_de_la_base(db) -> None:
    import re

    from bms_agent import dominio

    def check(tabla: str, columna: str) -> set[str]:
        sql = db.execute("SELECT sql FROM sqlite_master WHERE name = ?", (tabla,)).fetchone()[0]
        en_lista = re.search(rf"\b{columna}\b[^\n]*?IN \(([^)]*)\)", sql, re.S)
        if en_lista is None:
            # Una cadena de OR (evaluacion.resultado: un IN es lento en cada fila).
            definicion = re.search(rf"^\s*{columna}\b.*?\),$", sql, re.S | re.M).group(0)
            return set(re.findall(rf"{columna} = '([^']*)'", definicion))
        lista = en_lista.group(1)
        return {v.strip().strip("'") for v in lista.replace("\n", " ").split(",")}

    assert set(dominio.EstadoHallazgo.valores()) == check("hallazgo", "estado")
    assert set(dominio.EstadoHallazgo.valores()) == check("hallazgo_evento", "estado")
    assert set(dominio.TipoEventoHallazgo.valores()) == check("hallazgo_evento", "tipo")
    assert set(dominio.MotivoEjecucion.valores()) == check("ejecucion_reglas", "motivo")
    assert set(dominio.PapelObjetivo.valores()) == check("hallazgo_objetivo", "papel")
    assert set(dominio.AmbitoHallazgo.valores()) == check("hallazgo", "ambito")
    assert set(dominio.Severidad.valores()) == check("hallazgo", "severidad")
    assert set(dominio.ResultadoRegla.valores()) == check("evaluacion", "resultado")
    assert set(dominio.Calidad.valores()) == check("hallazgo", "calidad")
    assert dominio.ESTADOS_PENDIENTES == {"abierto", "aceptado", "desaparecido"}
