# Instala bms-agent en este ordenador, sin Docker (paso 14, docs/instalacion-nativa.md).
#
#   instalar.bat                     en C:\BMS (doble clic, con tu usuario de siempre)
#   .\instalar.ps1 -Raiz D:\BMS      en otra carpeta
#
# Una sola vez, y con permiso de administrador: Windows lo pide en una ventana. Hace falta
# internet solo durante la instalacion (unos 20 MB de descargas).
#
# Lo que hace, y por que:
#   - baja el Python 3.13 de Windows (el paquete "python" de nuget.org, que publica la Python
#     Software Foundation) y cada dependencia de PyPI, y no usa nada cuyo sha256 no sea
#     exactamente el fijado (fijado.json, requirements-windows.txt); python.exe y su DLL
#     ademas tienen que llevar la firma de la Python Software Foundation;
#   - pone un Python para cada papel (runtime\consola, lector, salida y orden): el cortafuegos
#     de Windows distingue los programas por su ruta. Un entorno virtual no valdria: su
#     python.exe arranca el de la base como otro proceso, y el cortafuegos veria siempre ese.
#     De cada uno solo queda un programa, python.exe: ni pythonw.exe ni los lanzadores de pip
#     y de venv, que serian programas sin reglas;
#   - cada uno con su python313._pth: solo ve su biblioteca, lib\ y app\src, y no hace caso
#     de PYTHONPATH ni de nada del registro;
#   - crea las reglas del cortafuegos (todas empiezan por "BMS Finanzas - "): la consola, el
#     lector y las ordenes sin red; la salida solo por el puerto 443;
#   - deja el programa de solo lectura para tu usuario; solo datos\ y buzon\ se pueden cambiar;
#   - al acabar, con tu usuario: los accesos del escritorio, la clave de la API (si quieres) y
#     la comprobacion del aislamiento.
param(
    [string]$Raiz = "C:\BMS",
    [string]$Usuario = "",
    [switch]$Elevado
)

. "$PSScriptRoot\comun.ps1"

$Proyecto = Split-Path $PSScriptRoot -Parent

# Lo unico que puede haber en la carpeta de instalacion: lo que deja bms-agent. Una carpeta asi
# se acepta aunque no tenga instalacion.json: es la que deja desinstalar.bat con tus datos
# (datos y buzon) o un intento de instalar que no acabo (instalacion.log, descargas, runtime...).
$DeLaInstalacion = @("instalacion.json", "instalacion.log", "descargas", "runtime", "lib", "app",
    "windows", "datos", "buzon")

function Validar-Raiz([string]$Texto) {
    if (-not [System.IO.Path]::IsPathRooted($Texto)) {
        Fallar "La carpeta de instalacion tiene que ser una ruta completa, como C:\BMS."
    }
    $completa = [System.IO.Path]::GetFullPath($Texto).TrimEnd("\")
    if ($completa.Length -le 3) { Fallar "No se instala en la raiz de un disco: usa una carpeta, como C:\BMS." }
    $unidad = [System.IO.Path]::GetPathRoot($completa)
    if (-not (Test-Path -LiteralPath $unidad)) { Fallar "No existe la unidad $unidad en este ordenador." }
    if ($completa -notmatch '^[A-Za-z]:\\[A-Za-z0-9_\\ .-]+$') {
        Fallar "La carpeta de instalacion solo puede llevar letras sin acentos, numeros, espacios, puntos y guiones."
    }
    if (Test-Path -LiteralPath $completa) {
        # Un enlace (o un hijo que lo es) llevaria lo que se instala a otra carpeta, que no
        # tendria los permisos de esta.
        if ((Get-Item -Force -LiteralPath $completa).Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            Fallar "$completa es un enlace a otra carpeta: elige una carpeta de verdad."
        }
        $dentro = @(Get-ChildItem -Force -LiteralPath $completa -ErrorAction SilentlyContinue)
        $ajenos = @($dentro | Where-Object { $DeLaInstalacion -notcontains $_.Name } | ForEach-Object { $_.Name })
        if ($ajenos.Count -gt 0) {
            Fallar ("$completa ya existe y no es una instalacion de bms-agent (tiene " + ($ajenos -join ", ") + "): elige otra carpeta.")
        }
        $enlaces = @($dentro | Where-Object { $_.Attributes -band [System.IO.FileAttributes]::ReparsePoint } | ForEach-Object { $_.Name })
        if ($enlaces.Count -gt 0) {
            Fallar ("En $completa, " + ($enlaces -join ", ") + " es un enlace a otra carpeta: borralo y vuelve a instalar.")
        }
    }
    return $completa
}

function Leer-Fijado {
    $fijado = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot "fijado.json") | ConvertFrom-Json
    if ($fijado.python.sha256 -notmatch '^[0-9a-f]{64}$') {
        Fallar "Falta el sha256 fijado del Python (windows\fijado.json): sin el no se descarga nada. Quien mantiene el programa lo fija con scripts\fijar_windows.py (docs/instalacion-nativa.md, 'Para quien mantiene el programa')."
    }
    if ($fijado.python.url -notmatch '^https://api\.nuget\.org/v3-flatcontainer/python/') {
        Fallar "El Python solo se baja de nuget.org (https://api.nuget.org/v3-flatcontainer/python/)."
    }
    return $fijado
}

