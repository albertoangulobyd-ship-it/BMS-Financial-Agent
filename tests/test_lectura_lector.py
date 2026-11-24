"""El lector de verdad (leer-facturas.ps1 de windows/ y de docker/), orden a orden (paso 17).

Aqui no hay PowerShell. `leer_facturas` hace lo mismo que windows/leer-facturas.ps1, paso a
paso y con las mismas ordenes de bms-agent (cli.main), con una salida falsa que apunta cuando
se enciende y se apaga y una API falsa que se niega a contestar con la salida apagada. Los
tests estaticos de abajo comprueban que los dos scripts dan esos pasos en ese orden.

Puertas que viven aqui:

- el orden no cambia: tomar, salida, aislamiento, contar, esperar el si, leer, y al final,
  pase lo que pase, salida apagada y la lectura cerrada si quedo a medias;
- si el aislamiento falla no se cuenta ni se lee (y la puerta del lector tampoco deja);
- sin respuesta o con un no no se gasta nada;
- el tope para la lectura; el si de la app vale para lo que se conto;
- sin PDF no se enciende nada;
- un PDF que la API no acepta no bloquea los demas, y un fallo de la API que no es de un PDF
  (la clave, el saldo, no disponible) cierra la lectura con su motivo (paso 18, D12).
"""

from __future__ import annotations

import re
from datetime import timedelta

import pytest
from conftest import RAIZ, persona
from test_lectura import (DEL_DOCUMENTO, FALLOS_API, SIN_PDF, ClienteQueCuenta, ClienteQueFalla,
                          _error_api, _pdf)

from bms_agent import cli, lectura, permisos, servicios
from bms_agent.almacen import preparar
from bms_agent.nativo import LecturaNoAislada


class SalidaFalsa:
    """La salida de la instalacion nativa: solo se apunta cuando se enciende y se apaga."""

    def __init__(self) -> None:
        self.encendida = False
        self.historia: list[str] = []

    def encender(self) -> None:
        self.encendida = True
        self.historia.append("encendida")

    def apagar(self) -> None:
        self.encendida = False
        self.historia.append("apagada")


class ApiFalsa(ClienteQueCuenta):
    """La API: sin la salida encendida no se llega a ella."""

    def __init__(self, salida: SalidaFalsa, **opciones) -> None:
        super().__init__(**opciones)
        self.salida = salida

    def count_tokens(self, **peticion):
        assert self.salida.encendida, "contar con la salida apagada"
        return super().count_tokens(**peticion)

    def parse(self, **peticion):
        assert self.salida.encendida, "leer con la salida apagada"
        return super().parse(**peticion)


class ApiQueFalla(ApiFalsa, ClienteQueFalla):
    """La API sin la salida encendida no se alcanza, y falla en los PDF que se le digan."""


