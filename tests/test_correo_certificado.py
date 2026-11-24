"""El certificado y los ajustes del correo de facturas (paso 18, pasos 7 del plan; solo Docker).

- crear: RSA de 3072 bits, autofirmado, 24 meses, la clave en PEM PKCS#8 seguida de su
  certificado; el .cer, solo la parte publica. Nunca rehace el actual (solo --siguiente).
- La asercion es la que pide Microsoft (PS256, x5t#S256, aud del inquilino, iss = sub,
  jti nuevo, 5 minutos) y la firma se verifica con la parte publica.
- activar, volver y borrar (todo local), con los ajustes al dia.
- La clave no sale: ni en un mensaje, ni en una excepcion (ni encadenada), ni en el registro,
  ni en la salida de la CLI; la credencial no se copia ni se guarda.
- Se firma tambien con los procesos prohibidos (el gancho de auditoria de nativo).
- Los ajustes se validan con rigor (lo que va en las URL de Microsoft) y sus errores no dicen
  lo que pone.
- En la instalacion nativa no hay correo (decision del dueno: solo Docker).
"""

from __future__ import annotations

import ast
import base64
import copy
import hashlib
import json
import logging
import os
import pickle
import re
import subprocess
import sys
import traceback
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import RAIZ
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

from bms_agent import cli, documents, nativo
from bms_agent.correo import MAX_PDF, ajustes, certificado

SRC = RAIZ / "src" / "bms_agent"
AHORA = datetime(2026, 11, 24, 10, 0, tzinfo=timezone.utc)
INQUILINO = "11111111-2222-4333-8444-555555555555"
APLICACION = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
BUZON = "facturen@contoso.onmicrosoft.com"
CONTROL = "bms-control@contoso.onmicrosoft.com"


