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
Operación (nota no contractual): timeout de lectura/escritura del
  servidor 3600 s (default del build); concurrencia efectiva 4 slots
  (n_slots); caché de prompt activa (prefijos compartidos aceleran el
  prompt eval, observado 200 tok/s con LCP similarity).
  max_tokens: rango recomendado 1..4096 (el build no lo valida; ver
  Entrada).

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
      Nota de superficie (ronda v0.1.0): el build TAMBIÉN acepta urls
      http(s) en image_url.url e intenta descargarlas server-side
      (fetch saliente; 500 si falla). PROHIBIDO para el consumidor:
      rechaza toda url no-data antes de enviar — es superficie SSRF
      contenida solo por CERRADA-6
      Errata 2026-11-04 (aviso de seguridad): el build TAMBIÉN acepta
      partes input_audio, video_url e input_video y pasa esos bytes a
      ffmpeg/ffprobe del sistema (libmtmd, PATH). PROHIBIDO para el
      consumidor de v1: no forman parte de esta frontera ni tienen
      límites declarados. Su habilitación es I1-V en el gateway (ADR-006)
    tools: array [opcional] — {type:"function", function:{name,
      description, parameters: JSON Schema}}
    tool_choice: "auto" [opcional]
    response_format: {type:"json_schema", json_schema:{name, schema}}
      [opcional] — fuerza salida JSON conforme al esquema (B-T3)
    max_tokens: entero [opcional] — techo pedido de generación. El build
      NO valida el rango: 0, -1 y 4097 se aceptan con 2xx (ignorado o
      truncado sin error); el rango recomendado del contrato es 1..4096
      y su verificación es del lado consumidor
    stream: boolean [opcional] — SSE con chunks en formato OpenAI
      (object: "chat.completion.chunk", delta por token); verificado
      2026-11-03 (mejora aditiva compatible)
Salida:
  choices[0].message.content: string — texto de respuesta
  choices[0].finish_reason: "stop" | "length" (truncado por max_tokens)
    — el consumidor DEBE verificarlo para detectar cortes (H6 ronda v0.1.0)
  choices[0].message.tool_calls: array — {id: string, function:{name,
    arguments: string JSON}} cuando el modelo decide llamar una tool (B-T6)
  usage: {prompt_tokens, completion_tokens, total_tokens}
  timings: {prompt_per_second, predicted_per_second} — medición del
    servidor, base del umbral contractual
  (con stream:true: líneas "data: {chunk}" SSE terminadas en
    data: [DONE]; usage por chunk solo con stream_options — fuera de
    esta versión)
Errores:
  400 {error:{code,message,type}} — entrada malformada o campo no
    soportado (p. ej. parte audio_url, B-T8; errata 2026-11-04:
    input_audio sí lo acepta el build, ver nota de superficie); estado: sin
    efecto lateral ("slot queda libre": no ejercitado por batería,
    comportamiento estándar del build)
  503 — motor cargando; estado: reintentable (no ejercitado por
    batería; comportamiento estándar del build; máquina de estados en
    SPEC-1)
  500 — fetch server-side fallido (image_url http inalcanzable);
    estado: sin efecto lateral; el consumidor no debería llegar aquí
    si rechaza urls no-data antes de enviar (ronda v0.1.0)
  404 — ruta o método equivocado (p. ej. GET en chat/completions);
    estado: sin efecto lateral
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
  - Fail-closed ESTRUCTURAL (B-T9): JSON malformado, messages ausente o
    content[] con tipo no soportado → 400 estructurado; jamás 2xx
    ambiguo ahí. NO es fail-closed de campos: el build IGNORA campos
    top-level no reconocidos con 2xx (temperature, seed, typos) — el
    consumidor valida su payload antes de enviar; el greedy sobrevive a
    esos overrides (verificado, ronda v0.1.0)
  - La voz NO forma parte de esta frontera v1 (errata 2026-11-04: el
    build acepta input_audio; B-T8 sólo probaba audio_url inexistente); el endpoint /v1/realtime existe en
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
