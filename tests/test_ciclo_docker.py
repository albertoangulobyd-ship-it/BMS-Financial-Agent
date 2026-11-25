"""El ciclo automatico de Docker de verdad (paso 18, docker/ciclo.ps1), con pwsh y un docker falso.

Lo que dicen los pines de test_entorno_local.py, corrido: docker/ciclo.ps1 y docker/comun.ps1 tal
cual, en una copia de la carpeta docker/, con un `docker` falso delante en el PATH que apunta cada
orden y contesta lo que pide cada caso. Asi se ve el orden de las ordenes de un ciclo (la pausa,
el cerrojo, el latido, el correo y registrar, la pasada del dia, la lectura pedida o automatica,
y la lectura que nunca se queda viva), lo que hace con cada codigo de salida, y que el bucle no
sale nunca por si mismo. Sin pwsh, se salta. Lo que solo se ve en Windows (el Programador de
tareas, Docker Desktop, el disco de verdad) va en la lista de §7.4 del diseno.
"""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from conftest import RAIZ

from bms_agent import ciclo as modulo_ciclo

PWSH = shutil.which("pwsh")
pytestmark = pytest.mark.skipif(PWSH is None, reason="sin pwsh")

DOCKER = RAIZ / "docker"

# El docker falso: apunta cada orden (y la base que pide BMS_BASE) y contesta con la primera regla
# cuyo trozo esta en la orden: [trozo, codigo de salida, lo que dice por la salida normal].
FALSO = """#!{python}
import json, os, sys
linea = " ".join(sys.argv[1:])
with open(os.environ["DOCKER_FALSO_REGISTRO"], "a", encoding="utf-8") as f:
    f.write(json.dumps({{"orden": linea, "base": os.environ.get("BMS_BASE")}}) + "\\n")
with open(os.environ["DOCKER_FALSO"], encoding="utf-8") as f:
    reglas = json.load(f)
for trozo, codigo, salida in reglas:
    if trozo in linea:
        if salida:
            print(salida)
        sys.exit(codigo)
sys.exit(0)
"""

INICIO = ["info", "image inspect bms-agent:local"]
LATIDO = "compose run --rm -T orden ciclo latido --variante docker --disco-libre"
CORREO = ["compose up -d --wait --wait-timeout 120 salida_correo",
          "compose run --rm -T correo",
          "compose run --rm -T orden correo registrar --entrada /correo/entrada "
          "--estado /correo/estado"]
SIGUIENTE = "compose run --rm -T orden lectura siguiente"
# La ronda del bucle que ademas comprueba el alcance (§2.3), hasta la primera que acaba bien.
TRAER_COMPROBAR = ("compose run --rm -T correo correo traer --ajustes /run/secrets/correo_ajustes "
                   "--certificado-fichero /run/secrets/correo_certificado --estado /correo/estado "
                   "--entrada /correo/entrada --comprobar")
PAUSADO = "compose run --rm -T orden ciclo latido --pausado --variante docker"


def _automatica(n: int) -> list[str]:
    return [SIGUIENTE, "compose run --rm -T orden lectura tomar --automatica",
            "compose up -d --wait --wait-timeout 180 salida",
            f"compose run --rm -T lector lectura contar {n} /buzon/facturas --out /datos/out",
            f"compose run --rm -T orden lectura autorizar {n}",
            f"compose run --rm -T lector lectura leer {n} /buzon/facturas --out /datos/out",
            f"compose run --rm -T orden lectura cerrar {n} --motivo interrumpida --si-viva"]


def _puerto_libre() -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", 8765)) != 0


