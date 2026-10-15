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
    """Lo que queda de una factura (spec §5). Solo las relaciones confirmadas lo mueven.

    anulada: anulada a mano, anulada por un abono que la anula, o sustituida o
    corregida por otra (sale de los totales). acreditada: los abonos
    confirmados cubren lo que quedaba sin que se pagara nada (paso 8); un
    abono parcial solo baja lo pendiente.
    """

    PENDIENTE = "pendiente"
    VENCIDA = "vencida"
    PAGADA = "pagada"
    ANULADA = "anulada"
    ACREDITADA = "acreditada"


class EstadoRevision(_Texto):
    SIN_REVISAR = "sin_revisar"
    NECESITA_REVISION = "necesita_revision"
    REVISADA = "revisada"


class EstadoExcepcion(_Texto):
    ABIERTA = "abierta"
    ASIGNADA = "asignada"
    ESPERANDO_EXTERNO = "esperando_externo"
    RESUELTA = "resuelta"


ESTADOS_EXCEPCION_ABIERTA = frozenset({EstadoExcepcion.ABIERTA.value,
                                       EstadoExcepcion.ASIGNADA.value,
                                       EstadoExcepcion.ESPERANDO_EXTERNO.value})


class EsperandoA(_Texto):
    """A quien se espera cuando una excepcion esta esperando a alguien de fuera."""

    PROVEEDOR = "proveedor"
    CLIENTE = "cliente"
    CONTABLE = "contable"
    EXACT = "exact"
    TRNSPRNT = "trnsprnt"
    BANCO = "banco"
    OTRO = "otro"


class ResolucionExcepcion(_Texto):
    """Como acabo una excepcion. Ninguna es "aprobada": resolver no aprueba un pago."""

    CORREGIDO = "corregido"
    ACEPTADO = "aceptado"
    ANULADO = "anulado"
    NO_PROCEDE = "no_procede"
    CONDICION_DESAPARECIDA = "condicion_desaparecida"


class ResultadoRevision(_Texto):
    """Lo que deja una persona al revisar una factura. No hay "aprobada"."""

    REVISADA = "revisada"
    DEVUELTA = "devuelta"


class Prioridad(_Texto):
    NORMAL = "normal"
    ATENCION = "atencion"
    URGENTE = "urgente"
    BLOQUEADA = "bloqueada"


class EntidadPrioridad(_Texto):
    """Lo que tiene prioridad propia ademas de una factura (cache prioridad)."""

    EXCEPCION = "excepcion"
    PROVEEDOR = "proveedor"
    CLIENTE = "cliente"
    OBJETO = "objeto"
    ORDEN_COMPRA = "orden_compra"
    TRIMESTRE = "trimestre"


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


# Lo que mueve cada tipo de relacion confirmada (paso 8). Un abono que acredita
# o anula baja lo pendiente de la original y gasta lo suyo; las dos siguen en
# los totales y en el IVA, cada una en su fecha, y se compensan. Una factura
# sustituida o corregida por otra sale de los totales, de la caja y del IVA.
# Una relacionada no mueve nada (y tampoco calla un duplicado).
RELACIONES_QUE_ACREDITAN = frozenset({TipoRelacion.ACREDITA.value, TipoRelacion.ANULA.value})
RELACIONES_QUE_SUSTITUYEN = frozenset({TipoRelacion.SUSTITUYE.value,
                                       TipoRelacion.CORRIGE.value})


class RelacionCitada(_Texto):
    """Lo que dice un documento de la factura que nombra (stated_relation de v2, o Exact)."""

    ACREDITA = "credits"
    CORRIGE = "corrects"
    SUSTITUYE = "replaces"
    ANULA = "cancels"
    SE_REFIERE = "refers_to"
    DESCONOCIDA = "unknown"


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


class EstadoHallazgo(_Texto):
    """Donde esta un hallazgo. Abierto, aceptado y desaparecido siguen pidiendo a alguien.

    desaparecido es el de una regla pegajosa cuya condicion ya no se da: no
    se cierra solo, lo cierra una persona (resuelto). cerrado es el de una
    regla normal que se cerro sola, con la edicion o la importacion que lo
    causo apuntada en su evento.
    """

    ABIERTO = "abierto"
    ACEPTADO = "aceptado"           # anulado por una persona, mientras la huella sea la anulada
    DESAPARECIDO = "desaparecido"   # condicion desaparecida en una regla pegajosa
    CERRADO = "cerrado"             # cerrado por el sistema (regla no pegajosa)
    RESUELTO = "resuelto"           # cerrado por una persona


ESTADOS_PENDIENTES = frozenset({EstadoHallazgo.ABIERTO.value, EstadoHallazgo.ACEPTADO.value,
                                EstadoHallazgo.DESAPARECIDO.value})


class TipoEventoHallazgo(_Texto):
    """La historia de un hallazgo (hallazgo_evento), en el orden en que puede pasar."""

    DETECTADO = "detectado"
    CAMBIO_EVIDENCIA = "cambio_evidencia"
    DESAPARECIDO = "desaparecido"
    CERRADO_AUTOMATICO = "cerrado_automatico"
    RESUELTO = "resuelto"
    ACEPTADO = "aceptado"
    REABIERTO = "reabierto"


class MotivoEjecucion(_Texto):
    """Por que corrio el motor de reglas (ejecucion_reglas.motivo)."""

    INGESTA = "ingesta"
    IMPORTACION = "importacion"
    EDICION = "edicion"
    DIARIA = "diaria"
    MANUAL = "manual"


class PapelObjetivo(_Texto):
    PRINCIPAL = "principal"
    RELACIONADO = "relacionado"


