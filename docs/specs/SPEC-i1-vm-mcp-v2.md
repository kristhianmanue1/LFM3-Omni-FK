# SPEC-i1-vm — Servidor MCP local v2 (stdio vía gateway 8092)

> Cubre: TAREA I1-VM del PLAN LFM3-2. Formato: 02 §2.2. Transporte y
> frontera decididos en ADR-002 y ADR-008 (stdio; sin red nueva; enrutamiento
> por el gateway loopback 8092 con compartición de cerrojo TTS y límites de
> seguridad). Preserva el contrato mcp-tools-v1 intacto en src/mcp_server.py.
> Contrato formal en docs/contracts/mcp-tools-v2.md. Claves en inglés (ADR-029).

```text
SPEC-i1-vm [cubre: I1-VM, ADR-002, ADR-008]
Comportamiento: proceso hijo de transporte stdio conforme a especificación
  MCP (JSON-RPC 2.0); expone herramientas omnimodales para agentes e IDEs:
  salud unificada, inferencia de texto (con dialecto schema v2-ext),
  visión sobre imagen (PNG/JPEG), audio/ASR (WAV), síntesis de voz
  (TTS en español vía gateway 8092 con cerrojo mutex 503) y video corto MP4
  (si la capacidad video está activa en capabilities).
  Reutiliza gateway_core para prevalidación y delega en el gateway HTTP
  loopback (127.0.0.1:8092). Stateless: no persiste conversaciones.

Entradas:
  initialize: handshake MCP estándar — obligatorio primer método;
    negociación de versión contra las soportadas (2025-06-18, 2025-03-26)
  tools/list: sin campos
  tools/call:
    name: "health" | "infer_text" | "infer_vision" | "infer_audio" |
          "synthesize_speech" | "infer_video" [obligatorio]
    arguments para health: ninguno ({} o ausente)
    arguments para infer_text:
      prompt: string [obligatorio] (1..8000 caracteres)
      schema: objeto JSON Schema [opcional; dialecto v2-ext soportado]
      max_tokens: entero [opcional] (1..4096; defecto 512)
    arguments para infer_vision:
      image_base64: string [obligatorio] — PNG o JPEG en base64
      prompt: string [obligatorio] (1..8000 caracteres)
      schema: objeto JSON Schema [opcional; dialecto v2-ext]
      max_tokens: entero [opcional] (1..4096; defecto 1024)
    arguments para infer_audio:
      audio_base64: string [obligatorio] — WAV en base64
      prompt: string [obligatorio] (1..8000 caracteres)
      schema: objeto JSON Schema [opcional; dialecto v2-ext]
      max_tokens: entero [opcional] (1..4096; defecto 1024)
    arguments para synthesize_speech:
      input: string [obligatorio] (1..600 caracteres)
      response_format: string [opcional] ("wav")
      [voz fija desde issue #2 (decisión del Operador, 2026-11-07):
       sin voice ni speed; los campos no declarados se rechazan en la
       frontera MCP antes del gateway, la respuesta no atribuye voz ni
       velocidad y format:"wav" describe el formato aplicado. Ver
       docs/contracts/mcp-tools-v2.md, sección «Voz fija y migración»]
    arguments para infer_video: [activo sólo si video: true en gateway]
      video_base64: string [obligatorio] — MP4 en base64 (<= 16 MiB)
      prompt: string [obligatorio] (1..8000 caracteres)
      schema: objeto JSON Schema [opcional; dialecto v2-ext]
      max_tokens: entero [opcional] (1..4096; defecto 1024)
    campos no declarados: rechazados con detalle del campo extra

Salidas:
  health: {state:"up"|"down", model:string, gateway_port:8092,
           backend_port:8091, capabilities:objeto}
  infer_text: {text:string, validated:boolean, usage:objeto}
  infer_vision: {description:string, validated:boolean, usage:objeto}
  infer_audio: {text:string, validated:boolean, usage:objeto}
  synthesize_speech: {audio_base64:string, format:"wav",
                      chars:int, duration_est_s:float}
  infer_video: {description:string, validated:boolean, usage:objeto}

Errores:
  gateway no disponible -> isError:true con mensaje explícito; reintentable
  cerrojo TTS ocupado en gateway (503) -> isError:true mensaje "tts_busy"
  arguments inválidos -> isError:true con mensaje claro; sin efecto lateral
  salida del modelo que viola schema o forma inválida -> isError:true
    "salida_invalida"; dato no confiable nunca se entrega como válido
  tool no conocida -> error JSON-RPC -32602
  método antes de initialize -> error JSON-RPC -32002

Casos:
  - DADO un agente MCP CUANDO envía initialize ENTONCES responde
    capabilities y lista de herramientas v2 omnimodales.
  - DADO una sesión MCP v2 CUANDO llama health ENTONCES responde state "up",
    puertos 8092/8091 y capacidades activas del gateway.
  - DADO infer_text con schema dialecto v2-ext (enum, min/max, array)
    CUANDO se invoca ENTONCES texto cumple el esquema y validated es true.
  - DADO infer_audio con audio WAV base64 ENTONCES devuelve texto
    transcrito/analizado con validated y usage.
  - DADO synthesize_speech con texto en español CUANDO gateway está libre
    ENTONCES devuelve audio_base64 en formato WAV con cabecera RIFF.
  - DADO synthesize_speech mientras el cerrojo TTS está retenido ENTONCES
    devuelve isError:true con 503/tts_busy reintentable.
  - DADO infer_video con MP4 sintético CUANDO video activo ENTONCES
    devuelve description válida y usage.
  - DADO el servidor MCP v1 (src/mcp_server.py) CUANDO se ejecutan sus
    pruebas ENTONCES todas pasan sin regresión (mcp-tools-v1 intacto).

Invariantes:
  - Transporte stdio puro; sin apertura de sockets propios adicionales.
  - Toda llamada de inferencia y síntesis pasa por el gateway 8092.
  - Compartición estricta de exclusión mutua de TTS con clientes HTTP.
  - Toda salida del modelo validada fail-closed contra esquema cerrado.
```
