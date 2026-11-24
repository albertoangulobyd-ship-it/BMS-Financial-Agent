"""La lectura de los PDF pedida desde la app (paso 17, lectura.py; especificacion §5).

Puertas que viven aqui:

- la peticion: una sola viva, quien puede pedirla, darle el si o cancelarla
  (importar_datos; "consulta" no), cada cambio en la auditoria;
- el si vale solo para la estimacion que se vio (su huella: con otra, un conflicto) y antes
  de que caduque (15 minutos), y lo aprobado no se puede cambiar despues;
- el lector espera el si de la app o escrito en su ventana; con un no o sin respuesta no
  gasta nada;
- leyendo: solo lo que se conto y se aprobo, nunca por encima del tope, y para despues del
  documento en curso si se lo piden; la pasada recorre sus fases en orden con sus cuentas, y
  cada documento acaba nuevo, ya leido, posible duplicado o fallido;
- una lectura que un lector dejo a medias no bloquea la siguiente;
- lo que la API no acepta no bloquea nada (paso 18, D12): un PDF de mas de MAX_BYTES_API, o
  uno que la API rechaza al contarlo, queda omitido y los demas se cuentan y se leen; un
  fallo de la API que no es del documento (la clave, el saldo, no disponible) para la cuenta
  o la pasada con su motivo, sin contar ningun documento como fallido.

Ningun test llama a la API: el cliente falso cuenta lo que se pagaria.
"""

from __future__ import annotations

import base64
import itertools
import json
import re
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from conftest import estimacion_lectura, lectura_esperando, persona
from test_extraccion_pasada import _extraccion

from bms_agent import campos, lectura, servicios
from bms_agent.almacen import transaccion
from bms_agent.extract import extraer_pasada
from bms_agent.permisos import PermisoDenegado

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
_PETICIONES = itertools.count(1)


@pytest.fixture
def gente(almacen):
    conn = almacen.conn
    return {"ana": persona(conn, "Ana", "administracion"),
            "carla": persona(conn, "Carla", "consulta")}


def _fila(conn, solicitud_id):
    return conn.execute("SELECT * FROM solicitud_lectura WHERE id = ?",
                        (solicitud_id,)).fetchone()


def _eventos(conn, solicitud_id) -> list[str]:
    return [f["tipo"] for f in conn.execute(
        "SELECT tipo FROM evento WHERE tabla = 'solicitud_lectura' AND fila_id = ? "
        "ORDER BY id", (solicitud_id,))]


# ============================================================ la peticion

def test_una_lectura_pedida_desde_la_app_y_solo_una_viva(almacen, gente) -> None:
    conn = almacen.conn
    diferencia = servicios.ejecutar(conn, "pedir_lectura", {}, usuario_id=gente["ana"])
    solicitud = diferencia.detalle["solicitud_id"]
    fila = _fila(conn, solicitud)
    assert (fila["estado"], fila["origen"], fila["pedida_por"]) == ("pedida", "app",
                                                                     gente["ana"])
    evento = conn.execute("SELECT * FROM evento WHERE id = ?",
                          (diferencia.evento_id,)).fetchone()
    assert (evento["tipo"], evento["usuario_id"], evento["actor"]) == (
        "lectura_pedida", gente["ana"], gente["ana"])
    # Pedir no toca nada que lea una regla: no pasa el motor.
    assert diferencia.ejecucion_id is None
    # Otra mientras hay una viva: no (un 409 en /api/v2).
    with pytest.raises(lectura.EstadoNoValido, match="una cada vez"):
        servicios.ejecutar(conn, "pedir_lectura", {}, usuario_id=gente["ana"])
    assert servicios.codigo_de_error(lectura.EstadoNoValido("x")) == "estado_no_valido"
    # Quien solo consulta no pide, ni da el si, ni dice que no.
    for orden, datos in (("pedir_lectura", {}),
                         ("aprobar_lectura", {"solicitud_id": solicitud,
                                              "huella_estimacion": "0" * 64}),
                         ("cancelar_lectura", {"solicitud_id": solicitud})):
        with pytest.raises(PermisoDenegado):
            servicios.ejecutar(conn, orden, datos, usuario_id=gente["carla"])
    # Y la base no admite dos vivas, aunque alguien se salte el codigo.
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        with transaccion(conn):
            conn.execute("INSERT INTO solicitud_lectura (origen, pedida_en, estado, "
                         "actualizada_en) VALUES ('lector', '2026-10-14T09:30:00+00:00', "
                         "'comprobando', '2026-10-14T09:30:00+00:00')")


def test_el_lector_toma_la_pedida_o_crea_una(almacen, gente) -> None:
    conn = almacen.conn
    # Sin PDF y sin nada pedido: nada que hacer, y no se crea ninguna.
    assert lectura.tomar(conn, hay_pdf=False) == lectura.Tomada(
        None, lectura.VACIO, lectura.MOTIVOS["buzon_vacio"])
    assert conn.execute("SELECT count(*) FROM solicitud_lectura").fetchone()[0] == 0
    # Sin PDF con una pedida: termina en nada_que_leer.
    pedida, _e = lectura.pedir(conn, gente["ana"])
    assert lectura.tomar(conn, hay_pdf=False).como == lectura.VACIO
    assert (_fila(conn, pedida)["estado"], _fila(conn, pedida)["motivo_codigo"]) == (
        "nada_que_leer", "buzon_vacio")
    # Con PDF, la pedida pasa a comprobando.
    pedida, _e = lectura.pedir(conn, gente["ana"])
    tomada = lectura.tomar(conn, hay_pdf=True)
    assert (tomada.solicitud_id, tomada.como) == (pedida, lectura.TOMADA)
    assert _fila(conn, pedida)["estado"] == "comprobando"
    assert _fila(conn, pedida)["tomada_en"] is not None
    # Otro lector a la vez: no la toca.
    assert lectura.tomar(conn, hay_pdf=True).como == lectura.OCUPADA
    assert _eventos(conn, pedida) == ["lectura_pedida", "lectura_tomada"]
    lectura.cerrar(conn, pedida, "salida")
    # Sin nada pedido, el lector crea la suya (origen lector, de nadie).
    creada = lectura.tomar(conn, hay_pdf=True)
    fila = _fila(conn, creada.solicitud_id)
    assert (creada.como, fila["origen"], fila["pedida_por"], fila["estado"]) == (
        lectura.CREADA, "lector", None, "comprobando")
    evento = conn.execute("SELECT * FROM evento ORDER BY id DESC").fetchone()
    assert (evento["tipo"], evento["usuario_id"]) == ("lectura_pedida", None)


def test_contar_deja_la_estimacion_su_huella_y_el_plazo(almacen, gente, reloj) -> None:
    conn = almacen.conn
    est = estimacion_lectura(nuevos=3, ya_leidos=2, bajo=50_000, alto=60_000)
    solicitud = lectura_esperando(conn, gente["ana"], est)
    fila = _fila(conn, solicitud)
    assert (fila["estado"], fila["pdf_nuevos"], fila["pdf_ya_leidos"]) == (
        "esperando_aprobacion", 3, 2)
    assert (fila["coste_min_usd_micro"], fila["coste_max_usd_micro"]) == (150_000, 180_000)
    assert fila["huella_estimacion"] == est.huella(solicitud)
    assert json.loads(fila["estimacion_json"]) == est.a_json()
    assert fila["caduca_en"] == (reloj.ahora() + timedelta(minutes=15)).isoformat()
    assert _eventos(conn, solicitud) == ["lectura_pedida", "lectura_tomada",
                                         "lectura_contando", "lectura_contada"]
    # La huella cambia con cualquier cosa que se aprueba: otra peticion, otro documento,
    # otra horquilla.
    assert est.huella(solicitud) != est.huella(solicitud + 1)
    assert est.huella(solicitud) != estimacion_lectura(3, 2, alto=60_001).huella(solicitud)


def test_contar_sin_nada_nuevo_o_sin_tarifa_no_espera_ningun_si(almacen, gente) -> None:
    conn = almacen.conn
    for est, estado, codigo in (
            (estimacion_lectura(nuevos=0, ya_leidos=3), "nada_que_leer", "ya_leidas"),
            (estimacion_lectura(nuevos=0, ya_leidos=0), "nada_que_leer", "buzon_vacio"),
            (estimacion_lectura(nuevos=1, alto=None), "fallida", "sin_tarifa")):
        lectura.pedir(conn, gente["ana"])
        solicitud = lectura.tomar(conn, hay_pdf=True).solicitud_id
        assert lectura.contar(conn, solicitud, lambda _a: est)[0] == estado
        fila = _fila(conn, solicitud)
        assert (fila["estado"], fila["motivo_codigo"], fila["caduca_en"]) == (estado, codigo,
                                                                              None)


def test_si_le_dicen_que_no_mientras_cuenta_no_escribe_nada_mas(almacen, gente) -> None:
    conn = almacen.conn
    solicitud, _e = lectura.pedir(conn, gente["ana"])
    lectura.tomar(conn, hay_pdf=True)

    def estimar(antes):
        antes("a.pdf")
        lectura.cancelar(conn, gente["ana"], solicitud)
        antes("b.pdf")
        raise AssertionError("no tendria que llegar aqui")

    with pytest.raises(lectura.Parada):
        lectura.contar(conn, solicitud, estimar)
    fila = _fila(conn, solicitud)
    assert (fila["estado"], fila["huella_estimacion"], fila["cancelada_por"]) == (
        "cancelada", None, gente["ana"])


# ============================================================ el si

def test_el_si_vale_solo_para_la_estimacion_que_se_vio(almacen, gente) -> None:
    conn = almacen.conn
    solicitud = lectura_esperando(conn, gente["ana"])
    huella = _fila(conn, solicitud)["huella_estimacion"]
    # Con otra huella: conflicto (409), y nada cambia.
    with pytest.raises(lectura.EstimacionCambiada) as error:
        servicios.ejecutar(conn, "aprobar_lectura", {
            "solicitud_id": solicitud, "huella_estimacion": "f" * 64}, usuario_id=gente["ana"])
    assert servicios.codigo_de_error(error.value) == "conflicto"
    assert _fila(conn, solicitud)["estado"] == "esperando_aprobacion"
    # Un tope por encima de lo que se vio: no.
    with pytest.raises(ValueError, match="tope"):
        servicios.ejecutar(conn, "aprobar_lectura", {
            "solicitud_id": solicitud, "huella_estimacion": huella,
            "tope_usd_micro": 120_001}, usuario_id=gente["ana"])
    # Con la suya: aprobada, por Ana, desde la app, con el tope en el extremo alto.
    diferencia = servicios.ejecutar(conn, "aprobar_lectura", {
        "solicitud_id": solicitud, "huella_estimacion": huella}, usuario_id=gente["ana"],
        peticion_id="si-1")
    fila = _fila(conn, solicitud)
    assert (fila["estado"], fila["aprobada_por"], fila["aprobada_via"], fila["tope_usd_micro"],
            fila["huella_aprobada"]) == ("aprobada", gente["ana"], "app", 120_000, huella)
    assert diferencia.detalle["tope_usd_micro"] == 120_000
    evento = conn.execute("SELECT * FROM evento WHERE id = ?",
                          (diferencia.evento_id,)).fetchone()
    assert (evento["tipo"], evento["usuario_id"], evento["peticion_id"]) == (
        "lectura_aceptada", gente["ana"], "si-1")
    # El mismo clic dos veces no es otro si.
    assert servicios.ejecutar(conn, "aprobar_lectura", {
        "solicitud_id": solicitud, "huella_estimacion": huella}, usuario_id=gente["ana"],
        peticion_id="si-1").repetida
    # Y ya no espera: otro si no vale.
    with pytest.raises(lectura.EstadoNoValido, match="no espera"):
        lectura.aprobar(conn, gente["ana"], solicitud, huella)


