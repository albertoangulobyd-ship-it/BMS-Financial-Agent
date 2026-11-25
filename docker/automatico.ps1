# Que el mini PC trabaje solo con la variante Docker (paso 18, docs/entorno-local.md): trae el
# correo de facturas, lo registra y lee lo que toca cada 5 minutos, sin nadie delante.
#
#   .\automatico.ps1 -Instalar      pone las dos tareas (sin ser administrador, con la cuenta
#                                   que las va a correr)
#   .\automatico.ps1 -Quitar        las quita
#   .\automatico.ps1 -Pausar        nada arranca solo hasta -Reanudar (o iniciar.bat): para
#                                   actualizar Docker Desktop o Windows
#   .\automatico.ps1 -Reanudar      vuelve a funcionar
#   .\automatico.ps1 -Estado        como esta, sin abrir la base (tambien sin nada)
#
# Las tareas, en el Programador de tareas de Windows:
#   "BMS Finanzas - ciclo (Docker)"     al iniciar sesion la cuenta (a los 2 minutos) y cada
#                                       15 minutos (el vigilante: si el bucle murio, lo vuelve a
#                                       arrancar; si sigue vivo, no hace nada), corre
#                                       ciclo.ps1 -Bucle en un PowerShell oculto, sin limite de
#                                       tiempo.
#   "BMS Finanzas - bloquear (Docker)"  al iniciar sesion, bloquea la pantalla (con -SinBloquear,
#                                       no se pone).
#
# Docker Desktop solo funciona con la sesion iniciada: lo recomendado es un usuario local
# estandar aparte (por ejemplo "bms", en el grupo docker-users, con la contrasena sin caducidad)
# que inicia sesion solo al encender el equipo y se queda con la pantalla bloqueada; el dueno
# trabaja con su cuenta de siempre y abre la app en http://127.0.0.1:8765/app. -Instalar
# comprueba esa cuenta y avisa de lo que no cuadra. Los pasos (inicio de sesion automatico con
# netplwiz, Docker Desktop al iniciar sesion y sin actualizarse solo), en docs/entorno-local.md.
param(
    [switch]$Instalar,
    [switch]$Quitar,
    [switch]$Pausar,
    [switch]$Reanudar,
    [switch]$Estado,
    [ValidateRange(5, 60)][int]$Minutos = 5,
    [switch]$SinBloquear
)

. "$PSScriptRoot\comun.ps1"

$acciones = @(@($Instalar, $Quitar, $Pausar, $Reanudar, $Estado) | Where-Object { $_ })
if ($acciones.Count -gt 1) {
    Fallar "Una cosa cada vez: -Instalar, -Quitar, -Pausar, -Reanudar o -Estado."
}
if ($acciones.Count -eq 0) { $Estado = $true }

function Tiene-Tareas {
    return [bool](Get-Command Register-ScheduledTask -ErrorAction SilentlyContinue)
}

