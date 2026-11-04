# Objetivo y alcance — evolución a servicio compartido

Estado: propuesta de F0 para PLAN LFM3-2, 2026-11-04.
Autoridad: encargo del Operador de esta sesión para producir un plan
incremental, contratos, vigilancia del ciclo de vida y dos revisiones.
Autoriza documentos y revisiones; no implementación, activación ni Git.
Procedencia normativa: AGENTS.md, estándar transversal y guías 01/02/04/06.
Razón: ampliar consumidores exige una frontera distinta de localhost v1.

## Objetivo del producto

Ofrecer a agentes, proyectos web, apps, dispositivos/robots y humanos un
servicio de inferencia compartido, versionado y verificable, con identidad,
recursos acotados y capacidades declaradas. Comenzar por texto e imagen
sobre el motor local vigente; habilitar acceso remoto de forma incremental.
El resultado del modelo es una propuesta de datos, nunca autoridad para
actuar ni garantía de verdad, seguridad física o validez de dominio.

Resultado observable: dos proyectos identificados consumen el mismo
servicio mediante clientes documentados, sin conocer detalles del motor,
sin acceder a recursos del otro y con errores y límites previsibles.

## Estado de partida y procedencia

- HEAD de partida: 4572164270073431a765e53e1353a233b0897dec.
- Rama de trabajo: docs/reconcile-current-state; dos correcciones
  documentales locales preceden a este plan y deben preservarse.
- Contratos v1 locales existentes: superficie-inferencia y mcp-tools.
- llama-server --version observado: 0.8.0 b11960, commit 8642541b2.
- F0 histórico fija Apple M2/16 GiB y localhost:8091; no se revalidó
  hardware ni capacidad sostenida en esta planificación.
- Ronda F3 histórica declara 37 tests y 12 golden; no son una prueba nueva
  de capacidad multiusuario ni acreditan aislamiento entre consumidores.
- AN-KLA context status y verify: ok; sin cambio de memoria en este encargo.
- Sondas sintéticas de la sesión reprodujeron: bool como number, esquema
  no soportado anidado omitido, cabecera PNG truncada aceptada, truncamiento
  de salida no comunicado y B-T10 exitoso sin PID. Deben volverse RED en I0.
- Aceptar propiedades adicionales es legal en JSON Schema por defecto;
  no acredita forma cerrada. No confundir este límite con aquel defecto.

## Requisitos de la ampliación

Todos provienen del encargo actual y las recomendaciones analizadas en
sesión; su adopción para ejecución se decide en el gate I0-D.

| ID | Requisito | Aceptación | Prioridad |
|---|---|---|---|
| S-01 | Inferencia texto/imagen utilizable incrementalmente | demo real y regresión de cada I0–I4 | imprescindible |
| S-02 | Contrato general y perfiles | versión, errores, límites y matriz de conformidad publicados localmente | imprescindible |
| S-03 | Identidad y permisos por consumidor | credencial revocada rechazada; cliente A no consulta B | imprescindible remoto |
| S-04 | Recursos y admisión acotados | exceso rechazado antes del motor; cola saturada no crece | imprescindible |
| S-05 | Igual política HTTP/MCP | fixtures equivalentes producen igual admisión, rechazo y cuotas | imprescindible |
| S-06 | Clientes agentes/web/apps/dispositivos | ejemplo ejecutable por perfil, incluido fallo controlado | imprescindible |
| S-07 | Operación verificable | reinicio, cancelación, salud y recuperación con evidencia | imprescindible |
| S-08 | Evaluación de capacidad y calidad | umbrales fijados antes de corridas, datos y decisión conservados | imprescindible |
| S-09 | Ciclo de vida modelo/motor | candidato detectado, evaluado, rechazado o promovido con rollback | imprescindible |
| S-10 | Datos minimizados y aislados | canarios A/B no cruzan logs, cachés ni resultados | imprescindible |
| S-11 | Voz/video verificables | demos de modalidad más presupuesto y regresión propios | imprescindible local (I1-V, ADR-006/007); video condicionado a su gate |
| S-12 | Contratos compatibles y migración | consumidor v1 sigue pasando; v2 no se activa por renombrar v1 | imprescindible |

## Dentro del alcance propuesto

