# ADR-013: Triaje formal de candidatos, evaluación comparativa contra Golden Dataset y protocolo gobernado de promoción o rechazo

```text
ADR-013: Triaje formal de candidatos, evaluación comparativa contra Golden Dataset
y protocolo gobernado de promoción o rechazo preservando el baseline congelado.
Estado: aceptado (formalizado en TAREA I6-E/I6-U, PLAN LFM3-2; 2026-11-07)
Contexto:
  - Las decisiones fundacionales (D-06, ADR-001) establecen que el motor llama.cpp
    y los pesos de LiquidAI/LFM3-Omni-2B-GGUF están congelados por registro.
  - La Fase I2-V entregó la infraestructura de vigilancia periódica sobre fuentes
    oficiales, pero faltaba formalizar la compuerta de evaluación y promoción para
    cerrar el PLAN LFM3-2.
  - Riesgos técnicos y normativos:
    1) Actualizaciones automáticas o silenciosas que degraden la calidad o rompan
       compatibilidad con clientes del ecosistema.
    2) Descarga de modelos no testeados o con licencias comerciales hostiles que
       comprometan legalmente el proyecto.
    3) Consumo excesivo de CPU/GPU o memoria durante benchmarks incontrolados.
    4) Falta de reversibilidad si un modelo promovido falla en producción.
Decisión:
  1. Compuerta de Rechazo Temprano (Early Rejection Gate):
     - Antes de descargar pesos o ejecutar pruebas de cómputo, todo candidato se
       evalúa contra cuatro criterios excluyentes:
       * Licencia admisible (sin telemetría obligatoria ni restricciones abusivas).
       * Arquitectura compatible con el runtime llama.cpp local.
       * Presupuesto de memoria dentro de límites (RSS pico <= 6 GB).
       * Soporte omnimodal (no perder ninguna modalidad activa del baseline).
     - Si incumple cualquiera de ellos, pasa de inmediato a 'rejected' con dictamen
       inmutable y sin consumo de ancho de banda ni cómputo.
  2. Evaluación comparativa en paralelo:
     - Los candidatos que superen el triaje temprano se ejecutan en entorno aislado
       contra un Golden Dataset omnimodal representativo.
     - En ningún momento se sobrescriben ni alteran los archivos del baseline activo.
     - Se miden de forma trazable: conformidad con esquemas (schema v2-ext),
       latencia p50/p95 (TTFT) y memoria pico.
  3. Dictamen por defecto: Rechazo Formal (Fail-Closed):
     - Todo candidato que no demuestre paridad o superioridad técnica es rechazado.
     - El baseline congelado, sus hashes SHA-256 y sus puertos permanecen inalterados.
  4. Protocolo de Promoción Excepcional:
     - Solo procede con autorización expresa del Operador tras evaluar el expediente.
     - Exige despliegue en canario (puerto secundario) y verificación del plan de
       rollback en un solo paso antes de redirigir el tráfico principal.
Consecuencias:
  - Positivas:
    * Se elimina cualquier riesgo de regresión silenciosa o rotura de contratos.
    * Se garantiza la reproducibilidad absoluta y la integridad legal del sistema.
    * Se cuenta con un camino estructurado y medido para futuras evoluciones del motor.
  - Negativas / Mitigaciones:
    * La evaluación requiere tiempo y dataset de calibración; mitigación: el triaje
      temprano descarta el 90% de los candidatos sin coste alguno.
```
