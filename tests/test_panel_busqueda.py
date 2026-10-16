"""Panel principal, busqueda, vista economica de los Objetos e historia (paso 12).

Puertas del paso 12 que viven aqui, sobre el almacen entero:

- propiedades de consistencia: lo pendiente de un proveedor (y de un cliente)
  es la suma de lo pendiente de sus facturas abiertas, tal como las encuentra
  la busqueda; y lo facturado por Objeto mas lo que no es de ningun Objeto es
  la base de todas las ventas que cuentan (y lo mismo con los costes);
- un test por cada filtro del §18 de la lista de funciones, con su respuesta
  calculada aparte (un oraculo) sobre un escenario donde ningun filtro da
  todas las facturas ni ninguna.

La puerta de /api/datos (byte a byte la foto) y la del contrato v2 estan en
test_contrato_v2.py.
"""

from __future__ import annotations

import random
from datetime import date

import pytest
from conftest import factura_de, persona
from test_ventas import (
    EXACT_CLIENTES,
    MOTIVO,
    OBJETOS,
    VENTAS,
    _ana,
    _confirmar,
    _orden,
    _pagar,
    _relacion,
    _rev,
    _sustituta,
    compras,
)

from test_planning import _cambiado, _planning, maestros  # noqa: F401

from bms_agent import consultas, flujo_caja, hallazgos, relaciones
from bms_agent.importadores.registrar import importar_fichero

COMPRAS = ("2026-018", "2026-0912", "B-2026-077", "2026-112", "2026-4471")


def _cliente(conn, exact_id: str) -> int:
    return conn.execute("SELECT id FROM cliente WHERE exact_id = ?", (exact_id,)).fetchone()[0]


def _objeto(conn, codigo: str) -> int:
    return conn.execute("SELECT id FROM objeto WHERE codigo = ?", (codigo,)).fetchone()[0]


@pytest.fixture
def escenario(compras, reloj):
    """Compras v1, ventas de Exact con su PO, un abono enlazado, una factura pagada, otra
    anulada, un campo corregido a mano y otra devuelta: hay de todo para cada filtro."""
    conn = compras.conn
    ana = _ana(conn)
    importar_fichero(compras, "exact", "clientes", EXACT_CLIENTES, lanzado_por=ana)
    importar_fichero(compras, "maestro_csv", "objetos", OBJETOS, lanzado_por=ana)
    importar_fichero(compras, "exact", "facturas_venta", VENTAS, lanzado_por=ana)
    haven = _cliente(conn, "10001")
    _orden(conn, "registrar_po", {"numero": "PO-4500123", "lado": "cliente", "parte_id": haven,
                                  "valor": "10000", "objetos": [_objeto(conn, "Rijnhaven")]})
    _confirmar(conn, _relacion(conn, factura_de(conn, "C2026-0005"),
                               factura_de(conn, "V2026-0101")))
    _pagar(conn, factura_de(conn, "2026-018"))
    _orden(conn, "anular_factura", {"factura_id": factura_de(conn, "2026-112"),
                                    "rev": _rev(conn, factura_de(conn, "2026-112")),
                                    "motivo": "Factura emitida por error, la retira el proveedor"})
    f = factura_de(conn, "2026-0912")
    _orden(conn, "fijar_campo", {"tabla": "factura", "fila_id": f, "campo": "emisor_nombre_doc",
                                 "valor": "De Vries Montage", "motivo": "El nombre del maestro",
                                 "rev": _rev(conn, f)})
    f = factura_de(conn, "B-2026-077")
    _orden(conn, "devolver_factura", {"factura_id": f, "huella": consultas.detalle(
        conn, f)["huella_contenido"], "motivo": "Falta el detalle de las horas"})
    _orden(conn, "crear_excepcion", {"tabla": "factura", "fila_id": factura_de(conn, "V2026-0102"),
                                     "titulo": "Confirmar el Objeto con el cliente",
                                     "motivo": "El cliente no ha confirmado la obra"})
    # Seis dias despues, con la pasada diaria: las de mediados de octubre ya han vencido.
    reloj.avanzar(days=6)
    hallazgos.recalcular(conn, motivo="diaria")
    return compras


def test_el_escenario_tiene_de_todo(escenario) -> None:
    conn = escenario.conn
    resultado = consultas.buscar(conn, {"limite": "1000"})
    filas = resultado["facturas"]
    assert len(filas) == resultado["total"] == conn.execute(
        "SELECT count(*) FROM factura").fetchone()[0]
    assert resultado["al_dia"] and resultado["estado_del"] == "2026-10-20"
    assert {"pendiente", "vencida", "pagada", "anulada", "acreditada"} <= {
        f["estado_pago"] for f in filas}
    assert {"sin_revisar", "necesita_revision"} <= {f["estado_revision"] for f in filas}
    assert len({f["nivel"] for f in filas}) >= 3


# ============================================================ un test por filtro del §18

def _todas(conn) -> list[dict]:
    return consultas.buscar(conn, {"limite": "1000"})["facturas"]


def _ids(conn, peticion: dict) -> set[int]:
    resultado = consultas.buscar(conn, {**peticion, "limite": "1000"})
    assert resultado["total"] == len(resultado["facturas"])
    return {f["id"] for f in resultado["facturas"]}


