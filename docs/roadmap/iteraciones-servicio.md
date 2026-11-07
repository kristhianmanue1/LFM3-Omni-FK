# Aceptación y ejecución incremental — PLAN LFM3-2

Estado: PROPUESTO. Complemento del plan; no activa ninguna iteración.
Procedencia: S-01..S-12, contratos general/perfiles, guías 04/06.
Razón: una lista de tareas no basta para demostrar utilidad incremental.

## Método común de ejecución

1. Leer AGENTS/AN-KLA, verificar Git/memoria y autoridad de la tarea.
2. Tomar la siguiente tarea del plan cuyo gate anterior esté cerrado.
3. Antes de código: SPEC con entradas/salidas/errores, tests, comandos
   exactos y contratos sin PARCIAL; ADR si nueva frontera/dependencia.
4. Contrato de tarea acota lecturas, escrituras, red, herramientas y coste.
   Dependencias se instalan sólo con autoridad específica; fijar lock.
5. RED de propiedades discriminantes, corrección mínima, GREEN y suite.
6. Demo real desde consumidor; informe usa revisión de código/config/datos
   medidos, no sólo texto de documentación o exit code del cliente.
7. Revisor con contexto nuevo lee artefactos y diff; no recibe el relato
   del autor como sustituto de evidencia. Corregir HIGH/BLOCKER, justificar
   MED por decisión correspondiente, repetir checks afectados.
8. Cinco gates AGENTS, reporte dos capas en docs/reviews y handoff.
9. Sin permiso de activar: dejar artefacto listo y sistema previo operativo.

Comandos hoy existentes: check_sizes.py, check_plans.py, check_reports.py,
check_templates.py para docs/MANIFEST.json y scripts/MANIFEST.json.
Suite de motor existente: python3 -m unittest tests.test_mcp_server -v y
python3 tests/run_golden.py; requieren motor vivo en los casos declarados.
No ejecutar la batería real con un motor distinto del artefacto registrado.

Las nuevas suites se crearán y se documentará su comando en cada SPEC;
aquí son criterios de aceptación, no comandos existentes ni tests pasados.
Las pruebas de política usan backend falso con contador de llamadas;
las pruebas de integración además usan el motor verdadero.

## I0 — Base local reparada

Usuario usable: agente local o humano CLI conserva texto/imagen y salida
estructurada, con errores confiables. No se necesita exposición externa.

F0/F1: ratificar requisitos, resolver dialecto de schema, estrategia de
compatibilidad y librería de validación; documentar nuevos límites sólo
para v2. Corregir defectos compatibles de v1 sin estrecharlo silenciosamente.
Si un fix necesita restricción incompatible, entregar adaptador v2 separado
manteniendo v1 local hasta decisión de migración; no anunciar v1 reparado.

Regresiones requeridas:

- Schema anidado no soportado rechazado aunque el campo no aparezca;
  bool no satisface number; estructuras inválidas no provocan crash.
- Campos extra y límites se verifican según dialecto aceptado; no afirmar
  additionalProperties:false si no está realmente soportado.
- PNG/JPEG truncados, falsas firmas y exceso de píxeles no llegan al motor.
- Salida cortada conserva estado incompleto; estructura parcial no pasa
  como completa; uso/tipos inválidos producen fallo controlado.
- B-T10 no pasa sin PID; PID deriva del listener, no de coincidencia laxa;
  medir memoria atribuible y presión/swap además de RSS bajo mmap.
- Dos arranques simultáneos, lock con dueño vivo, huérfano, PID reciclado,
  puerto ocupado por proceso ajeno y variables de entorno host adversas.
  Inspección previa vio lock con PID del shell comprobado como llama-server:
  hipótesis de carrera por confirmar en fixture aislado antes de corregir.
- Readiness verifica modelo efectivo además de salud; parar no mata ajenos.
- Motor/modelo/proyector se inventarían por ruta, revisión, hash y licencia.

Gate I0: demos locales, regresión y revisión fresca; rollback recupera
baseline registrado. Si falla, conservar v0.1.0 y reportar propiedad incierta.

## I1 — API común utilizable en loopback

Usuario usable: backend local consume API compatible OpenAI con las mismas
políticas que MCP v2; no necesita implementar validación propia para admitir
peticiones ni distinguir excepciones de llama.cpp.

Entregables: gateway modular, H, capabilities, errores estables, schema
wire cerrado y cliente Python mínimo. Puerto configurado sin ocupar 8080;
no cambiar el listener del motor en 8091 ni asumir puerto libre.
SPEC I1-D asigna puerto configurable y prueba colisión antes del arranque;
no esperar a D-03 de la exposición remota para decidir el puerto local.

Gate I1:

