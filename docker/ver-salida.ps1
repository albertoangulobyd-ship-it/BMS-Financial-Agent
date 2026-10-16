# Lo que ha intentado salir a internet (paso 13, docs/entorno-local.md, el mantenimiento de
# cada mes). Lo lee del registro de la salida, que vive en su propio volumen: no se pierde al
# parar o arrancar (el de "docker compose logs salida" solo llega hasta el ultimo arranque).
#
#   .\ver-salida.ps1               cada intento, de lo mas viejo a lo mas nuevo
#   .\ver-salida.ps1 -Rechazados   solo lo que no se dejo salir
#
# Solo tiene que salir api.anthropic.com. Cualquier otra cosa es un aviso para quien
# mantiene el programa.
param([switch]$Rechazados)

. "$PSScriptRoot\comun.ps1"

Comprobar-Docker
Asegurar-Imagen
$argumentos = @("salida-registro")
if ($Rechazados) { $argumentos += "--rechazados" }
$codigo = Orden $argumentos
if ($codigo -ne 0) { Fallar "No hay registro todavia: arranca la consola con .\iniciar.ps1 y vuelve a probar." }
