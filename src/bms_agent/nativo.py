"""La instalacion nativa de Windows, sin Docker (paso 14, docs/instalacion-nativa.md).

La misma separacion que el entorno de Docker, hecha con lo que trae Windows. Cada
papel (consola, lector, salida, orden) tiene su propio interprete de Python, una copia
real del Python de Windows en runtime/<papel>/python.exe, y el cortafuegos de Windows
tiene reglas para cada uno por su ruta: la consola, el lector y las ordenes sin red
(ni de salida ni de entrada), la salida solo al puerto 443. No vale un entorno virtual:
su python.exe es un lanzador que arranca el Python de la base como otro proceso, y el
cortafuegos veria siempre ese.

Ese Python es el paquete "python" de nuget.org, el que publica la Python Software
Foundation (python.org lo da como una de sus distribuciones oficiales para Windows), en
la version 3.13 (paso 14b): la 3.11 ya no tiene binarios para Windows con sus
correcciones de seguridad. El paquete es un zip; de el, el instalador saca tools/ menos
lo que no es el interprete (destino_en_runtime) y le pone su ._pth.

Lo que el codigo sabe de esa instalacion vive aqui:

- `detectar`: si el interprete que corre es uno de los de la instalacion, y cual (su
  carpeta es su papel). Lo dice instalacion.json, en la raiz, que solo escribe el
  instalador y que el usuario no puede tocar (la raiz es de solo lectura para el, y la
  comprobacion de aislamiento lo prueba). Un interprete con la forma de la instalacion
  (runtime/<papel>/ con su python3XY._pth) sin instalacion.json es un error, no un "no
  hay": si no, borrar ese fichero apagaria todas las puertas. Fuera de ella (el
  desarrollo, Docker, los tests) no hay instalacion y nada de esto cambia.
- `exigir_lectura`: la puerta de cualquier llamada a la API (extract, coste --estimar,
  reextraer). Solo el lector, solo por el proxy de esta pasada y solo si la comprobacion
  de aislamiento del lector y de la salida de esta misma pasada salio bien
  (aislamiento.motivo_para_no_leer). Sin comprobacion, o con una que falla, no se paga
  nada: falla cerrada, y no hay opcion para saltarsela.
- `clave_del_lector`: la clave de la API, cifrada con DPAPI (secretos.py), solo para el
  lector.
- `contenido_pth` y `destino_en_runtime`: lo que el instalador escribe en el ._pth de
  cada papel y lo que saca del paquete de NuGet.

- `prohibir_procesos`: en la instalacion, ningun codigo de Python del proceso (tampoco
  el de las dependencias) arranca otro programa. El codigo de la app no lo hace (lo
  vigila test_instalacion_nativa por el AST), pero las dependencias si podrian sin que
  nadie lo viera: el SDK de la API, al montar su cabecera X-Stainless-OS, llama a
  platform.system(), y en Windows eso pregunta a WMI y, si WMI no contesta, ejecuta `ver`
  con cmd.exe (con Python 3.11, siempre `ver`). Un gancho de auditoria (sys.addaudithook,
  que no se puede quitar) dice que no a cada forma de lanzar un proceso; platform lo toma
  como "no hay ver" y saca la version de sys.getwindowsversion.

Lo que no puede hacer y se dice en la guia: el cortafuegos distingue programas, y un
proceso comprometido podria arrancar otro programa que no tenga reglas. Contra eso, el
gancho (que codigo nativo con ctypes podria saltarse) y, si se quiere mas, el usuario de
Windows aparte, AppContainer o la variante de Docker.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from .aislamiento import FICHERO as FICHERO_AISLAMIENTO, ROLES, motivo_para_no_leer

FICHERO_INSTALACION = "instalacion.json"
VERSION_INSTALACION = 1
PUERTO_CONSOLA = 8765
PUERTO_SALIDA = 3128
USUARIO_PROXY = "bms"
LOCAL = "127.0.0.1"
# El lector sale por el proxy que diga esta variable (la lee el cliente HTTP del SDK);
# la credencial de la pasada va dentro (http://bms:CREDENCIAL@127.0.0.1:3128).
VARIABLE_PROXY = "HTTPS_PROXY"

# Lo que lleva cada carpeta de la raiz. El codigo no se puede escribir (lo comprueba la
# comprobacion de aislamiento); los datos y el buzon si.
CODIGO = ("app", "lib", "runtime", "windows")
ESCRIBIBLES = ("datos", "buzon")

# El Python de cada papel (windows/fijado.json dice cual se baja, y su sha256).
VERSION_PYTHON = (3, 13)
_ETIQUETA = f"{VERSION_PYTHON[0]}{VERSION_PYTHON[1]}"
DLL_PYTHON = f"python{_ETIQUETA}.dll"
# El ._pth va junto a python313.dll (Python lo busca alli antes que junto al programa).
# Con el, Python no mira PYTHONPATH, PYTHONHOME ni el registro, entra en modo aislado, no
# importa site (sin site no hay site-packages ni la carpeta del usuario) y su sys.path es
# exactamente esto, relativo a la carpeta del python.exe de cada papel: la biblioteca
# (Lib, en .py), sus modulos compilados (DLLs, los .pyd), las dependencias y el codigo de
# la app. Sin "." (la carpeta del programa): en el paquete de NuGet alli no hay nada que
# importar, y una ruta menos es un sitio menos donde dejar un modulo.
FICHERO_PTH = f"python{_ETIQUETA}._pth"
RUTAS_PTH = ("Lib", "DLLs", r"..\..\lib", r"..\..\app\src")

# Lo que el instalador saca del paquete de NuGet para cada papel: la carpeta tools/ (lo
# demas es del propio NuGet: el nuspec, su firma, los props de MSBuild) sin lo que no es
# el interprete. Fuera pythonw.exe (otro programa sin reglas en la misma carpeta), pip con
# sus lanzadores .exe (Lib/site-packages), ensurepip, venv (con venvlauncher.exe, otro
# programa) y lo que solo sirve para compilar extensiones (include, libs). Es lo mismo que
# deja fuera el propio paquete al copiar el runtime (build/native/python.props), salvo
# vcruntime140*.dll, que se queda: Windows no siempre lo trae. Queda un solo programa,
# python.exe; el instalador lo comprueba.
CARPETA_DEL_PAQUETE = "tools/"
FUERA_DEL_RUNTIME = ("pythonw.exe", "include/", "libs/", "Lib/site-packages/", "Lib/ensurepip/",
                     "Lib/venv/")
# Lo que tiene que haber en cada runtime/<papel> despues de abrir el paquete.
NECESARIOS_DEL_RUNTIME = ("python.exe", DLL_PYTHON, "Lib/os.py", "DLLs/_socket.pyd",
                          "DLLs/_sqlite3.pyd", "DLLs/_ssl.pyd")

# Los sucesos de auditoria con los que Python arranca otro proceso (la lista de la
# documentacion de sys.audit). Son nombres de sucesos, no llamadas: aqui no se lanza nada.
SUCESOS_DE_PROCESO = frozenset({
    "subprocess.Popen", "os.system", "os.startfile", "os.exec", "os.spawn", "os.posix_spawn",
    "os.fork", "os.forkpty", "pty.spawn", "_winapi.CreateProcess", "webbrowser.open"})


class InstalacionNoValida(RuntimeError):
    """Hay un instalacion.json pero no se entiende: no se sigue como si no hubiera."""


class LecturaNoAislada(RuntimeError):
    """Una llamada a la API que la instalacion nativa no deja hacer."""


@dataclass(frozen=True)
class Instalacion:
    raiz: Path
    rol: str
    puerto_consola: int = PUERTO_CONSOLA
    puerto_salida: int = PUERTO_SALIDA

    @property
    def datos(self) -> Path:
        return self.raiz / "datos"

    @property
    def buzon(self) -> Path:
        return self.raiz / "buzon"

    @property
    def resultado_aislamiento(self) -> Path:
        return self.datos / FICHERO_AISLAMIENTO

    @property
    def fichero_clave(self) -> Path:
        from .secretos import FICHERO

        return self.datos / "secretos" / FICHERO

    def ejecutable(self, rol: str) -> Path:
        return self.raiz / "runtime" / rol / "python.exe"

    def carpetas_a_probar(self) -> dict[str, Path]:
        """Las carpetas que la comprobacion intenta escribir: el codigo (no tiene que poder),
        la carpeta del propio interprete (un DLL dejado alli lo cargaria el siguiente
        arranque), la raiz (alli esta instalacion.json, del que dependen las puertas) y
        windows (los scripts que arrancan la salida con su credencial y corren elevados al
        desinstalar), y los datos y el buzon (tienen que poder)."""
        carpetas = {nombre: self.raiz / nombre for nombre in ("app", "lib", "windows")}
        carpetas["raiz"] = self.raiz
        carpetas[f"runtime/{self.rol}"] = self.raiz / "runtime" / self.rol
        carpetas.update({nombre: self.raiz / nombre for nombre in ESCRIBIBLES})
        return carpetas


def detectar(ejecutable: str | Path | None = None) -> Instalacion | None:
    """La instalacion del interprete que corre, o None si no es uno de la instalacion nativa.

    El interprete esta en <raiz>/runtime/<papel>/python.exe y la raiz tiene
    instalacion.json. Un instalacion.json que no se entiende es un error, no un "no hay":
    fuera de la instalacion las puertas de este modulo no se aplican. Por lo mismo, un
    interprete de la instalacion (en runtime/<papel>, con un python3XY._pth al lado: el de
    esta version o el de otra) sin instalacion.json tambien es un error: que falte el
    fichero no apaga las puertas.
    """
    programa = Path(ejecutable if ejecutable is not None else sys.executable)
    carpeta = programa.parent
    rol = carpeta.name.lower()
    if carpeta.parent.name.lower() != "runtime" or rol not in ROLES:
        return None
    raiz = carpeta.parent.parent
    fichero = raiz / FICHERO_INSTALACION
    if not fichero.is_file():
        if _tiene_pth(carpeta):
            raise InstalacionNoValida(f"falta {fichero}: este programa es el de {rol} de la "
                                      "instalacion nativa; vuelve a instalar con instalar.bat")
        return None
    try:
        datos = json.loads(fichero.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise InstalacionNoValida(f"{fichero} no se entiende ({exc}): vuelve a instalar") from None
    if not isinstance(datos, dict) or datos.get("version") != VERSION_INSTALACION:
        raise InstalacionNoValida(f"{fichero} no es de esta version: vuelve a instalar")
    try:
        consola = int(datos.get("puerto_consola", PUERTO_CONSOLA))
        salida = int(datos.get("puerto_salida", PUERTO_SALIDA))
    except (TypeError, ValueError):
        raise InstalacionNoValida(f"{fichero}: los puertos no son numeros") from None
    if not (1024 <= consola <= 65535 and 1024 <= salida <= 65535) or consola == salida:
        raise InstalacionNoValida(f"{fichero}: los puertos no valen")
    return Instalacion(raiz, rol, consola, salida)


def _tiene_pth(carpeta: Path) -> bool:
    """Si la carpeta tiene el ._pth de un Python de la instalacion, de esta version o de otra
    (una instalacion de antes de cambiar de version tampoco apaga las puertas)."""
    try:
        return any(p.is_file() for p in carpeta.glob("python3*._pth"))
    except OSError:
        return False


def instalacion_actual() -> Instalacion | None:
    """La del interprete que corre (los tests la sustituyen)."""
    return detectar()


def huella_sesion(credencial: str) -> str:
    """La huella de la credencial del proxy de una pasada: lo que ata la comprobacion de
    aislamiento a esa pasada sin apuntar la credencial."""
    return hashlib.sha256(credencial.encode("utf-8")).hexdigest()


def leer_proxy(texto: str | None, puerto: int | None = None) -> tuple[tuple[str, int], str]:
    """El proxy de la salida y la credencial de la pasada, de http://bms:CREDENCIAL@127.0.0.1:P.

    Solo 127.0.0.1: el proxy de la instalacion nativa escucha ahi y en ningun otro sitio.
    ValueError si no es eso; el mensaje no lleva la credencial.
    """
    if not texto:
        raise ValueError(f"falta {VARIABLE_PROXY}: la lectura sale por el proxy de la salida")
    partes = urlsplit(texto.strip())
    try:
        puerto_url = partes.port
    except ValueError:
        puerto_url = None
    if partes.scheme != "http" or partes.hostname != LOCAL or puerto_url is None:
        raise ValueError(f"{VARIABLE_PROXY} tiene que ser el proxy de la salida, "
                         f"http://{USUARIO_PROXY}:...@{LOCAL}:PUERTO")
    if puerto is not None and puerto_url != puerto:
        raise ValueError(f"{VARIABLE_PROXY} no es el puerto de la salida ({puerto})")
    if partes.username != USUARIO_PROXY or not partes.password:
        raise ValueError(f"{VARIABLE_PROXY} no lleva la credencial de esta pasada")
    return (LOCAL, puerto_url), partes.password


def proxy_del_entorno(puerto: int | None = None, entorno: dict[str, str] | None = None
                      ) -> tuple[tuple[str, int], str]:
    texto = os.environ.get(VARIABLE_PROXY) if entorno is None else entorno.get(VARIABLE_PROXY)
    return leer_proxy(texto, puerto)


def exigir_lectura(instalacion: Instalacion, entorno: dict[str, str] | None = None,
                   ahora: datetime | None = None) -> None:
    """Deja seguir una llamada a la API solo si la hace el lector de una pasada comprobada.

    LecturaNoAislada si no: otro papel, sin el proxy de la pasada, o sin una comprobacion de
    aislamiento del lector y de la salida que haya salido bien en esa misma pasada.
    """
    if instalacion.rol != "lector":
        raise LecturaNoAislada(f"este programa es el de {instalacion.rol}, y aqui no se habla con "
                               "la API: lo hace el lector, con leer-facturas.bat")
    try:
        _proxy, credencial = proxy_del_entorno(instalacion.puerto_salida, entorno)
    except ValueError as exc:
        raise LecturaNoAislada(f"{exc}. Lee las facturas con leer-facturas.bat") from None
    motivo = motivo_para_no_leer(instalacion.resultado_aislamiento, huella_sesion(credencial),
                                 ahora)
    if motivo:
        raise LecturaNoAislada(f"no se lee nada ni se paga nada: {motivo}. leer-facturas.bat "
                               "arranca la salida y comprueba el aislamiento antes de leer")


def exigir_lectura_si_nativa() -> None:
    """La puerta, si se corre en la instalacion nativa; fuera de ella no hace nada."""
    instalacion = instalacion_actual()
    if instalacion is not None:
        exigir_lectura(instalacion)


def clave_del_lector(instalacion: Instalacion, protector=None,
                     fichero: str | Path | None = None) -> str:
    """La clave de la API, descifrada, solo para el lector. `fichero`: otra que la de la
    instalacion (clave comprobar --fichero); la regla del lector es la misma."""
    from .config import ClaveNoValida
    from .secretos import leer_clave

    if instalacion.rol != "lector":
        raise ClaveNoValida(f"la clave de la API solo la descifra el lector; este programa es el "
                            f"de {instalacion.rol}")
    return leer_clave(instalacion.fichero_clave if fichero is None else Path(fichero),
                      protector)


def _sin_procesos(suceso: str, _argumentos: tuple) -> None:
    if suceso in SUCESOS_DE_PROCESO:
        # PermissionError es un OSError: quien prueba un programa que puede no estar (platform
        # con `ver`) lo toma como que no esta, y sigue.
        raise PermissionError(f"la instalacion nativa no arranca otros programas ({suceso})")


_prohibidos = False


def prohibir_procesos() -> None:
    """Desde ahora, ningun codigo de Python de este proceso arranca otro programa. Para
    siempre: un gancho de auditoria no se puede quitar. Solo en la instalacion nativa (en
    los tests romperia lo que si lanza procesos, como pytest con pwsh)."""
    global _prohibidos
    if not _prohibidos:
        sys.addaudithook(_sin_procesos)
        _prohibidos = True


def prohibir_procesos_si_nativa() -> None:
    """El gancho, si el interprete que corre es uno de la instalacion. Mira el interprete de
    verdad (detectar), no instalacion_actual, que los tests sustituyen."""
    if detectar() is not None:
        prohibir_procesos()


def contenido_pth() -> str:
    """El python313._pth de cada papel, con fin de linea de Windows."""
    return "\r\n".join(RUTAS_PTH) + "\r\n"


class PaqueteNoValido(ValueError):
    """El paquete de Python trae algo que no se puede abrir sin salirse de la carpeta."""


def destino_en_runtime(entrada: str) -> str | None:
    """Donde va, dentro de runtime/<papel>, una entrada del paquete de NuGet (con "/"), o
    None si no va. Lo mismo que hace Destino-En-Runtime en windows/instalar.ps1: los tests
    comparan los dos con el mismo paquete.

    Solo lo de tools/, sin FUERA_DEL_RUNTIME; la comparacion no distingue mayusculas, como
    Windows. Una entrada con "..", con "\\", con ":" o con una ruta absoluta no es de un
    paquete bueno (el sha256 fijado ya lo impide; esto es por si acaso): PaqueteNoValido,
    y no se abre nada.
    """
    partes = entrada.split("/")
    if (entrada.startswith("/") or "\\" in entrada or ":" in entrada
            or any(p in ("..", ".") for p in partes) or "" in partes[:-1]):
        raise PaqueteNoValido(f"el paquete de Python trae una ruta que no vale: {entrada!r}")
    if not entrada.lower().startswith(CARPETA_DEL_PAQUETE) or entrada.endswith("/"):
        return None
    resto = entrada[len(CARPETA_DEL_PAQUETE):]
    if not resto:
        return None
    for fuera in FUERA_DEL_RUNTIME:
        if fuera.endswith("/") and resto.lower().startswith(fuera.lower()):
            return None
        if not fuera.endswith("/") and resto.lower() == fuera.lower():
            return None
    return resto
