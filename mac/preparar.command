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
# Lo que llega por la red, antes de mirarlo: solo una clave ed25519 (tipo y 68 de base64).
printf '%s' "$linea" | grep -Eq '^ssh-ed25519 [A-Za-z0-9+/]{68}$' || fallar "El mini PC ha dado una clave que no es la que se espera (ed25519). No sigas y avisa a quien mantiene el programa."
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
