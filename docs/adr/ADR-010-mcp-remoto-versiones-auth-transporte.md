# ADR-010: Arquitectura de servidor MCP remoto desacoplado, transporte Streamable HTTP, autenticación por scopes y aprovechamiento omnimodal integral

```text
ADR-010: Servidor MCP remoto desacoplado sobre HTTPS (puerto 8443), transporte
Streamable HTTP (POST/SSE), autenticación Bearer por scopes de proyecto y catálogo
omnimodal integral (texto, visión, audio, voz, video y conversación por turnos).
Estado: propuesto (formalizado en TAREA I3-D, PLAN LFM3-2; autorizado 2026-11-07)
Contexto:
  - Las fases I0, I1, I1-V e I2 completaron la superficie local de inferencia y
    el servicio web privado multi-inquilino en loopback/HTTPS (puerto 8443).
  - El servidor MCP v2 actual (src/mcp_server_v2.py) opera mediante stdio
    (stdin/stdout) como subproceso local exclusivo para un único agente o CLI.
  - La Fase I3 tiene como objetivo desacoplar el servidor MCP para permitir que
    agentes externos e independientes consuman el servicio a través de la red
    privada segura, sin necesidad de ejecutar subprocesos locales ni acceder
    directamente al host.
  - Directiva explícita del Operador (2026-11-07): el servidor MCP remoto no debe
    limitarse a texto plano; debe aprovechar y exponer de forma integral todas
    las capacidades omnimodales demostradas del modelo:
    1) Texto libre y estructurado (dialecto schema v2-ext).
    2) Reconocimiento de imágenes y análisis visual (JPEG/PNG).
    3) Procesamiento y transcripción de audio (WAV PCM 16kHz).
    4) Síntesis de voz hablada en español (llama-tts).
    5) Percepción temporal de video corto (MP4 con inspección ffprobe).
    6) Conversación fluida por turnos con streaming (SSE por frase/token).
  - Desafíos arquitectónicos críticos:
    1) Desacoplamiento de sesiones: prohibición de un estado global mutable
       (evitar variables globales compartidas de sesión que mezclen proyectos).
    2) Transporte normativo: adoptar Streamable HTTP (MCP specification) con
       mensajería JSON-RPC 2.0 por POST y Server-Sent Events (SSE) para streaming.
    3) Autenticación y granularidad de acceso: integrar la autenticación Bearer
       de I2 (config/tokens.json) con validación estricta de scopes por tool.
    4) Concurrencia y contención de recursos: proteger el motor (8091) contra
       saturación y respetar la exclusión mutua de TTS (503 tts_busy sin cola).
    5) Cancelación limpia: permitir la cancelación inmediata de inferencias
       en vuelo al recibir notificaciones o al desconectarse el cliente.
Decisión:
  1. Endpoint y Transporte Streamable HTTP:
     - El servicio expone el endpoint `/mcp` sobre el terminador TLS seguro
       (puerto 8443) gestionado por `gateway_http.py` y `gateway_tls.py`.
     - El transporte implementa la especificación Streamable HTTP de MCP:
       * Peticiones de métodos (initialize, tools/list, tools/call) mediante
         `POST /mcp` con `Content-Type: application/json`.
       * Canal de eventos y streaming opcional mediante `GET /mcp` con
         `Accept: text/event-stream` (SSE).
       * Soporte de cabecera `Mcp-Session-Id` (UUID v4) para vincular peticiones
         y streams a una sesión desacoplada sin persistencia global compartida.
     - Se mantiene compatibilidad estricta con las versiones de protocolo MCP
       `2024-11-05`, `2025-03-26` y `2025-06-18`.
  2. Catálogo omnimodal completo en tools/list:
     El servidor remoto publica el catálogo unificado de capacidades del modelo:
     - `health`: estado del servicio y verificación de conectividad.
     - `capabilities`: modalidades activas y límites de entrada.
     - `infer_text`: completado de texto y estructuración con schema v2-ext.
     - `infer_vision`: análisis de imágenes en base64 con schema opcional.
     - `infer_audio`: análisis y transcripción de audio WAV en base64.
     - `synthesize_speech`: síntesis de voz en español devolviendo WAV base64.
     - `infer_video`: inspección y razonamiento temporal sobre clips MP4.
     - `conversational_turn`: turno conversacional con soporte de streaming
       incremental de texto y fragmentos de voz sintetizada.
  3. Autenticación, scopes y aislamiento multi-proyecto:
     - Toda petición al endpoint `/mcp` exige obligatoriamente las cabeceras:
       `Authorization: Bearer <token>` y `X-Project-ID: <project_id>`.
     - Se reutiliza el registro seguro `config/tokens.json` con permisos 0600.
     - Se aplica la matriz determinista de scopes:
       * `health`, `capabilities`: cualquier token válido no revocado.
       * `infer_text`: scope `infer:text` o `mcp:tools`.
       * `infer_vision`: scope `infer:vision` o `mcp:tools`.
       * `infer_audio`: scope `infer:audio` o `mcp:tools`.
       * `synthesize_speech`: scope `speech:synthesize` o `mcp:tools`.
       * `infer_video`: scope `infer:video` o `mcp:tools`.
       * `conversational_turn`: scopes `infer:text` + `turn:stream` o `mcp:tools`.
     - Si el proyecto no cuenta con el scope requerido, la herramienta responde
       `isError: true` con mensaje `insufficient_scope`.
  4. Contención de egreso, validación en frontera y exclusión de TTS:
     - Política estricta de no-egreso (anti-SSRF): todos los medios binarios
       deben entregarse como cadenas base64 verificadas por firma mágica.
       Se rechazan taxativamente URLs externas o referencias locales a ficheros.
     - La salida del modelo es dato no confiable: toda respuesta condicionada
       a schema es validada por el dialecto v2-ext en `gateway_core.py`.
     - Exclusión mutua de TTS: si `synthesize_speech` o un turno conversacional
       con audio encuentra el sintetizador ocupado, responde inmediatamente
       `isError: true` con código `tts_busy` (sin cola ni bloqueo de memoria).
  5. Cancelación de peticiones:
     - Notificación JSON-RPC `notifications/cancelled` recibida en `/mcp`
       desencadena la cancelación inmediata de la inferencia en `llama-server`.
     - El cierre abrupto de la conexión HTTP/SSE cliente cancela la tarea
       asociada en el gateway y libera los cupos de concurrencia.
Consecuencias:
  - Positivas:
    * Los agentes del ecosistema pueden interactuar con el modelo omnimodal
      a través del estándar industrial MCP sin requerir acceso de shell local.
    * Aprovechamiento integral de texto, visión, audio, voz, video y conversación.
    * Aislamiento determinista entre proyectos con cuotas y revocación inmediata.
    * Se preserva intacto el contrato local v1 y el servidor stdio v2.
  - Negativas / Limitaciones:
    * Clientes MCP antiguos que solo admitan stdio requerirán un adaptador
      o proxy de transporte (mcp-proxy).
    * Mayor complejidad en la gestión del ciclo de vida de streams SSE y sesiones.
  - Mitigaciones:
    * El servidor valida cabeceras y métodos devolviendo errores JSON-RPC
      estándar y códigos HTTP normativos.
    * Se proporciona un cliente de referencia en Python para pruebas de integración.
```
