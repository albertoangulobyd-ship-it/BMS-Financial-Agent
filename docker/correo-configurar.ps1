# El correo de facturas, la primera vez (paso 18, docs/correo-m365.md): el programa lee, sin
# poder cambiar nada, un buzon de Microsoft 365 que solo recibe facturas. En dos fases: el
# certificado tiene que existir antes que la aplicacion de Entra, y sus ids solo existen
# despues. Mira que hay y sigue donde quedo; se puede repetir sin miedo.
#
#   .\correo-configurar.ps1
#
# Fase 1 (sin certificado): crea la clave y el certificado en este equipo (la clave privada no
# sale nunca de aqui) y ensena la parte publica (el .cer) con una nota para el informatico.
# Fase 2 (con certificado): pide los cuatro datos que te da el informatico, los guarda, y
# comprueba con Microsoft que el programa solo puede leer ese buzon. Nunca rehace el
# certificado (eso invalidaria el que ya esta en Entra): para uno nuevo, correo-certificado.bat.
#
# Todo queda en docker\secretos\correo; las ordenes del certificado y de los ajustes corren
# en el contenedor de las ordenes, sin red, con solo esa carpeta montada.
. "$PSScriptRoot\comun.ps1"

Comprobar-Docker
Asegurar-Imagen
Elegir-Base

$cer = Join-Path $CarpetaSecretosCorreo "correo_certificado.cer"
$guid = '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
$direccion = '^[A-Za-z0-9_+-]+(\.[A-Za-z0-9_+-]+)*@[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$'

function Nota-Para-El-Informatico([string]$Fichero) {
    Escribir ""
    Escribir "La parte publica del certificado (la que se sube a Entra) esta en:" "Cyan"
    Escribir ("  " + $Fichero) "Cyan"
    Escribir ""
    Escribir "Para el informatico (copialo y mandaselo, con el fichero):"
    Escribir "  Sube este .cer a una aplicacion de Entra nueva siguiendo docs/correo-m365.md. Son unos 45"
    Escribir "  minutos de trabajo y luego hay que esperar hasta 2 horas a que Exchange reparta el"
    Escribir "  permiso. Despues pasame el id del inquilino (tenant), el de la aplicacion (client id),"
    Escribir "  la direccion del buzon de las facturas y la del buzon de control."
    Escribir "Voor de beheerder:"
    Escribir "  Upload dit .cer naar een nieuwe app-registratie in Entra volgens docs/correo-m365.md. Het"
    Escribir "  werk duurt ongeveer 45 minuten; daarna kan het tot 2 uur duren voordat Exchange de rechten"
    Escribir "  heeft verwerkt. Geef me daarna de tenant-id, de client-id van de app, het adres van de"
    Escribir "  factuurmailbox en dat van de controlemailbox."
    Escribir ""
}

function Preguntar([string]$Que, [string]$Guardado, [string]$Patron) {
    # Uno a uno, hasta que valga. Con Intro, lo guardado.
    while ($true) {
        $texto = $Que
        if ($Guardado) { $texto += " [" + $Guardado + "; Intro para dejarlo]" }
        $valor = ("" + (Read-Host $texto)).Trim()
        if (-not $valor -and $Guardado) { return $Guardado }
        if ($valor -match $Patron -and $valor.Length -le 320) { return $valor }
        Escribir "Eso no vale. Vuelve a escribirlo (o cierra la ventana: no se ha guardado nada)." "Yellow"
    }
}

function Dominio([string]$Direccion) {
    return $Direccion.Substring($Direccion.IndexOf("@") + 1).ToLowerInvariant()
}

Escribir "El correo de facturas: el programa solo puede leer un buzon; nunca manda, mueve ni borra nada." "Cyan"
$ver = Orden-Secretos-Correo @("correo", "certificado", "ver")

# ---------------------------------------------------------------- fase 1: el certificado
if ($ver -eq $CorreoSinConfigurar) {
    Escribir "Fase 1: se crea el certificado en este equipo." "Cyan"
    $codigo = Orden-Secretos-Correo @("correo", "certificado", "crear")
    if ($codigo -ne 0) { Fallar "No se ha creado el certificado. Mira el mensaje de arriba." }
    Nota-Para-El-Informatico $cer
    Escribir "Cuando tengas los cuatro datos, vuelve a abrir correo-configurar.bat." "Green"
    exit 0
}
if ($ver -ne 0) {
    Fallar "El certificado de ahora no se puede usar (arriba, por que). No se rehace: para uno nuevo, correo-certificado.bat."
}

