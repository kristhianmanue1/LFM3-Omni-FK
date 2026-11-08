# Informe — fix-tests-hermeticos, intento 4

Ejecutor: agente en worktree
`/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-fix-tests-hermeticos`,
rama `agent/fix-tests-hermeticos`, HEAD `8b59118` (intentos 1-3 en commit;
este intento queda sin commit para el capitán). Intento ACOTADO: el diseño
cerrado del intento 3 no se toca; sólo las cinco correcciones del
mandato-intento-4. Prohibiciones respetadas: ningún `kill`/`pkill`/
`stop.sh` mío contra procesos o puertos reales (las señales a hijos
directos siempre por handle `Popen`), motor real no arrancado, alcance
limitado a `tests/` y este expediente (`git status --porcelain` en
`green_checks_git-intento-4.txt`). Nota de entorno: AN-KLA responde
`reader_gate_unavailable` (memoria no inicializada); no se inicializó sin
habilitación del Operador.

## Disposición de los 5 hallazgos de la ronda 3

1. **[HIGH] `test_11` deja sin cleanup al primer hijo si falla el segundo
   `Popen`** — **fixed.** En `tests/test_piloto_live_i2.py` el cleanup de
   cada `Popen` se registra INMEDIATAMENTE tras crearlo
   (`addCleanup(fx.terminate_handle, …)` antes de la siguiente
   adquisición) y la inscripción (`fx.own`) va después, con manejo del
   fallo (`self.fail` con motivo; los handles ya están garantizados).
   Control `test_11b_second_popen_failure_collects_first_child`: induce
   `FileNotFoundError` en el segundo `Popen` (intérprete inexistente),
   corre `doCleanups()` en vivo y demuestra que el primer hijo terminó
   por handle y quedó recogido (`poll()` no `None`, sin proceso ni
   zombie). En verde en `focal-intento-4.txt`.
2. **[HIGH] El centinela se borra antes de liberar a los hijos** —
   **fixed.** `register_cleanup` inscribe ahora UNA sola pieza,
   `final_cleanup`, con `try/finally`: escribe el centinela y verifica;
   mientras haya supervivientes conserva el tmp y el centinela y el
   fallo viaja con el PID y la ruta conservada; sólo borra cuando ya es
   seguro (`_survivors()` vacío) y SIN `ignore_errors` — un fallo de
   borrado se propaga. Idempotente (tmp ya ausente ⇒ no-op). Control
   `test_survivor_keeps_tmp_and_sentinel` (`tests/test_hermetic_fixture.py`):
   un sustituto que IGNORA el centinela hace FALLAR el caso interior por
   su limpieza, el fallo nombra PID y ruta, y el directorio y el
   centinela quedan presentes; al final el sustituto termina POR SU
   HANDLE (nunca por un PID leído de archivo) y sólo entonces el borrado
   procede. En verde en `focal-intento-4.txt` (7 tests del módulo).
   Nota incidental: el primer humo de este control (diseño inicial con
   el caso interior a nivel de módulo) falló y conservó su escena en
   `${TMPDIR}/hermetic-cleanup-*` con el centinela presente — el
   comportamiento de diagnóstico, ejercido sin querer; retirada tras
   constatarlo, cero residuos al final.
3. **[MED] `setUpClass` de `TestPilotoPrivadoLive` sin limpieza de
   preparación** — **fixed.** `addClassCleanup` tras CADA adquisición
   (backend, tmp, gateway, TLS) vía `_close_server`/`temp_dir.cleanup`;
   `tearDownClass` eliminado. El defecto venía de `main`: verificado con
   `git show 60c6568:tests/test_piloto_live_i2.py` (setUpClass secuencial
   + sólo tearDownClass, líneas 117/194 de entonces).