@pytest.fixture
def lector(tmp_path, monkeypatch, capsys):
    db = tmp_path / "datos" / "bms.sqlite3"
    buzon = tmp_path / "buzon" / "facturas"
    buzon.mkdir(parents=True)
    out = tmp_path / "datos" / "out"
    with preparar(db) as almacen:
        ana = persona(almacen.conn, "Ana", "administracion")
    salida = SalidaFalsa()
    estado = {"puerta": True, "ventana": lambda _segundos: "si\n"}

    def cliente_api(_anthropic):
        # La puerta del lector (nativo.exigir_lectura): con la salida de esta pasada y su
        # aislamiento comprobado.
        if not (salida.encendida and estado["puerta"]):
            raise LecturaNoAislada("no se lee nada ni se paga nada: el aislamiento no esta bien")
        return estado["api"]

    monkeypatch.setattr(cli, "_cliente_api", cliente_api)
    monkeypatch.setattr(cli, "_linea_de_la_ventana", lambda: estado["ventana"])
    estado["api"] = ApiFalsa(salida)

    def leer_facturas(*, aislamiento_bien: bool = True) -> tuple[list[str], int | str]:
        """Lo que hace windows/leer-facturas.ps1 (PASOS_WINDOWS), con sus mismas ordenes."""
        pasos = ["tomar"]
        codigo = cli.main(["lectura", "tomar", str(buzon), "--db", str(db)])
        if codigo == cli.LECTURA_NADA:
            return pasos, "nada"
        if codigo == cli.LECTURA_OCUPADA:
            return pasos, "ocupada"
        solicitud = capsys.readouterr().out.strip().splitlines()[-1]
        assert re.fullmatch(r"[0-9]+", solicitud)
        salida.encender()
        pasos.append("salida")
        try:
            pasos.append("aislamiento")
            if not aislamiento_bien:
                cli.main(["lectura", "cerrar", solicitud, "--motivo", "aislamiento", "--db",
                          str(db)])
                return pasos, "aislamiento"
            pasos.append("contar")
            codigo = cli.main(["lectura", "contar", solicitud, str(buzon), "--out", str(out),
                               "--db", str(db)])
            if codigo != 0:
                return pasos, codigo
            pasos.append("esperar")
            codigo = cli.main(["lectura", "esperar", solicitud, "--db", str(db)])
            if codigo != 0:
                return pasos, codigo
            pasos.append("leer")
            return pasos, cli.main(["lectura", "leer", solicitud, str(buzon), "--out", str(out),
                                    "--db", str(db)])
        finally:
            salida.apagar()
            pasos.append("apagar")
            cli.main(["lectura", "cerrar", solicitud, "--motivo", "interrumpida", "--si-viva",
                      "--db", str(db)])
            pasos.append("cerrar")

    def ultima():
        with preparar(db) as almacen:
            return almacen.conn.execute(
                "SELECT * FROM solicitud_lectura ORDER BY id DESC LIMIT 1").fetchone()

    def desde_la_app(orden: str, datos: dict | None = None) -> None:
        """Una orden de la app, por su propia conexion (el servidor, no el lector)."""
        with preparar(db) as almacen:
            servicios.ejecutar(almacen.conn, orden, datos or {}, usuario_id=ana)

    return {"leer_facturas": leer_facturas, "salida": salida, "estado": estado, "buzon": buzon,
            "ultima": ultima, "app": desde_la_app, "db": db}


PASOS_COMPLETOS = ["tomar", "salida", "aislamiento", "contar", "esperar", "leer", "apagar",
                   "cerrar"]


def test_el_orden_de_siempre_y_la_salida_apagada_al_final(lector) -> None:
    _pdf(lector["buzon"], "una")
    _pdf(lector["buzon"], "otra")
    pasos, codigo = lector["leer_facturas"]()
    assert (pasos, codigo) == (PASOS_COMPLETOS, 0)
    assert lector["salida"].historia == ["encendida", "apagada"]
    api = lector["estado"]["api"]
    assert (api.conteos, sorted(api.leidos)) == (2, ["otra", "una"])
    fila = lector["ultima"]()
    assert (fila["estado"], fila["origen"], fila["aprobada_via"]) == ("hecha", "lector",
                                                                      "ventana")


def test_la_app_pide_y_da_el_si_y_el_lector_lee(lector) -> None:
    _pdf(lector["buzon"], "una")
    lector["app"]("pedir_lectura")

    def la_app_dice_que_si(_segundos):
        fila = lector["ultima"]()
        lector["app"]("aprobar_lectura", {"solicitud_id": fila["id"],
                                          "huella_estimacion": fila["huella_estimacion"]})
        return None

    lector["estado"]["ventana"] = la_app_dice_que_si
    pasos, codigo = lector["leer_facturas"]()
    assert (pasos, codigo) == (PASOS_COMPLETOS, 0)
    fila = lector["ultima"]()
    assert (fila["estado"], fila["origen"], fila["aprobada_via"]) == ("hecha", "app", "app")
    assert fila["aprobada_por"] == fila["pedida_por"] is not None


@pytest.mark.parametrize("donde", ["script", "puerta"])
def test_si_el_aislamiento_falla_no_se_cuenta_ni_se_lee(lector, donde) -> None:
    _pdf(lector["buzon"], "una")
    if donde == "puerta":
        # El script vio bien el aislamiento, pero la puerta del lector no (otra credencial,
        # una comprobacion vieja): tampoco se cuenta.
        lector["estado"]["puerta"] = False
    pasos, codigo = lector["leer_facturas"](aislamiento_bien=donde != "script")
    api = lector["estado"]["api"]
    assert (api.conteos, api.leidos) == (0, [])
    assert pasos[-2:] == ["apagar", "cerrar"] and "esperar" not in pasos
    assert codigo in ("aislamiento", cli.LECTURA_FALLIDA)
    fila = lector["ultima"]()
    assert (fila["estado"], fila["motivo_codigo"]) == ("fallida", "aislamiento")
    assert lector["salida"].historia == ["encendida", "apagada"]


