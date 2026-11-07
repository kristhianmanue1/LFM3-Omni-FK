# SPEC I1-VS — Síntesis de voz en español vía `llama-tts` en el gateway

Estado: activo al cerrar el gate de I1-VS. Procedencia: PLAN LFM3-2
TAREA I1-VS; ADR-006 (capabilities por modalidad), ADR-007 aceptado
(D-08: TTS vía `llama-tts --tts-lang es`; `/v1/realtime` fuera por
`ggml-org/llama.cpp#31689`), D-06a (prioridad voz), D-09 con D-10
implementada (I1-VT). Extiende SPEC-i1 y SPEC-i1-va.

## 1. Ruta y dialecto de petición (`POST /v1/audio/speech`)

Se añade `"POST /v1/audio/speech"` a `RUTAS_PERMITIDAS`. Cuerpo JSON
estricto (mismas cotas de transporte que `POST /v1/chat/completions`:
sin `Transfer-Encoding`, sin `Content-Encoding` comprimido, con
`Content-Length` <= `MAX_BODY_BYTES`):

- Claves permitidas en el objeto raíz: `"input"` (obligatoria),
  `"language"` (opcional, default `"es"`), `"response_format"`
  (opcional, default `"wav"`), `"model"` (opcional, string).
- Cualquier otra clave (incluidas `"voice"`, `"speaker_ref"`,
  `"speaker_file"`, `"speed"`, `"stream"`) -> 400 `unknown_field`
  (ADR-007: sin clonación de voz ni `speaker_ref`).
- `input`: string de `1..600` caracteres (`MAX_TTS_CHARS = 600`), con al
  menos un carácter imprimible no blanco (`strip()` no vacío), y **sin
  caracteres de control** (ningún carácter con `ord(c) < 32` o
  `ord(c) == 127`, incluidos `\n`, `\r`, `\t`, `\x00`). Si viola tipo,
  longitud o caracteres -> 400 `invalid_tts_input` antes de tocar el
  subproceso.
- `language`: sólo `"es"` -> otro valor da 400 `unsupported_field_value`.
- `response_format`: sólo `"wav"` -> otro valor da 400
  `unsupported_field_value`.

## 2. Ejecución segura de `llama-tts` y exclusión mutua (ADR-007)

- **Una síntesis a la vez, sin cola:** el gateway protege la síntesis
  con un cerrojo no bloqueante (`LOCK_TTS.acquire(blocking=False)`). Si
  ya hay una síntesis en curso, responde de inmediato **503
  `overloaded`** (`{"error": {"code": "overloaded", "message": ...,
  "request_id": ...}}`) sin lanzar subproceso ni encolar.
- **Entrega del texto por archivo `0600` (nunca en `argv`):** se crea un
  directorio temporal privado `0700` por petición (`tempfile.mkdtemp`),
  dentro de él `prompt.txt` con permisos `0600` (`O_CREAT | O_EXCL`,
  UTF-8) y ruta de salida `out.wav`. Se invoca `llama-tts` como lista de
  argumentos sin shell (`shell=False`):
  `[binario_tts, "-m", ruta_modelo, "-mm", ruta_mmproj, "--tts-lang",
  "es", "-f", prompt_path, "-o", wav_path]` con `--no-escape`, entorno
  saneado (variables `LLAMA_ARG_*` neutralizadas y `PATH` fijado al
  directorio del binario + `/usr/bin:/bin:/usr/sbin:/sbin`) y timeout
  de `120` s.
- **Verificación del binario y artefactos:** `llama-tts` se resuelve y
  su `sha256` se comprueba contra el hash inventariado en F0 §7
  (`b983acbd59f89df0da0cce9665c75366b94f5736331470fc73d2b8bb5c84c377`,
  overridable sólo en tests mediante inyección explícita del runner). Si
  el binario o los pesos faltan, el subproceso falla o el archivo de
  salida no es un WAV RIFF/WAVE válido (`len >= 44`, firma `RIFF..WAVE`
  y muestras no vacías) -> **502 `backend_error`**.
- **Limpieza garantizada:** en bloque `finally`, el directorio temporal
  (`prompt.txt` y `out.wav`) se elimina siempre antes de liberar el
  cerrojo y devolver la respuesta.
