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
- las anclas se copian ANTES que la base: con la consola en marcha algo
  puede anclar mientras se copia, y un ancla mas nueva que la base copiada
  haria que la copia no pasara `db verificar` (la cadena no llegaria a ella).
  Un ancla mas vieja que la base siempre se cumple. Los originales, despues:
  cada documento de la base copiada ya tiene su original escrito;
- cada copia va en su carpeta con la fecha, y nunca sobrescribe otra;
- un MANIFIESTO.sha256 con el hash de cada fichero, y al acabar se comprueba
  la copia: la base pasa integrity_check, su cadena de auditoria cumple las
  anclas copiadas (lo mismo que miraria `db verificar`) y cada fichero tiene
  el hash del manifiesto. Una copia que no se puede leer no es una copia.

La carpeta out/ (las extracciones exportadas) no va en la copia: lo que hace
falta de ella esta en la base, y el extractor no vuelve a pagar un PDF cuya
extraccion vigente ya esta en la base (extract.extraer_pasada).

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

ANTES_DE_RESTAURAR = "antes-de-restaurar"

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


def cortes_que_valen(fichero, ruta_db: Path, *, comprobar_antes: bool = True,
                     ) -> tuple[set[tuple[int, str]], list[str]]:
    """Las anclas que perdonan los cortes del fichero de anclas, y lo que falla de ellos.

    Un corte perdona su ancla si lo sustituido sigue donde dice, con el hash
    que dice (la base guardada en antes-de-restaurar/ al restaurar). Si ya no
    esta, es un problema: lo que la restauracion quito no se puede ver en
    ningun sitio. Un corte sin nada guardado (una instalacion nueva) perdona
    sin mas. En una copia (`comprobar_antes` falso) lo sustituido se quedo en
    el ordenador de la base, y basta con que el corte este en sus anclas.
    """
    perdonadas: set[tuple[int, str]] = set()
    problemas: list[str] = []
    for corte in fichero.cortes:
        if comprobar_antes and corte.antes is not None:
            guardada = ruta_db.parent / corte.antes / ruta_db.name
            if not guardada.is_file() or _sha256(guardada) != corte.antes_sha256:
                problemas.append(
                    f"la restauracion que corto el ancla {corte.id} dejo lo sustituido en "
                    f"{corte.antes}, y ya no esta ahi (o no es lo que se guardo)")
                continue
        perdonadas.add((corte.id, corte.hash))
    return perdonadas, problemas


def _problemas_de_la_cadena(conn: sqlite3.Connection, anclas: Path,
                            ruta_db: Path | None = None) -> list[str]:
    """Lo que `db verificar` diria de la cadena de la copia con sus anclas: sin esto, una copia
    con un ancla mas alla de su cadena pasaria por buena y no se podria restaurar."""
    from .auditoria import leer_fichero, verificar_cadena

    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'evento'"
                    ).fetchone() is None:
        return []
    fichero = leer_fichero(anclas)
    perdonadas, _ = cortes_que_valen(fichero, ruta_db or anclas, comprobar_antes=False)
    return [f"la cadena de la copia: {p}"
            for p in fichero.malas + verificar_cadena(conn, fichero.anclas, fichero=fichero,
                                                      perdonadas=perdonadas).problemas]


