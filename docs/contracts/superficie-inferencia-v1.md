# CONTRATO: lfm3-omni/superficie-inferencia v1

> Frontera pública del motor servido por llama-server. Fuente de
> capacidades: docs/verificaciones-motor.md (B-T1..B-T12, medido
> 2026-11-02). Restricciones de F0: CERRADA-6 (localhost), REQ-8
> (licencia lfm1.0, EV-10). Motor fijado por ADR-001.

```text
CONTRATO: lfm3-omni/superficie-inferencia v1
Base URL: http://127.0.0.1:8091 (solo localhost; CERRADA-6)
Motor: llama-server 0.8.0 (build 11960) + LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M
  (ADR-001; cambiar motor o modelo es incompatible y exige v2)
CORS: el build vigente refleja cualquier Origin con credentials
  (aviso registrado del log de arranque); aceptable sólo mientras el
  vínculo sea localhost (CERRADA-6). Cualquier cambio de vínculo exige
  api-key + --cors-origins explícitos antes de arrancar.
Límites: contexto 128000 tokens por slot × 4 slots (n_ctx_slot del log
  de carga); max_tokens aceptado 1..4096; prompt de batería observado
  en 28-30 tokens (no hay techo declarado de prompt menor al contexto).

Entrada:
  GET /health
    — sin campos. Verificación de vida.
  GET /v1/models
    — sin campos. Descubrimiento del modelo servido.
  POST /v1/chat/completions
    messages: array [obligatorio] — roles system|user|assistant;
      content como string o partes:
      {type:"text", text} | {type:"image_url", image_url:{url:"data:image/png;base64,..." | data:image/jpeg;base64,...}}
      (JPEG declarado, no ejercitado por batería: B-T7 midió PNG)
    tools: array [opcional] — {type:"function", function:{name,
      description, parameters: JSON Schema}}
    tool_choice: "auto" [opcional]
    response_format: {type:"json_schema", json_schema:{name, schema}}
      [opcional] — fuerza salida JSON conforme al esquema (B-T3)
    max_tokens: entero [opcional] (1..4096; no ejercitado por batería,
      comportamiento estándar del build)
Salida:
  choices[0].message.content: string — texto de respuesta
  choices[0].message.tool_calls: array — {function:{name, arguments:
    string JSON}} cuando el modelo decide llamar una tool (B-T6)
  usage: {prompt_tokens, completion_tokens, total_tokens}
  timings: {prompt_per_second, predicted_per_second} — medición del
    servidor, base del umbral contractual
Errores:
  400 {error:{code,message,type}} — entrada malformada o campo no
    soportado (p. ej. audio en chat en este build, B-T8); estado: sin
    efecto lateral ("slot queda libre": no ejercitado por batería,
    comportamiento estándar del build)
  503 — motor cargando; estado: reintentable (no ejercitado por
    batería; comportamiento estándar del build; máquina de estados en
    SPEC-1)
Invariantes:
  - Escucha únicamente en 127.0.0.1:8091 — fuente: CERRADA-6 + runbook
    de ADR-001; verificación binaria B-T12
  - Modelo servido exactamente LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M (B-T2)
  - Muestreo greedy (--temp 0) y --reasoning off; determinismo 3/3
    observado en corridas contiguas, sin prometerlo entre reinicios
    del proceso (B-T4)
  - Toda salida que un consumidor persista o reenvíe pasa antes por
    validación contra esquema cerrado — response_format en la llamada
    o validador del consumidor (REQ-7) (B-T3)
  - Rendimiento contractual: mediana de n=3 corridas de 64 tokens
    >= 15 tok/s en predicted_per_second; observado 55.9 (B-T5)
  - Fail-closed: lo no declarado en este contrato se rechaza con 400
    estructurado; jamás 2xx ambiguo (B-T9)
  - La voz NO forma parte de esta frontera v1: audio de entrada por
    chat se rechaza con 400 (B-T8); el endpoint /v1/realtime existe en
    el build pero no está verificado ni declarado aquí — de incorporarse,
    exigirá v2. Su verificación de capacidad es tarea aparte (F3-3)
  - Recursos: RSS residente con el modelo cargado < 4 GB (REQ-5, B-T10)
  - Licencia del modelo: LFM Open License v1.0 — consumo interno del
    ecosistema dentro de licencia; todo esquema de cobro a terceros se
    documenta y se mantiene bajo el umbral de la licencia (REQ-8, EV-10,
    B-T11)
Compatibilidad:
  - Compatible hacia atrás: añadir campos opcionales de entrada;
    ampliar salidas con campos nuevos; corregir mensajes de error sin
    cambiar códigos.
  - Exige v2: cambiar host o puerto declarados; restringir entradas hoy
    aceptadas; cambiar códigos de error; cambiar motor o modelo (ADR-001);
    incorporar la voz a la frontera declarada.
```

## Casos de verificación contractual

Los casos B-T1..B-T12 de docs/verificaciones-motor.md son los casos de
prueba de este contrato (SPEC-1 los traza 1:1). Un fallo de cualquiera
de ellos con el motor vigente es regresión contractual, no incidencia
del consumidor.
