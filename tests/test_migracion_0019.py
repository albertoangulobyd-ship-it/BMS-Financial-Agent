"""La migracion 0019 (paso 18, diseno §3.9): el correo de facturas y la lectura automatica.

- Una base en 0018 con peticiones de lectura y pasadas en cada estado (y una viva, a medio
  leer) pasa a 0019 sin perder ni cambiar nada: las mismas filas, columna a columna,
  `PRAGMA foreign_key_check` vacio, la pasada apuntando a la peticion de verdad y los
  nombres exactos de 0018 en los indices y disparadores. El esquema que queda es el de una
  base nueva, texto a texto (lo que mira `db verificar`).
- Si algo falla (una persona que ya se llamara `correo`), la base se queda en 0018 entera.
- Lo que la 0019 garantiza por si misma: los dos usuarios de sistema nuevos, una
  automatica solo con su autorizacion (y ninguna persona le da el si), la autorizacion la
  firma una persona y con techos, el correo se apunta una vez por llegada, cada adjunto
  con su documento, y las exclusiones, pausas y correos atendidos los pone quien toca.

La base de partida se escribe con SQL a mano, no con lectura.py: lectura.py ya es el de la
0019 (y lo seguira cambiando), y lo que se prueba aqui es la migracion.
"""

from __future__ import annotations

import shutil
import sqlite3

import pytest

from bms_agent.almacen import USUARIOS_SISTEMA, abrir, transaccion, usuario_sistema
from bms_agent.almacen.evidencia import verificar_esquema, verificar_evidencia
from bms_agent.almacen.migrar import DIRECTORIO_SQL, disponibles, migrar
from bms_agent.auditoria import verificar_cadena
from conftest import persona

T = "2026-11-23T{}:00+00:00"
H1, H2, H3 = "1" * 64, "2" * 64, "3" * 64
SHA = "ab" * 32
TABLAS_REHECHAS = ("solicitud_lectura", "pasada_lectura")
# Los nombres de 0018 (diseno §3.9, punto 3.7), que la 0019 conserva.
NOMBRES_0018 = {
    ("table", "solicitud_lectura"), ("table", "pasada_lectura"),
    ("index", "solicitud_lectura_una_viva"), ("index", "solicitud_lectura_estado"),
    ("index", "sqlite_autoindex_pasada_lectura_1"),
    ("trigger", "solicitud_lectura_personas_alta"), ("trigger", "solicitud_lectura_personas"),
    ("trigger", "solicitud_lectura_fija"), ("trigger", "solicitud_lectura_terminada"),
    ("trigger", "solicitud_lectura_sin_delete"), ("trigger", "pasada_lectura_alta"),
    ("trigger", "pasada_lectura_avanza"), ("trigger", "pasada_lectura_sin_delete"),
}
NUEVAS = ("lectura_automatica", "mensaje_correo", "adjunto_correo", "exclusion_automatica",
          "pausa_lectura_automatica", "correo_atendido", "ronda_correo", "estado_correo",
          "estado_ciclo")


def _t(hora: str) -> str:
    return T.format(hora)


def _peticion(conn, origen: str, pedida_por: int | None, estado: str, en: str) -> int:
    return int(conn.execute(
        "INSERT INTO solicitud_lectura (origen, pedida_por, pedida_en, estado, tomada_en, "
        "actualizada_en) VALUES (?, ?, ?, ?, ?, ?)",
        (origen, pedida_por, en, estado, en if estado == "comprobando" else None, en)).lastrowid)


def _poner(conn, tabla: str, fila_id: int, **campos) -> None:
    columnas = ", ".join(f"{c} = ?" for c in campos)
    conn.execute(f"UPDATE {tabla} SET {columnas} WHERE id = ?", (*campos.values(), fila_id))


def _contada(conn, solicitud: int, en: str, *, huella: str = H1) -> None:
    _poner(conn, "solicitud_lectura", solicitud, estado="contando", actualizada_en=en)
    _poner(conn, "solicitud_lectura", solicitud, estado="esperando_aprobacion", pdf_nuevos=2,
           pdf_ya_leidos=1, coste_min_usd_micro=50_000, coste_max_usd_micro=120_000,
           huella_estimacion=huella, estimacion_json='{"documentos": 3}', contada_en=en,
           caduca_en=_t("23:59"), actualizada_en=en)


