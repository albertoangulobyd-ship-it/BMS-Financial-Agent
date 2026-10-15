"""Volver a leer documentos ya leidos: con presupuesto, sin pisar nada y sin cambiar lo vigente hasta la puerta.

Es lo unico del agente que vuelve a pagar por un documento que ya tiene una
extraccion (spec §3.18 y §10). Por eso va aparte de `extract`, que con la
politica CONSERVAR nunca vuelve a pagar lo ya leido, y por eso tiene tres
frenos:

1. Presupuesto. Antes de pagar nada se cuentan los tokens de entrada de
   cada documento con count_tokens (exacto, y contar no se cobra) y se
   estima la salida con el historico de la misma version del esquema y el
   mismo esfuerzo (o, sin historico, con un factor declarado y la marca
   "sin medir"). Si el extremo alto de la horquilla pasa del presupuesto, no
   se paga nada. Sin presupuesto, solo se estima. La base tampoco admite una
   reextraccion cuya estimacion alta pase de su presupuesto. Y el
   presupuesto es un tope de lo que se paga, no solo de lo que se estima:
   la via sincrona suma lo que cuesta cada respuesta (tambien un rechazo) y
   se para antes del documento cuyo peor caso (su entrada y todo su
   max_tokens de salida) ya no cabe; un lote, que no se puede parar a
   medias, solo se manda si el peor caso de todo el lote cabe.
2. Candidatas. Lo que se lee queda guardado como cualquier extraccion (en el
   almacen, y exportado en out/reextraccion/ con el hash y las versiones en
   el nombre), pero no es la vigente de su documento: las facturas, sus
   hallazgos y el panel siguen como estaban.
3. La puerta. `activar` solo pasa a vigentes las candidatas de una version
   si la comparacion con la version anterior (scoring.comparar_versiones)
   dice que es al menos igual de buena, llega al 98 % en los campos
   criticos y la factura con inyeccion sigue dando el IBAN de la cabecera.
   Lo activa una persona con admin. Al activar, lo que una persona corrigio
   no se pisa: si la lectura nueva lo contradice queda sin resolver (M1), y
   la edicion de una linea que la lectura nueva no trae queda apuntada y es
   un hallazgo (M2).

Nada de aqui importa el SDK de Anthropic: el cliente se inyecta (la CLI lo
crea), y en los tests es un cliente falso que cuenta las llamadas. Las
peticiones no llevan herramientas, ni la sincrona ni la de lotes.

Por lotes (API de Batches) cuesta la mitad y tarda horas: `ejecutar` manda el
lote y `recoger` lee sus resultados cuando ha terminado. Un rechazo, un
error, un resultado caducado o cancelado, o una salida que no es el esquema
van a la lista de reintentos (reextraccion_resultado): los lotes no admiten
el respaldo de modelo del servidor, asi que nadie los reintenta solo.
"""

from __future__ import annotations

import base64
import json
import math
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from . import coste, scoring
from .almacen import Almacen, reloj_de, transaccion, usuario_sistema
from .almacen.evidencia import foto
from .almacen.extracciones import RegistroInvalido, leer_registro, registrar_extraccion
from .almacen.unidades import json_canonico, sha256_texto
from .auditoria import registrar
from .documents import SourceDocument
from .extract import (
    REINTENTO_ERROR,
    REINTENTO_PRESUPUESTO,
    REINTENTO_RECHAZO,
    ExtractionRecord,
    Rechazado,
    Reintento,
    build_request,
    construir_peticion_lote,
    extract_invoice,
    leer_resultado_lote,
)
from .pricing import estimate_cost
from .reloj import marca

# Donde se exportan las candidatas, dentro de la carpeta de extracciones. No
# es out/ mismo: lo que hay en out/ cuenta como vigente para quien lee sin
# almacen (load_records), y una candidata no lo es hasta su activacion.
CARPETA_EXPORTACION = "reextraccion"

Objetivo = scoring.Version          # (modelo, prompt_version, schema_version)
Informar = Callable[[str, str, str], None]


def objetivo_actual() -> Objetivo:
    """Las versiones con las que se leeria hoy: las de config.py."""
    from . import config

    return (config.model_id(), config.PROMPT_VERSION, config.SCHEMA_VERSION)


class PresupuestoInsuficiente(RuntimeError):
    """La estimacion alta (o, por lotes, el peor caso) pasa del presupuesto: no se paga nada."""

    def __init__(self, estimacion: coste.Estimacion, presupuesto: Decimal,
                 detalle: str | None = None) -> None:
        self.estimacion, self.presupuesto = estimacion, presupuesto
        alto = estimacion.coste_alto
        if detalle is None:
            detalle = ("sin tarifa conocida para " + estimacion.modelo if alto is None
                       else f"hasta ${alto:.4f} estimados")
        super().__init__(f"{detalle} y el presupuesto es ${presupuesto:.2f}: no se paga nada")


class PuertaCerrada(RuntimeError):
    """La version nueva no pasa la puerta: nada se activa."""

    def __init__(self, comparacion: scoring.Comparacion) -> None:
        self.comparacion = comparacion
        super().__init__("la version nueva no puede pasar a vigente: "
                         + "; ".join(comparacion.motivos))


def leer_presupuesto(texto: str) -> Decimal:
    """Un presupuesto en dolares, con dos decimales como mucho ("25", "12.50", "12,50")."""
    try:
        valor = Decimal(str(texto).strip().replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"presupuesto no valido: {texto!r}") from None
    if not valor.is_finite() or valor < 0 or valor != valor.quantize(Decimal("0.01")):
        raise ValueError(f"presupuesto no valido: {texto!r} (dolares, dos decimales como mucho)")
    return valor


# ------------------------------------------------------------ seleccion


@dataclass(frozen=True)
class Criterio:
    """Que documentos volver a leer. Los criterios se suman (todos a la vez)."""

    abiertas: bool = False          # facturas que siguen en juego (sin pagar ni anular)
    desde: date | None = None       # con fecha de factura desde ese dia
    proveedor: str | None = None    # id o nombre del proveedor
    sin_objeto: bool = False        # alguna linea sin Objeto imputado
    reintentos: bool = False        # en la lista de reintentos de esta version
    limite: int | None = None

    def vacio(self) -> bool:
        return not (self.abiertas or self.desde or self.proveedor or self.sin_objeto
                    or self.reintentos)

    def a_dict(self) -> dict[str, Any]:
        return {"abiertas": self.abiertas,
                "desde": self.desde.isoformat() if self.desde else None,
                "proveedor": self.proveedor, "sin_objeto": self.sin_objeto,
                "reintentos": self.reintentos, "limite": self.limite}


