# fix-issue2-voz-fija — informe del ejecutor, intento 1

## Capa técnica

```text
id: fix-issue2-voz-fija
date: 2026-11-09
time_utc: 22:31:46Z
head_sha: 7fd40fc7328bcb87a44e418de455a67d52022df9
model: codex (autodeclarado)
STATE: PARCIAL
GATE: 4/5 criterios cerrados en MCP stdio; SPEC-i1-vm desalineada,
  integración con sockets inconclusa y revisión fresca pendiente
EVIDENCE: red.txt; green.txt; focal.txt; gates.txt;
  listeners-before.txt; listeners-after.txt; diff de trabajo
PENDING: decisión sobre enmienda de SPEC-i1-vm y alcance de mcp_remote;
  revisión fresca agy; integración en entorno con sockets efímeros
DECISION: escalate
report_sha256: 5c7ad2b6b99c143962de326afcd823dcf97f4b44c58abde750f4c4a11bedfaa9
```

## Resultado y criterios de aceptación

1. **fixed** — prueba de proceso `test_proceso_rechaza_voice_y_speed_antes_backend`:
   `voice="otra"` y `speed=1.5` producen `isError:true` con el campo
   nombrado. La sonda de backend se activa exactamente una vez con la
   petición de control válida, y no con las dos rechazadas (`focal.txt`).
2. **fixed para MCP stdio** — la respuesta exitosa ya no incluye `voice`
   ni `speed`; `test_synthesize_speech_exitoso` lo comprueba. Límite:
   `src/mcp_remote.py` conserva otro handler que todavía atribuye `voice`
   sin aplicarla; no se declara corregida esa superficie.
3. **pendiente** — contrato, `tools/list` stdio y pruebas concuerdan;
   `SPEC-i1-vs-sintesis-voz.md` §1 confirma el rechazo en gateway.
   `SPEC-i1-vm-mcp-v2.md` todavía declara `voice`, `speed` y `voice` de
   salida. Su edición está prohibida en este mandato: el criterio de
   concordancia documental completa no queda cerrado.
4. **justified** — `test_campo_desconocido_rechazado_antes_gateway`,
   `test_synthesize_speech_cerrojo_ocupado_retorna_503_tts_busy`,
   `test_wav_invalido_rechazado` y
   `test_gateway_tts_texto_fuera_argv_y_limpieza` pasan (`focal.txt`).
   El runner falso comprueba archivo `0600`, ausencia de texto en `argv`,
   WAV válido y eliminación del temporal. La integración HTTP real con
   puerto efímero queda inconclusa por el sandbox.
5. **fixed** — sección «Voz fija y migración» del contrato declara ruptura,
   mensaje y cambio requerido para consumidores MCP v2.

## Cambios

- `src/mcp_server_v2.py`: retira `voice` y `speed` de esquema y allowlist,
  deja de atribuir voz y valida el WAV recibido antes de responder éxito.
- `tests/test_mcp_server_v2.py`: regresiones de frontera, respuesta,
  catálogo, proceso con sonda controlada y runner TTS sin red.
