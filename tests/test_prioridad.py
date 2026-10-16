"""La prioridad (spec §8): cada suelo, cada borde de los puntos, la puerta de "necesita
accion", la espera a alguien de fuera y que una persona solo pueda subirla.

`prioridad.calcular` es pura: estos casos no tocan la base. Los de la ultima
parte prueban lo mismo en el almacen (la subida a mano y la cache).
"""

from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta

import pytest
from conftest import RAIZ, factura_de, persona

from bms_agent import prioridad, servicios
from bms_agent.prioridad import (
    PESOS,
    Entradas,
    Hallazgo,
    Hija,
    Pesos,
    PesosNoValidos,
    Resultado,
    Subida,
    agregar,
    calcular,
    clave_orden,
    de_excepcion,
    huella_entradas,
    pesos_de_yaml,
)

HOY = date(2026, 10, 15)          # el plazo del BTW del T3 es el 31-10: 16 dias


def _h(regla: str = "D4", severidad: str = "bloqueo", estado: str = "abierto",
       entrada: str = "otra", **extra) -> Hallazgo:
    return Hallazgo(regla=regla, severidad=severidad, estado=estado, entrada=entrada,
                    texto=f"Lo que dice {regla}.", **extra)


def _e(**cambios) -> Entradas:
    """Una compra limpia, revisada y sin plazo: todo en cero salvo lo que se cambie."""
    base = dict(sentido="entrante", revisada=True, fecha_factura=date(2026, 9, 15))
    base.update(cambios)
    return Entradas(**base)


def _vence_en(dias: int, **cambios) -> Entradas:
    return _e(vencimiento=HOY + timedelta(days=dias), **cambios)


# ------------------------------------------------------------ suelos

@pytest.mark.parametrize("regla", ["B1", "B2", "C2", "A5", "X1", "K4", "K6", "R3", "D1", "D2",
                                   "D2b", "D3", "D4", "D6", "E3", "E4", "F1", "F2", "F3", "F7",
                                   "G1", "Q1", "A8"])
def test_un_hallazgo_que_bloquea_abierto_pone_bloqueada(regla) -> None:
    r = calcular(_e(hallazgos=(_h(regla),)), HOY)
    assert (r.nivel, r.suelo) == ("bloqueada", "bloqueada")
    assert r.motivos[0] == f"Bloqueada: Lo que dice {regla} ({regla})"


def test_un_bloqueo_anulado_no_pone_suelo_y_uno_desaparecido_pide_atencion() -> None:
    assert calcular(_e(hallazgos=(_h(estado="aceptado"),)), HOY).nivel == "normal"
    r = calcular(_e(hallazgos=(_h("B2", estado="desaparecido"),)), HOY)
    assert (r.nivel, r.suelo) == ("atencion", "atencion")
    assert "su condición ha desaparecido" in r.motivos[0]


@pytest.mark.parametrize("regla", sorted(prioridad.REGLAS_URGENTES))
def test_las_reglas_urgentes_ponen_por_lo_menos_urgente(regla) -> None:
    r = calcular(_e(hallazgos=(_h(regla, "retencion"),)), HOY)
    assert (r.nivel, r.suelo) == ("urgente", "urgente")
    assert f"({regla})" in r.motivos[0]


@pytest.mark.parametrize("hoy, urgente", [
    (date(2026, 10, 24), True),     # el BTW vence en 7 dias
    (date(2026, 10, 23), False),    # en 8
    (date(2026, 10, 31), True),     # hoy mismo
])
def test_el_iva_a_siete_dias_del_btw_es_urgente(hoy, urgente) -> None:
    for entrada in ("iva_blanda", "iva_dura"):
        r = calcular(_e(hallazgos=(_h("E7", "retencion", entrada=entrada),)), hoy)
        assert (r.suelo == "urgente") is urgente, (hoy, entrada)


def test_el_iva_de_un_trimestre_ya_vencido_cuenta_con_el_plazo_siguiente() -> None:
    """Una factura de febrero vista en octubre: su IVA va en la declaracion del 31-10."""
    vieja = _e(fecha_factura=date(2026, 2, 10), hallazgos=(_h("E7", "retencion", entrada="iva_blanda"),))
    assert prioridad.dias_hasta_btw(date(2026, 2, 10), date(2026, 10, 24)) == 7
    assert calcular(vieja, date(2026, 10, 24)).suelo == "urgente"
    assert calcular(vieja, date(2026, 10, 23)).suelo == "atencion"


