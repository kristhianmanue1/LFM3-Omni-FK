# Propuesta: ajuste del PLAN LFM3-2 para capacidades multimodales

Fecha: 2026-11-04. Base: main = 310e7ff (árbol limpio).
Encargo del Operador: integrar en el PLAN LFM3-2 existente (no un plan nuevo)
las capacidades técnicamente soportadas por LFM3-Omni-2B, priorizando voz y
conversación humano-agente; menor complejidad; no reabrir iteraciones cerradas
sin causa técnica demostrable; no dependencias artificiales local→remoto.
Estado: propuesta del autor para ronda adversarial; nada aplicado aún.

## 1. Evidencia de sesión (sondas loopback contra el motor congelado)

Motor: llama-server 0.8.0 b11960-8642541b2, modelo Q4_K_M, mmproj
`mmproj-LFM3-Omni-2B-Q4_0.gguf`, arranque `--reasoning off --temp 0
--host 127.0.0.1 --port 8091`. Artefactos en el directorio de esta propuesta.

| ID | Sonda | Resultado |
|---|---|---|
| P-1 | GET /props | modalities {vision:true, video:true, audio:true} |
| P-2 | chat `input_audio` {data,format:wav} WAV `say` es-MX + system «Perform ASR in Spanish.» | «El paquete llega el martes a las 3 de la tarde.» exacto, 1.76 s |
| P-3 | mismo audio + pregunta de comprensión | devolvió la transcripción, no la respuesta (comprensión parcial) |
| P-4 | chat `audio_url` (lo que envía B-T8) | 400 unsupported content[].type |
| P-5 | POST /v1/audio/transcriptions multipart | mismo texto exacto, 0.57 s |
| P-6 | chat con `modalities:["text","audio"]` | ignorado en silencio: sólo texto |
| P-7 | `video_url` e `input_video` mp4 sintético 2.5 s, 10 frames (rojo→azul) | aceptado; respuesta temporal FALSA («red… red»), 68 prompt tokens |
| P-8 | /v1/realtime output_modalities ["audio"] (8091 temp 0; 8093 temp 0.8; 8093 temp 0.4 rp 1.2) | voz ininteligible en es/en; un caso 215 s de bucle |
| P-9 | llama-tts --tts-lang es (pesos en caché) | voz clara; re-ASR exacto; Operador la oyó: «clara, un poco semi robotizada, buena pronunciación en español» |
| P-10 | /v1/realtime output_modalities ["text","audio"] | texto correcto; voz «español con acento de voz en inglés» (Operador); re-ASR «Apacete yiga el martes al atraso» |
| P-11 | código b11960 y master (v0.9.0) `tools/server/server-realtime.cpp` | no pasa `inp.lang`/`inp.voice` al gen-audio; `tools/tts/tts.cpp` sí (common_chat_get_tts_prompt + lang/voice); muestreo de frames de audio fijado internamente (card: temp 0.4, rp 1.2) — `--temp` no lo gobierna |
| P-12 | conversación humana por turnos (ASR 8091 → texto 8091 → llama-tts) | 5 turnos OK; ASR 0.4–0.9 s; voz 2.6–11 s |
| P-13 | conversación casi tiempo real (VAD por energía, SSE, TTS por frase) | 6 turnos OK; primera voz 2.8–4.4 s tras silencio del Operador |
| P-14 | issue upstream | ggml-org/llama.cpp#31689 (autorizado por el Operador) |

Limitación: juez de inteligibilidad = ASR del mismo modelo (sesgo) más oído
del Operador en P-9/P-10/P-12/P-13; no hay corpus ni métrica de error.

## 2. Diagnóstico

D1. B-T8 es falso negativo: prueba un tipo de contenido inexistente con WAV
falso. `verificaciones-motor.md` §2/§5, `superficie-inferencia-v1.md`
(«audio de entrada por chat se rechaza con 400») y `tests/golden/casos.json`
afirman una limitación inexistente; el 8091 acepta audio y video sin
declararlo. Corrección de hecho; no reabre I0/I1 (su alcance texto/imagen y
su gateway 8092, que rechaza audio, siguen correctos).
D2. Voz, ASR y video NO requieren modelo/motor nuevos: están en el artefacto
congelado. Su ubicación en I6 (candidatos/promoción) y S-11 «futuro
condicionado» crean dependencia artificial.
D3. SSE local está atado a I3 (MCP remoto/OAuth) sin necesidad técnica.
D4. Realtime voz↔voz en español no es usable con ningún build actual (P-11).
D5. Drift documental: `iteraciones-servicio.md` «todas not_started»;
README «Plan vigente: PLAN-1»; `project-manifest.yaml` anuncia audio/video/
voz no ofrecidos por contrato.

## 3. Cambios propuestos (por archivo)

### 3.1 Ampliación delimitada de I1 (sin nueva fase): tareas I1-V*

