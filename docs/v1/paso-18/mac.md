# Diseño · paso 18b: el Mac por el mini PC

> Guardado en el repositorio el 24-11-2026 para que no se pierda si se recrea la máquina. Las rutas
> `scratchpad/…` (y `correo/mac/…`) son ficheros de trabajo de la sesión de diseño (borradores,
> pruebas, revisiones y copias de las fuentes); no están en el repositorio.

**El navegador de un Mac abre la app del mini PC por un túnel SSH cifrado, solo en la red de la
oficina, y todo lo demás sigue en el mini PC.**

Para quien lo construye. **Versión final**, tras dos revisiones adversarias (seguridad y viabilidad;
qué se aceptó y cómo, en §10). Escrita el 24-11-2026 sobre `HEAD b685843` de la rama
`claude/zapier-mcp-setup-rjn0q6`, sin tocar el repositorio; todas las referencias `fichero:línea`
están ancladas a ese commit (el borrador anterior lo estaba a `0062d38`; el commit siguiente de la
rama, `f65c434`, solo toca `docs/v1/paso-18/desviaciones.md` y `tests/test_correo_certificado.py`, que
aquí no se citan). Sale de
`scratchpad/correo/mac/investigacion.md` («inv. §N», con la URL de cada afirmación y las fuentes en
`scratchpad/correo/mac/fuentes/`) y de `revision-seguridad.md` y `revision-viabilidad.md` (misma
carpeta). Lo que solo se puede comprobar en un Windows 11 Pro o en un Mac reales va marcado
**[comprobar en Windows 11]** o **[comprobar en macOS]** y está en la lista de §5.2.

**Comprobado aquí** (guiones y salidas en `scratchpad/correo/mac/pruebas-final/`):

- **Con un OpenSSH de verdad** (9.6p1 de Ubuntu, sacado de los `.deb` a `correo/mac/openssh/root` y
  arrancado en un espacio de montaje propio con `unshare -m`, sin instalar nada en el sistema;
  `dentro.sh` → `resultado.txt`): el `sshd_config` **literal** de §2.3 pasa `sshd -t`; `sshd -T`
  da para la cuenta del túnel `allowtcpforwarding local`, `allowstreamlocalforwarding no`,
  `x11forwarding no`, `permittunnel no`, `permitopen 127.0.0.1:8765`, `permitlisten none`,
  `maxsessions 0`, `forcecommand exit 1` y para otra cuenta `authorizedkeysfile none` y
  `allowtcpforwarding no`; el `-L` al 8765 funciona; el `-L` a otro puerto («administratively
  prohibited»), el `-L` a un socket Unix («refused streamlocal port forward»), el `-R` a un socket Unix
  y una orden remota («no more sessions») se rechazan; y `StrictModes` rechaza el fichero de claves
  bajo una carpeta con modo `1777` («bad ownership or modes for directory»). La revisión de seguridad
  ya había probado con el mismo sshd otros 19 casos sobre la configuración anterior (otro destino con
  formas raras de `127.0.0.1`, `-D`, `-W`, `-R` TCP, `sftp`, `scp`, `-w`, contraseña, otra clave,
  `from=` de otra IP: todos rechazados; `pruebas-seg/`).
- **Con `pwsh` 7.4.13**: el código nuevo de los anexos C y D (`funciones.ps1`, `flujo.ps1`,
  `proteger.ps1`) se analiza sin errores y es ASCII; `probar.ps1` pasa 14 casos (`Texto-Config` igual
  carácter a carácter al `sshd_config` probado con sshd; `Comprobar-Lo-Que-Se-Aplica` con la salida de
  un sshd 9.6, de uno ≥ 10.3 y de uno mal configurado; la plantilla de `secedit` y la comprobación de
  después, también con la cuenta escrita por su nombre, como la exporta `secedit`) y `probar-origen.ps1` 12 casos (`resultado-pwsh.txt`). El resto de funciones puras (`Ip-Valida`, `Resto-De`,
  `Clave-Publica-Valida`, `Huella-Sha256`) no cambia y ya se probó en el borrador
  (`borrador/docker/mac.ps1`).
- **Con `bash`**: los dos `.command` de los anexos A y B pasan `bash -n` y `bash --posix -n`, son
  ASCII y sin construcciones de bash 4; `abrir-bms.command` se ha ejecutado contra programas falsos en
  10 casos (`falso/probar-abrir.sh` → `falso/resultado-abrir.txt`) y `preparar.command` en 5
  (`falso/probar-preparar.sh` → `falso/resultado-preparar.txt`).
- **No se ha podido comprobar aquí**: nada que necesite Windows o macOS de verdad (ACL de NTFS,
  `secedit`, el cortafuegos, UIPI, `taskkill`, TCC, la semántica de `bind` de macOS, el cruce de
  sesiones). Todo eso está en §5.2.

**La petición** (literal): «Si tambien quiero que funcione en una mac pero se haga todo a traves de
la pc mini, para mantener el sandbox». **Sus respuestas**: el navegador del Mac abre la app del mini
PC por un canal cifrado (acepta que lo que ve y los PDF que descargue lleguen al Mac); solo desde la
misma red que el mini PC; el mini PC tiene Windows 11 Pro.

**La decisión técnica ya tomada** (no se reabre, y nada de las revisiones la contradice): un túnel
SSH local con el OpenSSH que traen Windows 11 Pro (servidor) y macOS (cliente). El Mac reenvía su
`127.0.0.1:8765` al `127.0.0.1:8765` del mini PC y su navegador abre `http://127.0.0.1:8765/app`.

---

## 0. Resumen y decisiones

| # | Decisión | Por qué (corto) |
| --- | --- | --- |
| M1 | **Túnel SSH local** (`ssh -N -L 127.0.0.1:8765:127.0.0.1:8765`) del OpenSSH de macOS al servidor OpenSSH de Windows (capacidad opcional `OpenSSH.Server~~~~0.0.1.0`, que se actualiza con Windows Update). | La app no cambia: ve `Host` y `Origin` `127.0.0.1:8765` como siempre (`serve.py:293-304`, `:269-284`); no se publica nada nuevo de la app en la red; el navegador del Mac está en un contexto seguro. Sin servicios de fuera ni programas que instalar. |
| M2 | **Una cuenta local solo para el túnel, `bms-tunel`**: estándar, sin grupos propios, con **los cuatro «Denegar el inicio de sesión»** (local, Escritorio remoto, por lotes y como servicio) puestos a su SID, oculta en la pantalla de inicio, contraseña aleatoria que nadie guarda. sshd entra con un inicio de **red** S4U, que no se toca. | «Sin grupos» no la saca de Usuarios (Usuarios contiene a Usuarios autenticados): lo que de verdad le quita la pantalla y el Escritorio remoto son las negaciones; lo que le quita los datos es que nadie dé lectura a esos grupos (M12, §2.12). |
| M3 | **`sshd_config` entero de bms-agent**: todo cerrado para todos (también `AllowStreamLocalForwarding`, `X11Forwarding` y `PermitTunnel` a `no`) y un `Match User bms-tunel` que solo abre `AllowTcpForwarding local` hacia `PermitOpen 127.0.0.1:8765`. `AllowUsers bms-tunel@<IP del Mac>`, solo clave, `MaxSessions 0`, `ForceCommand exit 1`, `PermitTTY no`, `PermitListen none`. Comprobado después con `sshd -T` (que acepta la forma de OpenSSH ≥ 10.3). | Probado con un sshd 9.6 de verdad. Una configuración mezclada con otra no se puede razonar. Si ya había cambios que no son nuestros, no se toca salvo `-SustituirConfiguracion` (§2.9). |
| M4 | **Las claves en `C:\ProgramData\ssh\bms_tunel_authorized_keys`**, solo de SYSTEM y Administradores; cada línea la escribe el script con `restrict,port-forwarding,permitopen="127.0.0.1:8765",from="<IP>",command="exit 1"`. **Y la carpeta `C:\ProgramData\ssh` tiene que ser de los administradores**: si la creó otra cuenta antes que el servicio, se aparta y el servicio la rehace. | La cuenta del túnel no puede tocar las claves; sshd (SYSTEM) usa la carpeta aunque no sea suya (solo apunta «Bad owner»). |
| M5 | **Cortafuegos con dos reglas propias en cualquier perfil**: una que deja pasar al 22 de `sshd.exe` **solo a las IP de los Mac** y otra que **bloquea a todos los demás** (un bloqueo gana a cualquier regla que deje pasar). La de Microsoft (`OpenSSH-Server-In-TCP`) se apaga. **No se cambia la categoría de la red.** | Marcar la red como privada encendería para toda la red otras reglas que no son nuestras (compartir, detección, apps). La IP del Mac ya está en tres capas. |
| M6 | **IP reservada en el router** para el mini PC y para cada Mac (con la «Dirección Wi-Fi privada» del Mac en **Fija**). Reserva de último recurso: `red` (toda la subred del mini PC). | La IP del Mac está en tres capas (cortafuegos, `AllowUsers`, `from=`); la del mini PC, en el Mac. |
| M7 | **Las huellas se comparan a ojo, la primera vez**, en las dos pantallas; después `StrictHostKeyChecking yes` con `HostKeyAlias bms-minipc`. | `ssh-keyscan` no autentica nada (inv. §4.3). |
| M8 | **En el Mac, una carpeta `mac/`** con `preparar.command` (una vez) y `abrir-bms.command` (cada día), con el `PATH` del sistema y `/usr/bin/ssh`. La clave `ed25519` con **frase obligatoria** en el Llavero; la configuración aislada en `~/.bms-tunel/`. | Sin tocar Gatekeeper ni nada de lo que el dueño tenga en `~/.ssh`. |
| M9 | **El puerto del Mac es el 8765** y nadie más lo coge: `abrir-bms` para si está ocupado, **lo guarda con un `nc` propio mientras el túnel está cortado** (la pestaña de la app sigue llamando con el token) y solo da el túnel por abierto si quien escucha es su `ssh` (`lsof`). | La app exige ese puerto en `Host` y `Origin`; la pestaña de Procesar consulta cada 2 s con el token aunque falle (`processing-workspace.tsx:91-101`). |
| M10 | **Un solo script de Windows, `mac.ps1` + `mac.bat`, idéntico en `docker\` y en `windows\`**, con PowerShell por su ruta completa, que se eleva solo, **no carga `comun.ps1`** y se niega si otra cuenta puede cambiar `mac.ps1`, `mac.bat`, **la carpeta `mac\`** o sus carpetas (escribir, crear ficheros, borrar, permisos **o ser su dueño**). Lo que hay que preguntar (la clave del Mac) se pregunta **antes de elevar**. Opciones: `-Instalar`, `-AnadirClave`, `-QuitarClave`, `-Estado`, `-Apagar`, `-Encender`, `-Quitar`, `-CopiarParaElMac`. | Es un script de administrador: si otra cuenta pudiera cambiarlo, correría lo suyo como administrador. La ventana de administrador no recibe ficheros arrastrados (UIPI). |
| M11 | **El estado en el registro** (`HKLM:\SOFTWARE\bms-agent\TunelMac`, valor `Estado`, JSON): la foto de antes y la lista de Mac. | `-Quitar` deja el equipo como estaba. |
| M12 | **La carpeta del proyecto, protegida** (Docker con el usuario «bms» del paso 18): `docker\proteger.bat -Usuario bms`, como administrador, una vez al poner la carpeta y otra con cada versión nueva: dueño Administradores, sin herencia, el dueño `M`, «bms» `RX` y `M` solo en `docker\estado` y `docker\secretos\correo`; nadie más lee nada. En la nativa ya lo hace `instalar.ps1` (`:359-381`). | Sin eso «bms» podría cambiar los scripts que abre el dueño (también `mac.bat`) y lo que va al Mac, y `bms-tunel` leería los secretos por ser de Usuarios. Es lo que pide el paso 18 aunque no haya Mac. |
| M13 | **Una persona aparte para el Mac** (`persona.bat -Nombre "Ana Mac" -Rol administracion`), con su token. | Perder el Mac revoca solo ese token y la auditoría distingue el Mac del mini PC. |
| M14 | **Nada cambia en Python, en la app, en `docker-compose.yml` ni en el `Dockerfile`**; `mac.ps1` no usa Docker ni toca el programa. Fuera de `mac.*`: `docker\proteger.*` (nuevo), y en la nativa `instalar.ps1` copia `mac\` a `<Raiz>\mac`, `desinstalar.ps1` para si el túnel sigue instalado y `comprobar.ps1` lo dice en una línea. | Regla "el código de Python no lanza procesos" intacta; la consola sigue sin red. |

**Lo que no cambia**: la consola sigue escuchando solo en `127.0.0.1` (en Docker, publicada en
`"127.0.0.1:8765:8765"`, `docker-compose.yml:77-78`); `http://<IP del mini PC>:8765` desde otro
equipo sigue sin abrir nada (`instalacion-nativa.md:558-559`); cada persona entra con su token
personal; la consola no tiene red; ningún secreto ni dato del programa en el Mac (ni base, ni clave de
la API, ni certificado del correo): en el Mac solo hay una clave SSH que únicamente abre ese túnel.
**Lo que sí cambia y hay que decir**: hay un servidor SSH escuchando en el `0.0.0.0:22` del mini PC.
Desde la red solo llegan las IP de los Mac; **desde el propio mini PC llega cualquier programa** (el
cortafuegos no filtra el tráfico local) a la parte de sshd previa a la clave (§1.2).

### 0.1 Alternativas descartadas

