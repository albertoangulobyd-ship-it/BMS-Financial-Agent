"""La cadena de auditoria encuentra lo que se toca por detras de la aplicacion.

La puerta del paso 1: una fila editada con una conexion directa, despues de
borrar los disparadores, no pasa la verificacion. Y lo que la cadena sola no
puede ver (reescribir el final entero, o cortarlo) lo ven las anclas.
"""

from __future__ import annotations

import sqlite3

import pytest

from bms_agent.almacen import abrir, transaccion, usuario_sistema
from bms_agent.almacen.migrar import migrar
from bms_agent.auditoria import (
    HASH_INICIAL,
    Ancla,
    Cambio,
    anclar,
    cabeza,
    calcular_hash,
    historial,
    leer_anclas,
    registrar,
    verificar_cadena,
)


def _eventos(conn, cuantos: int = 4) -> None:
    sistema = usuario_sistema(conn, "sistema")
    for n in range(cuantos):
        with transaccion(conn):
            registrar(
                conn, tipo="prueba", actor=sistema, tabla="factura", fila_id=7,
                motivo=f"evento {n}", datos={"n": n},
                cambios=[Cambio("factura", 7, "total_cent", n + 1, n * 100, (n + 1) * 100,
                                "manual_correccion", fuente_anterior="extraccion",
                                motivo="la factura dice otra cosa")],
            )


@pytest.fixture
def fichero(tmp_path, reloj):
    """Una base en disco: la conexion directa del atacante necesita un fichero."""
    ruta = tmp_path / "bms.sqlite3"
    conn = abrir(ruta, reloj=reloj)
    migrar(conn)
    _eventos(conn)
    conn.close()
    return ruta


def _directa(ruta):
    """Lo que haria alguien con el fichero: sqlite3 a pelo, sin disparadores."""
    conn = sqlite3.connect(ruta, isolation_level=None)
    conn.execute("DROP TRIGGER evento_sin_update")
    conn.execute("DROP TRIGGER evento_sin_delete")
    conn.execute("DROP TRIGGER cambio_campo_sin_update")
    conn.execute("DROP TRIGGER cambio_campo_sin_delete")
    return conn


def _verificar(ruta, anclas=()):
    conn = abrir(ruta)
    try:
        return verificar_cadena(conn, anclas)
    finally:
        conn.close()


def test_una_cadena_intacta_se_verifica(db) -> None:
    _eventos(db)
    resultado = verificar_cadena(db)
    assert resultado.ok, resultado.problemas
    assert resultado.eventos == 5      # el de la migracion y los cuatro
    filas = db.execute("SELECT hash_anterior, hash FROM evento ORDER BY id").fetchall()
    assert filas[0]["hash_anterior"] == HASH_INICIAL
    assert all(b["hash_anterior"] == a["hash"] for a, b in zip(filas, filas[1:]))


def test_un_evento_fuera_de_una_transaccion_no_se_escribe(db) -> None:
    with pytest.raises(RuntimeError, match="transaccion"):
        registrar(db, tipo="suelto", actor=usuario_sistema(db, "sistema"))


def test_los_disparadores_impiden_tocar_la_cadena_desde_la_aplicacion(db) -> None:
    _eventos(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE evento SET motivo = 'otro' WHERE id = 2")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM evento WHERE id = 5")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE cambio_campo SET valor_nuevo = '1' WHERE id = 1")


def test_un_evento_que_no_sigue_al_ultimo_no_entra(db) -> None:
    sistema = usuario_sistema(db, "sistema")
    ultimo = cabeza(db)
    with pytest.raises(sqlite3.IntegrityError, match="fuera de la cadena"):
        db.execute("INSERT INTO evento (id, en, actor, tipo, resultado, hash_anterior, hash) "
                   "VALUES (?, '2026-10-14T09:30:00+00:00', ?, 'x', 'ok', ?, ?)",
                   (ultimo.id + 1, sistema, "1" * 64, "2" * 64))
    with pytest.raises(sqlite3.IntegrityError, match="fuera de la cadena"):
        db.execute("INSERT INTO evento (id, en, actor, tipo, resultado, hash_anterior, hash) "
                   "VALUES (?, '2026-10-14T09:30:00+00:00', ?, 'x', 'ok', ?, ?)",
                   (ultimo.id + 5, sistema, ultimo.hash, "2" * 64))


