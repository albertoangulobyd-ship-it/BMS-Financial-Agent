"""El BTW (paso 11; seccion 8 de la lista de funciones): las cifras de cada trimestre, su
hoja de trabajo y el estado de su declaracion.

La declaracion se prepara, no se presenta (arquitectura.md, regla 5). Aqui no
hay nada que hable con la Belastingdienst: se calculan las cifras, se genera la
hoja de trabajo con la lista de lo que hay que revisar, y una persona con
gestionar_btw apunta el estado del trimestre:

- abierto: lo que es todo trimestre sin fila en periodo_btw;
- listo_revision: la hoja esta lista para que la revise el asesor o la otra
  persona; se guarda entera (hoja_btw) y su sha256 queda en el periodo. Solo
  despues de que el trimestre haya terminado. Vuelve a abierto con un motivo;
- presentado: una persona la presento en el portal y lo anota con la
  referencia, lo declarado y el dia. Tiene que ser la hoja que se marco lista
  y las cifras de hoy tienen que seguir siendo esas (si no, otra vez lista).
  Es irreversible (la base lo exige) y deja apuntado lo que se declaro de cada
  factura (periodo_btw_declarada), contra lo que compara C4 desde entonces.

Las cifras salen de v_btw_linea (las lineas de IVA de las facturas que
cuentan, con su trimestre por la fecha de factura: factuurstelsel) y de
config/btw.yaml, que dice a que rubrica va cada linea (politica.ConfigBtw):

- una venta con IVA normal va a 1a, 1b, 1c o 1e por su tipo, con su base y su
  cuota; una sin IVA (tipo cero, IVA trasladado al cliente), solo con su base;
- la cuota de una compra con IVA normal es IVA soportado (5b);
- el IVA trasladado de una compra se autoliquida (la base por el tipo de
  config/btw.yaml) en 2a, 4b o 4a segun de donde sea el proveedor, y vuelve
  como deducible en 5b: las dos cosas se compensan;
- con KOR, exento o tipo cero en una compra no hay IVA que declarar;
- un abono va en su propio trimestre, en negativo (la fecha es la suya);
- una factura anulada, fusionada en otra o sustituida no esta en la vista;
  una que no esta en euros (X1), o a la que le falta lo que su linea
  necesita (E0), queda fuera de las cifras y se dice en la hoja.

5a es el IVA a declarar (la columna de IVA de 1a a 4b), 5c es 5a menos 5b: lo
que se estima a pagar si es positivo, a devolver si es negativo. Las cifras
van en centimos; la declaracion se rellena en euros enteros, y eso lo hace la
persona que la presenta.

Facturas que piden revisar el IVA: las del trimestre con un hallazgo de
IVA pendiente (las reglas con entrada de IVA, dura o blanda), mas las de C4 de
ese trimestre, las que tienen pendiente algo que pone su IVA en duda (un
duplicado, una mal encaminada, una lectura dudosa de lo que se declara) y las
que tienen una linea fuera de las cifras (revisar).

La hoja lleva escrita la huella de sus cifras (huella_cifras): presentar exige
que las cifras de hoy sean las de la hoja marcada, no que la lista de revisar
siga igual.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from . import politica
from .almacen import reloj_de
from .almacen.unidades import a_cent, de_cent, json_canonico, sha256_texto
from .auditoria import Cambio, registrar
from .campos import Conflicto, FaltaMotivo, Persona
from .dominio import EntradaPrioridad, EstadoBtw, Fuente, Permiso
from .permisos import (
    AUTORREVISADO,
    DENEGADO,
    SeparacionDeFunciones,
    exigir,
    orden_auditada,
    separacion,
)
from .politica import FUERA, ConfigBtw
from .reglas import catalogo
from .reglas.base import euros_texto
from .reglas.instantanea import moneda_extranjera
from .reglas.iva import LineaIva, huella_iva, pais_iva, tipo_de_lineas
from .reloj import limite_btw, marca, trimestre_de

TABLA = "periodo_btw"
COLUMNAS: tuple[str, ...] = (
    "ano", "trimestre", "inicio", "fin", "limite_presentacion", "limite_pago", "estado",
    "listo_en", "listo_por", "presentado_en", "presentado_por", "referencia_presentacion",
    "importe_declarado_cent", "hoja_id", "hoja_sha256", "nota",
)
ABIERTO = EstadoBtw.ABIERTO.value
LISTO = EstadoBtw.LISTO_REVISION.value
PRESENTADO = EstadoBtw.PRESENTADO.value
GESTIONAR = Permiso.GESTIONAR_BTW.value
EVENTO_HOJA = "btw_hoja_guardada"
EVENTO_LISTO = "btw_lista_revision"
EVENTO_REABIERTO = "btw_reabierto"
EVENTO_PRESENTADO = "btw_presentacion_anotada"

# Las rubricas de la declaracion (aangifte omzetbelasting), como las nombra el
# formulario. 1d (uso privado) no se usa en una empresa de servicios.
RUBRICAS: dict[str, str] = {
    "1a": "Leveringen/diensten belast met hoog tarief",
    "1b": "Leveringen/diensten belast met laag tarief",
    "1c": "Leveringen/diensten belast met overige tarieven, behalve 0%",
    "1e": "Leveringen/diensten belast met 0% of niet bij u belast",
    "2a": "Leveringen/diensten waarbij de omzetbelasting naar u is verlegd",
    "3a": "Leveringen naar landen buiten de EU",
    "3b": "Leveringen naar of diensten in landen binnen de EU",
    "3c": "Installatie/afstandsverkopen binnen de EU",
    "4a": "Leveringen/diensten uit landen buiten de EU",
    "4b": "Leveringen/diensten uit landen binnen de EU",
    "5a": "Verschuldigde omzetbelasting",
    "5b": "Voorbelasting",
    "5c": "Subtotaal (5a min 5b): te betalen of terug te vragen",
}
ORDEN_RUBRICAS: tuple[str, ...] = ("1a", "1b", "1c", "1e", "2a", "3a", "3b", "3c", "4a", "4b")
# Las rubricas cuya columna de IVA es la cuota impresa de una venta.
_CON_CUOTA = frozenset({"1a", "1b", "1c"})
# Las reglas de IVA (las que el §8 de la especificacion cuenta como IVA duro o blando): un hallazgo
# pendiente de una de ellas pide revisar la factura antes de declarar.
REGLAS_IVA = frozenset(r.id for r in catalogo.CATALOGO if r.entrada_prioridad in (
    EntradaPrioridad.IVA_DURA.value, EntradaPrioridad.IVA_BLANDA.value))
# Las que no son de IVA pero lo ponen en duda: un duplicado (B2, B3) o una original
# pendiente con su sustituta (R3) declararian el mismo IVA dos veces, y una factura
# que no va dirigida a BMS (A8) no es suya. Q2 solo si la lectura dudosa es de lo
# que se declara (CAMPOS_DUDA): la fecha decide el trimestre.
REGLAS_DUDA = frozenset({"A8", "B2", "B3", "Q2", "R3"})
CAMPOS_DUDA = frozenset({"base_cent", "iva_cent", "total_cent", "tipo_iva_pb",
                         "tratamiento_iva", "fecha_factura"})
_PENDIENTES = ("abierto", "desaparecido")


class EstadoNoValido(ValueError):
    """La orden no tiene sentido en el estado en que esta el trimestre."""


# ------------------------------------------------------------ el calendario

def periodo_de(ano: int, trimestre: int) -> tuple[date, date]:
    """El primer y el ultimo dia de un trimestre natural."""
    if trimestre not in (1, 2, 3, 4):
        raise ValueError(f"un trimestre va de 1 a 4, no {trimestre}")
    inicio = date(ano, (trimestre - 1) * 3 + 1, 1)
    siguiente = date(ano + (trimestre == 4), trimestre * 3 % 12 + 1, 1)
    return inicio, siguiente - timedelta(days=1)


def limites(ano: int, trimestre: int) -> tuple[date, date]:
    """El ultimo dia para presentar y para pagar un trimestre.

    El de config/btw.yaml, que solo admite el plazo de siempre (ConfigBtw): el
    ultimo dia del mes siguiente al trimestre (reloj.limite_btw), el T3 el 31
    de octubre y el T4 el 31 de enero del ano siguiente. Presentar y pagar
    vencen el mismo dia.
    """
    limite = limite_btw(ano, trimestre)
    return limite, limite


def anterior(ano: int, trimestre: int) -> tuple[int, int]:
    """El trimestre de antes: el anterior al primero es el cuarto del ano pasado."""
    return (ano - 1, 4) if trimestre == 1 else (ano, trimestre - 1)


def etiqueta(ano: int, trimestre: int) -> str:
    return f"{ano}-T{trimestre}"


def leer_etiqueta(texto: str) -> tuple[int, int]:
    """'2026-T3', '2026-3' o '2026T3' es (2026, 3)."""
    limpio = str(texto).strip().upper().replace("T", "-").replace("--", "-")
    ano, _, numero = limpio.partition("-")
    try:
        resultado = int(ano), int(numero)
    except ValueError:
        raise ValueError(f"{texto!r} no es un trimestre: se escribe 2026-T3") from None
    periodo_de(*resultado)
    return resultado


# ------------------------------------------------------------ las lineas

@dataclass(frozen=True)
class LineaBtw:
    """Una linea de IVA de una factura que cuenta (v_btw_linea), con lo que la hoja ensena.

    `moneda` es la moneda que no es el euro (X1), o None. `pais` es de donde es
    la contraparte para el IVA trasladado (reglas.iva.pais_iva). `tipo_lineas_pb`
    es, en una venta con IVA normal sin tipo en la cabecera ni desglose, el unico
    tipo de sus lineas (reglas.iva.tipo_de_lineas): lo que E0 acepta como tipo.
    """

    factura_id: int
    factura_iva_id: int | None
    sentido: str
    tipo: str
    numero: str | None
    contraparte: str | None
    fecha: date | None
    tratamiento: str | None
    tipo_iva_pb: int | None
    base_cent: int | None
    cuota_cent: int | None
    moneda: str | None
    pais: str
    tipo_lineas_pb: int | None = None

    @property
    def tipo_efectivo_pb(self) -> int | None:
        """El tipo con que se declara: el de la linea o, sin el, el de las lineas de la
        factura."""
        return self.tipo_iva_pb if self.tipo_iva_pb is not None else self.tipo_lineas_pb

    @property
    def trimestre(self) -> tuple[int, int] | None:
        return trimestre_de(self.fecha) if self.fecha is not None else None

    def linea_iva(self) -> LineaIva:
        return LineaIva(self.tratamiento, self.tipo_iva_pb, self.base_cent, self.cuota_cent)


def lineas(conn: sqlite3.Connection, ano: int | None = None,
           trimestre: int | None = None) -> list[LineaBtw]:
    """Las lineas de IVA de las facturas que cuentan, de un trimestre o de todos."""
    filtro, parametros = "", ()
    if ano is not None and trimestre is not None:
        filtro, parametros = "WHERE l.ano = ? AND l.trimestre = ?", (ano, trimestre)
    salida = []
    filas = conn.execute(
            "SELECT l.factura_id, l.factura_iva_id, l.sentido, l.tipo, l.fecha_factura, "
            "l.tratamiento, l.tipo_iva_pb, l.base_cent, l.cuota_cent, l.moneda_doc, f.numero, "
            "f.emisor_nombre_doc, f.emisor_btw_doc, f.receptor_nombre_doc, f.receptor_btw_doc, "
            "p.nombre AS proveedor, c.nombre AS cliente "
            "FROM v_btw_linea AS l JOIN factura AS f ON f.id = l.factura_id "
            "LEFT JOIN proveedor AS p ON p.id = f.proveedor_id "
            f"LEFT JOIN cliente AS c ON c.id = f.cliente_id {filtro} "
            "ORDER BY l.fecha_factura, l.factura_id, coalesce(l.factura_iva_id, 0)",
            parametros).fetchall()
    de_lineas = _tipos_de_lineas(conn, {
        f["factura_id"] for f in filas if f["factura_iva_id"] is None
        and f["tipo_iva_pb"] is None and f["sentido"] == "saliente"
        and f["tratamiento"] == "estandar"})
    for fila in filas:
        entrante = fila["sentido"] == "entrante"
        btw = fila["emisor_btw_doc"] if entrante else fila["receptor_btw_doc"]
        nombre = (fila["proveedor"] or fila["emisor_nombre_doc"] if entrante
                  else fila["cliente"] or fila["receptor_nombre_doc"])
        salida.append(LineaBtw(
            factura_id=fila["factura_id"], factura_iva_id=fila["factura_iva_id"],
            sentido=fila["sentido"], tipo=fila["tipo"], numero=fila["numero"],
            contraparte=nombre,
            fecha=date.fromisoformat(fila["fecha_factura"]) if fila["fecha_factura"] else None,
            tratamiento=fila["tratamiento"], tipo_iva_pb=fila["tipo_iva_pb"],
            base_cent=fila["base_cent"], cuota_cent=fila["cuota_cent"],
            moneda=moneda_extranjera(fila["moneda_doc"]), pais=pais_iva(btw),
            tipo_lineas_pb=de_lineas.get(fila["factura_id"])
            if fila["factura_iva_id"] is None else None))
    return salida


def _tipos_de_lineas(conn: sqlite3.Connection, facturas: set[int]) -> dict[int, int]:
    """El unico tipo de las lineas vivas de cada factura, si lo tienen (tipo_de_lineas)."""
    if not facturas:
        return {}
    tipos: dict[int, list[int | None]] = defaultdict(list)
    marcas = ", ".join("?" * len(facturas))
    for factura_id, tipo in conn.execute(
            f"SELECT factura_id, tipo_iva_pb FROM factura_linea WHERE retirada_en IS NULL "
            f"AND factura_id IN ({marcas})", sorted(facturas)):
        tipos[factura_id].append(tipo)
    salida = {f: tipo_de_lineas(t) for f, t in tipos.items()}
    return {f: t for f, t in salida.items() if t is not None}


def declarables(lineas_: list[LineaBtw]) -> dict[int, list[LineaBtw]]:
    """Por factura, sus lineas si cuenta en un trimestre: con fecha y en euros (como C4)."""
    salida: dict[int, list[LineaBtw]] = defaultdict(list)
    for linea in lineas_:
        if linea.fecha is not None and linea.moneda is None:
            salida[linea.factura_id].append(linea)
    return salida


def huellas(lineas_: list[LineaBtw]) -> dict[int, str]:
    """La huella de IVA de cada factura que cuenta: lo que C4 compara con lo declarado."""
    return {factura_id: huella_iva(propias[0].sentido, propias[0].pais,
                                   [l.linea_iva() for l in propias])
            for factura_id, propias in declarables(lineas_).items()}


# ------------------------------------------------------------ clasificar

@dataclass(frozen=True)
class Clasificada:
    """Lo que una linea pone en la declaracion.

    `rubrica` es la de config/btw.yaml, FUERA si no va en la declaracion, o
    None si no se puede clasificar (entonces `motivo` dice por que). En su
    rubrica pone `omzet_cent` y `btw_cent` (la cuota de una venta, o lo
    autoliquidado de una compra con IVA trasladado); en 5b, `deducible_cent`.
    """

    linea: LineaBtw
    rubrica: str | None
    omzet_cent: int = 0
    btw_cent: int = 0
    deducible_cent: int = 0
    autoliquidado_cent: int = 0
    motivo: str | None = None


def por_tipo(base_cent: int, tipo_pb: int) -> int:
    """La base por un tipo, al centimo y con el medio hacia fuera (como un abono en negativo)."""
    producto = base_cent * tipo_pb
    cociente, resto = divmod(abs(producto), 10_000)
    if resto * 2 >= 10_000:
        cociente += 1
    return cociente if producto >= 0 else -cociente


# Lo que falta es E0; lo que esta en el papel y no se pudo leer, Q2 (E0 no lo cuenta
# como falta). La factura va igual a la lista de las que piden revisar el IVA.
_SIN_TIPO_O_CUOTA = "IVA normal sin tipo o sin cuota (E0, o Q2 si no se pudo leer)"
_SIN_CUOTA = "IVA normal sin cuota (E0, o Q2 si no se pudo leer)"


def clasificar(linea: LineaBtw, config: ConfigBtw) -> Clasificada:
    """A que rubrica va una linea y con que importes (ver el docstring del modulo)."""
    if linea.moneda is not None:
        return Clasificada(linea, None, motivo=f"no está en euros ({linea.moneda}): X1")
    if linea.tratamiento in (None, "desconocido"):
        return Clasificada(linea, None, motivo="no se sabe cómo trata el IVA: E0")
    if linea.base_cent is None:
        return Clasificada(linea, None, motivo="sin base imponible")
    if linea.sentido == "saliente":
        if linea.tratamiento == "estandar":
            tipo = linea.tipo_efectivo_pb
            if tipo is None or linea.cuota_cent is None:
                return Clasificada(linea, None, motivo=_SIN_TIPO_O_CUOTA)
            clave = f"estandar:{tipo}"
            rubrica = config.rubrica("saliente", clave) or config.rubrica(
                "saliente", "estandar:otros")
            if rubrica not in _CON_CUOTA and linea.cuota_cent != 0:
                # Defensa: el cargador ya no deja poner un tipo con cuota en 1e, pero una
                # cuota cobrada al cliente nunca se pierde de 5a en silencio.
                return Clasificada(linea, None, motivo=f"IVA cobrado al {_tipo(tipo)} % y "
                                   f"btw.yaml lo pone en {rubrica}, que no lleva IVA")
            return Clasificada(linea, rubrica, omzet_cent=linea.base_cent,
                               btw_cent=linea.cuota_cent if rubrica in _CON_CUOTA else 0)
        clave = (f"autoliquidacion:{linea.pais}" if linea.tratamiento == "autoliquidacion"
                 else linea.tratamiento)
        rubrica = config.rubrica("saliente", clave)
        if rubrica is None or rubrica == FUERA:
            return Clasificada(linea, FUERA)
        return Clasificada(linea, rubrica, omzet_cent=linea.base_cent)
    if linea.tratamiento == "estandar":
        if linea.cuota_cent is None:
            return Clasificada(linea, None, motivo=_SIN_CUOTA)
        rubrica = config.rubrica("entrante", "estandar")
        if rubrica == FUERA:
            return Clasificada(linea, FUERA)
        return Clasificada(linea, rubrica, deducible_cent=linea.cuota_cent)
    if linea.tratamiento == "autoliquidacion":
        rubrica = config.rubrica("entrante", f"autoliquidacion:{linea.pais}")
        autoliquidado = por_tipo(linea.base_cent, config.tipo_autoliquidacion_pb)
        return Clasificada(linea, rubrica, omzet_cent=linea.base_cent, btw_cent=autoliquidado,
                           autoliquidado_cent=autoliquidado,
                           deducible_cent=autoliquidado if config.autoliquidacion_deducible
                           else 0)
    return Clasificada(linea, FUERA)


@dataclass
class Cifras:
    """Las cifras de un conjunto de lineas (un trimestre, el ano hasta hoy)."""

    rubricas: dict[str, list[int]] = field(
        default_factory=lambda: {r: [0, 0] for r in ORDEN_RUBRICAS})
    voorbelasting_cent: int = 0
    ingresos_cent: int = 0
    iva_repercutido_cent: int = 0
    iva_autoliquidado_cent: int = 0
    costes_cent: int = 0
    lineas: list[Clasificada] = field(default_factory=list)

    @property
    def iva_a_declarar_cent(self) -> int:
        """5a: la columna de IVA de 1a a 4b."""
        return sum(btw for _omzet, btw in self.rubricas.values())

    @property
    def saldo_cent(self) -> int:
        """5c: 5a menos 5b. Positivo, a pagar; negativo, a devolver."""
        return self.iva_a_declarar_cent - self.voorbelasting_cent

    @property
    def sin_clasificar(self) -> list[Clasificada]:
        return [c for c in self.lineas if c.rubrica is None]

    @property
    def fuera(self) -> list[Clasificada]:
        return [c for c in self.lineas if c.rubrica == FUERA]

    def como_dict(self) -> dict[str, Any]:
        saldo = self.saldo_cent
        return {
            "rubricas": [{"rubrica": r, "descripcion": RUBRICAS[r], "omzet_cent": o,
                          "btw_cent": b} for r, (o, b) in self.rubricas.items()],
            "5a": self.iva_a_declarar_cent, "5b": self.voorbelasting_cent, "5c": saldo,
            "ingresos_cent": self.ingresos_cent,
            "iva_repercutido_cent": self.iva_repercutido_cent,
            "iva_autoliquidado_cent": self.iva_autoliquidado_cent,
            "costes_cent": self.costes_cent,
            "iva_deducible_cent": self.voorbelasting_cent,
            "a_pagar_cent": max(saldo, 0), "a_devolver_cent": max(-saldo, 0),
            "lineas": len(self.lineas),
            "sin_clasificar": [_de_clasificada(c) for c in self.sin_clasificar],
            "fuera": [_de_clasificada(c) for c in self.fuera],
        }


def _de_clasificada(c: Clasificada) -> dict[str, Any]:
    return {"factura_id": c.linea.factura_id, "numero": c.linea.numero,
            "contraparte": c.linea.contraparte, "tratamiento": c.linea.tratamiento,
            "base_cent": c.linea.base_cent, "motivo": c.motivo or "no va en la declaración"}


def huella_cifras(cifras_: Cifras) -> str:
    """El sha256 de lo que se declara: las rubricas, 5a, 5b y 5c y cada linea con sus importes
    y su rubrica.

    No lleva lo que se revisa (los hallazgos abiertos) ni los nombres: resolver
    o anular un hallazgo, o corregir el nombre de un proveedor, despues de marcar
    la hoja lista no cambia lo que se presenta. Es lo que anotar_presentacion
    compara con la hoja marcada, que la lleva escrita.
    """
    lineas_ = [[c.linea.factura_id, c.linea.factura_iva_id, c.linea.sentido, c.linea.tipo,
                c.linea.fecha.isoformat() if c.linea.fecha else None, c.linea.tratamiento,
                c.linea.tipo_efectivo_pb, c.linea.base_cent, c.linea.cuota_cent,
                c.linea.moneda, c.linea.pais, c.rubrica, c.omzet_cent, c.btw_cent,
                c.deducible_cent, c.autoliquidado_cent] for c in cifras_.lineas]
    return sha256_texto(json_canonico({
        "rubricas": {r: list(v) for r, v in cifras_.rubricas.items()},
        "5a": cifras_.iva_a_declarar_cent, "5b": cifras_.voorbelasting_cent,
        "5c": cifras_.saldo_cent, "lineas": lineas_}))


def cifras(lineas_: list[LineaBtw], config: ConfigBtw) -> Cifras:
    """Las cifras de unas lineas: pura, sobre lo que da `lineas`."""
    salida = Cifras()
    for linea in lineas_:
        c = clasificar(linea, config)
        salida.lineas.append(c)
        if linea.moneda is None and linea.base_cent is not None:
            if linea.sentido == "saliente":
                salida.ingresos_cent += linea.base_cent
            else:
                salida.costes_cent += linea.base_cent
        if c.rubrica in salida.rubricas:
            salida.rubricas[c.rubrica][0] += c.omzet_cent
            salida.rubricas[c.rubrica][1] += c.btw_cent
            if linea.sentido == "saliente":
                salida.iva_repercutido_cent += c.btw_cent
            else:
                salida.iva_autoliquidado_cent += c.btw_cent
        salida.voorbelasting_cent += c.deducible_cent
    return salida


# ------------------------------------------------------------ lo que hay que revisar

def revisar(conn: sqlite3.Connection, ano: int, trimestre: int, facturas: set[int],
            fuera: dict[int, str] | None = None) -> list[dict[str, Any]]:
    """Las facturas del trimestre que piden revisar el IVA antes de declarar.

    - las que tienen un hallazgo de IVA pendiente (REGLAS_IVA), mas las de C4 del
      trimestre; una de C4 puede no estar ya en el (se anulo, cambio de fecha) y
      entra por la clave de su C4 (el §8);
    - las que tienen pendiente un hallazgo que pone en duda su IVA aunque no sea
      de IVA (REGLAS_DUDA: un duplicado contaria su IVA dos veces, una mal
      encaminada no es de BMS) o una lectura dudosa sin verificar de lo que se
      declara (Q2 en CAMPOS_DUDA);
    - `fuera`: las que no entran en las cifras (sin clasificar, con su motivo),
      tenga el hallazgo que tenga: lo que no se suma tiene que verlo alguien.

    `facturas` son las del trimestre (sus lineas).
    """
    reglas = sorted(REGLAS_IVA | REGLAS_DUDA)
    marcas = ", ".join("?" * len(reglas))
    objetivos: dict[int, set[int]] = defaultdict(set)
    campos_q2: dict[int, set[str]] = defaultdict(set)
    for hallazgo_id, fila_id, campo in conn.execute(
            f"SELECT o.hallazgo_id, o.fila_id, o.campo FROM hallazgo_objetivo AS o "
            f"JOIN hallazgo AS h ON h.id = o.hallazgo_id WHERE o.tabla = 'factura' "
            f"AND h.estado IN ('abierto', 'desaparecido') AND h.regla IN ({marcas})", reglas):
        objetivos[hallazgo_id].add(fila_id)
        if campo is not None:
            campos_q2[hallazgo_id].add(campo)
    c4 = f"C4|factura:%|{etiqueta(ano, trimestre)}"
    por_factura: dict[int, set[str]] = defaultdict(set)
    for fila in conn.execute(
            f"SELECT id, regla, clave, factura_id FROM hallazgo WHERE estado IN "
            f"('abierto', 'desaparecido') AND regla IN ({marcas}) ORDER BY id", reglas):
        de_este = set(objetivos.get(fila["id"], ())) | (
            {fila["factura_id"]} if fila["factura_id"] is not None else set())
        if fila["regla"] == "C4":
            if _como(fila["clave"], c4):
                por_factura[fila["factura_id"]].add("C4")
            continue
        if fila["regla"] == "Q2" and not campos_q2.get(fila["id"], set()) & CAMPOS_DUDA:
            continue
        for factura_id in de_este & facturas:
            por_factura[factura_id].add(fila["regla"])
    fuera = {f: m for f, m in (fuera or {}).items() if f in facturas}
    for factura_id in fuera:
        por_factura.setdefault(factura_id, set())
    if not por_factura:
        return []
    marcas = ", ".join("?" * len(por_factura))
    datos = {f["id"]: f for f in conn.execute(
        f"SELECT id, numero, sentido, emisor_nombre_doc, receptor_nombre_doc FROM factura "
        f"WHERE id IN ({marcas})", sorted(por_factura))}
    return [{"factura_id": f, "numero": datos[f]["numero"],
             "contraparte": datos[f]["emisor_nombre_doc"] if datos[f]["sentido"] == "entrante"
             else datos[f]["receptor_nombre_doc"],
             "reglas": sorted(por_factura[f], key=_orden_regla),
             "fuera_de_las_cifras": fuera.get(f)}
            for f in sorted(por_factura)]


def _fuera(cifras_: Cifras) -> dict[int, str]:
    """Por factura, el motivo por el que una de sus lineas no entra en las cifras."""
    salida: dict[int, str] = {}
    for c in cifras_.sin_clasificar:
        salida.setdefault(c.linea.factura_id, c.motivo or "sin clasificar")
    return salida


def _como(clave: str, patron: str) -> bool:
    cabeza, _, cola = patron.partition("%")
    return clave.startswith(cabeza) and clave.endswith(cola)


def _orden_regla(regla: str) -> tuple[str, int]:
    numero = "".join(c for c in regla if c.isdigit())
    return regla[0], int(numero or 0)


def diferencias(conn: sqlite3.Connection, periodo: sqlite3.Row | None,
                lineas_: list[LineaBtw]) -> list[dict[str, Any]]:
    """Lo que ya no es lo que se declaro en un trimestre presentado (lo mismo que mira C4)."""
    if periodo is None or periodo["estado"] != PRESENTADO:
        return []
    declaradas = {f["factura_id"]: f for f in conn.execute(
        "SELECT factura_id, huella, base_cent, cuota_cent FROM periodo_btw_declarada "
        "WHERE periodo_id = ?", (periodo["id"],))}
    ahora = huellas(lineas_)
    salida = []
    for factura_id in sorted(set(declaradas) | set(ahora)):
        antes, hoy = declaradas.get(factura_id), ahora.get(factura_id)
        if antes is not None and hoy == antes["huella"]:
            continue
        motivo = "tarde" if antes is None else "fuera" if hoy is None else "cambio"
        salida.append({"factura_id": factura_id, "motivo": motivo,
                       "base_declarada_cent": antes["base_cent"] if antes else None,
                       "cuota_declarada_cent": antes["cuota_cent"] if antes else None})
    return salida


# ------------------------------------------------------------ la hoja de trabajo

# Lo que empieza por uno de estos caracteres una hoja de calculo lo puede leer
# como una formula (=HYPERLINK, +cmd, -2+3, @SUM). Un texto que viene de un
# documento de un tercero (un nombre, un numero de factura) se escribe con un
# apostrofo delante: se lee como texto.
_FORMULA = ("=", "+", "-", "@", "\t", "\r", "\n")


def celda(valor: Any) -> str:
    """Un texto para la hoja, neutralizado contra formulas."""
    if valor is None:
        return ""
    texto = str(valor)
    if texto.startswith(_FORMULA) or texto.lstrip().startswith(_FORMULA[:4]):
        return "'" + texto
    return texto


def importe(cent: int | None) -> str:
    """Un importe de la hoja: 1234,56 o -200,00 (sin separador de miles). Es un numero que
    escribe el sistema, no un texto de un documento: no se neutraliza."""
    if cent is None:
        return ""
    return f"{de_cent(cent):.2f}".replace(".", ",")


def _tipo(pb: int | None) -> str:
    if pb is None:
        return ""
    return format(Decimal(pb).scaleb(-2).normalize(), "f").replace(".", ",")


@dataclass(frozen=True)
class Hoja:
    """Una hoja de trabajo: su texto (CSV con BOM, separador ";") y el sha256 de sus bytes."""

    ano: int
    trimestre: int
    texto: str
    sha256: str
    cifras_sha256: str = ""

    def en_bytes(self) -> bytes:
        """Los bytes que se exportan y de los que es el sha256."""
        return self.texto.encode("utf-8")


HUELLA_CIFRAS = "Huella de las cifras"


def _escribir_hoja(ano: int, trimestre: int, config: ConfigBtw, config_sha: str, empresa: str,
                   cifras_: Cifras, revisar_: list[dict[str, Any]],
                   diferencias_: list[dict[str, Any]]) -> str:
    """El texto de la hoja. No lleva ni la hora ni el estado: el mismo contenido da siempre
    el mismo sha256, el que se marca listo y el que se presenta.

    `config_sha` es el sha256 del btw.yaml en politica_version (el texto con que
    se hizo). La hoja lleva escrita la huella de sus cifras (huella_cifras): lo
    que anotar_presentacion compara con las de hoy."""
    inicio, fin = periodo_de(ano, trimestre)
    presentar, pagar = limites(ano, trimestre)
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(["Hoja de trabajo BTW", celda(empresa)])
    escritor.writerow(["Trimestre", etiqueta(ano, trimestre), inicio.isoformat(),
                       fin.isoformat()])
    escritor.writerow(["Plazo de presentación", presentar.isoformat()])
    escritor.writerow(["Plazo de pago", pagar.isoformat()])
    escritor.writerow(["Sistema", config.sistema, config.periodicidad])
    escritor.writerow(["Configuración (btw.yaml)", config_sha,
                       "confirmada por el asesor" if config.confirmado
                       else "POR CONFIRMAR CON EL ASESOR"])
    escritor.writerow([HUELLA_CIFRAS, huella_cifras(cifras_)])
    escritor.writerow(["La presenta una persona en el portal de la Belastingdienst; "
                       "el agente no presenta nada."])
    escritor.writerow([])
    escritor.writerow(["Rúbrica", "Descripción", "Omzet (sin IVA)", "Omzetbelasting"])
    for rubrica, (omzet, btw) in cifras_.rubricas.items():
        escritor.writerow([rubrica, RUBRICAS[rubrica], importe(omzet), importe(btw)])
    escritor.writerow(["5a", RUBRICAS["5a"], "", importe(cifras_.iva_a_declarar_cent)])
    escritor.writerow(["5b", RUBRICAS["5b"], "", importe(cifras_.voorbelasting_cent)])
    escritor.writerow(["5c", RUBRICAS["5c"], "", importe(cifras_.saldo_cent)])
    escritor.writerow([])
    escritor.writerow(["Resumen"])
    for nombre, valor in (("Ingresos sin IVA", cifras_.ingresos_cent),
                          ("IVA repercutido", cifras_.iva_repercutido_cent),
                          ("IVA autoliquidado (2a, 4a, 4b)", cifras_.iva_autoliquidado_cent),
                          ("Costes sin IVA", cifras_.costes_cent),
                          ("IVA soportado deducible (5b)", cifras_.voorbelasting_cent)):
        escritor.writerow([nombre, importe(valor)])
    saldo = cifras_.saldo_cent
    escritor.writerow(["Estimación: a pagar" if saldo >= 0 else "Estimación: a devolver",
                       importe(abs(saldo))])
    escritor.writerow([])
    escritor.writerow(["Líneas"])
    escritor.writerow(["Factura", "Sentido", "Tipo", "Número", "Contraparte", "Fecha",
                       "Tratamiento", "Tipo IVA", "Base", "Cuota", "Autoliquidada", "Rúbrica",
                       "Nota"])
    for c in cifras_.lineas:
        l = c.linea
        escritor.writerow([l.factura_id, l.sentido, l.tipo, celda(l.numero),
                           celda(l.contraparte), l.fecha.isoformat() if l.fecha else "",
                           l.tratamiento or "", _tipo(l.tipo_efectivo_pb), importe(l.base_cent),
                           importe(l.cuota_cent),
                           importe(c.autoliquidado_cent) if c.autoliquidado_cent else "",
                           c.rubrica or "", c.motivo or ""])
    escritor.writerow([])
    escritor.writerow(["Facturas que piden revisar el IVA"])
    escritor.writerow(["Factura", "Número", "Contraparte", "Reglas", "Fuera de las cifras"])
    for r in revisar_:
        escritor.writerow([r["factura_id"], celda(r["numero"]), celda(r["contraparte"]),
                           ", ".join(r["reglas"]), r["fuera_de_las_cifras"] or ""])
    escritor.writerow([])
    escritor.writerow(["Fuera de las cifras"])
    escritor.writerow(["Factura", "Número", "Contraparte", "Motivo"])
    for c in cifras_.sin_clasificar + cifras_.fuera:
        escritor.writerow([c.linea.factura_id, celda(c.linea.numero),
                           celda(c.linea.contraparte), c.motivo or "no va en la declaración"])
    if diferencias_:
        escritor.writerow([])
        escritor.writerow(["Diferencias con lo presentado"])
        escritor.writerow(["Factura", "Motivo", "Base declarada", "Cuota declarada"])
        for d in diferencias_:
            escritor.writerow([d["factura_id"], d["motivo"], importe(d["base_declarada_cent"]),
                               importe(d["cuota_declarada_cent"])])
    return "\ufeff" + salida.getvalue()


def hoja(conn: sqlite3.Connection, ano: int, trimestre: int) -> Hoja:
    """La hoja de trabajo de un trimestre tal como esta ahora, con el btw.yaml vigente."""
    periodo_de(ano, trimestre)
    config, config_sha = politica.config_btw_y_sha(conn)
    propias = lineas(conn, ano, trimestre)
    cifras_ = cifras(propias, config)
    revisar_ = revisar(conn, ano, trimestre, {l.factura_id for l in propias}, _fuera(cifras_))
    texto = _escribir_hoja(ano, trimestre, config, config_sha, politica.empresa(conn).nombre,
                           cifras_, revisar_,
                           diferencias(conn, periodo(conn, ano, trimestre), propias))
    return Hoja(ano, trimestre, texto, sha256_texto(texto), huella_cifras(cifras_))


def huella_escrita(texto: str) -> str | None:
    """La huella de las cifras que lleva escrita una hoja (None en una de antes de llevarla)."""
    for fila in csv.reader(io.StringIO(texto.lstrip("\ufeff")), delimiter=";"):
        if not fila:
            break
        if fila[0] == HUELLA_CIFRAS and len(fila) > 1:
            return fila[1]
    return None


# ------------------------------------------------------------ lo que se ve

def periodo(conn: sqlite3.Connection, ano: int, trimestre: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM periodo_btw WHERE ano = ? AND trimestre = ?",
                        (ano, trimestre)).fetchone()


def estado_de(conn: sqlite3.Connection, ano: int, trimestre: int) -> str:
    """El estado de un trimestre: el de su fila, o abierto si no la tiene."""
    fila = periodo(conn, ano, trimestre)
    return fila["estado"] if fila else ABIERTO


def trimestre(conn: sqlite3.Connection, ano: int, trimestre_: int,
              hoy: date | None = None) -> dict[str, Any]:
    """Todo lo de un trimestre: su estado, sus plazos, sus cifras, lo que hay que revisar, lo
    que quedo fuera y, si se presento, lo que ya no es lo declarado."""
    hoy = hoy or reloj_de(conn).hoy()
    config, config_sha = politica.config_btw_y_sha(conn)
    inicio, fin = periodo_de(ano, trimestre_)
    presentar, pagar = limites(ano, trimestre_)
    fila = periodo(conn, ano, trimestre_)
    propias = lineas(conn, ano, trimestre_)
    cifras_ = cifras(propias, config)
    revisar_ = revisar(conn, ano, trimestre_, {l.factura_id for l in propias}, _fuera(cifras_))
    diferencias_ = diferencias(conn, fila, propias)
    texto = _escribir_hoja(ano, trimestre_, config, config_sha, politica.empresa(conn).nombre,
                           cifras_, revisar_, diferencias_)
    sha = sha256_texto(texto)
    marcada = _huella_marcada(conn, fila)
    estado = fila["estado"] if fila else ABIERTO
    return {
        "ano": ano, "trimestre": trimestre_, "etiqueta": etiqueta(ano, trimestre_),
        "inicio": inicio.isoformat(), "fin": fin.isoformat(), "terminado": fin < hoy,
        "limite_presentacion": presentar.isoformat(), "limite_pago": pagar.isoformat(),
        "dias_para_limite": (presentar - hoy).days, "estado": estado,
        "rev": fila["rev"] if fila else None,
        "listo_por": _nombre(conn, fila["listo_por"]) if fila else None,
        "presentado_en": fila["presentado_en"] if fila else None,
        "presentado_por": _nombre(conn, fila["presentado_por"]) if fila else None,
        "referencia": fila["referencia_presentacion"] if fila else None,
        "importe_declarado_cent": fila["importe_declarado_cent"] if fila else None,
        "hoja_sha256": sha, "hoja_marcada_sha256": fila["hoja_sha256"] if fila else None,
        "hoja_al_dia": fila is None or fila["hoja_sha256"] in (None, sha),
        "cifras_sha256": huella_cifras(cifras_),
        "cifras_al_dia": marcada is None or marcada == huella_cifras(cifras_),
        "configuracion": {"sha256": config_sha, "confirmada": config.confirmado},
        "cifras": cifras_.como_dict(), "revisar": revisar_, "diferencias": diferencias_,
    }


def _huella_marcada(conn: sqlite3.Connection, fila: sqlite3.Row | None) -> str | None:
    """La huella de las cifras de la hoja marcada lista de un periodo, o None si no la hay.

    Una hoja guardada antes de llevarla escrita da su sha256 entero: con ella
    solo vale la misma hoja, como antes."""
    if fila is None or fila["hoja_id"] is None:
        return None
    guardada = conn.execute("SELECT sha256, contenido FROM hoja_btw WHERE id = ?",
                            (fila["hoja_id"],)).fetchone()
    if guardada is None:
        return None
    return huella_escrita(guardada["contenido"]) or guardada["sha256"]


def _nombre(conn: sqlite3.Connection, usuario_id: int | None) -> str | None:
    if usuario_id is None:
        return None
    fila = conn.execute("SELECT nombre FROM usuario WHERE id = ?", (usuario_id,)).fetchone()
    return fila["nombre"] if fila else None


def resumen(conn: sqlite3.Connection, hoy: date | None = None) -> dict[str, Any]:
    """El BTW de un vistazo: el trimestre en curso, los que estan por presentar con su
    plazo, los anteriores con su estado, el ano hasta hoy y lo que no tiene fecha."""
    hoy = hoy or reloj_de(conn).hoy()
    config, config_sha = politica.config_btw_y_sha(conn)
    todas = lineas(conn)
    actual = trimestre_de(hoy)
    # Los trimestres con facturas o con estado, los ya terminados de este ano y el
    # anterior al de hoy (en enero, el cuarto del ano pasado, que vence el 31) aunque
    # no tengan nada: un trimestre sin facturas tambien se declara.
    vistos = {l.trimestre for l in todas if l.trimestre is not None}
    vistos |= {(f["ano"], f["trimestre"]) for f in conn.execute(
        "SELECT ano, trimestre FROM periodo_btw")}
    vistos |= {(actual[0], numero) for numero in range(1, actual[1])}
    vistos.add(anterior(*actual))
    anteriores = []
    for ano, numero in sorted((t for t in vistos if t < actual), reverse=True):
        propias = [l for l in todas if l.trimestre == (ano, numero)]
        c = cifras(propias, config).como_dict()
        presentar, _pagar = limites(ano, numero)
        anteriores.append({
            "ano": ano, "trimestre": numero, "etiqueta": etiqueta(ano, numero),
            "estado": estado_de(conn, ano, numero),
            "limite_presentacion": presentar.isoformat(),
            "dias_para_limite": (presentar - hoy).days,
            "5a": c["5a"], "5b": c["5b"], "5c": c["5c"], "ingresos_cent": c["ingresos_cent"],
            "costes_cent": c["costes_cent"]})
    del_ano = [l for l in todas if l.fecha is not None and l.fecha.year == hoy.year
               and l.fecha <= hoy]
    return {
        "hoy": hoy.isoformat(),
        "configuracion": {"sha256": config_sha, "confirmada": config.confirmado},
        "actual": trimestre(conn, *actual, hoy=hoy),
        "por_presentar": [a for a in anteriores if a["estado"] != PRESENTADO],
        "anteriores": anteriores,
        "ano_hasta_hoy": {"ano": hoy.year, **{k: v for k, v in cifras(
            del_ano, config).como_dict().items() if k not in ("sin_clasificar", "fuera")}},
        "sin_fecha": len({l.factura_id for l in todas if l.fecha is None}),
    }


# ------------------------------------------------------------ las ordenes

def _cambios_alta(fila_id: int, valores: dict[str, Any], motivo: str | None) -> list[Cambio]:
    return [Cambio(tabla=TABLA, fila_id=fila_id, campo=c, rev=0, valor_anterior=None,
                   valor_nuevo=valores[c], fuente_nueva=Fuente.MANUAL_ENTRADA.value,
                   motivo=motivo)
            for c in COLUMNAS if valores.get(c) is not None]


def _escribir(conn: sqlite3.Connection, persona: Persona, fila: sqlite3.Row | None, ano: int,
              trimestre_: int, nuevos: dict[str, Any], *, tipo: str, motivo: str | None,
              datos: dict[str, Any]) -> tuple[int, int]:
    """Una orden sobre un periodo: su evento con un cambio_campo por columna, y la fila.

    Sin fila, la da de alta con su calendario y sus plazos. Devuelve el evento y el id.
    """
    usuario = persona.usuario_id
    if fila is None:
        inicio, fin = periodo_de(ano, trimestre_)
        presentar, pagar = limites(ano, trimestre_)
        fila_id = int(conn.execute("SELECT coalesce(max(id), 0) + 1 FROM periodo_btw"
                                   ).fetchone()[0])
        valores = {"ano": ano, "trimestre": trimestre_, "inicio": inicio.isoformat(),
                   "fin": fin.isoformat(), "limite_presentacion": presentar.isoformat(),
                   "limite_pago": pagar.isoformat(), "estado": ABIERTO, **nuevos}
        evento = registrar(conn, tipo=tipo, actor=usuario, usuario_id=usuario, tabla=TABLA,
                           fila_id=fila_id, motivo=motivo, peticion_id=persona.peticion_id,
                           datos=datos, cambios=_cambios_alta(fila_id, valores, motivo))
        columnas = ("id", *COLUMNAS, "rev")
        conn.execute(f"INSERT INTO periodo_btw ({', '.join(columnas)}) "
                     f"VALUES ({', '.join('?' * len(columnas))})",
                     (fila_id, *(valores.get(c) for c in COLUMNAS), 0))
        return evento, fila_id
    rev = fila["rev"] + 1
    cambios = [Cambio(tabla=TABLA, fila_id=fila["id"], campo=c, rev=rev,
                      valor_anterior=fila[c], valor_nuevo=v,
                      fuente_nueva=Fuente.MANUAL_ENTRADA.value,
                      fuente_anterior=Fuente.MANUAL_ENTRADA.value, motivo=motivo)
               for c, v in nuevos.items() if v != fila[c]]
    evento = registrar(conn, tipo=tipo, actor=usuario, usuario_id=usuario, tabla=TABLA,
                       fila_id=fila["id"], motivo=motivo, peticion_id=persona.peticion_id,
                       datos=datos, cambios=cambios)
    asignaciones = ", ".join(f"{c} = ?" for c in nuevos)
    cursor = conn.execute(
        f"UPDATE periodo_btw SET {asignaciones}, rev = ? WHERE id = ? AND rev = ?",
        (*nuevos.values(), rev, fila["id"], fila["rev"]))
    if cursor.rowcount != 1:
        raise Conflicto(f"el trimestre {etiqueta(ano, trimestre_)} cambio mientras se escribia")
    return evento, fila["id"]


def _guardar_hoja(conn: sqlite3.Connection, persona: Persona, hoja_: Hoja,
                  datos: dict[str, Any]) -> int:
    """La hoja en hoja_btw, con su evento; la misma hoja (el mismo sha256) no se guarda dos
    veces."""
    fila = conn.execute("SELECT id FROM hoja_btw WHERE sha256 = ?", (hoja_.sha256,)).fetchone()
    if fila is not None:
        return int(fila["id"])
    usuario = persona.usuario_id
    hoja_id = int(conn.execute("SELECT coalesce(max(id), 0) + 1 FROM hoja_btw").fetchone()[0])
    foto = {"ano": hoja_.ano, "trimestre": hoja_.trimestre, "sha256": hoja_.sha256,
            "generada_en": marca(reloj_de(conn).ahora()), "usuario_id": usuario}
    evento = registrar(conn, tipo=EVENTO_HOJA, actor=usuario, usuario_id=usuario,
                       tabla="hoja_btw", fila_id=hoja_id, motivo=persona.motivo,
                       datos={**datos, "fila": foto})
    conn.execute(
        "INSERT INTO hoja_btw (id, ano, trimestre, sha256, contenido, generada_en, usuario_id, "
        "evento_id) VALUES (:id, :ano, :trimestre, :sha256, :contenido, :generada_en, "
        ":usuario_id, :evento_id)",
        {**foto, "id": hoja_id, "contenido": hoja_.texto, "evento_id": evento})
    return hoja_id


def _terminado(conn: sqlite3.Connection, ano: int, trimestre_: int) -> date:
    """El ultimo dia del trimestre, si ya paso; si no, EstadoNoValido."""
    _inicio, fin = periodo_de(ano, trimestre_)
    if fin >= reloj_de(conn).hoy():
        raise EstadoNoValido(f"el trimestre {etiqueta(ano, trimestre_)} no ha terminado: no se "
                             "puede preparar su declaracion hasta el dia siguiente a su fin")
    return fin


def marcar_lista(conn: sqlite3.Connection, persona: Persona, ano: int, trimestre_: int, *,
                 hoja_sha256: str, datos: dict[str, Any] | None = None) -> int | None:
    """Marca un trimestre terminado como listo para revisar, con la hoja que vio la persona.

    `hoja_sha256` es el de la hoja que se reviso: si las cifras cambiaron desde
    entonces, Conflicto. La hoja se guarda entera. Un trimestre ya listo con
    esa misma hoja no cambia (None); uno presentado no vuelve a estar listo.
    """
    with orden_auditada(conn):
        exigir(conn, persona.usuario_id, GESTIONAR, accion="marcar un trimestre del BTW listo")
        _terminado(conn, ano, trimestre_)
        fila = periodo(conn, ano, trimestre_)
        if fila is not None and fila["estado"] == PRESENTADO:
            raise EstadoNoValido(f"el trimestre {etiqueta(ano, trimestre_)} ya esta presentado: "
                                 "es irreversible")
        politica.apuntar_btw_en_uso(conn, persona.usuario_id)
        _config, config_sha = politica.config_btw_y_sha(conn)
        hoja_ = hoja(conn, ano, trimestre_)
        if hoja_sha256 != hoja_.sha256:
            raise Conflicto(f"la hoja del trimestre {etiqueta(ano, trimestre_)} cambio desde que "
                            "se miro: vuelve a generarla y a revisarla")
        if fila is not None and fila["estado"] == LISTO and fila["hoja_sha256"] == hoja_.sha256:
            return None
        datos = dict(datos or {})
        hoja_id = _guardar_hoja(conn, persona, hoja_, datos)
        evento, _id = _escribir(
            conn, persona, fila, ano, trimestre_,
            {"estado": LISTO, "hoja_id": hoja_id, "hoja_sha256": hoja_.sha256,
             "listo_en": marca(reloj_de(conn).ahora()), "listo_por": persona.usuario_id},
            tipo=EVENTO_LISTO, motivo=(persona.motivo or "").strip() or None,
            datos={**datos, "hoja_sha256": hoja_.sha256, "cifras_sha256": hoja_.cifras_sha256,
                   "configuracion": config_sha})
        return evento


def reabrir(conn: sqlite3.Connection, persona: Persona, ano: int, trimestre_: int, *,
            rev: int, datos: dict[str, Any] | None = None) -> int:
    """Devuelve a abierto un trimestre listo para revisar (con motivo): la hoja ya no vale."""
    motivo = (persona.motivo or "").strip()
    with orden_auditada(conn):
        exigir(conn, persona.usuario_id, GESTIONAR, accion="reabrir un trimestre del BTW")
        if not motivo:
            raise FaltaMotivo("reabrir un trimestre del BTW pide un motivo")
        fila = periodo(conn, ano, trimestre_)
        if fila is None or fila["estado"] != LISTO:
            raise EstadoNoValido(
                f"el trimestre {etiqueta(ano, trimestre_)} no esta listo para revisar "
                + ("(esta presentado: es irreversible)" if fila is not None
                   and fila["estado"] == PRESENTADO else "(ya esta abierto)"))
        if fila["rev"] != rev:
            raise Conflicto(f"el trimestre {etiqueta(ano, trimestre_)} cambio (rev {fila['rev']}, "
                            f"no {rev}): vuelve a mirarlo")
        evento, _id = _escribir(
            conn, persona, fila, ano, trimestre_,
            {"estado": ABIERTO, "hoja_id": None, "hoja_sha256": None, "listo_en": None,
             "listo_por": None}, tipo=EVENTO_REABIERTO, motivo=motivo, datos=dict(datos or {}))
        return evento


def anotar_presentacion(conn: sqlite3.Connection, persona: Persona, ano: int, trimestre_: int,
                        *, hoja_sha256: str, referencia: str, importe_declarado: Decimal,
                        fecha: date | None = None, rev: int | None = None,
                        datos: dict[str, Any] | None = None) -> int:
    """Anota que una persona presento el trimestre en el portal: es irreversible.

    Se presenta lo que se marco listo: `hoja_sha256` tiene que ser la hoja
    marcada y las cifras de hoy tienen que seguir siendo las suyas (la huella
    que lleva escrita; si no, Conflicto: se vuelve a marcar lista y a revisar).
    Lo que se revisa no entra: resolver o anular un hallazgo despues de marcarla
    es lo normal y no obliga a marcarla otra vez. `rev`, si se da, es la del
    periodo que vio la persona (servicios la pide siempre). La referencia es la del
    acuse de la Belastingdienst; `importe_declarado`, lo que se declaro a pagar
    (en negativo, a devolver); `fecha`, el dia en que se presento (por
    defecto hoy), despues del trimestre y nunca en el futuro. Quien la marco
    lista no la anota si hay otra persona con gestionar_btw (si no, queda
    autorrevisado). Apunta lo declarado de cada factura: contra eso mira C4.
    """
    texto = (referencia or "").strip()
    with orden_auditada(conn):
        exigir(conn, persona.usuario_id, GESTIONAR,
               accion="anotar la presentacion de un trimestre del BTW")
        fin = _terminado(conn, ano, trimestre_)
        fila = periodo(conn, ano, trimestre_)
        if fila is None or fila["estado"] != LISTO:
            raise EstadoNoValido(
                f"el trimestre {etiqueta(ano, trimestre_)} se anota presentado desde listo para "
                "revisar" + (": ya esta presentado, es irreversible"
                             if fila is not None and fila["estado"] == PRESENTADO else ""))
        if not texto:
            raise FaltaMotivo("anotar una presentacion pide la referencia de la Belastingdienst")
        hoy = reloj_de(conn).hoy()
        dia = fecha or hoy
        if dia <= fin or dia > hoy:
            raise ValueError(f"la presentacion es de despues del trimestre ({fin.isoformat()}) "
                             f"y no del futuro, no del {dia.isoformat()}")
        if rev is not None and fila["rev"] != rev:
            raise Conflicto(f"el trimestre {etiqueta(ano, trimestre_)} cambio (rev {fila['rev']}, "
                            f"no {rev}): vuelve a mirarlo")
        if hoja_sha256 != fila["hoja_sha256"]:
            raise Conflicto("esa no es la hoja que se marco lista: se presenta la que se reviso")
        config = politica.apuntar_btw_en_uso(conn, persona.usuario_id)
        propias = lineas(conn, ano, trimestre_)
        cifras_ = cifras(propias, config)
        marcada = _huella_marcada(conn, fila)
        ahora = (huella_cifras(cifras_) if marcada != fila["hoja_sha256"]
                 else hoja(conn, ano, trimestre_).sha256)
        if ahora != marcada:
            raise Conflicto(f"las cifras del trimestre {etiqueta(ano, trimestre_)} cambiaron desde "
                            "que se marco listo: vuelve a marcarlo listo y a revisarlo")
        decision = separacion(conn, GESTIONAR, fila["listo_por"], persona.usuario_id)
        if decision == DENEGADO:
            raise SeparacionDeFunciones(
                persona.usuario_id, GESTIONAR, "quien marco la hoja lista no anota su "
                "presentacion habiendo otra persona con gestionar_btw",
                "anotar la presentacion de un trimestre del BTW")
        declaradas = _declaradas(conn, propias)
        importe_cent = a_cent(importe_declarado)
        evento, periodo_id = _escribir(
            conn, persona, fila, ano, trimestre_,
            {"estado": PRESENTADO, "presentado_en": dia.isoformat(),
             "presentado_por": persona.usuario_id, "referencia_presentacion": texto,
             "importe_declarado_cent": importe_cent,
             "nota": (persona.motivo or "").strip() or fila["nota"]},
            tipo=EVENTO_PRESENTADO, motivo=(persona.motivo or "").strip() or None,
            datos={**(datos or {}), "hoja_sha256": fila["hoja_sha256"],
                   "cifras_sha256": huella_cifras(cifras_),
                   "autorrevisado": decision == AUTORREVISADO,
                   "estimado_cent": cifras_.saldo_cent,
                   "declaradas": {str(i): {**d, "periodo_id": fila["id"]}
                                  for i, d in declaradas.items()}})
        conn.executemany(
            "INSERT INTO periodo_btw_declarada (id, periodo_id, factura_id, huella, base_cent, "
            "cuota_cent, evento_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(i, periodo_id, d["factura_id"], d["huella"], d["base_cent"], d["cuota_cent"],
              evento) for i, d in sorted(declaradas.items())])
        return evento


def _declaradas(conn: sqlite3.Connection, propias: list[LineaBtw]) -> dict[int, dict[str, Any]]:
    """Lo que se declara de cada factura del trimestre, con el id que tendra su fila."""
    siguiente = int(conn.execute("SELECT coalesce(max(id), 0) + 1 FROM periodo_btw_declarada"
                                 ).fetchone()[0])
    por_factura = declarables(propias)
    huella_de = huellas(propias)
    salida = {}
    for i, factura_id in enumerate(sorted(por_factura), start=siguiente):
        lineas_ = por_factura[factura_id]
        bases = [l.base_cent for l in lineas_]
        cuotas = [l.cuota_cent for l in lineas_]
        salida[i] = {"factura_id": factura_id, "huella": huella_de[factura_id],
                     "base_cent": None if None in bases else sum(bases),
                     "cuota_cent": None if None in cuotas else sum(cuotas)}
    return salida


# ------------------------------------------------------------ comprobar

def verificar(conn: sqlite3.Connection) -> list[str]:
    """Que cada periodo sea lo que dice su historia, sin fiarse de los disparadores (como
    excepciones.verificar). Las hojas guardadas y lo declarado son evidencia: los comprueba
    almacen/evidencia.py."""
    problemas: list[str] = []
    ultimos: dict[tuple[int, str], str] = {}
    revs: dict[int, int] = {}
    for fila_id, campo, rev, valor in conn.execute(
            "SELECT fila_id, campo, rev, valor_nuevo FROM cambio_campo WHERE tabla = ? "
            "ORDER BY id", (TABLA,)):
        ultimos[(fila_id, campo)] = valor
        revs[fila_id] = max(revs.get(fila_id, 0), rev)
    existentes = set()
    for fila in conn.execute("SELECT * FROM periodo_btw ORDER BY id"):
        existentes.add(fila["id"])
        nombre = f"el trimestre {etiqueta(fila['ano'], fila['trimestre'])}"
        if fila["id"] not in revs:
            problemas.append(f"{nombre} no tiene historia: se ha metido por detras")
            continue
        if fila["rev"] != revs[fila["id"]]:
            problemas.append(f"{nombre}: rev {fila['rev']} y su ultimo cambio es la "
                             f"{revs[fila['id']]}")
        for columna in COLUMNAS:
            actual = None if fila[columna] is None else json_canonico(fila[columna])
            esperado = ultimos.get((fila["id"], columna))
            if esperado == "null":
                esperado = None
            if actual != esperado:
                problemas.append(f"{nombre}: {columna} no es lo que dejo su ultimo cambio (se ha "
                                 "modificado por detras)")
    for fila_id in sorted(set(revs) - existentes):
        problemas.append(f"el periodo del BTW {fila_id} tiene historia y ya no existe: se ha "
                         "borrado")
    return problemas


def a_json(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, indent=2)


def euros(cent: int | None) -> str:
    """Un importe para la CLI: 12.400,00."""
    return "-" if cent is None else euros_texto(de_cent(cent))