Todas loopback, motor/modelo congelados, sin dependencias nuevas de Python,
con registro propio en `registro-avance.md` y cierre `accepted_local`.

- I1-VA — ASR y comprensión de audio. Gateway: `POST /v1/audio/transcriptions`
  y parte `input_audio` en chat (validación WAV: RIFF/fmt/PCM16, mono,
  16 kHz o re-muestreo declarado, techo bytes y duración antes del motor);
  tool MCP stdio `transcribe_audio`. Primer paso: reescribir B-T8 a la
  propiedad correcta (input_audio aceptado en 8091 = capacidad del motor;
  audio_url rechazado) con registro.
  Gate: 3–5 clips (`say` + ≥1 voz consentida del Operador) con propiedad
  «contiene palabras clave» fijada antes; WAV corrupto/enorme → 400 antes
  del motor; capabilities `audio` de entrada sólo tras gate.
- I1-VS — síntesis de voz. Fachada del gateway `POST /v1/audio/speech`
  sobre `llama-tts --tts-lang es` como subproceso (sin shell, texto por argv
  acotado), un único proceso de voz a la vez, timeout; tool `synthesize_speech`.
  Sin clonación ni speaker_ref. Gate: ida-vuelta TTS→ASR contiene el texto;
  límite de caracteres/segundos; escucha del Operador registrada.
- I1-VR — conversación local. Patrón probado P-13: fin de turno por señal
  (silencio medido o commit explícito del cliente), SSE de texto local en el
  gateway (sale de I3), voz por frase, cancelación del turno en curso.
  Realtime nativo /v1/realtime NO se ofrece hasta resolver #31689 (D4).
  Gate: primera voz ≤ 5 s tras fin de turno en hardware del Operador
  (umbral candidato, fijar antes de medir); cancelación detiene TTS y libera
  el proceso; dos sesiones no se cruzan.
- I1-VV — video. `video_url`/`input_video` con límites (duración, FPS,
  frames, bytes); ffmpeg/ffprobe del sistema registrado como dependencia de
  ejecución (inventario, versión). Gate: 2–3 preguntas temporales
  sintéticas (P-7 hoy falla); si no pasan, no se anuncia video.

Orden: VA → VS → VR → VV. VA no depende de nada nuevo; VS de D-08; VR de VA+VS;
VV independiente (puede adelantarse si D-06a lo prioriza).

### 3.2 PLAN-2-servicio-compartido.md
- §Secuencia: «I0 -> I1 (+ ampliación I1-V local) -> I2 ...»; I1-V no
  bloquea I2 ni depende de él.
- Bloque TAREAS: insertar TAREA I1-VA/VS/VR/VV tras I1-U.
- I3-M: quitar SSE de texto local (queda «SSE bajo proxy remoto»).
- I6-E/I6-U sin cambio de texto; se precisa en iteraciones que I6 no
  incluye modalidades ya presentes en el artefacto baseline.

### 3.3 iteraciones-servicio.md
- Nueva sección «I1-V — Modalidades locales del artefacto vigente» con los
  gates de 3.1 y rollback (retirar ruta del allowlist y capabilities).
- §I6 párrafo Audio/Voz/Video: se conserva para modalidades de candidatos
  nuevos; las del baseline remiten a I1-V.
- Corregir «Actualmente todas las iteraciones están not_started».

### 3.4 objetivo-y-alcance-servicio.md
- S-11: «Voz/video verificables» pasa de «futuro condicionado» a
  «imprescindible local (I1-V)»; video condicionado a su gate.

### 3.5 decisiones-servicio.md
- D-06 se divide: D-06a prioridad de modalidad = ACEPTADA (Operador,
  2026-11-04: voz → conversación → visión/video → combinada); D-06b
  hardware/presupuesto antes de I6 = pendiente.
- D-08 estrategia de voz: propuesta `llama-tts` subproceso (P-9/P-13);
  realtime nativo descartado mientras #31689 abierto. Pendiente de aceptación.
- D-09 datos de audio: sólo muestras sintéticas o consentidas, sin
  persistencia por defecto, logs sin contenido. Pendiente.

### 3.6 Contratos
- `superficie-inferencia-v1.md`: errata fechada sobre B-T8: el motor 8091
  acepta `input_audio`/video; v1 sigue sin ofrecerlos (no cambia frontera v1).
- `servicio-general-v2.md` y `perfiles-servicio-v2.md` (PROPUESTOS): añadir
  modalidades audio/voz/video con límites por SPEC de cada I1-V*; perfil D:
  observaciones de audio/video sólo como propuesta, controlador independiente.
- `mcp-tools-v1.md`: tools nuevas como adición (o v2 según su regla de
  compatibilidad).

