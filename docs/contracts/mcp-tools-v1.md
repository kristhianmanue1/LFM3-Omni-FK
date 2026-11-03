# CONTRATO: lfm3-omni/mcp-tools v1

> Frontera del servidor MCP propio hacia agentes consumidores
> (transporte stdio, ADR-002). Comportamiento detallado en SPEC-2
> (docs/specs/SPEC-2-mcp.md); delega en el CONTRATO
> lfm3-omni/superficie-inferencia v1 como consumidor, sin ampliar sus
> límites. Implementación: F3-1 del PLAN LFM3-1.

```text
CONTRATO: lfm3-omni/mcp-tools v1
Transporte: stdio (JSON-RPC por stdin/stdout; sin sockets propios)
Consumidor típico: agente CLI que lanza el binario como hijo

Entrada:
  initialize: handshake MCP estándar [obligatorio como primer método]
  tools/list: sin campos
  tools/call:
    name: "health" | "infer_text" | "infer_vision" [obligatorio]
    arguments.health: ninguno
    arguments.infer_text:
      prompt: string [obligatorio] (1..8000 caracteres)
      schema: objeto JSON Schema [opcional]
      max_tokens: entero [opcional] (1..4096; defecto 512)
    arguments.infer_vision:
      image_base64: string [obligatorio] (PNG o JPEG)
      prompt: string [obligatorio]
Salida:
  initialize → capabilities + lista de tres tools
  tools/list → las tres tools con sus esquemas de arguments
  tools/call health → {estado:"arriba"|"abajo", modelo:string, puerto:8091}
  tools/call infer_text → {contenido:string, validado:boolean,
    usage:objeto}
  tools/call infer_vision → {descripcion:string, usage:objeto}
Errores:
  motor no disponible → isError:true, mensaje explícito — estado:
    sin efecto lateral, reintentable
  arguments fuera de rango o tipo incorrecto → isError:true con el
    campo rechazado — estado: sin efecto lateral
  salida del motor que viola el schema pedido → isError:true
    "salida_invalida" — estado: sin efecto lateral; jamás contenido no
    validado presentado como válido (REQ-7)
Invariantes:
  - Solo stdin/stdout y el motor en 127.0.0.1:8091 (ADR-002, CERRADA-6)
  - Validación en frontera de toda salida del motor cuando la tool
    declara schema (REQ-7)
  - La salida del modelo es dato no confiable; nunca se ejecuta ni se
    reenvía como instrucción (principio 7)
  - Stateless: ninguna conversación se persiste en v1
  - Los identificadores de tools y campos (health, infer_text,
    infer_vision, prompt, schema, max_tokens, image_base64) son parte
    del contrato: renombrarlos exige v2
  - Licencia del modelo heredada del contrato v1 (REQ-8, EV-10)
Compatibilidad:
  - Compatible: añadir tools o campos opcionales de salida
  - Exige v2: renombrar o retirar tools/campos; cambiar transporte;
    ampliar límites del contrato v1
```

## Verificación

Los casos de SPEC-2 (docs/specs/SPEC-2-mcp.md) son los casos de prueba
de este contrato; F3-1 los convierte en tests (RED-GREEN) y su evidencia
vive en el reporte de la tarea.
