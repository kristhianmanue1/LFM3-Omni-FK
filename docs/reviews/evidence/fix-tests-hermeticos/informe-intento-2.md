# Informe — fix-tests-hermeticos, intento 2

Ejecutor: agente en worktree
`/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-fix-tests-hermeticos`,
rama `agent/fix-tests-hermeticos`, base `main` `60c6568`. Fecha: 2026-11-07
(noche). Alcance del mandato original respetado: sólo `tests/` y este
expediente (`git status --porcelain` lo confirma; ver
`green_checks_git-intento-2.txt`). Restricciones añadidas del intento 2
cumplidas: ningún `kill`/`pkill`/`lsof|kill`/`stop.sh` mío contra procesos
o puertos reales; ningún proceso terminado mediante un PID leído de
archivo; motor real no arrancado (sigue sin haber motor en esta máquina:
línea base de todos los archivos de evidencia, listeners y procesos
«(ninguno)» antes y después de cada corrida).

## Disposición de los hallazgos de la revisión adversarial

1. **[BLOCKER] Carrera contra procesos reales / lsof global.** —
   **fixed.** Adopté el diseño recomendado por el capitán, sin
   desviación estructural: en `bin_dir` viven un `lsof` y un `curl`
   sustitutos que sólo responden desde el estado propio del fixture
   (`STUB_DIR/listeners/PUERTO`, inscrito por los propios procesos del
   fixture). Los procesos sustitutos de 8091, 8092 y 8443 no enlazan
   puerto real alguno; basta con que el `lsof` sustituto los reporte
   mientras vivan (con fidelidad añadida: un zombie —muerto sin
   recoger— ya no tiene sockets y el `lsof` real jamás lo listaría,
   así que el sustituto tampoco). `stop.sh` sólo puede descubrir PIDs
   del pidfile de la copia (escrito por la propia `serve.sh` copia) o
   del registro del fixture: ningún PID ajeno puede llegar a `kill`, y
   la guarda de puertos ocupados desapareció (era la única razón de
   salto además de node). Control positivo incluido y ejecutado: un
   proceso «ajeno» lanzado por el test con comando
   `llama-server … --port 8091` (argv[0] real vía `exec -a`, verifica
   `ps` antes de la parada) que el fixture NO inscribe sobrevive a la
   copia de `stop.sh` (`focal-test_piloto-intento-2.txt`, test_11 ok;
   traza completa en `p1-probe-intento-2.txt`). Desviación menor
   declarada: además del `lsof` sustituto hace falta un `curl`
   sustituto, porque `serve.sh` sondea la readiness con `curl` contra
   `127.0.0.1:8091` y ya nada enlaza ese puerto; el `curl` sustituto
   resuelve por el mismo registro (misma fuente de verdad, sin estado
   nuevo).
2. **[HIGH] Limpieza incompleta / os.kill sobre PIDs de archivo.** —
   **fixed.** Toda adquisición va en `addCleanup` (LIFO): `rmtree` del
   tmp registrado primero (corre al final), terminación por handle
   `Popen` (`terminate`/`wait`/`kill` del handle) para gateway, TLS y
   el proceso ajeno del control, y salida por centinela (`apagar`) para
   los procesos que `serve.sh` engendra y de los que el test no puede
   tener handle: el sustituto comprueba su propio entorno y sale solo;
   ninguna señal sale del fixture y la reutilización de PIDs queda
   fuera de juego por construcción (nadie señaliza a un PID). El
   `os.kill(int(pidfile), SIGKILL)` del intento 1 desapareció. Cobertura
   ejecutada de los tres caminos que pedía el hallazgo — node ausente
   (skip antes de crear nada), error de preparación (copy2 roto con
   procesos ya lanzados) y timeout del arranque con motor sustituto ya
   huérfano (`STUB_BROKEN=1` + timeout de 8 s) — con cero restos (ni
   directorios `i2-parada-*` ni procesos del fixture) tras cada caso:
   `limpieza-intento-2.txt`, RESULTADO LIMPIEZA: OK.