@pytest.mark.parametrize("dias, revisada, excepcion, suelo", [
    (31, False, False, "urgente"),     # vencida mas de 30 dias, sin revisar
    (30, False, False, "normal"),      # 30 justos: aun no
    (31, True, False, "normal"),       # revisada y sin excepcion: no necesita accion
    (31, True, True, "urgente"),       # revisada pero con una excepcion abierta
])
def test_una_compra_vencida_mas_de_30_dias_que_necesita_accion_es_urgente(
        dias, revisada, excepcion, suelo) -> None:
    r = calcular(_vence_en(-dias, revisada=revisada, excepcion_abierta=excepcion), HOY)
    assert r.suelo == suelo


@pytest.mark.parametrize("dias, suelo", [(61, "urgente"), (60, "normal")])
def test_una_venta_vencida_mas_de_60_dias_es_urgente_aunque_este_revisada(dias, suelo) -> None:
    assert calcular(_vence_en(-dias, sentido="saliente", revisada=True), HOY).suelo == suelo


@pytest.mark.parametrize("entradas, motivo", [
    (_e(hallazgos=(_h("G3", "retencion", entrada="planning"),)), "retenida por"),
    (_e(excepcion_abierta=True), "excepción abierta"),
    (_e(dudosos=2), "2 campos dudosos sin verificar (Q2)"),
    (_e(sin_resolver=1), "1 cambio manual sin resolver (M1)"),
    (_e(hallazgos=(_h("B4", "retencion", estado="desaparecido"),)), "nadie lo ha cerrado"),
])
def test_lo_que_pide_atencion(entradas, motivo) -> None:
    r = calcular(entradas, HOY)
    assert r.suelo == "atencion"
    assert motivo in r.motivos[0]


def test_un_aviso_abierto_no_pone_suelo() -> None:
    assert calcular(_e(hallazgos=(_h("P5", "aviso", entrada="limite_po"),)), HOY).suelo == "normal"


# ------------------------------------------------------------ puntos

@pytest.mark.parametrize("dias, puntos", [
    (0, 20), (3, 20), (4, 10), (7, 10), (8, 0),
    (-1, 15), (-14, 15), (-15, 25), (-30, 25), (-31, 35), (-200, 35),
])
def test_plazo_y_vencimiento_de_una_compra(dias, puntos) -> None:
    assert calcular(_vence_en(dias, revisada=False), HOY).puntos == puntos


@pytest.mark.parametrize("dias, puntos", [
    (3, 0), (-1, 10), (-14, 10), (-15, 20), (-30, 20), (-31, 30), (-60, 30), (-61, 30),
])
def test_vencimiento_de_una_venta(dias, puntos) -> None:
    """Una venta no suma por el plazo que se acerca, solo por lo vencido."""
    assert calcular(_vence_en(dias, sentido="saliente", revisada=False), HOY).puntos == puntos


@pytest.mark.parametrize("cent, puntos", [
    (249_999, 0), (250_000, 5), (999_999, 5), (1_000_000, 10), (2_499_999, 10),
    (2_500_000, 20), (-2_500_000, 20),
])
def test_importe(cent, puntos) -> None:
    assert calcular(_e(importe_cent=cent, revisada=False), HOY).puntos == puntos


def test_plazo_vencimiento_e_importe_solo_cuentan_si_necesita_accion() -> None:
    caso = dict(vencimiento=HOY - timedelta(days=20), importe_cent=3_000_000)
    assert calcular(_e(revisada=True, **caso), HOY).puntos == 0
    assert calcular(_e(revisada=False, **caso), HOY).puntos == 25 + 20
    assert calcular(_e(revisada=True, excepcion_abierta=True, **caso), HOY).puntos == 25 + 20
    # Lo de los hallazgos cuenta siempre.
    con_planning = _e(revisada=True, hallazgos=(_h("G3", "retencion", entrada="planning"),))
    assert calcular(con_planning, HOY).puntos == 15


def test_una_factura_pagada_anulada_o_fusionada_no_tiene_plazo() -> None:
    r = calcular(_vence_en(-40, revisada=False, en_juego=False), HOY)
    assert (r.puntos, r.suelo) == (0, "normal")


@pytest.mark.parametrize("valor, puntos", [
    (None, 15), (49_999, 15), (50_000, 25), (249_999, 25), (250_000, 35)])
