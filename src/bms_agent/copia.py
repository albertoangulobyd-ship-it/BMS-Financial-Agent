"""La copia de seguridad del almacen: la base, sus originales y sus anclas (paso 13).

En el entorno de Docker la base vive en un volumen (datos), que el dueno no
ve como una carpeta de Windows: SQLite necesita bloqueos de verdad, y la
carpeta compartida de Windows con Docker Desktop no los da bien. Por eso la
copia no es "copiar la carpeta": es esta orden, que se lanza con
copia.ps1 hacia el disco externo cifrado.

Lo que hace, y por que:

- la base se copia con la copia en caliente de SQLite (backup): sale entera y
  coherente aunque la consola este abierta y escribiendo; copiar el fichero a
  mano con la consola en marcha puede dejar una copia a medias;
- los originales (documentos/) y las anclas de la auditoria (anclas.log) van
  con ella: sin las anclas, `db verificar` no puede comprobar que nadie corto
  el final de la cadena; sin los originales, la evidencia se queda en lo
  extraido;
- cada copia va en su carpeta con la fecha, y nunca sobrescribe otra;
- un MANIFIESTO.sha256 con el hash de cada fichero, y al acabar se comprueba
  la copia: la base pasa integrity_check y cada fichero tiene el hash del
  manifiesto. Una copia que no se puede leer no es una copia.

`restaurar` hace el camino de vuelta (restaurar.ps1), sin que nadie tenga que
copiar ficheros a mano dentro del volumen.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from .almacen import abrir, raiz_documentos_de, ruta_anclas_de
from .reloj import RELOJ_SISTEMA, ZONA_EMPRESA, Reloj

MANIFIESTO = "MANIFIESTO.sha256"


class CopiaFallida(RuntimeError):
    """La copia no se pudo hacer o no pasa su comprobacion."""


@dataclass
class Copia:
    carpeta: Path
    ficheros: int = 0
    bytes: int = 0
    documentos: int = 0
    problemas: list[str] = field(default_factory=list)


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as fichero:
        for trozo in iter(lambda: fichero.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def leer_manifiesto(carpeta: Path) -> dict[str, str]:
    """Ruta relativa -> sha256, del MANIFIESTO.sha256 de una copia."""
    salida = {}
    for linea in (carpeta / MANIFIESTO).read_text(encoding="utf-8").splitlines():
        if linea.strip():
            sha, relativa = linea.split("  ", 1)
            salida[relativa] = sha
    return salida


def comprobar(carpeta: Path, nombre_base: str) -> list[str]:
    """Los problemas de una copia: la base no pasa integrity_check, un fichero falta, sobra o
    no tiene el hash de su manifiesto. Vacio si esta bien.

    La base se abre como inmutable: comprobar una copia no la toca (abrirla con
    el almacen la pasaria a WAL y le cambiaria el hash), y asi tambien se
    comprueba en un disco montado de solo lectura.
    """
    problemas = []
    base = carpeta / nombre_base
    try:
        conn = sqlite3.connect(f"file:{base}?mode=ro&immutable=1", uri=True)
        try:
            resultado = [f[0] for f in conn.execute("PRAGMA integrity_check")]
        finally:
            conn.close()
        if resultado != ["ok"]:
            problemas.extend(f"la base copiada: {r}" for r in resultado)
    except sqlite3.Error as exc:
        problemas.append(f"la base copiada no se abre: {exc}")
    manifiesto = leer_manifiesto(carpeta)
    presentes = {p.relative_to(carpeta).as_posix() for p in carpeta.rglob("*")
                 if p.is_file() and p.name != MANIFIESTO}
    for relativa in sorted(set(manifiesto) - presentes):
        problemas.append(f"falta {relativa}")
    for relativa in sorted(presentes - set(manifiesto)):
        problemas.append(f"sobra {relativa}: no esta en el manifiesto")
    for relativa in sorted(presentes & set(manifiesto)):
        if _sha256(carpeta / relativa) != manifiesto[relativa]:
            problemas.append(f"{relativa} no tiene el hash del manifiesto")
    return problemas


def copiar(ruta_db: str | Path, destino: str | Path, *, reloj: Reloj | None = None) -> Copia:
    """Copia la base, sus originales y sus anclas en una carpeta nueva dentro de `destino`, y
    la comprueba. CopiaFallida si algo no sale."""
    ruta_db = Path(ruta_db)
    if not ruta_db.is_file():
        raise CopiaFallida(f"no existe la base {ruta_db}")
    destino = Path(destino)
    if not destino.is_dir():
        raise CopiaFallida(f"no existe la carpeta de destino {destino}: hay que conectar el "
                           "disco antes")
    momento = (reloj or RELOJ_SISTEMA).ahora().astimezone(ZoneInfo(ZONA_EMPRESA)).strftime(
        "%Y%m%d-%H%M%S")
    carpeta = destino / f"bms-copia-{ruta_db.stem}-{momento}"
    try:
        carpeta.mkdir()
    except FileExistsError:
        raise CopiaFallida(f"ya hay una copia en {carpeta}: no se sobrescribe") from None
    origen = abrir(ruta_db)
    try:
        copia_conn = sqlite3.connect(carpeta / ruta_db.name)
        try:
            origen.backup(copia_conn)
            # La copia es un solo fichero: sin WAL, abrirla para comprobarla (o en otro
            # ordenador) no deja ficheros -wal y -shm al lado.
            copia_conn.execute("PRAGMA journal_mode = DELETE")
        finally:
            copia_conn.close()
    finally:
        origen.close()
    documentos = raiz_documentos_de(ruta_db)
    if documentos.is_dir():
        shutil.copytree(documentos, carpeta / documentos.name)
    anclas = ruta_anclas_de(ruta_db)
    if anclas.is_file():
        shutil.copy2(anclas, carpeta / anclas.name)
    copia = Copia(carpeta)
    lineas = []
    for fichero in sorted(p for p in carpeta.rglob("*") if p.is_file()):
        relativa = fichero.relative_to(carpeta).as_posix()
        lineas.append(f"{_sha256(fichero)}  {relativa}")
        copia.ficheros += 1
        copia.bytes += fichero.stat().st_size
        copia.documentos += relativa.startswith(f"{documentos.name}/")
    (carpeta / MANIFIESTO).write_text("\n".join(lineas) + "\n", encoding="utf-8")
    copia.problemas = comprobar(carpeta, ruta_db.name)
    if copia.problemas:
        raise CopiaFallida(f"la copia en {carpeta} no pasa su comprobacion: "
                           + "; ".join(copia.problemas[:5]))
    return copia


# ------------------------------------------------------------ restaurar

@dataclass
class Restauracion:
    base: Path
    antes: Path | None
    documentos_anadidos: int = 0


def restaurar(origen: str | Path, ruta_db: str | Path) -> Restauracion:
    """Vuelve a poner una copia en su sitio. CopiaFallida si no se puede hacer con seguridad.

    Antes de tocar nada: la copia tiene que pasar su comprobacion, ser de una
    base del mismo nombre (una copia de la base de prueba no se restaura sobre
    la de verdad, ni al reves) y nadie puede tener la base abierta (la consola
    parada). Lo que habia se guarda primero, entero, en antes-de-restaurar/ al
    lado de la base: restaurar no pierde nada aunque se elija la copia
    equivocada. La base se escribe con la copia en caliente de SQLite, que
    respeta el WAL; los originales que faltan se anaden (nunca se pisa uno, van
    por su hash) y las anclas pasan a ser las de la copia, que son las de esa
    cadena.
    """
    from .almacen import MARCA_DEMO, NOMBRE_DEMO, marca_de_fichero

    origen, ruta_db = Path(origen), Path(ruta_db)
    copia_db = origen / ruta_db.name
    if not copia_db.is_file():
        raise CopiaFallida(f"{origen} no es una copia de {ruta_db.name}")
    if (marca_de_fichero(copia_db) == MARCA_DEMO) != (ruta_db.name == NOMBRE_DEMO):
        raise CopiaFallida("una copia de la base de prueba solo vuelve a la base de prueba, y "
                           "una de la de verdad, a la de verdad")
    problemas = comprobar(origen, ruta_db.name)
    if problemas:
        raise CopiaFallida(f"la copia no pasa su comprobacion: {'; '.join(problemas[:5])}")
    antes = None
    if ruta_db.exists():
        ocupada = sqlite3.connect(ruta_db, timeout=0, isolation_level=None)
        try:
            ocupada.execute("BEGIN EXCLUSIVE")
            ocupada.execute("ROLLBACK")
        except sqlite3.OperationalError:
            raise CopiaFallida("la base esta abierta (la consola en marcha?): para con "
                               "parar.ps1 y vuelve a probar") from None
        finally:
            ocupada.close()
        guardadas = ruta_db.parent / "antes-de-restaurar"
        guardadas.mkdir(exist_ok=True)
        antes = copiar(ruta_db, guardadas).carpeta
    fuente = sqlite3.connect(f"file:{copia_db}?mode=ro&immutable=1", uri=True)
    try:
        destino = sqlite3.connect(ruta_db)
        try:
            fuente.backup(destino)
        finally:
            destino.close()
    finally:
        fuente.close()
    resultado = Restauracion(ruta_db, antes)
    documentos = raiz_documentos_de(ruta_db)
    copiados = origen / documentos.name
    if copiados.is_dir():
        for fichero in sorted(p for p in copiados.rglob("*") if p.is_file()):
            sitio = documentos / fichero.relative_to(copiados)
            if sitio.exists():
                continue
            sitio.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fichero, sitio)
            resultado.documentos_anadidos += 1
    anclas = origen / ruta_anclas_de(ruta_db).name
    if anclas.is_file():
        shutil.copy2(anclas, ruta_anclas_de(ruta_db))
    return resultado
