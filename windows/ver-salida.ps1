# Lo que ha intentado salir a internet, sin Docker (paso 14, docs/instalacion-nativa.md, el
# mantenimiento de cada mes). Lo lee del registro de la salida (datos\registro-salida), que
# no se borra al parar.
#
#   .\ver-salida.ps1               cada intento, de lo mas viejo a lo mas nuevo
#   .\ver-salida.ps1 -Rechazados   solo lo que no se dejo salir
#
# Solo tiene que salir api.anthropic.com. Cualquier otra cosa, o un intento sin la
# credencial de la pasada (407), es un aviso para quien mantiene el programa.
param([switch]$Rechazados)

. "$PSScriptRoot\comun.ps1"

$Inst = Buscar-Instalacion
$argumentos = @("salida-registro", "--fichero", (Join-Path $Inst.Raiz "datos\registro-salida\salida.log"))
if ($Rechazados) { $argumentos += "--rechazados" }
$codigo = Orden-De "orden" $argumentos
if ($codigo -ne 0) { Fallar "No hay registro todavia: la salida solo arranca al leer facturas (leer-facturas.bat)." }