def _estado(conn, columna: str) -> dict[int, object]:
    """Lo que dice la cache de estado de cada factura (el oraculo de los filtros de estado)."""
    return dict(conn.execute(f"SELECT factura_id, {columna} FROM factura_estado"))


def _imputadas(conn, condicion: str, *parametros) -> set[int]:
    return {f[0] for f in conn.execute(
        f"SELECT i.factura_id FROM factura_imputacion AS i WHERE i.retirada_en IS NULL "
        f"AND {condicion}", parametros)}


def _comprobar(conn, peticion: dict, esperado: set[int]) -> None:
    """La busqueda da exactamente lo esperado, y el filtro separa algo: ni todas ni ninguna."""
    todas = {f["id"] for f in _todas(conn)}
    obtenido = _ids(conn, peticion)
    assert obtenido == esperado, (peticion, sorted(obtenido), sorted(esperado))
    assert 0 < len(obtenido) < len(todas), peticion


def test_filtro_numero_de_factura(escenario) -> None:
    """§18 Invoice number: parte del numero, sin separadores ni mayusculas."""
    conn = escenario.conn
    from bms_agent.parsing import normalizar_referencia

    esperado = {f[0] for f in conn.execute("SELECT id, numero FROM factura")
                if "4471" in (normalizar_referencia(f[1]) or "")}
    _comprobar(conn, {"numero": "44 71"}, esperado)
    assert factura_de(conn, "2026-4471") in esperado
    _comprobar(conn, {"numero": "v2026/0101"}, {factura_de(conn, "V2026-0101")})


def test_filtro_proveedor(escenario) -> None:
    """§18 Provider: las facturas del proveedor del maestro (tambien sus abonos)."""
    conn = escenario.conn
    van_dijk = conn.execute("SELECT proveedor_id FROM factura WHERE numero = '2026-4471'"
                            ).fetchone()[0]
    esperado = {f[0] for f in conn.execute("SELECT id FROM factura WHERE proveedor_id = ?",
                                           (van_dijk,))}
    assert esperado == {factura_de(conn, "2026-4471"), factura_de(conn, "CN-2026-031")}
    _comprobar(conn, {"proveedor_id": str(van_dijk)}, esperado)


def test_filtro_cliente(escenario) -> None:
    """§18 Client: sus ventas y las compras imputadas a uno de sus Objetos."""
    conn = escenario.conn
    haven = _cliente(conn, "10001")
    ventas = {f[0] for f in conn.execute("SELECT id FROM factura WHERE cliente_id = ?", (haven,))}
    objetos = [f[0] for f in conn.execute("SELECT id FROM objeto WHERE cliente_id = ?", (haven,))]
    compras_ = set().union(*(_imputadas(conn, "i.objeto_id = ?", o) for o in objetos))
    assert ventas and compras_ - ventas
    _comprobar(conn, {"cliente_id": str(haven)}, ventas | compras_)


def test_filtro_objeto(escenario) -> None:
    """§18 Object: con alguna linea imputada al Objeto, de compra o de venta."""
    conn = escenario.conn
    schiedam = _objeto(conn, "Schiedam")
    esperado = _imputadas(conn, "i.objeto_id = ?", schiedam)
    assert {factura_de(conn, "V2026-0102"), factura_de(conn, "2026-0912")} <= esperado
    _comprobar(conn, {"objeto_id": str(schiedam)}, esperado)


def test_filtro_po(escenario) -> None:
    """§18 PO: por la PO registrada o por su numero (impreso o imputado)."""
    conn = escenario.conn
    po = conn.execute("SELECT id FROM orden_compra WHERE numero = 'PO-4500123'").fetchone()[0]
    esperado = _imputadas(conn, "i.orden_compra_id = ?", po) | {f[0] for f in conn.execute(
        "SELECT factura_id FROM factura_referencia WHERE retirada_en IS NULL "
        "AND orden_compra_id = ?", (po,))}
    assert factura_de(conn, "V2026-0101") in esperado
    _comprobar(conn, {"orden_compra_id": str(po)}, esperado)
    _comprobar(conn, {"po": "po 4500123"}, esperado)


def test_filtro_periodo(escenario) -> None:
    """§18 Period: fecha de factura desde y hasta, periodo de prestacion que se cruza, y el
    trimestre del BTW."""
    conn = escenario.conn
    fechas = dict(conn.execute("SELECT id, fecha_factura FROM factura"))
    _comprobar(conn, {"fecha_desde": "2026-09-16"},
               {i for i, f in fechas.items() if f and f >= "2026-09-16"})
    _comprobar(conn, {"fecha_hasta": "2026-09-15"},
               {i for i, f in fechas.items() if f and f <= "2026-09-15"})
    _comprobar(conn, {"trimestre": "2026-T4"},
               {i for i, f in fechas.items() if f and f >= "2026-10-01"})
    # El periodo: el de la cabecera o, sin el, el de sus lineas.
    periodos = {}
    for i, inicio, fin in conn.execute("SELECT id, periodo_inicio, periodo_fin FROM factura"):
        desde, hasta = conn.execute(
            "SELECT min(coalesce(fecha_inicio, fecha_trabajo)), "
            "max(coalesce(fecha_fin, fecha_trabajo, fecha_inicio)) FROM factura_linea "
            "WHERE factura_id = ? AND retirada_en IS NULL", (i,)).fetchone()
        periodos[i] = (inicio or desde, fin or hasta)
    _comprobar(conn, {"periodo_desde": "2026-09-10"},
               {i for i, (_d, h) in periodos.items() if h and h >= "2026-09-10"})
    _comprobar(conn, {"periodo_hasta": "2026-09-06"},
               {i for i, (d, _h) in periodos.items() if d and d <= "2026-09-06"})


