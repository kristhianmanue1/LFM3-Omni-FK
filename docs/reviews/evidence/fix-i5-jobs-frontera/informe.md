# Informe del ejecutor — fix-i5-jobs-frontera, intento 1

- **Fecha:** 2026-11-08
- **Rama:** `agent/fix-i5-jobs-frontera` (base `main` `60c6568`)
- **Archivos tocados:** `src/jobs_manager.py`, `src/gateway_http.py`,
  `tests/test_jobs_boundary_i5.py` (nuevo), `tests/test_jobs_i5.py`
  (edición mínima), este expediente.
- **Motor real:** nunca arrancado; `lsof` sin listeners en
  8091/8092/8443 antes y después de cada batería (`green.txt`).

## 1. Disposición de los hallazgos del mandato

### BLOCKER-1 — /jobs sin frontera ni scope de modalidad → **fixed**

- `gateway_http.py` `/jobs`: exige `jobs:create` **más** el scope de la
  modalidad de la operación (`SCOPE_POR_OPERACION`) **más** los scopes
  derivados del contenido del payload (`_determinar_scopes_chat`, la
  misma regla que H) y valida el cuerpo con `validar_payload` (con
  inspector de video) antes de `create_job`. El sobre completo también
  se valida: raíz objeto y `ttl_seconds` entero en 60..86400.
- `jobs_manager.py` `_execute_single_job`: la salida del backend se
  valida en la frontera antes de persistir — forma cerrada de
  `choices`, `content` cadena, `finish_reason == "stop"`
  (`_extraer_salida`) y `validar_salida` contra el esquema cuando el
  payload trae `response_format`. Cualquier fallo termina en `failed`
  explícito (`_fallar`); nunca `succeeded`.
- Evidencia: `red.txt` (tests 06-08, 12-13 fallan hoy del código viejo),
  `green.txt` (los mismos en verde, 2 corridas).

### BLOCKER-2 — 202 sin registro durable → **fixed**

- Escrituras durables: tmp `0600` + bucle de escritura + `fsync` +
  `os.replace` + `fsync` del directorio (`_volcar_tmp_durable`,
  `_reemplazar_durable`). Los `OSError` se propagan: `create_job`
  responde 500 `storage_error`, jamás 202 sin escritura constatada.
- Commit recuperable: el job se escribe primero y el registro de
  idempotencia se crea después con `os.link` exclusivo — el registro
  **es** el punto de admisión. Si el commit falla, el job se retira
  (rollback) y, si el borrado fallara, el arranque lo reconcilia.
- Arranque fail-closed: un `queued` sin registro que lo confirme pasa a
  `failed` (`admission_unconfirmed`) y jamás se ejecuta.
- Evidencia: tests 16-18 (inyección de `OSError` en job y registro;
  huérfano sin registro nunca ejecutado, cuenta de backend 0).

### HIGH-1 — sin reclamo ni presupuesto compartido → **fixed**

- Reclamo atómico entre procesos: `flock` exclusivo no bloqueante por
  job (`_reclamar`/`_soltar_reclamo`); una segunda instancia no puede
  reclamar el mismo job.
- Admisión compartida con H/M: el worker pasa por el
  `FairQueueDispatcher` del gateway con los límites del proyecto
  (`build_server` cablea `dispatcher` + `rate_limit_lookup`). Sin
  presupuesto, el job vuelve a la cola y reintenta; nunca se ejecuta
  sin admisión.
- Evidencia: test 19 (dos instancias sobre el mismo `data_dir` con la
  carrera ensanchada deliberadamente: cada job se ejecuta exactamente
  una vez — en el RED, dos veces); test 20 (dispatcher grabador
  registra acquire/release).

### HIGH-2 — retención y confidencialidad → **fixed** (cifrado aparte)

- Purga verificable: al expirar, el job se reduce a un tombstone sin
  `payload` ni `result` (get_job del dueño, barrido de arranque y
  barrido en cada admisión). El 410 es estable tras la purga y
  `DELETE` responde `already_terminal` sobre lo purgado.
- Permisos: directorios `0700` y archivos `0600` en data, idempotency
  y claims.
