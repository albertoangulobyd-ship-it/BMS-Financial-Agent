"""Los hallazgos: lo que encuentra el motor de reglas, guardado con su historia.

Cada pasada (`recalcular`) evalua el catalogo entero sobre una instantanea
del almacen, rehace la cache de evaluaciones y compara los fallos con los
hallazgos que ya habia. Un hallazgo tiene dos cosas separadas:

- su **clave** (regla, objetivo y llave): quien es. No lleva valores, asi
  que un importe corregido no crea un hallazgo nuevo ni le quita su
  historia;
- su **huella** (los valores comparados, la fuente de cada campo que la
  regla lee y los parametros de la politica): que evidencia tiene. Una
  anulacion queda atada a la huella que acepto.

Lo que le pasa queda en hallazgo_evento, con el evento de auditoria que lo
causo (la edicion o la importacion que hizo aparecer, cambiar o desaparecer
la condicion):

- detectado, cambio_evidencia: aparece, o cambia su evidencia;
- desaparecido: la condicion de una regla pegajosa ya no se da. No se cierra
  sola: "editar hasta que el aviso se vaya" y tocar el maestro son justo los
  casos en que la condicion desaparece y el problema no; lo cierra una
  persona (`resolver`, resuelto);
- cerrado_automatico: la de una regla normal ya no se da, y se cierra;
- aceptado: una persona con anular_aviso lo anula (`anular`), con un motivo
  de al menos 10 caracteres; vale mientras la huella sea esa y no venza;
- reabierto: cambia la evidencia de uno aceptado, vence su anulacion o
  vuelve la condicion de uno cerrado, resuelto o desaparecido.

Un sin_datos no cierra nada: si la regla no ha podido mirar (un importe que
ahora no se lee), el hallazgo se queda como estaba.

La base exige lo mismo por su cuenta (migracion 0003): el estado y la huella
de un hallazgo son siempre los de su ultimo evento, una regla pegajosa no se
puede cerrar sola y una regla de la lista de la decision 12 no se anula.
"""

from __future__ import annotations

import gc
import json
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from . import __version__
from .almacen import reloj_de, transaccion, usuario_sistema
from .auditoria import registrar
from .campos import FaltaMotivo, Persona
from .dominio import (
    ESTADOS_PENDIENTES,
    EstadoHallazgo,
    MotivoEjecucion,
    Permiso,
    Severidad,
    TipoEventoHallazgo,
)
from .permisos import SeparacionDeFunciones, exigir, orden_auditada, personas_con
from .reglas import catalogo, motor
from .reglas import instantanea as instantaneas
from .reglas.base import FALLO, SIN_DATOS, Instantanea, Politica, Resultado
from .reloj import marca

ABIERTO = EstadoHallazgo.ABIERTO.value
ACEPTADO = EstadoHallazgo.ACEPTADO.value
DESAPARECIDO = EstadoHallazgo.DESAPARECIDO.value
CERRADO = EstadoHallazgo.CERRADO.value
RESUELTO = EstadoHallazgo.RESUELTO.value

DETECTADO = TipoEventoHallazgo.DETECTADO.value
CAMBIO_EVIDENCIA = TipoEventoHallazgo.CAMBIO_EVIDENCIA.value
EV_DESAPARECIDO = TipoEventoHallazgo.DESAPARECIDO.value
CERRADO_AUTOMATICO = TipoEventoHallazgo.CERRADO_AUTOMATICO.value
EV_RESUELTO = TipoEventoHallazgo.RESUELTO.value
EV_ACEPTADO = TipoEventoHallazgo.ACEPTADO.value
REABIERTO = TipoEventoHallazgo.REABIERTO.value

MOTIVO_MINIMO = 10
# Una anulacion de un importe de 10.000 euros o mas pide segunda firma (§3, decision 12).
IMPORTE_SEGUNDA_FIRMA_CENT = 1_000_000

_TAMANO_LOTE = 500


class NoAnulable(ValueError):
    """La regla del hallazgo no se puede anular: se corrige el dato o se resuelve el caso."""


class EstadoNoValido(ValueError):
    """La orden no tiene sentido en el estado en que esta el hallazgo."""


@dataclass(frozen=True)
class Transicion:
    """Lo que le paso a un hallazgo en una pasada o en una orden."""

    hallazgo_id: int
    clave: str
    regla: str
    factura_id: int | None
    tipo: str
    estado_anterior: str | None
    estado: str
    causa_evento_id: int | None
    nota: str | None = None