| Alternativa | Por qué no |
| --- | --- |
| **Escritorio remoto** (la «Windows App» del Mac contra el RDP de Windows 11 Pro) | Daría al Mac una sesión de Windows entera con contraseña en el 3389; una sola sesión interactiva a la vez (chocaría con la de «bms»); peor de usar |
| **Tailscale** (o ZeroTier, Cloudflare Tunnel, ngrok) | Un servicio de fuera con su cuenta y un agente que corre como SYSTEM; sirve para entrar desde fuera, que el dueño no quiere. Alternativa futura |
| **Publicar la app en la red** (`0.0.0.0:8765`, `netsh portproxy`) | Rompe `serve.py:8-12` y `:20-31`; HTTP en claro; `http://192.168.x.y` no es contexto seguro (`crypto.randomUUID`, `frontend/src/lib/api.ts:381`; el portapapeles, `frontend/src/aurora/chat/ai-actions.tsx:179`) |
| **Un proxy inverso con TLS** (Caddy, nginx) | Software y certificados nuevos; la app tendría que aceptar otro `Host`/`Origin` |
| **Un contenedor con `sshd`** | Segundo contenedor con un pie fuera, imagen nueva que parchear, no sirve para la nativa |
| **Una VPN en el router** | Depende del router; en la misma red no aporta nada |
| **SSH con contraseña**, o con la cuenta del dueño o la de «bms» | Contraseñas que adivinar; cuentas con ficheros, DPAPI o Docker |
| **`DisableForwarding`** | Apaga también el reenvío TCP que se necesita (inv. §1.4) |
| **`Include` de un trozo en el `sshd_config` del dueño** | En sshd gana el primer valor; `AllowUsers` cortaría el uso que ya tuviera. Si ya hay uso, se para (§2.9) |
| **Un agente de `launchd`** con el túnel siempre abierto | Más tiempo abierto, más superficie; el dueño abre el túnel cuando usa la app |
| **Un certificado de SSH (una CA)** / **una llave FIDO2** | Para uno o dos Mac, una línea por Mac basta; el `ssh` de Apple no trae soporte de llaves sin una biblioteca aparte |
| **`localhost` en lugar de `127.0.0.1`** | `permitopen`/`PermitOpen` no resuelven nombres; `localhost` en el Mac puede ir a `::1` (inv. §1.6) |
| **Marcar la red del mini PC como privada** (lo que hacía el borrador) | Enciende todas las reglas de entrada del perfil Privado para cualquier equipo de la wifi (detección de redes, compartir, las apps dejadas pasar «en redes privadas»: `fuentes/ms/Set-NetConnectionProfile.md:214`, `New-NetFirewallRule.md:735-737`). Con la regla de los Mac en cualquier perfil no hace falta |
| **sshd apagado por defecto**, encendido solo mientras se usa el Mac | Para encenderlo habría que ir al mini PC, que es justo lo que el Mac evita. `-Apagar` existe para cuando no se use; `-Estado` pone en rojo un acumulado de más de 35 días |
| **`ListenAddress <IP del mini PC>`** | No quita el alcance local (un programa del equipo llega igual a esa IP) y, si la IP no está aún al arrancar (wifi, DHCP), sshd no arranca |
| **Copiar `mac.ps1` a `C:\Program Files` y usar esa copia** (la reserva del borrador) | La primera vez y con cada versión nueva saldría de la misma carpeta que «bms» podría cambiar: no arregla nada sin proteger la carpeta, y con ella protegida no hace falta |
| **Guardar el 8765 del Mac también después de cerrar la ventana** (un `nc` que se queda solo) | Un proceso suelto que el dueño no ve. En su lugar: la guía dice «Salir» antes de cerrar, y si `abrir-bms` para por un error con la pestaña abierta, guarda el puerto hasta que el dueño la cierra (§3.5) |
| **`Get-LocalGroupMember`** para los grupos de la cuenta | En Windows PowerShell 5.1 falla con miembros huérfanos o de Entra (PowerShell/PowerShell#2996): se usa ADSI por SID |
| **`Stop-Process` sobre los `sshd.exe`** | No ve `sshd-session.exe` (OpenSSH ≥ 9.8) y puede dar «acceso denegado» en procesos de SYSTEM: `taskkill /F` por ejecutable y se vuelve a mirar (§2.8) |

---

## 1. Qué corre dónde y qué cruza la red

```
 MAC (red de la oficina, IP reservada)                 MINI PC (Windows 11 Pro, IP reservada)
 +-------------------------------------+               +-----------------------------------------------+
 | Navegador (perfil solo para la app) |               | sshd.exe (servicio, SYSTEM), escucha 0.0.0.0:22|
 |   http://127.0.0.1:8765/app         |               |   cortafuegos: solo las IP de los Mac          |
 |        | bucle local del Mac        |               |   AllowUsers bms-tunel@<IP del Mac>, solo clave|
 |        v                            |  TCP 22,      |        | tras la clave: un proceso de sshd de la |
 | /usr/bin/ssh -N  (abrir-bms)        |  SSH cifrado  |        | cuenta bms-tunel (sesion 0), sin consola|
 |   escucha 127.0.0.1:8765  ==========|==============>|        v  abre 127.0.0.1:8765 y nada mas       |
 |   (cortado: lo guarda un nc propio) |  Mac:alto     | 127.0.0.1:8765  <- Docker Desktop             |
 |   ~/.bms-tunel: clave (frase en el  |  -> mini PC:22|   (com.docker.backend.exe, sesion de "bms")   |
 |   Llavero), huella del mini PC      |               |   -> salida -> consola (red interna, sin red)  |
 +-------------------------------------+               |   nativa: la consola escucha ahi directamente  |
                                                        +-----------------------------------------------+
```

**Lo que cruza la red**: una conexión TCP del Mac (puerto alto) al 22 del mini PC, cifrada por SSH
(clave `ed25519` del Mac y clave `ed25519` del mini PC). Dentro van las peticiones y respuestas HTTP
de la app: la página, el token de la persona del Mac en la cabecera `X-BMS-Token`
(`frontend/src/lib/api.ts:395`), los datos que se ven y los PDF que se descargan. Nada más: ni la app
en el 8765 de la red, ni SMB, ni RDP, ni el disco del mini PC.

**Lo que corre en el Mac**: el `ssh` de macOS (y, mientras el túnel está cortado, un `nc` que guarda el
puerto), solo mientras está abierta la ventana de `abrir-bms`, y el navegador. Nada del programa. En
`~/.bms-tunel/` (carpeta `700`): la clave privada (cifrada con su frase), su `.pub`, la huella del mini
PC, la configuración del túnel, la IP del mini PC, el nombre del Mac y las copias de los dos scripts.

**Lo que corre en el mini PC de más**: el servicio `sshd` (automático) y, por cada túnel abierto, sus
procesos: `sshd.exe` y, desde OpenSSH 9.8, `sshd-session.exe` (y en 10.x `sshd-auth.exe`;
`openssh/win-src/pathnames.h:50-61` del fork de Windows), unos como SYSTEM, la parte previa a la clave
con una cuenta virtual restringida (`fuentes/src-win/contrib_win32_win32compat_win32_usertoken_utils.c:610-700`,
`generate_sshd_virtual_token`, sin privilegios) y el que atiende el reenvío como `bms-tunel`. Nada de
Docker, de la app ni de Python cambia.

**Quién abre la conexión a `127.0.0.1:8765`** (inv. §2): con clave, Win32-OpenSSH hace un inicio de
sesión S4U **de tipo red** (`LsaLogonUser(…, Network, …)`, `win32_usertoken_utils.c:230`), sin
contraseña ni credenciales, y el canal `direct-tcpip` lo atiende un proceso de `bms-tunel` en la sesión
0. En Docker, el puerto lo escucha `com.docker.backend.exe` en la sesión de «bms»; en la nativa, la
consola. La pila TCP es del equipo, no de la sesión **[comprobar en Windows 11]** con la sesión de «bms»
bloqueada: es lo mismo que ya da por bueno §4.2 del diseño del paso 18 para la cuenta del dueño. La
cuenta del túnel no puede manejar Docker (sus tuberías solo las usan quien lo arrancó, `docker-users`,
los administradores y SYSTEM; `bms-tunel` no está en ninguno, §2.2).

### 1.1 Por qué la app no cambia

- **Escucha**: `serve.py:8-12` ("Escucha SOLO en 127.0.0.1"), `interfaz_permitida`
  (`serve.py:222-236`). En Docker la salida publica `"127.0.0.1:8765:8765"` (`docker-compose.yml:77-78`).
  Quien se conecta es `sshd` desde dentro del propio mini PC.
- **`Host`**: `host_permitido` (`serve.py:293-304`) exige `127.0.0.1` o `localhost` (`HOSTS_LOCALES`,
  `serve.py:107`) y el 8765. El navegador del Mac manda `Host: 127.0.0.1:8765`. Por eso el puerto del
  Mac tiene que ser el **8765** (M9).
- **`Origin`**: `origenes_permitidos` (`serve.py:269-284`), comparados enteros tras `normalizar_origen`
  (`serve.py:244-266`) en cada petición (`_rechazada`, `serve.py:549-565`): lo mismo.
- **Contexto seguro**: `http://127.0.0.1` lo es (inv. §4.7); la app usa `crypto.randomUUID`
  (`frontend/src/lib/api.ts:381`) y `navigator.clipboard.writeText`
  (`frontend/src/aurora/chat/ai-actions.tsx:179`). Requisito: Safari 15.4 o más, Chrome o Firefox
  recientes **[comprobar en macOS]**.
- **El token**: vive en memoria (`frontend/src/lib/session.tsx:1-4`); cada respuesta de la API lleva
  `Cache-Control: no-store` (`serve.py:516`, `:615`, `:938`). Pero **la pestaña de Procesar consulta
  cada 2 s con el token y sigue aunque falle** (`frontend/src/aurora/processing/processing-workspace.tsx:91-101`,
  `()=>undefined` y `setTimeout`): por eso el 8765 del Mac no puede quedar libre mientras haya una
  pestaña abierta (M9, §3.5).
- **Defensas contra webs que visite el Mac**: las mismas que en el mini PC (`serve.py:20-31`).

### 1.2 Quién llega al puerto 22 del mini PC

| Desde | Llega a | Qué lo para |
| --- | --- | --- |
| **Un Mac de la lista**, desde su IP | sshd entero | Su clave (con frase), `from=`, `AllowUsers`; tras entrar, solo el `-L` al `127.0.0.1:8765` |
| **Otro equipo de la red** | Nada | La regla "resto" lo bloquea en cualquier perfil (§2.5). Si suplanta la IP de un Mac (ARP), llega a la parte previa a la clave |
| **Un programa del propio mini PC** (cualquier cuenta: «bms», el dueño; en la nativa, también el lector, que abre PDF de fuera) | La parte previa a la clave, por `127.0.0.1:22` o por la IP del equipo: **el cortafuegos no filtra el tráfico local** (`instalacion-nativa.md:404-406`) | `AllowUsers`/`from=` se miran **después** del intercambio de claves (rechazan `127.0.0.1`; con la reserva `red`, la IP del propio equipo pasa esas dos y queda la clave). Sin la clave de un Mac no entra |
| **Un contenedor con red** (en Docker, `salida` y `salida_correo`, que están en `red_exterior`, `docker-compose.yml:55-80`) | Lo mismo, por `host.docker.internal` («resolves to the internal IP address used by the host», `fuentes/docker/troubleshoot-and-support_faqs_general.md:41-43`) **[comprobar en Windows 11]** | Lo mismo |

Lo de las dos últimas filas no es un hueco del túnel sino superficie: un programa del equipo **ya
comprometido** tiene un servicio más con el que hablar antes de autenticarse, del mismo tipo que los
que Windows ya tiene escuchando en todas las direcciones (RPC en el 135, SMB en el 445). Un fallo de
sshd previo a la autenticación (como los de octubre de 2026, inv. §6) sería un camino de ese programa
a una cuenta virtual sin privilegios o, si el fallo es del proceso que vigila, a SYSTEM. Por eso:
Windows Update al día, `-Estado` en **rojo** con el último acumulado de hace más de 35 días, `-Apagar`
cuando no se use el Mac y el registro de rechazos en `-Estado`. `MaxStartups 3:50:10` lo puede agotar
un programa local (el túnel no abriría mientras tanto): lo mismo, un programa ya comprometido; desde
OpenSSH 9.8 `PerSourcePenalties` (encendido por defecto) castiga al origen que falla, que sería
`127.0.0.1` y no el Mac.

---

## 2. El lado de Windows

### 2.1 Ficheros y opciones

| Fichero | Qué es |
| --- | --- |
| `docker/mac.ps1`, `docker/mac.bat` | El script (el borrador `scratchpad/correo/mac/borrador/docker/mac.ps1` con los cambios de este documento y del anexo C) y su `.bat`. ASCII, Windows PowerShell 5.1, CRLF (`.gitattributes` ya lo hace para `*.ps1` y `*.bat`) |
| `windows/mac.ps1`, `windows/mac.bat` | **Byte a byte iguales** a los de `docker/` (una prueba lo exige). `instalar.ps1` ya los copia a `<Raiz>\windows` (`windows/instalar.ps1:465-468` copia `*.ps1` y `*.bat`) |
| `docker/proteger.ps1`, `docker/proteger.bat` | Nuevo: protege la carpeta del proyecto en la variante Docker con el usuario «bms» (§2.12, anexo D) |
| `mac/preparar.command`, `mac/abrir-bms.command`, `mac/LEEME.txt` | Lo del Mac (§3). En la nativa, `instalar.ps1` los copia a `<Raiz>\mac` (§7, 15b.3) |

**Los dos `.bat` llaman a PowerShell por su ruta completa** (anexo D): `cmd.exe` busca un programa
nombrado sin ruta **primero en la carpeta actual** (`fuentes-seg/nf-processenv-needcurrentdirectoryforexepathw.md:76-80`),
y la guía abre la terminal en `docker\`: un `powershell.cmd` plantado ahí correría como el dueño justo
cuando espera el aviso de administrador.

```bat
@echo off
rem Abre mac.ps1 sin tener que cambiar la politica de scripts de Windows (pide administrador).
rem PowerShell por su ruta completa: cmd busca los programas primero en la carpeta actual.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0mac.ps1" %*
if errorlevel 1 pause
```

**Cómo lo abre el dueño**:

- **Docker**: desde su cuenta de Windows, una ventana de PowerShell en la carpeta `docker` del proyecto
  (clic derecho en un hueco → **Abrir en Terminal**): `.\mac.bat -Instalar`.
- **Nativa**: si instaló con su propia cuenta, igual en `C:\BMS\windows`. Si instaló con otro usuario
  (el «bms» del paso 18 §4.2), su cuenta **no puede ni abrir** `C:\BMS\windows` sin elevar
  (`instalar.ps1:359-367` solo da `RX` al usuario de la instalación; el token sin elevar del dueño no
  tiene ningún permiso que valga): **Terminal (Administrador)** y `& C:\BMS\windows\mac.bat -Instalar`.
  Nunca «Continuar» en el Explorador (añadiría un permiso que la siguiente actualización quita).

| Opción | Qué hace | Cuándo |
| --- | --- | --- |
| `-CopiarParaElMac <carpeta>` | Sin administrador. Comprueba que nadie más puede cambiar lo que va al Mac (§2.11), copia `mac\preparar.command`, `abrir-bms.command` y `LEEME.txt` a `<carpeta>\bms-mac` (la memoria USB), enseña su SHA-256 (16 primeros caracteres) y **la IP de este equipo** | Antes de preparar un Mac |
| `-Instalar [-Nombre x] [-SustituirConfiguracion]` | **Antes de elevar**: si hay una clave de un Mac en la memoria, ofrece añadirlo (nombre, IP, clave, huella; §2.13). **Ya elevado**: la capacidad de OpenSSH si falta, la cuenta, `C:\ProgramData\ssh` de fiar, el fichero de claves, el `sshd_config`, el servicio, las dos reglas y el Mac. Repetible: rehace lo que falte o se haya cambiado a mano | Una vez; y para arreglar lo que diga `-Estado` |
| `-AnadirClave [-Nombre x]` | Antes de elevar, lo del Mac (con un nombre que ya existe, cambia la IP y/o la clave); ya elevado, lo aplica | Un Mac nuevo; cambió la IP del Mac; clave nueva |
| `-QuitarClave [-Nombre x]` | Elige el Mac antes de elevar; ya elevado, lo quita y **corta todos los túneles abiertos** (§2.8); si Windows no deja cortar alguno, lo dice en rojo: «reinicia el equipo» | Mac perdido, vendido o que ya no se usa |
| `-Estado` | Todo, sin cambiar nada (§2.7) | Cuando algo no va; en el mantenimiento del mes |
| `-Apagar` / `-Encender` | Para `sshd` (inicio «deshabilitado»), corta los túneles y cierra el cortafuegos, sin desinstalar; y lo contrario | Semanas sin usar el Mac; Windows sin actualizar; un aviso de seguridad de OpenSSH |
| `-Quitar` | Lo deshace todo y deja el equipo como estaba (§2.8) | Ya no se quiere el Mac |

Parámetros internos (los pone el propio script al elevarse; la ventana de administrador **los vuelve a
validar y nunca se los cree**): `-Elevado`; `-Usuario <SID>` (el de quien lo abrió, para §2.11;
tiene que casar con `^S-1-5-21-\d+-\d+-\d+-\d+$`); `-Nombre` (`^[a-z0-9][a-z0-9-]{0,30}$`); `-Ip`
(`Origen-Valido`: una IP privada o la red de la reserva `red`); `-Clave` (solo el base64 de 68
caracteres; se rehace `ssh-ed25519 <base64>` y pasa otra vez por `Clave-Publica-Valida`);
`-MismaClave`. Ninguno lleva espacios ni comillas.

**Cómo se eleva**: comprueba primero que nadie más puede cambiar lo que va a correr (§2.11), pregunta
lo del Mac (§2.13) y se relanza con `Start-Process -FilePath (Get-Process -Id $PID).Path -Verb RunAs
-Wait -PassThru` (el patrón de `windows/instalar.ps1:143-156`); la ventana de administrador termina con
«Pulsa Intro para cerrar esta ventana» (`Esperar-Intro`). Si ya es administrador (la nativa desde una
Terminal de administrador), hace todo en la misma ventana. Comprueba que corre en un PowerShell de 64
bits.

Constantes (en el script; ningún valor del dueño): cuenta `bms-tunel`, puerto `8765`,
`C:\ProgramData\ssh\sshd_config` (`sshd_config.antes-bms`, `sshd_config.bms-nueva`),
`bms_tunel_authorized_keys`, `C:\Windows\System32\OpenSSH\sshd.exe` y su `sshd_config_default`,
reglas `BMS-Tunel-Mac-sshd` y `BMS-Tunel-Mac-sshd-resto`, regla de Microsoft `OpenSSH-Server-In-TCP`,
estado en `HKLM:\SOFTWARE\bms-agent\TunelMac`, `$FicherosDelMac = @("preparar.command",
"abrir-bms.command", "LEEME.txt")`, y **las herramientas del sistema por ruta completa**:
`$Icacls`, `$Taskkill`, `$Secedit`, `$Takeown` = `Join-Path $env:SystemRoot "System32\<x>.exe"`.

### 2.2 La cuenta del túnel (`Asegurar-Cuenta`)

```powershell
New-LocalUser -Name bms-tunel -Password (Contrasena-Que-Nadie-Guarda) -PasswordNeverExpires `
    -AccountNeverExpires -UserMayNotChangePassword -Description "bms-agent: solo el tunel del Mac"
```

- **Lo que es de verdad**: una cuenta estándar sin grupos **propios**. Pero **está en Usuarios
  igualmente**: «S-1-5-32-545 Users … After the initial installation of the operating system, the only
  member is the Authenticated Users group» (`fuentes-seg/understand-security-identifiers.md:214`), y
  todo inicio de sesión lleva Usuarios autenticados. Su token de sshd (S4U de red) lleva Todos,
  Usuarios autenticados, Usuarios, Red y Cuenta local (`:178`, `:176`, `:187`). Así que lee lo que
  lean esos grupos: por eso nada de bms-agent se lo da (§2.12) y `-Instalar`/`-Estado` lo comprueban
  (`Lectores-De-Datos`, anexo C).
- **Contraseña**: 32 bytes del generador del sistema en base64 más `aZ7!` (por si la directiva pide
  complejidad), convertida a `SecureString` y tirada: ni se escribe, ni se enseña, ni se guarda (una
  prueba lo vigila). sshd no la necesita. `-PasswordNeverExpires` para que una caducada no estorbe al
  S4U **[comprobar en Windows 11]**. `-Description` tiene un máximo de 48 caracteres: la frase tiene 32.
- **Sin grupos propios, mirado por SID con ADSI** (`Grupos-De-La-Cuenta`: los grupos del usuario por
  `WinNT://./bms-tunel,user` y su `objectSid`). Si está en alguno (Administradores, Usuarios de
  escritorio remoto, `docker-users`…), se la saca con `Remove-LocalGroupMember -SID … -Member <sid>` y
  se dice. **Si no se puede mirar, es un error** (`Fallar`, con sshd parado), nunca «ninguno»: así no se
  repite el fallo de `Get-LocalGroupMember` con miembros huérfanos (PowerShell/PowerShell#2996).
- **Los cuatro «Denegar…»** (`Negar-Inicios`, anexo C): `SeDenyInteractiveLogonRight`,
  `SeDenyRemoteInteractiveLogonRight`, `SeDenyBatchLogonRight` y `SeDenyServiceLogonRight` para su SID,
  con `secedit`: se exporta `USER_RIGHTS` (UTF-16), se escribe una plantilla con **solo esos cuatro**
  (lo que tenían, tal cual, más `*<SID>`; `secedit` exporta las cuentas locales por su nombre y los
  grupos como `*SID`, así que la cuenta se reconoce como `*<SID>`, `bms-tunel` o `EQUIPOms-tunel`), `secedit /configure` con una base temporal, se vuelve a
  exportar y se comprueba que esos cuatro llevan el SID **y que todos los demás derechos siguen
  exactamente igual**; si no, se vuelve a aplicar lo exportado al principio y `-Instalar` para. **Nunca
  se toca «Tener acceso a este equipo desde la red» ni su «Denegar»**: el S4U de sshd es un inicio de
  red (`LsaLogonUser(…, Network, …)`, `win32_usertoken_utils.c:230`), que estos cuatro no tocan. La
  carpeta temporal es la `TEMP` del dueño elevado (otras cuentas no escriben ahí) con un nombre
  aleatorio, y se borra.
- **Oculta**: valor DWORD `bms-tunel = 0` en `HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\
  Winlogon\SpecialAccounts\UserList` (práctica conocida, cosmética) **[comprobar en Windows 11]**.
- **Su perfil** (`C:\Users\bms-tunel`) lo crea sshd en el primer túnel (la primera conexión puede
  tardar más: `preparar` espera hasta 60 s).
- Si la cuenta existe y está deshabilitada, `Enable-LocalUser`.

### 2.3 El `sshd_config` exacto

`Texto-Config` lo genera a partir de la lista de Mac. Con un Mac `mac-oficina` en `192.168.1.23`
(IP de ejemplo), es **literalmente** esto (salida de `Texto-Config`, fin de línea LF, sin BOM;
**probado con `sshd -t` y `sshd -T` de un OpenSSH 9.6 de verdad**, §0 de la cabecera):

```
# bms-agent: tunel del Mac (mac.ps1).
# No lo cambies a mano: lo rehace mac.bat. El de antes esta en sshd_config.antes-bms.
# Solo deja que los Mac de la lista abran 127.0.0.1:8765 de este equipo, con su
# clave y desde su IP. Ni consola, ni ficheros, ni otro destino.

Port 22
AddressFamily inet
HostKey __PROGRAMDATA__/ssh/ssh_host_ed25519_key
SyslogFacility AUTH
LogLevel VERBOSE

AllowUsers bms-tunel@192.168.1.23
AuthenticationMethods publickey
PubkeyAuthentication yes
PubkeyAcceptedAlgorithms ssh-ed25519
PasswordAuthentication no
PermitEmptyPasswords no
AuthorizedKeysFile none
LoginGraceTime 30
MaxAuthTries 3
MaxStartups 3:50:10
ClientAliveInterval 30
ClientAliveCountMax 3
UseDNS no

AllowTcpForwarding no
AllowStreamLocalForwarding no
AllowAgentForwarding no
X11Forwarding no
PermitTunnel no
GatewayPorts no
PermitOpen none
PermitListen none
PermitTTY no
MaxSessions 0
ForceCommand exit 1

Match User bms-tunel
    AuthorizedKeysFile __PROGRAMDATA__/ssh/bms_tunel_authorized_keys
    AllowTcpForwarding local
    PermitOpen 127.0.0.1:8765
```

Con dos Mac, `AllowUsers bms-tunel@192.168.1.23 bms-tunel@192.168.1.31`. **Sin ningún Mac**, en lugar
de `AllowUsers` va **`DenyUsers *`**.

| Línea | Para qué |
| --- | --- |
| Marca y comentarios | `Tipo-De-Config` reconoce el fichero por su primera línea |
| `AddressFamily inet` | Solo IPv4: la regla, `AllowUsers` y `from=` hablan IPv4 |
| `HostKey …ed25519_key` | Una sola clave del equipo, la que se compara en el Mac |
| `SyslogFacility AUTH`, `LogLevel VERBOSE` | Al Visor de eventos (OpenSSH/Operational): IP y **huella** de cada entrada y cada reenvío denegado. Nunca un secreto (inv. §1.9) |
| `AllowUsers bms-tunel@<IP>` / `DenyUsers *` | Solo esa cuenta y solo desde esas IP. **Se mira después del intercambio de claves** (§1.2) |
| `AuthenticationMethods publickey`, `PasswordAuthentication no`, `PubkeyAcceptedAlgorithms ssh-ed25519` | Solo clave, y solo `ed25519` |
| `AuthorizedKeysFile none` (global) y el fichero propio **dentro del `Match`** | Las claves solo valen para `bms-tunel`. El `none` va fuera de un `Match` a propósito (CVE-2026-106587, inv. §6) |
| `LoginGraceTime 30`, `MaxAuthTries 3`, `MaxStartups 3:50:10` | Acotan los intentos y las conexiones a medias |
| `ClientAliveInterval 30`, `ClientAliveCountMax 3` | Un túnel muerto se cierra en ~90 s |
| `AllowTcpForwarding no`, `AllowStreamLocalForwarding no`, `AllowAgentForwarding no`, `X11Forwarding no`, `PermitTunnel no`, `GatewayPorts no`, `PermitOpen none`, `PermitListen none` | Cerrado para todos. `AllowStreamLocalForwarding` **sí existe** en Win32-OpenSSH y vale `yes` por defecto (`openssh/win-src/servconf.h:198`); con `no` los sockets y tuberías locales quedan cerrados aunque un día alguien pusiera `PermitOpen any` (probado: «refused streamlocal port forward»). `PermitTunnel no` cubre además el fallo de `restrict` con el túnel tun (CVE-2026-73283/-106586, inv. §1.6). Si un sshd las tuviera por no admitidas, solo apuntaría «Unsupported option» y seguiría (`servconf.c:2654-2658` del fork) |
| `Match User bms-tunel` → `AllowTcpForwarding local`, `PermitOpen 127.0.0.1:8765` | Solo el `-L` de esa cuenta, a ese destino exacto (`PermitListen none` cubre el `-R`) |
| `PermitTTY no`, `MaxSessions 0`, `ForceCommand exit 1` | Ni consola, ni órdenes, ni sftp (inv. §1.7) |
| Sin `Subsystem sftp` | Sin sftp ni scp |

**Lo que no se escribe**, a propósito: `KbdInteractiveAuthentication`, `PermitRootLogin`, `PidFile`
(no aplican; `AuthenticationMethods publickey` ya deja solo la clave); **`StrictModes`** (se queda en
`yes`: en Windows exige que el fichero de claves sea de SYSTEM, Administradores, TrustedInstaller o
**el propio usuario** y que nadie más pueda escribirlo, `w32-sshfileperm.c:61` y `:136-141`; frente a
la cuenta del túnel protege la ACL de §2.4, no `StrictModes`); `DisableForwarding`; `ListenAddress`
(§0.1); `PerSourcePenalties` (encendido por defecto desde 9.8; escribirlo rompería un sshd 9.5); el
`Match Group administrators` de fábrica.

Requisitos de versión: todo existe desde OpenSSH 8.5; Windows 11 trae 8.6 o 9.5 según la versión, y
Windows Update puede traer una más nueva (inv. §1.8; el fork de GitHub va por 10.5). No se compara la
versión: si el sshd del equipo no entiende una línea, `sshd -t` falla y `Aplicar` para con el servidor
parado.

**Comprobado con el propio sshd, no con lo que creemos haber escrito** (`Comprobar-Lo-Que-Se-Aplica`,
anexo C): tras escribirlo, `sshd.exe -T -C user=bms-tunel,host=mac,addr=<IP del primer Mac>` tiene que
dar `allowtcpforwarding local`, `permitopen 127.0.0.1:8765`, `permitlisten none`, `permittty no`,
`maxsessions 0`, `forcecommand exit 1`, `passwordauthentication no`, `authenticationmethods publickey`,
`allowagentforwarding no`, `gatewayports no` y un `authorizedkeysfile` que acabe en
`bms_tunel_authorized_keys`; `allowstreamlocalforwarding`, `x11forwarding` y `permittunnel`, `no` o
ausentes. Para `user=otra-cuenta`: `allowtcpforwarding no`, `permitopen none` y
**`authorizedkeysfile none` o ninguna línea `authorizedkeysfile`**: desde OpenSSH 10.3,
`AuthorizedKeysFile none` se guarda como lista vacía (`CLEAR_ON_NONE_ARRAY`, `revision-fuentes/servconf-V_10_3_P1.c:538`,
después de rellenar los valores por defecto en `:458`, así que queda vacía y no vale ninguna clave) y
`sshd -T` no imprime la línea (`fuentes/src-win/servconf.c:466` y `dump_cfg_strarray_oneline`,
`:4256-4268`). El 9.6 de verdad imprime `authorizedkeysfile none` (`pruebas-final/resultado.txt`, F3).
El formato exacto de la salida de `-T` en el sshd de Windows **[comprobar en Windows 11]**.

### 2.4 El fichero de claves exacto

`C:\ProgramData\ssh\bms_tunel_authorized_keys`, generado por `Texto-Claves` (LF, sin BOM). Con el Mac
de arriba (la clave es el vector de prueba, bytes 0..31):

```
# bms-agent: las claves de los Mac (mac.ps1). No lo cambies a mano: lo rehace mac.bat.
restrict,port-forwarding,permitopen="127.0.0.1:8765",from="192.168.1.23",command="exit 1" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4f bms-mac-oficina
```

- **Las opciones las pone el script, nunca el dueño.** De lo que llega del Mac (`Clave-Publica-Valida`)
  se acepta solo `ssh-ed25519 <68 caracteres de base64> [comentario]`, blob de 51 bytes con la cabecera
  exacta, y se guarda solo `ssh-ed25519 <base64>`; el comentario se cambia por `bms-<nombre>`.
- **Las opciones**: `restrict`, `port-forwarding`, `permitopen="127.0.0.1:8765"` (que se cruza con
  `PermitOpen`), `from="<IP>"`, `command="exit 1"`.
- **Permisos** (`Solo-Administradores`): `& $Icacls <fichero> /inheritance:r /grant:r *S-1-5-18:F
  *S-1-5-32-544:F` y `/setowner *S-1-5-32-544`. Por SID, nunca por nombre. **La cuenta del túnel ni lo
  lee ni lo cambia porque nadie se lo da**; lo lee sshd desde su proceso de SYSTEM **[comprobar en
  Windows 11]** que sshd lo acepta así para un usuario estándar. **La prueba de que `StrictModes` está
  en vigor no es darle escritura a `bms-tunel`** (eso Windows lo permite: es «el propio usuario»), sino
  a **otra** cuenta: con `icacls … /grant *S-1-5-32-545:W`, el Visor de eventos tiene que decir «Bad
  permissions. Try removing permissions for user: BUILTIN\Users…» y «Authentication refused», y el Mac
  no entra; `mac.bat -Instalar` lo deja bien (§5.2).
- **La huella** de cada clave (`Huella-Sha256`): `"SHA256:" + base64(SHA-256(blob))` sin `=`, igual que
  `ssh-keygen -l -E sha256` (vector: `SHA256:ZkAslGjFiUHdGf/WUL8rQvkib4PTvQatUV0OUQSncCA`).

### 2.5 El cortafuegos (`Poner-Reglas`)

```powershell
# "resto": bloquea el 22 de sshd.exe a todos menos a los Mac, en cualquier perfil.
New-NetFirewallRule -Name BMS-Tunel-Mac-sshd-resto -DisplayName "BMS - tunel del Mac (sshd): nadie mas" `
    -Direction Inbound -Action Block -Protocol TCP -LocalPort 22 -Program $Sshd `
    -Profile Any -RemoteAddress @("0.0.0.0-192.168.1.22", "192.168.1.24-255.255.255.255")
# Los Mac, en cualquier perfil (la red no se cambia a privada).
New-NetFirewallRule -Name BMS-Tunel-Mac-sshd -DisplayName "BMS - tunel del Mac (sshd): solo los Mac" `
    -Direction Inbound -Action Allow -Protocol TCP -LocalPort 22 -Program $Sshd `
    -Profile Any -RemoteAddress @("192.168.1.23")
```

- `-RemoteAddress` de "resto" es todo IPv4 menos los Mac (`Resto-De`, probado con IP sueltas,
  contiguas y una `/24`). Un bloqueo gana a cualquier regla que deje pasar: si Windows Update volviera a
  encender `OpenSSH-Server-In-TCP`, o alguien añadiera otra, el 22 seguiría cerrado para los demás.
- `Poner-Reglas -Cerrado` deja solo "resto" con `Any` (nadie): es lo primero que hace `Aplicar` y lo que
  queda si algo falla.
- La de Microsoft se **deshabilita** (no se borra); se apunta si estaba encendida, para `-Quitar`.
- **La categoría de la red no se toca** (ni `Set-NetConnectionProfile` ni `Set-NetFirewallProfile`):
  cambiarla a privada enciende para cualquier equipo de la red todas las reglas de entrada del perfil
  Privado. Las dos reglas valen en cualquier perfil, acotadas a `sshd.exe`, al 22 y a las IP de los Mac.
  `-Estado` enseña la categoría de cada red (solo información) y avisa si el perfil activo tiene
  «bloquear todas las conexiones entrantes» (`AllowInboundRules` en `False`), que también taparía la
  regla de los Mac.
- El tráfico local no lo filtra el cortafuegos (`instalacion-nativa.md:404-406`): la conexión de sshd a
  la app no necesita regla, y un programa del propio equipo llega al 22 (§1.2).

### 2.6 La huella del mini PC

`C:\ProgramData\ssh\ssh_host_ed25519_key.pub`, que crea el servicio la primera vez que arranca
(`contrib_win32_win32compat_wmain_sshd.c`). `-Instalar`, si no existe, arranca el servicio **una vez con
el cortafuegos ya cerrado y la carpeta ya comprobada** (§2.8). `Decir-Para-El-Mac` la enseña al final de
`-Instalar` y `-AnadirClave`, y `-Estado` siempre:

```
En el Mac (preparar.command) te va a pedir:
   la IP de este equipo: 192.168.1.10   (Ethernet)
   y que compares la huella de este equipo: SHA256:…
```

### 2.7 `-Estado`

Sin cambiar nada, con «bien», «aviso» o **«mal»** (rojo) por línea. Nunca enseña una clave entera.

```
El tunel del Mac en este equipo
   servidor     bien  sshd Running, inicio Automatic; sshd.exe 9.5.x.x
   carpeta ssh  bien  C:\ProgramData\ssh es de los administradores y nadie mas la cambia
   config       bien  la de bms-agent, sin cambios a mano, sshd -t sin errores
   reenvio      bien  solo 127.0.0.1:8765 de este equipo; sin consola, sin ficheros, sin -R
   cuenta       bien  bms-tunel: sin grupos propios; pantalla, Escritorio remoto, tareas y servicios denegados; no caduca; oculta
   datos        bien  ni bms-tunel ni Todos/Usuarios/Usuarios autenticados leen C:\bms-agent (secretos, estado, buzon)
   scripts      bien  nadie mas puede cambiar mac.bat ni lo del Mac (preparar 3f2a..., abrir-bms 91c0...)
   claves       bien  1 Mac
                      mac-oficina      192.168.1.23       SHA256:…  desde 2026-11-25
   cortafuegos  bien  el 22 solo para los Mac (cualquier red); el resto, bloqueado
   red                Ethernet: 192.168.1.10/24, red Public (da igual para el tunel)
   tuneles            1 abierto ahora: mac-oficina (192.168.1.23); 3 procesos de sshd
   app          bien  contesta en 127.0.0.1:8765 (com.docker.backend)
   huella de este equipo: SHA256:…   (la que tiene que ensenar el Mac la primera vez)
   entro      25-11-2026 09:14  mac-oficina desde 192.168.1.23
   rechazos     bien  0 en los ultimos 7 dias (Visor de eventos: OpenSSH, Operational)
   windows      bien  ultima actualizacion instalada: 12-11-2026 (sshd se actualiza con Windows Update)
```

Qué mira: el servicio y `VersionInfo.FileVersion` de `sshd.exe`; `Carpeta-Ssh-Segura` (**mal** si hay
pegas); `Tipo-De-Config` y el SHA-256 apuntado; `sshd -t`; `Comprobar-Lo-Que-Se-Aplica`; la cuenta
(`Grupos-De-La-Cuenta` por ADSI: si falla, **mal** «no se han podido mirar sus grupos»; las cuatro
negaciones en un `secedit /export`; sin caducidad; oculta); `Lectores-De-Datos` sobre `Rutas-De-Datos`
(**mal** si alguien lee); `Quien-Mas-Puede-Cambiar` (ya pasó antes de elevar) y el SHA-256 de los dos
`.command` de `mac\`; que el fichero de claves sea byte a byte el que generaría `Texto-Claves`; las tres
reglas (la de Microsoft encendida es aviso); la categoría de cada red y `AllowInboundRules` de su perfil;
los túneles abiertos (`Get-NetTCPConnection -LocalPort 22 -State Established`, con la IP traducida al
nombre del Mac) y cuántos `Procesos-De-Sshd`; si la app contesta y quién escucha en el 8765; los cinco
últimos «Accepted publickey» y los rechazos de la semana del registro `OpenSSH/Operational`; la fecha
del último acumulado (`Get-HotFix`): **mal** si tiene más de 35 días («actualiza Windows o, hasta
entonces, mac.bat -Apagar»). El nombre del registro, el texto de sus líneas y que `Get-HotFix` dé la
fecha **[comprobar en Windows 11]**.

### 2.8 Cómo se aplica, idempotencia y cómo se deshace

**El estado** (`HKLM:\SOFTWARE\bms-agent\TunelMac`, valor `Estado`, JSON compacto; nada secreto):

```json
{"version":1,"instalado":"2026-11-25 09:02",
 "antes":{"capacidad":"NotPresent","carpeta":false,"config":"ausente","servicio_inicio":"",
          "servicio_en_marcha":false,"regla_microsoft":"no_existe"},
 "apagado":false,"config_sha256":"<SHA-256 del sshd_config escrito>",
 "macs":[{"nombre":"mac-oficina","ip":"192.168.1.23","clave":"ssh-ed25519 AAAA…","alta":"2026-11-25"}]}
```

**`Aplicar`** (lo usan `-Instalar`, `-AnadirClave`, `-QuitarClave`, `-Apagar` y `-Encender`; código en el
anexo C), en este orden, y si algo falla **sshd queda parado y el cortafuegos cerrado**:

1. `Poner-Reglas -Cerrado`; `Stop-Service sshd -Force`; **`Parar-Tuneles`**: todos los procesos
   `sshd*.exe` (`Win32_Process` con `Name LIKE 'sshd%'`, de `System32\OpenSSH` o sin ruta visible) con
   `taskkill /F /PID` por su ruta (habilita el privilegio de depuración que piden los procesos de SYSTEM
   y de `bms-tunel`; `Stop-Process` podría dar «acceso denegado»), **y se vuelve a mirar** hasta 10 s.
   Si queda alguno, se sigue (para que los demás Mac no se queden sin túnel) y al final se dice en
   **rojo**: «queda N proceso(s) de un túnel que Windows no ha dejado cortar: reinicia el equipo ahora;
   al volver, solo entran los Mac de la lista». Que `Stop-Service` solo no los corte, y que `taskkill`
   sí, **[comprobar en Windows 11]** con un sshd 9.5 y, si llega, con uno ≥ 9.8.
2. `Carpeta-Ssh-Segura` (§2.8.1): con pegas, `Fallar` («`mac.bat -Instalar` lo arregla»).
3. Escribe el fichero de claves (`Escribir-Ascii`: `UTF8Encoding($false)`) y le pone sus permisos.
4. Escribe `sshd_config.bms-nueva` y `sshd.exe -t -f sshd_config.bms-nueva`. Si falla, la borra y para
   con el texto de sshd.
5. `Move-Item` sobre `sshd_config`; apunta su SHA-256 en el estado.
6. `Comprobar-Lo-Que-Se-Aplica` (§2.3).
7. Si está apagado: inicio `Disabled` y fin. Si no: inicio `Automatic`, `Start-Service`, espera a que
   escuche el 22 (20 s) y `Poner-Reglas` con los Mac.

#### 2.8.1 `C:\ProgramData\ssh` tiene que ser de los administradores

Cualquier usuario puede crear carpetas en `C:\ProgramData` y queda como su dueño
**[comprobar en Windows 11]** con `icacls C:\ProgramData`. El servicio crea `ssh` con
`O:BAD:PAI(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1200a9;;;AU)` **solo si no existe**
(`contrib_win32_win32compat_wmain_sshd.c:138`, `create_directory_withsddl`, `openssh/win-src/misc.c:1422-1450`);
si existe, `check_secure_folder_permission` solo apunta «Bad owner» y sigue
(`contrib_win32_win32compat_w32-sshfileperm.c:190-196`, `:224-226`). Si «bms» la creara antes,
podría cambiar después lo que sshd (SYSTEM) lee, o leer la clave privada del equipo.

`Carpeta-Ssh-Segura` (anexo C) mira la carpeta y todo lo que hay dentro (también `logs`): que nada sea
un enlace; que el dueño sea SYSTEM, Administradores o TrustedInstaller; que ninguna regla `Allow` dé a
otro escribir, añadir, borrar, cambiar permisos o hacerse dueño; y que nadie más lea las claves privadas
del equipo (`ssh_host_*_key`). La lectura de Usuarios autenticados en la carpeta (la del SDDL de sshd)
es normal.

Si hay pegas en `-Instalar`: lo explica, pide `si` y **aparta la carpeta entera**
(`Apartar-Carpeta-Ssh`: para sshd, `Move-Item` a `C:\ProgramData\ssh.apartada-AAAAMMDD-HHMMSS`, y
después `takeown /A /R` e `icacls /inheritance:r` solo SYSTEM y Administradores, para que nada de dentro
se use); el servicio la vuelve a crear con su SDDL en el primer arranque, con **claves del equipo
nuevas** (si ya había Mac, cada uno tiene que volver a comparar la huella: lo dice en rojo). Si no se
puede mover (algo la tiene abierta): para con «reinicia el equipo y repite `mac.bat -Instalar` antes de
abrir nada más». En `Aplicar` y en `-Estado`, con pegas, falla cerrado / **mal**. `-Quitar` no toca las
carpetas apartadas (lo dice).

**`-Instalar`**, paso a paso:

1. *Antes de elevar*: `Quien-Mas-Puede-Cambiar` (§2.11) y, si hay una clave en la memoria o el dueño
   quiere, `Pedir-Mac` (§2.13).
2. Si `sshd_config` es **«otra»** y no hay `-SustituirConfiguracion`: para sin tocar nada (§2.9).
3. Si el servicio `sshd` existe y su ejecutable no está en `C:\Windows\System32\OpenSSH`: para.
4. **`Lectores-De-Datos`** (`Rutas-De-Datos`: la carpeta del proyecto o `<Raiz>`, y sus `datos`,
   `buzon`, `docker\secretos`, `docker\secretos\correo` y `docker\estado` que existan): si Todos,
   Usuarios autenticados, Usuarios, Red o Cuenta local pueden leer alguna, para: «Con Docker:
   `proteger.bat -Usuario bms` (o pon el proyecto en tu carpeta de usuario si no usas «bms»); en la
   nativa, `instalar.bat`».
5. Si el servicio ya estaba en marcha, o hay `administrators_authorized_keys` o algún
   `C:\Users\*\.ssh\authorized_keys`: lo dice («desde ahora solo entrará el túnel del Mac»).
6. Dice lo que va a hacer y pide `si`.
7. **La foto de antes**, guardada antes de cambiar nada (solo la primera vez). Si es una repetición y el
   `sshd_config` nuestro se cambió a mano: copia `sshd_config.cambiada-AAAAMMDD-HHMMSS` y lo rehace.
8. `Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0` si falta.
9. Deshabilita `OpenSSH-Server-In-TCP` y `Poner-Reglas -Cerrado`, **antes de arrancar nada**.
10. `Carpeta-Ssh-Segura`; con pegas, `Apartar-Carpeta-Ssh` (con `si`).
11. Si no está la clave del equipo: `Start-Service sshd`, 5 s, `Stop-Service` (con el cortafuegos
    cerrado; un programa local podría hablarle en esos 5 s, como con el servicio en marcha); y otra vez
    `Carpeta-Ssh-Segura`: con pegas, para.
12. Guarda el `sshd_config` de antes como `sshd_config.antes-bms` (si había uno y aún no está guardado).
13. `Asegurar-Cuenta` (§2.2: cuenta, grupos por ADSI, `Negar-Inicios`, oculta). Si `Negar-Inicios`
    falla, para (con sshd parado).
14. Si llegó un Mac validado: lo pone en el estado (sustituye al del mismo nombre). `Aplicar`.
15. `Decir-Para-El-Mac` y «Pulsa Intro».

**Idempotencia**: cada paso mira antes de hacer y lo generado se rehace siempre entero desde el estado.

**`-Quitar`** (pide `si`) deja el equipo como estaba según la foto:

1. `Stop-Service sshd`, `Parar-Tuneles`, borra las dos reglas propias.
2. `sshd_config.antes-bms` vuelve a ser `sshd_config`; si antes no había, se borra el nuestro.
3. Borra el fichero de claves. `Negar-Inicios -Quitar` (si falla, aviso: quedan cuatro negaciones a un
   SID que ya no existe, inofensivas). Borra el perfil de `bms-tunel` (`Win32_UserProfile` por SID →
   `Remove-CimInstance`), la cuenta y su valor de `UserList`.
4. Si la capacidad **no** estaba antes: `Remove-WindowsCapability`, borra la regla de Microsoft si sigue
   ahí y, si `C:\ProgramData\ssh` no existía antes, pregunta si la borra. «Si Windows lo pide, reinicia».
5. Si la capacidad **sí** estaba: el inicio y el estado del servicio de antes, y la regla de Microsoft.
6. Dice las carpetas `ssh.apartada-*` que haya. Borra `HKLM:\SOFTWARE\bms-agent\TunelMac` (lo último).
   Dice: «En cada Mac: `bash ~/.bms-tunel/preparar.command --borrar`, y un token nuevo para su persona».

**[comprobar en Windows 11]**: que tras `-Quitar` todo queda como antes, en un equipo sin la capacidad y
en uno con ella; y si `Remove-WindowsCapability` ya borra la regla de Microsoft.

### 2.9 Si el `sshd_config` ya tenía cambios del dueño

`Tipo-De-Config` distingue **ausente**, **de fábrica** (igual, sin contar `CR` ni espacios del final, a
`C:\Windows\System32\OpenSSH\sshd_config_default`), **nuestro** (empieza por la marca) y **otra**.

- **otra** → `-Instalar` para sin tocar nada: «C:\ProgramData\ssh\sshd_config tiene cambios que no son
  de bms-agent… Si no se usa para otra cosa: `mac.bat -Instalar -SustituirConfiguracion`».
- **de fábrica pero en uso** → sigue, con el aviso.
- **nuestro cambiado a mano** → copia `sshd_config.cambiada-…` y lo rehace.

### 2.10 Cómo convive con lo demás

- **`comun.ps1`**: `mac.ps1` no lo carga. Copia `Escribir` (`docker/comun.ps1:10-12`), `Es-Si`
  (`docker/comun.ps1:90-95`) y `Es-Administrador` (`windows/comun.ps1:53-56`) con el mismo código (una
  prueba lo exige) y su propio `Fallar` con `Esperar-Intro`. Por eso no está en `SCRIPTS` de
  `tests/test_entorno_local.py:300-303` ni en el de `tests/test_instalacion_nativa.py:1119-1120`: tiene
  su prueba propia (§5.1).
- **Docker y el programa**: `mac.ps1` no llama a `docker`, no para ni arranca nada, no toca
  `docker\estado`: no pausa la automatización ni toma el cerrojo (paso 18 §4.4).
- **El usuario «bms»** (paso 18 §4.2): el túnel necesita lo mismo que el dueño en su cuenta: la sesión
  de «bms» iniciada (bloqueada) y Docker Desktop en marcha. Y la carpeta del proyecto protegida (§2.12).
- **El vigilante de `iniciar.ps1 -EnSegundoPlano`** mira quién **escucha** en el 8765: sshd no escucha
  ahí (se conecta).
- **La nativa**: `windows/comprobar.ps1:85-108` enseña lo que escucha en `127.0.0.1`. sshd escucha en
  `0.0.0.0:22`; se añade allí una línea informativa si existe el estado del túnel («sshd del túnel del
  Mac: solo reenvía a 127.0.0.1:8765, solo desde <IP>; su parte previa a la clave la alcanza cualquier
  programa de este equipo»), leyendo el registro, sin elevar. **Lo que sshd no hace** es el hueco de
  `instalacion-nativa.md:398-410` (reenviar a internet): solo reenvía al 8765 y con la clave de un Mac.
  **Lo que sí hace**: el lector (que abre PDF de fuera) puede hablar con la parte de sshd previa a la
  clave (§1.2).
- **Windows Update** actualiza sshd con el acumulado (inv. §1.1). Si un día trae OpenSSH ≥ 9.8 o ≥ 10.3,
  `Parar-Tuneles` y `Comprobar-Lo-Que-Se-Aplica` ya cuentan con ello.

### 2.11 Lo que corre como administrador o va al Mac, que otra cuenta no puede cambiar

`mac.ps1` es el primer script de `docker\` que corre como administrador, y `mac\` es código que acaba
corriendo como el dueño en el Mac. Si otra cuenta del equipo (la de «bms») pudiera cambiarlos, correría
lo suyo como administrador aquí o como el dueño allí: el sandbox se perdería.

`Quien-Mas-Puede-Cambiar` (anexo C), **antes de pedir ser administrador** y otra vez ya elevado, mira:

- **Los ficheros**: `mac.ps1`, `mac.bat` y, si existe la carpeta `mac\` junto a la del script
  (`<proyecto>\mac` o `<Raiz>\mac`), `preparar.command`, `abrir-bms.command` y `LEEME.txt`. Nadie puede
  escribir, añadir, cambiar atributos, borrar, cambiar permisos ni hacerse dueño.
- **Sus carpetas** (`docker\` o `windows\`, y `mac\`): además, **nadie puede crear ficheros ni
  carpetas** en ellas (un `powershell.cmd` plantado junto a `mac.bat`).
- **Cada carpeta de más arriba, hasta la raíz**: nadie puede borrarla, renombrarla (borrar hijos en la de
  arriba), cambiar permisos ni hacerse dueño (crear subcarpetas en `C:\`, que pueden todos, no importa).
- **El dueño de cada una de esas cosas** tiene que ser SYSTEM, Administradores, TrustedInstaller o quien
  lo abre: el dueño puede cambiar los permisos aunque ninguna regla se lo dé
  (`fuentes-seg/understand-security-identifiers.md:143`, «Owner Rights»).
- Ninguna puede ser un enlace (punto de reanálisis).

Solo cuentan las reglas `Allow` que se aplican al propio objeto (no las solo heredables, como
`CREATOR OWNER`). Los permitidos son exactamente SYSTEM, Administradores, TrustedInstaller y el SID de
quien lo abrió. Si algo no cuadra: «Otra cuenta de este equipo puede cambiar lo que mac.bat ejecuta como
administrador o lo que va al Mac (<ruta>: <cuenta>). Así no se sigue. Con Docker: proteger.bat. En la
nativa: instalar.bat lo deja bien.»

**Pasa**: con el proyecto protegido por `proteger.bat` (§2.12); con el proyecto en la carpeta de usuario
del dueño (sin «bms»); en la nativa (`C:\BMS\windows` y `C:\BMS\mac`, `instalar.ps1:359-381`). **No
pasa**: en una carpeta creada en `C:\` sin proteger (hereda Usuarios autenticados: Modificar), ni en una
clonada por «bms» (su dueño), ni dentro de OneDrive (enlaces) **[comprobar en Windows 11]** los casos.

Es una comprobación de **higiene**, no de manipulación: si el fichero ya estuviera cambiado, el código
cambiado podría saltársela. Lo que asegura es que el estado normal sea seguro, y la confianza de partida
es la de siempre: la carpeta que entregó quien mantiene el programa, protegida justo después de ponerla
(§2.12). `-CopiarParaElMac` copia lo del Mac **solo después** de esta comprobación.

### 2.12 La carpeta del proyecto protegida (`proteger.bat`, Docker con «bms»)

En la variante Docker del paso 18, «bms» ejecuta `<repo>\docker\ciclo.ps1` (paso 18, `diseno.md:1021`),
escribe la pausa, el cerrojo y los registros en `docker\estado` (`:1059-1060`, `:1132`) y su Docker
Desktop monta `docker\secretos\correo` (`:167-168`, `:454`). El dueño, con su cuenta, abre `persona.bat`,
`iniciar.bat`, `mac.bat`… de la misma carpeta. Ninguna ubicación «natural» sirve sin más: en el perfil
del dueño, «bms» no la lee; clonada por «bms», es suya; creada en `C:\`, hereda «Usuarios
autenticados: Modificar» y **«bms» puede cambiar los scripts que abre el dueño** (y `bms-tunel`, que
está en Usuarios, leería `docker\secretos\anthropic_api_key.txt` y el `.pem` del correo). Eso es un
problema del paso 18 aunque no haya Mac; este diseño lo resuelve porque el Mac lo necesita.

**`docker\proteger.bat -Usuario bms`** (anexo D; se eleva solo, como `mac.bat`), una vez al poner la
carpeta y **otra cada vez que se ponga una versión nueva** (antes de `iniciar.bat`):

1. Comprueba: 64 bits; la carpeta del proyecto (`Split-Path -Parent $PSScriptRoot`) no es la raíz de un
   disco ni está en `%SystemRoot%`, `%ProgramFiles%`, `%ProgramFiles(x86)%` o `%ProgramData%`; ni ella
   ni nada de su primer nivel es un enlace; el usuario existe, no es quien lo abre y no es administrador
   (ADSI, por SID).
2. Explica y pide `si`: «Hazlo justo después de poner la carpeta, antes de que «bms» arranque nada con
   ella» (es el momento de confianza, como el de cualquier instalación).
3. Ya elevado, con `$Icacls` por ruta: `/setowner *S-1-5-32-544 /T /C`; la raíz `/inheritance:r` con
   `SYSTEM:(OI)(CI)F`, `Administradores:(OI)(CI)F`, **el dueño `(OI)(CI)M`**, **«bms» `(OI)(CI)RX`**, y
   fuera cualquier otro permiso puesto a mano (como `instalar.ps1:336-345`); todo lo de dentro
   `/reset /T` (hereda solo eso); y **`M` para «bms» solo en `docker\estado` y `docker\secretos\correo`**
   (`$EscribeBms`; las crea si faltan).
4. Comprueba que en la raíz solo quedan esos cuatro, y lo dice.

Así: «bms» lee lo que necesita (también los secretos, que su Docker Desktop monta) y solo escribe donde
el ciclo escribe; nadie más del equipo lee el proyecto (ni `bms-tunel`, ni Todos, ni Usuarios); los
ficheros que el dueño cree después son suyos (permitidos en §2.11). **Si el paso 15 añade otra carpeta en
la que escriba «bms»**, se añade a `$EscribeBms` (una prueba compara la lista con lo que escriben los
scripts del paso 15, §5.1). Lo que no hace: nada en la nativa (allí `instalar.ps1` ya protege `<Raiz>`),
nada con Docker, nada fuera de la carpeta del proyecto.

### 2.13 Lo que se pregunta antes de elevar, y lo que se copia al Mac

**La ventana de administrador no recibe ficheros arrastrados desde el Explorador** (UIPI: los mensajes
de arrastre de un proceso de integridad media no llegan a uno de integridad alta; Microsoft, «Why
doesn't drag and drop work when my application is running elevated?»). Por eso **todo lo que hay que
preguntar del Mac se pregunta en la ventana normal** (`Pedir-Mac`, anexo C, en el bloque
`if (-not $Elevado)`), y nada pide arrastrar:

1. **La clave, sin escribir rutas**: `Claves-En-Memorias` busca `bms-*.pub` en la carpeta `bms-mac` de
   cada unidad lista que no sea la del sistema (`[IO.DriveInfo]::GetDrives()`, sin administrador), donde
   la deja `preparar.command`. Con una, propone usarla («Intro para usar E:\bms-mac\bms-mac-oficina.pub»)
   y saca el nombre del Mac del nombre del fichero. Si no, pide la ruta o la línea pegada.
2. El nombre (si no vino), la IP del Mac (o `red`), y con un nombre que ya existe, «¿cambiarlo?» y «¿con
   la misma clave?».
3. **La huella de la clave del Mac**, para compararla con la pantalla del Mac, y `si`.
4. Pasa a la ventana de administrador `-Nombre`, `-Ip`, `-Clave <base64>` y `-MismaClave`, que allí se
   vuelven a validar (`Origen-Valido`, `Clave-Publica-Valida`).

En la nativa con otro usuario de instalación, el dueño ya está en una Terminal de administrador: las
preguntas salen en la misma ventana y la clave se encuentra igual en la memoria (sin arrastrar).

**`-CopiarParaElMac <carpeta>`** (sin administrador; en la nativa, desde la Terminal de administrador):
tras `Quien-Mas-Puede-Cambiar` (que incluye `mac\`), copia los tres ficheros a `<carpeta>\bms-mac`
(pregunta si ya existe), enseña el SHA-256 corto de cada uno (para quien mantiene el programa) y la IP
de este equipo, que el Mac pedirá.

---

## 3. El lado del Mac

### 3.1 La carpeta `mac/`

| Fichero | Qué es | Tamaño |
| --- | --- | --- |
| `mac/preparar.command` | Una vez por Mac (y repetible): clave, huella, configuración, prueba, `BMS` en el Escritorio (anexo A) | ~300 líneas |
| `mac/abrir-bms.command` | Cada día: abre el túnel y la app; lo reabre si se corta y guarda el puerto mientras tanto (anexo B) | ~175 líneas |
| `mac/LEEME.txt` | Qué es y dónde está la guía (abajo) | 9 líneas |

`mac/LEEME.txt`:

```
bms-agent: lo de esta carpeta es para un Mac, no para el mini PC.
Sirve para abrir la app del mini PC desde el navegador de un Mac de la misma red,
por un tunel cifrado. Nada del programa se instala en el Mac.

Se lleva al Mac con mac.bat -CopiarParaElMac (en el mini PC), no copiandola a mano.
La primera vez: en Terminal, escribe "bash " (con el espacio), arrastra aqui
preparar.command y pulsa Intro. Despues, cada dia: BMS en el Escritorio.

La guia paso a paso: docs/entorno-local.md, apartado "Usarlo desde un Mac".
```

- **Fin de línea LF** (bash no lee CRLF). En `.gitattributes`: `mac/*.command text eol=lf` y
  `mac/*.txt text eol=lf`. Así también una copia hecha desde el clon del mini PC lleva LF.
- **Modo `100755` en git** (`git update-index --chmod=+x mac/*.command`): ayuda con `git clone`, pero no
  se depende de él (3.2).
- **ASCII**, `#!/bin/bash`, **bash 3.2** de Apple (nada de arrays asociativos, `${v,,}`, `mapfile`,
  `readarray`, `|&`, `&>>`, `coproc`, `wait -n`). **`export PATH=/usr/bin:/bin:/usr/sbin:/sbin`** en la
  segunda línea de código, y las herramientas que importan además por su variable con ruta completa
  (`SSH=/usr/bin/ssh`, `SSH_ADD`, `SSH_KEYGEN`, `SSH_KEYSCAN`, `NC=/usr/bin/nc`, `CURL`, `OPEN`,
  `PGREP=/usr/bin/pgrep`, `LSOF=/usr/sbin/lsof`): un OpenSSH de Homebrew no entiende `UseKeychain`
  (inv. §4.1), y nada del `PATH` del dueño decide qué corre.
- Requisito: **macOS 12 o más** (`ssh-add --apple-use-keychain`; Safari 15.4) **[comprobar en macOS]**.

### 3.2 Cómo llega al Mac y cómo se abre la primera vez

**Con una memoria USB formateada en exFAT o FAT32** (las de fábrica lo están; una formateada en el Mac
como «Mac OS Plus» o APFS no se lee en Windows), y **siempre con `mac.bat -CopiarParaElMac`**, que copia
`mac\` a `<memoria>\bms-mac` **después** de comprobar que ninguna otra cuenta del mini PC ha podido
cambiarla (§2.11, §2.13). La misma memoria trae de vuelta la clave pública del Mac: `preparar` la deja
en `bms-mac` y `mac.bat` la busca ahí. (Un `git clone` o el ZIP de GitHub funcionan igual en el Mac,
pero no pasan por esa comprobación: la guía no los ofrece.)

**La primera vez se abre así**: Terminal → escribir `bash ` (con el espacio) → arrastrar
`preparar.command` desde la memoria → Intro. Pasar el fichero a `bash` no lo "abre" Launch Services, así
que ni el bit de ejecución ni la cuarentena importan (inv. §4.5) **[comprobar en macOS]**. **macOS
preguntará si Terminal puede acceder a los archivos de un volumen extraíble** (y luego al Escritorio):
hay que decir **Permitir**; si se dice que no, `bash` da «Operation not permitted» (se arregla en
Ajustes del Sistema → Privacidad y seguridad → Archivos y carpetas → Terminal) **[comprobar en macOS]**.

Nada más empezar, `preparar` copia los dos scripts a `~/.bms-tunel/` con `cp -X` (sin atributos
extendidos, o sea sin cuarentena), les pone `chmod 700` y quita la cuarentena **solo** de
`abrir-bms.command` (`xattr -d com.apple.quarantine`, nunca `-r` ni `-c`): desde la segunda vez ya no
hace falta la memoria (`bash ~/.bms-tunel/preparar.command`). Al final crea en el Escritorio el enlace
**`BMS.command`** → `~/.bms-tunel/abrir-bms.command`, **comprobando que se ha creado**; si no (TCC), lo
dice y da la otra forma (`bash ~/.bms-tunel/abrir-bms.command`). Que el doble clic en el enlace abra
Terminal y lo ejecute **[comprobar en macOS]**.

### 3.3 `preparar.command`

Una máquina de estados que se puede repetir (texto completo en el anexo A):

0. Se niega si hay un túnel suyo abierto (`pgrep -U "$(id -u)" -f "ssh -F <config> -N"`); crea
   `~/.bms-tunel` (`700`) y se copia allí (3.2).
1. **La clave** (si no existe): nombre corto del Mac (`^[a-z0-9][a-z0-9-]{0,30}$`); `ssh-keygen -q -t
   ed25519 -a 100 -C bms-<nombre>` (pide la frase dos veces); **sin frase no vale** (si
   `ssh-keygen -y -P ""` la abre, la borra y vuelve a pedir); `ssh-add --apple-use-keychain` (la frase al
   Llavero, una vez).
2. **Para el mini PC**: si corre desde la memoria, copia `bms-<nombre>.pub` junto a `preparar.command`
   (`<memoria>/bms-mac`, donde lo busca `mac.bat`; si no se puede, al Escritorio); la pone en el
   portapapeles; enseña el nombre, **la IP de este Mac** (`route -n get default` → `ipconfig getifaddr`)
   y **la huella de su clave**.
3. **El mini PC**: pide su IP (la enseñan `mac.bat -CopiarParaElMac` y `-Estado`) o confirma la
   guardada, solo IPv4 privada; `nc -z -G 5 <IP> 22`. Si no contesta: «falta `mac.bat -Instalar` (o
   `-AnadirClave`) con la IP de este Mac» y **termina bien** (código 0): al repetir, sigue aquí.
4. **La huella del mini PC**: `ssh-keyscan -T 5 -t ed25519` → `bms-minipc ssh-ed25519 …` → `ssh-keygen
   -l -E sha256` → la enseña y pide `si` solo si es la misma que enseña el mini PC. Fijada y igual: no
   pregunta; **distinta**: avisa en grande antes de preguntar.
5. **La configuración** `~/.bms-tunel/ssh_config` (3.4).
6. **La prueba**: quita una reserva suya que hubiera quedado (`pgrep -U … -f "nc -lk 127.0.0.1 8765"`); si
   el 8765 del Mac está ocupado, para (3.6); abre el túnel con `BatchMode=yes` en segundo plano y espera
   **hasta 60 s** (la primera conexión crea el perfil de `bms-tunel` en el mini PC) a que **su** `ssh`
   escuche (`lsof -p <pid>`) o se muera. Y distingue: muerto con «Permission denied» → «el mini PC no
   acepta la clave de este Mac todavía: `mac.bat -AnadirClave`»; muerto con la huella → «NO sigas»;
   muerto por otra cosa → las cinco primeras líneas del error y «que el mini PC esté encendido y en la
   misma red, y que la IP de este Mac sea la apuntada (`mac.bat -Estado`)»; vivo sin escuchar a los 60 s
   → «el mini PC tarda: vuelve a probar en un minuto»; escuchando → pide `/consola` con `curl`: `200`
   «funciona»; sin respuesta «el túnel abre, pero la app del mini PC no contesta (sesión de bms y Docker
   Desktop)»; otro código, lo dice.
7. **`BMS` en el Escritorio** (3.2) y cómo se usa.

`bash preparar.command --borrar`: se niega con un túnel abierto; pide `si`; quita una reserva suya;
`ssh-add -d --apple-use-keychain`; `rm -rf ~/.bms-tunel`; quita `BMS.command`; recuerda
`mac.bat -QuitarClave -Nombre <nombre>` y un token nuevo para la persona de ese Mac.

### 3.4 `~/.bms-tunel/` y la configuración del túnel

| Fichero | Qué |
| --- | --- |
| `clave_ed25519`, `.pub` | La clave del Mac (`600`), cifrada con su frase; la frase, en el Llavero |
| `known_hosts` | Una línea: `bms-minipc ssh-ed25519 AAAA…` (fijada a ojo) |
| `ssh_config` | Abajo |
| `ip-minipc`, `nombre` | Lo que preguntó `preparar` |
| `abrir-bms.command`, `preparar.command` | Las copias sin cuarentena |
| `ultimo-error.txt` | Lo que dijo `ssh` la última vez (sin secretos) |

`ssh_config` (lo escribe `preparar`; se usa solo con `/usr/bin/ssh -F ~/.bms-tunel/ssh_config -N
bms-minipc`, y `-F` hace que no se lean `~/.ssh/config` ni `/etc/ssh/ssh_config`):

```
IgnoreUnknown UseKeychain

Host bms-minipc
    HostName 192.168.1.10
    Port 22
    User bms-tunel
    IdentityFile /Users/<usuario>/.bms-tunel/clave_ed25519
    IdentitiesOnly yes
    UseKeychain yes
    AddKeysToAgent yes
    PreferredAuthentications publickey
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    HostKeyAlias bms-minipc
    HostKeyAlgorithms ssh-ed25519
    UserKnownHostsFile /Users/<usuario>/.bms-tunel/known_hosts
    GlobalKnownHostsFile /dev/null
    StrictHostKeyChecking yes
    CheckHostIP no
    UpdateHostKeys no
    LocalForward 127.0.0.1:8765 127.0.0.1:8765
    ExitOnForwardFailure yes
    ServerAliveInterval 15
    ServerAliveCountMax 3
    ConnectTimeout 10
    ForwardAgent no
    ForwardX11 no
    PermitLocalCommand no
    RequestTTY no
    ControlMaster no
    ControlPath none
```

- `HostKeyAlias` + `StrictHostKeyChecking yes` + `CheckHostIP no`: la identidad del mini PC es su
  huella, no su IP.
- `LocalForward 127.0.0.1:8765 127.0.0.1:8765`: escucha solo en el bucle local del Mac y pide
  literalmente lo que `permitopen`/`PermitOpen` admiten.
- `ExitOnForwardFailure yes`: si no puede escuchar en el 8765, `ssh` se cierra.
- `ServerAliveInterval 15` × 3: un mini PC que no contesta se detecta en ~45 s.
- Sin `SessionType none` (OpenSSH 8.7; Monterey trae 8.6): `-N` en la línea de órdenes.
- **La frase**: `abrir-bms` llama a `ssh-add --apple-use-keychain` antes del túnel, que la saca del
  Llavero sin preguntar, y así el `ssh` en segundo plano va con `BatchMode=yes`
  **[comprobar en macOS]** (también tras reiniciar el Mac).

### 3.5 `abrir-bms.command`

Texto completo en el anexo B; ejecutado contra programas falsos en 10 casos (§5.1).

1. Sin `~/.bms-tunel/ssh_config`, `known_hosts` o la clave: «abre antes preparar.command».
2. **Ya abierto en otra ventana**: para cada `pgrep -U "$(id -u)" -f "ssh -F <config> -N"`, solo si
   `lsof -nP -a -p <pid> -iTCP@127.0.0.1:8765 -sTCP:LISTEN` dice que **ese** `ssh` escucha en el 8765,
   abre el navegador y termina. (Con `-U` no se fía de procesos de otra cuenta; con `lsof` no abre el
   navegador hacia un puerto que tenga otro.)
3. Mata una **reserva** suya que quedara de una ventana cerrada de golpe
   (`pgrep -U … -f "nc -lk 127.0.0.1 8765"`).
4. **Si el 8765 del Mac está ocupado** (`nc -z -G 2 127.0.0.1 8765`, que ve a cualquiera): lo dice y para
   (3.6).
5. `ssh-add --apple-use-keychain` (si falla, el túnel va sin `BatchMode`).
6. Bucle: **suelta la reserva justo antes** de `ssh -F … -N -o BatchMode=yes bms-minipc 2>ultimo-error.txt
   &`; espera hasta 60 s a que **su** `ssh` escuche (`lsof`); la primera vez pide `/app` con `curl` y
   abre el navegador (`200` → `/app`; `503` → la consola de antes; sin respuesta → «el túnel está abierto,
   pero la app del mini PC no contesta»); luego `wait`.
7. **En cuanto `ssh` termina, si ya se abrió la app: la reserva** — `nc -lk 127.0.0.1 8765 </dev/null
   >/dev/null &`, un `nc` suyo que acepta y no contesta, comprobado con `lsof` en ≤ 3 s. Así, mientras
   espera para reconectar (el Mac se ha dormido, el mini PC se reinicia de noche), **ningún otro programa
   coge el 8765** y recibe el token que la pestaña de Procesar sigue mandando cada 2 s. Si no puede
   guardarlo (otro programa lo ha cogido en ese instante): para con «cierra la pestaña de la app y pide en
   el mini PC un token nuevo para este Mac».
8. Mira por qué terminó en `ultimo-error.txt`. **Para** si: la huella no es la fijada («NO sigas»),
   «Permission denied» (clave quitada o IP del Mac distinta de la apuntada), «administratively
   prohibited», o el puerto lo cogió otro (`Address already in use`: alguien se coló entre soltar la
   reserva y `ssh`, cosa de milisegundos). Cuando para así con la app ya abierta, **la reserva sigue y la
   ventana espera**: «Cierra la pestaña de la app (o pulsa Salir en ella) y luego pulsa Intro aquí». Si
   nunca llegó a abrir y duró menos de 30 s: enseña el error y para («que el mini PC esté encendido…»).
   Si no: «El túnel se ha cortado… No uses la app hasta que vuelva», espera 5, 10, 20, 40, 60 s (vuelve a
   5 tras un túnel de más de 2 minutos) **con el puerto guardado** y vuelve al paso 6.
9. Cerrar la ventana (o Ctrl+C) manda `HUP`/`INT`: el `trap` mata `ssh` y la reserva y dice «Túnel
   cerrado. Si la app sigue abierta en el navegador: Salir, o cierra la pestaña». Terminal puede preguntar
   «¿Terminar los procesos de esta ventana?» **[comprobar en macOS]**.

**Lo que queda**: si el dueño **cierra la ventana con la pestaña de la app abierta**, el 8765 queda libre
y la pestaña sigue llamando con el token. En un Mac **sin otras cuentas** (la guía lo pide, con el
invitado apagado) nadie más puede escuchar ahí; con otras cuentas, una de ellas podría. Por eso la guía
dice «Salir en la app, y luego cierra la ventana». Cortarlo del todo pediría que la app dejara de
consultar tras varios fallos (un cambio de la app, fuera de M14).

### 3.6 El puerto 8765 del Mac ocupado

La app solo funciona con `Host` y `Origin` en el 8765: no se puede usar otro puerto. Si otro programa
del Mac escucha ahí, el navegador le mandaría la página **y el token**. Por eso `abrir-bms` lo mira con
`nc -z` antes de abrir (y `preparar` antes de probar) y para con «Otro programa de este Mac usa ya el
puerto 8765… ciérralo (o reinicia el Mac)».

**`ExitOnForwardFailure` no es lo que protege en macOS**: con la semántica BSD, un `bind` a
`127.0.0.1:8765` con `SO_REUSEADDR` (que `ssh` pone) sale bien aunque otro programa tenga
`0.0.0.0:8765`, y el tráfico a `127.0.0.1` va al más específico (el de `ssh`). Lo que protege antes de
abrir es el `nc -z`. **Mientras el túnel está abierto**, que otro programa se ponga en `0.0.0.0:8765` no
importa (el tráfico a `127.0.0.1` sigue yendo a `ssh`), y uno de **otra cuenta** no puede ponerse en
`127.0.0.1:8765` mientras lo tiene `ssh` (macOS no deja a un usuario sin privilegios coger una
dirección y puerto que tiene otro usuario) **[comprobar en macOS]** las dos cosas. Mientras el túnel
está cortado, lo guarda la reserva (3.5).

### 3.7 Cerrar el túnel, dormir, reiniciar

- **Cerrar**: «Salir» en la app y luego cerrar la ventana de Terminal (o Ctrl+C). Sin ventana no hay
  túnel.
- **El Mac se duerme**: al despertar, `ServerAliveInterval` detecta el túnel muerto, la reserva guarda el
  puerto y el bucle lo reabre solo.
- **El mini PC se reinicia de noche**: el bucle reintenta (hasta 60 s entre intentos) con el puerto
  guardado mientras la ventana siga abierta; vuelve cuando sshd, la sesión de «bms» y Docker estén
  arriba.
- **Cambió la IP del Mac**: el cortafuegos tira los paquetes (un tiempo de espera); `abrir-bms` dice «que
  la IP de este Mac sea la que tiene apuntada (`mac.bat -Estado`)». Arreglo: `mac.bat -AnadirClave
  -Nombre <el mismo>` → «¿con la misma clave?» `si` → la IP nueva.
- **Cambió la IP del mini PC**: `bash ~/.bms-tunel/preparar.command` → escribir la nueva; la huella
  sigue siendo la misma (alias), no pregunta.

### 3.8 Varios Mac

Una clave por Mac, cada una con su nombre, su IP y su línea; y **una persona por Mac** en la app (M13).
En el mini PC, `mac.bat -AnadirClave` por cada uno; `AllowUsers` lleva todos, la regla de los Mac todas
las IP y "resto" el complemento. Quitar uno corta un momento los túneles de los demás (se reconectan
solos). Nunca se copia una clave de un Mac a otro.

---

## 4. Seguridad

### 4.1 Lo que puede hacer cada uno

| Quién | Qué puede | Qué no | Cómo se corta |
| --- | --- | --- | --- |
| **Quien roba el Mac** (bloqueado, con FileVault) | Nada: sin la contraseña del Mac no hay Llavero ni disco | — | `mac.bat -QuitarClave` y un token nuevo para la persona del Mac, por si acaso |
| **Quien roba el Mac abierto** (sesión iniciada) | Con la wifi de la oficina a su alcance: abrir el túnel y llegar a la **página de entrada**; con el token del Mac a mano (no guardado en el navegador, pero sí en su gestor de claves si está desbloqueado), entrar como **la persona del Mac** (rol `administracion`) mientras no se corte | Ni consola, ni ficheros, ni otro puerto del mini PC, ni salir a internet desde allí; ni personas ni política (no es `administrador`) | **`mac.bat -QuitarClave -Nombre <ese Mac>`** (corta también los túneles abiertos, comprobado; si Windows no deja, reiniciar) **y** `persona.bat -Nombre "<persona del Mac>" -Rol administracion` (token nuevo: el anterior deja de valer, `docker/persona.ps1:1-3`). El token del dueño no cambia |
| **Quien copia la clave** (una copia de seguridad) | Nada sin la frase. Con la frase: lo mismo, pero **solo desde la IP de ese Mac** y en la red de la oficina | Usarla desde otra IP | `-QuitarClave` y crear otra |
| **Alguien en la misma wifi**, sin clave | Ver que el 22 del mini PC no contesta. Si suplanta la IP de un Mac (ARP), llegar a la parte de sshd previa a la clave | Entrar sin la clave; ver lo que va por el túnel | Windows Update al día; `-Apagar` |
| **Alguien en la misma wifi el día de preparar** | Suplantar al mini PC solo con un ataque activo **y** que el dueño acepte una huella distinta de la de la pantalla | — | La comparación de las dos pantallas (M7) |
| **Una web que visite el Mac** | Nada (rebote de DNS → `Host` rechazado; otra web → `Origin` rechazado; sin token no hay órdenes; `serve.py:20-31`) | — | — |
| **Otra cuenta del Mac**, o un demonio de otro usuario | Con el túnel abierto: llegar a la página de entrada, sin token nada. Con el túnel cortado: nada (la reserva tiene el puerto). **Tras cerrar la ventana con la pestaña abierta**: escuchar en el 8765 y recibir el token de la persona del Mac | Coger el 8765 mientras `ssh` o la reserva lo tienen | La guía: un Mac **sin otras cuentas** (invitado apagado) y «Salir» antes de cerrar. Si pasara: token nuevo para la persona del Mac |
| **Una extensión del navegador** con acceso a todos los sitios | Leer lo que se ve (facturas, IBAN) y el token que se escribe | — | La guía: un perfil del navegador solo para la app, sin extensiones |
| **Un programa malicioso en el Mac**, con la sesión del dueño | Lo que pueda el dueño mientras la app está abierta, y abrir el túnel él mismo | Llegar a nada más del mini PC que el 8765 | macOS al día; `-QuitarClave`; token nuevo |
| **Un programa ya comprometido en el mini PC** (de «bms», del dueño; en la nativa, el lector) o **un contenedor con red** (`salida`) | Hablar con la parte de sshd **previa a la clave** por el bucle local (§1.2): solo le sirve un fallo de sshd sin parchear | Entrar sin la clave de un Mac | Windows Update al día (`-Estado` en rojo a los 35 días); `-Apagar` si no se usa el Mac |
| **La cuenta `bms-tunel`**, si alguien consiguiera ejecutar algo con ella (un fallo de sshd **después** de la clave) | Lo de cualquier usuario del equipo en la sesión 0 (está en Usuarios): leer lo que lean Todos, Usuarios o Usuarios autenticados | **Los datos de bms-agent** (el proyecto, sus secretos, el buzón, `<Raiz>\datos`): nada se los da (§2.12; `-Instalar` y `-Estado` lo comprueban). Iniciar sesión en la pantalla, por Escritorio remoto, como tarea o servicio (negado, §2.2). Manejar Docker (no está en `docker-users`). Tocar sus claves | `-Apagar` y avisar |
| **La cuenta «bms»** comprometida | Lo que ya podía (Docker, lo que monta, `docker\estado`) | Cambiar `mac.ps1`, `persona.ps1`, lo de `mac\` u otro script que abra el dueño (§2.11, §2.12); tocar `C:\ProgramData\ssh` (§2.8.1) | — |

### 4.2 Lo que no cambia

- **El token personal** de cada persona: sin él, la app no enseña nada. **El Mac tiene su propia
  persona** (M13): la auditoría separa lo hecho desde el Mac de lo hecho en el mini PC (las peticiones
  llegan las dos de `127.0.0.1`; lo que las distingue es el token).
- **`Host` y `Origin`**, la cabecera del token y el JSON: las mismas comprobaciones en cada petición.
- **La consola sin red**, el lector solo con la API, el correo solo con Microsoft.
- **Ningún secreto en el Mac** más que su clave SSH (y su frase en el Llavero). Ni en registros: el Visor
  de eventos del mini PC guarda IP y huellas; `ultimo-error.txt` guarda mensajes de `ssh`.

### 4.3 Los PDF descargados en el Mac

El dueño lo aceptó. Se quedan en **Descargas** hasta que los borre; cada descarga queda en la auditoría
(`documento_abierto`, `serve.py:892`); con **FileVault** están cifrados en reposo; Time Machine o iCloud
podrían copiarlos fuera si el dueño los mueve allí. La caché del navegador no guarda las respuestas de la
API (`Cache-Control: no-store`).

### 4.4 Lo que añade de superficie, dicho claro

Un servidor SSH escuchando en el `0.0.0.0:22` del mini PC: **desde la red** solo contesta a las IP de los
Mac (cualquier perfil de red), solo acepta una clave `ed25519` de la lista y solo deja abrir el 8765 del
propio equipo; **desde el propio mini PC** (y los contenedores con red), su parte previa a la clave la
alcanza cualquier programa (§1.2). Se actualiza con Windows Update. En octubre de 2026 hubo fallos de
OpenSSH for Windows con ejecución remota sin autenticar, arreglados en el acumulado de ese mes (inv. §6):
por eso `-Estado` pone en rojo un acumulado de más de 35 días, el mantenimiento del mes lo mira, y
`-Apagar` existe para cuando el Mac no se use o haya un aviso sin parche.

---

## 5. Pruebas

### 5.1 Las automáticas, aquí (Linux, sin Windows ni Mac)

**`tests/test_tunel_mac.py`** (nuevo, ~550 líneas). Las de `pwsh` se saltan sin él, como
`tests/test_instalacion_nativa.py:2241-2252` (`_pwsh`); las de `bash`, sin `bash`. Las funciones se
sacan por el AST, como `test_instalacion_nativa.py:2266-2270`, y el código "sin comentarios ni cadenas"
es `_codigo` (`test_instalacion_nativa.py:1127-1130`).

| Prueba | Lo que exige |
| --- | --- |
| `test_los_dos_mac_ps1_son_el_mismo` | `docker/mac.ps1` == `windows/mac.ps1` y `docker/mac.bat` == `windows/mac.bat`, byte a byte |
| `test_los_bat_llaman_a_powershell_por_su_ruta` | `mac.bat` y `proteger.bat`: `@echo off`; la línea `"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0<nombre>.ps1" %*`; `if errorlevel 1 pause`; ninguna línea que empiece por `powershell `; ASCII |
| `test_mac_ps1_no_carga_comun_ni_usa_docker` | En `mac.ps1` y `proteger.ps1`: sin `comun.ps1`, `Comprobar-Docker`, `Pausar-Automatico`; en `_codigo`, ni `docker`, ni `Invoke-Expression`/`iex`, `DownloadString`, `curl`, `wget`, `-EncodedCommand`, `Set-ExecutionPolicy`, `Invoke-WebRequest … -OutFile`, `Add-Type`; `FromBase64String` solo dentro de `Clave-Publica-Valida` y `Huella-Sha256` |
| `test_las_ayudas_son_las_de_comun` | `Escribir`, `Es-Si` y `Es-Administrador` de `mac.ps1` y de `proteger.ps1` (sin comentarios) son las de `docker/comun.ps1` y `windows/comun.ps1` |
| `test_herramientas_del_sistema_por_su_ruta` | `$Icacls`, `$Taskkill`, `$Secedit`, `$Takeown` se definen como `Join-Path $env:SystemRoot "System32\<x>.exe"` y solo se llaman así (`& $Icacls …`); en `_codigo`, ningún `icacls.exe`/`taskkill`/`secedit`/`takeown` a pelo, ningún `Stop-Process` ni `Get-Process -Name sshd` |
| `test_lo_de_sshd_se_escribe_sin_bom` | `Escribir-Ascii` usa `UTF8Encoding($false)`; ningún `Out-File`, `Set-Content` ni `Add-Content`, ni redirección a un fichero; la única otra escritura es `WriteAllText(…, [Text.Encoding]::Unicode)` dentro de `Negar-Inicios` (la plantilla de `secedit`) |
| `test_aplicar_falla_cerrado` | En `Aplicar`, por este orden: `Poner-Reglas -Cerrado` < `Stop-Service` < `Parar-Tuneles` < `Carpeta-Ssh-Segura` < `Escribir-Ascii $FicheroClaves` < `-t -f $ConfigNueva` < `Move-Item` < `Comprobar-Lo-Que-Se-Aplica` < `Start-Service` < `Poner-Reglas $macs`; el aviso en rojo de los procesos que quedan, al final |
| `test_parar_tuneles` | `Procesos-De-Sshd` con `Win32_Process` y `Name LIKE 'sshd%'`; `Parar-Tuneles` con `& $Taskkill /F /PID`, vuelve a mirar en un bucle y devuelve cuántos quedan; `-Quitar` y `Aplicar` lo llaman después de `Stop-Service` |
| `test_instalar_en_orden` | En `-Instalar` (ya elevado): «otra» y la ruta del servicio < `Lectores-De-Datos` < `Read-Host "Seguir?` < `Foto-De-Antes`/`Guardar-Estado` < `Add-WindowsCapability` < `Disable-NetFirewallRule` y `Poner-Reglas -Cerrado` < `Carpeta-Ssh-Segura`/`Apartar-Carpeta-Ssh` < el primer `Start-Service` < otra vez `Carpeta-Ssh-Segura` < `Asegurar-Cuenta` < `Aplicar` |
| `test_no_se_eleva_sin_mirar_quien_puede_cambiar` | `Quien-Mas-Puede-Cambiar` < `Pedir-Mac` < `-Verb RunAs`; los SID permitidos son exactamente SYSTEM, Administradores, TrustedInstaller y `$SidDeQuienLoAbre`; la llamada incluye `$FicherosDelMac` y `$CarpetaDelMac`; la máscara de las carpetas propias incluye `CreateFiles` y `CreateDirectories`; se mira `GetOwner(` y `ReparsePoint`; `-CopiarParaElMac` va después de la comprobación |
| `test_lo_del_mac_se_pregunta_antes_de_elevar` | `Pedir-Mac` y `Elegir-Mac` solo dentro de `if (-not $Elevado)`; ninguna pregunta contiene «Arrastra»; tras `-Verb RunAs`, `-Ip` pasa por `Origen-Valido` y `-Clave` por `Clave-Publica-Valida` antes de usarse; `-Usuario` casa con `^S-1-5-21-` |
| `test_las_reglas_del_cortafuegos` | Exactamente dos `New-NetFirewallRule`, las dos con `-Profile Any -Program $Sshd -LocalPort 22 -Protocol TCP -Direction Inbound`: una `-Action Allow -RemoteAddress $origenes`, otra `-Action Block`; **nunca** `Set-NetConnectionProfile` ni `Set-NetFirewallProfile`; `Remove-NetFirewallRule` solo de `$ReglaMac`, `$ReglaResto` o (en `-Quitar`) `$ReglaMicrosoft`; `Disable-NetFirewallRule` solo de `$ReglaMicrosoft` |
| `test_la_cuenta` | `New-LocalUser` con `-PasswordNeverExpires`, `-UserMayNotChangePassword` y `-Password (Contrasena-Que-Nadie-Guarda)`; ningún `Add-LocalGroupMember` ni `Get-LocalGroupMember` (los grupos, por `Grupos-De-La-Cuenta` con `[ADSI]`, y si lanza, `Fallar`); `$DerechosNegados` son exactamente los cuatro; **ni `SeDenyNetworkLogonRight` ni `SeNetworkLogonRight`** en `_codigo`; `& $Secedit` solo dentro de `Negar-Inicios`; `Asegurar-Cuenta` llama a `Negar-Inicios` y para si devuelve algo; `-Quitar` llama a `Negar-Inicios … -Quitar` antes de `Remove-LocalUser` |
| `test_por_sid_y_nunca_por_nombre` | `icacls` solo con `*S-1-5-18`, `*S-1-5-32-544` o `"*" + <sid>`; ningún `Administrators`, `Administradores`, `Beheerders`, `Users`, `Usuarios`, `Gebruikers`, `Everyone`, `Todos` en `_codigo` |
| `test_ningun_secreto_en_el_estado` | `Guardar-Estado` solo recibe `version`, `instalado`, `antes`, `apagado`, `config_sha256`, `macs` (y en cada Mac `nombre`, `ip`, `clave`, `alta`); la contraseña no sale de `Contrasena-Que-Nadie-Guarda` más que a `New-LocalUser` |
| `test_pwsh_analiza_mac_ps1` (pwsh) | `Parser::ParseFile` sin errores en los dos `mac.ps1` y en `proteger.ps1` |
| `test_pwsh_el_sshd_config` (pwsh) | `Texto-Config` con 0, 1 y 2 Mac: **igual, carácter a carácter, al bloque de §2.3** (con uno; `DenyUsers *` sin `AllowUsers` con 0); cada directiva una vez fuera del `Match`; el `Match` con sus tres líneas; están `AllowStreamLocalForwarding no`, `X11Forwarding no` y `PermitTunnel no`; nunca `Subsystem`, `PasswordAuthentication yes`, `AllowTcpForwarding yes`, `GatewayPorts yes`, `PermitOpen any`, `StrictModes`, `DisableForwarding`, `ListenAddress`, `PerSourcePenalties`, `Match Group`, `administrators_authorized_keys`, `PermitRootLogin`, `localhost`; sin `\r` ni BOM |
| `test_pwsh_comprobar_lo_que_se_aplica` (pwsh) | Con un `sshd` falso (un `.ps1` que imprime según `user=`, como `pruebas-final/sshd-falso.ps1`): salida de 9.6 → bien; de ≥ 10.3 (sin `authorizedkeysfile` para otra cuenta) → bien; `authorizedkeysfile .ssh/authorized_keys` para otra cuenta → falla; `permitopen any` → falla; `x11forwarding` ausente → bien, `yes` → falla; salida vacía → falla |
| `test_pwsh_las_negaciones` (pwsh) | `Texto-Negaciones` y `Diferencias-De-Derechos` con los casos de `pruebas-final/probar.ps1` (añade y quita la cuenta sin tocar lo que había; nunca la red; ve otro derecho cambiado; una línea vacía que `secedit` omite; la cuenta exportada por su nombre) |
| `test_pwsh_el_fichero_de_claves`, `…_la_clave_pegada`, `…_la_huella`, `…_las_ip`, `…_el_resto` (pwsh) | Como en el borrador (las ocho claves malas, la huella contra Python, las IP buenas y malas, `Resto-De` sin huecos ni solapes) y **`Origen-Valido`** con los 12 casos de `pruebas-final/probar-origen.ps1` |
| `test_proteger` | `proteger.ps1`: `$EscribeBms` es exactamente `docker\estado` y `docker\secretos\correo`; si existe `docker/ciclo.ps1` (paso 15), cada literal `Join-Path $PSScriptRoot "<x>"` de `ciclo.ps1` y de las funciones de `comun.ps1` que llama (`Tomar-Cerrojo`, `Pausar-Automatico`, el registro del ciclo) empieza por `estado` o por `secretos\correo` (así, si el paso 15 escribe en otro sitio, la prueba falla y se añade a `$EscribeBms`); por este orden: comprobaciones < `Read-Host "Seguir?` < `-Verb RunAs` < `/setowner` < `/inheritance:r` < `/reset` < el `/grant` de `M`; en `/inheritance:r` exactamente SYSTEM `F`, Administradores `F`, `$Dueno` `M` y «bms» `RX`; para si el usuario es administrador o es quien lo abre; sin Docker |
| `test_los_ps1_de_docker_son_los_que_son` (en `test_entorno_local.py`) | Los `.ps1` de `docker/` son `SCRIPTS` + `comun` + `mac` + `proteger` (+ los del paso 18) |
| `test_mac_command_*` | `mac/*.command` existen, modo `100755`, `.gitattributes` con `mac/*.command text eol=lf`, sin `\r`, ASCII, `#!/bin/bash`, `export PATH=/usr/bin:/bin:/usr/sbin:/sbin`; `bash -n` y `bash --posix -n`; sin construcciones de bash 4 (fuera de comentarios); cada herramienta por su variable con ruta completa; **`pgrep` siempre con `-U "$YO"`**; `LSOF=/usr/sbin/lsof`; en `abrir-bms`, `soltar` justo antes de `"$SSH" -F` y `reservar` justo después de `wait "$PID_SSH"`; el `ssh_config` del heredoc con las líneas de §3.4 y ninguna de `StrictHostKeyChecking no|accept-new|off`, `GatewayPorts yes`, `RemoteForward`, `DynamicForward`, `ForwardAgent yes`, `ProxyCommand`, `LocalCommand`, `0.0.0.0`, `localhost`; `ssh` siempre con `-F` y `-N`; ni `sudo`, ni `xattr -r`/`-c`, ni `curl … \| bash`; `rm -rf` solo de `"$DIR"` en `--borrar`; en `preparar`, la frase vacía (`-y -P ""`) y el `es_si` de la huella antes de `mv … "$CONOCIDOS"`, y el `ln -sfn` comprobado |
| `test_abrir_bms_contra_programas_falsos` (bash) | Copia `abrir-bms.command` cambiando solo las líneas `export PATH=`, `SSH=`, `SSH_ADD=`, `NC=`, `CURL=`, `OPEN=`, `PGREP=` y `LSOF=` (el script no tiene ganchos de prueba), con `HOME` temporal y un `sleep` que acorta las esperas: los 10 casos de `pruebas-final/falso/probar-abrir.sh` (todo bien y vuelve tras un corte sin reabrir el navegador, con la reserva entre medias; el puerto ocupado al empezar; clave quitada; huella cambiada; alguien coge el puerto al cortarse; ya abierto con `lsof` que lo confirma; un `ssh` nuestro que no escucha con otro en el puerto; una reserva huérfana; la red no llega; alguien se cuela entre soltar y `ssh`). **Ejecutados aquí** |
| `test_preparar_contra_programas_falsos` (bash) | Igual con `preparar.command` desde una "memoria" temporal y `~/.bms-tunel` ya con clave y huella: los 5 casos de `pruebas-final/falso/probar-preparar.sh` (funciona y deja `BMS.command`, la `.pub` en la memoria y las copias; `ssh` muere → el mensaje de red; vivo sin escuchar → «tarda»; «Permission denied» → `-AnadirClave`; el Escritorio no deja → lo dice y da la otra forma). **Ejecutados aquí** |
| `test_sshd_de_verdad` (opcional, `BMS_PROBAR_SSHD=1` con `sshd`/`ssh` en el `PATH`) | Genera la configuración con `pwsh`, cambia `__PROGRAMDATA__/ssh/` por una carpeta **bajo `$HOME`** con `chmod 700` (bajo `/tmp`, `StrictModes` la rechaza: probado, F9; si algún antecesor no es seguro, se salta diciéndolo), `Port 22` por uno libre (+ `ListenAddress 127.0.0.1`), `bms-tunel` por el usuario de la prueba y `AllowUsers …@IP` por `…@127.0.0.1`; necesita el usuario `sshd` de la separación de privilegios (si no está, se salta). Comprueba F1-F8 de `pruebas-final/dentro.sh` y los casos de `pruebas-seg/`. Prueba la semántica de OpenSSH, no la de Windows (§5.2). **Corrido aquí a mano** con `unshare -m` (el `dentro.sh`) |

En `tests/test_instalacion_nativa.py`: `test_ningun_script_usa_docker_ni_ejecuta_texto_ni_baja_sin_hash`
(`:1148-1150`) y `test_pwsh_cada_script_pasa_el_analizador` (`:2375`) aceptan `mac.ps1` en
`windows/*.ps1` con la excepción con nombre de `FromBase64String`; el pin de `Poner-Permisos`
(`:1756`, `foreach ($hijo in @("app", "lib", "runtime", "windows"))`) pasa a incluir `"mac"`; pines
nuevos de 15b.3 (`instalar.ps1` copia `mac\*` a `<Raiz>\mac`; `desinstalar.ps1` para si existe
`HKLM:\SOFTWARE\bms-agent\TunelMac` y borra `<Raiz>\mac`; la línea de `comprobar.ps1`).

**Docs** (paso 17): `docs/entorno-local.md` tiene «Usarlo desde un Mac» con `-CopiarParaElMac`,
`bash `, `preparar.command`, `-Instalar`, `BMS.command`, `http://127.0.0.1:8765/app`, «Salir» y la
persona del Mac; y `proteger.bat` donde el paso 18 explica el usuario «bms».

### 5.2 La lista de comprobación en Windows 11 y en macOS reales (para §7.4 del diseño del paso 18)

| Qué | Aquí (Linux) | Solo en el mini PC / en el Mac |
| --- | --- | --- |
| `mac.ps1` en Windows PowerShell 5.1 | Pines y `pwsh` | `mac.bat -Instalar` en un Windows 11 Pro **sin** la capacidad y en uno **con** ella (y con un `sshd_config` cambiado: para; con `-SustituirConfiguracion`: sigue); dos veces seguidas; la ventana de administrador espera a Intro; desde un PowerShell de 32 bits, para |
| `mac.bat` sin `powershell` de la carpeta | Pin del `.bat` | Un `powershell.cmd` que escriba un fichero, puesto en `docker\` (como administrador, para probar): `.\mac.bat -Estado` no lo ejecuta |
| La carpeta protegida | Pines de `proteger.ps1` | `proteger.bat -Usuario bms` en una carpeta recién puesta en `C:\bms-agent`: `icacls` da solo SYSTEM, Administradores, el dueño `M` y «bms» `RX`, y `M` de «bms» en `docker\estado` y `docker\secretos\correo`; con la sesión de «bms», el ciclo del paso 18 corre y escribe en `docker\estado`; `correo-certificado.bat` escribe el `.pem`; el dueño abre `persona.bat`, `iniciar.bat`, `mac.bat` sin elevar; «bms» **no** puede crear un fichero en `docker\` ni cambiar `persona.ps1`; repetirlo no cambia nada |
| Quién puede cambiar `mac.ps1` y `mac\` | Pines | Pasa con la carpeta protegida, en `C:\Users\<dueño>\…` y en `C:\BMS\windows`; **para** en una carpeta de `C:\` sin proteger, en una clonada por «bms», dentro de OneDrive, y si «bms» es dueño de `mac\preparar.command`; lo mismo en un Windows en neerlandés |
| La nativa con «bms» de usuario de la instalación | — | El dueño no abre `C:\BMS\windows` sin elevar; desde **Terminal (Administrador)**, `& C:\BMS\windows\mac.bat -CopiarParaElMac E:\`, `-Instalar` y `-Estado` funcionan; `instalar.bat` deja `C:\BMS\mac` con los tres ficheros en LF |
| La clave del Mac sin arrastrar | Pines | `-Instalar` encuentra `E:\bms-mac\bms-mac-oficina.pub` y saca el nombre; con dos memorias o ninguna, pide la ruta; escribir la ruta o pegar la línea funciona; nada pide arrastrar a la ventana de administrador |
| sshd acepta la configuración | Texto exacto y sshd 9.6 de verdad | `sshd.exe -t`; `sshd.exe -T -C user=bms-tunel,host=mac,addr=<IP>` da lo de §2.3 y su formato; para `user=otra-cuenta`, `authorizedkeysfile none` (o nada, con ≥ 10.3); que `AllowStreamLocalForwarding`, `X11Forwarding` y `PermitTunnel` no rompen el arranque del sshd que traiga; versión de `sshd.exe` y si su acumulado trae los arreglos de CVE-2025-26466 y de octubre de 2026 |
| `C:\ProgramData\ssh` | Pines | `icacls C:\ProgramData` (si un usuario estándar puede crear carpetas); con `C:\ProgramData\ssh` creada **antes** por «bms» (sin la capacidad): `-Instalar` la ve, la aparta con `si` y el servicio la rehace con su SDDL (`icacls` da dueño Administradores); en una instalación limpia, `Carpeta-Ssh-Segura` no da pegas (las claves privadas del equipo, solo SYSTEM y Administradores) |
| El túnel de punta a punta | sshd 9.6 de verdad | Con la sesión de «bms» **bloqueada**: desde el Mac, `abrir-bms` abre la app y se entra con el token de la persona del Mac. **El cruce de sesiones** (sesión 0 → `com.docker.backend.exe` en la de «bms»; y en la nativa, a la consola) |
| Lo que el túnel no deja | sshd 9.6 de verdad | Desde el Mac: `-L 127.0.0.1:9000:127.0.0.1:22` (y `:2375`, `:3389`, `:445`) → «administratively prohibited»; `-L` a `\\.\pipe\docker_engine` → rechazado; `-R 9000:127.0.0.1:22` falla; sin `-N` no da consola ni ejecuta nada; `sftp` falla; contraseña → «Permission denied (publickey)»; otra clave → denegado; la clave del Mac A desde la IP del Mac B → denegado |
| La cuenta | Pines | Tras `-Instalar`: `secedit /export /areas USER_RIGHTS` tiene el SID de `bms-tunel` en los cuatro «Denegar…» y **ningún otro derecho ha cambiado** (comparar con un export de antes); el S4U de sshd sigue funcionando y crea su perfil; no sale en la pantalla de inicio; `runas /user:bms-tunel cmd` (con una contraseña puesta a mano, solo para probar) → «no se ha concedido el tipo de inicio de sesión»; tras `-Quitar`, los cuatro sin el SID; `Grupos-De-La-Cuenta` con un grupo local que tenga un miembro huérfano no falla |
| Los datos, para la cuenta del túnel | Pines | `-Instalar` para si la carpeta del proyecto hereda «Usuarios autenticados» (sin proteger) y sigue tras `proteger.bat`; `-Estado` lo dice en rojo si se le da a mano lectura a Usuarios en `docker\secretos` |
| El fichero de claves | Pines | sshd lo lee con permisos solo de SYSTEM y Administradores; **con escritura para Usuarios** (`icacls … /grant *S-1-5-32-545:W`, a mano): «Bad permissions. Try removing permissions for user: BUILTIN\Users…» y «Authentication refused.» en OpenSSH/Operational y el Mac no entra; `mac.bat -Instalar` lo arregla. (Con escritura para `bms-tunel` sshd lo acepta: es el propio usuario) |
| El cortafuegos | Pines y `Resto-De` | Con la red marcada como **pública** y como **privada**, el Mac llega y nada más cambia (la categoría no se toca); desde otro equipo de la red, el 22 no contesta; encendiendo a mano `OpenSSH-Server-In-TCP`, otro equipo sigue sin llegar y `-Estado` avisa; con «bloquear todas las conexiones entrantes» en el perfil activo, `-Estado` avisa |
| Quién más llega al 22 | — | Para saberlo, no para aprobar: desde `salida` (`docker compose exec salida python -c "import socket;socket.create_connection(('host.docker.internal',22),3)"`) y desde un proceso de la nativa (`Test-NetConnection 127.0.0.1 -Port 22`): se espera que conecten (§1.2); el registro de sshd los rechaza tras el intercambio de claves |
| Revocar | Pines del orden | `-QuitarClave` con un túnel abierto: `Get-CimInstance Win32_Process -Filter "Name LIKE 'sshd%'"` y `Get-NetTCPConnection -LocalPort 22 -State Established` quedan sin ese túnel en segundos; `abrir-bms` para con «no acepta la clave» y pide cerrar la pestaña. Con un sshd ≥ 9.8 (cuando llegue, o el MSI de GitHub en un equipo de pruebas), lo mismo con `sshd-session.exe`. Si `taskkill` no puede, `-QuitarClave` lo dice en rojo. Que `Stop-Service sshd` corte o no las sesiones, apuntarlo. `-Apagar`: sshd parado, inicio deshabilitado, el 22 cerrado, ningún proceso `sshd*`; `-Encender` lo devuelve |
| Reinicio de noche | — | Tras el reinicio: sshd arriba solo; el Mac (con la ventana abierta) se reconecta cuando vuelve la sesión de «bms», y mientras tanto `nc -z 127.0.0.1 8765` desde otra cuenta del Mac ve el puerto ocupado (la reserva) |
| `-Quitar` | Pines | Deja capacidad, servicio, reglas, cuenta, perfil, negaciones, `sshd_config`, `UserList` y `HKLM\SOFTWARE\bms-agent\TunelMac` como antes, en los dos casos; qué hace `Remove-WindowsCapability` con la regla de Microsoft |
| `-Estado` | — | El nombre del registro `OpenSSH/Operational` y el texto de «Accepted publickey … ED25519 SHA256:…»; `Get-HotFix` da la fecha del último acumulado (si no, otra fuente); `sshd_config_default` existe y `Tipo-De-Config` da "fabrica" recién instalado |
| La nativa sin el túnel quitado | Pin | `desinstalar.bat` con el túnel instalado para y pide `mac.bat -Quitar` antes |
| macOS: versión | — | `/usr/bin/ssh -V` (macOS 12 o más); acepta `UseKeychain`, `HostKeyAlias`, `ExitOnForwardFailure` con `-F`; `/usr/sbin/lsof`, `/usr/bin/nc -lk 127.0.0.1 8765` y `pgrep -U` existen y se comportan como en §3.5 |
| macOS: abrir la primera vez | `bash -n` | `bash preparar.command` desde una memoria exFAT: macOS pregunta por el volumen extraíble y por el Escritorio; con «No permitir», el mensaje; con «Permitir», sin avisos de Gatekeeper; `xattr -l ~/.bms-tunel/abrir-bms.command` sin cuarentena; doble clic en `BMS.command` abre Terminal y lo ejecuta; con el Escritorio en iCloud, el enlace funciona |
| macOS: la memoria | — | Una memoria formateada en el Mac (APFS) no se ve en Windows; una exFAT sí, con `bms-mac\bms-mac-oficina.pub` (los `._*` que deja macOS no estorban) |
| macOS: Llavero | — | `preparar` pide la frase una vez; `abrir-bms` no la pide (tampoco tras reiniciar el Mac); `preparar --borrar` la quita |
| macOS: huella | — | La primera vez se compara; con la clave del mini PC cambiada, `abrir-bms` para con «NO sigas» y `preparar` avisa en grande |
| macOS: el puerto | Programas falsos | Con `nc -l 8765` en marcha, `abrir-bms` y `preparar` paran sin abrir nada. **Resultado esperado en macOS**: con otro programa en `0.0.0.0:8765`, `ssh` **sí** abre `127.0.0.1:8765` (semántica BSD) y lo que para es el `nc -z` previo. Desde **otra cuenta** del Mac, `nc -l 127.0.0.1 8765` falla mientras el túnel está abierto y mientras la reserva lo guarda, y funciona tras cerrar la ventana (lo que queda, §3.5). La reserva no deja la pestaña colgada para siempre al volver el túnel |
| macOS: cerrar y dormir | Programas falsos | Cerrar la ventana deja sin `ssh` ni `nc` (`pgrep -U $(id -u) -f bms-tunel` y `-f "nc -lk"` vacíos) y qué pregunta Terminal; dormir el Mac 10 minutos: al despertar, se reconecta solo |
| macOS: el navegador | — | Safari y Chrome, en un perfil sin extensiones: entrar, Procesar, copiar en el chat (contexto seguro), descargar un PDF; el navegador no ofrece guardar el token, o se le dice «Nunca»; ningún aviso de "red local" para `ssh` (TN3179) |
| macOS: la IP | — | Con la «Dirección Wi-Fi privada» en Fija, la IP reservada se mantiene tras reiniciar y actualizar macOS |

---

## 6. Documentación

### 6.1 `docs/entorno-local.md`: el apartado nuevo «Usarlo desde un Mac»

Va **antes de «Para quien mantiene el programa»** (que sigue siendo el último), con el número que toque
después de lo que añada el paso 18. En §1 (`:49-54`) la frase pasa a ser: «…desde otro ordenador de la
oficina o de casa no se llega, aunque esté en la misma red, **salvo un Mac al que hayas dado una clave**
(apartado N): su navegador la abre por un túnel cifrado como si estuviera en este ordenador, y nada
más». En §6 (Arrancar y parar), una fila: «Abrir la app desde el Mac | Doble clic en **BMS** del
Escritorio del Mac (apartado N)». En §12 (mantenimiento), un punto: «`.\mac.bat -Estado` si usas el
Mac». En §10 (si algo no va), las filas de la tabla de abajo. Y en §12.5 (versión nueva), tras «Pon la
carpeta nueva…»: «si usas el usuario «bms» de lo automático, **`.\proteger.bat -Usuario bms`** antes de
`iniciar.bat`».

El texto (para el dueño, en castellano):

> ## N. Usarlo desde un Mac (opcional)
>
> Puedes abrir la app desde un Mac de la oficina o de casa, **sin instalar nada del programa en el
> Mac**: todo sigue en el mini PC (los datos, la clave de la API, el correo, la lectura). El navegador
> del Mac solo ve la app del mini PC a través de un **túnel cifrado**, como si estuvieras sentado
> delante del mini PC. Lo que llega al Mac es lo que ves en pantalla y los PDF que descargues.
>
> Solo funciona **en la misma red que el mini PC** (la de la oficina o la de casa). Desde fuera, no.
>
> **Lo que necesitas**
>
> | | |
> | --- | --- |
> | **Mini PC** | Windows 11 Pro, con tu cuenta de administrador. Encendido, con el programa en marcha. Si usas el usuario «bms» para lo automático, la carpeta del proyecto **protegida** con `proteger.bat` (apartado del usuario «bms»). |
> | **Mac** | macOS 12 o más, con Safari, Chrome o Firefox al día. **FileVault** encendido. **Sin otras cuentas de usuario** y con la de **invitado apagada** (Ajustes del Sistema → Usuarios y grupos). |
> | **Router** | Poder **reservar una IP** para el mini PC y otra para el Mac. |
> | **Una memoria USB** | **Formateada en exFAT o FAT32** (como vienen de fábrica; una formateada en el Mac como «Mac OS Plus» o APFS no se lee en Windows). |
> | **Tiempo** | Media hora la primera vez. |
>
> **0. Las IP (una vez).** En el router, reserva una IP para el mini PC y otra para el Mac, y apúntalas
> (por ejemplo `192.168.1.10` y `192.168.1.23`). En el Mac: Ajustes del Sistema → Wi-Fi → **Detalles…**
> de tu red → **Dirección Wi-Fi privada: Fija** (o Desactivada). Si el mini PC va por cable, mejor.
>
> **1. En el mini PC: la carpeta para el Mac.** Conecta la memoria. En la carpeta `docker` del proyecto,
> abre una ventana de PowerShell (clic derecho en un hueco → **Abrir en Terminal**) y escribe (con la
> letra de tu memoria):
>
> ```powershell
> .\mac.bat -CopiarParaElMac E:\
> ```
>
> Comprueba que nadie más ha podido cambiar esos ficheros, los copia a `E:\bms-mac` y te enseña **la IP
> del mini PC**: apúntala. (En la instalación nativa con el usuario «bms»: abre **Terminal
> (Administrador)** y escribe `& C:\BMS\windows\mac.bat -CopiarParaElMac E:\`; lo mismo en los pasos
> siguientes, con `& C:\BMS\windows\mac.bat` en lugar de `.\mac.bat`.)
>
> **2. En el Mac, la primera parte.** Conecta la memoria al Mac. Abre **Terminal** (Aplicaciones →
> Utilidades). Escribe `bash ` (con un espacio detrás), **arrastra el fichero `preparar.command`** de la
> carpeta `bms-mac` de la memoria a la ventana y pulsa Intro. **Si macOS pregunta si Terminal puede
> acceder a los archivos de un volumen extraíble (o al Escritorio), di Permitir.** Te pide:
> - un nombre corto para el Mac (por ejemplo `mac-oficina`);
> - una **frase** para su clave, dos veces. Que no la uses para nada más. Se guarda en el Llavero del
>   Mac: no hace falta que la recuerdes.
>
> Te enseña **la IP de este Mac** y **la huella de su clave** (empieza por `SHA256:`), y deja en la
> memoria un fichero `bms-mac-oficina.pub`. Después te pregunta la IP del mini PC (la del paso 1). Como
> el mini PC aún no está preparado, dice que no contesta y termina. **Deja esa ventana abierta.**
>
> **3. En el mini PC: instalar.** Conecta la memoria al mini PC. En la misma ventana de PowerShell:
>
> ```powershell
> .\mac.bat -Instalar
> ```
>
> - «Hay una clave de un Mac en la memoria… ¿Añadirlo ahora?» → `si`. Escribe la **IP del Mac** que te
>   enseñó el Mac y pulsa Intro para usar la clave de la memoria. Te enseña la **huella de la clave del
>   Mac**: **compárala con la de la pantalla del Mac**. Si es igual, `si`.
> - Windows te pide permiso de administrador: di que sí. En la ventana nueva, «¿Seguir?» → `si`. Instala
>   el servidor SSH de Windows (unos minutos la primera vez).
> - Al final te enseña **la IP del mini PC** y **la huella del mini PC**. Deja esta ventana abierta.
>
> **4. En el Mac, la segunda parte.** En la ventana de Terminal escribe
> `bash ~/.bms-tunel/preparar.command` y pulsa Intro (ya no hace falta la memoria). Si te pregunta si la
> IP del mini PC sigue siendo la misma, pulsa Intro. Te enseña la huella del mini PC: **compárala con la
> de la pantalla del mini PC**; si es exactamente igual, `si`. Si no, no sigas y avisa a quien mantiene el
> programa. Luego prueba el túnel y deja en el **Escritorio** un icono **BMS**.
>
> **5. Tu token para el Mac.** En el mini PC, en la carpeta `docker`:
>
> ```powershell
> .\persona.bat -Nombre "Tu nombre Mac" -Rol administracion
> ```
>
> Es una persona aparte, solo para el Mac: si un día pierdes el Mac, cambias solo ese token, y en la app
> se ve qué se hizo desde el Mac. Guárdalo en tu gestor de claves. (Con `administracion` haces el
> trabajo de cada día; las personas y la política, desde el mini PC.)
>
> **Cada día**
>
> 1. Doble clic en **BMS** en el Escritorio del Mac. Se abre una ventana de Terminal y, en el navegador,
>    la app: **`http://127.0.0.1:8765/app`**.
> 2. Entras con **el token del Mac**.
> 3. **Deja abierta la ventana de Terminal** mientras uses la app. Al acabar, **primero «Salir» en la app
>    y luego cierra la ventana**, en ese orden.
>
> Si el Mac se duerme o el mini PC se reinicia, la ventana lo dice, guarda el sitio y vuelve a abrir el
> túnel sola; no uses la app hasta que ponga «Túnel abierto otra vez». Si la ventana para y te pide que
> cierres la pestaña de la app, hazlo y pulsa Intro.
>
> **Lo que tienes que saber**
>
> - Abre la app en un **perfil del navegador solo para ella, sin extensiones** (Safari → Ajustes →
>   Perfiles, o un perfil nuevo de Chrome): una extensión con permiso para todos los sitios podría leer tus
>   facturas y los IBAN.
> - **Que el navegador no guarde el token**: si te ofrece guardarlo, «Nunca». Un navegador que lo rellena
>   solo en `127.0.0.1:8765` se lo daría a cualquier programa que ocupara ese puerto.
> - La dirección es siempre `http://127.0.0.1:8765/app`, pero solo funciona con la ventana de BMS
>   abierta: no la dejes abierta en una pestaña sin la ventana. Si otro programa del Mac usa el puerto
>   8765, BMS lo dice y no abre nada: ciérralo o reinicia el Mac.
> - El mini PC tiene que estar encendido y con el programa en marcha (la sesión de «bms» iniciada).
> - Los **PDF que descargues se quedan en Descargas** del Mac: bórralos cuando ya no te hagan falta.
> - **Bloquea el Mac** cuando te levantes.
> - **Si pierdes el Mac o te lo roban**: en el mini PC, `.\mac.bat -QuitarClave` (deja de poder entrar en
>   el acto; si dice en rojo que queda un túnel, reinicia el mini PC) y un token nuevo para el Mac
>   (`.\persona.bat -Nombre "Tu nombre Mac" -Rol administracion`: el de antes deja de valer).
> - **Si no vas a usar el Mac en semanas**, o Windows lleva tiempo sin actualizarse: `.\mac.bat -Apagar`
>   (y `.\mac.bat -Encender` para volver).
> - **Otro Mac**: los pasos 1, 2 y 4 en ese Mac, en el mini PC `.\mac.bat -AnadirClave` en lugar de
>   `-Instalar`, y su propia persona (paso 5, con otro nombre). Cada Mac tiene su propia clave.
> - **Si cambia la IP del Mac**: `.\mac.bat -AnadirClave` con el mismo nombre, «¿con la misma clave?»
>   `si`, y la IP nueva. **Si cambia la del mini PC**: en el Mac, `bash ~/.bms-tunel/preparar.command` y
>   la IP nueva.
> - **Quitarlo todo**: en el mini PC, `.\mac.bat -Quitar`; en cada Mac,
>   `bash ~/.bms-tunel/preparar.command --borrar`.
> - **Para ver cómo está**: `.\mac.bat -Estado` en el mini PC (también en el mantenimiento del mes). Si
>   pone en **rojo** que Windows lleva más de un mes sin actualizarse, actualízalo o, hasta entonces,
>   `.\mac.bat -Apagar`.
>
> **Si algo no va**
>
> | Lo que ves | Qué hacer |
> | --- | --- |
> | «Otro programa de este Mac usa ya el puerto 8765» | Cierra ese programa o reinicia el Mac, y vuelve a abrir BMS. |
> | «En cuanto se ha cortado el túnel, otro programa de este Mac ha cogido el puerto 8765» | Cierra la pestaña de la app y pide en el mini PC un token nuevo para el Mac (`persona.bat`). Avisa a quien mantiene el programa. |
> | «El mini PC no acepta la clave de este Mac» | La clave se quitó, o la IP del Mac cambió: `.\mac.bat -Estado` en el mini PC y, si hace falta, `.\mac.bat -AnadirClave`. |
> | «No se ha podido abrir el túnel» | El mini PC está apagado o en otra red, o la IP del Mac no es la apuntada. `.\mac.bat -Estado`. |
> | «La identidad del mini PC NO es la que se fijó» | **No sigas.** Si has reinstalado algo en el mini PC, repite `preparar.command` y compara la huella; si no, avisa a quien mantiene el programa. |
> | «El túnel está abierto, pero la app del mini PC no contesta» | En el mini PC, la sesión de «bms» y Docker Desktop (`automatico.bat -Estado`). |
> | En el Mac, «Operation not permitted» | Ajustes del Sistema → Privacidad y seguridad → Archivos y carpetas → Terminal: deja que use los volúmenes extraíbles y el Escritorio. |
> | `mac.bat`: «Otra cuenta de este equipo puede cambiar lo que mac.bat ejecuta…» | La carpeta del proyecto no está protegida: `.\proteger.bat -Usuario bms` (con Docker) o `instalar.bat` (nativa). Si sigue, avisa a quien mantiene el programa. |
> | `mac.bat`: «C:\ProgramData\ssh no es de fiar» | `.\mac.bat -Instalar` (la aparta y la rehace; después, en cada Mac, `preparar` otra vez para comparar la huella nueva). |
> | `mac.bat`: «tiene cambios que no son de bms-agent» | El servidor SSH del mini PC ya se usa para otra cosa: habla con quien mantiene el programa antes de usar `-SustituirConfiguracion`. |
> | `mac.bat -QuitarClave`: en rojo, «queda un proceso de un túnel» | Reinicia el mini PC ahora. |

### 6.2 Lo demás

| Documento | Qué cambia |
| --- | --- |
| `docs/entorno-local.md` (lo del paso 18) | Donde se explica el usuario «bms» y el inicio de sesión automático: un paso **«La carpeta del proyecto, protegida»** con `.\proteger.bat -Usuario bms` (como administrador; una vez al poner la carpeta, por ejemplo en `C:\bms-agent`, y otra con cada versión nueva, antes de `iniciar.bat`), y qué hace en dos frases (§2.12) |
| `docs/instalacion-nativa.md` | §1 (`:49-51`): la misma salvedad del Mac. Un apartado corto «Usarlo desde un Mac»: «igual que en entorno-local.md, con `C:\BMS\windows\mac.bat` desde **Terminal (Administrador)** si instalaste con otro usuario». §11 (`:398-410`, el hueco): «el servidor SSH del túnel del Mac no reenvía a internet (solo al `127.0.0.1:8765`, y con la clave de un Mac), pero su parte previa a la clave la alcanza cualquier programa de este ordenador, también el lector: por eso Windows Update al día y `mac.bat -Apagar` si no usas el Mac». §16 (`:558-559`): sigue valiendo; «desde otro equipo de la red, el puerto 22 del mini PC tampoco contesta» |
| `docs/app-local.md` (`:59-60`) | «Solo se abre desde el propio ordenador» → «…o desde un Mac por el túnel del mini PC, que la app ve igual que el propio ordenador» |
| `README.md` (`:24`) | Añadir «y usarlo desde un Mac por un túnel cifrado» a la descripción de `entorno-local.md` |
| `docs/uso-v1.md` | En «El mantenimiento del mes» que añade el paso 18: `mac.bat -Estado` (si se usa el Mac): la fecha del último acumulado, los Mac de la lista, los rechazos |
| `docs/arquitectura.md` (`:236-239`) | «El navegador de un Mac de la misma red puede abrir la app por un túnel SSH al `127.0.0.1` del mini PC (`mac.bat`); la app no cambia y no se publica nada nuevo de la app» |
| `windows/LEEME.txt` | `mac.bat`: el túnel del Mac (opcional) |
| `docs/v1/paso-18/diseno.md` | §4.2: un párrafo «La carpeta del proyecto (Docker con «bms»)» con `proteger.bat` y `$EscribeBms`; §7.4: las filas de §5.2; §9: la fila 15b (§7 de aquí); §11: un punto 3b («`proteger.bat -Usuario bms`») y un punto 10 con las acciones de §8; §12 pregunta 4 (`:1915-1916`): «Contestada el 24-11-2026: la usará en el mini PC y desde un Mac de la misma red, por el túnel de `docs/v1/paso-18/diseno-mac.md`». Este documento se guarda como **`docs/v1/paso-18/diseno-mac.md`** |
| `docs/v1/registro.md` | Una subsección del paso 18 (abajo) |

### 6.3 La subsección del registro

```
### Paso 18b · el Mac por el mini PC (petición del dueño del 24-11-2026)

Lo que pidió: «que funcione en una mac pero se haga todo a traves de la pc mini, para mantener el
sandbox». Forma: el navegador del Mac, por un canal cifrado; solo la misma red; Windows 11 Pro.

| Pieza | Qué es |   ← docker/mac.ps1 = windows/mac.ps1 (+ .bat, PowerShell por ruta): capacidad
                     OpenSSH.Server, cuenta bms-tunel (sin grupos propios, los cuatro "Denegar" con
                     secedit), sshd_config de bms-agent (todo cerrado + Match que solo abre -L a
                     127.0.0.1:8765), claves con restrict/permitopen/from, C:\ProgramData\ssh de los
                     administradores, dos reglas en cualquier perfil (los Mac; el resto bloqueado), estado
                     en HKLM\SOFTWARE\bms-agent\TunelMac; docker/proteger.ps1 (+ .bat); mac/
                     preparar.command y abrir-bms.command; tests/test_tunel_mac.py
| Puertas | … |   ← la app no cambia (Host/Origin/127.0.0.1); solo clave ed25519 con frase; una por Mac y
                     una persona por Mac; solo desde la IP del Mac; ni consola, ni sftp, ni -R, ni otro
                     destino; huellas comparadas a ojo; nada pide arrastrar a una ventana de administrador;
                     mac.bat no corre si otra cuenta puede cambiarlo a él o a mac\; la carpeta del
                     proyecto protegida; el 8765 del Mac guardado mientras el túnel está cortado;
                     -Quitar deja el equipo como estaba; nada del programa en el Mac
| Cambios de comportamiento | … |   ← «desde otro ordenador no se llega» → salvo un Mac con su clave;
                                     un servidor SSH en el 22 (desde la red, solo los Mac)
| Desviaciones | … |   ← (las que haya al construir)
| Resultado | … |   ← pruebas aquí; lista de §5.2 pendiente en el mini PC y el Mac
```

---

## 7. Dónde entra en el plan de construcción

Va en el **flujo C, como paso 15b**, justo después del paso 15 (Docker) del plan del paso 18
(`docs/v1/paso-18/diseno.md` §9, `:1785`) y antes del 16 (e2e): `proteger.ps1` necesita saber qué
carpetas escribe «bms», y eso lo deja el 15. No depende del correo ni de la lectura automática. Se
verifica entero aquí, como los demás pasos; lo que solo se ve en Windows o en el Mac va a §5.2. **Al
construir, volver a anclar cada `fichero:línea`** (este documento lo está a `b685843`) y comprobar el
conjunto `SCRIPTS` de `tests/test_entorno_local.py:300-303`, que el paso 15 puede haber ampliado.

| # | Commit (forma de siempre) | Ficheros | Tamaño | Verificación aquí |
| --- | --- | --- | --- | --- |
| 15b.0 | `feat(v1-paso-18): proteger la carpeta del proyecto de docker` | `docker/proteger.ps1` (~150, anexo D), `docker/proteger.bat` (5), `tests/test_tunel_mac.py` (la parte de `proteger`, ~80), `tests/test_entorno_local.py` (~5: el conjunto de `docker/*.ps1`) | ~250 | `pytest tests/test_tunel_mac.py tests/test_entorno_local.py` con `pwsh` |
| 15b.1 | `test(v1-paso-18): las guardas del tunel del mac` + `feat(v1-paso-18): mac.bat, el tunel del mac en el mini pc` (juntos o seguidos) | `docker/mac.ps1` (~1000: el borrador con los anexos C), `docker/mac.bat` (5), `windows/mac.ps1` y `windows/mac.bat` (copias), `tests/test_tunel_mac.py` (la parte de Windows, ~300), `tests/test_instalacion_nativa.py` (~10) | ~2 300 | `pytest tests/test_tunel_mac.py tests/test_instalacion_nativa.py tests/test_entorno_local.py`; `cmp docker/mac.ps1 windows/mac.ps1` |
| 15b.2 | `feat(v1-paso-18): preparar y abrir-bms, el lado del mac` | `mac/preparar.command` (~300, anexo A), `mac/abrir-bms.command` (~175, anexo B), `mac/LEEME.txt`, `.gitattributes` (+2), `git update-index --chmod=+x mac/*.command`, `tests/test_tunel_mac.py` (la parte del Mac, ~170, con los programas falsos) | ~650 | `pytest tests/test_tunel_mac.py`; `bash -n`; `git ls-files -s mac` da `100755` |
| 15b.3 | `feat(v1-paso-18): la nativa lleva lo del mac y no lo deja suelto` | `windows/instalar.ps1` (copia `$Proyecto\mac\*` a `<Raiz>\mac` junto a `windows`, y `"mac"` en las listas de `Poner-Permisos` y de `Unblock-File`), `windows/desinstalar.ps1` (si existe `HKLM:\SOFTWARE\bms-agent\TunelMac`, para con «Primero: `C:\BMS\windows\mac.bat -Quitar`»; `"mac"` en la lista de carpetas que borra), `windows/comprobar.ps1` (la línea de §2.10), sus pines | ~40 | `pytest tests/test_instalacion_nativa.py` |
| 17 (con el resto) | `docs(v1-paso-18): usarlo desde un mac` | §6 entero y este documento como `docs/v1/paso-18/diseno-mac.md` | ~250 + este | Las pruebas de documentos del paso 17 y las de §5.1 sobre `entorno-local.md` |

Orden dentro de 15b.1: primero las funciones puras (`Texto-Config`, `Texto-Claves`,
`Clave-Publica-Valida`, `Huella-Sha256`, `Ip-Valida`, `Origen-Valido`, `Resto-De`, `Texto-Negaciones`,
`Diferencias-De-Derechos`, `Comprobar-Lo-Que-Se-Aplica` con su `sshd` falso) con sus pruebas de
`pwsh`; después `Aplicar` y las acciones con sus pines de orden; `-Estado` al final. Ningún fichero de
`src/`, `frontend/`, `docker-compose.yml` ni `Dockerfile` cambia (`git diff --stat` en la revisión).

Fuera del repositorio, después del paso 17: las acciones del dueño (§8) y la lista de §5.2.

---

## 8. Lo que solo puede hacer o decidir el dueño

1. **El router**: reservar una IP para el mini PC (mejor por cable) y otra para cada Mac. Si no se puede,
   la reserva es escribir `red` como IP del Mac (cualquier equipo de la red llega al servidor SSH, aunque
   sin la clave no entra).
2. **El Mac**: la «Dirección Wi-Fi privada» en **Fija**; **FileVault**; bloqueo de pantalla; macOS al
   día; **sin otras cuentas de usuario y sin invitado**; un **perfil del navegador solo para la app**,
   sin extensiones; que el navegador **no guarde el token**.
3. **La carpeta del proyecto** (Docker con «bms»): `proteger.bat -Usuario bms` como administrador al
   ponerla y con cada versión nueva.
4. **Windows Update al día** en el mini PC (ya lo pide el paso 18): el servidor SSH se parchea con él.
   Si un mes no puede, `mac.bat -Apagar` hasta hacerlo.
5. **`mac.bat -CopiarParaElMac`, `-Instalar`** desde su cuenta, y aceptar el permiso de Windows.
6. **Comparar las huellas** en las dos pantallas: es lo único que no puede hacer nadie por él.
7. **Un nombre por Mac**, una clave por Mac y **una persona por Mac** (`persona.bat`, rol
   `administracion` salvo que necesite más); la frase de cada clave, que no use para nada más.
8. **Al acabar, «Salir» en la app y luego cerrar la ventana de BMS.**
9. **Si pierde un Mac**: `mac.bat -QuitarClave` y un token nuevo para la persona de ese Mac (si
   `-QuitarClave` lo pide en rojo, reiniciar el mini PC). **Si no lo usa en semanas**: `mac.bat -Apagar`.
10. **Los PDF descargados** en el Mac: borrarlos cuando no hagan falta.
11. **El mantenimiento del mes**: `mac.bat -Estado` (nada en rojo).
12. **La lista de §5.2**, una vez, con quien mantiene el programa.
13. **Decidir** (§9.2): si quiere que la clave caduque sola cada año; si algún día quiere entrar desde
    fuera (sería otro diseño).

---

## 9. Riesgos y preguntas abiertas

### 9.1 Riesgos

| Riesgo | Qué se hace | Queda |
| --- | --- | --- |
| **El cruce de sesiones** (sshd en la sesión 0 no llegara al puerto de Docker Desktop en la sesión de «bms») | Todo apunta a que llega (pila TCP del equipo) y §4.2 del paso 18 depende de lo mismo | **[comprobar en Windows 11]** el primer día |
| **Un fallo de sshd previo a la autenticación** | Desde la red solo las IP de los Mac; "resto" bloquea a los demás; `MaxStartups`, `LoginGraceTime`; Windows Update; `-Estado` en rojo a los 35 días; `-Apagar` | **Cualquier programa del mini PC y los contenedores con red llegan a esa parte por el bucle local** (§1.2): un programa ya comprometido tiene un servicio más con el que intentarlo. Lo que tarde el parche |
| **Un programa del mini PC agota `MaxStartups`** | `PerSourcePenalties` (≥ 9.8) castiga a `127.0.0.1`, no al Mac | El túnel no abre mientras dure (un programa ya comprometido) |
| **La versión del sshd de Windows** no entiende una línea, o imprime `-T` distinto | `sshd -t` antes y `sshd -T` después (que ya acepta la forma de ≥ 10.3); si no, para con el servidor parado | Ajustar la línea al construir **[comprobar en Windows 11]** |
| **Windows Update trae un sshd ≥ 9.8** (procesos `sshd-session.exe`) | `Parar-Tuneles` mata por nombre `sshd%` y ruta, con `taskkill /F`, y vuelve a mirar | Si Windows no deja cortar uno, el aviso en rojo y el reinicio |
| **Windows Update vuelve a encender o a crear `OpenSSH-Server-In-TCP`** | La regla "resto" lo tapa; `-Estado` avisa; `-Instalar` la vuelve a apagar | — |
| **Cambia la IP del Mac o del mini PC** | Reservas; mensajes; `-AnadirClave` con el mismo nombre; `preparar` con la IP nueva | Falla cerrado |
| **El dueño acepta una huella sin mirarla** | Las dos pantallas, `si`, aviso en grande si cambia | La primera vez, un atacante activo en ese momento |
| **Otra cuenta puede cambiar `mac.ps1`, `mac\` o los scripts del dueño** (la de «bms») | `proteger.bat`; `Quien-Mas-Puede-Cambiar` se niega a elevar y a copiar al Mac | La confianza de partida: la carpeta que entrega quien mantiene el programa, protegida justo al ponerla (unos minutos sin proteger con cada versión nueva, con lo automático en pausa) |
| **`C:\ProgramData\ssh` creada antes por otra cuenta** | `Carpeta-Ssh-Segura`; se aparta y se rehace | — |
| **La pestaña de la app con el token, con el 8765 del Mac libre** | Reserva mientras el túnel está cortado; `lsof` al dar el túnel por abierto; si para con la app abierta, espera a que se cierre la pestaña; la guía: «Salir» antes de cerrar, Mac sin otras cuentas | Cerrar la ventana con la pestaña abierta en un Mac con otras cuentas. Cortarlo del todo pide cambiar la app |
| **El token en el Mac** | Persona aparte para el Mac (rol `administracion`); el navegador no lo guarda; perfil sin extensiones | Lo que el dueño guarde en su gestor de claves (solo sirve con la clave del Mac y en la red de la oficina, o en el propio mini PC) |
| **Los PDF en el Mac** | Aceptado; guía: Descargas, FileVault, borrarlos | Lo que el dueño mueva a iCloud o Time Machine |
| **`secedit` deja algo distinto de lo pedido** | Se comprueba con un segundo export y, si otro derecho cambió, se vuelve a aplicar el primero y para | **[comprobar en Windows 11]** |
| **Más software que mantener** | sshd con Windows Update; `ssh` con macOS | — |

### 9.2 Preguntas abiertas (solo decisiones del dueño)

1. **¿Caducidad de la clave?** Con `expiry-time="AAAAMMDD"` en la línea, cada clave dejaría de valer a
   los 12 meses y habría que repetir `preparar --borrar`, `preparar` y `-AnadirClave`. Más seguro si un
   Mac se pierde sin que nadie se entere; más trabajo. El diseño no la pone.
2. **¿El rol de la persona del Mac?** El diseño pone `administracion` (el trabajo diario). Si el dueño
   necesita gestionar personas o la política desde el Mac, `administrador` (y perder el Mac pesa más).
3. **¿Entrar desde fuera algún día?** Sería otro diseño (Tailscale, WireGuard); este no lo impide.
4. **¿Un Mac con macOS 11 o anterior, o un Mac con otras cuentas que no se pueden quitar?** El diseño
   pide macOS 12 y un Mac sin otras cuentas; si no es así, se adapta `preparar` o se acepta lo de §3.5.
5. **¿Ya usa el servidor SSH del mini PC para otra cosa?** Este diseño no lo combina: `-Instalar` para y
   lo dice.

Lo que depende de probarlo está en §5.2; lo más importante, en el resumen de la entrega.

---

## 10. Revisión

Dos revisiones adversarias del borrador anterior: **seguridad** (8 mayores, 3 menores; probó con un
OpenSSH 9.6 de verdad) y **viabilidad** (1 bloqueante, 5 mayores, 9 menores). Cada hallazgo se ha
comprobado aquí contra la fuente o con una prueba antes de aceptarlo. Ninguno reabre la decisión del
túnel SSH. Varios coinciden entre las dos (se dice en cada fila).

### 10.1 Seguridad

| # | Hallazgo | Comprobado | Veredicto y arreglo |
| --- | --- | --- | --- |
| S-M1 | El token se puede cazar en el Mac cogiendo el 8765 en los huecos del túnel (la pestaña de Procesar consulta cada 2 s con el token); la rama «ya abierto» usaba `pgrep -f` sin `-U` y no miraba quién escucha | Sí: `processing-workspace.tsx:91-101` (`()=>undefined` y `setTimeout`) y `api.ts:389-400` (la cabecera en cada petición); el borrador dormía con el puerto libre | **Aceptado.** `abrir-bms` guarda el puerto con un `nc -lk 127.0.0.1 8765` propio desde que se corta hasta justo antes de relanzar `ssh` (§3.5 paso 7; probado con programas falsos: «reserva» entre `ssh-fin` y el siguiente `ssh-inicio`); `pgrep -U "$(id -u)"` y `lsof -p <pid> … -sTCP:LISTEN` para dar el túnel por abierto (pasos 2 y 6); si para por un error con la app abierta, guarda el puerto hasta que el dueño cierra la pestaña; reserva huérfana, fuera al empezar. Guía: «Salir» antes de cerrar, sin favoritos, Mac sin otras cuentas ni invitado. Lo que queda (cerrar la ventana con la pestaña abierta en un Mac con otras cuentas), dicho tal cual en §3.5 y §9.1 |
| S-M2 = V-M4 | «Sin ningún grupo» no existe: Usuarios contiene a Usuarios autenticados; `bms-tunel` lee lo que lean esos grupos (también `docker\secretos` heredando de `C:\`); `Asegurar-Cuenta` y `-Estado` se saltaban sin avisar un grupo que no podían listar | Sí: `understand-security-identifiers.md:214` y `:187`; el S4U es de red (`win32_usertoken_utils.c:230`), así que negar los otros cuatro inicios no lo rompe | **Aceptado.** §2.2 y §4.1 corregidos («sin grupos propios; está en Usuarios»). Obligatorio: `SeDenyInteractiveLogonRight`, `SeDenyRemoteInteractiveLogonRight`, `SeDenyBatchLogonRight` y `SeDenyServiceLogonRight` por SID con `secedit`, comprobando después que nada más cambió (`Negar-Inicios`, probado en su parte pura); nunca el acceso por red. `Lectores-De-Datos` en `-Instalar` (para) y `-Estado` (mal) para Todos, Usuarios autenticados, Usuarios, Red, Cuenta local y la cuenta, sobre el proyecto, sus secretos, el estado, el buzón y los datos de la nativa; y `proteger.bat` hace que nadie de esos lea (§2.12). Grupos por ADSI y por SID; si no se pueden mirar, error. La prueba engañosa de §5.2 (`Get-LocalGroupMember -SID S-1-5-32-545`) se quita |
| S-M3 = V-M3 | `-QuitarClave` y `-Apagar` no cortan los túneles con OpenSSH ≥ 9.8 (`sshd-session.exe`, `sshd-auth.exe`); `Stop-Process` puede dar «acceso denegado» y se tragaba; el script decía que los había cortado | Sí: `openssh/win-src/pathnames.h:50-61` y `fuentes/src-win/servconf.c:414-425`; el borrador mataba solo `Get-Process -Name sshd` con `SilentlyContinue` | **Aceptado.** `Procesos-De-Sshd` (`Win32_Process`, `Name LIKE 'sshd%'`, ruta de `System32\OpenSSH` o sin ruta visible), `taskkill /F /PID` por su ruta, se vuelve a mirar 10 s y, si queda alguno, aviso en rojo «reinicia el equipo» (§2.8 paso 1). `-Estado` dice los túneles abiertos y cuántos procesos hay. Filas en §5.2 (con un sshd ≥ 9.8, y si `Stop-Service` los corta) |
| S-M4 | Si «bms» crea antes `C:\ProgramData\ssh`, sshd (SYSTEM) usa una carpeta suya: de «bms» a administrador | Sí en el código: `wmain_sshd.c:138` crea con su SDDL solo si no existe; `misc.c:1422-1450` y `w32-sshfileperm.c:190-196`, `:224-226` solo apuntan «Bad owner». Que un usuario estándar pueda crearla, **[comprobar en Windows 11]** (es lo que dice el ACL por defecto de `ProgramData`) | **Aceptado.** `Carpeta-Ssh-Segura` (dueño, escritura de otros, enlaces, lectura de las claves privadas del equipo) antes y después del primer arranque, en cada `Aplicar` y en `-Estado`; con pegas en `-Instalar`, `Apartar-Carpeta-Ssh` (se aparta entera, `takeown`, y el servicio la rehace) (§2.8.1). Fila en §5.2 |
| S-M5 = V-m6 | `mac.bat` llamaba a `powershell` sin ruta (cmd busca primero en la carpeta actual); la comprobación no miraba crear ficheros en la carpeta ni el dueño de los objetos | Sí: `borrador/docker/mac.bat:3`; `fuentes-seg/nf-processenv-needcurrentdirectoryforexepathw.md:76-80`; `borrador/docker/mac.ps1:272-291` (sin `CreateFiles`/`AppendData` en la carpeta, sin `Owner`); `understand-security-identifiers.md:143` | **Aceptado.** `"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"` en `mac.bat` y `proteger.bat`; `Quien-Mas-Puede-Cambiar` mira el dueño (`GetOwner`), crear ficheros y carpetas en las carpetas propias, y enlaces; `icacls`, `taskkill`, `secedit` y `takeown` por ruta completa (§2.1, §2.11, anexo C). La copia «solo de administradores» se descarta (§0.1): no arregla la primera vez; la carpeta protegida sí. Los otros `.bat` del repositorio también llaman a `powershell` sin ruta: con la carpeta protegida nadie más puede crear nada en `docker\` ni en `windows\`; alinearlos sería un cambio aparte, fuera de este paso |
| S-M6 | Los `mac/*.command` iban del mini PC al Mac sin ninguna comprobación | Sí: el borrador solo protegía `mac.ps1` y `mac.bat` (`mac.ps1:648`) | **Aceptado.** `mac\` y sus tres ficheros entran en `Quien-Mas-Puede-Cambiar`, y lo que va al Mac sale **solo** por `mac.bat -CopiarParaElMac`, después de esa comprobación (§2.13, §3.2); enseña el SHA-256 corto de cada fichero; `-Estado` también. En la nativa, `instalar.ps1` copia `mac\` a `<Raiz>\mac`, protegida como el resto (15b.3) |
| S-M7 | La parte de sshd previa a la autenticación la alcanzan los procesos del propio equipo y los contenedores con red; el diseño decía lo contrario | Sí: sshd en `0.0.0.0:22`, el tráfico local no lo filtra el cortafuegos (`instalacion-nativa.md:404-406`), `salida` en `red_exterior` (`docker-compose.yml:55-80`) y `host.docker.internal` (`faqs_general.md:41-43`). Matiz comprobado: el análisis previo a la clave corre en un proceso con una cuenta virtual sin privilegios (`win32_usertoken_utils.c:610-700`), vigilado por uno de SYSTEM | **Aceptado en parte.** Corregido en §0, §1.2 (nuevo), §2.10, §4.1, §4.4 y §9.1; `-Estado` en **rojo** con el acumulado de más de 35 días; filas en §5.2 desde `salida` y desde un proceso de la nativa. **Rechazado**: sshd apagado por defecto (el Mac no podría encenderlo sin ir al mini PC; `-Apagar` existe) y `ListenAddress` (no quita el alcance local y rompe el arranque si la IP no está aún) (§0.1). Tampoco se pone `!<IP del mini PC>` en `from=` con la reserva `red`: la clave sigue haciendo falta y la negación quedaría vieja justo en el caso sin reservas |
| S-M8 | Marcar la red como privada abre el mini PC más allá del 22 | Sí: `New-NetFirewallRule.md:735-737`, `Set-NetConnectionProfile.md:214`; el borrador lo ofrecía (`mac.ps1:726-733`) | **Aceptado, con la alternativa que proponía**: la categoría no se toca nunca; las dos reglas en `-Profile Any`, acotadas a `sshd.exe`, el 22 y las IP de los Mac (§2.5). Se pierde el «falla cerrado con la red pública», que no vale lo que cuesta. `-Estado` enseña la categoría y avisa si el perfil activo bloquea todas las entradas. Se quita el paso de la guía |
| S-m1 | `AllowStreamLocalForwarding` existe en Win32-OpenSSH y queda en `yes`; la prueba prohibía cerrarlo | Sí: `openssh/win-src/servconf.h:173`, `:198`, `:217`; y **probado**: con las tres líneas, `sshd -t` pasa, `-T` da `no`, y el `-L` a un socket Unix pasa a rechazarse por esa opción («refused streamlocal port forward», F6) | **Aceptado.** `AllowStreamLocalForwarding no`, `X11Forwarding no` y `PermitTunnel no` globales (§2.3); en lo esperado de `-T` (`no` o ausentes) y en el pin; fuera de la lista de prohibidos |
| S-m2 | El navegador de diario: extensiones; el token guardado y sincronizado | Sí (la guía no lo decía) | **Aceptado en parte.** Guía: un perfil del navegador solo para la app, sin extensiones; que el **navegador** no guarde el token (además, lo rellenaría en cualquier programa que ocupara `127.0.0.1:8765`). **No** se pide «nunca en el gestor de contraseñas»: el token hace falta cada vez que se entra (vive solo en memoria, `session.tsx:1-4`), la guía de siempre ya lo manda al gestor (`entorno-local.md` §5) y solo no sirve sin la clave del Mac y la red de la oficina; y es la persona del Mac, no la del dueño (S-m3) |
| S-m3 | El Mac usaba el token del dueño (administrador) | Sí | **Aceptado.** Una persona aparte para el Mac con rol `administracion` (M13, guía paso 5); perder el Mac revoca solo ese token y la auditoría lo separa (§4.1, §4.2). El rol es decisión del dueño (§9.2) |

### 10.2 Viabilidad

| # | Hallazgo | Comprobado | Veredicto y arreglo |
| --- | --- | --- | --- |
| V-B1 | `mac.bat` se negaba a correr en cualquier ubicación del proyecto compatible con el paso 18 Docker | Sí: «bms» ejecuta `<repo>\docker\ciclo.ps1` y escribe `docker\estado` (paso 18, `diseno.md:1021`, `:1059-1060`, `:1132`) y su Docker Desktop monta `docker\secretos\correo` (`:167-168`, `:454`); las tres ubicaciones fallan como dice | **Aceptado, con el arreglo 1 implementado aquí**: `docker\proteger.bat -Usuario bms` (15b.0, anexo D): dueño Administradores, sin herencia, el dueño `M`, «bms» `RX` y `M` solo en `docker\estado` y `docker\secretos\correo`, con su prueba (§2.12, §5.1). Es un arreglo del paso 18 (sin él «bms» puede cambiar `persona.ps1` y los demás scripts del dueño), por eso va también a §4.2 y §11 de su diseño (§6.2). La reserva de copiar a `Program Files` se descarta (§0.1) |
| V-M1 | Arrastrar el `.pub` a la ventana de administrador no funciona (UIPI) | Comportamiento conocido de Windows (no se puede probar aquí) | **Aceptado.** Nada pide arrastrar a la ventana de administrador: lo del Mac se pregunta antes de elevar (`Pedir-Mac` en `if (-not $Elevado)`), la clave la busca `Claves-En-Memorias` en `<memoria>\bms-mac` (donde la deja `preparar`), y a la ventana elevada solo pasan `-Nombre`, `-Ip`, `-Clave <base64>`, que allí se vuelven a validar (§2.13). En la nativa desde una Terminal de administrador, se pregunta en la misma ventana y la clave se encuentra igual. Pin y fila en §5.2 |
| V-M2 | `Comprobar-Lo-Que-Se-Aplica` fallaba siempre con un sshd basado en OpenSSH ≥ 10.3 (`authorizedkeysfile none` ya no se imprime) | Sí: `revision-fuentes/servconf-V_10_3_P1.c:538` (después de rellenar los valores por defecto, `:458`: la lista queda vacía, no vuelve a la de por defecto); `fuentes/src-win/servconf.c:466` y `:4256-4268`; el 9.6 de verdad sí imprime la línea (F3) | **Aceptado.** Para otra cuenta vale `none` o que falte la línea, y se exige además `allowtcpforwarding no` y `permitopen none` (§2.3, anexo C). Probado con `pwsh` y un `sshd` falso con las dos salidas y una mala (`probar.ps1`) |
| V-M3 | = S-M3 | | Ver S-M3 |
| V-M4 | = S-M2 (y que los secretos de Docker los leería `bms-tunel` con la herencia de `C:\`) | Sí: `entorno-local.md:104-107`, ningún `icacls` en `docker/*.ps1` | Ver S-M2 y V-B1: `proteger.bat` y `Lectores-De-Datos` |
| V-M5 | La prueba de `StrictModes` estaba al revés: Windows deja escribir al propio usuario | Sí: `w32-sshfileperm.c:61` y `:136-141` (se salta el ACE de `pw`), `auth2-pubkeyfile.c:479-483` | **Aceptado.** La prueba de §5.2 da escritura a **Usuarios** y espera «Bad permissions… / Authentication refused.»; el texto de §2.3 y §2.4 dice que frente a la cuenta del túnel protege la ACL, no `StrictModes` |
| V-m1 | `Get-LocalGroupMember` revienta con SID huérfanos y el error se tragaba | Conocido (PowerShell/PowerShell#2996); en el borrador, `catch { continue }` y `catch { $false }` | **Aceptado.** `Grupos-De-La-Cuenta` por ADSI y por SID; si lanza, error (`Fallar` en `-Instalar`, **mal** en `-Estado`) (§2.2, anexo C). En `proteger.ps1`, igual |
| V-m2 | TCC: Terminal pedirá permiso para la memoria y el Escritorio; el `ln` no se comprobaba | Sí en el borrador (`ln -sfn` sin comprobar y «Listo») | **Aceptado.** Guía: «di Permitir» y cómo arreglarlo si no; `preparar` comprueba el enlace y, si falla, lo dice y da `bash ~/.bms-tunel/abrir-bms.command` (probado con un `ln` que falla, caso E); el fallo al copiar desde la memoria dice lo de Permitir. Filas en §5.2 (también con el Escritorio en iCloud) |
| V-m3 | La memoria: formato y vuelta al Mac en el paso 4 | Sí | **Aceptado.** «Formateada en exFAT o FAT32» en «Lo que necesitas»; `preparar` se copia a `~/.bms-tunel` nada más empezar y el paso 4 es `bash ~/.bms-tunel/preparar.command`, sin la memoria |
| V-m4 | El resultado esperado de `ExitOnForwardFailure` no es el de macOS (BSD); el hueco inverso con el túnel abierto | De fuentes secundarias (no se puede probar aquí) | **Aceptado.** §3.6 y §5.2 dicen el resultado esperado en macOS (lo que para es el `nc -z`). El «hueco inverso» no lo es: con el túnel abierto, el tráfico a `127.0.0.1` va al `ssh` (más específico) y otra cuenta no puede coger la misma dirección y puerto **[comprobar en macOS]**; con el túnel cortado, la reserva (S-M1) |
| V-m5 | `test_sshd_de_verdad` no pasaría con el fichero de claves bajo `/tmp` | **Probado**: «Authentication refused: bad ownership or modes for directory» con una carpeta `1777` (F9) | **Aceptado.** La carpeta de la prueba bajo `$HOME` con `700`, y se salta diciéndolo si algún antecesor no es seguro (§5.1) |
| V-m6 | = S-M5 | | Ver S-M5 |
| V-m7 | En la nativa con «bms» de usuario de la instalación, el dueño no puede abrir `C:\BMS\windows` | Sí: `instalar.ps1:359-367` (solo `RX` al usuario de la instalación) | **Aceptado.** La guía de la nativa: **Terminal (Administrador)** y `& C:\BMS\windows\mac.bat …`; nunca «Continuar» en el Explorador (§2.1, §6.1). Como ahí todo corre elevado, la clave se encuentra en la memoria sin arrastrar |
| V-m8 | `preparar` decía «el túnel abre» cuando no había abierto | Sí en el borrador (`codigo=000` sin mirar si `ssh` seguía vivo) | **Aceptado.** Espera hasta 60 s a que **su** `ssh` escuche (`lsof`) o muera, y distingue muerto (mensaje de red con el error), vivo sin escuchar («tarda»), escuchando sin app («la app no contesta») (§3.3 paso 6; probado, casos A-D) |
| V-m9 | Las referencias `fichero:línea` eran de `0062d38` | Sí: la rama va por `b685843`; `SCRIPTS` de `test_entorno_local.py` está en `:300` | **Aceptado.** Todo este documento está anclado a `b685843`; §7 pide volver a anclar al construir y mirar si el paso 15 cambió `SCRIPTS` |

---

## Anexo A. `mac/preparar.command` (`bash -n` y `bash --posix -n` sin errores; ejecutado contra programas falsos en 5 casos)

```bash
#!/bin/bash
# bms-agent: prepara este Mac para abrir la app del mini PC por el tunel (paso 18b,
# docs/entorno-local.md "Usarlo desde un Mac"). Se puede repetir: hace lo que falte.
#
#   Como se abre: en Terminal, escribe "bash " (con el espacio), arrastra este fichero a la
#   ventana y pulsa Intro. (Asi no hace falta tocar Gatekeeper ni permisos.)
#
#   bash preparar.command            preparar, o seguir donde se quedo
#   bash preparar.command --borrar   quitar de este Mac la clave y todo lo del tunel
#
# Nada del programa corre en el Mac: ni la base, ni la clave de la API, ni el correo. Solo una
# clave SSH que abre ese tunel (al 127.0.0.1:8765 del mini PC) y nada mas.
# bash 3.2 de macOS: nada de arrays asociativos, ${v,,}, mapfile ni readarray.

set -u
umask 077
export PATH=/usr/bin:/bin:/usr/sbin:/sbin

DIR="$HOME/.bms-tunel"
CLAVE="$DIR/clave_ed25519"
CONFIG="$DIR/ssh_config"
CONOCIDOS="$DIR/known_hosts"
ERRORES="$DIR/ultimo-error.txt"
PUERTO=8765
ALIAS=bms-minipc
CUENTA=bms-tunel
SSH=/usr/bin/ssh
SSH_ADD=/usr/bin/ssh-add
SSH_KEYGEN=/usr/bin/ssh-keygen
SSH_KEYSCAN=/usr/bin/ssh-keyscan
NC=/usr/bin/nc
CURL=/usr/bin/curl
PGREP=/usr/bin/pgrep
LSOF=/usr/sbin/lsof
YO="$(id -u)"
AQUI="$(cd "$(dirname "$0")" && pwd)"

decir() { printf '%s\n' "$*"; }
titulo() { printf '\n== %s\n' "$*"; }
fallar() { printf '\n%s\n\n' "$*" >&2; exit 1; }
es_si() {
    case "$(printf '%s' "$1" | tr 'A-Z' 'a-z' | tr -d ' ')" in
        si|s|"s"$'\xc3\xad') return 0 ;;
        *) return 1 ;;
    esac
}
puerto_ocupado() { "$NC" -z -G 2 127.0.0.1 "$PUERTO" >/dev/null 2>&1; }
escucha_el() { "$LSOF" -nP -a -p "$1" -iTCP@127.0.0.1:"$PUERTO" -sTCP:LISTEN -t >/dev/null 2>&1; }
tunel_abierto() { "$PGREP" -U "$YO" -f "ssh -F $CONFIG -N" >/dev/null 2>&1; }
quitar_reserva() {
    # Una reserva del puerto que dejo abrir-bms al cerrarse de golpe: es nuestra.
    for p in $("$PGREP" -U "$YO" -f "nc -lk 127.0.0.1 $PUERTO" 2>/dev/null); do kill "$p" 2>/dev/null; sleep 0.5; done
}

ip_privada() {
    # Una IPv4 de red privada (10/8, 172.16/12, 192.168/16), sin ceros de mas. La imprime si vale.
    local ip="$1" a b c d resto
    case "$ip" in ''|*[!0-9.]*) return 1 ;; esac
    IFS=. read -r a b c d resto <<FIN
$ip
FIN
    [ -z "$resto" ] && [ -n "$d" ] || return 1
    for x in "$a" "$b" "$c" "$d"; do
        case "$x" in ''|0[0-9]*) return 1 ;; esac
        [ "$x" -le 255 ] || return 1
    done
    if [ "$a" -eq 10 ] || { [ "$a" -eq 172 ] && [ "$b" -ge 16 ] && [ "$b" -le 31 ]; } ||
        { [ "$a" -eq 192 ] && [ "$b" -eq 168 ]; }; then
        [ "$d" -ne 0 ] && [ "$d" -ne 255 ] || return 1
        printf '%s\n' "$ip"
        return 0
    fi
    return 1
}

ip_de_este_mac() {
    local interfaz
    interfaz="$(route -n get default 2>/dev/null | awk '/interface:/ {print $2}')"
    [ -n "$interfaz" ] && ipconfig getifaddr "$interfaz" 2>/dev/null
}

borrar() {
    tunel_abierto && fallar "Hay un tunel abierto (BMS): cierra esa ventana y vuelve a probar."
    decir "Se va a quitar de este Mac la clave del tunel, su frase del Llavero y $DIR."
    printf 'Seguir? (escribe si) '
    read -r r
    es_si "$r" || fallar "No se ha borrado nada."
    quitar_reserva
    if [ -f "$CLAVE" ]; then
        "$SSH_ADD" -d --apple-use-keychain "$CLAVE" >/dev/null 2>&1 || true
    fi
    nombre="$(cat "$DIR/nombre" 2>/dev/null)"
    rm -rf "$DIR"
    [ -L "$HOME/Desktop/BMS.command" ] && rm -f "$HOME/Desktop/BMS.command"
    decir "Borrado. En el mini PC, si no lo has hecho: mac.bat -QuitarClave -Nombre ${nombre:-<el de este Mac>}"
    decir "y un token nuevo para la persona de este Mac (persona.bat)."
    exit 0
}

[ "$(uname -s)" = Darwin ] || fallar "Esto es para un Mac."
[ -x "$SSH" ] || fallar "No encuentro $SSH (el ssh de macOS)."
if [ "${1:-}" = "--borrar" ]; then borrar; fi
[ $# -eq 0 ] || fallar "Uso: bash preparar.command   (o: bash preparar.command --borrar)"
tunel_abierto && fallar "Hay un tunel abierto (BMS). Cierra esa ventana y vuelve a abrir preparar."

mkdir -p "$DIR" && chmod 700 "$DIR" || fallar "No puedo crear $DIR."
decir "El tunel de este Mac al mini PC: preparar ($("$SSH" -V 2>&1))"
if [ "$AQUI" != "$DIR" ]; then
    # Copias sin atributos (-X): sin la cuarentena de una descarga. La segunda vez ya no hace
    # falta la memoria: bash ~/.bms-tunel/preparar.command
    cp -X "$AQUI/preparar.command" "$DIR/preparar.command" || fallar "No se ha podido copiar preparar.command a $DIR (si macOS pregunto si Terminal puede acceder a la memoria, hay que decir Permitir)."
    cp -X "$AQUI/abrir-bms.command" "$DIR/abrir-bms.command" || fallar "Falta abrir-bms.command junto a preparar.command."
    chmod 700 "$DIR/abrir-bms.command" "$DIR/preparar.command"
    xattr -d com.apple.quarantine "$DIR/abrir-bms.command" 2>/dev/null || true
fi

# ------------------------------------------------------------ 1. la clave de este Mac
if [ ! -f "$CLAVE" ]; then
    titulo "1. La clave de este Mac"
    nombre=""
    while ! printf '%s' "$nombre" | grep -Eq '^[a-z0-9][a-z0-9-]{0,30}$'; do
        printf 'Un nombre corto para este Mac (minusculas, cifras y guiones; p. ej. mac-oficina): '
        read -r nombre
    done
    decir "Ahora una frase para la clave (dos veces). Que no la uses en otro sitio. Se guarda en el"
    decir "Llavero de este Mac: no hace falta recordarla; si un dia se pierde, se hace otra clave."
    while :; do
        rm -f "$CLAVE" "$CLAVE.pub"
        "$SSH_KEYGEN" -q -t ed25519 -a 100 -C "bms-$nombre" -f "$CLAVE" || fallar "No se ha creado la clave."
        # Sin frase no: quien copiara la clave (una copia de seguridad, por ejemplo) entraria.
        if "$SSH_KEYGEN" -y -P "" -f "$CLAVE" >/dev/null 2>&1; then
            decir "Sin frase no vale. Otra vez."
            continue
        fi
        break
    done
    printf '%s\n' "$nombre" > "$DIR/nombre"
    # La frase al Llavero ahora, una vez: abrir-bms ya no la pide.
    "$SSH_ADD" --apple-use-keychain "$CLAVE" || fallar "No se ha podido guardar la frase en el Llavero."
fi
nombre="$(cat "$DIR/nombre")"

# ------------------------------------------------------------ 2. lo que hay que llevar al mini PC
titulo "2. Para el mini PC"
pub="bms-$nombre.pub"
destino="$CLAVE.pub"
if [ "$AQUI" != "$DIR" ]; then
    # Junto a preparar.command (la memoria, carpeta bms-mac): alli la busca mac.bat.
    if cp "$CLAVE.pub" "$AQUI/$pub" 2>/dev/null; then
        destino="$AQUI/$pub"
    elif cp "$CLAVE.pub" "$HOME/Desktop/$pub" 2>/dev/null; then
        destino="$HOME/Desktop/$pub"
    fi
fi
pbcopy < "$CLAVE.pub" 2>/dev/null || true
ipmac="$(ip_de_este_mac)"
decir "Nombre de este Mac:   $nombre"
decir "IP de este Mac:       ${ipmac:-no la encuentro (Ajustes del Sistema, Wi-Fi o Red, Detalles)}"
decir "Clave publica:        $destino   (tambien en el portapapeles)"
decir "Huella de la clave:   $("$SSH_KEYGEN" -l -E sha256 -f "$CLAVE.pub" | awk '{print $2}')"
decir "En el mini PC: mac.bat -Instalar (o -AnadirClave) la encuentra en la memoria USB. Te pedira"
decir "esa IP y te ensenara la misma huella."

# ------------------------------------------------------------ 3. el mini PC
titulo "3. El mini PC"
ipmini="$(cat "$DIR/ip-minipc" 2>/dev/null)"
if [ -n "$ipmini" ]; then
    printf 'IP del mini PC: %s. Intro si sigue siendo esa, o escribe la nueva: ' "$ipmini"
    read -r r
    [ -n "$r" ] && ipmini="$r"
fi
while ! ip_privada "$ipmini" >/dev/null; do
    printf 'La IP del mini PC (la ensena mac.bat -CopiarParaElMac o -Estado; p. ej. 192.168.1.10): '
    read -r ipmini
done
printf '%s\n' "$ipmini" > "$DIR/ip-minipc"
if ! "$NC" -z -G 5 "$ipmini" 22 >/dev/null 2>&1; then
    decir ""
    decir "El mini PC no contesta en $ipmini (puerto 22). Lo normal la primera vez: falta hacer en el"
    decir "mini PC mac.bat -Instalar (o -AnadirClave) con la IP de este Mac (${ipmac:-?})."
    decir "Si ya esta hecho: que este encendido y en la misma red (mac.bat -Estado en el mini PC)."
    decir "Cuando este, en Terminal: bash ~/.bms-tunel/preparar.command (sigue desde aqui)."
    exit 0
fi

# ------------------------------------------------------------ 4. la huella del mini PC
titulo "4. La huella del mini PC"
tmp="$DIR/known_hosts.nuevo"
linea="$("$SSH_KEYSCAN" -T 5 -t ed25519 -p 22 "$ipmini" 2>/dev/null | grep -v '^#' | awk '$2 == "ssh-ed25519" {print $2" "$3; exit}')"
[ -n "$linea" ] || fallar "El mini PC no ha dado su clave. Vuelve a probar en un minuto."
printf '%s %s\n' "$ALIAS" "$linea" > "$tmp"
huella="$("$SSH_KEYGEN" -l -E sha256 -f "$tmp" | awk '{print $2}')"
if [ -f "$CONOCIDOS" ] && [ "$(cat "$CONOCIDOS")" = "$(cat "$tmp")" ]; then
    decir "La huella del mini PC es la de siempre: $huella"
    rm -f "$tmp"
else
    if [ -f "$CONOCIDOS" ]; then
        decir "ATENCION: la huella del mini PC NO es la que se fijo. Solo es normal si se ha reinstalado"
        decir "algo en el mini PC (mac.bat -Quitar y -Instalar, o Windows). Si no sabes por que, NO sigas."
    fi
    decir "Huella que da el mini PC: $huella"
    decir "Mirala en el mini PC (al acabar mac.bat, o mac.bat -Estado): tiene que ser exactamente la misma."
    printf 'Es la misma? (escribe si) '
    read -r r
    es_si "$r" || { rm -f "$tmp"; fallar "No se ha fijado nada. Si no es la misma, no sigas y avisa a quien mantiene el programa."; }
    mv -f "$tmp" "$CONOCIDOS"
fi

# ------------------------------------------------------------ 5. la configuracion del tunel
cat > "$CONFIG" <<FIN
# bms-agent: el tunel al mini PC (lo escribe preparar.command; no lo cambies a mano).
# Se usa solo asi: /usr/bin/ssh -F $CONFIG -N $ALIAS
# -F hace que no se lean ~/.ssh/config ni /etc/ssh/ssh_config.
IgnoreUnknown UseKeychain

Host $ALIAS
    HostName $ipmini
    Port 22
    User $CUENTA
    IdentityFile $CLAVE
    IdentitiesOnly yes
    UseKeychain yes
    AddKeysToAgent yes
    PreferredAuthentications publickey
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    HostKeyAlias $ALIAS
    HostKeyAlgorithms ssh-ed25519
    UserKnownHostsFile $CONOCIDOS
    GlobalKnownHostsFile /dev/null
    StrictHostKeyChecking yes
    CheckHostIP no
    UpdateHostKeys no
    LocalForward 127.0.0.1:$PUERTO 127.0.0.1:$PUERTO
    ExitOnForwardFailure yes
    ServerAliveInterval 15
    ServerAliveCountMax 3
    ConnectTimeout 10
    ForwardAgent no
    ForwardX11 no
    PermitLocalCommand no
    RequestTTY no
    ControlMaster no
    ControlPath none
FIN
chmod 600 "$CONFIG" "$CONOCIDOS"

# ------------------------------------------------------------ 6. probar
titulo "5. Probar el tunel"
quitar_reserva
if puerto_ocupado; then
    fallar "Otro programa de este Mac usa ya el puerto $PUERTO. La app solo funciona en ese puerto: cierralo (o reinicia el Mac) y vuelve a probar: bash ~/.bms-tunel/preparar.command"
fi
"$SSH_ADD" --apple-use-keychain "$CLAVE" >/dev/null 2>&1 || true
"$SSH" -F "$CONFIG" -N -o BatchMode=yes "$ALIAS" 2>"$ERRORES" &
pid=$!
estado=esperando
i=0
# Hasta 60 s: la primera vez, el mini PC crea el perfil de la cuenta del tunel.
while [ $i -lt 120 ]; do
    if ! kill -0 "$pid" 2>/dev/null; then estado=muerto; break; fi
    if escucha_el "$pid"; then estado=abierto; break; fi
    sleep 0.5
    i=$((i + 1))
done
codigo=000
if [ "$estado" = abierto ]; then
    codigo="$("$CURL" -s -o /dev/null -m 15 -w '%{http_code}' "http://127.0.0.1:$PUERTO/consola")"
fi
kill "$pid" 2>/dev/null
wait "$pid" 2>/dev/null
if grep -q -e 'Host key verification failed' -e 'REMOTE HOST IDENTIFICATION HAS CHANGED' "$ERRORES" 2>/dev/null; then
    fallar "La identidad del mini PC NO es la que se acaba de fijar. No sigas y avisa a quien mantiene el programa."
fi
if grep -q 'Permission denied' "$ERRORES" 2>/dev/null; then
    fallar "El mini PC no acepta la clave de este Mac todavia: en el mini PC, mac.bat -AnadirClave (nombre $nombre, IP ${ipmac:-?}, el fichero $pub). Luego: bash ~/.bms-tunel/preparar.command"
fi
case "$estado" in
    muerto)
        sed -n '1,5p' "$ERRORES" 2>/dev/null
        fallar "No se ha podido abrir el tunel. Que el mini PC este encendido y en la misma red, y que la IP de este Mac (${ipmac:-?}) sea la que tiene apuntada (mac.bat -Estado en el mini PC). Luego: bash ~/.bms-tunel/preparar.command" ;;
    esperando)
        fallar "El mini PC tarda en contestar. Vuelve a probar en un minuto: bash ~/.bms-tunel/preparar.command" ;;
esac
case "$codigo" in
    200) decir "Funciona: la app del mini PC contesta por el tunel." ;;
    000) decir "El tunel abre, pero la app del mini PC no contesta. No pasa nada: abrir-bms lo dira"
         decir "cuando la app este en marcha en el mini PC (sesion de bms y Docker Desktop)." ;;
    *) decir "El tunel abre y el mini PC contesta ($codigo)." ;;
esac

# ------------------------------------------------------------ 7. BMS en el Escritorio
titulo "Listo"
if ln -sfn "$DIR/abrir-bms.command" "$HOME/Desktop/BMS.command" 2>/dev/null && [ -L "$HOME/Desktop/BMS.command" ]; then
    decir "Para abrir la app: doble clic en BMS.command del Escritorio (puedes arrastrarlo al Dock)."
else
    decir "No he podido dejar BMS en el Escritorio (si macOS pregunto si Terminal puede acceder al"
    decir "Escritorio, hay que decir Permitir). Para abrir la app: en Terminal, bash $DIR/abrir-bms.command"
fi
decir "Se abre una ventana de Terminal con el tunel y la app en el navegador, en"
decir "http://127.0.0.1:$PUERTO/app. Entras con el token de la persona de este Mac."
```

## Anexo B. `mac/abrir-bms.command` (`bash -n` y `bash --posix -n` sin errores; ejecutado contra programas falsos en 10 casos)

```bash
#!/bin/bash
# bms-agent: abre el tunel al mini PC y la app en el navegador de este Mac (paso 18b,
# docs/entorno-local.md "Usarlo desde un Mac"). preparar.command lo deja en ~/.bms-tunel y en
# el Escritorio como BMS.command.
#
# Deja esta ventana abierta mientras uses la app: al cerrarla (o con Ctrl+C) se cierra el
# tunel. Si se corta (el Mac se duerme, el mini PC se reinicia), lo vuelve a abrir solo y,
# mientras tanto, guarda el puerto 8765 de este Mac para que ningun otro programa lo coja: la
# pestana de la app sigue llamando con tu token.
# bash 3.2 de macOS. Solo herramientas del sistema.

set -u
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
DIR="$HOME/.bms-tunel"
CONFIG="$DIR/ssh_config"
CLAVE="$DIR/clave_ed25519"
ERRORES="$DIR/ultimo-error.txt"
ALIAS=bms-minipc
PUERTO=8765
URL="http://127.0.0.1:$PUERTO"
SSH=/usr/bin/ssh
SSH_ADD=/usr/bin/ssh-add
NC=/usr/bin/nc
CURL=/usr/bin/curl
OPEN=/usr/bin/open
PGREP=/usr/bin/pgrep
LSOF=/usr/sbin/lsof
YO="$(id -u)"

decir() { printf '%s\n' "$*"; }
hora() { date +%H:%M; }
fallar() { printf '\n%s\n\n' "$*" >&2; exit 1; }
# Con la pestana de la app quiza abierta: el puerto sigue guardado hasta que la cierre.
fallar_con_pestana() {
    printf '\n%s\n\n' "$*" >&2
    if [ -n "$PID_RESERVA" ]; then
        printf 'Cierra la pestana de la app (o pulsa Salir en ella) y luego pulsa Intro aqui. '
        read -r _
    fi
    exit 1
}

# Alguien (quien sea) escucha en 127.0.0.1:8765 de este Mac.
puerto_ocupado() { "$NC" -z -G 2 127.0.0.1 "$PUERTO" >/dev/null 2>&1; }
# El proceso $1 escucha en 127.0.0.1:8765 (lsof sin root solo ve los procesos propios).
escucha_el() { "$LSOF" -nP -a -p "$1" -iTCP@127.0.0.1:"$PUERTO" -sTCP:LISTEN -t >/dev/null 2>&1; }

if [ ! -f "$CONFIG" ] || [ ! -f "$DIR/known_hosts" ] || [ ! -f "$CLAVE" ]; then
    fallar "Este Mac aun no esta preparado: abre antes preparar.command (docs/entorno-local.md, Usarlo desde un Mac)."
fi

# 1. Ya abierto en otra ventana: solo si quien escucha en el 8765 es ese ssh, y es nuestro.
for p in $("$PGREP" -U "$YO" -f "ssh -F $CONFIG -N" 2>/dev/null); do
    if escucha_el "$p"; then
        decir "El tunel ya esta abierto en otra ventana de Terminal: se abre la app."
        "$OPEN" "$URL/app"
        exit 0
    fi
done

# 2. Una reserva del puerto que quedo de una ventana cerrada de golpe: es nuestra, fuera.
for p in $("$PGREP" -U "$YO" -f "nc -lk 127.0.0.1 $PUERTO" 2>/dev/null); do
    kill "$p" 2>/dev/null
    sleep 0.5
done

# 3. La app solo acepta 127.0.0.1:8765 (Host y Origin). Si otro programa de este Mac escucha
#    ahi, el navegador le mandaria la pagina y el token: se dice y se para.
if puerto_ocupado; then
    fallar "Otro programa de este Mac usa ya el puerto $PUERTO. La app solo funciona en ese puerto: cierralo (o reinicia el Mac) y vuelve a abrir BMS."
fi

# 4. La clave: su frase sale del Llavero; si no esta, se pide aqui una vez.
LOTE=yes
"$SSH_ADD" --apple-use-keychain "$CLAVE" >/dev/null 2>&1 || LOTE=no

PID_SSH=""
PID_RESERVA=""
reservar() {
    # Mientras no hay tunel, el 8765 lo tiene un nc nuestro que acepta y no contesta.
    "$NC" -lk 127.0.0.1 "$PUERTO" </dev/null >/dev/null 2>&1 &
    PID_RESERVA=$!
    i=0
    while [ $i -lt 15 ]; do
        kill -0 "$PID_RESERVA" 2>/dev/null || break
        if escucha_el "$PID_RESERVA"; then return 0; fi
        sleep 0.2
        i=$((i + 1))
    done
    kill "$PID_RESERVA" 2>/dev/null
    PID_RESERVA=""
    return 1
}
soltar() {
    if [ -n "$PID_RESERVA" ]; then
        kill "$PID_RESERVA" 2>/dev/null
        wait "$PID_RESERVA" 2>/dev/null
    fi
    PID_RESERVA=""
}
cerrar() {
    if [ -n "$PID_SSH" ]; then kill "$PID_SSH" 2>/dev/null; fi
    PID_SSH=""
    soltar
}
trap 'cerrar; decir ""; decir "Tunel cerrado. Si la app sigue abierta en el navegador: Salir, o cierra la pestana."; exit 0' INT TERM HUP
trap cerrar EXIT

abierta=no
espera=5
while :; do
    inicio=$(date +%s)
    # Justo antes de ssh se suelta la reserva; si alguien se cuela en ese instante, ssh no
    # puede escuchar y sale (ExitOnForwardFailure): se para abajo.
    soltar
    "$SSH" -F "$CONFIG" -N -o BatchMode="$LOTE" "$ALIAS" 2>"$ERRORES" &
    PID_SSH=$!
    listo=no
    i=0
    while [ $i -lt 120 ]; do
        kill -0 "$PID_SSH" 2>/dev/null || break
        if escucha_el "$PID_SSH"; then listo=si; break; fi
        sleep 0.5
        i=$((i + 1))
    done
    if [ "$listo" = si ]; then
        if [ "$abierta" = no ]; then
            codigo="$("$CURL" -s -o /dev/null -m 15 -w '%{http_code}' "$URL/app")"
            case "$codigo" in
                200) "$OPEN" "$URL/app" ;;
                503) decir "La app no esta construida en el mini PC: se abre la consola de antes."
                     "$OPEN" "$URL/consola" ;;
                000) decir "El tunel esta abierto, pero la app del mini PC no contesta: que el mini PC tenga"
                     decir "la sesion de bms iniciada y Docker Desktop en marcha (o la consola, en la nativa)."
                     decir "Cuando conteste, abre $URL/app en el navegador." ;;
                *) "$OPEN" "$URL/app" ;;
            esac
            abierta=si
            decir "$(hora) Tunel abierto. Deja esta ventana abierta mientras uses la app. Al acabar:"
            decir "      Salir en la app, y luego cierra esta ventana. La direccion es siempre $URL/app."
        else
            decir "$(hora) Tunel abierto otra vez. Ya puedes seguir en la app."
        fi
    fi
    wait "$PID_SSH"
    PID_SSH=""
    # Lo primero, el puerto: la pestana de la app sigue llamando cada 2 s con el token.
    if [ "$abierta" = si ] && ! reservar; then
        fallar "En cuanto se ha cortado el tunel, otro programa de este Mac ha cogido el puerto $PUERTO. Cierra la pestana de la app y pide en el mini PC un token nuevo para este Mac (persona.bat)."
    fi
    duro=$(( $(date +%s) - inicio ))
    # Lo que no se arregla esperando: se dice y se para.
    if grep -q -e 'Host key verification failed' -e 'REMOTE HOST IDENTIFICATION HAS CHANGED' "$ERRORES" 2>/dev/null; then
        fallar_con_pestana "La identidad del mini PC NO es la que se fijo. No sigas: si se ha reinstalado algo en el mini PC, vuelve a hacer preparar.command y compara la huella; si no, avisa a quien mantiene el programa."
    fi
    if grep -q 'Permission denied' "$ERRORES" 2>/dev/null; then
        fallar_con_pestana "El mini PC no acepta la clave de este Mac (o la IP de este Mac ya no es la que tiene apuntada el mini PC). En el mini PC: mac.bat -Estado, y mac.bat -AnadirClave si hace falta."
    fi
    if grep -q -e 'administratively prohibited' "$ERRORES" 2>/dev/null; then
        fallar_con_pestana "El mini PC no deja este reenvio. Manda $ERRORES a quien mantiene el programa."
    fi
    if grep -q -e 'Address already in use' -e 'Could not request local forwarding' -e 'cannot listen' "$ERRORES" 2>/dev/null; then
        fallar_con_pestana "Otro programa de este Mac ha cogido el puerto $PUERTO. Cierra la pestana de la app; si no sabes que programa es, pide en el mini PC un token nuevo para este Mac (persona.bat)."
    fi
    if [ "$abierta" = no ] && [ "$duro" -lt 30 ]; then
        sed -n '1,5p' "$ERRORES" 2>/dev/null
        fallar "No se ha podido abrir el tunel. Que el mini PC este encendido y en la misma red, y que la IP de este Mac sea la que tiene apuntada (mac.bat -Estado en el mini PC)."
    fi
    [ "$duro" -gt 120 ] && espera=5
    decir "$(hora) El tunel se ha cortado (el Mac se ha dormido, el mini PC se ha reiniciado o se ha ido la red)."
    decir "      No uses la app hasta que vuelva. Se reintenta en $espera s; para dejarlo: Salir en la app y cierra esta ventana."
    sleep "$espera"
    [ "$espera" -lt 60 ] && espera=$((espera * 2))
done
```

## Anexo C. `mac.ps1`: lo que decide qué entra en sshd, en las claves y en el cortafuegos, y lo que cambia tras la revisión

El script entero es el borrador `scratchpad/correo/mac/borrador/docker/mac.ps1` (~810 líneas) con
estos cambios. **Se sustituyen** por las de C.2 y C.3 las funciones del mismo nombre y la entrada
(parámetros, comprobación y elevación); **se añaden** las nuevas; las de C.1 no cambian salvo
`Solo-Administradores` (`$Icacls`) y `Elegir-Mac` (nueva). Las acciones del `switch` cambian como dicen
§2.1, §2.8 y §2.13: `-Instalar` en el orden de §2.8 (con `$nuevoMac`), `-AnadirClave` exige
`$nuevoMac` (con `-MismaClave`, la clave que ya tenía), `-QuitarClave` usa el `-Nombre` que eligió
`Elegir-Mac`, `-Quitar` añade `Negar-Inicios $sid -Quitar` antes de `Remove-LocalUser` y dice las
carpetas `ssh.apartada-*`; `Mostrar-Estado` gana las líneas de §2.7 (con `Negaciones-Que-Faltan`,
`Lectores-De-Datos (Rutas-De-Datos)`, `Carpeta-Ssh-Segura`, `Procesos-De-Sshd`) y `Linea-De-Estado` un
tercer nivel, «mal» en rojo. Se quitan el `Pedir-Mac` de antes, la pregunta de la red privada,
`Get-LocalGroupMember` y `Get-Process -Name sshd`. Constantes nuevas: `$Icacls`, `$Taskkill`,
`$Secedit`, `$Takeown` (`Join-Path $env:SystemRoot "System32\<x>.exe"`) y `$FicherosDelMac`.

### C.1 Las que no cambian (del borrador, probadas allí), `Solo-Administradores` con `$Icacls` y `Elegir-Mac`

```powershell
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

function Solo-Administradores([string]$Ruta) {
    # Solo SYSTEM y Administradores; la cuenta del tunel ni lo lee ni lo cambia. sshd lo lee
    # desde su proceso de SYSTEM, como administrators_authorized_keys.
    & $Icacls $Ruta /inheritance:r /grant:r ("*" + $SidSistema + ":F") ("*" + $SidAdministradores + ":F") | Out-Null
    & $Icacls $Ruta /setowner ("*" + $SidAdministradores) | Out-Null
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
```

### C.2 Las nuevas o cambiadas (`pruebas-final/funciones.ps1`: analizada con `pwsh`, ASCII; las puras, probadas con `probar.ps1`, 14 casos)

```powershell
# Lo que cambia en mac.ps1 tras la revision (paso 18b, diseno-mac.md apartado 10). Solo funciones:
# las constantes ($Cuenta, $PuertoApp, $Sshd, $ProgramasSsh, $CarpetaSsh, $Icacls, $Taskkill,
# $Secedit, $SidSistema, $SidAdministradores, $SidTrustedInstaller...) son las de mac.ps1.

$DerechosNegados = @("SeDenyInteractiveLogonRight", "SeDenyRemoteInteractiveLogonRight",
    "SeDenyBatchLogonRight", "SeDenyServiceLogonRight")
# Los grupos que lleva cualquier inicio de sesion de red de una cuenta local (el S4U de sshd):
# Todos, Usuarios autenticados, Usuarios (que contiene a Usuarios autenticados), Red y Cuenta local.
$SidesDeCualquiera = @("S-1-1-0", "S-1-5-11", "S-1-5-32-545", "S-1-5-2", "S-1-5-113")

function Sid-De-Regla($Regla) {
    try { return $Regla.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value } catch { return ("" + $Regla.IdentityReference) }
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
    # lean lo del programa: el proyecto, sus secretos, el estado, el buzon, los datos de la
    # nativa. Devuelve la primera ruta que si, o $null.
    $quien = @($SidesDeCualquiera) + @($SidTunel)
    foreach ($r in $Rutas) {
        if (-not (Test-Path -LiteralPath $r)) { continue }
        $acl = Get-Acl -LiteralPath $r
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
    # Docker: <proyecto> = padre de docker\. Nativa: <Raiz> = padre de windows\.
    $padre = Split-Path -Parent $PSScriptRoot
    return @($padre, (Join-Path $padre "datos"), (Join-Path $padre "buzon"),
        (Join-Path $padre "docker\secretos"), (Join-Path $padre "docker\secretos\correo"),
        (Join-Path $padre "docker\estado"))
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

function Grupos-De-La-Cuenta([string]$Nombre) {
    # Los grupos locales de los que la cuenta es miembro directo, por SID. Con ADSI (los grupos
    # del usuario) y no con Get-LocalGroupMember, que en 5.1 falla con miembros huerfanos o de
    # Entra. Si no se puede mirar, lanza: quien llama lo trata como un error, nunca como "ninguno".
    $u = [ADSI]("WinNT://" + $env:COMPUTERNAME + "/" + $Nombre + ",user")
    $sids = @()
    foreach ($g in @($u.psbase.Invoke("Groups"))) {
        $bytes = $g.GetType().InvokeMember("objectSid", "GetProperty", $null, $g, $null)
        $sids += (New-Object Security.Principal.SecurityIdentifier($bytes, 0)).Value
    }
    return $sids
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
        $mal = Diferencias-De-Derechos (Lineas-De-Derechos $textoAntes) (Lineas-De-Derechos ([IO.File]::ReadAllText($despues, [Text.Encoding]::Unicode))) $Sid -Quitar:$Quitar
        if ($mal) {
            & $Secedit /configure /db (Join-Path $tmp "vuelta.sdb") /cfg $antes /areas USER_RIGHTS /quiet 2>&1 | Out-Null
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
        $u = Get-LocalUser -Name $Cuenta
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

function Aplicar($E) {
    # Rehace claves, configuracion y reglas a partir del estado, y arranca sshd. Si algo no
    # cuadra, sshd queda parado y el cortafuegos cerrado: falla cerrado.
    $macs = @(Macs-De $E)
    Poner-Reglas -Cerrado
    Stop-Service -Name sshd -Force -ErrorAction SilentlyContinue
    $quedan = Parar-Tuneles
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
    if ($quedan -gt 0) {
        Escribir ("   ATENCION: queda " + $quedan + " proceso(s) de un tunel que Windows no ha dejado cortar. Reinicia el equipo ahora: al volver, solo entran los Mac de la lista.") "Red"
    }
}
```

### C.3 La entrada: parámetros, comprobación, preguntas antes de elevar y elevación (`pruebas-final/flujo.ps1`: analizada con `pwsh`; `Origen-Valido`, 12 casos)

```powershell
# Lo que cambia en el flujo de mac.ps1 (paso 18b, diseno-mac.md apartados 2.1, 2.11 y 2.13).
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

function Copiar-Para-El-Mac([string]$Destino) {
    # Lo que va al Mac sale de aqui despues de comprobar que nadie mas lo puede cambiar.
    $origen = Join-Path (Split-Path -Parent $PSScriptRoot) "mac"
    if (-not (Test-Path -LiteralPath $Destino -PathType Container)) { Fallar ("No encuentro " + $Destino + " (la memoria USB, p. ej. E:\).") }
    $carpeta = Join-Path $Destino "bms-mac"
    if (Test-Path -LiteralPath $carpeta) {
        if (-not (Es-Si (Read-Host ("Ya hay " + $carpeta + ". Sustituir lo que hay? (escribe si)")))) { Fallar "No se ha copiado nada." }
    } else {
        New-Item -ItemType Directory -Path $carpeta | Out-Null
    }
    foreach ($f in $FicherosDelMac) {
        Copy-Item -LiteralPath (Join-Path $origen $f) -Destination (Join-Path $carpeta $f) -Force
        $h = (Get-FileHash -LiteralPath (Join-Path $carpeta $f) -Algorithm SHA256).Hash.ToLower()
        Escribir ("   " + $f + "   sha256 " + $h.Substring(0, 16))
    }
    Escribir ("Copiado en " + $carpeta + ".") "Green"
    Escribir "En el Mac te va a pedir la IP de este equipo:" "Cyan"
    foreach ($c in @(Ips-Del-Equipo)) { Escribir ("   " + $c.Ip + "   (" + $c.Interfaz + ")") }
}

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
$CarpetaDelMac = Join-Path (Split-Path -Parent $PSScriptRoot) "mac"
$ficheros = @($PSCommandPath, (Join-Path $PSScriptRoot "mac.bat"))
$carpetas = @($PSScriptRoot)
if (Test-Path -LiteralPath $CarpetaDelMac) {
    $ficheros += @($FicherosDelMac | ForEach-Object { Join-Path $CarpetaDelMac $_ })
    $carpetas += $CarpetaDelMac
} elseif ($accion -eq "CopiarParaElMac") {
    Fallar ("Falta la carpeta " + $CarpetaDelMac + " (en la nativa, vuelve a abrir instalar.bat).")
}
$quien = Quien-Mas-Puede-Cambiar $ficheros $carpetas $Usuario
if ($quien) {
    Fallar ("Otra cuenta de este equipo puede cambiar lo que mac.bat ejecuta como administrador o lo que va al Mac (" + $quien +
        "). Asi no se sigue. Con Docker: proteger.bat (docs/entorno-local.md). En la nativa: instalar.bat lo deja bien.")
}
if ($accion -eq "CopiarParaElMac") { Copiar-Para-El-Mac $CopiarParaElMac; exit 0 }

# Lo que hay que preguntar, antes de pedir ser administrador.
if (-not $Elevado) {
    $leido = Leer-Estado
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
```

## Anexo D. `docker/proteger.ps1` y los dos `.bat` (analizado con `pwsh`, ASCII)

```powershell
# La carpeta del proyecto, protegida (paso 18b, docs/entorno-local.md "El usuario de lo
# automatico"). Con Docker y el usuario aparte de lo automatico ("bms"): solo los
# administradores y tu cuenta pueden cambiarla; "bms" la lee y solo escribe en docker\estado y
# docker\secretos\correo. Asi "bms" no puede cambiar los scripts que abres tu (persona.bat,
# mac.bat...) ni lo que se copia al Mac, y ninguna otra cuenta del equipo lee los secretos ni
# las facturas.
#
#   .\proteger.bat -Usuario bms   una vez al poner la carpeta, y otra cada vez que pongas una
#                                 version nueva (antes de iniciar.bat)
#
# Windows PowerShell 5.1, ASCII. No carga comun.ps1 (corre como administrador). No usa Docker.
param(
    [string]$Usuario = "",
    [switch]$Elevado,
    [string]$Dueno = ""
)

$ErrorActionPreference = "Continue"
$SidSistema = "S-1-5-18"
$SidAdministradores = "S-1-5-32-544"
$Icacls = Join-Path $env:SystemRoot "System32\icacls.exe"
# Las carpetas en las que escribe "bms" (docs/v1/paso-18/diseno.md 4.1, 4.4 y 2.4): la pausa, el
# cerrojo y los registros del ciclo; el certificado del correo que escribe la orden montada.
$EscribeBms = @("docker\estado", "docker\secretos\correo")

function Escribir([string]$Texto, [string]$Color = "Gray") {
    Write-Host $Texto -ForegroundColor $Color
}

function Esperar-Intro {
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

function Icacls([string[]]$Argumentos) {
    & $Icacls @Argumentos | Out-Null
    if ($LASTEXITCODE -ne 0) { Fallar ("No se han podido poner los permisos (icacls " + ($Argumentos -join " ") + ").") }
}

function Grupos-De-La-Cuenta([string]$Nombre) {
    # Igual que en mac.ps1: por ADSI y por SID; si no se puede mirar, lanza.
    $u = [ADSI]("WinNT://" + $env:COMPUTERNAME + "/" + $Nombre + ",user")
    $sids = @()
    foreach ($g in @($u.psbase.Invoke("Groups"))) {
        $bytes = $g.GetType().InvokeMember("objectSid", "GetProperty", $null, $g, $null)
        $sids += (New-Object Security.Principal.SecurityIdentifier($bytes, 0)).Value
    }
    return $sids
}

if ([Environment]::Is64BitOperatingSystem -and -not [Environment]::Is64BitProcess) {
    Fallar "Abre proteger.bat con doble clic o desde una ventana normal (no desde un programa de 32 bits)."
}
$Proyecto = Split-Path -Parent $PSScriptRoot
foreach ($prohibida in @($env:SystemRoot, $env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:ProgramData)) {
    if ($prohibida -and $Proyecto.StartsWith($prohibida, [StringComparison]::OrdinalIgnoreCase)) {
        Fallar ("La carpeta del proyecto no puede estar en " + $prohibida + ": ponla, por ejemplo, en C:\bms-agent.")
    }
}
if ([IO.Path]::GetPathRoot($Proyecto) -eq $Proyecto) { Fallar "La carpeta del proyecto no puede ser la raiz de un disco." }
foreach ($c in @(Get-Item -Force -LiteralPath $Proyecto) + @(Get-ChildItem -Force -LiteralPath $Proyecto)) {
    if ($c.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        Fallar ($c.FullName + " es un enlace a otro sitio: quitalo y vuelve a probar.")
    }
}
if (-not $Usuario) { Fallar "Di el usuario de lo automatico: proteger.bat -Usuario bms" }
$cuenta = Get-LocalUser -Name $Usuario -ErrorAction SilentlyContinue
if (-not $cuenta) { $cuenta = Get-LocalUser -SID $Usuario -ErrorAction SilentlyContinue }
if (-not $cuenta) { Fallar ("No hay ningun usuario local " + $Usuario + " en este equipo.") }
$sidBms = $cuenta.SID.Value
if (-not $Dueno) { $Dueno = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value }
if ($Dueno -notmatch '^S-1-5-21-\d+-\d+-\d+-\d+$') { Fallar "Uso interno: -Dueno no es un SID de una cuenta." }
if ($sidBms -eq $Dueno) { Fallar ("El usuario de lo automatico tiene que ser otro, no tu cuenta (" + $cuenta.Name + ").") }
try { $grupos = @(Grupos-De-La-Cuenta $cuenta.Name) } catch { Fallar ("No se han podido mirar los grupos de " + $cuenta.Name + ".") }
if ($grupos -contains $SidAdministradores) { Fallar ($cuenta.Name + " es administrador: el usuario de lo automatico tiene que ser un usuario estandar.") }

if (-not $Elevado) {
    Escribir ("La carpeta " + $Proyecto + ":") "Cyan"
    Escribir ("   podran cambiarla los administradores y tu; " + $cuenta.Name + " solo leerla, y escribir en " + ($EscribeBms -join " y ") + ".")
    Escribir "   Nadie mas del equipo podra leerla (ni los secretos, ni el buzon)."
    Escribir "Hazlo justo despues de poner la carpeta (la primera vez o con una version nueva), antes de" "Yellow"
    Escribir ("que " + $cuenta.Name + " arranque nada con ella.") "Yellow"
    if (-not (Es-Si (Read-Host "Seguir? (escribe si)"))) { Fallar "No se ha cambiado nada." }
    if (-not (Es-Administrador)) {
        $argumentos = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ('"' + $PSCommandPath + '"'),
            "-Usuario", $sidBms, "-Dueno", $Dueno, "-Elevado")
        try {
            $p = Start-Process -FilePath (Get-Process -Id $PID).Path -ArgumentList $argumentos -Verb RunAs -Wait -PassThru
        } catch {
            Fallar "Sin permiso de administrador no se puede. Vuelve a abrir proteger.bat y di que si."
        }
        exit $p.ExitCode
    }
}

$sistema = "*" + $SidSistema
$administradores = "*" + $SidAdministradores
# 1. Todo, de los administradores: ni "bms" ni nadie puede cambiar los permisos.
Icacls @($Proyecto, "/setowner", $administradores, "/T", "/C", "/Q")
# 2. La raiz: sin la herencia de C:\ (que deja a cualquier usuario cambiar y leer).
Icacls @($Proyecto, "/inheritance:r", "/grant:r", ($sistema + ":(OI)(CI)F"), ($administradores + ":(OI)(CI)F"),
    ("*" + $Dueno + ":(OI)(CI)M"), ("*" + $sidBms + ":(OI)(CI)RX"), "/Q")
$nuestros = @($SidSistema, $SidAdministradores, $Dueno, $sidBms)
foreach ($regla in @((Get-Acl -LiteralPath $Proyecto).Access | Where-Object { -not $_.IsInherited -and "$($_.AccessControlType)" -eq "Allow" })) {
    $quien = $regla.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
    if ($nuestros -notcontains $quien) { Icacls @($Proyecto, "/remove:g", ("*" + $quien), "/Q") }
}
# 3. Lo de dentro hereda solo eso.
foreach ($hijo in @(Get-ChildItem -Force -LiteralPath $Proyecto)) {
    Icacls @($hijo.FullName, "/reset", "/T", "/C", "/Q")
}
# 4. Donde escribe "bms".
foreach ($r in $EscribeBms) {
    $ruta = Join-Path $Proyecto $r
    New-Item -ItemType Directory -Force -Path $ruta | Out-Null
    Icacls @($ruta, "/grant", ("*" + $sidBms + ":(OI)(CI)M"), "/Q")
}
# 5. Comprobarlo: en la raiz, solo esos cuatro.
$quedan = @((Get-Acl -LiteralPath $Proyecto).Access | Where-Object { "$($_.AccessControlType)" -eq "Allow" } |
    ForEach-Object { $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value } |
    Where-Object { $nuestros -notcontains $_ })
if ($quedan.Count -gt 0) { Fallar ("La carpeta tiene permisos de " + ($quedan -join ", ") + " que no se pueden quitar.") }
Escribir ("Listo: " + $Proyecto + " es de los administradores; tu la cambias, " + $cuenta.Name + " la lee y escribe solo en " + ($EscribeBms -join " y ") + ".") "Green"
Esperar-Intro
```

`docker/proteger.bat` y `docker/mac.bat` (= `windows/mac.bat`), con CRLF en el repositorio:

```bat
@echo off
rem Abre proteger.ps1 sin tener que cambiar la politica de scripts de Windows (pide administrador).
rem PowerShell por su ruta completa: cmd busca los programas primero en la carpeta actual.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0proteger.ps1" %*
if errorlevel 1 pause

@echo off
rem Abre mac.ps1 sin tener que cambiar la politica de scripts de Windows (pide administrador).
rem PowerShell por su ruta completa: cmd busca los programas primero en la carpeta actual.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0mac.ps1" %*
if errorlevel 1 pause
```
