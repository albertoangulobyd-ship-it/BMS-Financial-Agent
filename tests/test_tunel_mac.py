"""El Mac por el mini PC (paso 18b, docs/v1/paso-18/mac.md), solo en la variante Docker.

Lo que se puede probar aqui, en Linux, sin Windows ni macOS (mac.md §5.1): los pines de
docker/proteger.ps1 (la carpeta del proyecto protegida), y que lo que protege casa con lo que de
verdad escriben los scripts del ciclo automatico (paso 15); los de docker/mac.ps1 (el tunel en el
mini PC), sus funciones puras con pwsh y el script entero corrido con lo de Windows sustituido. Lo
que solo se ve en un Windows 11 o en un Mac de verdad esta en la lista de mac.md §5.2.

Las de pwsh se saltan sin el, como en test_instalacion_nativa.py; el codigo "sin comentarios ni
cadenas" es _codigo, como alli.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import RAIZ

DOCKER = RAIZ / "docker"
WINDOWS = RAIZ / "windows"
PWSH = shutil.which("pwsh")

# Los dos .ps1 de este paso que corren como administrador y no cargan comun.ps1.
ADMINISTRADOR = ("proteger", "mac")

SID_SISTEMA = "S-1-5-18"
SID_ADMINISTRADORES = "S-1-5-32-544"
# Los nombres de los grupos de Windows, en ingles, espanol y neerlandes: nunca por su nombre.
NOMBRES_DE_GRUPOS = ("Administrators", "Administradores", "Beheerders", "Users", "Usuarios",
                     "Gebruikers", "Everyone", "Todos", "Iedereen", "Authenticated Users")


def _ps1(carpeta: Path, nombre: str) -> str:
    return (carpeta / f"{nombre}.ps1").read_text(encoding="utf-8")


def _codigo(texto: str) -> str:
    """El script sin sus comentarios ni lo que va entre comillas: lo que de verdad se ejecuta."""
    sin_cadenas = re.sub(r'"(?:[^"`]|`.)*"|\'[^\']*\'', '""', texto)
    return "\n".join(linea.split("#", 1)[0] for linea in sin_cadenas.splitlines())


def _sin_comentarios(texto: str) -> str:
    return "\n".join(linea for linea in texto.splitlines() if not linea.lstrip().startswith("#"))


def _funcion(texto: str, nombre: str) -> str:
    """El cuerpo de una funcion de un .ps1 (hasta la llave que la cierra, en su columna)."""
    inicio = texto.index(f"function {nombre}")
    return texto[inicio:texto.index("\n}\n", inicio) + 3]


def _en_orden(texto: str, pasos: list[str]) -> None:
    """Cada paso aparece en el texto despues del anterior."""
    desde = 0
    for paso in pasos:
        encontrado = texto.find(paso, desde)
        assert encontrado >= 0, (paso, texto[desde:desde + 300])
        desde = encontrado + len(paso)


# ============================================================ los dos .bat y lo comun


@pytest.mark.parametrize("nombre", ADMINISTRADOR)
def test_los_bat_llaman_a_powershell_por_su_ruta(nombre) -> None:
    """cmd busca un programa nombrado sin ruta primero en la carpeta actual (la guia abre la
    terminal en docker\\): un powershell.cmd plantado ahi correria justo cuando se espera el aviso
    de administrador. Por eso, PowerShell por su ruta completa."""
    crudo = (DOCKER / f"{nombre}.bat").read_bytes()
    assert crudo.isascii() and b"\r\n" in crudo
    lineas = crudo.decode("ascii").splitlines()
    assert lineas[0] == "@echo off"
    assert lineas[-1] == "if errorlevel 1 pause"
    llamada = ('"%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -NoProfile '
               f'-ExecutionPolicy Bypass -File "%~dp0{nombre}.ps1" %*')
    assert llamada in lineas
    assert not [l for l in lineas if re.match(r"\s*powershell(\.exe)?\s", l, re.IGNORECASE)]
    assert [l for l in lineas if not l.lower().startswith("rem ")] == [
        "@echo off", llamada, "if errorlevel 1 pause"]


@pytest.mark.parametrize("nombre", ADMINISTRADOR)
def test_mac_ps1_no_carga_comun_ni_usa_docker(nombre) -> None:
    """Corren como administrador: no cargan comun.ps1 (que pone Set-Location y lo de Docker), no
    tocan Docker ni la pausa, y no ejecutan texto ni bajan nada."""
    texto = _ps1(DOCKER, nombre)
    assert texto.isascii()
    for prohibido in ("comun.ps1", "Comprobar-Docker", "Pausar-Automatico", "Tomar-Cerrojo"):
        assert prohibido not in _sin_comentarios(texto), prohibido
    codigo = _codigo(texto)
    assert not re.search(r"\bdocker\b", codigo, re.IGNORECASE)
    assert not re.search(r"Invoke-Expression|\biex\b|DownloadString|DownloadFile|"
                         r"Start-BitsTransfer|\bcurl\b|\bwget\b|Net\.WebClient|-EncodedCommand|"
                         r"Set-ExecutionPolicy|Invoke-RestMethod|-OutFile|"
                         r"Add-Type|ServerCertificateValidationCallback",
                         codigo, re.IGNORECASE)
    # Solo se pregunta a la app de este equipo (mac.bat -Estado), nunca a otro sitio.
    for linea in [l for l in texto.splitlines() if "Invoke-WebRequest" in l and
                  not l.lstrip().startswith("#")]:
        assert '-Uri ("http://127.0.0.1:" + $PuertoApp + "/consola")' in linea, linea
    # El base64 solo para mirar una clave publica (y su huella).
    sin = texto
    for funcion in ("Clave-Publica-Valida", "Huella-Sha256"):
        if f"function {funcion}" in sin:
            sin = sin.replace(_funcion(sin, funcion), "")
    assert "FromBase64String" not in _codigo(sin)
    # Lo que solo entiende PowerShell 7 (como los demas scripts de docker\).
    assert not re.search(r"&&|\|\||\?\?|\?\.|-Parallel|-AsPlainText|-AsHashtable|utf8NoBOM|"
                         r"\$PSStyle|GetRelativePath", codigo)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{6,}", texto)


@pytest.mark.parametrize("nombre", ADMINISTRADOR)
def test_las_ayudas_son_las_de_comun(nombre) -> None:
    """Escribir, Es-Si y Es-Administrador, copiadas con el mismo codigo (sin comentarios) que en
    docker/comun.ps1 y windows/comun.ps1: no cargan comun.ps1, pero dicen y preguntan igual."""
    texto = _ps1(DOCKER, nombre)
    comunes = {"docker": _ps1(DOCKER, "comun"), "windows": _ps1(WINDOWS, "comun")}
    for funcion, donde in (("Escribir", ("docker", "windows")), ("Es-Si", ("docker", "windows")),
                           ("Es-Administrador", ("windows",))):
        propia = _sin_comentarios(_funcion(texto, funcion))
        for carpeta in donde:
            assert propia == _sin_comentarios(_funcion(comunes[carpeta], funcion)), (funcion,
                                                                                     carpeta)


@pytest.mark.parametrize("nombre", ADMINISTRADOR)
def test_herramientas_del_sistema_por_su_ruta(nombre) -> None:
    """icacls (y en mac.ps1 taskkill, secedit y takeown) por su ruta en System32, y solo por su
    variable: nunca a pelo, que un icacls.cmd de la carpeta actual se colaria."""
    texto = _ps1(DOCKER, nombre)
    herramientas = {"Icacls": "icacls", "Taskkill": "taskkill", "Secedit": "secedit",
                    "Takeown": "takeown"}
    usadas = set(re.findall(r"^\$(Icacls|Taskkill|Secedit|Takeown) = ", texto, re.M))
    assert "Icacls" in usadas
    for variable in usadas:
        exe = herramientas[variable]
        assert f'${variable} = Join-Path $env:SystemRoot "System32\\{exe}.exe"\n' in texto
    codigo = _codigo(texto)
    for exe in herramientas.values():
        assert not re.search(rf"(?<![\w$-]){exe}(\.exe)?\b", codigo, re.IGNORECASE), exe
    # Cada llamada, con &: "& $Icacls ...".
    for variable in usadas:
        for m in re.finditer(rf"\${variable}\b", codigo):
            antes = codigo[max(0, m.start() - 2):m.start()]
            despues = codigo[m.end():m.end() + 3]
            assert antes == "& " or despues.startswith(" = "), (variable, antes, despues)
    assert "Stop-Process" not in codigo and not re.search(r"Get-Process\s+-Name\s+sshd", codigo)


@pytest.mark.parametrize("nombre", ADMINISTRADOR)
def test_por_sid_y_nunca_por_nombre(nombre) -> None:
    """Los permisos, por SID (*S-1-5-18, *S-1-5-32-544, "*" + el SID de una cuenta): un Windows
    en espanol o en neerlandes no llama igual a los grupos."""
    texto = _ps1(DOCKER, nombre)
    codigo = _codigo(texto)
    sin_comentarios = _sin_comentarios(texto)
    for grupo in NOMBRES_DE_GRUPOS:
        # (Solo-Administradores es el nombre de una funcion, no un grupo.)
        assert not re.search(rf"(?<![\w-]){grupo}\b", codigo), grupo
        assert f'"{grupo}' not in sin_comentarios, grupo
        assert not re.search(rf"\\{grupo}\b", sin_comentarios), grupo
    assert f'$SidSistema = "{SID_SISTEMA}"' in texto
    assert f'$SidAdministradores = "{SID_ADMINISTRADORES}"' in texto
    # Lo que va a icacls como cuenta: "*" + un SID (de las constantes o de una cuenta).
    for m in re.finditer(r'"\*"\s*\+\s*\$(\w+)', texto):
        assert m.group(1) in ("SidSistema", "SidAdministradores", "Dueno", "sidBms", "quien",
                              "Sid", "SidDeQuienLoAbre"), m.group(0)


@pytest.mark.skipif(PWSH is None, reason="sin pwsh")
def test_pwsh_analiza_mac_ps1() -> None:
    """Sin errores de sintaxis (el analizador de PowerShell; el de Windows PowerShell 5.1 solo
    esta en Windows, mac.md §5.2)."""
    ficheros = [DOCKER / f"{n}.ps1" for n in ADMINISTRADOR]
    lista = ", ".join("'" + str(f).replace("'", "''") + "'" for f in ficheros)
    guion = ("$e = [ordered]@{}; foreach ($f in @(" + lista + ")) { $t = $null; $x = $null; "
             "[System.Management.Automation.Language.Parser]::ParseFile($f, [ref]$t, [ref]$x) "
             "| Out-Null; $e[$f] = @($x | ForEach-Object { $_.Message }) }; "
             "$e | ConvertTo-Json -Depth 3")
    proceso = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command", guion],
                             capture_output=True, text=True, timeout=120)
    assert proceso.returncode == 0, proceso.stderr
    errores = json.loads(proceso.stdout)
    assert set(errores) == {str(f) for f in ficheros}
    assert {n: e for n, e in errores.items() if e} == {}


# ============================================================ proteger.ps1 (15b.0)


def _escribe_bms() -> list[str]:
    texto = _ps1(DOCKER, "proteger")
    m = re.search(r"^\$EscribeBms = @\(([^)]*)\)$", texto, re.M)
    assert m, "falta $EscribeBms"
    return re.findall(r'"([^"]+)"', m.group(1))


def test_proteger_escribe_bms_es_estado_y_secretos_del_correo() -> None:
    assert _escribe_bms() == ["docker\\estado", "docker\\secretos\\correo"]
    texto = _ps1(DOCKER, "proteger")
    # Lo que el Docker de "bms" monta (y no podria crear), creado vacio si falta: el buzon.
    assert '$MontaBms = @("buzon")\n' in texto
    compose = (DOCKER / "docker-compose.yml").read_text(encoding="utf-8")
    montajes = set(re.findall(r"^\s*- (\.\./[^:\s]+):", compose, re.M))
    assert montajes == {"../buzon"}
    assert "- ../buzon:/buzon:ro" in compose and not re.search(r"\.\./buzon:/buzon\s*$", compose,
                                                                re.M)


# Lo que escribe un script: el sitio de un New-Item, Set-Content, Remove-Item..., de una
# redireccion a un fichero, de [IO.File]::..., y un -v de Docker que no es de solo lectura (lo
# escribe el Docker Desktop de "bms").
_ESCRITURAS = [
    re.compile(r"\b(?:New-Item|Set-Content|Add-Content|Out-File|Remove-Item|Move-Item|Copy-Item|"
               r"Rename-Item|Clear-Content|Export-Clixml|Start-Transcript)\b[^\n|]*?"
               r"-(?:Literal|File)?Path\s+\(?(?:Join-Path\s+)?\$(?:script:)?(\w+)"),
    re.compile(r"\[(?:System\.)?IO\.(?:File|Directory)\]::\w+\(\s*\$(?:script:)?(\w+)"),
    re.compile(r"(?<![*\d])>>?\s*\$(?:script:)?(\w+)"),
    re.compile(r'-v\s+"\$\{(\w+)\}:(?![^"]*:ro")[^"]*"'),
]


def _rutas_escritas(textos: dict[str, str]) -> dict[str, set[str]]:
    """Cada variable en la que se escribe, con a que se refiere: una ruta de docker\\ (la de su
    Join-Path $PSScriptRoot "<x>", siguiendo las variables que salen de otra con Join-Path y los
    foreach sobre un Get-ChildItem), "HKCU:" (el registro de la cuenta) o "?" (no se sabe)."""
    juntos = "\n".join(_sin_comentarios(t) for t in textos.values())

    def resolver(nombre: str, vistos: frozenset = frozenset()) -> set[str]:
        if nombre == "null":
            return {"null"}
        if nombre in vistos:
            return {"?"}
        vistos = vistos | {nombre}
        rutas: set[str] = set()
        for m in re.finditer(rf"^\s*\$(?:script:)?{nombre}\s*=\s*(.+)$", juntos, re.M):
            valor = m.group(1).strip()
            raiz = re.fullmatch(r'Join-Path \$PSScriptRoot "([^"]+)"', valor)
            otra = re.match(r"Join-Path \$(?:script:)?(\w+)\b", valor)
            if raiz:
                rutas.add(raiz.group(1))
            elif otra:
                rutas |= resolver(otra.group(1), vistos)
            elif re.fullmatch(r'"HKCU:\\[^"]*"', valor):
                rutas.add("HKCU:")
            elif valor != "$null":
                rutas.add("?")
        for m in re.finditer(rf"foreach \(\${nombre} in @?\(?Get-ChildItem -LiteralPath "
                             r"\$(?:script:)?(\w+)", juntos):
            rutas |= resolver(m.group(1), vistos)
        return rutas or {"?"}

    escritas: dict[str, set[str]] = {}
    for texto in textos.values():
        codigo = _sin_comentarios(texto)
        for patron in _ESCRITURAS:
            for m in patron.finditer(codigo):
                escritas[m.group(1)] = resolver(m.group(1))
    return escritas


def test_proteger_deja_escribir_a_bms_justo_donde_escriben_los_scripts_del_paso_15() -> None:
    """mac.md §5.1: lo que escriben los scripts que corre "bms" (ciclo.ps1 y automatico.ps1, con
    comun.ps1) esta en $EscribeBms. Si un paso nuevo escribe en otro sitio, esta prueba falla y
    hay que anadirlo a $EscribeBms (o no escribir ahi)."""
    assert (DOCKER / "ciclo.ps1").exists(), "falta el paso 15"
    textos = {n: _ps1(DOCKER, n) for n in ("ciclo", "automatico", "comun")}
    escritas = _rutas_escritas(textos)
    # Lo que se sabe que escriben (si cambia, que se mire aqui).
    assert {"CarpetaEstado", "FicheroPausa", "FicheroCiclo", "CarpetaRegistroCiclo",
            "RegistroCiclo", "CarpetaSecretosCorreo", "ClaveTerminal"} <= set(escritas)
    permitidas = [r.removeprefix("docker\\") for r in _escribe_bms()]
    for variable, rutas in escritas.items():
        for ruta in rutas - {"HKCU:", "null"}:
            assert ruta != "?", f"no se sabe donde escribe ${variable}"
            assert any(ruta == p or ruta.startswith(p + "\\") for p in permitidas), (variable,
                                                                                    ruta)
    # El cerrojo tambien (se abre con [IO.File]::Open y se crea si falta).
    assert escritas["FicheroCerrojo"] == {"estado\\ciclo.cerrojo"}


def test_las_rutas_escritas_se_ven_aunque_cambien() -> None:
    """La prueba de arriba ve una escritura nueva fuera de lo protegido (y una que no sabe
    resolver), no solo las de hoy."""
    falso = {"comun": '$Otra = Join-Path $PSScriptRoot "buzon\\algo"\n'
                      '$Bien = Join-Path $PSScriptRoot "estado\\x"\n'
                      '$script:Hijo = Join-Path $Bien ("y" + $z)\n'
                      'function F { Set-Content -LiteralPath $Otra -Value 1 }\n'
                      'function G { Add-Content -LiteralPath $script:Hijo -Value 1 }\n'
                      'function H { "x" | Out-File -FilePath $Raro }\n'
                      'function I { [System.IO.File]::WriteAllText($Bien, "x") }\n'
                      '$SoloLeer = Join-Path $PSScriptRoot "secretos"\n'
                      '$Montada = Join-Path $PSScriptRoot "datos"\n'
                      'function J { docker compose run -v "${Montada}:/o" orden x }\n'
                      'function K { docker compose run -v "${SoloLeer}:/o:ro" orden x }\n'
                      'function L { foreach ($f in @(Get-ChildItem -LiteralPath $Otra)) '
                      '{ Remove-Item -LiteralPath $f.FullName } }\n'}
    escritas = _rutas_escritas(falso)
    assert escritas["Otra"] == {"buzon\\algo"} and escritas["Hijo"] == {"estado\\x"}
    assert escritas["Bien"] == {"estado\\x"} and escritas["f"] == {"buzon\\algo"}
    assert escritas["Raro"] == {"?"} and escritas["Montada"] == {"datos"}
    assert "SoloLeer" not in escritas


def test_proteger_en_orden_y_con_los_cuatro_permisos() -> None:
    """mac.md §2.12 y anexo D: las comprobaciones antes de preguntar; preguntar antes de pedir
    ser administrador; ya como administrador, el dueno, la raiz sin herencia con los cuatro, lo
    de dentro que hereda y la M de "bms" solo donde escribe."""
    texto = _ps1(DOCKER, "proteger")
    codigo = _sin_comentarios(texto)
    _en_orden(codigo, [
        "[Environment]::Is64BitProcess",
        "Dentro-De $Proyecto $prohibida",
        "[IO.Path]::GetPathRoot($Proyecto) -eq $Proyecto",
        "Dentro-De $Proyecto $perfiles",
        "Enlace-Dentro $Proyecto",
        "Get-LocalUser -Name $Usuario",
        "if ($sidBms -eq $Dueno) { Fallar",
        "Grupos-De-La-Cuenta $cuenta.Name",
        "if ($grupos -contains $SidAdministradores) { Fallar",
        'Read-Host "Seguir?',
        "-Verb RunAs",
        '"/setowner", $administradores, "/T", "/C", "/L"',
        '"/inheritance:r", "/grant:r"',
        '"/remove:g"',
        '"/reset", "/T", "/C", "/L"',
        '"/grant", ("*" + $sidBms + ":(OI)(CI)M")',
        "(Get-Acl -LiteralPath $Proyecto).Access",
    ])
    # La raiz: exactamente SYSTEM F, Administradores F, el dueno M y "bms" RX.
    linea = re.search(r'Cambiar-Permisos @\(\$Proyecto, "/inheritance:r", "/grant:r", (.*?), "/Q"\)',
                      codigo, re.S)
    concedidos = [c.strip() for c in linea.group(1).replace("\n", " ").split(",")]
    assert concedidos == ['($sistema + ":(OI)(CI)F")', '($administradores + ":(OI)(CI)F")',
                          '("*" + $Dueno + ":(OI)(CI)M")', '("*" + $sidBms + ":(OI)(CI)RX")']
    # La M de "bms", solo en $EscribeBms (y nada mas se concede).
    grants = re.findall(r'"/grant(?::r)?"', codigo)
    assert len(grants) == 2
    cuarto = codigo[codigo.index("foreach ($r in $EscribeBms)"):]
    assert '"/grant", ("*" + $sidBms + ":(OI)(CI)M")' in cuarto[:cuarto.index("\n}\n")]
    # Se para si la cuenta es administradora o es quien lo abre; el dueno es un SID de cuenta.
    assert "'^S-1-5-21-\\d+-\\d+-\\d+-\\d+$'" in texto
    # Lo que llega a la ventana de administrador se vuelve a mirar ahi (las comprobaciones estan
    # fuera del if (-not $Elevado)).
    elevar = codigo.index("if (-not $Elevado)")
    assert codigo.index("Grupos-De-La-Cuenta $cuenta.Name") < elevar
    assert '"-Usuario", $sidBms, "-Dueno", $Dueno, "-Elevado"' in codigo
    # Nada en la nativa ni fuera del proyecto: no hay copia en windows\.
    assert not (WINDOWS / "proteger.ps1").exists() and not (WINDOWS / "proteger.bat").exists()


# ------------------------------------------------------------ proteger.ps1 con pwsh

# Lo que sustituye a Windows, puesto en la copia del script tras $ErrorActionPreference:
# Get-LocalUser y Get-Acl (no estan en pwsh de Linux) y los grupos de la cuenta (sin ADSI). Un
# icacls falso (por $env:SystemRoot) apunta cada orden y lleva la ACL de la raiz en un JSON.
SUSTITUTOS = r"""
function Get-LocalUser {
    [CmdletBinding()] param([string]$Name, [string]$SID)
    foreach ($x in @(Get-Content -LiteralPath $env:PRUEBA_USUARIOS -Raw | ConvertFrom-Json)) {
        if (($Name -and $x.Name -eq $Name) -or ($SID -and $x.SID -eq $SID)) {
            return [pscustomobject]@{ Name = $x.Name; SID = [pscustomobject]@{ Value = $x.SID } }
        }
    }
    return $null
}
function Get-Acl {
    [CmdletBinding()] param([string]$LiteralPath)
    $reglas = @()
    foreach ($r in @(Get-Content -LiteralPath $env:PRUEBA_ACL -Raw | ConvertFrom-Json)) {
        $id = [pscustomobject]@{ Sid = $r.sid }
        $id | Add-Member -MemberType ScriptMethod -Name Translate -Value { param($Tipo) [pscustomobject]@{ Value = $this.Sid } }
        $reglas += [pscustomobject]@{ IdentityReference = $id; IsInherited = [bool]$r.heredada; AccessControlType = $r.tipo }
    }
    return [pscustomobject]@{ Access = $reglas }
}
"""

ICACLS_FALSO = """#!{python}
import json, os, sys
argumentos = sys.argv[1:]
with open(os.environ["PRUEBA_ICACLS"], "a", encoding="utf-8") as f:
    f.write(json.dumps(argumentos) + "\\n")
