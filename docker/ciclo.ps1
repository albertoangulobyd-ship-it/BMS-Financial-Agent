# El ciclo automatico de la variante Docker (paso 18, docs/entorno-local.md): trae lo nuevo del
# buzon de facturas, lo registra, hace la pasada del dia y lee lo que toca, sin nadie delante.
#
#   .\ciclo.ps1            un ciclo, ahora (es lo que hace ciclo.bat)
#   .\ciclo.ps1 -Bucle     lo que corre la tarea "BMS Finanzas - ciclo (Docker)" de
#                          automatico.ps1: un ciclo cada 5 minutos (-Minutos, de 5 a 60), para
#                          siempre, en un solo PowerShell oculto
#
# El bucle no sale nunca por si mismo: si Docker Desktop aun no esta (WSL2 en frio puede
# tardar), espera; si algo falla, lo apunta en su registro (docker\estado\registro) y sigue en
# la vuelta siguiente. Con la pausa puesta (docker\estado\automatico.pausa, la ponen
# parar.bat, restaurar.bat, correo-certificado.bat -Activar y automatico.bat -Pausar) no hace
# nada. Siempre con la base de verdad, nunca con los DATOS DE PRUEBA.
#
# Cada ciclo, en este orden (diseno del paso 18, seccion 4.1): la pausa; el cerrojo (sin
# esperar: si otro lo tiene, este ciclo se salta) y otra vez la pausa; el latido con el disco
# libre (con menos de 10 GiB, nada mas); el correo (si esta configurado), y registrar lo que
# trajo; la pasada del dia (a partir de las 06:00); y la lectura: la que pidio una persona en
# la app (con el si de la app, como mucho 15 minutos) o una automatica dentro de la
# autorizacion que firmo una persona en la app, con sus topes. Aqui no se escribe nunca que
# si: el si de una automatica es esa autorizacion (lectura autorizar).
param(
    [switch]$Bucle,
    [ValidateRange(5, 60)][int]$Minutos = 5
)

. "$PSScriptRoot\comun.ps1"

# Al empezar el bucle, el correo comprueba que solo puede leer su buzon aunque no le toque.
$PrimeraRonda = $Bucle.IsPresent
$RegistroLimpiado = ""

function Abrir-Registro {
    # El registro del dia, docker\estado\registro\ciclo-AAAA-MM-DD.log; los de hace mas de 30
    # dias se borran (por su nombre), una vez al dia.
    $hoy = (Get-Date).ToString("yyyy-MM-dd", [Globalization.CultureInfo]::InvariantCulture)
    try {
        New-Item -ItemType Directory -Force -Path $CarpetaRegistroCiclo -ErrorAction Stop | Out-Null
    } catch {
        $script:RegistroCiclo = $null
        return
    }
    $script:RegistroCiclo = Join-Path $CarpetaRegistroCiclo ("ciclo-" + $hoy + ".log")
    if ($script:RegistroLimpiado -eq $hoy) { return }
    $script:RegistroLimpiado = $hoy
    $limite = (Get-Date).Date.AddDays(-30)
    foreach ($fichero in @(Get-ChildItem -LiteralPath $CarpetaRegistroCiclo -Filter "ciclo-*.log" -File -ErrorAction SilentlyContinue)) {
        if (-not ($fichero.Name -match '^ciclo-([0-9]{4}-[0-9]{2}-[0-9]{2})\.log$')) { continue }
        try {
            $dia = [DateTime]::ParseExact($Matches[1], "yyyy-MM-dd", [Globalization.CultureInfo]::InvariantCulture)
        } catch {
            continue
        }
        if ($dia -lt $limite) { Remove-Item -LiteralPath $fichero.FullName -Force -ErrorAction SilentlyContinue }
    }
}

