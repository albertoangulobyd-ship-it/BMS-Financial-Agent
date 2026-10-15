"""La revision de una factura: la huella de lo que se vio, y que cualquier cambio la anula.

Puerta del paso 4: cualquier cambio posterior invalida una revision. Se prueba
con cada clase de cambio: una correccion, una linea excluida, otra
imputacion, un hallazgo nuevo que llega por otra factura, una anulacion, una
verificacion y una extraccion nueva que contradice lo corregido. Una nota no
cambia lo revisado.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest
from conftest import factura_de, persona
from test_hallazgos import SOLAPADA, _cargar, _hallazgo, _registro

from bms_agent import campos, consola_assets, dominio, hallazgos, revision, servicios
from bms_agent.almacen import transaccion, usuario_sistema
from bms_agent.almacen.evidencia import verificar_evidencia
from bms_agent.auditoria import registrar
from bms_agent.campos import Conflicto, Persona
from bms_agent.permisos import PermisoDenegado, SeparacionDeFunciones

MOTIVO = "Comprobado con el proveedor por telefono"


@pytest.fixture
def una(almacen, tmp_path):
    """La 01 sola, limpia, con la pasada hecha."""
    _cargar(almacen, tmp_path / "out", _registro("a"))
    hallazgos.recalcular(almacen.conn)
    return almacen


def _estado(conn, factura_id: int) -> str:
    return conn.execute("SELECT estado_revision FROM factura_estado WHERE factura_id = ?",
                        (factura_id,)).fetchone()[0]


def _revisar(conn, quien: int, factura_id: int, nota: str | None = None):
    return servicios.ejecutar(conn, "marcar_revisada", {
        "factura_id": factura_id, "huella": revision.huella_contenido(conn, factura_id),
        "motivo": nota}, usuario_id=quien)


def _rev(conn, tabla: str, fila_id: int) -> int:
    return conn.execute(f"SELECT rev FROM {tabla} WHERE id = ?", (fila_id,)).fetchone()[0]


def test_una_factura_limpia_se_revisa_y_es_sin_objeciones_nunca_aprobada(una) -> None:
    conn = una.conn
    f = factura_de(conn, "2026-4471")
    ana = persona(conn, "Ana", "administracion")
    assert _estado(conn, f) == "sin_revisar"
    assert revision.etiqueta_sistema(0, 0, 0) == "Sin objeciones del sistema"
    dif = _revisar(conn, ana, f, "Mirada contra el planning")
    assert _estado(conn, f) == "revisada"
    assert dif.detalle["autorrevisada"] is False
    fila = conn.execute("SELECT * FROM revision").fetchone()
    assert (fila["resultado"], fila["usuario_id"], fila["nota"]) == (
        "revisada", ana, "Mirada contra el planning")
    # Ninguna etiqueta ni ningun estado dice "aprobada".
    for texto in (revision.etiqueta_sistema(0, 0, 0), revision.etiqueta_sistema(0, 0, 3),
                  revision.etiqueta_sistema(2, 1, 0), consola_assets.PAGINA):
        assert "aprobad" not in texto.lower().replace("no aprueba", "")
    for enum in (dominio.EstadoRevision, dominio.ResultadoRevision, dominio.EstadoExcepcion,
                 dominio.ResolucionExcepcion, dominio.EstadoPago):
        assert not any("aprob" in v for v in enum.valores())


def _cambios_posteriores():
    """Cada cambio despues de revisar, como una funcion (conn, almacen, tmp, ana, bea, f)."""
    def corregir(conn, _a, _t, ana, _b, f):
        servicios.ejecutar(conn, "fijar_campo", {
            "tabla": "factura", "fila_id": f, "campo": "fecha_vencimiento",
            "valor": "2026-10-20", "rev": _rev(conn, "factura", f), "motivo": MOTIVO},
            usuario_id=ana)

    def excluir(conn, _a, _t, ana, _b, f):
        linea = conn.execute("SELECT id FROM factura_linea WHERE factura_id = ? ORDER BY id "
                             "DESC", (f,)).fetchone()[0]
        servicios.ejecutar(conn, "excluir_linea", {
            "linea_id": linea, "rev": _rev(conn, "factura_linea", linea), "motivo": MOTIVO},
            usuario_id=ana)

    def imputar(conn, _a, _t, ana, _b, f):
        from bms_agent.importadores.tarifas import sembrar_tarifas
        from conftest import TARIFAS_V1

        sembrar_tarifas(conn, TARIFAS_V1)
        imputacion = conn.execute("SELECT id FROM factura_imputacion WHERE factura_id = ? "
                                  "ORDER BY id", (f,)).fetchone()[0]
        otro = conn.execute("SELECT id FROM objeto ORDER BY id DESC").fetchone()[0]
        servicios.ejecutar(conn, "cambiar_objeto", {
            "imputacion_id": imputacion, "objeto_id": otro,
            "rev": _rev(conn, "factura_imputacion", imputacion), "motivo": MOTIVO},
            usuario_id=ana)

    def otra_factura(conn, almacen, tmp, _a, _b, _f):
        # Llega otra factura que se pisa con la revisada: un B4 que tambien es suyo.
        _cargar(almacen, tmp / "out2", _registro("b", **SOLAPADA))
        hallazgos.recalcular(conn)

    def anular(conn, _a, _t, _ana, bea, _f):
        # La revision se hizo con el B4 anulado (ver _preparar): vence su anulacion.
        b4 = _hallazgo(conn, "B4")
        servicios.ejecutar(conn, "anular_hallazgo", {
            "hallazgo_id": b4["id"], "huella": b4["huella"], "motivo": MOTIVO,
            "vigente_hasta": "2026-12-31"}, usuario_id=bea)

    def verificar(conn, _a, _t, ana, bea, f):
        servicios.ejecutar(conn, "verificar_campo", {
            "tabla": "factura", "fila_id": f, "campo": "total_cent",
            "rev": _rev(conn, "factura", f)}, usuario_id=bea)

    def extraccion_nueva(conn, almacen, tmp, _a, _b, _f):
        nueva = _registro("a", invoice_date="2026-09-16")
        nueva["extracted_at"] = "2026-10-01T10:00:00+00:00"
        _cargar(almacen, tmp / "out2", nueva)
        hallazgos.recalcular(conn)

    return {"corregir": corregir, "excluir_linea": excluir, "imputar": imputar,
            "otra_factura": otra_factura, "anular": anular, "verificar": verificar,
            "extraccion_nueva": extraccion_nueva}


def _preparar(conn, almacen, tmp, ana, bea, f, cambio: str) -> None:
    """Lo que hay antes de revisar: en el caso de la anulacion, un B4 ya anulado."""
    if cambio == "anular":
        _cargar(almacen, tmp / "out2", _registro("b", **SOLAPADA))
        hallazgos.recalcular(conn)
        b4 = _hallazgo(conn, "B4")
        servicios.ejecutar(conn, "anular_hallazgo", {
            "hallazgo_id": b4["id"], "huella": b4["huella"], "motivo": MOTIVO}, usuario_id=bea)
    _revisar(conn, ana, f)


@pytest.mark.parametrize("cambio", sorted(_cambios_posteriores()))
def test_cualquier_cambio_posterior_invalida_la_revision(una, tmp_path, cambio) -> None:
    conn = una.conn
    f = factura_de(conn, "2026-4471")
    ana = persona(conn, "Ana", "administracion")
    bea = persona(conn, "Bea", "administracion")
    _preparar(conn, una, tmp_path, ana, bea, f, cambio)
    assert _estado(conn, f) == "revisada"
    huella = revision.huella_contenido(conn, f)
    antes = conn.execute("SELECT count(*) FROM revision").fetchone()[0]

    _cambios_posteriores()[cambio](conn, una, tmp_path, ana, bea, f)

    assert revision.huella_contenido(conn, f) != huella
    assert _estado(conn, f) == "necesita_revision"
    # La revision sigue ahi (es de solo escritura): solo deja de valer.
    assert conn.execute("SELECT count(*) FROM revision").fetchone()[0] == antes


def test_la_diferencia_de_la_orden_dice_que_revision_deja_de_valer(una) -> None:
    conn = una.conn
    f = factura_de(conn, "2026-4471")
    ana = persona(conn, "Ana", "administracion")
    _revisar(conn, ana, f)
    dif = servicios.ejecutar(conn, "fijar_campo", {
        "tabla": "factura", "fila_id": f, "campo": "fecha_vencimiento", "valor": "2026-10-20",
        "rev": _rev(conn, "factura", f), "motivo": MOTIVO}, usuario_id=ana)
    assert dif.revisiones_invalidadas == [f]


def test_una_nota_no_cambia_lo_revisado(una) -> None:
    conn = una.conn
    f = factura_de(conn, "2026-4471")
    ana = persona(conn, "Ana", "administracion")
    _revisar(conn, ana, f)
    servicios.ejecutar(conn, "anadir_nota", {"fila_id": f, "texto": "Llamado el proveedor"},
                       usuario_id=ana)
    assert _estado(conn, f) == "revisada"


def test_no_se_revisa_con_algo_pendiente(almacen, tmp_path) -> None:
    conn = almacen.conn
    _cargar(almacen, tmp_path / "out", _registro("a"), _registro("b", **SOLAPADA))
    hallazgos.recalcular(conn)
    a = factura_de(conn, "2026-4471")
    ana = persona(conn, "Ana", "administracion")
    bea = persona(conn, "Bea", "administracion")
    with pytest.raises(revision.NoRevisable, match="B4"):
        _revisar(conn, ana, a)
    # Con el B4 anulado si; una correccion sin verificar no.
    b4 = _hallazgo(conn, "B4")
    servicios.ejecutar(conn, "anular_hallazgo", {"hallazgo_id": b4["id"], "huella": b4["huella"],
                                                 "motivo": MOTIVO}, usuario_id=bea)
    servicios.ejecutar(conn, "fijar_campo", {
        "tabla": "factura", "fila_id": a, "campo": "fecha_vencimiento", "valor": "2026-10-20",
        "rev": _rev(conn, "factura", a), "motivo": MOTIVO}, usuario_id=ana)
    with pytest.raises(revision.NoRevisable, match="sin resolver"):
        _revisar(conn, bea, a)
    servicios.ejecutar(conn, "verificar_campo", {
        "tabla": "factura", "fila_id": a, "campo": "fecha_vencimiento",
        "rev": _rev(conn, "factura", a)}, usuario_id=bea)
    # Ana corrigio y Bea anulo: con dos personas, revisa una tercera.
    with pytest.raises(SeparacionDeFunciones):
        _revisar(conn, ana, a)
    with pytest.raises(SeparacionDeFunciones):
        _revisar(conn, bea, a)
    carla = persona(conn, "Carla", "administracion")
    assert _revisar(conn, carla, a).detalle["autorrevisada"] is False
    assert _estado(conn, a) == "revisada"


def test_con_una_sola_persona_se_permite_y_queda_autorrevisada(una) -> None:
    conn = una.conn
    f = factura_de(conn, "2026-4471")
    ana = persona(conn, "Ana", "administracion")
    servicios.ejecutar(conn, "fijar_campo", {
        "tabla": "factura", "fila_id": f, "campo": "plazo_pago_dias", "valor": "30",
        "rev": _rev(conn, "factura", f)}, usuario_id=ana)
    dif = _revisar(conn, ana, f)
    assert dif.detalle["autorrevisada"] is True
    assert conn.execute("SELECT autorrevisada FROM revision").fetchone()[0] == 1
    # Llega otra persona con revisar_factura: ya no se puede revisar lo propio.
    persona(conn, "Bea", "administracion")
    servicios.ejecutar(conn, "fijar_campo", {
        "tabla": "factura", "fila_id": f, "campo": "plazo_pago_dias", "valor": "21",
        "rev": _rev(conn, "factura", f), "motivo": "El contrato dice 21 dias"}, usuario_id=ana)
    with pytest.raises(SeparacionDeFunciones):
        _revisar(conn, ana, f)
    denegado = conn.execute("SELECT * FROM evento WHERE tipo = 'permiso_denegado' "
                            "ORDER BY id DESC").fetchone()
    assert denegado["usuario_id"] == ana


def test_revisar_lo_que_ya_cambio_es_un_conflicto(una) -> None:
    conn = una.conn
    f = factura_de(conn, "2026-4471")
    ana = persona(conn, "Ana", "administracion")
    vista = revision.huella_contenido(conn, f)
    servicios.ejecutar(conn, "fijar_campo", {
        "tabla": "factura", "fila_id": f, "campo": "plazo_pago_dias", "valor": "30",
        "rev": _rev(conn, "factura", f)}, usuario_id=ana)
    with pytest.raises(Conflicto):
        servicios.ejecutar(conn, "marcar_revisada", {"factura_id": f, "huella": vista},
                           usuario_id=ana)


def test_devolver_pide_una_nota_y_deja_la_factura_pidiendo_revision(una) -> None:
    conn = una.conn
    f = factura_de(conn, "2026-4471")
    ana = persona(conn, "Ana", "administracion")
    from bms_agent.campos import FaltaMotivo

    with pytest.raises(FaltaMotivo):
        servicios.ejecutar(conn, "devolver_factura", {"factura_id": f}, usuario_id=ana)
    servicios.ejecutar(conn, "devolver_factura", {"factura_id": f,
                                                  "motivo": "Falta el parte de horas"},
                       usuario_id=ana)
    assert _estado(conn, f) == "necesita_revision"
    # Una revision despues la deja revisada otra vez.
    _revisar(conn, ana, f)
    assert _estado(conn, f) == "revisada"


def test_solo_una_persona_con_revisar_factura_y_en_su_orden(una) -> None:
    conn = una.conn
    f = factura_de(conn, "2026-4471")
    carla = persona(conn, "Carla", "consulta")
    with pytest.raises(PermisoDenegado):
        _revisar(conn, carla, f)
    for quien in ("motor", "sistema"):
        with pytest.raises(PermisoDenegado):
            _revisar(conn, usuario_sistema(conn, quien), f)
    huella = revision.huella_contenido(conn, f)
    for actor, usuario in ((usuario_sistema(conn, "motor"), None), (carla, carla)):
        with pytest.raises(sqlite3.IntegrityError, match="revisar_factura"):
            with transaccion(conn):
                evento = registrar(conn, tipo="revision_registrada", actor=actor,
                                   usuario_id=usuario)
                conn.execute("INSERT INTO revision (factura_id, resultado, huella_contenido, "
                             "usuario_id, en, evento_id) VALUES (?, 'revisada', ?, ?, "
                             "'2026-10-14T09:30:00+00:00', ?)", (f, huella, actor, evento))


def test_db_verificar_ve_una_revision_tocada_por_detras(una) -> None:
    conn = una.conn
    f = factura_de(conn, "2026-4471")
    ana = persona(conn, "Ana", "administracion")
    _revisar(conn, ana, f)
    assert verificar_evidencia(conn) == []
    conn.execute("DROP TRIGGER revision_sin_update")
    conn.execute("UPDATE revision SET nota = 'otra cosa', autorrevisada = 0")
    assert any("revision" in p and "por detras" in p for p in verificar_evidencia(conn))


def test_la_huella_del_contenido_es_la_misma_para_una_factura_y_para_todas(una, tmp_path) -> None:
    conn = una.conn
    _cargar(una, tmp_path / "out2", _registro("b", **SOLAPADA))
    hallazgos.recalcular(conn)
    ana = persona(conn, "Ana", "administracion")
    a = factura_de(conn, "2026-4471")
    campos.fijar(conn, "factura", a, {"total_cent": Decimal("1")}, Persona(ana, MOTIVO))
    hallazgos.recalcular(conn)
    todas = revision.contenidos(conn)
    for factura_id, huella in todas.items():
        assert revision.contenidos(conn, [factura_id]) == {factura_id: huella}
