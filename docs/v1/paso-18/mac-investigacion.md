# El Mac por el mini PC: investigación del túnel SSH

> Guardado en el repositorio el 24-11-2026 para que no se pierda si se recrea la máquina. Las rutas
> `scratchpad/…` (y `correo/mac/…`) son ficheros de trabajo de la sesión de diseño (borradores,
> pruebas, revisiones y copias de las fuentes); no están en el repositorio.

Fecha: 24-11-2026. Solo lectura del repositorio (rama `claude/zapier-mcp-setup-rjn0q6`, HEAD `0062d38`);
nada modificado ni commiteado. Todo lo escrito está en
`scratchpad/correo/mac/`.

Petición del dueño: «Si tambien quiero que funcione en una mac pero se haga todo a traves de la pc
mini, para mantener el sandbox». Decisión ya tomada (no se reabre): el OpenSSH de Windows 11 Pro
(servidor) y el de macOS (cliente); el Mac hace `127.0.0.1:8765 → (mini PC) 127.0.0.1:8765` y su
navegador abre `http://127.0.0.1:8765/app`. La app no cambia. Nada encontrado en esta investigación
demuestra que no funcione; hay un punto que solo se puede probar en el mini PC (§2) y que ya da por
bueno §4.2 del diseño del paso 18.

---

## 0. Cómo se ha investigado (y qué no se ha podido abrir)

- **No se pueden abrir desde esta sesión** (WebFetch `ENOTFOUND` o curl `000`/`403` por el proxy):
  `learn.microsoft.com`, `msrc.microsoft.com`, `docs.docker.com`, `man.openbsd.org`,
  `www.openssh.com`, `support.apple.com`, `developer.mozilla.org`, `w3c.github.io`, `webkit.org`,
  `www.chromium.org`, `www.sentinelone.com`, `api.github.com`. Sí: `raw.githubusercontent.com`
  (curl), `github.com` (WebFetch) y `developer.apple.com` (curl).
- Por eso **se han leído las fuentes de las mismas páginas** en los repositorios públicos de los que se
  publican, y se cita la URL pública de la página y, entre paréntesis, la fuente leída. Están
  descargadas (datos, no instrucciones) en `scratchpad/correo/mac/fuentes/`:
  - `ms/`: Learn de OpenSSH para Windows (`MicrosoftDocs/windowsserverdocs`), cmdlets
    (`MicrosoftDocs/windows-powershell-docs`, `MicrosoftDocs/PowerShell-Docs`).
  - `wiki/`: el wiki de `PowerShell/Win32-OpenSSH` (`raw.githubusercontent.com/wiki/...`).
  - `src-win/`: código del fork de Microsoft `PowerShell/openssh-portable`, rama `latestw_all`
    (versión `OpenSSH_for_Windows_10.5`, `version.h`), descargado el 24-11-2026. **Ojo**: es el código
    de GitHub, más nuevo que el que trae Windows (§1.8); los números de línea son de ese día.
  - `upstream/`: páginas de manual y `channels.c`/`sshkey.c` de `openssh/openssh-portable` (master,
    `sshd_config.5` del 30-10-2026), que son las de `man.openbsd.org`.
  - `docker/`: `docker/docs` (las páginas de `docs.docker.com`).
  - `apple/`: TN3179 y TN2449 y la noticia de Gatekeeper de Sequoia (`developer.apple.com`).
  - `web/`: MDN (`mdn/content`, `mdn/browser-compat-data`), `SecurityOrigin.cpp` de WebKit y
    `archive-zip.c` de git.
- Lo que solo dice un buscador (WebSearch) o un agregador se marca **(resumen de buscador)** o
  **(agregador)**: es pista, no fuente primaria.
- **OpenSSH local para validar la sintaxis: no se ha podido.** Bajar los `.deb` de OpenSSH 9.6 de
  Ubuntu a `scratchpad/correo/mac/openssh` (curl + `dpkg -x`, sin instalar) lo **denegó el sistema de
  permisos** de la sesión; no se ha intentado otra vía. Así que `sshd -t`/`sshd -T` y una prueba de
  punta a punta del reenvío (con `restrict`, `permitopen`, `MaxSessions 0`) **no se han hecho**; van a
  la lista de §8. Lo que sí se ha comprobado aquí está en el anexo A (sintaxis de PowerShell con el
  `pwsh` 7.4.13 del scratchpad, `bash -n`, y la huella SHA256 calculada en PowerShell contra Python).

---

## 1. El servidor OpenSSH en Windows 11 Pro

### 1.1 Instalar y arrancar

- Es una **capacidad opcional** ("Feature on Demand"). Nombre exacto: **`OpenSSH.Server~~~~0.0.1.0`**
  (y `OpenSSH.Client~~~~0.0.1.0`). Comprobar: `Get-WindowsCapability -Online | Where-Object Name -like
  'OpenSSH*'`; instalar: `Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0`
  (devuelve `RestartNeeded : False`). Pide PowerShell **5.1 o más** y una cuenta del grupo
  Administradores. https://learn.microsoft.com/windows-server/administration/openssh/openssh_install_firstuse
  (fuente: `MicrosoftDocs/windowsserverdocs/.../OpenSSH/OpenSSH_Install_FirstUse.md`, ms.date
  04-09-2025, pivote "windows-11").
- El servicio se llama **`sshd`** ("OpenSSH SSH Server"); hay que ponerlo en automático:
  `Start-Service sshd; Set-Service -Name sshd -StartupType 'Automatic'` (misma página). Las claves de
  host se generan solas la primera vez que arranca y viven en `C:\ProgramData\ssh`
  https://learn.microsoft.com/windows-server/administration/openssh/openssh_keymanagement (fuente
  `OpenSSH_KeyManagement.md`, ms.date 03-10-2025).
- **Se actualiza con Windows Update**: «This article uses the in-box OpenSSH Feature on Demand in
  Windows and Windows Server. Microsoft supports and services this version through Windows Update, so
  it's the recommended option for most users», y el fork de GitHub «might differ from the version in
  Windows» (página de instalación). Los binarios de GitHub son "Preview"/"Beta" y se actualizan a mano
  https://github.com/PowerShell/Win32-OpenSSH/releases — **no** se usan.
- Desinstalar: `Remove-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0` y quitar la regla;
  «If the service was in use when you uninstalled it, you should restart Windows» (página de
  instalación).
- Ejecutables: `%systemdrive%\Windows\System32\openssh` (sshd.exe, ssh-keygen.exe…)
  https://learn.microsoft.com/windows-server/administration/openssh/openssh-server-configuration
  (fuente `openssh-server-configuration.md`, ms.date 05-08-2025).

### 1.2 La regla del cortafuegos que crea

- «Installing OpenSSH Server creates and enables a firewall rule named `OpenSSH-Server-In-TCP`. This
  rule allows inbound SSH traffic on port 22» (página de instalación, pivote Windows 11). El script de
  comprobación de Learn, si falta, la crea así: `New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP'
  -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow
  -LocalPort 22` — **sin `-Profile`**, y el valor por defecto de `-Profile` es **`Any`**
  https://learn.microsoft.com/powershell/module/netsecurity/new-netfirewallrule (fuente
  `windows-powershell-docs/.../NetSecurity/New-NetFirewallRule.md`).