function De-Grupo([string]$Que) {
    # Si esta cuenta esta en un grupo (por su SID, o por su nombre), segun whoami /groups.
    if (-not $env:SystemRoot) { return $false }
    $whoami = Join-Path $env:SystemRoot "System32\whoami.exe"
    if (-not (Test-Path -LiteralPath $whoami)) { return $false }
    $lineas = @(& $whoami /groups /fo csv /nh 2>$null)
    foreach ($linea in $lineas) {
        if (("" + $linea).IndexOf($Que, [StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    }
    return $false
}

function Avisos-De-La-Cuenta {
    # Lo que no cuadra de la cuenta que va a correr las tareas (diseno del paso 18, 4.2).
    $avisos = @()
    $nombre = $env:USERNAME
    $local = $null
    if (Get-Command Get-LocalUser -ErrorAction SilentlyContinue) {
        $local = Get-LocalUser -Name $nombre -ErrorAction SilentlyContinue
    }
    if ($null -eq $local) {
        $avisos += "Esta cuenta no es un usuario local de este equipo (es de la empresa o de un dominio): el inicio de sesion automatico necesita un usuario local con contrasena, por ejemplo 'bms'."
    } else {
        if (("" + $local.PrincipalSource) -ne "Local") {
            $avisos += "Esta cuenta es una cuenta de Microsoft: entra con Windows Hello y no sirve para el inicio de sesion automatico. Usa un usuario local con contrasena, por ejemplo 'bms'."
        }
        if ($null -ne $local.PasswordExpires) {
            $avisos += ("La contrasena de esta cuenta caduca el " + $local.PasswordExpires.ToString("yyyy-MM-dd", [Globalization.CultureInfo]::InvariantCulture) + ": entonces el equipo deja de iniciar sesion solo. Para que no caduque, en un PowerShell de administrador: " + 'Set-LocalUser -Name ' + $nombre + ' -PasswordNeverExpires $true')
        }
    }
    if (De-Grupo "S-1-5-32-544") {
        $avisos += "Esta cuenta es administradora: para lo que corre solo, mejor un usuario estandar aparte (por ejemplo 'bms')."
    }
    if (-not (De-Grupo "\docker-users")) {
        $avisos += "Esta cuenta no esta en el grupo docker-users: Docker Desktop no la deja usar Docker. Un administrador la anade en Administracion de equipos > Usuarios y grupos locales > Grupos > docker-users."
    }
    return $avisos
}

function Decir-Resultado($Resultado) {
    # LastTaskResult, en claro.
    $hex = "0x{0:X8}" -f $Resultado
    switch ($hex) {
        "0x00000000" { return "bien" }
        "0x00041301" { return "corriendo ahora (lo normal: el bucle no termina)" }
        "0x00041303" { return "aun no ha corrido" }
        "0x8007052E" { return "la cuenta no ha podido iniciar sesion (su contrasena ha cambiado): vuelve a ponerla en netplwiz y a abrir automatico.bat -Instalar" }
        default { return ("termino con " + $hex) }
    }
}

if ($Instalar) {
    if (-not (Tiene-Tareas)) { Fallar "Esto solo se hace en Windows (el Programador de tareas)." }
    Comprobar-Docker
    Asegurar-Imagen
    $avisos = @(Avisos-De-La-Cuenta)
    if ($avisos.Count -gt 0) {
        Escribir "Antes de seguir, lo que no cuadra de esta cuenta:" "Yellow"
        foreach ($aviso in $avisos) { Escribir ("  - " + $aviso) "Yellow" }
        $respuesta = Read-Host "Poner las tareas con esta cuenta de todas formas? (escribe si)"
        if (-not (Es-Si $respuesta)) {
            Escribir "No se ha puesto nada." "Yellow"
            exit 0
        }
    }
    $usuario = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $ciclo = Join-Path $PSScriptRoot "ciclo.ps1"
    $argumentos = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $ciclo + '" -Bucle -Minutos ' + $Minutos
    $accion = New-ScheduledTaskAction -Execute $powershell -Argument $argumentos -WorkingDirectory $PSScriptRoot
    # Al iniciar sesion esta cuenta, a los 2 minutos, y despues cada 15 (el vigilante).
    $alEntrar = New-ScheduledTaskTrigger -AtLogOn -User $usuario
    $alEntrar.Delay = "PT2M"
    # Sin -RepetitionDuration: se repite sin fin (PT15M).
    $alEntrar.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15)).Repetition
    # Una sola a la vez (IgnoreNew), sin limite de tiempo (PT0S: el de por defecto, 72 horas,
    # cortaria el bucle cada tres dias), y si falla, otra vez a los 5 minutos (3 veces).
    $ajustes = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    $ajustes.ExecutionTimeLimit = "PT0S"
    # Solo con la sesion iniciada (la de Docker Desktop), sin elevar y sin guardar contrasena.
    $quien = New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive -RunLevel Limited
    # Si ya estaba (otra vez -Instalar, por ejemplo con otros -Minutos), el bucle de antes se
    # para con el cerrojo en la mano: no se corta una lectura a medias.
    if ($null -ne (Tarea-Del-Ciclo)) {
        if (-not (Tomar-Cerrojo -Esperar 120 -Aviso "El ciclo automatico esta trabajando: espero a que acabe (como mucho 2 minutos)...")) {
            Fallar "Hay una lectura en marcha (miralo en Procesar): espera a que termine o parala, y vuelve a probar."
        }
        Stop-ScheduledTask -TaskName $TareaCiclo -TaskPath "\" -ErrorAction SilentlyContinue
    }
    try {
        Register-ScheduledTask -TaskName $TareaCiclo -TaskPath "\" -Action $accion -Trigger $alEntrar -Settings $ajustes -Principal $quien -Description "bms-agent (Docker): trae el correo de facturas y lee lo que toca cada pocos minutos (docker\ciclo.ps1 -Bucle)." -Force -ErrorAction Stop | Out-Null
    } catch {
        Fallar ("No se ha podido poner la tarea del ciclo: " + $_.Exception.Message)
    }
    if ($SinBloquear) {
        Unregister-ScheduledTask -TaskName $TareaBloquear -TaskPath "\" -Confirm:$false -ErrorAction SilentlyContinue
    } else {
        $bloquear = New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot "System32\rundll32.exe") -Argument "user32.dll,LockWorkStation"
        $alEntrarYa = New-ScheduledTaskTrigger -AtLogOn -User $usuario
        $ajustesBloquear = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        $ajustesBloquear.ExecutionTimeLimit = "PT1M"
        try {
            Register-ScheduledTask -TaskName $TareaBloquear -TaskPath "\" -Action $bloquear -Trigger $alEntrarYa -Settings $ajustesBloquear -Principal $quien -Description "bms-agent (Docker): bloquea la pantalla al iniciar sesion solo." -Force -ErrorAction Stop | Out-Null
        } catch {
            Escribir ("No se ha podido poner la tarea de bloquear la pantalla: " + $_.Exception.Message) "Yellow"
        }
    }
    Soltar-Cerrojo
    try { Start-ScheduledTask -TaskName $TareaCiclo -TaskPath "\" -ErrorAction Stop } catch { }
    Escribir ("Puesto. El ciclo corre cada " + $Minutos + " minutos con esta cuenta, mientras tenga la sesion iniciada.") "Green"
    if (En-Pausa) { Escribir "Ojo: la automatizacion esta en pausa. Para que trabaje: automatico.bat -Reanudar." "Yellow" }
    Escribir "Falta, si no esta: el inicio de sesion automatico de esta cuenta (netplwiz), Docker Desktop al iniciar sesion y sin actualizarse solo (docs/entorno-local.md)."
    Escribir "Para ver como va: automatico.bat -Estado. El registro de cada dia, en docker\estado\registro."
    exit 0
}

if ($Quitar) {
    if (-not (Tiene-Tareas)) { Fallar "Esto solo se hace en Windows (el Programador de tareas)." }
    # Con el cerrojo: no se corta una lectura a medias.
    if (-not (Tomar-Cerrojo -Esperar 120 -Aviso "El ciclo automatico esta trabajando: espero a que acabe (como mucho 2 minutos)...")) {
        Fallar "Hay una lectura en marcha (miralo en Procesar): espera a que termine o parala, y vuelve a probar."
    }
    foreach ($tarea in @($TareaCiclo, $TareaBloquear)) {
        Stop-ScheduledTask -TaskName $tarea -TaskPath "\" -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $tarea -TaskPath "\" -Confirm:$false -ErrorAction SilentlyContinue
        if (Get-ScheduledTask -TaskName $tarea -TaskPath "\" -ErrorAction SilentlyContinue) {
            Escribir ("No se ha podido quitar '" + $tarea + "': quitala con la cuenta que la puso.") "Yellow"
        }
    }
    Soltar-Cerrojo
    Escribir "Quitado: ya no se trae el correo ni se lee nada solo. La consola sigue como estaba (iniciar.bat, parar.bat)." "Green"
    exit 0
}

if ($Pausar) {
    if (-not (Pausar-Automatico "automatico.bat -Pausar")) { Fallar "No se ha podido esperar a lo que esta en marcha. La pausa queda puesta." }
    Soltar-Cerrojo
    Escribir "En pausa. Para volver: automatico.bat -Reanudar (o iniciar.bat)." "Green"
    exit 0
}

if ($Reanudar) {
    Reanudar-Automatico
    if (-not (Automatizacion-Puesta)) { Escribir "Las tareas no estan puestas: automatico.bat -Instalar." "Yellow" }
    exit 0
}

# -Estado (y sin nada): todo sin abrir la base.
Escribir "Lo automatico (Docker):" "Cyan"
if (Tiene-Tareas) {
    foreach ($tarea in @($TareaCiclo, $TareaBloquear)) {
        $puesta = Get-ScheduledTask -TaskName $tarea -TaskPath "\" -ErrorAction SilentlyContinue
        if ($null -eq $puesta) {
            Escribir ("  " + $tarea + ": no esta (o la puso otra cuenta, que es la que la ve). Se pone con automatico.bat -Instalar.") "Yellow"
            continue
        }
        $info = Get-ScheduledTaskInfo -TaskName $tarea -TaskPath "\" -ErrorAction SilentlyContinue
        $linea = "  " + $tarea + ": " + ("" + $puesta.State)
        if ($null -ne $info) {
            if ($info.LastRunTime -and $info.LastRunTime.Year -gt 2000) {
                $linea += ", la ultima vez " + $info.LastRunTime.ToString("yyyy-MM-dd HH:mm", [Globalization.CultureInfo]::InvariantCulture) + ": " + (Decir-Resultado $info.LastTaskResult)
            } else {
                $linea += ", aun no ha corrido"
            }
        }
        $color = if (("" + $puesta.State) -eq "Disabled") { "Yellow" } else { "Gray" }
        Escribir $linea $color
    }
} else {
    Escribir "  (sin el Programador de tareas de Windows: solo lo de abajo)"
}
if (En-Pausa) {
    $texto = ("" + (Get-Content -LiteralPath $FicheroPausa -TotalCount 1 -ErrorAction SilentlyContinue)).Trim()
    Escribir ("  EN PAUSA. " + $texto + " Para volver: automatico.bat -Reanudar o iniciar.bat.") "Yellow"
}
$ciclo = Leer-Ciclo
$visto = if ($null -ne $ciclo) { Instante-Utc $ciclo.visto_en } else { $null }
if ($null -eq $visto) {
    Escribir "  El ciclo automatico aun no ha corrido aqui." "Yellow"
} else {
    $hace = [int]((Get-Date).ToUniversalTime() - $visto).TotalMinutes
    $cuando = $visto.ToLocalTime().ToString("yyyy-MM-dd HH:mm", [Globalization.CultureInfo]::InvariantCulture)
    if ($hace -gt 30 -and -not (En-Pausa)) {
        Escribir ("  El ciclo automatico no corre desde " + $cuando + " (hace " + $hace + " minutos). Mira la tarea de arriba y el registro de hoy.") "Red"
    } else {
        Escribir ("  El ciclo paso por ultima vez a las " + $cuando + ".")
    }
    if ($null -ne $ciclo.disco_libre_bytes) {
        $libre = [long]$ciclo.disco_libre_bytes
        $gb = [math]::Floor($libre / 1GB)
        $color = if ($libre -lt $DiscoMinimo) { "Red" } else { "Gray" }
        Escribir ("  Disco libre: " + $gb + " GB" + $(if ($libre -lt $DiscoMinimo) { " (con menos de 10 no se trae ni se lee nada)" } else { "" }) + ".") $color
    }
}
if (Test-Path -LiteralPath $FicheroAjustesCorreo) {
    try {
        $ajustesCorreo = Get-Content -LiteralPath $FicheroAjustesCorreo -Raw -ErrorAction Stop | ConvertFrom-Json
        $caduca = if ($null -ne $ajustesCorreo.certificado) { Instante-Utc $ajustesCorreo.certificado.caduca_en } else { $null }
        if ($null -eq $caduca) {
            Escribir "  El correo: sin certificado actual (correo-configurar.bat)." "Yellow"
        } else {
            $dias = [int][math]::Floor(($caduca - (Get-Date).ToUniversalTime()).TotalDays)
            $fecha = $caduca.ToString("yyyy-MM-dd", [Globalization.CultureInfo]::InvariantCulture)
            if ($dias -lt 0) {
                Escribir ("  El certificado del correo CADUCO el " + $fecha + ": no entra ninguna factura. correo-certificado.bat.") "Red"
            } elseif ($dias -le 60) {
                Escribir ("  El certificado del correo caduca el " + $fecha + " (quedan " + $dias + " dias): renuevalo con correo-certificado.bat.") "Yellow"
            } else {
                Escribir ("  El certificado del correo caduca el " + $fecha + ".")
            }
        }
    } catch {
        Escribir "  El correo: no se pueden leer sus ajustes (correo-configurar.bat)." "Yellow"
    }
} else {
    Escribir "  El correo de facturas no esta configurado (correo-configurar.bat)."
}
if (Docker-Listo 0) {
    $corriendo = Servicios-En-Marcha
    $faltan = @(@("consola", "salida", "salida_correo") | Where-Object { $corriendo -notcontains $_ })
    if ($faltan.Count -gt 0) {
        Escribir ("  Docker contesta; no estan en marcha: " + ($faltan -join ", ") + " (iniciar.bat).") "Yellow"
    } else {
        Escribir "  Docker contesta y la consola esta en marcha."
    }
} else {
    Escribir "  Docker no contesta (con esta cuenta): sin Docker Desktop en marcha no se hace nada solo." "Yellow"
}
Escribir ("  El registro de cada dia: " + $CarpetaRegistroCiclo)
exit 0
