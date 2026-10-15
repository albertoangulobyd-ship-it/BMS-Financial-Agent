"""Lo que es una regla, sobre que se evalua y que devuelve.

Una regla es una funcion pura sobre una instantanea congelada del almacen
(`Instantanea`): las facturas con sus valores actuales, sus lineas, las
relaciones confirmadas, la politica y `hoy`. No toca la base, ni el reloj,
ni el entorno, ni la red: lo comprueba un test que lee el codigo (AST) y
otro que la ejecuta con un proxy que apunta cada atributo que lee y lo
compara con lo que declara (`Regla.lee`). Asi el resultado depende solo de
los datos, se puede repetir, y la huella de un hallazgo puede decir de que
campos salio.

Cada regla devuelve un `Resultado` por cada fila que mira: ok, fallo,
sin_datos o no_aplica. sin_datos no es ok: es "no se ha podido mirar", y
nunca cierra un hallazgo ni deja una factura en verde.

Las comprobaciones de fondo (sumar lineas, la cuota por el tipo, el digito
de control del IBAN...) son funciones sobre Decimal que devuelven una
`Comprobacion`. Las usan las reglas del motor y tambien checks.py y
dashboard.py, que las envuelven para el contrato v1 de siempre: una sola
aritmetica, dos formas de contarla.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Any, NamedTuple

from ..dominio import (
    AmbitoHallazgo,
    EntradaPrioridad,
    PapelObjetivo,
    ResultadoRegla,
    Sentido,
    Severidad,
)

OK = ResultadoRegla.OK.value
FALLO = ResultadoRegla.FALLO.value
SIN_DATOS = ResultadoRegla.SIN_DATOS.value
NO_APLICA = ResultadoRegla.NO_APLICA.value

# Lo que hace un fallo (validacion-facturas.md §2): Bloqueo, Retencion, Aviso.
B = Severidad.BLOQUEO.value
R = Severidad.RETENCION.value
A = Severidad.AVISO.value
GRAVEDAD = {B: 0, R: 1, A: 2}

PRINCIPAL = PapelObjetivo.PRINCIPAL.value
RELACIONADO = PapelObjetivo.RELACIONADO.value

ENTRANTE = Sentido.ENTRANTE.value
SALIENTE = Sentido.SALIENTE.value


# ------------------------------------------------------------ politica

@dataclass(frozen=True)
class Politica:
    """Tolerancias y umbrales con los que se evalua (validacion-facturas.md §4).

    Entran en la huella de cada hallazgo las que su regla usa: si alguien
    afloja una tolerancia, la evidencia que se acepto ya no es la misma.
    """

    tolerancia_linea: Decimal = Decimal("0.01")
    tolerancia_factura: Decimal = Decimal("0.02")
    ventana_duplicado_dias: int = 14
    tolerancia_duplicado: Decimal = Decimal("0.01")

    def valor(self, nombre: str) -> str:
        """El parametro como texto, para la huella (sin floats ni ambiguedad)."""
        return str(getattr(self, nombre))

    def como_texto(self) -> dict[str, str]:
        return {f.name: self.valor(f.name) for f in fields(self)}


# ------------------------------------------------------------ instantanea

@dataclass(frozen=True, slots=True)
class Linea:
    """Una linea activa de una factura, con sus valores actuales.

    `objeto` es la clave del Objeto que nombra: el Objeto resuelto de su
    imputacion ("objeto:7") o, sin resolver, el texto impreso normalizado
    ("doc:rijnhaven"). `ilegibles` son los campos con un literal impreso que
    no se pudo leer (o que no son euros): estan en el papel, pero no hay valor.
    """

    id: int
    orden: int
    descripcion_doc: str | None
    objeto_doc: str | None
    unidad: str | None
    cantidad_mil: int | None
    tarifa_e4: int | None
    importe_cent: int | None
    tipo_iva_pb: int | None
    fecha_inicio: date | None
    fecha_fin: date | None
    fecha_trabajo: date | None
    objeto: str | None
    ilegibles: frozenset[str]


@dataclass(frozen=True, slots=True)
class TramoIva:
    """Una fila del desglose de IVA por tipo (v2). Una factura v1 no tiene."""

    id: int
    tipo_iva_pb: int | None
    base_cent: int | None
    cuota_cent: int | None


@dataclass(frozen=True, slots=True)
class Factura:
    """Una factura con los valores actuales de cada campo (los de campos.py).

    `parte` es la contraparte como clave de agrupacion: la fila del maestro si
    esta resuelta ("proveedor:3"); si no, el btw-id, el KvK o el nombre
    impreso normalizados ("btw:NL001234567B01"). None si el documento no dice
    quien es: una factura sin contraparte no se agrupa con nadie. `moneda` es
    la moneda que no es el euro, si la hay (X1). `no_solicitados` son las
    columnas que la version del esquema de su extraccion no pidio al modelo.
    """

    id: int
    sentido: str
    tipo: str
    numero: str | None
    numero_norm: str | None
    parte: str | None
    parte_nombre: str
    proveedor_id: int | None
    cliente_id: int | None
    emisor_nombre_doc: str | None
    emisor_kvk_doc: str | None
    emisor_btw_doc: str | None
    receptor_nombre_doc: str | None
    receptor_btw_doc: str | None
    fecha_factura: date | None
    periodo_inicio: date | None
    periodo_fin: date | None
    base_cent: int | None
    iva_cent: int | None
    total_cent: int | None
    tipo_iva_pb: int | None
    tratamiento_iva: str | None
    iban_doc: str | None
    moneda: str | None
    anulada: bool
    fusionada_en_id: int | None
    lineas: tuple[Linea, ...]
    desglose: tuple[TramoIva, ...]
    ilegibles: frozenset[str]
    no_solicitados: frozenset[str]


@dataclass(frozen=True, slots=True)
class Relacion:
    """Una relacion confirmada entre dos facturas (las propuestas no cuentan)."""

    origen_id: int
    destino_id: int
    tipo: str


@dataclass(frozen=True)
class Instantanea:
    """Todo lo que una regla puede ver, congelado. Lo construye reglas/instantanea.py."""

    hoy: date
    politica: Politica
    facturas: tuple[Factura, ...]
    relaciones: tuple[Relacion, ...] = ()


# ------------------------------------------------------------ resultados
#
# Tuplas con nombre y no dataclasses: una pasada crea decenas de miles de
# resultados, y una tupla se construye varias veces mas rapido. Son igual de
# inmutables.

SIN_VALORES: Mapping[str, Any] = MappingProxyType({})


class Comprobacion(NamedTuple):
    """Lo que dice una comprobacion de fondo: resultado y explicacion."""

    resultado: str
    detalle: str


class Objetivo(NamedTuple):
    """Una fila (y, si se sabe, el campo) a la que se refiere un resultado."""

    tabla: str
    fila_id: int
    campo: str | None = None
    papel: str = PRINCIPAL


class Resultado(NamedTuple):
    """Lo que dice una regla de una fila.

    `valores` son los valores comparados, en enteros y textos (van en la
    huella). `clave` distingue varios resultados de la misma regla sobre la
    misma fila (E4 mira la cuota y el btw-id del receptor). `grupo` es la
    identidad de un hallazgo que cubre varias facturas (B2: la contraparte y
    el numero): todas las del grupo llevan el mismo, y comparten hallazgo.
    `severidad` solo si no es la del catalogo para el sentido de la factura
    (Q1 bloquea cuando falta el numero).
    """

    regla: str
    tabla: str
    fila_id: int
    resultado: str
    detalle: str
    valores: Mapping[str, Any] = SIN_VALORES
    clave: str = ""
    grupo: str | None = None
    severidad: str | None = None
    objetivos: tuple[Objetivo, ...] = ()

    @property
    def clave_hallazgo(self) -> str:
        """La identidad del hallazgo que daria: regla, objetivo y llave.

        No lleva los valores: si un importe cambia, el hallazgo es el mismo con
        otra evidencia (otra huella), no uno nuevo.
        """
        if self.grupo is not None:
            return f"{self.regla}|{self.grupo}"
        base = f"{self.regla}|{self.tabla}:{self.fila_id}"
        return f"{base}|{self.clave}" if self.clave else base


# ------------------------------------------------------------ reglas

Evaluador = Callable[[Instantanea], Iterable[Resultado]]


@dataclass(frozen=True)
class Regla:
    """Una regla del catalogo: su metadato (spec §7) y su evaluacion.

    `lee` son los atributos de la instantanea que la regla puede leer, como
    "factura.base_cent", "linea.importe_cent" o "politica.tolerancia_linea";
    los de la politica son los parametros que entran en la huella.
    `solo_texto` son los que lee solo para escribir su explicacion (el nombre
    o el numero impresos en el detalle de un duplicado): no son evidencia, y
    su fuente no entra en la huella.
    `severidad_saliente` y `anulable_saliente`, si la regla cambia en las
    facturas de venta (D2: bloquea una compra, retiene una venta).
    `segunda_firma`: anularla pide otra persona con anular_aviso, si la hay.
    """

    id: str
    titulo: str
    familia: str
    evaluar: Evaluador
    lee: frozenset[str]
    severidad: str
    solo_texto: frozenset[str] = frozenset()
    severidad_saliente: str | None = None
    anulable: bool = False
    anulable_saliente: bool | None = None
    pegajosa: bool = False
    segunda_firma: bool = False
    entrada_prioridad: str = EntradaPrioridad.OTRA.value
    calidad: str | None = None
    ambito: str = AmbitoHallazgo.FACTURA.value
    version: int = 1
    descripcion: str = ""

    def severidad_para(self, sentido: str | None) -> str:
        if sentido == SALIENTE and self.severidad_saliente is not None:
            return self.severidad_saliente
        return self.severidad

    def anulable_para(self, sentido: str | None) -> bool:
        if sentido == SALIENTE and self.anulable_saliente is not None:
            return self.anulable_saliente
        return self.anulable

    @property
    def parametros(self) -> tuple[str, ...]:
        return tuple(sorted(n.split(".", 1)[1] for n in self.lee if n.startswith("politica.")))

    def metadatos(self) -> dict[str, Any]:
        """Lo que dice el catalogo de la regla, sin la funcion (para su hash)."""
        return {
            "id": self.id, "titulo": self.titulo, "familia": self.familia,
            "version": self.version, "severidad": self.severidad,
            "severidad_saliente": self.severidad_saliente, "anulable": self.anulable,
            "anulable_saliente": self.anulable_saliente, "pegajosa": self.pegajosa,
            "segunda_firma": self.segunda_firma, "entrada_prioridad": self.entrada_prioridad,
            "calidad": self.calidad, "ambito": self.ambito, "lee": sorted(self.lee),
            "solo_texto": sorted(self.solo_texto),
        }


# Lo que lee siempre una regla de factura: recorrer las facturas, saber cual
# es cada una y si esta fuera de juego (anulada o fusionada en otra).
LEE_POR_FACTURA = frozenset({
    "instantanea.facturas", "instantanea.politica",
    "factura.id", "factura.anulada", "factura.fusionada_en_id",
})

PorFactura = Callable[[Factura, Politica], Sequence[Resultado]]


def fuera_de_juego(factura: Factura) -> str | None:
    """Por que una factura ya no se evalua, o None si se evalua.

    Una factura anulada o fusionada en otra ya no se paga ni se cuenta: sus
    avisos de aritmetica o de moneda no piden nada a nadie. Una regla de
    grupo tampoco la empareja con otras.
    """
    if factura.anulada:
        return "La factura está anulada."
    if factura.fusionada_en_id is not None:
        return f"La factura está fusionada en la factura {factura.fusionada_en_id}."
    return None


def por_factura(regla_id: str, funcion: PorFactura) -> Evaluador:
    """Una regla de una factura sola: la funcion se llama con cada factura en juego.

    Devuelve una lista y no un generador: son decenas de miles de llamadas
    por pasada, y un generador por factura y regla se nota.
    """
    def evaluar(instantanea: Instantanea) -> list[Resultado]:
        politica = instantanea.politica
        salida: list[Resultado] = []
        for factura in instantanea.facturas:
            if factura.anulada or factura.fusionada_en_id is not None:
                salida.append(Resultado(regla_id, "factura", factura.id, NO_APLICA,
                                        fuera_de_juego(factura)))
            else:
                salida.extend(funcion(factura, politica))
        return salida
    return evaluar


def resultado_de(regla_id: str, factura: Factura, comprobacion: Comprobacion, *,
                 valores: Mapping[str, Any] = SIN_VALORES, clave: str = "",
                 grupo: str | None = None, severidad: str | None = None,
                 objetivos: tuple[Objetivo, ...] = ()) -> Resultado:
    """Un Resultado de una factura a partir de una comprobacion de fondo."""
    return Resultado(regla_id, "factura", factura.id, comprobacion.resultado,
                     comprobacion.detalle, valores, clave, grupo, severidad, objetivos)


# ------------------------------------------------------------ escalas
#
# Los enteros del almacen vuelven a Decimal exactos para las comprobaciones
# de fondo, que son las mismas que lee checks.py desde los literales.

def euros(cent: int | None) -> Decimal | None:
    return None if cent is None else Decimal(cent).scaleb(-2)


def tarifa(e4: int | None) -> Decimal | None:
    return None if e4 is None else Decimal(e4).scaleb(-4)


def cantidad(mil: int | None) -> Decimal | None:
    return None if mil is None else compacto(Decimal(mil).scaleb(-3))


def porcentaje(pb: int | None) -> Decimal | None:
    return None if pb is None else compacto(Decimal(pb).scaleb(-2))


def compacto(valor: Decimal) -> Decimal:
    """Sin ceros de mas a la derecha y sin exponente: 21.00 es 21, 37.500 es 37.5."""
    if valor == valor.to_integral_value():
        return valor.quantize(Decimal(1))
    return valor.normalize()


def euros_texto(valor: Decimal) -> str:
    """Un importe como se lee en la empresa: 2.399,00."""
    return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def periodo_de(factura: Factura) -> tuple[date | None, date | None]:
    """El periodo de prestacion, de la cabecera o deducido de las lineas.

    Muchas facturas solo lo declaran linea a linea; sin mirar ahi, las reglas
    de periodo no verian nada justo donde un duplicado pasa mas desapercibido.
    Es la idea de dashboard._periodo_de, mas la fecha de trabajo de cada
    linea que trae v2.
    """
    inicio, fin = factura.periodo_inicio, factura.periodo_fin
    if inicio is not None and fin is not None:
        return inicio, fin
    inicios = sorted(d for l in factura.lineas for d in (l.fecha_inicio, l.fecha_trabajo)
                     if d is not None)
    fines = sorted(d for l in factura.lineas for d in (l.fecha_fin, l.fecha_trabajo)
                   if d is not None)
    return (inicio or (inicios[0] if inicios else None),
            fin or (fines[-1] if fines else None))


LEE_PERIODO = frozenset({
    "factura.periodo_inicio", "factura.periodo_fin", "factura.lineas",
    "linea.fecha_inicio", "linea.fecha_fin", "linea.fecha_trabajo",
})


def lineas_en_orden(factura: Factura) -> list[Linea]:
    """Las lineas por su posicion impresa: el resultado no depende del orden de entrada."""
    return sorted(factura.lineas, key=lambda l: (l.orden, l.id))


def vinculadas(relaciones: Iterable[Relacion]) -> frozenset[frozenset[int]]:
    """Los pares de facturas unidos por una relacion confirmada."""
    return frozenset(frozenset((r.origen_id, r.destino_id)) for r in relaciones)


LEE_RELACIONES = frozenset({"instantanea.relaciones", "relacion.origen_id", "relacion.destino_id"})
