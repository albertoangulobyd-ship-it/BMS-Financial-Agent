"""El lector de extractos CAMT.053 (ISO 20022), versiones .001.02 y .001.08 (spec §9).

Lee con xml.etree.ElementTree, que no va a buscar nada fuera del fichero, y
antes de leer rechaza cualquier declaracion (`<!DOCTYPE`, `<!ENTITY`...): un
extracto no las necesita, y son la puerta de las entidades externas y de las
bombas de entidades. Solo admite las dos versiones de la especificacion; otra
version se rechaza en vez de leerse a medias.

De cada extracto (Stmt) saca la cuenta, el numero de secuencia
(ElctrncSeqNb, o LglSeqNb), los saldos de apertura (OPBD, o PRCD) y de
cierre (CLBD) y sus apuntes. Cada transaccion (TxDtls) es un movimiento: un
apunte agrupado (una remesa de cobros o pagos) da tantos movimientos como
transacciones, con la referencia del apunte en `remesa`. Lo que se comprueba
al leer, porque un fichero que no cuadra esta incompleto o mal leido:

- las transacciones de un apunte agrupado suman el apunte;
- los apuntes contabilizados suman la diferencia entre el saldo de cierre y
  el de apertura.

Un apunte en otra moneda que el euro se lee con su literal y su moneda (X1);
no entra en ninguna suma. Los apuntes que no estan contabilizados (PDNG,
INFO) no son movimientos: se dicen como aviso.

Leer es puro: bytes en, registros canonicos fuera.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from ..almacen.unidades import sha256_bytes
from ..reloj import ZONA_EMPRESA
from .base import LoteLeido, Rechazo
from .canonico import ExtractoCanonico, MovimientoCanonico

VERSIONES = {
    "urn:iso:std:iso:20022:tech:xsd:camt.053.001.02": "001.02",
    "urn:iso:std:iso:20022:tech:xsd:camt.053.001.08": "001.08",
}
_IMPORTE = re.compile(r"[0-9]+(?:\.[0-9]{1,5})?")
_SIN_REFERENCIA = {"NOTPROVIDED", "NONREF", "NOTAVAILABLE"}


class FicheroNoAdmitido(ValueError):
    """Un fichero que no se lee: con declaraciones XML, de otra version o mal formado."""


class ExtractoNoValido(ValueError):
    """Un extracto que no cuadra o al que le falta lo imprescindible."""


# ------------------------------------------------------------ seguridad

def _texto_del_fichero(contenido: bytes) -> str:
    for codificacion in ("utf-8-sig", "utf-16"):
        try:
            return contenido.decode(codificacion)
        except UnicodeDecodeError:
            continue
    return contenido.decode("latin-1")


def comprobar_seguro(contenido: bytes) -> None:
    """Rechaza un XML con cualquier declaracion (`<!DOCTYPE`, `<!ENTITY`, `<!ELEMENT`...).

    Solo se admiten los comentarios y las secciones CDATA. Se mira en el texto
    ya decodificado (tambien UTF-16) y en los bytes tal cual, para que una
    codificacion rara no la esconda.
    """
    if re.search(rb"<!\s*(?:DOCTYPE|ENTITY|ELEMENT|ATTLIST|NOTATION)", contenido, re.IGNORECASE):
        raise FicheroNoAdmitido("el fichero trae una declaracion DOCTYPE o ENTITY: no se lee")
    texto = _texto_del_fichero(contenido)
    for encontrado in re.finditer(r"<!", texto):
        resto = texto[encontrado.start():encontrado.start() + 9]
        if not (resto.startswith("<!--") or resto.startswith("<![CDATA[")):
            raise FicheroNoAdmitido("el fichero trae una declaracion DOCTYPE o ENTITY: no se lee")


# ------------------------------------------------------------ el arbol

def _local(etiqueta: str) -> str:
    return etiqueta.rsplit("}", 1)[-1]


def _hijos(elemento: ET.Element | None, nombre: str) -> list[ET.Element]:
    if elemento is None:
        return []
    return [h for h in elemento if _local(h.tag) == nombre]


def _hijo(elemento: ET.Element | None, *ruta: str) -> ET.Element | None:
    for nombre in ruta:
        siguientes = _hijos(elemento, nombre)
        if not siguientes:
            return None
        elemento = siguientes[0]
    return elemento


def _primero(*elementos: ET.Element | None) -> ET.Element | None:
    """El primero que existe. Sin `or`: un elemento sin hijos es falso para Python."""
    return next((e for e in elementos if e is not None), None)


def _texto(elemento: ET.Element | None, *ruta: str) -> str | None:
    destino = _hijo(elemento, *ruta)
    if destino is None or destino.text is None:
        return None
    return destino.text.strip() or None


def _fecha(elemento: ET.Element | None) -> date | None:
    """Una fecha de un elemento que trae Dt o DtTm (o es el mismo una fecha)."""
    texto = _texto(elemento, "Dt") or _texto(elemento, "DtTm")
    if texto is None and elemento is not None and elemento.text:
        texto = elemento.text.strip() or None
    if texto is None:
        return None
    try:
        return date.fromisoformat(texto[:10])
    except ValueError:
        raise ExtractoNoValido(f"{texto!r} no es una fecha") from None


def _instante(texto: str | None) -> datetime | None:
    """La hora de creacion del fichero; sin zona, es la de la empresa."""
    if not texto:
        return None
    try:
        instante = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=ZoneInfo(ZONA_EMPRESA))
    return instante.astimezone(timezone.utc)


def _importe(elemento: ET.Element | None, donde: str) -> tuple[Decimal, str, str]:
    """El importe (sin signo), su moneda y su literal de un elemento Amt."""
    if elemento is None or not (elemento.text or "").strip():
        raise ExtractoNoValido(f"{donde}: falta el importe")
    texto = elemento.text.strip()
    if not _IMPORTE.fullmatch(texto):
        raise ExtractoNoValido(f"{donde}: {texto!r} no es un importe")
    moneda = (elemento.get("Ccy") or "").strip().upper()
    if len(moneda) != 3:
        raise ExtractoNoValido(f"{donde}: el importe {texto} no dice su moneda")
    return Decimal(texto), moneda, texto


def _signo(indicador: str | None, donde: str) -> int:
    if indicador == "CRDT":
        return 1
    if indicador == "DBIT":
        return -1
    raise ExtractoNoValido(f"{donde}: CdtDbtInd es {indicador!r}, ni CRDT ni DBIT")


# ------------------------------------------------------------ un extracto

def _saldos(stmt: ET.Element) -> dict[str, tuple[Decimal, date | None, str]]:
    salida: dict[str, tuple[Decimal, date | None, str]] = {}
    for saldo in _hijos(stmt, "Bal"):
        codigo = _texto(saldo, "Tp", "CdOrPrtry", "Cd") or _texto(saldo, "Tp", "CdOrPrtry",
                                                                    "Prtry")
        if codigo not in ("OPBD", "PRCD", "CLBD") or codigo in salida:
            continue
        importe, moneda, _literal = _importe(_hijo(saldo, "Amt"), f"saldo {codigo}")
        signo = _signo(_texto(saldo, "CdtDbtInd"), f"saldo {codigo}")
        salida[codigo] = (signo * importe, _fecha(_hijo(saldo, "Dt")), moneda)
    return salida


def _parte(transaccion: ET.Element, quien: str) -> tuple[str | None, str | None]:
    """El nombre y la cuenta de la contraparte: Cdtr de un cargo, Dbtr de un abono."""
    partes = _hijo(transaccion, "RltdPties")
    nombre = _texto(partes, quien, "Nm") or _texto(partes, quien, "Pty", "Nm")
    cuenta = (_texto(partes, f"{quien}Acct", "Id", "IBAN")
              or _texto(partes, f"{quien}Acct", "Id", "Othr", "Id"))
    return nombre, cuenta


def _referencia(texto: str | None) -> str | None:
    if texto is None or texto.strip().upper() in _SIN_REFERENCIA:
        return None
    return texto.strip()


def _concepto(*elementos: ET.Element | None) -> str | None:
    for elemento in elementos:
        if elemento is None:
            continue
        lineas = [h.text.strip() for h in _hijos(_hijo(elemento, "RmtInf"), "Ustrd")
                  if h.text and h.text.strip()]
        if lineas:
            return " ".join(lineas)
    for elemento in elementos:
        for etiqueta in ("AddtlTxInf", "AddtlNtryInf"):
            texto = _texto(elemento, etiqueta)
            if texto:
                return texto
    return None


def _transacciones(apunte: ET.Element) -> list[ET.Element]:
    return [t for detalle in _hijos(apunte, "NtryDtls") for t in _hijos(detalle, "TxDtls")]


def _movimientos_de(apunte: ET.Element, numero: int, cuenta: str,
                    posicion: int) -> list[MovimientoCanonico]:
    """Los movimientos de un apunte: uno por transaccion, o el apunte si no trae ninguna."""
    donde = f"apunte {numero}"
    importe, moneda, literal = _importe(_hijo(apunte, "Amt"), donde)
    signo = _signo(_texto(apunte, "CdtDbtInd"), donde)
    contable = _fecha(_hijo(apunte, "BookgDt"))
    if contable is None:
        raise ExtractoNoValido(f"{donde}: falta la fecha contable")
    valor = _fecha(_hijo(apunte, "ValDt"))
    ref_apunte = _texto(apunte, "AcctSvcrRef")
    transacciones = _transacciones(apunte) or [None]
    agrupado = len(transacciones) > 1
    importes: list[tuple[Decimal, str, str, int]] = []
    for indice, transaccion in enumerate(transacciones, start=1):
        cantidad = _primero(_hijo(transaccion, "Amt"),
                            _hijo(transaccion, "AmtDtls", "TxAmt", "Amt"),
                            _hijo(transaccion, "AmtDtls", "InstdAmt", "Amt"))
        if cantidad is None:
            if agrupado:
                raise ExtractoNoValido(f"{donde}: un apunte agrupado sin el importe de cada "
                                       "transaccion no se puede repartir")
            importes.append((importe, moneda, literal, signo))
            continue
        propio, moneda_tx, literal_tx = _importe(cantidad, f"{donde}, transaccion {indice}")
        indicador = _texto(transaccion, "CdtDbtInd")
        importes.append((propio, moneda_tx, literal_tx,
                         _signo(indicador, donde) if indicador else signo))
    if agrupado and all(m == moneda for _i, m, _l, _s in importes):
        if sum(s * i for i, _m, _l, s in importes) != signo * importe:
            raise ExtractoNoValido(f"{donde}: sus transacciones no suman el apunte "
                                   f"({literal} {moneda})")
    salida = []
    for indice, (transaccion, (cantidad, moneda_tx, literal_tx, signo_tx)) in enumerate(
            zip(transacciones, importes), start=1):
        quien = "Cdtr" if signo_tx < 0 else "Dbtr"
        nombre, cuenta_contraparte = _parte(transaccion, quien) if transaccion is not None else (
            None, None)
        referencias = _hijo(transaccion, "Refs") if transaccion is not None else None
        estructurada = _texto(transaccion, "RmtInf", "Strd", "CdtrRefInf", "Ref") if (
            transaccion is not None) else None
        salida.append(MovimientoCanonico(
            fila=posicion + indice - 1,
            crudo={"apunte": str(numero), "transaccion": str(indice)},
            cuenta_propia_iban=cuenta, fecha_contable=contable, fecha_valor=valor,
            importe=signo_tx * cantidad,
            importe_crudo=f"{'-' if signo_tx < 0 else ''}{literal_tx} {moneda_tx}",
            moneda=moneda_tx, contraparte_iban=cuenta_contraparte, contraparte_nombre=nombre,
            concepto=_concepto(transaccion, apunte),
            referencia_estructurada=_referencia(estructurada),
            referencia_e2e=_referencia(_texto(referencias, "EndToEndId")),
            ref_banco=_texto(referencias, "AcctSvcrRef") or ref_apunte,
            remesa=(ref_apunte or f"apunte {numero}") if agrupado else None))
    return salida


def _extracto(stmt: ET.Element, numero: int, version: str,
              avisos: list[str]) -> ExtractoCanonico:
    cuenta = _texto(stmt, "Acct", "Id", "IBAN")
    if cuenta is None:
        raise ExtractoNoValido("el extracto no dice la cuenta (Acct/Id/IBAN)")
    saldos = _saldos(stmt)
    apertura = saldos.get("OPBD") or saldos.get("PRCD")
    cierre = saldos.get("CLBD")
    moneda = (_texto(stmt, "Acct", "Ccy") or (cierre[2] if cierre else None) or "EUR").upper()
    secuencia_texto = _texto(stmt, "ElctrncSeqNb") or _texto(stmt, "LglSeqNb")
    secuencia = int(secuencia_texto) if secuencia_texto and secuencia_texto.isdigit() else None
    movimientos: list[MovimientoCanonico] = []
    suma, sumable = Decimal(0), True
    for orden, apunte in enumerate(_hijos(stmt, "Ntry"), start=1):
        estado_ = _hijo(apunte, "Sts")
        estado = (_texto(estado_, "Cd") or (estado_.text or "").strip()) if estado_ is not None \
            else "BOOK"
        if estado and estado != "BOOK":
            avisos.append(f"extracto {numero}, apunte {orden}: {estado}, sin contabilizar; no "
                          "entra")
            continue
        nuevos = _movimientos_de(apunte, orden, cuenta, len(movimientos) + 1)
        movimientos.extend(nuevos)
        for m in nuevos:
            if m.moneda != moneda:
                sumable = False
            suma += m.importe
    fechas = [m.fecha_contable for m in movimientos]
    rango = _hijo(stmt, "FrToDt")
    desde = _fecha(_hijo(rango, "FrDtTm")) if rango is not None else None
    hasta = _fecha(_hijo(rango, "ToDtTm")) if rango is not None else None
    desde = desde or (min(fechas) if fechas else (apertura[1] if apertura else None))
    hasta = hasta or (max(fechas) if fechas else (cierre[1] if cierre else None))
    con_saldos = apertura is not None and cierre is not None
    if con_saldos and sumable and apertura[0] + suma != cierre[0]:
        raise ExtractoNoValido(
            f"los apuntes suman {suma} y los saldos van de {apertura[0]} a {cierre[0]}: el "
            "extracto esta incompleto")
    if not sumable:
        avisos.append(f"extracto {numero}: trae apuntes en otra moneda; no se comprueba que "
                      "sumen los saldos")
    return ExtractoCanonico(
        fila=numero, crudo={"Id": _texto(stmt, "Id") or "", "IBAN": cuenta},
        cuenta_propia_iban=cuenta, identificador=_texto(stmt, "Id"), secuencia=secuencia,
        moneda=moneda, saldo_inicial=apertura[0] if apertura else None,
        saldo_final=cierre[0] if cierre else None,
        fecha_saldo_inicial=apertura[1] if apertura else None,
        fecha_saldo_final=cierre[1] if cierre else None, desde=desde, hasta=hasta,
        con_saldos=con_saldos, formato=f"camt053:{version}", movimientos=tuple(movimientos))


# ------------------------------------------------------------ el fichero

def version_de(contenido: bytes) -> str | None:
    """La version de un CAMT.053 admitido, o None si el fichero no lo es."""
    try:
        comprobar_seguro(contenido)
        raiz = ET.fromstring(contenido)
    except (FicheroNoAdmitido, ET.ParseError):
        return None
    espacio = raiz.tag[1:].split("}", 1)[0] if raiz.tag.startswith("{") else ""
    return VERSIONES.get(espacio)


def reconoce(contenido: bytes) -> bool:
    """Si los bytes parecen un XML (lo que decide si se lee como CAMT y no como MT940 o CSV)."""
    inicio = contenido.lstrip(b"\xef\xbb\xbf \t\r\n")[:200]
    return inicio.startswith(b"<")


def leer(contenido: bytes, nombre: str = "", *,
         exportado_en: datetime | None = None) -> LoteLeido:
    """El lote de un fichero CAMT.053. Lanza FicheroNoAdmitido si no se puede leer entero."""
    comprobar_seguro(contenido)
    try:
        raiz = ET.fromstring(contenido)
    except ET.ParseError as exc:
        raise FicheroNoAdmitido(f"{nombre or 'el fichero'} no es un XML bien formado: "
                                f"{exc}") from None
    espacio = raiz.tag[1:].split("}", 1)[0] if raiz.tag.startswith("{") else ""
    version = VERSIONES.get(espacio)
    if version is None or _local(raiz.tag) != "Document":
        raise FicheroNoAdmitido(f"{nombre or 'el fichero'} no es un CAMT.053 .001.02 ni "
                                f".001.08 ({espacio or 'sin espacio de nombres'})")
    informe = _hijo(raiz, "BkToCstmrStmt")
    if informe is None:
        raise FicheroNoAdmitido("no trae BkToCstmrStmt: no es un extracto")
    creado = _instante(_texto(informe, "GrpHdr", "CreDtTm"))
    extractos, rechazos, avisos = [], [], []
    for numero, stmt in enumerate(_hijos(informe, "Stmt"), start=1):
        try:
            extractos.append(_extracto(stmt, numero, version, avisos))
        except (ExtractoNoValido, ValueError) as exc:
            rechazos.append(Rechazo(numero, str(exc), {"Id": _texto(stmt, "Id") or "",
                                                       "IBAN": _texto(stmt, "Acct", "Id", "IBAN")
                                                       or ""}))
    if not extractos and not rechazos:
        raise FicheroNoAdmitido("el fichero no trae ningun extracto (Stmt)")
    desdes = [e.desde for e in extractos if e.desde]
    hastas = [e.hasta for e in extractos if e.hasta]
    return LoteLeido(
        fuente="banco", tipo="extracto", formato=f"camt053:{version}",
        fichero_sha256=sha256_bytes(contenido), mapeo_id=None, mapeo_sha256=None,
        exportado_en=creado or exportado_en, cubre_desde=min(desdes) if desdes else None,
        cubre_hasta=max(hastas) if hastas else None, completo=False,
        registros=tuple(extractos), rechazos=tuple(rechazos), avisos=tuple(avisos))