4. **[MED] Identificadores nuevos en español** — **fixed.** Renombrados
   los citados (`vivos`→`alive`, `duplicado`→`duplicate`,
   `visto`→`seen`, `vivo`→`alive`, `apagar`→`sentinel` (variable),
   `modelo`→`model_id`, `lineas`→`lines`, `esperar_invocaciones`→
   `wait_for_invocaciones`, `minimo`→`minimum`) y los que el inventario
   agregó: `assertArriba`→`assert_serve_up`, `mensaje`→`message`,
   `adverso`→`adversarial_path`, `parada`→`stop_run`,
   `RAIZ`→`ROOT` (nuevo en tres archivos) y los seis nombres de test del
   fixture a inglés. El ARCHIVO centinela `apagar`→`shutdown`: ni
   `stop.sh` ni `serve.sh` lo leen (grep en
   `inventario-identificadores-intento-4.txt`, §1) — es interno del
   fixture, así que se renombra. Inventario completo pre/post en el
   mismo expediente (§2/§3); los españoles conservados (§4:
   `RAIZ`/`lanzar_serve`/`assertLimpio`/`muerto`/`ajeno`/`ocupante`/
   `veneno`/`victima`/`comando`/`inv`/`primero`/`segundo` en
   `test_ciclo_arranque.py`) son preexistentes en `main`, contados uno a
   uno contra `git show 60c6568:…`. Prosa, docstrings y comentarios
   siguen en español.
5. **[MED] Vía acotada de señal a PID reciclado dentro del mismo
   segundo** — **residual**, por mandato (no cerrar aquí). Riesgo
   residual declarado para decisión del Operador (ver decisiones
   abiertas). Mitigación propuesta como tarea aparte: endurecer
   `run/stop.sh` para matar por pidfile + hora de inicio (lstart)
   registrada al arrancar, no sólo por descubrimiento de puerto.

Cuatro `fixed`, un `residual` (mandatado).

## Cambios por archivo (intento 4)

- `tests/hermetic_fixture.py`: limpieza única `final_cleanup`
  (`try/finally`, conservación con supervivientes, borrado seguro sin
  `ignore_errors`, idempotente); `stop_and_verify` con plazo configurable
  (`verify_timeout`, 10 s por defecto) y fallo con ruta conservada;
  centinela renombrado a `shutdown` (interno: `run/` no lo lee);
  identificadores de los sustitutos lsof/curl/motor a inglés.
- `tests/test_hermetic_fixture.py`: seis tests renombrados a inglés;
  `RAIZ`→`ROOT`; control nuevo
  `CleanupKeepsSceneForSurvivors.test_survivor_keeps_tmp_and_sentinel`
  (caso interior definido dentro del método para que el cargador no lo
  recoja: está diseñado para fallar por su limpieza).
- `tests/test_piloto_live_i2.py`: `setUpClass` con `addClassCleanup`
  tras cada adquisición y `tearDownClass` fuera; `test_11` con cleanup
  por `Popen` inmediato e inscripción posterior con manejo de fallo;
  control nuevo `test_11b_second_popen_failure_collects_first_child`;
  `RAIZ`→`ROOT`.
- `tests/test_ciclo_arranque.py`: renombres de identificadores nuevos
  (`wait_for_invocations`, `minimum`, `assert_serve_up`, `message`,
  `adversarial_path`, `stop_run`); sin cambios de aserción.
- `tests/test_engine_probe.py`: `RAIZ`→`ROOT`.
- Expediente: `capturar-intento-4.py`, `focal-intento-4.txt`,
  `green_suite_1/2-intento-4.txt`, `mutantes-intento-4.txt`,
  `green_checks_git-intento-4.txt`,
  `inventario-identificadores-intento-4.txt`, este informe.

## Salida real de las verificaciones

- **Focales con `-v`** (`focal-intento-4.txt`): piloto 13 (incluye
  `test_11` y `test_11b`) + ciclo 8 + fixture 7 (incluye el control
  nuevo) + sonda 7 = **35 tests, OK, 53.9 s**; fotos lsof/ps limpias
  antes y después.