function Guardar-Ciclo([hashtable]$Cambios) {
    # docker\estado\ciclo.json, con lo que ya tenia y estos cambios.
    $datos = [ordered]@{}
    $antes = Leer-Ciclo
    if ($null -ne $antes) {
        foreach ($propiedad in $antes.PSObject.Properties) {
            $valor = $propiedad.Value
            if ($valor -is [DateTime]) { $valor = Texto-Utc $valor }
            $datos[$propiedad.Name] = $valor
        }
    }
    foreach ($clave in $Cambios.Keys) { $datos[$clave] = $Cambios[$clave] }
    try {
        Set-Content -LiteralPath $FicheroCiclo -Value ($datos | ConvertTo-Json) -Encoding ascii -ErrorAction Stop
    } catch {
        Anotar ("No se puede escribir " + $FicheroCiclo + ": " + $_.Exception.Message) "Red"
    }
}

function Numero-De($Resultado) {
    # El numero de la lectura que da "lectura tomar" (la ultima linea de su salida normal).
    $ultima = ("" + ($Resultado.Lineas | Select-Object -Last 1)).Trim()
    if ($ultima -match '^[0-9]+$') { return $ultima }
    return $null
}

function Pasada-Del-Correo {
    # Una ronda del correo (correo traer, en su contenedor, por su salida) y, siempre que el
    # correo este configurado, correo registrar (en el de las ordenes, sin red): tambien si la
    # ronda no ha podido traer nada, registra lo que ya hubiera en la bandeja.
    if (-not ((Test-Path -LiteralPath $FicheroAjustesCorreo) -and (Test-Path -LiteralPath $FicheroCertificadoCorreo))) {
        if (Test-Path -LiteralPath $CarpetaSecretosCorreo) {
            # A medias (la fase 1 de correo-configurar) o con el certificado borrado: la app
            # lo dice si el correo ya estaba registrado (si no, no apunta nada).
            Anotar "El correo no esta configurado del todo (correo-configurar.bat): no se trae nada."
            Compose-Anotado @("run", "--rm", "-T", "orden", "correo", "registrar", "--fallo", "sin_configurar") | Out-Null
        }
        return
    }
    $salidaCorreo = Compose-Anotado @("up", "-d", "--wait", "--wait-timeout", "120", "salida_correo")
    if ($salidaCorreo.Codigo -ne 0) {
        Anotar "La salida del correo no arranca: esta vez no se trae nada." "Yellow"
        Compose-Anotado @("run", "--rm", "-T", "orden", "correo", "registrar", "--fallo", "salida") | Out-Null
    } else {
        if ($script:PrimeraRonda) {
            $traer = Compose-Anotado (@("run", "--rm", "-T", "correo") + $OrdenTraer + @("--comprobar"))
        } else {
            $traer = Compose-Anotado @("run", "--rm", "-T", "correo")
        }
        if ($traer.Codigo -eq 0) { $script:PrimeraRonda = $false }
        if (@(0, $CorreoSinConfigurar, $CorreoFallo) -notcontains $traer.Codigo) {
            # El correo no ha llegado a decir como acabo (su contenedor no arranco, o un fallo
            # del programa): la app lo ve como un fallo interno.
            Compose-Anotado @("run", "--rm", "-T", "orden", "correo", "registrar", "--fallo", "interno") | Out-Null
        }
    }
    Compose-Anotado @("run", "--rm", "-T", "orden", "correo", "registrar", "--entrada", "/correo/entrada", "--estado", "/correo/estado") | Out-Null
}

function Pasada-Del-Dia {
    # recalcular --diaria la primera vez cada dia, a partir de las 06:00 (la marca, en ciclo.json).
    $ahora = Get-Date
    if ($ahora.Hour -lt 6) { return }
    $hoy = $ahora.ToString("yyyy-MM-dd", [Globalization.CultureInfo]::InvariantCulture)
    $ciclo = Leer-Ciclo
    if ($null -ne $ciclo -and ("" + $ciclo.diaria) -eq $hoy) { return }
    $pasada = Compose-Anotado @("run", "--rm", "-T", "orden", "recalcular", "--diaria")
    if ($pasada.Codigo -eq 0) { Guardar-Ciclo @{ diaria = $hoy } }
}

