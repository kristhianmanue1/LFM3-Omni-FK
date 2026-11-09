# fix-issue2-voz-fija — informe del ejecutor, intento 3

## Capa técnica

```text
id = fix-issue2-voz-fija-intento-3
date = 2026-11-09
time_utc = 23:41:59Z
head_sha = 7fd40fc7328bcb87a44e418de455a67d52022df9
model = GLM 5.3 Flash (autodeclarado)
STATE = OK
GATE = MED-1, LOW-1, LOW-2 y LOW-3 cerrados en su alcance (SPEC-i3 §4.6 y SPEC-i4:101 enmendadas, test de concordancia fortalecido con RED/GREEN, corrección de registro en este informe); tres gates OK, drift al día, 89 pruebas OK (test_mcp_remote 21 dos pasadas + test_mcp_server_v2 47), sin escucha en 8091/8092/8443 antes y después; código producto congelado: cero ediciones bajo src/ esta ronda
PENDING = firma real de examples/cliente_perfil_w.py con su test_06 (decisión 2 del intento 2), destino de --voice/--speed en cli.py (decisión 3) y elección sobre «caracteres legibles» en §4.6 (nueva decisión 3); el código hoy no coincide aún con la firma declarada en SPEC-i4
DECISION = proceed
EVIDENCE
- red-intento-3.txt: el test de concordancia fortalecido falla hoy contra la SPEC-i3 sin enmendar, exactamente en la propiedad nueva (assertNotRegex "`voice`" en §4.6); las superficies previas (SPEC-i1, contrato, catálogo remoto) en verde antes del fallo; exit=1 -> pass
- green-intento-3.txt: tests.test_mcp_remote 21 OK dos pasadas consecutivas (exit=0) y tests.test_mcp_server_v2 47 OK; listeners sin escucha en 8091/8092/8443 antes y después -> pass
- listeners-before-intento-3.txt y listeners-after-intento-3.txt: ambos vacíos -> pass
- gates-intento-3.txt: check_sizes OK (440 archivos; ruta de lectura 1799/1800), check_plans OK (2 planes), check_reports OK (25 reportes con capa técnica, 1 exento); drift corpus/v10 y gate/v14 al día; git diff --check limpio; git status acotado a los 8 ficheros acumulados de las rondas 1-3 y el expediente sin track -> pass
- concordancia en cuatro superficies verificada por test: SPEC-i1-vm ↔ contrato v2 (segmentos arguments y salida de synthesize_speech sin voice/speed) ↔ SPEC-i3 §4.6 enmendada ↔ esquemas idénticos de synthesize_speech en mcp_server_v2.TOOLS y TOOLS_REMOTE -> pass
- LOW-1 (registro): mcp_remote.py:379-383 ejecuta dispatcher.acquire_slot antes de _ejecutar_tool; gateway_auth.py:222 y 233 elevan 429 rate_limit_exceeded y 503 overloaded: una petición remota con voice/speed consume puesto de cola y puede recibir 429/503 antes del rechazo de contrato; informe-intento-2.md:154 queda corregido por registro en este informe, sin editar la evidencia inmutable -> pass
report_sha256 = c231908f74dad92ac7bee4949f8ab68d18ff2bb26bf5894ee185737ab13c9154
```

## Disposición de los hallazgos de la revisión r3

1. **[MED-1] SPEC-i3-mcp-remote.md §4.6 prometía la voz retirada —
   fixed.** Enmienda acotada de §4.6: argumentos `input` +
   `response_format` (enum «wav», defecto «wav», como el contrato y ambos
   catálogos), nota de voz fija desde issue #2 (decisión del Operador,
   2026-11-07) con rechazo de campos no declarados en la frontera MCP
   remota antes de llamar al gateway (`invalid_payload`, «arguments
   inválidos: campos no declarados en el contrato», nombrando cada
   campo), salida sin atribución de voz ni velocidad con `format:"wav"`
   como formato aplicado, y remisión al contrato `mcp-tools-v2.md`,
   sección «Voz fija y migración». Retirados `voice`, `speed` y el campo
   `"voice"` de la salida de ejemplo. El resto de §4.6 (contención de
   concurrencia `tts_busy`) y las demás secciones de la SPEC quedan
   intactas. Evidencia: RED en `red-intento-3.txt`, GREEN en
   `green-intento-3.txt`.
