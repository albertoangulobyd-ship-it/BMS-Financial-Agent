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
    # 5, 10, 20, 40 y luego 60 s entre intentos (vuelve a 5 tras un tunel de mas de 2 minutos).
    espera=$((espera * 2))
    [ "$espera" -gt 60 ] && espera=60
done