function Leer-Requisitos {
    # requirements-windows.txt, con el formato de pip: nombre==version y sus --hash=sha256.
    # Una dependencia sin hash para todo: no se instala nada sin comprobar.
    $requisitos = @()
    $actual = $null
    foreach ($linea in (Get-Content -LiteralPath (Join-Path $PSScriptRoot "requirements-windows.txt"))) {
        $texto = ($linea -replace '#.*$', '').Trim().TrimEnd('\').Trim()
        if ($texto -eq "") { continue }
        if ($texto -match '^([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9_.+!-]+)') {
            $actual = [pscustomobject]@{ Nombre = $Matches[1]; Version = $Matches[2]; Hashes = @() }
            $requisitos += $actual
        }
        foreach ($m in [regex]::Matches($texto, '--hash=sha256:([0-9a-f]{64})')) {
            if ($null -eq $actual) { Fallar "requirements-windows.txt no se entiende." }
            $actual.Hashes += $m.Groups[1].Value
        }
    }
    $sinHash = @($requisitos | Where-Object { $_.Hashes.Count -eq 0 } | ForEach-Object { $_.Nombre })
    if ($sinHash.Count -gt 0) {
        Fallar ("Faltan los sha256 de " + ($sinHash -join ", ") + " en windows\requirements-windows.txt: sin ellos no se instala nada. Quien mantiene el programa los fija con scripts\fijar_windows.py.")
    }
    return $requisitos
}

function Crear-Accesos([string]$Raiz) {
    # Los accesos directos del escritorio de tu usuario (por eso, fuera de la parte de
    # administrador).
    $escritorio = [Environment]::GetFolderPath("Desktop")
    $shell = New-Object -ComObject WScript.Shell
    $accesos = @(
        @{ Nombre = "Abrir la consola"; Script = "iniciar.bat"; Argumentos = "" },
        @{ Nombre = "Datos de prueba"; Script = "iniciar.bat"; Argumentos = "-Demo" },
        @{ Nombre = "Parar"; Script = "parar.bat"; Argumentos = "" },
        @{ Nombre = "Importar el buzon"; Script = "importar.bat"; Argumentos = "" },
        @{ Nombre = "Leer facturas"; Script = "leer-facturas.bat"; Argumentos = "" },
        @{ Nombre = "Comprobar aislamiento"; Script = "comprobar.bat"; Argumentos = "" }
    )
    foreach ($a in $accesos) {
        $acceso = $shell.CreateShortcut((Join-Path $escritorio ($Prefijo + $a.Nombre + ".lnk")))
        $acceso.TargetPath = Join-Path $Raiz ("windows\" + $a.Script)
        $acceso.Arguments = $a.Argumentos
        $acceso.WorkingDirectory = Join-Path $Raiz "windows"
        $acceso.Save()
    }
    $buzon = $shell.CreateShortcut((Join-Path $escritorio ($Prefijo + "Buzon.lnk")))
    $buzon.TargetPath = Join-Path $Raiz "buzon"
    $buzon.Save()
}

# ---------------------------------------------------------------- la parte de tu usuario

$Raiz = Validar-Raiz $Raiz
if (-not (Test-Path -LiteralPath (Join-Path $Proyecto "src\bms_agent\cli.py"))) {
    Fallar "Abre instalar.bat desde la carpeta del proyecto (la que tiene src y config), no desde la instalacion."
}
# Sin los hashes fijados no se sigue, y antes de crear nada: asi un intento sin ellos no deja
# una carpeta a medias.
$null = Leer-Fijado
$null = @(Leer-Requisitos)
if (-not $Elevado) {
    $sid = Sid-Actual
    Escribir "Instalando bms-agent en $Raiz. Windows te va a pedir permiso de administrador (una vez)." "Cyan"
    $argumentos = Linea-De-Argumentos @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath,
        "-Raiz", $Raiz, "-Usuario", $sid, "-Elevado")
    try {
        $proceso = Start-Process -FilePath (Get-Process -Id $PID).Path -ArgumentList $argumentos `
            -Verb RunAs -Wait -PassThru
    } catch {
        Fallar "Sin permiso de administrador no se puede instalar: las reglas del cortafuegos lo necesitan. Vuelve a abrir instalar.bat y di que si."
    }
    if ($proceso.ExitCode -ne 0) {
        Fallar ("La instalacion no ha terminado bien. Lo que ha pasado esta en " + (Join-Path $Raiz "instalacion.log"))
    }
    Crear-Accesos $Raiz
    Escribir ""
    Escribir "Instalado en $Raiz, con sus accesos en el escritorio (BMS Finanzas - ...)." "Green"
    $respuesta = Read-Host "Quieres guardar ahora la clave de la API? (escribe si; tambien se puede luego con clave.bat)"
    if (Es-Si $respuesta) {
        & (Join-Path $Raiz "windows\clave.ps1")
    }
    Escribir ""
    Escribir "Comprobando el aislamiento (lo mismo que comprobar.bat)..." "Cyan"
    & (Join-Path $Raiz "windows\comprobar.ps1")
    Escribir ""
    Escribir "Siguiente paso: tu token personal (persona.bat) y la empresa (empresa.bat), como dice docs/instalacion-nativa.md." "Cyan"
    exit 0
}

# ---------------------------------------------------------------- la parte de administrador

# Aqui un fallo no cierra la ventana sin mas: se dice, se apunta y se espera a que lo leas.
function Fallar([string]$Texto) { throw $Texto }

function Descargar-Verificado([string]$Url, [string]$Sha256, [string]$Destino) {
    # Lo unico de este instalador que trae algo de fuera. Si esta en windows\paquetes (un
    # paquete preparado sin internet), de ahi; si no, de la direccion fijada. Lo traido no se
    # usa si su sha256 no es exactamente el fijado: se borra y se para.
    $local = Join-Path (Join-Path $PSScriptRoot "paquetes") (Split-Path $Destino -Leaf)
    if (Test-Path -LiteralPath $local) {
        Copy-Item -LiteralPath $local -Destination $Destino -Force
    } else {
        if ($Url -notmatch '^https://') { Fallar "Solo se descarga por https: $Url" }
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destino -ErrorAction Stop
    }
    $real = (Get-FileHash -Algorithm SHA256 -LiteralPath $Destino).Hash.ToLower()
    if ($real -ne $Sha256.ToLower()) {
        Remove-Item -LiteralPath $Destino -Force -ErrorAction SilentlyContinue
        Fallar ("Lo traido para " + (Split-Path $Destino -Leaf) + " no es lo fijado (su sha256 es " + $real + "): no se instala nada con ello.")
    }
}

function Rueda-De($Requisito) {
    # La rueda cuyo sha256 es uno de los fijados: el hash decide el fichero, no su nombre.
    $paquetes = Join-Path $PSScriptRoot "paquetes"
    if (Test-Path -LiteralPath $paquetes) {
        foreach ($f in (Get-ChildItem -File -LiteralPath $paquetes -Filter *.whl)) {
            $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $f.FullName).Hash.ToLower()
            if ($Requisito.Hashes -contains $hash) {
                return [pscustomobject]@{ Nombre = $f.Name; Url = ""; Sha256 = $hash }
            }
        }
    }
    $meta = Invoke-RestMethod -UseBasicParsing -ErrorAction Stop `
        -Uri ("https://pypi.org/pypi/" + $Requisito.Nombre + "/" + $Requisito.Version + "/json")
    foreach ($fichero in $meta.urls) {
        if ($fichero.filename -like "*.whl" -and ($Requisito.Hashes -contains $fichero.digests.sha256) -and
            $fichero.url -match '^https://files\.pythonhosted\.org/') {
            return [pscustomobject]@{ Nombre = $fichero.filename; Url = $fichero.url; Sha256 = $fichero.digests.sha256 }
        }
    }
    Fallar ("En PyPI no esta la rueda fijada de " + $Requisito.Nombre + " " + $Requisito.Version + ".")
}

function Comprobar-Firma([string]$Fichero, [string]$Firmante) {
    # Ademas del hash: python.exe y su DLL van firmados (Authenticode, con sello de tiempo) por
    # la Python Software Foundation. Se compara el nombre entero del firmante (su CN), no un
    # trozo del texto del certificado.
    $firma = Get-AuthenticodeSignature -FilePath $Fichero
    $nombre = ""
    if ($null -ne $firma.SignerCertificate) {
        $nombre = $firma.SignerCertificate.GetNameInfo([System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false)
    }
    if ($firma.Status -ne "Valid" -or $nombre -cne $Firmante) {
        Fallar ("$Fichero no lleva una firma valida de " + $Firmante + ": no se instala.")
    }
}

function Destino-En-Runtime([string]$Entrada) {
    # Donde va una entrada del paquete de NuGet dentro de runtime\<papel> (con "/"), o $null si
    # no va: lo mismo que nativo.destino_en_runtime (los tests comparan los dos con el mismo
    # paquete). Solo tools/, sin lo de $FueraDelRuntime, sin distinguir mayusculas. Una ruta con
    # "..", "\", ":" o absoluta no es de un paquete bueno: se para sin abrir nada.
    $partes = $Entrada.Split("/")
    $mala = $Entrada.StartsWith("/") -or $Entrada.Contains("\") -or $Entrada.Contains(":")
    for ($i = 0; $i -lt $partes.Count; $i++) {
        if ($partes[$i] -eq ".." -or $partes[$i] -eq "." -or ($partes[$i] -eq "" -and $i -lt $partes.Count - 1)) {
            $mala = $true
        }
    }
    if ($mala) { Fallar ("El paquete de Python trae una ruta que no vale (" + $Entrada + "): no se instala.") }
    $minusculas = $Entrada.ToLowerInvariant()
    if (-not $minusculas.StartsWith($CarpetaDelPaquete, [System.StringComparison]::Ordinal) -or $Entrada.EndsWith("/")) {
        return $null
    }
    $resto = $Entrada.Substring($CarpetaDelPaquete.Length)
    if ($resto -eq "") { return $null }
    $restoMinusculas = $resto.ToLowerInvariant()
    foreach ($fuera in $FueraDelRuntime) {
        $f = $fuera.ToLowerInvariant()
        if ($f.EndsWith("/")) {
            if ($restoMinusculas.StartsWith($f, [System.StringComparison]::Ordinal)) { return $null }
        } elseif ($restoMinusculas -eq $f) {
            return $null
        }
    }
    return $resto
}

function Comprobar-Runtime([string]$Carpeta) {
    # En la carpeta de un Python, un solo programa: python.exe (otro .exe seria un programa sin
    # reglas del cortafuegos). Y lo necesario para arrancar: si falta, el paquete no es el
    # esperado.
    $Carpeta = [System.IO.Path]::GetFullPath($Carpeta)
    $programas = @(Get-ChildItem -Recurse -File -Force -LiteralPath $Carpeta |
        Where-Object { @(".exe", ".com", ".scr") -contains $_.Extension.ToLowerInvariant() })
    if ($programas.Count -ne 1 -or $programas[0].FullName -ne (Join-Path $Carpeta "python.exe")) {
        Fallar ("En " + $Carpeta + " tiene que haber un solo programa, python.exe, y hay: " + (($programas | ForEach-Object { $_.FullName }) -join ", ") + ". No se instala.")
    }
    foreach ($necesario in $NecesariosDelRuntime) {
        if (-not (Test-Path -LiteralPath (Join-Path $Carpeta $necesario))) {
            Fallar ("Al Python de " + $Carpeta + " le falta " + $necesario + ": el paquete no es el esperado. No se instala.")
        }
    }
}

function Abrir-Python([string]$Paquete, [string]$Destino) {
    # El paquete de NuGet es un zip. Se abre con .NET, entrada a entrada, y no con
    # Expand-Archive: solo lo que dice Destino-En-Runtime, nada fuera de $Destino, sin depender
    # de la extension (.nupkg) ni de como trate los corchetes de [Content_Types].xml (en
    # PowerShell, comodines).
    Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
    $carpeta = [System.IO.Path]::GetFullPath($Destino)
    Remove-Item -Recurse -Force -LiteralPath $carpeta -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $carpeta | Out-Null
    $zip = [System.IO.Compression.ZipFile]::OpenRead($Paquete)
    try {
        foreach ($entrada in $zip.Entries) {
            $relativa = Destino-En-Runtime $entrada.FullName
            if ($null -eq $relativa) { continue }
            $ruta = [System.IO.Path]::GetFullPath((Join-Path $carpeta $relativa))
            if (-not $ruta.StartsWith($carpeta + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
                Fallar ("El paquete de Python trae una ruta que no vale (" + $entrada.FullName + "): no se instala.")
            }
            New-Item -ItemType Directory -Force -Path (Split-Path $ruta -Parent) | Out-Null
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entrada, $ruta, $true)
        }
    } finally {
        $zip.Dispose()
    }
    Comprobar-Runtime $carpeta
}

function Escribir-Pth([string]$Carpeta) {
    # Junto a python313.dll. Con este fichero Python no mira PYTHONPATH, PYTHONHOME ni el
    # registro, entra en modo aislado y no importa site (ni site-packages ni la carpeta del
    # usuario): solo ve su biblioteca (Lib y DLLs), las dependencias (..\..\lib) y el codigo de
    # la app (..\..\app\src). Lo mismo que nativo.contenido_pth.
    [System.IO.File]::WriteAllText((Join-Path $Carpeta $FicheroPth),
        (($RutasPth -join "`r`n") + "`r`n"), [System.Text.Encoding]::ASCII)
}

function Icacls([string[]]$Argumentos) {
    & icacls.exe @Argumentos | Out-Null
    if ($LASTEXITCODE -ne 0) { Fallar ("No se han podido poner los permisos (icacls " + ($Argumentos -join " ") + ").") }
}

function Cerrar-Raiz([string]$Raiz, [string]$Sid) {
    # Lo primero de la parte de administrador, antes de bajar, copiar o ejecutar nada: la raiz,
    # de los administradores, y tu usuario solo lee. Lo que se crea dentro lo hereda. Sin
    # esto, bajo C:\ (que deja a cualquier usuario crear y cambiar ficheros) lo bajado se
    # podria cambiar despues de comprobar su sha256, y el paso 5 ejecutaria como administrador
    # codigo de una carpeta que cualquiera escribe.
    $sistema = "*S-1-5-18"
    $administradores = "*S-1-5-32-544"
    $nuestros = @("S-1-5-18", "S-1-5-32-544", $Sid)
    if ((Get-Item -Force -LiteralPath $Raiz).Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        Fallar "$Raiz es un enlace a otra carpeta: no se instala ahi."
    }
    Icacls @($Raiz, "/setowner", $administradores, "/T", "/C", "/Q")
    Icacls @($Raiz, "/inheritance:r", "/grant:r", ($sistema + ":(OI)(CI)F"),
        ($administradores + ":(OI)(CI)F"), ("*" + $Sid + ":(OI)(CI)RX"), "/Q")
    # /inheritance:r deja los permisos puestos a mano (Todos: control total, por ejemplo): fuera
    # todo permiso que no sea de estos tres.
    foreach ($regla in @((Get-Acl -LiteralPath $Raiz).Access | Where-Object { -not $_.IsInherited -and "$($_.AccessControlType)" -eq "Allow" })) {
        $quien = $regla.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
        if ($nuestros -notcontains $quien) { Icacls @($Raiz, "/remove:g", ("*" + $quien), "/Q") }
    }
    $quedan = @((Get-Acl -LiteralPath $Raiz).Access | Where-Object { "$($_.AccessControlType)" -eq "Allow" } |
        ForEach-Object { $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value } |
        Where-Object { $nuestros -notcontains $_ })
    if ($quedan.Count -gt 0) { Fallar ("La carpeta $Raiz tiene permisos de " + ($quedan -join ", ") + " que no se pueden quitar: elige otra carpeta.") }
    # Lo que ya habia del programa (de una instalacion anterior o de un intento que no acabo)
    # pasa a heredar de la raiz; los datos y el buzon tienen los suyos, solo para tu usuario.
    foreach ($hijo in @(Get-ChildItem -Force -LiteralPath $Raiz)) {
        if ($hijo.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            Fallar ("En $Raiz, " + $hijo.Name + " es un enlace a otra carpeta: borralo y vuelve a instalar.")
        }
        if (@("datos", "buzon") -notcontains $hijo.Name) {
            Icacls @($hijo.FullName, "/reset", "/T", "/C", "/Q")
        }
    }
}

function Poner-Permisos([string]$Raiz, [string]$Sid) {
    $sistema = "*S-1-5-18"
    $administradores = "*S-1-5-32-544"
    $usuario = "*" + $Sid
    # El dueno de todo, los administradores: tu usuario no puede cambiarse los permisos del codigo.
    Icacls @($Raiz, "/setowner", $administradores, "/T", "/C", "/Q")
    # La raiz y lo que cuelga de ella (app, lib, runtime, windows): leer y ejecutar, nada mas.
    # Sin la herencia de C:\, que deja a cualquier usuario crear y cambiar ficheros.
    Icacls @($Raiz, "/inheritance:r", "/grant:r", ($sistema + ":(OI)(CI)F"),
        ($administradores + ":(OI)(CI)F"), ($usuario + ":(OI)(CI)RX"), "/Q")
    foreach ($hijo in @("app", "lib", "runtime", "windows")) {
        Icacls @((Join-Path $Raiz $hijo), "/reset", "/T", "/C", "/Q")
    }
    # Los datos y el buzon: tu usuario puede cambiar lo que hay dentro. Nadie mas que el.
    foreach ($hijo in @("datos", "buzon")) {
        $ruta = Join-Path $Raiz $hijo
        Icacls @($ruta, "/inheritance:r", "/grant:r", ($sistema + ":(OI)(CI)F"),
            ($administradores + ":(OI)(CI)F"), ($usuario + ":(OI)(CI)M"), "/Q")
        if (@(Get-ChildItem -Force -LiteralPath $ruta).Count -gt 0) {
            Icacls @((Join-Path $ruta "*"), "/reset", "/T", "/C", "/Q")
        }
    }
}

function Crear-Reglas([string]$Raiz) {
    Quitar-Reglas
    foreach ($regla in (Reglas-Del-Cortafuegos $Raiz)) {
        $parametros = @{
            DisplayName = $regla.Nombre
            Group       = $Grupo
            Description = "bms-agent: aislamiento por programa (docs/instalacion-nativa.md)"
            Direction   = $regla.Direccion
            Action      = $regla.Accion
            Program     = $regla.Programa
            Profile     = "Any"
            Enabled     = "True"
        }
        if ($regla.Protocolo) { $parametros["Protocol"] = $regla.Protocolo }
        if ($regla.Puertos.Count -gt 0) { $parametros["RemotePort"] = $regla.Puertos }
        New-NetFirewallRule @parametros -ErrorAction Stop | Out-Null
    }
}

function Instalar([string]$Raiz, [string]$Sid) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $fijado = Leer-Fijado
    $requisitos = @(Leer-Requisitos)
    $script:Inst = [pscustomobject]@{ Raiz = $Raiz; PuertoConsola = 8765; PuertoSalida = 3128 }
    foreach ($rol in $Roles) { Parar-Rol $rol }
    $descargas = Join-Path $Raiz "descargas"
    Remove-Item -Recurse -Force -LiteralPath $descargas -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $descargas | Out-Null

    Escribir ("1/7 Python " + $fijado.python.version + ", el de la Python Software Foundation en nuget.org (comprobado por su sha256 y su firma)...") "Cyan"
    $paquete = Join-Path $descargas $fijado.python.fichero
    Descargar-Verificado $fijado.python.url $fijado.python.sha256 $paquete
    $base = Join-Path $descargas "python"
    Abrir-Python $paquete $base
    foreach ($nombre in @("python.exe", $DllPython)) {
        Comprobar-Firma (Join-Path $base $nombre) $fijado.python.firmante
    }

    Escribir "2/7 Un Python para cada papel: consola, lector, salida y orden..." "Cyan"
    foreach ($rol in $Roles) {
        $destino = Join-Path $Raiz ("runtime\" + $rol)
        Remove-Item -Recurse -Force -LiteralPath $destino -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Force -Path $destino | Out-Null
        Copy-Item -Path (Join-Path $base "*") -Destination $destino -Recurse -Force
        Escribir-Pth $destino
        # Un solo programa por papel: python.exe, el de sus reglas.
        Comprobar-Runtime $destino
    }

    Escribir "3/7 Las dependencias (cada rueda comprobada por su sha256)..." "Cyan"
    $lib = Join-Path $Raiz "lib"
    Remove-Item -Recurse -Force -LiteralPath $lib -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $lib | Out-Null
    foreach ($requisito in $requisitos) {
        $rueda = Rueda-De $requisito
        $fichero = Join-Path $descargas $rueda.Nombre
        Descargar-Verificado $rueda.Url $rueda.Sha256 $fichero
        # Una rueda es un zip; instalarla es abrirla en lib\ (lo que haria pip --target). Una
        # con .data (scripts, cabeceras) no se sabe poner asi, y se para.
        $comoZip = $fichero + ".zip"
        Copy-Item -LiteralPath $fichero -Destination $comoZip -Force
        Expand-Archive -LiteralPath $comoZip -DestinationPath $lib -Force
        Remove-Item -LiteralPath $comoZip -Force
    }
    if (@(Get-ChildItem -Directory -LiteralPath $lib -Filter "*.data").Count -gt 0) {
        Fallar "Una dependencia trae una carpeta .data: no se sabe instalar sin pip."
    }

    Escribir "4/7 El programa..." "Cyan"
    $app = Join-Path $Raiz "app"
    Remove-Item -Recurse -Force -LiteralPath $app -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path (Join-Path $app "src") | Out-Null
    Copy-Item -Recurse -Force -Path (Join-Path $Proyecto "src\bms_agent") -Destination (Join-Path $app "src")
    Copy-Item -Recurse -Force -Path (Join-Path $Proyecto "config") -Destination $app
    # Las tarifas de verdad no van con el programa (como en Docker): entran por el buzon.
    Remove-Item -Force -LiteralPath (Join-Path $app "config\tarifas.yaml") -ErrorAction SilentlyContinue
    foreach ($nombre in @("pyproject.toml", "README.md")) {
        Copy-Item -Force -LiteralPath (Join-Path $Proyecto $nombre) -Destination $app
    }
    Get-ChildItem -Recurse -Directory -LiteralPath $app -Filter "__pycache__" |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    $scripts = Join-Path $Raiz "windows"
    Remove-Item -Recurse -Force -LiteralPath $scripts -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $scripts | Out-Null
    foreach ($patron in @("*.ps1", "*.bat", "fijado.json", "requirements-windows.txt", "LEEME.txt")) {
        Copy-Item -Force -Path (Join-Path $PSScriptRoot $patron) -Destination $scripts
    }
    # Lo copiado de una descarga lleva la marca de "viene de internet"; el programa no.
    foreach ($carpeta in @("app", "lib", "runtime", "windows")) {
        Get-ChildItem -Recurse -File -LiteralPath (Join-Path $Raiz $carpeta) |
            Unblock-File -ErrorAction SilentlyContinue
    }

    Escribir "5/7 Preparando y probando el programa..." "Cyan"
    $orden = Join-Path $Raiz "runtime\orden\python.exe"
    # La biblioteca del paquete de NuGet viene sin compilar: se compila aqui, una vez, porque
    # despues tu usuario no puede escribir en runtime\ (y cada arranque la compilaria otra vez).
    # Con checked-hash, un .pyc solo vale si el .py es el mismo.
    $bibliotecas = @($Roles | ForEach-Object { Join-Path $Raiz ("runtime\" + $_ + "\Lib") })
    & $orden -X utf8 -m compileall -q --invalidation-mode checked-hash @bibliotecas | Out-Null
    & $orden -X utf8 -m compileall -q (Join-Path $app "src") $lib | Out-Null
    # Que el ._pth vale de verdad: modo aislado, sin site, y la version fijada.
    & $orden -X utf8 -c ("import sys, sqlite3, anthropic, pydantic, yaml, tzdata, bms_agent.cli; " +
        "assert sys.flags.isolated == 1 and sys.flags.no_site == 1 and 'site' not in sys.modules, 'el ._pth no se aplica'; " +
        "assert '%d.%d.%d' % sys.version_info[:3] == '" + $fijado.python.version + "', sys.version; " +
        "print('   Python', sys.version.split()[0], '- SQLite', sqlite3.sqlite_version)") | Out-Host
    if ($LASTEXITCODE -ne 0) { Fallar "El programa no arranca con lo instalado. Mira el mensaje de arriba." }

    Escribir "6/7 Las carpetas de tus datos y del buzon..." "Cyan"
    foreach ($carpeta in @("datos", "datos\secretos", "datos\out", "datos\registro-salida", "buzon",
                           "buzon\facturas", "buzon\hecho")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $Raiz $carpeta) | Out-Null
    }
    foreach ($carpeta in (Carpetas-Del-Buzon).Keys) {
        New-Item -ItemType Directory -Force -Path (Join-Path $Raiz ("buzon\" + $carpeta)) | Out-Null
    }
    $instalacion = [ordered]@{
        version        = 1
        puerto_consola = 8765
        puerto_salida  = 3128
        python         = $fijado.python.version
        instalado      = (Get-Date).ToString("s")
        reglas         = @(Reglas-Del-Cortafuegos $Raiz | ForEach-Object { $_.Nombre })
    }
    [System.IO.File]::WriteAllText((Join-Path $Raiz "instalacion.json"), ($instalacion | ConvertTo-Json),
        (New-Object System.Text.UTF8Encoding $false))

    Escribir "7/7 El cortafuegos de Windows y los permisos de las carpetas..." "Cyan"
    Crear-Reglas $Raiz
    # Enabled no es un booleano (es GpoBoolean, o un numero): se compara como texto.
    $apagados = @(Get-NetFirewallProfile | Where-Object { @("True", "1") -notcontains ("" + $_.Enabled) })
    if ($apagados.Count -gt 0) {
        Escribir ("ATENCION: el cortafuegos de Windows esta apagado en " + (($apagados | ForEach-Object { $_.Name }) -join ", ") + ". Sin el, las reglas no hacen nada: enciendelo (Seguridad de Windows, Firewall y proteccion de red).") "Red"
    }
    Remove-Item -Recurse -Force -LiteralPath $descargas -ErrorAction SilentlyContinue
    Poner-Permisos $Raiz $Sid
}

if (-not (Es-Administrador)) {
    Write-Host "Esta parte necesita permiso de administrador." -ForegroundColor Red
    exit 1
}
if ($Usuario -notmatch '^S-1-(5-21|12-1)(-\d+)+$') {
    Write-Host "Falta el usuario para el que se instala: abre instalar.bat con doble clic." -ForegroundColor Red
    exit 1
}
$bien = $false
$apuntando = $false
try {
    New-Item -ItemType Directory -Force -Path $Raiz | Out-Null
    Cerrar-Raiz $Raiz $Usuario
    Start-Transcript -Path (Join-Path $Raiz "instalacion.log") -Force | Out-Null
    $apuntando = $true
    Instalar $Raiz $Usuario
    $bien = $true
} catch {
    Write-Host ""
    Write-Host ("No se ha instalado: " + $_.Exception.Message) -ForegroundColor Red
} finally {
    if ($apuntando) { Stop-Transcript | Out-Null }
}
if (-not $bien) {
    Read-Host "Pulsa Intro para cerrar esta ventana"
    exit 1
}
Write-Host "Hecho. Esta ventana se cierra sola." -ForegroundColor Green
Start-Sleep -Seconds 2
exit 0
