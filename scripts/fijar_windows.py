"""Fija los sha256 de la instalacion nativa de Windows (paso 14). Para quien mantiene el programa.

El instalador (windows/instalar.ps1) no baja nada cuyo sha256 no este fijado en
windows/fijado.json (el Python embebible) y windows/requirements-windows.txt (cada rueda).
Este script rellena lo que falte, con internet, y deja los dos ficheros para revisarlos y
subirlos a git:

    python scripts/fijar_windows.py              rellena lo PENDIENTE
    python scripts/fijar_windows.py --comprobar  solo dice que falta (sale con 1 si falta algo)

- Las ruedas: el sha256 que publica PyPI (https://pypi.org/pypi/NOMBRE/VERSION/json) de la
  rueda que vale para Windows x64 y CPython 3.11 (cp311-win_amd64, abi3 o py3-none-any).
  Ninguna se elige por su nombre si hay dos que valen: se dice y se para.
- El Python embebible: se baja de python.org y se calcula su sha256. Eso solo dice que es lo
  que python.org sirve hoy; antes de subirlo, comprueba la firma de Sigstore del fichero
  (python.org publica un .sigstore al lado) como dice docs/instalacion-nativa.md.

No toca src/ ni nada de lo que corre: es una herramienta de quien prepara la version.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REQUISITOS = RAIZ / "windows" / "requirements-windows.txt"
FIJADO = RAIZ / "windows" / "fijado.json"
PYPI = "https://pypi.org/pypi"
PENDIENTE = "# PENDIENTE"

_REQUISITO = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9_.+!-]+)")
_HASH = re.compile(r"--hash=sha256:([0-9a-f]{64})")


@dataclass
class Requisito:
    nombre: str
    version: str
    hashes: list[str] = field(default_factory=list)


def leer_requisitos(texto: str) -> list[Requisito]:
    """requirements-windows.txt como lo lee instalar.ps1 (Leer-Requisitos): nombre==version y
    sus --hash=sha256, sin los comentarios."""
    requisitos: list[Requisito] = []
    for linea in texto.splitlines():
        limpio = re.sub(r"#.*$", "", linea).strip().rstrip("\\").strip()
        if not limpio:
            continue
        encontrado = _REQUISITO.match(limpio)
        if encontrado:
            requisitos.append(Requisito(encontrado.group(1), encontrado.group(2)))
        for valor in _HASH.findall(limpio):
            if not requisitos:
                raise ValueError("un hash sin dependencia delante")
            requisitos[-1].hashes.append(valor)
    return requisitos


def vale_para_windows(fichero: str) -> bool:
    """Si una rueda vale para CPython 3.11 en Windows x64, por las etiquetas de su nombre."""
    if not fichero.endswith(".whl"):
        return False
    partes = fichero[:-4].split("-")
    if len(partes) < 5:
        return False
    pythons, abis, plataformas = (set(p.split(".")) for p in partes[-3:])
    if not plataformas & {"win_amd64", "any"}:
        return False
    if "cp311" in pythons and abis & {"cp311", "none"}:
        return True
    if "abi3" in abis:
        return any(re.fullmatch(r"cp3(\d+)", p) and int(p[3:]) <= 11 for p in pythons)
    return bool(pythons & {"py3", "py311", "py2"}) and "none" in abis


def elegir_rueda(meta: dict, nombre: str) -> tuple[str, str]:
    """El fichero y el sha256 de la unica rueda de PyPI que vale para Windows x64 y 3.11."""
    validas = [(f["filename"], f["digests"]["sha256"]) for f in meta.get("urls", [])
               if vale_para_windows(f.get("filename", ""))]
    if not validas:
        raise ValueError(f"{nombre}: PyPI no tiene ninguna rueda para Windows x64 y Python 3.11")
    especificas = [v for v in validas if "win_amd64" in v[0]]
    elegidas = especificas or validas
    if len(elegidas) != 1:
        raise ValueError(f"{nombre}: valen varias ruedas ({', '.join(f for f, _ in elegidas)}); "
                         "fija la buena a mano")
    return elegidas[0]


def escribir_requisitos(texto: str, hashes: dict[str, str]) -> str:
    """El fichero con el hash de cada PENDIENTE que se ha sacado; lo demas, tal cual."""
    salida = []
    for linea in texto.splitlines():
        encontrado = _REQUISITO.match(linea.strip())
        if encontrado and PENDIENTE in linea and encontrado.group(1) in hashes:
            cabeza = f"{encontrado.group(1)}=={encontrado.group(2)}"
            salida.append(f"{cabeza} \\\n    --hash=sha256:{hashes[encontrado.group(1)]}")
        else:
            salida.append(linea)
    return "\n".join(salida) + "\n"


def pendientes(requisitos: list[Requisito], fijado: dict) -> list[str]:
    """Lo que falta fijar: las dependencias sin hash y el Python embebible."""
    faltan = [r.nombre for r in requisitos if not r.hashes]
    if not re.fullmatch(r"[0-9a-f]{64}", str(fijado.get("python", {}).get("sha256", ""))):
        faltan.append("python-embebible")
    return faltan


def _bajar(url: str) -> bytes:  # pragma: no cover (red)
    with urllib.request.urlopen(url, timeout=60) as respuesta:
        return respuesta.read()


def main(argv: list[str] | None = None) -> int:  # pragma: no cover (red)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--comprobar", action="store_true", help="solo dice que falta")
    args = parser.parse_args(argv)
    texto = REQUISITOS.read_text(encoding="utf-8")
    fijado = json.loads(FIJADO.read_text(encoding="utf-8"))
    faltan = pendientes(leer_requisitos(texto), fijado)
    if args.comprobar or not faltan:
        print("Falta fijar: " + ", ".join(faltan) if faltan else "Todo fijado.")
        return 1 if faltan else 0
    hashes = {}
    for requisito in leer_requisitos(texto):
        if requisito.hashes:
            continue
        meta = json.loads(_bajar(f"{PYPI}/{requisito.nombre}/{requisito.version}/json"))
        fichero, sha256 = elegir_rueda(meta, requisito.nombre)
        print(f"{requisito.nombre}: {fichero} {sha256}")
        hashes[requisito.nombre] = sha256
    REQUISITOS.write_text(escribir_requisitos(texto, hashes), encoding="utf-8")
    if "python-embebible" in faltan:
        contenido = _bajar(fijado["python"]["url"])
        fijado["python"]["sha256"] = hashlib.sha256(contenido).hexdigest()
        print(f"{fijado['python']['fichero']}: {fijado['python']['sha256']}  (comprueba su firma de "
              "Sigstore antes de subirlo: docs/instalacion-nativa.md)")
        FIJADO.write_text(json.dumps(fijado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Revisa windows/requirements-windows.txt y windows/fijado.json y subelos a git.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
