# Vigilancia y ciclo de vida de motor/modelo

Estado: PROPUESTO; procedimiento diseñado, ninguna vigilancia activada.
Procedencia: S-09 y mandato del Operador 2026-11-04.
Razón: detectar mejora sin convertir upstream en actualización autorizada.
Se incorpora desde I0; I2 entrega inventario y ensayo; I6 evalúa candidatos.

## Objetos distintos que deben identificarse

- Servicio: versión, contrato, configuración y dependencias fijadas.
- Motor: paquete, build/commit, binario/hash y plataforma.
- Modelo: repositorio, revisión inmutable, archivo GGUF/hash/cuantización.
- Proyector y auxiliares: revisión/hash, plantilla/tokenizador/config.
- Evaluación: corpus/versiones/hashes, condiciones y resultados brutos.

El baseline inicial se inventaría sin descargar ni actualizar artefactos.
Si no puede acreditarse origen/revisión exactos, registrar unknown y bloquear
promoción; un hash local no prueba autenticidad o autorización del origen.
El nombre de una familia no convierte modelos diferentes en compatibles.

## Fuentes y cadencia propuesta

Responsable: mantenedor del servicio designado por Operador en I2-D.
Suplente y canal de aviso se fijan antes de automatizar notificaciones.
I2-D los registra junto al mantenedor; I2-V verifica su presencia. Sin canal
externo aceptado, la intervención se solicita mediante informe local.

| Fuente oficial | Qué se vigila | Frecuencia propuesta |
|---|---|---|
| HF LiquidAI/LFM3-Omni-2B-GGUF y ficha original | commits/revisiones, archivos, capacidades, licencias | semanal |
| LiquidAI oficial | sucesores de familia y notas de versión | mensual |
| ggml-org/llama.cpp releases/avisos de seguridad | cambios del motor y vulnerabilidades | semanal |
| canal de seguridad del proveedor/dependencias fijadas | afectación del baseline | diaria si job autorizado |
| especificación MCP y SDK elegido | versiones, auth y deprecaciones | mensual |
| registro local de carga/calidad/incidentes | regresión o capacidad insuficiente | semanal y tras incidente |

Fuentes: https://huggingface.co/LiquidAI/LFM3-Omni-2B-GGUF,
https://huggingface.co/LiquidAI/LFM3-Omni-2B,
https://github.com/ggml-org/llama.cpp/releases,
https://github.com/ggml-org/llama.cpp/security/advisories,
https://modelcontextprotocol.io/specification/.
No fiarse de agregadores, un alias latest o recomendaciones de un LLM.
Fijar en configuración la allowlist exacta; impedir redirecciones a destinos
no permitidos. Metadatos de proveedor siguen siendo datos no confiables.

Cadencias son objetivos operativos pendientes de activación, no promesas de
monitoreo actual. Ejecución manual es válida mientras no exista job aceptado.
Presupuesto candidato por corrida: <=12 peticiones, <=5 MiB transferidos,
<=120 s; sin descargar pesos ni invocar inferencia tarifada.
Cachear ETag/revisión; no actualizar paquetes, modelos ni reglas de consumo.

## Salida de vigilancia

Registro por corrida: run_id, checked_at UTC, baseline_ref, fuente/URL,
observed_revision, status, evidence_ref y next_due_at. Una fuente fallida
produce status unavailable, conserva last_success_at y marca obsolescencia;
no se interpreta como no_change. Tras dos fallos consecutivos o vencimiento
2x de cadencia, solicitar intervención al mantenedor.
Deduplicar por fuente+revisión; sin novedades, no generar alertas repetidas.
No enviar email/Slack u otro mensaje sin canal y autorización explícitos.

Registro candidato: candidate_id, origen/revisión/fecha, relación con
baseline, cambios declarados atribuidos, licencia exacta/hash, artefactos,
riesgo, coste/hardware requerido y estado. No marcar verified porque lo
publique el proveedor. Ejemplo: candidato mejora visión según su ficha;
la medición local aún no existe.
Persistencia de estos registros será código de I2-V con contrato cerrado,
retención/paths fijados en SPEC; este archivo no escribe memoria AN-KLA.

## Máquina de estados de candidato

