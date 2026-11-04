# Revisión adversarial documental independiente — Paquete PLAN LFM3-2

**Método.** Revisión puramente documental, sin herramientas ni comandos (denegados), sin historial de autor ni rondas previas. Leí los seis documentos propuestos completos y los contrasté contra `superficie-inferencia-v1.md` y `mcp-tools-v1.md`. Las líneas citan el paquete recibido. No ejecuté pruebas ni verifiqué hashes.

## Hallazgos priorizados

**F-01 · ALTA · I0-R ordena "corregir" v1 rompiendo su propia cláusula de compatibilidad.**
Archivo/líneas: PLAN (64–71); iteraciones (43–47, 47–61); superficie-v1 Compatibilidad (103–109); mcp-v1 (87–91).
Contraejemplo: v1 acepta hoy bool como number y PNG truncado (sondas, objetivo 35–37); v1 exige v2 para "restringir entradas hoy aceptadas". I0-R Produce "correcciones locales" y verifica "suite/golden sin regresiones": si el fix rechaza bool o PNG truncado en la superficie v1, un golden que capturaba 2xx pasa a 400 — el ejecutor no puede satisfacer a la vez I0-R y la compatibilidad v1; iteraciones (43–47) ya lo prohíbe ("no anunciar v1 reparado"), pero el plan, que es lo que ordena tareas (203), no incorpora esa división.
Impacto: riesgo de reparación silenciosa de v1 o de gate I0 imposible de cerrar limpio.
Corrección: dividir I0-R en fixes no observables como restricción (crashes, medición B-T10) aplicables a v1, y rechazos de entradas antes aceptadas detrás de adaptador/flag v2 con v1 intacto; ajustar Produce y verificación.

**F-02 · ALTA · Gate I2: la matriz de carga 1/2/4/8 es inobservable bajo los límites candidatos.**
Archivo/líneas: iteraciones (105–112) vs servicio-general (37–41).
Contraejemplo: concurrencia global 1, por proyecto 1, cola por proyecto 2, 10 ll/min: a concurrencia 8, ~5 de 8 peticiones reciben 429/503/queue_timeout; TTFT/total p95 a 4–8 no puede medirse. El SLO ("solicititudes válidas admitidas", 99–101) excluye rechazos de política, así que el gate "pasa" sin haber observado nunca la concurrencia que exige.
Impacto: benchmark no concluyente o tentación de relajar límites sin decisión registrada.
Corrección: que D-04 fije además la configuración de medición (principal de benchmark con límites elevados, o política documentada como desviación durante la corrida), conservando los límites ratificados para activación.

**F-03 · MEDIA-ALTA · Vacío sin responsable: la denegación de egreso del motor exigida por el gate I2 no la produce ninguna tarea.**
Archivo/líneas: iteraciones (124–127); PLAN I2-D (98–103), I2-P (104–111); superficie-v1 (35–38).
Contraejemplo: el gate exige "verificación negativa y control positivo" del egreso del backend; ningún Produce implementa el mecanismo (PF/launchd/sandbox — hipótesis a verificar en SPEC) sobre un binario Homebrew congelado; "destinos de mantenimiento autorizados" (125) carecen de lista y de autoridad que los apruebe.
Impacto: gate incerrable por quien ejecuta I2-P; la superficie SSRF hoy contenida sólo por localhost queda expuesta tras I2 sin control real. Este es un vacío sin responsable, no un gate de diseño futuro asignado.
Corrección: ADR de egreso en I2-D (mecanismo, lista de destinos, autoridad) y Produce explícito en I2-P ("política de egreso implementada y verificada"). Contraste: el dialecto de schema sí está asignado (servicio-general 146–148 → I0-D) y el schema del perfil D también (perfiles 95); esos no son vacíos.

**F-04 · MEDIA · I0-D declara producir decisiones D-01..D-07 que no vencen en I0.**
Archivo/líneas: PLAN (57–58) vs objetivo (84–94).
Contraejemplo: el Produce de I0-D incluye "decisiones D-01..07"; D-05 vence "antes I4-UI" y D-06 "antes I6": cerrarlas en I0 contradice sus fechas y forzaría decisiones sin datos (hardware, demanda, UI).
Impacto: ejecutor literal bloquea I0 o decide fuera de su tiempo/autoridad.
Corrección: reformular Produce como "registro de D-01..D-07 con estados (D-01 cerrada; resto pendiente con fecha límite)".

