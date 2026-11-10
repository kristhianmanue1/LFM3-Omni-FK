# Mandato del revisor — fix-i5-despacho (agy)

Eres el REVISOR fresco de otra familia (agy, Gemini). Contexto fresco:
evalúa sólo lo que ves en el worktree. **Sólo lectura**: no modifiques
archivos, no hagas commit, no arranques el motor ni servicios, sin red
externa.

Worktree: `/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-fix-i5-despacho`
Rama `agent/fix-i5-despacho`, base `main` `7fd40fc`. Cambios SIN commit:
revisa `git diff` y los archivos nuevos sin seguimiento.

## Tarea

Revisión adversarial defect-first de la tarea `fix-i5-despacho` (ola 3):
cierre del residual MED aceptado por el Operador (2026-11-08) según su
prescripción literal, más LOW-1 (alineación de `_resolver_rival`) y
LOW-7 (reloj inyectable).

## Lee, en este orden

1. `docs/reviews/evidence/fix-i5-despacho/mandato.md`;
2. `docs/reviews/evidence/fix-i5-jobs-frontera/aceptacion-riesgo.md`
   (§El caso y §Seguimiento — la prescripción que debió ejecutarse tal
   cual) y `disposicion-ronda4.md`;
3. el diff completo (`git diff` + `git status --short`) y cada archivo
   tocado en su estado final (`src/jobs_manager.py`,
   `src/jobs_recovery.py`, `tests/test_jobs_boundary_i5.py`,
   `tests/test_jobs_despacho_i5.py` — nuevo);
4. la evidencia del expediente: `red.txt`, `green.txt`;
5. `docs/reviews/evidence/fix-i5-despacho/informe.md` del ejecutor.

## Verifica contra el código, no contra la prosa

Cada afirmación verificable del informe contra la salida real (grep de
identificadores, lectura de las líneas citadas). Puntos mínimos:

- prescripción punto 1: los dos disparadores del `except OSError` del
  worker terminan en `_reconciliar_abandono` (relectura bajo
  `self.lock`; si sigue `queued`, sale de `_en_cola`);
- prescripción punto 3: si la relectura falla, fail-closed preservado;
- `_reclamar` propaga `OSError` real y sólo devuelve `None` por
  contención de flock (`EWOULDBLOCK`/`EAGAIN`);
- LOW-1: `_resolver_rival` pasa por `_asegurar_despacho` (ramas vivas
  uniformes);
- LOW-7: `reloj` inyectable gobierna barrido, purga y deadlines; sin
  `time.monotonic` ni `datetime.now` sueltos en el manager/mixin; la
  comparación del barrido usa `.total_seconds()` (el HIGH propio del
  ejecutor);
- garantías de `fix-i5-jobs-frontera` preservadas (despacho tras doble
  fallo, purga bajo lock, D1 flock, RFC 8785, persistencia atómica);
- RED corresponde: los tests 27-31 fallaban por la razón correcta y el
  GREEN ejecuta exactamente una vez (marcador del backend == 1);
- alcance respetado (los archivos tocados están en el mandato §4; la
  partida del módulo de tests nuevo está documentada como Decisión 1);
- límites de tamaño: `jobs_manager.py` en 800/800 — verificar que no se
  pasa ni un renglón y que el gate pasa.

Puedes ejecutar comandos de sólo lectura y los módulos de test
(`python3.12 -m unittest tests.test_jobs_i5 tests.test_jobs_boundary_i5
tests.test_jobs_despacho_i5 tests.test_jobs_intento2_i5
tests.test_jobs_intento3_i5 tests.test_jobs_intento4_i5`); nunca la
suite completa ni `test_piloto_live_i2`.

## Veredicto

Clasifica cada hallazgo nuevo: BLOCKER | HIGH | MED | LOW, con evidencia
`archivo:línea`. BLOCKER o HIGH existentes ⇒ `blocked`. Cierra con el
veredicto (`proceed | blocked`), los conteos por severidad, un párrafo
por hallazgo y, en una línea separada, el marcador: la palabra FIN, un
espacio, la palabra rev-despacho, un espacio y el número total de
hallazgos nuevos.
