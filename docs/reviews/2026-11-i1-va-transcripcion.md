# Revisión de la TAREA I1-VA — 2026-11-05

## Encargo y superficie (capa humana)

Encargo del Operador (2026-11-05, sesión OpenCode): «Encargar I1-VA» —
transcripción en español vía `input_audio` en el chat del gateway.
Ejecutor: GLM 5.3 (OpenCode). Motor congelado sin cambio; ADR-006 §1
(capabilities por modalidad), ADR-007 aceptado (D-08).

Produce: parte `input_audio` del dialecto v2 con validación estructural
de WAV en frontera (`src/gateway_core.py`: 4 MiB, 60 s, un solo
`fmt `/`data`, tamaño RIFF consistente, PCM 16-bit, fail-closed),
SPEC nuevo (`docs/specs/SPEC-i1-va-transcripcion.md`), corpus sintético
y umbral CER fijados antes de medir (`tests/corpus_va.json` + diez WAV
TTS en `tests/medios-binarios/`), medidor del gate
(`tests/medir_cer_va.py`), diez pruebas nuevas
(`tests/test_gateway_va.py`), `chat_transcripcion` en el cliente de
referencia y capabilities anunciando `transcripcion` con `entrada`
+`audio`.

## Orden declarado: umbral antes de medir

Corpus (frases, hashes, método, criterio «CER mediana ≤ 0.10 y ningún
caso > 0.25») fijado en `tests/corpus_va.json` ANTES de la primera
medición; tras la reubicación de los WAV (gate de binarios) el corpus
sufrió un retoque de rutas y la medición se REPITIÓ contra el árbol
final para que la evidencia postdate al corpus (M3 de la ronda 1).

## Ronda 1 — diff completo (subagente fresco)

Reprodujo CER, hashes y capabilities en vivo. Veredicto fix-and-retry:

| ID | Sev. | Hallazgo | Disposición |
|---|---|---|---|
| H1 | HIGH | `data` duplicado evadía el tope de duración (sólo el primer data contaba; probado contra el motor: 1,6 s real + 55 s de silencio pasaban y el motor lo procesaba) | segundo `data` → 400 siempre; test va2c |
| M1 | MED | tamaño RIFF nunca verificado | RIFF == len-8 o 400 |
| M2 | MED | gates.txt archivaba un BLOQ intermedio | evidencia regenerada contra el árbol final |
| M3 | MED | corpus retoñado tras cer.txt (rutas) | CER re-medido tras el retoque |
| L1..L3 | LOW | literales de umbral; «» sin quitar; tabla >80 col | umbrales numéricos en el corpus; normalizar completa; prosa ≤80 (filas de tabla, estilo del repo) |

## Ronda 2 — fixes (subagente fresco)

Reconstruyó los vectores de H1/M1 de forma independiente (tres
variantes → 400; controles sanos pasan) y re-midió el CER en vivo con
salida idéntica a la archivada. Veredicto **proceed** con:

| ID | Sev. | Hallazgo | Disposición |
|---|---|---|---|
| MED-1 | MED | `if data:` por truthiness: data(0) + data(real) pasaba | bandera `visto_data` (ronda 3) |
| LOW-1 | LOW | filas de tabla §5 >80 col | estilo vigente del repo (tablas no miden columnas) |
| INFO-1 | INFO | proceso ajeno PID 15398 (gateway python3.9 en 49832, del 2026-11-04) | reportado al Operador; intacto |

## Ronda 3 — delta MED-1 (subagente fresco)

Bandera verificada con vectores propios (vacío+real, real+vacío,
doble vacío → todos 400; controles sanos pasan) y suite completa.
`data(0)` único pasa: WAV degenerado sin ambigüedad ni evasión de
presupuesto (máximos, no mínimos, declara el SPEC). Veredicto
**proceed**.

## Resultado del gate CER (motor vivo)

Mediana 0.000, peor 0.116 (corpus-07: «cinco» transcrito «5»), diez
casos, criterio declarado antes de medir → **PASS**
(`evidence/i1-va-sesion/cer.txt|json`).

## Capa técnica

```text
id = i1-va-transcripcion-2026-11-05
date = 2026-11-05
time_utc = 11:50:00Z
head_sha = c16ab5ffee5b10e2c87b515cd313b1dc5d7bb3a2
model = glm-5-3
STATE = OK
GATE = unittest 110 OK (10 nuevas VA; skipped=8 por fixture con motor vivo); CER mediana 0.000 peor 0.116 PASS con umbral fijado antes de medir; demo cliente 9/9; 5/5 gates OK; ruta de lectura 1799/1800; git diff --check limpio
PENDING = publicar (autorizacion por operacion); retencion en flujos realtime (I1-VR); proceso ajeno PID 15398 (gateway python3.9 del 2026-11-04) reportado al Operador; margen de ruta de lectura: 1 linea
DECISION = proceed
OPERATIONS = commit en rama feat/i1-va-transcripcion; merge a main y push pendientes de autorizacion por operacion
AUTHORITY = encargo del Operador 2026-11-05 «Encargar I1-VA» (sesion OpenCode); ADR-006 (enmienda capabilities); ADR-007 aceptado (D-08); D-06a
RISK = medio-bajo: frontera del gateway ampliada (audio) con validacion estructural estricta y adversarial triple; motor y contratos v1 sin cambio; /v1/audio/transcriptions del motor sigue sin exponerse; rollback por revert
EVIDENCE
- RED 12 fallos (input_audio ausente) -> pass (red.txt)
- gate CER con corpus sintetico TTS y umbral prefijado -> pass (cer.txt/cer.json)
- vectores adversariales de H1/M1/MED-1 rechazados antes del motor, contador 0 (rondas 2-3, reproducidos por revisores) -> pass
- demo cliente 9/9 con transcripcion exacta del corpus-01 -> pass (demo-cliente.txt)
- ronda adversarial 1 fix-and-retry (H1+3 MED+3 LOW corregidos) -> pass
- ronda 2 proceed + ronda 3 proceed (delta MED-1 con vectores propios) -> pass
report_sha256 = ef1e2c4356807e36879c37ea0f38dd4d75e2b90346eca29149de524bc02455f4
```
