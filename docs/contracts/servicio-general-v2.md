# CONTRATO: lfm3-omni/service v2 — general de consumo

Estado: PROPUESTO, no implementado ni activado. PLAN LFM3-2.
Procedencia: S-01..S-12 de docs/roadmap/objetivo-y-alcance-servicio.md.
Razón: todos los transportes deben compartir admisión, datos y autoridad.
Los contratos v1 conservan su alcance local; este documento no los altera.

## Entrada

Identidad obtenida de autenticación, nunca de un campo libre del cliente:
project_id, principal_id y scopes; device_id si es dispositivo registrado.
Cada llamada tiene request_id generado por servidor. Los clientes pueden
aportar client_request_id ASCII de 1..64 caracteres para correlación,
jamás como credencial ni como identidad de tenant.

Operaciones comunes: capabilities, infer_text, infer_vision, cancel.
I5 añade create_job/get_job/cancel_job; I6 añade sólo modalidades aprobadas.
El catálogo de capabilities sólo anuncia operaciones ya aceptadas.

Perfiles de transporte: docs/contracts/perfiles-servicio-v2.md.
La representación wire concreta la fija cada perfil antes de implementarse.
En todos: rechazar campos desconocidos; no recibir payload opaco de motor.

Límites candidatos, ratificados y publicados antes de cada activación:

| Recurso | Perfil inicial propuesto I1/I2 |
|---|---|
| HTTP body completo | 4 MiB, incluso si llega por chunks |
| prompt | 1..8000 caracteres y máximo 8192 tokens de entrada total |
| messages | 1..32; roles y partes permitidos por perfil |
| salida síncrona | max_tokens entero 1..1024, default 256; bool inválido |
| imágenes | una por llamada; PNG/JPEG decodificado <=2 MiB |
| dimensiones | lados <=2048; píxeles <=4 194 304; una imagen estática |
| schema | <=64 KiB UTF-8, profundidad <=16, <=256 nodos |
| objetos schema | <=64 propiedades por objeto, enum <=32 elementos |
| tools propuestas | <=16, nombre ASCII 1..64, argumentos <=16 KiB |
| concurrencia | global 1 y por proyecto 1 hasta benchmark |
| cola | global 8 pendientes; por proyecto 2 |
| admisión por proyecto | 10 llamadas/minuto, burst máximo 2 |
| espera en cola | <=10 s; después queue_timeout |
| procesamiento | <=120 s desde despacho; total <=130 s |
| metadatos error | mensaje <=512 caracteres; <=8 detalles |

Límites de caracteres, tokens, bytes y tiempo son simultáneos; exceder uno
rechaza, nunca trunca silenciosamente. El presupuesto de tokens incluye
plantilla, mensajes, tools y representación de imagen. Si el adaptador no
puede contabilizar esa modalidad de manera fiable, no anuncia su admisión.
La precisión del conteo debe demostrarse contra el motor fijado.
Rate limit también aplica a solicitudes rechazadas y descubrimiento.
Estos valores son propuesta de arranque, no capacidad observada ni SLA.

## Salida

Envelope lógico no OpenAI: request_id:string, contract_version:"2",
operation:string, state:"succeeded"|"failed"|"cancelled", model_revision:
string, result:objeto por operación, error:objeto o null, usage:objeto.
En éxito error es null; en fallo result es null. usage contiene sólo
contadores medidos (input_tokens/output_tokens), o null si no disponibles.
model_revision es referencia al manifiesto verificado, no texto del modelo.

infer_text: text:string|null, structured:JSON|null, schema_validated:boolean,
finish_reason:"stop"|"length"|"tool_calls", complete:boolean,
tool_calls:lista acotada de {id,name,arguments} o lista vacía.
Sólo finish_reason tool_calls permite text null; arguments es objeto
validado contra el esquema registrado de esa tool. No implica ejecución.
infer_vision: description:string y los mismos indicadores de completitud;
no declarar validación semántica por comprobar la forma de description.
Schema solicitado: validar el esquema entero antes de llamar al motor y el
resultado después. Sin schema, schema_validated es false.
finish_reason length implica complete:false; salida estructurada truncada
no se entrega como resultado exitoso apto para automatización.

capabilities: contract_versions, transport_profiles, operations,
model_revision, limits, modalities, schema_dialect, streaming,
cancellation, enabled_profiles; todo proviene de configuración verificada.
No publicar rutas, secretos, prompts, slots ni detalles administrativos.
La forma wire y cotas de cada colección se cierran en SPEC-SERVICE I0-D.

cancel devuelve result:{target_request_id, cancellation_status,
target_state}. cancellation_status:"accepted"|"pending"|"already_terminal";
target_state usa los estados de solicitud definidos abajo. El envelope
state succeeded sólo acredita que la operación de solicitar/consultar
cancelación respondió; no que el trabajo objetivo esté detenido.
Aceptar cancelación no prueba que el backend haya detenido su cómputo:
el objetivo conserva cancellation_pending hasta confirmación o vencimiento.
Objetivo inexistente o ajeno: not_found, sin revelar su existencia.
Mapeo: objetivo received/queued retirado sin envío -> accepted y target
cancelled; objetivo running -> pending y target cancellation_pending;
objetivo ya cancellation_pending -> pending sin duplicar la señal;
objetivo previamente terminal -> already_terminal y estado conservado.

## Errores

Forma lógica: code, message, retryable, details (lista de field/reason).
Códigos acotados; detalles no copian cuerpos ni excepciones del backend.

