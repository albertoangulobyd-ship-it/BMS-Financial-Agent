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
    # Paso 5. La cuenta pagable (decision 3): con solo_verificadas, lo
    # heredado del primer maestro no se paga hasta que alguien lo atesta o lo
    # verifica (lo estricto de D2, como interruptor).
    iban_solo_verificadas: bool = False
    # Tras un cambio del telefono de verificacion, cuantos dias no vale
    # ninguna verificacion por telefono de ese proveedor (decision 4).
    enfriamiento_telefono_dias: int = 14
    # Frescura de cada fuente (decision 7): pasado el limite, Z1 y las reglas
    # que dependen de ella dan sin_datos en vez de ok.
    frescura_exact_dias: int = 7
    frescura_trnsprnt_dias: int = 7
    frescura_banco_dias_laborables: int = 3
    # La identidad de BM Support BV (config/empresa.yaml), ya normalizada:
    # A8 compara con ella a quien va dirigida una factura.
    empresa_nombres: tuple[str, ...] = ("bm support bv",)
    empresa_btw: str | None = None
    empresa_kvk: str | None = None
    # Paso 7. Las cuentas de la empresa (config/empresa.yaml): un traspaso
    # entre ellas no es un pago de nadie (K7, F7).
    empresa_ibans: tuple[str, ...] = ()
    # Una factura esta pagada cuando lo confirmado deja su saldo dentro de
    # esto (decision 5; por defecto, al centimo).
    tolerancia_pago: Decimal = Decimal("0.00")
    # K1: una venta es "vencida" pasados estos dias de su vencimiento.
    dias_vencida_venta: int = 14
    # K3: dias sin rastro en el banco de un pago marcado a mano.
    dias_pago_sin_extracto: int = 7
    # K7: dias que un movimiento puede estar sin casar con ninguna factura.
    dias_movimiento_sin_casar: int = 7
    # K4: dos cargos iguales a la misma contraparte con la misma referencia en
    # menos de estos dias son un pago doble.
    ventana_doble_pago_dias: int = 30
    # Paso 9: las ordenes de compra. P5 avisa con este porcentaje consumido; P7
    # cuando caduca dentro de estos dias con valor por consumir; P9 si, al ritmo
    # de estas semanas, se agota antes de estos dias de su fin.
    po_aviso_consumo_pct: int = 80
    po_dias_caducidad: int = 30
    po_margen_prevision_dias: int = 14
    po_semanas_ritmo: int = 8
    # G3: una tarifa de compra por encima de la pactada retiene; por encima de
    # este porcentaje sobre la pactada, bloquea (y anularla pide segunda firma).
    tarifa_exceso_bloqueo_pct: int = 10
    # Paso 10: el planning. Con el planning obligatorio, una compra sin ningun
    # turno de su proveedor en lo facturado bloquea (G1); si no, retiene. Las
    # horas facturadas y las del planning se admiten distintas en esto por cada
    # dia comparado (G2, V1, G6). Sin ciclo de facturacion, el trabajo sin
    # facturar de un mes se busca pasados estos dias de su fin (V6).
    planning_obligatorio: bool = False
    planning_tolerancia_horas_dia: Decimal = Decimal("0.25")
    planning_dias_gracia: int = 14
    # Paso 11: el BTW (config/btw.yaml, por confirmar con el asesor). E7: los
    # tipos de IVA que no son raros, en puntos basicos. E5: el umbral anual de
    # la KOR y desde que porcentaje de el se avisa.
    iva_tipos_habituales_pb: tuple[int, ...] = (0, 900, 2100)
    kor_umbral_cent: int = 2_000_000
    kor_aviso_pct: int = 90

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
    # Paso 10: el numero de semana impreso, sin ano (el ano lo pone la fecha de la
    # factura al cruzar con el planning: reglas/turnos.semana_impresa).
    semana_doc: int | None = None


