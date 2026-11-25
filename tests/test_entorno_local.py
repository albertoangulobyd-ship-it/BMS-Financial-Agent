"""El entorno local de Docker (paso 13), sin arrancar ningun contenedor.

Puertas que viven aqui (la de los contenedores de verdad esta en test_entorno_docker.py):

- docker-compose.yml: la consola y el lector solo estan en redes internas; la salida
  es el unico servicio con un pie fuera; el unico puerto publicado lo esta en
  127.0.0.1; todos con el sistema de ficheros de solo lectura, sin capacidades y sin
  escalar privilegios; la clave es un secreto que solo ve el lector y nunca una
  variable; el lector solo arranca a proposito y sale por el proxy;
- paso 18: el correo, en su propia red interna con un solo vecino (la salida del correo,
  que solo deja ir a Microsoft y sale por su propia red), sin la base ni la clave de la
  API, con solo sus dos secretos; la imagen da a bms cada punto de montaje en que se
  escribe;
- el Dockerfile: base fijada por etiqueta y digest, usuario sin privilegios,
  comprobacion de salud, dependencias con su hash;
- .dockerignore y .gitignore dejan fuera los datos, el buzon y la clave;
- los scripts de Windows: existen, dicen las cosas en claro, nunca borran el volumen
  ni llevan la clave; paso 18: el ciclo automatico (que no sale nunca por si mismo), la
  pausa y el cerrojo, las tareas, el correo, y ningun montaje de docker/secretos salvo
  docker/secretos/correo en el contenedor de las ordenes; con pwsh, cada script pasa el
  analizador de PowerShell (el ciclo de verdad contra un docker falso, en
  test_ciclo_docker.py);
- la consola solo escucha en 0.0.0.0 dentro de un contenedor, y ahi no lee PDF;
- la clave se lee de su fichero sin ensenarla;
- la copia de seguridad sale entera, comprobada y sin sobrescribir otra.
"""

from __future__ import annotations

import contextlib
import http.client
import importlib.metadata
import json
import re
import shutil
import sqlite3
import subprocess
import threading

import pytest
import yaml
from conftest import RAIZ

from bms_agent import config, copia, salida
from bms_agent.almacen import preparar
from bms_agent.cli import main
from bms_agent.serve import crear_servidor, en_contenedor, interfaz_permitida

DOCKER = RAIZ / "docker"
COMPOSE = DOCKER / "docker-compose.yml"
SERVICIOS = ("consola", "salida", "lector", "orden", "correo", "salida_correo")


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _redes(servicio: dict) -> set[str]:
    redes = servicio.get("networks") or {}
    return set(redes) if isinstance(redes, (dict, list)) else set()


# ============================================================ docker-compose.yml

def test_estan_los_seis_servicios_con_la_misma_imagen(compose) -> None:
    assert set(compose["services"]) == set(SERVICIOS)
    assert {s["image"] for s in compose["services"].values()} == {"bms-agent:local"}
    assert compose["services"]["consola"]["build"] == {"context": "..",
                                                       "dockerfile": "docker/Dockerfile"}


@pytest.mark.parametrize("nombre", SERVICIOS)
def test_cada_servicio_va_endurecido(compose, nombre) -> None:
    s = compose["services"][nombre]
    assert s["read_only"] is True
    assert s["cap_drop"] == ["ALL"] and "cap_add" not in s
    assert "no-new-privileges:true" in s["security_opt"]
    assert s.get("privileged") is not True and s.get("init") is True
    assert s.get("network_mode") in (None, "none")
    assert s.get("pid") is None and s.get("ipc") is None
    assert any(t.startswith("/tmp:") and "noexec" in t for t in s["tmpfs"])
    for volumen in s.get("volumes", []):
        assert "docker.sock" not in volumen
    assert s.get("user") in (None, "10001:10001")


def test_la_consola_y_el_lector_solo_estan_en_redes_internas(compose) -> None:
    redes, servicios = compose["networks"], compose["services"]
    assert _redes(servicios["consola"]) == {"red_consola"}
    assert _redes(servicios["lector"]) == {"red_lector"}
    assert servicios["orden"]["network_mode"] == "none" and not _redes(servicios["orden"])
    assert redes["red_consola"]["internal"] is True
    assert redes["red_lector"]["internal"] is True
    # Las redes con salida, y en cada una solo su salida (paso 18: la del correo, aparte).
    externas = {n for n, r in redes.items() if not (r or {}).get("internal")}
    assert externas == {"red_exterior", "red_exterior_correo"}
    con_salida = {n for n, s in servicios.items() if _redes(s) & externas}
    assert con_salida == {"salida", "salida_correo"}
    assert _redes(servicios["salida"]) == {"red_consola", "red_lector", "red_exterior"}
    # Paso 18: el correo, solo en su red interna; la salida del correo, en esa y en la suya
    # con salida, no en red_exterior (alli escucha la entrada a la consola) ni en la del lector.
    assert _redes(servicios["correo"]) == {"red_correo"}
    assert redes["red_correo"]["internal"] is True
    assert _redes(servicios["salida_correo"]) == {"red_correo", "red_exterior_correo"}
    vecinos = {red: {n for n, s in servicios.items() if red in _redes(s)} for red in redes}
    assert vecinos == {"red_consola": {"consola", "salida"}, "red_lector": {"lector", "salida"},
                       "red_exterior": {"salida"}, "red_correo": {"correo", "salida_correo"},
                       "red_exterior_correo": {"salida_correo"}}


def test_el_unico_puerto_es_el_de_la_consola_en_127_0_0_1(compose) -> None:
    publicados = {n: s.get("ports", []) for n, s in compose["services"].items()}
    assert publicados == {"consola": [], "salida": ["127.0.0.1:8765:8765"], "lector": [],
                          "orden": [], "correo": [], "salida_correo": []}
    for servicio in compose["services"].values():
        assert "expose" not in servicio


def test_la_salida_solo_deja_ir_a_la_api_y_escucha_en_la_red_del_lector(compose) -> None:
    s = compose["services"]["salida"]
    orden = s["command"]
    assert orden[0] == "salida"
    valor = {orden[i]: orden[i + 1] for i in range(1, len(orden), 2)}
    assert valor == {"--escuchar": "proxy:3128", "--permitir": "api.anthropic.com:443",
                     "--reenviar": "entrada:8765=consola:8765",
                     "--registro": "/registro/salida.log"}
    assert orden.count("--permitir") == 1
    salida.lista_blanca([valor["--permitir"]])
    # "proxy" es su nombre solo en la red del lector; "entrada", solo en la de fuera (por ahi
    # llega el puerto publicado): la consola no ve el proxy y el lector no ve la entrada.
    assert s["networks"]["red_lector"]["aliases"] == ["proxy"]
    assert s["networks"]["red_exterior"]["aliases"] == ["entrada"]
    assert not (s["networks"]["red_consola"] or {}).get("aliases")
    assert s["healthcheck"]["test"][-2:] == ["salud", "proxy:3128"]


def test_la_salida_del_correo_solo_deja_ir_a_microsoft_y_escucha_en_su_red(compose) -> None:
    """Paso 18 (D2, §1.3): la gemela de la salida de la API, con su lista (los dos hosts de
    Microsoft, salida.DESTINOS_CORREO), su registro y sin reenviar nada a la consola."""
    s = compose["services"]["salida_correo"]
    assert s["command"] == ["salida", "--escuchar", "proxy-correo:3128",
                            "--permitir", "login.microsoftonline.com:443",
                            "--permitir", "graph.microsoft.com:443",
                            "--registro", "/registro/salida-correo.log"]
    orden = s["command"]
    permitidos = tuple(orden[i + 1] for i, a in enumerate(orden) if a == "--permitir")
    assert permitidos == salida.DESTINOS_CORREO
    salida.lista_blanca(list(permitidos))
    # "proxy-correo" es su nombre solo en la red del correo; en la suya de fuera, ninguno.
    assert s["networks"]["red_correo"]["aliases"] == ["proxy-correo"]
    assert not (s["networks"]["red_exterior_correo"] or {}).get("aliases")
    assert s["healthcheck"]["test"][-2:] == ["salud", "proxy-correo:3128"]
    assert s["volumes"] == ["registro_correo:/registro"]
    assert s["restart"] == "unless-stopped" and "depends_on" not in s
    # La de la API sigue con su unica lista.
    assert compose["services"]["salida"]["command"].count("--permitir") == 1


def test_el_correo_solo_trae_por_su_salida_y_no_ve_la_base_ni_la_clave(compose) -> None:
    """Paso 18 (D1, §1.3): una ronda (correo traer) por la salida del correo, con sus dos
    volumenes; sin el volumen datos, sin el buzon y sin el registro de la API."""
    correo = compose["services"]["correo"]
    assert correo["profiles"] == ["correo"]
    assert correo["command"] == ["correo", "traer", "--ajustes", "/run/secrets/correo_ajustes",
                                 "--certificado-fichero", "/run/secrets/correo_certificado",
                                 "--estado", "/correo/estado", "--entrada", "/correo/entrada"]
    entorno = correo["environment"]
    assert entorno == {"HTTPS_PROXY": "http://proxy-correo:3128",
                       "https_proxy": "http://proxy-correo:3128", "NO_PROXY": "", "no_proxy": ""}
    assert correo["depends_on"] == {"salida_correo": {"condition": "service_healthy"}}
    assert correo["healthcheck"] == {"disable": True}
    assert correo["volumes"] == ["correo_estado:/correo/estado", "correo_entrada:/correo/entrada"]
    # Lo que corre el ciclo es lo mismo (docker/comun.ps1, $OrdenTraer).
    comun = (DOCKER / "comun.ps1").read_text(encoding="utf-8")
    traer = re.search(r"^\$OrdenTraer = @\((.*)\)$", comun, re.M).group(1)
    assert re.findall(r'"([^"]*)"', traer) == correo["command"]
    comprobar = re.search(r"^\$OrdenComprobar = @\((.*)\)$", comun, re.M).group(1)
    assert re.findall(r'"([^"]*)"', comprobar) == ["correo", "comprobar"] + correo["command"][2:8]


def test_el_lector_solo_arranca_a_proposito_y_sale_por_el_proxy(compose) -> None:
    lector = compose["services"]["lector"]
    assert lector["profiles"] == ["lector"]
    assert compose["services"]["orden"]["profiles"] == ["ordenes"]
    assert "profiles" not in compose["services"]["consola"]
    assert "profiles" not in compose["services"]["salida"]
    assert "profiles" not in compose["services"]["salida_correo"]
    entorno = lector["environment"]
    assert entorno["HTTPS_PROXY"] == entorno["https_proxy"] == "http://proxy:3128"
    assert entorno["NO_PROXY"] == entorno["no_proxy"] == ""
    assert "HTTP_PROXY" not in entorno and "ALL_PROXY" not in entorno
    assert lector["depends_on"]["salida"]["condition"] == "service_healthy"
    assert lector["healthcheck"] == {"disable": True}