raiz = os.environ["PRUEBA_RAIZ"]
if argumentos and argumentos[0] == raiz:
    with open(os.environ["PRUEBA_ACL"], encoding="utf-8") as f:
        acl = json.load(f)
    if "/inheritance:r" in argumentos:
        acl = [r for r in acl if not r["heredada"]]
    if "/grant:r" in argumentos:
        concedidos = [a.split(":")[0].lstrip("*") for a in argumentos if a.startswith("*")]
        acl = [r for r in acl if r["sid"] not in concedidos]
        acl += [{{"sid": s, "heredada": False, "tipo": "Allow"}} for s in concedidos]
    if "/remove:g" in argumentos:
        quitar = argumentos[argumentos.index("/remove:g") + 1].lstrip("*")
        if quitar not in os.environ.get("PRUEBA_NO_SE_QUITA", "").split(","):
            acl = [r for r in acl if r["sid"] != quitar]
    with open(os.environ["PRUEBA_ACL"], "w", encoding="utf-8") as f:
        json.dump(acl, f)
sys.exit(int(os.environ.get("PRUEBA_ICACLS_CODIGO", "0")))
"""

BMS = "S-1-5-21-1111-2222-3333-1002"
DUENO = "S-1-5-21-1111-2222-3333-1001"


class Proteger:
    """Una copia del proyecto (docker\\proteger.ps1 y unas carpetas) con lo falso de Windows."""

    def __init__(self, raiz: Path, carpeta: str = "proyecto") -> None:
        self.raiz = raiz
        self.proyecto = raiz / carpeta
        (self.proyecto / "docker" / "secretos").mkdir(parents=True)
        (self.proyecto / "src").mkdir()
        (self.proyecto / "docker" / "iniciar.ps1").write_text("# x\n", encoding="ascii")
        shutil.copy(DOCKER / "proteger.ps1", self.proyecto / "docker" / "proteger.ps1")
        self.parchear('$ErrorActionPreference = "Continue"\n',
                      '$ErrorActionPreference = "Continue"\n' + SUSTITUTOS)
        self.parchear("    # Igual que en mac.ps1: por ADSI y por SID; si no se puede mirar, lanza.\n",
                      "    if ($env:PRUEBA_GRUPOS -eq 'falla') { throw 'ADSI' }\n"
                      "    return @($env:PRUEBA_GRUPOS -split ',')\n")
        sistema = raiz / "Windows" / "System32"
        sistema.mkdir(parents=True)
        icacls = sistema / "icacls.exe"
        icacls.write_text(ICACLS_FALSO.format(python=sys.executable), encoding="utf-8")
        icacls.chmod(0o755)
        self.usuarios = [{"Name": "bms", "SID": BMS}, {"Name": "yo", "SID": DUENO}]
        self.grupos = "S-1-5-32-545"
        # La raiz, como la deja una carpeta nueva en C:\ (hereda Usuarios autenticados).
        self.acl = [{"sid": "S-1-5-11", "heredada": True, "tipo": "Allow"},
                    {"sid": SID_SISTEMA, "heredada": True, "tipo": "Allow"}]
        self.entorno_extra: dict[str, str] = {}

    def parchear(self, antes: str, despues: str) -> None:
        fichero = self.proyecto / "docker" / "proteger.ps1"
        texto = fichero.read_bytes().decode("ascii").replace("\r\n", "\n")
        assert texto.count(antes) == 1, antes
        fichero.write_bytes(texto.replace(antes, despues).replace("\n", "\r\n").encode("ascii"))

    def correr(self, *argumentos: str, entrada: str = "\n\n") -> subprocess.CompletedProcess:
        (self.raiz / "usuarios.json").write_text(json.dumps(self.usuarios), encoding="utf-8")
        (self.raiz / "acl.json").write_text(json.dumps(self.acl), encoding="utf-8")
        (self.raiz / "icacls.log").write_text("", encoding="utf-8")
        entorno = {**os.environ, "SystemRoot": str(self.raiz / "Windows"),
                   "PRUEBA_USUARIOS": str(self.raiz / "usuarios.json"),
                   "PRUEBA_ACL": str(self.raiz / "acl.json"),
                   "PRUEBA_ICACLS": str(self.raiz / "icacls.log"),
                   "PRUEBA_RAIZ": str(self.proyecto), "PRUEBA_GRUPOS": self.grupos,
                   "USERPROFILE": str(self.raiz / "Users" / "yo"), **self.entorno_extra}
        for variable in ("ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
            entorno.pop(variable, None)
        return subprocess.run(
            [PWSH, "-NoProfile", "-File", str(self.proyecto / "docker" / "proteger.ps1"),
             *argumentos], env=entorno, input=entrada, capture_output=True, text=True,
            timeout=180)

    def icacls(self) -> list[list[str]]:
        texto = (self.raiz / "icacls.log").read_text(encoding="utf-8")
        return [json.loads(l) for l in texto.splitlines()]

    def acl_final(self) -> list[dict]:
        return json.loads((self.raiz / "acl.json").read_text(encoding="utf-8"))


@pytest.fixture
def proteger(tmp_path):
    if PWSH is None:
        pytest.skip("sin pwsh")
    return Proteger(tmp_path)


def _elevado(p: Proteger, *mas: str) -> subprocess.CompletedProcess:
    return p.correr("-Elevado", "-Usuario", BMS, "-Dueno", DUENO, *mas)


def test_pwsh_proteger_pone_los_permisos_en_orden(proteger) -> None:
    proceso = _elevado(proteger)
    assert proceso.returncode == 0, proceso.stdout + proceso.stderr
    p = str(proteger.proyecto)
    llamadas = proteger.icacls()
    assert llamadas[0] == [p, "/setowner", "*S-1-5-32-544", "/T", "/C", "/L", "/Q"]
    assert llamadas[1] == [p, "/inheritance:r", "/grant:r", "*S-1-5-18:(OI)(CI)F",
                           "*S-1-5-32-544:(OI)(CI)F", f"*{DUENO}:(OI)(CI)M", f"*{BMS}:(OI)(CI)RX",
                           "/Q"]
    # Lo de dentro (tambien el buzon, que se crea vacio) hereda solo eso.
    hijos = sorted(Path(l[0]).name for l in llamadas if l[1:2] == ["/reset"])
    assert hijos == ["buzon", "docker", "src"]
    assert all(l[1:] == ["/reset", "/T", "/C", "/L", "/Q"] for l in llamadas
               if l[1:2] == ["/reset"])
    # La M de "bms", al final y solo en docker\estado y docker\secretos\correo (que se crean).
    assert llamadas[-2:] == [
        [str(proteger.proyecto / "docker" / "estado"), "/grant", f"*{BMS}:(OI)(CI)M", "/Q"],
        [str(proteger.proyecto / "docker" / "secretos" / "correo"), "/grant",
         f"*{BMS}:(OI)(CI)M", "/Q"]]
    assert len(llamadas) == 2 + 3 + 2
    assert (proteger.proyecto / "docker" / "estado").is_dir()
    assert (proteger.proyecto / "docker" / "secretos" / "correo").is_dir()
    assert (proteger.proyecto / "buzon").is_dir()
    assert sorted(r["sid"] for r in proteger.acl_final()) == sorted(
        [SID_SISTEMA, SID_ADMINISTRADORES, DUENO, BMS])
    assert "Listo:" in proceso.stdout


def test_pwsh_proteger_quita_lo_puesto_a_mano_y_para_si_no_se_puede(proteger) -> None:
    proteger.acl.append({"sid": "S-1-1-0", "heredada": False, "tipo": "Allow"})
    proceso = _elevado(proteger)
    assert proceso.returncode == 0, proceso.stdout + proceso.stderr
    assert [str(proteger.proyecto), "/remove:g", "*S-1-1-0", "/Q"] in proteger.icacls()
    proteger.entorno_extra["PRUEBA_NO_SE_QUITA"] = "S-1-1-0"
    proceso = _elevado(proteger)
    assert proceso.returncode == 1
    assert "S-1-1-0 que no se pueden quitar" in proceso.stdout


def test_pwsh_proteger_para_si_icacls_falla(proteger) -> None:
    proteger.entorno_extra["PRUEBA_ICACLS_CODIGO"] = "5"
    proceso = _elevado(proteger)
    assert proceso.returncode == 1 and len(proteger.icacls()) == 1
    assert "No se han podido poner los permisos (icacls" in proceso.stdout


@pytest.mark.parametrize("caso", ["administrador", "el_mismo", "no_existe", "grupos_falla",
                                  "sin_usuario", "dueno_malo"])
def test_pwsh_proteger_para_sin_tocar_nada_con_una_cuenta_que_no_vale(proteger, caso) -> None:
    argumentos = ["-Elevado", "-Usuario", BMS, "-Dueno", DUENO]
    esperado = {"administrador": "es administrador", "el_mismo": "tiene que ser otro",
                "no_existe": "No hay ningun usuario local", "grupos_falla":
                "No se han podido mirar los grupos", "sin_usuario": "Di el usuario",
                "dueno_malo": "-Dueno no es un SID"}[caso]
    if caso == "administrador":
        proteger.grupos = "S-1-5-32-545,S-1-5-32-544"
    elif caso == "el_mismo":
        argumentos[4] = BMS
    elif caso == "no_existe":
        argumentos[2] = "nadie"
    elif caso == "grupos_falla":
        proteger.grupos = "falla"
    elif caso == "sin_usuario":
        argumentos[1:3] = []
    else:
        argumentos[4] = "S-1-5-32-544"
    proceso = proteger.correr(*argumentos)
    assert proceso.returncode == 1 and proteger.icacls() == []
    assert esperado in proceso.stdout, proceso.stdout + proceso.stderr
    assert not (proteger.proyecto / "docker" / "estado").exists()


def test_pwsh_proteger_por_su_nombre_y_preguntando(proteger) -> None:
    """Sin elevar: pregunta antes de nada y, sin "si", no toca nada (ni pide administrador)."""
    proceso = proteger.correr("-Usuario", "bms", "-Dueno", DUENO, entrada="no\n")
    assert proceso.returncode == 1 and proteger.icacls() == []
    assert "No se ha cambiado nada." in proceso.stdout
    assert "escribir en docker\\estado y docker\\secretos\\correo" in proceso.stdout


def test_pwsh_proteger_no_entra_en_un_enlace(proteger) -> None:
    """Un enlace dentro (aunque este hondo): icacls /T entraria en el sitio al que apunta y "bms"
    podria acabar escribiendo fuera del proyecto. Se para sin tocar nada."""
    (proteger.proyecto / "docker" / "estado").mkdir()
    fuera = proteger.raiz / "fuera"
    fuera.mkdir()
    (proteger.proyecto / "docker" / "estado" / "registro").symlink_to(fuera)
    proceso = _elevado(proteger)
    assert proceso.returncode == 1 and proteger.icacls() == []
    assert "es un enlace a otro sitio" in proceso.stdout


@pytest.mark.parametrize("donde", ["perfiles", "raiz_del_sistema"])
def test_pwsh_proteger_no_en_una_carpeta_que_no_vale(tmp_path, donde) -> None:
    if PWSH is None:
        pytest.skip("sin pwsh")
    if donde == "perfiles":
        p = Proteger(tmp_path, "Users/otro/proyecto")
    else:
        p = Proteger(tmp_path, "Windows/proyecto")
    proceso = _elevado(p)
    assert proceso.returncode == 1 and p.icacls() == []
    assert "la carpeta del proyecto no puede estar en" in proceso.stdout.lower()


def test_lo_que_escriben_de_verdad_el_ciclo_y_la_pausa_esta_en_escribe_bms(tmp_path) -> None:
    """Corrido: un ciclo entero (con el correo y una lectura automatica), la pausa y la vuelta,
    con un docker falso (test_ciclo_docker.py). Lo que cambia en la carpeta del proyecto esta
    todo en $EscribeBms."""
    if PWSH is None:
        pytest.skip("sin pwsh")
    from test_ciclo_docker import Ciclo, _puerto_libre

    if not _puerto_libre():
        pytest.skip("el puerto 8765 esta en uso (hay una consola en marcha)")
    ciclo = Ciclo(tmp_path)
    ciclo.correo()
    ciclo.clave()
    proyecto = ciclo.docker.parent
    # Como las deja proteger.ps1: ya creadas ("bms" no puede crear nada en docker\).
    for carpeta in _escribe_bms():
        (proyecto / carpeta.replace("\\", "/")).mkdir(parents=True, exist_ok=True)

    def foto() -> dict[str, tuple[int, int]]:
        return {str(f.relative_to(proyecto)).replace("/", "\\"): (f.stat().st_mtime_ns,
                                                                  f.stat().st_size)
                for f in proyecto.rglob("*")}

    antes = foto()
    proceso, ordenes = ciclo.correr([["lectura siguiente", 0, ""],
                                     ["lectura tomar --automatica", 0, "17"]])
    assert proceso.returncode == 0, proceso.stdout + proceso.stderr
    for accion in ("-Pausar", "-Reanudar"):
        proceso, _ordenes = ciclo.script("automatico", accion)
        assert proceso.returncode == 0, proceso.stdout + proceso.stderr
    despues = foto()
    cambiadas = {r for r in set(despues) | set(antes) if antes.get(r) != despues.get(r)}
    assert cambiadas, "el ciclo no ha escrito nada"
    permitidas = _escribe_bms()
    fuera = {r for r in cambiadas
             if not any(r.startswith(p + "\\") or r == p for p in permitidas)}
    assert fuera == set()
    assert any(r.startswith("docker\\estado\\registro\\") for r in cambiadas)
    assert "docker\\estado\\ciclo.json" in cambiadas


# ============================================================ mac.ps1 (15b.1): los pines


def _mac() -> str:
    return _ps1(DOCKER, "mac")


def _flujo() -> str:
    """Lo que corre el script fuera de las funciones: la entrada y las acciones."""
    texto = _sin_comentarios(_mac())
    return texto[texto.index("$acciones = @()"):]


def _accion(nombre: str) -> str:
    """El bloque de una accion del switch (hasta la siguiente)."""
    flujo = _flujo()
    inicio = flujo.index(f'    "{nombre}" {{\n')
    fin = flujo.find('\n    "', inicio + 10)
    return flujo[inicio:fin if fin > 0 else len(flujo)]


def test_mac_solo_en_docker() -> None:
    """La decision del dueno: el Mac solo con la variante Docker. Ni mac.ps1 ni mac.bat en
    windows\\ (mac.md §2.1 los pedia iguales alli), y nada de la nativa cambia (15b.3 no va)."""
    assert (DOCKER / "mac.ps1").is_file() and (DOCKER / "mac.bat").is_file()
    assert not list(WINDOWS.glob("mac.*"))
    for nombre in ("instalar", "desinstalar", "comprobar"):
        assert "TunelMac" not in _ps1(WINDOWS, nombre) and "bms-tunel" not in _ps1(WINDOWS,
                                                                                  nombre)


def test_lo_de_sshd_se_escribe_sin_bom() -> None:
    texto = _mac()
    escribir = _funcion(texto, "Escribir-Ascii")
    assert "[IO.File]::WriteAllText($Ruta, $Texto, (New-Object Text.UTF8Encoding($false)))" in escribir
    codigo = _codigo(texto)
    for prohibido in ("Out-File", "Set-Content", "Add-Content", "Export-Clixml", "Tee-Object"):
        assert prohibido not in codigo, prohibido
    # Ninguna redireccion a un fichero: solo 2>&1 y 2>$null.
    assert set(re.findall(r"\S*>\S*", codigo)) <= {"2>&1", "2>$null"}
    # Las otras dos, las plantillas de secedit (UTF-16, como las exporta), en Negar-Inicios.
    assert len(re.findall(r"WriteAllText\(", texto)) == 3
    negar = _funcion(texto, "Negar-Inicios")
    assert ("[IO.File]::WriteAllText($nueva, (Texto-Negaciones $textoAntes $Sid -Quitar:$Quitar), "
            "[Text.Encoding]::Unicode)") in negar
    assert ("[IO.File]::WriteAllText($vuelta, (Texto-Vuelta $derechosAntes $derechosDespues), "
            "[Text.Encoding]::Unicode)") in negar


def test_aplicar_falla_cerrado() -> None:
    """mac.md §2.8: primero se cierra todo; lo nuevo se escribe y se comprueba con el propio sshd;
    solo al final se arranca y se abre a los Mac. Si algo falla antes, sshd queda parado y el
    cortafuegos cerrado (Fallar sale del script)."""
    aplicar = _sin_comentarios(_funcion(_mac(), "Aplicar"))
    _en_orden(aplicar, [
        "Poner-Reglas -Cerrado",
        "Stop-Service -Name sshd -Force",
        "$script:Quedan = Parar-Tuneles",
        "$pegas = @(Carpeta-Ssh-Segura)",
        "if ($pegas.Count -gt 0) { Fallar",
        "Escribir-Ascii $FicheroClaves (Texto-Claves $macs)",
        "Solo-Administradores $FicheroClaves",
        "Escribir-Ascii $ConfigNueva (Texto-Config $macs)",
        "& $Sshd -t -f $ConfigNueva",
        "if ($LASTEXITCODE -ne 0) {",
        "Fallar",
        "Move-Item -LiteralPath $ConfigNueva -Destination $Config -Force",
        "$mal = Comprobar-Lo-Que-Se-Aplica $macs",
        "if ($mal) { Fallar",
        "Set-Service -Name sshd -StartupType Automatic",
        "Start-Service -Name sshd",
        "if (-not (Esperar-Escucha 20)) { Fallar",
        "Poner-Reglas $macs",
        "ATENCION: queda",
    ])
    # Apagado: ni se arranca ni se abre (el "resto" se queda con Any).
    apagado = aplicar[aplicar.index("if ($E.apagado) {"):aplicar.index("} else {")]
    assert "Start-Service" not in apagado and "Poner-Reglas" not in apagado
    assert "Set-Service -Name sshd -StartupType Disabled" in apagado
    # Cerrado: "resto" bloquea a todos (Any) y la de los Mac no se pone.
    reglas = _funcion(_mac(), "Poner-Reglas")
    assert '$bloqueados = @("Any")' in reglas and "if (-not $abierto) { return }" in reglas


def test_parar_tuneles() -> None:
    texto = _mac()
    procesos = _funcion(texto, "Procesos-De-Sshd")
    assert "Get-CimInstance Win32_Process -Filter \"Name LIKE 'sshd%'\"" in procesos
    assert "$_.ExecutablePath.StartsWith($carpeta, [StringComparison]::OrdinalIgnoreCase)" in procesos
    parar = _funcion(texto, "Parar-Tuneles")
    assert "& $Taskkill /F /PID ([int]$p.ProcessId)" in parar
    assert "for ($i = 0; $i -lt 10; $i++) {" in parar and "Procesos-De-Sshd).Count -eq 0) { return 0 }" in parar
    assert parar.rstrip().endswith("return @(Procesos-De-Sshd).Count\n}")
    quitar = _accion("Quitar")
    assert quitar.index("Stop-Service -Name sshd") < quitar.index("Parar-Tuneles")
    # -Estado dice cuantos procesos de sshd hay y que tuneles estan abiertos.
    estado = _funcion(texto, "Mostrar-Estado")
    assert "@(Procesos-De-Sshd).Count" in estado
    assert "Get-NetTCPConnection -LocalPort 22 -State Established" in estado


def test_instalar_en_orden() -> None:
    """mac.md §2.8, -Instalar ya elevado: lo que para sin tocar nada, la pregunta, la foto de
    antes, y solo entonces la capacidad, el cortafuegos cerrado antes de arrancar nada, la carpeta
    de fiar, la clave del equipo, la cuenta y Aplicar."""
    _en_orden(_accion("Instalar"), [
        'if ($tipo -eq "otra" -and -not $SustituirConfiguracion) {',
        "Fallar",
        "$servicio.PathName",
        "Fallar",
        "$lee = Lectores-De-Datos (Rutas-De-Datos) $sidTunel",
        "if ($lee) {",
        "Fallar",
        'Read-Host "Seguir?',
        "antes = (Foto-De-Antes)",
        "Guardar-Estado $EstadoDelTunel",
        "Add-WindowsCapability -Online -Name $Capacidad",
        "Get-NetFirewallRule -Name $ReglaMicrosoft -ErrorAction SilentlyContinue | Disable-NetFirewallRule",
        "Poner-Reglas -Cerrado",
        "$pegas = @(Carpeta-Ssh-Segura)",
        'Read-Host "Apartarla?',
        "Apartar-Carpeta-Ssh",
        "Start-Service -Name sshd",
        "Stop-Service -Name sshd -Force",
        "$pegas = @(Carpeta-Ssh-Segura)",
        "Fallar",
        "Copy-Item -LiteralPath $Config -Destination $ConfigAntes",
        "Asegurar-Cuenta",
        "Aplicar $EstadoDelTunel",
        "Decir-Para-El-Mac",
    ])


def test_no_se_eleva_sin_mirar_quien_puede_cambiar() -> None:
    """mac.md §2.11: antes de pedir ser administrador (y otra vez ya elevado, porque la
    comprobacion esta fuera del if), que nadie mas pueda cambiar mac.ps1, mac.bat ni lo de mac\\;
    y lo del Mac solo se copia despues."""
    flujo = _flujo()
    _en_orden(flujo, [
        "$ficheros = @($PSCommandPath, (Join-Path $PSScriptRoot \"mac.bat\"))",
        "$carpetas = @($PSScriptRoot)",
        "$ficheros += @($FicherosDelMac | ForEach-Object { Join-Path $CarpetaDelMac $_ })",
        "$carpetas += $CarpetaDelMac",
        "$quien = Quien-Mas-Puede-Cambiar $ficheros $carpetas $Usuario",
        "if ($quien) {",
        "Fallar",
        'if ($accion -eq "CopiarParaElMac") { Copiar-Para-El-Mac $CopiarParaElMac; exit 0 }',
        "if (-not $Elevado) {",
        "Pedir-Mac",
        "-Verb RunAs",
    ])
    assert flujo.count("Quien-Mas-Puede-Cambiar") == 1
    assert flujo.index("Quien-Mas-Puede-Cambiar") < flujo.index("if (-not $Elevado) {")
    texto = _mac()
    assert ('$FicherosDelMac = @("preparar.command", "abrir-bms.command", "LEEME.txt")'
            in texto)
    assert '$CarpetaDelMac = Join-Path (Split-Path -Parent $PSScriptRoot) "mac"' in texto
    assert ('$SidTrustedInstaller = "S-1-5-80-956008885-3418522649-1831038044-1853292631-'
            '2271478464"') in texto
    quien = _funcion(texto, "Quien-Mas-Puede-Cambiar")
    assert ("$permitidos = @($SidSistema, $SidAdministradores, $SidTrustedInstaller, "
            "$SidDeQuienLoAbre)") in quien
    en_su_carpeta = re.search(r'\$enSuCarpeta = \[[^\]]+\]"([^"]+)"', quien).group(1)
    assert {"CreateFiles", "CreateDirectories", "Delete", "DeleteSubdirectoriesAndFiles",
            "ChangePermissions", "TakeOwnership"} <= {x.strip() for x in en_su_carpeta.split(",")}
    en_fichero = re.search(r'\$enFichero = \[[^\]]+\]"([^"]+)"', quien).group(1)
    assert {"WriteData", "AppendData", "WriteAttributes", "Delete", "ChangePermissions",
            "TakeOwnership"} <= {x.strip() for x in en_fichero.split(",")}
    assert "GetOwner(" in quien and "ReparsePoint" in quien and "InheritOnly" in quien
    # Lo del Mac se copia sin administrador y despues de la comprobacion.
    copiar = _funcion(texto, "Copiar-Para-El-Mac")
    assert "Copy-Item -LiteralPath (Join-Path $CarpetaDelMac $f)" in copiar


def test_lo_del_mac_se_pregunta_antes_de_elevar() -> None:
    """mac.md §2.13: la ventana de administrador no recibe ficheros arrastrados (UIPI): lo del
    Mac se pregunta antes, y lo que pasa a la de administrador se vuelve a validar alli."""
    texto = _mac()
    flujo = _flujo()
    preguntas = flujo[flujo.index("if (-not $Elevado) {"):flujo.index("if (-not (Es-Administrador)) {")]
    for llamada in ("Pedir-Mac $leido", "Elegir-Mac $leido"):
        assert llamada in preguntas
        assert flujo.count(llamada.split()[0] + " ") == 1, llamada
    assert "arrastra" not in _sin_comentarios(texto).lower()
    elevado = flujo[flujo.index("-Verb RunAs"):]
    _en_orden(elevado, ["$origen = Origen-Valido $Ip",
                        '$completa = Clave-Publica-Valida ("ssh-ed25519 " + $Clave)',
                        "if (-not $origen -or -not $completa) { Fallar",
                        "$nuevoMac = [pscustomobject][ordered]@{ nombre = $Nombre; ip = $origen; "
                        "clave = $completa;"])
    assert "if ($Usuario -notmatch '^S-1-5-21-\\d+-\\d+-\\d+-\\d+$') { Fallar" in flujo
    assert ("if ($Nombre -and $Nombre -notmatch $PatronNombre) { Fallar" in flujo and
            "$PatronNombre = '^[a-z0-9][a-z0-9-]{0,30}$'" in texto)
    # A la ventana de administrador solo pasan el nombre, la IP, el base64 de la clave y si es la
    # misma; con -MismaClave, la clave tiene que ser la que ya tenia ese Mac.
    assert "$Clave = $m.clave.Split(\" \")[1]" in flujo
    assert "$deAntes[0].clave -ne $nuevoMac.clave" in flujo


def test_las_reglas_del_cortafuegos() -> None:
    texto = _mac()
    codigo = _sin_comentarios(texto)
    nuevas = re.findall(r"New-NetFirewallRule (.*?)\| Out-Null", codigo, re.S)
    assert len(nuevas) == 2
    for regla in nuevas:
        regla = " ".join(regla.replace("`", " ").split())
        for trozo in ("-Direction Inbound", "-Protocol TCP -LocalPort 22 -Program $Sshd",
                      "-Profile Any"):
            assert trozo in regla, (trozo, regla)
    acciones = sorted(" ".join(r.split()) for r in nuevas)
    assert any("-Name $ReglaResto" in r and "-Action Block" in r and
               "-RemoteAddress $bloqueados" in r for r in acciones)
    assert any("-Name $ReglaMac " in r and "-Action Allow" in r and
               "-RemoteAddress $origenes" in r for r in acciones)
    for prohibido in ("Set-NetConnectionProfile", "Set-NetFirewallProfile", "-Profile Private",
                      "-Profile Public", "NetworkCategory Private"):
        assert prohibido not in codigo, prohibido
    for linea in [l for l in codigo.splitlines() if "Remove-NetFirewallRule" in l]:
        assert re.search(r"-Name \$(ReglaMac|ReglaResto|ReglaMicrosoft) ", linea), linea
    assert codigo.count("-Name $ReglaMicrosoft -ErrorAction SilentlyContinue | Remove-NetFirewallRule") == 1
    # La de Microsoft solo se borra en -Quitar (y si la capacidad no estaba antes); si no, se apaga.
    assert ("-Name $ReglaMicrosoft -ErrorAction SilentlyContinue | Remove-NetFirewallRule"
            in _accion("Quitar"))
    for linea in [l for l in codigo.splitlines() if "able-NetFirewallRule" in l]:
        assert "$ReglaMicrosoft" in linea, linea
    assert '$ReglaMac = "BMS-Tunel-Mac-sshd"' in texto
    assert '$ReglaResto = "BMS-Tunel-Mac-sshd-resto"' in texto
    assert '$ReglaMicrosoft = "OpenSSH-Server-In-TCP"' in texto


def test_la_cuenta() -> None:
    texto = _mac()
    sin = _sin_comentarios(texto)
    nueva = " ".join(re.search(r"New-LocalUser (.*?)\| Out-Null", sin, re.S).group(1)
                     .replace("`", " ").split())
    for trozo in ("-Name $Cuenta", "-Password (Contrasena-Que-Nadie-Guarda)",
                  "-PasswordNeverExpires", "-AccountNeverExpires", "-UserMayNotChangePassword"):
        assert trozo in nueva, trozo
    assert "Add-LocalGroupMember" not in sin and "Get-LocalGroupMember" not in sin
    assert sin.count("Contrasena-Que-Nadie-Guarda") == 2  # la funcion y New-LocalUser
    contrasena = _funcion(sin, "Contrasena-Que-Nadie-Guarda")
    for prohibido in ("Escribir", "Write-", "Set-ItemProperty", "Guardar-Estado", "Out-", "$env:"):
        assert prohibido not in contrasena, prohibido
    assert "[Security.Cryptography.RandomNumberGenerator]::Create()" in contrasena
    grupos = _funcion(texto, "Grupos-De-La-Cuenta")
    assert '[ADSI]("WinNT://" + $env:COMPUTERNAME + "/" + $Nombre + ",user")' in grupos
    asegurar = _sin_comentarios(_funcion(texto, "Asegurar-Cuenta"))
    _en_orden(asegurar, ["try { $grupos = @(Grupos-De-La-Cuenta $Cuenta) } catch { Fallar",
                         "Remove-LocalGroupMember -SID $g -Member $sid -ErrorAction Stop",
                         "$mal = Negar-Inicios $sid", "if ($mal) { Fallar",
                         "New-ItemProperty -Path $ListaDeInicio -Name $Cuenta -PropertyType DWord -Value 0"])
    derechos = re.search(r"\$DerechosNegados = @\((.*?)\)", texto, re.S).group(1)
    assert re.findall(r'"(\w+)"', derechos) == [
        "SeDenyInteractiveLogonRight", "SeDenyRemoteInteractiveLogonRight",
        "SeDenyBatchLogonRight", "SeDenyServiceLogonRight"]
    assert "SeDenyNetworkLogonRight" not in sin and "SeNetworkLogonRight" not in sin
    # secedit, solo para esos derechos (USER_RIGHTS), y solo en Negar-Inicios (y el /export de
    # Negaciones-Que-Faltan, para -Estado).
    usos = [l for l in sin.splitlines() if "& $Secedit" in l]
    assert usos and all("/areas USER_RIGHTS" in l for l in usos)
    sin_las_dos = sin.replace(_funcion(sin, "Negar-Inicios"), "").replace(
        _funcion(sin, "Negaciones-Que-Faltan"), "")
    assert "$Secedit" not in sin_las_dos.replace('$Secedit = Join-Path', "")
    assert "/configure" not in _funcion(sin, "Negaciones-Que-Faltan")
    quitar = _accion("Quitar")
    _en_orden(quitar, ["$mal = Negar-Inicios $u.SID.Value -Quitar", "Remove-CimInstance",
                       "Remove-LocalUser -Name $Cuenta"])


def test_ningun_secreto_en_el_estado() -> None:
    """El estado del registro (HKLM\\SOFTWARE\\bms-agent\\TunelMac): solo lo de mac.md §2.8, y de
    cada Mac su nombre, su IP, su clave publica y la fecha."""
    guardar = _sin_comentarios(_funcion(_mac(), "Guardar-Estado"))
    claves = re.findall(r"(\w+) = ", guardar[guardar.index("$guardado = [ordered]@{"):
                                                guardar.index("Set-ItemProperty")])
    assert claves == ["guardado", "version", "instalado", "antes", "apagado", "config_sha256",
                      "macs", "nombre", "ip", "clave", "alta"]
    assert ("Set-ItemProperty -Path $ClaveDeEstado -Name \"Estado\" -Value "
            "(ConvertTo-Json -InputObject $guardado -Depth 5 -Compress)") in guardar
    assert '$ClaveDeEstado = "HKLM:\\SOFTWARE\\bms-agent\\TunelMac"' in _mac()


@pytest.mark.skipif(PWSH is None, reason="sin pwsh")
def test_pwsh_ninguna_variable_pisa_un_parametro() -> None:
    """En PowerShell los nombres no distinguen mayusculas: $estado = ... en el script es el
    [switch]$Estado de sus parametros, y no puede guardar el estado (le paso al borrador). Ni el
    script ni ninguna funcion asigna a una variable que se llama como uno de sus parametros, salvo
    los que la ventana normal rellena para la de administrador."""
    guion = r"""
