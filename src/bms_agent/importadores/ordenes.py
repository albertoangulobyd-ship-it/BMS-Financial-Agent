"""La hoja de ordenes de compra en YAML, el otro formato de po_csv (spec §9; paso 9).

Una persona que no tiene la hoja de calculo a mano puede teclear las PO en un
YAML con dos listas, `ordenes` y `modificaciones`; cada entrada lleva los
campos del registro canonico con su nombre (OrdenCompraCanonica y
ModificacionPOCanonica):

    ordenes:
      - numero: PO-4500123
        lado: cliente
        parte_ref: "10001"
        objetos_ref: [Rijnhaven, Waalhaven]
        fecha_inicio: 2026-09-01
        fecha_fin: 2026-12-31
        valor: "10000.00"
    modificaciones:
      - numero: PO-4500123
        lado: cliente
        parte_ref: "10001"
        fecha: 2026-10-01
        valor_nuevo: "12500.00"
        motivo: Ampliacion de Waalhaven

Da los mismos registros que el CSV y entra por el mismo registrar_lote, con
las mismas reglas. Los numeros se leen como texto, nunca como numeros de YAML:
YAML 1.1 lee 1250.50 como float (pierde centimos), 012500 como octal (5440) y
12:30 como sexagesimal (750), sin que nadie lo vea. Leidos como texto, el
importe es lo que la persona tecleo, y el crudo tambien; un importe que no es
una cifra con, si acaso, decimales tras un punto ("12:30", "1_000") se
rechaza. Leer es puro, como todo lector.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import yaml
from pydantic import ValidationError

from ..almacen.unidades import sha256_bytes
from .base import LoteLeido, Rechazo
from .canonico import MODELOS

FUENTE = "po_csv"
FORMATO = "yaml:po-v1"
SECCIONES = {"ordenes_compra": "ordenes", "modificaciones_po": "modificaciones"}


# Un importe tecleado: cifras y, si acaso, sus decimales tras un punto.
_IMPORTE = re.compile(r"\d+(\.\d+)?")


class YamlNoValido(ValueError):
    """Un fichero que no es un YAML de PO (no es un mapa con ordenes o modificaciones)."""


class _Cargador(yaml.SafeLoader):
    """SafeLoader sin enteros ni floats implicitos: un numero sin comillas queda como texto.

    Las fechas, los si/no y los nulos se siguen resolviendo como siempre.
    """


_Cargador.yaml_implicit_resolvers = {
    inicial: [(etiqueta, regexp) for etiqueta, regexp in resolvers
              if etiqueta not in ("tag:yaml.org,2002:int", "tag:yaml.org,2002:float")]
    for inicial, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()}


def _cargar(contenido: bytes) -> dict[str, Any]:
    try:
        datos = yaml.load(contenido.decode("utf-8-sig"), Loader=_Cargador)  # noqa: S506
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise YamlNoValido(f"no es un YAML legible: {exc}") from None
    if not isinstance(datos, dict) or not set(datos) & set(SECCIONES.values()):
        raise YamlNoValido("un YAML de PO es un mapa con la lista ordenes, modificaciones o "
                           "las dos")
    sobran = set(datos) - set(SECCIONES.values())
    if sobran:
        raise YamlNoValido(f"no se entiende {', '.join(sorted(map(str, sobran)))}: solo ordenes "
                           "y modificaciones")
    return datos


def reconoce(contenido: bytes) -> bool:
    try:
        _cargar(contenido)
    except YamlNoValido:
        return False
    return True


def _crudo(entrada: dict[str, Any]) -> dict[str, str]:
    return {str(k): "" if v is None else (", ".join(map(str, v)) if isinstance(v, list)
                                          else str(v))
            for k, v in entrada.items()}


def _importes_no_validos(entrada: dict[str, Any]) -> list[str]:
    """Los importes que no son una cifra tecleada (un si/no, una fecha, "12:30", "1_000")."""
    return sorted(clave for clave in ("valor", "valor_nuevo")
                  if entrada.get(clave) is not None
                  and not (isinstance(entrada[clave], str)
                           and _IMPORTE.fullmatch(entrada[clave].strip())))


def leer(contenido: bytes, tipo: str, *, exportado_en: datetime | None = None) -> LoteLeido:
    """El lote de un tipo (ordenes_compra o modificaciones_po) de un YAML de PO."""
    if tipo not in SECCIONES:
        raise ValueError(f"un YAML de PO da ordenes_compra o modificaciones_po, no {tipo}")
    datos = _cargar(contenido)
    entradas = datos.get(SECCIONES[tipo]) or []
    if not isinstance(entradas, list):
        raise YamlNoValido(f"{SECCIONES[tipo]} es una lista")
    modelo = MODELOS[tipo]
    registros, rechazos = [], []
    for fila, entrada in enumerate(entradas, start=1):
        if not isinstance(entrada, dict):
            rechazos.append(Rechazo(fila, "cada entrada es un mapa de campos",
                                    {"entrada": str(entrada)}))
            continue
        crudo = _crudo(entrada)
        malos = _importes_no_validos(entrada)
        if malos:
            rechazos.append(Rechazo(fila, f"{', '.join(malos)}: un importe es una cifra con, si "
                                          "acaso, sus decimales tras un punto (\"1250.50\")",
                                    crudo))
            continue
        if "fila" in entrada or "crudo" in entrada:
            rechazos.append(Rechazo(fila, "fila y crudo no son campos de la hoja", crudo))
            continue
        valores = dict(entrada)
        for clave in ("valor", "valor_nuevo"):
            if isinstance(valores.get(clave), str):
                valores.setdefault(f"{clave}_crudo", valores[clave])
        try:
            registros.append(modelo.model_validate({**valores, "fila": fila, "crudo": crudo}))
        except ValidationError as exc:
            motivo = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                               for e in exc.errors(include_url=False))
            rechazos.append(Rechazo(fila, motivo, crudo))
    return LoteLeido(
        fuente=FUENTE, tipo=tipo, formato=FORMATO, fichero_sha256=sha256_bytes(contenido),
        mapeo_id=None, mapeo_sha256=None, exportado_en=exportado_en, cubre_desde=None,
        cubre_hasta=None, completo=False, registros=tuple(registros), rechazos=tuple(rechazos))


def lotes(contenido: bytes, tipo: str, *,
          exportado_en: datetime | None = None) -> list[LoteLeido]:
    """Los lotes de una importacion: con ordenes_compra, las PO y despues sus modificaciones
    (las de una PO nueva necesitan la PO); con modificaciones_po, solo las modificaciones."""
    tipos = (["ordenes_compra", "modificaciones_po"] if tipo == "ordenes_compra"
             else [tipo])
    datos = _cargar(contenido)
    return [leer(contenido, t, exportado_en=exportado_en) for t in tipos
            if t == tipo or datos.get(SECCIONES[t])]


def contrato(contenido: bytes) -> dict[str, Any]:
    """Lo que da leer un YAML de PO, en JSON: lo que fija su test de contrato."""
    return {"formato": FORMATO, "fuente": FUENTE, "lotes": [
        {"tipo": lote.tipo, "registros": [r.model_dump(mode="json") for r in lote.registros],
         "rechazos": [r.a_dict() for r in lote.rechazos]}
        for lote in (leer(contenido, t) for t in SECCIONES)]}