def test_el_si_con_un_tope_menor(almacen, gente) -> None:
    conn = almacen.conn
    solicitud = lectura_esperando(conn, gente["ana"])
    huella = _fila(conn, solicitud)["huella_estimacion"]
    lectura.aprobar(conn, gente["ana"], solicitud, huella, 70_000)
    assert _fila(conn, solicitud)["tope_usd_micro"] == 70_000


def test_pasado_el_plazo_no_vale_el_si(almacen, gente, reloj) -> None:
    conn = almacen.conn
    solicitud = lectura_esperando(conn, gente["ana"])
    huella = _fila(conn, solicitud)["huella_estimacion"]
    reloj.avanzar(minutes=15)
    with pytest.raises(lectura.EstadoNoValido, match="plazo"):
        lectura.aprobar(conn, gente["ana"], solicitud, huella)
    assert _fila(conn, solicitud)["aprobada_en"] is None


def test_lo_aprobado_y_lo_terminado_no_cambian(almacen, gente) -> None:
    conn = almacen.conn
    solicitud = lectura_esperando(conn, gente["ana"])
    lectura.aprobar(conn, gente["ana"], solicitud, _fila(conn, solicitud)["huella_estimacion"])
    for asignacion in ("estimacion_json = '[]'", "tope_usd_micro = 1",
                       "coste_max_usd_micro = coste_max_usd_micro + 1",
                       "huella_estimacion = '" + "a" * 64 + "'", "aprobada_por = NULL"):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(f"UPDATE solicitud_lectura SET {asignacion} WHERE id = ?",
                         (solicitud,))
    with pytest.raises(sqlite3.IntegrityError, match="no se borra"):
        conn.execute("DELETE FROM solicitud_lectura")
    lectura.cancelar(conn, gente["ana"], solicitud)
    with pytest.raises(sqlite3.IntegrityError, match="terminada no cambia"):
        conn.execute("UPDATE solicitud_lectura SET motivo = 'otro' WHERE id = ?", (solicitud,))
    # Un usuario de sistema no da el si desde la app.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE solicitud_lectura SET aprobada_por = (SELECT id FROM usuario "
                     "WHERE nombre = 'extractor')")


def test_no_leer_en_cada_estado(almacen, gente) -> None:
    conn = almacen.conn
    ana = gente["ana"]
    # Pedida, comprobando, contando y esperando el si: cancelada al momento.
    pedida, _e = lectura.pedir(conn, ana)
    lectura.cancelar(conn, ana, pedida)
    assert _fila(conn, pedida)["estado"] == "cancelada"
    for hasta in ("comprobando", "esperando_aprobacion", "aprobada"):
        solicitud, _e = lectura.pedir(conn, ana)
        lectura.tomar(conn, hay_pdf=True)
        if hasta != "comprobando":
            lectura.contar(conn, solicitud, lambda _a: estimacion_lectura())
        if hasta == "aprobada":
            lectura.aprobar(conn, ana, solicitud, _fila(conn, solicitud)["huella_estimacion"])
        diferencia = servicios.ejecutar(conn, "cancelar_lectura", {"solicitud_id": solicitud},
                                        usuario_id=ana)
        fila = _fila(conn, solicitud)
        assert (fila["estado"], fila["cancelada_por"], fila["cancelada_via"],
                diferencia.detalle["estado"]) == ("cancelada", ana, "app", "cancelada"), hasta
    # Terminada: no hay nada que cancelar.
    with pytest.raises(lectura.EstadoNoValido, match="ya termino"):
        lectura.cancelar(conn, ana, pedida)


def test_una_lectura_abandonada_no_bloquea_la_siguiente(almacen, gente, reloj) -> None:
    conn = almacen.conn
    ana = gente["ana"]
    # Esperando el si, el lector se cerro con la X: sin sus senales (cada 10 s mientras
    # espera) en 90 s, otra peticion la da por terminada.
    vieja = lectura_esperando(conn, ana)
    reloj.avanzar(seconds=60)
    with pytest.raises(lectura.EstadoNoValido):
        lectura.pedir(conn, ana)
    reloj.avanzar(seconds=30)
    nueva, _e = lectura.pedir(conn, ana)
    assert (_fila(conn, vieja)["estado"], _fila(conn, vieja)["motivo_codigo"]) == (
        "fallida", "abandonada")
    # Comprobando, sin senales 45 minutos: el lector siguiente la cierra y empieza otra.
    lectura.tomar(conn, hay_pdf=True)
    reloj.avanzar(minutes=44)
    assert lectura.tomar(conn, hay_pdf=True).como == lectura.OCUPADA
    reloj.avanzar(minutes=1)
    otra = lectura.tomar(conn, hay_pdf=True)
    assert otra.como == lectura.CREADA and _fila(conn, nueva)["estado"] == "fallida"
    assert lectura.para_la_app(conn)["solicitud"]["id"] == otra.solicitud_id


def test_otro_lector_vuelve_a_contar_la_que_esperaba_y_el_si_de_antes_no_vale(
        almacen, gente, reloj) -> None:
    """La ventana que esperaba el si se cerro: el lector siguiente toma la misma peticion
    (lo que la persona pidio sigue) y la vuelve a contar. Un si a lo que se vio antes ya no
    vale: si la cuenta cambio, es un conflicto; hay que mirarla otra vez."""
    conn = almacen.conn
    ana = gente["ana"]
    solicitud = lectura_esperando(conn, ana, estimacion_lectura(nuevos=2))
    huella_vieja = _fila(conn, solicitud)["huella_estimacion"]
    # Mientras el lector espera y da senales, nadie se la quita.
    linea, _llamadas = _sin_nada_escrito(reloj)
    for _vez in range(30):
        linea(2)
        lectura._senal(conn, solicitud, ("esperando_aprobacion",))
    assert lectura.tomar(conn, hay_pdf=True).como == lectura.OCUPADA
    reloj.avanzar(seconds=90)
    otra = lectura.tomar(conn, hay_pdf=True)
    assert (otra.solicitud_id, otra.como) == (solicitud, lectura.TOMADA)
    fila = _fila(conn, solicitud)
    assert (fila["estado"], fila["huella_estimacion"], fila["pdf_nuevos"],
            fila["caduca_en"]) == ("comprobando", None, None, None)
    with pytest.raises(lectura.EstadoNoValido):
        lectura.aprobar(conn, ana, solicitud, huella_vieja)
    lectura.contar(conn, solicitud, lambda _a: estimacion_lectura(nuevos=3))
    with pytest.raises(lectura.EstimacionCambiada):
        lectura.aprobar(conn, ana, solicitud, huella_vieja)
    lectura.aprobar(conn, ana, solicitud, _fila(conn, solicitud)["huella_estimacion"])
    assert _fila(conn, solicitud)["pdf_nuevos"] == 3


# ============================================================ esperar el si

def _sin_nada_escrito(reloj, al_llamar=None):
    """Una ventana donde nadie escribe: cada espera pasa su tiempo en el reloj."""
    llamadas = []

    def linea(segundos):
        llamadas.append(segundos)
        if al_llamar is not None:
            al_llamar(len(llamadas))
        reloj.avanzar(seconds=segundos)
        return None

    return linea, llamadas


def test_el_si_de_la_app_llega_mientras_el_lector_espera(almacen, gente, reloj) -> None:
    conn = almacen.conn
    solicitud = lectura_esperando(conn, gente["ana"])

    def la_app_dice_que_si(vez):
        if vez == 3:
            lectura.aprobar(conn, gente["ana"], solicitud,
                            _fila(conn, solicitud)["huella_estimacion"])

    linea, llamadas = _sin_nada_escrito(reloj, la_app_dice_que_si)
    assert lectura.esperar(conn, solicitud, linea=linea) == "aprobada"
    # Mira la peticion cada 2 s.
    assert llamadas == [2, 2, 2]


@pytest.mark.parametrize("escrito, estado, via", [("si\n", "aprobada", "ventana"),
                                                  (" Sí\n", "aprobada", "ventana"),
                                                  ("no\n", "cancelada", "ventana"),
                                                  ("\n", "cancelada", "ventana")])
def test_lo_escrito_en_la_ventana_del_lector(almacen, gente, escrito, estado, via) -> None:
    conn = almacen.conn
    solicitud = lectura_esperando(conn, gente["ana"])
    assert lectura.esperar(conn, solicitud, linea=lambda _s: escrito) == estado
    fila = _fila(conn, solicitud)
    assert fila["estado"] == estado
    if estado == "aprobada":
        # Lo da quien tiene la ventana delante: ninguna persona de la app, con el tope en el
        # extremo alto de lo que la ventana acaba de ensenar.
        assert (fila["aprobada_via"], fila["aprobada_por"], fila["tope_usd_micro"]) == (
            via, None, fila["coste_max_usd_micro"])
        evento = conn.execute("SELECT * FROM evento ORDER BY id DESC").fetchone()
        assert (evento["tipo"], evento["usuario_id"]) == ("lectura_aceptada", None)
    else:
        assert (fila["cancelada_via"], fila["cancelada_por"]) == (via, None)


def test_sin_respuesta_en_15_minutos_caduca(almacen, gente, reloj) -> None:
    conn = almacen.conn
    solicitud = lectura_esperando(conn, gente["ana"])
    linea, llamadas = _sin_nada_escrito(reloj)
    assert lectura.esperar(conn, solicitud, linea=linea) == "caducada"
    assert sum(llamadas) == 15 * 60
    fila = _fila(conn, solicitud)
    assert (fila["estado"], fila["aprobada_en"]) == ("caducada", None)
    # Y nadie gasto nada: no hay pasada.
    assert conn.execute("SELECT count(*) FROM pasada_lectura").fetchone()[0] == 0


def test_el_si_de_los_scripts_y_el_del_lector_son_el_mismo() -> None:
    from test_revision_final import _es_si_como_comun_ps1

    for respuesta in ("si", "sí", "Sí", " SI ", "s", "", "no", "sii", "yes", "S\n"):
        assert lectura.es_si(respuesta) is _es_si_como_comun_ps1(respuesta), respuesta


# ============================================================ leer

# Cada PDF de prueba es una factura distinta (numero, fecha e importe), salvo la que se dice
# copia de otra: la misma factura en otro PDF.
_ORDEN_DE_FACTURA: dict[str, int] = {}


def _factura(clave: str):
    i = _ORDEN_DE_FACTURA.setdefault(clave, len(_ORDEN_DE_FACTURA))
    base = 100 + 37 * i
    return _extraccion(f"F-{clave}").model_copy(update={
        "invoice_date": f"2026-{1 + i % 9:02d}-{10 + i % 18:02d}",
        "subtotal_excl_vat_raw": f"{base},00", "vat_amount_raw": f"{base * 21 // 100},{base * 21 % 100:02d}",
        "total_incl_vat_raw": f"{base + base * 21 // 100},{base * 21 % 100:02d}"})


