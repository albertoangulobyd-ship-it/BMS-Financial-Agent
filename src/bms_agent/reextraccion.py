"""Volver a leer documentos ya leidos: con presupuesto, sin pisar nada y sin cambiar lo vigente hasta la puerta.

Es lo unico del agente que vuelve a pagar por un documento que ya tiene una
extraccion (spec §3.18 y §10). Por eso va aparte de `extract`, que con la
politica CONSERVAR nunca vuelve a pagar lo ya leido, y por eso tiene tres
frenos:

1. Presupuesto. Antes de pagar nada se cuentan los tokens de entrada de
   cada documento con count_tokens (exacto, y contar no se cobra) y se
   estima la salida con el historico de la misma version del esquema (o,
   sin historico, con un factor declarado y la marca "sin medir"). Si el
   extremo alto de la horquilla pasa del presupuesto, no se paga nada. Sin
   presupuesto, solo se estima. La base tampoco admite una reextraccion cuya
   estimacion alta pase de su presupuesto.
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
from datetime import date
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
    REINTENTO_RECHAZO,
    ExtractionRecord,
    Rechazado,
    Reintento,
    build_request,
    construir_peticion_lote,
    extract_invoice,
    leer_resultado_lote,
)
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
    """La estimacion alta pasa del presupuesto (o no hay tarifa): no se paga nada."""

    def __init__(self, estimacion: coste.Estimacion, presupuesto: Decimal) -> None:
        self.estimacion, self.presupuesto = estimacion, presupuesto
        alto = estimacion.coste_alto
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
    mismas versiones (vigente, candidata o activada), y no se puede leer uno
    cuyo original no esta guardado (Q4). Los dos casos se dicen. El orden es
    el de los documentos, y el limite se aplica al final.
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
    vigentes = vigentes_por_documento(conn)
    seleccion = Seleccion()
    for fila in filas:
        if fila["id"] in leidos:
            seleccion.ya_leidos += 1
            seleccion.omitidos.append((fila["id"], "ya leido con estas versiones: no se paga otra "
                                                   "vez"))
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
    del historico de esa version del esquema (coste.estimar_salida), en
    horquilla. Por lotes, la mitad.
    """
    modelo, _prompt, esquema = objetivo
    salida = coste.estimar_salida(coste.leer_documentos(_registros(conn)), modelo=modelo,
                                  esquema=esquema)
    entrada = sum(coste.contar_entrada(client, build_request(doc, model=modelo))
                  for doc in documentos)
    n = len(documentos)
    return coste.Estimacion(
        modelo=modelo, en_cache=ya_leidos, nuevos=n, entrada=entrada,
        salida_baja=salida.bajo * n, salida_alta=salida.alto * n,
        salida_medida=salida.medida, origen_salida=salida.origen, lote=lote)


def comprobar_presupuesto(estimacion: coste.Estimacion, presupuesto: Decimal) -> None:
    """Se niega si el extremo alto pasa del presupuesto, o si no hay tarifa con que medirlo."""
    alto = estimacion.coste_alto
    if alto is None or alto > presupuesto:
        raise PresupuestoInsuficiente(estimacion, presupuesto)


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
    return {"modelo": est.modelo, "documentos": est.nuevos, "ya_leidos": est.en_cache,
            "entrada": est.entrada, "salida_baja": est.salida_baja,
            "salida_alta": est.salida_alta, "salida_medida": est.salida_medida,
            "origen_salida": est.origen_salida, "lote": est.lote,
            "coste_bajo": None if est.coste_bajo is None else str(est.coste_bajo),
            "coste_alto": None if est.coste_alto is None else str(est.coste_alto)}


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


def _terminar(conn: sqlite3.Connection, reextraccion_id: int,
              resultado: ResultadoReextraccion) -> None:
    with transaccion(conn):
        conn.execute(
            "UPDATE reextraccion SET estado = 'terminada', terminada_en = ?, extraidas = ?, "
            "reintentos = ? WHERE id = ?",
            (marca(reloj_de(conn).ahora()), len(resultado.candidatas), len(resultado.reintentos),
             reextraccion_id))
        _evento_reextraccion(conn, reextraccion_id, "reextraccion_terminada",
                             tokens_entrada=resultado.tokens_entrada,
                             tokens_salida=resultado.tokens_salida)
    resultado.estado = "terminada"


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
    se pierde si falla el siguiente). Por lotes: manda el lote y deja la
    pasada esperando; `recoger` lee los resultados.
    """
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
            enviado = client.messages.batches.create(requests=peticiones)
        except Exception as exc:  # no se mando: todo a reintentar, nada pagado
            with transaccion(conn):
                for elegido in seleccion.documentos:
                    reintento = Reintento(elegido.sha256, REINTENTO_ERROR,
                                          f"el lote no se pudo mandar: {type(exc).__name__}")
                    _apuntar(conn, reextraccion_id, elegido, reintento=reintento)
                    resultado.reintentos.append((elegido.documento_id, reintento.motivo,
                                                 reintento.detalle))
            _terminar(conn, reextraccion_id, resultado)
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

    for elegido, doc in zip(seleccion.documentos, documentos):
        try:
            record = extract_invoice(client, doc, model=modelo)
            resultado.tokens_entrada += record.usage.get("input_tokens") or 0
            resultado.tokens_salida += record.usage.get("output_tokens") or 0
            extraccion_id = _guardar_candidata(almacen, reextraccion_id, elegido, record,
                                               out_dir, via)
        except Exception as exc:  # una pasada no se detiene por un documento
            # Un rechazo es un reintento con su motivo; cualquier otro fallo, un
            # error. Si lo que fallo fue guardarla, lo pagado sigue exportado en
            # out/reextraccion/, y el documento vuelve a pedirse con --reintentos.
            motivo = REINTENTO_RECHAZO if isinstance(exc, Rechazado) else REINTENTO_ERROR
            reintento = Reintento(doc.sha256, motivo, f"{type(exc).__name__}: {exc}")
            with transaccion(conn):
                _apuntar(conn, reextraccion_id, elegido, reintento=reintento)
            resultado.reintentos.append((elegido.documento_id, reintento.motivo,
                                         reintento.detalle))
            avisar("reintento", elegido.nombre, reintento.detalle)
            continue
        resultado.candidatas.append((elegido.documento_id, extraccion_id))
        avisar("candidata", elegido.nombre, f"extraccion {extraccion_id}")
    _terminar(conn, reextraccion_id, resultado)
    return resultado


def pendientes_de_lote(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Las reextracciones por lotes que esperan sus resultados."""
    return conn.execute("SELECT * FROM reextraccion WHERE estado = 'esperando_lote' "
                        "ORDER BY id").fetchall()


