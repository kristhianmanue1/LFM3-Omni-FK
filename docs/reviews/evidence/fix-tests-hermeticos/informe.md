# Informe — fix-tests-hermeticos, intento 1

Ejecutor: agente en worktree
`/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-fix-tests-hermeticos`,
rama `agent/fix-tests-hermeticos`, base `main` `60c6568`. Fecha: 2026-11-07
(noche). Alcance respetado: sólo `tests/` y este expediente (git status lo
confirma: tres archivos de `tests/` modificados + este directorio).

## Resumen de estado

**PARCIAL.** P1 (negativa: ningún test toca lo real) y P3 verificadas con
evidencia; la rama «con motor» de P2 verificada. Quedan inconclusive, por
la misma causa exógena (el motor del Operador en 8091, que no debo tocar),
la rama «sin motor» de P2 y la corrida del cuerpo hermético de `test_11`.

## Cambios por archivo

1. `tests/test_mcp_server.py` — `MOTOR_VIVO = mcp._motor_up()` evaluado
   una vez al importar; `ToolsConMotor` con
   `@unittest.skipUnless(MOTOR_VIVO, "requiere motor vivo en 127.0.0.1:8091
   (bash run/serve.sh); no detectado")`. Docstrings (módulo y clase)
   actualizados al nuevo comportamiento. Aserciones intactas.
2. `tests/test_jobs_i5.py` — ayudante `_motor_vivo()` (sonda GET
   `/health`, una vez al importar) y `@unittest.skipUnless` en
   `test_09_post_jobs_http_flujo_completo`, único test del módulo que
   requiere el motor (evidencia: sin motor, el job muere al instante y el
   DELETE responde `already_terminal`). `test_10` (alcances) y `test_11`
   (guion demo) no dependen del motor: pasaron sin motor en la corrida
   accidental (`incidente-suite-accidental.txt`).
3. `tests/test_piloto_live_i2.py` — `test_11_rollback_parada_limpia`
   reescrito hermético al patrón de `tests/test_ciclo_arranque.py`:
   copias de `run/serve.sh` y `run/stop.sh` en un directorio temporal,
   sustituto de `llama-server` en un `PATH` propio, residuos de PID y
   cerrojos pre-creados, y aserciones de que `stop.sh` (i) devuelve 0 con
   «detenido: sin escucha en 8091», (ii) libera 8091 y mata el proceso del
   motor sustituto, y (iii) elimina `llama-server.pid`, `serve.lock`,
   `serve_pilot.lock`, `gateway.pid` y `tls.pid`. Se salta con motivo
   explícito si 8091/8092/8443 están ocupados por procesos ajenos (no los
   toca) o si `node` no está disponible. Imports y `_puerto_libre` /
   `_pid_vivo` nuevos en el módulo.

Archivos de `tests/` modificados: **3**.

## Causa raíz (con evidencia)

- **P1 roto**: `test_11` ejecutaba `bash run/stop.sh` y `bash run/serve.sh`
  REALES del checkout (`tests/test_piloto_live_i2.py` líneas 458–470
  pre-fix): `stop.sh --all` contra puertos reales y `serve.sh` real que
  arranca un `llama-server` que queda huérfano. Demostrado sin ejecutar
  nada real con `probe_p1_red.py` (`subprocess.run` grabador): registró
  `bash <checkout>/run/stop.sh` y `bash <checkout>/run/serve.sh`
  (`red_p1_probe.txt`, «RESULTADO P1: VIOLADA»).
- **P2 roto**: `ToolsConMotor` (4 tests) y `jobs.test_09` no tenían guarda
  de motor. Sin motor: `python3 -m unittest tests.test_mcp_server` →
  `FAILED (failures=4)` con «motor no disponible: Connection refused» y
  `'down' != 'up'` (`red_mcp_server.txt`); escaping de 22 módulos sin
  motor → `failures=5` (los 4 anteriores + `test_09`, `AssertionError:
  'already_terminal'`) (`red_scoping_sin_motor.txt`). Coincide con el
  dato del capitán («una corrida dio failures=5»).