- Texto, JSON e imagen completan desde cliente HTTP real.
- Campo desconocido, esquema inválido, tamaño/cantidad/profundidad límite
  y URLs externas rechazados antes de llamar al backend (contador cero).
- Validación de esquemas independiente de restricción de generación.
- Allowlist de rutas; /props, /slots, /metrics y UI embebida no pasan.
- Límites comprobados antes de descompresión/decodificación costosa;
  compresión de entrada no admitida inicialmente; chunked tiene cota real.
- Errores saneados sin paths ni payload de usuario; request_id trazable.
- Conformidad con subconjunto OpenAI, lista de SDK/versiones comprobadas.
- v1 local sigue pasando; v2 no se anuncia como implementado por borrador.

Rollback I1: detener gateway y conservar operación local aceptada I0.

## I1-V — Modalidades locales del artefacto vigente

Usuario usable: agente o humano local transcribe audio español, recibe
voz española y conversa por turnos; después, video corto. Mismo motor y
modelo (ADR-001); loopback; ADR-006 enmienda ADR-005; ADR-007 fija voz.
I0/I1 conservan accepted_local. Evidencia de partida y límites de las
sondas: docs/reviews/2026-11-plan2-ajuste-multimodal.md.

Gate común: fixtures y umbrales fijados en SPEC antes de medir; medios
sólo data URI/base64 (URL -> 400, contador cero); capability anunciada
sólo tras su gate; voz o cámara reales sólo con D-09 aceptada.

- I1-V0: inventario ffmpeg/ffprobe/llama-tts con hash, PATH fijo en
  serve.sh, B-T8 corregido y aviso v1 «PROHIBIDO audio/video en 8091».
- I1-VA: sólo input_audio en chat (JSON); multipart /v1/audio/
  transcriptions y tools MCP v2 son cortes posteriores con su SPEC.
  CER sobre corpus sintético; «comprensión de audio» queda evaluable
  aparte (la sonda P-3 devolvió transcripción, no respuesta).
- I1-VS: llama-tts con texto por archivo 0600 o stdin (verificado en
  SPEC), esquema cerrado, una síntesis a la vez, 503 sin cola, salida
  única borrada; pico de memoria y swap medidos (REQ-5/B-T10 ampliado).
- I1-VR: SSE local, voz por frase, fin de turno por señal real; la
  desconexión cancela la tarea del motor (log o /slots) antes de liberar
  cupo; p95, N y marca de tiempo fijados antes de medir.
- I1-VV: límites de duración/FPS/frames/bytes; preguntas temporales
  sintéticas; readiness compara hash de ffmpeg con el inventario. Si no
  pasa, video no se anuncia.
- I1-VX (ADR-008): extensión del dialecto de schema v2 en stdlib (`enum`,
  `minimum`/`maximum` sin `bool`, `array` acotado 0..64 y sub-objeto de
  nivel 1 bajo la raíz con `required` y rechazo de claves sobrantes en
  todo objeto) y demostración de percepción multimodal estructurada
  (audio+schema e imagen+schema en un solo turno). v1 e I0/I1 intactos.
- I1-VM (ADR-008): perfil MCP local v2 sobre stdio que valida con
  `gateway_core` y enruta la ejecución por el gateway loopback `8092`
  (compartiendo el cerrojo único de `llama-tts` y los límites de S-05),
  exponiendo texto, visión, audio, síntesis de voz, capabilities (y
  video si `I1-VV` cerró su gate) sin alterar `mcp-tools-v1`.
- I1-VC (ADR-008): CLI unificado stdlib sobre el gateway loopback (8092)
  para modalidades activas y adaptador local del perfil D con simulador
  (`observed_at`/`expires_at` verificados antes y después de inferir,
  deduplicación/orden por `observation_id`, descarte de salida incompleta
  y `enum` cerrado sin actuadores; identidad remota de `device_id` en I4).

Rollback I1-V: retirar ruta del allowlist y la capability; v1 y I1 intactos.

## I2 — Servicio web privado por invitación

Usuario usable: dos proyectos con credenciales distintas consumen HTTPS
desde fuera de la máquina, con cuotas y observabilidad.

Antes de código: Operador fija proyecto piloto A/B, datos sintéticos o
reales autorizados, destino, identidad, dominio, TLS, acceso de red y coste.
SLO candidato para ratificar antes de medir: éxito >=99% de solicitudes
válidas admitidas en prueba sin fallos inducidos; p95 primer token <=5 s,
p95 total <=30 s para 64 tokens, cola <=10 s. Prueba se rechaza si el
hardware no cumple: ajustar alcance con decisión, nunca umbral retrospectivo.
SLO no es SLA público. Para imagen fijar SLO separado antes de prueba.

