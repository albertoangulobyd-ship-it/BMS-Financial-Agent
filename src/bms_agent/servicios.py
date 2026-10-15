"""Las ordenes de las personas (spec §6, servicios.py): editar, revisar, excepciones.

Cada cosa que una persona puede hacer desde la consola, la CLI o
POST /api/v2/acciones es una `Accion` tipada de `ACCIONES`, y todas pasan por
`ejecutar`, que hace siempre lo mismo y en este orden:

1. Comprueba los datos (cada parametro con su tipo; nada que no se espere).
2. Idempotencia: si la peticion (`peticion_id`) ya se aplico, no se repite y
   se dice; si el mismo id llega con otra orden, se rechaza.
3. Abre la transaccion de la orden. Dentro: la persona es una persona activa
   (nunca un usuario de sistema), tiene el permiso de la orden (tabla del §6),
   la orden trae su motivo donde hace falta y la fila esta en la rev que la
   persona vio (concurrencia optimista: si otra persona la cambio antes, es
   un Conflicto y no se pisa nada).
4. Escribe por campos.py (o por excepciones.py, revision.py, hallazgos.py y
   estados.py, que escriben sus propias tablas con la misma auditoria).
5. Recalcula todo (reglas, hallazgos, excepciones, estado y prioridad) en la
   misma transaccion.
6. Devuelve una `Diferencia`: los resultados de reglas que cambiaron, los
   hallazgos que se abrieron, cerraron o reabrieron, las revisiones que
   dejaron de valer, las prioridades que se movieron y los totales afectados.

Si algo falla en cualquier punto, no queda nada: ni la escritura, ni su
evento, ni el recalculo. Una denegacion de permiso si queda, como evento
denegado, despues del ROLLBACK.

Lo que no hay aqui, a proposito (spec §21): ninguna orden crea ni prepara una
factura, paga, aprueba un pago o presenta el BTW. Marcar una factura pagada
llega con los pagos (paso 7); el IBAN y su verificacion, con el registro de
cuentas (paso 5); el estado del BTW, con el paso 11.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from . import campos, estados, excepciones, hallazgos, revision
from .almacen.unidades import de_cent, de_e4, de_mil, de_pb, json_canonico, sha256_texto
from .campos import Conflicto, FaltaMotivo, Persona
from .dominio import FUENTES_MANUALES, Permiso
from .identidad import anadir_alias
from .permisos import PermisoDenegado, es_persona, exigir, orden_auditada

P = Permiso

ENTERO = "entero"
TEXTO = "texto"
FECHA = "fecha"
VALOR = "valor"
LISTA = "lista"
OBJETO = "objeto"


class AccionDesconocida(ValueError):
    """La orden pedida no existe."""


class DatosNoValidos(ValueError):
    """Los datos de la orden no tienen la forma que espera."""


class PeticionRepetida(ValueError):
    """El mismo peticion_id llega con otra orden, u otra persona: no es un reintento."""


@dataclass(frozen=True)
class Parametro:
    nombre: str
    tipo: str
    obligatorio: bool = True
    ayuda: str = ""


@dataclass
class Contexto:
    """Lo que tiene una orden mientras se ejecuta."""

    conn: sqlite3.Connection
    persona: Persona
    segunda_firma: Persona | None
    datos_evento: dict[str, Any]


@dataclass
class Hecho:
    """Lo que escribio una orden, antes del recalculo."""

    evento_id: int | None = None
    facturas: set[int] = field(default_factory=set)
    detalle: dict[str, Any] = field(default_factory=dict)
    hallazgos: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class Accion:
    """Una orden de una persona.

    `permiso` es el del §6. None en las que dependen del campo: rellenar un
    valor vacio pide anadir_informacion y corregir uno que existe
    editar_extraccion (lo decide campos.py, no quien edita); verificar o
    deshacer, el permiso de corregir ese campo. `motivo` dice si la orden
    lo pide siempre ("obligatorio"), nunca ("opcional") o segun el campo
    ("segun_campo": cambiar un valor que existe lo pide).
    """

    nombre: str
    permiso: str | None
    descripcion: str
    parametros: tuple[Parametro, ...]
    ejecutar: Callable[[Contexto, dict[str, Any]], Hecho]
    motivo: str = "opcional"
    rev: bool = False


# ------------------------------------------------------------ la diferencia

@dataclass
class Diferencia:
    """Lo que cambio con una orden. Es lo que la consola y la CLI ensenan."""

    accion: str
    evento_id: int | None = None
    repetida: bool = False
    ejecucion_id: int | None = None
    resultados: list[dict[str, Any]] = field(default_factory=list)
    hallazgos: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    revisiones_invalidadas: list[int] = field(default_factory=list)
    prioridades: list[dict[str, Any]] = field(default_factory=list)
    totales: list[dict[str, Any]] = field(default_factory=list)
    excepciones: dict[str, Any] = field(default_factory=dict)
    detalle: dict[str, Any] = field(default_factory=dict)

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)

    def lineas(self) -> list[str]:
        """La diferencia en castellano, linea a linea, para la CLI."""
        if self.repetida:
            return [f"Esta peticion ya se aplico (evento {self.evento_id}): no se repite."]
        if self.evento_id is None:
            return ["No cambia nada: los valores ya eran esos."]
        salida = [f"Hecho (evento {self.evento_id}, pasada {self.ejecucion_id})."]
        for clave, texto in (("abiertos", "abiertos"), ("cerrados", "cerrados"),
                             ("reabiertos", "reabiertos"), ("aceptados", "aceptados"),
                             ("cambios_evidencia", "con otra evidencia")):
            lista = self.hallazgos.get(clave) or []
            if lista:
                reglas = ", ".join(f"{h['regla']} ({h['tipo']})" for h in lista)
                salida.append(f"  hallazgos {texto}: {reglas}")
        if self.resultados:
            salida.append(f"  resultados de reglas que cambian: {len(self.resultados)}")
        for p in self.prioridades:
            salida.append(f"  prioridad de {p['entidad']} {p['entidad_id']}: "
                          f"{p['antes'] or '-'} -> {p['despues'] or '-'}")
        for f in self.revisiones_invalidadas:
            salida.append(f"  la revision de la factura {f} deja de valer")
        for t in self.totales:
            salida.append(f"  {t['entidad']} {t['id']} {t['campo']}: {t['antes']} -> "
                          f"{t['despues']}")
        if self.excepciones.get("creadas"):
            salida.append("  excepciones abiertas: "
                          + ", ".join(str(e) for e in self.excepciones["creadas"]))
        return salida


_GRUPO_TRANSICION = {
    "detectado": "abiertos", "reabierto": "reabiertos", "cerrado_automatico": "cerrados",
    "desaparecido": "cerrados", "resuelto": "cerrados", "aceptado": "aceptados",
    "cambio_evidencia": "cambios_evidencia",
}


def _foto_totales(conn: sqlite3.Connection) -> dict[int, tuple]:
    """Lo que entra en los totales de cada factura, para comparar antes y despues."""
    return {f[0]: tuple(f[1:]) for f in conn.execute(
        "SELECT id, sentido, proveedor_id, cliente_id, base_cent, iva_cent, total_cent, anulada, "
        "fusionada_en_id, moneda_doc FROM factura")}


_COLUMNAS_TOTAL = ("base_cent", "iva_cent", "total_cent")


def _cuenta(fila: tuple) -> bool:
    """Si una factura suma en los totales: ni anulada, ni fusionada, ni en otra moneda."""
    _sentido, _p, _c, _b, _i, _t, anulada, fusionada, moneda = fila
    return not anulada and fusionada is None and moneda is None


def _totales(antes: dict[int, tuple], despues: dict[int, tuple]) -> list[dict[str, Any]]:
    """Los totales que cambiaron: los de cada factura tocada y los de su proveedor o cliente."""
    salida: list[dict[str, Any]] = []
    partes: set[tuple[str, int]] = set()
    for factura_id in sorted(set(antes) | set(despues)):
        a, d = antes.get(factura_id), despues.get(factura_id)
        if a == d:
            continue
        for i, columna in enumerate(_COLUMNAS_TOTAL, start=3):
            va = a[i] if a and _cuenta(a) else None
            vd = d[i] if d and _cuenta(d) else None
            if va != vd:
                salida.append({"entidad": "factura", "id": factura_id, "campo": columna,
                               "antes": va, "despues": vd})
        for fila in (a, d):
            if fila is not None:
                if fila[1] is not None:
                    partes.add(("proveedor", fila[1]))
                if fila[2] is not None:
                    partes.add(("cliente", fila[2]))

    def suma(fotos: dict[int, tuple], parte: tuple[str, int], i: int) -> int:
        posicion = 1 if parte[0] == "proveedor" else 2
        return sum(f[i] or 0 for f in fotos.values() if f[posicion] == parte[1] and _cuenta(f))

    for parte in sorted(partes):
        for i, columna in ((3, "base_cent"), (5, "total_cent")):
            va, vd = suma(antes, parte, i), suma(despues, parte, i)
            if va != vd:
                salida.append({"entidad": parte[0], "id": parte[1], "campo": columna,
                               "antes": va, "despues": vd})
    return salida


def _diferencia(nombre: str, hecho: Hecho, recalculo: hallazgos.Diferencia | None,
                antes: dict[int, tuple], despues: dict[int, tuple]) -> Diferencia:
    diferencia = Diferencia(accion=nombre, evento_id=hecho.evento_id, detalle=hecho.detalle)
    grupos: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for h in hecho.hallazgos:
        grupos[_GRUPO_TRANSICION.get(h["tipo"], "otros")].append(h)
    if recalculo is not None:
        diferencia.ejecucion_id = recalculo.ejecucion_id
        diferencia.resultados = [asdict(c) for c in recalculo.cambios_evaluacion]
        for t in recalculo.transiciones:
            grupos[_GRUPO_TRANSICION.get(t.tipo, "otros")].append({
                "hallazgo_id": t.hallazgo_id, "regla": t.regla, "factura_id": t.factura_id,
                "clave": t.clave, "tipo": t.tipo, "causa_evento_id": t.causa_evento_id})
        if recalculo.estados is not None:
            diferencia.revisiones_invalidadas = list(recalculo.estados.revisiones_invalidadas)
            diferencia.prioridades = [asdict(p) for p in recalculo.estados.prioridades]
        if recalculo.excepciones is not None:
            diferencia.excepciones = {
                "creadas": list(recalculo.excepciones.creadas),
                "vinculos": [list(v) for v in recalculo.excepciones.vinculos]}
    diferencia.hallazgos = dict(grupos)
    diferencia.totales = _totales(antes, despues)
    return diferencia


# ------------------------------------------------------------ valores de entrada

_DECIMAL = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")
_SI = {"si", "sí", "true", "1", "verdadero"}
_NO = {"no", "false", "0", "falso"}


def valor_de_entrada(definicion: campos.Campo, valor: Any) -> Any:
    """El valor que escribe una persona, del tipo que espera campos.py.

    Los importes, cantidades, tarifas y tipos llegan como texto ("2902,79" o
    "2902.79", sin separador de miles: "2.902,79" seria ambiguo) o como
    entero; nunca como float, que ya habria perdido decimales.
    """
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    tipo, nombre = definicion.tipo, f"{definicion.tabla}.{definicion.nombre}"
    if tipo in (campos.CENT, campos.MIL, campos.E4, campos.PB):
        if isinstance(valor, bool) or isinstance(valor, float):
            raise DatosNoValidos(f"{nombre}: un importe se escribe como texto, no {valor!r}")
        if isinstance(valor, (int, Decimal)):
            return Decimal(valor)
        texto = str(valor).strip().replace(" ", "").replace(" ", "")
        if not _DECIMAL.match(texto):
            raise DatosNoValidos(f"{nombre}: {valor!r} no es un numero; se escribe sin "
                                 "separador de miles, como 2902,79")
        return Decimal(texto.replace(",", "."))
    if tipo in (campos.ENTERO, campos.REF):
        if isinstance(valor, bool):
            raise DatosNoValidos(f"{nombre}: se espera un entero")
        if isinstance(valor, int):
            return valor
        texto = str(valor).strip()
        if not re.fullmatch(r"[+-]?\d+", texto):
            raise DatosNoValidos(f"{nombre}: {valor!r} no es un entero")
        return int(texto)
    if tipo == campos.BOOL:
        if isinstance(valor, bool):
            return valor
        texto = str(valor).strip().lower()
        if texto in _SI:
            return True
        if texto in _NO:
            return False
        raise DatosNoValidos(f"{nombre}: se espera si o no, no {valor!r}")
    if tipo == campos.FECHA:
        try:
            return date.fromisoformat(str(valor).strip())
        except ValueError:
            raise DatosNoValidos(f"{nombre}: {valor!r} no es una fecha AAAA-MM-DD") from None
    if not isinstance(valor, str):
        raise DatosNoValidos(f"{nombre}: se espera texto, no {valor!r}")
    return valor


def de_columna(definicion: campos.Campo, valor: Any) -> Any:
    """Un valor tal como esta en la columna, de vuelta al tipo de entrada (deshacer)."""
    if valor is None:
        return None
    conversor = {campos.CENT: de_cent, campos.MIL: de_mil, campos.E4: de_e4,
                 campos.PB: de_pb}.get(definicion.tipo)
    if conversor is not None:
        return conversor(valor)
    if definicion.tipo == campos.BOOL:
        return bool(valor)
    return valor


def _coercionar(parametro: Parametro, valor: Any) -> Any:
    if valor is None:
        return None
    if parametro.tipo == ENTERO:
        if isinstance(valor, bool):
            raise DatosNoValidos(f"{parametro.nombre}: se espera un entero")
        if isinstance(valor, int):
            return valor
        if isinstance(valor, str) and re.fullmatch(r"[+-]?\d+", valor.strip()):
            return int(valor.strip())
        raise DatosNoValidos(f"{parametro.nombre}: {valor!r} no es un entero")
    if parametro.tipo == FECHA:
        try:
            return date.fromisoformat(str(valor).strip()).isoformat()
        except ValueError:
            raise DatosNoValidos(f"{parametro.nombre}: {valor!r} no es una fecha AAAA-MM-DD") from None
    if parametro.tipo == TEXTO:
        if not isinstance(valor, str):
            raise DatosNoValidos(f"{parametro.nombre}: se espera texto")
        return valor
    if parametro.tipo == LISTA:
        if not isinstance(valor, list):
            raise DatosNoValidos(f"{parametro.nombre}: se espera una lista")
        return valor
    if parametro.tipo == OBJETO:
        if not isinstance(valor, dict):
            raise DatosNoValidos(f"{parametro.nombre}: se espera un objeto")
        return valor
    if isinstance(valor, float):
        raise DatosNoValidos(f"{parametro.nombre}: un numero con decimales se escribe como texto")
    return valor


def _validar(accion: Accion, datos: Mapping[str, Any]) -> dict[str, Any]:
    conocidos = {p.nombre for p in accion.parametros}
    sobran = sorted(set(datos) - conocidos)
    if sobran:
        raise DatosNoValidos(f"{accion.nombre} no lleva {', '.join(sobran)}")
    salida = {}
    for parametro in accion.parametros:
        valor = _coercionar(parametro, datos.get(parametro.nombre))
        if parametro.obligatorio and valor is None:
            raise DatosNoValidos(f"{accion.nombre} necesita {parametro.nombre}")
        salida[parametro.nombre] = valor
    return salida


# ------------------------------------------------------------ ayudas

_TABLAS_DE_FACTURA = ("factura", "factura_linea", "factura_imputacion", "factura_iva",
                      "factura_referencia")
# Lo que tiene su propia orden: alli se comprueba lo que la edicion suelta no.
_CAMPOS_CON_ORDEN = {
    ("factura", "anulada"): "anular_factura",
    ("factura", "fusionada_en_id"): "fusionar_factura",
    ("factura_imputacion", "objeto_id"): "cambiar_objeto",
    ("factura_imputacion", "recurso_id"): "cambiar_objeto",
    ("factura_imputacion", "orden_compra_id"): "la imputacion a una PO (paso 9)",
    ("factura_referencia", "orden_compra_id"): "la imputacion a una PO (paso 9)",
    ("factura_referencia", "clase"): "cambiar_po",
    ("proveedor", "telefono_verificacion"): "el telefono de verificacion (paso 5)",
}
_MAESTROS = ("proveedor", "cliente", "contacto")


def _factura_de_fila(conn: sqlite3.Connection, tabla: str, fila_id: int) -> int | None:
    if tabla == "factura":
        return fila_id
    if tabla in _TABLAS_DE_FACTURA:
        fila = conn.execute(f"SELECT factura_id FROM {tabla} WHERE id = ?", (fila_id,)).fetchone()
        return fila[0] if fila else None
    return None


def _rev(conn: sqlite3.Connection, tabla: str, fila_id: int) -> int:
    fila = conn.execute(f"SELECT rev FROM {tabla} WHERE id = ?", (fila_id,)).fetchone()
    if fila is None:
        raise LookupError(f"no hay {tabla} {fila_id}")
    return int(fila[0])


def _comprobar_rev(conn: sqlite3.Connection, tabla: str, fila_id: int, rev: int) -> None:
    actual = _rev(conn, tabla, fila_id)
    if actual != rev:
        raise Conflicto(f"{tabla} {fila_id} esta en la rev {actual} y se edito sobre la {rev}: "
                        "vuelve a cargarla")


def _motivo(ctx: Contexto, que: str) -> str:
    motivo = (ctx.persona.motivo or "").strip()
    if not motivo:
        raise FaltaMotivo(f"{que} pide un motivo")
    return motivo


# ------------------------------------------------------------ campos

def _fijar_campo(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    """Rellenar un valor que falta o corregir uno que se leyo mal (§10)."""
    tabla, fila_id, nombre = d["tabla"], d["fila_id"], d["campo"]
    if tabla not in _TABLAS_DE_FACTURA:
        raise DatosNoValidos(f"fijar_campo edita las facturas y sus lineas; {tabla} se cambia "
                             "con corregir_maestro" if tabla in _MAESTROS
                             else f"{tabla} no se edita desde aqui")
    otra = _CAMPOS_CON_ORDEN.get((tabla, nombre))
    if otra is not None:
        raise DatosNoValidos(f"{tabla}.{nombre} se cambia con {otra}")
    definicion = campos.campo(tabla, nombre)
    valor = valor_de_entrada(definicion, d["valor"])
    resultado = campos.fijar(ctx.conn, tabla, fila_id, {nombre: valor}, ctx.persona,
                             tipo="campo_fijado", rev_esperada=d["rev"], datos=ctx.datos_evento)
    efecto = resultado.de(tabla, fila_id, nombre)
    return Hecho(resultado.evento_id, {_factura_de_fila(ctx.conn, tabla, fila_id)} - {None},
                 {"efecto": efecto.accion if efecto else None,
                  "fuente": efecto.fuente if efecto else None})


def _corregir_maestro(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    """Corregir un proveedor, un cliente o un contacto que no viene de Exact ni de TRNSPRNT."""
    tabla, fila_id, nombre = d["tabla"], d["fila_id"], d["campo"]
    if tabla not in _MAESTROS:
        raise DatosNoValidos(f"corregir_maestro es para {', '.join(_MAESTROS)}")
    otra = _CAMPOS_CON_ORDEN.get((tabla, nombre))
    if otra is not None:
        raise DatosNoValidos(f"{tabla}.{nombre} se cambia con {otra}")
    definicion = campos.campo(tabla, nombre)
    valor = valor_de_entrada(definicion, d["valor"])
    resultado = campos.fijar(ctx.conn, tabla, fila_id, {nombre: valor}, ctx.persona,
                             tipo="maestro_corregido", rev_esperada=d["rev"],
                             datos=ctx.datos_evento)
    if resultado.evento_id is not None:
        from .ingesta import reconciliar_referencias

        reconciliar_referencias(ctx.conn)
    return Hecho(resultado.evento_id)


def _verificar_campo(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    """Dar por bueno el valor de un campo (lo deja verificado para su rev)."""
    tabla, fila_id, nombre = d["tabla"], d["fila_id"], d["campo"]
    if tabla not in (*_TABLAS_DE_FACTURA, *_MAESTROS):
        raise DatosNoValidos(f"{tabla} no tiene campos que verificar aqui")
    _comprobar_rev(ctx.conn, tabla, fila_id, d["rev"])
    with campos.orden(ctx.conn, ctx.persona, tipo="campo_verificado", tabla=tabla,
                      fila_id=fila_id, datos=ctx.datos_evento) as o:
        o.verificar(tabla, fila_id, (nombre,))
    return Hecho(o.resultado.evento_id, {_factura_de_fila(ctx.conn, tabla, fila_id)} - {None})


def _revertir_campo(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    """Deshacer un cambio manual: el campo vuelve a su valor automatico (o se vacia)."""
    tabla, fila_id, nombre = d["tabla"], d["fila_id"], d["campo"]
    if tabla not in (*_TABLAS_DE_FACTURA, *_MAESTROS):
        raise DatosNoValidos(f"{tabla} no tiene campos que deshacer aqui")
    _motivo(ctx, "deshacer un cambio")
    procedencia = campos.procedencia(ctx.conn, tabla, fila_id).get(nombre)
    if procedencia is None or procedencia["fuente"] not in FUENTES_MANUALES:
        raise DatosNoValidos(f"{tabla}.{nombre} no tiene un cambio manual que deshacer")
    definicion = campos.campo(tabla, nombre)
    automatico = (procedencia["valor_automatico"] if procedencia["fuente_automatica"] is not None
                  else None)
    resultado = campos.fijar(ctx.conn, tabla, fila_id,
                             {nombre: de_columna(definicion, automatico)}, ctx.persona,
                             tipo="campo_revertido", rev_esperada=d["rev"],
                             datos=ctx.datos_evento)
    return Hecho(resultado.evento_id, {_factura_de_fila(ctx.conn, tabla, fila_id)} - {None})


def _anadir_nota(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    tabla = d["tabla"] or "factura"
    if tabla not in ("factura", "excepcion"):
        raise DatosNoValidos("una nota es de una factura o de una excepcion")
    if ctx.conn.execute(f"SELECT 1 FROM {tabla} WHERE id = ?", (d["fila_id"],)).fetchone() is None:
        raise LookupError(f"no hay {tabla} {d['fila_id']}")
    nota = campos.anadir_nota(ctx.conn, tabla, d["fila_id"], d["texto"], ctx.persona,
                              datos=ctx.datos_evento)
    evento = ctx.conn.execute("SELECT evento_id FROM nota WHERE id = ?", (nota,)).fetchone()[0]
    return Hecho(evento, {d["fila_id"]} if tabla == "factura" else set(), {"nota_id": nota})


def _cambiar_objeto(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    """Imputar una linea a otro Objeto (y, si se dice, a otro recurso)."""
    conn = ctx.conn
    imputacion = conn.execute("SELECT * FROM factura_imputacion WHERE id = ?",
                              (d["imputacion_id"],)).fetchone()
    if imputacion is None:
        raise LookupError(f"no hay imputacion {d['imputacion_id']}")
    if imputacion["retirada_en"] is not None:
        raise DatosNoValidos(f"la imputacion {d['imputacion_id']} esta retirada")
    valores: dict[str, Any] = {"objeto_id": d["objeto_id"]}
    if d["objeto_id"] is not None and conn.execute(
            "SELECT 1 FROM objeto WHERE id = ?", (d["objeto_id"],)).fetchone() is None:
        raise LookupError(f"no hay Objeto {d['objeto_id']}")
    if d["recurso_id"] is not None:
        if conn.execute("SELECT 1 FROM recurso WHERE id = ?", (d["recurso_id"],)).fetchone() is None:
            raise LookupError(f"no hay recurso {d['recurso_id']}")
        valores["recurso_id"] = d["recurso_id"]
    resultado = campos.fijar(conn, "factura_imputacion", d["imputacion_id"], valores,
                             ctx.persona, tipo="objeto_cambiado", rev_esperada=d["rev"],
                             datos=ctx.datos_evento)
    return Hecho(resultado.evento_id, {imputacion["factura_id"]})


def _anadir_alias(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    """Un nombre impreso mas con el que se reconoce un Objeto o un recurso."""
    from .ingesta import reconciliar_referencias

    if d["tabla"] not in ("objeto", "recurso"):
        raise DatosNoValidos("aqui se anaden alias de Objetos y recursos; los de proveedores y "
                             "clientes son maestros (admin)")
    if ctx.conn.execute(f"SELECT 1 FROM {d['tabla']} WHERE id = ?",
                        (d["fila_id"],)).fetchone() is None:
        raise LookupError(f"no hay {d['tabla']} {d['fila_id']}")
    antes = ctx.conn.execute("SELECT coalesce(max(id), 0) FROM evento").fetchone()[0]
    alias_id = anadir_alias(ctx.conn, d["tabla"], d["alias"], d["fila_id"], ctx.persona,
                            datos=ctx.datos_evento)
    evento = ctx.conn.execute("SELECT max(id) FROM evento").fetchone()[0]
    if evento == antes:
        return Hecho(None, detalle={"alias_id": alias_id, "imputaciones_resueltas": 0})
    resueltas = reconciliar_referencias(ctx.conn)
    return Hecho(evento, detalle={"alias_id": alias_id, "imputaciones_resueltas": resueltas})


def _cambiar_po(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    """Decir que una referencia impresa es (o no es) un numero de PO."""
    referencia = ctx.conn.execute("SELECT factura_id FROM factura_referencia WHERE id = ?",
                                  (d["referencia_id"],)).fetchone()
    if referencia is None:
        raise LookupError(f"no hay referencia {d['referencia_id']}")
    resultado = campos.fijar(ctx.conn, "factura_referencia", d["referencia_id"],
                             {"clase": d["clase"]}, ctx.persona, tipo="referencia_clasificada",
                             rev_esperada=d["rev"], datos=ctx.datos_evento)
    return Hecho(resultado.evento_id, {referencia["factura_id"]})


# ------------------------------------------------------------ lineas

_CAMPOS_LINEA_NUEVA = ("descripcion_doc", "objeto_doc", "recurso_doc", "unidad_doc",
                       "tipo_turno_doc", "fecha_inicio", "fecha_fin", "fecha_trabajo",
                       "cantidad_mil", "tarifa_e4", "importe_cent", "tipo_iva_pb")


def _excluir_linea(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    _motivo(ctx, "excluir una linea")
    _comprobar_rev(ctx.conn, "factura_linea", d["linea_id"], d["rev"])
    with campos.orden(ctx.conn, ctx.persona, tipo="linea_excluida", tabla="factura_linea",
                      fila_id=d["linea_id"], datos=ctx.datos_evento) as o:
        o.retirar("factura_linea", d["linea_id"])
    return Hecho(o.resultado.evento_id,
                 {_factura_de_fila(ctx.conn, "factura_linea", d["linea_id"])} - {None})


def _anadir_linea(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    """Una linea que esta en el papel y la extraccion no trajo, con su imputacion."""
    conn = ctx.conn
    _motivo(ctx, "anadir una linea")
    factura_id = d["factura_id"]
    _comprobar_rev(conn, "factura", factura_id, d["rev"])
    sobran = sorted(set(d["valores"]) - set(_CAMPOS_LINEA_NUEVA))
    if sobran:
        raise DatosNoValidos(f"una linea nueva no lleva {', '.join(sobran)}")
    valores = {n: valor_de_entrada(campos.campo("factura_linea", n), v)
               for n, v in d["valores"].items()}
    orden_ = conn.execute("SELECT coalesce(max(orden), 0) + 1 FROM factura_linea "
                          "WHERE factura_id = ?", (factura_id,)).fetchone()[0]
    with campos.orden(conn, ctx.persona, tipo="linea_anadida", tabla="factura",
                      fila_id=factura_id, factura_id=factura_id, datos=ctx.datos_evento) as o:
        linea = o.crear("factura_linea", {"factura_id": factura_id, "orden": orden_, **valores})
        imputacion = o.crear("factura_imputacion", {"factura_id": factura_id, "linea_id": linea})
    return Hecho(o.resultado.evento_id, {factura_id},
                 {"linea_id": linea, "imputacion_id": imputacion})


def _dividir_linea(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    """Repartir una linea entre varios Objetos: se retira su imputacion y se crean otras.

    Las partes tienen que sumar el importe de la linea (I1): una division que
    pierde o inventa dinero no entra.
    """
    conn = ctx.conn
    _motivo(ctx, "dividir una linea")
    linea = conn.execute("SELECT * FROM factura_linea WHERE id = ?", (d["linea_id"],)).fetchone()
    if linea is None:
        raise LookupError(f"no hay linea {d['linea_id']}")
    _comprobar_rev(conn, "factura_linea", d["linea_id"], d["rev"])
    if linea["retirada_en"] is not None:
        raise DatosNoValidos(f"la linea {d['linea_id']} esta excluida")
    if linea["importe_cent"] is None:
        raise DatosNoValidos("una linea sin importe no se puede repartir")
    partes = d["partes"]
    if len(partes) < 2:
        raise DatosNoValidos("dividir es repartir en dos partes o mas")
    definicion = {n: campos.campo("factura_imputacion", n)
                  for n in ("objeto_id", "importe_cent", "horas_mil")}
    nuevas = []
    for i, parte in enumerate(partes):
        if not isinstance(parte, dict) or set(parte) - {"objeto_id", "importe", "horas"}:
            raise DatosNoValidos(f"la parte {i + 1} lleva objeto_id, importe y, si quiere, horas")
        valores = {"objeto_id": valor_de_entrada(definicion["objeto_id"], parte.get("objeto_id")),
                   "importe_cent": valor_de_entrada(definicion["importe_cent"],
                                                    parte.get("importe"))}
        if parte.get("horas") is not None:
            valores["horas_mil"] = valor_de_entrada(definicion["horas_mil"], parte["horas"])
        if valores["importe_cent"] is None:
            raise DatosNoValidos(f"la parte {i + 1} no dice su importe")
        nuevas.append(valores)
    suma = sum(campos.a_columna(definicion["importe_cent"], v["importe_cent"]) for v in nuevas)
    if suma != linea["importe_cent"]:
        raise DatosNoValidos(f"las partes suman {de_cent(suma)} y la linea es de "
                             f"{de_cent(linea['importe_cent'])}")
    activas = [f[0] for f in conn.execute(
        "SELECT id FROM factura_imputacion WHERE linea_id = ? AND retirada_en IS NULL",
        (d["linea_id"],))]
    with campos.orden(conn, ctx.persona, tipo="linea_dividida", tabla="factura_linea",
                      fila_id=d["linea_id"], factura_id=linea["factura_id"],
                      datos=ctx.datos_evento) as o:
        for imputacion in activas:
            o.retirar("factura_imputacion", imputacion)
        creadas = [o.crear("factura_imputacion", {"factura_id": linea["factura_id"],
                                                  "linea_id": d["linea_id"], **valores})
                   for valores in nuevas]
    return Hecho(o.resultado.evento_id, {linea["factura_id"]}, {"imputaciones": creadas})


# ------------------------------------------------------------ anular y fusionar

def _anular_factura(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    """Anular una factura que no se paga ni se cuenta (no emite ningun abono)."""
    _motivo(ctx, "anular una factura")
    resultado = campos.fijar(ctx.conn, "factura", d["factura_id"], {"anulada": True},
                             ctx.persona, tipo="factura_anulada", rev_esperada=d["rev"],
                             datos=ctx.datos_evento)
    return Hecho(resultado.evento_id, {d["factura_id"]})


def _fusionar_factura(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    """Fusionar un reenvio en su factura: sale de los totales y su B2 queda desaparecido.

    Quien fusiona cierra en la misma orden el B2 que la fusion deja
    desaparecido, si tiene resolver_aviso; si no, queda para quien lo tenga.
    """
    _motivo(ctx, "fusionar una factura")
    resultado = campos.fijar(ctx.conn, "factura", d["factura_id"],
                             {"fusionada_en_id": d["destino_id"]}, ctx.persona,
                             tipo="factura_fusionada", rev_esperada=d["rev"],
                             datos=ctx.datos_evento)
    return Hecho(resultado.evento_id, {d["factura_id"], d["destino_id"]},
                 {"cerrar_b2": [d["factura_id"], d["destino_id"]]})


# ------------------------------------------------------------ revision

def _marcar_revisada(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    revision_id = revision.marcar_revisada(ctx.conn, ctx.persona, d["factura_id"],
                                           huella=d["huella"], nota=ctx.persona.motivo,
                                           datos=ctx.datos_evento)
    fila = ctx.conn.execute("SELECT evento_id, autorrevisada FROM revision WHERE id = ?",
                            (revision_id,)).fetchone()
    return Hecho(fila[0], {d["factura_id"]},
                 {"revision_id": revision_id, "autorrevisada": bool(fila[1]),
                  "etiqueta": "revisada por una persona"})


def _devolver_factura(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    revision_id = revision.devolver(ctx.conn, ctx.persona, d["factura_id"],
                                    nota=ctx.persona.motivo or "", huella=d["huella"],
                                    datos=ctx.datos_evento)
    evento = ctx.conn.execute("SELECT evento_id FROM revision WHERE id = ?",
                              (revision_id,)).fetchone()[0]
    return Hecho(evento, {d["factura_id"]}, {"revision_id": revision_id})


# ------------------------------------------------------------ excepciones y avisos

def _factura_de_excepcion(conn: sqlite3.Connection, excepcion_id: int) -> set[int]:
    fila = conn.execute("SELECT factura_id FROM excepcion WHERE id = ?", (excepcion_id,)).fetchone()
    return {fila[0]} if fila and fila[0] is not None else set()


def _crear_excepcion(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    excepcion_id = excepciones.crear(ctx.conn, ctx.persona, tabla=d["tabla"] or "factura",
                                     fila_id=d["fila_id"], titulo=d["titulo"],
                                     datos=ctx.datos_evento)
    evento = ctx.conn.execute("SELECT max(id) FROM evento").fetchone()[0]
    return Hecho(evento, _factura_de_excepcion(ctx.conn, excepcion_id),
                 {"excepcion_id": excepcion_id})


def _asignar_excepcion(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    evento = excepciones.asignar(ctx.conn, ctx.persona, d["excepcion_id"],
                                 responsable_id=d["responsable_id"], rev=d["rev"],
                                 datos=ctx.datos_evento)
    return Hecho(evento, _factura_de_excepcion(ctx.conn, d["excepcion_id"]))


def _esperar_externo(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    evento = excepciones.esperar(ctx.conn, ctx.persona, d["excepcion_id"],
                                 esperando_a=d["esperando_a"],
                                 fecha_seguimiento=d["fecha_seguimiento"], rev=d["rev"],
                                 datos=ctx.datos_evento)
    fila = ctx.conn.execute("SELECT fecha_seguimiento FROM excepcion WHERE id = ?",
                            (d["excepcion_id"],)).fetchone()
    return Hecho(evento, _factura_de_excepcion(ctx.conn, d["excepcion_id"]),
                 {"fecha_seguimiento": fila[0]})


def _resolver_excepcion(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    evento = excepciones.resolver(ctx.conn, ctx.persona, d["excepcion_id"],
                                  resolucion=d["resolucion"],
                                  notas=ctx.persona.motivo or "", rev=d["rev"],
                                  datos=ctx.datos_evento)
    return Hecho(evento, _factura_de_excepcion(ctx.conn, d["excepcion_id"]))


def _comprobar_huella_hallazgo(conn: sqlite3.Connection, hallazgo_id: int,
                               huella: str | None) -> sqlite3.Row:
    fila = conn.execute("SELECT * FROM hallazgo WHERE id = ?", (hallazgo_id,)).fetchone()
    if fila is None:
        raise LookupError(f"no hay hallazgo {hallazgo_id}")
    if huella is not None and fila["huella"] != huella:
        raise Conflicto(f"la evidencia del hallazgo {hallazgo_id} cambio desde que se cargo: "
                        "vuelve a mirarla antes de decidir")
    return fila


def _cerrar_hallazgo(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    """Cerrar un hallazgo cuya condicion ha desaparecido (el unico cierre de un pegajoso)."""
    fila = _comprobar_huella_hallazgo(ctx.conn, d["hallazgo_id"], d["huella"])
    hallazgos.resolver(ctx.conn, d["hallazgo_id"], ctx.persona, datos=ctx.datos_evento)
    evento = ctx.conn.execute("SELECT max(id) FROM evento").fetchone()[0]
    return Hecho(evento, {fila["factura_id"]} - {None}, hallazgos=[{
        "hallazgo_id": fila["id"], "regla": fila["regla"], "factura_id": fila["factura_id"],
        "clave": fila["clave"], "tipo": "resuelto", "causa_evento_id": evento}])


def _anular_hallazgo(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    """Aceptar la evidencia de un hallazgo que se puede anular, con motivo y, si hace falta,
    la segunda firma de otra persona (que se identifica con su propio token)."""
    fila = _comprobar_huella_hallazgo(ctx.conn, d["hallazgo_id"], d["huella"])
    anulacion = hallazgos.anular(ctx.conn, d["hallazgo_id"], ctx.persona,
                                 vigente_hasta=d["vigente_hasta"],
                                 segunda_firma=ctx.segunda_firma, datos=ctx.datos_evento)
    evento = ctx.conn.execute("SELECT evento_id, autoaprobada FROM anulacion WHERE id = ?",
                              (anulacion,)).fetchone()
    return Hecho(evento[0], {fila["factura_id"]} - {None},
                 {"anulacion_id": anulacion, "autoaprobada": bool(evento[1])},
                 hallazgos=[{"hallazgo_id": fila["id"], "regla": fila["regla"],
                             "factura_id": fila["factura_id"], "clave": fila["clave"],
                             "tipo": "aceptado", "causa_evento_id": evento[0]}])


def _subir_prioridad(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    subida = estados.subir_prioridad(ctx.conn, ctx.persona, entidad=d["entidad"] or "factura",
                                     entidad_id=d["entidad_id"], nivel=d["nivel"],
                                     hasta=d["hasta"], datos=ctx.datos_evento)
    evento = ctx.conn.execute("SELECT evento_id FROM prioridad_manual WHERE id = ?",
                              (subida,)).fetchone()[0]
    facturas = {d["entidad_id"]} if (d["entidad"] or "factura") == "factura" else set()
    return Hecho(evento, facturas, {"subida_id": subida})


def _recalcular(ctx: Contexto, d: dict[str, Any]) -> Hecho:
    """Volver a pasar las reglas sin cambiar nada (lo hace tambien cada orden)."""
    return Hecho(None, detalle={"recalcular": True})


# ------------------------------------------------------------ el catalogo

def _p(nombre: str, tipo: str = ENTERO, obligatorio: bool = True, ayuda: str = "") -> Parametro:
    return Parametro(nombre, tipo, obligatorio, ayuda)


_MOTIVO = _p("motivo", TEXTO, False, "por que (lo piden las correcciones y las decisiones)")
_CAMPO = (_p("tabla", TEXTO), _p("fila_id"), _p("campo", TEXTO))

ACCIONES: dict[str, Accion] = {a.nombre: a for a in (
    Accion("fijar_campo", None,
           "Rellenar un valor que falta o corregir uno mal extraido de una factura o una linea "
           "(periodo, horas, tarifas, importes, contraparte...).",
           (*_CAMPO, _p("valor", VALOR, False), _p("rev"), _MOTIVO),
           _fijar_campo, motivo="segun_campo", rev=True),
    Accion("verificar_campo", None,
           "Dar por bueno el valor actual de un campo; lo verifica otra persona si hay dos.",
           (*_CAMPO, _p("rev"), _MOTIVO), _verificar_campo, rev=True),
    Accion("revertir_campo", None,
           "Deshacer un cambio manual: el campo vuelve a su valor automatico.",
           (*_CAMPO, _p("rev"), _MOTIVO), _revertir_campo, motivo="obligatorio", rev=True),
    Accion("anadir_nota", P.ANADIR_INFORMACION.value,
           "Una nota interna en una factura o una excepcion.",
           (_p("tabla", TEXTO, False), _p("fila_id"), _p("texto", TEXTO)), _anadir_nota),
    Accion("cambiar_objeto", P.CAMBIAR_OBJETO.value,
           "Imputar una linea a otro Objeto (y recurso).",
           (_p("imputacion_id"), _p("objeto_id", ENTERO, False), _p("recurso_id", ENTERO, False),
            _p("rev"), _MOTIVO), _cambiar_objeto, motivo="segun_campo", rev=True),
    Accion("anadir_alias", P.CAMBIAR_OBJETO.value,
           "Un nombre impreso mas para un Objeto o un recurso.",
           (_p("tabla", TEXTO), _p("fila_id"), _p("alias", TEXTO)), _anadir_alias),
    Accion("cambiar_po", P.CAMBIAR_PO.value,
           "Decir si una referencia impresa es un numero de PO (u otra clase).",
           (_p("referencia_id"), _p("clase", TEXTO), _p("rev"), _MOTIVO), _cambiar_po,
           motivo="segun_campo", rev=True),
    Accion("excluir_linea", P.EDITAR_EXTRACCION.value,
           "Excluir una linea (se retira, no se borra; su imputacion con ella).",
           (_p("linea_id"), _p("rev"), _MOTIVO), _excluir_linea, motivo="obligatorio", rev=True),
    Accion("anadir_linea", P.EDITAR_EXTRACCION.value,
           "Anadir una linea que esta en el papel y la extraccion no trajo.",
           (_p("factura_id"), _p("valores", OBJETO), _p("rev"), _MOTIVO), _anadir_linea,
           motivo="obligatorio", rev=True),
    Accion("dividir_linea", P.EDITAR_EXTRACCION.value,
           "Repartir una linea entre varios Objetos (las partes suman la linea).",
           (_p("linea_id"), _p("partes", LISTA), _p("rev"), _MOTIVO), _dividir_linea,
           motivo="obligatorio", rev=True),
    Accion("corregir_maestro", P.ADMIN.value,
           "Corregir un proveedor, cliente o contacto que no viene de Exact ni de TRNSPRNT.",
           (*_CAMPO, _p("valor", VALOR, False), _p("rev"), _MOTIVO), _corregir_maestro,
           motivo="segun_campo", rev=True),
    Accion("anular_factura", P.ANULAR_ACREDITAR.value,
           "Anular una factura: no se paga ni se cuenta (no emite ningun abono).",
           (_p("factura_id"), _p("rev"), _MOTIVO), _anular_factura, motivo="obligatorio",
           rev=True),
    Accion("fusionar_factura", P.ANULAR_ACREDITAR.value,
           "Fusionar un reenvio duplicado en su factura.",
           (_p("factura_id"), _p("destino_id"), _p("rev"), _MOTIVO), _fusionar_factura,
           motivo="obligatorio", rev=True),
    Accion("marcar_revisada", P.REVISAR_FACTURA.value,
           "Dar una factura por revisada (no aprueba ningun pago).",
           (_p("factura_id"), _p("huella", TEXTO), _MOTIVO), _marcar_revisada),
    Accion("devolver_factura", P.REVISAR_FACTURA.value,
           "Devolver una factura con una nota que dice por que.",
           (_p("factura_id"), _p("huella", TEXTO, False), _MOTIVO), _devolver_factura,
           motivo="obligatorio"),
    Accion("crear_excepcion", P.RESOLVER_AVISO.value,
           "Abrir a mano una excepcion sobre una factura.",
           (_p("tabla", TEXTO, False), _p("fila_id"), _p("titulo", TEXTO), _MOTIVO),
           _crear_excepcion),
    Accion("asignar_excepcion", P.RESOLVER_AVISO.value,
           "Poner a una persona a cargo de una excepcion.",
           (_p("excepcion_id"), _p("responsable_id"), _p("rev"), _MOTIVO), _asignar_excepcion,
           rev=True),
    Accion("esperar_externo", P.RESOLVER_AVISO.value,
           "Dejar una excepcion esperando a alguien de fuera, con fecha de seguimiento.",
           (_p("excepcion_id"), _p("esperando_a", TEXTO), _p("fecha_seguimiento", FECHA, False),
            _p("rev"), _MOTIVO), _esperar_externo, rev=True),
    Accion("resolver_excepcion", P.RESOLVER_AVISO.value,
           "Resolver una excepcion, con su resolucion y sus notas.",
           (_p("excepcion_id"), _p("resolucion", TEXTO), _p("rev"), _MOTIVO),
           _resolver_excepcion, motivo="obligatorio", rev=True),
    Accion("cerrar_hallazgo", P.RESOLVER_AVISO.value,
           "Cerrar un hallazgo cuya condicion ha desaparecido.",
           (_p("hallazgo_id"), _p("huella", TEXTO, False), _MOTIVO), _cerrar_hallazgo,
           motivo="obligatorio"),
    Accion("anular_hallazgo", P.ANULAR_AVISO.value,
           "Anular un hallazgo de una regla que lo admite (motivo de 10 caracteres o mas).",
           (_p("hallazgo_id"), _p("huella", TEXTO), _p("vigente_hasta", FECHA, False), _MOTIVO),
           _anular_hallazgo, motivo="obligatorio"),
    Accion("subir_prioridad", P.RESOLVER_AVISO.value,
           "Subir la prioridad de algo (solo se sube; nunca a bloqueada).",
           (_p("entidad", TEXTO, False), _p("entidad_id"), _p("nivel", TEXTO),
            _p("hasta", FECHA, False), _MOTIVO), _subir_prioridad, motivo="obligatorio"),
    Accion("recalcular", P.VER_FACTURAS.value,
           "Volver a pasar las reglas (cada orden ya lo hace al terminar).",
           (), _recalcular),
)}


# ------------------------------------------------------------ ejecutar

def huella_peticion(nombre: str, datos: Mapping[str, Any], motivo: str | None) -> str:
    """Lo que identifica el contenido de una peticion: la misma orden con los mismos datos."""
    return sha256_texto(json_canonico({"accion": nombre, "datos": dict(datos),
                                       "motivo": motivo}))


def _ya_aplicada(conn: sqlite3.Connection, peticion_id: str, usuario_id: int,
                 huella: str) -> int | None:
    fila = conn.execute("SELECT id, usuario_id, json_extract(datos_json, '$.peticion.sha256') "
                        "FROM evento WHERE peticion_id = ? AND resultado = 'ok'",
                        (peticion_id,)).fetchone()
    if fila is None:
        return None
    if fila[1] != usuario_id or fila[2] != huella:
        raise PeticionRepetida(f"la peticion {peticion_id} ya se uso para otra orden")
    return int(fila[0])


def _exigir_persona(conn: sqlite3.Connection, usuario_id: int | None, accion: str) -> None:
    """Toda orden de aqui es de una persona: un usuario de sistema no firma ninguna."""
    if not es_persona(conn, usuario_id):
        fila = conn.execute("SELECT nombre, es_sistema FROM usuario WHERE id = ?",
                            (usuario_id,)).fetchone() if usuario_id is not None else None
        if fila is not None and fila["es_sistema"]:
            motivo = f"{fila['nombre']} es un usuario de sistema: no firma ordenes de personas"
        else:
            motivo = "la orden necesita una persona activa"
        raise PermisoDenegado(usuario_id, Permiso.VER_FACTURAS.value, motivo, accion)


def ejecutar(conn: sqlite3.Connection, nombre: str, datos: Mapping[str, Any] | None = None, *,
             usuario_id: int | None, peticion_id: str | None = None,
             segunda_firma_id: int | None = None) -> Diferencia:
    """Ejecuta una orden de una persona, entera o nada (ver el docstring del modulo)."""
    accion = ACCIONES.get(nombre)
    if accion is None:
        raise AccionDesconocida(f"no hay ninguna orden {nombre!r}")
    datos = dict(datos or {})
    motivo = datos.get("motivo")
    if motivo is not None and not isinstance(motivo, str):
        raise DatosNoValidos("el motivo es un texto")
    valores = _validar(accion, datos)
    huella = huella_peticion(nombre, {k: v for k, v in valores.items() if k != "motivo"},
                             (motivo or "").strip() or None)
    if peticion_id is not None:
        if not isinstance(peticion_id, str) or not peticion_id.strip() or len(peticion_id) > 200:
            raise DatosNoValidos("peticion_id es un texto de hasta 200 caracteres")
        previo = _ya_aplicada(conn, peticion_id, usuario_id, huella)
        if previo is not None:
            return Diferencia(accion=nombre, evento_id=previo, repetida=True)
    persona = Persona(usuario_id, motivo=motivo, peticion_id=peticion_id)
    segunda = None
    if segunda_firma_id is not None and nombre != "anular_hallazgo":
        raise DatosNoValidos("la segunda firma es solo para anular un hallazgo")
    if segunda_firma_id is not None:
        segunda = Persona(segunda_firma_id, motivo=motivo,
                          peticion_id=f"{peticion_id}:segunda_firma" if peticion_id else None)
    contexto = Contexto(conn, persona, segunda,
                        {"peticion": {"accion": nombre, "sha256": huella}})

    with orden_auditada(conn):
        _exigir_persona(conn, usuario_id, nombre)
        if accion.permiso is not None:
            exigir(conn, usuario_id, accion.permiso, accion=nombre)
        if accion.motivo == "obligatorio" and not (motivo or "").strip():
            raise FaltaMotivo(f"{nombre} pide un motivo")
        antes = _foto_totales(conn)
        hecho = accion.ejecutar(contexto, valores)
        recalculo = None
        if hecho.evento_id is not None or nombre == "recalcular":
            recalculo = hallazgos.recalcular(conn, motivo="edicion" if hecho.evento_id else
                                             "manual", usuario_id=usuario_id,
                                             causa_evento_id=hecho.evento_id)
            cerrar = hecho.detalle.pop("cerrar_b2", None)
            if cerrar:
                hecho.hallazgos.extend(_cerrar_b2(conn, persona, cerrar, contexto))
                if hecho.hallazgos:
                    recalculo = _juntar(recalculo, hallazgos.recalcular(
                        conn, motivo="edicion", usuario_id=usuario_id,
                        causa_evento_id=hecho.evento_id))
        despues = _foto_totales(conn)
    return _diferencia(nombre, hecho, recalculo, antes, despues)


def _cerrar_b2(conn: sqlite3.Connection, persona: Persona, facturas: list[int],
               contexto: Contexto) -> list[dict[str, Any]]:
    """Los B2 que una fusion dejo desaparecidos, cerrados por quien fusiono (si puede)."""
    from .permisos import tiene

    if not tiene(conn, persona.usuario_id, Permiso.RESOLVER_AVISO.value):
        return []
    cerrados = []
    marcas = ", ".join("?" * len(facturas))
    for fila in conn.execute(
            f"SELECT DISTINCT h.* FROM hallazgo AS h LEFT JOIN hallazgo_objetivo AS o "
            f"ON o.hallazgo_id = h.id AND o.tabla = 'factura' WHERE h.regla = 'B2' "
            f"AND h.estado = 'desaparecido' AND (h.factura_id IN ({marcas}) "
            f"OR o.fila_id IN ({marcas}))", (*facturas, *facturas)).fetchall():
        motivo = (persona.motivo or "").strip() or "fusionada en su factura"
        hallazgos.resolver(conn, fila["id"], Persona(persona.usuario_id, motivo),
                           datos={"por_fusion": True})
        evento = conn.execute("SELECT max(id) FROM evento").fetchone()[0]
        cerrados.append({"hallazgo_id": fila["id"], "regla": "B2",
                         "factura_id": fila["factura_id"], "clave": fila["clave"],
                         "tipo": "resuelto", "causa_evento_id": evento})
    return cerrados


def _juntar(primera: hallazgos.Diferencia, segunda: hallazgos.Diferencia) -> hallazgos.Diferencia:
    """Dos pasadas de una misma orden, como una sola diferencia."""
    primera.transiciones.extend(segunda.transiciones)
    primera.cambios_evaluacion.extend(segunda.cambios_evaluacion)
    if segunda.estados is not None and primera.estados is not None:
        primera.estados.prioridades.extend(segunda.estados.prioridades)
        primera.estados.revisiones_invalidadas.extend(segunda.estados.revisiones_invalidadas)
    primera.ejecucion_id = segunda.ejecucion_id
    return primera


def permiso_de(nombre: str) -> str | None:
    """El permiso que pide una orden (None: el del campo; ver Accion)."""
    return ACCIONES[nombre].permiso
