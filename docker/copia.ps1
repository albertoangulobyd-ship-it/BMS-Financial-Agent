# Hace una copia de seguridad comprobada en el disco externo cifrado (paso 13,
# docs/entorno-local.md, "Copias de seguridad").
#
#   .\copia.ps1 -Destino E:\BMS-copias
#   .\copia.ps1 -Comprobar E:\BMS-copias\bms-copia-bms-20261016-090256   (solo mirarla)
#
# Copia la base de verdad, sus originales y sus anclas en una carpeta nueva con la fecha, y
# comprueba la copia (la base se abre y cada fichero tiene su hash). Se puede hacer con la
# consola en marcha.
param(
    [string]$Destino,
    [string]$Comprobar,
    [switch]$Demo
)

. "$PSScriptRoot\comun.ps1"

Comprobar-Docker
Asegurar-Imagen
$base = if ($Demo) { "/datos/demo.sqlite3" } else { "/datos/bms.sqlite3" }
if ($Comprobar) {
    if (-not (Test-Path $Comprobar)) { Fallar "No encuentro $Comprobar." }
    $carpeta = (Resolve-Path $Comprobar).Path
    docker compose run --rm -T -v "${carpeta}:/copia:ro" orden copia /copia --comprobar --db $base | Out-Host
    if ($LASTEXITCODE -ne 0) { Fallar "Esa copia no esta bien: haz otra en cuanto puedas." }
    Escribir "La copia esta bien: se abre y cada fichero tiene su hash." "Green"
    exit 0
}
if (-not $Destino) { Fallar "Dime donde dejar la copia: .\copia.ps1 -Destino E:\BMS-copias" }
if (-not (Test-Path $Destino)) {
    Fallar "No encuentro $Destino. Conecta y desbloquea el disco cifrado, crea la carpeta y vuelve a probar."
}
$destinoCompleto = (Resolve-Path $Destino).Path

Escribir "Haciendo la copia en $destinoCompleto..." "Cyan"
docker compose run --rm -T -v "${destinoCompleto}:/copia" orden copia /copia --db $base
if ($LASTEXITCODE -ne 0) { Fallar "La copia no se ha hecho bien. Mira el mensaje de arriba." }
Escribir "Copia hecha y comprobada. Expulsa el disco con seguridad antes de desconectarlo." "Green"
