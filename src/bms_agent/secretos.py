"""La clave de la API cifrada con DPAPI, en la instalacion nativa de Windows (paso 14).

En Docker la clave es un secreto que solo ve el contenedor del lector, pero en el
disco de Windows es un fichero de texto (docker/secretos). Aqui no hay fichero de
texto: la clave se cifra con DPAPI (CryptProtectData), que la ata al usuario de
Windows que la guardo y a este ordenador. El fichero que queda en
datos/secretos/clave-api.dpapi no sirve en otro ordenador, a otro usuario ni en una
copia de seguridad robada, y no se lee abriendolo.

Lo que DPAPI no hace, y la guia lo dice: cualquier programa que corra con el mismo
usuario de Windows puede pedir que se descifre. Por eso, ademas, el codigo solo la
descifra en el lector (nativo.clave_del_lector), y para separarla de verdad esta el
usuario de Windows dedicado (docs/instalacion-nativa.md, "Un usuario aparte").

- Ambito del usuario actual (sin CRYPTPROTECT_LOCAL_MACHINE), sin ventanas
  (CRYPTPROTECT_UI_FORBIDDEN: nada puede pedirle nada a nadie) y con una entropia
  propia: otro programa que descifre a ciegas los blobs de DPAPI del usuario no
  descifra este sin saberla.
- La clave nunca se escribe en claro, ni en el registro ni en un mensaje de error.
- Fuera de Windows no hay DPAPI: se dice (`SinDPAPI`), no se guarda la clave de otra
  manera. Los tests usan un protector falso inyectado.

Es el unico modulo que usa ctypes, y solo para crypt32 y LocalFree (un test lo vigila:
nada de lanzar procesos).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Protocol

from .config import ClaveNoValida, parece_una_clave

CRYPTPROTECT_UI_FORBIDDEN = 0x1
ENTROPIA = b"BMS Finanzas - clave de la API - v1"
DESCRIPCION = "BMS Finanzas: clave de la API"
# Delante del blob, para reconocer el fichero sin intentar descifrar cualquier cosa.
CABECERA = b"BMS-DPAPI-1\n"
FICHERO = "clave-api.dpapi"


class SinDPAPI(ClaveNoValida):
    """No hay DPAPI: no es Windows."""


class Protector(Protocol):
    def proteger(self, datos: bytes, entropia: bytes) -> bytes: ...

    def desproteger(self, blob: bytes, entropia: bytes) -> bytes: ...


class DPAPI:
    """CryptProtectData y CryptUnprotectData de crypt32, por ctypes."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise SinDPAPI("la clave cifrada con DPAPI solo existe en Windows (la instalacion "
                           "nativa); en Docker la clave va en docker/secretos")
        import ctypes
        from ctypes import wintypes

        class Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        self._ctypes = ctypes
        self._Blob = Blob
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._proteger = crypt32.CryptProtectData
        self._proteger.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.POINTER(Blob),
                                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                   ctypes.POINTER(Blob)]
        self._proteger.restype = wintypes.BOOL
        self._desproteger = crypt32.CryptUnprotectData
        self._desproteger.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p,
                                      ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                                      wintypes.DWORD, ctypes.POINTER(Blob)]
        self._desproteger.restype = wintypes.BOOL
        self._liberar = kernel32.LocalFree
        self._liberar.argtypes = [ctypes.c_void_p]
        self._liberar.restype = ctypes.c_void_p

    def _blob(self, datos: bytes):
        ctypes = self._ctypes
        memoria = ctypes.create_string_buffer(datos, len(datos))
        blob = self._Blob(len(datos), ctypes.cast(memoria, ctypes.POINTER(ctypes.c_char)))
        return blob, memoria

    def _llamar(self, funcion, datos: bytes, entropia: bytes, descripcion: str | None) -> bytes:
        ctypes = self._ctypes
        entrada, _m1 = self._blob(datos)
        extra, _m2 = self._blob(entropia)
        salida = self._Blob()
        ok = funcion(ctypes.byref(entrada), descripcion, ctypes.byref(extra), None, None,
                     CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(salida))
        if not ok:
            raise OSError(ctypes.get_last_error(), "DPAPI no ha podido con la clave")
        try:
            return ctypes.string_at(salida.pbData, salida.cbData)
        finally:
            self._liberar(salida.pbData)

    def proteger(self, datos: bytes, entropia: bytes) -> bytes:
        return self._llamar(self._proteger, datos, entropia, DESCRIPCION)

    def desproteger(self, blob: bytes, entropia: bytes) -> bytes:
        return self._llamar(self._desproteger, blob, entropia, None)


def protector_del_sistema() -> Protector:
    """El de verdad (DPAPI). Los tests lo sustituyen por uno falso."""
    return DPAPI()


def guardar_clave(clave: str, ruta: str | Path, protector: Protector | None = None) -> Path:
    """Cifra la clave y la deja en `ruta`, en su sitio de una vez (se escribe aparte y se
    cambia de nombre: nunca queda media). ClaveNoValida si no parece una clave; el mensaje no
    la lleva."""
    clave = clave.strip()
    if not parece_una_clave(clave):
        raise ClaveNoValida("eso no parece una clave de la API de Anthropic (empieza por sk-ant- "
                            "y va en una sola linea)")
    protector = protector or protector_del_sistema()
    blob = protector.proteger(clave.encode("utf-8"), ENTROPIA)
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporal = tempfile.mkstemp(prefix=".clave-", dir=ruta.parent)
    with os.fdopen(descriptor, "wb") as fichero:
        fichero.write(CABECERA + blob)
    os.replace(temporal, ruta)
    return ruta


def leer_clave(ruta: str | Path, protector: Protector | None = None) -> str:
    """La clave descifrada. ClaveNoValida, sin la clave en el mensaje, si no hay, si el fichero
    no es de aqui o si DPAPI no la descifra (otro usuario de Windows u otro ordenador)."""
    ruta = Path(ruta)
    try:
        contenido = ruta.read_bytes()
    except FileNotFoundError:
        raise ClaveNoValida("no hay ninguna clave guardada: guardala con clave.bat") from None
    except OSError as exc:
        raise ClaveNoValida(f"no se puede leer {ruta}: {exc.strerror or exc}") from None
    if not contenido.startswith(CABECERA) or len(contenido) == len(CABECERA):
        raise ClaveNoValida(f"{ruta} no es una clave guardada por clave.bat: vuelve a guardarla")
    protector = protector or protector_del_sistema()
    try:
        claro = protector.desproteger(contenido[len(CABECERA):], ENTROPIA)
    except OSError:
        raise ClaveNoValida("la clave guardada no se puede descifrar: se guardo con otro usuario "
                            "de Windows o en otro ordenador. Vuelve a guardarla con clave.bat"
                            ) from None
    try:
        clave = claro.decode("utf-8")
    except UnicodeDecodeError:
        raise ClaveNoValida("la clave guardada no es texto: vuelve a guardarla con clave.bat"
                            ) from None
    if not parece_una_clave(clave):
        raise ClaveNoValida("lo guardado no parece una clave de la API: vuelve a guardarla con "
                            "clave.bat")
    return clave


def borrar_clave(ruta: str | Path) -> bool:
    """Borra la clave guardada. False si no habia."""
    try:
        Path(ruta).unlink()
    except FileNotFoundError:
        return False
    return True