def test_filtro_vencimiento(escenario) -> None:
    """§18 Due date: por el vencimiento efectivo (el impreso o la fecha mas el plazo)."""
    conn = escenario.conn
    vence = _estado(conn, "vencimiento")
    _comprobar(conn, {"vence_desde": "2026-10-16", "vence_hasta": "2026-10-31"},
               {i for i, v in vence.items() if v and "2026-10-16" <= v <= "2026-10-31"})
    _comprobar(conn, {"vence_hasta": "2026-10-15"},
               {i for i, v in vence.items() if v and v <= "2026-10-15"})


def test_filtro_estado_de_pago(escenario) -> None:
    """§18 Payment status: uno o varios estados de pago."""
    conn = escenario.conn
    estado = _estado(conn, "estado_pago")
    _comprobar(conn, {"estado_pago": "pagada,anulada"},
               {i for i, e in estado.items() if e in ("pagada", "anulada")})
    _comprobar(conn, {"estado_pago": ["vencida"]},
               {i for i, e in estado.items() if e == "vencida"})


def test_filtro_estado_de_revision(escenario) -> None:
    """§18 Review status."""
    conn = escenario.conn
    estado = _estado(conn, "estado_revision")
    _comprobar(conn, {"estado_revision": "necesita_revision"},
               {i for i, e in estado.items() if e == "necesita_revision"})
    assert factura_de(conn, "B-2026-077") in _ids(conn, {"estado_revision": "necesita_revision"})


def test_filtro_prioridad(escenario) -> None:
    """§18 Priority: uno o varios niveles."""
    conn = escenario.conn
    nivel = _estado(conn, "nivel")
    elegidos = sorted({n for n in nivel.values()})[:2]
    _comprobar(conn, {"nivel": ",".join(elegidos)},
               {i for i, n in nivel.items() if n in elegidos})


def test_filtro_calidad_del_dato(escenario) -> None:
    """§18 Data-quality status: una o varias calidades; "neutra" es sin ninguna marca."""
    conn = escenario.conn
    calidad = _estado(conn, "calidad")
    _comprobar(conn, {"calidad": "neutra"}, {i for i, c in calidad.items() if c is None})
    _comprobar(conn, {"calidad": "faltante,discrepancia"},
               {i for i, c in calidad.items() if c in ("faltante", "discrepancia")})


def test_filtro_ediciones_manuales(escenario) -> None:
    """§18 Manual edits (§11): editada, suplementada, corregida o con cambios sin resolver."""
    conn = escenario.conn
    corregida = _estado(conn, "corregida")
    editada = _estado(conn, "editada")
    _comprobar(conn, {"edicion": "corregida"}, {i for i, c in corregida.items() if c})
    assert factura_de(conn, "2026-0912") in _ids(conn, {"edicion": "corregida"})
    _comprobar(conn, {"edicion": "editada"}, {i for i, c in editada.items() if c})


def test_filtro_pendiente(escenario) -> None:
    """§18 Outstanding: pendiente o vencida; y lo contrario."""
    conn = escenario.conn
    estado = _estado(conn, "estado_pago")
    abiertas = {i for i, e in estado.items() if e in ("pendiente", "vencida")}
    _comprobar(conn, {"pendiente": "si"}, abiertas)
    _comprobar(conn, {"pendiente": "no"}, set(estado) - abiertas)


def test_filtro_vencida(escenario) -> None:
    """§18 Overdue."""
    conn = escenario.conn
    estado = _estado(conn, "estado_pago")
    _comprobar(conn, {"vencida": "si"}, {i for i, e in estado.items() if e == "vencida"})
    assert factura_de(conn, "2026-0912") in _ids(conn, {"vencida": "sí"})


def test_filtro_pagada(escenario) -> None:
    """§18 Paid."""
    conn = escenario.conn
    estado = _estado(conn, "estado_pago")
    _comprobar(conn, {"pagada": "si"}, {i for i, e in estado.items() if e == "pagada"})
    assert _ids(conn, {"pagada": "si"}) == {factura_de(conn, "2026-018")}


def test_filtro_anulada_o_acreditada(escenario) -> None:
    """§18 Cancelled / credited."""
    conn = escenario.conn
    estado = _estado(conn, "estado_pago")
    _comprobar(conn, {"anulada_acreditada": "si"},
               {i for i, e in estado.items() if e in ("anulada", "acreditada")})
    assert factura_de(conn, "2026-112") in _ids(conn, {"anulada_acreditada": "si"})


