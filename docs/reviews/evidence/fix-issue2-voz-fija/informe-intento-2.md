# fix-issue2-voz-fija — informe del ejecutor, intento 2

## Capa técnica

```text
id = fix-issue2-voz-fija-intento-2
date = 2026-11-09
time_utc = 22:47:49Z
head_sha = 7fd40fc7328bcb87a44e418de455a67d52022df9
model = GLM 5.3 Flash (autodeclarado)
STATE = OK
GATE = 3/3 hallazgos del intento 1 cerrados en su alcance (SPEC-i1-vm alineada, mcp_remote con voz fija y regresiones, PERFIL-W investigado sin arreglo); tres gates OK, drift al día, 114 pruebas OK dos pasadas sin errores de bind; desajustes fuera de alcance registrados como decisión, no editados
PENDING = revisor fresco de otra familia (agy o Gemini), ordenado por el Operador; enmienda futura de SPEC-i3-mcp-remote.md §4.6; rumbo de examples/cliente_perfil_w.py y de cli.py speech, ambos fuera de alcance de este mandato
DECISION = proceed
EVIDENCE
- red-intento-2.txt: 9 fallos exactamente en las propiedades nuevas (3 remotos HTTP test_13/14/15 y 6 de frontera), con las 12 pruebas previas del módulo en verde -> pass
- green-intento-2.txt: tests.test_mcp_remote + tests.test_mcp_server_v2 + tests.test_mcp_server + tests.test_perfiles_i4, 114 pruebas OK dos pasadas consecutivas; único skipped preexistente ToolsConMotor (exige motor vivo 8091, prohibido) -> pass
- listeners-before-intento-2.txt y listeners-after-intento-2.txt: sin escucha en 8091/8092/8443 antes y después de las dos pasadas -> pass
- gates-intento-2.txt: check_sizes, check_plans y check_reports OK; drift de plantillas corpus/v10 y gate/v14 al día; git diff --check limpio; git status acotado a los ficheros permitidos -> pass
- frontera remota sin gateway: RunnerTTSFalso.llamadas == 0 en rechazo de voice y speed; == 1 con WAV válido en el caso de control -> pass
- concordancia SPEC-i1-vm ↔ contrato v2 ↔ catálogo remoto verificada por test (sin voice/speed, voz fija, procedencia 2026-11-07) -> pass
- SPEC-i3-mcp-remote.md §4.6 sigue declarando voice/speed y respuesta con voz: desajuste real fuera de alcance editable -> inconclusive
- cli.py speech acepta --voice/--speed y los ignora sin avisar (payload nunca los incluye): fuera de alcance -> inconclusive
- PERFIL-W: el SDK envía modalities+audio contra /v1/chat/completions y el dialecto v2 los rechaza (CLAVES_TOP); la ruta real es /v1/audio/speech; test_06 sólo simula urlopen -> pass
report_sha256 = b97a62f9f63a4eb12d70f330a76fef55d0b09e732baf6e78c165e11951425519
```

## Disposición de los hallazgos del intento 1

1. **[HIGH-DOC] SPEC-i1-vm-mcp-v2.md desalineada — fixed.** Retirados
   `voice` y `speed` de los argumentos y `voice:string` de la salida de
   `synthesize_speech` (líneas 43–45 y 60 del árbol original). La SPEC
   declara ahora voz fija: rechazo de campos no declarados en la frontera
   MCP antes del gateway, respuesta sin atribución de voz ni velocidad,
   `format:"wav"` como formato aplicado, y cita la procedencia (issue #2,
   decisión del Operador del 2026-11-07) con remisión al contrato
   (`mcp-tools-v2.md`, «Voz fija y migración»). No se reescribió ninguna
   otra sección histórica. Evidencia: diff de la SPEC,
   `test_concordancia_documental_spec_contrato_catalogo` (rojo en
   `red-intento-2.txt`, verde en `green-intento-2.txt`).
2. **[HIGH-REMOTO] mcp_remote aceptaba y reflejaba `voice` — fixed.**
   Catálogo `TOOLS_REMOTE` sin `voice`/`speed` y con los campos que el
   contrato declara (`input`, `response_format:"wav"`, descripción de voz
   fija alineada con la superficie stdio). El handler
   `_tool_synthesize_speech` rechaza en la frontera, con error
   estructurado `invalid_payload` («arguments inválidos: campos no
   declarados en el contrato: [...]») y nombrando cada campo, antes de
   llamar al gateway; la respuesta exitosa ya no atribuye voz ni
   velocidad (`{audio_base64, format, chars, duration_est_s}`). Evidencia:
   `test_13`/`test_14`/`test_15` por HTTP completo y 6 pruebas de
   frontera sin sockets; RED y GREEN en el expediente.
