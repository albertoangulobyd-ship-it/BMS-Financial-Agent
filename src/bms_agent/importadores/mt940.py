"""El lector de extractos MT940, con un perfil del campo :86: por banco (spec §9).

MT940 es el mismo para todos en lo de fuera: `:20:` abre un extracto, `:25:`
dice la cuenta, `:28C:` su numero (y secuencia), `:60F:` el saldo de
apertura, cada `:61:` un apunte y `:62F:` el saldo de cierre. Lo de dentro
del `:86:` (quien es la contraparte, su cuenta, el concepto, la referencia)
cada banco lo escribe a su manera: por eso hay un perfil para ING, ABN AMRO
y Rabobank, que dice que etiquetas (/CNTP/, /NAME/, /REMI/...) busca y como
lee cada una. El perfil se elige por el banco de la cuenta del extracto
(INGB, ABNA, RABO), o se pide (`mt940:ing`). Sin etiquetas que reconozca, el
`:86:` entero es el concepto.

Como en CAMT, lo que no cuadra no entra: los apuntes tienen que sumar la
diferencia entre el saldo de cierre y el de apertura. MT940 no dice cuando
se saco el fichero; la frescura (Z1) se mide con la fecha que da quien lo
importa (la del fichero, por defecto).

Leer es puro: bytes en, registros canonicos fuera.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from ..almacen.unidades import sha256_bytes
from ..reglas.bancaria import validar_iban
from .base import LoteLeido, Rechazo
from .camt053 import ExtractoNoValido, FicheroNoAdmitido
from .canonico import ExtractoCanonico, MovimientoCanonico

_ETIQUETA = re.compile(r"^:(\d{2}[A-Z]?):(.*)$")
_SALDO = re.compile(r"^(?P<signo>[CD])(?P<fecha>\d{6})(?P<moneda>[A-Z]{3})(?P<importe>\d+,\d*)$")
_LINEA = re.compile(
    r"^(?P<valor>\d{6})(?P<contable>\d{4})?(?P<marca>RC|RD|C|D)(?P<fondos>[A-Z])?"
    r"(?P<importe>\d+,\d*)(?P<tipo>[NSF][A-Z0-9]{3})(?P<referencia>.*?)(?://(?P<banco>.*))?$")
_CANDIDATO_IBAN = re.compile(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}")
_SIN_REFERENCIA = {"NOTPROVIDED", "NONREF", "NOTAVAILABLE", ""}


@dataclass(frozen=True)
class Perfil:
    """Como lee un banco su campo :86:."""

    nombre: str
    etiquetas: tuple[str, ...]


PERFILES = {
    "ing": Perfil("ing", ("CNTP", "REMI", "EREF", "MARF", "CSID", "BENM", "ORDP", "PURP", "ULTC",
                          "ULTD", "ULTB", "RTRN", "BUSP", "PREF", "IREF", "CREF", "ISDT")),
    "abn": Perfil("abn", ("TRTP", "IBAN", "BIC", "NAME", "REMI", "EREF", "CSID", "MARF", "ORDP",
                          "BENM", "ADDR", "PREF", "ISDT")),
    "rabobank": Perfil("rabobank", ("EREF", "MARF", "CSID", "CNTP", "NAME", "ADDR", "REMI", "ISDT",
                                    "ORDP", "BENM", "ULTD", "ULTB", "PREF", "RTRN", "PURP")),
    "generico": Perfil("generico", ()),
}
# El perfil por el codigo del banco en la cuenta del extracto.
_POR_BANCO = {"INGB": "ing", "ABNA": "abn", "RABO": "rabobank"}


# ------------------------------------------------------------ el fichero en campos

def _decodificar(contenido: bytes) -> str:
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            return contenido.decode(codificacion)
        except UnicodeDecodeError:
            continue
    return contenido.decode("latin-1")


def _campos(texto: str) -> list[list[tuple[str, str]]]:
    """Los extractos del fichero, cada uno como la lista de sus campos (etiqueta, valor).

    Lo que va antes del primer :20: (la cabecera de ING, el sobre {1:...}{2:...})
    no es de ningun extracto. Una linea que no empieza por etiqueta sigue el
    campo de antes; "-}" o "-" cierra el mensaje.
    """
    extractos: list[list[tuple[str, str]]] = []
    actual: list[tuple[str, str]] | None = None
    for linea in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        limpia = linea.rstrip()
        if limpia.startswith("{4:"):
            limpia = limpia[3:]
        encontrada = _ETIQUETA.match(limpia)
        if encontrada:
            etiqueta, valor = encontrada.groups()
            if etiqueta == "20":
                actual = []
                extractos.append(actual)
            if actual is not None:
                actual.append((etiqueta, valor))
        elif limpia in ("-", "-}"):
            actual = None
        elif actual is not None and actual and limpia:
            etiqueta, valor = actual[-1]
            actual[-1] = (etiqueta, f"{valor}\n{limpia}")
    return extractos


def _importe(texto: str) -> Decimal:
    entero, _, decimales = texto.partition(",")
    return Decimal(f"{int(entero)}.{decimales or '0'}")


def _fecha(aammdd: str) -> date:
    return date(2000 + int(aammdd[:2]), int(aammdd[2:4]), int(aammdd[4:6]))


def _saldo(valor: str, donde: str) -> tuple[Decimal, date, str]:
    encontrado = _SALDO.match(valor.strip())
    if not encontrado:
        raise ExtractoNoValido(f"{donde}: {valor!r} no es un saldo")
    importe = _importe(encontrado["importe"])
    signo = -1 if encontrado["signo"] == "D" else 1
    return signo * importe, _fecha(encontrado["fecha"]), encontrado["moneda"]


def iban_de(texto: str) -> str | None:
    """El IBAN de un campo :25: ("NL69INGB0123456789EUR", "INGBNL2A/NL69...", con espacios)."""
    compacto = "".join(texto.split()).upper()
    for candidato in _CANDIDATO_IBAN.findall(compacto):
        for largo in range(len(candidato), 14, -1):
            if validar_iban(candidato[:largo]):
                return candidato[:largo]
    return None


# ------------------------------------------------------------ el :86:

def _por_etiquetas(texto: str, etiquetas: tuple[str, ...]) -> dict[str, str]:
    """Las etiquetas /XXXX/ que reconoce el perfil, con lo que va hasta la siguiente."""
    if not etiquetas:
        return {}
    patron = re.compile(r"/(" + "|".join(etiquetas) + r")/")
    encontradas = list(patron.finditer(texto))
    salida: dict[str, str] = {}
    for actual, siguiente in zip(encontradas, [*encontradas[1:], None]):
        fin = siguiente.start() if siguiente is not None else len(texto)
        valor = texto[actual.end():fin]
        salida.setdefault(actual.group(1), valor.strip().rstrip("/").strip())
    return salida


def _referencia(texto: str | None) -> str | None:
    if texto is None:
        return None
    limpio = texto.strip().strip("/").strip()
    return None if limpio.upper() in _SIN_REFERENCIA else limpio


@dataclass(frozen=True)
class Info:
    contraparte_iban: str | None = None
    contraparte_nombre: str | None = None
    concepto: str | None = None
    referencia_estructurada: str | None = None
    referencia_e2e: str | None = None


def leer_86(texto: str, perfil: Perfil, complementario: str = "") -> Info:
    """Lo que dice un :86: con el perfil de su banco.

    /CNTP/ (ING, Rabobank) es cuenta/BIC/nombre/ciudad; /IBAN/ y /NAME/ (ABN
    AMRO, Rabobank), la cuenta y el nombre sueltos. /REMI/ es el concepto:
    "USTD//texto" libre o "STRD/CUR/referencia" estructurada. Rabobank deja a
    veces la cuenta de la contraparte en la linea complementaria del :61:.
    """
    unido = "".join(texto.split("\n"))
    campos = _por_etiquetas(unido, perfil.etiquetas)
    if not campos:
        return Info(concepto=" ".join(texto.split()) or None)
    iban = nombre = concepto = estructurada = None
    if "CNTP" in campos:
        partes = campos["CNTP"].split("/")
        iban = partes[0] if partes else None
        nombre = partes[2] if len(partes) > 2 else None
    iban = campos.get("IBAN") or iban
    nombre = campos.get("NAME") or nombre
    remi = campos.get("REMI")
    if remi is not None:
        if remi.upper().startswith("USTD//"):
            concepto = remi[6:]
        elif remi.upper().startswith("STRD/CUR/"):
            estructurada = remi[9:]
        elif remi.upper().startswith("STRD/"):
            estructurada = remi[5:]
        else:
            concepto = remi
    if not iban and complementario:
        iban = iban_de(complementario)
    return Info(contraparte_iban=(iban or "").strip() or None,
                contraparte_nombre=(nombre or "").strip() or None,
                concepto=(concepto or "").strip() or None,
                referencia_estructurada=_referencia(estructurada),
                referencia_e2e=_referencia(campos.get("EREF")))


# ------------------------------------------------------------ un extracto

def _apunte(valor: str, numero: int) -> dict:
    primera, _, complementario = valor.partition("\n")
    encontrado = _LINEA.match(primera.strip())
    if not encontrado:
        raise ExtractoNoValido(f"apunte {numero}: {primera!r} no es una linea :61:")
    fecha_valor = _fecha(encontrado["valor"])
    contable = fecha_valor
    if encontrado["contable"]:
        mes, dia = int(encontrado["contable"][:2]), int(encontrado["contable"][2:])
        ano = fecha_valor.year
        if mes - fecha_valor.month > 6:
            ano -= 1
        elif fecha_valor.month - mes > 6:
            ano += 1
        contable = date(ano, mes, dia)
    marca = encontrado["marca"]
    signo = 1 if marca in ("C", "RD") else -1
    importe = _importe(encontrado["importe"])
    return {"valor": fecha_valor, "contable": contable, "importe": signo * importe,
            "crudo": f"{marca}{encontrado['importe']}",
            "referencia": _referencia(encontrado["referencia"]),
            "banco": _referencia(encontrado["banco"]), "complementario": complementario}


def _extracto(campos: list[tuple[str, str]], numero: int, perfil_pedido: str | None,
              avisos: list[str]) -> ExtractoCanonico:
    valores: dict[str, str] = {}
    apuntes: list[tuple[str, str | None]] = []
    for etiqueta, valor in campos:
        if etiqueta == "61":
            apuntes.append((valor, None))
        elif etiqueta == "86" and apuntes and apuntes[-1][1] is None:
            apuntes[-1] = (apuntes[-1][0], valor)
        elif etiqueta not in valores:
            valores[etiqueta] = valor
    cuenta = iban_de(valores.get("25", ""))
    if cuenta is None:
        raise ExtractoNoValido(f"el extracto {numero} no dice su cuenta como IBAN (:25:)")
    perfil = PERFILES[perfil_pedido or _POR_BANCO.get(cuenta[4:8], "generico")]
    apertura = _saldo(valores.get("60F") or valores.get("60M") or "", ":60F:")
    cierre = _saldo(valores.get("62F") or valores.get("62M") or "", ":62F:")
    numero_extracto = (valores.get("28C") or valores.get("28") or "").split("/")[0].strip()
    secuencia = int(numero_extracto) if numero_extracto.isdigit() else None
    movimientos: list[MovimientoCanonico] = []
    for indice, (linea, info86) in enumerate(apuntes, start=1):
        apunte = _apunte(linea, indice)
        info = leer_86(info86 or "", perfil, apunte["complementario"])
        movimientos.append(MovimientoCanonico(
            fila=indice, crudo={"61": linea, "86": info86 or ""},
            cuenta_propia_iban=cuenta, fecha_contable=apunte["contable"],
            fecha_valor=apunte["valor"], importe=apunte["importe"],
            importe_crudo=apunte["crudo"], moneda=cierre[2],
            contraparte_iban=info.contraparte_iban, contraparte_nombre=info.contraparte_nombre,
            concepto=info.concepto, referencia_estructurada=info.referencia_estructurada,
            referencia_e2e=info.referencia_e2e or apunte["referencia"],
            ref_banco=apunte["banco"]))
    suma = sum((m.importe for m in movimientos), Decimal(0))
    if apertura[0] + suma != cierre[0]:
        raise ExtractoNoValido(
            f"los apuntes suman {suma} y los saldos van de {apertura[0]} a {cierre[0]}: el "
            "extracto esta incompleto")
    if perfil.nombre == "generico":
        avisos.append(f"extracto {numero}: banco sin perfil de :86:; el concepto va entero")
    fechas = [m.fecha_contable for m in movimientos]
    return ExtractoCanonico(
        fila=numero, crudo={"20": valores.get("20", ""), "25": valores.get("25", "")},
        cuenta_propia_iban=cuenta, identificador=(valores.get("20") or "").strip() or None,
        secuencia=secuencia, moneda=cierre[2], saldo_inicial=apertura[0],
        saldo_final=cierre[0], fecha_saldo_inicial=apertura[1], fecha_saldo_final=cierre[1],
        desde=min(fechas) if fechas else apertura[1], hasta=max(fechas) if fechas else cierre[1],
        con_saldos=True, formato=f"mt940:{perfil.nombre}", movimientos=tuple(movimientos))


def reconoce(contenido: bytes) -> bool:
    return re.search(rb"(?m)^:20:", contenido) is not None and (
        re.search(rb"(?m)^:61:", contenido) is not None
        or re.search(rb"(?m)^:62[FM]:", contenido) is not None)


def leer(contenido: bytes, nombre: str = "", *, exportado_en: datetime | None = None,
         perfil: str | None = None) -> LoteLeido:
    """El lote de un fichero MT940. `perfil` fuerza el del :86: (ing, abn, rabobank)."""
    if perfil is not None and perfil not in PERFILES:
        raise FicheroNoAdmitido(f"no hay perfil MT940 {perfil!r}: {', '.join(sorted(PERFILES))}")
    bloques = _campos(_decodificar(contenido))
    if not bloques:
        raise FicheroNoAdmitido(f"{nombre or 'el fichero'} no trae ningun extracto MT940 (:20:)")
    extractos, rechazos, avisos = [], [], []
    for numero, campos in enumerate(bloques, start=1):
        try:
            extractos.append(_extracto(campos, numero, perfil, avisos))
        except (ExtractoNoValido, ValueError) as exc:
            rechazos.append(Rechazo(numero, str(exc), {etiqueta: valor for etiqueta, valor in
                                                       campos if etiqueta in ("20", "25")}))
    formatos = sorted({e.formato for e in extractos}) or [f"mt940:{perfil or 'generico'}"]
    desdes = [e.desde for e in extractos if e.desde]
    hastas = [e.hasta for e in extractos if e.hasta]
    return LoteLeido(
        fuente="banco", tipo="extracto", formato=formatos[0],
        fichero_sha256=sha256_bytes(contenido), mapeo_id=None, mapeo_sha256=None,
        exportado_en=exportado_en, cubre_desde=min(desdes) if desdes else None,
        cubre_hasta=max(hastas) if hastas else None, completo=False,
        registros=tuple(extractos), rechazos=tuple(rechazos), avisos=tuple(avisos))
