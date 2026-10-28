"""La revision final de la V1: un test por cada hallazgo que se corrigio.

Cada test falla con el codigo de antes de la revision (800b936) y pasa con el
de ahora; el registro (docs/v1/registro.md, "Revision final") dice cual es
cual. Los escenarios de reglas puras de aqui los usa tambien
test_pureza_reglas: una regla nueva lee lo que declara.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from conftest import (
    RAIZ,
    apunte,
    camt053,
    cuentas_propias,
    factura_de,
    importar_camt,
    persona,
)
from test_hallazgos import SOLAPADA, _cargar, _registro
from test_reglas import factura, instantanea, linea
from test_reglas_paso5 import compra
from test_reglas_paso7 import aplicacion
from test_reglas_paso7 import banco as banco_puro
from test_servicios import _ids, escenario  # noqa: F401 (escenario es un fixture)

from bms_agent import btw, campos, consultas, flujo_caja, hallazgos, pagos, servicios
from bms_agent.almacen import usuario_sistema
from bms_agent.campos import Automatico
from bms_agent.importadores.registrar import importar_fichero
from bms_agent.pagos import PagoNoValido
from bms_agent.permisos import usuario_por_nombre
from bms_agent.reglas import catalogo
from bms_agent.reglas.base import Imputacion, TramoIva

MOTIVO = "Comprobado con el proveedor por telefono"
EXACT_PROVEEDORES = RAIZ / "tests" / "fixtures" / "importacion" / "exact-proveedores-v1.csv"
PAGOS_EXACT = RAIZ / "tests" / "fixtures" / "importacion" / "exact-pagos_exact-v1.csv"
DESCONOCIDA = "NL53RABO0333444555"
LIMPIA = dict(invoice_number="2026-3001", invoice_date="2026-07-01",
              service_period_start="2026-06-01", service_period_end="2026-06-07",
              due_date="2026-07-31")


def _ana(conn) -> int:
    return usuario_por_nombre(conn, "Ana")


def _rev(conn, tabla: str, fila_id: int) -> int:
    return conn.execute(f"SELECT rev FROM {tabla} WHERE id = ?", (fila_id,)).fetchone()[0]


def _orden(conn, nombre: str, datos: dict, usuario: str = "Ana") -> servicios.Diferencia:
    return servicios.ejecutar(conn, nombre, {"motivo": MOTIVO, **datos},
                              usuario_id=usuario_por_nombre(conn, usuario))


def _estado(conn, factura_id: int) -> tuple:
    return tuple(conn.execute("SELECT estado_pago, pendiente_cent, nivel FROM factura_estado "
                              "WHERE factura_id = ?", (factura_id,)).fetchone())


def _abiertos(conn, regla: str, factura_id: int | None = None) -> list:
    filas = conn.execute("SELECT * FROM hallazgo WHERE regla = ? AND estado = 'abierto' "
                         "ORDER BY id", (regla,)).fetchall()
    return [h for h in filas if factura_id is None or h["factura_id"] == factura_id]


@pytest.fixture
def vandijk(almacen, tmp_path):
    """Tres facturas de Van Dijk (la 01, una que se pisa con ella y una de julio), las cuentas
    propias de BM Support BV y Ana, que lo puede todo."""
    _cargar(almacen, tmp_path / "out", _registro("a"), _registro("b", **SOLAPADA),
            _registro("c", **LIMPIA))
    ana = persona(almacen.conn, "Ana", "administrador")
    cuentas_propias(almacen, ana)
    hallazgos.recalcular(almacen.conn)
    return almacen


@pytest.fixture
def banco(tipado):
    """Las siete facturas v1 con el maestro de proveedores de Exact y las cuentas propias."""
    ana = persona(tipado.conn, "Ana", "administrador")
    cuentas_propias(tipado, ana)
    importar_fichero(tipado, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana)
    return tipado


def _propuesta(almacen, numero: str, importe: str, fecha: str = "2026-10-12") -> int:
    """Un cargo con la referencia y el importe de la factura pero a una cuenta que nadie
    conoce: dos de tres, una propuesta."""
    conn = almacen.conn
    importar_camt(almacen, _ana(conn), camt053(apunte(
        f"-{importe}", fecha, iban=DESCONOCIDA, concepto=f"Factuur {numero}")),
        nombre=f"extracto-{numero}.xml")
    [aplicacion] = conn.execute("SELECT id FROM aplicacion_pago WHERE factura_id = ? AND "
                                "estado = 'propuesta'", (factura_de(conn, numero),)).fetchall()
    return aplicacion[0]


# ============================================================ 1. anular lo pagado

def test_no_se_anula_una_factura_pagada_ni_con_un_pago_propuesto(vandijk) -> None:
    """Anulada, una factura no cuenta, y lo pagado de ella tampoco: el dinero salia de lo
    pagado del proveedor sin que nada lo dijera. Con un pago propuesto o confirmado, no se
    anula: se retira el pago o se apunta un abono."""
    conn = vandijk.conn
    a = factura_de(conn, "2026-4471")
    aplicacion = _propuesta(vandijk, "2026-4471", "2902.79")
    with pytest.raises(servicios.DatosNoValidos, match="lleva el pago"):
        _orden(conn, "anular_factura", {"factura_id": a, "rev": _rev(conn, "factura", a)})
    _orden(conn, "confirmar_pago", {"aplicacion_id": aplicacion,
                                    "rev": _rev(conn, "aplicacion_pago", aplicacion)})
    assert _estado(conn, a)[:2] == ("pagada", 0)
    proveedor = conn.execute("SELECT proveedor_id FROM factura WHERE id = ?", (a,)).fetchone()[0]
    pagado = consultas.proveedor(conn, proveedor)["siempre_pagado_cent"] if proveedor else None
    with pytest.raises(servicios.DatosNoValidos, match="retirar_pago"):
        _orden(conn, "anular_factura", {"factura_id": a, "rev": _rev(conn, "factura", a)})
    assert conn.execute("SELECT anulada FROM factura WHERE id = ?", (a,)).fetchone()[0] == 0
    if proveedor:
        assert consultas.proveedor(conn, proveedor)["siempre_pagado_cent"] == pagado
    # Retirado el pago (no era de ella), se anula.
    _orden(conn, "retirar_pago", {"aplicacion_id": aplicacion,
                                  "rev": _rev(conn, "aplicacion_pago", aplicacion)})
    _orden(conn, "anular_factura", {"factura_id": a, "rev": _rev(conn, "factura", a)})
    assert _estado(conn, a)[0] == "anulada"


def test_no_se_confirma_un_pago_de_una_factura_que_ya_no_cuenta(vandijk) -> None:
    """La 2026-3001 tiene un pago propuesto y otra la sustituye: el pago no se confirma ahi
    (no contaria en nada), se paga la nueva."""
    conn = vandijk.conn
    c, b = factura_de(conn, "2026-3001"), factura_de(conn, "2026-4480")
    total_c = conn.execute("SELECT total_cent FROM factura WHERE id = ?", (c,)).fetchone()[0]
    aplicacion = _propuesta(vandijk, "2026-3001", f"{total_c / 100:.2f}")
    _orden(conn, "enlazar_facturas", {"origen_id": b, "destino_id": c, "tipo": "sustituye"})
    with pytest.raises(PagoNoValido, match="sustituida"):
        _orden(conn, "confirmar_pago", {"aplicacion_id": aplicacion,
                                        "rev": _rev(conn, "aplicacion_pago", aplicacion)})
    assert conn.execute("SELECT estado FROM aplicacion_pago WHERE id = ?",
                        (aplicacion,)).fetchone()[0] == "propuesta"


def test_k9_el_pago_de_exact_de_una_anulada_no_desaparece(banco, tmp_path) -> None:
    """Exact trae el pago de una factura que aqui esta anulada: se aplica (es lo que dice
    Exact), y K9 lo retiene con su excepcion hasta que alguien diga donde esta el dinero."""
    conn = banco.conn
    koster = factura_de(conn, "2026-0912")
    _orden(conn, "anular_factura", {"factura_id": koster, "rev": _rev(conn, "factura", koster)})
    cabecera = PAGOS_EXACT.read_text(encoding="utf-8-sig").splitlines()[0]
    ruta = tmp_path / "pagos.csv"
    ruta.write_text(f"{cabecera}\nInkoop;20003;2026-0912;1.781,12;0,00;;10-10-2026;EUR\n",
                    encoding="utf-8")
    importar_fichero(banco, "exact", "pagos_exact", ruta, lanzado_por=_ana(conn))
    hallazgos.recalcular(conn)
    [k9] = _abiertos(conn, "K9", koster)
    assert k9["severidad"] == "retencion"
    assert json.loads(k9["valores_json"])["pagado_cent"] == 178112
    assert "no cuenta en ningún total" in k9["detalle"]
    assert _estado(conn, koster)[2] == "atencion"
    assert conn.execute("SELECT count(*) FROM excepcion WHERE tabla = 'factura' AND "
                        "fila_id = ? AND estado <> 'resuelta'", (koster,)).fetchone()[0] == 1
    assert catalogo.regla("K9").pegajosa and not catalogo.regla("K9").anulable


# ============================================================ 2. saldos del otro signo

def test_una_factura_pagada_y_despues_abonada_no_esta_vencida(banco, reloj) -> None:
    """La 2026-4471 se paga entera por el banco y despues se le enlaza el abono de Van Dijk:
    lo que queda es negativo (sobra). Ni vencida ni K1 ni puntos de vencida: pagada, y K2
    dice lo que sobra. Lo vencido de las compras no se resta."""
    conn = banco.conn
    a, abono = factura_de(conn, "2026-4471"), factura_de(conn, "CN-2026-031")
    importar_camt(banco, _ana(conn), camt053(apunte(
        "-2902.79", "2026-10-12", iban="NL02ABNA0123456789", nombre="Bouwtechniek Van Dijk BV",
        concepto="Factuur 2026-4471")))
    assert _estado(conn, a)[:2] == ("pagada", 0)
    _orden(conn, "enlazar_facturas", {"origen_id": abono, "destino_id": a, "tipo": "acredita"})
    # Dos meses despues de su vencimiento, todavia no vencida.
    reloj.avanzar(days=67)
    hallazgos.recalcular(conn)
    estado, pendiente, _nivel = _estado(conn, a)
    assert estado == "pagada" and pendiente < 0
    assert _abiertos(conn, "K1", a) == []
    assert _abiertos(conn, "K2", a)
    motivos = conn.execute("SELECT motivos_json FROM factura_estado WHERE factura_id = ?",
                           (a,)).fetchone()[0]
    assert "vencida" not in motivos
    despues = consultas.panel(conn)["atencion"]["compras_vencidas"]
    assert a not in [f["id"] for f in despues["lista"]]
    assert despues["pendiente_cent"] >= 0


def test_un_abono_sin_enlazar_no_vence_ni_es_un_cobro_esperado(banco, reloj) -> None:
    """El abono de Van Dijk sin relacion: R4 lo dice, pero no esta vencido (no tiene deuda
    que pagar), no es urgente por dias y no entra en la caja como un cobro."""
    conn = banco.conn
    abono = factura_de(conn, "CN-2026-031")
    reloj.avanzar(days=67)
    hallazgos.recalcular(conn)
    estado, pendiente, nivel = _estado(conn, abono)
    assert (estado, pendiente) == ("pendiente", -12251)
    assert nivel != "urgente"
    assert _abiertos(conn, "K1", abono) == []
    assert _abiertos(conn, "R4", abono)
    motivos = conn.execute("SELECT motivos_json FROM factura_estado WHERE factura_id = ?",
                           (abono,)).fetchone()[0]
    assert "vencida" not in motivos
    partidas, _ = flujo_caja.datos(conn)
    assert abono not in {p.factura_id for p in partidas}
    assert abono not in [f["id"] for f in
                         consultas.panel(conn)["atencion"]["compras_vencidas"]["lista"]]


def test_vence_y_de_mas_son_puras() -> None:
    from bms_agent.reglas.pagos import de_mas, vence

    assert vence(10000, 500) and not vence(10000, -500) and not vence(-500, -500)
    assert vence(None, None) and not vence(0, 0)
    assert de_mas(10000, -500) and not de_mas(10000, -500, tolerancia=500)
    assert de_mas(-500, 100) and not de_mas(-500, -100) and not de_mas(10000, 500)
    assert not de_mas(None, -5)


# ============================================================ 3. prioridad de proveedor y Objeto

def _prioridad(conn, entidad: str, entidad_id: int) -> str | None:
    fila = conn.execute("SELECT nivel FROM prioridad WHERE entidad = ? AND entidad_id = ?",
                        (entidad, entidad_id)).fetchone()
    return fila[0] if fila else None


def test_pagar_mal_una_factura_bloqueada_no_baja_a_su_proveedor_ni_a_su_objeto(banco) -> None:
    """La 2026-112 de Smit se paga a una cuenta que no es pagable para Smit (F7): la factura
    sigue Bloqueada, y su proveedor y su Objeto tambien (antes bajaban a nada al pagarla)."""
    conn = banco.conn
    smit = factura_de(conn, "2026-112")
    proveedor = conn.execute("SELECT proveedor_id FROM factura WHERE id = ?",
                             (smit,)).fetchone()[0]
    objetos = [f[0] for f in conn.execute(
        "SELECT DISTINCT objeto_id FROM factura_imputacion WHERE factura_id = ? AND objeto_id "
        "IS NOT NULL AND retirada_en IS NULL", (smit,))]
    importar_camt(banco, _ana(conn), camt053(apunte(
        "-653.40", "2026-10-13", iban="NL03RABO0312456789", nombre="Loodgietersbedrijf Smit",
        concepto="Factuur 2026-112")))
    [aplicacion] = conn.execute("SELECT id FROM aplicacion_pago WHERE factura_id = ?",
                                (smit,)).fetchall()
    _orden(conn, "confirmar_pago", {"aplicacion_id": aplicacion[0],
                                    "rev": _rev(conn, "aplicacion_pago", aplicacion[0])})
    assert _estado(conn, smit)[0] == "pagada" and _estado(conn, smit)[2] == "bloqueada"
    assert _abiertos(conn, "F7")
    assert _prioridad(conn, "proveedor", proveedor) == "bloqueada"
    for objeto in objetos:
        assert _prioridad(conn, "objeto", objeto) == "bloqueada"


def test_un_hallazgo_del_proveedor_sin_facturas_le_da_su_prioridad(banco, tmp_path) -> None:
    """Un maestro posterior trae un proveedor nuevo con su cuenta y sin facturas: F5 bloquea
    sobre el proveedor, y el proveedor queda Bloqueado (antes, sin prioridad)."""
    conn = banco.conn
    texto = EXACT_PROVEEDORES.read_text(encoding="utf-8-sig").rstrip("\n") + (
        "\n20008;Nieuwe Leverancier BV;Bedrijf;12345678;NL008888888B01;VH21;30;Kade 1;"
        "3011 AA;Rotterdam;;010-7654321;Actief;NL91ABNA0417164300;Nieuwe Leverancier BV\n")
    ruta = tmp_path / "proveedores-2.csv"
    ruta.write_text(texto, encoding="utf-8")
    importar_fichero(banco, "exact", "proveedores", ruta, lanzado_por=_ana(conn))
    hallazgos.recalcular(conn)
    onbekend = conn.execute("SELECT id FROM proveedor WHERE exact_id = '20008'").fetchone()[0]
    [f5] = [h for h in _abiertos(conn, "F5") if h["tabla"] == "proveedor"]
    assert f5["fila_id"] == onbekend and f5["severidad"] == "bloqueo"
    assert conn.execute("SELECT count(*) FROM factura WHERE proveedor_id = ?",
                        (onbekend,)).fetchone()[0] == 0
    assert _prioridad(conn, "proveedor", onbekend) == "bloqueada"


# ============================================================ 8 y 12. D6 e I1 en el almacen

def test_d6_un_desglose_que_no_es_la_cabecera_no_se_declara_sin_objeciones(vandijk) -> None:
    """La 2026-4471 dice base 2.399,00 y cuota 503,79; su desglose trae ademas una fila del
    9 %. El BTW declara el desglose (3.399,00 y 593,79): D6 lo bloquea."""
    conn = vandijk.conn
    a = factura_de(conn, "2026-4471")
    extractor = Automatico("extraccion", usuario_sistema(conn, "extractor"))
    for tipo, base, cuota in (("21", "2399.00", "503.79"), ("9", "1000.00", "90.00")):
        campos.crear(conn, "factura_iva", {"factura_id": a, "tipo_iva_pb": Decimal(tipo),
                                           "base_cent": Decimal(base),
                                           "cuota_cent": Decimal(cuota)}, extractor)
    hallazgos.recalcular(conn)
    assert sorted((l.tipo_iva_pb, l.base_cent, l.cuota_cent) for l in btw.lineas(conn, 2026, 3)
                  if l.factura_id == a) == [(900, 100000, 9000), (2100, 239900, 50379)]
    [d6] = _abiertos(conn, "D6", a)
    assert d6["severidad"] == "bloqueo" and "3.399,00" in d6["detalle"]
    assert _estado(conn, a)[2] == "bloqueada"


def test_i1_corregir_una_linea_dividida_deja_sus_partes_a_la_vista(escenario) -> None:
    """La primera linea de la 2026-4471 se divide en 1.000,00 y 593,75 y despues se corrige a
    2.000,00: las partes siguen sumando 1.593,75, e I1 lo dice."""
    conn = escenario.conn
    ids = _ids(conn)
    _orden(conn, "dividir_linea", {
        "linea_id": ids["linea"], "rev": _rev(conn, "factura_linea", ids["linea"]),
        "partes": [{"objeto_id": ids["rijnhaven"], "importe": "1000"},
                   {"objeto_id": ids["schiedam"], "importe": "593,75"}]})
    assert _abiertos(conn, "I1", ids["a"]) == []
    _orden(conn, "fijar_campo", {"tabla": "factura_linea", "fila_id": ids["linea"],
                                 "campo": "importe_cent", "valor": "2000",
                                 "rev": _rev(conn, "factura_linea", ids["linea"])})
    [i1] = _abiertos(conn, "I1", ids["a"])
    assert i1["severidad"] == "retencion" and "1.593,75" in i1["detalle"]


# ============================================================ reglas puras: D6, I1, E2 y K9

def _evaluar(regla_id: str, inst) -> list:
    return [r for r in catalogo.regla(regla_id).evaluar(inst) if r.resultado == "fallo"]


def _imputacion(id_: int, linea_id: int, importe: int) -> Imputacion:
    return Imputacion(id_, linea_id, 1, None, None, importe, None, None, None, None, None)


DESGLOSE_VIEJO = factura(901, base_cent=34000, iva_cent=7140, total_cent=41140, desglose=(
    TramoIva(9011, 2100, 34000, 7140), TramoIva(9012, 900, 10000, 900)))
DESGLOSE_BUENO = factura(902, desglose=(TramoIva(9021, 2100, 24000, 5040),
                                        TramoIva(9022, 2100, 10000, 2100)))
DESGLOSE_SIN = factura(903, desglose=(TramoIva(9031, 2100, None, None),))
PARTIDA = factura(904, lineas=(linea(9041, importe_cent=200000),), imputaciones=(
    _imputacion(1, 9041, 100000), _imputacion(2, 9041, 59375)))
ENTERA = factura(905, lineas=(linea(9051),), imputaciones=(_imputacion(3, 9051, 34000),))
SIN_IMPORTE = factura(906, lineas=(linea(9061, importe_cent=None),), imputaciones=(
    _imputacion(4, 9061, None),))
DEL_21 = factura(907, parte="btw:NL009999999B01", fecha_factura=date(2026, 8, 15))
DEL_9 = factura(908, parte="btw:NL009999999B01", fecha_factura=date(2026, 9, 15),
                tipo_iva_pb=900, iva_cent=3060, total_cent=37060)
OTRA_DEL_21 = factura(909, parte="btw:NL009999999B01", fecha_factura=date(2026, 10, 1),
                      desglose=(TramoIva(9091, 2100, 34000, 7140, "estandar"),))


def test_d6_el_desglose_que_no_suma_la_cabecera_bloquea() -> None:
    """La cabecera dice 340,00 y 71,40; el desglose, 440,00 y 80,40 (el que declara el BTW):
    D3 da cada fila por buena, D6 no."""
    inst = instantanea(DESGLOSE_VIEJO, DESGLOSE_BUENO, DESGLOSE_SIN, factura(910))
    assert _evaluar("D3", inst) == []
    [d6] = _evaluar("D6", inst)
    assert d6.fila_id == 901 and "440,00" in d6.detalle and "80,40" in d6.detalle
    assert {o.tabla for o in d6.objetivos} == {"factura", "factura_iva"}
    por_id = {r.fila_id: r.resultado for r in catalogo.regla("D6").evaluar(inst)}
    assert por_id == {901: "fallo", 902: "ok", 903: "sin_datos", 910: "no_aplica"}
    assert catalogo.nunca_anulable("D6", "entrante") and not catalogo.regla("D6").anulable


def test_i1_unas_imputaciones_que_no_cubren_su_linea_retienen() -> None:
    """La linea se corrigio a 2.000,00 despues de dividirla en 1.000,00 y 593,75."""
    inst = instantanea(PARTIDA, ENTERA, SIN_IMPORTE, factura(911))
    [i1] = _evaluar("I1", inst)
    assert i1.fila_id == 904 and "1.593,75" in i1.detalle and "2.000,00" in i1.detalle
    por_id = {r.fila_id: r.resultado for r in catalogo.regla("I1").evaluar(inst)}
    assert por_id == {904: "fallo", 905: "ok", 906: "sin_datos", 911: "no_aplica"}
    assert catalogo.regla("I1").severidad == "retencion" and not catalogo.regla("I1").anulable


def test_e2_un_tipo_que_el_proveedor_nunca_habia_traido() -> None:
    """Del 21 % al 9 % con el mismo regimen: E2 lo dice (E1 y E7 no lo ven). Volver al 21 %
    despues no es nuevo: ya lo traia."""
    inst = instantanea(DEL_21, DEL_9, OTRA_DEL_21)
    [e2] = _evaluar("E2", inst)
    assert e2.fila_id == 908 and "9 %" in e2.detalle and "21 %" in e2.detalle
    assert _evaluar("E1", inst) == [] and _evaluar("E7", inst) == []


def test_k9_pura() -> None:
    anulada = compra(921, anulada=True)
    fusionada = compra(922, fusionada_en_id=1)
    cero = compra(923, anulada=True)
    inst = banco_puro(anulada, fusionada, cero, compra(924), aplicaciones=(
        aplicacion(1, 921, 41140), aplicacion(2, 922, 1000, fuente="exact"),
        aplicacion(3, 923, 500, fuente="manual", metodo="manual"),
        aplicacion(4, 923, -500, fuente="manual", metodo="manual"),
        aplicacion(5, 924, 41140), aplicacion(6, 921, 10, estado="propuesta")))
    assert sorted(r.fila_id for r in _evaluar("K9", inst)) == [921, 922]


def escenarios() -> list:
    """Instantaneas que pasan por cada rama de las reglas de la revision final
    (test_pureza_reglas)."""
    return [
        instantanea(DESGLOSE_VIEJO, DESGLOSE_BUENO, DESGLOSE_SIN, PARTIDA, ENTERA, SIN_IMPORTE,
                    DEL_21, DEL_9, OTRA_DEL_21, factura(910)),
        banco_puro(compra(921, anulada=True), compra(922, fusionada_en_id=1), compra(924),
                   aplicaciones=(aplicacion(1, 921, 41140),
                                 aplicacion(2, 922, 1000, fuente="exact"),
                                 aplicacion(5, 924, 41140))),
    ]


# ============================================================ 4. las anclas, sin excusas

def _reescribir_desde(ruta, desde_id: int, *, cambiar=None, borrar_desde: int | None = None):
    """Lo que hace quien puede escribir el fichero de la base: quita los disparadores, toca la
    cadena, recalcula los hashes y los vuelve a poner."""
    import sqlite3

    from bms_agent.auditoria import HASH_INICIAL, calcular_hash

    c = sqlite3.connect(ruta)
    c.row_factory = sqlite3.Row
    disparadores = [(r["name"], r["sql"]) for r in c.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND tbl_name IN "
        "('evento', 'cambio_campo', 'usuario', 'usuario_rol')")]
    for nombre, _sql in disparadores:
        c.execute(f"DROP TRIGGER {nombre}")
    if cambiar is not None:
        cambiar(c)
    if borrar_desde is not None:
        c.execute("DELETE FROM cambio_campo WHERE evento_id >= ?", (borrar_desde,))
        c.execute("DELETE FROM evento WHERE id >= ?", (borrar_desde,))
    cambios: dict = {}
    for f in c.execute("SELECT * FROM cambio_campo ORDER BY evento_id, id"):
        cambios.setdefault(f["evento_id"], []).append(dict(f))
    anterior = HASH_INICIAL
    for f in list(c.execute("SELECT * FROM evento ORDER BY id")):
        fila = dict(f)
        fila["hash_anterior"] = anterior
        nuevo = calcular_hash(fila, cambios.get(fila["id"], []))
        if fila["id"] >= desde_id:
            c.execute("UPDATE evento SET hash_anterior = ?, hash = ? WHERE id = ?",
                      (anterior, nuevo, fila["id"]))
        anterior = c.execute("SELECT hash FROM evento WHERE id = ?", (fila["id"],)).fetchone()[0]
    for _nombre, sql in disparadores:
        c.execute(sql)
    c.commit()
    c.close()


def _verificar(ruta, capsys) -> tuple[int, str]:
    from bms_agent.cli import main

    codigo = main(["db", "verificar", "--db", str(ruta)])
    salida = capsys.readouterr()
    return codigo, salida.out + salida.err


def test_reescribir_la_cadena_desde_el_primer_evento_no_pasa_db_verificar(tmp_path,
                                                                           capsys) -> None:
    """La revision: se reescribe el evento 1 (la identidad de la base cambia), se recalculan
    los hashes y una orden normal ancla la cabeza falsa. Antes, las anclas de verdad pasaban
    por "de otra base" y `db verificar` decia "Todo cuadra"."""
    from bms_agent import permisos
    from bms_agent.almacen import preparar
    from bms_agent.auditoria import anclar, leer_anclas

    db = tmp_path / "datos" / "bms.sqlite3"
    with preparar(db) as almacen:
        permisos.crear_usuario(almacen.conn, "Ana")
        permisos.crear_usuario(almacen.conn, "Bea")
        anclar(almacen.conn, almacen.ruta_anclas)
    assert _verificar(db, capsys)[0] == 0

    def falsear(c) -> None:
        datos = json.loads(c.execute("SELECT datos_json FROM evento WHERE id = 1").fetchone()[0])
        datos["almacen"] = "0" * 32
        from bms_agent.almacen.unidades import json_canonico
        c.execute("UPDATE evento SET datos_json = ? WHERE id = 1", (json_canonico(datos),))
        c.execute("UPDATE evento SET motivo = 'falsificado' WHERE id = "
                  "(SELECT max(id) FROM evento)")

    _reescribir_desde(db, 1, cambiar=falsear)
    antes = len(leer_anclas(db.parent / "anclas.log")[0])
    with preparar(db) as almacen:
        permisos.crear_usuario(almacen.conn, "Carla")
        from bms_agent.cli import _anclar
        _anclar(almacen)
    assert "no se ancla" in capsys.readouterr().err
    assert len(leer_anclas(db.parent / "anclas.log")[0]) == antes
    codigo, salida = _verificar(db, capsys)
    assert codigo == 1 and "Todo cuadra" not in salida
    assert "no consta" in salida


def test_una_base_de_antes_con_anclas_suyas_no_se_da_por_reescrita(tmp_path, capsys) -> None:
    """Una base creada antes de `nueva_base` no consta en el fichero; si lo comparte con
    otra, sus anclas propias bastan (es lo mismo que mira `anclar`): no es una cadena
    reescrita, que no consigue ninguna."""
    from bms_agent import permisos
    from bms_agent.almacen import preparar
    from bms_agent.auditoria import LINEA_BASE, anclar

    db = tmp_path / "datos" / "bms.sqlite3"
    otra = tmp_path / "datos" / "otra.sqlite3"
    with preparar(db) as almacen:
        permisos.crear_usuario(almacen.conn, "Ana")
        anclar(almacen.conn, almacen.ruta_anclas)
    log = db.parent / "anclas.log"
    # Como si fuera de antes: sin su linea nueva_base.
    log.write_text("".join(l for l in log.read_text(encoding="utf-8").splitlines(True)
                           if f"\t{LINEA_BASE}\t" not in l), encoding="utf-8")
    with preparar(otra) as almacen:
        permisos.crear_usuario(almacen.conn, "Bea")
        anclar(almacen.conn, almacen.ruta_anclas)
    assert _verificar(otra, capsys)[0] == 0
    codigo, salida = _verificar(db, capsys)
    assert codigo == 0, salida
    with preparar(db) as almacen:
        permisos.crear_usuario(almacen.conn, "Carla")
        assert anclar(almacen.conn, almacen.ruta_anclas) is not None

def test_un_evento_de_restauracion_falso_no_perdona_un_corte(tmp_path, capsys) -> None:
    """La revision: se corta el final de la cadena y se escribe un evento `restauracion` que
    nombra las anclas cortadas. Solo perdona lo que dice el fichero de anclas (lo escribe
    copia.restaurar, con lo sustituido guardado y su hash): `db verificar` lo da por cortado."""
    from bms_agent import permisos
    from bms_agent.almacen import preparar, transaccion, usuario_sistema
    from bms_agent.auditoria import TIPO_RESTAURACION, anclar, registrar

    db = tmp_path / "datos" / "bms.sqlite3"
    with preparar(db) as almacen:
        permisos.crear_usuario(almacen.conn, "Ana")
        anclar(almacen.conn, almacen.ruta_anclas)
        corte = almacen.conn.execute("SELECT max(id) FROM evento").fetchone()[0] + 1
        permisos.crear_usuario(almacen.conn, "Bea")
        cortada = anclar(almacen.conn, almacen.ruta_anclas)

    def sin_bea(c) -> None:
        c.execute("DELETE FROM usuario_rol WHERE usuario_id IN (SELECT id FROM usuario WHERE "
                  "nombre = 'Bea')")
        c.execute("DELETE FROM usuario WHERE nombre = 'Bea'")

    _reescribir_desde(db, corte, cambiar=sin_bea, borrar_desde=corte)
    with preparar(db) as almacen:
        with transaccion(almacen.conn):
            registrar(almacen.conn, tipo=TIPO_RESTAURACION,
                      actor=usuario_sistema(almacen.conn, "sistema"), motivo="restaurada",
                      datos={"anclas_descartadas": [[cortada.id, cortada.hash]]})
    codigo, salida = _verificar(db, capsys)
    assert codigo == 1 and "Todo cuadra" not in salida
    assert "se ha cortado" in salida or "se ha reescrito" in salida


def test_una_restauracion_de_verdad_sigue_cuadrando_y_sin_lo_sustituido_no(tmp_path,
                                                                           capsys) -> None:
    """Restaurar apunta el corte en el fichero de anclas con el hash de lo que guardo en
    antes-de-restaurar/: `db verificar` cuadra. Si lo sustituido desaparece, ya no."""
    import shutil

    from bms_agent import copia, permisos
    from bms_agent.almacen import preparar
    from bms_agent.auditoria import LINEA_CORTE, anclar

    db = tmp_path / "datos" / "bms.sqlite3"
    with preparar(db) as almacen:
        permisos.crear_usuario(almacen.conn, "Ana")
        anclar(almacen.conn, almacen.ruta_anclas)
    disco = tmp_path / "disco"
    disco.mkdir()
    hecha = copia.copiar(db, disco)
    with preparar(db) as almacen:
        permisos.crear_usuario(almacen.conn, "Bea")
        anclar(almacen.conn, almacen.ruta_anclas)
    copia.restaurar(hecha.carpeta, db)
    assert f"\t{LINEA_CORTE}\t" in (db.parent / "anclas.log").read_text(encoding="utf-8")
    codigo, salida = _verificar(db, capsys)
    assert codigo == 0, salida
    shutil.rmtree(db.parent / copia.ANTES_DE_RESTAURAR)
    codigo, salida = _verificar(db, capsys)
    assert codigo == 1 and "ya no esta ahi" in salida


# ============================================================ 5 y 7. /api/datos y los IBAN sueltos

@pytest.fixture
def servidor_datos(tmp_path, out_v1):
    """El servidor con las siete fixtures v1 y un sitio propio declarado (localhost:3000)."""
    import threading

    from bms_agent import permisos
    from bms_agent.almacen import preparar
    from bms_agent.cli import main
    from bms_agent.serve import crear_servidor

    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(tmp_path / "no"),
                 "--db", str(db)]) == 0
    with preparar(db) as almacen:
        dora = persona(almacen.conn, "Dora", "consulta")
        token = permisos.emitir_token(almacen.conn, dora)
    srv = crear_servidor(tmp_path / "facturas", tmp_path / "vacio", 0, ruta_db=db,
                         origenes_extra=["http://localhost:3000"])
    hilo = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05},
                            daemon=True)
    hilo.start()
    try:
        yield srv.server_address[1], token
    finally:
        srv.shutdown()
        srv.server_close()


def _get(puerto: int, ruta: str, cabeceras: dict) -> tuple[int, dict, bytes]:
    import http.client

    conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=5)
    conexion.request("GET", ruta, headers={"Host": f"127.0.0.1:{puerto}", **cabeceras})
    respuesta = conexion.getresponse()
    datos = respuesta.read()
    conexion.close()
    return respuesta.status, {k.lower(): v for k, v in respuesta.getheaders()}, datos


def test_api_datos_pide_token_y_no_da_un_iban_entero_a_otro_origen(servidor_datos) -> None:
    """La revision: GET /api/datos sin token daba cada factura con su IBAN entero, tambien con
    CORS a un origen declarado. Ahora pide un token personal con ver_facturas, y a un origen
    declarado le llegan enmascarados. A la consola (sin Origin), enteros."""
    from bms_agent.reglas.bancaria import validar_iban
    from bms_agent.serve import CABECERA_TOKEN

    puerto, token = servidor_datos
    otro = {"Origin": "http://localhost:3000"}
    assert _get(puerto, "/api/datos", {})[0] == 401
    estado, cabeceras, _ = _get(puerto, "/api/datos", otro)
    assert estado == 401
    estado, cabeceras, cuerpo = _get(puerto, "/api/datos", {**otro, CABECERA_TOKEN: token})
    assert estado == 200 and cabeceras["access-control-allow-origin"] == "http://localhost:3000"
    ibanes = [f["iban"] for f in json.loads(cuerpo)["filas"] if f.get("iban")]
    assert ibanes and all(".." in i for i in ibanes)
    from bms_agent.consultas import ibanes_en
    assert ibanes_en(cuerpo.decode("utf-8")) == []
    estado, _, cuerpo = _get(puerto, "/api/datos", {CABECERA_TOKEN: token})
    enteros = [f["iban"] for f in json.loads(cuerpo)["filas"] if f.get("iban")]
    assert estado == 200 and any(validar_iban(i) for i in enteros)


@pytest.mark.parametrize("texto", [
    "nl75ingb0002445689", "NL75-INGB-0002-4456-89", "NL75.INGB.0002.4456.89",
    "NL 75 INGB 0002 4456 89", "NL75INGB 0002445689", "NL75 INGB 0002 445689",
    "Pagad a nl75 ingb 0002 4456 89, por favor", "NL75INGB0002445689 en 2026-10",
])
def test_sin_ibanes_ve_un_iban_escrito_de_cualquier_manera(texto) -> None:
    from bms_agent.consultas import ibanes_en, sin_ibanes

    enmascarado = sin_ibanes(texto)
    assert "NL..5689" in enmascarado
    assert "4456" not in enmascarado.replace("NL..5689", "")
    assert ibanes_en(texto) and not ibanes_en(enmascarado)


def test_sin_ibanes_no_toca_lo_que_no_es_un_iban() -> None:
    from bms_agent.consultas import sin_ibanes

    for texto in ("DBN-2026-08 y JV-2026-003, PO 4500012345", "NL001234567B01",
                  "KvK 87654321, tel. 010-1234567", "NL..5689"):
        assert sin_ibanes(texto) == texto


# ============================================================ 6. caracteres de control

def test_un_pdf_con_secuencias_de_escape_no_manda_en_la_terminal(tmp_path, capsys) -> None:
    """La revision: una extraccion cuyo proveedor y numero llevan ESC/OSC/BEL se imprimia tal
    cual en `bms-agent facturas` (borrar lineas, titulo de la ventana, portapapeles). Ahora
    se guarda sin ellos en las tablas tipadas, y la CLI no los deja salir aunque los haya."""
    from bms_agent.cli import main

    registro = _registro("esc", supplier_name="Van Dijk BV\x1b]0;PWNED\x07\x1b[2J\x1b[31m"
                                               "BETAAL NU NL00FAKE\x1b[0m‮",
                         invoice_number="2026-4471\x1b[1A\x1b[2K")
    out = tmp_path / "out"
    out.mkdir()
    (out / "esc.json").write_text(json.dumps(registro), encoding="utf-8")
    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["importar-out", "--out", str(out), "--pdfs", str(tmp_path / "no"),
                 "--db", str(db)]) == 0
    capsys.readouterr()
    assert main(["facturas", "--db", str(db)]) == 0
    salida = capsys.readouterr()
    for crudo in ("\x1b", "\x07", "‮"):
        assert crudo not in salida.out + salida.err
    assert "Van Dijk BV" in salida.out
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect(db)) as conn:
        nombre, numero = conn.execute("SELECT emisor_nombre_doc, numero FROM factura").fetchone()
        assert "\x1b" not in nombre + numero and "�" in numero
        # La evidencia (lo que dijo el modelo) se queda como llego.
        assert any("\\u001b" in p or "\x1b" in p
                   for (p,) in conn.execute("SELECT contenido_json FROM extraccion"))


def test_la_salida_segura_y_el_registro_del_servidor() -> None:
    import io
    from types import SimpleNamespace

    from bms_agent.serve import Manejador
    from bms_agent.terminal import SalidaSegura, sin_control

    assert sin_control("a\tb\nc\x1b[2K\r\x9b⁦d") == "a\tb\nc�[2K���d"
    flujo = io.StringIO()
    SalidaSegura(flujo).write("ok\x1b]52;c;TkwwMEZBS0U=\x07\n")
    assert "\x1b" not in flujo.getvalue() and flujo.getvalue().endswith("\n")
    impreso = io.StringIO()
    falso = SimpleNamespace(address_string=lambda: "127.0.0.1",
                            _control_char_table=Manejador._control_char_table)
    import contextlib
    with contextlib.redirect_stdout(impreso):
        Manejador.log_message(falso, '"%s" %s', "GET /\x1b[2J HTTP/1.1", "404")
    assert "\x1b" not in impreso.getvalue() and "\\x1b" in impreso.getvalue()


# ============================================================ 10. el original

@pytest.fixture
def con_originales(almacen, out_v1, pdfs_ejemplo):
    """Las siete v1 tipadas; las tres primeras con su PDF en el almacen de documentos."""
    from bms_agent.importadores.extracciones import importar_out
    from bms_agent.ingesta import tipar_pendientes

    importar_out(almacen, out_v1, pdfs_ejemplo)
    tipar_pendientes(almacen.conn)
    return almacen


def test_el_original_se_descarga_desde_la_consola_y_queda_en_la_auditoria(tmp_path, out_v1,
                                                                           pdfs_ejemplo) -> None:
    """La revision: documentos.abrir solo lo llamaba la reextraccion; nadie podia abrir el PDF
    desde el producto. Ahora GET /api/v2/facturas/N/original da sus bytes (adjunto, sin CORS,
    solo desde la consola) y cada descarga queda como documento_abierto."""
    import hashlib
    import threading

    from bms_agent import permisos
    from bms_agent.almacen import preparar
    from bms_agent.cli import main
    from bms_agent.serve import CABECERA_TOKEN, crear_servidor

    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(pdfs_ejemplo),
                 "--db", str(db)]) == 0
    with preparar(db) as almacen:
        dora = persona(almacen.conn, "Dora", "consulta")
        token = permisos.emitir_token(almacen.conn, dora)
        factura, sha = almacen.conn.execute(
            "SELECT f.id, d.sha256 FROM factura f JOIN documento d ON d.id = f.documento_id "
            "WHERE d.ruta_cas IS NOT NULL ORDER BY f.id LIMIT 1").fetchone()
    srv = crear_servidor(tmp_path / "facturas", tmp_path / "vacio", 0, ruta_db=db,
                         origenes_extra=["http://localhost:3000"])
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05},
                     daemon=True).start()
    try:
        puerto = srv.server_address[1]
        ruta = f"/api/v2/facturas/{factura}/original"
        assert _get(puerto, ruta, {})[0] == 401
        estado, cabeceras, cuerpo = _get(puerto, ruta, {CABECERA_TOKEN: token})
        assert estado == 200 and hashlib.sha256(cuerpo).hexdigest() == sha
        assert cabeceras["content-type"] == "application/pdf"
        assert cabeceras["content-disposition"].startswith("attachment;")
        assert "access-control-allow-origin" not in cabeceras
        estado, cabeceras, _ = _get(puerto, ruta, {CABECERA_TOKEN: token,
                                                   "Origin": "http://localhost:3000"})
        assert estado == 403 and "access-control-allow-origin" not in cabeceras
    finally:
        srv.shutdown()
        srv.server_close()
    with preparar(db) as almacen:
        abiertos = almacen.conn.execute(
            "SELECT usuario_id FROM evento WHERE tipo = 'documento_abierto'").fetchall()
    assert [a[0] for a in abiertos] == [dora]


def test_bms_agent_original_guarda_el_pdf(tmp_path, out_v1, pdfs_ejemplo, capsys) -> None:
    import hashlib

    from bms_agent.almacen import preparar
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(pdfs_ejemplo),
                 "--db", str(db)]) == 0
    with preparar(db) as almacen:
        factura, sha = almacen.conn.execute(
            "SELECT f.id, d.sha256 FROM factura f JOIN documento d ON d.id = f.documento_id "
            "WHERE d.ruta_cas IS NOT NULL ORDER BY f.id LIMIT 1").fetchone()
    capsys.readouterr()
    destino = tmp_path / "original.pdf"
    assert main(["original", str(factura), "--salida", str(destino), "--db", str(db)]) == 0
    assert hashlib.sha256(destino.read_bytes()).hexdigest() == sha
    assert main(["original", str(factura), "--salida", str(destino), "--db", str(db)]) == 1
    assert "no se sobrescribe" in capsys.readouterr().err
    with preparar(db) as almacen:
        assert almacen.conn.execute("SELECT count(*) FROM evento WHERE tipo = "
                                    "'documento_abierto'").fetchone()[0] == 1


# ============================================================ 11. roles a medida

def test_un_rol_a_medida_por_la_cli_no_da_lo_que_no_lleva(tmp_path, capsys) -> None:
    """La revision: los permisos solo se daban en tres paquetes. `rol crear` hace uno con los
    que se digan (captura: pasar a limpio, sin verificar cuentas ni marcar pagos)."""
    from bms_agent import permisos
    from bms_agent.almacen import preparar
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["usuario", "crear", "Eva", "--db", str(db)]) == 0
    assert main(["rol", "crear", "captura", "--db", str(db)]) == 0
    assert main(["rol", "crear", "raro", "--permiso", "volar", "--db", str(db)]) == 1
    assert main(["usuario", "asignar", "Eva", "captura", "--db", str(db)]) == 0
    capsys.readouterr()
    assert main(["rol", "listar", "--db", str(db)]) == 0
    listado = capsys.readouterr().out
    assert "captura" in listado and "editar_extraccion" in listado
    with preparar(db) as almacen:
        conn = almacen.conn
        eva = permisos.usuario_por_nombre(conn, "Eva")
        tiene = permisos.permisos_de(conn, eva)
        assert {"ver_facturas", "editar_extraccion", "cambiar_objeto"} <= tiene
        assert not tiene & {"confirmar_iban", "marcar_pagada", "anular_aviso", "admin",
                            "gestionar_btw"}
        assert conn.execute("SELECT count(*) FROM evento WHERE tipo = 'rol_creado'").fetchone()[
            0] >= 1


# ============================================================ 13. la fecha de recepcion

def test_una_factura_leida_de_una_carpeta_lleva_su_fecha_de_recepcion(almacen, tmp_path) -> None:
    """La revision: ninguna via de entrada daba la fecha de recepcion (solo la aceptaba de
    correo o de una ingesta). Leida de una carpeta, es el dia en que el sistema la registro."""
    from test_extraccion_pasada import PDF, ClienteFalso

    from bms_agent.ingesta import ingestar_pasada

    pdfs = tmp_path / "facturas"
    pdfs.mkdir()
    (pdfs / "a.pdf").write_bytes(PDF)
    ingestar_pasada(ClienteFalso(), [pdfs / "a.pdf"], tmp_path / "out", almacen=almacen)
    conn = almacen.conn
    fecha, registrado = conn.execute(
        "SELECT f.fecha_recepcion, d.registrado_en FROM factura f JOIN documento d "
        "ON d.id = f.documento_id").fetchone()
    assert fecha == "2026-10-14" and registrado.startswith("2026-10-14")
    fuente = conn.execute("SELECT fuente, fuente_ref FROM procedencia_campo WHERE tabla = "
                          "'factura' AND campo = 'fecha_recepcion'").fetchone()
    assert fuente["fuente"] == "calculado" and fuente["fuente_ref"].startswith("documento:")


def test_lo_que_llega_de_out_no_toma_la_fecha_de_la_migracion(tipado) -> None:
    assert {f[0] for f in tipado.conn.execute("SELECT fecha_recepcion FROM factura")} == {None}


# ============================================================ 14, 16 y 30. la ficha

def test_la_ficha_ensena_la_persona_de_la_linea_las_etiquetas_y_de_donde_vence(banco) -> None:
    """La revision: la ficha no tenia recurso_doc ni el nombre de la persona de una
    imputacion; los campos salian como base_cent o tipo_iva_pb; y un vencimiento calculado
    con el plazo del maestro no decia de donde salia (ninguna fuente era nunca el maestro)."""
    conn = banco.conn
    koster = factura_de(conn, "2026-0912")
    ficha = consultas.detalle(conn, koster)
    linea = ficha["lineas"][0]
    assert {"recurso_doc", "semana_doc", "tipo_turno_doc"} <= {c["campo"] for c in linea["campos"]}
    assert "recurso" in linea["imputaciones"][0]
    etiquetas = {c["campo"]: c["etiqueta"] for c in ficha["campos"]}
    assert etiquetas["base_cent"] == "Base (sin IVA)" and etiquetas["tipo_iva_pb"] == "Tipo de IVA"
    # 2026-0912 no imprime vencimiento: es su fecha mas los 30 dias de Koster en el maestro.
    v = ficha["vencimiento"]
    assert v["fuente"] == "maestro" and v["fuente_texto"] == "Del maestro"
    assert v["fuente_ref"].startswith("proveedor:") and v["plazo_dias"] == 30
    assert ficha["vencimiento"]["fecha"] == conn.execute(
        "SELECT vencimiento FROM factura_estado WHERE factura_id = ?", (koster,)).fetchone()[0]


def test_un_importe_se_escribe_como_lo_ensena_la_consola(vandijk) -> None:
    conn = vandijk.conn
    a = factura_de(conn, "2026-4471")
    _orden(conn, "fijar_campo", {"tabla": "factura", "fila_id": a, "campo": "total_cent",
                                 "valor": "2.902,80", "rev": _rev(conn, "factura", a)})
    assert conn.execute("SELECT total_cent FROM factura WHERE id = ?", (a,)).fetchone()[0] == \
        290280
    with pytest.raises(servicios.DatosNoValidos, match="miles o decimales"):
        _orden(conn, "fijar_campo", {"tabla": "factura", "fila_id": a, "campo": "total_cent",
                                     "valor": "2.902", "rev": _rev(conn, "factura", a)})


# ============================================================ 15. las horas por semana

def test_la_economia_por_semana_lleva_sus_horas(vandijk) -> None:
    """La revision: por_semana decia 0 horas en cada semana aunque las tuviera."""
    from bms_agent import permisos
    from bms_agent.importadores.tarifas import sembrar_tarifas
    from conftest import TARIFAS_V1

    conn = vandijk.conn
    sembrar_tarifas(conn, TARIFAS_V1)
    hallazgos.recalcular(conn)
    rijnhaven = conn.execute("SELECT id FROM objeto WHERE codigo = 'Rijnhaven'").fetchone()[0]
    a = factura_de(conn, "2026-4471")
    imputacion = conn.execute(
        "SELECT i.id, i.rev FROM factura_imputacion i JOIN factura_linea l ON l.id = i.linea_id "
        "WHERE i.factura_id = ? ORDER BY l.orden LIMIT 1", (a,)).fetchone()
    servicios.ejecutar(conn, "cambiar_objeto", {"imputacion_id": imputacion[0],
                                                "objeto_id": rijnhaven, "rev": imputacion[1],
                                                "motivo": MOTIVO},
                       usuario_id=permisos.usuario_por_nombre(conn, "Ana"))
    semanas = consultas.objeto(conn, rijnhaven)["economia"]["por_semana"]
    assert sum(s["horas_compra_mil"] for s in semanas) > 0
    assert sum(s["horas_compra_mil"] for s in semanas) == sum(
        m["horas_compra_mil"] for m in consultas.objeto(conn, rijnhaven)["economia"]["por_mes"])


# ============================================================ 9. la consola hace lo de cada dia

ACCIONES_DE_LA_CONSOLA = (
    "verificar_iban", "rechazar_iban", "atestar_iban", "fijar_telefono_verificacion",
    "marcar_pagada", "confirmar_pago", "retirar_pago", "anular_factura", "fusionar_factura",
    "deshacer_fusion", "dividir_linea", "anadir_linea", "anadir_referencia", "registrar_po",
    "corregir_po", "corregir_maestro", "anadir_alias", "cambiar_objeto")


def test_la_consola_tiene_un_formulario_para_cada_orden_de_cada_dia() -> None:
    """La revision: verificar una cuenta, confirmar un pago, anular, repartir una linea,
    registrar una PO o corregir el maestro solo se podian hacer por la CLI."""
    from bms_agent import consola_assets

    for accion in ACCIONES_DE_LA_CONSOLA:
        assert f"formulario('{accion}'" in consola_assets.SCRIPT, accion
        assert accion in servicios.ACCIONES, accion
    for ruta in ("/original", "/hoja.csv", "/api/v2/flujo", "/api/v2/recursos"):
        assert ruta in consola_assets.SCRIPT, ruta


@pytest.mark.skipif(__import__("shutil").which("node") is None, reason="sin node")
def test_la_consola_pinta_las_cuentas_los_pagos_y_la_caja_como_texto(banco, tmp_path) -> None:
    """Lo nuevo de la consola, con un nombre de proveedor que lleva HTML: se pinta como texto,
    y salen los botones de verificar, confirmar un pago, anular y repartir."""
    import subprocess

    from test_consola import DOM_DE_PRUEBA

    from bms_agent import consola_assets

    conn = banco.conn
    smit = factura_de(conn, "2026-112")
    importar_camt(banco, _ana(conn), camt053(apunte(
        "-653.40", "2026-10-13", iban="NL03RABO0312456789", nombre="Loodgietersbedrijf Smit",
        concepto="Factuur 2026-112")))
    proveedor = conn.execute("SELECT proveedor_id FROM factura WHERE id = ?",
                             (smit,)).fetchone()[0]
    datos = {"ficha": consultas.detalle(conn, smit),
             "vista": consultas.proveedor(conn, proveedor),
             "flujo": flujo_caja.flujo(conn, date(2026, 10, 14), desde=date(2026, 10, 1),
                                       hasta=date(2026, 10, 31))}
    assert datos["ficha"]["pagos"] and datos["ficha"]["pagos"][0]["estado"] == "propuesta"
    # Lo que llega de un extracto o de un maestro, con HTML dentro.
    datos["ficha"]["pagos"][0]["concepto"] = "<script>alert(1)</script>"
    datos["vista"]["nombre"] = "<img src=x onerror=alert(2)>"
    fichero = tmp_path / "datos.json"
    fichero.write_text(json.dumps(datos, default=str), encoding="utf-8")
    script = tmp_path / "consola.js"
    script.write_text(consola_assets.SCRIPT, encoding="utf-8")
    prueba = tmp_path / "prueba.js"
    prueba.write_text(DOM_DE_PRUEBA.split("vm.runInThisContext")[0] + r"""