def comprobar(carpeta: Path, nombre_base: str, *, cadena: bool = True) -> list[str]:
    """Los problemas de una copia: la base no pasa integrity_check, su cadena no cumple sus
    anclas, un fichero falta, sobra o no tiene el hash de su manifiesto. Vacio si esta bien.

    La base se abre como inmutable: comprobar una copia no la toca (abrirla con
    el almacen la pasaria a WAL y le cambiaria el hash), y asi tambien se
    comprueba en un disco montado de solo lectura. `cadena=False` solo lo usa
    la copia de antes de restaurar (lo que habia puede ser justo lo que esta
    mal, y se guarda igual).
    """
    problemas = []
    base = carpeta / nombre_base
    try:
        conn = sqlite3.connect(f"file:{base}?mode=ro&immutable=1", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            resultado = [f[0] for f in conn.execute("PRAGMA integrity_check")]
            if resultado != ["ok"]:
                problemas.extend(f"la base copiada: {r}" for r in resultado)
            elif cadena:
                problemas.extend(_problemas_de_la_cadena(
                    conn, carpeta / ruta_anclas_de(base).name))
        finally:
            conn.close()
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


def _carpeta_nueva(destino: Path, nombre: str, *, numerar: bool) -> Path:
    for intento in range(1, 100 if numerar else 2):
        carpeta = destino / (nombre if intento == 1 else f"{nombre}-{intento}")
        try:
            carpeta.mkdir()
            return carpeta
        except FileExistsError:
            continue
    raise CopiaFallida(f"ya hay una copia en {destino / nombre}: no se sobrescribe")


def copiar(ruta_db: str | Path, destino: str | Path, *, reloj: Reloj | None = None,
           conexion: sqlite3.Connection | None = None, cadena: bool = True,
           numerar: bool = False) -> Copia:
    """Copia la base, sus originales y sus anclas en una carpeta nueva dentro de `destino`, y
    la comprueba. CopiaFallida si algo no sale.

    `conexion` es una conexion ya abierta a la base (restaurar copia con la que
    tiene la base en exclusiva); sin ella, se abre con el almacen. `numerar`
    anade -2, -3... si ya hay una copia de ese segundo (la de antes de
    restaurar no puede dejar de hacerse por eso).
    """
    ruta_db = Path(ruta_db)
    if not ruta_db.is_file():
        raise CopiaFallida(f"no existe la base {ruta_db}")
    destino = Path(destino)
    if not destino.is_dir():
        raise CopiaFallida(f"no existe la carpeta de destino {destino}: hay que conectar el "
                           "disco antes")
    momento = (reloj or RELOJ_SISTEMA).ahora().astimezone(ZoneInfo(ZONA_EMPRESA)).strftime(
        "%Y%m%d-%H%M%S")
    carpeta = _carpeta_nueva(destino, f"bms-copia-{ruta_db.stem}-{momento}", numerar=numerar)
    anclas = ruta_anclas_de(ruta_db)
    if anclas.is_file():
        shutil.copy2(anclas, carpeta / anclas.name)
    origen = conexion if conexion is not None else abrir(ruta_db)
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
        if conexion is None:
            origen.close()
    documentos = raiz_documentos_de(ruta_db)
    if documentos.is_dir():
        shutil.copytree(documentos, carpeta / documentos.name)
    copia = Copia(carpeta)
    lineas = []
    for fichero in sorted(p for p in carpeta.rglob("*") if p.is_file()):
        relativa = fichero.relative_to(carpeta).as_posix()
        lineas.append(f"{_sha256(fichero)}  {relativa}")
        copia.ficheros += 1
        copia.bytes += fichero.stat().st_size
        copia.documentos += relativa.startswith(f"{documentos.name}/")
    (carpeta / MANIFIESTO).write_text("\n".join(lineas) + "\n", encoding="utf-8")
    copia.problemas = comprobar(carpeta, ruta_db.name, cadena=cadena)
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
    evento_id: int | None = None
    anclas_descartadas: int = 0


def _en_exclusiva(ruta_db: Path) -> sqlite3.Connection:
    """Una conexion que tiene la base para ella sola mientras este abierta. CopiaFallida si
    otro la tiene abierta.

    La base va en WAL, y en WAL una conexion abierta y quieta no bloquea un
    BEGIN EXCLUSIVE: asi no se ve una consola en marcha. Salir de WAL
    (journal_mode=DELETE) si exige ser la unica conexion: falla con "database
    is locked" si hay otra, aunque no este haciendo nada. Con locking_mode
    EXCLUSIVE y una escritura, el cerrojo se queda hasta cerrar: nadie entra
    entre la copia de antes y la restauracion.
    """
    conn = sqlite3.connect(ruta_db, timeout=0, isolation_level=None)
    try:
        modo = conn.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
        if str(modo).lower() != "delete":
            raise sqlite3.OperationalError(f"journal_mode sigue en {modo}")
        conn.execute("PRAGMA locking_mode = EXCLUSIVE")
        conn.execute("BEGIN EXCLUSIVE")
        conn.execute("COMMIT")
    except sqlite3.OperationalError:
        conn.close()
        raise CopiaFallida("la base esta abierta (la consola en marcha?): para con "
                           "parar.ps1 y vuelve a probar") from None
    conn.row_factory = sqlite3.Row
    return conn


def _juntar_anclas(copiadas: Path, propias: Path) -> None:
    """Las anclas de la copia que el fichero de la base no tiene, al final. El fichero solo
    crece (auditoria.anclar): restaurar no borra las anclas de lo que sustituye, que siguen
    diciendo lo que llego a haber."""
    if not copiadas.is_file():
        return
    ya = set(propias.read_text(encoding="utf-8").splitlines()) if propias.is_file() else set()
    nuevas = [linea for linea in copiadas.read_text(encoding="utf-8").splitlines()
              if linea.strip() and linea not in ya]
    if nuevas:
        propias.parent.mkdir(parents=True, exist_ok=True)
        with propias.open("a", encoding="utf-8", newline="") as fichero:
            fichero.write("".join(f"{linea}\n" for linea in nuevas))


def _cabeza(conn: sqlite3.Connection) -> list | None:
    from .auditoria import cabeza

    tiene = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'evento'").fetchone()
    fila = cabeza(conn) if tiene else None
    return [fila.id, fila.hash] if fila else None


def restaurar(origen: str | Path, ruta_db: str | Path, *, reloj: Reloj | None = None
              ) -> Restauracion:
    """Vuelve a poner una copia en su sitio. CopiaFallida si no se puede hacer con seguridad.

    Antes de tocar nada: la copia tiene que pasar su comprobacion, ser de una
    base del mismo nombre (una copia de la base de prueba no se restaura sobre
    la de verdad, ni al reves) y nadie puede tener la base abierta (la consola
    parada; _en_exclusiva lo comprueba tambien en WAL y no suelta la base
    hasta acabar). Lo que habia se guarda primero, entero, en
    antes-de-restaurar/ al lado de la base: restaurar no pierde nada aunque se
    elija la copia equivocada. La base se escribe con la copia en caliente de
    SQLite; los originales que faltan se anaden (nunca se pisa uno, van por su
    hash).

    Restaurar corta la cadena de auditoria: lo firmado despues de la copia se
    va. Eso no se esconde. El fichero de anclas no se reescribe (solo crece:
    se le anaden las de la copia que no tenga), y la base restaurada recibe un
    evento `restauracion` con la copia, las dos cabezas y las anclas que deja
    sin cumplir, que se ancla en seguida. Esas anclas se apuntan tambien en el
    fichero de anclas, con la carpeta y el hash de lo sustituido: `db
    verificar` solo perdona las que nombra el fichero, si lo sustituido sigue
    alli, y dice que hubo una restauracion. Lo firma el operador del fichero
    (el usuario de sistema), como las ordenes de `usuario`: quien tiene la
    base ya puede sacar un token con `usuario token`, asi que pedir uno aqui no
    protegeria nada.
    """
    from .almacen import MARCA_DEMO, NOMBRE_DEMO, marca_de_fichero, transaccion, usuario_sistema
    from .auditoria import (
        TIPO_RESTAURACION,
        anclar,
        anclas_sin_cumplir,
        apuntar_cortes,
        leer_anclas,
        registrar,
    )

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
    # En una instalacion nueva (recuperar tras perder el ordenador) la carpeta aun no existe.
    ruta_db.parent.mkdir(parents=True, exist_ok=True)
    habia = ruta_db.is_file() and ruta_db.stat().st_size > 0
    antes = sustituida = None
    exclusiva = _en_exclusiva(ruta_db)
    try:
        if habia:
            sustituida = _cabeza(exclusiva)
            guardadas = ruta_db.parent / ANTES_DE_RESTAURAR
            guardadas.mkdir(exist_ok=True)
            antes = copiar(ruta_db, guardadas, reloj=reloj, conexion=exclusiva,
                           cadena=False, numerar=True).carpeta
        fuente = sqlite3.connect(f"file:{copia_db}?mode=ro&immutable=1", uri=True)
        try:
            fuente.backup(exclusiva)
        finally:
            fuente.close()
    finally:
        exclusiva.close()
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
    ruta_anclas = ruta_anclas_de(ruta_db)
    _juntar_anclas(origen / ruta_anclas.name, ruta_anclas)

    conn = abrir(ruta_db, reloj=reloj)
    try:
        if _cabeza(conn) is None:
            return resultado
        leidas, _malas = leer_anclas(ruta_anclas)
        cortadas = anclas_sin_cumplir(conn, leidas)
        # Lo que perdona el corte va fuera de la base, con donde quedo lo sustituido: un
        # evento de restauracion lo puede escribir quien escribe la base (auditoria).
        apuntar_cortes(conn, ruta_anclas, cortadas,
                       antes=(str(antes.relative_to(ruta_db.parent)) if antes is not None
                              else None),
                       antes_sha256=_sha256(antes / ruta_db.name) if antes is not None else None)
        with transaccion(conn):
            resultado.evento_id = registrar(
                conn, tipo=TIPO_RESTAURACION, actor=usuario_sistema(conn, "sistema"),
                motivo=f"restaurada desde la copia {origen.name}",
                datos={"copia": str(origen), "cabeza_copia": _cabeza(conn),
                       "sustituida": sustituida,
                       "antes": str(antes) if antes is not None else None,
                       "anclas_descartadas": [[a.id, a.hash] for a in cortadas]})
        anclar(conn, ruta_anclas)
    finally:
        conn.close()
    resultado.anclas_descartadas = len(cortadas)
    return resultado
