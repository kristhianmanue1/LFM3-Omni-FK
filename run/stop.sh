#!/usr/bin/env bash
# Parada limpia del motor LFM3-Omni (puerto 8091).
set -euo pipefail

PORT=8091
DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$DIR/llama-server.pid"

if [ -f "$PIDFILE" ]; then
  kill "$(cat "$PIDFILE")" 2>/dev/null || true
  rm -f "$PIDFILE"
fi

pkill -f "llama-server.*--port $PORT" 2>/dev/null || true
sleep 1

if lsof -nP -iTCP:$PORT -sTCP:LISTEN 2>/dev/null | grep -q LISTEN; then
  echo "BLOQ: el puerto $PORT sigue en escucha" >&2
  exit 1
fi

echo "detenido: sin escucha en $PORT"
