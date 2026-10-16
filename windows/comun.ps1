# Lo que comparten los scripts de la instalacion nativa (paso 14, docs/instalacion-nativa.md).
# No se ejecuta solo: lo cargan instalar.ps1, iniciar.ps1, leer-facturas.ps1 y los demas.
#
# Sin Docker: cada papel tiene su propio Python (runtime\<papel>\python.exe) y el
# cortafuegos de Windows trata cada uno por su ruta. Estos scripts solo arrancan esos
# programas con la orden de bms-agent que toca. Funcionan en Windows PowerShell 5.1 (el
# que trae Windows) y en PowerShell 7. Solo ASCII: un .ps1 sin BOM se lee como ANSI en 5.1.

# "Continue" y no "Stop": cada orden se comprueba por su codigo de salida ($LASTEXITCODE).
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

# Lo que dice Python llega en UTF-8 (python -X utf8) y se lee en UTF-8: los acentos se ven.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$Prefijo = "BMS Finanzas - "
$Grupo = "BMS Finanzas"
$RaizPorDefecto = "C:\BMS"
$Roles = @("consola", "lector", "salida", "orden")
$Api = "api.anthropic.com:443"
$ApiNombre = "api.anthropic.com"
# Lo que vive como mucho la salida, si nadie la para: una lectura (la de un lote grande tarda)
# y una comprobacion.
$VidaSalidaLectura = 3 * 60 * 60
$VidaSalidaComprobacion = 10 * 60

function Escribir([string]$Texto, [string]$Color = "Gray") {
    Write-Host $Texto -ForegroundColor $Color
}

