"""Los registros canonicos de los maestros (spec §9): lo que un lector entrega.

Modelos de pydantic con `extra='forbid'`: un campo que no esta aqui no
existe, y una fila que lo trae se rechaza. Por eso un mapeo no puede hacer
que una importacion escriba el estado de una cuenta (`verificada`): la
cuenta canonica no tiene estado, solo titular, a quien pertenece, IBAN y
nombre del titular.

Importes en Decimal (nunca float) y fechas como date. Cada registro guarda
su fila y su contenido crudo, tal como venia, para explicar despues de donde
salio cada valor.

Las referencias (`*_ref`) son como el fichero nombra a otra fila: el numero
de Exact de un proveedor o un cliente, el codigo de un Objeto, el nombre de
un recurso. registrar.py las resuelve por coincidencia exacta; lo que no se
encuentra es un rechazo (Z2), nunca un alta.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator, model_validator

from ..reglas.bancaria import validar_iban
from ..reglas.normas import normalizar_iban, parece_iban

Regimen = Literal["estandar", "autoliquidacion", "kor", "exento", "tipo_cero", "desconocido"]


class Canonico(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fila: int
    crudo: dict[str, str]


class ProveedorCanonico(Canonico):
    id_externo: str | None = None
    nombre: str
    tipo: Literal["zzp", "empresa"] | None = None
    kvk: str | None = None
    btw_id: str | None = None
    regimen_iva: Regimen | None = None
    plazo_pago_dias: int | None = None
    direccion: str | None = None
    email_facturacion: str | None = None
    telefono_verificacion: str | None = None
    activo: bool = True


class ClienteCanonico(Canonico):
    id_externo: str | None = None
    nombre: str
    kvk: str | None = None
    btw_id: str | None = None
    plazo_pago_dias: int | None = None
    requiere_po: bool | None = None
    tratamiento_iva_defecto: Regimen | None = None
    verlegd_elegible: bool = False
    activo: bool = True


class ContactoCanonico(Canonico):
    """Una persona de contacto de un proveedor o un cliente.

    Su telefono es para hablar con ella, nunca el de verificacion de las
    cuentas: ese es un campo del proveedor con su propia orden y su
    enfriamiento (F8, F9), y ningun contacto lo cambia.
    """

    titular: Literal["proveedor", "cliente"]
    parte_ref: str
    nombre: str
    email: str | None = None
    telefono: str | None = None
    funcion: str | None = None
    activo: bool = True


class CuentaBancariaCanonica(Canonico):
    """Una cuenta de un proveedor o un cliente segun su maestro. No lleva ningun estado."""

    titular: Literal["proveedor", "cliente"]
    parte_ref: str
    iban: str
    nombre_titular: str | None = None

    @field_validator("iban")
    @classmethod
    def _iban_valido(cls, valor: str) -> str:
        limpio = normalizar_iban(valor) or ""
        if not validar_iban(limpio):
            raise ValueError(f"{limpio!r} no pasa el digito de control modulo 97")
        return limpio


class ObjetoCanonico(Canonico):
    codigo: str
    nombre: str
    cliente_ref: str | None = None
    requiere_po: bool | None = None
    activo_desde: date | None = None
    activo_hasta: date | None = None


class RecursoCanonico(Canonico):
    nombre: str
    tipo: Literal["empleado", "zzp", "personal_proveedor"] | None = None
    proveedor_ref: str | None = None
    activo: bool = True


class AliasCanonico(Canonico):
    """Otro nombre con el que se reconoce una fila que ya existe (nunca un IBAN)."""

    tabla: Literal["proveedor", "cliente", "objeto", "recurso"]
    alias: str
    destino_ref: str


class TarifaCanonica(Canonico):
    """Una tarifa pactada. `moneda` es la del fichero: lo que no es el euro no entra (X1)."""

    sentido: Literal["compra", "venta"]
    proveedor_ref: str | None = None
    recurso_ref: str | None = None
    cliente_ref: str | None = None
    objeto_ref: str | None = None
    tipo_servicio: str | None = None
    tipo_turno: str | None = None
    unidad: str | None = None
    tarifa: Decimal
    tarifa_crudo: str
    moneda: str | None = None
    vigente_desde: date | None = None
    vigente_hasta: date | None = None


class CicloCanonico(Canonico):
    cliente_ref: str | None = None
    objeto_ref: str | None = None
    frecuencia: Literal["semanal", "cuatrisemanal", "mensual"]
    ancla: date | None = None
    dias_gracia: int = 0
    vigente_desde: date | None = None
    vigente_hasta: date | None = None


# ------------------------------------------------------------ banco y pagos (paso 7)

def _iban_o_nada(valor: str | None) -> str | None:
    """La cuenta de la contraparte si tiene forma de IBAN; si no (un numero antiguo, nada), None.

    Es lo que dice el banco de adonde fue o de donde vino el dinero: sirve
    para casar y para comparar con el registro (F7). No se comprueba el
    digito de control: si el banco da un IBAN raro, eso es lo que paso.
    """
    limpio = normalizar_iban(valor)
    return limpio if limpio and parece_iban(limpio) else None


class MovimientoCanonico(Canonico):
    """Un apunte del banco (o una transaccion de un apunte agrupado). importe con signo:
    un cargo es negativo. moneda es la del apunte: lo que no es EUR no entra en ninguna suma."""

    cuenta_propia_iban: str | None = None
    fecha_contable: date
    fecha_valor: date | None = None
    importe: Decimal
    importe_crudo: str
    moneda: str = "EUR"
    contraparte_iban: str | None = None
    contraparte_nombre: str | None = None
    concepto: str | None = None
    referencia_estructurada: str | None = None
    referencia_e2e: str | None = None
    ref_banco: str | None = None
    remesa: str | None = None

    @field_validator("moneda")
    @classmethod
    def _moneda(cls, valor: str) -> str:
        texto = (valor or "").strip().upper()
        if len(texto) != 3 or not texto.isalpha():
            raise ValueError(f"{valor!r} no es un codigo de moneda")
        return texto

    @field_validator("cuenta_propia_iban")
    @classmethod
    def _propia(cls, valor: str | None) -> str | None:
        return normalizar_iban(valor)

    @field_validator("contraparte_iban")
    @classmethod
    def _contraparte(cls, valor: str | None) -> str | None:
        return _iban_o_nada(valor)


class ExtractoCanonico(Canonico):
    """Un extracto de una cuenta: sus saldos, su numero de secuencia y sus movimientos.

    `con_saldos` es falso en los CSV del banco: no traen saldo de apertura ni
    de cierre fiables, y con ellos no se evalua la continuidad (K6).
    """

    cuenta_propia_iban: str
    identificador: str | None = None
    secuencia: int | None = None
    moneda: str = "EUR"
    saldo_inicial: Decimal | None = None
    saldo_final: Decimal | None = None
    fecha_saldo_inicial: date | None = None
    fecha_saldo_final: date | None = None
    desde: date | None = None
    hasta: date | None = None
    con_saldos: bool = True
    formato: str
    movimientos: tuple[MovimientoCanonico, ...] = ()

    @field_validator("cuenta_propia_iban")
    @classmethod
    def _propia(cls, valor: str) -> str:
        limpio = normalizar_iban(valor) or ""
        if not validar_iban(limpio):
            raise ValueError(f"{limpio!r} no es un IBAN que pase el digito de control")
        return limpio


class PagoExactCanonico(Canonico):
    """Lo que dice Exact de lo pagado de una factura: el importe pagado, o lo que queda abierto.

    `sentido` es el diario: compra (crediteuren) o venta (debiteuren).
    `parte_ref` es el numero de Exact del proveedor o el cliente; `numero`, el
    de la factura como lo imprime. Con importe_pagado vale ese; si no, lo
    pagado es la factura menos lo abierto.
    """

    sentido: Literal["compra", "venta"]
    parte_ref: str
    numero: str
    importe_factura: Decimal | None = None
    importe_abierto: Decimal | None = None
    importe_pagado: Decimal | None = None
    fecha_pago: date | None = None
    moneda: str | None = None


# ------------------------------------------------------------ facturas de venta (paso 8)

class FilaVentaCanonica(Canonico):
    """Una fila de un listado de facturas de venta (Exact): la cabecera, repetida, y una linea.

    Un listado de ventas con lineas trae una fila por linea con los datos de
    la factura en cada una; ventas.py las junta en una FacturaVentaCanonica
    (y rechaza la factura si sus filas no dicen lo mismo de la cabecera).
    `objeto_ref` es el centro de coste o el proyecto: el codigo (o un alias)
    de un Objeto. `factura_relacionada`, la factura que abona o corrige.
    """

    id_externo: str | None = None
    numero: str
    tipo: Literal["factura", "nota_credito"] | None = None
    cliente_ref: str
    cliente_nombre: str | None = None
    cliente_btw: str | None = None
    contacto: str | None = None
    fecha_factura: date
    fecha_vencimiento: date | None = None
    condiciones_pago: str | None = None
    periodo_inicio: date | None = None
    periodo_fin: date | None = None
    tratamiento_iva: Regimen | None = None
    base: Decimal | None = None
    base_crudo: str | None = None
    iva: Decimal | None = None
    iva_crudo: str | None = None
    total: Decimal | None = None
    total_crudo: str | None = None
    po_ref: str | None = None
    factura_relacionada: str | None = None
    moneda: str | None = None
    orden: int
    descripcion: str | None = None
    objeto_ref: str | None = None
    recurso_ref: str | None = None
    linea_desde: date | None = None
    linea_hasta: date | None = None
    cantidad: Decimal | None = None
    cantidad_crudo: str | None = None
    unidad: str | None = None
    tarifa: Decimal | None = None
    tarifa_crudo: str | None = None
    importe: Decimal
    importe_crudo: str
    tipo_iva: Decimal | None = None
    cuota_iva: Decimal | None = None
    linea_po_ref: str | None = None


class LineaVentaCanonica(Canonico):
    """Una linea de una factura de venta: lo que se facturo, de que Objeto y de que periodo."""

    orden: int
    descripcion: str | None = None
    objeto_ref: str | None = None
    recurso_ref: str | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    cantidad: Decimal | None = None
    cantidad_crudo: str | None = None
    unidad: str | None = None
    tarifa: Decimal | None = None
    tarifa_crudo: str | None = None
    importe: Decimal
    importe_crudo: str
    tipo_iva: Decimal | None = None
    cuota_iva: Decimal | None = None
    po_ref: str | None = None


class IvaVentaCanonico(BaseModel):
    """El IVA de una factura de venta para un tipo: su base y su cuota (la suma de sus lineas)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tipo_iva: Decimal
    base: Decimal
    cuota: Decimal | None = None