def _aprobada(conn, solicitud: int, via: str, por: int | None, en: str, *,
              autorizacion: int | None = None) -> None:
    campos = dict(estado="aprobada", aprobada_por=por, aprobada_en=en, aprobada_via=via,
                  tope_usd_micro=120_000, huella_aprobada=H1, actualizada_en=en)
    if autorizacion is not None:
        campos["autorizacion_id"] = autorizacion
    _poner(conn, "solicitud_lectura", solicitud, **campos)


def _leyendo(conn, solicitud: int, en: str) -> int:
    _poner(conn, "solicitud_lectura", solicitud, estado="leyendo", actualizada_en=en)
    return int(conn.execute(
        "INSERT INTO pasada_lectura (solicitud_id, fase, total, fases_json, empezada_en, "
        "actualizada_en) VALUES (?, 'cargando', 2, ?, ?, ?)",
        (solicitud, f'[{{"fase": "cargando", "en": "{en}"}}]', en, en)).lastrowid)


def _sembrar_0018(conn) -> dict[str, int]:
    """Dos personas y seis peticiones, con sus pasadas, en cada final posible y una viva."""
    ana, bob = persona(conn, "Ana", "administrador"), persona(conn, "Bob", "administracion")
    with transaccion(conn):
        # 1. Desde la app, aprobada por Ana y hecha.
        hecha = _peticion(conn, "app", ana, "pedida", _t("08:00"))
        _poner(conn, "solicitud_lectura", hecha, estado="comprobando", tomada_en=_t("08:01"),
               actualizada_en=_t("08:01"))
        _contada(conn, hecha, _t("08:02"))
        _aprobada(conn, hecha, "app", ana, _t("08:03"))
        pasada = _leyendo(conn, hecha, _t("08:04"))
        _poner(conn, "pasada_lectura", pasada, fase="hecha", leidas=2, coste_usd_micro=90_000,
               fases_json='[{"fase": "cargando", "en": "x"}, {"fase": "hecha", "en": "y"}]',
               resultado_json='[{"documento_id": 1, "nombre": "a.pdf", "estado": "leida"}]',
               terminada_en=_t("08:09"), actualizada_en=_t("08:09"))
        _poner(conn, "solicitud_lectura", hecha, estado="hecha", terminada_en=_t("08:09"),
               actualizada_en=_t("08:09"))
        # 2. Abierta en el lector, aceptada en su ventana y cancelada alli a medias.
        cancelada = _peticion(conn, "lector", None, "comprobando", _t("09:00"))
        _contada(conn, cancelada, _t("09:01"))
        _aprobada(conn, cancelada, "ventana", None, _t("09:02"))
        pasada = _leyendo(conn, cancelada, _t("09:03"))
        _poner(conn, "solicitud_lectura", cancelada, cancelada_en=_t("09:04"),
               cancelada_via="ventana", actualizada_en=_t("09:04"))
        _poner(conn, "pasada_lectura", pasada, fase="cancelada", leidas=1,
               coste_usd_micro=40_000, motivo="parada en la ventana",
               terminada_en=_t("09:05"), actualizada_en=_t("09:05"))
        _poner(conn, "solicitud_lectura", cancelada, estado="cancelada",
               motivo="parada en la ventana", terminada_en=_t("09:05"),
               actualizada_en=_t("09:05"))
        # 3. Pedida por Bob y caducada sin respuesta.
        caducada = _peticion(conn, "app", bob, "pedida", _t("10:00"))
        _contada(conn, caducada, _t("10:01"), huella=H2)
        _poner(conn, "solicitud_lectura", caducada, estado="caducada", motivo="sin respuesta",
               terminada_en=_t("10:20"), actualizada_en=_t("10:20"))
        # 4. El lector sin nada nuevo que leer.
        nada = _peticion(conn, "lector", None, "comprobando", _t("11:00"))
        _poner(conn, "solicitud_lectura", nada, estado="nada_que_leer", motivo_codigo="ya_leidas",
               pdf_nuevos=0, pdf_ya_leidos=3, terminada_en=_t("11:01"),
               actualizada_en=_t("11:01"))
        # 5. Aprobada desde la app, cancelada por Ana desde alli y la pasada fallida.
        fallida = _peticion(conn, "app", ana, "pedida", _t("12:00"))
        _contada(conn, fallida, _t("12:01"), huella=H3)
        _aprobada(conn, fallida, "app", ana, _t("12:02"))
        pasada = _leyendo(conn, fallida, _t("12:03"))
        _poner(conn, "solicitud_lectura", fallida, cancelada_por=ana, cancelada_en=_t("12:04"),
               cancelada_via="app", actualizada_en=_t("12:04"))
        _poner(conn, "pasada_lectura", pasada, fase="fallida", fallidas=2,
               coste_usd_micro=120_000, motivo="la API no contesto",
               terminada_en=_t("12:05"), actualizada_en=_t("12:05"))
        _poner(conn, "solicitud_lectura", fallida, estado="fallida", motivo_codigo="lectura",
               motivo="la API no contesto", terminada_en=_t("12:05"),
               actualizada_en=_t("12:05"))
        # 6. Viva: aprobada por Bob, leyendo el segundo documento.
        viva = _peticion(conn, "app", bob, "pedida", _t("13:00"))
        _contada(conn, viva, _t("13:01"))
        _aprobada(conn, viva, "app", bob, _t("13:02"))
        pasada = _leyendo(conn, viva, _t("13:03"))
        _poner(conn, "pasada_lectura", pasada, fase="leyendo", leidas=1,
               coste_usd_micro=30_000, documento_actual="b.pdf", documento_fase="leyendo",
               resultado_json='[{"documento_id": 1, "nombre": "a.pdf", "estado": "leida"}]',
               actualizada_en=_t("13:04"))
    return {"ana": ana, "bob": bob, "viva": viva, "hecha": hecha, "pasada_viva": pasada}