def _b64d(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _trozos_de_la_clave(pem: bytes) -> list[str]:
    """Las lineas de base64 del bloque de la clave privada: ninguna puede salir de ningun
    sitio (mas de 40 caracteres: no se confunden con nada)."""
    bloque = pem.split(b"-----BEGIN PRIVATE KEY-----")[1].split(b"-----END PRIVATE KEY-----")[0]
    lineas = [l.decode("ascii") for l in bloque.split() if len(l) > 40]
    assert len(lineas) > 30
    return lineas


def _sin_la_clave(texto: str, pem: bytes) -> None:
    trozos = _trozos_de_la_clave(pem)
    assert "PRIVATE KEY" not in texto
    assert not [t for t in trozos if t in texto or t[:24] in texto]
    # Ni los numeros de la clave (el modulo privado, los primos) en decimal o en hexadecimal.
    numeros = serialization.load_pem_private_key(
        pem.split(b"-----BEGIN CERTIFICATE-----")[0], password=None).private_numbers()
    for n in (numeros.d, numeros.p, numeros.q):
        assert str(n)[:30] not in texto and format(n, "x")[:30] not in texto


def _excepcion_entera(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) + repr(exc)


@pytest.fixture
def carpeta(tmp_path) -> Path:
    """La carpeta de los secretos del correo (docker\\secretos\\correo, montada en orden)."""
    salida = tmp_path / "secretos-correo"
    salida.mkdir()
    return salida


@pytest.fixture(scope="module")
def creado(tmp_path_factory) -> tuple[Path, certificado.Datos]:
    """Un certificado creado una vez para las pruebas que solo lo leen (RSA 3072 tarda)."""
    salida = tmp_path_factory.mktemp("creado")
    hecho = certificado.crear(salida, ahora=AHORA)
    return salida, hecho.datos


def _ajustes_validos(**cambios) -> dict:
    datos = {"version": 1, "inquilino": INQUILINO, "aplicacion": APLICACION,
             "buzon": BUZON, "buzon_control": CONTROL, "desde": "2026-10-25",
             "certificado": None, "siguiente": None, "anterior": None,
             "limites": {"pdf_dia": 150, "mib_dia": 750}}
    datos.update(cambios)
    return datos


# ============================================================ crear

def test_max_pdf_es_lo_que_se_manda_a_la_api() -> None:
    assert MAX_PDF == documents.MAX_BYTES_API == 20 * 1024 * 1024


def test_crear_hace_una_clave_rsa_3072_autofirmada_de_24_meses(creado) -> None:
    salida, datos = creado
    pem, cer = certificado.rutas(salida)
    contenido = pem.read_bytes()
    # La clave en PKCS#8 sin cifrar, seguida de su certificado; nada mas.
    assert contenido.startswith(b"-----BEGIN PRIVATE KEY-----\n")
    assert contenido.count(b"-----BEGIN ") == 2
    assert contenido.index(b"-----BEGIN CERTIFICATE-----") > contenido.index(
        b"-----END PRIVATE KEY-----")
    clave = serialization.load_pem_private_key(contenido.split(b"-----BEGIN CERT")[0],
                                               password=None)
    assert isinstance(clave, rsa.RSAPrivateKey)
    assert clave.key_size == 3072 and clave.private_numbers().public_numbers.e == 65537
    cert = x509.load_pem_x509_certificate(cer.read_bytes())
    # El .cer es solo la parte publica: el certificado del .pem.
    assert b"PRIVATE" not in cer.read_bytes()
    assert cer.read_bytes() in contenido
    assert cert.public_key().public_numbers() == clave.public_key().public_numbers()
    # Autofirmado, sin datos de la empresa, 24 meses desde que se crea.
    assert cert.issuer == cert.subject
    assert cert.subject.rfc4514_string() == "CN=BMS lector de facturas"
    cert.public_key().verify(cert.signature, cert.tbs_certificate_bytes,
                             padding.PKCS1v15(), cert.signature_hash_algorithm)
    assert cert.not_valid_after_utc == datetime(2028, 11, 24, 10, 0, tzinfo=timezone.utc)
    assert cert.not_valid_before_utc == AHORA - timedelta(minutes=5)
    assert cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False
    # La huella es la del certificado en DER (la de los ajustes y la de x5t#S256).
    der = cert.public_bytes(serialization.Encoding.DER)
    assert datos.huella_sha256 == hashlib.sha256(der).hexdigest()
    assert datos.huella_sha1 == hashlib.sha1(der).hexdigest().upper()
    assert datos.caduca_en == cert.not_valid_after_utc
    assert datos.dias(AHORA) == 731
    if os.name == "posix":
        assert pem.stat().st_mode & 0o777 == 0o600


def test_24_meses_desde_un_29_de_febrero() -> None:
    bisiesto = datetime(2028, 2, 29, 12, 0, tzinfo=timezone.utc)
    assert certificado._dentro_de_meses(bisiesto, 24) == datetime(2030, 2, 28, 12, 0,
                                                                 tzinfo=timezone.utc)
    assert certificado._dentro_de_meses(AHORA, 24) == datetime(2028, 11, 24, 10, 0,
                                                              tzinfo=timezone.utc)


def test_crear_no_rehace_el_actual(carpeta) -> None:
    primero = certificado.crear(carpeta, ahora=AHORA).datos
    pem, cer = certificado.rutas(carpeta)
    antes = (pem.read_bytes(), cer.read_bytes())
    with pytest.raises(certificado.NoSeHace, match="no se rehace") as error:
        certificado.crear(carpeta, ahora=AHORA)
    assert primero.huella_sha256[:16] in str(error.value)
    assert (pem.read_bytes(), cer.read_bytes()) == antes
    # Tampoco uno que no se puede leer: se borra a proposito o se deja.
    pem.write_bytes(b"roto")
    with pytest.raises(certificado.NoSeHace, match="no se rehace"):
        certificado.crear(carpeta, ahora=AHORA)
    assert pem.read_bytes() == b"roto"


def test_sin_actual_no_hay_siguiente_ni_se_crea_con_restos(carpeta) -> None:
    with pytest.raises(certificado.NoSeHace, match="que renovar"):
        certificado.crear(carpeta, siguiente=True, ahora=AHORA)
    assert list(carpeta.iterdir()) == []
    certificado.crear(carpeta, ahora=AHORA)
    certificado.crear(carpeta, siguiente=True, ahora=AHORA)
    with pytest.raises(certificado.NoSeHace, match="ya hay uno siguiente"):
        certificado.crear(carpeta, siguiente=True, ahora=AHORA)
    # Un siguiente sin actual (una vuelta cortada a medias): no se crea otro actual encima.
    certificado.rutas(carpeta)[0].unlink()
    with pytest.raises(certificado.NoSeHace, match="volver|activar"):
        certificado.crear(carpeta, ahora=AHORA)


def test_la_carpeta_tiene_que_existir(tmp_path) -> None:
    with pytest.raises(certificado.NoSeHace, match="no existe"):
        certificado.crear(tmp_path / "no-esta", ahora=AHORA)


# ============================================================ la asercion

def test_la_asercion_es_la_que_pide_microsoft(creado) -> None:
    salida, datos = creado
    credencial = certificado.cargar(certificado.rutas(salida)[0])
    assert credencial.datos == datos
    momento = AHORA + timedelta(days=1, seconds=7)
    asercion = credencial.asercion(INQUILINO.upper(), APLICACION, ahora=momento)
    cabecera, carga, firma = asercion.split(".")
    der = x509.load_pem_x509_certificate(certificado.rutas(salida)[1].read_bytes()).public_bytes(
        serialization.Encoding.DER)
    assert json.loads(_b64d(cabecera)) == {
        "alg": "PS256", "typ": "JWT",
        "x5t#S256": base64.urlsafe_b64encode(hashlib.sha256(der).digest()).rstrip(b"=").decode()}
    reclamado = json.loads(_b64d(carga))
    segundos = int(momento.timestamp())
    assert reclamado == {
        "aud": f"https://login.microsoftonline.com/{INQUILINO}/oauth2/v2.0/token",
        "iss": APLICACION, "sub": APLICACION, "jti": reclamado["jti"],
        "nbf": segundos, "iat": segundos, "exp": segundos + 300}
    assert uuid.UUID(reclamado["jti"]).version == 4
    # Sin relleno de base64 en ningun trozo (JWS compacto).
    assert "=" not in asercion
    # RSA-PSS con SHA-256, MGF1 SHA-256 y sal de 32 bytes (PS256), con la parte publica.
    publica = x509.load_pem_x509_certificate(certificado.rutas(salida)[1].read_bytes()).public_key()
    firmado = f"{cabecera}.{carga}".encode("ascii")
    publica.verify(_b64d(firma), firmado,
                   padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
                   hashes.SHA256())
    with pytest.raises(InvalidSignature):
        publica.verify(_b64d(firma), firmado + b"x",
                       padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
                       hashes.SHA256())
    # Un jti nuevo cada vez.
    otra = credencial.asercion(INQUILINO, APLICACION, ahora=momento)
    assert json.loads(_b64d(otra.split(".")[1]))["jti"] != reclamado["jti"]


def test_la_asercion_solo_con_ids_de_entra_y_un_certificado_que_vale(creado) -> None:
    salida, datos = creado
    credencial = certificado.cargar(certificado.rutas(salida)[0])
    # El inquilino va en la URL del token: solo un GUID.
    for malo in ("contoso.onmicrosoft.com", f"{INQUILINO}/../common", "common", ""):
        with pytest.raises(ajustes.AjustesNoValidos):
            credencial.asercion(malo, APLICACION, ahora=AHORA)
    with pytest.raises(ajustes.AjustesNoValidos):
        credencial.asercion(INQUILINO, "otra-app", ahora=AHORA)
    with pytest.raises(certificado.CertificadoCaducado, match="caduco"):
        credencial.asercion(INQUILINO, APLICACION, ahora=datos.caduca_en)
    with pytest.raises(certificado.CertificadoCaducado, match="hora del equipo"):
        credencial.asercion(INQUILINO, APLICACION, ahora=datos.emitido_en - timedelta(seconds=1))
    with pytest.raises(ValueError, match="zona horaria"):
        credencial.asercion(INQUILINO, APLICACION, ahora=datetime(2027, 1, 1))


def test_la_credencial_no_ensena_ni_copia_la_clave(creado) -> None:
    salida, datos = creado
    pem = certificado.rutas(salida)[0].read_bytes()
    credencial = certificado.cargar(certificado.rutas(salida)[0])
    _sin_la_clave(repr(credencial) + str(credencial), pem)
    assert datos.huella_sha256[:16] in repr(credencial)
    for copiar in (pickle.dumps, copy.copy, copy.deepcopy):
        with pytest.raises(TypeError, match="no se copia"):
            copiar(credencial)
    with pytest.raises((AttributeError, TypeError)):
        vars(credencial)


# ============================================================ un .pem que no vale

def _otra_clave(bits: int = 3072) -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=bits)