def test_los_filtros_de_mas(escenario) -> None:
    """Los que no estan en el §18 pero ayudan: sentido, texto, excepcion e importe."""
    conn = escenario.conn
    sentidos = dict(conn.execute("SELECT id, sentido FROM factura"))
    _comprobar(conn, {"sentido": "saliente"}, {i for i, s in sentidos.items() if s == "saliente"})
    _comprobar(conn, {"texto": "havenbedrijf"},
               {i for i, s in sentidos.items() if s == "saliente" and i in {
                   f[0] for f in conn.execute("SELECT id FROM factura WHERE receptor_nombre_doc "
                                              "LIKE 'Havenbedrijf%'")}})
    _comprobar(conn, {"excepcion": "si"},
               {i for i, e in _estado(conn, "excepcion_id").items() if e is not None})
    importes = {f[0]: abs(f[1] if f[1] is not None else f[2] or 0) for f in conn.execute(
        "SELECT id, base_cent, total_cent FROM factura") if (f[1] is not None or f[2] is not None)}
    _comprobar(conn, {"importe_min": "2000"}, {i for i, v in importes.items() if v >= 200000})
    _comprobar(conn, {"importe_max": "1500,50"}, {i for i, v in importes.items() if v <= 150050})


def test_los_filtros_se_suman(escenario) -> None:
    conn = escenario.conn
    schiedam = _objeto(conn, "Schiedam")
    vencidas = {i for i, e in _estado(conn, "estado_pago").items() if e == "vencida"}
    compras_ = {f[0] for f in conn.execute("SELECT id FROM factura WHERE sentido = 'entrante'")}
    esperado = vencidas & compras_ & _imputadas(conn, "i.objeto_id = ?", schiedam)
    assert esperado == {factura_de(conn, "2026-0912"), factura_de(conn, "2026-4471")}
    assert _ids(conn, {"sentido": "entrante", "vencida": "si",
                       "objeto_id": str(schiedam)}) == esperado


@pytest.mark.parametrize("peticion, error", [
    ({"proveedor": "3"}, "filtro desconocido"),
    ({"proveedor_id": "3 OR 1=1"}, "no es un numero entero"),
    ({"estado_pago": "pagada,aprobada"}, "aprobada no es ninguno"),
    ({"fecha_desde": "14-10-2026"}, "AAAA-MM-DD"),
    ({"vencida": "quizas"}, "si o no"),
    ({"importe_min": "1.000"}, "sin separador de miles"),
    ({"trimestre": "2026-T5"}, "trimestre"),
    ({"numero": "--"}, "nada que buscar"),
    ({"orden": "nombre"}, "orden"),
    ({"limite": "0"}, "limite"),
    ({"pendiente": ["si", "no"]}, "un valor"),
])
def test_un_filtro_que_no_se_entiende_se_rechaza(escenario, peticion, error) -> None:
    with pytest.raises(consultas.FiltroNoValido, match=error):
        consultas.buscar(escenario.conn, peticion)


def test_el_texto_de_quien_busca_nunca_entra_en_el_sql(escenario) -> None:
    """Un valor con comillas y SQL es un valor: no encuentra nada y no rompe nada."""
    conn = escenario.conn
    antes = conn.execute("SELECT count(*) FROM factura").fetchone()[0]
    for peticion in ({"numero": "'; DROP TABLE factura; --"},
                     {"texto": "x' OR '1'='1"}, {"po": "1' OR 1=1 --"}):
        assert _ids(conn, peticion) == set()
    assert conn.execute("SELECT count(*) FROM factura").fetchone()[0] == antes
    # Y en el codigo: lo escrito no aparece en el fragmento de ningun filtro, que lleva un
    # parametro por cada valor.
    centinelas = {"texto": "zq9x", "entero": "987654", "fecha": "2031-07-15",
                  "importe": "4321", "trimestre": "2031-T2"}
    for filtro in consultas.FILTROS.values():
        if filtro.tipo in centinelas:
            fragmento, parametros = filtro.traducir(filtro.nombre, [centinelas[filtro.tipo]])
            assert centinelas[filtro.tipo] not in fragmento, filtro.nombre
        else:
            valores = list(filtro.valores) if filtro.tipo == "lista" else ["si"]
            fragmento, parametros = filtro.traducir(filtro.nombre, [",".join(valores)])
        assert fragmento.count("?") == len(parametros), filtro.nombre


def test_paginar_y_ordenar(escenario) -> None:
    conn = escenario.conn
    todas = consultas.buscar(conn, {"limite": "1000"})["facturas"]
    primera = consultas.buscar(conn, {"limite": "3"})
    segunda = consultas.buscar(conn, {"limite": "3", "pagina": "2"})
    assert primera["total"] == segunda["total"] == len(todas)
    assert [f["id"] for f in primera["facturas"] + segunda["facturas"]] == [
        f["id"] for f in todas[:6]]
    por_fecha = consultas.buscar(conn, {"orden": "fecha", "limite": "1000"})["facturas"]
    fechas = [f["fecha_factura"] for f in por_fecha if f["fecha_factura"]]
    assert fechas == sorted(fechas, reverse=True)
    por_importe = consultas.buscar(conn, {"orden": "importe", "limite": "1000"})["facturas"]
    importes = [abs(f["base_cent"] if f["base_cent"] is not None else f["total_cent"] or 0)
                for f in por_importe]
    assert importes == sorted(importes, reverse=True)


