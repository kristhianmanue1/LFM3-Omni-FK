# Informe — fix-tests-hermeticos, intento 3

Ejecutor: agente en worktree
`/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-fix-tests-hermeticos`,
rama `agent/fix-tests-hermeticos`, HEAD `bbd6f8a` (intentos 1-2 en commit;
este intento queda sin commit para el capitán). Diseño cerrado del
mandato-intento-3 aplicado tal cual; prohibiciones respetadas: ningún
`kill`/`pkill`/`stop.sh` mío contra procesos o puertos reales, ninguna
señal desde Python a un PID leído de archivo, motor real no arrancado,
alcance limitado a `tests/` y este expediente (`git status --porcelain`
en `green_checks_git-intento-3.txt`). La suite completa y
`tests.test_ciclo_arranque` sólo se ejecutaron DESPUÉS de convertirlos.

## Disposición de los 6 hallazgos de la ronda 2

1. **[BLOCKER] BASH_ENV puede sustituir el lsof del fixture y reabrir el
   descubrimiento global.** — **fixed.** El entorno de las copias ya no
   copia `os.environ`: es el explícito mínimo del mandato (PATH anclado a
   `bin_dir` + directorios de sistema, HOME/TMPDIR/STUB_DIR al tmp, LANG=C
   y `BASH_ENV` apuntando al `fixture_env.sh` PROPIO del fixture); las
   copias corren siempre como `["/bin/bash", "--noprofile", "--norc",
   <script>]`. La única definición de función que puede entrar es la
   nuestra: el `kill` vigilado. Controles positivos de precedencia
   ejecutados: el `env` de un bash del fixture contiene exactamente la
   base más las adiciones internas del propio bash (`PWD`, `SHLVL`, `_`)
   y ningún `BASH_FUNC_*`; `type lsof` resuelve al ejecutable de `bin_dir`
   (no a función ni binario del host); `type kill` declara función
   (`focal-fixture-intento-3.txt`, 6 OK).
2. **[BLOCKER] Un PID reciclado todavía puede llegar a kill.** —
   **fixed.** `owned_pids` inscribe cada proceso del fixture como
   «pid hora_de_inicio» (el motor sustituto se inscribe solo antes del
   `exec`; los lanzados por el test, con `own()` al obtener el handle) y
   el `kill` vigilado sólo llama a `builtin kill` si la hora de inicio
   vigente (`/bin/ps -p PID -o lstart=`, también con LANG=C) coincide con
   la inscrita; en cualquier otro caso no señala, escribe la negativa en
   `kill_denied.log` y devuelve 1. Controles: PID ajeno no inscrito
   (denegado, sobrevive) e inscrito con hora falsa —reciclado—
   (denegado, sobrevive), ambos con negativa registrada
   (`focal-fixture-intento-3.txt`); en vivo, la corrida de delación de
   test_11 deja al ajeno vivo con `reason=not-registered` en el registro
   y el mutante 2 (kill permisivo) muere (`mutantes-intento-3.txt`).
3. **[HIGH] P1 global no se cumple en `test_ciclo_arranque` (enlazaba el
   8091 real).** — **fixed.** `test_ciclo_arranque.py` convertido al
   fixture: ningún proceso enlaza puerto alguno; los escenarios r13-r18
   se expresan con el registro de listeners y el estado HTTP de los
   sustitutos. Auditoría de la suite: los únicos `bind` reales son
   efímeros `("127.0.0.1", 0)` (grep en el expediente de trabajo; única
   excepción histórica, `sondas_multimodal.py`, es herramienta manual que
   no descubre `unittest`). Ciclo en verde dos veces dentro de las
   suites de 317 (`green_suite_1/2-intento-3.txt`).
4. **[HIGH] La limpieza podía borrar el centinela sin confirmar la
   salida.** — **fixed.** Toda adquisición va en `addCleanup`; los hijos
   directos se terminan por handle `Popen` (`terminate_handle`); los
   nacidos de `serve.sh` salen por centinela y `stop_and_verify`
   EXIGE que todos los PIDs inscritos hayan salido: si algo sobrevive
   tras el plazo, la prueba FALLA con el PID y su hora de inicio
   inscrita, y el centinela nunca se borra antes de confirmar. El tmp se
   borra al final (registrado primero, LIFO). Sin restos tras las dos
   suites ni tras ninguna corrida focal (estados «(ninguno)» en todas
   las evidencias).
