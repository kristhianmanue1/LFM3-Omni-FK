# Registro de avance — PLAN LFM3-2

Estado: vivo; una sección por iteración, transiciones con fecha y
evidencia. Procedencia: `docs/roadmap/iteraciones-servicio.md`
(§Registro de avance para ejecutores). Los estados son propuestos por
el agente con evidencia; la aceptación la decide el Operador.
`accepted_local` se abrevia en las filas sin repetir «propuesto»:
sólo cuenta como aceptación lo registrado por escrito. Los encargos
citados (p. ej. «…y despes aprobada la tarea») autorizan la ejecución
y anticipan la aprobación posterior del Operador; no son aceptación de
fase.

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
  **I1-V0, I1-VT, I1-VA, I1-VS, I1-VR, I1-VV, I1-VX, I1-VM e I1-VC**
  (I1-VM/VC constan en la tabla desde el 2026-11-06; commit
  `5a69110`). I0 e I1 conservan `accepted_local`.
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
| 2026-11-06 | I1-VS `accepted_local` (propuesto) | fddabbe | fixes aplicados; TTS->ASR CER mediana 0.000 peor 0.000 PASS; RSS llama-tts 3094.5 MiB < 4 GiB, RSS motor 2216.0 MiB < 4 GiB; demo 11/11; suite 116 OK; ronda 2 proceed; capabilities anuncia voz/audio |
| 2026-11-06 | I1-VR `implementing` → `verifying` | fddabbe + trabajo | RED 4 fallos (red.txt); GREEN: SSE sin buffering (stream=True) en gateway_http, cancelación hasta /slots y conversación N=5 con p95 primera voz 3.76 s <= 8.0 s; ronda 1 fix-and-retry (2 HIGH + 2 MED + 1 LOW corregidos) |
| 2026-11-06 | I1-VR `accepted_local` (propuesto) | commit de esta TAREA | fixes aplicados (cierre garantizado, /slots fail-closed, bloqueo 503 slot_not_released, línea <=64 KiB, TTS por cada frase); p95 3.76 s PASS; demo 13/13; suite 124 OK; ronda 2 proceed; capabilities anuncia streaming |
| 2026-11-06 | I1-VV `accepted_local` | 21650a1 | video corto data URI MP4 con ffprobe verificado por hash, cotas 16 MiB/10s/120f/1080p, suite 132 OK, gate 3/3 acierto 100%, demo 15/15; rondas proceed; capabilities anuncia video |
| 2026-11-06 | I1-VX `accepted_local` | 050891e | dialecto schema v2-ext (enum, min/max, array, sub-objetos prof 1), validación fail-closed de salida, gate percepción live 3/3 = 100% p95 0.87s, suite 150 OK; rondas proceed |
| 2026-11-06 | I1-VM `accepted_local` | 4ec42fd | servidor MCP local stdio v2 desacoplado vía gateway 8092 con cerrojo TTS 503 compartido; suite MCP 77 OK (40 v2 + 37 v1 intacto), demo cliente stdio; rondas proceed |
| 2026-11-06 | I1-VC `accepted_local` | 5003e4b | CLI unificado stdlib y adaptador local perfil D para robots/simuladores (deriva <=2s, deduplicación, secuencia y descarte fail-closed); suite 208 OK; simulador e2e live; rondas proceed |
| 2026-11-06 | I2-D `accepted_local` | commit de esta TAREA | diseño y formalización de arquitectura I2: SPEC-i2, ADR-009, dossier-operacion-i2, D-02/D-03/D-04 formalizadas; ronda 1 fix-and-retry subsanada; ronda 2 proceed; 5 gates OK |
| 2026-11-06 | I2-P `accepted_local` | 5fe4258 | implementación auth Bearer, tokens.json 0600, recarga en memoria, token bucket, fair queuing, terminador TLS stdlib, anti-SSRF; suite 232 OK (24 tests I2 nuevos); 5 gates OK; ronda 2 proceed |
| 2026-11-07 | I2-V `accepted_local` | 3a172d4 | vigilancia reproducible de ciclo de vida (src/vigilancia.py), presupuesto tiempo/bytes/red, máquina estados 10 estados con blocked, triaje temprano, sanitización 5 capas, 9 escenarios de ensayo OK, 19 tests nuevos (suite 251 OK); rondas 1 y 2 proceed |
| 2026-11-07 | I2-U `accepted_local` | commit de esta TAREA | piloto HTTPS privado activado (run/serve_pilot.sh con lock y fail-closed, run/stop.sh --all con rollback real, scope profile:d cerrado en gateway_http.py, demo cliente 5/5 OK, 12 tests nuevos suite 263 OK); rondas 1 y 2 proceed |

## I2 — Servicio web privado por invitación

- Estado actual: `accepted_local` (propuesto al Operador) para
  I2-D, I2-P, I2-V e I2-U.
- Owner: agente ejecutor (OpenCode / Antigravity). Reviewer: subagente
  con contexto fresco (ronda adversarial I2-D).