param([string]$Fichero)
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Fichero, [ref]$null, [ref]$null)
$salida = @()
$ambitos = @($ast) + @($ast.FindAll({ $args[0] -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true))
foreach ($a in $ambitos) {
    if ($a -is [System.Management.Automation.Language.FunctionDefinitionAst]) {
        $nombre = $a.Name; $cuerpo = $a.Body; $params = @()
        if ($a.Parameters) { $params += $a.Parameters }
        if ($a.Body.ParamBlock) { $params += $a.Body.ParamBlock.Parameters }
    } else {
        $nombre = "(script)"; $cuerpo = $a; $params = @()
        if ($a.ParamBlock) { $params += $a.ParamBlock.Parameters }
    }
    $nombres = @($params | ForEach-Object { $_.Name.VariablePath.UserPath.ToLower() })
    $nodos = $cuerpo.FindAll({ $args[0] -is [System.Management.Automation.Language.AssignmentStatementAst] -or $args[0] -is [System.Management.Automation.Language.ForEachStatementAst] }, $true)
    foreach ($x in $nodos) {
        $padre = $x.Parent; $propia = $true
        while ($padre -and $padre -ne $cuerpo) {
            if ($padre -is [System.Management.Automation.Language.FunctionDefinitionAst]) { $propia = $false; break }
            $padre = $padre.Parent
        }
        if (-not $propia) { continue }
        if ($x -is [System.Management.Automation.Language.ForEachStatementAst]) { $izq = $x.Variable } else { $izq = $x.Left }
        if ($izq -is [System.Management.Automation.Language.ConvertExpressionAst]) { $izq = $izq.Child }
        if ($izq -isnot [System.Management.Automation.Language.VariableExpressionAst]) { continue }
        if ($nombres -contains $izq.VariablePath.UserPath.ToLower()) { $salida += ($nombre + ":" + $izq.VariablePath.UserPath) }
    }
}
$salida | Sort-Object -Unique
"""
    for nombre, permitidas in (("mac", {"(script):Usuario", "(script):Nombre", "(script):Ip",
                                        "(script):Clave", "(script):MismaClave"}),
                               ("proteger", {"(script):Dueno"})):
        proceso = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command",
                                  "& { " + guion + " } -Fichero '" + str(DOCKER / f"{nombre}.ps1") + "'"],
                                 capture_output=True, text=True, timeout=120)
        assert proceso.returncode == 0, proceso.stderr
        assert set(proceso.stdout.split()) == permitidas, (nombre, proceso.stdout)


# ============================================================ mac.ps1: las funciones puras con pwsh

# Las constantes del script (de $Cuenta a $Quedan) y sus funciones, sin correr la entrada; $Sshd,
# un sshd falso que imprime lo que daria "sshd -T" segun $env:SSHD_FALSO (mac.md §5.1, como el de
# pruebas-final/sshd-falso.ps1).
SSHD_FALSO = r"""
$quien = ("" + ($args -join " "))
$v = $env:SSHD_FALSO
if ($v -eq "vacio") { exit 1 }
if ($quien -match "user=bms-tunel") {
    "allowtcpforwarding local"
    if ($v -eq "permitopen_any") { "permitopen any" } else { "permitopen 127.0.0.1:8765" }
    "permitlisten none"; "permittty no"; "maxsessions 0"
    "forcecommand exit 1"; "passwordauthentication no"; "authenticationmethods publickey"; "allowagentforwarding no"
    "gatewayports no"; "allowstreamlocalforwarding no"; "permittunnel no"
    if ($v -eq "x11_si") { "x11forwarding yes" } elseif ($v -ne "x11_ausente") { "x11forwarding no" }
    "authorizedkeysfile __PROGRAMDATA__/ssh/bms_tunel_authorized_keys"
} else {
    "allowtcpforwarding no"; "permitopen none"; "allowstreamlocalforwarding no"
    if ($v -eq "96") { "authorizedkeysfile none" }
    if ($v -eq "malo") { "authorizedkeysfile .ssh/authorized_keys" }
}
"""

PURAS = r"""
param([string]$Script, [string]$Falso)
$ErrorActionPreference = "Stop"
$texto = [IO.File]::ReadAllText($Script)
$desde = $texto.IndexOf('$Cuenta = "bms-tunel"')
$hasta = $texto.IndexOf('$Quedan = 0')
$carpeta = "'" + (Split-Path -Parent $Script).Replace("'", "''") + "'"
. ([scriptblock]::Create($texto.Substring($desde, $hasta - $desde).Replace('$PSScriptRoot', $carpeta)))
$Sshd = $Falso
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Script, [ref]$null, [ref]$null)
foreach ($f in $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    . ([scriptblock]::Create($f.Extent.Text))
}
$r = [ordered]@{}
$vector = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4f prueba@mac"
$r["huella"] = Huella-Sha256 $vector
$r["valida"] = Clave-Publica-Valida $vector
$r["malas"] = @(@(
    ('command="x" ' + $vector),
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC",
    ($vector + "`nssh-ed25519 AAAA"),
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4= x",
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE4AAAAIAABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4f",
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIQABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4f",
    ($vector + ' ' + ('x' * 201)),
    "") | ForEach-Object { "" + (Clave-Publica-Valida $_) })
$r["comentario_raro"] = Clave-Publica-Valida ($vector + ' "a",command="b"' + [char]9)
$ips = @("192.168.1.23", "10.0.0.5", "172.16.4.4", "172.31.255.254", "8.8.8.8", "127.0.0.1",
    "0.0.0.0", "192.168.1.256", "192.168.001.23", "192.168.1.23/24", "::1", "192.168.1.1,10.0.0.1",
    "172.32.0.1", "192.168.1.0", "192.168.1.255", " 192.168.1.9 ", "mac.local", "", "169.254.1.1")
$r["ips"] = [ordered]@{}
foreach ($i in $ips) { $r["ips"][$i] = "" + (Ip-Valida $i) }
$r["red"] = @(@((Red-De "192.168.1.23" 24), (Red-De "10.1.2.3" 16), (Red-De "8.8.8.8" 24), (Red-De "192.168.1.23" 8), (Red-De "192.168.1.23" 31)) | ForEach-Object { "" + $_ })
$r["origen"] = [ordered]@{}
foreach ($o in @("192.168.1.23", "192.168.1.0/24", "10.1.0.0/16", "192.168.1.5/24", "8.8.8.0/24",
    "192.168.001.0/24", "192.168.1.0/8", "192.168.1.0/31", "192.168.1.0", "300.1.1.0/24",
    "192.168.1.0/24 ", "192.168.1.0/24,1.2.3.4")) { $r["origen"][$o] = "" + (Origen-Valido $o) }
