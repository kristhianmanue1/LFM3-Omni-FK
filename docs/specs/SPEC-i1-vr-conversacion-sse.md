# SPEC I1-VR — Conversación local por turnos con SSE de texto y voz por frase

Estado: activo al cerrar el gate de I1-VR. Procedencia: PLAN LFM3-2
TAREA I1-VR; ADR-006 aceptado (enmienda de ADR-005: SSE sobre
`ThreadingHTTPServer` stdlib permitido en loopback y `streaming: true` en
capabilities al cerrar el gate); ADR-007 aceptado (síntesis frase a frase
con `llama-tts --tts-lang es`); D-10 aceptada (retención privada de
transcripciones por turno en `src/transcripciones.py`). Extiende
SPEC-i1, SPEC-i1-va y SPEC-i1-vs.

## 1. Dialecto de streaming en `POST /v1/chat/completions`

- Se añade `"stream"` a `CLAVES_TOP` de `src/gateway_core.py`.
- `stream` es opcional; cuando aparece, debe ser booleano (`bool`):
  cualquier otro tipo (`1`, `"true"`, `null`, lista) -> 400
  `unsupported_field_value` antes de tocar el motor (contador en 0).
- `stream: false` (o ausente) conserva íntegro el comportamiento síncrono
  de I0/I1 (`application/json`).
- **Incompatibilidad con `response_format` (`json_schema`):** la
  validación de salida estructurada contra schema cerrado exige el JSON
  completo antes de responder (`06` §5, SPEC-i0 §5). Por tanto,
  `stream: true` combinado con `response_format` no nulo se rechaza en
  la frontera con **400 `unsupported_field_value`** («streaming no
  compatible con response_format json_schema») y contador del motor en 0.

## 2. Transporte SSE sin buffering y cancelación hasta el motor (ADR-006 §2)

- Cuando `stream: true` pasa la validación de frontera, el gateway abre
  conexión HTTP hacia el backend (`POST /v1/chat/completions`, timeout
  `BACKEND_TIMEOUT_S`). Si el backend no responde `200`, falla cerrado con
  **502 `backend_error`** (`application/json`) antes de abrir stream SSE.
- Si el backend responde `200`, el gateway envía cabeceras:
  `HTTP/1.1 200 OK`, `Content-Type: text/event-stream; charset=utf-8`,
  `Cache-Control: no-cache`, `X-Accel-Buffering: no`, `X-Request-Id`,
  `X-V2-Mode: sse-passthrough`, y `Connection: close` (`close_connection =
  True`).
- **Sin buffering:** el gateway lee línea a línea del socket del backend
  (`resp.readline(MAX_SSE_LINE_BYTES + 1)` con cota `64` KiB por línea) y
  escribe y hace `flush()` inmediato en `self.wfile` por cada línea
  recibida, hasta encontrar `data: [DONE]` o EOF.
- **Cancelación y confirmación de liberación de slot ante desconexión:**
  1. Un cerrojo de slot de streaming (`LOCK_STREAM_SLOT`) y un indicador
     de confirmación pendiente (`_SLOT_PENDIENTE`) garantizan que ninguna
     nueva inferencia (`stream: true` o `stream: false`) reutilice el cupo
     antes de que una desconexión o corte sin `data: [DONE]` haya
     confirmado la liberación en el motor (ADR-006 §2).
  2. Si la escritura en `self.wfile` (incluida `end_headers()`) lanza
     `BrokenPipeError`, `ConnectionResetError`, `OSError` o
     `HTTPException`, o si el stream termina sin `data: [DONE]`, el
     gateway cierra siempre el socket hacia el backend (`resp.close()`) en
     el bloque `finally`, lo que provoca en `llama-server` la cancelación
     de la tarea (`cancel task` / `release`).
  3. Antes de habilitar el cupo para otra petición,
     `_esperar_liberacion_slot` consulta `GET /slots` del backend (con
     reintentos cortos de 25 ms hasta `2.0` s) exigiendo una lista no
     vacía donde todos los elementos tengan `is_processing is False`. Si
     el slot sigue sin confirmar liberación, las peticiones entrantes a
     `/v1/chat/completions` se rechazan fail-closed con **503
     `overloaded`** (`detail: "slot_not_released"`).

## 3. Conversación local por turnos, marca de fin de turno y umbrales (`p95`, `N`)

Fijados **ANTES de medir** (`PLAN-2` TAREA I1-VR,
`iteraciones-servicio.md` §I1-V):

