"""El BTW (paso 11) sobre el almacen: las cifras de cada trimestre, su hoja y su estado.

El reloj de las pruebas esta en el 2026-10-14: el tercer trimestre de 2026 ya
termino y vence el 31 de octubre; el cuarto esta en curso. Las facturas se dan
de alta como las daria la extraccion, sin pasar por un PDF: lo que se mira
aqui es lo que btw.py hace con ellas. Puertas del paso 11 que viven aqui:

- el IVA normal al 21 % (1a y 5b, y lo que queda a pagar);
- el IVA trasladado de una compra va a 2a y a 5b y se compensa;
- la KOR, y un abono en un trimestre posterior;
- el plazo del cuarto trimestre es el 31 de enero, y el del tercero de 2026 el
  2026-10-31;
- presentar es irreversible y queda con el hash de la hoja, y una factura que
  llega tarde a un trimestre presentado da C4.

Las reglas sin base (C4, E0, E5, E7) estan en test_reglas_paso11.py.
"""

from __future__ import annotations

import ast
import csv
import dataclasses
import hashlib
import io
import json
import re
import sqlite3
from datetime import date
from decimal import Decimal

import pytest
from conftest import RAIZ, persona

from bms_agent import btw, campos, hallazgos, politica, servicios
from bms_agent.almacen import usuario_sistema
from bms_agent.almacen.evidencia import verificar_evidencia
from bms_agent.auditoria import registrar
from bms_agent.campos import Automatico, Conflicto, FaltaMotivo, Persona
from bms_agent.permisos import PermisoDenegado, SeparacionDeFunciones, orden_auditada
from bms_agent.reglas import instantanea
from bms_agent.reglas.base import en_juego
from bms_agent.reglas.iva import huella_de_factura

REFERENCIA = "OB-2026-T3-0001"
MOTIVO = "El asesor pide repasar dos compras"
EXACT_CLIENTES = RAIZ / "tests" / "fixtures" / "importacion" / "exact-clientes-v1.csv"


# ------------------------------------------------------------ constructores

def _alta(conn, numero: str, *, sentido: str = "entrante", fecha: str | None = "2026-08-10",
          base: str | None = "1000.00", iva: str | None = "210.00", tipo_iva: str | None = "21",
          tratamiento: str | None = "estandar", tipo: str = "factura", btw_doc: str | None = None,
          nombre: str | None = None, desglose=(), moneda: str | None = None,
          cliente_id: int | None = None) -> int:
    """Una factura dada de alta como la daria la extraccion, con su desglose si lo tiene:
    (tratamiento, tipo, base, cuota) por fila."""
    origen = Automatico("extraccion", usuario_sistema(conn, "extractor"))
    valores = {"sentido": sentido, "tipo": tipo, "origen": "manual", "numero": numero,
               "fecha_factura": fecha, "tratamiento_iva": tratamiento, "moneda_doc": moneda,
               "cliente_id": cliente_id}
    if base is not None:
        valores["base_cent"] = Decimal(base)
        valores["total_cent"] = Decimal(base) + Decimal(iva or 0)
    if iva is not None:
        valores["iva_cent"] = Decimal(iva)
    if tipo_iva is not None:
        valores["tipo_iva_pb"] = Decimal(tipo_iva)
    lado = "emisor" if sentido == "entrante" else "receptor"
    valores[f"{lado}_nombre_doc"] = nombre or f"Parte {numero}"
    valores[f"{lado}_btw_doc"] = btw_doc
    with campos.orden(conn, origen, tipo="factura_alta") as o:
        factura_id = o.crear("factura", {k: v for k, v in valores.items() if v is not None})
        for tratamiento_, tipo_, base_, cuota_ in desglose:
            o.crear("factura_iva", {
                "factura_id": factura_id, "tratamiento": tratamiento_,
                "tipo_iva_pb": None if tipo_ is None else Decimal(tipo_),
                "base_cent": Decimal(base_),
                "cuota_cent": None if cuota_ is None else Decimal(cuota_)})
    return factura_id


def _rubricas(cifras: dict) -> dict[str, tuple[int, int]]:
    """Las rubricas con algo: (omzet, btw) en centimos."""
    return {r["rubrica"]: (r["omzet_cent"], r["btw_cent"]) for r in cifras["rubricas"]
            if r["omzet_cent"] or r["btw_cent"]}


def _cifras(conn, ano: int = 2026, trimestre: int = 3) -> dict:
    return btw.trimestre(conn, ano, trimestre)["cifras"]


def _listo(conn, quien: int, ano: int = 2026, trimestre: int = 3) -> btw.Hoja:
    hoja = btw.hoja(conn, ano, trimestre)
    btw.marcar_lista(conn, Persona(quien), ano, trimestre, hoja_sha256=hoja.sha256)
    return hoja


def _presentar(conn, quien: int, anota: int | None = None, *, importe: str = "0",
               fecha: date | None = None) -> btw.Hoja:
    """Lo marca listo `quien` y lo anota presentado `anota` (por defecto, la misma)."""
    hoja = _listo(conn, quien)
    btw.anotar_presentacion(conn, Persona(anota or quien), 2026, 3, hoja_sha256=hoja.sha256,
                            referencia=REFERENCIA, importe_declarado=Decimal(importe),
                            fecha=fecha)
    return hoja


def _c4(conn) -> list:
    return conn.execute("SELECT * FROM hallazgo WHERE regla = 'C4' AND estado = 'abierto' "
                        "ORDER BY factura_id").fetchall()


def _datos_evento(conn, evento_id: int) -> dict:
    return json.loads(conn.execute("SELECT datos_json FROM evento WHERE id = ?",
                                   (evento_id,)).fetchone()[0])


def _rev_factura(conn, factura_id: int) -> int:
    return conn.execute("SELECT rev FROM factura WHERE id = ?", (factura_id,)).fetchone()[0]


@pytest.fixture
def ana(almacen) -> int:
    """Ana, de administracion: la unica con gestionar_btw (salvo donde se diga)."""
    return persona(almacen.conn, "Ana", "administracion")


# ============================================================ las cifras

def test_el_iva_normal_al_21_va_a_1a_y_5b_y_queda_a_pagar_la_diferencia(almacen) -> None:
    """Puerta: el IVA normal al 21 %."""
    conn = almacen.conn
    _alta(conn, "V-1", sentido="saliente", base="10000.00", iva="2100.00")
    _alta(conn, "V-2", sentido="saliente", base="1000.00", iva="90.00", tipo_iva="9")
    _alta(conn, "V-3", sentido="saliente", base="500.00", iva="0.00", tipo_iva="0",
          tratamiento="tipo_cero")
    _alta(conn, "C-1", base="4000.00", iva="840.00")
    _alta(conn, "C-octubre", base="100.00", iva="21.00", fecha="2026-10-02")
    c = _cifras(conn)
    assert _rubricas(c) == {"1a": (1_000_000, 210_000), "1b": (100_000, 9_000),
                            "1e": (50_000, 0)}
    assert (c["5a"], c["5b"], c["5c"]) == (219_000, 84_000, 135_000)
    assert (c["a_pagar_cent"], c["a_devolver_cent"]) == (135_000, 0)
    assert (c["ingresos_cent"], c["iva_repercutido_cent"]) == (1_150_000, 219_000)
    assert (c["costes_cent"], c["iva_deducible_cent"]) == (400_000, 84_000)
    texto = btw.hoja(conn, 2026, 3).texto
    assert "\r\n1a;Leveringen/diensten belast met hoog tarief;10000,00;2100,00\r\n" in texto
    assert "\r\n5c;Subtotaal (5a min 5b): te betalen of terug te vragen;;1350,00\r\n" in texto
    assert "\r\nEstimación: a pagar;1350,00\r\n" in texto
    # La compra de octubre es del cuarto trimestre.
    assert _cifras(conn, 2026, 4)["5b"] == 2_100


