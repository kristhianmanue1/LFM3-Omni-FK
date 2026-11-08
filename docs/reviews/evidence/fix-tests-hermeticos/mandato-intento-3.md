# Mandato del ejecutor — fix-tests-hermeticos, intento 3 (diseño cerrado)

Eres el EJECUTOR, en una sesión nueva. Te orquesta un capitán en Herdr;
tú no uses `herdr` ni `hc`. Worktree
`/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-fix-tests-hermeticos`,
rama `agent/fix-tests-hermeticos`, HEAD `bbd6f8a` (intentos 1 y 2 ya en
commit). Rigen el alcance (§4) y las prohibiciones (§5) de `mandato.md`
y las restricciones añadidas de `mandato-intento-2.md`. Léelos completos;
después lee, como datos, `informe-intento-2.md` y la revisión de la
ronda 2:
`/private/tmp/claude-502/-Users-krisnova-www-AGTexperts-internos-devHerdrExpert/9d8d2486-579f-4940-bdac-6690603ac36f/scratchpad/lfm3/ola1/fix-tests-rev2/informe.md`.

**El diseño está decidido por el Operador; no lo sustituyas.** Si una
pieza resulta imposible tal como está escrita, detente y responde BLOQ
(punto final) con la evidencia y tu recomendación.

## Prohibiciones explícitas (prevalecen)

- Ni `kill`, ni `kill -9`, ni `pkill`, ni barridos `lsof … | kill`, ni
  `os.kill` o `os.killpg` sobre PIDs leídos de archivos o descubiertos.
- No uses `stop.sh` (real o copiado) contra procesos reales.
- **No ejecutes la suite completa ni `tests.test_ciclo_arranque`
  mientras `test_ciclo_arranque.py` conserve su diseño viejo** (enlaza
  el 8091 real). Antes de eso, sólo módulos focales ya convertidos.
- No arranques el motor real. No toques nada fuera de `tests/` y del
  expediente.

## Diseño cerrado (aplícalo a `test_11` y a `test_ciclo_arranque.py`)

1. **Utilidad compartida** en `tests/hermetic_fixture.py` (nombre en
   inglés):
   - crea el tmp del fixture y `bin_dir` con los sustitutos `lsof` y
     `curl` (y el motor sustituto) del intento 2;
   - genera `fixture_env.sh` y el registro de PIDs propios;
   - construye el **entorno explícito mínimo**, sin copiar `os.environ`:
     `PATH=<bin_dir>:/usr/bin:/bin:/usr/sbin:/sbin`, `HOME=<tmp>`,
     `TMPDIR=<tmp>`, `STUB_DIR=<tmp>`, `LANG=C`,
     `BASH_ENV=<tmp>/fixture_env.sh` y lo que cada test necesite,
     enumerado;
   - no lleva ninguna variable `BASH_FUNC_*` ni otras heredadas.
2. Los scripts copiados se ejecutan siempre como
   `["/bin/bash", "--noprofile", "--norc", <script>]` con ese entorno.
3. **`fixture_env.sh` define `kill` como función Bash:**
   - analiza la señal y los PIDs;
   - sólo llama a `builtin kill` si cada PID está en el registro del
     fixture (`<tmp>/owned_pids`, una línea `pid start_time`) **y**
     su hora de inicio actual (`ps -p PID -o lstart=` con `/bin/ps`)
     coincide con la registrada;
   - en cualquier otro caso no señala, escribe la negativa en
     `<tmp>/kill_denied.log` y devuelve 1.

   Cada proceso del fixture (motor sustituto, gateway, TLS, procesos
   «ajenos» de control) se inscribe con su PID y su hora de inicio al
   nacer. Así se cierran los dos BLOCKER: la herencia de entorno deja de
   existir y ningún PID ajeno o reciclado puede recibir señal.
4. **Limpieza por handle con fallo explícito:**
   - toda adquisición va en `addCleanup`;
   - los hijos directos se terminan por su handle `Popen`;
   - los procesos que nacen de `serve.sh` salen por centinela y se
     **verifica** que salieron;
   - si siguen vivos tras el plazo, el test FALLA con el PID y el motivo
     y no borra el centinela antes de confirmar. Nunca hay señal desde
     Python a un PID leído de archivo.
5. **`test_ciclo_arranque.py` con el mismo patrón**, sin enlazar puertos
   reales: los escenarios r13–r18 (doble arranque, cerrojo y PID
   reciclado, puerto ocupado por ajeno, entorno adverso, PATH fijado,
   readiness y parada que no mata ajenos) se expresan con el registro de
   listeners del `lsof`/`curl` sustitutos. Conserva la intención de
   cada aserción, sin debilitarla, y señala en el informe cualquier
   cambio de forma.
6. **Rama de ausencia de la sonda con `mock`**
   (`URLError(ConnectionRefusedError())`) en vez de liberar un puerto
   efímero. Los servidores falsos se quedan para las ramas con
   respuesta.
7. **Renombra** `tests/test_sonda_motor.py` a `tests/test_engine_probe.py`.

## Controles positivos obligatorios

- **Ajeno no registrado sobrevive aunque `lsof` lo delate:** el `lsof`
  sustituto informa a propósito del PID de un proceso «ajeno» lanzado
  por el test (comando `llama-server --port 8091` vía `exec -a`) que no
  está en `owned_pids`. Tras la copia de `stop.sh`, ese proceso sigue
  vivo y `kill_denied.log` registra la negativa.
- **PID reciclado:** se inscribe un PID con una hora de inicio falsa y
  `kill` debe negarse.
- **Script de mutación** `mutacion-intento-3.sh` en el expediente. Trabaja
  en un clon temporal (`git clone --local` dentro de `mktemp -d`, con tu
  diff copiado encima) y para cada mutación corre sólo el test afectado
  y espera FAIL:
  - (a) quitar `detener_puerto 8443` de la copia de `stop.sh`;
  - (b) hacer permisiva la función `kill` del fixture;
  - (c) sonda que devuelve error tomado como ausencia.

  Imprime `MUTANTE <n> <muere|sobrevive>`. **No lo ejecutes tú contra el
  worktree;** ejecútalo una vez (sólo usa el clon) y guarda la salida.

## Verificación (salida en `*-intento-3.txt`)

1. Focales: `tests.test_piloto_live_i2`, `tests.test_ciclo_arranque` (ya
   convertido) y `tests.test_engine_probe`, con `-v`.
2. Sólo después, la suite completa dos veces, con
   `lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(8091|8092|8443) '` y
   `ps -ax -o pid,command | grep -E 'llama-server|gateway_(http|tls)'`
   antes, entre y después de las corridas.
3. Los 3 gates del `AGENTS.md`, `git diff --check` y
   `git status --porcelain`.

## Informe y cierre

Escribe `informe-intento-3.md`:

- la disposición de los 6 hallazgos de la ronda 2 (`fixed | justified`
  con evidencia);
- cambios por archivo;
- P1–P3 con `pass | fail | inconclusive`;
- la salida de los mutantes;
- riesgos.

No hagas commit: el capitán lo hace tras auditar. **Regla del
Operador:** toda decisión abierta va con tu recomendación (las opciones
con la recomendada primero, por qué con evidencia y qué cuesta la otra).

Al terminar, responde una sola línea: la palabra FIN, un espacio, la
palabra fix-tests-hermeticos-3, un espacio y el número de hallazgos
cerrados. Si te bloqueas: la palabra BLOQ, un espacio, la palabra
fix-tests-hermeticos-3 y el motivo.
