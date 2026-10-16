"""El entorno local de Docker (paso 13), sin arrancar ningun contenedor.

Puertas que viven aqui (la de los contenedores de verdad esta en test_entorno_docker.py):

- docker-compose.yml: la consola y el lector solo estan en redes internas; la salida
  es el unico servicio con un pie fuera; el unico puerto publicado lo esta en
  127.0.0.1; todos con el sistema de ficheros de solo lectura, sin capacidades y sin
  escalar privilegios; la clave es un secreto que solo ve el lector y nunca una
  variable; el lector solo arranca a proposito y sale por el proxy;
- el Dockerfile: base fijada por etiqueta y digest, usuario sin privilegios,
  comprobacion de salud, dependencias con su hash;
- .dockerignore y .gitignore dejan fuera los datos, el buzon y la clave;
- los scripts de Windows: existen, dicen las cosas en claro, nunca borran el volumen
  ni llevan la clave;
- la consola solo escucha en 0.0.0.0 dentro de un contenedor, y ahi no lee PDF;
- la clave se lee de su fichero sin ensenarla;
- la copia de seguridad sale entera, comprobada y sin sobrescribir otra.
"""

from __future__ import annotations

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
SERVICIOS = ("consola", "salida", "lector", "orden")


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _redes(servicio: dict) -> set[str]:
    redes = servicio.get("networks") or {}
    return set(redes) if isinstance(redes, (dict, list)) else set()


# ============================================================ docker-compose.yml

def test_estan_los_cuatro_servicios_con_la_misma_imagen(compose) -> None:
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
    # La unica red con salida, y solo la salida esta en ella.
    externas = {n for n, r in redes.items() if not (r or {}).get("internal")}
    assert externas == {"red_exterior"}
    con_salida = {n for n, s in servicios.items() if _redes(s) & externas}
    assert con_salida == {"salida"}
    assert _redes(servicios["salida"]) == {"red_consola", "red_lector", "red_exterior"}


def test_el_unico_puerto_es_el_de_la_consola_en_127_0_0_1(compose) -> None:
    publicados = {n: s.get("ports", []) for n, s in compose["services"].items()}
    assert publicados == {"consola": [], "salida": ["127.0.0.1:8765:8765"], "lector": [],
                          "orden": []}
    for servicio in compose["services"].values():
        assert "expose" not in servicio


def test_la_salida_solo_deja_ir_a_la_api_y_escucha_en_la_red_del_lector(compose) -> None:
    s = compose["services"]["salida"]
    orden = s["command"]
    assert orden[0] == "salida"
    valor = {orden[i]: orden[i + 1] for i in range(1, len(orden), 2)}
    assert valor == {"--escuchar": "proxy:3128", "--permitir": "api.anthropic.com:443",
                     "--reenviar": "entrada:8765=consola:8765"}
    assert orden.count("--permitir") == 1
    salida.lista_blanca([valor["--permitir"]])
    # "proxy" es su nombre solo en la red del lector; "entrada", solo en la de fuera (por ahi
    # llega el puerto publicado): la consola no ve el proxy y el lector no ve la entrada.
    assert s["networks"]["red_lector"]["aliases"] == ["proxy"]
    assert s["networks"]["red_exterior"]["aliases"] == ["entrada"]
    assert not (s["networks"]["red_consola"] or {}).get("aliases")
    assert s["healthcheck"]["test"][-2:] == ["salud", "proxy:3128"]


def test_el_lector_solo_arranca_a_proposito_y_sale_por_el_proxy(compose) -> None:
    lector = compose["services"]["lector"]
    assert lector["profiles"] == ["lector"]
    assert compose["services"]["orden"]["profiles"] == ["ordenes"]
    assert "profiles" not in compose["services"]["consola"]
    assert "profiles" not in compose["services"]["salida"]
    entorno = lector["environment"]
    assert entorno["HTTPS_PROXY"] == entorno["https_proxy"] == "http://proxy:3128"
    assert entorno["NO_PROXY"] == entorno["no_proxy"] == ""
    assert "HTTP_PROXY" not in entorno and "ALL_PROXY" not in entorno
    assert lector["depends_on"]["salida"]["condition"] == "service_healthy"
    assert lector["healthcheck"] == {"disable": True}