### 3.7 verificaciones-motor.md
- Adenda fechada §8: P-1..P-11 resumidas; B-T8 reclasificado (corrección del
  hecho, no reescritura del histórico).

### 3.8 ADR-006 (nuevo): estrategia de voz local
- Contexto P-8..P-11; decisión llama-tts subproceso para TTS, ASR por
  servidor 8091, realtime nativo fuera hasta corrección upstream;
  consecuencias (latencia 2.8–4.4 s, recarga del modelo por llamada,
  memoria pico +~3 GB durante TTS).

### 3.9 Drift
- README: «Plan vigente: PLAN-2» y estado de voz; `project-manifest.yaml`:
  distinguir «ofrece» (contrato) de «motor soporta».

## 4. Lo que NO cambia
I0/I1 aceptadas; ADR-001..005; solo localhost; motor congelado; I2..I5 en lo
sustantivo; perfil D sin actuadores; Glosomata/Lalia sin cambios (LFM3 como
motor STT/TTS separado para Glosomata; realtime para conversación tipo
Lalia, por turnos con señal real).

## 5. Primera capacidad
I1-VA (ASR español): funciona hoy exacta (P-2/P-5/P-12), sin decisión
pendiente, reutiliza gateway_core y MCP stdio.

## 6. Correcciones tras ronda adversarial R1 (fix-and-retry)

Revisor: subagente de contexto fresco (Claude Opus 5.5, autodeclarado),
3 HIGH, 7 MED, 3 LOW; el autor re-verificó H1–H3, M1 y L2 contra el repo.
Esta sección PREVALECE sobre §3–§5 donde difieran.

| ID | Disposición |
|---|---|
| H1 | Nuevo ADR-006 «Modalidades locales y streaming» ENMIENDA ADR-005 en dos puntos: (a) capabilities anuncia una modalidad sólo tras su gate I1-V; (b) SSE sobre ThreadingHTTPServer stdlib permitido en I1-VR, con cancelación al desconectar del cliente y sin buffering. ADR-005 sale de §4 «no cambia» y gana una línea «enmendado por ADR-006». |
| H2 | ffmpeg/ffprobe declarados dependencia de ejecución YA EXISTENTE del motor congelado (libmtmd, PATH). Errata v1 = aviso de seguridad: «PROHIBIDO para el consumidor: input_audio, video_url, input_video en 8091» (como image_url http). TAREA previa de I1-VA: inventario_motor.py registra ffmpeg/ffprobe/llama-tts (versión+hash) y serve.sh fija PATH explícito. |
| H3 | Decidido: tools de voz/video en un adaptador MCP v2 sobre gateway_core (S-05). mcp_server.py v1 y mcp-tools-v1 intactos. |
| M1 | I1-VA depende de D-09 sólo para voz real: su gate base usa fixtures `say`; voz del Operador sólo con D-09 aceptada. WAV de las sondas de sesión: se informan al Operador para borrado o conservación. §5 corregido: «sin decisión pendiente para el gate sintético». |
| M2 | Gate VA: CER sobre corpus sintético fijado antes de medir (≥10 frases es-MX, umbral en SPEC antes de correr); capability anunciada `transcripcion`, no `audio`. «Comprensión de audio» sale de VA (P-3 la refuta) y queda como pendiente evaluable. |
| M3 | Gate VR sin cifra en el plan: SPEC fija p95, N≥20 turnos y timestamp de fin de turno ANTES de medir; P-13 es observación exploratoria, no línea base. |
| M4 | «+~3 GB» retirado como afirmación; medir pico RSS de llama-tts y swap como evidencia de VS; REQ-5/B-T10 se amplía en el SPEC de VS. |
| M5 | VS: texto al subproceso por archivo 0600 en directorio privado por petición (no argv), validado contra esquema cerrado (longitud, sin control chars), una síntesis a la vez y 503 overloaded sin cola, salida en ruta única por petición, borrado al terminar. |
| M6 | Primer corte VA: sólo `input_audio` en chat (JSON). `/v1/audio/transcriptions` multipart queda para un corte posterior con su SPEC. |
| M7 | I2-D excluye las rutas I1-V de la exposición remota salvo que su admisión/SLO las cubra con decisión explícita. |
| L1 | Gates VA/VV: sólo data URI/base64; URL http(s)/file → 400 en el gateway, cero llamadas al motor. |
| L2 | perfiles-v2 §H: «Texto libre admite SSE en I1-VR (local) e I3 (remoto)». registro-avance: I0/I1 conservan accepted_local. |
| L3 | Ningún cambio en AGENTS.md (ruta de lectura 1789/1800). |

Primer corte resultante: TAREA I1-V0 (inventario ffmpeg/llama-tts + PATH +
errata/aviso v1 + B-T8 corregido) → I1-VA (input_audio en chat, gateway +
MCP v2) → I1-VS → I1-VR (tras ADR-006) → I1-VV.