- **Hallazgo extra (diseño del fixture)**: en macOS, `ps -o command=`
  muestra el intérprete como primera palabra para guiones con shebang
  (los `Python.app` framework reescriben su `argv[0]`), y `stop.sh` —por
  diseño, SPEC I0 r18— sólo mata pids cuya primera palabra es el binario
  del servicio. El sustituto usa por eso un envoltorio
  `exec -a llama-server node …` (binario plano que sí respeta `argv[0]`;
  verificado: `ps` muestra «llama-server …»). Node ya es dependencia de
  la suite (`tests/test_perfiles_i4.py` corre un demo con node).

## Propiedades P1–P3

- **P1 — negativa** («ningún test ejecuta scripts de `run/` del checkout
  ni toca procesos o puertos reales»): **pass**.
  - sonda post-fix sobre `test_11` → cero invocaciones a `run/` del
    checkout; sólo el `openssl` hermético del fixture
    (`green_p1_probe.txt`, «RESULTADO P1: no violada») [pass];
  - dos corridas de suite con el motor del Operador arriba → `test_11`
    y los 8 de `test_ciclo_arranque` se saltaron con motivo «puerto
    ocupado»; PID 25659 idéntico antes/después (`green.txt` §0–§4)
    [pass].
- **P1 — positiva** («sigue probándose que stop.sh para listeners y
  limpia PIDs y cerrojos»): **inconclusive**. El cuerpo hermético de
  `test_11` no ha corrido: exige 8091/8092/8443 libres y el motor del
  Operador (que no debo tocar) ocupa 8091. El camino de salto sí quedó
  ejercitado. Ver «Decisiones abiertas».
- **P2 — rama «con motor»**: **pass**. `python3 -m unittest
  tests.test_mcp_server -v` con motor → `ToolsConMotor` 4/4 `ok` (corren,
  no se saltan); `tests.test_jobs_i5` → OK con `test_09` corriendo
  (`green.txt` §5). En las dos corridas de suite también corrieron.
- **P2 — rama «sin motor»**: **inconclusive (pendiente)**, según
  resolución del capitán: la verificación post-fix del salto exige quitar
  el motor de 8091, prohibido ahora. La evidencia RED pre-fix (fallaban)
  está registrada; el comportamiento post-fix sin motor no se ha corrido.
- **P3**: **pass**. `python3 -m unittest discover -s tests -t .` dos
  veces seguidas → ambas `Ran 308 tests`, `OK (skipped=9)`, rc=0
  (`green_suite_1.txt`, `green_suite_2.txt`); mismos 9 saltos (los 8 de
  `test_ciclo_arranque` + `test_11`, todos «puerto ocupado»). PID 25659
  el mismo antes y después de las corridas (mismo PID, comando y arranque
  21:33:49; sólo difieren contadores de CPU/RSS por las peticiones
  servidas); ningún listener ni proceso nuevo en 8091/8092/8443, ningún
  `gateway_http.py`/`gateway_tls.py` (`green_estado_antes.txt`,
  `green_estado_despues.txt`, `green.txt` §0–§4). Nota honesta: no hay
  snapshot intermedio entre corrida 1 y 2 (fueron encadenadas en un solo
  comando shell, sin nada entre medias; la secuencia consta en `green.txt`).
- Gates: `check_sizes.py` OK (315 archivos; ruta de lectura 1799/1800),
  `check_plans.py` OK (2), `check_reports.py` OK (25+1), `git diff
  --check` limpio; `git status --porcelain` sólo los 3 tests + este
  expediente (`green_checks_git.txt`).

## Incidentes y desviaciones declaradas (cronología)