def _pkcs8(clave, cifrado=None) -> bytes:
    return clave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                               cifrado or serialization.NoEncryption())


def test_un_pem_que_no_vale_se_dice_sin_la_clave(creado, carpeta) -> None:
    salida, _datos = creado
    bueno = certificado.rutas(salida)[0].read_bytes()
    clave_pem, cert_pem = bueno.split(b"-----BEGIN CERTIFICATE-----")
    cert_pem = b"-----BEGIN CERTIFICATE-----" + cert_pem
    otra = _otra_clave()
    pequena = _otra_clave(2048)
    curva = ec.generate_private_key(ec.SECP256R1())
    pkcs1 = otra.private_bytes(serialization.Encoding.PEM,
                               serialization.PrivateFormat.TraditionalOpenSSL,
                               serialization.NoEncryption())
    cifrada = _pkcs8(otra, serialization.BestAvailableEncryption(b"una contrasena"))
    rota = clave_pem.replace(clave_pem.split(b"\n")[5], b"A" * 64)
    casos = {
        "vacio": b"",
        "basura": b"esto no es un certificado\n",
        "solo la clave": clave_pem,
        "solo el certificado": cert_pem,
        "otra clave": _pkcs8(otra) + cert_pem,
        "pkcs1": pkcs1 + cert_pem,
        "cifrada": cifrada + cert_pem,
        "2048 bits": _pkcs8(pequena) + cert_pem,
        "curva eliptica": _pkcs8(curva) + cert_pem,
        "algo detras": bueno + b"y algo mas\n",
        "algo delante": b"hola\n" + bueno,
        "dos claves": clave_pem + bueno,
        "clave rota": rota + cert_pem,
        "demasiado grande": bueno + b"\n" * (certificado.MAX_PEM),
    }
    for nombre, contenido in casos.items():
        ruta = carpeta / f"{nombre}.pem"
        ruta.write_bytes(contenido)
        with pytest.raises(certificado.CertificadoNoValido) as error:
            certificado.cargar(ruta)
        exc = error.value
        # Ni encadenada a la de cryptography (que podria llevar algo de lo leido).
        assert exc.__cause__ is None and exc.__context__ is None, nombre
        texto = _excepcion_entera(exc)
        _sin_la_clave(texto, bueno)
        if b"PRIVATE KEY-----" in contenido and nombre not in ("solo la clave",):
            for otro in (otra, pequena):
                linea = _pkcs8(otro).split(b"\n")[3].decode()
                assert linea not in texto, nombre
    with pytest.raises(certificado.SinCertificado, match="no hay certificado"):
        certificado.cargar(carpeta / "no-esta.pem")


