# El Mac por el mini PC (paso 18b, docs/entorno-local.md "Usarlo desde un Mac"): el tunel SSH
# que deja al navegador de un Mac de la misma red abrir la app de este equipo. Solo en la
# variante Docker.
#
#   .\mac.bat -CopiarParaElMac E:\   copia lo del Mac (la carpeta mac\) a la memoria USB, despues
#                                    de comprobar que ninguna otra cuenta lo ha podido cambiar
#   .\mac.bat -Instalar      el servidor OpenSSH de Windows, la cuenta del tunel, su
#                            configuracion y el cortafuegos (y, si quieres, el primer Mac)
#   .\mac.bat -AnadirClave   anade un Mac (o le cambia la IP o la clave): nombre, IP y clave
#   .\mac.bat -QuitarClave   quita un Mac: deja de poder entrar en el acto
#   .\mac.bat -Estado        como esta todo, sin cambiar nada
#   .\mac.bat -Apagar        cierra el tunel sin desinstalar nada (si un tiempo no se usa)
#   .\mac.bat -Encender      lo vuelve a abrir
#   .\mac.bat -Quitar        lo deshace todo y deja el equipo como estaba
#
# El tunel solo deja una cosa: que un Mac de la lista, con su clave y desde su IP, abra
# 127.0.0.1:8765 de este equipo. Ni consola, ni ficheros, ni otro puerto, ni salir a internet.
# La app no cambia. Este script no usa Docker ni toca el programa: no pausa nada.
# Windows PowerShell 5.1, todo en ASCII. No carga comun.ps1: corre como administrador y
# cuantos menos ficheros haya que fiarse, mejor (Escribir, Es-Si y Es-Administrador son copia de
# los de alli). Lo que hay que preguntar del Mac se pregunta antes de pedir ser administrador: la
# ventana de administrador no recibe ficheros arrastrados.
param(
    [switch]$Instalar,
    [switch]$AnadirClave,
    [switch]$QuitarClave,
    [switch]$Estado,
    [switch]$Apagar,
    [switch]$Encender,
    [switch]$Quitar,
    [string]$CopiarParaElMac = "",
    [string]$Nombre = "",
    [string]$Ip = "",
    [string]$Clave = "",
    [switch]$MismaClave,
    [switch]$SustituirConfiguracion,
    [switch]$Elevado,
    [string]$Usuario = ""
)

$ErrorActionPreference = "Continue"

$Cuenta = "bms-tunel"
$PuertoApp = 8765
$Capacidad = "OpenSSH.Server~~~~0.0.1.0"
$CarpetaSsh = Join-Path $env:ProgramData "ssh"
$Config = Join-Path $CarpetaSsh "sshd_config"
$ConfigAntes = Join-Path $CarpetaSsh "sshd_config.antes-bms"
$ConfigNueva = Join-Path $CarpetaSsh "sshd_config.bms-nueva"
$FicheroClaves = Join-Path $CarpetaSsh "bms_tunel_authorized_keys"
$ClaveDeEstado = "HKLM:\SOFTWARE\bms-agent\TunelMac"
$ClaveDelEquipo = Join-Path $CarpetaSsh "ssh_host_ed25519_key.pub"
$ProgramasSsh = Join-Path $env:SystemRoot "System32\OpenSSH"
$Sshd = Join-Path $ProgramasSsh "sshd.exe"
$ConfigDeFabrica = Join-Path $ProgramasSsh "sshd_config_default"
$ReglaMac = "BMS-Tunel-Mac-sshd"
$ReglaResto = "BMS-Tunel-Mac-sshd-resto"
$ReglaMicrosoft = "OpenSSH-Server-In-TCP"
$Marca = "# bms-agent: tunel del Mac (mac.ps1)."
$ListaDeInicio = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList"
# Las herramientas del sistema, por su ruta: cmd y PowerShell no buscan asi en la carpeta actual.
$Icacls = Join-Path $env:SystemRoot "System32\icacls.exe"
$Taskkill = Join-Path $env:SystemRoot "System32\taskkill.exe"
$Secedit = Join-Path $env:SystemRoot "System32\secedit.exe"
$Takeown = Join-Path $env:SystemRoot "System32\takeown.exe"
# Lo que va al Mac (la carpeta mac\ del proyecto), y solo por -CopiarParaElMac.
$CarpetaDelMac = Join-Path (Split-Path -Parent $PSScriptRoot) "mac"
$FicherosDelMac = @("preparar.command", "abrir-bms.command", "LEEME.txt")
# Por SID y nunca por nombre: en un Windows en neerlandes "Users" es "Gebruikers".
$SidSistema = "S-1-5-18"
$SidAdministradores = "S-1-5-32-544"
$SidTrustedInstaller = "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"
$PatronNombre = '^[a-z0-9][a-z0-9-]{0,30}$'
$DerechosNegados = @("SeDenyInteractiveLogonRight", "SeDenyRemoteInteractiveLogonRight",
    "SeDenyBatchLogonRight", "SeDenyServiceLogonRight")
# Los grupos que lleva cualquier inicio de sesion de red de una cuenta local (el S4U de sshd):
# Todos, Usuarios autenticados, Usuarios (que contiene a Usuarios autenticados), Red y Cuenta local.
$SidesDeCualquiera = @("S-1-1-0", "S-1-5-11", "S-1-5-32-545", "S-1-5-2", "S-1-5-113")
# Los procesos de un tunel que Windows no deja cortar (Aplicar).
$Quedan = 0

# ---------------------------------------------------------------- ayudas (como comun.ps1)

function Escribir([string]$Texto, [string]$Color = "Gray") {
    Write-Host $Texto -ForegroundColor $Color
}

function Esperar-Intro {
    # La ventana de administrador se cierra al acabar: que se pueda leer antes.
    if ($Elevado) { Read-Host "Pulsa Intro para cerrar esta ventana" | Out-Null }
}

function Fallar([string]$Texto) {
    Write-Host ""
    Write-Host $Texto -ForegroundColor Red
    Write-Host ""
    Esperar-Intro
    exit 1
}

function Es-Si([string]$Respuesta) {
    # "si", "si con tilde" o "s", en mayusculas o no. La tilde se compara por su codigo.
    $texto = ("" + $Respuesta).Trim().ToLower().Replace([string][char]0x00ED, "i")
    return ($texto -eq "si" -or $texto -eq "s")
}

function Es-Administrador {
    $yo = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    return $yo.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Escribir-Ascii([string]$Ruta, [string]$Texto) {
    # Sin BOM y con LF: sshd leeria un BOM como parte de la primera linea. Nunca Out-File
    # ni Set-Content (en 5.1, Out-File escribe UTF-16).
    [IO.File]::WriteAllText($Ruta, $Texto, (New-Object Text.UTF8Encoding($false)))
}

# ---------------------------------------------------------------- lo que se puede probar fuera

function Numero-De-Ip([string]$Ip) {
    $o = $Ip.Split(".")
    return ([int64]$o[0] * 16777216) + ([int64]$o[1] * 65536) + ([int64]$o[2] * 256) + [int64]$o[3]
}

function Ip-De-Numero([int64]$N) {
    return ("{0}.{1}.{2}.{3}" -f [int64][math]::Floor($N / 16777216), ([int64][math]::Floor($N / 65536) % 256),
        ([int64][math]::Floor($N / 256) % 256), ($N % 256))
}

function Ip-Valida([string]$Texto) {
    # Una IPv4 de red privada (10/8, 172.16/12, 192.168/16), sin ceros de mas. Ni nombres, ni
    # rangos, ni listas, ni IPv6: va tal cual a sshd_config, a la clave y al cortafuegos.
    $t = ("" + $Texto).Trim()
    if ($t -notmatch '^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$') { return $null }
    $o = @([int]$Matches[1], [int]$Matches[2], [int]$Matches[3], [int]$Matches[4])
    foreach ($x in $o) { if ($x -gt 255) { return $null } }
    $normal = ($o -join ".")
    if ($normal -ne $t) { return $null }
    $privada = ($o[0] -eq 10) -or ($o[0] -eq 172 -and $o[1] -ge 16 -and $o[1] -le 31) -or
        ($o[0] -eq 192 -and $o[1] -eq 168)
    if (-not $privada) { return $null }
    if ($o[3] -eq 0 -or $o[3] -eq 255) { return $null }
    return $normal
}

function Red-De([string]$Ip, [int]$Prefijo) {
    # La red entera de una IP ("red", la reserva si no se puede fijar la IP del Mac).
    if ($null -eq (Ip-Valida $Ip) -or $Prefijo -lt 16 -or $Prefijo -gt 30) { return $null }
    $tam = [int64][math]::Pow(2, 32 - $Prefijo)
    $inicio = [int64][math]::Floor((Numero-De-Ip $Ip) / $tam) * $tam
    return ((Ip-De-Numero $inicio) + "/" + $Prefijo)
}

function Origen-Valido([string]$Texto) {
    # Lo que llega de la ventana normal: una IP privada (Ip-Valida) o, con la reserva "red", la
    # red que da Red-De (a.b.c.0/n, de 16 a 30). Se rehace y se compara: nada mas pasa.
    $t = ("" + $Texto).Trim()
    if ($t -notmatch '^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})/(\d{1,2})$') { return (Ip-Valida $t) }
    $base = $Matches[1]
    $prefijo = [int]$Matches[2]
    foreach ($x in $base.Split(".")) { if ([int]$x -gt 255) { return $null } }
    $red = Red-De (Ip-De-Numero ((Numero-De-Ip $base) + 1)) $prefijo
    if ($red -ne $t) { return $null }
    return $red
}

function Rango-De([string]$Origen) {
    # "a.b.c.d" o "a.b.c.d/nn" como [inicio, fin].
    $partes = $Origen.Split("/")
    $n = Numero-De-Ip $partes[0]
    if ($partes.Count -eq 1) { return @($n, $n) }
    $tam = [int64][math]::Pow(2, 32 - [int]$partes[1])
    return @($n, ($n + $tam - 1))
}

function Resto-De([string[]]$Origenes) {
    # Todo IPv4 menos los Mac: lo que bloquea la regla "resto" aunque otra regla dejara pasar.
    $rangos = @($Origenes | ForEach-Object { , (Rango-De $_) } | Sort-Object { $_[0] })
    $resto = @()
    $siguiente = [int64]0
    foreach ($r in $rangos) {
        if ($r[0] -gt $siguiente) {
            $resto += ((Ip-De-Numero $siguiente) + "-" + (Ip-De-Numero ($r[0] - 1)))
        }
        if ($r[1] + 1 -gt $siguiente) { $siguiente = $r[1] + 1 }
    }
    if ($siguiente -le 4294967295) { $resto += ((Ip-De-Numero $siguiente) + "-255.255.255.255") }
    return $resto
}

function Clave-Publica-Valida([string]$Linea) {
    # Solo "ssh-ed25519 <base64> [comentario]", sin opciones delante: las opciones las pone
    # este script, nunca lo pegado. El blob son 51 bytes: 4+11 ("ssh-ed25519") y 4+32.
    $t = ("" + $Linea).Trim()
    if ($t -notmatch '^ssh-ed25519 ([A-Za-z0-9+/]{68})( [ -~]{0,200})?$') { return $null }
    $b64 = $Matches[1]
    try { $blob = [Convert]::FromBase64String($b64) } catch { return $null }
    if ($blob.Length -ne 51) { return $null }
    if ($blob[0] -ne 0 -or $blob[1] -ne 0 -or $blob[2] -ne 0 -or $blob[3] -ne 11) { return $null }
    if ([Text.Encoding]::ASCII.GetString($blob, 4, 11) -ne "ssh-ed25519") { return $null }
    if ($blob[15] -ne 0 -or $blob[16] -ne 0 -or $blob[17] -ne 0 -or $blob[18] -ne 32) { return $null }
    return ("ssh-ed25519 " + $b64)
}

function Huella-Sha256([string]$Linea) {
    # Como "ssh-keygen -l -E sha256": SHA-256 del blob, en base64 sin los "=" del final.
    $partes = ("" + $Linea).Trim() -split '\s+'
    $blob = [Convert]::FromBase64String($partes[1])
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $h = $sha.ComputeHash($blob) } finally { $sha.Dispose() }
    return ("SHA256:" + [Convert]::ToBase64String($h).TrimEnd("="))
}

