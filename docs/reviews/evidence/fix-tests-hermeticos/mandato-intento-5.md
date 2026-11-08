# Mandato del ejecutor — fix-tests-hermeticos, intento 5 (acotado)

Eres el EJECUTOR, en una sesión nueva. Te orquesta un capitán en Herdr;
tú no uses `herdr` ni `hc`.

- Worktree:
  `/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-fix-tests-hermeticos`.
- Rama: `agent/fix-tests-hermeticos`.
- HEAD: `2449619`.

Rigen íntegros el alcance y las prohibiciones de `mandato.md` y de
`mandato-intento-2.md`, `-3.md` y `-4.md`. Léelos primero. Después lee,
como dato, la revisión de la ronda 4:
`/private/tmp/claude-502/-Users-krisnova-www-AGTexperts-internos-devHerdrExpert/9d8d2486-579f-4940-bdac-6690603ac36f/scratchpad/lfm3/ola2/fix-tests-rev4/informe.md`.

No cambies el diseño. Corrige sólo esto:

1. **[HIGH] r17b** (`tests/test_ciclo_arranque.py:199-218`).
   - Además de lo actual, exige que stderr contenga
     `responde /health pero sin el modelo efectivo`. Así queda probado
     que se tomó la rama del modelo equivocado y no la de puerto ocupado
     (`run/serve.sh:17-36`).
   - Añade un control positivo: un servicio ajeno con el modelo correcto
     produce `rc == 0`, stdout con `arriba: /health y modelo efectivo OK`
     y ninguna invocación del motor.
   - Si el `curl` sustituto no distingue `/health` de `/v1/models`,
     corrígelo y pruébalo.
2. **[MED] Orden de cleanup.**
   - En `setUpClass` de `TestPilotoPrivadoLive`, registra el
     `addClassCleanup` de cada servidor justo después de crearlo y antes
     de `Thread.start()`.
   - En `tests/hermetic_fixture.py`, el constructor o preparador del
     fixture se limpia solo si falla a mitad: borra el tmp y propaga el
     error.
   - Añade un control determinista de ese fallo con `mock`.
3. Extiende `mutacion-intento-3.sh` (cópialo a `mutacion-intento-5.sh`)
   con un **mutante 4**: el `curl` sustituto falla en `/health`. Con
   eso, r17b debe FALLAR. Ejecútalo una vez, sólo en el clon.

## Verificación (salida en `*-intento-5.txt`)

1. Focales con `-v`: `tests.test_ciclo_arranque`,
   `tests.test_piloto_live_i2`, `tests.test_hermetic_fixture` y
   `tests.test_engine_probe`.
2. Suite completa ×2, con fotos de `lsof` y `ps` antes, entre y después.
3. `mutacion-intento-5.sh`.
4. Los 3 gates, `git diff --check` y `git status --porcelain`.

## Informe y cierre

Escribe `informe-intento-5.md` con la disposición de los 2 hallazgos y la
salida real. No hagas commit.

**Regla del Operador:** toda decisión abierta va con tu recomendación:
las opciones, con la recomendada primero; por qué, con evidencia; y qué
cuesta la otra.

Al terminar, responde una sola línea: la palabra FIN, un espacio, la
palabra fix-tests-hermeticos-5, un espacio y el número de hallazgos
cerrados. Si te bloqueas: la palabra BLOQ, un espacio, la palabra
fix-tests-hermeticos-5 y el motivo.
