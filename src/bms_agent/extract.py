"""Llamada de extraccion.

Propiedad de seguridad de este modulo: la peticion NO lleva herramientas.
El proceso que lee contenido de terceros no tiene con que actuar. Su unica
salida posible es un objeto validado contra el esquema.

build_request es una funcion pura precisamente para poder comprobar esa
propiedad en un test, sin llamar a la API. La peticion de lote
(construir_peticion_lote) tambien: misma entrada, mismo esquema, mismo
esfuerzo y ninguna herramienta, con el hash del documento como custom_id.

Lo que se extrae no se sobrescribe nunca. Cada extraccion va a su propio
fichero, nombrado por el hash del documento y por las versiones que la
produjeron, y si ese nombre ya existe se anade otro al lado. Es la evidencia
de lo que se leyo: una pasada nueva no puede borrar la anterior.

Con un almacen, cada documento de la pasada entra tambien alli: el PDF en el
almacen de documentos y la extraccion (nueva o reutilizada de out/) con el
mismo texto que el fichero. out/ sigue escribiendose igual: la puntuacion y
el coste leen de ahi, y es lo que leen el panel y el informe si no hay
almacen. La factura tipada la hace ingesta.py despues de esta pasada.
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import config
from .cache import CONSERVAR, CachedExtraction, indexar, reutilizable
from .documents import SourceDocument, UnsupportedDocument, load_pdf
from .prompts import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_TEXT
from .schema import InvoiceExtraction, esquema_json

if TYPE_CHECKING:
    from .almacen import Almacen


@dataclass
class ExtractionRecord:
    """Extraccion mas su procedencia. Esto es lo que se guarda."""

    source_sha256: str
    source_name: str
    model: str
    prompt_version: str
    schema_version: str
    extracted_at: str
    extraction: InvoiceExtraction
    usage: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_sha256": self.source_sha256,
            "source_name": self.source_name,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
            "extracted_at": self.extracted_at,
            "request_id": self.request_id,
            "usage": self.usage,
            "extraction": self.extraction.model_dump(mode="json"),
        }

    def contenido(self) -> str:
        """El texto exacto que se guarda, en out/ y en el almacen: el mismo en los dos."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def write_json(self, out_dir: str | Path) -> Path:
        """Guarda la extraccion sin pisar ninguna otra.

        El nombre lleva el hash y las versiones, asi que una extraccion de
        otro modelo, prompt o esquema nunca cae en el mismo fichero. Si el
        nombre ya existe (un --force con las mismas versiones), se anade un
        sufijo en vez de sobrescribir. El fichero se crea en modo exclusivo:
        ni dos procesos a la vez pueden pisarse.

        Se escribe con newline='': sin el, Windows pondria CRLF y los bytes
        del fichero ya no serian contenido(), que es lo que va al almacen.
        importar-out hashea los bytes, y la misma extraccion entraria otra vez.
        """
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        contenido = self.contenido()
        base = nombre_fichero(
            self.source_sha256, self.model, self.prompt_version, self.schema_version
        )
        numero = 1
        while True:
            target = out_dir / (base if numero == 1 else f"{base[:-5]}__{numero}.json")
            try:
                with target.open("x", encoding="utf-8", newline="") as fichero:
                    fichero.write(contenido)
                return target
            except FileExistsError:
                if _mismo_contenido(target, contenido):
                    return target
                numero += 1


def _trozo(texto: str) -> str:
    """Una version convertida en algo que vale como trozo de nombre de fichero."""
    return re.sub(r"[^A-Za-z0-9.-]+", "-", str(texto)).strip("-") or "x"


def nombre_fichero(
    sha256: str, model: str, prompt_version: str, schema_version: str
) -> str:
    """Nombre de una extraccion: hash del documento y las tres versiones.

    Por ejemplo 3573674ab6f9__claude-opus-5__extract-2026-09-17.1__s1.json.
    El hash va delante para que las extracciones de un mismo documento salgan
    juntas al listar la carpeta.
    """
    return (
        f"{sha256[:12]}__{_trozo(model)}__{_trozo(prompt_version)}"
        f"__s{_trozo(schema_version)}.json"
    )


def _mismo_contenido(ruta: Path, contenido: str) -> bool:
    """Byte a byte: read_text cambiaria CRLF por LF y daria por igual lo que no lo es."""
    try:
        return ruta.read_bytes() == contenido.encode("utf-8")
    except OSError:
        return False


def _mensajes(doc: SourceDocument) -> list[dict[str, Any]]:
    """El documento y la orden de extraer. El PDF va antes del texto."""
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": doc.media_type,
                        "data": doc.data_b64,
                    },
                },
                {"type": "text", "text": EXTRACTION_USER_TEXT},
            ],
        }
    ]


