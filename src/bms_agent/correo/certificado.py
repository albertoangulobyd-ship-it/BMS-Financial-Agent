"""El certificado del correo de facturas (paso 18, diseno §2.2 y §2.4), en la variante Docker.

El correo pide su token a Microsoft con una asercion firmada (client credentials con
certificado, sin msal). La clave privada, RSA de 3072 bits, se genera aqui, en `orden` (sin
red), y no sale de este ordenador: lo unico que se sube a la aplicacion de Entra es la parte
publica, el .cer. El certificado es autofirmado y vale 24 meses.

Los ficheros, todos en una carpeta (en Docker, docker\\secretos\\correo, que solo se monta en
`orden` y solo para estas ordenes; el contenedor `correo` solo ve el .pem actual, como el
secreto de Docker `correo_certificado`):

- correo_certificado.pem: la clave privada (PKCS#8, PEM, sin cifrar, como la clave de la API
  en docker\\secretos) seguida de su certificado; es lo que usa el correo;
- correo_certificado.cer: el certificado (PEM), para subirlo a Entra;
- correo_certificado-siguiente.pem/.cer: el de la renovacion, hasta que se activa;
- correo_certificado-anterior.pem/.cer: el de antes de activar, hasta que se comprueba el
  nuevo (y se borra) o se vuelve a el.

El .pem es lo que cuenta: el .cer de cada uno se rehace de su .pem en cada orden que cambia la
carpeta, y los ajustes de la misma carpeta (ajustes.py), si los hay, se ponen al dia con la
huella y la caducidad de cada uno.

Lo que nunca pasa: que la clave salga de este modulo (de el solo sale la firma de la
asercion), que se escriba en un registro, o que un mensaje o una excepcion lleve algo de ella.
Los errores de cryptography no se encadenan: cada fallo es un CertificadoNoValido con un texto
propio, lanzado fuera del `except`.
"""

from __future__ import annotations

import base64
import calendar
import contextlib
import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

from . import ajustes as _ajustes

BITS = 3072
EXPONENTE = 65537
MESES = 24
# Sin datos de la empresa: el nombre solo sirve para reconocerlo en Entra.
NOMBRE_COMUN = "BMS lector de facturas"
# Vale desde un poco antes de crearlo, por si el reloj de Microsoft va algo por detras.
MARGEN_INICIO = timedelta(minutes=5)
MAX_PEM = 8 * 1024
VIDA_ASERCION = timedelta(minutes=5)
AUDIENCIA = "https://login.microsoftonline.com/{inquilino}/oauth2/v2.0/token"

BASE = "correo_certificado"
ACTUAL, SIGUIENTE, ANTERIOR = "actual", "siguiente", "anterior"
CUALES = (ACTUAL, SIGUIENTE, ANTERIOR)
_SUFIJO = {ACTUAL: "", SIGUIENTE: "-siguiente", ANTERIOR: "-anterior"}
# Los ajustes llaman "certificado" al actual.
_EN_LOS_AJUSTES = {ACTUAL: "certificado", SIGUIENTE: "siguiente", ANTERIOR: "anterior"}

_BLOQUE = re.compile(rb"-----BEGIN ([A-Z0-9 ]{1,40})-----\r?\n([A-Za-z0-9+/=\r\n]+?)"
                     rb"-----END \1-----")


class CertificadoNoValido(ValueError):
    """El certificado no se puede usar. El mensaje nunca lleva nada de la clave."""


class SinCertificado(CertificadoNoValido):
    """Aun no hay certificado (correo-configurar.bat, fase 1)."""


class CertificadoCaducado(CertificadoNoValido):
    """El certificado ya no vale (o aun no: el reloj)."""


class NoSeHace(Exception):
    """La orden no se hace, sin cambiar nada, por lo que dice el mensaje."""


@dataclass(frozen=True)
class Datos:
    """Lo publico de un certificado."""

    huella_sha256: str
    huella_sha1: str            # la que ensena Entra ("Thumbprint"), solo para compararla
    emitido_en: datetime
    caduca_en: datetime

    def huella(self) -> _ajustes.Huella:
        return _ajustes.Huella(self.huella_sha256, self.caduca_en)

    def dias(self, ahora: datetime | None = None) -> int:
        """Los dias que le quedan (negativo si ya caduco)."""
        return (self.caduca_en - _ahora(ahora)) // timedelta(days=1)