function Linea-De-Clave($Mac) {
    return ('restrict,port-forwarding,permitopen="127.0.0.1:' + $PuertoApp + '",from="' + $Mac.ip +
        '",command="exit 1" ' + $Mac.clave + ' bms-' + $Mac.nombre)
}

function Texto-Claves([object[]]$Macs) {
    $lineas = @("# bms-agent: las claves de los Mac (mac.ps1). No lo cambies a mano: lo rehace mac.bat.")
    foreach ($m in $Macs) { $lineas += (Linea-De-Clave $m) }
    return (($lineas -join "`n") + "`n")
}

function Texto-Config([object[]]$Macs) {
    if ($Macs.Count -eq 0) {
        $quien = "DenyUsers *"
    } else {
        $quien = "AllowUsers " + ((@($Macs | ForEach-Object { $Cuenta + "@" + $_.ip })) -join " ")
    }
    $lineas = @(
        $Marca,
        "# No lo cambies a mano: lo rehace mac.bat. El de antes esta en sshd_config.antes-bms.",
        "# Solo deja que los Mac de la lista abran 127.0.0.1:$PuertoApp de este equipo, con su",
        "# clave y desde su IP. Ni consola, ni ficheros, ni otro destino.",
        "",
        "Port 22",
        "AddressFamily inet",
        "HostKey __PROGRAMDATA__/ssh/ssh_host_ed25519_key",
        "SyslogFacility AUTH",
        "LogLevel VERBOSE",
        "",
        $quien,
        "AuthenticationMethods publickey",
        "PubkeyAuthentication yes",
        "PubkeyAcceptedAlgorithms ssh-ed25519",
        "PasswordAuthentication no",
        "PermitEmptyPasswords no",
        "AuthorizedKeysFile none",
        "LoginGraceTime 30",
        "MaxAuthTries 3",
        "MaxStartups 3:50:10",
        "ClientAliveInterval 30",
        "ClientAliveCountMax 3",
        "UseDNS no",
        "",
        "AllowTcpForwarding no",
        "AllowStreamLocalForwarding no",
        "AllowAgentForwarding no",
        "X11Forwarding no",
        "PermitTunnel no",
        "GatewayPorts no",
        "PermitOpen none",
        "PermitListen none",
        "PermitTTY no",
        "MaxSessions 0",
        "ForceCommand exit 1",
        "",
        "Match User $Cuenta",
        "    AuthorizedKeysFile __PROGRAMDATA__/ssh/bms_tunel_authorized_keys",
        "    AllowTcpForwarding local",
        "    PermitOpen 127.0.0.1:$PuertoApp"
    )
    return (($lineas -join "`n") + "`n")
}

function Normalizar-Config([string]$Texto) {
    return ((($Texto -replace "`r", "") -split "`n" | ForEach-Object { $_.TrimEnd() }) -join "`n").Trim()
}

function Macs-De($E) {
    if ($null -eq $E -or $null -eq $E.macs) { return @() }
    return @($E.macs | Where-Object { $null -ne $_ })
}

function Mac-De-La-Ip([string]$Ip, [object[]]$Macs) {
    # El nombre del Mac de una IP (la suya, o la red de la reserva "red"), o "?".
    if ($Ip -notmatch '^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$') { return "?" }
    $n = Numero-De-Ip $Ip
    foreach ($m in $Macs) {
        $r = Rango-De ("" + $m.ip)
        if ($n -ge $r[0] -and $n -le $r[1]) { return ("" + $m.nombre) }
    }
    return "?"
}

function Lo-Que-Se-Aplica([string]$Quien, [string]$Ip) {
    $d = @{}
    $lineas = & $Sshd -T -C ("user=" + $Quien + ",host=mac,addr=" + $Ip) 2>$null
    foreach ($l in $lineas) {
        $p = ("" + $l).Split(" ", 2)
        if ($p.Count -eq 2 -and -not $d.ContainsKey($p[0])) { $d[$p[0]] = $p[1] }
    }
    return $d
}

function Comprobar-Lo-Que-Se-Aplica([object[]]$Macs) {
    # Lo que sshd dice que hara (sshd -T), no lo que creemos haber escrito.
    $ip = "192.0.2.1"
    if ($Macs.Count -gt 0) { $ip = ("" + $Macs[0].ip).Split("/")[0] }
    $tunel = Lo-Que-Se-Aplica $Cuenta $ip
    if ($tunel.Count -eq 0) { return "sshd -T no dice nada" }
    $esperado = [ordered]@{
        "allowtcpforwarding" = "local"; "permitopen" = "127.0.0.1:$PuertoApp"; "permitlisten" = "none";
        "permittty" = "no"; "maxsessions" = "0"; "forcecommand" = "exit 1";
        "passwordauthentication" = "no"; "authenticationmethods" = "publickey";
        "allowagentforwarding" = "no"; "gatewayports" = "no"
    }
    foreach ($k in $esperado.Keys) {
        if ($tunel[$k] -ne $esperado[$k]) { return ("para " + $Cuenta + ", " + $k + " es '" + $tunel[$k] + "' y tenia que ser '" + $esperado[$k] + "'") }
    }
    # Estas tres van escritas a "no"; un sshd que no las imprime las tiene en "no" por defecto
    # salvo AllowStreamLocalForwarding, que ademas cortan PermitOpen y PermitListen.
    foreach ($k in @("allowstreamlocalforwarding", "x11forwarding", "permittunnel")) {
        if ($tunel.ContainsKey($k) -and $tunel[$k] -ne "no") { return ("para " + $Cuenta + ", " + $k + " es '" + $tunel[$k] + "'") }
    }
    if (-not ("" + $tunel["authorizedkeysfile"]).EndsWith("bms_tunel_authorized_keys")) {
        return ("para " + $Cuenta + ", authorizedkeysfile es '" + $tunel["authorizedkeysfile"] + "'")
    }
    $otro = Lo-Que-Se-Aplica "otra-cuenta" $ip
    # Desde OpenSSH 10.3, "AuthorizedKeysFile none" se guarda como lista vacia y sshd -T ya no
    # imprime la linea: vale "none" o que no este.
    $claves = $otro["authorizedkeysfile"]
    if (($null -ne $claves -and $claves -ne "none") -or $otro["allowtcpforwarding"] -ne "no" -or
        $otro["permitopen"] -ne "none") {
        return "para otra cuenta, sshd no queda cerrado"
    }
    return $null
}

function Lineas-De-Derechos([string]$Exportado) {
    # "Derecho = a,b,c" de la seccion [Privilege Rights] de un secedit /export, como tabla.
    $d = [ordered]@{}
    $dentro = $false
    foreach ($l in ($Exportado -split "`r?`n")) {
        $t = $l.Trim()
        if ($t.StartsWith("[")) { $dentro = ($t -eq "[Privilege Rights]"); continue }
        if (-not $dentro -or -not $t) { continue }
        $p = $t.Split("=", 2)
        if ($p.Count -eq 2) { $d[$p[0].Trim()] = $p[1].Trim() }
    }
    return $d
}