5. **[MED] El control de ausencia de la sonda no era determinista
   (puerto efímero liberado).** — **fixed.** La rama de ausencia
   verificada usa `mock` con `URLError(ConnectionRefusedError())`; los
   servidores falsos quedan para las ramas con respuesta. Añadido además
   `test_transport_error_is_not_absence` (`URLError(TimeoutError)`) que
   pinza la rama «error de sonda con motivo» — la que el mutante 3 rompe
   (`mutantes-intento-3.txt`, MUTANTE 3 muere).
6. **[LOW] `tests/test_sonda_motor.py` con nombre en español.** —
   **fixed.** Renombrado a `tests/test_engine_probe.py`; identificadores
   a inglés (clase `DeterministicEngineProbe`, métodos `test_engine_up`,
   `test_verified_absence`, `test_malformed_response`, `test_error_5xx`,
   `test_status_not_ok`, `test_probe_timeout`). Docstrings y comentarios
   en español.

Los seis hallazgos quedan cerrados: seis `fixed`.

## Cambios por archivo (intento 3)

- `tests/hermetic_fixture.py` (nuevo): utilidad compartida del mandato
  §1 — tmp + `bin_dir` con los sustitutos `lsof` y `curl` (multi-PID,
  fieles al zombie), wrapper del motor con autoinscripción de nacimiento
  e identidad `argv[0]=llama-server` vía `exec -a`, ajeno de control,
  sustitutos de listeners, entorno explícito mínimo, `kill` vigilado por
  `BASH_ENV`, limpieza por handle + centinela con verificación y
  `wait_identity` (ver riesgos).
- `tests/test_hermetic_fixture.py` (nuevo): los seis controles
  deterministas del fixture (entorno, precedencia, y las tres ramas del
  kill vigilado).
- `tests/test_engine_probe.py` (nuevo) en lugar de
  `tests/test_sonda_motor.py` (borrado): renombrado a inglés + rama de
  ausencia con `mock` + control de error de transporte (7 tests).
- `tests/test_piloto_live_i2.py`: sólo `test_11`, reescrito sobre el
  fixture (node para la identidad del sustituto, como el intento 2):
  parada legítima (rc 0, tres «detenido», tres muertes, cero negativas,
  cerrojos limpios) y corrida de delación (lsof delata al ajeno, kill
  niega, ajeno vivo, stop.sh falla cerrado). Fuera `_pid_alive` y todo
  el fixture inline del intento 2; import del fixture compartido.
- `tests/test_ciclo_arranque.py`: conversión completa r13-r18 al patrón
  hermético (misma intención en cada aserción; cambios de forma abajo).
- Expediente: `capturar-intento-3.py`, `mutacion-intento-3.sh`,
  `mutantes-intento-3.txt` (y `-abortado.txt`, ver mutantes),
  `focal-intento-3.txt`, `focal-fixture-intento-3.txt`,
  `green_suite_1/2-intento-3.txt`, `green_checks_git-intento-3.txt`.

## Cambios de forma declarados (mandato §5: sin debilitar aserciones)

- **Ciclo, readiness y ocupante:** `salud_disponible()`/`puerto_libre()`
  (que tocaban el 8091 real) pasan a ser `listener_alive(8091)` sobre el
  registro del fixture; el ocupante ajeno de r15 es una línea suya en el
  registro en vez de un socket real. El atajo idempotente de serve.sh
  sigue ejerciéndose vía el `curl` sustituto (r17b).
- **Ciclo r14:** el `_matar_todo` entre escenarios es ahora baja del
  registro + verificación de que el sustituto salió solo al verse dado
  de baja: el segundo arranque sigue ejercitando el cerrojo, no el atajo
  (la intención original), y desaparecen las señales del fixture.
