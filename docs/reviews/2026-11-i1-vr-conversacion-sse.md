# Revisión de la TAREA I1-VR — Conversación local por turnos con SSE y voz — 2026-11-06

## Encargo y superficie (capa humana)

Encargo del Operador (2026-11-06): «ronda adversarial para afinar y
procede, tienes aprobados commits, merges, pr push, etc segun convenga en
el avance». Ejecución de `TAREA I1-VR` de `PLAN LFM3-2` (`ADR-006` enmienda
`ADR-005` permitiendo SSE de texto en loopback y cancelación hasta el
motor; `ADR-007` voz por frase; `D-10` retención privada de turnos).

Produce:
- `docs/specs/SPEC-i1-vr-conversacion-sse.md`: especificación de `stream:
  true` SSE de texto sin buffering en `POST /v1/chat/completions`,
  cancelación de tarea ante desconexión hasta confirmación en `/slots`,
  y conversación local de `N = 5` turnos sobre fixtures sintéticos con
  latencia de primera voz `p95 <= 8.0 s`.
- `src/gateway_core.py` y `src/gateway_http.py`: validación estricta de
  `stream` (`bool`), incompatibilidad de `stream: true` con
  `response_format` (400 antes del backend), stream SSE línea a línea con
  cota de seguridad `MAX_SSE_LINE_BYTES = 64 * 1024`, cierre garantizado
  del backend `resp.close()`, confirmación fail-closed de `/slots` libres
  antes de permitir nueva inferencia (`503 slot_not_released` si no se
  confirma) y anuncio de `streaming: true` en `/v1/capabilities`.
- `tests/test_gateway_vr.py` (8 pruebas nuevas, suite `124 OK`),
  `tests/medir_conversacion_vr.py` (gate de `N = 5` turnos, síntesis frase
  por frase, aislamiento `D-10` y desconexión en motor vivo),
  `examples/cliente_i1.py` (`13/13 OK`) y evidencia en
  `docs/reviews/evidence/i1-vr-sesion/`.

## Ronda 1 — diff completo (subagente fresco `ea091dcc`)

Veredicto inicial: **fix-and-retry** (2 HIGH, 2 MED, 1 LOW):

| ID | Sev. | Hallazgo | Disposición |
|---|---|---|---|
| H-1 | HIGH | Desconexión durante `end_headers()` o fin sin `[DONE]` fugaba `resp` y omitía `/slots` | `try ... finally: resp.close()` envuelve headers y stream; `vio_done` rastrea `[DONE]`; test en `test_vr3` |
| H-2 | HIGH | `_esperar_liberacion_slot` no era fail-closed; peticiones `stream: false` saltaban `LOCK_STREAM_SLOT` con slot ocupado | Exige lista no vacía con `is_processing is False`; `_SLOT_PENDIENTE` y `LOCK_STREAM_SLOT` protegen `stream: true` y `false` con 503 `slot_not_released`; test en `test_vr3c` |
| M-1 | MED | `resp.readline()` leía sin cota de bytes | `MAX_SSE_LINE_BYTES = 64 * 1024` con `readline(limit)` y corte seguro; test en `test_vr3d` |
| M-2 | MED | `medir_conversacion_vr.py` sólo sintetizaba la frase 0 | Sintetiza todas las frases por turno (`frases_tts`); verificado en `conversacion_vr.json` |
| L-1 | LOW | Prosa >80 cols en spec y `sesion_b` quedaba en disco | Líneas ajustadas y `sesion_b.unlink()` en `finally` |

## Ronda 2 — fixes verificados (subagente fresco `88035af4`)

Auditoría sobre los 5 hallazgos con pruebas unitarias específicas y suite
completa. Veredicto: **proceed** (todos los hallazgos cerrados con PASS).

## Capa técnica

```text
id = i1-vr-conversacion-sse-2026-11-06
date = 2026-11-06
time_utc = 03:26:00Z
head_sha = fddabbe36b4a24e1c947733b8aca2354d68fb951
model = gemini-3-8-flash
STATE = OK
GATE = unittest 124 OK (8 nuevas VR; skipped=8 con motor vivo); conversacion N=5 turnos p95 primera voz 3.76 s <= 8.0 s PASS; cancelacion SSE en motor vivo con /slots liberado; sesion D-10 0600 aislada; demo cliente 13/13; golden --rapido 11/11; 5/5 gates OK; git diff --check limpio
PENDING = ejecucion de I1-VV -> I1-VX -> I1-VM -> I1-VC segun PLAN LFM3-2
DECISION = proceed
OPERATIONS = commit en rama feat/i1-vr-conversacion-sse, merge a main y push a origin (autorizados por el Operador en sesion)
AUTHORITY = encargo del Operador 2026-11-06 «ronda adversarial para afinar y procede, tienes aprobados commits, merges, pr push, etc segun convenga en el avance»; ADR-006; ADR-007; D-09 con D-10
RISK = bajo-medio: stream SSE sin buffering y cancelacion de tareas hasta el motor en loopback; exclusion mutua y verificacion fail-closed de /slots ante desconexion; contratos v1 intactos; rollback por revert
EVIDENCE
- RED 4 fallos (streaming no soportado en I0/I1) -> pass (red.txt)
- gate conversacion N=5 turnos p95 3.76 s <= 8.0 s y cancelacion en motor vivo -> pass (conversacion_vr.txt/conversacion_vr.json)
- demo cliente 13/13 y golden --rapido 11/11 con motor vivo -> pass (demo-cliente.txt, golden.txt)
- ronda adversarial 1 fix-and-retry (2 HIGH, 2 MED, 1 LOW corregidos) -> pass
- ronda adversarial 2 sobre los fixes en contexto fresco: proceed -> pass
report_sha256 = cfdb35aa5183bd6261de8679d4fdba5ff4575b43129ce84c7ab137cea38fc6a0
```
