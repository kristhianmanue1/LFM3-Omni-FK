# Perfiles de consumo — lfm3-omni/service v2

Estado: PROPUESTOS. Complementan el contrato general; no lo sustituyen.
Procedencia: S-02/S-05/S-06/S-12; razón: diferentes transportes necesitan
formas wire sin bifurcar identidad, cuotas ni validación.
Las rutas son propuestas; SPEC por iteración las cierra antes del código.

## H — HTTP compatible OpenAI, I1/I2

Entrada: POST /v1/chat/completions, GET /v1/models y GET /capabilities.
Sin passthrough libre al motor: allowlist de campos y subcampos cerrada.
messages/roles/partes/tools/response_format y valores permitidos se
especifican en SPEC-HTTP; modelo aceptado debe coincidir con catálogo.
Compatibilidad significa sólo ese subconjunto, no cualquier payload SDK.
SPEC-HTTP enumera por campo: admitido y aplicado, o rechazado con motivo;
no aceptar-e-ignorar parámetros en silencio. temperature sólo si puede
garantizarse greedy; valores distintos de cero se rechazan en v2. seed y
otros campos no implementados se rechazan explícitamente. Fixtures por
SDK/version/config prueban el payload enviado; no prometer defaults sin
haberlos observado. v1 local mantiene su comportamiento documentado.
Autenticación: Authorization Bearer; nunca clave en URL o cuerpo.
I1 usa credencial de prueba y principal fijo, sólo loopback, no apto para
usuarios externos. I2 sustituye ese modo por identidad revocable y cuotas
por proyecto; el modo de prueba no puede quedar habilitado con red remota.

Salida: conservar estructura OpenAI para el subconjunto probado;
X-Request-ID y X-Service-Contract:2 en cabeceras. /capabilities usa forma
del contrato general. Documentar SDK/versiones probadas y campos ausentes.
No anunciar Responses API, embeddings u otras APIs no implementadas.
Herramientas externas: sólo propuestas tool_calls, sin ejecutarlas.

Errores: HTTP de contrato general, body error:{code,message,type,param},
con request_id, retryable y detalles acotados documentados como extensión.
No inventar usage si el backend no lo informa.

SSE: chunks OpenAI; finish_reason terminal y DONE sólo en éxito completo
según semántica de completitud del perfil. Error terminal: data JSON con
error y request_id; cierre sin DONE. Desconexión sin terminal es resultado
incompleto. No reintentar generación parcial automáticamente.
Desactivar buffering del proxy para streams y probar desconexiones reales.
Structured output: primer perfil sólo stream:false; rechazar combinación
stream:true+schema antes del motor. Texto libre admite SSE en I3.

Invariantes: health público, si existe, mínimo y sin identificadores;
readiness completo y metrics requieren identidad de operación. Origin
allowlist explícita; no CORS abierto con credentials. TLS antes de remoto.
Compatibilidad: mantener clientes locales v1; v2 externo no reinterpreta
los campos ni los límites del v1 histórico. Puertos/domino se fijan en I2.

## M — MCP remoto y local, I3

Entrada: endpoint /mcp mediante Streamable HTTP, versiones y clientes
fijados por ADR-MCP; mantener MCP stdio v1 aparte. No convertir stdin
compartido en sesión global multiusuario ni reutilizar INICIALIZADO global.
Tools candidatas health/infer_text/infer_vision/capabilities; cancelación
por transporte según versión negociada. Esquemas iguales al núcleo.
La operación lógica cancel se mapea al mecanismo nativo de la versión:
notificación por id JSON-RPC en stdio legado o cierre del stream HTTP en
el perfil que lo defina; adaptador relaciona id con request_id e identidad.
No requiere una tool adicional; se conserva el mapeo de estados general.
H dispone además de DELETE /requests/{request_id} para solicitudes propias
identificadas, con el resultado de cancel del contrato general. Requests
ajenos/inexistentes devuelven 404; el registro operativo no guarda prompts.

Salida: CallToolResult con content y, si versión lo permite,
structuredContent conforme a outputSchema. Conservar request_id, error
estable, completitud y modelo efectivo en representación acordada.
Errores de protocolo separados de fallos de tool; isError no se pierde.

Autorización: seguir especificación MCP fijada para transporte HTTP,
incluyendo discovery del recurso, validación de audience y permisos.
No afirmar compatibilidad OAuth por añadir sólo bearer estático.
Usar implementación mantenida evaluada, sin servidor OAuth casero.
Revocar token/proyecto impide nuevas llamadas en todas las tools.

Invariantes: mismas cuotas HTTP/MCP; identidad fuera de argumentos.
Verificar cliente legado y moderno, negociación, cabeceras, origin,
stream cancelado y recuperación. La revisión 2026-07-28 consultada cambia
sesiones/handshake frente a 2025: ADR decide matriz, no asumir equivalencia.
Compatibilidad: nuevo perfil remoto separado de mcp-tools v1; no retirar
stdio ni renombrar sus campos publicados sin migración.

## W — Humanos, web y apps, I4

Entrada: backend de aplicación autentica usuario y llama perfil H.
Browser/móvil nunca reciben clave administrativa o compartida del motor.
Salida: texto escapado/Markdown saneado, fuentes sólo si realmente existen,
truncamiento, error y estado explícitos. Historial opt-in con contrato
propio y retención; no almacenar sólo por habilitar una UI.