def test_el_par_tiene_que_ser_suyo(creado, carpeta) -> None:
    """Un certificado con la clave de otro no firma nada: se dice al cargarlo."""
    salida, _datos = creado
    otro = certificado.crear(carpeta, ahora=AHORA)
    clave_de_otro = certificado.rutas(carpeta)[0].read_bytes().split(b"-----BEGIN CERT")[0]
    cert_bueno = certificado.rutas(salida)[1].read_bytes()
    mezcla = carpeta / "mezcla.pem"
    mezcla.write_bytes(clave_de_otro + cert_bueno)
    with pytest.raises(certificado.CertificadoNoValido, match="no es el de esa clave"):
        certificado.cargar(mezcla)
    assert otro.datos is not None


# ============================================================ renovar

def _huella_en(carpeta: Path, cual: str) -> str | None:
    datos = certificado.estado(carpeta)[cual]
    return datos.huella_sha256 if isinstance(datos, certificado.Datos) else None


def _fijar_ajustes(carpeta: Path) -> None:
    ajustes.escribir(carpeta / ajustes.FICHERO, ajustes.fijar(
        None, hoy=AHORA.date(), inquilino=INQUILINO, aplicacion=APLICACION, buzon=BUZON,
        buzon_control=CONTROL))


def _en_los_ajustes(carpeta: Path) -> tuple[str | None, str | None, str | None]:
    leidos = ajustes.leer(carpeta / ajustes.FICHERO)
    return tuple(None if h is None else h.huella_sha256
                 for h in (leidos.certificado, leidos.siguiente, leidos.anterior))


def test_renovar_crear_siguiente_activar_y_borrar_el_anterior(carpeta) -> None:
    _fijar_ajustes(carpeta)
    viejo = certificado.crear(carpeta, ahora=AHORA).datos.huella_sha256
    assert _en_los_ajustes(carpeta) == (viejo, None, None)
    nuevo = certificado.crear(carpeta, siguiente=True,
                              ahora=AHORA + timedelta(days=700)).datos.huella_sha256
    assert (_huella_en(carpeta, "actual"), _huella_en(carpeta, "siguiente")) == (viejo, nuevo)
    assert _en_los_ajustes(carpeta) == (viejo, nuevo, None)
    # El .cer del siguiente es el que se sube a Entra.
    assert certificado.rutas(carpeta, "siguiente")[1].is_file()
    assert certificado.activar(carpeta).datos.huella_sha256 == nuevo
    assert [_huella_en(carpeta, c) for c in certificado.CUALES] == [nuevo, None, viejo]
    assert _en_los_ajustes(carpeta) == (nuevo, None, viejo)
    # Cada .cer es el de su .pem; el del siguiente ya no esta.
    for cual in certificado.CUALES:
        pem, cer = certificado.rutas(carpeta, cual)
        assert cer.exists() == pem.exists()
        if pem.exists():
            assert cer.read_bytes() in pem.read_bytes()
    # Sin otro siguiente no hay nada que activar; con el anterior sin comprobar, tampoco.
    with pytest.raises(certificado.NoSeHace, match="ningun certificado siguiente"):
        certificado.activar(carpeta)
    certificado.crear(carpeta, siguiente=True, ahora=AHORA + timedelta(days=701))
    antes = sorted((p.name, p.read_bytes()) for p in carpeta.iterdir())
    with pytest.raises(certificado.NoSeHace, match="anterior"):
        certificado.activar(carpeta)
    assert sorted((p.name, p.read_bytes()) for p in carpeta.iterdir()) == antes
    borrados, aviso = certificado.borrar(carpeta, "siguiente")
    assert (borrados, aviso) == (["siguiente"], None)
    # Comprobado el nuevo: se borra el anterior.
    assert certificado.borrar(carpeta, "anterior") == (["anterior"], None)
    assert certificado.borrar(carpeta, "anterior") == ([], None)
    assert sorted(p.name for p in carpeta.iterdir()) == [
        "correo_ajustes.json", "correo_certificado.cer", "correo_certificado.pem"]
    assert _en_los_ajustes(carpeta) == (nuevo, None, None)


