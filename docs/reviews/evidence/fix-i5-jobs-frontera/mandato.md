# Mandato del ejecutor — fix-i5-jobs-frontera, intento 1

Eres el EJECUTOR. Te orquesta un capitán en Herdr; tú no uses `herdr` ni
`hc`. Trabajas SÓLO en este worktree
(`/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-fix-i5-jobs-frontera`,
rama `agent/fix-i5-jobs-frontera`, base `main` `60c6568`).
**Tarea material**: aplican los disparadores 1, 2, 3 y 4 de `04` §5.3.

## 1. Lee completos, en este orden

- `AGENTS.md` y lo que manda leer, incluido
  `docs/ai-agent-guide/06-componentes-con-llm.md`;
- `docs/ai-agent-guide/04-ejecucion-y-verificacion.md`;
- `docs/specs/SPEC-i5-jobs.md`;
- `docs/adr/ADR-012-trabajos-largos-persistencia-idempotencia.md`;
- `docs/contracts/perfiles-servicio-v2.md` §H y §J;
- `src/jobs_manager.py`, `src/gateway_http.py` (rutas `/jobs`,
  `_leer_json_post`, `build_server`) y `src/gateway_core.py`
  (`validar_payload`, `validar_salida`, scopes);
- `src/gateway_auth.py` (`FairQueueDispatcher`, `verify_request`);
- `tests/test_jobs_i5.py`.

Hallazgos de la revisión fresca de I3–I6 que debes cerrar (es un dato;
el capitán confirmó los marcados con ✔ contra el código):

**[BLOCKER-1]** `/jobs` admite trabajos sin la frontera H ni el scope de
la operación. ✔

- `gateway_http.py:558-579` sólo exige `jobs:create`;
- `jobs_manager.py:202-214` y `:435-446` reenvían el `payload` a
  `/v1/chat/completions` sin `validar_payload`;
- `:459-473` persiste la salida sin `validar_salida`.

Corrección:

- exigir `jobs:create` **y** el scope de la modalidad de la operación;
- validar el cuerpo con el núcleo (`validar_payload`) antes de admitir;
- validar la completitud (`finish_reason`) y el esquema (`validar_salida`)
  antes de persistir el resultado. Si la validación falla, el job termina
  en estado de fallo explícito, nunca `completed`.

**[BLOCKER-2]** Un `202` sin registro durable. ✔

- `_save_job_atomically` se traga el `OSError` (`:123-136`);
- `create_job` escribe el job y el índice en dos reemplazos separados
  (`:302-318`), sin `fsync`.

Corrección:

- propagar los fallos: ningún `202` si la escritura no consta;
- `fsync` de archivo y de directorio;
- commit recuperable de job e índice (por ejemplo, índice derivable de
  los archivos de job al arrancar);
- tests que inyectan un fallo en cada transición.

**[HIGH-1]** Sin reclamo ni presupuesto compartido entre procesos.

- cada `JobsManager` tiene su propio lock, cola y worker (`:75-86`);
- `startup_recover` encola todo lo `queued`;
- el worker no pasa por `FairQueueDispatcher`.

Corrección:

- reclamo atómico entre procesos (por ejemplo, `rename` o
  `fcntl.flock`);
- el worker adquiere la admisión compartida con H/M;
- test con dos instancias sobre el mismo `data_dir` que no ejecutan el
  mismo job.

**[HIGH-2]** Retención y confidencialidad.

- `get_job` sólo responde 410 tras `expires_at` y no purga nada;
- JSON en claro sin permisos explícitos;
- `expires_at` se fija desde la admisión, pero §J lo propone tras
  terminar.

Corrección:

- purga o tombstone verificable al expirar;
- archivos `0600` y directorios `0700`;
- `expires_at` conforme a §J. El cifrado en reposo NO se implementa: es
  una decisión para el Operador, que va en el informe con tu
  recomendación.

