"""Quien puede hacer que: permisos, roles, personas y usuarios de sistema.

Una persona tiene permisos a traves de sus roles, y un rol asignado solo se
cierra (usuario_rol.hasta), asi que siempre se puede saber quien podia que
y cuando. Los usuarios de sistema (sistema, extractor, importador, motor)
actuan pero no tienen roles: la base lo impide con un disparador, y aqui
`exigir()` les niega cualquier permiso. Asi ninguna orden de persona puede
llegar firmada por el sistema, y nada automatico puede verificar un IBAN,
revisar una factura o presentar el BTW.

`exigir()` lanza PermisoDenegado. Un intento denegado tambien queda en la
auditoria (spec §5, evento con resultado 'denegado'), pero ese evento no
puede ir dentro de la transaccion de la orden denegada: el ROLLBACK se lo
llevaria. Por eso `exigir()` lo registra solo cuando no hay transaccion
abierta; dentro de una, la excepcion sale sin registrar
(`registrada=False`) y quien abrio la transaccion lo registra despues del
ROLLBACK con `registrar_denegacion()` (campos.orden lo hace).

Separacion de funciones (§3.13): `si_hay_dos()` decide con la politica "si
hay dos": quien hizo algo no puede ser quien lo revisa cuando hay otra
persona con el permiso; si es la unica, se permite y queda marcado como
autorrevisado. Exigirlo siempre bloquearia una administracion de una
persona. Una negativa es SeparacionDeFunciones, un PermisoDenegado mas, y
queda registrada igual. En el paso 2 la unica revision es verificar un
campo; los predicados SOD1-SOD5 llegan con las ordenes que separan (ver el
registro, paso 2) y se escriben encima de `separacion()`.

La CLI local actua como el operador del fichero (`por=None`, actor
'sistema'): quien la ejecuta ya tiene la base. Desde el paso 4 cada persona
tiene un token (`emitir_token`), del que la base guarda solo el sha256; con
el se identifica en el servidor local y en las ordenes de la CLI.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any

from .almacen import USUARIOS_SISTEMA, reloj_de, transaccion, usuario_sistema
from .almacen.evidencia import foto
from .auditoria import registrar
from .dominio import Permiso
from .reloj import marca

PERMISOS: tuple[str, ...] = Permiso.valores()

# Roles de partida. "administracion" es el trabajo de cada dia; "administrador"
# ademas gestiona usuarios, roles y politica; "consulta" solo mira.
ROLES_BASE: dict[str, tuple[str, frozenset[str]]] = {
    "administrador": ("Todo, incluidos usuarios, roles y politica", frozenset(PERMISOS)),
    "administracion": (
        "El trabajo diario: corregir, imputar, revisar, pagos, avisos, BTW e importaciones",
        frozenset(PERMISOS) - {Permiso.ADMIN.value},
    ),
    "consulta": ("Ver facturas y su detalle", frozenset({Permiso.VER_FACTURAS.value})),
}

PERMITIDO = "permitido"
AUTORREVISADO = "autorrevisado"
DENEGADO = "denegado"


class PermisoDenegado(PermissionError):
    """Una persona (o un usuario de sistema) sin el permiso que pide la orden."""

    # El codigo estable del error en /api/v2 (servicios.codigo_de_error): la app dice
    # el texto en neerlandes o en ingles a partir de el, no de la frase en espanol.
    codigo = "sin_permiso"

    def __init__(
        self, usuario_id: int | None, permiso: str, motivo: str, accion: str | None = None,
    ) -> None:
        super().__init__(motivo)
        self.usuario_id = usuario_id
        self.permiso = permiso
        self.motivo = motivo
        self.accion = accion
        self.registrada = False


class SeparacionDeFunciones(PermisoDenegado):
    """La misma persona no puede hacer y revisar cuando hay otra que puede.

    Es una denegacion como las demas: queda en la auditoria con resultado
    'denegado' (un intento de aprobarse a uno mismo tiene que verse), y quien
    captura PermisoDenegado la captura tambien.
    """

    codigo = "segunda_persona"


def _ahora(conn: sqlite3.Connection) -> str:
    return marca(reloj_de(conn).ahora())


def _comprobar_permiso(permiso: str) -> str:
    valor = str(permiso)
    if valor not in PERMISOS:
        raise ValueError(f"permiso desconocido: {permiso!r}")
    return valor


def _usuario(conn: sqlite3.Connection, usuario_id: int | None) -> sqlite3.Row | None:
    if usuario_id is None:
        return None
    return conn.execute(
        "SELECT id, nombre, es_sistema, activo FROM usuario WHERE id = ?", (usuario_id,)
    ).fetchone()


def es_persona(conn: sqlite3.Connection, usuario_id: int | None) -> bool:
    """Un usuario que existe, esta activo y no es de sistema."""
    fila = _usuario(conn, usuario_id)
    return fila is not None and fila["es_sistema"] == 0 and fila["activo"] == 1


def permisos_de(
    conn: sqlite3.Connection, usuario_id: int | None, *, en: str | None = None
) -> frozenset[str]:
    """Los permisos que tiene una persona en un instante (por defecto, ahora)."""
    if not es_persona(conn, usuario_id):
        return frozenset()
    instante = en or _ahora(conn)
    filas = conn.execute(
        "SELECT DISTINCT rp.permiso FROM usuario_rol AS ur "
        "JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id "
        "WHERE ur.usuario_id = ? AND ur.desde <= ? AND (ur.hasta IS NULL OR ur.hasta > ?)",
        (usuario_id, instante, instante),
    )
    return frozenset(f["permiso"] for f in filas)


def tiene(
    conn: sqlite3.Connection, usuario_id: int | None, permiso: str, *, en: str | None = None,
) -> bool:
    return _comprobar_permiso(permiso) in permisos_de(conn, usuario_id, en=en)


def exigir(
    conn: sqlite3.Connection, usuario_id: int | None, permiso: str, *, accion: str | None = None
) -> None:
    """Lanza PermisoDenegado si el usuario no es una persona activa con el permiso.

    Sin transaccion abierta, la denegacion queda registrada antes de lanzar;
    con una abierta, la registra quien la abrio, despues del ROLLBACK.
    """
    permiso = _comprobar_permiso(permiso)
    fila = _usuario(conn, usuario_id)
    if fila is None:
        motivo = f"la orden necesita una persona con el permiso {permiso}"
    elif fila["es_sistema"]:
        motivo = (f"{fila['nombre']} es un usuario de sistema: no puede tener el permiso "
                  f"{permiso}")
    elif not fila["activo"]:
        motivo = f"{fila['nombre']} esta desactivado"
    elif permiso not in permisos_de(conn, usuario_id):
        motivo = f"{fila['nombre']} no tiene el permiso {permiso}"
    else:
        return
    error = PermisoDenegado(usuario_id, permiso, motivo, accion)
    if not conn.in_transaction:
        registrar_denegacion(conn, error)
    raise error


def registrar_denegacion(conn: sqlite3.Connection, error: PermisoDenegado) -> int:
    """El intento denegado, en la auditoria. Devuelve el id del evento.

    usuario_id del evento solo admite personas; un usuario de sistema que
    intento algo queda como actor.
    """
    fila = _usuario(conn, error.usuario_id)
    persona = fila is not None and not fila["es_sistema"]
    with transaccion(conn):
        actor = fila["id"] if fila is not None else usuario_sistema(conn, "sistema")
        evento = registrar(
            conn, tipo="permiso_denegado", actor=actor,
            usuario_id=error.usuario_id if persona else None, resultado="denegado",
            motivo=error.motivo,
            datos={"permiso": error.permiso, "accion": error.accion,
                   "usuario_solicitante": error.usuario_id},
        )
    error.registrada = True
    return evento


@contextmanager
def orden_auditada(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Una transaccion que, si la orden se deniega, deja la denegacion registrada.

    Si esta transaccion es la de fuera, el ROLLBACK se lleva todo lo que la
    orden hubiera escrito, y despues se registra el intento denegado en una
    transaccion nueva. Si va dentro de otra, la excepcion sigue hacia arriba
    sin registrar: lo hara quien abrio la de fuera.
    """
    exterior = not conn.in_transaction
    try:
        with transaccion(conn):
            yield conn
    except PermisoDenegado as error:
        if exterior and not error.registrada:
            registrar_denegacion(conn, error)
        raise


