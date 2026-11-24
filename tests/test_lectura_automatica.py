"""La lectura automatica (paso 18, diseno §5; lectura_automatica.py y lectura.py).

Puertas que viven aqui:

- la autorizacion la firma una persona con admin, cada cambio es una fila nueva (la vigente es
  la ultima) y la base no la deja cambiar, borrar ni pasar de sus techos;
- lo gastado cuenta por dia y por mes de Amsterdam, tambien el dia del cambio de hora, y solo
  lo de las automaticas;
- las pausas: la de una persona dura hasta las 00:00 del dia siguiente (o hasta reanudarla); la
  de volumen, una vez al dia y hasta que una persona la quite;
- tras un fallo tecnico se espera 1 h, y el doble tras cada uno seguido, como mucho 24 h;
- lo que se puede leer solo (elegibles) y lo que espera a una persona (esperan_persona), y las
  exclusiones en bloque;
- las cuatro ordenes nuevas, con su permiso;
- y, con el paso 5, la lectura automatica entera con el cliente falso, leyendo del almacen.

Ningun test llama a la API ni a Microsoft: el correo se apunta en la base a mano.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from conftest import persona

from bms_agent import lectura_automatica as auto
from bms_agent import servicios
from bms_agent.almacen import transaccion, usuario_sistema
from bms_agent.almacen.documentos import registrar_documento
from bms_agent.almacen.evidencia import verificar_evidencia
from bms_agent.almacen.extracciones import leer_registro, registrar_extraccion
from bms_agent.almacen.unidades import sha256_bytes
from bms_agent.lectura import EstadoNoValido
from bms_agent.permisos import PermisoDenegado
from bms_agent.reloj import marca

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
UTC = timezone.utc
POR_DEFECTO = dict(activa=1, **auto.POR_DEFECTO)


@pytest.fixture
def gente(almacen):
    conn = almacen.conn
    return {"ana": persona(conn, "Ana", "administrador"),
            "berta": persona(conn, "Berta", "administracion"),
            "carla": persona(conn, "Carla", "consulta")}


def _fijar(conn, quien, **valores) -> int:
    diferencia = servicios.ejecutar(conn, "fijar_lectura_automatica",
                                    {**POR_DEFECTO, "motivo": "Las del correo, solas", **valores},
                                    usuario_id=quien)
    return diferencia.detalle["autorizacion_id"]


# ------------------------------------------------------------ el correo, a mano

_GRAPH = iter(range(1, 10_000))


def _documento(almacen, marca_pdf: str, *, original: bool = True) -> int:
    """Un PDF que trajo el correo, en el almacen (o solo apuntado, sin su original)."""
    contenido = PDF + f"%marca:{marca_pdf}\n".encode()
    with transaccion(almacen.conn):
        return registrar_documento(
            almacen, sha256=sha256_bytes(contenido), contenido=contenido if original else None,
            nombre_original=f"{marca_pdf}.pdf", tipo_mime="application/pdf", origen="correo",
            ruta_declarada="entrante", recibido_en="2026-10-14T08:00:00+00:00",
            recibido_fuente="correo", actor=usuario_sistema(almacen.conn, "correo"),
            mensaje_id="<x@ejemplo.test>").id


def _correo(conn, recibido_en: str, *adjuntos: tuple, carpeta: str = "bandeja",
            graph_id: str | None = None, asunto: str | None = "Factuur") -> int:
    """Un mensaje del buzon, registrado, con sus adjuntos: (resultado, documento_id) o
    (resultado, documento_id, nombre)."""
    graph_id = graph_id or f"AAMkAG{next(_GRAPH)}"
    correo = usuario_sistema(conn, "correo")
    with transaccion(conn):
        mensaje = conn.execute(
            "INSERT INTO mensaje_correo (graph_id, carpeta, recibido_en, remitente_doc, "
            "asunto_doc, adjuntos, en_linea, traido_en, registrado_en, registrado_por) "
            "VALUES (?, ?, ?, 'facturen@proveedor.example', ?, ?, 0, ?, ?, ?)",
            (graph_id, carpeta, recibido_en, asunto, len(adjuntos), recibido_en, recibido_en,
             correo)).lastrowid
        for i, adjunto in enumerate(adjuntos):
            resultado, documento_id = adjunto[:2]
            nombre = adjunto[2] if len(adjunto) > 2 else f"adjunto-{i}.pdf"
            sha = None
            if documento_id is not None:
                sha = conn.execute("SELECT sha256 FROM documento WHERE id = ?",
                                   (documento_id,)).fetchone()[0]
            conn.execute(
                "INSERT INTO adjunto_correo (mensaje_id, graph_adjunto_id, nombre_doc, bytes, "
                "sha256, resultado, documento_id) VALUES (?, ?, ?, 100, ?, ?, ?)",
                (mensaje, f"AAMkAd{i}", nombre, sha, resultado, documento_id))
    return mensaje


def _leido(conn, documento_id: int) -> None:
    """El documento ya tiene su extraccion (vigente)."""
    sha = conn.execute("SELECT sha256 FROM documento WHERE id = ?", (documento_id,)).fetchone()[0]
    texto = ('{"source_sha256": "%s", "model": "m", "prompt_version": "p", '
             '"schema_version": "1", "extraction": {}}' % sha)
    with transaccion(conn):
        registrar_extraccion(conn, leer_registro(texto), documento_id=documento_id, via="api",
                             actor=usuario_sistema(conn, "extractor"))


# ------------------------------------------------------------ peticiones hechas a mano

def _automatica(conn, empezada: str, coste: int, *, autorizacion: int,
                via: str = "automatica", quien: int | None = None) -> int:
    """Una lectura aceptada cuya pasada empezo en `empezada` y gasto `coste`, por SQL (con los
    mismos CHECK y disparadores que la de verdad). `via` app: la acepto una persona."""
    with transaccion(conn):
        origen = "automatica" if via == "automatica" else "app"
        solicitud = conn.execute(
            "INSERT INTO solicitud_lectura (origen, pedida_por, pedida_en, estado, tomada_en, "
            "actualizada_en) VALUES (?, ?, ?, 'comprobando', ?, ?)",
            (origen, quien, empezada, empezada, empezada)).lastrowid
        conn.execute(
            "UPDATE solicitud_lectura SET estado = 'esperando_aprobacion', pdf_nuevos = 1, "
            "pdf_ya_leidos = 0, coste_min_usd_micro = 1, coste_max_usd_micro = ?, "
            "huella_estimacion = ?, caduca_en = ? WHERE id = ?",
            (max(coste, 1), "a" * 64, empezada, solicitud))
        conn.execute(
            "UPDATE solicitud_lectura SET estado = 'aprobada', aprobada_en = ?, aprobada_via = ?, "
            "aprobada_por = ?, autorizacion_id = ?, tope_usd_micro = ?, huella_aprobada = ? "
            "WHERE id = ?",
            (empezada, via, quien if via == "app" else None,
             autorizacion if via == "automatica" else None, max(coste, 1), "a" * 64, solicitud))
        pasada = conn.execute(
            "INSERT INTO pasada_lectura (solicitud_id, fase, empezada_en, actualizada_en) "
            "VALUES (?, 'cargando', ?, ?)", (solicitud, empezada, empezada)).lastrowid
        conn.execute("UPDATE pasada_lectura SET coste_usd_micro = ?, fase = 'hecha', "
                     "terminada_en = ? WHERE id = ?", (coste, empezada, pasada))
        conn.execute("UPDATE solicitud_lectura SET estado = 'leyendo' WHERE id = ?", (solicitud,))
        conn.execute("UPDATE solicitud_lectura SET estado = 'hecha', terminada_en = ? "
                     "WHERE id = ?", (empezada, solicitud))
    return solicitud


def _terminada(conn, terminada: str, estado: str = "fallida", motivo_codigo: str | None = None,
               origen: str = "automatica") -> int:
    """Una automatica que termino sin leer (fallida con su motivo, o nada_que_leer)."""
    with transaccion(conn):
        solicitud = conn.execute(
            "INSERT INTO solicitud_lectura (origen, pedida_en, estado, tomada_en, "
            "actualizada_en) VALUES (?, ?, 'comprobando', ?, ?)",
            (origen, terminada, terminada, terminada)).lastrowid
        conn.execute("UPDATE solicitud_lectura SET estado = ?, motivo_codigo = ?, "
                     "terminada_en = ? WHERE id = ?", (estado, motivo_codigo, terminada,
                                                       solicitud))
    return solicitud


# ============================================================ la autorizacion

def test_la_autorizacion_la_firma_una_persona_con_admin(almacen, gente) -> None:
    conn = almacen.conn
    assert auto.vigente(conn) is None and auto.encendida(conn) is None
    primera = _fijar(conn, gente["ana"])
    fila = auto.vigente(conn)
    assert (fila["id"], fila["activa"], fila["fijada_por"]) == (primera, 1, gente["ana"])
    assert {k: fila[k] for k in auto.POR_DEFECTO} == auto.POR_DEFECTO
    evento = conn.execute("SELECT * FROM evento WHERE tipo = 'lectura_automatica_fijada'"
                          ).fetchone()
    assert (evento["actor"], evento["usuario_id"], evento["tabla"], evento["fila_id"],
            evento["motivo"]) == (gente["ana"], gente["ana"], "lectura_automatica", primera,
                                  "Las del correo, solas")
    # Apagarla es otra fila: la vigente es la ultima, y la de antes no cambia.
    segunda = _fijar(conn, gente["ana"], activa=0, motivo="De vacaciones")
    assert auto.vigente(conn)["id"] == segunda and auto.encendida(conn) is None
    assert conn.execute("SELECT activa FROM lectura_automatica WHERE id = ?",
                        (primera,)).fetchone()[0] == 1
    # Sin admin no (quien pide lecturas tampoco), y sin motivo tampoco.
    for quien in (gente["berta"], gente["carla"]):
        with pytest.raises(PermisoDenegado):
            _fijar(conn, quien)
    with pytest.raises(servicios.FaltaMotivo):
        _fijar(conn, gente["ana"], motivo="  ")
    # Ningun usuario de sistema, ni por la orden ni por detras de ella.
    automatico = usuario_sistema(conn, "automatico")
    with pytest.raises(PermisoDenegado, match="usuario de sistema"):
        _fijar(conn, automatico)
    with pytest.raises(sqlite3.IntegrityError, match="la autoriza una persona"):
        auto.fijar(conn, automatico, **POR_DEFECTO)
    assert conn.execute("SELECT count(*) FROM lectura_automatica").fetchone()[0] == 2
    # Ni se cambia ni se borra.
    with pytest.raises(sqlite3.IntegrityError, match="solo escritura"):
        conn.execute("UPDATE lectura_automatica SET tope_dia_usd_micro = 20000000")
    with pytest.raises(sqlite3.IntegrityError, match="solo escritura"):
        conn.execute("DELETE FROM lectura_automatica")
    assert verificar_evidencia(conn) == []


@pytest.mark.parametrize("cambio, mensaje", [
    ({"activa": 2}, "activa"),
    ({"activa": True}, None),
    ({"tope_dia_usd_micro": 0}, "tope_dia_usd_micro"),
    ({"tope_dia_usd_micro": 20_000_001}, "tope_dia_usd_micro"),
    ({"tope_mes_usd_micro": 1_999_999}, "tope_mes_usd_micro"),
    ({"tope_mes_usd_micro": 200_000_001}, "tope_mes_usd_micro"),
    ({"max_documentos": 0}, "max_documentos"),
    ({"max_documentos": 101}, "max_documentos"),
    ({"max_por_documento_usd_micro": 0}, "max_por_documento_usd_micro"),
    ({"max_por_documento_usd_micro": 2_000_001}, "max_por_documento_usd_micro"),
    ({"tope_dia_usd_micro": "2000000.5"}, "tope_dia_usd_micro"),
])
def test_los_topes_tienen_sus_rangos(almacen, gente, cambio, mensaje) -> None:
    conn = almacen.conn
    if mensaje is None:   # un booleano de Python vale como 0/1; la orden lo rechaza (ENTERO)
        auto.fijar(conn, gente["ana"], **{**POR_DEFECTO, **cambio})
        with pytest.raises(servicios.DatosNoValidos, match="entero"):
            _fijar(conn, gente["ana"], **cambio)
        return
    with pytest.raises((auto.ValorNoValido, servicios.DatosNoValidos), match=mensaje) as error:
        _fijar(conn, gente["ana"], **cambio)
    assert servicios.codigo_de_error(error.value) == "invalido"
    assert conn.execute("SELECT count(*) FROM lectura_automatica").fetchone()[0] == 0


def test_los_techos_estan_en_la_base(almacen, gente) -> None:
    """Aunque alguien se salte el codigo: 20 USD al dia, 200 al mes, 100 facturas por ronda y
    por factura no mas que el dia."""
    conn = almacen.conn
    sql = ("INSERT INTO lectura_automatica (activa, tope_dia_usd_micro, tope_mes_usd_micro, "
           "max_documentos, max_por_documento_usd_micro, fijada_por, fijada_en) "
           "VALUES (1, ?, ?, ?, ?, ?, '2026-10-14T09:30:00+00:00')")
    for valores in ((20_000_001, 25_000_000, 20, 1), (2_000_000, 200_000_001, 20, 1),
                    (2_000_000, 1_000_000, 20, 1), (2_000_000, 25_000_000, 101, 1),
                    (2_000_000, 25_000_000, 20, 2_000_001)):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            conn.execute(sql, (*valores, gente["ana"]))


# ============================================================ lo gastado

def test_lo_gastado_por_dia_y_mes_de_amsterdam(almacen, gente, reloj) -> None:
    conn = almacen.conn
    autorizacion = _fijar(conn, gente["ana"], tope_dia_usd_micro=20_000_000)
    # 14-10-2026 en Amsterdam (CEST, UTC+2): de 13-10 22:00 a 14-10 22:00 UTC.
    _automatica(conn, "2026-10-13T21:59:59+00:00", 1_000, autorizacion=autorizacion)  # el 13
    _automatica(conn, "2026-10-13T22:00:00+00:00", 20_000, autorizacion=autorizacion)  # el 14
    _automatica(conn, "2026-10-14T21:59:59+00:00", 300_000, autorizacion=autorizacion)  # el 14
    _automatica(conn, "2026-10-14T22:00:00+00:00", 4_000_000, autorizacion=autorizacion)  # 15
    # Lo que acepto una persona ya tuvo su si: no cuenta.
    _automatica(conn, "2026-10-14T09:00:00+00:00", 50_000_000, autorizacion=autorizacion,
                via="app", quien=gente["berta"])
    # Septiembre (30-09 22:00 UTC es ya el 1 de octubre en Amsterdam).
    _automatica(conn, "2026-09-30T21:59:59+00:00", 600_000_000 // 1000, autorizacion=autorizacion)
    _automatica(conn, "2026-09-30T22:00:00+00:00", 7, autorizacion=autorizacion)
    assert auto.gastado(conn, reloj.ahora()) == (320_000, 4_321_007)
    assert auto.gastado(conn, datetime(2026, 10, 14, 22, 30, tzinfo=UTC)) == (4_000_000,
                                                                              4_321_007)
    assert auto.gastado(conn, datetime(2026, 9, 30, 21, 0, tzinfo=UTC)) == (600_000, 600_000)


@pytest.mark.parametrize("dia, inicio, fin", [
    # El ultimo domingo de octubre dura 25 horas (de CEST a CET)...
    ("2026-10-25T12:00:00+00:00", "2026-10-24T22:00:00+00:00", "2026-10-25T23:00:00+00:00"),
    # ... y el ultimo de marzo, 23 (de CET a CEST).
    ("2026-03-29T12:00:00+00:00", "2026-03-28T23:00:00+00:00", "2026-03-29T22:00:00+00:00"),
])
def test_lo_gastado_el_dia_del_cambio_de_hora(almacen, gente, dia, inicio, fin) -> None:
    conn = almacen.conn
    autorizacion = _fijar(conn, gente["ana"], tope_dia_usd_micro=20_000_000)
    ahora = datetime.fromisoformat(dia)
    segundo = timedelta(seconds=1)
    for instante, coste in ((datetime.fromisoformat(inicio) - segundo, 1),
                            (datetime.fromisoformat(inicio), 10),
                            (datetime.fromisoformat(fin) - segundo, 100),
                            (datetime.fromisoformat(fin), 1_000)):
        _automatica(conn, marca(instante), coste, autorizacion=autorizacion)
    hoy, _mes = auto.gastado(conn, ahora)
    assert hoy == 110
    # La pausa de una persona acaba a las 00:00 del dia siguiente, tambien ese dia.
    assert auto.manana(ahora) == datetime.fromisoformat(fin)


def test_el_tope_alcanzado_y_lo_que_queda(almacen, gente, reloj) -> None:
    conn = almacen.conn
    _fijar(conn, gente["ana"])     # 2 USD al dia, 25 al mes, 0,50 por factura
    autorizacion = auto.vigente(conn)
    ahora = reloj.ahora()
    assert auto.tope_alcanzado(autorizacion, 1_500_000, 1_500_000, ahora) is None
    assert auto.queda(autorizacion, 1_500_000, 1_500_000) == 500_000
    # Con 1,50 gastados y una factura mas, ya no llega: para (el texto lo dice asi).
    tope = auto.tope_alcanzado(autorizacion, 1_500_001, 1_500_001, ahora)
    assert tope == auto.Tope("limite_dia", "2026-10-14T22:00:00+00:00")
    # El mes, antes que el dia: si se acabo el mes, manana tampoco.
    tope = auto.tope_alcanzado(autorizacion, 1_600_000, 24_600_000, ahora)
    assert tope == auto.Tope("limite_mes", "2026-10-31T23:00:00+00:00")
    assert auto.queda(autorizacion, 100_000, 24_600_000) == 400_000
    assert auto.queda(autorizacion, 3_000_000, 3_000_000) == 0


# ============================================================ las pausas

def test_la_pausa_de_una_persona_dura_hasta_las_00_de_manana(almacen, gente, reloj) -> None:
    conn = almacen.conn
    assert auto.pausa_vigente(conn) is None
    pausa_id, evento = auto.pausar(conn, "persona", gente["berta"])
    pausa = auto.pausa_vigente(conn)
    assert (pausa["id"], pausa["motivo"], pausa["por"], pausa["hasta"]) == (
        pausa_id, "persona", gente["berta"], "2026-10-14T22:00:00+00:00")
    fila = conn.execute("SELECT * FROM evento WHERE id = ?", (evento,)).fetchone()
    assert (fila["tipo"], fila["actor"], fila["usuario_id"]) == (
        "lectura_automatica_pausada", gente["berta"], gente["berta"])
    reloj.instante = datetime(2026, 10, 14, 21, 59, 59, tzinfo=UTC)
    assert auto.pausa_vigente(conn) is not None
    reloj.instante = datetime(2026, 10, 14, 22, 0, tzinfo=UTC)
    assert auto.pausa_vigente(conn) is None
    # La firma una persona, nunca el sistema; y sin nadie, no.
    automatico = usuario_sistema(conn, "automatico")
    with pytest.raises(sqlite3.IntegrityError, match="parar y reanudar, una persona"):
        auto.pausar(conn, "persona", automatico)
    with pytest.raises(auto.ValorNoValido):
        auto.pausar(conn, "persona")


def test_reanudar_quita_la_pausa_y_sin_pausa_es_un_409(almacen, gente, reloj) -> None:
    conn = almacen.conn
    with pytest.raises(EstadoNoValido, match="no esta en pausa"):
        servicios.ejecutar(conn, "reanudar_lectura_automatica", {}, usuario_id=gente["berta"])
    auto.pausar(conn, "persona", gente["ana"])
    diferencia = servicios.ejecutar(conn, "reanudar_lectura_automatica",
                                    {"motivo": "Era una prueba"}, usuario_id=gente["berta"])
    assert auto.pausa_vigente(conn) is None
    evento = conn.execute("SELECT * FROM evento WHERE id = ?", (diferencia.evento_id,)).fetchone()
    assert (evento["tipo"], evento["usuario_id"], evento["motivo"]) == (
        "lectura_automatica_reanudada", gente["berta"], "Era una prueba")
    assert diferencia.ejecucion_id is None       # no toca nada que lea una regla
    # Quien solo consulta, no.
    auto.pausar(conn, "persona", gente["ana"])
    with pytest.raises(PermisoDenegado):
        servicios.ejecutar(conn, "reanudar_lectura_automatica", {}, usuario_id=gente["carla"])
    # Reanudar lo hace una persona, tambien en la base.
    with pytest.raises(sqlite3.IntegrityError, match="una persona"):
        auto.reanudar(conn, usuario_sistema(conn, "automatico"))
    assert verificar_evidencia(conn) == []


def test_la_pausa_por_volumen_una_vez_al_dia_y_hasta_que_la_quite_una_persona(
        almacen, gente, reloj) -> None:
    conn = almacen.conn
    pausa_id, _evento = auto.pausar(conn, "volumen")
    fila = conn.execute("SELECT * FROM pausa_lectura_automatica WHERE id = ?",
                        (pausa_id,)).fetchone()
    assert (fila["por"], fila["hasta"]) == (usuario_sistema(conn, "automatico"), None)
    # Otra vez ese dia: ya esta.
    assert auto.pausar(conn, "volumen") is None
    # Una persona la quita; ese mismo dia (de Amsterdam) el correo sigue diciendo que hay
    # mucho, y no vuelve: se pone una vez al dia.
    auto.reanudar(conn, gente["berta"], "Mirada la lista")
    assert auto.pausa_vigente(conn) is None
    reloj.instante = datetime(2026, 10, 14, 21, 59, tzinfo=UTC)
    assert auto.pausar(conn, "volumen") is None
    # Al dia siguiente, si; y dura dias, hasta que una persona la quite.
    reloj.instante = datetime(2026, 10, 14, 22, 0, tzinfo=UTC)
    assert auto.pausar(conn, "volumen") is not None
    reloj.avanzar(days=3)
    assert auto.pausa_vigente(conn)["motivo"] == "volumen"
    # La de volumen gana a una de persona que llega despues (acaba antes).
    auto.pausar(conn, "persona", gente["ana"])
    reloj.avanzar(days=1)
    assert auto.pausa_vigente(conn)["motivo"] == "volumen"
    # La pone el sistema, nunca una persona.
    auto.reanudar(conn, gente["ana"])
    reloj.avanzar(days=1)
    with pytest.raises(sqlite3.IntegrityError, match="la pone el sistema"):
        auto.pausar(conn, "volumen", gente["ana"])
    assert verificar_evidencia(conn) == []


# ============================================================ la espera tras un fallo

def test_la_espera_tras_fallos_crece_hasta_24_horas_y_vuelve_tras_una_buena(almacen,
                                                                            reloj) -> None:
    conn = almacen.conn
    inicio = reloj.ahora()
    assert auto.espera_tras_fallo(conn) is None
    esperas = []
    for i, motivo in enumerate(("saldo", "api_no_disponible", "salida", "aislamiento",
                                "clave_rechazada", "contar", "sin_tarifa")):
        terminada = marca(inicio + timedelta(days=i))
        _terminada(conn, terminada, motivo_codigo=motivo)
        espera = auto.espera_tras_fallo(conn, inicio + timedelta(days=i))
        assert (espera.motivo_codigo, espera.desde, espera.fallos) == (motivo, marca(inicio), i + 1)
        esperas.append(datetime.fromisoformat(espera.proximo_intento) - (inicio + timedelta(days=i)))
    assert esperas == [timedelta(hours=h) for h in (1, 2, 4, 8, 16, 24, 24)]
    ultima = inicio + timedelta(days=6)
    assert auto.espera_tras_fallo(conn, ultima + timedelta(hours=23, minutes=59)) is not None
    assert auto.espera_tras_fallo(conn, ultima + timedelta(hours=24)) is None
    # Lo de una persona no cuenta; una automatica buena, o que no pudo por otra cosa, corta.
    _terminada(conn, marca(ultima), motivo_codigo="saldo", origen="lector")
    assert auto.espera_tras_fallo(conn, ultima).fallos == 7
    _terminada(conn, marca(ultima), "nada_que_leer", "excluidas")
    assert auto.espera_tras_fallo(conn, ultima) is None
    _terminada(conn, marca(ultima), motivo_codigo="clave")
    assert auto.espera_tras_fallo(conn, ultima).proximo_intento == marca(ultima +
                                                                         timedelta(hours=1))
    # Un fallo que no es tecnico (el lector se cerro) tampoco hace esperar.
    _terminada(conn, marca(ultima), motivo_codigo="interrumpida")
    assert auto.espera_tras_fallo(conn, ultima) is None


# ============================================================ lo que se lee solo

def test_elegibles_y_pendientes_del_correo(almacen, gente) -> None:
    conn = almacen.conn
    vieja, nueva, leida, apartada, grande, otra = (
        _documento(almacen, n) for n in ("vieja", "nueva", "leida", "apartada", "grande", "otra"))
    sin_original = _documento(almacen, "sin-original", original=False)
    _correo(conn, "2026-10-14T08:00:00+00:00", ("documento", nueva), ("documento", leida))
    _correo(conn, "2026-10-13T08:00:00+00:00", ("documento", vieja), ("xml", None))
    _correo(conn, "2026-10-12T08:00:00+00:00", ("documento", apartada), ("documento", grande),
            ("documento", sin_original))
    # La misma "nueva" llega antes en otro mensaje: cuenta la primera llegada.
    _correo(conn, "2026-10-11T08:00:00+00:00", ("documento", otra))
    _correo(conn, "2026-10-10T08:00:00+00:00", ("documento", nueva))
    _leido(conn, leida)
    auto.excluir(conn, [apartada], "persona", gente["berta"])
    auto.excluir(conn, [grande], "grande", usuario_sistema(conn, "automatico"),
                 solicitud_id=_terminada(conn, "2026-10-14T09:00:00+00:00", "nada_que_leer",
                                         "excluidas"))
    assert [d["documento_id"] for d in auto.elegibles(conn)] == [nueva, otra, vieja]
    assert auto.elegibles(conn, limite=2)[0] == {
        "documento_id": nueva, "sha256": conn.execute("SELECT sha256 FROM documento WHERE id = ?",
                                                      (nueva,)).fetchone()[0],
        "ruta_cas": conn.execute("SELECT ruta_cas FROM documento WHERE id = ?",
                                 (nueva,)).fetchone()[0],
        "nombre_original": "nueva.pdf", "llegada": "2026-10-10T08:00:00+00:00"}
    _fijar(conn, gente["ana"], max_documentos=1)
    assert [d["documento_id"] for d in auto.elegibles(conn, auto.vigente(conn))] == [nueva]
    # Lo que aparto la automatica se puede leer a mano; lo que aparto una persona, no.
    assert [d["documento_id"] for d in auto.pendientes_del_correo(conn)] == [
        nueva, otra, grande, vieja]
    assert auto.contar_elegibles(conn) == (3, "2026-10-10T08:00:00+00:00")
    # Lo que llego solo por "no deseado" no cuenta (no se trae, pero aunque lo estuviera).
    junk = _documento(almacen, "junk")
    _correo(conn, "2026-10-01T08:00:00+00:00", ("documento", junk), carpeta="no_deseado")
    assert junk not in [d["documento_id"] for d in auto.pendientes_del_correo(conn)]
    assert sin_original not in [d["documento_id"] for d in auto.pendientes_del_correo(conn)]


def test_una_extraccion_candidata_no_cuenta_como_leida(almacen) -> None:
    """La regla de ingesta.vigentes_por_documento, sin cargar cada extraccion: un documento
    cuya unica extraccion es una candidata sin activar sigue sin leer."""
    from bms_agent.ingesta import vigentes_por_documento

    conn = almacen.conn
    documento = _documento(almacen, "candidata")
    _correo(conn, "2026-10-14T08:00:00+00:00", ("documento", documento))
    _leido(conn, documento)
    extraccion = conn.execute("SELECT id FROM extraccion WHERE documento_id = ?",
                              (documento,)).fetchone()[0]
    assert documento in vigentes_por_documento(conn) and not auto.elegibles(conn)
    # Como si fuera la candidata de una relectura que nadie activo.
    with transaccion(conn):
        reextraccion = conn.execute(
            "INSERT INTO reextraccion (modelo, prompt_version, schema_version, via, "
            "criterio_json, documentos, presupuesto_usd_cent, estimado_bajo_usd_cent, "
            "estimado_alto_usd_cent, salida_medida, estimacion_json, iniciada_en, actor) "
            "VALUES ('m', 'p', '1', 'api', '{}', 1, 100, 1, 2, 0, '{}', ?, ?)",
            ("2026-10-14T09:00:00+00:00", usuario_sistema(conn, "extractor"))).lastrowid
        evento = conn.execute("SELECT max(id) FROM evento").fetchone()[0]
        conn.execute(
            "INSERT INTO reextraccion_resultado (reextraccion_id, documento_id, resultado, "
            "extraccion_id, en, evento_id) VALUES (?, ?, 'candidata', ?, ?, ?)",
            (reextraccion, documento, extraccion, "2026-10-14T09:00:00+00:00", evento))
    assert documento not in vigentes_por_documento(conn)
    assert [d["documento_id"] for d in auto.elegibles(conn)] == [documento]


def test_excluir_en_bloque_hasta_200(almacen, gente) -> None:
    conn = almacen.conn
    ids = [_documento(almacen, f"doc-{i}", original=False) for i in range(201)]
    for documento in ids:
        _correo(conn, "2026-10-14T08:00:00+00:00", ("documento", documento))
    # Mas de 200, ninguno, uno que no existe o algo que no es un id: no se aparta nada.
    for datos, codigo in (({"documento_ids": ids}, "invalido"),
                          ({"documento_ids": []}, "invalido"),
                          ({"documento_ids": [ids[0], 99_999]}, "no_existe"),
                          ({"documento_ids": [ids[0], "x"]}, "invalido"),
                          ({"documento_ids": [ids[0], True]}, "invalido"),
                          ({"documento_ids": ids[0]}, "invalido")):
        with pytest.raises(Exception) as error:
            servicios.ejecutar(conn, "excluir_de_lectura_automatica", datos,
                               usuario_id=gente["berta"])
        assert servicios.codigo_de_error(error.value) == codigo, datos
    assert conn.execute("SELECT count(*) FROM exclusion_automatica").fetchone()[0] == 0
    # 200 de una vez (con uno repetido), con su evento cada una y la peticion en el primero.
    diferencia = servicios.ejecutar(
        conn, "excluir_de_lectura_automatica",
        {"documento_ids": ids[:200] + [ids[0]], "motivo": "Publicidad"},
        usuario_id=gente["berta"], peticion_id="excluir-1")
    assert diferencia.detalle == {"excluidos": 200, "ya_estaban": 0}
    assert diferencia.ejecucion_id is None
    filas = conn.execute("SELECT * FROM exclusion_automatica ORDER BY id").fetchall()
    assert [(f["documento_id"], f["motivo_codigo"], f["solicitud_id"], f["por"])
            for f in filas] == [(i, "persona", None, gente["berta"]) for i in ids[:200]]
    eventos = conn.execute("SELECT * FROM evento WHERE tipo = 'lectura_excluida' ORDER BY id"
                           ).fetchall()
    assert len(eventos) == 200 and eventos[0]["peticion_id"] == "excluir-1"
    assert {(e["usuario_id"], e["motivo"]) for e in eventos} == {(gente["berta"], "Publicidad")}
    # La misma peticion otra vez no hace nada; los que ya estaban, se dejan.
    assert servicios.ejecutar(conn, "excluir_de_lectura_automatica",
                              {"documento_ids": ids[:200] + [ids[0]], "motivo": "Publicidad"},
                              usuario_id=gente["berta"], peticion_id="excluir-1").repetida
    diferencia = servicios.ejecutar(conn, "excluir_de_lectura_automatica",
                                    {"documento_ids": [ids[0], ids[200]]},
                                    usuario_id=gente["berta"])
    assert diferencia.detalle == {"excluidos": 1, "ya_estaban": 1}
    assert auto.elegibles(conn) == [] and auto.pendientes_del_correo(conn) == []
    # La de una persona la pone una persona; las demas, el sistema y con su peticion.
    otro = _documento(almacen, "otro", original=False)
    with pytest.raises(sqlite3.IntegrityError, match="una exclusion de persona"):
        auto.excluir(conn, [otro], "persona", usuario_sistema(conn, "automatico"))
    with pytest.raises(sqlite3.IntegrityError):
        auto.excluir(conn, [otro], "grande", gente["berta"],
                     solicitud_id=_terminada(conn, "2026-10-14T09:00:00+00:00", "nada_que_leer",
                                             "excluidas"))
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        auto.excluir(conn, [otro], "fallo", usuario_sistema(conn, "automatico"))
    with pytest.raises(sqlite3.IntegrityError, match="solo escritura"):
        conn.execute("DELETE FROM exclusion_automatica")
    assert verificar_evidencia(conn) == []


# ============================================================ lo que espera a una persona

def test_esperan_persona(almacen, gente) -> None:
    conn = almacen.conn
    leida, apartada, ya_leida_y_apartada, buena = (
        _documento(almacen, n) for n in ("leida", "apartada", "leida-y-apartada", "buena"))
    sin_pdf = _correo(conn, "2026-10-14T07:00:00+00:00", asunto="Zie de link")
    con_xml = _correo(conn, "2026-10-14T06:00:00+00:00", ("documento", leida),
                      ("xml", None, "factuur.xml"))
    _correo(conn, "2026-10-14T05:00:00+00:00", ("documento", buena))     # bien: no espera
    _correo(conn, "2026-10-14T04:00:00+00:00", ("documento", apartada),
            ("documento", ya_leida_y_apartada), ("no_pdf", None, "logo.png"))
    # Lo que llego a "no deseado" espera, hasta que la misma llegada aparece en la bandeja.
    junk = _correo(conn, "2026-10-14T03:00:00+00:00", ("no_deseado", None),
                   carpeta="no_deseado", graph_id="AAMkJUNK1")
    rescatado = _correo(conn, "2026-10-14T02:00:00+00:00", ("no_deseado", None),
                        carpeta="no_deseado", graph_id="AAMkJUNK2")
    _correo(conn, "2026-10-14T08:00:00+00:00", ("documento", buena), graph_id="AAMkJUNK2")
    atendido = _correo(conn, "2026-10-14T01:00:00+00:00", ("enlace", None))
    servicios.ejecutar(conn, "marcar_correo_atendido",
                       {"mensaje_id": atendido, "nota": "Bajada de la web"},
                       usuario_id=gente["berta"])
    _leido(conn, ya_leida_y_apartada)
    auto.excluir(conn, [apartada, ya_leida_y_apartada], "persona", gente["berta"])
    esperan = auto.esperan_persona(conn)
    assert [c["mensaje_id"] for c in esperan["correos"]] == [sin_pdf, con_xml, junk]
    assert esperan["correos_total"] == 3 and rescatado not in esperan["correos"]
    assert esperan["correos"][1] == {
        "mensaje_id": con_xml, "recibido_en": "2026-10-14T06:00:00+00:00", "carpeta": "bandeja",
        "remitente_doc": "facturen@proveedor.example", "asunto_doc": "Factuur",
        "adjuntos": [{"nombre_doc": "adjunto-0.pdf", "resultado": "documento", "bytes": 100,
                      "documento_id": leida},
                     {"nombre_doc": "factuur.xml", "resultado": "xml", "bytes": 100,
                      "documento_id": None}]}
    # Las facturas apartadas y aun sin leer.
    assert esperan["documentos"] == [{"documento_id": apartada, "nombre_original": "apartada.pdf",
                                      "recibido_en": "2026-10-14T08:00:00+00:00",
                                      "motivo_codigo": "persona"}]
    assert esperan["documentos_total"] == 1
    # Como mucho `limite` filas, con su total.
    recortado = auto.esperan_persona(conn, limite=1)
    assert (len(recortado["correos"]), recortado["correos_total"]) == (1, 3)


def test_marcar_un_correo_atendido(almacen, gente) -> None:
    conn = almacen.conn
    mensaje = _correo(conn, "2026-10-14T07:00:00+00:00")
    for datos, codigo in (({"mensaje_id": 99_999}, "no_existe"),
                          ({"mensaje_id": mensaje, "nota": "x" * 501}, "invalido")):
        with pytest.raises(Exception) as error:
            servicios.ejecutar(conn, "marcar_correo_atendido", datos, usuario_id=gente["berta"])
        assert servicios.codigo_de_error(error.value) == codigo
    with pytest.raises(PermisoDenegado):
        servicios.ejecutar(conn, "marcar_correo_atendido", {"mensaje_id": mensaje},
                           usuario_id=gente["carla"])
    diferencia = servicios.ejecutar(conn, "marcar_correo_atendido",
                                    {"mensaje_id": mensaje, "nota": " Pedida por telefono "},
                                    usuario_id=gente["berta"])
    fila = conn.execute("SELECT * FROM correo_atendido").fetchone()
    assert (fila["mensaje_id"], fila["por"], fila["nota"]) == (mensaje, gente["berta"],
                                                                "Pedida por telefono")
    evento = conn.execute("SELECT * FROM evento WHERE id = ?", (diferencia.evento_id,)).fetchone()
    assert (evento["tipo"], evento["usuario_id"]) == ("correo_atendido", gente["berta"])
    with pytest.raises(EstadoNoValido, match="ya esta atendido"):
        servicios.ejecutar(conn, "marcar_correo_atendido", {"mensaje_id": mensaje},
                           usuario_id=gente["berta"])
    assert auto.esperan_persona(conn)["correos_total"] == 0
    with pytest.raises(sqlite3.IntegrityError, match="una persona"):
        auto.marcar_atendido(conn, _correo(conn, "2026-10-14T07:00:00+00:00"),
                             usuario_sistema(conn, "correo"))
    assert verificar_evidencia(conn) == []


# ============================================================ lo que ensena la app

def test_el_resumen_para_la_app(almacen, gente, reloj) -> None:
    conn = almacen.conn
    apagada = auto.resumen(conn)
    assert apagada == {
        "activa": False, "autorizacion_id": None, "tope_dia_usd_micro": None,
        "tope_mes_usd_micro": None, "max_documentos": None, "max_por_documento_usd_micro": None,
        "fijada_por": None, "fijada_en": None, "gastado_hoy_usd_micro": 0,
        "gastado_mes_usd_micro": 0, "queda_hoy_usd_micro": 0, "parada": None,
        "motivo_codigo": None, "desde": None, "proximo_intento": None, "hasta": None,
        "pendientes": 0, "elegibles": 0, "elegible_mas_antigua": None}
    autorizacion = _fijar(conn, gente["ana"])
    _automatica(conn, "2026-10-14T08:00:00+00:00", 1_200_000, autorizacion=autorizacion)
    documentos = [_documento(almacen, n) for n in ("a", "b")]
    _correo(conn, "2026-10-13T08:00:00+00:00", ("documento", documentos[0]))
    _correo(conn, "2026-10-14T08:00:00+00:00", ("documento", documentos[1]))
    auto.excluir(conn, [documentos[1]], "persona", gente["berta"])
    resumen = auto.resumen(conn)
    assert resumen == {
        "activa": True, "autorizacion_id": autorizacion, "tope_dia_usd_micro": 2_000_000,
        "tope_mes_usd_micro": 25_000_000, "max_documentos": 20,
        "max_por_documento_usd_micro": 500_000,
        "fijada_por": {"id": gente["ana"], "nombre": "Ana"},
        "fijada_en": "2026-10-14T09:30:00+00:00", "gastado_hoy_usd_micro": 1_200_000,
        "gastado_mes_usd_micro": 1_200_000, "queda_hoy_usd_micro": 800_000, "parada": None,
        "motivo_codigo": None, "desde": None, "proximo_intento": None, "hasta": None,
        "pendientes": 1, "elegibles": 1, "elegible_mas_antigua": "2026-10-13T08:00:00+00:00"}
    # Parada, por orden: la pausa, la espera tras un fallo y el tope.
    _automatica(conn, "2026-10-14T08:30:00+00:00", 400_000, autorizacion=autorizacion)
    assert {k: auto.resumen(conn)[k] for k in ("parada", "hasta", "queda_hoy_usd_micro")} == {
        "parada": "limite_dia", "hasta": "2026-10-14T22:00:00+00:00",
        "queda_hoy_usd_micro": 400_000}
    _terminada(conn, "2026-10-14T09:00:00+00:00", motivo_codigo="saldo")
    assert {k: auto.resumen(conn)[k] for k in ("parada", "motivo_codigo", "desde",
                                               "proximo_intento")} == {
        "parada": "fallo", "motivo_codigo": "saldo", "desde": "2026-10-14T09:00:00+00:00",
        "proximo_intento": "2026-10-14T10:00:00+00:00"}
    auto.pausar(conn, "persona", gente["berta"])
    assert {k: auto.resumen(conn)[k] for k in ("parada", "desde", "hasta")} == {
        "parada": "persona", "desde": "2026-10-14T09:30:00+00:00",
        "hasta": "2026-10-14T22:00:00+00:00"}
    # Apagada no esta parada: esta apagada.
    _fijar(conn, gente["ana"], activa=0)
    assert auto.resumen(conn)["parada"] is None and auto.resumen(conn)["activa"] is False
    assert verificar_evidencia(conn) == []


def test_db_verificar_ve_una_fila_metida_por_detras(almacen, gente) -> None:
    conn = almacen.conn
    _fijar(conn, gente["ana"])
    auto.pausar(conn, "volumen")
    assert verificar_evidencia(conn) == []
    with transaccion(conn):
        conn.execute("INSERT INTO pausa_lectura_automatica (tipo, por, en) "
                     "VALUES ('reanuda', ?, '2026-10-14T09:31:00+00:00')", (gente["ana"],))
        conn.execute("INSERT INTO lectura_automatica (activa, tope_dia_usd_micro, "
                     "tope_mes_usd_micro, max_documentos, max_por_documento_usd_micro, "
                     "fijada_por, fijada_en) VALUES (1, 20000000, 200000000, 100, 20000000, ?, "
                     "'2026-10-14T09:31:00+00:00')", (gente["ana"],))
    problemas = verificar_evidencia(conn)
    assert any(p.startswith("pausa_lectura_automatica") and "por detras" in p
               for p in problemas), problemas
    assert any(p.startswith("lectura_automatica") and "por detras" in p for p in problemas)


# ============================================================ paso 5: la lectura automatica

from bms_agent import cli, lectura  # noqa: E402
from bms_agent.almacen import preparar  # noqa: E402
from bms_agent.nativo import LecturaNoAislada  # noqa: E402
from test_lectura import (DEL_DOCUMENTO, FALLOS_API, ClienteQueCuenta,  # noqa: E402
                          ClienteQueFalla)
from test_lectura_lector import ApiFalsa, ApiQueFalla, SalidaFalsa  # noqa: E402


def _del_correo(almacen, *marcas: str, recibido: str = "2026-10-14T08:00:00+00:00") -> list[int]:
    """PDF que trajo el correo (cada uno en su mensaje de la bandeja), en el almacen."""
    ids = []
    for i, nombre in enumerate(marcas):
        documento = _documento(almacen, nombre)
        instante = datetime.fromisoformat(recibido) + timedelta(minutes=i)
        _correo(almacen.conn, marca(instante), ("documento", documento, f"{nombre}.pdf"))
        ids.append(documento)
    return ids


def _ronda(almacen, client, out, *, cancelar=None) -> tuple[str, int | None]:
    """Lo que hace la rama automatica de ciclo.ps1 (§4.1), con las mismas funciones que sus
    ordenes: siguiente, tomar --automatica, contar, autorizar y leer, leyendo del almacen."""
    conn = almacen.conn
    que = lectura.siguiente(conn)
    if que.codigo != lectura.LEER:
        return que.codigo, None
    hay = bool(cli._pdfs_a_leer(None, almacen, automatica=True))
    tomada = lectura.tomar(conn, hay_pdf=hay, automatica=True)
    solicitud = tomada.solicitud_id
    if solicitud is None:
        return tomada.como, None
    try:
        estado, _est = lectura.contar(conn, solicitud, lambda antes: lectura.estimar(
            client, cli._pdfs_a_leer(None, almacen, solicitud), out, almacen=almacen,
            antes=antes))
    except lectura.ParadaApi as parada:
        lectura.cerrar(conn, solicitud, parada.motivo, detalle=parada.detalle)
        return "fallida", solicitud
    if estado != "esperando_aprobacion":
        return estado, solicitud
    estado = lectura.autorizar(conn, solicitud)
    if estado != "aprobada":
        return estado, solicitud
    if cancelar is not None:
        cancelar(solicitud)
    leida = lectura.leer(conn, solicitud, client=client, almacen=almacen,
                         pdfs=cli._pdfs_a_leer(None, almacen, solicitud), out_dir=out)
    return leida.estado, solicitud


def _fila(conn, solicitud):
    return conn.execute("SELECT * FROM solicitud_lectura WHERE id = ?", (solicitud,)).fetchone()


def _excluidos(conn) -> dict[int, str]:
    return {f[0]: f[1] for f in conn.execute(
        "SELECT documento_id, motivo_codigo FROM exclusion_automatica")}


def test_una_automatica_entera_leyendo_del_almacen(almacen, gente, tmp_path) -> None:
    """De punta a punta en Python (§7.3), sin red: las facturas del correo se leen solas con
    la autorizacion vigente, sin que nadie diga que si, y la segunda vez no se paga nada."""
    conn = almacen.conn
    out = tmp_path / "out"
    documentos = _del_correo(almacen, "una", "dos", "tres")
    client = ClienteQueCuenta()
    # Apagada: nada, y no se cuenta ni se paga nada.
    assert _ronda(almacen, client, out) == (lectura.NADA, None)
    autorizacion = _fijar(conn, gente["ana"])
    assert lectura.siguiente(conn).codigo == lectura.LEER
    estado, solicitud = _ronda(almacen, client, out)
    assert estado == "hecha" and sorted(client.leidos) == ["dos", "tres", "una"]
    fila = _fila(conn, solicitud)
    assert (fila["origen"], fila["pedida_por"], fila["aprobada_via"], fila["aprobada_por"],
            fila["autorizacion_id"]) == ("automatica", None, "automatica", None, autorizacion)
    assert fila["tope_usd_micro"] == min(fila["coste_max_usd_micro"], 2_000_000)
    assert fila["huella_aprobada"] == fila["huella_estimacion"]
    # Nadie firma como persona: lo pide y lo acepta "automatico", lo lee el extractor.
    eventos = conn.execute(
        "SELECT e.tipo, e.usuario_id, u.nombre, e.datos_json FROM evento AS e "
        "JOIN usuario AS u ON u.id = e.actor WHERE e.tabla = 'solicitud_lectura' "
        "AND e.fila_id = ? ORDER BY e.id", (solicitud,)).fetchall()
    assert [(e["tipo"], e["nombre"]) for e in eventos] == [
        ("lectura_pedida", "automatico"), ("lectura_contando", "extractor"),
        ("lectura_contada", "extractor"), ("lectura_aceptada", "automatico"),
        ("lectura_empezada", "extractor"), ("lectura_terminada", "extractor")]
    assert {e["usuario_id"] for e in eventos} == {None}
    import json

    aceptada = json.loads(eventos[3]["datos_json"])
    assert {k: aceptada[k] for k in ("via", "autorizacion_id", "fijada_por", "tope_dia",
                                     "tope_mes", "gastado_dia", "gastado_mes")} == {
        "via": "automatica", "autorizacion_id": autorizacion, "fijada_por": gente["ana"],
        "tope_dia": 2_000_000, "tope_mes": 25_000_000, "gastado_dia": 0, "gastado_mes": 0}
    # Las tres, leidas del almacen (por su hash) y con su factura.
    pasada = conn.execute("SELECT * FROM pasada_lectura WHERE solicitud_id = ?",
                          (solicitud,)).fetchone()
    resultado = json.loads(pasada["resultado_json"])
    shas = {conn.execute("SELECT sha256 FROM documento WHERE id = ?", (d,)).fetchone()[0]
            for d in documentos}
    assert {r["nombre"] for r in resultado} == {f"{s}.pdf" for s in shas}
    assert {r["estado"] for r in resultado} == {"nueva"}
    assert {r["documento_id"] for r in resultado} == set(documentos)
    assert auto.gastado(conn) == (pasada["coste_usd_micro"],) * 2 and pasada["coste_usd_micro"]
    assert auto.elegibles(conn) == []
    # Otra ronda: nada nuevo, nada pagado.
    contados = client.conteos
    assert _ronda(almacen, client, out) == (lectura.NADA, None)
    assert (client.conteos, len(client.leidos)) == (contados, 3)
    assert verificar_evidencia(conn) == []


def test_una_persona_no_da_el_si_a_una_automatica(almacen, gente, tmp_path) -> None:
    conn = almacen.conn
    _del_correo(almacen, "una")
    _fijar(conn, gente["ana"])
    tomada = lectura.tomar(conn, hay_pdf=True, automatica=True)
    solicitud = tomada.solicitud_id
    lectura.contar(conn, solicitud, lambda antes: lectura.estimar(
        ClienteQueCuenta(), cli._pdfs_a_leer(None, almacen, solicitud), tmp_path / "out",
        almacen=almacen, antes=antes))
    fila = _fila(conn, solicitud)
    assert fila["estado"] == "esperando_aprobacion"
    with pytest.raises(EstadoNoValido, match="es automatica"):
        servicios.ejecutar(conn, "aprobar_lectura", {"solicitud_id": solicitud,
                                                     "huella_estimacion": fila["huella_estimacion"]},
                           usuario_id=gente["ana"])
    with pytest.raises(EstadoNoValido, match="es automatica"):
        lectura.aprobar_en_ventana(conn, solicitud)
    # Ni saltandose el codigo: la base no deja otro si que el de la autorizacion.
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        with transaccion(conn):
            conn.execute("UPDATE solicitud_lectura SET estado = 'aprobada', aprobada_en = ?, "
                         "aprobada_via = 'app', aprobada_por = ?, tope_usd_micro = 1, "
                         "huella_aprobada = huella_estimacion WHERE id = ?",
                         ("2026-10-14T09:30:00+00:00", gente["ana"], solicitud))
    assert lectura.autorizar(conn, solicitud) == "aprobada"
    # Una vez, y solo a una automatica.
    with pytest.raises(EstadoNoValido, match="no espera un si"):
        lectura.autorizar(conn, solicitud)
    lectura.cerrar(conn, solicitud, "interrumpida")
    with pytest.raises(EstadoNoValido, match="no es automatica"):
        lectura.autorizar(conn, _terminada(conn, "2026-10-14T09:00:00+00:00", origen="lector",
                                           motivo_codigo="salida"))


def _contada(almacen, out, client=None) -> int:
    """Una automatica tomada y contada (las elegibles de ahora), que espera su si."""
    conn = almacen.conn
    tomada = lectura.tomar(conn, hay_pdf=True, automatica=True)
    estado, _est = lectura.contar(conn, tomada.solicitud_id, lambda antes: lectura.estimar(
        client or ClienteQueCuenta(),
        [almacen.documentos.ruta(d["ruta_cas"]) for d in auto.elegibles(conn, limite=100)],
        out, almacen=almacen, antes=antes))
    assert estado == "esperando_aprobacion"
    return tomada.solicitud_id


def test_el_tope_de_autorizar_es_el_minimo(almacen, gente, tmp_path) -> None:
    """mín(lo que puede costar lo que se lee, lo que queda hoy, lo que queda este mes)."""
    conn = almacen.conn
    out = tmp_path / "out"
    _del_correo(almacen, "una", "dos", "tres")
    _fijar(conn, gente["ana"], activa=0)
    solicitud = _contada(almacen, out)
    alto_total = _fila(conn, solicitud)["coste_max_usd_micro"]
    alto = alto_total // 3
    # Apagada: no se acepta, y no se gasta nada.
    assert lectura.autorizar(conn, solicitud) == "nada_que_leer"
    assert _fila(conn, solicitud)["motivo_codigo"] == "sin_autorizacion"

    def tope_con(**valores) -> int:
        _fijar(conn, gente["ana"], **valores)
        solicitud = _contada(almacen, out)
        assert lectura.autorizar(conn, solicitud) == "aprobada"
        tope = _fila(conn, solicitud)["tope_usd_micro"]
        lectura.cerrar(conn, solicitud, "interrumpida")
        return tope

    # Con sitio de sobra, lo que puede costar.
    assert tope_con(tope_dia_usd_micro=20_000_000, max_por_documento_usd_micro=alto + 1) == (
        alto_total)
    # Lo que queda hoy da para dos facturas y media: el tope es eso.
    assert tope_con(tope_dia_usd_micro=alto * 5 // 2, max_por_documento_usd_micro=alto + 1) == (
        alto * 5 // 2)
    # Lo del mes, por debajo de lo del dia (lo gastado por otra automatica este mes).
    _fijar(conn, gente["ana"], tope_dia_usd_micro=20_000_000)
    _automatica(conn, "2026-10-02T08:00:00+00:00", alto, autorizacion=auto.vigente(conn)["id"])
    assert tope_con(tope_dia_usd_micro=alto * 3, tope_mes_usd_micro=alto * 3,
                    max_por_documento_usd_micro=alto + 1) == alto * 2
    # Si lo de hoy ya no llega a una factura, no se acepta (y no se aparta nada).
    _fijar(conn, gente["ana"], tope_dia_usd_micro=20_000_000)
    _automatica(conn, "2026-10-14T08:00:00+00:00", alto, autorizacion=auto.vigente(conn)["id"])
    _fijar(conn, gente["ana"], tope_dia_usd_micro=alto + alto // 2,
           max_por_documento_usd_micro=alto + 1)
    solicitud = _contada(almacen, out)
    assert lectura.autorizar(conn, solicitud) == "nada_que_leer"
    assert _fila(conn, solicitud)["motivo_codigo"] == "limite_dia"
    assert _excluidos(conn) == {}


def test_lo_que_pasa_del_maximo_por_factura_no_se_lee_solo(almacen, gente, tmp_path) -> None:
    conn = almacen.conn
    out = tmp_path / "out"
    documentos = _del_correo(almacen, "una", "dos")
    _fijar(conn, gente["ana"], activa=0)
    solicitud = _contada(almacen, out)
    alto = _fila(conn, solicitud)["coste_max_usd_micro"] // 2
    lectura.autorizar(conn, solicitud)
    _fijar(conn, gente["ana"], max_por_documento_usd_micro=alto - 1)
    client = ClienteQueCuenta()
    estado, solicitud = _ronda(almacen, client, out)
    assert (estado, _fila(conn, solicitud)["motivo_codigo"]) == ("nada_que_leer", "excluidas")
    assert client.leidos == [] and _excluidos(conn) == {d: "grande" for d in documentos}
    automatico = usuario_sistema(conn, "automatico")
    assert [tuple(f) for f in conn.execute(
        "SELECT DISTINCT solicitud_id, por FROM exclusion_automatica")] == [(solicitud, automatico)]
    assert lectura.siguiente(conn).codigo == lectura.NADA
    # Espera a una persona, que si la puede leer desde Procesar.
    assert {d["documento_id"] for d in auto.esperan_persona(conn)["documentos"]} == set(documentos)
    assert {d["documento_id"] for d in auto.pendientes_del_correo(conn)} == set(documentos)
    assert verificar_evidencia(conn) == []


def test_cada_llamada_no_pasa_del_maximo_por_factura_ni_de_una_ronda(almacen, gente,
                                                                      tmp_path) -> None:
    """El maximo por factura es un tope duro de cada llamada (max_tokens), aunque quede mas
    del dia; y una ronda no lee mas de max_documentos aunque el tope diera para mas."""
    conn = almacen.conn
    out = tmp_path / "out"
    _del_correo(almacen, "una", "dos", "tres")

    class Anota(ClienteQueCuenta):
        def __init__(self) -> None:
            super().__init__()
            self.max_tokens: list[int] = []

        def parse(self, **peticion):
            self.max_tokens.append(peticion["max_tokens"])
            return super().parse(**peticion)

    client = Anota()
    _fijar(conn, gente["ana"], activa=0)
    tomada = lectura.tomar(conn, hay_pdf=True, automatica=True)
    estado, est = lectura.contar(conn, tomada.solicitud_id, lambda antes: lectura.estimar(
        client, [almacen.documentos.ruta(d["ruta_cas"]) for d in auto.elegibles(conn)], out,
        almacen=almacen, antes=antes))
    contado = est.documentos[0]
    lectura.autorizar(conn, tomada.solicitud_id)
    por_documento = contado.alto_usd_micro
    _fijar(conn, gente["ana"], tope_dia_usd_micro=20_000_000, max_documentos=2,
           max_por_documento_usd_micro=por_documento)
    estado, solicitud = _ronda(almacen, client, out)
    assert estado == "hecha" and len(client.leidos) == 2
    esperado, _peor = lectura.salida_que_cabe(est.modelo, contado.entrada, por_documento)
    assert client.max_tokens == [esperado, esperado]
    # La tercera, en la ronda siguiente.
    assert _ronda(almacen, client, out)[0] == "hecha" and len(client.leidos) == 3


def test_contar_aparta_lo_que_la_api_no_acepta(almacen, gente, tmp_path) -> None:
    conn = almacen.conn
    out = tmp_path / "out"
    mala, buena = _del_correo(almacen, "mala", "buena")
    _fijar(conn, gente["ana"])
    client = ClienteQueFalla(al_contar={"mala": DEL_DOCUMENTO["413"]})
    estado, solicitud = _ronda(almacen, client, out)
    assert estado == "hecha" and client.leidos == ["buena"]
    assert _excluidos(conn) == {mala: "rechazado_api"}
    assert conn.execute("SELECT solicitud_id FROM exclusion_automatica").fetchone()[0] == solicitud
    evento = conn.execute("SELECT * FROM evento WHERE tipo = 'lectura_excluida'").fetchone()
    assert "request_too_large" in evento["motivo"]
    assert auto.esperan_persona(conn)["documentos"][0]["documento_id"] == mala
    # Si la API no acepta ninguna de las nuevas: nada que leer, apartadas, sin espera.
    otra_mala = _del_correo(almacen, "otra-mala")[0]
    client = ClienteQueFalla(al_contar={"otra-mala": DEL_DOCUMENTO["400"]})
    estado, solicitud = _ronda(almacen, client, out)
    fila = _fila(conn, solicitud)
    assert (estado, fila["estado"], fila["motivo_codigo"]) == ("nada_que_leer", "nada_que_leer",
                                                               "excluidas")
    sha = conn.execute("SELECT sha256 FROM documento WHERE id = ?", (otra_mala,)).fetchone()[0]
    assert f"{sha}.pdf" in fila["motivo"] and _excluidos(conn)[otra_mala] == "rechazado_api"
    assert auto.espera_tras_fallo(conn) is None
    assert lectura.siguiente(conn).codigo == lectura.NADA
    del buena


@pytest.mark.parametrize("al", ["contar", "leer"])
def test_un_fallo_de_la_api_en_una_automatica_espera_y_no_aparta(almacen, gente, tmp_path,
                                                                 reloj, al) -> None:
    conn = almacen.conn
    out = tmp_path / "out"
    _del_correo(almacen, "una", "dos")
    _fijar(conn, gente["ana"])
    fabrica, motivo = FALLOS_API["402"]
    falla = {"una": fabrica, "dos": fabrica}
    client = ClienteQueFalla(**({"al_contar": falla} if al == "contar" else {"al_leer_falla": falla}))
    estado, solicitud = _ronda(almacen, client, out)
    fila = _fila(conn, solicitud)
    assert (estado, fila["estado"], fila["motivo_codigo"]) == ("fallida", "fallida", motivo)
    assert _excluidos(conn) == {}
    que = lectura.siguiente(conn)
    assert (que.codigo, que.parada, que.motivo) == (lectura.LIMITE, "fallo", "saldo")
    assert que.proximo_intento == marca(datetime.fromisoformat(fila["terminada_en"])
                                        + timedelta(hours=1))
    # A la hora se vuelve a probar (y, si sigue sin saldo, se espera el doble).
    reloj.avanzar(hours=1)
    estado, _solicitud = _ronda(almacen, client, out)
    assert estado == "fallida" and lectura.siguiente(conn).proximo_intento == marca(
        reloj.ahora() + timedelta(hours=2))
    assert _excluidos(conn) == {}
    # Con saldo otra vez, se leen y la espera vuelve a 1 h.
    reloj.avanzar(hours=2)
    estado, _solicitud = _ronda(almacen, ClienteQueCuenta(), out)
    assert estado == "hecha" and auto.espera_tras_fallo(conn) is None


def test_la_segunda_falla_por_el_documento_la_aparta(almacen, gente, tmp_path, reloj,
                                                     monkeypatch) -> None:
    # Un fallo sin uso cuenta lo peor que podia costar: con una salida corta, la otra cabe.
    monkeypatch.setenv("BMS_EXTRACT_MAX_TOKENS", "1000")
    conn = almacen.conn
    out = tmp_path / "out"
    mala, buena = _del_correo(almacen, "mala", "buena")
    _fijar(conn, gente["ana"])
    client = ClienteQueFalla(al_leer_falla={"mala": DEL_DOCUMENTO["400"]})
    assert _ronda(almacen, client, out)[0] == "hecha"
    # A la primera, se reintenta en la ronda siguiente.
    assert _excluidos(conn) == {}
    assert [d["documento_id"] for d in auto.elegibles(conn)] == [mala]
    estado, segunda = _ronda(almacen, client, out)
    assert estado == "hecha" and client.intentos.count("mala") == 2
    assert _excluidos(conn) == {mala: "fallo"}
    evento = conn.execute("SELECT * FROM evento WHERE tipo = 'lectura_excluida'").fetchone()
    usuario = conn.execute("SELECT nombre FROM usuario WHERE id = ?",
                           (evento["actor"],)).fetchone()[0]
    assert (usuario, evento["usuario_id"], json_fila(evento)["solicitud_id"]) == (
        "automatico", None, segunda)
    assert lectura.siguiente(conn).codigo == lectura.NADA
    del buena


def json_fila(evento) -> dict:
    import json

    return json.loads(evento["datos_json"])["fila"]


def test_un_fallo_de_una_persona_no_cuenta_para_apartarla(almacen, gente, tmp_path) -> None:
    """Lo que falla en una lectura de una persona no cuenta para las dos de la automatica."""
    conn = almacen.conn
    out = tmp_path / "out"
    mala = _del_correo(almacen, "mala")[0]
    client = ClienteQueFalla(al_leer_falla={"mala": DEL_DOCUMENTO["400"]})
    solicitud, _e = lectura.pedir(conn, gente["berta"])
    lectura.tomar(conn, hay_pdf=True)
    pdfs = cli._pdfs_a_leer(None, almacen, solicitud)
    lectura.contar(conn, solicitud, lambda antes: lectura.estimar(client, pdfs, out,
                                                                    almacen=almacen, antes=antes))
    servicios.ejecutar(conn, "aprobar_lectura", {
        "solicitud_id": solicitud, "huella_estimacion": _fila(conn, solicitud)["huella_estimacion"]},
        usuario_id=gente["berta"])
    assert lectura.leer(conn, solicitud, client=client, almacen=almacen, pdfs=pdfs,
                        out_dir=out).estado == "hecha"
    _fijar(conn, gente["ana"])
    assert _ronda(almacen, client, out)[0] == "hecha"
    assert _excluidos(conn) == {} and auto.elegibles(conn)[0]["documento_id"] == mala


def test_parar_una_automatica_la_pausa_hasta_manana(almacen, gente, tmp_path, reloj) -> None:
    conn = almacen.conn
    out = tmp_path / "out"
    _del_correo(almacen, "una", "dos")
    _fijar(conn, gente["ana"])

    def para(solicitud):
        servicios.ejecutar(conn, "cancelar_lectura", {"solicitud_id": solicitud},
                           usuario_id=gente["berta"])

    estado, solicitud = _ronda(almacen, ClienteQueCuenta(), out, cancelar=para)
    assert estado == "cancelada"
    pausa = auto.pausa_vigente(conn)
    assert (pausa["motivo"], pausa["por"], pausa["solicitud_id"], pausa["hasta"]) == (
        "persona", gente["berta"], solicitud, "2026-10-14T22:00:00+00:00")
    que = lectura.siguiente(conn)
    assert (que.codigo, que.parada, que.hasta) == (lectura.LIMITE, "persona",
                                                   "2026-10-14T22:00:00+00:00")
    # Parar no es un fallo tecnico: no hace esperar mas.
    assert auto.espera_tras_fallo(conn) is None
    # A las 00:00 de Amsterdam vuelve sola...
    reloj.instante = datetime(2026, 10, 14, 22, 0, tzinfo=UTC)
    assert lectura.siguiente(conn).codigo == lectura.LEER
    # ... y antes, una persona la puede volver a encender ("Weer aanzetten").
    reloj.instante = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
    servicios.ejecutar(conn, "reanudar_lectura_automatica", {}, usuario_id=gente["berta"])
    assert lectura.siguiente(conn).codigo == lectura.LEER
    # Parar una que aun no lee tambien pausa.
    tomada = lectura.tomar(conn, hay_pdf=True, automatica=True)
    para(tomada.solicitud_id)
    assert _fila(conn, tomada.solicitud_id)["estado"] == "cancelada"
    assert auto.pausa_vigente(conn)["solicitud_id"] == tomada.solicitud_id
    # Parar la de una persona no pausa la automatica.
    servicios.ejecutar(conn, "reanudar_lectura_automatica", {}, usuario_id=gente["berta"])
    suya, _e = lectura.pedir(conn, gente["berta"])
    para(suya)
    assert auto.pausa_vigente(conn) is None
    assert verificar_evidencia(conn) == []


def test_siguiente_en_su_orden(almacen, gente, tmp_path, reloj) -> None:
    conn = almacen.conn
    # Sin autorizacion y sin nada pedido: nada.
    assert lectura.siguiente(conn) == lectura.Siguiente(
        lectura.NADA, detalle="la lectura automatica esta apagada")
    # Lo que pide una persona va antes que nada, aunque la automatica este apagada.
    pedida, _e = lectura.pedir(conn, gente["berta"])
    assert lectura.siguiente(conn).codigo == lectura.PEDIDA
    lectura.tomar(conn, hay_pdf=True, solo_pedida=True)
    # Otra viva con su lector: nada.
    assert lectura.siguiente(conn).codigo == lectura.NADA
    lectura.cerrar(conn, pedida, "salida")
    autorizacion = _fijar(conn, gente["ana"])
    # Encendida, pero en pausa.
    auto.pausar(conn, "volumen")
    assert (lectura.siguiente(conn).codigo, lectura.siguiente(conn).parada) == (lectura.LIMITE,
                                                                               "volumen")
    auto.reanudar(conn, gente["berta"])
    # Tras un fallo tecnico, a esperar.
    _terminada(conn, marca(reloj.ahora()), motivo_codigo="api_no_disponible")
    que = lectura.siguiente(conn)
    assert (que.codigo, que.parada, que.motivo, que.desde, que.proximo_intento) == (
        lectura.LIMITE, "fallo", "api_no_disponible", "2026-10-14T09:30:00+00:00",
        "2026-10-14T10:30:00+00:00")
    reloj.avanzar(hours=1)
    # Sin nada que leer: nada.
    assert lectura.siguiente(conn).codigo == lectura.NADA
    _del_correo(almacen, "una")
    assert lectura.siguiente(conn).codigo == lectura.LEER
    # Lo de hoy ya no llega a una factura: parada hasta las 00:00.
    _automatica(conn, marca(reloj.ahora() - timedelta(minutes=5)), 1_500_001,
                autorizacion=autorizacion)
    que = lectura.siguiente(conn)
    assert (que.codigo, que.parada, que.hasta) == (lectura.LIMITE, "limite_dia",
                                                   "2026-10-14T22:00:00+00:00")
    reloj.instante = datetime(2026, 10, 14, 22, 0, tzinfo=UTC)
    assert lectura.siguiente(conn).codigo == lectura.LEER
    # Una automatica que su ciclo dejo a medias no para nada: tomar la cierra.
    tomada = lectura.tomar(conn, hay_pdf=True, automatica=True)
    assert lectura.siguiente(conn).codigo == lectura.NADA
    reloj.avanzar(minutes=46)
    assert lectura.siguiente(conn).codigo == lectura.LEER
    nueva = lectura.tomar(conn, hay_pdf=True, automatica=True)
    assert nueva.como == lectura.CREADA
    assert (_fila(conn, tomada.solicitud_id)["estado"],
            _fila(conn, tomada.solicitud_id)["motivo_codigo"]) == ("fallida", "abandonada")
    # El lector se cerro: no es un fallo tecnico, no hace esperar.
    assert auto.espera_tras_fallo(conn) is None


def test_una_automatica_que_esperaba_se_cierra_y_la_de_una_persona_se_vuelve_a_contar(
        almacen, gente, tmp_path, reloj) -> None:
    conn = almacen.conn
    _del_correo(almacen, "una")
    _fijar(conn, gente["ana"])
    tomada = lectura.tomar(conn, hay_pdf=True, automatica=True)
    lectura.contar(conn, tomada.solicitud_id, lambda antes: lectura.estimar(
        ClienteQueCuenta(), cli._pdfs_a_leer(None, almacen, tomada.solicitud_id),
        tmp_path / "out", almacen=almacen, antes=antes))
    # El ciclo murio entre contar y autorizar: a los 90 s sin senales, se cierra (no se vuelve
    # a contar como la de una persona).
    reloj.avanzar(seconds=91)
    otra = lectura.tomar(conn, hay_pdf=True, automatica=True)
    assert otra.como == lectura.CREADA
    assert _fila(conn, tomada.solicitud_id)["motivo_codigo"] == "abandonada"
    lectura.cerrar(conn, otra.solicitud_id, "salida")
    # La de una persona que esperaba el si y cuyo lector ya no esta: la automatica no la
    # toca, y el camino de la pedida la vuelve a contar.
    suya, _e = lectura.pedir(conn, gente["berta"])
    lectura.tomar(conn, hay_pdf=True, solo_pedida=True)
    lectura.contar(conn, suya, lambda _antes: lectura.estimar(
        ClienteQueCuenta(), cli._pdfs_a_leer(None, almacen, suya), tmp_path / "out",
        almacen=almacen))
    reloj.avanzar(seconds=91)
    assert lectura.siguiente(conn).codigo == lectura.PEDIDA
    assert lectura.tomar(conn, hay_pdf=True, automatica=True).como == lectura.OCUPADA
    assert lectura.tomar(conn, hay_pdf=True, solo_pedida=True) == lectura.Tomada(
        suya, lectura.TOMADA, "se vuelve a contar")
    # Sin nada pedido, --solo-pedida no crea ninguna.
    lectura.cerrar(conn, suya, "salida")
    assert lectura.tomar(conn, hay_pdf=True, solo_pedida=True).como == lectura.VACIO
    assert lectura.viva(conn) is None


def test_lo_que_lee_una_persona_incluye_lo_del_correo(almacen, gente, tmp_path) -> None:
    """La lectura de una persona (Procesar, leer-facturas): el buzon y lo que el correo trajo
    y falta por leer, menos lo que una persona aparto; la automatica, solo lo elegible."""
    conn = almacen.conn
    buzon = tmp_path / "buzon"
    buzon.mkdir()
    (buzon / "papel.pdf").write_bytes(PDF + b"%marca:papel\n")
    correo, apartada, grande = _del_correo(almacen, "correo", "apartada", "grande")
    auto.excluir(conn, [apartada], "persona", gente["berta"])
    auto.excluir(conn, [grande], "grande", usuario_sistema(conn, "automatico"),
                 solicitud_id=_terminada(conn, "2026-10-14T09:00:00+00:00", "nada_que_leer",
                                         "excluidas"))
    nombres = {p.name for p in cli._pdfs_a_leer(str(buzon), almacen, automatica=False)}
    sha = {d: conn.execute("SELECT sha256 FROM documento WHERE id = ?", (d,)).fetchone()[0]
           for d in (correo, apartada, grande)}
    assert nombres == {"papel.pdf", f"{sha[correo]}.pdf", f"{sha[grande]}.pdf"}
    # La automatica: nada sin autorizacion encendida; con ella, solo lo elegible.
    assert cli._pdfs_a_leer(str(buzon), almacen, automatica=True) == []
    _fijar(conn, gente["ana"])
    assert [p.name for p in cli._pdfs_a_leer(str(buzon), almacen, automatica=True)] == [
        f"{sha[correo]}.pdf"]


# ============================================================ el ciclo, por la CLI

@pytest.fixture
def ciclo(tmp_path, monkeypatch, capsys):
    """Las ordenes de ciclo.ps1 (§4.1) con cli.main, sobre una base en disco, una salida falsa
    y una API falsa que sin la salida encendida no se alcanza (como test_lectura_lector)."""
    db = tmp_path / "datos" / "bms.sqlite3"
    buzon = tmp_path / "buzon" / "facturas"
    buzon.mkdir(parents=True)
    out = tmp_path / "datos" / "out"
    with preparar(db) as almacen:
        ana = persona(almacen.conn, "Ana", "administrador")
    salida = SalidaFalsa()
    estado = {"api": ApiFalsa(salida), "ventana": None}

    def cliente_api(_anthropic):
        if not salida.encendida:
            raise LecturaNoAislada("no se lee nada ni se paga nada: sin la salida")
        return estado["api"]

    def sin_ventana():
        raise AssertionError("el ciclo no lee ninguna ventana")

    monkeypatch.setattr(cli, "_cliente_api", cliente_api)
    monkeypatch.setattr(cli, "_linea_de_la_ventana", sin_ventana)

    def orden(*argumentos: str) -> int:
        return cli.main([*argumentos, "--db", str(db)])

    def leer_con_salida(solicitud: str, *, automatica: bool) -> list[str]:
        """Leer-Con-Salida de ciclo.ps1: la salida, contar, autorizar o esperar --solo-app,
        leer, y pase lo que pase la salida apagada y la lectura cerrada si quedo a medias."""
        pasos = []
        salida.encender()
        try:
            pasos.append("contar")
            if orden("lectura", "contar", solicitud, str(buzon), "--out", str(out)) != 0:
                return pasos
            if automatica:
                pasos.append("autorizar")
                codigo = orden("lectura", "autorizar", solicitud)
            else:
                pasos.append("esperar")
                codigo = orden("lectura", "esperar", solicitud, "--solo-app")
            if codigo != 0:
                return pasos
            pasos.append("leer")
            orden("lectura", "leer", solicitud, str(buzon), "--out", str(out))
            return pasos
        finally:
            salida.apagar()
            orden("lectura", "cerrar", solicitud, "--motivo", "interrumpida", "--si-viva")

    def una_vuelta() -> tuple[int, list[str]]:
        """Lo que hace el ciclo con la lectura: (lo que dijo siguiente, los pasos)."""
        capsys.readouterr()
        codigo = orden("lectura", "siguiente")
        if codigo == 0:
            argumentos = ("lectura", "tomar", "--automatica")
        elif codigo == cli.LECTURA_PEDIDA:
            argumentos = ("lectura", "tomar", str(buzon), "--solo-pedida")
        else:
            return codigo, []
        if orden(*argumentos) != 0:
            return codigo, ["tomar"]
        solicitud = capsys.readouterr().out.strip().splitlines()[-1]
        return codigo, ["tomar"] + leer_con_salida(solicitud, automatica=codigo == 0)

    def con_la_base(funcion):
        with preparar(db) as almacen:
            return funcion(almacen)

    return {"vuelta": una_vuelta, "base": con_la_base, "ana": ana, "salida": salida,
            "estado": estado, "buzon": buzon, "orden": orden, "monkeypatch": monkeypatch}


def test_el_ciclo_por_la_cli(ciclo, capsys) -> None:
    base = ciclo["base"]
    ana = ciclo["ana"]
    assert ciclo["vuelta"]() == (cli.LECTURA_NADA, [])
    base(lambda a: _del_correo(a, "una", "dos"))
    assert ciclo["vuelta"]() == (cli.LECTURA_NADA, [])           # apagada
    base(lambda a: auto.fijar(a.conn, ana, **POR_DEFECTO, motivo="Las del correo"))
    codigo, pasos = ciclo["vuelta"]()
    assert (codigo, pasos) == (0, ["tomar", "contar", "autorizar", "leer"])
    assert sorted(ciclo["estado"]["api"].leidos) == ["dos", "una"]
    assert ciclo["salida"].historia == ["encendida", "apagada"]
    fila = base(lambda a: a.conn.execute(
        "SELECT * FROM solicitud_lectura ORDER BY id DESC").fetchone())
    assert (fila["origen"], fila["estado"], fila["aprobada_via"]) == ("automatica", "hecha",
                                                                      "automatica")
    # Nada nuevo: no se enciende nada.
    assert ciclo["vuelta"]() == (cli.LECTURA_NADA, [])
    # Parada (pausa por volumen): 9, y dice por que.
    base(lambda a: auto.pausar(a.conn, "volumen"))
    base(lambda a: _del_correo(a, "tres"))
    capsys.readouterr()
    assert ciclo["orden"]("lectura", "siguiente") == cli.LECTURA_LIMITE
    assert "mucho mas correo de lo normal" in capsys.readouterr().err
    assert ciclo["salida"].historia == ["encendida", "apagada"]


def test_el_ciclo_lee_la_pedida_con_el_si_de_la_app(ciclo) -> None:
    base = ciclo["base"]
    base(lambda a: _del_correo(a, "una"))
    (ciclo["buzon"] / "papel.pdf").write_bytes(PDF + b"%marca:papel\n")
    base(lambda a: servicios.ejecutar(a.conn, "pedir_lectura", {}, usuario_id=ciclo["ana"]))

    def la_app_dice_que_si():
        def linea(_segundos):
            def si(almacen):
                fila = almacen.conn.execute(
                    "SELECT * FROM solicitud_lectura ORDER BY id DESC").fetchone()
                servicios.ejecutar(almacen.conn, "aprobar_lectura", {
                    "solicitud_id": fila["id"], "huella_estimacion": fila["huella_estimacion"]},
                    usuario_id=ciclo["ana"])
            base(si)
            return None
        return linea

    ciclo["monkeypatch"].setattr(cli, "_sin_ventana", la_app_dice_que_si)
    codigo, pasos = ciclo["vuelta"]()
    assert (codigo, pasos) == (cli.LECTURA_PEDIDA, ["tomar", "contar", "esperar", "leer"])
    assert sorted(ciclo["estado"]["api"].leidos) == ["papel", "una"]
    fila = base(lambda a: a.conn.execute(
        "SELECT * FROM solicitud_lectura ORDER BY id DESC").fetchone())
    assert (fila["origen"], fila["estado"], fila["aprobada_via"]) == ("app", "hecha", "app")


def test_autorizar_por_la_cli_dice_por_que_no(ciclo, capsys) -> None:
    base = ciclo["base"]
    base(lambda a: _del_correo(a, "una"))
    base(lambda a: auto.fijar(a.conn, ciclo["ana"], **POR_DEFECTO, motivo="Las del correo"))
    capsys.readouterr()
    assert ciclo["orden"]("lectura", "tomar", "--automatica") == 0
    solicitud = capsys.readouterr().out.strip()
    ciclo["salida"].encender()
    assert ciclo["orden"]("lectura", "contar", solicitud, str(ciclo["buzon"])) == 0
    # La apagan entre contar y autorizar: no se lee.
    base(lambda a: auto.fijar(a.conn, ciclo["ana"], **{**POR_DEFECTO, "activa": 0},
                              motivo="Ahora no"))
    capsys.readouterr()
    assert ciclo["orden"]("lectura", "autorizar", solicitud) == cli.LECTURA_NADA
    assert "la lectura automatica esta apagada" in capsys.readouterr().err
    # Una que ya no espera, o una de una persona: no.
    assert ciclo["orden"]("lectura", "autorizar", solicitud) == cli.LECTURA_FALLIDA
    # Esperar el si de una automatica no tiene sentido.
    assert ciclo["orden"]("lectura", "esperar", solicitud) == cli.LECTURA_FALLIDA
    ciclo["salida"].apagar()
