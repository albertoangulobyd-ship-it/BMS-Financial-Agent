# Quita bms-agent de este ordenador, sin Docker (paso 14, docs/instalacion-nativa.md).
#
#   desinstalar.bat
#
# Quita el programa (runtime, lib, app, windows), sus reglas del cortafuegos (exactamente
# las que empiezan por "BMS Finanzas - ") y los accesos del escritorio. TUS DATOS SE QUEDAN
# (datos\ y buzon\) salvo que escribas SI, en mayusculas, cuando te lo pregunte. Haz antes una
# copia (copia.bat). Necesita permiso de administrador, como al instalar.
param(
    [string]$Raiz = "",
    [switch]$Elevado,
    [switch]$BorrarDatos
)

. "$PSScriptRoot\comun.ps1"

# Fuera de la carpeta de la instalacion: una ventana cuya carpeta actual es C:\BMS\windows no
# deja borrarla (desinstalar.bat tambien sale de ella antes de empezar).
Set-Location -LiteralPath $env:SystemRoot

if (-not $Elevado) {
    if ($Raiz) {
        $Inst = [pscustomobject]@{ Raiz = $Raiz.TrimEnd("\") }
    } else {
        $Inst = Buscar-Instalacion
    }
    $respuesta = Read-Host ("Se va a quitar bms-agent de " + $Inst.Raiz + ": el programa, sus reglas del cortafuegos y los accesos del escritorio. Seguir? (escribe si)")
    if (-not (Es-Si $respuesta)) {
        Escribir "No has escrito si: no se ha quitado nada." "Yellow"
        exit 0
    }
    Escribir ("Tus datos (la base, los originales, la clave cifrada y el buzon) se quedan en " + $Inst.Raiz + "\datos y \buzon.") "Yellow"
    $borrar = Read-Host "Para borrarlos tambien, escribe SI en mayusculas (haz antes una copia con copia.bat). Cualquier otra cosa los deja"
    $borrarDatos = ($borrar -ceq "SI")
    # La parte de administrador corre este mismo script, en su sitio: windows\ es de los
    # administradores y tu usuario no lo puede cambiar. Una copia en %TEMP%, que tu usuario si
    # puede cambiar, la podria cambiar cualquier programa tuyo antes de que digas que si a la
    # ventana de permiso. Que la carpeta se borre mientras corre da igual: PowerShell lee el
    # script entero (y comun.ps1) antes de empezar.
    $lista = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath,
        "-Raiz", $Inst.Raiz, "-Elevado")
    if ($borrarDatos) { $lista += "-BorrarDatos" }
    try {
        $proceso = Start-Process -FilePath (Get-Process -Id $PID).Path -ArgumentList (Linea-De-Argumentos $lista) `
            -Verb RunAs -Wait -PassThru
    } catch {
        Fallar "Sin permiso de administrador no se pueden quitar las reglas del cortafuegos: no se ha quitado nada."
    }
    $escritorio = [Environment]::GetFolderPath("Desktop")
    Get-ChildItem -File -LiteralPath $escritorio -Filter ($Prefijo + "*.lnk") -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
    if ($proceso.ExitCode -ne 0) { Fallar "No se ha podido quitar todo. Mira la otra ventana." }
    if ($borrarDatos -and (Test-Path -LiteralPath $Inst.Raiz)) {
        Escribir ("Quitado, tambien tus datos, pero queda la carpeta " + $Inst.Raiz + " (algo la tenia abierta): borrala a mano.") "Yellow"
    } elseif ($borrarDatos) {
        Escribir "Quitado, tambien tus datos." "Green"
    } else {
        Escribir ("Quitado. Tus datos siguen en " + $Inst.Raiz + "\datos y \buzon; para volver a usarlos, instalar.bat en la misma carpeta.") "Green"
    }
    exit 0
}

if (-not (Es-Administrador)) {
    Write-Host "Esta parte necesita permiso de administrador." -ForegroundColor Red
    exit 1
}
$Inst = [pscustomobject]@{ Raiz = $Raiz }
foreach ($rol in $Roles) { Parar-Rol $rol }
Quitar-Reglas
$quedan = @(Get-NetFirewallRule -DisplayName ($Prefijo + "*") -ErrorAction SilentlyContinue)
foreach ($carpeta in @("runtime", "lib", "app", "windows", "descargas")) {
    Remove-Item -Recurse -Force -LiteralPath (Join-Path $Raiz $carpeta) -ErrorAction SilentlyContinue
}
foreach ($fichero in @("instalacion.json", "instalacion.log")) {
    Remove-Item -Force -LiteralPath (Join-Path $Raiz $fichero) -ErrorAction SilentlyContinue
}
if ($BorrarDatos) {
    foreach ($carpeta in @("datos", "buzon")) {
        Remove-Item -Recurse -Force -LiteralPath (Join-Path $Raiz $carpeta) -ErrorAction SilentlyContinue
    }
}
if (@(Get-ChildItem -Force -LiteralPath $Raiz -ErrorAction SilentlyContinue).Count -eq 0) {
    Remove-Item -Force -LiteralPath $Raiz -ErrorAction SilentlyContinue
}
if ($quedan.Count -gt 0) {
    Write-Host "No se han podido quitar todas las reglas del cortafuegos." -ForegroundColor Red
    Read-Host "Pulsa Intro para cerrar esta ventana"
    exit 1
}
Write-Host "Hecho." -ForegroundColor Green
Start-Sleep -Seconds 2
exit 0
