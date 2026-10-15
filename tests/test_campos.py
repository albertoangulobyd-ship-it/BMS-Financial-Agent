"""campos.py: la unica via de escritura de las tablas controladas, y como decide cada campo.

La puerta del paso 2 que vive aqui:

- el valor original sobrevive a dos correcciones;
- el sistema, y no quien edita, decide entre suplir y corregir, y deshacer
  devuelve el campo a su fuente original;
- un valor automatico nunca pisa uno manual;
- una correccion sin motivo no entra;
- un UPDATE fuera de campos.py lo rechaza la guarda, y en el codigo no hay
  ninguno (test que lee los fuentes).
"""

from __future__ import annotations

import ast
import re
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from conftest import RAIZ, factura_de, persona

from bms_agent import campos
from bms_agent.almacen import abrir, usuario_sistema
from bms_agent.auditoria import historial, verificar_cadena
from bms_agent.campos import (
    Automatico,
    CampoDeOtroSistema,
    CampoNoEditable,
    Conflicto,
    FaltaMotivo,
    Leido,
    Persona,
)
from bms_agent.permisos import PermisoDenegado, SeparacionDeFunciones

FUENTES = RAIZ / "src" / "bms_agent"


def _p(conn, tabla, fila_id, campo):
    return campos.procedencia(conn, tabla, fila_id)[campo]


def _total(conn, factura_id):
    return conn.execute("SELECT total_cent FROM factura WHERE id = ?", (factura_id,)).fetchone()[0]


@pytest.fixture
def ana(tipado):
    return persona(tipado.conn, "Ana", "administracion")


# --- la puerta: como decide fijar ---

def test_el_original_sobrevive_a_dos_correcciones(tipado, ana) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    campos.fijar(conn, "factura", f, {"total_cent": Decimal("2902.80")}, Persona(ana, "lectura mala"))
    campos.fijar(conn, "factura", f, {"total_cent": Decimal("2902.81")}, Persona(ana, "otra vez"))

    p = _p(conn, "factura", f, "total_cent")
    assert _total(conn, f) == 290281
    assert (p["valor_actual"], p["fuente"]) == (290281, "manual_correccion")
    assert (p["valor_original"], p["valor_original_crudo"], p["fuente_original"]) == (
        290279, "2.902,79", "extraccion")
    cambios = [c for e in historial(conn, "factura", f) for c in e["cambios"]
               if c["campo"] == "total_cent"]
    assert [(c["valor_anterior"], c["valor_nuevo"], c["fuente_nueva"]) for c in cambios] == [
        ("null", "290279", "extraccion"), ("290279", "290280", "manual_correccion"),
        ("290280", "290281", "manual_correccion")]


def test_el_sistema_decide_entre_suplir_y_corregir(tipado, ana) -> None:
    """Quien edita no elige: lo que faltaba se suple, lo que habia se corrige."""
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    suplido = campos.fijar(conn, "factura", f, {"referencia_pago": "RF-1"}, Persona(ana))
    corregido = campos.fijar(conn, "factura", f, {"emisor_nombre_doc": "Van Dijk BV"},
                             Persona(ana, "nombre abreviado en el maestro"))
    assert suplido.de("factura", f, "referencia_pago").fuente == "manual_entrada"
    assert corregido.de("factura", f, "emisor_nombre_doc").fuente == "manual_correccion"
    # Una persona no puede pedir la fuente: campos.py no la acepta como automatica.
    with pytest.raises(ValueError, match="no es una fuente automatica"):
        Automatico("manual_entrada", ana)
    ediciones = conn.execute("SELECT * FROM v_factura_ediciones WHERE factura_id = ?", (f,)).fetchone()
    assert (ediciones["editada"], ediciones["suplementada"], ediciones["corregida"]) == (1, 1, 1)


def test_corregir_una_lectura_ilegible_es_corregir(tipado, ana) -> None:
    """Un literal que no se pudo leer es un original: rellenarlo es una correccion."""
    conn = tipado.conn
    f = factura_de(conn, "NW-2026-0042")       # en dolares: importes vacios con su literal
    assert _total(conn, f) is None
    with pytest.raises(FaltaMotivo):
        campos.fijar(conn, "factura", f, {"total_cent": Decimal("2300.00")}, Persona(ana))
    r = campos.fijar(conn, "factura", f, {"total_cent": Decimal("2300.00")}, Persona(ana, "en euros"))
    assert r.de("factura", f, "total_cent").fuente == "manual_correccion"


def test_deshacer_devuelve_la_fuente_original(tipado, ana) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    campos.fijar(conn, "factura", f, {"total_cent": Decimal("1")}, Persona(ana, "probando"))
    r = campos.fijar(conn, "factura", f, {"total_cent": Decimal("2902.79")}, Persona(ana, "deshacer"))
    p = _p(conn, "factura", f, "total_cent")
    assert r.de("factura", f, "total_cent").accion == "revertido"
    assert (p["fuente"], p["fuente_ref"], p["valor_actual"]) == ("extraccion", p["fuente_automatica_ref"], 290279)
    assert p["fuente_automatica_ref"].startswith("extraccion:")
    assert not campos.estado_campo(p).editado


def test_un_suplido_se_deshace_quitandolo(tipado, ana) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    campos.fijar(conn, "factura", f, {"referencia_pago": "RF-1"}, Persona(ana))
    with pytest.raises(FaltaMotivo):
        campos.fijar(conn, "factura", f, {"referencia_pago": None}, Persona(ana))
    campos.fijar(conn, "factura", f, {"referencia_pago": None}, Persona(ana, "no era suya"))
    p = _p(conn, "factura", f, "referencia_pago")
    assert (p["valor_actual"], p["fuente"]) == (None, "manual_entrada")