def test_discrepancia_de_planning(valor, puntos) -> None:
    h = _h("G2", "retencion", entrada="planning", valor_cent=valor)
    assert calcular(_e(hallazgos=(h,)), HOY).puntos == puntos


def test_dos_discrepancias_de_planning_suman_su_valor_y_cuentan_una_vez() -> None:
    hs = (_h("G2", "retencion", entrada="planning", valor_cent=30_000),
          _h("G4", "retencion", entrada="planning", valor_cent=30_000))
    assert calcular(_e(hallazgos=hs), HOY).puntos == 25


def test_facturacion_ausente() -> None:
    hs = (_h("V5", "retencion", entrada="facturacion_ausente"),
          _h("V8", "retencion", entrada="facturacion_ausente"))
    assert calcular(_e(hallazgos=hs), HOY).puntos == 20


@pytest.mark.parametrize("valor, semanas, puntos", [
    (99_999, 0, 15), (100_000, 0, 25), (100_000, 1, 30), (100_000, 4, 45), (100_000, 5, 45),
    (99_999, 3, 30)])
def test_trabajo_sin_facturar(valor, semanas, puntos) -> None:
    h = _h("V6", "retencion", entrada="trabajo_sin_facturar", valor_cent=valor,
           semanas_tras_gracia=semanas)
    assert calcular(_e(hallazgos=(h,)), HOY).puntos == puntos


def test_limite_de_po_blando() -> None:
    assert calcular(_e(hallazgos=(_h("P5", "aviso", entrada="limite_po"),)), HOY).puntos == 10


@pytest.mark.parametrize("dias, puntos", [(0, 20), (7, 20), (8, 10), (30, 10), (31, 0)])
def test_caducidad_de_po(dias, puntos) -> None:
    h = _h("P7", "aviso", entrada="caducidad_po", dias_para_caducar=dias)
    assert calcular(_e(hallazgos=(h,)), HOY).puntos == puntos


@pytest.mark.parametrize("hoy, puntos", [(date(2026, 10, 16), 20), (date(2026, 10, 17), 35)])
def test_iva_blando_y_su_extra_a_catorce_dias_del_btw(hoy, puntos) -> None:
    """El 16-10 faltan 15 dias para el 31-10; el 17-10, 14."""
    h = _h("E1", "aviso", entrada="iva_blanda")
    assert calcular(_e(hallazgos=(h,)), hoy).puntos == puntos


@pytest.mark.parametrize("reglas, puntos", [
    (("U1",), 10), (("U1", "U1"), 10), (("U1", "D2b"), 20), (("U1", "D2b", "R4"), 20)])
def test_otras_anomalias_diez_por_regla_hasta_veinte(reglas, puntos) -> None:
    hs = tuple(_h(r, "aviso") for r in reglas)
    assert calcular(_e(hallazgos=hs), HOY).puntos == puntos


@pytest.mark.parametrize("puntos, nivel", [(0, "normal"), (19, "normal"), (20, "atencion"),
                                           (39, "atencion"), (40, "urgente"), (400, "urgente")])
def test_de_puntos_a_nivel_nunca_bloqueada(puntos, nivel) -> None:
    assert prioridad.nivel_de_puntos(puntos) == nivel


def test_muchos_puntos_dan_urgente_y_no_bloqueada() -> None:
    hs = (_h("V6", "aviso", entrada="trabajo_sin_facturar", valor_cent=10**8,
             semanas_tras_gracia=10),
          _h("G2", "aviso", entrada="planning", valor_cent=10**8),
          _h("V5", "aviso", entrada="facturacion_ausente"))
    r = calcular(_vence_en(-100, revisada=False, importe_cent=10**9, hallazgos=hs), HOY)
    assert r.puntos >= 100 and r.nivel == "urgente" and r.suelo != "bloqueada"


# ------------------------------------------------------------ esperando a alguien de fuera

def _esperando(fecha: date, **cambios) -> Entradas:
    return _e(revisada=False, excepcion_abierta=True, esperando_a="proveedor",
              fecha_seguimiento=fecha, **cambios)


@pytest.mark.parametrize("dias, puntos", [(2, 10), (5, 5)])
def test_esperando_con_el_seguimiento_por_llegar_divide_plazo(dias, puntos) -> None:
    r = calcular(_esperando(HOY + timedelta(days=3), vencimiento=HOY + timedelta(days=dias)), HOY)
    assert r.puntos == puntos
    assert "a la mitad: se espera al proveedor" in " ".join(r.motivos)