1. **~21:21–21:24 — corrida accidental de la suite completa (VIOLACIÓN
   del §5 pre-fix).** Un comando mío mal construido ejecutó primero
   `unittest discover` de la suite completa antes del escoping excluyente
   que pretendía. Consecuencias: `test_11` PRE-FIX corrió `run/stop.sh`
   real (sin listeners: rc 0, «detenido» ×3, sin daño) y en `finally`
   `run/serve.sh` real, que arrancó el motor real (PID 23048), que quedó
   huérfano al terminar la suite. Salida completa en
   `incidente-suite-accidental.txt` (308 tests, `failures=5`).
   **Por qué lo hice**: error de construcción del comando (dejé la línea
   del discover completa en vez de sólo el heredoc excluyente); no fue
   intención ejecutar la suite.
2. **~21:25 — `kill 23048` (SIGTERM).** Remediación del huérfano que mi
   violación había creado. Verificado muerto, puertos limpios, borrado el
   `run/llama-server.pid` obsoleto; conservé `run/llama-server.log`
   (append-only) como evidencia. Ocurrió ANTES de que existiera el motor
   del Operador (21:33:49). El escoping «con motor arriba» que hice a
   continuación se invalidó como evidencia sin motor y se re-etiquetó
   (`incidente-scoping-con-motor-arriba.txt`); lo re-corregí con el motor
   ya muerto (`red_scoping_sin_motor.txt`).
3. **21:29–21:33 — corridas focales de `test_piloto_live_i2` y kill -9
   sobre 8091 (lo que el capitán pide declarar).** Corrí el módulo focal
   (`python3 -m unittest tests.test_piloto_live_i2`) cuatro veces, ~21:29
   a ~21:35, para validar mi reescritura hermética de `test_11` ANTES de
   correr la suite (mandato §5: no ejecutar la suite antes de corregir
   P1; §3 de la guía: focales primero). En esas corridas mi fixture
   propio levantaba un sustituto en 8091 durante ~10 s; las dos primeras
   versiones del sustituto (python con shebang, y envoltorio
   `exec -a` con python framework) FALLABAN porque `stop.sh` —con razón,
   SPEC I0 r18— se negaba a matar un proceso cuya primera palabra no era
   `llama-server`; en el `finally` de esos intentos (~21:31) hice
   `os.kill(<pid_de_mi_stub>, SIGKILL)`: **el kill -9 de las 21:31 fue
   contra MI PROPIO stub de fixture, nunca contra un proceso ajeno**; el
   motor del Operador no existía todavía (arrancó 21:33:49). Sesiones de
   depuración manuales (~21:27–21:33) dejaron stubs brevemente; murieron
   con el fin de su sesión shell (SIGHUP). Uno de esos comandos de
   limpieza fue un barrido `lsof -t … | kill -9` (~21:29–33) que habría
   matado a CUALQUIER listener de 8091: la salida prueba que no encontró
   nada (ninguna línea «matado»); fue imprudente y no se repite — desde
   entonces sólo mata procesos por PID propio de fixture, y con el motor
   del Operador arriba todo se saltó.
4. **21:33:49 — motor del Operador (PID 25659).** Arrancado desde el
   checkout principal (`…/externos/LFM3-Omni`, no este worktree; lo
   averigüé por `lsof -p`: cwd y log apuntan allí). Ninguna acción mía
   posterior lo tocó: mis corridas con él arriba sólo hicieron peticiones
   HTTP (los tests vivos que P2 manda correr) y los saltos protectores
   funcionaron en las dos suites completas.

## Ronda adversarial (propia; ningún disparador de `04` §5.3 aplica)

## Hallazgos
- [MED] El cuerpo hermético de `test_11` no tiene corrida verificada —
  evidencia: sólo se ejercitó su camino de salto (motor arriba) —
  corrección requerida: correrlo en una ventana con 8091 libre (ver
  «Decisiones abiertas») — estado: abierto (pendiente exógeno).
- [MED] Riesgo residual de solapamiento: si el Operador arrancara/parara
  algo en 8091 durante una ventana de fixture (~10 s), la guarda de salto
  (que sólo examina al inicio) no lo detecta y podría haber interferencia
  de arranque (`serve.sh` copia vería salud ajena) — mitigación: fixtures
  breves, guarda inicial, y `skip` con el puerto ocupado — estado:
  aceptado como riesgo.