@pytest.mark.parametrize("respuesta, codigo, estado", [
    ("no\n", cli.LECTURA_CANCELADA, "cancelada"),
    (None, cli.LECTURA_CADUCADA, "caducada")])
def test_con_un_no_o_sin_respuesta_no_se_gasta_nada(lector, monkeypatch, respuesta, codigo,
                                                   estado) -> None:
    _pdf(lector["buzon"], "una")
    if respuesta is None:
        monkeypatch.setattr(lectura, "PLAZO_RESPUESTA", timedelta(seconds=0))
    lector["estado"]["ventana"] = lambda _segundos: respuesta
    pasos, salio = lector["leer_facturas"]()
    assert (pasos[-3:], salio) == (["esperar", "apagar", "cerrar"], codigo)
    api = lector["estado"]["api"]
    # Contar es gratis; leer, no: no se ha leido nada.
    assert (api.conteos, api.leidos) == (1, [])
    assert lector["ultima"]()["estado"] == estado
    assert lector["salida"].historia == ["encendida", "apagada"]


def test_el_no_de_la_app_mientras_espera(lector) -> None:
    _pdf(lector["buzon"], "una")

    def la_app_dice_que_no(_segundos):
        lector["app"]("cancelar_lectura", {"solicitud_id": lector["ultima"]()["id"]})
        return None

    lector["estado"]["ventana"] = la_app_dice_que_no
    pasos, codigo = lector["leer_facturas"]()
    assert codigo == cli.LECTURA_CANCELADA and "leer" not in pasos
    assert lector["estado"]["api"].leidos == []
    assert lector["ultima"]()["cancelada_via"] == "app"


def test_el_tope_que_da_la_app_para_la_lectura(lector) -> None:
    for nombre in ("a", "b", "c"):
        _pdf(lector["buzon"], nombre)

    def un_tope_corto(_segundos):
        import json

        fila = lector["ultima"]()
        alto = json.loads(fila["estimacion_json"])["documentos"][0]["alto_usd_micro"]
        lector["app"]("aprobar_lectura", {"solicitud_id": fila["id"],
                                          "huella_estimacion": fila["huella_estimacion"],
                                          "tope_usd_micro": alto})
        return None

    lector["estado"]["ventana"] = un_tope_corto
    pasos, codigo = lector["leer_facturas"]()
    assert (pasos, codigo) == (PASOS_COMPLETOS, 0)
    assert len(lector["estado"]["api"].leidos) == 1
    with preparar(lector["db"]) as almacen:
        pasada = almacen.conn.execute("SELECT * FROM pasada_lectura").fetchone()
    fila = lector["ultima"]()
    assert pasada["fase"] == "tope" and pasada["coste_usd_micro"] <= fila["tope_usd_micro"]
    assert fila["estado"] == "hecha"


def test_ctrl_c_esperando_cierra_la_lectura_y_apaga_la_salida(lector) -> None:
    _pdf(lector["buzon"], "una")

    def ctrl_c(_segundos):
        raise KeyboardInterrupt

    lector["estado"]["ventana"] = ctrl_c
    with pytest.raises(KeyboardInterrupt):
        lector["leer_facturas"]()
    fila = lector["ultima"]()
    assert (fila["estado"], fila["motivo_codigo"]) == ("fallida", "interrumpida")
    assert lector["salida"].historia == ["encendida", "apagada"]
    assert lector["estado"]["api"].leidos == []


def test_sin_pdf_no_se_enciende_nada(lector) -> None:
    pasos, codigo = lector["leer_facturas"]()
    assert (pasos, codigo) == (["tomar"], "nada")
    assert lector["salida"].historia == []
    # Una pedida desde la app termina sin nada que leer.
    lector["app"]("pedir_lectura")
    assert lector["leer_facturas"]() == (["tomar"], "nada")
    fila = lector["ultima"]()
    assert (fila["estado"], fila["motivo_codigo"]) == ("nada_que_leer", "buzon_vacio")


