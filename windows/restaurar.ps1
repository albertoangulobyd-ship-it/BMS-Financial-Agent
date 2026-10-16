# Vuelve a poner una copia de seguridad en su sitio, sin Docker (paso 14,
# docs/instalacion-nativa.md, "Copias de seguridad").
#
#   .\restaurar.ps1 -Origen E:\BMS-copias\bms-copia-bms-20261016-090256
#
# Para la consola, comprueba la copia y la restaura (bms-agent restaurar, la misma que en
# Docker). Lo que hubiera antes no se pierde: queda guardado entero en
# datos\antes-de-restaurar. La vuelta atras queda en la auditoria y db verificar la ensena.
param(
    [Parameter(Mandatory = $true)][string]$Origen,
    [switch]$Demo
)

. "$PSScriptRoot\comun.ps1"

$Inst = Buscar-Instalacion
Elegir-Base -Demo:$Demo
if (-not (Test-Path -LiteralPath $Origen)) {
    Fallar "No encuentro $Origen. Conecta y desbloquea el disco cifrado y elige la carpeta bms-copia-... que quieras."
}
$origenCompleto = (Resolve-Path -LiteralPath $Origen).Path

$respuesta = Read-Host "Se va a poner la copia $origenCompleto en lugar de los datos de ahora (que se guardan antes). Seguir? (escribe si)"
if (-not (Es-Si $respuesta)) {
    Escribir "No has escrito si: no se ha tocado nada." "Yellow"
    exit 0
}
Escribir "Parando la consola..." "Cyan"
Parar-Rol "consola"
$codigo = Orden-De "orden" @("restaurar", $origenCompleto)
if ($codigo -ne 0) { Fallar "No se ha restaurado. Tus datos siguen como estaban. Mira el mensaje de arriba." }
$codigo = Orden-De "orden" @("db", "verificar")
if ($codigo -ne 0) { Fallar "La copia esta puesta pero no cuadra. No sigas trabajando y avisa a quien mantiene el programa." }
Escribir "Restaurada y comprobada. Arranca la consola con iniciar.bat" "Green"
