"""La politica: los ficheros de config/ que cambian como decide el sistema, con su hash.

Cada fichero que se aplica (las tarifas que se siembran, los pesos de la
prioridad) queda en politica_version con su texto entero y su sha256, y con
su evento de auditoria: meses despues se puede saber con que pesos se
ordeno una lista o con que tabla se imputo una linea.

Los pesos de la prioridad que valen son los del ultimo prioridad.yaml
cargado. Hasta que se carga uno, valen los de prioridad.Pesos, que son los
mismos que trae config/prioridad.yaml (un test lo comprueba). Un fichero que
no tiene la forma entera se rechaza antes de apuntarse: los suelos de la
prioridad no estan en el fichero, asi que ningun fichero los puede relajar.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .almacen import reloj_de, transaccion, usuario_sistema
from .almacen.evidencia import foto
from .almacen.unidades import sha256_texto
from .auditoria import registrar as registrar_evento
from .prioridad import PESOS, Pesos, pesos_de_yaml
from .reloj import marca

FICHERO_PRIORIDAD = "prioridad.yaml"


def registrar(conn: sqlite3.Connection, fichero: str, texto: str,
              usuario_id: int | None = None) -> bool:
    """Apunta un fichero en politica_version si ese contenido no estaba ya. Devuelve si es nuevo.

    Volver a una version anterior es otra fila (otra fecha): la que vale es
    la ultima que se cargo.
    """
    sha256 = sha256_texto(texto)
    reloj = reloj_de(conn)
    hoy = reloj.hoy().isoformat()
    ultima = vigente(conn, fichero)
    if ultima is not None and ultima["sha256"] == sha256:
        return False
    if conn.execute("SELECT 1 FROM politica_version WHERE fichero = ? AND sha256 = ? "
                    "AND vigente_desde = ?", (fichero, sha256, hoy)).fetchone():
        return False
    sistema = usuario_sistema(conn, "sistema")
    with transaccion(conn):
        fila_id = int(conn.execute(
            "INSERT INTO politica_version (sha256, fichero, contenido, vigente_desde, cargada_en, "
            "cargada_por) VALUES (?, ?, ?, ?, ?, ?)",
            (sha256, fichero, texto, hoy, marca(reloj.ahora()), usuario_id or sistema),
        ).lastrowid)
        registrar_evento(conn, tipo="politica_cargada", actor=sistema, usuario_id=usuario_id,
                         tabla="politica_version", fila_id=fila_id,
                         datos={"fichero": fichero, "sha256": sha256,
                                "fila": foto(conn, "politica_version", fila_id)})
    return True


def vigente(conn: sqlite3.Connection, fichero: str) -> sqlite3.Row | None:
    """La ultima version cargada de un fichero, o None."""
    return conn.execute(
        "SELECT * FROM politica_version WHERE fichero = ? ORDER BY id DESC LIMIT 1",
        (fichero,)).fetchone()


def pesos_prioridad(conn: sqlite3.Connection) -> Pesos:
    """Los pesos de la prioridad que valen ahora: los del ultimo prioridad.yaml cargado."""
    fila = vigente(conn, FICHERO_PRIORIDAD)
    return PESOS if fila is None else pesos_de_yaml(fila["contenido"])


def cargar_prioridad(conn: sqlite3.Connection, ruta: str | Path,
                     usuario_id: int | None = None) -> tuple[Pesos, bool]:
    """Valida y apunta un fichero de pesos. Devuelve los pesos y si era nuevo.

    Un fichero que no tiene la forma entera lanza PesosNoValidos y no se
    apunta nada.
    """
    texto = Path(ruta).read_text(encoding="utf-8")
    pesos = pesos_de_yaml(texto)
    return pesos, registrar(conn, FICHERO_PRIORIDAD, texto, usuario_id)