def _ahora(ahora: datetime | None) -> datetime:
    if ahora is None:
        return datetime.now(timezone.utc)
    if ahora.tzinfo is None:
        raise ValueError("el instante tiene que llevar zona horaria")
    return ahora.astimezone(timezone.utc)


def _datos(certificado: x509.Certificate) -> Datos:
    der = certificado.public_bytes(serialization.Encoding.DER)
    return Datos(hashlib.sha256(der).hexdigest(), hashlib.sha1(der).hexdigest().upper(),
                 certificado.not_valid_before_utc, certificado.not_valid_after_utc)


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode("ascii")


def _json(datos: dict) -> bytes:
    return json.dumps(datos, separators=(",", ":"), ensure_ascii=True).encode("ascii")


class Credencial:
    """La clave privada y su certificado, para firmar la asercion del token. La clave no sale
    de aqui: ni un atributo publico, ni su repr, ni una copia (pickle o copy)."""

    __slots__ = ("_clave", "_x5t", "datos")

    def __init__(self, clave: rsa.RSAPrivateKey, certificado: x509.Certificate) -> None:
        self._clave = clave
        der = certificado.public_bytes(serialization.Encoding.DER)
        self._x5t = _b64(hashlib.sha256(der).digest())
        self.datos = _datos(certificado)

    def __repr__(self) -> str:
        return f"<credencial del correo, certificado {self.datos.huella_sha256[:16]}>"

    def __reduce_ex__(self, _protocolo: object) -> object:
        raise TypeError("la credencial del correo no se copia ni se guarda")

    def asercion(self, inquilino: str, aplicacion: str, *, ahora: datetime | None = None
                 ) -> str:
        """La asercion firmada (JWT, PS256) con la que se pide el token del inquilino
        (docs-ms entra_certificate-credentials, "Assertion format"): cabecera alg PS256, typ JWT
        y x5t#S256 (SHA-256 del certificado en DER); aud el punto del token del inquilino, iss
        y sub la aplicacion, jti nuevo, nbf = iat = ahora y exp 5 minutos despues. Firma
        RSA-PSS con SHA-256, MGF1 SHA-256 y sal de 32 bytes."""
        inquilino = _ajustes.guid(inquilino, "inquilino")
        aplicacion = _ajustes.guid(aplicacion, "aplicacion")
        momento = _ahora(ahora)
        if momento >= self.datos.caduca_en:
            raise CertificadoCaducado(
                f"el certificado caduco el {self.datos.caduca_en:%Y-%m-%d}: hace falta uno "
                "nuevo (correo-certificado.bat)")
        if momento < self.datos.emitido_en:
            raise CertificadoCaducado("el certificado aun no vale: mira la hora del equipo")
        segundos = int(momento.timestamp())
        cabecera = {"alg": "PS256", "typ": "JWT", "x5t#S256": self._x5t}
        carga = {"aud": AUDIENCIA.format(inquilino=inquilino), "iss": aplicacion,
                 "sub": aplicacion, "jti": str(uuid.uuid4()), "nbf": segundos,
                 "iat": segundos, "exp": segundos + int(VIDA_ASERCION.total_seconds())}
        firmado = f"{_b64(_json(cabecera))}.{_b64(_json(carga))}".encode("ascii")
        firma = None
        with contextlib.suppress(Exception):
            firma = self._clave.sign(
                firmado, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
                hashes.SHA256())
        if firma is None:
            raise CertificadoNoValido("no se ha podido firmar la asercion con el certificado")
        return f"{firmado.decode('ascii')}.{_b64(firma)}"


# ------------------------------------------------------------------ leer un .pem

def _leer(ruta: Path) -> bytes:
    try:
        with open(ruta, "rb") as fichero:
            contenido = fichero.read(MAX_PEM + 1)
    except FileNotFoundError:
        raise SinCertificado(f"no hay certificado del correo en {ruta}") from None
    except OSError as exc:
        raise CertificadoNoValido(f"no se puede leer el certificado del correo de {ruta}: "
                                  f"{exc.strerror or type(exc).__name__}") from None
    if len(contenido) > MAX_PEM:
        raise CertificadoNoValido(f"{ruta}: mas de {MAX_PEM} bytes, no es el certificado del "
                                  "correo")
    return contenido