$r["resto"] = [ordered]@{}
foreach ($caso in @("192.168.1.23", "192.168.1.40,192.168.1.23", "192.168.1.0/24", "10.0.0.1,10.0.0.2",
    "192.168.1.0/24,192.168.1.7", "10.0.0.1,172.16.0.0/16,192.168.1.23")) {
    $r["resto"][$caso] = @(Resto-De $caso.Split(","))
}
$k = Clave-Publica-Valida $vector
$uno = @([pscustomobject]@{ nombre = "mac-oficina"; ip = "192.168.1.23"; clave = $k; alta = "2026-11-25" })
$dos = @($uno[0], [pscustomobject]@{ nombre = "mac-casa"; ip = "192.168.1.31"; clave = $k; alta = "2026-11-25" })
$r["config0"] = Texto-Config @()
$r["config1"] = Texto-Config $uno
$r["config2"] = Texto-Config $dos
$r["claves0"] = Texto-Claves @()
$r["claves1"] = Texto-Claves $uno
$r["claves2"] = Texto-Claves $dos
$red = @([pscustomobject]@{ nombre = "toda-la-red"; ip = "192.168.1.0/24"; clave = $k; alta = "x" })
$r["claves_red"] = Texto-Claves $red
$r["quien_es"] = @((Mac-De-La-Ip "192.168.1.31" $dos), (Mac-De-La-Ip "192.168.1.99" $dos), (Mac-De-La-Ip "192.168.1.99" $red), (Mac-De-La-Ip "::1" $dos))
$r["aplica"] = [ordered]@{}
foreach ($v in @("96", "103", "malo", "permitopen_any", "x11_ausente", "x11_si", "vacio")) {
    $env:SSHD_FALSO = $v
    $r["aplica"][$v] = "" + (Comprobar-Lo-Que-Se-Aplica $uno)
}
$r["si"] = @(@("si", "S", " si ", ("s" + [char]0x00ED), "no", "", "sip") | ForEach-Object { Es-Si $_ })
$r["macs"] = @((@(Macs-De ('{"macs":[{"nombre":"a"}]}' | ConvertFrom-Json))).Count, (@(Macs-De ('{"macs":[]}' | ConvertFrom-Json))).Count, (@(Macs-De $null)).Count)
# Los derechos de "denegar" (mac.md 2.2; los casos de pruebas-final/probar.ps1).
$exportado = "[Unicode]`r`nUnicode=yes`r`n[System Access]`r`nMinimumPasswordAge = 0`r`n[Privilege Rights]`r`nSeNetworkLogonRight = *S-1-1-0,*S-1-5-32-544,*S-1-5-32-545`r`nSeDenyNetworkLogonRight = Guest`r`nSeDenyInteractiveLogonRight = Guest`r`nSeInteractiveLogonRight = Guest,*S-1-5-32-544,*S-1-5-32-545`r`n"
$sid = "S-1-5-21-1-2-3-1005"
$n = [ordered]@{}
$t = Texto-Negaciones $exportado $sid
$n["plantilla"] = $t
$n["quitar"] = Texto-Negaciones ($exportado.Replace("SeDenyInteractiveLogonRight = Guest", "SeDenyInteractiveLogonRight = Guest,*$sid")) $sid -Quitar
$antes = Lineas-De-Derechos $exportado
$con = $exportado.Replace("SeDenyInteractiveLogonRight = Guest", "SeDenyInteractiveLogonRight = Guest,*$sid") + "SeDenyRemoteInteractiveLogonRight = *$sid`r`nSeDenyBatchLogonRight = *$sid`r`nSeDenyServiceLogonRight = *$sid`r`n"
$bien = Lineas-De-Derechos $con
$n["tras_bien"] = "" + (Diferencias-De-Derechos $antes $bien $sid)
$n["tras_otro_cambio"] = "" + (Diferencias-De-Derechos $antes (Lineas-De-Derechos ($con.Replace("SeNetworkLogonRight = *S-1-1-0,*S-1-5-32-544,*S-1-5-32-545", "SeNetworkLogonRight = *S-1-1-0,*S-1-5-32-544"))) $sid)
$n["tras_red_cambiada"] = "" + (Diferencias-De-Derechos $antes (Lineas-De-Derechos ($con.Replace("SeDenyNetworkLogonRight = Guest", "SeDenyNetworkLogonRight = Guest,*$sid"))) $sid)
$n["tras_falta_uno"] = "" + (Diferencias-De-Derechos $antes (Lineas-De-Derechos ($con.Replace("SeDenyBatchLogonRight = *$sid", "SeDenyBatchLogonRight = "))) $sid)
$n["tras_quitar_linea_vacia"] = "" + (Diferencias-De-Derechos $bien (Lineas-De-Derechos $exportado) $sid -Quitar)
$n["tras_por_nombre"] = "" + (Diferencias-De-Derechos $antes (Lineas-De-Derechos ($exportado.Replace("SeDenyInteractiveLogonRight = Guest", "SeDenyInteractiveLogonRight = Guest,bms-tunel") + "SeDenyRemoteInteractiveLogonRight = EQUIPO\bms-tunel`r`nSeDenyBatchLogonRight = *$sid`r`nSeDenyServiceLogonRight = bms-tunel`r`n")) $sid)
$conNombre = $exportado.Replace("SeDenyInteractiveLogonRight = Guest", "SeDenyInteractiveLogonRight = Guest,bms-tunel")
$n["plantilla_con_nombre"] = Texto-Negaciones $conNombre $sid
$n["quitar_con_nombre"] = Texto-Negaciones $conNombre $sid -Quitar
$n["vuelta"] = Texto-Vuelta $antes (Lineas-De-Derechos ($con + "SeShutdownPrivilege = *S-1-5-32-545`r`n"))
$r["negaciones"] = $n
$r | ConvertTo-Json -Depth 6
"""

VECTOR = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4f"


@pytest.fixture(scope="module")
def puras(tmp_path_factory):
    if PWSH is None:
        pytest.skip("sin pwsh")
    carpeta = tmp_path_factory.mktemp("puras")
    (carpeta / "puras.ps1").write_text(PURAS, encoding="ascii")
    (carpeta / "sshd-falso.ps1").write_text(SSHD_FALSO, encoding="ascii")
    entorno = {**os.environ, "SystemRoot": str(carpeta / "Windows"),
               "ProgramData": str(carpeta / "ProgramData")}
    proceso = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File",
                              str(carpeta / "puras.ps1"), str(DOCKER / "mac.ps1"),
                              str(carpeta / "sshd-falso.ps1")],
                             env=entorno, capture_output=True, text=True, timeout=180)
    assert proceso.returncode == 0, proceso.stdout + proceso.stderr
    return json.loads(proceso.stdout)


def _bloque_del_diseno(seccion: str) -> str:
    texto = (RAIZ / "docs" / "v1" / "paso-18" / "mac.md").read_text(encoding="utf-8")
    return re.search(r"```\n(.*?)```", texto[texto.index(seccion):], re.S).group(1)


def test_pwsh_el_sshd_config(puras) -> None:
    """mac.md §2.3: con un Mac, igual caracter a caracter al sshd_config que se probo con un
    OpenSSH 9.6 de verdad; con dos, AllowUsers con los dos; sin ninguno, DenyUsers *."""
    uno = puras["config1"]
    assert uno == _bloque_del_diseno("### 2.3 El `sshd_config` exacto")
    assert "\r" not in uno and not uno.startswith("﻿") and uno.isascii()
    assert puras["config2"] == uno.replace(
        "AllowUsers bms-tunel@192.168.1.23\n",
        "AllowUsers bms-tunel@192.168.1.23 bms-tunel@192.168.1.31\n")
    cero = puras["config0"]
    assert "\nDenyUsers *\n" in cero and "AllowUsers" not in cero
    assert cero.replace("DenyUsers *", "AllowUsers bms-tunel@192.168.1.23") == uno
    for config in (cero, uno, puras["config2"]):
        lineas = config.splitlines()
        fuera = lineas[:lineas.index("Match User bms-tunel")]
        directivas = [l.split()[0] for l in fuera if l and not l.startswith("#")]
        assert len(directivas) == len(set(directivas))
        assert lineas[lineas.index("Match User bms-tunel"):] == [
            "Match User bms-tunel",
            "    AuthorizedKeysFile __PROGRAMDATA__/ssh/bms_tunel_authorized_keys",
            "    AllowTcpForwarding local", "    PermitOpen 127.0.0.1:8765"]
        for linea in ("AllowStreamLocalForwarding no", "X11Forwarding no", "PermitTunnel no",
                      "AuthorizedKeysFile none", "PasswordAuthentication no", "MaxSessions 0",
                      "ForceCommand exit 1", "PermitTTY no", "PermitListen none"):
            assert linea in fuera, linea
        for prohibido in ("Subsystem", "PasswordAuthentication yes", "AllowTcpForwarding yes",
                          "GatewayPorts yes", "PermitOpen any", "StrictModes",
                          "DisableForwarding", "ListenAddress", "PerSourcePenalties",
                          "Match Group", "administrators_authorized_keys", "PermitRootLogin",
                          "localhost"):
            assert prohibido not in config, prohibido


def test_pwsh_el_fichero_de_claves(puras) -> None:
    """mac.md §2.4: las opciones las pone el script; de lo que llega del Mac solo la clave."""
    assert puras["claves1"] == _bloque_del_diseno("### 2.4 El fichero de claves exacto")
    assert puras["claves0"] == ("# bms-agent: las claves de los Mac (mac.ps1). No lo cambies a "
                                "mano: lo rehace mac.bat.\n")
    lineas = puras["claves2"].splitlines()
    assert lineas[1:] == [
        f'restrict,port-forwarding,permitopen="127.0.0.1:8765",from="{ip}",command="exit 1" '
        f"{VECTOR} bms-{nombre}" for nombre, ip in (("mac-oficina", "192.168.1.23"),
                                                   ("mac-casa", "192.168.1.31"))]
    assert 'from="192.168.1.0/24"' in puras["claves_red"]
    for texto in (puras["claves0"], puras["claves1"], puras["claves2"]):
        assert "\r" not in texto and texto.isascii()


def test_pwsh_la_clave_pegada(puras) -> None:
    """Solo "ssh-ed25519 <68 de base64> [comentario]", con el blob de 51 bytes y su cabecera; nada
    de opciones delante, otro tipo, otra longitud, dos lineas ni un comentario larguisimo. Un
    comentario con comillas o comas no importa: se tira (la linea la escribe el script)."""
    assert puras["valida"] == VECTOR
    assert puras["malas"] == [""] * 8
    assert puras["comentario_raro"] == VECTOR


def test_pwsh_la_huella(puras) -> None:
    import base64
    import hashlib

    blob = base64.b64decode(VECTOR.split()[1])
    esperada = "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
    assert puras["huella"] == esperada == "SHA256:ZkAslGjFiUHdGf/WUL8rQvkib4PTvQatUV0OUQSncCA"


def test_pwsh_las_ip(puras) -> None:
    buenas = {"192.168.1.23", "10.0.0.5", "172.16.4.4", "172.31.255.254"}
    for ip, valida in puras["ips"].items():
        if ip in buenas:
            assert valida == ip
        elif ip == " 192.168.1.9 ":
            assert valida == "192.168.1.9"
        else:
            assert valida == "", ip
    assert puras["red"] == ["192.168.1.0/24", "10.1.0.0/16", "", "", ""]
    assert puras["origen"] == {
        "192.168.1.23": "192.168.1.23", "192.168.1.0/24": "192.168.1.0/24",
        "10.1.0.0/16": "10.1.0.0/16", "192.168.1.5/24": "", "8.8.8.0/24": "",
        "192.168.001.0/24": "", "192.168.1.0/8": "", "192.168.1.0/31": "", "192.168.1.0": "",
        "300.1.1.0/24": "", "192.168.1.0/24 ": "192.168.1.0/24", "192.168.1.0/24,1.2.3.4": ""}
    assert puras["quien_es"] == ["mac-casa", "?", "toda-la-red", "?"]


def _numero(ip: str) -> int:
    a, b, c, d = (int(x) for x in ip.split("."))
    return (a << 24) | (b << 16) | (c << 8) | d


def test_pwsh_el_resto(puras) -> None:
    """La regla "resto" bloquea todo IPv4 menos los Mac: sin huecos ni solapes."""
    assert puras["resto"]["192.168.1.23"] == ["0.0.0.0-192.168.1.22",
                                             "192.168.1.24-255.255.255.255"]
    assert puras["resto"]["10.0.0.1,10.0.0.2"] == ["0.0.0.0-10.0.0.0",
                                                  "10.0.0.3-255.255.255.255"]
    for caso, rangos in puras["resto"].items():
        dentro = set()
        for origen in caso.split(","):
            base, _, prefijo = origen.partition("/")
            n = _numero(base)
            tam = 1 << (32 - int(prefijo)) if prefijo else 1
            dentro.add((n, n + tam - 1))
        tramos = sorted([(_numero(a), _numero(b)) for a, b in (r.split("-") for r in rangos)] +
                        list(dentro))
        # Juntos, los rangos bloqueados y los de los Mac cubren 0..2^32-1 sin solaparse (salvo
        # lo que los Mac comparten entre si).
        siguiente = 0
        for inicio, fin in tramos:
            assert inicio <= siguiente, (caso, inicio, siguiente)
            siguiente = max(siguiente, fin + 1)
        assert siguiente == 1 << 32
        for a, b in (r.split("-") for r in rangos):
            for inicio, fin in dentro:
                assert _numero(b) < inicio or _numero(a) > fin, (caso, a, b)


def test_pwsh_comprobar_lo_que_se_aplica(puras) -> None:
    """mac.md §2.3: con lo que dice el propio sshd (-T). Un 9.6 (authorizedkeysfile none para
    otra cuenta) y uno >= 10.3 (sin la linea) valen; claves para otra cuenta, permitopen any, X11
    o un sshd que no dice nada, no."""
    a = puras["aplica"]
    assert a["96"] == "" and a["103"] == "" and a["x11_ausente"] == ""
    assert a["malo"] == "para otra cuenta, sshd no queda cerrado"
    assert "permitopen es 'any'" in a["permitopen_any"]
    assert "x11forwarding es 'yes'" in a["x11_si"]
    assert a["vacio"] == "sshd -T no dice nada"


def test_pwsh_las_negaciones(puras) -> None:
    n = puras["negaciones"]
    sid = "S-1-5-21-1-2-3-1005"
    plantilla = n["plantilla"].split("\r\n")
    assert plantilla[:6] == ["[Unicode]", "Unicode=yes", "[Version]", 'signature="$CHICAGO$"',
                             "Revision=1", "[Privilege Rights]"]
    assert [l for l in plantilla if l.startswith("Se")] == [
        f"SeDenyInteractiveLogonRight = Guest,*{sid}",
        f"SeDenyRemoteInteractiveLogonRight = *{sid}", f"SeDenyBatchLogonRight = *{sid}",
        f"SeDenyServiceLogonRight = *{sid}"]
    assert "Network" not in n["plantilla"]
    assert "SeDenyInteractiveLogonRight = Guest\r\n" in n["quitar"] and sid not in n["quitar"]
    assert n["tras_bien"] == ""
    assert n["tras_otro_cambio"] == "SeNetworkLogonRight"
    assert n["tras_red_cambiada"] == "SeDenyNetworkLogonRight"
    assert n["tras_falta_uno"] == "SeDenyBatchLogonRight"
    assert n["tras_quitar_linea_vacia"] == ""
    assert n["tras_por_nombre"] == ""
    assert "SeDenyInteractiveLogonRight = Guest,*" + sid + "\r\n" in n["plantilla_con_nombre"]
    assert "bms-tunel" not in n["plantilla_con_nombre"]
    assert "SeDenyInteractiveLogonRight = Guest\r\n" in n["quitar_con_nombre"]
    # La vuelta atras lleva cada derecho de antes y de despues, con lo de antes (vacio si no
    # estaba): secedit /configure solo toca lo que trae la plantilla.
    vuelta = [l for l in n["vuelta"].split("\r\n") if l.startswith("Se")]
    assert vuelta == sorted(vuelta) and len(vuelta) == 8
    assert "SeShutdownPrivilege = " in vuelta and "SeDenyBatchLogonRight = " in vuelta
    assert "SeDenyInteractiveLogonRight = Guest" in vuelta
    assert "SeNetworkLogonRight = *S-1-1-0,*S-1-5-32-544,*S-1-5-32-545" in vuelta


def test_pwsh_las_ayudas(puras) -> None:
    assert puras["si"] == [True, True, True, True, False, False, False]
    assert puras["macs"] == [1, 0, 0]


# ============================================================ mac.ps1 corrido, con Windows sustituido

# Lo de Windows que mac.ps1 usa, sustituido en una copia del script (tras $ErrorActionPreference)
# por funciones que leen y escriben un "mundo" en JSON (el registro, el servicio, la capacidad,
# las reglas del cortafuegos, las cuentas, los procesos, las ACL...) y apuntan cada llamada. Los
# programas (sshd, icacls, taskkill, secedit, takeown) son falsos de verdad, en
# $env:SystemRoot\System32, y apuntan en el mismo sitio: asi se ve el orden de todo.
SUSTITUTOS_MAC = r"""
function Mundo { return (Microsoft.PowerShell.Management\Get-Content -LiteralPath $env:PRUEBA_MUNDO -Raw | ConvertFrom-Json -AsHashtable) }
function Guardar-Mundo($M) { [IO.File]::WriteAllText($env:PRUEBA_MUNDO, (ConvertTo-Json -InputObject $M -Depth 10)) }
function Apuntar([string]$Que, $Datos) { [IO.File]::AppendAllText($env:PRUEBA_LLAMADAS, (ConvertTo-Json -Compress -Depth 5 -InputObject @($Que, $Datos)) + "`n") }
function Get-LocalUser { [CmdletBinding()] param([string]$Name)
    $u = (Mundo).usuarios[$Name]
    if (-not $u) { return $null }
    return [pscustomobject]@{ Name = $Name; SID = [pscustomobject]@{ Value = $u.SID }; Enabled = [bool]$u.Enabled; PasswordExpires = $u.PasswordExpires }
}
function New-LocalUser { [CmdletBinding()] param([string]$Name, $Password, [switch]$PasswordNeverExpires, [switch]$AccountNeverExpires, [switch]$UserMayNotChangePassword, [string]$Description)
    Apuntar "New-LocalUser" @{ Name = $Name; Password = $Password.GetType().FullName; Longitud = $Password.Length; SoloLectura = $Password.IsReadOnly();
        PasswordNeverExpires = [bool]$PasswordNeverExpires; AccountNeverExpires = [bool]$AccountNeverExpires; UserMayNotChangePassword = [bool]$UserMayNotChangePassword; Description = $Description }
    $m = Mundo; $m.usuarios[$Name] = @{ SID = $env:PRUEBA_SID_TUNEL; Enabled = $true; PasswordExpires = $null }; $m.perfiles = @($env:PRUEBA_SID_TUNEL); Guardar-Mundo $m
    return [pscustomobject]@{ Name = $Name }
}
function Enable-LocalUser { [CmdletBinding()] param([string]$Name) Apuntar "Enable-LocalUser" $Name; $m = Mundo; $m.usuarios[$Name].Enabled = $true; Guardar-Mundo $m }
function Remove-LocalUser { [CmdletBinding()] param([string]$Name) Apuntar "Remove-LocalUser" $Name; $m = Mundo; $m.usuarios.Remove($Name); Guardar-Mundo $m }
function Remove-LocalGroupMember { [CmdletBinding()] param([string]$SID, [string]$Member)
    Apuntar "Remove-LocalGroupMember" @($SID, $Member); $m = Mundo; $m.grupos_tunel = @($m.grupos_tunel | Where-Object { $_ -ne $SID }); Guardar-Mundo $m }
function Get-WindowsCapability { [CmdletBinding()] param([switch]$Online, [string]$Name) return [pscustomobject]@{ Name = $Name; State = (Mundo).capacidad } }
function Add-WindowsCapability { [CmdletBinding()] param([switch]$Online, [string]$Name)
    Apuntar "Add-WindowsCapability" $Name
    $m = Mundo; $m.capacidad = "Installed"; $m.servicio = @{ Status = "Stopped"; StartType = "Manual" }
    $m.reglas["OpenSSH-Server-In-TCP"] = @{ Enabled = "True"; Action = "Allow"; Profile = "Any" }; Guardar-Mundo $m
    return [pscustomobject]@{ RestartNeeded = $false }
}
function Remove-WindowsCapability { [CmdletBinding()] param([switch]$Online, [string]$Name)
    Apuntar "Remove-WindowsCapability" $Name; $m = Mundo; $m.capacidad = "NotPresent"; $m.servicio = $null; Guardar-Mundo $m }
function Get-Service { [CmdletBinding()] param([string]$Name)
    $s = (Mundo).servicio; if (-not $s) { return $null }
    return [pscustomobject]@{ Name = $Name; Status = $s.Status; StartType = $s.StartType } }
function Set-Service { [CmdletBinding()] param([string]$Name, [string]$StartupType)
    Apuntar "Set-Service" $StartupType; $m = Mundo; $m.servicio.StartType = $StartupType; Guardar-Mundo $m }
function Start-Service { [CmdletBinding()] param([string]$Name)
    Apuntar "Start-Service" $Name
    $m = Mundo; if (-not $m.servicio) { throw "no hay servicio sshd" }
    $c = Join-Path $env:ProgramData "ssh"
    if (-not (Microsoft.PowerShell.Management\Test-Path -LiteralPath $c)) { Microsoft.PowerShell.Management\New-Item -ItemType Directory -Path $c | Out-Null }
    $k = Join-Path $c "ssh_host_ed25519_key.pub"
    if (-not (Microsoft.PowerShell.Management\Test-Path -LiteralPath $k)) {
        [IO.File]::WriteAllText($k, $env:PRUEBA_CLAVE_EQUIPO + " root@minipc`n")
        [IO.File]::WriteAllText((Join-Path $c "ssh_host_ed25519_key"), "privada")
    }
    $f = Join-Path $c "sshd_config"
    if (-not (Microsoft.PowerShell.Management\Test-Path -LiteralPath $f)) { [IO.File]::WriteAllText($f, [IO.File]::ReadAllText($ConfigDeFabrica)) }
    $m.servicio.Status = "Running"; Guardar-Mundo $m
}
function Stop-Service { [CmdletBinding()] param([string]$Name, [switch]$Force)
    Apuntar "Stop-Service" $Name; $m = Mundo; if ($m.servicio) { $m.servicio.Status = "Stopped"; Guardar-Mundo $m } }
function Get-CimInstance { [CmdletBinding()] param([Parameter(Position = 0)][string]$ClassName, [string]$Filter)
    $m = Mundo
    if ($ClassName -eq "Win32_Service") {
        if (-not $m.servicio) { return $null }
        return [pscustomobject]@{ Name = "sshd"; ProcessId = 4000; State = $m.servicio.Status; PathName = ('"' + $ProgramasSsh + '\sshd.exe"') }
    }
    if ($ClassName -eq "Win32_Process") { return @($m.procesos | ForEach-Object { [pscustomobject]@{ ProcessId = $_.ProcessId; Name = "sshd.exe"; ExecutablePath = ($ProgramasSsh + "\sshd.exe") } }) }
    if ($ClassName -eq "Win32_UserProfile") { return @($m.perfiles | ForEach-Object { [pscustomobject]@{ SID = $_ } }) }
}
function Remove-CimInstance { [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$InputObject)
    process { Apuntar "Remove-CimInstance" $InputObject.SID; $m = Mundo; $m.perfiles = @($m.perfiles | Where-Object { $_ -ne $InputObject.SID }); Guardar-Mundo $m } }
function Get-NetFirewallRule { [CmdletBinding()] param([string]$Name)
    $r = (Mundo).reglas[$Name]; if (-not $r) { return $null }
    return [pscustomobject]@{ Name = $Name; Enabled = $r.Enabled; Action = $r.Action; Profile = $r.Profile } }
function Remove-NetFirewallRule { [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$InputObject)
    process { if ($InputObject) { Apuntar "Remove-NetFirewallRule" $InputObject.Name; $m = Mundo; $m.reglas.Remove($InputObject.Name); Guardar-Mundo $m } } }
function Disable-NetFirewallRule { [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$InputObject, [string]$Name)
    process { $n = $Name; if ($InputObject) { $n = $InputObject.Name }; if (-not $n) { return }; Apuntar "Disable-NetFirewallRule" $n; $m = Mundo; $m.reglas[$n].Enabled = "False"; Guardar-Mundo $m } }
function Enable-NetFirewallRule { [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$InputObject, [string]$Name)
    process { $n = $Name; if ($InputObject) { $n = $InputObject.Name }; if (-not $n) { return }; Apuntar "Enable-NetFirewallRule" $n; $m = Mundo; $m.reglas[$n].Enabled = "True"; Guardar-Mundo $m } }
function New-NetFirewallRule { [CmdletBinding()] param([string]$Name, [string]$DisplayName, [string]$Direction, [string]$Action, [string]$Protocol, $LocalPort, [string]$Program, [string]$Profile, [string[]]$RemoteAddress)
    $r = @{ Enabled = "True"; Action = $Action; Profile = $Profile; RemoteAddress = @($RemoteAddress); Program = $Program; LocalPort = ("" + $LocalPort); Direction = $Direction; Protocol = $Protocol }
    Apuntar "New-NetFirewallRule" @{ Name = $Name; Regla = $r }
    $m = Mundo; $m.reglas[$Name] = $r; Guardar-Mundo $m
    return [pscustomobject]@{ Name = $Name } }
function Get-NetFirewallProfile { [CmdletBinding()] param([string]$Name) return [pscustomobject]@{ Name = $Name; AllowInboundRules = (Mundo).entrada } }
function Get-NetIPConfiguration { [CmdletBinding()] param()
    return @((Mundo).ips | ForEach-Object { [pscustomobject]@{ InterfaceAlias = $_.Interfaz; InterfaceIndex = $_.Indice; IPv4DefaultGateway = "192.168.1.1";
        IPv4Address = @([pscustomobject]@{ IPAddress = $_.Ip; PrefixLength = $_.Prefijo }) } }) }
function Get-NetConnectionProfile { [CmdletBinding()] param($InterfaceIndex)
    $i = @((Mundo).ips | Where-Object { $_.Indice -eq $InterfaceIndex })[0]
    if ($i) { return [pscustomobject]@{ NetworkCategory = $i.Red } } }
function Get-NetTCPConnection { [CmdletBinding()] param($LocalPort, [string]$State)
    $m = Mundo
    if ($LocalPort -eq 22 -and $State -eq "Listen") { if ($m.servicio -and $m.servicio.Status -eq "Running") { return [pscustomobject]@{ LocalPort = 22; OwningProcess = $PID } }; return $null }
    if ($LocalPort -eq 22) { return @($m.conexiones | ForEach-Object { [pscustomobject]@{ RemoteAddress = $_ } }) }
    if ($m.app) { return [pscustomobject]@{ LocalPort = $LocalPort; OwningProcess = $PID } } }
function Get-Acl { [CmdletBinding()] param([string]$LiteralPath)
    $m = Mundo; $a = $m.acl[$LiteralPath]
    # Una ACL con testigo es de esa carpeta mientras el testigo este dentro (si se aparta la
    # carpeta, la nueva que crea el servicio ya no la lleva).
    if ($a -and $a.testigo -and -not (Microsoft.PowerShell.Management\Test-Path -LiteralPath (Join-Path $LiteralPath $a.testigo))) { $a = $null }
    # Lo que crea el servicio en ProgramData\ssh: de SYSTEM y Administradores (las claves del
    # equipo, solo de ellos); lo demas, como el proyecto protegido.
    if (-not $a -and $LiteralPath -like "*ssh_host_*_key") { $a = $m.acl_clave }
    if (-not $a -and $LiteralPath.StartsWith($env:ProgramData)) { $a = $m.acl_ssh }
    if (-not $a) { $a = $m.acl_defecto }
    $reglas = @()
    foreach ($r in @($a.reglas)) {
        $id = [pscustomobject]@{ Sid = $r.sid }
        $id | Add-Member -MemberType ScriptMethod -Name Translate -Value { param($Tipo) [pscustomobject]@{ Value = $this.Sid } }
        $id | Add-Member -MemberType ScriptMethod -Name ToString -Value { $this.Sid } -Force
        $flags = [Security.AccessControl.PropagationFlags]::None
        if ($r.solo_herencia) { $flags = [Security.AccessControl.PropagationFlags]::InheritOnly }
        $reglas += [pscustomobject]@{ IdentityReference = $id; AccessControlType = $r.tipo; FileSystemRights = [Security.AccessControl.FileSystemRights]$r.derechos; PropagationFlags = $flags }
    }
    $acl = [pscustomobject]@{ Access = $reglas; Owner = $a.dueno; Sid = $a.dueno }
    $acl | Add-Member -MemberType ScriptMethod -Name GetOwner -Value { param($Tipo) [pscustomobject]@{ Value = $this.Sid } }
    return $acl }
function Test-Path { [CmdletBinding()] param([Parameter(Position = 0)][string]$Path, [string]$LiteralPath, [string]$PathType)
    $p = $Path; if ($LiteralPath) { $p = $LiteralPath }
    if ($p -like "HKLM:*") { return (Mundo).registro.ContainsKey($p) }
    $a = @{}; if ($LiteralPath) { $a["LiteralPath"] = $LiteralPath } else { $a["Path"] = $Path }
    if ($PathType) { $a["PathType"] = $PathType }
    return (Microsoft.PowerShell.Management\Test-Path @a) }
