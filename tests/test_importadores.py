"""Los importadores de maestros (paso 5): contratos, registrar_lote y la orden de importar.

- Cada mapeo de config/importacion tiene su fichero de ejemplo anonimizado y
  su JSON esperado: leerlo tiene que dar ese JSON, campo a campo (el test de
  contrato). La semilla de config/tarifas.yaml, igual.
- registrar_lote es el unico escritor: repetir un fichero no hace nada,
  simular no escribe nada, las cuentas entran enteras o ninguna, un valor
  puesto a mano no se pisa (M1), nada se crea solo (Z2), lo que no esta en
  euros no entra (X1) y ninguna importacion escribe un estado decidido.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from conftest import RAIZ, TARIFAS_V1, persona
from pydantic import ValidationError

from bms_agent import campos
from bms_agent.almacen import transaccion, usuario_sistema
from bms_agent.campos import Persona
from bms_agent.importadores.canonico import CuentaBancariaCanonica
from bms_agent.importadores.registrar import importar_fichero
from bms_agent.importadores.tabular import (
    LectorTabular,
    MapeoNoValido,
    contrato,
    mapeo_de_yaml,
    mapeos,
)
from bms_agent.importadores.tarifas import contrato_semilla
from bms_agent.permisos import PermisoDenegado

FIXTURES = RAIZ / "tests" / "fixtures" / "importacion"
CONFIG = RAIZ / "config" / "importacion"
MAPEOS = mapeos(CONFIG)
EXACT_PROVEEDORES = FIXTURES / "exact-proveedores-v1.csv"
EXACT_CLIENTES = FIXTURES / "exact-clientes-v1.csv"


def _fichero(mapeo_id: str):
    return FIXTURES / f"{mapeo_id}.csv"


def _contenido_de(conn) -> dict[str, list[tuple]]:
    """Cada fila de cada tabla: para ver que algo no escribio nada."""
    tablas = [f[0] for f in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name")]
    return {t: [tuple(f) for f in conn.execute(f"SELECT * FROM {t} ORDER BY rowid")]
            for t in tablas}


def _variante(tmp_path, nombre: str, origen, cambios: dict[str, str]):
    """Una copia del fichero de ejemplo con unas lineas cambiadas (en utf-8 con BOM, como Exact)."""
    texto = origen.read_bytes().decode("utf-8-sig")
    for viejo, nuevo in cambios.items():
        assert viejo in texto, viejo
        texto = texto.replace(viejo, nuevo)
    ruta = tmp_path / nombre
    ruta.write_bytes(("﻿" + texto).encode("utf-8"))
    return ruta


def _abiertos(conn, regla: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM hallazgo WHERE regla = ? AND estado = 'abierto' "
                        "ORDER BY id", (regla,)).fetchall()


@pytest.fixture
def ana(almacen) -> int:
    return persona(almacen.conn, "Ana", "administracion")


# ------------------------------------------------------------ contratos

@pytest.mark.parametrize("mapeo", MAPEOS, ids=lambda m: m.id)
def test_cada_mapeo_lee_su_ejemplo_como_dice_su_contrato(mapeo) -> None:
    esperado = json.loads((FIXTURES / f"{mapeo.id}.esperado.json").read_text(encoding="utf-8"))
    assert contrato(mapeo, _fichero(mapeo.id).read_bytes()) == esperado


def test_cada_mapeo_tiene_su_ejemplo_y_su_contrato() -> None:
    ids = {m.id for m in MAPEOS}
    assert {p.stem for p in FIXTURES.glob("*.csv")} == ids
    assert {p.name.removesuffix(".esperado.json") for p in FIXTURES.glob("*.esperado.json")} == (
        ids | {"config-tarifas"})
    assert {(m.fuente, m.tipo) for m in MAPEOS} == {
        ("exact", "proveedores"), ("exact", "clientes"), ("maestro_csv", "objetos"),
        ("maestro_csv", "recursos"), ("maestro_csv", "alias"), ("maestro_csv", "tarifas"),
        ("maestro_csv", "ciclos"), ("maestro_csv", "contactos"),
        # Paso 7: lo pagado segun Exact y los CSV de movimientos de ING y Rabobank.
        ("exact", "pagos_exact"), ("banco", "extracto"),
        # Paso 8: las facturas de venta de Exact, con sus lineas.
        ("exact", "facturas_venta")}


def test_la_semilla_de_tarifas_lee_como_dice_su_contrato() -> None:
    esperado = json.loads((FIXTURES / "config-tarifas.esperado.json").read_text(encoding="utf-8"))
    assert contrato_semilla(TARIFAS_V1.read_text(encoding="utf-8")) == esperado


@pytest.mark.parametrize("mapeo", MAPEOS, ids=lambda m: m.id)
def test_cada_lector_reconoce_su_formato_por_la_cabecera_y_no_otro(mapeo) -> None:
    lector = LectorTabular(mapeo, mapeo.registros[0].tipo)
    assert lector.reconoce(_fichero(mapeo.id).read_bytes())
    for otro in MAPEOS:
        if otro.id != mapeo.id:
            assert not lector.reconoce(_fichero(otro.id).read_bytes()), otro.id


def test_la_codificacion_y_los_numeros_de_cada_fichero() -> None:
    """Exact exporta en utf-8 con BOM; la hoja de Objetos en cp1252. Coma decimal."""
    objetos = contrato(next(m for m in MAPEOS if m.id == "maestro_csv-objetos-v1"),
                       _fichero("maestro_csv-objetos-v1").read_bytes())
    assert "IJsselmonde Café" in [r["nombre"] for r in objetos["lotes"][0]["registros"]]
    proveedores = contrato(next(m for m in MAPEOS if m.id == "exact-proveedores-v1"),
                           EXACT_PROVEEDORES.read_bytes())
    [lote, cuentas] = proveedores["lotes"]
    assert lote["registros"][0]["crudo"]["Crediteurnummer"] == "20001"     # sin el BOM
    assert lote["registros"][0]["plazo_pago_dias"] == 30                  # "30 dagen"
    assert lote["registros"][0]["direccion"] == "Havenstraat 12, 3011 AA, Rotterdam"
    assert cuentas["completo"] is True
    assert [c["iban"] for c in cuentas["registros"]][0] == "NL02ABNA0123456789"


def test_ningun_mapeo_puede_leer_un_estado_de_cuenta() -> None:
    """El registro canonico de una cuenta no tiene estado: ni un mapeo ni una fila lo traen."""
    with pytest.raises(MapeoNoValido, match="estado"):
        mapeo_de_yaml("""