def test_la_busqueda_dice_de_que_dia_es_el_estado(escenario, reloj) -> None:
    """Lo que depende de hoy (vencida) es de la ultima pasada: se dice, y sin pasada de hoy
    la respuesta no esta al dia."""
    conn = escenario.conn
    assert consultas.buscar(conn)["al_dia"]
    reloj.avanzar(days=1)
    resultado = consultas.buscar(conn)
    assert resultado["estado_del"] == "2026-10-20" and not resultado["al_dia"]
    assert not consultas.panel(conn)["al_dia"]


# ============================================================ puerta: consistencia

def _escenario_al_azar(almacen, semilla: int) -> None:
    """Pagos parciales, enteros y de mas, una sustitucion, una anulacion, una linea dividida
    entre dos Objetos y otra sin Objeto, al azar."""
    conn = almacen.conn
    azar = random.Random(semilla)
    if azar.random() < 0.5:
        _orden(conn, "enlazar_facturas", {"origen_id": factura_de(conn, "CN-2026-031"),
                                          "destino_id": factura_de(conn, "2026-4471"),
                                          "tipo": "acredita", "motivo": MOTIVO})
    if azar.random() < 0.5:
        nueva = _sustituta(almacen, citar=False)
        _orden(conn, "enlazar_facturas", {"origen_id": nueva,
                                          "destino_id": factura_de(conn, "2026-4471"),
                                          "tipo": azar.choice(["sustituye", "corrige"]),
                                          "motivo": MOTIVO})
    for numero in ("2026-0912", "B-2026-077", "V2026-0101", "V2026-0102", "NW-2026-0042"):
        f = factura_de(conn, numero)
        total = conn.execute("SELECT total_cent FROM factura WHERE id = ?", (f,)).fetchone()[0]
        eleccion = azar.choice(["nada", "parcial", "entera", "de_mas", "anular"])
        if total is None or eleccion == "nada":
            continue
        if eleccion == "anular":
            if conn.execute("SELECT origen FROM factura WHERE id = ?", (f,)).fetchone()[0] \
                    == "extraccion":
                _orden(conn, "anular_factura", {"factura_id": f, "rev": _rev(conn, f),
                                                "motivo": MOTIVO})
        elif eleccion == "parcial":
            _pagar(conn, f, importe=f"{azar.randint(1, total - 1) / 100:.2f}")
        elif eleccion == "entera":
            _pagar(conn, f)
        else:
            _pagar(conn, f, importe=f"{(total + 1000) / 100:.2f}")
    if azar.random() < 0.6:
        # Una linea de compra repartida entre dos Objetos, y otra que queda sin Objeto.
        linea = conn.execute("SELECT l.id, l.rev, l.importe_cent FROM factura_linea AS l "
                             "JOIN factura AS f ON f.id = l.factura_id WHERE f.numero = "
                             "'B-2026-077' AND l.retirada_en IS NULL ORDER BY l.id"
                             ).fetchone()
        if linea is not None and linea[2] and linea[2] > 100:
            mitad = linea[2] // 2
            _orden(conn, "dividir_linea", {
                "linea_id": linea[0], "rev": linea[1], "motivo": MOTIVO,
                "partes": [{"objeto_id": _objeto(conn, "Rijnhaven"),
                            "importe": f"{mitad / 100:.2f}"},
                           {"objeto_id": _objeto(conn, "Schiedam"),
                            "importe": f"{(linea[2] - mitad) / 100:.2f}"}]})
    if azar.random() < 0.6:
        imputacion = conn.execute(
            "SELECT i.id, i.rev FROM factura_imputacion AS i JOIN factura AS f "
            "ON f.id = i.factura_id WHERE f.numero = 'V2026-0102' AND i.retirada_en IS NULL"
        ).fetchone()
        _orden(conn, "cambiar_objeto", {"imputacion_id": imputacion[0],
                                        "rev": imputacion[1], "motivo": MOTIVO})


@pytest.mark.parametrize("semilla", range(5))
def test_lo_pendiente_de_cada_parte_es_lo_que_encuentra_la_busqueda(escenario, semilla) -> None:
    """Propiedad (puerta del paso 12): lo pendiente de cada proveedor y cada cliente en su vista
    es la suma de lo pendiente de sus facturas pendientes tal como las encuentra la busqueda,
    y lo que entra y sale en el panel es lo pendiente de todas, por su direccion."""
    conn = escenario.conn
    _escenario_al_azar(escenario, semilla)
    for tabla, filtro, de_todas in (("proveedor", "proveedor_id", consultas.proveedores),
                                    ("cliente", "cliente_id", consultas.clientes)):
        for resumen in de_todas(conn):
            vista = getattr(consultas, tabla)(conn, resumen["id"])
            busqueda = consultas.buscar(conn, {filtro: str(resumen["id"]), "pendiente": "si",
                                               "sentido": "entrante" if tabla == "proveedor"
                                               else "saliente", "limite": "1000"})
            filas = busqueda["facturas"]
            assert vista["pendiente_cent"] == busqueda["suma"]["pendiente_cent"] == sum(
                f["pendiente_cent"] or 0 for f in filas) == resumen["pendiente_cent"], (
                tabla, resumen["id"])
            assert vista["vencido_cent"] == sum(f["pendiente_cent"] or 0 for f in filas
                                                if f["estado_pago"] == "vencida")
            assert {f["id"] for f in vista["abiertas_detalle"]} == {
                f["id"] for f in filas if f["pendiente_cent"] is not None}
    panel = consultas.panel(conn)
    por_direccion = {flujo_caja.ENTRADA: 0, flujo_caja.SALIDA: 0}
    for f in consultas.buscar(conn, {"pendiente": "si", "limite": "1000"})["facturas"]:
        if f["pendiente_cent"]:
            por_direccion[flujo_caja.direccion(f["sentido"], f["pendiente_cent"])] += abs(
                f["pendiente_cent"])
    assert panel["dinero_entra"]["pendiente_cent"] == por_direccion[flujo_caja.ENTRADA]
    assert panel["dinero_sale"]["pendiente_cent"] == por_direccion[flujo_caja.SALIDA]
    vencidas = consultas.buscar(conn, {"vencida": "si", "sentido": "entrante",
                                       "limite": "1000"})
    assert panel["atencion"]["compras_vencidas"]["pendiente_cent"] == vencidas["suma"][
        "pendiente_cent"]
    assert panel["atencion"]["compras_vencidas"]["facturas"] == vencidas["total"]