- **Qué perfiles tiene la regla que crea la capacidad no está documentado.** El MSI de GitHub la
  cambió en 9.2.2.0 a «apply to Private networks only» (notas de la versión v9.2.2.0p1-Beta en
  https://github.com/PowerShell/Win32-OpenSSH/releases), pero eso es el MSI, no la capacidad.
  **[comprobar en Windows 11]**: `Get-NetFirewallRule -Name OpenSSH-Server-In-TCP | Format-List
  Name,Enabled,Profile,Direction` y su filtro de direcciones/programa. Diseño: **deshabilitarla** y
  poner una propia (§5).

### 1.3 Dónde vive `sshd_config` y cuándo se lee

- `%programdata%\ssh\sshd_config` (o el de `sshd.exe -f`); **si falta, sshd lo genera con los valores
  por defecto al arrancar**; se lee al arrancar el servicio: «Any changes to the configuration file
  require the service to be restarted» (página de configuración). Mismo texto en el wiki:
  https://github.com/PowerShell/Win32-OpenSSH/wiki/sshd_config
- El `sshd_config` por defecto del fork (`contrib/win32/openssh/sshd_config`,
  https://github.com/PowerShell/openssh-portable/blob/latestw_all/contrib/win32/openssh/sshd_config)
  trae `AuthorizedKeysFile .ssh/authorized_keys`, `Subsystem sftp sftp-server.exe` y al final
  `Match Group administrators` → `AuthorizedKeysFile __PROGRAMDATA__/ssh/administrators_authorized_keys`.
  El de la capacidad de Windows 11 debería ser igual o muy parecido **[comprobar en Windows 11]**
  (guardar una copia antes de tocarlo).
- Hay un shell por defecto para las órdenes remotas: `cmd.exe`, o el que diga
  `HKLM\SOFTWARE\OpenSSH\DefaultShell` (página de configuración).
- Desde v9.4.0.0 «the sshd service will check the `$env:ProgramData\ssh` folder permissions upon
  startup» (notas de v9.4.0.0p1-Beta, releases). Con KB5044380 (oct. 2024, Windows 11 23H2) Microsoft
  reconoció que sshd podía no arrancar y dio como arreglo temporal reponer los permisos de
  `C:\ProgramData\ssh` y `\logs` (control total SYSTEM y Administradores, lectura usuarios
  autenticados); 24H2 no estaba afectado
  https://www.neowin.net/news/microsoft-confirms-openssh-issues-in-windows-11-23h2-kb5044380/
  (resumen de buscador). Para `mac.ps1 -Estado`: si `sshd` no arranca, mirar esos permisos.

### 1.4 Las directivas que el diseño quiere usar, en Win32-OpenSSH

Learn y el wiki listan las **no disponibles** en Windows: `AcceptEnv`, `AllowStreamLocalForwarding`,
`AuthorizedKeysCommand(User)`, `AuthorizedPrincipalsCommand(User)`, `ExposeAuthInfo`,
`GSSAPICleanupCredentials`, `GSSAPIStrictAcceptorCheck`, `Hostbased*`, `IgnoreRhosts`,
`IgnoreUserKnownHosts`, `KbdInteractiveAuthentication`, `KerberosAuthentication`, `Kerberos*`,
`PermitTunnel`, `PermitUserEnvironment`, `PermitUserRC`, `PidFile`, `PrintLastLog`, `PrintMotd`,
`RDomain`, `StreamLocalBindMask`, `StreamLocalBindUnlink`, `StrictModes`, `X11DisplayOffset`,
`X11Forwarding`, `X11UseLocalhost`, `XAuthLocation` (página de configuración, "Configuration
arguments"; wiki `sshd_config`, "Not supported"). Todo lo que no está ahí se rige por el manual de
OpenBSD (https://man.openbsd.org/sshd_config; fuente `openssh-portable/sshd_config.5`).

Qué pasa si se escribe una directiva "no disponible": en el código de GitHub, una opción marcada
`sUnsupported` se apunta como «Unsupported option …» con nivel INFO y **se sigue** (no es fatal)
(`servconf.c:2652-2660`,
https://github.com/PowerShell/openssh-portable/blob/latestw_all/servconf.c). Las de la lista se
siguen analizando como siempre en ese código (`case sX11Forwarding`, `case sPermitTunnel`…), o sea
que escribirlas no rompe el arranque, pero **no hacen nada** en Windows. Diseño: **no escribirlas**
(menos cosas que explicar); `PermitTunnel` y X11 no existen en Windows.

| Directiva | En Win32-OpenSSH | Para el túnel | Fuente |
| --- | --- | --- | --- |
| `AllowUsers` | Sí. Nombres **en minúscula** (Windows los compara sin mayúsculas y el código los pasa a minúscula, `servconf.c:4115-4168`); cuentas locales sin dominio; admite `usuario@IP` (ejemplo de Learn: `AllowUsers localuser@192.168.2.23`); desde el código de GitHub también un SID (`servconf.c:1676-1703`) | `AllowUsers bms-tunel@<IP del Mac>` | página de configuración; wiki `sshd_config` |
| `DenyGroups` / `AllowGroups` | Sí (orden: DenyUsers, AllowUsers, DenyGroups, AllowGroups). «To prevent administrators from signing in, use Administrators with the `DenyGroups` directive» | Opcional; con `AllowUsers` de una sola cuenta no hace falta | ídem |
| `Match User` | Sí, mismas reglas de patrones, **minúscula** | `Match User bms-tunel` | ídem |
| `PasswordAuthentication`, `AuthenticationMethods` | Sí; los únicos métodos en Windows son `password` y `publickey` | `PasswordAuthentication no`, `AuthenticationMethods publickey` | ídem |
| `AuthorizedKeysFile` | Sí; relativo al perfil del usuario o **absoluto**; acepta `__PROGRAMDATA__` (lo usa el fichero por defecto) | Un fichero propio en `C:\ProgramData\ssh` (§1.5) | ídem |
| `AllowTcpForwarding local` | No está en la lista de no disponibles; `local` = solo `-L` | Global `no`, en el `Match` `local` | `sshd_config.5`, `.It Cm AllowTcpForwarding` |
| `PermitOpen` | Ídem; formas `host:puerto`, `IPv4:puerto`, `[IPv6]:puerto`; `none` lo prohíbe todo; **sin patrones ni resolución de nombres** | `PermitOpen 127.0.0.1:8765` en el `Match`, `none` global | `sshd_config.5`, `.It Cm PermitOpen` |
| `PermitListen` | Ídem; es para `-R` (reenvío remoto), **no** limita `-L`: lo aclaró el propio proyecto en https://github.com/PowerShell/Win32-OpenSSH/issues/1590 (un `PermitListen 4023` no impedía `-L` a 4024) | `PermitListen none` | `sshd_config.5`; issue 1590 |
| `PermitTTY` | Sí | `no` | `sshd_config.5` |
| `ForceCommand` | Sí, pero el wiki dice «Enforced only on non-PTY sessions. To block PTY access, use PermitTTY="no"». En Windows la orden se lanza con el shell por defecto y `/c` si es `cmd.exe` (`-c` si es otro) (`contrib/win32/win32compat/w32-doexec.c:325-340`) | `ForceCommand exit 1` + `PermitTTY no` | wiki `sshd_config`; código |
| `MaxSessions 0` | No está en la lista; en OpenSSH «setting it to 0 will prevent all shell, login and subsystem sessions while still permitting forwarding» | **`MaxSessions 0`**: ni shell, ni orden, ni sftp; el reenvío sí | `sshd_config.5`, `.It Cm MaxSessions` |
| `DisableForwarding` | Existe, pero lo apaga **todo**, también el TCP que se necesita; además hasta OpenSSH 10.0 no apagaba X11 ni el agente (CVE-2025-32728, https://nvd.nist.gov/vuln/detail/CVE-2025-32728) | **No usar** | `sshd_config.5`; NVD |
| `AllowAgentForwarding`, `GatewayPorts` | Sí | `no` | `sshd_config.5` |
| `Subsystem sftp` | Viene puesto por defecto | **Quitarlo** (y `MaxSessions 0` + `ForceCommand` lo cubren igualmente: «This applies to shell, command, or subsystem execution») | `sshd_config.5`, `.It Cm ForceCommand` |
| `SyslogFacility`, `LogLevel` | `AUTH` (por defecto) → ETW, se ve en el Visor de eventos (OpenSSH/Operational); `LOCAL0` → ficheros en `%programdata%\ssh\logs` | `AUTH` y `LogLevel VERBOSE` (apunta la huella de la clave usada; nunca un secreto) | página de configuración; https://github.com/PowerShell/Win32-OpenSSH/wiki/Logging-Facilities |
| `StrictModes` | En la lista de "no disponibles", **pero** en el código de GitHub es justo lo que activa la comprobación de la ACL del fichero de claves en Windows (`auth2-pubkeyfile.c:469-484`: `if (strict_modes && check_secure_file_permission(file, pw, 1) != 0) … "Authentication refused."`) | **No tocarlo** (por defecto `yes`) | código |
| `PermitRootLogin` | No aplica en Windows | — | página de configuración |

Además, `ForceCommand` «does not limit other kinds of access that a client may request via their
connection, such as TCP, agent, socket or X11 forwarding» (`sshd_config.5`): por eso los límites del
reenvío van aparte (`AllowTcpForwarding`, `PermitOpen`, `PermitListen`) y en la clave (§1.6).

Ejemplo de `sshd_config` completo en `ejemplos/sshd_config.ejemplo` (idea: todo cerrado globalmente y
un `Match User bms-tunel` que solo abre `AllowTcpForwarding local` + `PermitOpen 127.0.0.1:8765`).
**No se ha podido pasar por `sshd -t`** (§0) → **[comprobar en Windows 11]** con
`sshd.exe -t` y `sshd.exe -T -C user=bms-tunel,host=mac,addr=<IP del Mac>` (muestra lo efectivo para
esa conexión; `-C` es de OpenSSH, https://man.openbsd.org/sshd).

### 1.5 `administrators_authorized_keys` frente a `~/.ssh/authorized_keys`, y la ACL

- **Usuario estándar**: `C:\Users\<usuario>\.ssh\authorized_keys`. **Administrador**:
  `C:\ProgramData\ssh\administrators_authorized_keys` en lugar del de su perfil («You must use it
  instead of the user-specific file»), con ACL solo SYSTEM y Administradores:
  `icacls.exe "C:\ProgramData\ssh\administrators_authorized_keys" /inheritance:r /grant
  "Administrators:F" /grant "SYSTEM:F"`; en Windows en otro idioma, **por SID** (`*S-1-5-32-544`)
  (página de claves). Lo hace el `Match Group administrators` del fichero por defecto (§1.3).
- **La cuenta del túnel debe ser estándar**: si fuera administradora le tocaría el fichero de
  administradores y tendría derechos de administrador.
- **Fichero propio en `C:\ProgramData\ssh`** (p. ej. `bms_tunel_authorized_keys`) con
  `AuthorizedKeysFile` absoluto: las claves no dependen del perfil de la cuenta del túnel y **la cuenta
  no puede cambiarlas**. Qué exige el código de Windows a un fichero de claves
  (`contrib/win32/win32compat/w32-sshfileperm.c:65-170`,
  `check_secure_file_permission(file, pw, read_ok=1)`):
  - dueño: Administradores, SYSTEM, el propio usuario o TrustedInstaller («Bad owner» si no);
  - ninguna otra cuenta con derechos de **escritura** (escribir, añadir, atributos, `WRITE_DAC`,
    `WRITE_OWNER`, `DELETE`); con `read_ok` se permite que otros **lean**.
  - El wiki lo dice igual: «This file should not be owned by, nor provide access to any other user»,
    y da `icacls … /inheritance:r`
    https://github.com/PowerShell/Win32-OpenSSH/wiki/Security-protection-of-various-files-in-Win32-OpenSSH
  - Propuesta: dueño Administradores, ACL **solo** `*S-1-5-18:F` (SYSTEM) y `*S-1-5-32-544:F`
    (Administradores), sin herencia; la cuenta del túnel sin ningún permiso. Funciona igual que
    `administrators_authorized_keys`, que también es solo SYSTEM/Administradores y lo lee sshd
    **[comprobar en Windows 11]** que sshd lee un fichero absoluto así para un usuario estándar (lo
    esperable: el monitor de sshd corre como SYSTEM, ver §2).
- Las **claves de host** tienen que ser de SYSTEM o Administradores y nadie más con acceso (wiki de
  permisos). Leer la **pública** (`ssh_host_ed25519_key.pub`) para enseñar la huella se hace desde el
  `mac.ps1 -Instalar` elevado.

### 1.6 Las opciones de `authorized_keys`, y cómo se combinan con `PermitOpen`

Del manual de sshd (sección AUTHORIZED_KEYS FILE FORMAT, https://man.openbsd.org/sshd; fuente
`openssh-portable/sshd.8:560-710`):

- `restrict`: «disable port, agent and X11 forwarding, as well as disabling PTY allocation and
  execution of `~/.ssh/rc`. If any future restriction capabilities are added to authorized_keys files,
  they will be included in this set.»
- `port-forwarding`: «Enable port forwarding previously disabled by the `restrict` option.»
- `permitopen="host:port"`: limita `-L` a ese destino; varias separadas por comas; «No pattern matching
  or name lookup is performed on the specified hostnames, they must be literal host names and/or
  addresses.»
- `from="pattern-list"`: además de la clave, la IP (o el nombre) del cliente tiene que estar en la
  lista; admite CIDR. Su propósito: que una clave robada no sirva desde cualquier sitio.
- `command="…"`: se ejecuta en lugar de lo que pida el cliente; «applies to shell, command or
  subsystem execution»; `ForceCommand` de `sshd_config` gana sobre ella.
- **Las dos listas se cruzan**: en `channel_connect_to_port` (`channels.c:5026` y siguientes,
  https://github.com/openssh/openssh-portable/blob/master/channels.c) un `-L` pasa solo si lo permite
  la lista del usuario (`permitopen` de la clave) **y** la del administrador (`PermitOpen` del
  `sshd_config`); si no: «Received request … to connect to host … but the request was denied» y
  `SSH2_OPEN_ADMINISTRATIVELY_PROHIBITED`. Como no hay resolución de nombres, el Mac tiene que pedir
  literalmente `127.0.0.1:8765` (si pidiera `localhost:8765` se denegaría).
- Línea propuesta (la escribe el script, nunca la pega el dueño con opciones):
  `restrict,port-forwarding,permitopen="127.0.0.1:8765",from="<IP del Mac>",command="exit 1" ssh-ed25519 AAAA…`
- Estas opciones son código común de OpenSSH (`auth-options.c`), no del port de Windows, y no salen en
  la lista de no disponibles; nada en el wiki dice que Windows las trate distinto. **[comprobar en
  Windows 11]** que un `-L` a otro puerto da "administratively prohibited" y que `ssh … ` sin `-N`
  no abre nada (§8).
- Riesgo conocido relacionado: «the `restrict` option in authorized_keys doesn't block tunnel
  forwarding, but only when tunnel forwarding is enabled on the server» (CVE-2026-73283 /
  CVE-2026-106586, arreglado en OpenSSH 10.5/10.6; mitigación: `PermitTunnel no`)
  https://access.redhat.com/security/cve/CVE-2026-106586 (resumen de buscador). En Windows
  `PermitTunnel` no está disponible (no hay tun), así que no aplica.

### 1.7 Qué corre, como quién, con `ForceCommand` y `MaxSessions 0`

- Con `ssh -N` el cliente **no abre ninguna sesión**, solo canales de reenvío
  (`-N`: «Do not execute a remote command. This is useful for just forwarding ports»,
  https://man.openbsd.org/ssh; fuente `ssh.1`). Así que en uso normal ni `ForceCommand` ni el shell
  llegan a ejecutarse.
- Si alguien con la clave pidiera una sesión: `MaxSessions 0` la rechaza; si aun así se abriera,
  `ForceCommand exit 1` (o `command="exit 1"` de la clave) ejecuta `"cmd.exe" /c exit 1` como la cuenta
  del túnel y termina (`w32-doexec.c:336-337`; `exit 1` vale también en PowerShell si alguien cambiara
  `DefaultShell`). `PermitTTY no` cubre la advertencia del wiki sobre PTY.

### 1.8 La versión que trae Windows 11 hoy

- **No hay lista oficial**. En el issue abierto para eso
  (https://github.com/PowerShell/Win32-OpenSSH/issues/2053) un usuario resume en febrero de 2026 que
  sigue sin haberla. Datos sueltos (no oficiales): Windows 11 22H2/23H2 con `8.6p1` (tabla de un
  usuario sacada de las ISO, junio de 2024); Windows 11 24H2 con `OpenSSH_for_Windows_9.5p1, LibreSSL
  3.8.2` (vía Reddit, en el mismo issue); otros informes de usuarios dan `9.5p2` (resumen de
  buscador). Las actualizaciones llegan a veces en el acumulado mensual sin anunciarlo (comentarios
  del mismo issue).
- GitHub va por delante: última `10.4.0.0p1-Preview` (20-10-2026) y el código ya dice
  `OpenSSH_for_Windows_10.5` (releases; `version.h`).
- Para el diseño: lo que se usa existe desde hace años en OpenSSH (`PermitListen` desde 7.8,
  `AllowTcpForwarding local`, `restrict`, `PubkeyAcceptedAlgorithms` desde 8.5), así que vale con 9.5.
  **[comprobar en Windows 11]**: `& "$env:WINDIR\System32\OpenSSH\sshd.exe" -V` (o `ssh -V`) y la
  versión de fichero; `mac.ps1 -Estado` la enseña.

### 1.9 Registro

- Por defecto a ETW: Visor de eventos → Registros de aplicaciones y servicios → OpenSSH → Operational
  (INFO) y Admin (errores) https://github.com/PowerShell/Win32-OpenSSH/wiki/Logging-Facilities. Se lee
  con `Get-WinEvent -LogName OpenSSH/Operational` (nombre del registro **[comprobar en Windows 11]**).
- Con `LogLevel VERBOSE` sshd apunta «Accepted publickey for … from <IP> … ED25519 SHA256:…» (la
  huella, no la clave) y cada denegación de reenvío (`channels.c`). Nada de eso es un secreto.

---

## 2. La conexión reenviada: quién la abre y si llega al puerto de Docker Desktop

- **Quién la abre.** El diseño de Win32-OpenSSH: «SSHD listener runs as System … spawns a worker to
  process and incoming connection. The worker acts as a privileged monitor, further spawning an
  unprivileged child (running as "sshd") to process unauthenticated network data. Once the connection
  is authentication, unprivileged child exits, and the privileged monitor spawns one more worker
  running in the context of the authenticated user»
  https://github.com/PowerShell/Win32-OpenSSH/wiki/About-Win32-OpenSSH-and-Design-Details. Los
  canales `direct-tcpip` (los `-L`) los atiende ese proceso: **la conexión a `127.0.0.1:8765` la abre
  un proceso que corre como la cuenta del túnel**, lanzado por un servicio, o sea en la **sesión 0**
  (la de los servicios), no en la de «bms» ni en la del dueño.
- **Con qué token.** Con clave, Win32-OpenSSH hace un inicio de sesión **S4U de tipo red**
  (`LsaLogonUser(…, Network, …)` con `MsV1_0S4ULogon`,
  `contrib/win32/win32compat/win32_usertoken_utils.c:116-238`, línea 230); con contraseña,
  `LOGON32_LOGON_NETWORK_CLEARTEXT` (línea 858). Y carga el perfil del usuario con `LoadUserProfileW`
  (línea 458); si el perfil no existe, «it gets created upon first logon via ssh» (página de diseño).
  Learn: «A remote session opened via key-based authentication doesn't have associated user
  credentials … This behavior is by design» (página de claves). Abrir un socket TCP no necesita
  credenciales.
- **Quién escucha en 8765.** En Docker Desktop para Windows, el puerto publicado lo escucha el proceso
  del backend: «Docker Desktop's backend process listens on the specified host port … When an
  application such as a web browser connects to that port, Docker Desktop forwards the connection into
  the Linux VM» y, con WSL 2, la red la lleva `com.docker.backend.exe`
  https://docs.docker.com/desktop/features/networking/ (fuente
  `docker/docs/content/manuals/desktop/features/networking/_index.md`). Con `"127.0.0.1:8765:8765"`
  escucha solo en el bucle local IPv4. (No es `wslrelay`: ese es el reenvío de localhost de las
  distribuciones de WSL, no el de los puertos publicados de Docker Desktop.)
- **¿Llega un proceso de la sesión 0 (cuenta del túnel) a un puerto que escucha un proceso de la
  sesión de «bms»?** **No hay documentación de Docker ni de Microsoft que lo diga expresamente.** Lo
  que hay apunta a que sí: en Windows la pila TCP es del equipo, no de la sesión (Citrix necesita una
  función propia, "virtual loopback", precisamente porque dos sesiones que escuchan en el mismo puerto
  chocan: https://docs.citrix.com/en-us/citrix-virtual-apps-desktops/manage-deployment/virtual-ip-virtual-loopback.html;
  y en entornos de varios usuarios «it's difficult to prevent malicious users from connecting to other
  user's TCP tunnels», https://jpassing.com/2021/01/07/how-iap-desktop-protects-tcp-tunnels), ambos
  como resumen de buscador. El aislamiento de bucle local de Windows es de las apps AppContainer
  (UWP), y sshd no lo es. **[comprobar en Windows 11]**. Nota: **§4.2 del diseño ya depende de lo
  mismo** (el dueño, con su cuenta, abre `127.0.0.1:8765` mientras Docker Desktop corre en la sesión de
  «bms»); si eso funciona, lo del túnel también, salvo algo propio de la sesión 0 que no se ha
  encontrado. Prueba en el mini PC: con la sesión de «bms» bloqueada, `ssh -N -L …` desde el Mac y
  `curl -sI http://127.0.0.1:8765/app` en el Mac.
- **Docker no se puede manejar desde la cuenta del túnel**: «When Docker Desktop launches, all
  non-privileged named pipes are created so that only the following users can access them: The user
  that launched Docker Desktop. Members of the local Administrators group. The LOCALSYSTEM account»
  https://docs.docker.com/desktop/setup/install/windows-permission-requirements/ (fuente
  `docker/docs/.../windows-permission-requirements.md:43-46`). Bien: la cuenta del túnel no es ninguna
  de las tres.
- **El cortafuegos no se mete**: el tráfico de `127.0.0.1` no lo filtra (ya lo dice
  `docs/instalacion-nativa.md:405-407` del repositorio para la variante nativa).
- **Variante nativa**: la consola escucha en `127.0.0.1:8765` con el usuario de la instalación; el
  túnel llega igual. Y sshd **no abre un hueco nuevo** de los que describe
  `docs/instalacion-nativa.md:400-410` («hablar con otro programa que escuche en 127.0.0.1 y reenvíe a
  internet… un túnel SSH»): un programa local que conecte a `127.0.0.1:22` no tiene clave, `AllowUsers
  bms-tunel@<IP del Mac>` lo rechaza por origen, y aun autenticado solo podría ir a `127.0.0.1:8765`
  (`PermitOpen`) y nunca escuchar (`PermitListen none`).

---

## 3. La cuenta local solo para el túnel

- **Crearla**: `New-LocalUser -Name bms-tunel -Password <SecureString> -PasswordNeverExpires
  -AccountNeverExpires -UserMayNotChangePassword -Description …` (parámetros documentados en
  https://learn.microsoft.com/powershell/module/microsoft.powershell.localaccounts/new-localuser?view=powershell-5.1;
  fuente `PowerShell-Docs/reference/5.1/Microsoft.PowerShell.LocalAccounts/New-LocalUser.md`).
  Contraseña: 32 bytes del generador del sistema en base64 (+ un sufijo con mayúscula, cifra y signo
  por si la directiva pide complejidad), convertida a `SecureString` y tirada; no se escribe en ningún
  sitio (ejemplo en `ejemplos/mac-ejemplos.ps1`, `Contrasena-Que-Nadie-Guarda`). Se pone
  `PasswordNeverExpires` aunque nadie la use: una contraseña caducada podría estorbar al inicio de
  sesión S4U **[comprobar en Windows 11]**; con una contraseña, además, no entra en juego la directiva
  de "contraseñas en blanco solo en consola".
- **¿Necesita sshd su contraseña?** **No.** Con clave, Win32-OpenSSH hace S4U (§2): no guarda ni pide
  contraseña, y la sesión no lleva credenciales (Learn, página de claves). Si alguien cambia la
  contraseña, el túnel sigue (al revés que la cuenta «bms» de §4.2, que sí la necesita para el inicio
  automático).
- **Ningún grupo**: `New-LocalUser` no mete la cuenta en ningún grupo (la documentación no dice que lo
  haga; para eso está `Add-LocalGroupMember`) **[comprobar en Windows 11]** con
  `Get-LocalGroupMember -SID S-1-5-32-545` (el parámetro `-SID` está documentado:
  `Get-LocalGroupMember.md:108`). Eso ya le quita el inicio de sesión local: «Allow log on locally»
  (`SeInteractiveLogonRight`) lo tienen por defecto Administradores, Operadores de copia y **Usuarios**
  https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/security-policy-settings/allow-log-on-locally
  (resumen de buscador); y el de Escritorio remoto lo tienen Administradores y "Usuarios de escritorio
  remoto". `Grupos-De-La-Cuenta` del ejemplo comprueba por SID que no está en 544, 545, 555 ni 551.
- **Negarlo además, a propósito** (Windows 11 Pro tiene `secpol.msc`): "Denegar el inicio de sesión
  local" (`SeDenyInteractiveLogonRight`) y "Denegar el inicio de sesión a través de Servicios de
  Escritorio remoto" (`SeDenyRemoteInteractiveLogonRight`), por `secedit /export` +
  `/configure /areas USER_RIGHTS`. **Nunca** "Denegar el acceso desde la red"
  (`SeDenyNetworkLogonRight`): el S4U de sshd es de **tipo red** (`win32_usertoken_utils.c:230`) y lo
  cortaría. Por la misma razón la cuenta necesita "Tener acceso a este equipo desde la red"
  (`SeNetworkLogonRight`), que por defecto tiene **Todos** **[comprobar en Windows 11]** con `secedit
  /export`. Tocar la directiva local con `secedit` es delicado; propuesta: lo hace `-Instalar` solo si
  el dueño lo acepta, y si no, basta con no estar en ningún grupo.
- **Ocultarla de la pantalla de inicio**: valor DWORD con el nombre exacto de la cuenta y `0` en
  `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList`; se quita
  borrando el valor; la cuenta sigue funcionando y se puede escribir a mano en "Otro usuario". No es
  documentación oficial de Microsoft, sino práctica conocida (p. ej.
  https://learn.microsoft.com/en-us/answers/questions/1281830/how-to-remove-user-account-from-windows-logon-scre,
  resumen de buscador). Sin pertenecer a Usuarios quizá ni salga **[comprobar en Windows 11]**.
- **Grupos por SID** (Windows del dueño puede estar en neerlandés): Learn recomienda el SID en `icacls`
  para sistemas no ingleses (`*S-1-5-32-544`) (página de claves). SYSTEM `S-1-5-18`, Administradores
  `S-1-5-32-544`, Usuarios `S-1-5-32-545`.
- **Quitarla** (`-Quitar`): `Remove-LocalUser`, su perfil (`Win32_UserProfile` por SID) y el valor de
  `UserList`.

---

## 4. macOS

### 4.1 El cliente ssh que trae

- macOS trae OpenSSH de Apple con LibreSSL 3.3.6. Versiones según informes (no hay tabla de Apple):
  macOS 15.0 Sequoia, `OpenSSH 9.8p1`
  (https://applech2.com/archives/20240917-openssh-9-8p1-on-macos-15-sequoia.html, resumen de
  buscador); macOS 26 Tahoe, `OpenSSH_10.0p2, LibreSSL 3.3.6` en octubre de 2025
  (https://lists.mindrot.org/pipermail/openssh-unix-dev/2025-October/042265.html) y `10.0p1` en 26.3
  según una guía de terceros. Con OpenSSH 10 Apple quitó DSA. **[comprobar en macOS]** con
  `/usr/bin/ssh -V`. Todo lo que usa el diseño (`-N`, `ExitOnForwardFailure`, `HostKeyAlias`,
  ed25519) existe desde mucho antes.
- **Usar siempre `/usr/bin/ssh` y `/usr/bin/ssh-add`**: si hay un OpenSSH de Homebrew antes en el
  `PATH`, no conoce las opciones de Apple (`UseKeychain`, `--apple-use-keychain`) y falla; GitHub lo
  documenta para `ssh-add` («illegal option -- apple-use-keychain» → usar `/usr/bin/ssh-add`)
  https://docs.github.com/en/authentication/troubleshooting-ssh/error-ssh-add-illegal-option----apple-use-keychain
  (resumen de buscador).

### 4.2 La clave ed25519 con frase guardada en el Llavero

- `ssh-keygen -t ed25519 -a 100 -f ~/.bms-tunel/clave_ed25519 -C "bms-tunel mac"` (comentario
  genérico: sin nombres ni correos). Pide la frase dos veces.
- Llavero: Apple introdujo **`UseKeychain`** en `ssh_config`; desde macOS 10.12.2 está apagado por
  defecto y hay que poner `UseKeychain yes`; para que el agente cargue la clave, `AddKeysToAgent yes`;
  y para configuraciones compartidas con otros OpenSSH, `IgnoreUnknown UseKeychain`
  https://developer.apple.com/library/archive/technotes/tn2449/_index.html (TN2449). Alternativa
  explícita: `/usr/bin/ssh-add --apple-use-keychain ~/.bms-tunel/clave_ed25519` (en macOS 12 y
  siguientes; antes `-K`, ahora obsoleto) (enlace de GitHub de §4.1).
- La frase protege la clave en reposo (copias, Time Machine); mientras la sesión del Mac está abierta
  el Llavero la da sin preguntar. **[comprobar en macOS]** que la primera conexión pide la frase en la
  ventana de Terminal y que la segunda ya no.

### 4.3 Configuración aislada y la huella del host fijada

- `ssh -F <fichero>`: «If a configuration file is given on the command line, the system-wide
  configuration file (/etc/ssh/ssh_config) will be ignored» y tampoco se lee `~/.ssh/config`
  (https://man.openbsd.org/ssh, `-F`). Así lo del túnel no se mezcla con lo que el dueño tenga.
  Ejemplo en `ejemplos/ssh_config.ejemplo`.
- Opciones (https://man.openbsd.org/ssh_config; fuente `ssh_config.5`):
  `HostKeyAlias bms-minipc` (la huella se guarda con el alias, no con la IP: si la IP cambia no hay
  "host desconocido"), `UserKnownHostsFile ~/.bms-tunel/known_hosts`, `StrictHostKeyChecking yes`
  («never automatically add host keys … and refuses to connect to hosts whose host key has
  changed»), `HostKeyAlgorithms ssh-ed25519`, `IdentitiesOnly yes`, `LocalForward 127.0.0.1:8765
  127.0.0.1:8765` (dirección de escucha explícita; por defecto el cliente ya escucha solo en el bucle
  local, `GatewayPorts no`), `ExitOnForwardFailure yes` («terminate the connection if it cannot set up
  all requested … local … port forwardings (e.g. if either end is unable to bind and listen on a
  specified port)»), `ServerAliveInterval 15` + `ServerAliveCountMax 3` (corta a los ~45 s si el
  mini PC no contesta), `ForwardAgent no`, `PermitLocalCommand no`. `-N` en la línea de órdenes mejor
  que `SessionType none` (que es de OpenSSH 8.7+).
- **Fijar la huella la primera vez** (sin "yes" a ciegas): `mac.ps1` enseña en el mini PC la huella
  SHA256 de `ssh_host_ed25519_key.pub`; `preparar.command` hace `ssh-keyscan -t ed25519 <IP>`
  (https://man.openbsd.org/ssh-keyscan), calcula la huella (`ssh-keygen -l -f <fichero>`), la enseña y
  pide al dueño que confirme que es la misma que ve en el mini PC; solo entonces escribe
  `bms-minipc ssh-ed25519 AAAA…` en `~/.bms-tunel/known_hosts`. `ssh-keyscan` no autentica nada: por eso
  la comparación a ojo es la que vale.
- **Huella en PowerShell sin `ssh-keygen`**: es `"SHA256:" + base64(SHA-256(blob))` sin los `=` del
  final, donde el blob es lo que va en base64 en la línea `.pub` (`fingerprint_b64` en
  https://github.com/openssh/openssh-portable/blob/master/sshkey.c: «Trim padding characters from
  end»). Función `Huella-Sha256` en `ejemplos/mac-ejemplos.ps1`, comprobada aquí contra Python con un
  vector (anexo A). Así `mac.ps1` no depende de que esté instalado el cliente OpenSSH.
- **La clave pública del Mac al mini PC**: no comparten portapapeles. Es pública, pero su integridad
  importa (quien la cambie por la suya entra). Propuesta: `preparar.command` la deja en un fichero y
  enseña su huella; el dueño la lleva (memoria USB, correo a sí mismo…), `mac.ps1 -AnadirClave` la
  valida (solo `ssh-ed25519 <base64> [comentario]`, blob de 51 bytes = 4+11+4+32, sin opciones delante;
  `Clave-Publica-Valida` del ejemplo) y enseña su huella; el dueño compara las dos pantallas.

### 4.4 Los ficheros `.command`

- Un fichero `nombre.command` con órdenes de shell se abre con doble clic en Terminal y se ejecuta; si
  no tiene el bit de ejecución, Terminal dice que no hay permisos y hay que hacer `chmod u+x`
  (varias respuestas de Apple Community, p. ej. https://discussions.apple.com/thread/7454656; resumen
  de buscador) **[comprobar en macOS]** el texto exacto y si la ventana se queda abierta al terminar
  (depende del perfil de Terminal).
- El intérprete: `#!/bin/bash` es el bash 3.2 de Apple (sin arrays asociativos ni `${v,,}`)
  **[comprobar en macOS]** con `/bin/bash --version`. El boceto `ejemplos/abrir-bms.ejemplo.sh` pasa
  `bash -n` y `bash --posix -n` aquí.
- **El bit de ejecución viaja en git** (modo `100755`) y **en el ZIP de GitHub**: `git archive
  --format=zip` guarda el modo Unix de los ejecutables en los atributos externos con "creator
  version" Unix (`0x0317`) (`archive-zip.c:331-336`,
  https://github.com/git/git/blob/master/archive-zip.c). Que el botón "Download ZIP" de GitHub use
  `git archive` y que la Utilidad de Archivo de macOS respete el modo: **[comprobar en macOS]**. Hoy
  el repositorio no tiene ningún fichero `100755` (`git ls-files -s`); los `mac/*.command` serían los
  primeros (`git update-index --chmod=+x`).

### 4.5 Cuarentena y Gatekeeper

- Los ficheros que crea una app con cuarentena (navegadores, Mail…) llevan `com.apple.quarantine`
  (`LSFileQuarantineEnabled`: «whether the files this app creates are quarantined by default»,
  https://developer.apple.com/documentation/bundleresources/information-property-list/lsfilequarantineenabled).
  Un ZIP bajado con Safari la lleva, y lo que se descomprime con la Utilidad de Archivo la hereda
  **[comprobar en macOS]**.
- **macOS 15 Sequoia** quitó el atajo de Control-clic → Abrir: «users will no longer be able to
  Control-click to override Gatekeeper when opening software that isn't signed correctly or
  notarized. They'll need to visit System Settings > Privacy & Security»
  https://developer.apple.com/news/?id=saqachfa (06-08-2024). Un informe de terceros lo reproduce con
  un `.command` de un ZIP bajado en Safari: doble clic → rechazo, clic derecho → Abrir → el mismo
  rechazo sin botón; se arregla con "Abrir igualmente" en Ajustes → Privacidad y seguridad o con
  `xattr -d com.apple.quarantine <fichero>` https://github.com/Ninja-FSE/dccore-dev/issues/662.
- **`git clone` desde Terminal**: git es una herramienta de línea de órdenes, no una app con
  cuarentena, así que lo que escribe no debería llevarla **[comprobar en macOS]** con `xattr -l`. En
  el Mac, `/usr/bin/git` pide instalar las Command Line Tools la primera vez. **GitHub Desktop**: no se
  ha encontrado si marca lo que clona **[comprobar en macOS]**. Además el repositorio podría ser
  privado: el dueño tendría que entrar en GitHub en el Mac.
- **Forma segura y sencilla** para el dueño, sea cual sea el origen: abrir Terminal, escribir `bash `,
  arrastrar `preparar.command` a la ventana y pulsar Intro. Pasarle el fichero a bash no lo "abre"
  Launch Services ni lo ejecuta como programa en cuarentena, así que Gatekeeper no interviene
  **[comprobar en macOS]**. Después `preparar.command` puede quitar la cuarentena **solo** de
  `abrir-bms.command` (`xattr -d com.apple.quarantine`, sin `-r` sobre carpetas enteras) y ponerle
  `chmod u+x`. Copiar la carpeta desde una memoria USB con el Finder no añade cuarentena
  **[comprobar en macOS]**.

### 4.6 La red local desde el Mac

- **Privacidad de red local (macOS 15+)**: TN3179 dice que macOS permite la red local sin preguntar a
  «Command-line tools run from Terminal or over SSH, including any child processes they spawn»
  https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy
  (fuente: el JSON de la página). Un `.command` corre en Terminal: `ssh` no debería pedir permiso. El
  tráfico a `127.0.0.1` no es "red local" (la red local es la de una interfaz con difusión: Wi-Fi o
  Ethernet), así que el navegador tampoco. Resolver un nombre `.local` sí es operación de red local
  (misma TN). Hay un informe de que tras actualizar a Tahoe 26.3 no se llegaba por ssh a ningún equipo
  de la red y la causa era un fichero de escucha viejo en `/private/tmp`
  (https://discussions.apple.com/thread/256252831, resumen de buscador): para la guía de problemas,
  `ssh -vvv`.
- **El nombre del mini PC**: Windows trae mDNS nativo desde Windows 10 1703 y una regla
  "mDNS (UDP-In)" en el cortafuegos
  (https://techcommunity.microsoft.com/blog/networkingblog/mdns-in-the-enterprise/3275777, resumen de
  buscador), pero **no se ha encontrado** documentación de que Windows 11 conteste a
  `<nombre>.local` desde un Mac de forma fiable, y con la red como Pública la regla puede no aplicar.
  **Recomendación: IP fija por reserva DHCP en el router para el mini PC** (y para el Mac, porque la
  regla del cortafuegos, `AllowUsers` y `from=` la usan). Con `HostKeyAlias` la identidad del mini PC
  la da la huella, no el nombre ni la IP.
- **Ojo con la "Dirección Wi-Fi privada" del Mac** (macOS 15+): por red puede ser Desactivada, Fija o
  Rotatoria; la rotatoria «changes to a different private address every two weeks»; las redes
  WPA2/WPA3 van por defecto en Fija, y la dirección cambia si se borran los ajustes de red
  https://support.apple.com/102509 (resumen de buscador). Con Rotatoria la reserva DHCP del Mac se
  pierde cada dos semanas y el túnel deja de entrar (el cortafuegos tira los paquetes). Acción del
  dueño: en esa red, Fija (y reservar esa dirección) o Desactivada; o Ethernet.

### 4.7 El navegador del Mac: `http://127.0.0.1:8765` es contexto seguro

- Por la especificación, un origen con host `127.0.0.0/8`, `::1` o `localhost` es "potentially
  trustworthy" y la página es contexto seguro aunque vaya por `http`
  https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Secure_Contexts (fuente
  `mdn/content/.../secure_contexts/index.md`).
- **Safari (WebKit)**: `shouldTreatAsPotentiallyTrustworthy` da verdadero si
  `SecurityOrigin::isLocalHostOrLoopbackIPAddress(host)`, que acepta `127.*.*.*`, `[::1]` y `localhost`
  (`Source/WebCore/page/SecurityOrigin.cpp:68-110` y `641-650`,
  https://github.com/WebKit/WebKit/blob/main/Source/WebCore/page/SecurityOrigin.cpp).
- **Importa para la app**: `frontend/src/lib/api.ts:380-382` usa `crypto.randomUUID()`, que **solo
  existe en contexto seguro** (MDN, `{{SecureContext_header}}` en
  https://developer.mozilla.org/en-US/docs/Web/API/Crypto/randomUUID) y está en Chrome 92, Firefox 95 y
  **Safari 15.4** (`mdn/browser-compat-data/api/Crypto.json`). `navigator.clipboard.writeText`
  (`ai-actions.tsx:179`) también pide contexto seguro
  (https://developer.mozilla.org/en-US/docs/Web/API/Clipboard/writeText, `{{securecontext_header}}`
  en su fuente de `mdn/content`). Con `127.0.0.1` todo eso funciona; con la IP de
  la red (`http://192.168.x.y:8765`) no funcionaría, otra razón (además de `host_permitido`) para el
  túnel. Requisito: Safari 15.4 o más **[comprobar en macOS]** con la app de verdad (Procesar, copiar).
- **Chrome 154 (octubre de 2026)** avisa antes de abrir HTTP por defecto, pero solo para sitios
  públicos; la guía de Chromium dice que `http://localhost` cuenta como seguro y no avisa
  https://chromium.googlesource.com/chromium/src/+/main/docs/security/ask-before-http/ask-before-http-adoption-guide.md
  y https://blog.google/security/https-by-defau/ (resumen de buscador). Que tampoco avise con
  `127.0.0.1` es lo esperable (es bucle local) pero no está dicho **[comprobar en macOS]**.
- **Qué se queda en el Mac**: las respuestas de la API van con `Cache-Control: no-store`
  (`serve.py:516,615,938`; `consola.py:49`), así que la caché del navegador no guarda datos; los PDF
  descargados sí (el dueño lo aceptó). La página y su token de sesión viven en memoria
  (`frontend/src/lib/session.tsx:1-3`).

---

## 5. El cortafuegos de Windows

- **Regla propia** con `New-NetFirewallRule`: `-Direction Inbound -Action Allow -Protocol TCP
  -LocalPort 22 -Program "$env:WINDIR\System32\OpenSSH\sshd.exe" -Profile Private -RemoteAddress <IP
  del Mac>` (ejemplo `Poner-Regla`). Parámetros de
  https://learn.microsoft.com/powershell/module/netsecurity/new-netfirewallrule:
  - `-Profile`: «The rule is active on the local computer only when the specified profile is currently
    active … Only one profile is applied at a time»; valores `Any, Domain, Private, Public`; por
    defecto `Any`.
  - `-RemoteAddress`: una IPv4/IPv6, subred, rango o palabra clave (`LocalSubnet`, `Intranet`…; con `4`
    o `6` al final se limita a esa familia, p. ej. `LocalSubnet4`).
  - `-Program`: la ruta completa del ejecutable.
- **IP concreta mejor que `LocalSubnet`**: `LocalSubnet` son las subredes de **todas** las interfaces,
  también las virtuales (vEthernet de WSL/Hyper-V) **[comprobar en Windows 11]** qué incluye con
  `Get-NetIPAddress`. Con la IP del Mac hace falta la reserva DHCP (§4.6); `LocalSubnet4` como reserva
  si el dueño no puede reservar.
- **Red marcada como Pública**: la regla de solo Privado no aplica y la entrada se bloquea (el tráfico
  entrante sin regla se bloquea por defecto); el túnel no abre: falla cerrado. La categoría se ve con
  `Get-NetConnectionProfile` y se cambia con `Set-NetConnectionProfile -NetworkCategory Private`
  («*Private* - Networks at home or work, where you know and trust the people and devices on the
  network»; `DomainAuthenticated` no se puede poner a mano)
  https://learn.microsoft.com/powershell/module/netconnection/set-netconnectionprofile (fuente
  `Set-NetConnectionProfile.md`), o en Configuración → Red e Internet → Ethernet → Tipo de perfil de
  red. `mac.ps1 -Estado` debería decirlo.
- **La regla de Microsoft**: deshabilitar `OpenSSH-Server-In-TCP` (no borrarla: si Windows la repone
  al actualizar la capacidad, `-Estado` lo ve) **[comprobar en Windows 11]** si una actualización la
  vuelve a habilitar.
- **Tres capas para la misma idea** ("solo el Mac"): cortafuegos (`-RemoteAddress`), `AllowUsers
  bms-tunel@<IP>` y `from="<IP>"` en la clave. Si la IP del Mac cambia, fallan las tres a la vez (sin
  mensaje en el Mac más que un tiempo de espera): `abrir-bms.command` debería decir "¿ha cambiado la
  IP del Mac?" y `mac.ps1 -Estado` enseñar la IP configurada.
- Opcional: `AddressFamily inet` en sshd (solo IPv4), para que la regla y `AllowUsers` con IPv4 no
  tengan una puerta IPv6 al lado.

---

## 6. Riesgos conocidos de tener sshd en Windows

| Qué | Afecta | Estado | Fuente |
| --- | --- | --- | --- |
| **regreSSHion** CVE-2024-6387 (RCE previa a la autenticación, Linux/glibc) y CVE-2024-6409 | Microsoft: «Although Windows contains an OpenSSH component, the vulnerable code cannot be exploited or controlled by an adversary» | **Windows no afectado** | https://www.securityweek.com/microsoft-says-windows-not-impacted-by-regresshion-as-second-openssh-bug-is-found/ (resumen de buscador) |
| CVE-2024-43581, CVE-2024-43615 (sftp/scp), CVE-2024-38029 (ssh-agent) | OpenSSH for Windows | Arreglados en Windows en octubre de 2024 (KB5044284 en 24H2) y en GitHub v9.8.0.0 | notas de v9.8.0.0p1-Preview en releases; resumen de buscador |
| CVE-2025-26465 (MITM del cliente con `VerifyHostKeyDNS`) y **CVE-2025-26466** (DoS previo a la autenticación, 9.5p1-9.9p1) | Upstream; en GitHub «cherry-picked from upstream» en v9.8.2.0 | El inbox 9.5 está en el rango de 26466; que el acumulado lo traiga parcheado: **[comprobar en Windows 11]** | https://blog.qualys.com/vulnerabilities-threat-research/2025/02/18/qualys-tru-discovers-two-vulnerabilities-in-openssh-cve-2025-26465-cve-2025-26466; releases |
| CVE-2025-27731 (elevación local en OpenSSH for Windows) | Local | Abril de 2025, parcheado | releases v9.8.2.0 («fix CVE-2025-27731»); agregadores |
| **Octubre de 2026**: CVE-2026-97816 (use-after-free, ejecución remota sin autenticar, crítica), CVE-2026-88157 y CVE-2026-83754 (desbordamientos, ejecución remota), CVE-2026-83923 (ruta relativa, ejecución remota), CVE-2026-70163 (sin límite de recursos), CVE-2026-83769, -83871, -97811 (elevación local) | OpenSSH for Windows, Windows 10/11 y Server 2019-2025 | En el acumulado de octubre de 2026 (13-10-2026) | https://github.com/advisories?query=openssh (lista de GHSA, sin revisar); https://www.bleepingcomputer.com/news/microsoft/microsoft-october-2026-patch-tuesday-fixes-1-411-flaws-3-zero-days/, https://www.rapid7.com/blog/post/em-patch-tuesday-october-2026/ (resumen de buscador). **No se ha podido abrir MSRC** para ver si piden el servidor instalado |
| CVE-2026-106587 («none» en una opción dentro de un `Match` leído como nombre de fichero) | sshd < 10.6, local, baja | No usar `none` dentro de `Match` (el ejemplo no lo hace) | GHSA-8fmq-pfxf-6hmc (https://github.com/advisories/GHSA-8fmq-pfxf-6hmc) |
| CVE-2026-73283 / CVE-2026-106586 (`restrict` no cubre el túnel tun) | sshd < 10.5/10.6 con `PermitTunnel` encendido | En Windows no hay `PermitTunnel` | §1.6 |
| CVE-2026-123158 ("SSHole") | Linux con musl sin PAM | No afecta a Windows ni a macOS | https://github.com/advisories/GHSA-4fcc-vm97-gx3x (lista de GHSA) |

Qué se saca de aquí para el diseño:

- **El mini PC tiene que estar al día de Windows Update** (ya lo pide §4.5 del diseño: reinicios de
  noche). El parche de sshd llega con el acumulado (Learn, §1.1); `mac.ps1 -Estado` enseña la versión
  de `sshd.exe` y la fecha del último acumulado (`Get-HotFix | Sort-Object InstalledOn`) **[comprobar
  en Windows 11]** que `Get-HotFix` lo da.
- **Superficie**: con la regla de §5, el puerto 22 solo lo ve la IP del Mac en una red Privada; un fallo
  previo a la autenticación (como los de octubre de 2026) solo se puede intentar desde esa IP (o
  suplantándola en la red local). `MaxStartups` bajo y `LoginGraceTime 30` acotan los DoS.
- **Si el Mac no se usa** durante un tiempo, `mac.ps1 -Quitar` (o al menos parar `sshd` y deshabilitar
  la regla): la recomendación de los avisos de octubre de 2026 era deshabilitar el servidor hasta
  parchear (SentinelOne, resumen de buscador).
- **Lo que gana quien robe la clave del Mac** (y esté en la red con la IP del Mac): llegar a la página
  de entrada de la app, que pide el token personal; nada más (`PermitOpen`, `MaxSessions 0`, sin
  `PermitListen`). Lo mismo que alguien sentado al mini PC sin token.

---

## 7. Implicaciones para el diseño (para quien lo escriba)

1. **Nada cambia en la app ni en Python** (regla "Python no lanza procesos" intacta): el `Host` y el
   `Origin` llegan como `127.0.0.1:8765` porque el navegador del Mac abre `http://127.0.0.1:8765/app`.
   El Mac tiene que pedir literalmente `127.0.0.1` en los dos extremos del `-L` (§1.6) y abrir
   `127.0.0.1`, no `localhost` (el `-L` explícito escucha solo en IPv4).
2. **`docker/mac.ps1` + `mac.bat`** (`-Instalar` elevado con el patrón de `windows/instalar.ps1:143-152`,
   `Start-Process -Verb RunAs` y un `-Elevado`; `-Estado`, `-AnadirClave`, `-QuitarClave`, `-Quitar`).
   La variante nativa necesita lo mismo (la consola también está en `127.0.0.1:8765`): o el mismo
   script compartido o uno en `windows/`. `mac.ps1` no usa Docker: **no** encaja en `SCRIPTS` de
   `tests/test_entorno_local.py:260-277` tal cual (pide `Comprobar-Docker`); necesita su propia prueba
   estática (ASCII, `.bat` con `-ExecutionPolicy Bypass`, SIDs y no nombres de grupo, nada de
   `PasswordAuthentication yes`, `PermitOpen 127.0.0.1:8765`, `MaxSessions 0`, la regla con
   `-Profile Private`, nunca `Remove`/`Disable` de reglas que no sean suyas salvo `OpenSSH-Server-In-TCP`).
3. `-Instalar`: capacidad → **detectar un `sshd_config` que no sea el de fábrica ni el nuestro y
   pararse** (el dueño podría usar sshd para otra cosa) → guardar el original → escribir el nuestro →
   cuenta (§3) → fichero de claves con su ACL (§1.5) → `sshd.exe -t` → servicio automático y arrancar
   → regla propia y deshabilitar la de Microsoft → enseñar la huella del host y la IP del mini PC y la
   categoría de la red.
4. `-Estado`: servicio, versión, `sshd -T -C …` filtrado, regla (perfil, IP remota, habilitada) y la de
   Microsoft, categoría de la red, quién escucha en 8765 (`Get-NetTCPConnection`), claves (huellas,
   nunca la clave), últimos accesos del Visor de eventos (necesita elevación).
5. **En el Mac (`mac/`)**: `preparar.command` (clave con frase en el Llavero, huella del host
   comparada, `ssh_config` y `known_hosts` en `~/.bms-tunel/`, deja la pública y su huella) y
   `abrir-bms.command` (comprueba con `nc -z 127.0.0.1 8765` **antes** de abrir que nadie escucha ya
   ahí — `lsof` sin root solo ve los procesos propios —, abre `ssh -F … -N`, espera al puerto, prueba
   `curl` a `/app` y abre el navegador; al cerrar la ventana se cierra el túnel). Rutas absolutas
   (`/usr/bin/ssh`, `/usr/bin/nc`, `/usr/bin/open`), bash 3.2, bit `100755` en git. Boceto en
   `ejemplos/abrir-bms.ejemplo.sh`.
6. **Documentos**: `docs/entorno-local.md` §1 dice hoy «desde otro ordenador de la oficina o de casa no
   se llega, aunque esté en la misma red» (`:49-54`) y `docs/instalacion-nativa.md:51` lo mismo: hay
   que añadir "salvo el Mac con su clave, por el túnel". Una guía nueva para el dueño (castellano), con
   las acciones suyas: reservas DHCP (mini PC y Mac), red Privada, Wi-Fi privada del Mac en Fija o
   apagada, Windows Update al día.
7. **§12.4 del diseño del paso 18** (`docs/v1/paso-18/diseno.md:1917`: «¿El dueño usará la app en el
   propio mini PC? … usarla desde otro ordenador no está diseñado aquí») queda contestada por esta
   petición.
8. `windows/comprobar.ps1:85-108` (nativa) solo enseña lo que escucha en `127.0.0.1`/`::1`; sshd
   escucha en `0.0.0.0:22` y no saldría. Por transparencia, `comprobar` podría decir "sshd del túnel
   del Mac: solo reenvía a 127.0.0.1:8765, solo desde <IP>" leyendo lo que dejó `mac.ps1`.

---

## 8. Lo que no he podido confirmar

Cada punto, con dónde se comprueba (va a la lista de §7.4 del diseño):

**Sin poder ejecutarlo aquí**

1. Validar `ejemplos/sshd_config.ejemplo` con un sshd y probar de punta a punta `restrict`,
   `permitopen`, `MaxSessions 0`, `ForceCommand`, `PermitListen none` y la intersección con
   `PermitOpen`: bajar un OpenSSH al scratchpad lo **denegó el sistema de permisos**. En el mini PC:
   `sshd.exe -t`; `sshd.exe -T -C user=bms-tunel,host=mac,addr=<IP>`; desde el Mac: `-L` a
   `127.0.0.1:8765` funciona, `-L` a `127.0.0.1:22` o a `127.0.0.1:2375` da "administratively
   prohibited", `-R` falla, `ssh bms-minipc` sin `-N` no da shell, `sftp` y `scp` fallan
   **[comprobar en Windows 11]**.

**Windows 11 Pro (mini PC)**

2. Qué perfiles, programa y direcciones tiene la regla `OpenSSH-Server-In-TCP` que crea la capacidad, y
   si una actualización de la capacidad la vuelve a habilitar o recrear **[comprobar en Windows 11]**.
3. La versión exacta de OpenSSH que trae el mini PC (`sshd.exe -V`) y si su acumulado trae los
   arreglos de CVE-2025-26466 y de octubre de 2026 **[comprobar en Windows 11]**; MSRC no se ha podido
   abrir.
4. Que la capacidad deja el `sshd_config` de fábrica igual que el del fork (`Match Group
   administrators`, `Subsystem sftp`) y que **no lo sobrescribe** al actualizarse **[comprobar en
   Windows 11]**.
5. **El cruce de sesiones**: que el proceso de sshd de la cuenta del túnel (sesión 0) llega a
   `127.0.0.1:8765` publicado por `com.docker.backend.exe` en la sesión de «bms», con esa sesión
   **bloqueada**, y también con la variante nativa **[comprobar en Windows 11]** (es lo mismo que ya
   supone §4.2 para la cuenta del dueño).
6. Que sshd acepta un `AuthorizedKeysFile` absoluto en `C:\ProgramData\ssh` con ACL solo
   SYSTEM/Administradores para un usuario **estándar** (y lo rechaza si la cuenta del túnel puede
   escribirlo) **[comprobar en Windows 11]**.
7. Que `New-LocalUser` deja la cuenta sin grupos; que así no puede iniciar sesión local ni por
   Escritorio remoto; que el S4U de red de sshd funciona igual sin pertenecer a Usuarios; que
   "Tener acceso a este equipo desde la red" incluye a Todos; y que la contraseña caducada no estorba
   (aunque se pone `PasswordNeverExpires`) **[comprobar en Windows 11]**.
8. Que el valor de `SpecialAccounts\UserList` la oculta en Windows 11 25H2 y si sin grupos ya no salía
   **[comprobar en Windows 11]**.
9. El comportamiento real de `ForceCommand` con PTY en el inbox (el wiki dice que solo se aplica sin
   PTY; con `PermitTTY no` + `MaxSessions 0` no debería importar) **[comprobar en Windows 11]**.
10. Que `X11Forwarding`, `PermitTunnel`, etc. no rompen el arranque del inbox si alguien los escribe
    (en el código de GitHub no rompen; el diseño no los escribe) **[comprobar en Windows 11]**.
11. El nombre del registro de eventos (`OpenSSH/Operational`) y que `LogLevel VERBOSE` apunta la huella
    de la clave **[comprobar en Windows 11]**.
12. Si Windows 11 contesta a `<nombre>.local` por mDNS a un Mac con la red Privada (para no depender
    de la IP) **[comprobar en Windows 11]** y **[comprobar en macOS]**; el diseño recomienda IP
    reservada de todas formas.
13. Qué cubre `LocalSubnet` en el mini PC con Docker Desktop/WSL (interfaces vEthernet) **[comprobar en
    Windows 11]**.
14. `Get-HotFix` como fecha del último acumulado **[comprobar en Windows 11]**.

**macOS**

15. La versión de `/usr/bin/ssh` del Mac del dueño y que acepta `UseKeychain`, `HostKeyAlias`,
    `ExitOnForwardFailure` con `-F` **[comprobar en macOS]**.
16. Que la primera conexión pide la frase en Terminal y la guarda en el Llavero, y la siguiente no
    pregunta (también con `ssh` en segundo plano dentro del script) **[comprobar en macOS]**.
17. El texto y el comportamiento del doble clic en un `.command` sin bit de ejecución y con cuarentena
    en la versión de macOS del dueño; que "Abrir igualmente" aparece en Privacidad y seguridad
    **[comprobar en macOS]**.
18. Que el ZIP de GitHub conserva el bit de ejecución al descomprimirlo con la Utilidad de Archivo, que
    la cuarentena pasa a los ficheros de dentro, que `git clone` desde Terminal no la pone, qué hace
    GitHub Desktop, y que una copia desde una memoria USB no la pone **[comprobar en macOS]**.
19. Que `bash <fichero>` con un fichero en cuarentena no pasa por Gatekeeper **[comprobar en macOS]**.
20. Que `ssh` lanzado desde un `.command` no pide permiso de "Red local" (TN3179 dice que no)
    **[comprobar en macOS]**.
21. Que Safari (15.4+) y Chrome tratan `http://127.0.0.1:8765` como contexto seguro con la app de
    verdad (`crypto.randomUUID`, copiar en el chat) y que Chrome 154 no avisa por HTTP con `127.0.0.1`
    **[comprobar en macOS]**.
22. Que el `-L 127.0.0.1:8765` del Mac falla (y `ExitOnForwardFailure` corta) si otro programa
    escucha ya en `0.0.0.0:8765` o `127.0.0.1:8765` (ssh usa `SO_REUSEADDR` en sus escuchas,
    `channels.c:4079`) **[comprobar en macOS]**; de ahí el `nc -z` previo.
23. La reserva DHCP del Mac con la "Dirección Wi-Fi privada" en Fija (que no cambia con las
    actualizaciones de macOS; hay un informe de que cambió) **[comprobar en macOS]**.

**Fuentes no abiertas**

24. Las páginas de Learn, MSRC, docs.docker.com, man.openbsd.org, openssh.com, support.apple.com, MDN,
    WebKit y Chromium se han leído por su fuente en GitHub o por resúmenes de buscador (§0); para
    abrirlas hay que permitir esos dominios en la red de la sesión.

---

## Anexo A. Lo que se ha comprobado aquí

En `scratchpad/correo/mac/ejemplos/`:

- `mac-ejemplos.ps1`: trozos para `mac.ps1` (capacidad, cuenta, contraseña aleatoria, `UserList`,
  grupos por SID, huella SHA256, validar la clave pública, fichero de claves con `icacls` por SID,
  regla del cortafuegos, categoría de la red, quién escucha, `sshd -t/-T`, eventos). ASCII; **el
  analizador de PowerShell (pwsh 7.4.13) no da errores**. Ejecutado en Linux solo para la huella:
  `Huella-Sha256` da `SHA256:ZkAslGjFiUHdGf/WUL8rQvkib4PTvQatUV0OUQSncCA` para el vector de
  `vector.txt` (clave ed25519 de bytes 0..31), **igual que Python** (`hashlib` + `base64` sin `=`);
  `Clave-Publica-Valida` acepta esa línea, la rechaza con `command="x"` delante y rechaza una `ssh-rsa`.
  Que corra en Windows PowerShell 5.1: **[comprobar en Windows 11]**.
- `sshd_config.ejemplo`: no validado (§8.1).
- `ssh_config.ejemplo`: no validado (no hay ssh aquí).
- `abrir-bms.ejemplo.sh`: `bash -n` y `bash --posix -n` sin errores (bash de Linux, no el 3.2 de
  Apple).
- Las IP de los ejemplos son de documentación (192.0.2.0/24); ningún dato del dueño.
