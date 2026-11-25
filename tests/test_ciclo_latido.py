"""El latido del ciclo automatico (paso 18, paso 10 del plan; diseno §3.9, §4.1) y las bandas del
servidor que lo dicen (paso 11; diseno §6.1).

- `ciclo latido` escribe estado_ciclo: cuando se vio, si esta en pausa (y desde cuando), el disco
  libre y la variante; lo que no se da queda como estaba;
- la banda roja de la app con cada condicion de §6.1, a partir de una base de prueba.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from bms_agent import ciclo, cli
from bms_agent.almacen import Almacen, abrir, preparar
from bms_agent.almacen.documentos import AlmacenDocumentos
from bms_agent.almacen.migrar import migrar
from bms_agent.reloj import RelojFijo, marca

AHORA = datetime(2026, 11, 24, 10, 0, tzinfo=timezone.utc)
GIB = 1024 ** 3


@pytest.fixture
def reloj() -> RelojFijo:
    return RelojFijo(AHORA)


@pytest.fixture
def almacen(reloj, tmp_path) -> Almacen:
    conn = abrir(":memory:", reloj=reloj)
    migrar(conn)
    try:
        yield Almacen(conn, AlmacenDocumentos(tmp_path / "documentos"))
    finally:
        conn.close()


def _fila(conn) -> dict:
    return dict(conn.execute("SELECT * FROM estado_ciclo").fetchone())


def test_el_latido_escribe_estado_ciclo(almacen, reloj) -> None:
    conn = almacen.conn
    assert ciclo.leer(conn) is None
    ciclo.latido(conn, disco_libre=200 * GIB, variante="docker")
    assert _fila(conn) == {"id": 1, "visto_en": marca(AHORA), "variante": "docker",
                           "pausado": 0, "pausado_desde": None,
                           "disco_libre_bytes": 200 * GIB, "actualizado_en": marca(AHORA)}
    # Lo que no se da queda como estaba.
    reloj.avanzar(minutes=5)
    hecho = ciclo.latido(conn)
    assert (hecho.visto_en, hecho.variante, hecho.disco_libre_bytes, hecho.pausado) == (
        marca(AHORA + timedelta(minutes=5)), "docker", 200 * GIB, False)
    # En pausa: desde cuando, y sigue siendo desde entonces.
    reloj.avanzar(minutes=5)
    ciclo.latido(conn, pausado=True)
    desde = marca(AHORA + timedelta(minutes=10))
    assert (_fila(conn)["pausado"], _fila(conn)["pausado_desde"]) == (1, desde)
    reloj.avanzar(hours=3)
    ciclo.latido(conn, pausado=True)
    assert _fila(conn)["pausado_desde"] == desde
    # El ciclo vuelve a pasar: ya no esta en pausa.
    reloj.avanzar(minutes=5)
    ciclo.latido(conn, disco_libre=9 * GIB)
    fila = _fila(conn)
    assert (fila["pausado"], fila["pausado_desde"], fila["disco_libre_bytes"]) == (0, None,
                                                                                9 * GIB)
    assert ciclo.leer(conn).disco_bajo


@pytest.mark.parametrize("valores", [{"disco_libre": -1}, {"disco_libre": True},
                                     {"disco_libre": 2 ** 70}, {"variante": "windows"}])
def test_el_latido_no_apunta_lo_que_no_vale(almacen, valores) -> None:
    with pytest.raises(ValueError):
        ciclo.latido(almacen.conn, **valores)
    assert ciclo.leer(almacen.conn) is None


def test_ciclo_latido_por_la_cli(tmp_path, capsys) -> None:
    db = tmp_path / "datos" / "bms.sqlite3"
    assert cli.main(["ciclo", "latido", "--disco-libre", str(50 * GIB), "--variante", "docker",
                     "--db", str(db)]) == 0
    assert "50 GiB libres" in capsys.readouterr().out
    assert cli.main(["ciclo", "latido", "--pausado", "--db", str(db)]) == 0
    assert "en pausa" in capsys.readouterr().out
    assert cli.main(["ciclo", "latido", "--disco-libre", str(GIB), "--reanudado",
                     "--db", str(db)]) == 0
    assert "poco disco" in capsys.readouterr().err
    assert cli.main(["ciclo", "latido", "--disco-libre", "-5", "--db", str(db)]) == 2
    with pytest.raises(SystemExit):
        cli.main(["ciclo", "latido", "--pausado", "--reanudado", "--db", str(db)])
    with preparar(db) as almacen:
        fila = almacen.conn.execute("SELECT * FROM estado_ciclo").fetchone()
        assert (fila["pausado"], fila["disco_libre_bytes"], fila["variante"]) == (0, GIB,
                                                                                "docker")


# ============================================================ las bandas del servidor (§6.1)

from bms_agent import consultas  # noqa: E402
from bms_agent import lectura_automatica as auto  # noqa: E402
from bms_agent.correo import registrar  # noqa: E402


def _estado_correo(conn, **columnas) -> None:
    valores = {"buzon": "facturen@contoso.onmicrosoft.com",
               "ultima_consulta": marca(AHORA - timedelta(minutes=5)),
               "ultima_buena": marca(AHORA - timedelta(minutes=5)), "error_codigo": None,
               "error_desde": None, "alcance_comprobado_en": marca(AHORA - timedelta(hours=1)),
               "alcance_bien": 1, "credencial_caduca_en": marca(AHORA + timedelta(days=400)),
               "hoy_json": "{}", "aviso_volumen": 0, "actualizado_en": marca(AHORA),
               **columnas}
    conn.execute("DELETE FROM estado_correo")
    conn.execute(f"INSERT INTO estado_correo (id, {', '.join(valores)}) VALUES "
                 f"(1, {', '.join('?' * len(valores))})", tuple(valores.values()))


def _bandas(conn) -> list[str]:
    return consultas.bandas_urgentes(conn)


def test_sin_nada_no_hay_bandas(almacen) -> None:
    assert _bandas(almacen.conn) == []
    # El correo al dia y el ciclo que acaba de pasar, con disco: nada urgente.
    _estado_correo(almacen.conn)
    ciclo.latido(almacen.conn, disco_libre=200 * GIB, variante="docker")
    assert _bandas(almacen.conn) == []


@pytest.mark.parametrize("columnas, nl, en", [
    ({"credencial_caduca_en": marca(AHORA - timedelta(hours=1))},
     "Er komen geen facturen meer binnen: het certificaat is verlopen",
     "Invoices are no longer coming in: the certificate has expired"),
    ({"credencial_caduca_en": marca(AHORA + timedelta(days=12, hours=1))},
     "Het certificaat verloopt over 12 dagen (06-12-2026)",
     "The certificate expires in 12 days (06-12-2026)"),
    ({"alcance_bien": 0, "error_codigo": "alcance", "error_desde": marca(AHORA)},
     "het programma kan meer lezen dan alleen de facturenmailbox",
     "the program can read more than the invoice mailbox"),
    # La ultima comprobacion del alcance salio mal, aunque la ronda no lo diga como error.
    ({"alcance_bien": 0}, "het programma kan meer lezen dan alleen de facturenmailbox",
     "the program can read more than the invoice mailbox"),
    ({"error_codigo": "control_no_existe", "error_desde": marca(AHORA)},
     "de controlemailbox bestaat niet meer", "the control mailbox no longer exists"),
    ({"ultima_buena": marca(AHORA - timedelta(hours=25))},
     "al meer dan 24 uur geen geslaagde controle", "no successful mailbox check for more"),
    # Sin ninguna buena todavia (ni rondas apuntadas): desde que empezo el error.
    ({"ultima_buena": None, "error_codigo": "credencial",
      "error_desde": marca(AHORA - timedelta(hours=25))},
     "al meer dan 24 uur geen geslaagde controle", "no successful mailbox check for more"),
])
def test_las_bandas_del_correo(almacen, columnas, nl, en) -> None:
    _estado_correo(almacen.conn, **columnas)
    [banda] = _bandas(almacen.conn)
    assert banda.startswith("MAILBOX · ") and nl in banda and en in banda
    assert "facturen@" not in banda


def test_sin_configurar_no_hay_banda_del_correo(almacen) -> None:
    _estado_correo(almacen.conn, ultima_buena=None, error_codigo="sin_configurar",
                   error_desde=marca(AHORA), credencial_caduca_en=None)
    assert _bandas(almacen.conn) == []


def test_un_certificado_caducado_no_dice_dos_veces_lo_mismo(almacen) -> None:
    _estado_correo(almacen.conn, credencial_caduca_en=marca(AHORA - timedelta(days=3)),
                   ultima_buena=marca(AHORA - timedelta(days=3)), error_codigo="credencial",
                   error_desde=marca(AHORA - timedelta(days=3)))
    assert len(_bandas(almacen.conn)) == 1


def test_las_bandas_del_ciclo_y_del_disco(almacen, reloj) -> None:
    conn = almacen.conn
    ciclo.latido(conn, disco_libre=200 * GIB)
    reloj.avanzar(minutes=31)
    [banda] = _bandas(conn)
    assert banda == ("AUTOMATISCH · Het automatische werk loopt niet sinds 24-11-2026 11:00. "
                     "Zie automatico.bat -Estado. · AUTOMATIC · Automatic work has not run since "
                     "24-11-2026 11:00. See automatico.bat -Estado.")
    # En pausa: hasta 24 horas no es urgente (alguien lo paro); despues, si.
    ciclo.latido(conn, pausado=True)
    reloj.avanzar(hours=23)
    assert _bandas(conn) == []
    reloj.avanzar(hours=2)
    [banda] = _bandas(conn)
    assert "loopt niet sinds 24-11-2026 11:31" in banda
    # El disco.
    ciclo.latido(conn, disco_libre=8 * GIB + 5)
    [banda] = _bandas(conn)
    assert banda == ("SCHIJF · Nog maar 8 GB vrij: er wordt niets opgehaald of gelezen. · "
                     "DISK · Only 8 GB free: nothing is fetched or read.")


def test_la_banda_de_la_api_sin_saldo_o_con_la_clave_rechazada(almacen) -> None:
    from conftest import persona

    from bms_agent import lectura

    conn = almacen.conn
    ana = persona(conn, "Ana", "administracion")
    for motivo, nl, en in (("saldo", "Het tegoed voor de API is op", "The API credit has run out"),
                           ("clave_rechazada", "De API weigert de sleutel",
                            "The API refuses the key")):
        solicitud, _e = lectura.pedir(conn, ana)
        lectura.cerrar(conn, solicitud, motivo)
        [banda] = _bandas(conn)
        assert banda.startswith(f"LEZEN · {nl}") and f"READING · {en}" in banda
        # En la nativa (y en local) la clave se cambia con clave.bat; en Docker no hay
        # clave.bat: se nombra el fichero de docker\secretos (paso 12).
        docker = consultas.bandas_urgentes(conn, "contenedor")
        if motivo == "clave_rechazada":
            assert "(clave.bat)" in banda and "clave.bat" not in docker[0]
            assert "docker\\secretos\\anthropic_api_key.txt" in docker[0]
            assert consultas.bandas_urgentes(conn, "nativo") == [banda]
        else:
            assert docker == [banda]
    # Una lectura que termina de otra forma despues: ya no.
    solicitud, _e = lectura.pedir(conn, ana)
    lectura.cerrar(conn, solicitud, "salida")
    assert _bandas(conn) == []


def test_la_banda_de_las_facturas_que_esperan_mas_de_4_horas(almacen, reloj) -> None:
    """§6.1: elegibles que esperan mas de 4 horas desde que entraron (las registro `correo
    registrar`), con la automatica encendida todo ese tiempo, sin pausa ni tope, y sin ninguna
    automatica buena en esas 4 horas (la lectura falla sin decirlo)."""
    from conftest import persona
    from test_lectura_automatica import POR_DEFECTO, _del_correo

    conn = almacen.conn
    ana = persona(conn, "Ana", "administrador")
    _del_correo(almacen, "una", "dos", recibido=marca(AHORA - timedelta(hours=1)))
    reloj.avanzar(hours=5)
    assert _bandas(conn) == []                         # apagada: no se espera nada
    # Recien encendida, lo que ya estaba no lleva 4 horas esperando a la automatica.
    auto.fijar(conn, ana, **POR_DEFECTO, motivo="Las del correo")
    reloj.avanzar(hours=3, minutes=59)
    assert _bandas(conn) == []
    # Cambiar los topes no la apaga: sigue contando desde que se encendio.
    auto.fijar(conn, ana, **{**POR_DEFECTO, "max_documentos": 7}, motivo="Mas por ronda")
    reloj.avanzar(minutes=2)
    _del_correo(almacen, "nueva", recibido=marca(reloj.ahora() - timedelta(minutes=1)))
    [banda] = _bandas(conn)
    assert banda == ("LEZEN · 2 facturen wachten al meer dan 4 uur op automatisch lezen. · "
                     "READING · 2 invoices have waited more than 4 hours for automatic reading.")
    # En pausa (una persona o el volumen) no es urgente: ya se sabe por que.
    auto.pausar(conn, "volumen")
    assert _bandas(conn) == []


def test_la_espera_cuenta_desde_que_entro_no_desde_que_la_recibio_microsoft(almacen, reloj
                                                                            ) -> None:
    """Un correo que llego de noche (o antes de configurar el correo) y que se registra ahora no
    lleva horas esperando: la banda cuenta desde que entro."""
    from conftest import persona
    from test_lectura_automatica import POR_DEFECTO, _correo, _documento

    conn = almacen.conn
    auto.fijar(conn, persona(conn, "Ana", "administrador"), **POR_DEFECTO, motivo="Solas")
    reloj.avanzar(hours=6)
    documento = _documento(almacen, "noche")
    mensaje = _correo(conn, marca(reloj.ahora() - timedelta(hours=8)),
                      ("documento", documento, "noche.pdf"))
    conn.execute("DROP TRIGGER mensaje_correo_sin_update")
    conn.execute("UPDATE mensaje_correo SET registrado_en = ? WHERE id = ?",
                 (marca(reloj.ahora()), mensaje))
    assert _bandas(conn) == []
    reloj.avanzar(hours=4, minutes=1)
    [banda] = _bandas(conn)
    assert banda.startswith("LEZEN · 1 facturen wachten al meer dan 4 uur")


def test_una_automatica_buena_en_las_ultimas_4_horas_quita_la_banda(almacen, reloj) -> None:
    """Una automatica que salio bien hace poco dice que la lectura funciona; una de hace mas de 4
    horas, con las lecturas fallando desde entonces, no tapa la banda (O2)."""
    from conftest import persona
    from test_lectura_automatica import POR_DEFECTO, _automatica, _del_correo

    conn = almacen.conn
    auto.fijar(conn, persona(conn, "Ana", "administrador"), **POR_DEFECTO, motivo="Solas")
    _del_correo(almacen, "una", recibido=marca(AHORA))
    reloj.avanzar(hours=1)

    def hecha() -> None:
        _automatica(conn, marca(reloj.ahora()), 1000, autorizacion=auto.vigente(conn)["id"])

    hecha()                         # leyo otras; esta sigue esperando
    reloj.avanzar(hours=3, minutes=30)
    assert _bandas(conn) == []      # una buena hace 3,5 horas
    reloj.avanzar(minutes=31)
    [banda] = _bandas(conn)         # la ultima buena, hace mas de 4 horas
    assert banda.startswith("LEZEN · 1 facturen wachten al meer dan 4 uur")
    hecha()
    assert _bandas(conn) == []


def test_la_banda_por_lo_que_dejo_registrar(almacen, tmp_path) -> None:
    """De `correo registrar --fallo` a la banda: un certificado que caduca dentro de poco sale
    aunque el correo este parado por la salida."""
    _estado_correo(almacen.conn, credencial_caduca_en=marca(AHORA + timedelta(days=5)))
    assert registrar.apuntar_fallo(almacen, "salida")
    [banda] = _bandas(almacen.conn)
    assert "verloopt over 5 dagen" in banda


def test_la_primera_ronda_que_falla_no_es_24_horas_sin_ronda_buena(almacen, reloj,
                                                                    tmp_path) -> None:
    """Un buzon recien configurado cuya primera ronda fallo hace 5 minutos no lleva 24 horas sin
    ninguna buena: la API dice `retrasado` y no hay banda. Las 24 horas cuentan desde la primera
    ronda apuntada."""
    from test_correo_registrar import Bandeja

    caja = Bandeja(tmp_path / "correo")
    caja.estado_json(empezada="2026-11-24T09:55:00Z", codigo="sin_conexion", mensajes=0, pdf=0,
                     ultima_buena=None)
    # Sin ninguna buena, sin rondas apuntadas y sin error: no hay desde cuando contar.
    _estado_correo(almacen.conn, ultima_buena=None)
    assert _bandas(almacen.conn) == []
    registrar.registrar(almacen, entrada=caja.entrada, estado=caja.estado)
    correo = consultas.correo(almacen.conn, "contenedor")
    assert (correo["estado"], correo["error_codigo"], correo["ultima_buena"]) == (
        "retrasado", "sin_conexion", None)
    assert _bandas(almacen.conn) == []
    # Un dia despues, sin ninguna buena todavia (otro error, otra fila): ya si.
    reloj.avanzar(hours=23, minutes=50)
    caja.estado_json(empezada="2026-11-25T09:45:00Z", codigo="credencial", mensajes=0, pdf=0,
                     ultima_buena=None)
    registrar.registrar(almacen, entrada=caja.entrada, estado=caja.estado)
    assert _bandas(almacen.conn) == []
    reloj.avanzar(minutes=10, seconds=1)
    [banda] = _bandas(almacen.conn)
    assert "al meer dan 24 uur geen geslaagde controle" in banda