version: 1
fuente: exact
tipo: proveedores
formato: "csv:malo"
lectura: {codificaciones: [utf-8]}
cabecera: [IBAN]
registros:
  cuentas:
    fijos: {titular: proveedor}
    campos:
      parte_ref: {columna: Crediteurnummer}
      iban: {columna: IBAN}
      estado: {columna: Status}
""", "malo")
    with pytest.raises(ValidationError, match="estado"):
        CuentaBancariaCanonica(fila=2, crudo={}, titular="proveedor", parte_ref="20001",
                               iban="NL02ABNA0123456789", estado="verificada")
    with pytest.raises(ValidationError, match="modulo 97"):
        CuentaBancariaCanonica(fila=2, crudo={}, titular="proveedor", parte_ref="20001",
                               iban="NL02ABNA0123456788")


# ------------------------------------------------------------ registrar: el maestro de Exact

def test_el_primer_maestro_de_exact_da_las_cuentas_de_partida(almacen, ana) -> None:
    conn = almacen.conn
    r = importar_fichero(almacen, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana)
    proveedores, cuentas_ = r.lotes
    assert (proveedores.tipo, proveedores.estado, proveedores.aceptadas) == ("proveedores",
                                                                            "parcial", 6)
    assert [(x.fila, x.codigo) for x in proveedores.rechazos] == [(8, "fila")]
    assert (cuentas_.tipo, cuentas_.estado, cuentas_.aceptadas) == ("cuentas", "aceptada", 5)
    assert cuentas_.cuentas[0].baseline and len(cuentas_.cuentas[0].nuevas) == 5
    # Cada proveedor por su numero de Exact, con la procedencia de su importacion.
    van_dijk = conn.execute("SELECT * FROM proveedor WHERE exact_id = '20001'").fetchone()
    assert (van_dijk["nombre"], van_dijk["regimen_iva"], van_dijk["telefono_verificacion"]) == (
        "Bouwtechniek Van Dijk BV", "estandar", "010-1234567")
    procedencia = conn.execute(
        "SELECT fuente, fuente_ref FROM procedencia_campo WHERE tabla = 'proveedor' AND "
        "fila_id = ? AND campo = 'nombre'", (van_dijk["id"],)).fetchone()
    assert tuple(procedencia) == ("importacion", f"importacion:{proveedores.importacion_id}")
    # Las cuentas: heredadas del primer maestro, ninguna decidida por nadie.
    assert {f["primera_fuente"] for f in conn.execute("SELECT * FROM cuenta_bancaria")} == {
        "baseline"}
    tipos = [f["tipo"] for f in conn.execute("SELECT tipo FROM cuenta_evento ORDER BY id")]
    assert sorted(set(tipos)) == ["baseline", "visto_en_exact"] and len(tipos) == 10
    assert conn.execute("SELECT count(*) FROM cuenta_evento WHERE usuario_id IS NOT NULL"
                        ).fetchone()[0] == 0
    # Quien: el importador lo ejecuta y Ana lo lanza.
    evento = conn.execute("SELECT * FROM evento WHERE tipo = 'cuentas_del_maestro'").fetchone()
    assert (evento["actor"], evento["usuario_id"]) == (usuario_sistema(conn, "importador"), ana)
    # Una sola tarea de atencion para atestarlas (F0), y la fila rechazada retiene (Z2).
    [f0] = _abiertos(conn, "F0")
    assert (f0["tabla"], f0["fila_id"]) == ("importacion", cuentas_.importacion_id)
    assert [z["fila_id"] for z in _abiertos(conn, "Z2")] == [proveedores.importacion_id]
    assert campos.verificar_controladas(conn) == []


def test_importar_otra_vez_el_mismo_fichero_no_hace_nada(almacen, ana) -> None:
    conn = almacen.conn
    importar_fichero(almacen, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana)
    antes = _contenido_de(conn)
    r = importar_fichero(almacen, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana)
    assert [x.repetida for x in r.lotes] == [True, True] and r.recalculo is None
    assert _contenido_de(conn) == antes


def test_simular_lo_hace_todo_y_no_escribe_nada(almacen, ana, tmp_path) -> None:
    conn = almacen.conn
    antes = _contenido_de(conn)
    r = importar_fichero(almacen, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana,
                         simular=True)
    assert r.simulada and [x.simulada for x in r.lotes] == [True, True]
    assert len(r.lotes[0].nuevos) > 0 and r.lotes[1].cuentas[0].baseline
    assert _contenido_de(conn) == antes
    assert not list(tmp_path.glob("documentos/**/*.csv"))


def test_las_cuentas_entran_enteras_o_ninguna(almacen, ana, tmp_path) -> None:
    """Una cuenta de un proveedor rechazado tumba todas: una foto a medias del maestro
    haria pasar por retiradas las que faltan. Los proveedores entran fila a fila."""
    conn = almacen.conn
    ruta = _variante(tmp_path, "acreedores.csv", EXACT_PROVEEDORES, {
        "Bouwbedrijf Onbekend;Bedrijf;;NL006666666B01;XX;30;;;;;;Actief;;":
        "Bouwbedrijf Onbekend;Bedrijf;;NL006666666B01;XX;30;;;;;;Actief;NL91ABNA0417164300;X"})
    r = importar_fichero(almacen, "exact", "proveedores", ruta, lanzado_por=ana)
    proveedores, cuentas_ = r.lotes
    assert proveedores.estado == "parcial" and cuentas_.estado == "rechazada"
    assert [(x.fila, x.codigo) for x in cuentas_.rechazos] == [(8, "referencia")]
    assert conn.execute("SELECT count(*) FROM cuenta_bancaria").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM proveedor").fetchone()[0] == 6
    # Un IBAN que no pasa el modulo 97 tambien: ninguna cuenta entra.
    mal = _variante(tmp_path, "acreedores-2.csv", EXACT_PROVEEDORES,
                    {"NL44RABO0123456789": "NL44RABO0123456788"})
    r = importar_fichero(almacen, "exact", "proveedores", mal, lanzado_por=ana)
    assert r.lotes[1].estado == "rechazada"
    assert conn.execute("SELECT count(*) FROM cuenta_bancaria").fetchone()[0] == 0


def test_quien_falta_en_la_foto_completa_queda_inactivo_y_vuelve_si_reaparece(almacen, ana,
                                                                              tmp_path) -> None:
    conn = almacen.conn
    sin_rechazos = {"20007;Bouwbedrijf Onbekend;Bedrijf;;NL006666666B01;XX;30;;;;;;Actief;;\r\n": ""}
    entera = _variante(tmp_path, "a.csv", EXACT_PROVEEDORES, sin_rechazos)
    importar_fichero(almacen, "exact", "proveedores", entera, lanzado_por=ana)
    smit = conn.execute("SELECT id FROM proveedor WHERE exact_id = '20005'").fetchone()[0]
    sin_smit = _variante(tmp_path, "b.csv", EXACT_PROVEEDORES, {
        **sin_rechazos,
        "20005;Loodgietersbedrijf Smit;Bedrijf;54321098;NL005678912B01;VH21;30;;;Leiden;;"
        "071-5556667;Actief;;\r\n": ""})
    r = importar_fichero(almacen, "exact", "proveedores", sin_smit, lanzado_por=ana)
    assert r.lotes[0].retirados == [("proveedor", smit)]
    assert conn.execute("SELECT activo FROM proveedor WHERE id = ?", (smit,)).fetchone()[0] == 0
    # Con una fila rechazada la foto no esta entera: nadie se retira.
    r = importar_fichero(almacen, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana)
    assert r.lotes[0].retirados == [] and r.lotes[0].avisos
    assert conn.execute("SELECT activo FROM proveedor WHERE id = ?", (smit,)).fetchone()[0] == 1
    assert campos.verificar_controladas(conn) == []


def test_un_valor_puesto_a_mano_no_lo_pisa_la_importacion(almacen, ana) -> None:
    """M1: el valor de la importacion queda como automatico y el campo, sin resolver."""
    conn = almacen.conn
    admin = persona(conn, "Bea", "administrador")
    proveedor = campos.crear(conn, "proveedor", {
        "nombre": "Bouwtechniek Van Dijk BV", "btw_id": "NL001234567B01",
        "email_facturacion": "boekhouding@vandijk.example"}, Persona(admin))
    r = importar_fichero(almacen, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana)
    assert ("proveedor", proveedor, "email_facturacion") in r.lotes[0].sin_resolver
    fila = conn.execute("SELECT * FROM proveedor WHERE id = ?", (proveedor,)).fetchone()
    assert fila["email_facturacion"] == "boekhouding@vandijk.example"
    assert fila["exact_id"] == "20001"                        # adoptado, no duplicado
    procedencia = conn.execute(
        "SELECT * FROM procedencia_campo WHERE tabla = 'proveedor' AND fila_id = ? AND "
        "campo = 'email_facturacion'", (proveedor,)).fetchone()
    assert procedencia["fuente"] == "manual_entrada"
    assert json.loads(procedencia["valor_automatico"]) == "facturen@vandijk.example"


def test_quien_no_tiene_importar_datos_no_importa(almacen) -> None:
    conn = almacen.conn
    dora = persona(conn, "Dora", "consulta")
    antes = conn.execute("SELECT count(*) FROM importacion").fetchone()[0]
    with pytest.raises(PermisoDenegado):
        importar_fichero(almacen, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=dora)
    assert conn.execute("SELECT count(*) FROM importacion").fetchone()[0] == antes


def test_ni_el_importador_ni_nadie_sin_confirmar_iban_escribe_una_cuenta_verificada(
        almacen, ana) -> None:
    """Aunque alguien se salte el codigo: la base no admite del importador ningun estado."""
    conn = almacen.conn
    importar_fichero(almacen, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana)
    cuenta = conn.execute("SELECT id FROM cuenta_bancaria ORDER BY id").fetchone()[0]
    importador = usuario_sistema(conn, "importador")
    for usuario in (importador, None):
        with pytest.raises(sqlite3.IntegrityError):
            with transaccion(conn):
                conn.execute(
                    "INSERT INTO cuenta_evento (cuenta_id, tipo, metodo, telefono_usado, "
                    "usuario_id, en, evento_id) VALUES (?, 'verificada', 'llamada', "
                    "'0101234567', ?, '2026-10-14T09:30:00+00:00', (SELECT max(id) FROM evento))",
                    (cuenta, usuario))
    # Y ni la propia importacion puede dar de alta una cuenta fuera de su curso.
    with pytest.raises(sqlite3.IntegrityError):
        with transaccion(conn):
            conn.execute(
                "INSERT INTO cuenta_bancaria (titular, proveedor_id, iban, primera_vez_en, "
                "primera_fuente, importacion_id, evento_id) VALUES ('proveedor', 1, "
                "'NL91ABNA0417164300', '2026-10-14T09:30:00+00:00', 'maestro_exact', 1, "
                "(SELECT max(id) FROM evento))")


# ------------------------------------------------------------ los demas maestros

def _maestros_base(almacen, ana) -> None:
    importar_fichero(almacen, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana)
    importar_fichero(almacen, "exact", "clientes", EXACT_CLIENTES, lanzado_por=ana)


def test_una_referencia_desconocida_rechaza_la_fila_y_no_crea_nada(almacen, ana) -> None:
    conn = almacen.conn
    _maestros_base(almacen, ana)
    clientes = conn.execute("SELECT count(*) FROM cliente").fetchone()[0]
    r = importar_fichero(almacen, "maestro_csv", "objetos", _fichero("maestro_csv-objetos-v1"),
                         lanzado_por=ana)
    [lote] = r.lotes
    assert lote.estado == "parcial"
    assert {(x.fila, x.codigo) for x in lote.rechazos} == {(5, "referencia"), (6, "fila")}
    assert conn.execute("SELECT count(*) FROM cliente").fetchone()[0] == clientes
    assert [f[0] for f in conn.execute("SELECT codigo FROM objeto ORDER BY codigo")] == [
        "Rijnhaven", "Schiedam", "Waalhaven"]
    [z2] = [z for z in _abiertos(conn, "Z2") if z["fila_id"] == lote.importacion_id]
    assert {tuple(f[:2]) for f in json.loads(z2["valores_json"])["filas"]} == {
        (5, "referencia"), (6, "fila")}


def test_una_tarifa_en_otra_moneda_no_entra_y_la_importacion_queda_bloqueada(almacen,
                                                                             ana) -> None:
    conn = almacen.conn
    _maestros_base(almacen, ana)
    importar_fichero(almacen, "maestro_csv", "objetos", _fichero("maestro_csv-objetos-v1"),
                     lanzado_por=ana)
    r = importar_fichero(almacen, "maestro_csv", "tarifas", _fichero("maestro_csv-tarifas-v1"),
                         lanzado_por=ana)
    [lote] = r.lotes
    assert "X1" in {x.codigo for x in lote.rechazos}
    assert conn.execute("SELECT count(*) FROM tarifa_acordada WHERE fuente = 'maestro'"
                        ).fetchone()[0] == lote.aceptadas > 0
    [x1] = [h for h in _abiertos(conn, "X1") if h["tabla"] == "importacion"]
    assert (x1["fila_id"], x1["severidad"], x1["pegajosa"], x1["anulable"]) == (
        lote.importacion_id, "bloqueo", 1, 0)


@pytest.mark.parametrize("mapeo_id, tabla", [
    ("maestro_csv-recursos-v1", "recurso"), ("maestro_csv-alias-v1", "alias"),
    ("maestro_csv-ciclos-v1", "ciclo_facturacion"), ("maestro_csv-contactos-v1", "contacto")])
def test_recursos_alias_y_ciclos_entran_fila_a_fila(almacen, ana, mapeo_id, tabla) -> None:
    conn = almacen.conn
    _maestros_base(almacen, ana)
    for previo in ("maestro_csv-objetos-v1", "maestro_csv-recursos-v1"):
        if previo != mapeo_id:
            importar_fichero(almacen, "maestro_csv", previo.split("-")[1], _fichero(previo),
                             lanzado_por=ana)
    antes = conn.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0]
    r = importar_fichero(almacen, "maestro_csv", mapeo_id.split("-")[1], _fichero(mapeo_id),
                         lanzado_por=ana)
    [lote] = r.lotes
    assert lote.estado == "parcial" and lote.aceptadas > 0
    assert conn.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0] > antes
    assert campos.verificar_controladas(conn) == []


# ------------------------------------------------------------ por la CLI

def test_importar_y_ver_el_registro_por_la_cli(tmp_path, capsys) -> None:
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["db", "init", "--db", str(db)]) == 0
    assert main(["usuario", "crear", "Ana", "--rol", "administracion", "--db", str(db)]) == 0
    capsys.readouterr()
    assert main(["usuario", "token", "Ana", "--db", str(db)]) == 0
    token = capsys.readouterr().out.splitlines()[1].strip()
    base = ["importar", "exact", "proveedores", str(EXACT_PROVEEDORES), "--db", str(db),
            "--exportado", "2026-10-13"]
    assert main([*base, "--simular", "--token", token]) == 0
    assert "simulado: no se ha escrito nada" in capsys.readouterr().out
    assert main(base) == 1                                      # sin token, nada
    assert "token" in capsys.readouterr().err
    assert main([*base, "--token", token]) == 0
    salida = capsys.readouterr().out
    assert "cuentas: 5 en el fichero, 5 nuevas" in salida and "heredadas" in salida
    assert main([*base, "--token", token]) == 0
    assert "ya importado" in capsys.readouterr().out
    assert main(["iban", "listar", "--db", str(db)]) == 0
    listado = capsys.readouterr().out
    assert "NL02ABNA0123456789" in listado and "heredada" in listado
    # La tarea de F0 por la CLI: atestar todo lo heredado, con el token de la persona.
    assert main(["iban", "atestar", "--motivo", "Comprobadas con los pagos de 2025",
                 "--db", str(db)]) == 1
    capsys.readouterr()
    assert main(["iban", "atestar", "--motivo", "Comprobadas con los pagos de 2025",
                 "--db", str(db), "--token", token]) == 0
    assert "F0 (resuelto)" in capsys.readouterr().out
    assert main(["iban", "listar", "--db", str(db)]) == 0
    assert "heredada" not in capsys.readouterr().out
    assert main(["fuentes", "--db", str(db)]) == 0
    assert "exact" in capsys.readouterr().out
    assert main(["db", "verificar", "--db", str(db)]) == 0


# ------------------------------------------------------------ correcciones de la revision

def _mapeo(mapeo_id: str):
    return next(m for m in MAPEOS if m.id == mapeo_id)


@pytest.mark.parametrize("texto", ["42.50", "1.5", "45.5 EUR", "1.0745", "12,34,56", "1.074.5",
                                   "1,074.00"])
def test_un_importe_que_no_tiene_la_forma_del_mapeo_se_rechaza(texto) -> None:
    """Con coma decimal y punto de miles, "42.50" no son 4250 euros: no se lee."""
    from bms_agent.importadores.tabular import ValorNoValido, _decimal

    with pytest.raises(ValorNoValido):
        _decimal(texto, _mapeo("maestro_csv-tarifas-v1"))


@pytest.mark.parametrize("texto, valor", [("1.074,00", "1074.00"), ("42,50", "42.50"),
                                          ("1.000", "1000"), ("1074", "1074"),
                                          ("-12,5", "-12.5"), ("€ 1.234.567,89", "1234567.89"),
                                          ("45,50 EUR", "45.50")])
def test_un_importe_con_la_forma_del_mapeo_se_lee(texto, valor) -> None:
    from decimal import Decimal

    from bms_agent.importadores.tabular import _decimal

    assert _decimal(texto, _mapeo("maestro_csv-tarifas-v1")) == Decimal(valor)


@pytest.mark.parametrize("texto", ["2,5", "1.000", "30/60", "14 of 30", "dagen"])
def test_un_entero_tiene_que_ser_un_entero_entero(texto) -> None:
    from bms_agent.importadores.tabular import Campo, ValorNoValido, _convertir

    campo = Campo("plazo_pago_dias", columna="x", tipo="entero")
    with pytest.raises(ValorNoValido):
        _convertir(texto, campo, _mapeo("exact-proveedores-v1"))


@pytest.mark.parametrize("texto, valor", [("30", 30), ("30 dagen", 30), ("14 dagen netto", 14),
                                          (" 21 ", 21)])
def test_un_entero_con_su_unidad_se_lee(texto, valor) -> None:
    from bms_agent.importadores.tabular import Campo, _convertir

    campo = Campo("plazo_pago_dias", columna="x", tipo="entero")
    assert _convertir(texto, campo, _mapeo("exact-proveedores-v1")) == valor


def test_una_fecha_de_exportacion_futura_no_se_admite(almacen, ana, reloj) -> None:
    """Un fichero que dice ser de manana haria que Exact no caducase nunca (Z1)."""
    from datetime import timedelta

    conn = almacen.conn
    antes = _contenido_de(conn)
    with pytest.raises(ValueError, match="futuro"):
        importar_fichero(almacen, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana,
                         exportado_en=reloj.ahora() + timedelta(days=1))
    assert _contenido_de(conn) == antes
    # El mismo dia si (la CLI pone las doce del dia que se le dice).
    r = importar_fichero(almacen, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana,
                         exportado_en=reloj.ahora() + timedelta(hours=3))
    assert r.lotes[0].importacion_id is not None and not r.lotes[0].repetida


def test_cada_mapeo_usado_queda_en_la_politica(almacen, ana) -> None:
    from bms_agent import politica

    conn = almacen.conn
    importar_fichero(almacen, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana)
    fila = politica.vigente(conn, "importacion/exact-proveedores-v1.yaml")
    texto = (CONFIG / "exact-proveedores-v1.yaml").read_text(encoding="utf-8")
    assert fila is not None and fila["contenido"] == texto
    sha = conn.execute("SELECT DISTINCT mapeo_sha256 FROM importacion WHERE fuente = 'exact'"
                       ).fetchall()
    assert [s[0] for s in sha] == [fila["sha256"]]
    # Otra importacion con el mismo mapeo no lo apunta otra vez.
    importar_fichero(almacen, "exact", "clientes", EXACT_CLIENTES, lanzado_por=ana)
    importar_fichero(almacen, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana)
    assert conn.execute("SELECT count(*) FROM politica_version WHERE fichero = ?",
                        ("importacion/exact-proveedores-v1.yaml",)).fetchone()[0] == 1


def test_los_contactos_entran_por_su_proveedor_o_su_cliente(almacen, ana, tmp_path) -> None:
    conn = almacen.conn
    _maestros_base(almacen, ana)
    r = importar_fichero(almacen, "maestro_csv", "contactos",
                         _fichero("maestro_csv-contactos-v1"), lanzado_por=ana)
    [lote] = r.lotes
    assert lote.estado == "parcial"
    assert {x.codigo for x in lote.rechazos} == {"referencia"}
    filas = conn.execute("SELECT c.nombre, p.exact_id, c.telefono FROM contacto AS c "
                         "LEFT JOIN proveedor AS p ON p.id = c.proveedor_id ORDER BY c.id"
                         ).fetchall()
    assert ("Marieke de Boer", "20001", "010-1234599") in [tuple(f) for f in filas]
    # El telefono de un contacto no es el de verificacion: ese no lo toca.
    assert conn.execute("SELECT telefono_verificacion FROM proveedor WHERE exact_id = '20001'"
                        ).fetchone()[0] == "010-1234567"
    # Otra vez el mismo contacto con otro correo: el mismo, cambiado.
    antes = conn.execute("SELECT count(*) FROM contacto").fetchone()[0]
    importar_fichero(almacen, "maestro_csv", "contactos",
                     _variante(tmp_path, "contactos-2.csv",
                               _fichero("maestro_csv-contactos-v1"),
                               {"m.deboer@vandijk.example": "marieke@vandijk.example"}),
                     lanzado_por=ana)
    assert conn.execute("SELECT count(*) FROM contacto").fetchone()[0] == antes
    assert conn.execute("SELECT email FROM contacto WHERE nombre = 'Marieke de Boer'"
                        ).fetchone()[0] == "marieke@vandijk.example"
    assert campos.verificar_controladas(conn) == []


def test_adoptar_una_fila_con_un_valor_por_defecto_deja_su_historia_entera(almacen, ana) -> None:
    """Un proveedor dado de alta a mano (activo por defecto) que Exact adopta por su btw-id:
    el mismo valor de otra fuente no es un cambio, y la procedencia sigue cuadrando con su
    historia (db verificar)."""
    conn = almacen.conn
    jefa = persona(conn, "Jefa", "administrador")
    campos.crear(conn, "proveedor", {"nombre": "Bouwtechniek Van Dijk BV",
                                     "btw_id": "NL001234567B01"}, Persona(jefa))
    importar_fichero(almacen, "exact", "proveedores", EXACT_PROVEEDORES, lanzado_por=ana)
    assert conn.execute("SELECT exact_id FROM proveedor WHERE btw_id = 'NL001234567B01'"
                        ).fetchone()[0] == "20001"
    assert campos.verificar_controladas(conn) == []
