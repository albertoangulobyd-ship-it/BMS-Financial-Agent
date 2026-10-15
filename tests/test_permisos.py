"""permisos.py: personas, roles, usuarios de sistema y separacion de funciones.

Los permisos son los once del §19 mas revisar_factura, gestionar_btw e
importar_datos. Un usuario de sistema no tiene roles (lo impide la base) ni
permisos (lo niega exigir). Un intento denegado queda en la auditoria.
"""

from __future__ import annotations

import sqlite3

import pytest
from conftest import persona

from bms_agent import permisos
from bms_agent.almacen import USUARIOS_SISTEMA, transaccion, usuario_sistema
from bms_agent.almacen.evidencia import verificar_evidencia
from bms_agent.auditoria import verificar_cadena
from bms_agent.dominio import Permiso
from bms_agent.permisos import PermisoDenegado


def _denegados(conn) -> int:
    return conn.execute("SELECT count(*) FROM evento WHERE tipo = 'permiso_denegado'").fetchone()[0]


def test_el_catalogo_es_el_de_la_base(db) -> None:
    assert set(permisos.PERMISOS) == {f["codigo"] for f in db.execute("SELECT codigo FROM permiso")}
    assert len(permisos.PERMISOS) == 14
    assert {"revisar_factura", "gestionar_btw", "importar_datos"} <= set(permisos.PERMISOS)
    for _nombre, (_descripcion, lista) in permisos.ROLES_BASE.items():
        assert lista <= set(permisos.PERMISOS)


def test_un_usuario_de_sistema_no_tiene_roles_ni_permisos(db) -> None:
    permisos.asegurar_roles_base(db)
    for nombre in USUARIOS_SISTEMA:
        sistema = usuario_sistema(db, nombre)
        with pytest.raises(ValueError, match="sistema"):
            permisos.asignar_rol(db, sistema, "administrador")
        with pytest.raises(sqlite3.IntegrityError, match="sistema no puede tener roles"):
            db.execute("INSERT INTO usuario_rol (usuario_id, rol_id, desde) VALUES (?, 1, ?)",
                       (sistema, "2026-10-14T09:30:00+00:00"))
        for permiso in permisos.PERMISOS:
            assert not permisos.tiene(db, sistema, permiso)
            with pytest.raises(PermisoDenegado, match="usuario de sistema"):
                permisos.exigir(db, sistema, permiso)
    with pytest.raises(ValueError, match="sistema"):
        permisos.crear_usuario(db, "motor")


def test_exigir_lanza_y_deja_la_denegacion_en_la_auditoria(db) -> None:
    ana = persona(db, "Ana", "consulta")
    permisos.exigir(db, ana, "ver_facturas")
    with pytest.raises(PermisoDenegado) as error:
        permisos.exigir(db, ana, "marcar_pagada", accion="marcar pagada la 2026-4471")
    assert error.value.registrada
    fila = db.execute("SELECT * FROM evento WHERE tipo = 'permiso_denegado'").fetchone()
    assert (fila["usuario_id"], fila["resultado"]) == (ana, "denegado")
    assert "marcar_pagada" in fila["datos_json"] and "2026-4471" in fila["datos_json"]
    with pytest.raises(ValueError, match="desconocido"):
        permisos.exigir(db, ana, "pagar")


def test_dentro_de_una_orden_la_denegacion_se_registra_despues_del_rollback(db) -> None:
    ana = persona(db, "Ana", "consulta")
    antes = db.execute("SELECT count(*) FROM evento").fetchone()[0]
    with pytest.raises(PermisoDenegado):
        with permisos.orden_auditada(db):
            permisos.crear_usuario(db, "Intrusa")      # esto se deshace
            permisos.exigir(db, ana, "admin")
    assert _denegados(db) == 1
    assert db.execute("SELECT count(*) FROM usuario WHERE nombre = 'Intrusa'").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM evento").fetchone()[0] == antes + 1
    # Dentro de una transaccion ajena no se registra: lo hace quien la abrio.
    with pytest.raises(PermisoDenegado) as error:
        with transaccion(db):
            permisos.exigir(db, ana, "admin")
    assert not error.value.registrada and _denegados(db) == 1
    assert verificar_cadena(db).ok


def test_un_rol_cerrado_ya_no_da_permisos(db, reloj) -> None:
    ana = persona(db, "Ana", "administracion")
    assert permisos.tiene(db, ana, "editar_extraccion")
    assert not permisos.tiene(db, ana, "admin")
    reloj.avanzar(hours=1)
    permisos.cerrar_rol(db, ana, "administracion")
    reloj.avanzar(hours=1)
    assert not permisos.tiene(db, ana, "editar_extraccion")
    # La historia queda: hace un rato si lo tenia.
    assert permisos.tiene(db, ana, "editar_extraccion", en="2026-10-14T10:00:00+00:00")