3. **[PERFIL-W] Investigación, no arreglo — documented.** El defecto
   hipoetizado es real (ver sección «Investigación PERFIL-W»). No se
   editó `examples/cliente_perfil_w.py` ni
   `tests/test_perfiles_i4.py`; la recomendación queda como decisión para
   el Operador.

## Cambios por archivo (esta ronda)

- `docs/specs/SPEC-i1-vm-mcp-v2.md`: enmienda acotada del tool
  `synthesize_speech` (argumentos, salida y nota de voz fija con
  procedencia).
- `src/mcp_remote.py`: catálogo sin `voice`/`speed` (con
  `response_format` enum wav, como el stdio y el contrato), nota de voz
  fija en el docstring del módulo, y handler con rechazo de campos no
  declarados antes del gateway y respuesta sin atribución.
- `tests/test_mcp_remote.py`: tres regresiones HTTP (`test_13`,
  `test_14`, `test_15`), clase `VozFijaRemotoFrontera` de frontera sin
  sockets (rechazo de ambos campos con contador de runner, respuesta sin
  atribución, caso válido con conjunto exacto de claves, catálogo
  cerrado vía `tools/list`, verificación documental) y utilidades
  (`RunnerTTSFalso`, `HttpHandlerFalso`, WAV sintético).
- Expediente: `red-intento-2.txt`, `green-intento-2.txt`,
  `gates-intento-2.txt`, `listeners-before-intento-2.txt`,
  `listeners-after-intento-2.txt` y este informe.
- Sin cambios en `src/mcp_server_v2.py`, `docs/contracts/mcp-tools-v2.md`
  ni ninguna otra ruta del alcance prohibido.

## Propiedades y verificaciones

| Propiedad | Estado | Evidencia y límite |
|---|---|---|
| Rechazo de `voice` y `speed` en la frontera remota | pass | `test_13`/`test_14` (HTTP) y 2 pruebas de frontera; RED los mostró fallando antes del arreglo |
| Gateway no llamado en el rechazo | pass | `RunnerTTSFalso.llamadas == 0`; el rechazo precede a `_sintetizar_wav` |
| Respuesta remota sin atribución de voz/velocidad | pass | `test_respuesta_exitosa_sin_atribucion` y conjunto exacto de claves |
| Caso válido conservado | pass | `test_08` previo en verde dos pasadas; unidad con claves exactas y WAV íntegro |
| Catálogo remoto cerrado (`tools/list` sin voice/speed) | pass | `test_15` (HTTP) y unidad con `{input, response_format}` exacto y `additionalProperties:false` |
| Concordancia SPEC-i1-vm ↔ contrato v2 ↔ catálogo | pass | `test_concordancia_documental_spec_contrato_catalogo` |
| Concordancia SPEC-i3 §4.6 ↔ remoto | fail → documented | Fuera de alcance editable; decisión 1 para el Operador |
| Síntesis del SDK perfil W contra servicio real | fail → documented | Evidencia estática del dialecto; decisión 2 para el Operador |
| Módulos del §3/§4 dos pasadas | pass | 114 OK ×2; el bind efímero funcionó hoy (a diferencia de la ronda 1) |
| Tres gates, drift, `git diff --check`, `git status` | pass | `gates-intento-2.txt` |
| Listeners 8091/8092/8443 antes/después | pass | Ambos ficheros vacíos |
| Verificación contra motor real | inconclusive | Prohibido arrancar motor; síntesis probada con runners falsos y `validar_wav` fail-closed en `_sintetizar_wav` |

## Investigación PERFIL-W (sin arreglo, según mandato)

Pregunta: ¿puede `examples/cliente_perfil_w.py::synthesize_speech`
sintetizar voz contra el servicio real?

Evidencia estática (ningún servicio arrancado):

- El SDK (líneas 233–249) hace `POST /v1/chat/completions` con payload
  estilo OpenAI: `modalities:["audio"]` y `audio:{voice, format}`.