def test_volver_al_anterior_si_el_nuevo_no_vale(carpeta) -> None:
    _fijar_ajustes(carpeta)
    viejo = certificado.crear(carpeta, ahora=AHORA).datos.huella_sha256
    with pytest.raises(certificado.NoSeHace, match="ningun certificado anterior"):
        certificado.volver(carpeta)
    nuevo = certificado.crear(carpeta, siguiente=True, ahora=AHORA).datos.huella_sha256
    certificado.activar(carpeta)
    # Microsoft dijo credencial (el .cer aun no estaba en Entra): se vuelve, y el nuevo queda
    # como siguiente para activarlo otra vez.
    assert certificado.volver(carpeta).datos.huella_sha256 == viejo
    assert [_huella_en(carpeta, c) for c in certificado.CUALES] == [viejo, nuevo, None]
    assert _en_los_ajustes(carpeta) == (viejo, nuevo, None)
    assert certificado.activar(carpeta).datos.huella_sha256 == nuevo
    # Una vuelta (o una activacion) cortada a medias: sin actual, con siguiente y anterior.
    # volver lo deja como antes de activar.
    os.replace(certificado.rutas(carpeta)[0], certificado.rutas(carpeta, "siguiente")[0])
    assert certificado.volver(carpeta).datos.huella_sha256 == viejo
    assert [_huella_en(carpeta, c) for c in certificado.CUALES] == [viejo, nuevo, None]
    # Con actual y siguiente, volver no pisa el siguiente.
    certificado.activar(carpeta)
    certificado.crear(carpeta, siguiente=True, ahora=AHORA)
    with pytest.raises(certificado.NoSeHace, match="borrar --siguiente"):
        certificado.volver(carpeta)


def test_borrar_sin_opciones_corta_el_acceso(carpeta) -> None:
    _fijar_ajustes(carpeta)
    certificado.crear(carpeta, ahora=AHORA)
    certificado.crear(carpeta, siguiente=True, ahora=AHORA)
    certificado.activar(carpeta)
    certificado.crear(carpeta, siguiente=True, ahora=AHORA)
    borrados, aviso = certificado.borrar(carpeta)
    assert (sorted(borrados), aviso) == (sorted(certificado.CUALES), None)
    assert [p.name for p in carpeta.iterdir()] == [ajustes.FICHERO]
    assert _en_los_ajustes(carpeta) == (None, None, None)


def test_unos_ajustes_que_no_valen_no_paran_la_renovacion(carpeta) -> None:
    (carpeta / ajustes.FICHERO).write_text("{}", encoding="utf-8")
    hecho = certificado.crear(carpeta, ahora=AHORA)
    assert hecho.aviso.startswith("los ajustes no se han puesto al dia: les falta version")
    assert (carpeta / ajustes.FICHERO).read_text(encoding="utf-8") == "{}"


# ============================================================ la CLI

def _cli(capsys, *argumentos: str) -> tuple[int, str, str]:
    codigo = cli.main(["correo", *argumentos])
    salida = capsys.readouterr()
    return codigo, salida.out, salida.err


