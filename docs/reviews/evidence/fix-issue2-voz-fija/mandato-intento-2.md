# Mandato del ejecutor — fix-issue2-voz-fija, intento 2

Eres el EJECUTOR (opencode, GLM). No uses `codex`, `herdr` ni `hc`.
Trabajas SÓLO en este worktree
(`/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-issue2-voz-fija`,
rama `agent/fix-issue2-voz-fija`, base `main` `7fd40fc`).
**Tarea material**: aplican los disparadores de `04` §5.3.

## 1. Contexto de la ronda 1 (cerrada; consérvalo, no reviertas nada)

La ronda 1 (codex) ya aplicó la voz fija en el MCP stdio v2 y está en el
árbol SIN commit: `src/mcp_server_v2.py` (esquema y allowlist sin
`voice`/`speed`, rechazo antes del gateway, respuesta sin atribución,
WAV de salida validado), `docs/contracts/mcp-tools-v2.md` (sección «Voz
fija y migración», procedencia issue #2, decisión del Operador
2026-11-07) y `tests/test_mcp_server_v2.py`. El capitán re-verificó: 72
pruebas OK en los tres módulos MCP, dos pasadas, gates en verde, sin
listeners en 8091/8092/8443.

El informe de la ronda 1 es
`docs/reviews/evidence/fix-issue2-voz-fija/informe.md` (STATE PARCIAL,
decisión escalate): dejó tres hallazgos abiertos que ESTA ronda cierra,
con alcance ampliado por el capitán por procedencia de los criterios del
issue #2 («la respuesta nunca atribuye una voz que no se aplicó»;
«contrato, SPEC, `tools/list` y pruebas concuerdan»).

## 2. Hallazgos a cerrar (datos; el capitán confirmó las líneas contra
el árbol de trabajo)

**[HIGH-DOC] `docs/specs/SPEC-i1-vm-mcp-v2.md` desalineada.** Las líneas
43–45 declaran `voice` y `speed` como argumentos y la línea 60 declara
`voice:string` en la salida de `synthesize_speech`. Enmienda acotada:
retíralos, declara voz fija (rechazo de campos no declarados antes del
gateway, respuesta sin atribución, `format:"wav"` describe el formato
aplicado) y cita la procedencia (issue #2, decisión del Operador
2026-11-07). No reescribas otras secciones históricas; sólo la alineación
directa de este tool.

**[HIGH-REMOTO] `src/mcp_remote.py` acepta y refleja `voice`.** El
catálogo declara `voice` y `speed` (líneas ~123–130) y el handler
`_tool_synthesize_speech` (~577) los lee, valida y devuelve el `voice`
solicitado sin aplicarlo. Alinea con la decisión: esquema del catálogo
sin `voice`/`speed`, rechazo con error estructurado antes de llamar al
gateway (patrón de campos no declarados del propio módulo remoto), y
respuesta sin atribución de voz ni velocidad. Añade las regresiones en
`tests/test_mcp_remote.py` (rechazo de ambos, sin atribución, catálogo
cerrado, conservación del caso válido).

**[PERFIL-W] Investigación, no arreglo.** El SDK de referencia
`examples/cliente_perfil_w.py::synthesize_speech` (~233) envía
`modalities:["audio"]` + `audio.voice` contra `/v1/chat/completions`,
pero la voz real del servicio va por `POST /v1/audio/speech` y el gateway
v2 rechaza campos no declarados en el dialecto: el SDK parece no poder
sintetizar contra el servicio real hoy (el test `test_06` de
`tests/test_perfiles_i4.py` pasa porque simula `urlopen`). NO lo cambies:
investiga la ruta real (contrato `docs/contracts/perfiles-servicio-v2.md`
§W y `gateway_core.py`) y documéntalo en el informe como decisión para el
Operador, con tu recomendación (opciones, la recomendada primero, por qué
y qué cuesta la otra). Si tu investigación refuta el defecto, documéntalo
igualmente con evidencia.

