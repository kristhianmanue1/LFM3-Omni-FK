# Mandato del ejecutor — fix-i5-despacho, intento 1

Eres el EJECUTOR (opencode, GLM). No uses `codex`, `herdr` ni `hc`.
Trabajas SÓLO en este worktree
(`/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-fix-i5-despacho`,
rama `agent/fix-i5-despacho`, base `main` `7fd40fc`).
**Tarea material**: aplican los disparadores de `04` §5.3.

## 1. Contexto y decisión vigente

El residual MED de I5 fue **aceptado por escrito por el Operador**
(2026-11-08) con seguimiento obligatorio en ESTA tarea. La prescripción
exacta está en
`docs/reviews/evidence/fix-i5-jobs-frontera/aceptacion-riesgo.md`
(§Seguimiento) y debes ejecutarla tal cual. Los LOW pendientes están en
`docs/reviews/evidence/fix-i5-jobs-frontera/disposicion-ronda4.md`.

## 2. Lee completos, en este orden

- `AGENTS.md` y lo que manda leer, incluido
  `docs/ai-agent-guide/06-componentes-con-llm.md`;
- `docs/ai-agent-guide/04-ejecucion-y-verificacion.md`;
- `docs/specs/SPEC-i5-jobs.md`;
- `docs/adr/ADR-012-trabajos-largos-persistencia-idempotencia.md`;
- `docs/contracts/perfiles-servicio-v2.md` §J;
- `src/jobs_manager.py` (completo), `src/jobs_recovery.py`,
  `src/jobs_storage.py`, `src/canonical_json.py`;
- `tests/test_jobs_i5.py` y `tests/test_jobs_boundary_i5.py`;
- `docs/reviews/evidence/fix-i5-jobs-frontera/aceptacion-riesgo.md` y
  `disposicion-ronda4.md`.

## 3. Hallazgos a cerrar (datos; el capitán confirmó las anclas contra
`main` `7fd40fc`)

**[RESIDUAL-MED] `202` sin despacho tras `OSError` en la ventana
desencolar → persistir `running`.**

Estado hoy (`src/jobs_manager.py`): `_reclamar` (:488) con
`except OSError` (:495, :499); worker `except OSError` (:593);
`_marcar_running` (:534); `_asegurar_despacho` (:176); conjunto en
memoria `_en_cola` (:123, :189-191, :349, :692). Si cualquier `OSError`
cae entre retirar el job de `work_queue` y persistir `running`, el job
queda `queued` en disco, fuera de la cola y dentro de `_en_cola`: el
reintento con la misma clave de idempotencia responde `202` sin avance.

Corrección — prescripción EXACTA del Operador:

1. Si se abandona un job retirado de la cola sin haber persistido
   `running` (`_reclamar` devuelve `None` por `OSError`, o salta el
   `except OSError` del worker), releer el job bajo `self.lock`.
2. Si sigue `queued`, sacarlo de `_en_cola` para que el siguiente
   reintento lo reencole.
3. Si la relectura también falla, conservar el comportamiento actual,
   que es fail-closed.

Tests con inyección de `OSError` en cada transición de esa ventana: el
siguiente reintento debe reencolar y ejecutar (o terminar en fallo
explícito), jamás un `202` eterno.

**[LOW-1] `_resolver_rival` (:352, llamada en :323) responde `202` sin
pasar por `_asegurar_despacho`.** Bajo D1 (instancia única por
`jobs_dir` con flock) es inalcanzable; la disposición de la ronda 4 manda
ALINEARLA con `_asegurar_despacho` o anotarla como defensiva exclusiva de
D1. Elige, prueba lo alcanzable y documenta la elección en el informe.

**[LOW-7] Reloj no inyectable.** `time.monotonic()` fijo en
`jobs_manager.py:130` y `jobs_recovery.py:71-73` (barrido, purga,
deadlines). Inyecta el reloj (parámetro de constructor con valor real por
defecto) y reescribe los tests de tiempo para usar reloj falso, sin
pausas reales.

