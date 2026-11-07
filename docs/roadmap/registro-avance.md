# Registro de avance — PLAN LFM3-2

Estado: vivo; una sección por iteración, transiciones con fecha y
evidencia. Procedencia: `docs/roadmap/iteraciones-servicio.md`
(§Registro de avance para ejecutores). Los estados son propuestos por
el agente con evidencia; la aceptación la decide el Operador.

## I0 — Base local reparada

- Estado actual: `accepted_local` (propuesto al Operador; ver
  transiciones).
- Owner: agente ejecutor (GLM 5.3 Flash, OpenCode). Reviewer: subagente
  independiente con contexto fresco (ronda adversarial al cierre).
- Encargo: Operador, 2026-11-04 — «analiza y adelantes para primera
  iteracion» (adopta D-01 y habilita I0-R/I0-U; local, sin activación
  remota).
- Alcance de archivos permitidos: `run/serve.sh`, `run/stop.sh`,
  `tests/run_golden.py`, `tests/test_*.py`, `src/adapter_v2.py`,
  `scripts/inventario_motor.py`, `examples/`, `docs/specs/`,
  `docs/adr/ADR-004*`, `docs/roadmap/`, `docs/reviews/`, `README.md`
  (sólo si el cierre lo exige).
- Red: sólo loopback (motor 8091, adaptador 8092). Sin dependencias
  nuevas (ADR-004). Presupuesto: una corrida completa del motor por
  verificación; sin benchmarks de carga (I2).
- Bloqueos: ninguno para I0; D-02..D-07 siguen pendientes hasta sus
  gates (`docs/roadmap/decisiones-servicio.md`).

### Transiciones

| Fecha (UTC) | Estado | HEAD | Evidencia / razón |
|---|---|---|---|
| 2026-11-04 | `not_started` | 4572164 (base del plan) | plan persistido; encargo aún no dado |
| 2026-11-04 | `designing` | 59390ab | encargo recibido; SPEC/ADR/decisiones en curso |
| 2026-11-04 | `implementing` | 59390ab | RED de propiedades registrada; correcciones en curso |
| 2026-11-04 | `verifying` | 59390ab | GREEN completo (34 tests, golden 11/11, demo 7/7); ronda adversarial fresca: veredicto fix-and-retry (1 BLOCKER + 1 HIGH + 6 MED con repro) |
| 2026-11-04 | `accepted_local` (propuesto) | commit de esta TAREA | fixes aplicados y re-corridos (una regresión propia detectada y corregida por la re-corrida); 34 tests OK, golden 11/11, demo 7/7, 5 gates OK; rollback probado (stop/serve); sin activación remota |

### I1 — API común utilizable en loopback

- Estado actual: `accepted_local` (propuesto al Operador; ver
  transiciones).
- Owner: agente ejecutor (GLM 5.3 Flash, OpenCode). Reviewer: subagente
  independiente con contexto fresco.
- Encargo: Operador, 2026-11-04 — «adelante con pendientes» (tras
  cerrar I0 y su push autorizado para la sesión). Alcance: I1 local
  (loopback), sin exposición remota (D-02/D-03 siguen pendientes y no
  bloquean I1).
- Alcance de archivos: `src/gateway_core.py`, `src/gateway_http.py`,
  `src/adapter_v2.py` (fachada), `tests/test_gateway_i1.py`,
  `tests/test_adapter_v2.py` (sólo si el reorg lo exige),
  `examples/cliente_i1.py`, `docs/specs/SPEC-i1-*`, `docs/adr/ADR-005*`,
  `docs/roadmap/`, `docs/reviews/`.

### Transiciones

| Fecha (UTC) | Estado | HEAD | Evidencia / razón |
|---|---|---|---|
| 2026-11-04 | `not_started` | e0e7d8f | I0 cerrada; I1 sin encargo |
| 2026-11-04 | `designing` | e0e7d8f | encargo de pendientes; SPEC/ADR en curso |
| 2026-11-04 | `implementing` | e0e7d8f | RED de propiedades nuevas (i1-red.txt) |
| 2026-11-04 | `verifying` | e0e7d8f | GREEN (40 tests, golden 11/11, cliente 7/7); ronda adversarial 1: fix-and-retry (2 MED + 7 LOW) |
| 2026-11-04 | `accepted_local` (propuesto) | commit de esta TAREA | fixes aplicados; ronda adversarial 2: proceed con mutation testing; 5 gates OK; sin activación remota |

### I1-V — Modalidades locales del artefacto vigente

- Estado actual: `accepted_local` (propuesto al Operador) para
  **I1-V0, I1-VT, I1-VA e I1-VS**; I1-VR/VV/VX/VM/VC `not_started`. I0
  e I1 conservan `accepted_local`.
- Owner: agente ejecutor (GLM 5.3, OpenCode; ajuste del plan: Claude
  Opus 5.5, Claude Code). Reviewer: subagente con contexto fresco
  (ronda del ajuste: fix-and-retry -> proceed por relectura,
  docs/reviews/2026-11-plan2-ajuste-multimodal.md; rondas I1-V0 en
  docs/reviews/2026-11-i1-v0-inventario-bt8.md).
- Encargo: Operador, 2026-11-04 — integración multimodal en el PLAN
  LFM3-2 existente; «corre ronda adversarial del ajuste al plan para
  afinar y procede». Ejecución de I1-V0: Operador, 2026-11-05 —
  «Encargar I1-V0» (sesión OpenCode). Encargo de I1-VA e I1-VT (D-10):
  Operador, 2026-11-05, misma sesión.