def test_la_clave_es_un_secreto_que_solo_ve_el_lector(compose) -> None:
    servicios = compose["services"]
    # Paso 18: solo el lector ve la clave de la API, y solo el correo sus dos ficheros (de su
    # propia carpeta, docker\secretos\correo).
    assert {n: s["secrets"] for n, s in servicios.items() if s.get("secrets")} == {
        "lector": ["anthropic_api_key"], "correo": ["correo_ajustes", "correo_certificado"]}
    assert compose["secrets"] == {
        "anthropic_api_key": {"file": "./secretos/anthropic_api_key.txt"},
        "correo_ajustes": {"file": "./secretos/correo/correo_ajustes.json"},
        "correo_certificado": {"file": "./secretos/correo/correo_certificado.pem"}}
    assert servicios["lector"]["environment"]["BMS_CLAVE_API_FICHERO"] == \
        "/run/secrets/anthropic_api_key"
    texto = COMPOSE.read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY" not in texto and "sk-ant" not in texto
    for servicio in servicios.values():
        for nombre in (servicio.get("environment") or {}):
            assert not re.search(r"KEY|SECRET|PASSWORD", nombre, re.IGNORECASE) or \
                nombre == "BMS_CLAVE_API_FICHERO", nombre


def test_los_datos_van_en_un_volumen_y_el_buzon_se_lee_sin_escribir(compose) -> None:
    servicios = compose["services"]
    assert compose["volumes"] == {"datos": {}, "registro_salida": {}, "correo_estado": {},
                                  "correo_entrada": {}, "registro_correo": {}}
    assert servicios["consola"]["volumes"] == ["datos:/datos"]
    # La salida (el unico contenedor con internet) no ve los datos: solo su registro, que
    # vive en su volumen para que no se pierda con el contenedor (docker compose down).
    assert servicios["salida"]["volumes"] == ["registro_salida:/registro"]
    assert servicios["lector"]["volumes"] == ["datos:/datos", "../buzon:/buzon:ro"]
    # Paso 18: las ordenes registran lo del correo y lo quitan de su bandeja (el acuse); su
    # estado y el registro de su salida, solo para leerlos.
    assert servicios["orden"]["volumes"] == ["datos:/datos", "../buzon:/buzon:ro",
                                             "registro_salida:/registro:ro",
                                             "correo_entrada:/correo/entrada",
                                             "correo_estado:/correo/estado:ro",
                                             "registro_correo:/registro-correo:ro"]
    # Lo que ve la base, nunca el correo ni su salida.
    for nombre in ("correo", "salida_correo"):
        assert not [v for v in servicios[nombre]["volumes"]
                    if v.split(":")[0] in ("datos", "../buzon", "registro_salida")], nombre
    for nombre in ("consola", "lector", "orden"):
        assert servicios[nombre]["environment"]["BMS_DB"] == "/datos/${BMS_BASE:-bms}.sqlite3"


def test_la_consola_corre_en_modo_contenedor(compose) -> None:
    orden = compose["services"]["consola"]["command"]
    assert orden[:2] == ["serve", "--contenedor"] and "--puerto" in orden
    assert orden[orden.index("--puerto") + 1] == "8765"
    assert orden[orden.index("--out") + 1].startswith("/datos/")


def test_docker_compose_config_lo_acepta() -> None:
    if shutil.which("docker") is None:
        pytest.skip("no hay CLI de Docker en esta maquina")
    proceso = subprocess.run(["docker", "compose", "-f", str(COMPOSE), "config", "-q"],
                             capture_output=True, text=True, timeout=60)
    if proceso.returncode != 0 and "docker: 'compose' is not a docker command" in \
            proceso.stderr:
        pytest.skip("la CLI de Docker no trae compose")
    assert proceso.returncode == 0, proceso.stderr
    perfiles = subprocess.run(["docker", "compose", "-f", str(COMPOSE), "config", "--profiles"],
                              capture_output=True, text=True, timeout=60)
    assert set(perfiles.stdout.split()) == {"lector", "ordenes", "correo"}


# ============================================================ Dockerfile y dependencias

def _dockerfile() -> list[str]:
    """Las instrucciones del Dockerfile, con las lineas partidas ya unidas."""
    texto = (DOCKER / "Dockerfile").read_text(encoding="utf-8")
    sin_comentarios = [l for l in texto.splitlines() if not l.lstrip().startswith("#")]
    return [i.strip() for i in re.sub(r"\\\n", " ", "\n".join(sin_comentarios)).splitlines()
            if i.strip()]


def test_el_dockerfile_fija_la_base_por_etiqueta_y_digest() -> None:
    [desde] = [i for i in _dockerfile() if i.startswith("FROM ")]
    assert re.fullmatch(r"FROM python:3\.11\.\d+-slim-[a-z]+@sha256:[0-9a-f]{64}", desde), desde


def test_el_dockerfile_corre_sin_privilegios_y_con_salud() -> None:
    instrucciones = _dockerfile()
    usuarios = [i for i in instrucciones if i.startswith("USER ")]
    assert usuarios == ["USER 10001:10001"]
    assert instrucciones.index(usuarios[0]) > max(
        n for n, i in enumerate(instrucciones) if i.startswith(("RUN ", "COPY ")))
    [salud] = [i for i in instrucciones if i.startswith("HEALTHCHECK ")]
    assert '"salud", "127.0.0.1:8765"' in salud
    assert any(i.startswith("ENTRYPOINT [\"python\", \"-m\", \"bms_agent.cli\"]")
               for i in instrucciones)
    for i in instrucciones:
        if i.startswith(("ENV ", "ARG ")):
            assert not re.search(r"KEY|SECRET|TOKEN|PASSWORD", i, re.IGNORECASE), i
    [instalar] = [i for i in instrucciones if "pip install" in i]
    assert "--require-hashes" in instalar and "--only-binary=:all:" in instalar
    assert "requirements.txt" in instalar
    # Paso 18: tambien las del correo, en la misma orden (las mismas reglas: hash y ruedas).
    assert "-r /app/docker/requirements-correo.txt" in instalar
    assert ("COPY docker/requirements.txt docker/requirements-correo.txt /app/docker/"
            in instrucciones)


def test_cada_volumen_en_que_se_escribe_es_de_bms_en_la_imagen(compose) -> None:
    """Paso 18 (V1): un volumen nuevo toma el dueno de su carpeta en la imagen; si no existe,
    es de root y el usuario 10001 no puede escribir. Cada volumen con nombre que algun servicio
    monta con escritura tiene su punto de montaje en el mkdir y en el chown de la imagen."""
    [hecho] = [i for i in _dockerfile() if "mkdir -p" in i]
    creadas = re.search(r"mkdir -p ([^&]+)", hecho).group(1).split()
    de_bms = re.search(r"chown bms:bms ([^&]+)", hecho).group(1).split()
    escritos = set()
    for servicio in compose["services"].values():
        for volumen in servicio.get("volumes", []):
            partes = volumen.split(":")
            if partes[0] in compose["volumes"] and partes[2:] != ["ro"]:
                escritos.add(partes[1])
    assert escritos == {"/datos", "/registro", "/correo/estado", "/correo/entrada"}
    assert escritos <= set(creadas) and escritos <= set(de_bms)
    assert "/buzon" in creadas and "/buzon" not in de_bms


def _fijadas(fichero: str) -> dict[str, tuple[str, list[str]]]:
    """Las dependencias de un requirements de docker/: nombre normalizado -> (version, sha256
    de cada rueda). Cada una con version y al menos un hash."""
    texto = (DOCKER / fichero).read_text(encoding="utf-8")
    paquetes = {}
    for bloque in re.split(r"\n(?=[A-Za-z])", re.sub(r"(?m)^#.*\n", "", texto).strip()):
        cabeza = bloque.split()[0]
        nombre, version = cabeza.split("==")
        hashes = re.findall(r"--hash=sha256:([0-9a-f]{64})", bloque)
        assert hashes, nombre
        paquetes[nombre.lower().replace("_", "-")] = (version, hashes)
    return paquetes


def _instaladas_como_fijadas(paquetes: dict[str, tuple[str, list[str]]]) -> None:
    """Las mismas versiones con que pasan los tests."""
    for nombre, (version, _hashes) in paquetes.items():
        try:
            instalada = importlib.metadata.version(nombre)
        except importlib.metadata.PackageNotFoundError:
            continue
        assert instalada == version, (nombre, instalada, version)


def test_las_dependencias_van_con_version_y_hash() -> None:
    paquetes = _fijadas("requirements.txt")
    # Lo que pide pyproject.toml, y las mismas versiones con que pasan los tests.
    for nombre in ("anthropic", "pydantic", "pyyaml"):
        assert nombre in paquetes
    _instaladas_como_fijadas(paquetes)


def test_las_dependencias_del_correo_son_solo_de_docker() -> None:
    """Paso 18 (decision del dueno: el correo, solo en Docker): la firma del certificado de
    Microsoft (cryptography, con cffi y pycparser) va fijada con hash para las dos
    plataformas de la imagen en su propio fichero, que la instalacion nativa no ve:
    scripts/fijar_windows.py compara requirements.txt con Windows, y Windows no las lleva."""
    import tomllib

    correo = _fijadas("requirements-correo.txt")
    assert set(correo) == {"cryptography", "cffi", "pycparser"}
    # Las binarias, una rueda por plataforma (x86_64 y aarch64); pycparser es py3-none-any.
    for nombre, ruedas in (("cryptography", 2), ("cffi", 2), ("pycparser", 1)):
        assert len(set(correo[nombre][1])) == ruedas, nombre
    assert not set(correo) & set(_fijadas("requirements.txt"))
    windows = (RAIZ / "windows" / "requirements-windows.txt").read_text(encoding="utf-8")
    assert not re.search(r"(?im)^(cryptography|cffi|pycparser)==", windows)
    # En pyproject, un extra: el paquete no la necesita para nada mas que el correo.
    proyecto = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert not [d for d in proyecto["dependencies"] if d.startswith("cryptography")]
    [pide] = proyecto["optional-dependencies"]["correo"]
    minima = re.fullmatch(r"cryptography>=(\d+)", pide)
    assert minima and int(minima.group(1)) <= int(correo["cryptography"][0].split(".")[0])
    _instaladas_como_fijadas(correo)


