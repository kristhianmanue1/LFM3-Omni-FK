#!/usr/bin/env bash
# Parada limpia del motor LFM3-Omni (puerto 8091).
set -euo pipefail

PORT=8091
DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$DIR/llama-server.pid"

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE")"
  # Propiedad antes de disparo: jamás matar un pid reciclado ajeno
  # (mismo binario en otro puerto cuenta como ajeno).
  if ps -p "$PID" -o command= 2>/dev/null | grep -q "llama-server.*--port $PORT"; then
    kill "$PID" 2>/dev/null || true
  fi
  rm -f "$PIDFILE"
fi

pkill -f "llama-server.*--port $PORT" 2>/dev/null || true

for _ in 1 2 3; do
  if ! lsof -nP -iTCP:$PORT -sTCP:LISTEN 2>/dev/null | grep -q LISTEN; then
    echo "detenido: sin escucha en $PORT"
    exit 0
  fi
  sleep 1
done

echo "BLOQ: el puerto $PORT sigue en escucha" >&2
exit 1