@dataclass
class Diferencia:
    """Lo que cambio con una pasada: resultados, hallazgos que se mueven y lo pendiente."""

    ejecucion_id: int | None = None
    simulada: bool = False
    evaluaciones: dict[str, int] = field(default_factory=dict)
    transiciones: list[Transicion] = field(default_factory=list)
    retenidos: list[str] = field(default_factory=list)
    pendientes: dict[str, int] = field(default_factory=dict)

    def de_tipo(self, *tipos: str) -> list[Transicion]:
        return [t for t in self.transiciones if t.tipo in tipos]

    def resumen(self) -> dict[str, Any]:
        return {
            "evaluaciones": dict(sorted(self.evaluaciones.items())),
            "transiciones": dict(sorted(Counter(t.tipo for t in self.transiciones).items())),
            "retenidos": len(self.retenidos),
            "pendientes": dict(sorted(self.pendientes.items())),
        }


class _Simulacion(Exception):
    def __init__(self, diferencia: Diferencia) -> None:
        super().__init__("simulacion")
        self.diferencia = diferencia


def _filas(conn: sqlite3.Connection, sql: str, parametros: Sequence[Any] = ()) -> list[tuple]:
    cursor = conn.cursor()
    cursor.row_factory = None
    return cursor.execute(sql, tuple(parametros)).fetchall()


def _lotes(valores: Sequence[Any]) -> Iterable[Sequence[Any]]:
    for inicio in range(0, len(valores), _TAMANO_LOTE):
        yield valores[inicio:inicio + _TAMANO_LOTE]


# ------------------------------------------------------------ huellas


def _fuentes(conn: sqlite3.Connection, detectados: Sequence[motor.Detectado],
             instantanea: Instantanea) -> dict[str, dict[str, str]]:
    """De que fuente sale cada campo que lee cada hallazgo, para su huella.

    Solo se leen las procedencias de las filas que tienen un fallo: son
    pocas, y asi una pasada sobre miles de facturas limpias no lee la
    procedencia de todas.
    """
    lineas = {f.id: [l.id for l in f.lineas] for f in instantanea.facturas}
    tramos = {f.id: [t.id for t in f.desglose] for f in instantanea.facturas}
    columnas_de = {r.id: motor.campos_de_fuente(r) for r in catalogo.CATALOGO}
    filas_de = {"factura": lambda f: [f], "factura_linea": lambda f: lineas.get(f, []),
                "factura_iva": lambda f: tramos.get(f, [])}
    pedidas: dict[str, set[int]] = defaultdict(set)
    for d in detectados:
        for tabla in columnas_de[d.regla]:
            for factura_id in d.facturas:
                pedidas[tabla].update(filas_de[tabla](factura_id))
    fuente: dict[tuple[str, int, str], str] = {}
    for tabla, ids in pedidas.items():
        for lote in _lotes(sorted(ids)):
            marcas = ", ".join("?" * len(lote))
            for fila_id, campo, valor in _filas(
                    conn, f"SELECT fila_id, campo, fuente FROM procedencia_campo "
                          f"WHERE tabla = ? AND fila_id IN ({marcas})", (tabla, *lote)):
                fuente[(tabla, fila_id, campo)] = valor
    salida: dict[str, dict[str, str]] = {}
    for d in detectados:
        propias: dict[str, str] = {}
        for tabla, columnas in columnas_de[d.regla].items():
            for factura_id in d.facturas:
                for fila_id in filas_de[tabla](factura_id):
                    for columna in columnas:
                        valor = fuente.get((tabla, fila_id, columna))
                        if valor is not None:
                            propias[f"{tabla}:{fila_id}:{columna}"] = valor
        salida[d.clave] = propias
    return salida


def calcular(conn: sqlite3.Connection, instantanea: Instantanea,
             resultados: Sequence[Resultado] | None = None) -> list[tuple[motor.Detectado, str]]:
    """Los hallazgos que dan los resultados, cada uno con su huella, en el orden de sus claves."""
    if resultados is None:
        resultados = motor.evaluar(instantanea)
    detectados = motor.agrupar(resultados, instantanea)
    fuentes = _fuentes(conn, detectados, instantanea)
    return [(d, motor.huella(catalogo.regla(d.regla), d.valores, fuentes[d.clave],
                             instantanea.politica)) for d in detectados]


# ------------------------------------------------------------ escritura


def _valores_json(valores: Any) -> str:
    return motor.canonico(dict(valores))


_CON_VALORES = frozenset({FALLO, SIN_DATOS})


