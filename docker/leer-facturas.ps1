# Lee con la API de Anthropic los PDF de buzon\facturas (paso 13, docs/entorno-local.md).
#
# ESTO CUESTA DINERO (unos centimos por factura). Por eso primero cuenta, gratis, lo que
# va a mandar, y no sigue hasta que digas que si. Lo ya leido no se vuelve a pagar.
#
# Paso 17: la lectura se puede pedir desde la app (Procesar, "Pedir lectura"). Este script
# toma esa peticion (o crea una, si nadie pidio nada), y la app ve cada paso: lo que cuesta,
# el si (en la app, "Empezar", o escrito aqui, como mucho en 15 minutos) y el progreso. Con
# un no, o sin respuesta, no se lee nada ni se gasta nada.
#
# El lector es el unico contenedor que ve la clave (docker\secretos\anthropic_api_key.txt)
# y el unico que sale a internet, y solo a api.anthropic.com, por el proxy de la salida. Lo
# demas (tomar la peticion, esperar el si, cerrarla) lo hace el contenedor de las ordenes,
# que no tiene red ninguna.
#
#   .\leer-facturas.ps1          a tus datos de verdad
#
# Con -Demo no se lee nada: los DATOS DE PRUEBA ya traen sus facturas leidas, un PDF de prueba
# no se manda nunca a la API, y el buzon es el mismo para las dos bases (lo que haya en
# buzon\facturas es de verdad y no se paga para dejarlo en la base de prueba).
param([switch]$Demo)

. "$PSScriptRoot\comun.ps1"

if ($Demo) {
    Fallar "Con -Demo no se lee nada ni se paga nada: los datos de prueba ya traen sus facturas leidas. Para tus facturas: .\leer-facturas.bat (sin -Demo)."
}

$buzon = Join-Path (Split-Path $PSScriptRoot -Parent) "buzon"
$facturas = Join-Path $buzon "facturas"
$clave = Join-Path $PSScriptRoot "secretos\anthropic_api_key.txt"

Comprobar-Docker
Asegurar-Imagen
Elegir-Base
New-Item -ItemType Directory -Force -Path $facturas | Out-Null

# La lectura pedida desde la app, o una nueva. Sin ningun PDF no hay nada que leer.
$lineas = @(docker compose run --rm -T orden lectura tomar /buzon/facturas)
$codigo = $LASTEXITCODE
if ($codigo -eq $LecturaNada) {
    Escribir "No hay PDF en $facturas." "Yellow"
    exit 0
}
if ($codigo -eq $LecturaOcupada) {
    Fallar "Ya hay otra lectura en marcha (arriba, cual). Si su ventana ya no esta abierta, di 'No leer' en la app y vuelve a abrir esto."
}
$solicitud = ("" + ($lineas | Select-Object -Last 1)).Trim()
if ($codigo -ne 0 -or $solicitud -notmatch '^[0-9]+$') {
    Fallar "No se ha podido empezar la lectura. Mira el mensaje de arriba."
}
if (-not (Test-Path $clave)) {
    Cerrar-Lectura $solicitud "clave"
    Fallar "Falta la clave de la API en $clave. Como ponerla: docs/entorno-local.md, 'La clave de la API'."
}

$motivo = $null
$aviso = $null
try {
    Escribir "Contando lo que se mandaria (contar es gratis)..." "Cyan"
    docker compose run --rm -T lector lectura contar $solicitud /buzon/facturas --out /datos/out | Out-Host
    $codigo = $LASTEXITCODE
    if ($codigo -eq $LecturaNada) {
        $aviso = "No hay facturas nuevas: lo que hay ya esta leido. No se ha gastado nada."
    } elseif ($codigo -eq $LecturaCancelada) {
        $aviso = "Han dicho que no en la app: no se ha leido ni gastado nada."
    } elseif ($codigo -ne 0) {
        $motivo = "No se ha podido contar. Mira el mensaje de arriba."
    } else {
        # El si: en la app ("Empezar") o escrito aqui. Como mucho 15 minutos. Sin tuberia: lo
        # que se escribe en esta ventana le llega.
        docker compose run --rm -T orden lectura esperar $solicitud
        $codigo = $LASTEXITCODE
        if ($codigo -eq $LecturaCaducada) {
            $aviso = "Nadie ha dicho que si en 15 minutos: no se ha leido ni gastado nada."
        } elseif ($codigo -eq $LecturaCancelada) {
            $aviso = "No se lee: no se ha leido ni gastado nada."
        } elseif ($codigo -ne 0) {
            $motivo = "La lectura no ha podido esperar el si. Mira el mensaje de arriba."
        } else {
            docker compose run --rm -T lector lectura leer $solicitud /buzon/facturas --out /datos/out | Out-Host
            $codigo = $LASTEXITCODE
            if ($codigo -eq $LecturaCancelada) {
                $aviso = "Han parado la lectura antes de leer nada: no se ha gastado nada."
            } elseif ($codigo -ne 0) {
                $motivo = "La lectura ha terminado con problemas. Mira el mensaje de arriba."
            }
        }
    }
} finally {
    # Pase lo que pase (tambien con Ctrl+C), la lectura no se queda viva: si el lector la
    # dejo a medias, termina aqui.
    Cerrar-Lectura $solicitud "interrumpida" -SiViva
}

if ($motivo) { Fallar $motivo }
if ($aviso) {
    Escribir $aviso "Yellow"
    exit 0
}
Escribir "Hecho. Las facturas leidas ya estan en la app y en la consola." "Green"
