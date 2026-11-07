#!/usr/bin/env bash
# Arranque orquestado del piloto privado HTTPS (Fase I2).
# Puertos:
# - 8091: motor llama-server (loopback interno)
# - 8092: gateway HTTP v2 con auth Bearer y colas por proyecto (loopback interno)
# - 8443: terminador TLS stdlib (interfaz privada para proyectos piloto)
# Cero dependencias externas; fail-closed en caso de error.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
LOCK="$DIR/serve_pilot.lock"
GATEWAY_LOG="$DIR/gateway.log"
TLS_LOG="$DIR/tls.log"
GATEWAY_PIDFILE="$DIR/gateway.pid"
TLS_PIDFILE="$DIR/tls.pid"
CERT_PEM="$ROOT/config/certs/cert.pem"

# 1. Cerrojo de concurrencia atómico
if [ -d "$LOCK" ]; then
  LPID="$(cat "$LOCK/pid" 2>/dev/null || true)"
  LCMD="$(ps -p "$LPID" -o command= 2>/dev/null || true)"
  if [ -n "$LCMD" ] && printf '%s\n' "$LCMD" | grep -q "serve_pilot.sh"; then
    echo "BLOQ: otro arranque del piloto en curso (pid $LPID)" >&2
    exit 1
  fi
  rm -rf "$LOCK"
fi
mkdir "$LOCK" || { echo "BLOQ: cerrojo irrecuperable ($LOCK)" >&2; exit 1; }
echo $$ >"$LOCK/pid"
trap 'rm -rf "$LOCK" 2>/dev/null' EXIT

# Fallo limpio en caso de interrupción durante el arranque
cleanup_on_error() {
  echo "BLOQ: fallo durante el arranque del piloto; abortando y limpiando..." >&2
  bash "$DIR/stop.sh" --all || true
  rm -rf "$LOCK" 2>/dev/null || true
  exit 1
}

echo "=== [1/4] Verificando motor en puerto 8091 ==="
bash "$DIR/serve.sh" || cleanup_on_error

echo "=== [2/4] Asegurando certificados locales TLS ==="
python3 -c "from pathlib import Path; from src.gateway_tls import asegurar_certificados_locales; asegurar_certificados_locales(Path('$ROOT/config/certs'))" || cleanup_on_error

echo "=== [3/4] Levantando Gateway HTTP v2 (puerto 8092 con autenticación) ==="
if lsof -nP -iTCP:8092 -sTCP:LISTEN 2>/dev/null | grep -q LISTEN; then
  if curl -sf -m 1 "http://127.0.0.1:8092/healthz" 2>/dev/null | grep -q '"ok"'; then
    echo "Gateway 8092 ya activo y saludable."
  else
    echo "BLOQ: puerto 8092 ocupado por un proceso que no responde /healthz" >&2
    cleanup_on_error
  fi
else
  export LFM3_AUTH_ENABLED=1
  export LFM3_GATEWAY_PORT=8092
  export LFM3_BACKEND="http://127.0.0.1:8091"
  nohup python3 "$ROOT/src/gateway_http.py" >>"$GATEWAY_LOG" 2>&1 &
  GW_PID=$!
  echo "$GW_PID" >"$GATEWAY_PIDFILE"
  
  INTENTO=0
  while [ "$INTENTO" -lt 15 ]; do
    if curl -sf -m 1 "http://127.0.0.1:8092/healthz" 2>/dev/null | grep -q '"ok"'; then
      break
    fi
    INTENTO=$((INTENTO + 1))
    sleep 0.5
  done
  if [ "$INTENTO" -eq 15 ]; then
    echo "BLOQ: Gateway 8092 no respondió en el tiempo asignado; revisa $GATEWAY_LOG" >&2
    cleanup_on_error
  fi
  echo "Gateway 8092 activo y autenticado (pid $GW_PID)."
fi

echo "=== [4/4] Levantando Terminador TLS (puerto 8443) ==="
if lsof -nP -iTCP:8443 -sTCP:LISTEN 2>/dev/null | grep -q LISTEN; then
  if curl -sf --cacert "$CERT_PEM" -m 1 "https://127.0.0.1:8443/healthz" 2>/dev/null | grep -q '"ok"'; then
    echo "Terminador TLS 8443 ya activo y saludable."
  else
    echo "BLOQ: puerto 8443 ocupado por un proceso ajeno o con certificado inválido" >&2
    cleanup_on_error
  fi
else
  export LFM3_TLS_PORT=8443
  export LFM3_GATEWAY_PORT=8092
  nohup python3 "$ROOT/src/gateway_tls.py" >>"$TLS_LOG" 2>&1 &
  TLS_PID=$!
  echo "$TLS_PID" >"$TLS_PIDFILE"
  
  INTENTO=0
  while [ "$INTENTO" -lt 15 ]; do
    if curl -sf --cacert "$CERT_PEM" -m 1 "https://127.0.0.1:8443/healthz" 2>/dev/null | grep -q '"ok"'; then
      break
    fi
    INTENTO=$((INTENTO + 1))
    sleep 0.5
  done
  if [ "$INTENTO" -eq 15 ]; then
    echo "BLOQ: Terminador TLS 8443 no respondió en el tiempo asignado; revisa $TLS_LOG" >&2
    cleanup_on_error
  fi
  echo "Terminador TLS 8443 activo y verificado con CA local (pid $TLS_PID)."
fi

echo "=== Piloto Privado HTTPS Activo ==="
echo "Endpoint: https://127.0.0.1:8443"
echo "Proyectos autorizados: proyecto-alpha, proyecto-beta"