class FacturaVentaCanonica(Canonico):
    """Una factura de venta entera, como la da su sistema (spec §9).

    Los totales son los de la cabecera si el fichero los trae; si no, la suma
    de las lineas. `referencias` son las PO (de la cabecera y de las lineas).
    """

    id_externo: str
    numero: str
    tipo: Literal["factura", "nota_credito"]
    cliente_ref: str
    cliente_nombre: str | None = None
    cliente_btw: str | None = None
    contacto: str | None = None
    fecha_factura: date
    fecha_vencimiento: date | None = None
    condiciones_pago: str | None = None
    periodo_inicio: date | None = None
    periodo_fin: date | None = None
    tratamiento_iva: Regimen | None = None
    base: Decimal
    base_crudo: str | None = None
    iva: Decimal | None = None
    iva_crudo: str | None = None
    total: Decimal | None = None
    total_crudo: str | None = None
    iva_por_tipo: tuple[IvaVentaCanonico, ...] = ()
    referencias: tuple[str, ...] = ()
    factura_relacionada: str | None = None
    moneda: str | None = None
    lineas: tuple[LineaVentaCanonica, ...] = ()


# ------------------------------------------------------------ ordenes de compra (paso 9)

def _lista_de_texto(valor: object) -> object:
    """Una lista de codigos: la de un YAML tal cual, o la celda de un CSV separada por comas."""
    if isinstance(valor, str):
        return tuple(p.strip() for p in valor.split(",") if p.strip())
    return valor


