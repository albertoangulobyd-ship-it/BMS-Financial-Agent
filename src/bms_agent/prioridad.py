"""La prioridad (spec §8): suelos, puntos y lo que sube una persona.

`calcular(entradas, hoy, pesos)` es una funcion pura: no lee la base, ni el
reloj, ni ficheros. Recibe lo que se sabe de una factura (sus hallazgos
pendientes, si necesita que alguien actue, su vencimiento, su importe, su
excepcion) y devuelve el nivel, los puntos, el suelo y los motivos. Asi el
mismo caso da siempre la misma prioridad, y un test la recorre entera.

Dos capas, y lo que pone una persona:

1. **Suelo.** El nivel minimo que imponen los hallazgos abiertos y sin
   anular (bloqueada, urgente, atencion). Esta en el codigo y no en la
   politica: es la parte dura, la que dice que un IBAN sin verificar bloquea
   aunque alguien ajuste los pesos.
2. **Puntos.** Plazos, vencimiento, importe, planning, facturacion, PO, IVA y
   anomalias, con los pesos de config/prioridad.yaml (`Pesos`). Los de plazo,
   vencimiento e importe solo cuentan si la factura necesita que alguien
   actue: tiene una excepcion abierta o no esta revisada. Los puntos dan
   normal, atencion o urgente, nunca bloqueada.
3. **Subida a mano.** Una persona puede subir una prioridad, con un motivo y
   hasta una fecha; nadie puede bajarla. El nivel final es el mayor de los
   tres, asi que una subida nunca baja nada, y bloqueada tiene siempre una
   regla con nombre detras (no se sube a mano a bloqueada).

Los motivos empiezan por el del suelo y siguen con cada aportacion, para que
quien mira sepa por que una factura esta arriba: "Bloqueada: ... (F3) · vence
en 2 días +20 · importe 12.400,00 ≥ 10.000 +10".

`agregar` da la prioridad de lo que tiene facturas (proveedor, cliente,
Objeto, trimestre): el maximo de sus hijas. `de_excepcion`, la de una
excepcion: el maximo de los suelos de sus hallazgos y el nivel de su
factura. `clave_orden` es el orden de todas las listas.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

import yaml

from .dominio import EntradaPrioridad, Prioridad, Sentido, Severidad
from .reloj import proximo_limite_btw

NORMAL = Prioridad.NORMAL.value
ATENCION = Prioridad.ATENCION.value
URGENTE = Prioridad.URGENTE.value
BLOQUEADA = Prioridad.BLOQUEADA.value
NIVELES: tuple[str, ...] = (NORMAL, ATENCION, URGENTE, BLOQUEADA)
RANGO: dict[str, int] = {nivel: i for i, nivel in enumerate(NIVELES)}
# Lo que una persona puede pedir al subir una prioridad.
NIVELES_A_MANO: tuple[str, ...] = (ATENCION, URGENTE)

_B = Severidad.BLOQUEO.value
_R = Severidad.RETENCION.value
_E = EntradaPrioridad
ENTRANTE = Sentido.ENTRANTE.value
SALIENTE = Sentido.SALIENTE.value

ABIERTO = "abierto"
DESAPARECIDO = "desaparecido"

# ------------------------------------------------------------ suelos (codigo)

# Los que ponen una factura por lo menos en urgente (§8, capa 1).
REGLAS_URGENTES = frozenset({"B3", "B4", "B5", "V7", "F7", "P4", "P6", "P10", "K5"})
# Un hallazgo de IVA con el plazo del BTW a esta distancia o menos.
DIAS_IVA_URGENTE = 7
# Una compra vencida mas de esto que necesita accion; una venta, mas de esto.
DIAS_VENCIDA_URGENTE = {ENTRANTE: 30, SALIENTE: 60}
ENTRADAS_IVA = frozenset({_E.IVA_DURA.value, _E.IVA_BLANDA.value})

# Las entradas de los puntos, como texto: se miran en cada factura de cada pasada.
_PLANNING = _E.PLANNING.value
_FACTURACION_AUSENTE = _E.FACTURACION_AUSENTE.value
_TRABAJO_SIN_FACTURAR = _E.TRABAJO_SIN_FACTURAR.value
_LIMITE_PO = _E.LIMITE_PO.value
_CADUCIDAD_PO = _E.CADUCIDAD_PO.value
_IVA_BLANDA = _E.IVA_BLANDA.value
_OTRA = _E.OTRA.value

ETIQUETA = {NORMAL: "Normal", ATENCION: "Atención", URGENTE: "Urgente", BLOQUEADA: "Bloqueada"}
_A_QUIEN = {"proveedor": "al proveedor", "cliente": "al cliente", "contable": "al contable",
            "exact": "a Exact", "trnsprnt": "a TRNSPRNT", "banco": "al banco",
            "otro": "a alguien de fuera"}


# ------------------------------------------------------------ pesos (politica)

@dataclass(frozen=True)
class Tramo:
    """Un escalon de una tabla de puntos: a partir de (o hasta) `limite`, `puntos`."""

    limite: int
    puntos: int


@dataclass(frozen=True)
class Pesos:
    """Los puntos de la capa 2 (§8). Su texto es config/prioridad.yaml.

    Los importes van en euros enteros y los plazos en dias. `plazo_entrante`
    y `caducidad_po` son "hasta N dias"; `vencida_*` e `importe`, "desde N".
    Los extras de planning se suman uno detras de otro.
    """

    nivel_atencion: int = 20
    nivel_urgente: int = 40
    plazo_entrante: tuple[Tramo, ...] = (Tramo(3, 20), Tramo(7, 10))
    vencida_entrante: tuple[Tramo, ...] = (Tramo(1, 15), Tramo(15, 25), Tramo(31, 35))
    vencida_saliente: tuple[Tramo, ...] = (Tramo(1, 10), Tramo(15, 20), Tramo(31, 30))
    importe: tuple[Tramo, ...] = (Tramo(2500, 5), Tramo(10000, 10), Tramo(25000, 20))
    planning: int = 15
    planning_extras: tuple[Tramo, ...] = (Tramo(500, 10), Tramo(2500, 10))
    facturacion_ausente: int = 20
    sin_facturar_umbral: int = 1000
    sin_facturar_bajo: int = 15
    sin_facturar_alto: int = 25
    sin_facturar_por_semana: int = 5
    sin_facturar_maximo_extra: int = 20
    limite_po: int = 10
    caducidad_po: tuple[Tramo, ...] = (Tramo(7, 20), Tramo(30, 10))
    iva_blando: int = 20
    iva_blando_extra: int = 15
    iva_blando_extra_dias: int = 14
    otra_por_regla: int = 10
    otra_maximo: int = 20
    esperando_divisor: int = 2
    seguimiento_vencido: int = 10

    def como_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __post_init__(self) -> None:
        # El hash se calcula una vez: va en la huella de cada factura de cada pasada.
        texto = json.dumps(self.como_dict(), sort_keys=True, separators=(",", ":"))
        object.__setattr__(self, "_sha256", hashlib.sha256(texto.encode("utf-8")).hexdigest())

    def sha256(self) -> str:
        """El hash de los pesos que se aplican (va con cada resultado en las caches)."""
        return self._sha256


PESOS = Pesos()


class PesosNoValidos(ValueError):
    """El fichero de pesos no tiene la forma de config/prioridad.yaml."""


def _entero(valor: Any, donde: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
        raise PesosNoValidos(f"{donde}: se espera un entero de cero o mas, no {valor!r}")
    return valor


def _seccion(datos: Mapping[str, Any], clave: str, claves: set[str]) -> Mapping[str, Any]:
    valor = datos.get(clave)
    if not isinstance(valor, dict):
        raise PesosNoValidos(f"{clave}: falta o no es una seccion")
    sobran, faltan = set(valor) - claves, claves - set(valor)
    if sobran or faltan:
        raise PesosNoValidos(f"{clave}: sobran {sorted(sobran)} y faltan {sorted(faltan)}")
    return valor


def _tramos(valor: Any, donde: str, limite: str) -> tuple[Tramo, ...]:
    if not isinstance(valor, list) or not valor:
        raise PesosNoValidos(f"{donde}: se espera una lista de tramos")
    tramos = []
    for i, tramo in enumerate(valor):
        if not isinstance(tramo, dict) or set(tramo) != {limite, "puntos"}:
            raise PesosNoValidos(f"{donde}[{i}]: un tramo es {{{limite}: N, puntos: N}}")
        tramos.append(Tramo(_entero(tramo[limite], f"{donde}[{i}].{limite}"),
                            _entero(tramo["puntos"], f"{donde}[{i}].puntos")))
    limites = [t.limite for t in tramos]
    if limites != sorted(set(limites)):
        raise PesosNoValidos(f"{donde}: los tramos van ordenados de menor a mayor, sin repetir")
    return tuple(tramos)


_SECCIONES = {
    "niveles": {"atencion", "urgente"},
    "planning": {"puntos", "extras"},
    "trabajo_sin_facturar": {"umbral_euros", "puntos_bajo", "puntos_alto", "por_semana",
                             "maximo_extra"},
    "iva_blando": {"puntos", "extra", "extra_hasta_dias_btw"},
    "otra_anomalia": {"por_regla", "maximo"},
    "esperando_externo": {"divisor_plazos", "seguimiento_vencido"},
}
_CLAVES = set(_SECCIONES) | {"plazo_entrante", "vencida_entrante", "vencida_saliente", "importe",
                             "facturacion_ausente", "limite_po", "caducidad_po"}


def pesos_de_yaml(texto: str) -> Pesos:
    """Los pesos de un texto con la forma de config/prioridad.yaml, o PesosNoValidos.

    Se exige la forma entera, sin claves de mas ni de menos: un fichero que
    olvida una seccion no debe sacar de la nada los pesos de otra version.
    """
    try:
        datos = yaml.safe_load(texto)
    except yaml.YAMLError as exc:
        raise PesosNoValidos(f"no es YAML: {exc}") from None
    if not isinstance(datos, dict):
        raise PesosNoValidos("el fichero de pesos es un diccionario")
    sobran, faltan = set(datos) - _CLAVES, _CLAVES - set(datos)
    if sobran or faltan:
        raise PesosNoValidos(f"sobran {sorted(sobran)} y faltan {sorted(faltan)}")
    niveles = _seccion(datos, "niveles", _SECCIONES["niveles"])
    planning = _seccion(datos, "planning", _SECCIONES["planning"])
    sin_facturar = _seccion(datos, "trabajo_sin_facturar", _SECCIONES["trabajo_sin_facturar"])
    iva = _seccion(datos, "iva_blando", _SECCIONES["iva_blando"])
    otra = _seccion(datos, "otra_anomalia", _SECCIONES["otra_anomalia"])
    esperando = _seccion(datos, "esperando_externo", _SECCIONES["esperando_externo"])
    pesos = Pesos(
        nivel_atencion=_entero(niveles["atencion"], "niveles.atencion"),
        nivel_urgente=_entero(niveles["urgente"], "niveles.urgente"),
        plazo_entrante=_tramos(datos["plazo_entrante"], "plazo_entrante", "hasta_dias"),
        vencida_entrante=_tramos(datos["vencida_entrante"], "vencida_entrante", "desde_dias"),
        vencida_saliente=_tramos(datos["vencida_saliente"], "vencida_saliente", "desde_dias"),
        importe=_tramos(datos["importe"], "importe", "desde_euros"),
        planning=_entero(planning["puntos"], "planning.puntos"),
        planning_extras=_tramos(planning["extras"], "planning.extras", "desde_euros"),
        facturacion_ausente=_entero(datos["facturacion_ausente"], "facturacion_ausente"),
        sin_facturar_umbral=_entero(sin_facturar["umbral_euros"], "trabajo_sin_facturar"),
        sin_facturar_bajo=_entero(sin_facturar["puntos_bajo"], "trabajo_sin_facturar"),
        sin_facturar_alto=_entero(sin_facturar["puntos_alto"], "trabajo_sin_facturar"),
        sin_facturar_por_semana=_entero(sin_facturar["por_semana"], "trabajo_sin_facturar"),
        sin_facturar_maximo_extra=_entero(sin_facturar["maximo_extra"], "trabajo_sin_facturar"),
        limite_po=_entero(datos["limite_po"], "limite_po"),
        caducidad_po=_tramos(datos["caducidad_po"], "caducidad_po", "hasta_dias"),
        iva_blando=_entero(iva["puntos"], "iva_blando.puntos"),
        iva_blando_extra=_entero(iva["extra"], "iva_blando.extra"),
        iva_blando_extra_dias=_entero(iva["extra_hasta_dias_btw"], "iva_blando"),
        otra_por_regla=_entero(otra["por_regla"], "otra_anomalia.por_regla"),
        otra_maximo=_entero(otra["maximo"], "otra_anomalia.maximo"),
        esperando_divisor=_entero(esperando["divisor_plazos"], "esperando_externo"),
        seguimiento_vencido=_entero(esperando["seguimiento_vencido"], "esperando_externo"),
    )
    if not 0 < pesos.nivel_atencion < pesos.nivel_urgente:
        raise PesosNoValidos("niveles: atencion tiene que ser mayor que cero y menor que urgente")
    if pesos.esperando_divisor < 1:
        raise PesosNoValidos("esperando_externo.divisor_plazos es 1 o mas")
    return pesos


def pesos_a_yaml(pesos: Pesos) -> str:
    """El texto con la forma de config/prioridad.yaml que da estos pesos (sin comentarios).

    Es lo que se apunta en politica_version cuando se calcula sin haber
    cargado ningun fichero: pesos_de_yaml lo lee de vuelta y da los mismos.
    """
    def tramos(lista: tuple[Tramo, ...], limite: str) -> list[dict[str, int]]:
        return [{limite: t.limite, "puntos": t.puntos} for t in lista]

    datos = {
        "niveles": {"atencion": pesos.nivel_atencion, "urgente": pesos.nivel_urgente},
        "plazo_entrante": tramos(pesos.plazo_entrante, "hasta_dias"),
        "vencida_entrante": tramos(pesos.vencida_entrante, "desde_dias"),
        "vencida_saliente": tramos(pesos.vencida_saliente, "desde_dias"),
        "importe": tramos(pesos.importe, "desde_euros"),
        "planning": {"puntos": pesos.planning,
                     "extras": tramos(pesos.planning_extras, "desde_euros")},
        "facturacion_ausente": pesos.facturacion_ausente,
        "trabajo_sin_facturar": {
            "umbral_euros": pesos.sin_facturar_umbral, "puntos_bajo": pesos.sin_facturar_bajo,
            "puntos_alto": pesos.sin_facturar_alto, "por_semana": pesos.sin_facturar_por_semana,
            "maximo_extra": pesos.sin_facturar_maximo_extra},
        "limite_po": pesos.limite_po,
        "caducidad_po": tramos(pesos.caducidad_po, "hasta_dias"),
        "iva_blando": {"puntos": pesos.iva_blando, "extra": pesos.iva_blando_extra,
                       "extra_hasta_dias_btw": pesos.iva_blando_extra_dias},
        "otra_anomalia": {"por_regla": pesos.otra_por_regla, "maximo": pesos.otra_maximo},
        "esperando_externo": {"divisor_plazos": pesos.esperando_divisor,
                              "seguimiento_vencido": pesos.seguimiento_vencido},
    }
    return ("# Pesos de prioridad.Pesos, apuntados por la primera pasada sin fichero cargado.\n"
            + yaml.safe_dump(datos, sort_keys=True, allow_unicode=True))


# ------------------------------------------------------------ entradas

@dataclass(frozen=True)
class Hallazgo:
    """Lo que aporta un hallazgo pendiente: su regla, su severidad y su estado.

    `texto` es su explicacion (para el motivo); `valor_cent` lo que vale una
    discrepancia de planning o un trabajo sin facturar; `semanas_tras_gracia`
    y `dias_para_caducar` los de V6 y P7.
    """

    regla: str
    severidad: str
    estado: str
    entrada: str
    texto: str
    valor_cent: int | None = None
    semanas_tras_gracia: int | None = None
    dias_para_caducar: int | None = None


@dataclass(frozen=True)
class Subida:
    """Una prioridad subida a mano: hasta que nivel, por que, quien y hasta cuando."""

    nivel: str
    motivo: str
    quien: str = ""
    hasta: date | None = None

    def vigente(self, hoy: date) -> bool:
        return self.hasta is None or self.hasta >= hoy


@dataclass(frozen=True)
class Entradas:
    """Lo que se sabe de una factura para su prioridad.

    `en_juego` es falso si la factura no tiene plazo que correr ni importe
    que reclamar (pagada, anulada o fusionada en otra). `esperando_a` y `fecha_seguimiento` solo
    con su excepcion esperando a alguien de fuera.
    """

    sentido: str
    vencimiento: date | None = None
    en_juego: bool = True
    importe_cent: int | None = None
    fecha_factura: date | None = None
    hallazgos: tuple[Hallazgo, ...] = ()
    excepcion_abierta: bool = False
    revisada: bool = False
    esperando_a: str | None = None
    fecha_seguimiento: date | None = None
    dudosos: int = 0
    sin_resolver: int = 0
    subidas: tuple[Subida, ...] = ()

    @property
    def necesita_accion(self) -> bool:
        """Tiene una excepcion abierta o no esta revisada (§8, entradas)."""
        return self.excepcion_abierta or not self.revisada


@dataclass(frozen=True)
class Resultado:
    nivel: str
    puntos: int
    suelo: str
    motivos: tuple[str, ...] = field(default_factory=tuple)

    @property
    def texto(self) -> str:
        return " · ".join(self.motivos)


# ------------------------------------------------------------ texto

def euros(cent: int) -> str:
    """Un importe como se lee en la empresa: 12.400,00."""
    valor = Decimal(cent).scaleb(-2)
    return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _miles(euros_enteros: int) -> str:
    return f"{euros_enteros:,}".replace(",", ".")


def _dias(n: int) -> str:
    return "1 día" if n == 1 else f"{n} días"


def _frase(texto: str) -> str:
    return texto.strip().rstrip(".").strip()


def _reglas(hallazgos: Iterable[Hallazgo]) -> str:
    return ", ".join(sorted({h.regla for h in hallazgos}, key=_orden_regla))


def _orden_regla(regla: str) -> tuple[str, int, str]:
    """Q1 antes que Q2, D2 antes que D2b y P4 antes que P10."""
    letras = regla.rstrip("0123456789abcdefghijklmnopqrstuvwxyz")
    resto = regla[len(letras):]
    numero = "".join(c for c in resto if c.isdigit())
    return (letras, int(numero) if numero else 0, resto)


def _en_orden(hallazgos: Iterable[Hallazgo]) -> list[Hallazgo]:
    return sorted(hallazgos, key=lambda h: (_orden_regla(h.regla), h.texto))


# ------------------------------------------------------------ calculo

def _hasta(tramos: Sequence[Tramo], valor: int) -> int:
    """Los puntos del primer tramo "hasta N" que cubre el valor (0 si ninguno)."""
    for tramo in tramos:
        if valor <= tramo.limite:
            return tramo.puntos
    return 0


def _desde(tramos: Sequence[Tramo], valor: int) -> tuple[int, int | None]:
    """Los puntos del ultimo tramo "desde N" que alcanza el valor, y su limite."""
    puntos, limite = 0, None
    for tramo in tramos:
        if valor >= tramo.limite:
            puntos, limite = tramo.puntos, tramo.limite
    return puntos, limite


def dias_hasta_btw(fecha_factura: date | None, hoy: date) -> int | None:
    """Cuantos dias quedan para el plazo del BTW que le toca a la factura."""
    if fecha_factura is None:
        return None
    return (proximo_limite_btw(fecha_factura, hoy) - hoy).days


def nivel_de_puntos(puntos: int, pesos: Pesos = PESOS) -> str:
    """0-19 normal, 20-39 atencion, 40 o mas urgente. Nunca bloqueada."""
    if puntos >= pesos.nivel_urgente:
        return URGENTE
    if puntos >= pesos.nivel_atencion:
        return ATENCION
    return NORMAL


def mayor(*niveles: str) -> str:
    return max(niveles, key=RANGO.__getitem__)


def suelo_de(hallazgo: Hallazgo) -> str:
    """El suelo que pone un hallazgo solo (los de plazo e IVA son de la factura)."""
    if hallazgo.estado == ABIERTO:
        if hallazgo.severidad == _B:
            return BLOQUEADA
        if hallazgo.regla in REGLAS_URGENTES:
            return URGENTE
        if hallazgo.severidad == _R:
            return ATENCION
        return NORMAL
    return ATENCION if hallazgo.estado == DESAPARECIDO else NORMAL


def _suelo(e: Entradas, dias_btw: int | None, vencida: int) -> tuple[str, list[str]]:
    """El suelo de la factura y lo que lo explica, empezando por lo mas grave."""
    abiertos = _en_orden(h for h in e.hallazgos if h.estado == ABIERTO) if e.hallazgos else []
    bloqueos = [h for h in abiertos if h.severidad == _B]
    if bloqueos:
        return BLOQUEADA, [f"{_frase(h.texto)} ({h.regla})" for h in bloqueos]

    urgentes = [f"{_frase(h.texto)} ({h.regla})" for h in abiertos
                if h.regla in REGLAS_URGENTES]
    iva = [h for h in abiertos if h.entrada in ENTRADAS_IVA]
    if iva and dias_btw is not None and dias_btw <= DIAS_IVA_URGENTE:
        urgentes.append(f"IVA por resolver ({_reglas(iva)}) y el BTW vence en {_dias(dias_btw)}")
    limite = DIAS_VENCIDA_URGENTE.get(e.sentido)
    if limite is not None and vencida > limite and (e.sentido == SALIENTE or e.necesita_accion):
        porque = "" if e.sentido == SALIENTE else (
            " con una excepción abierta" if e.excepcion_abierta else " sin revisar")
        urgentes.append(f"vencida hace {_dias(vencida)}{porque}")
    if urgentes:
        return URGENTE, urgentes

    atencion = [f"retenida por {_frase(h.texto)} ({h.regla})" for h in abiertos
                if h.severidad == _R]
    if e.excepcion_abierta:
        atencion.append("excepción abierta")
    if e.dudosos:
        atencion.append(f"{e.dudosos} campo{'s' if e.dudosos > 1 else ''} dudoso"
                        f"{'s' if e.dudosos > 1 else ''} sin verificar (Q2)")
    if e.sin_resolver:
        atencion.append(f"{e.sin_resolver} cambio{'s' if e.sin_resolver > 1 else ''} manual"
                        f"{'es' if e.sin_resolver > 1 else ''} sin resolver (M1)")
    for h in _en_orden(h for h in e.hallazgos if h.estado == DESAPARECIDO) if e.hallazgos else ():
        atencion.append(f"{_frase(h.texto)} ({h.regla}): su condición ha desaparecido y nadie "
                        "lo ha cerrado")
    return (ATENCION, atencion) if atencion else (NORMAL, [])


def _puntos(e: Entradas, hoy: date, pesos: Pesos, dias: int | None, vencida: int,
            dias_btw: int | None) -> list[tuple[str, int]]:
    """Cada aportacion de puntos con su texto, en el orden en que se explican."""
    aportes: list[tuple[str, int]] = []
    plazos: list[tuple[str, int]] = []
    if e.necesita_accion and e.en_juego:
        if e.sentido == ENTRANTE and dias is not None and dias >= 0:
            puntos = _hasta(pesos.plazo_entrante, dias)
            if puntos:
                plazos.append(("vence hoy" if dias == 0 else f"vence en {_dias(dias)}", puntos))
        if vencida >= 1:
            tabla = pesos.vencida_entrante if e.sentido == ENTRANTE else pesos.vencida_saliente
            puntos, _limite = _desde(tabla, vencida)
            if puntos:
                plazos.append((f"vencida hace {_dias(vencida)}", puntos))
    esperando = e.esperando_a is not None and e.fecha_seguimiento is not None
    if esperando and e.fecha_seguimiento > hoy:
        a_quien = _A_QUIEN.get(e.esperando_a, e.esperando_a)
        plazos = [(f"{texto} (a la mitad: se espera {a_quien} hasta el "
                   f"{e.fecha_seguimiento.isoformat()})", puntos // pesos.esperando_divisor)
                  for texto, puntos in plazos]
    aportes.extend(plazos)
    # Como el plazo: lo que no esta en juego (anulada, fusionada, pagada) no pide
    # accion por lo que vale. Sin esto, una anulada grande quedaba en Atencion.
    if e.necesita_accion and e.en_juego and e.importe_cent is not None:
        puntos, limite = _desde(pesos.importe, abs(e.importe_cent) // 100)
        if puntos:
            aportes.append((f"importe {euros(abs(e.importe_cent))} ≥ {_miles(limite)}", puntos))

    if not e.hallazgos and not esperando:
        return [(texto, puntos) for texto, puntos in aportes if puntos]
    por_entrada: dict[str, list[Hallazgo]] = defaultdict(list)
    for h in e.hallazgos:
        if h.estado == ABIERTO:
            por_entrada[h.entrada].append(h)

    def de(entrada: str) -> list[Hallazgo]:
        return por_entrada.get(entrada, [])

    planning = de(_PLANNING)
    if planning:
        valor = sum(h.valor_cent or 0 for h in planning)
        puntos = pesos.planning
        for tramo in pesos.planning_extras:
            if valor >= tramo.limite * 100:
                puntos += tramo.puntos
        cuanto = f" por {euros(valor)}" if valor else ""
        aportes.append((f"discrepancia de planning ({_reglas(planning)}){cuanto}", puntos))
    ausente = de(_FACTURACION_AUSENTE)
    if ausente:
        aportes.append((f"facturación ausente ({_reglas(ausente)})", pesos.facturacion_ausente))
    sin_facturar = de(_TRABAJO_SIN_FACTURAR)
    if sin_facturar:
        valor = sum(h.valor_cent or 0 for h in sin_facturar)
        puntos = (pesos.sin_facturar_bajo if valor < pesos.sin_facturar_umbral * 100
                  else pesos.sin_facturar_alto)
        semanas = max((h.semanas_tras_gracia or 0) for h in sin_facturar)
        extra = min(pesos.sin_facturar_por_semana * semanas, pesos.sin_facturar_maximo_extra)
        texto = f"trabajo sin facturar ({_reglas(sin_facturar)}) por {euros(valor)}"
        if semanas:
            texto += f", {semanas} semana{'s' if semanas > 1 else ''} pasado el margen"
        aportes.append((texto, puntos + extra))
    limite_po = de(_LIMITE_PO)
    if limite_po:
        aportes.append((f"límite de PO ({_reglas(limite_po)})", pesos.limite_po))
    caducidad = [h for h in de(_CADUCIDAD_PO) if h.dias_para_caducar is not None]
    if caducidad:
        dias_po = min(h.dias_para_caducar for h in caducidad)
        puntos = _hasta(pesos.caducidad_po, dias_po)
        if puntos:
            aportes.append((f"la PO caduca en {_dias(dias_po)} ({_reglas(caducidad)})", puntos))
    iva = de(_IVA_BLANDA)
    if iva:
        aportes.append((f"IVA por revisar ({_reglas(iva)})", pesos.iva_blando))
        if dias_btw is not None and dias_btw <= pesos.iva_blando_extra_dias:
            aportes.append((f"el BTW vence en {_dias(dias_btw)}", pesos.iva_blando_extra))
    otras = sorted({h.regla for h in de(_OTRA)}, key=_orden_regla)
    if otras:
        aportes.append((f"anomalías: {', '.join(otras)}",
                        min(pesos.otra_por_regla * len(otras), pesos.otra_maximo)))
    if esperando and e.fecha_seguimiento < hoy:
        aportes.append((f"el seguimiento venció el {e.fecha_seguimiento.isoformat()}",
                        pesos.seguimiento_vencido))
    return [(texto, puntos) for texto, puntos in aportes if puntos]


def calcular(entradas: Entradas, hoy: date, pesos: Pesos = PESOS) -> Resultado:
    """La prioridad de una factura: el mayor de su suelo, sus puntos y sus subidas a mano."""
    e = entradas
    dias = (e.vencimiento - hoy).days if e.vencimiento is not None and e.en_juego else None
    vencida = -dias if dias is not None and dias < 0 else 0
    dias_btw = dias_hasta_btw(e.fecha_factura, hoy)

    suelo, por_suelo = _suelo(e, dias_btw, vencida)
    aportes = _puntos(e, hoy, pesos, dias, vencida, dias_btw)
    puntos = sum(p for _t, p in aportes)
    subidas = sorted((s for s in e.subidas if s.vigente(hoy) and s.nivel in NIVELES_A_MANO),
                     key=lambda s: (-RANGO[s.nivel], s.hasta or date.max, s.motivo))
    nivel = mayor(suelo, nivel_de_puntos(puntos, pesos), *(s.nivel for s in subidas))

    motivos: list[str] = []
    if por_suelo:
        motivos.append(f"{ETIQUETA[suelo]}: " + "; ".join(por_suelo))
    motivos.extend(f"{texto} +{p}" for texto, p in aportes)
    for s in subidas:
        hasta = f" hasta el {s.hasta.isoformat()}" if s.hasta else ""
        quien = f" por {s.quien}" if s.quien else ""
        motivos.append(f"subida a mano a {ETIQUETA[s.nivel].lower()}{quien}{hasta}: "
                       f"{_frase(s.motivo)}")
    return Resultado(nivel=nivel, puntos=puntos, suelo=suelo, motivos=tuple(motivos))


# ------------------------------------------------------------ huella

def _iso(dia: date | None) -> str | None:
    return None if dia is None else dia.isoformat()


def huella_entradas(entradas: Entradas, hoy: date, pesos: Pesos = PESOS) -> str:
    """El hash de lo que entro en el calculo: las entradas, hoy y los pesos.

    Se arma a mano y no con asdict: la pasada lo calcula para cada factura
    del historico, y asdict copia en profundidad cada hallazgo.
    """
    e = entradas
    contenido = [
        e.sentido, _iso(e.vencimiento), e.en_juego, e.importe_cent, _iso(e.fecha_factura),
        [[h.regla, h.severidad, h.estado, h.entrada, h.texto, h.valor_cent,
          h.semanas_tras_gracia, h.dias_para_caducar] for h in e.hallazgos],
        e.excepcion_abierta, e.revisada, e.esperando_a, _iso(e.fecha_seguimiento), e.dudosos,
        e.sin_resolver, [[s.nivel, s.motivo, s.quien, _iso(s.hasta)] for s in e.subidas],
        hoy.isoformat(), pesos.sha256(),
    ]
    texto = json.dumps(contenido, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# ------------------------------------------------------------ agregar y ordenar

@dataclass(frozen=True)
class Hija:
    """Una factura (u otra cosa con prioridad) vista desde lo que la contiene."""

    id: int
    resultado: Resultado
    vencimiento: date | None = None
    importe_cent: int | None = None
    etiqueta: str = ""


def clave_orden(nivel: str, puntos: int, vencimiento: date | None, importe_cent: int | None,
                id_: int) -> tuple:
    """Nivel (el mas alto primero), puntos, vencimiento (el mas cercano; sin fecha al final),
    importe absoluto (el mayor primero) e id."""
    return (-RANGO[nivel], -puntos, vencimiento is None, vencimiento or date.max,
            -abs(importe_cent or 0), id_)


def clave_de(hija: Hija) -> tuple:
    return clave_orden(hija.resultado.nivel, hija.resultado.puntos, hija.vencimiento,
                       hija.importe_cent, hija.id)


def ordenar(hijas: Iterable[Hija]) -> list[Hija]:
    return sorted(hijas, key=clave_de)


def agregar(hijas: Iterable[Hija], hoy: date, subidas: Sequence[Subida] = ()) -> Hija | None:
    """Lo que tiene facturas toma el maximo de sus hijas, y lo que se le suba a mano.

    Puntos, vencimiento e importe son los de su hija mas urgente (la primera
    en el orden de las listas), para ordenar un proveedor igual que su
    factura mas urgente. None si no tiene ninguna.
    """
    lista = ordenar(hijas)
    if not lista:
        return None
    primera = lista[0]
    vigentes = sorted((s for s in subidas if s.vigente(hoy) and s.nivel in NIVELES_A_MANO),
                      key=lambda s: (-RANGO[s.nivel], s.hasta or date.max, s.motivo))
    nivel = mayor(primera.resultado.nivel, *(s.nivel for s in vigentes))
    motivos = [f"por {primera.etiqueta or f'la factura {primera.id}'}: "
               + (primera.resultado.texto or ETIQUETA[primera.resultado.nivel].lower())]
    if len(lista) > 1:
        motivos.append(f"{len(lista)} facturas")
    for s in vigentes:
        hasta = f" hasta el {s.hasta.isoformat()}" if s.hasta else ""
        quien = f" por {s.quien}" if s.quien else ""
        motivos.append(f"subida a mano a {ETIQUETA[s.nivel].lower()}{quien}{hasta}: "
                       f"{_frase(s.motivo)}")
    resultado = Resultado(nivel=nivel, puntos=primera.resultado.puntos,
                          suelo=primera.resultado.suelo, motivos=tuple(motivos))
    return Hija(primera.id, resultado, primera.vencimiento, primera.importe_cent,
                primera.etiqueta)


def de_excepcion(hallazgos: Iterable[Hallazgo], factura: Resultado | None, hoy: date,
                 subidas: Sequence[Subida] = ()) -> Resultado:
    """Una excepcion: el mayor de los suelos de sus hallazgos y el nivel de su factura."""
    lista = _en_orden(hallazgos)
    suelos = [suelo_de(h) for h in lista]
    suelo = mayor(NORMAL, *suelos)
    vigentes = [s for s in subidas if s.vigente(hoy) and s.nivel in NIVELES_A_MANO]
    nivel = mayor(suelo, factura.nivel if factura else NORMAL, *(s.nivel for s in vigentes))
    motivos = [f"{ETIQUETA[suelo]}: " + "; ".join(
        f"{_frase(h.texto)} ({h.regla})" for h, s in zip(lista, suelos) if s == suelo)
        ] if suelo != NORMAL else []
    if factura is not None:
        propios = [m for m in factura.motivos if m not in motivos]
        if propios:
            motivos.append("su factura: " + " · ".join(propios))
    for s in vigentes:
        motivos.append(f"subida a mano a {ETIQUETA[s.nivel].lower()}: {_frase(s.motivo)}")
    return Resultado(nivel=nivel, puntos=factura.puntos if factura else 0, suelo=suelo,
                     motivos=tuple(motivos))
