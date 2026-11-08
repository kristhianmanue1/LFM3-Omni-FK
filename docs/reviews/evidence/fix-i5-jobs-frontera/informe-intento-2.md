# Informe del ejecutor — fix-i5-jobs-frontera, intento 2

- **Fecha:** 2026-11-08
- **Rama:** `agent/fix-i5-jobs-frontera`, base `c50fbf0`
  (reorganización D5 commiteada por el capitán; rebase sobre `192eda1`).
- **Archivos tocados:** `src/jobs_manager.py`, `src/jobs_storage.py`,
  `src/gateway_jobs.py`, `src/gateway_http.py`,
  `docs/specs/SPEC-i5-jobs.md`, `tests/test_jobs_i5.py`,
  `tests/test_jobs_boundary_i5.py`, `tests/test_jobs_intento2_i5.py`
  (nuevo), este expediente.
- **Motor real:** nunca arrancado; `lsof`/`ps` sin listeners ni
  procesos motor/gateway antes/entre/después de cada batería
  (`green-intento-2.txt`).

## 1. Disposición de los hallazgos (mandato-intento-2, ronda 1)

### [BLOCKER-1] Fallo tras `os.link` dejaba el registro sin job y
bloqueaba el reintento → **fixed**

- `commit_registro_idempotencia` distingue fases: un fallo tras el
  `link` (unlink del tmp, fsync del directorio) lanza
  `CommitTrasLinkError` — el commit tiene resultado incierto.
- En `create_job`: si el registro se puede retirar (y retira),
  job y registro fuera y `500 storage_error` — el reintento readmite
  limpio; si el registro NO se puede retirar (unlink falla, registro
  presente), la pareja registro+job constante en disco ES la
  admisión → `202`. Un `202` jamás se apoya en un registro ausente.
- Camino del reintento: registro huérfano (job ausente) se retira y
  la clave readmite (antes: `410` perpetuo); si es irretirable,
  `500 storage_error` explícito.
- Puerta lateral cerrada: fallo de `save_job` posterior al `replace`
  también descarta el job (antes dejaba un huérfano `queued` que
  bloqueaba el reintento con `429` — la reproduje con diagnóstico
  propio antes de corregir).