Dos experimentos separados, fijados por D-04: (A) admisión end-to-end con
configuración final de piloto y carga ofrecida 1/2/4/8, midiendo también
rechazo/timeout y cantidad efectivamente admitida; (B) capacidad aislada del
backend con concurrencia ejecutada/configuración de ensayo explícitamente
autorizadas. No crear principal con bypass habilitable en producción.
Si la configuración sólo ejecuta 1, no afirmar capacidad medida a 4/8 por
ofrecer esa carga. Configuración B nunca se activa por pasar un benchmark;
la A debe cumplir su SLO y publicar tasa de admisión/rechazo además de
latencia de admitidas, para no esconder saturación detrás del denominador.
Carga reproducible: prompts cortos/largos, mezcla texto/imagen y 30 min
en condición térmica registrada. No afirmar capacidad por tok/s secuencial.
Registrar versiones, timestamps, red, cache warm/cold,
cantidad de casos, errores, tiempo de cola, TTFT, total p50/p95, memoria,
presión/swap y carga del host. Límite de ejecución inicial del experimento:
45 min, 500 inferencias y sólo fixtures; parar ante presión crítica,
crecimiento sostenido de swap o afectar uso del Operador.
Reducir matriz antes de correr si no cabe; no declarar matriz completa.

Gate I2:

- Sin identidad 401; sin scope 403; revocado rechazado sin reinicio global.
- A no accede a B ni falsificando project_id ni por logs/cache/errores.
- Límites aplican por identidad a través de todos los clientes; cuotas no
  se duplican al reiniciar worker ni abrir conexiones nuevas.
- Cola acotada y justa; sin cupos fantasma tras timeout/desconexión.
- Servicio reinicia sin bucle; health/readiness distinguen proceso/modelo;
  logs rotan; secretos fuera de repo y resultado del modelo.
- Fallo DNS/TLS/motor produce error explícito; no fallback remoto oculto.
- Egreso denegado al motor salvo destinos de mantenimiento autorizados;
  ninguna imagen puede disparar fetch server-side.
- ADR I2-D asigna responsable y mecanismo viable de egreso por proceso/
  entorno aislado, lista exacta de destinos y permisos de mantenimiento;
  I2-P implementa y prueba esa política. No modificar firewall global o
  red ajena por este plan. Si no hay mecanismo verificable, bloquear remoto.
- I2-D registra mantenedor, suplente, canal autorizado y escalado local
  de vigilancia; sin canal externo aceptado, producir informe local para
  intervención, sin enviar mensajes a terceros.
- Backend sin acceso externo directo: verificación negativa y control
  positivo del acceso permitido desde gateway, no sólo un firewall supuesto.
- Métricas identifican modelo/config, colas, rechazos y carga sin contenido.
- Dossier aceptado antes de activación; demo desde A/B y retirada probada.

Vigilancia: ensayo manual genera informe sin cambio del baseline. Programar
job periódico necesita autorización de instalación/activación, aunque esté
incluido en la arquitectura. Sin ella queda procedimiento manual usable.
Rollback I2: revocar accesos y cerrar entrada externa; conservar I1 local.

## I3 — Agentes remotos y streaming de texto

Usuario usable: dos clientes MCP concretos ejecutan inferencia remota;
clientes H reciben texto progresivo con cancelación verificable.

Gate I3:

- Fijar protocolo y auth; contratos MCP 2025/2026 no se mezclan sin pruebas.
- Versiones no admitidas, audience/token/origin erróneos rechazados;
  autenticación y cuotas compartidas H/M; stdio v1 conservado.
- Completitud y error representados en tool result/outputSchema acordado.
- SSE entrega incrementos bajo proxy, error terminal sin falso DONE y
  desconexión termina trabajo o mantiene cupo bloqueado hasta confirmación.
- Prompt malicioso propone tool fuera de scope: nunca se ejecuta acción.
- Cancelación no soportada por backend impide anunciar capacidad; evaluar
  alternativa de worker aislado y su impacto, sin matar trabajos ajenos.

Rollback I3: deshabilitar perfil M/SSE sin romper H aceptado.

## I4 — Clientes web/apps y dispositivo simulado

Usuario usable: cliente JS/backend, cliente app representativo y simulador
de dispositivo consumen los mismos contratos. UI real sólo con encargo y
repo propios frontExpert+Skevi; no crearla como efecto implícito del plan.

Gate I4:

- No clave compartida en bundle/URL/log; login/logout/revocación y scope
  usuario/proyecto; contenido escapado y CSRF si cookies.
- capabilities evita mostrar voz/video no activos; error/saturación/
  truncamiento visibles; cancelar no continúa consumiendo sin control.
