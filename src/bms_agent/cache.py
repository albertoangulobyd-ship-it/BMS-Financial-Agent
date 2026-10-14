"""Reutilizacion de extracciones ya hechas.

Un proveedor reenvia la misma factura, el mismo correo llega dos veces, o se
vuelve a lanzar la carpeta entera despues de anadir tres PDF. En los tres
casos, volver a llamar a la API por un documento cuyos bytes ya se han leido
es gasto tirado.

Un documento se identifica por el hash de sus bytes. Que extraccion guardada
sirve para ese hash lo decide la politica:

- CONSERVAR (por defecto): sirve cualquier extraccion de esos mismos bytes,
  la hiciera el modelo y la version de prompt y de esquema que la hiciera.
  Cambiar de modelo o subir una version no vuelve a pagar la carpeta entera:
  lo ya leido se conserva, y volver a leerlo es una decision aparte.
- ESTRICTA (`extract --estricta`): solo sirve una extraccion hecha con el
  mismo modelo y las mismas versiones. Es la de medir: si se compara un
  modelo con otro, reutilizar lo viejo esconderia la diferencia.

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

CONSERVAR = "conservar"
ESTRICTA = "estricta"
POLITICAS = (CONSERVAR, ESTRICTA)


@dataclass(frozen=True)
class CachedExtraction:
    path: Path
    sha256: str
    model: str
    prompt_version: str
    schema_version: str
    extracted_at: str = ""

    def matches(self, model: str, prompt_version: str, schema_version: str) -> bool:
        """Se genero en las mismas condiciones. Es la prueba de la politica ESTRICTA.

        Cambiar de modelo o tocar el prompt da otra extraccion posible: para
        medir si mejora, la guardada no sirve. Para trabajar, si (CONSERVAR).
        """
        return (
            self.model == model
            and self.prompt_version == prompt_version
            and self.schema_version == schema_version
        )


def indexar(out_dir: str | Path) -> dict[str, list[CachedExtraction]]:
    """Todas las extracciones guardadas, por hash, la mas reciente primero.

    Un mismo documento puede tener varias: nada se sobrescribe, asi que una
    pasada con otro modelo o un --force anaden una al lado de las anteriores.
    Se lee una vez por ejecucion, no una vez por documento. Un fichero
    ilegible o incompleto se ignora en lugar de romper la ejecucion: como
    mucho se vuelve a extraer ese documento.
    """
    out_dir = Path(out_dir)
    if not out_dir.is_dir():
        return {}

    index: dict[str, list[CachedExtraction]] = {}
    for path in sorted(out_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            entry = CachedExtraction(
                path=path,
                sha256=payload["source_sha256"],
                model=payload["model"],
                prompt_version=payload["prompt_version"],
                schema_version=payload["schema_version"],
                extracted_at=str(payload.get("extracted_at") or ""),
            )
        except (json.JSONDecodeError, KeyError, OSError, TypeError):
            continue
        index.setdefault(entry.sha256, []).append(entry)

    for entries in index.values():
        entries.sort(key=lambda e: (e.extracted_at, e.path.name), reverse=True)
    return index


def build_index(out_dir: str | Path) -> dict[str, CachedExtraction]:
    """La extraccion mas reciente de cada documento guardado."""
    return {sha256: entries[0] for sha256, entries in indexar(out_dir).items()}


def reutilizable(
    candidatas: list[CachedExtraction] | None,
    *,
    politica: str,
    model: str,
    prompt_version: str,
    schema_version: str,
) -> CachedExtraction | None:
    """La extraccion guardada que se reutiliza, o None si hay que pagar.

    Con las dos politicas se prefiere la que coincide en todo. Con CONSERVAR,
    si ninguna coincide, vale la mas reciente de las que haya.
    """
    if politica not in POLITICAS:
        raise ValueError(f"politica de cache desconocida: {politica!r}")
    candidatas = candidatas or []
    for entry in candidatas:
        if entry.matches(model, prompt_version, schema_version):
            return entry
    if politica == CONSERVAR and candidatas:
        return candidatas[0]
    return None
