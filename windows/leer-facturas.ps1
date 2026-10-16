# Lee con la API de Anthropic los PDF de buzon\facturas, sin Docker (paso 14,
# docs/instalacion-nativa.md).
#
# ESTO CUESTA DINERO (unos centimos por factura). Por eso primero cuenta lo que va a mandar,
# te ensena el coste y no sigue hasta que digas que si. Lo ya leido no se vuelve a pagar.
#
# Como sale a internet, y solo asi:
#   1. arranca la salida (el proxy que solo deja ir a api.anthropic.com:443) en 127.0.0.1,
#      con una credencial nueva para esta pasada, que solo ven la salida y el lector;
#   2. comprueba el aislamiento de la salida y del lector con sus propios programas: el
#      lector no puede llegar a internet por su cuenta, y por el proxy solo a la API;
#   3. si algo de eso falla, NO LEE NADA ni paga nada (y el lector tampoco lo haria: mira
#      esa misma comprobacion antes de llamar a la API);
#   4. cuenta, pregunta, lee, y para la salida al acabar (tambien si algo falla).
#
#   .\leer-facturas.ps1          a tus datos de verdad
#
# Con -Demo no se lee nada: los DATOS DE PRUEBA ya traen sus facturas leidas, un PDF de prueba
# no se manda nunca a la API, y el buzon es el mismo para las dos bases.
param([switch]$Demo)

. "$PSScriptRoot\comun.ps1"

if ($Demo) {
    Fallar "Con -Demo no se lee nada ni se paga nada: los datos de prueba ya traen sus facturas leidas. Para tus facturas: leer-facturas.bat (sin -Demo)."
}

$Inst = Buscar-Instalacion
Elegir-Base
$facturas = Join-Path $Inst.Raiz "buzon\facturas"
$out = Join-Path $Inst.Raiz "datos\out"
$clave = Join-Path $Inst.Raiz "datos\secretos\clave-api.dpapi"
New-Item -ItemType Directory -Force -Path $facturas | Out-Null
if (-not (Test-Path -LiteralPath $clave)) {
    Fallar "Falta la clave de la API. Guardala con clave.bat (docs/instalacion-nativa.md, 'La clave de la API')."
}
if ((Get-ChildItem -File -Path $facturas -Filter *.pdf).Count -eq 0) {
    Escribir "No hay PDF en $facturas." "Yellow"
    exit 0
}

Escribir "Arrancando la salida (solo hacia api.anthropic.com, y solo durante esta lectura)..." "Cyan"
$credencial = Nueva-Credencial
$salida = Arrancar-Salida $credencial
if ($null -eq $salida) {
    Fallar ("La salida no ha arrancado: no se lee nada. Mira " + (Join-Path $Inst.Raiz "datos\salida-errores.log"))
}

$motivo = $null
$aviso = $null
try {
    Escribir "Comprobando el aislamiento de la salida y del lector..." "Cyan"
    $env:BMS_PROXY_CLAVE = $credencial
    $codigoSalida = Comprobar-Rol "salida"
    Remove-Item Env:\BMS_PROXY_CLAVE -ErrorAction SilentlyContinue

    # El lector sale por el proxy de esta pasada, con su credencial, y por nada mas.
    $env:HTTPS_PROXY = "http://bms:" + $credencial + "@127.0.0.1:" + $Inst.PuertoSalida
    Remove-Item Env:\NO_PROXY -ErrorAction SilentlyContinue
    Remove-Item Env:\ANTHROPIC_BASE_URL -ErrorAction SilentlyContinue
    $codigoLector = Comprobar-Rol "lector"

    if ($codigoSalida -ne 0 -or $codigoLector -ne 0) {
        $motivo = "El aislamiento no esta bien (arriba, lo que falla): no se lee nada ni se paga nada. Ejecuta comprobar.bat y, si sigue en rojo, avisa a quien mantiene el programa."
    } else {
        Escribir "Contando lo que se mandaria (contar es gratis)..." "Cyan"
        $codigo = Orden-De "lector" @("coste", "--estimar", $facturas, "--out", $out)
        if ($codigo -ne 0) {
            $motivo = "No se ha podido contar. Mira el mensaje de arriba."
        } else {
            $respuesta = Read-Host "Leer estas facturas cuesta lo que dice arriba. Seguir? (escribe si)"
            if (-not (Es-Si $respuesta)) {
                $aviso = "No has escrito si: no se ha leido nada ni se ha gastado nada."
            } else {
                $codigo = Orden-De "lector" @("extract", $facturas, "--out", $out)
                if ($codigo -ne 0) { $motivo = "La lectura ha terminado con problemas. Mira el mensaje de arriba." }
            }
        }
    }
} finally {
    # Pase lo que pase (tambien con Ctrl+C), la salida se para y la credencial se olvida.
    Remove-Item Env:\HTTPS_PROXY -ErrorAction SilentlyContinue
    Remove-Item Env:\BMS_PROXY_CLAVE -ErrorAction SilentlyContinue
    Parar-Salida $salida
}

if ($motivo) { Fallar $motivo }
if ($aviso) {
    Escribir $aviso "Yellow"
    exit 0
}
Escribir "Hecho. Las facturas leidas ya estan en la consola. La salida esta parada." "Green"
