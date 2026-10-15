"""Relaciones entre facturas (spec §7, R1-R5) y lo que mueven, en puro.

Una relacion une un origen (el abono, la factura que corrige o la que
sustituye) con su destino (la original). Solo las confirmadas por una persona
mueven algo (decision 20); las que propone la extraccion o Exact esperan.

Lo que mueve cada tipo confirmado (`efectos`):

- acredita o anula: el abono le quita a la original lo que dice la relacion
  (o el abono entero si no lo dice), en el signo de la original, y ese mismo
  importe se gasta del abono. Las dos siguen en los totales y en el IVA, cada
  una en su fecha: se compensan. Un abono que lo cubre todo deja la original
  acreditada (o anulada, si la anula); uno parcial le baja lo pendiente.
- sustituye o corrige: la original sale de juego, de los totales, de la caja
  y del IVA; cuenta la nueva.
- relacionada: nada.

Las reglas:

- R1 (retiene, se anula): un abono o una correccion nombra una factura que
  no esta (la misma contraparte y el mismo numero), o que esta repetida.
- R2 (retiene, pegajosa, no se anula): los abonos le quitan a una factura mas
  de lo que vale, o un abono se gasta en mas de lo que vale.
- R3 (bloquea, pegajosa, no se anula): la original y la que la sustituye
  estan las dos pendientes (las dos se pagarian) o las dos pagadas.
- R4 (aviso): un abono sin ninguna relacion confirmada que diga que abona.
- R5 (aviso): una relacion propuesta espera a que una persona la confirme o
  la rechace.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any, NamedTuple

from ..dominio import RELACIONES_QUE_ACREDITAN, RELACIONES_QUE_SUSTITUYEN
from .base import (
    FALLO,
    LEE_EN_JUEGO,
    RELACIONADO,
    SIN_DATOS,
    Factura,
    Instantanea,
    Objetivo,
    Resultado,
    en_juego,
    euros,
    euros_texto,
    fallo,
    sin_datos,
    solo_objeciones,
)
from .pagos import tolerancia_cent

ACREDITAN = RELACIONES_QUE_ACREDITAN
SUSTITUYEN = RELACIONES_QUE_SUSTITUYEN
NOTA_CREDITO = "nota_credito"
# Lo que dice un documento de la factura que nombra y que, si no esta, es R1:
# abonarla, corregirla, sustituirla o anularla. "refers_to" solo la menciona.
CITAS_QUE_PIDEN = frozenset({"credits", "corrects", "replaces", "cancels"})


# ------------------------------------------------------------ lo que mueven

class Efecto(NamedTuple):
    """Lo que las relaciones confirmadas hacen con una factura.

    `acreditado_cent`: lo que le quitan los abonos (en su signo), o en un
    abono lo ya gastado de el (en el signo del abono). `sustituida_por`: la
    factura que la sustituye o la corrige (la de id menor si fueran varias).
    `anulada_por_abono`: un abono que la anula.
    """

    acreditado_cent: int = 0
    sustituida_por: int | None = None
    anulada_por_abono: bool = False


SIN_EFECTO = Efecto()


def importe_de(relacion: Any, total_origen: int | None) -> int:
    """Lo que acredita una relacion, en el signo de la original: el suyo, o el abono entero.

    El abono lleva su total en negativo (un abono de 500 a una factura de
    1.000 es -500): acredita 500. Sin total en euros (X1), nada.
    """
    if relacion.importe_cent is not None:
        return relacion.importe_cent
    return -total_origen if total_origen is not None else 0


def efectos(relaciones: Iterable[Any], totales: Mapping[int, int | None]) -> dict[int, Efecto]:
    """Lo que mueven las relaciones confirmadas, por factura (solo las que tienen algo).

    `relaciones` son las confirmadas y vivas (cualquier cosa con origen_id,
    destino_id, tipo e importe_cent); `totales`, el total de cada factura.
    Es lo mismo que la vista v_factura_relaciones, escrito una vez para las
    reglas, las caches, la caja y las consultas.
    """
    acreditado: dict[int, int] = defaultdict(int)
    sustituida: dict[int, int] = {}
    anuladas: set[int] = set()
    for r in relaciones:
        if r.tipo in ACREDITAN:
            cent = importe_de(r, totales.get(r.origen_id))
            acreditado[r.destino_id] += cent
            acreditado[r.origen_id] -= cent
            if r.tipo == "anula":
                anuladas.add(r.destino_id)
        elif r.tipo in SUSTITUYEN:
            previo = sustituida.get(r.destino_id)
            sustituida[r.destino_id] = r.origen_id if previo is None else min(previo, r.origen_id)
    ids = set(acreditado) | set(sustituida) | anuladas
    return {i: Efecto(acreditado.get(i, 0), sustituida.get(i), i in anuladas) for i in ids}


def _texto(cent: int | None) -> str:
    return "?" if cent is None else euros_texto(euros(cent))


def _numero(factura: Factura) -> str:
    return factura.numero or f"(factura {factura.id})"


# ------------------------------------------------------------ R1

def _preparar_r1(instantanea: Instantanea) -> dict[str, Any]:
    """Las citas de cada factura y las facturas por (sentido, contraparte, numero).

    Una fusionada no cuenta: es la copia de otra que tambien casaria.
    """
    citas: dict[int, list[Any]] = defaultdict(list)
    for cita in instantanea.citas:
        citas[cita.factura_id].append(cita)
    por_numero: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for f in instantanea.facturas:
        if f.parte is not None and f.numero_norm is not None and f.fusionada_en_id is None:
            por_numero[(f.sentido, f.parte, f.numero_norm)].append(f.id)
    return {"citas": citas, "por_numero": por_numero}


def r1(factura: Factura, contexto: dict[str, Any]) -> list[Resultado]:
    """R1: un abono o una correccion nombra una factura que no esta (o que esta repetida)."""
    salida = []
    for cita in contexto["citas"].get(factura.id, ()):
        if cita.relacion not in CITAS_QUE_PIDEN and factura.tipo != NOTA_CREDITO:
            continue
        clave = f"cita:{cita.id}"
        if cita.numero_norm is None:
            salida.append(sin_datos("R1", factura, "Nombra otra factura, pero su número no se "
                                                   "pudo leer.", clave=clave))
            continue
        if factura.parte is None:
            salida.append(sin_datos("R1", factura, "El documento no dice de quién es: no se "
                                                   "puede buscar la factura que nombra.",
                                    clave=clave))
            continue
        encontradas = [i for i in contexto["por_numero"].get(
            (factura.sentido, factura.parte, cita.numero_norm), ()) if i != factura.id]
        if len(encontradas) == 1:
            continue
        que = ("no está en el almacén" if not encontradas
               else f"está {len(encontradas)} veces ({', '.join(map(str, encontradas))})")
        salida.append(fallo(
            "R1", factura, f"Nombra la factura {cita.numero_doc or cita.numero_norm} de la misma "
                           f"contraparte ({cita.relacion or 'sin decir qué es'}), que {que}.",
            valores={"cita": cita.id, "numero_norm": cita.numero_norm,
                     "relacion": cita.relacion, "encontradas": encontradas},
            clave=clave, objetivos=(Objetivo("factura", factura.id),)))
    return salida


LEE_R1 = LEE_EN_JUEGO | frozenset({
    "factura.id", "factura.tipo", "factura.sentido", "factura.parte", "factura.numero_norm",
    "instantanea.citas", "cita.id", "cita.factura_id", "cita.numero_norm", "cita.numero_doc",
    "cita.relacion",
})


# ------------------------------------------------------------ R2

def r2(instantanea: Instantanea) -> list[Resultado]:
    """R2: los abonos confirmados le quitan a una factura mas de lo que vale, o un abono se
    gasta en mas de lo que vale (retiene, pegajosa)."""
    tolerancia = tolerancia_cent(instantanea.politica.tolerancia_pago)
    facturas = {f.id: f for f in instantanea.facturas}
    abonos_de: dict[int, list[int]] = defaultdict(list)
    destinos_de: dict[int, list[int]] = defaultdict(list)
    for r in instantanea.relaciones:
        if r.tipo in ACREDITAN and r.origen_id in facturas and r.destino_id in facturas:
            abonos_de[r.destino_id].append(r.origen_id)
            destinos_de[r.origen_id].append(r.destino_id)
    salida: list[Resultado] = []
    for destino_id, abonos in sorted(abonos_de.items()):
        f = facturas[destino_id]
        relacionados = tuple(Objetivo("factura", a, None, RELACIONADO) for a in sorted(abonos))
        if f.total_cent is None:
            salida.append(Resultado("R2", "factura", f.id, SIN_DATOS,
                                    "Tiene abonos, pero no un total en euros con que compararlos.",
                                    clave="acreditado"))
            continue
        if abs(f.acreditado_cent) > abs(f.total_cent) + tolerancia:
            salida.append(fallo(
                "R2", f, f"Los abonos le quitan {_texto(f.acreditado_cent)} a {_numero(f)}, que "
                         f"vale {_texto(f.total_cent)}.",
                valores={"total_cent": f.total_cent, "acreditado_cent": f.acreditado_cent,
                         "abonos": sorted(abonos)},
                clave="acreditado",
                objetivos=(Objetivo("factura", f.id, "total_cent"), *relacionados)))
    for abono_id, destinos in sorted(destinos_de.items()):
        a = facturas[abono_id]
        if a.total_cent is None:
            continue
        gastado = -a.acreditado_cent
        if abs(gastado) > abs(a.total_cent) + tolerancia:
            salida.append(fallo(
                "R2", a, f"El abono {_numero(a)} vale {_texto(a.total_cent)} y se ha aplicado por "
                         f"{_texto(gastado)}.",
                valores={"total_cent": a.total_cent, "aplicado_cent": gastado,
                         "destinos": sorted(destinos)},
                clave="aplicado",
                objetivos=(Objetivo("factura", a.id, "total_cent"),
                           *(Objetivo("factura", d, None, RELACIONADO)
                             for d in sorted(destinos)))))
    return salida


LEE_R2 = frozenset({
    "instantanea.facturas", "instantanea.relaciones", "instantanea.politica",
    "politica.tolerancia_pago", "relacion.tipo", "relacion.origen_id", "relacion.destino_id",
    "factura.id", "factura.total_cent", "factura.acreditado_cent", "factura.numero",
})


# ------------------------------------------------------------ R3

def _abierta(f: Factura, tolerancia: int) -> bool:
    """Pendiente: ni anulada, ni saldada (pagada o acreditada), con algo que pagar."""
    if f.anulada or f.total_cent is None or f.pagada:
        return False
    return abs(f.total_cent - f.pagado_cent - f.acreditado_cent) > tolerancia


def _pagada(f: Factura) -> bool:
    """Pagada con dinero: saldada y con algo pagado (una acreditada no se pago)."""
    return f.pagada and f.pagado_cent != 0


def r3(instantanea: Instantanea) -> list[Resultado]:
    """R3: la original y la que la sustituye (o corrige), las dos pendientes o las dos pagadas.

    Las dos pendientes es el riesgo de pagar dos veces el mismo trabajo: la
    original sigue en la contabilidad hasta que un abono la anule. Las dos
    pagadas es que ya se pago dos veces. La lee aunque la original este
    fuera de juego (sustituida): para eso existe.
    """
    tolerancia = tolerancia_cent(instantanea.politica.tolerancia_pago)
    facturas = {f.id: f for f in instantanea.facturas}
    salida: list[Resultado] = []
    for r in sorted(instantanea.relaciones, key=lambda r: (r.origen_id, r.destino_id)):
        if r.tipo not in SUSTITUYEN or r.origen_id not in facturas or r.destino_id not in facturas:
            continue
        nueva, original = facturas[r.origen_id], facturas[r.destino_id]
        if nueva.anulada or nueva.fusionada_en_id is not None:
            continue
        if _abierta(nueva, tolerancia) and _abierta(original, tolerancia):
            que = "las dos están pendientes: se pagaría el mismo trabajo dos veces"
        elif _pagada(nueva) and _pagada(original):
            que = "las dos están pagadas"
        else:
            continue
        menor, mayor = sorted((nueva.id, original.id))
        detalle = (f"{_numero(nueva)} sustituye a {_numero(original)} y {que}. Anula o abona la "
                   "original.")
        valores = {"nueva": nueva.id, "original": original.id, "tipo": r.tipo,
                   "pendiente_cent": [nueva.total_cent - nueva.pagado_cent - nueva.acreditado_cent
                                      if nueva.total_cent is not None else None,
                                      original.total_cent - original.pagado_cent
                                      - original.acreditado_cent
                                      if original.total_cent is not None else None],
                   "pagado_cent": [nueva.pagado_cent, original.pagado_cent]}
        objetivos = (Objetivo("factura", nueva.id),
                     Objetivo("factura", original.id, None, RELACIONADO))
        for ref in (nueva.id, original.id):
            salida.append(Resultado("R3", "factura", ref, FALLO, detalle, valores,
                                    grupo=f"par:{menor}-{mayor}", objetivos=objetivos))
    return salida


LEE_R3 = frozenset({
    "instantanea.facturas", "instantanea.relaciones", "instantanea.politica",
    "politica.tolerancia_pago", "relacion.tipo", "relacion.origen_id", "relacion.destino_id",
    "factura.id", "factura.anulada", "factura.fusionada_en_id", "factura.total_cent",
    "factura.pagada", "factura.pagado_cent", "factura.acreditado_cent", "factura.numero",
})


# ------------------------------------------------------------ R4

def _preparar_r4(instantanea: Instantanea) -> frozenset[int]:
    """Los abonos con una relacion confirmada que dice a que factura abonan."""
    return frozenset(r.origen_id for r in instantanea.relaciones if r.tipo in ACREDITAN)


def r4(factura: Factura, enlazados: frozenset[int]) -> list[Resultado]:
    """R4: un abono sin ninguna relacion confirmada que diga a que factura abona (aviso)."""
    if factura.tipo != NOTA_CREDITO or factura.id in enlazados:
        return []
    return [fallo("R4", factura, "Es un abono y ninguna relación confirmada dice a qué factura "
                                 "abona: no baja lo pendiente de ninguna.",
                  valores={"tipo": factura.tipo, "total_cent": factura.total_cent},
                  objetivos=(Objetivo("factura", factura.id),))]


LEE_R4 = LEE_EN_JUEGO | frozenset({
    "factura.id", "factura.tipo", "factura.total_cent", "instantanea.relaciones",
    "relacion.tipo", "relacion.origen_id",
})


# ------------------------------------------------------------ R5

_QUIEN_PROPONE = {"extraccion": "La extracción", "exact": "Exact"}


def r5(instantanea: Instantanea) -> list[Resultado]:
    """R5: una relacion propuesta espera a que una persona la confirme o la rechace (aviso)."""
    facturas = {f.id: f for f in instantanea.facturas}
    salida: list[Resultado] = []
    for r in sorted(instantanea.propuestas, key=lambda r: r.id):
        origen, destino = facturas.get(r.origen_id), facturas.get(r.destino_id)
        if origen is None or destino is None or not en_juego(origen):
            continue
        quien = _QUIEN_PROPONE.get(r.fuente, "El sistema")
        detalle = (f"{quien} propone que {_numero(origen)} {r.tipo} {_numero(destino)}: "
                   "confírmalo o recházalo (hasta entonces no mueve nada).")
        valores = {"relacion": r.id, "tipo": r.tipo, "origen": origen.id,
                   "destino": destino.id, "importe_cent": r.importe_cent}
        objetivos = (Objetivo("factura", origen.id),
                     Objetivo("factura", destino.id, None, RELACIONADO))
        for ref in (origen.id, destino.id):
            salida.append(Resultado("R5", "factura", ref, FALLO, detalle, valores,
                                    grupo=f"relacion:{r.id}", objetivos=objetivos))
    return salida


LEE_R5 = frozenset({
    "instantanea.facturas", "instantanea.propuestas", "relacion.id", "relacion.tipo",
    "relacion.origen_id", "relacion.destino_id", "relacion.fuente", "relacion.importe_cent",
    "factura.id", "factura.numero", "factura.anulada", "factura.fusionada_en_id",
    "factura.sustituida_por",
})

EVALUAR = {
    "R1": solo_objeciones(r1, _preparar_r1),
    "R2": r2,
    "R3": r3,
    "R4": solo_objeciones(r4, _preparar_r4),
    "R5": r5,
}

# El numero impreso solo se ensena: corregirlo no cambia la evidencia de R2, R3 ni R5.
SOLO_TEXTO = frozenset({"factura.numero"})
