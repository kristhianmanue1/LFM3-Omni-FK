# Mandato del revisor — fix-issue2-voz-fija (agy, ronda 1)

Eres el REVISOR fresco de otra familia (agy, Gemini). Contexto fresco:
evalúa sólo lo que ves en el worktree, sin supuestos sobre cómo se llegó
al cambio. **Sólo lectura**: no modifiques ningún archivo, no hagas
commit, no arranques servicios ni el motor, sin red externa.

Worktree:
`/Users/krisnova/www/AGTexperts/externos/LFM3-Omni-wt-issue2-voz-fija`
Rama `agent/fix-issue2-voz-fija`, base `main` `7fd40fc`. Los cambios están
SIN commit: revisa `git diff` y los archivos nuevos sin seguimiento.

## Tarea

Revisión adversarial defect-first del cambio contra el mandato del
ejecutor y los criterios de aceptación del issue #2 (voz fija en el
contrato v1; decisión del Operador 2026-11-07).

## Lee, en este orden

1. `docs/reviews/evidence/fix-issue2-voz-fija/mandato.md` y
   `mandato-intento-2.md`;
2. el diff completo (`git diff` + `git status --short`) y cada archivo
   tocado en su estado final;
3. la evidencia del expediente: `red.txt`, `green.txt`, `focal.txt`,
   `gates.txt` (ronda 1) y `red-intento-2.txt`, `green-intento-2.txt`,
   `gates-intento-2.txt` (ronda 2);
4. `informe.md` (ronda 1) e `informe-intento-2.md` (ronda 2) del
   ejecutor;
5. `docs/contracts/mcp-tools-v2.md` (sección de `synthesize_speech`),
   `docs/specs/SPEC-i1-vm-mcp-v2.md` y
   `docs/specs/SPEC-i1-vs-sintesis-voz.md` para consistencia.

## Verifica contra el código, no contra la prosa

Cada afirmación verificable del informe debe coincidir con la salida real
(grep de los identificadores citados: nombres de función, claves de
esquema, constantes; lectura de las líneas citadas). Puntos mínimos:

- [DEFECTO-1] `voice` y `speed` se rechazan en la frontera MCP con error
  estructurado, ANTES de cualquier llamada al backend — en AMBAS
  superficies: stdio (`mcp_server_v2.py`) y remoto (`mcp_remote.py`);
- la respuesta nunca atribuye una voz o velocidad que no se aplicó
  (ningún eco del `voice` solicitado) en ninguna de las dos superficies;
- `tools/list` de ambos catálogos, la SPEC enmendada y el contrato
  editado concuerdan con el comportamiento;
- conservación: rechazo de campos desconocidos, cerrojo TTS 503,
  validación WAV, texto fuera de argv, limpieza;
- declaración de compatibilidad/migración para consumidores MCP v2
  presente en contrato e informe;
- las verificaciones declaradas (gates, módulos de test) son
  reproducibles con `python3.12` y no tocan `tests/test_piloto_live_i2.py`;
- alcance respetado: ningún archivo fuera de los permitidos por el
  mandato.

Puedes ejecutar comandos de sólo lectura (grep, git diff, lectura de
archivos) y módulos de test existentes si no escriben fuera del worktree;
nunca la suite completa ni `test_piloto_live_i2`.

## Veredicto

Clasifica cada hallazgo: BLOCKER | HIGH | MED | LOW, con evidencia
`archivo:línea`. BLOCKER o HIGH existentes ⇒ `blocked`. Responde al final
del informe el veredicto (`proceed | blocked`), los conteos por
severidad, un párrafo por hallazgo y, en una sola línea separada, el
marcador: la palabra FIN, un espacio, la palabra rev-issue2, un espacio y
el número total de hallazgos nuevos.