def test_el_lector_lee_tambien_lo_que_trajo_el_correo(lector) -> None:
    """Paso 18: leer-facturas sigue igual, y lo que el correo dejo en el almacen sin leer entra
    en la misma cuenta y la misma lectura (con el si de siempre); lo que una persona aparto de
    la lectura automatica, no. Sin nada en buzon/facturas tambien hay que leer."""
    from test_lectura_automatica import _correo, _documento

    from bms_agent import lectura_automatica

    with preparar(lector["db"]) as almacen:
        del_correo = _documento(almacen, "del-correo")
        apartado = _documento(almacen, "apartado")
        _correo(almacen.conn, "2026-10-14T08:00:00+00:00", ("documento", del_correo),
                ("documento", apartado))
        ana = permisos.usuario_por_nombre(almacen.conn, "Ana")
        lectura_automatica.excluir(almacen.conn, [apartado], "persona", ana)
    pasos, codigo = lector["leer_facturas"]()
    assert (pasos, codigo) == (PASOS_COMPLETOS, 0)
    assert lector["estado"]["api"].leidos == ["del-correo"]
    fila = lector["ultima"]()
    assert (fila["estado"], fila["origen"], fila["aprobada_via"]) == ("hecha", "lector",
                                                                      "ventana")
    # Leido, ya no queda nada que leer.
    assert lector["leer_facturas"]() == (["tomar"], "nada")


def test_dos_lectores_a_la_vez_no(lector) -> None:
    _pdf(lector["buzon"], "una")
    with preparar(lector["db"]) as almacen:
        lectura.tomar(almacen.conn, hay_pdf=True)
    assert lector["leer_facturas"]() == (["tomar"], "ocupada")
    assert lector["salida"].historia == []


# ============================================================ los fallos de la API (paso 18)

def test_un_pdf_que_la_api_no_acepta_no_bloquea_los_demas(lector, capsys) -> None:
    """Antes, un PDF que la API rechazaba al contar cerraba toda la lectura con "contar". Ahora
    queda omitido (la ventana dice por que) y los demas se cuentan, se aprueban y se leen."""
    for nombre in ("una", "mala", "otra"):
        _pdf(lector["buzon"], nombre)
    api = ApiQueFalla(lector["salida"], al_contar={"mala": DEL_DOCUMENTO["413"]})
    lector["estado"]["api"] = api
    pasos, codigo = lector["leer_facturas"]()
    assert (pasos, codigo) == (PASOS_COMPLETOS, 0)
    # La contraprueba (sin el PDF) va justo despues del primero que la API no acepta.
    assert api.contados[api.contados.index("mala") + 1] == SIN_PDF
    assert (sorted(api.contados), sorted(api.leidos)) == (
        sorted(["mala", SIN_PDF, "otra", "una"]), ["otra", "una"])
    assert "mala" not in api.intentos
    assert re.search(r"omitido +mala\.pdf: la API no lo acepta: \w+ 413 request_too_large",
                     capsys.readouterr().out)
    fila = lector["ultima"]()
    assert (fila["estado"], fila["pdf_nuevos"]) == ("hecha", 2)
    assert lector["salida"].historia == ["encendida", "apagada"]


@pytest.mark.parametrize("nombre", sorted(FALLOS_API))
def test_un_fallo_de_la_api_al_contar_cierra_con_su_motivo(lector, capsys, nombre) -> None:
    """La clave, el saldo o la API no disponible: no se cuenta nada mas, no se espera ningun si
    y la lectura termina fallida con ese motivo (no con "contar"); la salida, apagada."""
    _pdf(lector["buzon"], "una")
    _pdf(lector["buzon"], "otra")
    fabrica, motivo = FALLOS_API[nombre]
    api = ApiQueFalla(lector["salida"], al_contar={"otra": fabrica})
    lector["estado"]["api"] = api
    pasos, codigo = lector["leer_facturas"]()
    assert (pasos[-3:], codigo) == (["contar", "apagar", "cerrar"], cli.LECTURA_FALLIDA)
    assert (api.contados, api.intentos) == (["otra"], [])
    fila = lector["ultima"]()
    assert (fila["estado"], fila["motivo_codigo"]) == ("fallida", motivo)
    assert fila["motivo"].startswith(lectura.MOTIVOS[motivo] + ": otra.pdf: ")
    assert lectura.MOTIVOS[motivo] in capsys.readouterr().err
    assert lector["salida"].historia == ["encendida", "apagada"]


