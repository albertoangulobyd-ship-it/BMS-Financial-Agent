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
    if (-not (Imagen-Lista)) {
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

# Paso 17: como acaban las ordenes "lectura" del lector (los mismos numeros que
# cli.LECTURA_NADA y los demas; los tests exigen que sean iguales).
$LecturaNada = 3
$LecturaOcupada = 4
$LecturaCancelada = 5
$LecturaCaducada = 6
$LecturaFallida = 7
# Paso 18: lo que dice "lectura siguiente" al ciclo automatico (0: una lectura
# automatica): la que pidio una persona en la app, o la automatica parada.
$LecturaPedida = 8
$LecturaLimite = 9

function Cerrar-Lectura([string]$Solicitud, [string]$Motivo, [switch]$SiViva) {
    # La lectura que no se ha podido hacer termina fallida, con su motivo, y la app lo ve. Lo
    # escribe el contenedor de las ordenes, sin red. Con -SiViva (el final del script), solo
    # si el lector la dejo a medias. Lo que dice, en pantalla (y en el registro del ciclo).
    $argumentos = @("lectura", "cerrar", $Solicitud, "--motivo", $Motivo)
    if ($SiViva) { $argumentos += "--si-viva" }
    docker compose run --rm -T orden @argumentos 2>&1 | ForEach-Object { Anotar ("" + $_) }
}

function Orden([string[]]$Argumentos) {
    # Una orden suelta en el contenedor "orden", que no tiene red ninguna. El token, si
    # hay, pasa por el entorno (-e BMS_TOKEN sin valor): nunca en la linea de la orden.
    # Out-Host: lo que dice la orden se ve, y no se mezcla con lo que devuelve la funcion.
    docker compose run --rm -T -e BMS_TOKEN orden @Argumentos | Out-Host
    return $LASTEXITCODE
}

# ======================================================================= paso 18: funcionar solo
#
# El ciclo automatico (ciclo.ps1 -Bucle, que arranca la tarea de automatico.ps1), la pausa y
# el cerrojo (diseno del paso 18, secciones 4.1 y 4.4). Todo lo que escriben, en docker\estado
# (fuera de git); lo del correo, en docker\secretos\correo. Nada mas.

# Como acaban "correo traer" y "correo comprobar" (los mismos numeros que
# cli.CORREO_SIN_CONFIGURAR y cli.CORREO_FALLO; los tests exigen que sean iguales).
$CorreoSinConfigurar = 10
$CorreoFallo = 11

$CarpetaEstado = Join-Path $PSScriptRoot "estado"
$FicheroPausa = Join-Path $PSScriptRoot "estado\automatico.pausa"
$FicheroCerrojo = Join-Path $PSScriptRoot "estado\ciclo.cerrojo"
$FicheroCiclo = Join-Path $PSScriptRoot "estado\ciclo.json"
$CarpetaRegistroCiclo = Join-Path $PSScriptRoot "estado\registro"
$CarpetaSecretosCorreo = Join-Path $PSScriptRoot "secretos\correo"
$FicheroAjustesCorreo = Join-Path $PSScriptRoot "secretos\correo\correo_ajustes.json"
$FicheroCertificadoCorreo = Join-Path $PSScriptRoot "secretos\correo\correo_certificado.pem"
$FicheroClaveApi = Join-Path $PSScriptRoot "secretos\anthropic_api_key.txt"
# Las tareas de automatico.ps1, en la carpeta raiz del Programador de tareas (una cuenta sin
# permisos de administrador puede crear ahi las suyas).
$TareaCiclo = "BMS Finanzas - ciclo (Docker)"
$TareaBloquear = "BMS Finanzas - bloquear (Docker)"
# Con menos libre no se trae ni se lee nada (ciclo.DISCO_MINIMO, 10 GiB).
$DiscoMinimo = 10GB
# Lo que corre el contenedor del correo (su "command" de docker-compose.yml) y su
# comprobacion: los dos secretos de Docker y sus dos volumenes, nunca la carpeta de secretos.
$OrdenTraer = @("correo", "traer", "--ajustes", "/run/secrets/correo_ajustes", "--certificado-fichero", "/run/secrets/correo_certificado", "--estado", "/correo/estado", "--entrada", "/correo/entrada")
$OrdenComprobar = @("correo", "comprobar", "--ajustes", "/run/secrets/correo_ajustes", "--certificado-fichero", "/run/secrets/correo_certificado", "--estado", "/correo/estado")

$RegistroCiclo = $null
$Cerrojo = $null
$PausaYaEstaba = $false

function Anotar([string]$Texto, [string]$Color = "Gray") {
    # En pantalla y, en el ciclo, tambien en su registro del dia (docker\estado\registro).
    Write-Host $Texto -ForegroundColor $Color
    if ($script:RegistroCiclo) {
        try {
            $hora = (Get-Date).ToString("HH:mm:ss", [Globalization.CultureInfo]::InvariantCulture)
            Add-Content -LiteralPath $script:RegistroCiclo -Value ($hora + " " + $Texto) -Encoding UTF8 -ErrorAction Stop
        } catch { }
    }
}

function Compose-Anotado([string[]]$Argumentos) {
    # docker compose con lo que dice (las dos salidas) en pantalla y en el registro del ciclo.
    # Devuelve su codigo y las lineas de su salida normal (el numero que da "lectura tomar").
    $normal = @()
    docker compose @Argumentos 2>&1 | ForEach-Object {
        $linea = "" + $_
        if (-not ($_ -is [System.Management.Automation.ErrorRecord])) { $normal += $linea }
        Anotar $linea
    }
    $codigo = $LASTEXITCODE
    return [pscustomobject]@{ Codigo = $codigo; Lineas = $normal }
}

function Docker-Listo([int]$Segundos = 0) {
    # Si Docker contesta, esperando como mucho estos segundos (Docker Desktop puede tardar en
    # arrancar en frio). Nunca sale del script: el ciclo no puede pararse por esto.
    $hasta = (Get-Date).AddSeconds($Segundos)
    while ($true) {
        if (Get-Command docker -ErrorAction SilentlyContinue) {
            docker info *> $null
            if ($LASTEXITCODE -eq 0) { return $true }
        }
        if ((Get-Date) -ge $hasta) { return $false }
        Start-Sleep -Seconds 10
    }
}

function Imagen-Lista {
    docker image inspect bms-agent:local *> $null
    return ($LASTEXITCODE -eq 0)
}

function Tomar-Cerrojo([int]$Esperar = 0, [string]$Aviso = "") {
    # Una sola cosa a la vez: el ciclo, una lectura a mano, una copia, iniciar, restaurar o el
    # certificado del correo. El cerrojo es docker\estado\ciclo.cerrojo abierto en exclusiva
    # mientras dura; si el proceso muere, Windows lo suelta. Sin esperar (el ciclo) o esperando
    # como mucho estos segundos. Devuelve si se tiene.
    if ($null -ne $script:Cerrojo) { return $true }
    try {
        New-Item -ItemType Directory -Force -Path $CarpetaEstado -ErrorAction Stop | Out-Null
    } catch {
        Anotar ("No se puede usar " + $CarpetaEstado + ": " + $_.Exception.Message) "Red"
        return $false
    }
    $hasta = (Get-Date).AddSeconds($Esperar)
    $avisado = $false
    while ($true) {
        try {
            $script:Cerrojo = [System.IO.File]::Open($FicheroCerrojo, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
            return $true
        } catch [System.UnauthorizedAccessException] {
            Anotar ("Esta cuenta no puede abrir " + $FicheroCerrojo + " (permisos).") "Red"
            return $false
        } catch {
            # Lo tiene otro: se espera, si se puede.
        }
        if ((Get-Date) -ge $hasta) { return $false }
        if ($Aviso -and -not $avisado) {
            Escribir $Aviso "Yellow"
            $avisado = $true
        }
        Start-Sleep -Seconds 2
    }
}

function Soltar-Cerrojo {
    if ($null -ne $script:Cerrojo) {
        try { $script:Cerrojo.Dispose() } catch { }
        $script:Cerrojo = $null
    }
}

function En-Pausa {
    return (Test-Path -LiteralPath $FicheroPausa)
}

function Tarea-Del-Ciclo {
    # La tarea del ciclo, si esta cuenta la ve ($null si no esta o no se ve).
    if (-not (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue)) { return $null }
    return (Get-ScheduledTask -TaskName $TareaCiclo -TaskPath "\" -ErrorAction SilentlyContinue)
}

function Automatizacion-Puesta {
    # La tarea esta (si esta cuenta la ve) o el ciclo ya ha corrido alguna vez aqui.
    return (($null -ne (Tarea-Del-Ciclo)) -or (Test-Path -LiteralPath $FicheroCiclo))
}

function Pausar-Automatico([string]$Quien, [switch]$SoloSiSigue) {
    # Antes de parar, actualizar, restaurar o activar un certificado: el ciclo y el vigilante no
    # arrancan nada mientras exista docker\estado\automatico.pausa. Despues toma el cerrojo,
    # esperando como mucho 2 minutos a lo que este en marcha. Devuelve verdadero con el cerrojo
    # en la mano; falso si no se pudo (y quien llamo no toca nada). Con el cerrojo, la pausa se
    # queda puesta: se quita con Reanudar-Automatico (iniciar.bat, automatico.bat -Reanudar).
    # Sin el, se queda (parar.bat, automatico.bat -Pausar: no empieza nada nuevo), salvo con
    # -SoloSiSigue (restaurar.bat, correo-certificado.bat -Activar, que se vuelven a abrir mas
    # tarde): entonces se quita la pausa que puso esta llamada, y todo sigue como estaba. Si no,
    # la vez siguiente la encontraria puesta y no la quitaria al acabar (-SiLaPuseYo).
    $script:PausaYaEstaba = Test-Path -LiteralPath $FicheroPausa
    if (-not $script:PausaYaEstaba) {
        try {
            New-Item -ItemType Directory -Force -Path $CarpetaEstado -ErrorAction Stop | Out-Null
            $cuando = (Get-Date).ToString("yyyy-MM-dd HH:mm", [Globalization.CultureInfo]::InvariantCulture)
            Set-Content -LiteralPath $FicheroPausa -Value ("En pausa desde " + $cuando + " (" + $Quien + ").") -Encoding ascii -ErrorAction Stop
        } catch {
            Escribir ("No se puede poner la pausa (" + $FicheroPausa + "): " + $_.Exception.Message) "Red"
            return $false
        }
    }
    Escribir "La automatizacion queda en pausa: no arranca nada sola hasta iniciar.bat o automatico.bat -Reanudar." "Yellow"
    if (-not (Tomar-Cerrojo -Esperar 120 -Aviso "El ciclo automatico esta trabajando: espero a que acabe (como mucho 2 minutos)...")) {
        if ($SoloSiSigue -and -not $script:PausaYaEstaba) {
            Remove-Item -LiteralPath $FicheroPausa -Force -ErrorAction SilentlyContinue
        }
        if (Test-Path -LiteralPath $FicheroPausa) {
            Escribir "Hay una lectura en marcha (miralo en Procesar): espera a que termine o parala, y vuelve a probar. Mientras, no empieza nada nuevo." "Yellow"
        } else {
            Escribir "Hay una lectura en marcha (miralo en Procesar): espera a que termine o parala, y vuelve a probar. La automatizacion sigue como estaba." "Yellow"
        }
        return $false
    }
    # La app lo dice (ciclo latido --pausado), si la automatizacion esta puesta y Docker contesta.
    if ((Automatizacion-Puesta) -and (Docker-Listo 0) -and (Imagen-Lista)) {
        $base = $env:BMS_BASE
        $env:BMS_BASE = "bms"
        docker compose run --rm -T orden ciclo latido --pausado --variante docker *> $null
        $env:BMS_BASE = $base
    }
    return $true
}

function Reanudar-Automatico([switch]$SiLaPuseYo) {
    # Quita la pausa (y enciende la tarea del ciclo si alguien la apago y esta cuenta puede).
    # Con -SiLaPuseYo, solo si la puso este mismo script: una pausa de antes se respeta.
    if ($SiLaPuseYo -and $script:PausaYaEstaba) {
        Escribir "La automatizacion sigue en pausa, como estaba (para volver: automatico.bat -Reanudar)." "Yellow"
        return
    }
    if (Test-Path -LiteralPath $FicheroPausa) {
        Remove-Item -LiteralPath $FicheroPausa -Force -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $FicheroPausa) {
            Escribir ("No se ha podido quitar la pausa (" + $FicheroPausa + "): la automatizacion sigue parada.") "Red"
            return
        }
        Escribir "La automatizacion vuelve a funcionar." "Green"
    }
    $tarea = Tarea-Del-Ciclo
    if ($null -ne $tarea -and ("" + $tarea.State) -eq "Disabled") {
        try {
            Enable-ScheduledTask -TaskName $TareaCiclo -TaskPath "\" -ErrorAction Stop | Out-Null
        } catch {
            Escribir ("La tarea '" + $TareaCiclo + "' esta apagada y esta cuenta no la puede encender: encendela desde la cuenta que la puso (automatico.bat -Instalar).") "Yellow"
        }
    }
}

function Instante-Utc($Valor) {
    # Un instante AAAA-MM-DDTHH:MM:SSZ como fecha en UTC, o $null. PowerShell 7 ya da las
    # fechas de un JSON como fechas; Windows PowerShell 5.1, como texto.
    if ($Valor -is [DateTime]) { return $Valor.ToUniversalTime() }
    try {
        $estilo = [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal
        return [DateTime]::ParseExact(("" + $Valor), "yyyy-MM-dd'T'HH:mm:ss'Z'", [Globalization.CultureInfo]::InvariantCulture, $estilo)
    } catch {
        return $null
    }
}

function Texto-Utc([DateTime]$Instante) {
    return $Instante.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", [Globalization.CultureInfo]::InvariantCulture)
}

function Leer-Ciclo {
    # docker\estado\ciclo.json: lo que deja el ciclo (la ultima vez que paso, la pasada del dia)
    # para automatico.bat -Estado e iniciar.bat, sin abrir la base. $null si no esta.
    try {
        return (Get-Content -LiteralPath $FicheroCiclo -Raw -ErrorAction Stop | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Aviso-Del-Ciclo {
    # Lo que se dice si la automatizacion esta puesta y el ciclo no pasa desde hace mas de 30
    # minutos (sin pausa); $null si no hay nada que decir.
    if (En-Pausa) { return $null }
    $ciclo = Leer-Ciclo
    if ($null -eq $ciclo) { return $null }
    $visto = Instante-Utc $ciclo.visto_en
    if ($null -eq $visto) { return $null }
    if (((Get-Date).ToUniversalTime() - $visto).TotalMinutes -le 30) { return $null }
    return ("El ciclo automatico no corre desde " + $visto.ToLocalTime().ToString("yyyy-MM-dd HH:mm", [Globalization.CultureInfo]::InvariantCulture) + ": mira automatico.bat -Estado.")
}

function Disco-Libre {
    # Lo libre, en bytes, de la unidad del proyecto y de la de Docker Desktop (su disco de WSL2
    # vive por defecto en %LOCALAPPDATA%\Docker): el menor. Desde Windows: el contenedor solo
    # veria el disco virtual. $null si no se sabe.
    $libre = $null
    foreach ($ruta in @($PSScriptRoot, $env:LOCALAPPDATA)) {
        if (-not $ruta) { continue }
        try {
            $unidad = (Get-Item -LiteralPath $ruta -ErrorAction Stop).PSDrive
            $disco = Get-PSDrive -Name $unidad.Name -PSProvider FileSystem -ErrorAction Stop
            if ($null -ne $disco.Free -and ($null -eq $libre -or [long]$disco.Free -lt $libre)) {
                $libre = [long]$disco.Free
            }
        } catch { }
    }
    return $libre
}

function Entorno-De-La-Consola {
    # Como contesta la consola en 127.0.0.1:8765: $null si no contesta; "demo" con los DATOS
    # DE PRUEBA (cabecera X-BMS-Entorno); "" con los de verdad.
    try {
        $respuesta = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 -Uri "http://127.0.0.1:8765/consola"
    } catch {
        return $null
    }
    if ($respuesta.StatusCode -ne 200) { return $null }
    $entorno = ""
    foreach ($nombre in @($respuesta.Headers.Keys)) {
        if ($nombre -ieq "X-BMS-Entorno") { $entorno = ("" + $respuesta.Headers[$nombre]).Trim() }
    }
    return $entorno
}

function Servicios-En-Marcha {
    return @(docker compose ps --status running --services 2>$null | ForEach-Object { ("" + $_).Trim() })
}

function Orden-Secretos-Correo([string[]]$Argumentos) {
    # Las ordenes del certificado y de los ajustes del correo (correo certificado ... y correo
    # ajustes ...), en el contenedor de las ordenes, sin red, con SOLO la carpeta
    # docker\secretos\correo montada y solo para esta orden: nunca docker\secretos entera,
    # donde esta la clave de la API.
    New-Item -ItemType Directory -Force -Path $CarpetaSecretosCorreo | Out-Null
    docker compose run --rm -T -v "${CarpetaSecretosCorreo}:/secretos-correo" orden @Argumentos --carpeta /secretos-correo | Out-Host
    return $LASTEXITCODE
}

function Comprobar-Correo {
    # correo comprobar (que solo puede leer su buzon) en el contenedor del correo de siempre,
    # que solo ve los dos ficheros actuales, por su salida. Devuelve el codigo de salida y el
    # del correo (credencial, permiso, alcance...), que va en su salida de errores.
    $que = $null
    docker compose run --rm -T correo @OrdenComprobar 2>&1 | ForEach-Object {
        $linea = "" + $_
        if ($linea -match '^Correo: ([a-z_]+): ') { $que = $Matches[1] }
        Anotar $linea
    }
    $codigo = $LASTEXITCODE
    return [pscustomobject]@{ Codigo = $codigo; Que = $que }
}

function Registrar-Correo {
    # Lo que trajo el correo, a la base (correo registrar, en el contenedor de las ordenes):
    # asi la app ve enseguida el resultado de una comprobacion o de una ronda.
    docker compose run --rm -T orden correo registrar --entrada /correo/entrada --estado /correo/estado 2>&1 | ForEach-Object { Anotar ("" + $_) }
    return $LASTEXITCODE
}
