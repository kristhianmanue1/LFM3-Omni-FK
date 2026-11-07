# ADR-008: Superficie omnimodal local para agentes, robots y humanos (I1-V)

```text
ADR-008: Extensión controlada del bloque local I1-V (dialecto v2-ext,
MCP stdio v2 vía gateway loopback, CLI unificado y perfil D local)
antes de la exposición remota I2
Estado: aceptado (Operador, 2026-11-06: «ronda adversarial para afinar
y procede, tienes aprobados commits, merges, pr push, etc segun
convenga en el avance»)
Contexto:
  - El artefacto congelado (ADR-001) y el gateway loopback I1 (ADR-005/
    ADR-006/ADR-007) ya operan en loopback (127.0.0.1:8091 y 8092).
  - Existen cuatro brechas entre las capacidades del modelo y lo que
    pueden consumir agentes locales, robots/dispositivos y humanos hoy:
    1) ADR-004 restringió el dialecto de schema v2 a objetos planos con
       propiedades escalares sin enum, sin arrays y sin cotas numéricas,
       lo que impide usar salidas estructuradas para clasificación de
       intenciones (enum), detección de listas de objetos en visión/
       video (array) o propuestas acotadas del perfil D (servicio-
       general-v2 §Esquemas y perfiles-servicio-v2 §D).
    2) El servidor MCP local (src/mcp_server.py, v1) habla directo con
       8091 con validación v1 parcial y sólo expone health/infer_text/
       infer_vision; en PLAN LFM3-2, MCP v2 estaba diferido hasta I3
       (remoto con OAuth/Streamable HTTP), dejando a los agentes MCP
       locales sin acceso a transcripción (I1-VA), síntesis de voz
       (I1-VS), video (si cierra I1-VV) ni a las garantías del gateway
       loopback (S-05).
    3) No existe un CLI unificado sobre el gateway loopback (8092) para
       que humanos o scripts de automatización consuman las modalidades
       activas desde terminal sin escribir código.
    4) El perfil D (dispositivos/robots con ventana temporal de validez
       observed_at/expires_at y propuestas acotadas) estaba pospuesto a
       I4 detrás de TLS/OAuth remoto (I2/I3), cuando su validación de
       seguridad más crítica (descarte de observaciones caducadas o
       repetidas y esquema cerrado sin actuadores) es local.
Decisión:
  1. Enmienda acotada de ADR-004 (dialecto de schema v2, Tarea I1-VX):
     mantener el validador propio en Python stdlib 3.12+ (cero
     dependencias externas, fail-closed, sin $ref ni recursión libre),
     ampliando el dialecto cerrado sólo en cuatro puntos verificables:
     - `enum` (lista de 1..32 literales únicos del tipo declarado) en
       propiedades escalares (`string`, `integer`, `number`, `boolean`);
       `bool` jamás satisface `integer` ni `number`;
     - `minimum` y `maximum` numéricos finitos (con minimum <= maximum,
       excluyendo `bool`) en propiedades `integer` y `number`;
     - `array` de profundidad 1 (`items` escalar con tipo/enum/cotas o
       `items` objeto plano de 1..16 propiedades escalares) con
       `minItems`/`maxItems` enteros (0 <= minItems <= maxItems <= 64);
     - objeto anidado de 1 nivel bajo la raíz (raíz = nivel 0 con 1..32
       propiedades; sub-objeto = nivel 1 con 1..16 propiedades
       escalares con tipo/enum/cotas, p. ej. `proposal` en el perfil D
       con `kind` enum y campos escalares de parámetros). Todo `object`
       (raíz, nivel 1 o `items` de array) valida `required` y rechaza
       cualquier clave extra no declarada (`sobran`) en `validar_salida`
       (502 `output_not_valid`). Cualquier objeto en nivel > 1, array
       anidado o keyword fuera del dialecto se rechaza con 400
       `unsupported_schema` antes del motor (contador 0).
     El comportamiento de todos los schemas v2 planos de I0/I1 se
     preserva intacto.
  2. MCP local v2 sobre stdio (Tarea I1-VM): servidor MCP `stdio` que
     reutiliza `gateway_core` para validación previa de argumentos y
     enruta toda ejecución por el gateway HTTP loopback (`127.0.0.1:8092`,
     configurable por `LFM3_GATEWAY_PORT`), nunca directo a `8091` ni
     lanzando `llama-tts` por su cuenta. Así todos los clientes HTTP y
     subprocesos MCP `stdio` comparten el mismo cerrojo de exclusión
     mutua de TTS (ADR-007: 503 sin cola) y los mismos límites (S-05).
     Expone las modalidades activas según `capabilities` (incluyendo
     video sólo si `I1-VV` cerró su gate con `video: true`) y preserva
     `src/mcp_server.py` (`mcp-tools-v1`) intacto.
  3. CLI unificado y adaptador local del perfil D con simulador (Tarea
     I1-VC): entrypoint CLI stdlib contra el gateway 8092 para
     humanos/scripts (texto, visión, audio, voz, schema, y video si
     `capabilities.video` está activo) y adaptador local del perfil D
     que verifica `observed_at`/`expires_at` (margen de reloj <= 2 s)
     tanto antes de enviar como al recibir la respuesta del gateway
     (descartando propuestas que caducaron durante la inferencia),
     deduplica y rechaza reordenamiento por `observation_id`, descarta
     salidas incompletas (`finish_reason != "stop"`) y valida la
     propuesta contra `enum` cerrado sin actuadores físicos. En loopback
     usa `device_id` de simulador local; la identidad revocable por
     credencial de dispositivo permanece en I4 tras I2.
  4. Orden dentro de I1-V: I1-VS (voz TTS) -> I1-VR (conversación SSE)
     -> I1-VV (video corto, condicional a su gate) -> I1-VX (dialecto
     schema v2-ext y percepción multimodal estructurada) -> I1-VM (MCP
     stdio v2 vía gateway 8092) -> I1-VC (CLI unificado y perfil D
     local). Ninguna de estas tareas abre red remota ni relaja
     CERRADA-6 o I2.
Alternativas descartadas:
  - Que MCP v2 stdio llame directo a 8091 o invoque llama-tts en su
    propio proceso: permitiría ejecuciones concurrentes de llama-tts
    entre procesos MCP y HTTP, violando ADR-007 (una síntesis a la vez)
    y REQ-5 (< 4 GiB RSS).
  - Esperar a I2/I3/I4 para dar voz/audio/schema/perfil D a agentes y
    simuladores locales: bloquea el valor local detrás de TLS/OAuth.
  - Instalar jsonschema/pydantic: rompe cero-dependencias (README).
Consecuencias:
  - Gana: agentes MCP locales, CLI, humanos y simuladores de robots
    aprovechan las modalidades activas y salidas JSON con enum/arrays/
    cotas a través de una única frontera loopback (8092) antes de I2.
  - Pierde: tres tareas locales adicionales en I1-V, cada una sujeta a
    SPEC, RED/GREEN y ronda adversarial fresca.
  - Queda obligado: v1 e I0/I1/I1-VA siguen pasando sin regresión;
    capabilities sólo anuncia lo que cerró su gate; prohibido exponer
    estas rutas fuera de 127.0.0.1 sin cerrar I2.
```