def personas_con(conn: sqlite3.Connection, permiso: str, *, en: str | None = None) -> list[int]:
    """Las personas activas que tienen el permiso en ese instante."""
    permiso = _comprobar_permiso(permiso)
    instante = en or _ahora(conn)
    return [f["id"] for f in conn.execute(
        "SELECT DISTINCT u.id FROM usuario AS u "
        "JOIN usuario_rol AS ur ON ur.usuario_id = u.id "
        "JOIN rol_permiso AS rp ON rp.rol_id = ur.rol_id "
        "WHERE u.es_sistema = 0 AND u.activo = 1 AND rp.permiso = ? "
        "AND ur.desde <= ? AND (ur.hasta IS NULL OR ur.hasta > ?) ORDER BY u.id",
        (permiso, instante, instante),
    )]


def si_hay_dos(personas_con_permiso: int, misma_persona: bool) -> str:
    """La politica "si hay dos": permitido, autorrevisado o denegado.

    Distintas personas: permitido. La misma, y es la unica con el permiso:
    se permite y se marca autorrevisado (una persona sola no se bloquea a si
    misma). La misma habiendo otra que puede: denegado.
    """
    if not misma_persona:
        return PERMITIDO
    return DENEGADO if personas_con_permiso >= 2 else AUTORREVISADO


