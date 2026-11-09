# Mandato del ejecutor — fix-issue2-voz-fija, intento 1

Eres el EJECUTOR (codex). Te orquesta un capitán; no uses `herdr` ni `hc`.
Trabajas SÓLO en este worktree
(`/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-issue2-voz-fija`,
rama `agent/fix-issue2-voz-fija`, base `main` `7fd40fc`).
**Tarea material**: aplican los disparadores de `04` §5.3.

## 1. Contexto y decisión vigente

GitHub issue #2 «Alinear voice/speed de synthesize_speech con la voz TTS
realmente aplicada». Decisión del Operador (2026-11-07, comentario en el
issue, cita literal):

> **Superficie elegida: voz fija en el contrato v1** (opción 1 de esta
> issue).
>
> - `synthesize_speech` del MCP rechaza `voice` y `speed` antes de llegar
>   al motor, igual que el gateway (`SPEC-i1-vs-sintesis-voz.md:19-21`,
>   ADR-007), y devuelve sólo los parámetros efectivamente aplicados.
> - La selección real de voz queda fuera de v1. Si se necesita, será un
>   cambio de contrato v2 con migración declarada; no está medido que
>   `llama-tts` con el GGUF congelado permita elegir voz.
> - Motivo: el gateway ya es de voz fija; el desajuste está sólo en el
>   MCP. El consumidor previsto (glosomata) elige voz cambiando de motor,
>   no dentro de LFM3.

Criterios de aceptación del issue (siguen vigentes):

- Una prueba de proceso solicita voz o velocidad distinta de la
  predeterminada y demuestra que se rechaza antes del motor.
- La respuesta nunca atribuye una voz o velocidad que no se aplicó.
- `docs/contracts/mcp-tools-v2.md`, SPEC, `tools/list` y pruebas
  concuerdan.
- Se conservan texto fuera de argv, rechazo de campos desconocidos,
  cerrojo TTS 503, WAV validado y limpieza.
- Se declara compatibilidad o migración para consumidores MCP v2.

## 2. Lee completos, en este orden

- `AGENTS.md` y lo que manda leer, incluido
  `docs/ai-agent-guide/06-componentes-con-llm.md`;
- `docs/ai-agent-guide/04-ejecucion-y-verificacion.md`;
- `docs/contracts/mcp-tools-v2.md` (sección de `synthesize_speech`);
- `docs/specs/SPEC-i1-vs-sintesis-voz.md`;
- `src/mcp_server_v2.py` (`handle_synthesize_speech`, `tools/list` y
  esquemas de entrada);
- `src/mcp_remote.py` (sólo las partes del catálogo que describen
  `synthesize_speech`);
- `tests/test_mcp_server_v2.py`.

Hallazgo a cerrar (dato; el capitán lo confirmó contra el código en
`main` `7fd40fc`):

**[DEFECTO-1]** `handle_synthesize_speech` valida `voice` y `speed` pero
no los aplica ni los reenvía; la respuesta MCP devuelve el `voice`
solicitado aunque no se haya aplicado (atribución falsa). Con la decisión
de voz fija, ambos parámetros deben rechazarse en la frontera MCP (error
estructurado, jamás éxito) y la respuesta debe devolver sólo los
parámetros efectivamente aplicados.

## 3. Alcance

Permitido:

- `src/mcp_server_v2.py`;
- `src/mcp_remote.py`, sólo si el catálogo debe reflejar la decisión
  (texto del tool y esquema);
- `tests/test_mcp_server_v2.py` (los tests nuevos van aquí);
- `docs/contracts/mcp-tools-v2.md`: alinea la sección de
  `synthesize_speech` con la decisión, declara la procedencia de la regla
  (issue #2, decisión del Operador 2026-11-07) y la migración para
  consumidores que hoy envían esos campos;
- este expediente (`docs/reviews/evidence/fix-issue2-voz-fija/`).

`tests/test_mcp_remote.py` y `tests/test_perfiles_i4.py` sólo si un test
existente necesita adaptarse al comportamiento corregido.

Fuera de alcance: todo lo demás. En particular:

- `src/gateway_core.py`, `src/gateway_http.py`, `src/adapter_v2.py`:
  úsalos, no los cambies (si hiciera falta cambiarlos, BLOQ con tu
  recomendación);
- `docs/specs/SPEC-i1-vs-sintesis-voz.md` y ADR: léelos para verificar
  consistencia; si detectas desajuste real, anótalo como decisión en el
  informe, no lo edites;
- `run/`, `scripts/`, `skevi-gate.json`, `AGENTS.md`, `.skevi/`.

## 4. Prohibido

- arrancar el motor, `run/serve.sh`, `run/stop.sh`, gateways reales o
  servicios;
- `kill`, `pkill` o barridos sobre procesos reales;
- red (sin `gh`, sin `curl` externo);
- commit, push, stash o ramas;
- editar la configuración de los gates.

Usa `python3.12` para todos los tests y gates (runtime del proyecto;
`python3` del sistema es 3.9 y no sirve). Los tests usan un backend falso
en un puerto efímero; jamás 8091/8092/8443 reales. **No ejecutes la suite
completa**: este worktree conserva `tests/test_piloto_live_i2.py`, que
ejecuta `run/stop.sh` y `run/serve.sh` reales y está prohibido. Ejecuta
los módulos concretos (§3) y lista antes con
`grep -rl mcp_server_v2 tests/` cuáles otros tocan el módulo.

## 5. Método (`04` §3 y `06` §2)

1. **RED primero**: un test por propiedad que falle hoy — rechazo de
   `voice`, rechazo de `speed`, rechazo antes del motor (ninguna llamada
   al backend cuando vienen), respuesta sin atribución de voz no
   aplicada, `tools/list` alineado, conservación del rechazo de campos
   desconocidos, cerrojo TTS 503 y validación WAV. Guarda la salida en
   `red.txt`.
2. **GREEN**: corrige. Guarda `green.txt` con los módulos de §4 dos
   veces, y `lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(8091|8092|8443) '`
   antes y después.
3. Los 3 gates del `AGENTS.md`, `git diff --check` y
   `git status --porcelain`.
4. Ronda adversarial propia sobre tu diff con el catálogo
   `.skevi/review-defect-catalog.md`. Después habrá un revisor fresco de
   otra familia (agy, Gemini), ordenado por el Operador.

## 6. Informe y cierre

Escribe `informe.md` en este expediente con:

- la disposición de cada criterio de aceptación (`fixed | justified`,
  con evidencia);
- los cambios por archivo;
- las propiedades con `pass | fail | inconclusive`;
- la declaración de compatibilidad/migración para consumidores MCP v2
  (qué rompe, qué mensaje reciben, qué deben cambiar);
- los riesgos;
- las decisiones para el Operador (cada una con tu recomendación:
  opciones con la recomendada primero, por qué con evidencia y qué cuesta
  la otra). No hagas commit.

Al terminar, responde una sola línea: la palabra FIN, un espacio, la
palabra fix-issue2, un espacio y el número de criterios cerrados. Si te
bloqueas: la palabra BLOQ, un espacio, la palabra fix-issue2 y el motivo.
