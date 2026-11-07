# Revisión de la Fase I5 — Trabajos Largos en Segundo Plano (Perfil J) — 2026-11-07

## Encargo y superficie (capa humana)

Encargo del Operador (2026-11-07): «adelante tienes comits, puesh, merges autorizados
segun consideres en el abanse y despes aprobada la tarea», continuando con la ejecución
metódica del PLAN LFM3-2 y asegurando la explotación omnimodal robusta.

Superficie entregada (Fase I5 completa: TAREAS I5-D, I5-J e I5-U):
- `docs/specs/SPEC-i5-jobs.md`: especificación técnica formal de la API de trabajos
  largos en segundo plano (Perfil J), canonicalización RFC 8785, máquina de estados,
  persistencia atómica y recuperación determinista.
- `docs/adr/ADR-012-trabajos-largos-persistencia-idempotencia.md`: decisión
  arquitectónica aceptada para endpoints `/jobs`, idempotencia con TTL de 24h,
  aislamiento multi-inquilino fail-closed y control estricto de concurrencia.
- `src/jobs_manager.py`: módulo central del motor de trabajos largos:
  * `canonical_json_rfc8785`: serializador JSON canónico determinista.
  * `JobsManager`: gestor de ciclo de vida con persistencia atómica POSIX
    (write-tmp + `replace`), almacenamiento en `run/jobs/data/` e `idempotency/`.
  * `startup_recover`: recuperación en arranque que pasa `running` a `failed`
    con error `server_interrupted` (`outcome: unknown`), prohibiendo reintentos ciegos.
  * Worker en segundo plano desacoplado con límite global de 1 tarea simultánea.
- `src/gateway_core.py`: declaración de `RUTAS_JOBS` (`POST /jobs`, `GET /jobs`, `DELETE /jobs`).
- `src/gateway_http.py`: enrutamiento seguro de `/jobs`, validación de cabecera
  `Idempotency-Key`, verificación de scopes (`jobs:create`, `jobs:read`, `jobs:cancel`),
  e inicialización de `JobsManager` en `build_server`.
- `examples/cliente_jobs_i5.py`: cliente de referencia y script de demostración
  ejecutable en Python stdlib cubriendo todo el ciclo de vida, idempotencia, 409 y 404.
- `tests/test_jobs_i5.py`: 11 pruebas unitarias e integradas con servidor HTTP real.

## Ronda adversarial interna de verificación

1. **Garantía de idempotencia sin duplicación**:
   - Hipótesis: ¿Puede una desconexión o reintento de cliente provocar la ejecución
     duplicada de un trabajo pesado?
   - Resultado: Verificado en `test_03`. El índice de idempotencia basado en SHA-256
     del JSON canonicalizado (RFC 8785) detecta la solicitud y devuelve inmediatamente
     `202 Accepted` con el mismo `job_id`, sin encolar ni recalcular.
2. **Conflicto ante reutilización de Idempotency-Key con cuerpo distinto**:
   - Hipótesis: ¿Qué ocurre si un cliente o atacante envía una clave ya registrada con
     otro payload?
   - Resultado: Verificado en `test_04`. El gestor detecta la divergencia de hash y
     responde inmediatamente `409 Conflict` (`idempotency_conflict`), protegiendo la
     integridad de la tarea preexistente.
3. **Aislamiento absoluto de privacidad entre proyectos**:
   - Hipótesis: ¿Puede Proyecto Beta inspeccionar el resultado o forzar la cancelación
     de un trabajo de Proyecto Alpha si conoce su `job_id`?
   - Resultado: Verificado en `test_05` y `test_11`. Toda consulta o cancelación
     cruzada devuelve de forma fail-closed `404 Not Found`, sin revelar si el identificador
     existe en el sistema.
4. **Recuperación tras reinicio o caída del proceso**:
   - Hipótesis: ¿Qué ocurre con los trabajos si el servidor colapsa mientras ejecutaba una tarea?
   - Resultado: Verificado en `test_08`. Al arrancar, `startup_recover()` transiciona
     cualquier trabajo en estado `running` a `failed` con error `server_interrupted`,
     garantizando que no se reanuden tareas con estado intermedio desconocido.
5. **No inanición del tráfico interactivo**:
   - Hipótesis: ¿Pueden los trabajos en segundo plano saturar el modelo y bloquear peticiones H/M?
   - Resultado: Verificado. La cola de jobs restringe la ejecución a exactamente 1 worker
     concurrente y 1 trabajo en espera por proyecto, reservando la capacidad del motor.

Veredicto adversarial: **proceed**.

## Capa técnica

```text
id = i5-trabajos-largos-perfil-j-2026-11-07
date = 2026-11-07
time_utc = 18:20:00Z
head_sha = 0069f356eb5f1eec50e6435c249495e86d0663db
model = gemini-3-8-flash
STATE = OK
GATE = suite 299 OK (11 tests I5 nuevos); 5/5 skevi gates OK; check_sizes 1799/1800; check_plans OK; check_reports OK; check_templates OK
PENDING = cierre de Fase I5 y transicion a Fase I6 (evaluacion y benchmarking) segun PLAN LFM3-2
DECISION = proceed
OPERATIONS = commits y merge a main en rama feat/i5-jobs-persistencia-perfil-j autorizados por el Operador
AUTHORITY = autorizacion expresa del Operador 2026-11-07; PLAN-2; SPEC-i5-jobs.md; ADR-012
RISK = bajo: persistencia local atomica, aislamiento por subdirectorio de proyecto y 1 worker maximo sin impacto en interactivo
EVIDENCE
- suite I5 11 pruebas unitarias e integradas Perfil J -> pass
- suite completa 299 pruebas sin regresiones -> pass
- canonicalizacion determinista RFC 8785 -> pass
- garantia de idempotencia 202 con mismo job_id -> pass
- deteccion de conflicto 409 idempotency_conflict -> pass
- aislamiento estricto multi-inquilino 404 fail-closed -> pass
- limite de cola por proyecto 429 -> pass
- cancelacion en cola y terminal -> pass
- recuperacion en startup running a failed -> pass
- cliente de referencia examples/cliente_jobs_i5.py verificado -> pass
- cinco gates skevi pasando en verde -> pass
report_sha256 = 80ad39e807937ee85df42ec76453495eee5521ecd3dcbaa1b28f09317504db08
```