def test_un_valor_automatico_nunca_pisa_uno_manual(tipado, ana) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    campos.fijar(conn, "factura", f, {"total_cent": Decimal("2902.80")}, Persona(ana, "lectura mala"))
    extractor = usuario_sistema(conn, "extractor")
    r = campos.fijar(conn, "factura", f, {"total_cent": Leido(Decimal("3000.00"), crudo="3.000,00")},
                     Automatico("extraccion", extractor, ref="extraccion:99"))

    efecto = r.de("factura", f, "total_cent")
    assert (efecto.accion, efecto.discrepancia) == ("solo_automatico", True)
    p = _p(conn, "factura", f, "total_cent")
    assert _total(conn, f) == 290280 and p["fuente"] == "manual_correccion"
    assert (p["valor_automatico"], p["fuente_automatica_ref"]) == (300000, "extraccion:99")
    assert campos.estado_campo(p).sin_resolver          # M1
    assert conn.execute("SELECT sin_resolver FROM v_factura_ediciones WHERE factura_id = ?",
                        (f,)).fetchone()[0] == 1


def test_un_automatico_que_coincide_con_lo_manual_lo_resuelve(tipado, ana) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    campos.fijar(conn, "factura", f, {"total_cent": Decimal("2902.80")}, Persona(ana, "lectura mala"))
    campos.fijar(conn, "factura", f, {"total_cent": Decimal("2902.80")},
                 Automatico("extraccion", usuario_sistema(conn, "extractor"), ref="extraccion:99"))
    assert not campos.estado_campo(_p(conn, "factura", f, "total_cent")).sin_resolver


def test_una_correccion_sin_motivo_no_entra(tipado, ana) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    eventos = conn.execute("SELECT count(*) FROM evento").fetchone()[0]
    for motivo in (None, "", "   "):
        with pytest.raises(FaltaMotivo):
            campos.fijar(conn, "factura", f, {"total_cent": Decimal("1")}, Persona(ana, motivo))
    assert _total(conn, f) == 290279
    assert conn.execute("SELECT count(*) FROM evento").fetchone()[0] == eventos
    # Y la base tampoco lo admite aunque alguien se salte campos.py.
    assert "manual_correccion' OR length(trim(coalesce(motivo" in conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'cambio_campo'").fetchone()[0]


def test_un_campo_de_exact_no_se_corrige_aqui(tipado) -> None:
    conn = tipado.conn
    admin = persona(conn, "Bea", "administrador")
    importador = usuario_sistema(conn, "importador")
    proveedor = campos.crear(conn, "proveedor", {"nombre": "Van Dijk BV", "exact_id": "E-1"},
                             Automatico("importacion", importador, en_nombre_de="exact"))
    with pytest.raises(CampoDeOtroSistema, match="exact"):
        campos.fijar(conn, "proveedor", proveedor, {"nombre": "Otro"}, Persona(admin, "mal escrito"))
    with pytest.raises(CampoDeOtroSistema):
        campos.fijar(conn, "proveedor", proveedor, {"kvk": "1"},
                     Automatico("importacion", importador, en_nombre_de="maestro_csv"))
    # Su importacion si, y lo que es local (el telefono de verificacion) tambien.
    campos.fijar(conn, "proveedor", proveedor, {"nombre": "Van Dijk B.V."},
                 Automatico("importacion", importador, en_nombre_de="exact"))
    campos.fijar(conn, "proveedor", proveedor, {"telefono_verificacion": "+31 10 1234567"},
                 Persona(admin))


def test_un_campo_del_sistema_no_se_edita(tipado, ana) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    for campo, valor in (("sentido", "saliente"), ("numero_norm", "X"), ("documento_id", 2),
                         ("moneda_doc", "EUR")):
        with pytest.raises(CampoNoEditable):
            campos.fijar(conn, "factura", f, {campo: valor}, Persona(ana, "probando"))


def test_cada_campo_pide_su_permiso(tipado) -> None:
    conn = tipado.conn
    consulta = persona(conn, "Carla", "consulta")
    f = factura_de(conn, "2026-4471")
    with pytest.raises(PermisoDenegado, match="anadir_informacion"):
        campos.fijar(conn, "factura", f, {"referencia_pago": "X"}, Persona(consulta))
    with pytest.raises(PermisoDenegado, match="editar_extraccion"):
        campos.fijar(conn, "factura", f, {"total_cent": Decimal("1")}, Persona(consulta, "x"))
    imputacion = conn.execute("SELECT id FROM factura_imputacion WHERE factura_id = ? ORDER BY id",
                              (f,)).fetchone()[0]
    with pytest.raises(PermisoDenegado, match="cambiar_objeto"):
        campos.fijar(conn, "factura_imputacion", imputacion, {"objeto_id": None}, Persona(consulta, "x"))
    denegados = conn.execute(
        "SELECT usuario_id, resultado, json_extract(datos_json, '$.permiso') FROM evento "
        "WHERE tipo = 'permiso_denegado' ORDER BY id").fetchall()
    assert [tuple(d) for d in denegados] == [
        (consulta, "denegado", "anadir_informacion"), (consulta, "denegado", "editar_extraccion"),
        (consulta, "denegado", "cambiar_objeto")]
    assert verificar_cadena(conn).ok


def test_un_usuario_de_sistema_no_edita_como_persona(tipado) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    for nombre in ("sistema", "extractor", "importador", "motor"):
        with pytest.raises(PermisoDenegado, match="usuario de sistema"):
            campos.fijar(conn, "factura", f, {"referencia_pago": "X"},
                         Persona(usuario_sistema(conn, nombre)))


def test_nadie_crea_una_factura_a_mano(tipado) -> None:
    conn = tipado.conn
    admin = persona(conn, "Bea", "administrador")
    with pytest.raises(PermisoDenegado, match="nadie puede"):
        campos.crear(conn, "factura", {"sentido": "entrante", "tipo": "factura", "origen": "manual"},
                     Persona(admin))


def test_una_edicion_sobre_una_version_vieja_es_un_conflicto(tipado, ana) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    rev = conn.execute("SELECT rev FROM factura WHERE id = ?", (f,)).fetchone()[0]
    campos.fijar(conn, "factura", f, {"referencia_pago": "A"}, Persona(ana), rev_esperada=rev)
    with pytest.raises(Conflicto):
        campos.fijar(conn, "factura", f, {"referencia_pago": "B"}, Persona(ana, "otra"),
                     rev_esperada=rev)