def test_el_iva_trasladado_de_una_compra_va_a_2a_y_5b_y_se_compensa(almacen) -> None:
    """Puerta: el IVA trasladado de una compra se autoliquida en 2a y vuelve en 5b."""
    conn = almacen.conn
    _alta(conn, "C-verlegd", base="5000.00", iva="0.00", tipo_iva=None,
          tratamiento="autoliquidacion", btw_doc="NL001234567B01")
    c = _cifras(conn)
    assert _rubricas(c) == {"2a": (500_000, 105_000)}
    assert (c["5a"], c["5b"], c["5c"]) == (105_000, 105_000, 0)
    assert (c["iva_autoliquidado_cent"], c["costes_cent"]) == (105_000, 500_000)
    assert ";C-verlegd;Parte C-verlegd;2026-08-10;autoliquidacion;;5000,00;0,00;1050,00;2a;" \
        in btw.hoja(conn, 2026, 3).texto
    # De un proveedor de la UE va a 4b y de uno de fuera a 4a: tambien se compensa.
    _alta(conn, "C-de", base="1000.00", iva="0.00", tipo_iva=None,
          tratamiento="autoliquidacion", btw_doc="DE123456789")
    _alta(conn, "C-gb", base="200.00", iva="0.00", tipo_iva=None,
          tratamiento="autoliquidacion", btw_doc="GB123456789")
    c = _cifras(conn)
    assert _rubricas(c) == {"2a": (500_000, 105_000), "4b": (100_000, 21_000),
                            "4a": (20_000, 4_200)}
    assert c["5c"] == 0
    # Con un desglose de dos filas, la normal deduce su cuota y la trasladada se autoliquida.
    _alta(conn, "C-mixta", base="700.00", iva="105.00", tipo_iva=None,
          desglose=(("estandar", "21", "500.00", "105.00"),
                    ("autoliquidacion", None, "200.00", None)))
    c = _cifras(conn)
    assert _rubricas(c)["2a"] == (520_000, 109_200)
    assert (c["5a"], c["5b"], c["5c"]) == (134_400, 144_900, -10_500)


def test_una_compra_con_kor_no_tiene_iva_que_declarar(almacen) -> None:
    """Puerta: la KOR. Es coste, sin IVA soportado, y la hoja dice que no va en la
    declaracion."""
    conn = almacen.conn
    _alta(conn, "C-kor", base="800.00", iva="0.00", tipo_iva=None, tratamiento="kor")
    _alta(conn, "C-1")
    c = _cifras(conn)
    assert _rubricas(c) == {}
    assert (c["5a"], c["5b"], c["5c"], c["costes_cent"]) == (0, 21_000, -21_000, 180_000)
    assert [(f["numero"], f["motivo"]) for f in c["fuera"]] == [
        ("C-kor", "no va en la declaración")]
    assert c["sin_clasificar"] == []
    assert "\r\nFuera de las cifras\r\n" in (texto := btw.hoja(conn, 2026, 3).texto)
    assert ";C-kor;Parte C-kor;no va en la declaración\r\n" in texto


def test_un_abono_de_un_trimestre_posterior_cuenta_en_el_suyo(almacen, ana) -> None:
    """Puerta: un abono en un trimestre posterior va en ese trimestre, en negativo, y el
    trimestre presentado sigue siendo lo que se presento."""
    conn = almacen.conn
    _alta(conn, "V-1", sentido="saliente", base="1000.00", iva="210.00")
    _alta(conn, "C-1", base="600.00", iva="126.00")
    hallazgos.recalcular(conn)
    hoja = _presentar(conn, ana, importe="84")
    _alta(conn, "V-1-abono", sentido="saliente", tipo="nota_credito", fecha="2026-10-05",
          base="-400.00", iva="-84.00")
    _alta(conn, "C-1-abono", tipo="nota_credito", fecha="2026-11-03", base="-600.00",
          iva="-126.00")
    hallazgos.recalcular(conn)
    cuarto = _cifras(conn, 2026, 4)
    assert _rubricas(cuarto) == {"1a": (-40_000, -8_400)}
    assert (cuarto["5a"], cuarto["5b"], cuarto["5c"]) == (-8_400, -12_600, 4_200)
    assert (cuarto["ingresos_cent"], cuarto["costes_cent"]) == (-40_000, -60_000)
    tercero = btw.trimestre(conn, 2026, 3)
    assert _rubricas(tercero["cifras"]) == {"1a": (100_000, 21_000)}
    assert tercero["diferencias"] == [] and tercero["hoja_al_dia"]
    assert btw.hoja(conn, 2026, 3).sha256 == hoja.sha256
    assert _c4(conn) == []


@pytest.mark.parametrize("ano, trimestre, limite", [
    (2026, 3, date(2026, 10, 31)), (2026, 4, date(2027, 1, 31)), (2025, 4, date(2026, 1, 31)),
    (2026, 1, date(2026, 4, 30)), (2026, 2, date(2026, 7, 31)), (2027, 4, date(2028, 1, 31)),
])
def test_el_plazo_es_el_ultimo_dia_del_mes_siguiente_al_trimestre(ano, trimestre, limite):
    """Puerta: el del cuarto trimestre es el 31 de enero; el del tercero de 2026, el
    2026-10-31. Presentar y pagar vencen el mismo dia."""
    assert btw.limites(ano, trimestre) == (limite, limite)


def test_los_plazos_van_al_trimestre_a_la_hoja_y_al_periodo(almacen, ana) -> None:
    conn = almacen.conn
    tercero = btw.trimestre(conn, 2026, 3)
    assert (tercero["limite_presentacion"], tercero["limite_pago"]) == ("2026-10-31",
                                                                         "2026-10-31")
    assert tercero["dias_para_limite"] == 17 and tercero["terminado"]
    cuarto = btw.trimestre(conn, 2026, 4)
    assert (cuarto["limite_presentacion"], cuarto["terminado"]) == ("2027-01-31", False)
    hoja = _listo(conn, ana)
    assert "\r\nPlazo de presentación;2026-10-31\r\nPlazo de pago;2026-10-31\r\n" in hoja.texto
    fila = btw.periodo(conn, 2026, 3)
    assert (fila["inicio"], fila["fin"], fila["limite_presentacion"], fila["limite_pago"]) == (
        "2026-07-01", "2026-09-30", "2026-10-31", "2026-10-31")


def test_lo_que_no_se_puede_clasificar_queda_fuera_de_las_cifras(almacen, ana) -> None:
    conn = almacen.conn
    dolares = _alta(conn, "C-usd", moneda="USD")
    sin_regimen = _alta(conn, "C-e0", tratamiento="desconocido")
    sin_cuota = _alta(conn, "V-e0", sentido="saliente", iva=None)
    _alta(conn, "C-1")
    anulada = _alta(conn, "C-anulada", base="999.00", iva="209.79")
    servicios.ejecutar(conn, "anular_factura", {
        "factura_id": anulada, "rev": _rev_factura(conn, anulada), "motivo": "Anulada en Exact"},
        usuario_id=ana)
    c = _cifras(conn)
    motivos = {f["factura_id"]: f["motivo"] for f in c["sin_clasificar"]}
    assert set(motivos) == {dolares, sin_regimen, sin_cuota}
    assert "X1" in motivos[dolares] and "E0" in motivos[sin_regimen]
    assert "E0" in motivos[sin_cuota]
    # Solo la compra en euros con su IVA suma; la anulada ni aparece.
    assert (c["5b"], c["costes_cent"]) == (21_000, 200_000)
    assert c["lineas"] == 4


