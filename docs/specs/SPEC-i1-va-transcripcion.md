# SPEC I1-VA — Transcripción en español vía input_audio

Estado: activo al cerrar el gate de I1-VA. Procedencia: PLAN LFM3-2
TAREA I1-VA; ADR-006 (enmienda de capabilities por modalidad), ADR-007
aceptado (D-08; ASR por el motor 8091), D-06a (prioridad voz→…),
encargo del Operador 2026-11-05. Extiende SPEC-i1 (gateway loopback):
lo no redefinido aquí rige SPEC-i1.

## 1. Parte de contenido input_audio (dialecto v2)

En `messages[].content[]` se admite la parte
`{"type": "input_audio", "input_audio": {"data": "<base64>", "format": "wav"}}`
— claves exactas, sin campos extra. `format` sólo `"wav"`. La parte
`audio_url` NO está admitida (con URL data:, http(s) o cualquier otra
forma → 400 `unknown_content_type` antes del motor, contador en 0):
el audio entra como datos, nunca como URL que el motor pudiera
resolver (guía 06 §5; ADR-006 §3).

## 2. Validación en frontera (antes del motor; fail-closed)

Sobre los bytes decodificados (base64 estricto, `invalid_audio` 400):

- Presupuesto de bytes: ≤ 4 MiB (`MAX_AUDIO_BYTES`).
- Estructura RIFF/WAVE: firma `RIFF…WAVE`, tamaño RIFF consistente con
  el archivo, chunks `fmt ` y `data` presentes, **únicos** (un segundo
  `fmt ` o `data` es ambigüedad para el motor → 400) y consistentes
  con el archivo (sin bytes sobrantes ni data truncado); `fmt ` PCM
  (formato 1), 16 bits, 1 o 2 canales, tasa 1–96000 Hz. Todo desvío →
  400 `invalid_audio`.
- Duración: bytes de `data` / (tasa·canales·2) ≤ 60 s
  (`MAX_AUDIO_SEGUNDOS`) → 400 `invalid_audio` si excede.

La parte válida se re-emite canónica y se proxifica al motor tal cual
(como el resto del dialecto). Errores siempre con `request_id`, sin
eco del payload.

## 3. Corpus sintético y umbral CER (fijados ANTES de medir)

`tests/corpus_va.json` declara las diez frases, los WAV (en
`tests/medios-binarios/`, patrón binario del gate)
sintetizados con `llama-tts` del artefacto congelado con su sha256, la
normalización (minúsculas, sin puntuación, espacios colapsados), el
CER (Levenshtein por carácter sobre la longitud de referencia) y el
criterio de pase: **CER mediano ≤ 0.10 y ningún caso > 0.25**. Medición
con `tests/medir_cer_va.py` contra el gateway con motor vivo; la
evidencia se archiva en la revisión de la TAREA.

## 4. Capabilities al cerrar el gate (ADR-006 §1)

`GET /v1/capabilities` pasa a declarar `entrada: [texto, imagen,
audio]` y `transcripcion: true`. `streaming`, `audio` (voz de salida),
`video` y `voz` siguen `false`: sólo se anuncia lo que su TAREA cerró.

## 5. Matriz REQ-SPEC-test

| REQ | Propiedad | Verificación |
|---|---|---|
| VA1 | input_audio válido atraviesa y llega al motor | `test_gateway_va::va1` (contador 1) |
| VA2 | WAV corrupto/truncado/sobrante, base64 inválido, chunks duplicados o tamaño RIFF falso → 400, contador 0 | `test_gateway_va::va2*` |
| VA3 | bytes > 4 MiB o duración > 60 s → 400, contador 0 | `test_gateway_va::va3` |
| VA4 | audio_url (data:/http) o claves extra/format != wav → 400, contador 0 | `test_gateway_va::va4` |
| VA5 | capabilities anuncia transcripcion y sigue sin voz/video | `test_gateway_va::va5` |
| VA6 | CER del corpus bajo el umbral fijado | `tests/medir_cer_va.py` (gate con motor vivo) |
| VA7 | cer/normalización correctos por unidad | `test_gateway_va::va7` |

## 6. Comandos exactos

```bash
python3.12 -m unittest tests.test_gateway_va -v
bash run/serve.sh
python3.12 src/gateway_http.py &          # 8092 (LFM3_GATEWAY_PORT)
python3.12 tests/medir_cer_va.py > docs/reviews/evidence/i1-va-sesion/cer.txt
python3.12 examples/cliente_i1.py
```

## 7. Límites declarados

- Sólo WAV PCM 16-bit (el contenedor que libmtmd consume sin pérdida
  de control); sin mp3/ogg/opus, sin audio de salida, sin streaming.
- El corpus es sintético (TTS del propio artefacto): acredita el
  circuito de transcripción del dialecto, no calidad ASR sobre voz
  humana arbitraria (eso pertenece a D-09/D-10 con sesiones reales).
- `/v1/audio/transcriptions` del motor NO se expone por el gateway:
  superficie cerrada (SPEC-i1 §2).