def _escribir_evaluaciones(conn: sqlite3.Connection, ejecucion_id: int,
                           resultados: Sequence[Resultado]) -> int:
    """Pone la cache al dia escribiendo solo lo que cambia. Devuelve cuantas filas cambiaron.

    Lo habitual es que una orden cambie unas pocas facturas: reescribir las
    decenas de miles de evaluaciones de un historico entero costaria mas que
    evaluarlas. Una fila que no cambia conserva su ejecucion_id, que es la
    pasada desde la que el resultado es ese.

    Los valores comparados se guardan donde dicen algo que la factura no
    dice ya: en un fallo (la evidencia) y en un sin_datos (lo que faltaba).
    En un ok o un no_aplica son los valores actuales de la factura, que estan
    en sus tablas.
    """
    anteriores = {(t, f, r, c): (i, res, d, v) for i, t, f, r, c, res, d, v in _filas(
        conn, "SELECT id, tabla, fila_id, regla, clave, resultado, detalle, valores_json "
              "FROM evaluacion")}
    volcar = json.JSONEncoder(sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode
    nuevas, viejas = [], []
    for r in resultados:
        clave = r.clave_hallazgo
        valores = (volcar(dict(r.valores)) if r.valores and r.resultado in _CON_VALORES
                   else None)
        previa = anteriores.pop((r.tabla, r.fila_id, r.regla, clave), None)
        if previa is not None:
            if previa[1:] == (r.resultado, r.detalle, valores):
                continue
            viejas.append((previa[0],))
        nuevas.append((ejecucion_id, r.regla, r.tabla, r.fila_id, clave, r.resultado, r.detalle,
                       valores))
    viejas.extend((previa[0],) for previa in anteriores.values())
    conn.executemany("DELETE FROM evaluacion WHERE id = ?", viejas)
    conn.executemany(
        "INSERT INTO evaluacion (ejecucion_id, regla, tabla, fila_id, clave, resultado, detalle, "
        "valores_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", nuevas)
    return len(nuevas) + len(anteriores)


def _evento(conn: sqlite3.Connection, hallazgo_id: int, tipo: str, estado: str, huella: str, *,
            en: str, causa: int | None, ejecucion_id: int | None,
            usuario_id: int | None = None, nota: str | None = None) -> int:
    cursor = conn.execute(
        "INSERT INTO hallazgo_evento (hallazgo_id, tipo, estado, huella, causa_evento_id, "
        "ejecucion_id, usuario_id, en, nota) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (hallazgo_id, tipo, estado, huella, causa, ejecucion_id, usuario_id, en, nota))
    return int(cursor.lastrowid)


def _objetivos_de(d: motor.Detectado) -> set[tuple[str, int, str | None, str]]:
    return {(o.tabla, o.fila_id, o.campo, o.papel) for o in d.objetivos}


def _escribir_objetivos(conn: sqlite3.Connection, hallazgo_id: int,
                        objetivos: set[tuple[str, int, str | None, str]]) -> None:
    conn.execute("DELETE FROM hallazgo_objetivo WHERE hallazgo_id = ?", (hallazgo_id,))
    conn.executemany(
        "INSERT INTO hallazgo_objetivo (hallazgo_id, tabla, fila_id, campo, papel) "
        "VALUES (?, ?, ?, ?, ?)",
        [(hallazgo_id, *o) for o in sorted(objetivos, key=lambda o: (o[0], o[1], o[2] or ""))])


@dataclass(frozen=True)
class _Previo:
    id: int
    clave: str
    regla: str
    huella: str
    estado: str
    pegajosa: int
    tabla: str
    fila_id: int
    factura_id: int | None
    datos: tuple            # lo descriptivo, para no reescribir lo que no cambia


_COLUMNAS_DATOS = ("regla_version", "tabla", "fila_id", "factura_id", "severidad", "pegajosa",
                   "anulable", "titulo", "detalle", "valores_json")


def _anulable(regla: Any, sentido: str | None) -> int:
    """Si el hallazgo se puede anular: lo dice el catalogo, y nunca la lista de la decision 12."""
    return int(regla.anulable_para(sentido) and not catalogo.nunca_anulable(regla.id, sentido))


def _vigente(anulaciones: Sequence[tuple], huella: str, hoy: date) -> tuple | None:
    """La anulacion que vale para esta huella hoy: la ultima con esa huella y sin vencer."""
    for fila in sorted(anulaciones, key=lambda a: a[0], reverse=True):
        _id, a_huella, hasta, _usuario, _evento_id, _en = fila
        if a_huella == huella and (hasta is None or date.fromisoformat(hasta) >= hoy):
            return fila
    return None


class _Pasada:
    """Una pasada del motor, con todo lo que necesita leido una vez."""

    def __init__(self, conn: sqlite3.Connection, *, motivo: str, usuario_id: int | None,
                 causa_evento_id: int | None, politica: Politica | None) -> None:
        self.conn = conn
        self.motivo = MotivoEjecucion(motivo).value
        self.usuario_id = usuario_id
        self.causa_evento_id = causa_evento_id
        reloj = reloj_de(conn)
        self.hoy = reloj.hoy()
        self.ahora = marca(reloj.ahora())
        self.politica = politica or Politica()
        self.diferencia = Diferencia()

    def ejecutar(self) -> Diferencia:
        conn = self.conn
        instantanea = instantaneas.construir(conn, hoy=self.hoy, politica=self.politica)
        resultados = motor.evaluar(instantanea)
        detectados = calcular(conn, instantanea, resultados)
        self.sentido = {f.id: f.sentido for f in instantanea.facturas}

        desde = _filas(conn, "SELECT coalesce(max(hasta_evento_id), 0) FROM ejecucion_reglas")[0][0]
        hasta = _filas(conn, "SELECT coalesce(max(id), 0) FROM evento")[0][0]
        self.ejecucion_id = int(conn.execute(
            "INSERT INTO ejecucion_reglas (motivo, hoy, iniciada_en, usuario_id, actor, "
            "version_codigo, catalogo_sha256, politica_sha256, hasta_evento_id, causa_evento_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (self.motivo, self.hoy.isoformat(), self.ahora, self.usuario_id,
             usuario_sistema(conn, "motor"), __version__, catalogo.sha256(),
             motor.sha256_politica(self.politica), hasta, self.causa_evento_id)).lastrowid)
        self.diferencia.ejecucion_id = self.ejecucion_id
        self.diferencia.evaluaciones = dict(Counter(r.resultado for r in resultados))
        _escribir_evaluaciones(conn, self.ejecucion_id, resultados)

        self.causas = dict(_filas(
            conn, "SELECT factura_id, max(evento_id) FROM cambio_campo "
                  "WHERE evento_id > ? AND factura_id IS NOT NULL GROUP BY factura_id", (desde,)))
        self.previos = {fila[1]: _Previo(*fila[:9], datos=tuple(fila[9:])) for fila in _filas(
            conn, "SELECT id, clave, regla, huella, estado, pegajosa, tabla, fila_id, factura_id, "
                  f"{', '.join(_COLUMNAS_DATOS)} FROM hallazgo")}
        self.anulaciones: dict[int, list[tuple]] = defaultdict(list)
        for fila in _filas(conn, "SELECT hallazgo_id, id, huella, vigente_hasta, usuario_id, "
                                 "evento_id, en FROM anulacion"):
            self.anulaciones[fila[0]].append(fila[1:])
        self.objetivos: dict[int, set[tuple]] = defaultdict(set)
        for hallazgo_id, *objetivo in _filas(
                conn, "SELECT hallazgo_id, tabla, fila_id, campo, papel FROM hallazgo_objetivo"):
            self.objetivos[hallazgo_id].add(tuple(objetivo))

        vistos: set[str] = set()
        sin_cambios: list[tuple] = []
        for d, huella in detectados:
            vistos.add(d.clave)
            previo = self.previos.get(d.clave)
            if previo is None:
                self._nuevo(d, huella)
            elif not self._seguir(previo, d, huella):
                sin_cambios.append((self.ahora, self.ejecucion_id, previo.id))
        conn.executemany("UPDATE hallazgo SET ultima_vez_en = ?, ultima_ejecucion_id = ? "
                         "WHERE id = ?", sin_cambios)
        self._desaparecidos(resultados, vistos)

        self.diferencia.pendientes = dict(_filas(
            conn, f"SELECT estado, count(*) FROM hallazgo WHERE estado IN "
                  f"({', '.join('?' * len(ESTADOS_PENDIENTES))}) GROUP BY estado",
            sorted(ESTADOS_PENDIENTES)))
        conn.execute("UPDATE ejecucion_reglas SET terminada_en = ?, resumen_json = ? WHERE id = ?",
                     (self.ahora, motor.canonico(self.diferencia.resumen()), self.ejecucion_id))
        return self.diferencia

    # -------------------------------------------------------- transiciones

    def _causa(self, facturas: Iterable[int | None]) -> int | None:
        """La ultima edicion o importacion que toco alguna de sus facturas desde la pasada previa.

        Si ninguna se toco (una pasada diaria, una anulacion que vence), la
        causa es la que dio quien lanzo la pasada, o ninguna.
        """
        causas = [self.causas[f] for f in facturas if f in self.causas]
        return max(causas) if causas else self.causa_evento_id

    def _anotar(self, hallazgo_id: int, clave: str, regla: str, factura_id: int | None,
                tipo: str, antes: str | None, estado: str, causa: int | None,
                nota: str | None = None) -> None:
        self.diferencia.transiciones.append(Transicion(
            hallazgo_id, clave, regla, factura_id, tipo, antes, estado, causa, nota))

    def _nuevo(self, d: motor.Detectado, huella: str) -> None:
        regla = catalogo.regla(d.regla)
        sentido = self.sentido.get(d.factura_id)
        hallazgo_id = int(self.conn.execute(
            "INSERT INTO hallazgo (clave, regla, regla_version, huella, tabla, fila_id, "
            "factura_id, severidad, calidad, ambito, pegajosa, anulable, titulo, detalle, "
            "valores_json, estado, primera_vez_en, ultima_vez_en, ultima_ejecucion_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (d.clave, regla.id, regla.version, huella, d.tabla, d.fila_id, d.factura_id,
             d.severidad, regla.calidad, regla.ambito, int(regla.pegajosa),
             _anulable(regla, sentido), regla.titulo, d.detalle, _valores_json(d.valores),
             ABIERTO, self.ahora, self.ahora, self.ejecucion_id)).lastrowid)
        _escribir_objetivos(self.conn, hallazgo_id, _objetivos_de(d))
        causa = self._causa(d.facturas)
        _evento(self.conn, hallazgo_id, DETECTADO, ABIERTO, huella, en=self.ahora, causa=causa,
                ejecucion_id=self.ejecucion_id)
        self._anotar(hallazgo_id, d.clave, regla.id, d.factura_id, DETECTADO, None, ABIERTO, causa)

    def _seguir(self, previo: _Previo, d: motor.Detectado, huella: str) -> bool:
        """Un hallazgo que ya existia y sigue dandose. Devuelve si hubo que tocarlo."""
        regla = catalogo.regla(d.regla)
        sentido = self.sentido.get(d.factura_id)
        vigente = _vigente(self.anulaciones.get(previo.id, ()), huella, self.hoy)
        destino = ACEPTADO if vigente is not None else ABIERTO
        cambia = huella != previo.huella
        tipo, nota, usuario, causa = None, None, None, self._causa(d.facturas)
        if previo.estado == ABIERTO:
            if destino == ACEPTADO:
                tipo, usuario, causa = EV_ACEPTADO, vigente[3], vigente[4]
                nota = f"vuelve la evidencia que se anulo el {vigente[5]}"
            elif cambia:
                tipo = CAMBIO_EVIDENCIA
        elif previo.estado == ACEPTADO:
            if destino == ACEPTADO and cambia:
                tipo, usuario, causa = EV_ACEPTADO, vigente[3], vigente[4]
                nota = f"la nueva evidencia es la que se anulo el {vigente[5]}"
            elif destino == ABIERTO:
                tipo = REABIERTO
                nota = "la evidencia cambio" if cambia else "la anulacion ha vencido"
        else:
            tipo = REABIERTO
            nota = "la condicion vuelve a darse"

        objetivos = _objetivos_de(d)
        cambian_objetivos = objetivos != self.objetivos.get(previo.id, set())
        datos = (regla.version, d.tabla, d.fila_id, d.factura_id, d.severidad, int(regla.pegajosa),
                 _anulable(regla, sentido), regla.titulo, d.detalle, _valores_json(d.valores))
        if tipo is None and not cambian_objetivos and datos == previo.datos:
            return False
        if tipo is not None:
            _evento(self.conn, previo.id, tipo, destino, huella, en=self.ahora, causa=causa,
                    ejecucion_id=self.ejecucion_id, usuario_id=usuario, nota=nota)
            self._anotar(previo.id, d.clave, regla.id, d.factura_id, tipo, previo.estado, destino,
                         causa, nota)
        self.conn.execute(
            "UPDATE hallazgo SET regla_version = ?, tabla = ?, fila_id = ?, factura_id = ?, "
            "severidad = ?, pegajosa = ?, anulable = ?, titulo = ?, detalle = ?, "
            "valores_json = ?, huella = ?, estado = ?, ultima_vez_en = ?, "
            "ultima_ejecucion_id = ? WHERE id = ?",
            (*datos, huella if tipo is not None else previo.huella,
             destino if tipo is not None else previo.estado, self.ahora, self.ejecucion_id,
             previo.id))
        if cambian_objetivos:
            _escribir_objetivos(self.conn, previo.id, objetivos)
        return True

    def _desaparecidos(self, resultados: Sequence[Resultado], vistos: set[str]) -> None:
        """Los hallazgos que esta pasada ya no da: se cierran, quedan desaparecidos o se retienen.

        Se retiene (no cambia nada) el que la regla no pudo mirar: su
        resultado es sin_datos, o lo es el de alguna de sus facturas.
        """
        perdidos = [(clave, previo) for clave, previo in sorted(self.previos.items())
                    if clave not in vistos and previo.estado in (ABIERTO, ACEPTADO)]
        if not perdidos:
            return
        reglas = {previo.regla for _c, previo in perdidos}
        por_clave = {r.clave_hallazgo: r.resultado for r in resultados
                     if r.regla in reglas and r.resultado != FALLO}
        sin_datos = {(r.regla, r.tabla, r.fila_id) for r in resultados
                     if r.regla in reglas and r.resultado == SIN_DATOS}
        for clave, previo in perdidos:
            filas = {(t, f) for t, f, _c, _p in self.objetivos.get(previo.id, ())}
            filas.add((previo.tabla, previo.fila_id))
            if (previo.regla not in catalogo.POR_ID
                    or por_clave.get(clave) == SIN_DATOS
                    or (clave not in por_clave
                        and any((previo.regla, t, f) in sin_datos for t, f in filas))):
                self.diferencia.retenidos.append(clave)
                continue
            facturas = {f for t, f in filas if t == "factura"}
            causa = self._causa(facturas)
            tipo, estado = ((EV_DESAPARECIDO, DESAPARECIDO) if previo.pegajosa
                            else (CERRADO_AUTOMATICO, CERRADO))
            _evento(self.conn, previo.id, tipo, estado, previo.huella, en=self.ahora, causa=causa,
                    ejecucion_id=self.ejecucion_id)
            self.conn.execute(
                "UPDATE hallazgo SET estado = ?, ultima_ejecucion_id = ? WHERE id = ?",
                (estado, self.ejecucion_id, previo.id))
            self._anotar(previo.id, clave, previo.regla, previo.factura_id, tipo, previo.estado,
                         estado, causa)


