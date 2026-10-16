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
    # Suplementada: un campo que el documento no traia, puesto a mano (manual_entrada).
    f = factura_de(conn, "2026-018")
    assert conn.execute("SELECT fecha_vencimiento FROM factura WHERE id = ?",
                        (f,)).fetchone()[0] is None
    _orden(conn, "fijar_campo", {"tabla": "factura", "fila_id": f, "campo": "fecha_vencimiento",
                                 "valor": "2026-11-30", "motivo": "Lo dice el contrato",
                                 "rev": _rev(conn, f)})
    suplementada = _estado(conn, "suplementada")
    assert suplementada[f]
    _comprobar(conn, {"edicion": "suplementada"}, {i for i, c in suplementada.items() if c})
    sin_resolver = _estado(conn, "sin_resolver")
    assert sin_resolver[factura_de(conn, "2026-0912")]
    _comprobar(conn, {"edicion": "sin_resolver"}, {i for i, c in sin_resolver.items() if c})
    _comprobar(conn, {"edicion": "suplementada,corregida"},
               {i for i in suplementada if suplementada[i] or corregida[i]})


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
    # Siempre, con importes al azar: una compra que siempre cuenta (2026-018, pagada) con
    # su linea sin Objeto y una base que ya no es la suma de sus lineas. Asi lo imputado sin
    # Objeto y lo que la base no reparte (desviacion 6) tienen costes en cada semilla.
    f = factura_de(conn, "2026-018")
    imputacion = conn.execute("SELECT id, rev FROM factura_imputacion WHERE factura_id = ? "
                              "AND retirada_en IS NULL", (f,)).fetchone()
    _orden(conn, "cambiar_objeto", {"imputacion_id": imputacion[0], "rev": imputacion[1],
                                    "motivo": MOTIVO})
    base = conn.execute("SELECT base_cent FROM factura WHERE id = ?", (f,)).fetchone()[0]
    nueva = base + azar.choice([-1, 1]) * azar.randint(100, 50000)
    _orden(conn, "fijar_campo", {"tabla": "factura", "fila_id": f, "campo": "base_cent",
                                 "valor": f"{nueva / 100:.2f}", "motivo": MOTIVO,
                                 "rev": _rev(conn, f)})


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
    # Lo sin Objeto tiene de las dos cosas, y de costes en cada semilla.
    imputado, sin_imputar = resumen["sin_objeto"]["imputado"], resumen["sin_objeto"]["sin_imputar"]
    assert imputado["costes_cent"] != 0 and sin_imputar["costes_cent"] != 0
    assert sin_objeto["costes_cent"] == imputado["costes_cent"] + sin_imputar["costes_cent"]
    assert sin_objeto["ingresos_cent"] == imputado["ingresos_cent"] + sin_imputar[
        "ingresos_cent"]
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
    assert p["ordenes_compra"]["activas"] == p["ordenes_compra"]["cliente"]["activas"] == 1
    assert (p["ordenes_compra"]["cliente"]["valor_cent"],
            p["ordenes_compra"]["cliente"]["consumido_cent"]) == (po["valor_cent"],
                                                                  po["consumido_cent"])
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


# ============================================================ revision del paso 12

def test_la_suma_de_la_busqueda_es_la_de_la_vista_de_la_parte(escenario) -> None:
    """Solo suman las facturas que cuentan: la anulada 2026-112 sale en la busqueda de su
    proveedor, pero no suma (como en su vista), y se dice que no cuenta. Compras y ventas no
    se suman entre si."""
    conn = escenario.conn
    for resumen in consultas.proveedores(conn):
        vista = consultas.proveedor(conn, resumen["id"])["siempre_facturado"]
        suma = consultas.buscar(conn, {"proveedor_id": str(resumen["id"])})["suma"]
        assert (suma["total_cent"], suma["base_cent"], suma["cuentan"]) == (
            vista["total_cent"], vista["base_cent"], vista["facturas"]), resumen["id"]
    for resumen in consultas.clientes(conn):
        vista = consultas.cliente(conn, resumen["id"])["siempre_facturado"]
        suma = consultas.buscar(conn, {"cliente_id": str(resumen["id"]),
                                       "sentido": "saliente"})["suma"]
        assert (suma["total_cent"], suma["base_cent"]) == (vista["total_cent"],
                                                           vista["base_cent"])
    anulada = factura_de(conn, "2026-112")
    proveedor = conn.execute("SELECT proveedor_id FROM factura WHERE id = ?",
                             (anulada,)).fetchone()[0]
    r = consultas.buscar(conn, {"proveedor_id": str(proveedor)})
    assert [f["id"] for f in r["facturas"]] == [anulada]
    assert r["suma"]["total_cent"] == 0 and (r["suma"]["cuentan"], r["suma"]["no_cuentan"]) == (
        0, 1)
    # Sin sentido, lo de las compras y lo de las ventas va por separado y arriba no hay suma.
    todo = consultas.buscar(conn, {"limite": "1000"})["suma"]
    assert todo["mezcla"] and todo["total_cent"] is None and todo["pendiente_cent"] is None
    compras_ = consultas.buscar(conn, {"sentido": "entrante"})["suma"]
    assert not compras_["mezcla"] and todo["compras"] == compras_["compras"]
    assert compras_["pendiente_cent"] == compras_["compras"]["pendiente_cent"]
    assert todo["ventas"]["pendiente_cent"] == consultas.buscar(
        conn, {"sentido": "saliente"})["suma"]["pendiente_cent"]


