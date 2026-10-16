# Importa lo que hayas dejado en el buzon (paso 13, docs/entorno-local.md). No cuesta nada:
# no llama a ninguna API, y el contenedor que importa no tiene red.
#
#   .\importar.ps1          a tus datos de verdad
#   .\importar.ps1 -Demo    a los DATOS DE PRUEBA
#
# Cada carpeta del buzon es un tipo de fichero:
#
#   buzon\exact\proveedores   el listado de crediteuren de Exact (CSV)
#   buzon\exact\clientes      el listado de debiteuren de Exact (CSV)
#   buzon\exact\ventas        las facturas de venta de Exact (CSV)
#   buzon\exact\pagos         los openstaande posten / betalingen de Exact (CSV)
#   buzon\banco               los extractos del banco (CAMT.053 .xml, MT940 o CSV)
#   buzon\trnsprnt            el planning exportado de TRNSPRNT (CSV)
#   buzon\po                  la hoja de ordenes de compra (CSV o YAML)
#
# Lo que entra bien se mueve a buzon\hecho\<fecha>\; lo que no, se queda donde estaba y
# se dice por que. Los PDF de facturas (buzon\facturas) los lee leer-facturas.ps1.
param([switch]$Demo)

. "$PSScriptRoot\comun.ps1"

$buzon = Join-Path (Split-Path $PSScriptRoot -Parent) "buzon"
$carpetas = [ordered]@{
    "exact\proveedores" = @("exact", "proveedores")
    "exact\clientes"    = @("exact", "clientes")
    "exact\ventas"      = @("exact", "facturas_venta")
    "exact\pagos"       = @("exact", "pagos_exact")
    "banco"             = @("banco", "extracto")
    "trnsprnt"          = @("trnsprnt", "planning")
    "po"                = @("po_csv", "ordenes_compra")
}

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
$mal = 0
foreach ($f in $ficheros) {
    $fuente, $tipo = $carpetas[$f.Carpeta]
    $dentro = "/buzon/" + ($f.Carpeta -replace "\\", "/") + "/" + $f.Fichero.Name
    Escribir ""
    Escribir "Importando $($f.Carpeta)\$($f.Fichero.Name)..." "Cyan"
    $codigo = Orden @("importar", $fuente, $tipo, $dentro)
    if ($codigo -eq 0) {
        New-Item -ItemType Directory -Force -Path (Join-Path $hecho $f.Carpeta) | Out-Null
        Move-Item -Path $f.Fichero.FullName -Destination (Join-Path $hecho $f.Carpeta)
        $bien++
    } else {
        Escribir "No ha entrado: se queda en el buzon. El motivo esta justo arriba." "Red"
        $mal++
    }
}
Olvidar-Token
Escribir ""
Escribir "Hecho: $bien importados, $mal con problemas." $(if ($mal -eq 0) { "Green" } else { "Yellow" })
