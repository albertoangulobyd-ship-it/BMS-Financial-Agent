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
    ({"error_codigo": "control_no_existe", "error_desde": marca(AHORA)},
     "de controlemailbox bestaat niet meer", "the control mailbox no longer exists"),
    ({"ultima_buena": marca(AHORA - timedelta(hours=25))},
     "al meer dan 24 uur geen geslaagde controle", "no successful mailbox check for more"),
    ({"ultima_buena": None, "error_codigo": "credencial", "error_desde": marca(AHORA)},
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
    # Una lectura que termina de otra forma despues: ya no.
    solicitud, _e = lectura.pedir(conn, ana)
    lectura.cerrar(conn, solicitud, "salida")
    assert _bandas(conn) == []


def test_la_banda_de_las_facturas_que_esperan_mas_de_4_horas(almacen, reloj) -> None:
    from conftest import persona
    from test_lectura_automatica import POR_DEFECTO, _del_correo

    conn = almacen.conn
    _del_correo(almacen, "una", "dos", recibido=marca(AHORA - timedelta(hours=5)))
    _del_correo(almacen, "nueva", recibido=marca(AHORA - timedelta(hours=1)))
    assert _bandas(conn) == []                         # apagada: no se espera nada
    ana = persona(conn, "Ana", "administrador")
    auto.fijar(conn, ana, **POR_DEFECTO, motivo="Las del correo")
    [banda] = _bandas(conn)
    assert banda == ("LEZEN · 2 facturen wachten al meer dan 4 uur op automatisch lezen. · "
                     "READING · 2 invoices have waited more than 4 hours for automatic reading.")
    # En pausa (una persona o el volumen) no es urgente: ya se sabe por que.
    auto.pausar(conn, "volumen")
    assert _bandas(conn) == []


def test_la_banda_por_lo_que_dejo_registrar(almacen, tmp_path) -> None:
    """De `correo registrar --fallo` a la banda: un certificado que caduca dentro de poco sale
    aunque el correo este parado por la salida."""
    registrar.apuntar_fallo(almacen, "salida")
    almacen.conn.execute("UPDATE estado_correo SET ultima_buena = ?, credencial_caduca_en = ?",
                         (marca(AHORA), marca(AHORA + timedelta(days=5))))
    [banda] = _bandas(almacen.conn)
    assert "verloopt over 5 dagen" in banda