def recalcular(conn: sqlite3.Connection, *, motivo: str = MotivoEjecucion.MANUAL.value,
               usuario_id: int | None = None, causa_evento_id: int | None = None,
               simular: bool = False, politica: Politica | None = None) -> Diferencia:
    """Evalua todo el catalogo y pone al dia los hallazgos, en una transaccion.

    Se llama al final de cada orden que cambia algo que una regla lee (la
    ingesta, importar-out, la semilla), dentro de su transaccion, y una vez
    al dia con `bms-agent recalcular --diaria`. Con `simular` hace lo mismo y
    lo deshace: dice que cambiaria sin escribir nada.
    """
    with _sin_recolector():
        if simular:
            try:
                with transaccion(conn):
                    diferencia = _Pasada(conn, motivo=motivo, usuario_id=usuario_id,
                                         causa_evento_id=causa_evento_id,
                                         politica=politica).ejecutar()
                    raise _Simulacion(diferencia)
            except _Simulacion as simulacion:
                return replace(simulacion.diferencia, simulada=True)
        with transaccion(conn):
            return _Pasada(conn, motivo=motivo, usuario_id=usuario_id,
                           causa_evento_id=causa_evento_id, politica=politica).ejecutar()


@contextmanager
def _sin_recolector() -> Iterator[None]:
    """El recolector de ciclos de Python, parado mientras dura una pasada.

    Una pasada crea decenas de miles de tuplas que viven hasta el final, sin
    ningun ciclo; el recolector las recorre una y otra vez sin liberar nada y
    se lleva un tercio del tiempo. Se vuelve a poner como estaba al salir.
    """
    activo = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if activo:
            gc.enable()