# ---------------------------------------------------------------- fase 2: los ajustes
Escribir "El certificado ya esta (arriba, su huella y su caducidad); no se toca. Para uno nuevo: correo-certificado.bat." "Cyan"
$guardados = $null
if (Test-Path -LiteralPath $FicheroAjustesCorreo) {
    try {
        $guardados = Get-Content -LiteralPath $FicheroAjustesCorreo -Raw -ErrorAction Stop | ConvertFrom-Json
    } catch {
        $guardados = $null
    }
}
if ($null -eq $guardados) {
    $respuesta = Read-Host "Tienes ya los cuatro datos del informatico (el inquilino, la aplicacion y las dos direcciones)? (escribe si)"
    if (-not (Es-Si $respuesta)) {
        Nota-Para-El-Informatico $cer
        Escribir "Cuando los tengas, vuelve a abrir correo-configurar.bat." "Green"
        exit 0
    }
    $antes = @{ inquilino = ""; aplicacion = ""; buzon = ""; control = ""; desde = "" }
} else {
    Escribir "Fase 2 otra vez: lo guardado sale entre corchetes; con Intro se deja como esta." "Cyan"
    $desdeGuardado = $guardados.desde
    if ($desdeGuardado -is [DateTime]) { $desdeGuardado = $desdeGuardado.ToString("yyyy-MM-dd", [Globalization.CultureInfo]::InvariantCulture) }
    $antes = @{ inquilino = ("" + $guardados.inquilino); aplicacion = ("" + $guardados.aplicacion); buzon = ("" + $guardados.buzon); control = ("" + $guardados.buzon_control); desde = ("" + $desdeGuardado) }
}

$inquilino = Preguntar "El id del inquilino (Directory (tenant) ID)" $antes.inquilino $guid
$aplicacion = Preguntar "El id de la aplicacion (Application (client) ID)" $antes.aplicacion $guid
$buzon = Preguntar "La direccion del buzon de las facturas" $antes.buzon $direccion
while ($true) {
    $control = Preguntar "La direccion del buzon de control (otro buzon, que la aplicacion no puede leer)" $antes.control $direccion
    if ($control.ToLowerInvariant() -eq $buzon.ToLowerInvariant()) {
        Escribir "Tiene que ser otro buzon, distinto del de las facturas." "Yellow"
    } elseif ((Dominio $control) -ne (Dominio $buzon)) {
        Escribir "Tiene que ser del mismo dominio que el de las facturas." "Yellow"
    } else {
        break
    }
    $antes.control = ""
}
$porDefecto = $antes.desde
if (-not $porDefecto) { $porDefecto = (Get-Date).AddDays(-30).ToString("yyyy-MM-dd", [Globalization.CultureInfo]::InvariantCulture) }
$desde = Preguntar "Desde que dia se traen las facturas (AAAA-MM-DD; lo anterior se queda en el buzon)" $porDefecto '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'

$codigo = Orden-Secretos-Correo @("correo", "ajustes", "fijar", "--inquilino", $inquilino, "--aplicacion", $aplicacion, "--buzon", $buzon, "--buzon-control", $control, "--desde", $desde)
if ($codigo -ne 0) { Fallar "No se ha guardado nada: algo no vale (arriba, que). Vuelve a abrir correo-configurar.bat." }

# La comprobacion con Microsoft (por la salida del correo), y lo que diga, a la base: la app lo
# ve enseguida. Con el cerrojo: no se pisa con una ronda del ciclo automatico.
if (-not (Tomar-Cerrojo -Esperar 900 -Aviso "El ciclo automatico esta trabajando: espero a que acabe (como mucho 15 minutos)...")) {
    Fallar "Los datos estan guardados, pero el ciclo automatico sigue trabajando. Vuelve a abrir correo-configurar.bat dentro de un rato (con Intro, los deja como estan)."
}
Escribir "Comprobando con Microsoft que el programa solo puede leer ese buzon..." "Cyan"
$comprobado = Comprobar-Correo
Registrar-Correo | Out-Null
Soltar-Cerrojo

if ($comprobado.Codigo -eq 0) {
    Escribir "Hecho: el programa puede leer el buzon de las facturas, y solo ese." "Green"
    $tarea = Tarea-Del-Ciclo
    if ($null -eq $tarea -and -not (Test-Path -LiteralPath $FicheroCiclo)) {
        Escribir "Para que lo traiga solo cada 5 minutos: automatico.bat -Instalar (con la cuenta que se queda con la sesion iniciada)." "Yellow"
    } else {
        Escribir "El ciclo automatico lo trae en su ronda siguiente." "Green"
    }
    exit 0
}
switch ("" + $comprobado.Que) {
    "permiso" {
        Fallar "Microsoft aun no deja leer el buzon. Las dos primeras horas despues de que el informatico lo configure es normal (Exchange tarda en repartir el permiso): vuelve a abrir correo-configurar.bat en media hora; con Intro se deja todo como esta."
    }
    "alcance" {
        Fallar "La aplicacion puede leer MAS que el buzon de las facturas: por seguridad no se trae nada. Pide al informatico que lo revise (docs/correo-m365.md, 'Si sale alcance')."
    }
    "credencial" {
        Fallar "Microsoft no acepta el certificado: puede que el .cer no se haya subido a esa aplicacion, o que el inquilino o la aplicacion no sean esos. Revisalo con el informatico (docs/correo-m365.md, 'Si sale credencial')."
    }
    "control_no_existe" {
        Fallar "El buzon de control no existe: vuelve a abrir correo-configurar.bat y escribe uno que exista (y que la aplicacion no pueda leer)."
    }
    "reloj" {
        Fallar "La hora de este equipo no esta bien: ponla en hora (Configuracion > Hora e idioma > Sincronizar ahora) y vuelve a abrir correo-configurar.bat."
    }
    default {
        Fallar "No se ha podido comprobar ahora (arriba, por que: sin red, Microsoft ocupado...). Lo guardado se queda: vuelve a abrir correo-configurar.bat dentro de un rato; con Intro se deja todo como esta."
    }
}
