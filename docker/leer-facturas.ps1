# Lee con la API de Anthropic los PDF de buzon\facturas (paso 13, docs/entorno-local.md).
#
# ESTO CUESTA DINERO (unos centimos por factura). Por eso primero cuenta, gratis, lo que
# va a mandar, y no sigue hasta que digas que si. Lo ya leido no se vuelve a pagar.
#
# El lector es el unico contenedor que ve la clave (docker\secretos\anthropic_api_key.txt)
# y el unico que sale a internet, y solo a api.anthropic.com, por el proxy de la salida.
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
if (-not (Test-Path $clave)) {
    Fallar "Falta la clave de la API en $clave. Como ponerla: docs/entorno-local.md, 'La clave de la API'."
}
if ((Get-ChildItem -File -Path $facturas -Filter *.pdf).Count -eq 0) {
    Escribir "No hay PDF en $facturas." "Yellow"
    exit 0
}

Escribir "Contando lo que se mandaria (contar es gratis)..." "Cyan"
docker compose run --rm -T lector coste --estimar /buzon/facturas --out /datos/out
if ($LASTEXITCODE -ne 0) { Fallar "No se ha podido contar. Mira el mensaje de arriba." }

$respuesta = Read-Host "Leer estas facturas cuesta lo que dice arriba. Seguir? (escribe si)"
if ($respuesta -ne "si") {
    Escribir "No se ha leido nada ni se ha gastado nada." "Yellow"
    exit 0
}
docker compose run --rm -T lector extract /buzon/facturas --out /datos/out
if ($LASTEXITCODE -ne 0) { Fallar "La lectura ha terminado con problemas. Mira el mensaje de arriba." }
Escribir "Hecho. Las facturas leidas ya estan en la consola." "Green"