## 3. Alcance

Permitido:

- `docs/specs/SPEC-i1-vm-mcp-v2.md` (enmienda acotada del punto 2);
- `src/mcp_remote.py`;
- `tests/test_mcp_remote.py` (tests nuevos aquí);
- `tests/test_perfiles_i4.py` sólo si tu investigación exige adaptar un
  test existente (documéntalo);
- este expediente (`docs/reviews/evidence/fix-issue2-voz-fija/`, archivos
  nuevos con sufijo `-intento-2`).

Fuera de alcance: todo lo demás. En particular NO toques
`src/mcp_server_v2.py` ni `docs/contracts/mcp-tools-v2.md` (cerrados en
ronda 1; si detectas necesidad, BLOQ con tu recomendación),
`examples/cliente_perfil_w.py` (sólo informe), `src/gateway_core.py`,
`src/gateway_http.py`, `run/`, `scripts/`, `skevi-gate.json`, `AGENTS.md`,
`.skevi/` y otras SPEC/ADR (si el desajuste es real, decisión en el
informe, no edición).

## 4. Prohibido

- arrancar el motor, `run/serve.sh`, `run/stop.sh`, gateways reales o
  servicios;
- `kill`, `pkill` o barridos sobre procesos reales;
- red externa (sin `gh`, sin `curl` externo);
- commit, push, stash o ramas;
- editar la configuración de los gates.

Usa `python3.12` para todos los tests y gates (runtime del proyecto;
`python3` del sistema es 3.9 y no sirve). Los tests usan backends falsos
en puertos efímeros de localhost; jamás 8091/8092/8443 reales. **No
ejecutes la suite completa**: este worktree conserva
`tests/test_piloto_live_i2.py`, que ejecuta `run/stop.sh` y `run/serve.sh`
reales y está prohibido. Ejecuta los módulos concretos de §3 y lista
antes con `grep -rl mcp_remote tests/` cuáles otros tocan el módulo.

## 5. Método (`04` §3 y `06` §2)

1. **RED primero**: un test por propiedad nueva que falle hoy — rechazo
   de `voice` y de `speed` en el remoto antes del gateway, respuesta
   remota sin atribución, catálogo remoto cerrado (`tools/list` sin esos
   campos), y verificación documental SPEC↔contrato↔catálogo. Guarda la
   salida en `red-intento-2.txt`.
2. **GREEN**: corrige. Guarda `green-intento-2.txt` con los módulos de §4
   dos veces, y `lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(8091|8092|8443) '`
   antes y después.
3. Los 3 gates del `AGENTS.md`, `git diff --check` y
   `git status --porcelain`.
4. Ronda adversarial propia sobre el diff completo (ronda 1 + 2) con el
   catálogo `.skevi/review-defect-catalog.md`. Después habrá un revisor
   fresco de otra familia (agy, Gemini), ordenado por el Operador.

## 6. Informe y cierre

Escribe `informe-intento-2.md` en este expediente, replicando el formato
de la capa técnica del `informe.md` de la ronda 1 (fence `text` con
`id/date/time_utc/head_sha/model/STATE/GATE/EVIDENCE/PENDING` y
`report_sha256` canónico del bloque, excluyendo la línea del propio hash;
el gate lo verifica). Contenido:

- la disposición de cada hallazgo (`fixed | justified | documented`,
  con evidencia);
- los cambios por archivo;
- las propiedades con `pass | fail | inconclusive`;
- la investigación PERFIL-W con su recomendación;
- los riesgos y las decisiones para el Operador (cada una con tu
  recomendación). No hagas commit.

Al terminar, responde una sola línea: la palabra FIN, un espacio, la
palabra fix-issue2, un espacio y el número de hallazgos cerrados. Si te
bloqueas: la palabra BLOQ, un espacio, la palabra fix-issue2 y el motivo.