- **Ciclo r17b:** el conteo de invocaciones pasa de `== 1` a `== 0`: el
  servicio ajeno ya no pasa por el wrapper que escribe el marcador; la
  aserción sigue significando «el atajo no lanzó ningún motor».
- **test_11, segunda parada (control de delación):** se ESPERA rc != 0
  con «sigue en escucha»: con un listener ajeno vivo que no puede
  señalar, `stop.sh` debe fallar cerrado en vez de declarar el puerto
  libre. El ajeno sobrevive ahora CON el lsof delatándolo (en el
  intento 2 sobrevivía porque no era visible).
- **Sustituto del motor:** dos variantes. Con `node_bin` (test_11) hay
  identidad `argv[0]=llama-server`; sin él (ciclo) el sustituto corre en
  Python SIN identidad: el Python de macOS (build framework) reescribe
  `argv[0]` tras `exec -a` (verificado en depuración: ps mostraba al
  intérprete), y el ciclo no ejecuta `stop.sh` contra el motor, así que
  no la necesita y conserva su dependencia cero de node.
- **`kill -0`:** el vigilante delega la señal 0 sin registro: es una
  sonda de existencia que no entrega señal alguna, y `serve.sh` sondea a
  su hijo recién nacido antes de que el wrapper termine de inscribirlo
  (negarla ahí era una carrera de arranque: BLOQ espurio «el motor
  murió»). Las señales reales siguen vigiladas al 100 %.

## Propiedades P1-P3

- **P1 (negativa)** — ningún test ejecuta scripts de `run/` del checkout
  ni toca procesos/puertos reales: **pass.** Sólo hay `copy2` de
  `run/` hacia el tmp y ejecución de las copias con bash anclado
  (auditoría grep: cero ejecuciones directas; cero binds a
  8091/8092/8443 en la suite); estados «(ninguno)» antes/después en
  todas las evidencias.
- **P1 (positiva)** — sigue probándose que `stop.sh` para listeners y
  limpia PIDs y cerrojos: **pass.** `test_11` completo (tres puertos,
  tres procesos, cerrojos y pidfiles) y r18 en verde
  (`focal-intento-3.txt`, 27 tests OK); los mutantes 1 y 2 demuestran
  que las aserciones muerden.
- **P2 (sin motor)** — saltos con motivo explícito, comprobado una vez:
  **pass.** Ambas suites: `OK (skipped=2)` (guardas de
  `ToolsConMotor` y `jobs.test_09`, «conexión rehusada, nada escucha»);
  las ramas de la sonda con controles deterministas en verde.
- **P2 (con motor)** — se ejecutan cuando lo hay: **inconclusive** en
  esta ronda (no hay motor y arrancarlo está prohibido); misma
  atribución de rondas previas que el intento 2.
- **P3** — dos corridas seguidas idénticas y sin restos: **pass.**
  `Ran 317 tests, OK (skipped=2), rc=0` dos veces (317 = 310 del
  intento 2 + 6 del fixture + 1 del control de transporte de la sonda),
  con fotos limpias antes, entre y después
  (`green_suite_1/2-intento-3.txt`).

## Mutantes (salida íntegra en `mutantes-intento-3.txt`)

BASELINE en verde sobre el clon (test_11 rc=0; sonda rc=0) y:

- **MUTANTE 1 muere** — sin `detener_puerto 8443`, test_11 falla en
  `AssertionError: 'detenido: sin escucha en 8443' not found`.
- **MUTANTE 2 muere** — con el kill permisivo, la parada mata al ajeno
  delatado y declara el 8091 libre: falla `stop.sh declaró el 8091 libre
  con un listener ajeno vivo`.
- **MUTANTE 3 muere** — la sonda que toma el error como ausencia falla
  en `test_transport_error_is_not_absence` (`reason` None).

