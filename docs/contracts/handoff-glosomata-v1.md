# Handoff Glosomata v1 — oído, boca y cerebro para conversación hablada

> Interfaz para que Glosomata convierta un agente conversacional de texto
> en conversador por voz, consumiendo LFM3-Omni como un motor más
> (ADR-007, división de responsabilidades registrada: LFM3 = inferencia,
> Glosomata = captura/reproducción/motores de voz, Lalia-Akuo = turnos).
> Latencias y hallazgos de voz MEDIDOS el 2026-11-10 con micrófono real
> del Operador; evidencia en
> `docs/reviews/evidence/motor-2-31689/` (voz-registros.txt).

## 0. Estado del motor consumido (par 2, ADR-014)

- llama.cpp master `54cde710` (fix realtime #31689) + GGUF
  LiquidAI/LFM3-Omni-2B Q4_K_M sin cambio; arranque con
  `--tts-lang es` (run/serve.sh).
- Superficies: motor HTTP en 8091 (contrato superficie-inferencia v1),
  gateway v2 en 8092 (dialecto v2 estricto), solo 127.0.0.1,
  sin api-key en loopback (CERRADA-6).
- `POST /v1/audio/speech` en el gateway: voz fija `es` (issue #2),
  `input` 1..600 caracteres imprimibles, `response_format: wav`,
  rechaza `voice`/`speaker_ref`/`stream`, exclusión mutua (503 sin cola).

## 1. Oído — ASR (listo, medido)

`POST http://127.0.0.1:8091/v1/audio/transcriptions` (multipart):

    curl -s -F file=@entrada.wav -F model=x \
      http://127.0.0.1:8091/v1/audio/transcriptions

- WAV 16 kHz mono s16; respuesta `{"text": "..."}`.
- Medido 2026-11-10: 0.4–0.9 s por turno, español exacto (transcribió
  preguntas completas del Operador sin error).
- Nota contractual: ruta del motor (8091); el gateway v2 no la expone
  como ruta propia — su vía contratada de audio de entrada es chat con
  `input_audio` (dialecto v2).

## 2. Cerebro — chat (agente de texto sin cambios)

El agente conversacional existente sigue igual; si se quiere cerebro
local, `POST http://127.0.0.1:8092/v1/chat/completions` (gateway,
dialecto v2 estricto con input_audio de entrada) o 8091 (contrato v1).
Medido 0.3–1.1 s por respuesta breve.

## 3. Boca — dos vías con voces medidas

| Vía | Latencia por frase | Registro |
|---|---|---|
| Motores propios de Glosomata (Piper/Kokoro calientes) | sub-segundo si están calientes | el que Glosomata opere |
| llama-tts vía LFM3 (gateway `/v1/audio/speech`, voz fija es) | 2.0–4.7 s (recarga de modelo por llamada, ADR-007) | masculina 130–156 Hz / femenina 233–255 Hz, 6/6 turnos estables |

- Voz premium seleccionable (`--tts-voice male|female`) existe a nivel
  motor y está validada de oído, pero NO está contratada para
  consumidores: abrir la selección de voz es la decisión B2 pendiente
  del Operador (issue #2 fijó voz fija).
- Referencia ejecutable del bucle completo:
  `examples/conversacion_voz_hibrida.py` (`--voz male|female`),
  corrida real 6/6 turnos con micrófono del Operador.

## 4. Turnos — patrón medido

Corte por silencio: captura 16 kHz mono, umbral adaptativo (3x piso de
ruido inicial + 250 RMS), cierre con ~1.4 s de silencio tras habla,
tope 10 s. Probado con micrófono real (MacBook Air, ffmpeg
avfoundation `:0`). Pendiente fino: el umbral necesita calibración por
ambiente; barge-in (interrupción) es territorio Lalia-Akuo.

## 5. Realtime WS (experimental, NO contratado)

`ws://127.0.0.1:8091/v1/realtime` — primera voz 0.3–0.45 s, pero el
audio es continuación de conversación: sigue el registro del
interlocutor y deriva en sesiones largas (123->224 Hz reproducidos).
No puede garantizar voz fija con este modelo; no aparece en
capabilities y su anuncio futuro requiere gate propio. Para
Glosomata hoy: usar solo si se ACEPTA voz espejo como característica.

## 6. Latencia total esperada (conversación hablada)

| Configuración | Respuesta tras silencio del humano |
|---|---|
| Glosomata con TTS propio caliente | ~1–2 s (objetivo alcanzable) |
| Bucle híbrido con llama-tts (probado) | 3.1–6.3 s |

Dúplex instantáneo tipo llamada: bloqueado a nivel motor (ADR-007,
bug upstream #31689 corregido para voz de disparo único; la sesión
realtime dúplex con voz fija sigue sin garantía).

## 7. Checklist de integración en Glosomata

1. Consumidor de ASR: cliente HTTP multipart a
   `/v1/audio/transcriptions` (ver arriba).
2. Adaptador de boca: `POST /v1/audio/speech` en 8092 (voz fija es,
   WAV); manejar 503 overloaded sin cola (exclusión mutua).
3. Bucle de turnos con corte por silencio (patrón §4).
4. (Opcional) voces premium male/female: esperar decisión B2 del
   Operador (contrato v2) — a nivel motor ya funciona.
5. (Opcional) modo espejo realtime WS: sólo con aceptación explícita
   de voz variable (§5).
6. Ciclo de vida: el motor se arranca/para con decisión del Operador
   (`run/serve.sh` / `run/stop.sh`); Glosomata debe tratar 8091/8092
   como dependencias locales, jamás gestionar su ciclo.

## 8. Pendientes contractuales que tocan este handoff

- issue #3 de LFM3-Omni: superficie TTS formal para consumidores
  (abierto, sin mandato) — este handoff es su caso de uso concreto.
- Decisión B2 (selección de voz a consumidores): pendiente Operador.
- LOW-N1 y SPEC-i4-c: ajustes documentales independientes.