2. **[LOW-3] SPEC-i4:101 declaraba `synthesize_speech(text, voice=None)`
   — fixed.** Elección documentada: firma sin `voice`
   (`synthesize_speech(text)`) más nota de voz fija con la misma
   procedencia y remisión al contrato, en dos líneas añadidas; sin tocar
   nada más de la SPEC. Nota honesta: el SDK
   `examples/cliente_perfil_w.py` todavía define `voice=None` hoy; la
   SPEC queda alineada con el contrato vigente y el código del SDK sigue
   siendo la decisión 2 del intento 2 (fuera de alcance esta ronda).
3. **[LOW-2] Test de concordancia probaba menos de lo que decía —
   fixed.** `test_concordancia_documental_spec_contrato_catalogo`
   fortalecido (único test editado; import de `TOOLS` añadido para él):
   ahora verifica además (a) que el contrato
   `docs/contracts/mcp-tools-v2.md` no declara `voice`/`speed` en los
   segmentos de argumentos y de salida de `synthesize_speech` (la mención
   de migración vive en su propia sección y no se le exige silencio),
   (b) que la SPEC-i3 §4.6 enmendada no declara `voice`/`speed` —ni como
   argumento entre acentos graves ni como campo de salida JSON— y declara
   voz fija, procedencia 2026-11-07 y la remisión «Voz fija y migración»,
   y (c) que los esquemas `inputSchema` de `synthesize_speech` en
   `mcp_server_v2.TOOLS` y `TOOLS_REMOTE` son idénticos, con
   propiedades exactas `{input, response_format}` y
   `additionalProperties:false` en ambos. RED como control positivo:
   falló contra la SPEC sin enmendar justo en la propiedad nueva.
4. **[LOW-1] Corrección de registro, no de informe — documented.** Ver
   sección siguiente. `informe-intento-2.md` no se tocó (evidencia
   inmutable); la corrección queda registrada aquí.

## Corrección de registro (LOW-1)

`informe-intento-2.md` (línea 154, tabla adversarial, fila Autorización)
afirma que el rechazo remoto de `voice`/`speed` ocurre «sin tocar el
dispatcher ni el cerrojo». Verificación de esta ronda:

- La parte del cerrojo sigue siendo cierta: el rechazo dentro de
  `_tool_synthesize_speech` no adquiere `LOCK_TTS`.
- La parte del dispatcher era incorrecta para el camino HTTP completo:
  `mcp_remote.py:379-383` ejecuta `dispatcher.acquire_slot(project_id,
  rl_cfg)` **antes** de `_ejecutar_tool` (línea 386), y
  `gateway_auth.py:222` y `:233` elevan `429 rate_limit_exceeded` y
  `503 overloaded` dentro de `acquire_slot`. Una petición con `voice` o
  `speed` consume un puesto de cola y puede recibir 429/503 antes del
  error de contrato `invalid_payload`.
- Es comportamiento preexistente para cualquier argumento inválido en el
  remoto (no introducido por las rondas 1-2) y sin efecto lateral
  duradero: el `finally` de `mcp_remote.py:389-391` libera el slot.
- La afirmación del intento 2 era cierta para las pruebas de frontera
  (`_tool_synthesize_speech` invocado directo, sin dispatcher) y para la
  superficie stdio v2, que no pasa por `acquire_slot`.

No se editó `informe-intento-2.md`; esta sección es la corrección de
registro.

## Cambios por archivo (esta ronda)

- `docs/specs/SPEC-i3-mcp-remote.md`: enmienda acotada de §4.6 (argumentos
  sin voice/speed y con `response_format`, nota de voz fija con
  procedencia y remisión, salida sin atribución).