def test_un_fallo_nuestro_al_contar_sigue_siendo_contar(lector) -> None:
    _pdf(lector["buzon"], "una")
    lector["estado"]["api"] = ApiQueFalla(
        lector["salida"], al_contar={"una": lambda: TypeError("un fallo nuestro")})
    _pasos, codigo = lector["leer_facturas"]()
    fila = lector["ultima"]()
    assert (codigo, fila["estado"], fila["motivo_codigo"]) == (cli.LECTURA_FALLIDA, "fallida",
                                                               "contar")
    assert "un fallo nuestro" in fila["motivo"]


def test_un_400_de_la_configuracion_no_dice_que_no_hay_nada(lector, capsys) -> None:
    """El mismo 400 con todos, tambien sin el PDF (la configuracion): la lectura termina
    fallida con api_no_disponible y lo que dijo la API, no "no hay facturas nuevas", y no se
    aparta ninguna (la cuenta no se guarda)."""
    _pdf(lector["buzon"], "una")
    _pdf(lector["buzon"], "otra")
    configuracion = lambda: _error_api(  # noqa: E731
        400, "invalid_request_error", "output_config.effort: unknown value")
    api = ApiQueFalla(lector["salida"], al_contar={"una": configuracion, "otra": configuracion,
                                                   SIN_PDF: configuracion})
    lector["estado"]["api"] = api
    pasos, codigo = lector["leer_facturas"]()
    assert (pasos[-3:], codigo) == (["contar", "apagar", "cerrar"], cli.LECTURA_FALLIDA)
    assert (api.contados, api.intentos) == (["otra", SIN_PDF], [])
    fila = lector["ultima"]()
    assert (fila["estado"], fila["motivo_codigo"], fila["estimacion_json"]) == (
        "fallida", "api_no_disponible", None)
    assert "output_config.effort: unknown value; sin el PDF, lo mismo" in fila["motivo"]
    assert "omitido" not in capsys.readouterr().out
    assert lector["salida"].historia == ["encendida", "apagada"]


def test_un_buzon_con_solo_pdf_que_la_api_no_acepta(lector, capsys) -> None:
    """Hay un PDF nuevo, pero la API no lo acepta: la ventana no dice "no hay facturas nuevas"
    (el script lo diria con LECTURA_NADA) sino que no se ha podido contar, con por que."""
    _pdf(lector["buzon"], "mala")
    api = ApiQueFalla(lector["salida"], al_contar={"mala": DEL_DOCUMENTO["413"]})
    lector["estado"]["api"] = api
    pasos, codigo = lector["leer_facturas"]()
    assert (pasos[-3:], codigo) == (["contar", "apagar", "cerrar"], cli.LECTURA_FALLIDA)
    fila = lector["ultima"]()
    assert (fila["estado"], fila["motivo_codigo"]) == ("fallida", "contar")
    salida = capsys.readouterr()
    assert re.search(r"omitido +mala\.pdf: la API no lo acepta", salida.out)
    assert "No se lee: no se ha podido contar lo que costaria" in salida.err
    assert "la API no acepta ninguno de los PDF nuevos: mala.pdf" in salida.err
    assert lector["salida"].historia == ["encendida", "apagada"]


def test_sin_saldo_al_leer_el_lector_para_y_no_culpa_a_ninguna(lector, capsys) -> None:
    """Un 402 en la primera: no se intenta la segunda, ninguna queda "con problemas", y la
    lectura termina fallida con "saldo" (antes: hecha, con todas fallidas y el texto del SDK)."""
    _pdf(lector["buzon"], "una")
    _pdf(lector["buzon"], "otra")
    api = ApiQueFalla(lector["salida"], al_leer_falla={"otra": FALLOS_API["402"][0]})
    lector["estado"]["api"] = api
    pasos, codigo = lector["leer_facturas"]()
    assert (pasos, codigo) == (PASOS_COMPLETOS, cli.LECTURA_FALLIDA)
    assert (api.intentos, api.leidos) == (["otra"], [])
    fila = lector["ultima"]()
    assert (fila["estado"], fila["motivo_codigo"]) == ("fallida", "saldo")
    salida = capsys.readouterr().out
    assert re.search(r"sin leer +otra\.pdf: el saldo de la API se ha acabado", salida)
    assert re.search(r"sin leer +una\.pdf: el saldo de la API se ha acabado", salida)
    assert "con problemas 0" in salida and f": fallida (fallida)" in salida
    assert lector["salida"].historia == ["encendida", "apagada"]