function New-Item { [CmdletBinding()] param([string]$Path, [string]$ItemType, [switch]$Force)
    if ($Path -like "HKLM:*") { $m = Mundo; if (-not $m.registro.ContainsKey($Path)) { $m.registro[$Path] = @{} }; Guardar-Mundo $m; return [pscustomobject]@{ Name = $Path } }
    $a = @{ Path = $Path }; if ($ItemType) { $a["ItemType"] = $ItemType }; if ($Force) { $a["Force"] = $true }
    return (Microsoft.PowerShell.Management\New-Item @a) }
function Remove-Item { [CmdletBinding()] param([string]$Path, [string]$LiteralPath, [switch]$Recurse, [switch]$Force)
    $p = $Path; if ($LiteralPath) { $p = $LiteralPath }
    if ($p -like "HKLM:*") { Apuntar "Remove-Item" $p; $m = Mundo; $m.registro.Remove($p); Guardar-Mundo $m; return }
    $a = @{}; if ($LiteralPath) { $a["LiteralPath"] = $LiteralPath } else { $a["Path"] = $Path }
    if ($Recurse) { $a["Recurse"] = $true }; if ($Force) { $a["Force"] = $true }
    if ($PSBoundParameters["ErrorAction"]) { $a["ErrorAction"] = $PSBoundParameters["ErrorAction"] }
    Microsoft.PowerShell.Management\Remove-Item @a }
function Get-ItemProperty { [CmdletBinding()] param([string]$Path, [string]$LiteralPath, [string]$Name)
    $p = $Path; if ($LiteralPath) { $p = $LiteralPath }
    $clave = (Mundo).registro[$p]
    if ($null -eq $clave -or -not $clave.ContainsKey($Name)) {
        if ($PSBoundParameters["ErrorAction"] -eq "Stop") { throw ("no hay " + $p) }
        return $null }
    $o = [pscustomobject]@{}; $o | Add-Member -NotePropertyName $Name -NotePropertyValue $clave[$Name]; return $o }
function Set-ItemProperty { [CmdletBinding()] param([string]$Path, [string]$Name, $Value) $m = Mundo; $m.registro[$Path][$Name] = $Value; Guardar-Mundo $m }
function New-ItemProperty { [CmdletBinding()] param([string]$Path, [string]$Name, [string]$PropertyType, $Value, [switch]$Force)
    $m = Mundo; $m.registro[$Path][$Name] = $Value; Guardar-Mundo $m; return $null }
function Remove-ItemProperty { [CmdletBinding()] param([string]$Path, [string]$Name)
    $m = Mundo; if ($m.registro[$Path]) { $m.registro[$Path].Remove($Name) }; Guardar-Mundo $m }
function Get-WinEvent { [CmdletBinding()] param([string]$LogName, [int]$MaxEvents)
    return @((Mundo).eventos | ForEach-Object { [pscustomobject]@{ TimeCreated = [datetime]$_.cuando; Message = $_.texto } }) }
function Get-HotFix { [CmdletBinding()] param() $f = (Mundo).hotfix; if ($f) { return [pscustomobject]@{ InstalledOn = [datetime]$f } } }
function Invoke-WebRequest { [CmdletBinding()] param([switch]$UseBasicParsing, [int]$TimeoutSec, [string]$Uri)
    Apuntar "Invoke-WebRequest" $Uri; if ((Mundo).app) { return [pscustomobject]@{ StatusCode = 200 } }; throw "no contesta" }
function Start-Sleep { [CmdletBinding()] param([int]$Seconds) }
function Start-Process { [CmdletBinding()] param([string]$FilePath, [string[]]$ArgumentList, [string]$Verb, [switch]$Wait, [switch]$PassThru)
    Apuntar "Start-Process" @{ Verb = $Verb; ArgumentList = @($ArgumentList) }
    return [pscustomobject]@{ ExitCode = 0 } }
