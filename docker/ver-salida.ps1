# Lo que ha intentado salir a internet (paso 13, docs/entorno-local.md, el mantenimiento de
# cada mes). Lo lee del registro de cada salida, que vive en su propio volumen: no se pierde
# al parar o arrancar (el de "docker compose logs" solo llega hasta el ultimo arranque).
#
#   .\ver-salida.ps1               cada intento, de lo mas viejo a lo mas nuevo
#   .\ver-salida.ps1 -Rechazados   solo lo que no se dejo salir
#
# Hay dos salidas, cada una con su lista y su registro: la de la API (la usa el lector), por
# la que solo tiene que salir api.anthropic.com; y la del correo de facturas (paso 18, la usa
# el contenedor del correo), por la que solo tienen que salir login.microsoftonline.com y
# graph.microsoft.com. Cualquier otra cosa es un aviso para quien mantiene el programa.
param([switch]$Rechazados)

. "$PSScriptRoot\comun.ps1"

Comprobar-Docker
Asegurar-Imagen
$hay = $false
Escribir "La salida de la API (el lector): solo tiene que salir api.anthropic.com." "Cyan"
$argumentos = @("salida-registro")
if ($Rechazados) { $argumentos += "--rechazados" }
$codigo = Orden $argumentos
if ($codigo -eq 0) { $hay = $true } else { Escribir "Aun no hay registro de la salida de la API." "Yellow" }
Escribir ""
Escribir "La salida del correo de facturas: solo tienen que salir login.microsoftonline.com y graph.microsoft.com." "Cyan"
$argumentos = @("salida-registro", "--fichero", "/registro-correo/salida-correo.log")
if ($Rechazados) { $argumentos += "--rechazados" }
$codigo = Orden $argumentos
if ($codigo -eq 0) { $hay = $true } else { Escribir "Aun no hay registro de la salida del correo (sin el correo configurado, es lo normal)." "Yellow" }
if (-not $hay) { Fallar "No hay registro todavia: arranca la consola con .\iniciar.ps1 y vuelve a probar." }