def _sql_hasta(carpeta, version: int):
    """Las migraciones hasta `version`, en su carpeta: lo que se prueba es la 0019, aunque
    despues lleguen otras."""
    carpeta.mkdir()
    for migracion in disponibles():
        if migracion.version <= version:
            shutil.copy2(DIRECTORIO_SQL / migracion.nombre, carpeta / migracion.nombre)
    return carpeta


@pytest.fixture
def base_0018(tmp_path, reloj):
    """Una base de verdad (en disco, con claves foraneas) migrada hasta la 0018, con datos, y
    la carpeta de las migraciones hasta la 0019."""
    conn = abrir(tmp_path / "bms.sqlite3", reloj=reloj)
    try:
        assert [m.version for m in migrar(conn, _sql_hasta(tmp_path / "sql-0018", 18))][-1] == 18
        ids = _sembrar_0018(conn)
        yield conn, ids, _sql_hasta(tmp_path / "sql-0019", 19)
    finally:
        conn.close()


def _filas(conn, tabla: str) -> list[dict]:
    return [dict(f) for f in conn.execute(f"SELECT * FROM {tabla} ORDER BY id")]


def _objetos(conn, tablas=TABLAS_REHECHAS) -> set[tuple[str, str]]:
    marcas = ", ".join("?" * len(tablas))
    return {(f[0], f[1]) for f in conn.execute(
        f"SELECT type, name FROM sqlite_master WHERE tbl_name IN ({marcas})", tablas)}