def test_esperando_divide_tambien_lo_vencido_pero_no_el_importe() -> None:
    r = calcular(_esperando(HOY + timedelta(days=3), vencimiento=HOY - timedelta(days=20),
                            importe_cent=1_000_000), HOY)
    assert r.puntos == 25 // 2 + 10


def test_el_dia_del_seguimiento_no_divide_ni_suma() -> None:
    r = calcular(_esperando(HOY, vencimiento=HOY + timedelta(days=2)), HOY)
    assert r.puntos == 20


def test_con_el_seguimiento_pasado_suma_diez() -> None:
    r = calcular(_esperando(HOY - timedelta(days=1), vencimiento=HOY + timedelta(days=2)), HOY)
    assert r.puntos == 20 + 10
    assert any("el seguimiento venció" in m for m in r.motivos)


# ------------------------------------------------------------ subir a mano

def test_una_persona_sube_y_el_nivel_es_el_mayor() -> None:
    r = calcular(_e(subidas=(Subida("urgente", "el cliente amenaza con parar", "Ana"),)), HOY)
    assert (r.nivel, r.suelo, r.puntos) == ("urgente", "normal", 0)
    assert r.motivos[-1].startswith("subida a mano a urgente por Ana")


def test_una_subida_no_baja_nada() -> None:
    bloqueada = _e(hallazgos=(_h(),), subidas=(Subida("atencion", "no es para tanto, creo"),))
    assert calcular(bloqueada, HOY).nivel == "bloqueada"
    urgente = _e(hallazgos=(_h("B3", "retencion"),),
                 subidas=(Subida("atencion", "sube a atencion"),))
    assert calcular(urgente, HOY).nivel == "urgente"


def test_una_subida_vence_y_nunca_llega_a_bloqueada() -> None:
    vencida = Subida("urgente", "solo esta semana", hasta=HOY - timedelta(days=1))
    del_dia = Subida("urgente", "solo hoy", hasta=HOY)
    assert calcular(_e(subidas=(vencida,)), HOY).nivel == "normal"
    assert calcular(_e(subidas=(del_dia,)), HOY).nivel == "urgente"
    assert calcular(_e(subidas=(Subida("bloqueada", "a mano no"),)), HOY).nivel == "normal"


def test_bloqueada_tiene_siempre_una_regla_con_nombre() -> None:
    azar = random.Random(4)
    reglas = ["D4", "B3", "G3", "U1", "X1", "E7", "P5", "F3"]
    for _ in range(400):
        hs = tuple(_h(azar.choice(reglas), azar.choice(["bloqueo", "retencion", "aviso"]),
                      azar.choice(["abierto", "aceptado", "desaparecido"]),
                      azar.choice(["otra", "planning", "iva_blanda"]))
                   for _ in range(azar.randint(0, 3)))
        entradas = _e(hallazgos=hs, revisada=azar.random() < 0.5,
                      vencimiento=HOY + timedelta(days=azar.randint(-90, 20)),
                      importe_cent=azar.randint(0, 5_000_000),
                      subidas=(Subida(azar.choice(["atencion", "urgente", "bloqueada"]),
                                      "subida al azar"),) if azar.random() < 0.3 else ())
        r = calcular(entradas, HOY)
        if r.nivel == "bloqueada":
            assert r.suelo == "bloqueada"
            regla = next(h.regla for h in hs if h.estado == "abierto" and h.severidad == "bloqueo")
            assert r.motivos[0].startswith("Bloqueada:") and f"({regla})" in r.motivos[0]


# ------------------------------------------------------------ motivos, huella, orden

def test_el_motivo_empieza_por_el_suelo_y_sigue_con_cada_aportacion() -> None:
    """El ejemplo del §8."""
    f3 = Hallazgo("F3", "bloqueo", "abierto", "iban",
                  "IBAN NL..4300 no verificado para Van Dijk BV")
    r = calcular(_vence_en(2, revisada=False, importe_cent=1_240_000, hallazgos=(f3,)), HOY)
    assert r.texto == ("Bloqueada: IBAN NL..4300 no verificado para Van Dijk BV (F3) · "
                       "vence en 2 días +20 · importe 12.400,00 ≥ 10.000 +10")


