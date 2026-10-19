# Arranca la consola en este ordenador (paso 13, docs/entorno-local.md).
#
#   .\iniciar.ps1          con los datos de verdad
#   .\iniciar.ps1 -Demo    con DATOS DE PRUEBA: se crean de nuevo, con la fecha de hoy
#
# La consola solo se abre desde este ordenador y no tiene salida a internet: la app
# (http://127.0.0.1:8765/app), en su propia ventana de Edge; la consola de antes sigue en
# http://127.0.0.1:8765/consola, de reserva. Para leer PDF con la API esta
# leer-facturas.ps1.
param([switch]$Demo)

. "$PSScriptRoot\comun.ps1"

Comprobar-Docker
Asegurar-Imagen
Elegir-Base -Demo:$Demo

# Si la consola ya estaba en marcha (con esta base o con la otra), se para antes: la base
# de prueba se rehace, y no se borra una base que alguien tiene abierta.
docker compose down *> $null

if ($Demo) {
    Escribir "Creando los DATOS DE PRUEBA (todo ficticio, aparte de tus datos de verdad)..." "Yellow"
    $codigo = Orden @("demo", "crear", "--rehacer", "--db", "/datos/demo.sqlite3")
    if ($codigo -ne 0) { Fallar "No se han podido crear los datos de prueba. Mira el mensaje de arriba." }
    Escribir "Apunta uno de los dos tokens de arriba: es el que se escribe al entrar en la consola." "Yellow"
}

# La pasada del dia (recalcular --diaria): lo que depende de la fecha (vencidas, plazos, PO
# que caducan) se pone al dia aunque hoy no se importe nada. Una base que aun no existe (la
# primera vez) no tiene nada que recalcular.
docker compose run --rm -T orden recalcular --diaria *> $null
if ($LASTEXITCODE -eq 0) {
    Escribir "Pasada del dia hecha." "Cyan"
} else {
    Escribir "No se ha hecho la pasada del dia (la primera vez es normal: aun no hay datos)." "Yellow"
}

docker compose up -d consola salida
if ($LASTEXITCODE -ne 0) { Fallar "La consola no ha arrancado. Mira el mensaje de arriba." }

Escribir "Esperando a que la consola conteste..." "Cyan"
$lista = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $respuesta = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri "http://127.0.0.1:8765/app"
        if ($respuesta.StatusCode -eq 200) { $lista = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $lista) { Fallar "La consola no contesta. Prueba otra vez en un minuto, o mira: docker compose logs consola" }

if ($Demo) {
    Escribir "Lista, con DATOS DE PRUEBA. Veras arriba la banda de TESTGEGEVENS (en la consola de antes, DATOS DE PRUEBA)." "Yellow"
} else {
    Escribir "Lista, con tus datos de verdad." "Green"
}
Escribir "Se abre la app en su ventana: http://127.0.0.1:8765/app"
Escribir "Si la app no se ve bien, la consola de antes sigue en http://127.0.0.1:8765/consola"
Escribir "Para pararla: .\parar.ps1"
Abrir-App "http://127.0.0.1:8765/app"
