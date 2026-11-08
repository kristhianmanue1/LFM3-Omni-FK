# Mandato del ejecutor — fix-i5-jobs-frontera, intento 3 (acotado)

Eres el EJECUTOR, en una sesión nueva. Te orquesta un capitán en Herdr;
tú no uses `herdr` ni `hc`. Worktree
`/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-fix-i5-jobs-frontera`,
rama `agent/fix-i5-jobs-frontera`, HEAD `1511764`.

Rigen íntegros el alcance, las prohibiciones y las decisiones D1–D5 de
`mandato.md` y `mandato-intento-2.md`. La suite completa está permitida:
este worktree ya es hermético. Léelos primero. Después lee, como dato,
la revisión de la ronda 2:
`/private/tmp/claude-502/-Users-krisnova-www-AGTexperts-internos-devHerdrExpert/9d8d2486-579f-4940-bdac-6690603ac36f/scratchpad/lfm3/ola2/fix-i5-rev2-glm/informe.md`.

No cambies el diseño. Corrige sólo esto, con RED primero:

1. **[MED-1]** `startup_recover` (`src/jobs_manager.py:138-170`).
   Añade una transición durable `cancellation_pending → failed`
   (`server_interrupted`), junto a la de `running`. El test debe afirmar
   el estado final en disco.
2. **[MED-2]** Control positivo de D2. Con un job `running` o
   `cancellation_pending` del proyecto, un segundo POST se **admite**
   (`202`) porque SPEC-i5:75 cuenta sólo `queued`. Ese test debe quedar
   rojo si se vuelve al conteo de no terminales.
3. **[MED-3]** `stop()` (`src/jobs_manager.py:128-136`). Cierra el fd
   de instancia sólo cuando el hilo del worker haya terminado de verdad.
   Si sigue vivo tras el plazo, no liberes el cerrojo (fail-closed) y
   deja constancia del motivo. El test: apagado con un job en vuelo y
   backend lento, y una segunda instancia que debe fallar con
   `JobsDirOcupado` mientras el worker viva.
4. **[LOW-4]** `src/jobs_storage.py:202-219`. Bifurca por `errno`:
   - `EWOULDBLOCK`/`EAGAIN` → «ocupado por otra instancia»;
   - el resto → «cerrojo no soportado por este sistema de archivos», con
     la causa.

   En los dos casos falla cerrado. El test inyecta `ENOLCK`.
5. **[LOW-5]** Rama irretirable tras `os.link`
   (`src/jobs_manager.py:314-328`). Responde `500` (`storage_error`) en
   vez de `202` y deja que el reintento reconcilie por la vía del
   huérfano. Razón: fail-closed (estándar §1, principio 5) y §J
   («admisión sólo tras persistir … atómicamente»). Ajusta el test
   correspondiente.
6. **[LOW-6]** Toma `self.lock` alrededor de la purga en `get_job`
   (`src/jobs_manager.py:397-411`).
7. **NO** cierres el LOW-7 (reloj inyectable). Queda como seguimiento:
   anótalo en el informe con tu recomendación.

**Tamaño:** `jobs_manager.py` tiene 793/800 líneas. Si no cabe sin
comprimir, mueve código cohesivo a `jobs_storage.py` (por ejemplo, la
recuperación) en un paso de reorganización pura, declarado en el
informe. Nada de sentencias unidas con `;` y columna máxima ~88.

## Verificación (salida en `*-intento-3.txt`)

1. RED de los puntos 1–6.
2. La suite completa dos veces, con fotos de `lsof`/`ps`/`run/jobs`
   antes, entre y después.
3. Los 5 gates, `git diff --check`, `git status --porcelain`, y
   `wc -l` y columna máxima de cada archivo tocado.

## Informe y cierre

Escribe `informe-intento-3.md` con la disposición de los 7 hallazgos y
la salida real. No hagas commit.

**Regla del Operador:** toda decisión abierta va con tu recomendación
(las opciones con la recomendada primero, por qué con evidencia y qué
cuesta la otra).

Al terminar, responde una sola línea: la palabra FIN, un espacio, la
palabra fix-i5-3, un espacio y el número de hallazgos cerrados. Si te
bloqueas: la palabra BLOQ, un espacio, la palabra fix-i5-3 y el motivo.