- Evidencia: `red-intento-2.txt` (29-31 en rojo por la razón
  correcta: reintento `410`, registro huérfano bloqueando);
  `green-intento-2.txt` (29-31 en verde, inyección en cada paso:
  fsync 1-4, replace, link). Regresiones de la ronda adversarial:
  test_40 (fsync sostenido #4+#5: una sola ejecución, un registro) y
  test_30/31.

### [HIGH-2/3/7] Concurrencia entre procesos → **fixed** (por diseño D1)

- D1: `JobsStorage.tomar_cerrojo_instancia()` toma `flock` exclusivo
  y no bloqueante sobre `<jobs_dir>/.instance.lock` AL ARRANCAR y
  antes de cualquier recuperación. Segunda instancia:
  `JobsDirOcupado` con el directorio y la causa en el mensaje, sin
  worker ni `startup_recover`. `stop()` libera el cerrojo; un
  arranque que falle tras tomarlo también lo libera (ronda
  adversarial: fd huérfano). `main()` del gateway traduce la
  excepción a `BLOQ` + exit 1.
- `startup_recover` sólo corre con el cerrojo tomado (implícito en
  D1: no hay segunda instancia).
- Contar+commit bajo `self.lock` (una instancia): test_28 — 6 hilos,
  claves distintas, mismo proyecto: exactamente un `202` y cinco
  `429 queue_limit_per_project_exceeded`.
- Evidencia: test_27 (segunda instancia falla cerrada; un `running`
  vivo de la primera no es tocado), test_28, test_19 del boundary
  (reescrito a la topología D1; la segunda instancia falla y la
  primera ejecuta cada job exactamente una vez).

### [HIGH-4] Excepción no-`ErrorV2` dejaba el job en `queued` → **fixed**

- `_worker_loop`: ante defecto inesperado, `_cerrar_por_defecto`
  hace la transición durable a `failed` con
  `worker_internal_error` desde cualquier estado no terminal
  (`queued|running|cancellation_pending`); si el disco también
  falla, stderr + el arranque siguiente reconcilia. El test afirma
  el estado final, no sólo el hilo vivo.
- Evidencia: test_32 (estado final `failed/worker_internal_error`,
  worker vivo, 0 ejecuciones sin admisión), test_43 (rama
  `running`), test_26 del boundary adaptado (flock liberado,
  comprobado tomando el cerrojo directamente).

### [HIGH-5] Espera por admisión sin fin → **fixed**

- `admission_deadline` persistido por job (`ESPERA_ADMISION_S = 60`,
  §J «60 s de cola»). El worker lo comprueba antes de pedir admisión
  y otra vez justo tras adquirirla (si venció durante la espera, se
  libera el slot concedido y el job no se ejecuta tarde — hallazgo
  de la ronda adversarial). Agotado: `failed/admission_timeout`.
- Saturación sostenida probada con reloj del sistema adelantando el
  deadline en disco, sin `sleep` reales largos (dos proyectos,
  dispatcher que nunca concede).
- Evidencia: test_33 (deadline presente, agotamiento por proyecto),
  test_41 (vence DURANTE la espera: 0 ejecuciones, concesión
  liberada).

### [HIGH-6] Purga y temporales → **fixed** (según D4)

- Barrido periódico dentro del bucle del worker (`get(timeout=1.0)`
  → `_barrido_si_toca()`), sin hilo nuevo: vencidos a tombstone,
  temporales huérfanos `*.tmp.*` (edad > `tmp_edad_s`, 300 s por
  defecto — un tmp legítimo vive milisegundos) y claims sin dueño
  (job inexistente o terminal; el claim con flock sostenido se
  respeta), todo bajo el cerrojo de instancia.
- `get_job` ya no presenta como lograda una purga que falló: el
  `410` sigue (el resultado no se entrega tras TTL), pero el fallo
  se cuenta (`fallos_purga`) y se imprime a stderr; el barrido
  también cuenta e imprime sus fallos (ronda adversarial) y
  reintenta.
- Evidencia: test_34 (barrido sin tráfico, tombstone sin payload),
  test_35 (tmp sensible huérfano fuera; tmp en curso respetado),
  test_36 (claims: fantasma y terminal fuera, sostenido respeta),
  test_37 (410 sin tombstone falso + `fallos_purga` + reintento),
  test_42 (fallos del barrido contados).

### [MED-8] `operation` no cadena → **fixed**

- `create_job` comprueba `isinstance(operation, str)` y allowlist
  antes de usarla: `400 unsupported_operation` para lista, entero,
  dict o `None`; la conexión ya no se rompe por `TypeError`.
- Evidencia: test_38 (vía HTTP, los cuatro tipos, 400 controlado;
  en RED la conexión se rompía — traza en `red-intento-2.txt`).

### [MED-9] `build_server` y tests tocaban `run/jobs` y 8091 → **fixed**

- `build_server(..., jobs_dir=None)`: sin `jobs_dir` NO se construye
  `JobsManager` ni se crea `run/jobs`; `/jobs` responde
  `501 not_implemented` hasta asignación. `main()` pasa el `jobs_dir`
  explícito (`LFM3_JOBS_DIR` o `run/jobs`) y traduce `JobsDirOcupado`
  a `BLOQ`.
- Todos los tests de `/jobs` inyectan `jobs_dir` temporal y backend
  falso en la construcción; `JobsManagerDirectTests` usa dispatcher
  sin presupuesto (los jobs quedan `queued`, nada toca el 8091). El
  residuo `run/jobs/{data,idempotency}` (vacío, del intento 1) se
  retiró y ya no se recrea.
- Evidencia: test_39 (clon nuevo: sin `run/jobs`, `jobs_manager`
  `None`, 501), `green-intento-2.txt` final (sin creación).

### [MED-10] `test_09` con backend falso controlado → **fixed**

- `test_09` reescrito: POST → 202; sincroniza a terminal y afirma
  `succeeded` con `result.text`/`complete`; DELETE sobre terminal →
  `already_terminal` **con `target_state == "succeeded"`** (no
  comodín). Rama queued determinista con proyecto-epsilon (token
  bucket que nunca concede): DELETE inmediato → `accepted`/`cancelled`
  y estado final `cancelled` (SPEC-i5 §2.3).
- La guarda de motor se retiró (autorizado por el capitán): el test
  ya no usa 8091; también se quitaron `probe_engine` y las constantes
  de sonda. `setUpClass` de la clase usa backend falso propio y
  `jobs_dir` temporal.
- Evidencia: `green-intento-2.txt` (test_09 en verde sin motor).

### [MED-12] Contención de tamaño → **fixed** (cubierta por D5)

- D5 ejecutado en el primer paso (commit `c50fbf0` del capitán;
  `refactor-listo.txt`). Tras los hallazgos, `jobs_manager.py` volvió
  a exceder 800 y se partió otra vez por dominio: el cerrojo de
  instancia y la limpieza del árbol (tmp/claims) viven en
  `jobs_storage.py`. Todos los archivos ≤ 800 líneas y ≤ 88 columnas.

## 2. Aplicación de las decisiones del Operador (D1–D5)

- **D1:** una instancia por `jobs_dir` (`.instance.lock`, flock EX|NB
  al arrancar, antes de la recuperación); error explícito con
  directorio y causa; sin worker ni recovery en la segunda instancia;
  `stop()` y los fallos de arranque liberan el cerrojo. Resuelve
  HIGH-2/3/7 por topología en vez de coordinación N-instancias.
- **D2:** `_contar_encolados` vuelve al literal de SPEC-i5:75 (sólo
  `state == "queued"`), verificado sin editar esa línea del SPEC. Sin
  carrera: una instancia (D1) y contar+commit bajo `self.lock`; los
  tests directos usan dispatcher sin presupuesto para mantener jobs
  `queued` de forma determinista.
- **D3:** aplazado y registrado como **DESVIACIÓN DECLARADA** (§3 de
  este informe).
- **D4:** barrido periódico dentro del bucle del worker (sin hilo
  nuevo) + limpieza de `*.tmp.*` huérfanos y claims bajo el cerrojo
  de instancia.
- **D5:** reorganización pura ejecutada y detenida en
  `FIN fix-i5-2-refactor` (commit del capitán). El intento 2 no
  añadió compresión: sin `;`, ≤ 88 columnas, estilo del vecino.

## 3. Desviación del cifrado (D3, obligatoria)

- **DESVIACIÓN DECLARADA** del contrato
  `docs/contracts/perfiles-servicio-v2.md` §J («Persistencia cifra
  resultados y controla accesos»): la persistencia protege con
  permisos 0600/0700, **sin cifrado en reposo**. Registrada en
  `docs/specs/SPEC-i5-jobs.md` §4 (con corrección de la línea que
  prometía «cifrado/aislado», procedencia y fecha) y aquí. Fijada
  como **requisito bloqueante para exponer `/jobs`** más allá del
  modo de prueba. No se implementó cifrado (orden expresa D3).

## 4. Rondas adversariales

- **Propia:** relectura del diff completo; diagnóstico reproducido
  del 429 por huérfano `queued` antes de corregir.
- **Contexto fresco real** (subagente revisor, disparadores 1–4 de
  `04` §5.3): veredicto inicial `fix-and-retry` con 1 BLOCKER, 2 MED,
  5 LOW. Todos corregidos:
  - **BLOCKER** (doble ejecución con fsync sostenido): `retirar_registro`
    distinguía mal «unlink falló» de «unlink OK, fsync falló» → un
    `202` sin registro y el reintento ejecutaba dos veces. Semántica
    nueva: `True` = registro ausente tras la llamada (reintento
    limpio); `False` = sigue presente (el 202 se apoya en él).
    Regresión test_40. Re-sonda del revisor: 1 ejecución, mismo
    `job_id` en replay.
  - **MED** deadline vencido durante la espera de admisión →
    re-chequeo tras `_admitir` liberando el slot (test_41).
  - **MED** barrido silenciaba fallos de purga → cuenta e imprime
    (test_42).
  - **LOW**: flock liberado si el arranque falla tras tomarlo;
    retorno de `retirar_registro` bifurcado en el huérfano;
    `eliminar_job` audible en stderr; dos líneas >88 partidas.
  - Re-ronda del mismo revisor con sus sondas: **proceed**, 8/8
    cerrados. Nota residual suya: `test_41` podría dar un falso rojo
    en una máquina muy lenta (ventana de 0,6 s); aceptado como
    seguimiento.

## 5. Cambios por archivo

- `src/jobs_storage.py` (279): `CommitTrasLinkError` y
  `JobsDirOcupado`; `tomar_cerrojo_instancia` (D1);
  `commit_registro_idempotencia` con fases (BLOCKER-1);
  `retirar_registro` sin ambigüedad; `eliminar_job` audible;
  `limpiar_temporales` y `limpiar_claims_huerfanos` (D4).
- `src/jobs_manager.py` (793): cerrojo de instancia con liberación en
  fallos de arranque; MED-8; reconciliación de huérfanos y rama
  `CommitTrasLinkError`; descarte del job en fallos post-replace;
  `admission_deadline` y sus dos chequeos (HIGH-5); `_cerrar_por_defecto`
  no-terminal (HIGH-4); `_barrido_si_toca` (D4); `fallos_purga`
  contado en `get_job` y en el barrido; conteo D2 literal.
- `src/gateway_jobs.py` (127): `construir_jobs_manager` con
  `jobs_dir` inyectable (MED-9).
- `src/gateway_http.py` (742): `build_server(..., jobs_dir=None)`
  sin JobsManager por defecto; `main()` pasa `jobs_dir` explícito y
  traduce `JobsDirOcupado`.
- `docs/specs/SPEC-i5-jobs.md`: D2 verificada sin edición; D3
  desviación declarada + corrección de la línea del cifrado.
- `tests/test_jobs_intento2_i5.py` (nuevo, 776): tests 27-43 — 13
  propiedades del mandato + 4 regresiones de la ronda adversarial.
- `tests/test_jobs_i5.py` (460): setUp directo con dispatcher sin
  presupuesto y test_08 con `stop()` previo (D1/D2/MED-9);
  `setUpClass` con backend falso y `jobs_dir` inyectado; `test_09`
  reescrito (MED-10) sin guarda de motor ni 8091.
- `tests/test_jobs_boundary_i5.py` (795): `setUpClass` con
  `jobs_dir` inyectado; test_19 reescrito a D1; test_26 adaptado a
  HIGH-4.

## 6. Incidente del proceso (registro, pedido del capitán)

- Durante el RED inicial, `test_39` colgó el proceso: el test llamaba
  `servidor.shutdown()` sin haber arrancado `serve_forever`
  (`socketserver.shutdown()` espera un evento que sólo el loop
  setea); el timeout del shell terminó el proceso (PID 93901, ya
  extinto; sin procesos huérfanos; nada requirió `kill`). Diagnóstico
  confirmado por el capitán; corrección: `serve_forever` en hilo
  daemon y `shutdown()` en el `finally` sólo con el loop arrancado.
  Lección registrada: nunca `shutdown()` sin loop sirviendo.

## 7. Riesgos residuales (aceptados con nombre)

1. **Durabilidad degradada ante fallo de fsync**: un `fsync` fallido
   deja la escritura en page cache; el proceso la ve, un crash del
   host podría revertirla. Los caminos de reconciliación (huérfanos,
   `admission_unconfirmed`, purga que reintenta) son fail-closed.
2. **`ESPERA_ADMISION_S` fijo (60 s)**: sin deadline distinto por
   operación ni reloj inyectable en producción (los tests adelantan
   el deadline en disco). §J fija 60 s de cola; cambiarlo es decisión
   de contrato.
3. **Barrido con cadencia del worker**: la purga periódica ocurre
   cada `INTERVALO_BARRIDO_S` (30 s) cuando el worker respira; un
   worker saturado sin pausa la retrasa (nunca la cancela: get,
   admisión y arranque también barren).
4. **`test_41` sensible a máquina muy lenta** (nota del revisor):
   ventana de 0,6 s; falso rojo posible, nunca falso verde.
5. **Jobs legados sin `admission_deadline`**: sin límite de admisión
   (conservador con historia desconocida); los nuevos siempre lo
   llevan.
6. **Supuestos de plataforma**: flock, hardlinks y POSIX (APFS/ext4
   sí; exFAT no → fail-closed).

## 8. Decisiones para el Operador (recomendación primero)

### 8.1 Cifrado en reposo (D3 ya decidido el aplazamiento)

- **Recomendada:** mantener el aplazamiento con la desviación
  registrada y el requisito bloqueante para exponer `/jobs`; cifrar
  (AES-GCM, clave fuera del árbol) como tarea propia ANTES de
  cualquier exposición multi-consumidor.
- **Por qué:** §J lo exige y 0600/0700 no protege frente al operador
  del host ni a copias del volumen; el payload lleva datos de
  clientes.
- **Coste de la otra** (cifrar ya): una tarea más antes de cerrar
  I5, gestión de clave y migración de historia inexistente aún (vent
  aja corta); razonable si se anticipa la exposición.

### 8.2 Cadencia del barrido (D4)

- **Recomendada:** 30 s por defecto, parámetro inyectable como está.
- **Por qué:** proporcional (una vuelta por segundo del worker), sin
  hilo ni temporizador propios; los tests usan 0,2 s.
- **Coste de la otra** (bajarlo): más E/S de escaneo con colas
  grandes; subirlo alarga la ventana de datos vencidos en disco sin
  tráfico.

## 9. Reporte de fase (dos capas)

```text
id = fix-i5-jobs-frontera-e2
date = 2026-11-08
time_utc = 20:05:00Z
head_sha = c50fbf0 (más diff de trabajo sin commit, mandato §5)
model = zai-coding-plan/glm-5.3
STATE = OK
GATE = mandato-intento-2: RED (red-intento-2.txt, 12 fallos por razón correcta)
  + GREEN (batería §3 x2 + suite completa x2 con lsof/ps limpios, green-intento-2.txt)
  + gates x3 + git diff --check + status
  + ronda adversarial de contexto fresco con re-sonda (proceed, 8/8)
PENDING = ninguno del ejecutor; capitán: commit del intento 2 y revisor fresco de otra familia
EVIDENCE
- python3 -m unittest tests.test_jobs_intento2_i5 (RED) -> 13 tests: 12 fallos/errores por la razón de cada hallazgo; 1 pass (28) [pass]
- python3 -m unittest <batería §3, 10 módulos> x2 -> 158 OK, 158 OK [pass]
- python3 -m unittest discover -s tests -t . x2 -> 365 OK (skipped=1) ambas [pass]
- lsof/ps antes/entre/después -> sin listeners 8091/8092/8443 ni procesos motor/gateway [pass]
- python3 scripts/check_sizes.py -> OK (todos <= 800 líneas) [pass]
- python3 scripts/check_plans.py -> OK 2 planes [pass]
- python3 scripts/check_reports.py -> OK [pass]
- git diff --check -> sin salida [pass]
- re-sonda del revisor fresco: doble ejecución 1, deadline 0 ejecuciones, flock libre, huérfano irretirable 500 [pass]
DECISION = proceed
```

*La capa humana de este informe es todo lo anterior; ante contradicción,
gana la capa técnica del bloque. Sin commit (mandato §5). La suite
completa se ejecutó con la autorización expresa del capitán
(2026-11-08), que levantó la prohibición vigente del mandato original.*
