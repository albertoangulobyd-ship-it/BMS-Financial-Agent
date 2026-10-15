"""Reglas de unicidad que cruzan el historico: B2, B3 y B4.

Es lo que una factura mirada de una en una no puede ver: el mismo numero
dos veces, el mismo importe dos veces en pocos dias, el mismo periodo
cobrado dos veces. Las tres son pegajosas: un duplicado que deja de verse
porque alguien edito un importe no es un duplicado resuelto.

Las comprobaciones de fondo (`numeros_repetidos`, `importes_repetidos`,
`periodos_solapados`) trabajan sobre `Candidata`, que no sabe de donde
sale: el motor las construye desde el almacen y dashboard.py desde las
filas del panel v1. Ninguna depende del orden en que llegan las facturas:
se ordenan por la fecha y despues por `orden`, que el motor llena con el id
de la factura y el panel con su posicion de siempre.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Hashable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .base import (
    FALLO,
    LEE_PERIODO,
    LEE_RELACIONES,
    NO_APLICA,
    OK,
    RELACIONADO,
    SIN_DATOS,
    Factura,
    Instantanea,
    Objetivo,
    Politica,
    Resultado,
    euros,
    euros_texto,
    fuera_de_juego,
    periodo_de,
    vinculadas,
)


@dataclass(frozen=True)
class Candidata:
    """Una factura tal como la ven las reglas de duplicados.

    `grupo` es la contraparte (y el sentido): None no agrupa con nadie, para
    que las facturas sin nombre, btw-id ni KvK no se junten entre si. `ref`
    dice quien es (el id de la factura, o la fila del panel) y `orden`
    desempata de forma estable.
    """

    ref: Hashable
    grupo: str | None
    numero: str | None
    fecha: date | None
    total: Decimal | None
    inicio: date | None
    fin: date | None
    orden: tuple | int


Par = tuple[Candidata, Candidata, int]


def _par(a: Candidata, b: Candidata) -> frozenset:
    return frozenset((a.ref, b.ref))


def numeros_repetidos(
    candidatas: Iterable[Candidata], enlazadas: frozenset[frozenset] = frozenset(),
) -> list[tuple[tuple[str, str], list[Candidata]]]:
    """B2: misma contraparte y mismo numero, en grupos de dos o mas.

    Dos facturas unidas por una relacion confirmada (una sustituye a la
    otra) no son un duplicado entre si; una tercera con el mismo numero, si.
    Los grupos salen ordenados por su clave y sus miembros por `orden`.
    """
    por_clave: dict[tuple[str, str], list[Candidata]] = defaultdict(list)
    for c in candidatas:
        if c.grupo is None or c.numero is None:
            continue
        por_clave[(c.grupo, c.numero)].append(c)
    salida = []
    for clave, grupo in sorted(por_clave.items()):
        grupo = sorted(grupo, key=lambda c: c.orden)
        miembros = [c for c in grupo
                    if any(o is not c and _par(c, o) not in enlazadas for o in grupo)]
        if len(miembros) > 1:
            salida.append((clave, miembros))
    return salida


def periodos_compatibles(a: Candidata, b: Candidata) -> bool:
    """Dos facturas pueden ser el mismo trabajo cobrado dos veces.

    Lo son si sus periodos se pisan, o si alguna no declara periodo y por
    tanto no se puede descartar. Dos semanas distintas al mismo importe son
    la rutina de un autonomo con tarifa fija, no un duplicado.
    """
    if not (a.inicio and a.fin) or not (b.inicio and b.fin):
        return True
    return a.inicio <= b.fin and b.inicio <= a.fin


def importes_repetidos(
    candidatas: Iterable[Candidata], politica: Politica,
    enlazadas: frozenset[frozenset] = frozenset(),
) -> list[Par]:
    """B3: misma contraparte, el mismo total (con la tolerancia), a pocos dias, otro numero.

    Devuelve cada par (el anterior primero) con los dias que los separan.
    Un autonomo con tarifa fija factura el mismo importe todas las semanas:
    sin exigir que los periodos sean compatibles, cada par consecutivo
    saltaria y la regla se volveria ruido puro.
    """
    por_grupo: dict[str, list[Candidata]] = defaultdict(list)
    for c in candidatas:
        if c.grupo is None or c.total is None or c.fecha is None:
            continue
        por_grupo[c.grupo].append(c)
    pares: list[Par] = []
    for _grupo, lista in sorted(por_grupo.items()):
        lista = sorted(lista, key=lambda c: (c.fecha, c.orden))
        for i, a in enumerate(lista):
            # La ventana se corta antes de mirar nada mas: con la lista por
            # fecha, la primera factura fuera de plazo deja fuera a todas las
            # siguientes. Mirar antes el importe convertia a un proveedor con
            # miles de facturas en millones de comparaciones.
            for b in lista[i + 1:]:
                dias = (b.fecha - a.fecha).days
                if dias > politica.ventana_duplicado_dias:
                    break
                if a.numero == b.numero or abs(a.total - b.total) > politica.tolerancia_duplicado:
                    continue
                if not periodos_compatibles(a, b) or _par(a, b) in enlazadas:
                    continue
                pares.append((a, b, dias))
    return pares


def periodos_solapados(
    candidatas: Iterable[Candidata],
    excluir: Callable[[Candidata, Candidata], bool] = lambda _a, _b: False,
) -> list[Par]:
    """B4: el mismo periodo cobrado dos veces por la misma contraparte.

    Se comparan rangos de fechas, no textos: del 7 al 13 solapa con del 1 al
    10 aunque no se parezcan en nada, y ese es el caso que hay que cazar.
    Devuelve cada par con los dias que se pisan. `excluir` deja fuera los
    pares que se explican solos (un abono, una relacion confirmada, dos
    Objetos distintos).
    """
    por_grupo: dict[str, list[Candidata]] = defaultdict(list)
    for c in candidatas:
        if c.grupo is None or c.inicio is None or c.fin is None or c.inicio > c.fin:
            continue
        por_grupo[c.grupo].append(c)
    pares: list[Par] = []
    for _grupo, rangos in sorted(por_grupo.items()):
        rangos = sorted(rangos, key=lambda c: (c.inicio, c.orden))
        for i, a in enumerate(rangos):
            for b in rangos[i + 1:]:
                if b.inicio > a.fin:
                    break
                if excluir(a, b):
                    continue
                pares.append((a, b, (min(a.fin, b.fin) - b.inicio).days + 1))
    return pares


# ------------------------------------------------------------ las reglas


def _grupo_de(factura: Factura) -> str | None:
    return None if factura.parte is None else f"{factura.sentido}|{factura.parte}"


def _candidata(factura: Factura) -> Candidata:
    inicio, fin = periodo_de(factura)
    return Candidata(ref=factura.id, grupo=_grupo_de(factura), numero=factura.numero_norm,
                     fecha=factura.fecha_factura, total=euros(factura.total_cent),
                     inicio=inicio, fin=fin, orden=factura.id)


def _numero(factura: Factura) -> str:
    return factura.numero or "(sin número)"


def _iso(dia: date | None) -> str | None:
    return None if dia is None else dia.isoformat()


def _por_pares(regla_id: str, pares: Sequence[Par], facturas: dict[int, Factura],
               detalle: Callable[[Factura, Factura, Candidata, Candidata, int], str],
               valores: Callable[[Candidata, Candidata, int], dict],
               campos: tuple[str, ...]) -> Iterator[Resultado]:
    """Un hallazgo por par, con un resultado para cada factura del par.

    La principal es la que llego despues (la que duplica a la otra). La
    clave es el par de ids: si cambia un importe, el hallazgo es el mismo
    con otra huella.
    """
    for a, b, dias in pares:
        menor, mayor = sorted((a.ref, b.ref))
        fa, fb = facturas[a.ref], facturas[b.ref]
        texto = detalle(fa, fb, a, b, dias)
        objetivos = tuple(Objetivo("factura", b.ref, c) for c in campos) + tuple(
            Objetivo("factura", a.ref, c, RELACIONADO) for c in campos)
        for ref in (a.ref, b.ref):
            yield Resultado(regla_id, "factura", ref, FALLO, texto, valores=valores(a, b, dias),
                            grupo=f"par:{menor}-{mayor}", objetivos=objetivos)


def b2(instantanea: Instantanea) -> Iterator[Resultado]:
    """B2: la misma contraparte con el mismo numero (normalizado), sin fusionar ni enlazar.

    Se cierra fusionando o enlazando las facturas; anularla pide una segunda
    firma cuando hay otra persona que puede darla.
    """
    facturas = {f.id: f for f in instantanea.facturas}
    candidatas: list[Candidata] = []
    for factura in instantanea.facturas:
        motivo = fuera_de_juego(factura)
        if motivo is not None:
            yield Resultado("B2", "factura", factura.id, NO_APLICA, motivo)
        elif factura.parte is None:
            yield Resultado("B2", "factura", factura.id, SIN_DATOS,
                            "El documento no dice de quién es: no se puede buscar un duplicado.")
        elif factura.numero_norm is None:
            yield Resultado("B2", "factura", factura.id, SIN_DATOS, "La factura no tiene número.")
        else:
            # B2 solo compara la contraparte y el numero: ni fechas ni importes
            # entran en su evidencia, asi que corregir un total no la mueve.
            candidatas.append(Candidata(ref=factura.id, grupo=_grupo_de(factura),
                                        numero=factura.numero_norm, fecha=None, total=None,
                                        inicio=None, fin=None, orden=factura.id))
    en_grupo: set[int] = set()
    for (_grupo, numero), miembros in numeros_repetidos(
            candidatas, vinculadas(instantanea.relaciones)):
        ids = sorted(m.ref for m in miembros)
        principal = facturas[ids[-1]]
        detalle = (f"{principal.parte_nombre} tiene {len(ids)} facturas con el número "
                   f"{_numero(principal)}.")
        objetivos = (Objetivo("factura", principal.id, "numero"),) + tuple(
            Objetivo("factura", i, "numero", RELACIONADO) for i in ids[:-1])
        # La identidad es la primera factura del grupo, y no la contraparte:
        # "btw:NL..." pasa a "proveedor:3" cuando se da de alta el maestro, y
        # el duplicado sigue siendo el mismo. Por lo mismo la contraparte no
        # va en la evidencia: lo comparado es el numero y que facturas son.
        valores = {"numero_norm": numero, "facturas": ids}
        for i in ids:
            en_grupo.add(i)
            yield Resultado("B2", "factura", i, FALLO, detalle, valores=valores,
                            grupo=f"grupo:{ids[0]}", objetivos=objetivos)
    for c in candidatas:
        if c.ref not in en_grupo:
            yield Resultado("B2", "factura", c.ref, OK,
                            f"Ninguna otra factura de la contraparte con el número "
                            f"{_numero(facturas[c.ref])}.", valores={"numero_norm": c.numero})


LEE_B2 = LEE_RELACIONES | frozenset({
    "instantanea.facturas", "factura.id", "factura.anulada", "factura.fusionada_en_id",
    "factura.sentido", "factura.parte", "factura.parte_nombre", "factura.numero",
    "factura.numero_norm",
})


def b3(instantanea: Instantanea) -> Iterator[Resultado]:
    """B3: duplicado probable por contenido: mismo importe, pocos dias, numero distinto."""
    politica = instantanea.politica
    facturas = {f.id: f for f in instantanea.facturas}
    candidatas: list[Candidata] = []
    for factura in instantanea.facturas:
        motivo = fuera_de_juego(factura)
        if motivo is not None:
            yield Resultado("B3", "factura", factura.id, NO_APLICA, motivo)
        elif factura.parte is None or factura.total_cent is None or factura.fecha_factura is None:
            yield Resultado("B3", "factura", factura.id, SIN_DATOS,
                            "Sin contraparte, total o fecha: no se puede buscar un duplicado "
                            "por importe.")
        else:
            candidatas.append(_candidata(factura))
    pares = importes_repetidos(candidatas, politica, vinculadas(instantanea.relaciones))

    def detalle(fa: Factura, fb: Factura, a: Candidata, b: Candidata, dias: int) -> str:
        periodos = ("y periodos que se pisan" if a.inicio and a.fin and b.inicio and b.fin
                    else "y ningún periodo que lo descarte")
        return (f"{fb.parte_nombre}: {_numero(fa)} y {_numero(fb)} suman lo mismo "
                f"({euros_texto(b.total)}) con {dias} días de diferencia {periodos}.")

    def valores(a: Candidata, b: Candidata, dias: int) -> dict:
        return {"facturas": [a.ref, b.ref],
                "totales_cent": [facturas[a.ref].total_cent, facturas[b.ref].total_cent],
                "fechas": [_iso(a.fecha), _iso(b.fecha)], "dias": dias,
                "periodos": [[_iso(a.inicio), _iso(a.fin)], [_iso(b.inicio), _iso(b.fin)]]}

    en_par = {ref for a, b, _d in pares for ref in (a.ref, b.ref)}
    yield from _por_pares("B3", pares, facturas, detalle, valores, ("total_cent",))
    for c in candidatas:
        if c.ref not in en_par:
            yield Resultado("B3", "factura", c.ref, OK,
                            "Ninguna otra factura de la contraparte con el mismo importe en "
                            f"{politica.ventana_duplicado_dias} días.")


LEE_B3 = LEE_RELACIONES | LEE_PERIODO | frozenset({
    "instantanea.facturas", "instantanea.politica", "factura.id", "factura.anulada",
    "factura.fusionada_en_id", "factura.sentido", "factura.parte", "factura.parte_nombre",
    "factura.numero", "factura.numero_norm", "factura.fecha_factura", "factura.total_cent",
    "politica.tolerancia_duplicado", "politica.ventana_duplicado_dias",
})


def _objetos(factura: Factura) -> frozenset[str]:
    return frozenset(l.objeto for l in factura.lineas if l.objeto is not None)


def b4(instantanea: Instantanea) -> Iterator[Resultado]:
    """B4: periodos de cobro que se pisan, por Objeto cuando las lineas lo nombran.

    Un abono no cobra un periodo: cubre a proposito el de la factura que
    corrige. Una relacion confirmada entre las dos tampoco es un doble cobro,
    ni dos facturas que nombran Objetos distintos (dos obras a la vez).
    """
    facturas = {f.id: f for f in instantanea.facturas}
    enlazadas = vinculadas(instantanea.relaciones)
    objetos = {f.id: _objetos(f) for f in instantanea.facturas}
    candidatas: list[Candidata] = []
    for factura in instantanea.facturas:
        motivo = fuera_de_juego(factura)
        candidata = None
        if motivo is None:
            # B4 solo compara contraparte y periodo: ni la fecha, ni el total,
            # ni el numero entran en su evidencia.
            inicio, fin = periodo_de(factura)
            candidata = Candidata(ref=factura.id, grupo=_grupo_de(factura), numero=None,
                                  fecha=None, total=None, inicio=inicio, fin=fin,
                                  orden=factura.id)
        if motivo is not None:
            yield Resultado("B4", "factura", factura.id, NO_APLICA, motivo)
        elif factura.tipo == "nota_credito":
            yield Resultado("B4", "factura", factura.id, NO_APLICA,
                            "Un abono no cobra un periodo: cubre el de la factura que corrige.")
        elif candidata.grupo is None or candidata.inicio is None or candidata.fin is None:
            yield Resultado("B4", "factura", factura.id, SIN_DATOS,
                            "Sin contraparte o sin periodo completo: no se puede comparar.")
        elif candidata.inicio > candidata.fin:
            yield Resultado("B4", "factura", factura.id, SIN_DATOS,
                            "El periodo empieza despues de acabar.")
        else:
            candidatas.append(candidata)

    def excluir(a: Candidata, b: Candidata) -> bool:
        distintos = objetos[a.ref] and objetos[b.ref] and not (objetos[a.ref] & objetos[b.ref])
        return _par(a, b) in enlazadas or bool(distintos)

    pares = periodos_solapados(candidatas, excluir)

    def detalle(fa: Factura, fb: Factura, a: Candidata, b: Candidata, dias: int) -> str:
        return (f"{fb.parte_nombre}: {_numero(fa)} ({_iso(a.inicio)} a {_iso(a.fin)}) y "
                f"{_numero(fb)} ({_iso(b.inicio)} a {_iso(b.fin)}) solapan {dias} día(s).")

    def valores(a: Candidata, b: Candidata, dias: int) -> dict:
        # Los Objetos deciden si el par cuenta, pero no van en la evidencia:
        # sus claves cambian al resolverse ("doc:rijnhaven" pasa a "objeto:1")
        # y eso no cambia lo que se acepto, dos periodos que se pisan.
        return {"facturas": [a.ref, b.ref], "dias": dias,
                "periodos": [[_iso(a.inicio), _iso(a.fin)], [_iso(b.inicio), _iso(b.fin)]]}

    en_par = {ref for a, b, _d in pares for ref in (a.ref, b.ref)}
    yield from _por_pares("B4", pares, facturas, detalle, valores,
                          ("periodo_inicio", "periodo_fin"))
    for c in candidatas:
        if c.ref not in en_par:
            yield Resultado("B4", "factura", c.ref, OK,
                            "Ningún otro periodo de la contraparte se pisa con este.")


LEE_B4 = LEE_RELACIONES | LEE_PERIODO | frozenset({
    "instantanea.facturas", "factura.id", "factura.anulada", "factura.fusionada_en_id",
    "factura.tipo", "factura.sentido", "factura.parte", "factura.parte_nombre",
    "factura.numero", "linea.objeto",
})

# Lo que las reglas de duplicados leen solo para su explicacion.
SOLO_TEXTO = frozenset({"factura.parte_nombre", "factura.numero"})