- Núcleo de políticas compartido, API HTTP, adaptadores MCP local/remoto.
- Autenticación, cuotas, colas limitadas, cancelación, observabilidad.
- Ejemplos de integración; piloto privado por invitación con HTTPS.
- Contratos y pruebas de conformidad, incorporación de consumidores.
- Vigilancia de fichas, artefactos, licencias y avisos de seguridad.
- Integración robótica de interpretación/propuestas con simulador.
- Contrato para una UI separada basada en frontExpert + Skevi.

## Fuera del alcance inicial

- Alta disponibilidad, infraestructura multinodo y autoscaling.
- Acceso público anónimo, facturación y cobro a terceros.
- Control de actuadores físicos, navegación crítica o decisiones clínicas.
- Ejecución de shell/tools arbitrarias sugeridas por el modelo.
- Entrenamiento, fine-tuning, navegación web, RAG o embeddings no evaluados.
- Guardar conversaciones, imágenes o audio por defecto.
- Garantizar exactitud semántica por un schema válido.
- Actualizar automáticamente motor, modelo o políticas.
- Crear UI dentro de este repositorio; usar móviles/robots reales como
  sustituto de simuladores sin autorización de esos sistemas.

## Decisiones pendientes y defaults de propuesta

| ID | Decisión y fecha límite | Default seguro mientras falta |
|---|---|---|
| D-01 | Adoptar objetivo y contratos; antes de ejecutar I0 | documentos propuestos, sin activación |
| D-02 | Proyectos piloto, datos permitidos y responsable; antes I2 | sólo fixtures sintéticos |
| D-03 | Host, dominio, TLS, red, identidad y presupuesto; antes I2 | sólo loopback, ningún túnel |
| D-04 | SLO, límites piloto y configuración de medición de capacidad; antes benchmark I2 | valores candidatos, sin SLA ni bypass de cuotas |
| D-05 | Repositorio/UI y autorización separada; antes I4-UI | cliente mínimo sin UI nueva |
| D-06a | Prioridad de modalidad; antes de I1-V | ACEPTADA 2026-11-04: voz → conversación → visión/video → combinada |
| D-06b | Hardware y presupuesto de candidatos; antes I6 | texto/imagen estables |
| D-08 | Estrategia de voz; antes de I1-VS | ADR-007 propuesto: llama-tts, sin realtime nativo |
| D-09 | Datos de audio/imagen; antes de usar voz o cámara reales en gates | sólo fixtures sintéticos, sin persistencia, logs sin contenido |
| D-07 | Publicación comercial y licencia de código; antes ofrecerla | piloto interno sin oferta comercial |

Elegir framework, librería de validación, autenticación y supervisor se
resuelve en ADRs I0/I1: comparar al menos dos alternativas, fijar versiones,
licencia y superficie de ejecución. No instalar dependencias por este plan.
Si falta una decisión, bloquear sólo su tarea; preservar la funcionalidad
ya aceptada. La creación del plan no cambia CERRADA-6 ni ADR-001/002.

## Criterio de terminación de esta planificación

Plan, contratos propuestos, aceptación por iteración y vigilancia escritos;
revisión fresca, revisión externa solicitada y disposiciones registradas;
gates locales ejecutados. Una revisión externa fallida se declara pendiente,
no se sustituye por atribuir al CLI una aprobación inexistente.

## Fuentes técnicas para revalidar antes de implementar

Consulta documental de sesión, 2026-11-04; no congela upstream:

- MCP: https://modelcontextprotocol.io/specification/2026-07-28/
- Modelo: https://huggingface.co/LiquidAI/LFM3-Omni-2B-GGUF
- Licencia: https://huggingface.co/LiquidAI/LFM3-Omni-2B-GGUF/blob/main/LICENSE
- Motor: https://github.com/ggml-org/llama.cpp/tree/master/tools/server
- Consumo: https://genai.owasp.org/llmrisk/llm102025-unbounded-consumption/
- Agencia: https://genai.owasp.org/llmrisk/llm062025-excessive-agency/
- Schema: https://json-schema.org/understanding-json-schema/reference/object

Las afirmaciones históricas requieren nueva medición para cerrar un gate
operativo. La licencia debe revisarse sobre el texto exacto aplicable a la
entidad; no inferir habilitación comercial de la existencia de este plan.