Estados: detected -> triaged -> evaluation_authorized -> evaluated ->
rejected | promotion_proposed -> accepted -> canary -> active -> retired.
blocked es una anotación, no un estado alternativo: conserva prior_state,
blocked_reason, blocked_at y owner. Entra al faltar dependencia, sale al
registrar resolución verificada y continúa desde prior_state, sin saltar
gates ni aceptar autoridad nueva. rollback devuelve baseline previo.
Transición temprana explícita: triaged -> rejected por licencia,
incompatibilidad o coste no aceptable. Evidencia mínima: fuente/revisión,
razón, responsable, fecha y hashes/config del baseline intactos; no exige
descarga, autorización de evaluación, benchmark ni canario.

- detected/triaged: sólo metadatos; no descargar o ejecutar código del autor.
- evaluation_authorized: permiso de descarga, destino, coste, datos,
  duración y acciones exactas registrado; entorno aislado del baseline.
- evaluated: mediciones reproducibles y límite de incertidumbre.
- promotion_proposed: dossier contrato/migración/licencia/rollback/revisión.
- accepted: autorización del Operador, no autodeclaración del modelo.
- canary: exposición acotada autorizada; no datos reales por defecto.
- active: criterios canario cumplidos y activación exacta aceptada.
- retired: fecha de fin, consumidores avisados por canal autorizado,
  versión anterior recuperable según retención acordada.

Cada transición conserva autor, autoridad, artefactos exactos y evidencia.
Promoción modifica baseline sólo mediante operación registrada. Vigilar y
clasificar son autoridades diferentes de descargar, probar y activar.

## Evaluación de mejora

Antes de cada experimento fijar hipótesis, corpus, umbrales, presupuesto,
comparador y criterio de rechazo. Mantener corpus estable; casos nuevos se
versionan por separado y se evalúan en ambos candidatos. Comparar:

- Conformidad de contratos, rechazo de entradas y estabilidad.
- Calidad por tarea/idioma y modalidad; no sólo benchmarks del proveedor.
- Éxito de schema, propuesta de tools válida y resistencia a instrucciones
  maliciosas en texto/imagen; no se pretende prueba universal de seguridad.
- Latencia p50/p95, TTFT, throughput bajo carga, memoria/presión/swap,
  energía si se mide, cancelación y recuperación.
- Coste de operación y disponibilidad del hardware real.
- Licencia y términos aplicables a entidad y forma de ofrecer el servicio.

Regla candidata: 100% de propiedades contractuales críticas; cero
HIGH/BLOCKER abiertos; calidad no inferior al margen fijado por tarea;
latencia/memoria dentro de SLO aceptados. No compensar ruptura de seguridad
con promedio de calidad. Si mejora una tarea y empeora otra, proponer perfil
nuevo o rechazar; nunca cambiar alias servido en silencio.

La ficha/modelo nuevo no implica motor compatible: evaluar pareja completa.
Si se requiere motor distinto, probarlo como cambio separado antes del
modelo, manteniendo posibilidad de atribuir la regresión.

## Canario y rollback

Antes: baseline y configuración recuperables, corpus/cliente de control,
consumidores y ventana de prueba identificados. Canario candidato: sólo
proyectos de prueba autorizados, hasta 1 h o 100 llamadas, lo primero que
ocurra; parar ante error crítico, fuga, presión de memoria o incumplir SLO.
Si el presupuesto no permite carga suficiente, resultado inconcluso.

Rollback: retirar ruta/candidato, restaurar artefactos/config exactos,
comprobar modelo servido y batería crítica; registrar intervalo afectado y
resultados desconocidos. No borrar evidencia para dejar verde el informe.
Motor congelado no significa ignorar vulnerabilidades: ante afectación,
contener/revocar exposición y elevar decisión; no actualizar sin permiso.

## Pruebas de la vigilancia

Usar fixtures locales: revisión idéntica, nueva revisión, etiqueta movida,
fuente caída, timeout, respuesta enorme, redirección host no permitido,
licencia cambiada y metadato que contiene instrucciones. Todos deben dejar
baseline intacto. Job ausente no se reporta sano: estado not_configured.
Una simulación verifica procedimiento; no acredita vigilancia en producción.