def _base_total(conn, sentido: str) -> int:
    """La base de las facturas de un sentido que cuentan, sacada de las facturas y de lo que
    mueven las relaciones, sin pasar por ninguna vista."""
    movido = relaciones.efectos(conn)
    total = 0
    for id_, base, anulada, fusionada in conn.execute(
            "SELECT id, base_cent, anulada, fusionada_en_id FROM factura WHERE sentido = ?",
            (sentido,)):
        if anulada or fusionada is not None or base is None:
            continue
        if relaciones.efecto_de(movido, id_).sustituida_por is not None:
            continue
        total += base
    return total


@pytest.mark.parametrize("semilla", range(5))
def test_lo_de_cada_objeto_mas_lo_sin_objeto_es_la_base_total(escenario, semilla) -> None:
    """Propiedad (puerta del paso 12): los ingresos de cada Objeto (su vista) mas lo facturado
    sin Objeto es la base de todas las ventas que cuentan; y los costes de cada Objeto mas lo
    comprado sin Objeto, la de todas las compras. Cada Objeto suma lo mismo por meses y por
    semanas que de siempre."""
    conn = escenario.conn
    _escenario_al_azar(escenario, semilla)
    resumen = consultas.objetos_resumen(conn)
    ingresos = costes = 0
    for fila in resumen["objetos"]:
        vista = consultas.objeto(conn, fila["id"])
        siempre = vista["economia"]["siempre"]
        assert siempre == fila["siempre"]
        assert sum(m["ingresos_cent"] for m in vista["economia"]["por_mes"]) == siempre[
            "ingresos_cent"]
        assert sum(m["costes_cent"] for m in vista["economia"]["por_mes"]) == siempre[
            "costes_cent"]
        assert sum(s["ingresos_cent"] for s in vista["economia"]["por_semana"]) == siempre[
            "ingresos_cent"]
        assert sum(s["costes_cent"] for s in vista["economia"]["por_semana"]) == siempre[
            "costes_cent"]
        ingresos += siempre["ingresos_cent"]
        costes += siempre["costes_cent"]
    sin_objeto = resumen["sin_objeto"]["total"]
    assert ingresos + sin_objeto["ingresos_cent"] == _base_total(conn, "saliente") == resumen[
        "totales"]["ingresos_cent"]
    assert costes + sin_objeto["costes_cent"] == _base_total(conn, "entrante") == resumen[
        "totales"]["costes_cent"]


def test_lo_sin_objeto_dice_de_donde_sale(escenario) -> None:
    """Una venta imputada sin Objeto va a "imputado"; una con la base sin repartir entre
    lineas (aqui, la factura en dolares no cuenta: sin base) no suma en ningun sitio."""
    conn = escenario.conn
    imputacion = conn.execute(
        "SELECT i.id, i.rev, i.importe_cent FROM factura_imputacion AS i JOIN factura AS f "
        "ON f.id = i.factura_id WHERE f.numero = 'V2026-0102' AND i.retirada_en IS NULL"
    ).fetchone()
    antes = consultas.objetos_resumen(conn)
    _orden(conn, "cambiar_objeto", {"imputacion_id": imputacion[0],
                                    "rev": imputacion[1], "motivo": MOTIVO})
    despues = consultas.objetos_resumen(conn)
    assert despues["sin_objeto"]["imputado"]["ingresos_cent"] == antes["sin_objeto"][
        "imputado"]["ingresos_cent"] + imputacion[2]
    schiedam = {o["codigo"]: o for o in despues["objetos"]}["Schiedam"]
    assert schiedam["siempre"]["ingresos_cent"] == {o["codigo"]: o for o in antes[
        "objetos"]}["Schiedam"]["siempre"]["ingresos_cent"] - imputacion[2]
    assert despues["totales"]["sin_base"] >= 1


# ============================================================ el panel principal (§17)

