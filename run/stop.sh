#!/usr/bin/env bash
# Parada limpia de procesos del servicio LFM3-Omni (puertos 8091, 8092, 8443).
# SPEC I0 §7 y SPEC I2 §5.2: propiedad antes de disparo — sólo se mata un pid cuya
# línea de comando es realmente el binario o script correspondiente en este puerto.
# Un pid reciclado o un proceso ajeno que mencione el patrón sobrevive (SPEC I0 r18).
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$DIR/llama-server.pid"

es_proceso_servicio() {
  local PID="$1"
  local PUERTO="$2"
  [ -n "$PID" ] || return 1
  local CMD
  CMD="$(ps -p "$PID" -o command= 2>/dev/null || true)"
  [ -n "$CMD" ] || return 1
  case "$PUERTO" in
    8091)
      local BINARIO
      BINARIO="$(printf '%s' "$CMD" | cut -d' ' -f1)"
      case "${BINARIO##*/}" in
        llama-server) printf '%s\n' "$CMD" | grep -Eq -- "--port ${PUERTO}([[:space:]]|$)" ;;
        *) return 1 ;;
      esac
      ;;
    8092)
      printf '%s\n' "$CMD" | grep -Eq 'gateway_http\.py'
      ;;
    8443)
      printf '%s\n' "$CMD" | grep -Eq 'gateway_tls\.py'
      ;;
    *)
      return 1
      ;;
  esac
}

detener_puerto() {
  local PUERTO="$1"
  if [ "$PUERTO" = "8091" ] && [ -f "$PIDFILE" ]; then
    local PID
    PID="$(cat "$PIDFILE")"
    if es_proceso_servicio "$PID" "$PUERTO"; then
      kill "$PID" 2>/dev/null || true
    fi
    rm -f "$PIDFILE"
  fi

  for PID in $(lsof -nP -iTCP:"$PUERTO" -sTCP:LISTEN -t 2>/dev/null || true); do
    if es_proceso_servicio "$PID" "$PUERTO"; then
      kill "$PID" 2>/dev/null || true
    fi
  done

  for _ in 1 2 3; do
    if ! lsof -nP -iTCP:"$PUERTO" -sTCP:LISTEN 2>/dev/null | grep -q LISTEN; then
      echo "detenido: sin escucha en $PUERTO"
      return 0
    fi
    sleep 1
  done

  echo "BLOQ: el puerto $PUERTO sigue en escucha; revisa el dueño con lsof -iTCP:$PUERTO" >&2
  return 1
}

TARGET="${1:-8091}"
if [ "$TARGET" = "--all" ]; then
  detener_puerto 8443 || true
  detener_puerto 8092 || true
  detener_puerto 8091
else
  detener_puerto "$TARGET"
fi
