"""El planning de TRNSPRNT en el almacen (paso 10): importar, conciliar, evaluar y verlo.

Puertas del paso 10 que viven aqui, sobre el almacen entero (las de las
reglas puras estan en test_reglas_paso10.py):

- una foto del planning entra entera o no entra, con los turnos que no traen
  identificador marcados como fragiles, y la exportacion semanal se lee por
  semanas;
- cada foto aceptada queda congelada (evidencia) y vale la mas nueva de cada
  dia (v_turno_vigente);
- la conciliacion deja la traza de cada linea a sus turnos, y no cambia
  cuando cambia el planning: una foto mas nueva que cambia una semana ya
  facturada da V9;
- el trabajo sin facturar aparece pasado su periodo y su gracia, y sube la
  prioridad del cliente;
- las vistas (Objeto, cliente, PO, flujo de caja) dicen sin datos sin
  planning, y lo que sale de el cuando lo hay.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest
from conftest import RAIZ, cuentas_propias, factura_de, persona

from bms_agent import campos, consultas, flujo_caja, hallazgos, servicios
from bms_agent.almacen.evidencia import verificar_evidencia
from bms_agent.importadores.registrar import importar_fichero

IMPORTACION = RAIZ / "tests" / "fixtures" / "importacion"
PLANNING = IMPORTACION / "trnsprnt-planning-v1.csv"
SEMANAL = IMPORTACION / "trnsprnt-planning-semana-v1.csv"
VENTAS = IMPORTACION / "exact-facturas_venta-v1.csv"
MOTIVO = "Visto con el planning delante"


# ------------------------------------------------------------ constructores

def _ana(conn) -> int:
    return conn.execute("SELECT id FROM usuario WHERE nombre = 'Ana'").fetchone()[0]


@pytest.fixture
def maestros(almacen):
    """Clientes, proveedores, Objetos y recursos del maestro. Ana lo puede todo."""
    conn = almacen.conn
    ana = persona(conn, "Ana", "administrador")
    cuentas_propias(almacen, ana)
    for fuente, tipo, nombre in (("exact", "clientes", "exact-clientes-v1.csv"),
                                 ("exact", "proveedores", "exact-proveedores-v1.csv"),
                                 ("maestro_csv", "objetos", "maestro_csv-objetos-v1.csv"),
                                 ("maestro_csv", "recursos", "maestro_csv-recursos-v1.csv")):
        importar_fichero(almacen, fuente, tipo, IMPORTACION / nombre, lanzado_por=ana)
    return almacen


def _planning(almacen, ruta=PLANNING, **opciones):
    return importar_fichero(almacen, "trnsprnt", "planning", ruta,
                            lanzado_por=_ana(almacen.conn), **opciones)


def _cambiado(tmp_path, *cambios: tuple[str, str], fuente=PLANNING, nombre="planning.csv"):
    texto = fuente.read_text(encoding="utf-8-sig")
    for viejo, nuevo in cambios:
        assert viejo in texto, viejo
        texto = texto.replace(viejo, nuevo)
    ruta = tmp_path / nombre
    ruta.write_text(texto, encoding="utf-8")
    return ruta


_FILA_VENTA = ("70;{numero};Factuur;{fecha};18-11-2026;10001;Havenbedrijf Rotterdam BV;"
               "NL009999999B01;M. Visser;30 dagen;{desde};{hasta};Normaal;;;EUR;{base};{iva};"
               "{total};1;Beveiliging {objeto};{objeto};;{medewerker};{desde};{hasta};{horas};uur;"
               "{tarifa};{base};21;{iva};")


def _euros(cent: int) -> str:
    return f"{cent // 100},{cent % 100:02d}"


def _venta(tmp_path, numero="V2026-0201", *, fecha="19-10-2026", desde="12-10-2026",
           hasta="18-10-2026", objeto="Rijnhaven", medewerker="", horas="15",
           tarifa="59,80", nombre="ventas.csv"):
    """Una venta de Exact de una sola linea por horas (el listado de ejemplo con otra fila)."""
    base = round(float(horas.replace(",", ".")) * float(tarifa.replace(",", ".")) * 100)
    iva = base * 21 // 100
    cabecera = VENTAS.read_text(encoding="utf-8-sig").splitlines()[0]
    fila = _FILA_VENTA.format(numero=numero, fecha=fecha, desde=desde, hasta=hasta,
                              objeto=objeto, medewerker=medewerker, horas=horas, tarifa=tarifa,
                              base=_euros(base), iva=_euros(iva), total=_euros(base + iva))
    ruta = tmp_path / nombre
    ruta.write_bytes(("﻿" + cabecera + "\n" + fila + "\n").encode("utf-8"))
    return ruta


def _importar_venta(almacen, ruta) -> int:
    resultado = importar_fichero(almacen, "exact", "facturas_venta", ruta,
                                 lanzado_por=_ana(almacen.conn))
    assert [l.estado for l in resultado.lotes] == ["aceptada"], resultado.lotes[0].rechazos
    return resultado.lotes[0].importacion_id


def _abiertos(conn, regla: str, tabla: str = "factura") -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM hallazgo WHERE regla = ? AND tabla = ? "
                        "AND estado = 'abierto' ORDER BY id", (regla, tabla)).fetchall()


def _conciliacion(conn, factura_id: int, *, activas: bool = True) -> list[tuple]:
    return [tuple(f) for f in conn.execute(
        "SELECT t.id_externo, c.horas_mil, c.regla, t.importacion_id FROM conciliacion AS c "
        "JOIN planning_turno AS t ON t.id = c.planning_turno_id JOIN factura_imputacion AS i "
        "ON i.id = c.imputacion_id WHERE i.factura_id = ? AND (c.retirada_en IS NULL) = ? "
        "ORDER BY c.id", (factura_id, int(activas)))]


def _limpio(conn) -> None:
    assert campos.verificar_controladas(conn) == []
    assert hallazgos.verificar(conn) == []
    assert verificar_evidencia(conn) == []


# ============================================================ importar

def test_una_foto_del_planning_entra_entera_con_sus_turnos(maestros) -> None:
    conn = maestros.conn
    resultado = _planning(maestros)
    [lote] = resultado.lotes
    assert (lote.estado, lote.aceptadas) == ("aceptada", 7)
    assert any("clave sintetica" in a for a in lote.avisos)
    importacion = conn.execute("SELECT * FROM importacion WHERE id = ?",
                               (lote.importacion_id,)).fetchone()
    assert (importacion["cubre_desde"], importacion["cubre_hasta"]) == ("2026-10-12",
                                                                        "2026-10-20")
    turnos = {f["id_externo"]: f for f in conn.execute(
        "SELECT * FROM planning_turno WHERE importacion_id = ?", (lote.importacion_id,))}
    # La noche sin horas planificadas: de 23:00 a 7:00 menos la pausa.
    noche = turnos["D-2026-104212"]
    assert (noche["horas_planificadas_mil"], noche["hora_fin"], noche["tipo_turno"]) == (
        7500, "07:00", "Nacht")
    assert noche["proveedor_id"] is not None and noche["recurso_id"] is not None
    assert turnos["D-2026-104215"]["estado"] == "cancelado"
    assert turnos["D-2026-104217"]["horas_planificadas_mil"] == 8333
    assert turnos["D-2026-104217"]["facturable"] == 0
    [fragil] = [t for t in turnos.values() if t["clave_fragil"]]
    assert fragil["id_externo"].startswith("sint:2026-10-19|")
    # Lo que no esta en el maestro entra con su texto, sin resolver, y es Z2.
    assert turnos["D-2026-104217"]["objeto_id"] is None
    assert turnos["D-2026-104217"]["objeto_ref_doc"] == "IJsselmonde"
    [z2] = [h for h in _abiertos(conn, "Z2", "importacion") if h["fila_id"] == lote.importacion_id]
    assert "planning" in z2["detalle"] or "sin resolver" in z2["detalle"]
    # Cada turno es evidencia: su foto en el evento de su importacion, y no se toca.
    _limpio(conn)
    with pytest.raises(sqlite3.DatabaseError, match="evidencia"):
        conn.execute("UPDATE planning_turno SET horas_aprobadas_mil = 1 WHERE id = ?",
                     (noche["id"],))


def test_una_fila_que_no_se_lee_rechaza_la_foto_entera(maestros, tmp_path) -> None:
    conn = maestros.conn
    ruta = _cambiado(tmp_path, ("D-2026-104213;13-10-2026", "D-2026-104213;31-13-2026"))
    [lote] = _planning(maestros, ruta).lotes
    assert lote.estado == "rechazada" and lote.aceptadas == 0
    assert conn.execute("SELECT count(*) FROM planning_turno").fetchone()[0] == 0
    # Dos turnos con el mismo identificador tampoco entran.
    ruta = _cambiado(tmp_path, ("D-2026-104213", "D-2026-104212"), nombre="dobles.csv")
    [lote] = _planning(maestros, ruta).lotes
    assert lote.estado == "rechazada"
    assert any(r.codigo == "duplicada" for r in lote.rechazos)


def test_la_exportacion_semanal_se_lee_por_semanas(maestros) -> None:
    conn = maestros.conn
    [lote] = _planning(maestros, SEMANAL).lotes
    assert lote.estado == "aceptada"
    filas = conn.execute("SELECT nivel, fecha, semana_iso, dias, horas_aprobadas_mil, estado "
                         "FROM planning_turno ORDER BY id").fetchall()
    assert [tuple(f) for f in filas] == [
        ("semana", "2026-10-12", "2026-W42", 5, 40000, "validado"),
        ("semana", "2026-10-12", "2026-W42", 2, 16000, "validado"),
        ("semana", "2026-12-28", "2026-W53", 1, 8000, "validado")]
    assert conn.execute("SELECT cubre_desde, cubre_hasta FROM importacion WHERE id = ?",
                        (lote.importacion_id,)).fetchone()[:] == ("2026-10-12", "2027-01-03")


def test_lo_que_cubre_una_foto_se_puede_decir_y_no_admite_turnos_de_fuera(maestros) -> None:
    conn = maestros.conn
    [lote] = _planning(maestros, cubre_desde=date(2026, 10, 13),
                       cubre_hasta=date(2026, 10, 25), simular=True).lotes
    assert lote.estado == "rechazada"
    assert any("2026-10-12" in r.motivo for r in lote.rechazos)
    [lote] = _planning(maestros, cubre_desde=date(2026, 10, 5),
                       cubre_hasta=date(2026, 10, 25)).lotes
    assert lote.estado == "aceptada"
    assert conn.execute("SELECT cubre_desde, cubre_hasta FROM importacion WHERE id = ?",
                        (lote.importacion_id,)).fetchone()[:] == ("2026-10-05", "2026-10-25")


def test_vale_la_foto_mas_nueva_de_cada_dia(maestros, tmp_path) -> None:
    conn = maestros.conn
    _planning(maestros)
    # La segunda solo cubre el 12 de octubre: ese dia vale ella, los demas la primera.
    ruta = _cambiado(tmp_path, ("Jan Bakker;20004;Objectbeveiliging;Nacht;;7,50;7,50",
                                "Jan Bakker;20004;Objectbeveiliging;Nacht;;6,50;6,50"))
    [lote] = _planning(maestros, ruta, cubre_desde=date(2026, 10, 12),
                       cubre_hasta=date(2026, 10, 12)).lotes
    assert lote.estado == "rechazada"           # trae turnos de fuera de lo que dice cubrir
    texto = ruta.read_text(encoding="utf-8")
    solo_el_12 = tmp_path / "solo-el-12.csv"
    solo_el_12.write_text("\n".join(l for l in texto.splitlines()
                                    if l.startswith("Dienst-ID") or ";12-10-2026;" in l) + "\n",
                          encoding="utf-8")
    [lote] = _planning(maestros, solo_el_12).lotes
    assert lote.estado == "aceptada"
    vigentes = dict(conn.execute("SELECT id_externo, importacion_id FROM v_turno_vigente"))
    assert vigentes["D-2026-104212"] == lote.importacion_id
    assert vigentes["D-2026-104213"] != lote.importacion_id
    horas = conn.execute("SELECT horas_aprobadas_mil FROM v_turno_vigente WHERE id_externo = ?",
                         ("D-2026-104212",)).fetchone()[0]
    assert horas == 6500
    # La foto de antes sigue entera: es evidencia.
    assert conn.execute("SELECT count(*) FROM planning_turno").fetchone()[0] == 9


# ============================================================ conciliar

def test_la_conciliacion_deja_la_traza_de_cada_linea_a_sus_turnos(maestros, tmp_path) -> None:
    conn = maestros.conn
    _planning(maestros)
    _importar_venta(maestros, _venta(tmp_path))
    v201 = factura_de(conn, "V2026-0201")
    # Sin persona en la linea, el Objeto y la semana: los dos turnos facturables de
    # Rijnhaven esa semana (el cancelado y el de otro Objeto no).
    assert _conciliacion(conn, v201) == [("D-2026-104211", 7500, "objeto_semana", 7),
                                         ("D-2026-104212", 7500, "objeto_semana", 7)]
    [traza] = consultas.detalle(conn, v201)["conciliacion"]
    assert traza["nivel"] == "objeto_semana" and traza["horas_mil"] == 15000
    assert [t["id_externo"] for t in traza["turnos"]] == ["D-2026-104211", "D-2026-104212"]
    assert [r["resultado"] for r in conn.execute(
        "SELECT resultado FROM evaluacion WHERE regla = 'V1' AND fila_id = ? ORDER BY id DESC "
        "LIMIT 1", (v201,))] == ["ok"]
    # Lo escribio el motor, con la importacion del planning como fuente.
    evento = conn.execute("SELECT e.tipo, u.nombre FROM evento AS e JOIN usuario AS u "
                          "ON u.id = e.actor WHERE e.tipo = 'conciliacion_sincronizada'"
                          ).fetchone()
    assert tuple(evento) == ("conciliacion_sincronizada", "motor")
    with pytest.raises(sqlite3.DatabaseError, match="controlada"):
        conn.execute("UPDATE conciliacion SET horas_mil = 1")
    _limpio(conn)


def test_si_cambia_la_imputacion_la_conciliacion_se_retira_y_se_rehace(maestros,
                                                                      tmp_path) -> None:
    conn = maestros.conn
    _planning(maestros)
    _importar_venta(maestros, _venta(tmp_path))
    v201 = factura_de(conn, "V2026-0201")
    imputacion = conn.execute("SELECT id, rev FROM factura_imputacion WHERE factura_id = ? "
                              "AND retirada_en IS NULL", (v201,)).fetchone()
    waalhaven = conn.execute("SELECT id FROM objeto WHERE codigo = 'Waalhaven'").fetchone()[0]
    servicios.ejecutar(conn, "cambiar_objeto", {
        "imputacion_id": imputacion["id"], "objeto_id": waalhaven, "recurso_id": None,
        "rev": imputacion["rev"], "motivo": MOTIVO}, usuario_id=_ana(conn))
    assert [c[0] for c in _conciliacion(conn, v201, activas=False)] == ["D-2026-104211",
                                                                        "D-2026-104212"]
    assert [c[0] for c in _conciliacion(conn, v201)] == ["D-2026-104213"]
    _limpio(conn)


def test_una_foto_nueva_que_cambia_una_semana_facturada_da_v9(maestros, tmp_path) -> None:
    conn = maestros.conn
    _planning(maestros)
    _importar_venta(maestros, _venta(tmp_path))
    v201 = factura_de(conn, "V2026-0201")
    assert _abiertos(conn, "V9") == []
    ruta = _cambiado(tmp_path, ("Jan Bakker;20004;Objectbeveiliging;Nacht;;7,50;7,50",
                                "Jan Bakker;20004;Objectbeveiliging;Nacht;;6,50;6,50"))
    [lote] = _planning(maestros, ruta).lotes
    assert lote.estado == "aceptada"
    [v9] = _abiertos(conn, "V9")
    assert v9["fila_id"] == v201 and v9["severidad"] == "retencion"
    assert "otras horas" in v9["detalle"] and "15 h entonces, 14 h ahora" in v9["detalle"]
    # Lo conciliado no se toca: sigue apuntando a los turnos de la primera foto.
    assert {c[3] for c in _conciliacion(conn, v201)} == {7}
    # Y con las horas de ahora la factura tampoco cuadra (V1).
    assert [h["fila_id"] for h in _abiertos(conn, "V1")] == [v201]
    _limpio(conn)


def test_con_el_planning_pasado_de_su_frescura_no_se_concilia(maestros, tmp_path) -> None:
    from datetime import datetime, timezone

    conn = maestros.conn
    importar_fichero(maestros, "trnsprnt", "planning", PLANNING, lanzado_por=_ana(conn),
                     exportado_en=datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
    _importar_venta(maestros, _venta(tmp_path))
    v201 = factura_de(conn, "V2026-0201")
    assert _conciliacion(conn, v201) == []
    [r] = conn.execute("SELECT resultado, detalle FROM evaluacion WHERE regla = 'V1' "
                       "AND fila_id = ? ORDER BY id DESC LIMIT 1", (v201,)).fetchall()
    assert r["resultado"] == "sin_datos" and "frescura" in r["detalle"]


# ============================================================ lo que no se ha facturado

def test_el_trabajo_sin_facturar_de_agosto_es_v6_del_cliente(maestros, tmp_path) -> None:
    conn = maestros.conn
    ruta = _cambiado(tmp_path, *((f"{d}-10-2026", f"{d - 7:02d}-08-2026")
                                 for d in (12, 13, 17, 18, 19, 20)))
    [lote] = _planning(maestros, ruta).lotes
    assert lote.estado == "aceptada"
    haven = conn.execute("SELECT id FROM cliente WHERE exact_id = '10001'").fetchone()[0]
    v6 = _abiertos(conn, "V6", "cliente")
    assert {h["fila_id"] for h in v6} == {haven}
    rijnhaven = [h for h in v6 if '"desde":"2026-08-01"' in h["valores_json"]
                 and f'"objeto":{_objeto(conn, "Rijnhaven")}' in h["valores_json"]]
    assert rijnhaven, [h["valores_json"] for h in v6]
    assert "estimado" in rijnhaven[0]["detalle"]
    # La prioridad del cliente lo cuenta (trabajo sin facturar, con semanas tras la gracia).
    prioridad = conn.execute("SELECT nivel, motivos_json FROM prioridad WHERE entidad = "
                             "'cliente' AND entidad_id = ?", (haven,)).fetchone()
    assert prioridad is not None and "trabajo sin facturar" in prioridad["motivos_json"]
    vista = consultas.cliente(conn, haven)["trabajo_sin_facturar"]
    assert vista["estado"] == "ok" and vista["horas_mil"] > 0 and vista["estimado"]
    _limpio(conn)


def _objeto(conn, codigo: str) -> int:
    return conn.execute("SELECT id FROM objeto WHERE codigo = ?", (codigo,)).fetchone()[0]


# ============================================================ las vistas

def test_sin_planning_las_vistas_dicen_sin_datos(maestros, tmp_path) -> None:
    conn = maestros.conn
    _importar_venta(maestros, _venta(tmp_path))
    haven = conn.execute("SELECT id FROM cliente WHERE exact_id = '10001'").fetchone()[0]
    assert consultas.cliente(conn, haven)["trabajo_sin_facturar"]["estado"] == "sin_datos"
    horas = consultas.objeto(conn, _objeto(conn, "Rijnhaven"))["horas"]
    assert horas["planning"] == "sin_datos"
    assert horas["total"]["planificadas_mil"] is None and horas["total"]["cliente_mil"] == 15000
    assert horas["esperado"]["entrante_estimado_cent"] is None
    estimado = flujo_caja.flujo(conn, date(2026, 10, 14))["estimado"]
    assert estimado["importe_cent"] is None and "planning" in estimado["nota"]
    # Un sin_datos por regla, del planning entero (no uno por factura).
    filas = conn.execute("SELECT regla, tabla, fila_id, resultado FROM evaluacion "
                         "WHERE regla IN ('G2', 'V1', 'V9') ORDER BY regla").fetchall()
    assert [tuple(f) for f in filas] == [("G2", "planning", 0, "sin_datos"),
                                         ("V1", "planning", 0, "sin_datos"),
                                         ("V9", "planning", 0, "sin_datos")]


def test_las_horas_del_objeto_y_el_estimado_salen_del_planning(maestros, tmp_path) -> None:
    conn = maestros.conn
    _planning(maestros)
    _importar_venta(maestros, _venta(tmp_path, horas="7,5"))
    horas = consultas.objeto(conn, _objeto(conn, "Rijnhaven"))["horas"]
    assert horas["planning"] == "ok"
    [w42, w43] = horas["semanas"]
    assert (w42["semana"], w42["validadas_mil"], w42["facturables_mil"], w42["cliente_mil"],
            w42["sin_facturar_mil"], w42["diferencia_cliente_mil"]) == (
        "2026-W42", 15000, 15000, 7500, 7500, -7500)
    # La semana 43 no ha empezado: no hay nada sin facturar todavia.
    assert w43["semana"] == "2026-W43" and w43["sin_facturar_mil"] is None
    # Lo que falta de la semana 42 (la noche de 7,5 h a 59,80) va aparte, como estimado.
    assert horas["esperado"]["entrante_estimado_cent"] == 44850
    assert horas["esperado"]["entrante_cent"] > 0       # la venta abierta, con su IVA
    estimado = flujo_caja.flujo(conn, date(2026, 10, 14))["estimado"]
    assert estimado["entrada_sin_facturar_cent"] == 44850
    assert estimado["importe_cent"] == estimado["entrada_sin_facturar_cent"] + estimado[
        "entrada_planificada_cent"] - estimado["salida_sin_facturar_cent"] - estimado[
        "salida_planificada_cent"]
    assert "Estimado" in estimado["nota"]


def test_la_cli_importa_el_planning_y_ensena_las_horas_del_objeto(tmp_path, capsys) -> None:
    from bms_agent import permisos
    from bms_agent.almacen import preparar
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    with preparar(db) as almacen:
        ana = persona(almacen.conn, "Ana", "administrador")
        token = permisos.emitir_token(almacen.conn, ana)
    for fuente, tipo, nombre in (("exact", "clientes", "exact-clientes-v1.csv"),
                                 ("maestro_csv", "objetos", "maestro_csv-objetos-v1.csv")):
        main(["importar", fuente, tipo, str(IMPORTACION / nombre), "--token", token,
              "--db", str(db)])
    capsys.readouterr()
    assert main(["importar", "exact", "planning", str(PLANNING), "--desde", "2026-10-12",
                 "--token", token, "--db", str(db)]) == 1
    assert "solo valen para el planning" in capsys.readouterr().err
    assert main(["importar", "trnsprnt", "planning", str(PLANNING), "--desde", "2026-10-12",
                 "--hasta", "2026-10-25", "--token", token, "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    assert "planning: aceptada; 7 filas, 7 aceptadas" in salida
    assert "clave sintetica" in salida
    with preparar(db) as almacen:
        rijnhaven = _objeto(almacen.conn, "Rijnhaven")
    assert main(["objeto", str(rijnhaven), "--db", str(db)]) == 0
    salida = capsys.readouterr().out
    assert "2026-W42" in salida and "total" in salida


def test_el_dominio_del_planning_es_el_de_la_base(db) -> None:
    import re

    from bms_agent import dominio

    def check(tabla: str, columna: str) -> set[str]:
        sql = db.execute("SELECT sql FROM sqlite_master WHERE name = ?", (tabla,)).fetchone()[0]
        lista = re.search(rf"CHECK \({columna} IN \(([^)]*)\)", sql).group(1)
        return {v.strip().strip("'") for v in lista.replace("\n", " ").split(",")}

    assert set(dominio.EstadoTurno.valores()) == check("planning_turno", "estado")
    assert set(dominio.NivelTurno.valores()) == check("planning_turno", "nivel")
    assert set(dominio.MetodoConciliacion.valores()) == check("conciliacion", "metodo")
    assert set(dominio.NivelConciliacion.valores()) == check("conciliacion", "regla")
    # Validado, no aprobado: el sistema no aprueba nada (test_alcance_v1).
    assert "aprobado" not in dominio.EstadoTurno.valores()