@dataclass(frozen=True, slots=True)
class LineaSinCasar:
    """Una linea editada por una persona que la extraccion vigente no trae (paso 6, M2).

    `activa` dice si la linea sigue contando (nadie la ha excluido despues);
    `excluida`, si ya estaba excluida cuando llego la lectura nueva (la
    exclusion no se pudo llevar a ninguna linea nueva). `campos` son los
    "tabla.campo" que una persona habia cambiado.
    """

    linea_id: int
    orden: int
    activa: bool
    excluida: bool
    campos: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Imputacion:
    """Una imputacion activa de una linea (factura_imputacion), paso 9.

    A que Objeto, recurso y PO va, por cuanto sin IVA y de que dias, con el
    tipo de trabajo y el turno de su linea. De aqui sale lo consumido de una PO
    y con que tarifa pactada se compara la linea (G3, G6, V4).
    """

    id: int
    linea_id: int | None
    objeto_id: int | None
    recurso_id: int | None
    orden_compra_id: int | None
    importe_cent: int | None
    horas_mil: int | None
    fecha_inicio: date | None
    fecha_fin: date | None
    tipo_servicio: str | None
    tipo_turno: str | None


@dataclass(frozen=True, slots=True)
class Referencia:
    """Una referencia impresa viva (factura_referencia), paso 9: su valor normalizado, su
    clase y la PO con la que el sistema la caso (None si no casa con ninguna de la parte)."""

    id: int
    linea_id: int | None
    valor_doc: str
    valor_norm: str | None
    clase: str
    orden_compra_id: int | None


@dataclass(frozen=True, slots=True)
class TramoIva:
    """Una fila del desglose de IVA por tipo (v2, Exact). Una factura v1 no tiene.

    `tratamiento` es el de la fila, si lo dice (Exact lo dice; una lectura v2
    no): sin el, vale el de la factura (paso 11, reglas/iva.lineas_iva).
    """

    id: int
    tipo_iva_pb: int | None
    base_cent: int | None
    cuota_cent: int | None
    tratamiento: str | None = None


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
    # Paso 5: lo que leen las reglas de identidad, de notas y del original.
    # `dudosos` son los campos criticos con una lectura dudosa que nadie ha
    # verificado (Q2); `sin_original`, que se extrajo de un documento cuyo
    # original no se guardo (Q4).
    documento_id: int | None = None
    emisor_direccion_doc: str | None = None
    kor_mencionada: bool | None = None
    notas_doc: str | None = None
    dudosos: frozenset[str] = frozenset()
    sin_original: bool = False
    # Paso 6: las lineas editadas que la extraccion vigente no pudo casar (M2).
    sin_casar: tuple[LineaSinCasar, ...] = ()
    # Paso 7: el vencimiento efectivo (el impreso, o la fecha mas el plazo,
    # del maestro antes que del papel) y lo que se ha pagado de ella segun la
    # fuente que manda (banco, Exact, a mano). `pagada` si lo confirmado deja
    # su saldo dentro de la tolerancia (reglas.pagos.saldo).
    vencimiento: date | None = None
    pagado_cent: int = 0
    fuente_pago: str | None = None
    pagada: bool = False
    # Paso 8: de donde viene (extraccion, exact, trnsprnt), lo que le quitan los
    # abonos confirmados (en su signo; en un abono, lo ya gastado de el) y, si
    # otra factura confirmada la sustituye o la corrige, cual: entonces sale
    # de juego, de los totales, de la caja y del IVA. `pagada` es "saldada":
    # lo pagado y lo acreditado dejan su saldo en la tolerancia.
    origen: str = "extraccion"
    acreditado_cent: int = 0
    sustituida_por: int | None = None
    # Paso 9: sus imputaciones activas y sus referencias impresas vivas.
    imputaciones: tuple[Imputacion, ...] = ()
    referencias: tuple[Referencia, ...] = ()


@dataclass(frozen=True, slots=True)
class Relacion:
    """Una relacion entre dos facturas: el origen (el abono, la que corrige o sustituye) y su
    destino (la original). En `Instantanea.relaciones`, solo las confirmadas: las propuestas no
    mueven nada y van aparte (`Instantanea.propuestas`). `importe_cent`, lo que acredita un abono
    en el signo de la original (None: el abono entero)."""

    origen_id: int
    destino_id: int
    tipo: str
    id: int = 0
    importe_cent: int | None = None
    fuente: str = "manual"


@dataclass(frozen=True, slots=True)
class Cita:
    """Una factura que un documento nombra, tal como la nombra (factura_cita, paso 8).

    `numero_norm` es su numero normalizado (None si no se pudo leer);
    `relacion` lo que el documento dice que es (credits, corrects, replaces,
    cancels, refers_to, unknown).
    """

    id: int
    factura_id: int
    numero_doc: str | None
    numero_norm: str | None
    relacion: str | None


