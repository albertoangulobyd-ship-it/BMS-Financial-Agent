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