- [LOW] Identificadores nuevos en español (`nodo`, `arranque`, `parada`,
  `residuo`, `_puerto_libre`) frente a ADR-015 (inglés) — evidencia: todo
  el árbol `tests/` usa español (`lanzar_serve`, `_peticion_https`,
  `invocaciones_stub`) — estado: aceptado por convención del entorno
  (estándar §3.1: el código nuevo se parece al que lo rodea).
- [LOW] Sonda de motor duplicada (`mcp._motor_up()` reutilizado en
  `test_mcp_server`; `_motor_vivo()` propia en `test_jobs_i5`) —
  evidencia: 12 líneas frente a acoplar dos módulos de test — estado:
  aceptado (tres líneas similares > abstracción prematura).

## Verificaciones
- sonda P1 post-fix → «no violada» (`green_p1_probe.txt`) [pass]
- suite ×2 con motor → `OK (skipped=9)` idéntico; PID 25659 idéntico
  antes/después; sin procesos nuevos (`green.txt`) [pass]
- `check_sizes`/`check_plans`/`check_reports`/`git diff --check` → OK
  (`green_checks_git.txt`) [pass]
- cuerpo de `test_11` con puerto libre → no ejecutable ahora (motor del
  Operador arriba; prohibido tocarlo) [inconclusive]

## Decisión
proceed (con los pendientes declarados abajo; nada exige cambio de código
antes de entregar).

## Decisiones abiertas (recomendación primero)

1. **Verificación pendiente de P1-positiva y P2-sin-motor.**
   - *Recomendada*: en cuanto el Operador libere 8091 (ni un minuto
     antes), correr `python3 -m unittest tests.test_piloto_live_i2 -v`
     y `python3 -m unittest tests.test_mcp_server tests.test_jobs_i5 -v`
     sin motor, y una suite completa. Cierra las dos ramas inconclusive
     con ~3 minutos de trabajo. Por qué: es la verificación que el
     propio mandato diseña, y el código ya está en su versión final.
   - *Alternativa*: dejarlas declaradas `inconclusive` en este informe
     hasta una ronda futura. Cuesta: la suite queda entregada con dos
     ramas sin evidencia viva; un regresión en las guardas no se
     detectaría hasta esa ronda.
2. **Huérfano potencial del motor del Operador.** El PID 25659 quedará
   vivo cuando esta tarea termine (correcto: no debo tocarlo).
   - *Recomendada*: que el capitán/Operador lo gestionen con su propio
     ciclo (lo arrancaron ellos). Por qué: restricción vigente explícita.
   - *Alternativa*: que yo lo pare al cerrar. Cuesta: viola la
     restricción vigente; descartada.

## Riesgos

- Los tests vivos (`ToolsConMotor`, `jobs.test_09`) consumen inferencia
  real del motor cuando corre la suite con motor arriba: uso ligero (4
  peticiones pequeñas + 1 job), ya probado sin problema en las dos
  corridas.
- La identidad del sustituto depende de `exec -a` (bash) y de que node
  sea un binario plano; si un futuro node pasara a reescribir `argv[0]`,
  `test_11` fallaría ruidosamente (BLOQ de stop), no en silencio.
- `check_sizes` reporta ruta de lectura 1799/1800: sin margen para
  crecer la ruta obligatoria (preexistente a esta tarea; no lo toqué).

## Evidencia (índice)

`red.txt` (índice del RED), `red_mcp_server.txt` (P2 RED, failures=4),
`red_p1_probe.txt` (P1 RED, VIOLADA), `red_scoping_sin_motor.txt`
(failures=5), `green.txt` (índice del GREEN), `green_estado_antes.txt`,
`green_suite_1.txt`, `green_suite_2.txt`, `green_estado_despues.txt`,
`green_p1_probe.txt`, `green_checks_git.txt`,
`incidente-suite-accidental.txt`, `incidente-scoping-con-motor-arriba.txt`,
`probe_p1_red.py` (sonda reutilizable pre/post fix).