class Ciclo:
    """Una copia de docker/ con sus scripts, el docker falso y lo que hace falta para correrlos."""

    def __init__(self, raiz):
        self.raiz = raiz
        self.docker = raiz / "proyecto" / "docker"
        self.docker.mkdir(parents=True)
        for script in DOCKER.glob("*.ps1"):
            shutil.copy(script, self.docker / script.name)
        self.binarios = raiz / "bin"
        self.binarios.mkdir()
        falso = self.binarios / "docker"
        falso.write_text(FALSO.format(python=sys.executable), encoding="utf-8")
        falso.chmod(0o755)
        self.reglas = raiz / "reglas.json"
        self.registro = raiz / "docker.log"
        self.estado = self.docker / "estado"

    def entorno(self, reglas) -> dict[str, str]:
        self.reglas.write_text(json.dumps(reglas), encoding="utf-8")
        self.registro.write_text("", encoding="utf-8")
        entorno = {**os.environ, "PATH": f"{self.binarios}{os.pathsep}{os.environ['PATH']}",
                   "DOCKER_FALSO": str(self.reglas),
                   "DOCKER_FALSO_REGISTRO": str(self.registro), "BMS_BASE": "demo"}
        entorno.pop("LOCALAPPDATA", None)
        return entorno

    def correo(self, ajustes: bool = True, certificado: bool = True) -> None:
        carpeta = self.docker / "secretos" / "correo"
        carpeta.mkdir(parents=True, exist_ok=True)
        if ajustes:
            (carpeta / "correo_ajustes.json").write_text("{}", encoding="utf-8")
        if certificado:
            (carpeta / "correo_certificado.pem").write_text("de prueba", encoding="utf-8")

    def clave(self) -> None:
        (self.docker / "secretos").mkdir(parents=True, exist_ok=True)
        (self.docker / "secretos" / "anthropic_api_key.txt").write_text("de prueba\n",
                                                                        encoding="utf-8")

    def hoy_hecho(self) -> None:
        """La pasada del dia ya hecha hoy (asi no depende de la hora a la que corre la prueba)."""
        self.estado.mkdir(parents=True, exist_ok=True)
        (self.estado / "ciclo.json").write_text(json.dumps({"diaria": date.today().isoformat()}),
                                                encoding="utf-8")

    def correr(self, reglas=(), *argumentos: str) -> tuple[subprocess.CompletedProcess, list[str]]:
        proceso = subprocess.run(
            [PWSH, "-NoProfile", "-NonInteractive", "-File", str(self.docker / "ciclo.ps1"),
             *argumentos], env=self.entorno(list(reglas)), capture_output=True, text=True,
            timeout=300)
        return proceso, self.ordenes()

    def llamadas(self) -> list[dict]:
        texto = self.registro.read_text(encoding="utf-8") if self.registro.exists() else ""
        return [json.loads(linea) for linea in texto.splitlines()]

    def ordenes(self) -> list[str]:
        """Las ordenes, con el disco libre del latido como N."""
        ordenes = []
        for llamada in self.llamadas():
            orden = llamada["orden"]
            if orden.startswith(LATIDO):
                self.libre = int(orden.removeprefix(LATIDO).strip())
                orden = LATIDO + " N"
            ordenes.append(orden)
        return ordenes

    def registro_del_dia(self) -> str:
        fichero = self.estado / "registro" / f"ciclo-{date.today().isoformat()}.log"
        return fichero.read_text(encoding="utf-8") if fichero.exists() else ""

    def ciclo_json(self) -> dict:
        return json.loads((self.estado / "ciclo.json").read_text(encoding="utf-8"))


@pytest.fixture
def ciclo(tmp_path):
    if not _puerto_libre():
        pytest.skip("el puerto 8765 esta en uso (hay una consola en marcha)")
    return Ciclo(tmp_path)


def _con_disco(ciclo: Ciclo, ordenes: list[str]) -> None:
    """Los casos de abajo piden mas de 10 GiB libres en la maquina de las pruebas."""
    if ordenes[2:3] == [LATIDO + " N"] and ciclo.libre < modulo_ciclo.DISCO_MINIMO:
        pytest.skip("esta maquina tiene menos de 10 GiB libres")


# ============================================================ un ciclo