def test_un_cambio_no_se_cuelga_de_un_evento_viejo(db) -> None:
    _eventos(db, 2)
    with pytest.raises(sqlite3.IntegrityError, match="orden en curso"):
        db.execute("INSERT INTO cambio_campo (evento_id, tabla, fila_id, campo, rev, "
                   "fuente_nueva) VALUES (1, 'factura', 7, 'total_cent', 9, 'extraccion')")


def test_la_persona_que_pide_no_puede_ser_un_usuario_de_sistema(db) -> None:
    motor = usuario_sistema(db, "motor")
    with transaccion(db), pytest.raises(sqlite3.IntegrityError, match="persona"):
        registrar(db, tipo="x", actor=motor, usuario_id=motor)


def test_la_cadena_encuentra_una_fila_editada_sin_disparadores(fichero) -> None:
    """La puerta: editar un evento por detras se ve, y se ve cual."""
    atacante = _directa(fichero)
    atacante.execute("UPDATE evento SET motivo = 'nada que ver' WHERE id = 3")
    atacante.close()

    resultado = _verificar(fichero)
    assert not resultado.ok
    assert resultado.problemas == [
        "el evento 3 o sus cambio_campo se han modificado (el hash no coincide)"]


def test_rehacer_el_hash_de_la_fila_editada_rompe_el_enlace_con_la_siguiente(fichero) -> None:
    atacante = _directa(fichero)
    fila = atacante.execute("SELECT * FROM evento WHERE id = 3").fetchone()
    columnas = [d[0] for d in atacante.execute("SELECT * FROM evento").description]
    evento = dict(zip(columnas, fila), motivo="nada que ver")
    cambios = [dict(zip([d[0] for d in atacante.execute("SELECT * FROM cambio_campo").description], c))
               for c in atacante.execute("SELECT * FROM cambio_campo WHERE evento_id = 3")]
    atacante.execute("UPDATE evento SET motivo = ?, hash = ? WHERE id = 3",
                     ("nada que ver", calcular_hash(evento, cambios)))
    atacante.close()

    assert _verificar(fichero).problemas == [
        "el evento 4 no cuelga del anterior (hash_anterior no coincide)"]


def test_la_cadena_encuentra_un_cambio_de_campo_editado(fichero) -> None:
    atacante = _directa(fichero)
    atacante.execute("UPDATE cambio_campo SET valor_nuevo = '999' WHERE evento_id = 4")
    atacante.close()
    assert _verificar(fichero).problemas == [
        "el evento 4 o sus cambio_campo se han modificado (el hash no coincide)"]


def test_la_cadena_encuentra_un_evento_borrado_por_en_medio(fichero) -> None:
    atacante = _directa(fichero)
    atacante.execute("DELETE FROM cambio_campo WHERE evento_id = 3")
    atacante.execute("DELETE FROM evento WHERE id = 3")
    atacante.close()
    problemas = _verificar(fichero).problemas
    assert problemas == [
        "falta el evento 3: se ha borrado algo de la cadena",
        "el evento 4 no cuelga del anterior (hash_anterior no coincide)",
    ]


def test_las_anclas_ven_lo_que_la_cadena_sola_no_puede_ver(fichero, tmp_path) -> None:
    """Cortar el final, o reescribirlo entero con hashes nuevos, deja una cadena coherente."""
    conn = abrir(fichero)
    log = tmp_path / "out" / "anclas.log"
    ancla = anclar(conn, log)
    conn.close()
    anclas, malas = leer_anclas(log)
    assert anclas == [ancla] and malas == []

    atacante = _directa(fichero)
    atacante.execute("DELETE FROM cambio_campo WHERE evento_id = 5")
    atacante.execute("DELETE FROM evento WHERE id = 5")
    atacante.close()
    assert _verificar(fichero).ok                     # sin anclas, no se nota
    assert _verificar(fichero, anclas).problemas == [
        "la cadena ya no llega al evento anclado 5: se ha cortado"]