# ============================================================ los scripts dicen lo mismo

WINDOWS = RAIZ / "windows"
DOCKER = RAIZ / "docker"

# Lo que hace cada paso de leer_facturas en windows/leer-facturas.ps1, en su orden.
PASOS_WINDOWS = [
    ("tomar", 'Valor-De "lector" @("lectura", "tomar", $facturas)'),
    ("salida", "$salida = Arrancar-Salida $credencial $VidaSalidaLectura"),
    ("aislamiento", 'Comprobar-Rol "salida"'),
    ("aislamiento", 'Comprobar-Rol "lector"'),
    ("aislamiento", 'Cerrar-Lectura $solicitud "aislamiento"'),
    ("contar", 'Orden-De "lector" @("lectura", "contar", $solicitud, $facturas, "--out", $out)'),
    ("esperar", 'Orden-Directa "lector" @("lectura", "esperar", $solicitud)'),
    ("leer", 'Orden-De "lector" @("lectura", "leer", $solicitud, $facturas, "--out", $out)'),
    ("apagar", "} finally {"),
    ("apagar", "Parar-Salida $salida"),
    ("cerrar", 'Cerrar-Lectura $solicitud "interrumpida" -SiViva'),
]

PASOS_DOCKER = [
    ("tomar", "docker compose run --rm -T orden lectura tomar /buzon/facturas"),
    ("contar", "docker compose run --rm -T lector lectura contar $solicitud /buzon/facturas "
               "--out /datos/out"),
    ("esperar", "docker compose run --rm -T orden lectura esperar $solicitud\n"),
    ("leer", "docker compose run --rm -T lector lectura leer $solicitud /buzon/facturas "
             "--out /datos/out"),
    ("cerrar", "} finally {"),
    ("cerrar", 'Cerrar-Lectura $solicitud "interrumpida" -SiViva'),
]


def _sin_comentarios(texto: str) -> str:
    return "\n".join(linea for linea in texto.splitlines() if not linea.lstrip().startswith("#"))


@pytest.mark.parametrize("carpeta, pasos", [(WINDOWS, PASOS_WINDOWS), (DOCKER, PASOS_DOCKER)])
def test_los_scripts_dan_los_pasos_en_el_mismo_orden(carpeta, pasos) -> None:
    texto = _sin_comentarios((carpeta / "leer-facturas.ps1").read_text(encoding="utf-8"))
    posiciones = [texto.index(trozo) for _paso, trozo in pasos]
    assert posiciones == sorted(posiciones), pasos
    # Cada orden, una vez: nadie cuenta ni lee por otro camino.
    for orden in ("contar", "esperar", "leer"):
        assert len(re.findall(rf"lectura\"?,? \"?{orden}\b", texto)) == 1, orden
    assert "extract" not in texto and "coste" not in texto
    # Esperar y leer van en la rama de un codigo 0 del paso anterior: con un no, sin
    # respuesta o con un fallo no se llega a ellos.
    def marca(orden: str) -> str:
        return f"lectura {orden}" if carpeta == DOCKER else f'"lectura", "{orden}"'

    for anterior, siguiente in (("contar", "esperar"), ("esperar", "leer")):
        trozo = texto[texto.index(marca(anterior)):texto.index(marca(siguiente))]
        assert "} elseif ($codigo -ne 0) {" in trozo and "} else {" in trozo, trozo
    # Fallar (que sale) solo despues del finally: la salida se apaga y la lectura se cierra.
    final = texto.index('Cerrar-Lectura $solicitud "interrumpida" -SiViva')
    assert texto.index("if ($motivo) { Fallar $motivo }") > final


