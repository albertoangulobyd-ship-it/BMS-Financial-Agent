"""Lo pagado (paso 7): casar el banco con las facturas, el saldo, las ordenes y K1-K8.

Puertas del paso 7 que viven aqui, sobre el almacen entero (importar,
casar, evaluar y las caches):

- un pago parcial deja la factura pendiente o vencida con lo que queda, y K2;
- pagada solo dentro de la tolerancia (0,00 por defecto);
- casar solo es automatico con referencia, importe y contraparte; si no, una
  propuesta que confirma una persona;
- una rotura de la cadena de extractos bloquea (K6);
- dos cargos iguales son un pago doble (K4);
- pagar una factura Bloqueada da K5;
- marcar pagada a mano pide motivo, y la base no deja escribir pagos por
  fuera de campos.py.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from conftest import (
    OTRA_CUENTA_PROPIA,
    RAIZ,
    apunte,
    camt053,
    cuentas_propias,
    factura_de,
    importar_camt,
    persona,
)

from bms_agent import campos, flujo_caja, hallazgos, pagos, politica, servicios
from bms_agent.campos import FaltaMotivo
from bms_agent.importadores.registrar import importar_fichero
from bms_agent.pagos import PagoNoValido
from bms_agent.permisos import usuario_por_nombre

EXACT_PROVEEDORES = RAIZ / "tests" / "fixtures" / "importacion" / "exact-proveedores-v1.csv"
VAN_DIJK = "NL02ABNA0123456789"          # 2026-4471, 2902,79, en el maestro
KOSTER = "NL20INGB0001234567"            # 2026-0912, 1781,12, la del maestro
BAKKER = "NL67INGB0006543210"            # B-2026-077, 1251,62, en el maestro
SMIT = "NL03RABO0312456789"              # 2026-112, 653,40, sin cuenta en el maestro
DESCONOCIDA = "NL53RABO0333444555"
BELASTINGDIENST = "NL86INGB0002445588"
MOTIVO = "Pagada desde la caja, recibo en la carpeta"


@pytest.fixture
def banco(tipado):
    """Las siete facturas v1, el maestro de proveedores de Exact (con sus cuentas) y las
    cuentas propias de BM Support BV. Ana lo puede todo."""
    conn = tipado.conn
    ana = persona(conn, "Ana", "administrador")
    cuentas_propias(tipado, ana)
    importar_fichero(tipado, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana)
    return tipado


def _ana(conn) -> int:
    return usuario_por_nombre(conn, "Ana")


def _estado(conn, numero: str) -> tuple:
    fila = conn.execute("SELECT e.estado_pago, e.pendiente_cent, e.nivel FROM factura_estado e "
                        "JOIN factura f ON f.id = e.factura_id WHERE f.numero = ?",
                        (numero,)).fetchone()
    return tuple(fila)


def _aplicaciones(conn, numero: str | None = None) -> list[sqlite3.Row]:
    filtro, parametros = ("WHERE f.numero = ?", (numero,)) if numero else ("", ())
    return conn.execute(f"SELECT a.*, f.numero FROM aplicacion_pago a JOIN factura f ON "
                        f"f.id = a.factura_id {filtro} ORDER BY a.id", parametros).fetchall()


def _hallazgos(conn, regla: str, *, abiertos: bool = True) -> list[sqlite3.Row]:
    filtro = " AND estado = 'abierto'" if abiertos else ""
    return conn.execute(f"SELECT * FROM hallazgo WHERE regla = ?{filtro} ORDER BY id",
                        (regla,)).fetchall()


def _de_factura(conn, regla: str, numero: str) -> list[sqlite3.Row]:
    return [h for h in _hallazgos(conn, regla)
            if h["tabla"] == "factura" and h["fila_id"] == factura_de(conn, numero)]


def _rev(conn, tabla: str, fila_id: int) -> int:
    return conn.execute(f"SELECT rev FROM {tabla} WHERE id = ?", (fila_id,)).fetchone()[0]


def _orden(conn, nombre: str, datos: dict) -> servicios.Diferencia:
    return servicios.ejecutar(conn, nombre, datos, usuario_id=_ana(conn))


def _confirmar(conn, aplicacion_id: int) -> servicios.Diferencia:
    return _orden(conn, "confirmar_pago", {
        "aplicacion_id": aplicacion_id, "rev": _rev(conn, "aplicacion_pago", aplicacion_id)})


def _limpio(conn) -> None:
    assert campos.verificar_controladas(conn) == []
    assert hallazgos.verificar(conn) == []


# ------------------------------------------------------------ casar

def test_con_referencia_importe_y_contraparte_se_casa_solo(banco) -> None:
    conn = banco.conn
    assert _estado(conn, "2026-4471")[:2] == ("pendiente", 290279)
    resultado = importar_camt(banco, _ana(conn), camt053(apunte(
        "-2902.79", iban=VAN_DIJK, nombre="Bouwtechniek Van Dijk BV",
        concepto="Factuur 2026-4471")))
    assert resultado.recalculo.conciliacion.automaticas
    [a] = _aplicaciones(conn)
    assert (a["numero"], a["fuente"], a["metodo"], a["estado"], a["importe_cent"],
            a["fecha_pago"], a["regla"]) == (
        "2026-4471", "banco", "automatica", "confirmada", 290279, "2026-10-12",
        "referencia+importe+contraparte")
    assert _estado(conn, "2026-4471")[:2] == ("pagada", 0)
    saldo = pagos.saldos(conn)[factura_de(conn, "2026-4471")]
    assert (saldo.pagada, saldo.fuente, saldo.pendiente_cent) == (True, "banco", 0)
    # Lo pagado sale del flujo de caja.
    partidas, _movidos = flujo_caja.datos(conn)
    assert factura_de(conn, "2026-4471") not in {p.factura_id for p in partidas}
    _limpio(conn)


def test_con_dos_de_tres_es_una_propuesta_que_confirma_una_persona(banco) -> None:
    conn = banco.conn
    importar_camt(banco, _ana(conn), camt053(apunte(
        "-653.40", "2026-10-13", iban=SMIT, nombre="Loodgietersbedrijf Smit",
        concepto="Factuur 2026-112")))
    [a] = _aplicaciones(conn)
    assert (a["numero"], a["metodo"], a["estado"], a["regla"]) == (
        "2026-112", "propuesta", "propuesta", "referencia+importe")
    assert a["confirmada_por"] is None
    # Una propuesta no paga nada.
    assert _estado(conn, "2026-112")[:2] == ("vencida", 65340)
    assert [p["id"] for p in pagos.propuestas(conn)] == [a["id"]]
    _confirmar(conn, a["id"])
    a = _aplicaciones(conn)[0]
    assert (a["estado"], a["confirmada_por"]) == ("confirmada", _ana(conn))
    assert _estado(conn, "2026-112")[:2] == ("pagada", 0)
    # El cargo fue a una cuenta que no es pagable para Smit: F7, aunque lo confirmara Ana.
    [f7] = _hallazgos(conn, "F7")
    assert (f7["tabla"], f7["severidad"]) == ("movimiento", "bloqueo")
    assert _estado(conn, "2026-112")[2] == "bloqueada"
    # Lo confirmado no se confirma otra vez.
    with pytest.raises(PagoNoValido, match="solo se confirma una propuesta"):
        _confirmar(conn, a["id"])
    _limpio(conn)


def test_sin_dos_coincidencias_no_se_casa_y_k7_lo_dice_pasados_los_dias(banco) -> None:
    conn = banco.conn
    ana = _ana(conn)
    _orden(conn, "anadir_beneficiario", {"iban": BELASTINGDIENST, "nombre": "Belastingdienst",
                                         "motivo": "Pagos de BTW"})
    importar_camt(banco, ana, camt053(
        # Solo el importe de la 2026-4471: nada.
        apunte("-2902.79", "2026-10-01", iban=DESCONOCIDA, nombre="Alguien"),
        # Un traspaso a otra cuenta propia y un pago a Hacienda: no se casan ni avisan.
        apunte("-500.00", "2026-10-01", iban=OTRA_CUENTA_PROPIA, concepto="Traspaso"),
        apunte("-1200.00", "2026-10-01", iban=BELASTINGDIENST, concepto="Omzetbelasting Q3"),
        # Uno de hoy: todavia esta en plazo.
        apunte("-10.00", "2026-10-13", iban=DESCONOCIDA), desde="2026-10-01"))
    assert _aplicaciones(conn) == []
    importes = {h["fila_id"]: h for h in _hallazgos(conn, "K7")}
    sin_casar = conn.execute("SELECT id FROM movimiento_bancario WHERE importe_cent = -290279"
                             ).fetchone()[0]
    assert list(importes) == [sin_casar]
    assert importes[sin_casar]["severidad"] == "aviso"
    assert _hallazgos(conn, "F7") == []
    # Lo que queda por casar: ni el traspaso ni Hacienda, que no se casan con nada.
    assert [m["id"] for m in pagos.movimientos(conn, sin_casar=True)] == [sin_casar + 3,
                                                                         sin_casar]


def test_lo_retirado_no_se_vuelve_a_proponer_y_se_puede_enlazar_a_mano(banco) -> None:
    conn = banco.conn
    importar_camt(banco, _ana(conn), camt053(apunte(
        "-653.40", "2026-10-13", iban=SMIT, concepto="Factuur 2026-112")))
    [a] = _aplicaciones(conn)
    with pytest.raises(FaltaMotivo):
        _orden(conn, "retirar_pago", {"aplicacion_id": a["id"], "rev": a["rev"]})
    _orden(conn, "retirar_pago", {"aplicacion_id": a["id"], "rev": a["rev"],
                                  "motivo": "Es de otra obra de Smit"})
    assert _aplicaciones(conn)[0]["estado"] == "retirada"
    _orden(conn, "recalcular", {})
    assert [x["estado"] for x in _aplicaciones(conn)] == ["retirada"]
    assert _estado(conn, "2026-112")[:2] == ("vencida", 65340)
    # Ana lo enlaza a mano con el movimiento: es del banco, y manual.
    movimiento = a["movimiento_id"]
    f = factura_de(conn, "2026-112")
    _orden(conn, "marcar_pagada", {"factura_id": f, "movimiento_id": movimiento,
                                   "rev": _rev(conn, "factura", f), "motivo": MOTIVO})
    enlazada = _aplicaciones(conn)[-1]
    assert (enlazada["fuente"], enlazada["metodo"], enlazada["estado"], enlazada["importe_cent"],
            enlazada["fecha_pago"]) == ("banco", "manual", "confirmada", 65340, "2026-10-13")
    assert _estado(conn, "2026-112")[:2] == ("pagada", 0)
    _limpio(conn)


# ------------------------------------------------------------ parcial y tolerancia

def test_un_pago_parcial_deja_la_factura_pendiente_con_su_saldo_y_k2(banco) -> None:
    conn = banco.conn
    importar_camt(banco, _ana(conn), camt053(apunte(
        "-600.00", "2026-10-13", iban=BAKKER, nombre="Schilderwerken Bakker",
        concepto="Factuur B-2026-077 deel 1")))
    [a] = _aplicaciones(conn)
    assert (a["metodo"], a["importe_cent"], a["regla"]) == ("propuesta", 60000,
                                                            "referencia+contraparte")
    _confirmar(conn, a["id"])
    # Sigue pendiente (vence el 16), con lo que queda; no hay plan de pagos que gestionar.
    assert _estado(conn, "B-2026-077")[:2] == ("pendiente", 65162)
    [k2] = _de_factura(conn, "K2", "B-2026-077")
    assert k2["severidad"] == "retencion" and "651,62" in k2["detalle"]
    partidas, movidos = flujo_caja.datos(conn)
    bakker = factura_de(conn, "B-2026-077")
    assert [p.importe_cent for p in partidas if p.factura_id == bakker] == [65162]
    assert [(m.importe_cent, m.direccion) for m in movidos if m.factura_id == bakker] == [
        (60000, "salida")]
    _limpio(conn)


def test_un_pago_parcial_de_una_vencida_la_deja_vencida(banco) -> None:
    conn = banco.conn
    f = factura_de(conn, "2026-112")
    _orden(conn, "marcar_pagada", {"factura_id": f, "importe": "300,00",
                                   "fecha_pago": "2026-10-10", "rev": _rev(conn, "factura", f),
                                   "motivo": MOTIVO})
    assert _estado(conn, "2026-112")[:2] == ("vencida", 35340)
    assert _de_factura(conn, "K2", "2026-112")
    # El resto, otro dia: pagada, y K2 deja de verse.
    _orden(conn, "marcar_pagada", {"factura_id": f, "fecha_pago": "2026-10-12",
                                   "rev": _rev(conn, "factura", f), "motivo": MOTIVO})
    assert [a["importe_cent"] for a in _aplicaciones(conn)] == [30000, 35340]
    assert _estado(conn, "2026-112")[:2] == ("pagada", 0)
    assert _de_factura(conn, "K2", "2026-112") == []


def test_pagada_solo_dentro_de_la_tolerancia(banco) -> None:
    conn = banco.conn
    importar_camt(banco, _ana(conn), camt053(apunte(
        "-2902.78", iban=VAN_DIJK, concepto="Factuur 2026-4471")))
    [a] = _aplicaciones(conn)
    assert (a["metodo"], a["importe_cent"]) == ("propuesta", 290278)
    _confirmar(conn, a["id"])
    # Con la tolerancia por defecto (0,00) falta un centimo: no esta pagada.
    assert _estado(conn, "2026-4471")[:2] == ("pendiente", 1)
    assert _de_factura(conn, "K2", "2026-4471")
    # Con 0,01 en la politica, si.
    carpeta = banco.documentos.raiz.parent / "reglas"
    carpeta.mkdir()
    texto = (RAIZ / "config" / "reglas.yaml").read_text(encoding="utf-8")
    assert 'tolerancia: "0.00"' in texto
    (carpeta / "reglas.yaml").write_text(texto.replace('tolerancia: "0.00"', 'tolerancia: "0.01"'),
                                         encoding="utf-8")
    politica.cargar(conn, carpeta / "reglas.yaml", _ana(conn))
    _orden(conn, "recalcular", {})
    assert _estado(conn, "2026-4471")[0] == "pagada"
    assert _de_factura(conn, "K2", "2026-4471") == []


# ------------------------------------------------------------ K4, K5, K6

def test_dos_cargos_iguales_son_un_pago_doble_k4(banco) -> None:
    conn = banco.conn
    importar_camt(banco, _ana(conn), camt053(
        apunte("-2902.79", "2026-10-12", iban=VAN_DIJK, concepto="Factuur 2026-4471"),
        apunte("-2902.79", "2026-10-13", iban=VAN_DIJK, concepto="Factuur 2026-4471")))
    # El primero paga la factura; el segundo no tiene a que casarse.
    assert [a["importe_cent"] for a in _aplicaciones(conn)] == [290279]
    [k4] = _hallazgos(conn, "K4")
    assert (k4["tabla"], k4["severidad"]) == ("movimiento", "bloqueo")
    valores = json.loads(k4["valores_json"])
    assert len(valores["movimientos"]) == 2
    # Y si alguien enlaza el segundo a la misma factura, la factura esta pagada de mas.
    segundo = conn.execute("SELECT max(id) FROM movimiento_bancario").fetchone()[0]
    f = factura_de(conn, "2026-4471")
    _orden(conn, "marcar_pagada", {"factura_id": f, "movimiento_id": segundo,
                                   "importe": "2902,79", "rev": _rev(conn, "factura", f),
                                   "motivo": MOTIVO})
    assert _de_factura(conn, "K4", "2026-4471")
    assert _de_factura(conn, "K2", "2026-4471")
    assert _estado(conn, "2026-4471")[2] == "bloqueada"


def test_pagar_una_factura_bloqueada_da_k5(banco) -> None:
    conn = banco.conn
    # La 2026-0912 de Koster lleva otra cuenta que la del maestro: esta Bloqueada desde hoy.
    assert _estado(conn, "2026-0912")[2] == "bloqueada"
    bloqueos = {h["regla"] for h in _hallazgos(conn, "F3") + _hallazgos(conn, "F2")
                if h["fila_id"] == factura_de(conn, "2026-0912")}
    assert bloqueos
    importar_camt(banco, _ana(conn), camt053(
        # Un pago de ayer, antes del bloqueo: no es K5.
        apunte("-100.00", "2026-10-13", iban=KOSTER, concepto="Factuur 2026-0912 voorschot"),
        # Y el resto hoy, con la factura Bloqueada.
        apunte("-1681.12", "2026-10-14", iban=KOSTER, concepto="Factuur 2026-0912"),
        hasta="2026-10-14"))
    koster = _aplicaciones(conn, "2026-0912")
    for a in koster:
        if a["estado"] == "propuesta":
            _confirmar(conn, a["id"])
    assert sorted(a["fecha_pago"] for a in _aplicaciones(conn, "2026-0912")) == [
        "2026-10-13", "2026-10-14"]
    [k5] = _de_factura(conn, "K5", "2026-0912")
    valores = json.loads(k5["valores_json"])
    assert valores["fecha_pago"] == "2026-10-14" and set(valores["reglas"]) == bloqueos
    assert k5["severidad"] == "retencion"


def test_un_salto_en_la_secuencia_de_extractos_bloquea_k6(banco) -> None:
    conn = banco.conn
    ana = _ana(conn)
    importar_camt(banco, ana, camt053(apunte("-10.00", "2026-10-05", iban=DESCONOCIDA),
                                      secuencia=1, identificador="S1", desde="2026-10-05",
                                      hasta="2026-10-05"), "s1.xml")
    assert _hallazgos(conn, "K6") == []
    # Falta el 2: lo que paga el 3 no se da por bueno.
    resultado = importar_camt(banco, ana, camt053(
        apunte("-2902.79", "2026-10-12", iban=VAN_DIJK, concepto="Factuur 2026-4471"),
        inicial="9990.00", secuencia=3, identificador="S3"), "s3.xml")
    tercero = resultado.lotes[0].importacion_id
    rotura = [h for h in _hallazgos(conn, "K6") if h["tabla"] == "importacion"]
    assert [(h["fila_id"], h["severidad"]) for h in rotura] == [(tercero, "bloqueo")]
    assert "falta" in rotura[0]["detalle"] or "secuencia" in rotura[0]["detalle"]
    assert _estado(conn, "2026-4471")[0] == "pagada"
    [k6] = _de_factura(conn, "K6", "2026-4471")
    assert k6["severidad"] == "bloqueo"
    assert _estado(conn, "2026-4471")[2] == "bloqueada"
    # Llega el 2 y la cadena encadena: K6 deja de verse.
    importar_camt(banco, ana, camt053(apunte("0.00", "2026-10-08"), inicial="9990.00",
                                      secuencia=2, identificador="S2", desde="2026-10-06",
                                      hasta="2026-10-08"), "s2.xml")
    assert _hallazgos(conn, "K6") == []
    _limpio(conn)


def test_un_saldo_que_no_encadena_bloquea_k6(banco) -> None:
    conn = banco.conn
    ana = _ana(conn)
    importar_camt(banco, ana, camt053(apunte("-10.00", "2026-10-05", iban=DESCONOCIDA),
                                      secuencia=1, identificador="S1", desde="2026-10-05",
                                      hasta="2026-10-05"), "s1.xml")
    importar_camt(banco, ana, camt053(apunte("-5.00", "2026-10-06", iban=DESCONOCIDA),
                                      inicial="9000.00", secuencia=2, identificador="S2",
                                      desde="2026-10-06", hasta="2026-10-06"), "s2.xml")
    [k6] = _hallazgos(conn, "K6")
    assert (k6["tabla"], k6["severidad"]) == ("importacion", "bloqueo")
    assert "9990" in k6["detalle"] or "9.990" in k6["detalle"]


# ------------------------------------------------------------ a mano y la base

def test_marcar_pagada_pide_motivo_y_no_apunta_el_futuro_ni_otra_moneda(banco) -> None:
    conn = banco.conn
    f = factura_de(conn, "2026-018")
    base = {"factura_id": f, "rev": _rev(conn, "factura", f)}
    with pytest.raises(FaltaMotivo):
        _orden(conn, "marcar_pagada", base)
    with pytest.raises(PagoNoValido, match="todavia no se ha hecho"):
        _orden(conn, "marcar_pagada", {**base, "fecha_pago": "2026-10-15", "motivo": MOTIVO})
    usd = factura_de(conn, "NW-2026-0042")
    with pytest.raises(PagoNoValido, match="X1"):
        _orden(conn, "marcar_pagada", {"factura_id": usd, "rev": _rev(conn, "factura", usd),
                                       "motivo": MOTIVO})
    assert _aplicaciones(conn) == []
    _orden(conn, "marcar_pagada", {**base, "fecha_pago": "2026-10-01", "motivo": MOTIVO})
    [a] = _aplicaciones(conn)
    assert (a["fuente"], a["metodo"], a["estado"], a["importe_cent"], a["motivo"],
            a["confirmada_por"]) == ("manual", "manual", "confirmada", 152000, MOTIVO, _ana(conn))
    assert _estado(conn, "2026-018")[:2] == ("pagada", 0)
    # Sin extractos que cubran los dias siguientes, K3 no sabe; con uno al dia, avisa.
    assert _de_factura(conn, "K3", "2026-018") == []
    importar_camt(banco, _ana(conn), camt053(apunte("-0.50", "2026-10-12"),
                                             desde="2026-10-02"))
    [k3] = _de_factura(conn, "K3", "2026-018")
    assert k3["severidad"] == "aviso"
    # Una orden sobre otra version de la factura es un conflicto.
    with pytest.raises(campos.Conflicto):
        _orden(conn, "marcar_pagada", {**base, "rev": base["rev"] + 1, "motivo": MOTIVO,
                                       "importe": "1,00"})


def test_lo_de_exact_no_se_retira_aqui_y_el_banco_manda(banco) -> None:
    conn = banco.conn
    carpeta = banco.documentos.raiz.parent
    cabecera = (RAIZ / "tests" / "fixtures" / "importacion" / "exact-pagos_exact-v1.csv"
                ).read_text(encoding="utf-8-sig").splitlines()[0]
    ruta = carpeta / "pagos.csv"
    ruta.write_text(f"{cabecera}\nInkoop;20001;2026-4471;2.902,79;2.402,79;;10-10-2026;EUR\n",
                    encoding="utf-8")
    importar_fichero(banco, "exact", "pagos_exact", ruta, lanzado_por=_ana(conn))
    [exact] = _aplicaciones(conn)
    assert (exact["fuente"], exact["importe_cent"]) == ("exact", 50000)
    with pytest.raises(PagoNoValido, match="Exact"):
        _orden(conn, "retirar_pago", {"aplicacion_id": exact["id"], "rev": exact["rev"],
                                      "motivo": "No"})
    assert _estado(conn, "2026-4471")[:2] == ("pendiente", 240279)
    # Llega el banco con el pago entero: manda el banco, y K8 dice que no coinciden.
    importar_camt(banco, _ana(conn), camt053(apunte(
        "-2902.79", iban=VAN_DIJK, concepto="Factuur 2026-4471")))
    assert _estado(conn, "2026-4471")[:2] == ("pagada", 0)
    assert pagos.saldos(conn)[factura_de(conn, "2026-4471")].fuente == "banco"
    [k8] = _de_factura(conn, "K8", "2026-4471")
    assert json.loads(k8["valores_json"]) == {"banco_cent": 290279, "exact_cent": 50000}


# ------------------------------------------------------------ revision del paso 7

def _marcar(conn, numero: str, **datos) -> servicios.Diferencia:
    f = factura_de(conn, numero)
    return _orden(conn, "marcar_pagada", {"factura_id": f, "rev": _rev(conn, "factura", f),
                                          "motivo": MOTIVO, **datos})


def _movimiento_de(conn, iban: str) -> int:
    return conn.execute("SELECT id FROM movimiento_bancario WHERE contraparte_iban = ?",
                        (iban,)).fetchone()[0]


def test_enlazar_un_movimiento_no_paga_mas_de_lo_que_queda_de_el(banco) -> None:
    """Un cargo de 10,00 no paga una factura de 2902,79, ni dos veces, ni Hacienda paga una
    factura: un enlace a mano es evidencia del banco y apaga K3 (revision del paso 7)."""
    conn = banco.conn
    _orden(conn, "anadir_beneficiario", {"iban": BELASTINGDIENST, "nombre": "Belastingdienst",
                                         "motivo": "Pagos de BTW"})
    importar_camt(banco, _ana(conn), camt053(apunte("-10.00", iban=DESCONOCIDA),
                                             apunte("-12.00", iban=BELASTINGDIENST)))
    diez, hacienda = _movimiento_de(conn, DESCONOCIDA), _movimiento_de(conn, BELASTINGDIENST)
    with pytest.raises(PagoNoValido, match="quedan 10.00"):
        _marcar(conn, "2026-4471", movimiento_id=diez, importe="2902,79")
    with pytest.raises(PagoNoValido, match="beneficiario conocido"):
        _marcar(conn, "2026-4471", movimiento_id=hacienda, importe="12,00")
    assert _aplicaciones(conn) == []
    # Lo que si se puede: lo que queda del movimiento, que deja la factura con su saldo.
    _marcar(conn, "2026-4471", movimiento_id=diez)
    [a] = _aplicaciones(conn)
    assert (a["fuente"], a["importe_cent"]) == ("banco", 1000)
    assert _estado(conn, "2026-4471")[:2] == ("pendiente", 289279)
    # Y el movimiento ya no da para otra factura.
    with pytest.raises(PagoNoValido, match="aplicado entero"):
        _marcar(conn, "2026-112", movimiento_id=diez, importe="5,00")
    assert len(_aplicaciones(conn)) == 1
    _limpio(conn)


def test_no_se_marca_a_mano_lo_que_el_banco_ya_paga_en_parte(banco) -> None:
    """Lo marcado a mano no cuenta si hay pagos del banco (manda el banco): la orden no puede
    salir bien y dejar la factura pendiente con K2 (revision del paso 7)."""
    conn = banco.conn
    importar_camt(banco, _ana(conn), camt053(apunte(
        "-1000.00", iban=VAN_DIJK, concepto="Factuur 2026-4471")))
    [a] = _aplicaciones(conn)
    _confirmar(conn, a["id"])
    assert _estado(conn, "2026-4471")[:2] == ("pendiente", 190279)
    with pytest.raises(PagoNoValido, match="banco"):
        _marcar(conn, "2026-4471")
    assert len(_aplicaciones(conn)) == 1
    # El resto llega por el banco y se enlaza: pagada.
    importar_camt(banco, _ana(conn), camt053(apunte("-1902.79", "2026-10-13", iban=DESCONOCIDA),
                                             inicial="9000.00", secuencia=2,
                                             identificador="STMT-2", desde="2026-10-13"), "2.xml")
    _marcar(conn, "2026-4471", movimiento_id=_movimiento_de(conn, DESCONOCIDA))
    assert _estado(conn, "2026-4471")[:2] == ("pagada", 0)


def test_un_pago_enlazado_lleva_la_fecha_del_banco_y_k5_lo_ve(banco) -> None:
    """Con un movimiento, la fecha del pago es la del banco: otra dejaria un pago hecho con la
    factura Bloqueada fuera de K5 (revision del paso 7)."""
    conn = banco.conn
    assert _estado(conn, "2026-0912")[2] == "bloqueada"
    importar_camt(banco, _ana(conn), camt053(apunte("-1781.12", "2026-10-14", iban=KOSTER),
                                             hasta="2026-10-14"))
    [a] = _aplicaciones(conn)
    _orden(conn, "retirar_pago", {"aplicacion_id": a["id"], "rev": a["rev"],
                                  "motivo": "La enlazo yo"})
    with pytest.raises(PagoNoValido, match="fecha del banco"):
        _marcar(conn, "2026-0912", movimiento_id=a["movimiento_id"], fecha_pago="2026-10-01")
    _marcar(conn, "2026-0912", movimiento_id=a["movimiento_id"], fecha_pago="2026-10-14")
    assert _aplicaciones(conn)[-1]["fecha_pago"] == "2026-10-14"
    assert _de_factura(conn, "K5", "2026-0912")


def test_casar_solo_es_automatico_con_el_importe_exacto(banco) -> None:
    """Con una tolerancia de 0,01, un cargo de 2902,78 casa en referencia, importe y
    contraparte, pero no es el importe: una propuesta por lo que movio el banco, no un pago
    automatico de 2902,79 (revision del paso 7)."""
    conn = banco.conn
    carpeta = banco.documentos.raiz.parent / "reglas"
    carpeta.mkdir()
    texto = (RAIZ / "config" / "reglas.yaml").read_text(encoding="utf-8")
    (carpeta / "reglas.yaml").write_text(texto.replace('tolerancia: "0.00"', 'tolerancia: "0.01"'),
                                         encoding="utf-8")
    politica.cargar(conn, carpeta / "reglas.yaml", _ana(conn))
    importar_camt(banco, _ana(conn), camt053(apunte(
        "-2902.78", iban=VAN_DIJK, concepto="Factuur 2026-4471")))
    [a] = _aplicaciones(conn)
    assert (a["metodo"], a["estado"], a["importe_cent"], a["regla"]) == (
        "propuesta", "propuesta", 290278, "referencia+importe+contraparte")
    assert pagos.casar(
        pagos.MovimientoAbierto(1, None, -290278, VAN_DIJK, frozenset({"20264471"})),
        [pagos.FacturaAbierta(9, "entrante", "20264471", None, 290279, frozenset({VAN_DIJK}))],
        1).metodo == "propuesta"


def test_un_pago_a_mano_cita_su_prueba_y_queda_autorrevisado(banco) -> None:
    """La prueba de un pago a mano (evidencia_documento_id) se puede dar, y quien marca y
    confirma a la vez queda como autorrevisado en el evento (revision del paso 7)."""
    conn = banco.conn
    documento = conn.execute("SELECT min(id) FROM documento").fetchone()[0]
    with pytest.raises(LookupError):
        _marcar(conn, "2026-018", fecha_pago="2026-10-01", evidencia_documento_id=999999)
    _marcar(conn, "2026-018", fecha_pago="2026-10-01", evidencia_documento_id=documento)
    [a] = _aplicaciones(conn)
    assert a["evidencia_documento_id"] == documento
    datos = json.loads(conn.execute("SELECT datos_json FROM evento WHERE tipo = 'pago_marcado'"
                                    ).fetchone()[0])
    assert datos["autorrevisado"] is True
    _limpio(conn)


def test_dos_recibos_mensuales_con_el_mismo_concepto_no_son_un_pago_doble(banco) -> None:
    """El concepto entero no es una referencia de pago: dos cuotas de un leasing con el mismo
    texto a 28 dias (febrero) no son K4. Un numero de factura en el concepto si lo es
    (revision del paso 7)."""
    conn = banco.conn
    ana = _ana(conn)
    cuota = "Leasecontract LC-88 maandtermijn"
    importar_camt(banco, ana, camt053(apunte("-49.95", "2026-02-02", iban=KOSTER, concepto=cuota,
                                             e2e="LC88-202602"),
                                      secuencia=1, identificador="F", desde="2026-02-01",
                                      hasta="2026-02-28"), "feb.xml")
    importar_camt(banco, ana, camt053(apunte("-49.95", "2026-03-02", iban=KOSTER, concepto=cuota,
                                             e2e="LC88-202603"),
                                      inicial="9950.05", secuencia=2, identificador="M",
                                      desde="2026-03-01", hasta="2026-03-31"), "mar.xml")
    assert _hallazgos(conn, "K6") == []
    assert _hallazgos(conn, "K4") == []
    # Dos cargos que citan la misma factura en el concepto, si.
    importar_camt(banco, ana, camt053(
        apunte("-49.95", "2026-04-02", iban=KOSTER, concepto="Factuur 2026-0912 deel"),
        apunte("-49.95", "2026-04-03", iban=KOSTER, concepto="Factuur 2026-0912 deel"),
        inicial="9900.10", secuencia=3, identificador="A", desde="2026-04-01",
        hasta="2026-04-30"), "abr.xml")
    [k4] = _hallazgos(conn, "K4")
    assert len(json.loads(k4["valores_json"])["movimientos"]) == 2


def test_exact_dice_abierta_y_el_banco_pagada_da_k8(banco) -> None:
    """Exact sin nada pagado no dejaba ninguna aplicacion y K8 no tenia con que comparar
    (revision del paso 7)."""
    conn = banco.conn
    cabecera = (RAIZ / "tests" / "fixtures" / "importacion" / "exact-pagos_exact-v1.csv"
                ).read_text(encoding="utf-8-sig").splitlines()[0]
    ruta = banco.documentos.raiz.parent / "pagos.csv"
    ruta.write_text(f"{cabecera}\nInkoop;20001;2026-4471;2.902,79;2.902,79;;;EUR\n",
                    encoding="utf-8")
    [lote] = importar_fichero(banco, "exact", "pagos_exact", ruta, lanzado_por=_ana(conn)).lotes
    assert lote.estado == "aceptada" and _aplicaciones(conn) == []
    importar_camt(banco, _ana(conn), camt053(apunte(
        "-2902.79", iban=VAN_DIJK, concepto="Factuur 2026-4471")))
    assert _estado(conn, "2026-4471")[0] == "pagada"
    [k8] = _de_factura(conn, "K8", "2026-4471")
    assert json.loads(k8["valores_json"]) == {"banco_cent": 290279, "exact_cent": 0}


def test_la_base_no_deja_escribir_pagos_por_fuera(banco) -> None:
    conn = banco.conn
    importar_camt(banco, _ana(conn), camt053(apunte(
        "-653.40", "2026-10-13", iban=SMIT, concepto="Factuur 2026-112")))
    [a] = _aplicaciones(conn)
    f = factura_de(conn, "2026-112")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO aplicacion_pago (factura_id, importe_cent, fecha_pago, fuente, "
                     "metodo, estado, motivo, confirmada_por, confirmada_en, rev) VALUES (?, 100, "
                     "'2026-10-01', 'manual', 'manual', 'confirmada', 'x', ?, "
                     "'2026-10-14T09:30:00+00:00', 0)", (f, _ana(conn)))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE aplicacion_pago SET estado = 'confirmada' WHERE id = ?", (a["id"],))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE aplicacion_pago SET importe_cent = 1 WHERE id = ?", (a["id"],))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM aplicacion_pago")
    assert [tuple(x) for x in _aplicaciones(conn)] == [tuple(a)]


def test_ningun_usuario_de_sistema_confirma_un_pago(banco) -> None:
    from bms_agent.almacen import usuario_sistema
    from bms_agent.permisos import PermisoDenegado

    conn = banco.conn
    importar_camt(banco, _ana(conn), camt053(apunte(
        "-653.40", "2026-10-13", iban=SMIT, concepto="Factuur 2026-112")))
    [a] = _aplicaciones(conn)
    with pytest.raises(PermisoDenegado):
        servicios.ejecutar(conn, "confirmar_pago", {"aplicacion_id": a["id"], "rev": a["rev"]},
                           usuario_id=usuario_sistema(conn, "motor"))
    assert _aplicaciones(conn)[0]["estado"] == "propuesta"


# ------------------------------------------------------------ por la CLI

def test_pagos_y_flujo_de_caja_por_la_cli(tmp_path, capsys) -> None:
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["db", "init", "--db", str(db)]) == 0
    assert main(["usuario", "crear", "Ana", "--rol", "administrador", "--db", str(db)]) == 0
    capsys.readouterr()
    assert main(["usuario", "token", "Ana", "--db", str(db)]) == 0
    token = capsys.readouterr().out.splitlines()[1].strip()
    carpeta = tmp_path / "politica"
    carpeta.mkdir()
    (carpeta / "empresa.yaml").write_text(
        (RAIZ / "config" / "empresa.yaml").read_text(encoding="utf-8").replace(
            "cuentas_propias: []", "cuentas_propias:\n  - NL60INGB0009988776\n"),
        encoding="utf-8")
    assert main(["politica", "cargar", str(carpeta / "empresa.yaml"), "--db", str(db),
                 "--token", token]) == 0
    extracto = RAIZ / "tests" / "fixtures" / "banco" / "camt053-001.02.xml"
    assert main(["importar", "banco", "extracto", str(extracto), "--db", str(db),
                 "--token", token]) == 0
    assert "aceptada" in capsys.readouterr().out
    assert main(["pagos", "--sin-casar", "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    assert "Bouwtechniek Van Dijk BV" in salida and "sin casar" in salida
    assert main(["pagos", "--propuestas", "--db", str(db)]) == 0
    assert "No hay pagos propuestos" in capsys.readouterr().out
    assert main(["flujo-caja", "--hoy", "2026-10-18", "--json", "--db", str(db)]) == 0
    datos = json.loads(capsys.readouterr().out)
    assert datos["ventanas"]["semana"] == ["2026-10-18", "2026-10-18"]
    assert datos["estimado"]["importe_cent"] is None
    assert main(["flujo-caja", "--desde", "2026-10-01", "--db", str(db)]) == 1
    assert main(["flujo-caja", "--db", str(db)]) == 0
    assert "estimado" in capsys.readouterr().out.lower()