function Fallar([string]$Texto) {
    Write-Host ""
    Write-Host $Texto -ForegroundColor Red
    Write-Host ""
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

function Sid-Actual {
    return [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
}

function Comillas([string]$Texto) {
    # Para Start-Process: Windows PowerShell 5.1 junta los argumentos con espacios sin
    # comillas, y una ruta con espacios se partiria en dos.
    if ($Texto -eq "") { return '""' }
    if ($Texto -notmatch '[\s"]') { return $Texto }
    return '"' + $Texto.Replace('"', '\"') + '"'
}

function Linea-De-Argumentos([string[]]$Argumentos) {
    return (($Argumentos | ForEach-Object { Comillas $_ }) -join " ")
}

function Buscar-Instalacion {
    # La raiz es la carpeta de encima de windows\ (alli deja el instalador estos scripts) o,
    # si se lanzan desde la carpeta del proyecto, la de por defecto.
    $candidatas = @((Split-Path $PSScriptRoot -Parent), $RaizPorDefecto)
    foreach ($raiz in $candidatas) {
        $fichero = Join-Path $raiz "instalacion.json"
        if (Test-Path -LiteralPath $fichero) {
            $datos = Get-Content -Raw -LiteralPath $fichero | ConvertFrom-Json
            return [pscustomobject]@{
                Raiz          = $raiz
                PuertoConsola = [int]$datos.puerto_consola
                PuertoSalida  = [int]$datos.puerto_salida
            }
        }
    }
    Fallar "bms-agent no esta instalado en este ordenador (falta instalacion.json). Instalalo con instalar.bat (docs/instalacion-nativa.md)."
}

function Programa([string]$Rol) {
    return (Join-Path $Inst.Raiz ("runtime\" + $Rol + "\python.exe"))
}

function Elegir-Base([switch]$Demo) {
    # Todas las ordenes usan la base que diga BMS_DB.
    if ($Demo) {
        $env:BMS_DB = Join-Path $Inst.Raiz "datos\demo.sqlite3"
    } else {
        $env:BMS_DB = Join-Path $Inst.Raiz "datos\bms.sqlite3"
    }
}

# Las opciones de cada Python: -u, sin bufer (lo que dice va saliendo, tambien a un fichero o
# por una tuberia; con el ._pth no se mira PYTHONUNBUFFERED), y -X utf8.
$OpcionesPython = @("-u", "-X", "utf8")

function Orden-De([string]$Rol, [string[]]$Argumentos) {
    # Una orden de bms-agent con el programa de ese papel, que es el que tiene sus reglas del
    # cortafuegos. Out-Host: lo que dice se ve y no se mezcla con lo que devuelve la funcion.
    # Con -u se ve segun sale (una lectura larga no deja la ventana parada) y en su orden.
    $programa = Programa $Rol
    if (-not (Test-Path -LiteralPath $programa)) {
        Fallar "Falta $programa. Vuelve a instalar con instalar.bat."
    }
    Push-Location -LiteralPath $Inst.Raiz
    try {
        & $programa @OpcionesPython -m bms_agent.cli @Argumentos | Out-Host
        $codigo = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    return $codigo
}

function Orden-Directa([string]$Rol, [string[]]$Argumentos) {
    # Igual, pero hablando con la ventana sin pasar por PowerShell: para lo que pregunta algo
    # sin que se vea (la clave de la API).
    $programa = Programa $Rol
    if (-not (Test-Path -LiteralPath $programa)) {
        Fallar "Falta $programa. Vuelve a instalar con instalar.bat."
    }
    $todos = $OpcionesPython + @("-m", "bms_agent.cli") + $Argumentos
    $proceso = Start-Process -FilePath $programa -ArgumentList (Linea-De-Argumentos $todos) `
        -WorkingDirectory $Inst.Raiz -NoNewWindow -Wait -PassThru
    return $proceso.ExitCode
}

function Procesos-De([string]$Rol) {
    # Los procesos de un papel, por la ruta de su programa: un PID que se reutiliza no
    # confunde a nadie.
    $programa = Programa $Rol
    return @(Get-Process -Name python -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and ($_.Path -eq $programa) })
}

function Parar-Rol([string]$Rol) {
    foreach ($proceso in (Procesos-De $Rol)) {
        Stop-Process -Id $proceso.Id -Force -ErrorAction SilentlyContinue
        $proceso.WaitForExit(10000) | Out-Null
    }
}

function Arrancar-En-Segundo-Plano([string]$Rol, [string[]]$Argumentos) {
    # Sin ventana; lo que dice va a datos\<papel>.log y datos\<papel>-errores.log.
    $programa = Programa $Rol
    $registro = Join-Path $Inst.Raiz ("datos\" + $Rol + ".log")
    $errores = Join-Path $Inst.Raiz ("datos\" + $Rol + "-errores.log")
    $todos = $OpcionesPython + @("-m", "bms_agent.cli") + $Argumentos
    return (Start-Process -FilePath $programa -ArgumentList (Linea-De-Argumentos $todos) `
        -WorkingDirectory $Inst.Raiz -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $registro -RedirectStandardError $errores)
}

function Puerto-Abierto([int]$Puerto) {
    $cliente = New-Object System.Net.Sockets.TcpClient
    try {
        return $cliente.ConnectAsync("127.0.0.1", $Puerto).Wait(500)
    } catch {
        return $false
    } finally {
        $cliente.Close()
    }
}

function Nueva-Credencial {
    # 32 bytes al azar para el proxy de una pasada: solo los ven la salida y el lector.
    $bytes = New-Object byte[] 32
    $generador = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generador.GetBytes($bytes) } finally { $generador.Dispose() }
    return (($bytes | ForEach-Object { $_.ToString("x2") }) -join "")
}

function Arrancar-Salida([string]$Credencial, [int]$Segundos) {
    # El proxy de salida, solo en 127.0.0.1 y solo mientras dura la pasada. La credencial va
    # por el entorno del proceso de la salida, nunca en su linea de ordenes. Se para con
    # Parar-Salida al acabar; y si la ventana se cierra con la X (PowerShell muere sin llegar
    # al finally), se para sola a los $Segundos (--max-segundos).
    if ($Segundos -le 0) { Fallar "La salida necesita un plazo para pararse sola." }
    Parar-Rol "salida"
    if (Puerto-Abierto $Inst.PuertoSalida) {
        Fallar ("El puerto " + $Inst.PuertoSalida + " de este ordenador lo usa otro programa: la salida no puede arrancar.")
    }
    $registro = Join-Path $Inst.Raiz "datos\registro-salida\salida.log"
    $env:BMS_PROXY_CLAVE = $Credencial
    try {
        $proceso = Arrancar-En-Segundo-Plano "salida" @("salida", "--escuchar", ("127.0.0.1:" + $Inst.PuertoSalida),
            "--permitir", $Api, "--registro", $registro, "--clave-del-entorno",
            "--max-segundos", ([string]$Segundos))
    } finally {
        Remove-Item Env:\BMS_PROXY_CLAVE -ErrorAction SilentlyContinue
    }
    for ($i = 0; $i -lt 30; $i++) {
        if ($proceso.HasExited) { return $null }
        if (Puerto-Abierto $Inst.PuertoSalida) { return $proceso }
        Start-Sleep -Milliseconds 500
    }
    Stop-Process -Id $proceso.Id -Force -ErrorAction SilentlyContinue
    return $null
}

function Parar-Salida($Proceso) {
    if ($Proceso -and -not $Proceso.HasExited) {
        Stop-Process -Id $Proceso.Id -Force -ErrorAction SilentlyContinue
    }
    Parar-Rol "salida"
}

function Preparar-Certificados {
    # El lector comprueba el certificado de la API con los de Windows (truststore), dentro de
    # su propio proceso, que no tiene red. Si Windows aun no tiene la raiz o los intermedios de
    # la API (los baja cuando le hacen falta), el lector no los puede bajar y la lectura fallaria
    # con un error de TLS. PowerShell si tiene red: con una peticion a la API, Windows baja y
    # guarda la cadena. Lo que conteste la API da igual; solo cuenta un fallo de TLS.
    try {
        Invoke-WebRequest -UseBasicParsing -Method Head -TimeoutSec 20 -Uri ("https://" + $ApiNombre + "/") | Out-Null
        return $true
    } catch {
        if ($null -ne $_.Exception.Response) { return $true }
        Escribir ("   aviso no se ha podido hablar con " + $ApiNombre + " desde este ordenador (" + $_.Exception.Message + "): si el lector falla con un error de certificado, prueba otra vez con internet") "Yellow"
        return $false
    }
}

function Comprobar-Rol([string]$Rol, [string[]]$Extra = @()) {
    # La comprobacion de aislamiento de un papel, con su propio programa.
    return (Orden-De $Rol (@("comprobar-aislamiento", "--rol", $Rol) + $Extra))
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

function Olvidar-Token {
    Remove-Item Env:\BMS_TOKEN -ErrorAction SilentlyContinue
}

function Reglas-Del-Cortafuegos([string]$Raiz) {
    # Las reglas del cortafuegos de Windows, por programa. Windows no filtra 127.0.0.1, asi
    # que la consola sigue contestando al navegador y el lector llega al proxy local.
    # En Windows un bloqueo gana siempre a un permiso: la salida no lleva "bloquear todo y
    # permitir el 443", sino el permiso del 443 y un bloqueo de todo lo demas, por partes.
    $tabla = @(
        @{ Rol = "consola"; Que = "sin salida"; Direccion = "Outbound"; Accion = "Block"; Protocolo = ""; Puertos = @() },
        @{ Rol = "consola"; Que = "sin entrada"; Direccion = "Inbound"; Accion = "Block"; Protocolo = ""; Puertos = @() },
        @{ Rol = "lector"; Que = "sin salida"; Direccion = "Outbound"; Accion = "Block"; Protocolo = ""; Puertos = @() },
        @{ Rol = "lector"; Que = "sin entrada"; Direccion = "Inbound"; Accion = "Block"; Protocolo = ""; Puertos = @() },
        @{ Rol = "orden"; Que = "sin salida"; Direccion = "Outbound"; Accion = "Block"; Protocolo = ""; Puertos = @() },
        @{ Rol = "orden"; Que = "sin entrada"; Direccion = "Inbound"; Accion = "Block"; Protocolo = ""; Puertos = @() },
        @{ Rol = "salida"; Que = "sin entrada"; Direccion = "Inbound"; Accion = "Block"; Protocolo = ""; Puertos = @() },
        @{ Rol = "salida"; Que = "solo TCP 443"; Direccion = "Outbound"; Accion = "Allow"; Protocolo = "TCP"; Puertos = @("443") },
        @{ Rol = "salida"; Que = "ningun otro puerto TCP"; Direccion = "Outbound"; Accion = "Block"; Protocolo = "TCP"; Puertos = @("1-442", "444-65535") },
        @{ Rol = "salida"; Que = "sin UDP"; Direccion = "Outbound"; Accion = "Block"; Protocolo = "UDP"; Puertos = @() },
        @{ Rol = "salida"; Que = "sin ICMPv4"; Direccion = "Outbound"; Accion = "Block"; Protocolo = "ICMPv4"; Puertos = @() },
        @{ Rol = "salida"; Que = "sin ICMPv6"; Direccion = "Outbound"; Accion = "Block"; Protocolo = "ICMPv6"; Puertos = @() }
    )
    foreach ($fila in $tabla) {
        [pscustomobject]@{
            Nombre    = $Prefijo + $fila.Rol + " - " + $fila.Que
            Rol       = $fila.Rol
            Programa  = (Join-Path $Raiz ("runtime\" + $fila.Rol + "\python.exe"))
            Direccion = $fila.Direccion
            Accion    = $fila.Accion
            Protocolo = $fila.Protocolo
            Puertos   = $fila.Puertos
        }
    }
}

function Quitar-Reglas {
    # Exactamente las de bms-agent: las que empiezan por el prefijo.
    Get-NetFirewallRule -DisplayName ($Prefijo + "*") -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule -ErrorAction SilentlyContinue
}

function Carpetas-Del-Buzon {
    # Cada carpeta del buzon es un tipo de fichero, en el orden en que unos usan lo que
    # traen otros (el mismo que el del entorno de Docker).
    return [ordered]@{
        "exact\proveedores"     = @("exact", "proveedores")
        "exact\clientes"        = @("exact", "clientes")
        "maestro\objetos"       = @("maestro_csv", "objetos")
        "maestro\recursos"      = @("maestro_csv", "recursos")
        "maestro\contactos"     = @("maestro_csv", "contactos")
        "maestro\alias"         = @("maestro_csv", "alias")
        "maestro\tarifas"       = @("maestro_csv", "tarifas")
        "maestro\ciclos"        = @("maestro_csv", "ciclos")
        "trnsprnt"              = @("trnsprnt", "planning")
        "po"                    = @("po_csv", "ordenes_compra")
        "po\modificaciones"     = @("po_csv", "modificaciones_po")
        "exact\ventas"          = @("exact", "facturas_venta")
        "exact\pagos"           = @("exact", "pagos_exact")
        "banco"                 = @("banco", "extracto")
    }
}