class ClienteQueCuenta:
    """Hace de la API sin red. Cuenta lo que se pagaria y lo que se cuenta (gratis)."""

    def __init__(self, copias=None, al_leer=None) -> None:
        self.messages = self
        self.leidos: list[str] = []
        self.conteos = 0
        self.copias = copias or {}
        self.al_leer = al_leer

    def count_tokens(self, **_peticion):
        self.conteos += 1
        return type("C", (), {"input_tokens": 4321})()

    @staticmethod
    def _contenido(peticion) -> bytes:
        for mensaje in peticion["messages"]:
            for bloque in mensaje["content"]:
                if bloque.get("type") == "document":
                    return base64.b64decode(bloque["source"]["data"])
        raise AssertionError("sin documento")

    def parse(self, **peticion):
        contenido = self._contenido(peticion)
        marca = contenido.split(b"%marca:")[1].split(b"\n")[0].decode()
        self.leidos.append(marca)
        if self.al_leer is not None:
            self.al_leer(marca)
        uso = type("U", (), {"input_tokens": 6000, "output_tokens": 700})()
        return type("R", (), {
            "stop_reason": "end_turn",
            "parsed_output": _factura(self.copias.get(marca, marca)),
            "usage": uso, "_request_id": f"req_{next(_PETICIONES)}"})()


def _pdf(carpeta: Path, nombre: str) -> Path:
    ruta = carpeta / f"{nombre}.pdf"
    ruta.write_bytes(PDF + f"%marca:{nombre}\n".encode())
    return ruta


@pytest.fixture
def buzon(almacen, tmp_path):
    """Un buzon con una factura ya leida (y en la base) y dos nuevas."""
    carpeta = tmp_path / "buzon"
    carpeta.mkdir()
    out = tmp_path / "out"
    vieja = _pdf(carpeta, "vieja")
    extraer_pasada(ClienteQueCuenta(), [vieja], out, almacen=almacen)
    from bms_agent.ingesta import tipar_pendientes

    with transaccion(almacen.conn):
        tipar_pendientes(almacen.conn)
    _pdf(carpeta, "nueva-1")
    _pdf(carpeta, "nueva-2")
    return carpeta, out


def _contada(almacen, quien, carpeta, out, client) -> int:
    conn = almacen.conn
    solicitud, _e = lectura.pedir(conn, quien)
    lectura.tomar(conn, hay_pdf=True)
    estado, _est = lectura.contar(conn, solicitud, lambda antes: lectura.estimar(
        client, sorted(carpeta.glob("*.pdf")), out, almacen=almacen, antes=antes))
    assert estado == "esperando_aprobacion"
    return solicitud


def _leer(almacen, solicitud, carpeta, out, client, impreso=None):
    return lectura.leer(almacen.conn, solicitud, client=client, almacen=almacen,
                        pdfs=sorted(carpeta.glob("*.pdf")), out_dir=out,
                        imprimir=(lambda t, n, d: impreso.append((t, n))) if impreso is not None
                        else None)


def _pasada(conn, solicitud):
    return conn.execute("SELECT * FROM pasada_lectura WHERE solicitud_id = ?",
                        (solicitud,)).fetchone()


def test_la_cuenta_ve_lo_ya_leido_como_la_pasada(almacen, gente, buzon) -> None:
    carpeta, out = buzon
    client = ClienteQueCuenta()
    est = lectura.estimar(client, sorted(carpeta.glob("*.pdf")), out, almacen=almacen)
    assert [(d.nombre, d.clase) for d in est.documentos] == [
        ("nueva-1.pdf", "nuevo"), ("nueva-2.pdf", "nuevo"), ("vieja.pdf", "ya_leido")]
    # Contar no paga: solo cuenta las dos nuevas.
    assert (client.conteos, client.leidos) == (2, [])
    assert est.coste_max_usd_micro == sum(d.alto_usd_micro for d in est.de_clase("nuevo"))
    # Lo leido sigue sin pagarse aunque falte out/: lo dice la base.
    for fichero in out.glob("*.json"):
        fichero.unlink()
    est = lectura.estimar(client, sorted(carpeta.glob("*.pdf")), out, almacen=almacen)
    assert est.ya_leidos == 1 and est.nuevos == 2


def test_leer_paga_solo_lo_aprobado_y_recorre_sus_fases(almacen, gente, buzon) -> None:
    conn = almacen.conn
    carpeta, out = buzon
    client = ClienteQueCuenta()
    solicitud = _contada(almacen, gente["ana"], carpeta, out, client)
    lectura.aprobar(conn, gente["ana"], solicitud, _fila(conn, solicitud)["huella_estimacion"])
    # Un PDF que llega despues de contar no se lee: espera a la proxima.
    _pdf(carpeta, "tardia")
    impreso = []
    leida = _leer(almacen, solicitud, carpeta, out, client, impreso)
    assert client.leidos == ["nueva-1", "nueva-2"]
    assert (leida.estado, leida.fase) == ("hecha", "hecha")
    assert {r["nombre"]: r["estado"] for r in leida.resultado} == {
        "nueva-1.pdf": "nueva", "nueva-2.pdf": "nueva", "vieja.pdf": "ya_leida"}
    for fila in leida.resultado:
        assert fila["documento_id"] is not None and fila["factura_id"] is not None
    assert {r["numero"] for r in leida.resultado if r["estado"] == "nueva"} == {
        "F-nueva-1", "F-nueva-2"}
    pasada = _pasada(conn, solicitud)
    assert [f["fase"] for f in json.loads(pasada["fases_json"])] == [
        "cargando", "leyendo", "comparando", "analizando", "organizando", "hecha"]
    assert (pasada["total"], pasada["leidas"], pasada["ya_leidas"], pasada["fallidas"]) == (
        3, 2, 1, 0)
    # Lo gastado es lo que costo cada respuesta: 6.000 de entrada y 700 de salida, dos veces.
    assert pasada["coste_usd_micro"] == leida.gastado_usd_micro == 2 * 38_000
    assert pasada["documento_actual"] is None and pasada["terminada_en"] is not None
    fila = _fila(conn, solicitud)
    assert (fila["estado"], fila["terminada_en"] is not None) == ("hecha", True)
    assert _eventos(conn, solicitud)[-2:] == ["lectura_empezada", "lectura_terminada"]
    assert ("ok", "nueva-1.pdf") in impreso and ("cache", "vieja.pdf") in impreso
    assert "tardia.pdf" not in {n for _t, n in impreso}


def test_el_progreso_se_ve_documento_a_documento(almacen, gente, buzon) -> None:
    """Lo que la app ve en cada consulta mientras lee: la fase, el documento de ahora y lo que
    hace con el, y las cuentas que solo suben."""
    conn = almacen.conn
    carpeta, out = buzon
    vistas = []

    def mirar(_marca):
        vistas.append(lectura.para_la_app(conn)["pasada_en_curso"])

    client = ClienteQueCuenta(al_leer=mirar)
    solicitud = _contada(almacen, gente["ana"], carpeta, out, client)
    lectura.aprobar(conn, gente["ana"], solicitud, _fila(conn, solicitud)["huella_estimacion"])
    _leer(almacen, solicitud, carpeta, out, client)
    assert [(v["fase"], v["documento_actual"], v["documento_fase"]) for v in vistas] == [
        ("leyendo", "nueva-1.pdf", "leyendo"), ("leyendo", "nueva-2.pdf", "leyendo")]
    assert vistas[1]["recientes"] == ["nueva-1.pdf"]
    assert vistas[1]["leidas"] == 1 and vistas[1]["coste_usd_micro"] == 38_000
    final = lectura.para_la_app(conn)
    assert final["pasada_en_curso"]["fase"] == "hecha"
    assert final["ultima_pasada"]["resultado"] == final["pasada_en_curso"]["resultado"]


def test_el_tope_para_la_lectura(almacen, gente, buzon) -> None:
    conn = almacen.conn
    carpeta, out = buzon
    client = ClienteQueCuenta()
    solicitud = _contada(almacen, gente["ana"], carpeta, out, client)
    est = json.loads(_fila(conn, solicitud)["estimacion_json"])
    alto = next(d["alto_usd_micro"] for d in est["documentos"] if d["clase"] == "nuevo")
    # Un tope que solo da para una: la segunda ya no cabe (38.000 gastados mas su alto).
    lectura.aprobar(conn, gente["ana"], solicitud, _fila(conn, solicitud)["huella_estimacion"],
                    alto)
    leida = _leer(almacen, solicitud, carpeta, out, client)
    assert client.leidos == ["nueva-1"]
    assert (leida.estado, leida.fase) == ("hecha", "tope")
    assert "tope" in leida.motivo
    assert {r["nombre"] for r in leida.resultado} == {"nueva-1.pdf", "vieja.pdf"}
    pasada = _pasada(conn, solicitud)
    assert pasada["coste_usd_micro"] <= alto and pasada["fase"] == "tope"
    assert (pasada["leidas"], pasada["ya_leidas"]) == (1, 1)


class ClienteQueSeAlarga(ClienteQueCuenta):
    """La API cuando una factura sale mucho mas larga que su estimacion: quiere `salida`
    tokens de salida y la API nunca da mas que el max_tokens de la peticion; si no le
    alcanza, la respuesta llega cortada (stop_reason max_tokens, sin factura) y se cobra
    entera. La entrada que cobra es la que cuenta count_tokens. Con `sin_uso`, la llamada
    falla sin decir su uso (como un JSON cortado que rechaza messages.parse)."""

    ENTRADA = 6000

    def __init__(self, salida: int, sin_uso: bool = False) -> None:
        super().__init__()
        self.salida, self.sin_uso = salida, sin_uso
        self.max_tokens: list[int] = []

    def count_tokens(self, **_peticion):
        self.conteos += 1
        return type("C", (), {"input_tokens": self.ENTRADA})()

    def parse(self, **peticion):
        respuesta = super().parse(**peticion)
        tope = peticion["max_tokens"]
        self.max_tokens.append(tope)
        if self.salida <= tope:
            respuesta.usage = type("U", (), {"input_tokens": self.ENTRADA,
                                             "output_tokens": self.salida})()
            return respuesta
        if self.sin_uso:
            raise ValueError("JSON cortado: no valida contra el esquema")
        respuesta.stop_reason, respuesta.parsed_output = "max_tokens", None
        respuesta.usage = type("U", (), {"input_tokens": self.ENTRADA, "output_tokens": tope})()
        return respuesta