Errores: sesión expirada no se reintenta con otra identidad; mostrar
saturación sin bucles; cancelación e incompletitud visibles.
Invariantes: permisos por usuario y proyecto, protección CSRF si cookies,
ningún dato generado insertado como HTML ejecutable. Login/logout y
revocación probados. App nativa: flujo de cliente público adecuado,
no secreto embebido. No se afirma integración móvil hasta probarla.
Si H recibe sólo credencial de proyecto, la atribución al humano corresponde
al backend W: conservar asociación minimizada user_ref-client_request_id-
request_id con acceso/retención propios. H no eleva client_request_id a
identidad ni promete auditar al usuario final. Delegación de usuario exige
token verificable y contrato de identidad adicional antes de anunciarla.

La UI será proyecto separado, frontExpert contrato v2 + Skevi por regla
adoptada. Este repo entrega contrato y cliente de referencia; crear repo o
publicar UI necesita destino y encargo autorizados propios.
Compatibilidad: UI consume capabilities; no deduce modalidad del nombre Omni.

## D — Dispositivos y robots, I4

Entrada propuesta de adaptador sobre H: device_id derivado de credencial,
observation_id:string (1..64), observed_at:UTC, expires_at:UTC,
image o prompt y lista acotada de tipos de propuesta permitidos.
Salida: observation_id, request_id, model_revision, complete,
proposal:{kind,payload} y expires_at. Esquema por tarea autorizado.
No generar confidence como garantía si no existe calibración independiente.

Errores: observación caducada, dispositivo revocado, reloj fuera de margen,
propuesta no permitida o salida incompleta: descartar sin actuar.
Margen temporal candidato 2 s; no habilitar si sincronización no se prueba.

Invariantes: integración inicial sólo simulador, sin actuadores.
Controlador independiente valida estado físico, vigencia y permisos antes
de cualquier acción. La parada local y control de seguridad no dependen
de red/modelo. Una solicitud repetida no debe duplicar acción física;
correlación y deduplicación pertenecen al controlador, no a la inferencia.
El robot puede leer la escena después de enviar: nunca aplicar propuesta
caducada por el simple orden de llegada de respuestas.
Compatibilidad: cambios en acciones o payload exigen perfil versionado.

## J — Trabajos largos, I5

Entrada: POST /jobs con operación admitida y límites I5; Idempotency-Key
ASCII 1..64. GET /jobs/{id}; DELETE /jobs/{id} solicita cancelación.
Scope jobs:create/read/cancel más scope de operación; id aleatorio opaco.
La identidad y clave forman namespace; mismo cuerpo devuelve mismo job,
cuerpo distinto con misma clave produce 409. No promete exactly-once
entre fallos; nunca usar este contrato para ejecutar efectos externos.
Comparar digest de operación+payload normalizado con defaults, sin campos
de correlación/credenciales, canonicalizado por RFC 8785
(https://www.rfc-editor.org/rfc/rfc8785). Rechazar claves
JSON duplicadas y números no finitos. SPEC-JOBS fija librería/version y
fixtures de orden de claves, tipos y defaults; no hash de bytes crudos.

Salida: 202 con job_id/state/status_url; GET sólo para su proyecto;
admisión sólo tras persistir job e idempotencia atómicamente. Si se pierde
202 o conexión después de ese punto, el job continúa; repetir POST con
misma clave/cuerpo recupera el mismo id. Antes del commit durable no existe
admisión: el reintento puede crear un único job. GET desconectado no cancela.
DELETE responde estado de la operación y del job objetivo por separado,
según cancel del contrato general; aceptación no acredita cómputo detenido.
El resultado se entrega en el envelope del contrato general.
Retención propuesta resultado 1 h tras
terminal y tombstone idempotencia 24 h; caducado 410 para dueño, ajeno 404.
Persistencia cifra resultados y controla accesos; registrar borrado.
No crear jobs persistentes si falta almacenamiento/retención aceptados.
Tras vencer tombstone, reutilizar una clave crea un nuevo job_id y puede
repetir inferencia; el cliente debe tratarla como nueva solicitud. No se
ofrece deduplicación más allá de 24 h; ejemplos deben mostrar esa ventana.

Estados: queued -> running -> succeeded/failed/cancellation_pending;
cancellation_pending -> cancelled/failed. Estado expirado después de TTL.
Reinicio: queued recuperable una vez; running pasa failed con outcome
unknown y no se repite automáticamente. Reclamo atómico impide dos workers.
Especificar durabilidad real y recuperación antes de activarlo.
Límites candidatos: 60 s de cola, 600 s procesamiento, salida <=4096 tokens,
cola global 8, un job pendiente por proyecto, máximo global 1 ejecutando.
Presupuesto de cola/inferencia compartido con H/M; definir prioridad justa
para no dejar sin servicio las llamadas interactivas.

## Matriz obligatoria de conformidad

Cada perfil tiene tests de credencial revocada, identidad suplantada,
entrada inválida, límites, cuota, cancelación, backend caído, resultado
truncado y datos A/B. Pruebas cruzadas H/M verifican cuota única.
W/D/J añaden sus casos específicos. Ningún perfil puede anunciarse activo
antes de tener prueba real con un consumidor representativo y rollback.