def test_el_panel_tiene_los_siete_bloques_del_paragrafo_17(escenario) -> None:
    conn = escenario.conn
    p = consultas.panel(conn)
    for bloque in ("dinero_entra", "dinero_sale", "caja", "facturacion", "ordenes_compra",
                   "btw", "atencion"):
        assert bloque in p, bloque
    assert p["hoy"] == "2026-10-20" and p["al_dia"]
    caja = p["caja"]["ventanas"]
    for ventana in ("vencido", "semana", "mes", "proximos_30", "total"):
        assert caja[ventana]["neto_cent"] == caja[ventana]["entrada_cent"] - caja[ventana][
            "salida_cent"]
    assert caja["total"]["entrada_cent"] == p["dinero_entra"]["pendiente_cent"]
    assert caja["total"]["salida_cent"] == p["dinero_sale"]["pendiente_cent"]
    # Sin planning, la facturacion dice que no lo sabe: nunca cero.
    assert p["facturacion"]["estado"] == "sin_datos" and "planning" in p["facturacion"]["detalle"]
    assert p["caja"]["estimado"]["importe_cent"] is None
    # La PO activa con lo consumido de su vista.
    [po] = consultas.ordenes_compra(conn)
    assert p["ordenes_compra"]["activas"] == 1
    assert (p["ordenes_compra"]["valor_cent"], p["ordenes_compra"]["consumido_cent"]) == (
        po["valor_cent"], po["consumido_cent"])
    # El BTW: el trimestre en curso y el proximo plazo que no ha pasado (el del tercero).
    assert p["btw"]["trimestre"] == "2026-T4"
    assert p["btw"]["proximo_plazo"]["trimestre"] == "2026-T3"
    assert p["btw"]["proximo_plazo"]["limite_presentacion"] == "2026-10-31"


def test_cada_aviso_pendiente_va_a_una_sola_categoria(escenario) -> None:
    """Las categorias de "atencion" reparten los hallazgos pendientes sin contar ninguno dos
    veces ni dejarse ninguno; los aceptados se cuentan aparte."""
    conn = escenario.conn
    p = consultas.panel(conn)["atencion"]
    pendientes = conn.execute("SELECT estado, count(*) FROM hallazgo WHERE estado IN "
                              "('abierto', 'desaparecido', 'aceptado') GROUP BY estado")
    por_estado = dict(pendientes.fetchall())
    assert p["hallazgos"] == por_estado.get("abierto", 0) + por_estado.get("desaparecido", 0)
    assert p["aceptados"] == por_estado.get("aceptado", 0)
    assert sum(c["activos"] for c in p["categorias"]) == p["hallazgos"]
    from bms_agent.reglas import catalogo

    claves = {c["clave"] for c in p["categorias"]}
    for regla in catalogo.CATALOGO:
        assert consultas.categoria_de(regla.id) in claves
    assert consultas.categoria_de("F3") == "iban" and consultas.categoria_de("B2") == "duplicados"
    assert consultas.categoria_de("P4") == "ordenes_compra" and consultas.categoria_de("E0") == "iva"
    assert consultas.categoria_de("G2") == "planning" and consultas.categoria_de("V6") == \
        "sin_facturar"
    assert consultas.categoria_de("Q2") == "lecturas_dudosas"
    # Lo vencido: las compras de mediados de octubre, con sus dias.
    vencidas = {f["numero"]: f["dias"] for f in p["compras_vencidas"]["lista"]}
    assert vencidas["2026-0912"] == 6 and p["compras_vencidas"]["sin_importe"] == 1
    assert p["excepciones"]["abiertas"] >= 1


def test_el_panel_dice_el_trabajo_sin_facturar_del_planning(maestros, tmp_path) -> None:
    """Con planning, la facturacion cuenta lo que dicen los V6 abiertos: lo mismo que la vista
    de cada cliente."""
    conn = maestros.conn
    ruta = _cambiado(tmp_path, *((f"{d}-10-2026", f"{d - 7:02d}-08-2026")
                                 for d in (12, 13, 17, 18, 19, 20)))
    _planning(maestros, ruta)
    p = consultas.panel(conn)["facturacion"]
    assert p["estado"] == "ok"
    haven = _cliente(conn, "10001")
    vista = consultas.cliente(conn, haven)["trabajo_sin_facturar"]
    assert p["sin_facturar"]["valor_cent"] == vista["valor_cent"] > 0
    assert p["sin_facturar"]["horas_mil"] == vista["horas_mil"]
    assert p["sin_facturar"]["clientes"] == [haven]
    assert consultas.panel(conn)["caja"]["estimado"]["importe_cent"] is not None


# ============================================================ procedencia, ediciones e historia

def test_cada_campo_dice_su_fuente_y_quien_lo_cambio_y_por_que(escenario) -> None:
    """§11 y §13: la ficha da de cada campo la etiqueta de su fuente (las siete), la
    referencia de esa fuente y, si lo cambio una persona, quien, cuando y su motivo."""
    conn = escenario.conn
    ficha = consultas.detalle(conn, factura_de(conn, "2026-0912"))
    campos_ = {c["campo"]: c for c in ficha["campos"]}
    nombre = campos_["emisor_nombre_doc"]
    assert (nombre["fuente"], nombre["fuente_texto"]) == ("manual_correccion", "Corregido a mano")
    assert nombre["corregido"] and nombre["sin_resolver"]
    assert nombre["motivo"] == "El nombre del maestro" and nombre["cambiado_por"] == "Ana"
    assert nombre["original_crudo"] is not None and nombre["original"] != nombre["valor"]
    numero = campos_["numero"]
    assert numero["fuente_texto"] == "Extraído del documento" and numero["motivo"] is None
    assert numero["fuente_ref"].startswith("extraccion:")
    assert set(consultas.ETIQUETA_FUENTE) == {"extraccion", "importacion", "planning", "maestro",
                                              "manual_entrada", "manual_correccion", "calculado"}
    venta = consultas.detalle(conn, factura_de(conn, "V2026-0101"))
    assert {c["fuente_texto"] for c in venta["campos"] if c["valor"] is not None} >= {
        "Importado de otro sistema"}


