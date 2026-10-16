# Importa lo que hayas dejado en el buzon (paso 13, docs/entorno-local.md). No cuesta nada:
# no llama a ninguna API, y el contenedor que importa no tiene red.
#
#   .\importar.ps1          a tus datos de verdad
#   .\importar.ps1 -Demo    a los DATOS DE PRUEBA (solo admiten ficheros de prueba: uno de
#                           verdad se rechaza y se queda en el buzon)
#
# Cada carpeta del buzon es un tipo de fichero. Se importan en este orden, porque unos
# usan lo que traen otros (las tarifas y los ciclos, los Objetos y las personas; las
# ventas, los clientes y las PO; los pagos, las facturas):
#
#   buzon\exact\proveedores    el listado de crediteuren de Exact (CSV)
#   buzon\exact\clientes       el listado de debiteuren de Exact (CSV)
#   buzon\maestro\objetos      los Objetos (CSV)
#   buzon\maestro\recursos     las personas del planning (CSV)
#   buzon\maestro\contactos    los contactos de proveedores y clientes (CSV)
#   buzon\maestro\alias        los otros nombres de un proveedor, un cliente o un Objeto (CSV)
#   buzon\maestro\tarifas      las tarifas pactadas, de compra y de venta (CSV)
#   buzon\maestro\ciclos       los ciclos de facturacion (CSV)
#   buzon\trnsprnt             el planning exportado de TRNSPRNT (CSV)
#   buzon\po                   la hoja de ordenes de compra (CSV o YAML)
#   buzon\po\modificaciones    los cambios de una orden de compra (CSV)
#   buzon\exact\ventas         las facturas de venta de Exact (CSV)
#   buzon\exact\pagos          los openstaande posten / betalingen de Exact (CSV)
#   buzon\banco                los extractos del banco (CAMT.053 .xml, MT940 o CSV)
#
# Lo que entra entero se mueve a buzon\hecho\<fecha>\. Lo que entra con alguna fila
# rechazada tambien se mueve, y se dice. Lo que no entra se queda donde estaba y se dice
# por que. Al final se hace la pasada del dia (recalcular --diaria). Los PDF de facturas
# (buzon\facturas) los lee leer-facturas.ps1.
param([switch]$Demo)

. "$PSScriptRoot\comun.ps1"

$buzon = Join-Path (Split-Path $PSScriptRoot -Parent) "buzon"
$carpetas = [ordered]@{
    "exact\proveedores"     = @("exact", "proveedores")
    "exact\clientes"        = @("exact", "clientes")
    "maestro\objetos"       = @("maestro_csv", "objetos")
    "maestro\recursos"      = @("maestro_csv", "recursos")
    "maestro\contactos"     = @("maestro_csv", "contactos")
    "maestro\alias"         = @("maestro_csv", "alias")
    "maestro\tarifas"       = @("maestro_csv", "tarifas")
    "maestro\ciclos"        = @("maestro_csv", "ciclos")
    "trnsprnt"              = @("trnsprnt", "planning")
    "po"                    = @("po_csv", "ordenes_compra")
    "po\modificaciones"     = @("po_csv", "modificaciones_po")
    "exact\ventas"          = @("exact", "facturas_venta")
    "exact\pagos"           = @("exact", "pagos_exact")
    "banco"                 = @("banco", "extracto")
}
# Los codigos de salida de "bms-agent importar" (cli.py): 3, un lote no ha entrado; 4, ha
# entrado con filas rechazadas.
$rechazada = 3
$parcial = 4

Comprobar-Docker
Asegurar-Imagen
Elegir-Base -Demo:$Demo
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
    $dentro = "/buzon/" + ($f.Carpeta -replace "\\", "/") + "/" + $f.Fichero.Name
    Escribir ""
    Escribir "Importando $($f.Carpeta)\$($f.Fichero.Name)..." "Cyan"
    $codigo = Orden @("importar", $fuente, $tipo, $dentro)
    if ($codigo -eq 0 -or $codigo -eq $parcial) {
        New-Item -ItemType Directory -Force -Path (Join-Path $hecho $f.Carpeta) | Out-Null
        Move-Item -Path $f.Fichero.FullName -Destination (Join-Path $hecho $f.Carpeta)
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
docker compose run --rm -T orden recalcular --diaria *> $null
if ($LASTEXITCODE -ne 0) { Escribir "No se ha podido hacer la pasada del dia (recalcular --diaria)." "Yellow" }

Escribir ""
Escribir "Hecho: $bien importados, $aMedias con filas rechazadas, $mal sin entrar." $(if ($mal -eq 0 -and $aMedias -eq 0) { "Green" } else { "Yellow" })