def test_las_facturas_que_piden_revisar_el_iva_son_las_del_trimestre(almacen) -> None:
    conn = almacen.conn
    sin_regimen = _alta(conn, "C-e0", tratamiento="desconocido")
    mala = _alta(conn, "C-d3", base="1000.00", iva="250.00")
    _alta(conn, "C-1")
    _alta(conn, "C-octubre", tratamiento="desconocido", fecha="2026-10-02")
    hallazgos.recalcular(conn)
    revisar = {r["factura_id"]: r["reglas"] for r in btw.trimestre(conn, 2026, 3)["revisar"]}
    assert set(revisar) == {sin_regimen, mala}
    assert "E0" in revisar[sin_regimen] and "D3" in revisar[mala]
    texto = btw.hoja(conn, 2026, 3).texto
    assert f"\r\n{sin_regimen};C-e0;Parte C-e0;" in texto.split(
        "Facturas que piden revisar el IVA")[1]


def test_la_vista_y_las_reglas_dicen_lo_mismo_de_cada_factura(almacen) -> None:
    """v_btw_linea (lo que se declara) y reglas/iva.lineas_iva (lo que mira C4) son lo mismo:
    si no, C4 veria diferencias que no hay."""
    conn = almacen.conn
    _alta(conn, "V-1", sentido="saliente", btw_doc="NL009999999B01")
    _alta(conn, "V-ue", sentido="saliente", tratamiento="autoliquidacion", iva="0.00",
          tipo_iva=None, btw_doc="BE0123456789")
    _alta(conn, "C-1")
    _alta(conn, "C-de", tratamiento="autoliquidacion", iva=None, tipo_iva=None,
          btw_doc="DE123456789")
    _alta(conn, "C-kor", tratamiento="kor", iva="0.00", tipo_iva=None)
    _alta(conn, "C-mixta", base="700.00", iva="105.00", tipo_iva=None, btw_doc="DE1",
          desglose=(("estandar", "21", "500.00", "105.00"), ("autoliquidacion", None,
                                                             "200.00", None),
                    (None, "9", "0.00", "0.00")))
    _alta(conn, "C-usd", moneda="USD")
    _alta(conn, "C-sin-fecha", fecha=None)
    _alta(conn, "C-abono", tipo="nota_credito", base="-100.00", iva="-21.00",
          fecha="2025-12-30")
    foto = instantanea.construir(conn, hoy=date(2026, 10, 14))
    esperadas = {f.id: huella_de_factura(f) for f in foto.facturas
                 if en_juego(f) and f.moneda is None and f.fecha_factura is not None}
    assert len(esperadas) == 7
    assert btw.huellas(btw.lineas(conn)) == esperadas


def test_la_hoja_neutraliza_lo_que_una_hoja_de_calculo_leeria_como_formula(almacen) -> None:
    conn = almacen.conn
    _alta(conn, '=HYPERLINK("http://x";"pulsa")', nombre="@SUM(A1:A9)")
    _alta(conn, "+31-2026", nombre=" -2+3", tratamiento="desconocido")
    hallazgos.recalcular(conn)
    texto = btw.hoja(conn, 2026, 3).texto
    assert texto.startswith("﻿Hoja de trabajo BTW;BM Support BV\r\n")
    celdas = [c for fila in csv.reader(io.StringIO(texto[1:]), delimiter=";") for c in fila]
    assert "'=HYPERLINK(\"http://x\";\"pulsa\")" in celdas
    assert {"'@SUM(A1:A9)", "'+31-2026", "' -2+3"} <= set(celdas)
    for celda in celdas:
        # Solo los importes que escribe el sistema empiezan por un signo.
        assert not celda.lstrip().startswith(("=", "+", "@")), celda
        assert not celda.startswith("-") or re.fullmatch(r"-\d+,\d\d", celda), celda
    assert [btw.celda(v) for v in ("=1+1", "-5", "+5", "@A1", "\t=1", "  =1", "Van Dijk", None,
                                   12)] == [
        "'=1+1", "'-5", "'+5", "'@A1", "'\t=1", "'  =1", "Van Dijk", "", "12"]


# ============================================================ el estado del trimestre

def test_presentar_es_irreversible_y_queda_con_el_hash_de_la_hoja(almacen, ana) -> None:
    """Puerta: la presentacion es irreversible y lleva el hash de la hoja que se reviso."""
    conn = almacen.conn
    beatriz = persona(conn, "Beatriz", "administracion")
    venta = _alta(conn, "V-1", sentido="saliente", base="10000.00", iva="2100.00")
    compra = _alta(conn, "C-1", base="4000.00", iva="840.00")
    hoja = btw.hoja(conn, 2026, 3)
    assert hoja.sha256 == hashlib.sha256(hoja.en_bytes()).hexdigest()
    btw.marcar_lista(conn, Persona(ana), 2026, 3, hoja_sha256=hoja.sha256)
    fila = btw.periodo(conn, 2026, 3)
    assert (fila["estado"], fila["hoja_sha256"], fila["listo_por"]) == ("listo_revision",
                                                                       hoja.sha256, ana)
    guardada = conn.execute("SELECT * FROM hoja_btw WHERE id = ?", (fila["hoja_id"],)).fetchone()
    assert guardada["contenido"] == hoja.texto and guardada["sha256"] == hoja.sha256
    # Quien la marco lista no la anota habiendo otra persona con gestionar_btw.
    with pytest.raises(SeparacionDeFunciones):
        btw.anotar_presentacion(conn, Persona(ana), 2026, 3, hoja_sha256=hoja.sha256,
                                referencia=REFERENCIA, importe_declarado=Decimal("1260"))
    evento = btw.anotar_presentacion(conn, Persona(beatriz, motivo="Presentada en el portal"),
                                     2026, 3, hoja_sha256=hoja.sha256, referencia=REFERENCIA,
                                     importe_declarado=Decimal("1260"),
                                     fecha=date(2026, 10, 12))
    fila = btw.periodo(conn, 2026, 3)
    assert (fila["estado"], fila["presentado_en"], fila["presentado_por"],
            fila["referencia_presentacion"], fila["importe_declarado_cent"],
            fila["hoja_sha256"], fila["nota"]) == (
        "presentado", "2026-10-12", beatriz, REFERENCIA, 126_000, hoja.sha256,
        "Presentada en el portal")
    datos = _datos_evento(conn, evento)
    assert (datos["hoja_sha256"], datos["autorrevisado"], datos["estimado_cent"]) == (
        hoja.sha256, False, 126_000)
    assert [tuple(d) for d in conn.execute(
        "SELECT factura_id, base_cent, cuota_cent FROM periodo_btw_declarada "
        "ORDER BY factura_id")] == [(venta, 1_000_000, 210_000), (compra, 400_000, 84_000)]
    # Ninguna orden lo devuelve atras ni lo vuelve a presentar...
    rev = fila["rev"]
    with pytest.raises(btw.EstadoNoValido, match="irreversible"):
        btw.reabrir(conn, Persona(ana, motivo="Me equivoque"), 2026, 3, rev=rev)
    with pytest.raises(btw.EstadoNoValido, match="irreversible"):
        _listo(conn, ana)
    with pytest.raises(btw.EstadoNoValido, match="irreversible"):
        btw.anotar_presentacion(conn, Persona(beatriz), 2026, 3, hoja_sha256=hoja.sha256,
                                referencia="OTRA", importe_declarado=Decimal("0"))
    # ... ni una escritura auditada de una persona con el permiso: lo para la base.
    for nuevos in ({"estado": "listo_revision", "presentado_en": None, "presentado_por": None,
                    "referencia_presentacion": None, "importe_declarado_cent": None},
                   {"referencia_presentacion": "OTRA"}, {"nota": "corregida por detras"}):
        with pytest.raises(sqlite3.IntegrityError, match="irreversible"):
            with orden_auditada(conn):
                btw._escribir(conn, Persona(beatriz), btw.periodo(conn, 2026, 3), 2026, 3,
                              nuevos, tipo="btw_reabierto", motivo="por detras", datos={})
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM periodo_btw")
    for orden_sql in ("UPDATE hoja_btw SET contenido = 'x'", "DELETE FROM hoja_btw",
                      "UPDATE periodo_btw_declarada SET base_cent = 0",
                      "DELETE FROM periodo_btw_declarada"):
        with pytest.raises(sqlite3.IntegrityError, match="solo escritura"):
            conn.execute(orden_sql)
    assert btw.periodo(conn, 2026, 3)["rev"] == rev and btw.estado_de(conn, 2026, 3) == \
        "presentado"
    assert btw.verificar(conn) == [] and verificar_evidencia(conn) == []