class OrdenCompraCanonica(Canonico):
    """Una PO tal como la teclea una persona en la hoja de POs (spec §9: po_csv).

    `lado` dice de quien es: la que un cliente da a BM Support BV (cliente) o
    la que BM Support BV da a un proveedor (proveedor). `parte_ref` es la parte
    como la nombra la hoja (numero de Exact, btw-id, KvK o alias confirmado) y
    `objetos_ref`, los Objetos que cubre (ninguno: cualquiera de la parte). El
    valor es sin IVA; lo que no esta en euros no entra (X1).
    """

    numero: str
    lado: Literal["cliente", "proveedor"]
    parte_ref: str
    objetos_ref: tuple[str, ...] = ()
    fecha_emision: date | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    valor: Decimal
    valor_crudo: str | None = None
    moneda: str | None = None
    cerrada: bool = False

    @field_validator("objetos_ref", mode="before")
    @classmethod
    def _objetos(cls, valor: object) -> object:
        return _lista_de_texto(valor)

    @field_validator("valor")
    @classmethod
    def _positivo(cls, valor: Decimal) -> Decimal:
        if valor <= 0:
            raise ValueError("el valor de una PO es mayor que cero")
        return valor


class ModificacionPOCanonica(Canonico):
    """Una modificacion de una PO, en su propia fila: un valor nuevo, un fin nuevo o los dos,
    desde `fecha`, con su motivo. La PO se nombra como en la hoja de POs."""

    numero: str
    lado: Literal["cliente", "proveedor"]
    parte_ref: str
    fecha: date
    valor_nuevo: Decimal | None = None
    valor_nuevo_crudo: str | None = None
    fecha_fin_nueva: date | None = None
    motivo: str
    moneda: str | None = None

    @field_validator("valor_nuevo")
    @classmethod
    def _positivo(cls, valor: Decimal | None) -> Decimal | None:
        if valor is not None and valor <= 0:
            raise ValueError("el valor nuevo de una PO es mayor que cero")
        return valor

    @model_validator(mode="after")
    def _algo_cambia(self) -> "ModificacionPOCanonica":
        if self.valor_nuevo is None and self.fecha_fin_nueva is None:
            raise ValueError("una modificacion cambia el valor, el fin o los dos")
        if not self.motivo.strip():
            raise ValueError("una modificacion lleva su motivo")
        return self