- **Respuesta exitosa:** HTTP `200`, `Content-Type: audio/wav`,
  `Content-Length`, `X-Request-Id` y `X-V2-Mode: tts-wav`, cuerpo con
  los bytes WAV generados.

## 3. Criterio de ida-vuelta TTS -> ASR y memoria (fijados ANTES de medir)

- **Ida-vuelta TTS -> ASR (`tests/medir_tts_vs.py`):** sobre 5 frases en
  español fijadas antes de medir, cada frase se sintetiza vía
  `POST /v1/audio/speech` en el gateway (`8092`), el WAV devuelto se
  convierte a 16 kHz mono PCM16 con `ffmpeg` (si su tasa difiere) y se
  transcribe vía `POST /v1/chat/completions` (`input_audio`) en el mismo
  gateway. Criterio de pase: **CER mediano <= 0.15 y ningún caso > 0.30**
  (misma función `cer` y normalización de `SPEC-i1-va`).
- **Memoria y swap (`REQ-5` / `B-T10` ampliado):** se mide el pico RSS
  del subproceso `llama-tts` (`/usr/bin/time -l` en macOS) con el motor
  `llama-server` (`8091`) vivo:
  - RSS del subproceso `llama-tts` < 4 GiB (`4 * 1024^3` bytes);
  - RSS de `llama-server` (`8091`) tras la síntesis < 4 GiB;
  - Swap global del host antes y después reportado explícitamente (sin
    crecimiento descontrolado).
- **Veredicto del Operador (oído humano):** registrado en P-9 de la
  evidencia previa («clara, un poco semi robotizada, buena pronunciación
  en español», `docs/reviews/evidence/plan2-ajuste-sesion/README.md`) y
  muestra WAV de la sesión archivada en `medios-binarios/`.

## 4. Capabilities al cerrar el gate (ADR-006 §1)

`GET /v1/capabilities` pasa a declarar:
- `entrada: ["texto", "imagen", "audio"]`
- `salida: ["texto", "audio"]`
- `transcripcion: true`, `voz: true`, `audio: true`
- `streaming: false`, `video: false` (siguen en `false` hasta cerrar
  `I1-VR` e `I1-VV`).

## 5. Matriz REQ-SPEC-test

| REQ | Propiedad | Verificación |
|---|---|---|
| VS1 | `POST /v1/audio/speech` válido entrega `audio/wav` RIFF/WAVE, usa `-f` con archivo `0600` (texto no en `argv`) y borra temporales | `test_gateway_vs::vs1` |
| VS2 | `input` vacío, >600 chars, con caracteres de control (`\n`, `\x00`), no-string o claves extra/`voice`/`speaker_ref` -> 400 sin lanzar `llama-tts` (contador TTS 0) | `test_gateway_vs::vs2*` |
| VS3 | concurrencia: segunda petición simultánea a `/v1/audio/speech` recibe 503 `overloaded` sin cola | `test_gateway_vs::vs3` |
| VS4 | fallo del subproceso, timeout o WAV inválido -> 502 `backend_error` y temporales limpios | `test_gateway_vs::vs4` |
| VS5 | capabilities anuncia `voz: true`, `audio: true`, `salida: ["texto", "audio"]` y mantiene `streaming`/`video` en `false` | `test_gateway_vs::vs5` |
| VS6 | ida-vuelta TTS -> ASR sobre 5 frases (CER mediano <= 0.15, peor <= 0.30) y pico RSS < 4 GiB con motor vivo | `tests/medir_tts_vs.py` |

## 6. Comandos exactos

```bash
python3.12 -m unittest tests.test_gateway_vs -v
bash run/serve.sh
python3.12 src/gateway_http.py &
python3.12 tests/medir_tts_vs.py docs/reviews/evidence/i1-vs-sesion/tts_vs.json
python3.12 examples/cliente_i1.py
```

## 7. Límites declarados

- Latencia de varios segundos por llamada (`llama-tts` carga el modelo en
  cada invocación; `ADR-007`). Una síntesis a la vez (`503` sin cola).
- Sólo español (`language: "es"`) y salida WAV (`response_format: "wav"`),
  sin streaming de audio ni clonación de voz.