def separacion(
    conn: sqlite3.Connection, permiso: str, autor_id: int | None, revisor_id: int
) -> str:
    """si_hay_dos con las personas que hoy tienen el permiso."""
    misma = autor_id is not None and autor_id == revisor_id
    return si_hay_dos(len(personas_con(conn, permiso)), misma)


# ------------------------------------------------------- usuarios y roles

def _actor_y_persona(conn: sqlite3.Connection, por: int | None) -> tuple[int, int | None]:
    """Quien firma una orden de administracion: una persona con admin, o la CLI local."""
    if por is None:
        return usuario_sistema(conn, "sistema"), None
    exigir(conn, por, Permiso.ADMIN.value, accion="administrar usuarios y roles")
    return por, por


def crear_usuario(
    conn: sqlite3.Connection, nombre: str, *, email: str | None = None, por: int | None = None
) -> int:
    """Una persona nueva, sin roles. Los nombres de sistema estan reservados."""
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("una persona necesita un nombre")
    if nombre.lower() in USUARIOS_SISTEMA:
        raise ValueError(f"{nombre!r} es el nombre de un usuario de sistema")
    with orden_auditada(conn):
        actor, persona = _actor_y_persona(conn, por)
        cursor = conn.execute(
            "INSERT INTO usuario (nombre, email, creado_en) VALUES (?, ?, ?)",
            (nombre, (email or "").strip() or None, _ahora(conn)),
        )
        usuario_id = int(cursor.lastrowid)
        registrar(conn, tipo="usuario_creado", actor=actor, usuario_id=persona,
                  tabla="usuario", fila_id=usuario_id,
                  datos={"fila": foto(conn, "usuario", usuario_id)})
    return usuario_id


def usuario_por_nombre(conn: sqlite3.Connection, nombre: str) -> int:
    fila = conn.execute("SELECT id FROM usuario WHERE nombre = ?", (nombre,)).fetchone()
    if fila is None:
        raise LookupError(f"no hay ningun usuario {nombre!r}")
    return int(fila["id"])


def rol_por_nombre(conn: sqlite3.Connection, nombre: str) -> int | None:
    fila = conn.execute("SELECT id FROM rol WHERE nombre = ?", (nombre,)).fetchone()
    return int(fila["id"]) if fila else None


def crear_rol(
    conn: sqlite3.Connection,
    nombre: str,
    permisos: Iterable[str],
    *,
    descripcion: str | None = None,
    por: int | None = None,
) -> int:
    """Un rol con sus permisos. Cada fila queda con su evento y su foto."""
    lista = sorted({_comprobar_permiso(p) for p in permisos})
    with orden_auditada(conn):
        actor, persona = _actor_y_persona(conn, por)
        if rol_por_nombre(conn, nombre) is not None:
            raise ValueError(f"ya hay un rol {nombre!r}")
        rol_id = int(conn.execute(
            "INSERT INTO rol (nombre, descripcion) VALUES (?, ?)", (nombre, descripcion)
        ).lastrowid)
        registrar(conn, tipo="rol_creado", actor=actor, usuario_id=persona, tabla="rol",
                  fila_id=rol_id, datos={"fila": foto(conn, "rol", rol_id)})
        for permiso in lista:
            fila_id = int(conn.execute(
                "INSERT INTO rol_permiso (rol_id, permiso) VALUES (?, ?)", (rol_id, permiso)
            ).lastrowid)
            registrar(conn, tipo="rol_permiso_anadido", actor=actor, usuario_id=persona,
                      tabla="rol_permiso", fila_id=fila_id,
                      datos={"fila": foto(conn, "rol_permiso", fila_id)})
    return rol_id