@pytest.mark.parametrize("sin_uso", [False, True])
def test_el_tope_no_se_pasa_aunque_una_factura_salga_larga(almacen, gente, buzon,
                                                            sin_uso) -> None:
    """El tope es duro: una factura que quiere toda la salida de la configuracion (16.000
    tokens, muy por encima de su extremo alto) llega como mucho a lo que aun cabe en el tope,
    con su max_tokens; se cobra entera y no se guarda, y la siguiente ya no cabe."""
    from bms_agent import config
    from bms_agent.pricing import estimate_cost

    conn = almacen.conn
    carpeta, out = buzon
    client = ClienteQueSeAlarga(config.max_tokens(), sin_uso=sin_uso)
    solicitud = _contada(almacen, gente["ana"], carpeta, out, client)
    fila = _fila(conn, solicitud)
    tope = fila["coste_max_usd_micro"]
    lectura.aprobar(conn, gente["ana"], solicitud, fila["huella_estimacion"])
    leida = _leer(almacen, solicitud, carpeta, out, client)
    pasada = _pasada(conn, solicitud)
    assert pasada["coste_usd_micro"] == leida.gastado_usd_micro <= tope
    assert client.leidos == ["nueva-1"]
    # La llamada llevo como max_tokens lo que cabia, no los 16.000 de la configuracion: lo
    # que costo (o, sin uso, lo peor que podia costar) es lo que quedaba del tope.
    (max_tokens,) = client.max_tokens
    assert max_tokens < config.max_tokens()
    modelo = json.loads(fila["estimacion_json"])["modelo"]
    peor = lectura.micro(estimate_cost(modelo, ClienteQueSeAlarga.ENTRADA, max_tokens))
    assert pasada["coste_usd_micro"] == peor
    assert peor <= tope < lectura.micro(estimate_cost(modelo, ClienteQueSeAlarga.ENTRADA,
                                                      max_tokens + 1))
    assert (leida.fase, {r["nombre"]: r["estado"] for r in leida.resultado}) == (
        "tope", {"nueva-1.pdf": "fallida", "vieja.pdf": "ya_leida"})


def test_cada_llamada_lleva_como_max_tokens_lo_que_queda_del_tope(almacen, gente,
                                                                    buzon) -> None:
    """Lo que cabe se mira llamada a llamada: la primera, con todo el tope por delante; la
    segunda, con lo que dejo la primera. Ninguna con mas que la configuracion."""
    from bms_agent import config
    from bms_agent.pricing import estimate_cost

    conn = almacen.conn
    carpeta, out = buzon
    client = ClienteQueSeAlarga(700)
    solicitud = _contada(almacen, gente["ana"], carpeta, out, client)
    fila = _fila(conn, solicitud)
    tope = fila["coste_max_usd_micro"]
    modelo = json.loads(fila["estimacion_json"])["modelo"]
    lectura.aprobar(conn, gente["ana"], solicitud, fila["huella_estimacion"])
    leida = _leer(almacen, solicitud, carpeta, out, client)
    assert (leida.estado, leida.fase, client.leidos) == ("hecha", "hecha", ["nueva-1", "nueva-2"])
    una = lectura.micro(estimate_cost(modelo, ClienteQueSeAlarga.ENTRADA, 700))
    assert client.max_tokens == [
        lectura.salida_que_cabe(modelo, ClienteQueSeAlarga.ENTRADA, tope)[0],
        lectura.salida_que_cabe(modelo, ClienteQueSeAlarga.ENTRADA, tope - una)[0]]
    assert 700 < client.max_tokens[1] < client.max_tokens[0] < config.max_tokens()
    assert _pasada(conn, solicitud)["coste_usd_micro"] == 2 * una <= tope
    # Lo que se apunta de cada lectura es el max_tokens con que se pidio.
    usos = [json.loads(u) for (u,) in conn.execute(
        "SELECT e.uso_json FROM extraccion AS e JOIN documento AS d ON d.id = e.documento_id "
        "WHERE d.nombre_original LIKE 'nueva-%' ORDER BY e.id")]
    assert [u["max_tokens"] for u in usos] == client.max_tokens


def test_salida_que_cabe() -> None:
    from bms_agent import config
    from bms_agent.pricing import estimate_cost

    modelo = config.model_id()
    precio = lambda e, s: lectura.micro(estimate_cost(modelo, e, s))  # noqa: E731
    holgado = precio(5000, config.max_tokens()) + 1
    assert lectura.salida_que_cabe(modelo, 5000, holgado) == (
        config.max_tokens(), precio(5000, config.max_tokens()))
    justo = precio(5000, 1234)
    salida, peor = lectura.salida_que_cabe(modelo, 5000, justo)
    assert precio(5000, salida) == peor <= justo < precio(5000, salida + 1)
    assert lectura.salida_que_cabe(modelo, 5000, 0) == (0, precio(5000, 0))


def test_parar_leyendo_para_despues_del_documento_en_curso(almacen, gente, buzon) -> None:
    conn = almacen.conn
    carpeta, out = buzon

    def la_app_dice_que_pare(marca):
        if marca == "nueva-1":
            servicios.ejecutar(conn, "cancelar_lectura", {"solicitud_id": solicitud},
                               usuario_id=gente["ana"])
            fila = _fila(conn, solicitud)
            assert (fila["estado"], fila["cancelada_por"]) == ("leyendo", gente["ana"])
            assert lectura.para_la_app(conn)["solicitud"]["parar_pedido"] is True
            # Pedirlo otra vez no es nada nuevo.
            with pytest.raises(lectura.EstadoNoValido, match="ya se pidio parar"):
                lectura.cancelar(conn, gente["ana"], solicitud)

    client = ClienteQueCuenta(al_leer=la_app_dice_que_pare)
    solicitud = _contada(almacen, gente["ana"], carpeta, out, client)
    lectura.aprobar(conn, gente["ana"], solicitud, _fila(conn, solicitud)["huella_estimacion"])
    leida = _leer(almacen, solicitud, carpeta, out, client)
    assert client.leidos == ["nueva-1"]
    assert (leida.estado, leida.fase) == ("cancelada", "cancelada")
    # Lo leido queda, con su resultado: la app lo ensena como hecho.
    assert {r["nombre"]: r["estado"] for r in leida.resultado} == {
        "nueva-1.pdf": "nueva", "vieja.pdf": "ya_leida"}
    assert _fila(conn, solicitud)["estado"] == "cancelada"


def test_con_un_no_antes_de_empezar_no_se_lee_nada(almacen, gente, buzon) -> None:
    conn = almacen.conn
    carpeta, out = buzon
    client = ClienteQueCuenta()
    solicitud = _contada(almacen, gente["ana"], carpeta, out, client)
    lectura.aprobar(conn, gente["ana"], solicitud, _fila(conn, solicitud)["huella_estimacion"])
    lectura.cancelar(conn, gente["ana"], solicitud)
    leida = _leer(almacen, solicitud, carpeta, out, client)
    assert (leida.estado, client.leidos) == ("cancelada", [])
    assert _pasada(conn, solicitud) is None


def test_con_otro_modelo_que_el_contado_no_se_lee(almacen, gente, buzon, monkeypatch) -> None:
    """El si es para lo que se conto con un modelo y unas versiones: si la configuracion
    cambio entre contar y leer, no se paga nada y la lectura termina fallida."""
    from bms_agent import config

    conn = almacen.conn
    carpeta, out = buzon
    client = ClienteQueCuenta()
    solicitud = _contada(almacen, gente["ana"], carpeta, out, client)
    lectura.aprobar(conn, gente["ana"], solicitud, _fila(conn, solicitud)["huella_estimacion"])
    monkeypatch.setattr(config, "PROMPT_VERSION", "extract/2099-01-01.1")
    leida = _leer(almacen, solicitud, carpeta, out, client)
    assert (leida.estado, client.leidos) == ("fallida", [])
    assert _fila(conn, solicitud)["motivo_codigo"] == "estimacion"
    assert _pasada(conn, solicitud) is None


def test_un_duplicado_y_un_pdf_que_no_se_lee(almacen, gente, buzon, tmp_path) -> None:
    """Un PDF distinto con la misma factura (B2) es un posible duplicado; uno que no es un
    PDF, fallido. Ninguno crea otra copia ni deja la lectura a medias."""
    conn = almacen.conn
    carpeta, out = buzon
    (carpeta / "nueva-2.pdf").unlink()
    _pdf(carpeta, "copia")
    (carpeta / "roto.pdf").write_bytes(b"no soy un pdf")
    client = ClienteQueCuenta(copias={"copia": "vieja"})
    solicitud = _contada(almacen, gente["ana"], carpeta, out, client)
    lectura.aprobar(conn, gente["ana"], solicitud, _fila(conn, solicitud)["huella_estimacion"])
    leida = _leer(almacen, solicitud, carpeta, out, client)
    estados = {r["nombre"]: r["estado"] for r in leida.resultado}
    assert estados == {"copia.pdf": "posible_duplicado", "nueva-1.pdf": "nueva",
                       "vieja.pdf": "ya_leida"}
    # El que no es un PDF no se conto ni se aprobo: no se lee ni se paga.
    assert "roto" not in client.leidos and leida.estado == "hecha"


def test_un_fallo_leyendo_cierra_la_lectura_y_lo_leido_queda(almacen, gente, buzon,
                                                            monkeypatch) -> None:
    from bms_agent import hallazgos

    conn = almacen.conn
    carpeta, out = buzon
    client = ClienteQueCuenta()
    solicitud = _contada(almacen, gente["ana"], carpeta, out, client)
    lectura.aprobar(conn, gente["ana"], solicitud, _fila(conn, solicitud)["huella_estimacion"])

    def falla(*_a, **_k):
        raise RuntimeError("se rompio el motor")

    monkeypatch.setattr(hallazgos, "recalcular", falla)
    with pytest.raises(RuntimeError, match="se rompio"):
        _leer(almacen, solicitud, carpeta, out, client)
    fila = _fila(conn, solicitud)
    assert (fila["estado"], fila["motivo_codigo"]) == ("fallida", "lectura")
    assert "se rompio el motor" in fila["motivo"]
    pasada = _pasada(conn, solicitud)
    assert pasada["fase"] == "fallida" and pasada["terminada_en"] is not None
    # Lo pagado no se pierde: las dos lecturas estan en la base.
    assert conn.execute("SELECT count(*) FROM extraccion").fetchone()[0] == 3


def test_ctrl_c_leyendo_deja_la_lectura_interrumpida(almacen, gente, buzon) -> None:
    conn = almacen.conn
    carpeta, out = buzon

    def ctrl_c(_marca):
        raise KeyboardInterrupt

    client = ClienteQueCuenta(al_leer=ctrl_c)
    solicitud = _contada(almacen, gente["ana"], carpeta, out, client)
    lectura.aprobar(conn, gente["ana"], solicitud, _fila(conn, solicitud)["huella_estimacion"])
    with pytest.raises(KeyboardInterrupt):
        _leer(almacen, solicitud, carpeta, out, client)
    assert _fila(conn, solicitud)["motivo_codigo"] == "interrumpida"
    assert _pasada(conn, solicitud)["fase"] == "fallida"


# ============================================================ los fallos de la API (paso 18)

_PETICION_API = "https://api.anthropic.com/v1/messages"


def _error_api(estado: int, tipo: str | None, mensaje: str = "", codigo: str | None = None,
               *, cuerpo: bool = True):
    """Un error del SDK hecho a mano, con la forma que tiene el que levanta el SDK: la clase de
    su codigo, la respuesta y el cuerpo de la API ({"type": "error", "error": {...}})."""
    import anthropic
    import httpx2

    clases = {400: "BadRequestError", 401: "AuthenticationError", 403: "PermissionDeniedError",
              404: "NotFoundError", 413: "RequestTooLargeError", 429: "RateLimitError",
              500: "InternalServerError", 529: "OverloadedError"}
    clase = getattr(anthropic, clases.get(estado, "APIStatusError"))
    error: dict = {"type": tipo, "message": mensaje}
    if codigo is not None:
        error["details"] = {"error_code": codigo}
    body = {"type": "error", "error": error, "request_id": "req_falso"} if cuerpo else None
    respuesta = httpx2.Response(estado, request=httpx2.Request("POST", _PETICION_API))
    return clase(f"Error code: {estado} - {body}", response=respuesta, body=body)


