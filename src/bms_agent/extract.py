"""Llamada de extraccion.

Propiedad de seguridad de este modulo: la peticion NO lleva herramientas.
El proceso que lee contenido de terceros no tiene con que actuar. Su unica
salida posible es un objeto validado contra el esquema.

build_request es una funcion pura precisamente para poder comprobar esa
propiedad en un test, sin llamar a la API.

Lo que se extrae no se sobrescribe nunca. Cada extraccion va a su propio
fichero, nombrado por el hash del documento y por las versiones que la
produjeron, y si ese nombre ya existe se anade otro al lado. Es la evidencia
de lo que se leyo: una pasada nueva no puede borrar la anterior.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from .cache import CONSERVAR, CachedExtraction, indexar, reutilizable
from .documents import SourceDocument, UnsupportedDocument, load_pdf
from .prompts import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_TEXT
from .schema import InvoiceExtraction


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

    def write_json(self, out_dir: str | Path) -> Path:
        """Guarda la extraccion sin pisar ninguna otra.

        El nombre lleva el hash y las versiones, asi que una extraccion de
        otro modelo, prompt o esquema nunca cae en el mismo fichero. Si el
        nombre ya existe (un --force con las mismas versiones), se anade un
        sufijo en vez de sobrescribir. El fichero se crea en modo exclusivo:
        ni dos procesos a la vez pueden pisarse.
        """
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        contenido = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        base = nombre_fichero(
            self.source_sha256, self.model, self.prompt_version, self.schema_version
        )
        numero = 1
        while True:
            target = out_dir / (base if numero == 1 else f"{base[:-5]}__{numero}.json")
            try:
                with target.open("x", encoding="utf-8") as fichero:
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
    try:
        return ruta.read_text(encoding="utf-8") == contenido
    except OSError:
        return False


def build_request(doc: SourceDocument, model: str | None = None) -> dict[str, Any]:
    """Construye los argumentos de la llamada. Sin herramientas, a proposito."""
    return {
        "model": model or config.model_id(),
        "max_tokens": config.max_tokens(),
        "system": EXTRACTION_SYSTEM_PROMPT,
        "messages": [
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
        ],
        "output_format": InvoiceExtraction,
    }


def extract_invoice(
    client: Any, doc: SourceDocument, model: str | None = None
) -> ExtractionRecord:
    """Extrae una factura. El cliente se inyecta para poder sustituirlo en tests."""
    request = build_request(doc, model=model)
    response = client.messages.parse(**request)

    if getattr(response, "stop_reason", None) == "refusal":
        details = getattr(response, "stop_details", None)
        raise RuntimeError(
            f"El modelo rechazo el documento {doc.path.name}: "
            f"{getattr(details, 'category', 'sin categoria')}"
        )

    usage = getattr(response, "usage", None)

    return ExtractionRecord(
        source_sha256=doc.sha256,
        source_name=doc.path.name,
        model=request["model"],
        prompt_version=config.PROMPT_VERSION,
        schema_version=config.SCHEMA_VERSION,
        extracted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        extraction=response.parsed_output,
        usage={
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
        }
        if usage
        else {},
        request_id=getattr(response, "_request_id", None),
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
    """
    model = model or config.model_id()
    avisar = informar or (lambda _tipo, _nombre, _detalle: None)
    indice = {} if forzar else indexar(out_dir)
    resultado = resultado if resultado is not None else ResultadoPasada()

    for ruta in rutas:
        ruta = Path(ruta)
        resultado.total += 1
        try:
            doc = load_pdf(ruta)
        except UnsupportedDocument as exc:
            resultado.fallidas += 1
            resultado.errores.append(f"{ruta.name}: {exc}")
            avisar("omitido", ruta.name, str(exc))
            continue

        guardada = reutilizable(
            indice.get(doc.sha256), politica=politica, model=model,
            prompt_version=config.PROMPT_VERSION, schema_version=config.SCHEMA_VERSION,
        )
        if guardada is not None:
            resultado.reutilizadas += 1
            avisar("cache", ruta.name, _detalle_cache(guardada, model))
            continue

        try:
            record = extract_invoice(client, doc, model=model)
        except Exception as exc:  # una pasada no se detiene por un documento
            resultado.fallidas += 1
            resultado.errores.append(f"{ruta.name}: {type(exc).__name__}: {exc}")
            avisar("error", ruta.name, f"{type(exc).__name__}: {exc}")
            continue

        target = record.write_json(out_dir)
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
        avisar("ok", ruta.name, f"{target.name}{sufijo}")

    return resultado


def _detalle_cache(guardada: CachedExtraction, model: str) -> str:
    """Que extraccion se reutiliza, y si se hizo con otras versiones."""
    if guardada.matches(model, config.PROMPT_VERSION, config.SCHEMA_VERSION):
        return f"{guardada.path.name}  (sin coste)"
    return (
        f"{guardada.path.name}  (sin coste; leida con {guardada.model}, "
        f"prompt {guardada.prompt_version}, esquema {guardada.schema_version})"
    )
