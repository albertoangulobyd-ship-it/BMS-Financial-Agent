# El certificado con que el programa pide su permiso a Microsoft para leer el buzon de
# facturas (paso 18, docs/correo-m365.md): renovarlo sin quedarse ni un dia sin correo, verlo
# o borrarlo. La clave privada se crea en este equipo y no sale nunca de aqui.
#
#   .\correo-certificado.ps1             crea el siguiente (el de la renovacion), al lado del de
#                                        ahora, y ensena su .cer para el informatico
#   .\correo-certificado.ps1 -Activar    cuando el informatico dice que ya lo subio: el
#                                        siguiente pasa a ser el de ahora y se comprueba con
#                                        Microsoft; si no vale, se vuelve al de antes
#   .\correo-certificado.ps1 -Ver        huella y caducidad de cada uno
#   .\correo-certificado.ps1 -Descartar  borra el siguiente (una renovacion que no se va a subir)
#   .\correo-certificado.ps1 -Borrar     borra todos: este equipo ya no puede leer el buzon
#                                        (para cortar el acceso del todo, el informatico quita
#                                        tambien el certificado en Entra)
#
# Todo queda en docker\secretos\correo. Las ordenes del certificado corren en el contenedor de
# las ordenes, sin red, con solo esa carpeta montada; la comprobacion, en el contenedor del
# correo de siempre, que solo ve los dos ficheros de ahora.
param(
    [switch]$Activar,
    [switch]$Ver,
    [switch]$Descartar,
    [switch]$Borrar
)

. "$PSScriptRoot\comun.ps1"

if (@(@($Activar, $Ver, $Descartar, $Borrar) | Where-Object { $_ }).Count -gt 1) {
    Fallar "Una cosa cada vez: -Activar, -Ver, -Descartar o -Borrar (o nada, para crear el siguiente)."
}

Comprobar-Docker
Asegurar-Imagen
Elegir-Base

$cerSiguiente = Join-Path $CarpetaSecretosCorreo "correo_certificado-siguiente.cer"
$pemSiguiente = Join-Path $CarpetaSecretosCorreo "correo_certificado-siguiente.pem"
$pemAnterior = Join-Path $CarpetaSecretosCorreo "correo_certificado-anterior.pem"

if ($Ver) {
    $codigo = Orden-Secretos-Correo @("correo", "certificado", "ver")
    exit $codigo
}

if ($Descartar) {
    $respuesta = Read-Host "Se borra el certificado siguiente (el de la renovacion, sin activar). Seguir? (escribe si)"
    if (-not (Es-Si $respuesta)) { Escribir "No has escrito si: no se ha tocado nada." "Yellow"; exit 0 }
    $codigo = Orden-Secretos-Correo @("correo", "certificado", "borrar", "--siguiente")
    if ($codigo -ne 0) { Fallar "No se ha borrado. Mira el mensaje de arriba." }
    Escribir "Hecho. Si el informatico ya lo habia subido a Entra, que lo quite." "Green"
    exit 0
}

if ($Borrar) {
    $respuesta = Read-Host "Se borran TODOS los certificados del correo de este equipo: el programa deja de poder leer el buzon. Seguir? (escribe si)"
    if (-not (Es-Si $respuesta)) { Escribir "No has escrito si: no se ha tocado nada." "Yellow"; exit 0 }
    $codigo = Orden-Secretos-Correo @("correo", "certificado", "borrar")
    if ($codigo -ne 0) { Fallar "No se ha borrado. Mira el mensaje de arriba." }
    Escribir "Hecho: este equipo ya no puede leer el buzon. Para cortar el acceso del todo, el informatico quita tambien el certificado en Entra (docs/correo-m365.md)." "Green"
    exit 0
}