def test_la_cli_del_certificado_y_de_los_ajustes(carpeta, capsys, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    c = str(carpeta)
    assert _cli(capsys, "certificado", "ver", "--carpeta", c)[0] == cli.CORREO_SIN_CONFIGURAR
    assert _cli(capsys, "ajustes", "ver", "--carpeta", c)[0] == cli.CORREO_SIN_CONFIGURAR
    codigo, salida, _ = _cli(capsys, "certificado", "crear", "--carpeta", c)
    assert codigo == 0 and "La clave privada se queda en este equipo" in salida
    pem = certificado.rutas(carpeta)[0].read_bytes()
    huella = certificado.datos_de(certificado.rutas(carpeta)[0]).huella_sha256
    assert f"huella SHA-256: {huella}" in salida
    assert str(certificado.rutas(carpeta)[1]) in salida
    todo = salida
    codigo, salida, error = _cli(capsys, "certificado", "crear", "--carpeta", c)
    assert codigo == 1 and "no se rehace" in error
    todo += salida + error
    # La primera vez, los cuatro datos.
    codigo, _salida, error = _cli(capsys, "ajustes", "fijar", "--carpeta", c, "--buzon", BUZON)
    assert codigo == 2 and "--inquilino, --aplicacion, --buzon-control" in error
    codigo, salida, error = _cli(capsys, "ajustes", "fijar", "--carpeta", c,
                                 "--inquilino", INQUILINO.upper(), "--aplicacion", APLICACION,
                                 "--buzon", "Facturen@Contoso.onmicrosoft.com",
                                 "--buzon-control", CONTROL)
    assert (codigo, error) == (0, "")
    leidos = ajustes.leer(carpeta / ajustes.FICHERO)
    assert (leidos.inquilino, leidos.buzon) == (INQUILINO, BUZON)
    assert leidos.certificado.huella_sha256 == huella
    # Despues, solo lo que cambia: otro buzon de control (§2.3, control_no_existe).
    otro = "control-2@contoso.onmicrosoft.com"
    assert _cli(capsys, "ajustes", "fijar", "--carpeta", c, "--buzon-control", otro)[0] == 0
    assert ajustes.leer(carpeta / ajustes.FICHERO).buzon_control == otro
    codigo, salida, _ = _cli(capsys, "ajustes", "ver", "--carpeta", c)
    assert codigo == 0 and BUZON in salida and otro in salida and huella[:16] in salida
    todo += salida
    codigo, salida, error = _cli(capsys, "certificado", "crear", "--siguiente", "--carpeta", c)
    assert codigo == 0 and "correo_certificado-siguiente.cer" in salida
    todo += salida + error
    pem_siguiente = certificado.rutas(carpeta, "siguiente")[0].read_bytes()
    for orden in (("certificado", "activar"), ("certificado", "ver"), ("certificado", "volver"),
                  ("certificado", "borrar", "--siguiente"), ("certificado", "ver")):
        codigo, salida, error = _cli(capsys, *orden, "--carpeta", c)
        assert codigo == 0, (orden, error)
        todo += salida + error
    codigo, salida, error = _cli(capsys, "certificado", "borrar", "--anterior", "--carpeta", c)
    assert (codigo, salida.strip()) == (0, "No habia nada que borrar.")
    # Un .pem roto: ver lo dice, sin la clave, y sale con 2.
    roto = pem.replace(pem.split(b"\n")[4], b"B" * 64)
    certificado.rutas(carpeta)[0].write_bytes(roto)
    codigo, salida, error = _cli(capsys, "certificado", "ver", "--carpeta", c)
    assert codigo == 2 and "no se puede usar" in salida
    todo += salida + error
    _sin_la_clave(todo + caplog.text, pem)
    _sin_la_clave(todo + caplog.text, pem_siguiente)


def test_la_cli_sin_carpeta_o_con_ajustes_malos(carpeta, capsys) -> None:
    codigo, _salida, error = _cli(capsys, "certificado", "crear", "--carpeta",
                                  str(carpeta / "no-esta"))
    assert codigo == 1 and "no existe" in error
    with pytest.raises(SystemExit):
        cli.main(["correo", "certificado", "crear"])
    capsys.readouterr()
    (carpeta / ajustes.FICHERO).write_text('{"version": 1}', encoding="utf-8")
    codigo, _salida, error = _cli(capsys, "ajustes", "ver", "--carpeta", str(carpeta))
    assert codigo == 2 and "les falta" in error
    # Unos ajustes que no valen solo se sustituyen enteros.
    codigo, _salida, error = _cli(capsys, "ajustes", "fijar", "--carpeta", str(carpeta),
                                  "--buzon-control", CONTROL)
    assert codigo == 2
    codigo, _salida, error = _cli(capsys, "ajustes", "fijar", "--carpeta", str(carpeta),
                                  "--inquilino", INQUILINO, "--aplicacion", APLICACION,
                                  "--buzon", BUZON, "--buzon-control", CONTROL)
    assert codigo == 0 and "se sustituyen" in error
    assert ajustes.leer(carpeta / ajustes.FICHERO).buzon == BUZON


def test_en_la_nativa_no_hay_correo(carpeta, capsys, monkeypatch) -> None:
    """Decision del dueno: el correo es solo de Docker. La instalacion nativa lo dice y no
    toca nada."""
    monkeypatch.setattr(nativo, "instalacion_actual", lambda: object())
    codigo, _salida, error = _cli(capsys, "certificado", "crear", "--carpeta", str(carpeta))
    assert codigo == 2 and "solo de la variante Docker" in error
    assert list(carpeta.iterdir()) == []


# ============================================================ los ajustes

def test_los_ajustes_se_leen_y_se_escriben_iguales(carpeta) -> None:
    ruta = carpeta / ajustes.FICHERO
    ruta.write_text(json.dumps(_ajustes_validos(
        certificado={"huella_sha256": "a" * 64, "caduca_en": "2028-11-24T10:00:00Z"})),
        encoding="utf-8")
    leidos = ajustes.leer(ruta)
    assert leidos.desde == date(2026, 10, 25) and leidos.limites == ajustes.Limites(150, 750)
    assert leidos.certificado.caduca_en == datetime(2028, 11, 24, 10, tzinfo=timezone.utc)
    ajustes.escribir(ruta, leidos)
    assert ajustes.leer(ruta) == leidos
    assert json.loads(ruta.read_text(encoding="utf-8")) == ajustes.como_datos(leidos)
    if os.name == "posix":
        assert ruta.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ajustes.SinAjustes):
        ajustes.leer(carpeta / "no-esta.json")