def test_la_huella_de_las_entradas_cambia_con_cualquier_entrada_y_con_hoy() -> None:
    base = _vence_en(2, revisada=False)
    huella = huella_entradas(base, HOY)
    assert huella == huella_entradas(_vence_en(2, revisada=False), HOY)
    assert huella != huella_entradas(_vence_en(3, revisada=False), HOY)
    assert huella != huella_entradas(base, HOY + timedelta(days=1))
    assert huella != huella_entradas(base, HOY, Pesos(planning=16))


def test_el_orden_nivel_puntos_vencimiento_importe_e_id() -> None:
    def hija(id_, nivel, puntos, vence=None, importe=None):
        return Hija(id_, Resultado(nivel, puntos, nivel), vence, importe)

    hijas = [hija(1, "normal", 0), hija(2, "urgente", 10), hija(3, "urgente", 30),
             hija(4, "urgente", 30, date(2026, 10, 20)), hija(5, "urgente", 30, date(2026, 10, 18)),
             hija(6, "urgente", 30, date(2026, 10, 18), -900_000),
             hija(7, "urgente", 30, date(2026, 10, 18), 100), hija(8, "bloqueada", 0)]
    assert [h.id for h in prioridad.ordenar(hijas)] == [8, 6, 7, 5, 4, 3, 2, 1]
    assert clave_orden("normal", 0, None, None, 1) > clave_orden("normal", 0, HOY, None, 9)


def test_lo_que_tiene_facturas_toma_el_maximo_de_sus_hijas() -> None:
    hijas = [Hija(1, Resultado("atencion", 25, "atencion", ("x +25",)), etiqueta="la factura A"),
             Hija(2, Resultado("urgente", 10, "urgente", ("Urgente: B3",)),
                  etiqueta="la factura B")]
    agregada = agregar(hijas, HOY)
    assert (agregada.resultado.nivel, agregada.id) == ("urgente", 2)
    assert agregada.resultado.motivos[0].startswith("por la factura B")
    assert agregar([], HOY) is None
    subida = agregar(hijas, HOY, [Subida("urgente", "subida del proveedor")])
    assert subida.resultado.nivel == "urgente"


def test_una_excepcion_toma_el_mayor_de_sus_hallazgos_y_su_factura() -> None:
    factura = Resultado("urgente", 40, "atencion", ("vencida +40",))
    r = de_excepcion([_h("G3", "retencion")], factura, HOY)
    assert (r.nivel, r.suelo) == ("urgente", "atencion")
    r = de_excepcion([_h("D4"), _h("G3", "retencion")], factura, HOY)
    assert (r.nivel, r.suelo) == ("bloqueada", "bloqueada")
    assert de_excepcion([_h(estado="aceptado")], None, HOY).nivel == "normal"


# ------------------------------------------------------------ los pesos

def test_config_prioridad_yaml_es_lo_que_dice_el_codigo() -> None:
    texto = (RAIZ / "config" / "prioridad.yaml").read_text(encoding="utf-8")
    assert pesos_de_yaml(texto) == PESOS


@pytest.mark.parametrize("cambio, error", [
    (lambda t: t.replace("limite_po: 10\n", ""), "faltan"),
    (lambda t: t + "nueva_regla: 5\n", "sobran"),
    (lambda t: t.replace("limite_po: 10", "limite_po: 10.5"), "entero"),
    (lambda t: t.replace("limite_po: 10", "limite_po: -1"), "entero"),
    (lambda t: t.replace("{hasta_dias: 3, puntos: 20}", "{hasta_dias: 9, puntos: 20}"),
     "ordenados"),
    (lambda t: t.replace("  urgente: 40", "  urgente: 10"), "menor que urgente"),
    (lambda t: "[1, 2]", "diccionario"),
])
def test_un_fichero_de_pesos_con_otra_forma_se_rechaza(cambio, error) -> None:
    texto = (RAIZ / "config" / "prioridad.yaml").read_text(encoding="utf-8")
    with pytest.raises(PesosNoValidos, match=error):
        pesos_de_yaml(cambio(texto))