"""

PROGRAMA_FALSO = r'''#!{python}
import json, os, sys
nombre = os.path.basename(sys.argv[0])
a = sys.argv[1:]
with open(os.environ["PRUEBA_LLAMADAS"], "a", encoding="utf-8") as f:
    f.write(json.dumps([nombre, a]) + "\n")
with open(os.environ["PRUEBA_MUNDO"], encoding="utf-8") as f:
    mundo = json.load(f)

def guardar():
    with open(os.environ["PRUEBA_MUNDO"], "w", encoding="utf-8") as f:
        json.dump(mundo, f)

def derechos(texto):
    d, dentro = {{}}, False
    for linea in texto.replace("\r", "").split("\n"):
        t = linea.strip()
        if t.startswith("["):
            dentro = t == "[Privilege Rights]"
        elif dentro and "=" in t:
            k, v = t.split("=", 1)
            d[k.strip()] = v.strip()
    return d

def escribir_derechos(d):
    return "[Unicode]\r\nUnicode=yes\r\n[Privilege Rights]\r\n" + "".join(
        f"{{k}} = {{v}}\r\n" for k, v in d.items() if v)

if nombre == "sshd.exe":
    if a[:1] == ["-t"]:
        if "-f" in a and mundo.get("sshd_t") == "falla":
            print("/x/sshd_config line 2: Bad configuration option: X11Forwarding")
            sys.exit(255)
        sys.exit(0)
    if a[:1] == ["-T"]:
        tunel = "user=bms-tunel" in a[a.index("-C") + 1]
        v = mundo.get("sshd_T", "96")
        if tunel:
            print("\n".join(["allowtcpforwarding local", "permitopen 127.0.0.1:8765",
                             "permitlisten none", "permittty no", "maxsessions 0",
                             "forcecommand exit 1", "passwordauthentication no",
                             "authenticationmethods publickey", "allowagentforwarding no",
                             "gatewayports no", "allowstreamlocalforwarding no",
                             "x11forwarding no", "permittunnel no",
                             "authorizedkeysfile __PROGRAMDATA__/ssh/bms_tunel_authorized_keys"]))
        else:
            print("allowtcpforwarding no\npermitopen none")
            print("authorizedkeysfile " + (".ssh/authorized_keys" if v == "malo" else "none"))
        sys.exit(0)
elif nombre == "taskkill.exe":
    pid = int(a[a.index("/PID") + 1])
    mundo["procesos"] = [p for p in mundo["procesos"] if p["ProcessId"] != pid or p.get("duro")]
    guardar()
elif nombre == "secedit.exe":
    cfg = a[a.index("/cfg") + 1]
    if a[0] == "/export":
        with open(cfg, "w", encoding="utf-16") as f:
            f.write(mundo["derechos"])
    elif a[0] == "/configure":
        with open(cfg, encoding="utf-16") as f:
            pedido = derechos(f.read())
        actual = derechos(mundo["derechos"])
        actual.update(pedido)
        if mundo.get("secedit") == "de_mas" and "vuelta" not in a[a.index("/db") + 1]:
            actual["SeShutdownPrivilege"] = "*S-1-5-32-545"
        mundo["derechos"] = escribir_derechos(actual)
        guardar()
sys.exit(0)
'''

SID_TUNEL = "S-1-5-21-9-9-9-1010"
SID_DUENO = "S-1-5-21-1-2-3-1001"
SID_BMS = "S-1-5-21-1-2-3-1002"
# La clave del equipo (otro vector: 32 bytes 0x20..0x3f).
CLAVE_EQUIPO = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICAhIiMkJSYnKCkqKywtLi8wMTIzNDU2Nzg5Ojs8PT4/"
DERECHOS_DE_ANTES = ("[Unicode]\r\nUnicode=yes\r\n[Privilege Rights]\r\n"
                     "SeNetworkLogonRight = *S-1-1-0,*S-1-5-32-544,*S-1-5-32-545\r\n"
                     "SeDenyInteractiveLogonRight = Guest\r\n"
                     "SeInteractiveLogonRight = Guest,*S-1-5-32-544,*S-1-5-32-545\r\n")
NEGADOS = ("SeDenyInteractiveLogonRight", "SeDenyRemoteInteractiveLogonRight",
           "SeDenyBatchLogonRight", "SeDenyServiceLogonRight")


class Tunel:
    """Una copia del proyecto (docker\\mac.ps1, mac.bat y mac\\) con lo de Windows sustituido."""

    def __init__(self, raiz: Path) -> None:
        self.raiz = raiz
        self.docker = raiz / "proyecto" / "docker"
        self.docker.mkdir(parents=True)
        self.carpeta_mac = raiz / "proyecto" / "mac"
        self.carpeta_mac.mkdir()
        for nombre in ("preparar.command", "abrir-bms.command", "LEEME.txt"):
            (self.carpeta_mac / nombre).write_text(f"# {nombre}\n", encoding="ascii")
        shutil.copy(DOCKER / "mac.bat", self.docker / "mac.bat")
        texto = (DOCKER / "mac.ps1").read_bytes().decode("ascii").replace("\r\n", "\n")
        for antes, despues in (
                ('$ErrorActionPreference = "Continue"\n',
                 '$ErrorActionPreference = "Continue"\n' + SUSTITUTOS_MAC),
                ("    $yo = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]"
                 "::GetCurrent()\n    return $yo.IsInRole([Security.Principal.WindowsBuiltInRole]"
                 "::Administrator)\n", "    return [bool](Mundo).admin\n"),
                ('    $u = [ADSI]("WinNT://" + $env:COMPUTERNAME + "/" + $Nombre + ",user")\n',
                 '    $g = (Mundo).grupos_tunel\n    if ($g -eq "falla") { throw "ADSI" }\n'
                 '    return @($g)\n')):
            assert texto.count(antes) == 1, antes
            texto = texto.replace(antes, despues)
        (self.docker / "mac.ps1").write_bytes(texto.replace("\n", "\r\n").encode("ascii"))
        self.programdata = raiz / "ProgramData"
        self.programdata.mkdir()
        self.ssh = self.programdata / "ssh"
        openssh = raiz / "Windows" / "System32" / "OpenSSH"
        openssh.mkdir(parents=True)
        (openssh / "sshd_config_default").write_text("# de fabrica\nSubsystem sftp sftp-server.exe\n",
                                                     encoding="ascii")
        for programa, carpeta in (("sshd.exe", openssh), ("icacls.exe", openssh.parent),
                                  ("taskkill.exe", openssh.parent),
                                  ("secedit.exe", openssh.parent),
                                  ("takeown.exe", openssh.parent)):
            (carpeta / programa).write_text(PROGRAMA_FALSO.format(python=sys.executable),
                                            encoding="utf-8")
            (carpeta / programa).chmod(0o755)
        self.usb = raiz / "usb"
        self.usb.mkdir()
        admin = {"sid": SID_ADMINISTRADORES, "tipo": "Allow", "derechos": "FullControl"}
        sistema = {"sid": SID_SISTEMA, "tipo": "Allow", "derechos": "FullControl"}
        self.mundo = {
            "admin": True, "capacidad": "NotPresent", "servicio": None, "reglas": {},
            "usuarios": {}, "grupos_tunel": [], "procesos": [], "conexiones": [], "perfiles": [],
            "derechos": DERECHOS_DE_ANTES, "entrada": "NotConfigured", "app": True,
            "hotfix": "2026-11-12", "eventos": [], "sshd_t": "", "sshd_T": "96",
            "ips": [{"Interfaz": "Ethernet", "Indice": 7, "Ip": "192.168.1.10", "Prefijo": 24,
                     "Red": "Public"}],
            "registro": {"HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\ProfileList":
                         {"ProfilesDirectory": str(raiz / "Users")},
                         "HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon\\"
                         "SpecialAccounts\\UserList": {}},
            "acl_defecto": {"dueno": SID_ADMINISTRADORES, "reglas": [sistema, admin, {
                "sid": SID_DUENO, "tipo": "Allow", "derechos": "Modify"}, {
                "sid": SID_BMS, "tipo": "Allow", "derechos": "ReadAndExecute"}]},
            "acl": {},
            "acl_ssh": {"dueno": SID_ADMINISTRADORES, "reglas": [sistema, admin, {
                "sid": "S-1-5-11", "tipo": "Allow", "derechos": "ReadAndExecute"}]},
            "acl_clave": {"dueno": SID_ADMINISTRADORES, "reglas": [sistema, admin]},
        }

    def correr(self, *argumentos: str, entrada: str = "", elevado: bool = True,
               ) -> subprocess.CompletedProcess:
        self.mundo["admin"] = elevado
        (self.raiz / "mundo.json").write_text(json.dumps(self.mundo), encoding="utf-8")
        (self.raiz / "llamadas.log").write_text("", encoding="utf-8")
        entorno = {**os.environ, "SystemRoot": str(self.raiz / "Windows"),
                   "ProgramData": str(self.programdata), "SystemDrive": str(self.raiz),
                   "PRUEBA_MUNDO": str(self.raiz / "mundo.json"),
                   "PRUEBA_LLAMADAS": str(self.raiz / "llamadas.log"),
                   "PRUEBA_SID_TUNEL": SID_TUNEL, "PRUEBA_CLAVE_EQUIPO": CLAVE_EQUIPO,
                   "TMPDIR": str(self.raiz)}
        extra = ["-Elevado"] if elevado else []
        proceso = subprocess.run(
            [PWSH, "-NoProfile", "-File", str(self.docker / "mac.ps1"), *argumentos, *extra,
             "-Usuario", SID_DUENO], env=entorno, input=entrada + "\n" * 5,
            capture_output=True, text=True, timeout=300)
        self.mundo = json.loads((self.raiz / "mundo.json").read_text(encoding="utf-8"))
        return proceso

    def llamadas(self) -> list[list]:
        texto = (self.raiz / "llamadas.log").read_text(encoding="utf-8")
        return [json.loads(l) for l in texto.splitlines()]

    def nombres(self) -> list[str]:
        """Las llamadas en orden, en corto: "Start-Service", "icacls.exe /inheritance:r"..."""
        salida = []
        for nombre, datos in self.llamadas():
            if nombre == "New-NetFirewallRule":
                salida.append(f"New-NetFirewallRule {datos['Name']}")
            elif nombre.endswith(".exe"):
                salida.append(f"{nombre} {datos[0] if datos else ''}".strip())
            else:
                salida.append(nombre)
        return salida

    def estado(self) -> dict | None:
        clave = self.mundo["registro"].get("HKLM:\\SOFTWARE\\bms-agent\\TunelMac")
        return json.loads(clave["Estado"]) if clave else None

    def instalar(self, *mas: str, entrada: str = "si\n") -> subprocess.CompletedProcess:
        """-Instalar ya elevado, con el Mac de ejemplo (como lo pasa la ventana normal)."""
        return self.correr("-Instalar", "-Nombre", "mac-oficina", "-Ip", "192.168.1.23",
                           "-Clave", VECTOR.split()[1], *mas, entrada=entrada)


@pytest.fixture
def tunel(tmp_path):
    if PWSH is None:
        pytest.skip("sin pwsh")
    return Tunel(tmp_path)


def _salida(proceso: subprocess.CompletedProcess) -> str:
    return proceso.stdout + proceso.stderr


def test_pwsh_mac_instalar_de_cero_con_un_mac(tunel) -> None:
    proceso = tunel.instalar()
    assert proceso.returncode == 0, _salida(proceso)
    salida = proceso.stdout
    # Lo que queda escrito: el sshd_config y las claves de mac.md, sin BOM ni CR.
    config = (tunel.ssh / "sshd_config").read_bytes()
    assert config.decode("ascii") == _bloque_del_diseno("### 2.3 El `sshd_config` exacto")
    claves = (tunel.ssh / "bms_tunel_authorized_keys").read_bytes()
    assert claves.decode("ascii") == _bloque_del_diseno("### 2.4 El fichero de claves exacto")
    assert not (tunel.ssh / "sshd_config.bms-nueva").exists()
    assert not (tunel.ssh / "sshd_config.antes-bms").exists()
    # El estado: la foto de antes y el Mac, nada mas.
    estado = tunel.estado()
    assert set(estado) == {"version", "instalado", "antes", "apagado", "config_sha256", "macs"}
    assert estado["antes"] == {"capacidad": "NotPresent", "carpeta": False, "config": "ausente",
                               "servicio_inicio": "", "servicio_en_marcha": False,
                               "regla_microsoft": "no_existe"}
    assert [set(m) for m in estado["macs"]] == [{"nombre", "ip", "clave", "alta"}]
    assert estado["macs"][0]["clave"] == VECTOR and estado["apagado"] is False
    import hashlib
    assert estado["config_sha256"] == hashlib.sha256(config).hexdigest().upper()
    # La cuenta: con una contrasena que nadie ve, sin caducidad, oculta y sin poder entrar.
    nueva = [d for n, d in tunel.llamadas() if n == "New-LocalUser"][0]
    assert nueva["Password"] == "System.Security.SecureString" and nueva["SoloLectura"]
    assert nueva["Longitud"] == 48 and nueva["PasswordNeverExpires"]
    assert nueva["UserMayNotChangePassword"] and nueva["AccountNeverExpires"]
    assert tunel.mundo["registro"]["HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\"
                                   "Winlogon\\SpecialAccounts\\UserList"] == {"bms-tunel": 0}
    derechos = dict(l.split(" = ") for l in tunel.mundo["derechos"].split("\r\n") if " = " in l)
    for negado in NEGADOS:
        assert f"*{SID_TUNEL}" in derechos[negado].split(","), negado
    assert derechos["SeNetworkLogonRight"] == "*S-1-1-0,*S-1-5-32-544,*S-1-5-32-545"
    assert derechos["SeDenyInteractiveLogonRight"] == f"Guest,*{SID_TUNEL}"
    # El servicio, en marcha y automatico; el cortafuegos: la de Microsoft apagada, "resto" a
    # todos menos al Mac y la de los Mac solo a su IP, en cualquier perfil.
    assert tunel.mundo["servicio"] == {"Status": "Running", "StartType": "Automatic"}
    reglas = tunel.mundo["reglas"]
    assert reglas["OpenSSH-Server-In-TCP"]["Enabled"] == "False"
    assert reglas["BMS-Tunel-Mac-sshd-resto"]["RemoteAddress"] == [
        "0.0.0.0-192.168.1.22", "192.168.1.24-255.255.255.255"]
    assert reglas["BMS-Tunel-Mac-sshd"]["RemoteAddress"] == ["192.168.1.23"]
    for nombre in ("BMS-Tunel-Mac-sshd-resto", "BMS-Tunel-Mac-sshd"):
        r = reglas[nombre]
        assert (r["Profile"], r["LocalPort"], r["Protocol"], r["Direction"]) == (
            "Any", "22", "TCP", "Inbound")
        assert r["Program"].endswith("sshd.exe")
    assert reglas["BMS-Tunel-Mac-sshd-resto"]["Action"] == "Block"
    assert reglas["BMS-Tunel-Mac-sshd"]["Action"] == "Allow"
    # En orden: nada arranca antes de cerrar el cortafuegos; la clave del equipo se crea con el
    # cortafuegos cerrado; solo al final se abre a los Mac.
    orden = tunel.nombres()
    _en_orden("\n".join(orden), [
        "Add-WindowsCapability", "Disable-NetFirewallRule",
        "New-NetFirewallRule BMS-Tunel-Mac-sshd-resto", "Start-Service", "Stop-Service",
        "New-LocalUser", "secedit.exe /export", "secedit.exe /configure", "secedit.exe /export",
        "New-NetFirewallRule BMS-Tunel-Mac-sshd-resto", "Stop-Service",
        "icacls.exe", "sshd.exe -t", "sshd.exe -T", "sshd.exe -T", "Set-Service",
        "Start-Service", "New-NetFirewallRule BMS-Tunel-Mac-sshd-resto",
        "New-NetFirewallRule BMS-Tunel-Mac-sshd"])
    assert orden.index("New-NetFirewallRule BMS-Tunel-Mac-sshd") == len(orden) - 1 or \
        "Start-Service" not in orden[orden.index("New-NetFirewallRule BMS-Tunel-Mac-sshd"):]
    # El fichero de claves: solo SYSTEM y Administradores, por SID.
    icacls = [d for n, d in tunel.llamadas() if n == "icacls.exe"]
    ruta = str(tunel.ssh / "bms_tunel_authorized_keys")
    assert [ruta, "/inheritance:r", "/grant:r", "*S-1-5-18:F", "*S-1-5-32-544:F"] in icacls
    assert [ruta, "/setowner", "*S-1-5-32-544"] in icacls
    # Lo que se dice para el Mac: la IP de este equipo y su huella; nunca una clave entera.
    assert "la IP de este equipo: 192.168.1.10" in salida
    assert "SHA256:" in salida and "Listo." in salida
    assert VECTOR.split()[1] not in salida and CLAVE_EQUIPO.split()[1] not in salida


def test_pwsh_mac_estado_tras_instalar_todo_bien_y_sin_claves(tunel) -> None:
    assert tunel.instalar().returncode == 0
    tunel.mundo["conexiones"] = ["192.168.1.23"]
    tunel.mundo["eventos"] = [{"cuando": "2026-11-25T09:14:00", "texto":
                               "Accepted publickey for bms-tunel from 192.168.1.23 port 51234 "
                               "ssh2: ED25519 SHA256:ZkAslGjFiUHdGf/WUL8rQvkib4PTvQatUV0OUQSncCA"}]
    tunel.mundo["hotfix"] = (__import__("datetime").date.today().isoformat())
    proceso = tunel.correr("-Estado")
    assert proceso.returncode == 0, _salida(proceso)
    lineas = {l.split()[0]: l for l in proceso.stdout.splitlines()
              if l.startswith("   ") and len(l.split()) > 1}
    for que in ("servidor", "config", "reenvio", "cuenta", "datos", "scripts", "claves",
                "cortafuegos", "app", "rechazos", "windows"):
        assert re.match(rf"\s+{que}\s+.*?\bbien\b", lineas[que]), lineas.get(que)
    assert "carpeta ssh" in proceso.stdout and "mal" not in proceso.stdout.split()
    assert "mac-oficina      192.168.1.23" in proceso.stdout
    assert "1 abierto(s) ahora: mac-oficina (192.168.1.23)" in proceso.stdout
    assert "entro      25-11-2026 09:14  mac-oficina desde 192.168.1.23" in proceso.stdout
    assert VECTOR.split()[1] not in proceso.stdout
    # -Estado no cambia nada.
    assert not [n for n in tunel.nombres() if n in (
        "Start-Service", "Stop-Service", "Set-Service", "New-NetFirewallRule",
        "Remove-NetFirewallRule", "New-LocalUser", "icacls.exe", "secedit.exe /configure")]


def test_pwsh_mac_estado_dice_en_rojo_lo_que_esta_mal(tunel) -> None:
    assert tunel.instalar().returncode == 0
    tunel.mundo["hotfix"] = "2026-01-01"
    tunel.mundo["grupos_tunel"] = ["S-1-5-32-555"]
    tunel.mundo["acl"][str(tunel.docker.parent)] = {"dueno": SID_ADMINISTRADORES, "reglas": [
        {"sid": "S-1-5-11", "tipo": "Allow", "derechos": "ReadAndExecute"}]}
    (tunel.ssh / "bms_tunel_authorized_keys").write_text("# a mano\n", encoding="ascii")
    tunel.mundo["reglas"]["OpenSSH-Server-In-TCP"]["Enabled"] = "True"
    tunel.mundo["app"] = False
    proceso = tunel.correr("-Estado")
    assert proceso.returncode == 0, _salida(proceso)
    salida = proceso.stdout
    for que, nivel in (("windows", "mal"), ("cuenta", "mal"), ("datos", "mal"),
                       ("claves", "mal"), ("cortafuegos", "aviso"), ("app", "aviso")):
        linea = [l for l in salida.splitlines() if l.strip().startswith(que + " ")][0]
        assert linea.split()[1] == nivel, linea
    assert "actualiza Windows o, hasta entonces, mac.bat -Apagar" in salida
    assert "proteger.bat -Usuario bms" in salida


def test_pwsh_mac_anadir_y_quitar_un_mac_y_el_tunel_que_no_se_corta(tunel) -> None:
    assert tunel.instalar().returncode == 0
    proceso = tunel.correr("-AnadirClave", "-Nombre", "mac-casa", "-Ip", "192.168.1.31",
                           "-Clave", CLAVE_EQUIPO.split()[1])
    assert proceso.returncode == 0, _salida(proceso)
    config = (tunel.ssh / "sshd_config").read_text(encoding="ascii")
    assert "AllowUsers bms-tunel@192.168.1.23 bms-tunel@192.168.1.31\n" in config
    assert tunel.mundo["reglas"]["BMS-Tunel-Mac-sshd"]["RemoteAddress"] == [
        "192.168.1.23", "192.168.1.31"]
    assert tunel.mundo["reglas"]["BMS-Tunel-Mac-sshd-resto"]["RemoteAddress"] == [
        "0.0.0.0-192.168.1.22", "192.168.1.24-192.168.1.30", "192.168.1.32-255.255.255.255"]
    assert [m["nombre"] for m in tunel.estado()["macs"]] == ["mac-oficina", "mac-casa"]
    # Quitar uno con un tunel abierto que Windows no deja cortar: lo dice en rojo.
    tunel.mundo["procesos"] = [{"ProcessId": 501}, {"ProcessId": 502, "duro": True}]
    proceso = tunel.correr("-QuitarClave", "-Nombre", "mac-oficina")
    assert proceso.returncode == 0, _salida(proceso)
    assert [p["ProcessId"] for p in tunel.mundo["procesos"]] == [502]
    assert "ATENCION: queda 1 proceso(s)" in proceso.stdout
    assert "hasta que reinicies el equipo" in proceso.stdout
    assert ["taskkill.exe", ["/F", "/PID", "501"]] in tunel.llamadas()
    claves = (tunel.ssh / "bms_tunel_authorized_keys").read_text(encoding="ascii")
    assert "bms-mac-oficina" not in claves and "bms-mac-casa" in claves
    assert "AllowUsers bms-tunel@192.168.1.31\n" in (tunel.ssh / "sshd_config").read_text(
        encoding="ascii")
    # Sin procesos que se resistan: "cortados".
    tunel.mundo["procesos"] = []
    proceso = tunel.correr("-QuitarClave", "-Nombre", "mac-casa")
    assert proceso.returncode == 0 and "se han cortado los tuneles abiertos" in proceso.stdout
    config = (tunel.ssh / "sshd_config").read_text(encoding="ascii")
    assert "\nDenyUsers *\n" in config and "AllowUsers" not in config
    assert "BMS-Tunel-Mac-sshd" not in tunel.mundo["reglas"]
    assert tunel.mundo["reglas"]["BMS-Tunel-Mac-sshd-resto"]["RemoteAddress"] == ["Any"]


def test_pwsh_mac_apagar_y_encender(tunel) -> None:
    assert tunel.instalar().returncode == 0
    proceso = tunel.correr("-Apagar")
    assert proceso.returncode == 0, _salida(proceso)
    assert tunel.mundo["servicio"] == {"Status": "Stopped", "StartType": "Disabled"}
    assert "BMS-Tunel-Mac-sshd" not in tunel.mundo["reglas"]
    assert tunel.mundo["reglas"]["BMS-Tunel-Mac-sshd-resto"]["RemoteAddress"] == ["Any"]
    assert tunel.estado()["apagado"] is True
    assert "Start-Service" not in tunel.nombres()
    proceso = tunel.correr("-Encender")
    assert proceso.returncode == 0, _salida(proceso)
    assert tunel.mundo["servicio"] == {"Status": "Running", "StartType": "Automatic"}
    assert tunel.mundo["reglas"]["BMS-Tunel-Mac-sshd"]["RemoteAddress"] == ["192.168.1.23"]


def test_pwsh_mac_quitar_deja_el_equipo_como_estaba(tunel) -> None:
    assert tunel.instalar().returncode == 0
    proceso = tunel.correr("-Quitar", entrada="si\nno\n")
    assert proceso.returncode == 0, _salida(proceso)
    m = tunel.mundo
    assert m["capacidad"] == "NotPresent" and m["servicio"] is None
    assert m["reglas"] == {} and m["usuarios"] == {} and m["perfiles"] == []
    assert "HKLM:\\SOFTWARE\\bms-agent\\TunelMac" not in m["registro"]
    assert m["registro"]["HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon\\"
                         "SpecialAccounts\\UserList"] == {}
    assert SID_TUNEL not in m["derechos"]
    assert not (tunel.ssh / "bms_tunel_authorized_keys").exists()
    assert not (tunel.ssh / "sshd_config").exists()
    # La carpeta ssh no estaba antes: se pregunta, y con "no" se queda.
    assert tunel.ssh.is_dir()
    orden = tunel.nombres()
    _en_orden("\n".join(orden), ["Stop-Service", "Remove-NetFirewallRule",
                                 "secedit.exe /configure", "Remove-CimInstance",
                                 "Remove-LocalUser", "Remove-WindowsCapability",
                                 "Remove-NetFirewallRule", "Remove-Item"])
    assert "preparar.command --borrar" in proceso.stdout


def test_pwsh_mac_quitar_devuelve_un_servidor_que_ya_estaba(tunel) -> None:
    """Con la capacidad ya puesta, sshd en marcha, la regla de Microsoft encendida y un
    sshd_config del dueno: -Instalar para; con -SustituirConfiguracion sigue y guarda el de
    antes; -Quitar lo devuelve todo."""
    tunel.mundo["capacidad"] = "Installed"
    tunel.mundo["servicio"] = {"Status": "Running", "StartType": "Automatic"}
    tunel.mundo["reglas"]["OpenSSH-Server-In-TCP"] = {"Enabled": "True", "Action": "Allow",
                                                     "Profile": "Any"}
    tunel.ssh.mkdir()
    (tunel.ssh / "sshd_config").write_text("Port 2222\n", encoding="ascii")
    (tunel.ssh / "ssh_host_ed25519_key.pub").write_text(CLAVE_EQUIPO + "\n", encoding="ascii")
    proceso = tunel.instalar()
    assert proceso.returncode == 1 and "-SustituirConfiguracion" in proceso.stdout
    assert tunel.estado() is None and tunel.mundo["usuarios"] == {}
    assert (tunel.ssh / "sshd_config").read_text() == "Port 2222\n"
    proceso = tunel.instalar("-SustituirConfiguracion")
    assert proceso.returncode == 0, _salida(proceso)
    assert "ya estaba en marcha" in proceso.stdout
    assert (tunel.ssh / "sshd_config.antes-bms").read_text() == "Port 2222\n"
    assert tunel.estado()["antes"]["config"] == "otra"
    proceso = tunel.correr("-Quitar", entrada="si\n")
    assert proceso.returncode == 0, _salida(proceso)
    m = tunel.mundo
    assert (tunel.ssh / "sshd_config").read_text() == "Port 2222\n"
    assert m["capacidad"] == "Installed"
    assert m["servicio"] == {"Status": "Running", "StartType": "Automatic"}
    assert m["reglas"] == {"OpenSSH-Server-In-TCP": {"Enabled": "True", "Action": "Allow",
                                                     "Profile": "Any"}}


@pytest.mark.parametrize("caso", ["sshd_t", "sshd_T", "secedit", "grupos"])
def test_pwsh_mac_lo_que_falla_deja_sshd_parado_y_el_cortafuegos_cerrado(tunel, caso) -> None:
    if caso == "sshd_t":
        tunel.mundo["sshd_t"] = "falla"
    elif caso == "sshd_T":
        tunel.mundo["sshd_T"] = "malo"
    elif caso == "secedit":
        tunel.mundo["secedit"] = "de_mas"
    else:
        tunel.mundo["grupos_tunel"] = "falla"
    proceso = tunel.instalar()
    assert proceso.returncode == 1, _salida(proceso)
    esperado = {"sshd_t": "sshd no acepta la configuracion nueva",
                "sshd_T": "para otra cuenta, sshd no queda cerrado",
                "secedit": "se ha vuelto a poner todo como estaba",
                "grupos": "No se han podido mirar los grupos de bms-tunel"}[caso]
    assert esperado in proceso.stdout
    assert tunel.mundo["servicio"]["Status"] == "Stopped"
    assert tunel.mundo["reglas"]["BMS-Tunel-Mac-sshd-resto"]["RemoteAddress"] == ["Any"]
    assert "BMS-Tunel-Mac-sshd" not in tunel.mundo["reglas"]
    if caso == "sshd_t":
        assert not (tunel.ssh / "sshd_config.bms-nueva").exists()
        assert not (tunel.ssh / "sshd_config").read_text().startswith("# bms-agent")
    if caso == "secedit":
        # Vuelve a estar como antes: tambien lo que secedit anadio de mas y los derechos que
        # antes no tenian a nadie (secedit /configure solo toca lo que trae la plantilla).
        assert tunel.mundo["derechos"] == DERECHOS_DE_ANTES


@pytest.mark.parametrize("pega", ["dueno", "permiso", "clave_legible", "enlace"])
def test_pwsh_mac_la_carpeta_ssh_de_otro_se_aparta(tunel, pega) -> None:
    """mac.md §2.8.1: una C:\\ProgramData\\ssh creada por otra cuenta (o que otra puede cambiar,
    con la clave del equipo a la vista o un enlace dentro) se aparta entera (con "si") y el
    servicio la rehace; sin "si", nada arranca."""
    tunel.ssh.mkdir()
    (tunel.ssh / "plantado.txt").write_text("# plantado\n", encoding="ascii")
    if pega == "dueno":
        acl = {"dueno": SID_BMS, "reglas": []}
        tunel.mundo["acl"][str(tunel.ssh)] = {**acl, "testigo": "plantado.txt"}
        esperado = "es de " + SID_BMS
    elif pega == "permiso":
        tunel.mundo["acl"][str(tunel.ssh)] = {"dueno": SID_ADMINISTRADORES, "testigo": "plantado.txt",
                                             "reglas": [{"sid": SID_BMS, "tipo": "Allow",
                                                         "derechos": "AppendData"}]}
        esperado = SID_BMS + " puede cambiarlo"
    elif pega == "clave_legible":
        (tunel.ssh / "ssh_host_ed25519_key").write_text("privada", encoding="ascii")
        tunel.mundo["acl"][str(tunel.ssh / "ssh_host_ed25519_key")] = {
            "dueno": SID_ADMINISTRADORES, "testigo": "../plantado.txt", "reglas": [
                {"sid": "S-1-5-32-545", "tipo": "Allow", "derechos": "ReadAndExecute"}]}
        esperado = "puede leer la clave del equipo"
    else:
        (tunel.ssh / "enlace").symlink_to(tunel.raiz)
        esperado = "es un enlace"
    proceso = tunel.instalar(entrada="si\nno\n")
    assert proceso.returncode == 1 and "no es de fiar" in proceso.stdout
    assert esperado in proceso.stdout, proceso.stdout
    assert "Start-Service" not in tunel.nombres() and tunel.ssh.is_dir()
    proceso = tunel.instalar(entrada="si\nsi\n")
    assert proceso.returncode == 0, _salida(proceso)
    apartadas = list(tunel.programdata.glob("ssh.apartada-*"))
    assert len(apartadas) == 1 and (apartadas[0] / "plantado.txt").read_text() == "# plantado\n"
    assert not (tunel.ssh / "plantado.txt").exists()
    llamadas = tunel.llamadas()
    # Solo la carpeta de arriba: sin /R ni /T (dentro podria haber enlaces a otros sitios).
    assert ["takeown.exe", ["/F", str(apartadas[0]), "/A"]] in llamadas
    assert [str(apartadas[0]), "/inheritance:r", "/grant:r", "*S-1-5-18:(OI)(CI)F",
            "*S-1-5-32-544:(OI)(CI)F", "/L", "/Q"] in [d for n, d in llamadas if n == "icacls.exe"]
    assert not [d for n, d in llamadas if n in ("takeown.exe", "icacls.exe") and
                ("/R" in d or "/T" in d)]
    assert (tunel.ssh / "ssh_host_ed25519_key.pub").exists()
    assert (tunel.ssh / "sshd_config").read_text().startswith("# bms-agent")


def test_pwsh_mac_no_sigue_si_otros_leen_los_datos(tunel) -> None:
    tunel.mundo["acl"][str(tunel.docker.parent / "docker" / "secretos")] = {
        "dueno": SID_ADMINISTRADORES, "reglas": [
            {"sid": "S-1-5-32-545", "tipo": "Allow", "derechos": "ReadAndExecute"}]}
    (tunel.docker / "secretos").mkdir()
    proceso = tunel.instalar()
    assert proceso.returncode == 1 and "proteger.bat -Usuario bms" in proceso.stdout
    assert tunel.estado() is None and "Add-WindowsCapability" not in tunel.nombres()


@pytest.mark.parametrize("donde, como", [
    ("docker", {"sid": "S-1-5-32-545", "tipo": "Allow", "derechos": "Modify"}),
    ("docker", {"sid": SID_BMS, "tipo": "Allow", "derechos": "CreateFiles"}),
    ("mac/preparar.command", "dueno"),
    ("mac", {"sid": SID_BMS, "tipo": "Allow", "derechos": "AppendData"}),
    ("arriba", {"sid": "S-1-5-11", "tipo": "Allow", "derechos": "Delete"})])
def test_pwsh_mac_no_corre_si_otra_cuenta_puede_cambiarlo(tunel, donde, como) -> None:
    """mac.md §2.11: ni elevar, ni preguntar, ni copiar al Mac."""
    if donde == "arriba":
        ruta = str(tunel.docker.parent.parent)
    else:
        ruta = str(tunel.docker.parent / donde)
    if como == "dueno":
        tunel.mundo["acl"][ruta] = {"dueno": SID_BMS, "reglas": []}
    else:
        tunel.mundo["acl"][ruta] = {"dueno": SID_ADMINISTRADORES, "reglas": [como]}
    for argumentos in (["-Estado"], ["-CopiarParaElMac", str(tunel.usb)]):
        proceso = tunel.correr(*argumentos, elevado=False)
        assert proceso.returncode == 1, _salida(proceso)
        assert "Otra cuenta de este equipo puede cambiar" in proceso.stdout
        assert "Start-Process" not in tunel.nombres() and not (tunel.usb / "bms-mac").exists()
    # Una regla que solo se hereda (CREATOR OWNER en C:\) no cuenta.
    tunel.mundo["acl"][ruta] = {"dueno": SID_ADMINISTRADORES, "reglas": [
        {"sid": "S-1-3-0", "tipo": "Allow", "derechos": "FullControl", "solo_herencia": True}]}
    proceso = tunel.correr("-CopiarParaElMac", str(tunel.usb), elevado=False)
    assert proceso.returncode == 0, _salida(proceso)


def test_pwsh_mac_copiar_para_el_mac(tunel) -> None:
    proceso = tunel.correr("-CopiarParaElMac", str(tunel.usb), elevado=False)
    assert proceso.returncode == 0, _salida(proceso)
    import hashlib
    for nombre in ("preparar.command", "abrir-bms.command", "LEEME.txt"):
        copiado = (tunel.usb / "bms-mac" / nombre).read_bytes()
        assert copiado == (tunel.carpeta_mac / nombre).read_bytes()
        assert f"{nombre}   sha256 {hashlib.sha256(copiado).hexdigest()[:16]}" in proceso.stdout
    assert "192.168.1.10" in proceso.stdout and "Start-Process" not in tunel.nombres()
    # Otra vez: pregunta antes de sustituir.
    proceso = tunel.correr("-CopiarParaElMac", str(tunel.usb), elevado=False, entrada="no\n")
    assert proceso.returncode == 1 and "No se ha copiado nada." in proceso.stdout
    shutil.rmtree(tunel.carpeta_mac)
    proceso = tunel.correr("-CopiarParaElMac", str(tunel.usb), elevado=False)
    assert proceso.returncode == 1 and "Falta la carpeta" in proceso.stdout


def test_pwsh_mac_lo_del_mac_se_pregunta_en_la_ventana_normal(tunel) -> None:
    """Sin elevar: la clave de la memoria (bms-mac\\bms-<nombre>.pub), su nombre, la IP y la
    huella, y a la ventana de administrador solo el nombre, la IP y el base64."""
    usb_mac = tunel.usb / "bms-mac"
    usb_mac.mkdir()
    (usb_mac / "bms-mac-oficina.pub").write_text(VECTOR + " bms-mac-oficina\n", encoding="ascii")
    tunel.mundo["registro"]["HKLM:\\SOFTWARE\\bms-agent\\TunelMac"] = {"Estado": json.dumps(
        {"version": 1, "instalado": "x", "antes": {}, "apagado": False, "config_sha256": "",
         "macs": []})}
    # Las "memorias" son las unidades que ve .NET: aqui, se pide la ruta (o se pega la linea).
    entrada = "\n".join(["mac-oficina", "8.8.8.8", "192.168.1.10", "192.168.1.23",
                         "no-es-una-clave", str(usb_mac / "bms-mac-oficina.pub"), "si"]) + "\n"
    proceso = tunel.correr("-AnadirClave", elevado=False, entrada=entrada)
    assert proceso.returncode == 0, _salida(proceso)
    salida = proceso.stdout
    assert "eso no es una IP de una red privada" in salida
    assert "esa es la IP de este equipo, no la del Mac" in salida
    assert "eso no es una clave publica ed25519" in salida
    assert "Huella de la clave del Mac: SHA256:ZkAslGjFiUHdGf/WUL8rQvkib4PTvQatUV0OUQSncCA" in salida
    [(nombre, datos)] = [x for x in tunel.llamadas() if x[0] == "Start-Process"]
    assert datos["Verb"] == "RunAs"
    argumentos = datos["ArgumentList"]
    assert argumentos[5:] == ["-AnadirClave", "-Elevado", "-Usuario", SID_DUENO, "-Nombre",
                              "mac-oficina", "-Ip", "192.168.1.23", "-Clave", VECTOR.split()[1]]
    assert argumentos[:4] == ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
    # Sin "si" a la huella, no se pide ser administrador.
    entrada = "\n".join(["mac-oficina", "192.168.1.23", VECTOR, "no"]) + "\n"
    proceso = tunel.correr("-AnadirClave", elevado=False, entrada=entrada)
    assert proceso.returncode == 1 and "Start-Process" not in tunel.nombres()


def test_pwsh_mac_lo_que_llega_a_la_ventana_de_administrador_se_vuelve_a_mirar(tunel) -> None:
    assert tunel.instalar().returncode == 0
    for ip, clave in (("8.8.8.8", VECTOR.split()[1]), ("192.168.1.31", "AAAA" * 17),
                      ("192.168.1.5/24", VECTOR.split()[1])):
        proceso = tunel.correr("-AnadirClave", "-Nombre", "mac-casa", "-Ip", ip, "-Clave", clave)
        assert proceso.returncode == 1 and "Uso interno" in proceso.stdout, (ip, clave)
    # -MismaClave con otra clave: no.
    proceso = tunel.correr("-AnadirClave", "-Nombre", "mac-oficina", "-Ip", "192.168.1.40",
                           "-Clave", CLAVE_EQUIPO.split()[1], "-MismaClave")
    assert proceso.returncode == 1 and "-MismaClave" in proceso.stdout
    # Con la que tenia: solo cambia la IP.
    proceso = tunel.correr("-AnadirClave", "-Nombre", "mac-oficina", "-Ip", "192.168.1.40",
                           "-Clave", VECTOR.split()[1], "-MismaClave")
    assert proceso.returncode == 0, _salida(proceso)
    assert [(m["nombre"], m["ip"]) for m in tunel.estado()["macs"]] == [("mac-oficina",
                                                                         "192.168.1.40")]
    # La reserva "red": la red entera, en las tres capas.
    proceso = tunel.correr("-AnadirClave", "-Nombre", "mac-oficina", "-Ip", "192.168.1.0/24",
                           "-Clave", VECTOR.split()[1])
    assert proceso.returncode == 0, _salida(proceso)
    assert "AllowUsers bms-tunel@192.168.1.0/24\n" in (tunel.ssh / "sshd_config").read_text()
    assert 'from="192.168.1.0/24"' in (tunel.ssh / "bms_tunel_authorized_keys").read_text()
    assert tunel.mundo["reglas"]["BMS-Tunel-Mac-sshd-resto"]["RemoteAddress"] == [
        "0.0.0.0-192.168.0.255", "192.168.2.0-255.255.255.255"]


def test_pwsh_mac_sin_instalar_no_hace_nada_mas(tunel) -> None:
    for accion in ("-Estado", "-QuitarClave", "-Apagar", "-Quitar"):
        proceso = tunel.correr(accion, elevado=False)
        assert proceso.returncode == 1 and "no esta instalado" in proceso.stdout, accion
        assert "Start-Process" not in tunel.nombres()
    proceso = tunel.correr("-Estado", "-Apagar")
    assert proceso.returncode == 1 and "Di una cosa" in proceso.stdout
    proceso = tunel.correr("-Instalar", "-Nombre", "Mac Oficina")
    assert proceso.returncode == 1 and "El nombre del Mac" in proceso.stdout


# ============================================================ el lado del Mac (15b.2)

MAC = RAIZ / "mac"
COMMANDS = ("preparar.command", "abrir-bms.command")
BASH = shutil.which("bash")
# Las herramientas que importan, por su variable y su ruta (mac.md §3.1): nada del PATH del dueno
# decide que ssh corre (un OpenSSH de Homebrew no entiende UseKeychain).
HERRAMIENTAS = {"SSH": "/usr/bin/ssh", "SSH_ADD": "/usr/bin/ssh-add",
                "SSH_KEYGEN": "/usr/bin/ssh-keygen", "SSH_KEYSCAN": "/usr/bin/ssh-keyscan",
                "NC": "/usr/bin/nc", "CURL": "/usr/bin/curl", "OPEN": "/usr/bin/open",
                "PGREP": "/usr/bin/pgrep", "LSOF": "/usr/sbin/lsof"}


def _command(nombre: str) -> str:
    return (MAC / nombre).read_text(encoding="ascii")


def _sin_comentarios_bash(texto: str) -> str:
    return "\n".join(l for l in texto.splitlines() if not l.lstrip().startswith("#"))


def test_mac_lo_que_va_al_mac() -> None:
    """mac.md §3.1: tres ficheros, en LF (bash no lee CRLF), ASCII, y los .command con el bit de
    ejecucion en git (100755)."""
    assert sorted(p.name for p in MAC.iterdir()) == ["LEEME.txt", "abrir-bms.command",
                                                     "preparar.command"]
    atributos = (RAIZ / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert "mac/*.command text eol=lf" in atributos and "mac/*.txt text eol=lf" in atributos
    for nombre in (*COMMANDS, "LEEME.txt"):
        crudo = (MAC / nombre).read_bytes()
        assert b"\r" not in crudo and crudo.isascii() and crudo.endswith(b"\n"), nombre
    leeme = (MAC / "LEEME.txt").read_text(encoding="ascii")
    texto = (RAIZ / "docs" / "v1" / "paso-18" / "mac.md").read_text(encoding="utf-8")
    assert leeme == re.search(r"```\n(.*?)```", texto[texto.index("`mac/LEEME.txt`:"):],
                              re.S).group(1)
    indice = subprocess.run(["git", "-C", str(RAIZ), "ls-files", "-s", "--", "mac"],
                            capture_output=True, text=True, check=True).stdout
    modos = {l.split("\t")[1]: l.split()[0] for l in indice.splitlines()}
    assert modos == {"mac/LEEME.txt": "100644", "mac/abrir-bms.command": "100755",
                     "mac/preparar.command": "100755"}
    eol = subprocess.run(["git", "-C", str(RAIZ), "check-attr", "eol", "--",
                          "mac/preparar.command", "mac/LEEME.txt"],
                         capture_output=True, text=True, check=True).stdout
    assert eol.count("eol: lf") == 2


@pytest.mark.parametrize("nombre", COMMANDS)
def test_mac_command_bash_3_2_y_solo_herramientas_del_sistema(nombre) -> None:
    texto = _command(nombre)
    lineas = texto.splitlines()
    assert lineas[0] == "#!/bin/bash"
    codigo = [l for l in lineas[1:] if l.strip() and not l.lstrip().startswith("#")]
    # El PATH del sistema antes de nada que llame a un programa.
    assert "export PATH=/usr/bin:/bin:/usr/sbin:/sbin" in codigo[:3], codigo[:3]
    sin = _sin_comentarios_bash(texto)
    # bash 3.2 de Apple: nada de bash 4.
    for prohibido in (r"declare -A", r"local -A", r"\$\{\w+,,\}", r"\$\{\w+\^\^\}", r"\bmapfile\b",
                      r"\breadarray\b", r"\|&", r"&>>", r"\bcoproc\b", r"wait -n", r"local -n",
                      r"declare -n", r"\[\[ -v"):
        assert not re.search(prohibido, sin), prohibido
    # Cada herramienta, por su variable con su ruta; nunca a pelo como orden.
    usadas = dict(re.findall(r"^([A-Z_]+)=(/\S+)$", sin, re.M))
    for variable, ruta in usadas.items():
        if variable in HERRAMIENTAS:
            assert ruta == HERRAMIENTAS[variable], variable
    assert usadas.get("SSH") == "/usr/bin/ssh" and usadas.get("LSOF") == "/usr/sbin/lsof"
    for orden in ("ssh", "ssh-add", "ssh-keygen", "ssh-keyscan", "nc", "curl", "open", "pgrep",
                  "lsof"):
        assert not re.search(rf"(^|[;&|(]|\$\(|then|do|else)\s*{re.escape(orden)}\s", sin,
                             re.M), orden
    # pgrep, siempre de los procesos de esta cuenta.
    for linea in [l for l in sin.splitlines() if '"$PGREP"' in l]:
        assert '"$PGREP" -U "$YO" -f' in linea, linea
    # ssh, siempre con su configuracion aislada (-F) y sin consola (-N); salvo ssh -V.
    for linea in [l for l in sin.splitlines() if re.search(r'"\$SSH" -', l)]:
        assert '"$SSH" -V' in linea or '"$SSH" -F "$CONFIG" -N' in linea, linea
    for prohibido in (r"\bsudo\b", r"xattr -r", r"xattr -c", r"\|\s*(ba)?sh\b", r"\beval\b",
                      r"StrictHostKeyChecking (no|accept-new|off)", r"\bsource\b"):
        assert not re.search(prohibido, sin), prohibido
    if "rm -rf" in sin:
        assert [l.strip() for l in sin.splitlines() if "rm -rf" in l] == ['rm -rf "$DIR"']
        assert 'rm -rf "$DIR"' in sin[sin.index("borrar() {"):sin.index("\n}\n",
                                                                       sin.index("borrar() {"))]


@pytest.mark.skipif(BASH is None, reason="sin bash")
@pytest.mark.parametrize("nombre", COMMANDS)
def test_mac_command_bash_n(nombre) -> None:
    for opciones in (["-n"], ["--posix", "-n"]):
        proceso = subprocess.run([BASH, *opciones, str(MAC / nombre)], capture_output=True,
                                 text=True, timeout=60)
        assert proceso.returncode == 0, (opciones, proceso.stderr)


def test_mac_la_configuracion_del_tunel() -> None:
    """mac.md §3.4: el ssh_config que escribe preparar.command, con las lineas del diseno, y
    nada que abra mas de lo que hace falta."""
    texto = _command("preparar.command")
    heredoc = texto[texto.index('cat > "$CONFIG" <<FIN\n') + len('cat > "$CONFIG" <<FIN\n'):]
    heredoc = heredoc[:heredoc.index("\nFIN\n")]
    disenado = _bloque_del_diseno("`ssh_config` (lo escribe `preparar`")
    esperado = (disenado.replace("bms-minipc", "$ALIAS").replace("192.168.1.10", "$ipmini")
                .replace("/Users/<usuario>/.bms-tunel/clave_ed25519", "$CLAVE")
                .replace("/Users/<usuario>/.bms-tunel/known_hosts", "$CONOCIDOS")
                .replace("User bms-tunel", "User $CUENTA").replace("8765", "$PUERTO"))
    lineas = [l for l in heredoc.splitlines() if not l.startswith("#")]
    assert "\n".join(lineas) + "\n" == esperado
    for prohibido in ("GatewayPorts yes", "RemoteForward", "DynamicForward", "ForwardAgent yes",
                      "ProxyCommand", "0.0.0.0", "localhost", "StrictHostKeyChecking no",
                      "accept-new", "PermitLocalCommand yes"):
        assert prohibido not in heredoc, prohibido
    assert not re.search(r"(?m)^\s*LocalCommand", heredoc)


def test_mac_preparar_en_orden() -> None:
    """Sin frase no vale; la huella se compara (con "si") antes de fijarla; el enlace del
    Escritorio se comprueba; y lo que llega del mini PC se mira antes de usarlo."""
    texto = _sin_comentarios_bash(_command("preparar.command"))
    _en_orden(texto, [
        'tunel_abierto && fallar',
        'cp -X "$AQUI/preparar.command"',
        'xattr -d com.apple.quarantine "$DIR/abrir-bms.command"',
        '"$SSH_KEYGEN" -q -t ed25519 -a 100 -C "bms-$nombre" -f "$CLAVE"',
        'if "$SSH_KEYGEN" -y -P "" -f "$CLAVE" >/dev/null 2>&1; then',
        "continue",
        '"$SSH_ADD" --apple-use-keychain "$CLAVE"',
        'while ! ip_privada "$ipmini" >/dev/null; do',
        '"$SSH_KEYSCAN" -T 5 -t ed25519',
        "grep -Eq '^ssh-ed25519 [A-Za-z0-9+/]{68}$'",
        'es_si "$r" || { rm -f "$tmp"; fallar',
        'mv -f "$tmp" "$CONOCIDOS"',
        'cat > "$CONFIG" <<FIN',
        'quitar_reserva',
        'if puerto_ocupado; then',
        '"$SSH" -F "$CONFIG" -N -o BatchMode=yes "$ALIAS"',
        'if ln -sfn "$DIR/abrir-bms.command" "$HOME/Desktop/BMS.command" 2>/dev/null && '
        '[ -L "$HOME/Desktop/BMS.command" ]; then',
    ])
    assert "umask 077" in texto and 'chmod 700 "$DIR"' in texto
    assert 'chmod 600 "$CONFIG" "$CONOCIDOS"' in texto


def test_mac_abrir_bms_guarda_el_puerto() -> None:
    """mac.md §3.5: la reserva se suelta justo antes de ssh y se pone justo cuando ssh termina
    (la pestana de la app sigue llamando con el token)."""
    texto = _sin_comentarios_bash(_command("abrir-bms.command"))
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    i = lineas.index('"$SSH" -F "$CONFIG" -N -o BatchMode="$LOTE" "$ALIAS" 2>"$ERRORES" &')
    assert lineas[i - 1] == "soltar"
    j = lineas.index('wait "$PID_SSH"')
    assert lineas[j + 1] == 'PID_SSH=""'
    assert lineas[j + 2] == 'if [ "$abierta" = si ] && ! reservar; then'
    assert '"$NC" -lk 127.0.0.1 "$PUERTO" </dev/null >/dev/null 2>&1 &' in texto
    assert "trap cerrar EXIT" in texto and "INT TERM HUP" in texto
    # Ya abierto solo si quien escucha es ese ssh (lsof), y el puerto ocupado para.
    _en_orden(texto, ['for p in $("$PGREP" -U "$YO" -f "ssh -F $CONFIG -N"', 'if escucha_el "$p"',
                      'for p in $("$PGREP" -U "$YO" -f "nc -lk 127.0.0.1 $PUERTO"',
                      "if puerto_ocupado; then", "fallar"])


# ------------------------------------------------------------ con programas falsos

# Los programas de macOS que usan los .command, falsos (pruebas-final/falso de mac.md §5.1): ssh
# sigue un guion (abre y se corta, deniega, la huella, el puerto ocupado...), nc guarda el puerto,
# lsof dice quien escucha. Solo se cambian las lineas del PATH y de las herramientas del script.
FALSOS = {
    "ssh": r"""#!/bin/bash
