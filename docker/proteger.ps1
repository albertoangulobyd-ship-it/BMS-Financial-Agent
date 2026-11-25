# La carpeta del proyecto, protegida (paso 18b, docs/entorno-local.md "El usuario de lo
# automatico"). Con Docker y el usuario aparte de lo automatico ("bms"): solo los
# administradores y tu cuenta pueden cambiarla; "bms" la lee y solo escribe en docker\estado y
# docker\secretos\correo. Asi "bms" no puede cambiar los scripts que abres tu (persona.bat,
# mac.bat...) ni lo que se copia al Mac, y ninguna otra cuenta del equipo lee los secretos ni
# las facturas.
#
#   .\proteger.bat -Usuario bms   una vez al poner la carpeta, y otra cada vez que pongas una
#                                 version nueva (antes de iniciar.bat)
#
# Windows PowerShell 5.1, ASCII. No carga comun.ps1 (corre como administrador). No usa Docker.
param(
    [string]$Usuario = "",
    [switch]$Elevado,
    [string]$Dueno = ""
)

$ErrorActionPreference = "Continue"
$SidSistema = "S-1-5-18"
$SidAdministradores = "S-1-5-32-544"
$Icacls = Join-Path $env:SystemRoot "System32\icacls.exe"
# Las carpetas en las que escribe "bms" (docs/v1/paso-18/diseno.md 4.1, 4.4 y 2.4): la pausa, el
# cerrojo, ciclo.json y los registros del ciclo; el certificado del correo que escribe la orden
# montada. tests/test_tunel_mac.py lo compara con lo que escriben los scripts de docker\.
$EscribeBms = @("docker\estado", "docker\secretos\correo")
# Lo que el Docker de "bms" monta y no puede crear el (solo lee la raiz): el buzon de facturas
# (docker-compose.yml, ../buzon:/buzon:ro). Si falta, se crea aqui, vacio.
$MontaBms = @("buzon")

function Escribir([string]$Texto, [string]$Color = "Gray") {
    Write-Host $Texto -ForegroundColor $Color
}

function Esperar-Intro {
    if ($Elevado) { Read-Host "Pulsa Intro para cerrar esta ventana" | Out-Null }
}

function Fallar([string]$Texto) {
    Write-Host ""
    Write-Host $Texto -ForegroundColor Red
    Write-Host ""
    Esperar-Intro
    exit 1
}

function Es-Si([string]$Respuesta) {
    # "si", "si con tilde" o "s", en mayusculas o no. La tilde se compara por su codigo.
    $texto = ("" + $Respuesta).Trim().ToLower().Replace([string][char]0x00ED, "i")
    return ($texto -eq "si" -or $texto -eq "s")
}