def test_un_importe_que_no_cabe_sin_redondear_queda_vacio_y_dudoso(tipado) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    r = campos.fijar(conn, "factura", f,
                     {"total_cent": Leido(Decimal("2902.791"), crudo="2.902,791")},
                     Automatico("extraccion", usuario_sistema(conn, "extractor"), ref="extraccion:9"))
    p = _p(conn, "factura", f, "total_cent")
    assert _total(conn, f) is None and p["dudoso"] == 1
    assert r.de("factura", f, "total_cent").accion == "cambiado"
    # Una persona no tiene ese margen: su valor se convierte exacto o falla.
    ana = persona(conn, "Ana", "administracion")
    with pytest.raises(ValueError):
        campos.fijar(conn, "factura", f, {"total_cent": Decimal("1.001")}, Persona(ana, "x"))


# --- verificar y notas ---

def test_verificar_vale_para_la_version_que_se_verifico(tipado, ana) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    campos.verificar_campos(conn, "factura", f, ["emisor_kvk_doc"], Persona(ana))
    assert campos.estado_campo(_p(conn, "factura", f, "emisor_kvk_doc")).verificado
    campos.fijar(conn, "factura", f, {"emisor_kvk_doc": "8765 4321"}, Persona(ana, "espacios"))
    assert not campos.estado_campo(_p(conn, "factura", f, "emisor_kvk_doc")).verificado


def test_quien_corrige_no_verifica_si_hay_otra_persona(tipado, ana) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    campos.fijar(conn, "factura", f, {"total_cent": Decimal("2902.80")}, Persona(ana, "lectura mala"))
    # Sola, se autorrevisa y queda marcado.
    r = campos.verificar_campos(conn, "factura", f, ["total_cent"], Persona(ana))
    datos = conn.execute("SELECT datos_json FROM evento WHERE id = ?", (r.evento_id,)).fetchone()[0]
    assert f"factura:{f}:total_cent" in datos and "autorrevisados" in datos
    campos.fijar(conn, "factura", f, {"total_cent": Decimal("2902.81")}, Persona(ana, "otra"))
    bea = persona(conn, "Bea", "administracion")
    with pytest.raises(SeparacionDeFunciones):
        campos.verificar_campos(conn, "factura", f, ["total_cent"], Persona(ana))
    campos.verificar_campos(conn, "factura", f, ["total_cent"], Persona(bea))
    p = _p(conn, "factura", f, "total_cent")
    assert p["verificado_por"] == bea and not campos.estado_campo(p).sin_resolver


def test_el_sistema_no_verifica(tipado) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    with pytest.raises(PermisoDenegado):
        with campos.orden(conn, Automatico("calculado", usuario_sistema(conn, "motor")),
                          tipo="x") as o:
            o.verificar("factura", f, ("total_cent",))
    with pytest.raises(sqlite3.IntegrityError, match="persona"):
        conn.execute("UPDATE procedencia_campo SET verificado_por = 1, verificado_en = "
                     "'2026-10-14T09:30:00+00:00', verificado_rev = 0 WHERE id = 1")


def test_una_nota_la_escribe_una_persona_y_solo_se_anade(tipado, ana) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    nota = campos.anadir_nota(conn, "factura", f, "Llamado el proveedor", Persona(ana))
    fila = conn.execute("SELECT * FROM nota WHERE id = ?", (nota,)).fetchone()
    assert (fila["usuario_id"], fila["texto"]) == (ana, "Llamado el proveedor")
    with pytest.raises(PermisoDenegado):
        campos.anadir_nota(conn, "factura", f, "x", Persona(usuario_sistema(conn, "motor")))
    with pytest.raises(sqlite3.IntegrityError, match="solo escritura"):
        conn.execute("UPDATE nota SET texto = 'otra cosa'")


# --- calculos y una orden = un evento ---

def test_una_factura_tipada_es_un_solo_evento(tipado) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    [evento] = conn.execute("SELECT * FROM evento WHERE tipo = 'factura_tipada' AND fila_id = ?",
                            (f,)).fetchall()
    tablas = {c[0] for c in conn.execute(
        "SELECT DISTINCT tabla FROM cambio_campo WHERE evento_id = ?", (evento["id"],))}
    assert tablas == {"factura", "factura_linea", "factura_imputacion"}


def test_corregir_una_linea_arrastra_su_imputacion(tipado, ana) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    linea = conn.execute("SELECT id FROM factura_linea WHERE factura_id = ? AND orden = 1",
                         (f,)).fetchone()[0]
    campos.fijar(conn, "factura_linea", linea, {"importe_cent": Decimal("1593.70")},
                 Persona(ana, "importe mal leido"))
    imputacion = conn.execute("SELECT * FROM factura_imputacion WHERE linea_id = ?", (linea,)).fetchone()
    assert imputacion["importe_cent"] == 159370
    assert _p(conn, "factura_imputacion", imputacion["id"], "importe_cent")["fuente"] == "calculado"


def test_un_objeto_puesto_a_mano_no_lo_pisa_el_calculo(tipado, ana) -> None:
    from bms_agent.importadores.tarifas import sembrar_tarifas
    from conftest import TARIFAS_V1

    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    imputacion = conn.execute(
        "SELECT i.id FROM factura_imputacion AS i JOIN factura_linea AS l ON l.id = i.linea_id "
        "WHERE i.factura_id = ? AND l.orden = 1", (f,)).fetchone()[0]
    assert conn.execute("SELECT objeto_id FROM factura_imputacion WHERE id = ?",
                        (imputacion,)).fetchone()[0] is None
    sembrar_tarifas(conn, TARIFAS_V1)
    rijnhaven, schiedam = (conn.execute("SELECT id FROM objeto WHERE codigo = ?", (c,)).fetchone()[0]
                           for c in ("Rijnhaven", "Schiedam"))
    assert conn.execute("SELECT objeto_id FROM factura_imputacion WHERE id = ?",
                        (imputacion,)).fetchone()[0] == rijnhaven
    r = campos.fijar(conn, "factura_imputacion", imputacion, {"objeto_id": schiedam},
                     Persona(ana, "era Schiedam"))
    assert r.de("factura_imputacion", imputacion, "objeto_id").fuente == "manual_correccion"
    sembrar_tarifas(conn, TARIFAS_V1)
    from bms_agent.ingesta import reconciliar_referencias

    reconciliar_referencias(conn)
    assert conn.execute("SELECT objeto_id FROM factura_imputacion WHERE id = ?",
                        (imputacion,)).fetchone()[0] == schiedam


