"""El almacen: ajustes, migraciones, tablas que no se reescriben y documentos.

La puerta del paso 1 que vive aqui: UPDATE y DELETE abortan en cada tabla de
solo escritura, y el almacen de documentos no sobrescribe y detecta un
original alterado.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import stat
from decimal import Decimal
from pathlib import Path

import pytest

from bms_agent.almacen import (
    USUARIOS_SISTEMA,
    Almacen,
    abrir,
    comprobar_version,
    preparar,
    transaccion,
    usuario_sistema,
)
from bms_agent.almacen import documentos
from bms_agent.almacen.documentos import AlmacenDocumentos, DocumentoCorrupto
from bms_agent.almacen.extracciones import leer_registro, registrar_extraccion
from bms_agent.almacen.migrar import (
    DIRECTORIO_SQL,
    MigracionAlterada,
    comprobar,
    disponibles,
    migrar,
)
from bms_agent.almacen.unidades import (
    FueraDeRango,
    PerdidaDePrecision,
    a_cent,
    a_e4,
    a_mil,
    a_pb,
    de_cent,
    de_e4,
    json_canonico,
    sha256_bytes,
)
from bms_agent import campos, cuentas, excepciones
from bms_agent.auditoria import Cambio, registrar
from bms_agent.campos import Automatico, Persona

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
SHA_PDF = sha256_bytes(PDF)
AHORA = "2026-10-14T09:30:00+00:00"

# Las tablas cuyo UPDATE y DELETE abortan. documento e importacion tienen una
# excepcion cada una (apuntar el original una vez; rellenar mientras esta en
# curso) que se prueba aparte; fuera de ella, abortan igual.
SOLO_ESCRITURA = ("migracion", "politica_version", "evento", "cambio_campo", "extraccion",
                  "nota", "hallazgo_evento", "anulacion", "excepcion_hallazgo", "revision",
                  "prioridad_manual", "cuenta_bancaria", "cuenta_evento",
                  "reextraccion_resultado", "activacion", "linea_sin_casar",
                  "orden_compra_modificacion")
EVIDENCIA = ("documento", "importacion", "ejecucion_reglas", "reextraccion", "extracto_bancario",
             "movimiento_bancario")


def _tablas(conn) -> list[str]:
    return [f["name"] for f in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name")]


def _disparadores(conn) -> set[str]:
    return {f["name"] for f in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}


# --- abrir y ajustes ---

def test_abrir_fija_claves_foraneas_wal_y_espera(tmp_path) -> None:
    conn = abrir(tmp_path / "datos" / "bms.sqlite3")
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert isinstance(conn.execute("SELECT 1 AS uno").fetchone(), sqlite3.Row)
    finally:
        conn.close()


def test_un_sqlite_sin_tablas_strict_no_se_usa() -> None:
    with pytest.raises(RuntimeError, match="3.37"):
        comprobar_version((3, 36, 0))
    comprobar_version((3, 37, 0))


def test_la_ruta_por_defecto_sale_de_bms_db(monkeypatch, tmp_path) -> None:
    from bms_agent.almacen import RUTA_POR_DEFECTO, ruta_por_defecto

    monkeypatch.setenv("BMS_DB", str(tmp_path / "x.sqlite3"))
    assert ruta_por_defecto() == tmp_path / "x.sqlite3"
    monkeypatch.delenv("BMS_DB")
    assert ruta_por_defecto() == RUTA_POR_DEFECTO == Path("datos/bms.sqlite3")


def test_datos_esta_fuera_de_git() -> None:
    from conftest import RAIZ

    assert "/datos/" in (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()


# --- esquema ---

def test_todas_las_tablas_son_strict_con_clave_entera(db) -> None:
    for tabla in _tablas(db):
        estricta = db.execute(
            "SELECT strict FROM pragma_table_list WHERE name = ?", (tabla,)).fetchone()[0]
        assert estricta == 1, tabla
        claves = [c for c in db.execute(f"PRAGMA table_info({tabla})") if c["pk"]]
        assert [c["type"] for c in claves] == ["INTEGER"], tabla


def test_ninguna_columna_es_real(db) -> None:
    """Dinero y cantidades son enteros (spec §4): un REAL suma con error."""
    for tabla in _tablas(db):
        for columna in db.execute(f"PRAGMA table_info({tabla})"):
            assert columna["type"] not in ("REAL", "FLOAT", "DOUBLE", "NUMERIC"), (
                tabla, columna["name"])


def test_strict_y_las_fechas_se_comprueban(db) -> None:
    sistema = usuario_sistema(db, "sistema")
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        db.execute(
            "INSERT INTO politica_version (sha256, fichero, contenido, vigente_desde, "
            "cargada_en, cargada_por) VALUES (?, 'reglas.yaml', 'x', '2026-02-30', ?, ?)",
            ("a" * 64, AHORA, sistema))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO documento (sha256, tipo_mime, bytes, origen, ruta_declarada, "
                   "recibido_fuente, registrado_en, registrado_por) "
                   "VALUES (?, 'application/pdf', '12.50', 'manual', 'entrante', "
                   "'desconocido', ?, ?)", (SHA_PDF, AHORA, sistema))


def test_los_usuarios_de_sistema_estan_y_no_tienen_roles_ni_token(db) -> None:
    nombres = [f["nombre"] for f in db.execute(
        "SELECT nombre FROM usuario WHERE es_sistema = 1 ORDER BY id")]
    assert nombres == list(USUARIOS_SISTEMA)
    motor = usuario_sistema(db, "motor")
    db.execute("INSERT INTO rol (nombre) VALUES ('administracion')")
    with pytest.raises(sqlite3.IntegrityError, match="sistema no puede tener roles"):
        db.execute("INSERT INTO usuario_rol (usuario_id, rol_id, desde) VALUES (?, 1, ?)",
                   (motor, AHORA))
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        db.execute("UPDATE usuario SET token_sha256 = ? WHERE id = ?", ("b" * 64, motor))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE usuario SET es_sistema = 0 WHERE id = ?", (motor,))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE usuario SET nombre = 'otro' WHERE id = ?", (motor,))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM usuario WHERE id = ?", (motor,))


def test_una_persona_tiene_roles_que_solo_se_cierran(db) -> None:
    db.execute("INSERT INTO usuario (nombre, email, creado_en) VALUES ('Ana', 'ana@bms', ?)",
               (AHORA,))
    db.execute("INSERT INTO rol (nombre) VALUES ('administracion')")
    db.execute("INSERT INTO rol_permiso (rol_id, permiso) VALUES (1, 'revisar_factura')")
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        db.execute("INSERT INTO rol_permiso (rol_id, permiso) VALUES (1, 'pagar')")
    db.execute("INSERT INTO usuario_rol (usuario_id, rol_id, desde) VALUES (5, 1, ?)", (AHORA,))
    db.execute("UPDATE usuario_rol SET hasta = ? WHERE id = 1", ("2026-10-15T00:00:00+00:00",))
    with pytest.raises(sqlite3.IntegrityError, match="solo se cierra"):
        db.execute("UPDATE usuario_rol SET hasta = ? WHERE id = 1", ("2026-10-16T00:00:00+00:00",))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM usuario_rol WHERE id = 1")


def test_los_catorce_permisos(db) -> None:
    codigos = {f["codigo"] for f in db.execute("SELECT codigo FROM permiso")}
    assert codigos == {
        "ver_facturas", "editar_extraccion", "anadir_informacion", "cambiar_objeto",
        "cambiar_po", "marcar_pagada", "anular_acreditar", "resolver_aviso", "anular_aviso",
        "confirmar_iban", "admin", "revisar_factura", "gestionar_btw", "importar_datos",
    }


def test_una_correccion_manual_sin_motivo_no_entra(db) -> None:
    """Ni el cambio ni su evento: si quedara el evento, su hash cubriria un cambio que no esta."""
    from bms_agent.auditoria import verificar_cadena

    eventos = db.execute("SELECT count(*) FROM evento").fetchone()[0]
    with transaccion(db):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            registrar(db, tipo="correccion", actor=usuario_sistema(db, "sistema"), cambios=[
                Cambio("factura", 1, "total_cent", 2, 100, 121, "manual_correccion",
                       fuente_anterior="extraccion")])
    assert db.execute("SELECT count(*) FROM evento").fetchone()[0] == eventos
    assert db.execute("SELECT count(*) FROM evento WHERE tipo = 'correccion'").fetchone()[0] == 0
    assert verificar_cadena(db).ok


# --- solo escritura: la puerta ---

def _poblar(almacen: Almacen) -> None:
    """Una fila en cada tabla de solo escritura y de evidencia."""
    conn = almacen.conn
    sistema = usuario_sistema(conn, "sistema")
    with transaccion(conn):
        conn.execute(
            "INSERT INTO politica_version (sha256, fichero, contenido, vigente_desde, "
            "cargada_en, cargada_por) VALUES (?, 'reglas.yaml', 'tolerancia: 1', "
            "'2026-10-01', ?, ?)", ("c" * 64, AHORA, sistema))
        documento = documentos.registrar_documento(
            almacen, sha256=SHA_PDF, contenido=PDF, nombre_original="a.pdf",
            tipo_mime="application/pdf", origen="carpeta", ruta_declarada="entrante",
            recibido_en=AHORA, recibido_fuente="mtime", actor=sistema)
        texto = ('{"source_sha256": "%s", "model": "m", "prompt_version": "p", '
                 '"schema_version": "1", "extraction": {}}' % SHA_PDF)
        extraccion = registrar_extraccion(conn, leer_registro(texto), documento_id=documento.id,
                                          via="api", actor=sistema).id
        conn.execute(
            "INSERT INTO importacion (fuente, tipo, formato, fichero_sha256, estado, "
            "iniciada_en, terminada_en, actor) VALUES ('extracciones', 'extraccion', "
            "'json', ?, 'aceptada', ?, ?, ?)", ("d" * 64, AHORA, AHORA, sistema))
        registrar(conn, tipo="prueba", actor=sistema, cambios=[
            Cambio("factura", 1, "numero", 1, None, "2026-1", "extraccion")])
        persona = int(conn.execute(
            "INSERT INTO usuario (nombre, creado_en) VALUES ('Ana', ?)", (AHORA,)).lastrowid)
        evento = registrar(conn, tipo="nota_anadida", actor=persona, usuario_id=persona)
        conn.execute("INSERT INTO nota (tabla, fila_id, texto, usuario_id, en, evento_id) "
                     "VALUES ('factura', 1, 'llamado el proveedor', ?, ?, ?)",
                     (persona, AHORA, evento))
        # Paso 3: una pasada cerrada, un hallazgo con su deteccion y una anulacion de Ana.
        motor = usuario_sistema(conn, "motor")
        ejecucion = conn.execute(
            "INSERT INTO ejecucion_reglas (motivo, hoy, iniciada_en, terminada_en, actor, "
            "version_codigo, catalogo_sha256, politica_sha256, hasta_evento_id) "
            "VALUES ('manual', '2026-10-14', ?, ?, ?, '0.1.0', ?, ?, 0)",
            (AHORA, AHORA, motor, "e" * 64, "f" * 64)).lastrowid
        hallazgo = conn.execute(
            "INSERT INTO hallazgo (clave, regla, regla_version, huella, tabla, fila_id, "
            "severidad, ambito, pegajosa, anulable, titulo, detalle, valores_json, estado, "
            "primera_vez_en, ultima_vez_en, ultima_ejecucion_id) VALUES ('B3|par:1-2', 'B3', "
            "1, ?, 'factura', 1, 'retencion', 'factura', 1, 1, 'Duplicado', 'b', '{}', "
            "'abierto', ?, ?, ?)", ("a" * 64, AHORA, AHORA, ejecucion)).lastrowid
        conn.execute("INSERT INTO hallazgo_evento (hallazgo_id, tipo, estado, huella, "
                     "ejecucion_id, en) VALUES (?, 'detectado', 'abierto', ?, ?, ?)",
                     (hallazgo, "a" * 64, ejecucion, AHORA))
        rol = conn.execute("INSERT INTO rol (nombre) VALUES ('avisos')").lastrowid
        conn.execute("INSERT INTO rol_permiso (rol_id, permiso) VALUES (?, 'anular_aviso')", (rol,))
        conn.execute("INSERT INTO usuario_rol (usuario_id, rol_id, desde) VALUES (?, ?, ?)",
                     (persona, rol, AHORA))
        anulado = registrar(conn, tipo="hallazgo_anulado", actor=persona, usuario_id=persona)
        conn.execute("INSERT INTO anulacion (hallazgo_id, huella, motivo, usuario_id, en, "
                     "evento_id) VALUES (?, ?, 'el proveedor lo confirmo', ?, ?, ?)",
                     (hallazgo, "a" * 64, persona, AHORA, anulado))
        # Paso 4: una factura con su revision, su prioridad subida y una
        # excepcion con un hallazgo unido. Ana revisa y gestiona avisos.
        for permiso in ("revisar_factura", "resolver_aviso"):
            conn.execute("INSERT INTO rol_permiso (rol_id, permiso) VALUES (?, ?)", (rol, permiso))
        factura = campos.crear(conn, "factura", {"sentido": "entrante", "tipo": "factura",
                                                 "origen": "manual", "numero": "2026-1"},
                               Automatico("extraccion", sistema))
        revisado = registrar(conn, tipo="revision_registrada", actor=persona, usuario_id=persona)
        conn.execute("INSERT INTO revision (factura_id, resultado, huella_contenido, usuario_id, "
                     "en, evento_id) VALUES (?, 'revisada', ?, ?, ?, ?)",
                     (factura, "b" * 64, persona, AHORA, revisado))
        subido = registrar(conn, tipo="prioridad_subida", actor=persona, usuario_id=persona)
        conn.execute("INSERT INTO prioridad_manual (entidad, entidad_id, nivel, motivo, "
                     "usuario_id, en, evento_id) VALUES ('factura', ?, 'urgente', "
                     "'el cliente espera la respuesta', ?, ?, ?)",
                     (factura, persona, AHORA, subido))
        excepcion = excepciones.crear(conn, Persona(persona), tabla="factura", fila_id=factura,
                                      titulo="Comprobar con el proveedor")
        unido = registrar(conn, tipo="excepciones_sincronizadas", actor=motor)
        conn.execute("INSERT INTO excepcion_hallazgo (excepcion_id, hallazgo_id, vinculado_en, "
                     "evento_id) VALUES (?, ?, ?, ?)", (excepcion, hallazgo, AHORA, unido))
        # Paso 5: una cuenta que Ana (con confirmar_iban) verifica por telefono al teclearla.
        conn.execute("INSERT INTO rol_permiso (rol_id, permiso) VALUES (?, 'confirmar_iban')",
                     (rol,))
        proveedor = campos.crear(conn, "proveedor", {"nombre": "Van Dijk BV"},
                                 Automatico("importacion", usuario_sistema(conn, "importador"),
                                            en_nombre_de="maestro_csv"))
        cuentas.decidir(conn, Persona(persona, "llamado al numero de siempre"),
                        titular="proveedor", objetivos=[(proveedor, "NL02ABNA0123456789")],
                        decision=cuentas.Decision("verificada", metodo="llamada",
                                                  telefono_usado="010 1234567"), crear=True)
        # Paso 6: una reextraccion cerrada con su candidata, que Ana (con admin)
        # activa, y una linea editada que la extraccion vigente no pudo casar.
        extractor = usuario_sistema(conn, "extractor")
        reextraccion = conn.execute(
            "INSERT INTO reextraccion (modelo, prompt_version, schema_version, via, "
            "criterio_json, documentos, presupuesto_usd_cent, estimado_bajo_usd_cent, "
            "estimado_alto_usd_cent, salida_medida, estimacion_json, iniciada_en, actor) "
            "VALUES ('m', 'p', '1', 'api', '{}', 1, 500, 10, 20, 0, '{}', ?, ?)",
            (AHORA, extractor)).lastrowid
        resultado = registrar(conn, tipo="reextraccion_resultado", actor=extractor)
        conn.execute("INSERT INTO reextraccion_resultado (reextraccion_id, documento_id, "
                     "resultado, extraccion_id, en, evento_id) VALUES (?, ?, 'candidata', ?, "
                     "?, ?)", (reextraccion, documento.id, extraccion, AHORA, resultado))
        conn.execute("UPDATE reextraccion SET estado = 'terminada', terminada_en = ?, "
                     "extraidas = 1 WHERE id = ?", (AHORA, reextraccion))
        conn.execute("INSERT INTO rol_permiso (rol_id, permiso) VALUES (?, 'admin')", (rol,))
        activado = registrar(conn, tipo="extraccion_activada", actor=persona, usuario_id=persona)
        conn.execute("INSERT INTO activacion (extraccion_id, documento_id, comparacion_sha256, "
                     "usuario_id, en, evento_id) VALUES (?, ?, ?, ?, ?, ?)",
                     (extraccion, documento.id, "9" * 64, persona, AHORA, activado))
        leida = campos.crear(conn, "factura", {
            "sentido": "entrante", "tipo": "factura", "origen": "extraccion",
            "documento_id": documento.id, "extraccion_vigente_id": extraccion},
            Automatico("extraccion", extractor))
        linea = campos.crear(conn, "factura_linea", {"factura_id": leida, "orden": 1},
                             Automatico("extraccion", extractor))
        sin_casar = registrar(conn, tipo="linea_sin_casar", actor=extractor)
        conn.execute("INSERT INTO linea_sin_casar (factura_id, linea_id, extraccion_id, "
                     "excluida, campos_json, en, evento_id) VALUES (?, ?, ?, 0, '[]', ?, ?)",
                     (leida, linea, extraccion, AHORA, sin_casar))
        # Paso 7: un extracto del banco con un movimiento, de una importacion
        # que el importador abre y cierra.
        importador = usuario_sistema(conn, "importador")
        banco = conn.execute(
            "INSERT INTO importacion (fuente, tipo, formato, fichero_sha256, iniciada_en, "
            "actor) VALUES ('banco', 'extracto', 'camt053:001.02', ?, ?, ?)",
            ("7" * 64, AHORA, importador)).lastrowid
        extracto = conn.execute(
            "INSERT INTO extracto_bancario (importacion_id, cuenta_propia_iban, moneda, "
            "saldo_inicial_cent, saldo_final_cent, con_saldos, entradas, formato) "
            "VALUES (?, 'NL60INGB0009988776', 'EUR', 100, 50, 1, 1, 'camt053:001.02')",
            (banco,)).lastrowid
        conn.execute(
            "INSERT INTO movimiento_bancario (importacion_id, extracto_id, cuenta_propia_iban, "
            "posicion, fecha_contable, importe_cent, importe_crudo, moneda, huella) "
            "VALUES (?, ?, 'NL60INGB0009988776', 1, '2026-10-12', -50, '0.50', 'EUR', ?)",
            (banco, extracto, "8" * 64))
        conn.execute("UPDATE importacion SET estado = 'aceptada', terminada_en = ? WHERE id = ?",
                     (AHORA, banco))
        # Paso 9: una PO de un cliente que Ana (con cambiar_po) modifica.
        conn.execute("INSERT INTO rol_permiso (rol_id, permiso) VALUES (?, 'cambiar_po')", (rol,))
        cliente = campos.crear(conn, "cliente", {"nombre": "Havenbedrijf"},
                               Automatico("importacion", importador, en_nombre_de="maestro_csv"))
        orden = campos.crear(conn, "orden_compra", {
            "numero": "PO-1", "lado": "cliente", "cliente_id": cliente,
            "valor_original_cent": 1000000, "fuente": "po_csv"},
            Automatico("importacion", importador))
        modificado = registrar(conn, tipo="po_modificada", actor=persona, usuario_id=persona)
        conn.execute("INSERT INTO orden_compra_modificacion (orden_compra_id, fecha, "
                     "valor_nuevo_cent, motivo, usuario_id, en, evento_id) VALUES (?, '2026-10-01', "
                     "1200000, 'ampliacion firmada', ?, ?, ?)", (orden, persona, AHORA, modificado))


@pytest.mark.parametrize("tabla", SOLO_ESCRITURA + EVIDENCIA)
def test_update_y_delete_abortan_en_cada_tabla_de_solo_escritura(almacen, tabla) -> None:
    _poblar(almacen)
    conn = almacen.conn
    assert conn.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0] >= 1
    texto = next(c["name"] for c in conn.execute(f"PRAGMA table_info({tabla})")
                 if c["type"] == "TEXT" and not c["pk"])
    antes = conn.execute(f"SELECT * FROM {tabla} ORDER BY rowid").fetchall()

    # Un UPDATE que no cambia nada no puede fallar por un CHECK ni un UNIQUE:
    # si aborta, es el disparador, y el mensaje lo dice.
    disparador = r"solo escritura|evidencia|en curso"
    with pytest.raises(sqlite3.IntegrityError, match=disparador):
        conn.execute(f"UPDATE {tabla} SET {texto} = {texto}")
    with pytest.raises(sqlite3.IntegrityError, match=disparador):
        conn.execute(f"UPDATE {tabla} SET {texto} = 'otro'")
    with pytest.raises(sqlite3.IntegrityError, match=disparador):
        conn.execute(f"DELETE FROM {tabla}")
    assert [tuple(f) for f in conn.execute(f"SELECT * FROM {tabla} ORDER BY rowid")] == [
        tuple(f) for f in antes]


def test_la_lista_de_tablas_de_solo_escritura_esta_completa(db) -> None:
    """Una tabla nueva que aborta DELETE tiene que entrar en la prueba de arriba."""
    disparadores = _disparadores(db)
    con_guarda = {t for t in _tablas(db) if f"{t}_sin_delete" in disparadores}
    blindadas = {t for t in con_guarda if f"{t}_sin_update" in disparadores}
    assert blindadas == set(SOLO_ESCRITURA + EVIDENCIA)
    # Las que no se borran pero si se editan: desactivar, cerrar un rol, y las
    # controladas del paso 2 (solo por campos.py, ver test_campos.py).
    from bms_agent.campos import TABLAS_CONTROLADAS

    # El hallazgo del paso 3 cambia de estado, pero solo como diga su ultimo
    # evento (test_hallazgos.py), y la excepcion del paso 4 es controlada como
    # las del paso 2, aunque la escribe excepciones.py (test_excepciones.py).
    assert con_guarda - blindadas == {"usuario", "usuario_rol", "procedencia_campo", "hallazgo",
                                      "excepcion", *TABLAS_CONTROLADAS}


def test_un_documento_solo_admite_apuntar_su_original_una_vez(almacen) -> None:
    conn = almacen.conn
    sistema = usuario_sistema(conn, "sistema")
    registrado = documentos.registrar_documento(
        almacen, sha256=SHA_PDF, contenido=None, nombre_original="a.pdf",
        tipo_mime="application/pdf", origen="out_v1", ruta_declarada="entrante",
        recibido_en=None, recibido_fuente="desconocido", actor=sistema)
    assert (registrado.nuevo, registrado.original) == (True, "falta")
    ruta = f"{SHA_PDF[:2]}/{SHA_PDF}.pdf"
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):   # la ruta sale del hash
        conn.execute("UPDATE documento SET ruta_cas = 'ab/otro.pdf', bytes = 1")
    with pytest.raises(sqlite3.IntegrityError):                  # y nada mas cambia
        conn.execute("UPDATE documento SET ruta_cas = ?, bytes = ?, origen = 'manual'",
                     (ruta, len(PDF)))

    otra_vez = documentos.registrar_documento(
        almacen, sha256=SHA_PDF, contenido=PDF, nombre_original="otro-nombre.pdf",
        tipo_mime="application/pdf", origen="carpeta", ruta_declarada="entrante",
        recibido_en=AHORA, recibido_fuente="mtime", actor=sistema)
    assert (otra_vez.id, otra_vez.nuevo, otra_vez.original) == (registrado.id, False, "anadido")
    fila = conn.execute("SELECT * FROM documento").fetchone()
    assert (fila["ruta_cas"], fila["bytes"], fila["origen"], fila["nombre_original"]) == (
        ruta, len(PDF), "out_v1", "a.pdf")
    with pytest.raises(sqlite3.IntegrityError, match="una vez"):
        conn.execute("UPDATE documento SET ruta_cas = ?", (ruta,))


def test_una_importacion_se_rellena_mientras_esta_en_curso(db) -> None:
    importador = usuario_sistema(db, "importador")
    db.execute("INSERT INTO importacion (fuente, tipo, formato, fichero_sha256, iniciada_en, "
               "actor) VALUES ('extracciones', 'extraccion', 'json', ?, ?, ?)",
               ("e" * 64, AHORA, importador))
    db.execute("UPDATE importacion SET filas_leidas = 3, filas_aceptadas = 3")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE importacion SET fichero_sha256 = ?", ("f" * 64,))
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):   # cerrar exige la hora
        db.execute("UPDATE importacion SET estado = 'aceptada'")
    db.execute("UPDATE importacion SET estado = 'aceptada', terminada_en = ?", (AHORA,))
    with pytest.raises(sqlite3.IntegrityError, match="en curso"):
        db.execute("UPDATE importacion SET estado = 'en_curso'")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):  # el mismo fichero no entra dos veces
        db.execute("INSERT INTO importacion (fuente, tipo, formato, fichero_sha256, iniciada_en, "
                   "actor) VALUES ('extracciones', 'extraccion', 'json', ?, ?, ?)",
                   ("e" * 64, AHORA, importador))


# --- transacciones ---

def test_una_transaccion_que_falla_no_deja_nada(db) -> None:
    sistema = usuario_sistema(db, "sistema")
    eventos = db.execute("SELECT count(*) FROM evento").fetchone()[0]
    with pytest.raises(ZeroDivisionError):
        with transaccion(db):
            registrar(db, tipo="prueba", actor=sistema)
            1 / 0
    assert db.execute("SELECT count(*) FROM evento").fetchone()[0] == eventos
    assert not db.in_transaction


def test_una_transaccion_dentro_de_otra_deshace_solo_lo_suyo(db) -> None:
    sistema = usuario_sistema(db, "sistema")
    with transaccion(db):
        registrar(db, tipo="fuera", actor=sistema)
        with pytest.raises(ValueError):
            with transaccion(db):
                registrar(db, tipo="dentro", actor=sistema)
                raise ValueError
        registrar(db, tipo="fuera-otra-vez", actor=sistema)
    tipos = [f["tipo"] for f in db.execute(
        "SELECT tipo FROM evento WHERE tipo <> 'migracion_aplicada' ORDER BY id")]
    assert tipos == ["fuera", "fuera-otra-vez"]


# --- migraciones ---

def test_migrar_dos_veces_aplica_cada_migracion_una_vez(tmp_path) -> None:
    conn = abrir(tmp_path / "bms.sqlite3")
    try:
        primera = migrar(conn)
        assert [m.nombre for m in primera] == [m.nombre for m in disponibles()]
        assert migrar(conn) == []
        filas = conn.execute("SELECT version, nombre, sha256 FROM migracion").fetchall()
        assert [(f["version"], f["nombre"], f["sha256"]) for f in filas] == [
            (m.version, m.nombre, m.sha256) for m in disponibles()]
        assert conn.execute(
            "SELECT count(*) FROM evento WHERE tipo = 'migracion_aplicada'"
        ).fetchone()[0] == len(disponibles())
    finally:
        conn.close()


def test_dos_procesos_que_migran_a_la_vez_no_chocan(tmp_path, monkeypatch) -> None:
    """B migra entera mientras A ya tiene su lista de pendientes: A no falla ni repite."""
    from bms_agent.almacen import migrar as modulo
    from bms_agent.auditoria import verificar_cadena

    ruta = tmp_path / "carrera.sqlite3"
    a, b = abrir(ruta), abrir(ruta)
    original = modulo.pendientes

    def pendientes_viejas(conn, directorio=None):
        lista = original(conn, directorio)
        if conn is a:
            monkeypatch.setattr(modulo, "pendientes", original)
            migrar(b)
        return lista

    monkeypatch.setattr(modulo, "pendientes", pendientes_viejas)
    try:
        assert [m.nombre for m in migrar(a)] == []
        assert a.execute("SELECT count(*) FROM migracion").fetchone()[0] == len(disponibles())
        assert a.execute(
            "SELECT count(*) FROM evento WHERE tipo = 'migracion_aplicada'"
        ).fetchone()[0] == len(disponibles())
        assert verificar_cadena(a).ok
    finally:
        a.close()
        b.close()


def test_cada_base_tiene_su_identidad(tmp_path, reloj) -> None:
    """Con el mismo reloj, dos bases nuevas no tienen el mismo primer evento."""
    from bms_agent.auditoria import identidad

    bases = [abrir(tmp_path / f"{n}.sqlite3", reloj=reloj) for n in (1, 2)]
    try:
        for conn in bases:
            migrar(conn)
        assert identidad(bases[0]) != identidad(bases[1])
        assert all(len(identidad(conn)) == 64 for conn in bases)
    finally:
        for conn in bases:
            conn.close()


def test_el_hash_de_una_migracion_no_depende_del_final_de_linea(tmp_path) -> None:
    copia = tmp_path / "sql"
    copia.mkdir()
    original = (DIRECTORIO_SQL / "0001_almacen.sql").read_bytes()
    (copia / "0001_almacen.sql").write_bytes(original.replace(b"\n", b"\r\n"))
    assert disponibles(copia)[0].sha256 == disponibles()[0].sha256


def test_una_migracion_editada_despues_de_aplicarse_detiene_todo(tmp_path) -> None:
    copia = tmp_path / "sql"
    shutil.copytree(DIRECTORIO_SQL, copia)
    conn = abrir(tmp_path / "bms.sqlite3")
    try:
        migrar(conn, copia)
        with (copia / "0001_almacen.sql").open("a", encoding="utf-8") as fichero:
            fichero.write("\n-- un retoque inocente\n")
        assert comprobar(conn, copia) and "se edito" in comprobar(conn, copia)[0]
        with pytest.raises(MigracionAlterada):
            migrar(conn, copia)
    finally:
        conn.close()


def test_una_migracion_que_falla_no_deja_nada_a_medias(tmp_path) -> None:
    copia = tmp_path / "sql"
    shutil.copytree(DIRECTORIO_SQL, copia)
    siguiente = len(disponibles()) + 1
    (copia / f"{siguiente:04d}_rota.sql").write_text(
        "CREATE TABLE a_medias (id INTEGER PRIMARY KEY) STRICT;\nESTO NO ES SQL;\n",
        encoding="utf-8")
    conn = abrir(tmp_path / "bms.sqlite3")
    try:
        with pytest.raises(sqlite3.OperationalError):
            migrar(conn, copia)
        assert [f["version"] for f in conn.execute("SELECT version FROM migracion")] == list(
            range(1, siguiente))
        assert "a_medias" not in _tablas(conn)
        assert not conn.in_transaction
    finally:
        conn.close()


def test_las_migraciones_van_de_una_en_una(tmp_path) -> None:
    copia = tmp_path / "sql"
    shutil.copytree(DIRECTORIO_SQL, copia)
    salto = len(disponibles()) + 2
    (copia / f"{salto:04d}_salto.sql").write_text("SELECT 1;\n", encoding="utf-8")
    with pytest.raises(ValueError, match="de 1 en 1"):
        disponibles(copia)


def test_preparar_crea_la_base_y_la_carpeta_de_documentos_al_lado(tmp_path) -> None:
    with preparar(tmp_path / "datos" / "bms.sqlite3") as almacen:
        assert almacen.documentos.raiz == tmp_path / "datos" / "documentos"
        assert usuario_sistema(almacen.conn, "importador") > 0
    with pytest.raises(ValueError, match="memoria"):
        preparar(":memory:")


# --- unidades ---

def test_los_enteros_del_almacen_no_redondean_nunca() -> None:
    assert a_cent(Decimal("8740.00")) == 874000
    assert a_cent(Decimal("-12.5")) == -1250
    assert a_mil(Decimal("37.5")) == 37500
    assert a_e4(Decimal("42.5025")) == 425025
    assert a_pb(Decimal("21")) == 2100 and a_pb(Decimal("5.5")) == 550
    assert de_cent(874000) == Decimal("8740.00") and de_e4(425025) == Decimal("42.5025")
    with pytest.raises(PerdidaDePrecision):
        a_cent(Decimal("0.005"))
    with pytest.raises(PerdidaDePrecision):
        a_e4(Decimal("1.00001"))
    with pytest.raises(TypeError):
        a_cent(12.5)
    with pytest.raises(TypeError):
        a_cent("12.50")
    with pytest.raises(ValueError):
        a_cent(Decimal("NaN"))


def test_la_exactitud_no_depende_de_la_precision_del_contexto() -> None:
    """Con mas de 100 cifras, Decimal redondeaba antes de comprobar: ya no."""
    with pytest.raises(PerdidaDePrecision):
        a_cent(Decimal("1" * 99 + ".005"))
    with pytest.raises(PerdidaDePrecision):
        a_cent(Decimal("1E-999999999"))
    assert a_cent(Decimal("100E-4")) == 1 and a_cent(Decimal("-0.10")) == -10
    assert a_cent(Decimal("0E+999999")) == 0
    assert a_cent(Decimal("92233720368547758.07")) == 2**63 - 1
    assert a_cent(Decimal("-92233720368547758.08")) == -(2**63)
    for fuera in ("92233720368547758.08", "-92233720368547758.09", "1E+999999999", "-" + "1" * 40):
        with pytest.raises(FueraDeRango):
            a_cent(Decimal(fuera))


def test_el_json_canonico_ordena_y_rechaza_floats() -> None:
    assert json_canonico({"b": 1, "a": [None, True, "é"]}) == '{"a":[null,true,"é"],"b":1}'
    with pytest.raises(TypeError, match="float"):
        json_canonico({"importe": 12.5})
    with pytest.raises(TypeError):
        json_canonico({"importe": Decimal("12.5")})
    with pytest.raises(TypeError):
        json_canonico({1: "clave no textual"})


# --- almacen de documentos: la puerta ---

def test_guardar_es_de_una_vez_y_de_solo_lectura(tmp_path) -> None:
    cas = AlmacenDocumentos(tmp_path / "documentos")
    relativa = cas.guardar(PDF, "pdf")
    assert relativa == f"{SHA_PDF[:2]}/{SHA_PDF}.pdf"
    ruta = cas.ruta(relativa)
    assert ruta.read_bytes() == PDF
    if os.name == "posix":
        assert stat.S_IMODE(ruta.stat().st_mode) == 0o444
    assert cas.guardar(PDF, "pdf") == relativa                # el mismo otra vez: nada
    assert cas.ficheros() == [relativa]                       # ni temporales sueltos


def test_el_almacen_no_sobrescribe_un_original_alterado(tmp_path) -> None:
    cas = AlmacenDocumentos(tmp_path / "documentos")
    ruta = cas.ruta(cas.guardar(PDF, "pdf"))
    os.chmod(ruta, 0o644)
    ruta.write_bytes(PDF + b"% alterado\n")
    os.chmod(ruta, 0o444)

    with pytest.raises(DocumentoCorrupto, match="no se sobrescribe"):
        cas.guardar(PDF, "pdf")
    assert ruta.read_bytes() == PDF + b"% alterado\n"         # no se repara en silencio
    with pytest.raises(DocumentoCorrupto, match="no coincide"):
        cas.leer(f"{SHA_PDF[:2]}/{SHA_PDF}.pdf", SHA_PDF)


def test_una_ruta_fuera_del_almacen_no_se_acepta(tmp_path) -> None:
    cas = AlmacenDocumentos(tmp_path)
    for mala in ("../etc/passwd", f"zz/{SHA_PDF}.pdf", f"{SHA_PDF[:2]}/{SHA_PDF}.PDF", ""):
        with pytest.raises(ValueError):
            cas.ruta(mala)


def _registrar(almacen, contenido=PDF, nombre="a.pdf") -> int:
    return documentos.registrar_documento(
        almacen, sha256=sha256_bytes(contenido), contenido=contenido, nombre_original=nombre,
        tipo_mime="application/pdf", origen="carpeta", ruta_declarada="entrante",
        recibido_en=AHORA, recibido_fuente="mtime",
        actor=usuario_sistema(almacen.conn, "sistema")).id


def test_verificar_vuelve_a_calcular_cada_hash(almacen) -> None:
    documento_id = _registrar(almacen)
    otro = PDF + b"% otro\n"
    _registrar(almacen, otro, "b.pdf")
    assert documentos.verificar(almacen) == []

    ruta = almacen.documentos.ruta(f"{SHA_PDF[:2]}/{SHA_PDF}.pdf")
    os.chmod(ruta, 0o644)
    ruta.write_bytes(b"%PDF-1.4 cambiado")
    os.chmod(ruta, 0o444)
    borrado = almacen.documentos.ruta(almacen.conn.execute(
        "SELECT ruta_cas FROM documento WHERE nombre_original = 'b.pdf'").fetchone()[0])
    os.chmod(borrado, 0o644)
    borrado.unlink()
    (ruta.parent / "suelto.pdf").write_bytes(b"x")

    problemas = documentos.verificar(almacen)
    errores = [p for p in problemas if p.gravedad == "error"]
    assert [p.documento_id for p in errores] == [documento_id, documento_id + 1]
    assert "no coincide" in errores[0].detalle and "falta" in errores[1].detalle
    assert [p.gravedad for p in problemas if "suelto" in p.detalle] == ["aviso"]


def test_abrir_un_documento_queda_auditado_tambien_si_falla(almacen) -> None:
    documento_id = _registrar(almacen)
    sistema = usuario_sistema(almacen.conn, "sistema")
    assert documentos.abrir(almacen, documento_id, actor=sistema, motivo="revision") == PDF

    ruta = almacen.documentos.ruta(f"{SHA_PDF[:2]}/{SHA_PDF}.pdf")
    os.chmod(ruta, 0o644)
    ruta.write_bytes(b"%PDF-1.4 cambiado")
    with pytest.raises(DocumentoCorrupto):
        documentos.abrir(almacen, documento_id, actor=sistema)
    aperturas = almacen.conn.execute(
        "SELECT resultado, motivo FROM evento WHERE tipo = 'documento_abierto' ORDER BY id"
    ).fetchall()
    assert [tuple(f) for f in aperturas] == [("ok", "revision"), ("error", None)]


def test_abrir_dentro_de_una_transaccion_se_niega(almacen) -> None:
    """Dentro, el ROLLBACK de quien llama se llevaria el registro de la apertura fallida."""
    sistema = usuario_sistema(almacen.conn, "sistema")
    with transaccion(almacen.conn):
        cursor = almacen.conn.execute(
            "INSERT INTO documento (sha256, tipo_mime, origen, ruta_declarada, recibido_fuente, "
            "registrado_en, registrado_por) VALUES (?, 'application/pdf', 'manual', 'entrante', "
            "'desconocido', ?, ?)", ("b" * 64, AHORA, sistema))
    documento_id = cursor.lastrowid
    with pytest.raises(DocumentoCorrupto):
        documentos.abrir(almacen, documento_id, actor=sistema)
    with pytest.raises(RuntimeError, match="transaccion"):
        with transaccion(almacen.conn):
            documentos.abrir(almacen, documento_id, actor=sistema)
    aperturas = almacen.conn.execute(
        "SELECT resultado FROM evento WHERE tipo = 'documento_abierto'").fetchall()
    assert [f[0] for f in aperturas] == ["error"]


def test_el_contenido_tiene_que_ser_el_del_hash(almacen) -> None:
    with pytest.raises(ValueError, match="no es el del hash"):
        documentos.registrar_documento(
            almacen, sha256="0" * 64, contenido=PDF, nombre_original="a.pdf",
            tipo_mime="application/pdf", origen="carpeta", ruta_declarada="entrante",
            recibido_en=AHORA, recibido_fuente="mtime",
            actor=usuario_sistema(almacen.conn, "sistema"))


# --- reloj ---

def test_hoy_es_la_fecha_de_amsterdam_y_las_marcas_van_en_utc() -> None:
    from datetime import date, datetime, timedelta, timezone

    from bms_agent.reloj import RelojFijo, marca

    noche = RelojFijo(datetime(2026, 10, 14, 23, 30, tzinfo=timezone.utc))
    assert noche.hoy() == date(2026, 10, 15)              # en Amsterdam ya es manana
    hora_local = datetime(2026, 10, 15, 1, 30, tzinfo=timezone(timedelta(hours=2)))
    assert marca(hora_local) == "2026-10-14T23:30:00+00:00"
    with pytest.raises(ValueError):
        marca(datetime(2026, 10, 14, 23, 30))
    with pytest.raises(ValueError):
        RelojFijo(datetime(2026, 10, 14))