def recoger(client: Any, almacen: Almacen, reextraccion_id: int, *,
            out_dir: str | Path, informar: Informar | None = None) -> ResultadoReextraccion:
    """Lee los resultados de un lote que ha terminado y los guarda como candidatas o reintentos.

    Si el lote no ha terminado, no cambia nada. Cada resultado se ata a su
    documento por custom_id (el sha256 del documento): llegan en cualquier
    orden. Un documento del lote que no tiene resultado tambien va a
    reintentos.
    """
    avisar = informar or (lambda _tipo, _nombre, _detalle: None)
    conn = almacen.conn
    fila = _fila_reextraccion(conn, reextraccion_id)
    resultado = ResultadoReextraccion(reextraccion_id, fila["via"], fila["estado"],
                                      lote_id=fila["lote_id"])
    if fila["estado"] != "esperando_lote":
        raise ValueError(f"la reextraccion {reextraccion_id} no espera ningun lote "
                         f"(esta {fila['estado']})")
    lote = client.messages.batches.retrieve(fila["lote_id"])
    if getattr(lote, "processing_status", None) != "ended":
        resultado.sin_terminar = True
        return resultado

    detalle = json.loads(fila["estimacion_json"])
    por_sha = {}
    for elegido in detalle.get("seleccionados", []):
        doc = conn.execute("SELECT nombre_original, tipo_mime, bytes FROM documento "
                           "WHERE id = ?", (elegido["documento_id"],)).fetchone()
        por_sha[elegido["sha256"]] = Seleccionado(
            documento_id=elegido["documento_id"], sha256=elegido["sha256"],
            nombre=doc["nombre_original"] or f"{elegido['sha256'][:12]}.pdf",
            tipo_mime=doc["tipo_mime"], bytes=doc["bytes"], anterior_id=elegido["anterior_id"])
    vistos = set()
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
                                    schema_version=fila["schema_version"])
        if isinstance(leido, Reintento):
            with transaccion(conn):
                _apuntar(conn, reextraccion_id, elegido, reintento=leido)
            resultado.reintentos.append((elegido.documento_id, leido.motivo, leido.detalle))
            avisar("reintento", elegido.nombre, leido.detalle)
            continue
        try:
            extraccion_id = _guardar_candidata(almacen, reextraccion_id, elegido, leido,
                                               Path(out_dir), "lote")
        except RegistroInvalido as exc:
            reintento = Reintento(sha, "invalido", str(exc))
            with transaccion(conn):
                _apuntar(conn, reextraccion_id, elegido, reintento=reintento)
            resultado.reintentos.append((elegido.documento_id, reintento.motivo, str(exc)))
            continue
        resultado.candidatas.append((elegido.documento_id, extraccion_id))
        resultado.tokens_entrada += leido.usage.get("input_tokens") or 0
        resultado.tokens_salida += leido.usage.get("output_tokens") or 0
        avisar("candidata", elegido.nombre, f"extraccion {extraccion_id}")
    for sha, elegido in por_sha.items():
        if sha not in vistos:
            reintento = Reintento(sha, REINTENTO_ERROR, "el lote no trajo resultado")
            with transaccion(conn):
                _apuntar(conn, reextraccion_id, elegido, reintento=reintento)
            resultado.reintentos.append((elegido.documento_id, reintento.motivo,
                                         reintento.detalle))
    _terminar(conn, reextraccion_id, resultado)
    return resultado


# ------------------------------------------------------------ la puerta y la activacion


def comparar(conn: sqlite3.Connection, truth: dict[str, dict[str, Any]], objetivo: Objetivo, *,
             inyeccion: str = scoring.INYECCION) -> scoring.Comparacion:
    """`score --comparar-versiones` sobre el almacen: todas las extracciones, candidatas incluidas."""
    return scoring.comparar_versiones(truth, _registros(conn), objetivo, inyeccion=inyeccion)


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