def _esquema(conn) -> dict[tuple[str, str], tuple[str, str | None]]:
    return {(f[0], f[1]): (f[2], f[3]) for f in conn.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master")}


# ------------------------------------------------------------ la migracion, con datos

def test_la_0019_rehace_las_dos_tablas_sin_perder_ni_cambiar_nada(base_0018) -> None:
    conn, _ids, hasta_0019 = base_0018
    antes = {t: _filas(conn, t) for t in TABLAS_REHECHAS}
    assert [len(antes[t]) for t in TABLAS_REHECHAS] == [6, 4]
    assert _objetos(conn) == NOMBRES_0018

    assert [m.nombre for m in migrar(conn, hasta_0019)] == ["0019_correo.sql"]

    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    despues = {t: _filas(conn, t) for t in TABLAS_REHECHAS}
    for fila in despues["solicitud_lectura"]:
        assert fila.pop("autorizacion_id") is None
    assert despues == antes                         # fila a fila, columna a columna
    # La pasada apunta a la peticion de verdad, no a la tabla nueva que ya no existe.
    assert [(f["table"], f["from"], f["to"]) for f in conn.execute(
        "PRAGMA foreign_key_list(pasada_lectura)")] == [("solicitud_lectura", "solicitud_id",
                                                         "id")]
    referencias = {(f["table"], f["from"]) for f in conn.execute(
        "PRAGMA foreign_key_list(solicitud_lectura)")}
    assert ("lectura_automatica", "autorizacion_id") in referencias
    # Los mismos nombres de 0018, y nada que se llame _nueva.
    assert _objetos(conn) == NOMBRES_0018
    assert not [f[0] for f in conn.execute("SELECT name, sql FROM sqlite_master")
                if "lectura_nueva" in f[0] or "lectura_nueva" in (f[1] or "")]
    assert set(NUEVAS) <= {f[0] for f in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_el_esquema_migrado_con_datos_es_el_de_una_base_nueva(base_0018, tmp_path) -> None:
    conn, _ids, hasta_0019 = base_0018
    migrar(conn, hasta_0019)
    nueva = abrir(tmp_path / "nueva.sqlite3")
    try:
        migrar(nueva, hasta_0019)
        assert _esquema(conn) == _esquema(nueva)
    finally:
        nueva.close()
    # Lo que mira `db verificar`: el esquema de las migraciones, texto a texto, la evidencia
    # con su auditoria (la 0019 con su evento) y la cadena.
    assert verificar_esquema(conn, hasta_0019) == []
    assert verificar_evidencia(conn) == []
    assert verificar_cadena(conn).ok
    assert conn.execute("SELECT count(*) FROM evento WHERE tipo = 'migracion_aplicada' "
                        "AND fila_id = 19").fetchone()[0] == 1


def test_los_usuarios_de_sistema_nuevos_van_detras_de_las_personas(base_0018) -> None:
    conn, ids, hasta_0019 = base_0018
    migrar(conn, hasta_0019)
    sistema = [(f["id"], f["nombre"]) for f in conn.execute(
        "SELECT id, nombre FROM usuario WHERE es_sistema = 1 ORDER BY id")]
    assert [n for _i, n in sistema] == list(USUARIOS_SISTEMA)
    assert dict((n, i) for i, n in sistema)["correo"] > max(ids["ana"], ids["bob"])
    for nombre in ("correo", "automatico"):
        quien = usuario_sistema(conn, nombre)
        with pytest.raises(sqlite3.IntegrityError, match="sistema no puede tener roles"):
            conn.execute("INSERT INTO usuario_rol (usuario_id, rol_id, desde) VALUES (?, 1, ?)",
                         (quien, _t("14:00")))
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            conn.execute("UPDATE usuario SET token_sha256 = ? WHERE id = ?", (H1, quien))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE usuario SET nombre = 'otro' WHERE id = ?", (quien,))


def test_la_lectura_viva_sigue_y_los_disparadores_de_0018_tambien(base_0018) -> None:
    from bms_agent import lectura

    conn, ids, _hasta_0019 = base_0018
    migrar(conn)                                    # con todas: lo que hace una instalacion
    viva, pasada = ids["viva"], ids["pasada_viva"]
    assert lectura.viva(conn)["id"] == viva
    assert lectura.para_la_app(conn)["pasada_en_curso"]["documento_actual"] == "b.pdf"
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):     # una viva, una sola
        _peticion(conn, "lector", None, "comprobando", _t("14:00"))
    with pytest.raises(sqlite3.IntegrityError, match="solo avanza"):
        _poner(conn, "pasada_lectura", pasada, coste_usd_micro=10)
    with pytest.raises(sqlite3.IntegrityError, match="no se cambian"):
        _poner(conn, "solicitud_lectura", viva, tope_usd_micro=100_000)
    with transaccion(conn):
        _poner(conn, "pasada_lectura", pasada, fase="hecha", leidas=2, coste_usd_micro=70_000,
               documento_actual=None, documento_fase=None, terminada_en=_t("14:01"),
               actualizada_en=_t("14:01"))
        _poner(conn, "solicitud_lectura", viva, estado="hecha", terminada_en=_t("14:01"),
               actualizada_en=_t("14:01"))
    assert lectura.viva(conn) is None
    with pytest.raises(sqlite3.IntegrityError, match="terminada no cambia"):
        _poner(conn, "solicitud_lectura", ids["hecha"], motivo="otro")
    with pytest.raises(sqlite3.IntegrityError, match="no se borra"):
        conn.execute("DELETE FROM solicitud_lectura WHERE id = ?", (viva,))
    with pytest.raises(sqlite3.IntegrityError, match="no se borra"):
        conn.execute("DELETE FROM pasada_lectura")
    with pytest.raises(sqlite3.IntegrityError, match="nace pedida"):
        conn.execute("INSERT INTO solicitud_lectura (origen, pedida_por, pedida_en, estado, "
                     "actualizada_en) VALUES ('app', ?, ?, 'aprobada', ?)",
                     (ids["ana"], _t("14:02"), _t("14:02")))
    with pytest.raises(sqlite3.IntegrityError, match="la pide una persona"):
        conn.execute("INSERT INTO solicitud_lectura (origen, pedida_por, pedida_en, estado, "
                     "actualizada_en) VALUES ('app', ?, ?, 'pedida', ?)",
                     (usuario_sistema(conn, "automatico"), _t("14:02"), _t("14:02")))


def test_una_0019_que_falla_deja_la_base_en_0018_entera(base_0018) -> None:
    """Una persona que ya se llamara `correo` (antes del paso 18 el nombre no estaba
    reservado): la migracion para y no deja nada a medias."""
    conn, _ids, hasta_0019 = base_0018
    conn.execute("INSERT INTO usuario (nombre, creado_en) VALUES ('correo', ?)", (_t("14:00"),))
    antes = {t: _filas(conn, t) for t in TABLAS_REHECHAS}
    esquema = _esquema(conn)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        migrar(conn, hasta_0019)
    assert not conn.in_transaction
    assert conn.execute("SELECT max(version) FROM migracion").fetchone()[0] == 18
    assert _esquema(conn) == esquema
    assert {t: _filas(conn, t) for t in TABLAS_REHECHAS} == antes
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


# ------------------------------------------------------------ lo que la 0019 garantiza

def _personas(db) -> tuple[int, int]:
    return persona(db, "Ana", "administrador"), persona(db, "Bob", "administracion")


def _autorizacion(db, por: int, **cambios) -> int:
    valores = dict(activa=1, tope_dia_usd_micro=2_000_000, tope_mes_usd_micro=25_000_000,
                   max_documentos=20, max_por_documento_usd_micro=500_000, fijada_por=por,
                   fijada_en=_t("07:00"), motivo="encendida")
    valores.update(cambios)
    columnas = ", ".join(valores)
    return int(db.execute(
        f"INSERT INTO lectura_automatica ({columnas}) VALUES ({', '.join('?' * len(valores))})",
        tuple(valores.values())).lastrowid)


def test_la_autorizacion_la_firma_una_persona_y_tiene_techos(db) -> None:
    ana, _bob = _personas(db)
    primera = _autorizacion(db, ana)
    assert _autorizacion(db, ana, activa=0, motivo="apagada") == primera + 1
    with pytest.raises(sqlite3.IntegrityError, match="la autoriza una persona"):
        _autorizacion(db, usuario_sistema(db, "automatico"))
    with pytest.raises(sqlite3.IntegrityError, match="la autoriza una persona"):
        _autorizacion(db, usuario_sistema(db, "sistema"))
    for malos in ({"activa": 2}, {"tope_dia_usd_micro": 0}, {"tope_dia_usd_micro": 20_000_001},
                  {"tope_mes_usd_micro": 1_999_999}, {"tope_mes_usd_micro": 200_000_001},
                  {"max_documentos": 0}, {"max_documentos": 101},
                  {"max_por_documento_usd_micro": 0},
                  {"max_por_documento_usd_micro": 2_000_001}, {"fijada_en": "ayer"}):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _autorizacion(db, ana, **malos)
    # En el techo, entra.
    _autorizacion(db, ana, tope_dia_usd_micro=20_000_000, tope_mes_usd_micro=200_000_000,
                  max_documentos=100, max_por_documento_usd_micro=20_000_000)
    with pytest.raises(sqlite3.IntegrityError, match="evidencia: no se modifica"):
        db.execute("UPDATE lectura_automatica SET activa = 0 WHERE id = ?", (primera,))
    with pytest.raises(sqlite3.IntegrityError, match="evidencia: no se borra"):
        db.execute("DELETE FROM lectura_automatica")


def _automatica_esperando(db) -> int:
    automatica = _peticion(db, "automatica", None, "comprobando", _t("08:00"))
    _contada(db, automatica, _t("08:01"))
    return automatica


def test_una_automatica_solo_la_acepta_su_autorizacion(db) -> None:
    ana, _bob = _personas(db)
    autorizacion = _autorizacion(db, ana)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):      # nadie la pide
        _peticion(db, "automatica", ana, "comprobando", _t("08:00"))
    automatica = _automatica_esperando(db)
    for via, por, autorizada in (("automatica", None, None), ("app", ana, None),
                                 ("app", ana, autorizacion), ("ventana", None, None)):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _aprobada(db, automatica, via, por, _t("08:02"), autorizacion=autorizada)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):      # sin si, sin autorizacion
        _poner(db, "solicitud_lectura", automatica, autorizacion_id=autorizacion)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        _aprobada(db, automatica, "automatica", None, _t("08:02"), autorizacion=999)
    _aprobada(db, automatica, "automatica", None, _t("08:02"), autorizacion=autorizacion)
    fila = db.execute("SELECT * FROM solicitud_lectura WHERE id = ?", (automatica,)).fetchone()
    assert (fila["aprobada_por"], fila["aprobada_via"], fila["autorizacion_id"]) == (
        None, "automatica", autorizacion)
    otra = _autorizacion(db, ana, motivo="otro tope")
    with pytest.raises(sqlite3.IntegrityError, match="no se cambian"):
        _poner(db, "solicitud_lectura", automatica, autorizacion_id=otra)
    _poner(db, "solicitud_lectura", automatica, estado="nada_que_leer", motivo_codigo="excluidas",
           terminada_en=_t("08:03"), actualizada_en=_t("08:03"))
    # La de una persona no se acepta con una autorizacion.
    de_ana = _peticion(db, "app", ana, "pedida", _t("09:00"))
    _contada(db, de_ana, _t("09:01"))
    for via, por in (("automatica", None), ("automatica", ana)):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _aprobada(db, de_ana, via, por, _t("09:02"), autorizacion=autorizacion)
    _aprobada(db, de_ana, "app", ana, _t("09:02"))