@dataclass(frozen=True, slots=True)
class Parte:
    """Un proveedor o un cliente del maestro, con lo que lo identifica ya normalizado.

    `nombres` son su nombre y sus alias confirmados, normalizados: el nombre
    comercial que una persona confirmo cuenta como el suyo (A2).
    """

    id: int
    tabla: str
    nombre: str
    nombres: frozenset[str]
    kvk: str | None
    btw: str | None
    regimen_iva: str | None
    activo: bool
    # Paso 9: si el cliente pide PO en sus facturas (P2). None: no se sabe.
    requiere_po: bool | None = None
    # Paso 11: si al cliente se le puede facturar con el IVA trasladado o al 0 %
    # (E7). None en un proveedor.
    verlegd_elegible: bool | None = None


@dataclass(frozen=True, slots=True)
class Objeto:
    """Un Objeto del maestro (paso 9): de que cliente es y si pide PO (None hereda la del
    cliente, P2)."""

    id: int
    codigo: str
    cliente_id: int | None
    requiere_po: bool | None
    activo_desde: date | None
    activo_hasta: date | None


@dataclass(frozen=True, slots=True)
class OrdenCompra:
    """Una orden de compra con su valor y su fin vigentes (paso 9).

    `lado` cliente: la que un cliente da a BMS, la consumen las ventas a ese
    cliente; proveedor: la que BMS da a un proveedor, la consumen sus compras.
    `parte_id` es ese cliente o ese proveedor. `valor_cent` y `fecha_fin` son
    los de la ultima modificacion que los cambia (ordenes.vigentes); los
    originales se conservan aparte. `objetos`: los que cubre (vacio: todos los
    de su parte).
    """

    id: int
    numero: str
    numero_norm: str
    lado: str
    parte_id: int
    fecha_emision: date | None
    fecha_inicio: date | None
    fecha_fin: date | None
    valor_cent: int
    valor_original_cent: int
    fecha_fin_original: date | None
    cerrada: bool
    objetos: frozenset[int] = frozenset()


@dataclass(frozen=True, slots=True)
class Tarifa:
    """Una tarifa pactada (tarifa_acordada), paso 9. Lo que no esta (None) vale para todo:
    una tarifa sin Objeto es de cualquier Objeto de su parte. `tipo_turno` ya normalizado
    (tarifas.normalizar_turno: el turno de dia es el de siempre, None)."""

    id: int
    sentido: str
    proveedor_id: int | None
    recurso_id: int | None
    cliente_id: int | None
    objeto_id: int | None
    orden_compra_id: int | None
    tipo_servicio: str | None
    tipo_turno: str | None
    unidad: str | None
    tarifa_e4: int
    vigente_desde: date | None
    vigente_hasta: date | None


@dataclass(frozen=True, slots=True)
class EventoCuenta:
    """Lo que le paso a una cuenta del registro (cuenta_evento).

    `llegada` es cuando llego lo que motivo una decision: el documento con el
    IBAN nuevo o la importacion del maestro que lo cambio; el telefono que vale
    es el del maestro de antes de eso (F8). `con_permiso`, si quien decidio
    tenia confirmar_iban en ese momento. `telefono_usado`, normalizado.
    """

    id: int
    tipo: str
    en: str
    importacion_id: int | None
    documento_id: int | None
    usuario_id: int | None
    con_permiso: bool
    telefono_usado: str | None
    llegada: str | None
    decision_facturas: str | None
    # El dia (en la zona de la empresa) de `en`: F7 mira la cuenta como estaba
    # el dia del cargo. None en las instantaneas de prueba: se toma de `en`.
    dia: date | None = None


@dataclass(frozen=True, slots=True)
class Cuenta:
    """Una cuenta del registro con sus eventos en orden. `parte_id` es su proveedor o cliente.

    `primer_documento`: cuando llego el primer documento de su proveedor que
    imprimia este IBAN (None si ninguno). Si llego antes de que la cuenta se
    aceptara, es lo que motiva verificarla aunque la orden no nombre la
    factura: el telefono que vale es el de antes de ese documento (F8).
    """

    id: int
    titular: str
    parte_id: int
    iban: str
    primera_fuente: str
    eventos: tuple[EventoCuenta, ...]
    primer_documento: str | None = None


