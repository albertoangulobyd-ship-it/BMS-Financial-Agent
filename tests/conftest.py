"""Fixtures comunes de los tests de la V1.

- Ningun test escribe en el almacen de verdad: BMS_DB apunta siempre a una
  carpeta temporal, tambien en los tests que no piden almacen y ejecutan
  `extract` o el servidor, que ahora escriben en el.
- `reloj` es un reloj parado; `db` una base en memoria con todas las
  migraciones aplicadas y ese reloj; `almacen` la base mas una carpeta de
  documentos temporal. Los pasos siguientes construyen encima de estas.
- `pdfs_ejemplo` escribe los tres PDF del generador, cuyos hashes son los de
  las fixtures v1 01, 02 y 03.
- `tipado` (paso 2) es el almacen con las siete fixtures v1 importadas y
  convertidas en facturas tipadas; `persona(conn, nombre, *roles)` crea una
  persona con esos roles de permisos.ROLES_BASE.
"""

from __future__ import annotations

import importlib.util
import shutil
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from bms_agent.almacen import Almacen, abrir
from bms_agent.almacen.documentos import AlmacenDocumentos
from bms_agent.almacen.migrar import migrar
from bms_agent.reloj import RelojFijo

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES_V1 = RAIZ / "tests" / "fixtures" / "v1"
TARIFAS_V1 = FIXTURES_V1 / "tarifas.yaml"
GOLDEN = RAIZ / "tests" / "golden"
INSTANTE_FIJO = datetime(2026, 10, 14, 9, 30, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _almacen_aislado(tmp_path_factory, monkeypatch) -> Path:
    ruta = tmp_path_factory.mktemp("almacen") / "bms.sqlite3"
    monkeypatch.setenv("BMS_DB", str(ruta))
    return ruta


@pytest.fixture
def reloj() -> RelojFijo:
    return RelojFijo(INSTANTE_FIJO)


@pytest.fixture
def db(reloj):
    conn = abrir(":memory:", reloj=reloj)
    migrar(conn)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def almacen(db, tmp_path) -> Almacen:
    return Almacen(db, AlmacenDocumentos(tmp_path / "documentos"))


def _generador():
    ruta = RAIZ / "scripts" / "generar_facturas_ejemplo.py"
    spec = importlib.util.spec_from_file_location("generador_ejemplo", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def pdfs_ejemplo(tmp_path) -> Path:
    """Los tres PDF de ejemplo, en una carpeta propia del test."""
    generador = _generador()
    carpeta = tmp_path / "facturas"
    carpeta.mkdir()
    for nombre, lineas in (
        ("01-limpia.pdf", generador.FACTURA_LIMPIA),
        ("02-sin-kvk-btw-verlegd.pdf", generador.FACTURA_SIN_KVK),
        ("03-con-inyeccion.pdf", generador.FACTURA_CON_INYECCION),
    ):
        generador.write_pdf(carpeta / nombre, lineas)
    return carpeta


@pytest.fixture
def out_v1(tmp_path) -> Path:
    """Una copia de las siete extracciones v1, como si fueran el out/ de alguien."""
    destino = tmp_path / "out"
    destino.mkdir()
    for fichero in sorted(FIXTURES_V1.glob("*.json")):
        shutil.copy2(fichero, destino / fichero.name)
    return destino


@pytest.fixture
def tipado(almacen, out_v1) -> Almacen:
    """Las siete fixtures v1 en el almacen, ya tipadas (factura, lineas, imputaciones)."""
    from bms_agent.importadores.extracciones import importar_out
    from bms_agent.ingesta import tipar_pendientes

    importar_out(almacen, out_v1, None)
    assert {t.accion for t in tipar_pendientes(almacen.conn)} == {"creada"}
    return almacen


def persona(conn, nombre: str, *roles: str) -> int:
    """Una persona con roles de partida (administrador, administracion, consulta)."""
    from bms_agent import permisos

    permisos.asegurar_roles_base(conn)
    usuario_id = permisos.crear_usuario(conn, nombre)
    for rol in roles:
        permisos.asignar_rol(conn, usuario_id, rol)
    return usuario_id


def factura_de(conn, numero: str) -> int:
    return conn.execute("SELECT id FROM factura WHERE numero = ?", (numero,)).fetchone()[0]


# ------------------------------------------------------------ paso 17: la lectura pedida

def estimacion_lectura(nuevos: int = 2, ya_leidos: int = 1, *, alto: int = 60_000,
                       bajo: int = 50_000):
    """Una cuenta del lector hecha a mano, sin API: `nuevos` PDF nuevos (cada uno con su
    entrada contada y su horquilla, en millonesimas de dolar) y `ya_leidos` ya leidos."""
    from bms_agent import lectura

    documentos = [lectura.Contado(f"nueva-{i}.pdf", f"{i + 1:064x}", "nuevo", 4000, bajo, alto)
                  for i in range(nuevos)]
    documentos += [lectura.Contado(f"leida-{i}.pdf", f"{i + 100:064x}", "ya_leido")
                   for i in range(ya_leidos)]
    return lectura.Estimacion("claude-opus-5-5", "extract/x", "2", 1200, 6400, False,
                              "sin medir", documentos)


def lectura_esperando(conn, quien: int | None, estimacion=None) -> int:
    """Una lectura pedida desde la app por `quien` (o abierta en el lector, con None), tomada
    y contada por el lector con `estimacion`: espera el si."""
    from bms_agent import lectura

    if quien is not None:
        solicitud, _evento = lectura.pedir(conn, quien)
    tomada = lectura.tomar(conn, hay_pdf=True)
    solicitud = tomada.solicitud_id
    estado, _est = lectura.contar(conn, solicitud,
                                  lambda _antes: estimacion or estimacion_lectura())
    assert estado == "esperando_aprobacion"
    return solicitud


# ------------------------------------------------------------ paso 7: el banco

CUENTA_PROPIA = "NL60INGB0009988776"
OTRA_CUENTA_PROPIA = "NL93RABO0987654321"


def cuentas_propias(almacen, usuario_id: int, *ibans: str) -> None:
    """Carga config/empresa.yaml con estas cuentas propias (por defecto las dos de las
    fixtures del banco), como `politica cargar`."""
    from bms_agent import politica

    ibans = ibans or (CUENTA_PROPIA, OTRA_CUENTA_PROPIA)
    texto = (RAIZ / "config" / "empresa.yaml").read_text(encoding="utf-8").replace(
        "cuentas_propias: []", "cuentas_propias:\n" + "".join(f"  - {i}\n" for i in ibans))
    carpeta = almacen.documentos.raiz.parent / "politica-prueba"
    carpeta.mkdir(exist_ok=True)
    ruta = carpeta / "empresa.yaml"
    ruta.write_text(texto, encoding="utf-8")
    politica.cargar(almacen.conn, ruta, usuario_id)


def apunte(importe: str, fecha: str = "2026-10-12", *, iban: str | None = None,
           nombre: str | None = None, concepto: str | None = None, ref: str | None = None,
           e2e: str | None = None, moneda: str = "EUR", estado: str = "BOOK",
           detalles: tuple[dict, ...] = (), ref_banco: str | None = None) -> dict:
    """Un apunte de un CAMT.053: importe con signo (negativo, un cargo). Con `detalles`, una
    remesa: un apunte con varias transacciones (cada una, un apunte sin fecha)."""
    return {"importe": Decimal(importe), "fecha": fecha, "iban": iban, "nombre": nombre,
            "concepto": concepto, "ref": ref, "e2e": e2e, "moneda": moneda, "estado": estado,
            "detalles": tuple(detalles), "ref_banco": ref_banco}


def _tx(a: dict, cargo: bool, con_importe: bool) -> str:
    parte, cuenta = ("Cdtr", "CdtrAcct") if cargo else ("Dbtr", "DbtrAcct")
    trozos = ["<TxDtls>"]
    if a["e2e"]:
        trozos.append(f"<Refs><EndToEndId>{a['e2e']}</EndToEndId></Refs>")
    if con_importe:
        trozos.append(f"<AmtDtls><TxAmt><Amt Ccy=\"{a['moneda']}\">{abs(a['importe']):.2f}"
                      "</Amt></TxAmt></AmtDtls>")
    if a["nombre"] or a["iban"]:
        trozos.append("<RltdPties>")
        if a["nombre"]:
            trozos.append(f"<{parte}><Nm>{a['nombre']}</Nm></{parte}>")
        if a["iban"]:
            trozos.append(f"<{cuenta}><Id><IBAN>{a['iban']}</IBAN></Id></{cuenta}>")
        trozos.append("</RltdPties>")
    if a["concepto"] or a["ref"]:
        trozos.append("<RmtInf>")
        if a["concepto"]:
            trozos.append(f"<Ustrd>{a['concepto']}</Ustrd>")
        if a["ref"]:
            trozos.append(f"<Strd><CdtrRefInf><Ref>{a['ref']}</Ref></CdtrRefInf></Strd>")
        trozos.append("</RmtInf>")
    trozos.append("</TxDtls>")
    return "".join(trozos)


def camt053(*apuntes: dict, cuenta: str = CUENTA_PROPIA, inicial: str = "10000.00",
            final: str | None = None, secuencia: int | None = 1, version: str = "001.02",
            identificador: str = "STMT-1", desde: str = "2026-10-12",
            hasta: str = "2026-10-13") -> bytes:
    """Un CAMT.053 de prueba. El saldo final, si no se da, es el inicial mas los apuntes
    contabilizados en euros (el extracto cuadra)."""
    if final is None:
        final = str(Decimal(inicial) + sum(
            (a["importe"] for a in apuntes if a["estado"] == "BOOK" and a["moneda"] == "EUR"),
            Decimal(0)))

    def saldo(codigo: str, importe: str, dia: str) -> str:
        valor = Decimal(importe)
        return (f"<Bal><Tp><CdOrPrtry><Cd>{codigo}</Cd></CdOrPrtry></Tp>"
                f"<Amt Ccy=\"EUR\">{abs(valor):.2f}</Amt>"
                f"<CdtDbtInd>{'DBIT' if valor < 0 else 'CRDT'}</CdtDbtInd>"
                f"<Dt><Dt>{dia}</Dt></Dt></Bal>")

    entradas = []
    for i, a in enumerate(apuntes, start=1):
        cargo = a["importe"] < 0
        txs = ([_tx(d, cargo, True) for d in a["detalles"]] if a["detalles"]
               else [_tx(a, cargo, False)])
        lote = f"<Btch><NbOfTxs>{len(a['detalles'])}</NbOfTxs></Btch>" if a["detalles"] else ""
        entradas.append(
            f"<Ntry><Amt Ccy=\"{a['moneda']}\">{abs(a['importe']):.2f}</Amt>"
            f"<CdtDbtInd>{'DBIT' if cargo else 'CRDT'}</CdtDbtInd><Sts>{a['estado']}</Sts>"
            f"<BookgDt><Dt>{a['fecha']}</Dt></BookgDt>"
            f"<AcctSvcrRef>{a['ref_banco'] or f'{identificador}-{i}'}</AcctSvcrRef>"
            f"<NtryDtls>{lote}{''.join(txs)}</NtryDtls></Ntry>")
    secuencia_xml = "" if secuencia is None else f"<ElctrncSeqNb>{secuencia}</ElctrncSeqNb>"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.{version}"><BkToCstmrStmt>'
        f"<GrpHdr><MsgId>{identificador}</MsgId><CreDtTm>{hasta}T18:00:00</CreDtTm></GrpHdr>"
        f"<Stmt><Id>{identificador}</Id>{secuencia_xml}"
        f"<FrToDt><FrDtTm>{desde}T00:00:00</FrDtTm><ToDtTm>{hasta}T23:59:59</ToDtTm></FrToDt>"
        f"<Acct><Id><IBAN>{cuenta}</IBAN></Id><Ccy>EUR</Ccy></Acct>"
        f"{saldo('OPBD', inicial, desde)}{saldo('CLBD', final, hasta)}"
        f"{''.join(entradas)}</Stmt></BkToCstmrStmt></Document>").encode("utf-8")


def importar_camt(almacen, usuario_id: int, contenido: bytes, nombre: str = "extracto.xml"):
    """Importa un CAMT.053 como lo haria `bms-agent importar banco extracto`."""
    from bms_agent.importadores.registrar import importar_fichero

    ruta = almacen.documentos.raiz.parent / nombre
    ruta.write_bytes(contenido)
    return importar_fichero(almacen, "banco", "extracto", ruta, lanzado_por=usuario_id)