def test_una_automatica_entera_y_siempre_con_la_base_de_verdad(ciclo) -> None:
    ciclo.correo()
    ciclo.clave()
    ciclo.hoy_hecho()
    proceso, ordenes = ciclo.correr([["lectura siguiente", 0, ""],
                                     ["lectura tomar --automatica", 0, "17"]])
    assert proceso.returncode == 0, proceso.stdout + proceso.stderr
    _con_disco(ciclo, ordenes)
    assert ordenes == INICIO + [LATIDO + " N"] + CORREO + _automatica(17)
    # Nunca con los DATOS DE PRUEBA, aunque quien lo arranco tuviera BMS_BASE=demo.
    assert {c["base"] for c in ciclo.llamadas() if c["orden"].startswith("compose")} == {"bms"}
    # El latido deja ciclo.json (lo leen automatico.bat -Estado e iniciar.bat) y el registro.
    datos = ciclo.ciclo_json()
    visto = datetime.strptime(datos["visto_en"], "%Y-%m-%dT%H:%M:%SZ")
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((ahora - visto).total_seconds()) < 300
    assert datos["disco_libre_bytes"] == ciclo.libre and datos["diaria"] == date.today().isoformat()
    registro = ciclo.registro_del_dia()
    assert "Ciclo automatico." in registro and "lectura leer 17" not in registro


def test_la_pedida_en_la_app_espera_el_si_de_la_app(ciclo) -> None:
    ciclo.correo()
    ciclo.clave()
    ciclo.hoy_hecho()
    _proceso, ordenes = ciclo.correr([["lectura siguiente", 8, ""],
                                      ["lectura tomar /buzon/facturas --solo-pedida", 0, "21"]])
    _con_disco(ciclo, ordenes)
    assert ordenes[-7:] == [
        SIGUIENTE, "compose run --rm -T orden lectura tomar /buzon/facturas --solo-pedida",
        "compose up -d --wait --wait-timeout 180 salida",
        "compose run --rm -T lector lectura contar 21 /buzon/facturas --out /datos/out",
        "compose run --rm -T orden lectura esperar 21 --solo-app",
        "compose run --rm -T lector lectura leer 21 /buzon/facturas --out /datos/out",
        "compose run --rm -T orden lectura cerrar 21 --motivo interrumpida --si-viva"]


@pytest.mark.parametrize("codigo", [3, 9])
def test_sin_nada_que_leer_no_se_toma_nada(ciclo, codigo) -> None:
    ciclo.hoy_hecho()
    _proceso, ordenes = ciclo.correr([["lectura siguiente", codigo, ""]])
    _con_disco(ciclo, ordenes)
    assert ordenes == INICIO + [LATIDO + " N", SIGUIENTE]


@pytest.mark.parametrize("donde, codigo, hasta", [
    ("lectura contar", 7, "contar"), ("lectura autorizar", 3, "autorizar"),
    ("lectura tomar --automatica", 4, "tomar")])
def test_lo_que_no_sigue_no_lee_y_no_se_queda_vivo(ciclo, donde, codigo, hasta) -> None:
    ciclo.clave()
    ciclo.hoy_hecho()
    _proceso, ordenes = ciclo.correr([["lectura siguiente", 0, ""],
                                      [donde, codigo, ""],
                                      ["lectura tomar --automatica", 0, "17"]])
    _con_disco(ciclo, ordenes)
    lectura = ordenes[ordenes.index(SIGUIENTE):]
    if hasta == "tomar":
        # Ocupada: nada que cerrar (no hay numero).
        assert lectura == _automatica(17)[:2]
        return
    corte = [o for o in _automatica(17) if f"lectura {hasta}" in o][0]
    esperado = _automatica(17)
    assert lectura == esperado[:esperado.index(corte) + 1] + [esperado[-1]]


@pytest.mark.parametrize("codigo, tomar", [
    (0, "compose run --rm -T orden lectura tomar --automatica"),
    (8, "compose run --rm -T orden lectura tomar /buzon/facturas --solo-pedida")])
def test_sin_el_numero_de_la_lectura_no_se_arranca_nada(ciclo, codigo, tomar) -> None:
    """Si tomar acaba bien pero no dice un numero (la ultima linea de su salida normal), no hay
    lectura que contar, leer ni cerrar: nada mas."""
    ciclo.clave()
    ciclo.hoy_hecho()
    _proceso, ordenes = ciclo.correr([["lectura siguiente", codigo, ""],
                                      ["lectura tomar", 0, "Lectura 17 (de la app)."]])
    _con_disco(ciclo, ordenes)
    assert ordenes[ordenes.index(SIGUIENTE):] == [SIGUIENTE, tomar]