3. **[HIGH] Saltos por falso negativo de la sonda.** — **fixed.** Nueva
   sonda compartida `tests/engine_probe.py` (`probe_engine`) que
   distingue la ausencia verificada (conexión rehusada:
   `ConnectionRefusedError` directa o como `reason` de `URLError`) del
   error de sonda (respuesta malformada, timeout, 5xx, status distinto
   de ok, otro error de transporte). Sólo la ausencia verificada salta;
   el error de sonda hace FALLAR la guarda con su motivo
   (`AssertionError`/`self.fail` con el motivo exacto), y ambas guardas
   se evalúan una sola vez al importar (P2 del mandato original).
   `test_mcp_server` usa `setUpClass` de `ToolsConMotor` (skip de clase
   con motivo; error de sonda → la clase falla) y `test_jobs_i5` lleva
   la guarda al cuerpo de `test_09`. Controles deterministas de las dos
   ramas con servidores falsos en puertos efímeros: 6 tests en
   `tests/test_sonda_motor.py` (arriba, ausencia verificada, malformada,
   5xx, status≠ok, timeout), en verde (`focal-sonda-intento-2.txt`). El
   comportamiento vivo sin motor quedó ejercitado: ambas guardas saltan
   hoy con motivo «conexión rehusada, nada escucha»
   (`focal-guardas-intento-2.txt`, skipped=2, rc=0).
4. **[HIGH] test_11 no probaba 8092 y 8443.** — **fixed.** Procesos
   sustitutos de gateway y TLS con comandos que pasan el patrón real de
   `stop.sh` (`gateway_http.py`, `gateway_tls.py` en la línea de
   comando real que ve `ps`), inscritos como listeners 8092/8443 en el
   registro del fixture. El test verifica las tres líneas
   «detenido: sin escucha en {8443, 8092, 8091}», la muerte de los tres
   procesos (motor vía `ps` con relevancia de zombie, gateway/TLS vía
   handle) y la limpieza de `llama-server.pid`, `serve.lock`,
   `serve_pilot.lock`, `gateway.pid` y `tls.pid`. Invertir la lógica de
   parada de cualquiera de los tres puertos rompe el test (falta la
   línea, sobrevive el proceso o queda el residuo). Advertencia honrada
   del desarrollo: la primera versión del sustituto listaba como LISTEN
   a procesos muertos-sin-recoger (zombies hijos del test) y `stop.sh`
   BLOQeaba 8443/8092; se corrigió siendo fiel al `lsof` real (un
   zombie no tiene sockets). El fallo se detectó y corrigió antes de
   cerrar la evidencia.
5. **[MED] Evidencia P1 vacua (skip por puerto ocupado).** — **fixed.**
   `probe_p1_intento2.py` repite la sonda sobre el `test_11` nuevo con
   el cuerpo EJECUTADO (el grabador delega todo lo que no apunta a
   `run/` del checkout, y aborta con VACUA si el test no pasa): registra
   las invocaciones de la `serve.sh` y la `stop.sh` TEMPORALES
   (`/var/folders/.../i2-parada-.../serve.sh` y `stop.sh`), ninguna
   ruta de `run/` del checkout, y test_11 ok. Resultado: «P1: no
   violada (cuerpo ejecutado, copias temporales)»
   (`p1-probe-intento-2.txt`). El camino de salto que quedó (sólo node
   ausente) ya no depende del estado de la máquina.
6. **[MED] Identificadores nuevos en español.** — **fixed.** Renombrado
   a inglés todo lo añadido en los intentos 1 y 2: `_pid_alive`,
   `node_bin`, `startup`, `stop_run`, `leftover`, `deadline`, `env`,
   `gateway`, `tls`, `foreign`, `cmdline`, `terminate`,
   `stop_substitutes`, `ENGINE_UP`/`PROBE_ERROR`/`probe_engine`
   (desaparecen `_puerto_libre`, `_pid_vivo`, `_motor_vivo`,
   `MOTOR_VIVO`, `nodo`, `arranque`, `parada`, `residuo`, `fin`,
   `pid_stub`, `salida` local, `comando`). Los scripts del fixture
   (bash/python/node dentro del test) usan identificadores en inglés.
   Docstrings y comentarios siguen en español (verificado con grep; los
   únicos restos españoles son comentarios, mensajes y el prefijo de
   tmp `i2-parada-`, que no es identificador).