def _sin_conexion():
    import anthropic
    import httpx2

    return anthropic.APIConnectionError(request=httpx2.Request("POST", _PETICION_API))


def _sin_respuesta():
    import anthropic
    import httpx2

    return anthropic.APITimeoutError(request=httpx2.Request("POST", _PETICION_API))


# Los fallos de la API que no son del documento (§5.3 del diseno del paso 18), con el motivo
# con que paran la pasada. Mensajes inventados, con la forma de los de la API.
FALLOS_API = {
    "401": (lambda: _error_api(401, "authentication_error", "invalid x-api-key"),
            "clave_rechazada"),
    "403": (lambda: _error_api(403, "permission_error",
                               "Your API key does not have permission to use this resource."),
            "clave_rechazada"),
    "402": (lambda: _error_api(402, "billing_error", "This organization has no funds left."),
            "saldo"),
    "400-saldo": (lambda: _error_api(400, "invalid_request_error",
                                     "Your credit balance is too low to access the API."),
                  "saldo"),
    "429-gasto": (lambda: _error_api(429, "rate_limit_error",
                                     "You have reached your specified API usage limits.",
                                     "enforced_spend_limit_reached"), "saldo"),
    "429": (lambda: _error_api(429, "rate_limit_error",
                               "Number of requests has exceeded your rate limit."),
            "api_no_disponible"),
    "500": (lambda: _error_api(500, "api_error", "Internal server error"), "api_no_disponible"),
    "529": (lambda: _error_api(529, "overloaded_error", "Overloaded"), "api_no_disponible"),
    "sin-conexion": (_sin_conexion, "api_no_disponible"),
    "sin-respuesta": (_sin_respuesta, "api_no_disponible"),
}
# Los que son del documento: la pasada sigue con el siguiente.
DEL_DOCUMENTO = {
    "413": lambda: _error_api(413, "request_too_large",
                              "Request exceeds the maximum allowed number of bytes."),
    "400": lambda: _error_api(400, "invalid_request_error", "The PDF specified was not valid."),
}


# La marca de una peticion sin PDF: la contraprueba de estimar (la misma peticion sin el PDF).
SIN_PDF = "(sin pdf)"


class ClienteQueFalla(ClienteQueCuenta):
    """La API con fallos, PDF a PDF (por su marca): al contar (`al_contar`) o al leer
    (`al_leer_falla`) lanza el error que da su fabrica, en vez de contestar; los de `rechaza`
    el modelo los rechaza (stop_reason refusal, que se cobra). Cuenta cada intento, tambien
    los que fallan: tras una parada no se llama mas. Una peticion sin PDF lleva la marca
    SIN_PDF: `al_contar={SIN_PDF: ...}` es una API que tampoco la acepta (la configuracion)."""

    def __init__(self, al_contar=None, al_leer_falla=None, rechaza=(), **opciones) -> None:
        super().__init__(**opciones)
        self.al_contar = al_contar or {}
        self.al_leer_falla = al_leer_falla or {}
        self.rechaza = set(rechaza)
        self.contados: list[str] = []
        self.intentos: list[str] = []

    def _marca(self, peticion) -> str:
        if not any(bloque.get("type") == "document" for mensaje in peticion["messages"]
                   for bloque in mensaje["content"]):
            return SIN_PDF
        return self._contenido(peticion).split(b"%marca:")[1].split(b"\n")[0].decode()

    def count_tokens(self, **peticion):
        marca = self._marca(peticion)
        self.conteos += 1
        self.contados.append(marca)
        if marca in self.al_contar:
            raise self.al_contar[marca]()
        return type("C", (), {"input_tokens": 4321})()

    def parse(self, **peticion):
        marca = self._marca(peticion)
        self.intentos.append(marca)
        if marca in self.al_leer_falla:
            raise self.al_leer_falla[marca]()
        if marca in self.rechaza:
            uso = type("U", (), {"input_tokens": 6000, "output_tokens": 10})()
            return type("R", (), {"stop_reason": "refusal", "parsed_output": None,
                                  "stop_details": type("D", (), {"category": "cyber"})(),
                                  "usage": uso, "_request_id": "req_rechazo"})()
        return super().parse(**peticion)


def test_cada_motivo_tiene_su_texto_en_la_app() -> None:
    """La app dice el por que de cada final malo en cada idioma a partir de su codigo
    (process-texts.ts, reasonOf; el tipo Messages obliga a los tres idiomas): un codigo de
    MOTIVOS sin su texto saldria como "el lector no ha podido terminar"."""
    from conftest import RAIZ

    texto = (RAIZ / "frontend" / "src" / "aurora" / "processing" / "process-texts.ts").read_text(
        encoding="utf-8")
    razones = texto[texto.index("export function reasonOf"):]
    razones = razones[:razones.index("\n}\n")]
    for codigo in lectura.MOTIVOS:
        assert f"{codigo}: r.{codigo}," in razones, codigo