Nota de proceso: la PRIMERA ejecución del guion abortó en el BASELINE
(`mutantes-intento-3-abortado.txt`): el clon destapó una carrera real —
el `ps` inmediato tras lanzar al ajeno veía al `/bin/bash` del wrapper
antes del `exec -a`. Corregida con `wait_identity` (espera acotada de
identidad ante ps); tras verificar test_11 tres veces en verde en un
clon de diagnóstico, se ejecutó el guion una única vez completo. El
worktree nunca fue mutado: el guion sólo trabaja en `git clone --local`
dentro de `mktemp -d`.

## Verificación del mandato (índice de evidencia)

`focal-intento-3.txt` (piloto 12 + ciclo 8 + sonda 7 = 27, `-v`),
`focal-fixture-intento-3.txt` (6 controles del fixture),
`mutantes-intento-3.txt` (baseline + 3 mutantes),
`green_suite_1-intento-3.txt` y `green_suite_2-intento-3.txt` (317 OK ×2
con estado lsof/ps antes/después; el «antes» de la segunda es la foto
«entre»), `green_checks_git-intento-3.txt` (3 gates del AGENTS.md rc=0,
más los dos de drift del kit, `git diff --check` rc=0 y
`git status --porcelain` acotado a `tests/` + expediente).

## Decisiones abiertas (recomendación primero)

1. **Verificación de P2-con-motor** cuando haya motor de verdad.
   - *Recomendada*: en cuanto el Operador arranque su motor, correr
     `python3 -m unittest tests.test_mcp_server tests.test_jobs_i5 -v` y
     ver las guardas no saltar. Por qué: es la única rama sin evidencia
     viva y cierra en un minuto. Coste de la alternativa: la suite se
     entrega con esa rama declarada inconclusive (atribuida).
   - *Alternativa*: dejarla como `inconclusive` documentada. Coste: un
     regresión con motor vivo no se detectaría hasta esa corrida.
2. **Delegación de `kill -0` sin registro.**
   - *Recomendada*: conservarla, documentada en el propio fixture. Por
     qué: la señal 0 no entrega señal (la propiedad «ningún PID ajeno
     recibe señal» se conserva) y negarla crea una carrera de arranque
     real, demostrada en depuración (BLOQ espurio). Coste de la
     alternativa: arrancques intermitentes de todos los escenarios con
     motor.
   - *Alternativa*: exigir registro también para el `-0` con una espera
     en el wrapper antes del exec. Coste: más piezas móviles en el
     arranque y sigue habiendo una ventana.
3. **Sustituto del motor en Python (sin identidad) para el ciclo.**
   - *Recomendada*: conservarlo. Por qué: el ciclo no ejecuta `stop.sh`
     contra el motor (r14 usa la baja del registro) y así mantiene su
     dependencia cero de node, igual que su diseño original. Coste de la
     alternativa (node en todo): sin node se perderían los 8 tests del
     ciclo en vez de sólo test_11.
   - *Alternativa*: usar node también en el ciclo. Coste: salto en
     cascada si node falta; doble superficie de sustitutos activa.

## Riesgos

- La identidad `exec -a llama-server` depende de node como binario plano
  (riesgo heredado del intento 2, sigue cierto): si node dejara de
  respetar `argv[0]`, test_11 falla ruidosamente, no en silencio.
- El vigilante tiene una ventana mínima entre comprobar la hora de
  inicio y entregar la señal: un PID reciclado dentro de esa ventana
  recibiría la señal. No eliminable sin handles de kernel; queda
  acotada por la comprobación de identidad inmediatamente anterior.
- La vigilancia entera descansa en `BASH_ENV`: si bash dejara de
  honrarlo para shells no interactivos, el `kill` volvería a ser el
  builtin — y test_11 fallaría ruidosamente (el ajeno delatado moriría)
  y `test_kill_vigilado_definido_por_el_fixture` con él.
- La fidelidad de los sustitutos `lsof`/`curl` ata los tests al
  mecanismo de descubrimiento actual de `run/`: si cambia (pidof,
  puertos reales), los tests fallan — que es lo buscado.
- `check_sizes` reporta la ruta de lectura en 1799/1800 (preexistente):
  sin margen para que la ruta obligatoria crezca; este intento no la
  toca (sus archivos viven en `tests/` y el expediente).