def test_la_clave_es_un_secreto_que_solo_ve_el_lector(compose) -> None:
    servicios = compose["services"]
    assert {n for n, s in servicios.items() if s.get("secrets")} == {"lector"}
    assert servicios["lector"]["secrets"] == ["anthropic_api_key"]
    assert compose["secrets"] == {"anthropic_api_key": {
        "file": "./secretos/anthropic_api_key.txt"}}
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
    assert compose["volumes"] == {"datos": {}}
    assert servicios["consola"]["volumes"] == ["datos:/datos"]
    assert servicios["salida"].get("volumes") is None
    for nombre in ("lector", "orden"):
        assert servicios[nombre]["volumes"] == ["datos:/datos", "../buzon:/buzon:ro"]
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
    assert set(perfiles.stdout.split()) == {"lector", "ordenes"}


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


def test_las_dependencias_van_con_version_y_hash() -> None:
    texto = (DOCKER / "requirements.txt").read_text(encoding="utf-8")
    paquetes = {}
    for bloque in re.split(r"\n(?=[A-Za-z])", re.sub(r"(?m)^#.*\n", "", texto).strip()):
        cabeza = bloque.split()[0]
        nombre, version = cabeza.split("==")
        hashes = re.findall(r"--hash=sha256:([0-9a-f]{64})", bloque)
        assert hashes, nombre
        paquetes[nombre.lower().replace("_", "-")] = version
    # Lo que pide pyproject.toml, y las mismas versiones con que pasan los tests.
    for nombre in ("anthropic", "pydantic", "pyyaml"):
        assert nombre in paquetes
    for nombre, version in paquetes.items():
        try:
            instalada = importlib.metadata.version(nombre)
        except importlib.metadata.PackageNotFoundError:
            continue
        assert instalada == version, (nombre, instalada, version)


def test_dockerignore_y_gitignore_dejan_fuera_los_datos_y_la_clave() -> None:
    reglas = [l.strip() for l in (RAIZ / ".dockerignore").read_text(encoding="utf-8")
              .splitlines() if l.strip() and not l.startswith("#")]
    # Primero todo fuera; luego solo lo que hace falta para la imagen.
    assert reglas[0] == "**"
    dentro = {r[1:] for r in reglas if r.startswith("!")}
    assert dentro == {"docker/requirements.txt", "pyproject.toml", "README.md", "config/",
                      "src/"}
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

SCRIPTS = ("iniciar", "parar", "importar", "leer-facturas", "copia", "restaurar", "persona")


@pytest.mark.parametrize("nombre", SCRIPTS)
def test_cada_script_tiene_su_bat_y_habla_claro(nombre) -> None:
    ps1 = (DOCKER / f"{nombre}.ps1").read_text(encoding="utf-8")
    bat = (DOCKER / f"{nombre}.bat").read_text(encoding="utf-8")
    assert f'-File "%~dp0{nombre}.ps1" %*' in bat and "-ExecutionPolicy Bypass" in bat
    assert '. "$PSScriptRoot\\comun.ps1"' in ps1
    assert "Comprobar-Docker" in ps1
    # Windows PowerShell lee un .ps1 sin BOM como ANSI: nada fuera del ASCII.
    assert ps1.isascii() and bat.isascii()
    assert "sk-ant-" not in ps1
    assert not re.search(r"down\s+(-v|--volumes)", ps1)
    assert "Escribir" in ps1 or "Fallar" in ps1


def test_iniciar_con_demo_usa_la_base_de_prueba_y_la_rehace() -> None:
    comun = (DOCKER / "comun.ps1").read_text(encoding="utf-8")
    iniciar = (DOCKER / "iniciar.ps1").read_text(encoding="utf-8")
    assert '$env:BMS_BASE = "demo"' in comun and '$env:BMS_BASE = "bms"' in comun
    assert '"demo", "crear", "--rehacer", "--db", "/datos/demo.sqlite3"' in iniciar
    assert "up -d consola salida" in iniciar
    assert "127.0.0.1:8765/consola" in iniciar


def test_el_token_va_por_el_entorno_y_no_en_la_orden() -> None:
    comun = (DOCKER / "comun.ps1").read_text(encoding="utf-8")
    assert "-AsSecureString" in comun and "ZeroFreeBSTR" in comun
    assert "run --rm -T -e BMS_TOKEN orden" in comun
    assert "--token" not in "".join((DOCKER / f"{n}.ps1").read_text(encoding="utf-8")
                                    for n in SCRIPTS)


