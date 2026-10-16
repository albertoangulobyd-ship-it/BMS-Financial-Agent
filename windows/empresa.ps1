# Pone la identidad de BM Support BV en la base de verdad: sus cuentas (IBAN), su btw-id y su
# KvK, sin Docker (paso 14, docs/instalacion-nativa.md). Sin las cuentas propias no entra
# ningun extracto del banco. Pide el token de una persona con el rol administrador.
#
#   .\empresa.ps1 -Ver
#   .\empresa.ps1 -Cuentas "NL02ABNA0123456789,NL44RABO0123456789" -BtwId "NL001122334B01" -Kvk "12345678"
#
# Las cuentas que se dan sustituyen a las de antes: se escriben todas, separadas por comas.
param(
    [string]$Cuentas = "",
    [string]$BtwId = "",
    [string]$Kvk = "",
    [switch]$Ver
)

. "$PSScriptRoot\comun.ps1"

$Inst = Buscar-Instalacion
Elegir-Base

if ($Ver) {
    $codigo = Orden-De "orden" @("empresa", "ver")
    exit $codigo
}
$lista = @($Cuentas -split "[,;]" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if ($lista.Count -eq 0 -and -not $BtwId -and -not $Kvk) {
    Fallar "Di las cuentas (-Cuentas), el btw-id (-BtwId) o el KvK (-Kvk). Para ver lo que hay: .\empresa.bat -Ver"
}
$argumentos = @("empresa", "fijar")
foreach ($cuenta in $lista) { $argumentos += @("--cuenta", $cuenta) }
if ($BtwId) { $argumentos += @("--btw-id", $BtwId) }
if ($Kvk) { $argumentos += @("--kvk", $Kvk) }
Pedir-Token
$codigo = Orden-De "orden" $argumentos
Olvidar-Token
if ($codigo -ne 0) { Fallar "No se ha puesto. Mira el mensaje de arriba." }
Escribir "Hecho. Ya se pueden importar los extractos del banco (importar.bat)." "Green"