# ------------------------------------------------------------ el planning (paso 10)

_HORA = re.compile(r"([01]?[0-9]|2[0-3])[:.]([0-5][0-9])")
# Las 24:00 solo como fin: el turno que acaba a medianoche (16:00 a 24:00).
_FIN_DEL_DIA = re.compile(r"24[:.]00")
DIAS_SEMANA = ("horas_lunes", "horas_martes", "horas_miercoles", "horas_jueves",
               "horas_viernes", "horas_sabado", "horas_domingo")
_HORAS = ("horas_planificadas", "horas_realizadas", "horas_aprobadas")
_HORAS_DEL_ESTADO = {"validado": "horas_aprobadas", "realizado": "horas_realizadas"}


class TurnoCanonico(Canonico):
    """Un turno del planning (TRNSPRNT) tal como lo da el fichero (spec §9).

    Un turno de un dia lleva `fecha`, y si no trae las horas planificadas pero
    si el inicio, el fin y la pausa, las planificadas son fin - inicio - pausa
    (un turno de noche que acaba al dia siguiente suma 24 horas al fin). Una
    fila de la exportacion semanal pivotada lleva `ano` y `semana` y las horas de
    cada dia (`horas_lunes`...): se lee a nivel de semana, sin partirla en
    dias, con su total en `horas_total`, que va a las horas de su estado (las
    validadas de una fila validada, las realizadas de una realizada, las
    planificadas de las demas); el total tiene que ser la suma de los dias.
    `estado` validado es el turno cuyas horas dio por buenas el planning, y
    tiene que traer esas horas; un turno que no esta validado no trae horas
    validadas (el fichero se contradice, y no se adivina cual de los dos
    manda).

    Un fin a las 24:00 es medianoche; un turno que empieza y acaba a la misma
    hora dura 24 horas (una guardia de un dia entero), no cero.

    `id_externo` es el identificador estable del turno en TRNSPRNT. Si el
    fichero no lo trae, planning.py le pone una clave sintetica y la marca
    `clave_fragil`. Los `*_ref` son como el fichero nombra a cada cosa; los
    resuelve registrar.py por coincidencia exacta, y nada se crea solo.
    """

    id_externo: str | None = None
    clave_fragil: bool = False
    fecha: date | None = None
    ano: int | None = None
    semana: int | None = None
    hora_inicio: str | None = None
    hora_fin: str | None = None
    pausa_min: int | None = None
    horas_planificadas: Decimal | None = None
    horas_realizadas: Decimal | None = None
    horas_aprobadas: Decimal | None = None
    horas_total: Decimal | None = None
    horas_lunes: Decimal | None = None
    horas_martes: Decimal | None = None
    horas_miercoles: Decimal | None = None
    horas_jueves: Decimal | None = None
    horas_viernes: Decimal | None = None
    horas_sabado: Decimal | None = None
    horas_domingo: Decimal | None = None
    estado: Literal["planificado", "realizado", "validado", "cancelado"]
    objeto_ref: str | None = None
    objeto_nombre: str | None = None
    recurso_ref: str | None = None
    proveedor_ref: str | None = None
    cliente_ref: str | None = None
    po_ref: str | None = None
    tipo_servicio: str | None = None
    tipo_turno: str | None = None
    facturable: bool | None = None
    tarifa_compra: Decimal | None = None
    tarifa_venta: Decimal | None = None
    moneda: str | None = None

    @field_validator("hora_inicio", "hora_fin")
    @classmethod
    def _hora(cls, valor: str | None, info: ValidationInfo) -> str | None:
        if valor is None:
            return None
        if info.field_name == "hora_fin" and _FIN_DEL_DIA.fullmatch(valor.strip()):
            return "24:00"
        hora = _HORA.fullmatch(valor.strip())
        if hora is None:
            raise ValueError(f"{valor!r} no es una hora (HH:MM)")
        return f"{int(hora.group(1)):02d}:{hora.group(2)}"

    @field_validator("pausa_min")
    @classmethod
    def _pausa(cls, valor: int | None) -> int | None:
        if valor is not None and valor < 0:
            raise ValueError("una pausa no es negativa")
        return valor

    @model_validator(mode="after")
    def _coherente(self) -> "TurnoCanonico":
        if (self.fecha is None) == (self.ano is None or self.semana is None):
            raise ValueError("un turno lleva su fecha (un dia) o su ano y su semana (la "
                             "exportacion semanal), una de las dos")
        if self.horas_total is not None:
            destino = _HORAS_DEL_ESTADO.get(self.estado, "horas_planificadas")
            if getattr(self, destino) is not None and getattr(self, destino) != self.horas_total:
                raise ValueError(f"el total ({self.horas_total}) no es {destino} "
                                 f"({getattr(self, destino)})")
            object.__setattr__(self, destino, self.horas_total)
        if self.estado != "validado" and self.horas_aprobadas is not None:
            raise ValueError(f"un turno {self.estado} trae horas validadas "
                             f"({self.horas_aprobadas}): o no esta validado o no lo estan sus "
                             "horas")
        for nombre in (*_HORAS, "horas_total", *DIAS_SEMANA, "tarifa_compra", "tarifa_venta"):
            valor = getattr(self, nombre)
            if valor is not None and valor < 0:
                raise ValueError(f"{nombre} no puede ser negativo")
        if self.fecha is None:
            try:
                date.fromisocalendar(self.ano, self.semana, 1)
            except ValueError:
                raise ValueError(f"el ano {self.ano} no tiene semana {self.semana}") from None
            dias = [getattr(self, d) for d in DIAS_SEMANA]
            totales = [getattr(self, h) for h in _HORAS if getattr(self, h) is not None]
            if not totales:
                raise ValueError("una fila semanal lleva su total de horas")
            if any(d is not None for d in dias):
                suma = sum((d for d in dias if d is not None), Decimal(0))
                if any(t != suma for t in totales):
                    raise ValueError(f"el total de la semana ({', '.join(map(str, totales))}) "
                                     f"no es la suma de sus dias ({suma})")
        elif (self.horas_planificadas is None and self.hora_inicio is not None
              and self.hora_fin is not None):
            object.__setattr__(self, "horas_planificadas", self._duracion())
        if self.estado == "validado" and self.horas_aprobadas is None:
            raise ValueError("un turno validado trae sus horas validadas")
        return self

    def _duracion(self) -> Decimal:
        """fin - inicio - pausa, en horas; un fin anterior al inicio es del dia siguiente, y
        uno igual al inicio, 24 horas despues.

        Es un valor derivado, no impreso: un turno de 07:10 a 15:30 son 8,333...
        horas, y se guarda a la milesima de hora (3,6 segundos), redondeado a
        proposito y no por el conversor, que nunca redondea lo que lee.
        """
        inicio = int(self.hora_inicio[:2]) * 60 + int(self.hora_inicio[3:])
        fin = int(self.hora_fin[:2]) * 60 + int(self.hora_fin[3:])
        minutos = ((fin - inicio) % (24 * 60) or 24 * 60) - (self.pausa_min or 0)
        if minutos < 0:
            raise ValueError("la pausa es mas larga que el turno")
        return (Decimal(minutos) / Decimal(60)).quantize(Decimal("0.001"), ROUND_HALF_UP)

    @property
    def nivel(self) -> str:
        return "dia" if self.fecha is not None else "semana"

    @property
    def dia(self) -> date:
        """El dia del turno o, en una fila semanal, el lunes de su semana."""
        return self.fecha if self.fecha is not None else date.fromisocalendar(
            self.ano, self.semana, 1)

    @property
    def dias(self) -> int:
        """Los dias con horas: uno en un turno; en una fila semanal, los que traen horas (si no
        trae el detalle por dia, los siete)."""
        if self.fecha is not None:
            return 1
        detalle = [getattr(self, d) for d in DIAS_SEMANA]
        if all(d is None for d in detalle):
            return 7
        return sum(1 for d in detalle if d)


MODELOS: dict[str, type[Canonico]] = {
    "proveedores": ProveedorCanonico, "clientes": ClienteCanonico,
    "contactos": ContactoCanonico, "cuentas": CuentaBancariaCanonica, "objetos": ObjetoCanonico,
    "recursos": RecursoCanonico, "alias": AliasCanonico, "tarifas": TarifaCanonica,
    "ciclos": CicloCanonico, "movimientos": MovimientoCanonico,
    "pagos_exact": PagoExactCanonico,
    "lineas_venta": FilaVentaCanonica, "facturas_venta": FacturaVentaCanonica,
    "ordenes_compra": OrdenCompraCanonica, "modificaciones_po": ModificacionPOCanonica,
    "planning": TurnoCanonico,
}