- `docs/specs/SPEC-i4-c-clientes-y-perfiles.md`: enmienda acotada de la
  línea 101 (firma sin `voice` y nota de voz fija).
- `tests/test_mcp_remote.py`: import de `TOOLS` (`mcp_server_v2`) y
  fortalecimiento exclusivo de
  `test_concordancia_documental_spec_contrato_catalogo`.
- Expediente: `red-intento-3.txt`, `green-intento-3.txt`,
  `gates-intento-3.txt`, `listeners-before-intento-3.txt`,
  `listeners-after-intento-3.txt` y este informe.
- **Sin cambios bajo `src/`** (congelado por mandato): el diff de
  `src/mcp_remote.py` y `src/mcp_server_v2.py` visible en `git status` es
  el acumulado de las rondas 1-2, conservado sin revertir nada.

## Propiedades y verificaciones

| Propiedad | Estado | Evidencia y límite |
|---|---|---|
| RED del test fortalecido contra SPEC-i3 sin enmendar | pass | `red-intento-3.txt`: fallo exacto en §4.6, exit=1 |
| GREEN: SPEC-i3 §4.6 sin declaraciones voice/speed, con voz fija y procedencia | pass | `green-intento-3.txt` (21 OK ×2) |
| Contrato sin voice/speed en argumentos y salida de synthesize_speech | pass | Test (segmentos acotados); la sección de migración puede nombrarlos |
| Esquemas synthesize_speech idénticos en TOOLS y TOOLS_REMOTE | pass | Test: `inputSchema` iguales, `{input, response_format}` exacto, `additionalProperties:false` |
| SPEC-i4:101 sin `voice` en la firma del SDK | pass | Diff; el código del SDK real sigue pendiente (decisión 2) |
| Corrección LOW-1 registrada sin editar informe previo | pass | Sección «Corrección de registro»; anclas `mcp_remote.py:379-383`, `gateway_auth.py:222/233` |
| Módulos dos pasadas + stdio v2 | pass | 21 OK ×2 + 47 OK; sin errores de bind |
| Listeners 8091/8092/8443 antes/después | pass | Ambos ficheros vacíos; sin servicios arrancados |
| Tres gates, drift, `git diff --check`, `git status` | pass | `gates-intento-3.txt` |
| Anchura ~80 columnas en líneas editadas | pass | Sólo líneas preexistentes (213-214 de SPEC-i3) superan 80 |
| Rechazo remoto aislado del dispatcher (afirmación intento 2) | fail → corrected | Corrección de registro LOW-1; comportamiento preexistente |
| Verificación contra motor real | inconclusive | Prohibido arrancar motor; pruebas con runners falsos y ficheros falsos |

## Ronda adversarial propia (diff acumulado, sesgo de esta ronda)

Contexto fresco simulado: revisión del diff de la ronda 3 contra el
catálogo `.skevi/review-defect-catalog.md`, sin apoyarme en la intención
de los cambios.