def test_una_copia_fusionada_no_suma_dos_veces(escenario) -> None:
    conn = escenario.conn
    van_dijk = conn.execute("SELECT proveedor_id FROM factura WHERE numero = '2026-4471'"
                            ).fetchone()[0]
    antes = consultas.buscar(conn, {"proveedor_id": str(van_dijk)})["suma"]
    copia = _sustituta(escenario, citar=False)
    _orden(conn, "fusionar_factura", {"factura_id": copia,
                                      "destino_id": factura_de(conn, "2026-4471"),
                                      "rev": _rev(conn, copia), "motivo": MOTIVO})
    despues = consultas.buscar(conn, {"proveedor_id": str(van_dijk)})
    assert copia in {f["id"] for f in despues["facturas"]}
    assert despues["suma"]["total_cent"] == antes["total_cent"]
    assert despues["suma"]["no_cuentan"] == antes["no_cuentan"] + 1
    assert despues["suma"]["total_cent"] == consultas.proveedor(conn, van_dijk)[
        "siempre_facturado"]["total_cent"]


def test_el_texto_se_busca_sin_mayusculas_tambien_fuera_del_ascii(escenario) -> None:
    """lower() de SQLite solo pliega ASCII: "ÖZTÜRK" no se encontraba ni escrito igual."""
    conn = escenario.conn
    f = factura_de(conn, "2026-018")
    _orden(conn, "fijar_campo", {"tabla": "factura", "fila_id": f, "campo": "emisor_nombre_doc",
                                 "valor": "ÖZTÜRK Élan Bouw", "motivo": "Como en el maestro",
                                 "rev": _rev(conn, f)})
    for buscado in ("Öztürk", "öztürk", "ÖZTÜRK", "élan", "ÉLAN BOUW", "rk élan"):
        assert _ids(conn, {"texto": buscado}) == {f}, buscado
    assert _ids(conn, {"texto": "oztürk"}) == set()


@pytest.mark.parametrize("peticion", [
    {"proveedor_id": "99999999999999999999"}, {"objeto_id": "9223372036854775808"},
    {"limite": "1" + "0" * 30},
])
def test_un_entero_demasiado_grande_es_un_filtro_no_valido(escenario, peticion) -> None:
    with pytest.raises(consultas.FiltroNoValido, match="demasiado grande"):
        consultas.buscar(escenario.conn, peticion)


def test_la_busqueda_admite_valores_que_no_son_texto(escenario) -> None:
    conn = escenario.conn
    van_dijk = conn.execute("SELECT proveedor_id FROM factura WHERE numero = '2026-4471'"
                            ).fetchone()[0]
    assert _ids(conn, {"proveedor_id": van_dijk}) == _ids(conn, {"proveedor_id": str(van_dijk)})
    assert consultas.buscar(conn, {"limite": 5})["limite"] == 5


def test_el_filtro_de_periodo_encuentra_una_factura_que_solo_imprime_la_semana(escenario) -> None:
    """Sin periodo en la cabecera, la factura de horas "semana 37" (sin fechas por linea) es de
    la semana 37: la misma cuenta que la economia por semana del Objeto (turnos.dias_de)."""
    conn = escenario.conn
    f = factura_de(conn, "2026-0912")
    assert conn.execute("SELECT count(*) FROM factura_linea WHERE factura_id = ? AND "
                        "semana_doc = 37 AND fecha_inicio IS NULL AND fecha_trabajo IS NULL",
                        (f,)).fetchone()[0] == 1
    for campo in ("periodo_inicio", "periodo_fin"):
        _orden(conn, "fijar_campo", {"tabla": "factura", "fila_id": f, "campo": campo,
                                     "valor": None, "motivo": "No lo imprime",
                                     "rev": _rev(conn, f)})
    assert conn.execute("SELECT periodo_inicio, periodo_fin FROM factura WHERE id = ?",
                        (f,)).fetchone()[:] == (None, None)
    [fila] = [x for x in _todas(conn) if x["id"] == f]
    assert (fila["periodo_desde"], fila["periodo_hasta"]) == ("2026-09-07", "2026-09-13")
    assert f in _ids(conn, {"periodo_desde": "2026-09-07", "periodo_hasta": "2026-09-13"})
    assert f not in _ids(conn, {"periodo_desde": "2026-09-14"})
    schiedam = consultas.objeto(conn, _objeto(conn, "Schiedam"))["economia"]["por_semana"]
    assert any(s["semana"] == "2026-W37" and s["costes_cent"] for s in schiedam)