- Dispositivo tiene identidad revocable; observación vencida, reloj fuera
  de margen, reordenamiento y repetición descartan propuesta sin actuar.
- Simulador prueba pérdida de red y deduplicación; no actuadores reales.
- Tabla cliente/versión/perfil probado, ejemplo mínimo reproducible y
  política de retirada/deprecación entregados a cada consumidor.

Gate UI externo pendiente no impide cerrar sólo los clientes entregados:
reportar I4-C y I4-UI por separado, nunca declarar UI construida por handoff.
Rollback I4: retirar cliente/perfil defectuoso manteniendo API/MCP aceptados.

## I5 — Trabajos largos sin bloquear interacción

Usuario usable: envía job, consulta progreso, obtiene resultado privado,
cancela o recibe expiración explícita.

Gate I5:

- Jobs no amplían cuotas ni scopes; justicia entre interactivos y batch.
- Dos workers con misma idempotency key no duplican registro/ejecución;
  diferente cuerpo 409; A/B no comparten namespace ni resultados.
- Caída en cada transición: queued recuperable, running desconocido no
  repetido; encolado y publicación con durabilidad declarada y comprobada.
- TTL borra contenido y conserva tombstone acotado; cifrado/acceso
  operativos; sin datos reales hasta decisión de retención aceptada.
- Cancelación/deadline no libera cupo antes de liberar motor; resultados
  tardíos descartados; sin webhook arbitrario ni acceso por URL predecible.
- POST admitido con 202 perdido se recupera por idempotencia sin cancelar
  ni duplicar; GET desconectado no cambia estado. DELETE separa aceptación
  de cancelación y detención confirmada del objetivo.
- Tráfico interactivo conserva su SLO; si no, no activar batch simultáneo.

Rollback I5: detener nueva admisión, drenar/cancelar y conservar datos sólo
según retención aceptada; no borrar ni migrar por instrucción del modelo.

## I6 — Modalidades o versiones nuevas

Usuario usable: motor/modelo mejorado conservando modalidades existentes,
una modalidad nueva con cliente real y contrato propio, o baseline
preservado con candidato rechazado y razones reproducibles.

Rutas excluyentes de cierre: rechazo temprano (sin descarga/benchmark),
rechazo tras evaluación autorizada, o promoción aceptada. Las dos primeras
no exigen canario ni demo nueva; acreditan baseline intacto y motivo. Una
actualización de motor por seguridad o modelo sólo de texto prueba las
capacidades afectadas y regresión existente; no inventa modalidad nueva.

Las modalidades ya presentes en el artefacto baseline (voz, transcripción,
video) se habilitan en I1-V, no aquí; lo siguiente rige para candidatos.
Audio: muestra/duración/codec/idioma, ASR y métrica de error sobre corpus
consentido antes de correr. Voz: inteligibilidad, latencia, cancelación y
límites de salida; sin clonar identidad ni voces por defecto. Video:
duración/FPS/resolución/cantidad de frames y preguntas temporales evaluadas.
No inferir video válido por procesar una sola imagen ni ASR por handshake.

Gate I6: presupuesto y umbrales fijados antes, evaluación aislada y no
regresión del baseline; licencia/hardware/contrato revisados, aceptación
específica, canario y rollback. Promover modelo o motor exige su operación
registrada y nueva versión cuando contrato vigente lo exige.
Este gate operativo aplica a promoción; rechazo cierra con las evidencias
de su ruta, sin declarar mejora implementada ni activación.

## Registro de avance para ejecutores

Antes de iniciar una iteración, crear su registro con estado not_started,
owner, reviewer, bloqueos/decisiones y referencias a SPEC/contrato/tests.
Transiciones: not_started -> designing -> implementing -> verifying ->
ready_for_activation -> active, o blocked con causa. Trabajo local sin
activación remota puede cerrar accepted_local. Rechazo I6 usa rejected.
Cada actualización conserva fecha, HEAD/diff, gate, evidencia y próximo
paso; no marcar casillas por intención. El Operador decide aceptación y
activación; el agente propone el estado con evidencia y declara autoridad.
Estado vigente de cada iteración: docs/roadmap/registro-avance.md.

## Handoff por iteración

Registrar id, fecha UTC, autor/revisor y contexto recibido, HEAD/diff,
hashes de motor/modelo/proyector/config, tests/fixtures y salidas completas
saneadas; función que ya puede usar cada consumidor; límites y riesgos;
rollback probado y siguiente tarea. En docs/reviews va registro de hallazgos
con impacto, disposición y estado. Checkpoints AN-KLA sólo con autoridad
vigente y contratos, no necesarios para que estos archivos sean utilizables.