def test_cargar_los_pesos_los_apunta_en_la_politica_y_los_usa(tipado, tmp_path) -> None:
    from bms_agent import politica
    from bms_agent.hallazgos import recalcular

    conn = tipado.conn
    recalcular(conn)
    fila = conn.execute("SELECT politica_sha256 FROM factura_estado LIMIT 1").fetchone()
    assert fila[0] == PESOS.sha256()
    ruta = RAIZ / "config" / "prioridad.yaml"
    pesos, nuevo = politica.cargar_prioridad(conn, ruta)
    assert nuevo and pesos == PESOS
    assert not politica.cargar_prioridad(conn, ruta)[1]
    version = politica.vigente(conn, politica.FICHERO_PRIORIDAD)
    assert version["contenido"] == ruta.read_text(encoding="utf-8")

    otro = tmp_path / "prioridad.yaml"
    otro.write_text(ruta.read_text(encoding="utf-8").replace(
        "  atencion: 20", "  atencion: 15"), encoding="utf-8")
    politica.cargar_prioridad(conn, otro)
    recalcular(conn)
    usados = {f[0] for f in conn.execute("SELECT DISTINCT politica_sha256 FROM factura_estado")}
    assert usados == {politica.pesos_prioridad(conn).sha256()} != {PESOS.sha256()}


# ------------------------------------------------------------ en el almacen

def test_subir_a_mano_en_el_almacen_solo_sube(tipado) -> None:
    conn = tipado.conn
    ana = persona(conn, "Ana", "administracion")
    limpia = factura_de(conn, "2026-0912")
    usd = factura_de(conn, "NW-2026-0042")
    servicios.ejecutar(conn, "recalcular", usuario_id=ana)

    dif = servicios.ejecutar(conn, "subir_prioridad", {
        "entidad_id": limpia, "nivel": "urgente", "motivo": "el cliente espera respuesta hoy"},
        usuario_id=ana)
    assert {(p["entidad"], p["entidad_id"], p["despues"]) for p in dif.prioridades} >= {
        ("factura", limpia, "urgente")}
    assert conn.execute("SELECT nivel FROM factura_estado WHERE factura_id = ?",
                        (limpia,)).fetchone()[0] == "urgente"
    # Por debajo de lo que ya se ve no es subir: ni por la orden ni por la base.
    from bms_agent.estados import NoSube

    with pytest.raises(NoSube):
        servicios.ejecutar(conn, "subir_prioridad", {
            "entidad_id": usd, "nivel": "atencion", "motivo": "atencion para la de dolares"},
            usuario_id=ana)
    with pytest.raises(NoSube):
        servicios.ejecutar(conn, "subir_prioridad", {
            "entidad_id": limpia, "nivel": "bloqueada", "motivo": "bloqueada a mano, no"},
            usuario_id=ana)
    from bms_agent.almacen import transaccion
    from bms_agent.auditoria import registrar

    with pytest.raises(sqlite3.IntegrityError, match="solo se sube"):
        with transaccion(conn):
            evento = registrar(conn, tipo="prioridad_subida", actor=ana, usuario_id=ana)
            conn.execute("INSERT INTO prioridad_manual (entidad, entidad_id, nivel, motivo, "
                         "usuario_id, en, evento_id) VALUES ('factura', ?, 'atencion', "
                         "'por detras de la orden', ?, '2026-10-14T09:30:00+00:00', ?)",
                         (usd, ana, evento))
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        with transaccion(conn):
            evento = registrar(conn, tipo="prioridad_subida", actor=ana, usuario_id=ana)
            conn.execute("INSERT INTO prioridad_manual (entidad, entidad_id, nivel, motivo, "
                         "usuario_id, en, evento_id) VALUES ('factura', ?, 'bloqueada', "
                         "'bloqueada por detras', ?, '2026-10-14T09:30:00+00:00', ?)",
                         (limpia, ana, evento))
    # Una subida no se toca ni se borra.
    with pytest.raises(sqlite3.IntegrityError, match="solo escritura"):
        conn.execute("UPDATE prioridad_manual SET nivel = 'atencion'")
    with pytest.raises(sqlite3.IntegrityError, match="solo escritura"):
        conn.execute("DELETE FROM prioridad_manual")