def test_max_bytes_api_cabe_en_una_peticion() -> None:
    """20 MiB, y en base64 (4 por cada 3) por debajo de los 32 MB por peticion de la API, con
    sitio para el prompt."""
    from bms_agent.documents import MAX_BYTES_API

    assert MAX_BYTES_API == 20 * 1024 * 1024
    assert 4 * -(-MAX_BYTES_API // 3) < 32_000_000 - 1_000_000


@pytest.mark.parametrize("nombre", sorted(FALLOS_API))
def test_clasificar_error_lo_que_no_es_del_documento(nombre) -> None:
    fabrica, motivo = FALLOS_API[nombre]
    assert lectura.clasificar_error(fabrica()) == motivo
    assert motivo in lectura.MOTIVOS and motivo in lectura.FALLOS_DE_LA_API


def test_clasificar_error_lo_que_es_del_documento() -> None:
    from bms_agent.extract import Cortado, Rechazado

    for fabrica in DEL_DOCUMENTO.values():
        assert lectura.clasificar_error(fabrica()) == lectura.DOCUMENTO
    # Lo que no es un error de la API es cosa de ese documento: el modelo lo rechazo, se corto,
    # la salida no valida.
    for error in (Rechazado("rechazado"), Cortado("cortado"), ValueError("no valida")):
        assert lectura.clasificar_error(error) == lectura.DOCUMENTO
    # Un 400 que no habla de saldo es del documento aunque diga "credit" en otra cosa.
    assert lectura.clasificar_error(_error_api(400, "invalid_request_error",
                                               "credit note page is encrypted")) == "documento"


def test_clasificar_error_sin_depender_del_sdk() -> None:
    """Lee el codigo, el cuerpo y el nombre de la clase con getattr: vale con el SDK fijado,
    con otro y con un error que no es del SDK pero tiene su forma."""

    class ErrorSuelto(Exception):
        def __init__(self, status_code, body=None, message=""):
            super().__init__(message)
            self.status_code, self.body, self.message = status_code, body, message

    class APIConnectionError(Exception):
        pass

    class APITimeoutError(APIConnectionError):
        pass

    assert lectura.clasificar_error(ErrorSuelto(401)) == "clave_rechazada"
    assert lectura.clasificar_error(ErrorSuelto(402, "texto que no es JSON")) == "saldo"
    assert lectura.clasificar_error(ErrorSuelto(
        429, {"error": {"type": "rate_limit_error",
                        "details": {"error_code": "enforced_spend_limit_reached"}}})) == "saldo"
    assert lectura.clasificar_error(ErrorSuelto(429, None)) == "api_no_disponible"
    assert lectura.clasificar_error(ErrorSuelto(
        400, None, "Your credit balance is too low")) == "saldo"
    assert lectura.clasificar_error(ErrorSuelto(413, {"error": "raro"})) == "documento"
    # Lo que la tabla no nombra no es del documento: para sin apartar nada.
    for estado in (404, 408, 409, 422, 503):
        assert lectura.clasificar_error(ErrorSuelto(estado)) == "api_no_disponible", estado
    assert lectura.clasificar_error(APITimeoutError()) == "api_no_disponible"
    # Un codigo que no es un numero no es un error de la API.
    assert lectura.clasificar_error(ErrorSuelto(True)) == "documento"
    assert lectura.clasificar_error(ErrorSuelto("401")) == "documento"
    # Sin cuerpo, como un 429 que no trae nada.
    assert lectura.clasificar_error(_error_api(429, None, cuerpo=False)) == "api_no_disponible"
    assert lectura.clasificar_error(_error_api(402, None, cuerpo=False)) == "saldo"
    # La clave, por su codigo aunque no traiga cuerpo.
    for estado in (401, 403):
        assert lectura.clasificar_error(ErrorSuelto(estado)) == "clave_rechazada", estado
        assert lectura.clasificar_error(_error_api(estado, None, cuerpo=False)) == (
            "clave_rechazada"), estado


def test_sobre_el_error_es_una_linea_corta_sin_la_peticion() -> None:
    texto = lectura.sobre_el_error(_error_api(400, "invalid_request_error",
                                              "linea uno\nlinea " + "x" * 400))
    assert texto.startswith("BadRequestError 400 invalid_request_error: linea uno linea x")
    assert len(texto) == 300 and "\n" not in texto and "req_falso" not in texto
    assert lectura.sobre_el_error(_sin_conexion()) == "APIConnectionError: Connection error."


def test_un_pdf_de_mas_de_max_bytes_api_no_se_manda(almacen, gente, buzon, monkeypatch) -> None:
    """Ni al contar ni al leer: queda omitido, con por que, y los demas se cuentan y se leen."""
    from bms_agent import documents

    conn = almacen.conn
    carpeta, out = buzon
    # El tope de verdad, con un PDF de verdad un byte mas grande.
    grande = carpeta / "grande.pdf"
    grande.write_bytes(PDF + b"%marca:grande\n" + b" " * (documents.MAX_BYTES_API - len(PDF) - 13))
    assert grande.stat().st_size == documents.MAX_BYTES_API + 1
    client = ClienteQueFalla()
    est = lectura.estimar(client, sorted(carpeta.glob("*.pdf")), out, almacen=almacen)
    assert [(d.nombre, d.clase, d.rechazado_api) for d in est.documentos] == [
        ("grande.pdf", "omitido", True), ("nueva-1.pdf", "nuevo", False),
        ("nueva-2.pdf", "nuevo", False), ("vieja.pdf", "ya_leido", False)]
    assert "demasiado grande para la API" in est.documentos[0].detalle
    assert client.contados == ["nueva-1", "nueva-2"]
    grande.unlink()
    # Justo en el tope se manda; uno mas, no.
    monkeypatch.setattr(documents, "MAX_BYTES_API", len(PDF) + len(b"%marca:justo\n"))
    _pdf(carpeta, "justo")
    (carpeta / "pasado.pdf").write_bytes(PDF + b"%marca:pasado\n" + b" ")
    client = ClienteQueFalla()
    solicitud = _contada(almacen, gente["ana"], carpeta, out, client)
    assert sorted(client.contados) == ["justo"]
    fila = _fila(conn, solicitud)
    assert (fila["pdf_nuevos"], fila["pdf_ya_leidos"]) == (1, 1)
    documentos = {d["nombre"]: d for d in json.loads(fila["estimacion_json"])["documentos"]}
    assert documentos["pasado.pdf"]["rechazado_api"] is True
    assert "rechazado_api" not in documentos["justo.pdf"]
    lectura.aprobar(conn, gente["ana"], solicitud, fila["huella_estimacion"])
    impreso = []
    leida = _leer(almacen, solicitud, carpeta, out, client, impreso)
    assert client.leidos == ["justo"] and leida.estado == "hecha"
    # El que no se manda no se elige al leer: ni en el progreso ni en el resultado.
    assert "pasado.pdf" not in {n for _t, n in impreso}
    assert {r["nombre"] for r in leida.resultado} == {"justo.pdf", "vieja.pdf"}


@pytest.mark.parametrize("nombre", sorted(DEL_DOCUMENTO))
def test_un_pdf_que_la_api_no_acepta_al_contar_no_tumba_la_cuenta(almacen, gente, buzon,
                                                                   nombre) -> None:
    """Un 413 o un 400 de un PDF al contarlo lo deja omitido, con lo que dijo la API; los
    demas se cuentan, se aprueban y se leen. Antes cerraba toda la peticion con "contar"."""
    conn = almacen.conn
    carpeta, out = buzon
    # Otra copia del mismo PDF tampoco se manda.
    (carpeta / "otra-copia.pdf").write_bytes((carpeta / "nueva-1.pdf").read_bytes())
    client = ClienteQueFalla(al_contar={"nueva-1": DEL_DOCUMENTO[nombre]})
    solicitud = _contada(almacen, gente["ana"], carpeta, out, client)
    # Antes de darlo por malo, la contraprueba: la misma peticion sin el PDF, que la API acepta.
    assert client.contados == ["nueva-1", SIN_PDF, "nueva-2"]
    fila = _fila(conn, solicitud)
    assert (fila["estado"], fila["pdf_nuevos"], fila["pdf_ya_leidos"]) == (
        "esperando_aprobacion", 1, 1)
    documentos = {d["nombre"]: d for d in json.loads(fila["estimacion_json"])["documentos"]}
    assert (documentos["nueva-1.pdf"]["clase"], documentos["nueva-1.pdf"]["rechazado_api"]) == (
        "omitido", True)
    assert documentos["nueva-1.pdf"]["detalle"].startswith("la API no lo acepta: ")
    assert nombre in documentos["nueva-1.pdf"]["detalle"]
    assert documentos["otra-copia.pdf"] == {**documentos["nueva-1.pdf"],
                                            "nombre": "otra-copia.pdf"}
    # Los demas, como siempre: sin claves nuevas (su huella no cambia).
    assert set(documentos["nueva-2.pdf"]) == {"nombre", "sha256", "clase", "entrada",
                                              "bajo_usd_micro", "alto_usd_micro"}
    lectura.aprobar(conn, gente["ana"], solicitud, fila["huella_estimacion"])
    impreso = []
    leida = _leer(almacen, solicitud, carpeta, out, client, impreso)
    assert (leida.estado, client.intentos) == ("hecha", ["nueva-2"])
    assert {r["nombre"]: r["estado"] for r in leida.resultado} == {
        "nueva-2.pdf": "nueva", "vieja.pdf": "ya_leida"}
    assert not {"nueva-1.pdf", "otra-copia.pdf"} & {n for _t, n in impreso}


def test_dos_pdf_seguidos_con_el_mismo_400_al_contar_quedan_omitidos(almacen, gente,
                                                                     buzon) -> None:
    """Dos PDF malos seguidos dan el mismo 400 (el mismo mensaje para cualquier PDF cifrado o
    con demasiadas paginas): con la contraprueba bien, son de sus PDF, no de la API. Quedan
    omitidos los dos y los demas se cuentan: un freno de "dos iguales seguidos" al contar
    bloquearia la cuenta entera cada vez, como antes de D12. La contraprueba va una vez."""
    conn = almacen.conn
    carpeta, out = buzon
    _pdf(carpeta, "nueva-3")
    igual = DEL_DOCUMENTO["400"]
    client = ClienteQueFalla(al_contar={"nueva-1": igual, "nueva-2": igual})
    solicitud = _contada(almacen, gente["ana"], carpeta, out, client)
    assert client.contados == ["nueva-1", SIN_PDF, "nueva-2", "nueva-3"]
    fila = _fila(conn, solicitud)
    assert (fila["estado"], fila["pdf_nuevos"]) == ("esperando_aprobacion", 1)
    documentos = {d["nombre"]: d for d in json.loads(fila["estimacion_json"])["documentos"]}
    assert [n for n, d in documentos.items() if d.get("rechazado_api")] == [
        "nueva-1.pdf", "nueva-2.pdf"]


def test_sin_contraprueba_si_la_api_ya_conto_otro_pdf(almacen, buzon) -> None:
    """Si la API ya conto otro PDF de esta cuenta, la configuracion vale (con un PDF dentro,
    mas que la contraprueba): un 400 despues es de su PDF, sin mas llamadas."""
    carpeta, out = buzon

    def no_se_llama():
        raise AssertionError("la contraprueba no hacia falta")

    client = ClienteQueFalla(al_contar={"nueva-2": DEL_DOCUMENTO["400"], SIN_PDF: no_se_llama})
    est = lectura.estimar(client, sorted(carpeta.glob("*.pdf")), out, almacen=almacen)
    assert client.contados == ["nueva-1", "nueva-2"]
    assert [(d.nombre, d.clase, d.rechazado_api) for d in est.documentos] == [
        ("nueva-1.pdf", "nuevo", False), ("nueva-2.pdf", "omitido", True),
        ("vieja.pdf", "ya_leido", False)]


def test_un_400_de_la_configuracion_al_contar_no_aparta_ningun_pdf(almacen, gente,
                                                                   buzon) -> None:
    """Un 400 que no es de ningun PDF (el modelo no admite el esfuerzo, el esquema...) llega
    igual con todos, y tambien sin el PDF: la contraprueba lo ve y no se aparta ninguno. La
    cuenta para (api_no_disponible, con lo que dijo la API) y nada queda omitido ni "ya leido";
    antes de la contraprueba, todos quedaban omitidos y la peticion decia que no habia nada
    nuevo."""
    conn = almacen.conn
    carpeta, out = buzon
    configuracion = lambda: _error_api(  # noqa: E731
        400, "invalid_request_error", "output_config.effort: unknown value")
    client = ClienteQueFalla(al_contar={"nueva-1": configuracion, "nueva-2": configuracion,
                                        SIN_PDF: configuracion})
    with pytest.raises(lectura.ParadaApi) as parada:
        lectura.estimar(client, sorted(carpeta.glob("*.pdf")), out, almacen=almacen)
    assert parada.value.motivo == "api_no_disponible"
    assert parada.value.detalle == (
        "nueva-1.pdf: BadRequestError 400 invalid_request_error: output_config.effort: "
        "unknown value; sin el PDF, lo mismo")
    assert client.contados == ["nueva-1", SIN_PDF]


@pytest.mark.parametrize("nombre", sorted(FALLOS_API))
def test_la_contraprueba_que_falla_por_la_api_para_la_cuenta(almacen, buzon, nombre) -> None:
    """Si la contraprueba falla por algo que no es de ningun PDF (la clave, el saldo, no
    disponible), la cuenta para con ese motivo, como si hubiera fallado el PDF."""
    carpeta, out = buzon
    fabrica, motivo = FALLOS_API[nombre]
    client = ClienteQueFalla(al_contar={"nueva-1": DEL_DOCUMENTO["413"], SIN_PDF: fabrica})
    with pytest.raises(lectura.ParadaApi) as parada:
        lectura.estimar(client, sorted(carpeta.glob("*.pdf")), out, almacen=almacen)
    assert parada.value.motivo == motivo
    # (La clase del 413 cambia con el SDK: RequestTooLargeError o ContentTooLargeError.)
    assert re.fullmatch(r"nueva-1\.pdf: \w+ 413 request_too_large: .*; sin el PDF: .*",
                        parada.value.detalle)
    assert client.contados == ["nueva-1", SIN_PDF]


def test_la_contraprueba_con_otro_400_o_con_un_fallo_nuestro(almacen, buzon) -> None:
    """Otro 400 sin el PDF tampoco es del documento (api_no_disponible); un fallo nuestro en
    la contraprueba sigue hacia arriba, como al contar."""
    carpeta, out = buzon
    otro = lambda: _error_api(400, "invalid_request_error", "otro mensaje")  # noqa: E731
    client = ClienteQueFalla(al_contar={"nueva-1": DEL_DOCUMENTO["400"], SIN_PDF: otro})
    with pytest.raises(lectura.ParadaApi) as parada:
        lectura.estimar(client, sorted(carpeta.glob("*.pdf")), out, almacen=almacen)
    assert parada.value.motivo == "api_no_disponible"
    assert parada.value.detalle.endswith(
        "; sin el PDF: BadRequestError 400 invalid_request_error: otro mensaje")
    client = ClienteQueFalla(al_contar={"nueva-1": DEL_DOCUMENTO["400"],
                                        SIN_PDF: lambda: TypeError("un fallo nuestro")})
    with pytest.raises(TypeError, match="un fallo nuestro"):
        lectura.estimar(client, sorted(carpeta.glob("*.pdf")), out, almacen=almacen)


def test_si_la_api_no_acepta_ninguno_de_los_nuevos_no_dice_que_no_hay_nada(
        almacen, gente, buzon, monkeypatch) -> None:
    """Hay PDF nuevos, pero ninguno se puede mandar (un 413, un 400, o demasiado grande): la
    peticion no dice "no hay ningun PDF" ni "ya estan leidas", que no seria verdad. Termina
    fallida con "contar" (no se ha podido contar, como antes de D12), y el motivo dice cuales
    y por que."""
    from bms_agent import documents

    conn = almacen.conn
    carpeta, out = buzon
    client = ClienteQueFalla(al_contar={"nueva-1": DEL_DOCUMENTO["413"],
                                        "nueva-2": DEL_DOCUMENTO["400"]})
    solicitud, _e = lectura.pedir(conn, gente["ana"])
    lectura.tomar(conn, hay_pdf=True)
    estado, est = lectura.contar(conn, solicitud, lambda antes: lectura.estimar(
        client, sorted(carpeta.glob("*.pdf")), out, almacen=almacen, antes=antes))
    assert (estado, est.nuevos, est.ya_leidos) == ("fallida", 0, 1)
    fila = _fila(conn, solicitud)
    assert (fila["estado"], fila["motivo_codigo"], fila["estimacion_json"]) == (
        "fallida", "contar", None)
    assert fila["motivo"].startswith(
        lectura.MOTIVOS["contar"] + ": la API no acepta ninguno de los PDF nuevos: "
        "nueva-1.pdf (la API no lo acepta: ")
    assert " 413 request_too_large: " in fila["motivo"]
    assert "; nueva-2.pdf (la API no lo acepta: BadRequestError 400 " in fila["motivo"]
    evento = conn.execute("SELECT * FROM evento WHERE tabla = 'solicitud_lectura' AND "
                          "fila_id = ? ORDER BY id DESC", (solicitud,)).fetchone()
    datos = json.loads(evento["datos_json"])
    assert (evento["tipo"], datos["motivo_codigo"], datos["rechazados_api"]) == (
        "lectura_fallida", "contar", 2)
    # Solo uno, y demasiado grande: no se llama a la API ni para la contraprueba.
    for nombre in ("nueva-1", "nueva-2", "vieja"):
        (carpeta / f"{nombre}.pdf").unlink()
    _pdf(carpeta, "nueva-3")
    monkeypatch.setattr(documents, "MAX_BYTES_API", 10)
    client = ClienteQueFalla()
    solicitud, _e = lectura.pedir(conn, gente["ana"])
    lectura.tomar(conn, hay_pdf=True)
    estado, _est = lectura.contar(conn, solicitud, lambda antes: lectura.estimar(
        client, sorted(carpeta.glob("*.pdf")), out, almacen=almacen, antes=antes))
    fila = _fila(conn, solicitud)
    assert (estado, fila["motivo_codigo"], client.contados) == ("fallida", "contar", [])
    assert "nueva-3.pdf (demasiado grande para la API" in fila["motivo"]


@pytest.mark.parametrize("nombre", sorted(FALLOS_API))
def test_un_fallo_de_la_api_al_contar_para_la_cuenta_con_su_motivo(almacen, gente, buzon,
                                                                   nombre) -> None:
    """La clave, el saldo o la API no disponible no son de un PDF: no se cuenta ninguno mas
    (ParadaApi con su motivo, que el lector pone a la peticion en vez de "contar")."""
    carpeta, out = buzon
    fabrica, motivo = FALLOS_API[nombre]
    client = ClienteQueFalla(al_contar={"nueva-1": fabrica})
    with pytest.raises(lectura.ParadaApi) as parada:
        lectura.estimar(client, sorted(carpeta.glob("*.pdf")), out, almacen=almacen)
    assert parada.value.motivo == motivo
    assert parada.value.detalle.startswith("nueva-1.pdf: ")
    assert client.contados == ["nueva-1"]


def test_un_fallo_nuestro_al_contar_no_se_toma_por_un_pdf_malo(almacen, buzon) -> None:
    """Lo que no es un error de la API (un fallo del programa) sigue hacia arriba, como antes:
    el lector cierra la peticion con "contar" y no aparta ningun PDF."""
    carpeta, out = buzon
    client = ClienteQueFalla(al_contar={"nueva-1": lambda: TypeError("un fallo nuestro")})
    with pytest.raises(TypeError, match="un fallo nuestro"):
        lectura.estimar(client, sorted(carpeta.glob("*.pdf")), out, almacen=almacen)


@pytest.mark.parametrize("origen", ["app", "lector"])
@pytest.mark.parametrize("nombre", sorted(FALLOS_API))
def test_un_fallo_de_la_api_al_leer_para_la_pasada_sin_apartar_nada(almacen, gente, buzon,
                                                                    nombre, origen) -> None:
    """El primer documento falla por la API (sin saldo, la clave, sobrecarga...): la pasada para
    ahi, ese queda sin leer (no fallido: no es culpa suya), el siguiente no se paga, ninguno
    cuenta como fallido y la peticion termina fallida con su motivo. Igual en una lectura
    pedida por una persona que en una abierta en el lector."""
    conn = almacen.conn
    carpeta, out = buzon
    fabrica, motivo = FALLOS_API[nombre]
    client = ClienteQueFalla(al_leer_falla={"nueva-1": fabrica})
    if origen == "app":
        solicitud = _contada(almacen, gente["ana"], carpeta, out, client)
        lectura.aprobar(conn, gente["ana"], solicitud,
                        _fila(conn, solicitud)["huella_estimacion"])
    else:
        solicitud = lectura.tomar(conn, hay_pdf=True).solicitud_id
        lectura.contar(conn, solicitud, lambda antes: lectura.estimar(
            client, sorted(carpeta.glob("*.pdf")), out, almacen=almacen, antes=antes))
        assert lectura.esperar(conn, solicitud, linea=lambda _s: "si\n") == "aprobada"
    impreso = []
    leida = _leer(almacen, solicitud, carpeta, out, client, impreso)
    assert client.intentos == ["nueva-1"]
    assert (leida.estado, leida.fase, leida.fallidas) == ("fallida", "fallida", 0)
    assert leida.motivo.startswith(lectura.MOTIVOS[motivo]) and "nueva-1.pdf" in leida.motivo
    # Lo ya leido sigue saliendo; los dos sin leer, no (se cuentan la proxima vez).
    assert {r["nombre"]: r["estado"] for r in leida.resultado} == {"vieja.pdf": "ya_leida"}
    assert ("sin_leer", "nueva-1.pdf") in impreso and ("sin_leer", "nueva-2.pdf") in impreso
    assert ("error", "nueva-1.pdf") not in impreso
    fila = _fila(conn, solicitud)
    assert (fila["estado"], fila["motivo_codigo"], fila["origen"]) == (
        "fallida", motivo, origen)
    assert fila["motivo"] == leida.motivo
    pasada = _pasada(conn, solicitud)
    assert (pasada["fase"], pasada["fallidas"], pasada["leidas"], pasada["ya_leidas"]) == (
        "fallida", 0, 0, 1)
    assert [r["nombre"] for r in json.loads(pasada["resultado_json"])] == ["vieja.pdf"]
    # Sin uso no se sabe si se cobro: cuenta lo peor que podia costar, dentro del tope.
    assert 0 < pasada["coste_usd_micro"] <= fila["tope_usd_micro"]
    evento = conn.execute("SELECT * FROM evento WHERE tabla = 'solicitud_lectura' AND "
                          "fila_id = ? ORDER BY id DESC", (solicitud,)).fetchone()
    assert evento["tipo"] == "lectura_terminada"
    datos = json.loads(evento["datos_json"])
    assert (datos["a"], datos["fase"], datos["motivo_codigo"], datos["fallidas"],
            datos["sin_leer"]) == ("fallida", "fallida", motivo, 0, 2)
    # La app lo ve: la peticion fallida con su codigo, y la pasada con lo que se leyo.
    vista = lectura.para_la_app(conn)
    assert (vista["solicitud"]["estado"], vista["solicitud"]["motivo_codigo"]) == (
        "fallida", motivo)
    assert vista["ultima_pasada"]["fase"] == "fallida"
    assert campos.verificar_controladas(conn) == []


def test_un_fallo_de_la_api_en_medio_deja_lo_leido(almacen, gente, buzon) -> None:
    """Lo que se leyo antes del fallo queda; lo de despues, sin leer."""
    conn = almacen.conn
    carpeta, out = buzon
    _pdf(carpeta, "nueva-3")
    client = ClienteQueFalla(al_leer_falla={"nueva-2": FALLOS_API["402"][0]})
    solicitud = _contada(almacen, gente["ana"], carpeta, out, client)
    lectura.aprobar(conn, gente["ana"], solicitud, _fila(conn, solicitud)["huella_estimacion"])
    leida = _leer(almacen, solicitud, carpeta, out, client)
    assert client.intentos == ["nueva-1", "nueva-2"]
    assert (leida.estado, _fila(conn, solicitud)["motivo_codigo"]) == ("fallida", "saldo")
    assert {r["nombre"]: r["estado"] for r in leida.resultado} == {
        "nueva-1.pdf": "nueva", "vieja.pdf": "ya_leida"}
    assert (_pasada(conn, solicitud)["leidas"], _pasada(conn, solicitud)["fallidas"]) == (1, 0)


def _salida_corta(monkeypatch) -> None:
    """Un fallo sin uso cuenta lo peor que podia costar (toda su salida): con la salida de la
    configuracion, el primero se lleva casi todo el tope y el segundo ya no cabe. Con una
    salida corta caben todos, y se ve que hace la pasada con el segundo."""
    monkeypatch.setenv("BMS_EXTRACT_MAX_TOKENS", "1000")


def test_dos_400_iguales_seguidos_paran_sin_culpar_a_ninguno(almacen, gente, buzon,
                                                            monkeypatch) -> None:
    """El mismo 400 (codigo, tipo y mensaje) en dos documentos seguidos es algo de la API que
    no se ha sabido clasificar: para la pasada como api_no_disponible, y ninguno de los dos
    queda como fallido; el tercero no se paga."""
    _salida_corta(monkeypatch)
    conn = almacen.conn
    carpeta, out = buzon
    _pdf(carpeta, "nueva-3")
    igual = DEL_DOCUMENTO["400"]
    client = ClienteQueFalla(al_leer_falla={"nueva-1": igual, "nueva-2": igual})
    solicitud = _contada(almacen, gente["ana"], carpeta, out, client)
    lectura.aprobar(conn, gente["ana"], solicitud, _fila(conn, solicitud)["huella_estimacion"])
    al_parar = {}

    def imprimir(tipo, nombre, _detalle) -> None:
        # Lo que ve la app al parar, antes de terminar: el primero ya no sale como fallido.
        if (tipo, nombre) == ("sin_leer", "nueva-2.pdf"):
            pasada = _pasada(conn, solicitud)
            al_parar.update(fallidas=pasada["fallidas"],
                            resultado=json.loads(pasada["resultado_json"]))

    leida = lectura.leer(conn, solicitud, client=client, almacen=almacen,
                         pdfs=sorted(carpeta.glob("*.pdf")), out_dir=out, imprimir=imprimir)
    assert al_parar == {"fallidas": 0, "resultado": []}
    assert client.intentos == ["nueva-1", "nueva-2"]
    assert (leida.estado, leida.fallidas) == ("fallida", 0)
    assert _fila(conn, solicitud)["motivo_codigo"] == "api_no_disponible"
    assert {r["nombre"] for r in leida.resultado} == {"vieja.pdf"}
    assert _pasada(conn, solicitud)["fallidas"] == 0


def test_un_400_del_documento_no_para_y_dos_distintos_tampoco(almacen, gente, buzon,
                                                             monkeypatch) -> None:
    """Un PDF que la API no acepta al leerlo es fallido, como siempre, y se sigue; dos fallos
    distintos seguidos, o dos iguales con uno bueno en medio, tambien."""
    _salida_corta(monkeypatch)
    conn = almacen.conn
    carpeta, out = buzon
    for nombre in ("nueva-3", "nueva-4"):
        _pdf(carpeta, nombre)
    otro = lambda: _error_api(400, "invalid_request_error", "otro mensaje")  # noqa: E731
    # El mismo 400 en la 1 y la 3, con la 2 bien leida en medio; y otro 400 en la 4.
    client = ClienteQueFalla(al_leer_falla={
        "nueva-1": DEL_DOCUMENTO["400"], "nueva-3": DEL_DOCUMENTO["400"], "nueva-4": otro})
    solicitud = _contada(almacen, gente["ana"], carpeta, out, client)
    lectura.aprobar(conn, gente["ana"], solicitud, _fila(conn, solicitud)["huella_estimacion"])
    leida = _leer(almacen, solicitud, carpeta, out, client)
    assert client.intentos == ["nueva-1", "nueva-2", "nueva-3", "nueva-4"]
    assert (leida.estado, leida.fase, leida.fallidas) == ("hecha", "hecha", 3)
    assert {r["nombre"]: r["estado"] for r in leida.resultado} == {
        "nueva-1.pdf": "fallida", "nueva-2.pdf": "nueva", "nueva-3.pdf": "fallida",
        "nueva-4.pdf": "fallida", "vieja.pdf": "ya_leida"}
    assert _fila(conn, solicitud)["motivo_codigo"] is None


def test_un_rechazo_del_modelo_no_para(almacen, gente, buzon, monkeypatch) -> None:
    """Un rechazo (Rechazado) es del documento: fallido, y se sigue. Dos seguidos tampoco
    paran: no son un error de la API."""
    _salida_corta(monkeypatch)
    conn = almacen.conn
    carpeta, out = buzon
    _pdf(carpeta, "nueva-3")
    client = ClienteQueFalla(rechaza={"nueva-1", "nueva-2"})
    solicitud = _contada(almacen, gente["ana"], carpeta, out, client)
    lectura.aprobar(conn, gente["ana"], solicitud, _fila(conn, solicitud)["huella_estimacion"])
    leida = _leer(almacen, solicitud, carpeta, out, client)
    assert client.intentos == ["nueva-1", "nueva-2", "nueva-3"]
    assert (leida.estado, leida.fase) == ("hecha", "hecha")
    assert {r["nombre"]: r["estado"] for r in leida.resultado} == {
        "nueva-1.pdf": "fallida", "nueva-2.pdf": "fallida", "nueva-3.pdf": "nueva",
        "vieja.pdf": "ya_leida"}


def test_informar_no_vuelve_fallido_lo_que_paro_la_api(almacen, gente, buzon) -> None:
    """Un aviso de error que llegue despues de `fallo` (de ese documento, o del primero de dos
    400 iguales) no lo vuelve fallido: no es culpa suya (§5.7)."""
    conn = almacen.conn
    carpeta, out = buzon
    solicitud = _contada(almacen, gente["ana"], carpeta, out, ClienteQueFalla())
    lectura.aprobar(conn, gente["ana"], solicitud, _fila(conn, solicitud)["huella_estimacion"])
    seguimiento = lectura.empezar(conn, solicitud, 2)
    igual = DEL_DOCUMENTO["400"]
    assert seguimiento.fallo("nueva-1.pdf", igual()) is False
    seguimiento.informar("error", "nueva-1.pdf", "el primero, del documento")
    assert seguimiento.estados == {"nueva-1.pdf": "fallida"}
    assert seguimiento.fallo("nueva-2.pdf", igual()) is True
    for nombre in ("nueva-1.pdf", "nueva-2.pdf"):
        seguimiento.informar("error", nombre, "un aviso tardio")
    assert seguimiento.estados == {"nueva-1.pdf": "sin_leer", "nueva-2.pdf": "sin_leer"}
    assert (seguimiento.parada, seguimiento.motivo_codigo) == ("fallida", "api_no_disponible")


@pytest.mark.parametrize("nombre", ["529", "402", "400-dos-iguales"])
def test_parar_mientras_falla_la_api_termina_cancelada(almacen, gente, buzon, monkeypatch,
                                                       nombre) -> None:
    """Una persona pide parar mientras se lee un documento, y esa llamada falla por algo que
    no es del documento: gana lo de la persona. La lectura termina cancelada (sin
    motivo_codigo: no cuenta como un fallo de la API) y el documento queda sin leer, no
    fallido. Con un 400 del documento, ya era asi."""
    _salida_corta(monkeypatch)
    conn = almacen.conn
    carpeta, out = buzon
    estado = {}

    def falla(fabrica):
        def lanzar():
            lectura.cancelar(conn, gente["ana"], estado["solicitud"])
            return fabrica()
        return lanzar

    if nombre == "400-dos-iguales":
        # El segundo de dos 400 iguales: tampoco es de los documentos.
        al_leer = {"nueva-1": DEL_DOCUMENTO["400"], "nueva-2": falla(DEL_DOCUMENTO["400"])}
    else:
        al_leer = {"nueva-1": falla(FALLOS_API[nombre][0])}
    client = ClienteQueFalla(al_leer_falla=al_leer)
    solicitud = estado["solicitud"] = _contada(almacen, gente["ana"], carpeta, out, client)
    lectura.aprobar(conn, gente["ana"], solicitud, _fila(conn, solicitud)["huella_estimacion"])
    impreso = []
    leida = _leer(almacen, solicitud, carpeta, out, client, impreso)
    assert (leida.estado, leida.fase, leida.fallidas) == ("cancelada", "cancelada", 0)
    assert leida.motivo == "se pidio parar la lectura: no se paga nada mas"
    fila = _fila(conn, solicitud)
    assert (fila["estado"], fila["motivo_codigo"]) == ("cancelada", None)
    assert fila["cancelada_en"] is not None
    parado = "nueva-2.pdf" if nombre == "400-dos-iguales" else "nueva-1.pdf"
    assert ("sin_leer", parado) in impreso and ("error", parado) not in impreso
    assert ("sin_leer", "nueva-2.pdf") in impreso
    assert {r["nombre"] for r in leida.resultado} == {"vieja.pdf"}
    pasada = _pasada(conn, solicitud)
    assert (pasada["fase"], pasada["fallidas"]) == ("cancelada", 0)
    datos = json.loads(conn.execute(
        "SELECT datos_json FROM evento WHERE tabla = 'solicitud_lectura' AND fila_id = ? "
        "ORDER BY id DESC", (solicitud,)).fetchone()[0])
    assert (datos["a"], "motivo_codigo" in datos) == ("cancelada", False)


# ============================================================ lo que ve la app

def test_lo_que_lee_la_app(almacen, gente, reloj) -> None:
    conn = almacen.conn
    assert lectura.para_la_app(conn) == {
        "solicitud": None, "pasada_en_curso": None, "ultima_pasada": None,
        "plazo_respuesta_segundos": 900, "consulta_cada_segundos": 2}
    solicitud = lectura_esperando(conn, gente["ana"])
    vista = lectura.para_la_app(conn)["solicitud"]
    assert (vista["id"], vista["estado"], vista["viva"], vista["abandonada"]) == (
        solicitud, "esperando_aprobacion", True, False)
    assert vista["pedida_por"] == {"id": gente["ana"], "nombre": "Ana"}
    assert (vista["pdf_nuevos"], vista["pdf_ya_leidos"], vista["coste_max_usd_micro"]) == (
        2, 1, 120_000)
    assert vista["huella_estimacion"] == _fila(conn, solicitud)["huella_estimacion"]
    assert "estimacion_json" not in vista
    # Ningun numero con decimales: el contrato va en enteros.
    texto = json.dumps(lectura.para_la_app(conn))
    assert not [v for v in json.loads(texto)["solicitud"].values() if isinstance(v, float)]
    # Sin respuesta y con el lector cerrado, la app ve que esta abandonada.
    reloj.avanzar(minutes=20)
    assert lectura.para_la_app(conn)["solicitud"]["abandonada"] is True
    # Terminada, sigue siendo la ultima.
    lectura.cancelar(conn, gente["ana"], solicitud)
    vista = lectura.para_la_app(conn)["solicitud"]
    assert (vista["estado"], vista["viva"], vista["cancelada_por"]["nombre"]) == (
        "cancelada", False, "Ana")
    assert campos.verificar_controladas(conn) == []


# ============================================================ por /api/v2

def test_la_lectura_por_la_api(tmp_path) -> None:
    """GET /api/v2/lectura lleva la peticion y su pasada (contrato 2.5); las tres ordenes van
    por POST /api/v2/acciones con sus codigos: un si con otra huella es un 409 «conflicto»,
    uno fuera de plazo o de estado un 409 «estado_no_valido», y quien solo consulta, 403."""
    import threading

    from test_consola import AgenteFalso, _leer, _orden

    from bms_agent import consultas, permisos
    from bms_agent.almacen import preparar
    from bms_agent.serve import crear_servidor

    db = tmp_path / "datos" / "bms.sqlite3"
    with preparar(db) as almacen:
        conn = almacen.conn
        ana, carla = persona(conn, "Ana", "administracion"), persona(conn, "Carla", "consulta")
        tokens = {"ana": permisos.emitir_token(conn, ana),
                  "carla": permisos.emitir_token(conn, carla)}
    srv = crear_servidor(tmp_path / "facturas", tmp_path / "out", 0, token="t",
                         agente=AgenteFalso(), ruta_db=db)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05},
                     daemon=True).start()
    puerto = srv.server_address[1]
    try:
        estado, cabeceras, cuerpo = _leer(puerto, "/api/v2/lectura", tokens["carla"])
        assert estado == 200 and cabeceras["x-bms-contrato"] == consultas.CONTRATO_V2 == "2.5"
        assert (cuerpo["lectura"]["solicitud"], cuerpo["lectura"]["pasada_en_curso"]) == (
            None, None)
        estado, respuesta = _orden(puerto, tokens["carla"], {"accion": "pedir_lectura"})
        assert (estado, respuesta["codigo"]) == (403, "sin_permiso")
        estado, respuesta = _orden(puerto, tokens["ana"], {"accion": "pedir_lectura",
                                                           "peticion_id": "p-1"})
        assert estado == 200, respuesta
        solicitud = respuesta["diferencia"]["detalle"]["solicitud_id"]
        estado, respuesta = _orden(puerto, tokens["ana"], {"accion": "pedir_lectura"})
        assert (estado, respuesta["codigo"]) == (409, "estado_no_valido")
        # El lector la toma y la cuenta (aqui, a mano y sin API).
        with preparar(db) as almacen:
            lectura.tomar(almacen.conn, hay_pdf=True)
            lectura.contar(almacen.conn, solicitud, lambda _a: estimacion_lectura())
        _e, _c, cuerpo = _leer(puerto, "/api/v2/lectura", tokens["carla"])
        vista = cuerpo["lectura"]["solicitud"]
        assert (vista["id"], vista["estado"], vista["pdf_nuevos"]) == (
            solicitud, "esperando_aprobacion", 2)
        estado, respuesta = _orden(puerto, tokens["ana"], {
            "accion": "aprobar_lectura",
            "datos": {"solicitud_id": solicitud, "huella_estimacion": "e" * 64}})
        assert (estado, respuesta["codigo"]) == (409, "conflicto")
        estado, respuesta = _orden(puerto, tokens["ana"], {
            "accion": "aprobar_lectura",
            "datos": {"solicitud_id": solicitud, "huella_estimacion": vista["huella_estimacion"],
                      "tope_usd_micro": "90000"}})
        assert estado == 200 and respuesta["diferencia"]["detalle"]["tope_usd_micro"] == 90_000
        estado, respuesta = _orden(puerto, tokens["ana"], {
            "accion": "aprobar_lectura",
            "datos": {"solicitud_id": solicitud,
                      "huella_estimacion": vista["huella_estimacion"]}})
        assert (estado, respuesta["codigo"]) == (409, "estado_no_valido")
        estado, respuesta = _orden(puerto, tokens["ana"], {
            "accion": "cancelar_lectura", "datos": {"solicitud_id": solicitud}})
        assert estado == 200 and respuesta["diferencia"]["detalle"]["estado"] == "cancelada"
        estado, respuesta = _orden(puerto, tokens["ana"], {
            "accion": "cancelar_lectura", "datos": {"solicitud_id": 999}})
        assert (estado, respuesta["codigo"]) == (404, "no_existe")
        _e, _c, cuerpo = _leer(puerto, "/api/v2/lectura", tokens["carla"])
        assert cuerpo["lectura"]["solicitud"]["estado"] == "cancelada"
    finally:
        srv.shutdown()
        srv.server_close()
