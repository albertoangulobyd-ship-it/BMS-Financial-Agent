# Arranca la consola en este ordenador, sin Docker (paso 14, docs/instalacion-nativa.md).
#
#   .\iniciar.ps1          con los datos de verdad
#   .\iniciar.ps1 -Demo    con DATOS DE PRUEBA: se crean de nuevo, con la fecha de hoy
#
# La consola corre con su propio programa (runtime\consola\python.exe), que el cortafuegos
# de Windows deja sin red, y solo se abre desde este ordenador
# (http://127.0.0.1:8765/consola). Antes comprueba el aislamiento de la consola y de las
# ordenes; si algo falla, la consola lo dice con una banda roja arriba. Para leer PDF con
# la API esta leer-facturas.ps1.
param([switch]$Demo)

. "$PSScriptRoot\comun.ps1"

$Inst = Buscar-Instalacion
Elegir-Base -Demo:$Demo

# Si la consola ya estaba en marcha (con esta base o con la otra), se para antes: la base de
# prueba se rehace, y no se borra una base que alguien tiene abierta.
Parar-Rol "consola"
# Una salida que se quedo encendida (una ventana de leer-facturas cerrada con la X) se para:
# solo esta encendida mientras se lee. Si el lector esta leyendo ahora, no se toca.
if ((Procesos-De "lector").Count -eq 0) { Parar-Rol "salida" }
# Si el puerto sigue ocupado es otro programa (la consola de Docker, por ejemplo): el
# navegador acabaria en esa y no en esta.
if (Puerto-Abierto $Inst.PuertoConsola) {
    Fallar ("El puerto " + $Inst.PuertoConsola + " lo usa otro programa. Si es la consola de Docker, parala con docker\parar.bat; despues vuelve a probar.")
}

if ($Demo) {
    Escribir "Creando los DATOS DE PRUEBA (todo ficticio, aparte de tus datos de verdad)..." "Yellow"
    $codigo = Orden-De "orden" @("demo", "crear", "--rehacer", "--db", $env:BMS_DB)
    if ($codigo -ne 0) { Fallar "No se han podido crear los datos de prueba. Mira el mensaje de arriba." }
    Escribir "Apunta uno de los dos tokens de arriba: es el que se escribe al entrar en la consola." "Yellow"
}

# La pasada del dia (recalcular --diaria): lo que depende de la fecha (vencidas, plazos, PO
# que caducan) se pone al dia aunque hoy no se importe nada.
$codigo = Orden-De "orden" @("recalcular", "--diaria")
if ($codigo -eq 0) {
    Escribir "Pasada del dia hecha." "Cyan"
} else {
    Escribir "No se ha hecho la pasada del dia (la primera vez es normal: aun no hay datos)." "Yellow"
}

# El aislamiento de la consola y de las ordenes, con sus propios programas: que no lleguen a
# internet. Si falla, la consola arranca igual pero lo dice en rojo en cada pagina.
Escribir "Comprobando que la consola y las ordenes no tienen salida a internet..." "Cyan"
$consola = Comprobar-Rol "consola"
$ordenes = Comprobar-Rol "orden"
if ($consola -ne 0 -or $ordenes -ne 0) {
    Escribir "ATENCION: el aislamiento no esta bien (arriba, lo que falla). No trabajes con datos de verdad hasta que comprobar.bat salga en verde." "Red"
}

$proceso = Arrancar-En-Segundo-Plano "consola" @("serve", "--puerto", ([string]$Inst.PuertoConsola),
    "--out", (Join-Path $Inst.Raiz "datos\out"), "--facturas", (Join-Path $Inst.Raiz "buzon\facturas"))

Escribir "Esperando a que la consola conteste..." "Cyan"
$direccion = "http://127.0.0.1:" + $Inst.PuertoConsola + "/consola"
$lista = $false
for ($i = 0; $i -lt 30; $i++) {
    if ($proceso.HasExited) { break }
    try {
        $respuesta = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri $direccion
        if ($respuesta.StatusCode -eq 200) { $lista = $true; break }
    } catch { Start-Sleep -Seconds 1 }
}
if (-not $lista) {
    Fallar ("La consola no contesta. Mira " + (Join-Path $Inst.Raiz "datos\consola-errores.log") + " y mandaselo a quien mantiene el programa.")
}

if ($Demo) {
    Escribir "Lista, con DATOS DE PRUEBA. Veras una banda roja arriba en cada pagina." "Yellow"
} else {
    Escribir "Lista, con tus datos de verdad." "Green"
}
Escribir "Se abre en el navegador: $direccion"
Escribir "Entra con tu token personal. Para pararla: parar.bat"
try {
    Start-Process $direccion
} catch {
    Escribir "Abre esa direccion en el navegador." "Yellow"
}
