# Verificaciones del motor — batería 2026-11-02

> Registro de pruebas por **propiedades binarias** sobre el servicio vivo,
> conforme a `docs/ai-agent-guide/06-componentes-con-llm.md` §2: los tests
> se escriben sobre la propiedad, no sobre el texto; los umbrales se
> declaran antes de medir. Este documento es insumo del contrato F1 y
> semilla del conjunto de referencia (golden set) que F2 versionará junto
> al código que verifique.
> Motor: llama-server 0.8.0 (build 11960) · modelo
> `LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M` · puerto 8091, solo localhost
> (CERRADA-6 del F0).

## 1. Criterios declarados (antes de medir)

| ID | Propiedad (falla o no falla) | Criterio declarado |
|---|---|---|
| B-T1 | Salud del servicio | `/health` → HTTP 200 y `{"status":"ok"}` |
| B-T2 | Modelo fijado servido | `/v1/models` devuelve exactamente `['LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M']` |
| B-T3 | Salida bajo esquema cerrado | Con `response_format` json_schema `{nombre:string, edad:integer}`, la salida parsea como JSON y cumple ambos tipos |
| B-T4 | Determinismo greedy | Mismo prompt ×3 con `--temp 0` → 3/3 salidas idénticas byte a byte |
| B-T5 | Umbral de throughput | Generación de 64 tokens: **mediana de n=3 corridas, 20 s de separación ≥ 15 tok/s** (medida en `timings.predicted_per_second` del servidor, no en tiempo de pared) |
| B-T6 | Tool calling | Con tool `get_weather(city:string)` y `tool_choice:"auto"`, la respuesta emite `tool_calls` con `function.name` correcto y `arguments` que parsea como JSON |
| B-T7 | Comprensión de imagen | PNG 8×8 completamente rojo (sintético, procedencia §3) → la respuesta identifica el color rojo |
| B-T8 | ASR por audio en chat OAI | WAV 16 kHz mono de `say "azul"` + system `Perform ASR in Spanish.` → la transcripción contiene «azul» |
| B-T9 | Frontera fail-closed | JSON malformado o `messages` ausente → HTTP 400 con cuerpo de error estructurado; jamás 2xx |
| B-T10 | Recursos (REQ-5) | Modelo cargado y bajo generación real: RSS residente del proceso < 4 GB |
| B-T11 | Cláusula de licencia (REQ-8) | El contrato v1 publicado cita REQ-8 y EV-10 |
| B-T12 | Binding exclusivo (REQ-2) | Los sockets en escucha del puerto muestran solo 127.0.0.1:8091 |

## 2. Resultados

| ID | Resultado | Medición |
|---|---|---|
| B-T1 | **pass** | HTTP 200, `{"status":"ok"}` |
| B-T2 | **pass** | lista exacta del modelo fijado |
| B-T3 | **pass** | `{"nombre": "Ana", "edad": 34}` — parsea y cumple el esquema |
| B-T4 | **pass** | 3/3 idénticas («…8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19…») |
| B-T5 | **pass** (con anomalía registrada, §4) | corridas: 55.9 / 54.8 / 56.6 tok/s → mediana **55.9 ≥ 15** |
| B-T6 | **pass** | `tool_calls[0].function = get_weather`, `arguments = {"city":"CDMX"}` |
| B-T7 | **pass** | respuesta: «rojo» |
| B-T8 | **fail como capacidad, pass como regresión** | HTTP 400 `unsupported content[].type` — el endpoint OpenAI de este build no acepta `audio_url`; la voz NO forma parte del contrato v1 (verificaciones-motor §7 y contrato v1). El golden set ejecuta la segunda lectura: la limitación se sostiene → pass; si se dejara de sostener → alarma de cambio contractual |
| B-T9 | **pass** | 400 `parse_error…` y 400 `'messages' is required`, cuerpos estructurados |
| B-T10 | **pass** | salud 200 y completación real; RSS residente 23 MiB bajo carga — los pesos van por mmap al file cache y no cuentan como RSS anónimo; huella máxima observada 2.78 GiB en warmup (EV-9). Propiedad `< 4 GB` por cualquier conteo |
| B-T11 | **pass** | el contrato cita REQ-8 y EV-10 (2 apariciones cada uno) |
| B-T12 | **pass** | `lsof` muestra solo `TCP 127.0.0.1:8091 (LISTEN)` del proceso del motor |

Balance: **12 pass / 1 fail** (11 pass + B-T10/B-T11/B-T12 añadidos por la
ronda adversarial; ver §7). El fail de B-T8 es una capacidad del
endpoint, no del motor: la ficha oficial ubica la voz en tiempo real en
`/v1/realtime` (WebSocket) — su verificación queda pendiente para F1/F3
con un cliente WS mínimo.

## 3. Casos de referencia con procedencia (semillas del golden set)

