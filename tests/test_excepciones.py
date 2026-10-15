"""Las excepciones: una por entidad, con su estado, su responsable y su resolucion.

Cada caso carga extracciones v1 escritas a mano (las de test_hallazgos.py),
deja que la pasada del motor abra las excepciones, y hace lo que haria una
persona con excepciones.py. Lo que la base exige por su cuenta (migracion
0004) se prueba saltandose el codigo.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest
from conftest import RAIZ, factura_de, persona
from test_hallazgos import SOLAPADA, _cargar, _hallazgo, _registro

from bms_agent import campos, excepciones, hallazgos
from bms_agent.almacen import transaccion, usuario_sistema
from bms_agent.auditoria import Cambio, registrar
from bms_agent.campos import Conflicto, FaltaMotivo, Persona
from bms_agent.excepciones import BloqueoAbierto, EstadoNoValido
from bms_agent.permisos import PermisoDenegado

HOY = date(2026, 10, 14)

# La 01 con una linea cobrada de mas (10 x 42,50 = 425, cobra 430) y los
# totales cuadrados con ella: D2b, que bloquea una compra y se puede anular.
D2B = dict(
    invoice_number="2026-5000", subtotal_excl_vat_raw="430,00", vat_amount_raw="90,30",
    total_incl_vat_raw="520,30",
    lines=[{"description": "Montagewerk, locatie Rijnhaven", "quantity_raw": "10,00",
            "unit": "uur", "unit_rate_raw": "42,50", "line_total_raw": "430,00",
            "location": "Rijnhaven", "week_number": 36, "period_start": None,
            "period_end": None}],
)


@pytest.fixture
def pares(almacen, tmp_path):
    """La 01 y otra que se pisa con ella: un B4, que retiene las dos."""
    _cargar(almacen, tmp_path / "out", _registro("a"), _registro("b", **SOLAPADA))
    hallazgos.recalcular(almacen.conn)
    return almacen


@pytest.fixture
def d2b(almacen, tmp_path):
    _cargar(almacen, tmp_path / "out", _registro("c", **D2B))
    hallazgos.recalcular(almacen.conn)
    return almacen


def _excepciones(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM excepcion ORDER BY id").fetchall()


def _alta_por_detras(conn, persona_id: int, factura_id: int, estado: str, **extra) -> None:
    """Una excepcion metida sin excepciones.py, con su auditoria completa (la guarda pasa)."""
    fila_id = excepciones._siguiente_id(conn)
    valores = {"titulo": "x", "tabla": "factura", "fila_id": factura_id,
               "factura_id": factura_id, "estado": estado,
               "creada_en": "2026-10-14T09:30:00+00:00", "creada_por": persona_id, **extra}
    with transaccion(conn):
        registrar(conn, tipo="prueba", actor=persona_id, usuario_id=persona_id,
                  cambios=excepciones._cambios_alta(fila_id, valores, "manual_entrada"))
        excepciones._insertar(conn, fila_id, valores)


def _unidos(conn, excepcion_id: int) -> list[str]:
    return [h["regla"] for h in excepciones.hallazgos_de(conn, excepcion_id)]


# ------------------------------------------------------------ las abre el motor

def test_una_por_entidad_con_sus_hallazgos(pares) -> None:
    conn = pares.conn
    a, b = factura_de(conn, "2026-4471"), factura_de(conn, "2026-4480")
    filas = _excepciones(conn)
    # El B4 cubre las dos facturas: ninguna se paga sin mirarlo.
    assert {(e["tabla"], e["fila_id"], e["estado"]) for e in filas} == {
        ("factura", a, "abierta"), ("factura", b, "abierta")}
    for e in filas:
        assert _unidos(conn, e["id"]) == ["B4"]
        assert e["creada_por"] == usuario_sistema(conn, "motor")
        assert e["titulo"] == "B4 Periodo facturado dos veces"
    evento = conn.execute("SELECT * FROM evento WHERE tipo = 'excepciones_sincronizadas'"
                          ).fetchone()
    assert evento["actor"] == usuario_sistema(conn, "motor")


def test_una_pasada_sin_cambios_no_abre_ni_escribe_nada(pares) -> None:
    conn = pares.conn
    eventos = conn.execute("SELECT count(*) FROM evento").fetchone()[0]
    diferencia = hallazgos.recalcular(conn)
    assert diferencia.excepciones.creadas == [] and diferencia.excepciones.vinculos == []
    assert conn.execute("SELECT count(*) FROM evento").fetchone()[0] == eventos
    assert len(_excepciones(conn)) == 2


def test_un_hallazgo_nuevo_se_une_a_la_que_esta_abierta(pares) -> None:
    conn = pares.conn
    a = factura_de(conn, "2026-4471")
    ana = persona(conn, "Ana", "administracion")
    campos.fijar(conn, "factura", a, {"total_cent": 1}, Persona(ana, "Para ver el D4"))
    diferencia = hallazgos.recalcular(conn)
    abierta = excepciones.abierta_de(conn, "factura", a)
    assert diferencia.excepciones.creadas == []
    assert sorted(_unidos(conn, abierta["id"])) == ["B4", "D4"]


def test_un_aviso_solo_abre_una_si_su_regla_lo_pide(monkeypatch) -> None:
    from bms_agent.reglas import catalogo

    assert excepciones.merece_excepcion("D4", "bloqueo", "abierto")
    assert excepciones.merece_excepcion("B4", "retencion", "desaparecido")
    assert not excepciones.merece_excepcion("D4", "bloqueo", "aceptado")
    assert not excepciones.merece_excepcion("G3", "aviso", "abierto")
    con_excepcion = catalogo.POR_ID["G3"].__class__(
        **{**catalogo.POR_ID["G3"].__dict__, "crea_excepcion": True})
    monkeypatch.setitem(catalogo.POR_ID, "G3", con_excepcion)
    assert excepciones.merece_excepcion("G3", "aviso", "abierto")


def test_una_entidad_sin_hallazgos_que_la_pidan_no_tiene_excepcion(tipado) -> None:
    conn = tipado.conn
    hallazgos.recalcular(conn)
    usd = factura_de(conn, "NW-2026-0042")
    inyeccion = factura_de(conn, "2026-0912")
    # Paso 5: el aviso de inyeccion de la 03 abre la suya (Q3 crea excepcion); los Q4 de
    # cada factura sin su original guardado son avisos que no la piden.
    assert sorted((e["fila_id"], _unidos(conn, e["id"])) for e in _excepciones(conn)) == sorted(
        [(inyeccion, ["Q3"]), (usd, ["X1"])])


# ------------------------------------------------------------ el estado lo pone una persona

def test_asignar_esperar_y_resolver(pares, reloj) -> None:
    conn = pares.conn
    a = factura_de(conn, "2026-4471")
    ana = persona(conn, "Ana", "administracion")
    bea = persona(conn, "Bea", "administracion")
    e = excepciones.abierta_de(conn, "factura", a)

    excepciones.asignar(conn, Persona(ana), e["id"], responsable_id=bea, rev=0)
    e = excepciones.abierta_de(conn, "factura", a)
    assert (e["estado"], e["responsable_id"], e["rev"]) == ("asignada", bea, 1)

    # Sin fecha: hoy + 14, o el vencimiento si llega antes (el de la 01 es el 15-10).
    excepciones.esperar(conn, Persona(bea, "Pedido el abono"), e["id"],
                        esperando_a="proveedor", rev=1)
    e = excepciones.abierta_de(conn, "factura", a)
    assert (e["estado"], e["esperando_a"], e["fecha_seguimiento"]) == (
        "esperando_externo", "proveedor", "2026-10-15")
    assert e["responsable_id"] == bea
    with pytest.raises(ValueError, match="ya ha pasado"):
        excepciones.esperar(conn, Persona(bea), e["id"], esperando_a="proveedor",
                            fecha_seguimiento="2026-10-13", rev=2)

    with pytest.raises(FaltaMotivo):
        excepciones.resolver(conn, Persona(bea), e["id"], resolucion="corregido", notas=" ",
                             rev=2)
    excepciones.resolver(conn, Persona(bea), e["id"], resolucion="aceptado",
                         notas="El proveedor confirma dos semanas distintas", rev=2)
    resuelta = conn.execute("SELECT * FROM excepcion WHERE id = ?", (e["id"],)).fetchone()
    assert (resuelta["estado"], resuelta["resolucion"], resuelta["resuelta_por"]) == (
        "resuelta", "aceptado", bea)
    assert resuelta["hallazgo_evento_hasta"] == conn.execute(
        "SELECT max(id) FROM hallazgo_evento").fetchone()[0]
    # Una resuelta ya no cambia.
    with pytest.raises(EstadoNoValido):
        excepciones.asignar(conn, Persona(ana), e["id"], responsable_id=ana)
    assert excepciones.verificar(conn) == []


def test_el_seguimiento_por_defecto_es_como_mucho_hoy_mas_catorce() -> None:
    assert excepciones.seguimiento_por_defecto(HOY, None) == HOY + timedelta(days=14)
    assert excepciones.seguimiento_por_defecto(HOY, HOY + timedelta(days=30)) == HOY + timedelta(
        days=14)
    assert excepciones.seguimiento_por_defecto(HOY, HOY + timedelta(days=3)) == HOY + timedelta(
        days=3)
    # Una factura ya vencida no adelanta el seguimiento al pasado.
    assert excepciones.seguimiento_por_defecto(HOY, HOY - timedelta(days=3)) == HOY + timedelta(
        days=14)


def test_no_se_resuelve_con_un_bloqueo_abierto_sin_anular(d2b) -> None:
    conn = d2b.conn
    c = factura_de(conn, "2026-5000")
    ana = persona(conn, "Ana", "administracion")
    e = excepciones.abierta_de(conn, "factura", c)
    assert _unidos(conn, e["id"]) == ["D2b"]
    with pytest.raises(BloqueoAbierto, match="D2b"):
        excepciones.resolver(conn, Persona(ana), e["id"], resolucion="aceptado",
                             notas="La tarifa pactada es otra")
    # La base tampoco lo deja, aunque alguien se salte el codigo.
    with pytest.raises(sqlite3.IntegrityError, match="bloquea abierto"):
        with transaccion(conn):
            excepciones._cambiar(conn, Persona(ana), e, {
                "estado": "resuelta", "resolucion": "aceptado", "resolucion_notas": "a mano",
                "resuelta_en": "2026-10-14T09:30:00+00:00", "resuelta_por": ana,
                "hallazgo_evento_hasta": 0}, tipo="excepcion_resuelta", motivo="a mano")
    # Anulado el bloqueo, si.
    d2b_ = _hallazgo(conn, "D2b")
    hallazgos.anular(conn, d2b_["id"], Persona(ana, "La tarifa de 43 euros esta pactada"))
    hallazgos.recalcular(conn)
    excepciones.resolver(conn, Persona(ana), e["id"], resolucion="anulado",
                         notas="Anulado el D2b: la tarifa esta pactada")
    assert conn.execute("SELECT estado FROM excepcion WHERE id = ?", (e["id"],)).fetchone()[0] == (
        "resuelta")


def test_resolver_no_cierra_los_hallazgos_y_no_vuelve_a_abrirse_sola(pares) -> None:
    conn = pares.conn
    a = factura_de(conn, "2026-4471")
    ana = persona(conn, "Ana", "administracion")
    e = excepciones.abierta_de(conn, "factura", a)
    excepciones.resolver(conn, Persona(ana), e["id"], resolucion="no_procede",
                         notas="Son dos obras distintas en la misma semana")
    assert _hallazgo(conn, "B4")["estado"] == "abierto"
    diferencia = hallazgos.recalcular(conn)
    assert diferencia.excepciones.creadas == []
    assert excepciones.abierta_de(conn, "factura", a) is None


def test_si_el_problema_vuelve_con_otra_evidencia_se_abre_otra(pares) -> None:
    conn = pares.conn
    a, b = factura_de(conn, "2026-4471"), factura_de(conn, "2026-4480")
    ana = persona(conn, "Ana", "administracion")
    vieja = excepciones.abierta_de(conn, "factura", a)
    excepciones.resolver(conn, Persona(ana), vieja["id"], resolucion="no_procede",
                         notas="Son dos obras distintas en la misma semana")
    # Cambia el periodo de la otra: el B4 cambia de evidencia.
    campos.fijar(conn, "factura", b, {"periodo_fin": date(2026, 9, 10)},
                 Persona(ana, "El periodo acaba el 10"))
    diferencia = hallazgos.recalcular(conn)
    nueva = excepciones.abierta_de(conn, "factura", a)
    assert nueva is not None and nueva["id"] != vieja["id"]
    assert nueva["id"] in diferencia.excepciones.creadas
    assert _unidos(conn, nueva["id"]) == ["B4"]
    # La resuelta sigue como estaba.
    assert conn.execute("SELECT estado FROM excepcion WHERE id = ?",
                        (vieja["id"],)).fetchone()[0] == "resuelta"


def test_una_persona_abre_una_a_mano_y_no_hay_dos(tipado) -> None:
    conn = tipado.conn
    hallazgos.recalcular(conn)
    ana = persona(conn, "Ana", "administracion")
    limpia = factura_de(conn, "2026-4471")
    nueva = excepciones.crear(conn, Persona(ana, "El cliente discute las horas"),
                              tabla="factura", fila_id=limpia, titulo="Horas en disputa")
    e = conn.execute("SELECT * FROM excepcion WHERE id = ?", (nueva,)).fetchone()
    assert (e["creada_por"], e["descripcion"], e["estado"]) == (
        ana, "El cliente discute las horas", "abierta")
    with pytest.raises(EstadoNoValido, match="ya tiene"):
        excepciones.crear(conn, Persona(ana), tabla="factura", fila_id=limpia, titulo="Otra")
    # Ni saltandose el codigo: la base no admite dos abiertas de la misma entidad.
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        _alta_por_detras(conn, ana, limpia, "abierta")


def test_quien_no_tiene_resolver_aviso_ni_un_usuario_de_sistema_tocan_una(pares) -> None:
    conn = pares.conn
    a = factura_de(conn, "2026-4471")
    carla = persona(conn, "Carla", "consulta")
    e = excepciones.abierta_de(conn, "factura", a)
    for quien in (carla, usuario_sistema(conn, "motor"), usuario_sistema(conn, "sistema")):
        with pytest.raises(PermisoDenegado):
            excepciones.asignar(conn, Persona(quien), e["id"], responsable_id=carla)
    denegados = conn.execute("SELECT count(*) FROM evento WHERE tipo = 'permiso_denegado'"
                             ).fetchone()[0]
    assert denegados == 3
    # El responsable es una persona activa, no un usuario de sistema.
    ana = persona(conn, "Ana", "administracion")
    with pytest.raises(ValueError, match="persona activa"):
        excepciones.asignar(conn, Persona(ana), e["id"], responsable_id=usuario_sistema(
            conn, "motor"))


def test_la_base_solo_deja_el_estado_a_una_persona_con_resolver_aviso(pares) -> None:
    conn = pares.conn
    a = factura_de(conn, "2026-4471")
    e = excepciones.abierta_de(conn, "factura", a)
    motor = usuario_sistema(conn, "motor")
    carla = persona(conn, "Carla", "consulta")
    for actor, usuario in ((motor, None), (carla, carla)):
        with pytest.raises(sqlite3.IntegrityError, match="resolver_aviso"):
            with transaccion(conn):
                registrar(conn, tipo="excepcion_asignada", actor=actor, usuario_id=usuario,
                          cambios=[Cambio("excepcion", e["id"], "estado", 1, "abierta",
                                          "asignada", "manual_entrada"),
                                   Cambio("excepcion", e["id"], "responsable_id", 1, None,
                                          carla, "manual_entrada")])
                conn.execute("UPDATE excepcion SET estado = 'asignada', responsable_id = ?, "
                             "rev = 1 WHERE id = ?", (carla, e["id"]))


def test_la_guarda_y_los_check_de_la_tabla(pares) -> None:
    conn = pares.conn
    a = factura_de(conn, "2026-4471")
    e = excepciones.abierta_de(conn, "factura", a)
    ana = persona(conn, "Ana", "administracion")
    # Un UPDATE sin su cambio_campo lo rechaza la guarda.
    with pytest.raises(sqlite3.IntegrityError, match="controlada"):
        conn.execute("UPDATE excepcion SET titulo = 'otro', rev = rev + 1 WHERE id = ?",
                     (e["id"],))
    with pytest.raises(sqlite3.IntegrityError, match="no se borra"):
        conn.execute("DELETE FROM excepcion")
    # asignada sin responsable, esperando sin fecha: los CHECK.
    for nuevos in ({"estado": "asignada"}, {"estado": "esperando_externo",
                                             "esperando_a": "proveedor"}):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            with transaccion(conn):
                excepciones._cambiar(conn, Persona(ana), e, nuevos, tipo="prueba", motivo=None)
    with pytest.raises(sqlite3.IntegrityError, match="nace abierta"):
        _alta_por_detras(conn, ana, factura_de(conn, "2026-4480"), "asignada", responsable_id=ana)
    # Una union con un hallazgo solo se anade.
    with pytest.raises(sqlite3.IntegrityError, match="solo escritura"):
        conn.execute("DELETE FROM excepcion_hallazgo")


def test_las_guardas_de_la_excepcion_son_las_del_script(db) -> None:
    import importlib.util

    from bms_agent.almacen.migrar import disponibles

    spec = importlib.util.spec_from_file_location("guardas", RAIZ / "scripts" / "generar_guardas.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    sql = next(m.sql for m in disponibles() if m.version == 4)
    assert modulo.guardas("excepcion", modulo.columnas(db, "excepcion")) in sql
    columnas = [c["name"] for c in db.execute("PRAGMA table_info(excepcion)")
                if c["name"] not in ("id", "rev")]
    assert tuple(columnas) == excepciones.COLUMNAS


def test_verificar_ve_una_excepcion_o_una_union_tocadas_por_detras(pares) -> None:
    conn = pares.conn
    a = factura_de(conn, "2026-4471")
    e = excepciones.abierta_de(conn, "factura", a)
    assert excepciones.verificar(conn) == []
    for disparador in ("excepcion_guarda_update", "excepcion_identidad", "excepcion_de_persona",
                       "excepcion_resolver", "excepcion_hallazgo_sin_update"):
        conn.execute(f"DROP TRIGGER {disparador}")
    conn.execute("UPDATE excepcion SET estado = 'resuelta', resolucion = 'aceptado', "
                 "resolucion_notas = 'x', resuelta_en = '2026-10-14T09:30:00+00:00', "
                 "resuelta_por = 1, hallazgo_evento_hasta = 0 WHERE id = ?", (e["id"],))
    # Una union que dice venir de otro evento (uno que no la registro).
    conn.execute("UPDATE excepcion_hallazgo SET evento_id = 1 WHERE excepcion_id = ?",
                 (e["id"],))
    problemas = excepciones.verificar(conn)
    assert any("estado no es lo que dejo" in p for p in problemas)
    assert any("no la registro su evento" in p for p in problemas)


def test_rev_vieja_es_un_conflicto(pares) -> None:
    conn = pares.conn
    a = factura_de(conn, "2026-4471")
    ana = persona(conn, "Ana", "administracion")
    e = excepciones.abierta_de(conn, "factura", a)
    excepciones.asignar(conn, Persona(ana), e["id"], responsable_id=ana, rev=0)
    with pytest.raises(Conflicto):
        excepciones.asignar(conn, Persona(ana), e["id"], responsable_id=ana, rev=0)


def test_no_se_resuelve_con_un_bloqueo_desaparecido_sin_cerrar(almacen, tmp_path) -> None:
    """Un pegajoso cuya condicion desaparecio sigue abierto hasta que una persona lo cierra
    (§7): la excepcion que lo agrupa no se resuelve antes."""
    from bms_agent import permisos, servicios
    from bms_agent.ingesta import reconciliar_referencias

    conn = almacen.conn
    _cargar(almacen, tmp_path / "out", _registro("a"), _registro("b", invoice_date="2026-09-16"))
    ana = persona(conn, "Ana", "administrador")
    campos.crear(conn, "proveedor", {"nombre": "Bouwtechniek Van Dijk BV",
                                     "btw_id": "NL001234567B01"}, Persona(ana))
    reconciliar_referencias(conn)
    hallazgos.recalcular(conn)
    a, b = sorted(f[0] for f in conn.execute("SELECT id FROM factura"))
    # Quien fusiona no puede cerrar hallazgos: el B2 queda desaparecido.
    permisos.crear_rol(conn, "fusionar", ["ver_facturas", "anular_acreditar"])
    pedro = persona(conn, "Pedro")
    permisos.asignar_rol(conn, pedro, "fusionar")
    rev = conn.execute("SELECT rev FROM factura WHERE id = ?", (b,)).fetchone()[0]
    servicios.ejecutar(conn, "fusionar_factura", {
        "factura_id": b, "destino_id": a, "rev": rev, "motivo": "Es el mismo PDF reenviado"},
        usuario_id=pedro)
    b2 = _hallazgo(conn, "B2")
    assert b2["estado"] == "desaparecido"
    e = excepciones.abierta_de(conn, "factura", a)
    assert "B2" in _unidos(conn, e["id"])
    with pytest.raises(BloqueoAbierto, match="B2"):
        excepciones.resolver(conn, Persona(ana), e["id"], resolucion="corregido",
                             notas="Fusionado el reenvio")
    # La base tampoco.
    with pytest.raises(sqlite3.IntegrityError, match="desaparecido"):
        with transaccion(conn):
            excepciones._cambiar(conn, Persona(ana), e, {
                "estado": "resuelta", "resolucion": "corregido", "resolucion_notas": "a mano",
                "resuelta_en": "2026-10-14T09:30:00+00:00", "resuelta_por": ana,
                "hallazgo_evento_hasta": 0}, tipo="excepcion_resuelta", motivo="a mano")
    # Cerrado el B2 por una persona, si.
    hallazgos.resolver(conn, b2["id"], Persona(ana, "Visto: era el mismo PDF"))
    excepciones.resolver(conn, Persona(ana), e["id"], resolucion="corregido",
                         notas="Fusionado el reenvio")
    assert conn.execute("SELECT estado FROM excepcion WHERE id = ?",
                        (e["id"],)).fetchone()[0] == "resuelta"