@dataclass(frozen=True)
class Seleccionado:
    documento_id: int
    sha256: str
    nombre: str
    tipo_mime: str
    bytes: int | None
    anterior_id: int | None         # la extraccion vigente del documento


@dataclass
class Seleccion:
    documentos: list[Seleccionado] = field(default_factory=list)
    # (documento_id, por que no se vuelve a leer)
    omitidos: list[tuple[int, str]] = field(default_factory=list)
    ya_leidos: int = 0


def _del_proveedor(conn: sqlite3.Connection, valor: str) -> set[int]:
    """Las facturas de un proveedor: por su id, por su nombre en el maestro o por el impreso."""
    from .identidad import normalizar_nombre

    texto = valor.strip()
    if texto.isdigit():
        return {f[0] for f in conn.execute(
            "SELECT id FROM factura WHERE proveedor_id = ?", (int(texto),))}
    buscado = normalizar_nombre(texto)
    proveedores = {f[0] for f in conn.execute("SELECT id, nombre FROM proveedor")
                   if normalizar_nombre(f[1]) == buscado}
    return {f[0] for f in conn.execute(
        "SELECT id, proveedor_id, emisor_nombre_doc FROM factura")
        if f[1] in proveedores or normalizar_nombre(f[2]) == buscado}


def seleccionar(conn: sqlite3.Connection, criterio: Criterio, objetivo: Objetivo) -> Seleccion:
    """Los documentos que cumplen el criterio y que todavia no se han leido con el objetivo.

    Nunca se vuelve a pagar un documento que ya tiene una extraccion de esas
    mismas versiones (vigente, candidata o activada), ni uno que esta en un
    lote sin recoger (mandado, o que no se sabe si se mando: su resultado
    puede estar pagado ya), y no se puede leer uno cuyo original no esta
    guardado (Q4). Los tres casos se dicen. El orden es el de los
    documentos, y el limite se aplica al final.
    """
    from .ingesta import vigentes_por_documento

    if criterio.vacio():
        raise ValueError("hace falta al menos un criterio: --abiertas, --desde, --proveedor, "
                         "--sin-objeto o --reintentos")
    if criterio.limite is not None and criterio.limite < 1:
        raise ValueError("--limite tiene que ser 1 o mas")
    modelo, prompt, esquema = objetivo
    condiciones = ["f.origen = 'extraccion'", "f.documento_id IS NOT NULL"]
    parametros: list[Any] = []
    if criterio.abiertas:
        condiciones.append(
            "f.anulada = 0 AND f.fusionada_en_id IS NULL AND coalesce(("
            "SELECT estado_pago FROM factura_estado AS fe WHERE fe.factura_id = f.id), "
            "'pendiente') IN ('pendiente', 'vencida')")
    if criterio.desde is not None:
        condiciones.append("(f.fecha_factura >= ? OR (f.fecha_factura IS NULL "
                           "AND date(d.registrado_en) >= ?))")
        parametros += [criterio.desde.isoformat()] * 2
    if criterio.sin_objeto:
        condiciones.append(
            "EXISTS (SELECT 1 FROM factura_linea AS l JOIN factura_imputacion AS i "
            "ON i.linea_id = l.id WHERE l.factura_id = f.id AND l.retirada_en IS NULL "
            "AND i.retirada_en IS NULL AND i.objeto_id IS NULL)")
    if criterio.reintentos:
        condiciones.append(
            "EXISTS (SELECT 1 FROM reextraccion_resultado AS r JOIN reextraccion AS x "
            "ON x.id = r.reextraccion_id WHERE r.documento_id = d.id "
            "AND r.resultado = 'reintento' AND x.modelo = ? AND x.prompt_version = ? "
            "AND x.schema_version = ?)")
        parametros += [modelo, prompt, esquema]
    filas = conn.execute(
        "SELECT DISTINCT f.id AS factura_id, d.id, d.sha256, d.nombre_original, d.tipo_mime, "
        "d.bytes, d.ruta_cas FROM factura AS f JOIN documento AS d ON d.id = f.documento_id "
        f"WHERE {' AND '.join(condiciones)} ORDER BY d.id", parametros).fetchall()
    if criterio.proveedor:
        del_proveedor = _del_proveedor(conn, criterio.proveedor)
        filas = [f for f in filas if f["factura_id"] in del_proveedor]

    leidos = {f[0] for f in conn.execute(
        "SELECT documento_id FROM extraccion WHERE modelo = ? AND prompt_version = ? "
        "AND schema_version = ?", (modelo, prompt, esquema))}
    en_lote = en_lotes_sin_recoger(conn)
    vigentes = vigentes_por_documento(conn)
    seleccion = Seleccion()
    for fila in filas:
        if fila["id"] in leidos:
            seleccion.ya_leidos += 1
            seleccion.omitidos.append((fila["id"], "ya leido con estas versiones: no se paga otra "
                                                   "vez"))
        elif fila["id"] in en_lote:
            n = en_lote[fila["id"]]
            seleccion.omitidos.append((fila["id"], f"en un lote sin recoger (reextraccion {n}): "
                                                   f"se recoge con --recoger {n}"))
        elif fila["ruta_cas"] is None:
            seleccion.omitidos.append((fila["id"], "el original no esta guardado (Q4): no se "
                                                   "puede volver a leer"))
        elif criterio.limite is not None and len(seleccion.documentos) >= criterio.limite:
            seleccion.omitidos.append((fila["id"], "fuera del limite"))
        else:
            seleccion.documentos.append(Seleccionado(
                documento_id=fila["id"], sha256=fila["sha256"],
                nombre=fila["nombre_original"] or f"{fila['sha256'][:12]}.pdf",
                tipo_mime=fila["tipo_mime"], bytes=fila["bytes"],
                anterior_id=vigentes.get(fila["id"])))
    return seleccion


def en_lotes_sin_recoger(conn: sqlite3.Connection) -> dict[int, int]:
    """Documento -> reextraccion, de los lotes mandados (o quiza mandados) sin su resultado."""
    salida: dict[int, int] = {}
    for fila in conn.execute("SELECT id, estimacion_json FROM reextraccion WHERE estado IN "
                             "('esperando_lote', 'lote_desconocido') ORDER BY id"):
        apuntados = _apuntados(conn, fila["id"])
        for elegido in json.loads(fila["estimacion_json"]).get("seleccionados", []):
            if elegido["documento_id"] not in apuntados:
                salida.setdefault(elegido["documento_id"], fila["id"])
    return salida


