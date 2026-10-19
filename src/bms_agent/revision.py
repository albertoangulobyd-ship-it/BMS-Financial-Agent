"""La revision de una factura por una persona (spec §7, Review, y §15).

Una persona con revisar_factura mira una factura y la da por revisada, o la
devuelve con una nota. La revision guarda la **huella del contenido** que
vio: los valores actuales de la factura y de sus lineas, imputaciones,
desglose, referencias y relaciones; la fuente de cada campo, su valor
automatico, si es dudoso y si esta verificado; y la evidencia de sus
hallazgos pendientes. Cualquier cambio despues (una correccion, una
extraccion nueva, un hallazgo que se abre por un maestro o un planning que
cambio) da otra huella, y la revision deja de valer sin tocarla: la tabla es
de solo escritura.

El estado de revision de una factura:

- revisada: su ultima revision es "revisada" y su huella es la de ahora;
- necesita revision: tiene un hallazgo que bloquea o retiene pendiente y
  sin anular, un campo critico dudoso sin verificar, un cambio manual sin
  resolver, o su ultima revision fue devuelta o ya no vale;
- sin revisar: nada de lo anterior y nadie la ha revisado.

Solo se marca revisada si no tiene nada de lo que pide revision. Quien la
revisa no puede ser quien cambio a mano lo que revisa (o anulo uno de sus
hallazgos) si hay otra persona con revisar_factura; si es la unica, se
permite y queda marcada como autorrevisada (politica "si hay dos").

Una factura limpia es "sin objeciones del sistema", nunca "aprobada":
revisar no aprueba un pago, y que el sistema no vea nada no es lo mismo que
que una persona lo haya mirado.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from . import campos
from .almacen import reloj_de
from .auditoria import registrar
from .campos import Conflicto, FaltaMotivo, Persona
from .dominio import (
    ESTADOS_PENDIENTES,
    EstadoRevision,
    FUENTES_MANUALES,
    Permiso,
    ResultadoRevision,
    Severidad,
)
from .permisos import AUTORREVISADO, DENEGADO, SeparacionDeFunciones, exigir, orden_auditada, separacion
from .reloj import marca

REVISADA = EstadoRevision.REVISADA.value
NECESITA_REVISION = EstadoRevision.NECESITA_REVISION.value
SIN_REVISAR = EstadoRevision.SIN_REVISAR.value

TABLAS_DE_FACTURA: tuple[str, ...] = (
    "factura", "factura_linea", "factura_imputacion", "factura_iva", "factura_referencia",
    "factura_cita")
_PIDEN_REVISION = frozenset({Severidad.BLOQUEO.value, Severidad.RETENCION.value})
_LOTE = 500

ETIQUETA_LIMPIA = "Sin objeciones del sistema"


class NoRevisable(ValueError):
    """La factura tiene algo pendiente que pide revision: se arregla antes de darla por revisada."""

    codigo = "no_revisable"


def _filas(conn: sqlite3.Connection, sql: str, parametros: Sequence[Any] = ()) -> list[tuple]:
    cursor = conn.cursor()
    cursor.row_factory = None
    return cursor.execute(sql, tuple(parametros)).fetchall()


def _en_lotes(conn: sqlite3.Connection, sql: str, ids: Sequence[int] | None,
              columna: str) -> list[tuple]:
    """Una consulta para todas las facturas, o por lotes para unas pocas."""
    if ids is None:
        return _filas(conn, sql + " ORDER BY id")
    salida: list[tuple] = []
    for inicio in range(0, len(ids), _LOTE):
        lote = ids[inicio:inicio + _LOTE]
        marcas = ", ".join("?" * len(lote))
        salida.extend(_filas(conn, f"{sql} WHERE {columna} IN ({marcas}) ORDER BY id", lote))
    return salida


# ------------------------------------------------------------ huella del contenido

def contenidos(conn: sqlite3.Connection,
               factura_ids: Iterable[int] | None = None) -> dict[int, str]:
    """La huella del contenido de cada factura (todas, o las pedidas).

    Se lee de golpe, tabla a tabla y en orden de id, y se hashea por factura:
    asi la pasada del motor la puede rehacer para todo el historico. No
    entran las notas (comentar no cambia lo que se reviso) ni las
    excepciones (son el trabajo, no el contenido).
    """
    ids = None if factura_ids is None else sorted(set(factura_ids))
    partes: dict[int, list[Any]] = defaultdict(list)
    de_factura: dict[tuple[str, int], int] = {}
    for tabla in TABLAS_DE_FACTURA:
        columnas = ", ".join(campos.REGISTRO[tabla])
        columna = "id" if tabla == "factura" else "factura_id"
        for fila in _en_lotes(conn, f"SELECT {columna}, id, rev, {columnas} FROM {tabla}", ids,
                              columna):
            factura_id = fila[0]
            de_factura[(tabla, fila[1])] = factura_id
            partes[factura_id].append([tabla, *fila[1:]])
    sql = ("SELECT fila_id, campo, fuente, valor_automatico, dudoso, rev_campo, verificado_rev "
           "FROM procedencia_campo WHERE tabla = ?")
    for tabla in TABLAS_DE_FACTURA:
        if ids is None:
            filas = _filas(conn, sql + " ORDER BY fila_id, campo", (tabla,))
        else:
            propias = sorted(f for t, f in de_factura if t == tabla)
            filas = []
            for inicio in range(0, len(propias), _LOTE):
                lote = propias[inicio:inicio + _LOTE]
                filas.extend(_filas(
                    conn, f"{sql} AND fila_id IN ({', '.join('?' * len(lote))}) "
                          "ORDER BY fila_id, campo", (tabla, *lote)))
        for fila_id, campo, fuente, automatico, dudoso, rev_campo, verificado_rev in filas:
            factura_id = de_factura.get((tabla, fila_id))
            if factura_id is not None:
                partes[factura_id].append(["procedencia", tabla, fila_id, campo, fuente,
                                           automatico, dudoso, verificado_rev == rev_campo])
    columnas = ", ".join(campos.REGISTRO["factura_relacion"])
    for fila in _filas(conn, f"SELECT id, rev, {columnas} FROM factura_relacion ORDER BY id"):
        relacion = dict(zip(("id", "rev", *campos.REGISTRO["factura_relacion"]), fila))
        for factura_id in {relacion["origen_id"], relacion["destino_id"]}:
            if factura_id in partes:
                partes[factura_id].append(["factura_relacion", *fila])
    for factura_id, clave, huella, estado, anulacion in pendientes_por_factura(conn):
        if factura_id in partes:
            partes[factura_id].append(["hallazgo", clave, huella, estado, anulacion])
    return {
        factura_id: hashlib.sha256(json.dumps(
            lista, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        for factura_id, lista in partes.items()
    }


def pendientes_por_factura(conn: sqlite3.Connection) -> list[tuple[int, str, str, str, Any]]:
    """(factura, clave, huella, estado, ultima anulacion) de cada hallazgo pendiente, por
    cada factura que cubre. La anulacion entra en la huella del contenido: anular otra vez
    (otro plazo, otra persona) tambien es un cambio despues de revisar."""
    marcas = ", ".join("?" * len(ESTADOS_PENDIENTES))
    estados = sorted(ESTADOS_PENDIENTES)
    anulacion = "(SELECT max(id) FROM anulacion WHERE hallazgo_id = h.id)"
    return _filas(
        conn,
        f"SELECT h.factura_id, h.clave, h.huella, h.estado, {anulacion} FROM hallazgo AS h "
        f"WHERE h.estado IN ({marcas}) AND h.factura_id IS NOT NULL "
        f"UNION SELECT o.fila_id, h.clave, h.huella, h.estado, {anulacion} "
        f"FROM hallazgo_objetivo AS o JOIN hallazgo AS h ON h.id = o.hallazgo_id "
        f"WHERE o.tabla = 'factura' AND h.estado IN ({marcas}) "
        f"ORDER BY 1, 2", (*estados, *estados))


def huella_contenido(conn: sqlite3.Connection, factura_id: int) -> str:
    huellas = contenidos(conn, [factura_id])
    if factura_id not in huellas:
        raise LookupError(f"no hay factura {factura_id}")
    return huellas[factura_id]


# ------------------------------------------------------------ campos por resolver

@dataclass
class CamposFactura:
    """Lo que dicen las procedencias de los campos de una factura (y de sus hijas).

    `sin_resolver`: un valor manual distinto del ultimo automatico sin
    verificar (M1), o una edicion de una persona que hizo desaparecer un
    hallazgo (lo cerro o lo dejo desaparecido) y que nadie ha verificado desde
    entonces: "editar hasta que el aviso se vaya" lo tiene que ver otra
    persona (spec §7). Un campo que cambio otra vez despues ya no es esa
    edicion. `dudosos`: los campos criticos dudosos sin verificar (Q2).
    `criticos_verificados`: una persona verifico cada campo critico con valor
    de la cabecera.
    """

    editada: bool = False
    suplementada: bool = False
    corregida: bool = False
    sin_resolver: set[tuple[str, int, str]] = field(default_factory=set)
    dudosos: set[tuple[str, int, str]] = field(default_factory=set)
    criticos_verificados: bool = False


def estado_de_campos(conn: sqlite3.Connection) -> dict[int, CamposFactura]:
    """Por factura, sus marcas de edicion, sus cambios sin resolver y sus campos dudosos.

    Una sola lectura de las procedencias que importan (lo que puso una
    persona, lo dudoso y lo verificado): la pasada del motor lo hace para
    todo el historico en cada orden, y casi todo lo extraido no es nada de eso.
    """
    salida: dict[int, CamposFactura] = defaultdict(CamposFactura)
    manuales: dict[tuple[str, int, str], tuple[int, int, int | None]] = {}
    verificados: dict[int, int] = defaultdict(int)
    criticos = {t: frozenset(campos.criticos(t)) for t in TABLAS_DE_FACTURA}
    for tabla in TABLAS_DE_FACTURA:
        columna = "id" if tabla == "factura" else "factura_id"
        for (factura_id, fila_id, campo, fuente, actual, automatico, dudoso, rev_campo,
             verificado_rev) in _filas(
                conn, f"SELECT t.{columna}, p.fila_id, p.campo, p.fuente, p.valor_actual, "
                      "p.valor_automatico, p.dudoso, p.rev_campo, p.verificado_rev "
                      f"FROM procedencia_campo AS p JOIN {tabla} AS t ON t.id = p.fila_id "
                      "WHERE p.tabla = ? AND (p.fuente IN ('manual_entrada', 'manual_correccion') "
                      "OR p.dudoso = 1 OR p.verificado_rev IS NOT NULL)", (tabla,)):
            verificado = verificado_rev is not None and verificado_rev == rev_campo
            estado_ = salida[factura_id]
            clave = (tabla, fila_id, campo)
            if fuente in FUENTES_MANUALES:
                estado_.editada = True
                if fuente == "manual_entrada":
                    estado_.suplementada = True
                else:
                    estado_.corregida = True
                manuales[clave] = (factura_id, rev_campo, verificado_rev)
                if automatico is not None and automatico != actual and not verificado:
                    estado_.sin_resolver.add(clave)
            elif dudoso and campo in criticos[tabla] and not verificado and tabla in (
                    "factura", "factura_linea"):
                estado_.dudosos.add(clave)
            if tabla == "factura" and verificado and campo in criticos["factura"]:
                verificados[factura_id] += 1
    marcas = ", ".join("?" * len(TABLAS_DE_FACTURA))
    for tabla, fila_id, campo, rev in _filas(
            conn,
            "SELECT DISTINCT c.tabla, c.fila_id, c.campo, c.rev FROM hallazgo_evento AS he "
            "JOIN hallazgo AS h ON h.id = he.hallazgo_id "
            "JOIN evento AS e ON e.id = he.causa_evento_id "
            "JOIN cambio_campo AS c ON c.evento_id = e.id "
            "WHERE he.tipo IN ('cerrado_automatico', 'desaparecido') AND e.usuario_id IS NOT NULL "
            f"AND c.tabla IN ({marcas}) AND c.fuente_nueva IN ('manual_entrada', 'manual_correccion') "
            "AND (c.factura_id = h.factura_id OR c.factura_id IN (SELECT fila_id FROM "
            "hallazgo_objetivo WHERE hallazgo_id = h.id AND tabla = 'factura'))",
            TABLAS_DE_FACTURA):
        manual = manuales.get((tabla, fila_id, campo))
        if manual is not None:
            factura_id, rev_campo, verificado_rev = manual
            if rev_campo == rev and verificado_rev != rev_campo:
                salida[factura_id].sin_resolver.add((tabla, fila_id, campo))
    if verificados:
        nombres = sorted(criticos["factura"])
        ids = sorted(verificados)
        for inicio in range(0, len(ids), _LOTE):
            lote = ids[inicio:inicio + _LOTE]
            for factura_id, con_valor in _filas(
                    conn, f"SELECT fila_id, count(*) FROM procedencia_campo WHERE tabla = 'factura' "
                          f"AND campo IN ({', '.join('?' * len(nombres))}) "
                          "AND valor_actual IS NOT NULL "
                          f"AND fila_id IN ({', '.join('?' * len(lote))}) GROUP BY fila_id",
                    (*nombres, *lote)):
                salida[factura_id].criticos_verificados = con_valor == verificados[factura_id]
    return dict(salida)


def ediciones_sin_resolver(conn: sqlite3.Connection) -> dict[int, set[tuple[str, int, str]]]:
    """Por factura, los campos con un cambio manual sin resolver (ver CamposFactura)."""
    return {f: c.sin_resolver for f, c in estado_de_campos(conn).items() if c.sin_resolver}


def dudosos_sin_verificar(conn: sqlite3.Connection) -> dict[int, set[tuple[str, int, str]]]:
    """Por factura, los campos criticos dudosos que nadie ha verificado (Q2)."""
    return {f: c.dudosos for f, c in estado_de_campos(conn).items() if c.dudosos}


# ------------------------------------------------------------ estado

@dataclass(frozen=True)
class Ultima:
    """La ultima revision de una factura."""

    id: int
    resultado: str
    huella_contenido: str
    autorrevisada: bool
    usuario_id: int
    en: str
    nota: str | None


def ultimas(conn: sqlite3.Connection) -> dict[int, Ultima]:
    return {f[1]: Ultima(f[0], f[2], f[3], bool(f[4]), f[5], f[6], f[7]) for f in _filas(
        conn, "SELECT r.id, r.factura_id, r.resultado, r.huella_contenido, r.autorrevisada, "
              "r.usuario_id, r.en, r.nota FROM revision AS r WHERE r.id = (SELECT max(id) "
              "FROM revision WHERE factura_id = r.factura_id)")}


def estado(ultima: Ultima | None, huella_actual: str | None, pide_revision: bool) -> str:
    """revisada, necesita_revision o sin_revisar (ver el docstring del modulo)."""
    if (ultima is not None and ultima.resultado == ResultadoRevision.REVISADA.value
            and ultima.huella_contenido == huella_actual):
        return REVISADA
    if pide_revision or ultima is not None:
        return NECESITA_REVISION
    return SIN_REVISAR


def etiqueta_sistema(pendientes: int, aceptados: int, sin_datos: int,
                     campos_pendientes: int = 0) -> str:
    """Lo que dice el sistema de una factura. Nunca "aprobada"."""
    if pendientes == 0 and campos_pendientes == 0:
        if sin_datos:
            return (f"Sin objeciones en lo comprobado; {sin_datos} "
                    f"{'regla' if sin_datos == 1 else 'reglas'} sin datos")
        return ETIQUETA_LIMPIA
    partes = []
    if pendientes - aceptados > 0:
        n = pendientes - aceptados
        partes.append(f"{n} {'objeción' if n == 1 else 'objeciones'} del sistema")
    if aceptados:
        partes.append(f"{aceptados} {'anulada' if aceptados == 1 else 'anuladas'} por una persona")
    if campos_pendientes:
        partes.append(f"{campos_pendientes} {'campo' if campos_pendientes == 1 else 'campos'} "
                      "por verificar")
    return "; ".join(partes)


def lo_que_pide_revision(conn: sqlite3.Connection, factura_id: int) -> list[str]:
    """Lo que impide dar la factura por revisada (y la deja en necesita revision)."""
    motivos = []
    marcas = ", ".join("?" * len(ESTADOS_PENDIENTES))
    for fila in conn.execute(
            f"SELECT regla, titulo, severidad, estado FROM hallazgo WHERE estado IN ({marcas}) "
            "AND (factura_id = ? OR id IN (SELECT hallazgo_id FROM hallazgo_objetivo "
            "WHERE tabla = 'factura' AND fila_id = ?)) ORDER BY id",
            (*sorted(ESTADOS_PENDIENTES), factura_id, factura_id)):
        if fila["severidad"] in _PIDEN_REVISION and fila["estado"] != "aceptado":
            motivos.append(f"{fila['regla']} {fila['titulo']} ({fila['estado']})")
    campos_ = estado_de_campos(conn).get(factura_id, CamposFactura())
    dudosos = campos_.dudosos
    if dudosos:
        motivos.append(f"{len(dudosos)} campo(s) dudoso(s) sin verificar: "
                       + ", ".join(f"{t}.{c}" for t, _f, c in sorted(dudosos)))
    editados = campos_.sin_resolver
    if editados:
        motivos.append(f"{len(editados)} cambio(s) manual(es) sin resolver: "
                       + ", ".join(f"{t}.{c}" for t, _f, c in sorted(editados)))
    return motivos


def autores(conn: sqlite3.Connection, factura_id: int) -> set[int]:
    """Quien puso a mano algo de lo que se revisa, o anulo un hallazgo suyo que sigue aceptado."""
    personas: set[int] = set()
    for tabla in TABLAS_DE_FACTURA:
        columna = "id" if tabla == "factura" else "factura_id"
        personas.update(f[0] for f in _filas(
            conn, f"SELECT DISTINCT p.cambiado_por FROM procedencia_campo AS p "
                  f"JOIN {tabla} AS t ON t.id = p.fila_id WHERE p.tabla = ? AND t.{columna} = ? "
                  "AND p.fuente IN ('manual_entrada', 'manual_correccion')", (tabla, factura_id)))
    personas.update(f[0] for f in _filas(
        conn, "SELECT a.usuario_id FROM anulacion AS a JOIN hallazgo AS h ON h.id = a.hallazgo_id "
              "WHERE h.estado = 'aceptado' AND a.id = (SELECT max(id) FROM anulacion "
              "WHERE hallazgo_id = h.id) AND (h.factura_id = ? OR h.id IN (SELECT hallazgo_id "
              "FROM hallazgo_objetivo WHERE tabla = 'factura' AND fila_id = ?))",
        (factura_id, factura_id)))
    return personas


# ------------------------------------------------------------ ordenes

def _existe(conn: sqlite3.Connection, factura_id: int) -> None:
    if conn.execute("SELECT 1 FROM factura WHERE id = ?", (factura_id,)).fetchone() is None:
        raise LookupError(f"no hay factura {factura_id}")


def _registrar(conn: sqlite3.Connection, persona: Persona, factura_id: int, resultado: str,
               huella: str, autorrevisada: bool, nota: str | None,
               datos: dict[str, Any] | None) -> int:
    """El evento de la revision con su foto, y despues la fila (la base exige ese orden)."""
    fila = {"factura_id": factura_id, "resultado": resultado, "huella_contenido": huella,
            "autorrevisada": int(autorrevisada), "usuario_id": persona.usuario_id,
            "en": marca(reloj_de(conn).ahora()), "nota": nota}
    evento = registrar(conn, tipo="revision_registrada", actor=persona.usuario_id,
                       usuario_id=persona.usuario_id, tabla="factura", fila_id=factura_id,
                       factura_id=factura_id, motivo=nota, peticion_id=persona.peticion_id,
                       datos={**(datos or {}), "fila": fila})
    return int(conn.execute(
        "INSERT INTO revision (factura_id, resultado, huella_contenido, autorrevisada, "
        "usuario_id, en, nota, evento_id) VALUES (:factura_id, :resultado, :huella_contenido, "
        ":autorrevisada, :usuario_id, :en, :nota, :evento_id)",
        {**fila, "evento_id": evento}).lastrowid)


def marcar_revisada(conn: sqlite3.Connection, persona: Persona, factura_id: int, *,
                    huella: str | None = None, nota: str | None = None,
                    datos: dict[str, Any] | None = None) -> int:
    """Da la factura por revisada. Devuelve el id de la revision.

    `huella` es la que vio quien revisa: si la factura cambio desde entonces,
    se niega (Conflicto) en vez de dar por revisado algo que nadie ha visto.
    """
    with orden_auditada(conn):
        exigir(conn, persona.usuario_id, Permiso.REVISAR_FACTURA.value,
               accion="marcar una factura como revisada")
        _existe(conn, factura_id)
        actual = huella_contenido(conn, factura_id)
        if huella is not None and huella != actual:
            raise Conflicto(f"la factura {factura_id} cambio desde que se cargo: vuelve a mirarla")
        pendiente = lo_que_pide_revision(conn, factura_id)
        if pendiente:
            raise NoRevisable("antes de darla por revisada: " + "; ".join(pendiente))
        autorrevisada = False
        if persona.usuario_id in autores(conn, factura_id):
            decision = separacion(conn, Permiso.REVISAR_FACTURA.value, persona.usuario_id,
                                  persona.usuario_id)
            if decision == DENEGADO:
                raise SeparacionDeFunciones(
                    persona.usuario_id, Permiso.REVISAR_FACTURA.value,
                    "esta persona cambio o anulo algo de la factura y hay otra con "
                    "revisar_factura: la revisa la otra", "marcar una factura como revisada")
            autorrevisada = decision == AUTORREVISADO
        texto = (nota or "").strip() or None
        return _registrar(conn, persona, factura_id, ResultadoRevision.REVISADA.value, actual,
                          autorrevisada, texto, datos)


def devolver(conn: sqlite3.Connection, persona: Persona, factura_id: int, *, nota: str,
             huella: str | None = None, datos: dict[str, Any] | None = None) -> int:
    """Devuelve la factura: queda pidiendo revision, con la nota que dice por que."""
    texto = (nota or "").strip()
    with orden_auditada(conn):
        exigir(conn, persona.usuario_id, Permiso.REVISAR_FACTURA.value,
               accion="devolver una factura")
        _existe(conn, factura_id)
        if not texto:
            raise FaltaMotivo("devolver una factura pide una nota que diga por que")
        actual = huella_contenido(conn, factura_id)
        if huella is not None and huella != actual:
            raise Conflicto(f"la factura {factura_id} cambio desde que se cargo: vuelve a mirarla")
        return _registrar(conn, persona, factura_id, ResultadoRevision.DEVUELTA.value, actual,
                          False, texto, datos)
