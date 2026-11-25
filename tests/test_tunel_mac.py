"""El Mac por el mini PC (paso 18b, docs/v1/paso-18/mac.md), solo en la variante Docker.

Lo que se puede probar aqui, en Linux, sin Windows ni macOS (mac.md §5.1): los pines de
docker/proteger.ps1 (la carpeta del proyecto protegida), y que lo que protege casa con lo que de
verdad escriben los scripts del ciclo automatico (paso 15). Lo que solo se ve en un Windows 11 o
en un Mac de verdad esta en la lista de mac.md §5.2.

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
ADMINISTRADOR = ("proteger",)

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
                         r"Set-ExecutionPolicy|Invoke-WebRequest|Invoke-RestMethod|-OutFile|"
                         r"Add-Type|ServerCertificateValidationCallback",
                         codigo, re.IGNORECASE)
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
        assert not re.search(rf"\b{grupo}\b", codigo), grupo
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
        '"/setowner", $administradores, "/T", "/C"',
        '"/inheritance:r", "/grant:r"',
        '"/remove:g"',
        '"/reset", "/T", "/C"',
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
    assert llamadas[0] == [p, "/setowner", "*S-1-5-32-544", "/T", "/C", "/Q"]
    assert llamadas[1] == [p, "/inheritance:r", "/grant:r", "*S-1-5-18:(OI)(CI)F",
                           "*S-1-5-32-544:(OI)(CI)F", f"*{DUENO}:(OI)(CI)M", f"*{BMS}:(OI)(CI)RX",
                           "/Q"]
    # Lo de dentro (tambien el buzon, que se crea vacio) hereda solo eso.
    hijos = sorted(Path(l[0]).name for l in llamadas if l[1:2] == ["/reset"])
    assert hijos == ["buzon", "docker", "src"]
    assert all(l[1:] == ["/reset", "/T", "/C", "/Q"] for l in llamadas if l[1:2] == ["/reset"])
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
