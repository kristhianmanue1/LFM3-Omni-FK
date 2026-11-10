#!/usr/bin/env bash
# Arranque del motor LFM3-Omni según el runbook de ADR-001.
# Puerto 8091, solo localhost (CERRADA-6); greedy; no-reasoning.
# SPEC I0 §7: host explícito, entorno adversario neutralizado,
# cerrojo con dueño vivo identificable y readiness de modelo efectivo.
set -euo pipefail

# PATH del llamador con los directorios de sistema GARANTIZADOS al
# final (revisión agy 2026-11-10: en un PATH mínimo, dirname/grep/
# curl fallaban antes de cualquier diagnóstico fail-closed). Se AÑADE
# al final, jamás se antepone ni se sustituye: el fixture hermético
# necesita su bin_dir primero para que sus sustitutos ganen (SPEC I0
# r16, entorno adversario sin perder hermeticidad).
PATH="$PATH:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH

PORT=8091
HOST=127.0.0.1
MODELO_ID="LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M"
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$DIR/llama-server.log"
PIDFILE="$DIR/llama-server.pid"
LOCK="$DIR/serve.lock"
BUDGET="${LFM3_WAIT_BUDGET:-240}"

# El curl queda anclado desde el inicio (revisión agy 2026-11-10,
# hallazgo MED): el atajo idempotente y el readiness usan el mismo
# binario resuelto del entorno del llamador; en un PATH mínimo, un
# curl desnudo abortaría con 127 antes del diagnóstico fail-closed.
CURL_BIN="$(command -v curl 2>/dev/null || true)"
if [ -z "$CURL_BIN" ] && [ -x /usr/bin/curl ]; then
  CURL_BIN=/usr/bin/curl
fi
if [ -z "$CURL_BIN" ] || [ ! -x "$CURL_BIN" ]; then
  echo "BLOQ: sin curl para el readiness del motor" >&2
  exit 1
fi

if "$CURL_BIN" -sf -m 2 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q '"ok"'; then
  # Atajo idempotente: un servicio ya arriba sólo cuenta si sirve el
  # modelo efectivo registrado (SPEC I0 r17/r22).
  INTENTO=0
  while [ "$INTENTO" -lt 2 ]; do
    if "$CURL_BIN" -sf -m 2 "http://127.0.0.1:$PORT/v1/models" 2>/dev/null \
        | grep -q "$MODELO_ID"; then
      echo "arriba: /health y modelo efectivo OK (ya estaba en $PORT)"
      exit 0
    fi
    INTENTO=$((INTENTO + 1))
    sleep 1
  done
  echo "BLOQ: $PORT ya responde /health pero sin el modelo efectivo registrado" >&2
  exit 1
fi

# Puerto ocupado por un proceso ajeno (listener sin /health del motor):
# no lanzar nada y fallar cerrado (SPEC I0 r15).
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | grep -q LISTEN; then
  echo "BLOQ: puerto $PORT ocupado por un proceso ajeno" >&2
  exit 1
fi

# Cerrojo atómico: el dueño vivo se identifica por el comando del
# SCRIPT (serve.sh + este directorio), no por un grep del binario del
# motor. Un pid muerto o ajeno (reciclado) se recupera (SPEC I0 r13/r14).
if [ -d "$LOCK" ]; then
  LPID="$(cat "$LOCK/pid" 2>/dev/null || true)"
  LCMD="$(ps -p "$LPID" -o command= 2>/dev/null || true)"
  if [ -n "$LCMD" ] \
     && printf '%s\n' "$LCMD" | grep -q "serve.sh" \
     && printf '%s\n' "$LCMD" | grep -q "$DIR"; then
    echo "BLOQ: otro arranque en curso (pid $LPID)" >&2
    exit 1
  fi
  rm -rf "$LOCK"
fi
mkdir "$LOCK" || { echo "BLOQ: cerrojo irrecuperable ($LOCK)" >&2; exit 1; }
echo $$ >"$LOCK/pid"
trap 'rm -rf "$LOCK" 2>/dev/null' EXIT

# Entorno adversario: LLAMA_ARG_* del host no debe alterar el runbook
# registrado (SPEC I0 r16).
for V in $(env | sed -n 's/^\(LLAMA_ARG_[A-Za-z0-9_]*\)=.*/\1/p'); do
  unset "$V"
done

