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
  de al menos 10 caracteres; vale la ultima anulacion que se firmo, mientras
  la huella sea la suya y no venza;
- reabierto: cambia la evidencia de uno aceptado, vence su anulacion o
  vuelve la condicion de uno cerrado, resuelto o desaparecido. Deja el
  hallazgo abierto; si la anulacion vuelve a valer, va detras su evento
  aceptado, y solo si quien la firmo aun puede anular.

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
from typing import Any, NamedTuple

from . import __version__, conciliacion, estados, excepciones, ordenes_compra, pagos, relaciones
from . import politica as politicas
from .almacen import reloj_de, transaccion, usuario_sistema
from .auditoria import registrar
from .campos import FaltaMotivo, Persona
from .dominio import (
    ESTADOS_PENDIENTES,
    AmbitoHallazgo,
    EstadoHallazgo,
    MotivoEjecucion,
    Permiso,
    Severidad,
    TipoEventoHallazgo,
)
from .permisos import SeparacionDeFunciones, exigir, orden_auditada, personas_con
from .reglas import catalogo, motor
from .reglas import instantanea as instantaneas
from .reglas.base import FALLO, GRAVEDAD, SIN_DATOS, Instantanea, Politica, Resultado
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

    codigo = "no_anulable"


class EstadoNoValido(ValueError):
    """La orden no tiene sentido en el estado en que esta el hallazgo."""

    codigo = "estado_no_valido"


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


class CambioEvaluacion(NamedTuple):
    """Un resultado de una regla que cambio con la pasada (None: no estaba, o ya no esta).

    Una tupla con nombre y no una dataclass congelada: la primera pasada de un
    historico crea una por cada resultado (decenas de miles), y una dataclass
    congelada tarda diez veces mas en construirse.
    """

    regla: str
    tabla: str
    fila_id: int
    clave: str
    antes: str | None
    despues: str | None