Los seis hallazgos de la revisión quedan cerrados: seis `fixed`.

## Cambios por archivo (intento 2)

- `tests/engine_probe.py` (nuevo, 60 líneas): sonda tri-estado
  compartida por las guardas de motor de la suite.
- `tests/test_sonda_motor.py` (nuevo, 126 líneas): seis controles
  deterministas de la sonda con servidores falsos en puertos efímeros.
- `tests/test_piloto_live_i2.py`: `test_11` reescrito al diseño de
  aislamiento por descubrimiento (`lsof`/`curl` sustitutos sobre
  `STUB_DIR/listeners`, procesos sin puertos reales, control positivo
  ajeno, limpieza por handle + centinela, cobertura 8443/8092/8091);
  fuera `_puerto_libre`, la guarda de puertos y el `os.kill` de
  archivo; imports `signal`/`socket` eliminados; `_pid_alive`.
- `tests/test_mcp_server.py`: guarda de motor vía `probe_engine` +
  `setUpClass` de `ToolsConMotor` (skip con motivo / fallo con motivo);
  docstring del módulo actualizado.
- `tests/test_jobs_i5.py`: `_motor_vivo`/`MOTOR_VIVO` sustituidos por
  la sonda compartida; guarda en el cuerpo de `test_09`.
- Expediente: `capturar-intento-2.py` (estado antes/después de cada
  corrida), `probe_p1_intento2.py`, `probe_limpieza_intento2.py` y los
  `*-intento-2.txt` de evidencia.

## Propiedades P1–P3

- **P1 (negativa)** — ningún test ejecuta scripts de `run/` del
  checkout ni toca procesos/puertos reales: **pass**. Sonda con cuerpo
  ejecutado, copias temporales registradas, cero rutas del checkout
  (`p1-probe-intento-2.txt`); suites con estado «(ninguno)» antes y
  después.
- **P1 (positiva)** — sigue probándose que `stop.sh` para listeners y
  limpia PIDs y cerrojos: **pass**, ahora para los TRES puertos y sin
  depender de que 8091 esté libre: `test_11` ok con cuerpo completo
  (`focal-test_piloto-intento-2.txt`); el inconclusive del intento 1
  queda cerrado.
- **P2 (sin motor)** — los tests que requieren motor se saltan con
  motivo explícito, comprobado una vez: **pass** con evidencia viva
  (no hay motor en la máquina): `ToolsConMotor` (clase) y `jobs.test_09`
  saltan con «conexión rehusada, nada escucha»
  (`focal-guardas-intento-2.txt`); las dos ramas de la sonda tienen
  controles deterministas en verde (`focal-sonda-intento-2.txt`).
- **P2 (con motor)** — se ejecutan cuando lo hay: **inconclusive** en
  esta ronda (no hay motor y arrancarlo está prohibido). Evidencia
  atribuida de rondas previas: intento 1 con el motor del Operador
  (`green.txt` §5 del expediente) y la auditoría del capitán citada por
  el revisor. El código de la rama es el mismo que corrió entonces
  (aserciones intactas); lo único nuevo es la guarda, cubierta de forma
  determinista.
- **P3** — dos corridas seguidas idénticas y sin restos: **pass**.
  `Ran 310 tests, OK (skipped=2), rc=0` dos veces (310 = 308 del
  intento 1 + 6 de la sonda − 4 métodos de `ToolsConMotor` que ahora se
  saltan como una sola entrada de clase + 0; los 2 skips son las dos
  guardas de motor), sin listeners en 8091/8092/8443 ni procesos
  `llama-server`/`gateway_*` nuevos, con estado capturado antes y
  después de cada corrida (`green_suite_1-intento-2.txt`,
  `green_suite_2-intento-2.txt`).

## Verificación del mandato (índice de evidencia)

