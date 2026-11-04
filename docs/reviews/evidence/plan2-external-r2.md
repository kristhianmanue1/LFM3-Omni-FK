# Verificación de correcciones — Ronda R2 · PLAN LFM3-2

**Método.** Verificación puramente documental, de un solo pase, sin herramientas, comandos, red, memoria ni subagentes (denegados); ningún archivo escrito o modificado. Leí los seis documentos corregidos completos y los contrasté, hallazgo por hallazgo, contra el texto real recibido. Los números de línea citan el paquete recibido. No ejecuté pruebas ni gates, y no verifiqué hashes.

## Tabla de comprobación F-01..F-12

| ID | Estado | Evidencia breve en el texto |
|---|---|---|
| F-01 | **Cerrado** | PLAN I0-R (69): Produce separa "fixes compatibles v1" y "adaptador local v2 para nuevas restricciones"; verificación (72–73): "rechazos nuevos de tipos/schema/imagen sólo en adaptador v2, v1 preservado"; fallback (76): "si no es separable, bloquear su activación y elevar migración". Iteraciones (42–44): "no anunciar v1 reparado". Plan e iteraciones ahora coinciden. |
| F-02 | **Cerrado** | D-04 (objetivo 91) incluye "configuración de medición de capacidad"; iteraciones (107–115): A con "configuración final de piloto" mide "rechazo/timeout y cantidad efectivamente admitida" y publica "tasa de admisión/rechazo además de latencia de admitidas"; B aislado con "concurrencia ejecutada/configuración de ensayo explícitamente autorizadas"; "No crear principal con bypass habilitable en producción"; "Configuración B nunca se activa por pasar un benchmark". |
| F-03 | **Cerrado** | I2-D (PLAN 107): ADR "identidad/red/egreso/supervisor"; Gate I2 (iteraciones 138–141): "ADR I2-D asigna responsable y mecanismo viable de egreso… lista exacta de destinos y permisos de mantenimiento; I2-P implementa y prueba esa política… Si no hay mecanismo verificable, bloquear remoto". I2-P (122–124) implementa contención con verificación negativa y positiva. El vacío sin responsable queda asignado. |
| F-04 | **Cerrado** | PLAN I0-D (64–66): "registrar D-01 aceptada y D-02..D-07 pendientes hasta su gate", con verificación "sin exigir decisiones de UI/modalidad/comercialización para cerrar I0". |
| F-05 | **Cerrado** | Contrato (79–90): `cancellation_status` y mapeo por estado objetivo (received/queued→accepted; running→pending; ya pending→pending sin duplicar; terminal→already_terminal). Perfil M (57–60): cancel lógico "se mapea al mecanismo nativo de la versión" (notificación JSON-RPC por id o cierre de stream), "se conserva el mapeo de estados general", sin tool adicional. H (61–63): "DELETE /requests/{request_id}… con el resultado de cancel del contrato general"; J (149–150) DELETE separa estados. |
| F-06 | **Cerrado** (disputa resuelta) | H (14–20): "Compatibilidad significa sólo ese subconjunto"; "SPEC-HTTP enumera por campo: admitido y aplicado, o rechazado con motivo; no aceptar-e-ignorar parámetros en silencio"; temperature distinta de cero rechazada, seed y no implementados rechazo explícito; "Fixtures por SDK/version/config"; Gate I1 (89): "Conformidad con subconjunto OpenAI, lista de SDK/versiones comprobadas". Sin contradicción residual (detalle abajo). |
| F-07 | **Cerrado** | J (138–142): digest de "operación+payload normalizado con defaults", RFC 8785, excluye correlación/credenciales, rechaza claves duplicadas y no finitos, fixtures de orden de claves; (155–158): tras vencer tombstone "crea un nuevo job_id y puede repetir inferencia", ejemplos deben mostrar la ventana. |
| F-08 | **Cerrado** | W (97–101): responsable explícito backend W con "asociación minimizada user_ref-client_request_id-request_id" y retención propia; "H no eleva client_request_id a identidad ni promete auditar al usuario final"; contrato (12–14) lo excluye como identidad. |
| F-09 | **Cerrado** | J (151): frase completa: "El resultado se entrega en el envelope del contrato general." |
| F-10 | **Cerrado** | Ciclo-vida (23–26): I2-D registra suplente/canal; "I2-V verifica su presencia"; sin canal externo, "informe local". Iteraciones Gate I2 (142–144) replica. `blocked` (74–77): "anotación, no un estado alternativo" con prior_state/blocked_reason/owner, entrada y salida "sin saltar gates". |
| F-11 | **Cerrado** | Iteraciones (76–77): "SPEC I1-D asigna puerto configurable y prueba colisión antes del arranque; no esperar a D-03"; PLAN I1-D (89) fija "puerto". |
| F-12 | **Cerrado** | Contrato Errores (115–117): "los tiempos… son los del perfil/version configurados: H/M inicial 10/120 s; J propone 60/600 s. El código no fija un plazo universal; capabilities publica el del perfil". Coherente con J (165–166). |

## Resolución de la disputa F-06