@pytest.mark.parametrize("cambios, campo", [
    ({"version": 2}, "version"),
    ({"version": True}, "version"),
    ({"inquilino": "contoso.onmicrosoft.com"}, "inquilino"),
    ({"inquilino": "11111111-2222-4333-8444-55555555555g"}, "inquilino"),
    ({"aplicacion": "11111111222243338444555555555555"}, "aplicacion"),
    ({"buzon": "facturen@contoso.onmicrosoft.com/../users"}, "buzon"),
    ({"buzon": "facturen@contoso.onmicrosoft.com?$expand=x"}, "buzon"),
    ({"buzon": "fac#turen@contoso.onmicrosoft.com"}, "buzon"),
    ({"buzon": "fac%2Fturen@contoso.onmicrosoft.com"}, "buzon"),
    ({"buzon": "fac turen@contoso.onmicrosoft.com"}, "buzon"),
    ({"buzon": "facturen@contoso"}, "buzon"),
    ({"buzon": "factuKen@contoso.onmicrosoft.com"}, "buzon"),
    ({"buzon": ".facturen@contoso.onmicrosoft.com"}, "buzon"),
    ({"buzon": "a" * 65 + "@contoso.onmicrosoft.com"}, "buzon"),
    ({"buzon": 7}, "buzon"),
    ({"buzon_control": BUZON}, "buzon_control"),
    ({"buzon_control": "bms-control@fabrikam.example"}, "buzon_control"),
    ({"desde": "2026-13-01"}, "desde"),
    ({"desde": "25-10-2026"}, "desde"),
    ({"limites": {"pdf_dia": 0, "mib_dia": 750}}, "limites.pdf_dia"),
    ({"limites": {"pdf_dia": True, "mib_dia": 750}}, "limites.pdf_dia"),
    ({"limites": {"pdf_dia": 150, "mib_dia": 10 ** 6}}, "limites.mib_dia"),
    ({"limites": {"pdf_dia": 150}}, "limites"),
    ({"certificado": {"huella_sha256": "A" * 64, "caduca_en": "2028-11-24T10:00:00Z"}},
     "certificado.huella_sha256"),
    ({"certificado": {"huella_sha256": "a" * 64, "caduca_en": "2028-11-24"}},
     "certificado.caduca_en"),
    ({"anterior": {"huella_sha256": "a" * 64}}, "anterior"),
    ({"otra": 1}, "claves que no son"),
])
def test_unos_ajustes_que_no_valen_dicen_el_campo_y_no_lo_que_pone(carpeta, cambios,
                                                                   campo) -> None:
    ruta = carpeta / ajustes.FICHERO
    ruta.write_text(json.dumps(_ajustes_validos(**cambios)), encoding="utf-8")
    with pytest.raises(ajustes.AjustesNoValidos) as error:
        ajustes.leer(ruta)
    texto = str(error.value)
    assert campo in texto
    for valor in cambios.values():
        if isinstance(valor, str) and len(valor) > 6:
            assert valor not in texto


@pytest.mark.parametrize("contenido", [
    b"", b"[]", b"no es json", b'{"version": 1, "version": 1}', b"\xff\xfe",
    b'{"version": NaN}', b"[" * 16000, b" " * (ajustes.MAX_BYTES + 1)])
def test_un_fichero_de_ajustes_que_no_es_json_de_ajustes(carpeta, contenido) -> None:
    ruta = carpeta / ajustes.FICHERO
    ruta.write_bytes(contenido)
    with pytest.raises(ajustes.AjustesNoValidos):
        ajustes.leer(ruta)


def test_fijar_los_ajustes() -> None:
    hoy = date(2026, 11, 24)
    with pytest.raises(ajustes.AjustesNoValidos, match="la primera vez hacen falta"):
        ajustes.fijar(None, hoy=hoy, inquilino=INQUILINO)
    primeros = ajustes.fijar(None, hoy=hoy, inquilino=INQUILINO, aplicacion=APLICACION,
                             buzon=BUZON, buzon_control=CONTROL)
    assert primeros.desde == date(2026, 10, 25) and primeros.limites == ajustes.Limites()
    assert primeros.certificado is None
    cambiados = ajustes.fijar(primeros, hoy=hoy, desde="2026-01-01", pdf_dia=20)
    assert (cambiados.desde, cambiados.limites, cambiados.buzon) == (
        date(2026, 1, 1), ajustes.Limites(20, 750), BUZON)
    with pytest.raises(ajustes.AjustesNoValidos, match="posterior a hoy"):
        ajustes.fijar(primeros, hoy=hoy, desde="2026-11-25")
    with pytest.raises(ajustes.AjustesNoValidos, match="limites.mib_dia"):
        ajustes.fijar(primeros, hoy=hoy, mib_dia=0)
    with pytest.raises(ajustes.AjustesNoValidos, match="otro buzon"):
        ajustes.fijar(primeros, hoy=hoy, buzon_control=BUZON.upper())


