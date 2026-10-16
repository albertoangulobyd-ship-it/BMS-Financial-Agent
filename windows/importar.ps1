# Importa lo que hayas dejado en el buzon, sin Docker (paso 14, docs/instalacion-nativa.md).
# No cuesta nada: no llama a ninguna API, y el programa que importa (runtime\orden) no tiene
# red.
#
#   .\importar.ps1          a tus datos de verdad
#   .\importar.ps1 -Demo    a los DATOS DE PRUEBA (solo admiten ficheros de prueba: uno de
#                           verdad se rechaza y se queda en el buzon)
#
# Cada carpeta del buzon (C:\BMS\buzon) es un tipo de fichero, las mismas que en Docker
# (docs/entorno-local.md, apartado 7), y se importan en ese orden. Lo que entra entero se
# mueve a buzon\hecho\<fecha>\. Lo que entra con alguna fila rechazada tambien se mueve, y se
# dice. Lo que no entra se queda donde estaba y se dice por que. Al final se hace la pasada
# del dia (recalcular --diaria). Los PDF de facturas (buzon\facturas) los lee
# leer-facturas.ps1.
param([switch]$Demo)

. "$PSScriptRoot\comun.ps1"

$Inst = Buscar-Instalacion
Elegir-Base -Demo:$Demo
$buzon = Join-Path $Inst.Raiz "buzon"
$carpetas = Carpetas-Del-Buzon
# Los codigos de salida de "bms-agent importar" (cli.py): 3, un lote no ha entrado; 4, ha
# entrado con filas rechazadas.
$rechazada = 3
$parcial = 4

foreach ($carpeta in $carpetas.Keys) {
    New-Item -ItemType Directory -Force -Path (Join-Path $buzon $carpeta) | Out-Null
}

$ficheros = @()
foreach ($carpeta in $carpetas.Keys) {
    $ficheros += Get-ChildItem -File -Path (Join-Path $buzon $carpeta) |
        ForEach-Object { [pscustomobject]@{ Carpeta = $carpeta; Fichero = $_ } }
}
if ($ficheros.Count -eq 0) {
    Escribir "No hay nada que importar en $buzon. Deja los ficheros en su carpeta y vuelve a probar." "Yellow"
    exit 0
}

Pedir-Token
$hecho = Join-Path $buzon ("hecho\" + (Get-Date -Format "yyyy-MM-dd"))
$bien = 0
$aMedias = 0
$mal = 0
foreach ($f in $ficheros) {
    $fuente, $tipo = $carpetas[$f.Carpeta]
    Escribir ""
    Escribir "Importando $($f.Carpeta)\$($f.Fichero.Name)..." "Cyan"
    $codigo = Orden-De "orden" @("importar", $fuente, $tipo, $f.Fichero.FullName)
    if ($codigo -eq 0 -or $codigo -eq $parcial) {
        New-Item -ItemType Directory -Force -Path (Join-Path $hecho $f.Carpeta) | Out-Null
        Move-Item -LiteralPath $f.Fichero.FullName -Destination (Join-Path $hecho $f.Carpeta)
        if ($codigo -eq $parcial) {
            Escribir "Ha entrado, pero con filas rechazadas (arriba, cada una con su motivo). Corrigelas en el sistema de origen y vuelve a exportarlo." "Yellow"
            $aMedias++
        } else {
            $bien++
        }
    } elseif ($codigo -eq $rechazada) {
        Escribir "No ha entrado ninguna fila: se queda en el buzon. El motivo esta justo arriba." "Red"
        $mal++
    } else {
        Escribir "No ha entrado: se queda en el buzon. El motivo esta justo arriba." "Red"
        $mal++
    }
}
Olvidar-Token

# La pasada del dia: lo que depende de la fecha (vencidas, plazos, PO que caducan).
$codigo = Orden-De "orden" @("recalcular", "--diaria")
if ($codigo -ne 0) { Escribir "No se ha podido hacer la pasada del dia (recalcular --diaria)." "Yellow" }

Escribir ""
Escribir "Hecho: $bien importados, $aMedias con filas rechazadas, $mal sin entrar." $(if ($mal -eq 0 -and $aMedias -eq 0) { "Green" } else { "Yellow" })