def test_dockerignore_y_gitignore_dejan_fuera_los_datos_y_la_clave() -> None:
    reglas = [l.strip() for l in (RAIZ / ".dockerignore").read_text(encoding="utf-8")
              .splitlines() if l.strip() and not l.startswith("#")]
    # Primero todo fuera; luego solo lo que hace falta para la imagen.
    assert reglas[0] == "**"
    dentro = {r[1:] for r in reglas if r.startswith("!")}
    assert dentro == {"docker/requirements.txt", "docker/requirements-correo.txt",
                      "pyproject.toml", "README.md", "config/", "src/"}
    assert {"**/secretos/", "**/*.sqlite3*", "**/.env"} <= set(reglas)
    assert "config/tarifas.yaml" in reglas
    gitignore = (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert {"/buzon/", "/docker/secretos/*", "/datos/"} <= set(gitignore)
    # La carpeta de la clave existe con su explicacion, y nada mas en git.
    assert (DOCKER / "secretos" / "LEEME.txt").is_file()
    versionados = subprocess.run(["git", "-C", str(RAIZ), "ls-files", "docker/secretos"],
                                 capture_output=True, text=True).stdout.split()
    assert set(versionados) <= {"docker/secretos/LEEME.txt"}


# ============================================================ los scripts de Windows

SCRIPTS = ("iniciar", "parar", "importar", "leer-facturas", "copia", "restaurar", "persona",
           "ver-salida",
           # Revision final: la identidad de la empresa y las ordenes sueltas con el token.
           "empresa", "orden",
           # Paso 18: el ciclo automatico (ciclo.bat, uno a mano), sus tareas, y el correo.
           "ciclo", "automatico", "correo-configurar", "correo-certificado")
# Paso 18b: los que corren como administrador y no cargan comun.ps1 (sus pruebas, en
# tests/test_tunel_mac.py).
SIN_COMUN = ("proteger", "mac")


def _ps1(nombre: str) -> str:
    return (DOCKER / f"{nombre}.ps1").read_text(encoding="utf-8")


def _codigo(texto: str) -> str:
    """El script sin sus comentarios ni lo que va entre comillas: lo que de verdad se ejecuta
    (como en test_instalacion_nativa.py)."""
    sin_cadenas = re.sub(r'"(?:[^"`]|`.)*"|\'[^\']*\'', '""', texto)
    return "\n".join(linea.split("#", 1)[0] for linea in sin_cadenas.splitlines())


def _sin_comentarios(texto: str) -> str:
    return "\n".join(l for l in texto.splitlines() if not l.lstrip().startswith("#"))


def _en_orden(texto: str, pasos: list[str]) -> None:
    """Cada paso aparece en el texto despues del anterior."""
    desde = 0
    for paso in pasos:
        encontrado = texto.find(paso, desde)
        assert encontrado >= 0, (paso, texto[desde:desde + 200])
        desde = encontrado + len(paso)


def _funcion(texto: str, nombre: str) -> str:
    """El cuerpo de una funcion de un .ps1 (hasta la llave que la cierra, en su columna)."""
    inicio = texto.index(f"function {nombre}")
    return texto[inicio:texto.index("\n}\n", inicio) + 3]


@pytest.mark.parametrize("nombre", SCRIPTS)
def test_cada_script_tiene_su_bat_y_habla_claro(nombre) -> None:
    ps1 = (DOCKER / f"{nombre}.ps1").read_text(encoding="utf-8")
    bat = (DOCKER / f"{nombre}.bat").read_text(encoding="utf-8")
    assert f'-File "%~dp0{nombre}.ps1" %*' in bat and "-ExecutionPolicy Bypass" in bat
    assert '. "$PSScriptRoot\\comun.ps1"' in ps1
    # El ciclo no sale nunca por si mismo (Comprobar-Docker sale si Docker no esta): espera a
    # Docker con Docker-Listo.
    if nombre == "ciclo":
        assert "Comprobar-Docker" not in ps1 and "Docker-Listo" in ps1
    else:
        assert "Comprobar-Docker" in ps1
    # Windows PowerShell lee un .ps1 sin BOM como ANSI: nada fuera del ASCII.
    assert ps1.isascii() and bat.isascii()
    assert "sk-ant-" not in ps1
    assert not re.search(r"down\s+(-v|--volumes)", ps1)
    assert "Escribir" in ps1 or "Fallar" in ps1 or "Anotar" in ps1
    # Paso 18: lo que hay que leer al acabar (la nota para el informatico y el .cer, como esta lo
    # automatico, un ciclo a mano) deja la ventana abierta tambien si todo fue bien, como
    # comprobar.bat de la nativa; los demas, solo si algo fallo.
    lineas = [l.strip() for l in bat.splitlines()]
    if nombre in ("ciclo", "automatico", "correo-configurar", "correo-certificado"):
        assert lineas[-1] == "pause" and "if errorlevel 1 pause" not in lineas
    else:
        assert lineas[-1] == "if errorlevel 1 pause"


def test_iniciar_con_demo_usa_la_base_de_prueba_y_la_rehace() -> None:
    comun = (DOCKER / "comun.ps1").read_text(encoding="utf-8")
    iniciar = (DOCKER / "iniciar.ps1").read_text(encoding="utf-8")
    assert '$env:BMS_BASE = "demo"' in comun and '$env:BMS_BASE = "bms"' in comun
    assert '"demo", "crear", "--rehacer", "--db", "/datos/demo.sqlite3"' in iniciar
    assert "up -d consola salida" in iniciar
    # Paso 18: tambien la salida del correo (§1.3).
    assert "docker compose up -d consola salida salida_correo\n" in iniciar
    # Paso 15: se espera a la consola (no depende de lo construido) y se abre la app en su
    # ventana de Edge; si la app no esta construida, la consola, de reserva.
    assert '$base = "http://127.0.0.1:8765"' in iniciar
    assert '$consola_url = $base + "/consola"' in iniciar and "-Uri $consola_url" in iniciar
    assert "$direccion = Direccion-De-La-App $base" in iniciar
    assert "Abrir-App $direccion" in iniciar


def test_el_token_va_por_el_entorno_y_no_en_la_orden() -> None:
    comun = (DOCKER / "comun.ps1").read_text(encoding="utf-8")
    assert "-AsSecureString" in comun and "ZeroFreeBSTR" in comun
    assert "run --rm -T -e BMS_TOKEN orden" in comun
    assert "--token" not in "".join((DOCKER / f"{n}.ps1").read_text(encoding="utf-8")
                                    for n in SCRIPTS)


def test_leer_facturas_cuenta_antes_y_pide_que_si() -> None:
    texto = (DOCKER / "leer-facturas.ps1").read_text(encoding="utf-8")
    contar = texto.index("lector lectura contar")
    preguntar = texto.index("orden lectura esperar")
    leer = texto.index("lector lectura leer")
    assert contar < preguntar < leer
    # Paso 17: el si lo espera `lectura esperar` (de la app o escrito en la ventana); "si",
    # "s" y "si" con tilde valen (lectura.es_si, como Es-Si de comun.ps1); otra cosa no lee.
    assert "Read-Host" not in texto and "extract" not in texto


def test_importar_conoce_cada_carpeta_del_buzon() -> None:
    """Una carpeta del buzon por cada tipo que se puede importar (cada mapeo de
    config/importacion): sin las del maestro, la base de verdad no tendria Objetos, tarifas
    ni ciclos, y las reglas del planning, las tarifas y las PO no tendrian con que mirar."""
    texto = (DOCKER / "importar.ps1").read_text(encoding="utf-8")
    pares = re.findall(r'"([a-z\\]+)"\s*=\s*@\("([a-z_]+)", "([a-z_]+)"\)', texto)
    tipos = [(f, t) for _c, f, t in pares]
    importables = set()
    for mapeo in (RAIZ / "config" / "importacion").glob("*.yaml"):
        datos = yaml.safe_load(mapeo.read_text(encoding="utf-8"))
        importables.add((datos["fuente"], datos["tipo"]))
    assert set(tipos) == importables and len(tipos) == len(importables)
    assert len({c for c, _f, _t in pares}) == len(pares)
    # En el orden en que unos usan lo que traen otros.
    antes = [("exact", "proveedores"), ("exact", "clientes"), ("maestro_csv", "objetos"),
             ("maestro_csv", "recursos")]
    despues = [("maestro_csv", "tarifas"), ("maestro_csv", "ciclos"), ("trnsprnt", "planning"),
               ("po_csv", "ordenes_compra"), ("exact", "facturas_venta"),
               ("exact", "pagos_exact")]
    assert max(tipos.index(t) for t in antes) < min(tipos.index(t) for t in despues)
    assert tipos.index(("po_csv", "ordenes_compra")) < tipos.index(("po_csv", "modificaciones_po"))
    assert tipos.index(("exact", "facturas_venta")) < tipos.index(("exact", "pagos_exact"))


def test_importar_solo_saca_del_buzon_lo_que_ha_entrado() -> None:
    """La decision va por el codigo de salida de `importar` (cli.SALIDA_RECHAZADA y
    SALIDA_PARCIAL), no por que no haya habido un error."""
    from bms_agent.cli import SALIDA_PARCIAL, SALIDA_RECHAZADA

    texto = (DOCKER / "importar.ps1").read_text(encoding="utf-8")
    assert f"$rechazada = {SALIDA_RECHAZADA}" in texto and f"$parcial = {SALIDA_PARCIAL}" in texto
    mover = texto.index("Move-Item")
    assert texto.index('if ($codigo -eq 0 -or $codigo -eq $parcial)') < mover
    assert mover < texto.index("elseif ($codigo -eq $rechazada)")


def test_la_pasada_del_dia_la_hacen_iniciar_e_importar() -> None:
    for nombre in ("iniciar", "importar"):
        texto = (DOCKER / f"{nombre}.ps1").read_text(encoding="utf-8")
        assert "orden recalcular --diaria" in texto, nombre
    iniciar = (DOCKER / "iniciar.ps1").read_text(encoding="utf-8")
    assert iniciar.index("recalcular --diaria") < iniciar.index("up -d consola salida")


def test_leer_facturas_no_lee_nada_con_demo() -> None:
    texto = (DOCKER / "leer-facturas.ps1").read_text(encoding="utf-8")
    assert texto.index("if ($Demo)") < texto.index("orden lectura tomar")
    assert "Elegir-Base -Demo" not in texto


def test_persona_pide_el_rol_y_no_cambia_el_de_quien_ya_existe() -> None:
    texto = (DOCKER / "persona.ps1").read_text(encoding="utf-8")
    assert re.search(r'\[Parameter\(Mandatory = \$true\)\]\[ValidateSet\([^)]*\)\]\[string\]\$Rol\s*\)',
                     texto)
    assert "Select-String" not in texto and "usuario listar" not in texto
    asegurar = texto.index('"usuario", "asegurar", $Nombre, "--rol", $Rol')
    assert asegurar < texto.index("if ($codigo -eq 3)") < texto.index('"usuario", "token"')


def test_usuario_asegurar_no_da_otro_rol_a_quien_ya_existe(tmp_path, capsys) -> None:
    from bms_agent.cli import SALIDA_OTRO_ROL

    db = str(tmp_path / "datos" / "bms.sqlite3")
    assert main(["usuario", "asegurar", "Bram", "--rol", "administrador", "--db", db]) == 0
    assert main(["usuario", "asegurar", "Bram", "--rol", "administrador", "--db", db]) == 0
    # Pedir solo consulta para quien ya es administrador: no se cambia nada.
    assert main(["usuario", "asegurar", "Bram", "--rol", "consulta", "--db", db]) == \
        SALIDA_OTRO_ROL
    assert "ya existe con administrador" in capsys.readouterr().err
    # El nombre es el exacto: "Bra" no es "Bram", y es otra persona.
    assert main(["usuario", "asegurar", "Bra", "--rol", "consulta", "--db", db]) == 0
    capsys.readouterr()
    assert main(["usuario", "listar", "--db", db]) == 0
    listado = capsys.readouterr().out
    assert re.search(r"Bram\s+persona\s+administrador\n", listado)
    assert re.search(r"Bra\s+persona\s+consulta\n", listado)


# ============================================================ paso 18: funcionar solo


def test_los_codigos_del_correo_son_los_de_la_cli_y_solo_de_docker() -> None:
    """Como acaban correo traer y correo comprobar: los mismos numeros en la CLI y en
    docker/comun.ps1; la nativa no trae el correo (decision del dueno) y no los tiene."""
    from bms_agent import cli

    comun = _ps1("comun")
    assert f"$CorreoSinConfigurar = {cli.CORREO_SIN_CONFIGURAR}\n" in comun
    assert f"$CorreoFallo = {cli.CORREO_FALLO}\n" in comun
    nativa = (RAIZ / "windows" / "comun.ps1").read_text(encoding="utf-8")
    assert "$Correo" not in nativa
    assert not list((RAIZ / "windows").glob("ciclo.*"))
    assert not list((RAIZ / "windows").glob("automatico.*"))
    assert not list((RAIZ / "windows").glob("correo-*"))


def test_ningun_script_monta_la_carpeta_de_secretos_salvo_la_del_correo_en_orden() -> None:
    """S5: la clave de la API vive en docker/secretos. Ningun -v de un script la monta en ningun
    servicio; la unica carpeta de secretos que se monta es docker/secretos/correo, solo en el
    contenedor de las ordenes (sin red) y solo para las ordenes del certificado y de los
    ajustes (§2.4)."""
    montajes = []
    for script in sorted(DOCKER.glob("*.ps1")):
        codigo = _sin_comentarios(script.read_text(encoding="utf-8"))
        for m in re.finditer(r'-v\s+"([^"]+)"\s+(\S+)', codigo):
            montajes.append((script.name, m.group(1), m.group(2)))
    con_secretos = [(n, v, s) for n, v, s in montajes if "secretos" in v.lower()]
    assert con_secretos == [("comun.ps1", "${CarpetaSecretosCorreo}:/secretos-correo", "orden")]
    assert '$CarpetaSecretosCorreo = Join-Path $PSScriptRoot "secretos\\correo"\n' in _ps1("comun")
    # Los demas montajes son los de siempre (la copia), y ninguno con una ruta de secretos.
    otros = {v.split(":")[0] for _n, v, _s in montajes} - {"${CarpetaSecretosCorreo}"}
    assert otros == {"${carpeta}", "${destinoCompleto}", "${origenCompleto}"}
    orden = _funcion(_ps1("comun"), "Orden-Secretos-Correo")
    assert "orden @Argumentos --carpeta /secretos-correo" in orden
    # Y solo los dos scripts del correo la usan.
    usan = {s.stem for s in DOCKER.glob("*.ps1") if "Orden-Secretos-Correo" in
            _sin_comentarios(s.read_text(encoding="utf-8"))} - {"comun"}
    assert usan == {"correo-configurar", "correo-certificado"}


def test_lo_que_escriben_el_ciclo_y_la_pausa_esta_en_docker_estado() -> None:
    """La pausa, el cerrojo, ciclo.json y el registro del ciclo, en docker/estado (fuera de git);
    el ciclo no nombra ninguna otra ruta del proyecto (lo de secretos solo lo mira)."""
    comun = _ps1("comun")
    rutas = dict(re.findall(r'^\$(\w+) = Join-Path \$PSScriptRoot "([^"]+)"$', comun, re.M))
    assert rutas == {
        "CarpetaEstado": "estado", "FicheroPausa": "estado\\automatico.pausa",
        "FicheroCerrojo": "estado\\ciclo.cerrojo", "FicheroCiclo": "estado\\ciclo.json",
        "CarpetaRegistroCiclo": "estado\\registro", "CarpetaSecretosCorreo": "secretos\\correo",
        "FicheroAjustesCorreo": "secretos\\correo\\correo_ajustes.json",
        "FicheroCertificadoCorreo": "secretos\\correo\\correo_certificado.pem",
        "FicheroClaveApi": "secretos\\anthropic_api_key.txt"}
    for nombre in ("ciclo", "automatico"):
        assert "Join-Path $PSScriptRoot" not in _sin_comentarios(_ps1(nombre)).replace(
            'Join-Path $PSScriptRoot "ciclo.ps1"', "").replace(
            'Join-Path $PSScriptRoot "comun.ps1"', ""), nombre
    for funcion in ("Tomar-Cerrojo", "Pausar-Automatico", "Reanudar-Automatico", "Anotar"):
        assert "$PSScriptRoot" not in _funcion(comun, funcion), funcion
    assert "/docker/estado/" in (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_el_cerrojo_y_la_pausa() -> None:
    """§4.4: el cerrojo es un fichero abierto en exclusiva (si el proceso muere, Windows lo
    suelta); la pausa espera como mucho 2 minutos al cerrojo y la app la ve."""
    comun = _ps1("comun")
    tomar = _funcion(comun, "Tomar-Cerrojo")
    assert "[System.IO.File]::Open($FicheroCerrojo, [System.IO.FileMode]::OpenOrCreate, " \
           "[System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)" in tomar
    pausar = _funcion(comun, "Pausar-Automatico")
    assert pausar.index("Set-Content -LiteralPath $FicheroPausa") < pausar.index(
        "Tomar-Cerrojo -Esperar 120") < pausar.index("ciclo latido --pausado --variante docker")
    assert '$env:BMS_BASE = "bms"' in pausar
    # Sin el cerrojo, con -SoloSiSigue se quita la pausa que puso esta llamada (y solo esa).
    sin_cerrojo = pausar[pausar.index("Tomar-Cerrojo -Esperar 120"):]
    sin_cerrojo = sin_cerrojo[:sin_cerrojo.index("return $false")]
    assert ("if ($SoloSiSigue -and -not $script:PausaYaEstaba) {\n"
            "            Remove-Item -LiteralPath $FicheroPausa") in sin_cerrojo.replace("\r\n",
                                                                                   "\n")
    reanudar = _funcion(comun, "Reanudar-Automatico")
    assert "Remove-Item -LiteralPath $FicheroPausa" in reanudar
    assert "$SiLaPuseYo -and $script:PausaYaEstaba" in reanudar
    # Ni la pausa ni el cerrojo salen del script: quien los llama decide.
    for funcion in ("Tomar-Cerrojo", "Soltar-Cerrojo", "En-Pausa", "Pausar-Automatico",
                    "Reanudar-Automatico", "Docker-Listo", "Imagen-Lista", "Anotar",
                    "Compose-Anotado", "Disco-Libre", "Leer-Ciclo", "Instante-Utc",
                    "Texto-Utc", "Entorno-De-La-Consola", "Cerrar-Lectura", "Elegir-Base",
                    "Tarea-Del-Ciclo", "Automatizacion-Puesta"):
        cuerpo = _codigo(_funcion(comun, funcion))
        assert "Fallar" not in cuerpo and not re.search(r"\bexit\b", cuerpo), funcion


@pytest.mark.parametrize("nombre, antes, llamada", [
    ("parar", "docker compose down\n", '"parar.bat"'),
    ("restaurar", "docker compose down | Out-Host", '"restaurar.bat" -SoloSiSigue')])
def test_parar_y_restaurar_pausan_antes_de_parar_nada(nombre, antes, llamada) -> None:
    """O4: sin la pausa, el ciclo (y el depends_on de compose) lo volverian a arrancar en
    minutos. Si no se puede esperar a lo que esta en marcha, no se toca nada: restaurar ni
    siquiera deja la pausa (si no, al volver a abrirlo no la quitaria); parar, si."""
    texto = _sin_comentarios(_ps1(nombre))
    pausa = texto.index(f"if (-not (Pausar-Automatico {llamada})) {{")
    assert pausa < texto.index(antes)
    assert texto.index("Fallar", pausa) < texto.index(antes)
    if nombre == "restaurar":
        # Vuelve al terminar bien (si la pausa la puso el); si algo falla, se queda en pausa.
        assert texto.index("db verificar") < texto.index("Reanudar-Automatico -SiLaPuseYo")
    else:
        assert "Reanudar-Automatico" not in texto
        assert "automatico.bat -Reanudar" in texto


def test_iniciar_no_se_queda_colgado_y_reanuda() -> None:
    """§4.4: con la consola ya en marcha con la base de verdad y la nuestra, solo se abre (sin
    parar nada); si no, el cerrojo esperando como mucho 1 minuto, y lo de siempre."""
    texto = _sin_comentarios(_ps1("iniciar"))
    rapido = texto[texto.index('if (-not $Demo -and (Entorno-De-La-Consola) -eq "") {'):
                   texto.index("Tomar-Cerrojo -Esperar 60")]
    assert '$enMarcha -contains "consola" -and $enMarcha -contains "salida"' in rapido
    assert "Reanudar-Automatico" in rapido and "Abrir-App $direccion" in rapido
    assert "exit 0" in rapido
    for nada in ("compose down", "compose up", "Tomar-Cerrojo -Esperar"):
        assert nada not in rapido, nada
    # La pasada del dia, si el ciclo no la ha hecho hoy, solo con el cerrojo libre y sin
    # esperarlo: no se pisa con un ciclo que esta leyendo.
    assert re.search(r'\$ciclo\.diaria\) -ne \$hoy\) -and \(Tomar-Cerrojo\)\) \{\n'
                     r'\s+docker compose run --rm -T orden recalcular --diaria \*> \$null\n'
                     r'\s+Soltar-Cerrojo\n', rapido.replace("\r\n", "\n"))
    assert rapido.count("recalcular") == 1
    cerrojo = texto.index("Tomar-Cerrojo -Esperar 60")
    assert cerrojo < texto.index("docker compose down") < texto.index(
        "up -d consola salida salida_correo") < texto.index("Soltar-Cerrojo", cerrojo) < \
        texto.rindex("Reanudar-Automatico")
    assert texto.index("Fallar", cerrojo) < texto.index("docker compose down")
    comun = _ps1("comun")
    assert '-ieq "X-BMS-Entorno"' in _funcion(comun, "Entorno-De-La-Consola")
    assert "ps --status running --services" in _funcion(comun, "Servicios-En-Marcha")


@pytest.mark.parametrize("nombre, primero", [
    ("leer-facturas", "docker compose run --rm -T orden lectura tomar"),
    ("copia", "docker compose run --rm -T -v \"${destinoCompleto}:/copia\" orden copia")])
def test_leer_facturas_y_copia_esperan_al_ciclo(nombre, primero) -> None:
    texto = _sin_comentarios(_ps1(nombre))
    cerrojo = texto.index("Tomar-Cerrojo -Esperar 900")
    assert cerrojo < texto.index(primero)
    assert texto.index("Fallar", cerrojo) < texto.index(primero)


def test_automatico_pone_las_tareas_sin_limite_y_comprueba_la_cuenta() -> None:
    """§4.2 (Docker): el bucle al iniciar sesion (2 minutos) y el vigilante cada 15, una sola
    instancia, sin limite de tiempo (PT0S: las 72 horas de por defecto cortarian el bucle),
    reintentos; solo con la sesion iniciada y sin guardar contrasena; la pantalla bloqueada;
    y avisa de la cuenta (local, estandar, sin caducidad, en docker-users)."""
    texto = _sin_comentarios(_ps1("automatico"))
    assert "[ValidateRange(5, 60)][int]$Minutos = 5" in texto
    assert ('$powershell = Join-Path $env:SystemRoot '
            '"System32\\WindowsPowerShell\\v1.0\\powershell.exe"') in texto
    assert ("'-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File \"' "
            "+ $ciclo + '\" -Bucle -Minutos ' + $Minutos") in texto
    assert '$ciclo = Join-Path $PSScriptRoot "ciclo.ps1"' in texto
    # La carpeta de trabajo del bucle, fuera del proyecto (asi se puede sustituir la carpeta).
    assert ("New-ScheduledTaskAction -Execute $powershell -Argument $argumentos "
            '-WorkingDirectory (Join-Path $env:SystemRoot "System32")') in texto
    assert "-WorkingDirectory $PSScriptRoot" not in texto
    # Con Windows Terminal, -WindowStyle Hidden no oculta nada: -Instalar ofrece la consola de
    # Windows para esa cuenta (lo que pone Configuracion > Para programadores > Terminal).
    assert '$ClaveTerminal = "HKCU:\\Console\\%%Startup"' in texto
    assert '$ConsolaDeWindows = "{B23D10C0-E52E-411E-9D5B-C09FDF709C7D}"' in texto
    poner = _funcion(texto, "Poner-La-Consola")
    assert '@("DelegationConsole", "DelegationTerminal")' in poner
    assert "-PropertyType String -Value $ConsolaDeWindows -Force" in poner
    assert "New-Item -Path $ClaveTerminal -ErrorAction Stop" in poner
    assert "-Force" not in poner[:poner.index("foreach")]
    instalar = texto[texto.index("if ($Instalar) {"):texto.index("if ($Quitar) {")]
    assert instalar.index("if (-not (Terminal-Es-La-Consola)) {") < instalar.index(
        "(Es-Si $respuesta) -and (Poner-La-Consola)") < instalar.index("Register-ScheduledTask")
    assert "New-ScheduledTaskTrigger -AtLogOn -User $usuario" in texto
    assert '$alEntrar.Delay = "PT2M"' in texto
    assert "-RepetitionInterval (New-TimeSpan -Minutes 15)" in texto
    assert "-RepetitionDuration" not in texto
    ajustes = texto[texto.index("$ajustes = New-ScheduledTaskSettingsSet"):]
    ajustes = ajustes[:ajustes.index("\n", ajustes.index("$ajustes.ExecutionTimeLimit")) + 1]
    for pieza in ("-MultipleInstances IgnoreNew", "-RestartCount 3",
                  "-RestartInterval (New-TimeSpan -Minutes 5)",
                  '$ajustes.ExecutionTimeLimit = "PT0S"'):
        assert pieza in ajustes, pieza
    assert ("New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive "
            "-RunLevel Limited") in texto
    assert len(re.findall(r"(?<![\w-])Register-ScheduledTask -TaskName", texto)) == 2
    assert not re.search(r"-Password\b|-RunLevel Highest|LogonType (Password|S4U)|"
                         r"Read-Host[^\n]*-AsSecureString", _codigo(texto))
    assert ('New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot '
            '"System32\\rundll32.exe") -Argument "user32.dll,LockWorkStation"') in texto
    for pieza in ("Get-LocalUser", "PasswordExpires", "PasswordNeverExpires", "PrincipalSource",
                  '"S-1-5-32-544"', '"\\docker-users"', '"System32\\whoami.exe"'):
        assert pieza in texto, pieza
    # Las acciones, con la pausa y el cerrojo de comun.ps1; -Estado sin abrir la base.
    assert 'Pausar-Automatico "automatico.bat -Pausar"' in texto and "Reanudar-Automatico" in texto
    estado = texto[texto.index("# -Estado") if "# -Estado" in texto else texto.index(
        'Escribir "Lo automatico (Docker):"'):]
    assert "compose run" not in estado and "Leer-Ciclo" in estado
    assert "$FicheroAjustesCorreo" in estado and "caduca_en" in estado
    assert "Get-ScheduledTaskInfo" in estado and "LastTaskResult" in estado
    comun = _ps1("comun")
    assert '$TareaCiclo = "BMS Finanzas - ciclo (Docker)"' in comun
    assert '$TareaBloquear = "BMS Finanzas - bloquear (Docker)"' in comun


def test_el_ciclo_no_sale_nunca_y_hace_sus_pasos_en_su_orden() -> None:
    """§4.1 y §4.2 (O9): -Bucle es un bucle sin fin que no llama a nada que salga (Fallar,
    Comprobar-Docker, Asegurar-Imagen, exit); espera a Docker hasta 10 minutos. Cada ciclo: la
    pausa, el cerrojo sin esperar, otra vez la pausa, el latido con el disco (con poco, nada
    mas), el correo y registrar, la pasada del dia y la lectura."""
    texto = _ps1("ciclo")
    codigo = _codigo(texto)
    for prohibido in ("Fallar", "Comprobar-Docker", "Asegurar-Imagen", "Pedir-Token",
                      "BMS_TOKEN"):
        assert prohibido not in codigo, prohibido
    assert not re.search(r"\bexit\b", codigo)
    assert "while ($true) {" in texto and "Docker-Listo 600" in texto
    bucle = texto[texto.index("while ($true) {"):]
    assert "} catch {" in bucle and "Start-Sleep -Seconds 30" in bucle
    # Lo unico que lo cierra: una version nueva de ciclo.ps1 o comun.ps1 (lo que tiene en
    # memoria es la de antes), mirado entre dos ciclos; el vigilante lo vuelve a arrancar.
    assert texto.index("$programa = Huella-Del-Programa") < texto.index("while ($true) {")
    _en_orden(bucle, ["try {", "if ((Huella-Del-Programa) -ne $programa) {", "break",
                      "if (En-Pausa) {"])
    assert len(re.findall(r"\bbreak\b", codigo)) == 1
    huella = _funcion(texto, "Huella-Del-Programa")
    assert '@($PSCommandPath, (Join-Path $PSScriptRoot "comun.ps1"))' in huella
    ciclo = _funcion(texto, "Un-Ciclo")
    pasos = ["if (En-Pausa) {", "if (-not (Tomar-Cerrojo)) {", "if (En-Pausa) {",
             '"ciclo", "latido", "--variante", "docker"', "--disco-libre",
             "$libre -lt $DiscoMinimo", '"registrar", "--fallo", "disco"',
             "Pasada-Del-Correo", "Pasada-Del-Dia", "Lectura-Del-Ciclo"]
    posiciones = []
    desde = 0
    for paso in pasos:
        desde = ciclo.index(paso, desde)
        posiciones.append(desde)
    assert posiciones == sorted(posiciones)
    assert "Tomar-Cerrojo -Esperar" not in ciclo
    # Cada paso en su propio try: sin correo se puede leer lo que ya hay.
    for paso in ("Pasada-Del-Correo", "Pasada-Del-Dia", "Lectura-Del-Ciclo"):
        assert f"try {{ {paso} }} catch {{" in ciclo, paso
    comun = _ps1("comun")
    assert "$DiscoMinimo = 10GB\n" in comun
    from bms_agent import ciclo as modulo_ciclo
    assert modulo_ciclo.DISCO_MINIMO == 10 * 1024 ** 3
    disco = _funcion(comun, "Disco-Libre")
    assert "Get-PSDrive" in disco and "$env:LOCALAPPDATA" in disco


def test_el_correo_del_ciclo_registra_siempre_y_apunta_lo_que_no_pudo() -> None:
    """§4.1 paso 3 (y lo que dejo el paso 10): la ronda por la salida del correo; si la salida
    no arranca, --fallo salida; si el correo no dice como acabo, --fallo interno; y registrar
    siempre, tambien si no trajo nada. Sin el correo configurado, no se trae nada."""
    texto = _ps1("ciclo")
    correo = _funcion(texto, "Pasada-Del-Correo")
    orden = ["Test-Path -LiteralPath $FicheroAjustesCorreo",
             '"registrar", "--fallo", "sin_configurar"',
             '"up", "-d", "--wait", "--wait-timeout", "120", "salida_correo"',
             '"registrar", "--fallo", "salida"', '"run", "--rm", "-T", "correo"',
             "@(0, $CorreoSinConfigurar, $CorreoFallo) -notcontains $traer.Codigo",
             '"registrar", "--fallo", "interno"',
             '"registrar", "--entrada", "/correo/entrada", "--estado", "/correo/estado"']
    posiciones = [correo.index(p) for p in orden]
    assert posiciones == sorted(posiciones)
    # Registrar va fuera de las ramas: tambien cuando la salida no arranco.
    final = correo[correo.rindex("    }\n"):]
    assert '"registrar", "--entrada"' in final
    # Al empezar el bucle, comprueba el alcance (§2.3).
    assert "$OrdenTraer + @(\"--comprobar\")" in correo
    assert "$PrimeraRonda = $Bucle.IsPresent" in texto


def test_la_lectura_del_ciclo_no_escribe_nunca_que_si() -> None:
    """§4.1 paso 5: la pedida en la app con el si de la app (esperar --solo-app); la automatica
    con la autorizacion vigente (autorizar). Contar y leer una vez cada uno, nunca extract, y
    la lectura no se queda viva."""
    texto = _ps1("ciclo")
    codigo = _sin_comentarios(texto)
    assert '"si"' not in codigo.lower() and "extract" not in codigo
    for orden in ("contar", "leer", "autorizar", "esperar"):
        assert len(re.findall(rf'"lectura", "{orden}"', codigo)) == 1, orden
    assert '"lectura", "esperar", $Solicitud, "--solo-app"' in codigo
    leer = _funcion(texto, "Leer-Con-Salida")
    pasos = ["Test-Path -LiteralPath $FicheroClaveApi", 'Cerrar-Lectura $Solicitud "clave"',
             "try {", '"up", "-d", "--wait", "--wait-timeout", "180", "salida"',
             'Cerrar-Lectura $Solicitud "salida"', '"lector", "lectura", "contar"',
             "if ($Automatica) {", '"orden", "lectura", "autorizar"',
             '"orden", "lectura", "esperar"', '"lector", "lectura", "leer"', "} finally {",
             'Cerrar-Lectura $Solicitud "interrumpida" -SiViva']
    posiciones = [leer.index(p) for p in pasos]
    assert posiciones == sorted(posiciones)
    for anterior, siguiente in (("contar", "autorizar"), ('esperar"', "leer")):
        trozo = leer[leer.index(anterior):leer.index(f'"lectura", "{siguiente}')]
        assert ".Codigo -ne 0) { return }" in trozo, (anterior, siguiente)
    lectura = _funcion(texto, "Lectura-Del-Ciclo")
    pasos = ['(Entorno-De-La-Consola) -eq "demo"', '"lectura", "siguiente"',
             "if ($toca.Codigo -eq 0) {", '"lectura", "tomar", "--automatica"',
             "Leer-Con-Salida $solicitud -Automatica", "$toca.Codigo -eq $LecturaPedida",
             '"lectura", "tomar", "/buzon/facturas", "--solo-pedida"',
             "Leer-Con-Salida $solicitud\n"]
    posiciones = [lectura.index(p) for p in pasos]
    assert posiciones == sorted(posiciones)
    from bms_agent import lectura as modulo_lectura
    for motivo in re.findall(r'Cerrar-Lectura \$Solicitud "([a-z_]+)"', texto):
        assert motivo in modulo_lectura.MOTIVOS, motivo


def test_correo_certificado_activa_con_la_pausa_y_vuelve_si_no_vale() -> None:
    """§2.4: crear el siguiente; -Activar con la automatizacion en pausa: activar (local),
    comprobar con el contenedor del correo de siempre, y borrar el anterior si vale o volver a
    el si Microsoft no acepta el nuevo; registrar y reanudar."""
    texto = _sin_comentarios(_ps1("correo-certificado"))
    assert 'Orden-Secretos-Correo @("correo", "certificado", "crear", "--siguiente")' in texto
    activar = texto[texto.index("# -Activar") if "# -Activar" in texto else texto.index(
        'Pausar-Automatico "correo-certificado.bat -Activar"'):]
    pasos = ['Pausar-Automatico "correo-certificado.bat -Activar" -SoloSiSigue',
             'Orden-Secretos-Correo @("correo", "certificado", "activar")',
             "$comprobado = Comprobar-Correo", "if ($comprobado.Codigo -eq 0) {",
             '"certificado", "borrar", "--anterior"', '$comprobado.Que -eq "credencial"',
             '"certificado", "volver"', "Registrar-Correo", "Soltar-Cerrojo",
             "Reanudar-Automatico -SiLaPuseYo", "if ($final) { Fallar $final }"]
    _en_orden(activar, pasos)
    # Si no se pudo activar, no se comprueba nada y se reanuda (si la pausa la puso el).
    fallo = activar[activar.index('"certificado", "activar")'):activar.index(
        "$comprobado = Comprobar-Correo")]
    assert fallo.index("Reanudar-Automatico -SiLaPuseYo") < fallo.index("Fallar")
    # Nunca rehace el actual.
    assert '@("correo", "certificado", "crear")' not in texto


def test_correo_configurar_en_dos_fases_sin_rehacer_nunca_el_certificado() -> None:
    """§2.6: fase 1, el certificado (solo si no hay); fase 2, los cuatro datos, la comprobacion
    y, al final, registrar (la app lo ve sin esperar al ciclo)."""
    texto = _sin_comentarios(_ps1("correo-configurar"))
    pasos = ['Orden-Secretos-Correo @("correo", "certificado", "ver")',
             "if ($ver -eq $CorreoSinConfigurar) {",
             'Orden-Secretos-Correo @("correo", "certificado", "crear")',
             '"correo", "ajustes", "fijar", "--inquilino", $inquilino',
             "Tomar-Cerrojo -Esperar 900", "$comprobado = Comprobar-Correo",
             "Registrar-Correo", "Soltar-Cerrojo", '"permiso" {', '"alcance" {',
             '"credencial" {', '"control_no_existe" {']
    posiciones = [texto.index(p) for p in pasos]
    assert posiciones == sorted(posiciones)
    assert texto.count('"certificado", "crear"') == 1
    for nunca in ("--siguiente", '"activar"', '"volver"', '"borrar"', "Pausar-Automatico"):
        assert nunca not in texto, nunca
    comun = _ps1("comun")
    comprobar = _funcion(comun, "Comprobar-Correo")
    assert "docker compose run --rm -T correo @OrdenComprobar 2>&1" in comprobar
    assert "orden correo registrar --entrada /correo/entrada --estado /correo/estado" in \
        _funcion(comun, "Registrar-Correo")


def test_ver_salida_ensena_los_dos_registros() -> None:
    texto = _ps1("ver-salida")
    assert '$argumentos = @("salida-registro")' in texto
    assert '@("salida-registro", "--fichero", "/registro-correo/salida-correo.log")' in texto
    for host in ("api.anthropic.com", "login.microsoftonline.com", "graph.microsoft.com"):
        assert host in texto, host


def test_los_scripts_de_docker_son_de_windows_powershell_5_1_y_no_bajan_nada() -> None:
    """Como los de la nativa (test_instalacion_nativa.py): nada que solo entienda PowerShell 7,
    nada que ejecute texto ni que baje algo."""
    todos = {p.stem: p.read_text(encoding="utf-8") for p in DOCKER.glob("*.ps1")}
    assert set(todos) == set(SCRIPTS) | {"comun"} | set(SIN_COMUN)
    for nombre, texto in todos.items():
        if nombre == "mac":
            # Mirar una clave publica pide FromBase64String: solo ahi (test_tunel_mac.py).
            for funcion in ("Clave-Publica-Valida", "Huella-Sha256"):
                texto = texto.replace(_funcion(texto, funcion), "")
        codigo = _codigo(texto)
        assert not re.search(r"&&|\|\||\?\?|\?\.|\s\?\s[^:\n]+\s:\s", codigo), nombre
        assert not re.search(r"-Parallel|-AsPlainText|-AsHashtable|-AsByteStream|utf8NoBOM|"
                             r"\$PSStyle|-SkipCertificateCheck|GetRelativePath|\bclean\s*\{",
                             codigo, re.IGNORECASE), nombre
        assert not re.search(r"Invoke-Expression|\biex\b|DownloadString|DownloadFile|"
                             r"Start-BitsTransfer|\bcurl\b|\bwget\b|Net\.WebClient|"
                             r"FromBase64String|-EncodedCommand|Set-ExecutionPolicy|"
                             r"ServerCertificateValidationCallback|-OutFile",
                             codigo, re.IGNORECASE), nombre
        simple = r'(?:\$[\w.:]+|"[^"]*")'
        assert not re.search(rf"Join-Path[ \t]+{simple}[ \t]+{simple}[ \t]+{simple}",
                             _sin_comentarios(texto)), nombre
        assert texto.isascii(), nombre
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{6,}", texto), nombre


def test_pwsh_cada_script_de_docker_pasa_el_analizador() -> None:
    """Sin errores de sintaxis en ningun .ps1 de docker/ (con el analizador de PowerShell; el
    de Windows PowerShell 5.1 solo esta en Windows, §7.4)."""
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("sin pwsh")
    carpeta = str(DOCKER).replace("'", "''")
    guion = ("$e = @{}; foreach ($f in Get-ChildItem -LiteralPath '" + carpeta + "' -Filter "
             "*.ps1) { "
             "$t = $null; $x = $null; [System.Management.Automation.Language.Parser]::ParseFile("
             "$f.FullName, [ref]$t, [ref]$x) | Out-Null; "
             "$e[$f.Name] = @($x | ForEach-Object { $_.Message }) }; $e | ConvertTo-Json -Depth 3")
    proceso = subprocess.run([pwsh, "-NoProfile", "-NonInteractive", "-Command", guion],
                             capture_output=True, text=True, timeout=120)
    assert proceso.returncode == 0, proceso.stderr
    errores = json.loads(proceso.stdout)
    assert set(errores) == {f"{n}.ps1" for n in (*SCRIPTS, *SIN_COMUN)} | {"comun.ps1"}
    assert {n: e for n, e in errores.items() if e} == {}


# ============================================================ la consola en un contenedor

def test_fuera_de_un_contenedor_solo_se_escucha_en_127_0_0_1(tmp_path) -> None:
    assert interfaz_permitida("127.0.0.1", contenedor=False) == "127.0.0.1"
    for interfaz in ("0.0.0.0", "192.168.1.10", "::", ""):
        with pytest.raises(ValueError):
            interfaz_permitida(interfaz, contenedor=False)
    assert interfaz_permitida("0.0.0.0", contenedor=True) == "0.0.0.0"
    with pytest.raises(ValueError):
        interfaz_permitida("192.168.1.10", contenedor=True)
    assert not en_contenedor((tmp_path / "no-hay",))
    (tmp_path / ".dockerenv").write_text("")
    assert en_contenedor((tmp_path / ".dockerenv",))


def test_en_un_contenedor_escucha_en_todas_y_no_lee_pdf(tmp_path, monkeypatch) -> None:
    from bms_agent import serve

    # Fuera de un contenedor, aunque la suite corra dentro de uno (/.dockerenv).
    monkeypatch.setattr(serve, "en_contenedor", lambda *a: False)
    with pytest.raises(ValueError):
        crear_servidor(tmp_path / "f", tmp_path / "o", 0, interfaz="0.0.0.0",
                       ruta_db=tmp_path / "bms.sqlite3")
    monkeypatch.setattr(serve, "en_contenedor", lambda *a: True)
    srv = crear_servidor(tmp_path / "f", tmp_path / "o", 0, token="t", interfaz="0.0.0.0",
                         lectura=False, ruta_db=tmp_path / "bms.sqlite3")
    try:
        assert srv.server_address[0] == "0.0.0.0"
        hilo = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05},
                                daemon=True)
        hilo.start()
        puerto = srv.server_address[1]
        conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=10)
        conexion.request("POST", "/api/ejecutar", body=b"{}", headers={
            "Host": f"127.0.0.1:{puerto}", "Content-Type": "application/json",
            "X-BMS-Token": "t"})
        respuesta = conexion.getresponse()
        cuerpo = json.loads(respuesta.read())
        conexion.close()
        # Lanzar una pasada no hace nada: en el entorno de Docker los PDF los lee el lector.
        assert respuesta.status == 409 and cuerpo["lanzada"] is False
        assert "lector" in cuerpo["mensaje"]
        # Y el Host sigue teniendo que ser el de este ordenador.
        conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=10)
        conexion.request("GET", "/consola", headers={"Host": f"192.168.1.10:{puerto}"})
        assert conexion.getresponse().status == 421
        conexion.close()
    finally:
        srv.shutdown()
        srv.server_close()


