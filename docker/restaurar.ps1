# Vuelve a poner una copia de seguridad en su sitio (paso 13, docs/entorno-local.md,
# "Copias de seguridad").
#
#   .\restaurar.ps1 -Origen E:\BMS-copias\bms-copia-bms-20261016-090256
#
# Para la consola, comprueba la copia y la restaura. Lo que hubiera antes no se pierde:
# queda guardado entero en el volumen, en antes-de-restaurar. La vuelta atras queda en la
# auditoria (un evento de restauracion) y db verificar la ensena.
#
# Paso 18: antes de parar la consola, la automatizacion queda en pausa (y se espera a lo que
# este en marcha); si todo va bien, vuelve al terminar (si no estaba ya en pausa). Si algo
# falla, se queda en pausa: que lo mire una persona. Si no se puede esperar a lo que esta en
# marcha, no se toca nada (tampoco la pausa). Con el correo de facturas, dice que hacer con lo
# que llego por correo despues de la copia.
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
if (-not (Es-Si $respuesta)) {
    Escribir "No has escrito si: no se ha tocado nada." "Yellow"
    exit 0
}
if (-not (Pausar-Automatico "restaurar.bat" -SoloSiSigue)) {
    Fallar "No se ha tocado nada. Vuelve a abrir restaurar.bat cuando acabe la lectura."
}
Escribir "Parando la consola..." "Cyan"
docker compose down | Out-Host
# Montada con su nombre (bms-copia-...): el evento de la restauracion dice de que copia viene.
$nombre = Split-Path $origenCompleto -Leaf
docker compose run --rm -T -v "${origenCompleto}:/copias/${nombre}:ro" orden restaurar "/copias/$nombre" --db $base | Out-Host
if ($LASTEXITCODE -ne 0) { Fallar "No se ha restaurado. Tus datos siguen como estaban. Mira el mensaje de arriba." }
docker compose run --rm -T orden db verificar --db $base | Out-Host
if ($LASTEXITCODE -ne 0) { Fallar "La copia esta puesta pero no cuadra. No sigas trabajando y avisa a quien mantiene el programa." }
Soltar-Cerrojo
Reanudar-Automatico -SiLaPuseYo
Escribir "Restaurada y comprobada. Arranca la consola con .\iniciar.ps1" "Green"
if (-not $Demo -and (Test-Path -LiteralPath $FicheroAjustesCorreo)) {
    # Lo que el correo registro despues de la copia no esta en los datos restaurados, y el
    # correo no lo vuelve a traer (ya lo trajo y lo quito de su bandeja): se dice, con la fecha.
    $desde = "la fecha de la copia"
    if ($nombre -match '-([0-9]{4})([0-9]{2})([0-9]{2})-[0-9]{6}(-[0-9]+)?$') {
        $desde = $Matches[1] + "-" + $Matches[2] + "-" + $Matches[3]
    }
    Escribir ""
    Escribir ("Ojo, el correo de facturas: lo que llego al buzon desde " + $desde + " no esta en los datos restaurados y no se vuelve a traer solo. Busca en el buzon de facturas los correos desde ese dia, guarda sus PDF en buzon\facturas y leelos con leer-facturas.bat.") "Yellow"
}