- **Número de turnos (`N`):** `N = 5` turnos consecutivos sobre fixtures
  sintéticos versionados en `tests/medios-binarios/` (`corpus-01.wav` a
  `corpus-05.wav` de `tests/corpus_va.json`, sin micrófono ni voz humana).
- **Marca de fin de turno (`t_eot`):** instante exacto (`time.monotonic()`)
  en que el cliente dispone del WAV de entrada del turno listo para enviar
  al gateway (`POST /v1/chat/completions` con `input_audio`).
- **Flujo por turno (100 % vía gateway `8092`):**
  1. `t_eot = time.monotonic()`.
  2. Transcripción del WAV del turno vía `POST /v1/chat/completions`
     (`input_audio`, `stream: false`) en `8092` -> `user_text`.
  3. Respuesta del asistente en conversación acumulada (`historial` con
     `role: system` + turnos previos + `user_text`) vía
     `POST /v1/chat/completions` (`stream: true`, `max_tokens: 96`) en
     `8092`.
  4. Segmentación incremental por frases a medida que llegan los eventos
     `data: {...}` del SSE (corte en `[.!?…](\s|$)` con mínimo 12
     caracteres imprimibles o al cierre `[DONE]`).
  5. Cada frase producida en el turno se sintetiza frase por frase vía
     `POST /v1/audio/speech` en `8092`. El instante en que termina de
     recibirse el WAV válido de la **primera frase** es `t_first_voice`.
  6. Latencia de primera voz del turno:
     `latencia_primera_voz_s = t_first_voice - t_eot` (incluye ASR + TTFT y
     primera frase SSE + síntesis `llama-tts` de la primera frase).
  7. Retención privada por turno (`D-10`): cada turno registra en una
     sesión creada con `transcripciones.new_session()` el `user_text`,
     `reply`, `params` y `hashes` (`input_wav` y `first_tts_wav`).
- **Umbral de pase fijado antes de medir:**
  - `N = 5` turnos completados sin error HTTP ni cruce de sesiones;
  - **`p95` de `latencia_primera_voz_s` <= `8.0` s** (y máximo por turno
    <= `8.0` s) en el hardware baseline MacBook Air M2;
  - Archivo JSONL de la sesión `D-10` con modo `0600`, exactamente `N = 5`
    líneas válidas bajo `docs/reviews/evidence/privado/transcripciones/` y
    `git status` limpio (excluido por `.gitignore`).

## 4. Capabilities al cerrar el gate (ADR-006 §1)

`GET /v1/capabilities` pasa a declarar:
- `streaming: true`
- `video: false` (única modalidad local aún en `false` hasta cerrar
  `TAREA I1-VV`).

## 5. Matriz REQ-SPEC-test

| REQ | Propiedad | Verificación |
|---|---|---|
| VR1 | `stream: true` entrega eventos SSE incrementalmente sin buffering y con `X-V2-Mode: sse-passthrough`; `stream: false` conserva JSON | `test_gateway_vr::vr1` |
| VR2 | `stream` no booleano o `stream: true` + `response_format` -> 400 `unsupported_field_value` antes del motor (contador 0) | `test_gateway_vr::vr2` |
| VR3 | desconexión del cliente a mitad del SSE cierra el stream al backend y espera confirmación de liberación de slot antes de soltar el cupo | `test_gateway_vr::vr3` |
| VR4 | dos sesiones concurrentes/consecutivas de conversación y retención `D-10` no cruzan turnos, historiales ni archivos JSONL `0600` | `test_gateway_vr::vr4` |
| VR5 | capabilities anuncia `streaming: true` y mantiene `video: false` | `test_gateway_vr::vr5` |
| VR6 | medición sobre `N = 5` turnos por gateway `8092`: `p95` de primera voz <= `8.0` s, cancelación en motor vivo (`cancel task` / `/slots` libre) y `D-10` íntegro | `tests/medir_conversacion_vr.py` |

## 6. Comandos exactos

```bash
python3.12 -m unittest tests.test_gateway_vr -v
bash run/serve.sh
python3.12 src/gateway_http.py &
python3.12 tests/medir_conversacion_vr.py docs/reviews/evidence/i1-vr-sesion/conversacion_vr.json
python3.12 examples/cliente_i1.py
```

## 7. Límites declarados

- SSE sólo para texto libre (`POST /v1/chat/completions` sin
  `response_format`). La voz se sintetiza frase por frase vía
  `POST /v1/audio/speech` (WAV completo por frase, sin streaming de bytes
  PCM).
- Un hilo stdlib por stream activo; concurrencia gobernada por el cerrojo
  de confirmación de liberación de slot ante desconexión.