def test_el_periodo_de_la_cache_es_el_de_turnos(escenario) -> None:
    """estados.periodos usa la misma cuenta que las horas: la semana impresa toma el ano de la
    fecha de la factura (la semana 52 de una factura de enero es la del ano anterior)."""
    from bms_agent import estados

    conn = escenario.conn
    f = factura_de(conn, "2026-0912")
    linea = conn.execute("SELECT id, rev FROM factura_linea WHERE factura_id = ?",
                         (f,)).fetchone()
    for tabla, fila_id, campo, valor in (
            ("factura", f, "periodo_inicio", None), ("factura", f, "periodo_fin", None),
            ("factura", f, "fecha_factura", "2027-01-06"),
            ("factura_linea", linea["id"], "semana_doc", "52")):
        rev = conn.execute(f"SELECT rev FROM {tabla} WHERE id = ?", (fila_id,)).fetchone()[0]
        _orden(conn, "fijar_campo", {"tabla": tabla, "fila_id": fila_id, "campo": campo,
                                     "valor": valor, "motivo": "Lo que imprime",
                                     "rev": rev})
    assert estados.periodos(conn)[f] == ("2026-12-21", "2026-12-27")
    assert f in _ids(conn, {"periodo_hasta": "2026-12-21", "periodo_desde": "2026-12-27"})


def test_la_vista_del_objeto_no_admite_medio_periodo(escenario) -> None:
    """Un solo extremo no es un periodo (antes se rellenaba con el mes en curso y daba un
    periodo al reves): los dos o ninguno, como el flujo de caja."""
    conn = escenario.conn
    rijnhaven = _objeto(conn, "Rijnhaven")
    for extremos in ({"hasta": date(2026, 9, 30)}, {"desde": date(2026, 11, 1)},
                     {"desde": date(2026, 9, 1)}):
        with pytest.raises(ValueError, match="desde y hasta"):
            consultas.objeto(conn, rijnhaven, **extremos)
    periodo = consultas.objeto(conn, rijnhaven, desde=date(2026, 9, 1),
                               hasta=date(2026, 9, 30))["economia"]["periodo"]
    assert (periodo["desde"], periodo["hasta"]) == ("2026-09-01", "2026-09-30")


def _po_de_proveedor(conn, numero: str, valor: str, fin: str | None = None) -> int:
    proveedor = conn.execute("SELECT proveedor_id FROM factura WHERE numero = '2026-018'"
                             ).fetchone()[0]
    datos = {"numero": numero, "lado": "proveedor", "parte_id": proveedor, "valor": valor,
             "motivo": MOTIVO}
    if fin:
        datos["fecha_fin"] = fin
    _orden(conn, "registrar_po", datos)
    return conn.execute("SELECT id FROM orden_compra WHERE numero = ?", (numero,)).fetchone()[0]


def test_el_bloque_de_po_no_suma_los_dos_lados(escenario) -> None:
    """Una PO de cliente (lo que BMS puede facturar) y una de proveedor (lo que le pueden
    facturar) van cada una en su lado, como en la vista del Objeto."""
    conn = escenario.conn
    _po_de_proveedor(conn, "BMS-PO-9", "5000")
    p = consultas.panel(conn)["ordenes_compra"]
    lista = consultas.ordenes_compra(conn)
    for lado in ("cliente", "proveedor"):
        suyas = [o for o in lista if o["lado"] == lado]
        assert p[lado]["activas"] == len(suyas) == 1
        assert p[lado]["valor_cent"] == sum(o["valor_cent"] for o in suyas)
        assert p[lado]["consumido_cent"] == sum(o["consumido_cent"] for o in suyas)
        assert p[lado]["restante_cent"] == p[lado]["valor_cent"] - p[lado]["consumido_cent"]
    assert (p["cliente"]["valor_cent"], p["proveedor"]["valor_cent"]) == (1000000, 500000)
    assert p["activas"] == 2 and "valor_cent" not in p
    assert consultas.comprobar_v2({**consultas.exportar_v2(conn)}) == []