@dataclass(frozen=True, slots=True)
class CambioTelefono:
    """Un valor del telefono de verificacion de un proveedor, en orden.

    `alta` si se puso al crear el proveedor (no es un cambio: no abre el
    enfriamiento); `dia`, en la zona de la empresa.
    """

    proveedor_id: int
    cambio_id: int
    valor: str | None
    en: str
    dia: date
    alta: bool


@dataclass(frozen=True, slots=True)
class Lote:
    """Una importacion de un maestro (no las de out/). `rechazos`: (fila, codigo, motivo).

    `exportado` es el dia en que se saco el fichero de su sistema, o el de la
    importacion si no se dijo; `ultimo`, si es la mas reciente de su fuente y
    tipo.
    """

    id: int
    fuente: str
    tipo: str
    estado: str
    exportado: date | None
    filas_rechazadas: int
    rechazos: tuple[tuple[int, str, str], ...]
    ultimo: bool
    # Paso 10: lo que una foto del planning trae y no se encuentra en el maestro
    # (fila, que es, como lo nombra el fichero): entra sin resolver, y es Z2.
    sin_resolver: tuple[tuple[int, str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Extracto:
    """Un extracto de una cuenta propia. `con_saldos` falso en los CSV del banco."""

    id: int
    importacion_id: int
    cuenta: str
    secuencia: int | None
    saldo_inicial_cent: int | None
    saldo_final_cent: int | None
    desde: date | None
    hasta: date | None
    con_saldos: bool


@dataclass(frozen=True, slots=True)
class Movimiento:
    """Un movimiento del banco. `importe_cent` None si no esta en euros (X1); con signo.

    `referencia` es lo que lo identifica como pago de algo, ya normalizado
    (K4): la referencia estructurada, el end-to-end o, si no hay, un numero de
    factura que aparece en el concepto. Nunca el concepto entero: dos recibos
    de un contrato con el mismo texto cada mes no son un pago doble.
    """

    id: int
    extracto_id: int
    cuenta: str
    fecha: date
    importe_cent: int | None
    moneda: str
    contraparte_iban: str | None
    contraparte_nombre: str | None
    referencia: str | None


@dataclass(frozen=True, slots=True)
class Aplicacion:
    """Lo que se pago de una factura: con su movimiento si es del banco. Importe en el signo
    de la factura."""

    id: int
    factura_id: int
    movimiento_id: int | None
    importe_cent: int
    fecha_pago: date
    fuente: str
    metodo: str
    estado: str


@dataclass(frozen=True, slots=True)
class Bloqueo:
    """Unos dias en que una factura estuvo Bloqueada: un hallazgo que bloquea, pendiente y sin
    anular, de `desde` a `hasta` (los dos incluidos; None si sigue). Para K5."""

    factura_id: int
    regla: str
    desde: date
    hasta: date | None


@dataclass(frozen=True, slots=True)
class PagadoExact:
    """Lo que la ultima importacion de pagos de Exact que trae una factura dice pagado de
    ella (tambien cero), y de que dia es esa foto de Exact (K8)."""

    factura_id: int
    pagado_cent: int
    fecha: date


@dataclass(frozen=True, slots=True)
class Turno:
    """Un turno del planning (planning_turno): el que vale hoy (v_turno_vigente) o el de una
    foto anterior con el que se concilio una factura (G7, V9).

    `fecha` es el dia del turno o, en una fila de la exportacion semanal
    (`nivel` semana), el lunes de su semana, y `dias` los dias con horas.
    `tipo_turno` ya normalizado (tarifas.normalizar_turno: el de dia es None).
    Los ids son los que se resolvieron al importar o, si entonces no se
    resolvio, los de ahora (instantanea.py); el proveedor de un turno sin el es
    el de su recurso, y el cliente el de su Objeto.
    """

    id: int
    importacion_id: int
    id_externo: str
    clave_fragil: bool
    nivel: str
    fecha: date
    dias: int
    hora_inicio: str | None
    hora_fin: str | None
    horas_planificadas_mil: int | None
    horas_realizadas_mil: int | None
    horas_aprobadas_mil: int | None
    estado: str
    objeto_id: int | None
    recurso_id: int | None
    proveedor_id: int | None
    cliente_id: int | None
    tipo_servicio: str | None
    tipo_turno: str | None
    facturable: bool | None
    tarifa_compra_e4: int | None = None
    tarifa_venta_e4: int | None = None
    orden_compra_id: int | None = None


@dataclass(frozen=True, slots=True)
class FotoPlanning:
    """Una importacion aceptada del planning: de cuando es y que dias cubre.

    `huecos`: los dias de lo que cubre de los que ya no dice nada, aunque
    ninguna foto mas nueva los cubra: los de las semanas de sus filas
    semanales que una foto mas nueva tapa solo en parte (turnos.tramos).
    """

    importacion_id: int
    exportado: date
    cubre_desde: date | None
    cubre_hasta: date | None
    huecos: tuple[tuple[date, date], ...] = ()


@dataclass(frozen=True, slots=True)
class Conciliacion:
    """Lo que la conciliacion (conciliacion.py) dejo de una imputacion: un turno de su celda,
    tal como era en la foto con la que se concilio, y las horas que se le asignaron."""

    id: int
    imputacion_id: int
    factura_id: int
    turno: Turno
    horas_mil: int
    nivel: str


@dataclass(frozen=True, slots=True)
class Ciclo:
    """Un ciclo de facturacion de un cliente o de un Objeto (V6, V8)."""

    id: int
    cliente_id: int | None
    objeto_id: int | None
    frecuencia: str
    ancla: date | None
    dias_gracia: int
    vigente_desde: date | None
    vigente_hasta: date | None


@dataclass(frozen=True, slots=True)
class PeriodoBtw:
    """Un trimestre del BTW ya presentado (periodo_btw), paso 11, para C4.

    `declaradas` son las facturas que entraron en la declaracion, cada una con
    la huella de su IVA tal como se declaro (reglas/iva.huella_iva). Lo que hoy
    no es eso (una factura que llego despues, una que cambio, una que ya no
    cuenta) es C4.
    """

    ano: int
    trimestre: int
    presentado_en: date
    declaradas: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class Instantanea:
    """Todo lo que una regla puede ver, congelado. Lo construye reglas/instantanea.py.

    Desde el paso 5, tambien los maestros (`proveedores`, `clientes`), el
    registro de cuentas con sus eventos, la historia de los telefonos de
    verificacion y las importaciones de maestros; desde el paso 7, el banco y
    lo pagado.
    """

    hoy: date
    politica: Politica
    facturas: tuple[Factura, ...]
    relaciones: tuple[Relacion, ...] = ()
    proveedores: tuple[Parte, ...] = ()
    clientes: tuple[Parte, ...] = ()
    cuentas: tuple[Cuenta, ...] = ()
    telefonos: tuple[CambioTelefono, ...] = ()
    lotes: tuple[Lote, ...] = ()
    # Paso 7: el banco, lo pagado de cada factura, a quien se paga sin ser
    # proveedor (beneficiario_conocido) y los dias en que cada factura con
    # algun pago estuvo Bloqueada.
    extractos: tuple[Extracto, ...] = ()
    movimientos: tuple[Movimiento, ...] = ()
    aplicaciones: tuple[Aplicacion, ...] = ()
    beneficiarios: frozenset[str] = frozenset()
    bloqueos: tuple[Bloqueo, ...] = ()
    exact_pagado: tuple[PagadoExact, ...] = ()
    # Paso 8: las relaciones propuestas (por la extraccion o por Exact) que
    # esperan a una persona, y las facturas que nombra cada documento.
    propuestas: tuple[Relacion, ...] = ()
    citas: tuple[Cita, ...] = ()
    # Paso 9: las ordenes de compra, las tarifas pactadas y los Objetos del maestro.
    ordenes: tuple[OrdenCompra, ...] = ()
    tarifas: tuple[Tarifa, ...] = ()
    objetos: tuple[Objeto, ...] = ()
    # Paso 10: el planning que vale (los turnos de la foto mas nueva de cada dia),
    # las fotos aceptadas (de cuando son y que cubren), la conciliacion de cada
    # imputacion con sus turnos y los ciclos de facturacion.
    turnos: tuple[Turno, ...] = ()
    fotos_planning: tuple[FotoPlanning, ...] = ()
    conciliaciones: tuple[Conciliacion, ...] = ()
    ciclos: tuple[Ciclo, ...] = ()
    # Paso 11: los trimestres del BTW ya presentados, con lo que se declaro (C4).
    periodos_btw: tuple[PeriodoBtw, ...] = ()


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
    `crea_excepcion`: un aviso suyo abre tambien una excepcion (Q3, K1, U1);
    los que bloquean o retienen la abren siempre (spec §7, Exceptions).
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
    crea_excepcion: bool = False
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
            "segunda_firma": self.segunda_firma, "crea_excepcion": self.crea_excepcion,
            "entrada_prioridad": self.entrada_prioridad,
            "calidad": self.calidad, "ambito": self.ambito, "lee": sorted(self.lee),
            "solo_texto": sorted(self.solo_texto),
        }


# Lo que lee siempre una regla de factura: recorrer las facturas, saber cual
# es cada una y si esta fuera de juego (anulada, fusionada en otra o
# sustituida por otra).
LEE_POR_FACTURA = frozenset({
    "instantanea.facturas", "instantanea.politica",
    "factura.id", "factura.anulada", "factura.fusionada_en_id", "factura.sustituida_por",
})

PorFactura = Callable[[Factura, Politica], Sequence[Resultado]]


def fuera_de_juego(factura: Factura) -> str | None:
    """Por que una factura ya no se evalua, o None si se evalua.

    Una factura anulada, fusionada en otra o sustituida (o corregida) por
    otra con una relacion confirmada ya no se paga ni se cuenta: sus avisos
    de aritmetica o de moneda no piden nada a nadie. Una regla de grupo
    tampoco la empareja con otras. Lo que si se mira de una sustituida (que
    la original y la nueva no esten las dos pendientes o las dos pagadas) es
    de R3, que la lee aunque este fuera.
    """
    if factura.anulada:
        return "La factura está anulada."
    if factura.fusionada_en_id is not None:
        return f"La factura está fusionada en la factura {factura.fusionada_en_id}."
    if factura.sustituida_por is not None:
        return f"La factura está sustituida por la factura {factura.sustituida_por}."
    return None


def en_juego(factura: Factura) -> bool:
    """Ni anulada, ni fusionada, ni sustituida: lo que se paga, se cuenta y se compara."""
    return not (factura.anulada or factura.fusionada_en_id is not None
                or factura.sustituida_por is not None)


def por_factura(regla_id: str, funcion: PorFactura) -> Evaluador:
    """Una regla de una factura sola: la funcion se llama con cada factura en juego.

    Devuelve una lista y no un generador: son decenas de miles de llamadas
    por pasada, y un generador por factura y regla se nota.
    """
    def evaluar(instantanea: Instantanea) -> list[Resultado]:
        politica = instantanea.politica
        salida: list[Resultado] = []
        for factura in instantanea.facturas:
            if (factura.anulada or factura.fusionada_en_id is not None
                    or factura.sustituida_por is not None):
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


# Una relacion "relacionada" no mueve nada, y tampoco calla un duplicado: si
# no, enlazar dos facturas cualesquiera seria la forma de quitar un B2 o un B4
# sin decir que una abona, corrige o sustituye a la otra (huecos.md, §9).
QUE_NO_EXPLICA = "relacionada"


def vinculadas(relaciones: Iterable[Relacion]) -> frozenset[frozenset[int]]:
    """Los pares de facturas unidos por una relacion confirmada que explica el parecido.

    Un abono, una correccion o una sustitucion explican que dos facturas se
    parezcan (el mismo numero, el mismo periodo); una relacion cualquiera no.
    """
    return frozenset(frozenset((r.origen_id, r.destino_id)) for r in relaciones
                     if r.tipo != QUE_NO_EXPLICA)


LEE_RELACIONES = frozenset({"instantanea.relaciones", "relacion.origen_id", "relacion.destino_id",
                            "relacion.tipo"})


# ------------------------------------------------------------ reglas del paso 5
#
# Las reglas de factura del paso 5 escriben solo lo que dicen algo: un fallo
# o un sin_datos. Un ok o un no_aplica no se escribe en la cache: cada
# resultado escrito cuesta unos 13 microsegundos entre la pasada y la cache, y
# catorce reglas mas por factura no cabrian en los dos segundos de cinco mil
# facturas (registro, paso 5). Que una regla no diga nada de una factura es
# que no tiene nada que objetar; sin_datos sigue escribiendose siempre.

LEE_EN_JUEGO = frozenset({"instantanea.facturas", "factura.anulada", "factura.fusionada_en_id",
                          "factura.sustituida_por"})

ConContexto = Callable[[Factura, Any], Sequence[Resultado]]


def solo_objeciones(funcion: ConContexto,
                    preparar: Callable[[Instantanea], Any] | None = None) -> Evaluador:
    """Una regla de factura del paso 5: la funcion con cada factura en juego y su contexto.

    `preparar` construye una vez por pasada lo que la regla necesita de la
    instantanea (los maestros por id, el estado de cada cuenta); sin el, el
    contexto es la instantanea misma. Una factura anulada o fusionada no da
    nada: lo que tuviera abierto se cierra (o queda desaparecido) como con
    cualquier otra regla.
    """
    def evaluar(instantanea: Instantanea) -> list[Resultado]:
        contexto = preparar(instantanea) if preparar is not None else instantanea
        salida: list[Resultado] = []
        for factura in instantanea.facturas:
            if (factura.anulada or factura.fusionada_en_id is not None
                    or factura.sustituida_por is not None):
                continue
            salida.extend(funcion(factura, contexto))
        return salida
    return evaluar


def fallo(regla_id: str, factura: Factura, detalle: str, *,
          valores: Mapping[str, Any] = SIN_VALORES, clave: str = "",
          severidad: str | None = None, objetivos: tuple[Objetivo, ...] = ()) -> Resultado:
    return Resultado(regla_id, "factura", factura.id, FALLO, detalle, valores, clave, None,
                     severidad, objetivos)


def sin_datos(regla_id: str, factura: Factura, detalle: str, *,
              valores: Mapping[str, Any] = SIN_VALORES, clave: str = "") -> Resultado:
    return Resultado(regla_id, "factura", factura.id, SIN_DATOS, detalle, valores, clave)


# Las fuentes con limite de frescura, y en que unidad (decision 7).
FRESCURA = {"exact": "frescura_exact_dias", "trnsprnt": "frescura_trnsprnt_dias",
            "banco": "frescura_banco_dias_laborables"}
VALIDOS = frozenset({"aceptada", "parcial"})


def dias_laborables(desde: date, hasta: date) -> int:
    """Los dias de lunes a viernes despues de `desde` y hasta `hasta`, incluido."""
    if hasta <= desde:
        return 0
    completas, resto = divmod((hasta - desde).days, 7)
    dias = completas * 5
    dia = desde.weekday()
    for _ in range(resto):
        dia = (dia + 1) % 7
        if dia < 5:
            dias += 1
    return dias


def ultimo_lote_valido(instantanea: Instantanea, fuente: str) -> Lote | None:
    """La ultima importacion aceptada (o parcial) de una fuente."""
    validos = [l for l in instantanea.lotes if l.fuente == fuente and l.estado in VALIDOS]
    return max(validos, key=lambda l: l.id) if validos else None


def edad(lote: Lote, hoy: date, fuente: str) -> int:
    """Lo viejo que es un lote: dias, o dias laborables en el banco."""
    if lote.exportado is None:
        return 0
    if fuente == "banco":
        return dias_laborables(lote.exportado, hoy)
    return (hoy - lote.exportado).days


def caducada(instantanea: Instantanea, fuente: str) -> bool | None:
    """Si una fuente esta pasada de su limite de frescura (Z1); None si nunca se importo."""
    lote = ultimo_lote_valido(instantanea, fuente)
    if lote is None or fuente not in FRESCURA:
        return None
    limite = getattr(instantanea.politica, FRESCURA[fuente])
    return edad(lote, instantanea.hoy, fuente) > limite


def importado(instantanea: Instantanea, tipo: str) -> bool:
    """Si ya entro algun maestro de ese tipo (proveedores, clientes...)."""
    return any(l.tipo == tipo and l.estado in VALIDOS for l in instantanea.lotes)


# Lo que lee `importado` (si ya entro un maestro de un tipo) y lo que lee
# `caducada` (si la ultima importacion de una fuente esta pasada de su limite).
LEE_IMPORTADO = frozenset({"instantanea.lotes", "lote.tipo", "lote.estado"})
LEE_CADUCIDAD = frozenset({"instantanea.lotes", "lote.fuente", "lote.estado", "lote.id",
                           "lote.exportado", "instantanea.hoy", "instantanea.politica",
                           "politica.frescura_exact_dias"})
LEE_LOTES = LEE_IMPORTADO | LEE_CADUCIDAD