# ------------------------------------------------------------ ordenes de personas


def _hallazgo(conn: sqlite3.Connection, hallazgo_id: int) -> sqlite3.Row:
    fila = conn.execute("SELECT * FROM hallazgo WHERE id = ?", (hallazgo_id,)).fetchone()
    if fila is None:
        raise LookupError(f"no hay hallazgo {hallazgo_id}")
    return fila


def _factura(conn: sqlite3.Connection, factura_id: int | None) -> sqlite3.Row | None:
    if factura_id is None:
        return None
    return conn.execute("SELECT sentido, base_cent, total_cent FROM factura WHERE id = ?",
                        (factura_id,)).fetchone()


def _fecha(valor: date | str | None) -> str | None:
    if valor is None:
        return None
    return (valor if isinstance(valor, date) else date.fromisoformat(str(valor))).isoformat()


def requiere_segunda_firma(conn: sqlite3.Connection, hallazgo: sqlite3.Row) -> bool:
    """Si anular este hallazgo pide la firma de una segunda persona.

    Cuando la regla lo pide (B2), cuando el hallazgo bloquea y cuando el
    importe es de 10.000 euros o mas (§3, decision 12). Solo se exige si hay
    otra persona con anular_aviso; si no, la anulacion entra como
    autoaprobada, y queda dicho.
    """
    regla = catalogo.POR_ID.get(hallazgo["regla"])
    factura = _factura(conn, hallazgo["factura_id"])
    importe = None
    if factura is not None:
        importe = (factura["base_cent"] if factura["base_cent"] is not None
                   else factura["total_cent"])
    return bool(
        (regla is not None and regla.segunda_firma)
        or hallazgo["severidad"] == Severidad.BLOQUEO.value
        or (importe is not None and abs(importe) >= IMPORTE_SEGUNDA_FIRMA_CENT))