- `expires_at` conforme a §J: se recalcula desde el estado terminal
  (`_cerrar` → `_recalcular_expiracion`); el registro de idempotencia
  vive 24 h (ventana del tombstone, §J).
- El cifrado en reposo NO se implementa (mandato §HIGH-2): decisión
  para el Operador — ver §5.

### HIGH-3 — idempotencia no RFC 8785, duplicados aceptados → **fixed**

- Serializador propio: números en forma ES6 (JSON.stringify, RFC 8785
  §3.2.2.3), claves ordenadas por unidades de código UTF-16 (no por
  punto de código), escapes mínimos de cadena, enteros acotados al
  rango doble, no finitos rechazados. Fixtures numéricos generados
  contra Node.js v26.7.0 (V8) el 2026-11-07.
- `_leer_json_post` usa `object_pairs_hook` que rechaza claves
  duplicadas con 400 controlado (código `invalid_json`, detalle
  `duplicate_key`, mensaje con el campo).
- Evidencia: tests 01-05 y 09-10; el revisor adversarial ejecutó un
  fuzz de 78.513 números, 3.629 cadenas hostiles y 3.000 órdenes de
  claves contra V8: 0 divergencias byte a byte.

## 2. Ronda adversarial (propia + contexto fresco; `04` §5.3)

Ronda propia sobre el diff con el catálogo de defectos, más un revisor
de contexto fresco (subagente) que devolvió `fix-and-retry`. Disposición
de sus hallazgos tras la corrección (checks repetidos: 141 tests × 2):

- **[HIGH] sobre de /jobs sin validar** (cuerpo no-objeto o
  `ttl_seconds` anómalo rompían la conexión) → **fixed**: validación
  del sobre completo en la frontera (tests 23-24).
- **[HIGH] 410 inestable tras la purga** (el tombstone perdía
  `expires_at`; el 2º GET daba 200; DELETE respondía `pending` sobre
  lo purgado) → **fixed**: el tombstone conserva `expires_at`,
  `expired` es terminal para cancel_job (test 25).
- **[MED] límites de cola check-then-act entre instancias** →
  **justificado** por escrito: topología vigente es un único gateway
  (decisión del Operador 2026-11-02, sólo localhost); el parche
  (flock de admisión global) queda propuesto en §5.3.
- **[MED] worker moría con excepción no-`ErrorV2` y fugaba el flock**
  → **fixed**: `_admitir` dentro del `try/finally` del reclamo;
  `except Exception` con traza a stderr; el worker sobrevive y el
  reclamo siempre se libera (test 26).
- **[MED] purga sólo al arrancar y en GET** → **fixed parcial**:
  barrido también en cada admisión (libera además plazas de cola).
  Residual documentado en §4 (sin tráfico no hay barrido temporal).
- **[LOW] `_resolver_rival` sin guarda de tombstone** → **fixed**
  (misma guarda 410 que el camino principal).
- **[LOW] gates.txt desactualizado** → **fixed** (regenerado con el
  estado final).

Hallazgo adicional cerrado durante la re-verificación: la carrera
admisión-vs-reclamo del límite por proyecto (expuesta por el test 06
existente) se cierra contando jobs **no terminales** del proyecto
(`queued|running|cancellation_pending`) — ver decisión §5.2.

## 3. Propiedades verificadas

| Propiedad | Estado | Evidencia |
|---|---|---|
| Scope de modalidad exigido (text y vision) | pass | tests 06-07; red.txt/green.txt |
| Payload fuera del dialecto rechazado | pass | test 08 |
| Sobre no-objeto y ttl anómalos → 400 | pass | tests 23-24 (regresión) |
| Clave duplicada (top y anidada) → 400 con campo | pass | tests 09-10 |
| Salida truncada → failed, nunca éxito | pass | test 12 |
| Salida fuera de esquema → failed | pass | test 13 |
| Salida válida → succeeded, complete true | pass | test 14 (control) |
| expires_at cuenta desde el terminal (§J) | pass | test 15 |
| OSError en escritura de job → 500 sin 202 | pass | test 16 |
| OSError en commit de registro → 500 sin restos | pass | test 17 |
| Job sin registro jamás se ejecuta | pass | test 18 |
| Dos instancias: cada job una vez | pass | test 19 (RED: 2 veces) |
| Worker pasa por dispatcher compartido | pass | test 20 |
| Worker sobrevive a dispatcher hostil | pass | test 26 (regresión) |
| Purga a tombstone sin payload/result | pass | test 21 |
| 410 estable tras purga; DELETE terminal | pass | test 25 (regresión) |
| Permisos 0600/0700 | pass | test 22 |
| Números RFC 8785 forma ES6 | pass | tests 01, 02; fuzz V8 0 divergencias |
| Claves por UTF-16; escapes mínimos | pass | tests 03, 04 |
| Suite focal (37) y batería §3 (141) ×2 | pass | green.txt |
| Gates x3, diff --check, status limpio | pass | gates.txt |