- El dialecto v2 de `/v1/chat/completions` es una allowlist cerrada:
  `CLAVES_TOP` (`gateway_core.py:44`) no contiene `modalities` ni
  `audio`, y `validar_payload` (`gateway_core.py:617`) responde
  `400 unknown_field` con «2 campo(s) no admitidos por el dialecto v2».
  La petición del SDK es rechazada hoy por el gateway real.
- La ruta real de TTS es `POST /v1/audio/speech`
  (`gateway_http.py:578–594`): dialecto `CLAVES_TTS`
  `{input, language, response_format, model}` vía `validar_payload_tts`,
  scope `speech:synthesize`, respuesta binaria `audio/wav` con cabecera
  `X-V2-Mode: tts-wav` y 503 sin cola. El SDK no tiene método para esa
  ruta y además espera una respuesta `choices[0].message.audio.data`
  que la ruta real no produce.
- `tests/test_perfiles_i4.py::test_06` pasa porque simula `urlopen`:
  prueba la forma del payload del cliente, no el servicio. No lo toqué:
  adaptarlo sin contrato nuevo codificaría comportamiento no decidido.
- El contrato `perfiles-servicio-v2.md` §W no declara síntesis de voz
  para W (remite al perfil H y a capabilities); el docstring del cliente
  («Síntesis de voz hablada (TTS WAV 24 kHz)») promete una capacidad no
  contratada. Coincide además con la voz fija: el parámetro `voice` del
  SDK nunca podría aplicarse.

Recomendación (opciones, la recomendada primero):