def _bloques(contenido: bytes) -> dict[str, bytes] | None:
    """Los bloques PEM del fichero por su tipo, si no hay nada mas que bloques y espacios, ni
    dos del mismo tipo."""
    bloques: dict[str, bytes] = {}
    posicion = 0
    for bloque in _BLOQUE.finditer(contenido):
        tipo = bloque.group(1).decode("ascii")
        if contenido[posicion:bloque.start()].strip() or tipo in bloques:
            return None
        bloques[tipo] = bloque.group(0)
        posicion = bloque.end()
    if contenido[posicion:].strip():
        return None
    return bloques


def _par(ruta: Path) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    """La clave y el certificado de un .pem, comprobados: PKCS#8 sin cifrar, RSA de al menos
    3072 bits, y el certificado es el de esa clave."""
    bloques = _bloques(_leer(ruta))
    if bloques is None or set(bloques) != {"PRIVATE KEY", "CERTIFICATE"}:
        raise CertificadoNoValido(f"{ruta}: no es una clave privada PKCS#8 sin cifrar seguida "
                                  "de su certificado, en PEM")
    clave = certificado = None
    with contextlib.suppress(Exception):
        clave = serialization.load_pem_private_key(bloques["PRIVATE KEY"], password=None)
        certificado = x509.load_pem_x509_certificate(bloques["CERTIFICATE"])
    if clave is None or certificado is None:
        raise CertificadoNoValido(f"{ruta}: la clave o el certificado no se pueden leer")
    if not isinstance(clave, rsa.RSAPrivateKey) or clave.key_size < BITS:
        raise CertificadoNoValido(f"{ruta}: la clave no es RSA de {BITS} bits o mas")
    publica = certificado.public_key()
    if not isinstance(publica, rsa.RSAPublicKey) or (
            publica.public_numbers() != clave.public_key().public_numbers()):
        raise CertificadoNoValido(f"{ruta}: el certificado no es el de esa clave")
    return clave, certificado


def cargar(ruta: str | Path) -> Credencial:
    """La credencial del .pem (en el contenedor `correo`, el secreto de Docker)."""
    return Credencial(*_par(Path(ruta)))


def datos_de(ruta: str | Path) -> Datos:
    """Lo publico del certificado de un .pem, comprobado el par entero."""
    return _datos(_par(Path(ruta))[1])


# ------------------------------------------------------------------ la carpeta

def rutas(carpeta: str | Path, cual: str = ACTUAL) -> tuple[Path, Path]:
    """El .pem y el .cer de uno (actual, siguiente o anterior) en la carpeta."""
    nombre = BASE + _SUFIJO[cual]
    return Path(carpeta) / f"{nombre}.pem", Path(carpeta) / f"{nombre}.cer"


def comprobar_carpeta(carpeta: str | Path) -> Path:
    """La carpeta de los secretos del correo, si existe."""
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        raise NoSeHace(f"la carpeta {carpeta} no existe (en Docker, docker\\secretos\\correo, "
                       "montada para esta orden)")
    return carpeta


def _hay(ruta: Path) -> bool:
    return ruta.exists() or ruta.is_symlink()


def _quitar(ruta: Path) -> bool:
    try:
        ruta.unlink()
    except FileNotFoundError:
        return False
    return True


def estado(carpeta: str | Path) -> dict[str, Datos | CertificadoNoValido | None]:
    """Lo que hay en la carpeta: por cada uno, sus datos, por que no vale, o None."""
    salida: dict[str, Datos | CertificadoNoValido | None] = {}
    for cual in CUALES:
        pem, _cer = rutas(carpeta, cual)
        if not _hay(pem):
            salida[cual] = None
            continue
        try:
            salida[cual] = datos_de(pem)
        except CertificadoNoValido as exc:
            salida[cual] = CertificadoNoValido(str(exc))
    return salida


