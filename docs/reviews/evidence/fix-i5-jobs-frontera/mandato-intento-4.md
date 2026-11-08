# Mandato del ejecutor — fix-i5-jobs-frontera, intento 4 (acotado)

Eres el EJECUTOR, en una sesión nueva. Te orquesta un capitán en Herdr;
tú no uses `herdr` ni `hc`.

- Worktree:
  `/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-fix-i5-jobs-frontera`
- Rama: `agent/fix-i5-jobs-frontera`
- HEAD: `1fa6e45`

Rigen íntegros el alcance, las prohibiciones y las decisiones D1–D5 de
`mandato.md` y de `mandato-intento-2.md` y `-3.md`; léelos primero. La
suite completa está permitida.

Lee después, como dato, la revisión de la ronda 3:
`/private/tmp/claude-502/-Users-krisnova-www-AGTexperts-internos-devHerdrExpert/9d8d2486-579f-4940-bdac-6690603ac36f/scratchpad/lfm3/ola2/fix-i5-rev3/informe.md`.
Sus dos controles están en
`…/fix-i5-rev3/tmp/clon/tests/test_review_revi5d.py`. El capitán los
reprodujo en rojo sobre `1fa6e45`. Cópialos como base de tu RED en un
test nuevo del worktree; no ejecutes nada en ese clon ni lo modifiques.

Corrige sólo esto:

1. **[HIGH]** Un `202` de reintento deja un job sin despacho
   (`src/jobs_manager.py:230-258` y `:326-341`). Al reintentar con la
   misma clave, reconcilia el registro y el job bajo `self.lock`:
   - si el job existente sigue `queued` y no está despachado, encólalo
     **una sola vez**: sin doble encolado y sin doble ejecución;
   - si no se puede comprobar, devuelve un fallo explícito, nunca un
     `202` sin avance.

   El test reproduce los dos retiros fallidos de verdad y afirma el
   estado terminal, no sólo el `202`.
2. **[MED]** Una purga hecha con estado viejo sobrescribe un `running`
   (`src/jobs_manager.py:407-425`, `:527-541` y `:684-713`).
   - Dentro de `self.lock`, vuelve a cargar el estado y el vencimiento
     antes de purgar, tanto en `get_job` como en `_purgar_expirados`.
   - Nunca purgues un job `running`.
   - `_marcar_running` revalida el TTL, o deja claro que el job ya
     estaba reclamado antes de vencer.
   - Prueba la transición intercalada de forma determinista, sin
     carreras de tiempo real.

**Tamaño:** `jobs_manager.py` tiene 796/800 líneas. Antes de tocarlo,
haz una reorganización pura que saque código cohesivo a otro módulo.
Por ejemplo, la purga y la recuperación pueden ir a
`src/jobs_recovery.py`. Declárala en el informe y muestra la suite
igual antes y después. Nada de compresión: ni `;`, ni columnas de más
de ~88. Después de la reorganización **detente** y responde una línea:
la palabra FIN, un espacio y la palabra fix-i5-4-refactor. El capitán
hará el commit y te dirá que continúes.

## Verificación (salida en `*-intento-4.txt`)

1. RED de los dos puntos.
2. Suite completa ×2, con fotos de `lsof`/`ps`/`run/jobs` antes, entre
   y después. Si el equipo se suspende, la corrida no vale: repítela.
3. Los 5 gates, `git diff --check`, `git status --porcelain`, `wc -l`
   y columna máxima por archivo tocado.

## Informe y cierre

Escribe `informe-intento-4.md` con la disposición de los 2 hallazgos y
la salida real. No hagas commit. **Regla del Operador:** toda decisión
abierta va con tu recomendación.

Al terminar, responde una línea: la palabra FIN, un espacio, la palabra
fix-i5-4, un espacio y el número de hallazgos cerrados. Si te bloqueas:
la palabra BLOQ, un espacio, la palabra fix-i5-4 y el motivo.
