# Mandato del ejecutor — fix-issue2-voz-fija, intento 3

Eres el EJECUTOR (opencode, GLM). No uses `codex`, `herdr` ni `hc`.
Trabajas SÓLO en este worktree
(`/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-issue2-voz-fija`,
rama `agent/fix-issue2-voz-fija`, base `main` `7fd40fc` con el trabajo SIN
commit de las rondas 1 y 2: consérvalo, no reviertas nada).
**Tarea material**: aplican los disparadores de `04` §5.3.

## 1. Contexto

La revisión fresca de otra familia (agy, Gemini) sobre las rondas 1 y 2
dio **proceed** con 1 MED y 3 LOW (su informe está en la sesión del
capitán; los hallazgos se citan abajo con sus anclas, verificadas por el
capitán contra este árbol). El MED condiciona el cierre del issue #2.
Esta ronda cierra el MED y los LOW accionables. **El código producto está
congelado: ninguna edición bajo `src/` en esta ronda.**

## 2. Hallazgos a cerrar

**[MED-1] `docs/specs/SPEC-i3-mcp-remote.md` rige el módulo remoto y
sigue prometiendo la voz retirada.** Líneas 195–196 declaran `voice` y
`speed` opcionales y la 202 muestra `"voice"` en la salida. Enmienda
acotada de la sección correspondiente (§4.6): sin `voice` ni `speed`,
rechazo de campos no declarados en la frontera antes del gateway,
respuesta sin atribución, con procedencia (issue #2, decisión del
Operador 2026-11-07) y referencia al contrato
`docs/contracts/mcp-tools-v2.md`, sección «Voz fija y migración».

**[LOW-3] `docs/specs/SPEC-i4-c-clientes-y-perfiles.md:101`** especifica
`synthesize_speech(text, voice=None)` para el cliente SDK: choca con la
voz fija. Alinea con el cambio mínimo (firma sin `voice` o nota de voz
fija), con la misma procedencia; documenta la elección en el informe.

**[LOW-2] El test de concordancia prueba menos de lo que dice.**
`tests/test_mcp_remote.py::test_concordancia_documental_spec_contrato_catalogo`
(~641) sólo mira la SPEC-i1-vm y el catálogo remoto. Fortalécelo: verifica
además que el contrato `docs/contracts/mcp-tools-v2.md` no declara
`voice`/`speed` en `synthesize_speech`, que la SPEC-i3 enmendada tampoco,
y que los esquemas de `synthesize_speech` de ambos catálogos
(`mcp_server_v2.TOOLS` y `TOOLS_REMOTE`) coinciden.

**[LOW-1] Corrección de registro, no de informe.** El
`informe-intento-2.md` (~154) afirma que el rechazo remoto ocurre «sin
tocar el dispatcher», pero `mcp_remote.py:379-383` ejecuta
`dispatcher.acquire_slot` antes de ejecutar el tool: una petición con
`voice` consume un puesto de cola y puede recibir 429/503 antes del error
de contrato (comportamiento preexistente para cualquier argumento
inválido). NO edites `informe-intento-2.md` (evidencia inmutable): deja
la corrección registrada en `informe-intento-3.md`.

## 3. Alcance

Permitido:

- `docs/specs/SPEC-i3-mcp-remote.md` (enmienda acotada);
- `docs/specs/SPEC-i4-c-clientes-y-perfiles.md` (enmienda acotada);
- `tests/test_mcp_remote.py` (sólo el test de concordancia);
- este expediente (`informe-intento-3.md` y evidencia con sufijo
  `-intento-3`).

Fuera de alcance: todo lo demás — en particular `src/` (congelado en esta
ronda), los demás SPEC/ADR, `run/`, `scripts/`, `skevi-gate.json`,
`AGENTS.md`, `.skevi/`.

## 4. Prohibido

- arrancar el motor, `run/serve.sh`, `run/stop.sh`, gateways reales o
  servicios;
- `kill`, `pkill`, red externa (sin `gh`, sin `curl` externo);
- commit, push, stash o ramas;
- editar la configuración de los gates.

Usa `python3.12` para tests y gates. **No ejecutes la suite completa**
(`tests/test_piloto_live_i2.py` ejecuta scripts reales y está prohibido).
Ejecuta `tests.test_mcp_remote` y los módulos MCP ya usados en rondas
previas.

## 5. Método (`04` §3 y `06` §2)

1. **RED primero**: el test de concordancia fortalecido debe FALLAR hoy
   contra la SPEC-i3 sin enmendar (y pasar después). Guarda la salida en
   `red-intento-3.txt`.
2. **GREEN**: enmienda las dos SPEC. Guarda `green-intento-3.txt` con
   `tests.test_mcp_remote` (dos veces) y `tests.test_mcp_server_v2`, y
   `lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(8091|8092|8443) '` antes y
   después.
3. Los 3 gates del `AGENTS.md`, `git diff --check` y
   `git status --porcelain`.
4. Ronda adversarial propia sobre el diff acumulado con el catálogo
   `.skevi/review-defect-catalog.md`.

## 6. Informe y cierre

Escribe `informe-intento-3.md` replicando la capa técnica canónica de los
informes previos (fence `text` con
`id/date/time_utc/head_sha/model/STATE/GATE/EVIDENCE/PENDING` y
`report_sha256` canónico del bloque, excluyendo la línea del hash), con
la disposición de cada hallazgo (MED-1, LOW-1, LOW-2, LOW-3), cambios por
archivo, propiedades, riesgos y decisiones para el Operador. No hagas
commit.

Al terminar, responde una sola línea: la palabra FIN, un espacio, la
palabra fix-issue2, un espacio y el número de hallazgos cerrados. Si te
bloqueas: la palabra BLOQ, un espacio, la palabra fix-issue2 y el motivo.