def test_una_ancla_detecta_un_final_reescrito(fichero, tmp_path) -> None:
    conn = abrir(fichero)
    ancla = anclar(conn, tmp_path / "anclas.log")
    conn.close()
    atacante = _directa(fichero)
    atacante.execute("DELETE FROM cambio_campo WHERE evento_id = 5")
    atacante.execute("DELETE FROM evento WHERE id = 5")
    atacante.close()
    conn = abrir(fichero)
    with transaccion(conn):                            # otro evento 5, bien encadenado
        registrar(conn, tipo="falso", actor=usuario_sistema(conn, "sistema"))
    conn.close()

    assert _verificar(fichero).ok
    assert _verificar(fichero, [ancla]).problemas == [
        "el evento anclado 5 ya no es el que se anclo: se ha reescrito"]


def test_anclar_no_repite_la_misma_cabeza(db, tmp_path) -> None:
    log = tmp_path / "anclas.log"
    primera = anclar(db, log)
    assert anclar(db, log) == primera
    _eventos(db, 1)
    segunda = anclar(db, log)
    anclas, _ = leer_anclas(log)
    assert anclas == [primera, segunda] and segunda.id == primera.id + 1


def test_dos_bases_pueden_compartir_el_fichero_de_anclas(tmp_path, reloj) -> None:
    """Cada linea dice de que base es: la otra base no da por reescrita a esta."""
    log = tmp_path / "anclas.log"
    bases = []
    for nombre in ("una", "otra"):
        conn = abrir(tmp_path / f"{nombre}.sqlite3", reloj=reloj)
        migrar(conn)
        _eventos(conn, 2)
        anclar(conn, log)
        bases.append(conn)
    try:
        anclas, malas = leer_anclas(log)
        assert malas == [] and [a.id for a in anclas] == [3, 3]
        assert anclas[0].hash != anclas[1].hash
        for conn in bases:
            resultado = verificar_cadena(conn, anclas)
            assert resultado.ok, resultado.problemas
            assert (resultado.anclas, resultado.anclas_ajenas, resultado.ultima_ancla) == (1, 1, 3)
        # anclar mira solo las suyas: la ultima linea es de la otra, y esta no se repite.
        anclar(bases[0], log)
        assert len(leer_anclas(log)[0]) == 2
    finally:
        for conn in bases:
            conn.close()


def test_una_linea_sin_identidad_se_comprueba_igual(fichero, tmp_path) -> None:
    """Las lineas de antes (cuando, id, hash) valen para cualquier base."""
    conn = abrir(fichero)
    ancla = cabeza(conn)
    conn.close()
    log = tmp_path / "anclas.log"
    log.write_text(f"2026-10-14T09:30:00+00:00\t{ancla.id}\t{'f' * 64}\n", encoding="utf-8")
    anclas, _ = leer_anclas(log)
    assert anclas[0].almacen is None
    assert _verificar(fichero, anclas).problemas == [
        f"el evento anclado {ancla.id} ya no es el que se anclo: se ha reescrito"]


def test_una_linea_de_anclas_ilegible_es_un_problema(tmp_path) -> None:
    log = tmp_path / "anclas.log"
    log.write_text("2026-10-14T09:30:00+00:00\t1\t" + "a" * 64 + "\nbasura\n", encoding="utf-8")
    anclas, malas = leer_anclas(log)
    assert anclas == [Ancla(1, "a" * 64)]
    assert len(malas) == 1 and "linea 2" in malas[0]


def test_el_historial_de_una_fila_trae_sus_eventos_y_sus_cambios(db) -> None:
    _eventos(db, 2)
    pasos = historial(db, "factura", 7)
    assert [p["motivo"] for p in pasos] == ["evento 0", "evento 1"]
    assert [[c["valor_nuevo"] for c in p["cambios"]] for p in pasos] == [["100"], ["200"]]
    assert historial(db, "factura", 8) == []


def test_la_hora_del_evento_es_la_del_reloj_de_la_conexion(db, reloj) -> None:
    _eventos(db, 1)
    reloj.avanzar(hours=2)
    _eventos(db, 1)
    horas = [f["en"] for f in db.execute("SELECT en FROM evento ORDER BY id")][-2:]
    assert horas == ["2026-10-14T09:30:00+00:00", "2026-10-14T11:30:00+00:00"]