## 4. Riesgos residuales (aceptados con nombre)

1. **Límites de cola entre procesos** (MED justificado): dos instancias
   sobre el mismo `data_dir` pueden admitir dos jobs no terminales del
   mismo proyecto en la misma ventana. Topología vigente: 1 gateway.
2. **Barrido de retención sin tráfico**: un job expirado que nadie
   consulta y sin nuevas admisiones ni reinicio conserva el payload en
   disco hasta uno de esos eventos (mismo régimen on-access que ya
   tenían los registros de idempotencia).
3. **Reintento de admisión sin deadline**: bajo saturación sostenida de
   H/M un job puede esperar en cola indefinidamente (la cancelación
   sigue disponible y correcta).
4. **Reintentos del worker consumen tokens** del rate limiter del
   proyecto (cadencia ≥ 0,5 s; con timeout de admisión de 60 s el ritmo
   real es bajo).
5. **Jobs legados** (pre-fix, sin `idempotency_key` en el job) quedan
   `admission_unconfirmed` al arrancar: fail-closed; el cliente debe
   reenviar con clave nueva.
6. **Supuestos de plataforma**: `flock` y `os.link` requieren POSIX con
   hardlinks (APFS/ext4 sí; exFAT no → 500 `storage_error` fail-closed).

## 5. Decisiones para el Operador (recomendación primero)

### 5.1 Cifrado en reposo de jobs (exigido por el mandato)

- **Recomendada:** cifrar prompts y resultados en reposo (AES-GCM,
  clave gestionada fuera del árbol: llavero del host o variable de
  entorno inyectada por servicio) antes de cualquier exposición más
  allá de loopback multi-consumidor.
- **Por qué:** §J ordena «Persistencia cifra resultados y controla
  accesos»; los permisos 0600/0700 recién añadidos protegen frente a
  otros usuarios del host, no frente al operador del host ni a copias
  del volumen; el payload contiene datos de clientes.
- **Coste de la otra** (mantener en claro): cero dependencias hoy, pero
  cualquier fuga del volumen `run/jobs` expone prompts y resultados, y
  la migración futura tendrá que re-cifrar historia.

### 5.2 Semántica del límite por proyecto (SPEC vs implementación)

- **Recomendada:** aceptar la semántica implementada — «1 job **no
  terminal** por proyecto» (SPEC §2.1 decía literal «1 job queued») —
  y reflejarla en el SPEC en su próxima edición.
- **Por qué:** el conteo literal de `queued` tiene una carrera
  check-then-act con el reclamo del worker que el test 06 existente ya
  exponía (202 donde el contrato promete 429); contar no terminales es
  verificable de forma determinista y más protector del motor.
- **Coste de la otra** (volver al literal): reaparece la carrera y el
  límite deja de ser establemente comprobable.

### 5.3 Topología multi-instancia

- **Recomendada:** mantener un único proceso gateway (decisión vigente
  2026-11-02) y, si algún día se autorizan N instancias sobre el mismo
  `jobs_dir`, añadir antes un flock de admisión global alrededor de
  contar+commit (~10 líneas; riesgo nº1).
- **Por qué:** reclamo de ejecución y commit de idempotencia ya son
  atómicos entre procesos; sólo el conteo de límites no lo es.
- **Coste de la otra** (habilitar multi-instancia hoy): dos admisiones
  simultáneas por proyecto posibles (límite §J violable bajo carrera).

### 5.4 Barrido temporal de retención

- **Recomendada:** mantener el barrido on-access (GET + admisión +
  arranque), proporcional al tráfico y sin temporizadores.
