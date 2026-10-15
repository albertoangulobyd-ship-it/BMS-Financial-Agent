"""Los extractos del banco (paso 7): CAMT.053, MT940, los CSV del banco y los pagos de Exact.

Puertas del paso 7 que viven aqui:

- CAMT.053 .001.02 y .001.08, con un apunte agrupado: cada TxDtls es un
  movimiento, y lo que no cuadra no entra;
- un XML con DOCTYPE o ENTITY no se lee (ni deja una importacion);
- un extracto de una cuenta que no es de BM Support BV no entra;
- un movimiento en otra moneda que el euro entra con su literal y da X1;
- un movimiento que ya estaba no entra otra vez, y dos iguales en el mismo
  extracto son dos (cuenta su posicion);
- MT940 con el :86: de ING, ABN AMRO y Rabobank;
- los CSV del banco entran "sin saldos" y K6 no los mira;
- los pagos de Exact (todo o nada; la fila de una factura que no esta, Z2).
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest
from conftest import (
    CUENTA_PROPIA,
    OTRA_CUENTA_PROPIA,
    RAIZ,
    apunte,
    camt053,
    cuentas_propias,
    importar_camt,
    persona,
)

from bms_agent import campos, hallazgos
from bms_agent.almacen.evidencia import verificar_evidencia
from bms_agent.importadores import banco, camt053 as lector_camt, mt940
from bms_agent.importadores.camt053 import FicheroNoAdmitido
from bms_agent.importadores.registrar import importar_fichero

BANCO = RAIZ / "tests" / "fixtures" / "banco"
IMPORTACION = RAIZ / "tests" / "fixtures" / "importacion"
CUENTA_AJENA = "NL07ABNA0555666777"


@pytest.fixture
def ana(almacen) -> int:
    """Ana lo puede todo y BM Support BV tiene sus dos cuentas en config/empresa.yaml."""
    usuario = persona(almacen.conn, "Ana", "administrador")
    cuentas_propias(almacen, usuario)
    return usuario


def _movimientos(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM movimiento_bancario ORDER BY id").fetchall()


def _abiertos(conn, regla: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM hallazgo WHERE regla = ? AND estado = 'abierto' "
                        "ORDER BY id", (regla,)).fetchall()


# ------------------------------------------------------------ CAMT.053

def test_camt_001_02_cada_transaccion_de_un_apunte_agrupado_es_un_movimiento() -> None:
    lote = lector_camt.leer((BANCO / "camt053-001.02.xml").read_bytes(), "a.xml")
    assert (lote.fuente, lote.tipo, lote.formato) == ("banco", "extracto", "camt053:001.02")
    [extracto] = lote.registros
    assert (extracto.cuenta_propia_iban, extracto.identificador, extracto.secuencia) == (
        CUENTA_PROPIA, "STMT-101", 101)
    assert (extracto.saldo_inicial, extracto.saldo_final, extracto.con_saldos) == (
        Decimal("10000.00"), Decimal("4923.31"), True)
    assert (extracto.desde, extracto.hasta) == (date(2026, 10, 12), date(2026, 10, 13))
    # Cuatro apuntes contabilizados y uno pendiente; el agrupado (2173,40) son dos.
    vistos = [(m.importe, m.contraparte_iban, m.contraparte_nombre, m.concepto, m.remesa)
              for m in extracto.movimientos]
    assert vistos == [
        (Decimal("-2902.79"), "NL02ABNA0123456789", "Bouwtechniek Van Dijk BV",
         "Factuur 2026-4471", None),
        (Decimal("-1520.00"), "NL44RABO0123456789", "J. de Vries", "2026-018", "ING-0002"),
        (Decimal("-653.40"), "NL03RABO0312456789", "Loodgietersbedrijf Smit",
         "Factuur 2026-112", "ING-0002"),
        (Decimal("-0.50"), None, None, "Kosten zakelijk betalen", None),
    ]
    assert [m.referencia_e2e for m in extracto.movimientos] == ["E2E-4471", "E2E-018", None,
                                                               None]
    assert any("PDNG" in aviso for aviso in lote.avisos)
    assert lote.exportado_en is not None


def test_camt_001_08_lee_los_cobros_agrupados_y_la_referencia_estructurada() -> None:
    lote = lector_camt.leer((BANCO / "camt053-001.08.xml").read_bytes(), "b.xml")
    assert lote.formato == "camt053:001.08"
    [extracto] = lote.registros
    assert (extracto.secuencia, extracto.saldo_inicial, extracto.saldo_final) == (
        102, Decimal("4923.31"), Decimal("5823.31"))
    vistos = [(m.importe, m.contraparte_iban, m.referencia_estructurada, m.remesa is not None)
              for m in extracto.movimientos]
    assert vistos == [
        (Decimal("-600.00"), "NL67INGB0006543210", None, False),
        (Decimal("1000.00"), "NL39RABO0300065264", "RF18539007547034", True),
        (Decimal("500.00"), "NL39RABO0300065264", None, True),
    ]


def test_las_dos_fixtures_entran_y_quedan_como_evidencia(almacen, ana) -> None:
    conn = almacen.conn
    for nombre in ("camt053-001.02.xml", "camt053-001.08.xml"):
        resultado = importar_fichero(almacen, "banco", "extracto", BANCO / nombre,
                                     lanzado_por=ana)
        [lote] = resultado.lotes
        assert (lote.estado, lote.rechazos) == ("aceptada", [])
    extractos = conn.execute("SELECT secuencia, con_saldos, entradas, formato FROM "
                             "extracto_bancario ORDER BY id").fetchall()
    assert [tuple(e) for e in extractos] == [(101, 1, 4, "camt053:001.02"),
                                             (102, 1, 3, "camt053:001.08")]
    movimientos = _movimientos(conn)
    assert [m["importe_cent"] for m in movimientos] == [-290279, -152000, -65340, -50, -60000,
                                                       100000, 50000]
    assert [m["posicion"] for m in movimientos] == [1, 2, 3, 4, 1, 2, 3]
    # La cadena encadena: ni K6 ni nada que diga que falta un extracto.
    assert _abiertos(conn, "K6") == []
    assert verificar_evidencia(conn) == []
    assert campos.verificar_controladas(conn) == []
    assert hallazgos.verificar(conn) == []
    # Y la evidencia es evidencia: ni se cambia ni se borra.
    with pytest.raises(sqlite3.IntegrityError, match="evidencia"):
        conn.execute("UPDATE movimiento_bancario SET importe_cent = 1 WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError, match="evidencia"):
        conn.execute("DELETE FROM extracto_bancario")


def test_un_movimiento_cambiado_por_detras_se_ve_al_verificar(almacen, ana) -> None:
    conn = almacen.conn
    importar_fichero(almacen, "banco", "extracto", BANCO / "camt053-001.02.xml", lanzado_por=ana)
    conn.execute("DROP TRIGGER movimiento_bancario_sin_update")
    conn.execute("UPDATE movimiento_bancario SET contraparte_iban = 'NL91ABNA0417164300' "
                 "WHERE id = 1")
    problemas = verificar_evidencia(conn)
    assert any("movimiento_bancario 1" in p and "contraparte_iban" in p for p in problemas)


def test_un_apunte_agrupado_que_no_suman_sus_transacciones_no_entra(almacen, ana) -> None:
    contenido = camt053(apunte("-100.00", detalles=(
        apunte("-60.00", iban="NL44RABO0123456789", concepto="uno"),
        apunte("-30.00", iban="NL03RABO0312456789", concepto="dos"))), final="9900.00")
    lote = lector_camt.leer(contenido)
    assert lote.registros == () and "no suman el apunte" in lote.rechazos[0].motivo
    [resultado] = importar_camt(almacen, ana, contenido).lotes
    assert resultado.estado == "rechazada"
    assert _movimientos(almacen.conn) == []


def test_un_extracto_cuyos_apuntes_no_dan_los_saldos_no_entra(almacen, ana) -> None:
    contenido = camt053(apunte("-100.00", iban="NL44RABO0123456789"), final="9950.00")
    [resultado] = importar_camt(almacen, ana, contenido).lotes
    assert resultado.estado == "rechazada"
    assert "incompleto" in resultado.rechazos[0].motivo
    assert almacen.conn.execute("SELECT count(*) FROM extracto_bancario").fetchone()[0] == 0


@pytest.mark.parametrize("cabecera", [
    '<!DOCTYPE Document [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;">]>',
    '<!DOCTYPE Document SYSTEM "file:///etc/passwd">',
    '<!DOCTYPE Document [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>',
    '<!ENTITY suelta "x">',
    '<!doctype Document>',
    '<! DOCTYPE Document>',
], ids=["bomba", "dtd-externo", "xxe", "entity", "minusculas", "con-espacio"])
def test_un_xml_con_doctype_o_entity_no_se_lee(almacen, ana, cabecera) -> None:
    conn = almacen.conn
    limpio = camt053(apunte("-10.00", iban="NL44RABO0123456789"))
    declaracion, cuerpo = limpio.split(b"\n", 1)
    contenido = declaracion + b"\n" + cabecera.encode() + b"\n" + cuerpo
    with pytest.raises(FicheroNoAdmitido, match="DOCTYPE o ENTITY"):
        lector_camt.leer(contenido)
    assert lector_camt.version_de(contenido) is None
    with pytest.raises(FicheroNoAdmitido):
        importar_camt(almacen, ana, contenido)
    # Ni una importacion a medias: no se llego a abrir.
    assert conn.execute("SELECT count(*) FROM importacion WHERE fuente = 'banco'"
                        ).fetchone()[0] == 0


def test_un_doctype_en_utf16_tambien_se_ve() -> None:
    texto = ('<?xml version="1.0" encoding="UTF-16"?>\n<!DOCTYPE d [<!ENTITY x "y">]>\n'
             '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"/>')
    with pytest.raises(FicheroNoAdmitido):
        lector_camt.comprobar_seguro(texto.encode("utf-16"))
    # Un comentario y un CDATA si se admiten.
    lector_camt.comprobar_seguro(b"<?xml version='1.0'?><!-- hola --><a><![CDATA[x]]></a>")


def test_otra_version_de_camt_no_se_lee_a_medias() -> None:
    contenido = camt053(apunte("-10.00")).replace(b"camt.053.001.02", b"camt.053.001.04")
    with pytest.raises(FicheroNoAdmitido, match="001.02"):
        lector_camt.leer(contenido)


def test_un_extracto_de_una_cuenta_que_no_es_de_bm_support_no_entra(almacen, ana) -> None:
    conn = almacen.conn
    [resultado] = importar_camt(almacen, ana, camt053(
        apunte("-10.00", iban="NL44RABO0123456789"), cuenta=CUENTA_AJENA)).lotes
    assert resultado.estado == "rechazada"
    assert [r.codigo for r in resultado.rechazos] == ["cuenta_ajena"]
    assert CUENTA_AJENA in resultado.rechazos[0].motivo
    assert conn.execute("SELECT count(*) FROM extracto_bancario").fetchone()[0] == 0
    # Con dos extractos en el fichero y uno ajeno, tampoco entra el bueno.
    dos = camt053(apunte("-10.00")).replace(
        b"</Stmt>", b"</Stmt>" + camt053(apunte("-5.00"), cuenta=CUENTA_AJENA).split(
            b"<Stmt>", 1)[1].split(b"</Stmt>", 1)[0].join([b"<Stmt>", b"</Stmt>"]), 1)
    [resultado] = importar_camt(almacen, ana, dos, "dos.xml").lotes
    assert resultado.estado == "rechazada"
    assert conn.execute("SELECT count(*) FROM movimiento_bancario").fetchone()[0] == 0


def test_sin_cuentas_propias_en_la_politica_no_entra_ningun_extracto(almacen) -> None:
    ana = persona(almacen.conn, "Ana", "administrador")
    [resultado] = importar_camt(almacen, ana, camt053(apunte("-10.00"))).lotes
    assert resultado.estado == "rechazada"
    assert "cuentas propias" in resultado.rechazos[0].motivo


def test_un_movimiento_en_otra_moneda_entra_con_su_literal_y_da_x1(almacen, ana) -> None:
    conn = almacen.conn
    importar_camt(almacen, ana, camt053(
        apunte("-2902.79", iban="NL02ABNA0123456789", concepto="Factuur 2026-4471"),
        apunte("-250.00", "2026-10-13", iban="GB29NWBK60161331926819", nombre="Northwind",
               concepto="Invoice NW-2026-0042", moneda="USD")))
    usd = conn.execute("SELECT * FROM movimiento_bancario WHERE moneda = 'USD'").fetchone()
    assert (usd["importe_cent"], usd["importe_crudo"]) == (None, "-250.00 USD")
    [x1] = _abiertos(conn, "X1")
    assert (x1["tabla"], x1["fila_id"], x1["severidad"]) == ("movimiento", usd["id"], "bloqueo")
    assert "USD" in x1["detalle"]


def test_los_movimientos_repetidos_no_entran_y_dos_iguales_son_dos(almacen, ana) -> None:
    conn = almacen.conn
    # Dos comisiones iguales del mismo dia: la misma referencia del banco y todo lo demas.
    comision = apunte("-0.50", "2026-10-13", concepto="Kosten zakelijk betalen",
                      ref_banco="ING-0003")
    primero = camt053(comision, comision, identificador="STMT-1", secuencia=1)
    [lote] = importar_camt(almacen, ana, primero, "uno.xml").lotes
    assert lote.estado == "aceptada"
    huellas = [m["huella"] for m in _movimientos(conn)]
    assert len(huellas) == 2 and len(set(huellas)) == 2
    # El mismo fichero otra vez: ya importado.
    [otra_vez] = importar_camt(almacen, ana, primero, "uno-otra-vez.xml").lotes
    assert otra_vez.repetida
    # Un extracto que se solapa: las dos comisiones ya estaban, la tercera es nueva.
    solapado = camt053(comision, comision, comision, identificador="STMT-1b", secuencia=1,
                       inicial="10000.00")
    [lote] = importar_camt(almacen, ana, solapado, "solapado.xml").lotes
    assert lote.estado == "aceptada"
    assert any("2 movimiento(s)" in a and "ya estaban" in a for a in lote.avisos)
    assert len(_movimientos(conn)) == 3
    assert verificar_evidencia(conn) == []


def test_simular_no_escribe_nada(almacen, ana) -> None:
    conn = almacen.conn
    ruta = almacen.documentos.raiz.parent / "simulado.xml"
    ruta.write_bytes((BANCO / "camt053-001.02.xml").read_bytes())
    resultado = banco.importar_extracto(almacen, ruta, lanzado_por=ana, simular=True)
    assert resultado.simulada and resultado.lotes[0].estado == "aceptada"
    assert len(resultado.lotes[0].nuevos) == 5
    for tabla in ("importacion WHERE fuente = 'banco'", "extracto_bancario",
                  "movimiento_bancario", "aplicacion_pago"):
        assert conn.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0] == 0, tabla


# ------------------------------------------------------------ MT940

MT940_ING = b"""{1:F01INGBNL2ABXXX0000000000}
{2:I940INGBNL2AXXXN}
{4:
:20:P261013000000001
:25:NL60INGB0009988776EUR
:28C:00101
:60F:C261012EUR10000,00
:61:2610121012D2902,79NTRFE2E-4471//ING-0001
/TRCD/00100/
:86:/CNTP/NL02ABNA0123456789/ABNANL2A/Bouwtechniek Van Dijk BV/Rotterdam/REMI/USTD//Factuur
 2026-4471/EREF/E2E-4471/
:61:2610131013C1500,00NTRFNONREF//ING-0002
:86:/CNTP/NL39RABO0300065264/RABONL2U/Havenbedrijf Schiedam/Schiedam/REMI/STRD/CUR/RF18539007
547034/
:62F:C261013EUR8597,21
-}
"""

MT940_ABN = b"""ABNANL2A
940
ABNANL2A
:20:ABN AMRO BANK NV
:25:NL07ABNA0555666777
:28:10201/1
:60F:C261012EUR5000,00
:61:2610121012D600,00N658NONREF
:86:/TRTP/OVERBOEKING/IBAN/NL67INGB0006543210/BIC/INGBNL2A/NAME/Schilderwerk
en Bakker/REMI/Factuur B-2026-077 deel 1/EREF/NOTPROVIDED
:62F:C261012EUR4400,00
-
"""

MT940_RABOBANK = b""":20:940S261013
:25:NL93RABO0987654321 EUR
:28C:00102
:60F:C261012EUR7000,00
:61:261013C1000,00N541NONREF
NL39RABO0300065264
:86:/EREF/V2026-0012-1//NAME/Havenbedrijf Schiedam/REMI/Betaling factuur V2026-0012/
:62F:C261013EUR8000,00
"""


def test_mt940_de_ing_lee_cntp_remi_y_eref() -> None:
    lote = mt940.leer(MT940_ING, "ing.sta")
    [extracto] = lote.registros
    assert (lote.formato, extracto.cuenta_propia_iban, extracto.secuencia) == (
        "mt940:ing", CUENTA_PROPIA, 101)
    assert (extracto.saldo_inicial, extracto.saldo_final) == (Decimal("10000.00"),
                                                              Decimal("8597.21"))
    cargo, abono = extracto.movimientos
    assert (cargo.importe, cargo.contraparte_iban, cargo.contraparte_nombre, cargo.concepto,
            cargo.referencia_e2e, cargo.ref_banco) == (
        Decimal("-2902.79"), "NL02ABNA0123456789", "Bouwtechniek Van Dijk BV",
        "Factuur 2026-4471", "E2E-4471", "ING-0001")
    assert (abono.importe, abono.contraparte_iban, abono.referencia_estructurada,
            abono.referencia_e2e) == (Decimal("1500.00"), "NL39RABO0300065264",
                                      "RF18539007547034", None)
    assert (cargo.fecha_contable, cargo.fecha_valor) == (date(2026, 10, 12), date(2026, 10, 12))


def test_mt940_de_abn_amro_lee_iban_name_y_remi_sueltos() -> None:
    lote = mt940.leer(MT940_ABN, "abn.sta")
    [extracto] = lote.registros
    assert (lote.formato, extracto.cuenta_propia_iban, extracto.secuencia) == (
        "mt940:abn", CUENTA_AJENA, 10201)
    [cargo] = extracto.movimientos
    assert (cargo.importe, cargo.contraparte_iban, cargo.contraparte_nombre, cargo.concepto,
            cargo.referencia_e2e) == (Decimal("-600.00"), "NL67INGB0006543210",
                                      "Schilderwerken Bakker", "Factuur B-2026-077 deel 1", None)


def test_mt940_de_rabobank_lee_la_cuenta_de_la_linea_del_61() -> None:
    lote = mt940.leer(MT940_RABOBANK, "rabo.sta")
    [extracto] = lote.registros
    assert (lote.formato, extracto.cuenta_propia_iban) == ("mt940:rabobank", OTRA_CUENTA_PROPIA)
    [abono] = extracto.movimientos
    assert (abono.importe, abono.contraparte_iban, abono.contraparte_nombre, abono.concepto,
            abono.referencia_e2e) == (Decimal("1000.00"), "NL39RABO0300065264",
                                      "Havenbedrijf Schiedam", "Betaling factuur V2026-0012",
                                      "V2026-0012-1")


def test_mt940_de_un_banco_sin_perfil_deja_el_86_entero_y_lo_avisa() -> None:
    otro = MT940_RABOBANK.replace(b"NL93RABO0987654321", b"NL85KNAB0101010101")
    lote = mt940.leer(otro)
    [extracto] = lote.registros
    assert lote.formato == "mt940:generico"
    assert extracto.movimientos[0].concepto.startswith("/EREF/V2026-0012-1//NAME/")
    assert any("sin perfil" in a for a in lote.avisos)
    # Pedido a mano, se lee con el perfil que se pide.
    assert mt940.leer(otro, perfil="rabobank").registros[0].movimientos[0].contraparte_nombre == (
        "Havenbedrijf Schiedam")
    with pytest.raises(FicheroNoAdmitido, match="perfil"):
        mt940.leer(otro, perfil="bunq")


def test_mt940_que_no_cuadra_no_entra() -> None:
    roto = MT940_ING.replace(b":62F:C261013EUR8597,21", b":62F:C261013EUR8597,20")
    lote = mt940.leer(roto)
    assert lote.registros == () and "incompleto" in lote.rechazos[0].motivo


def test_mt940_se_importa_y_se_elige_por_el_contenido(almacen, ana) -> None:
    ruta = almacen.documentos.raiz.parent / "ing.sta"
    ruta.write_bytes(MT940_ING)
    resultado = importar_fichero(almacen, "banco", "extracto", ruta, lanzado_por=ana)
    [lote] = resultado.lotes
    assert (lote.estado, lote.formato) == ("aceptada", "mt940:ing")
    assert len(_movimientos(almacen.conn)) == 2
    assert banco.leer(MT940_RABOBANK, formato="mt940:rabobank")[0].formato == "mt940:rabobank"


# ------------------------------------------------------------ los CSV del banco

def _sin_la_fila_rara(nombre: str, destino) -> object:
    lineas = (IMPORTACION / nombre).read_bytes().splitlines(keepends=True)
    ruta = destino / nombre
    ruta.write_bytes(b"".join(line for line in lineas if b"fila con signo raro" not in line))
    return ruta


def test_los_csv_del_banco_entran_sin_saldos_y_k6_no_los_mira(almacen, ana) -> None:
    conn = almacen.conn
    carpeta = almacen.documentos.raiz.parent
    ing = _sin_la_fila_rara("banco-extracto-ing-v1.csv", carpeta)
    [lote] = importar_fichero(almacen, "banco", "extracto", ing, lanzado_por=ana).lotes
    assert (lote.estado, lote.formato) == ("aceptada", "csv:ing-af-bij-v1")
    rabo = IMPORTACION / "banco-extracto-rabobank-v1.csv"
    [lote] = importar_fichero(almacen, "banco", "extracto", rabo, lanzado_por=ana).lotes
    assert lote.estado == "aceptada"
    extractos = conn.execute("SELECT cuenta_propia_iban, con_saldos, saldo_inicial_cent, "
                             "secuencia FROM extracto_bancario ORDER BY id").fetchall()
    assert [tuple(e) for e in extractos] == [(CUENTA_PROPIA, 0, None, None),
                                             (OTRA_CUENTA_PROPIA, 0, None, None)]
    # Las dos comisiones iguales de ING son dos movimientos.
    assert conn.execute("SELECT count(*) FROM movimiento_bancario WHERE importe_cent = -50"
                        ).fetchone()[0] == 2
    # Sin saldos no hay cadena que comprobar: K6 ni se evalua.
    assert _abiertos(conn, "K6") == []
    assert conn.execute("SELECT count(*) FROM evaluacion WHERE regla = 'K6' AND resultado <> "
                        "'ok'").fetchone()[0] == 0
    # La fila en dolares de Rabobank: X1.
    assert [h["tabla"] for h in _abiertos(conn, "X1")] == ["movimiento"]


def test_un_csv_del_banco_con_una_fila_que_no_se_lee_no_entra(almacen, ana) -> None:
    [lote] = importar_fichero(almacen, "banco", "extracto",
                              IMPORTACION / "banco-extracto-ing-v1.csv", lanzado_por=ana).lotes
    assert lote.estado == "rechazada"
    assert almacen.conn.execute("SELECT count(*) FROM movimiento_bancario").fetchone()[0] == 0


# ------------------------------------------------------------ los pagos de Exact

PAGOS_EXACT = IMPORTACION / "exact-pagos_exact-v1.csv"
EXACT_PROVEEDORES = IMPORTACION / "exact-proveedores-v1.csv"


def _pagos_exact(carpeta, *filas: str, nombre: str = "pagos.csv"):
    cabecera = PAGOS_EXACT.read_text(encoding="utf-8-sig").splitlines()[0]
    ruta = carpeta / nombre
    ruta.write_text("\n".join([cabecera, *filas]) + "\n", encoding="utf-8")
    return ruta


def test_los_pagos_de_exact_con_una_fila_que_no_se_lee_no_entran(tipado) -> None:
    conn = tipado.conn
    ana = persona(conn, "Ana", "administrador")
    [lote] = importar_fichero(tipado, "exact", "pagos_exact", PAGOS_EXACT,
                              lanzado_por=ana).lotes
    assert lote.estado == "rechazada"
    assert conn.execute("SELECT count(*) FROM aplicacion_pago").fetchone()[0] == 0


def test_los_pagos_de_exact_y_la_fila_de_una_factura_que_no_esta(tipado) -> None:
    conn = tipado.conn
    ana = persona(conn, "Ana", "administrador")
    importar_fichero(tipado, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana)
    carpeta = tipado.documentos.raiz.parent
    ruta = _pagos_exact(carpeta, "Inkoop;20001;2026-4471;2.902,79;0,00;;10-10-2026;EUR",
                        "Inkoop;20004;B-2026-077;1.251,62;651,62;;;EUR",
                        "Inkoop;20001;2026-9999;100,00;0,00;;;EUR")
    [lote] = importar_fichero(tipado, "exact", "pagos_exact", ruta, lanzado_por=ana).lotes
    assert lote.estado == "parcial"
    assert [r.fila for r in lote.rechazos] == [4]
    filas = conn.execute("SELECT f.numero, a.importe_cent, a.fuente, a.metodo, a.estado, "
                         "a.fecha_pago FROM aplicacion_pago a JOIN factura f ON f.id = "
                         "a.factura_id ORDER BY a.id").fetchall()
    assert [tuple(f) for f in filas] == [
        ("2026-4471", 290279, "exact", "automatica", "confirmada", "2026-10-10"),
        ("B-2026-077", 60000, "exact", "automatica", "confirmada", "2026-10-14")]
    estados = dict(conn.execute("SELECT f.numero, e.estado_pago FROM factura_estado e JOIN "
                                "factura f ON f.id = e.factura_id"))
    assert estados["2026-4471"] == "pagada" and estados["B-2026-077"] == "pendiente"
    assert ("importacion", lote.importacion_id) in [(h["tabla"], h["fila_id"])
                                                    for h in _abiertos(conn, "Z2")]
    # Exact dice otra cosa la vez siguiente: lo de antes se retira, no se borra.
    otra = _pagos_exact(carpeta, "Inkoop;20004;B-2026-077;1.251,62;0,00;;12-10-2026;EUR",
                        nombre="pagos-2.csv")
    [lote] = importar_fichero(tipado, "exact", "pagos_exact", otra, lanzado_por=ana).lotes
    assert lote.estado == "aceptada"
    bakker = conn.execute("SELECT a.importe_cent, a.estado FROM aplicacion_pago a JOIN factura f "
                          "ON f.id = a.factura_id WHERE f.numero = 'B-2026-077' ORDER BY a.id"
                          ).fetchall()
    assert [tuple(f) for f in bakker] == [(60000, "retirada"), (125162, "confirmada")]
    assert campos.verificar_controladas(conn) == []
    assert hallazgos.verificar(conn) == []


def test_un_pago_de_exact_en_otra_moneda_rechaza_el_fichero(tipado) -> None:
    conn = tipado.conn
    ana = persona(conn, "Ana", "administrador")
    ruta = _pagos_exact(tipado.documentos.raiz.parent,
                        "Inkoop;20001;2026-4471;2.902,79;0,00;;10-10-2026;EUR",
                        "Inkoop;20006;NW-2026-0042;1.000,00;0,00;;10-10-2026;USD")
    [lote] = importar_fichero(tipado, "exact", "pagos_exact", ruta, lanzado_por=ana).lotes
    assert lote.estado == "rechazada"
    assert [r.codigo for r in lote.rechazos] == ["X1"]
    assert conn.execute("SELECT count(*) FROM aplicacion_pago").fetchone()[0] == 0
