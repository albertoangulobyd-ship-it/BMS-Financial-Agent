# Da de alta a una persona en la base de verdad y le da su token para la consola (paso 13,
# docs/entorno-local.md). Si ya existe con ese mismo rol, le da un token nuevo (el anterior
# deja de valer). Si ya existe con otro rol, no toca nada ni da token: lo dice.
#
#   .\persona.ps1 -Nombre "Ana" -Rol administrador     todo, tambien personas y politica
#   .\persona.ps1 -Nombre "Bram" -Rol administracion   el trabajo diario, sin personas ni politica
#   .\persona.ps1 -Nombre "Carla" -Rol consulta        solo mirar
#
# El rol se dice siempre: no hay uno por defecto, para no dar sin querer mas de lo pensado.
param(
    [Parameter(Mandatory = $true)][string]$Nombre,
    [Parameter(Mandatory = $true)][ValidateSet("administrador", "administracion", "consulta")][string]$Rol
)

. "$PSScriptRoot\comun.ps1"

Comprobar-Docker
Asegurar-Imagen
Elegir-Base

# El nombre exacto, y solo con ese rol: "usuario asegurar" la crea si falta y sale con 3 si
# ya existe con otro rol (cli.py).
$codigo = Orden @("usuario", "asegurar", $Nombre, "--rol", $Rol)
if ($codigo -eq 3) {
    Fallar "$Nombre ya existe con otro rol (arriba): no se le ha dado ningun token. Si hay que cambiarle el rol, pide a quien mantiene el programa que lo haga."
}
if ($codigo -ne 0) { Fallar "No se ha podido dar de alta a $Nombre. Mira el mensaje de arriba." }
$codigo = Orden @("usuario", "token", $Nombre)
if ($codigo -ne 0) { Fallar "No se ha podido dar el token. Mira el mensaje de arriba." }
Escribir "Guarda ese token en el gestor de claves: se escribe al entrar en la consola." "Yellow"
