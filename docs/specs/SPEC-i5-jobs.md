# SPEC-i5-jobs: Trabajos largos en segundo plano, persistencia, idempotencia y Perfil J

- **Fase**: I5 (Fase 5 del PLAN LFM3-2: Servicio Compartido)
- **Estado**: Aceptado / En implementación
- **Procedencia**: S-04, S-07, S-10, perfil J de `docs/contracts/perfiles-servicio-v2.md`
- **Fecha**: 2026-11-07
- **Autoridad**: Decisión del Operador (sesión 2026-11-07)

---

## 1. Contexto y Objetivos

La plataforma LFM3-Omni dispone de APIs síncronas (Perfil H/W) y streaming/MCP
(Perfil M). Para tareas de inferencia pesadas (documentos extensos, lotes de
análisis visual, transcripciones largas de audio o inspección exhaustiva de
video), las conexiones HTTP interactivas corren riesgo de timeout de red.

El **Perfil J (Trabajos Largos)** introduce ejecución desacoplada en segundo
plano con las siguientes garantías:
1. **Idempotencia estricta**: Uso de la cabecera `Idempotency-Key` y canonicalización
   RFC 8785 para evitar duplicar cómputo ante reintentos de red.
2. **Aislamiento multi-inquilino**: Los jobs y sus resultados son privados y
   visibles únicamente para el proyecto autenticado que los creó. Proyectos
   ajenos reciben `404 Not Found` (fail-closed, sin revelar existencia).
3. **Persistencia atómica y durabilidad**: Cada cambio de estado se registra
   en disco mediante escritura atómica (POSIX rename con reemplazo atómico).
4. **Recuperación segura ante fallos**: Un reinicio del servidor marca los
   trabajos que estaban en ejecución (`running`) como `failed` con error
   `outcome: unknown`, impidiendo la re-ejecución automática ciega.
5. **Control de concurrencia y no inanición**: Límite global estricto de
   1 job en ejecución simultánea para no degradar el tráfico interactivo H/M.

---

## 2. Definición Wire de Endpoints

### 2.1 `POST /jobs` — Creación / Admisión de Trabajo

- **Cabeceras obligatorias**:
  * `Authorization: Bearer <token>` (requiere scopes `jobs:create` y el scope
    de la modalidad correspondiente, e.g. `infer:text`).
  * `Idempotency-Key: <string ASCII 1..64 caracteres>`.
  * `Content-Type: application/json`.
- **Cuerpo de la solicitud**:
  ```json
  {
    "operation": "infer_text",
    "payload": {
      "messages": [{"role": "user", "content": "Analiza este texto extenso..."}],
      "max_tokens": 512,
      "temperature": 0.0
    },
    "ttl_seconds": 3600
  }
  ```
- **Canonicalización de Idempotencia (RFC 8785)**:
  * Se normaliza el objeto `{"operation": operation, "payload": payload}`
    ordenando claves alfabéticamente y eliminando espacios superfluos.
  * Se calcula `sha256(canonical_bytes)`.
  * Si ya existe un job registrado para `(project_id, idempotency_key)`:
    - Si el hash coincide: se devuelve inmediatamente `202 Accepted` con los
      datos del job ya existente (no se duplica la tarea).
    - Si el hash NO coincide: se responde `409 Conflict` (`idempotency_conflict`).
- **Respuesta de éxito (`202 Accepted`)**:
  ```json
  {
    "job_id": "job-a1b2c3d4-e5f6-47a8-b9c0-123456789abc",
    "state": "queued",
    "status_url": "/jobs/job-a1b2c3d4-e5f6-47a8-b9c0-123456789abc",
    "created_at": "2026-11-07T18:10:00.000000Z",
    "expires_at": "2026-11-07T19:10:00.000000Z"
  }
  ```
- **Límites de admisión**:
  * Máximo 1 job en estado `queued` por proyecto.
  * Máximo 8 jobs pendientes en la cola global.
  * Superar estos límites responde `429 Too Many Requests` (`job_queue_full`).

---

### 2.2 `GET /jobs/{id}` — Consulta de Estado y Resultado

- **Cabeceras obligatorias**:
  * `Authorization: Bearer <token>` (requiere scope `jobs:read`).
- **Comportamiento**:
  * Si el job no existe o pertenece a otro proyecto: `404 Not Found`.
  * Si el job expiró (`ahora > expires_at`): `410 Gone` para el propietario.
