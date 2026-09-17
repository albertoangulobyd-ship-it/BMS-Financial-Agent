"""Llamada de extraccion.

Propiedad de seguridad de este modulo: la peticion NO lleva herramientas.
El proceso que lee contenido de terceros no tiene con que actuar. Su unica
salida posible es un objeto validado contra el esquema.

build_request es una funcion pura precisamente para poder comprobar esa
propiedad en un test, sin llamar a la API.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from .documents import SourceDocument
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
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{self.source_sha256[:12]}.json"
        target.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return target


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
