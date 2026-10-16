"""Fija lo que baja la instalacion nativa de Windows (pasos 14 y 14b). Para quien mantiene el programa.

El instalador (windows/instalar.ps1) no baja nada cuyo sha256 no este fijado en
windows/fijado.json (el Python de Windows) y windows/requirements-windows.txt (cada rueda).
Este script los rellena, con internet, y deja los dos ficheros para revisarlos y subirlos a
git:

    python scripts/fijar_windows.py                   rellena lo que falte
    python scripts/fijar_windows.py --rehacer         lo vuelve a sacar todo, aunque ya este
    python scripts/fijar_windows.py --python 3.13.X   otra version del Python que nuget.org
                                                      tenga (y sus ruedas)
    python scripts/fijar_windows.py --comprobar       sin red: dice que falta o que no cuadra
                                                      (sale con 1 si algo no esta bien)
    python scripts/fijar_windows.py --comprobar --paquetes CARPETA
                                                      ademas, los ficheros ya bajados

- El Python: el paquete "python" de nuget.org, que publica la Python Software Foundation
  (python.org lo da como una de sus distribuciones oficiales para Windows). Se baja de
  https://api.nuget.org/v3-flatcontainer/ y se calcula su sha256; ese numero solo dice que
  es lo que nuget.org sirve hoy, asi que se cruza con el SHA-512 que nuget.org publica de
  esa version en su catalogo (packageHash), al que se llega por el indice de registro. Si
  no son el mismo fichero, se para. El paquete y el catalogo son los dos de nuget.org: el
  cruce dice que lo bajado es lo que nuget.org lista, no de donde viene. De donde viene lo
  dice la firma Authenticode de la Python Software Foundation en python.exe y en la DLL, que
  comprueba el instalador en Windows; quien sube un sha256 nuevo la mira antes en un Windows
  (docs/instalacion-nativa.md, apartado 17). Tambien se mira que sea un zip con
  tools/python.exe, la DLL de esa version y la biblioteca, que es lo que el instalador abre.

Una version menor solo tiene binarios para Windows (tambien en nuget.org) mientras esta en
su fase de correcciones; las de solo seguridad salen en codigo fuente. Cuando --python 3.13.X
ya no encuentra el paquete, lo siguiente es la version menor siguiente (nativo.VERSION_PYTHON,
windows/comun.ps1 y la suite pasando en ella).
- Las ruedas: el sha256 que publica PyPI (https://pypi.org/pypi/NOMBRE/VERSION/json) de la
  rueda que vale para Windows x64 y esa version de CPython (cp3XY-win_amd64, abi3 o
  py3-none-any). Si valen dos, se dice y se para. Las versiones son las de
  docker/requirements.txt, mas tzdata: --comprobar lo exige.

No toca src/ ni nada de lo que corre: es una herramienta de quien prepara la version.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import re
import sys
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REQUISITOS = RAIZ / "windows" / "requirements-windows.txt"
REQUISITOS_DOCKER = RAIZ / "docker" / "requirements.txt"
FIJADO = RAIZ / "windows" / "fijado.json"
PYPI = "https://pypi.org/pypi"
NUGET_PAQUETES = "https://api.nuget.org/v3-flatcontainer/python"
NUGET_REGISTRO = "https://api.nuget.org/v3/registration5-gz-semver2/python/index.json"
NUGET_CATALOGO = "https://api.nuget.org/v3/catalog0/"
ORIGEN = "nuget.org: python, Python Software Foundation"
FIRMANTE = "Python Software Foundation"
# Lo que Windows trae y Docker no necesita: la base de zonas horarias (reloj.hoy()).
SOLO_WINDOWS = {"tzdata"}

_REQUISITO = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9_.+!-]+)")
_HASH = re.compile(r"--hash=sha256:([0-9a-f]{64})")
_VERSION = re.compile(r"3\.(\d+)\.(\d+)")


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


def normalizado(nombre: str) -> str:
    """El nombre como lo compara pip (PEP 503): PyYAML y pyyaml, typing_extensions y
    typing-extensions son el mismo."""
    return re.sub(r"[-_.]+", "-", nombre).lower()


def menor_de(version: str) -> int:
    """El 13 de 3.13.16: las etiquetas de las ruedas (cp313) dependen de el."""
    encontrado = _VERSION.fullmatch(version)
    if not encontrado:
        raise ValueError(f"{version!r} no es una version de Python 3 (3.X.Y)")
    return int(encontrado.group(1))


def vale_para_windows(fichero: str, menor: int) -> bool:
    """Si una rueda vale para CPython 3.<menor> en Windows x64, por las etiquetas de su nombre.
    Las de hilos libres (cp313t) no: el Python de la instalacion es el normal."""
    if not fichero.endswith(".whl"):
        return False
    partes = fichero[:-4].split("-")
    if len(partes) < 5:
        return False
    pythons, abis, plataformas = (set(p.split(".")) for p in partes[-3:])
    if not plataformas & {"win_amd64", "any"}:
        return False
    etiqueta = f"cp3{menor}"
    if etiqueta in pythons and abis & {etiqueta, "none"}:
        return True
    if "abi3" in abis:
        return any(re.fullmatch(r"cp3(\d+)", p) and int(p[3:]) <= menor for p in pythons)
    return bool(pythons & {"py3", f"py3{menor}"}) and "none" in abis


def elegir_rueda(meta: dict, nombre: str, menor: int) -> tuple[str, str]:
    """El fichero y el sha256 de la unica rueda de PyPI que vale para Windows x64 y 3.<menor>.
    Una retirada (yanked) no vale."""
    validas = [(f["filename"], f["digests"]["sha256"]) for f in meta.get("urls", [])
               if vale_para_windows(f.get("filename", ""), menor) and not f.get("yanked")]
    if not validas:
        raise ValueError(f"{nombre}: PyPI no tiene ninguna rueda para Windows x64 y Python 3.{menor}")
    especificas = [v for v in validas if "win_amd64" in v[0]]
    elegidas = especificas or validas
    if len(elegidas) != 1:
        raise ValueError(f"{nombre}: valen varias ruedas ({', '.join(f for f, _ in elegidas)}); "
                         "fija la buena a mano")
    return elegidas[0]


def escribir_requisitos(texto: str, hashes: dict[str, list[str]]) -> str:
    """El fichero con los hashes nuevos de las dependencias de `hashes` (lo que tuvieran antes,
    fuera, y un comentario PENDIENTE tambien); lo demas, tal cual."""
    lineas = texto.splitlines()
    salida: list[str] = []
    i = 0
    while i < len(lineas):
        linea = lineas[i]
        encontrado = _REQUISITO.match(linea)
        if not encontrado or encontrado.group(1) not in hashes:
            salida.append(linea)
            i += 1
            continue
        nuevos = hashes[encontrado.group(1)]
        if not nuevos or not all(re.fullmatch(r"[0-9a-f]{64}", h) for h in nuevos):
            raise ValueError(f"{encontrado.group(1)}: sin un sha256 que valga")
        salida.append(f"{encontrado.group(1)}=={encontrado.group(2)} \\")
        salida.extend(f"    --hash=sha256:{h}" + (" \\" if n < len(nuevos) - 1 else "")
                      for n, h in enumerate(nuevos))
        sigue = re.sub(r"#.*$", "", linea).rstrip().endswith("\\")
        i += 1
        while sigue and i < len(lineas):
            sigue = lineas[i].rstrip().endswith("\\")
            i += 1
    return "\n".join(salida) + "\n"


def url_del_paquete(version: str) -> str:
    return f"{NUGET_PAQUETES}/{version}/python.{version}.nupkg"


def sha512_nuget(contenido: bytes) -> str:
    """El SHA-512 como lo publica nuget.org (packageHash): en base64."""
    return base64.b64encode(hashlib.sha512(contenido).digest()).decode("ascii")


def entrada_del_registro(indice: dict, paginas: dict[str, dict], version: str) -> dict:
    """La entrada de esa version en el indice de registro de nuget.org (sus paginas pueden
    venir dentro del indice o aparte, en `paginas` por su @id)."""
    for pagina in indice.get("items", []):
        hojas = pagina.get("items")
        if hojas is None:
            hojas = paginas.get(pagina.get("@id", ""), {}).get("items", [])
        for hoja in hojas:
            entrada = hoja.get("catalogEntry", {})
            if entrada.get("version") == version:
                return hoja
    raise ValueError(f"nuget.org no tiene la version {version} del paquete python")


def cruzar_con_el_catalogo(contenido: bytes, catalogo: dict, version: str) -> list[str]:
    """Lo que no cuadra entre el fichero bajado y lo que nuget.org dice de el en su catalogo:
    el mismo paquete (id y version), de la Python Software Foundation, con el mismo SHA-512 y
    el mismo tamano. Vacio si todo cuadra."""
    malos = []
    if str(catalogo.get("id", "")).lower() != "python" or catalogo.get("version") != version:
        malos.append(f"el catalogo es de {catalogo.get('id')} {catalogo.get('version')}, "
                     f"no de python {version}")
    if FIRMANTE not in str(catalogo.get("authors", "")):
        malos.append(f"el autor del paquete no es la {FIRMANTE}: {catalogo.get('authors')!r}")
    if catalogo.get("packageHashAlgorithm") != "SHA512":
        malos.append(f"el catalogo no publica un SHA-512 ({catalogo.get('packageHashAlgorithm')})")
    elif catalogo.get("packageHash") != sha512_nuget(contenido):
        malos.append("el SHA-512 de lo bajado no es el que publica nuget.org: no es el mismo fichero")
    if catalogo.get("packageSize") not in (None, len(contenido)):
        malos.append(f"lo bajado tiene {len(contenido)} bytes y nuget.org dice "
                     f"{catalogo.get('packageSize')}")
    return malos


def revisar_paquete(contenido: bytes, version: str) -> list[str]:
    """Lo que no cuadra en el paquete con lo que el instalador espera abrir: un zip cuyo
    nuspec es el de python <version> de la Python Software Foundation, y que, con lo que se
    saca para cada papel (nativo.destino_en_runtime), deja un solo programa, python.exe, y
    lo necesario (la DLL de esa version, la biblioteca, los .pyd)."""
    nativo = _nativo()
    try:
        paquete = zipfile.ZipFile(io.BytesIO(contenido))
        nombres = paquete.namelist()
        nuspec = paquete.read("python.nuspec").decode("utf-8-sig")
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError) as exc:
        return [f"no es un paquete de NuGet que se pueda abrir ({exc})"]
    malos = []
    for etiqueta, esperado in (("id", "python"), ("version", version), ("authors", FIRMANTE)):
        if not re.search(rf"<{etiqueta}>{re.escape(esperado)}</{etiqueta}>", nuspec):
            malos.append(f"el nuspec no dice {etiqueta} = {esperado}")
    try:
        destinos = {d.lower() for d in map(nativo.destino_en_runtime, nombres) if d}
    except nativo.PaqueteNoValido as exc:
        return malos + [str(exc)]
    dll = f"python3{menor_de(version)}.dll"
    for necesario in (*nativo.NECESARIOS_DEL_RUNTIME, dll):
        if necesario.lower() not in destinos:
            malos.append(f"al paquete le falta tools/{necesario}")
    programas = sorted(d for d in destinos if d.endswith((".exe", ".com", ".scr")))
    if programas != ["python.exe"]:
        malos.append(f"en cada papel quedarian estos programas, y tiene que ser solo python.exe: "
                     f"{programas}")
    return malos


def problemas_de_las_dependencias(requisitos: list[Requisito], docker: list[Requisito]
                                  ) -> list[str]:
    """Lo que falta o no cuadra en requirements-windows.txt: cada dependencia con su sha256, y
    las mismas que docker/requirements.txt (mas tzdata) con las mismas versiones."""
    malos = [f"{r.nombre}: sin sha256" for r in requisitos if not r.hashes]
    windows = {normalizado(r.nombre): r for r in requisitos}
    de_docker = {normalizado(r.nombre): r for r in docker}
    for nombre in sorted(set(de_docker) - set(windows)):
        malos.append(f"{nombre}: esta en docker/requirements.txt y no en requirements-windows.txt")
    for nombre in sorted(set(windows) - set(de_docker) - SOLO_WINDOWS):
        malos.append(f"{nombre}: esta en requirements-windows.txt y no en docker/requirements.txt")
    for nombre in sorted(set(windows) & set(de_docker)):
        if windows[nombre].version != de_docker[nombre].version:
            malos.append(f"{nombre}: {windows[nombre].version} en Windows y "
                         f"{de_docker[nombre].version} en Docker")
    return malos


def problemas_del_python(fijado: dict) -> list[str]:
    """Lo que falta o no cuadra en fijado.json: el paquete de nuget.org entero (url, fichero,
    sha256, el SHA-512 de nuget.org, la entrada del catalogo, el firmante), y de la version
    menor que espera el codigo (nativo.VERSION_PYTHON: el nombre de la DLL y del ._pth)."""
    python = fijado.get("python", {}) if isinstance(fijado, dict) else {}
    version = str(python.get("version", ""))
    try:
        menor = menor_de(version)
    except ValueError as exc:
        return [f"python: {exc}"]
    malos = []
    esperada = _nativo().VERSION_PYTHON
    if (3, menor) != tuple(esperada):
        malos.append(f"python: {version} no es la {esperada[0]}.{esperada[1]} que espera "
                     "nativo.VERSION_PYTHON")
    if python.get("origen") != ORIGEN:
        malos.append(f"python: el origen tiene que ser {ORIGEN!r}")
    if python.get("url") != url_del_paquete(version):
        malos.append(f"python: la url tiene que ser {url_del_paquete(version)}")
    if python.get("fichero") != f"python.{version}.nupkg":
        malos.append(f"python: el fichero tiene que ser python.{version}.nupkg")
    if not re.fullmatch(r"[0-9a-f]{64}", str(python.get("sha256", ""))):
        malos.append("python: sin sha256")
    try:
        sha512 = base64.b64decode(str(python.get("sha512", "")), validate=True)
    except ValueError:
        sha512 = b""
    if len(sha512) != 64:
        malos.append("python: sin el SHA-512 de nuget.org (en base64, como lo publica)")
    if not str(python.get("catalogo", "")).startswith(NUGET_CATALOGO):
        malos.append(f"python: sin la entrada del catalogo de nuget.org ({NUGET_CATALOGO}...)")
    if python.get("firmante") != FIRMANTE:
        malos.append(f"python: el firmante tiene que ser {FIRMANTE!r}")
    return malos


def problemas(requisitos: list[Requisito], docker: list[Requisito], fijado: dict) -> list[str]:
    """Todo lo que falta o no cuadra, sin red. Vacio si todo esta."""
    return problemas_de_las_dependencias(requisitos, docker) + problemas_del_python(fijado)


def problemas_de_los_paquetes(carpeta: Path, requisitos: list[Requisito], fijado: dict
                              ) -> list[str]:
    """Con los ficheros ya bajados (la carpeta windows\\paquetes que usa el instalador sin
    internet): que el del Python tenga el sha256 y el SHA-512 fijados y sea un paquete que el
    instalador sabe abrir, y que cada dependencia tenga una rueda con uno de sus hashes."""
    malos = []
    python = fijado["python"]
    fichero = carpeta / python["fichero"]
    if not fichero.is_file():
        malos.append(f"falta {fichero}")
    else:
        contenido = fichero.read_bytes()
        if hashlib.sha256(contenido).hexdigest() != python["sha256"]:
            malos.append(f"{fichero.name}: su sha256 no es el fijado")
        if sha512_nuget(contenido) != python["sha512"]:
            malos.append(f"{fichero.name}: su SHA-512 no es el de nuget.org")
        malos += [f"{fichero.name}: {m}" for m in revisar_paquete(contenido, python["version"])]
    ruedas = {hashlib.sha256(r.read_bytes()).hexdigest() for r in carpeta.glob("*.whl")}
    malos += [f"{r.nombre}: no hay ninguna rueda con su sha256 en {carpeta}" for r in requisitos
              if not set(r.hashes) & ruedas]
    return malos


def _nativo():
    """bms_agent.nativo, del src de este proyecto: lo que el instalador saca del paquete."""
    src = str(RAIZ / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from bms_agent import nativo

    return nativo


def _bajar(url: str) -> bytes:  # pragma: no cover (red)
    peticion = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(peticion, timeout=120) as respuesta:
        datos = respuesta.read()
        if respuesta.headers.get("Content-Encoding", "").lower() == "gzip":
            datos = gzip.decompress(datos)
    return datos


def _json(url: str) -> dict:  # pragma: no cover (red)
    return json.loads(_bajar(url))


def fijar_python(version: str) -> dict:  # pragma: no cover (red)
    """El Python de nuget.org, bajado y cruzado con su catalogo. Para si algo no cuadra."""
    indice = _json(NUGET_REGISTRO)
    paginas = {p["@id"]: _json(p["@id"]) for p in indice.get("items", []) if "items" not in p}
    hoja = entrada_del_registro(indice, paginas, version)
    url_catalogo = hoja["catalogEntry"]["@id"]
    if not url_catalogo.startswith(NUGET_CATALOGO):
        raise SystemExit(f"la entrada del catalogo no es de nuget.org: {url_catalogo}")
    catalogo = _json(url_catalogo)
    url = url_del_paquete(version)
    contenido = _bajar(url)
    malos = cruzar_con_el_catalogo(contenido, catalogo, version) + revisar_paquete(contenido, version)
    if malos:
        raise SystemExit("El paquete de Python no vale:\n  " + "\n  ".join(malos))
    return {"version": version, "origen": ORIGEN, "fichero": f"python.{version}.nupkg",
            "url": url, "sha256": hashlib.sha256(contenido).hexdigest(),
            "sha512": catalogo["packageHash"], "catalogo": url_catalogo, "firmante": FIRMANTE}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--comprobar", action="store_true",
                        help="sin red: solo dice que falta o no cuadra (sale con 1 si algo)")
    parser.add_argument("--paquetes", type=Path,
                        help="con --comprobar: la carpeta con lo ya bajado (windows\\paquetes)")
    parser.add_argument("--rehacer", action="store_true", help="vuelve a sacarlo todo")
    parser.add_argument("--python", help="otra version del Python de nuget.org (3.X.Y)")
    args = parser.parse_args(argv)
    texto = REQUISITOS.read_text(encoding="utf-8")
    fijado = json.loads(FIJADO.read_text(encoding="utf-8"))
    docker = leer_requisitos(REQUISITOS_DOCKER.read_text(encoding="utf-8"))
    if args.comprobar:
        malos = problemas(leer_requisitos(texto), docker, fijado)
        if not malos and args.paquetes:
            malos = problemas_de_los_paquetes(args.paquetes, leer_requisitos(texto), fijado)
        print("No esta bien:\n  " + "\n  ".join(malos) if malos else "Todo fijado.")
        return 1 if malos else 0
    return _rellenar(texto, fijado, args.rehacer, args.python)  # pragma: no cover (red)


def _rellenar(texto: str, fijado: dict, rehacer: bool, version: str | None
              ) -> int:  # pragma: no cover (red)
    python = fijado.get("python", {})
    version = version or python.get("version", "")
    menor = menor_de(version)
    nuevo_python = rehacer or version != python.get("version") or bool(
        problemas_del_python(fijado))
    if nuevo_python:
        fijado["python"] = fijar_python(version)
        print(f"python {version}: {fijado['python']['url']}\n  sha256 {fijado['python']['sha256']}"
              f"\n  sha512 {fijado['python']['sha512']} (el de nuget.org)")
    cambiar_ruedas = rehacer or version != python.get("version")
    hashes = {}
    for requisito in leer_requisitos(texto):
        if requisito.hashes and not cambiar_ruedas:
            continue
        meta = _json(f"{PYPI}/{requisito.nombre}/{requisito.version}/json")
        fichero, sha256 = elegir_rueda(meta, requisito.nombre, menor)
        print(f"{requisito.nombre}: {fichero} {sha256}")
        hashes[requisito.nombre] = [sha256]
    REQUISITOS.write_text(escribir_requisitos(texto, hashes), encoding="utf-8")
    FIJADO.write_text(json.dumps(fijado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Revisa windows/requirements-windows.txt y windows/fijado.json (y, con otra version "
          "de Python, nativo.VERSION_PYTHON) y subelos a git.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
