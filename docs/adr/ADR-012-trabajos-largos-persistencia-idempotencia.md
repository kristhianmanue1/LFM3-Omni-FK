# ADR-012: Trabajos largos en segundo plano (Perfil J), persistencia atómica, idempotencia RFC 8785 y recuperación ante fallos

```text
ADR-012: Trabajos largos en segundo plano (Perfil J), persistencia atómica en disco,
idempotencia canónica (RFC 8785), aislamiento multi-inquilino y recuperación ante fallos.
Estado: aceptado (formalizado en TAREA I5-D, PLAN LFM3-2; 2026-11-07)
Contexto:
  - Tras completar las interfaces síncronas (H/W) y de streaming/remotas (M/D),
    el servicio compartido necesita soportar cargas de cómputo extensas (grandes
    volúmenes de texto, procesamiento de videos o transcripciones largas) sin que
    las conexiones HTTP sufran interrupciones o timeouts.
  - El Perfil J (docs/contracts/perfiles-servicio-v2.md §J) establece requisitos
    estrictos de idempotencia, durabilidad y aislamiento entre inquilinos.
  - Riesgos técnicos identificados:
    1) Duplicación de cómputo costoso si el cliente reintenta por pérdidas de red.
    2) Inanición del tráfico interactivo si los trabajos en segundo plano saturan
       el motor llama.cpp (8091).
    3) Pérdida de estado o inconsistencia si el proceso servidor se reinicia
       mientras un trabajo se encuentra en ejecución.
    4) Fugas de privacidad si los identificadores o resultados de trabajos son
       accesibles entre proyectos distintos.
Decisión:
  1. Endpoints Wire normativos:
     - POST /jobs: admite la tarea en segundo plano requiriendo Idempotency-Key.
       Responde 202 Accepted con status_url tras persistir atómicamente el job.
     - GET /jobs/{id}: consulta de estado y resultado. Exige token del mismo
       proyecto; intentos de consulta desde proyectos ajenos devuelven 404 Not Found.
     - DELETE /jobs/{id}: cancelación explícita. Retira de cola si está queued, o
       marca cancellation_pending si ya comenzó ejecución.
  2. Idempotencia normalizada según RFC 8785:
     - El payload {operation, payload} se serializa canónicamente (claves ordenadas,
       espacios eliminados, floats finitos) y se calcula su SHA-256.
     - Si la clave Idempotency-Key ya fue usada por el mismo proyecto:
       * Si el hash del cuerpo coincide: responde 202 con el job existente.
       * Si el hash del cuerpo difiere: responde 409 Conflict (idempotency_conflict).
  3. Durabilidad y persistencia atómica:
     - El estado se persiste en archivos JSON bajo run/jobs/data/<project_id>/<job_id>.json.
     - Las escrituras se realizan en archivo temporal y se consolidan mediante
       os.replace (POSIX rename atómico).
  4. Recuperación determinista ante reinicio del servidor (fail-closed):
     - En el arranque del servicio, todo trabajo encontrado en estado running pasa
       a failed con detalle de error outcome: unknown.
     - Queda estrictamente prohibido el reintento automático ciego de tareas en vuelo.
  5. Contención de recursos y equidad:
     - Límite global estricto: máximo 1 worker ejecutando simultáneamente para
       preservar el presupuesto del motor para llamadas interactivas.
     - Límite de cola por proyecto: 1 job queued por proyecto; cola global máxima 8.
Consecuencias:
  - Positivas:
    * Los clientes pueden delegar inferencias largas con garantía de no duplicación.
    * Los resultados son estrictamente privados y duraderos según el TTL acordado.
    * El tráfico interactivo de baja latencia queda protegido contra sobrecarga.
  - Negativas / Mitigaciones:
    * La concurrencia de jobs es serial (1 worker activo); mitigación: apropiado
      para hardware con recursos limitados (un único modelo en memoria).
```
