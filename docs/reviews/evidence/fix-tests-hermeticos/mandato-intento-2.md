# Mandato del ejecutor — fix-tests-hermeticos, intento 2

Eres el EJECUTOR, en una sesión nueva. Te orquesta un capitán en Herdr;
tú no uses `herdr` ni `hc`. El worktree, la rama y la base son los del
intento 1. Rigen ÍNTEGROS el alcance (§4) y las prohibiciones (§5) de
`docs/reviews/evidence/fix-tests-hermeticos/mandato.md`; léelo completo
primero. Después lee el informe del intento 1 (`informe.md`, dato) y la
revisión adversarial fresca (dato, verificada por el capitán):
`/private/tmp/claude-502/-Users-krisnova-www-AGTexperts-internos-devHerdrExpert/9d8d2486-579f-4940-bdac-6690603ac36f/scratchpad/lfm3/ola1/fix-tests-rev/informe.md`.

## Restricciones añadidas (prevalecen)

- Nada de `kill`, `kill -9`, `pkill`, `lsof … | kill` ni `stop.sh`
  (real o copiado) contra procesos o puertos reales, en ningún comando
  tuyo. Un proceso sólo se termina mediante el handle que tu fixture creó
  (`Popen`), nunca mediante un PID leído de un archivo.
- No arranques el motor real. Si aparece un proceso en 8091/8092/8443,
  no lo toques: anótalo en la evidencia.

## Objetivo: cerrar los hallazgos de la revisión

1. **[BLOCKER] Aislar la parada de `test_11`.** `run/stop.sh` resuelve
   `lsof` y `ps` por `PATH` (líneas 16, 50 y 57) y envía `kill` a lo que
   devuelve `lsof`. Diseño recomendado por el capitán, que elimina la
   carrera de raíz:
   - pon en `bin_dir` un `lsof` sustituto (y, si hace falta, un `ps`)
     que sólo informe de PIDs creados por el fixture, leídos de un
     estado propio del fixture;
   - los procesos sustitutos de 8091, 8092 y 8443 no necesitan enlazar
     puertos reales: basta con que el `lsof` sustituto los reporte
     mientras vivan;
   - así ningún PID ajeno puede llegar a `kill` y desaparece la guarda
     de puertos ocupados.

   Añade un control positivo: un proceso «ajeno» lanzado por el propio
   test, con comando `llama-server --port 8091`, que el `lsof` sustituto
   no reporta, tiene que sobrevivir a la copia de `stop.sh`.
   Si eliges otro diseño, justifícalo con la regla de recomendación.
2. **[HIGH] Limpieza.** Toda adquisición (tmp, procesos) va dentro de
   `try/finally` o de `addCleanup`. Los procesos se terminan por su
   handle `Popen`; no hay `os.kill` sobre PIDs leídos de archivo. Cubre:
   `node` ausente, error de preparación y timeout.
3. **[HIGH] `test_11` cubre 8092 y 8443.** Usa procesos sustitutos de
   gateway y TLS reportados por el `lsof` sustituto, con comandos que
   pasen el patrón de `stop.sh` (`gateway_http.py` y `gateway_tls.py`).
   Verifica que mueren, igual que el motor, y que se limpian los PID y
   cerrojos.
4. **[HIGH] Sondas de motor.** Distingue la ausencia verificada
   (`ConnectionRefusedError`, nada escucha) de un error de sonda
   (respuesta malformada, timeout o 5xx): sólo la ausencia verificada
   salta; un error de sonda hace FALLAR la guarda con su motivo. Añade
   controles deterministas de las dos ramas con un servidor HTTP falso en
   un puerto efímero o con `mock`.
5. **[MED] Evidencia P1 no vacua.** Repite `probe_p1_red.py` sobre el
   `test_11` nuevo con el cuerpo EJECUTADO: debe registrar la `serve.sh`
   y la `stop.sh` temporales y ninguna ruta `run/` del checkout.
6. **[MED] Identificadores en inglés** sólo para lo que añadiste en el
   intento 1 y en este (`_puerto_libre`, `_pid_vivo`, `nodo`, `arranque`,
   `parada`, `residuo`, `_motor_vivo`…). Docstrings y comentarios siguen
   en español.

## Verificación (guarda la salida en `*-intento-2.txt`)

- `lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(8091|8092|8443) '` y
  `ps -ax -o pid,command | grep -E 'llama-server|gateway_(http|tls)'`
  antes y después de cada corrida;
- la suite completa (`python3 -m unittest discover -s tests -t .`) dos
  veces, y `tests.test_piloto_live_i2 -v`;
- los 3 gates del `AGENTS.md`, `git diff --check` y
  `git status --porcelain`.

## Informe y cierre

Escribe `informe-intento-2.md`: la disposición de cada hallazgo
(`fixed | justified` y evidencia), cambios por archivo, las propiedades
P1–P3 con `pass | fail | inconclusive` y riesgos. **Regla del Operador:**
toda decisión que dejes abierta va con tu recomendación: las opciones con
la recomendada primero, por qué (con evidencia) y qué cuesta la otra. Con
el informe completo, responde una sola línea: la palabra FIN, un espacio,
la palabra fix-tests-hermeticos-2, un espacio y el número de hallazgos
cerrados. Si te bloqueas: la palabra BLOQ, un espacio, la palabra
fix-tests-hermeticos-2 y el motivo.