def _al_dia(carpeta: Path) -> str | None:
    """Rehace el .cer de cada .pem (y quita el que no tiene .pem) y pone al dia lo del
    certificado en los ajustes, si los hay. Devuelve un aviso si los ajustes no se pudieron
    poner al dia."""
    huellas: dict[str, _ajustes.Huella | None] = {}
    for cual in CUALES:
        pem, cer = rutas(carpeta, cual)
        huellas[_EN_LOS_AJUSTES[cual]] = None
        if not _hay(pem):
            _quitar(cer)
            continue
        try:
            _clave, certificado = _par(pem)
        except CertificadoNoValido:
            continue
        publico = certificado.public_bytes(serialization.Encoding.PEM)
        if not cer.is_file() or cer.read_bytes() != publico:
            _ajustes.escribir_de_una_vez(cer, publico)
        huellas[_EN_LOS_AJUSTES[cual]] = _datos(certificado).huella()
    fichero = carpeta / _ajustes.FICHERO
    try:
        actuales = _ajustes.leer(fichero)
    except _ajustes.SinAjustes:
        return None
    except _ajustes.AjustesNoValidos as exc:
        return f"los ajustes no se han puesto al dia: {exc}"
    nuevos = _ajustes.con_certificados(actuales, **huellas)
    if nuevos != actuales:
        _ajustes.escribir(fichero, nuevos)
    return None


def huellas(carpeta: str | Path) -> dict[str, _ajustes.Huella | None]:
    """Lo del certificado para los ajustes (certificado, siguiente, anterior), de la carpeta;
    None en el que no hay o no vale."""
    return {_EN_LOS_AJUSTES[cual]: (d.huella() if isinstance(d, Datos) else None)
            for cual, d in estado(carpeta).items()}


def _dentro_de_meses(momento: datetime, meses: int) -> datetime:
    anio, mes = divmod(momento.month - 1 + meses, 12)
    anio, mes = momento.year + anio, mes + 1
    return momento.replace(year=anio, month=mes,
                           day=min(momento.day, calendar.monthrange(anio, mes)[1]))


def _generar(ahora: datetime) -> tuple[bytes, bytes, Datos]:
    """Una clave nueva y su certificado autofirmado: (el .pem, el .cer, sus datos)."""
    momento = ahora.replace(microsecond=0)
    clave = rsa.generate_private_key(public_exponent=EXPONENTE, key_size=BITS)
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, NOMBRE_COMUN)])
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nombre).issuer_name(nombre)
        .public_key(clave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(momento - MARGEN_INICIO)
        .not_valid_after(_dentro_de_meses(momento, MESES))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
            encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(clave.public_key()),
                       critical=False)
        .sign(clave, hashes.SHA256()))
    publico = certificado.public_bytes(serialization.Encoding.PEM)
    privado = clave.private_bytes(serialization.Encoding.PEM,
                                  serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption())
    return privado + publico, publico, _datos(certificado)


def _describir(ruta: Path) -> str:
    try:
        datos = datos_de(ruta)
    except CertificadoNoValido as exc:
        return f"no se puede usar ({exc})"
    return f"huella {datos.huella_sha256[:16]}..., caduca el {datos.caduca_en:%Y-%m-%d}"


@dataclass(frozen=True)
class Hecho:
    """Lo que hizo una orden: sus datos y, si los ajustes no se pusieron al dia, por que."""

    datos: Datos | None
    aviso: str | None = None