def build_request(doc: SourceDocument, model: str | None = None) -> dict[str, Any]:
    """Construye los argumentos de la llamada. Sin herramientas, a proposito.

    output_config lleva el esfuerzo, siempre explicito (config.effort); el SDK
    le anade el esquema de output_format al mandarla (messages.parse). No hay
    `thinking`: en Opus 5.5 no se puede apagar, y pedirlo seria pedir algo
    que la API no deja cambiar.
    """
    return {
        "model": model or config.model_id(),
        "max_tokens": config.max_tokens(),
        "system": EXTRACTION_SYSTEM_PROMPT,
        "messages": _mensajes(doc),
        "output_format": InvoiceExtraction,
        "output_config": {"effort": config.effort()},
    }


def construir_peticion_lote(doc: SourceDocument, model: str | None = None) -> dict[str, Any]:
    """La misma peticion, como entrada de un lote de la API de Batches.

    Un lote no pasa por messages.parse, asi que el esquema va escrito en
    output_config.format (el mismo que deriva el SDK para la via sincrona;
    un test lo compara). custom_id es el sha256 del documento: los
    resultados de un lote llegan en cualquier orden, y es lo que los ata a
    su documento sin depender de la posicion. Ninguna herramienta, como en
    build_request.
    """
    return {
        "custom_id": doc.sha256,
        "params": {
            "model": model or config.model_id(),
            "max_tokens": config.max_tokens(),
            "system": EXTRACTION_SYSTEM_PROMPT,
            "messages": _mensajes(doc),
            "output_config": {
                "effort": config.effort(),
                "format": {"type": "json_schema", "schema": esquema_json()},
            },
        },
    }


class Rechazado(RuntimeError):
    """El modelo se nego a leer el documento (stop_reason refusal)."""


def extract_invoice(
    client: Any, doc: SourceDocument, model: str | None = None
) -> ExtractionRecord:
    """Extrae una factura. El cliente se inyecta para poder sustituirlo en tests."""
    request = build_request(doc, model=model)
    response = client.messages.parse(**request)

    if getattr(response, "stop_reason", None) == "refusal":
        details = getattr(response, "stop_details", None)
        raise Rechazado(
            f"El modelo rechazo el documento {doc.path.name}: "
            f"{getattr(details, 'category', 'sin categoria')}"
        )

    return ExtractionRecord(
        source_sha256=doc.sha256,
        source_name=doc.path.name,
        model=request["model"],
        prompt_version=config.PROMPT_VERSION,
        schema_version=config.SCHEMA_VERSION,
        extracted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        extraction=response.parsed_output,
        usage=_uso(getattr(response, "usage", None)),
        request_id=getattr(response, "_request_id", None),
    )


def _uso(usage: Any, *, lote: bool = False) -> dict[str, Any]:
    """Los tokens que se pagan, y si se pagaron al precio de lote.

    service_tier "batch" es lo que hace que coste.py cobre la mitad: sin
    apuntarlo, una pasada por lotes se contaria al doble de lo que costo.
    """
    if not usage:
        return {}
    uso: dict[str, Any] = {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
    }
    tier = "batch" if lote else getattr(usage, "service_tier", None)
    if isinstance(tier, str) and tier:
        uso["service_tier"] = tier
    return uso


# Por que un resultado de lote va a la lista de reintentos.
REINTENTO_RECHAZO = "rechazo"
REINTENTO_ERROR = "error"
REINTENTO_CADUCADO = "caducado"
REINTENTO_CANCELADO = "cancelado"
REINTENTO_INVALIDO = "invalido"


@dataclass(frozen=True)
class Reintento:
    """Un documento cuyo resultado no sirve: se vuelve a pedir, no se adivina."""

    sha256: str
    motivo: str
    detalle: str = ""