def test_las_listas_de_po_del_panel(escenario, reloj) -> None:
    """Cerca del limite (P5), cerca de caducar (P7 de una PO activa) y caducadas (P7 que sigue
    pendiente despues del fin): una PO que ya caduco no esta "cerca de caducar"."""
    conn = escenario.conn
    haven = conn.execute("SELECT id FROM orden_compra WHERE numero = 'PO-4500123'"
                         ).fetchone()[0]
    _orden(conn, "modificar_po", {"orden_compra_id": haven, "valor": "4500", "motivo": MOTIVO})
    nueve = _po_de_proveedor(conn, "BMS-PO-9", "5000", fin="2026-10-30")
    p = consultas.panel(conn)["ordenes_compra"]
    assert [o["id"] for o in p["cerca_del_limite"]] == [haven]
    assert [(o["id"], o["lado"]) for o in p["cerca_de_caducar"]] == [(nueve, "proveedor")]
    assert p["caducadas"] == []
    reloj.avanzar(days=20)
    hallazgos.recalcular(conn, motivo="diaria")
    assert conn.execute("SELECT estado FROM hallazgo WHERE regla = 'P7' AND fila_id = ?",
                        (nueve,)).fetchone()[0] == "abierto"
    p = consultas.panel(conn)["ordenes_compra"]
    assert p["proveedor"]["activas"] == 0 and p["cerca_de_caducar"] == []
    assert [(o["id"], o["fecha_fin"]) for o in p["caducadas"]] == [(nueve, "2026-10-30")]


def test_la_historia_de_una_factura_abonada_dice_quien_la_abono(escenario) -> None:
    """La relacion se escribe con el abono (origen): la factura abonada tambien la tiene en su
    historia, con su evento y la relacion en los dos sentidos."""
    conn = escenario.conn
    abono, venta = factura_de(conn, "C2026-0005"), factura_de(conn, "V2026-0101")
    h = consultas.historial_factura(conn, venta)
    assert "relacion_confirmada" in [e["tipo"] for e in h["eventos"]]
    [relacion] = [r for r in h["relaciones"] if r["estado"] == "confirmada"]
    assert (relacion["papel"], relacion["tipo"], relacion["otra_id"],
            relacion["otra_numero"]) == ("destino", "acredita", abono, "C2026-0005")
    del_abono = consultas.historial_factura(conn, abono)
    assert [r["papel"] for r in del_abono["relaciones"] if r["estado"] == "confirmada"] == [
        "origen"]
    confirmada = [e for e in h["eventos"] if e["tipo"] == "relacion_confirmada"][0]
    assert any(c["tabla"] == "factura_relacion" for c in confirmada["cambios"])
    # Una factura sin relaciones no gana eventos ajenos.
    ajena = consultas.historial_factura(conn, factura_de(conn, "2026-018"))
    assert ajena["relaciones"] == [] and "relacion_confirmada" not in [
        e["tipo"] for e in ajena["eventos"]]


def test_el_panel_dice_las_horas_validadas_que_no_estan_en_su_venta(maestros, tmp_path) -> None:
    """V5 (§7 "Missing billable hours", §8 "Missing billing"): una venta de la semana 42 cuya
    unica linea es del dia 14 deja fuera los dos turnos del dia 12."""
    from test_planning import _importar_venta, _venta

    conn = maestros.conn
    _planning(maestros)
    ruta = _venta(tmp_path, horas="8")
    texto = ruta.read_bytes().decode("utf-8")
    # La cabecera cobra la semana; la linea, solo el dia 14.
    antes, despues = texto.rsplit("12-10-2026;18-10-2026", 1)
    ruta.write_bytes((antes + "14-10-2026;14-10-2026" + despues).encode("utf-8"))
    _importar_venta(maestros, ruta)
    [v5] = conn.execute("SELECT id, fila_id FROM hallazgo WHERE regla = 'V5' "
                        "AND estado = 'abierto'").fetchall()
    [horas] = consultas.panel(conn)["facturacion"]["horas_sin_facturar"]
    assert (horas["hallazgo_id"], horas["factura_id"]) == (v5["id"], v5["fila_id"])
    assert (horas["objeto_id"], horas["desde"], horas["hasta"], horas["horas_mil"]) == (
        _objeto(conn, "Rijnhaven"), "2026-10-12", "2026-10-18", 15000)
    assert horas["valor_cent"] and horas["estimado"]
    assert consultas.categoria_de("V5") == "sin_facturar"