# --- la guarda de la base ---

CONTROLADAS = campos.TABLAS_CONTROLADAS


def test_un_update_fuera_de_campos_lo_rechaza_la_guarda(tipado) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    guarda = "tabla controlada"
    with pytest.raises(sqlite3.IntegrityError, match=guarda):
        conn.execute("UPDATE factura SET total_cent = 1 WHERE id = ?", (f,))
    with pytest.raises(sqlite3.IntegrityError, match=guarda):
        conn.execute("UPDATE factura SET total_cent = 1, rev = rev + 1 WHERE id = ?", (f,))
    with pytest.raises(sqlite3.IntegrityError, match="no se borra"):
        conn.execute("DELETE FROM factura_linea WHERE factura_id = ?", (f,))
    with pytest.raises(sqlite3.IntegrityError, match=guarda):
        conn.execute("INSERT INTO cliente (nombre) VALUES ('Por detras BV')")
    with pytest.raises(sqlite3.IntegrityError, match="procedencia_campo"):
        conn.execute("UPDATE procedencia_campo SET fuente = 'extraccion' WHERE fuente = 'calculado'")


def test_la_guarda_exige_el_cambio_de_cada_columna(tipado) -> None:
    """Un cambio_campo de un campo no tapa el cambio de otro, ni de otro valor."""
    from bms_agent.almacen import transaccion
    from bms_agent.auditoria import Cambio, registrar

    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    fila = conn.execute("SELECT * FROM factura WHERE id = ?", (f,)).fetchone()
    sistema = usuario_sistema(conn, "sistema")
    cambio = Cambio("factura", f, "referencia_pago", fila["rev"] + 1, None, "X", "calculado")
    with pytest.raises(sqlite3.IntegrityError, match="tabla controlada"):
        with transaccion(conn):
            registrar(conn, tipo="atajo", actor=sistema, cambios=[cambio])
            conn.execute("UPDATE factura SET referencia_pago = 'X', total_cent = 1, rev = rev + 1 "
                         "WHERE id = ?", (f,))
    with pytest.raises(sqlite3.IntegrityError, match="tabla controlada"):
        with transaccion(conn):
            registrar(conn, tipo="atajo", actor=sistema, cambios=[cambio])
            conn.execute("UPDATE factura SET referencia_pago = 'Y', rev = rev + 1 WHERE id = ?", (f,))
    # Con el evento en curso y el valor exacto, la base lo deja: la guarda es
    # la historia, no un nombre de modulo. Por eso hay ademas el test de abajo.
    with transaccion(conn):
        registrar(conn, tipo="atajo", actor=sistema, cambios=[cambio])
        conn.execute("UPDATE factura SET referencia_pago = 'X', rev = rev + 1 WHERE id = ?", (f,))


_ESCRITURA = re.compile(
    r"\b(?:UPDATE|INSERT\s+(?:OR\s+\w+\s+)?INTO|REPLACE\s+INTO|DELETE\s+FROM)\s+"
    r"(?:\{|\"?(?:" + "|".join(sorted(CONTROLADAS + ("procedencia_campo",), key=len, reverse=True))
    + r")\b)",
    re.IGNORECASE,
)