def test_en_windows_nada_se_cuenta_sin_el_aislamiento_bien() -> None:
    texto = (WINDOWS / "leer-facturas.ps1").read_text(encoding="utf-8")
    comprobado = texto.index("if ($codigoSalida -ne 0 -or $codigoLector -ne 0) {")
    sino = texto.index("} else {", comprobado)
    rama_mala = texto[comprobado:sino]
    assert 'Cerrar-Lectura $solicitud "aislamiento"' in rama_mala
    assert "contar" not in rama_mala and "leer" not in rama_mala
    assert texto.index('"lectura", "contar"') > sino
    # La credencial y el proxy se olvidan en el finally, antes de cerrar la lectura.
    finalmente = texto[texto.index("} finally {"):]
    assert finalmente.index("Remove-Item Env:\\HTTPS_PROXY") < finalmente.index("Parar-Salida")
    assert finalmente.index("Parar-Salida $salida") < finalmente.index("Cerrar-Lectura")


@pytest.mark.parametrize("carpeta", [WINDOWS, DOCKER])
def test_los_codigos_del_lector_son_los_de_la_cli(carpeta) -> None:
    comun = (carpeta / "comun.ps1").read_text(encoding="utf-8")
    codigos = (("Nada", cli.LECTURA_NADA), ("Ocupada", cli.LECTURA_OCUPADA),
               ("Cancelada", cli.LECTURA_CANCELADA), ("Caducada", cli.LECTURA_CADUCADA),
               ("Fallida", cli.LECTURA_FALLIDA),
               # Paso 18: lo que dice `lectura siguiente` al ciclo automatico.
               ("Pedida", cli.LECTURA_PEDIDA), ("Limite", cli.LECTURA_LIMITE))
    for nombre, valor in codigos:
        assert f"$Lectura{nombre} = {valor}\n" in comun, nombre
    # Cada codigo de la CLI, uno solo, y en los dos comun.ps1 los mismos y nada mas.
    de_la_cli = {n: v for n, v in vars(cli).items() if n.startswith("LECTURA_")}
    assert sorted(de_la_cli.values()) == list(range(3, 10))
    assert {f"Lectura{n.title()}" for n, _v in codigos} == {
        "Lectura" + n.removeprefix("LECTURA_").title() for n in de_la_cli}
    assert len(re.findall(r"^\$Lectura[A-Z][a-z]+ = \d+$", comun, re.M)) == len(de_la_cli)
    cerrar = comun[comun.index("function Cerrar-Lectura"):]
    cerrar = cerrar[:cerrar.index("\n}\n")]
    assert '@("lectura", "cerrar", $Solicitud, "--motivo", $Motivo)' in cerrar
    assert '"--si-viva"' in cerrar
    # Los motivos que usan los scripts son los que la CLI admite.
    for script in ("leer-facturas.ps1",):
        texto = (carpeta / script).read_text(encoding="utf-8")
        for motivo in re.findall(r'Cerrar-Lectura \$solicitud "([a-z_]+)"', texto):
            assert motivo in lectura.MOTIVOS, motivo


def test_docker_espera_el_si_en_el_contenedor_sin_red() -> None:
    texto = (DOCKER / "leer-facturas.ps1").read_text(encoding="utf-8")
    # Tomar, esperar y cerrar no hablan con la API: el contenedor de las ordenes, sin red.
    assert "run --rm -T orden lectura tomar" in texto
    assert "run --rm -T orden lectura esperar" in texto
    assert "run --rm -T lector lectura esperar" not in texto
    # Esperar va sin tuberia: lo que se escribe en la ventana le llega.
    esperar = texto[texto.index("run --rm -T orden lectura esperar"):]
    assert esperar.splitlines()[0].rstrip().endswith("$solicitud")
    compose = (DOCKER / "docker-compose.yml").read_text(encoding="utf-8")
    orden = compose[compose.index("\n  orden:"):]
    assert "network_mode: none" in orden[:orden.index("\nnetworks:")]


def test_la_persona_de_la_app_no_es_del_lector(lector) -> None:
    """El lector no firma como nadie: sus eventos son del extractor, sin persona."""
    _pdf(lector["buzon"], "una")
    lector["leer_facturas"]()
    with preparar(lector["db"]) as almacen:
        conn = almacen.conn
        filas = conn.execute(
            "SELECT e.tipo, e.usuario_id, u.nombre FROM evento AS e JOIN usuario AS u "
            "ON u.id = e.actor WHERE e.tabla = 'solicitud_lectura' ORDER BY e.id").fetchall()
        assert filas and {(f["usuario_id"], f["nombre"]) for f in filas} == {(None, "extractor")}
        assert permisos.es_persona(conn, None) is False