def test_una_factura_que_llega_tarde_a_un_trimestre_presentado_da_c4(almacen, ana) -> None:
    """Puerta: una factura tardia en un trimestre presentado da C4; tambien una declarada que
    ya no cuenta alli."""
    conn = almacen.conn
    _alta(conn, "C-1")
    declarada = _alta(conn, "C-2", base="500.00", iva="105.00", fecha="2026-09-05")
    hallazgos.recalcular(conn)
    hoja = _presentar(conn, ana, importe="-315")
    hallazgos.recalcular(conn)
    assert _c4(conn) == []
    tarde = _alta(conn, "C-tarde", base="300.00", iva="63.00", fecha="2026-09-28")
    hallazgos.recalcular(conn)
    [c4] = _c4(conn)
    assert (c4["factura_id"], c4["severidad"]) == (tarde, "aviso")
    assert c4["clave"].endswith("|2026-T3")
    t = btw.trimestre(conn, 2026, 3)
    assert t["diferencias"] == [{"factura_id": tarde, "motivo": "tarde",
                                 "base_declarada_cent": None, "cuota_declarada_cent": None}]
    assert {r["factura_id"]: r["reglas"] for r in t["revisar"]} == {tarde: ["C4"]}
    # Lo presentado no cambia: la hoja de hoy ya no es la presentada, que sigue guardada.
    assert (t["hoja_marcada_sha256"], t["hoja_al_dia"]) == (hoja.sha256, False)
    assert "\r\nDiferencias con lo presentado\r\n" in btw.hoja(conn, 2026, 3).texto
    assert conn.execute("SELECT count(*) FROM hoja_btw WHERE sha256 = ?",
                        (hoja.sha256,)).fetchone()[0] == 1
    # Anular una factura declarada tambien es una diferencia: ya no cuenta alli.
    servicios.ejecutar(conn, "anular_factura", {
        "factura_id": declarada, "rev": _rev_factura(conn, declarada),
        "motivo": "Anulada en Exact"}, usuario_id=ana)
    hallazgos.recalcular(conn)
    assert [h["factura_id"] for h in _c4(conn)] == [declarada, tarde]
    assert {d["factura_id"]: d["motivo"] for d in btw.trimestre(conn, 2026, 3)[
        "diferencias"]} == {declarada: "fuera", tarde: "tarde"}


def test_la_hoja_que_se_presenta_es_la_que_se_marco_lista(almacen, ana) -> None:
    conn = almacen.conn
    _alta(conn, "C-1")
    with pytest.raises(btw.EstadoNoValido, match="no ha terminado"):
        _listo(conn, ana, 2026, 4)
    with pytest.raises(Conflicto):
        btw.marcar_lista(conn, Persona(ana), 2026, 3, hoja_sha256="0" * 64)
    hoja = _listo(conn, ana)
    assert btw.marcar_lista(conn, Persona(ana), 2026, 3, hoja_sha256=hoja.sha256) is None
    # Llega otra factura del trimestre: lo que se marco ya no es lo de hoy.
    _alta(conn, "C-2", fecha="2026-09-30")
    with pytest.raises(Conflicto, match="cambiaron"):
        btw.anotar_presentacion(conn, Persona(ana), 2026, 3, hoja_sha256=hoja.sha256,
                                referencia=REFERENCIA, importe_declarado=Decimal("-420"))
    nueva = btw.hoja(conn, 2026, 3)
    with pytest.raises(Conflicto, match="no es la hoja"):
        btw.anotar_presentacion(conn, Persona(ana), 2026, 3, hoja_sha256=nueva.sha256,
                                referencia=REFERENCIA, importe_declarado=Decimal("-420"))
    # Se reabre (con motivo y la rev de lo que se vio) y se vuelve a marcar con la hoja nueva.
    rev = btw.periodo(conn, 2026, 3)["rev"]
    with pytest.raises(FaltaMotivo):
        btw.reabrir(conn, Persona(ana), 2026, 3, rev=rev)
    with pytest.raises(Conflicto):
        btw.reabrir(conn, Persona(ana, motivo=MOTIVO), 2026, 3, rev=rev - 1)
    btw.reabrir(conn, Persona(ana, motivo=MOTIVO), 2026, 3, rev=rev)
    fila = btw.periodo(conn, 2026, 3)
    assert (fila["estado"], fila["hoja_sha256"], fila["listo_por"]) == ("abierto", None, None)
    with pytest.raises(btw.EstadoNoValido, match="ya esta abierto"):
        btw.reabrir(conn, Persona(ana, motivo=MOTIVO), 2026, 3, rev=fila["rev"])
    with pytest.raises(btw.EstadoNoValido, match="desde listo"):
        btw.anotar_presentacion(conn, Persona(ana), 2026, 3, hoja_sha256=nueva.sha256,
                                referencia=REFERENCIA, importe_declarado=Decimal("-420"))
    _listo(conn, ana)
    assert conn.execute("SELECT count(*) FROM hoja_btw").fetchone()[0] == 2
    # Se presenta despues del trimestre y no en el futuro, con la referencia del acuse.
    for dia in (date(2026, 9, 30), date(2026, 10, 15)):
        with pytest.raises(ValueError, match="despues del trimestre"):
            btw.anotar_presentacion(conn, Persona(ana), 2026, 3, hoja_sha256=nueva.sha256,
                                    referencia=REFERENCIA, importe_declarado=Decimal("-420"),
                                    fecha=dia)
    with pytest.raises(FaltaMotivo):
        btw.anotar_presentacion(conn, Persona(ana), 2026, 3, hoja_sha256=nueva.sha256,
                                referencia="  ", importe_declarado=Decimal("-420"))
    # Sola con gestionar_btw, Ana la marca y la anota: queda autorrevisado.
    evento = btw.anotar_presentacion(conn, Persona(ana), 2026, 3, hoja_sha256=nueva.sha256,
                                     referencia=REFERENCIA, importe_declarado=Decimal("-420"),
                                     fecha=date(2026, 10, 1))
    assert _datos_evento(conn, evento)["autorrevisado"] is True
    assert btw.periodo(conn, 2026, 3)["presentado_en"] == "2026-10-01"
    assert btw.verificar(conn) == [] and verificar_evidencia(conn) == []


def test_solo_una_persona_con_gestionar_btw_pone_el_estado(almacen, ana) -> None:
    conn = almacen.conn
    carla = persona(conn, "Carla", "consulta")
    hoja = btw.hoja(conn, 2026, 3)
    with pytest.raises(PermisoDenegado):
        btw.marcar_lista(conn, Persona(carla), 2026, 3, hoja_sha256=hoja.sha256)
    # Ni por detras de btw.py: la base no deja escribir el periodo a quien no tiene el permiso
    # ni a un usuario de sistema.
    with pytest.raises(sqlite3.IntegrityError, match="gestionar_btw"):
        with orden_auditada(conn):
            btw._escribir(conn, Persona(carla), None, 2026, 3, {}, tipo="btw_reabierto",
                          motivo=None, datos={})
    motor = usuario_sistema(conn, "motor")
    valores = {"ano": 2026, "trimestre": 3, "inicio": "2026-07-01", "fin": "2026-09-30",
               "limite_presentacion": "2026-10-31", "limite_pago": "2026-10-31",
               "estado": "abierto"}
    with pytest.raises(sqlite3.IntegrityError, match="gestionar_btw"):
        with orden_auditada(conn):
            registrar(conn, tipo="btw_reabierto", actor=motor, usuario_id=None,
                      tabla="periodo_btw", fila_id=1, cambios=btw._cambios_alta(1, valores, None))
            conn.execute("INSERT INTO periodo_btw (id, ano, trimestre, inicio, fin, "
                         "limite_presentacion, limite_pago, estado) VALUES (1, :ano, :trimestre, "
                         ":inicio, :fin, :limite_presentacion, :limite_pago, :estado)", valores)
    # Un trimestre no nace presentado, aunque lo escriba quien puede.
    with pytest.raises(sqlite3.IntegrityError, match="no al darlo de alta"):
        with orden_auditada(conn):
            btw._escribir(conn, Persona(ana), None, 2026, 3, {
                "estado": "presentado", "presentado_en": "2026-10-10", "presentado_por": ana,
                "referencia_presentacion": REFERENCIA, "importe_declarado_cent": 0,
                "listo_en": "2026-10-10T09:00:00+00:00", "listo_por": ana},
                tipo="btw_presentacion_anotada", motivo=None, datos={})
    assert btw.periodo(conn, 2026, 3) is None


