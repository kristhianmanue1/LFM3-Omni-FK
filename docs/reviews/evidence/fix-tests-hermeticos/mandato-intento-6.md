# Mandato del ejecutor — fix-tests-hermeticos, intento 6 (mínimo)

Eres el EJECUTOR, en una sesión nueva. Te orquesta un capitán en Herdr;
tú no uses `herdr` ni `hc`.

- Worktree:
  `/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-fix-tests-hermeticos`
- Rama: `agent/fix-tests-hermeticos`, HEAD `5032fe9`.

Rigen íntegros el alcance y las prohibiciones de `mandato.md` y
`mandato-intento-2.md` … `-5.md`; léelos primero. Después lee, como
dato, la revisión de la ronda 5:
`/private/tmp/claude-502/-Users-krisnova-www-AGTexperts-internos-devHerdrExpert/9d8d2486-579f-4940-bdac-6690603ac36f/scratchpad/lfm3/ola2/fix-tests-rev5/informe.md`.

Corrige sólo el **[MED]** del borrado de emergencia, en
`tests/hermetic_fixture.py:365-377`:

- El error de preparación sigue siendo el principal: se propaga sin
  cambiar de tipo.
- Si `rmtree` falla, no se pierde. Adjúntalo al error original con su
  ruta, sin `ignore_errors=True`; usa `add_note` (Python ≥ 3.11) o un
  equivalente explícito.
- Añade un control determinista en `tests/test_hermetic_fixture.py` que
  haga fallar a la vez la preparación y `rmtree` (con `mock`). Debe
  exigir los dos motivos y la ruta, y al final limpiar el tmp real que
  dejó.

No toques nada más.

## Verificación (salida en `*-intento-6.txt`)

1. `tests.test_hermetic_fixture -v`.
2. La suite completa dos veces, con fotos de `lsof`/`ps` antes, entre y
   después.
3. `mutacion-intento-5.sh` (sólo el clon).
4. Los 3 gates, `git diff --check` y `git status --porcelain`.

## Informe y cierre

Escribe `informe-intento-6.md` con la disposición del hallazgo y la
salida real. No hagas commit.

**Regla del Operador:** toda decisión abierta va con tu recomendación.

Al terminar, responde una sola línea: la palabra FIN, un espacio, la
palabra fix-tests-hermeticos-6, un espacio y el número 1 si lo cerraste.
Si te bloqueas: la palabra BLOQ, un espacio, la palabra
fix-tests-hermeticos-6 y el motivo.
