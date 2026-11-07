# CONTRATO: lfm3-omni/mcp-tools v2

> Frontera del servidor MCP propio v2 hacia agentes consumidores locales
> (transporte stdio, ADR-002, ADR-008). Comportamiento detallado en SPEC-i1-vm
> (docs/specs/SPEC-i1-vm-mcp-v2.md); delega en el gateway HTTP loopback
> (127.0.0.1:8092) y reutiliza `gateway_core` para validación previa en
> frontera. Comparte con los clientes HTTP el mismo cerrojo de exclusión mutua
> de TTS (ADR-007, 503 sin cola) y los mismos límites de seguridad (S-05).
> Preserva intacto el contrato v1 (docs/contracts/mcp-tools-v1.md) y su
> ejecutable `src/mcp_server.py`.
> Identificadores y claves en inglés (ADR-029).

```text
CONTRATO: lfm3-omni/mcp-tools v2
Transporte: stdio (JSON-RPC 2.0 por stdin/stdout; sin sockets nuevos)
Consumidor típico: agentes CLI, IDEs y runtimes MCP locales como subproceso
Delegación: Gateway HTTP loopback (127.0.0.1:8092, configurable por entorno)

Entrada:
  initialize: handshake MCP estándar [obligatorio como primer método;
    versión negociada contra las soportadas: 2025-06-18, 2025-03-26]
  tools/list: sin campos [requiere initialize previo]
  tools/call [requiere initialize previo]:
    name: "health" | "infer_text" | "infer_vision" | "infer_audio" |
          "synthesize_speech" | "infer_video"
    arguments.health: ninguno ({} o ausente; campos extra se rechazan)
    arguments.infer_text:
      prompt: string [obligatorio] (1..8000 caracteres)
      schema: objeto JSON Schema [opcional; dialecto v2-ext: enum escalar,
        min/max, array, sub-objeto nivel 1; rechaza $ref y claves extra]
      max_tokens: entero [opcional] (1..4096; defecto 512)
    arguments.infer_vision:
      image_base64: string [obligatorio] — PNG o JPEG en base64 verificado
        por firma de bytes en frontera (gateway_core)
      prompt: string [obligatorio] (1..8000 caracteres)
      schema: objeto JSON Schema [opcional; dialecto v2-ext]
      max_tokens: entero [opcional] (1..4096; defecto 1024)
    arguments.infer_audio:
      audio_base64: string [obligatorio] — WAV en base64 verificado
        por firma mágica RIFF/WAVE y límites de tamaño (4 MiB)
      prompt: string [obligatorio] (1..8000 caracteres)
      schema: objeto JSON Schema [opcional; dialecto v2-ext]
      max_tokens: entero [opcional] (1..4096; defecto 1024)
    arguments.synthesize_speech:
      input: string [obligatorio] (1..600 caracteres, sin control)
      voice: string [opcional] (defecto "es_ES-davefx-medium")
      speed: number [opcional] (0.5..2.0; defecto 1.0)
      response_format: string [opcional] ("wav"; defecto "wav")
    arguments.infer_video: [anunciado sólo si gateway tiene video: true]
      video_base64: string [obligatorio] — MP4 verificado por caja ftyp y
        ffprobe (<= 16 MiB, <= 10 s, <= 30 fps, <= 120 frames, <= 1080p)
      prompt: string [obligatorio] (1..8000 caracteres)
      schema: objeto JSON Schema [opcional; dialecto v2-ext]
      max_tokens: entero [opcional] (1..4096; defecto 1024)
    campos no declarados en arguments: se rechazan nombrando el campo

Salida:
  initialize -> {protocolVersion, capabilities:{tools}, serverInfo}
  tools/list -> {tools:[health, infer_text, infer_vision, infer_audio,
                        synthesize_speech, infer_video (si activo)]}
  tools/call -> sobre CallToolResult estándar de MCP: el resultado viaja
    como string JSON dentro de content[0].text, con isError:boolean al
    nivel del result. El JSON interno por tool:
    health -> {state:"up"|"down", model:string, gateway_port:8092,
               backend_port:8091, capabilities:objeto}
    infer_text -> {text:string, validated:boolean, usage:objeto}
    infer_vision -> {description:string, validated:boolean, usage:objeto}
    infer_audio -> {text:string, validated:boolean, usage:objeto}
    synthesize_speech -> {audio_base64:string, format:"wav", voice:string,
                          chars:int, duration_est_s:float}
    infer_video -> {description:string, validated:boolean, usage:objeto}

Errores:
  gateway o motor no disponible -> isError:true con mensaje explícito;
    estado: sin efecto lateral, reintentable
  cerrojo TTS ocupado (HTTP 503) -> isError:true con mensaje "tts_busy";
    reintentable
  arguments fuera de rango, tipo incorrecto, campo no declarado o
    medios sin firma válida -> isError:true nombrando el campo rechazado;
    sin efecto lateral
  salida del modelo que viola el schema pedido o carece de forma válida ->
    isError:true "salida_invalida"; jamás salida no validada devuelta como
    válida (REQ-7, 06 §5)
  tool no conocida -> error JSON-RPC -32602
  métodos previos a initialize (excepto initialize) -> error JSON-RPC -32002
  JSON no parseable -> error JSON-RPC -32700
  notificación JSON-RPC (sin id) -> sin respuesta
```