def crear(carpeta: str | Path, *, siguiente: bool = False, ahora: datetime | None = None
          ) -> Hecho:
    """Una clave y un certificado nuevos. Sin `siguiente`, el primero: nunca rehace uno que
    ya existe (dejaria de valer el que esta en Entra, y el correo daria `credencial`). Con
    `siguiente`, el de la renovacion, al lado del actual."""
    carpeta = comprobar_carpeta(carpeta)
    actual, _ = rutas(carpeta, ACTUAL)
    proximo, _ = rutas(carpeta, SIGUIENTE)
    anterior, _ = rutas(carpeta, ANTERIOR)
    if siguiente:
        if not _hay(actual):
            raise NoSeHace("no hay certificado actual que renovar: el primero se crea sin "
                           "--siguiente")
        if _hay(proximo):
            raise NoSeHace(f"ya hay uno siguiente ({_describir(proximo)}): activalo cuando "
                           "este subido a Entra, o borralo (borrar --siguiente) si no se va a "
                           "subir")
        destino = SIGUIENTE
    else:
        if _hay(actual):
            raise NoSeHace(f"ya hay un certificado ({_describir(actual)}) y no se rehace: "
                           "dejaria de valer el que esta en Entra. Para uno nuevo, "
                           "correo-certificado.bat (crear --siguiente)")
        if _hay(proximo) or _hay(anterior):
            raise NoSeHace("hay un certificado siguiente o anterior sin el actual: vuelve al "
                           "anterior (volver) o activa el siguiente (activar)")
        destino = ACTUAL
    pem, cer, datos = _generar(_ahora(ahora))
    ruta_pem, ruta_cer = rutas(carpeta, destino)
    # El .cer primero: el .pem es lo que cuenta, y sin el no hay certificado.
    _ajustes.escribir_de_una_vez(ruta_cer, cer)
    _ajustes.escribir_de_una_vez(ruta_pem, pem)
    return Hecho(datos, _al_dia(carpeta))


def _mover(carpeta: Path, de: str, a: str) -> None:
    pem_de, cer_de = rutas(carpeta, de)
    pem_a, _cer_a = rutas(carpeta, a)
    os.replace(pem_de, pem_a)
    _quitar(cer_de)


def activar(carpeta: str | Path) -> Hecho:
    """El siguiente pasa a ser el actual, y el actual, el anterior (local, sin red: la
    comprobacion con Microsoft la hace despues el contenedor `correo`)."""
    carpeta = comprobar_carpeta(carpeta)
    actual, _ = rutas(carpeta, ACTUAL)
    proximo, _ = rutas(carpeta, SIGUIENTE)
    anterior, _ = rutas(carpeta, ANTERIOR)
    if not _hay(proximo):
        raise NoSeHace("no hay ningun certificado siguiente que activar (crear --siguiente)")
    datos = datos_de(proximo)
    if _hay(anterior):
        raise NoSeHace(f"aun hay un certificado anterior ({_describir(anterior)}): el ultimo "
                       "que se activo no se ha comprobado. Comprueba el correo y borra el "
                       "anterior (borrar --anterior), o vuelve a el (volver), antes de activar "
                       "otro")
    if _hay(actual):
        _mover(carpeta, ACTUAL, ANTERIOR)
    _mover(carpeta, SIGUIENTE, ACTUAL)
    return Hecho(datos, _al_dia(carpeta))


def volver(carpeta: str | Path) -> Hecho:
    """El anterior vuelve a ser el actual; el actual (el que no valio) vuelve a ser el
    siguiente, para activarlo otra vez cuando este bien subido a Entra."""
    carpeta = comprobar_carpeta(carpeta)
    actual, _ = rutas(carpeta, ACTUAL)
    proximo, _ = rutas(carpeta, SIGUIENTE)
    anterior, _ = rutas(carpeta, ANTERIOR)
    if not _hay(anterior):
        raise NoSeHace("no hay ningun certificado anterior al que volver")
    datos = datos_de(anterior)
    if _hay(actual):
        if _hay(proximo):
            raise NoSeHace(f"hay un certificado siguiente ({_describir(proximo)}) y el actual "
                           "no tiene donde ir: borra el siguiente (borrar --siguiente) antes "
                           "de volver")
        _mover(carpeta, ACTUAL, SIGUIENTE)
    _mover(carpeta, ANTERIOR, ACTUAL)
    return Hecho(datos, _al_dia(carpeta))


def borrar(carpeta: str | Path, cual: str | None = None) -> tuple[list[str], str | None]:
    """Borra uno (anterior o siguiente) o, sin `cual`, todos: cortar el acceso desde este
    equipo (§2.5). Devuelve los que habia y el aviso de los ajustes, si lo hay."""
    carpeta = comprobar_carpeta(carpeta)
    borrados = []
    for uno in CUALES if cual is None else (cual,):
        pem, cer = rutas(carpeta, uno)
        if _quitar(pem):
            borrados.append(uno)
        _quitar(cer)
    return borrados, _al_dia(carpeta)