def test_la_historia_de_una_factura(escenario) -> None:
    """§12: el original, cada cambio con quien, cuando, la fuente y el motivo, las revisiones
    y la historia de cada aviso."""
    conn = escenario.conn
    f = factura_de(conn, "2026-0912")
    h = consultas.historial_factura(conn, f)
    # Las fixtures se importan sin su PDF: el original no esta en el almacen (Q4), y se dice.
    assert h["documento"]["conservado"] is False and len(h["documento"]["sha256"]) == 64
    assert [e["vigente"] for e in h["extracciones"]] == [True]
    [cambio] = [c for e in h["eventos"] if e["persona"] for c in e["cambios"]
                if c["campo"] == "emisor_nombre_doc"]
    assert cambio["nuevo_texto"] == "De Vries Montage" and cambio["anterior_texto"]
    assert (cambio["fuente_anterior"], cambio["fuente_nueva"]) == ("extraccion",
                                                                   "manual_correccion")
    assert cambio["motivo"] == "El nombre del maestro"
    [evento] = [e for e in h["eventos"] if any(c is cambio for c in e["cambios"])]
    assert evento["usuario"] == "Ana" and evento["en"]
    # Los eventos van en orden y el primero es el de la extraccion, con sus valores.
    ids = [e["id"] for e in h["eventos"]]
    assert ids == sorted(ids) and not h["eventos"][0]["persona"]
    assert h["hallazgos"] and all(x["eventos"][0]["tipo"] == "detectado" for x in h["hallazgos"])
    devuelta = consultas.historial_factura(conn, factura_de(conn, "B-2026-077"))
    assert [(r["resultado"], r["usuario"]) for r in devuelta["revisiones"]] == [
        ("devuelta", "Ana")]
    anulada = consultas.historial_factura(conn, factura_de(conn, "2026-112"))
    assert any(e["motivo"] == "Factura emitida por error, la retira el proveedor"
               for e in anulada["eventos"])
    # Una venta de Exact no tiene documento: llego de otro sistema.
    assert consultas.historial_factura(conn, factura_de(conn, "V2026-0101"))["documento"] is None
    with pytest.raises(LookupError):
        consultas.historial_factura(conn, 99999)


def test_la_vista_del_objeto_tiene_sus_ingresos_costes_y_facturas(escenario) -> None:
    """§5: ingresos, costes y margen del periodo, del ano y de siempre; por mes y semana; y
    sus facturas de compra y de venta."""
    conn = escenario.conn
    rijnhaven = _objeto(conn, "Rijnhaven")
    v = consultas.objeto(conn, rijnhaven)
    e = v["economia"]
    assert e["periodo"]["desde"] == "2026-10-01" and e["periodo"]["hasta"] == "2026-10-20"
    # La venta de octubre (2.480,00) menos su abono (248,00): 2.232,00 en el mes.
    assert e["periodo"]["ingresos_cent"] == e["ano"]["ingresos_cent"] == 223200
    assert e["siempre"]["margen_cent"] == e["siempre"]["ingresos_cent"] - e["siempre"][
        "costes_cent"]
    assert {m["mes"] for m in e["por_mes"]} >= {"2026-09", "2026-10"}
    ventas = {f["numero"] for f in v["facturas"]["salientes"]}
    assert ventas == {"V2026-0101", "C2026-0005"}
    assert all(f["importe_objeto_cent"] for f in v["facturas"]["entrantes"])
    septiembre = consultas.objeto(conn, rijnhaven, desde=date(2026, 9, 1),
                                  hasta=date(2026, 9, 30))["economia"]["periodo"]
    assert septiembre["ingresos_cent"] == 0 and septiembre["costes_cent"] > 0
    with pytest.raises(ValueError):
        consultas.objeto(conn, rijnhaven, desde=date(2026, 10, 2), hasta=date(2026, 10, 1))


def test_la_tabla_de_validacion_facturas_es_la_del_catalogo() -> None:
    """La tabla del apartado 6 de docs/validacion-facturas.md sale del catalogo: si alguien
    cambia una regla sin regenerarla, este test lo dice."""
    import importlib.util
    from pathlib import Path

    from bms_agent.reglas import catalogo

    ruta = Path(__file__).resolve().parent.parent / "scripts" / "generar_catalogo_doc.py"
    spec = importlib.util.spec_from_file_location("catalogo_doc", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    texto = modulo.DOCUMENTO.read_text(encoding="utf-8")
    assert modulo.documento_con_tabla(texto) == texto
    for regla in catalogo.CATALOGO:
        assert f"| {regla.id} | **" in texto
    assert modulo.main(["--comprobar"]) == 0
