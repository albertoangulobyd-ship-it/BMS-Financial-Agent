"""Lo que cuesta cada pasada del agente, medido y no supuesto.

Dos preguntas distintas, y conviene no mezclarlas:

1. QUE HA COSTADO. Cada extraccion guarda su consumo real de tokens. Aqui
   solo se le pone precio y se agrupa. No llama a la API ni gasta nada.

2. QUE VA A COSTAR la proxima. Los tokens de ENTRADA se pueden contar antes
   de pagar: `messages.count_tokens` devuelve la cifra exacta de la misma
   peticion que se va a mandar, y esa llamada no se cobra. Los de SALIDA no
   se pueden saber sin generar, asi que se estiman con la mediana de vuestro
   propio historico y se dan como una horquilla, nunca como un numero
   redondo que parezca exacto.

La tercera cifra, la que mas tranquiliza: volver a lanzar una carpeta ya
leida cuesta cero. La cache va por hash de los bytes del documento, asi que
un reenvio no se vuelve a pagar. Una correccion si, porque es otro fichero y
hay que leerlo para saber que dice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from statistics import median
from typing import Any

from .pricing import PRICES, estimate_cost

# Dos extracciones separadas por mas de esto se cuentan como pasadas
# distintas. Es una heuristica sobre la hora de cada fichero, no un registro
# de ejecuciones: si hace falta exactitud, la da el fichero de ejecucion.
HUECO_ENTRE_PASADAS_MIN = 10


@dataclass
class Documento:
    nombre: str
    modelo: str
    entrada: int
    salida: int
    cuando: datetime | None
    coste: Decimal | None


@dataclass
class Pasada:
    """Un grupo de extracciones seguidas en el tiempo."""

    desde: datetime | None
    hasta: datetime | None
    documentos: list[Documento] = field(default_factory=list)

    @property
    def entrada(self) -> int:
        return sum(d.entrada for d in self.documentos)

    @property
    def salida(self) -> int:
        return sum(d.salida for d in self.documentos)

    @property
    def coste(self) -> Decimal | None:
        costes = [d.coste for d in self.documentos if d.coste is not None]
        if len(costes) != len(self.documentos):
            return None  # algun modelo sin tarifa: no se suma a medias
        return sum(costes, Decimal(0))


def _cuando(registro: dict[str, Any]) -> datetime | None:
    crudo = registro.get("extracted_at")
    if not crudo:
        return None
    try:
        return datetime.fromisoformat(str(crudo))
    except ValueError:
        return None


def leer_documentos(registros: list[dict[str, Any]]) -> list[Documento]:
    """Consumo y coste de cada extraccion ya guardada."""
    documentos = []
    for registro in registros:
        uso = registro.get("usage") or {}
        modelo = registro.get("model") or "desconocido"
        entrada = uso.get("input_tokens") or 0
        salida = uso.get("output_tokens") or 0
        documentos.append(
            Documento(
                nombre=registro.get("source_name") or "(sin nombre)",
                modelo=modelo,
                entrada=entrada,
                salida=salida,
                cuando=_cuando(registro),
                coste=estimate_cost(modelo, entrada, salida),
            )
        )
    return documentos


def agrupar_en_pasadas(documentos: list[Documento]) -> list[Pasada]:
    """Parte el historico en pasadas por los huecos de tiempo.

    Los documentos sin hora van juntos en una pasada al final: no se les
    inventa un hueco.
    """
    con_hora = sorted(
        (d for d in documentos if d.cuando is not None), key=lambda d: d.cuando
    )
    sin_hora = [d for d in documentos if d.cuando is None]

    pasadas: list[Pasada] = []
    for doc in con_hora:
        ultima = pasadas[-1] if pasadas else None
        if ultima is not None and ultima.hasta is not None:
            hueco = (doc.cuando - ultima.hasta).total_seconds() / 60
            if hueco <= HUECO_ENTRE_PASADAS_MIN:
                ultima.documentos.append(doc)
                ultima.hasta = doc.cuando
                continue
        pasadas.append(Pasada(desde=doc.cuando, hasta=doc.cuando, documentos=[doc]))

    pasadas.sort(key=lambda p: p.hasta or datetime.min, reverse=True)
    if sin_hora:
        # Al final, y en su propio grupo: no se les inventa una hora ni se
        # cuelan en la pasada de otro dia.
        pasadas.append(Pasada(desde=None, hasta=None, documentos=list(sin_hora)))
    return pasadas


@dataclass
class Estimacion:
    """Lo que costaria leer unos documentos que todavia no se han leido."""

    modelo: str
    en_cache: int
    nuevos: int
    entrada: int                     # contada, exacta
    salida_baja: int                 # horquilla, estimada
    salida_alta: int
    salida_medida: bool              # False si no habia historico del que sacarla

    @property
    def coste_bajo(self) -> Decimal | None:
        return estimate_cost(self.modelo, self.entrada, self.salida_baja)

    @property
    def coste_alto(self) -> Decimal | None:
        return estimate_cost(self.modelo, self.entrada, self.salida_alta)


# Sin historico propio, una factura de una pagina ronda esto de salida. Es
# un punto de partida declarado, no una medida: la horquilla se ensancha
# para que nadie lo lea como una cifra fiable.
SALIDA_POR_DEFECTO = (600, 1600)


def horquilla_de_salida(documentos: list[Documento]) -> tuple[int, int, bool]:
    """Cuantos tokens de salida esperar por documento, segun el historico."""
    salidas = [d.salida for d in documentos if d.salida]
    if len(salidas) < 3:
        return (*SALIDA_POR_DEFECTO, False)
    salidas.sort()
    centro = median(salidas)
    # Percentiles 10 y 90, para que un documento raro no mande en la cifra.
    ultimo = len(salidas) - 1
    bajo = salidas[int(0.10 * ultimo)]
    alto = salidas[int(0.90 * ultimo)]
    return int(min(bajo, centro)), int(max(alto, centro)), True


def contar_entrada(client: Any, peticion: dict[str, Any]) -> int:
    """Tokens de entrada exactos de una peticion. Esta llamada no se cobra.

    Se le quita `max_tokens`, que no es parte de la entrada; el resto va tal
    cual, incluido el esquema, que tambien ocupa.
    """
    argumentos = {k: v for k, v in peticion.items() if k != "max_tokens"}
    respuesta = client.messages.count_tokens(**argumentos)
    return int(getattr(respuesta, "input_tokens", 0) or 0)


def _miles(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _dolares(v: Decimal | None, decimales: int = 4) -> str:
    return "sin tarifa" if v is None else f"${v:.{decimales}f}"


def formatear_gastado(documentos: list[Documento]) -> str:
    if not documentos:
        return "No hay ninguna extraccion guardada todavia."

    modelos = sorted({d.modelo for d in documentos})
    entrada = sum(d.entrada for d in documentos)
    salida = sum(d.salida for d in documentos)
    costes = [d.coste for d in documentos if d.coste is not None]
    total = sum(costes, Decimal(0)) if costes else None

    lineas = [
        "Lo que ha costado",
        "-" * 52,
        f"  documentos leidos    {len(documentos):>14,}".replace(",", "."),
        f"  tokens de entrada    {_miles(entrada):>14}",
        f"  tokens de salida     {_miles(salida):>14}",
    ]
    if total is not None:
        lineas.append(f"  coste                {_dolares(total):>14}")
        if len(costes) == len(documentos) and documentos:
            media = total / Decimal(len(documentos))
            caro = max(documentos, key=lambda d: d.coste or Decimal(0))
            barato = min(documentos, key=lambda d: d.coste or Decimal(0))
            lineas += [
                "",
                f"  por documento        {_dolares(media):>14}",
                f"  el mas caro          {_dolares(caro.coste):>14}   {caro.nombre}",
                f"  el mas barato        {_dolares(barato.coste):>14}   {barato.nombre}",
            ]
    if len(costes) != len(documentos):
        faltan = sorted({d.modelo for d in documentos if d.coste is None})
        lineas.append(f"\n  Sin tarifa conocida para {', '.join(faltan)}.")
    if len(modelos) > 1:
        lineas.append(f"\n  Mezcla de modelos: {', '.join(modelos)}.")

    return "\n".join(lineas)


def formatear_pasadas(pasadas: list[Pasada]) -> str:
    if not pasadas:
        return ""
    lineas = ["Por pasada", "-" * 52]
    for pasada in pasadas:
        cuando = (
            pasada.desde.strftime("%Y-%m-%d %H:%M")
            if pasada.desde is not None
            else "(sin hora guardada)"
        )
        n = len(pasada.documentos)
        lineas.append(
            f"  {cuando:<20} {n:>4} doc   {_dolares(pasada.coste):>10}"
        )
    if len(pasadas) > 1:
        lineas.append(
            f"\n  Dos extracciones separadas por mas de {HUECO_ENTRE_PASADAS_MIN}"
            " minutos se cuentan aqui como pasadas distintas."
        )
    return "\n".join(lineas)


def formatear_relanzar(documentos: list[Documento]) -> str:
    n = len(documentos)
    if not n:
        return ""
    return "\n".join([
        "Volver a lanzar lo ya leido",
        "-" * 52,
        f"  {n} de {n} documentos estan en cache      {'$0.0000':>10}",
        "",
        "  La cache va por el hash de los bytes del PDF. Un reenvio del",
        "  mismo fichero no se vuelve a pagar. Una correccion si: es otro",
        "  fichero y hay que leerlo para saber que dice.",
        "  `--force` se salta la cache y vuelve a pagarlo todo.",
    ])


def formatear_estimacion(est: Estimacion) -> str:
    lineas = [
        "La proxima pasada",
        "-" * 52,
        f"  ya leidos (cache)    {est.en_cache:>14}   $0.0000",
        f"  por leer             {est.nuevos:>14}",
    ]
    if not est.nuevos:
        lineas.append("\n  No hay nada nuevo: la proxima pasada cuesta cero.")
        return "\n".join(lineas)

    rango = f"{_miles(est.salida_baja)} a {_miles(est.salida_alta)}"
    origen = "mediana de vuestro historico" if est.salida_medida else "sin medir"
    lineas += [
        "",
        f"  tokens de entrada    {_miles(est.entrada):>14}   contados, exacto",
        f"  tokens de salida     {rango:>14}   {origen}",
    ]
    bajo, alto = est.coste_bajo, est.coste_alto
    if bajo is None or alto is None:
        lineas.append(f"\n  Sin tarifa conocida para {est.modelo}; no hay estimacion.")
        return "\n".join(lineas)

    lineas += [
        "",
        f"  coste estimado       {_dolares(bajo) + ' a ' + _dolares(alto):>14}",
        f"  por documento        "
        f"{_dolares(bajo / est.nuevos) + ' a ' + _dolares(alto / est.nuevos):>14}",
        "",
        "  La entrada es exacta: contarla no se cobra. La salida no se puede",
        "  saber sin generar, y por eso va en horquilla.",
    ]
    if not est.salida_medida:
        lineas += [
            "  Con menos de tres extracciones previas de las que sacarla, la",
            f"  salida es un punto de partida declarado ({SALIDA_POR_DEFECTO[0]}-"
            f"{SALIDA_POR_DEFECTO[1]} tokens por documento), no una medida.",
        ]
    if est.modelo in PRICES:
        lineas.append(
            f"\n  Tarifa de {est.modelo}: ${PRICES[est.modelo][0]} entrada y"
            f" ${PRICES[est.modelo][1]} salida por millon."
        )
    return "\n".join(lineas)