def anular(conn: sqlite3.Connection, hallazgo_id: int, persona: Persona, *,
           vigente_hasta: date | str | None = None, segunda_firma: int | None = None) -> int:
    """Una persona con anular_aviso acepta la evidencia de ahora de un hallazgo. Devuelve su id.

    Vale mientras la huella del hallazgo sea la que se anula y, si se da
    `vigente_hasta`, hasta ese dia incluido. No se anula una regla que no lo
    admite (la lista de la decision 12 y las que el catalogo marca), ni un
    hallazgo que no este abierto o ya aceptado. El motivo es obligatorio, de
    al menos 10 caracteres: "ok" no explica nada a quien lo lea despues.
    """
    motivo = (persona.motivo or "").strip()
    with orden_auditada(conn):
        exigir(conn, persona.usuario_id, Permiso.ANULAR_AVISO.value, accion="anular un hallazgo")
        hallazgo = _hallazgo(conn, hallazgo_id)
        if hallazgo["estado"] not in (ABIERTO, ACEPTADO):
            raise EstadoNoValido(
                f"el hallazgo {hallazgo_id} esta {hallazgo['estado']}: solo se anula uno abierto")
        factura = _factura(conn, hallazgo["factura_id"])
        sentido = factura["sentido"] if factura is not None else None
        regla = catalogo.POR_ID.get(hallazgo["regla"])
        if (regla is None or not hallazgo["anulable"] or not regla.anulable_para(sentido)
                or catalogo.nunca_anulable(hallazgo["regla"], sentido)):
            raise NoAnulable(f"la regla {hallazgo['regla']} no se puede anular: hay que "
                             "corregir el dato o resolver el caso")
        if len(motivo) < MOTIVO_MINIMO:
            raise FaltaMotivo(f"anular un hallazgo pide un motivo de al menos {MOTIVO_MINIMO} "
                              "caracteres")
        hoy = reloj_de(conn).hoy()
        hasta = _fecha(vigente_hasta)
        if hasta is not None and hasta < hoy.isoformat():
            raise ValueError(f"una anulacion hasta el {hasta} ya habria vencido")
        en = marca(reloj_de(conn).ahora())
        autoaprobada = 0
        permiso = Permiso.ANULAR_AVISO.value
        if segunda_firma is not None:
            if segunda_firma == persona.usuario_id:
                raise SeparacionDeFunciones(
                    persona.usuario_id, permiso, "la segunda firma tiene que ser de otra persona",
                    "anular un hallazgo")
            exigir(conn, segunda_firma, permiso, accion="firmar en segundo lugar una anulacion")
        elif requiere_segunda_firma(conn, hallazgo):
            if any(p != persona.usuario_id for p in personas_con(conn, permiso)):
                raise SeparacionDeFunciones(
                    persona.usuario_id, permiso, "esta anulacion necesita la segunda firma de "
                    "otra persona con anular_aviso", "anular un hallazgo")
            autoaprobada = 1
        fila = {
            "hallazgo_id": hallazgo_id, "huella": hallazgo["huella"], "motivo": motivo,
            "usuario_id": persona.usuario_id, "en": en, "vigente_hasta": hasta,
            "segunda_firma_usuario_id": segunda_firma,
            "segunda_firma_en": en if segunda_firma is not None else None,
            "autoaprobada": autoaprobada,
        }
        evento = registrar(
            conn, tipo="hallazgo_anulado", actor=persona.usuario_id,
            usuario_id=persona.usuario_id, tabla="hallazgo", fila_id=hallazgo_id,
            factura_id=hallazgo["factura_id"], motivo=motivo, peticion_id=persona.peticion_id,
            datos={"fila": fila, "clave": hallazgo["clave"], "regla": hallazgo["regla"]})
        anulacion_id = int(conn.execute(
            "INSERT INTO anulacion (hallazgo_id, huella, motivo, usuario_id, en, vigente_hasta, "
            "segunda_firma_usuario_id, segunda_firma_en, autoaprobada, evento_id) "
            "VALUES (:hallazgo_id, :huella, :motivo, :usuario_id, :en, :vigente_hasta, "
            ":segunda_firma_usuario_id, :segunda_firma_en, :autoaprobada, :evento_id)",
            {**fila, "evento_id": evento}).lastrowid)
        _evento(conn, hallazgo_id, EV_ACEPTADO, ACEPTADO, hallazgo["huella"], en=en, causa=evento,
                ejecucion_id=None, usuario_id=persona.usuario_id, nota=motivo)
        conn.execute("UPDATE hallazgo SET estado = ? WHERE id = ?", (ACEPTADO, hallazgo_id))
    return anulacion_id