vm.runInThisContext(fs.readFileSync(process.argv[3], 'utf8'));
const B = window.BMSConsola;
const ficha = new Elemento('div'); B.pintarDetalle(ficha, datos.ficha);
const vista = new Elemento('div'); B.pintarParte(vista, 'proveedores', datos.vista);
const caja = new Elemento('div'); B.pintarCaja(caja, datos.flujo);
const atributos = [];
creados.forEach(e => Object.values(e.atributos).forEach(v => atributos.push(v)));
process.stdout.write(JSON.stringify({
  etiquetas: [...new Set(creados.map(e => e.tagName))], ficha: ficha.textContent,
  vista: vista.textContent, caja: caja.textContent, atributos: atributos}));
""", encoding="utf-8")
    proceso = subprocess.run(["node", str(prueba), str(fichero), str(script)],
                             capture_output=True, text=True, timeout=60)
    assert proceso.returncode == 0, proceso.stderr
    r = json.loads(proceso.stdout)
    assert "SCRIPT" not in r["etiquetas"] and not any("alert" in v for v in r["atributos"])
    assert "<script>alert(1)</script>" in r["ficha"]
    assert "<img src=x onerror=alert(2)>" in r["vista"]
    # Las v1 no traen su PDF: la ficha lo dice (con el PDF, el boton de descargarlo).
    for boton in ("Confirmar el pago", "Retirar", "Anular la factura", "no está en el almacén",
                  "Repartir entre Objetos", "Añadir una referencia", "Vence el"):
        assert boton in r["ficha"], boton
    for boton in ("Verificar por teléfono", "Rechazar la cuenta", "Atestar lo heredado",
                  "Cambiar el teléfono", "Teléfono de verificación", "071-5556667"):
        assert boton in r["vista"], boton
    assert "El periodo pedido" in r["caja"] and "Ver el periodo" in r["caja"]


# ============================================================ 20. la hoja del BTW sin la CLI

def test_la_hoja_del_btw_se_descarga_con_sus_bytes_y_su_sha256(servidor_datos) -> None:
    """La revision: en Docker la hoja no se podia sacar (--salida en un sistema de solo lectura,
    y la consola solo daba su hash). Ahora la consola la descarga con los bytes que se hashean."""
    import hashlib

    from bms_agent.serve import CABECERA_TOKEN

    puerto, token = servidor_datos
    estado, cabeceras, cuerpo = _get(puerto, "/api/v2/btw/2026-T3/hoja.csv",
                                     {CABECERA_TOKEN: token})
    assert estado == 200 and cabeceras["content-type"].startswith("text/csv")
    assert cabeceras["content-disposition"] == 'attachment; filename="btw-2026-T3.csv"'
    estado, _c, json_hoja = _get(puerto, "/api/v2/btw/2026-T3/hoja", {CABECERA_TOKEN: token})
    assert hashlib.sha256(cuerpo).hexdigest() == json.loads(json_hoja)["sha256"]
    assert _get(puerto, "/api/v2/btw/2026-T3/hoja.csv", {})[0] == 401


def test_una_salida_que_no_se_puede_escribir_es_una_linea_y_no_una_traza(tmp_path,
                                                                        capsys) -> None:
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["usuario", "crear", "Eva", "--db", str(db)]) == 0
    capsys.readouterr()
    codigo = main(["btw", "hoja", "2026-T3", "--salida", str(tmp_path / "no" / "h.csv"),
                   "--db", str(db)])
    salida = capsys.readouterr()
    assert codigo == 1 and "Traceback" not in salida.err
    assert "No se puede usar el fichero" in salida.err and "no existe" in salida.err


# ============================================================ 18. las cuentas propias

def test_las_cuentas_propias_se_ponen_por_una_orden_y_el_extracto_entra(tmp_path,
                                                                       capsys) -> None:
    """La revision (bloqueante): con datos de verdad cada extracto se rechazaba porque
    config/empresa.yaml no tiene cuentas propias, y en Docker ese fichero es de solo lectura.
    El rechazo dice ahora como se arregla, y `empresa fijar` lo arregla."""
    from conftest import CUENTA_PROPIA

    from bms_agent import permisos
    from bms_agent.almacen import preparar
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    extracto = tmp_path / "extracto.xml"
    extracto.write_bytes(camt053(apunte("-10.00", iban=DESCONOCIDA, concepto="Algo")))
    with preparar(db) as almacen:
        ana = persona(almacen.conn, "Ana", "administrador")
        token = permisos.emitir_token(almacen.conn, ana)
        dora = permisos.emitir_token(almacen.conn, persona(almacen.conn, "Dora", "consulta"))
    assert main(["importar", "banco", "extracto", str(extracto), "--db", str(db),
                 "--token", token]) != 0
    assert "empresa fijar" in capsys.readouterr().out
    assert main(["empresa", "ver", "--db", str(db)]) == 0
    assert "Falta: las cuentas propias" in capsys.readouterr().out
    # Quien solo consulta no la pone.
    assert main(["empresa", "fijar", "--cuenta", CUENTA_PROPIA, "--db", str(db),
                 "--token", dora]) == 1
    assert main(["empresa", "fijar", "--cuenta", "NL00BANK0000000000", "--db", str(db),
                 "--token", token]) == 1
    assert "digito de control" in capsys.readouterr().err
    assert main(["empresa", "fijar", "--cuenta", CUENTA_PROPIA, "--btw-id", "NL001122334B01",
                 "--kvk", "12345678", "--db", str(db), "--token", token]) == 0
    assert CUENTA_PROPIA in capsys.readouterr().out
    extracto.write_bytes(camt053(apunte("-10.00", iban=DESCONOCIDA, concepto="Algo"),
                                 identificador="STMT-2"))
    assert main(["importar", "banco", "extracto", str(extracto), "--db", str(db),
                 "--token", token]) == 0
    with preparar(db) as almacen:
        assert almacen.conn.execute("SELECT count(*) FROM movimiento_bancario").fetchone()[0] == 1


# ============================================================ 22. la verificacion que no vale

def test_una_verificacion_a_otro_telefono_no_dice_hecho_ni_sale_con_cero(tmp_path,
                                                                       capsys) -> None:
    """La revision: verificar una cuenta llamando a un numero que no es el del maestro
    quedaba apuntado (F8) y la CLI decia "Hecho" y salia con 0. Ahora dice que no vale, por
    que, y sale con SALIDA_SIN_EFECTO; la consola lo ensena como un error."""
    from bms_agent import permisos
    from bms_agent.almacen import preparar
    from bms_agent.cli import SALIDA_SIN_EFECTO, main

    db = tmp_path / "datos" / "bms.sqlite3"
    with preparar(db) as almacen:
        ana = persona(almacen.conn, "Ana", "administrador")
        importar_fichero(almacen, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana)
        token = permisos.emitir_token(almacen.conn, ana)
        van_dijk = almacen.conn.execute(
            "SELECT id FROM proveedor WHERE exact_id = '20001'").fetchone()[0]
    codigo = main(["iban", "verificar", "--proveedor-id", str(van_dijk),
                   "--iban", "NL02ABNA0123456789", "--telefono", "010 9999999",
                   "--motivo", MOTIVO, "--db", str(db), "--token", token])
    salida = capsys.readouterr().out
    assert codigo == SALIDA_SIN_EFECTO != 0
    assert "NO VALE" in salida and "no es el que tenia" in salida and "Hecho" not in salida
    # La llamada al numero del maestro si vale, y es "Hecho".
    codigo = main(["iban", "verificar", "--proveedor-id", str(van_dijk),
                   "--iban", "NL02ABNA0123456789", "--telefono", "010-1234567",
                   "--motivo", MOTIVO, "--db", str(db), "--token", token])
    assert codigo == 0 and capsys.readouterr().out.startswith("Hecho")


def test_la_consola_dice_como_error_una_verificacion_que_no_vale() -> None:
    from bms_agent.consola_assets import SCRIPT

    assert "detalle.eficaz === false" in SCRIPT
    assert "decir(resumen(r.diferencia), !!noVale(r.diferencia))" in SCRIPT


# ============================================================ 21. iban listar

def test_iban_listar_da_el_telefono_y_la_cuenta_impresa_que_f3_pide_verificar(banco) -> None:
    """La revision: `iban listar` no daba el numero al que llamar ni la cuenta nueva de una
    factura (no esta en el registro hasta que alguien la decide), y la guia lo mandaba ahi."""
    filas = {p["proveedor"]: p for p in consultas.registro_de_cuentas(banco.conn)}
    koster = filas["Elektro Installatie Koster"]
    assert koster["telefono_verificacion"] == "0182-555123"
    assert [c["iban"] for c in koster["cuentas"]] == ["NL20INGB0001234567"]
    assert [v["iban"] for v in koster["sin_registrar"]] == ["NL75INGB0002445689"]
    # Smit no tiene cuenta en el maestro: lo impreso sale igual.
    assert [v["iban"] for v in filas["Loodgietersbedrijf Smit"]["sin_registrar"]] == [
        "NL03RABO0312456789"]
    assert filas["Bouwtechniek Van Dijk BV"]["sin_registrar"] == []


def test_iban_listar_por_la_cli(tmp_path, out_v1, capsys) -> None:
    from bms_agent.almacen import preparar
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(tmp_path / "no"),
                 "--db", str(db)]) == 0
    with preparar(db) as almacen:
        ana = persona(almacen.conn, "Ana", "administrador")
        importar_fichero(almacen, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana)
    capsys.readouterr()
    assert main(["iban", "listar", "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    koster = salida[salida.index("Elektro Installatie Koster"):]
    koster = koster[:koster.index("\n", koster.index("NL75INGB0002445689"))]
    assert "se llama al 0182-555123" in koster and "NL20INGB0001234567" in koster
    assert "fuera del registro" in koster and "(F3)" in koster
    # La vista del proveedor dice lo mismo: a que numero se llama y que cuenta espera.
    with preparar(db) as almacen:
        id_koster = almacen.conn.execute(
            "SELECT id FROM proveedor WHERE exact_id = '20003'").fetchone()[0]
    assert main(["proveedor", str(id_koster), "--db", str(db)]) == 0
    vista = capsys.readouterr().out
    assert "0182-555123" in vista and "NL75INGB0002445689" in vista and "(F3)" in vista


# ============================================================ 26. None, () y "Ano"

def test_la_cli_no_ensena_none_ni_parentesis_vacios_ni_ano(tmp_path, capsys) -> None:
    """La revision: en una base nueva `buscar` decia "el estado es del None"; en la de
    prueba, `cliente 1` decia "factura None" en un aviso de la parte, `btw ver` "factura
    DGG-2026-118 ()" y "Ano 2026", y `objeto 1` "ano 2026"."""
    from bms_agent.cli import main

    nueva = tmp_path / "nueva" / "bms.sqlite3"
    assert main(["db", "init", "--db", str(nueva)]) == 0
    capsys.readouterr()
    assert main(["buscar", "--db", str(nueva)]) == 0
    assert "None" not in capsys.readouterr().out
    demo = tmp_path / "demo" / "demo.sqlite3"
    assert main(["demo", "crear", "--db", str(demo)]) == 0
    capsys.readouterr()
    salida = ""
    for orden in (["cliente", "1"], ["btw", "ver"], ["objeto", "1"], ["proveedor", "1"]):
        assert main([*orden, "--db", str(demo)]) == 0
        salida += capsys.readouterr().out
    assert "None" not in salida and "()" not in salida
    assert "Ano " not in salida and " ano " not in salida
    assert "Año 2026 hasta hoy" in salida and "año 2026" in salida
    assert "(fuera de las cifras)" in salida


