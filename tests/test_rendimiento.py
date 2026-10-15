"""Cinco mil facturas se recalculan en menos de dos segundos (puerta del paso 3).

El almacen se llena a mano, con los disparadores de guarda quitados en esta
base de prueba: crear cinco mil facturas por campos.py, con su auditoria
campo a campo, tardaria minutos, y lo que se mide aqui es la pasada del
motor (leer la instantanea, evaluar el catalogo, escribir la cache y los
hallazgos), no la ingesta. Los datos son como los de una administracion de
verdad: casi todo limpio, con algun total mal sumado, algun numero repetido
y algun periodo cobrado dos veces.
"""

from __future__ import annotations

import time
from datetime import date, timedelta

from bms_agent import hallazgos
from bms_agent.almacen import transaccion

FACTURAS = 5000
PROVEEDORES = 400
LIMITE_SEGUNDOS = 2.0
AHORA = "2026-10-14T09:30:00+00:00"


def _llenar(conn) -> None:
    for (nombre,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE '%_guarda_%' "
            "AND (name LIKE 'factura%' OR name LIKE 'procedencia_campo%')").fetchall():
        conn.execute(f"DROP TRIGGER {nombre}")
    facturas, lineas, imputaciones, procedencias = [], [], [], []
    linea_id = 0
    for i in range(1, FACTURAS + 1):
        proveedor = i % PROVEEDORES
        semana = date(2026, 1, 5) + timedelta(days=7 * (i // PROVEEDORES))
        fin = semana + timedelta(days=6 if i % 97 else 12)       # algun periodo que se pisa
        base = 100000 + (proveedor % 37) * 100
        iva = base * 21 // 100
        total = base + iva + (700 if i % 50 == 0 else 0)          # algun total mal sumado
        numero = f"2026-{i:05d}" if i % 333 else f"2026-{i - PROVEEDORES:05d}"
        facturas.append((
            i, numero, numero.replace("-", ""), f"Proveedor {proveedor}",
            f"NL{proveedor:09d}B01", semana.isoformat(), semana.isoformat(), fin.isoformat(),
            base, iva, total))
        for orden in (1, 2):
            linea_id += 1
            importe = base // 2
            lineas.append((linea_id, i, orden, f"Obra {proveedor % 20}", importe * 100 // 20,
                           importe))
            imputaciones.append((linea_id, i, linea_id))
        procedencias.extend(("factura", i, campo) for campo in (
            "numero", "emisor_nombre_doc", "emisor_btw_doc", "fecha_factura", "periodo_inicio",
            "periodo_fin", "base_cent", "iva_cent", "total_cent", "tipo_iva_pb"))
    with transaccion(conn):
        conn.executemany(
            "INSERT INTO factura (id, sentido, tipo, origen, numero, numero_norm, "
            "emisor_nombre_doc, emisor_btw_doc, fecha_factura, periodo_inicio, periodo_fin, "
            "base_cent, iva_cent, total_cent, tipo_iva_pb, tratamiento_iva, iban_doc) "
            "VALUES (?, 'entrante', 'factura', 'manual', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 2100, "
            "'estandar', 'NL02ABNA0123456789')", facturas)
        conn.executemany(
            "INSERT INTO factura_linea (id, factura_id, orden, descripcion_doc, objeto_doc, "
            "unidad, cantidad_mil, tarifa_e4, importe_cent) "
            "VALUES (?, ?, ?, 'Montagewerk', ?, 'hora', 20000, ?, ?)", lineas)
        conn.executemany("INSERT INTO factura_imputacion (id, factura_id, linea_id) "
                         "VALUES (?, ?, ?)", imputaciones)
        conn.executemany(
            "INSERT INTO procedencia_campo (tabla, fila_id, campo, fuente, fuente_original, "
            "rev_campo, cambiado_en, cambiado_por) VALUES (?, ?, ?, 'extraccion', 'extraccion', "
            "0, ?, 1)", [(*p, AHORA) for p in procedencias])


def _medir(conn) -> tuple[float, hallazgos.Diferencia]:
    inicio = time.perf_counter()
    diferencia = hallazgos.recalcular(conn, motivo="diaria")
    return time.perf_counter() - inicio, diferencia


def test_cinco_mil_facturas_se_recalculan_en_menos_de_dos_segundos(db) -> None:
    _llenar(db)
    primera, diferencia = _medir(db)
    hallazgos_ = diferencia.pendientes.get("abierto", 0)
    assert sum(diferencia.evaluaciones.values()) >= FACTURAS * 14
    assert 100 <= hallazgos_ <= 500, diferencia.resumen()
    assert {t.regla for t in diferencia.transiciones} >= {"D4", "B2", "B4"}
    assert primera < LIMITE_SEGUNDOS, f"la primera pasada tardo {primera:.2f} s"

    # La de cada dia, sin cambios, tampoco: y no escribe nada nuevo.
    segunda, otra = _medir(db)
    assert otra.transiciones == []
    assert segunda < LIMITE_SEGUNDOS, f"la segunda pasada tardo {segunda:.2f} s"