def test_la_primera_hoja_lista_apunta_la_configuracion_que_usa(almacen, ana) -> None:
    """El hash de la configuracion que lleva la hoja (y el evento de listo) es el de una fila
    de politica_version: se resuelve a un texto con una consulta (revision del paso 11)."""
    conn = almacen.conn
    assert politica.vigente(conn, politica.FICHERO_BTW) is None
    antes = btw.hoja(conn, 2026, 3)
    _listo(conn, ana)
    fila = politica.vigente(conn, politica.FICHERO_BTW)
    assert politica.config_btw_de_yaml(fila["contenido"]) == politica.ConfigBtw()
    [linea] = [l for l in btw.hoja(conn, 2026, 3).texto.split("\r\n")
               if l.startswith("Configuración (btw.yaml);")]
    sha = linea.split(";")[1]
    assert sha == fila["sha256"] and sha in antes.texto
    assert conn.execute("SELECT count(*) FROM politica_version WHERE sha256 = ?",
                        (sha,)).fetchone()[0] == 1
    evento = conn.execute("SELECT id FROM evento WHERE tipo = 'btw_lista_revision'").fetchone()
    assert _datos_evento(conn, evento["id"])["configuracion"] == sha
    assert btw.trimestre(conn, 2026, 3)["configuracion"]["sha256"] == sha


def test_el_resumen_trae_el_trimestre_en_curso_los_pendientes_y_el_ano(almacen, ana) -> None:
    conn = almacen.conn
    _alta(conn, "V-2025", sentido="saliente", fecha="2025-12-10")
    _alta(conn, "V-T1", sentido="saliente", fecha="2026-02-10")
    _alta(conn, "V-T3", sentido="saliente", fecha="2026-08-10", base="2000.00", iva="420.00")
    _alta(conn, "C-T4", fecha="2026-10-02", base="100.00", iva="21.00")
    _alta(conn, "C-futura", fecha="2026-11-02", base="100.00", iva="21.00")
    _alta(conn, "C-sin-fecha", fecha=None)
    r = btw.resumen(conn)
    assert (r["actual"]["etiqueta"], r["actual"]["estado"]) == ("2026-T4", "abierto")
    # El segundo trimestre no tiene facturas y tambien se declara.
    assert [(a["etiqueta"], a["estado"], a["limite_presentacion"]) for a in r["por_presentar"]] \
        == [("2026-T3", "abierto", "2026-10-31"), ("2026-T2", "abierto", "2026-07-31"),
            ("2026-T1", "abierto", "2026-04-30"), ("2025-T4", "abierto", "2026-01-31")]
    ano = r["ano_hasta_hoy"]
    assert (ano["ano"], ano["ingresos_cent"], ano["5a"], ano["5b"]) == (2026, 300_000, 63_000,
                                                                       2_100)
    assert r["sin_fecha"] == 1
    _presentar(conn, ana, importe="420")
    r = btw.resumen(conn)
    assert "2026-T3" not in {a["etiqueta"] for a in r["por_presentar"]}
    assert {a["etiqueta"]: a["estado"] for a in r["anteriores"]}["2026-T3"] == "presentado"


# ============================================================ la configuracion

def test_la_configuracion_de_partida_es_config_btw_yaml() -> None:
    texto = (RAIZ / "config" / "btw.yaml").read_text(encoding="utf-8")
    config = politica.config_btw_de_yaml(texto)
    assert config == politica.ConfigBtw() and not config.confirmado
    assert politica.config_btw_de_yaml(politica.btw_a_yaml(config)) == config
    assert config.rubrica("entrante", "autoliquidacion:nacional") == "2a"
    assert config.rubrica("saliente", "estandar:2100") == "1a"
    # Los parametros de E5 y E7 son los de la Politica de las reglas.
    reglas = politica.politica_de(None, None, texto)
    assert (reglas.iva_tipos_habituales_pb, reglas.kor_umbral_cent, reglas.kor_aviso_pct) == (
        (0, 900, 2100), 2_000_000, 90)


@pytest.mark.parametrize("antes, despues", [
    ("periodicidad: trimestral", "periodicidad: mensual"),
    ("sistema: factuurstelsel", "sistema: kasstelsel"),
    ("presentacion: ultimo_dia_mes_siguiente", "presentacion: dia_15"),
    ("confirmado: false", "confirmado: quizas"),
    ('    "21": 1a', '    "21": 5b'),
    ("    otros: 1c\n", ""),
    ("compras:\n  estandar: 5b", "compras:\n  estandar: 1a"),
    ("    ue: 4b", "    ue: 1a"),
    ('  autoliquidacion: "21"', '  autoliquidacion: "0"'),
    ('umbral: "20000.00"', 'umbral: "500.00"'),
    ("aviso_pct: 90", "aviso_pct: 10"),
    ("  tipo_cero: fuera\n  exento: fuera\n  kor: fuera", "  tipo_cero: fuera\n  exento: fuera"),
    # Revision del paso 11: 1e no lleva columna de IVA, solo admite el tipo cero (una venta
    # al 21 % alli perderia de 5a la cuota cobrada), y el tipo cero solo va a 1e.
    ('    "21": 1a', '    "21": 1e'),
    ("    otros: 1c", "    otros: 1e"),
    ('    "0": 1e', '    "0": 1a'),
    # Un umbral con mas de dos decimales no se trunca en silencio.
    ('umbral: "20000.00"', 'umbral: "20000.009"'),
])
def test_un_btw_yaml_que_la_v1_no_sabe_aplicar_no_se_carga(antes, despues) -> None:
    texto = (RAIZ / "config" / "btw.yaml").read_text(encoding="utf-8")
    assert texto.count(antes) == 1, antes
    with pytest.raises(politica.PoliticaNoValida):
        politica.config_btw_de_yaml(texto.replace(antes, despues))


def test_la_configuracion_cargada_va_en_la_hoja_y_cambia_las_cifras(almacen, ana,
                                                                    tmp_path) -> None:
    conn = almacen.conn
    admin = persona(conn, "Irene", "administrador")
    _alta(conn, "C-gb", base="200.00", iva="0.00", tipo_iva=None,
          tratamiento="autoliquidacion", btw_doc="GB123456789")
    assert _rubricas(_cifras(conn)) == {"4a": (20_000, 4_200)}
    antes = btw.hoja(conn, 2026, 3)
    ruta = tmp_path / "btw.yaml"
    ruta.write_text((RAIZ / "config" / "btw.yaml").read_text(encoding="utf-8").replace(
        "confirmado: false", "confirmado: true").replace("    fuera_ue: 4a", "    fuera_ue: 2a"),
        encoding="utf-8")
    with pytest.raises(PermisoDenegado):
        politica.cargar(conn, ruta, ana)
    resumen, nuevo = politica.cargar(conn, ruta, admin)
    assert nuevo and "trimestral" in resumen
    t = btw.trimestre(conn, 2026, 3)
    assert _rubricas(t["cifras"]) == {"2a": (20_000, 4_200)}
    assert t["configuracion"]["confirmada"] and t["hoja_sha256"] != antes.sha256
    assert "confirmada por el asesor" in btw.hoja(conn, 2026, 3).texto
    with pytest.raises(Conflicto):
        btw.marcar_lista(conn, Persona(ana), 2026, 3, hoja_sha256=antes.sha256)