function Quienes([string]$Valor) {
    if (-not $Valor) { return @() }
    return @($Valor.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Es-La-Cuenta([string]$Quien, [string]$Sid) {
    # secedit /export escribe las cuentas locales por su nombre y los grupos como *SID: la del
    # tunel puede salir como "*S-1-5-21-...", "bms-tunel" o "EQUIPO\bms-tunel".
    return ($Quien -eq ("*" + $Sid)) -or ($Quien -ieq $Cuenta) -or ($Quien -like ("*\" + $Cuenta))
}

function Texto-Negaciones([string]$Exportado, [string]$Sid, [switch]$Quitar) {
    # La plantilla de secedit /configure: SOLO los cuatro "Denegar...", con quien ya tenian (tal
    # cual) mas la cuenta del tunel, o menos con -Quitar. Nunca el acceso desde la red.
    $d = Lineas-De-Derechos $Exportado
    $lineas = @("[Unicode]", "Unicode=yes", "[Version]", 'signature="$CHICAGO$"', "Revision=1", "[Privilege Rights]")
    foreach ($derecho in $DerechosNegados) {
        $quien = @(Quienes $d[$derecho] | Where-Object { -not (Es-La-Cuenta $_ $Sid) })
        if (-not $Quitar) { $quien += ("*" + $Sid) }
        $lineas += ($derecho + " = " + ($quien -join ","))
    }
    return (($lineas -join "`r`n") + "`r`n")
}

function Diferencias-De-Derechos($Antes, $Despues, [string]$Sid, [switch]$Quitar) {
    # Tras secedit: los cuatro con (o sin) la cuenta, y todos los demas derechos exactamente igual.
    $todos = @(@($Antes.Keys) + @($Despues.Keys) + $DerechosNegados | Sort-Object -Unique)
    foreach ($derecho in $todos) {
        $esperado = @(Quienes $Antes[$derecho])
        $real = @(Quienes $Despues[$derecho])
        if ($DerechosNegados -contains $derecho) {
            $esperado = @($esperado | Where-Object { -not (Es-La-Cuenta $_ $Sid) })
            if (-not $Quitar) { $esperado += ("*" + $Sid) }
            $real = @($real | ForEach-Object { if (Es-La-Cuenta $_ $Sid) { "*" + $Sid } else { $_ } })
        }
        if ((@($esperado | Sort-Object -Unique) -join ",") -ne (@($real | Sort-Object -Unique) -join ",")) { return $derecho }
    }
    return $null
}

# ---------------------------------------------------------------- Windows

function Contrasena-Que-Nadie-Guarda {
    # 32 bytes del generador del sistema; sshd no la necesita (entra con clave, S4U). Va letra a
    # letra a un SecureString y el texto se tira: no se escribe ni se ensena en ningun sitio.
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $texto = [Convert]::ToBase64String($bytes) + "aZ7!"
    $segura = New-Object Security.SecureString
    foreach ($letra in $texto.ToCharArray()) { $segura.AppendChar($letra) }
    $segura.MakeReadOnly()
    $texto = $null
    [Array]::Clear($bytes, 0, $bytes.Length)
    return $segura
}

function Solo-Administradores([string]$Ruta) {
    # Solo SYSTEM y Administradores; la cuenta del tunel ni lo lee ni lo cambia. sshd lo lee
    # desde su proceso de SYSTEM, como administrators_authorized_keys.
    & $Icacls $Ruta /inheritance:r /grant:r ("*" + $SidSistema + ":F") ("*" + $SidAdministradores + ":F") | Out-Null
    & $Icacls $Ruta /setowner ("*" + $SidAdministradores) | Out-Null
}

function Sid-De-Regla($Regla) {
    try { return $Regla.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value } catch { return ("" + $Regla.IdentityReference) }
}

function Quien-Mas-Puede-Cambiar([string[]]$Ficheros, [string[]]$Carpetas, [string]$SidDeQuienLoAbre) {
    # Este script corre como administrador y lo de mac\ va al Mac: si otra cuenta (la de "bms",
    # por ejemplo) pudiera cambiarlo, correria lo suyo como administrador aqui o como el dueno en
    # el Mac. Mira los ficheros, sus carpetas (donde tampoco se puede crear nada: cmd busca los
    # programas primero en la carpeta actual) y cada carpeta de mas arriba hasta la raiz (ahi
    # basta con no poder borrar, renombrar ni cambiar permisos). Y el dueno de cada cosa, que
    # puede cambiar los permisos aunque ninguna regla se lo de. Devuelve la primera pega o $null.
    $permitidos = @($SidSistema, $SidAdministradores, $SidTrustedInstaller, $SidDeQuienLoAbre)
    $enFichero = [Security.AccessControl.FileSystemRights]"WriteData, AppendData, WriteExtendedAttributes, WriteAttributes, Delete, ChangePermissions, TakeOwnership"
    $enSuCarpeta = [Security.AccessControl.FileSystemRights]"CreateFiles, CreateDirectories, Delete, DeleteSubdirectoriesAndFiles, ChangePermissions, TakeOwnership"
    $enLasDeArriba = [Security.AccessControl.FileSystemRights]"Delete, DeleteSubdirectoriesAndFiles, ChangePermissions, TakeOwnership"
    $objetos = @()
    foreach ($f in $Ficheros) { $objetos += , @($f, $enFichero) }
    foreach ($c in $Carpetas) { $objetos += , @($c, $enSuCarpeta) }
    $arriba = @()
    foreach ($c in $Carpetas) {
        $p = Split-Path -Parent $c
        while ($p) {
            if (($Carpetas -notcontains $p) -and ($arriba -notcontains $p)) { $arriba += $p }
            $q = Split-Path -Parent $p
            if ($q -eq $p) { break }
            $p = $q
        }
    }
    foreach ($a in $arriba) { $objetos += , @($a, $enLasDeArriba) }
    foreach ($o in $objetos) {
        $item = Get-Item -LiteralPath $o[0] -Force -ErrorAction SilentlyContinue
        if (-not $item) { return ($o[0] + " (no existe)") }
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { return ($o[0] + " (es un enlace a otro sitio)") }
        try { $acl = Get-Acl -LiteralPath $o[0] } catch { return ($o[0] + " (no se puede leer su seguridad)") }
        $dueno = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
        if ($permitidos -notcontains $dueno) { return ($o[0] + ": es de " + $acl.Owner) }
        foreach ($ace in $acl.Access) {
            if ("" + $ace.AccessControlType -ne "Allow") { continue }
            if (($ace.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -ne 0) { continue }
            if (($ace.FileSystemRights -band $o[1]) -eq 0) { continue }
            $sid = Sid-De-Regla $ace
            if ($permitidos -notcontains $sid) { return ($o[0] + ": " + $ace.IdentityReference) }
        }
    }
    return $null
}

function Lectores-De-Datos([string[]]$Rutas, [string]$SidTunel) {
    # Que ni la cuenta del tunel ni un grupo que lleva cualquier cuenta local ($SidesDeCualquiera)
    # lean lo del programa: el proyecto, sus secretos, el estado, el buzon. Devuelve la primera
    # ruta que si, o $null.
    $quien = @($SidesDeCualquiera)
    if ($SidTunel) { $quien += $SidTunel }
    foreach ($r in $Rutas) {
        if (-not (Test-Path -LiteralPath $r)) { continue }
        try { $acl = Get-Acl -LiteralPath $r } catch { return ($r + " (no se puede leer su seguridad)") }
        foreach ($ace in $acl.Access) {
            if ("" + $ace.AccessControlType -ne "Allow") { continue }
            if (($ace.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -ne 0) { continue }
            if (($ace.FileSystemRights -band [Security.AccessControl.FileSystemRights]::ReadData) -eq 0) { continue }
            if ($quien -contains (Sid-De-Regla $ace)) { return ($r + ": " + $ace.IdentityReference) }
        }
    }
    return $null
}

function Rutas-De-Datos {
    # El proyecto (el padre de docker\) y lo que lleva datos o secretos.
    $padre = Split-Path -Parent $PSScriptRoot
    return @($padre, (Join-Path $padre "datos"), (Join-Path $padre "buzon"),
        (Join-Path $padre "docker\secretos"), (Join-Path $padre "docker\secretos\correo"),
        (Join-Path $padre "docker\estado"))
}

function Leer-Estado {
    # El estado (como estaba el equipo antes y los Mac) vive en el registro de la maquina, que
    # solo cambian los administradores: existe antes que C:\ProgramData\ssh y -Quitar lo borra
    # el ultimo. Nada secreto: IP, nombres y claves publicas.
    $v = Get-ItemProperty -Path $ClaveDeEstado -Name "Estado" -ErrorAction SilentlyContinue
    if (-not $v) { return $null }
    return ($v.Estado | ConvertFrom-Json)
}

function Guardar-Estado($E) {
    if (-not (Test-Path $ClaveDeEstado)) { New-Item -Path $ClaveDeEstado -Force | Out-Null }
    $guardado = [ordered]@{ version = $E.version; instalado = $E.instalado; antes = $E.antes;
        apagado = [bool]$E.apagado; config_sha256 = $E.config_sha256;
        macs = @(Macs-De $E | ForEach-Object { [ordered]@{ nombre = $_.nombre; ip = $_.ip; clave = $_.clave; alta = $_.alta } }) }
    Set-ItemProperty -Path $ClaveDeEstado -Name "Estado" -Value (ConvertTo-Json -InputObject $guardado -Depth 5 -Compress)
}

function Tipo-De-Config {
    if (-not (Test-Path -LiteralPath $Config)) { return "ausente" }
    $t = [IO.File]::ReadAllText($Config)
    if ($t.StartsWith($Marca)) { return "nuestra" }
    if ((Test-Path -LiteralPath $ConfigDeFabrica) -and
        ((Normalizar-Config $t) -eq (Normalizar-Config ([IO.File]::ReadAllText($ConfigDeFabrica))))) {
        return "fabrica"
    }
    return "otra"
}

function Foto-De-Antes {
    # Como estaba el equipo antes de la primera instalacion: -Quitar lo deja asi.
    $cap = Get-WindowsCapability -Online -Name $Capacidad
    $svc = Get-Service -Name sshd -ErrorAction SilentlyContinue
    $regla = Get-NetFirewallRule -Name $ReglaMicrosoft -ErrorAction SilentlyContinue
    $inicio = ""
    if ($svc) { $inicio = "" + $svc.StartType }
    $deMicrosoft = "no_existe"
    if ($regla) { $deMicrosoft = ("" + $regla.Enabled).ToLower() }
    return [pscustomobject][ordered]@{
        capacidad = ("" + $cap.State)
        carpeta = (Test-Path -LiteralPath $CarpetaSsh)
        config = (Tipo-De-Config)
        servicio_inicio = $inicio
        servicio_en_marcha = [bool]($svc -and $svc.Status -eq "Running")
        regla_microsoft = $deMicrosoft
    }
}

function Procesos-De-Sshd {
    # sshd.exe y, desde OpenSSH 9.8, sshd-session.exe (y en 10.x sshd-auth.exe): cada conexion es
    # uno o varios de estos. Los de System32\OpenSSH (o sin ruta visible).
    $carpeta = $ProgramasSsh.TrimEnd("\") + "\"
    return @(Get-CimInstance Win32_Process -Filter "Name LIKE 'sshd%'" -ErrorAction SilentlyContinue |
        Where-Object { (-not $_.ExecutablePath) -or $_.ExecutablePath.StartsWith($carpeta, [StringComparison]::OrdinalIgnoreCase) })
}

function Parar-Tuneles {
    # Con el servicio ya parado, todo proceso de sshd que quede es un tunel abierto (o su parte
    # previa a la clave). taskkill /F por su ruta, que habilita el privilegio de depuracion que
    # hace falta para procesos de SYSTEM y de la cuenta del tunel (Stop-Process podria dar
    # "acceso denegado"). Se vuelve a mirar: devuelve cuantos quedan.
    foreach ($p in @(Procesos-De-Sshd)) { & $Taskkill /F /PID ([int]$p.ProcessId) 2>&1 | Out-Null }
    for ($i = 0; $i -lt 10; $i++) {
        if (@(Procesos-De-Sshd).Count -eq 0) { return 0 }
        Start-Sleep -Seconds 1
    }
    return @(Procesos-De-Sshd).Count
}

function Carpeta-Ssh-Segura {
    # sshd (SYSTEM) lee de aqui su configuracion, las claves del equipo y las de los Mac. Si la
    # carpeta la creo otra cuenta antes que el servicio (cualquiera puede crear carpetas en
    # ProgramData), sshd la usa tal cual y solo apunta "Bad owner". Devuelve las pegas.
    $pegas = @()
    if (-not (Test-Path -LiteralPath $CarpetaSsh)) { return $pegas }
    $permitidos = @($SidSistema, $SidAdministradores, $SidTrustedInstaller)
    $escribir = [Security.AccessControl.FileSystemRights]"WriteData, AppendData, WriteExtendedAttributes, WriteAttributes, Delete, DeleteSubdirectoriesAndFiles, ChangePermissions, TakeOwnership"
    $cosas = @(Get-Item -LiteralPath $CarpetaSsh -Force) + @(Get-ChildItem -LiteralPath $CarpetaSsh -Force -Recurse -ErrorAction SilentlyContinue)
    foreach ($c in $cosas) {
        if ($c.Attributes -band [IO.FileAttributes]::ReparsePoint) { $pegas += ($c.FullName + ": es un enlace"); continue }
        try { $acl = Get-Acl -LiteralPath $c.FullName } catch { $pegas += ($c.FullName + ": no se puede leer su seguridad"); continue }
        $dueno = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
        if ($permitidos -notcontains $dueno) { $pegas += ($c.FullName + ": es de " + $acl.Owner) }
        $privada = (-not $c.PSIsContainer) -and ($c.Name -like "ssh_host_*_key")
        foreach ($ace in $acl.Access) {
            if ("" + $ace.AccessControlType -ne "Allow") { continue }
            if (($ace.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -ne 0) { continue }
            $sid = Sid-De-Regla $ace
            if ($permitidos -contains $sid) { continue }
            if (($ace.FileSystemRights -band $escribir) -ne 0) {
                $pegas += ($c.FullName + ": " + $ace.IdentityReference + " puede cambiarlo")
            } elseif ($privada -and (($ace.FileSystemRights -band [Security.AccessControl.FileSystemRights]::ReadData) -ne 0)) {
                $pegas += ($c.FullName + ": " + $ace.IdentityReference + " puede leer la clave del equipo")
            }
        }
    }
    return $pegas
}

function Apartar-Carpeta-Ssh {
    # La carpeta que no es de fiar se aparta entera (con lo que hubiera dentro) y la vuelve a
    # crear el servicio al arrancar, con sus permisos. Las claves del equipo seran nuevas.
    Stop-Service -Name sshd -Force -ErrorAction SilentlyContinue
    $apartada = $CarpetaSsh + ".apartada-" + (Get-Date -Format "yyyyMMdd-HHmmss")
    try { Move-Item -LiteralPath $CarpetaSsh -Destination $apartada -ErrorAction Stop } catch {
        Fallar ("No se puede apartar " + $CarpetaSsh + " (algo la tiene abierta). Reinicia el equipo y repite mac.bat -Instalar antes de abrir nada mas.")
    }
    & $Takeown /F $apartada /A /R /D Y 2>&1 | Out-Null
    & $Icacls $apartada /inheritance:r /grant:r ("*" + $SidSistema + ":(OI)(CI)F") ("*" + $SidAdministradores + ":(OI)(CI)F") /T /C /Q 2>&1 | Out-Null
    return $apartada
}

function Carpeta-De-Perfiles {
    # C:\Users (donde Windows pone la carpeta de cada cuenta), como en proteger.ps1.
    try {
        $clave = Get-ItemProperty -LiteralPath "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList" -Name ProfilesDirectory -ErrorAction Stop
        return [Environment]::ExpandEnvironmentVariables("" + $clave.ProfilesDirectory)
    } catch {
        return (Split-Path -Parent $env:USERPROFILE)
    }
}

function Carpetas-Apartadas {
    return @(Get-ChildItem -LiteralPath (Split-Path -Parent $CarpetaSsh) -Directory -Force -Filter "ssh.apartada-*" -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
}

function Grupos-De-La-Cuenta([string]$Nombre) {
    # Los grupos locales de los que la cuenta es miembro directo, por SID. Con ADSI (los grupos
    # del usuario) y no con los cmdlets de grupos, que en 5.1 fallan con miembros huerfanos o de
    # Entra. Si no se puede mirar, lanza: quien llama lo trata como un error, nunca como "ninguno".
    $u = [ADSI]("WinNT://" + $env:COMPUTERNAME + "/" + $Nombre + ",user")
    $sids = @()
    foreach ($g in @($u.psbase.Invoke("Groups"))) {
        $bytes = $g.GetType().InvokeMember("objectSid", "GetProperty", $null, $g, $null)
        $sids += (New-Object Security.Principal.SecurityIdentifier($bytes, 0)).Value
    }
    return $sids
}

function Texto-Vuelta($Antes, $Despues) {
    # La plantilla que deja los derechos como estaban: secedit /configure solo toca lo que trae la
    # plantilla, asi que lleva cada derecho de antes o de despues (y los cuatro), con lo que
    # tenia antes; vacio si antes no estaba.
    $todos = @(@($Antes.Keys) + @($Despues.Keys) + $DerechosNegados | Sort-Object -Unique)
    $lineas = @("[Unicode]", "Unicode=yes", "[Version]", 'signature="$CHICAGO$"', "Revision=1", "[Privilege Rights]")
    foreach ($derecho in $todos) { $lineas += ($derecho + " = " + ("" + $Antes[$derecho])) }
    return (($lineas -join "`r`n") + "`r`n")
}

function Negar-Inicios([string]$Sid, [switch]$Quitar) {
    # La cuenta del tunel no puede iniciar sesion en la pantalla, por Escritorio remoto, como
    # tarea ni como servicio. sshd entra con un inicio de red (S4U), que no se toca. Con secedit
    # y solo esos cuatro derechos; despues se comprueba que todo lo demas sigue igual y, si no,
    # se vuelve a poner como estaba. Devuelve $null si ha ido bien, o lo que ha fallado.
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("bms-tunel-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        $antes = Join-Path $tmp "antes.inf"
        $nueva = Join-Path $tmp "nueva.inf"
        $despues = Join-Path $tmp "despues.inf"
        & $Secedit /export /cfg $antes /areas USER_RIGHTS /quiet 2>&1 | Out-Null
        if (-not (Test-Path -LiteralPath $antes)) { return "secedit /export no ha dado nada" }
        $textoAntes = [IO.File]::ReadAllText($antes, [Text.Encoding]::Unicode)
        [IO.File]::WriteAllText($nueva, (Texto-Negaciones $textoAntes $Sid -Quitar:$Quitar), [Text.Encoding]::Unicode)
        & $Secedit /configure /db (Join-Path $tmp "bms.sdb") /cfg $nueva /areas USER_RIGHTS /quiet 2>&1 | Out-Null
        & $Secedit /export /cfg $despues /areas USER_RIGHTS /quiet 2>&1 | Out-Null
        if (-not (Test-Path -LiteralPath $despues)) { return "secedit /export no ha dado nada despues de cambiarlo" }
        $derechosAntes = Lineas-De-Derechos $textoAntes
        $derechosDespues = Lineas-De-Derechos ([IO.File]::ReadAllText($despues, [Text.Encoding]::Unicode))
        $mal = Diferencias-De-Derechos $derechosAntes $derechosDespues $Sid -Quitar:$Quitar
        if ($mal) {
            $vuelta = Join-Path $tmp "vuelta.inf"
            [IO.File]::WriteAllText($vuelta, (Texto-Vuelta $derechosAntes $derechosDespues), [Text.Encoding]::Unicode)
            & $Secedit /configure /db (Join-Path $tmp "vuelta.sdb") /cfg $vuelta /areas USER_RIGHTS /quiet 2>&1 | Out-Null
            return ("secedit no ha dejado " + $mal + " como tocaba; se ha vuelto a poner todo como estaba")
        }
        return $null
    } finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Negaciones-Que-Faltan([string]$Sid) {
    # Para -Estado: cuales de los cuatro "Denegar..." no llevan la cuenta del tunel.
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("bms-tunel-" + [guid]::NewGuid().ToString("N") + ".inf")
    try {
        & $Secedit /export /cfg $tmp /areas USER_RIGHTS /quiet 2>&1 | Out-Null
        if (-not (Test-Path -LiteralPath $tmp)) { return @("no se puede mirar") }
        $d = Lineas-De-Derechos ([IO.File]::ReadAllText($tmp, [Text.Encoding]::Unicode))
        return @($DerechosNegados | Where-Object { -not @(Quienes $d[$_] | Where-Object { Es-La-Cuenta $_ $Sid }) })
    } finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }
}

function Asegurar-Cuenta {
    $u = Get-LocalUser -Name $Cuenta -ErrorAction SilentlyContinue
    if (-not $u) {
        New-LocalUser -Name $Cuenta -Password (Contrasena-Que-Nadie-Guarda) -PasswordNeverExpires `
            -AccountNeverExpires -UserMayNotChangePassword `
            -Description "bms-agent: solo el tunel del Mac" | Out-Null
        Escribir "   cuenta $Cuenta creada (sin contrasena conocida)" "Green"
        $u = Get-LocalUser -Name $Cuenta -ErrorAction SilentlyContinue
        if (-not $u) { Fallar ("No se ha podido crear la cuenta " + $Cuenta + ". El servidor queda parado.") }
    }
    if (-not $u.Enabled) { Enable-LocalUser -Name $Cuenta }
    $sid = $u.SID.Value
    # Sin grupos propios (Administradores, Usuarios de escritorio remoto, docker-users...). Esta en
    # Usuarios igualmente (Usuarios contiene a Usuarios autenticados): lo que le quita los datos es
    # que nadie se los de (Lectores-De-Datos), y lo que le quita la pantalla, Negar-Inicios.
    try { $grupos = @(Grupos-De-La-Cuenta $Cuenta) } catch { Fallar ("No se han podido mirar los grupos de " + $Cuenta + ". El servidor queda parado.") }
    foreach ($g in $grupos) {
        try { Remove-LocalGroupMember -SID $g -Member $sid -ErrorAction Stop } catch { Fallar ("No se ha podido sacar a " + $Cuenta + " del grupo " + $g + ". El servidor queda parado.") }
        Escribir ("   la cuenta " + $Cuenta + " estaba en el grupo " + $g + ": quitada") "Yellow"
    }
    $mal = Negar-Inicios $sid
    if ($mal) { Fallar ("No se ha podido negar a " + $Cuenta + " el inicio de sesion (" + $mal + "). El servidor queda parado.") }
    if (-not (Test-Path $ListaDeInicio)) { New-Item -Path $ListaDeInicio -Force | Out-Null }
    New-ItemProperty -Path $ListaDeInicio -Name $Cuenta -PropertyType DWord -Value 0 -Force | Out-Null
}

function Claves-En-Memorias([string]$Nombre) {
    # Los bms-<nombre>.pub que preparar.command dejo en una memoria (carpeta bms-mac): asi nadie
    # tiene que arrastrar nada a una ventana de administrador (Windows no lo deja, UIPI).
    $patron = "bms-*.pub"
    if ($Nombre) { $patron = "bms-" + $Nombre + ".pub" }
    $sistema = [IO.Path]::GetPathRoot($env:SystemRoot)
    $hay = @()
    foreach ($u in [IO.DriveInfo]::GetDrives()) {
        if (-not $u.IsReady -or $u.RootDirectory.FullName -eq $sistema) { continue }
        $c = Join-Path $u.RootDirectory.FullName "bms-mac"
        if (Test-Path -LiteralPath $c -PathType Container) {
            $hay += @(Get-ChildItem -LiteralPath $c -Filter $patron -File -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
        }
    }
    return $hay
}

function Poner-Reglas([object[]]$Macs, [switch]$Cerrado) {
    # Dos reglas propias, solo para sshd.exe y el puerto 22, en cualquier perfil de red (no se
    # cambia la red a privada: eso abriria a la red otras reglas que no son nuestras). "resto"
    # bloquea a todos menos a los Mac (un bloqueo gana a cualquier regla que deje pasar); la
    # otra deja pasar solo a las IP de los Mac.
    Get-NetFirewallRule -Name $ReglaMac -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    Get-NetFirewallRule -Name $ReglaResto -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    $origenes = @($Macs | ForEach-Object { "" + $_.ip })
    $abierto = (-not $Cerrado) -and ($origenes.Count -gt 0)
    $bloqueados = @("Any")
    if ($abierto) { $bloqueados = @(Resto-De $origenes) }
    New-NetFirewallRule -Name $ReglaResto -DisplayName "BMS - tunel del Mac (sshd): nadie mas" `
        -Direction Inbound -Action Block -Protocol TCP -LocalPort 22 -Program $Sshd `
        -Profile Any -RemoteAddress $bloqueados | Out-Null
    if (-not $abierto) { return }
    New-NetFirewallRule -Name $ReglaMac -DisplayName "BMS - tunel del Mac (sshd): solo los Mac" `
        -Direction Inbound -Action Allow -Protocol TCP -LocalPort 22 -Program $Sshd `
        -Profile Any -RemoteAddress $origenes | Out-Null
}

function Ips-Del-Equipo {
    # Las IPv4 de las conexiones con salida (Ethernet o Wi-Fi), con su tipo de red.
    $lista = @()
    foreach ($c in @(Get-NetIPConfiguration -ErrorAction SilentlyContinue)) {
        if (-not $c.IPv4DefaultGateway) { continue }
        $dir = @($c.IPv4Address)[0]
        if (-not $dir) { continue }
        $categoria = "?"
        $perfil = Get-NetConnectionProfile -InterfaceIndex $c.InterfaceIndex -ErrorAction SilentlyContinue
        if ($perfil) { $categoria = "" + $perfil.NetworkCategory }
        $lista += [pscustomobject]@{ Interfaz = $c.InterfaceAlias; Indice = $c.InterfaceIndex;
            Ip = $dir.IPAddress; Prefijo = [int]$dir.PrefixLength; Red = $categoria }
    }
    return $lista
}

function Huella-Del-Equipo {
    if (-not (Test-Path -LiteralPath $ClaveDelEquipo)) { return "(aun no hay: la crea sshd la primera vez que arranca)" }
    return (Huella-Sha256 ([IO.File]::ReadAllText($ClaveDelEquipo)))
}

function Esperar-Escucha([int]$Segundos) {
    for ($i = 0; $i -lt $Segundos; $i++) {
        $c = Get-NetTCPConnection -LocalPort 22 -State Listen -ErrorAction SilentlyContinue
        if ($c) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Aplicar($E) {
    # Rehace claves, configuracion y reglas a partir del estado, y arranca sshd. Si algo no
    # cuadra, sshd queda parado y el cortafuegos cerrado: falla cerrado. En $Quedan, los
    # procesos de un tunel que Windows no ha dejado cortar.
    $macs = @(Macs-De $E)
    Poner-Reglas -Cerrado
    Stop-Service -Name sshd -Force -ErrorAction SilentlyContinue
    $script:Quedan = Parar-Tuneles
    $pegas = @(Carpeta-Ssh-Segura)
    if ($pegas.Count -gt 0) { Fallar ("C:\ProgramData\ssh no es de fiar (" + ($pegas -join "; ") + "). El servidor queda parado y el cortafuegos cerrado: mac.bat -Instalar lo arregla.") }
    Escribir-Ascii $FicheroClaves (Texto-Claves $macs)
    Solo-Administradores $FicheroClaves
    Escribir-Ascii $ConfigNueva (Texto-Config $macs)
    $prueba = & $Sshd -t -f $ConfigNueva 2>&1
    if ($LASTEXITCODE -ne 0) {
        Remove-Item -LiteralPath $ConfigNueva -Force
        Fallar ("sshd no acepta la configuracion nueva: " + (($prueba | ForEach-Object { "" + $_ }) -join " ") +
            ". El servidor queda parado y el cortafuegos cerrado. Manda este texto a quien mantiene el programa.")
    }
    Move-Item -LiteralPath $ConfigNueva -Destination $Config -Force
    $E.config_sha256 = (Get-FileHash -LiteralPath $Config -Algorithm SHA256).Hash
    Guardar-Estado $E
    $mal = Comprobar-Lo-Que-Se-Aplica $macs
    if ($mal) { Fallar ("sshd no aplicaria lo que tiene que aplicar (" + $mal + "). El servidor queda parado y el cortafuegos cerrado.") }
    if ($E.apagado) {
        Set-Service -Name sshd -StartupType Disabled
        Escribir "   el tunel esta apagado (mac.bat -Encender para abrirlo)" "Yellow"
    } else {
        Set-Service -Name sshd -StartupType Automatic
        Start-Service -Name sshd
        if (-not (Esperar-Escucha 20)) { Fallar "sshd no ha arrancado. Mira el Visor de eventos (OpenSSH) o mac.bat -Estado." }
        Poner-Reglas $macs
    }
    if ($script:Quedan -gt 0) {
        Escribir ("   ATENCION: queda " + $script:Quedan + " proceso(s) de un tunel que Windows no ha dejado cortar. Reinicia el equipo ahora: al volver, solo entran los Mac de la lista.") "Red"
    }
}

function Pedir-Mac($E, [string]$NombrePedido, [switch]$Opcional) {
    # Antes de pedir ser administrador: la ventana de administrador no recibe ficheros
    # arrastrados desde el Explorador (UIPI). Devuelve nombre, origen y clave validados, o $null.
    $macs = @(Macs-De $E)
    $encontradas = @(Claves-En-Memorias $NombrePedido)
    if ($Opcional) {
        $texto = "Anadir ahora un Mac? (escribe si; tambien luego con mac.bat -AnadirClave)"
        if ($encontradas.Count -gt 0) { $texto = "Hay una clave de un Mac en la memoria (" + $encontradas[0] + "). Anadirlo ahora? (escribe si)" }
        if (-not (Es-Si (Read-Host $texto))) { return $null }
    }
    $n = $NombrePedido
    if (-not $n -and $encontradas.Count -eq 1) {
        $n = ([IO.Path]::GetFileNameWithoutExtension($encontradas[0])).Substring(4)
        Escribir ("   el Mac se llama " + $n + " (por el nombre del fichero)")
    }
    while ($n -notmatch $PatronNombre) {
        $n = (Read-Host "Un nombre corto para este Mac (minusculas, cifras y guiones; p. ej. mac-oficina)").Trim()
    }
    $antes = $macs | Where-Object { $_.nombre -eq $n }
    $clave = $null
    $misma = $false
    if ($antes) {
        Escribir ("Ya hay un Mac " + $n + ": IP " + $antes.ip + ", huella " + (Huella-Sha256 $antes.clave)) "Yellow"
        if (-not (Es-Si (Read-Host "Cambiarlo? (escribe si)"))) { Fallar "No se ha cambiado nada." }
        if (Es-Si (Read-Host "Con la misma clave (solo cambias la IP)? (escribe si)")) { $clave = $antes.clave; $misma = $true }
    }
    $propias = @(Ips-Del-Equipo | ForEach-Object { $_.Ip })
    $origen = $null
    while (-not $origen) {
        $t = (Read-Host "La IP del Mac (la ensena preparar.command; p. ej. 192.168.1.23)").Trim()
        if ($t -eq "red") {
            $c = @(Ips-Del-Equipo)[0]
            if ($c) { $origen = Red-De $c.Ip $c.Prefijo }
            if ($origen) { Escribir ("   toda la red " + $origen + ": cualquier equipo de la red llega al servidor (sin la clave no entra). Mejor una IP fija.") "Yellow" }
            continue
        }
        $origen = Ip-Valida $t
        if (-not $origen) { Escribir "   eso no es una IP de una red privada (10.x, 172.16-31.x o 192.168.x)" "Yellow"; continue }
        if ($propias -contains $origen) { Escribir "   esa es la IP de este equipo, no la del Mac" "Yellow"; $origen = $null }
    }
    $propuesta = @(Claves-En-Memorias $n)
    while (-not $clave) {
        $pregunta = "La ruta del fichero .pub del Mac (p. ej. E:\bms-mac\bms-" + $n + ".pub), o pega la linea ssh-ed25519"
        if ($propuesta.Count -eq 1) { $pregunta = "Intro para usar " + $propuesta[0] + ", o escribe otra ruta" }
        $t = (Read-Host $pregunta).Trim().Trim('"')
        if (-not $t -and $propuesta.Count -eq 1) { $t = $propuesta[0] }
        $linea = $t
        if ($t -and -not $t.StartsWith("ssh-") -and (Test-Path -LiteralPath $t -PathType Leaf)) {
            if ((Get-Item -LiteralPath $t).Length -gt 4096) { Escribir "   ese fichero no es una clave publica" "Yellow"; continue }
            $linea = @([IO.File]::ReadAllLines($t) | Where-Object { $_.Trim() })[0]
        }
        $clave = Clave-Publica-Valida $linea
        if (-not $clave) { Escribir "   eso no es una clave publica ed25519 de preparar.command" "Yellow" }
    }
    Escribir ""
    Escribir ("Huella de la clave del Mac: " + (Huella-Sha256 $clave)) "Cyan"
    if (-not (Es-Si (Read-Host "Es la misma que ensena el Mac en su pantalla? (escribe si)"))) {
        Fallar "No se ha anadido nada. Si no es la misma, no uses ese fichero: vuelve a sacarlo del Mac."
    }
    return [pscustomobject]@{ nombre = $n; ip = $origen; clave = $clave; misma = $misma }
}

function Elegir-Mac($E, [string]$NombrePedido) {
    # -QuitarClave, antes de elevar: cual se quita.
    $macs = @(Macs-De $E)
    if ($macs.Count -eq 0) { Fallar "No hay ningun Mac anadido." }
    foreach ($m in $macs) { Escribir ("   " + $m.nombre + "   " + $m.ip + "   " + (Huella-Sha256 $m.clave)) }
    $n = $NombrePedido
    while (-not ($macs | Where-Object { $_.nombre -eq $n })) { $n = (Read-Host "Cual quitas (su nombre)").Trim() }
    if (-not (Es-Si (Read-Host ("Quitar " + $n + "? Deja de poder entrar ahora mismo (escribe si)")))) { Fallar "No se ha quitado nada." }
    return $n
}

function Copiar-Para-El-Mac([string]$Destino) {
    # Lo que va al Mac sale de aqui despues de comprobar que nadie mas lo puede cambiar.
    if (-not (Test-Path -LiteralPath $Destino -PathType Container)) { Fallar ("No encuentro " + $Destino + " (la memoria USB, p. ej. E:\).") }
    $carpeta = Join-Path $Destino "bms-mac"
    if (Test-Path -LiteralPath $carpeta) {
        if (-not (Es-Si (Read-Host ("Ya hay " + $carpeta + ". Sustituir lo que hay? (escribe si)")))) { Fallar "No se ha copiado nada." }
    } else {
        New-Item -ItemType Directory -Path $carpeta | Out-Null
    }
    foreach ($f in $FicherosDelMac) {
        Copy-Item -LiteralPath (Join-Path $CarpetaDelMac $f) -Destination (Join-Path $carpeta $f) -Force
        $h = (Get-FileHash -LiteralPath (Join-Path $carpeta $f) -Algorithm SHA256).Hash.ToLower()
        Escribir ("   " + $f + "   sha256 " + $h.Substring(0, 16))
    }
    Escribir ("Copiado en " + $carpeta + ".") "Green"
    Escribir "En el Mac te va a pedir la IP de este equipo:" "Cyan"
    foreach ($c in @(Ips-Del-Equipo)) { Escribir ("   " + $c.Ip + "   (" + $c.Interfaz + ")") }
}

function Decir-Para-El-Mac {
    Escribir ""
    Escribir "En el Mac (preparar.command) te va a pedir:" "Cyan"
    foreach ($c in @(Ips-Del-Equipo)) {
        Escribir ("   la IP de este equipo: " + $c.Ip + "   (" + $c.Interfaz + ")")
    }
    Escribir ("   y que compares la huella de este equipo: " + (Huella-Del-Equipo)) "Cyan"
}

function Linea-De-Estado([string]$Que, [string]$Nivel, [string]$Texto) {
    # "bien", "aviso" o "mal" (en rojo); "" para lo que solo informa.
    $color = "Gray"
    if ($Nivel -eq "bien") { $color = "Green" }
    if ($Nivel -eq "aviso") { $color = "Yellow" }
    if ($Nivel -eq "mal") { $color = "Red" }
    Escribir ("   {0,-12} {1,-5} {2}" -f $Que, $Nivel, $Texto) $color
}

function Bien-O([bool]$Bien, [string]$SiNo = "mal") {
    if ($Bien) { return "bien" }
    return $SiNo
}

function Mostrar-Estado($E) {
    # Sin cambiar nada. Nunca ensena una clave entera ni nada secreto: huellas, IP y nombres.
    $macs = @(Macs-De $E)
    Escribir "El tunel del Mac en este equipo" "Cyan"
    $svc = Get-Service -Name sshd -ErrorAction SilentlyContinue
    $version = "?"
    if (Test-Path -LiteralPath $Sshd) { $version = "" + (Get-Item -LiteralPath $Sshd).VersionInfo.FileVersion }
    $enMarcha = [bool]($svc -and $svc.Status -eq "Running")
    if (-not $svc) {
        Linea-De-Estado "servidor" "mal" "no hay servicio sshd: mac.bat -Instalar"
    } elseif ($E.apagado) {
        Linea-De-Estado "servidor" (Bien-O ((-not $enMarcha) -and ("" + $svc.StartType) -eq "Disabled")) ("apagado a proposito (mac.bat -Encender): sshd " + $svc.Status + ", inicio " + $svc.StartType + "; sshd.exe " + $version)
    } else {
        Linea-De-Estado "servidor" (Bien-O ($enMarcha -and ("" + $svc.StartType) -eq "Automatic")) ("sshd " + $svc.Status + ", inicio " + $svc.StartType + "; sshd.exe " + $version)
    }
    $pegas = @(Carpeta-Ssh-Segura)
    if ($pegas.Count -eq 0) {
        Linea-De-Estado "carpeta ssh" "bien" ($CarpetaSsh + " es de los administradores y nadie mas la cambia")
    } else {
        Linea-De-Estado "carpeta ssh" "mal" (($pegas -join "; ") + ": mac.bat -Instalar la aparta y la rehace")
    }
    $tipo = Tipo-De-Config
    $igual = ($tipo -eq "nuestra") -and ((Get-FileHash -LiteralPath $Config -Algorithm SHA256).Hash -eq $E.config_sha256)
    $null = & $Sshd -t 2>&1
    $acepta = ($LASTEXITCODE -eq 0)
    $texto = "la de bms-agent, sin cambios a mano, sshd -t sin errores"
    if (-not $igual) { $texto = "NO es la que dejo mac.bat (" + $tipo + "): mac.bat -Instalar la rehace" }
    elseif (-not $acepta) { $texto = "sshd -t da errores: mac.bat -Instalar" }
    Linea-De-Estado "config" (Bien-O ($igual -and $acepta)) $texto
    $mal = Comprobar-Lo-Que-Se-Aplica $macs
    $texto = "solo 127.0.0.1:" + $PuertoApp + " de este equipo; sin consola, sin ficheros, sin -R"
    if ($mal) { $texto = $mal }
    Linea-De-Estado "reenvio" (Bien-O (-not $mal)) $texto
    $u = Get-LocalUser -Name $Cuenta -ErrorAction SilentlyContinue
    $sidTunel = ""
    if (-not $u) {
        Linea-De-Estado "cuenta" "mal" "$Cuenta no existe: mac.bat -Instalar"
    } else {
        $sidTunel = $u.SID.Value
        $pegasCuenta = @()
        try {
            $grupos = @(Grupos-De-La-Cuenta $Cuenta)
            if ($grupos.Count -gt 0) { $pegasCuenta += ("esta en grupos propios (" + ($grupos -join ", ") + ")") }
        } catch {
            $pegasCuenta += "no se han podido mirar sus grupos"
        }
        $faltan = @(Negaciones-Que-Faltan $sidTunel)
        if ($faltan.Count -gt 0) { $pegasCuenta += ("sin negar: " + ($faltan -join ", ")) }
        if (-not $u.Enabled) { $pegasCuenta += "deshabilitada" }
        if ($null -ne $u.PasswordExpires) { $pegasCuenta += "su contrasena caduca" }
        $oculta = Get-ItemProperty -Path $ListaDeInicio -Name $Cuenta -ErrorAction SilentlyContinue
        if (-not $oculta -or $oculta.$Cuenta -ne 0) { $pegasCuenta += "sale en la pantalla de inicio" }
        if ($pegasCuenta.Count -eq 0) {
            Linea-De-Estado "cuenta" "bien" ($Cuenta + ": sin grupos propios; pantalla, Escritorio remoto, tareas y servicios denegados; no caduca; oculta")
        } else {
            Linea-De-Estado "cuenta" "mal" ($Cuenta + ": " + ($pegasCuenta -join "; ") + ": mac.bat -Instalar lo arregla")
        }
    }
    $lee = Lectores-De-Datos (Rutas-De-Datos) $sidTunel
    if ($lee) {
        Linea-De-Estado "datos" "mal" ("otras cuentas leen los datos del programa (" + $lee + "): proteger.bat -Usuario bms")
    } else {
        Linea-De-Estado "datos" "bien" ("ni " + $Cuenta + " ni los grupos de cualquier cuenta leen " + (Split-Path -Parent $PSScriptRoot) + " (secretos, estado, buzon)")
    }
    if (Test-Path -LiteralPath $CarpetaDelMac) {
        $cortos = @()
        foreach ($f in @("preparar.command", "abrir-bms.command")) {
            $ruta = Join-Path $CarpetaDelMac $f
            $h = "falta"
            if (Test-Path -LiteralPath $ruta) { $h = (Get-FileHash -LiteralPath $ruta -Algorithm SHA256).Hash.ToLower().Substring(0, 16) }
            $cortos += ($f.Split(".")[0] + " " + $h)
        }
        Linea-De-Estado "scripts" "bien" ("nadie mas puede cambiar mac.bat ni lo del Mac (" + ($cortos -join ", ") + ")")
    } else {
        Linea-De-Estado "scripts" "aviso" ("nadie mas puede cambiar mac.bat; falta la carpeta " + $CarpetaDelMac)
    }
    $clavesBien = (Test-Path -LiteralPath $FicheroClaves) -and ([IO.File]::ReadAllText($FicheroClaves) -eq (Texto-Claves $macs))
    $texto = "" + $macs.Count + " Mac"
    if (-not $clavesBien) { $texto += "; el fichero de claves no es el que dejo mac.bat: mac.bat -Instalar lo rehace" }
    Linea-De-Estado "claves" (Bien-O $clavesBien) $texto
    foreach ($m in $macs) {
        Escribir ("                      {0,-16} {1,-18} {2}  desde {3}" -f $m.nombre, $m.ip, (Huella-Sha256 $m.clave), $m.alta)
    }
    $mac = Get-NetFirewallRule -Name $ReglaMac -ErrorAction SilentlyContinue
    $resto = Get-NetFirewallRule -Name $ReglaResto -ErrorAction SilentlyContinue
    $ms = Get-NetFirewallRule -Name $ReglaMicrosoft -ErrorAction SilentlyContinue
    $restoBien = $resto -and ("" + $resto.Enabled) -eq "True" -and ("" + $resto.Action) -eq "Block" -and ("" + $resto.Profile) -eq "Any"
    $macBien = $E.apagado -or $macs.Count -eq 0 -or ($mac -and ("" + $mac.Enabled) -eq "True" -and ("" + $mac.Profile) -eq "Any")
    $nivel = Bien-O ($restoBien -and $macBien)
    $texto = "el 22 solo para los Mac (cualquier red); el resto, bloqueado"
    if ($E.apagado -or $macs.Count -eq 0) { $texto = "el 22 cerrado para todos" }
    if ($nivel -ne "bien") { $texto = "faltan las reglas BMS - tunel del Mac o no estan como tienen que estar: mac.bat -Instalar" }
    if ($ms -and ("" + $ms.Enabled) -eq "True") {
        if ($nivel -eq "bien") { $nivel = "aviso" }
        $texto += "; la regla de Microsoft (OpenSSH-Server-In-TCP) esta encendida otra vez (la de resto la sigue tapando): mac.bat -Instalar la apaga"
    }
    Linea-De-Estado "cortafuegos" $nivel $texto
    foreach ($c in @(Ips-Del-Equipo)) {
        $perfil = "" + $c.Red
        if ($perfil -eq "DomainAuthenticated") { $perfil = "Domain" }
        $deEntrada = ""
        try { $deEntrada = "" + (Get-NetFirewallProfile -Name $perfil -ErrorAction Stop).AllowInboundRules } catch { }
        if ($deEntrada -eq "False") {
            Linea-De-Estado "red" "aviso" ($c.Interfaz + ": " + $c.Ip + "/" + $c.Prefijo + ", red " + $c.Red + ": su perfil bloquea todas las conexiones entrantes, tambien la de los Mac")
        } else {
            Linea-De-Estado "red" "" ($c.Interfaz + ": " + $c.Ip + "/" + $c.Prefijo + ", red " + $c.Red + " (da igual para el tunel)")
        }
    }
    $abiertos = @(Get-NetTCPConnection -LocalPort 22 -State Established -ErrorAction SilentlyContinue)
    $quienes = @($abiertos | ForEach-Object { (Mac-De-La-Ip ("" + $_.RemoteAddress) $macs) + " (" + $_.RemoteAddress + ")" })
    $texto = "" + $abiertos.Count + " abierto(s) ahora"
    if ($quienes.Count -gt 0) { $texto += ": " + ($quienes -join ", ") }
    Linea-De-Estado "tuneles" "" ($texto + "; " + @(Procesos-De-Sshd).Count + " procesos de sshd")
    $contesta = $false
    try { $contesta = ((Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri ("http://127.0.0.1:" + $PuertoApp + "/consola")).StatusCode -eq 200) } catch { }
    $escucha = @(Get-NetTCPConnection -LocalPort $PuertoApp -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName } | Sort-Object -Unique)
    $texto = "contesta en 127.0.0.1:" + $PuertoApp + " (" + ($escucha -join ", ") + ")"
    if (-not $contesta) { $texto = "no contesta en 127.0.0.1:" + $PuertoApp + ": el Mac abrira el tunel pero no vera la app (la sesion de bms y Docker Desktop)" }
    Linea-De-Estado "app" (Bien-O $contesta "aviso") $texto
    Escribir ("   huella de este equipo: " + (Huella-Del-Equipo) + "   (la que tiene que ensenar el Mac la primera vez)") "Cyan"
    $eventos = @(Get-WinEvent -LogName "OpenSSH/Operational" -MaxEvents 2000 -ErrorAction SilentlyContinue)
    $entradas = @($eventos | Where-Object { $_.Message -match "Accepted publickey for " } | Select-Object -First 5)
    foreach ($ev in $entradas) {
        if ($ev.Message -match "from (\S+) port \d+ ssh2: ED25519 (SHA256:\S+)") {
            $desde = $Matches[1]
            $huella = $Matches[2]
            $quienEs = @($macs | Where-Object { (Huella-Sha256 $_.clave) -eq $huella } | ForEach-Object { $_.nombre })
            if ($quienEs.Count -eq 0) { $quienEs = @("una clave que ya no esta") }
            Escribir ("   entro      " + $ev.TimeCreated.ToString("dd-MM-yyyy HH:mm") + "  " + ($quienEs -join "") + " desde " + $desde)
        }
    }
    $semana = (Get-Date).AddDays(-7)
    $rechazos = @($eventos | Where-Object { $_.TimeCreated -gt $semana -and $_.Message -match "not allowed because|Invalid user|Connection closed by authenticating user|Failed publickey|administratively prohibited|refused" }).Count
    Linea-De-Estado "rechazos" (Bien-O ($rechazos -eq 0) "aviso") ("" + $rechazos + " en los ultimos 7 dias (Visor de eventos: OpenSSH, Operational)")
    $ultimo = Get-HotFix -ErrorAction SilentlyContinue | Where-Object { $_.InstalledOn } | Sort-Object InstalledOn -Descending | Select-Object -First 1
    if ($ultimo) {
        $viejo = $ultimo.InstalledOn -lt (Get-Date).AddDays(-35)
        $texto = "ultima actualizacion instalada: " + $ultimo.InstalledOn.ToString("dd-MM-yyyy") + " (sshd se actualiza con Windows Update)"
        if ($viejo) { $texto += ". Mas de 35 dias: actualiza Windows o, hasta entonces, mac.bat -Apagar" }
        Linea-De-Estado "windows" (Bien-O (-not $viejo)) $texto
    } else {
        Linea-De-Estado "windows" "aviso" "no se sabe la fecha de la ultima actualizacion: mira Windows Update"
    }
    $apartadas = @(Carpetas-Apartadas)
    if ($apartadas.Count -gt 0) { Escribir ("   apartadas: " + ($apartadas -join ", ") + " (mac.bat no las toca)") }
}

# ---------------------------------------------------------------- la entrada

$acciones = @()
foreach ($a in @("Instalar", "AnadirClave", "QuitarClave", "Estado", "Apagar", "Encender", "Quitar")) {
    if ((Get-Variable -Name $a -ValueOnly)) { $acciones += $a }
}
if ($CopiarParaElMac) { $acciones += "CopiarParaElMac" }
if ($acciones.Count -ne 1) {
    Fallar "Di una cosa: mac.bat -Instalar, -AnadirClave, -QuitarClave, -Estado, -Apagar, -Encender, -Quitar o -CopiarParaElMac E:\"
}
$accion = $acciones[0]
if ($Nombre -and $Nombre -notmatch $PatronNombre) { Fallar "El nombre del Mac: minusculas, cifras y guiones (p. ej. mac-oficina)." }
if ([Environment]::Is64BitOperatingSystem -and -not [Environment]::Is64BitProcess) {
    Fallar "Abre mac.bat con doble clic o desde una ventana normal (no desde un programa de 32 bits)."
}
if (-not $Usuario) { $Usuario = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value }
if ($Usuario -notmatch '^S-1-5-21-\d+-\d+-\d+-\d+$') { Fallar "Uso interno: -Usuario no es un SID de una cuenta." }

# Antes de nada: que ninguna otra cuenta pueda cambiar lo que va a correr como administrador ni
# lo que se copia al Mac.
$ficheros = @($PSCommandPath, (Join-Path $PSScriptRoot "mac.bat"))
$carpetas = @($PSScriptRoot)
if (Test-Path -LiteralPath $CarpetaDelMac) {
    $ficheros += @($FicherosDelMac | ForEach-Object { Join-Path $CarpetaDelMac $_ })
    $carpetas += $CarpetaDelMac
} elseif ($accion -eq "CopiarParaElMac") {
    Fallar ("Falta la carpeta " + $CarpetaDelMac + ".")
}
$quien = Quien-Mas-Puede-Cambiar $ficheros $carpetas $Usuario
if ($quien) {
    Fallar ("Otra cuenta de este equipo puede cambiar lo que mac.bat ejecuta como administrador o lo que va al Mac (" + $quien +
        "). Asi no se sigue: proteger.bat -Usuario bms, como administrador (docs/entorno-local.md).")
}
if ($accion -eq "CopiarParaElMac") { Copiar-Para-El-Mac $CopiarParaElMac; exit 0 }

# Lo que hay que preguntar, antes de pedir ser administrador.
if (-not $Elevado) {
    $leido = Leer-Estado
    if ($accion -ne "Instalar" -and $null -eq $leido) { Fallar "El tunel del Mac no esta instalado en este equipo: mac.bat -Instalar." }
    if ($accion -eq "Instalar" -or $accion -eq "AnadirClave") {
        $m = Pedir-Mac $leido $Nombre -Opcional:($accion -eq "Instalar")
        if ($m) { $Nombre = $m.nombre; $Ip = $m.ip; $Clave = $m.clave.Split(" ")[1]; $MismaClave = [switch]$m.misma }
    }
    if ($accion -eq "QuitarClave") { $Nombre = Elegir-Mac $leido $Nombre }
}
if (-not (Es-Administrador)) {
    Escribir "Windows te va a pedir permiso de administrador: el servidor SSH, la cuenta y el cortafuegos lo necesitan." "Cyan"
    $argumentos = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ('"' + $PSCommandPath + '"'),
        ("-" + $accion), "-Elevado", "-Usuario", $Usuario)
    if ($Nombre) { $argumentos += @("-Nombre", $Nombre) }
    if ($Ip) { $argumentos += @("-Ip", $Ip) }
    if ($Clave) { $argumentos += @("-Clave", $Clave) }
    if ($MismaClave) { $argumentos += "-MismaClave" }
    if ($SustituirConfiguracion) { $argumentos += "-SustituirConfiguracion" }
    try {
        $p = Start-Process -FilePath (Get-Process -Id $PID).Path -ArgumentList $argumentos -Verb RunAs -Wait -PassThru
    } catch {
        Fallar "Sin permiso de administrador no se puede. Vuelve a abrir mac.bat y di que si."
    }
    exit $p.ExitCode
}
# Ya como administrador: lo que llega de la ventana normal se vuelve a validar, nunca se cree.
$nuevoMac = $null
if ($Nombre -and $Ip -and $Clave) {
    $origen = Origen-Valido $Ip
    $completa = Clave-Publica-Valida ("ssh-ed25519 " + $Clave)
    if (-not $origen -or -not $completa) { Fallar "Uso interno: la IP o la clave del Mac no son validas." }
    $nuevoMac = [pscustomobject][ordered]@{ nombre = $Nombre; ip = $origen; clave = $completa; alta = (Get-Date -Format "yyyy-MM-dd") }
}

$EstadoDelTunel = Leer-Estado
if ($accion -ne "Instalar" -and $null -eq $EstadoDelTunel) {
    Fallar "El tunel del Mac no esta instalado en este equipo: mac.bat -Instalar."
}
if ($MismaClave) {
    # Solo cambia la IP: la clave tiene que ser la que ya tenia ese Mac.
    $deAntes = @(Macs-De $EstadoDelTunel | Where-Object { $_.nombre -eq $Nombre })
    if (-not $nuevoMac -or $deAntes.Count -ne 1 -or $deAntes[0].clave -ne $nuevoMac.clave) {
        Fallar "Uso interno: -MismaClave sin un Mac con esa clave."
    }
}

switch ($accion) {
    "Instalar" {
        Escribir "El tunel del Mac: instalar (o rehacer) en este equipo" "Cyan"
        $tipo = Tipo-De-Config
        if ($tipo -eq "otra" -and -not $SustituirConfiguracion) {
            Fallar ("C:\ProgramData\ssh\sshd_config tiene cambios que no son de bms-agent: puede que alguien use ya el servidor SSH de este equipo. " +
                "mac.bat no lo toca. Si no se usa para otra cosa: mac.bat -Instalar -SustituirConfiguracion (guarda una copia, y -Quitar la devuelve).")
        }
        $servicio = Get-CimInstance Win32_Service -Filter "Name='sshd'" -ErrorAction SilentlyContinue
        if ($servicio -and -not (("" + $servicio.PathName).Trim().Trim('"')).StartsWith($ProgramasSsh.TrimEnd("\") + "\", [StringComparison]::OrdinalIgnoreCase)) {
            Fallar ("El servidor SSH de este equipo no es el de Windows (" + $servicio.PathName + "): mac.bat no lo toca.")
        }
        $tunelAntes = Get-LocalUser -Name $Cuenta -ErrorAction SilentlyContinue
        $sidTunel = ""
        if ($tunelAntes) { $sidTunel = $tunelAntes.SID.Value }
        $lee = Lectores-De-Datos (Rutas-De-Datos) $sidTunel
        if ($lee) {
            Fallar ("Otras cuentas de este equipo pueden leer los datos del programa (" + $lee + "), y la del tunel tambien podria. " +
                "Antes, como administrador: proteger.bat -Usuario bms (o pon el proyecto en tu carpeta de usuario si no usas bms).")
        }
        $conClaves = (Test-Path -LiteralPath (Join-Path $CarpetaSsh "administrators_authorized_keys")) -or
            (@(Get-ChildItem -Path (Join-Path (Carpeta-De-Perfiles) "*\.ssh\authorized_keys") -Force -ErrorAction SilentlyContinue).Count -gt 0)
        if ($tipo -ne "nuestra" -and (($servicio -and $servicio.State -eq "Running") -or $conClaves)) {
            Escribir "El servidor SSH de este equipo ya estaba en marcha o hay claves de personas: desde ahora solo entrara el tunel del Mac (nadie mas por SSH)." "Yellow"
        }
        Escribir ("Se va a: instalar el servidor OpenSSH de Windows (si falta), crear la cuenta " + $Cuenta + " (sin contrasena conocida, sin grupos propios y sin poder iniciar sesion en la pantalla), " +
            "dejar sshd solo para el tunel y abrir el puerto 22 solo a los Mac que anadas (en cualquier red; la red no se toca).")
        if (-not (Es-Si (Read-Host "Seguir? (escribe si)"))) { Fallar "No se ha cambiado nada." }
        if ($null -eq $EstadoDelTunel) {
            # La foto de antes, guardada antes de cambiar nada: -Quitar deja el equipo asi.
            $EstadoDelTunel = [pscustomobject][ordered]@{ version = 1; instalado = (Get-Date -Format "yyyy-MM-dd HH:mm");
                antes = (Foto-De-Antes); apagado = $false; config_sha256 = ""; macs = @() }
            Guardar-Estado $EstadoDelTunel
        } elseif ($tipo -eq "nuestra" -and $EstadoDelTunel.config_sha256 -and
            ((Get-FileHash -LiteralPath $Config -Algorithm SHA256).Hash -ne $EstadoDelTunel.config_sha256)) {
            $copia = $Config + ".cambiada-" + (Get-Date -Format "yyyyMMdd-HHmmss")
            Copy-Item -LiteralPath $Config -Destination $copia
            Escribir ("   alguien cambio sshd_config a mano: copia en " + $copia + "; se rehace") "Yellow"
        }
        if ("" + (Get-WindowsCapability -Online -Name $Capacidad).State -ne "Installed") {
            Escribir "   instalando el servidor OpenSSH de Windows (unos minutos)..." "Cyan"
            Add-WindowsCapability -Online -Name $Capacidad | Out-Null
            if ("" + (Get-WindowsCapability -Online -Name $Capacidad).State -ne "Installed") {
                Fallar "Windows no ha instalado el servidor OpenSSH. Mira Windows Update y vuelve a probar (mac.bat -Quitar lo deshace)."
            }
        }
        # Antes de arrancar nada: la regla de Microsoft apagada y las nuestras cerradas.
        Get-NetFirewallRule -Name $ReglaMicrosoft -ErrorAction SilentlyContinue | Disable-NetFirewallRule
        Poner-Reglas -Cerrado
        $pegas = @(Carpeta-Ssh-Segura)
        if ($pegas.Count -gt 0) {
            Escribir ("C:\ProgramData\ssh no es de fiar: " + ($pegas -join "; ") + ".") "Yellow"
            Escribir "sshd (como SYSTEM) usaria lo que otra cuenta ha podido cambiar. Se aparta entera (no se borra) y el servicio la vuelve a crear, con claves del equipo nuevas." "Yellow"
            if (-not (Es-Si (Read-Host "Apartarla? (escribe si)"))) { Fallar "No se ha seguido. El servidor queda parado y el cortafuegos cerrado." }
            $apartada = Apartar-Carpeta-Ssh
            Escribir ("   apartada en " + $apartada) "Yellow"
            if (@(Macs-De $EstadoDelTunel).Count -gt 0) {
                Escribir "   ATENCION: la huella de este equipo cambia. En cada Mac: bash ~/.bms-tunel/preparar.command y compara la huella nueva." "Red"
            }
        }
        if (-not (Test-Path -LiteralPath $ClaveDelEquipo)) {
            # La primera vez que arranca, el servicio crea C:\ProgramData\ssh, su sshd_config de
            # fabrica y las claves del equipo. Con el cortafuegos cerrado no le llega nadie de fuera.
            Start-Service -Name sshd
            Start-Sleep -Seconds 5
            Stop-Service -Name sshd -Force
            if (-not (Test-Path -LiteralPath $ClaveDelEquipo)) { Fallar "sshd no ha creado la clave del equipo (ssh_host_ed25519_key)." }
            $pegas = @(Carpeta-Ssh-Segura)
            if ($pegas.Count -gt 0) { Fallar ("C:\ProgramData\ssh sigue sin ser de fiar (" + ($pegas -join "; ") + "). El servidor queda parado y el cortafuegos cerrado.") }
        }
        if ($EstadoDelTunel.antes.config -ne "ausente" -and (Tipo-De-Config) -ne "nuestra" -and -not (Test-Path -LiteralPath $ConfigAntes)) {
            Copy-Item -LiteralPath $Config -Destination $ConfigAntes
        }
        Asegurar-Cuenta
        if ($nuevoMac) { $EstadoDelTunel.macs = @(@(Macs-De $EstadoDelTunel | Where-Object { $_.nombre -ne $nuevoMac.nombre }) + $nuevoMac) }
        Aplicar $EstadoDelTunel
        Escribir "Listo." "Green"
        Decir-Para-El-Mac
    }
    "AnadirClave" {
        if (-not $nuevoMac) { Fallar "Uso interno: falta el Mac (nombre, IP y clave)." }
        $EstadoDelTunel.macs = @(@(Macs-De $EstadoDelTunel | Where-Object { $_.nombre -ne $nuevoMac.nombre }) + $nuevoMac)
        Aplicar $EstadoDelTunel
        Escribir ("Listo: " + $nuevoMac.nombre + " (" + $nuevoMac.ip + ") ya puede abrir el tunel.") "Green"
        Decir-Para-El-Mac
    }
    "QuitarClave" {
        $macs = @(Macs-De $EstadoDelTunel)
        if (-not ($macs | Where-Object { $_.nombre -eq $Nombre })) { Fallar ("Uso interno: no hay ningun Mac " + $Nombre + ".") }
        $EstadoDelTunel.macs = @($macs | Where-Object { $_.nombre -ne $Nombre })
        Aplicar $EstadoDelTunel
        if ($Quedan -gt 0) {
            Escribir ("Quitado: " + $Nombre + " ya no puede entrar de nuevo, pero un tunel abierto puede seguir hasta que reinicies el equipo (arriba, en rojo).") "Red"
        } else {
            Escribir ("Quitado: " + $Nombre + " ya no entra (y se han cortado los tuneles abiertos).") "Green"
        }
        Escribir ("En ese Mac: bash ~/.bms-tunel/preparar.command --borrar. Y un token nuevo para la persona de ese Mac: persona.bat -Nombre ""<su persona>"" -Rol administracion.")
    }
    "Apagar" {
        $EstadoDelTunel.apagado = $true
        Aplicar $EstadoDelTunel
        Escribir "Apagado: sshd parado y sin arrancar con Windows, el cortafuegos cerrado. Para volver: mac.bat -Encender." "Green"
    }
    "Encender" {
        $EstadoDelTunel.apagado = $false
        Aplicar $EstadoDelTunel
        Escribir "Encendido." "Green"
    }
    "Estado" {
        Mostrar-Estado $EstadoDelTunel
    }
    "Quitar" {
        Escribir "Se va a quitar todo lo del tunel del Mac y dejar el equipo como estaba." "Yellow"
        if (-not (Es-Si (Read-Host "Seguir? (escribe si)"))) { Fallar "No se ha cambiado nada." }
        $antes = $EstadoDelTunel.antes
        Stop-Service -Name sshd -Force -ErrorAction SilentlyContinue
        $quedanAhora = Parar-Tuneles
        Get-NetFirewallRule -Name $ReglaMac -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        Get-NetFirewallRule -Name $ReglaResto -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        if (Test-Path -LiteralPath $ConfigAntes) {
            Move-Item -LiteralPath $ConfigAntes -Destination $Config -Force
        } elseif ($antes.config -eq "ausente") {
            Remove-Item -LiteralPath $Config -Force -ErrorAction SilentlyContinue
        }
        Remove-Item -LiteralPath $FicheroClaves -Force -ErrorAction SilentlyContinue
        $u = Get-LocalUser -Name $Cuenta -ErrorAction SilentlyContinue
        if ($u) {
            $mal = Negar-Inicios $u.SID.Value -Quitar
            if ($mal) { Escribir ("   aviso: no se han quitado las negaciones de inicio de sesion (" + $mal + "); quedan a un SID que ya no existe, no hacen nada") "Yellow" }
            Get-CimInstance Win32_UserProfile -ErrorAction SilentlyContinue |
                Where-Object { $_.SID -eq $u.SID.Value } | Remove-CimInstance -ErrorAction SilentlyContinue
            Remove-LocalUser -Name $Cuenta
        }
        Remove-ItemProperty -Path $ListaDeInicio -Name $Cuenta -ErrorAction SilentlyContinue
        if ($antes.capacidad -ne "Installed") {
            Remove-WindowsCapability -Online -Name $Capacidad | Out-Null
            Get-NetFirewallRule -Name $ReglaMicrosoft -ErrorAction SilentlyContinue | Remove-NetFirewallRule
            if (-not $antes.carpeta -and (Test-Path -LiteralPath $CarpetaSsh)) {
                if (Es-Si (Read-Host "Borrar tambien C:\ProgramData\ssh (las claves de este equipo y sus registros)? (escribe si)")) {
                    Remove-Item -LiteralPath $CarpetaSsh -Recurse -Force
                }
            }
            Escribir "Si Windows lo pide, reinicia el equipo." "Yellow"
        } else {
            if ($antes.servicio_inicio) { Set-Service -Name sshd -StartupType $antes.servicio_inicio }
            if ($antes.servicio_en_marcha) { Start-Service -Name sshd }
            if ($antes.regla_microsoft -eq "true") { Enable-NetFirewallRule -Name $ReglaMicrosoft }
        }
        foreach ($a in @(Carpetas-Apartadas)) { Escribir ("   queda " + $a + " (la aparto mac.bat; no se toca)") "Yellow" }
        if ($quedanAhora -gt 0) { Escribir ("   ATENCION: queda " + $quedanAhora + " proceso(s) de un tunel que Windows no ha dejado cortar: reinicia el equipo ahora.") "Red" }
        Remove-Item -Path $ClaveDeEstado -Recurse -Force -ErrorAction SilentlyContinue
        Escribir "Quitado. En cada Mac: bash ~/.bms-tunel/preparar.command --borrar, y un token nuevo para su persona (persona.bat)." "Green"
    }
}
Esperar-Intro
exit 0