def test_la_cli_no_abre_la_consola_a_la_red_fuera_de_un_contenedor(capsys,
                                                                    monkeypatch) -> None:
    from bms_agent import serve

    # Si la suite corre dentro de un contenedor, la orden arrancaria de verdad y no volveria.
    monkeypatch.setattr(serve, "en_contenedor", lambda *a: False)
    assert main(["serve", "--contenedor", "--puerto", "0"]) == 2
    assert "contenedor" in capsys.readouterr().err


# ============================================================ la clave de la API

def test_sin_fichero_la_clave_la_busca_el_sdk(monkeypatch) -> None:
    monkeypatch.delenv(config.VARIABLE_FICHERO_CLAVE, raising=False)
    assert config.clave_api() is None


@pytest.mark.parametrize("codificacion", ["utf-8", "utf-8-sig", "utf-16", "utf-16-be"])
def test_la_clave_se_lee_de_su_fichero(tmp_path, monkeypatch, codificacion) -> None:
    """Como la guarde Windows: UTF-8 con o sin BOM (el Bloc de notas), UTF-16 (el Bloc de
    notas con "Unicode", o `>` en Windows PowerShell 5.1), con CRLF."""
    fichero = tmp_path / "anthropic_api_key.txt"
    texto = "  sk-ant-api03-de-prueba \r\n"
    contenido = (b"\xfe\xff" + texto.encode("utf-16-be") if codificacion == "utf-16-be"
                 else texto.encode(codificacion))
    fichero.write_bytes(contenido)
    monkeypatch.setenv(config.VARIABLE_FICHERO_CLAVE, str(fichero))
    assert config.clave_api() == "sk-ant-api03-de-prueba"