def test_una_persona_desactivada_no_puede_nada(db) -> None:
    ana = persona(db, "Ana", "administrador")
    db.execute("UPDATE usuario SET activo = 0 WHERE id = ?", (ana,))
    with pytest.raises(PermisoDenegado, match="desactivad"):
        permisos.exigir(db, ana, "ver_facturas")


def test_administrar_usuarios_pide_admin(db) -> None:
    ana = persona(db, "Ana", "administracion")
    with pytest.raises(PermisoDenegado, match="admin"):
        permisos.crear_usuario(db, "Bea", por=ana)
    assert _denegados(db) == 1
    jefa = persona(db, "Jefa", "administrador")
    bea = permisos.crear_usuario(db, "Bea", por=jefa)
    permisos.asignar_rol(db, bea, "consulta", por=jefa)
    autor = db.execute("SELECT usuario_id FROM evento WHERE tipo = 'rol_asignado' "
                       "ORDER BY id DESC").fetchone()[0]
    assert autor == jefa


@pytest.mark.parametrize("personas, misma, esperado", [
    (1, False, permisos.PERMITIDO),
    (2, False, permisos.PERMITIDO),
    (1, True, permisos.AUTORREVISADO),
    (2, True, permisos.DENEGADO),
    (3, True, permisos.DENEGADO),
    (0, True, permisos.AUTORREVISADO),
])
def test_si_hay_dos(personas, misma, esperado) -> None:
    assert permisos.si_hay_dos(personas, misma) == esperado


def test_la_separacion_cuenta_quien_tiene_el_permiso_ahora(db) -> None:
    ana = persona(db, "Ana", "administracion")
    assert permisos.separacion(db, "revisar_factura", ana, ana) == permisos.AUTORREVISADO
    bea = persona(db, "Bea", "administracion")
    assert permisos.separacion(db, "revisar_factura", ana, ana) == permisos.DENEGADO
    assert permisos.separacion(db, "revisar_factura", ana, bea) == permisos.PERMITIDO
    persona(db, "Carla", "consulta")
    assert permisos.personas_con(db, "revisar_factura") == [ana, bea]


def test_personas_y_roles_son_evidencia(db) -> None:
    """Cada persona, rol y asignacion tiene su evento con la foto de la fila."""
    ana = persona(db, "Ana", "administracion")
    assert verificar_evidencia(db) == []
    db.execute("INSERT INTO rol (nombre) VALUES ('por_detras')")
    db.execute("UPDATE usuario SET email = 'otra@x' WHERE id = ?", (ana,))
    problemas = verificar_evidencia(db)
    assert any("rol" in p and "por detras" in p for p in problemas)
    assert any(f"usuario {ana}" in p and "email" in p for p in problemas)


def test_el_dominio_dice_lo_mismo_que_la_base(db) -> None:
    from bms_agent import dominio

    def check(tabla: str, columna: str) -> set[str]:
        import re

        sql = db.execute("SELECT sql FROM sqlite_master WHERE name = ?", (tabla,)).fetchone()[0]
        lista = re.search(rf"\b{columna}\b[^\n]*?IN \(([^)]*)\)", sql, re.S).group(1)
        return {v.strip().strip("'") for v in lista.replace("\n", " ").split(",")}

    assert set(dominio.Fuente.valores()) == check("cambio_campo", "fuente_nueva")
    assert set(dominio.Fuente.valores()) == check("procedencia_campo", "fuente")
    assert dominio.FUENTES_AUTOMATICAS == check("procedencia_campo", "fuente_automatica")
    assert set(dominio.Sentido.valores()) == check("factura", "sentido")
    assert set(dominio.OrigenFactura.valores()) == check("factura", "origen")
    assert set(dominio.TratamientoIva.valores()) == check("factura", "tratamiento_iva")
    assert set(dominio.TipoRelacion.valores()) == check("factura_relacion", "tipo")
    assert set(dominio.EstadoRelacion.valores()) == check("factura_relacion", "estado")
    assert set(dominio.ClaseReferencia.valores()) == check("factura_referencia", "clase")
    assert set(dominio.Permiso.valores()) == {
        f["codigo"] for f in db.execute("SELECT codigo FROM permiso")}
    assert Permiso.ADMIN.value == "admin"


def test_la_cli_crea_personas_con_roles(tmp_path, capsys) -> None:
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["usuario", "crear", "Ana", "--email", "ana@bms", "--rol", "administracion",
                 "--db", str(db)]) == 0
    assert main(["usuario", "asignar", "Ana", "consulta", "--db", str(db)]) == 0
    assert main(["usuario", "crear", "motor", "--db", str(db)]) == 1
    assert main(["usuario", "asignar", "motor", "consulta", "--db", str(db)]) == 1
    assert main(["usuario", "listar", "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    assert "Ana" in salida and "administracion, consulta" in salida
    assert main(["db", "verificar", "--db", str(db)]) == 0