@dataclass
class Diferencia:
    """Lo que cambio con una pasada: resultados, hallazgos que se mueven y lo pendiente.

    Desde el paso 4 tambien lo que la pasada hizo despues de los hallazgos:
    las excepciones que abrio o a las que unio hallazgos (excepciones.py) y
    las prioridades y revisiones que se movieron en las caches (estados.py).
    """

    ejecucion_id: int | None = None
    simulada: bool = False
    evaluaciones: dict[str, int] = field(default_factory=dict)
    transiciones: list[Transicion] = field(default_factory=list)
    retenidos: list[str] = field(default_factory=list)
    pendientes: dict[str, int] = field(default_factory=dict)
    cambios_evaluacion: list[CambioEvaluacion] = field(default_factory=list)
    excepciones: Any = None
    estados: Any = None
    # Paso 7: lo que la pasada caso del banco antes de evaluar (pagos.conciliar).
    conciliacion: Any = None
    # Paso 8: las copias fusionadas y las relaciones propuestas o retiradas por
    # el sistema antes de evaluar (relaciones.sincronizar).
    relaciones: Any = None
    # Paso 9: las referencias e imputaciones casadas con una PO antes de evaluar
    # (ordenes_compra.sincronizar).
    ordenes: Any = None
    # Paso 10: las imputaciones conciliadas con el planning o retiradas antes de
    # evaluar (conciliacion.sincronizar).
    planning: Any = None

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
    imputaciones = {f.id: [i.id for i in f.imputaciones] for f in instantanea.facturas
                    if f.imputaciones}
    referencias = {f.id: [r.id for r in f.referencias] for f in instantanea.facturas
                   if f.referencias}
    columnas_de = {r.id: motor.campos_de_fuente(r) for r in catalogo.CATALOGO}
    filas_de = {"factura": lambda f: [f], "factura_linea": lambda f: lineas.get(f, []),
                "factura_iva": lambda f: tramos.get(f, []),
                "factura_imputacion": lambda f: imputaciones.get(f, []),
                "factura_referencia": lambda f: referencias.get(f, [])}
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
                           resultados: Sequence[Resultado],
                           cambios: list[CambioEvaluacion] | None = None) -> int:
    """Pone la cache al dia escribiendo solo lo que cambia. Devuelve cuantas filas cambiaron.

    En `cambios` deja cada resultado que paso de uno a otro (o aparecio, o
    ya no se da): es lo que una orden de una persona ensena como "lo que
    cambio" (servicios.py).

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
    sacar, nueva = anteriores.pop, nuevas.append
    # La tupla se desempaqueta en vez de leer sus campos uno a uno: son decenas
    # de miles de vueltas en la primera pasada de un historico.
    for r in resultados:
        regla, tabla, fila_id, resultado, detalle, valores_r = r[:6]
        clave = r.clave_hallazgo
        valores = (volcar(dict(valores_r)) if valores_r and resultado in _CON_VALORES
                   else None)
        previa = sacar((tabla, fila_id, regla, clave), None)
        if previa is not None:
            if previa[1:] == (resultado, detalle, valores):
                continue
            viejas.append((previa[0],))
        if cambios is not None and (previa is None or previa[1] != resultado):
            cambios.append(CambioEvaluacion(regla, tabla, fila_id, clave,
                                            None if previa is None else previa[1], resultado))
        nueva((ejecucion_id, regla, tabla, fila_id, clave, resultado, detalle, valores))
    viejas.extend((previa[0],) for previa in anteriores.values())
    if cambios is not None:
        cambios.extend(CambioEvaluacion(r, t, f, c, previa[1], None)
                       for (t, f, r, c), previa in sorted(anteriores.items()))
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


def _ambito(tabla: str, de_la_regla: str) -> str:
    """De que entidad es un hallazgo: la de su fila, si es una entidad (una importacion, un
    proveedor), o la de su regla. X1 mira facturas y tambien importaciones de maestros."""
    return tabla if tabla in _AMBITOS else de_la_regla


_AMBITOS = frozenset(AmbitoHallazgo.valores())


def _anulable(regla: Any, sentido: str | None) -> int:
    """Si el hallazgo se puede anular: lo dice el catalogo, y nunca la lista de la decision 12."""
    return int(regla.anulable_para(sentido) and not catalogo.nunca_anulable(regla.id, sentido))


@dataclass(frozen=True)
class _Anulacion:
    id: int
    huella: str
    vigente_hasta: str | None
    usuario_id: int
    evento_id: int
    en: str
    segunda_firma_usuario_id: int | None

    @property
    def firmantes(self) -> frozenset[int]:
        return frozenset(u for u in (self.usuario_id, self.segunda_firma_usuario_id)
                         if u is not None)


def _vigente(anulaciones: Sequence[_Anulacion], huella: str, hoy: date) -> _Anulacion | None:
    """La anulacion que vale para esta huella hoy, o None.

    Solo cuenta la ultima que se firmo para el hallazgo: anular otra vez uno
    aceptado es como se cambia el plazo, y si se mirasen tambien las
    anteriores, una sin plazo seguiria valiendo para siempre cuando la nueva
    vence. Vale si es de esta huella y no ha vencido.
    """
    if not anulaciones:
        return None
    ultima = max(anulaciones, key=lambda a: a.id)
    if ultima.huella != huella:
        return None
    if ultima.vigente_hasta is not None and date.fromisoformat(ultima.vigente_hasta) < hoy:
        return None
    return ultima


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
        self.politica = politica or politicas.politica_reglas(conn)
        self.diferencia = Diferencia()

    def ejecutar(self) -> Diferencia:
        conn = self.conn
        # Lo primero, lo que el sistema escribe antes de evaluar, y en este
        # orden: las copias en PDF de lo que llego de Exact se fusionan en su
        # factura y las citas proponen sus relaciones (paso 8); las referencias y
        # las imputaciones se casan con las PO, con las relaciones ya hechas (un
        # abono confirmado toma la PO de lo que abona; paso 9); las imputaciones
        # con horas se concilian con el planning, con sus PO ya puestas (paso 10);
        # despues se casa el banco con lo que queda en juego (paso 7). Lo que se
        # escribe ahora es lo que las reglas ven en esta misma pasada, y su evento
        # es la causa de lo que abra o cierre.
        self.diferencia.relaciones = relaciones.sincronizar(conn)
        self.diferencia.ordenes = ordenes_compra.sincronizar(conn)
        self.diferencia.planning = conciliacion.sincronizar(conn, hoy=self.hoy,
                                                            politica=self.politica)
        self.diferencia.conciliacion = pagos.conciliar(conn,
                                                       tolerancia=self.politica.tolerancia_pago)
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
        _escribir_evaluaciones(conn, self.ejecucion_id, resultados,
                               self.diferencia.cambios_evaluacion)

        self.causas = dict(_filas(
            conn, "SELECT factura_id, max(evento_id) FROM cambio_campo "
                  "WHERE evento_id > ? AND factura_id IS NOT NULL GROUP BY factura_id", (desde,)))
        self.previos = {fila[1]: _Previo(*fila[:9], datos=tuple(fila[9:])) for fila in _filas(
            conn, "SELECT id, clave, regla, huella, estado, pegajosa, tabla, fila_id, factura_id, "
                  f"{', '.join(_COLUMNAS_DATOS)} FROM hallazgo")}
        self.anulaciones: dict[int, list[_Anulacion]] = defaultdict(list)
        for fila in _filas(conn, "SELECT hallazgo_id, id, huella, vigente_hasta, usuario_id, "
                                 "evento_id, en, segunda_firma_usuario_id FROM anulacion"):
            self.anulaciones[fila[0]].append(_Anulacion(*fila[1:]))
        self.pueden_anular = frozenset(personas_con(conn, Permiso.ANULAR_AVISO.value,
                                                    en=self.ahora))
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
        # Lo que va detras de los hallazgos, en la misma transaccion: las
        # excepciones que agrupan los nuevos y las caches de estado y
        # prioridad, que dependen de todo lo anterior y de hoy.
        self.diferencia.excepciones = excepciones.sincronizar(conn, usuario_id=self.usuario_id)
        sin_datos = Counter(r.fila_id for r in resultados
                            if r.resultado == SIN_DATOS and r.tabla == "factura")
        self.diferencia.estados = estados.recalcular(conn, hoy=self.hoy,
                                                     ejecucion_id=self.ejecucion_id,
                                                     sin_datos=dict(sin_datos),
                                                     politica_reglas=self.politica)
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
             d.severidad, regla.calidad, _ambito(d.tabla, regla.ambito), int(regla.pegajosa),
             _anulable(regla, sentido), regla.titulo, d.detalle, _valores_json(d.valores),
             ABIERTO, self.ahora, self.ahora, self.ejecucion_id)).lastrowid)
        _escribir_objetivos(self.conn, hallazgo_id, _objetivos_de(d))
        causa = self._causa(d.facturas)
        _evento(self.conn, hallazgo_id, DETECTADO, ABIERTO, huella, en=self.ahora, causa=causa,
                ejecucion_id=self.ejecucion_id)
        self._anotar(hallazgo_id, d.clave, regla.id, d.factura_id, DETECTADO, None, ABIERTO, causa)

    def _revive(self, hallazgo_id: int, huella: str) -> _Anulacion | None:
        """La anulacion que puede volver a valer ahora, con un evento aceptado nuevo.

        Ese evento se atribuye a quien la firmo: si ya no puede anular (dejo
        el rol, se dio de baja), o no puede quien dio la segunda firma, la
        anulacion no vuelve sola y el hallazgo queda abierto para que lo mire
        alguien que si puede.
        """
        vigente = _vigente(self.anulaciones.get(hallazgo_id, ()), huella, self.hoy)
        if vigente is None or not vigente.firmantes <= self.pueden_anular:
            return None
        return vigente

    def _seguir(self, previo: _Previo, d: motor.Detectado, huella: str) -> bool:
        """Un hallazgo que ya existia y sigue dandose. Devuelve si hubo que tocarlo."""
        regla = catalogo.regla(d.regla)
        sentido = self.sentido.get(d.factura_id)
        cambia = huella != previo.huella
        causa = self._causa(d.facturas)
        # (tipo, estado, usuario, causa, nota) de cada evento, en orden.
        eventos: list[tuple[str, str, int | None, int | None, str | None]] = []

        def aceptado(anulacion: _Anulacion, nota: str) -> None:
            eventos.append((EV_ACEPTADO, ACEPTADO, anulacion.usuario_id, anulacion.evento_id,
                            f"{nota} el {anulacion.en}"))

        if previo.estado == ABIERTO:
            vuelve = self._revive(previo.id, huella)
            if vuelve is not None:
                aceptado(vuelve, "vuelve la evidencia que se anulo")
            elif cambia:
                eventos.append((CAMBIO_EVIDENCIA, ABIERTO, None, causa, None))
        elif previo.estado == ACEPTADO:
            sigue = _vigente(self.anulaciones.get(previo.id, ()), huella, self.hoy)
            if sigue is None:
                eventos.append((REABIERTO, ABIERTO, None, causa,
                                "la evidencia cambio" if cambia else "la anulacion ha vencido"))
            elif cambia:
                vuelve = self._revive(previo.id, huella)
                if vuelve is not None:
                    aceptado(vuelve, "la nueva evidencia es la que se anulo")
                else:
                    eventos.append((REABIERTO, ABIERTO, None, causa,
                                    "quien firmo la anulacion ya no puede anular"))
        else:
            eventos.append((REABIERTO, ABIERTO, None, causa, "la condicion vuelve a darse"))
            vuelve = self._revive(previo.id, huella)
            if vuelve is not None:
                aceptado(vuelve, "vuelve la evidencia que se anulo")

        objetivos = _objetivos_de(d)
        cambian_objetivos = objetivos != self.objetivos.get(previo.id, set())
        datos = (regla.version, d.tabla, d.fila_id, d.factura_id, d.severidad, int(regla.pegajosa),
                 _anulable(regla, sentido), regla.titulo, d.detalle, _valores_json(d.valores))
        if not eventos and not cambian_objetivos and datos == previo.datos:
            return False
        antes = previo.estado
        for tipo, estado, usuario, causa_evento, nota in eventos:
            _evento(self.conn, previo.id, tipo, estado, huella, en=self.ahora,
                    causa=causa_evento, ejecucion_id=self.ejecucion_id, usuario_id=usuario,
                    nota=nota)
            self._anotar(previo.id, d.clave, regla.id, d.factura_id, tipo, antes, estado,
                         causa_evento, nota)
            antes = estado
        self.conn.execute(
            "UPDATE hallazgo SET regla_version = ?, tabla = ?, fila_id = ?, factura_id = ?, "
            "severidad = ?, pegajosa = ?, anulable = ?, titulo = ?, detalle = ?, "
            "valores_json = ?, huella = ?, estado = ?, ultima_vez_en = ?, "
            "ultima_ejecucion_id = ? WHERE id = ?",
            (*datos, huella if eventos else previo.huella, antes, self.ahora,
             self.ejecucion_id, previo.id))
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
            # Si es pegajosa lo dice el catalogo, no la fila: una marca tocada
            # por detras no puede dejar que un duplicado se cierre solo.
            pegajosa = catalogo.regla(previo.regla).pegajosa or previo.pegajosa
            tipo, estado = ((EV_DESAPARECIDO, DESAPARECIDO) if pegajosa
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


def _importe_mayor(conn: sqlite3.Connection, hallazgo: sqlite3.Row) -> int | None:
    """El mayor importe (base, o total si no hay base) de las facturas que cubre el hallazgo.

    Un hallazgo de grupo (B2, B3, B4, G3) cuelga de su factura mas reciente,
    pero anularlo libera tambien las demas: un par con una factura de 50.000
    euros pide segunda firma aunque la principal sea de 425.
    """
    importes = [abs(base if base is not None else total) for base, total in _filas(
        conn, "SELECT base_cent, total_cent FROM factura WHERE id = ? OR id IN ("
              "SELECT fila_id FROM hallazgo_objetivo WHERE hallazgo_id = ? "
              "AND tabla = 'factura')", (hallazgo["factura_id"], hallazgo["id"]))
        if base is not None or total is not None]
    return max(importes) if importes else None


def firmas_vigentes(conn: sqlite3.Connection, hallazgo: sqlite3.Row) -> list[dict[str, Any]]:
    """Las segundas firmas que otra persona dio para anular este hallazgo y aun valen: con
    la evidencia de ahora (su huella), sin caducar y sin gastar; la mas reciente primero.

    Cada una dice para quien es (`solicitante_id`), quien firmo (`usuario_id`), hasta cuando
    vale la anulacion firmada (`vigente_hasta`) y cuando caduca la firma (`caduca_en`). La
    usa la orden de anular (servicios) y la ficha de la factura, para que la app no ofrezca
    aceptar algo que el servidor va a negar por falta de firma."""
    filas = conn.execute(
        "SELECT e.id, e.usuario_id, e.motivo, "
        "json_extract(e.datos_json, '$.solicitante_id') AS solicitante_id, "
        "json_extract(e.datos_json, '$.vigente_hasta') AS vigente_hasta, "
        "json_extract(e.datos_json, '$.caduca_en') AS caduca_en "
        "FROM evento AS e "
        "WHERE e.tipo = 'anulacion_firmada' AND e.resultado = 'ok' AND e.tabla = 'hallazgo' "
        "AND e.fila_id = ? AND json_extract(e.datos_json, '$.huella') = ? "
        "AND json_extract(e.datos_json, '$.caduca_en') > ? "
        "AND NOT EXISTS (SELECT 1 FROM evento AS s WHERE s.tipo = 'hallazgo_segunda_firma' "
        "AND json_extract(s.datos_json, '$.firma_evento_id') = e.id) "
        "ORDER BY e.id DESC",
        (hallazgo["id"], hallazgo["huella"], marca(reloj_de(conn).ahora()))).fetchall()
    return [dict(f) for f in filas]


def requiere_segunda_firma(conn: sqlite3.Connection, hallazgo: sqlite3.Row) -> bool:
    """Si anular este hallazgo pide la firma de una segunda persona.

    Cuando la regla lo pide (B2), cuando el hallazgo bloquea y cuando alguna
    de sus facturas es de 10.000 euros o mas (§3, decision 12). Que bloquea
    lo dice la fila o el catalogo para el sentido de la factura, lo que sea
    mas grave: la fila sola se puede tocar por detras. Solo se exige si hay
    otra persona con anular_aviso; si no, la anulacion entra como
    autoaprobada, y queda dicho.
    """
    regla = catalogo.POR_ID.get(hallazgo["regla"])
    factura = _factura(conn, hallazgo["factura_id"])
    sentido = factura["sentido"] if factura is not None else None
    bloquea = hallazgo["severidad"] == Severidad.BLOQUEO.value or (
        regla is not None and regla.severidad_para(sentido) == Severidad.BLOQUEO.value)
    importe = _importe_mayor(conn, hallazgo)
    return bool(
        (regla is not None and regla.segunda_firma) or bloquea
        or (importe is not None and importe >= IMPORTE_SEGUNDA_FIRMA_CENT))


def comprobar_anulable(conn: sqlite3.Connection, hallazgo: sqlite3.Row) -> None:
    """Que el hallazgo se pueda anular ahora: abierto o ya aceptado, y de una regla que lo
    admite para el sentido de su factura (EstadoNoValido o NoAnulable si no)."""
    if hallazgo["estado"] not in (ABIERTO, ACEPTADO):
        raise EstadoNoValido(
            f"el hallazgo {hallazgo['id']} esta {hallazgo['estado']}: solo se anula uno abierto")
    factura = _factura(conn, hallazgo["factura_id"])
    sentido = factura["sentido"] if factura is not None else None
    regla = catalogo.POR_ID.get(hallazgo["regla"])
    if (regla is None or not hallazgo["anulable"] or not regla.anulable_para(sentido)
            or catalogo.nunca_anulable(hallazgo["regla"], sentido)):
        raise NoAnulable(f"la regla {hallazgo['regla']} no se puede anular: hay que "
                         "corregir el dato o resolver el caso")


def anular(conn: sqlite3.Connection, hallazgo_id: int, persona: Persona, *,
           vigente_hasta: date | str | None = None,
           segunda_firma: Persona | None = None,
           datos: dict[str, Any] | None = None,
           datos_segunda_firma: dict[str, Any] | None = None) -> int:
    """Una persona con anular_aviso acepta la evidencia de ahora de un hallazgo. Devuelve su id.

    Vale mientras la huella del hallazgo sea la que se anula, sea la ultima
    anulacion que se firmo y, si se da `vigente_hasta`, hasta ese dia
    incluido. No se anula una regla que no lo admite (la lista de la
    decision 12 y las que el catalogo marca), ni un hallazgo que no este
    abierto o ya aceptado. El motivo es obligatorio, de al menos 10
    caracteres: "ok" no explica nada a quien lo lea despues.

    La segunda firma es la orden de otra persona (`segunda_firma`, con su
    propia peticion): queda como un evento suyo, hallazgo_segunda_firma,
    justo antes del de la anulacion, y la base no admite una anulacion con
    segunda firma sin el. Que esa persona la diera de verdad lo asegura
    quien la llama: servicios.py solo la pone si esa persona firmo antes,
    desde su sesion, la orden firmar_anulacion (`datos_segunda_firma` lleva
    el evento de esa firma, que asi queda gastada).
    """
    motivo = (persona.motivo or "").strip()
    with orden_auditada(conn):
        exigir(conn, persona.usuario_id, Permiso.ANULAR_AVISO.value, accion="anular un hallazgo")
        hallazgo = _hallazgo(conn, hallazgo_id)
        comprobar_anulable(conn, hallazgo)
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
        segundo = segunda_firma.usuario_id if segunda_firma is not None else None
        if segunda_firma is not None:
            if segundo == persona.usuario_id:
                raise SeparacionDeFunciones(
                    persona.usuario_id, permiso, "la segunda firma tiene que ser de otra persona",
                    "anular un hallazgo")
            exigir(conn, segundo, permiso, accion="firmar en segundo lugar una anulacion")
        elif requiere_segunda_firma(conn, hallazgo):
            if any(p != persona.usuario_id for p in personas_con(conn, permiso)):
                raise SeparacionDeFunciones(
                    persona.usuario_id, permiso, "esta anulacion necesita la segunda firma de "
                    "otra persona con anular_aviso: que la de antes con firmar_anulacion (para "
                    "quien anula, con esta huella y este plazo)", "anular un hallazgo")
            autoaprobada = 1
        fila = {
            "hallazgo_id": hallazgo_id, "huella": hallazgo["huella"], "motivo": motivo,
            "usuario_id": persona.usuario_id, "en": en, "vigente_hasta": hasta,
            "segunda_firma_usuario_id": segundo,
            "segunda_firma_en": en if segundo is not None else None,
            "autoaprobada": autoaprobada,
        }
        if segunda_firma is not None:
            firma = registrar(
                conn, tipo="hallazgo_segunda_firma", actor=segundo, usuario_id=segundo,
                tabla="hallazgo", fila_id=hallazgo_id, factura_id=hallazgo["factura_id"],
                motivo=(segunda_firma.motivo or "").strip() or motivo,
                peticion_id=segunda_firma.peticion_id,
                datos={**(datos_segunda_firma or {}), "clave": hallazgo["clave"],
                       "huella": hallazgo["huella"], "firma_con": persona.usuario_id})
            fila["segunda_firma_en"] = conn.execute(
                "SELECT en FROM evento WHERE id = ?", (firma,)).fetchone()[0]
        evento = registrar(
            conn, tipo="hallazgo_anulado", actor=persona.usuario_id,
            usuario_id=persona.usuario_id, tabla="hallazgo", fila_id=hallazgo_id,
            factura_id=hallazgo["factura_id"], motivo=motivo, peticion_id=persona.peticion_id,
            datos={**(datos or {}), "fila": fila, "clave": hallazgo["clave"],
                   "regla": hallazgo["regla"]})
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


def resolver(conn: sqlite3.Connection, hallazgo_id: int, persona: Persona, *,
             datos: dict[str, Any] | None = None,
             permiso: str = Permiso.RESOLVER_AVISO.value) -> int:
    """Una persona con resolver_aviso cierra un hallazgo cuya condicion ha desaparecido.

    Es la unica forma de cerrar uno de una regla pegajosa. Uno abierto no se
    resuelve: se corrige el dato (y entonces desaparece) o se anula. Los de
    las cuentas bancarias (familia F) los cierra tambien quien los hizo
    desaparecer con su verificacion o su rechazo, con confirmar_iban
    (`permiso`, lo pide servicios.py): es esa decision la que los resuelve.
    """
    motivo = (persona.motivo or "").strip()
    with orden_auditada(conn):
        exigir(conn, persona.usuario_id, permiso,
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
            datos={**(datos or {}), "clave": hallazgo["clave"], "regla": hallazgo["regla"],
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


def _clasificacion(regla_id: str, regla_version: int, sentido: str | None, severidad: str,
                   pegajosa: int, anulable: int) -> str | None:
    """Que no cuadra entre lo que dice la fila de un hallazgo y lo que dice el catalogo.

    Con la misma version de la regla, pegajosa y anulable son las del
    catalogo, y la severidad nunca es mas leve que la de la regla para el
    sentido de la factura (Q1 puede ser mas grave: bloquea si falta el
    numero). Una regla que ya no esta en el catalogo, o de otra version, no
    se compara: su fila es de cuando se evaluo.
    """
    regla = catalogo.POR_ID.get(regla_id)
    if regla is None or regla.version != regla_version:
        return None
    if pegajosa != int(regla.pegajosa):
        return "su marca pegajosa no es la del catalogo"
    if anulable != _anulable(regla, sentido):
        return "su marca anulable no es la del catalogo"
    if GRAVEDAD.get(severidad, 99) > GRAVEDAD[regla.severidad_para(sentido)]:
        return f"su severidad ({severidad}) es mas leve que la del catalogo"
    return None


def verificar(conn: sqlite3.Connection) -> list[str]:
    """Que cada hallazgo sea lo que dice su historia, sin fiarse de los disparadores.

    Cada hallazgo empieza con un evento detectado y su estado y su huella son
    los de su ultimo evento; lo que hizo una persona (aceptar, resolver)
    cuelga de un evento de auditoria suyo sobre ese hallazgo. A aceptado solo
    se llega con un evento aceptado, con una anulacion de esa huella firmada
    antes y de una regla que se puede anular. Su clasificacion (pegajosa,
    anulable, severidad) es la del catalogo y, si la evidencia es la de hoy,
    la severidad es la que da el motor ahora. Las anulaciones se comparan con
    la foto de su evento en almacen/evidencia.py.
    """
    problemas: list[str] = []
    eventos: dict[int, list[tuple]] = defaultdict(list)
    for fila in _filas(conn, "SELECT hallazgo_id, id, tipo, estado, huella, causa_evento_id, "
                             "usuario_id, en FROM hallazgo_evento ORDER BY id"):
        eventos[fila[0]].append(fila[1:])
    auditoria = {f[0]: f[1:] for f in _filas(
        conn, "SELECT id, tipo, usuario_id, tabla, fila_id FROM evento "
              "WHERE tipo IN ('hallazgo_anulado', 'hallazgo_resuelto')")}
    anulaciones = {(h, e): (huella, en) for h, e, huella, en in _filas(
        conn, "SELECT hallazgo_id, evento_id, huella, en FROM anulacion")}
    ahora = _ahora_del_motor(conn)
    for (hallazgo_id, clave, regla, regla_version, estado, huella, severidad, pegajosa,
         anulable, sentido) in _filas(
            conn, "SELECT h.id, h.clave, h.regla, h.regla_version, h.estado, h.huella, "
                  "h.severidad, h.pegajosa, h.anulable, f.sentido FROM hallazgo AS h "
                  "LEFT JOIN factura AS f ON f.id = h.factura_id ORDER BY h.id"):
        historia_ = eventos.pop(hallazgo_id, [])
        if not historia_:
            problemas.append(f"el hallazgo {hallazgo_id} ({clave}) no tiene historia")
            continue
        if historia_[0][1] != DETECTADO:
            problemas.append(f"el hallazgo {hallazgo_id} no empieza con su deteccion")
        _id, _tipo, ultimo_estado, ultima_huella, _causa, _usuario, _en = historia_[-1]
        if (estado, huella) != (ultimo_estado, ultima_huella):
            problemas.append(f"el hallazgo {hallazgo_id}: su estado o su huella no son los de su "
                             "ultimo evento (se ha modificado por detras)")
        clasificacion = _clasificacion(regla, regla_version, sentido, severidad, pegajosa,
                                       anulable)
        if clasificacion is not None:
            problemas.append(f"el hallazgo {hallazgo_id} ({clave}): {clasificacion}")
        detectado = ahora.get(clave)
        if (detectado is not None and detectado[1] == huella
                and detectado[0].severidad != severidad):
            problemas.append(f"el hallazgo {hallazgo_id} ({clave}): su severidad ({severidad}) "
                             f"no es la que da el motor ({detectado[0].severidad})")
        for evento_id, tipo, estado_evento, huella_evento, causa, usuario, en in historia_:
            if estado_evento == ACEPTADO:
                problema = _aceptado_sin_anulacion(
                    tipo, usuario, anulaciones.get((hallazgo_id, causa)), huella_evento, en,
                    regla, sentido)
                if problema is not None:
                    problemas.append(f"el evento {evento_id} del hallazgo {hallazgo_id} lo deja "
                                     f"aceptado y {problema}")
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


def _aceptado_sin_anulacion(tipo: str, usuario: int | None, anulacion: tuple | None,
                            huella: str, en: str, regla_id: str, sentido: str | None) -> str | None:
    """Por que un evento que deja un hallazgo aceptado no tiene detras una anulacion que valga."""
    if tipo != EV_ACEPTADO or usuario is None:
        return "no es una aceptacion de una persona"
    if anulacion is None or anulacion[0] != huella:
        return "no hay una anulacion de esa evidencia"
    if anulacion[1] > en:
        return "su anulacion es posterior"
    regla = catalogo.POR_ID.get(regla_id)
    if regla is None or not regla.anulable_para(sentido) or catalogo.nunca_anulable(
            regla_id, sentido):
        return "su regla no se puede anular"
    return None


def _ahora_del_motor(conn: sqlite3.Connection) -> dict[str, tuple[motor.Detectado, str]]:
    """Los hallazgos que da el motor sobre el almacen de ahora, por clave, con su huella."""
    instantanea = instantaneas.construir(conn, hoy=reloj_de(conn).hoy(),
                                         politica=politicas.politica_reglas(conn))
    return {d.clave: (d, huella) for d, huella in calcular(conn, instantanea)}

