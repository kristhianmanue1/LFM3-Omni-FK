# SPEC-2 — Servidor MCP propio (especificación)

> Cubre: REQ-4 del F0 (exponer el motor como herramientas para agentes
> por medio de contratos, API y MCP). Formato: 02 §2.2. Transporte y
> frontera decididos en ADR-002 (stdio; sin red nueva). Delega en el
> CONTRATO lfm3-omni/superficie-inferencia v1; la frontera MCP tiene su
> contrato en docs/contracts/mcp-tools-v1.md.

```text
SPEC-2 [cubre: REQ-4]
Comportamiento: proceso hijo de transporte stdio conforme a MCP; expone
  tres tools que envuelven el motor local: salud del motor, inferencia
  de texto (con esquema de salida opcional) e inferencia de visión.
  Stateless: no persiste conversaciones.
Entradas:
  initialize: handshake MCP estándar — sin campos propios
  tools/list: sin campos
  tools/call:
    name: "health" | "infer_text" | "infer_vision" [obligatorio]
    arguments para infer_text:
      prompt: string [obligatorio] (1..8000 caracteres)
      schema: objeto JSON Schema [opcional] — fuerza salida conforme
      max_tokens: entero [opcional] (1..4096; defecto 512)
    arguments para infer_vision:
      image_base64: string [obligatorio] — PNG o JPEG
      prompt: string [obligatorio]
    arguments para health: ninguno
Salidas:
  health: {estado:"arriba"|"abajo", modelo:string, puerto:8091}
  infer_text: {contenido:string, validado:boolean, usage:objeto}
  infer_vision: {descripcion:string, usage:objeto}
Errores:
  motor no disponible — respuesta MCP con isError:true y mensaje
    explícito; estado: sin efecto lateral, reintentable
  arguments que no cumplen el esquema de la tool — isError:true con
    detalle del campo rechazado; estado: sin efecto lateral
  esquema de salida violado por el motor — isError:true "salida_invalida";
    estado: sin efecto lateral; jamás se devuelve contenido sin validar
    presentado como válido (REQ-7)
Casos:
  - DADO un agente CLI que lanza el binario CUANDO envía initialize
    ENTONCES responde capabilities y la lista de tres tools
  - DADO una sesión MCP abierta CUANDO tools/call health ENTONCES
    estado "arriba" con el modelo del contrato v1
  - DADO tools/call infer_text con schema {nombre:string,edad:integer}
    CUANDO se pide registrar a una persona ENTONCES contenido parsea y
    cumple el esquema y validado es true
  - DADO tools/call infer_text sin schema CUANDO prompt libre ENTONCES
    validado es false y contenido es un string no vacío sin validación
    de esquema ni transformación (salida cruda)
  - DADO tools/call infer_vision con el PNG rojo de procedencia
    registrada ENTONCES descripcion contiene "rojo" o "red"
  - DADO el motor detenido CUANDO tools/call infer_text ENTONCES
    isError:true con mensaje explícito y el proceso MCP sigue vivo
Invariantes:
  - Sin sockets propios: solo stdin/stdout más el motor en
    127.0.0.1:8091 (ADR-002, CERRADA-6)
  - Toda salida de motor pasa validación contra esquema cerrado antes
    de salir por MCP cuando la tool declara schema (REQ-7)
  - La salida del modelo es dato no confiable: nunca se ejecuta ni se
    reenvía como instrucción (principio 7)
  - Stateless: ninguna conversación se persiste en v1
  - El MCP nunca amplía los límites del contrato v1 (host, puerto,
    campos): es consumidor del contrato, no fuente de excepciones
```
