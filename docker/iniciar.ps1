# Arranca la consola en este ordenador (paso 13, docs/entorno-local.md).
#
#   .\iniciar.ps1          con los datos de verdad
#   .\iniciar.ps1 -Demo    con DATOS DE PRUEBA: se crean de nuevo, con la fecha de hoy
#
# La consola solo se abre desde este ordenador y no tiene salida a internet: la app
# (http://127.0.0.1:8765/app), en su propia ventana de Edge; la consola de antes sigue en
# http://127.0.0.1:8765/consola, de reserva. Para leer PDF con la API esta
# leer-facturas.ps1.
#
# Paso 18: es el boton de cada dia y no se queda colgado. Si la consola ya contesta con tus
# datos de verdad y es la de aqui, solo se abre (sin parar nada). Si no, espera como mucho un
# minuto a que el ciclo automatico suelte el cerrojo (si esta leyendo, lo dice y no toca
# nada) y arranca como siempre. Al acabar, la automatizacion vuelve a funcionar si estaba en
# pausa (parar.bat la deja asi).
param([switch]$Demo)

. "$PSScriptRoot\comun.ps1"

Comprobar-Docker
Asegurar-Imagen
Elegir-Base -Demo:$Demo

$base = "http://127.0.0.1:8765"
$consola_url = $base + "/consola"

# Ya en marcha con la base pedida (los DATOS DE PRUEBA se rehacen siempre) y es la nuestra.
if (-not $Demo -and (Entorno-De-La-Consola) -eq "") {
    $enMarcha = Servicios-En-Marcha
    if ($enMarcha -contains "consola" -and $enMarcha -contains "salida") {
        # La pasada del dia la hace el ciclo automatico; si hoy aun no (o no esta puesto), aqui,
        # sin parar nada y sin esperar: solo si el cerrojo esta libre (si no, el ciclo esta
        # trabajando y la hace el; dos a la vez se pisarian en la base).
        $ciclo = Leer-Ciclo
        $hoy = (Get-Date).ToString("yyyy-MM-dd", [Globalization.CultureInfo]::InvariantCulture)
        if (($null -eq $ciclo -or ("" + $ciclo.diaria) -ne $hoy) -and (Tomar-Cerrojo)) {
            docker compose run --rm -T orden recalcular --diaria *> $null
            Soltar-Cerrojo
        }
        $avisoCiclo = Aviso-Del-Ciclo
        Reanudar-Automatico
        $direccion = Direccion-De-La-App $base
        Escribir "Ya estaba en marcha, con tus datos de verdad." "Green"
        if ($avisoCiclo) { Escribir $avisoCiclo "Yellow" }
        Escribir "Se abre en su ventana: $direccion"
        Escribir "Si la app no se ve bien, la consola de antes sigue en $consola_url"
        Abrir-App $direccion
        exit 0
    }
}

if (-not (Tomar-Cerrojo -Esperar 60 -Aviso "El ciclo automatico esta trabajando: espero un minuto...")) {
    Fallar "El ciclo automatico esta leyendo: vuelve a abrir iniciar.bat en unos minutos (o mira Procesar si la app esta abierta)."
}

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

# Paso 18: tambien la salida del correo de facturas (sin el correo configurado no hace nada).
docker compose up -d consola salida salida_correo
if ($LASTEXITCODE -ne 0) { Fallar "La consola no ha arrancado. Mira el mensaje de arriba." }

Escribir "Esperando a que la consola conteste..." "Cyan"
# Lista cuando contesta /consola, que no depende de lo construido de la app: si la app falta,
# la consola de antes se abre igual (Direccion-De-La-App).
$lista = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $respuesta = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri $consola_url
        if ($respuesta.StatusCode -eq 200) { $lista = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $lista) { Fallar "La consola no contesta. Prueba otra vez en un minuto, o mira: docker compose logs consola" }
Soltar-Cerrojo
$avisoCiclo = Aviso-Del-Ciclo
Reanudar-Automatico
$direccion = Direccion-De-La-App $base

if ($Demo) {
    Escribir "Lista, con DATOS DE PRUEBA. Veras arriba la banda de TESTGEGEVENS (en la consola de antes, DATOS DE PRUEBA)." "Yellow"
} else {
    Escribir "Lista, con tus datos de verdad." "Green"
}
Escribir "Se abre en su ventana: $direccion"
Escribir "Si la app no se ve bien, la consola de antes sigue en $consola_url"
if ($avisoCiclo) { Escribir $avisoCiclo "Yellow" }
Escribir "Para pararla: .\parar.ps1"
Abrir-App $direccion
