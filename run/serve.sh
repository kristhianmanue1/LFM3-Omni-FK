#!/usr/bin/env bash
# Arranque del motor LFM3-Omni según el runbook de ADR-001.
# Puerto 8091, solo localhost (CERRADA-6); greedy; no-reasoning.
set -euo pipefail

PORT=8091
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$DIR/llama-server.log"
PIDFILE="$DIR/llama-server.pid"

if curl -sf -m 2 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q '"ok"'; then
  echo "arriba: /health ya responde en $PORT"
  exit 0
fi

# Cerrojo atómico con detección de huérfano: dos arranques simultáneos
# no lanzan dos motores; un cerrojo tras SIGKILL no bloquea para siempre.
LOCK="$DIR/serve.lock"
if [ -d "$LOCK" ]; then
  LPID="$(cat "$LOCK/pid" 2>/dev/null || true)"
  if [ -n "$LPID" ] && ps -p "$LPID" -o command= 2>/dev/null | grep -q llama-server; then
    echo "BLOQ: otro arranque en curso (pid $LPID)" >&2
    exit 1
  fi
  rm -rf "$LOCK"
fi
mkdir "$LOCK" || { echo "BLOQ: cerrojo irrecuperable ($LOCK)" >&2; exit 1; }
echo $$ >"$LOCK/pid"
trap 'rm -rf "$LOCK" 2>/dev/null' EXIT

nohup llama-server \
  -hf LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M \
  --reasoning off --temp 0 --port "$PORT" \
  >>"$LOG" 2>&1 &
PID=$!
echo "$PID" >"$PIDFILE"

# Espera de salud: la primera carga descarga el GGUF si no hay caché.
# Aborta temprano si el proceso muere durante la carga.
for _ in $(seq 1 240); do
  kill -0 "$PID" 2>/dev/null || { echo "BLOQ: el motor murió durante la carga; revisa $LOG" >&2; exit 1; }
  if curl -sf -m 2 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q '"ok"'; then
    echo "arriba: /health OK (pid $PID); log: $LOG"
    exit 0
  fi
  sleep 5
done

echo "BLOQ: sin salud tras 20 min; revisa $LOG" >&2
exit 1