# ============================================================ E7 con el maestro de clientes

def test_e7_lee_la_marca_del_maestro_de_clientes(almacen, ana) -> None:
    from bms_agent.importadores.registrar import importar_fichero

    conn = almacen.conn
    importar_fichero(almacen, "exact", "clientes", EXACT_CLIENTES, lanzado_por=ana)
    clientes = dict(conn.execute("SELECT exact_id, id FROM cliente"))
    haven = _alta(conn, "V-haven", sentido="saliente", tratamiento="autoliquidacion",
                  iva="0.00", tipo_iva=None, cliente_id=clientes["10001"])
    schiedam = _alta(conn, "V-schiedam", sentido="saliente", tratamiento="autoliquidacion",
                     iva="0.00", tipo_iva=None, cliente_id=clientes["10002"])
    hallazgos.recalcular(conn)
    abiertos = {h["factura_id"] for h in conn.execute(
        "SELECT factura_id FROM hallazgo WHERE regla = 'E7' AND estado = 'abierto'")}
    assert haven in abiertos and schiedam not in abiertos


# ============================================================ CLI, API y comprobaciones

def test_el_btw_por_la_cli(tmp_path, capsys) -> None:
    from bms_agent import permisos
    from bms_agent.almacen import preparar
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    with preparar(db) as almacen:
        conn = almacen.conn
        ana = persona(conn, "Ana", "administracion")
        token = permisos.emitir_token(conn, ana)
        _alta(conn, "V-1", sentido="saliente", base="1000.00", iva="210.00")
        _alta(conn, "C-1", base="2000.00", iva="420.00")
        hallazgos.recalcular(conn)
    assert main(["btw", "ver", "2026-T3", "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    assert "BTW 2026-T3 (2026-07-01 a 2026-09-30): abierto" in salida
    # La CLI va con el reloj de verdad: los dias que faltan dependen de hoy.
    assert "plazo de presentacion y pago: 2026-10-31 (" in salida
    assert "a devolver" in salida and "POR CONFIRMAR CON EL ASESOR" in salida
    hoja = tmp_path / "hoja.csv"
    assert main(["btw", "hoja", "2026-T3", "--salida", str(hoja), "--db", str(db)]) == 0
    sha = hashlib.sha256(hoja.read_bytes()).hexdigest()
    assert f"sha256 {sha}" in capsys.readouterr().out
    # Sin --salida, en pantalla van los mismos bytes (con su BOM) cuyo sha256 se dice: una
    # hoja guardada con `> hoja.csv` da el hash que queda en el periodo.
    assert main(["btw", "hoja", "2026-T3", "--db", str(db)]) == 0
    salida = capsys.readouterr()
    assert salida.out.encode("utf-8") == hoja.read_bytes()
    assert hashlib.sha256(salida.out.encode("utf-8")).hexdigest() == sha
    assert f"sha256 {sha}" in salida.err
    assert main(["btw", "hoja", "2026-T5", "--db", str(db)]) == 1
    capsys.readouterr()
    # `btw estado` (el nombre del §6) es `btw ver`.
    assert main(["btw", "estado", "2026-T3", "--db", str(db)]) == 0
    assert "BTW 2026-T3 (2026-07-01 a 2026-09-30): abierto" in capsys.readouterr().out
    # Marcar lista y anotar piden un motivo (§6); anotar, ademas, la rev del periodo.
    listo = ["btw", "listo", "--trimestre", "2026-T3", "--hoja-sha256", sha, "--token",
             token, "--db", str(db)]
    assert main(listo) != 0
    assert "pide un motivo" in capsys.readouterr().err
    assert main([*listo, "--motivo", "Revisada con el asesor"]) == 0
    capsys.readouterr()
    assert main(["btw", "ver", "2026-T3", "--json", "--db", str(db)]) == 0
    rev = json.loads(capsys.readouterr().out)["rev"]
    # Lo declarado a devolver va en negativo, sin separador de miles.
    anotar = ["btw", "anotar", "--trimestre", "2026-T3", "--hoja-sha256", sha,
              "--referencia", REFERENCIA, "--importe-declarado", "-1234,56",
              "--motivo", "Presentada en el portal", "--token", token, "--db", str(db)]
    assert main([*anotar, "--rev", str(rev + 1)]) != 0
    assert "cambio" in capsys.readouterr().err
    assert main([*anotar, "--rev", str(rev)]) == 0
    capsys.readouterr()
    assert main(["btw", "ver", "2026-T3", "--json", "--db", str(db)]) == 0
    datos = json.loads(capsys.readouterr().out)
    assert (datos["estado"], datos["importe_declarado_cent"], datos["referencia"],
            datos["hoja_marcada_sha256"], datos["presentado_por"]) == (
        "presentado", -123_456, REFERENCIA, sha, "Ana")
    assert main(["btw", "reabrir", "--trimestre", "2026-T3", "--rev", str(datos["rev"]),
                 "--motivo", MOTIVO, "--token", token, "--db", str(db)]) != 0
    capsys.readouterr()
    assert main(["btw", "ver", "--db", str(db)]) == 0
    assert re.match(r"BTW \d{4}-T[1-4] ", capsys.readouterr().out)
    assert main(["db", "verificar", "--db", str(db)]) == 0


@pytest.fixture
def servidor_btw(tmp_path):
    """El servidor de verdad sobre un almacen con una venta y una compra del tercer
    trimestre."""
    import threading

    from test_consola import AgenteFalso

    from bms_agent import permisos
    from bms_agent.almacen import preparar
    from bms_agent.serve import crear_servidor

    db = tmp_path / "datos" / "bms.sqlite3"
    with preparar(db) as almacen:
        conn = almacen.conn
        ana = persona(conn, "Ana", "administracion")
        carla = persona(conn, "Carla", "consulta")
        _alta(conn, "V-1", sentido="saliente", base="1000.00", iva="210.00")
        _alta(conn, "C-1", base="2000.00", iva="420.00")
        tokens = {"ana": permisos.emitir_token(conn, ana),
                  "carla": permisos.emitir_token(conn, carla)}
    srv = crear_servidor(tmp_path / "facturas", tmp_path / "out", 0, token="token-del-servidor",
                         agente=AgenteFalso(), ruta_db=db)
    hilo = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    hilo.start()
    try:
        yield srv.server_address[1], tokens
    finally:
        srv.shutdown()
        srv.server_close()


def test_el_btw_por_la_api(servidor_btw) -> None:
    from test_consola import _leer, _orden, _pedir

    puerto, tokens = servidor_btw
    estado, _c, datos = _leer(puerto, "/api/v2/btw", tokens["carla"])
    assert estado == 200 and datos["btw"]["actual"]["etiqueta"] == "2026-T4"
    estado, _c, datos = _leer(puerto, "/api/v2/btw/2026-T3", tokens["carla"])
    assert estado == 200
    assert (datos["trimestre"]["limite_presentacion"], datos["trimestre"]["cifras"]["5c"]) == (
        "2026-10-31", -21_000)
    estado, _c, hoja = _leer(puerto, "/api/v2/btw/2026-T3/hoja", tokens["carla"])
    assert estado == 200 and hoja["trimestre"] == "2026-T3"
    assert hoja["sha256"] == hashlib.sha256(hoja["texto"].encode("utf-8")).hexdigest()
    for ruta in ("/api/v2/btw/2026-T9", "/api/v2/btw/hoy", "/api/v2/btw/2026-T3/otra"):
        assert _leer(puerto, ruta, tokens["carla"])[0] == 404, ruta
    assert _pedir(puerto, "GET", "/api/v2/btw")[0] == 401
    cuerpo = {"accion": "btw_lista_para_revision",
              "datos": {"trimestre": "2026-T3", "hoja_sha256": hoja["sha256"], "motivo": MOTIVO}}
    assert _orden(puerto, tokens["carla"], cuerpo)[0] == 403
    estado, respuesta = _orden(puerto, tokens["ana"], cuerpo)
    assert estado == 200, respuesta
    # El trimestre en curso no se marca, y se presenta la hoja que se marco.
    assert _orden(puerto, tokens["ana"], {"accion": "btw_lista_para_revision", "datos": {
        "trimestre": "2026-T4", "hoja_sha256": hoja["sha256"], "motivo": MOTIVO}})[0] == 409
    _e, _c, visto = _leer(puerto, "/api/v2/btw/2026-T3", tokens["carla"])
    rev = visto["trimestre"]["rev"]
    assert _orden(puerto, tokens["ana"], {"accion": "btw_anotar_presentacion", "datos": {
        "trimestre": "2026-T3", "rev": rev, "hoja_sha256": "0" * 64, "referencia": REFERENCIA,
        "importe_declarado": "-210,00", "motivo": MOTIVO}})[0] == 409
    estado, respuesta = _orden(puerto, tokens["ana"], {"accion": "btw_anotar_presentacion",
                                                       "datos": {
        "trimestre": "2026-T3", "rev": rev, "hoja_sha256": hoja["sha256"],
        "referencia": REFERENCIA, "importe_declarado": "-210,00", "motivo": MOTIVO}})
    assert estado == 200, respuesta
    _e, _c, datos = _leer(puerto, "/api/v2/btw/2026-T3", tokens["carla"])
    assert datos["trimestre"]["estado"] == "presentado"


def test_verificar_ve_un_periodo_una_hoja_o_lo_declarado_tocados_por_detras(almacen,
                                                                           ana) -> None:
    conn = almacen.conn
    _alta(conn, "C-1")
    _presentar(conn, ana, importe="-210")
    assert btw.verificar(conn) == [] and verificar_evidencia(conn) == []
    for disparador in ("periodo_btw_guarda_update", "periodo_btw_presentado_no_cambia",
                       "periodo_btw_de_persona_update", "hoja_btw_sin_update",
                       "periodo_btw_declarada_sin_update"):
        conn.execute(f"DROP TRIGGER {disparador}")
    conn.execute("UPDATE periodo_btw SET importe_declarado_cent = 0")
    conn.execute("UPDATE hoja_btw SET contenido = contenido || 'x'")
    conn.execute("UPDATE periodo_btw_declarada SET base_cent = 1")
    assert any("importe_declarado_cent no es lo que dejo" in p for p in btw.verificar(conn))
    problemas = verificar_evidencia(conn)
    assert any(p.startswith("hoja_btw") for p in problemas), problemas
    assert any("periodo_btw_declarada" in p for p in problemas), problemas


def test_las_guardas_del_periodo_son_las_del_script(db) -> None:
    import importlib.util

    from bms_agent.almacen.migrar import disponibles

    spec = importlib.util.spec_from_file_location("guardas", RAIZ / "scripts" / "generar_guardas.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    sql = next(m.sql for m in disponibles() if m.version == 14)
    assert modulo.guardas("periodo_btw", modulo.columnas(db, "periodo_btw")) in sql
    columnas = [c["name"] for c in db.execute("PRAGMA table_info(periodo_btw)")
                if c["name"] not in ("id", "rev")]
    assert tuple(columnas) == btw.COLUMNAS


def test_btw_no_habla_con_nadie_de_fuera() -> None:
    """Regla 5: el agente no presenta nada ni se conecta a la Belastingdienst."""
    arbol = ast.parse((RAIZ / "src" / "bms_agent" / "btw.py").read_text(encoding="utf-8"))
    importados = {a.name.split(".")[0] for n in ast.walk(arbol) if isinstance(n, ast.Import)
                  for a in n.names}
    importados |= {(n.module or "").split(".")[0] for n in ast.walk(arbol)
                   if isinstance(n, ast.ImportFrom) and n.level == 0}
    assert not importados & {"http", "urllib", "socket", "ssl", "smtplib", "requests",
                             "httpx", "anthropic", "subprocess"}


# ============================================================ correcciones de la revision

def _linea(conn, factura_id: int, orden: int, tipo: str | None) -> None:
    """Una linea de factura con su tipo de IVA, como la daria la extraccion."""
    origen = Automatico("extraccion", usuario_sistema(conn, "extractor"))
    with campos.orden(conn, origen, tipo="factura_alta") as o:
        o.crear("factura_linea", {k: v for k, v in {
            "factura_id": factura_id, "orden": orden, "importe_cent": Decimal("500.00"),
            "tipo_iva_pb": None if tipo is None else Decimal(tipo)}.items() if v is not None})


def _abiertos(conn, factura_id: int) -> set[str]:
    return {r[0] for r in conn.execute(
        "SELECT regla FROM hallazgo WHERE factura_id = ? AND estado = 'abierto'", (factura_id,))}


def test_e0_y_la_declaracion_dicen_lo_mismo_de_lo_que_falta(almacen) -> None:
    """Revision del paso 11: lo que E0 acepta, la declaracion lo clasifica; lo que no se
    puede clasificar, E0 lo dice o la factura va igual a la lista de revisar."""
    conn = almacen.conn
    # Una venta con el tipo solo en sus lineas (un tipo) va a 1a con su base y su cuota.
    lineas = _alta(conn, "V-lin", sentido="saliente", base="1000.00", iva="210.00",
                   tipo_iva=None)
    _linea(conn, lineas, 1, "21")
    _linea(conn, lineas, 2, "21")
    # Con dos tipos en las lineas y sin desglose no se sabe que base va a 1a y cual a 1b: E0.
    mezcla = _alta(conn, "V-mezcla", sentido="saliente", base="1000.00", iva="150.00",
                   tipo_iva=None)
    _linea(conn, mezcla, 1, "21")
    _linea(conn, mezcla, 2, "9")
    # Una fila con IVA normal sin tipo bajo una cabecera con IVA trasladado: E0.
    fila = _alta(conn, "V-fila", sentido="saliente", base="700.00", iva="105.00",
                 tipo_iva=None, tratamiento="autoliquidacion",
                 desglose=(("estandar", None, "500.00", "105.00"),
                           ("autoliquidacion", None, "200.00", None)))
    # Sin base no se declara; no es de E0 (es Q1), pero va a la lista.
    sin_base = _alta(conn, "C-sin-base", base=None, iva="21.00")
    hallazgos.recalcular(conn)
    assert "E0" not in _abiertos(conn, lineas)
    assert "E0" in _abiertos(conn, mezcla) and "E0" in _abiertos(conn, fila)
    assert "E0" not in _abiertos(conn, sin_base)
    t = btw.trimestre(conn, 2026, 3)
    assert _rubricas(t["cifras"])["1a"] == (100_000, 21_000)
    assert ";V-lin;Parte V-lin;2026-08-10;estandar;21;1000,00;210,00;;1a;" in btw.hoja(
        conn, 2026, 3).texto
    fuera = {f["factura_id"] for f in t["cifras"]["sin_clasificar"]}
    assert fuera == {mezcla, fila, sin_base}
    revisar = {r["factura_id"]: r for r in t["revisar"]}
    assert fuera <= set(revisar)
    assert "E0" in revisar[mezcla]["reglas"] and "E0" in revisar[fila]["reglas"]
    assert revisar[sin_base]["fuera_de_las_cifras"] == "sin base imponible"
    assert "\r\n" + f"{sin_base};C-sin-base;Parte C-sin-base;;sin base imponible\r\n" in \
        btw.hoja(conn, 2026, 3).texto.split("Facturas que piden revisar el IVA")[1]


def test_lo_que_no_se_pudo_leer_lo_dice_el_motivo() -> None:
    """Un tipo o una cuota ilegibles no son E0 (son Q2): el motivo no cita solo un E0 que no
    existe."""
    linea = btw.LineaBtw(1, None, "saliente", "factura", "V-1", "Cliente", date(2026, 8, 10),
                         "estandar", None, 100_000, None, None, "nacional")
    c = btw.clasificar(linea, politica.ConfigBtw())
    assert c.rubrica is None and "Q2" in c.motivo and "E0" in c.motivo


def test_una_venta_con_iva_en_una_rubrica_sin_iva_no_pierde_la_cuota() -> None:
    """Defensa (el cargador ya lo rechaza): una venta al 21 % que la configuracion pusiera en
    1e no suma su base sin la cuota; queda sin clasificar."""
    ventas = tuple(sorted({**dict(politica.ConfigBtw().ventas), "estandar:2100": "1e"}.items()))
    config = politica.ConfigBtw(ventas=ventas)
    linea = btw.LineaBtw(1, None, "saliente", "factura", "V-1", "Cliente", date(2026, 8, 10),
                         "estandar", 2100, 1_000_000, 210_000, None, "nacional")
    c = btw.cifras([linea], config)
    assert c.rubricas["1e"] == [0, 0] and c.iva_a_declarar_cent == 0
    assert [x.linea.factura_id for x in c.sin_clasificar] == [1]
    assert "1e" in c.sin_clasificar[0].motivo
    # Al tipo cero, 1e es lo suyo.
    cero = dataclasses.replace(linea, tipo_iva_pb=0, cuota_cent=0)
    assert btw.cifras([cero], config).rubricas["1e"] == [1_000_000, 0]


def test_un_duplicado_o_una_lectura_dudosa_del_iva_piden_revisarlo(almacen, ana) -> None:
    """Revision del paso 11: dos compras con el mismo numero de la misma contraparte (B2)
    sumarian el IVA dos veces; la lista de revisar las ensena aunque B2 no sea de IVA."""
    conn = almacen.conn
    a = _alta(conn, "C-77", nombre="Schoonmaak BV", btw_doc="NL001234567B01")
    b = _alta(conn, "C-77", nombre="Schoonmaak BV", btw_doc="NL001234567B01")
    hallazgos.recalcular(conn)
    assert "B2" in _abiertos(conn, a) | _abiertos(conn, b)
    t = btw.trimestre(conn, 2026, 3)
    assert t["cifras"]["5b"] == 42_000
    revisar = {r["factura_id"]: r["reglas"] for r in t["revisar"]}
    assert "B2" in revisar.get(a, []) + revisar.get(b, [])
    assert "B2" in btw.hoja(conn, 2026, 3).texto.split("Facturas que piden revisar el IVA")[1]


def test_resolver_un_hallazgo_entre_listo_y_anotar_no_obliga_a_marcar_otra_vez(almacen,
                                                                              ana) -> None:
    """Revision del paso 11: la hoja marcada lleva la huella de sus cifras; lo que se revisa
    (los hallazgos, los nombres) puede cambiar hasta anotar, las cifras no."""
    conn = almacen.conn
    raro = _alta(conn, "C-6", base="1000.00", iva="60.00", tipo_iva="6")
    hoja = _listo(conn, ana)
    assert btw.huella_escrita(hoja.texto) == hoja.cifras_sha256
    hallazgos.recalcular(conn)       # abre E7 (un tipo que no es de la lista)
    assert "E7" in _abiertos(conn, raro)
    t = btw.trimestre(conn, 2026, 3)
    assert t["hoja_sha256"] != hoja.sha256 and not t["hoja_al_dia"]
    assert t["cifras_al_dia"] and t["cifras_sha256"] == hoja.cifras_sha256
    # Una cifra que cambia si obliga: una compra mas del trimestre.
    otra = _alta(conn, "C-tarde")
    with pytest.raises(Conflicto, match="cifras"):
        btw.anotar_presentacion(conn, Persona(ana), 2026, 3, hoja_sha256=hoja.sha256,
                                referencia=REFERENCIA, importe_declarado=Decimal("-60"))
    servicios.ejecutar(conn, "anular_factura", {
        "factura_id": otra, "rev": _rev_factura(conn, otra), "motivo": "No era"},
        usuario_id=ana)
    evento = btw.anotar_presentacion(conn, Persona(ana), 2026, 3, hoja_sha256=hoja.sha256,
                                     referencia=REFERENCIA, importe_declarado=Decimal("-60"))
    fila = btw.periodo(conn, 2026, 3)
    assert (fila["estado"], fila["hoja_sha256"]) == ("presentado", hoja.sha256)
    datos = _datos_evento(conn, evento)
    assert (datos["hoja_sha256"], datos["cifras_sha256"]) == (hoja.sha256, hoja.cifras_sha256)


def test_en_enero_se_ve_el_cuarto_trimestre_aunque_este_vacio(almacen) -> None:
    """Revision del paso 11: el cuarto trimestre vence el 31 de enero; sin facturas tambien
    se declara."""
    r = btw.resumen(almacen.conn, hoy=date(2027, 1, 15))
    assert r["actual"]["etiqueta"] == "2027-T1"
    assert [(a["etiqueta"], a["limite_presentacion"], a["dias_para_limite"])
            for a in r["por_presentar"]] == [("2026-T4", "2027-01-31", 16)]


def test_un_iva_por_revisar_de_un_trimestre_presentado_cuenta_hacia_el_siguiente(
        almacen, ana, reloj) -> None:
    """Revision del paso 11: un C4 de un trimestre ya presentado no corre contra el plazo que
    ya se cumplio; la correccion va en la declaracion siguiente."""
    conn = almacen.conn
    _alta(conn, "C-1", btw_doc="NL001234567B01")
    hallazgos.recalcular(conn)
    _presentar(conn, ana, importe="-210")
    reloj.avanzar(days=11)           # 2026-10-25: el tercero presentado vence el 31
    tarde = _alta(conn, "C-tarde", btw_doc="NL001234567B02", base="50.00", iva="10.50")
    hallazgos.recalcular(conn)
    assert "C4" in _abiertos(conn, tarde)
    motivos = conn.execute("SELECT motivos_json FROM factura_estado WHERE factura_id = ?",
                           (tarde,)).fetchone()[0]
    assert "IVA por revisar (C4)" in motivos
    assert "el BTW vence en" not in motivos and "Urgente" not in motivos


def test_un_trimestre_tiene_la_prioridad_de_sus_facturas_pagadas_o_no(almacen, ana) -> None:
    """Revision del paso 11: un trimestre no se paga; una compra pagada con E0 sigue pidiendo
    revisar su IVA y el trimestre sigue con su prioridad."""
    from bms_agent import pagos

    conn = almacen.conn
    f = _alta(conn, "C-e0", tratamiento="desconocido", btw_doc="NL001234567B01")
    hallazgos.recalcular(conn)

    def del_trimestre():
        return conn.execute("SELECT nivel FROM prioridad WHERE entidad = 'trimestre' "
                            "AND entidad_id = 20263").fetchone()

    antes = del_trimestre()
    assert antes is not None
    pagos.marcar_pagada(conn, Persona(ana, "pagada por transferencia"), factura_id=f,
                        fecha_pago=date(2026, 10, 1))
    hallazgos.recalcular(conn)
    assert conn.execute("SELECT estado_pago FROM factura_estado WHERE factura_id = ?",
                        (f,)).fetchone()[0] == "pagada"
    assert [r["factura_id"] for r in btw.trimestre(conn, 2026, 3)["revisar"]] == [f]
    assert del_trimestre() is not None and del_trimestre()[0] == antes[0]
