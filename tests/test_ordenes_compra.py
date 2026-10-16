"""Ordenes de compra y tarifas pactadas en el almacen (paso 9).

Puertas del paso 9 que viven aqui, sobre el almacen entero (importar,
casar, evaluar y las caches):

- la aritmetica del consumo: sin IVA, los abonos confirmados restan, las
  facturas anuladas y las sustituidas no cuentan (y la vista SQL, la cuenta
  de las reglas y la de ordenes_compra dicen lo mismo);
- P4 sigue el orden del §7 (fecha de factura y id);
- los umbrales salen de la configuracion (config/reglas.yaml cargado);
- la caducidad se prueba con una fecha fija, y la prevision es determinista;
- que referencia es una PO lo decide el codigo casando con la lista de PO;
- la hoja de PO (CSV o YAML) pide cambiar_po, y una modificacion es su
  propia fila, de solo escritura.

Las reglas puras (P1-P10, G3/G6/V4 contra lo pactado) se prueban sobre
instantaneas en test_reglas_ordenes.py.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest
from conftest import RAIZ, cuentas_propias, factura_de, persona

from bms_agent import campos, consultas, hallazgos, ordenes_compra, servicios
from bms_agent.importadores.registrar import importar_fichero
from bms_agent.permisos import PermisoDenegado
from bms_agent.reglas import instantanea as instantaneas
from bms_agent.reglas import ordenes as reglas_ordenes

IMPORTACION = RAIZ / "tests" / "fixtures" / "importacion"
EXACT_CLIENTES = IMPORTACION / "exact-clientes-v1.csv"
EXACT_PROVEEDORES = IMPORTACION / "exact-proveedores-v1.csv"
OBJETOS = IMPORTACION / "maestro_csv-objetos-v1.csv"
VENTAS = IMPORTACION / "exact-facturas_venta-v1.csv"
PO_CSV = IMPORTACION / "po_csv-ordenes_compra-v1.csv"
MODIFICACIONES_CSV = IMPORTACION / "po_csv-modificaciones_po-v1.csv"
PO_YAML = IMPORTACION / "po_csv-yaml.yaml"
MOTIVO = "Visto con la PO del cliente delante"


# ------------------------------------------------------------ constructores

def _limpio(conn) -> None:
    assert campos.verificar_controladas(conn) == []
    assert hallazgos.verificar(conn) == []


@pytest.fixture
def ventas(almacen):
    """Clientes, proveedores y Objetos del maestro y el listado de ventas de Exact (V2026-0101
    con PO-4500123 impresa y su abono C2026-0005). Ana lo puede todo."""
    conn = almacen.conn
    ana = persona(conn, "Ana", "administrador")
    cuentas_propias(almacen, ana)
    importar_fichero(almacen, "exact", "clientes", EXACT_CLIENTES, lanzado_por=ana)
    importar_fichero(almacen, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana)
    importar_fichero(almacen, "maestro_csv", "objetos", OBJETOS, lanzado_por=ana)
    importar_fichero(almacen, "exact", "facturas_venta", VENTAS, lanzado_por=ana)
    return almacen


def _ana(conn) -> int:
    return conn.execute("SELECT id FROM usuario WHERE nombre = 'Ana'").fetchone()[0]


def _orden(conn, nombre: str, datos: dict, usuario: int | None = None) -> servicios.Diferencia:
    return servicios.ejecutar(conn, nombre, datos, usuario_id=usuario or _ana(conn))


def _po(conn, numero: str) -> int:
    from bms_agent.parsing import normalizar_referencia

    return conn.execute("SELECT id FROM orden_compra WHERE numero_norm = ?",
                        (normalizar_referencia(numero),)).fetchone()[0]


def _con_pos(almacen) -> int:
    resultado = importar_fichero(almacen, "po_csv", "ordenes_compra", PO_CSV,
                                 lanzado_por=_ana(almacen.conn))
    assert [lote.estado for lote in resultado.lotes] == ["parcial"]
    return _po(almacen.conn, "PO-4500123")


def _hallazgos(conn, regla: str, *, tabla: str | None = None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM hallazgo WHERE regla = ? AND estado = 'abierto'"
    parametros: tuple = (regla,)
    if tabla:
        sql += " AND tabla = ?"
        parametros += (tabla,)
    return conn.execute(sql + " ORDER BY id", parametros).fetchall()


def _consumo(conn, po_id: int) -> tuple[int, int]:
    fila = conn.execute("SELECT consumido_cent, restante_cent FROM v_po_consumo "
                        "WHERE orden_compra_id = ?", (po_id,)).fetchone()
    return fila[0], fila[1]


# ============================================================ casar referencias

def test_la_referencia_impresa_casa_con_la_po_de_su_cliente_y_la_imputa(ventas) -> None:
    conn = ventas.conn
    po = _con_pos(ventas)
    v101 = factura_de(conn, "V2026-0101")
    refs = conn.execute("SELECT orden_compra_id FROM factura_referencia WHERE factura_id = ? "
                        "AND retirada_en IS NULL", (v101,)).fetchall()
    assert [r[0] for r in refs] == [po]
    imputadas = conn.execute("SELECT orden_compra_id FROM factura_imputacion WHERE factura_id = ? "
                             "AND retirada_en IS NULL", (v101,)).fetchall()
    assert {r[0] for r in imputadas} == {po}
    # Sin IVA: la base de V2026-0101 (4.256,00); el abono aun no esta confirmado.
    assert _consumo(conn, po) == (425600, 1000000 - 425600)
    _limpio(conn)


def _rev(conn, tabla: str, fila_id: int) -> int:
    return conn.execute(f"SELECT rev FROM {tabla} WHERE id = ?", (fila_id,)).fetchone()[0]


def _imputaciones(conn, factura_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM factura_imputacion WHERE factura_id = ? "
                        "AND retirada_en IS NULL ORDER BY id", (factura_id,)).fetchall()


def _ventas_cambiadas(tmp_path, *cambios: tuple[str, str], extra: str = ""):
    """El listado de ventas de ejemplo con cambios de texto y filas de mas."""
    texto = VENTAS.read_text(encoding="utf-8-sig")
    for viejo, nuevo in cambios:
        assert viejo in texto, viejo
        texto = texto.replace(viejo, nuevo)
    ruta = tmp_path / "ventas.csv"
    ruta.write_bytes(("﻿" + texto + extra).encode("utf-8"))
    return ruta


@pytest.fixture
def otra_venta(almacen, tmp_path):
    """Como `ventas`, con una venta mas al mismo cliente con la misma PO (V2026-0103) y el
    abono C2026-0005 sin la PO impresa."""
    conn = almacen.conn
    ana = persona(conn, "Ana", "administrador")
    cuentas_propias(almacen, ana)
    importar_fichero(almacen, "exact", "clientes", EXACT_CLIENTES, lanzado_por=ana)
    importar_fichero(almacen, "maestro_csv", "objetos", OBJETOS, lanzado_por=ana)
    extra = ("70;V2026-0103;Factuur;03-10-2026;02-11-2026;10001;Havenbedrijf Rotterdam BV;"
             "NL009999999B01;M. Visser;30 dagen;01-10-2026;02-10-2026;Normaal;PO-4500123;;EUR;"
             "1.000,00;210,00;1.210,00;1;Montagewerk, locatie Rijnhaven;Rijnhaven;;Piet;"
             "01-10-2026;02-10-2026;16;uur;62,50;1.000,00;21;210,00;\n")
    ruta = _ventas_cambiadas(tmp_path, ("Normaal;PO-4500123;V2026-0101", "Normaal;;V2026-0101"),
                             extra=extra)
    importar_fichero(almacen, "exact", "facturas_venta", ruta, lanzado_por=ana)
    return almacen


def _confirmar_abono(conn) -> None:
    abono, original = factura_de(conn, "C2026-0005"), factura_de(conn, "V2026-0101")
    relacion = conn.execute("SELECT id, rev FROM factura_relacion WHERE origen_id = ? AND "
                            "destino_id = ?", (abono, original)).fetchone()
    _orden(conn, "confirmar_relacion", {"relacion_id": relacion["id"], "rev": relacion["rev"],
                                        "motivo": MOTIVO})


def _tres_cuentas(conn, po_id: int) -> tuple[int, int, int]:
    """Lo consumido segun la vista, segun ordenes_compra y segun las reglas."""
    vista = _consumo(conn, po_id)[0]
    almacen_ = sum(c.importe_cent for c in ordenes_compra.cargos(conn).get(po_id, []))
    reglas = sum(c.importe_cent for c in reglas_ordenes.cargos(
        instantaneas.construir(conn, hoy=date(2026, 10, 14))).get(po_id, []))
    return vista, almacen_, reglas


# ============================================================ la aritmetica del consumo

def test_el_abono_confirmado_resta_de_la_po_y_antes_no(ventas) -> None:
    conn = ventas.conn
    po = _con_pos(ventas)
    abono = factura_de(conn, "C2026-0005")
    assert {i["orden_compra_id"] for i in _imputaciones(conn, abono)} == {po}
    assert _tres_cuentas(conn, po) == (425600, 425600, 425600)
    _confirmar_abono(conn)
    # 4.256,00 - 248,00, sin IVA: el IVA (893,76 y -52,08) no consume la PO.
    assert _tres_cuentas(conn, po) == (400800, 400800, 400800)
    assert _consumo(conn, po) == (400800, 599200)
    _limpio(conn)


def test_un_abono_sin_po_impresa_toma_la_de_la_factura_que_abona(otra_venta) -> None:
    conn = otra_venta.conn
    po = _con_pos(otra_venta)
    abono = factura_de(conn, "C2026-0005")
    assert {i["orden_compra_id"] for i in _imputaciones(conn, abono)} == {None}
    _confirmar_abono(conn)
    assert {i["orden_compra_id"] for i in _imputaciones(conn, abono)} == {po}
    assert _tres_cuentas(conn, po) == (400800 + 100000,) * 3
    _limpio(conn)


def test_el_abono_de_una_original_anulada_ya_no_resta(ventas) -> None:
    """Anulada la original, su cargo sale de la PO: su abono no puede seguir restando (contaria
    dos veces y lo consumido quedaria en -248,00)."""
    conn = ventas.conn
    po = _con_pos(ventas)
    _confirmar_abono(conn)
    assert _tres_cuentas(conn, po) == (400800,) * 3
    v101 = factura_de(conn, "V2026-0101")
    _orden(conn, "anular_factura", {"factura_id": v101, "rev": _rev(conn, "factura", v101),
                                    "motivo": MOTIVO})
    assert _tres_cuentas(conn, po) == (0, 0, 0)
    assert _consumo(conn, po) == (0, 1000000)
    _limpio(conn)


def test_el_abono_de_una_original_sustituida_ya_no_resta(otra_venta) -> None:
    conn = otra_venta.conn
    po = _con_pos(otra_venta)
    _confirmar_abono(conn)
    abono = factura_de(conn, "C2026-0005")
    assert {i["orden_compra_id"] for i in _imputaciones(conn, abono)} == {po}   # heredada
    v101, v103 = factura_de(conn, "V2026-0101"), factura_de(conn, "V2026-0103")
    _orden(conn, "enlazar_facturas", {"origen_id": v103, "destino_id": v101,
                                      "tipo": "sustituye", "motivo": MOTIVO})
    # Solo la sustituta: 1.000,00, no 1.000,00 - 248,00. Y el abono ya no hereda la PO.
    assert _tres_cuentas(conn, po) == (100000,) * 3
    assert {i["orden_compra_id"] for i in _imputaciones(conn, abono)} == {None}
    _limpio(conn)


def test_una_sustituida_no_consume(otra_venta) -> None:
    conn = otra_venta.conn
    po = _con_pos(otra_venta)
    v101, v103 = factura_de(conn, "V2026-0101"), factura_de(conn, "V2026-0103")
    assert _tres_cuentas(conn, po) == (525600,) * 3
    _orden(conn, "enlazar_facturas", {"origen_id": v103, "destino_id": v101,
                                      "tipo": "sustituye", "motivo": MOTIVO})
    assert _tres_cuentas(conn, po) == (100000,) * 3
    assert _consumo(conn, po) == (100000, 900000)
    _limpio(conn)


def test_una_anulada_no_consume(otra_venta) -> None:
    conn = otra_venta.conn
    po = _con_pos(otra_venta)
    v103 = factura_de(conn, "V2026-0103")
    _orden(conn, "anular_factura", {"factura_id": v103, "rev": _rev(conn, "factura", v103),
                                    "motivo": MOTIVO})
    assert _tres_cuentas(conn, po) == (425600,) * 3
    _limpio(conn)


# ============================================================ referencias y clase

def test_una_referencia_que_una_persona_dice_que_no_es_po_no_casa(ventas) -> None:
    conn = ventas.conn
    po = _con_pos(ventas)
    v101 = factura_de(conn, "V2026-0101")
    referencia = conn.execute("SELECT id, rev FROM factura_referencia WHERE factura_id = ?",
                              (v101,)).fetchone()
    _orden(conn, "cambiar_po", {"referencia_id": referencia["id"], "clase": "ref_cliente",
                                "rev": referencia["rev"], "motivo": MOTIVO})
    assert conn.execute("SELECT orden_compra_id FROM factura_referencia WHERE id = ?",
                        (referencia["id"],)).fetchone()[0] is None
    assert {i["orden_compra_id"] for i in _imputaciones(conn, v101)} == {None}
    assert _consumo(conn, po)[0] == 0
    # La de la PO la sigue casando el sistema (el abono la imprime): no se edita a mano.
    with pytest.raises(servicios.DatosNoValidos, match="imputar_po"):
        _orden(conn, "fijar_campo", {"tabla": "factura_referencia", "fila_id": referencia["id"],
                                     "campo": "orden_compra_id", "valor": po,
                                     "rev": _rev(conn, "factura_referencia", referencia["id"])})
    _limpio(conn)


def test_una_referencia_que_no_casa_es_una_po_desconocida(ventas) -> None:
    conn = ventas.conn
    v101 = factura_de(conn, "V2026-0101")
    # Sin ninguna PO de cliente registrada no se sabe: sin datos, y P2 ve la PO impresa.
    assert _hallazgos(conn, "P3") == []
    assert conn.execute("SELECT resultado FROM evaluacion WHERE regla = 'P3' AND fila_id = ?",
                        (v101,)).fetchone()[0] == "sin_datos"
    assert conn.execute("SELECT resultado FROM evaluacion WHERE regla = 'P2' AND fila_id = ?",
                        (v101,)).fetchone()[0] == "ok"
    _orden(conn, "registrar_po", {"numero": "PO-1", "lado": "cliente",
                                  "parte_id": conn.execute("SELECT id FROM cliente WHERE "
                                                           "exact_id = '10001'").fetchone()[0],
                                  "valor": "5000"})
    [p3] = [h for h in _hallazgos(conn, "P3") if h["factura_id"] == v101]
    assert "PO-4500123" in p3["detalle"] and p3["severidad"] == "retencion"


# ============================================================ imputar a mano

def test_lo_que_imputa_una_persona_gana_a_lo_que_casa_el_sistema(ventas) -> None:
    conn = ventas.conn
    po = _con_pos(ventas)
    v101 = factura_de(conn, "V2026-0101")
    [primera, segunda] = _imputaciones(conn, v101)
    _orden(conn, "imputar_po", {"imputacion_id": segunda["id"], "orden_compra_id": None,
                                "rev": segunda["rev"], "motivo": "Waalhaven va sin PO"})
    procedencia = campos.procedencia(conn, "factura_imputacion", segunda["id"])["orden_compra_id"]
    assert procedencia["fuente"] == "manual_correccion"
    assert procedencia["valor_automatico"] == po          # el sistema lo sigue diciendo
    hallazgos.recalcular(conn)
    assert [i["orden_compra_id"] for i in _imputaciones(conn, v101)] == [po, None]
    assert _consumo(conn, po)[0] == primera["importe_cent"]
    # Una PO de otro cliente o de proveedor no se imputa a una venta.
    otra = _po(conn, "PO 4500777")
    with pytest.raises(servicios.DatosNoValidos, match="otra parte"):
        _orden(conn, "imputar_po", {"imputacion_id": primera["id"], "orden_compra_id": otra,
                                    "rev": _rev(conn, "factura_imputacion", primera["id"]),
                                    "motivo": MOTIVO})
    with pytest.raises(servicios.DatosNoValidos, match="es de proveedor"):
        _orden(conn, "imputar_po", {"imputacion_id": primera["id"],
                                    "orden_compra_id": _po(conn, "BMS-2026-014"),
                                    "rev": _rev(conn, "factura_imputacion", primera["id"]),
                                    "motivo": MOTIVO})
    _limpio(conn)


# ============================================================ umbrales y fechas

def test_los_umbrales_de_las_po_salen_de_la_configuracion(ventas, tmp_path) -> None:
    """Cada clave de las secciones ordenes_compra y tarifas de config/reglas.yaml llega a la
    politica con la que evaluan las reglas (y uno fuera de sus limites no se carga)."""
    from bms_agent import politica

    conn = ventas.conn
    po = _con_pos(ventas)
    schiedam = _po(conn, "PO 4500777")                     # acaba en 47 dias
    _orden(conn, "modificar_po", {"orden_compra_id": po, "valor": "5000", "motivo": "Recorte"})
    [p5] = [h for h in _hallazgos(conn, "P5") if h["fila_id"] == po]       # 85,12 % >= 80
    assert "85,12 %" in p5["detalle"]
    assert [h for h in _hallazgos(conn, "P7") if h["fila_id"] == schiedam] == []  # 47 > 30
    texto = (RAIZ / "config" / "reglas.yaml").read_text(encoding="utf-8")
    for clave in ("aviso_consumo_pct: 80", "dias_caducidad: 30", "margen_prevision_dias: 14",
                  "semanas_ritmo: 8", "exceso_bloqueo_pct: 10"):
        assert clave in texto, clave
    carpeta = tmp_path / "config"
    carpeta.mkdir()
    ruta = carpeta / "reglas.yaml"

    def cargar(*cambios: tuple[str, str]) -> None:
        nuevo = texto
        for viejo, otro in cambios:
            nuevo = nuevo.replace(viejo, otro)
        ruta.write_text(nuevo, encoding="utf-8")
        politica.cargar(conn, ruta, _ana(conn))

    cargar(("aviso_consumo_pct: 80", "aviso_consumo_pct: 90"),
           ("dias_caducidad: 30", "dias_caducidad: 90"),
           ("margen_prevision_dias: 14", "margen_prevision_dias: 30"),
           ("semanas_ritmo: 8", "semanas_ritmo: 4"),
           ("exceso_bloqueo_pct: 10", "exceso_bloqueo_pct: 25"))
    vigente = politica.politica_reglas(conn)
    assert (vigente.po_aviso_consumo_pct, vigente.po_dias_caducidad,
            vigente.po_margen_prevision_dias, vigente.po_semanas_ritmo,
            vigente.tarifa_exceso_bloqueo_pct) == (90, 90, 30, 4, 25)
    _orden(conn, "recalcular", {})
    assert [h for h in _hallazgos(conn, "P5") if h["fila_id"] == po] == []      # 85,12 < 90
    [p7] = [h for h in _hallazgos(conn, "P7") if h["fila_id"] == schiedam]      # 47 <= 90
    assert "(en 47 días)" in p7["detalle"]
    # Un umbral fuera de sus limites no se carga: por debajo de la mitad, P5 saltaria con
    # cualquier PO; por encima del 100 %, nunca.
    for malo in ("aviso_consumo_pct: 49", "aviso_consumo_pct: 101"):
        with pytest.raises(politica.PoliticaNoValida):
            cargar(("aviso_consumo_pct: 80", malo))
    assert politica.politica_reglas(conn).po_aviso_consumo_pct == 90


def test_la_caducidad_con_la_fecha_fija_y_la_prioridad_de_la_po(ventas) -> None:
    """Hoy es 2026-10-14 (el reloj de los tests): la PO de Schiedam acaba el 30 de noviembre."""
    conn = ventas.conn
    _con_pos(ventas)
    schiedam = _po(conn, "PO 4500777")
    # 47 dias: fuera de los 30. Se acorta a 20 de noviembre: 37. A 10 de noviembre: 27.
    assert [h for h in _hallazgos(conn, "P7") if h["fila_id"] == schiedam] == []
    _orden(conn, "modificar_po", {"orden_compra_id": schiedam, "fecha_fin": "2026-11-10",
                                  "motivo": "El cliente adelanta el fin de obra"})
    [p7] = [h for h in _hallazgos(conn, "P7") if h["fila_id"] == schiedam]
    assert p7["tabla"] == "orden_compra" and "(en 27 días)" in p7["detalle"]
    nivel, motivos = conn.execute("SELECT nivel, motivos_json FROM prioridad WHERE entidad = "
                                  "'orden_compra' AND entidad_id = ?", (schiedam,)).fetchone()
    assert "la PO caduca en 27 días (P7)" in motivos
    [fila] = [o for o in consultas.ordenes_compra(conn) if o["id"] == schiedam]
    assert fila["fecha_fin"] == "2026-11-10" and fila["nivel"] == nivel
    # Al dia siguiente la prioridad cuenta los dias de hoy desde el fin fijo del hallazgo.
    from bms_agent.almacen import reloj_de

    reloj_de(conn).avanzar(days=1)
    hallazgos.recalcular(conn, motivo="diaria")
    assert "la PO caduca en 26 días (P7)" in conn.execute(
        "SELECT motivos_json FROM prioridad WHERE entidad = 'orden_compra' AND entidad_id = ?",
        (schiedam,)).fetchone()[0]


def test_un_p7_aceptado_sigue_aceptado_al_dia_siguiente(ventas) -> None:
    """Los dias que quedan bajan cada dia: si estuvieran en la huella, un P7 aceptado se
    reabriria cada manana y apuntaria un cambio de evidencia cada dia."""
    from bms_agent.almacen import reloj_de

    conn = ventas.conn
    _con_pos(ventas)
    schiedam = _po(conn, "PO 4500777")
    _orden(conn, "modificar_po", {"orden_compra_id": schiedam, "fecha_fin": "2026-11-10",
                                  "motivo": "El cliente adelanta el fin de obra"})
    [p7] = [h for h in _hallazgos(conn, "P7") if h["fila_id"] == schiedam]
    _orden(conn, "anular_hallazgo", {"hallazgo_id": p7["id"], "huella": p7["huella"],
                                     "motivo": "Hablado con el cliente: no se alarga"})
    eventos = conn.execute("SELECT count(*) FROM hallazgo_evento WHERE hallazgo_id = ?",
                           (p7["id"],)).fetchone()[0]
    for _ in range(2):
        reloj_de(conn).avanzar(days=1)
        hallazgos.recalcular(conn, motivo="diaria")
    estado, detalle = conn.execute("SELECT estado, detalle FROM hallazgo WHERE id = ?",
                                   (p7["id"],)).fetchone()
    assert estado == "aceptado" and "(en 25 días)" in detalle
    assert conn.execute("SELECT count(*) FROM hallazgo_evento WHERE hallazgo_id = ?",
                        (p7["id"],)).fetchone()[0] == eventos
    _limpio(conn)


# ============================================================ P4 contra lo que quedaba

def test_p4_retiene_la_factura_que_pasa_lo_que_quedaba_y_es_pegajosa(otra_venta) -> None:
    conn = otra_venta.conn
    po = _con_pos(otra_venta)
    v101, v103 = factura_de(conn, "V2026-0101"), factura_de(conn, "V2026-0103")
    # Valor nuevo de 4.500,00: V2026-0101 (1-oct, 4.256,00) cabe; V2026-0103 (3-oct,
    # 1.000,00) llega con 244,00 por consumir.
    _orden(conn, "modificar_po", {"orden_compra_id": po, "valor": "4500", "fecha": "2026-10-10",
                                  "motivo": "El cliente recorta la PO"})
    [p4] = _hallazgos(conn, "P4")
    assert p4["factura_id"] == v103 and p4["pegajosa"] == 1
    assert "solo quedaban 244,00" in p4["detalle"]
    assert conn.execute("SELECT nivel FROM factura_estado WHERE factura_id = ?",
                        (v103,)).fetchone()[0] == "urgente"
    assert conn.execute("SELECT nivel FROM factura_estado WHERE factura_id = ?",
                        (v101,)).fetchone()[0] != "urgente"
    # Pegajosa: con la PO ampliada otra vez, el hallazgo no se cierra solo.
    _orden(conn, "modificar_po", {"orden_compra_id": po, "valor": "20000", "fecha": "2026-10-12",
                                  "motivo": "Ampliacion firmada"})
    assert conn.execute("SELECT estado FROM hallazgo WHERE id = ?",
                        (p4["id"],)).fetchone()[0] == "desaparecido"
    _limpio(conn)


# ============================================================ la modificacion

def test_una_modificacion_es_de_solo_escritura_y_la_firma_quien_puede(ventas) -> None:
    conn = ventas.conn
    po = _con_pos(ventas)
    _orden(conn, "modificar_po", {"orden_compra_id": po, "valor": "12500,00",
                                  "fecha": "2026-10-01", "motivo": "Ampliacion de Waalhaven"})
    detalle = consultas.orden_compra(conn, po)
    assert (detalle["valor_cent"], detalle["valor_original_cent"]) == (1250000, 1000000)
    assert [m["valor_nuevo"] for m in detalle["modificaciones"]] == ["12.500,00"]
    with pytest.raises(sqlite3.IntegrityError, match="solo escritura"):
        conn.execute("UPDATE orden_compra_modificacion SET valor_nuevo_cent = 1")
    with pytest.raises(sqlite3.IntegrityError, match="solo escritura"):
        conn.execute("DELETE FROM orden_compra_modificacion")
    # El valor original no se toca, ni por campos.py: lo que cambia es una modificacion.
    from bms_agent.almacen import usuario_sistema

    with pytest.raises(sqlite3.IntegrityError, match="modificacion"):
        campos.fijar(conn, "orden_compra", po, {"valor_original_cent": 1},
                     campos.Automatico("importacion", usuario_sistema(conn, "importador")))
    # Sin cambiar_po no se modifica; sin motivo tampoco.
    from bms_agent import permisos

    permisos.crear_rol(conn, "importacion", ["ver_facturas", "importar_datos"])
    bea = persona(conn, "Bea", "importacion")
    with pytest.raises(PermisoDenegado):
        _orden(conn, "modificar_po", {"orden_compra_id": po, "valor": "1",
                                      "motivo": "No deberia"}, usuario=bea)
    with pytest.raises(campos.FaltaMotivo):
        _orden(conn, "modificar_po", {"orden_compra_id": po, "valor": "1"})
    with pytest.raises(servicios.DatosNoValidos, match="valor, el fin"):
        _orden(conn, "modificar_po", {"orden_compra_id": po, "motivo": MOTIVO})
    from bms_agent.almacen.evidencia import verificar_evidencia

    assert verificar_evidencia(conn) == []
    _limpio(conn)


def test_una_modificacion_no_vale_desde_el_futuro_y_la_de_hoy_corrige(ventas,
                                                                         tmp_path) -> None:
    """Una modificacion vale en cuanto se apunta: con fecha futura subiria el limite hoy, y
    como la vigente es la de fecha mayor, una equivocada no se arreglaria con otra de hoy."""
    conn = ventas.conn
    po = _con_pos(ventas)                                   # hoy es 2026-10-14
    with pytest.raises(servicios.DatosNoValidos, match="posterior a hoy"):
        _orden(conn, "modificar_po", {"orden_compra_id": po, "valor": "100000",
                                      "fecha": "2027-06-01", "motivo": "Ampliacion de junio"})
    assert conn.execute("SELECT count(*) FROM orden_compra_modificacion").fetchone()[0] == 0
    # Una equivocada (de hoy o de antes) se corrige con otra sin fecha: la de hoy gana.
    _orden(conn, "modificar_po", {"orden_compra_id": po, "valor": "5000", "fecha": "2026-10-14",
                                  "motivo": "Recorte"})
    _orden(conn, "modificar_po", {"orden_compra_id": po, "valor": "9000",
                                  "motivo": "Corrijo la anterior: eran 9.000"})
    assert consultas.orden_compra(conn, po)["valor_cent"] == 900000
    assert _tres_cuentas(conn, po)[0] == 425600 and _consumo(conn, po)[1] == 900000 - 425600
    # La hoja de modificaciones tampoco apunta una futura: la fila se rechaza.
    hoja = tmp_path / "mods.csv"
    hoja.write_text(MODIFICACIONES_CSV.read_text(encoding="utf-8-sig").splitlines()[0] + "\n"
                    "PO-4500123;Klant;10001;01-06-2027;20.000,00;;Ampliacion de junio;EUR\n",
                    encoding="utf-8")
    [lote] = importar_fichero(ventas, "po_csv", "modificaciones_po", hoja,
                              lanzado_por=_ana(conn)).lotes
    assert lote.aceptadas == 0 and "posterior a hoy" in lote.rechazos[0].motivo
    assert consultas.orden_compra(conn, po)["valor_cent"] == 900000
    _limpio(conn)


def test_una_po_sin_numero_o_que_empieza_despues_de_su_fin_no_entra(ventas, tmp_path) -> None:
    conn = ventas.conn
    po = _con_pos(ventas)                                   # 2026-09-01 a 2026-12-31
    cliente = conn.execute("SELECT id FROM cliente WHERE exact_id = '10001'").fetchone()[0]
    with pytest.raises(servicios.DatosNoValidos, match="separadores"):
        _orden(conn, "registrar_po", {"numero": "--", "lado": "cliente", "parte_id": cliente,
                                      "valor": "100"})
    hoja = tmp_path / "pos.csv"
    hoja.write_text(PO_CSV.read_text(encoding="utf-8-sig").splitlines()[0] + "\n"
                    "-/-;Klant;10001;;;;;100,00;EUR;\n", encoding="utf-8")
    [lote] = importar_fichero(ventas, "po_csv", "ordenes_compra", hoja,
                              lanzado_por=_ana(conn)).lotes
    assert lote.aceptadas == 0 and "separadores" in lote.rechazos[0].motivo
    # El inicio no se corrige a despues del fin vigente (acortado) ni del original.
    _orden(conn, "modificar_po", {"orden_compra_id": po, "fecha_fin": "2026-11-01",
                                  "motivo": "Se acorta"})
    for inicio, que in (("2026-12-15", "fin vigente"), ("2027-01-15", "fin original")):
        with pytest.raises(servicios.DatosNoValidos, match=que):
            _orden(conn, "corregir_po", {"orden_compra_id": po, "campo": "fecha_inicio",
                                         "valor": inicio, "rev": _rev(conn, "orden_compra", po),
                                         "motivo": MOTIVO})
    _orden(conn, "corregir_po", {"orden_compra_id": po, "campo": "fecha_inicio",
                                 "valor": "2026-10-01", "rev": _rev(conn, "orden_compra", po),
                                 "motivo": MOTIVO})
    _limpio(conn)


# ============================================================ la hoja de PO

def test_la_hoja_de_po_entra_por_el_marco_de_importacion(ventas) -> None:
    conn = ventas.conn
    ana = _ana(conn)
    resultado = importar_fichero(ventas, "po_csv", "ordenes_compra", PO_CSV, lanzado_por=ana)
    [lote] = resultado.lotes
    assert (lote.aceptadas, [(r.fila, r.codigo) for r in lote.rechazos]) == (
        3, [(5, "X1"), (6, "fila"), (7, "fila")])
    po = _po(conn, "PO-4500123")
    fila = conn.execute("SELECT * FROM orden_compra WHERE id = ?", (po,)).fetchone()
    assert (fila["fuente"], fila["valor_original_cent"], fila["fecha_fin"]) == (
        "po_csv", 1000000, "2026-12-31")
    assert {f[0] for f in conn.execute(
        "SELECT o.codigo FROM orden_compra_objeto AS x JOIN objeto AS o ON o.id = x.objeto_id "
        "WHERE x.orden_compra_id = ?", (po,))} == {"Rijnhaven", "Waalhaven"}
    # Las modificaciones, en su hoja, como filas aparte.
    mods = importar_fichero(ventas, "po_csv", "modificaciones_po", MODIFICACIONES_CSV,
                            lanzado_por=ana)
    [lote] = mods.lotes
    assert lote.aceptadas == 3 and [r.fila for r in lote.rechazos] == [5, 6]
    detalle = consultas.orden_compra(conn, po)
    assert (detalle["valor_cent"], detalle["fecha_fin"], detalle["fecha_fin_original"]) == (
        1250000, "2027-03-31", "2026-12-31")
    assert {m["usuario"] for m in detalle["modificaciones"]} == {"Ana"}
    # Otra vez el mismo fichero: la misma importacion. Y una PO que vuelve con otro valor
    # se rechaza y pide la modificacion.
    assert importar_fichero(ventas, "po_csv", "ordenes_compra", PO_CSV,
                            lanzado_por=ana).lotes[0].repetida
    from bms_agent.almacen.evidencia import verificar_evidencia

    assert verificar_evidencia(conn) == []
    _limpio(conn)


def test_una_po_que_vuelve_con_otro_valor_se_rechaza_y_la_misma_anade_objetos(ventas,
                                                                              tmp_path) -> None:
    conn = ventas.conn
    texto = PO_CSV.read_text(encoding="utf-8-sig")
    solo_rijnhaven = tmp_path / "pos-1.csv"
    solo_rijnhaven.write_text(texto.replace("Rijnhaven, Waalhaven", "Rijnhaven")
                              + "PO-4500888;Klant;10001;Schiedam;;;;100,00;;\n",
                              encoding="utf-8")
    [lote] = importar_fichero(ventas, "po_csv", "ordenes_compra", solo_rijnhaven,
                              lanzado_por=_ana(conn)).lotes
    # Schiedam es de otro cliente: la PO 4500888 de Havenbedrijf no lo cubre.
    assert any(r.fila == 8 and "otro cliente" in r.motivo for r in lote.rechazos)
    po = _po(conn, "PO-4500123")

    def objetos() -> set[str]:
        return {f[0] for f in conn.execute(
            "SELECT o.codigo FROM orden_compra_objeto AS x JOIN objeto AS o "
            "ON o.id = x.objeto_id WHERE x.orden_compra_id = ? AND x.retirada_en IS NULL",
            (po,))}

    assert objetos() == {"Rijnhaven"}
    # La misma PO con un Objeto mas: se anade (lo que ya no trae no se retira).
    importar_fichero(ventas, "po_csv", "ordenes_compra", PO_CSV, lanzado_por=_ana(conn))
    assert objetos() == {"Rijnhaven", "Waalhaven"}
    # Con otro valor original no entra: pide la modificacion.
    otra = tmp_path / "pos-2.csv"
    otra.write_text(texto.replace("10.000,00", "11.000,00"), encoding="utf-8")
    [lote] = importar_fichero(ventas, "po_csv", "ordenes_compra", otra,
                              lanzado_por=_ana(conn)).lotes
    [motivo] = [r.motivo for r in lote.rechazos if r.fila == 2]
    assert "modificacion" in motivo
    assert conn.execute("SELECT valor_original_cent FROM orden_compra WHERE id = ?",
                        (po,)).fetchone()[0] == 1000000
    _limpio(conn)


def test_importar_la_hoja_de_po_pide_cambiar_po(ventas) -> None:
    conn = ventas.conn
    from bms_agent import permisos

    permisos.crear_rol(conn, "importacion", ["ver_facturas", "importar_datos"])
    bea = persona(conn, "Bea", "importacion")
    with pytest.raises(PermisoDenegado):
        importar_fichero(ventas, "po_csv", "ordenes_compra", PO_CSV, lanzado_por=bea)
    assert conn.execute("SELECT count(*) FROM orden_compra").fetchone()[0] == 0
    # Lo demas lo sigue importando.
    importar_fichero(ventas, "exact", "clientes", EXACT_CLIENTES, lanzado_por=bea)


def test_la_hoja_de_po_en_yaml_da_lo_mismo_que_el_csv(ventas) -> None:
    conn = ventas.conn
    resultado = importar_fichero(ventas, "po_csv", "ordenes_compra", PO_YAML,
                                 lanzado_por=_ana(conn))
    assert [(l.tipo, l.aceptadas, [r.fila for r in l.rechazos]) for l in resultado.lotes] == [
        ("ordenes_compra", 2, [3, 4]), ("modificaciones_po", 1, [2])]
    po = _po(conn, "PO-4500123")
    assert consultas.orden_compra(conn, po)["valor_cent"] == 1250000
    proveedor = _po(conn, "BMS-2026-014")
    assert conn.execute("SELECT lado, valor_original_cent FROM orden_compra WHERE id = ?",
                        (proveedor,)).fetchone()[:] == ("proveedor", 800000)
    _limpio(conn)


# ============================================================ las ordenes de una persona

def test_registrar_cerrar_y_cubrir_objetos_de_una_po(ventas) -> None:
    conn = ventas.conn
    cliente = conn.execute("SELECT id FROM cliente WHERE exact_id = '10001'").fetchone()[0]
    rijnhaven, schiedam = (conn.execute("SELECT id FROM objeto WHERE codigo = ?",
                                        (c,)).fetchone()[0] for c in ("Rijnhaven", "Schiedam"))
    diferencia = _orden(conn, "registrar_po", {
        "numero": "PO-4500123", "lado": "cliente", "parte_id": cliente, "valor": "10000",
        "fecha_inicio": "2026-09-01", "fecha_fin": "2026-12-31", "objetos": [rijnhaven]})
    po = diferencia.detalle["orden_compra_id"]
    assert conn.execute("SELECT fuente FROM orden_compra WHERE id = ?", (po,)).fetchone()[0] == (
        "manual")
    v101 = factura_de(conn, "V2026-0101")
    assert {i["orden_compra_id"] for i in _imputaciones(conn, v101)} == {po}
    # Waalhaven no lo cubre: P3 lo dice de la segunda linea.
    [p3] = [h for h in _hallazgos(conn, "P3") if h["factura_id"] == v101]
    assert "no cubre su Objeto" in p3["detalle"]
    _orden(conn, "objetos_po", {"orden_compra_id": po, "anadir": [
        conn.execute("SELECT id FROM objeto WHERE codigo = 'Waalhaven'").fetchone()[0]]})
    assert [h for h in _hallazgos(conn, "P3") if h["factura_id"] == v101] == []
    with pytest.raises(servicios.DatosNoValidos, match="otro cliente"):
        _orden(conn, "objetos_po", {"orden_compra_id": po, "anadir": [schiedam]})
    with pytest.raises(servicios.DatosNoValidos, match="ya hay una PO"):
        _orden(conn, "registrar_po", {"numero": "PO 4500123", "lado": "cliente",
                                      "parte_id": cliente, "valor": "1"})
    # Cerrada, lo que se le imputa retiene (P1); reabierta, no.
    _orden(conn, "cerrar_po", {"orden_compra_id": po, "rev": _rev(conn, "orden_compra", po),
                               "motivo": "Obra terminada"})
    [p1] = [h for h in _hallazgos(conn, "P1") if h["factura_id"] == v101]
    assert "cerrada" in p1["detalle"]
    _orden(conn, "cerrar_po", {"orden_compra_id": po, "cerrada": "no",
                               "rev": _rev(conn, "orden_compra", po), "motivo": "Se reabre"})
    assert [h for h in _hallazgos(conn, "P1") if h["factura_id"] == v101] == []
    _orden(conn, "corregir_po", {"orden_compra_id": po, "campo": "fecha_inicio",
                                 "valor": "2026-08-01", "rev": _rev(conn, "orden_compra", po),
                                 "motivo": "Mal tecleada"})
    with pytest.raises(servicios.DatosNoValidos, match="modificar_po"):
        _orden(conn, "corregir_po", {"orden_compra_id": po, "campo": "valor_original_cent",
                                     "valor": "1", "rev": _rev(conn, "orden_compra", po),
                                     "motivo": MOTIVO})
    _limpio(conn)


# ============================================================ lo que se lee

def test_la_ficha_de_la_po_y_la_vista_del_objeto(otra_venta) -> None:
    conn = otra_venta.conn
    po = _con_pos(otra_venta)
    detalle = consultas.orden_compra(conn, po)
    assert [(f["numero"], f["quedaba"]) for f in detalle["facturas"]] == [
        ("V2026-0101", "10.000,00"), ("V2026-0103", "5.744,00")]
    assert (detalle["consumido"], detalle["restante"], detalle["consumido_pct"]) == (
        "5.256,00", "4.744,00", "52,56 %")
    assert detalle["planificado"]["estado"] == "sin_datos"
    assert detalle["sin_facturar"]["estado"] == "sin_datos"
    assert detalle["prevision"]["agotamiento"] is not None
    assert [x["codigo"] for x in detalle["objetos"]] == ["Rijnhaven", "Waalhaven"]
    rijnhaven = conn.execute("SELECT id FROM objeto WHERE codigo = 'Rijnhaven'").fetchone()[0]
    vista = consultas.objeto(conn, rijnhaven)
    [fila] = [o for o in vista["ordenes_compra"] if o["id"] == po]
    # De la PO entera, 5.256,00; de Rijnhaven, 2.480,00 + 1.000,00.
    assert (fila["consumido_cent"], fila["consumido_objeto_cent"]) == (525600, 348000)
    assert fila["cubre_objeto"] and vista["ordenes_resumen"]["cliente"]["restante_cent"] == (
        1000000 - 525600)
    # Una PO sin Objetos cubre cualquiera de su cliente: la 4500777 de Bouwgroep, Schiedam.
    schiedam = conn.execute("SELECT id FROM objeto WHERE codigo = 'Schiedam'").fetchone()[0]
    vista_schiedam = consultas.objeto(conn, schiedam)
    [general] = vista_schiedam["ordenes_compra"]
    assert general["numero"] == "PO 4500777" and general["cubre_objeto"]
    assert vista_schiedam["ordenes_resumen"]["cliente"]["ordenes"] == 1
    lista = consultas.ordenes_compra(conn)
    # Sin el maestro de proveedores, la PO a Van Dijk no entro.
    assert {o["numero"] for o in lista} == {"PO-4500123", "PO 4500777"}
    with pytest.raises(LookupError):
        consultas.orden_compra(conn, 999)
    with pytest.raises(LookupError):
        consultas.objeto(conn, 999)


def test_la_ficha_de_una_factura_ensena_su_po(ventas) -> None:
    conn = ventas.conn
    po = _con_pos(ventas)
    ficha = consultas.detalle(conn, factura_de(conn, "V2026-0101"))
    assert {i["orden_compra"] for l in ficha["lineas"] for i in l["imputaciones"]} == {
        "PO-4500123"}
    assert {r["orden_compra_id"] for r in ficha["referencias"]} == {po}


# ============================================================ tarifas pactadas en el almacen

def test_v4_con_las_tarifas_de_venta_del_maestro(ventas) -> None:
    conn = ventas.conn
    importar_fichero(ventas, "maestro_csv", "tarifas", IMPORTACION / "maestro_csv-tarifas-v1.csv",
                     lanzado_por=_ana(conn))
    v101 = factura_de(conn, "V2026-0101")
    resultados = {r["clave"].rsplit("|", 1)[-1]: r for r in conn.execute(
        "SELECT * FROM evaluacion WHERE regla = 'V4' AND fila_id = ?", (v101,))}
    [primera, segunda] = _imputaciones(conn, v101)
    # Rijnhaven a 62,00 (la pactada); Waalhaven a 74,00 contra 1.074,00 (la de la hoja).
    assert resultados[f"pactada:{primera['id']}"]["resultado"] == "ok"
    assert resultados[f"pactada:{segunda['id']}"]["resultado"] == "fallo"
    [v4] = [h for h in _hallazgos(conn, "V4") if h["factura_id"] == v101]
    assert "por debajo" in v4["detalle"]


def test_una_tarifa_por_dia_del_maestro_casa_con_la_linea_por_dia(almacen, tmp_path) -> None:
    """La hoja de tarifas dice "dag" (la guarda como dia) y la linea de Exact imprime "dag": las
    dos son la misma unidad, y V4 compara con la pactada en vez de dar sin datos."""
    conn = almacen.conn
    ana = persona(conn, "Ana", "administrador")
    cuentas_propias(almacen, ana)
    importar_fichero(almacen, "exact", "clientes", EXACT_CLIENTES, lanzado_por=ana)
    importar_fichero(almacen, "maestro_csv", "objetos", OBJETOS, lanzado_por=ana)
    ruta = _ventas_cambiadas(tmp_path, ("40;uur;62,00;2.480,00", "5;dag;496,00;2.480,00"))
    importar_fichero(almacen, "exact", "facturas_venta", ruta, lanzado_por=ana)
    tarifas = tmp_path / "tarifas.csv"
    tarifas.write_text("Richting;Leverancier;Medewerker;Klant;Object;Soort werk;Dienst;Eenheid;"
                       "Tarief;Valuta;Geldig vanaf;Geldig tot\n"
                       "Verkoop;;;10001;Rijnhaven;Montagewerk;;dag;496,00;EUR;01-01-2026;\n",
                       encoding="utf-8")
    importar_fichero(almacen, "maestro_csv", "tarifas", tarifas, lanzado_por=ana)
    assert conn.execute("SELECT unidad FROM tarifa_acordada").fetchone()[0] == "dia"
    v101 = factura_de(conn, "V2026-0101")
    primera = _imputaciones(conn, v101)[0]
    assert conn.execute("SELECT unidad FROM factura_linea WHERE id = ?",
                        (primera["linea_id"],)).fetchone()[0] == "dia"
    assert conn.execute("SELECT resultado FROM evaluacion WHERE regla = 'V4' AND fila_id = ? "
                        "AND clave LIKE ?", (v101, f"%pactada:{primera['id']}")
                        ).fetchone()[0] == "ok"


# ============================================================ la CLI

def test_la_cli_ensena_las_po_su_ficha_y_la_del_objeto(tmp_path, capsys) -> None:
    from bms_agent.almacen import preparar
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    with preparar(db) as almacen:
        conn = almacen.conn
        ana = persona(conn, "Ana", "administrador")
        cuentas_propias(almacen, ana)
        for fuente, tipo, ruta in (("exact", "clientes", EXACT_CLIENTES),
                                   ("maestro_csv", "objetos", OBJETOS),
                                   ("exact", "facturas_venta", VENTAS),
                                   ("po_csv", "ordenes_compra", PO_CSV)):
            importar_fichero(almacen, fuente, tipo, ruta, lanzado_por=ana)
        po = _po(conn, "PO-4500123")
        rijnhaven = conn.execute("SELECT id FROM objeto WHERE codigo = 'Rijnhaven'").fetchone()[0]
    capsys.readouterr()
    assert main(["ordenes", "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    assert "PO-4500123" in salida and "4.256,00" in salida and "(42,56 %)" in salida
    assert main(["orden", str(po), "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    assert "V2026-0101" in salida and "quedaban 10.000,00" in salida
    assert "Objetos: Rijnhaven, Waalhaven" in salida
    assert main(["objeto", str(rijnhaven), "--db", str(db)]) == 0
    assert "PO PO-4500123" in capsys.readouterr().out
    assert main(["orden", "999", "--db", str(db)]) == 1
    assert main(["ordenes", "--json", "--db", str(db)]) == 0
    assert '"numero": "PO-4500123"' in capsys.readouterr().out