| Clase del catálogo | Ataque y resultado |
|---|---|
| Entrada no confiable e inyección | El test lee tres ficheros del propio repo (contenido confiable por procedencia) y los trocea por marcadores con `split(sep, 1)[1]`: si un marcador desaparece o se reordena, lanza `IndexError` y el test muere en voz alta, nunca en verde silencioso. Sin `eval`/`exec` ni consumo de salida de modelo en el camino nuevo. |
| Autorización | Ronda 3 no toca rutas de autorización (sólo docs y un test). El scope `speech:synthesize` y el orden scope → slot → rechazo quedan descritos con precisión en la corrección LOW-1, sin prometer aislamiento que no existe. |
| Secretos | El diff elimina el nombre de voz por defecto; no introduce secretos. Los tokens del test son falsos preexistentes. |
| Concurrencia | Los cambios documentales no alteran caminos concurrentes. El test lee ficheros estáticos; `MCPRemoteHandler` se instancia por prueba en la clase sin sockets. |
| Recursos no liberados | `read_text` cierra por construcción; el test fortalecido no abre sockets ni ficheros persistentes. |
| Trabajo no acotado | Lecturas acotadas a tres ficheros del repo; sin bucles nuevos. |
| Errores silenciados | Los gates guardan `exit=` explícito. Hallazgo propio: la primera captura de `red-intento-3.txt` registraba `exit=0` porque un `echo` intermedio reseteaba `$?`; se detectó antes de usar la evidencia y se regeneró con `exit=1` real. |
| Contrato roto | Cotejo por test, no por lectura: SPEC-i1 ↔ contrato (segmentos arguments/salida) ↔ SPEC-i3 §4.6 ↔ ambos catálogos. Residual declarado, no nuevo: §4.6 conserva «caracteres legibles» que el remoto no fuerza en frontera (el dialecto HTTP `/v1/audio/speech` sí rechaza caracteres de control aguas arriba); queda como decisión 3. SPEC-i4 ahora lidera al código del SDK (firma sin `voice`); desfase declarado, no ocultado. |
| Test que no prueba el requisito | Control positivo por RED: el test falló contra el árbol sin enmendar exactamente en la propiedad §4.6 que dice probar (`red-intento-3.txt`), y pasó tras la enmienda sin tocar producto. |

Hallazgos de la ronda: ninguno BLOCKER ni HIGH en alcance. Residuales
declarados (no hallazgos nuevos): «caracteres legibles» en §4.6 y firma
del SDK pendiente en `examples/`, ambos con decisión para el Operador.

## Compatibilidad y migración

Sin cambios de superficie en esta ronda: el contrato, los catálogos y los
handlers siguen exactamente como tras la ronda 2. Las enmiendas alinean
dos documentos con la decisión vigente del Operador (issue #2,
2026-11-07). Para consumidores: nada nuevo que hacer; quien ya omite
`voice`/`speed` no ve diferencia. La SPEC-i4 describe la firma objetivo
del SDK de referencia; la firma actual de `examples/cliente_perfil_w.py`
(`voice=None`) sigue funcionando contra el gateway real hasta la ronda de
reorientación decidida (el gateway ya rechaza ese parámetro con
`400 unknown_field`), por lo que el desfase SPEC-código es prospectivo y
no rompe llamadas existentes más allá de lo ya documentado.

## Decisiones para el Operador

1. **Recomendada — abrir la ronda de `examples/cliente_perfil_w.py` y su
   `test_06`** (ya era la decisión 2 del intento 2): la SPEC-i4 enmendada
   declara hoy `synthesize_speech(text)` y el SDK sigue con `voice=None`
   y la ruta equivocada (`/v1/chat/completions` con `modalities`/`audio`,
   rechazado `400 unknown_field` por `CLAVES_TOP`). Alternativa: revertir
   la nota de firma en SPEC-i4 hasta que exista la ronda; cuesta dejar la
   SPEC describiendo la intención y no el árbol.
2. **Recomendada — decidir el destino de `--voice/--speed` en
   `src/cli.py speech`** (decisión 3 del intento 2, sin cambios esta
   ronda): siguen siendo no-ops silenciosos. Recomiendo retirarlos o
   rechazarlos con error en una ronda de CLI. Alternativa: documentarlos
   como ignorados.
3. **Nueva — «caracteres legibles» en §4.6 de SPEC-i3.** Mantuve la
   palabra en la enmienda (cambio mínimo pedido) aunque el handler remoto
   no fuerza rechazo de caracteres de control en frontera; el dialecto
   HTTP `/v1/audio/speech` sí lo hace aguas arriba. Recomiendo dejarla
   (describe el contrato de extremo a extremo). Alternativa: retirar
   «legibles» en una futura enmienda documental para concordancia fina
   con la validación local del remoto.

No se ejecutaron motor, `run/serve.sh`, `run/stop.sh`, gateways reales,
red externa, `kill` ni operaciones Git persistentes. Sin commit: el árbol
queda con los cambios acumulados de las rondas 1-3 sin confirmar, según
mandato.
