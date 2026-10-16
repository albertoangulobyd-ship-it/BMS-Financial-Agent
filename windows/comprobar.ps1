# Comprueba el aislamiento de cada papel y lo dice en claro (paso 14,
# docs/instalacion-nativa.md, "Lo que prueba la comprobacion").
#
# No se fia de la configuracion: cada papel lo intenta con su propio programa.
#   consola y ordenes  no pueden llegar a internet, ni pasar por el proxy sin la credencial
#   salida             solo puede salir por el puerto 443
#   lector             no puede llegar a internet por su cuenta; por el proxy, solo a la API
#   todos              no pueden cambiar el programa (app, lib, runtime); si los datos y el buzon
#
# Antes de trabajar con datos de verdad, todo tiene que salir en verde. El resultado queda en
# datos\aislamiento.json, y la consola pinta una banda roja mientras algo falle o falte.
. "$PSScriptRoot\comun.ps1"

$Inst = Buscar-Instalacion
$resultados = [ordered]@{}

Escribir "1. El cortafuegos de Windows" "Cyan"
$cortafuegosBien = $true
try {
    foreach ($perfil in (Get-NetFirewallProfile -ErrorAction Stop)) {
        if ($perfil.Enabled -ne $true) {
            $cortafuegosBien = $false
            Escribir ("   MAL   el perfil " + $perfil.Name + " del cortafuegos esta apagado") "Red"
        }
    }
    $esperadas = @(Reglas-Del-Cortafuegos $Inst.Raiz)
    $hay = @(Get-NetFirewallRule -DisplayName ($Prefijo + "*") -ErrorAction SilentlyContinue)
    foreach ($regla in $esperadas) {
        if (-not ($hay | Where-Object { $_.DisplayName -eq $regla.Nombre })) {
            $cortafuegosBien = $false
            Escribir ("   MAL   falta la regla '" + $regla.Nombre + "'") "Red"
        }
    }
    if ($cortafuegosBien) { Escribir ("   bien  encendido, con sus " + $esperadas.Count + " reglas") "Green" }
} catch {
    Escribir "   aviso no se puede leer el cortafuegos desde aqui; lo que cuenta son las pruebas de abajo" "Yellow"
}

Escribir ""
Escribir "2. Cada papel prueba a salir, con su propio programa" "Cyan"
$credencial = Nueva-Credencial
$salida = Arrancar-Salida $credencial
try {
    $proxy = "127.0.0.1:" + $Inst.PuertoSalida
    if ($null -eq $salida) {
        Escribir "   La salida no arranca: el lector no se puede comprobar (y no leera)." "Red"
    }
    $resultados["consola"] = Comprobar-Rol "consola" @("--proxy", $proxy)
    $resultados["orden"] = Comprobar-Rol "orden" @("--proxy", $proxy)
    $env:BMS_PROXY_CLAVE = $credencial
    $resultados["salida"] = Comprobar-Rol "salida"
    Remove-Item Env:\BMS_PROXY_CLAVE -ErrorAction SilentlyContinue
    $env:HTTPS_PROXY = "http://bms:" + $credencial + "@" + $proxy
    Remove-Item Env:\NO_PROXY -ErrorAction SilentlyContinue
    $resultados["lector"] = Comprobar-Rol "lector"
} finally {
    Remove-Item Env:\HTTPS_PROXY -ErrorAction SilentlyContinue
    Remove-Item Env:\BMS_PROXY_CLAVE -ErrorAction SilentlyContinue
    Parar-Salida $salida
}

Escribir ""
Escribir "3. La clave de la API" "Cyan"
if (Test-Path -LiteralPath (Join-Path $Inst.Raiz "datos\secretos\clave-api.dpapi")) {
    $codigo = Orden-De "lector" @("clave", "comprobar")
    if ($codigo -ne 0) { Escribir "   MAL   la clave guardada no se puede usar: vuelve a guardarla con clave.bat" "Red" }
} else {
    Escribir "   aviso todavia no hay clave guardada (clave.bat); sin ella no se leen facturas" "Yellow"
}

Escribir ""
Escribir "Resumen" "Cyan"
$todoBien = $cortafuegosBien
foreach ($rol in $Roles) {
    if ($resultados[$rol] -eq 0) {
        Escribir ("   bien  " + $rol) "Green"
    } else {
        $todoBien = $false
        Escribir ("   MAL   " + $rol + " (arriba, lo que falla)") "Red"
    }
}
Escribir ""
if ($todoBien) {
    Escribir "Todo en verde: la consola y los datos no salen a internet, y el lector solo a la API por la salida." "Green"
    exit 0
}
Fallar "Algo no esta aislado (en rojo, arriba). No trabajes con datos de verdad: manda esta ventana a quien mantiene el programa."