# ============================================================ 27. las pistas en Docker

def test_en_docker_las_pistas_son_las_de_docker(tmp_path, capsys, monkeypatch) -> None:
    """La revision: dentro del contenedor `demo crear`, `usuario token` y `ordenes` decian que
    se usara `bms-agent serve` o `bms-agent importar`, que alli no se pueden escribir."""
    from bms_agent import serve
    from bms_agent.cli import CONSOLA_DOCKER, main

    monkeypatch.setattr(serve, "en_contenedor", lambda *a: True)
    demo = tmp_path / "demo" / "demo.sqlite3"
    assert main(["demo", "crear", "--db", str(demo)]) == 0
    salida = capsys.readouterr().out
    assert "bms-agent serve" not in salida
    assert f"iniciar.bat -Demo la abre en {CONSOLA_DOCKER}" in salida
    assert main(["demo", "crear", "--db", str(demo)]) == 0
    salida = capsys.readouterr().out
    assert "bms-agent" not in salida and "iniciar.bat -Demo" in salida
    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["usuario", "crear", "Ana", "--db", str(db)]) == 0
    assert main(["usuario", "token", "Ana", "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    assert "bms-agent serve" not in salida and CONSOLA_DOCKER in salida
    assert main(["ordenes", "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    assert "bms-agent importar" not in salida and "importar.bat" in salida
    # Fuera del contenedor, la orden de siempre.
    monkeypatch.setattr(serve, "en_contenedor", lambda *a: False)
    assert main(["ordenes", "--db", str(db)]) == 0
    assert "bms-agent importar po_csv" in capsys.readouterr().out


# ============================================================ 25. argparse en castellano

@pytest.mark.parametrize("orden, esperado", [
    (["btw"], "faltan argumentos: accion"),
    (["proveedor", "abc"], "el argumento id: 'abc' no es un numero entero"),
    (["export", "--v2", "--salida", "x"], "no se conocen estos argumentos: --salida x"),
    (["cat"], "el argumento orden: 'cat' no es ninguna de las posibles"),
])
def test_los_errores_de_la_linea_de_comandos_son_en_castellano(orden, esperado,
                                                               capsys) -> None:
    """La revision: los errores de argparse salian en ingles ("the following arguments are
    required", "invalid int value", "unrecognized arguments", "invalid choice")."""
    from bms_agent.cli import main

    with pytest.raises(SystemExit) as salida:
        main(orden)
    assert salida.value.code == 2
    error = capsys.readouterr().err
    assert error.startswith("uso: bms-agent") and esperado in error
    assert "usage" not in error and "error: argument" not in error


def test_la_ayuda_es_en_castellano_y_dice_lo_que_hace_la_v1(capsys) -> None:
    from bms_agent.cli import main

    for orden in (["--help"], ["iban", "verificar", "--help"], ["btw", "hoja", "-h"]):
        with pytest.raises(SystemExit):
            main(orden)
        ayuda = capsys.readouterr().out
        assert ayuda.startswith("uso: ") and "muestra esta ayuda y sale" in ayuda
        assert "opciones:" in ayuda
        for ingles in ("usage:", "show this help", "positional arguments", "options:\n"):
            assert ingles not in ayuda.replace("opciones:\n", "")
    with pytest.raises(SystemExit):
        main(["--help"])
    ayuda = " ".join(capsys.readouterr().out.split())
    assert "Fase 0" not in ayuda
    assert "no paga, no presenta el BTW" in ayuda


def test_un_error_que_no_se_conoce_se_queda_como_estaba() -> None:
    from bms_agent.argumentos import traducir

    assert traducir("algo nuevo de argparse") == "algo nuevo de argparse"
    assert traducir("argument --desde: expected one argument") == (
        "el argumento --desde: le falta su valor")


# ============================================================ 29. "sí" en las preguntas

def _es_si_como_comun_ps1(respuesta: str) -> bool:
    """Lo que hace Es-Si de docker/comun.ps1 (aqui no hay PowerShell para ejecutarlo)."""
    texto = respuesta.strip().lower().replace(chr(0x00ED), "i")
    return texto in ("si", "s")


def test_las_preguntas_de_los_scripts_aceptan_si_con_tilde() -> None:
    """La revision: leer-facturas.ps1 y restaurar.ps1 solo aceptaban "si" sin tilde; quien
    escribia "sí" leia que no se habia hecho nada y podia creer lo contrario."""
    import re

    comun = (RAIZ / "docker" / "comun.ps1").read_text(encoding="ascii")
    funcion = comun[comun.index("function Es-Si"):]
    funcion = funcion[:funcion.index("\n}\n")]
    assert "[char]0x00ED" in funcion and '-eq "si"' in funcion and '-eq "s"' in funcion
    assert ".ToLower()" in funcion and ".Trim()" in funcion
    texto = (RAIZ / "docker" / "restaurar.ps1").read_text(encoding="ascii")
    assert not re.search(r'-ne\s+"si"', texto)
    assert "if (-not (Es-Si $respuesta))" in texto and "No has escrito si" in texto
    # Paso 17: en leer-facturas.ps1 el si lo espera el lector (`lectura esperar`, de la app o
    # escrito en la ventana), con lectura.es_si, que dice lo mismo que Es-Si.
    from bms_agent.lectura import es_si

    texto = (RAIZ / "docker" / "leer-facturas.ps1").read_text(encoding="ascii")
    assert "lectura esperar" in texto and not re.search(r'-ne\s+"si"', texto)
    for respuesta in ("si", "sí", "Sí", " SI ", "s"):
        assert _es_si_como_comun_ps1(respuesta) and es_si(respuesta), respuesta
    for respuesta in ("", "no", "sii", "yes"):
        assert not _es_si_como_comun_ps1(respuesta) and not es_si(respuesta), respuesta


# ============================================================ 24. trimestres de antes de empezar

def test_un_trimestre_presentado_antes_de_empezar_se_anota_como_dice_la_guia(tmp_path,
                                                                            capsys) -> None:
    """La revision: en una base nueva los trimestres de antes salian como por presentar y con
    el plazo pasado, y nada decia como anotarlos. La guia (uso-v1.md, "El primer día") da el
    camino: la hoja, listo y anotar con lo que se declaro; aqui se comprueba que funciona."""
    from bms_agent import permisos
    from bms_agent.almacen import preparar
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    with preparar(db) as almacen:
        token = permisos.emitir_token(almacen.conn, persona(almacen.conn, "Ana",
                                                            "administrador"))
    capsys.readouterr()
    assert main(["btw", "ver", "--json", "--db", str(db)]) == 0
    resumen = json.loads(capsys.readouterr().out)
    antes = [a["etiqueta"] for a in resumen["por_presentar"]]
    assert antes, "una base nueva tiene trimestres terminados sin anotar"
    trimestre = antes[-1]
    hoja = tmp_path / "hoja.csv"
    assert main(["btw", "hoja", trimestre, "--salida", str(hoja), "--db", str(db)]) == 0
    sha = capsys.readouterr().out.split("sha256 ")[1].split()[0]
    assert main(["btw", "listo", "--trimestre", trimestre, "--hoja-sha256", sha,
                 "--motivo", "Presentado antes de usar el agente", "--db", str(db),
                 "--token", token]) == 0
    capsys.readouterr()
    assert main(["btw", "ver", trimestre, "--json", "--db", str(db)]) == 0
    rev = json.loads(capsys.readouterr().out)["rev"]
    assert main(["btw", "anotar", "--trimestre", trimestre, "--rev", str(rev),
                 "--hoja-sha256", sha, "--referencia", "OB-ANTES-1",
                 "--importe-declarado", "1234,56", "--motivo", "Presentado antes de usar el "
                 "agente; lo declarado sale del acuse", "--db", str(db), "--token", token]) == 0
    capsys.readouterr()
    assert main(["btw", "ver", "--json", "--db", str(db)]) == 0
    despues = [a["etiqueta"] for a in json.loads(capsys.readouterr().out)["por_presentar"]]
    assert trimestre not in despues
    guia = (RAIZ / "docs" / "uso-v1.md").read_text(encoding="utf-8")
    assert "btw listo" in guia and "antes de usar el agente" in guia