| Código | HTTP | Estado y efecto |
|---|---|---|
| invalid_request | 400 | no enviado al motor |
| unauthenticated | 401 | no revela recursos ni existencia de jobs |
| forbidden | 403 | no ejecutado; scope insuficiente |
| not_found | 404 | recurso inexistente o de otro proyecto |
| payload_too_large | 413 | lectura detenida y motor no llamado |
| rate_limited | 429 | no admitido; Retry-After acotado |
| overloaded | 503 | cola llena; no admitido |
| queue_timeout | 504 | retirado de cola, no enviado |
| backend_unavailable | 503 | no éxito; reintento acotado |
| deadline_exceeded | 504 | detener trabajo; resultado tardío descartado |
| invalid_output | 502 | no entregar resultado como válido |
| incomplete_output | 502 | estructura truncada; complete false |
| cancelled | perfil | trabajo cancelado; nunca convertirlo en éxito |
| internal_error | 500 | detalle saneado; request_id para investigación |

HTTP/MCP mapean estos códigos sin perder retryable ni request_id.
Los tiempos que disparan queue_timeout/deadline_exceeded son los del
perfil/version configurados: H/M inicial 10/120 s; J propone 60/600 s.
El código no fija un plazo universal; capabilities publica el del perfil.
Después de iniciar SSE no cambiar el HTTP inicial: emitir evento terminal
de error según perfil y cerrar. Nunca enviar un DONE exitoso tras error.
Reintento no implica idempotencia; nunca reintentar una acción física.

## Invariantes

- Identidad y permiso se comprueban antes de contabilizar inferencia o
  admitir un trabajo; se aplican límites de entrada antes de parseo caro.
- Rechazar URLs http/https/file para imágenes; ninguna descarga arbitraria
  ni acceso a filesystem solicitado por cliente. Egreso del motor acotado.
- Las credenciales externas terminan en el servicio; el backend usa
  identidad interna distinta. No pasar tokens del usuario al motor.
- Ninguna inferencia ejecuta tools, shell, movimientos ni acciones externas.
  tool_calls son propuestas; ejecutor independiente valida y autoriza.
- Validar forma no acredita verdad, suficiencia, confianza ni autorización.
- Estado stateless de aplicación no acredita aislamiento de KV/cache.
  Probar aislamiento A/B; desactivar reutilización entre proyectos si no
  puede demostrarse. No ofrecer aislamiento fuerte sin entorno adecuado.
- Sin conversaciones ni media persistidas por defecto. Logs sólo identidad
  seudonimizada, request_id, versión, estado, duración y contadores medidos.
  Retención candidata: 7 días de logs; acceso administrativo auditado.
- No respuestas/cache compartidos entre proyectos. Cuotas y recursos
  abarcan todos los transportes de una misma identidad.
- El motor sigue interno; sólo rutas declaradas pasan el gateway. TLS,
  identidad y reglas de origen son obligaciones del servicio remoto.
- Bloquear origin inválido cuando exista; ausencia de Origin no autentica
  ni bloquea automáticamente clientes máquina legítimos.
- Los errores y logs nunca revelan claves, datos de otros o rutas locales.
- El perfil de dispositivo usa observación, fecha y caducidad; nunca es un
  canal de control físico seguro ni garantiza plazos de tiempo real.
- Política y límites se versionan; ningún parámetro del cliente aumenta
  privilegios, concurrencia o techo administrativo.

## Esquemas y streaming

Propuesta de dialecto: JSON Schema 2020-12, subconjunto explícito cerrado
con type/properties/required/additionalProperties/items/enum/const y
cotas de longitud, número y cardinalidad que I0-D debe enumerar exactamente.
Rechazar $ref remoto y recursión; validar metadatos y todas las ramas.
Usar validador mantenido fijado, no extender a mano el actual sin evaluación.
Gramática de generación y validación posterior son responsabilidades
separadas; si no se pueden satisfacer ambas, rechazar la petición.

Para estructura, acumular y validar antes de publicar resultado. Streaming
libre entrega texto no validado semánticamente, marcado provisional; sólo
el terminal establece completitud. Datos parciales no habilitan acciones.
El perfil no puede prometer a la vez entrega inmediata y validación del
objeto completo antes de cada byte; declarar cuál ofrece.

## Estados y compatibilidad

Solicitud: received -> rejected | cancelled | queued -> running ->
succeeded | failed |
cancellation_pending -> cancelled | failed. Deadline desde running provoca
cancellation_pending; un terminal no vuelve a running ni cambia a éxito.
Cancelar en queued retira sin envío. Desconectar cliente interactivo H/M
desencadena cancelación; verificar liberación o aislar worker y alertar si
no confirma. Jobs J admitidos duraderamente son independientes de la
conexión: perder POST/202/GET no los cancela. Cancelación de J es explícita.
Retener capacidad ocupada hasta confirmación; no liberar cupo sólo porque
el gateway dejó de esperar. Restart marca in-flight como resultado desconocido
para auditoría y failed para consumo; no repite automáticamente.

Cambios aditivos opcionales compatibles sólo si no cambian semántica ni
límites aceptados. Restringir campos, límites, códigos, modelo garantizado,
transportes o dialecto requiere nueva versión/perfil con migración.
La ruta OpenAI /v1 no representa la versión de este contrato general.
Versiones activas se anuncian; preservar v1 local durante migración.
Un borrador no se anuncia como capacidad activa. Adopción y activación son
decisiones distintas. Emergencia: revocar acceso, no romper contrato en
silencio; notificar estado de retirada y alternativa al consumidor.