def test_leer_facturas_cuenta_antes_y_pide_que_si() -> None:
    texto = (DOCKER / "leer-facturas.ps1").read_text(encoding="utf-8")
    contar = texto.index("lector coste --estimar")
    preguntar = texto.index("Read-Host")
    leer = texto.index("lector extract")
    assert contar < preguntar < leer
    assert '$respuesta -ne "si"' in texto


def test_importar_conoce_cada_carpeta_del_buzon() -> None:
    texto = (DOCKER / "importar.ps1").read_text(encoding="utf-8")
    pares = set(re.findall(r'"([a-z\\]+)"\s*=\s*@\("([a-z_]+)", "([a-z_]+)"\)', texto))
    assert {(f, t) for _c, f, t in pares} == {
        ("exact", "proveedores"), ("exact", "clientes"), ("exact", "facturas_venta"),
        ("exact", "pagos_exact"), ("banco", "extracto"), ("trnsprnt", "planning"),
        ("po_csv", "ordenes_compra")}


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


def test_la_cli_no_abre_la_consola_a_la_red_fuera_de_un_contenedor(capsys) -> None:
    assert main(["serve", "--contenedor", "--puerto", "0"]) == 2
    assert "contenedor" in capsys.readouterr().err


# ============================================================ la clave de la API

def test_sin_fichero_la_clave_la_busca_el_sdk(monkeypatch) -> None:
    monkeypatch.delenv(config.VARIABLE_FICHERO_CLAVE, raising=False)
    assert config.clave_api() is None


def test_la_clave_se_lee_de_su_fichero(tmp_path, monkeypatch) -> None:
    fichero = tmp_path / "anthropic_api_key.txt"
    fichero.write_text("  sk-ant-api03-de-prueba \n", encoding="utf-8")
    monkeypatch.setenv(config.VARIABLE_FICHERO_CLAVE, str(fichero))
    assert config.clave_api() == "sk-ant-api03-de-prueba"


@pytest.mark.parametrize("contenido", [None, "", "   \n", "no-es-una-clave",
                                       "sk-ant-dos\nlineas", "sk-ant- con espacios"])
def test_un_fichero_de_clave_malo_se_dice_sin_ensenarla(tmp_path, monkeypatch, capsys,
                                                         pdfs_ejemplo, contenido) -> None:
    fichero = tmp_path / "anthropic_api_key.txt"
    if contenido is not None:
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
    with sqlite3.connect(con_datos) as original, \
            sqlite3.connect(hecha.carpeta / "bms.sqlite3") as copiada:
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


def test_restaurar_vuelve_a_la_copia_y_guarda_lo_de_antes(con_datos, tmp_path, capsys) -> None:
    disco = tmp_path / "disco"
    disco.mkdir()
    hecha = copia.copiar(con_datos, disco)
    with sqlite3.connect(con_datos) as conn:
        eventos_copia = conn.execute("SELECT count(*) FROM evento").fetchone()[0]
    # Despues de la copia se sigue trabajando: la base tiene mas que la copia.
    with preparar(con_datos) as almacen:
        from bms_agent import permisos
        from bms_agent.auditoria import anclar

        permisos.asegurar_roles_base(almacen.conn)
        permisos.crear_usuario(almacen.conn, "Persona despues de la copia")
        anclar(almacen.conn, almacen.ruta_anclas)
    with sqlite3.connect(con_datos) as conn:
        eventos_despues = conn.execute("SELECT count(*) FROM evento").fetchone()[0]
    assert eventos_despues > eventos_copia
    assert main(["restaurar", str(hecha.carpeta), "--db", str(con_datos)]) == 0
    with sqlite3.connect(con_datos) as conn:
        assert conn.execute("SELECT count(*) FROM evento").fetchone()[0] == eventos_copia
    assert main(["db", "verificar", "--db", str(con_datos)]) == 0
    # Lo que habia antes de restaurar esta guardado entero, y se puede volver a ello.
    [antes] = list((con_datos.parent / "antes-de-restaurar").iterdir())
    with sqlite3.connect(antes / "bms.sqlite3") as conn:
        assert conn.execute("SELECT count(*) FROM evento").fetchone()[0] == eventos_despues
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
