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

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from ..reglas.bancaria import validar_iban
from ..reglas.normas import normalizar_iban

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


MODELOS: dict[str, type[Canonico]] = {
    "proveedores": ProveedorCanonico, "clientes": ClienteCanonico,
    "contactos": ContactoCanonico, "cuentas": CuentaBancariaCanonica, "objetos": ObjetoCanonico,
    "recursos": RecursoCanonico, "alias": AliasCanonico, "tarifas": TarifaCanonica,
    "ciclos": CicloCanonico,
}