if (-not $Activar) {
    # 1. El siguiente, al lado del de ahora (que sigue valiendo hasta activarlo).
    $codigo = Orden-Secretos-Correo @("correo", "certificado", "crear", "--siguiente")
    if ($codigo -ne 0) {
        Fallar "No se ha creado (arriba, por que). Si ya habia uno siguiente: cuando este subido, correo-certificado.bat -Activar; si no se va a subir, correo-certificado.bat -Descartar."
    }
    Escribir ""
    Escribir "La parte publica del certificado nuevo (la que se sube a Entra) esta en:" "Cyan"
    Escribir ("  " + $cerSiguiente) "Cyan"
    Escribir ""
    Escribir "Para el informatico (copialo y mandaselo, con el fichero):"
    Escribir "  Sube este .cer a la MISMA aplicacion de Entra (Certificates & secrets), sin quitar el de"
    Escribir "  ahora: durante un rato valen los dos. Son unos 10 minutos. Avisame cuando este."
    Escribir "Voor de beheerder:"
    Escribir "  Upload dit .cer naar DEZELFDE app-registratie in Entra (Certificates & secrets), zonder"
    Escribir "  het huidige te verwijderen: een tijdje gelden ze allebei. Ongeveer 10 minuten werk."
    Escribir "  Laat het me weten als het klaar is."
    Escribir ""
    Escribir "Cuando este subido: correo-certificado.bat -Activar." "Green"
    exit 0
}

# -Activar. Con la automatizacion en pausa y el cerrojo: nada trae el correo a la vez.
if (-not (Test-Path -LiteralPath $pemSiguiente) -and -not (Test-Path -LiteralPath $pemAnterior)) {
    Fallar "No hay certificado siguiente que activar: primero correo-certificado.bat (sin nada), y que el informatico lo suba."
}
if (-not (Pausar-Automatico "correo-certificado.bat -Activar")) {
    Fallar "No se ha tocado nada. Vuelve a abrir correo-certificado.bat -Activar cuando acabe la lectura."
}
if (Test-Path -LiteralPath $pemAnterior) {
    # Una activacion de antes sin comprobar (sin red, por ejemplo): solo se repite la comprobacion.
    Escribir "La activacion de antes aun no se habia comprobado: se comprueba ahora." "Cyan"
} else {
    $codigo = Orden-Secretos-Correo @("correo", "certificado", "activar")
    if ($codigo -ne 0) {
        Soltar-Cerrojo
        Reanudar-Automatico -SiLaPuseYo
        Fallar "No se ha activado (arriba, por que). Sigue el de antes."
    }
}
Escribir "Comprobando con Microsoft el certificado nuevo..." "Cyan"
$comprobado = Comprobar-Correo
$final = $null
if ($comprobado.Codigo -eq 0) {
    Orden-Secretos-Correo @("correo", "certificado", "borrar", "--anterior") | Out-Null
    Escribir "Hecho: el certificado nuevo vale. Ya puedes pedir al informatico que quite el viejo de Entra." "Green"
} elseif ($comprobado.Que -eq "credencial") {
    # Microsoft no acepta el nuevo (aun no esta subido, o no en esa aplicacion): vuelve el de
    # antes, que sigue valiendo, y el nuevo queda como siguiente para otro -Activar.
    $codigo = Orden-Secretos-Correo @("correo", "certificado", "volver")
    if ($codigo -eq 0) {
        Comprobar-Correo | Out-Null
        $final = "Microsoft no acepta el certificado nuevo: se ha vuelto al de antes, que sigue valiendo. Comprueba con el informatico que el .cer nuevo esta subido en esa aplicacion y vuelve a abrir correo-certificado.bat -Activar."
    } else {
        $final = "Microsoft no acepta el certificado nuevo y no se ha podido volver al de antes (arriba, por que). Avisa a quien mantiene el programa."
    }
} else {
    $final = "No se ha podido comprobar ahora (arriba, por que: sin red, Microsoft ocupado...). Se quedan los dos; vuelve a abrir correo-certificado.bat -Activar dentro de un rato."
}
Registrar-Correo | Out-Null
Soltar-Cerrojo
Reanudar-Automatico -SiLaPuseYo
if ($final) { Fallar $final }
exit 0