**[HIGH-3]** La idempotencia no es RFC 8785 ni rechaza JSON duplicado.

- `canonical_json_rfc8785` es `json.dumps(sort_keys=True)` (`:39-53`);
- `_leer_json_post` acepta claves duplicadas.

Corrección:

- serialización de números conforme a RFC 8785 (forma ES6), con
  fixtures numéricos de su anexo;
- `object_pairs_hook` que rechaza duplicados en la frontera con un 400
  controlado (campo y motivo).

## 2. Alcance

Permitido:

- `src/jobs_manager.py`;
- `src/gateway_http.py`, sólo lo de `/jobs` y `_leer_json_post`;
- `tests/test_jobs_boundary_i5.py` (nuevo: pon aquí los tests nuevos);
- este expediente.

`tests/test_jobs_i5.py` sólo si un test existente necesita adaptarse al
comportamiento corregido. Edición mínima, sin tocar la guarda de motor
de `test_09` ni los imports del inicio: otra rama
(`agent/fix-tests-hermeticos`) los modifica.

Fuera de alcance: todo lo demás. En particular:

- `run/`, `scripts/`, `skevi-gate.json`, `AGENTS.md`, `.skevi/`;
- `gateway_core.py`: úsalo, no lo cambies. Si hace falta cambiarlo,
  BLOQ con tu recomendación;
- SPEC y ADR: si el código obliga a cambiar el contrato, anótalo como
  decisión en el informe, no lo edites.

## 3. Prohibido

- arrancar el motor, `run/serve.sh`, `run/stop.sh`, gateways reales o
  servicios;
- exponer `/jobs` (decisión vigente del Operador: no se expone);
- `kill`, `pkill` o barridos sobre procesos reales;
- red;
- commit, push, stash o ramas;
- editar la configuración de los gates.

Los tests usan siempre un `data_dir` temporal y un backend falso en un
puerto efímero; nunca `run/jobs` ni 8091.

**No ejecutes la suite completa:** este worktree conserva el
`tests/test_piloto_live_i2.py` viejo, que ejecuta el `run/stop.sh` y el
`run/serve.sh` reales. Ejecuta sólo `tests.test_jobs_i5` y
`tests.test_jobs_boundary_i5`, y los otros módulos que importen
`jobs_manager` o `gateway_http`, salvo `test_piloto_live_i2`, que está
prohibido. Lista primero cuáles son con `grep`.

## 4. Método (`04` §3 y `06` §2)

1. **RED primero:** un test por propiedad que falle hoy (scope de
   modalidad, payload fuera del dialecto, salida inválida o truncada,
   `OSError` en cada escritura, dos instancias, purga y permisos, número
   RFC 8785, clave duplicada). Guarda la salida en `red.txt`.
2. **GREEN:** corrige. Guarda `green.txt` con los módulos de §3 dos veces
   y `lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(8091|8092|8443) '` antes y
   después.
3. Los 3 gates del `AGENTS.md`, `git diff --check` y
   `git status --porcelain`.
4. Ronda adversarial propia sobre tu diff con el catálogo
   `.skevi/review-defect-catalog.md`. Después habrá un revisor fresco de
   otra familia.

## 5. Informe y cierre

Escribe `informe.md` en este expediente con:

- la disposición de cada hallazgo (`fixed | justified`, con evidencia);
- los cambios por archivo;
- las propiedades con `pass | fail | inconclusive`;
- los riesgos;
- las decisiones para el Operador.

Las decisiones incluyen el cifrado en reposo y cualquier cambio de
contrato. **Regla del Operador:** cada decisión va con tu recomendación
(las opciones con la recomendada primero, por qué con evidencia y qué
cuesta la otra). No hagas commit.

Al terminar, responde una sola línea: la palabra FIN, un espacio, la
palabra fix-i5, un espacio y el número de hallazgos cerrados. Si te
bloqueas: la palabra BLOQ, un espacio, la palabra fix-i5 y el motivo.