- **Respuesta (`200 OK`)**:
  ```json
  {
    "job_id": "job-a1b2c3d4-e5f6-47a8-b9c0-123456789abc",
    "contract_version": "2",
    "project_id": "proyecto-alpha",
    "operation": "infer_text",
    "state": "succeeded",
    "created_at": "2026-11-07T18:10:00.000000Z",
    "started_at": "2026-11-07T18:10:01.000000Z",
    "completed_at": "2026-11-07T18:10:05.000000Z",
    "expires_at": "2026-11-07T19:10:05.000000Z",
    "result": {
      "text": "Resultado del análisis...",
      "finish_reason": "stop",
      "complete": true
    },
    "error": null,
    "model_revision": "LiquidAI/LFM3-Omni-2B-GGUF"
  }
  ```

---

### 2.3 `DELETE /jobs/{id}` — Cancelación de Trabajo

- **Cabeceras obligatorias**:
  * `Authorization: Bearer <token>` (requiere scope `jobs:cancel`).
- **Comportamiento por estado**:
  * En `queued`: pasa de inmediato a `cancelled` y se retira de la cola.
  * En `running`: pasa a `cancellation_pending` y el worker finaliza la tarea
    como `cancelled`.
  * En estado terminal (`succeeded`, `failed`, `cancelled`): no muta el estado;
    responde con `cancellation_status: "already_terminal"`.
- **Respuesta (`200 OK`)**:
  ```json
  {
    "job_id": "job-a1b2c3d4-e5f6-47a8-b9c0-123456789abc",
    "cancellation_status": "accepted",
    "target_state": "cancelled"
  }
  ```

---

## 3. Máquina de Estados del Trabajo

```
               ┌──────────┐
               │  QUEUED  │ ◄─── POST /jobs (202 Accepted)
               └────┬─────┘
                    │
           (Worker lo reclama)
                    ▼
               ┌──────────┐
               │ RUNNING  │
               └────┬─────┘
                    │
         ┌──────────┼───────────────┬────────────────┐
         │          │               │                │
     (Éxito)    (Fallo/Error)   (Reinicio host)  (DELETE /jobs/{id})
         ▼          ▼               ▼                ▼
    SUCCEEDED     FAILED         FAILED       CANCELLATION_PENDING
                              (outcome:unk)          │
                                                     ▼
                                                 CANCELLED
```

---

## 4. Persistencia y Almacenamiento Seguro

- Directorio base: `run/jobs/` (o configurado vía `LFM3_JOBS_DIR`).
- Estructura:
  * `run/jobs/data/<project_id>/<job_id>.json`: Datos y resultado en
    claro con permisos 0600 (archivos) y 0700 (directorios); ver la
    desviación declarada más abajo.
  * `run/jobs/idempotency/<project_id>/<key_sha256>.json`: Registro de idempotencia
    con `{job_id, payload_hash, expires_at}`.
- Procedimiento de escritura segura:
  1. Serialización a JSON UTF-8.
  2. Escritura en archivo temporal `<archivo>.tmp.<pid>.<uuid>`.
  3. `os.replace` al destino definitivo (POSIX atómico).
- Al inicializar el servicio (`startup`):
  * Escaneo de `run/jobs/data/*/*.json`: cualquier job en estado `running` se
    actualiza a `failed` con mensaje `"Servidor reiniciado durante el procesamiento; resultado desconocido"`.

**DESVIACIÓN DECLARADA (D3, Operador 2026-11-08):** el contrato
`docs/contracts/perfiles-servicio-v2.md` §J («Persistencia cifra
resultados y controla accesos») NO se cumple: la persistencia de esta
iteración protege con permisos 0600/0700, sin cifrado en reposo. Los
permisos no protegen frente al operador del host ni frente a copias
del volumen. El cifrado queda fijado como **requisito bloqueante para
exponer `/jobs`** más allá del modo de prueba; su implementación es
una decisión y una tarea separadas (no se improvisa aquí). Procedencia:
decisión D3 del Operador, sesión 2026-11-08, expediente
`docs/reviews/evidence/fix-i5-jobs-frontera/` (intento 2).

---

## 5. Criterios de Aceptación y Gates

1. Tests unitarios e integrados cubriendo ciclo de vida completo (creación,
   idempotencia coincidente, conflicto 409, consulta, cancelación y aislamiento).
2. Verificación de no-fuga: un proyecto B intentando leer o cancelar un job de
   un proyecto A recibe `404 Not Found`.
3. Verificación de límite de cola por proyecto y global.
4. Verificación de recuperación ante reinicio (jobs en running pasan a failed).
5. Gates Skevi en verde y ruta de lectura obligatoria dentro del límite presupuestario.
