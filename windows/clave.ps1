# Guarda la clave de la API cifrada, sin Docker (paso 14, docs/instalacion-nativa.md, "La
# clave de la API").
#
#   .\clave.ps1            la pide (no se ve al escribirla) y la guarda cifrada
#   .\clave.ps1 -Borrar    la borra
#
# La clave se cifra con DPAPI de Windows: queda en datos\secretos\clave-api.dpapi y solo tu
# usuario de Windows, en este ordenador, la puede descifrar. No hay ningun fichero de texto
# con la clave, y nunca se ensena. De los programas de bms-agent, solo el lector la usa.
# Hazlo con tu usuario normal (doble clic en clave.bat), no como administrador: la clave queda
# atada al usuario que la guarda.
param([switch]$Borrar)

. "$PSScriptRoot\comun.ps1"

$Inst = Buscar-Instalacion
if ($Borrar) {
    $codigo = Orden-De "orden" @("clave", "borrar")
    exit $codigo
}
if (Es-Administrador) {
    Escribir "Aviso: esta ventana es de administrador. Si tu usuario de Windows no es el administrador, cierrala y abre clave.bat con doble clic." "Yellow"
}
Escribir "Pega la clave de la API (empieza por sk-ant-). En esta ventana se pega con el boton derecho del raton; no se ve al escribirla." "Cyan"
$codigo = Orden-Directa "orden" @("clave", "guardar")
if ($codigo -ne 0) { Fallar "No se ha guardado la clave. Mira el mensaje de arriba." }
$codigo = Orden-De "lector" @("clave", "comprobar")
if ($codigo -ne 0) { Fallar "La clave se ha guardado pero el lector no la puede leer. Avisa a quien mantiene el programa." }
Escribir "Clave guardada. Ya se pueden leer facturas (leer-facturas.bat)." "Green"
