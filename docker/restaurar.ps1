# Vuelve a poner una copia de seguridad en su sitio (paso 13, docs/entorno-local.md,
# "Copias de seguridad").
#
#   .\restaurar.ps1 -Origen E:\BMS-copias\bms-copia-bms-20261016-090256
#
# Para la consola, comprueba la copia y la restaura. Lo que hubiera antes no se pierde:
# queda guardado entero en el volumen, en antes-de-restaurar.
param(
    [Parameter(Mandatory = $true)][string]$Origen,
    [switch]$Demo
)

. "$PSScriptRoot\comun.ps1"

Comprobar-Docker
Asegurar-Imagen
if (-not (Test-Path $Origen)) {
    Fallar "No encuentro $Origen. Conecta y desbloquea el disco cifrado y elige la carpeta bms-copia-... que quieras."
}
$origenCompleto = (Resolve-Path $Origen).Path
$base = if ($Demo) { "/datos/demo.sqlite3" } else { "/datos/bms.sqlite3" }

$respuesta = Read-Host "Se va a poner la copia $origenCompleto en lugar de los datos de ahora (que se guardan antes). Seguir? (escribe si)"
if ($respuesta -ne "si") {
    Escribir "No se ha tocado nada." "Yellow"
    exit 0
}
Escribir "Parando la consola..." "Cyan"
docker compose down | Out-Host
docker compose run --rm -T -v "${origenCompleto}:/copia:ro" orden restaurar /copia --db $base | Out-Host
if ($LASTEXITCODE -ne 0) { Fallar "No se ha restaurado. Tus datos siguen como estaban. Mira el mensaje de arriba." }
docker compose run --rm -T orden db verificar --db $base | Out-Host
if ($LASTEXITCODE -ne 0) { Fallar "La copia esta puesta pero no cuadra. No sigas trabajando y avisa a quien mantiene el programa." }
Escribir "Restaurada y comprobada. Arranca la consola con .\iniciar.ps1" "Green"
