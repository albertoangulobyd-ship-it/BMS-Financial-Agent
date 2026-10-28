# Lee con la API de Anthropic los PDF de buzon\facturas, sin Docker (paso 14,
# docs/instalacion-nativa.md).
#
# ESTO CUESTA DINERO (unos centimos por factura). Por eso primero cuenta lo que va a mandar,
# te ensena el coste y no sigue hasta que digas que si. Lo ya leido no se vuelve a pagar.
#
# Paso 17: la lectura se puede pedir desde la app (Procesar, "Pedir lectura"). Este script
# toma esa peticion (o crea una, si nadie pidio nada), y la app ve cada paso: lo que cuesta,
# el si (en la app, "Empezar", o escrito aqui) y el progreso, factura a factura.
#
# Como sale a internet, y solo asi:
#   1. arranca la salida (el proxy que solo deja ir a api.anthropic.com:443) en 127.0.0.1,
#      con una credencial nueva para esta pasada, que solo ven la salida y el lector;
#   2. comprueba el aislamiento de la salida y del lector con sus propios programas: el
#      lector no puede llegar a internet por su cuenta, y por el proxy solo a la API;
#   3. si algo de eso falla, NO CUENTA NI LEE NADA ni paga nada (y el lector tampoco lo
#      haria: mira esa misma comprobacion antes de llamar a la API);
#   4. cuenta (gratis) y espera el si como mucho 15 minutos: de la app o escrito aqui. Con un
#      no, o sin respuesta, no lee nada ni gasta nada;
#   5. lee lo que conto, sin pasar del tope que se aprobo, y para la salida al acabar
#      (tambien si algo falla o se dice que no). Si se cierra la ventana con la X,
#      PowerShell no llega a pararla: se para sola a las 3 horas, y tambien la para abrir la
#      consola (iniciar.bat) o parar.bat.
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

# La lectura pedida desde la app, o una nueva. Sin ningun PDF no hay nada que leer (y una
# pedida termina asi, sin arrancar nada).
$tomada = Valor-De "lector" @("lectura", "tomar", $facturas)
if ($tomada.Codigo -eq $LecturaNada) {
    Escribir "No hay PDF en $facturas." "Yellow"
    exit 0
}
if ($tomada.Codigo -eq $LecturaOcupada) {
    Fallar "Ya hay otra lectura en marcha (arriba, cual). Si su ventana ya no esta abierta, di 'No leer' en la app y vuelve a abrir esto."
}
$solicitud = ("" + ($tomada.Lineas | Select-Object -Last 1)).Trim()
if ($tomada.Codigo -ne 0 -or $solicitud -notmatch '^[0-9]+$') {
    Fallar "No se ha podido empezar la lectura. Mira el mensaje de arriba."
}
if (-not (Test-Path -LiteralPath $clave)) {
    Cerrar-Lectura $solicitud "clave"
    Fallar "Falta la clave de la API. Guardala con clave.bat (docs/instalacion-nativa.md, 'La clave de la API')."
}

Escribir "Arrancando la salida (solo hacia api.anthropic.com, y solo durante esta lectura)..." "Cyan"
$credencial = Nueva-Credencial
$salida = Arrancar-Salida $credencial $VidaSalidaLectura
if ($null -eq $salida) {
    Cerrar-Lectura $solicitud "salida"
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
    Preparar-Certificados | Out-Null
    $env:HTTPS_PROXY = "http://bms:" + $credencial + "@127.0.0.1:" + $Inst.PuertoSalida
    Remove-Item Env:\NO_PROXY -ErrorAction SilentlyContinue
    Remove-Item Env:\ANTHROPIC_BASE_URL -ErrorAction SilentlyContinue
    $codigoLector = Comprobar-Rol "lector"

    if ($codigoSalida -ne 0 -or $codigoLector -ne 0) {
        Cerrar-Lectura $solicitud "aislamiento"
        $motivo = "El aislamiento no esta bien (arriba, lo que falla): no se cuenta, no se lee nada ni se paga nada. Ejecuta comprobar.bat y, si sigue en rojo, avisa a quien mantiene el programa."
    } else {
        Escribir "Contando lo que se mandaria (contar es gratis)..." "Cyan"
        $codigo = Orden-De "lector" @("lectura", "contar", $solicitud, $facturas, "--out", $out)
        if ($codigo -eq $LecturaNada) {
            $aviso = "No hay facturas nuevas: lo que hay ya esta leido. No se ha gastado nada."
        } elseif ($codigo -eq $LecturaCancelada) {
            $aviso = "Han dicho que no en la app: no se ha leido ni gastado nada."
        } elseif ($codigo -ne 0) {
            $motivo = "No se ha podido contar. Mira el mensaje de arriba."
        } else {
            # El si: en la app ("Empezar") o escrito aqui. Como mucho 15 minutos.
            $codigo = Orden-Directa "lector" @("lectura", "esperar", $solicitud)
            if ($codigo -eq $LecturaCaducada) {
                $aviso = "Nadie ha dicho que si en 15 minutos: no se ha leido ni gastado nada."
            } elseif ($codigo -eq $LecturaCancelada) {
                $aviso = "No se lee: no se ha leido ni gastado nada."
            } elseif ($codigo -ne 0) {
                $motivo = "La lectura no ha podido esperar el si. Mira el mensaje de arriba."
            } else {
                $codigo = Orden-De "lector" @("lectura", "leer", $solicitud, $facturas, "--out", $out)
                if ($codigo -eq $LecturaCancelada) {
                    $aviso = "Han parado la lectura antes de leer nada: no se ha gastado nada."
                } elseif ($codigo -ne 0) {
                    $motivo = "La lectura ha terminado con problemas. Mira el mensaje de arriba."
                }
            }
        }
    }
} finally {
    # Pase lo que pase (tambien con Ctrl+C), la salida se para y la credencial se olvida.
    Remove-Item Env:\HTTPS_PROXY -ErrorAction SilentlyContinue
    Remove-Item Env:\BMS_PROXY_CLAVE -ErrorAction SilentlyContinue
    Parar-Salida $salida
    # Y la lectura no se queda viva: si el lector la dejo a medias, termina aqui.
    Cerrar-Lectura $solicitud "interrumpida" -SiViva
}

if ($motivo) { Fallar $motivo }
if ($aviso) {
    Escribir $aviso "Yellow"
    exit 0
}
Escribir "Hecho. Las facturas leidas ya estan en la app y en la consola. La salida esta parada." "Green"