function Es-Administrador {
    $yo = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    return $yo.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Cambiar-Permisos([string[]]$Argumentos) {
    & $Icacls @Argumentos | Out-Null
    if ($LASTEXITCODE -ne 0) { Fallar ("No se han podido poner los permisos (icacls " + ($Argumentos -join " ") + ").") }
}

function Grupos-De-La-Cuenta([string]$Nombre) {
    # Igual que en mac.ps1: por ADSI y por SID; si no se puede mirar, lanza.
    $u = [ADSI]("WinNT://" + $env:COMPUTERNAME + "/" + $Nombre + ",user")
    $sids = @()
    foreach ($g in @($u.psbase.Invoke("Groups"))) {
        $bytes = $g.GetType().InvokeMember("objectSid", "GetProperty", $null, $g, $null)
        $sids += (New-Object Security.Principal.SecurityIdentifier($bytes, 0)).Value
    }
    return $sids
}

function Dentro-De([string]$Ruta, [string]$Carpeta) {
    # La ruta es esa carpeta o esta dentro de ella (sin confundir C:\Programas con C:\Program).
    if (-not $Carpeta) { return $false }
    $barra = [string][IO.Path]::DirectorySeparatorChar
    $c = $Carpeta.TrimEnd($barra) + $barra
    return (($Ruta.TrimEnd($barra) + $barra).StartsWith($c, [StringComparison]::OrdinalIgnoreCase))
}

function Enlace-Dentro([string]$Raiz) {
    # El primer enlace (punto de reanalisis: un enlace simbolico o una union) de la carpeta o de
    # cualquier cosa de dentro, sin entrar en ninguno; $null si no hay. icacls /T entraria en el
    # sitio al que apunta: se pondrian permisos (y "bms" podria escribir) fuera del proyecto.
    $inicio = Get-Item -Force -LiteralPath $Raiz
    if ($inicio.Attributes -band [IO.FileAttributes]::ReparsePoint) { return $inicio.FullName }
    $pendientes = New-Object System.Collections.Stack
    $pendientes.Push($inicio.FullName)
    while ($pendientes.Count -gt 0) {
        $carpeta = $pendientes.Pop()
        foreach ($c in @(Get-ChildItem -Force -LiteralPath $carpeta -ErrorAction Stop)) {
            if ($c.Attributes -band [IO.FileAttributes]::ReparsePoint) { return $c.FullName }
            if ($c.PSIsContainer) { $pendientes.Push($c.FullName) }
        }
    }
    return $null
}

function Carpeta-De-Perfiles {
    # C:\Users (donde Windows pone la carpeta de cada cuenta).
    try {
        $clave = Get-ItemProperty -LiteralPath "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList" -Name ProfilesDirectory -ErrorAction Stop
        return [Environment]::ExpandEnvironmentVariables("" + $clave.ProfilesDirectory)
    } catch {
        if ($env:USERPROFILE) { return (Split-Path -Parent $env:USERPROFILE) }
        return $null
    }
}

if ([Environment]::Is64BitOperatingSystem -and -not [Environment]::Is64BitProcess) {
    Fallar "Abre proteger.bat con doble clic o desde una ventana normal (no desde un programa de 32 bits)."
}
$Proyecto = Split-Path -Parent $PSScriptRoot
foreach ($prohibida in @($env:SystemRoot, $env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:ProgramData)) {
    if (Dentro-De $Proyecto $prohibida) {
        Fallar ("La carpeta del proyecto no puede estar en " + $prohibida + ": ponla, por ejemplo, en C:\bms-agent.")
    }
}
if ([IO.Path]::GetPathRoot($Proyecto) -eq $Proyecto) { Fallar "La carpeta del proyecto no puede ser la raiz de un disco." }
$perfiles = Carpeta-De-Perfiles
if (Dentro-De $Proyecto $perfiles) {
    # En la carpeta de una cuenta: "bms" no llega a la del dueno, y la suya la podria cambiar
    # entera (es la duena de las carpetas de arriba).
    Fallar ("Con el usuario de lo automatico, la carpeta del proyecto no puede estar en " + $perfiles + ": ponla, por ejemplo, en C:\bms-agent.")
}
try { $enlace = Enlace-Dentro $Proyecto } catch { Fallar ("No se ha podido mirar lo que hay en " + $Proyecto + ".") }
if ($enlace) { Fallar ($enlace + " es un enlace a otro sitio: quitalo y vuelve a probar.") }
if (-not $Usuario) { Fallar "Di el usuario de lo automatico: proteger.bat -Usuario bms" }
$cuenta = Get-LocalUser -Name $Usuario -ErrorAction SilentlyContinue
if (-not $cuenta -and $Usuario -match '^S-1-5-21-\d+-\d+-\d+-\d+$') {
    $cuenta = Get-LocalUser -SID $Usuario -ErrorAction SilentlyContinue
}
if (-not $cuenta) { Fallar ("No hay ningun usuario local " + $Usuario + " en este equipo.") }
$sidBms = $cuenta.SID.Value
if (-not $Dueno) { $Dueno = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value }
if ($Dueno -notmatch '^S-1-5-21-\d+-\d+-\d+-\d+$') { Fallar "Uso interno: -Dueno no es un SID de una cuenta." }
if ($sidBms -eq $Dueno) { Fallar ("El usuario de lo automatico tiene que ser otro, no tu cuenta (" + $cuenta.Name + ").") }
try { $grupos = @(Grupos-De-La-Cuenta $cuenta.Name) } catch { Fallar ("No se han podido mirar los grupos de " + $cuenta.Name + ".") }
if ($grupos -contains $SidAdministradores) { Fallar ($cuenta.Name + " es administrador: el usuario de lo automatico tiene que ser un usuario estandar.") }

if (-not $Elevado) {
    Escribir ("La carpeta " + $Proyecto + ":") "Cyan"
    Escribir ("   podran cambiarla los administradores y tu; " + $cuenta.Name + " solo leerla, y escribir en " + ($EscribeBms -join " y ") + ".")
    Escribir "   Nadie mas del equipo podra leerla (ni los secretos, ni el buzon)."
    Escribir "Hazlo justo despues de poner la carpeta (la primera vez o con una version nueva), antes de" "Yellow"
    Escribir ("que " + $cuenta.Name + " arranque nada con ella.") "Yellow"
    if (-not (Es-Si (Read-Host "Seguir? (escribe si)"))) { Fallar "No se ha cambiado nada." }
    if (-not (Es-Administrador)) {
        $argumentos = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ('"' + $PSCommandPath + '"'),
            "-Usuario", $sidBms, "-Dueno", $Dueno, "-Elevado")
        try {
            $p = Start-Process -FilePath (Get-Process -Id $PID).Path -ArgumentList $argumentos -Verb RunAs -Wait -PassThru
        } catch {
            Fallar "Sin permiso de administrador no se puede. Vuelve a abrir proteger.bat y di que si."
        }
        exit $p.ExitCode
    }
}