def cargar(almacen: Almacen, seleccion: Seleccion) -> list[SourceDocument]:
    """Los originales de lo seleccionado, del almacen de documentos (cada apertura queda auditada).

    Se cargan una vez y sirven para contar y para leer: abrir dos veces el
    mismo original dejaria dos aperturas por documento.
    """
    from .almacen.documentos import abrir

    actor = usuario_sistema(almacen.conn, "extractor")
    documentos = []
    for elegido in seleccion.documentos:
        contenido = abrir(almacen, elegido.documento_id, actor=actor,
                          motivo="reextraccion: contar y volver a leer")
        documentos.append(SourceDocument(
            path=Path(elegido.nombre), sha256=elegido.sha256, byte_size=len(contenido),
            data_b64=base64.standard_b64encode(contenido).decode("ascii"),
            media_type=elegido.tipo_mime))
    return documentos


# ------------------------------------------------------------ estimacion


def _registros(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Todas las extracciones guardadas, tambien las candidatas: todas se pagaron."""
    return [json.loads(f[0]) for f in conn.execute(
        "SELECT contenido_json FROM extraccion ORDER BY id")]


def estimar(
    client: Any, conn: sqlite3.Connection, documentos: list[SourceDocument],
    objetivo: Objetivo, *, lote: bool, ya_leidos: int = 0,
) -> coste.Estimacion:
    """Lo que costaria leer estos documentos con el objetivo, antes de pagar nada.

    La entrada se cuenta con count_tokens sobre la misma peticion que se va a
    mandar, esquema incluido: es exacta y contar no se cobra. La salida sale
    del historico de esa version del esquema con el mismo esfuerzo
    (coste.estimar_salida), en horquilla; el peor caso, del tope de salida
    de la peticion (max_tokens), que es lo que de verdad se puede llegar a
    pagar. Por lotes, la mitad. `entradas` guarda la de cada documento: la
    pasada sincrona compara el peor caso de cada uno con lo que queda.
    """
    from . import config

    modelo, _prompt, esquema = objetivo
    salida = coste.estimar_salida(coste.leer_documentos(_registros(conn)), modelo=modelo,
                                  esquema=esquema, esfuerzo=config.effort())
    entradas = tuple(coste.contar_entrada(client, build_request(doc, model=modelo))
                     for doc in documentos)
    n = len(documentos)
    return coste.Estimacion(
        modelo=modelo, en_cache=ya_leidos, nuevos=n, entrada=sum(entradas),
        salida_baja=salida.bajo * n, salida_alta=salida.alto * n,
        salida_medida=salida.medida, origen_salida=salida.origen, lote=lote,
        salida_peor=config.max_tokens() * n, entradas=entradas)


def comprobar_presupuesto(estimacion: coste.Estimacion, presupuesto: Decimal) -> None:
    """Se niega si el extremo alto pasa del presupuesto, o si no hay tarifa con que medirlo.

    Por lotes, ademas, si el peor caso pasa del presupuesto: un lote mandado
    se paga entero y no hay como pararlo a medias.
    """
    alto = estimacion.coste_alto
    if alto is None or alto > presupuesto:
        raise PresupuestoInsuficiente(estimacion, presupuesto)
    peor = estimacion.coste_peor
    if estimacion.lote and estimacion.salida_peor and (peor is None or peor > presupuesto):
        raise PresupuestoInsuficiente(
            estimacion, presupuesto,
            f"por lotes no se puede parar a medias: el peor caso del lote (cada documento "
            f"hasta su tope de salida) es ${peor:.4f}")


def _centimos(valor: Decimal | None, *, arriba: bool) -> int:
    if valor is None:
        return 0
    centimos = valor * 100
    return int(math.ceil(centimos) if arriba else math.floor(centimos))


def registrar_rechazo(conn: sqlite3.Connection, error: PresupuestoInsuficiente, *,
                      criterio: Criterio, objetivo: Objetivo,
                      iniciada_por: int | None = None) -> int:
    """Una reextraccion que no se paga por presupuesto queda en la auditoria, con su estimacion."""
    with transaccion(conn):
        return registrar(
            conn, tipo="reextraccion_rechazada", actor=usuario_sistema(conn, "extractor"),
            usuario_id=iniciada_por, resultado="denegado", motivo=str(error),
            datos={"criterio": criterio.a_dict(), "objetivo": list(objetivo),
                   "presupuesto": str(error.presupuesto),
                   "estimacion": _estimacion_json(error.estimacion)})


def _estimacion_json(est: coste.Estimacion) -> dict[str, Any]:
    from . import config

    return {"modelo": est.modelo, "documentos": est.nuevos, "ya_leidos": est.en_cache,
            "entrada": est.entrada, "salida_baja": est.salida_baja,
            "salida_alta": est.salida_alta, "salida_medida": est.salida_medida,
            "origen_salida": est.origen_salida, "lote": est.lote,
            "salida_peor": est.salida_peor, "esfuerzo": config.effort(),
            "max_tokens": config.max_tokens(),
            "coste_bajo": None if est.coste_bajo is None else str(est.coste_bajo),
            "coste_alto": None if est.coste_alto is None else str(est.coste_alto),
            "coste_peor": None if est.coste_peor is None else str(est.coste_peor)}


# ------------------------------------------------------------ la pasada


@dataclass
class ResultadoReextraccion:
    reextraccion_id: int
    via: str
    estado: str
    candidatas: list[tuple[int, int]] = field(default_factory=list)   # (documento, extraccion)
    reintentos: list[tuple[int, str, str]] = field(default_factory=list)  # (doc, motivo, detalle)
    lote_id: str | None = None
    tokens_entrada: int = 0
    tokens_salida: int = 0
    # recoger: el lote todavia no ha terminado, y no se ha cambiado nada.
    sin_terminar: bool = False


def _fila_reextraccion(conn: sqlite3.Connection, reextraccion_id: int) -> sqlite3.Row:
    fila = conn.execute("SELECT * FROM reextraccion WHERE id = ?", (reextraccion_id,)).fetchone()
    if fila is None:
        raise LookupError(f"no hay reextraccion {reextraccion_id}")
    return fila


def _evento_reextraccion(conn: sqlite3.Connection, reextraccion_id: int, tipo: str, *,
                         usuario_id: int | None = None, **datos: Any) -> int:
    """El evento de la pasada, con la foto de su fila tal como queda (es evidencia)."""
    return registrar(conn, tipo=tipo, actor=usuario_sistema(conn, "extractor"),
                     usuario_id=usuario_id, tabla="reextraccion", fila_id=reextraccion_id,
                     datos={**datos, "fila": foto(conn, "reextraccion", reextraccion_id)})


def _iniciar(conn: sqlite3.Connection, seleccion: Seleccion, estimacion: coste.Estimacion,
             presupuesto: Decimal, *, criterio: Criterio, objetivo: Objetivo, via: str,
             iniciada_por: int | None) -> int:
    modelo, prompt, esquema = objetivo
    detalle = {**_estimacion_json(estimacion), "presupuesto": str(presupuesto),
               "seleccionados": [{"documento_id": d.documento_id, "sha256": d.sha256,
                                  "anterior_id": d.anterior_id}
                                 for d in seleccion.documentos]}
    with transaccion(conn):
        reextraccion_id = int(conn.execute(
            "INSERT INTO reextraccion (modelo, prompt_version, schema_version, via, "
            "criterio_json, documentos, presupuesto_usd_cent, estimado_bajo_usd_cent, "
            "estimado_alto_usd_cent, salida_medida, estimacion_json, iniciada_en, iniciada_por, "
            "actor) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (modelo, prompt, esquema, via, json_canonico(criterio.a_dict()),
             len(seleccion.documentos), _centimos(presupuesto, arriba=False),
             _centimos(estimacion.coste_bajo, arriba=False),
             _centimos(estimacion.coste_alto, arriba=True), int(estimacion.salida_medida),
             json_canonico(detalle), marca(reloj_de(conn).ahora()), iniciada_por,
             usuario_sistema(conn, "extractor"))).lastrowid)
        _evento_reextraccion(conn, reextraccion_id, "reextraccion_iniciada",
                             usuario_id=iniciada_por)
    return reextraccion_id


def _apuntar(conn: sqlite3.Connection, reextraccion_id: int, elegido: Seleccionado, *,
             extraccion_id: int | None = None, reintento: Reintento | None = None) -> None:
    """Lo que dio un documento: una candidata o un reintento, con su evento (que lleva la foto)."""
    fila = {"reextraccion_id": reextraccion_id, "documento_id": elegido.documento_id,
            "resultado": "candidata" if extraccion_id is not None else "reintento",
            "extraccion_id": extraccion_id, "anterior_id": elegido.anterior_id,
            "motivo": reintento.motivo if reintento else None,
            "detalle": (reintento.detalle or None) if reintento else None,
            "en": marca(reloj_de(conn).ahora())}
    evento = registrar(conn, tipo="reextraccion_resultado",
                       actor=usuario_sistema(conn, "extractor"), tabla="documento",
                       fila_id=elegido.documento_id, datos={"fila": fila})
    conn.execute(
        "INSERT INTO reextraccion_resultado (reextraccion_id, documento_id, resultado, "
        "extraccion_id, anterior_id, motivo, detalle, en, evento_id) VALUES (:reextraccion_id, "
        ":documento_id, :resultado, :extraccion_id, :anterior_id, :motivo, :detalle, :en, "
        ":evento_id)", {**fila, "evento_id": evento})


def apuntar_relectura(conn: sqlite3.Connection, documento_id: int, extraccion_id: int,
                      origen: dict[str, Any], *, anterior_id: int | None) -> int:
    """La relectura de `extract --force/--estricta` de un documento con vigente de otras versiones.

    Queda como candidata, igual que lo que lee `reextraer`: una reextraccion
    de un documento, terminada, sin presupuesto (extract no lo tiene; lo que
    costo esta en el uso de la extraccion) y con el origen en su criterio.
    Asi solo pasa a vigente con `reextraer --activar`, despues de la puerta.
    Va en la transaccion de quien llama, despues de registrar la extraccion.
    `anterior_id` es la vigente del documento, que quien llama ya sabe.
    """
    fila = conn.execute("SELECT e.modelo, e.prompt_version, e.schema_version, e.via, d.sha256 "
                        "FROM extraccion AS e JOIN documento AS d ON d.id = e.documento_id "
                        "WHERE e.id = ?", (extraccion_id,)).fetchone()
    if conn.execute("SELECT 1 FROM reextraccion_resultado WHERE extraccion_id = ?",
                    (extraccion_id,)).fetchone():
        return extraccion_id                 # ya era candidata (el mismo contenido otra vez)
    elegido = Seleccionado(documento_id=documento_id, sha256=fila["sha256"], nombre="",
                           tipo_mime="", bytes=None, anterior_id=anterior_id)
    criterio = {"origen": "extract", **origen}
    detalle = {"origen": "extract", "seleccionados": [
        {"documento_id": documento_id, "sha256": fila["sha256"],
         "anterior_id": elegido.anterior_id}]}
    with transaccion(conn):
        reextraccion_id = int(conn.execute(
            "INSERT INTO reextraccion (modelo, prompt_version, schema_version, via, "
            "criterio_json, documentos, presupuesto_usd_cent, estimado_bajo_usd_cent, "
            "estimado_alto_usd_cent, salida_medida, estimacion_json, iniciada_en, actor) "
            "VALUES (?, ?, ?, ?, ?, 1, 0, 0, 0, 0, ?, ?, ?)",
            (fila["modelo"], fila["prompt_version"], fila["schema_version"], fila["via"],
             json_canonico(criterio), json_canonico(detalle), marca(reloj_de(conn).ahora()),
             usuario_sistema(conn, "extractor"))).lastrowid)
        _evento_reextraccion(conn, reextraccion_id, "reextraccion_iniciada")
        _apuntar(conn, reextraccion_id, elegido, extraccion_id=extraccion_id)
        _terminar(conn, reextraccion_id,
                  ResultadoReextraccion(reextraccion_id, fila["via"], "en_curso"))
    return extraccion_id


def _guardar_candidata(almacen: Almacen, reextraccion_id: int, elegido: Seleccionado,
                       record: ExtractionRecord, out_dir: Path, via: str) -> int:
    """Exporta la lectura (sin pisar nada) y la guarda en el almacen como candidata.

    Entra el texto del fichero exportado, como en `extract`: el almacen y la
    exportacion tienen el mismo hash.
    """
    destino = record.write_json(out_dir / CARPETA_EXPORTACION)
    texto = destino.read_bytes().decode("utf-8")
    conn = almacen.conn
    with transaccion(conn):
        extraccion = registrar_extraccion(
            conn, leer_registro(texto), documento_id=elegido.documento_id, via=via,
            actor=usuario_sistema(conn, "extractor"))
        _apuntar(conn, reextraccion_id, elegido, extraccion_id=extraccion.id)
    return extraccion.id


def _apuntados(conn: sqlite3.Connection, reextraccion_id: int) -> dict[int, str]:
    """Los documentos de la pasada que ya tienen su resultado apuntado: documento -> resultado."""
    return {f[0]: f[1] for f in conn.execute(
        "SELECT documento_id, resultado FROM reextraccion_resultado WHERE reextraccion_id = ?",
        (reextraccion_id,))}


def _terminar(conn: sqlite3.Connection, reextraccion_id: int,
              resultado: ResultadoReextraccion, *, gastado: Decimal | None = None,
              parada: bool = False) -> None:
    """Cierra la pasada con los recuentos de sus filas, no de lo que se vio en esta llamada.

    Una recogida que se corto a medias y se repite solo ve lo que faltaba:
    contar en memoria dejaria la fila diciendo menos de lo que tiene. El
    evento lleva lo gastado (la via sincrona) y si la pasada se paro por el
    presupuesto.
    """
    extra: dict[str, Any] = {}
    if gastado is not None:
        extra = {"gastado_usd": str(gastado), "parada_por_presupuesto": parada}
    with transaccion(conn):
        apuntados = list(_apuntados(conn, reextraccion_id).values())
        conn.execute(
            "UPDATE reextraccion SET estado = 'terminada', terminada_en = ?, extraidas = ?, "
            "reintentos = ? WHERE id = ?",
            (marca(reloj_de(conn).ahora()), apuntados.count("candidata"),
             apuntados.count("reintento"), reextraccion_id))
        _evento_reextraccion(conn, reextraccion_id, "reextraccion_terminada",
                             tokens_entrada=resultado.tokens_entrada,
                             tokens_salida=resultado.tokens_salida, **extra)
    resultado.estado = "terminada"


def _a_reintentar(conn: sqlite3.Connection, reextraccion_id: int, resultado: ResultadoReextraccion,
                  elegidos: list[Seleccionado], motivo: str, detalle: str) -> None:
    """Todos estos documentos a la lista de reintentos, en una transaccion."""
    with transaccion(conn):
        for elegido in elegidos:
            reintento = Reintento(elegido.sha256, motivo, detalle)
            _apuntar(conn, reextraccion_id, elegido, reintento=reintento)
            resultado.reintentos.append((elegido.documento_id, motivo, detalle))


def _rechazo_definitivo(exc: Exception) -> bool:
    """La API contesto que no (un 4xx): el lote no existe. Sin respuesta, no se sabe.

    Un timeout (408) o un corte de conexion pueden llegar despues de que la
    API aceptara el lote: darlo por no mandado y volver a pedirlo lo pagaria
    dos veces.
    """
    estado = getattr(exc, "status_code", None)
    return isinstance(estado, int) and 400 <= estado < 500 and estado != 408


def _sin_reintentos(client: Any) -> Any:
    """El cliente sin los reintentos automaticos del SDK, para crear el lote.

    Crear un lote no es idempotente: si el SDK repite un POST que llego pero
    cuya respuesta se perdio, quedan dos lotes pagados.
    """
    opciones = getattr(client, "with_options", None)
    return opciones(max_retries=0) if callable(opciones) else client


def _uso_coste(modelo: str, uso: dict[str, Any]) -> Decimal | None:
    entrada, salida = uso.get("input_tokens"), uso.get("output_tokens")
    if not isinstance(entrada, int) or not isinstance(salida, int):
        return None
    return estimate_cost(modelo, entrada, salida, lote=uso.get("service_tier") == "batch")


def ejecutar(
    client: Any,
    almacen: Almacen,
    seleccion: Seleccion,
    documentos: list[SourceDocument],
    estimacion: coste.Estimacion,
    presupuesto: Decimal,
    *,
    criterio: Criterio,
    objetivo: Objetivo,
    out_dir: str | Path,
    lote: bool = False,
    iniciada_por: int | None = None,
    informar: Informar | None = None,
) -> ResultadoReextraccion:
    """Paga la pasada, si el presupuesto lo cubre. Las lecturas quedan como candidatas.

    Sincrona: un documento cada vez, cada uno en su transaccion (lo pagado no
    se pierde si falla el siguiente). Antes de cada llamada se compara lo ya
    gastado mas el peor caso de ese documento (su entrada contada y todo su
    max_tokens de salida) con el presupuesto: si no cabe, ni ese ni los
    siguientes se pagan, y van a reintentos ("presupuesto"). Lo gastado es
    el uso de cada respuesta, tambien de un rechazo; de un fallo sin uso
    (no se sabe si se cobro) se cuenta su peor caso.

    Por lotes: manda el lote (el peor caso entero ya cabe: comprobar_presupuesto)
    y deja la pasada esperando; `recoger` lee los resultados. Si la API dice
    que no, todo va a reintentos; si no contesta, no se sabe si lo acepto, y
    la pasada queda en 'lote_desconocido' hasta que `recoger` lo encuentra.
    """
    from . import config

    comprobar_presupuesto(estimacion, presupuesto)
    if tuple(objetivo[1:]) != tuple(objetivo_actual()[1:]):
        raise ValueError("solo se lee con el prompt y el esquema de config.py: "
                         f"{objetivo_actual()[1:]}, no {tuple(objetivo[1:])}")
    avisar = informar or (lambda _tipo, _nombre, _detalle: None)
    conn = almacen.conn
    via = "lote" if lote else "api"
    modelo = objetivo[0]
    reextraccion_id = _iniciar(conn, seleccion, estimacion, presupuesto, criterio=criterio,
                               objetivo=objetivo, via=via, iniciada_por=iniciada_por)
    resultado = ResultadoReextraccion(reextraccion_id, via, "en_curso")
    out_dir = Path(out_dir)

    if lote:
        peticiones = [construir_peticion_lote(doc, model=modelo) for doc in documentos]
        try:
            enviado = _sin_reintentos(client).messages.batches.create(requests=peticiones)
        except Exception as exc:
            if _rechazo_definitivo(exc):    # no se mando: todo a reintentar, nada pagado
                _a_reintentar(conn, reextraccion_id, resultado, seleccion.documentos,
                              REINTENTO_ERROR, f"el lote no se pudo mandar: {type(exc).__name__}")
                _terminar(conn, reextraccion_id, resultado)
                return resultado
            with transaccion(conn):
                conn.execute("UPDATE reextraccion SET estado = 'lote_desconocido' WHERE id = ?",
                             (reextraccion_id,))
                _evento_reextraccion(conn, reextraccion_id, "reextraccion_lote_desconocido",
                                     usuario_id=iniciada_por,
                                     error=f"{type(exc).__name__}: {exc}")
            resultado.estado = "lote_desconocido"
            avisar("lote", "?", f"sin respuesta al mandarlo ({type(exc).__name__}): "
                                f"--recoger {reextraccion_id} lo busca en la API")
            return resultado
        resultado.lote_id = str(getattr(enviado, "id"))
        with transaccion(conn):
            conn.execute("UPDATE reextraccion SET lote_id = ?, estado = 'esperando_lote' "
                         "WHERE id = ?", (resultado.lote_id, reextraccion_id))
            _evento_reextraccion(conn, reextraccion_id, "reextraccion_lote_enviado",
                                 usuario_id=iniciada_por, lote_id=resultado.lote_id)
        resultado.estado = "esperando_lote"
        avisar("lote", resultado.lote_id, f"{len(peticiones)} documentos")
        return resultado

    tope = config.max_tokens()
    entradas = list(estimacion.entradas) or [0] * len(documentos)
    gastado, parada = Decimal(0), False
    pares = list(zip(seleccion.documentos, documentos))
    for posicion, (elegido, doc) in enumerate(pares):
        peor = estimate_cost(modelo, entradas[posicion] if posicion < len(entradas) else 0, tope)
        if peor is None or gastado + peor > presupuesto:
            parada = True
            restantes = [e for e, _d in pares[posicion:]]
            _a_reintentar(conn, reextraccion_id, resultado, restantes, REINTENTO_PRESUPUESTO,
                          f"no se paga: ${gastado:.4f} gastados mas el peor caso de un documento "
                          f"pasa del presupuesto (${presupuesto:.2f})")
            avisar("reintento", elegido.nombre, f"presupuesto: {len(restantes)} sin pagar")
            break
        try:
            record = extract_invoice(client, doc, model=modelo)
        except Exception as exc:  # una pasada no se detiene por un documento
            # Un rechazo se cobra y trae su uso; un fallo sin uso no se sabe si
            # se cobro, y se cuenta como si si, por su peor caso.
            uso = getattr(exc, "uso", None) or {}
            gastado += _uso_coste(modelo, uso) or peor
            resultado.tokens_entrada += uso.get("input_tokens") or 0
            resultado.tokens_salida += uso.get("output_tokens") or 0
            motivo = REINTENTO_RECHAZO if isinstance(exc, Rechazado) else REINTENTO_ERROR
            _a_reintentar(conn, reextraccion_id, resultado, [elegido], motivo,
                          f"{type(exc).__name__}: {exc}")
            avisar("reintento", elegido.nombre, resultado.reintentos[-1][2])
            continue
        gastado += _uso_coste(modelo, record.usage) or peor
        resultado.tokens_entrada += record.usage.get("input_tokens") or 0
        resultado.tokens_salida += record.usage.get("output_tokens") or 0
        try:
            extraccion_id = _guardar_candidata(almacen, reextraccion_id, elegido, record,
                                               out_dir, via)
        except Exception as exc:
            # Lo pagado sigue exportado en out/reextraccion/, y el documento
            # vuelve a pedirse con --reintentos.
            _a_reintentar(conn, reextraccion_id, resultado, [elegido], REINTENTO_ERROR,
                          f"{type(exc).__name__}: {exc}")
            avisar("reintento", elegido.nombre, resultado.reintentos[-1][2])
            continue
        resultado.candidatas.append((elegido.documento_id, extraccion_id))
        avisar("candidata", elegido.nombre, f"extraccion {extraccion_id}")
    _terminar(conn, reextraccion_id, resultado, gastado=gastado, parada=parada)
    return resultado


def pendientes_de_lote(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Las reextracciones por lotes que esperan sus resultados (o saber si se mandaron)."""
    return conn.execute("SELECT * FROM reextraccion WHERE estado IN ('esperando_lote', "
                        "'lote_desconocido') ORDER BY id").fetchall()


# Cuanto antes o despues de empezar la pasada puede decir la API que se creo
# su lote: los relojes de aqui y de la API no son el mismo.
MARGEN_LOTE_DESCONOCIDO = timedelta(hours=1)


def _instante(valor: Any) -> datetime | None:
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else None
    try:
        instante = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    return instante if instante.tzinfo else None


def _peticiones_de(lote: Any) -> int:
    cuentas = getattr(lote, "request_counts", None)
    return sum(int(getattr(cuentas, c, 0) or 0)
               for c in ("processing", "succeeded", "errored", "canceled", "expired"))


def _buscar_lote(client: Any, conn: sqlite3.Connection, fila: sqlite3.Row) -> list[str]:
    """Los lotes de la API que pueden ser el de una pasada sin respuesta al mandarlo.

    Se crearon cerca de cuando empezo la pasada, tienen tantas peticiones
    como documentos, y no son ya el lote de otra pasada. La lista de la API
    va de mas nuevo a mas viejo: se deja de mirar al pasar el margen.
    """
    inicio = _instante(fila["iniciada_en"])
    desde, hasta = inicio - MARGEN_LOTE_DESCONOCIDO, inicio + MARGEN_LOTE_DESCONOCIDO
    usados = {f[0] for f in conn.execute(
        "SELECT lote_id FROM reextraccion WHERE lote_id IS NOT NULL")}
    candidatos = []
    for lote in client.messages.batches.list(limit=100):
        creado = _instante(getattr(lote, "created_at", None))
        if creado is None:
            continue
        if creado < desde:
            break
        if (creado <= hasta and _peticiones_de(lote) == fila["documentos"]
                and str(getattr(lote, "id", "")) not in usados):
            candidatos.append(str(lote.id))
    return candidatos


def _reconciliar(client: Any, almacen: Almacen, fila: sqlite3.Row,
                 resultado: ResultadoReextraccion) -> bool:
    """Una pasada en 'lote_desconocido': busca su lote en la API. True si lo encontro.

    Si esta, se adopta su id y la pasada espera como cualquier otra. Si no
    esta, no se mando: sus documentos van a reintentos, sin haber pagado
    nada. Si hay mas de uno que podria ser, no se elige: lo decide una
    persona mirando la consola de la API.
    """
    conn = almacen.conn
    candidatos = _buscar_lote(client, conn, fila)
    if len(candidatos) > 1:
        raise ValueError(f"la reextraccion {fila['id']} no tuvo respuesta al mandar su lote, y "
                         f"hay {len(candidatos)} lotes en la API que podrian ser el suyo: "
                         + ", ".join(candidatos))
    if not candidatos:
        detalle = json.loads(fila["estimacion_json"])
        elegidos = [_seleccionado(conn, e) for e in detalle.get("seleccionados", [])]
        apuntados = _apuntados(conn, fila["id"])
        _a_reintentar(conn, fila["id"], resultado,
                      [e for e in elegidos if e.documento_id not in apuntados], REINTENTO_ERROR,
                      "el lote no llego a la API: no se mando, y no se pago")
        _terminar(conn, fila["id"], resultado)
        return False
    resultado.lote_id = candidatos[0]
    with transaccion(conn):
        conn.execute("UPDATE reextraccion SET lote_id = ?, estado = 'esperando_lote' "
                     "WHERE id = ?", (resultado.lote_id, fila["id"]))
        _evento_reextraccion(conn, fila["id"], "reextraccion_lote_encontrado",
                             lote_id=resultado.lote_id)
    resultado.estado = "esperando_lote"
    return True


def _seleccionado(conn: sqlite3.Connection, elegido: dict[str, Any]) -> Seleccionado:
    doc = conn.execute("SELECT nombre_original, tipo_mime, bytes FROM documento "
                       "WHERE id = ?", (elegido["documento_id"],)).fetchone()
    return Seleccionado(
        documento_id=elegido["documento_id"], sha256=elegido["sha256"],
        nombre=doc["nombre_original"] or f"{elegido['sha256'][:12]}.pdf",
        tipo_mime=doc["tipo_mime"], bytes=doc["bytes"], anterior_id=elegido["anterior_id"])


def recoger(client: Any, almacen: Almacen, reextraccion_id: int, *,
            out_dir: str | Path, informar: Informar | None = None) -> ResultadoReextraccion:
    """Lee los resultados de un lote que ha terminado y los guarda como candidatas o reintentos.

    Si el lote no ha terminado, no cambia nada. Cada resultado se ata a su
    documento por custom_id (el sha256 del documento): llegan en cualquier
    orden. Un documento del lote que no tiene resultado tambien va a
    reintentos. Una pasada cuyo lote no se sabe si se mando lo busca antes
    en la API (_reconciliar).

    Cada resultado se guarda en su transaccion, y la pasada sigue esperando
    hasta el final: si algo corta la recogida a medias (un disco lleno, un
    Ctrl-C), repetirla salta los documentos que ya tienen su resultado
    apuntado. Sin eso, el mismo contenido chocaria con su candidata (y la
    recogida no podria terminar nunca) o, leido otro dia, entraria dos veces
    y `coste` lo contaria pagado dos veces.
    """
    avisar = informar or (lambda _tipo, _nombre, _detalle: None)
    conn = almacen.conn
    fila = _fila_reextraccion(conn, reextraccion_id)
    resultado = ResultadoReextraccion(reextraccion_id, fila["via"], fila["estado"],
                                      lote_id=fila["lote_id"])
    if fila["estado"] == "lote_desconocido":
        if not _reconciliar(client, almacen, fila, resultado):
            return resultado
        fila = _fila_reextraccion(conn, reextraccion_id)
    if fila["estado"] != "esperando_lote":
        raise ValueError(f"la reextraccion {reextraccion_id} no espera ningun lote "
                         f"(esta {fila['estado']})")
    lote = client.messages.batches.retrieve(fila["lote_id"])
    if getattr(lote, "processing_status", None) != "ended":
        resultado.sin_terminar = True
        return resultado

    detalle = json.loads(fila["estimacion_json"])
    por_sha = {e["sha256"]: _seleccionado(conn, e) for e in detalle.get("seleccionados", [])}
    apuntados = _apuntados(conn, reextraccion_id)
    vistos = {sha for sha, elegido in por_sha.items() if elegido.documento_id in apuntados}
    for individual in client.messages.batches.results(fila["lote_id"]):
        sha = getattr(individual, "custom_id", None)
        elegido = por_sha.get(sha)
        if elegido is None or sha in vistos:
            continue
        vistos.add(sha)
        doc = SourceDocument(path=Path(elegido.nombre), sha256=sha,
                             byte_size=elegido.bytes or 0, data_b64="",
                             media_type=elegido.tipo_mime)
        leido = leer_resultado_lote(individual, doc, model=fila["modelo"],
                                    prompt_version=fila["prompt_version"],
                                    schema_version=fila["schema_version"],
                                    esfuerzo=detalle.get("esfuerzo"),
                                    max_tokens=detalle.get("max_tokens"))
        if isinstance(leido, Reintento):
            _a_reintentar(conn, reextraccion_id, resultado, [elegido], leido.motivo,
                          leido.detalle)
            avisar("reintento", elegido.nombre, leido.detalle)
            continue
        try:
            extraccion_id = _guardar_candidata(almacen, reextraccion_id, elegido, leido,
                                               Path(out_dir), "lote")
        except RegistroInvalido as exc:
            _a_reintentar(conn, reextraccion_id, resultado, [elegido], "invalido", str(exc))
            continue
        resultado.candidatas.append((elegido.documento_id, extraccion_id))
        resultado.tokens_entrada += leido.usage.get("input_tokens") or 0
        resultado.tokens_salida += leido.usage.get("output_tokens") or 0
        avisar("candidata", elegido.nombre, f"extraccion {extraccion_id}")
    sin_resultado = [e for sha, e in por_sha.items() if sha not in vistos]
    if sin_resultado:
        _a_reintentar(conn, reextraccion_id, resultado, sin_resultado, REINTENTO_ERROR,
                      "el lote no trajo resultado")
    _terminar(conn, reextraccion_id, resultado)
    return resultado


# ------------------------------------------------------------ la puerta y la activacion


def registros_vigentes_posibles(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Las extracciones que pueden ser la vigente: todas menos las candidatas sin activar."""
    from .almacen.extracciones import en_orden_de_out

    return [json.loads(f["contenido_json"]) for f in en_orden_de_out(conn)]


def comparar(conn: sqlite3.Connection, truth: dict[str, dict[str, Any]], objetivo: Objetivo, *,
             inyeccion: str = scoring.INYECCION) -> scoring.Comparacion:
    """`score --comparar-versiones` sobre el almacen.

    La nueva sale de todas las extracciones (sus candidatas incluidas); la
    anterior, de las que pueden ser la vigente: una candidata de otra
    version que nadie activo (un prompt rechazado) no es la referencia con
    la que se mide "no peor que la anterior".
    """
    return scoring.comparar_versiones(truth, _registros(conn), objetivo, inyeccion=inyeccion,
                                      anteriores=registros_vigentes_posibles(conn))


def resumen_comparacion(comparacion: scoring.Comparacion) -> dict[str, Any]:
    """Lo que dejo pasar (o no) la puerta, en una forma que se puede hashear y guardar."""
    return {
        "objetivo": list(comparacion.objetivo),
        "documentos": sorted(d.source_name for d in comparacion.nueva.documents),
        "critica_anterior": str(comparacion.anterior.critical_accuracy()),
        "critica_nueva": str(comparacion.nueva.critical_accuracy()),
        "aciertos_anterior": comparacion.anterior.hits(),
        "aciertos_nueva": comparacion.nueva.hits(),
        "inyeccion": comparacion.inyeccion,
        "inyeccion_fallo": comparacion.inyeccion_fallo,
        "umbral": str(comparacion.umbral),
        "motivos": comparacion.motivos,
    }


@dataclass(frozen=True)
class Activada:
    documento_id: int
    extraccion_id: int
    anterior_id: int | None
    factura_id: int | None
    accion: str
    contradichos: tuple[str, ...]      # valores manuales que la lectura nueva contradice (M1)
    sin_casar: tuple[int, ...]         # lineas editadas que no se pudieron casar (M2)


@dataclass
class ResultadoActivacion:
    comparacion: scoring.Comparacion
    comparacion_sha256: str
    activadas: list[Activada] = field(default_factory=list)
    diferencia: Any = None             # la pasada del motor (hallazgos.Diferencia)


def candidatas_pendientes(conn: sqlite3.Connection, objetivo: Objetivo) -> list[sqlite3.Row]:
    """La ultima candidata sin activar de cada documento, de las versiones objetivo."""
    modelo, prompt, esquema = objetivo
    return conn.execute(
        "SELECT r.documento_id, r.extraccion_id FROM reextraccion_resultado AS r "
        "JOIN extraccion AS e ON e.id = r.extraccion_id "
        "WHERE r.resultado = 'candidata' AND e.modelo = ? AND e.prompt_version = ? "
        "AND e.schema_version = ? "
        "AND NOT EXISTS (SELECT 1 FROM activacion AS a WHERE a.documento_id = r.documento_id "
        "                AND a.extraccion_id = r.extraccion_id) "
        "AND r.id = (SELECT max(o.id) FROM reextraccion_resultado AS o "
        "            JOIN extraccion AS oe ON oe.id = o.extraccion_id "
        "            WHERE o.documento_id = r.documento_id AND o.resultado = 'candidata' "
        "              AND oe.modelo = e.modelo AND oe.prompt_version = e.prompt_version "
        "              AND oe.schema_version = e.schema_version) "
        "ORDER BY r.documento_id", (modelo, prompt, esquema)).fetchall()


def activar(
    almacen: Almacen,
    persona_id: int,
    truth: dict[str, dict[str, Any]],
    *,
    objetivo: Objetivo | None = None,
    inyeccion: str = scoring.INYECCION,
) -> ResultadoActivacion:
    """Pasa a vigentes las candidatas de una version, si pasa la puerta.

    Lo firma una persona con admin. La puerta (scoring.comparar_versiones)
    se evalua sobre las respuestas escritas a mano; si no pasa, no se activa
    nada y el intento queda en la auditoria con sus motivos. Si pasa, cada
    candidata pendiente queda activada con el hash de la comparacion y su
    factura se vuelve a tipar con ella: lo manual no se pisa (M1 si la
    lectura nueva lo contradice), las lineas se casan por su huella y lo
    que no se puede casar queda para M2. Todo en una transaccion, con su
    recalculo al final: o se activan todas las candidatas pendientes con su
    factura al dia, o ninguna.
    """
    from .hallazgos import recalcular
    from .ingesta import tipar_documento, vigentes_por_documento
    from .permisos import exigir, orden_auditada

    conn = almacen.conn
    objetivo = objetivo or objetivo_actual()
    comparacion = comparar(conn, truth, objetivo, inyeccion=inyeccion)
    resumen = resumen_comparacion(comparacion)
    huella = sha256_texto(json_canonico(resumen))
    resultado = ResultadoActivacion(comparacion, huella)

    with orden_auditada(conn):
        exigir(conn, persona_id, "admin", accion="activar una reextraccion")
    if not comparacion.aprobada:
        with transaccion(conn):
            registrar(conn, tipo="activacion_rechazada", actor=persona_id, usuario_id=persona_id,
                      resultado="denegado", motivo="; ".join(comparacion.motivos),
                      datos={"comparacion": resumen, "comparacion_sha256": huella})
        raise PuertaCerrada(comparacion)

    with orden_auditada(conn):
        vigentes = vigentes_por_documento(conn)
        ultimo_evento = None
        for pendiente in candidatas_pendientes(conn, objetivo):
            documento_id, extraccion_id = pendiente["documento_id"], pendiente["extraccion_id"]
            with transaccion(conn):
                fila = {"extraccion_id": extraccion_id, "documento_id": documento_id,
                        "anterior_id": vigentes.get(documento_id),
                        "comparacion_sha256": huella, "usuario_id": persona_id,
                        "en": marca(reloj_de(conn).ahora())}
                evento = registrar(conn, tipo="extraccion_activada", actor=persona_id,
                                   usuario_id=persona_id, tabla="extraccion",
                                   fila_id=extraccion_id,
                                   datos={"fila": fila, "comparacion": resumen})
                conn.execute(
                    "INSERT INTO activacion (extraccion_id, documento_id, anterior_id, "
                    "comparacion_sha256, usuario_id, en, evento_id) VALUES (:extraccion_id, "
                    ":documento_id, :anterior_id, :comparacion_sha256, :usuario_id, :en, "
                    ":evento_id)", {**fila, "evento_id": evento})
                tipado = tipar_documento(conn, documento_id, extraccion_id=extraccion_id)
                ultimo_evento = evento
            resultado.activadas.append(Activada(
                documento_id=documento_id, extraccion_id=extraccion_id,
                anterior_id=fila["anterior_id"], factura_id=tipado.factura_id,
                accion=tipado.accion, contradichos=tipado.contradichos,
                sin_casar=tipado.sin_casar))
        if resultado.activadas:
            resultado.diferencia = recalcular(conn, motivo="ingesta", usuario_id=persona_id,
                                              causa_evento_id=ultimo_evento)
    return resultado