- **Por qué:** con tráfico normal la purga ocurre en la primera
  admisión o consulta posterior; un temporizador añade un hilo y
  complejidad de reloj para cubrir sólo reposos largos sin tráfico.
- **Coste de la otra** (temporizador): cobertura temporal estricta del
  TTL incluso sin tráfico, a cambio de complejidad y líneas de
  presupuesto (archivos al límite de 800).

## 6. Cambios por archivo

- `src/jobs_manager.py` (800 líneas): serializador RFC 8785 completo;
  persistencia durable (tmp 0600, fsync, rename, fsync de directorio);
  commit `os.link` del registro de idempotencia (24 h); reconciliación
  fail-closed al arranque; reclamo `flock`; admisión vía dispatcher
  compartido; validación de salida (completitud y esquema) antes de
  persistir; retención §J (expires desde terminal, tombstone, purga
  on-access/arranque/admisión); permisos 0700/0600; conteo de plaza
  sin carrera; worker robusto a fallos inesperados (stderr + reclamo
  siempre liberado).
- `src/gateway_http.py` (800 líneas): `SCOPE_POR_OPERACION`;
  `/jobs` valida el sobre completo, exige `jobs:create` + scope de
  modalidad + scopes de contenido y pasa el payload por
  `validar_payload`; `_leer_json_post` rechaza claves duplicadas con
  400 controlado; `build_server` cablea dispatcher y límites por
  proyecto en el JobsManager.
- `tests/test_jobs_boundary_i5.py` (nuevo, 800 líneas): 26 tests — 18
  propiedades RED-first + 3 controles positivos + 4 regresiones de la
  ronda adversarial (23-26). Backend falso en puerto efímero y data_dir
  temporal siempre; nunca `run/jobs` ni 8091.
- `tests/test_jobs_i5.py`: una sola edición mínima en test_09
  (`already_terminal` también es respuesta de contrato cuando el job
  ya terminó — carrera legítima con backend caído). Guarda de motor e
  imports intactos (rama `agent/fix-tests-hermeticos` los modifica).

## 7. Reporte de fase (dos capas)

```text
id = fix-i5-jobs-frontera-e1
date = 2026-11-08
time_utc = 06:08:09Z
head_sha = 60c6568b2e98a6666ea6400f89815eecb2f76094
model = zai-coding-plan/glm-5.3
STATE = OK
GATE = mandato fix-i5 §4: RED (red.txt, 18 propiedades), GREEN (141 tests x2 + lsof limpio), gates x3 + git diff --check + status, ronda adversarial propia + contexto fresco con hallazgos corregidos o justificados
PENDING = ninguno del ejecutor; el capitán convocará al revisor fresco de otra familia (mandato §4.4)
EVIDENCE
- python3 -m unittest tests.test_jobs_boundary_i5 (RED, pre-fix) -> 18 failures por la razon correcta (doble ejecucion 2!=1; expires 57.5<59; 202 con OSError; etc.) [pass]
- python3 -m unittest tests.test_jobs_i5 tests.test_jobs_boundary_i5 -> 37 tests OK [pass]
- python3 -m unittest (bateria §3: 9 modulos, salvo test_piloto_live_i2) x2 -> 141 OK, 141 OK (green.txt) [pass]
- lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(8091|8092|8443) ' antes y despues -> sin listeners [pass]
- python3 scripts/check_sizes.py -> OK 307 archivos, ruta 1799/1800 [pass]
- python3 scripts/check_plans.py -> OK 2 planes [pass]
- python3 scripts/check_reports.py -> OK 25 reportes, 1 exento [pass]
- git diff --check -> sin salida, exit 0 [pass]
- git status --porcelain -> solo los 4 archivos del alcance + expediente [pass]
- node v26.7.0 (V8) fuzz del revisor: 78513 numeros, 3629 cadenas, 3000 ordenes de claves vs canonical_json_rfc8785 -> 0 divergencias [pass]
DECISION = proceed
report_sha256 = ecaeb760207642820eed7af9d084bce8d8f90acef33dd8ab141d221ea1798e7b
```

*La capa humana de este informe es todo lo anterior; ante contradicción,
gana la capa técnica del bloque. Sin commit (mandato §5).*