def test_la_cache_de_prioridad_agrega_por_proveedor_trimestre_y_excepcion(tipado) -> None:
    from bms_agent.hallazgos import recalcular

    conn = tipado.conn
    recalcular(conn)
    usd = factura_de(conn, "NW-2026-0042")
    excepcion = conn.execute("SELECT id FROM excepcion WHERE factura_id = ?", (usd,)).fetchone()[0]
    fila = conn.execute("SELECT * FROM prioridad WHERE entidad = 'excepcion' AND entidad_id = ?",
                        (excepcion,)).fetchone()
    assert fila["nivel"] == "bloqueada" and "(X1)" in fila["motivos_json"]
    trimestres = {f["entidad_id"]: f["nivel"] for f in conn.execute(
        "SELECT * FROM prioridad WHERE entidad = 'trimestre'")}
    fecha = conn.execute("SELECT fecha_factura FROM factura WHERE id = ?", (usd,)).fetchone()[0]
    ano, mes = int(fecha[:4]), int(fecha[5:7])
    assert trimestres[ano * 10 + (mes - 1) // 3 + 1] == "bloqueada"
    for f in conn.execute("SELECT * FROM factura_estado"):
        assert len(f["huella_entradas"]) == 64 and f["politica_sha256"] == PESOS.sha256()


# ------------------------------------------------------------ correcciones de la revision

def test_lo_que_no_esta_en_juego_no_suma_por_importe() -> None:
    """Anulada, fusionada (y pagada, desde el paso 7) no necesita accion por su importe:
    sin esto, una anulada grande quedaba en Atencion para siempre."""
    r = calcular(_vence_en(-40, revisada=False, en_juego=False, importe_cent=3_000_000), HOY)
    assert (r.nivel, r.puntos, r.motivos) == ("normal", 0, ())
    # La misma, en juego, si.
    r = calcular(_vence_en(-40, revisada=False, importe_cent=3_000_000), HOY)
    assert any("importe" in m for m in r.motivos)


def test_volver_a_unos_pesos_anteriores_el_mismo_dia_los_pone_en_vigor(tipado, tmp_path) -> None:
    from bms_agent import politica

    conn = tipado.conn
    ruta = RAIZ / "config" / "prioridad.yaml"
    otro = tmp_path / "prioridad.yaml"
    otro.write_text(ruta.read_text(encoding="utf-8").replace(
        "  atencion: 20", "  atencion: 25"), encoding="utf-8")
    nuevos = [politica.cargar_prioridad(conn, r)[1] for r in (ruta, otro, ruta)]
    assert nuevos == [True, True, True]
    assert politica.pesos_prioridad(conn) == PESOS
    assert politica.vigente(conn, politica.FICHERO_PRIORIDAD)["contenido"] == ruta.read_text(
        encoding="utf-8")
    # Volver a cargar la que ya vale no apunta nada.
    assert politica.cargar_prioridad(conn, ruta)[1] is False


def test_los_pesos_con_que_se_calcula_estan_siempre_en_la_politica(tipado) -> None:
    """Sin cargar ningun fichero, la primera pasada apunta los pesos del codigo."""
    from bms_agent import politica
    from bms_agent.hallazgos import recalcular

    conn = tipado.conn
    assert politica.vigente(conn, politica.FICHERO_PRIORIDAD) is None
    recalcular(conn)
    version = politica.vigente(conn, politica.FICHERO_PRIORIDAD)
    assert version is not None
    usados = {f[0] for f in conn.execute("SELECT DISTINCT politica_sha256 FROM factura_estado")}
    usados |= {f[0] for f in conn.execute("SELECT DISTINCT politica_sha256 FROM prioridad")}
    assert usados == {pesos_de_yaml(version["contenido"]).sha256()} == {PESOS.sha256()}
    eventos = conn.execute("SELECT count(*) FROM evento").fetchone()[0]
    recalcular(conn)
    assert conn.execute("SELECT count(*) FROM politica_version").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM evento").fetchone()[0] == eventos


def test_los_dias_del_btw_saltan_los_trimestres_presentados() -> None:
    """Revision del paso 11: el plazo de un trimestre ya presentado se cumplio; lo que quede
    de su IVA va a la declaracion siguiente y corre contra su plazo."""
    hoy = date(2026, 10, 25)
    assert prioridad.dias_hasta_btw(date(2026, 8, 10), hoy) == 6
    assert prioridad.dias_hasta_btw(date(2026, 8, 10), hoy, frozenset({(2026, 3)})) == 98
    assert prioridad.dias_hasta_btw(date(2026, 8, 10), hoy,
                                    frozenset({(2026, 3), (2026, 4)})) == 187
    # Otro trimestre presentado no cambia nada.
    assert prioridad.dias_hasta_btw(date(2026, 8, 10), hoy, frozenset({(2026, 2)})) == 6
