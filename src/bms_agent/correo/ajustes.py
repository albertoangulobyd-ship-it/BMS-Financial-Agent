"""Los ajustes del correo de facturas (paso 18, diseno §2.4), version 1.

En Docker viven en docker\\secretos\\correo\\correo_ajustes.json: el contenedor `correo` los ve
como el secreto de Docker `correo_ajustes`, y `orden` los escribe (`correo ajustes fijar`, y
las ordenes de `correo certificado`) con esa carpeta montada solo para esa orden. No son un
secreto, pero llevan datos de la empresa (el id del inquilino y el de la aplicacion de Entra)
y datos personales (las direcciones de los buzones): nunca entran en config/, en un registro
ni en un mensaje de error (los errores dicen que campo esta mal, no lo que pone).

    {"version": 1, "inquilino": "<GUID>", "aplicacion": "<GUID>",
     "buzon": "facturen@contoso.example", "buzon_control": "bms-control@contoso.example",
     "desde": "AAAA-MM-DD",
     "certificado": {"huella_sha256": "<hex>", "caduca_en": "AAAA-MM-DDTHH:MM:SSZ"} | null,
     "siguiente": {...} | null, "anterior": {...} | null,
     "limites": {"pdf_dia": 150, "mib_dia": 750}}

Lo del certificado (su huella y su caducidad) no se escribe a mano: lo pone al dia
certificado.py con lo que hay en la carpeta cada vez que una orden local la cambia.

Se validan con rigor al leerlos y al fijarlos, y se rechaza lo que sobra: el inquilino va en
la URL del token y los buzones en las de Graph, asi que solo valen un GUID y una direccion de
un juego de caracteres corto (nada que en una URL cambie de sentido: ni `/`, `?`, `#`, `%`
ni espacios).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

VERSION = 1
# El nombre del fichero en la carpeta de los secretos del correo (docker\secretos\correo).
FICHERO = "correo_ajustes.json"
MAX_BYTES = 16 * 1024
# Lo que no se trae la primera vez: por defecto, lo anterior a hoy menos 30 dias.
DIAS_DESDE = 30
# Los topes por dia de lo que el correo baja (§3.5), y hasta donde se pueden subir.
PDF_DIA = 150
MIB_DIA = 750
TOPE_PDF_DIA = 1000
TOPE_MIB_DIA = 4096
MAX_DIRECCION = 320

CLAVES = ("version", "inquilino", "aplicacion", "buzon", "buzon_control", "desde",
          "certificado", "siguiente", "anterior", "limites")
CERTIFICADOS = ("certificado", "siguiente", "anterior")

_GUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# La parte de antes de la @: letras, cifras y . _ + - (sin dos puntos seguidos ni en los
# extremos). Lo que Exchange admite de mas (comillas, apostrofos...) no vale aqui.
_LOCAL = re.compile(r"[a-z0-9_+-]+(?:\.[a-z0-9_+-]+)*")
_ETIQUETA = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_INSTANTE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_HUELLA = re.compile(r"[0-9a-f]{64}")


class AjustesNoValidos(ValueError):
    """Los ajustes no se pueden usar. El mensaje dice que campo, nunca su valor."""


class SinAjustes(AjustesNoValidos):
    """Aun no hay ajustes (correo-configurar.bat, fase 2)."""


@dataclass(frozen=True)
class Huella:
    """Lo publico de un certificado que guardan los ajustes."""

    huella_sha256: str
    caduca_en: datetime


@dataclass(frozen=True)
class Limites:
    pdf_dia: int = PDF_DIA
    mib_dia: int = MIB_DIA


@dataclass(frozen=True)
class Ajustes:
    inquilino: str
    aplicacion: str
    buzon: str
    buzon_control: str
    desde: date
    certificado: Huella | None = None
    siguiente: Huella | None = None
    anterior: Huella | None = None
    limites: Limites = field(default_factory=Limites)


# ------------------------------------------------------------------ cada campo

def guid(valor: object, campo: str) -> str:
    """Un GUID (el id del inquilino o el de la aplicacion), en minusculas."""
    if isinstance(valor, str) and valor.strip().isascii():
        texto = valor.strip().lower()
        if _GUID.fullmatch(texto):
            return texto
    raise AjustesNoValidos(f"{campo}: no es un id de Entra (un GUID como "
                           "00000000-0000-0000-0000-000000000000)")


def direccion(valor: object, campo: str) -> str:
    """Una direccion de correo, en minusculas, con el juego de caracteres corto de arriba."""
    if isinstance(valor, str) and valor.strip().isascii():
        texto = valor.strip().lower()
        local, arroba, dominio = texto.rpartition("@")
        etiquetas = dominio.split(".")
        if (arroba and len(texto) <= MAX_DIRECCION and len(local) <= 64
                and _LOCAL.fullmatch(local) and len(dominio) <= 253 and len(etiquetas) >= 2
                and all(_ETIQUETA.fullmatch(e) for e in etiquetas)
                and etiquetas[-1].isalpha() and len(etiquetas[-1]) >= 2):
            return texto
    raise AjustesNoValidos(f"{campo}: no es una direccion de correo que se pueda usar (solo "
                           "letras, cifras y . _ + - antes de la @, un dominio con punto, y "
                           f"como mucho {MAX_DIRECCION} caracteres)")


def fecha(valor: object, campo: str) -> date:
    if isinstance(valor, str) and _FECHA.fullmatch(valor):
        try:
            return date.fromisoformat(valor)
        except ValueError:
            pass
    raise AjustesNoValidos(f"{campo}: no es una fecha AAAA-MM-DD")


def instante(valor: object, campo: str) -> datetime:
    """Un instante en UTC escrito AAAA-MM-DDTHH:MM:SSZ."""
    if isinstance(valor, str) and _INSTANTE.fullmatch(valor):
        try:
            return datetime.strptime(valor, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    raise AjustesNoValidos(f"{campo}: no es un instante AAAA-MM-DDTHH:MM:SSZ")


def texto_instante(momento: datetime) -> str:
    return momento.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _entero(valor: object, campo: str, tope: int) -> int:
    if type(valor) is int and 1 <= valor <= tope:
        return valor
    raise AjustesNoValidos(f"{campo}: tiene que ser un numero entero de 1 a {tope}")


def _huella(valor: object, campo: str) -> Huella | None:
    if valor is None:
        return None
    if not isinstance(valor, dict) or set(valor) != {"huella_sha256", "caduca_en"}:
        raise AjustesNoValidos(f"{campo}: tiene que llevar huella_sha256 y caduca_en, y nada "
                               "mas")
    huella = valor["huella_sha256"]
    if not isinstance(huella, str) or not _HUELLA.fullmatch(huella):
        raise AjustesNoValidos(f"{campo}.huella_sha256: no es un sha256 en hexadecimal")
    return Huella(huella, instante(valor["caduca_en"], f"{campo}.caduca_en"))


def _limites(valor: object) -> Limites:
    if not isinstance(valor, dict) or set(valor) != {"pdf_dia", "mib_dia"}:
        raise AjustesNoValidos("limites: tiene que llevar pdf_dia y mib_dia, y nada mas")
    return Limites(_entero(valor["pdf_dia"], "limites.pdf_dia", TOPE_PDF_DIA),
                   _entero(valor["mib_dia"], "limites.mib_dia", TOPE_MIB_DIA))


def _comprobar(ajustes: Ajustes) -> Ajustes:
    """Lo que tiene que cumplir el conjunto: dos buzones distintos del mismo dominio."""
    if ajustes.buzon == ajustes.buzon_control:
        raise AjustesNoValidos("buzon_control: tiene que ser otro buzon que el de las facturas "
                               "(uno que la aplicacion no pueda leer)")
    if ajustes.buzon.rpartition("@")[2] != ajustes.buzon_control.rpartition("@")[2]:
        raise AjustesNoValidos("buzon_control: tiene que ser del mismo dominio que el buzon de "
                               "las facturas")
    return ajustes


# ------------------------------------------------------------------ el fichero

def desde_datos(datos: object) -> Ajustes:
    """Los ajustes de lo leido del fichero, comprobado todo."""
    if not isinstance(datos, dict):
        raise AjustesNoValidos("no son un objeto JSON")
    faltan = [c for c in CLAVES if c not in datos]
    if faltan:
        raise AjustesNoValidos(f"les falta {', '.join(faltan)}")
    if len(datos) != len(CLAVES):
        raise AjustesNoValidos(f"llevan {len(datos) - len(CLAVES)} claves que no son de los "
                               "ajustes")
    if type(datos["version"]) is not int or datos["version"] != VERSION:
        raise AjustesNoValidos(f"no son de la version {VERSION}")
    return _comprobar(Ajustes(
        inquilino=guid(datos["inquilino"], "inquilino"),
        aplicacion=guid(datos["aplicacion"], "aplicacion"),
        buzon=direccion(datos["buzon"], "buzon"),
        buzon_control=direccion(datos["buzon_control"], "buzon_control"),
        desde=fecha(datos["desde"], "desde"),
        certificado=_huella(datos["certificado"], "certificado"),
        siguiente=_huella(datos["siguiente"], "siguiente"),
        anterior=_huella(datos["anterior"], "anterior"),
        limites=_limites(datos["limites"])))


def como_datos(ajustes: Ajustes) -> dict:
    def huella(h: Huella | None) -> dict | None:
        return None if h is None else {"huella_sha256": h.huella_sha256,
                                       "caduca_en": texto_instante(h.caduca_en)}

    return {"version": VERSION, "inquilino": ajustes.inquilino,
            "aplicacion": ajustes.aplicacion, "buzon": ajustes.buzon,
            "buzon_control": ajustes.buzon_control, "desde": ajustes.desde.isoformat(),
            "certificado": huella(ajustes.certificado), "siguiente": huella(ajustes.siguiente),
            "anterior": huella(ajustes.anterior),
            "limites": {"pdf_dia": ajustes.limites.pdf_dia,
                        "mib_dia": ajustes.limites.mib_dia}}


def _sin_repetidas(pares: list[tuple[str, object]]) -> dict:
    datos = dict(pares)
    if len(datos) != len(pares):
        raise ValueError("clave repetida")
    return datos


def _sin_constantes(_nombre: str) -> object:
    raise ValueError("NaN o Infinity")


def leer(ruta: str | Path) -> Ajustes:
    """Los ajustes del fichero. SinAjustes si no existe; AjustesNoValidos si no valen."""
    ruta = Path(ruta)
    try:
        with open(ruta, "rb") as fichero:
            contenido = fichero.read(MAX_BYTES + 1)
    except FileNotFoundError:
        raise SinAjustes(f"no hay ajustes del correo en {ruta}") from None
    except OSError as exc:
        raise AjustesNoValidos(f"no se pueden leer los ajustes del correo de {ruta}: "
                               f"{exc.strerror or type(exc).__name__}") from None
    if len(contenido) > MAX_BYTES:
        raise AjustesNoValidos(f"{ruta}: mas de {MAX_BYTES} bytes, no son unos ajustes")
    datos = _json(contenido)
    if datos is None:
        raise AjustesNoValidos(f"{ruta}: no es JSON en UTF-8 (o lleva claves repetidas)")
    return desde_datos(datos)


def _json(contenido: bytes) -> object | None:
    try:
        return json.loads(contenido.decode("utf-8"), object_pairs_hook=_sin_repetidas,
                          parse_constant=_sin_constantes)
    except (ValueError, RecursionError):  # tambien UnicodeDecodeError y JSONDecodeError
        return None


def escribir_de_una_vez(ruta: Path, contenido: bytes) -> None:
    """Escribe `ruta` entero o nada: aparte (0600, en la misma carpeta) y cambia de nombre."""
    descriptor, temporal = tempfile.mkstemp(prefix=".correo-", suffix=".tmp", dir=ruta.parent)
    try:
        with os.fdopen(descriptor, "wb") as fichero:
            fichero.write(contenido)
            fichero.flush()
            os.fsync(fichero.fileno())
        os.replace(temporal, ruta)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporal)
        raise


def escribir(ruta: str | Path, ajustes: Ajustes) -> None:
    texto = json.dumps(como_datos(_comprobar(ajustes)), indent=2, ensure_ascii=True) + "\n"
    escribir_de_una_vez(Path(ruta), texto.encode("ascii"))


# ------------------------------------------------------------------ fijarlos

def fijar(actuales: Ajustes | None, *, hoy: date, inquilino: str | None = None,
          aplicacion: str | None = None, buzon: str | None = None,
          buzon_control: str | None = None, desde: str | None = None,
          pdf_dia: int | None = None, mib_dia: int | None = None) -> Ajustes:
    """Los ajustes con lo que se da cambiado; lo que no se da queda como estaba. La primera
    vez hacen falta los cuatro datos del informatico (§2.1, paso 7). `desde`, por defecto
    hoy menos 30 dias, no puede ser posterior a hoy. Lo del certificado no se toca aqui."""
    if actuales is None:
        faltan = [nombre for nombre, valor in (
            ("--inquilino", inquilino), ("--aplicacion", aplicacion), ("--buzon", buzon),
            ("--buzon-control", buzon_control)) if valor is None]
        if faltan:
            raise AjustesNoValidos(f"aun no hay ajustes: la primera vez hacen falta "
                                   f"{', '.join(faltan)}")
        base = Ajustes(inquilino="", aplicacion="", buzon="", buzon_control="",
                       desde=hoy - timedelta(days=DIAS_DESDE))
    else:
        base = actuales
    cambios: dict = {}
    if inquilino is not None:
        cambios["inquilino"] = guid(inquilino, "inquilino")
    if aplicacion is not None:
        cambios["aplicacion"] = guid(aplicacion, "aplicacion")
    if buzon is not None:
        cambios["buzon"] = direccion(buzon, "buzon")
    if buzon_control is not None:
        cambios["buzon_control"] = direccion(buzon_control, "buzon_control")
    if desde is not None:
        cambios["desde"] = fecha(desde, "desde")
        if cambios["desde"] > hoy:
            raise AjustesNoValidos("desde: no puede ser posterior a hoy")
    if pdf_dia is not None or mib_dia is not None:
        cambios["limites"] = Limites(
            _entero(base.limites.pdf_dia if pdf_dia is None else pdf_dia, "limites.pdf_dia",
                    TOPE_PDF_DIA),
            _entero(base.limites.mib_dia if mib_dia is None else mib_dia, "limites.mib_dia",
                    TOPE_MIB_DIA))
    return _comprobar(replace(base, **cambios))


def con_certificados(ajustes: Ajustes, *, certificado: Huella | None,
                     siguiente: Huella | None, anterior: Huella | None) -> Ajustes:
    return replace(ajustes, certificado=certificado, siguiente=siguiente, anterior=anterior)
