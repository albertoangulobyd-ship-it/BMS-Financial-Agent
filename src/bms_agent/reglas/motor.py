"""El motor: evalua el catalogo sobre una instantanea y agrupa los fallos en hallazgos.

Todo lo de aqui es puro. `evaluar` corre cada regla y ordena los
resultados (por la posicion de la regla en el catalogo, la tabla, la fila,
el grupo y la clave), asi que el mismo almacen da siempre la misma lista, llegue como
llegue. `agrupar` junta los fallos que son el mismo hallazgo (los de un
grupo de B2, un par de B3) y decide su objetivo principal y su severidad.
`huella` es la evidencia de un hallazgo: los valores comparados, de que
fuente salio cada campo que la regla lee y los parametros de la politica
que uso. La identidad (la clave) no lleva valores; la huella si.

Lo unico que no esta aqui es leer el almacen (instantanea.py) y escribir
los hallazgos (hallazgos.py).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import islice
from operator import itemgetter
from typing import Any

from .base import (
    FALLO,
    GRAVEDAD,
    PRINCIPAL,
    RELACIONADO,
    Instantanea,
    Objetivo,
    Politica,
    Regla,
    Resultado,
)
from .catalogo import CATALOGO


class ResultadoDuplicado(RuntimeError):
    """Una regla dio dos resultados para la misma fila y la misma clave: es un error suyo."""


def evaluar(instantanea: Instantanea,
            reglas: Sequence[Regla] = CATALOGO) -> tuple[Resultado, ...]:
    """Cada regla sobre la instantanea, con los resultados en un orden fijo."""
    # La clave de orden no formatea la clave del hallazgo (son decenas de miles):
    # (grupo, clave) identifica lo mismo dentro de una regla y una fila. Va en
    # su propia tupla para compararla sin recortar nada: con ochenta mil
    # resultados, recortar cada par para buscar duplicados se notaba.
    # Con listas por comprension y los campos por posicion (tabla, fila_id,
    # grupo, clave): un generador por resultado se notaba en ochenta mil.
    ordenados: list[tuple[tuple[int, str, int, str, str], Resultado]] = []
    for posicion, regla in enumerate(reglas):
        ordenados.extend([((posicion, r[1], r[2], r[7] or "", r[6]), r)
                          for r in regla.evaluar(instantanea)])
    ordenados.sort(key=itemgetter(0))
    for (anterior, _r), (siguiente, r) in zip(ordenados, islice(ordenados, 1, None)):
        if anterior == siguiente:
            raise ResultadoDuplicado(f"{r.regla} dio dos resultados para {r.tabla} {r.fila_id} "
                                     f"con la clave {r.clave_hallazgo}")
    return tuple(map(itemgetter(1), ordenados))


@dataclass(frozen=True)
class Detectado:
    """Un hallazgo tal como lo ve esta pasada (aun sin huella, que necesita las fuentes)."""

    clave: str
    regla: str
    tabla: str
    fila_id: int
    factura_id: int | None
    severidad: str
    detalle: str
    valores: Mapping[str, Any]
    objetivos: tuple[Objetivo, ...]
    facturas: tuple[int, ...]


def agrupar(resultados: Iterable[Resultado], instantanea: Instantanea,
            reglas: Sequence[Regla] = CATALOGO) -> list[Detectado]:
    """Los fallos agrupados por su clave de hallazgo, en el orden de las claves."""
    por_id = {r.id: r for r in reglas}
    sentido = {f.id: f.sentido for f in instantanea.facturas}
    factura_de_linea = {l.id: f.id for f in instantanea.facturas for l in f.lineas}
    factura_de_tramo = {t.id: f.id for f in instantanea.facturas for t in f.desglose}
    grupos: dict[str, list[Resultado]] = {}
    for r in resultados:
        if r.resultado == FALLO:
            grupos.setdefault(r.clave_hallazgo, []).append(r)

    def factura_de(objetivo: Objetivo) -> int | None:
        if objetivo.tabla == "factura":
            return objetivo.fila_id
        if objetivo.tabla == "factura_linea":
            return factura_de_linea.get(objetivo.fila_id)
        if objetivo.tabla == "factura_iva":
            return factura_de_tramo.get(objetivo.fila_id)
        return None

    detectados = []
    for clave in sorted(grupos):
        miembros = sorted(grupos[clave], key=lambda r: (r.tabla, r.fila_id))
        regla = por_id[miembros[0].regla]
        principal = _principal(miembros)
        objetivos = _objetivos(miembros, principal)
        severidades = [m.severidad or regla.severidad_para(sentido.get(m.fila_id))
                       for m in miembros]
        modelo = next((m for m in miembros if (m.tabla, m.fila_id) == principal), miembros[0])
        facturas = sorted({f for f in (factura_de(o) for o in objetivos) if f is not None})
        detectados.append(Detectado(
            clave=clave, regla=regla.id, tabla=principal[0], fila_id=principal[1],
            factura_id=principal[1] if principal[0] == "factura" else None,
            severidad=min(severidades, key=lambda s: GRAVEDAD[s]),
            detalle=modelo.detalle, valores=modelo.valores, objetivos=objetivos,
            facturas=tuple(facturas)))
    return detectados


def _principal(miembros: Sequence[Resultado]) -> tuple[str, int]:
    """La fila del hallazgo: la del resultado o, en un grupo, la que la regla marco principal."""
    if miembros[0].grupo is None:
        return miembros[0].tabla, miembros[0].fila_id
    for m in miembros:
        for o in m.objetivos:
            if o.papel == PRINCIPAL and o.tabla == "factura":
                return o.tabla, o.fila_id
    ultimo = max(miembros, key=lambda m: m.fila_id)
    return ultimo.tabla, ultimo.fila_id


def _objetivos(miembros: Sequence[Resultado],
               principal: tuple[str, int]) -> tuple[Objetivo, ...]:
    """Cada fila (y campo) que toca el hallazgo, una vez, la principal marcada como tal."""
    papeles: dict[tuple[str, int, str | None], str] = {}

    def anadir(o: Objetivo) -> None:
        clave = (o.tabla, o.fila_id, o.campo)
        papel = PRINCIPAL if (o.tabla, o.fila_id) == principal else o.papel
        if papeles.get(clave) != PRINCIPAL:
            papeles[clave] = papel

    for m in miembros:
        anadir(Objetivo(m.tabla, m.fila_id, None, RELACIONADO))
        for o in m.objetivos:
            anadir(o)
    return tuple(Objetivo(t, f, c, p) for (t, f, c), p in
                 sorted(papeles.items(), key=lambda e: (e[0][0], e[0][1], e[0][2] or "")))


# ------------------------------------------------------------ la huella

# De que columnas del almacen sale cada atributo de la instantanea que no es
# una columna tal cual. Lo que no es un valor (la lista de lineas, el id,
# las marcas de ilegible) no tiene fuente, ni lo que solo dice si la factura
# se evalua (anulada, fusionada): un hallazgo de una factura anulada no existe.
# La contraparte sale de lo que imprime el documento y no de la fila del
# maestro que la resuelve: dar de alta el proveedor no cambia quien firmo la
# factura, y si cambiara la evidencia de un duplicado ya aceptado, cada
# importacion de maestros reabriria lo que una persona ya miro. Si la
# resolucion cambia el grupo, cambian las facturas del hallazgo, y eso si
# es evidencia.
_DERIVADOS_FACTURA = {
    "parte": ("emisor_btw_doc", "emisor_kvk_doc", "emisor_nombre_doc", "receptor_btw_doc",
              "receptor_nombre_doc"),
    "parte_nombre": ("emisor_nombre_doc", "receptor_nombre_doc"),
    "moneda": ("moneda_doc",),
}
_DERIVADOS_LINEA = {"objeto": ("objeto_doc",)}
_SIN_FUENTE = frozenset({"id", "orden", "lineas", "desglose", "ilegibles", "no_solicitados",
                         "anulada", "fusionada_en_id", "dudosos", "sin_original",
                         "sustituida_por", "acreditado_cent"})


def campos_de_fuente(regla: Regla) -> dict[str, tuple[str, ...]]:
    """Por tabla del almacen, las columnas cuya fuente entra en la huella de la regla."""
    tablas = {"factura": ("factura", _DERIVADOS_FACTURA),
              "linea": ("factura_linea", _DERIVADOS_LINEA),
              "tramo_iva": ("factura_iva", {})}
    salida: dict[str, set[str]] = {}
    for lectura in regla.lee - regla.solo_texto:
        tipo, _, nombre = lectura.partition(".")
        if tipo not in tablas or nombre in _SIN_FUENTE:
            continue
        tabla, derivados = tablas[tipo]
        salida.setdefault(tabla, set()).update(derivados.get(nombre, (nombre,)))
    return {tabla: tuple(sorted(columnas)) for tabla, columnas in sorted(salida.items())}


def canonico(valor: Any) -> str:
    """JSON con las claves ordenadas y sin espacios; un float no entra (ya viene redondeado)."""
    _sin_floats(valor)
    return json.dumps(valor, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sin_floats(valor: Any) -> None:
    if isinstance(valor, float):
        raise TypeError("un float no entra en la huella: los importes van en enteros")
    if isinstance(valor, Mapping):
        for v in valor.values():
            _sin_floats(v)
    elif isinstance(valor, (list, tuple)):
        for v in valor:
            _sin_floats(v)


def huella(regla: Regla, valores: Mapping[str, Any], fuentes: Mapping[str, str],
           politica: Politica) -> str:
    """La evidencia de un hallazgo, como sha256.

    Cambia si cambian los valores comparados, la fuente de cualquier campo
    que la regla lee (un valor que era de la extraccion y ahora es de una
    persona), un parametro de la politica que la regla usa o la version de la
    regla. Una anulacion vale mientras la huella sea la que se anulo.
    """
    contenido = {
        "regla": regla.id, "version": regla.version, "valores": dict(valores),
        "fuentes": dict(sorted(fuentes.items())),
        "parametros": {p: politica.valor(p) for p in regla.parametros},
    }
    return hashlib.sha256(canonico(contenido).encode("utf-8")).hexdigest()


def sha256_politica(politica: Politica) -> str:
    return hashlib.sha256(canonico(politica.como_texto()).encode("utf-8")).hexdigest()
