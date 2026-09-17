"""Carga de documentos de la zona no confiable.

Un documento se identifica por el hash de sus bytes, no por su nombre. Dos
correos pueden traer el mismo PDF con nombres distintos, y el mismo nombre
puede traer PDFs distintos.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

PDF_MAGIC = b"%PDF-"


class UnsupportedDocument(ValueError):
    """El fichero no es un PDF."""


@dataclass(frozen=True)
class SourceDocument:
    path: Path
    sha256: str
    byte_size: int
    data_b64: str
    media_type: str = "application/pdf"

    @property
    def short_hash(self) -> str:
        return self.sha256[:12]


def load_pdf(path: str | Path) -> SourceDocument:
    """Lee un PDF del disco y lo prepara para el extractor."""
    path = Path(path)
    data = path.read_bytes()

    if not data.startswith(PDF_MAGIC):
        raise UnsupportedDocument(
            f"{path.name} no empieza por %PDF-; no se trata como factura"
        )

    return SourceDocument(
        path=path,
        sha256=hashlib.sha256(data).hexdigest(),
        byte_size=len(data),
        # Sin saltos de linea: la API los rechaza en base64.
        data_b64=base64.standard_b64encode(data).decode("ascii"),
    )


def iter_pdfs(directory: str | Path) -> Iterator[Path]:
    """Recorre los PDF de una carpeta, en orden estable."""
    yield from sorted(Path(directory).glob("*.pdf"))