# ============================================================ procesos, red y la base

FIRMA_SIN_PROCESOS = r'''
import base64, json, os, subprocess, sys
sys.path.insert(0, sys.argv[1])
from bms_agent import nativo
nativo.prohibir_procesos()
# Desde aqui, nada arranca otro programa: tampoco cryptography al importarse, crear la clave
# o firmar.
from bms_agent.correo import certificado
hecho = certificado.crear(sys.argv[2])
credencial = certificado.cargar(certificado.rutas(sys.argv[2])[0])
asercion = credencial.asercion("11111111-2222-4333-8444-555555555555",
                               "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
cabecera, carga, firma = asercion.split(".")
publica = x509.load_pem_x509_certificate(certificado.rutas(sys.argv[2])[1].read_bytes()).public_key()
d = lambda t: base64.urlsafe_b64decode(t + "=" * (-len(t) % 4))
publica.verify(d(firma), f"{cabecera}.{carga}".encode(), padding.PSS(
    mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())
try:
    subprocess.run(["true"])
except PermissionError as exc:
    assert "no arranca otros programas" in str(exc)
else:
    raise SystemExit("ha lanzado un proceso")
print(json.loads(d(cabecera))["alg"], hecho.datos.huella_sha256 == credencial.datos.huella_sha256)
'''


def test_firma_con_los_procesos_prohibidos(tmp_path) -> None:
    """Como en la instalacion (nativo.prohibir_procesos, un gancho de auditoria que no se
    quita): importar cryptography, crear la clave y el certificado y firmar no arrancan ningun
    programa. Se prueba en otro proceso, con los avisos como errores."""
    carpeta = tmp_path / "secretos-correo"
    carpeta.mkdir()
    proceso = subprocess.run(
        [sys.executable, "-W", "error", "-c", FIRMA_SIN_PROCESOS, str(SRC.parent), str(carpeta)],
        capture_output=True, text=True, timeout=120)
    assert proceso.returncode == 0, proceso.stderr
    assert proceso.stdout.split() == ["PS256", "True"]


def test_lo_del_certificado_no_abre_la_base_ni_llega_a_la_api(tmp_path) -> None:
    """Los modulos del correo que hay en este paso no traen (tampoco por otro modulo) ni la
    base, ni la lectura, ni el SDK de la API, ni nada que hable con la red."""
    codigo = ("import sys; sys.path.insert(0, sys.argv[1]); "
              "import bms_agent.correo.certificado, bms_agent.correo.ajustes; "
              "print('\\n'.join(sorted(sys.modules)))")
    proceso = subprocess.run([sys.executable, "-c", codigo, str(SRC.parent)],
                             capture_output=True, text=True, timeout=60)
    assert proceso.returncode == 0, proceso.stderr
    cargados = set(proceso.stdout.split())
    # Sin socket: cryptography.x509 importa email.utils, que lo importa (para make_msgid) sin
    # abrir nada; lo que no deja salir es la red de cada contenedor (orden no tiene ninguna).
    prohibidos = {"sqlite3", "bms_agent.almacen", "bms_agent.lectura", "bms_agent.extract",
                  "bms_agent.ingesta", "bms_agent.serve", "anthropic", "httpx", "httpx2",
                  "httpcore", "httpcore2", "urllib.request", "urllib3", "http.client", "ssl"}
    assert cargados & prohibidos == set()


def test_solo_certificado_toca_la_clave() -> None:
    """cryptography solo la importa correo/certificado.py, y el atributo de la clave de la
    credencial (_clave) solo lo nombra ese modulo."""
    malos = []
    for ruta in sorted(SRC.rglob("*.py")):
        nombre = ruta.relative_to(SRC).as_posix()
        if nombre == "correo/certificado.py":
            continue
        for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Import):
                malos += [(nombre, a.name) for a in nodo.names
                          if a.name.split(".")[0] == "cryptography"]
            elif isinstance(nodo, ast.ImportFrom) and (nodo.module or "").split(".")[0] == (
                    "cryptography"):
                malos.append((nombre, nodo.module))
            elif isinstance(nodo, ast.Attribute) and nodo.attr == "_clave":
                malos.append((nombre, ast.unparse(nodo)))
            elif isinstance(nodo, ast.Constant) and nodo.value in ("_clave", "cryptography"):
                malos.append((nombre, nodo.value))
    assert malos == []
    # Y el modulo no escribe nada en el registro: ni logging ni print.
    texto = (SRC / "correo" / "certificado.py").read_text(encoding="utf-8")
    assert not re.search(r"\blogging\b|\bprint\(", texto)
