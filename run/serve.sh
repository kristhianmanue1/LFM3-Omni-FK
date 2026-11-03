#!/usr/bin/env bash
# Arranque del motor LFM3-Omni según el runbook de ADR-001.
# Puerto 8091, solo localhost (CERRADA-6); greedy; no-reasoning.
set -euo pipefail

PORT=8091
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$DIR/llama-server.log"
PIDFILE="$DIR/llama-server.pid"

if curl -sf -m 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  echo "arriba: /health ya responde en $PORT"
  exit 0
fi

nohup llama-server \
  -hf LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M \
  --reasoning off --temp 0 --port "$PORT" \
  >>"$LOG" 2>&1 &
echo $! >"$PIDFILE"

# Espera de salud: la primera carga descarga el GGUF si no hay caché.
for _ in $(seq 1 240); do
  if curl -sf -m 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    echo "arriba: /health OK (pid $(cat "$PIDFILE")); log: $LOG"
    exit 0
  fi
  sleep 5
done

echo "BLOQ: sin salud tras 20 min; revisa $LOG" >&2
exit 1
