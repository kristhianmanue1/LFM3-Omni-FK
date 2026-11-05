# Revisión de la TAREA I1-V0 — 2026-11-05

## Encargo y superficie (capa humana)

Encargo del Operador (2026-11-05, sesión OpenCode): «Encargar I1-V0».
Alcance exacto del plan: inventario de ffmpeg/ffprobe/llama-tts con
versión y hash, PATH fijado en `serve.sh` y B-T8 reescrito a
`input_audio` aceptado / `audio_url` rechazado; v1 sin cambio.
Ejecutor: GLM 5.3 (OpenCode). Hardware: MacBook Air M2 (Mac14,2), 16 GB.
Motor congelado sin cambio (ADR-001); ADR-006 §4 (propuesto) ampara el
PATH fijado.

Archivos: `run/serve.sh`, `scripts/inventario_motor.py`,
`scripts/MANIFEST.json`, `tests/run_golden.py`, `tests/golden/casos.json`,
`tests/test_ciclo_arranque.py`, `docs/f0-analisis-y-requerimientos.md`
(§7, registro congelado), `README.md` (descripción de B-T8),
`docs/plans/PLAN-2-servicio-compartido.md` (checkboxes I1-V0),
`docs/roadmap/registro-avance.md`, esta revisión y su evidencia
(`evidence/i1-v0-sesion/`).

Hallazgo propio durante el GREEN: el inventario falló cerrado al anclar
el PATH al directorio resuelto del motor (Cellar versionado, sin
ffmpeg); se ancló al directorio lógico de `command -v` (prefix
estable), el mismo criterio que `serve.sh`. El fail-closed hizo su
trabajo antes que la ronda adversarial.

## RED → GREEN

- RED (motor vivo, `evidence/i1-v0-sesion/red.txt`): `input_audio` →
  200 contradice la limitación documentada; `serve.sh` sin PATH fijado;
  inventario sin ffmpeg/ffprobe/llama-tts.
- GREEN: B-T8 reescrito (propiedad estructural; el CER se mide en
  I1-VA con corpus y umbral en SPEC); PATH fijado con test r16b
  (directorio envenenado no llega al motor); inventario ampliado.

## Ronda 1 — diff completo (subagente fresco)

Verificó en vivo: PATH del proceso real del motor, RED creíble del fix
(arnés con script viejo/nuevo), inventario reproduce hashes, golden,
gates, MANIFEST, v1 sin cambio, convenciones. Veredicto: fix-and-retry.

| ID | Sev. | Hallazgo | Disposición |
|---|---|---|---|
| H-1 | HIGH | `casos.json` citaba este registro, inexistente aún | este archivo viaja en el mismo commit |
| H-2 | MED | README aún describía B-T8 como limitación vigente | reescrito: input_audio aceptado, audio_url 400 |
| H-3 | LOW | runner no verificaba el mensaje del 400 | chequeo `unsupported content[].type`; golden re-corrido 12/12 |
| H-4 | LOW | r16b duplicaba la lista de directorios del sistema | comentario: la duplicación es la alarma, no deuda |

## Ronda 2 — fixes (subagente fresco)

Verificó las cuatro disposiciones contra el estado real (incluye
re-ejecución del golden `--rapido`: 11/0 con B-T8 en verde, e
inventario fresco reproduciendo artefactos y hashes idénticos) y el
diff completo contra la base: nada tocado fuera de lo declarado,
`docs/contracts/` sin cambio. Veredicto: **proceed**, con tres LOW:

| ID | Sev. | Hallazgo | Disposición |
|---|---|---|---|
| N-1 | LOW | timestamps manuscritos en cabeceras de evidencia | corregidos a fecha sin hora |
| N-2 | LOW | registro de avance pre-escribía este veredicto | quedó exacto al emitirse proceed; anotado como práctica |
| N-3 | LOW | test_g2 de test_gateway_i1.py flaky (un solo recv), preexistente | fuera de alcance; backlog con RED antes del fix |

## Capa técnica

```text
id = i1-v0-inventario-bt8-2026-11-05
date = 2026-11-05
time_utc = 04:18:00Z
head_sha = 9c0035bbd831822f9dcc4894d3619e2ac3546cc0
model = glm-5-3
STATE = OK
GATE = golden 12 pass 0 fail (B-T8 corregido, mensaje del 400 verificado); unittest 78 OK (skipped=8: fixture de ciclo se salta con motor vivo; test_ciclo_arranque 8/8 OK con puerto libre); 5/5 gates OK; ruta de lectura 1799/1800; git diff --check limpio
PENDING = D-08 y D-09 del Operador; ADR-006/007 propuestos; I1-VA..VV not_started; margen de ruta de lectura: 1 linea; backlog: test_g2 flaky preexistente (N-3)
DECISION = proceed
OPERATIONS = commit en rama feat/i1-v0-inventario-bt8; merge a main y push pendientes de autorizacion por operacion
AUTHORITY = encargo del Operador 2026-11-05 «Encargar I1-V0» (sesion OpenCode, seleccion explicita entre opciones)
RISK = bajo: inventario ampliado, PATH fijado en serve.sh (probado con motor real y stub), un caso del golden reescrito y documentos; v1 sin cambio; rollback por revert
EVIDENCE
- RED de las tres propiedades contra motor vivo -> pass (red.txt)
- inventario x2 reproduce hashes; F0 §7 registra los mismos -> pass
- ciclo vivo stop/serve; PATH del pid real = prefix motor + sistema -> pass (arranque.txt)
- golden completo 12 pass 0 fail re-corrido tras cada fix -> pass (golden.txt)
- unittest 78 OK; test_ciclo_arranque 8/8 con puerto libre (r16b incluido) -> pass
- ronda adversarial 1 fix-and-retry con H-1..H-4 corregidos -> pass
- ronda adversarial 2 sobre los fixes: proceed (LOW N-1..N-3 dispuestos) -> pass
report_sha256 = 77a81b9ef53f29e2d822ed4f1637b655069152a7cf38cd2b3adbb065be9ec95b
```