Preserva explícitamente las garantías ya cerradas en
`fix-i5-jobs-frontera`: despacho garantizado en reintento tras doble
fallo (`_asegurar_despacho` + `_en_cola`), purga con estado recargado
bajo lock, instancia única por `jobs_dir` con flock (D1), idempotencia
RFC 8785 y persistencia atómica. La suite existente de
`test_jobs_i5`/`test_jobs_boundary_i5` debe seguir en verde.

## 4. Alcance

Permitido:

- `src/jobs_manager.py`;
- `src/jobs_recovery.py`, sólo lo del reloj y el barrido si la
  prescripción lo toca;
- `tests/test_jobs_boundary_i5.py` (tests nuevos aquí);
- este expediente (`docs/reviews/evidence/fix-i5-despacho/`).

`tests/test_jobs_i5.py` sólo si un test existente necesita adaptarse al
comportamiento corregido.

Fuera de alcance: todo lo demás. En particular:

- `src/jobs_storage.py` y `src/canonical_json.py`: úsalos, no los
  cambies (si hiciera falta, BLOQ con tu recomendación);
- `src/gateway_http.py`, `src/gateway_core.py`: no los toques;
- SPEC, ADR y contratos: si el código obliga a cambiar el contrato,
  anótalo como decisión en el informe, no lo edites;
- `run/`, `scripts/`, `skevi-gate.json`, `AGENTS.md`, `.skevi/`.

## 5. Prohibido

- arrancar el motor, `run/serve.sh`, `run/stop.sh`, gateways reales o
  servicios;
- exponer `/jobs` (decisión vigente: no se expone; D3 cifrado bloquea);
- `kill`, `pkill` o barridos sobre procesos reales;
- red externa (sin `gh`, sin `curl` externo);
- commit, push, stash o ramas;
- editar la configuración de los gates.

Usa `python3.12` para todos los tests y gates (runtime del proyecto;
`python3` del sistema es 3.9 y no sirve). Los tests usan siempre un
`data_dir` temporal y un backend falso en un puerto efímero; nunca
`run/jobs` ni 8091. **No ejecutes la suite completa**: este worktree
conserva `tests/test_piloto_live_i2.py`, que ejecuta `run/stop.sh` y
`run/serve.sh` reales y está prohibido. Ejecuta los módulos concretos de
§4 y lista antes con `grep -rl jobs_manager tests/` cuáles otros tocan
el módulo.

## 6. Método (`04` §3 y `06` §2)

1. **RED primero**: un test por propiedad que falle hoy — inyección de
   `OSError` en cada transición de la ventana, reencolado verificable en
   el siguiente reintento, rival homologado, reloj falso en
   barrido/purga/deadline. Guarda la salida en `red.txt`.
2. **GREEN**: corrige. Guarda `green.txt` con los módulos de §5 dos
   veces, y `lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(8091|8092|8443) '`
   antes y después.
3. Los 3 gates del `AGENTS.md`, `git diff --check` y
   `git status --porcelain`.
4. Ronda adversarial propia sobre tu diff con el catálogo
   `.skevi/review-defect-catalog.md`. Después habrá un revisor fresco de
   otra familia (agy, Gemini), ordenado por el Operador.

## 7. Informe y cierre

Escribe `informe.md` en este expediente con la capa técnica que verifica
el gate (fence `text` con
`id/date/time_utc/head_sha/model/STATE/GATE/EVIDENCE/PENDING` y
`report_sha256` canónico del bloque, excluyendo la línea del propio
hash), y:

- la disposición de cada hallazgo (`fixed | justified`, con evidencia);
- los cambios por archivo;
- las propiedades con `pass | fail | inconclusive`;
- los riesgos;
- las decisiones para el Operador (cada una con tu recomendación:
  opciones con la recomendada primero, por qué con evidencia y qué cuesta
  la otra). No hagas commit.

Al terminar, responde una sola línea: la palabra FIN, un espacio, la
palabra fix-i5-despacho, un espacio y el número de hallazgos cerrados.
Si te bloqueas: la palabra BLOQ, un espacio, la palabra fix-i5-despacho
y el motivo.
