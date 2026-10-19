# Lo que comparten los scripts del entorno local (paso 13, docs/entorno-local.md).
# No se ejecuta solo: lo cargan iniciar.ps1, parar.ps1, importar.ps1 y los demas.

# "Continue" y no "Stop": en Windows PowerShell 5.1, lo que Docker escribe en la salida de
# errores (su progreso, por ejemplo) contaria como un error y cortaria el script. Cada
# orden de Docker se comprueba por su codigo de salida ($LASTEXITCODE).
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot

function Escribir([string]$Texto, [string]$Color = "Gray") {
    Write-Host $Texto -ForegroundColor $Color
}

function Fallar([string]$Texto) {
    Write-Host ""
    Write-Host $Texto -ForegroundColor Red
    Write-Host ""
    exit 1
}

function Comprobar-Docker {
    $null = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $?) {
        Fallar "No encuentro Docker. Instala Docker Desktop (docs/entorno-local.md, paso 1) y vuelve a probar."
    }
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Fallar "Docker Desktop no esta en marcha. Abrelo desde el menu Inicio, espera a que la ballena deje de moverse y vuelve a probar."
    }
}

function Elegir-Base([switch]$Demo) {
    # La consola, el lector y las ordenes usan la base que diga BMS_BASE (docker-compose.yml).
    if ($Demo) { $env:BMS_BASE = "demo" } else { $env:BMS_BASE = "bms" }
}

function Asegurar-Imagen {
    docker image inspect bms-agent:local *> $null
    if ($LASTEXITCODE -ne 0) {
        Escribir "Preparando el programa por primera vez (unos minutos; solo pasa una vez)..." "Cyan"
        docker compose build consola | Out-Host
        if ($LASTEXITCODE -ne 0) { Fallar "No se ha podido preparar el programa. Mira el mensaje de arriba." }
    }
}

function Direccion-De-La-App([string]$Base) {
    # Paso 15: la app (/app) si esta construida. Si no contesta 200 (serve da 503 cuando falta
    # lo construido o esta incompleto), se dice y se abre la consola de antes (/consola), que
    # no depende de ello: es la reserva.
    try {
        $respuesta = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri ($Base + "/app")
        if ($respuesta.StatusCode -eq 200) { return ($Base + "/app") }
    } catch { }
    Escribir "La app no se puede abrir (falta lo construido o esta incompleto). Se abre la consola de antes; avisa a quien mantiene el programa." "Yellow"
    return ($Base + "/consola")
}

function Abrir-App([string]$Direccion) {
    # Paso 15: la app se abre en su propia ventana de Edge (--app: sin pestanas ni barra de
    # direcciones), como un programa. Si Edge no esta, en el navegador de siempre; si
    # tampoco se puede, se dice la direccion. /consola sigue ahi, de reserva.
    $edge = $null
    foreach ($base in @(${env:ProgramFiles(x86)}, $env:ProgramFiles, $env:LOCALAPPDATA)) {
        if (-not $base) { continue }
        $candidato = Join-Path $base "Microsoft\Edge\Application\msedge.exe"
        if (Test-Path -LiteralPath $candidato) { $edge = $candidato; break }
    }
    try {
        if ($edge) {
            Start-Process -FilePath $edge -ArgumentList @("--app=" + $Direccion)
        } else {
            Start-Process $Direccion
        }
    } catch {
        try { Start-Process $Direccion } catch { Escribir "Abre esa direccion en el navegador." "Yellow" }
    }
}

function Pedir-Token {
    if ($env:BMS_TOKEN) { return }
    $seguro = Read-Host "Tu token personal (no se ve al escribirlo)" -AsSecureString
    $puntero = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro)
    try {
        $env:BMS_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($puntero)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($puntero)
    }
}

function Es-Si([string]$Respuesta) {
    # "si", "si con tilde" o "s", en mayusculas o no. La tilde se compara por su codigo: un .ps1 sin
    # BOM se lee como ANSI en Windows PowerShell 5.1, y aqui solo va ASCII.
    $texto = ("" + $Respuesta).Trim().ToLower().Replace([string][char]0x00ED, "i")
    return ($texto -eq "si" -or $texto -eq "s")
}

function Olvidar-Token {
    Remove-Item Env:\BMS_TOKEN -ErrorAction SilentlyContinue
}

function Orden([string[]]$Argumentos) {
    # Una orden suelta en el contenedor "orden", que no tiene red ninguna. El token, si
    # hay, pasa por el entorno (-e BMS_TOKEN sin valor): nunca en la linea de la orden.
    # Out-Host: lo que dice la orden se ve, y no se mezcla con lo que devuelve la funcion.
    docker compose run --rm -T -e BMS_TOKEN orden @Argumentos | Out-Host
    return $LASTEXITCODE
}
