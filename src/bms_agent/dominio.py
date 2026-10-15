"""Los valores que puede tomar cada estado del dominio, en un solo sitio.

Cada enumeracion de aqui es la misma lista que el CHECK de su columna en
las migraciones (un test lo comprueba): si el codigo y la base no dicen lo
mismo, una orden fallaria a medias contra la base en vez de no empezar.

Los valores son texto en castellano sin acentos porque son lo que se guarda
en la base y lo que viaja en el contrato JSON.
"""

from __future__ import annotations

from enum import Enum


class _Texto(str, Enum):
    """Un enum cuyo valor es el texto que se guarda."""

    def __str__(self) -> str:
        return self.value

    @classmethod
    def valores(cls) -> tuple[str, ...]:
        return tuple(m.value for m in cls)


class Sentido(_Texto):
    """Direccion de una factura. La decide la via de entrada, nunca el modelo."""

    ENTRANTE = "entrante"     # compra: un proveedor factura a BMS
    SALIENTE = "saliente"     # venta: BMS factura a un cliente


class Fuente(_Texto):
    """De donde sale el valor actual de un campo (las siete del §13)."""

    EXTRACCION = "extraccion"
    IMPORTACION = "importacion"
    PLANNING = "planning"
    MAESTRO = "maestro"
    MANUAL_ENTRADA = "manual_entrada"          # una persona rellena lo que faltaba
    MANUAL_CORRECCION = "manual_correccion"    # una persona cambia lo que habia
    CALCULADO = "calculado"


FUENTES_MANUALES = frozenset({Fuente.MANUAL_ENTRADA.value, Fuente.MANUAL_CORRECCION.value})
FUENTES_AUTOMATICAS = frozenset(Fuente.valores()) - FUENTES_MANUALES


class Calidad(_Texto):
    """Calidad de un dato, en orden de gravedad. Ninguna es "verde" por defecto."""

    FALTANTE = "faltante"
    DISCREPANCIA = "discrepancia"
    ANOMALIA = "anomalia"
    DUDOSO = "dudoso"
    VERIFICADO = "verificado"


class TipoFactura(_Texto):
    FACTURA = "factura"
    NOTA_CREDITO = "nota_credito"


class OrigenFactura(_Texto):
    EXTRACCION = "extraccion"
    EXACT = "exact"
    TRNSPRNT = "trnsprnt"
    MANUAL = "manual"


class TratamientoIva(_Texto):
    """Como trata el IVA una factura, un proveedor o un cliente."""

    ESTANDAR = "estandar"                  # IVA repercutido
    AUTOLIQUIDACION = "autoliquidacion"    # btw verlegd
    KOR = "kor"                            # kleineondernemersregeling
    EXENTO = "exento"
    TIPO_CERO = "tipo_cero"
    DESCONOCIDO = "desconocido"


class EstadoPago(_Texto):
    PENDIENTE = "pendiente"
    VENCIDA = "vencida"
    PAGADA = "pagada"
    ANULADA = "anulada"         # anulada o acreditada entera


class EstadoRevision(_Texto):
    SIN_REVISAR = "sin_revisar"
    NECESITA_REVISION = "necesita_revision"
    REVISADA = "revisada"


class EstadoExcepcion(_Texto):
    ABIERTA = "abierta"
    ASIGNADA = "asignada"
    ESPERANDO_EXTERNO = "esperando_externo"
    RESUELTA = "resuelta"


class Prioridad(_Texto):
    NORMAL = "normal"
    ATENCION = "atencion"
    URGENTE = "urgente"
    BLOQUEADA = "bloqueada"


class Severidad(_Texto):
    """Lo que hace un fallo: parar, retener o avisar (validacion-facturas.md §2)."""

    BLOQUEO = "bloqueo"
    RETENCION = "retencion"
    AVISO = "aviso"


class TipoRelacion(_Texto):
    ACREDITA = "acredita"
    ANULA = "anula"
    CORRIGE = "corrige"
    SUSTITUYE = "sustituye"
    RELACIONADA = "relacionada"


class EstadoRelacion(_Texto):
    """Solo una relacion confirmada mueve saldos, IVA o B4."""

    PROPUESTA = "propuesta"
    CONFIRMADA = "confirmada"
    RECHAZADA = "rechazada"


class FuenteRelacion(_Texto):
    EXTRACCION = "extraccion"
    EXACT = "exact"
    MANUAL = "manual"


class ClaseReferencia(_Texto):
    """Que es una referencia impresa. Lo decide el codigo, no el modelo."""

    PO = "po"
    ORDEN = "orden"
    PROYECTO = "proyecto"
    REF_CLIENTE = "ref_cliente"
    OTRA = "otra"


class EstadoBtw(_Texto):
    ABIERTO = "abierto"
    LISTO_REVISION = "listo_revision"
    PRESENTADO = "presentado"


class ResultadoRegla(_Texto):
    """sin_datos nunca cuenta como ok."""

    OK = "ok"
    FALLO = "fallo"
    SIN_DATOS = "sin_datos"
    NO_APLICA = "no_aplica"


class Permiso(_Texto):
    """Los once permisos del §19 y los tres propuestos (revisar, BTW, importar)."""

    VER_FACTURAS = "ver_facturas"
    EDITAR_EXTRACCION = "editar_extraccion"
    ANADIR_INFORMACION = "anadir_informacion"
    CAMBIAR_OBJETO = "cambiar_objeto"
    CAMBIAR_PO = "cambiar_po"
    MARCAR_PAGADA = "marcar_pagada"
    ANULAR_ACREDITAR = "anular_acreditar"
    RESOLVER_AVISO = "resolver_aviso"
    ANULAR_AVISO = "anular_aviso"
    CONFIRMAR_IBAN = "confirmar_iban"
    ADMIN = "admin"
    REVISAR_FACTURA = "revisar_factura"
    GESTIONAR_BTW = "gestionar_btw"
    IMPORTAR_DATOS = "importar_datos"


class SentidoTarifa(_Texto):
    """Una tarifa pactada es de compra (a un proveedor) o de venta (a un cliente)."""

    COMPRA = "compra"
    VENTA = "venta"


class OrigenAlias(_Texto):
    MAESTRO = "maestro"
    MANUAL = "manual"
    CONFIG = "config"


class FuenteTarifa(_Texto):
    CONFIG = "config"
    MAESTRO = "maestro"
    EXACT = "exact"
    TRNSPRNT = "trnsprnt"
    MANUAL = "manual"
    DOCUMENTO = "documento"


class TipoProveedor(_Texto):
    ZZP = "zzp"
    EMPRESA = "empresa"


class TipoRecurso(_Texto):
    EMPLEADO = "empleado"
    ZZP = "zzp"
    PERSONAL_PROVEEDOR = "personal_proveedor"