**F-05 · MEDIA · Cancelación: semántica accepted|pending indefinida y cancel ausente del perfil M.**
Archivo/líneas: servicio-general (16–18, 79–86); perfiles M (48–49).
Contraejemplo: el contrato no define cuándo se devuelve `accepted` frente a `pending` (¿queued vs running?); M lista tools sin `cancel` y remite a "cancelación por transporte", mientras el contrato declara `cancel` operación común y S-05 exige paridad HTTP/MCP.
Impacto: dos implementaciones conformes devolverían estados distintos; el consumidor MCP carece de camino contractual explícito de cancelación.
Corrección: mapear cada estado de solicitud → `cancellation_status` y declarar en M si cancel viaja como tool o como cancelación de protocolo MCP con semántica idéntica a la del contrato.

**F-06 · MEDIA · "Rechazar campos desconocidos" choca con la compatibilidad OpenAI declarada del perfil H.**
Archivo/líneas: servicio-general (22); perfiles H (11–13, 19–21, 87); superficie-v1 (88–93).
Contraejemplo: SDKs OpenAI envían `temperature`/`seed`/`top_p` habituales; v1 los ignora con 2xx; H los rechazaría con 400 por la regla global, mientras H promete compatibilidad de subconjunto OpenAI y S-06 exige ejemplos ejecutables.
Impacto: rotura de clientes reales y de los ejemplos del propio plan.
Corrección: en SPEC-HTTP, lista de campos aceptados-e-ignorados (muestreo bajo greedy) distinta de los desconocidos-rechazados, documentada como desviación.

**F-07 · MEDIA · Idempotencia J: igualdad de cuerpo sin canonicalización y reuso de clave tras tombstone sin definir.**
Archivo/líneas: perfiles J (111–130).
Contraejemplo: reintento con claves JSON reordenadas → "cuerpo distinto" → 409 espurio; tras 24 h de tombstone, repetir la misma clave crea un job nuevo que duplica ejecución, sin conducta contractual declarada ("no exactly-once" cubre fallos, no reuso de clave).
Impacto: conflictos falsos para clientes legítimos; duplicación silenciosa en automatizaciones de larga vida.
Corrección: definir comparación canónica (o declarar byte-exacto) y documentar el comportamiento post-TTL (nuevo job_id) en contrato y ejemplos.

**F-08 · MEDIA-BAJA · Perfil W: la atribución por usuario final se disuelve en el principal de proyecto.**
Archivo/líneas: perfiles W (70–87); servicio-general (10–14, 131).
Contraejemplo: el backend autentica al usuario y llama a H con credencial de proyecto; los logs del servicio sólo ven al principal; la auditoría ("acceso administrativo auditado") termina en el backend sin campo contractual de correlación.
Impacto: abuso por usuario final no investigable desde el servicio; obligación de auditoría difusa.
Corrección: declarar responsable explícito (backend) y añadir campo opcional de correlación con nota de minimización, o aceptar documentadamente el límite.

**F-09 · BAJA · Frase colgante en J.**
Archivo/líneas: perfiles J (126–127): "…aceptación no acredita cómputo detenido. resultado con contrato general."
Contraejemplo: oración sin verbo; queda sin definir si el resultado viaja en el envelope del contrato general.
Impacto: ambigüedad menor en documento normativo.
Corrección: "El resultado se entrega en el envelope del contrato general."

**F-10 · BAJA · Vigilancia: suplente y canal de aviso sin fecha límite ni tarea; estado `blocked` fuera del diagrama.**
Archivo/líneas: ciclo-vida (23–24, 55–56, 70–72); PLAN I2-D/I2-V.
Contraejemplo: mantenedor se designa en I2-D, pero suplente/canal quedan "antes de automatizar notificaciones" sin D-id ni Produce; la escalada tras dos fallos consecutivos (55–56) puede quedarse sin destinatario; `blocked` (72) no tiene transiciones en el diagrama (70–71).
Impacto: hueco de autoridad en el ciclo de vida; estado no operativo.
Corrección: asignar suplente/canal al checklist I2-D; formalizar `blocked` como estado o etiqueta con entrada/salida.

**F-11 · BAJA · Puerto del gateway I1 sin decisión asignada.**
Archivo/líneas: iteraciones (73–75); objetivo D-03 (90).
Contraejemplo: D-03 cubre host/dominio/TLS "antes I2"; el puerto loopback del gateway que I1-A implementa no está en la tabla de decisiones ni mandato de SPEC I1-D; "no asumir puerto libre" se reconoce, nadie lo cierra.
Impacto: bloqueo menor o elección ad hoc en I1-A.
Corrección: fijar puerto en SPEC I1-D con verificación de colisión.

