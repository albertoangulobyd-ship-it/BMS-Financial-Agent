"""Las excepciones: el trabajo pendiente de cada entidad (spec §7 y §15).

Un hallazgo dice que algo no cuadra; una excepcion dice quien se ocupa, de
que, hasta cuando y como acabo. Hay una abierta como mucho por entidad (una
factura, un proveedor...), y agrupa sus hallazgos que bloquean o retienen,
mas los avisos de las reglas que piden una (Q3, K1, U1). Asi un correo al
proveedor cubre todo lo suyo, y cada hallazgo sigue con su propia vida.

- La abre el motor, en cada pasada (`sincronizar`): una entidad con un
  hallazgo que la merece y sin excepcion abierta tiene una nueva; a una
  abierta se le unen los hallazgos nuevos. Tambien la puede abrir una
  persona a mano (`crear`), para algo que ninguna regla ve.
- Su estado lo pone una persona con resolver_aviso: asignada (con
  responsable), esperando a alguien de fuera (con a quien y una fecha de
  seguimiento, por defecto como mucho hoy + 14 dias) y resuelta (con una
  resolucion y sus notas). Nada automatico la asigna ni la resuelve: la base
  lo exige (migracion 0004).
- No se resuelve mientras un hallazgo suyo que bloquea siga abierto sin
  anular. Resolverla no cierra sus hallazgos ni aprueba ningun pago.
- Una resuelta no se toca. Si un hallazgo suyo vuelve a abrirse, o cambia
  su evidencia, despues de resolverla, la siguiente pasada abre otra; los que
  no cambiaron siguen cubiertos por aquella resolucion.

La tabla es controlada (rev y la guarda de siempre): cada columna que entra
o cambia tiene su cambio_campo en el evento de la orden. No pasa por
campos.py porque es estado de trabajo, no un dato de un documento: alli una
fuente automatica no pisa nunca lo manual, y aqui el motor tiene que poder
abrir una excepcion nueva aunque una persona cerrara la anterior. El estado
que pone una persona va como manual_entrada; lo que pone el motor, como
calculado.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .almacen import reloj_de, usuario_sistema
from .almacen.unidades import json_canonico
from .auditoria import Cambio, registrar
from .campos import Conflicto, FaltaMotivo, Persona
from .dominio import (
    ESTADOS_EXCEPCION_ABIERTA,
    AmbitoHallazgo,
    EsperandoA,
    EstadoExcepcion,
    EstadoHallazgo,
    Fuente,
    Permiso,
    ResolucionExcepcion,
    Severidad,
)
from .permisos import exigir, orden_auditada
from .reglas import catalogo
from .reloj import marca

ABIERTA = EstadoExcepcion.ABIERTA.value
ASIGNADA = EstadoExcepcion.ASIGNADA.value
ESPERANDO = EstadoExcepcion.ESPERANDO_EXTERNO.value
RESUELTA = EstadoExcepcion.RESUELTA.value

TABLA = "excepcion"
COLUMNAS: tuple[str, ...] = (
    "titulo", "descripcion", "tabla", "fila_id", "factura_id", "estado", "responsable_id",
    "esperando_a", "fecha_seguimiento", "resolucion", "resolucion_notas", "creada_en",
    "creada_por", "resuelta_en", "resuelta_por", "hallazgo_evento_hasta",
)
# El seguimiento de una excepcion que espera a alguien de fuera: por defecto
# como mucho dentro de 14 dias (spec §7).
SEGUIMIENTO_MAXIMO_DIAS = 14
# Los hallazgos que piden excepcion por su severidad; los avisos, si su regla lo dice.
SEVERIDADES = frozenset({Severidad.BLOQUEO.value, Severidad.RETENCION.value})
# Una excepcion se abre por lo que sigue pidiendo a alguien y no esta aceptado.
ESTADOS_QUE_PIDEN = frozenset({EstadoHallazgo.ABIERTO.value, EstadoHallazgo.DESAPARECIDO.value})
# Lo que vuelve a pedir trabajo despues de una resolucion.
_REAPERTURAS = ("detectado", "reabierto", "cambio_evidencia")
_ENTIDADES = frozenset(AmbitoHallazgo.valores())

_TRANSICIONES: dict[str, frozenset[str]] = {
    ASIGNADA: frozenset({ABIERTA, ASIGNADA, ESPERANDO}),
    ESPERANDO: frozenset({ABIERTA, ASIGNADA, ESPERANDO}),
    RESUELTA: frozenset({ABIERTA, ASIGNADA, ESPERANDO}),
}


class EstadoNoValido(ValueError):
    """La orden no tiene sentido en el estado en que esta la excepcion."""


class BloqueoAbierto(ValueError):
    """Un hallazgo que bloquea sigue abierto sin anular: la excepcion no se resuelve."""


@dataclass
class Sincronizacion:
    """Lo que hizo el motor con las excepciones en una pasada."""

    evento_id: int | None = None
    creadas: list[int] = field(default_factory=list)
    vinculos: list[tuple[int, int]] = field(default_factory=list)


# ------------------------------------------------------------ escritura

def _fila(conn: sqlite3.Connection, excepcion_id: int) -> sqlite3.Row:
    fila = conn.execute("SELECT * FROM excepcion WHERE id = ?", (excepcion_id,)).fetchone()
    if fila is None:
        raise LookupError(f"no hay excepcion {excepcion_id}")
    return fila


# Los cambio_campo de una excepcion no llevan factura_id: esa columna dice
# que dato de una factura cambio, y la pasada del motor la usa para buscar la
# causa de cada hallazgo que aparece o desaparece. Asignar o resolver una
# excepcion no cambia nada que lea una regla. El evento si lleva la factura,
# para que salga en su historia.

def _cambios_alta(fila_id: int, valores: dict[str, Any], fuente: str) -> list[Cambio]:
    return [Cambio(tabla=TABLA, fila_id=fila_id, campo=c, rev=0, valor_anterior=None,
                   valor_nuevo=valores[c], fuente_nueva=fuente)
            for c in COLUMNAS if valores.get(c) is not None]


def _ultima_fuente(conn: sqlite3.Connection, fila_id: int, campo: str) -> str | None:
    fila = conn.execute(
        "SELECT fuente_nueva FROM cambio_campo WHERE tabla = ? AND fila_id = ? AND campo = ? "
        "ORDER BY id DESC LIMIT 1", (TABLA, fila_id, campo)).fetchone()
    return fila[0] if fila else None


def _insertar(conn: sqlite3.Connection, fila_id: int, valores: dict[str, Any]) -> None:
    columnas = ("id", *COLUMNAS, "rev")
    conn.execute(f"INSERT INTO excepcion ({', '.join(columnas)}) "
                 f"VALUES ({', '.join('?' * len(columnas))})",
                 (fila_id, *(valores.get(c) for c in COLUMNAS), 0))


def _siguiente_id(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT coalesce(max(id), 0) + 1 FROM excepcion").fetchone()[0])


def _cambiar(conn: sqlite3.Connection, persona: Persona, excepcion: sqlite3.Row,
             nuevos: dict[str, Any], *, tipo: str, motivo: str | None,
             datos: dict[str, Any] | None = None) -> int:
    """Una orden de una persona sobre una excepcion: su evento con un cambio por columna."""
    rev = excepcion["rev"] + 1
    cambios = [
        Cambio(tabla=TABLA, fila_id=excepcion["id"], campo=c, rev=rev,
               valor_anterior=excepcion[c], valor_nuevo=v,
               fuente_nueva=Fuente.MANUAL_ENTRADA.value,
               fuente_anterior=_ultima_fuente(conn, excepcion["id"], c), motivo=motivo)
        for c, v in nuevos.items() if v != excepcion[c]]
    evento = registrar(
        conn, tipo=tipo, actor=persona.usuario_id, usuario_id=persona.usuario_id,
        tabla=TABLA, fila_id=excepcion["id"], factura_id=excepcion["factura_id"],
        motivo=motivo, peticion_id=persona.peticion_id, datos=datos, cambios=cambios)
    asignaciones = ", ".join(f"{c} = ?" for c in nuevos)
    cursor = conn.execute(
        f"UPDATE excepcion SET {asignaciones}, rev = ? WHERE id = ? AND rev = ?",
        (*nuevos.values(), rev, excepcion["id"], excepcion["rev"]))
    if cursor.rowcount != 1:
        raise Conflicto(f"la excepcion {excepcion['id']} cambio mientras se escribia")
    return evento


# ------------------------------------------------------------ el motor

@dataclass(frozen=True)
class _Pendiente:
    id: int
    regla: str
    severidad: str
    estado: str
    titulo: str
    entidades: tuple[tuple[str, int], ...]


def merece_excepcion(regla: str, severidad: str, estado: str) -> bool:
    """Un hallazgo que pide una excepcion: pendiente sin aceptar, y que bloquea o retiene
    (o un aviso de una regla que la pide)."""
    if estado not in ESTADOS_QUE_PIDEN:
        return False
    definicion = catalogo.POR_ID.get(regla)
    return severidad in SEVERIDADES or (definicion is not None and definicion.crea_excepcion)


def _pendientes(conn: sqlite3.Connection) -> list[_Pendiente]:
    """Los hallazgos que piden excepcion, cada uno con las entidades a las que afecta.

    Uno de grupo (B2, B4, G3) afecta a cada factura que cubre: ninguna de
    las dos facturas de un duplicado se paga sin mirarlo.
    """
    objetivos: dict[int, set[int]] = defaultdict(set)
    for hallazgo_id, fila_id in conn.execute(
            "SELECT o.hallazgo_id, o.fila_id FROM hallazgo_objetivo AS o "
            "JOIN hallazgo AS h ON h.id = o.hallazgo_id "
            "WHERE o.tabla = 'factura' AND h.estado IN ('abierto', 'desaparecido')"):
        objetivos[hallazgo_id].add(fila_id)
    salida = []
    for fila in conn.execute(
            "SELECT id, regla, severidad, estado, titulo, ambito, tabla, fila_id, factura_id "
            "FROM hallazgo WHERE estado IN ('abierto', 'desaparecido') ORDER BY id"):
        if not merece_excepcion(fila["regla"], fila["severidad"], fila["estado"]):
            continue
        if fila["ambito"] == AmbitoHallazgo.FACTURA.value:
            facturas = set(objetivos.get(fila["id"], ()))
            if fila["factura_id"] is not None:
                facturas.add(fila["factura_id"])
            entidades = tuple(("factura", f) for f in sorted(facturas))
        elif fila["tabla"] in _ENTIDADES:
            entidades = ((fila["tabla"], fila["fila_id"]),)
        else:
            entidades = ()
        salida.append(_Pendiente(fila["id"], fila["regla"], fila["severidad"], fila["estado"],
                                 fila["titulo"], entidades))
    return salida


def _titulo(hallazgos: list[_Pendiente]) -> str:
    nombres = [f"{h.regla} {h.titulo}" for h in hallazgos]
    if len(nombres) <= 2:
        return " y ".join(nombres)
    return f"{nombres[0]}, {nombres[1]} y {len(nombres) - 2} más"


def _descripcion(conn: sqlite3.Connection, tabla: str, fila_id: int) -> str | None:
    if tabla != "factura":
        return None
    fila = conn.execute(
        "SELECT numero, sentido, emisor_nombre_doc, receptor_nombre_doc FROM factura "
        "WHERE id = ?", (fila_id,)).fetchone()
    if fila is None:
        return None
    parte = fila["emisor_nombre_doc"] if fila["sentido"] == "entrante" else fila[
        "receptor_nombre_doc"]
    numero = fila["numero"] or "sin número"
    return f"Factura {numero}" + (f" de {parte}" if parte and fila["sentido"] == "entrante"
                                  else f" a {parte}" if parte else "")


def sincronizar(conn: sqlite3.Connection, *, usuario_id: int | None = None) -> Sincronizacion:
    """Abre las excepciones que faltan y les une los hallazgos nuevos. Un evento, o ninguno.

    Lo llama cada pasada del motor (hallazgos.recalcular), en su
    transaccion, despues de poner al dia los hallazgos. Si no hay nada que
    abrir ni que unir no escribe nada: una pasada sin cambios no deja eventos.
    """
    resultado = Sincronizacion()
    pendientes = _pendientes(conn)
    if not pendientes:
        return resultado
    abiertas = {(f["tabla"], f["fila_id"]): f["id"] for f in conn.execute(
        "SELECT id, tabla, fila_id FROM excepcion WHERE estado <> 'resuelta'")}
    resueltas: dict[int, int] = {f["id"]: f["hallazgo_evento_hasta"] for f in conn.execute(
        "SELECT id, hallazgo_evento_hasta FROM excepcion WHERE estado = 'resuelta'")}
    entidad_de = {f["id"]: (f["tabla"], f["fila_id"]) for f in conn.execute(
        "SELECT id, tabla, fila_id FROM excepcion")}
    vinculos: dict[int, set[int]] = defaultdict(set)
    for excepcion_id, hallazgo_id in conn.execute(
            "SELECT excepcion_id, hallazgo_id FROM excepcion_hallazgo"):
        vinculos[hallazgo_id].add(excepcion_id)
    marcas = ", ".join("?" * len(_REAPERTURAS))
    reabierto = dict(conn.execute(
        f"SELECT hallazgo_id, max(id) FROM hallazgo_evento WHERE tipo IN ({marcas}) "
        "GROUP BY hallazgo_id", _REAPERTURAS).fetchall())

    def cubierto(h: _Pendiente, entidad: tuple[str, int]) -> bool:
        """Lo cubre una resolucion de esa entidad posterior a su ultima reapertura."""
        return any(entidad_de[e] == entidad and e in resueltas
                   and reabierto.get(h.id, 0) <= resueltas[e] for e in vinculos.get(h.id, ()))

    por_entidad: dict[tuple[str, int], list[_Pendiente]] = defaultdict(list)
    for h in pendientes:
        for entidad in h.entidades:
            por_entidad[entidad].append(h)

    ahora = marca(reloj_de(conn).ahora())
    motor = usuario_sistema(conn, "motor")
    nuevas: list[tuple[int, dict[str, Any]]] = []
    uniones: list[tuple[int, int]] = []
    siguiente = _siguiente_id(conn)
    for entidad in sorted(por_entidad):
        hallazgos = por_entidad[entidad]
        abierta = abiertas.get(entidad)
        if abierta is not None:
            uniones.extend((abierta, h.id) for h in hallazgos if abierta not in vinculos[h.id])
            continue
        if all(cubierto(h, entidad) for h in hallazgos):
            continue
        tabla, fila_id = entidad
        valores = {
            "titulo": _titulo(hallazgos), "descripcion": _descripcion(conn, tabla, fila_id),
            "tabla": tabla, "fila_id": fila_id,
            "factura_id": fila_id if tabla == "factura" else None, "estado": ABIERTA,
            "creada_en": ahora, "creada_por": motor,
        }
        nuevas.append((siguiente, valores))
        uniones.extend((siguiente, h.id) for h in hallazgos)
        siguiente += 1
    if not nuevas and not uniones:
        return resultado

    cambios = [c for fila_id, valores in nuevas
               for c in _cambios_alta(fila_id, valores, Fuente.CALCULADO.value)]
    resultado.evento_id = registrar(
        conn, tipo="excepciones_sincronizadas", actor=motor, usuario_id=usuario_id,
        tabla=TABLA, datos={"creadas": [i for i, _v in nuevas],
                            "vinculos": [list(u) for u in uniones]},
        cambios=cambios)
    for fila_id, valores in nuevas:
        _insertar(conn, fila_id, valores)
    conn.executemany(
        "INSERT INTO excepcion_hallazgo (excepcion_id, hallazgo_id, vinculado_en, evento_id) "
        "VALUES (?, ?, ?, ?)", [(e, h, ahora, resultado.evento_id) for e, h in uniones])
    resultado.creadas = [i for i, _v in nuevas]
    resultado.vinculos = uniones
    return resultado


# ------------------------------------------------------------ ordenes de personas

def _exigir(conn: sqlite3.Connection, persona: Persona, accion: str) -> None:
    exigir(conn, persona.usuario_id, Permiso.RESOLVER_AVISO.value, accion=accion)


def _comprobar_rev(excepcion: sqlite3.Row, rev: int | None) -> None:
    if rev is not None and excepcion["rev"] != rev:
        raise Conflicto(f"la excepcion {excepcion['id']} esta en la rev {excepcion['rev']} y se "
                        f"edito sobre la {rev}: vuelve a cargarla")


def _comprobar_transicion(excepcion: sqlite3.Row, destino: str) -> None:
    if excepcion["estado"] not in _TRANSICIONES[destino]:
        raise EstadoNoValido(
            f"la excepcion {excepcion['id']} esta {excepcion['estado']}: no pasa a {destino}")


def abierta_de(conn: sqlite3.Connection, tabla: str, fila_id: int) -> sqlite3.Row | None:
    """La excepcion sin resolver de una entidad, si la hay."""
    return conn.execute("SELECT * FROM excepcion WHERE tabla = ? AND fila_id = ? "
                        "AND estado <> 'resuelta'", (tabla, fila_id)).fetchone()


def crear(conn: sqlite3.Connection, persona: Persona, *, tabla: str, fila_id: int,
          titulo: str, datos: dict[str, Any] | None = None) -> int:
    """Una persona abre a mano una excepcion sobre algo (lo que ninguna regla ve).

    El motivo de la persona es la descripcion. Si la entidad ya tiene una
    abierta, se trabaja en esa: no hay dos.
    """
    titulo = (titulo or "").strip()
    with orden_auditada(conn):
        _exigir(conn, persona, "abrir una excepcion")
        if tabla not in _ENTIDADES:
            raise ValueError(f"una excepcion es de {', '.join(sorted(_ENTIDADES))}, no de {tabla}")
        if not titulo:
            raise FaltaMotivo("una excepcion necesita decir de que va (titulo)")
        if tabla == "factura" and conn.execute(
                "SELECT 1 FROM factura WHERE id = ?", (fila_id,)).fetchone() is None:
            raise LookupError(f"no hay factura {fila_id}")
        existente = abierta_de(conn, tabla, fila_id)
        if existente is not None:
            raise EstadoNoValido(f"{tabla} {fila_id} ya tiene la excepcion {existente['id']} "
                                 "abierta: se trabaja en esa")
        fila_id_nueva = _siguiente_id(conn)
        valores = {
            "titulo": titulo, "descripcion": (persona.motivo or "").strip() or None,
            "tabla": tabla, "fila_id": fila_id,
            "factura_id": fila_id if tabla == "factura" else None, "estado": ABIERTA,
            "creada_en": marca(reloj_de(conn).ahora()), "creada_por": persona.usuario_id,
        }
        registrar(conn, tipo="excepcion_abierta", actor=persona.usuario_id,
                  usuario_id=persona.usuario_id, tabla=TABLA, fila_id=fila_id_nueva,
                  factura_id=valores["factura_id"], motivo=valores["descripcion"],
                  peticion_id=persona.peticion_id, datos=datos,
                  cambios=_cambios_alta(fila_id_nueva, valores, Fuente.MANUAL_ENTRADA.value))
        _insertar(conn, fila_id_nueva, valores)
    return fila_id_nueva


def asignar(conn: sqlite3.Connection, persona: Persona, excepcion_id: int, *,
            responsable_id: int, rev: int | None = None,
            datos: dict[str, Any] | None = None) -> int:
    """Pone a alguien a cargo. Si se esperaba a alguien de fuera, la espera termina."""
    with orden_auditada(conn):
        _exigir(conn, persona, "asignar una excepcion")
        excepcion = _fila(conn, excepcion_id)
        _comprobar_rev(excepcion, rev)
        _comprobar_transicion(excepcion, ASIGNADA)
        responsable = conn.execute("SELECT es_sistema, activo FROM usuario WHERE id = ?",
                                   (responsable_id,)).fetchone()
        if responsable is None or responsable["es_sistema"] or not responsable["activo"]:
            raise ValueError("el responsable de una excepcion es una persona activa")
        return _cambiar(conn, persona, excepcion, {
            "estado": ASIGNADA, "responsable_id": responsable_id, "esperando_a": None,
            "fecha_seguimiento": None,
        }, tipo="excepcion_asignada", motivo=(persona.motivo or "").strip() or None, datos=datos)


def seguimiento_por_defecto(hoy: date, vencimiento: date | None) -> date:
    """Hoy + 14 dias, o antes si la factura vence antes (y no ha vencido ya)."""
    tope = hoy + timedelta(days=SEGUIMIENTO_MAXIMO_DIAS)
    if vencimiento is not None and hoy <= vencimiento < tope:
        return vencimiento
    return tope


def esperar(conn: sqlite3.Connection, persona: Persona, excepcion_id: int, *,
            esperando_a: str, fecha_seguimiento: date | str | None = None,
            rev: int | None = None, datos: dict[str, Any] | None = None) -> int:
    """La excepcion espera a alguien de fuera hasta una fecha de seguimiento.

    Sin fecha, la de `seguimiento_por_defecto`. Una fecha pasada no tiene
    sentido: el seguimiento es cuando se vuelve a mirar.
    """
    with orden_auditada(conn):
        _exigir(conn, persona, "dejar una excepcion esperando")
        excepcion = _fila(conn, excepcion_id)
        _comprobar_rev(excepcion, rev)
        _comprobar_transicion(excepcion, ESPERANDO)
        quien = str(getattr(esperando_a, "value", esperando_a))
        if quien not in EsperandoA.valores():
            raise ValueError(f"se espera a {', '.join(EsperandoA.valores())}, no a {quien!r}")
        hoy = reloj_de(conn).hoy()
        if fecha_seguimiento is None:
            vencimiento = None
            if excepcion["factura_id"] is not None:
                fila = conn.execute("SELECT vencimiento FROM factura_estado WHERE factura_id = ?",
                                    (excepcion["factura_id"],)).fetchone()
                if fila is not None and fila["vencimiento"]:
                    vencimiento = date.fromisoformat(fila["vencimiento"])
            fecha = seguimiento_por_defecto(hoy, vencimiento)
        else:
            fecha = (fecha_seguimiento if isinstance(fecha_seguimiento, date)
                     else date.fromisoformat(str(fecha_seguimiento)))
            if fecha < hoy:
                raise ValueError(f"el seguimiento del {fecha.isoformat()} ya ha pasado")
        return _cambiar(conn, persona, excepcion, {
            "estado": ESPERANDO, "esperando_a": quien, "fecha_seguimiento": fecha.isoformat(),
        }, tipo="excepcion_esperando", motivo=(persona.motivo or "").strip() or None,
            datos=datos)


def bloqueos_abiertos(conn: sqlite3.Connection, excepcion_id: int) -> list[sqlite3.Row]:
    """Los hallazgos de la excepcion que bloquean y siguen abiertos sin anular."""
    return conn.execute(
        "SELECT h.* FROM excepcion_hallazgo AS eh JOIN hallazgo AS h ON h.id = eh.hallazgo_id "
        "WHERE eh.excepcion_id = ? AND h.severidad = 'bloqueo' AND h.estado = 'abierto' "
        "ORDER BY h.id", (excepcion_id,)).fetchall()


def resolver(conn: sqlite3.Connection, persona: Persona, excepcion_id: int, *,
             resolucion: str, notas: str, rev: int | None = None,
             datos: dict[str, Any] | None = None) -> int:
    """Da la excepcion por resuelta, con su resolucion y sus notas.

    No se puede mientras un hallazgo suyo que bloquea siga abierto sin
    anular: o se corrige el dato, o se anula (si la regla lo admite). Los
    hallazgos que retienen pueden quedar abiertos: resolver dice que el caso
    esta tratado, no que el hallazgo haya desaparecido, y sigue contando para
    la prioridad de la factura.
    """
    notas = (notas or "").strip()
    with orden_auditada(conn):
        _exigir(conn, persona, "resolver una excepcion")
        excepcion = _fila(conn, excepcion_id)
        _comprobar_rev(excepcion, rev)
        _comprobar_transicion(excepcion, RESUELTA)
        codigo = str(getattr(resolucion, "value", resolucion))
        if codigo not in ResolucionExcepcion.valores():
            raise ValueError(f"la resolucion es una de {', '.join(ResolucionExcepcion.valores())}")
        if not notas:
            raise FaltaMotivo("resolver una excepcion pide unas notas que digan como acabo")
        bloqueos = bloqueos_abiertos(conn, excepcion_id)
        if bloqueos:
            raise BloqueoAbierto(
                "no se resuelve: bloquea " + ", ".join(f"{h['regla']} (hallazgo {h['id']})"
                                                       for h in bloqueos)
                + ", abierto y sin anular")
        hasta = conn.execute("SELECT coalesce(max(id), 0) FROM hallazgo_evento").fetchone()[0]
        return _cambiar(conn, persona, excepcion, {
            "estado": RESUELTA, "resolucion": codigo, "resolucion_notas": notas,
            "resuelta_en": marca(reloj_de(conn).ahora()), "resuelta_por": persona.usuario_id,
            "hallazgo_evento_hasta": int(hasta),
        }, tipo="excepcion_resuelta", motivo=notas, datos=datos)


# ------------------------------------------------------------ lectura y verificacion

def hallazgos_de(conn: sqlite3.Connection, excepcion_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT h.* FROM excepcion_hallazgo AS eh JOIN hallazgo AS h ON h.id = eh.hallazgo_id "
        "WHERE eh.excepcion_id = ? ORDER BY h.id", (excepcion_id,)).fetchall()


def sin_resolver(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    marcas = ", ".join("?" * len(ESTADOS_EXCEPCION_ABIERTA))
    return conn.execute(f"SELECT * FROM excepcion WHERE estado IN ({marcas}) ORDER BY id",
                        sorted(ESTADOS_EXCEPCION_ABIERTA)).fetchall()


def verificar(conn: sqlite3.Connection) -> list[str]:
    """Que cada excepcion sea lo que dice su historia, sin fiarse de los disparadores.

    Cada columna vale lo que dejo su ultimo cambio_campo y la rev es la del
    ultimo cambio; cada union con un hallazgo esta en los datos del evento
    que la hizo.
    """
    problemas: list[str] = []
    ultimos: dict[tuple[int, str], str] = {}
    revs: dict[int, int] = {}
    for fila_id, campo, rev, valor in conn.execute(
            "SELECT fila_id, campo, rev, valor_nuevo FROM cambio_campo WHERE tabla = ? "
            "ORDER BY id", (TABLA,)):
        ultimos[(fila_id, campo)] = valor
        revs[fila_id] = max(revs.get(fila_id, 0), rev)
    existentes = set()
    for fila in conn.execute("SELECT * FROM excepcion ORDER BY id"):
        existentes.add(fila["id"])
        if fila["id"] not in revs:
            problemas.append(f"la excepcion {fila['id']} no tiene historia: se ha metido por detras")
            continue
        if fila["rev"] != revs[fila["id"]]:
            problemas.append(f"la excepcion {fila['id']}: rev {fila['rev']} y su ultimo cambio "
                             f"es la {revs[fila['id']]}")
        for columna in COLUMNAS:
            actual = None if fila[columna] is None else json_canonico(fila[columna])
            esperado = ultimos.get((fila["id"], columna))
            if esperado == "null":
                esperado = None
            if actual != esperado:
                problemas.append(f"la excepcion {fila['id']}: {columna} no es lo que dejo su "
                                 "ultimo cambio (se ha modificado por detras)")
    for fila_id in sorted(set(revs) - existentes):
        problemas.append(f"la excepcion {fila_id} tiene historia y ya no existe: se ha borrado")

    datos = {f["id"]: f["datos_json"] for f in conn.execute(
        "SELECT id, datos_json FROM evento WHERE tipo = 'excepciones_sincronizadas'")}
    for union in conn.execute("SELECT * FROM excepcion_hallazgo ORDER BY id"):
        texto = datos.get(union["evento_id"])
        vinculos = json.loads(texto).get("vinculos", []) if texto else []
        if [union["excepcion_id"], union["hallazgo_id"]] not in vinculos:
            problemas.append(f"la union {union['id']} de la excepcion {union['excepcion_id']} "
                             f"con el hallazgo {union['hallazgo_id']} no la registro su evento")
    return problemas