@pytest.mark.parametrize("motivo", ["limite_dia", "limite_mes", "excluidas", "sin_autorizacion",
                                    "saldo", "clave_rechazada", "api_no_disponible"])
def test_los_motivos_nuevos_de_una_peticion_que_termina(db, motivo) -> None:
    peticion = _peticion(db, "automatica", None, "comprobando", _t("08:00"))
    _poner(db, "solicitud_lectura", peticion, estado="fallida", motivo_codigo=motivo,
           terminada_en=_t("08:01"), actualizada_en=_t("08:01"))
    otra = _peticion(db, "lector", None, "comprobando", _t("08:02"))
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        _poner(db, "solicitud_lectura", otra, estado="fallida", motivo_codigo="otro_motivo",
               terminada_en=_t("08:03"), actualizada_en=_t("08:03"))


def _documento(db, sha: str = SHA) -> int:
    return int(db.execute(
        "INSERT INTO documento (sha256, nombre_original, tipo_mime, origen, ruta_declarada, "
        "mensaje_id, recibido_en, recibido_fuente, registrado_en, registrado_por) VALUES "
        "(?, 'f.pdf', 'application/pdf', 'correo', 'entrante', '<1@ejemplo.test>', ?, "
        "'correo', ?, ?)", (sha, _t("08:14"), _t("08:16"), usuario_sistema(db, "correo"))
    ).lastrowid)