**F-12 · BAJA · Umbrales de códigos de error presentados como globales admiten overrides por perfil.**
Archivo/líneas: servicio-general (40–41, 100–104) vs perfiles J (137).
Contraejemplo: la tabla general fija cola ≤10 s → `queue_timeout` y procesamiento ≤120 s; J propone cola 60 s y procesamiento 600 s; la marca "I1/I2" de la tabla (26) es fácil de pasar por alto y la sección Errores no repite el alcance.
Impacto: consumidor asume 504 a los 10 s para jobs.
Corrección: anotar en Errores que los umbrales son por perfil y versionados, con referencia a cada perfil.

## Veredicto

**fix-and-retry.** La arquitectura es coherente, la disciplina de autoridad es notablemente buena y la utilidad por iteración es real (I0 local → I1 API → I2 piloto → I3 agentes → I4 clientes → I5 jobs → I6 modalidades). Pero F-01 y F-02 son contradicciones ejecutables dentro de gates I0/I2, y F-03 es un vacío sin responsable en un gate de seguridad multiusuario; ninguna exige implementación ahora, todas son correcciones documentales previas a la decisión D-01. Los gates de diseño futuro correctamente asignados (dialecto schema→I0-D; matriz MCP→ADR I3-D; schema D→SPEC por tarea) no se contaron como defectos.

## Límites de la revisión

- Documental y de un solo pase; sin herramientas, sin ejecución de gates, sin pruebas, sin red ni memoria.
- Sin historia de autor ni rondas previas, según el encargo; los números de línea son los del paquete recibido, no verifiqué hashes SHA256.
- Las hipótesis de factibilidad (PF/launchd para egreso; SDKs OpenAI y campos por defecto) son razonamientos a confirmar en SPEC, no mediciones.
- No exijo que el software futuro exista hoy; cada hallazgo se contrastó con la distinción gate-asignado vs vacío-sin-responsable.
- Proveedor/modelo: autodeclaración del agente sin metadatos de runtime para confirmarla — GLM (Z.ai), modelo GLM-5.3 Flash.

🎙 jarvis: LFM3-2 · verificación · He concluido la revisión adversarial independiente: doce hallazgos priorizados, dos de ellos altos, con veredicto fix-and-retry servido para su decisión; ninguna prueba fue ejecutada ni archivo tocado. · El plan está bien cortado, operador; sólo pide unos ajustes de sastrería antes de la decisión D-01.

Confirmado el estado: estoy en modo Plan, y la revisión ya fue entregada íntegramente en la conversación — sin crear ni tocar archivos, sin herramientas, tal como exigía el encargo. Nada por corregir en ese respecto.

Si el veredicto **fix-and-retry** se acepta, la ronda de corrección sería puramente documental y constaría de, en orden sugerido:

1. **F-01 (alta)** — Reescribir la TAREA I0-R del plan: separar fixes no-observables (aplicables a v1) de rechazos de entradas antes aceptadas (detrás de adaptador v2), y ajustar su Produce y verificación.
2. **F-02 (alta)** — Añadir a D-04 en `objetivo-y-alcance-servicio.md` la configuración de medición del benchmark (principal/límites de prueba como desviación documentada).
3. **F-03 (media-alta)** — ADR de egreso del motor en I2-D y Produce explícito en I2-P; cerrar el vacío sin responsable.
4. **F-04 a F-12** — Ajustes menores: registro de decisiones D-01..07 en I0-D, mapeo `cancellation_status`, política de campos ignorados en SPEC-HTTP, canonicalización de idempotencia J, frase colgante en perfiles J, suplente/canal en I2-D, puerto del gateway en SPEC I1-D, y nota de alcance por perfil en la sección Errores.

Todas son ediciones de los seis documentos propuestos, sin implementación ni activación — coherente con D-01 y con la autoridad del encargo original.

**Nota de modo:** no puedo aplicar esas ediciones ni tocar ningún archivo mientras permanezca en este agente. Si desea que ejecute la ronda de corrección sobre los documentos, deberá cambiar a un agente con capacidad de edición; entonces procedería con encargo explícito y solo sobre esos ficheros.

🎙 jarvis: LFM3-2 · documentación · El informe quedó servido en la conversación y la ronda de corrección queda esbozada en doce remates, sin que un solo archivo haya sido molestado. · En modo Plan solo sirvo el té; para la costura, deberá cambiar de agente.
