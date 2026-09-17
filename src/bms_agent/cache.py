"""Reutilizacion de extracciones ya hechas.

Un proveedor reenvia la misma factura, el mismo correo llega dos veces, o se
vuelve a lanzar la carpeta entera despues de anadir tres PDF. En los tres
casos, volver a llamar a la API por un documento cuyos bytes ya se han leido
es gasto tirado.

Un documento se identifica por el hash de sus bytes. Si ya existe una
extraccion de ese hash, hecha con el mismo modelo y las mismas versiones de
prompt y de esquema, se reutiliza sin llamar a la API.

Lo que esto NO resuelve, y no puede: el mismo numero de factura llegando en
un PDF distinto (regenerado, reescaneado o corregido). Bytes distintos son
un documento distinto, y hay que leerlo para saber que dice. Esa duplicidad
la detectan las reglas B2, B3 y B4 del catalogo de validacion, despues de la
extraccion y sobre los datos ya estructurados.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CachedExtraction:
    path: Path
    sha256: str
    model: str
    prompt_version: str
    schema_version: str

    def matches(self, model: str, prompt_version: str, schema_version: str) -> bool:
        """Sirve solo si se genero en las mismas condiciones.

        Cambiar de modelo o tocar el prompt invalida lo guardado: el
        resultado podria ser otro, y reutilizarlo escondria la diferencia
        justo cuando se esta midiendo si mejora.
        """
        return (
            self.model == model
            and self.prompt_version == prompt_version
            and self.schema_version == schema_version
        )


def build_index(out_dir: str | Path) -> dict[str, CachedExtraction]:
    """Indexa por hash las extracciones ya guardadas.

    Se lee una vez por ejecucion, no una vez por documento. Un fichero
    ilegible o incompleto se ignora en lugar de romper la ejecucion: como
    mucho se vuelve a extraer ese documento.
    """
    out_dir = Path(out_dir)
    if not out_dir.is_dir():
        return {}

    index: dict[str, CachedExtraction] = {}
    for path in sorted(out_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            sha256 = payload["source_sha256"]
            entry = CachedExtraction(
                path=path,
                sha256=sha256,
                model=payload["model"],
                prompt_version=payload["prompt_version"],
                schema_version=payload["schema_version"],
            )
        except (json.JSONDecodeError, KeyError, OSError, TypeError):
            continue
        index[sha256] = entry

    return index