# Motor fijado por ADR-014 (par 2: llama.cpp master 54cde710 construido
# de fuente; el fix de realtime #31689 no existe en la bottled 0.9.0).
# Escalera de resolución con guard de identidad (ronda adversarial
# 2026-11-10, hallazgos BLOCKER-1/HIGH-1 del expediente motor-2-31689):
#   1) LFM3_MOTOR_BIN (override explícito),
#   2) binario fijado HERMANO del repo (producción),
#   3) legado command -v (sólo hermeticidad de tests con árbol
#      reubicado en fixture; emite AVISO: no es el par declarado).
# Las piernas 1 y 2 exigen SHA-256 igual al registrado (el par 2 real;
# LFM3_MOTOR_SHA_REGISTRADO lo ancla en fixtures herméticos). La
# pierna 3 no exige hash pero nunca pasa en silencio.
# llama-tts/ffmpeg/ffprobe siguen anclados por ADR-006 §4 y resuelven
# desde /opt/homebrew/bin (integridad del inventario).
SHA_REGISTRADO="${LFM3_MOTOR_SHA_REGISTRADO:-352c59e362dee5cf97bbbfbc63c0ab711a7c2c42053b1e33ae4abdb6e1d91564}"
MOTOR_BIN="${LFM3_MOTOR_BIN:-}"
LEGADO=0
if [ -n "$MOTOR_BIN" ] && [ ! -x "$MOTOR_BIN" ]; then
  echo "BLOQ: LFM3_MOTOR_BIN apunta a un binario no ejecutable: $MOTOR_BIN" >&2
  exit 1
fi
if [ -z "$MOTOR_BIN" ]; then
  CANDIDATO="$DIR/../../llamacpp-candidate-31689/src/build/bin/llama-server"
  if [ -x "$CANDIDATO" ]; then
    MOTOR_BIN="$CANDIDATO"
  else
    MOTOR_BIN="$(command -v llama-server)" || {
      echo "BLOQ: sin motor ADR-014 ni llama-server en PATH" >&2
      exit 1
    }
    LEGADO=1
    echo "AVISO: motor legacy de PATH ($MOTOR_BIN); no es el par 2 de ADR-014" >&2
  fi
fi
if [ "$LEGADO" -eq 0 ]; then
  HASH_REAL="$(shasum -a 256 "$MOTOR_BIN" | awk '{print $1}')"
  if [ "$HASH_REAL" != "$SHA_REGISTRADO" ]; then
    echo "BLOQ: hash del motor difiere del registrado (ADR-014): $MOTOR_BIN" >&2
    exit 1
  fi
fi
MOTOR_BIN_DIR="$(cd "$(dirname "$MOTOR_BIN")" && pwd)"
MOTOR_BIN="$MOTOR_BIN_DIR/$(basename "$MOTOR_BIN")"
# CURL_BIN ya quedó anclado al inicio del script (atajo idempotente y
# readiness usan el mismo binario; hallazgo MED de la revisión agy).
export PATH="$MOTOR_BIN_DIR:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

nohup "$MOTOR_BIN" \
  -hf LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M \
  --reasoning off --temp 0 --tts-lang es \
  --host "$HOST" --port "$PORT" \
  >>"$LOG" 2>&1 &
PID=$!
echo "$PID" >"$PIDFILE"

# Espera de readiness: salud DEL MOTOR y modelo efectivo (/v1/models)
# (SPEC I0 r17). La primera carga descarga el GGUF si no hay caché.
INTENTO=0
while [ "$INTENTO" -lt "$BUDGET" ]; do
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "BLOQ: el motor murió durante la carga; revisa $LOG" >&2
    rm -f "$PIDFILE"
    exit 1
  fi
  if "$CURL_BIN" -sf -m 2 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q '"ok"'; then
    if "$CURL_BIN" -sf -m 2 "http://127.0.0.1:$PORT/v1/models" 2>/dev/null \
        | grep -q "$MODELO_ID"; then
      echo "arriba: /health y modelo efectivo OK (pid $PID); motor: $MOTOR_BIN; log: $LOG"
      exit 0
    fi
    echo "aviso: /health OK pero modelo efectivo distinto; sigo esperando" >&2
  fi
  INTENTO=$((INTENTO + 1))
  sleep 5
done

echo "BLOQ: sin readiness (salud + modelo) tras $BUDGET intentos; revisa $LOG" >&2
rm -f "$PIDFILE"
exit 1