def resolver(conn: sqlite3.Connection, hallazgo_id: int, persona: Persona) -> int:
    """Una persona con resolver_aviso cierra un hallazgo cuya condicion ha desaparecido.

    Es la unica forma de cerrar uno de una regla pegajosa. Uno abierto no se
    resuelve: se corrige el dato (y entonces desaparece) o se anula.
    """
    motivo = (persona.motivo or "").strip()
    with orden_auditada(conn):
        exigir(conn, persona.usuario_id, Permiso.RESOLVER_AVISO.value,
               accion="cerrar un hallazgo cuya condicion ha desaparecido")
        hallazgo = _hallazgo(conn, hallazgo_id)
        if hallazgo["estado"] != DESAPARECIDO:
            raise EstadoNoValido(
                f"el hallazgo {hallazgo_id} esta {hallazgo['estado']}: solo se resuelve a mano "
                "uno cuya condicion ha desaparecido")
        if not motivo:
            raise FaltaMotivo("cerrar un hallazgo pide un motivo")
        en = marca(reloj_de(conn).ahora())
        evento = registrar(
            conn, tipo="hallazgo_resuelto", actor=persona.usuario_id,
            usuario_id=persona.usuario_id, tabla="hallazgo", fila_id=hallazgo_id,
            factura_id=hallazgo["factura_id"], motivo=motivo, peticion_id=persona.peticion_id,
            datos={"clave": hallazgo["clave"], "regla": hallazgo["regla"],
                   "huella": hallazgo["huella"]})
        evento_hallazgo = _evento(conn, hallazgo_id, EV_RESUELTO, RESUELTO, hallazgo["huella"],
                                  en=en, causa=evento, ejecucion_id=None,
                                  usuario_id=persona.usuario_id, nota=motivo)
        conn.execute("UPDATE hallazgo SET estado = ? WHERE id = ?", (RESUELTO, hallazgo_id))
    return evento_hallazgo


