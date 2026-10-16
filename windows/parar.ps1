# Para la consola (y la salida, si se habia quedado en marcha) (paso 14,
# docs/instalacion-nativa.md).
#
# Los datos no se tocan: viven en datos\ y siguen ahi la proxima vez. Si se apaga el
# ordenador sin parar, tampoco pasa nada (la base aguanta un corte).
. "$PSScriptRoot\comun.ps1"

$Inst = Buscar-Instalacion
Parar-Rol "consola"
Parar-Rol "salida"
if ((Procesos-De "consola").Count -gt 0) { Fallar "No se ha podido parar la consola. Reinicia el ordenador." }
Escribir "Parado. Tus datos siguen guardados; la proxima vez: iniciar.bat" "Green"