def leer_resultado_lote(
    resultado: Any, doc: SourceDocument, *, model: str, prompt_version: str | None = None,
    schema_version: str | None = None,
) -> ExtractionRecord | Reintento:
    """Un resultado de un lote como registro de extraccion, o como reintento.

    Lo que llega se valida contra el esquema con model_validate_json: un
    lote no pasa por messages.parse, y un JSON cortado (max_tokens) o que no
    es el esquema no se guarda como si fuera una lectura. Un rechazo, un
    error, un caducado o un cancelado van a la lista de reintentos: los lotes
    no admiten el respaldo de modelo del servidor, asi que nadie lo reintenta
    por nosotros.
    """
    from pydantic import ValidationError

    sha = getattr(resultado, "custom_id", None) or doc.sha256
    cuerpo = getattr(resultado, "result", None)
    tipo = getattr(cuerpo, "type", None)
    if tipo == "errored":
        error = getattr(getattr(cuerpo, "error", None), "error", None) or getattr(
            cuerpo, "error", None)
        clase = getattr(error, "type", None) or "error"
        return Reintento(sha, REINTENTO_ERROR, f"{clase}: {getattr(error, 'message', '')}".strip())
    if tipo == "expired":
        return Reintento(sha, REINTENTO_CADUCADO, "el lote caduco antes de leerlo")
    if tipo == "canceled":
        return Reintento(sha, REINTENTO_CANCELADO, "el lote se cancelo")
    if tipo != "succeeded":
        return Reintento(sha, REINTENTO_ERROR, f"resultado desconocido: {tipo!r}")

    mensaje = getattr(cuerpo, "message", None)
    if getattr(mensaje, "stop_reason", None) == "refusal":
        detalles = getattr(mensaje, "stop_details", None)
        return Reintento(sha, REINTENTO_RECHAZO,
                         f"rechazado: {getattr(detalles, 'category', 'sin categoria')}")
    texto = next((getattr(b, "text", "") for b in getattr(mensaje, "content", None) or []
                  if getattr(b, "type", None) == "text"), None)
    if texto is None:
        return Reintento(sha, REINTENTO_INVALIDO, "sin bloque de texto")
    try:
        extraccion = InvoiceExtraction.model_validate_json(texto)
    except ValidationError as exc:
        motivo = getattr(mensaje, "stop_reason", None)
        detalle = "cortado por max_tokens" if motivo == "max_tokens" else (
            f"no es el esquema: {exc.error_count()} errores")
        return Reintento(sha, REINTENTO_INVALIDO, detalle)
    # Las versiones son las de la peticion que se mando, que pudo ser horas
    # antes: quien recoge el lote las pasa.
    return ExtractionRecord(
        source_sha256=doc.sha256,
        source_name=doc.path.name,
        model=model,
        prompt_version=prompt_version or config.PROMPT_VERSION,
        schema_version=schema_version or config.SCHEMA_VERSION,
        extracted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        extraction=extraccion,
        usage=_uso(getattr(mensaje, "usage", None), lote=True),
        request_id=None,
    )


@dataclass
class ResultadoPasada:
    """Lo que hizo una pasada sobre una carpeta. Lo leen la CLI y el servidor."""

    total: int = 0
    extraidas: int = 0
    reutilizadas: int = 0
    fallidas: int = 0
    tokens_entrada: int = 0
    tokens_salida: int = 0
    errores: list[str] = field(default_factory=list)
    # Con almacen: documentos guardados alli, y los que no se pudo (estan en out/).
    almacenadas: int = 0
    sin_almacen: int = 0


# Avisos de progreso: (tipo, nombre del PDF, detalle). tipo es "omitido",
# "cache", "error" u "ok".
Informar = Callable[[str, str, str], None]


def extraer_pasada(
    client: Any,
    rutas: Iterable[str | Path],
    out_dir: str | Path,
    *,
    model: str | None = None,
    politica: str = CONSERVAR,
    forzar: bool = False,
    informar: Informar | None = None,
    resultado: ResultadoPasada | None = None,
    almacen: Almacen | None = None,
    ruta: str = "entrante",
) -> ResultadoPasada:
    """Extrae los PDF que no tengan ya una extraccion reutilizable.

    Es el unico bucle de extraccion: lo usan `extract` y el servidor local,
    para que los dos apliquen la misma politica de cache. Con CONSERVAR, un
    documento ya leido con cualquier version no vuelve a la API; con
    ESTRICTA, solo si coincide todo; con forzar, se vuelve a leer lo que ya
    estaba en out_dir, pero un PDF que se repite dentro de la misma pasada se
    paga una vez tambien con forzar: el indice empieza vacio y solo guarda lo
    que esta pasada acaba de escribir. Ninguna de las tres sobrescribe nada.

    Si se pasa `resultado`, se rellena sobre la marcha: el servidor lo lee
    desde otro hilo para ensenar el progreso y el coste mientras corre.

    Con `almacen`, cada documento leido o reutilizado entra tambien en el
    almacen (ver _al_almacen). Si eso falla, la pasada sigue: la extraccion
    ya esta en out/ y `importar-out` la recupera; no se vuelve a pagar.
    `ruta` es la via de entrada (entrante o saliente): la pone quien llama,
    nunca el modelo, y decide la direccion de la factura (ingesta.py).
    """
    model = model or config.model_id()
    avisar = informar or (lambda _tipo, _nombre, _detalle: None)
    indice = {} if forzar else indexar(out_dir)
    resultado = resultado if resultado is not None else ResultadoPasada()

    for ruta_pdf in rutas:
        ruta_pdf = Path(ruta_pdf)
        resultado.total += 1
        try:
            doc = load_pdf(ruta_pdf)
        except UnsupportedDocument as exc:
            resultado.fallidas += 1
            resultado.errores.append(f"{ruta_pdf.name}: {exc}")
            avisar("omitido", ruta_pdf.name, str(exc))
            continue

        guardada = reutilizable(
            indice.get(doc.sha256), politica=politica, model=model,
            prompt_version=config.PROMPT_VERSION, schema_version=config.SCHEMA_VERSION,
        )
        if guardada is not None:
            resultado.reutilizadas += 1
            avisar("cache", ruta_pdf.name, _detalle_cache(guardada, model))
            if almacen is not None:
                _al_almacen(almacen, doc, ruta_pdf, Path(guardada.path), "out_v1", resultado,
                            avisar, via_entrada=ruta)
            continue

        try:
            record = extract_invoice(client, doc, model=model)
        except Exception as exc:  # una pasada no se detiene por un documento
            resultado.fallidas += 1
            resultado.errores.append(f"{ruta_pdf.name}: {type(exc).__name__}: {exc}")
            avisar("error", ruta_pdf.name, f"{type(exc).__name__}: {exc}")
            continue

        target = record.write_json(out_dir)
        if almacen is not None:
            _al_almacen(almacen, doc, ruta_pdf, target, "api", resultado, avisar,
                        via_entrada=ruta)
        # Si el mismo PDF viene dos veces en la carpeta, la segunda ya no paga.
        indice.setdefault(doc.sha256, []).insert(0, CachedExtraction(
            path=target, sha256=doc.sha256, model=record.model,
            prompt_version=record.prompt_version, schema_version=record.schema_version,
            extracted_at=record.extracted_at,
        ))
        resultado.extraidas += 1
        resultado.tokens_entrada += record.usage.get("input_tokens") or 0
        resultado.tokens_salida += record.usage.get("output_tokens") or 0
        dudosos = record.extraction.low_confidence_fields
        sufijo = f"  (dudoso: {', '.join(dudosos)})" if dudosos else ""
        avisar("ok", ruta_pdf.name, f"{target.name}{sufijo}")

    return resultado