def listar_roles(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Los roles con sus permisos y cuantas personas activas los tienen hoy."""
    ahora = _ahora(conn)
    salida = []
    for rol in conn.execute("SELECT id, nombre, descripcion FROM rol ORDER BY nombre"):
        permisos = [f[0] for f in conn.execute(
            "SELECT permiso FROM rol_permiso WHERE rol_id = ? ORDER BY permiso", (rol["id"],))]
        personas = conn.execute(
            "SELECT count(DISTINCT ur.usuario_id) FROM usuario_rol AS ur JOIN usuario AS u "
            "ON u.id = ur.usuario_id WHERE ur.rol_id = ? AND u.activo = 1 AND ur.desde <= ? "
            "AND (ur.hasta IS NULL OR ur.hasta > ?)", (rol["id"], ahora, ahora)).fetchone()[0]
        salida.append({"id": rol["id"], "nombre": rol["nombre"],
                       "descripcion": rol["descripcion"], "permisos": permisos,
                       "personas": personas})
    return salida


def asegurar_roles_base(conn: sqlite3.Connection, *, por: int | None = None) -> list[str]:
    """Crea los roles de ROLES_BASE que falten. Devuelve los creados."""
    creados = []
    with orden_auditada(conn):
        for nombre, (descripcion, permisos) in ROLES_BASE.items():
            if rol_por_nombre(conn, nombre) is None:
                crear_rol(conn, nombre, permisos, descripcion=descripcion, por=por)
                creados.append(nombre)
    return creados


def asignar_rol(
    conn: sqlite3.Connection, usuario_id: int, rol: str, *, por: int | None = None
) -> int:
    """Da un rol a una persona desde ahora. Un usuario de sistema no puede tenerlo."""
    with orden_auditada(conn):
        actor, persona = _actor_y_persona(conn, por)
        fila = _usuario(conn, usuario_id)
        if fila is None:
            raise LookupError(f"no hay usuario {usuario_id}")
        if fila["es_sistema"]:
            raise ValueError(f"{fila['nombre']} es un usuario de sistema: no puede tener roles")
        rol_id = rol_por_nombre(conn, rol)
        if rol_id is None:
            raise LookupError(f"no hay ningun rol {rol!r}")
        if conn.execute(
            "SELECT 1 FROM usuario_rol WHERE usuario_id = ? AND rol_id = ? AND hasta IS NULL",
            (usuario_id, rol_id),
        ).fetchone():
            raise ValueError(f"{fila['nombre']} ya tiene el rol {rol}")
        asignacion = int(conn.execute(
            "INSERT INTO usuario_rol (usuario_id, rol_id, desde) VALUES (?, ?, ?)",
            (usuario_id, rol_id, _ahora(conn)),
        ).lastrowid)
        registrar(conn, tipo="rol_asignado", actor=actor, usuario_id=persona,
                  tabla="usuario_rol", fila_id=asignacion,
                  datos={"fila": foto(conn, "usuario_rol", asignacion)})
    return asignacion


def cerrar_rol(
    conn: sqlite3.Connection, usuario_id: int, rol: str, *, por: int | None = None,
) -> int:
    """Quita un rol desde ahora, cerrando la asignacion (no se borra)."""
    with orden_auditada(conn):
        actor, persona = _actor_y_persona(conn, por)
        fila = conn.execute(
            "SELECT ur.id FROM usuario_rol AS ur JOIN rol AS r ON r.id = ur.rol_id "
            "WHERE ur.usuario_id = ? AND r.nombre = ? AND ur.hasta IS NULL",
            (usuario_id, rol),
        ).fetchone()
        if fila is None:
            raise LookupError(f"el usuario {usuario_id} no tiene el rol {rol!r} abierto")
        conn.execute("UPDATE usuario_rol SET hasta = ? WHERE id = ?", (_ahora(conn), fila["id"]))
        registrar(conn, tipo="rol_cerrado", actor=actor, usuario_id=persona,
                  tabla="usuario_rol", fila_id=fila["id"],
                  datos={"fila": foto(conn, "usuario_rol", fila["id"])})
    return int(fila["id"])


def roles_de(conn: sqlite3.Connection, usuario_id: int, instante: str | None = None
             ) -> list[str]:
    """Los nombres de los roles abiertos de un usuario, por orden alfabetico."""
    instante = instante or _ahora(conn)
    return [r["nombre"] for r in conn.execute(
        "SELECT r.nombre FROM usuario_rol AS ur JOIN rol AS r ON r.id = ur.rol_id "
        "WHERE ur.usuario_id = ? AND ur.desde <= ? AND (ur.hasta IS NULL OR ur.hasta > ?) "
        "ORDER BY r.nombre", (usuario_id, instante, instante))]


def listar_usuarios(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Cada usuario con sus roles abiertos, para la CLI."""
    instante = _ahora(conn)
    usuarios = []
    for fila in conn.execute(
            "SELECT id, nombre, email, es_sistema, activo FROM usuario ORDER BY id"):
        usuarios.append({**dict(fila), "roles": roles_de(conn, fila["id"], instante)})
    return usuarios


# ------------------------------------------------------- tokens de persona

PREFIJO_TOKEN = "bms_"


def sha256_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_nuevo() -> str:
    """Un token al azar que empieza siempre por PREFIJO_TOKEN.

    token_urlsafe usa '-' entre sus caracteres, y uno de cada 64 empezaria
    por el: `--token -abc` lo lee argparse como otra opcion y la orden no
    llega a ejecutarse. Con el prefijo ningun token parece una opcion, y
    ademas se reconoce como un token de este programa si aparece donde no
    debe (un log, un fichero subido). El azar sigue siendo el de
    token_urlsafe(32): 256 bits.
    """
    return PREFIJO_TOKEN + secrets.token_urlsafe(32)


def emitir_token(conn: sqlite3.Connection, usuario_id: int, *, por: int | None = None) -> str:
    """Un token nuevo para una persona; el anterior deja de valer. Se devuelve una sola vez.

    La base guarda solo su sha256 (usuario.token_sha256): quien lee el
    fichero no puede actuar como nadie. Es la atribucion local de la V1
    (spec §3.17), hasta que llegue Entra ID con el despliegue.
    """
    token = token_nuevo()
    with orden_auditada(conn):
        actor, persona = _actor_y_persona(conn, por)
        fila = _usuario(conn, usuario_id)
        if fila is None:
            raise LookupError(f"no hay usuario {usuario_id}")
        if fila["es_sistema"]:
            raise ValueError(f"{fila['nombre']} es un usuario de sistema: no tiene token")
        if not fila["activo"]:
            raise ValueError(f"{fila['nombre']} esta desactivado")
        conn.execute("UPDATE usuario SET token_sha256 = ? WHERE id = ?",
                     (sha256_token(token), usuario_id))
        registrar(conn, tipo="usuario_modificado", actor=actor, usuario_id=persona,
                  tabla="usuario", fila_id=usuario_id, motivo="token nuevo",
                  datos={"fila": foto(conn, "usuario", usuario_id)})
    return token


def usuario_por_token(conn: sqlite3.Connection, token: str | None) -> int | None:
    """La persona activa de un token, o None. Un usuario de sistema no tiene token."""
    if not token:
        return None
    fila = conn.execute(
        "SELECT id FROM usuario WHERE token_sha256 = ? AND es_sistema = 0 AND activo = 1",
        (sha256_token(token),)).fetchone()
    return int(fila["id"]) if fila else None


def desactivar_usuario(conn: sqlite3.Connection, usuario_id: int, *,
                       por: int | None = None) -> None:
    """Una persona que ya no actua: no se borra, se desactiva, y su token deja de valer."""
    with orden_auditada(conn):
        actor, persona = _actor_y_persona(conn, por)
        fila = _usuario(conn, usuario_id)
        if fila is None:
            raise LookupError(f"no hay usuario {usuario_id}")
        if fila["es_sistema"]:
            raise ValueError(f"{fila['nombre']} es un usuario de sistema: no se desactiva")
        conn.execute("UPDATE usuario SET activo = 0, token_sha256 = NULL WHERE id = ?",
                     (usuario_id,))
        registrar(conn, tipo="usuario_modificado", actor=actor, usuario_id=persona,
                  tabla="usuario", fila_id=usuario_id, motivo="desactivado",
                  datos={"fila": foto(conn, "usuario", usuario_id)})