@pytest.mark.parametrize("que, motivo", [("clave", "clave"), ("salida", "salida")])
def test_sin_la_clave_o_sin_la_salida_la_lectura_termina_con_su_motivo(ciclo, que,
                                                                        motivo) -> None:
    """Sin el fichero de la clave no se arranca nada; sin la salida de la API, no se cuenta.
    La automatica queda fallida con su motivo (y la espera creciente de §5.2)."""
    if que == "salida":
        ciclo.clave()
    ciclo.hoy_hecho()
    _proceso, ordenes = ciclo.correr([["lectura siguiente", 0, ""],
                                      ["lectura tomar --automatica", 0, "17"],
                                      ["wait-timeout 180 salida", 1, ""]])
    _con_disco(ciclo, ordenes)
    lectura = ordenes[ordenes.index(SIGUIENTE):]
    cerrar = f"compose run --rm -T orden lectura cerrar 17 --motivo {motivo}"
    if que == "clave":
        assert lectura == _automatica(17)[:2] + [cerrar]
    else:
        assert lectura == _automatica(17)[:3] + [cerrar, _automatica(17)[-1]]
    assert not [o for o in ordenes if "lector" in o]


def test_sin_el_correo_configurado_no_se_trae_nada(ciclo) -> None:
    ciclo.hoy_hecho()
    _proceso, ordenes = ciclo.correr([["lectura siguiente", 3, ""]])
    _con_disco(ciclo, ordenes)
    assert not [o for o in ordenes if "correo" in o]


@pytest.mark.parametrize("ajustes, certificado", [(True, False), (False, True), (False, False)])
def test_el_correo_a_medias_lo_dice_y_no_trae(ciclo, ajustes, certificado) -> None:
    """La fase 1 de correo-configurar, o el certificado borrado: --fallo sin_configurar (que no
    apunta nada si el correo nunca llego a la base)."""
    ciclo.correo(ajustes=ajustes, certificado=certificado)
    ciclo.hoy_hecho()
    _proceso, ordenes = ciclo.correr([["lectura siguiente", 3, ""]])
    _con_disco(ciclo, ordenes)
    assert [o for o in ordenes if "correo" in o] == [
        "compose run --rm -T orden correo registrar --fallo sin_configurar"]


@pytest.mark.parametrize("regla, esperado", [
    (["salida_correo", 1, ""], ["compose up -d --wait --wait-timeout 120 salida_correo",
                                "compose run --rm -T orden correo registrar --fallo salida",
                                CORREO[2]]),
    (["run --rm -T correo", 1, ""], CORREO[:2] + [
        "compose run --rm -T orden correo registrar --fallo interno", CORREO[2]]),
    (["run --rm -T correo", 11, ""], CORREO),
    (["run --rm -T correo", 10, ""], CORREO)])
def test_el_correo_apunta_lo_que_no_pudo_y_registra_siempre(ciclo, regla, esperado) -> None:
    ciclo.correo()
    ciclo.hoy_hecho()
    _proceso, ordenes = ciclo.correr([regla, ["lectura siguiente", 3, ""]])
    _con_disco(ciclo, ordenes)
    assert ordenes == INICIO + [LATIDO + " N"] + esperado + [SIGUIENTE]


def test_la_pasada_del_dia_una_vez_al_dia_desde_las_seis(ciclo) -> None:
    antes = datetime.now()
    _proceso, ordenes = ciclo.correr([["lectura siguiente", 3, ""]])
    despues = datetime.now()
    if (antes.hour >= 6) != (despues.hour >= 6) or antes.date() != despues.date():
        pytest.skip("la prueba ha cruzado las 06:00 o la medianoche")
    _con_disco(ciclo, ordenes)
    diaria = "compose run --rm -T orden recalcular --diaria"
    if antes.hour < 6:
        assert diaria not in ordenes
        return
    assert ordenes == INICIO + [LATIDO + " N", diaria, SIGUIENTE]
    assert ciclo.ciclo_json()["diaria"] == date.today().isoformat()
    # La segunda vez, ya no; si falla, se vuelve a intentar en el ciclo siguiente.
    _proceso, ordenes = ciclo.correr([["lectura siguiente", 3, ""]])
    assert diaria not in ordenes
    (ciclo.estado / "ciclo.json").unlink()
    ciclo.correr([["recalcular", 1, ""], ["lectura siguiente", 3, ""]])
    assert "diaria" not in ciclo.ciclo_json()