def _mensaje(db, graph_id: str = "AAMkAGI2THVSAAA=", carpeta: str = "bandeja", **cambios) -> int:
    valores = dict(graph_id=graph_id, carpeta=carpeta,
                   internet_message_id_doc="<1@ejemplo.test>", recibido_en=_t("08:14"),
                   remitente_doc="facturen@proveedor.example", asunto_doc="Factuur 2026-0412",
                   adjuntos=1, en_linea=2, traido_en=_t("08:15"), registrado_en=_t("08:16"),
                   registrado_por=usuario_sistema(db, "correo"))
    valores.update(cambios)
    return int(db.execute(
        f"INSERT INTO mensaje_correo ({', '.join(valores)}) "
        f"VALUES ({', '.join('?' * len(valores))})", tuple(valores.values())).lastrowid)


def _adjunto(db, mensaje: int, graph_adjunto_id: str = "AAMkAd1", **cambios) -> int:
    valores = dict(mensaje_id=mensaje, graph_adjunto_id=graph_adjunto_id,
                   nombre_doc="factuur-0412.pdf", tipo_declarado_doc="application/pdf",
                   bytes=81234, sha256=None, resultado="no_pdf", documento_id=None)
    valores.update(cambios)
    return int(db.execute(
        f"INSERT INTO adjunto_correo ({', '.join(valores)}) "
        f"VALUES ({', '.join('?' * len(valores))})", tuple(valores.values())).lastrowid)