function Leer-Con-Salida([string]$Solicitud, [switch]$Automatica) {
    # Contar y leer, una sola vez cada uno; entre los dos, el si: la autorizacion vigente
    # (lectura autorizar, una automatica) o el de la app (lectura esperar --solo-app, la que
    # pidio una persona), nunca uno escrito aqui. El lector sale por la salida de la API, que
    # se arranca antes; pase lo que pase, la lectura no se queda viva.
    if (-not (Test-Path -LiteralPath $FicheroClaveApi)) {
        Anotar "Falta la clave de la API (docker\secretos\anthropic_api_key.txt): no se lee nada." "Yellow"
        Cerrar-Lectura $Solicitud "clave"
        return
    }
    try {
        $salidaApi = Compose-Anotado @("up", "-d", "--wait", "--wait-timeout", "180", "salida")
        if ($salidaApi.Codigo -ne 0) {
            Anotar "La salida de la API no arranca: no se lee nada." "Yellow"
            Cerrar-Lectura $Solicitud "salida"
            return
        }
        $contada = Compose-Anotado @("run", "--rm", "-T", "lector", "lectura", "contar", $Solicitud, "/buzon/facturas", "--out", "/datos/out")
        if ($contada.Codigo -ne 0) { return }
        if ($Automatica) {
            $aceptada = Compose-Anotado @("run", "--rm", "-T", "orden", "lectura", "autorizar", $Solicitud)
        } else {
            $aceptada = Compose-Anotado @("run", "--rm", "-T", "orden", "lectura", "esperar", $Solicitud, "--solo-app")
        }
        if ($aceptada.Codigo -ne 0) { return }
        Compose-Anotado @("run", "--rm", "-T", "lector", "lectura", "leer", $Solicitud, "/buzon/facturas", "--out", "/datos/out") | Out-Null
    } finally {
        Cerrar-Lectura $Solicitud "interrumpida" -SiViva
    }
}

function Lectura-Del-Ciclo {
    # Que toca (lectura siguiente): la que pidio una persona en la app, una automatica o nada.
    if ((Entorno-De-La-Consola) -eq "demo") {
        # El lector levantaria la salida y, con ella, la consola con los datos de verdad.
        Anotar "La consola esta con los DATOS DE PRUEBA (iniciar.bat -Demo): esta vez no se lee nada."
        return
    }
    $toca = Compose-Anotado @("run", "--rm", "-T", "orden", "lectura", "siguiente")
    if ($toca.Codigo -eq 0) {
        $tomada = Compose-Anotado @("run", "--rm", "-T", "orden", "lectura", "tomar", "--automatica")
        if ($tomada.Codigo -ne 0) { return }
        $solicitud = Numero-De $tomada
        if ($null -eq $solicitud) { return }
        Leer-Con-Salida $solicitud -Automatica
    } elseif ($toca.Codigo -eq $LecturaPedida) {
        $tomada = Compose-Anotado @("run", "--rm", "-T", "orden", "lectura", "tomar", "/buzon/facturas", "--solo-pedida")
        if ($tomada.Codigo -ne 0) { return }
        $solicitud = Numero-De $tomada
        if ($null -eq $solicitud) { return }
        Leer-Con-Salida $solicitud
    }
    # $LecturaNada o $LecturaLimite: nada que leer ahora (el porque, arriba).
}

