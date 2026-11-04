#!/usr/bin/env bash
# Parada limpia del motor LFM3-Omni (puerto 8091).
# SPEC I0 §7: propiedad antes de disparo — sólo se mata un pid cuya
# línea de comando es realmente el binario llama-server en este puerto
# (pidfile verificado o listener de lsof verificado). Un pid reciclado
# o un proceso ajeno que mencione el patrón sobrevive (SPEC I0 r18).
set -euo pipefail

PORT=8091
DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$DIR/llama-server.pid"

es_motor() {
  # $1 = pid; retorna 0 si el comando del pid es llama-server ... --port
  PID="$1"
  [ -n "$PID" ] || return 1
  CMD="$(ps -p "$PID" -o command= 2>/dev/null || true)"
  [ -n "$CMD" ] || return 1
  BINARIO="$(printf '%s' "$CMD" | cut -d' ' -f1)"
  case "${BINARIO##*/}" in
    llama-server) printf '%s\n' "$CMD" \
      | grep -Eq -- "--port ${PORT}([[:space:]]|$)" ;;
    *) return 1 ;;
  esac
}

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE")"
  if es_motor "$PID"; then
    kill "$PID" 2>/dev/null || true
  fi
  rm -f "$PIDFILE"
fi

# Listener vivo sin pidfile (motor lanzado a mano): mismo control de
# propiedad antes de disparar. Nunca un pkill amplio por patrón.
for PID in $(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true); do
  if es_motor "$PID"; then
    kill "$PID" 2>/dev/null || true
  fi
done

for _ in 1 2 3; do
  if ! lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | grep -q LISTEN; then
    echo "detenido: sin escucha en $PORT"
    exit 0
  fi
  sleep 1
done

echo "BLOQ: el puerto $PORT sigue en escucha; revisa el dueño con lsof -iTCP:$PORT" >&2
exit 1