def test_el_correo_se_apunta_una_vez_por_llegada(db) -> None:
    bandeja = _mensaje(db)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        _mensaje(db)
    # El mismo mensaje en "no deseado" y despues en la bandeja: dos llegadas (diseno §3.4).
    assert _mensaje(db, carpeta="no_deseado") != bandeja
    for malos in ({"graph_id": "a b"}, {"graph_id": "../x"}, {"graph_id": ""},
                  {"graph_id": "A" * 513}, {"carpeta": "enviados"}, {"recibido_en": "ayer"},
                  {"asunto_doc": "x" * 201}, {"remitente_doc": "x" * 321},
                  {"internet_message_id_doc": "x" * 999}, {"adjuntos": -1}):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _mensaje(db, graph_id=malos.pop("graph_id", "AQMkOtro"), **malos)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        _mensaje(db, graph_id="AQMkSinUsuario", registrado_por=999)


def test_cada_adjunto_con_lo_que_se_hizo_y_su_documento(db) -> None:
    mensaje, documento = _mensaje(db), _documento(db)
    _adjunto(db, mensaje, resultado="documento", sha256=SHA, documento_id=documento)
    # El mismo PDF en otro mensaje: el mismo documento, otra llegada.
    otro = _mensaje(db, graph_id="AQMkOtroMensaje")
    _adjunto(db, otro, resultado="documento", sha256=SHA, documento_id=documento)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        _adjunto(db, mensaje, resultado="xml")
    for malos in ({"resultado": "documento"}, {"resultado": "documento", "sha256": SHA},
                  {"resultado": "no_pdf", "documento_id": documento, "sha256": SHA},
                  {"resultado": "pdf"}, {"sha256": "AB" * 32}, {"sha256": "ab"},
                  {"nombre_doc": "x" * 256}, {"bytes": -1}):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _adjunto(db, mensaje, "AAMkOtro", **malos)
    for otro_sha in ("cd" * 32, None):
        with pytest.raises(sqlite3.IntegrityError, match="el de su sha256"):
            _adjunto(db, mensaje, "AAMkOtro", resultado="documento", sha256=otro_sha,
                     documento_id=documento)
    for resultado in ("no_es_pdf", "demasiado_grande", "xml", "reenvio", "no_pdf", "enlace",
                      "no_deseado", "de_prueba", "error"):
        _adjunto(db, mensaje, f"AAMk{resultado}", resultado=resultado)


def test_exclusiones_pausas_y_atendidos_los_pone_quien_toca(db) -> None:
    ana, _bob = _personas(db)
    automatico = usuario_sistema(db, "automatico")
    documento, otro = _documento(db), _documento(db, "cd" * 32)
    peticion = _peticion(db, "automatica", None, "comprobando", _t("08:00"))

    def excluir(doc, motivo, por, solicitud):
        db.execute("INSERT INTO exclusion_automatica (documento_id, motivo_codigo, "
                   "solicitud_id, por, en) VALUES (?, ?, ?, ?, ?)",
                   (doc, motivo, solicitud, por, _t("08:05")))

    for doc, motivo, por, solicitud, error in (
            (documento, "persona", automatico, None, "la pone una persona"),
            (documento, "grande", ana, peticion, "la pone una persona"),
            (documento, "grande", automatico, None, "CHECK"),
            (documento, "persona", ana, peticion, "CHECK"),
            (documento, "otro", automatico, peticion, "CHECK")):
        with pytest.raises(sqlite3.IntegrityError, match=error):
            excluir(doc, motivo, por, solicitud)
    excluir(documento, "persona", ana, None)
    excluir(otro, "rechazado_api", automatico, peticion)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):     # una vez y para siempre
        excluir(documento, "fallo", automatico, peticion)

    def pausa(tipo, motivo, por, *, hasta=None, solicitud=None):
        db.execute("INSERT INTO pausa_lectura_automatica (tipo, motivo, solicitud_id, por, en, "
                   "hasta) VALUES (?, ?, ?, ?, ?, ?)",
                   (tipo, motivo, solicitud, por, _t("08:10"), hasta))

    manana = "2026-11-23T23:00:00+00:00"
    for tipo, motivo, por, hasta, solicitud, error in (
            ("pausa", "volumen", ana, None, None, "la pone el sistema"),
            ("pausa", "persona", automatico, manana, peticion, "la pone el sistema"),
            ("reanuda", None, automatico, None, None, "la pone el sistema"),
            ("pausa", "persona", ana, None, peticion, "CHECK"),
            ("pausa", "volumen", automatico, manana, None, "CHECK"),
            ("pausa", None, ana, None, None, "CHECK"),
            ("reanuda", "persona", ana, manana, None, "CHECK"),
            ("pausa", "persona", ana, _t("08:00"), peticion, "CHECK"),
            ("pausa", "volumen", automatico, None, peticion, "CHECK")):
        with pytest.raises(sqlite3.IntegrityError, match=error):
            pausa(tipo, motivo, por, hasta=hasta, solicitud=solicitud)
    pausa("pausa", "persona", ana, hasta=manana, solicitud=peticion)
    pausa("reanuda", None, ana)
    pausa("pausa", "volumen", automatico)

    mensaje = _mensaje(db)

    def atendido(por, nota="mirado en Outlook"):
        db.execute("INSERT INTO correo_atendido (mensaje_id, por, en, nota) VALUES (?, ?, ?, ?)",
                   (mensaje, por, _t("09:00"), nota))

    with pytest.raises(sqlite3.IntegrityError, match="una persona"):
        atendido(usuario_sistema(db, "correo"))
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        atendido(ana, "x" * 501)
    atendido(ana)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        atendido(ana)