- **Suite completa dos veces** (`green_suite_1/2-intento-4.txt`):
  `Ran 319 tests, OK (skipped=2)` en 121.9 s y 122.2 s (317 del intento
  3 + `test_11b` + control del fixture). Fotos lsof/ps antes, entre (el
  «antes» de la segunda) y después: `(ninguno)` en todas. P3 en verde.
- **Mutación** (`mutantes-intento-4.txt`, guion del intento 3 intacto,
  sólo clon): BASELINE test_11 rc=0 y sonda rc=0; **MUTANTE 1 muere,
  MUTANTE 2 muere, MUTANTE 3 muere**.
- **Gates y git** (`green_checks_git-intento-4.txt`):
  `check_sizes`/`check_plans`/`check_reports` rc=0 (más los dos drift
  del kit, rc=0); `git diff --check` rc=0 (también el rango completo
  `60c6568`); `git status --porcelain` acotado a `tests/` + expediente.
- **Sin restos**: cero directorios `hermetic-*` en `${TMPDIR}` y cero
  procesos del fixture tras la batería (`pgrep` vacío).

## Propiedades P1-P3 (continuidad)

- **P1** — ningún test ejecuta `run/` del checkout ni toca
  procesos/puertos reales; `stop.sh`/`serve.sh` se ejercen en copias con
  sustitutos: **pass** (fotos limpias; mutantes 1 y 2 mordiendo).
- **P2 sin motor** — saltos con motivo, guardas deterministas:
  **pass** (`skipped=2` en ambas suites). **P2 con motor**:
  **inconclusive** (sin motor; arrancarlo está prohibido) — atribución
  heredada.
- **P3** — dos corridas idénticas sin restos: **pass** (319 OK ×2).

## Decisiones abiertas (recomendación primero)

1. **Riesgo residual del PID reciclado dentro del mismo segundo**
   (hallazgo 5, carrera inferida, no observada).
   - *Recomendada*: aceptarlo como residual documentado y agendar la
     tarea aparte de endurecer `run/stop.sh` (matado por pidfile +
     lstart registrado al arrancar). Por qué: cierra la ventana en el
     PRODUCTO, que es donde vive el riesgo real, sin inflar el fixture
     de pruebas; el kill vigilado ya exige inscripción + hora de inicio
     y las negativas quedan registradas (evidencia: controles del
     fixture y mutante 2). Coste de la alternativa: aislar la entrega
     de señales del host (handles de kernel / jaulas) — fuera del
     alcance de `tests/` y desproporcionado para P1 acotado.
   - *Alternativa*: exigir P1 absoluto con aislamiento de señales.
     Coste: infraestructura de sandbox en la suite y mantenimiento
     permanente de algo que una línea de `stop.sh` productivo cierra
     mejor.
2. **Verificación de P2-con-motor** cuando haya motor de verdad
   (heredada del intento 3).
   - *Recomendada*: en cuanto el Operador arranque su motor, correr
     `python3 -m unittest tests.test_mcp_server tests.test_jobs_i5 -v`
     y ver las guardas no saltar. Coste de la alternativa: la rama
     queda `inconclusive` (atribuida) hasta esa corrida.

## Riesgos

- Los del intento 3 siguen en pie (identidad `exec -a` dependiente de
  node; ventana mínima lectura-lstart→señal — el residual nº 1 arriba;
  vigilancia atada a `BASH_ENV`; fidelidad de los sustitutos al
  mecanismo de descubrimiento actual de `run/`).
- `final_cleanup` puede enmascarar un hipotético fallo de `rmtree` sobre
  el `AssertionError` de supervivientes si éstos mueren justo tras el
  plazo; caso de esquina, el fallo sustituto también es error de
  limpieza y conserva la escena.
- `check_sizes` reporta 1799/1800 en la ruta de lectura (preexistente):
  sin margen para que la ruta obligatoria crezca; este intento no la
  toca (todo vive en `tests/` y el expediente).

No se hizo commit: el capitán lo hace tras auditar.
