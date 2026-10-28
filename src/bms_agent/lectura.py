"""La lectura de los PDF pedida desde la app (paso 17; especificacion §5, revision §8.5).

La app no tiene red (connect-src 'self') ni lanza programas, asi que no puede leer un PDF.
Lo que si puede: pedir una lectura, ver lo que costaria, dar el si (o el no) y seguir el
progreso. Quien lee sigue siendo el lector, que abre una persona en el escritorio
(leer-facturas.bat), con el orden de seguridad de siempre:

1. enciende la salida con una credencial nueva (el script);
2. comprueba el aislamiento de la salida y del lector (el script, con el programa de cada
   papel). Si falla, no se cuenta, no se lee y no se paga;
3. cuenta lo que costaria (gratis, pero es una llamada a la API: con la salida encendida);
4. lee solo con un si, de la app o escrito en su ventana;
5. apaga la salida siempre (el `finally` del script).

Dos tablas (migracion 0018). `solicitud_lectura` es la peticion: pedida, comprobando,
contando, esperando_aprobacion, aprobada, leyendo y, al final, hecha, fallida, caducada,
cancelada o nada_que_leer. Viva solo hay una. `pasada_lectura` es el progreso de la
lectura de una peticion, documento a documento: lo que la app consulta cada 2 s.

Las ordenes de las personas van por servicios.py (POST /api/v2/acciones), con el permiso
importar_datos, y cada una deja su evento en la auditoria:

- pedir_lectura crea una peticion, solo si no hay otra viva (una que el lector dejo a
  medias, sin senales desde hace mucho, se da por terminada antes);
- aprobar_lectura da el si: solo mientras se espera, antes de que caduque, y para la
  estimacion que la persona vio (su huella; si cambio, es un Conflicto y hay que mirarla
  otra vez). Guarda el tope de gasto: por defecto el extremo alto de la horquilla, y nunca
  mas;
- cancelar_lectura dice que no. Antes de leer, la peticion queda cancelada al momento y el
  lector apaga la salida sin gastar nada; leyendo, el lector para despues del documento en
  curso.

Lo del lector son las ordenes `bms-agent lectura ...` (cli.py), que llaman los
leer-facturas.ps1 de windows/ y de docker/: tomar, contar, esperar, leer y cerrar. El lector
no firma como persona: sus eventos los firma el usuario de sistema "extractor".

El tope: antes de pagar cada documento se mira si lo gastado mas lo que puede costar ese
documento (el extremo alto de su estimacion, con su entrada contada) cabe en el tope. Si no
cabe, ni ese ni los siguientes se pagan, y la pasada termina en "tope". Lo gastado es el uso
de cada respuesta, tambien de un rechazo; de un fallo sin uso se cuenta su extremo alto.

Nada de aqui habla con la API por su cuenta ni lanza procesos: contar y leer reciben el
cliente de quien los llama (el lector, despues de su puerta, nativo.exigir_lectura).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from .almacen import reloj_de, transaccion, usuario_sistema
from .almacen.unidades import json_canonico, sha256_texto
from .auditoria import registrar
from .campos import Conflicto
from .reloj import marca

TABLA = "solicitud_lectura"

VIVOS = ("pedida", "comprobando", "contando", "esperando_aprobacion", "aprobada", "leyendo")
# Los vivos que tiene un lector entre manos.
DEL_LECTOR = ("comprobando", "contando", "esperando_aprobacion", "aprobada", "leyendo")
FINALES = ("hecha", "fallida", "caducada", "cancelada", "nada_que_leer")
ESTADOS = VIVOS + FINALES

FASES_EN_CURSO = ("cargando", "leyendo", "comparando", "analizando", "organizando")
FASES_FINALES = ("hecha", "fallida", "cancelada", "tope")
FASES = FASES_EN_CURSO + FASES_FINALES
DOCUMENTO_FASES = ("comparando", "leyendo", "guardando")
# Lo que fue de cada documento al terminar.
RESULTADOS = ("nueva", "ya_leida", "posible_duplicado", "fallida")
# Las reglas de duplicados: una factura nueva con uno de estos avisos abierto es un posible
# duplicado, y espera a una persona.
REGLAS_DUPLICADO = ("B2", "B3", "B4", "B5")

# El lector espera el si como mucho esto; despues apaga la salida (revision §8.5, punto 5).
PLAZO_RESPUESTA = timedelta(minutes=15)
# Cada cuanto mira el lector si llego el si de la app (y la app, el progreso).
CONSULTA_CADA = 2
# Una peticion que un lector tiene entre manos y no da senales desde hace esto (la ventana
# se cerro con la X, el ordenador se apago) se da por abandonada. Una llamada a la API tarda
# como mucho unos minutos (y sus reintentos); tipar y pasar las reglas, menos.
SIN_SENALES = timedelta(minutes=45)
# Mientras espera el si, el lector da senales cada LATIDO; sin ninguna en SIN_SENALES_ESPERANDO
# (su ventana se cerro), otro lector puede volver a contar esa misma peticion. Y como mucho,
# este rato despues de caducar (el lector la habria cerrado como caducada).
LATIDO = timedelta(seconds=10)
SIN_SENALES_ESPERANDO = timedelta(seconds=90)
MARGEN_CADUCIDAD = timedelta(minutes=5)
# Lo que ensena la app debajo de la escena: los dos ultimos terminados y el de ahora.
RECIENTES = 2

# Por que termino mal (motivo_codigo), con su frase para la CLI y la auditoria. La app dice
# el suyo en cada idioma a partir del codigo.
MOTIVOS = {
    "buzon_vacio": "no hay ningun PDF en el buzon",
    "ya_leidas": "no hay facturas nuevas: las que hay ya estan leidas y no se vuelven a pagar",
    "clave": "falta la clave de la API: guardala con clave.bat",
    "salida": "la salida no ha arrancado: no se ha leido ni pagado nada",
    "aislamiento": ("el aislamiento no esta bien: no se ha leido ni pagado nada. Ejecuta "
                    "comprobar.bat"),
    "contar": "no se ha podido contar lo que costaria: no se ha leido ni pagado nada",
    "sin_tarifa": ("no hay tarifa para el modelo: sin una cifra no se puede poner un tope, "
                   "y no se lee"),
    "estimacion": "la estimacion no es la que se aprobo: no se lee nada sin un si nuevo",
    "lectura": "la lectura ha fallado",
    "interrumpida": "el lector se cerro antes de terminar",
    "abandonada": "el lector dejo de dar senales: la lectura se da por terminada",
}


class EstadoNoValido(ValueError):
    """La orden no tiene sentido en el estado de la lectura (hay otra viva, ya termino, ya no
    espera un si). Un 409 en /api/v2."""

    codigo = "estado_no_valido"


class EstimacionCambiada(Conflicto):
    """El si llega para otra estimacion que la de ahora: hay que mirarla otra vez (409)."""


class Parada(Exception):
    """La peticion dejo de estar donde el lector la esperaba (se cancelo, o la cerro otro)."""

    def __init__(self, estado: str) -> None:
        super().__init__(f"la lectura esta {estado}")
        self.estado = estado


# ------------------------------------------------------------ utilidades

def _ahora(conn: sqlite3.Connection) -> datetime:
    return reloj_de(conn).ahora()


def _instante(texto: str | None) -> datetime | None:
    return datetime.fromisoformat(texto) if texto else None


def micro(coste: Decimal | None) -> int | None:
    """Dolares (pricing.estimate_cost, con seis decimales) en millonesimas enteras."""
    return None if coste is None else int(coste * 1_000_000)


def dolares(usd_micro: int | None) -> str:
    return "sin tarifa" if usd_micro is None else f"${Decimal(usd_micro) / 1_000_000:.4f}"


def _fila(conn: sqlite3.Connection, solicitud_id: int) -> sqlite3.Row:
    fila = conn.execute("SELECT * FROM solicitud_lectura WHERE id = ?",
                        (solicitud_id,)).fetchone()
    if fila is None:
        raise LookupError(f"no existe la lectura {solicitud_id}")
    return fila


def viva(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """La peticion viva, si la hay (solo puede haber una)."""
    marcas = ", ".join("?" * len(VIVOS))
    return conn.execute(f"SELECT * FROM solicitud_lectura WHERE estado IN ({marcas})",
                        VIVOS).fetchone()


def _ultima_senal(conn: sqlite3.Connection, fila: sqlite3.Row) -> datetime:
    pasada = conn.execute("SELECT actualizada_en FROM pasada_lectura WHERE solicitud_id = ?",
                          (fila["id"],)).fetchone()
    senales = [_instante(fila["actualizada_en"])]
    if pasada is not None:
        senales.append(_instante(pasada["actualizada_en"]))
    return max(s for s in senales if s is not None)


def abandonada(conn: sqlite3.Connection, fila: sqlite3.Row, ahora: datetime | None = None
               ) -> bool:
    """Si un lector tenia esta peticion entre manos y ya no esta: esperando el si, sin senales
    desde SIN_SENALES_ESPERANDO (o pasado el plazo, y un margen); en los demas estados del
    lector, sin senales desde SIN_SENALES. Una pedida no se abandona: espera a que alguien
    abra el lector (o diga que no)."""
    ahora = ahora or _ahora(conn)
    if fila["estado"] not in DEL_LECTOR:
        return False
    if fila["estado"] == "esperando_aprobacion":
        return (ahora >= _instante(fila["caduca_en"]) + MARGEN_CADUCIDAD
                or ahora - _ultima_senal(conn, fila) >= SIN_SENALES_ESPERANDO)
    return ahora - _ultima_senal(conn, fila) >= SIN_SENALES


def _extractor(conn: sqlite3.Connection) -> int:
    return usuario_sistema(conn, "extractor")


def _evento(conn: sqlite3.Connection, tipo: str, solicitud_id: int, *,
            persona: int | None = None, peticion_id: str | None = None,
            motivo: str | None = None, datos: dict[str, Any] | None = None) -> int:
    """El evento de un cambio de una lectura: lo firma la persona (desde la app) o el
    extractor (el lector, o una peticion que se da por abandonada)."""
    return registrar(conn, tipo=tipo, actor=persona if persona is not None else _extractor(conn),
                     usuario_id=persona, tabla=TABLA, fila_id=solicitud_id, motivo=motivo,
                     peticion_id=peticion_id, datos=datos)


def _pasar(conn: sqlite3.Connection, solicitud_id: int, de: Iterable[str], a: str | None, *,
           tipo: str, persona: int | None = None, peticion_id: str | None = None,
           motivo: str | None = None, datos: dict[str, Any] | None = None,
           **columnas: Any) -> int:
    """Cambia una peticion que esta en uno de `de` (a `a`, o se queda en su estado si `a` es
    None) con su evento, en una transaccion. EstadoNoValido si no estaba donde se esperaba."""
    de = tuple(de)
    with transaccion(conn):
        fila = _fila(conn, solicitud_id)
        if fila["estado"] not in de:
            raise EstadoNoValido(f"la lectura {solicitud_id} esta {fila['estado']}")
        ahora = marca(_ahora(conn))
        nuevos = dict(columnas, actualizada_en=ahora)
        if motivo is not None:
            nuevos["motivo"] = motivo
        if a is not None:
            nuevos["estado"] = a
            if a in FINALES:
                nuevos["terminada_en"] = ahora
        asignaciones = ", ".join(f"{c} = ?" for c in nuevos)
        cursor = conn.execute(
            f"UPDATE solicitud_lectura SET {asignaciones} WHERE id = ? AND estado = ?",
            (*nuevos.values(), solicitud_id, fila["estado"]))
        if cursor.rowcount != 1:
            raise EstadoNoValido(f"la lectura {solicitud_id} cambio mientras tanto")
        return _evento(conn, tipo, solicitud_id, persona=persona, peticion_id=peticion_id,
                       motivo=motivo, datos={"de": fila["estado"], "a": a or fila["estado"],
                                             **(datos or {})})


def _cerrar_abandonada(conn: sqlite3.Connection, fila: sqlite3.Row) -> None:
    """Una peticion que un lector dejo a medias termina fallida (y su pasada, si la tiene)."""
    _terminar_pasada(conn, fila["id"], "fallida", MOTIVOS["abandonada"])
    _pasar(conn, fila["id"], DEL_LECTOR, "fallida", tipo="lectura_fallida",
           motivo=MOTIVOS["abandonada"], motivo_codigo="abandonada",
           datos={"motivo_codigo": "abandonada"})


# ------------------------------------------------------------ las ordenes de las personas

def pedir(conn: sqlite3.Connection, persona: int, *, peticion_id: str | None = None,
          datos: dict[str, Any] | None = None) -> tuple[int, int]:
    """Una peticion nueva desde la app: (su id, el id de su evento)."""
    with transaccion(conn):
        actual = viva(conn)
        if actual is not None:
            if not abandonada(conn, actual):
                raise EstadoNoValido(f"ya hay una lectura {actual['estado']} (la {actual['id']}): "
                                     "una cada vez")
            _cerrar_abandonada(conn, actual)
        ahora = marca(_ahora(conn))
        solicitud_id = conn.execute(
            "INSERT INTO solicitud_lectura (origen, pedida_por, pedida_en, estado, "
            "actualizada_en) VALUES ('app', ?, ?, 'pedida', ?)",
            (persona, ahora, ahora)).lastrowid
        evento = _evento(conn, "lectura_pedida", solicitud_id, persona=persona,
                         peticion_id=peticion_id, datos={"origen": "app", **(datos or {})})
    return solicitud_id, evento


def _tope(fila: sqlite3.Row, tope: int | None) -> int:
    alto = fila["coste_max_usd_micro"]
    tope = alto if tope is None else tope
    if not isinstance(tope, int) or isinstance(tope, bool) or not 0 < tope <= alto:
        raise ValueError(f"el tope va en millonesimas de dolar, de 1 a {alto} (el extremo alto "
                         "de la estimacion)")
    return tope


def aprobar(conn: sqlite3.Connection, persona: int, solicitud_id: int, huella: str,
            tope: int | None = None, *, peticion_id: str | None = None,
            datos: dict[str, Any] | None = None) -> int:
    """El si de una persona desde la app, para la estimacion que vio (su huella)."""
    with transaccion(conn):
        fila = _fila(conn, solicitud_id)
        if fila["estado"] != "esperando_aprobacion":
            raise EstadoNoValido(f"la lectura {solicitud_id} esta {fila['estado']}: no espera "
                                 "un si")
        ahora = _ahora(conn)
        if ahora >= _instante(fila["caduca_en"]):
            raise EstadoNoValido(f"la lectura {solicitud_id} ya no espera: el plazo para decir "
                                 "que si acabo y el lector apaga la salida")
        if huella != fila["huella_estimacion"]:
            raise EstimacionCambiada(f"la estimacion de la lectura {solicitud_id} cambio desde "
                                     "que la viste: mirala otra vez")
        tope = _tope(fila, tope)
        return _pasar(conn, solicitud_id, ("esperando_aprobacion",), "aprobada",
                      tipo="lectura_aceptada", persona=persona, peticion_id=peticion_id,
                      aprobada_por=persona, aprobada_en=marca(ahora), aprobada_via="app",
                      tope_usd_micro=tope, huella_aprobada=huella,
                      datos={"via": "app", "tope_usd_micro": tope, "huella": huella,
                             **(datos or {})})


def cancelar(conn: sqlite3.Connection, persona: int, solicitud_id: int, *,
             peticion_id: str | None = None, datos: dict[str, Any] | None = None) -> int:
    """El no de una persona desde la app. Antes de leer, la peticion queda cancelada al
    momento (el lector lo ve y apaga la salida sin gastar nada); leyendo, se apunta que se
    pidio parar y el lector para despues del documento en curso (y la cierra el)."""
    with transaccion(conn):
        fila = _fila(conn, solicitud_id)
        ahora = marca(_ahora(conn))
        quien = {"cancelada_por": persona, "cancelada_en": ahora, "cancelada_via": "app"}
        if fila["estado"] == "leyendo" and not abandonada(conn, fila):
            if fila["cancelada_en"] is not None:
                raise EstadoNoValido(f"ya se pidio parar la lectura {solicitud_id}")
            return _pasar(conn, solicitud_id, ("leyendo",), None, tipo="lectura_parar",
                          persona=persona, peticion_id=peticion_id, **quien,
                          datos={"via": "app", **(datos or {})})
        if fila["estado"] == "leyendo":
            _terminar_pasada(conn, solicitud_id, "cancelada", MOTIVOS["abandonada"])
        if fila["estado"] not in VIVOS:
            raise EstadoNoValido(f"la lectura {solicitud_id} ya termino ({fila['estado']})")
        return _pasar(conn, solicitud_id, VIVOS, "cancelada", tipo="lectura_cancelada",
                      persona=persona, peticion_id=peticion_id, **quien,
                      datos={"via": "app", **(datos or {})})


# ------------------------------------------------------------ lo que hace el lector

TOMADA, CREADA, VACIO, OCUPADA = "tomada", "creada", "vacio", "ocupada"


@dataclass(frozen=True)
class Tomada:
    """Lo que paso al abrir el lector: la peticion que lleva (o ninguna) y por que."""

    solicitud_id: int | None
    como: str
    detalle: str = ""


def volver_a_contar(conn: sqlite3.Connection, solicitud_id: int) -> None:
    """Una peticion que esperaba el si vuelve a comprobando, sin su estimacion: el lector que
    la conto ya no esta (o el buzon cambio) y otro la vuelve a contar. La huella nueva es la
    de lo que se cuente ahora: un si a la de antes es un Conflicto."""
    _pasar(conn, solicitud_id, ("esperando_aprobacion",), "comprobando",
           tipo="lectura_tomada", tomada_en=marca(_ahora(conn)), pdf_nuevos=None,
           pdf_ya_leidos=None, coste_min_usd_micro=None, coste_max_usd_micro=None,
           huella_estimacion=None, estimacion_json=None, contada_en=None, caduca_en=None,
           datos={"otra_vez": True})


def tomar(conn: sqlite3.Connection, *, hay_pdf: bool) -> Tomada:
    """El lector se abre: toma la peticion pedida o crea una (origen lector) y la pone
    comprobando. Sin ningun PDF en el buzon no hay nada que hacer: una pedida termina en
    nada_que_leer y no se crea ninguna. Si otro lector tiene una entre manos (y da senales),
    no se toca. Una que esperaba el si y cuyo lector ya no esta se vuelve a contar (la misma
    peticion: lo que la persona pidio sigue); otra que un lector dejo a medias se da por
    terminada antes."""
    with transaccion(conn):
        actual = viva(conn)
        if actual is not None and actual["estado"] in DEL_LECTOR:
            if not abandonada(conn, actual):
                return Tomada(None, OCUPADA, f"la lectura {actual['id']} esta "
                                             f"{actual['estado']} en otro lector")
            if hay_pdf and actual["estado"] == "esperando_aprobacion":
                volver_a_contar(conn, actual["id"])
                return Tomada(actual["id"], TOMADA, "se vuelve a contar")
            _cerrar_abandonada(conn, actual)
            actual = None
        ahora = marca(_ahora(conn))
        if not hay_pdf:
            if actual is None:
                return Tomada(None, VACIO, MOTIVOS["buzon_vacio"])
            _pasar(conn, actual["id"], ("pedida",), "nada_que_leer", tipo="lectura_nada",
                   motivo=MOTIVOS["buzon_vacio"], motivo_codigo="buzon_vacio",
                   tomada_en=ahora, pdf_nuevos=0, pdf_ya_leidos=0,
                   datos={"motivo_codigo": "buzon_vacio"})
            return Tomada(actual["id"], VACIO, MOTIVOS["buzon_vacio"])
        if actual is not None:
            _pasar(conn, actual["id"], ("pedida",), "comprobando", tipo="lectura_tomada",
                   tomada_en=ahora)
            return Tomada(actual["id"], TOMADA)
        solicitud_id = conn.execute(
            "INSERT INTO solicitud_lectura (origen, pedida_en, estado, tomada_en, "
            "actualizada_en) VALUES ('lector', ?, 'comprobando', ?, ?)",
            (ahora, ahora, ahora)).lastrowid
        _evento(conn, "lectura_pedida", solicitud_id, datos={"origen": "lector"})
    return Tomada(solicitud_id, CREADA)


def cerrar(conn: sqlite3.Connection, solicitud_id: int, codigo: str, *,
           detalle: str | None = None, solo_si_viva: bool = False) -> bool:
    """El lector termina una peticion que no llega a leer, o que se quedo a medias: fallida
    con su motivo. Si ya no estaba viva (se cancelo, la cerro otro), no cambia nada y da
    False. Con una pasada en curso, la pasada termina fallida tambien."""
    if codigo not in MOTIVOS:
        raise ValueError(f"motivo desconocido: {codigo!r} (uno de {', '.join(MOTIVOS)})")
    motivo = MOTIVOS[codigo] + (f": {detalle}" if detalle else "")
    with transaccion(conn):
        fila = _fila(conn, solicitud_id)
        if fila["estado"] not in VIVOS:
            return False
        if solo_si_viva and fila["estado"] == "pedida":
            return False
        _terminar_pasada(conn, solicitud_id, "fallida", motivo)
        _pasar(conn, solicitud_id, VIVOS, "fallida", tipo="lectura_fallida", motivo=motivo,
               motivo_codigo=codigo, datos={"motivo_codigo": codigo})
    return True


def _sigue(conn: sqlite3.Connection, solicitud_id: int, estados: tuple[str, ...]) -> sqlite3.Row:
    """La peticion, si sigue donde el lector la dejo; si no (se cancelo), Parada."""
    fila = _fila(conn, solicitud_id)
    if fila["estado"] not in estados:
        raise Parada(fila["estado"])
    return fila


def _senal(conn: sqlite3.Connection, solicitud_id: int, estados: tuple[str, ...]) -> None:
    """El lector sigue vivo (y la peticion, donde la dejo): actualizada_en a ahora."""
    with transaccion(conn):
        _sigue(conn, solicitud_id, estados)
        conn.execute("UPDATE solicitud_lectura SET actualizada_en = ? WHERE id = ?",
                     (marca(_ahora(conn)), solicitud_id))


# ---- contar

@dataclass(frozen=True)
class Contado:
    """Un PDF del buzon en la cuenta: nuevo (con su entrada contada y lo que puede costar),
    ya leido (no se paga) u omitido (no se lee: no es un PDF, o es de la otra base)."""

    nombre: str
    sha256: str | None
    clase: str
    entrada: int = 0
    bajo_usd_micro: int | None = 0
    alto_usd_micro: int | None = 0
    detalle: str | None = None


@dataclass
class Estimacion:
    """Lo que costaria leer el buzon, documento a documento. La salida va en horquilla
    (coste.estimar_salida); la entrada, contada."""

    modelo: str
    prompt_version: str
    schema_version: str
    salida_baja: int
    salida_alta: int
    salida_medida: bool
    origen_salida: str
    documentos: list[Contado] = field(default_factory=list)

    def de_clase(self, clase: str) -> list[Contado]:
        return [d for d in self.documentos if d.clase == clase]

    @property
    def nuevos(self) -> int:
        return len(self.de_clase("nuevo"))

    @property
    def ya_leidos(self) -> int:
        return len(self.de_clase("ya_leido"))

    def _suma(self, columna: str) -> int | None:
        valores = [getattr(d, columna) for d in self.de_clase("nuevo")]
        return None if any(v is None for v in valores) else sum(valores)

    @property
    def coste_min_usd_micro(self) -> int | None:
        return self._suma("bajo_usd_micro")

    @property
    def coste_max_usd_micro(self) -> int | None:
        return self._suma("alto_usd_micro")

    def a_json(self) -> dict[str, Any]:
        return {"modelo": self.modelo, "prompt_version": self.prompt_version,
                "schema_version": self.schema_version,
                "salida": [self.salida_baja, self.salida_alta], "medida": self.salida_medida,
                "documentos": [{"nombre": d.nombre, "sha256": d.sha256, "clase": d.clase,
                                "entrada": d.entrada, "bajo_usd_micro": d.bajo_usd_micro,
                                "alto_usd_micro": d.alto_usd_micro}
                               for d in self.documentos]}

    def huella(self, solicitud_id: int) -> str:
        """Lo que se aprueba: esta peticion, este modelo y estas versiones, cada documento con
        lo que se le conto y la horquilla. Si algo de eso cambia, el si no vale."""
        return sha256_texto(json_canonico({
            "solicitud": solicitud_id, **self.a_json(),
            "coste_min_usd_micro": self.coste_min_usd_micro,
            "coste_max_usd_micro": self.coste_max_usd_micro}))

    def para_coste(self) -> Any:
        """La misma cuenta como la de `coste --estimar`, para escribirla igual."""
        from . import coste

        return coste.Estimacion(
            modelo=self.modelo, en_cache=self.ya_leidos, nuevos=self.nuevos,
            entrada=sum(d.entrada for d in self.de_clase("nuevo")),
            salida_baja=self.salida_baja * self.nuevos, salida_alta=self.salida_alta * self.nuevos,
            salida_medida=self.salida_medida, origen_salida=self.origen_salida)


def estimar(client: Any, pdfs: Iterable[str | Path], out_dir: str | Path, *, almacen: Any,
            politica: str | None = None, otras_vias: Iterable[str | Path] = (),
            antes: Callable[[str], None] | None = None) -> Estimacion:
    """Cuenta lo que costaria leer estos PDF, sin pagar nada: lo ya leido lo decide lo mismo
    que la pasada (extract.Conocido) y cada nuevo se cuenta con la API (count_tokens, que no
    se cobra). `antes(nombre)` va antes de cada PDF: el lector mira ahi si le dijeron que no."""
    from . import coste
    from . import config
    from .cache import CONSERVAR
    from .documents import UnsupportedDocument, load_pdf
    from .extract import Conocido, build_request
    from .pricing import estimate_cost

    modelo = config.model_id()
    conocido = Conocido.de(out_dir, model=modelo, politica=politica or CONSERVAR,
                           almacen=almacen, otras_vias=otras_vias)
    salida = coste.estimar_salida(coste.documentos_del_almacen(almacen.conn), modelo=modelo,
                                  esquema=config.SCHEMA_VERSION, esfuerzo=config.effort())
    est = Estimacion(modelo, config.PROMPT_VERSION, config.SCHEMA_VERSION, salida.bajo,
                     salida.alto, salida.medida, salida.origen)
    vistos: set[str] = set()
    for ruta in pdfs:
        ruta = Path(ruta)
        if antes is not None:
            antes(ruta.name)
        try:
            doc = load_pdf(ruta)
        except UnsupportedDocument as exc:
            est.documentos.append(Contado(ruta.name, None, "omitido", detalle=str(exc)))
            continue
        clase, detalle = conocido.clase(doc)
        if clase == "nuevo" and doc.sha256 in vistos:
            clase, detalle = "ya_leido", "el mismo PDF esta dos veces en el buzon: se paga una"
        vistos.add(doc.sha256)
        if clase != "nuevo":
            est.documentos.append(Contado(ruta.name, doc.sha256, clase, detalle=detalle))
            continue
        entrada = coste.contar_entrada(client, build_request(doc, model=modelo))
        est.documentos.append(Contado(
            ruta.name, doc.sha256, "nuevo", entrada,
            micro(estimate_cost(modelo, entrada, salida.bajo)),
            micro(estimate_cost(modelo, entrada, salida.alto))))
    return est


def contar(conn: sqlite3.Connection, solicitud_id: int,
           estimar_buzon: Callable[[Callable[[str], None]], Estimacion]) -> tuple[str, Estimacion | None]:
    """El lector, con la salida encendida y el aislamiento bien, cuenta lo que costaria.

    comprobando -> contando; despues, segun la cuenta: esperando_aprobacion (con la
    estimacion, su huella y hasta cuando vale el si), nada_que_leer (nada nuevo) o fallida
    (sin tarifa). Si mientras cuenta le dicen que no, para (Parada) sin escribir nada mas.
    Devuelve el estado en que queda y la estimacion."""
    _pasar(conn, solicitud_id, ("comprobando",), "contando", tipo="lectura_contando")
    est = estimar_buzon(lambda _nombre: _senal(conn, solicitud_id, ("contando",)))
    ahora = _ahora(conn)
    with transaccion(conn):
        _sigue(conn, solicitud_id, ("contando",))
        cuentas = {"pdf_nuevos": est.nuevos, "pdf_ya_leidos": est.ya_leidos,
                   "contada_en": marca(ahora)}
        datos = {"nuevos": est.nuevos, "ya_leidos": est.ya_leidos,
                 "omitidos": len(est.de_clase("omitido")),
                 "coste_min_usd_micro": est.coste_min_usd_micro,
                 "coste_max_usd_micro": est.coste_max_usd_micro}
        if not est.nuevos:
            codigo = "ya_leidas" if est.ya_leidos else "buzon_vacio"
            _pasar(conn, solicitud_id, ("contando",), "nada_que_leer", tipo="lectura_nada",
                   motivo=MOTIVOS[codigo], motivo_codigo=codigo, coste_min_usd_micro=0,
                   coste_max_usd_micro=0, **cuentas, datos=datos)
            return "nada_que_leer", est
        if est.coste_max_usd_micro is None or est.coste_min_usd_micro is None:
            _pasar(conn, solicitud_id, ("contando",), "fallida", tipo="lectura_fallida",
                   motivo=MOTIVOS["sin_tarifa"], motivo_codigo="sin_tarifa", **cuentas,
                   datos={**datos, "motivo_codigo": "sin_tarifa"})
            return "fallida", est
        huella = est.huella(solicitud_id)
        _pasar(conn, solicitud_id, ("contando",), "esperando_aprobacion",
               tipo="lectura_contada", **cuentas,
               coste_min_usd_micro=est.coste_min_usd_micro,
               coste_max_usd_micro=est.coste_max_usd_micro, huella_estimacion=huella,
               estimacion_json=json_canonico(est.a_json()),
               caduca_en=marca(ahora + PLAZO_RESPUESTA),
               datos={**datos, "huella": huella})
    return "esperando_aprobacion", est


# ---- esperar el si

def es_si(texto: str | None) -> bool:
    """"si", "si" con tilde o "s", en mayusculas o no (como Es-Si de los scripts)."""
    limpio = (texto or "").strip().lower().replace(chr(0x00ED), "i")
    return limpio in ("si", "s")


def aprobar_en_ventana(conn: sqlite3.Connection, solicitud_id: int) -> int:
    """El si escrito en la ventana del lector: lo da quien la tiene delante, con el tope en
    el extremo alto de la horquilla que la ventana acaba de ensenar."""
    with transaccion(conn):
        fila = _sigue(conn, solicitud_id, ("esperando_aprobacion",))
        if _ahora(conn) >= _instante(fila["caduca_en"]):
            raise Parada("caducada")
        tope = fila["coste_max_usd_micro"]
        return _pasar(conn, solicitud_id, ("esperando_aprobacion",), "aprobada",
                      tipo="lectura_aceptada", aprobada_en=marca(_ahora(conn)),
                      aprobada_via="ventana", tope_usd_micro=tope,
                      huella_aprobada=fila["huella_estimacion"],
                      datos={"via": "ventana", "tope_usd_micro": tope,
                             "huella": fila["huella_estimacion"]})


def cancelar_en_ventana(conn: sqlite3.Connection, solicitud_id: int) -> bool:
    """Otra cosa que "si" escrita en la ventana: no se lee. Tambien si la app acababa de dar
    el si y el lector aun no ha empezado: con dos respuestas distintas, no se gasta."""
    try:
        _pasar(conn, solicitud_id, ("esperando_aprobacion", "aprobada"), "cancelada",
               tipo="lectura_cancelada", cancelada_en=marca(_ahora(conn)),
               cancelada_via="ventana", datos={"via": "ventana"})
    except EstadoNoValido:
        return False
    return True


def caducar(conn: sqlite3.Connection, solicitud_id: int) -> bool:
    """Nadie dijo que si en el plazo: caducada (el lector apaga la salida sin gastar nada).
    False si ya no esperaba (otro respondio mientras tanto)."""
    try:
        _pasar(conn, solicitud_id, ("esperando_aprobacion",), "caducada",
               tipo="lectura_caducada")
    except EstadoNoValido:
        return False
    return True


def esperar(conn: sqlite3.Connection, solicitud_id: int, *,
            linea: Callable[[float], str | None], cada: float = CONSULTA_CADA) -> str:
    """El lector espera el si: de la app (mira la peticion cada `cada` segundos) o escrito en
    su ventana (`linea(segundos)` devuelve lo escrito, o None si en ese rato no se escribio
    nada). Lo que llegue antes. A los PLAZO_RESPUESTA, caducada. Devuelve "aprobada",
    "cancelada", "caducada" o el estado en que la encontro (si la cerro otro). Mientras
    espera, da senales cada LATIDO: sin ellas, otro lector puede volver a contarla."""
    ultima_senal = None
    while True:
        fila = _fila(conn, solicitud_id)
        if fila["estado"] != "esperando_aprobacion":
            return fila["estado"]
        ahora = _ahora(conn)
        caduca = _instante(fila["caduca_en"])
        if ahora >= caduca:
            if caducar(conn, solicitud_id):
                return "caducada"
            continue
        if ultima_senal is None or ahora - ultima_senal >= LATIDO:
            try:
                _senal(conn, solicitud_id, ("esperando_aprobacion",))
            except Parada:
                continue
            ultima_senal = ahora
        escrito = linea(min(cada, (caduca - ahora).total_seconds()))
        if escrito is None:
            continue
        if es_si(escrito):
            try:
                aprobar_en_ventana(conn, solicitud_id)
            except (Parada, EstadoNoValido):
                continue
            return "aprobada"
        cancelar_en_ventana(conn, solicitud_id)
        return _fila(conn, solicitud_id)["estado"]


# ---- leer

class _Seguimiento:
    """Lo que el lector apunta en pasada_lectura mientras lee (extract.Seguimiento), y el tope.

    Cada paso de cada documento se escribe en seguida (cada uno en su transaccion; dentro de
    la de tipar y pasar las reglas, con ella): la app lo ve en su siguiente consulta. Tocar
    la pasada es tambien la senal de que el lector sigue vivo."""

    def __init__(self, conn: sqlite3.Connection, solicitud_id: int, pasada_id: int, *,
                 modelo: str, tope: int, altos: dict[str, int],
                 imprimir: Callable[[str, str, str], None] | None = None) -> None:
        self.conn, self.solicitud_id, self.pasada_id = conn, solicitud_id, pasada_id
        self.modelo, self.tope, self.altos = modelo, tope, altos
        self.imprimir = imprimir or (lambda _t, _n, _d: None)
        self.gastado = 0
        self.parada: str | None = None
        self.motivo_parada: str | None = None
        self.estados: dict[str, str] = {}
        self.orden: list[str] = []
        self._alto_actual = 0

    # -- la fila

    def _escribir(self, **columnas: Any) -> None:
        ahora = marca(_ahora(self.conn))
        columnas["actualizada_en"] = ahora
        asignaciones = ", ".join(f"{c} = ?" for c in columnas)
        with transaccion(self.conn):
            self.conn.execute(f"UPDATE pasada_lectura SET {asignaciones} WHERE id = ?",
                              (*columnas.values(), self.pasada_id))

    def _cuentas(self) -> dict[str, Any]:
        valores = list(self.estados.values())
        return {"leidas": valores.count("leida"), "ya_leidas": valores.count("ya_leida"),
                "fallidas": valores.count("fallida"),
                "resultado_json": json_canonico([
                    {"nombre": n, "estado": self.estados[n]} for n in self.orden
                    if self.estados[n] != "sin_leer"])}

    def _anotar(self, nombre: str, estado: str) -> None:
        if nombre not in self.estados:
            self.orden.append(nombre)
        # Lo que fallo, fallo: un error al guardar despues de leer no lo arregla el "ok".
        if self.estados.get(nombre) != "fallida":
            self.estados[nombre] = estado

    def fase(self, fase: str) -> None:
        fila = self.conn.execute("SELECT fases_json FROM pasada_lectura WHERE id = ?",
                                 (self.pasada_id,)).fetchone()
        fases = json.loads(fila[0]) + [{"fase": fase, "en": marca(_ahora(self.conn))}]
        extra: dict[str, Any] = {}
        if fase != "leyendo":
            extra = {"documento_actual": None, "documento_fase": None}
        self._escribir(fase=fase, fases_json=json_canonico(fases), **extra)

    # -- extract.Seguimiento

    def empieza(self, nombre: str, que: str) -> None:
        fase = self.conn.execute("SELECT fase FROM pasada_lectura WHERE id = ?",
                                 (self.pasada_id,)).fetchone()[0]
        if fase == "cargando":
            self.fase("leyendo")
        self._escribir(documento_actual=nombre, documento_fase=que)

    def cabe(self, doc: Any) -> str | None:
        alto = self.altos.get(doc.sha256)
        if alto is None:
            return "no estaba entre las nuevas que se aprobaron: se contara la proxima vez"
        if self.parada is not None:
            return self.motivo_parada
        fila = _fila(self.conn, self.solicitud_id)
        if fila["estado"] != "leyendo" or fila["cancelada_en"] is not None:
            self.parada = "cancelada"
            self.motivo_parada = "se pidio parar la lectura: no se paga nada mas"
            return self.motivo_parada
        if self.gastado + alto > self.tope:
            self.parada = "tope"
            self.motivo_parada = (f"no cabe en el tope de {dolares(self.tope)}: "
                                  f"{dolares(self.gastado)} gastados mas lo que puede costar "
                                  f"este ({dolares(alto)})")
            return self.motivo_parada
        self._alto_actual = alto
        return None

    def pagado(self, uso: dict[str, Any] | None) -> None:
        from .pricing import estimate_cost

        coste = None
        if uso:
            entrada, salida = uso.get("input_tokens"), uso.get("output_tokens")
            if isinstance(entrada, int) and isinstance(salida, int):
                coste = micro(estimate_cost(self.modelo, entrada, salida,
                                            lote=uso.get("service_tier") == "batch"))
        # Sin uso no se sabe si se cobro: se cuenta como si si, por lo que podia costar.
        self.gastado += coste if coste is not None else self._alto_actual
        self._escribir(coste_usd_micro=self.gastado)

    def sin_pagar(self, nombre: str, motivo: str) -> None:
        self._anotar(nombre, "sin_leer")
        self.imprimir("sin_leer", nombre, motivo)

    # -- extract.Informar

    def informar(self, tipo: str, nombre: str, detalle: str) -> None:
        self._anotar(nombre, {"ok": "leida", "cache": "ya_leida"}.get(tipo, "fallida"))
        self._escribir(**self._cuentas())
        self.imprimir(tipo, nombre, detalle)


@dataclass
class Leida:
    """Como acabo la lectura: el estado de la peticion, la fase de la pasada y lo de cada
    documento."""

    estado: str
    fase: str
    resultado: list[dict[str, Any]] = field(default_factory=list)
    gastado_usd_micro: int = 0
    fallidas: int = 0
    errores_tipado: int = 0
    motivo: str | None = None

    def cuenta(self, estado: str) -> int:
        return sum(1 for r in self.resultado if r["estado"] == estado)


def _terminar_pasada(conn: sqlite3.Connection, solicitud_id: int, fase: str,
                     motivo: str | None) -> None:
    """Termina la pasada en curso de una peticion, si la tiene (fallida o cancelada)."""
    ahora = marca(_ahora(conn))
    conn.execute(
        "UPDATE pasada_lectura SET fase = ?, motivo = ?, documento_actual = NULL, "
        "documento_fase = NULL, terminada_en = ?, actualizada_en = ? "
        "WHERE solicitud_id = ? AND terminada_en IS NULL",
        (fase, motivo, ahora, ahora, solicitud_id))


def _duplicado(conn: sqlite3.Connection, factura_id: int) -> bool:
    marcas = ", ".join("?" * len(REGLAS_DUPLICADO))
    return conn.execute(
        f"SELECT 1 FROM hallazgo AS h WHERE h.regla IN ({marcas}) AND h.estado = 'abierto' "
        "AND (h.factura_id = ? OR EXISTS (SELECT 1 FROM hallazgo_objetivo AS o "
        "WHERE o.hallazgo_id = h.id AND o.tabla = 'factura' AND o.fila_id = ?))",
        (*REGLAS_DUPLICADO, factura_id, factura_id)).fetchone() is not None


def _resultado(conn: sqlite3.Connection, seguimiento: _Seguimiento, sha_de: dict[str, str],
               errores_tipado: set[int]) -> list[dict[str, Any]]:
    """Lo que fue de cada documento, con su factura: nueva, ya_leida (el mismo fichero: no se
    vuelve a pagar), posible_duplicado (otro PDF con la misma factura: B2-B5, espera a una
    persona) o fallida. Los que se quedaron sin leer (el tope, parar) no estan: se cuentan
    la proxima vez."""
    salida = []
    for nombre in seguimiento.orden:
        estado = seguimiento.estados[nombre]
        if estado == "sin_leer":
            continue
        documento = conn.execute("SELECT id FROM documento WHERE sha256 = ?",
                                 (sha_de.get(nombre),)).fetchone()
        documento_id = documento["id"] if documento is not None else None
        factura = None
        if documento_id is not None:
            factura = conn.execute(
                "SELECT f.id, f.numero, coalesce(p.nombre, c.nombre, CASE WHEN f.sentido = "
                "'entrante' THEN f.emisor_nombre_doc ELSE f.receptor_nombre_doc END) AS empresa "
                "FROM factura AS f LEFT JOIN proveedor AS p ON p.id = f.proveedor_id "
                "LEFT JOIN cliente AS c ON c.id = f.cliente_id "
                "WHERE f.documento_id = ? AND f.fusionada_en_id IS NULL ORDER BY f.id LIMIT 1",
                (documento_id,)).fetchone()
        if estado == "leida":
            if documento_id is None or documento_id in errores_tipado:
                estado = "fallida"
            elif factura is not None and _duplicado(conn, factura["id"]):
                estado = "posible_duplicado"
            else:
                estado = "nueva"
        salida.append({"documento_id": documento_id, "nombre": nombre, "estado": estado,
                       "factura_id": factura["id"] if factura is not None else None,
                       "numero": factura["numero"] if factura is not None else None,
                       "empresa": factura["empresa"] if factura is not None else None})
    return salida


def empezar(conn: sqlite3.Connection, solicitud_id: int, total: int, *,
            imprimir: Callable[[str, str, str], None] | None = None) -> _Seguimiento:
    """aprobada -> leyendo y la pasada nueva, cargando, con `total` documentos: el seguimiento
    con que se lee. EstadoNoValido si ya no esta aprobada."""
    fila = _fila(conn, solicitud_id)
    estimacion = json.loads(fila["estimacion_json"] or "{}")
    altos = {d["sha256"]: d["alto_usd_micro"] for d in estimacion.get("documentos", ())
             if d["sha256"] and d["clase"] == "nuevo"}
    ahora = marca(_ahora(conn))
    with transaccion(conn):
        _pasar(conn, solicitud_id, ("aprobada",), "leyendo", tipo="lectura_empezada",
               datos={"documentos": total, "tope_usd_micro": fila["tope_usd_micro"]})
        pasada_id = conn.execute(
            "INSERT INTO pasada_lectura (solicitud_id, fase, total, fases_json, empezada_en, "
            "actualizada_en) VALUES (?, 'cargando', ?, ?, ?, ?)",
            (solicitud_id, total, json_canonico([{"fase": "cargando", "en": ahora}]),
             ahora, ahora)).lastrowid
    return _Seguimiento(conn, solicitud_id, pasada_id, modelo=estimacion.get("modelo", ""),
                        tope=fila["tope_usd_micro"], altos=altos, imprimir=imprimir)


def terminar(conn: sqlite3.Connection, seguimiento: _Seguimiento,
             resultado: list[dict[str, Any]], *, errores_tipado: int = 0) -> Leida:
    """La pasada termina (hecha, tope o cancelada, segun por que paro) con lo que fue de cada
    documento, y la peticion con ella: hecha, o cancelada si se pidio parar."""
    solicitud_id, pasada_id = seguimiento.solicitud_id, seguimiento.pasada_id
    fase = seguimiento.parada or "hecha"
    estado = "cancelada" if fase == "cancelada" else "hecha"
    actual = _fila(conn, solicitud_id)
    if actual["estado"] != "leyendo":
        # Otro la dio por abandonada mientras tanto (y termino su pasada): lo leido queda
        # guardado, y la peticion como la dejo.
        return Leida(actual["estado"], fase, resultado, seguimiento.gastado,
                     motivo=actual["motivo"])
    cuentas = {"leidas": sum(1 for r in resultado if r["estado"] in ("nueva",
                                                                    "posible_duplicado")),
               "ya_leidas": sum(1 for r in resultado if r["estado"] == "ya_leida"),
               "fallidas": sum(1 for r in resultado if r["estado"] == "fallida")}
    ahora = marca(_ahora(conn))
    with transaccion(conn):
        fases = json.loads(conn.execute("SELECT fases_json FROM pasada_lectura WHERE id = ?",
                                        (pasada_id,)).fetchone()[0])
        conn.execute(
            "UPDATE pasada_lectura SET fase = ?, leidas = ?, ya_leidas = ?, fallidas = ?, "
            "resultado_json = ?, fases_json = ?, motivo = ?, documento_actual = NULL, "
            "documento_fase = NULL, terminada_en = ?, actualizada_en = ? WHERE id = ?",
            (fase, cuentas["leidas"], cuentas["ya_leidas"], cuentas["fallidas"],
             json_canonico(resultado), json_canonico(fases + [{"fase": fase, "en": ahora}]),
             seguimiento.motivo_parada, ahora, ahora, pasada_id))
        datos = {"fase": fase, **cuentas, "gastado_usd_micro": seguimiento.gastado,
                 "sin_leer": sum(1 for e in seguimiento.estados.values() if e == "sin_leer"),
                 "nuevas": sum(1 for r in resultado if r["estado"] == "nueva"),
                 "posibles_duplicados": sum(1 for r in resultado
                                            if r["estado"] == "posible_duplicado")}
        _pasar(conn, solicitud_id, ("leyendo",), estado, tipo="lectura_terminada",
               motivo=seguimiento.motivo_parada, datos=datos)
    return Leida(estado, fase, resultado, seguimiento.gastado, cuentas["fallidas"],
                 errores_tipado, seguimiento.motivo_parada)


def leer(conn: sqlite3.Connection, solicitud_id: int, *, client: Any, almacen: Any,
         pdfs: Iterable[str | Path], out_dir: str | Path, politica: str | None = None,
         otras_vias: Iterable[str | Path] = (),
         imprimir: Callable[[str, str, str], None] | None = None) -> Leida:
    """Lee con el si: aprobada -> leyendo, la pasada de siempre (ingesta.ingestar_pasada)
    con su progreso en pasada_lectura, y al final hecha (o cancelada, si se pidio parar).

    Solo se leen los PDF que se contaron (un PDF que llego despues espera a la proxima), solo
    se paga lo que se conto como nuevo y nada pasa del tope. Si la estimacion de la peticion
    no es la que se aprobo, no se lee nada. Si algo falla (tambien Ctrl+C), la pasada y la
    peticion terminan fallidas y el error sigue hacia arriba: lo ya leido queda guardado."""
    from . import config
    from .cache import CONSERVAR
    from .ingesta import ingestar_pasada

    fila = _fila(conn, solicitud_id)
    if fila["estado"] != "aprobada":
        # Se dijo que no (o la cerro otro) entre el si y empezar: no se lee nada.
        return Leida(fila["estado"], "")
    estimacion = json.loads(fila["estimacion_json"] or "{}")
    # El si es para lo que se conto, con el modelo y las versiones con que se conto: si la
    # configuracion cambio entre contar y leer, no es lo que se aprobo.
    misma = (estimacion.get("modelo"), estimacion.get("prompt_version"),
             estimacion.get("schema_version")) == (config.model_id(), config.PROMPT_VERSION,
                                                   config.SCHEMA_VERSION)
    if fila["huella_aprobada"] != fila["huella_estimacion"] or not misma:
        cerrar(conn, solicitud_id, "estimacion")
        return Leida("fallida", "", motivo=MOTIVOS["estimacion"])
    contados = {d["sha256"] for d in estimacion["documentos"] if d["sha256"]}
    elegidos, sha_de = [], {}
    for ruta in pdfs:
        ruta = Path(ruta)
        try:
            sha = _sha256_de(ruta)
        except OSError:
            continue
        if sha in contados:
            elegidos.append(ruta)
            sha_de[ruta.name] = sha

    seguimiento = empezar(conn, solicitud_id, len(elegidos), imprimir=imprimir)
    try:
        _r, ingesta = ingestar_pasada(
            client, elegidos, out_dir, almacen=almacen, model=config.model_id(),
            politica=politica or CONSERVAR, forzar=False, informar=seguimiento.informar,
            ruta="entrante", otras_vias=list(otras_vias), seguimiento=seguimiento,
            fase=seguimiento.fase)
        seguimiento.fase("organizando")
        errores = {t.documento_id for t in ingesta.errores}
        resultado = _resultado(conn, seguimiento, sha_de, errores)
    except BaseException as exc:
        codigo = "lectura" if isinstance(exc, Exception) else "interrumpida"
        cerrar(conn, solicitud_id, codigo, detalle=f"{type(exc).__name__}: {exc}"
               if isinstance(exc, Exception) else None)
        raise
    return terminar(conn, seguimiento, resultado, errores_tipado=len(errores))


def _sha256_de(ruta: Path) -> str:
    import hashlib

    return hashlib.sha256(ruta.read_bytes()).hexdigest()


# ------------------------------------------------------------ lo que lee la app

def _persona(conn: sqlite3.Connection, usuario_id: int | None) -> dict[str, Any] | None:
    if usuario_id is None:
        return None
    fila = conn.execute("SELECT id, nombre FROM usuario WHERE id = ?", (usuario_id,)).fetchone()
    return {"id": fila["id"], "nombre": fila["nombre"]} if fila is not None else None


def _solicitud(conn: sqlite3.Connection, fila: sqlite3.Row, ahora: datetime) -> dict[str, Any]:
    return {
        "id": fila["id"], "estado": fila["estado"], "origen": fila["origen"],
        "viva": fila["estado"] in VIVOS, "abandonada": abandonada(conn, fila, ahora),
        "pedida_por": _persona(conn, fila["pedida_por"]), "pedida_en": fila["pedida_en"],
        "tomada_en": fila["tomada_en"], "motivo": fila["motivo"],
        "motivo_codigo": fila["motivo_codigo"],
        "pdf_nuevos": fila["pdf_nuevos"], "pdf_ya_leidos": fila["pdf_ya_leidos"],
        "coste_min_usd_micro": fila["coste_min_usd_micro"],
        "coste_max_usd_micro": fila["coste_max_usd_micro"],
        "huella_estimacion": fila["huella_estimacion"], "contada_en": fila["contada_en"],
        "caduca_en": fila["caduca_en"],
        "aprobada_por": _persona(conn, fila["aprobada_por"]), "aprobada_en": fila["aprobada_en"],
        "aprobada_via": fila["aprobada_via"], "tope_usd_micro": fila["tope_usd_micro"],
        "cancelada_por": _persona(conn, fila["cancelada_por"]),
        "cancelada_en": fila["cancelada_en"], "cancelada_via": fila["cancelada_via"],
        "parar_pedido": fila["estado"] == "leyendo" and fila["cancelada_en"] is not None,
        "terminada_en": fila["terminada_en"], "actualizada_en": fila["actualizada_en"],
    }


def _pasada(fila: sqlite3.Row) -> dict[str, Any]:
    resultado = json.loads(fila["resultado_json"])
    terminados = [r for r in resultado if r["nombre"] != fila["documento_actual"]]
    return {
        "solicitud_id": fila["solicitud_id"], "fase": fila["fase"],
        "terminada": fila["terminada_en"] is not None,
        "total": fila["total"], "leidas": fila["leidas"], "ya_leidas": fila["ya_leidas"],
        "fallidas": fila["fallidas"], "coste_usd_micro": fila["coste_usd_micro"],
        "documento_actual": fila["documento_actual"], "documento_fase": fila["documento_fase"],
        "recientes": [r["nombre"] for r in terminados[-RECIENTES:]],
        "fases": json.loads(fila["fases_json"]), "motivo": fila["motivo"],
        "empezada_en": fila["empezada_en"], "terminada_en": fila["terminada_en"],
        "actualizada_en": fila["actualizada_en"], "resultado": resultado,
    }


def para_la_app(conn: sqlite3.Connection) -> dict[str, Any]:
    """Lo que GET /api/v2/lectura anade (paso 17, contrato 2.5): `solicitud` (la viva o la
    ultima), `pasada_en_curso` (la pasada de esa peticion, si la tiene, con lo que fue de
    cada documento hasta ahora) y `ultima_pasada` (la ultima terminada, con su resultado: lo
    que Documentos pinta de verde y de naranja hasta la siguiente). Sin red: solo lee."""
    ahora = _ahora(conn)
    fila = viva(conn) or conn.execute(
        "SELECT * FROM solicitud_lectura ORDER BY id DESC LIMIT 1").fetchone()
    pasada = None
    if fila is not None:
        pasada = conn.execute("SELECT * FROM pasada_lectura WHERE solicitud_id = ?",
                              (fila["id"],)).fetchone()
    ultima = conn.execute("SELECT * FROM pasada_lectura WHERE terminada_en IS NOT NULL "
                          "ORDER BY id DESC LIMIT 1").fetchone()
    return {"solicitud": _solicitud(conn, fila, ahora) if fila is not None else None,
            "pasada_en_curso": _pasada(pasada) if pasada is not None else None,
            "ultima_pasada": _pasada(ultima) if ultima is not None else None,
            "plazo_respuesta_segundos": int(PLAZO_RESPUESTA.total_seconds()),
            "consulta_cada_segundos": CONSULTA_CADA}