[ "$1" = "-V" ] && { echo "OpenSSH_9.8p1, LibreSSL 3.3.6" >&2; exit 0; }
n=$(cat "$FALSO/cuenta" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "$FALSO/cuenta"
echo "$*" >> "$FALSO/ssh.log"
linea=$(sed -n "${n}p" "$FALSO/guion"); [ -n "$linea" ] || linea=$(tail -n 1 "$FALSO/guion")
que=${linea%% *}; seg=${linea#* }
echo "ssh-inicio $n $que" >> "$FALSO/eventos.log"
case "$que" in
  abre|abre-y-roban)
    echo $$ > "$FALSO/escucha"
    trap 'rm -f "$FALSO/escucha"; echo "ssh-fin $n matado" >> "$FALSO/eventos.log"; exit 255' TERM
    /bin/sleep "$seg"
    rm -f "$FALSO/escucha"
    [ "$que" = abre-y-roban ] && touch "$FALSO/robar"
    echo "ssh-fin $n" >> "$FALSO/eventos.log"
    echo "Connection to bms-minipc closed by remote host." >&2; exit 255 ;;
  sigue) echo $$ > "$FALSO/escucha"; trap 'rm -f "$FALSO/escucha"; exit 255' TERM; while :; do /bin/sleep 0.1; done ;;
  colgado) trap 'exit 255' TERM; while :; do /bin/sleep 0.1; done ;;
  deniega) echo "bms-tunel@bms-minipc: Permission denied (publickey)." >&2; exit 255 ;;
  huella) echo "Host key verification failed." >&2; exit 255 ;;
  ocupado) echo "bind [127.0.0.1]:8765: Address already in use" >&2; echo "Could not request local forwarding." >&2; exit 255 ;;
  *) /bin/sleep 0.2; echo "ssh: connect to host 192.168.1.10 port 22: Operation timed out" >&2; exit 255 ;;
esac
""",
    "nc": r"""#!/bin/bash
case " $* " in
  *" -z "*" 22 "*) [ -f "$FALSO/sin-22" ] && exit 1; exit 0 ;;
  *" -z "*) [ -f "$FALSO/escucha" ] || [ -f "$FALSO/ocupado" ]; exit $? ;;
  *" -lk "*)
    if [ -f "$FALSO/ocupado" ] || [ -f "$FALSO/robar" ]; then echo "reserva-falla" >> "$FALSO/eventos.log"; exit 1; fi
    echo $$ > "$FALSO/escucha"; echo "reserva" >> "$FALSO/eventos.log"
    trap 'rm -f "$FALSO/escucha"; echo "suelta" >> "$FALSO/eventos.log"; exit 0' TERM
    while :; do /bin/sleep 0.1; done ;;
esac
exit 1
""",
    "lsof": r"""#!/bin/bash
pid=""; prev=""
for a in "$@"; do [ "$prev" = "-p" ] && pid="$a"; prev="$a"; done
[ -n "$pid" ] && [ -f "$FALSO/escucha" ] && [ "$(cat "$FALSO/escucha")" = "$pid" ] && { echo "$pid"; exit 0; }
exit 1
""",
    "pgrep": r"""#!/bin/bash
echo "pgrep $*" >> "$FALSO/pgrep.log"
case "$*" in
  *"ssh -F"*) [ -s "$FALSO/pgrep-ssh" ] && cat "$FALSO/pgrep-ssh" && exit 0 ;;
  *"nc -lk"*) [ -s "$FALSO/pgrep-nc" ] && cat "$FALSO/pgrep-nc" && exit 0 ;;
