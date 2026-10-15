"""La unica via de escritura de las tablas controladas, y el registro de sus campos.

Las tablas controladas (maestros, tarifas, facturas y sus hijas) solo se
escriben desde aqui. No es una convencion: la migracion 0002 pone en cada
una dos disparadores que exigen, para cada columna que entra o cambia, un
cambio_campo con el mismo valor en el evento en curso, y una rev que sube de
uno en uno. Un UPDATE escrito en cualquier otro sitio aborta, y un test
busca en el codigo cualquier sentencia que lo intente.

Una orden es una transaccion con un solo evento: se planifica entera (se
leen las filas, se decide cada campo, se comprueban permisos y motivos), se
registra el evento con todos sus cambio_campo y despues se escriben las
filas y su procedencia. Si algo falla antes, no se escribe nada.

Como decide `fijar` el origen de cada valor (spec §6):

- Una fuente automatica (extraccion, importacion, planning, maestro,
  calculado) nunca pisa un valor manual: solo actualiza valor_automatico, y
  si los dos no coinciden el campo queda "sin resolver" (M1). Una
  verificacion se hizo frente a la lectura de entonces: un automatico nuevo
  que contradice el valor manual la deja sin efecto, y vuelve M1.
- Un valor de una persona es manual_entrada si el campo no tenia original
  automatico, y manual_correccion si lo tenia. Lo decide el sistema, no
  quien edita. Cambiar un valor que ya existe exige el permiso de corregir y
  un motivo; rellenar uno vacio, el de suplir.
- Un valor manual igual al ultimo automatico deshace la correccion: el campo
  vuelve a la fuente automatica, con su referencia.
- Un campo cuyo dueno es Exact o TRNSPRNT (el maestro o la factura vienen de
  alli) no se edita aqui: la correccion va en ese sistema.
- El valor original y su literal impreso no cambian nunca.
- Crear una fila pide lo mismo que fijar sus campos despues: el permiso
  propio de cada campo, nada que no se edite y la atribucion 'manual'.

Cada orden lleva en su evento la foto de cada procedencia que escribe; la
guarda de procedencia_campo exige que la fila sea esa foto, y
`verificar_controladas` compara despues cada fila con la ultima.

El registro (REGISTRO) dice de cada campo su tipo, si es obligatorio en cada
sentido, si se puede editar, que permiso hace falta para suplirlo y para
corregirlo, si su dueno puede ser otro sistema, si es critico y, si es un
campo calculado, como se calcula y de que depende.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .almacen import reloj_de, transaccion
from .almacen.unidades import (
    FueraDeRango,
    PerdidaDePrecision,
    a_cent,
    a_e4,
    a_mil,
    a_pb,
    json_canonico,
)
from .auditoria import Cambio, registrar
from .dominio import (
    FUENTES_AUTOMATICAS,
    ClaseReferencia,
    EstadoRelacion,
    FrecuenciaCiclo,
    Fuente,
    FuenteRelacion,
    FuenteTarifa,
    OrigenAlias,
    OrigenFactura,
    Permiso,
    Sentido,
    SentidoTarifa,
    TipoFactura,
    TipoProveedor,
    TipoRecurso,
    TipoRelacion,
    TratamientoIva,
)
from .permisos import PermisoDenegado, SeparacionDeFunciones, exigir, orden_auditada, separacion
from .reloj import marca

# --------------------------------------------------------------- tipos

TEXTO = "texto"
FECHA = "fecha"
INSTANTE = "instante"
CENT = "cent"
MIL = "mil"
E4 = "e4"
PB = "pb"
ENTERO = "entero"
REF = "ref"
BOOL = "bool"
ENUM = "enum"

SIN_CRUDO = object()          # el valor no viene de un literal impreso
NO_CALCULA = object()         # un calculo que no aplica a esta fila deja el campo como esta

AMBOS = frozenset({Sentido.ENTRANTE.value, Sentido.SALIENTE.value})
ENTRANTE = frozenset({Sentido.ENTRANTE.value})
SALIENTE = frozenset({Sentido.SALIENTE.value})


class CampoNoEditable(ValueError):
    """El campo lo pone el sistema (estructura, calculo, via de entrada)."""


class CampoDeOtroSistema(ValueError):
    """El dueno del campo es Exact o TRNSPRNT: la correccion va en ese sistema."""


class FaltaMotivo(ValueError):
    """Cambiar un valor que ya existe exige un motivo."""


class Conflicto(RuntimeError):
    """La fila cambio desde que quien edita la leyo (rev distinta)."""


class FusionNoValida(ValueError):
    """Una factura solo se fusiona en otra de su mismo sentido y su misma parte, sin cadenas."""


# ------------------------------------------------------------ registro

Calculo = Callable[["Contexto"], Any]


@dataclass(frozen=True)
class Campo:
    tabla: str
    nombre: str
    tipo: str
    valores: tuple[str, ...] = ()
    obligatorio: frozenset[str] = frozenset()
    editable: bool = True
    permiso_suplir: str | None = None
    permiso_corregir: str | None = None
    externo: bool = False          # su dueno es Exact/TRNSPRNT cuando la fila viene de alli
    critico: bool = False
    propio: bool = False           # tiene su propio permiso, no el de su tabla
    motivo_siempre: bool = False   # cambiarlo pide motivo aunque este vacio (ciclo de vida)
    calculo: Calculo | None = None
    depende_de: tuple[str, ...] = ()          # campos de la misma fila
    depende_del_padre: tuple[str, ...] = ()   # campos de la fila padre (PADRES)
    defecto: Any = None                        # valor de alta si nadie lo da


@dataclass(frozen=True)
class Contexto:
    """Lo que ve un calculo: la fila tal como va a quedar, su padre y la base."""

    conn: sqlite3.Connection
    tabla: str
    fila: Mapping[str, Any]
    padre: Mapping[str, Any] | None


# Tabla hija -> (tabla padre, columna que la apunta). Un cambio en la fila
# padre recalcula los campos de la hija que dependen de ella, si la hija es
# la unica activa (una linea dividida en varias imputaciones ya no se copia).
PADRES = {"factura_imputacion": ("factura_linea", "linea_id")}

_TRATAMIENTOS = TratamientoIva.valores()


def _r(tipo: str, **opciones: Any) -> dict[str, Any]:
    return {"tipo": tipo, **opciones}


def _tabla(
    tabla: str, campos: dict[str, dict[str, Any]], *, suplir: str, corregir: str,
) -> dict[str, Campo]:
    return {
        nombre: Campo(
            tabla=tabla, nombre=nombre, tipo=opciones.pop("tipo"),
            propio="suplir" in opciones or "corregir" in opciones,
            permiso_suplir=opciones.pop("suplir", suplir),
            permiso_corregir=opciones.pop("corregir", corregir),
            **opciones,
        )
        for nombre, opciones in ((n, dict(o)) for n, o in campos.items())
    }


# ------------------------------------------------------------ calculos
#
# Cada calculo recibe la fila como quedara y devuelve el valor de la columna
# (ya en su escala: un _mil copiado es un entero, no se vuelve a escalar), o
# NO_CALCULA si no aplica. Los que buscan en los maestros importan identidad
# dentro de la funcion: identidad escribe alias a traves de este modulo.

def _numero_norm(ctx: Contexto) -> Any:
    from .parsing import normalizar_referencia

    return normalizar_referencia(ctx.fila.get("numero"))


def _proveedor_id(ctx: Contexto) -> Any:
    if ctx.fila.get("sentido") != Sentido.ENTRANTE.value:
        return NO_CALCULA
    from .identidad import resolver_parte

    r = resolver_parte(ctx.conn, "proveedor", btw=ctx.fila.get("emisor_btw_doc"),
                       kvk=ctx.fila.get("emisor_kvk_doc"), nombre=ctx.fila.get("emisor_nombre_doc"))
    return Leido(r.fila_id, ref=f"identidad:{r.por}" if r.fila_id else None)


def _cliente_id(ctx: Contexto) -> Any:
    if ctx.fila.get("sentido") != Sentido.SALIENTE.value:
        return NO_CALCULA
    from .identidad import resolver_parte

    r = resolver_parte(ctx.conn, "cliente", btw=ctx.fila.get("receptor_btw_doc"),
                       kvk=None, nombre=ctx.fila.get("receptor_nombre_doc"))
    return Leido(r.fila_id, ref=f"identidad:{r.por}" if r.fila_id else None)


def _unidad(ctx: Contexto) -> Any:
    from .parsing import es_unidad_hora

    texto = (ctx.fila.get("unidad_doc") or "").strip().lower()
    if not texto:
        return None
    return "hora" if es_unidad_hora(texto) else texto


def _tipo_servicio(ctx: Contexto) -> Any:
    """El tipo de trabajo de una linea: lo que va antes de la primera coma.

    Es la misma lectura que usan G3 y la proyeccion de venta
    ("Montagewerk, locatie Rijnhaven" es montagewerk).
    """
    texto = str(ctx.fila.get("descripcion_doc") or "").strip().lower()
    return texto.split(",")[0].strip() or None


def _semana_linea(ctx: Contexto) -> Any:
    """La semana ISO de la linea, por su fecha de trabajo o el inicio de su periodo.

    Con solo el numero de semana impreso queda vacia: el ano de esa semana
    se deduce con la fecha de la factura al cruzar con el planning (paso 10),
    no aqui.
    """
    from .reloj import semana_iso

    for clave in ("fecha_trabajo", "fecha_inicio"):
        valor = ctx.fila.get(clave)
        if valor:
            return semana_iso(date.fromisoformat(valor))
    return None


def _copia(clave: str) -> Calculo:
    def calcular(ctx: Contexto) -> Any:
        return None if ctx.padre is None else ctx.padre.get(clave)
    calcular.__name__ = f"copia_{clave}"
    return calcular


def _horas(ctx: Contexto) -> Any:
    if ctx.padre is None or ctx.padre.get("unidad") != "hora":
        return None
    return ctx.padre.get("cantidad_mil")


def _objeto_de_linea(ctx: Contexto) -> Any:
    if ctx.padre is None:
        return None
    from .identidad import resolver_objeto

    r = resolver_objeto(ctx.conn, ctx.padre.get("objeto_doc"))
    return Leido(r.fila_id, ref=f"identidad:{r.por}" if r.fila_id else None)


def _recurso_de_linea(ctx: Contexto) -> Any:
    if ctx.padre is None:
        return None
    from .identidad import resolver_recurso

    r = resolver_recurso(ctx.conn, ctx.padre.get("recurso_doc"))
    return Leido(r.fila_id, ref=f"identidad:{r.por}" if r.fila_id else None)


def _tipo_turno(ctx: Contexto) -> Any:
    if ctx.padre is None:
        return None
    texto = str(ctx.padre.get("tipo_turno_doc") or "").strip().lower()
    return texto or None


def _alias_norm(ctx: Contexto) -> Any:
    from .identidad import normalizar_nombre

    return normalizar_nombre(ctx.fila.get("alias"))


def _valor_norm(ctx: Contexto) -> Any:
    from .parsing import normalizar_referencia

    return normalizar_referencia(ctx.fila.get("valor_doc"))


# Etiquetas impresas que hacen de una referencia una PO, una orden, un
# proyecto o una referencia del cliente. El modelo copia la etiqueta; esto
# decide (spec §3.19). Lo que no esta en la lista es "otra".
ETIQUETAS_REFERENCIA: tuple[tuple[str, tuple[str, ...]], ...] = (
    (ClaseReferencia.PO.value, ("po", "p.o.", "po nummer", "po-nummer", "po number",
                                "purchase order", "inkooporder", "inkoopordernummer",
                                "bestelnummer", "bestelling")),
    (ClaseReferencia.ORDEN.value, ("order", "ordernummer", "opdracht", "opdrachtnummer",
                                   "werkorder")),
    (ClaseReferencia.PROYECTO.value, ("project", "projectnummer", "projectcode", "proyecto")),
    (ClaseReferencia.REF_CLIENTE.value, ("uw referentie", "uw ref", "uw kenmerk", "your reference",
                                         "your ref", "kenmerk", "referentie klant")),
)


def clasificar_referencia(etiqueta: str | None) -> str:
    texto = " ".join(str(etiqueta or "").lower().replace(":", " ").split())
    for clase, etiquetas in ETIQUETAS_REFERENCIA:
        if texto in etiquetas:
            return clase
    return ClaseReferencia.OTRA.value


def _clase(ctx: Contexto) -> Any:
    return clasificar_referencia(ctx.fila.get("etiqueta_doc"))


# ------------------------------------------------------------ las tablas

_EDITAR = Permiso.EDITAR_EXTRACCION.value
_SUPLIR = Permiso.ANADIR_INFORMACION.value
_ADMIN = Permiso.ADMIN.value
_OBJETO = Permiso.CAMBIAR_OBJETO.value
_PO = Permiso.CAMBIAR_PO.value
_ANULAR = Permiso.ANULAR_ACREDITAR.value
_IBAN = Permiso.CONFIRMAR_IBAN.value

_FIJO = {"editable": False}

REGISTRO: dict[str, dict[str, Campo]] = {
    "proveedor": _tabla("proveedor", {
        "nombre": _r(TEXTO, externo=True),
        "tipo": _r(ENUM, valores=TipoProveedor.valores(), externo=True),
        "kvk": _r(TEXTO, externo=True),
        "btw_id": _r(TEXTO, externo=True),
        "regimen_iva": _r(ENUM, valores=_TRATAMIENTOS, externo=True),
        "plazo_pago_dias": _r(ENTERO, externo=True),
        "direccion": _r(TEXTO, externo=True),
        "email_facturacion": _r(TEXTO, externo=True),
        "telefono_verificacion": _r(TEXTO, suplir=_IBAN, corregir=_IBAN),
        "activo": _r(BOOL, externo=True, defecto=1),
        "exact_id": _r(TEXTO, **_FIJO),
        "trnsprnt_id": _r(TEXTO, **_FIJO),
    }, suplir=_ADMIN, corregir=_ADMIN),
    "cliente": _tabla("cliente", {
        "nombre": _r(TEXTO, externo=True),
        "kvk": _r(TEXTO, externo=True),
        "btw_id": _r(TEXTO, externo=True),
        "plazo_pago_dias": _r(ENTERO, externo=True),
        "requiere_po": _r(BOOL),
        "tratamiento_iva_defecto": _r(ENUM, valores=_TRATAMIENTOS, externo=True),
        "verlegd_elegible": _r(BOOL, defecto=0),
        "activo": _r(BOOL, externo=True, defecto=1),
        "exact_id": _r(TEXTO, **_FIJO),
        "trnsprnt_id": _r(TEXTO, **_FIJO),
    }, suplir=_ADMIN, corregir=_ADMIN),
    "contacto": _tabla("contacto", {
        "proveedor_id": _r(REF, **_FIJO),
        "cliente_id": _r(REF, **_FIJO),
        "nombre": _r(TEXTO),
        "email": _r(TEXTO),
        "telefono": _r(TEXTO),
        "funcion": _r(TEXTO),
        "activo": _r(BOOL, defecto=1),
    }, suplir=_ADMIN, corregir=_ADMIN),
    "objeto": _tabla("objeto", {
        "codigo": _r(TEXTO, externo=True),
        "nombre": _r(TEXTO, externo=True),
        "cliente_id": _r(REF),
        "requiere_po": _r(BOOL, suplir=_PO, corregir=_PO),
        "activo_desde": _r(FECHA, externo=True),
        "activo_hasta": _r(FECHA, externo=True),
        "trnsprnt_id": _r(TEXTO, **_FIJO),
    }, suplir=_OBJETO, corregir=_OBJETO),
    "recurso": _tabla("recurso", {
        "nombre": _r(TEXTO, externo=True),
        "tipo": _r(ENUM, valores=TipoRecurso.valores(), externo=True),
        "proveedor_id": _r(REF, externo=True),
        "trnsprnt_id": _r(TEXTO, **_FIJO),
        "activo": _r(BOOL, externo=True, defecto=1),
    }, suplir=_ADMIN, corregir=_ADMIN),
    # El permiso de un alias depende de a que apunta: ver _permiso().
    "alias": _tabla("alias", {
        "tabla": _r(ENUM, valores=("proveedor", "cliente", "objeto", "recurso"), **_FIJO),
        "alias": _r(TEXTO),
        "alias_norm": _r(TEXTO, editable=False, calculo=_alias_norm, depende_de=("alias",)),
        "fila_id": _r(REF),
        "origen": _r(ENUM, valores=OrigenAlias.valores(), **_FIJO),
        "confirmado": _r(BOOL, defecto=0),
        "activo": _r(BOOL, defecto=1),
    }, suplir=_OBJETO, corregir=_OBJETO),
    "tarifa_acordada": _tabla("tarifa_acordada", {
        "sentido": _r(ENUM, valores=SentidoTarifa.valores(), **_FIJO),
        "proveedor_id": _r(REF),
        "recurso_id": _r(REF),
        "cliente_id": _r(REF),
        "objeto_id": _r(REF),
        "orden_compra_id": _r(REF),
        "tipo_servicio": _r(TEXTO),
        "tipo_turno": _r(TEXTO),
        "unidad": _r(TEXTO),
        "tarifa_e4": _r(E4),
        "vigente_desde": _r(FECHA),
        "vigente_hasta": _r(FECHA),
        "fuente": _r(ENUM, valores=FuenteTarifa.valores(), **_FIJO),
        "documento_id": _r(REF, **_FIJO),
    }, suplir=_ADMIN, corregir=_ADMIN),
    # Paso 5. El IBAN de un beneficiario que no es proveedor lo teclea una
    # persona con admin al darlo de alta; no se cambia despues (se retira y se
    # da de alta otro), igual que una cuenta del registro.
    "beneficiario_conocido": _tabla("beneficiario_conocido", {
        "iban": _r(TEXTO, **_FIJO),
        "nombre": _r(TEXTO),
        "motivo": _r(TEXTO),
        "creado_por": _r(REF, **_FIJO),
        "creado_en": _r(INSTANTE, **_FIJO),
        "retirada_en": _r(INSTANTE, **_FIJO),
    }, suplir=_ADMIN, corregir=_ADMIN),
    "ciclo_facturacion": _tabla("ciclo_facturacion", {
        "cliente_id": _r(REF),
        "objeto_id": _r(REF),
        "frecuencia": _r(ENUM, valores=FrecuenciaCiclo.valores()),
        "ancla": _r(FECHA),
        "dias_gracia": _r(ENTERO, defecto=0),
        "vigente_desde": _r(FECHA),
        "vigente_hasta": _r(FECHA),
    }, suplir=_ADMIN, corregir=_ADMIN),
    "factura": _tabla("factura", {
        "sentido": _r(ENUM, valores=Sentido.valores(), **_FIJO),
        "tipo": _r(ENUM, valores=TipoFactura.valores(), externo=True),
        "origen": _r(ENUM, valores=OrigenFactura.valores(), **_FIJO),
        "documento_id": _r(REF, **_FIJO),
        "extraccion_vigente_id": _r(REF, **_FIJO),
        "fuente_externa": _r(TEXTO, **_FIJO),
        "id_externo": _r(TEXTO, **_FIJO),
        "numero": _r(TEXTO, obligatorio=AMBOS, critico=True, externo=True),
        "numero_norm": _r(TEXTO, editable=False, calculo=_numero_norm, depende_de=("numero",)),
        "proveedor_id": _r(REF, obligatorio=ENTRANTE, critico=True, calculo=_proveedor_id,
                           depende_de=("sentido", "emisor_btw_doc", "emisor_kvk_doc",
                                       "emisor_nombre_doc")),
        "cliente_id": _r(REF, obligatorio=SALIENTE, critico=True, externo=True,
                         calculo=_cliente_id,
                         depende_de=("sentido", "receptor_btw_doc", "receptor_nombre_doc")),
        "contacto_id": _r(REF),
        "emisor_nombre_doc": _r(TEXTO, critico=True, externo=True),
        "emisor_direccion_doc": _r(TEXTO, externo=True),
        "emisor_kvk_doc": _r(TEXTO, externo=True),
        "emisor_btw_doc": _r(TEXTO, externo=True),
        "receptor_nombre_doc": _r(TEXTO, externo=True),
        "receptor_btw_doc": _r(TEXTO, externo=True),
        "contacto_nombre_doc": _r(TEXTO, externo=True),
        "fecha_factura": _r(FECHA, obligatorio=AMBOS, critico=True, externo=True),
        "fecha_recepcion": _r(FECHA),
        "fecha_envio": _r(FECHA, externo=True),
        "periodo_inicio": _r(FECHA, obligatorio=AMBOS, critico=True, externo=True),
        "periodo_fin": _r(FECHA, obligatorio=AMBOS, critico=True, externo=True),
        "fecha_vencimiento": _r(FECHA, externo=True),
        "plazo_pago_dias": _r(ENTERO, externo=True),
        "condiciones_pago_doc": _r(TEXTO, externo=True),
        "base_cent": _r(CENT, obligatorio=AMBOS, externo=True),
        "iva_cent": _r(CENT, obligatorio=AMBOS, critico=True, externo=True),
        "total_cent": _r(CENT, obligatorio=AMBOS, critico=True, externo=True),
        "tipo_iva_pb": _r(PB, externo=True),
        "tratamiento_iva": _r(ENUM, valores=_TRATAMIENTOS, obligatorio=AMBOS, externo=True),
        "kor_mencionada": _r(BOOL, externo=True),
        "autoliquidacion_mencionada": _r(BOOL, externo=True),
        "referencia_pago": _r(TEXTO, externo=True),
        # El IBAN impreso es evidencia, no un dato que se arregla: una persona
        # no lo edita (se verifica o se rechaza el IBAN, paso 5), asi que F3
        # nunca deja de ver lo que dice el documento.
        "iban_doc": _r(TEXTO, critico=True, externo=True, **_FIJO),
        "moneda_doc": _r(TEXTO, **_FIJO),
        "notas_doc": _r(TEXTO, **_FIJO),
        "anulada": _r(BOOL, suplir=_ANULAR, corregir=_ANULAR, defecto=0, motivo_siempre=True),
        "fusionada_en_id": _r(REF, suplir=_ANULAR, corregir=_ANULAR, motivo_siempre=True),
    }, suplir=_SUPLIR, corregir=_EDITAR),
    "factura_linea": _tabla("factura_linea", {
        "factura_id": _r(REF, **_FIJO),
        "orden": _r(ENTERO, **_FIJO),
        "huella_linea": _r(TEXTO, **_FIJO),
        "descripcion_doc": _r(TEXTO, externo=True),
        "objeto_doc": _r(TEXTO, externo=True),
        "recurso_doc": _r(TEXTO, externo=True),
        "unidad_doc": _r(TEXTO, externo=True),
        "semana_doc": _r(ENTERO, externo=True),
        "tipo_turno_doc": _r(TEXTO, externo=True),
        "fecha_inicio": _r(FECHA, externo=True),
        "fecha_fin": _r(FECHA, externo=True),
        "fecha_trabajo": _r(FECHA, externo=True),
        "semana_iso": _r(TEXTO, editable=False, calculo=_semana_linea,
                         depende_de=("fecha_trabajo", "fecha_inicio")),
        "unidad": _r(TEXTO, editable=False, calculo=_unidad, depende_de=("unidad_doc",)),
        "cantidad_mil": _r(MIL, externo=True),
        "tarifa_e4": _r(E4, externo=True),
        "importe_cent": _r(CENT, externo=True),
        "tipo_iva_pb": _r(PB, externo=True),
        "tipo_servicio": _r(TEXTO, calculo=_tipo_servicio, depende_de=("descripcion_doc",)),
        "retirada_en": _r(INSTANTE, **_FIJO),
    }, suplir=_SUPLIR, corregir=_EDITAR),
    "factura_imputacion": _tabla("factura_imputacion", {
        "factura_id": _r(REF, **_FIJO),
        "linea_id": _r(REF, **_FIJO),
        "objeto_id": _r(REF, suplir=_OBJETO, corregir=_OBJETO, calculo=_objeto_de_linea,
                        depende_del_padre=("objeto_doc",)),
        "recurso_id": _r(REF, suplir=_OBJETO, corregir=_OBJETO, calculo=_recurso_de_linea,
                         depende_del_padre=("recurso_doc",)),
        "orden_compra_id": _r(REF, suplir=_PO, corregir=_PO),
        "descripcion": _r(TEXTO, calculo=_copia("descripcion_doc"),
                          depende_del_padre=("descripcion_doc",)),
        "fecha_inicio": _r(FECHA, calculo=_copia("fecha_inicio"),
                           depende_del_padre=("fecha_inicio",)),
        "fecha_fin": _r(FECHA, calculo=_copia("fecha_fin"), depende_del_padre=("fecha_fin",)),
        "semana_iso": _r(TEXTO, editable=False, calculo=_copia("semana_iso"),
                         depende_del_padre=("semana_iso",)),
        "horas_mil": _r(MIL, calculo=_horas, depende_del_padre=("unidad", "cantidad_mil")),
        "tarifa_e4": _r(E4, calculo=_copia("tarifa_e4"), depende_del_padre=("tarifa_e4",)),
        "importe_cent": _r(CENT, calculo=_copia("importe_cent"),
                           depende_del_padre=("importe_cent",)),
        "tipo_servicio": _r(TEXTO, calculo=_copia("tipo_servicio"),
                            depende_del_padre=("tipo_servicio",)),
        "tipo_turno": _r(TEXTO, calculo=_tipo_turno, depende_del_padre=("tipo_turno_doc",)),
        "facturable": _r(BOOL),
        "retirada_en": _r(INSTANTE, **_FIJO),
    }, suplir=_SUPLIR, corregir=_EDITAR),
    "factura_iva": _tabla("factura_iva", {
        "factura_id": _r(REF, **_FIJO),
        "tipo_iva_pb": _r(PB, externo=True),
        "tratamiento": _r(ENUM, valores=_TRATAMIENTOS, externo=True),
        "base_cent": _r(CENT, externo=True),
        "cuota_cent": _r(CENT, externo=True),
        "cuota_autoliquidada_cent": _r(CENT),
        "deducible": _r(BOOL),
        "rubrica": _r(TEXTO),
        "retirada_en": _r(INSTANTE, **_FIJO),
    }, suplir=_SUPLIR, corregir=_EDITAR),
    "factura_referencia": _tabla("factura_referencia", {
        "factura_id": _r(REF, **_FIJO),
        "linea_id": _r(REF, **_FIJO),
        "etiqueta_doc": _r(TEXTO, externo=True),
        "valor_doc": _r(TEXTO, externo=True),
        "valor_norm": _r(TEXTO, editable=False, calculo=_valor_norm, depende_de=("valor_doc",)),
        "clase": _r(ENUM, valores=ClaseReferencia.valores(), suplir=_PO, corregir=_PO,
                    calculo=_clase, depende_de=("etiqueta_doc",)),
        "orden_compra_id": _r(REF, suplir=_PO, corregir=_PO),
        "retirada_en": _r(INSTANTE, **_FIJO),
    }, suplir=_SUPLIR, corregir=_EDITAR),
    "factura_relacion": _tabla("factura_relacion", {
        "origen_id": _r(REF, **_FIJO),
        "destino_id": _r(REF, **_FIJO),
        "tipo": _r(ENUM, valores=TipoRelacion.valores()),
        "importe_cent": _r(CENT),
        "estado": _r(ENUM, valores=EstadoRelacion.valores()),
        "fuente": _r(ENUM, valores=FuenteRelacion.valores(), **_FIJO),
        "evidencia_doc": _r(TEXTO, **_FIJO),
        "retirada_en": _r(INSTANTE, **_FIJO),
    }, suplir=_ANULAR, corregir=_ANULAR),
}

TABLAS_CONTROLADAS: tuple[str, ...] = tuple(REGISTRO)

# Permiso para dar de alta o retirar una fila a mano. Una factura no la crea
# nadie a mano en la V1: llega por un documento o por una importacion.
PERMISO_ALTA: dict[str, str | None] = {
    "proveedor": _ADMIN, "cliente": _ADMIN, "contacto": _ADMIN, "recurso": _ADMIN,
    "tarifa_acordada": _ADMIN, "beneficiario_conocido": _ADMIN, "ciclo_facturacion": _ADMIN,
    "objeto": _OBJETO, "alias": _OBJETO, "factura": None,
    "factura_linea": _EDITAR, "factura_imputacion": _EDITAR, "factura_iva": _EDITAR,
    "factura_referencia": _PO, "factura_relacion": _ANULAR,
}

# Lo que no se edita pero si da quien crea una fila a mano: a que fila
# pertenece y a que apunta. El resto de los campos que no se editan (los
# calculos, la huella, la retirada, los ids de Exact y TRNSPRNT) no los pone
# una persona ni al crear.
ESTRUCTURA: dict[str, frozenset[str]] = {
    "contacto": frozenset({"proveedor_id", "cliente_id"}),
    "alias": frozenset({"tabla"}),
    "tarifa_acordada": frozenset({"sentido", "documento_id"}),
    "beneficiario_conocido": frozenset({"iban", "creado_por", "creado_en"}),
    "factura_linea": frozenset({"factura_id", "orden"}),
    "factura_imputacion": frozenset({"factura_id", "linea_id"}),
    "factura_iva": frozenset({"factura_id"}),
    "factura_referencia": frozenset({"factura_id", "linea_id"}),
    "factura_relacion": frozenset({"origen_id", "destino_id"}),
}

# La columna que dice de donde viene una fila, y lo que vale cuando la crea
# una persona. Nadie firma a mano una fila como de Exact, del maestro o de
# la configuracion.
ATRIBUCION: dict[str, tuple[str, str]] = {
    "alias": ("origen", OrigenAlias.MANUAL.value),
    "tarifa_acordada": ("fuente", FuenteTarifa.MANUAL.value),
    "factura_relacion": ("fuente", FuenteRelacion.MANUAL.value),
}

# Las hijas de una factura que son del dueno de la factura: si la factura es
# de Exact o de TRNSPRNT, una persona no les anade ni les quita filas.
HIJAS_DEL_DUENO = ("factura_linea", "factura_iva", "factura_referencia")

# Como se retira una fila: con una marca de tiempo o desactivandola.
RETIRADA: dict[str, str] = {
    tabla: ("retirada_en" if "retirada_en" in campos else "activo")
    for tabla, campos in REGISTRO.items() if "retirada_en" in campos or "activo" in campos
}


def campo(tabla: str, nombre: str) -> Campo:
    try:
        return REGISTRO[tabla][nombre]
    except KeyError:
        raise KeyError(f"{tabla}.{nombre} no es un campo del registro") from None


def criticos(tabla: str) -> tuple[str, ...]:
    return tuple(n for n, c in REGISTRO[tabla].items() if c.critico)


def obligatorios(tabla: str, sentido: str) -> tuple[str, ...]:
    """Los campos sin los que una fila de ese sentido no esta completa (Q1)."""
    return tuple(n for n, c in REGISTRO[tabla].items() if sentido in c.obligatorio)


# ------------------------------------------------------------ origenes

@dataclass(frozen=True)
class Automatico:
    """Un valor que pone el sistema. `actor` es el usuario de sistema que escribe.

    `usuario_id` es la persona que lanzo la orden, si la hay (una
    importacion). `en_nombre_de` es el sistema dueno de los datos (exact,
    trnsprnt): solo su importacion puede escribir los campos que son suyos.
    """

    fuente: str
    actor: int
    ref: str | None = None
    usuario_id: int | None = None
    en_nombre_de: str | None = None

    def __post_init__(self) -> None:
        if self.fuente not in FUENTES_AUTOMATICAS:
            raise ValueError(
                f"{self.fuente!r} no es una fuente automatica; lo manual lo decide campos.py")


@dataclass(frozen=True)
class Persona:
    """Una persona que edita. El sistema decide si su valor suple o corrige."""

    usuario_id: int
    motivo: str | None = None
    peticion_id: str | None = None


@dataclass(frozen=True)
class Leido:
    """Un valor de una fuente automatica, con el literal del que sale.

    `crudo` es el literal tal cual (por ejemplo '8.740,00'); `dudoso`, que la
    fuente no lo pudo leer con seguridad (low_confidence_fields o un literal
    que no se pudo convertir); `ref`, si se quiere otra referencia que la de
    la orden (identidad:btw); `fuente`, si el valor es de otra fuente
    automatica que la de la orden (la direccion de una factura extraida la
    pone la via de entrada: es 'calculado', no 'extraccion').
    """

    valor: Any
    crudo: Any = SIN_CRUDO
    dudoso: bool = False
    ref: str | None = None
    fuente: str | None = None


Origen = Automatico | Persona


@dataclass(frozen=True)
class Efecto:
    """Lo que paso con un campo en una orden."""

    tabla: str
    fila_id: int
    campo: str
    accion: str               # alta | cambiado | igual | solo_automatico | revertido | verificado
    fuente: str | None = None
    discrepancia: bool = False


@dataclass
class ResultadoOrden:
    evento_id: int | None = None
    efectos: list[Efecto] = field(default_factory=list)
    creadas: list[tuple[str, int]] = field(default_factory=list)

    def de(self, tabla: str, fila_id: int, nombre: str) -> Efecto | None:
        for efecto in reversed(self.efectos):
            if (efecto.tabla, efecto.fila_id, efecto.campo) == (tabla, fila_id, nombre):
                return efecto
        return None


# ------------------------------------------------------------ conversion

def a_columna(definicion: Campo, valor: Any) -> Any:
    """El valor tal como se guarda en la columna. Solo aqui se escala el dinero."""
    if valor is None:
        return None
    tipo = definicion.tipo
    nombre = f"{definicion.tabla}.{definicion.nombre}"
    if tipo == CENT:
        return a_cent(_decimal(valor, nombre))
    if tipo == MIL:
        return a_mil(_decimal(valor, nombre))
    if tipo == E4:
        return a_e4(_decimal(valor, nombre))
    if tipo == PB:
        return a_pb(_decimal(valor, nombre))
    if tipo in (ENTERO, REF):
        if isinstance(valor, bool) or not isinstance(valor, int):
            raise TypeError(f"{nombre}: se espera un entero, no {valor!r}")
        return valor
    if tipo == BOOL:
        if isinstance(valor, bool) or valor in (0, 1):
            return int(valor)
        raise TypeError(f"{nombre}: se espera verdadero o falso, no {valor!r}")
    if tipo == FECHA:
        if isinstance(valor, datetime):
            raise TypeError(f"{nombre}: se espera una fecha, no un instante")
        if isinstance(valor, date):
            return valor.isoformat()
        if isinstance(valor, str):
            return date.fromisoformat(valor).isoformat()
        raise TypeError(f"{nombre}: se espera una fecha, no {valor!r}")
    if tipo == INSTANTE:
        if isinstance(valor, datetime):
            return marca(valor)
        if isinstance(valor, str):
            return marca(datetime.fromisoformat(valor))
        raise TypeError(f"{nombre}: se espera un instante, no {valor!r}")
    if tipo == ENUM:
        texto = str(valor.value if hasattr(valor, "value") else valor)
        if texto not in definicion.valores:
            raise ValueError(f"{nombre}: {texto!r} no es uno de {', '.join(definicion.valores)}")
        return texto
    if tipo == TEXTO:
        if not isinstance(valor, str):
            raise TypeError(f"{nombre}: se espera texto, no {valor!r}")
        return valor
    raise AssertionError(f"tipo desconocido {tipo}")


def _decimal(valor: Any, nombre: str) -> Decimal | int:
    if isinstance(valor, bool) or not isinstance(valor, (Decimal, int)):
        raise TypeError(f"{nombre}: se espera Decimal, no {type(valor).__name__}")
    return valor


def _json(valor: Any) -> str | None:
    return None if valor is None else json_canonico(valor)


def _de_json(texto: str | None) -> Any:
    return None if texto is None else json.loads(texto)


# ------------------------------------------------------------ la orden

@dataclass
class _Fila:
    tabla: str
    id: int
    nueva: bool
    rev: int                                   # la rev que tiene en la base (0 si es nueva)
    valores: dict[str, Any]                    # como quedara
    originales: dict[str, Any]                 # como estaba (vacio si es nueva)
    procedencia: dict[str, dict[str, Any] | None]   # campo -> su procedencia, leida a demanda
    cambiados: set[str] = field(default_factory=set)
    procedencia_tocada: set[str] = field(default_factory=set)
    procedencia_nueva: set[str] = field(default_factory=set)


_COLUMNAS_PROCEDENCIA = (
    "fuente", "fuente_ref", "valor_actual", "valor_original", "valor_original_crudo",
    "fuente_original", "valor_automatico", "fuente_automatica", "fuente_automatica_ref",
    "dudoso", "rev_campo", "cambiado_en", "cambiado_por", "verificado_por", "verificado_en",
    "verificado_rev",
)
_ORIGINALES = ("valor_original", "valor_original_crudo", "fuente_original")

# La clave de los datos del evento con la foto de cada procedencia que la
# orden escribe ("tabla:fila_id:campo" -> sus columnas).
FOTOS_PROCEDENCIA = "procedencia"


def clave_procedencia(tabla: str, fila_id: int, nombre: str) -> str:
    return f"{tabla}:{fila_id}:{nombre}"


class Orden:
    """Una orden en curso: se planifica entera y se escribe al salir del `with`."""

    def __init__(
        self, conn: sqlite3.Connection, origen: Origen, *, tipo: str,
        tabla: str | None, fila_id: int | None, factura_id: int | None,
        datos: Mapping[str, Any] | None,
    ) -> None:
        self.conn = conn
        self.origen = origen
        self.tipo = tipo
        self.tabla = tabla
        self.fila_id = fila_id
        self.factura_id = factura_id
        self.datos = dict(datos or {})
        self.ahora = marca(reloj_de(conn).ahora())
        self._filas: dict[tuple[str, int], _Fila] = {}
        self._orden: list[tuple[str, int]] = []
        self._siguiente: dict[str, int] = {}
        self._autorrevisados: list[str] = []
        self.resultado = ResultadoOrden()

    # ---- quien

    @property
    def persona(self) -> int | None:
        if isinstance(self.origen, Persona):
            return self.origen.usuario_id
        return self.origen.usuario_id

    @property
    def actor(self) -> int:
        return self.origen.usuario_id if isinstance(self.origen, Persona) else self.origen.actor

    # ---- lectura

    def fila(self, tabla: str, fila_id: int) -> Mapping[str, Any]:
        """La fila como quedara al terminar la orden (lo planificado encima de la base)."""
        return dict(self._cargar(tabla, fila_id).valores)

    def _cargar(self, tabla: str, fila_id: int) -> _Fila:
        clave = (tabla, fila_id)
        if clave in self._filas:
            return self._filas[clave]
        if tabla not in REGISTRO:
            raise ValueError(f"{tabla} no es una tabla controlada")
        fila = self.conn.execute(f"SELECT * FROM {tabla} WHERE id = ?", (fila_id,)).fetchone()
        if fila is None:
            raise LookupError(f"no hay {tabla} {fila_id}")
        valores = {c: fila[c] for c in REGISTRO[tabla]}
        estado = _Fila(tabla, fila_id, False, fila["rev"], dict(valores), dict(valores), {})
        self._filas[clave] = estado
        return estado

    def _procedencia(self, estado: _Fila, nombre: str) -> dict[str, Any] | None:
        if nombre not in estado.procedencia:
            fila = None if estado.nueva else self.conn.execute(
                "SELECT * FROM procedencia_campo WHERE tabla = ? AND fila_id = ? AND campo = ?",
                (estado.tabla, estado.id, nombre),
            ).fetchone()
            estado.procedencia[nombre] = (
                {c: fila[c] for c in _COLUMNAS_PROCEDENCIA} if fila is not None else None)
        return estado.procedencia[nombre]

    def _nuevo_id(self, tabla: str) -> int:
        if tabla not in self._siguiente:
            maximo = self.conn.execute(f"SELECT coalesce(max(id), 0) FROM {tabla}").fetchone()[0]
            self._siguiente[tabla] = int(maximo) + 1
        nuevo = self._siguiente[tabla]
        self._siguiente[tabla] += 1
        return nuevo

    # ---- operaciones

    def crear(self, tabla: str, valores: Mapping[str, Any]) -> int:
        """Planifica una fila nueva. Devuelve su id (ya fijado)."""
        if tabla not in REGISTRO:
            raise ValueError(f"{tabla} no es una tabla controlada")
        desconocidos = set(valores) - set(REGISTRO[tabla])
        if desconocidos:
            raise KeyError(f"{tabla} no tiene los campos {', '.join(sorted(desconocidos))}")
        if isinstance(self.origen, Persona):
            self._exigir(_permiso_alta(tabla, valores), f"dar de alta {tabla}")
            valores = self._alta_de_persona(tabla, valores)
        fila_id = self._nuevo_id(tabla)
        estado = _Fila(tabla, fila_id, True, 0, {c: None for c in REGISTRO[tabla]}, {}, {})
        self._filas[(tabla, fila_id)] = estado
        self._orden.append((tabla, fila_id))
        self.resultado.creadas.append((tabla, fila_id))
        if self.tabla is None:
            self.tabla, self.fila_id = tabla, fila_id

        for nombre, valor in valores.items():
            self._poner(estado, nombre, valor, self.origen, alta=True)
        for nombre, definicion in REGISTRO[tabla].items():
            if nombre in valores:
                continue
            if definicion.calculo is not None:
                self._calcular(estado, nombre)
            elif definicion.defecto is not None:
                self._poner(estado, nombre, Leido(definicion.defecto, ref="defecto"),
                            Automatico(Fuente.CALCULADO.value, self.actor), alta=True)
        return fila_id

    def _alta_de_persona(self, tabla: str, valores: Mapping[str, Any]) -> dict[str, Any]:
        """Lo que una persona puede dar al crear una fila: lo mismo que podria fijar despues.

        El permiso de la tabla (PERMISO_ALTA) cubre el contenido corriente de
        la fila; un campo con permiso propio (la PO, el Objeto, el telefono de
        verificacion) lo pide tambien al crear, porque si no crear seria la
        forma de saltarselo. Un campo que no se edita no se da, salvo la
        estructura; la atribucion es siempre 'manual'; y una hija de una
        factura de Exact o de TRNSPRNT no se crea aqui.
        """
        salida = dict(valores)
        atribucion = ATRIBUCION.get(tabla)
        if atribucion is not None:
            columna, manual = atribucion
            dado = salida.get(columna)
            if dado is not None and str(getattr(dado, "value", dado)) != manual:
                raise CampoNoEditable(
                    f"{tabla}.{columna} de una fila creada a mano es {manual!r}, no {dado!r}")
            salida[columna] = manual
        if tabla in HIJAS_DEL_DUENO and salida.get("factura_id") is not None:
            dueno = self._dueno(self._cargar("factura", salida["factura_id"]))
            if dueno is not None:
                raise CampoDeOtroSistema(
                    f"la factura {salida['factura_id']} viene de {dueno}: sus {tabla} se "
                    "cambian alli")
        estructura = ESTRUCTURA.get(tabla, frozenset())
        for nombre, valor in salida.items():
            definicion = REGISTRO[tabla][nombre]
            if valor is None or nombre in estructura or (
                    atribucion is not None and nombre == atribucion[0]):
                continue
            if not definicion.editable:
                raise CampoNoEditable(
                    f"{tabla}.{nombre} lo pone el sistema: tampoco se da al crear la fila")
            if definicion.propio:
                self._exigir(_permiso(definicion, salida, corregir=False),
                             f"rellenar {tabla}.{nombre}")
        return salida

    def fijar(self, tabla: str, fila_id: int, valores: Mapping[str, Any],
              *, rev_esperada: int | None = None) -> None:
        estado = self._cargar(tabla, fila_id)
        if rev_esperada is not None and not estado.nueva and estado.rev != rev_esperada:
            raise Conflicto(
                f"{tabla} {fila_id} esta en la rev {estado.rev} y se edito sobre la "
                f"{rev_esperada}: vuelve a cargarla")
        desconocidos = set(valores) - set(REGISTRO[tabla])
        if desconocidos:
            raise KeyError(f"{tabla} no tiene los campos {', '.join(sorted(desconocidos))}")
        if (tabla, fila_id) not in self._orden:
            self._orden.append((tabla, fila_id))
        if self.tabla is None:
            self.tabla, self.fila_id = tabla, fila_id
        cambiados = set()
        for nombre, valor in valores.items():
            if self._poner(estado, nombre, valor, self.origen):
                cambiados.add(nombre)
        self._propagar(estado, cambiados)

    def retirar(self, tabla: str, fila_id: int) -> None:
        """Retira una fila (retirada_en) o la desactiva (activo = 0). Nunca la borra."""
        columna = RETIRADA.get(tabla)
        if columna is None:
            raise ValueError(f"{tabla} no se retira")
        estado = self._cargar(tabla, fila_id)
        if isinstance(self.origen, Persona):
            self._exigir(_permiso_alta(tabla, estado.valores), f"retirar {tabla}")
            if not (self.origen.motivo or "").strip():
                raise FaltaMotivo(f"retirar {tabla} {fila_id} exige un motivo")
            dueno = self._dueno(estado)
            if dueno is not None:
                raise CampoDeOtroSistema(
                    f"{tabla} {fila_id} viene de {dueno}: se retira alli")
        if (tabla, fila_id) not in self._orden:
            self._orden.append((tabla, fila_id))
        if self.tabla is None:
            self.tabla, self.fila_id = tabla, fila_id
        valor = datetime.fromisoformat(self.ahora) if columna == "retirada_en" else False
        if estado.valores[columna] not in (None, 1):
            return                                    # ya estaba retirada
        self._poner(estado, columna, valor, self.origen, forzar=True)
        # Una linea excluida no puede seguir imputada: sus imputaciones se
        # retiran con ella, en la misma orden y con el mismo motivo, como hace
        # la ingesta con una linea que desaparece.
        for tabla_hija, (tabla_padre, columna_padre) in PADRES.items():
            if tabla_padre == tabla:
                for hija in self._hijas_activas(tabla_hija, columna_padre, fila_id):
                    self.retirar(tabla_hija, hija)

    def recalcular(self, tabla: str, fila_id: int, nombres: tuple[str, ...] | None = None) -> None:
        """Vuelve a calcular los campos calculados de una fila (por defecto, todos).

        Sirve cuando cambia algo fuera de la fila, por ejemplo un maestro
        nuevo que ahora resuelve un proveedor o un Objeto. Un valor manual no
        se pisa: el calculo solo queda como valor automatico.
        """
        estado = self._cargar(tabla, fila_id)
        if (tabla, fila_id) not in self._orden:
            self._orden.append((tabla, fila_id))
        cambiados = set()
        for nombre, definicion in REGISTRO[tabla].items():
            if definicion.calculo is not None and (nombres is None or nombre in nombres):
                if self._calcular(estado, nombre):
                    cambiados.add(nombre)
        self._propagar(estado, cambiados)

    def verificar(self, tabla: str, fila_id: int, nombres: tuple[str, ...]) -> None:
        """Una persona da por bueno el valor actual de cada campo.

        La verificacion vale para la rev del campo: cualquier cambio despues
        la deja sin efecto. Si quien verifica es quien puso el valor a mano y
        hay otra persona que podria verificarlo, se niega (si_hay_dos); si es
        la unica, queda marcada como autorrevisada.
        """
        if not isinstance(self.origen, Persona):
            raise PermisoDenegado(None, Permiso.EDITAR_EXTRACCION.value,
                                  "un campo lo verifica una persona, no el sistema")
        estado = self._cargar(tabla, fila_id)
        if (tabla, fila_id) not in self._orden:
            self._orden.append((tabla, fila_id))
        if self.tabla is None:
            self.tabla, self.fila_id = tabla, fila_id
        for nombre in nombres:
            definicion = campo(tabla, nombre)
            permiso = _permiso(definicion, estado.valores, corregir=True)
            self._exigir(permiso, f"verificar {tabla}.{nombre}")
            procedencia = self._procedencia(estado, nombre)
            if procedencia is None:
                raise ValueError(
                    f"{tabla}.{nombre} de la fila {fila_id} no tiene valor que verificar")
            autor = procedencia["cambiado_por"] if procedencia["fuente"] in (
                Fuente.MANUAL_ENTRADA.value, Fuente.MANUAL_CORRECCION.value) else None
            decision = separacion(self.conn, permiso, autor, self.origen.usuario_id)
            if decision == "denegado":
                raise SeparacionDeFunciones(
                    self.origen.usuario_id, permiso,
                    f"{tabla}.{nombre} lo cambio esta misma persona y hay otra con el permiso "
                    f"{permiso}: lo verifica la otra", f"verificar {tabla}.{nombre}")
            if decision == "autorrevisado":
                self._autorrevisados.append(f"{tabla}:{fila_id}:{nombre}")
            procedencia.update(verificado_por=self.origen.usuario_id, verificado_en=self.ahora,
                               verificado_rev=procedencia["rev_campo"])
            estado.procedencia_tocada.add(nombre)
            self.resultado.efectos.append(Efecto(tabla, fila_id, nombre, "verificado",
                                                 procedencia["fuente"]))

    # ---- decision por campo

    def _exigir(self, permiso: str | None, accion: str) -> None:
        if permiso is None:
            raise PermisoDenegado(self.persona, "admin", f"nadie puede {accion} a mano", accion)
        exigir(self.conn, self.origen.usuario_id, permiso, accion=accion)

    def _poner(self, estado: _Fila, nombre: str, entrada: Any, origen: Origen,
               *, alta: bool = False, forzar: bool = False, columna: bool = False) -> bool:
        """Decide y planifica un campo. Devuelve si cambia el valor de la columna."""
        definicion = campo(estado.tabla, nombre)
        if isinstance(origen, Persona):
            if isinstance(entrada, Leido):
                raise TypeError("una persona no trae literales: su valor es el valor")
            return self._poner_manual(estado, definicion, entrada, origen, forzar=forzar)
        leido = entrada if isinstance(entrada, Leido) else Leido(entrada)
        if leido.fuente is not None and leido.fuente != origen.fuente:
            origen = Automatico(leido.fuente, origen.actor, ref=origen.ref,
                                usuario_id=origen.usuario_id, en_nombre_de=origen.en_nombre_de)
        if columna:
            valor = leido.valor
        else:
            try:
                valor = a_columna(definicion, leido.valor)
            except (PerdidaDePrecision, FueraDeRango):
                # No se redondea nunca: el campo queda vacio y dudoso (Q2), con
                # su literal, y una persona decide.
                valor, leido = None, Leido(None, crudo=leido.crudo, dudoso=True, ref=leido.ref)
        return self._poner_automatico(estado, definicion, valor, leido, origen, alta=alta)

    def _dueno(self, estado: _Fila) -> str | None:
        """El sistema dueno de la fila, si viene de Exact o de TRNSPRNT."""
        valores = estado.valores
        if estado.tabla in ("proveedor", "cliente"):
            if valores.get("exact_id"):
                return "exact"
            return "trnsprnt" if valores.get("trnsprnt_id") else None
        if estado.tabla in ("objeto", "recurso"):
            return "trnsprnt" if valores.get("trnsprnt_id") else None
        if estado.tabla == "factura":
            return valores["origen"] if valores.get("origen") in ("exact", "trnsprnt") else None
        if estado.tabla in ("factura_linea", "factura_iva", "factura_referencia"):
            factura_id = valores.get("factura_id")
            if factura_id is None:
                return None
            return self._dueno(self._cargar("factura", factura_id))
        return None

    def _poner_automatico(self, estado: _Fila, definicion: Campo, valor: Any, leido: Leido,
                          origen: Automatico, *, alta: bool) -> bool:
        nombre = definicion.nombre
        # Una fila nueva la crea quien la crea; el dueno solo cuenta despues.
        dueno = self._dueno(estado) if definicion.externo and not estado.nueva else None
        if dueno is not None and origen.fuente != Fuente.CALCULADO.value and (
                origen.en_nombre_de != dueno):
            raise CampoDeOtroSistema(
                f"{estado.tabla}.{nombre} es de {dueno}: solo lo escribe su importacion")
        ref = leido.ref or origen.ref
        crudo = None if leido.crudo is SIN_CRUDO else _json(leido.crudo)
        procedencia = self._procedencia(estado, nombre)
        actual = estado.valores[nombre]

        if procedencia is None:
            if valor is None and crudo is None and not leido.dudoso:
                return False
            estado.procedencia[nombre] = {
                "fuente": origen.fuente, "fuente_ref": ref, "valor_actual": _json(valor),
                "valor_original": _json(valor), "valor_original_crudo": crudo,
                "fuente_original": origen.fuente, "valor_automatico": _json(valor),
                "fuente_automatica": origen.fuente, "fuente_automatica_ref": ref,
                "dudoso": int(leido.dudoso), "rev_campo": self._rev_nueva(estado),
                "cambiado_en": self.ahora, "cambiado_por": origen.actor,
                "verificado_por": None, "verificado_en": None, "verificado_rev": None,
            }
            estado.procedencia_nueva.add(nombre)
            estado.procedencia_tocada.add(nombre)
            cambia = valor != actual or (estado.nueva and valor is not None)
            if cambia:
                estado.valores[nombre] = valor
                estado.cambiados.add(nombre)
            self.resultado.efectos.append(Efecto(
                estado.tabla, estado.id, nombre, "alta" if estado.nueva else "cambiado",
                origen.fuente))
            return cambia

        automatico = {"valor_automatico": _json(valor), "fuente_automatica": origen.fuente,
                      "fuente_automatica_ref": ref}
        if procedencia["fuente"] not in FUENTES_AUTOMATICAS:
            # Lo manual gana: el automatico solo se apunta. Si el automatico
            # nuevo contradice el valor manual y no es el que habia cuando se
            # verifico, la verificacion ya no vale: se verifico frente a otra
            # lectura, y el campo vuelve a estar sin resolver (M1).
            nuevo = {**automatico, "dudoso": int(leido.dudoso)}
            if (procedencia["verificado_por"] is not None
                    and automatico["valor_automatico"] is not None
                    and automatico["valor_automatico"] != procedencia["valor_automatico"]
                    and automatico["valor_automatico"] != procedencia["valor_actual"]):
                nuevo.update(verificado_por=None, verificado_en=None, verificado_rev=None)
            if any(procedencia[c] != v for c, v in nuevo.items()):
                procedencia.update(nuevo)
                estado.procedencia_tocada.add(nombre)
            self.resultado.efectos.append(Efecto(
                estado.tabla, estado.id, nombre, "solo_automatico", procedencia["fuente"],
                discrepancia=_json(valor) != procedencia["valor_actual"]))
            return False

        if valor == actual:
            # El mismo valor de otra fuente automatica no es un cambio (no hay
            # cambio_campo): la procedencia sigue diciendo de donde salio el
            # valor (la fuente de su ultimo cambio, que verificar_controladas
            # compara) y apunta la nueva como automatica. Asi una importacion
            # que adopta un cliente de la semilla con activo por defecto no
            # deja una procedencia que su historia no explica.
            nuevo = {**automatico, "dudoso": int(leido.dudoso)}
            if procedencia["fuente"] == origen.fuente:
                nuevo["fuente_ref"] = ref
            if any(procedencia[c] != v for c, v in nuevo.items()):
                procedencia.update(nuevo)
                estado.procedencia_tocada.add(nombre)
            self.resultado.efectos.append(Efecto(
                estado.tabla, estado.id, nombre, "igual", origen.fuente))
            return False

        procedencia.update(
            automatico, fuente=origen.fuente, fuente_ref=ref, valor_actual=_json(valor),
            dudoso=int(leido.dudoso), rev_campo=self._rev_nueva(estado),
            cambiado_en=self.ahora, cambiado_por=origen.actor)
        estado.procedencia_tocada.add(nombre)
        estado.valores[nombre] = valor
        estado.cambiados.add(nombre)
        self.resultado.efectos.append(Efecto(
            estado.tabla, estado.id, nombre, "cambiado", origen.fuente))
        return True

    def _poner_manual(self, estado: _Fila, definicion: Campo, entrada: Any, persona: Persona,
                      *, forzar: bool) -> bool:
        nombre = definicion.nombre
        if not definicion.editable and not forzar and not estado.nueva:
            raise CampoNoEditable(f"{estado.tabla}.{nombre} lo pone el sistema: no se edita a mano")
        if definicion.externo and not estado.nueva:
            dueno = self._dueno(estado)
            if dueno is not None:
                raise CampoDeOtroSistema(
                    f"{estado.tabla}.{nombre} viene de {dueno}: corrigelo alli, y la siguiente "
                    "importacion lo traera")
        valor = a_columna(definicion, entrada)
        procedencia = self._procedencia(estado, nombre)
        actual = estado.valores[nombre]

        hay_automatico = procedencia is not None and procedencia["fuente_automatica"] is not None
        # Habia original automatico si una fuente automatica dijo algo: un
        # valor, o un literal que no se pudo leer (corregir una mala lectura
        # tambien es corregir).
        hay_original = procedencia is not None and (
            (procedencia["fuente_original"] in FUENTES_AUTOMATICAS
             and (procedencia["valor_original"] is not None
                  or procedencia["valor_original_crudo"] is not None))
            or procedencia["valor_automatico"] is not None)

        if not forzar and not estado.nueva:
            corrige = actual is not None or hay_original
            permiso = _permiso(definicion, estado.valores, corregir=corrige)
            self._exigir(permiso, f"{'corregir' if corrige else 'rellenar'} "
                                  f"{estado.tabla}.{nombre}")

        if hay_automatico and _json(valor) == procedencia["valor_automatico"]:
            fuente, ref, accion = (procedencia["fuente_automatica"],
                                   procedencia["fuente_automatica_ref"], "revertido")
            if procedencia["fuente"] in FUENTES_AUTOMATICAS:
                accion = "igual"
        elif not hay_original:
            fuente, ref, accion = (Fuente.MANUAL_ENTRADA.value, f"usuario:{persona.usuario_id}",
                                   "cambiado")
        else:
            fuente, ref, accion = (Fuente.MANUAL_CORRECCION.value,
                                   f"usuario:{persona.usuario_id}", "cambiado")

        if valor == actual and (procedencia is None or procedencia["fuente"] == fuente):
            self.resultado.efectos.append(Efecto(estado.tabla, estado.id, nombre, "igual",
                                                 procedencia["fuente"] if procedencia else None))
            return False
        motivo = (persona.motivo or "").strip()
        if definicion.motivo_siempre and not motivo:
            raise FaltaMotivo(
                f"{estado.tabla}.{nombre} cambia la vida de la fila: exige un motivo")
        if (actual is not None or fuente == Fuente.MANUAL_CORRECCION.value) and not motivo:
            raise FaltaMotivo(
                f"cambiar {estado.tabla}.{nombre} exige un motivo: ya tenia un valor")
        if estado.tabla == "factura" and nombre == "fusionada_en_id" and valor is not None:
            self._comprobar_fusion(estado, valor)

        rev = self._rev_nueva(estado)
        if procedencia is None:
            estado.procedencia[nombre] = {
                "fuente": fuente, "fuente_ref": ref, "valor_actual": _json(valor),
                "valor_original": _json(valor), "valor_original_crudo": None,
                "fuente_original": fuente, "valor_automatico": None, "fuente_automatica": None,
                "fuente_automatica_ref": None, "dudoso": 0, "rev_campo": rev,
                "cambiado_en": self.ahora, "cambiado_por": persona.usuario_id,
                "verificado_por": None, "verificado_en": None, "verificado_rev": None,
            }
            estado.procedencia_nueva.add(nombre)
        else:
            procedencia.update(fuente=fuente, fuente_ref=ref, valor_actual=_json(valor),
                               rev_campo=rev, cambiado_en=self.ahora,
                               cambiado_por=persona.usuario_id)
        estado.procedencia_tocada.add(nombre)
        # Tambien con el mismo valor y otra fuente (deshacer hacia un automatico
        # identico) hay cambio_campo: el cambio de fuente es historia del campo.
        estado.cambiados.add(nombre)
        estado.valores[nombre] = valor
        self.resultado.efectos.append(Efecto(estado.tabla, estado.id, nombre, accion, fuente))
        return valor != actual

    def _comprobar_fusion(self, estado: _Fila, destino_id: int) -> None:
        """Una fusion une un duplicado con su factura: mismo sentido, misma parte, sin cadenas.

        Sin esto, fusionar serviria para quitar de en medio cualquier factura
        (la de un proveedor en la de otro, o dos entre si). La parte tiene que
        estar resuelta en las dos: dos facturas sin proveedor no se sabe que
        sean del mismo. La migracion 0002 lo exige tambien con un disparador.
        """
        destino = self._cargar("factura", destino_id).valores
        sentido = estado.valores["sentido"]
        parte = "proveedor_id" if sentido == Sentido.ENTRANTE.value else "cliente_id"
        fusionadas_aqui = [i for (t, i), e in self._filas.items()
                           if t == "factura" and i != estado.id
                           and e.valores.get("fusionada_en_id") == estado.id]
        if not fusionadas_aqui:
            fusionadas_aqui = [f[0] for f in self.conn.execute(
                "SELECT id FROM factura WHERE fusionada_en_id = ? AND id <> ?",
                (estado.id, estado.id))]
        problema = None
        if destino_id == estado.id:
            problema = "una factura no se fusiona en si misma"
        elif destino.get("fusionada_en_id") is not None:
            problema = (f"la factura {destino_id} ya esta fusionada en la "
                        f"{destino['fusionada_en_id']}: se fusiona en esa")
        elif fusionadas_aqui:
            problema = (f"en la factura {estado.id} hay otras fusionadas "
                        f"({', '.join(map(str, fusionadas_aqui))}): no se encadenan")
        elif destino.get("sentido") != sentido:
            problema = "una compra y una venta no se fusionan"
        elif estado.valores.get(parte) is None or destino.get(parte) != estado.valores.get(parte):
            problema = (f"las dos facturas tienen que ser del mismo {parte[:-3]}, "
                        "y estar resuelto en las dos")
        if problema is not None:
            raise FusionNoValida(problema)

    def _rev_nueva(self, estado: _Fila) -> int:
        return 0 if estado.nueva else estado.rev + 1

    def _calcular(self, estado: _Fila, nombre: str) -> bool:
        definicion = REGISTRO[estado.tabla][nombre]
        padre = None
        if estado.tabla in PADRES:
            tabla_padre, columna = PADRES[estado.tabla]
            padre_id = estado.valores.get(columna)
            padre = self.fila(tabla_padre, padre_id) if padre_id is not None else None
        resultado = definicion.calculo(Contexto(self.conn, estado.tabla, estado.valores, padre))
        if resultado is NO_CALCULA:
            return False
        leido = resultado if isinstance(resultado, Leido) else Leido(resultado)
        origen = Automatico(Fuente.CALCULADO.value, self.actor, ref="calculo")
        return self._poner(estado, nombre, leido, origen, alta=estado.nueva, columna=True)

    def _propagar(self, estado: _Fila, cambiados: set[str]) -> None:
        """Recalcula lo que depende de los campos que acaban de cambiar."""
        pendientes = set(cambiados)
        vistos: set[str] = set()
        while pendientes:
            nombre_cambiado = pendientes.pop()
            vistos.add(nombre_cambiado)
            for nombre, definicion in REGISTRO[estado.tabla].items():
                if definicion.calculo is not None and nombre_cambiado in definicion.depende_de:
                    if self._calcular(estado, nombre) and nombre not in vistos:
                        pendientes.add(nombre)
        cambiados_todos = vistos
        for tabla_hija, (tabla_padre, columna) in PADRES.items():
            if tabla_padre != estado.tabla or not cambiados_todos:
                continue
            hijas = self._hijas_activas(tabla_hija, columna, estado.id)
            if len(hijas) != 1:
                continue
            hija = self._cargar(tabla_hija, hijas[0])
            if (tabla_hija, hija.id) not in self._orden:
                self._orden.append((tabla_hija, hija.id))
            for nombre, definicion in REGISTRO[tabla_hija].items():
                if (definicion.calculo is not None
                        and cambiados_todos & set(definicion.depende_del_padre)):
                    self._calcular(hija, nombre)

    def _hijas_activas(self, tabla: str, columna: str, padre_id: int) -> list[int]:
        en_base = [f["id"] for f in self.conn.execute(
            f"SELECT id FROM {tabla} WHERE {columna} = ? ORDER BY id", (padre_id,))]
        planificadas = [i for (t, i), e in self._filas.items() if t == tabla and e.nueva
                        and e.valores.get(columna) == padre_id]
        activas = []
        for fila_id in sorted(set(en_base) | set(planificadas)):
            valores = self._cargar(tabla, fila_id).valores
            if valores.get("retirada_en") is None:
                activas.append(fila_id)
        return activas

    # ---- escritura

    def escribir(self) -> ResultadoOrden:
        cambios: list[Cambio] = []
        fotos: dict[str, dict[str, Any]] = {}
        for clave in self._orden:
            estado = self._filas[clave]
            factura_id = _factura_de(estado)
            rev = self._rev_nueva(estado)
            for nombre in REGISTRO[estado.tabla]:
                procedencia = estado.procedencia.get(nombre)
                if nombre in estado.cambiados:
                    anterior = self._procedencia_anterior(estado, nombre)
                    cambios.append(Cambio(
                        tabla=estado.tabla, fila_id=estado.id, campo=nombre, rev=rev,
                        valor_anterior=None if estado.nueva else estado.originales[nombre],
                        valor_nuevo=estado.valores[nombre],
                        fuente_nueva=procedencia["fuente"],
                        fuente_anterior=anterior,
                        motivo=_motivo_de(self.origen, procedencia),
                        factura_id=factura_id,
                    ))
                if nombre in estado.procedencia_tocada:
                    fotos[clave_procedencia(estado.tabla, estado.id, nombre)] = {
                        c: procedencia[c] for c in _COLUMNAS_PROCEDENCIA}
        nuevas = [self._filas[c] for c in self._orden if self._filas[c].nueva]
        if not cambios and not fotos and not nuevas:
            return self.resultado

        datos = dict(self.datos)
        if fotos:
            # La procedencia de cada campo tocado, tal como queda: la guarda de
            # procedencia_campo exige que la fila sea esta foto, y como el
            # evento esta en la cadena, db verificar puede comparar despues.
            datos[FOTOS_PROCEDENCIA] = fotos
        if self._autorrevisados:
            datos["autorrevisados"] = sorted(self._autorrevisados)
        persona = self.origen if isinstance(self.origen, Persona) else None
        self.resultado.evento_id = registrar(
            self.conn, tipo=self.tipo, actor=self.actor, usuario_id=self.persona,
            tabla=self.tabla, fila_id=self.fila_id,
            factura_id=self.factura_id if self.factura_id is not None else (
                _factura_de(self._filas[self._orden[0]]) if self._orden else None),
            motivo=persona.motivo if persona else None,
            datos=datos or None, peticion_id=persona.peticion_id if persona else None,
            cambios=cambios,
        )
        for clave in self._orden:
            self._escribir_fila(self._filas[clave])
        for clave in self._orden:
            self._escribir_procedencia(self._filas[clave])
        return self.resultado

    def _procedencia_anterior(self, estado: _Fila, nombre: str) -> str | None:
        if estado.nueva or nombre in estado.procedencia_nueva:
            return None
        fila = self.conn.execute(
            "SELECT fuente FROM procedencia_campo WHERE tabla = ? AND fila_id = ? AND campo = ?",
            (estado.tabla, estado.id, nombre)).fetchone()
        return fila["fuente"] if fila else None

    def _escribir_fila(self, estado: _Fila) -> None:
        columnas = list(REGISTRO[estado.tabla])
        if estado.nueva:
            nombres = ["id", *columnas, "rev"]
            valores = [estado.id, *(estado.valores[c] for c in columnas), 0]
            self.conn.execute(
                f"INSERT INTO {estado.tabla} ({', '.join(nombres)}) "
                f"VALUES ({', '.join('?' * len(nombres))})", valores)
            return
        if not estado.cambiados:
            return
        nombres = sorted(c for c in estado.cambiados if estado.valores[c] != estado.originales[c])
        asignaciones = ", ".join(f"{c} = ?" for c in nombres)
        sql = (f"UPDATE {estado.tabla} SET {asignaciones}{', ' if nombres else ''}rev = ? "
               "WHERE id = ? AND rev = ?")
        cursor = self.conn.execute(
            sql, [*(estado.valores[c] for c in nombres), estado.rev + 1, estado.id, estado.rev])
        if cursor.rowcount != 1:
            raise Conflicto(f"{estado.tabla} {estado.id} cambio mientras se escribia")

    def _escribir_procedencia(self, estado: _Fila) -> None:
        for nombre in sorted(estado.procedencia_tocada):
            fila = estado.procedencia[nombre]
            if nombre in estado.procedencia_nueva:
                columnas = ("tabla", "fila_id", "campo", *_COLUMNAS_PROCEDENCIA)
                self.conn.execute(
                    f"INSERT INTO procedencia_campo ({', '.join(columnas)}) "
                    f"VALUES ({', '.join('?' * len(columnas))})",
                    (estado.tabla, estado.id, nombre, *(fila[c] for c in _COLUMNAS_PROCEDENCIA)))
            else:
                mutables = [c for c in _COLUMNAS_PROCEDENCIA if c not in _ORIGINALES]
                self.conn.execute(
                    f"UPDATE procedencia_campo SET {', '.join(f'{c} = ?' for c in mutables)} "
                    "WHERE tabla = ? AND fila_id = ? AND campo = ?",
                    (*(fila[c] for c in mutables), estado.tabla, estado.id, nombre))


def _motivo_de(origen: Origen, procedencia: Mapping[str, Any] | None) -> str | None:
    """En una orden de una persona, su motivo va en cada cambio: tambien al deshacer,
    y en lo que se recalcula por lo que ella cambio."""
    if not isinstance(origen, Persona) or procedencia is None:
        return None
    return (origen.motivo or "").strip() or None


def _factura_de(estado: _Fila) -> int | None:
    if estado.tabla == "factura":
        return estado.id
    if estado.tabla == "factura_relacion":
        return estado.valores.get("origen_id")
    return estado.valores.get("factura_id")


def _permiso(definicion: Campo, fila: Mapping[str, Any], *, corregir: bool) -> str | None:
    """El permiso para suplir o corregir un campo; el de un alias depende de a que apunta."""
    if definicion.tabla == "alias" and fila.get("tabla") in ("proveedor", "cliente"):
        return _ADMIN
    return definicion.permiso_corregir if corregir else definicion.permiso_suplir


def _permiso_alta(tabla: str, valores: Mapping[str, Any]) -> str | None:
    if tabla == "alias" and valores.get("tabla") in ("proveedor", "cliente"):
        return _ADMIN
    return PERMISO_ALTA.get(tabla)


@contextmanager
def orden(
    conn: sqlite3.Connection, origen: Origen, *, tipo: str, tabla: str | None = None,
    fila_id: int | None = None, factura_id: int | None = None,
    datos: Mapping[str, Any] | None = None,
) -> Iterator[Orden]:
    """Una orden: todo lo que se planifica dentro se escribe con un solo evento.

    Si la orden se deniega por permisos y es la transaccion de fuera, el
    intento denegado queda registrado despues del ROLLBACK.
    """
    with orden_auditada(conn):
        en_curso = Orden(conn, origen, tipo=tipo, tabla=tabla, fila_id=fila_id,
                         factura_id=factura_id, datos=datos)
        yield en_curso
        en_curso.escribir()


# ------------------------------------------------------------ atajos

def crear(conn: sqlite3.Connection, tabla: str, valores: Mapping[str, Any], origen: Origen,
          *, tipo: str | None = None, datos: Mapping[str, Any] | None = None) -> int:
    with orden(conn, origen, tipo=tipo or f"{tabla}_alta", datos=datos) as o:
        return o.crear(tabla, valores)


def fijar(conn: sqlite3.Connection, tabla: str, fila_id: int, valores: Mapping[str, Any],
          origen: Origen, *, tipo: str | None = None, rev_esperada: int | None = None,
          datos: Mapping[str, Any] | None = None) -> ResultadoOrden:
    with orden(conn, origen, tipo=tipo or "campos_fijados", tabla=tabla, fila_id=fila_id,
               datos=datos) as o:
        o.fijar(tabla, fila_id, valores, rev_esperada=rev_esperada)
    return o.resultado


def retirar(conn: sqlite3.Connection, tabla: str, fila_id: int, origen: Origen) -> ResultadoOrden:
    with orden(conn, origen, tipo=f"{tabla}_retirada", tabla=tabla, fila_id=fila_id) as o:
        o.retirar(tabla, fila_id)
    return o.resultado


def verificar_campos(conn: sqlite3.Connection, tabla: str, fila_id: int,
                     nombres: tuple[str, ...] | list[str], persona: Persona) -> ResultadoOrden:
    with orden(conn, persona, tipo="campo_verificado", tabla=tabla, fila_id=fila_id) as o:
        o.verificar(tabla, fila_id, tuple(nombres))
    return o.resultado


def recalcular(conn: sqlite3.Connection, tabla: str, fila_id: int, origen: Automatico,
               nombres: tuple[str, ...] | None = None) -> ResultadoOrden:
    with orden(conn, origen, tipo="campos_recalculados", tabla=tabla, fila_id=fila_id) as o:
        o.recalcular(tabla, fila_id, nombres)
    return o.resultado


def anadir_nota(conn: sqlite3.Connection, tabla: str, fila_id: int, texto: str,
                persona: Persona, *, datos: Mapping[str, Any] | None = None) -> int:
    """Una nota de una persona sobre una fila. Las notas solo se anaden."""
    if not (texto or "").strip():
        raise ValueError("una nota vacia no dice nada")
    with orden_auditada(conn):
        exigir(conn, persona.usuario_id, _SUPLIR, accion="anadir una nota")
        factura_id = fila_id if tabla == "factura" else None
        # La nota entra despues de su evento (la base lo exige), asi que su
        # foto se escribe antes, con lo que va a tener: es evidencia, y db
        # verificar la compara con la fila (almacen/evidencia.py).
        fila = {"tabla": tabla, "fila_id": fila_id, "texto": texto,
                "usuario_id": persona.usuario_id, "en": marca(reloj_de(conn).ahora())}
        evento = registrar(conn, tipo="nota_anadida", actor=persona.usuario_id,
                           usuario_id=persona.usuario_id, tabla=tabla, fila_id=fila_id,
                           factura_id=factura_id, peticion_id=persona.peticion_id,
                           datos={**(datos or {}), "fila": fila})
        cursor = conn.execute(
            "INSERT INTO nota (tabla, fila_id, texto, usuario_id, en, evento_id) "
            "VALUES (:tabla, :fila_id, :texto, :usuario_id, :en, :evento_id)",
            {**fila, "evento_id": evento})
        return int(cursor.lastrowid)


# ------------------------------------------------------------ lectura

def leer(conn: sqlite3.Connection, tabla: str, fila_id: int) -> dict[str, Any] | None:
    if tabla not in REGISTRO:
        raise ValueError(f"{tabla} no es una tabla controlada")
    fila = conn.execute(f"SELECT * FROM {tabla} WHERE id = ?", (fila_id,)).fetchone()
    return dict(fila) if fila is not None else None


def procedencia(conn: sqlite3.Connection, tabla: str, fila_id: int) -> dict[str, dict[str, Any]]:
    """La procedencia de cada campo de una fila, con los valores ya leidos del JSON."""
    resultado = {}
    for fila in conn.execute(
        "SELECT * FROM procedencia_campo WHERE tabla = ? AND fila_id = ? ORDER BY campo",
        (tabla, fila_id),
    ):
        datos = dict(fila)
        for clave in ("valor_actual", "valor_original", "valor_original_crudo", "valor_automatico"):
            datos[clave] = _de_json(datos[clave])
        resultado[fila["campo"]] = datos
    return resultado


@dataclass(frozen=True)
class EstadoCampo:
    """Las marcas de un campo para la vista de edicion manual (§11) y calidad (§14)."""

    fuente: str | None
    editado: bool
    suplementado: bool
    corregido: bool
    sin_resolver: bool
    dudoso: bool
    verificado: bool


def estado_campo(p: Mapping[str, Any] | None) -> EstadoCampo:
    """Lo que dice la procedencia de un campo (de procedencia()) sobre su estado.

    sin_resolver es la condicion de M1: un valor manual distinto del ultimo
    automatico, sin verificar. Un valor suplido donde lo automatico no dijo
    nada no esta sin resolver: nada lo contradice. Dudoso solo cuenta si el
    valor actual es el automatico (un valor de persona no es una lectura
    dudosa) y nadie lo ha verificado.
    """
    if p is None:
        return EstadoCampo(None, False, False, False, False, False, False)
    fuente = p["fuente"]
    verificado = p["verificado_rev"] is not None and p["verificado_rev"] == p["rev_campo"]
    manual = fuente in (Fuente.MANUAL_ENTRADA.value, Fuente.MANUAL_CORRECCION.value)
    sin_resolver = (manual and p["valor_automatico"] is not None
                    and p["valor_automatico"] != p["valor_actual"] and not verificado)
    return EstadoCampo(
        fuente=fuente, editado=manual,
        suplementado=fuente == Fuente.MANUAL_ENTRADA.value,
        corregido=fuente == Fuente.MANUAL_CORRECCION.value,
        sin_resolver=sin_resolver,
        dudoso=bool(p["dudoso"]) and not manual and not verificado,
        verificado=verificado,
    )


# ------------------------------------------------------------ verificacion

def verificar_controladas(conn: sqlite3.Connection) -> list[str]:
    """Que cada fila controlada sea lo que dice su historia, sin fiarse de los disparadores.

    Cada columna tiene que valer lo que dejo su ultimo cambio_campo, la rev
    de la fila tiene que ser la del ultimo cambio, y la procedencia de cada
    campo tiene que decir el mismo valor y la misma fuente, y ser entera la
    ultima foto que dejo un evento de ella (`verificar_procedencia`). Asi se
    ve una fila editada por detras (con los disparadores borrados), una
    metida sin su historia, una procedencia retocada para esconder un valor
    manual, un original reescrito o una verificacion inventada.
    """
    problemas: list[str] = []
    for tabla, campos in REGISTRO.items():
        ultimos: dict[tuple[int, str], sqlite3.Row] = {}
        revs: dict[int, int] = {}
        for c in conn.execute(
            "SELECT fila_id, campo, rev, valor_nuevo, fuente_nueva FROM cambio_campo "
            "WHERE tabla = ? ORDER BY id", (tabla,),
        ):
            ultimos[(c["fila_id"], c["campo"])] = c
            revs[c["fila_id"]] = max(revs.get(c["fila_id"], 0), c["rev"])
        procedencias = {
            (p["fila_id"], p["campo"]): p for p in conn.execute(
                "SELECT fila_id, campo, fuente, valor_actual FROM procedencia_campo "
                "WHERE tabla = ?",
                (tabla,))
        }
        existentes = set()
        for fila in conn.execute(f"SELECT * FROM {tabla} ORDER BY id"):
            existentes.add(fila["id"])
            if fila["id"] not in revs:
                problemas.append(f"{tabla} {fila['id']} no tiene historia: se ha metido por detras")
                continue
            if fila["rev"] != revs[fila["id"]]:
                problemas.append(
                    f"{tabla} {fila['id']}: rev {fila['rev']} y su ultimo cambio es la "
                    f"{revs[fila['id']]}")
            for nombre in campos:
                actual = _json(fila[nombre])
                ultimo = ultimos.get((fila["id"], nombre))
                esperado = None if ultimo is None else ultimo["valor_nuevo"]
                if esperado == "null":
                    esperado = None
                if actual != esperado:
                    problemas.append(
                        f"{tabla} {fila['id']}: {nombre} no es lo que dejo su ultimo cambio "
                        "(se ha modificado por detras)")
                p = procedencias.get((fila["id"], nombre))
                if p is not None and p["valor_actual"] != actual:
                    problemas.append(
                        f"{tabla} {fila['id']}: la procedencia de {nombre} no dice su valor")
                if p is not None and ultimo is not None and p["fuente"] != ultimo["fuente_nueva"]:
                    problemas.append(
                        f"{tabla} {fila['id']}: la procedencia de {nombre} no dice la fuente "
                        "de su ultimo cambio")
                if p is None and actual is not None:
                    problemas.append(
                        f"{tabla} {fila['id']}: {nombre} tiene valor y no tiene procedencia")
        for fila_id in sorted(set(revs) - existentes):
            problemas.append(f"{tabla} {fila_id} tiene historia y ya no existe: se ha borrado")
    return problemas + verificar_procedencia(conn)


def _fotos_de_procedencia(
    conn: sqlite3.Connection,
) -> dict[str, list[tuple[sqlite3.Row, dict[str, Any]]]]:
    """Cada foto de procedencia de la auditoria, por campo y en orden, con su evento."""
    fotos: dict[str, list[tuple[sqlite3.Row, dict[str, Any]]]] = {}
    for evento in conn.execute(
        "SELECT id, tipo, actor, usuario_id, datos_json FROM evento "
        "WHERE json_type(datos_json, ?) = 'object' ORDER BY id", (f"$.{FOTOS_PROCEDENCIA}",),
    ):
        for clave, foto in json.loads(evento["datos_json"])[FOTOS_PROCEDENCIA].items():
            fotos.setdefault(clave, []).append((evento, foto))
    return fotos


def verificar_procedencia(conn: sqlite3.Connection) -> list[str]:
    """Que cada procedencia sea la ultima foto suya que dejo un evento, y nada mas.

    Cada orden de campos.py pone en su evento la foto de cada procedencia que
    escribe, y el evento esta en la cadena. Asi, sin fiarse de los
    disparadores, se ve una procedencia metida o borrada por detras, una
    columna cambiada (el valor automatico, la marca de dudoso, quien
    verifico), un original que ya no es el de la primera foto, y una
    verificacion que no hizo la persona que dice: el evento en el que
    aparece tiene que ser de esa persona.
    """
    problemas: list[str] = []
    fotos = _fotos_de_procedencia(conn)
    vistas = set()
    for fila in conn.execute("SELECT * FROM procedencia_campo ORDER BY id"):
        clave = clave_procedencia(fila["tabla"], fila["fila_id"], fila["campo"])
        vistas.add(clave)
        historia = fotos.get(clave)
        if not historia:
            problemas.append(f"la procedencia de {clave} no tiene evento: se ha metido por detras")
            continue
        ultimo, foto = historia[-1]
        distintas = [c for c in _COLUMNAS_PROCEDENCIA if foto.get(c) != fila[c]]
        if distintas:
            problemas.append(
                f"la procedencia de {clave}: {', '.join(distintas)} no es lo que registro el "
                f"evento {ultimo['id']} (se ha modificado por detras)")
        primera = historia[0][1]
        if any(f.get(c) != primera.get(c) for _e, f in historia for c in _ORIGINALES):
            problemas.append(f"la procedencia de {clave}: el original cambio entre sus eventos")
        antes: tuple[Any, Any] = (None, None)
        for evento, f in historia:
            ahora = (f.get("verificado_por"), f.get("verificado_en"))
            if ahora[0] is not None and ahora != antes and (
                    evento["usuario_id"] != ahora[0] or evento["actor"] != ahora[0]):
                problemas.append(
                    f"la procedencia de {clave}: la verificacion del evento {evento['id']} "
                    f"no la hizo la persona {ahora[0]}")
            antes = ahora
    for clave in sorted(set(fotos) - vistas):
        problemas.append(
            f"la procedencia de {clave} la registro el evento {fotos[clave][0][0]['id']} "
            "y ya no existe: se ha borrado")
    return problemas