La postura del autor no deja contradicción, y la compruebo en tres frentes:

1. **Coherencia interna.** El contrato general (22) ordena "rechazar campos desconocidos" en todos los perfiles; H redefine compatibilidad como subconjunto documentado y no promete aceptar payload SDK arbitrario. Ambos textos apuntan en la misma dirección; no hay norma que se viole a sí misma.
2. **La objeción original queda respondida, no esquivada.** El escenario del hallazgo (SDK real envía `temperature`/`seed` por defecto → 400 inesperado) se convierte en frontera documentada y verificable: fixtures por SDK/version/config obligan a observar qué envía realmente cada cliente antes de anunciarlo, los ejemplos deben ser ejecutables (S-06, Gate I1) y SPEC-HTTP — gate de diseño futuro correctamente asignado — enumera campo por campo. El rechazo explícito es además semánticamente más honesto que aceptar-e-ignorar: un cliente que pide temperature 0.7 y recibe salida greedy tendría divergencia silenciosa entre lo pedido y lo aplicado.
3. **Lo que queda es riesgo documentado, no contradicción.** Un consumidor con defaults incompatibles tendrá que configurar explícitamente; eso es una limitación anunciada, comprobada por la lista de SDK probados, no una norma que se incumpla a sí misma. Disputa resuelta a favor del autor.

## Nuevos HIGH/BLOCKER

**Ninguno.** Observaciones menores, no bloqueantes:

- **F-02 residual esperado:** bajo límites candidatos (concurrencia 1), la carga ofrecida 4/8 del experimento A producirá mayoría de rechazos. El texto ya lo hace concluyente al exigir publicar la tasa de admisión/rechazo "para no esconder saturación detrás del denominador" y permitir "reducir matriz antes de correr si no cabe". El dimensionado de límites de piloto pertenece a D-04. Documentalmente suficiente.
- **F-05, ruta H del cancel lógico:** aparte de DELETE, el endpoint wire del `cancel` común queda para SPEC ("Las rutas son propuestas; SPEC por iteración las cierra", perfiles 6). Declarado, no vacío sin responsable.
- **F-07, redacción:** "mismo cuerpo devuelve mismo job" (136) convive con la comparación por digest canónico que excluye campos de correlación (138–139); el segundo párrafo define la comparación operativa. Sin contradicción ejecutable.

No detecté regresiones: las correcciones no rompen cláusulas vecinas (compatibilidad v1 en H (20) y (47–48), congelación de motor, prohibición de bypass, SLO sin retrospectividad).

## Veredicto

**proceed.** Las doce correcciones están presentes y verificables en el texto recibido; la disputa F-06 queda resuelta con la semántica más estricta del autor (subconjunto con rechazo documentado, sin aceptar-e-ignorar); no hay HIGH/BLOCKER nuevos ni huecos sin responsable. Los gates de diseño futuro (enumeración de campos en SPEC-HTTP, librería de canonicalización en SPEC-JOBS, matriz SDK, rutas por perfil) están correctamente asignados a tareas con Produce y verificación, y no se cuentan como defectos ni se exige software implementado ahora.

## Límites de la verificación

- Documental y de un solo pase; sin herramientas, comandos, red, memoria ni subagentes; ningún archivo escrito ni cambiado aplicado.
- No ejecuté pruebas, gates ni comandos; no verifiqué los hashes SHA256 declarados en el paquete.
- Los números de línea citan el texto recibido en esta conversación.
- La viabilidad de fixtures SDK reales y de RFC 8785 en implementación sigue correspondiendo a sus SPEC.
- Proveedor/modelo: autodeclaración del agente sin metadatos de runtime para confirmarla — GLM (Z.ai), GLM-5.3 Flash.

🎙 jarvis: LFM3-2 · verificación · He cotejado las doce correcciones contra el texto recibido y todas quedaron servidas y en orden, sin sobresaltos nuevos; la disputa del perfil H se resolvió con la sastrería del autor. · Proceed, operador; el plan vuelve limpio a la mesa de decisiones.

Confirmado el estado: permanezco en modo Plan, y la verificación R2 ya fue entregada íntegramente en la conversación — sin crear ni tocar archivos, sin herramientas, memoria, red ni subagentes, tal como exigía el encargo. Nada por corregir en ese respecto.

El veredicto vigente es **proceed**: las doce correcciones F-01..F-12 quedaron verificadas contra el texto recibido, la disputa F-06 resuelta a favor del autor (subconjunto OpenAI con rechazo documentado, sin aceptar-e-ignorar), y sin HIGH/BLOCKER nuevos ni regresiones detectadas.

Si desea un siguiente paso documental — por ejemplo, registrar la disposición de esta ronda en `docs/reviews/`, o preparar el expediente para la decisión D-01 — deberá cambiar a un agente con capacidad de edición; en este agente no escribo ni aplico cambios. Mientras tanto, puedo seguir sirviendo análisis, contrastes o borradores en la conversación.

🎙 jarvis: LFM3-2 · breve · Verificación servida y modo Plan confirmado; el expediente queda listo para su disposición.