def _textos_sql(ruta: Path) -> list[tuple[int, str]]:
    """Cada literal de texto de un modulo (tambien los trozos de un f-string)."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    textos = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            textos.append((nodo.lineno, nodo.value))
        elif isinstance(nodo, ast.JoinedStr):
            partes = [p.value if isinstance(p, ast.Constant) else "{" for p in nodo.values]
            textos.append((nodo.lineno, "".join(partes)))
    return textos


def test_solo_campos_escribe_las_tablas_controladas() -> None:
    """Ningun otro modulo tiene una sentencia que inserte, cambie o borre una controlada.

    Mira cada texto del codigo (tambien los f-string, donde una tabla
    variable cuenta como sospechosa) y tambien el texto plano, por si una
    sentencia se arma de otra forma.
    """
    encontradas = []
    for ruta in sorted(FUENTES.rglob("*.py")):
        if ruta.name == "campos.py":
            continue
        for linea, texto in _textos_sql(ruta):
            if _ESCRITURA.search(texto):
                encontradas.append(f"{ruta.relative_to(RAIZ)}:{linea}: {texto[:60]!r}")
        crudo = ruta.read_text(encoding="utf-8")
        for coincide in _ESCRITURA.finditer(crudo):
            if "{" not in coincide.group(0):
                encontradas.append(f"{ruta.relative_to(RAIZ)}: {coincide.group(0)!r}")
    assert encontradas == []


def test_la_busqueda_de_escrituras_ve_lo_que_tiene_que_ver() -> None:
    for sql in ("UPDATE factura SET x = 1", 'insert into "factura_linea" (a) values (1)',
                "INSERT OR REPLACE INTO alias VALUES (1)", "DELETE FROM objeto",
                "UPDATE {tabla} SET", "update procedencia_campo set"):
        assert _ESCRITURA.search(sql), sql
    for sql in ("UPDATE importacion SET estado = 'x'", "SELECT * FROM factura",
                "BEFORE UPDATE ON factura", "UPDATE usuario_rol SET hasta = ?"):
        assert not _ESCRITURA.search(sql), sql


def test_las_guardas_cubren_cada_columna(db) -> None:
    for tabla in CONTROLADAS:
        columnas = [c["name"] for c in db.execute(f"PRAGMA table_info({tabla})")
                    if c["name"] not in ("id", "rev")]
        for disparador in ("guarda_insert", "guarda_update"):
            sql = db.execute("SELECT sql FROM sqlite_master WHERE name = ?",
                             (f"{tabla}_{disparador}",)).fetchone()[0]
            faltan = [c for c in columnas if f"NEW.{c} " not in sql]
            assert faltan == [], (tabla, disparador)
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name = ?",
                          (f"{tabla}_sin_delete",)).fetchone()


def test_las_guardas_de_la_migracion_son_las_del_script(db) -> None:
    import importlib.util

    from bms_agent.almacen.migrar import disponibles

    spec = importlib.util.spec_from_file_location("guardas", RAIZ / "scripts" / "generar_guardas.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    # Las del paso 2 estan en la 0002 y las del paso 5 (beneficiario_conocido,
    # ciclo_facturacion) en la 0005: se buscan en todas.
    sql = "\n".join(m.sql for m in disponibles())
    for tabla in CONTROLADAS:
        assert modulo.guardas(tabla, modulo.columnas(db, tabla)) in sql, tabla


def test_el_registro_es_cada_columna_de_cada_tabla(db) -> None:
    for tabla in CONTROLADAS:
        columnas = [c["name"] for c in db.execute(f"PRAGMA table_info({tabla})")
                    if c["name"] not in ("id", "rev")]
        assert list(campos.REGISTRO[tabla]) == columnas, tabla


def test_los_enum_del_registro_son_los_check_de_la_base(db) -> None:
    for tabla, definiciones in campos.REGISTRO.items():
        sql = db.execute("SELECT sql FROM sqlite_master WHERE name = ?", (tabla,)).fetchone()[0]
        for nombre, definicion in definiciones.items():
            if definicion.tipo != campos.ENUM:
                continue
            check = re.search(rf"\b{nombre}\b[^\n]*?IN \(([^)]*)\)", sql, re.S)
            assert check, (tabla, nombre)
            valores = tuple(v.strip().strip("'") for v in check.group(1).replace("\n", " ").split(","))
            assert set(valores) == set(definicion.valores), (tabla, nombre)


def test_el_dinero_va_en_enteros_con_su_escala(db) -> None:
    sufijos = {"_cent": campos.CENT, "_mil": campos.MIL, "_e4": campos.E4, "_pb": campos.PB}
    for tabla in [f[0] for f in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]:
        for columna in db.execute(f"PRAGMA table_info({tabla})"):
            sufijo = next((s for s in sufijos if columna["name"].endswith(s)), None)
            if sufijo is None:
                continue
            assert columna["type"] == "INTEGER", (tabla, columna["name"])
            if tabla in campos.REGISTRO:
                assert campos.REGISTRO[tabla][columna["name"]].tipo == sufijos[sufijo]


def test_el_registro_dice_obligatorios_y_criticos() -> None:
    assert set(campos.obligatorios("factura", "entrante")) >= {
        "numero", "proveedor_id", "fecha_factura", "periodo_inicio", "periodo_fin",
        "base_cent", "iva_cent", "total_cent"}
    assert "cliente_id" in campos.obligatorios("factura", "saliente")
    assert "proveedor_id" not in campos.obligatorios("factura", "saliente")
    assert {"numero", "total_cent", "iban_doc"} <= set(campos.criticos("factura"))


# --- verificar lo escrito, sin fiarse de los disparadores ---

def test_db_verificar_ve_una_controlada_tocada_por_detras(tmp_path, out_v1, capsys) -> None:
    from bms_agent.cli import main

    db = tmp_path / "datos" / "bms.sqlite3"
    assert main(["importar-out", "--out", str(out_v1), "--pdfs", str(tmp_path / "no"),
                 "--db", str(db)]) == 0
    assert main(["db", "verificar", "--db", str(db)]) == 0
    assert "facturas tipadas      7" in capsys.readouterr().out

    atacante = sqlite3.connect(db, isolation_level=None)
    atacante.execute("DROP TRIGGER factura_guarda_update")
    atacante.execute("UPDATE factura SET total_cent = 1 WHERE numero = '2026-4471'")
    atacante.execute("DROP TRIGGER procedencia_campo_guarda_update")
    atacante.execute("UPDATE procedencia_campo SET fuente = 'extraccion' WHERE fuente = 'calculado' "
                     "AND tabla = 'factura' AND campo = 'tipo'")
    atacante.close()
    assert main(["db", "verificar", "--db", str(db)]) == 1
    salida = capsys.readouterr().out
    assert "total_cent no es lo que dejo su ultimo cambio" in salida
    assert "la procedencia de tipo no dice la fuente" in salida


def test_verificar_controladas_esta_limpio_tras_tipar_y_editar(tipado, ana) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    campos.fijar(conn, "factura", f, {"total_cent": Decimal("1")}, Persona(ana, "x"))
    campos.retirar(conn, "factura_linea", conn.execute(
        "SELECT id FROM factura_linea WHERE factura_id = ? AND orden = 3", (f,)).fetchone()[0],
        Persona(ana, "no se factura"))
    assert campos.verificar_controladas(conn) == []
    assert verificar_cadena(conn).ok


def test_retirar_una_linea_exige_motivo_y_no_la_borra(tipado, ana) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    linea = conn.execute("SELECT id FROM factura_linea WHERE factura_id = ? AND orden = 3",
                         (f,)).fetchone()[0]
    with pytest.raises(FaltaMotivo):
        campos.retirar(conn, "factura_linea", linea, Persona(ana))
    campos.retirar(conn, "factura_linea", linea, Persona(ana, "no se factura"))
    assert conn.execute("SELECT retirada_en FROM factura_linea WHERE id = ?",
                        (linea,)).fetchone()[0] == "2026-10-14T09:30:00+00:00"


def test_el_almacen_en_disco_admite_la_misma_escritura(tmp_path, reloj) -> None:
    """WAL y fichero: la guarda y el evento funcionan igual que en memoria."""
    from bms_agent.almacen.migrar import migrar

    conn = abrir(tmp_path / "bms.sqlite3", reloj=reloj)
    try:
        migrar(conn)
        importador = usuario_sistema(conn, "importador")
        cliente = campos.crear(conn, "cliente", {"nombre": "Havenbedrijf"},
                               Automatico("maestro", importador))
        assert campos.leer(conn, "cliente", cliente)["activo"] == 1
        assert campos.verificar_controladas(conn) == []
    finally:
        conn.close()


# --- correcciones de la revision del paso 2 ---

def test_una_extraccion_que_contradice_lo_verificado_vuelve_a_m1(tipado, ana) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    campos.fijar(conn, "factura", f, {"total_cent": Decimal("2902.80")}, Persona(ana, "lectura mala"))
    campos.verificar_campos(conn, "factura", f, ["total_cent"], Persona(ana))
    assert not campos.estado_campo(_p(conn, "factura", f, "total_cent")).sin_resolver
    extractor = usuario_sistema(conn, "extractor")
    # La misma lectura otra vez no deshace la verificacion: nada nuevo la contradice.
    campos.fijar(conn, "factura", f, {"total_cent": Leido(Decimal("2902.79"), crudo="2.902,79")},
                 Automatico("extraccion", extractor, ref="extraccion:98"))
    assert campos.estado_campo(_p(conn, "factura", f, "total_cent")).verificado
    campos.fijar(conn, "factura", f, {"total_cent": Leido(Decimal("3000.00"), crudo="3.000,00")},
                 Automatico("extraccion", extractor, ref="extraccion:99"))
    p = _p(conn, "factura", f, "total_cent")
    assert (p["valor_actual"], p["valor_automatico"]) == (290280, 300000)
    estado = campos.estado_campo(p)
    assert estado.sin_resolver and not estado.verificado
    assert conn.execute("SELECT sin_resolver FROM v_factura_ediciones WHERE factura_id = ?",
                        (f,)).fetchone()[0] == 1
    assert campos.verificar_controladas(conn) == []


def test_retirar_una_linea_retira_su_imputacion(tipado, ana) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    linea = conn.execute("SELECT id FROM factura_linea WHERE factura_id = ? AND orden = 3",
                         (f,)).fetchone()[0]
    r = campos.retirar(conn, "factura_linea", linea, Persona(ana, "no se factura"))
    imputacion = conn.execute("SELECT retirada_en FROM factura_imputacion WHERE linea_id = ?",
                              (linea,)).fetchone()
    assert imputacion["retirada_en"] == "2026-10-14T09:30:00+00:00"
    motivos = {c["motivo"] for c in conn.execute(
        "SELECT motivo FROM cambio_campo WHERE evento_id = ?", (r.evento_id,))}
    assert motivos == {"no se factura"}
    assert campos.verificar_controladas(conn) == []


def test_el_iban_del_documento_no_se_corrige_y_f3_lo_sigue_viendo(tipado, out_v1, ana) -> None:
    """Editar el IBAN impreso no puede quitar la parada F3: es evidencia, no un dato."""
    import json as _json

    from conftest import FIXTURES_V1

    from bms_agent.dashboard import detectar_ibanes
    from bms_agent.importadores.extracciones import importar_out
    from bms_agent.ingesta import tipar_pendientes
    from bms_agent.legado import registros_resueltos

    conn = tipado.conn
    registro = _json.loads((FIXTURES_V1 / "04-nota-credito.json").read_text(encoding="utf-8"))
    registro["extracted_at"] = "2026-10-01T08:00:00+00:00"
    registro["extraction"]["iban"] = "NL91 ABNA 0417 1643 00"
    (out_v1 / "04-nota-credito-z.json").write_text(_json.dumps(registro), encoding="utf-8")
    importar_out(tipado, out_v1, None)
    tipar_pendientes(conn)
    f = factura_de(conn, "CN-2026-031")
    assert campos.leer(conn, "factura", f)["iban_doc"] == "NL91 ABNA 0417 1643 00"
    assert detectar_ibanes(registros_resueltos(conn))

    with pytest.raises(CampoNoEditable):
        campos.fijar(conn, "factura", f, {"iban_doc": "NL02 ABNA 0123 4567 89"},
                     Persona(ana, "typo del OCR"))
    assert detectar_ibanes(registros_resueltos(conn))
    # Verificar la lectura si se puede: dice que el documento pone eso, no que la cuenta valga.
    campos.verificar_campos(conn, "factura", f, ["iban_doc"], Persona(ana))
    assert detectar_ibanes(registros_resueltos(conn))


@pytest.fixture
def van_dijk(tipado):
    """Van Dijk en el maestro: sus dos facturas (2026-4471 y CN-2026-031) quedan resueltas."""
    from bms_agent.ingesta import reconciliar_referencias

    conn = tipado.conn
    campos.crear(conn, "proveedor", {"nombre": "Bouwtechniek Van Dijk BV",
                                     "btw_id": "NL001234567B01"},
                 Automatico("maestro", usuario_sistema(conn, "importador")))
    reconciliar_referencias(conn)
    return conn


def test_fusionar_exige_motivo_misma_parte_y_sin_cadenas(van_dijk, ana) -> None:
    from bms_agent.legado import registros_resueltos

    conn = van_dijk
    jefa = persona(conn, "Bea", "administracion")
    a, b = factura_de(conn, "2026-4471"), factura_de(conn, "CN-2026-031")
    koster = factura_de(conn, "2026-0912")
    with pytest.raises(FaltaMotivo):
        campos.fijar(conn, "factura", b, {"fusionada_en_id": a}, Persona(jefa))
    with pytest.raises(campos.FusionNoValida, match="mismo proveedor"):
        campos.fijar(conn, "factura", a, {"fusionada_en_id": koster}, Persona(jefa, "duplicado"))
    with pytest.raises(campos.FusionNoValida, match="mismo proveedor"):
        campos.fijar(conn, "factura", koster, {"fusionada_en_id": a}, Persona(jefa, "duplicado"))
    antes = len(registros_resueltos(conn))
    campos.fijar(conn, "factura", b, {"fusionada_en_id": a}, Persona(jefa, "es la misma"))
    # Ni ciclo ni cadena.
    with pytest.raises(campos.FusionNoValida, match="ya esta fusionada"):
        campos.fijar(conn, "factura", a, {"fusionada_en_id": b}, Persona(jefa, "al reves"))
    otra = campos.crear(conn, "factura", {
        "sentido": "entrante", "tipo": "factura", "origen": "exact", "fuente_externa": "exact",
        "id_externo": "X-1", "numero": "EX-1",
        "proveedor_id": campos.leer(conn, "factura", a)["proveedor_id"]},
        Automatico("importacion", usuario_sistema(conn, "importador"), en_nombre_de="exact"))
    with pytest.raises(campos.FusionNoValida, match="no se encadenan"):
        campos.fijar(conn, "factura", a, {"fusionada_en_id": otra}, Persona(jefa, "cadena"))
    # Y la base tampoco lo deja, aunque alguien se salte campos.py.
    disparador = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'factura_fusion_valida_update'").fetchone()[0]
    assert "fusionada_en_id = NEW.id" in disparador
    # Una factura fusionada no desaparece de lo que leen el panel y sus avisos.
    assert len(registros_resueltos(conn)) == antes
    assert campos.verificar_controladas(conn) == []


def test_crear_una_fila_pide_lo_mismo_que_fijarla(tipado) -> None:
    from bms_agent import permisos

    conn = tipado.conn
    permisos.crear_rol(conn, "solo_admin", ["admin"])
    permisos.crear_rol(conn, "solo_editar", ["editar_extraccion"])
    admin = persona(conn, "Ada")
    permisos.asignar_rol(conn, admin, "solo_admin")
    editor = persona(conn, "Eli")
    permisos.asignar_rol(conn, editor, "solo_editar")

    with pytest.raises(PermisoDenegado, match="confirmar_iban"):
        campos.crear(conn, "proveedor", {"nombre": "Y BV", "telefono_verificacion": "+31 6 999"},
                     Persona(admin))
    with pytest.raises(CampoNoEditable, match="exact_id"):
        campos.crear(conn, "proveedor", {"nombre": "Y BV", "exact_id": "E1"}, Persona(admin))
    with pytest.raises(CampoNoEditable, match="origen"):
        campos.crear(conn, "alias", {"tabla": "proveedor", "alias": "VD", "fila_id": 1,
                                     "origen": "maestro"}, Persona(admin))
    proveedor = campos.crear(conn, "proveedor", {"nombre": "Y BV"}, Persona(admin))
    assert campos.leer(conn, "proveedor", proveedor)["exact_id"] is None

    f = factura_de(conn, "2026-4471")
    linea = conn.execute("SELECT id FROM factura_linea WHERE factura_id = ? AND orden = 1",
                         (f,)).fetchone()[0]
    with pytest.raises(PermisoDenegado, match="cambiar_po"):
        campos.crear(conn, "factura_imputacion", {"factura_id": f, "linea_id": linea,
                                                  "orden_compra_id": 7}, Persona(editor))
    with pytest.raises(PermisoDenegado, match="cambiar_objeto"):
        campos.crear(conn, "factura_imputacion", {"factura_id": f, "linea_id": linea,
                                                  "objeto_id": 1}, Persona(editor))
    with pytest.raises(CampoNoEditable, match="retirada_en"):
        campos.crear(conn, "factura_linea", {"factura_id": f, "orden": 9,
                                             "retirada_en": "2026-10-14T09:30:00+00:00"},
                     Persona(editor))
    nueva = campos.crear(conn, "factura_linea", {"factura_id": f, "orden": 9,
                                                 "descripcion_doc": "Extra"}, Persona(editor))
    assert campos.leer(conn, "factura_linea", nueva)["descripcion_doc"] == "Extra"
    jefa = persona(conn, "Bea", "administracion")
    otra = factura_de(conn, "2026-018")
    relacion = campos.crear(conn, "factura_relacion", {"origen_id": f, "destino_id": otra,
                                                       "tipo": "relacionada", "estado": "propuesta"},
                                   Persona(jefa))
    assert campos.leer(conn, "factura_relacion", relacion)["fuente"] == "manual"
    with pytest.raises(CampoNoEditable, match="fuente"):
        campos.crear(conn, "factura_relacion", {"origen_id": f, "destino_id": otra,
                                                "tipo": "relacionada", "estado": "propuesta",
                                                "fuente": "exact"},
                     Persona(jefa))
    assert campos.verificar_controladas(conn) == []


def test_las_lineas_de_una_factura_de_exact_no_se_tocan_aqui(tipado) -> None:
    conn = tipado.conn
    jefa = persona(conn, "Bea", "administracion")
    importador = usuario_sistema(conn, "importador")
    origen = Automatico("importacion", importador, en_nombre_de="exact")
    with campos.orden(conn, origen, tipo="importacion_exact") as o:
        factura = o.crear("factura", {"sentido": "entrante", "tipo": "factura", "origen": "exact",
                                      "fuente_externa": "exact", "id_externo": "X-1",
                                      "numero": "EX-1"})
        linea = o.crear("factura_linea", {"factura_id": factura, "orden": 1,
                                          "descripcion_doc": "Montage"})
    with pytest.raises(CampoDeOtroSistema):
        campos.crear(conn, "factura_linea", {"factura_id": factura, "orden": 2,
                                             "descripcion_doc": "Extra"}, Persona(jefa))
    with pytest.raises(CampoDeOtroSistema):
        campos.retirar(conn, "factura_linea", linea, Persona(jefa, "no va"))
    assert campos.leer(conn, "factura_linea", linea)["retirada_en"] is None


def test_db_verificar_ve_una_procedencia_reescrita_por_detras(tipado, ana) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    beto = persona(conn, "Beto", "administracion")
    campos.fijar(conn, "factura", f, {"total_cent": Decimal("1.00")}, Persona(ana, "x"))
    assert campos.estado_campo(_p(conn, "factura", f, "total_cent")).sin_resolver
    assert campos.verificar_controladas(conn) == []
    guardas = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' "
        "AND tbl_name = 'procedencia_campo'").fetchall()
    for g in guardas:
        conn.execute(f"DROP TRIGGER {g['name']}")
    p = _p(conn, "factura", f, "total_cent")
    conn.execute(
        "UPDATE procedencia_campo SET valor_original = '100', valor_original_crudo = '\"1,00\"', "
        "valor_automatico = '100', verificado_por = ?, verificado_en = ?, verificado_rev = ? "
        "WHERE tabla = 'factura' AND fila_id = ? AND campo = 'total_cent'",
        (beto, "2026-10-14T09:30:00+00:00", p["rev_campo"], f))
    for g in guardas:
        conn.execute(g["sql"])
    assert not campos.estado_campo(_p(conn, "factura", f, "total_cent")).sin_resolver
    problemas = campos.verificar_controladas(conn)
    clave = f"factura:{f}:total_cent"
    assert any(clave in p and "valor_original" in p and "verificado_por" in p for p in problemas)
    assert any(clave in p and "el original cambio" not in p for p in problemas)


def test_la_guarda_de_procedencia_exige_la_foto_del_evento(tipado, ana) -> None:
    """Que el ultimo evento nombre un campo ya no basta: tiene que llevar su foto exacta."""
    from bms_agent.almacen import transaccion
    from bms_agent.auditoria import registrar

    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    beto = persona(conn, "Beto", "administracion")
    clave = f"factura:{f}:total_cent"
    with pytest.raises(sqlite3.IntegrityError, match="foto"):
        with transaccion(conn):
            registrar(conn, tipo="campo_verificado", actor=ana, usuario_id=ana,
                      datos={"campos": [clave]})
            conn.execute(
                "UPDATE procedencia_campo SET verificado_por = ?, verificado_en = ?, "
                "verificado_rev = rev_campo WHERE tabla = 'factura' AND fila_id = ? "
                "AND campo = 'total_cent'", (beto, "2026-10-14T09:30:00+00:00", f))
    with pytest.raises(sqlite3.IntegrityError, match="foto"):
        with transaccion(conn):
            p = conn.execute("SELECT * FROM procedencia_campo WHERE tabla = 'factura' AND "
                             "fila_id = ? AND campo = 'total_cent'", (f,)).fetchone()
            foto = {c: p[c] for c in p.keys() if c not in ("id", "tabla", "fila_id", "campo")}
            registrar(conn, tipo="campo_verificado", actor=ana, usuario_id=ana,
                      datos={"procedencia": {clave: foto}})
            conn.execute(
                "UPDATE procedencia_campo SET valor_automatico = '1' WHERE tabla = 'factura' "
                "AND fila_id = ? AND campo = 'total_cent'", (f,))


def test_una_separacion_de_funciones_denegada_queda_en_la_auditoria(tipado, ana) -> None:
    conn = tipado.conn
    f = factura_de(conn, "2026-4471")
    persona(conn, "Bea", "administracion")
    campos.fijar(conn, "factura", f, {"total_cent": Decimal("2902.80")}, Persona(ana, "lectura mala"))
    eventos = conn.execute("SELECT count(*) FROM evento").fetchone()[0]
    with pytest.raises(PermisoDenegado) as error:
        campos.verificar_campos(conn, "factura", f, ["total_cent"], Persona(ana))
    assert isinstance(error.value, SeparacionDeFunciones)
    assert conn.execute("SELECT count(*) FROM evento").fetchone()[0] == eventos + 1
    ultimo = conn.execute("SELECT * FROM evento ORDER BY id DESC LIMIT 1").fetchone()
    assert (ultimo["tipo"], ultimo["resultado"], ultimo["usuario_id"]) == (
        "permiso_denegado", "denegado", ana)
    assert "verificar factura.total_cent" in ultimo["datos_json"]
    assert verificar_cadena(conn).ok


def test_rellenar_una_imputacion_es_anadir_informacion(tipado) -> None:
    from bms_agent import permisos

    conn = tipado.conn
    permisos.crear_rol(conn, "solo_anadir", ["anadir_informacion"])
    quien = persona(conn, "Ines")
    permisos.asignar_rol(conn, quien, "solo_anadir")
    f = factura_de(conn, "2026-4471")
    imputacion = conn.execute("SELECT id FROM factura_imputacion WHERE factura_id = ? ORDER BY id",
                              (f,)).fetchone()[0]
    campos.fijar(conn, "factura_imputacion", imputacion, {"facturable": True}, Persona(quien))
    assert campos.leer(conn, "factura_imputacion", imputacion)["facturable"] == 1
    with pytest.raises(PermisoDenegado, match="editar_extraccion"):
        campos.fijar(conn, "factura_imputacion", imputacion, {"facturable": False},
                     Persona(quien, "no"))


def test_db_verificar_ve_una_nota_o_una_politica_tocadas_por_detras(tipado, ana) -> None:
    from conftest import TARIFAS_V1

    from bms_agent.almacen.evidencia import verificar_evidencia
    from bms_agent.importadores.tarifas import sembrar_tarifas

    conn = tipado.conn
    sembrar_tarifas(conn, TARIFAS_V1)
    campos.anadir_nota(conn, "factura", factura_de(conn, "2026-4471"), "Llamado el proveedor",
                       Persona(ana))
    assert verificar_evidencia(conn) == []
    guardas = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE name IN ('nota_sin_update', "
        "'politica_version_sin_update')").fetchall()
    for g in guardas:
        conn.execute(f"DROP TRIGGER {g['name']}")
    conn.execute("UPDATE nota SET texto = 'pagar a NL99 OTRO'")
    conn.execute("UPDATE politica_version SET contenido = 'obras: {}'")
    for g in guardas:
        conn.execute(g["sql"])
    problemas = verificar_evidencia(conn)
    assert any(p.startswith("nota ") and "texto" in p for p in problemas)
    assert any(p.startswith("politica_version ") and "sha256" in p for p in problemas)
