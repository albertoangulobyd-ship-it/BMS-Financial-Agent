# Hace una copia de seguridad comprobada en el disco externo cifrado, sin Docker (paso 14,
# docs/instalacion-nativa.md, "Copias de seguridad").
#
#   .\copia.ps1 -Destino E:\BMS-copias
#   .\copia.ps1 -Comprobar E:\BMS-copias\bms-copia-bms-20261016-090256   (solo mirarla)
#
# La misma orden que en Docker (bms-agent copia): la base de verdad, sus originales y sus
# anclas en una carpeta nueva con la fecha, comprobada (la base se abre y cada fichero tiene
# su hash). Se puede hacer con la consola en marcha. La clave de la API no va en la copia: no
# serviria en otro ordenador (DPAPI), y alli se vuelve a guardar con clave.bat.
param(
    [string]$Destino,
    [string]$Comprobar,
    [switch]$Demo
)

. "$PSScriptRoot\comun.ps1"

$Inst = Buscar-Instalacion
Elegir-Base -Demo:$Demo
if ($Comprobar) {
    if (-not (Test-Path -LiteralPath $Comprobar)) { Fallar "No encuentro $Comprobar." }
    $carpeta = (Resolve-Path -LiteralPath $Comprobar).Path
    $codigo = Orden-De "orden" @("copia", $carpeta, "--comprobar")
    if ($codigo -ne 0) { Fallar "Esa copia no esta bien: haz otra en cuanto puedas." }
    Escribir "La copia esta bien: se abre y cada fichero tiene su hash." "Green"
    exit 0
}
if (-not $Destino) { Fallar "Dime donde dejar la copia: .\copia.bat -Destino E:\BMS-copias" }
if (-not (Test-Path -LiteralPath $Destino)) {
    Fallar "No encuentro $Destino. Conecta y desbloquea el disco cifrado, crea la carpeta y vuelve a probar."
}
$destinoCompleto = (Resolve-Path -LiteralPath $Destino).Path

Escribir "Haciendo la copia en $destinoCompleto..." "Cyan"
$codigo = Orden-De "orden" @("copia", $destinoCompleto)
if ($codigo -ne 0) { Fallar "La copia no se ha hecho bien. Mira el mensaje de arriba." }
Escribir "Copia hecha y comprobada. Expulsa el disco con seguridad antes de desconectarlo." "Green"
