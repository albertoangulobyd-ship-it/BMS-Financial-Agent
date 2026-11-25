# Para la consola y las salidas (paso 13, docs/entorno-local.md).
#
# Los datos no se tocan: viven en el volumen "datos" de Docker y siguen ahi la proxima
# vez. Este script nunca borra el volumen.
#
# Paso 18: antes de parar, la automatizacion queda en pausa (si no, el ciclo automatico y
# docker compose la volverian a arrancar en unos minutos), esperando como mucho 2 minutos a
# lo que este en marcha. Vuelve con iniciar.bat o automatico.bat -Reanudar.
. "$PSScriptRoot\comun.ps1"

if (-not (Pausar-Automatico "parar.bat")) {
    Fallar "No se ha parado nada todavia. Vuelve a abrir parar.bat cuando acabe la lectura."
}
Comprobar-Docker
docker compose down
if ($LASTEXITCODE -ne 0) { Fallar "No se ha podido parar. Mira el mensaje de arriba." }
Soltar-Cerrojo
Escribir "Parado. Tus datos siguen guardados. La automatizacion queda en pausa; para volver, iniciar.bat (o automatico.bat -Reanudar)." "Green"