def _al_almacen(
    almacen: Almacen,
    doc: SourceDocument,
    ruta: Path,
    fichero_out: Path,
    via: str,
    resultado: ResultadoPasada,
    avisar: Informar,
    *,
    via_entrada: str = "entrante",
) -> None:
    """Guarda el PDF y su extraccion en el almacen, en una transaccion por documento.

    Una por documento y no una por pasada: cada documento es una llamada
    pagada, y un fallo en el documento 40 no tiene que deshacer los 39
    anteriores. `fichero_out` es el fichero de out/ con la extraccion, recien
    escrita o reutilizada: entran sus bytes tal cual, como en importar-out,
    para que las dos vias den el mismo hash y no se guarde dos veces.
    """
    from .almacen import transaccion, usuario_sistema
    from .almacen.documentos import instante_de_fichero, registrar_documento
    from .almacen.extracciones import RegistroInvalido, leer_registro, registrar_extraccion

    try:
        texto = fichero_out.read_bytes().decode("utf-8")
        with transaccion(almacen.conn):
            actor = usuario_sistema(almacen.conn, "extractor")
            documento = registrar_documento(
                almacen, sha256=doc.sha256, contenido=base64.b64decode(doc.data_b64),
                nombre_original=ruta.name, tipo_mime=doc.media_type, origen="carpeta",
                ruta_declarada=via_entrada, recibido_en=instante_de_fichero(ruta),
                recibido_fuente="mtime", actor=actor,
            )
            registrar_extraccion(
                almacen.conn, leer_registro(texto), documento_id=documento.id,
                via=via, actor=actor, fichero=fichero_out.name,
            )
        resultado.almacenadas += 1
    except Exception as exc:  # la extraccion ya esta en out/: no se pierde nada pagado
        resultado.sin_almacen += 1
        detalle = f"almacen: {type(exc).__name__}: {exc}"
        resultado.errores.append(f"{ruta.name}: {detalle}")
        if isinstance(exc, (RegistroInvalido, UnicodeDecodeError)):
            # importar-out lo rechazaria igual: no se promete lo que no hara.
            avisar("error", ruta.name, f"{detalle} (esta en {fichero_out.name}, sin poder guardarse)")
        else:
            avisar("error", ruta.name,
                   f"{detalle} (esta en out/; `bms-agent importar-out` la recupera)")


def _detalle_cache(guardada: CachedExtraction, model: str) -> str:
    """Que extraccion se reutiliza, y si se hizo con otras versiones."""
    if guardada.matches(model, config.PROMPT_VERSION, config.SCHEMA_VERSION):
        return f"{guardada.path.name}  (sin coste)"
    return (
        f"{guardada.path.name}  (sin coste; leida con {guardada.model}, "
        f"prompt {guardada.prompt_version}, esquema {guardada.schema_version})"
    )
