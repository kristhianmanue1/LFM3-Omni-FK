# Mandato del ejecutor — fix-tests-hermeticos, intento 1

Eres el EJECUTOR. Te orquesta un capitán en Herdr; tú no uses `herdr` ni
`hc`. Trabajas SÓLO en este worktree
(`/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-fix-tests-hermeticos`,
rama `agent/fix-tests-hermeticos`, base `main` `60c6568`).

## 1. Lee completos, en este orden

`AGENTS.md` y lo que manda leer (`.skevi/usage-guide.md`,
`docs/ai-agent-guide/00-INDICE.md`, `docs/estandar-diseno-software-github.md`,
`docs/ai-agent-guide/04-ejecucion-y-verificacion.md` §1–§4); después
`tests/test_piloto_live_i2.py`, `tests/test_mcp_server.py`,
`tests/test_ciclo_arranque.py` (patrón de copias en tmp con
`llama-server` stub, líneas ~90–130), `run/serve.sh` y `run/stop.sh`
(sólo lectura), y `grep -rn "run/\|serve.sh\|stop.sh\|8091\|8092\|8443" tests/`.

## 2. Problema observado (dato del capitán, verifícalo)

- `tests/test_piloto_live_i2.py:458-470` (`test_11_rollback_parada_limpia`)
  ejecuta el `run/stop.sh` REAL del checkout (que por defecto usa `--all`:
  para 8443/8092/8091) y en `finally` el `run/serve.sh` REAL, que arranca
  un `llama-server` real en 8091 y lo deja huérfano.
- Los tests de `ToolsConMotor` (`tests/test_mcp_server.py:302+`) y otros
  que requieren motor vivo FALLAN si no hay motor («Connection refused»)
  en vez de saltarse. El resultado de la suite depende del orden y del
  estado de la máquina: una corrida dio `failures=5` y la siguiente `OK`.

## 3. Objetivo (propiedades verificables)

- **P1** — Ningún test ejecuta scripts de `run/` del checkout ni toca
  procesos o puertos reales del servicio. Para probar parada y arranque,
  se usan copias en un directorio temporal con `llama-server` stub, como
  `test_ciclo_arranque.py`. Debe seguir probándose lo que `test_11`
  pretendía: que `stop.sh` para listeners y limpia PIDs y cerrojos.
- **P2** — Los tests que requieren motor vivo en 127.0.0.1:8091 se saltan
  con motivo explícito (`skipUnless` o equivalente, comprobado una vez)
  cuando no hay motor, y se ejecutan cuando sí lo hay. No los borres ni
  los debilites.
- **P3** — Dos corridas seguidas de la suite completa dan el mismo
  resultado, y no queda ningún listener nuevo en 8091/8092/8443 ni ningún
  proceso `llama-server`, `gateway_http.py` o `gateway_tls.py` nuevo
  (`lsof -nP -iTCP -sTCP:LISTEN` y `ps` antes y después).

## 4. Alcance

Permitido: sólo `tests/` y este expediente
(`docs/reviews/evidence/fix-tests-hermeticos/`).
Fuera de alcance: todo lo demás, en particular `src/`, `run/`,
`scripts/`, `skevi-gate.json`, `AGENTS.md`, `.skevi/`, `docs/` fuera del
expediente.

## 5. Prohibido

- Ejecutar `run/serve.sh`, `run/stop.sh`, `run/serve_pilot.sh` o
  `llama-server` reales. Ejecutar `test_11` o la suite completa ANTES de
  que P1 esté corregido (lanzaría el motor real).
- Commit, push, stash, crear o borrar ramas, borrar archivos no pedidos.
- Editar la configuración de los gates para que pasen.
- Arrancar agentes o servicios; red.
- Si el objetivo es imposible dentro del alcance, NO lo amplíes:
  detente y ciérralo con BLOQ (punto 7).

## 6. Método y verificación (guarda la salida real en el expediente)

1. RED, sin ejecutar scripts reales: demuestra P2 corriendo sólo
   `python3 -m unittest tests.test_mcp_server` sin motor (debe fallar
   hoy). Para P1, demuestra la violación sin ejecutarla (p. ej., un test o
   una comprobación que detecte la ruta real de `run/` en `test_11`, o
   `subprocess` parcheado). Guarda la salida en `red.txt`.
2. GREEN: corrige y guarda la salida en `green.txt`:
   - `lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(8091|8092|8443) '` y
     `ps aux | grep -E 'llama-server|gateway_(http|tls)' | grep -v grep`,
     antes y después;
   - `python3 -m unittest discover -s tests -t .` dos veces seguidas;
   - `python3 scripts/check_sizes.py`, `check_plans.py` y
     `check_reports.py`;
   - `git diff --check` y `git status --porcelain`.
3. Declara como `inconclusive` la rama «con motor vivo» de P2 si no hay
   motor (no lo arranques).

## 7. Informe y cierre

Escribe `docs/reviews/evidence/fix-tests-hermeticos/informe.md`: cambios
por archivo, causa raíz con evidencia, propiedades P1–P3 con
`pass | fail | inconclusive` y la salida real, y riesgos. Sólo con el
informe completo, responde en pantalla con una sola línea: la palabra FIN,
un espacio, la palabra fix-tests-hermeticos, un espacio y el número de
archivos de `tests/` que modificaste. Si te bloqueas: la palabra BLOQ, un
espacio, la palabra fix-tests-hermeticos y el motivo.
