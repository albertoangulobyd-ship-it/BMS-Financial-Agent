#!/usr/bin/env python3
"""Escribe en docs/validacion-facturas.md la tabla de las reglas que evalua el motor.

    python scripts/generar_catalogo_doc.py            # reescribe la tabla
    python scripts/generar_catalogo_doc.py --comprobar  # sale con 1 si no coincide

La tabla va entre las marcas `<!-- catalogo:inicio -->` y `<!-- catalogo:fin -->`
del apartado 6 y sale entera de src/bms_agent/reglas/catalogo.py: el
identificador, el titulo, lo que mira (la descripcion de la regla), que hace
un fallo en una compra y en una venta, si se puede anular (con la lista dura
de la decision 12), si es pegajosa, si anularla pide segunda firma, si un
aviso abre excepcion, que aporta a la prioridad y de que es. Lo demas del
documento lo escribe una persona; esta tabla no, para que no se aparte del
codigo (tests/test_panel_busqueda.py lo comprueba).
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from bms_agent.reglas import catalogo  # noqa: E402

DOCUMENTO = RAIZ / "docs" / "validacion-facturas.md"
INICIO, FIN = "<!-- catalogo:inicio -->", "<!-- catalogo:fin -->"

_SEVERIDAD = {"bloqueo": "Bloqueo", "retencion": "Retención", "aviso": "Aviso"}
_PRIORIDAD = {"otra": "otra", "duplicado_exacto": "duplicado exacto",
              "duplicado": "duplicado", "iban": "IBAN", "iva_dura": "IVA duro",
              "iva_blanda": "IVA blando", "planning": "planning",
              "facturacion_ausente": "facturación ausente",
              "trabajo_sin_facturar": "trabajo sin facturar", "limite_po": "límite de PO",
              "limite_po_duro": "límite de PO duro", "caducidad_po": "caducidad de PO",
              "dias_vencida": "días vencida"}


def _celda(texto: str) -> str:
    return texto.replace("|", "\\|").replace("\n", " ")


def _anulable(regla: catalogo.Regla, sentido: str) -> bool:
    return regla.anulable_para(sentido) and not catalogo.nunca_anulable(regla.id, sentido)


def _si(valor: bool) -> str:
    return "sí" if valor else "no"


def tabla() -> str:
    """La tabla en Markdown, una fila por regla del catalogo, en su orden."""
    filas = ["| Regla | Qué mira | Compra | Venta | Anulable (compra / venta) | Pegajosa | "
             "Segunda firma | Abre excepción | Prioridad | De qué |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for regla in catalogo.CATALOGO:
        filas.append(
            f"| {regla.id} | **{_celda(regla.titulo)}**. {_celda(regla.descripcion)} | "
            f"{_SEVERIDAD[regla.severidad_para('entrante')]} | "
            f"{_SEVERIDAD[regla.severidad_para('saliente')]} | "
            f"{_si(_anulable(regla, 'entrante'))} / {_si(_anulable(regla, 'saliente'))} | "
            f"{_si(regla.pegajosa)} | {_si(regla.segunda_firma)} | "
            f"{_si(regla.crea_excepcion or regla.severidad != 'aviso')} | "
            f"{_PRIORIDAD.get(regla.entrada_prioridad, regla.entrada_prioridad)} | "
            f"{regla.ambito} |")
    return "\n".join(filas)


def bloque() -> str:
    return (f"{INICIO}\n\n_Generado de `src/bms_agent/reglas/catalogo.py` con "
            f"`python scripts/generar_catalogo_doc.py`: no se edita a mano. "
            f"{len(catalogo.CATALOGO)} reglas._\n\n{tabla()}\n\n{FIN}")


def documento_con_tabla(texto: str) -> str:
    """El documento con la tabla de ahora entre sus marcas."""
    cabeza, marca, resto = texto.partition(INICIO)
    if not marca or FIN not in resto:
        raise SystemExit(f"{DOCUMENTO} no tiene las marcas {INICIO} y {FIN}")
    return cabeza + bloque() + resto.split(FIN, 1)[1]


def main(argumentos: list[str]) -> int:
    texto = DOCUMENTO.read_text(encoding="utf-8")
    nuevo = documento_con_tabla(texto)
    if "--comprobar" in argumentos:
        if nuevo != texto:
            print("La tabla del catalogo no es la del codigo: python "
                  "scripts/generar_catalogo_doc.py", file=sys.stderr)
            return 1
        return 0
    DOCUMENTO.write_text(nuevo, encoding="utf-8")
    print(f"{len(catalogo.CATALOGO)} reglas escritas en {DOCUMENTO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