@pytest.mark.parametrize("contenido", [None, "", "   \n", "no-es-una-clave",
                                       "sk-ant-dos\nlineas", "sk-ant- con espacios",
                                       b"sk-ant-api03-\xff\xfeno-es-texto"])
def test_un_fichero_de_clave_malo_se_dice_sin_ensenarla(tmp_path, monkeypatch, capsys,
                                                         pdfs_ejemplo, contenido) -> None:
    fichero = tmp_path / "anthropic_api_key.txt"
    if isinstance(contenido, bytes):
        fichero.write_bytes(contenido)
        contenido = "sk-ant-api03-"
    elif contenido is not None:
        fichero.write_text(contenido, encoding="utf-8")
    monkeypatch.setenv(config.VARIABLE_FICHERO_CLAVE, str(fichero))
    with pytest.raises(config.ClaveNoValida) as error:
        config.clave_api()
    if contenido and contenido.strip():
        assert contenido.strip() not in str(error.value)
    # La CLI lo dice antes de crear el cliente, y sin traza.
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: pytest.fail("no se llama"))
    assert main(["coste", "--estimar", str(pdfs_ejemplo)]) == 2
    assert "clave de la API" in capsys.readouterr().err


# ============================================================ la copia de seguridad

@pytest.fixture
def con_datos(pdfs_ejemplo, tmp_path):
    """Una base en disco con las siete facturas v1, tres de ellas con su original, y sus
    anclas."""
    from bms_agent.auditoria import anclar
    from bms_agent.importadores.extracciones import importar_out

    ruta = tmp_path / "datos" / "bms.sqlite3"
    with preparar(ruta) as almacen:
        importar_out(almacen, RAIZ / "tests" / "fixtures" / "v1", pdfs_ejemplo)
        anclar(almacen.conn, almacen.ruta_anclas)
    return ruta