def test_una_ronda_del_correo_falla_con_un_codigo_de_la_lista(db) -> None:
    def ronda(resultado, codigo):
        db.execute("INSERT INTO ronda_correo (empezada_en, terminada_en, resultado, "
                   "error_codigo, mensajes, documentos_nuevos, registrada_en) "
                   "VALUES (?, ?, ?, ?, 2, 1, ?)",
                   (_t("08:00"), _t("08:01"), resultado, codigo, _t("08:02")))

    ronda("bien", None)
    for codigo in ("sin_configurar", "credencial", "reloj", "permiso", "alcance",
                   "control_no_existe", "sin_conexion", "limitado", "aislamiento", "salida",
                   "disco", "interno"):
        ronda("fallo", codigo)
    for resultado, codigo in (("fallo", None), ("bien", "disco"), ("fallo", "ocupado"),
                              ("regular", None)):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            ronda(resultado, codigo)


def test_las_caches_del_correo_y_del_ciclo_son_una_fila_que_se_reescribe(db) -> None:
    db.execute("INSERT INTO estado_correo (id, buzon, ultima_consulta, error_codigo, "
               "error_desde, hoy_json, actualizado_en) VALUES (1, 'facturen@ejemplo.test', ?, "
               "'limitado', ?, ?, ?)",
               (_t("08:00"), _t("07:55"), '{"fecha": "2026-11-23", "pdf": 1}', _t("08:00")))
    db.execute("UPDATE estado_correo SET error_codigo = NULL, error_desde = NULL, "
               "ultima_buena = ?, actualizado_en = ? WHERE id = 1", (_t("08:05"), _t("08:05")))
    for sql, valores in (
            ("INSERT INTO estado_correo (id, actualizado_en) VALUES (2, ?)", (_t("08:06"),)),
            ("UPDATE estado_correo SET error_codigo = 'disco'", ()),
            ("UPDATE estado_correo SET error_codigo = 'roto', error_desde = ?", (_t("08:06"),)),
            ("UPDATE estado_correo SET hoy_json = 'no es json'", ()),
            ("UPDATE estado_correo SET alcance_bien = 1", ()),
            ("UPDATE estado_correo SET aviso_volumen = 2", ())):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            db.execute(sql, valores)
    db.execute("INSERT INTO estado_ciclo (id, visto_en, variante, disco_libre_bytes, "
               "actualizado_en) VALUES (1, ?, 'docker', ?, ?)",
               (_t("08:00"), 50 * 2**30, _t("08:00")))
    db.execute("UPDATE estado_ciclo SET pausado = 1, pausado_desde = ?", (_t("08:10"),))
    for sql in ("INSERT INTO estado_ciclo (id, visto_en, actualizado_en) "
                "VALUES (2, '2026-11-23', '2026-11-23')",
                "UPDATE estado_ciclo SET variante = 'windows'",
                "UPDATE estado_ciclo SET pausado = 0",
                "UPDATE estado_ciclo SET disco_libre_bytes = -1"):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            db.execute(sql)
    db.execute("DELETE FROM estado_ciclo")                       # una cache, no evidencia