function Un-Ciclo {
    # 0. La pausa (no hace falta el cerrojo para mirarla).
    if (En-Pausa) {
        Anotar "En pausa: este ciclo no hace nada."
        return
    }
    # 1. El cerrojo, sin esperar; con el en la mano, otra vez la pausa (la pudieron poner ahora).
    if (-not (Tomar-Cerrojo)) {
        Anotar "Otra cosa esta trabajando (una lectura a mano, una copia, iniciar.bat...): este ciclo se salta."
        return
    }
    if (En-Pausa) {
        Anotar "En pausa: este ciclo no hace nada."
        return
    }
    if (-not (Imagen-Lista)) {
        Anotar "Falta el programa (la imagen bms-agent:local): abre iniciar.bat, que lo prepara." "Yellow"
        return
    }
    Elegir-Base
    Anotar "Ciclo automatico."
    # 2. El latido, con el disco libre medido desde Windows.
    $libre = Disco-Libre
    try {
        $latido = @("run", "--rm", "-T", "orden", "ciclo", "latido", "--variante", "docker")
        if ($null -ne $libre) { $latido += @("--disco-libre", ("" + $libre)) }
        Compose-Anotado $latido | Out-Null
        Guardar-Ciclo @{ visto_en = (Texto-Utc (Get-Date)); disco_libre_bytes = $libre }
    } catch {
        Anotar ("El latido ha fallado: " + $_.Exception.Message) "Red"
    }
    if ($null -ne $libre -and $libre -lt $DiscoMinimo) {
        Anotar "Quedan menos de 10 GiB libres: no se trae ni se lee nada." "Red"
        Compose-Anotado @("run", "--rm", "-T", "orden", "correo", "registrar", "--fallo", "disco") | Out-Null
        return
    }
    # 3. El correo. 4. La pasada del dia. 5. La lectura. Cada uno aparte: sin correo se puede
    # leer lo que ya hay.
    try { Pasada-Del-Correo } catch { Anotar ("El correo ha fallado: " + $_.Exception.Message) "Red" }
    try { Pasada-Del-Dia } catch { Anotar ("La pasada del dia ha fallado: " + $_.Exception.Message) "Red" }
    try { Lectura-Del-Ciclo } catch { Anotar ("La lectura ha fallado: " + $_.Exception.Message) "Red" }
}

function Apuntar-Pausa {
    # Una vez por pausa, que la app lo vea (ciclo latido --pausado), con el cerrojo (no se pisa
    # una restauracion). Pausar-Automatico ya lo hace; esto es por si no pudo (habia una
    # lectura en marcha). Devuelve si ya esta apuntado.
    if (-not (Tomar-Cerrojo)) { return $false }
    try {
        if (-not (En-Pausa)) { return $true }
        if (-not ((Docker-Listo 0) -and (Imagen-Lista))) { return $false }
        Elegir-Base
        $latido = Compose-Anotado @("run", "--rm", "-T", "orden", "ciclo", "latido", "--pausado", "--variante", "docker")
        return ($latido.Codigo -eq 0)
    } finally {
        Soltar-Cerrojo
    }
}

if (-not $Bucle) {
    # Un ciclo, ahora.
    try {
        Abrir-Registro
        if (Docker-Listo 60) {
            Un-Ciclo
        } else {
            Anotar "Docker Desktop no contesta: abrelo, espera a que la ballena deje de moverse y vuelve a probar." "Yellow"
        }
    } catch {
        Anotar ("El ciclo ha fallado: " + $_.Exception.Message) "Red"
    } finally {
        Soltar-Cerrojo
    }
    return
}

# El bucle. Con la pausa, mira cada 30 segundos si se quito (y el ciclo va enseguida).
$proximo = Get-Date
$proximaPausa = Get-Date
$pausaApuntada = $false
while ($true) {
    try {
        if (En-Pausa) {
            if (-not $pausaApuntada -and (Get-Date) -ge $proximaPausa) {
                $proximaPausa = (Get-Date).AddMinutes($Minutos)
                Abrir-Registro
                Anotar "En pausa: no se hace nada hasta iniciar.bat o automatico.bat -Reanudar."
                $pausaApuntada = Apuntar-Pausa
            }
            $proximo = Get-Date
        } else {
            $pausaApuntada = $false
            if ((Get-Date) -ge $proximo) {
                $proximo = (Get-Date).AddMinutes($Minutos)
                Abrir-Registro
                if (Docker-Listo 600) {
                    Un-Ciclo
                } else {
                    Anotar "Docker Desktop no contesta desde hace 10 minutos: se vuelve a probar en el ciclo siguiente." "Yellow"
                }
            }
        }
    } catch {
        try { Anotar ("El ciclo ha fallado (sigue en el siguiente): " + $_.Exception.Message) "Red" } catch { }
    } finally {
        Soltar-Cerrojo
    }
    Start-Sleep -Seconds 30
}
