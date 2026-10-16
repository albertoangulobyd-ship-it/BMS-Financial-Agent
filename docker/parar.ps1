# Para la consola y la salida (paso 13, docs/entorno-local.md).
#
# Los datos no se tocan: viven en el volumen "datos" de Docker y siguen ahi la proxima
# vez. Este script nunca borra el volumen.
. "$PSScriptRoot\comun.ps1"

Comprobar-Docker
docker compose down
if ($LASTEXITCODE -ne 0) { Fallar "No se ha podido parar. Mira el mensaje de arriba." }
Escribir "Parado. Tus datos siguen guardados; la proxima vez: .\iniciar.ps1" "Green"