- `docs/contracts/mcp-tools-v2.md`: contrato de voz fija, procedencia
  (issue #2, decisión del Operador 2026-11-07) y migración.
- Expediente: salidas RED, GREEN, focales, gates y sondeo de listeners.
  No se editó `src/mcp_remote.py`: cambiar sólo su catálogo anunciaría
  una restricción que su handler no cumple; el handler está fuera de alcance.

## Propiedades y verificaciones

| Propiedad | Estado | Evidencia y límite |
|---|---|---|
| Rechazo de `voice` y `speed` antes del backend | pass | Proceso stdio y control positivo, `focal.txt` |
| Sin atribución de voz o velocidad | pass | Respuesta MCP stdio, `focal.txt`; remoto separado |
| `tools/list` cerrado | pass | `test_tools_list_voz_fija` |
| Campos desconocidos | pass | Sonda `_http_gateway.assert_not_called()` |
| Cerrojo 503 | pass | Mock 503; integración HTTP inconclusa |
| WAV de salida | pass | WAV inválido rechazado y válido aceptado |
| Texto fuera de argv, 0600 y limpieza | pass | Runner falso directo |
| Módulos completos dos veces | inconclusive | `green.txt`: 60 pruebas por pasada, 5 errores `PermissionError` en bind efímero, cero fallos de aserción |
| Tres gates, diff y estado | pass | `gates.txt`, ejecutado tras código y reporte |
| Listeners 8091/8092/8443 antes/después | pass | Ambos archivos vacíos; sólo presencia observable, no prueba de ausencia universal |

RED (`red.txt`) observó fallos de voz, velocidad, atribución,
`tools/list` y WAV antes de cambiar producto. También registra errores
de bind del sandbox. GREEN focal: 17 pruebas OK (`focal.txt`). La suite
completa no se ejecutó porque incluye `test_piloto_live_i2.py`, prohibido.

## Compatibilidad y riesgos

Consumidores MCP stdio v2 que envían `voice` o `speed`, aun con valores
anteriores por defecto, reciben `isError:true` con
`arguments inválidos: campos no declarados en el contrato: ['voice']`
o `['speed']`. Deben omitirlos; la selección de voz se realiza por otro
motor. Reintentar sin cambiar argumentos no ayuda. No se afirma que
`llama-tts` con el GGUF congelado admita elegir voz.

El riesgo residual más concreto es la implementación remota separada:
su catálogo y handler aún aceptan `voice`/`speed`, y el handler devuelve
`voice` no aplicada. Una petición remota con `voice="otra"` refutaría
una afirmación global de que todo MCP cumple voz fija. Por eso esta ronda
acota el cierre al servidor stdio. El sandbox impide verificar aquí el
camino HTTP con sockets; no se atribuye ese fallo al producto.

## Ronda adversarial propia

Productor y revisor de esta ronda: mismo ejecutor codex, con historial
completo; se revisó diff y contratos, sin independencia de contexto.
Revisión fresca de agy/Gemini: pendiente, ordenada por el Operador.

| Clase del catálogo | Ataque y resultado |
|---|---|
| Entrada, autorización, contrato | `voice` y `speed` explícitos caen en `_campos_extra` antes de HTTP; el catálogo stdio no los anuncia. El handler remoto contradice la regla global: hallazgo HIGH fuera de alcance. |
| Secretos y recursos | El runner directo confirma texto fuera de argv, 0600 y borrado; la integración con socket falta. |
| Concurrencia y errores | Mock 503 propaga `tts_busy`; la sonda HTTP de cerrojo real no pudo abrir puerto. |
| Trabajo acotado | Límite de entrada 600 y WAV validado contra presupuesto de `gateway_core`. |
| Test que no prueba requisito | Control positivo de proceso activa la sonda de backend una vez con petición válida. |

Hallazgo HIGH documental: `SPEC-i1-vm-mcp-v2.md` sigue prometiendo
parámetros y salida retirados. Impacto: consumidor que la siga enviará
campos rechazados. Corrección requerida: enmienda explícita de esa SPEC;
estado abierto por alcance. Decisión de ronda: **escalate**.

## Decisiones para el Operador

1. **Recomendada: autorizar en una ronda posterior la enmienda de
   `SPEC-i1-vm-mcp-v2.md`** y revisar su trazabilidad. Evidencia: sus
   líneas 44–45 y 60 contradicen contrato y código. Alternativa: conservar
   la SPEC histórica con nota de supersesión; cuesta mantener una fuente
   activa contradictoria y obliga a una referencia correctiva inequívoca.
2. **Recomendada: abrir alcance separado para `mcp_remote.py` handler y
   pruebas remotas** si el issue #2 pretende cubrir toda superficie MCP.
   Evidencia: su `_tool_synthesize_speech` acepta y refleja `voice`.
   Alternativa: declarar explícitamente que issue #2 cubre sólo stdio;
   cuesta mantener la atribución falsa en MCP remoto.
3. **Recomendada: repetir los módulos concretos en un sandbox con bind
   efímero habilitado**, sin puertos reales. Alternativa: aceptar sólo las
   pruebas sin red; cuesta dejar inconclusa la integración HTTP de esta ronda.

No se ejecutaron motor, gateways reales, red externa ni operaciones Git
persistentes. Siguiente acción autorizada aquí: ninguna fuera del alcance;
revisor fresco y decisiones corresponden a la orquestación del Operador.