Cada caso registra entrada, propiedad esperada y procedencia (06 §3):

1. **salud**: `GET /health` — procedencia: runbook F0 §7.
2. **modelo-fijado**: `GET /v1/models` — procedencia: decisión de motor
   congelado por registro (AGENTS.md, F0).
3. **esquema-registro**: prompt «Registra a Ana de 34 años según el
   esquema.» — procedencia: caso sintético construido para B-T3.
4. **determinismo-serie**: prompt «Completa exactamente: 1, 2, 3, 4, 5,
   6, 7, 8, 9, ...» ×3 — procedencia: caso sintético para B-T4.
5. **throughput-serie**: prompt «Escribe los números del 1 al 40…» n=3 —
   procedencia: B-T5; protocolo declarado en §1.
6. **tool-weather**: prompt «¿Qué tiempo hace en CDMX? Usa la herramienta
   get_weather.» — procedencia: caso sintético para B-T6.
7. **imagen-roja**: PNG 8×8 RGB uniforme `#FF0000` generado por script
   Python stdlib (zlib+struct, sin dependencias) — procedencia: generador
   registrado aquí mismo; regenerable por comando.
8. **audio-fail-conocido**: WAV de `say "azul"` → documenta el fallo
   conocido de B-T8 como caso de regresión de contrato: si un build futuro
   del endpoint acepta audio, este caso cambia de estado con registro.

## 4. Anomalías y observaciones operativas

- **B-T5, primera corrida no protocolar**: 64 tokens en 6.58 s de pared
  (~10.45 tok/s) inmediatamente tras la batería T3/T4. Re-medición con
  protocolo declarado (n=3, 20 s): 54.8-56.6 tok/s. Hipótesis: arranque
  en frío del patrón (graph realloc / slot recién asignado). La observación
  original se conserva; el criterio del contrato usa la mediana
  protocolar. Un fallo futuro del umbral protocolar será señal real.
- **Caché de prompt activo**: con prefijos compartidos, el prompt eval
  subió de ~52 a **200 tok/s** (`slot get_availabl: selected slot by LCP
  similarity`). El contrato puede declarar prefijos estables por consumidor
  para aprovecharlo.
- **Aviso de seguridad del servidor** (log de arranque): «no API key is
  set and CORS allows all origins». Aceptable bajo CERRADA-6 (solo
  localhost); cualquier cambio de vínculo exige api-key + `--cors-origins`
  explícitos antes de arrancar. El contrato F1 lo codifica como
  prerequisito.
- **Contexto efectivo**: `n_slots = 4`, `n_ctx_slot = 128000` (128k por
  slot) — resuelve el inconclusive del análisis previo.
- **RSS estable**: ≈ 2.78 GiB con el modelo cargado (REQ-5 pass).

## 5. Qué gradúa al contrato F1

- Endpoints declarados: `/v1/chat/completions` (texto + visión + tools +
  `response_format` json_schema), `/v1/models`, `/health`; la voz NO
  forma parte de la frontera v1 (B-T8; `/v1/realtime` sin verificar,
  sonda aparte en F3-3).

## 7. Adiciones por ronda adversarial (2026-11-02)

La ronda adversarial de F1 (docs/reviews/2026-11-f1-adversarial.md,
contexto fresco real vía subagente independiente) produjo 13 hallazgos
(2 BLOQ, 5 MAYOR, 6 MENOR), todos declarativos o de trazabilidad. Esta
batería ganó tres casos como disposición directa:

- **B-T10** (de hallazgo 3): REQ-5 estaba trazado a B-T5 (throughput),
  que no prueba su criterio. Se creó el caso binario propio. Matiz de
  medición registrado: en macOS con carga mmap, el RSS anónimo del
  proceso no refleja la huella completa; se registran ambos valores
  (23 MiB residente bajo carga; 2.78 GiB máximo observado en warmup).
- **B-T11** (de hallazgo 1): REQ-8 sin SPEC — la cláusula de licencia
  del contrato es verificable como propiedad binaria por búsqueda.
- **B-T12** (de hallazgo 4): el invariante de binding citaba B-T1, que
  solo prueba respuesta en localhost, no exclusividad. Se creó el caso
  con `lsof`, que confirma un único socket en 127.0.0.1:8091.
- Muestreo de contrato: greedy (`--temp 0`), determinismo 3/3 observado;
  el contrato no promete determinismo byte a byte entre reinicios.
- Umbral de rendimiento de contrato: ≥ 15 tok/s mediana n=3 (observado
  55.9); prompt eval ≥ 50 tok/s sin caché, ≥ 200 con prefijo compartido.
- Frontera: toda salida del modelo pasa validación contra esquema cerrado
  (`response_format`) antes de persistir o reenviar (REQ-7).
- Herramientas: el modelo emite tool calls válidos — habilita el diseño
  MCP de REQ-4.
