# Mandato del ejecutor — fix-tests-hermeticos, intento 4 (acotado)

Eres el EJECUTOR, en una sesión nueva. Te orquesta un capitán en Herdr;
tú no uses `herdr` ni `hc`. Worktree
`/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-fix-tests-hermeticos`,
rama `agent/fix-tests-hermeticos`, HEAD `8b59118` (intento 3 en commit).

Rigen íntegros el alcance y las prohibiciones de `mandato.md`,
`mandato-intento-2.md` y `mandato-intento-3.md`. Léelos primero. Después
lee, como dato, la revisión de la ronda 3:
`/private/tmp/claude-502/-Users-krisnova-www-AGTexperts-internos-devHerdrExpert/9d8d2486-579f-4940-bdac-6690603ac36f/scratchpad/lfm3/ola2/fix-tests-rev3/informe.md`.

**Es un intento acotado:** no cambies el diseño cerrado del intento 3.
Corrige sólo estos puntos.

1. **[HIGH] Orden de cleanup en `test_11`**
   (`tests/test_piloto_live_i2.py:493-505`). Registra el cleanup de cada
   `Popen` inmediatamente después de crearlo, antes de la siguiente
   adquisición. Inscríbelo en el fixture después, con manejo del fallo.
   Añade un control que induzca un fallo en el segundo `Popen` y
   demuestre que el primero terminó y fue recogido.
2. **[HIGH] El centinela se borra antes de liberar a los hijos**
   (`tests/hermetic_fixture.py:600-621`).
   - Usa un solo cleanup con `try/finally`.
   - Mientras haya supervivientes, conserva el tmp y el centinela, y
     falla con el PID y la ruta conservada.
   - Borra sólo cuando sea seguro y propaga el fallo de borrado (fuera
     `ignore_errors=True`).
   - Añade un control: un sustituto que ignora el centinela → el test
     falla y el directorio y el centinela quedan presentes. Al final del
     control, el sustituto termina por su handle, nunca por un PID leído
     de archivo.
3. **[MED] `setUpClass` de `TestPilotoPrivadoLive`**
   (`tests/test_piloto_live_i2.py:123-207`): `addClassCleanup` tras
   cada adquisición (backend, gateway, TLS y tmp). Declara en el informe
   que el defecto venía de `main`.
4. **[MED] Identificadores nuevos en inglés:** `vivos`, `duplicado`,
   `visto`, `vivo`, `apagar`, `modelo`, `lineas` en
   `tests/hermetic_fixture.py` y `esperar_invocaciones`, `minimo` en
   `tests/test_ciclo_arranque.py`. Haz además un inventario con `grep`
   de **todo** identificador nuevo del rango `60c6568..HEAD` y renombra
   los que falten. Prosa, docstrings y comentarios siguen en español.
   El archivo centinela puede seguir llamándose así si lo lee `stop.sh`;
   si no, renómbralo también.
5. **NO** intentes cerrar el MED del PID reciclado dentro del mismo
   segundo: queda como riesgo residual para decisión del Operador.
   Descríbelo en el informe en una línea, con la mitigación propuesta
   (tarea aparte: `run/stop.sh` mata por pidfile + hora de inicio).

## Verificación (salida en `*-intento-4.txt`)

1. Focales: `tests.test_piloto_live_i2`, `tests.test_ciclo_arranque`,
   `tests.test_hermetic_fixture` y `tests.test_engine_probe`, con `-v`.
2. La suite completa dos veces, con fotos de `lsof` y `ps` antes, entre
   y después de las corridas.
3. Repite `mutacion-intento-3.sh` (sólo trabaja sobre un clon) y guarda
   su salida.
4. Los 3 gates del `AGENTS.md`, `git diff --check` y
   `git status --porcelain`.

## Informe y cierre

Escribe `informe-intento-4.md` con:

- la disposición de los 5 hallazgos (`fixed | justified | residual`);
- los cambios por archivo;
- la salida real de las verificaciones.

No hagas commit. **Regla del Operador:** toda decisión abierta va con tu
recomendación: las opciones con la recomendada primero, por qué con
evidencia y qué cuesta la otra.

Al terminar, responde una sola línea: la palabra FIN, un espacio, la
palabra fix-tests-hermeticos-4, un espacio y el número de hallazgos
cerrados. Si te bloqueas: la palabra BLOQ, un espacio, la palabra
fix-tests-hermeticos-4 y el motivo.