def test_la_copia_sale_entera_comprobada_y_se_abre(con_datos, tmp_path) -> None:
    disco = tmp_path / "disco"
    disco.mkdir()
    hecha = copia.copiar(con_datos, disco)
    assert hecha.carpeta.parent == disco and hecha.problemas == []
    nombres = {p.relative_to(hecha.carpeta).as_posix() for p in hecha.carpeta.rglob("*")
               if p.is_file()}
    assert {"bms.sqlite3", "anclas.log", copia.MANIFIESTO} <= nombres
    assert not {n for n in nombres if n.endswith(("-wal", "-shm"))}
    assert hecha.documentos >= 1 and any(n.startswith("documentos/") for n in nombres)
    manifiesto = copia.leer_manifiesto(hecha.carpeta)
    assert set(manifiesto) == nombres - {copia.MANIFIESTO}
    # La copia es una base que se abre y dice lo mismo que la original.
    with contextlib.closing(sqlite3.connect(con_datos)) as original, \
            contextlib.closing(sqlite3.connect(hecha.carpeta / "bms.sqlite3")) as copiada:
        for tabla in ("documento", "extraccion", "evento"):
            assert original.execute(f"SELECT count(*) FROM {tabla}").fetchone() == \
                copiada.execute(f"SELECT count(*) FROM {tabla}").fetchone()
    assert main(["db", "verificar", "--db", str(hecha.carpeta / "bms.sqlite3")]) == 0


