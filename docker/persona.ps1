# Da de alta a una persona en la base de verdad y le da su token para la consola (paso 13,
# docs/entorno-local.md). Si ya existe, le da un token nuevo (el anterior deja de valer).
#
#   .\persona.ps1 -Nombre "Ana"                       con todos los permisos (administrador)
#   .\persona.ps1 -Nombre "Bram" -Rol administracion  el trabajo diario, sin usuarios ni politica
#   .\persona.ps1 -Nombre "Carla" -Rol consulta       solo mirar
param(
    [Parameter(Mandatory = $true)][string]$Nombre,
    [ValidateSet("administrador", "administracion", "consulta")][string]$Rol = "administrador"
)

. "$PSScriptRoot\comun.ps1"

Comprobar-Docker
Asegurar-Imagen
Elegir-Base

$existe = docker compose run --rm -T orden usuario listar | Select-String -SimpleMatch $Nombre
if (-not $existe) {
    $codigo = Orden @("usuario", "crear", $Nombre, "--rol", $Rol)
    if ($codigo -ne 0) { Fallar "No se ha podido dar de alta a $Nombre. Mira el mensaje de arriba." }
}
$codigo = Orden @("usuario", "token", $Nombre)
if ($codigo -ne 0) { Fallar "No se ha podido dar el token. Mira el mensaje de arriba." }
Escribir "Guarda ese token en el gestor de claves: se escribe al entrar en la consola." "Yellow"
