# SPEC-2 — Servidor MCP propio (especificación)

> Cubre: REQ-4 del F0 (exponer el motor como herramientas para agentes
> por medio de contratos, API y MCP). Formato: 02 §2.2. Transporte y
> frontera decididos en ADR-002 (stdio; sin red nueva). Delega en el
> CONTRATO lfm3-omni/superficie-inferencia v1; la frontera MCP tiene su
> contrato en docs/contracts/mcp-tools-v1.md. Claves en inglés (ADR-029).

```text
SPEC-2 [cubre: REQ-4]
Comportamiento: proceso hijo de transporte stdio conforme a MCP; expone
  tres tools que envuelven el motor local: salud del motor, inferencia
  de texto (con esquema de salida opcional) e inferencia de visión.
  Stateless: no persiste conversaciones.
Entradas:
  initialize: handshake MCP estándar — primer método obligatorio;
    negociación de versión contra las soportadas
  tools/list: sin campos
  tools/call:
    name: "health" | "infer_text" | "infer_vision" [obligatorio]
    arguments para infer_text:
      prompt: string [obligatorio] (1..8000 caracteres)
      schema: objeto JSON Schema [opcional; null se rechaza; subconjunto
        soportado: type/properties/required/items]
      max_tokens: entero [opcional] (1..4096; defecto 512)
    arguments para infer_vision:
      image_base64: string [obligatorio] — PNG o JPEG por firma de bytes
      prompt: string [obligatorio] (1..8000 caracteres)
    arguments para health: ninguno
    campos no declarados: rechazados nombrando el campo
Salidas:
  health: {state:"up"|"down", model:string, port:8091}
  infer_text: {text:string, validated:boolean, usage:objeto}
  infer_vision: {description:string, usage:objeto}
Errores:
  motor no disponible — isError:true, mensaje explícito; estado: sin
    efecto lateral, reintentable
  motor rechaza la entrada (400) o está cargando (503) — isError:true
    con detalle y clasificación; estado: sin efecto lateral
  arguments que no cumplen el esquema de la tool — isError:true con
    detalle del campo rechazado; estado: sin efecto lateral
  esquema de salida violado por el motor, o respuesta sin forma válida
    (choices/content/usage) — isError:true "salida_invalida"; estado:
    sin efecto lateral; jamás se devuelve contenido sin validar
    presentado como válido (REQ-7)
  tool desconocida — error JSON-RPC -32602
  método antes de initialize — error JSON-RPC -32002
Casos:
  - DADO un agente CLI que lanza el binario CUANDO envía initialize
    ENTONCES responde capabilities y la lista de tres tools
  - DADO una sesión MCP abierta CUANDO tools/call health ENTONCES
    state "up" con el modelo del contrato v1 contrastado contra
    /v1/models del motor
  - DADO tools/call infer_text con schema {nombre:string,edad:integer}
    CUANDO se pide registrar a una persona ENTONCES text parsea y
    cumple el esquema y validated es true
  - DADO tools/call infer_text sin schema CUANDO prompt libre ENTONCES
    validated es false y text es un string no vacío sin validación de
    esquema ni transformación (salida cruda)
  - DADO tools/call infer_vision con el PNG rojo de procedencia
    registrada ENTONCES description contiene "rojo" o "red"
  - DADO tools/call infer_text con salida JSON válida que viola el
    schema ENTONCES isError:true "salida_invalida" (regresión del
    BLOCKER de la ronda F3)
  - DADO el motor detenido CUANDO tools/call infer_text ENTONCES
    isError:true con mensaje explícito y el proceso MCP sigue vivo
Invariantes:
  - Sin sockets propios: solo stdin/stdout más el motor en
    127.0.0.1:8091 (ADR-002, CERRADA-6)
  - Toda salida de motor pasa validación de forma cerrada y, si hay
    schema, conformidad por subconjunto antes de salir por MCP (REQ-7)
  - La salida del modelo es dato no confiable: nunca se ejecuta ni se
    reenvía como instrucción (principio 7)
  - Stateless: ninguna conversación se persiste en v1
  - El MCP nunca amplía los límites del contrato v1 (host, puerto,
    campos): es consumidor del contrato, no fuente de excepciones
  - Notificaciones JSON-RPC (sin id) no reciben respuesta; un surrogate
    Unicode malicioso no mata el bucle principal
```
