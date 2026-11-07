# Revisión de la TAREA I1-VS — Síntesis de voz en español (`llama-tts`) — 2026-11-06

## Encargo y superficie (capa humana)

Encargo del Operador (2026-11-06): «ronda adversarial para afinar y
procede, tienes aprobados commits, merges, pr push, etc segun convenga en
el avance». Ejecución de `TAREA I1-VS` de `PLAN LFM3-2` (`D-08` /
`ADR-007` aceptado, `D-09` con `D-10` implementada).

Produce:
- `docs/specs/SPEC-i1-vs-sintesis-voz.md`: especificación de
  `POST /v1/audio/speech` en el gateway loopback (`8092`).
- `src/gateway_core.py` y `src/gateway_http.py`: validación de frontera
  (`validar_payload_tts`: string `1..600` sin caracteres de control ni no
  imprimibles, `language: "es"`, `response_format: "wav"`, rechazo de
  claves extra como `voice`/`speaker_ref`), ejecución de `llama-tts` por
  archivo temporal `0600` (`-f`, jamás en `argv`), verificación del
  `sha256` de `llama-tts` y snapshot congelado, exclusión mutua sin cola
  (`503 overloaded`), validación estructural del WAV de salida con
  muestras no vacías y anuncio de `voz: true`, `audio: true`,
  `salida: ["texto", "audio"]` en `/v1/capabilities`.
- `tests/test_gateway_vs.py` (6 pruebas nuevas, suite `116 OK`),
  `tests/medir_tts_vs.py` (gate de ida-vuelta TTS -> ASR y memoria),
  `examples/cliente_i1.py` (`11/11 OK`) y evidencia en
  `docs/reviews/evidence/i1-vs-sesion/`.

## Ronda 1 — diff completo (subagente fresco `92c9a3bf`)

Veredicto inicial: **fix-and-retry** (1 HIGH, 3 MED, 1 LOW):

| ID | Sev. | Hallazgo | Disposición |
|---|---|---|---|
| H-1 | HIGH | `_sintetizar_wav` aceptaba un WAV de 44 bytes con `data(0)` sin muestras como `200 OK` en vez de `502 backend_error` | `validar_wav(datos, exigir_muestras=True)` exige `data > 0` y múltiplo de `canales * 2`; test en `test_vs4` |
| M-1 | MED | `OSError` en `tempfile.mkdtemp` / escritura de `prompt.txt` quedaba fuera del `try` interno y cerraba el socket sin JSON `502` | Creación y escritura del temporal incluidas dentro del `try ... except (OSError, SubprocessError)` -> `502 backend_error` JSON; test con `mock.patch` |
| M-2 | MED | `_resolver_entorno_tts` leía `LFM3_MODELO` y `LFM3_MMPROJ` del entorno | Eliminada lectura de variables de entorno; fijado directo a `SNAP_HF` congelado |
| M-3 | MED | `tests/medir_tts_vs.py` no verificaba `_comando_pid` en `_rss_motor_8091()` ni declaraba `procedencia` por frase | Verificación `llama-server` + `--port 8091` añadida y `procedencia` declarada en `FRASES_VS` |
| L-1 | LOW | Faltaba test unitario directo de `_resolver_entorno_tts` y `TimeoutExpired` | Añadido `test_vs4b_resolver_entorno_tts_verifica_hash_y_limpia_env` y subcaso `TimeoutExpired` |

## Ronda 2 — fixes verificados (subagente fresco `92c9a3bf`)

Reprodujo con vectores propios la corrección de H-1 (`502
invalid_tts_output` ante WAV de 44 bytes), M-1 (`502 tts_failed` y
`LOCK_TTS` liberado ante `ENOSPC`), M-2 (`SNAP_HF` fijo) y verificó la
suite y los 5 gates. Veredicto: **proceed** (con 1 LOW de actualizar las
cifras de la re-corrida en `registro-avance.md`, aplicado).

## Capa técnica

```text
id = i1-vs-sintesis-voz-2026-11-06
date = 2026-11-06
time_utc = 02:53:00Z
head_sha = f8eb30c67ca0687556713cb5a03a7d846c690b79
model = gemini-4-argon
STATE = OK
GATE = unittest 116 OK (6 nuevas VS; skipped=8 con motor vivo); TTS->ASR CER mediana 0.000 peor 0.000 PASS; RSS llama-tts 3094.5 MiB < 4 GiB y RSS motor 2216.0 MiB < 4 GiB; demo cliente 11/11; golden --rapido 11/11; 5/5 gates OK; git diff --check limpio
PENDING = ejecucion de I1-VR -> I1-VV -> I1-VX -> I1-VM -> I1-VC segun PLAN LFM3-2
DECISION = proceed
OPERATIONS = commit en rama feat/plan2-orientacion-e-i1-vs, merge a main y push (autorizados por el Operador en sesion)
AUTHORITY = encargo del Operador 2026-11-06 «ronda adversarial para afinar y procede, tienes aprobados commits, merges, pr push, etc segun convenga en el avance»; ADR-006; ADR-007 (D-08); D-09 con D-10
RISK = bajo-medio: nueva ruta POST /v1/audio/speech en loopback con texto por archivo 0600, exclusion mutua 503 sin cola y hash llama-tts verificado; contratos v1 intactos; rollback por revert
EVIDENCE
- RED 17 fallos (POST /v1/audio/speech ausente) -> pass (red.txt)
- gate TTS->ASR (mediana 0.000, peor 0.000) y memoria (RSS TTS 3094.5 MiB, RSS motor 2216.0 MiB) -> pass (tts_vs.txt/tts_vs.json)
- demo cliente 11/11 y golden --rapido 11/11 con motor vivo -> pass (demo-cliente.txt, golden.txt)
- ronda adversarial 1 fix-and-retry (1 HIGH WAV data(0), 3 MED, 1 LOW corregidos) -> pass
- ronda adversarial 2 sobre los fixes en contexto fresco: proceed -> pass
report_sha256 = 2178a1aec58915b0a7e2687caee2881697aab93c46717694c4a872dcfa721775
```
