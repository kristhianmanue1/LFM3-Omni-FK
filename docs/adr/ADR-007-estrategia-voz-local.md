# ADR-007: Estrategia de voz local (ASR por servidor, TTS por llama-tts)

```text
ADR-007: ASR vía llama-server 8091 (input_audio); TTS vía llama-tts
--tts-lang es como subproceso; /v1/realtime nativo fuera de alcance
Estado: propuesto (ajuste del PLAN LFM3-2, 2026-11-04); resuelve D-08
cuando el Operador lo acepte; revocable con independencia de ADR-006
Contexto: mismo modelo y mmproj registrados (ADR-001). Sondas:
  - input_audio en chat: ASR español exacto (P-2).
  - /v1/realtime: voz ininteligible con output_modalities ["audio"]
    (tres configuraciones de muestreo) y «español con acento de voz en
    inglés» con ["text","audio"] (oído del Operador, P-10). Causa en
    código: server-realtime.cpp no pasa lang/voice al generador de
    audio (b11960 y master con v0.9.0); upstream ggml-org/llama.cpp
    #31689. El muestreo de frames de audio es interno; --temp no lo
    gobierna (tools/tts/README.md).
  - llama-tts --tts-lang es: voz clara (re-ASR exacto; Operador: «clara,
    un poco semi robotizada, buena pronunciación en español», P-9).
  - Conversación casi en tiempo real (fin de turno por silencio, SSE,
    voz por frase): primera voz 2.8–4.4 s, observación exploratoria,
    no línea base (P-13).
Decisión: TTS con llama-tts como subproceso sin shell; texto entregado
por archivo 0600 en directorio privado por petición o stdin (nunca
argv: visible en ps); texto validado contra esquema cerrado (longitud,
sin caracteres de control); una síntesis a la vez y 503 overloaded sin
cola; salida en ruta única por petición, borrada al responder; sin
clonación de voz ni speaker_ref. ASR por 8091 con input_audio. No se
ofrece /v1/realtime nativo mientras #31689 siga abierto.
Alternativas descartadas:
  - /v1/realtime nativo: voz no usable en español (P-8/P-10).
  - Segunda instancia de llama-server sólo para voz: refutada; el
    muestreo no era la causa (P-8).
  - Motor TTS externo (Glosomata ya los tiene): fuera del alcance de
    inferencia de este repo; Glosomata puede consumir LFM3 como un motor
    más.
Consecuencias:
  - Gana: voz española validada por oído humano con el artefacto
    congelado.
  - Pierde: llama-tts recarga el modelo por llamada (latencia de
    segundos); pico de memoria del subproceso sin medir: se mide en
    I1-VS y REQ-5/B-T10 se amplía a él y al swap.
  - Queda obligado: el SPEC de I1-VS verifica que llama-tts acepta el
    prompt por archivo o stdin antes de cerrar; si #31689 se corrige,
    reevaluar realtime con operación registrada (ADR-001).
```
