# Informe — fix-tests-hermeticos, intento 5

Ejecutor: agente en worktree
`/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-fix-tests-hermeticos`,
rama `agent/fix-tests-hermeticos`, HEAD `2449619` (intentos 1-4 en commit;
este intento queda sin commit para el capitán). Intento ACOTADO: el diseño
cerrado del intento 3 no se toca; sólo las tres correcciones del
mandato-intento-5 (hallazgos HIGH r17b y MED orden de cleanup de la ronda
4, más el mutante 4). Prohibiciones respetadas: ningún `kill`/`pkill`/
`stop.sh` mío contra procesos o puertos reales (señales a hijos directos
sólo por handle `Popen`), motor real no arrancado, alcance limitado a
`tests/` y este expediente (`green_checks_git-intento-5.txt`).

## Disposición de los 2 hallazgos de la ronda 4

1. **[HIGH] `r17b` puede pasar sin probar el rechazo por modelo efectivo**
   — **fixed.**
   - `test_r17b_atajo_idempotente_exige_modelo` ahora lee stderr y exige
     el motivo BLOQ exacto `responde /health pero sin el modelo efectivo`
     (`run/serve.sh:30`): queda probado que se tomó la rama del modelo
     equivocado y no la de puerto ocupado (`:37`), que también haría
     fallar sin «arriba» y sin invocar el motor.
   - Control positivo nuevo
     `test_r17c_idempotent_shortcut_with_effective_model`: un servicio
     ajeno con el modelo correcto produce `rc == 0`, stdout con
     `arriba: /health y modelo efectivo OK` y cero invocaciones del
     motor.
   - El `curl` sustituto YA distingue `/health` de `/v1/models`
     (`_CURL_SUBSTITUTE`: `*/health` → `{"status":"ok"}`;
     `*/v1/models` → id del registro `http_state`), así que no hacía
     falta corregirlo; lo que faltaba era PROBARLO: mutante 4 (abajo)
     mata el camino `/health` y r17b falla por la aserción nueva, y
     r17c prueba el camino positivo con el modelo correcto.
   - Determinismo de la rama: `wait_for_foreign_service(model_id)`
     (helper nuevo en `CicloArranqueBase`, apoyado en
     `HermeticFixture.http_state`) espera a que el servicio ajeno tenga
     listener VIVO **y** estado HTTP publicado: sin eso, la carrera
     listener-publicado/estado-http podía hacer que serve.sh tomara la
     rama de puerto ocupado por azar (el defecto exacto que la revisión
     señalaba, en versión intermitente).
2. **[MED] La limpieza se registra después de adquisiciones que pueden
   fallar** — **fixed.**
   - `TestPilotoPrivadoLive.setUpClass`: `_start_server` registra el
     `addClassCleanup` de cada servidor (backend, gateway, TLS) justo
     tras crearlo y ANTES de `Thread.start()`. `shutdown()` sólo se
     pide si el hilo llegó a correr (bandera `started`): contra un hilo
     que jamás arrancó, el `Event` de `serve_forever` nunca se pone y
     la limpieza se bloquearía para siempre — el guard lo hace seguro.
     El tmp ya registraba su limpieza tras la adquisición (ronda 3).
   - `HermeticFixture.__init__`: la preparación (`_prepare` +
     `_write_substitutes`) queda bajo `try/except BaseException` que
     borra el tmp y REPROPAGA el error. A esas alturas no existen
     procesos (sólo directorios y archivos), así que el borrado es
     seguro; es best-effort (`ignore_errors=True`) para no enmascarar
     el error original con uno de `rmtree` — distinto del borrado de
     `final_cleanup`, que sí propaga sus fallos.
   - Control determinista con `mock`:
     `SelfCleaningConstructor.test_prepare_failure_deletes_tmp_and_propagates`
     induce `OSError` en `_write_substitutes` (fallo a mitad de la
     preparación, el escenario exacto de la revisión), exige que el
     error se propague y que no quede ningún tmp con el prefijo del
     control en el directorio temporal.

Ambos `fixed`.

## Cambios por archivo (intento 5)

- `tests/test_ciclo_arranque.py` (252→301): constante
  `EFFECTIVE_MODEL_ID`; helper `wait_for_foreign_service`; r17b con
  lectura de stderr y aserción del motivo BLOQ; r17c nuevo (control
  positivo del atajo).
- `tests/hermetic_fixture.py` (678→707): `__init__` con autolimpieza de
  la preparación (nuevo `_prepare`); helper de consulta
  `http_state(port)`. Sin cambios en los sustitutos ni en el kill
  vigilado.
- `tests/test_piloto_live_i2.py` (657→674): `_start_server`
  (addClassCleanup antes de `Thread.start()`, con guard de `shutdown`)
  y `_close_server(server, started)`; los tres servidores pasan por él.