1. **Recomendada — reorientar el SDK a la ruta real en una ronda futura
   con alcance sobre `examples/` y su test.** `synthesize_speech` pasa a
   `POST /v1/audio/speech` con `{input, language:"es",
   response_format:"wav"}`, trata la respuesta como bytes WAV crudos,
   retira el parámetro `voice` (coherente con issue #2) y maneja 503
   `tts_busy`; `test_06` pasa a verificar la ruta y el rechazo 503.
   Coste: pequeño (un método y un test); elimina la promesa falsa.
2. **Alternativa — sólo documental:** retirar la promesa de TTS del
   docstring y de la demo, dejando el método marcado como no funcional.
   Más barato, pero deja un método que siempre falla contra el servicio
   real y una demo que engaña si alguien la ejecuta.
3. **No recomendada — extender `/v1/chat/completions` con
   `modalities`/`audio`** para soportar TTS estilo OpenAI: exige
   contrato nuevo del gateway con migración declarada y medición del
   GGUF congelado; contradice la decisión de voz fija y multiplica el
   coste de mantenimiento del dialecto.

## Ronda adversarial propia (diff completo, rondas 1 + 2)

Contexto fresco simulado: revisión sólo del diff y de las specs, sin
apoyarse en la intención de los cambios. Revisor fresco real de otra
familia (agy/Gemini): pendiente, lo ordena el Operador.

| Clase del catálogo | Ataque y resultado |
|---|---|
| Entrada no confiable e inyección | `args` llega validado como objeto desde `handle_post`; las claves extra se listan con `sorted(set(...))` y viajan por `json.dumps` (escapado). Rechazo antes de `_sintetizar_wav`; WAV de salida validado dentro de `_sintetizar_wav` (fail-closed, sin cambios). |
| Autorización | El scope `speech:synthesize` se verifica en `handle_post` antes del handler; el rechazo de campos ocurre después del scope y sin tocar el dispatcher ni el cerrojo. Un proyecto sin scope sigue recibiendo `insufficient_scope` (`test_11` en verde). |
| Secretos | Sin secretos en el diff; el texto sigue en archivo 0600 dentro de `_sintetizar_wav` (probado en ronda 1 y sin cambios). |
| Concurrencia | El camino de rechazo no adquiere `LOCK_TTS` (no hay retención ni hueco); el caso válido conserva el 503 sin cola de `test_08`. |
| Recursos no liberados | `_sintetizar_wav` libera cerrojo y temporal en `finally` (sin cambios); los nuevos tests no abren recursos (sin sockets). |
| Trabajo no acotado | Límite 1..600 intacto antes de sintetizar; el mensaje de rechazo lista campos extra acotados por el límite de cuerpo del gateway (`MAX_BODY_BYTES`) aguas arriba. |
| Errores silenciados | El rechazo es error estructurado nombrando el campo; no se tragó ningún código. Se detectó un silencio preexistente fuera de alcance: `cli.py` ignora `--voice/--speed` sin avisar (decisión 3). |
| Contrato roto | Cotejo byte a byte: contrato v2 `synthesize_speech` = `input` + `response_format` («wav»; defecto «wav») y salida sin voz ↔ catálogo remoto ↔ stdio ↔ SPEC-i1-vm enmendada: concuerdan. Desajuste real restante: SPEC-i3 §4.6, fuera de alcance (decisión 1). Nota: el remoto tampoco exige «caracteres legibles» en `input` (SPEC-i3) ni control chars (el dialecto HTTP lo hace en `/v1/audio/speech`); preexistente, se pliega en la misma decisión 1 para no endurecer código más allá de su SPEC. |
| Test que no prueba el requisito | RED como control positivo: los 9 tests nuevos fallaron contra el árbol sin corregir exactamente por las propiedades que dicen probar (`red-intento-2.txt`). Las pruebas HTTP de rechazo no cuentan llamadas de gateway (lo hace la unidad); división declarada: HTTP prueba cableado, unidad prueba frontera. |

Hallazgos de la ronda: ningún BLOCKER ni HIGH en alcance. Fuera de
alcance, documentados: SPEC-i3 §4.6 (alto documental, decisión 1),
cliente perfil W (medio, decisión 2), `cli.py --voice/--speed` (bajo,
decisión 3). Un ajuste propio durante GREEN: la primera versión de
`test_catalogo_cerrado_en_tools_list` exigía `{input}` exacto y falló
contra la adición correcta de `response_format` (que el contrato y el
stdio ya declaran); se corrigió el test, no el producto, antes de las
dos pasadas definitivas.

## Compatibilidad y migración

Igual que en la superficie stdio (ronda 1): los consumidores MCP remotos
que envíen `voice` o `speed` —incluso con los valores que antes eran
predeterminados— reciben `isError:true` estructurado
(`invalid_payload`, «campos no declarados en el contrato» con la lista
de campos) y deben omitirlos; reintentar sin cambiar argumentos repite
el rechazo. El catálogo `tools/list` ya no los anuncia, por lo que un
consumidor que se guíe por el catálogo no los enviará. La respuesta
exitosa no atribuye voz: `format:"wav"` describe el formato aplicado.
La elección de otra voz sigue requiriendo otro motor; no se afirma que
el GGUF congelado admita selección. Sin cambios para quien ya envía
sólo `input` (o añade `response_format:"wav"`), ni para v1 (intacto;
`src/mcp_server.py` no declara voz).

## Decisiones para el Operador

1. **Recomendada — autorizar la enmienda de `SPEC-i3-mcp-remote.md`
   §4.6** en una ronda futura: retirar `voice`/`speed`, salida sin voz,
   argumentos `input` + `response_format`, voz fija con procedencia
   issue #2 (2026-11-07) y, si se quiere concordancia fina, la
   restricción de caracteres legibles en `input`. Evidencia: §4.6 líneas
   191–202 contradicen al código corregido y al catálogo remoto.
   Alternativa: nota puntual de supersesión en §4.6; cuesta mantener una
   fuente activa contradictoria para todo consumidor del MCP remoto.
2. **Recomendada — abrir ronda para `examples/cliente_perfil_w.py` y su
   `test_06`** con la opción 1 de la investigación PERFIL-W (ruta real
   `/v1/audio/speech`, respuesta binaria, sin `voice`). Evidencia:
   rechazo `400 unknown_field` garantizado por `CLAVES_TOP` hoy.
   Alternativa: sólo documental (quitar la promesa del docstring); cuesta
   dejar un método que siempre falla contra el servicio real.
3. **Recomendada — decidir el destino de `--voice/--speed` en
   `src/cli.py speech`.** El payload nunca los incluye: son no-ops
   silenciosos. Recomiendo retirarlos (o rechazarlos con error) en una
   ronda de CLI. Alternativa: documentarlos como ignorados; cuesta
   sorpresa silenciosa para el usuario que espera otra voz.
4. Sin decisión: el sandbox permitió hoy bind efímero y las 21 pruebas
   remotas HTTP corrieron completas — la limitación de la ronda 1 no
   afecta a esta; no se necesita re-ejecución en otro entorno.

No se ejecutaron motor, `run/serve.sh`, `run/stop.sh`, gateways reales,
red externa, `kill` ni operaciones Git persistentes. Sin commit: el
árbol queda con los cambios de las rondas 1 y 2 sin confirmar, según
mandato.
