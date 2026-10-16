# Una orden suelta de bms-agent con tu token, sin Docker (paso 14, docs/instalacion-nativa.md,
# "Las ordenes sueltas"). Lo que docs/uso-v1.md escribe "bms-agent ..." aqui se escribe
# "orden.bat ...", siempre sobre la base de verdad:
#
#   .\orden.bat iban listar
#   .\orden.bat iban verificar --proveedor-id 3 --iban NL91ABNA0417164300 --telefono 010-1234567 --motivo "Confirmado por telefono"
#   .\orden.bat btw ver
#   .\orden.bat historial 12
#
# Pide el token (no se ve al escribirlo) y lo pasa por el entorno, nunca en la linea de la
# orden. La orden corre con el programa de las ordenes (runtime\orden), que no tiene red.
. "$PSScriptRoot\comun.ps1"

if ($args.Count -eq 0) {
    Fallar "Di que orden: por ejemplo .\orden.bat iban listar (docs/uso-v1.md las explica)."
}
$Inst = Buscar-Instalacion
Elegir-Base
Pedir-Token
$codigo = Orden-De "orden" ([string[]]$args)
Olvidar-Token
exit $codigo
