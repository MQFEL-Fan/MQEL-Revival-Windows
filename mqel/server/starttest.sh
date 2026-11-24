#!/usr/bin/env bash
# Startet/stoppt Spielserver und Chat-Server (XMPP) im Hintergrund.
# Ausgaben: server/game_server.out, server/xmpp.out; PIDs: server/*.pid
#
# Gebrauch:  server/start.sh [start] [Optionen für game_server.py]
#            server/start.sh stop | restart [...] | status
# Vorgabe:   --host 0.0.0.0, Profil new (PROFILE=full server/start.sh für ein anderes)
#            HOST=127.0.0.1 server/start.sh   (nur lokal)

cd "$(dirname "$0")/.." || exit 1
HOST=${HOST:-0.0.0.0}
PROFILE=${PROFILE:-new}  # Chat prüft Anmeldungen gegen server/state/$PROFILE

# PID-Datei prüfen; ohne sie (Server von Hand gestartet) nach dem Skript suchen
running() {
    [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null && return
    local p; p=$(pgrep -f "^python3? (-u )?server/$(basename "$1" .pid)\.py" | head -1)
    [ -n "$p" ] && echo "$p" >"$1"
}

start_one() {  # Name, Ausgabe, Skript, Argumente...
    local pid=server/$1.pid out=$2; shift 2
    if running "$pid"; then
        echo "$(basename "$pid" .pid) läuft schon (PID $(cat "$pid"))"
        return
    fi
    nohup python3 -u "$@" >"$out" 2>&1 </dev/null &
    echo $! >"$pid"
    sleep 1
    if running "$pid"; then
        echo "$(basename "$pid" .pid) gestartet (PID $!, Ausgabe $out)"
    else
        echo "$(basename "$pid" .pid) beendet sich sofort:"; tail -5 "$out"; rm -f "$pid"
        return 1
    fi
}

stop_one() {
    local pid=server/$1.pid
    if running "$pid"; then
        kill "$(cat "$pid")" && echo "$1 beendet"
    fi
    rm -f "$pid"
}

cmd=${1:-start}
case $cmd in start|stop|restart|status) shift ;; *) cmd=start ;; esac

case $cmd in
    stop)    stop_one game_server; stop_one xmpp_server ;;
    status)  for n in game_server xmpp_server; do
                 if running server/$n.pid; then echo "$n läuft (PID $(cat server/$n.pid))"
                 else echo "$n läuft nicht"; fi
             done ;;
    restart) "$0" stop; sleep 1; exec "$0" start "$@" ;;
    start)
        start_one xmpp_server server/xmpp.out server/xmpp_server.py --host "$HOST" --port 5222 \
            --state "server/state/$PROFILE"
        start_one game_server server/game_server.out server/game_server.py \
            --host "$HOST" --port 8081 --profile "$PROFILE" "$@" ;;
esac