- Encargo: Operador, 2026-11-06 — «adelante» (ejecución de TAREA I2-D).
- Alcance de archivos: `docs/specs/SPEC-i2-piloto-privado.md`,
  `docs/adr/ADR-009-identidad-red-egreso-piloto-i2.md`,
  `docs/roadmap/dossier-operacion-i2.md`, `docs/roadmap/decisiones-servicio.md`,
  `docs/plans/PLAN-2-servicio-compartido.md`, `docs/reviews/`.
- Bloqueos: ninguno para diseño I2-D. Activación de red/código en I2-P.

## I3 — MCP remoto omnimodal

- Estado actual: `accepted_local` (propuesto al Operador).
- Procedencia de esta sección: añadida a posteriori (2026-11-09, tarea
  docs-current-state); las fases I3–I6 no registraron transiciones en
  su momento en este archivo. Se reconstruyen sólo desde commits y
  reviews locales, sin atribuir aceptaciones humanas no registradas.
- Encargo: Operador, 2026-11-07 — «adelante tienes comits, puesh,
  merges autorizados segun consideres en el abanse y despes aprobada la
  tarea» (citado en la review de la fase).
- Evidencia: commits `eb3c5fe` (I3-D), `ccab09e` (I3-M) y `1f3963f`
  (I3-U); review `../reviews/2026-11-i3-mcp-remote-omnimodal.md`
  (suite 275 OK, proceed); `docs/specs/SPEC-i3-mcp-remote.md` y
  ADR-010.

## I4 — Clientes SDK y perfiles W/D

- Estado actual: `accepted_local` (propuesto al Operador).
- Evidencia: commit `0069f35` (I4-C, I4-UI, I4-U); review
  `../reviews/2026-11-i4-clientes-perfiles-wd.md` (suite 288 OK,
  proceed); contrato `docs/contracts/handoff-frontexpert-v2.md`
  publicado en este repo. Límite: la adopción de la UI ocurre en
  frontExpert y sigue gateada por D-05 (pendiente) y encargo separado;
  el handoff no acredita UI ni adopción en ese repo.

## I5 — Trabajos largos en segundo plano (Perfil J)

- Estado actual: `accepted_local` (propuesto al Operador). El residual
  MED aceptado por escrito el 2026-11-08 quedó corregido en `599564b`;
  no está vigente.
- Evidencia: commit `c32f7de` y ola de correcciones (`920ba6a`,
  `1fa6e45`, `50f9a5b`, `b8ef913`); la review inicial (base `0069f35`)
  registró suite 299 OK
  (`../reviews/2026-11-i5-trabajos-largos-perfil-j.md`) y el cierre de
  la ola de correcciones, 376 tests OK (skipped=1) en dos pasadas
  (`../reviews/evidence/fix-i5-jobs-frontera/green-intento-4.txt`,
  2026-11-08, condiciones históricas). El Operador aceptó por escrito
  el residual MED (respuesta 202 sin despacho tras un OSError del
  worker) en
  `../reviews/evidence/fix-i5-jobs-frontera/aceptacion-riesgo.md`
  (commit `2c83934`). La corrección de atribución (`2c83934`) y
  `../reviews/evidence/fix-i5-jobs-frontera/disposicion-ronda4.md`
  registran que el Operador EXIGÍA para esta ola un proceed pre-merge
  de agy (Gemini, otra familia), que el proceed GLM de la ronda 4 —de
  la misma familia y sin excepción autorizada— no sustituye; la
  evidencia local conserva la exigencia, no la ocurrencia de ese
  proceed.
  La corrección del residual (`599564b`, PR #6) se integró el
  2026-11-09 por excepción puntual del Operador, SIN revisor fresco
  (cuota de agy agotada, 429):
  `../reviews/evidence/fix-i5-despacho/disposicion-excepcion-revisor.md`.

## I6 — Triaje y evaluación de modelos (condicional)

- Estado actual: `accepted_local` (propuesto al Operador) para la
  capacidad de triaje y evaluación; el plan la mantiene condicional por
  candidato o modalidad. Sin candidato evaluado ni promoción: baseline
  intacta.
- Evidencia: commit `60c6568` (I6-E, I6-U); review
  `../reviews/2026-11-i6-evaluacion-modelos.md` (suite 308 OK,
  proceed); `docs/specs/SPEC-i6-evaluacion-modelos.md` y ADR-013.

Límite común I3–I6: las cifras de suite de cada review se observaron
en un árbol de trabajo sobre la base de su `head_sha` (commit previo
al de la fase), no sobre el commit final; los commits acreditan la
implementación. La aceptación humana plena de cada iteración no consta
por escrito salvo lo anotado (residual I5, 2026-11-08, corregido en
`599564b`). El runtime vigente (motor 8091, gateway 8092, piloto 8443)
no se comprueba en este registro: su activación quedó documentada en su
fase y su estado actual corresponde al runbook.

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