- Bloqueos: ninguno para I1-VA e I1-VT. D-08 aceptada (2026-11-05);
  D-09 aceptada para gates con voz/cámara reales condicionada a D-10
  implementada (I1-VT); realtime nativo fuera por
  ggml-org/llama.cpp#31689.
- Evidencia de partida: docs/reviews/evidence/plan2-ajuste-sesion/ y
  sondas-Mac14-2-2026-11-04/ (tests/sondas_multimodal.py); de esta
  TAREA: docs/reviews/evidence/i1-v0-sesion/.

| Fecha (UTC) | Estado | HEAD | Evidencia / razón |
|---|---|---|---|
| 2026-11-04 | `not_started` | 310e7ff (base del ajuste) | tareas I1-V0..VV en plan; ADR-006/007 propuestos |
| 2026-11-05 | `implementing` | 9c0035b | encargo de I1-V0; RED de las tres propiedades (evidence/i1-v0-sesion/red.txt) |
| 2026-11-05 | `verifying` | 9c0035b + trabajo | GREEN: golden 12/12 con B-T8 corregido; unittest 78 OK; 5 gates OK; inventario reproduce hashes; ciclo vivo stop/serve con PATH fijado; ronda adversarial 1: fix-and-retry (H-1..H-4) |
| 2026-11-05 | `accepted_local` (propuesto) | commit de esta TAREA | fixes de la ronda 1 aplicados y re-verificados (golden 12/12); ronda adversarial 2 sobre los fixes: proceed; v1 sin cambio |
| 2026-11-05 | I1-V0 publicada en `origin/main` | 74733ee (rebase sobre f7b0d92) | push autorizado por el Operador; rebase por avance del remoto (sesión Dell G7, PR 1); hook pre-push fijado a Python ≥ 3.12 (a9aa1ff) tras rechazo con 3.9 |
| 2026-11-05 | I1-VA: encargo (`not_started` → `designing`) | a9aa1ff | encargo del Operador; D-08 aceptada y D-09 (reales con D-10) registradas; SPEC con corpus y umbral CER antes de medir |
| 2026-11-05 | I1-VT (D-10): encargo (`not_started`) | a9aa1ff | TAREA añadida al PLAN; condición de los gates de I1-V con voz/cámara reales |
| 2026-11-05 | I1-VT `implementing` → `verifying` | 48111d1 + trabajo | RED 7/7 (módulo ausente); GREEN: src/transcripciones.py, cableado en live_voice y conversacion_voz_local, nota D-10 en los tres realtime; 8 pruebas nuevas |
| 2026-11-05 | I1-VT `accepted_local` (propuesto) | commit de esta TAREA | unittest 100 OK; 5/5 gates; ronda adversarial 1 proceed (MED-1 + 6 LOW corregidos) y ronda 2 proceed (3 LOW de pulido aplicados); limitación declarada: realtime sin retención hasta I1-VR |
| 2026-11-05 | I1-VA `implementing` → `verifying` | c16ab5f + trabajo | RED 12 fallos; SPEC-i1-va + corpus/umbral fijados antes de medir; validación WAV estructural en frontera; ronda adversarial 1 fix-and-retry (H1 data duplicado + 3 MED) |
| 2026-11-05 | I1-VA `accepted_local` (propuesto) | commit de esta TAREA | fixes aplicados; CER mediana 0.000 peor 0.116 PASS; demo 9/9; suite 110 OK; rondas 2 y 3 proceed; capabilities anuncia transcripcion |
| 2026-11-06 | orientación ADR-008 (`D-11`) | f8eb30c | ADR-008 y tareas I1-VX, I1-VM, I1-VC añadidas; ronda adversarial doble fix-and-retry -> proceed |
| 2026-11-06 | I1-VS `implementing` → `verifying` | f8eb30c + trabajo | RED 17 fallos (red.txt); GREEN: POST /v1/audio/speech con texto por archivo 0600 (-f), exclusión mutua 503 sin cola, hash llama-tts verificado; ronda 1 fix-and-retry (H-1 WAV data(0) + 3 MED + 1 LOW) |
| 2026-11-06 | I1-VS `accepted_local` (propuesto) | commit de esta TAREA | fixes aplicados; TTS->ASR CER mediana 0.000 peor 0.000 PASS; RSS llama-tts 3094.5 MiB < 4 GiB, RSS motor 2216.0 MiB < 4 GiB; demo 11/11; suite 116 OK; ronda 2 proceed; capabilities anuncia voz/audio |

## Salida prevista

Cierre propuesto como `accepted_local` sólo con: conformidad de la
matriz H en verde, demo desde cliente HTTP real, revisión fresca sin
HIGH/BLOCKER, cinco gates OK, v1 y I0 pasando. Si algo falla:
`verifying` con pendientes explícitos.


## Evidencia de hardware Dell G7 7700 (2026-11-04)

Se ejecutó la instalación WSL2/CUDA y la batería sobre el artefacto
congelado. Informe: `../reviews/2026-11-dell-g7-7700.md`; retoma:
`../retomar-dell-g7.md`. Hubo pruebas personales autorizadas de voz,
video y conversación realtime inglesa, confirmadas por el Operador.
La sesión sin límite global terminó al detectar goodbye, con seis turnos.

Estas observaciones no cambian estados I1-V ni aceptan ADR-006/007.
No se publican medios personales ni transcripciones inexistentes.
D-10 registra conservación privada de transcripciones para la próxima
verificación; implementar y probar esa retención antes de retomarla.