def test_una_copia_tocada_no_pasa_la_comprobacion(con_datos, tmp_path) -> None:
    disco = tmp_path / "disco"
    disco.mkdir()
    hecha = copia.copiar(con_datos, disco)
    (hecha.carpeta / "anclas.log").write_text("otra cosa\n", encoding="utf-8")
    (hecha.carpeta / "de-mas.txt").write_text("x", encoding="utf-8")
    problemas = copia.comprobar(hecha.carpeta, "bms.sqlite3")
    assert any("anclas.log" in p for p in problemas) and any("de-mas" in p for p in problemas)


def test_la_copia_no_sobrescribe_ni_va_a_un_disco_que_no_esta(con_datos, tmp_path,
                                                             capsys) -> None:
    from bms_agent.reloj import RelojFijo
    from datetime import datetime, timezone

    reloj = RelojFijo(datetime(2026, 10, 14, 9, 30, tzinfo=timezone.utc))
    disco = tmp_path / "disco"
    disco.mkdir()
    primera = copia.copiar(con_datos, disco, reloj=reloj)
    assert primera.carpeta.name == "bms-copia-bms-20261014-113000"
    with pytest.raises(copia.CopiaFallida):
        copia.copiar(con_datos, disco, reloj=reloj)
    with pytest.raises(copia.CopiaFallida):
        copia.copiar(con_datos, tmp_path / "no-conectado")
    assert main(["copia", str(tmp_path / "no-conectado"), "--db", str(con_datos)]) == 1
    assert "conectar el disco" in capsys.readouterr().err
    assert main(["copia", str(disco), "--db", str(con_datos)]) == 0


def test_la_copia_de_la_base_de_prueba_lleva_sus_originales(tmp_path) -> None:
    from bms_agent import demo

    ruta = tmp_path / "datos" / "demo.sqlite3"
    demo.crear(ruta)
    disco = tmp_path / "disco"
    disco.mkdir()
    hecha = copia.copiar(ruta, disco)
    assert (hecha.carpeta / "demo.sqlite3").is_file()
    assert (hecha.carpeta / "demo-documentos").is_dir()
    assert demo.es_demo(hecha.carpeta / "demo.sqlite3")


def _eventos(ruta) -> int:
    # sqlite3.connect como "with" no cierra la conexion: una abierta haria que restaurar
    # viera la base en uso.
    with contextlib.closing(sqlite3.connect(ruta)) as conn:
        return conn.execute("SELECT count(*) FROM evento").fetchone()[0]


def test_restaurar_vuelve_a_la_copia_y_guarda_lo_de_antes(con_datos, tmp_path, capsys) -> None:
    disco = tmp_path / "disco"
    disco.mkdir()
    hecha = copia.copiar(con_datos, disco)
    eventos_copia = _eventos(con_datos)
    # Despues de la copia se sigue trabajando: la base tiene mas que la copia.
    with preparar(con_datos) as almacen:
        from bms_agent import permisos
        from bms_agent.auditoria import anclar

        permisos.asegurar_roles_base(almacen.conn)
        permisos.crear_usuario(almacen.conn, "Persona despues de la copia")
        anclar(almacen.conn, almacen.ruta_anclas)
    eventos_despues = _eventos(con_datos)
    assert eventos_despues > eventos_copia
    assert main(["restaurar", str(hecha.carpeta), "--db", str(con_datos)]) == 0
    # Lo de la copia, y el evento que dice que se restauro.
    assert _eventos(con_datos) == eventos_copia + 1
    assert main(["db", "verificar", "--db", str(con_datos)]) == 0
    # Lo que habia antes de restaurar esta guardado entero, y se puede volver a ello.
    [antes] = list((con_datos.parent / "antes-de-restaurar").iterdir())
    assert _eventos(antes / "bms.sqlite3") == eventos_despues
    assert copia.comprobar(antes, "bms.sqlite3") == []
    capsys.readouterr()


