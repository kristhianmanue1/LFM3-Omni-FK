# Revisión de la TAREA I1-VT — 2026-11-05

## Encargo y superficie (capa humana)

Encargo del Operador (2026-11-05, sesión OpenCode): «Encargar D-10» —
implementar la retención privada de transcripciones aceptada en D-10
antes de repetir pruebas personales auditables. Ejecutor: GLM 5.3
(OpenCode). D-09 quedó aceptada para los gates con voz/cámara reales
condicionada a esta tarea.

Produce: `src/transcripciones.py` (módulo stdlib, JSONL 0600 por
sesión bajo `docs/reviews/evidence/privado/transcripciones/`, fuera de
Git), cableado en los dos ejemplos con texto de turno nativo
(`examples/wsl/live_voice.py`, `examples/conversacion_voz_local.py`),
nota «D-10 pendiente» en los tres flujos realtime
(`continuous_unlimited`, `continuous_english`, `realtime_english`: sus
bucles sólo consumen eventos de audio y no exponen texto de turno; no
sirven como sesiones auditables hasta cablearlos, trabajo que queda
para I1-VR), y `tests/test_transcripciones.py` (ocho pruebas).

## RED → GREEN

- RED (`evidence/i1-vt-sesion/red.txt`): siete pruebas, todas fallidas
  — el módulo no existía y el cableado estaba ausente.
- GREEN: módulo + cableado + notas; se añadieron las pruebas de
  no-colisión de sesión y confinamiento durante la ronda 1 (ocho
  finales).

## Ronda 1 — diff completo (subagente fresco)

Verificó en vivo permisos (0600/0700 umask-independientes),
fail-closed sin escrituras parciales, gate de consentimiento antes de
toda la retención, hash sin conservar audio, suites y gates. Veredicto
**proceed** con 1 MED y 6 LOW:

| ID | Sev. | Hallazgo | Disposición |
|---|---|---|---|
| MED-1 | MED | identificadores y claves nuevos en español (ADR-015: sin excepciones) | renombrados a inglés (new_session/record_turn/user_text/reply/params; claves JSONL) |
| LOW-1 | LOW | colisión de sesión dentro del mismo segundo UTC | sufijo aleatorio os.urandom(3) |
| LOW-2 | LOW | record_turn no confinaba a la raíz privada | confinamiento con root= (default ROOT); rutas fuera → ValueError |
| LOW-3 | LOW | ventana escritura→chmod en archivo preexistente | chmod 0600 antes de escribir si existe |
| LOW-4 | LOW | open() sin context manager en el hash del wav | with-open |
| LOW-5 | LOW | pruebas de cableado sólo textuales | aceptado con nota (la lectura de ronda aporta la profundidad) |
| LOW-6 | LOW | ASR vacío abortaba con traceback crudo | mensaje controlado + fin de sesión (fail-closed) |

## Ronda 2 — fixes (subagente fresco)

Verificó los seis fixes uno a uno (incluye prueba viva del
confinamiento con seis vectores, entre ellos un symlink dentro de la
raíz apuntando fuera: rechazado) y las suites (8/8 y 100 OK).
Veredicto **proceed** con tres LOW de pulido, aplicados tras el
veredicto y re-verificados con la suite completa y los gates (sin
cambio semántico): claves de params en inglés (`language`, `flow`),
identificadores de tests consistentes con el estilo de cada archivo
(`RAIZ` se conserva: patrón de los catorce archivos de test del repo) y
bucle de escritura completa contra escrituras cortas de POSIX.

## Limitación declarada

Los flujos realtime no retienen: capturar su texto exige rediseñar sus
bucles de eventos (queda para I1-VR). Hasta entonces no son sesiones
auditables D-10; la nota vive en sus docstrings y en el registro de
avance.

## Capa técnica

```text
id = i1-vt-retencion-transcripciones-2026-11-05
date = 2026-11-05
time_utc = 06:16:00Z
head_sha = 48111d170ff5d33713fd5fa60e8c7be12610c600
model = glm-5-3
STATE = OK
GATE = unittest 100 OK (8 nuevos de retención; skipped=8 por fixture con motor vivo); 5/5 gates OK; ruta de lectura 1799/1800; py_compile 5/5 ejemplos; git diff --check limpio
PENDING = publicar (autorizacion por operacion); retencion en flujos realtime pendiente de I1-VR; margen de ruta de lectura: 1 linea
DECISION = proceed
OPERATIONS = commit en rama feat/i1-vt-retencion-transcripciones; merge a main y push pendientes de autorizacion por operacion
AUTHORITY = encargo del Operador 2026-11-05 «Encargar D-10» (sesion OpenCode); D-10 aceptada 2026-11-04; D-09 gates con reales condicionada a D-10
RISK = bajo: modulo nuevo stdlib aislado, dos ejemplos cableados tras consentimiento, tres docstrings con nota; docs/contracts sin cambio; rollback por revert
EVIDENCE
- RED 7/7 contra motor sin modulo ni cableado -> pass (red.txt)
- fixture sintetico contra la raiz real: JSONL 0600 completo y git check-ignore OK -> pass
- confinamiento verificado en vivo por el revisor (6 vectores incluido symlink) -> pass
- ronda adversarial 1: proceed con MED-1+6 LOW corregidos -> pass
- ronda adversarial 2 sobre los fixes: proceed; 3 LOW de pulido aplicados y re-verificados -> pass
report_sha256 = f6e5722ac5fbb3870f046eacc1723295b49303bf2423ed056086e0e013ae9d85
```