$sistema = "*" + $SidSistema
$administradores = "*" + $SidAdministradores
# 0. Lo que el Docker de "bms" monta, que no podria crear el.
foreach ($r in $MontaBms) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Proyecto $r) -ErrorAction SilentlyContinue | Out-Null
}
# 1. Todo, de los administradores: ni "bms" ni nadie puede cambiar los permisos. Con /L, icacls
#    trata un enlace que aparezca ahora (despues de mirar) como el enlace, sin entrar en el sitio
#    al que apunta.
Cambiar-Permisos @($Proyecto, "/setowner", $administradores, "/T", "/C", "/L", "/Q")
# 2. La raiz: sin la herencia de C:\ (que deja a cualquier usuario cambiar y leer).
Cambiar-Permisos @($Proyecto, "/inheritance:r", "/grant:r", ($sistema + ":(OI)(CI)F"), ($administradores + ":(OI)(CI)F"),
    ("*" + $Dueno + ":(OI)(CI)M"), ("*" + $sidBms + ":(OI)(CI)RX"), "/Q")
$nuestros = @($SidSistema, $SidAdministradores, $Dueno, $sidBms)
foreach ($regla in @((Get-Acl -LiteralPath $Proyecto).Access | Where-Object { -not $_.IsInherited -and "$($_.AccessControlType)" -eq "Allow" })) {
    $quien = $regla.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
    if ($nuestros -notcontains $quien) { Cambiar-Permisos @($Proyecto, "/remove:g", ("*" + $quien), "/Q") }
}
# 3. Lo de dentro hereda solo eso.
foreach ($hijo in @(Get-ChildItem -Force -LiteralPath $Proyecto)) {
    Cambiar-Permisos @($hijo.FullName, "/reset", "/T", "/C", "/L", "/Q")
}
# 4. Donde escribe "bms".
foreach ($r in $EscribeBms) {
    $ruta = Join-Path $Proyecto $r
    New-Item -ItemType Directory -Force -Path $ruta | Out-Null
    Cambiar-Permisos @($ruta, "/grant", ("*" + $sidBms + ":(OI)(CI)M"), "/Q")
}
# 5. Comprobarlo: en la raiz, solo esos cuatro.
$quedan = @((Get-Acl -LiteralPath $Proyecto).Access | Where-Object { "$($_.AccessControlType)" -eq "Allow" } |
    ForEach-Object { $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value } |
    Where-Object { $nuestros -notcontains $_ })
if ($quedan.Count -gt 0) { Fallar ("La carpeta tiene permisos de " + ($quedan -join ", ") + " que no se pueden quitar.") }
Escribir ("Listo: " + $Proyecto + " es de los administradores; tu la cambias, " + $cuenta.Name + " la lee y escribe solo en " + ($EscribeBms -join " y ") + ".") "Green"
Esperar-Intro