class AmbitoHallazgo(_Texto):
    """De que entidad es un hallazgo; una excepcion (paso 4) agrupa por ella."""

    FACTURA = "factura"
    PROVEEDOR = "proveedor"
    CLIENTE = "cliente"
    ORDEN_COMPRA = "orden_compra"
    TRIMESTRE = "trimestre"
    MOVIMIENTO = "movimiento"
    IMPORTACION = "importacion"


class EntradaPrioridad(_Texto):
    """Lo que aporta un hallazgo al calculo de prioridad (spec §7, ultima columna; §8)."""

    OTRA = "otra"
    DUPLICADO_EXACTO = "duplicado_exacto"
    DUPLICADO = "duplicado"
    IBAN = "iban"
    IVA_DURA = "iva_dura"
    IVA_BLANDA = "iva_blanda"
    PLANNING = "planning"
    FACTURACION_AUSENTE = "facturacion_ausente"
    TRABAJO_SIN_FACTURAR = "trabajo_sin_facturar"
    LIMITE_PO = "limite_po"
    LIMITE_PO_DURO = "limite_po_duro"
    CADUCIDAD_PO = "caducidad_po"
    DIAS_VENCIDA = "dias_vencida"


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


class TitularCuenta(_Texto):
    """De quien es una cuenta bancaria del registro."""

    PROVEEDOR = "proveedor"
    CLIENTE = "cliente"
    PROPIA = "propia"


class PrimeraFuenteCuenta(_Texto):
    """Como entro una cuenta en el registro (spec §5.C, decision 3)."""

    BASELINE = "baseline"                         # el primer maestro: la referencia de partida
    MAESTRO_EXACT = "maestro_exact"               # un maestro de Exact posterior
    MAESTRO_TRNSPRNT = "maestro_trnsprnt"
    VERIFICACION_MANUAL = "verificacion_manual"   # tecleada por quien llamo al proveedor


class TipoEventoCuenta(_Texto):
    """Lo que le pasa a una cuenta. Las cuatro ultimas son de una persona con confirmar_iban."""

    BASELINE = "baseline"
    VISTO_EN_EXACT = "visto_en_exact"
    AUSENTE_EN_EXACT = "ausente_en_exact"
    VISTO_EN_TRNSPRNT = "visto_en_trnsprnt"
    AUSENTE_EN_TRNSPRNT = "ausente_en_trnsprnt"
    VISTO_EN_DOCUMENTO = "visto_en_documento"     # en la lista, pero la base no la admite
    VERIFICADA = "verificada"
    RECHAZADA = "rechazada"
    ATESTADA = "atestada"
    RETIRADA = "retirada"


DECISIONES_CUENTA = frozenset({TipoEventoCuenta.VERIFICADA.value, TipoEventoCuenta.RECHAZADA.value,
                               TipoEventoCuenta.ATESTADA.value, TipoEventoCuenta.RETIRADA.value})


class MetodoVerificacion(_Texto):
    LLAMADA = "llamada"
    VIDEOLLAMADA = "videollamada"
    VISITA = "visita"


class DecisionFacturas(_Texto):
    """Que se hace con las facturas que traian la cuenta que se rechaza."""

    PAGAR_A_VERIFICADA = "pagar_a_verificada"
    ANULAR = "anular"


class FrecuenciaCiclo(_Texto):
    SEMANAL = "semanal"
    CUATRISEMANAL = "cuatrisemanal"
    MENSUAL = "mensual"


class FuenteImportacion(_Texto):
    """De donde viene un fichero que se importa (spec §9, Lector.fuente)."""

    EXTRACCIONES = "extracciones"
    EXACT = "exact"
    TRNSPRNT = "trnsprnt"
    BANCO = "banco"
    MAESTRO_CSV = "maestro_csv"     # una hoja de maestros rellenada a mano
    PO_CSV = "po_csv"


class TipoImportacion(_Texto):
    """Que trae un lote (spec §9). alias es una hoja de nombres para lo que ya existe."""

    PROVEEDORES = "proveedores"
    CLIENTES = "clientes"
    CONTACTOS = "contactos"
    OBJETOS = "objetos"
    RECURSOS = "recursos"
    ALIAS = "alias"
    CUENTAS = "cuentas"
    TARIFAS = "tarifas"
    ORDENES_COMPRA = "ordenes_compra"
    CICLOS = "ciclos"
    FACTURAS_VENTA = "facturas_venta"
    FACTURAS_COMPRA = "facturas_compra"
    PAGOS_EXACT = "pagos_exact"
    EXTRACTO = "extracto"
    PLANNING = "planning"


class FuenteAplicacion(_Texto):
    """De donde sale que una factura se pago (spec §5.E). Manda el banco, luego Exact, luego
    lo manual."""

    BANCO = "banco"
    EXACT = "exact"
    MANUAL = "manual"


class MetodoAplicacion(_Texto):
    """Como se encontro el pago: casado del todo por el sistema, propuesto, o puesto a mano."""

    AUTOMATICA = "automatica"
    PROPUESTA = "propuesta"
    MANUAL = "manual"


class EstadoAplicacion(_Texto):
    """Solo lo confirmado cuenta para el saldo. No hay ningun estado de "aprobado para pagar"."""

    PROPUESTA = "propuesta"
    CONFIRMADA = "confirmada"
    RETIRADA = "retirada"


# Que fuente manda en el saldo de una factura, de mas a menos (decision 5 y §9).
PRECEDENCIA_PAGO = (FuenteAplicacion.BANCO.value, FuenteAplicacion.EXACT.value,
                    FuenteAplicacion.MANUAL.value)
