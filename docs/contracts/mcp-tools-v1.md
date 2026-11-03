# CONTRATO: lfm3-omni/mcp-tools v1

> Frontera del servidor MCP propio hacia agentes consumidores
> (transporte stdio, ADR-002). Comportamiento detallado en SPEC-2
> (docs/specs/SPEC-2-mcp.md); delega en el CONTRATO
> lfm3-omni/superficie-inferencia v1 como consumidor, sin ampliar sus
> límites. Implementado en F3-1 del PLAN LFM3-1.
> Identificadores y claves en inglés (elección persistente de idiomas,
> ADR-029; sin excepciones).

```text
CONTRATO: lfm3-omni/mcp-tools v1
Transporte: stdio (JSON-RPC por stdin/stdout; sin sockets propios)
Consumidor típico: agente CLI que lanza el binario como hijo

Entrada:
  initialize: handshake MCP estándar [obligatorio como primer método;
    versión negociada contra las soportadas por el servidor]
  tools/list: sin campos [requiere initialize previo]
  tools/call [requiere initialize previo]:
    name: "health" | "infer_text" | "infer_vision" [obligatorio]
    arguments.health: ninguno ({} o ausente; cualquier campo se rechaza)
    arguments.infer_text:
      prompt: string [obligatorio] (1..8000 caracteres)
      schema: objeto JSON Schema [opcional; null explícito se rechaza;
        subconjunto soportado: type/properties/required/items — claves
        fuera del subconjunto se rechazan fail-closed]
      max_tokens: entero [opcional] (1..4096; defecto 512)
    arguments.infer_vision:
      image_base64: string [obligatorio] — PNG o JPEG, verificado por
        firma de bytes en la frontera (no por el MIME declarado)
      prompt: string [obligatorio] (1..8000 caracteres)
    campos no declarados en arguments: se rechazan nombrando el campo
      (superficie cerrada)
Salida:
  initialize → {protocolVersion, capabilities:{tools}, serverInfo}
  tools/list → {tools:[health, infer_text, infer_vision + inputSchema]}
  tools/call health → {state:"up"|"down", model:string, port:8091}
  tools/call infer_text → {text:string, validated:boolean, usage:objeto}
  tools/call infer_vision → {description:string, usage:objeto}
Errores:
  motor no disponible → isError:true, mensaje explícito — estado: sin
    efecto lateral, reintentable
  motor rechazó la entrada (HTTP 400) → isError:true con el detalle del
    motor — estado: sin efecto lateral; NO es reintentable tal cual
  motor cargando (HTTP 503) → isError:true, reintentable
  arguments fuera de rango, tipo incorrecto, campo no declarado o
    imagen sin firma PNG/JPEG → isError:true con el campo rechazado —
    estado: sin efecto lateral
  salida del motor que viola el schema pedido o carece de forma válida
    (choices/content/usage) → isError:true "salida_invalida" — estado:
    sin efecto lateral; jamás contenido no validado presentado como
    válido (REQ-7)
  tool no conocida → error JSON-RPC -32602
  métodos previos a initialize (excepto initialize) → error JSON-RPC
    -32002
  JSON no parseable → error JSON-RPC -32700
  notificación JSON-RPC (sin id) → sin respuesta
Invariantes:
  - Solo stdin/stdout y el motor en 127.0.0.1:8091 (ADR-002, CERRADA-6)
  - Validación en frontera de toda salida del motor: forma cerrada
    (choices/content string/usage objeto) y conformidad al schema
    pedido con el subconjunto declarado arriba (REQ-7)
  - La salida del modelo es dato no confiable: nunca se ejecuta ni se
    reenvía como instrucción (principio 7)
  - Stateless: ninguna conversación se persiste en v1
  - El MCP nunca amplía los límites del contrato v1 (host, puerto,
    campos): es consumidor del contrato, no fuente de excepciones
  - Los identificadores y claves (health, infer_text, infer_vision,
    prompt, schema, max_tokens, image_base64, state, model, port, text,
    validated, description, usage) son parte del contrato: renombrarlos
    exige v2
  - Las descripciones de infer_vision se generan con un techo interno
    de 1024 tokens: descripciones largas pueden quedar cortadas
  - El modelo reportado por health se contrasta contra /v1/models del
    motor; divergencia se reporta como state "down" (principio 3)
  - Licencia del modelo heredada del contrato v1 (REQ-8, EV-10)
Compatibilidad:
  - Compatible: añadir tools o campos opcionales de salida
  - Exige v2: renombrar o retirar tools/campos; cambiar transporte;
    ampliar límites del contrato v1; ampliar el subconjunto de schema
```

## Verificación

Los casos de SPEC-2 (docs/specs/SPEC-2-mcp.md) y la tabla de casos
borde de la ronda adversarial F3 (docs/reviews/2026-11-f3-adversarial.md)
son los casos de prueba de este contrato; tests/test_mcp_server.py los
implementa (RED-GREEN, 26 tests).