def test_restaurar_no_toca_nada_con_una_copia_mala_o_de_otra_base(con_datos, tmp_path) -> None:
    from bms_agent import demo

    disco = tmp_path / "disco"
    disco.mkdir()
    hecha = copia.copiar(con_datos, disco)
    (hecha.carpeta / "anclas.log").write_text("tocada\n", encoding="utf-8")
    contenido = con_datos.read_bytes()
    with pytest.raises(copia.CopiaFallida):
        copia.restaurar(hecha.carpeta, con_datos)
    # Una copia de la base de prueba no vuelve sobre la de verdad.
    prueba = tmp_path / "prueba" / "demo.sqlite3"
    demo.crear(prueba)
    de_prueba = copia.copiar(prueba, disco)
    shutil.copy(de_prueba.carpeta / "demo.sqlite3", de_prueba.carpeta / "bms.sqlite3")
    with pytest.raises(copia.CopiaFallida):
        copia.restaurar(de_prueba.carpeta, con_datos)
    with pytest.raises(copia.CopiaFallida):
        copia.restaurar(tmp_path / "no-es-una-copia", con_datos)
    assert con_datos.read_bytes() == contenido
    assert not (con_datos.parent / "antes-de-restaurar").exists()


def test_comprobar_una_copia_no_la_toca(con_datos, tmp_path, capsys) -> None:
    disco = tmp_path / "disco"
    disco.mkdir()
    hecha = copia.copiar(con_datos, disco)
    antes = {p.name: p.read_bytes() for p in hecha.carpeta.iterdir() if p.is_file()}
    hecha.carpeta.chmod(0o555)
    try:
        assert main(["copia", str(hecha.carpeta), "--comprobar", "--db", str(con_datos)]) == 0
    finally:
        hecha.carpeta.chmod(0o755)
    assert {p.name: p.read_bytes() for p in hecha.carpeta.iterdir() if p.is_file()} == antes
    assert "cada fichero tiene su hash" in capsys.readouterr().out


def test_una_copia_con_la_consola_anclando_a_la_vez_pasa_db_verificar(con_datos, tmp_path,
                                                                     monkeypatch) -> None:
    """Entre copiar la base y copiar las anclas, la consola en marcha escribe y ancla: la
    copia tiene que seguir pasando `db verificar`."""
    from bms_agent import permisos
    from bms_agent.auditoria import anclar

    real = shutil.copy2

    def copiar_con_la_consola_escribiendo(fuente, destino, *a, **k):
        if str(fuente).endswith("anclas.log"):
            with preparar(con_datos) as almacen:
                permisos.crear_usuario(almacen.conn, "Persona mientras se copia")
                anclar(almacen.conn, almacen.ruta_anclas)
        return real(fuente, destino, *a, **k)

    monkeypatch.setattr(copia.shutil, "copy2", copiar_con_la_consola_escribiendo)
    disco = tmp_path / "disco"
    disco.mkdir()
    hecha = copia.copiar(con_datos, disco)
    assert hecha.problemas == []
    assert main(["db", "verificar", "--db", str(hecha.carpeta / "bms.sqlite3")]) == 0


def test_una_copia_que_db_verificar_rechazaria_no_pasa_por_comprobada(con_datos,
                                                                     tmp_path) -> None:
    """Un ancla mas alla de la cadena de la copia: la copia no se da por buena."""
    disco = tmp_path / "disco"
    disco.mkdir()
    hecha = copia.copiar(con_datos, disco)
    anclas = hecha.carpeta / "anclas.log"
    ultima = anclas.read_text(encoding="utf-8").splitlines()[-1].split("\t")
    ultima[1] = str(int(ultima[1]) + 5)
    anclas.write_text(anclas.read_text(encoding="utf-8") + "\t".join(ultima) + "\n",
                      encoding="utf-8")
    manifiesto = (hecha.carpeta / copia.MANIFIESTO).read_text(encoding="utf-8")
    viejo = copia.leer_manifiesto(hecha.carpeta)["anclas.log"]
    (hecha.carpeta / copia.MANIFIESTO).write_text(
        manifiesto.replace(viejo, copia._sha256(anclas)), encoding="utf-8")
    problemas = copia.comprobar(hecha.carpeta, "bms.sqlite3")
    assert any("se ha cortado" in p for p in problemas)
    with pytest.raises(copia.CopiaFallida):
        copia.restaurar(hecha.carpeta, con_datos)


def test_restaurar_no_sigue_con_la_base_abierta_aunque_este_en_wal(con_datos,
                                                                   tmp_path) -> None:
    """La consola tiene la base abierta y quieta (en WAL): restaurar no la pisa."""
    disco = tmp_path / "disco"
    disco.mkdir()
    hecha = copia.copiar(con_datos, disco)
    viva = preparar(con_datos)
    try:
        assert viva.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        viva.conn.execute("SELECT count(*) FROM evento").fetchone()
        with pytest.raises(copia.CopiaFallida, match="abierta"):
            copia.restaurar(hecha.carpeta, con_datos)
    finally:
        viva.cerrar()
    assert not (con_datos.parent / copia.ANTES_DE_RESTAURAR).exists()
    copia.restaurar(hecha.carpeta, con_datos)


def test_restaurar_en_una_instalacion_nueva_crea_la_carpeta(con_datos, tmp_path,
                                                            capsys) -> None:
    disco = tmp_path / "disco"
    disco.mkdir()
    hecha = copia.copiar(con_datos, disco)
    nueva = tmp_path / "ordenador-nuevo" / "datos" / "bms.sqlite3"
    hecho = copia.restaurar(hecha.carpeta, nueva)
    assert hecho.antes is None and nueva.is_file()
    assert (nueva.parent / "documentos").is_dir() and (nueva.parent / "anclas.log").is_file()
    assert main(["db", "verificar", "--db", str(nueva)]) == 0
    capsys.readouterr()


def _usuarios(ruta) -> set[str]:
    with contextlib.closing(sqlite3.connect(ruta)) as conn:
        return {f[0] for f in conn.execute("SELECT nombre FROM usuario WHERE es_sistema = 0")}


def test_restaurar_no_reescribe_las_anclas_y_deja_el_corte_dicho(con_datos, tmp_path,
                                                                 capsys) -> None:
    """Una vuelta atras borra lo firmado despues de la copia: no puede quedar como si nada.
    El fichero de anclas solo crece, la base restaurada dice que se restauro (y que se
    corto), y `db verificar` lo ensena; sin ese evento, el corte es un problema."""
    from bms_agent import permisos
    from bms_agent.auditoria import TIPO_RESTAURACION, anclar

    disco = tmp_path / "disco"
    disco.mkdir()
    with preparar(con_datos) as almacen:
        permisos.asegurar_roles_base(almacen.conn)
        permisos.crear_usuario(almacen.conn, "Ana")
        anclar(almacen.conn, almacen.ruta_anclas)
    hecha = copia.copiar(con_datos, disco)
    with preparar(con_datos) as almacen:
        permisos.crear_usuario(almacen.conn, "Bram")
        anclar(almacen.conn, almacen.ruta_anclas)
        permisos.crear_usuario(almacen.conn, "Carla")
        anclar(almacen.conn, almacen.ruta_anclas)
        cabeza_sustituida = almacen.conn.execute(
            "SELECT id, hash FROM evento ORDER BY id DESC LIMIT 1").fetchone()
    anclas = con_datos.parent / "anclas.log"
    antes = anclas.read_text(encoding="utf-8")

    assert main(["restaurar", str(hecha.carpeta), "--db", str(con_datos)]) == 0
    assert "queda en la auditoria" in capsys.readouterr().out
    assert _usuarios(con_datos) == {"Ana"}
    despues = anclas.read_text(encoding="utf-8")
    assert despues.startswith(antes) and len(despues) > len(antes)

    with contextlib.closing(sqlite3.connect(con_datos)) as conn:
        [(tipo, datos_json)] = conn.execute(
            "SELECT tipo, datos_json FROM evento ORDER BY id DESC LIMIT 1").fetchall()
    datos = json.loads(datos_json)
    assert tipo == TIPO_RESTAURACION
    assert datos["sustituida"] == [cabeza_sustituida[0], cabeza_sustituida[1]]
    assert datos["copia"] == str(hecha.carpeta) and datos["antes"]
    assert len(datos["anclas_descartadas"]) == 2
    assert main(["db", "verificar", "--db", str(con_datos)]) == 0
    salida_verificar = capsys.readouterr().out
    assert "se restauro desde una copia" in salida_verificar
    assert "2 anclas son de lo que sustituyo una restauracion" in salida_verificar

    # Sin el evento de restauracion (una vuelta atras a mano), el corte se ve.
    a_mano = tmp_path / "a-mano" / "bms.sqlite3"
    a_mano.parent.mkdir()
    shutil.copy(hecha.carpeta / "bms.sqlite3", a_mano)
    (a_mano.parent / "anclas.log").write_text(antes, encoding="utf-8")
    assert main(["db", "verificar", "--db", str(a_mano)]) == 1
    assert "se ha cortado" in capsys.readouterr().out


def test_restaurar_dos_veces_sigue_cuadrando(con_datos, tmp_path, capsys) -> None:
    """Dos vueltas atras seguidas (en el mismo segundo): cada una guarda lo de antes en su
    carpeta, y la cadena cuadra con las anclas de las tres historias."""
    from datetime import datetime, timezone

    from bms_agent import permisos
    from bms_agent.auditoria import anclar
    from bms_agent.reloj import RelojFijo

    disco = tmp_path / "disco"
    disco.mkdir()
    primera = copia.copiar(con_datos, disco)
    with preparar(con_datos) as almacen:
        permisos.crear_usuario(almacen.conn, "Bram")
        anclar(almacen.conn, almacen.ruta_anclas)
    copia.restaurar(primera.carpeta, con_datos)
    with preparar(con_datos) as almacen:
        permisos.crear_usuario(almacen.conn, "Carla")
        anclar(almacen.conn, almacen.ruta_anclas)
    segunda = copia.copiar(con_datos, disco, reloj=RelojFijo(
        datetime(2030, 1, 1, tzinfo=timezone.utc)))
    with preparar(con_datos) as almacen:
        permisos.crear_usuario(almacen.conn, "Dirk")
        anclar(almacen.conn, almacen.ruta_anclas)
    copia.restaurar(segunda.carpeta, con_datos)
    assert len(list((con_datos.parent / copia.ANTES_DE_RESTAURAR).iterdir())) == 2
    assert _usuarios(con_datos) == {"Carla"}
    assert main(["db", "verificar", "--db", str(con_datos)]) == 0
    capsys.readouterr()