# ------------------------------------------------------------ lectura y verificacion


def historia(conn: sqlite3.Connection, hallazgo_id: int) -> list[dict[str, Any]]:
    """Los eventos de un hallazgo, en orden: la historia de resolucion del aviso."""
    return [dict(f) for f in conn.execute(
        "SELECT * FROM hallazgo_evento WHERE hallazgo_id = ? ORDER BY id", (hallazgo_id,))]


def pendientes(conn: sqlite3.Connection, factura_id: int | None = None) -> list[sqlite3.Row]:
    """Los hallazgos que siguen pidiendo a alguien (abiertos, aceptados y desaparecidos)."""
    marcas = ", ".join("?" * len(ESTADOS_PENDIENTES))
    sql = f"SELECT * FROM hallazgo WHERE estado IN ({marcas})"
    parametros: list[Any] = sorted(ESTADOS_PENDIENTES)
    if factura_id is not None:
        sql += (" AND (factura_id = ? OR id IN (SELECT hallazgo_id FROM hallazgo_objetivo "
                "WHERE tabla = 'factura' AND fila_id = ?))")
        parametros += [factura_id, factura_id]
    return conn.execute(sql + " ORDER BY id", parametros).fetchall()


def verificar(conn: sqlite3.Connection) -> list[str]:
    """Que cada hallazgo sea lo que dice su historia, sin fiarse de los disparadores.

    Cada hallazgo empieza con un evento detectado y su estado y su huella son
    los de su ultimo evento; lo que hizo una persona (aceptar, resolver)
    cuelga de un evento de auditoria suyo sobre ese hallazgo. Las anulaciones
    se comparan con la foto de su evento en almacen/evidencia.py.
    """
    problemas: list[str] = []
    eventos: dict[int, list[tuple]] = defaultdict(list)
    for fila in _filas(conn, "SELECT hallazgo_id, id, tipo, estado, huella, causa_evento_id, "
                             "usuario_id FROM hallazgo_evento ORDER BY id"):
        eventos[fila[0]].append(fila[1:])
    auditoria = {f[0]: f[1:] for f in _filas(
        conn, "SELECT id, tipo, usuario_id, tabla, fila_id FROM evento "
              "WHERE tipo IN ('hallazgo_anulado', 'hallazgo_resuelto')")}
    for hallazgo_id, clave, estado, huella in _filas(
            conn, "SELECT id, clave, estado, huella FROM hallazgo ORDER BY id"):
        historia_ = eventos.pop(hallazgo_id, [])
        if not historia_:
            problemas.append(f"el hallazgo {hallazgo_id} ({clave}) no tiene historia")
            continue
        if historia_[0][1] != DETECTADO:
            problemas.append(f"el hallazgo {hallazgo_id} no empieza con su deteccion")
        _id, _tipo, ultimo_estado, ultima_huella, _causa, _usuario = historia_[-1]
        if (estado, huella) != (ultimo_estado, ultima_huella):
            problemas.append(f"el hallazgo {hallazgo_id}: su estado o su huella no son los de su "
                             "ultimo evento (se ha modificado por detras)")
        for evento_id, tipo, _e, _h, causa, usuario in historia_:
            if usuario is None or tipo not in (EV_ACEPTADO, EV_RESUELTO):
                continue
            esperado = "hallazgo_anulado" if tipo == EV_ACEPTADO else "hallazgo_resuelto"
            auditado = auditoria.get(causa)
            if auditado is None or auditado != (esperado, usuario, "hallazgo", hallazgo_id):
                problemas.append(f"el evento {evento_id} del hallazgo {hallazgo_id} dice que lo "
                                 f"hizo la persona {usuario}, y no hay una orden suya que lo diga")
    for hallazgo_id in sorted(eventos):
        problemas.append(f"hay eventos del hallazgo {hallazgo_id}, que no existe")
    return problemas