esac
exit 1
""",
    "curl": '#!/bin/bash\necho "curl $*" >> "$FALSO/curl.log"\ncat "$FALSO/codigo" 2>/dev/null || echo 200\n',
    "open": '#!/bin/bash\necho "open $*" >> "$FALSO/open.log"\n',
    "ssh-add": '#!/bin/bash\necho "ssh-add $*" >> "$FALSO/ssh-add.log"\nexit 0\n',
    "sleep": '#!/bin/bash\necho "sleep $1" >> "$FALSO/sleep.log"\ncase "$1" in 0.*) exec /bin/sleep 0.05 ;; *) exec /bin/sleep 0.2 ;; esac\n',
    # Lo de preparar.command.
    "cp": '#!/bin/bash\n# cp de macOS: -X (sin atributos extendidos) no existe en el cp de GNU.\na=(); for x in "$@"; do [ "$x" = "-X" ] || a+=("$x"); done; exec /bin/cp "${a[@]}"\n',
    "ipconfig": "#!/bin/bash\necho 192.168.1.23\n",
    "route": '#!/bin/bash\necho "  interface: en0"\n',
    "pbcopy": "#!/bin/bash\ncat >/dev/null\n",
    "uname": "#!/bin/bash\necho Darwin\n",
    "xattr": '#!/bin/bash\necho "xattr $*" >> "$FALSO/xattr.log"\nexit 0\n',
    "ssh-keygen": '#!/bin/bash\necho "256 SHA256:ZkAslGjFiUHdGf/WUL8rQvkib4PTvQatUV0OUQSncCA nada (ED25519)"\n',
    "ssh-keyscan": '#!/bin/bash\ncat "$FALSO/keyscan" 2>/dev/null || echo "bms-minipc ' + VECTOR + '"\n',
}


class MacFalso:
    """Un Mac de mentira: un HOME, ~/.bms-tunel ya preparado (o no), una "memoria" con los
    .command y los programas falsos delante."""

    def __init__(self, raiz: Path) -> None:
        self.raiz = raiz
        self.bin = raiz / "bin"
        self.bin.mkdir()
        for nombre, texto in FALSOS.items():
            (self.bin / nombre).write_text(texto, encoding="utf-8")
            (self.bin / nombre).chmod(0o755)
        self.estado = raiz / "estado"
        self.estado.mkdir()
        self.home = raiz / "home"
        self.dir = self.home / ".bms-tunel"
        self.dir.mkdir(parents=True)
        (self.home / "Desktop").mkdir()
        self.usb = raiz / "usb" / "bms-mac"
        self.usb.mkdir(parents=True)
        for nombre in COMMANDS:
            texto = _command(nombre)
            texto = re.sub(r"(?m)^export PATH=.*$", f"export PATH={self.bin}:/usr/bin:/bin", texto)
            for variable in HERRAMIENTAS:
                texto = re.sub(rf"(?m)^{variable}=/\S+$",
                               f"{variable}={self.bin}/{HERRAMIENTAS[variable].rsplit('/', 1)[1]}",
                               texto)
            (self.usb / nombre).write_text(texto, encoding="ascii")

    def preparado(self) -> None:
        """~/.bms-tunel como lo deja un preparar.command que llego al final."""
        (self.dir / "ssh_config").write_text("# de prueba\n", encoding="ascii")
        (self.dir / "known_hosts").write_text(f"bms-minipc {VECTOR}\n", encoding="ascii")
        (self.dir / "clave_ed25519").write_text("privada de prueba\n", encoding="ascii")
        (self.dir / "clave_ed25519.pub").write_text(VECTOR + " bms-mac-oficina\n",
                                                    encoding="ascii")
        (self.dir / "nombre").write_text("mac-oficina\n", encoding="ascii")
        (self.dir / "ip-minipc").write_text("192.168.1.10\n", encoding="ascii")

    def correr(self, nombre: str, guion: str = "abre 1", entrada: str = "",
               *argumentos: str) -> subprocess.CompletedProcess:
        (self.estado / "guion").write_text(guion.replace("|", "\n") + "\n", encoding="ascii")
        entorno = {"HOME": str(self.home), "FALSO": str(self.estado), "LANG": "C",
                   "PATH": "/usr/bin:/bin"}
        proceso = subprocess.Popen([BASH, str(self.usb / nombre), *argumentos], env=entorno,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, start_new_session=True)
        try:
            salida, _ = proceso.communicate(entrada, timeout=90)
        finally:
            # Lo que se haya quedado (un nc o un ssh falsos): fuera.
            try:
                os.killpg(proceso.pid, 9)
            except ProcessLookupError:
                pass
        return subprocess.CompletedProcess(proceso.args, proceso.returncode, salida, "")

    def leer(self, nombre: str) -> str:
        fichero = self.estado / nombre
        return fichero.read_text(encoding="utf-8") if fichero.exists() else ""

    def eventos(self) -> list[str]:
        return self.leer("eventos.log").split()


@pytest.fixture
def mac_falso(tmp_path):
    if BASH is None:
        pytest.skip("sin bash")
    return MacFalso(tmp_path)


def test_abrir_bms_se_corta_vuelve_y_guarda_el_puerto_entre_medias(mac_falso) -> None:
    """Caso 1: abre, se corta y vuelve sin reabrir el navegador, con la reserva entre medias;
    y cuando el mini PC deja de aceptar la clave, para con el puerto guardado hasta Intro."""
    mac_falso.preparado()
    proceso = mac_falso.correr("abrir-bms.command", "abre 1|abre 1|deniega", "\n")
    salida = proceso.stdout
    assert proceso.returncode == 1, salida
    assert mac_falso.leer("open.log") == "open http://127.0.0.1:8765/app\n"
    assert "Tunel abierto otra vez" in salida and "Se reintenta en 5 s" in salida
    assert "Se reintenta en 10 s" in salida
    assert "El mini PC no acepta la clave de este Mac" in salida
    assert "Cierra la pestana de la app" in salida
    # Entre un ssh y el siguiente, la reserva; y al final se suelta.
    eventos = " ".join(mac_falso.eventos())
    assert eventos == ("ssh-inicio 1 abre ssh-fin 1 reserva suelta ssh-inicio 2 abre ssh-fin 2 "
                       "reserva suelta ssh-inicio 3 deniega reserva suelta")
    assert not (mac_falso.estado / "escucha").exists()
    # La frase, del Llavero; y el ssh, aislado y en lote.
    assert "ssh-add --apple-use-keychain" in mac_falso.leer("ssh-add.log")
    assert mac_falso.leer("ssh.log").splitlines()[0] == (
        f"-F {mac_falso.dir}/ssh_config -N -o BatchMode=yes bms-minipc")


@pytest.mark.parametrize("caso", ["ocupado", "ssh_nuestro_que_no_escucha"])
def test_abrir_bms_no_abre_con_el_puerto_ocupado(mac_falso, caso) -> None:
    mac_falso.preparado()
    (mac_falso.estado / "ocupado").touch()
    if caso == "ssh_nuestro_que_no_escucha":
        (mac_falso.estado / "pgrep-ssh").write_text("4242\n")
    proceso = mac_falso.correr("abrir-bms.command")
    assert proceso.returncode == 1
    assert "Otro programa de este Mac usa ya el puerto 8765" in proceso.stdout
    assert mac_falso.leer("cuenta") == "" and mac_falso.leer("open.log") == ""


def test_abrir_bms_la_clave_quitada_a_la_primera(mac_falso) -> None:
    mac_falso.preparado()
    proceso = mac_falso.correr("abrir-bms.command", "deniega")
    assert proceso.returncode == 1 and "no acepta la clave" in proceso.stdout
    # Nunca llego a abrir: ni navegador, ni reserva, ni esperar a nadie.
    assert mac_falso.leer("open.log") == "" and "reserva" not in mac_falso.eventos()
    assert "Cierra la pestana" not in proceso.stdout


def test_abrir_bms_la_huella_cambiada_para(mac_falso) -> None:
    mac_falso.preparado()
    proceso = mac_falso.correr("abrir-bms.command", "abre 1|huella", "\n")
    assert proceso.returncode == 1
    assert "La identidad del mini PC NO es la que se fijo" in proceso.stdout
    assert mac_falso.leer("cuenta") == "2\n"


def test_abrir_bms_si_alguien_coge_el_puerto_al_cortarse(mac_falso) -> None:
    mac_falso.preparado()
    proceso = mac_falso.correr("abrir-bms.command", "abre-y-roban 1|abre 1")
    assert proceso.returncode == 1
    assert "otro programa de este Mac ha cogido el puerto 8765" in proceso.stdout
    assert "token nuevo" in proceso.stdout
    assert mac_falso.leer("cuenta") == "1\n"


def test_abrir_bms_ya_abierto_en_otra_ventana(mac_falso) -> None:
    mac_falso.preparado()
    (mac_falso.estado / "pgrep-ssh").write_text("4242\n")
    (mac_falso.estado / "escucha").write_text("4242\n")
    proceso = mac_falso.correr("abrir-bms.command")
    assert proceso.returncode == 0 and "ya esta abierto en otra ventana" in proceso.stdout
    assert mac_falso.leer("open.log") == "open http://127.0.0.1:8765/app\n"
    assert mac_falso.leer("cuenta") == ""
    assert '-U ' in mac_falso.leer("pgrep.log")


def test_abrir_bms_quita_una_reserva_huerfana(mac_falso) -> None:
    mac_falso.preparado()
    huerfana = subprocess.Popen([str(mac_falso.bin / "nc"), "-lk", "127.0.0.1", "8765"],
                                env={"FALSO": str(mac_falso.estado), "PATH": "/usr/bin:/bin"},
                                start_new_session=True)
    try:
        for _ in range(100):
            if (mac_falso.estado / "escucha").exists():
                break
            __import__("time").sleep(0.05)
        (mac_falso.estado / "pgrep-nc").write_text(f"{huerfana.pid}\n")
        proceso = mac_falso.correr("abrir-bms.command", "abre 1|deniega", "\n")
        assert proceso.returncode == 1, proceso.stdout
        assert mac_falso.eventos()[:3] == ["reserva", "suelta", "ssh-inicio"]
        assert mac_falso.leer("open.log") == "open http://127.0.0.1:8765/app\n"
    finally:
        huerfana.kill()
        huerfana.wait()


def test_abrir_bms_sin_red_no_abre(mac_falso) -> None:
    mac_falso.preparado()
    proceso = mac_falso.correr("abrir-bms.command", "nada")
    assert proceso.returncode == 1
    assert "Operation timed out" in proceso.stdout
    assert "No se ha podido abrir el tunel" in proceso.stdout
    assert mac_falso.leer("open.log") == ""


def test_abrir_bms_alguien_se_cuela_entre_soltar_y_ssh(mac_falso) -> None:
    mac_falso.preparado()
    proceso = mac_falso.correr("abrir-bms.command", "abre 1|ocupado", "\n")
    assert proceso.returncode == 1
    assert "Otro programa de este Mac ha cogido el puerto 8765" in proceso.stdout
    assert " ".join(mac_falso.eventos()).endswith("ssh-inicio 2 ocupado reserva suelta")


def test_abrir_bms_espera_cada_vez_mas_hasta_60_s(mac_falso) -> None:
    """Tras cortes seguidos: 5, 10, 20, 40 y luego 60 s (no 80)."""
    mac_falso.preparado()
    proceso = mac_falso.correr("abrir-bms.command", "abre 1|abre 1|abre 1|abre 1|abre 1|abre 1|"
                               "deniega", "\n")
    assert proceso.returncode == 1, proceso.stdout
    esperas = re.findall(r"Se reintenta en (\d+) s", proceso.stdout)
    assert esperas == ["5", "10", "20", "40", "60", "60"]


def test_abrir_bms_sin_preparar(mac_falso) -> None:
    proceso = mac_falso.correr("abrir-bms.command")
    assert proceso.returncode == 1 and "abre antes preparar.command" in proceso.stdout


@pytest.mark.parametrize("codigo, abre", [("200", "/app"), ("503", "/consola"), ("000", "")])
def test_abrir_bms_lo_que_abre_segun_contesta_la_app(mac_falso, codigo, abre) -> None:
    mac_falso.preparado()
    (mac_falso.estado / "codigo").write_text(codigo)
    proceso = mac_falso.correr("abrir-bms.command", "abre 1|deniega", "\n")
    assert proceso.returncode == 1
    if abre:
        assert mac_falso.leer("open.log") == f"open http://127.0.0.1:8765{abre}\n"
    else:
        assert mac_falso.leer("open.log") == ""
        assert "la app del mini PC no contesta" in proceso.stdout


# preparar.command


def test_preparar_funciona_y_deja_bms_en_el_escritorio(mac_falso) -> None:
    mac_falso.preparado()
    (mac_falso.estado / "guion").write_text("sigue\n")
    proceso = mac_falso.correr("preparar.command", "sigue", "\n")
    assert proceso.returncode == 0, proceso.stdout
    salida = proceso.stdout
    assert "Funciona: la app del mini PC contesta por el tunel." in salida
    assert "La huella del mini PC es la de siempre" in salida
    escritorio = mac_falso.home / "Desktop" / "BMS.command"
    assert escritorio.is_symlink() and os.readlink(escritorio) == str(
        mac_falso.dir / "abrir-bms.command")
    # La clave publica, en la memoria (alli la busca mac.bat), y las copias sin cuarentena.
    assert (mac_falso.usb / "bms-mac-oficina.pub").read_text() == VECTOR + " bms-mac-oficina\n"
    for nombre in COMMANDS:
        assert (mac_falso.dir / nombre).read_bytes() == (mac_falso.usb / nombre).read_bytes()
        assert oct((mac_falso.dir / nombre).stat().st_mode & 0o777) == "0o700"
    assert mac_falso.leer("xattr.log") == (
        f"xattr -d com.apple.quarantine {mac_falso.dir}/abrir-bms.command\n")
    assert oct(mac_falso.dir.stat().st_mode & 0o777) == "0o700"
    config = (mac_falso.dir / "ssh_config").read_text()
    assert "    HostName 192.168.1.10\n" in config
    assert f"    IdentityFile {mac_falso.dir}/clave_ed25519\n" in config
    assert oct((mac_falso.dir / "ssh_config").stat().st_mode & 0o777) == "0o600"
    assert "IP de este Mac:       192.168.1.23" in salida
    assert "SHA256:ZkAslGjFiUHdGf/WUL8rQvkib4PTvQatUV0OUQSncCA" in salida


@pytest.mark.parametrize("guion, rc, texto", [
    ("nada", 1, "No se ha podido abrir el tunel"),
    ("colgado", 1, "El mini PC tarda en contestar"),
    ("deniega", 1, "mac.bat -AnadirClave (nombre mac-oficina, IP 192.168.1.23, el fichero "
                   "bms-mac-oficina.pub)"),
    ("huella", 1, "La identidad del mini PC NO es la que se acaba de fijar")])
def test_preparar_dice_por_que_no_abre(mac_falso, guion, rc, texto) -> None:
    mac_falso.preparado()
    proceso = mac_falso.correr("preparar.command", guion, "\n")
    assert proceso.returncode == rc and texto in proceso.stdout, proceso.stdout
    assert not (mac_falso.home / "Desktop" / "BMS.command").exists()


def test_preparar_sin_el_mini_pc_termina_bien_y_sigue_despues(mac_falso) -> None:
    mac_falso.preparado()
    (mac_falso.estado / "sin-22").touch()
    proceso = mac_falso.correr("preparar.command", "abre 1", "\n")
    assert proceso.returncode == 0, proceso.stdout
    assert "El mini PC no contesta en 192.168.1.10" in proceso.stdout
    assert "bash ~/.bms-tunel/preparar.command" in proceso.stdout
    assert mac_falso.leer("cuenta") == ""


def test_preparar_el_escritorio_que_no_deja(mac_falso) -> None:
    mac_falso.preparado()
    (mac_falso.bin / "ln").write_text('#!/bin/bash\necho "ln: Operation not permitted" >&2\nexit 1\n')
    (mac_falso.bin / "ln").chmod(0o755)
    proceso = mac_falso.correr("preparar.command", "sigue", "\n")
    assert proceso.returncode == 0, proceso.stdout
    assert "No he podido dejar BMS en el Escritorio" in proceso.stdout
    assert f"bash {mac_falso.dir}/abrir-bms.command" in proceso.stdout


def test_preparar_una_huella_nueva_se_compara_y_sin_si_no_se_fija(mac_falso) -> None:
    mac_falso.preparado()
    otra = "bms-minipc " + CLAVE_EQUIPO
    (mac_falso.estado / "keyscan").write_text(otra + "\n")
    proceso = mac_falso.correr("preparar.command", "sigue", "\nno\n")
    assert proceso.returncode == 1
    assert "ATENCION: la huella del mini PC NO es la que se fijo" in proceso.stdout
    assert (mac_falso.dir / "known_hosts").read_text() == f"bms-minipc {VECTOR}\n"
    proceso = mac_falso.correr("preparar.command", "sigue", "\nsi\n")
    assert proceso.returncode == 0, proceso.stdout
    assert (mac_falso.dir / "known_hosts").read_text() == otra + "\n"


@pytest.mark.parametrize("linea", [
    "bms-minipc ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC",
    "bms-minipc ssh-ed25519 AAAA;rm",
    "bms-minipc ssh-ed25519 " + VECTOR.split()[1] + "x"])
def test_preparar_no_se_cree_lo_que_da_el_mini_pc(mac_falso, linea) -> None:
    mac_falso.preparado()
    (mac_falso.dir / "known_hosts").unlink()
    (mac_falso.estado / "keyscan").write_text(linea + "\n")
    proceso = mac_falso.correr("preparar.command", "sigue", "\nsi\n")
    assert proceso.returncode == 1
    assert ("no es la que se espera" in proceso.stdout or
            "El mini PC no ha dado su clave" in proceso.stdout), proceso.stdout
    assert not (mac_falso.dir / "known_hosts").exists()


def test_preparar_con_el_tunel_abierto_no_hace_nada(mac_falso) -> None:
    mac_falso.preparado()
    (mac_falso.estado / "pgrep-ssh").write_text("4242\n")
    for argumentos in ((), ("--borrar",)):
        proceso = mac_falso.correr("preparar.command", "sigue", "si\n", *argumentos)
        assert proceso.returncode == 1 and "Hay un tunel abierto" in proceso.stdout
    assert (mac_falso.dir / "clave_ed25519").exists()


def test_preparar_borrar(mac_falso) -> None:
    mac_falso.preparado()
    (mac_falso.home / "Desktop" / "BMS.command").symlink_to(mac_falso.dir / "abrir-bms.command")
    proceso = mac_falso.correr("preparar.command", "sigue", "no\n", "--borrar")
    assert proceso.returncode == 1 and mac_falso.dir.exists()
    proceso = mac_falso.correr("preparar.command", "sigue", "si\n", "--borrar")
    assert proceso.returncode == 0, proceso.stdout
    assert not mac_falso.dir.exists()
    assert not (mac_falso.home / "Desktop" / "BMS.command").is_symlink()
    assert "ssh-add -d --apple-use-keychain" in mac_falso.leer("ssh-add.log")
    assert "mac.bat -QuitarClave -Nombre mac-oficina" in proceso.stdout


# ------------------------------------------------------------ con un OpenSSH de verdad

# La configuracion que escribe mac.ps1 (Texto-Config y Texto-Claves, con pwsh), probada con el sshd
# de un OpenSSH 9.6 de verdad (mac.md §0, "Con un OpenSSH de verdad"). Necesita la raiz de un
# OpenSSH sacado de sus .deb (BMS_OPENSSH, con usr/sbin/sshd y usr/bin/ssh), ser root y unshare:
# corre en un espacio de montaje propio (/run, un tmpfs nuevo; /etc/passwd con el usuario de la
# separacion de privilegios), sin cambiar nada del sistema. Prueba la semantica de OpenSSH, no la
# de Windows (mac.md §5.2).
DENTRO = r"""#!/bin/bash
set -u
O=$1; P=$2; T=/run/bmstunel
SSHD=$O/usr/sbin/sshd; SSH=$O/usr/bin/ssh; KEYGEN=$O/usr/bin/ssh-keygen; SFTP=$O/usr/bin/sftp
export LD_LIBRARY_PATH=$O/usr/lib/x86_64-linux-gnu
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
mount -t tmpfs -o mode=755 tmpfs /run
mkdir -p /run/sshd $T && chmod 755 $T
cp /etc/passwd $P/passwd && echo 'sshd:x:105:65534::/run/sshd:/usr/sbin/nologin' >> $P/passwd
mount --bind $P/passwd /etc/passwd
$KEYGEN -q -t ed25519 -N '' -f $T/ssh_host_ed25519_key
$KEYGEN -q -t ed25519 -N '' -C mac -f $T/mac
$KEYGEN -q -t ed25519 -N '' -C otra -f $T/otra
# La configuracion de mac.ps1, con las rutas, el puerto y la cuenta de esta prueba.
sed -e "s#__PROGRAMDATA__/ssh/#$T/#g" -e 's#^Port 22$#Port 2223\nListenAddress 127.0.0.1#' \
    -e 's#bms-tunel@192.168.1.23#root@127.0.0.1#' -e 's#^Match User bms-tunel#Match User root#' \
    $P/sshd_config > $T/sshd_config
# Las claves de mac.ps1, con la clave de esta prueba y desde 127.0.0.1.
clave="$(cut -d' ' -f1,2 $T/mac.pub)"
sed -e 's#from="192.168.1.23"#from="127.0.0.1"#' -e "s#ssh-ed25519 [A-Za-z0-9+/]* bms-#$clave bms-#" \
    $P/claves > $T/bms_tunel_authorized_keys
chmod 600 $T/bms_tunel_authorized_keys
echo "=== F1"; $SSHD -t -f $T/sshd_config; echo "rc=$?"
echo "=== F2"; $SSHD -T -f $T/sshd_config -C user=root,host=mac,addr=127.0.0.1
echo "=== F3"; $SSHD -T -f $T/sshd_config -C user=otra,host=mac,addr=127.0.0.1
echo "=== FIN-T"
python3 -I $P/servidores.py $T/docker.sock & SRV=$!
$SSHD -D -e -f $T/sshd_config 2>$P/sshd.log & SSHD_PID=$!
sleep 1.5
C=(-F /dev/null -p 2223 -i $T/mac -o IdentitiesOnly=yes -o UserKnownHostsFile=$T/kh -o StrictHostKeyChecking=accept-new -o BatchMode=yes -o ConnectTimeout=5)
tunel() { $SSH "${C[@]}" -N -o ExitOnForwardFailure=yes $1 root@127.0.0.1 2>$P/cli.err & local p=$!; sleep 1.2; eval "$2"; kill $p 2>/dev/null; wait $p 2>/dev/null; }
pedir() { python3 -I -c 'import socket,sys
s=socket.create_connection(("127.0.0.1",int(sys.argv[1])),3); s.settimeout(3); s.sendall(b"GET / HTTP/1.0\r\n\r\n")
d=b""
try:
    while True:
        x=s.recv(4096)
        if not x: break
        d+=x
except Exception: pass
print(d.decode(errors="replace").splitlines()[-1] if d else "NADA")' $1 2>/dev/null || echo NADA; }
echo "=== L8765"; tunel "-L 127.0.0.1:18765:127.0.0.1:8765" "pedir 18765"
echo "=== L9000"; tunel "-L 127.0.0.1:18765:127.0.0.1:9000" "pedir 18765"
echo "=== Llocalhost"; tunel "-L 127.0.0.1:18765:localhost:8765" "pedir 18765"
echo "=== Lunix"; tunel "-L 127.0.0.1:18766:$T/docker.sock" "pedir 18766"
echo "=== Rtcp"; timeout 5 $SSH "${C[@]}" -N -o ExitOnForwardFailure=yes -R 127.0.0.1:19000:127.0.0.1:8765 root@127.0.0.1 2>&1 | head -2
echo "=== Runix"; $SSH "${C[@]}" -N -o ExitOnForwardFailure=yes -R $T/plantado.sock:127.0.0.1:8765 root@127.0.0.1 2>/dev/null & p=$!; sleep 1.5; [ -S $T/plantado.sock ] && echo "SOCKET CREADO" || echo "sin socket"; kill $p 2>/dev/null; wait $p 2>/dev/null
echo "=== orden"; timeout 5 $SSH "${C[@]}" root@127.0.0.1 'echo EJECUTADO' 2>&1 | head -2
echo "=== sftp"; timeout 5 $SFTP -S $SSH -F /dev/null -P 2223 -i $T/mac -o IdentitiesOnly=yes -o UserKnownHostsFile=$T/kh -o BatchMode=yes root@127.0.0.1 <<<'ls' 2>&1 | head -2
echo "=== contrasena"; timeout 5 $SSH -F /dev/null -p 2223 -o UserKnownHostsFile=$T/kh -o PreferredAuthentications=password,keyboard-interactive -o PubkeyAuthentication=no -o BatchMode=yes root@127.0.0.1 true 2>&1 | head -1
echo "=== otra"; timeout 5 $SSH -F /dev/null -p 2223 -i $T/otra -o IdentitiesOnly=yes -o UserKnownHostsFile=$T/kh -o BatchMode=yes -N root@127.0.0.1 2>&1 | head -1
echo "=== otra-ip"; sed -i 's#from="127.0.0.1"#from="192.0.2.1"#' $T/bms_tunel_authorized_keys; timeout 5 $SSH "${C[@]}" -N root@127.0.0.1 2>&1 | head -1
kill $SSHD_PID 2>/dev/null; wait $SSHD_PID 2>/dev/null
echo "=== strictmodes"
sed -i 's#from="192.0.2.1"#from="127.0.0.1"#' $T/bms_tunel_authorized_keys
mkdir -p $T/comun/prueba && chmod 1777 $T/comun && chmod 700 $T/comun/prueba
cp $T/bms_tunel_authorized_keys $T/comun/prueba/
sed -e "s#AuthorizedKeysFile $T/bms_tunel_authorized_keys#AuthorizedKeysFile $T/comun/prueba/bms_tunel_authorized_keys#" $T/sshd_config > $T/sshd_config2
$SSHD -D -e -f $T/sshd_config2 2>$P/sshd2.log & SSHD_PID=$!; sleep 1.2
timeout 5 $SSH "${C[@]}" -N root@127.0.0.1 2>&1 | head -1
kill $SSHD_PID $SRV 2>/dev/null; wait 2>/dev/null
grep -E 'bad ownership or modes' $P/sshd2.log | head -1
echo "=== registro"; grep -E 'denied|refused|prohibit|no more sessions|not allowed|Accepted' $P/sshd.log | head -30
"""

SERVIDORES = r"""
import socket, sys, threading, os
def tcp(puerto, texto):
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", puerto)); s.listen(16)
    while True:
        c, _ = s.accept()
        try:
            c.recv(4096); c.sendall(b"HTTP/1.0 200 OK\r\n\r\n" + texto)
        finally:
            c.close()
def unix(ruta, texto):
    s = socket.socket(socket.AF_UNIX); s.bind(ruta); s.listen(16)
    while True:
        c, _ = s.accept()
        try:
            c.recv(4096); c.sendall(b"HTTP/1.0 200 OK\r\n\r\n" + texto)
        finally:
            c.close()
threading.Thread(target=tcp, args=(8765, b"APP-8765"), daemon=True).start()
threading.Thread(target=tcp, args=(9000, b"OTRO-9000"), daemon=True).start()
threading.Thread(target=unix, args=(sys.argv[1], b"SOCKET-UNIX"), daemon=True).start()
threading.Event().wait()
"""


def _openssh() -> Path | None:
    raiz = os.environ.get("BMS_OPENSSH")
    if not raiz:
        return None
    raiz = Path(raiz)
    if not (raiz / "usr" / "sbin" / "sshd").exists() or not (raiz / "usr" / "bin" / "ssh").exists():
        return None
    return raiz


def test_sshd_de_verdad(puras, tmp_path) -> None:
    """mac.md §5.1, test_sshd_de_verdad: el sshd_config y el fichero de claves que genera mac.ps1
    pasan sshd -t; sshd -T da lo de §2.3 para la cuenta del tunel y deja cerrada otra; el -L al
    8765 funciona y lo demas (otro puerto, localhost, un socket Unix, -D, -R, una orden, sftp,
    contrasena, otra clave, otra IP) no; y StrictModes rechaza las claves bajo una carpeta 1777."""
    raiz = _openssh()
    if raiz is None:
        pytest.skip("sin BMS_OPENSSH (la raiz de un OpenSSH sacado de sus .deb)")
    if os.geteuid() != 0 or shutil.which("unshare") is None:
        pytest.skip("hace falta ser root y unshare (un espacio de montaje propio)")
    if any(_puerto_ocupado(p) for p in (2223, 8765, 9000, 18765, 18766)):
        pytest.skip("un puerto de la prueba esta en uso")
    (tmp_path / "sshd_config").write_text(puras["config1"], encoding="ascii")
    (tmp_path / "claves").write_text(puras["claves1"], encoding="ascii")
    (tmp_path / "servidores.py").write_text(SERVIDORES, encoding="ascii")
    (tmp_path / "dentro.sh").write_text(DENTRO, encoding="ascii")
    proceso = subprocess.run(["unshare", "-m", "bash", str(tmp_path / "dentro.sh"), str(raiz),
                              str(tmp_path)], capture_output=True, text=True, timeout=240)
    salida = proceso.stdout
    trozos = re.split(r"(?m)^=== (\S+)$", salida)
    partes = {trozos[i]: trozos[i + 1].strip("\n") for i in range(1, len(trozos) - 1, 2)}
    assert partes["F1"].strip() == "rc=0", salida + proceso.stderr
    tunel = dict(l.split(" ", 1) for l in partes["F2"].splitlines() if " " in l)
    for clave, valor in (("allowtcpforwarding", "local"), ("permitopen", "127.0.0.1:8765"),
                         ("permitlisten", "none"), ("permittty", "no"), ("maxsessions", "0"),
                         ("forcecommand", "exit 1"), ("passwordauthentication", "no"),
                         ("authenticationmethods", "publickey"), ("allowagentforwarding", "no"),
                         ("gatewayports", "no"), ("allowstreamlocalforwarding", "no"),
                         ("x11forwarding", "no"), ("permittunnel", "no"),
                         ("pubkeyacceptedalgorithms", "ssh-ed25519")):
        assert tunel.get(clave) == valor, (clave, tunel.get(clave))
    assert tunel["authorizedkeysfile"].endswith("/bms_tunel_authorized_keys")
    otra = dict(l.split(" ", 1) for l in partes["F3"].splitlines() if " " in l)
    assert (otra["allowtcpforwarding"], otra["permitopen"], otra["authorizedkeysfile"]) == (
        "no", "none", "none")
    assert partes["L8765"].strip() == "APP-8765"
    for caso in ("L9000", "Llocalhost", "Lunix"):
        assert "OTRO-9000" not in partes[caso] and "SOCKET-UNIX" not in partes[caso]
        assert "APP-8765" not in partes[caso], caso
    assert "remote port forwarding failed" in partes["Rtcp"]
    assert partes["Runix"].strip() == "sin socket"
    assert "EJECUTADO" not in partes["orden"] and "sftp>" not in partes["sftp"]
    assert "Permission denied" in partes["contrasena"]
    assert "Permission denied" in partes["otra"] and "Permission denied" in partes["otra-ip"]
    assert "Permission denied" in partes["strictmodes"]
    assert "bad ownership or modes for directory" in partes["strictmodes"]
    registro = partes["registro"]
    assert "administratively prohibited" in registro or "but the request was denied" in registro
    assert "refused streamlocal port forward" in registro


def _puerto_ocupado(puerto: int) -> bool:
    import socket

    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", puerto)) == 0