`focal-test_piloto-intento-2.txt` (12 tests OK, test_11 con cuerpo),
`focal-sonda-intento-2.txt` (6 OK), `focal-guardas-intento-2.txt`
(44 tests, skipped=2 con motivo), `limpieza-intento-2.txt` (3 casos de
fallo, cero restos), `p1-probe-intento-2.txt` (P1 no violada, no
vacua), `green_suite_1-intento-2.txt` y `green_suite_2-intento-2.txt`
(310 OK ×2), `green_checks_git-intento-2.txt` (gates y git). Todos con
estado lsof/ps antes y después (comandos del mandato vía
`capturar-intento-2.py`; la línea del propio grep se excluye del ps).

## Ronda adversarial propia

Sobre el diff final, intentando refutarlo:

- El zombie: encontrado y corregido en caliente (hallazgo 4 arriba);
  la corrección se probó re-corriendo test_11 y las suites.
- ¿Puede un PID ajeno llegar a kill? Fuentes de PIDs de `stop.sh`: el
  pidfile de la copia (sólo lo escribe la `serve.sh` copia) y el
  `lsof` sustituto (sólo lista PIDs inscritos por los procesos del
  fixture y no-zombies). El control ajeno demuestra la propiedad en
  vivo. No encontré otra vía: `es_proceso_servicio` usa `ps` real y
  `kill` es builtin.
- ¿Puede el fixture colgarse? `stop_substitutes` espera acotada (5 s);
  `terminate` con `wait(timeout=5)` y `kill` del handle como respaldo;
  `subprocess.run` con timeout 120/60. El centinela escribe en el tmp
  del fixture (nadie más lo lee).
- ¿Se debilitó algo del intento 1? Las aserciones de `test_11` sólo
  crecieron (tres puertos, tres procesos, ajeno vivo); `ToolsConMotor`
  y `test_09` conservan sus aserciones intactas; nadie se borra.

## Decisiones abiertas (recomendación primero)

1. **Verificación de P2-con-motor** cuando haya motor de verdad.
   - *Recomendada*: en cuanto el Operador arranque su motor (decisión
     suya; yo no puedo), correr
     `python3 -m unittest tests.test_mcp_server tests.test_jobs_i5 -v`
     y ver las guardas no saltar. Por qué: es la única rama sin
     evidencia viva de esta ronda y cierra en un minuto. Coste de la
     alternativa: la suite se entrega con esa rama declarada
     inconclusive (atribuida a rondas previas).
   - *Alternativa*: dejarla como `inconclusive` documentada. Coste: un
     regresión en la sonda con motor vivo no se detectaría hasta esa
     corrida.
2. **`STUB_BROKEN` como púa de control en `stub_llama.js`.** Es un
   rodeo deliberado para el caso C de la sonda de limpieza (motor
   huérfano tras timeout).
   - *Recomendada*: conservarlo (documentado en el propio test; sólo lo
     fija el script del expediente en su propio proceso). Por qué:
     sin él no hay forma determinista de ejercer el timeout con
     huérfano real. Coste de quitarlo: pierde la cobertura C.
   - *Alternativa*: mover el caso C a un test propio con fixture
     duplicado. Coste: más superficie de fixture que mantener.

## Riesgos

- La fidelidad del `lsof`/`curl` sustitutos depende de `ps` real y del
  registro del fixture; si `stop.sh` cambiara su mecanismo de
  descubrimiento (p. ej. pidof, puertos reales), `test_11` fallaría
  ruidosamente — alarmar está bien ahí.
- La identidad `exec -a llama-server` depende de node como binario
  plano (ya riesgo declarado del intento 1); si node dejara de
  respetar argv[0], test_11 falla ruidosamente, no en silencio.
- `check_sizes` reporta ruta de lectura 1799/1800: sin margen para
  crecer la ruta obligatoria (preexistente; este intento añadió 5
  archivos de texto a `tests/` y expediente, dentro de límites de
  tamaño).
- La rama P2-con-motor sigue sin corrida viva en esta ronda (ver
  decisiones abiertas).