- `tests/test_hermetic_fixture.py` (206→232): control
  `SelfCleaningConstructor` con `mock` (imports `tempfile`,
  `unittest.mock`).
- Expediente: `mutacion-intento-5.sh` (extiende al de intento 3 con el
  mutante 4), `capturar-intento-5.py`, `focal-intento-5.txt`,
  `green_suite_1/2-intento-5.txt`, `mutantes-intento-5.txt`,
  `green_checks_git-intento-5.txt`, este informe.

## Salida real de las verificaciones

- **Focales con `-v`** (`focal-intento-5.txt`): ciclo 9 (incluye r17b
  reforzada y r17c nueva) + piloto 13 + fixture 8 (incluye el control
  nuevo) + sonda 7 = **37 tests, OK, 54,3 s**; fotos lsof/ps limpias
  antes y después.
- **Suite completa dos veces** (`green_suite_1/2-intento-5.txt`):
  `Ran 321 tests, OK (skipped=2)` en 122,0 s y 121,0 s (319 del intento
  4 + r17c + control del fixture). Fotos lsof/ps antes, entre (el
  «antes» de la segunda) y después: `(ninguno)` en todas. P3 en verde.
- **Mutación** (`mutantes-intento-5.txt`, script nuevo, sólo clon,
  ejecutado una vez): BASELINE test_11 rc=0, sonda rc=0, r17b rc=0;
  **MUTANTE 1 muere, MUTANTE 2 muere, MUTANTE 3 muere, MUTANTE 4
  muere**. El 4 falla exactamente por la aserción nueva: stderr del
  mutante dice `BLOQ: puerto 8091 ocupado por un proceso ajeno` y el
  test exige `responde /health pero sin el modelo efectivo` — el
  falso-positivo de la ronda 4 ya no pasa.
- **Gates y git** (`green_checks_git-intento-5.txt`):
  `check_sizes`/`check_plans`/`check_reports` rc=0 (más los dos drift
  del kit, rc=0); `git diff --check` rc=0 (también el rango
  `8b59118..HEAD`); `git status --porcelain` acotado a `tests/` +
  expediente.
- **Sin restos**: cero directorios `hermetic-*` y cero clones
  `mutacion-i5.*` en `${TMPDIR}`, cero procesos del fixture tras la
  batería (`pgrep` vacío).

## Propiedades P1-P3 (continuidad)

- **P1** — **pass**: fotos limpias; mutantes 1, 2 y 4 mordiendo; el
  atajo de r17b/r17c se ejercita con sustitutos sobre copias.
- **P2 sin motor** — **pass** (`skipped=2` en ambas suites). **P2 con
  motor** — **inconclusive** (sin motor; arrancarlo está prohibido) —
  atribución heredada.
- **P3** — **pass** (321 OK ×2, idéntico resultado).

## Decisiones abiertas (recomendación primero)

1. **Riesgo residual del PID reciclado dentro del mismo segundo**
   (heredado del intento 4, sin cambio aquí).
   - *Recomendada*: mantenerlo como residual documentado y agendar la
     tarea aparte de endurecer `run/stop.sh` (pidfile + lstart
     registrado al arrancar). Por qué: cierra la ventana en el
     PRODUCTO, donde vive el riesgo real, sin inflar el fixture; el
     kill vigilado ya exige inscripción + hora de inicio y las
     negativas quedan registradas (evidencia: controles del fixture y
     mutante 2). Coste de la alternativa: aislar la entrega de señales
     del host — fuera del alcance de `tests/` y desproporcionado.
2. **`ignore_errors=True` sólo en el borrado de emergencia de
   `__init__`** (elección de diseño de este intento).
   - *Recomendada*: conservarlo ahí y sólo ahí. Por qué: ese borrado
     corre dentro del `except` que repropaga el error original; si
     `rmtree` fallara y no se silenciara, sustituiría al error de
     preparación que el caller debe ver (la evidencia es el propio
     control: propaga `OSError` y sin tmp). Coste de la alternativa
     (propagar también el fallo de borrado): el caller perdería el
     motivo real del fallo de preparación por uno de filesystem.

## Riesgos

- Los del intento 4 siguen en pie (identidad `exec -a` dependiente de
  node; ventana mínima lectura-lstart→señal — residual nº 1 arriba;
  vigilancia atada a `BASH_ENV`; fidelidad de los sustitutos al
  mecanismo de descubrimiento actual de `run/`).
- `r17b`/`r17c` dependen del texto literal de los mensajes de
  `run/serve.sh` (`responde /health pero sin el modelo efectivo`,
  `arriba: /health y modelo efectivo OK`): si el runbook reescribe esos
  mensajes, los tests rompen a propósito (alarma, no adaptación
  silenciosa) — mismo criterio que `test_r16b` con el PATH.
- `check_sizes` reporta 1799/1800 en la ruta de lectura (preexistente):
  sin margen; este intento no la toca.

No se hizo commit: el capitán lo hace tras auditar.