def test_con_la_pausa_no_hace_nada(ciclo) -> None:
    ciclo.estado.mkdir(parents=True)
    (ciclo.estado / "automatico.pausa").write_text("En pausa.", encoding="utf-8")
    proceso, ordenes = ciclo.correr([])
    assert proceso.returncode == 0
    assert ordenes == ["info"]
    assert "En pausa" in ciclo.registro_del_dia()


def test_con_el_cerrojo_de_otro_se_salta_sin_esperar(ciclo) -> None:
    """Una lectura a mano, una copia, iniciar o restaurar tienen el cerrojo: el ciclo no espera."""
    ciclo.estado.mkdir(parents=True)
    fd = os.open(ciclo.estado / "ciclo.cerrojo", os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        inicio = time.monotonic()
        proceso, ordenes = ciclo.correr([])
        assert time.monotonic() - inicio < 60
    finally:
        os.close(fd)
    assert proceso.returncode == 0 and ordenes == ["info"]
    assert "este ciclo se salta" in ciclo.registro_del_dia()


def test_sin_la_imagen_no_hace_nada(ciclo) -> None:
    _proceso, ordenes = ciclo.correr([["image inspect", 1, ""]])
    assert ordenes == INICIO
    assert "iniciar.bat" in ciclo.registro_del_dia()


class _ConsolaDePrueba(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("X-BMS-Entorno", "demo")
        self.end_headers()
        self.wfile.write(b"consola")

    def log_message(self, *args):
        pass


def test_con_la_consola_en_datos_de_prueba_no_se_lee(ciclo) -> None:
    """El lector levantaria la salida y con ella la consola con los datos de verdad: con
    iniciar.bat -Demo en marcha, el ciclo trae y registra el correo pero no lee."""
    servidor = HTTPServer(("127.0.0.1", 8765), _ConsolaDePrueba)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        ciclo.correo()
        ciclo.hoy_hecho()
        _proceso, ordenes = ciclo.correr([["lectura siguiente", 0, ""]])
    finally:
        servidor.shutdown()
        servidor.server_close()
    _con_disco(ciclo, ordenes)
    assert ordenes == INICIO + [LATIDO + " N"] + CORREO
    assert "DATOS DE PRUEBA" in ciclo.registro_del_dia()


# ============================================================ el bucle


def _esperar(condicion, segundos: float) -> bool:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.5)
    return condicion()


def _con_disco_libre(ciclo: Ciclo) -> None:
    """El bucle mide el disco de la carpeta del proyecto: con menos de 10 GiB no lee nada."""
    if shutil.disk_usage(ciclo.docker).free < modulo_ciclo.DISCO_MINIMO:
        pytest.skip("esta maquina tiene menos de 10 GiB libres")


def _bucle(ciclo: Ciclo, reglas) -> subprocess.Popen:
    return subprocess.Popen(
        [PWSH, "-NoProfile", "-NonInteractive", "-File", str(ciclo.docker / "ciclo.ps1"),
         "-Bucle"], env=ciclo.entorno(reglas), stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)


def _pausar_y_reanudar(ciclo: Ciclo, proceso: subprocess.Popen, ciclos: int) -> None:
    """La pausa: la app lo ve una vez (latido --pausado), y nada mas; al quitarla, el ciclo
    vuelve enseguida (en la vuelta siguiente, como mucho 30 segundos)."""
    (ciclo.estado / "automatico.pausa").write_text("En pausa.", encoding="utf-8")
    assert _esperar(lambda: PAUSADO in ciclo.ordenes(), 45), ciclo.ordenes()
    hechas = len(ciclo.ordenes())
    time.sleep(3)
    assert len(ciclo.ordenes()) == hechas and proceso.poll() is None
    (ciclo.estado / "automatico.pausa").unlink()
    assert _esperar(lambda: ciclo.ordenes().count(SIGUIENTE) == ciclos, 45), ciclo.ordenes()


def test_el_bucle_no_sale_aunque_todo_falle_y_vuelve_tras_la_pausa(ciclo) -> None:
    """-Bucle: al empezar, el correo comprueba su alcance (--comprobar); con todo fallando sigue
    vivo; con la pausa no hace nada mas que decirlo a la app (latido --pausado, una vez); al
    quitarla, el ciclo va enseguida y, como la primera ronda no acabo bien, vuelve a comprobar."""
    _con_disco_libre(ciclo)
    ciclo.correo()
    ciclo.hoy_hecho()
    proceso = _bucle(ciclo, [["info", 0, ""], ["image inspect", 0, ""], ["salida_correo", 0, ""],
                             ["compose", 1, ""]])
    try:
        assert _esperar(lambda: SIGUIENTE in ciclo.ordenes(), 90), ciclo.ordenes()
        ordenes = ciclo.ordenes()
        assert TRAER_COMPROBAR in ordenes
        # Todo ha fallado: sigue vivo.
        time.sleep(2)
        assert proceso.poll() is None
        assert "--fallo interno" in " ".join(ordenes)
        _pausar_y_reanudar(ciclo, proceso, 2)
        assert proceso.poll() is None
        assert ciclo.ordenes().count(TRAER_COMPROBAR) == 2
        assert ciclo.ordenes().count(PAUSADO) == 1
    finally:
        proceso.kill()
        proceso.wait(timeout=30)


def test_el_bucle_comprueba_el_alcance_hasta_la_primera_ronda_buena(ciclo) -> None:
    """§2.3: el bucle pide correo traer --comprobar al empezar, y en cada ronda hasta que una
    acaba bien; despues, la ronda de siempre (el command del contenedor)."""
    _con_disco_libre(ciclo)
    ciclo.correo()
    ciclo.hoy_hecho()
    proceso = _bucle(ciclo, [["lectura siguiente", 3, ""]])
    try:
        assert _esperar(lambda: SIGUIENTE in ciclo.ordenes(), 90), ciclo.ordenes()
        assert TRAER_COMPROBAR in ciclo.ordenes()
        _pausar_y_reanudar(ciclo, proceso, 2)
        ordenes = ciclo.ordenes()
        segunda = ordenes[ordenes.index(SIGUIENTE) + 1:]
        assert CORREO[1] in segunda and TRAER_COMPROBAR not in segunda
        assert ordenes.count(TRAER_COMPROBAR) == 1 and proceso.poll() is None
    finally:
        proceso.kill()
        proceso.wait(timeout=30)


# ============================================================ la pausa y el cerrojo, por dentro


PRUEBA_COMUN = r"""
. (Join-Path $args[0] "comun.ps1")
$r = [ordered]@{}
$r["instante"] = Texto-Utc (Instante-Utc "2026-11-25T09:30:00Z")
$r["instante_fecha"] = Texto-Utc (Instante-Utc ([DateTime]::new(2026, 11, 25, 9, 30, 0, [DateTimeKind]::Utc)))
$r["instante_malo"] = $null -eq (Instante-Utc "ayer")
$r["disco"] = (Disco-Libre) -gt 0
# Sin la automatizacion puesta, la pausa no escribe en la base.
$r["pausa"] = Pausar-Automatico "prueba"
$r["pausa_fichero"] = Test-Path -LiteralPath $FicheroPausa
$r["pausa_ya_estaba"] = $PausaYaEstaba
Soltar-Cerrojo
# Una segunda pausa (de otro script) no la quita con -SiLaPuseYo.
$r["pausa2"] = Pausar-Automatico "otra"
$r["pausa2_ya_estaba"] = $PausaYaEstaba
Reanudar-Automatico -SiLaPuseYo
$r["sigue_en_pausa"] = Test-Path -LiteralPath $FicheroPausa
Soltar-Cerrojo
Reanudar-Automatico
$r["sin_pausa"] = -not (Test-Path -LiteralPath $FicheroPausa)
# Con el ciclo ya corriendo aqui, la pausa se dice a la app.
Set-Content -LiteralPath $FicheroCiclo -Value ('{"visto_en": "2000-01-01T00:00:00Z"}') -Encoding ascii
$env:BMS_BASE = "demo"
$r["pausa3"] = Pausar-Automatico "prueba"
$r["base_despues"] = $env:BMS_BASE
$r["aviso_en_pausa"] = $null -eq (Aviso-Del-Ciclo)
Soltar-Cerrojo
Reanudar-Automatico
$r["aviso_viejo"] = "" + (Aviso-Del-Ciclo)
Set-Content -LiteralPath $FicheroCiclo -Value ('{"visto_en": "' + (Texto-Utc (Get-Date)) + '"}') -Encoding ascii
$r["aviso_reciente"] = $null -eq (Aviso-Del-Ciclo)
# El cerrojo es de uno solo: otro proceso no lo toma mientras este lo tiene.
$r["cerrojo"] = Tomar-Cerrojo
$r["cerrojo_otra_vez"] = Tomar-Cerrojo
$r | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $args[0] "resultado.json") -Encoding ascii
$listo = Join-Path $args[0] "listo"
Set-Content -LiteralPath $listo -Value "si" -Encoding ascii
$hasta = (Get-Date).AddSeconds(60)
while ((Test-Path -LiteralPath $listo) -and (Get-Date) -lt $hasta) { Start-Sleep -Milliseconds 200 }
Soltar-Cerrojo
"""

OTRO = r"""
. (Join-Path $args[0] "comun.ps1")
$inicio = Get-Date
$tomado = Tomar-Cerrojo -Esperar 3
"" + $tomado + " " + [int]((Get-Date) - $inicio).TotalSeconds
"""


def test_la_pausa_el_cerrojo_y_el_aviso_del_ciclo(ciclo) -> None:
    (ciclo.raiz / "prueba.ps1").write_text(PRUEBA_COMUN, encoding="ascii")
    (ciclo.raiz / "otro.ps1").write_text(OTRO, encoding="ascii")
    entorno = ciclo.entorno([])
    proceso = subprocess.Popen([PWSH, "-NoProfile", "-NonInteractive", "-File",
                                str(ciclo.raiz / "prueba.ps1"), str(ciclo.docker)], env=entorno,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    listo = ciclo.docker / "listo"
    try:
        assert _esperar(listo.exists, 60), proceso.communicate(timeout=60)
        otro = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File",
                               str(ciclo.raiz / "otro.ps1"), str(ciclo.docker)], env=entorno,
                              capture_output=True, text=True, timeout=60)
    finally:
        listo.unlink(missing_ok=True)
        salida, errores = proceso.communicate(timeout=60)
    assert proceso.returncode == 0, salida + errores
    tomado, segundos = otro.stdout.split()
    assert tomado == "False" and int(segundos) >= 2
    r = json.loads((ciclo.docker / "resultado.json").read_text(encoding="ascii"))
    assert r["instante"] == r["instante_fecha"] == "2026-11-25T09:30:00Z"
    assert r["instante_malo"] is True and r["disco"] is True
    assert r["pausa"] is True and r["pausa_fichero"] is True and r["pausa_ya_estaba"] is False
    assert r["pausa2"] is True and r["pausa2_ya_estaba"] is True
    assert r["sigue_en_pausa"] is True and r["sin_pausa"] is True
    assert r["pausa3"] is True and r["base_despues"] == "demo"
    assert r["aviso_en_pausa"] is True
    assert "no corre desde" in r["aviso_viejo"] and r["aviso_reciente"] is True
    assert r["cerrojo"] is True and r["cerrojo_otra_vez"] is True
    # Solo la tercera pausa (con el ciclo ya corriendo aqui) lo dijo a la base, y a la de verdad.
    latidos = [c for c in ciclo.llamadas() if "latido" in c["orden"]]
    assert latidos == [{"orden": "compose run --rm -T orden ciclo latido --pausado --variante "
                                 "docker", "base": "bms"}]
