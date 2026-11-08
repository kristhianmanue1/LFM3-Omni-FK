# Informe del ejecutor — fix-i5-jobs-frontera, intento 3

- **Fecha:** 2026-11-08
- **Rama:** `agent/fix-i5-jobs-frontera`, HEAD `1511764` (sin commit,
  mandato §Informe).
- **Archivos tocados:** `src/jobs_manager.py` (796/81),
  `src/jobs_storage.py` (313/80), `tests/test_jobs_intento3_i5.py`
  (nuevo, 341/76), este expediente.
- **Motor real:** nunca arrancado; fotos `lsof`/`ps`/`run/jobs` antes,
  entre y después de ambas corridas, sin listeners 8091/8092/8443, sin
  procesos motor/gateway y sin `run/jobs` (`green-intento-3.txt`).
- **Diseño:** sin cambios; D1–D5 intactas y no reabiertas.

## 1. Disposición de los 7 hallazgos (ronda 2, revi5c)

### [MED-1] `cancellation_pending` no se reconciliaba tras crash →
**fixed**

- `startup_recover` trata `running` y `cancellation_pending` igual:
  transición durable a `failed` con `server_interrupted`
  (`jobs_manager.py:164-171`). Un job vencido en esa ventana purga por
  la vía de siempre (`_cerrar` → tombstone).
- Evidencia: `test_44` — job `cancellation_pending` en disco con su
  registro; tras arrancar, el estado EN DISCO es `failed` con
  `server_interrupted`. En RED quedó `cancellation_pending` para
  siempre (`red-intento-3.txt`).

### [MED-2] D2 sin control positivo → **fixed** (test, no código)

- `test_45`: con un job `running` (y en otro subtest
  `cancellation_pending`) del proyecto en disco, un segundo POST se
  **admite** (202), `SPEC-i5:75` literal. Verde contra HEAD (el conteo
  ya es el correcto); la **sonda de reversión** al conteo de no
  terminales del intento 1 lo pone en rojo en ambos subtests (429 ≠
  202, `rc_sonda=1`, `red-intento-3.txt`): el control muerde.
- Sin cambio de producción: D2 ya conforme; lo que faltaba era el
  test que atara el conteo al contrato.

### [MED-3] `stop()` liberaba el cerrojo con el worker vivo → **fixed**

- `stop()` sólo cierra el fd de instancia si el hilo terminó de
  verdad; vivo tras el plazo, imprime el motivo a stderr
  («worker vivo tras stop(timeout=…); no se libera el cerrojo de …
  (fail-closed, D1)») y NO libera el cerrojo. Es re-llamable: cuando
  el worker murió, una segunda llamada cierra el fd
  (`jobs_manager.py:128-147`).
- Evidencia: `test_46` — backend lento (4 s), job `running`,
  `stop(timeout=0.3)` con el hilo vivo; una segunda instancia falla
  con `JobsDirOcupado` mientras el worker viva; tras morir el hilo y
  re-llamar `stop()`, la segunda instancia arranca. En RED la segunda
  instancia arrancaba sin error (la reproducción exacta del revisor).

### [LOW-4] `ENOLCK` diagnosticado como «otra instancia» → **fixed**

- `tomar_cerrojo_instancia` bifurca por `errno`
  (`jobs_storage.py:208-231`): `EWOULDBLOCK`/`EAGAIN` → «ya está en
  uso por otra instancia»; el resto → «no admite el cerrojo de
  instancia en este sistema de archivos», con la causa cruda entre
  paréntesis. Ambos caminos fallan cerrados.
- Evidencia: `test_47` (ENOLCK: mensaje con «sistema de archivos», SIN
  «otra instancia», nombra el `jobs_dir`; EWOULDBLOCK: «otra
  instancia») y `test_47b` (ENOLCK en el arranque de `JobsManager`:
  `JobsDirOcupado` y un `queued` preexistente intacto — sin worker ni
  recuperación). En RED sólo mordía el diagnóstico; el fail-closed ya
  era correcto y `test_47b` pasaba (así se declaró en la revisión).

### [LOW-5] `202` en la rama irretirable tras `os.link` → **fixed**

- La rama `CommitTrasLinkError` responde siempre `500 storage_error`:
  nunca un 202 sobre durabilidad no confirmada (estándar §1 principio
  5; §J «admisión sólo tras persistir… atómicamente»). Retira el
  registro si el disco lo permite (reintento limpio) y descarta el job
  siempre; si el registro es irretirable, el reintento reconcilia por
  la vía del huérfano (`jobs_manager.py:326-341`).
- Evidencia: `test_48` — fsync n.º 4 (post-link) fallando y
  `retirar_registro` devolviendo `False`: `500`/`storage_error` (en
  RED: `202`); el reintento con la misma clave readmite y el job
  llega a `succeeded`.
- **Incidente del proceso (transparente):** mi primera versión invertía
  la condición y sólo descartaba el job cuando el retiro FALLABA; el
  caso de retiro con éxito dejaba un `queued` huérfano que bloqueaba
  el reintento con 429. Lo cazó la **suite completa** (test_29 y
  test_40 del intento 2 en rojo en la primera corrida GREEN);
  corregido a «descartar siempre» y suite re-corrida completa ×2 en
  verde. Es la demostración de para qué manda el mandato las dos
  corridas.

### [LOW-6] purga de `get_job` fuera de `self.lock` → **fixed**

- `get_job` toma `self.lock` alrededor de `_purgar_job`
  (`jobs_manager.py:417-422`): el tombstone no puede intercalarse con
  la transición `running` de `_marcar_running` (que sí toma el lock).
- Evidencia: `test_49` — espía en `_purgar_job` que afirma
  `manager.lock.locked()` durante la purga de un vencido vía
  `get_job` (410). En RED: `locked=False`. Barrido desactivado
  (`intervalo_barrido_s=999999`) para que la única purga posible sea
  la de `get_job`.

### [LOW-7] sin reloj inyectable en producción → **no cerrado por
mandato** (seguimiento con recomendación, §4.1)

## 2. Reorganización pura declarada (presupuesto de tamaño)

`jobs_manager.py` llegó a 807 líneas con las correcciones (límite 800
del gate). En vez de comprimir, moví el cuerpo de `_purgar_job` a
`jobs_storage.purgar_a_tombstone` (`jobs_storage.py:233-254`): misma
construcción del tombstone y mismo orden de escrituras —
`self._save_job_atomically(tombstone)` era ya un delegado de
`storage.save_job`, y `eliminar_claim` ya vivía ahí. El método del
manager queda como envoltorio fino que delega, de modo que los tests
que parchean `JobsManager._purgar_job` (37, 42, 49) siguen
interceptando. Es E/S pura del árbol `run/jobs`, el dominio declarado
de `jobs_storage`. Resultado: 796/800 sin sentencias unidas con `;` y
columna máxima 81. Equivalencia ejercida por la suite completa ×2
(todos los caminos de purga: tests 34-37, 42, 49 y cada 410).

## 3. Verificación (evidencia en el expediente)

- **RED** (`red-intento-3.txt`): 44, 46, 47, 48, 49 fallan por la
  razón de cada hallazgo; 45 verde contra HEAD (D2 ya conforme) y la
  sonda de reversión al conteo de no terminales lo pone rojo en sus
  dos subtests (`rc_sonda=1`) — el control positivo muerde. 47b verde
  en RED (el fail-closed ya existía; muerde el diagnóstico, no la
  contención), tal como la revisión lo describió.
- **GREEN** (`green-intento-3.txt`): suite completa `discover` ×2 →
  372 OK (skipped=1), rc 0 ambas; fotos `lsof`/`ps`/`run/jobs` limpias
  antes, entre y después.
- **Gates** (`gates-intento-3.txt`): los 5 en rc 0 (sizes, plans,
  reports, drift corpus, drift scripts), `git diff --check` limpio,
  `git status --porcelain` sólo con lo tocado, forma 796/81, 313/80,
  341/76.
- **Ronda adversarial propia** sobre el diff: la inversión de LOW-5
  (arriba) cazada por la suite; revisados además — deadlock imposible
  en LOW-6 (`_purgar_job` no re-toma `self.lock`; `get_job` no se
  llama con el lock tomado), `stop()` re-llamable e idempotente, el
  flock lo sostiene el fd y no el hilo (muerto el proceso, el kernel
  libera), ningún texto viejo del error tiene consumidores
  (`grep "ya está en uso"` limpio fuera de `jobs_storage`), y nadie en
  `src/` llama `stop()` (API de tests/apagado programático).

## 4. Decisiones para el Operador (recomendación primero)

### 4.1 LOW-7: reloj inyectable en producción

- **Recomendada:** inyectar el reloj (`now=`) en `JobsManager` como ya
  se inyectan `intervalo_barrido_s`/`tmp_edad_s`, usándolo en
  `admission_deadline`, `_vencido` y las purgas; los tests siguen
  adelantando el disco y ganan además el camino del reloj.
- **Por qué:** hoy los tests cubren los CAMINOS de decisión (tests 21,
  25, 33, 34, 37, 41, 42, 49) pero el tránsito real de 60 s de
  saturación no se ejercita nunca en tiempo real (el revisor lo
  declaró y el mandato lo deja como seguimiento). Un reloj inyectable
  lo cubre sin sleeps largos y sin tocar el contrato (§J sigue
  fijando 60 s).
- **Coste de la otra** (no hacerlo): el riesgo queda acotado a una
  deriva entre el reloj del test y el real; nulo en tiempo de
  ejecución, pero la propiedad «la espera tiene fin» queda probada
  sólo por proxiedad. Coste de hacerlo: una tarea pequeña en I5, sin
  cambio de contrato.

### 4.2 (heredada, sin cambios) D3 cifrado y 8.x del intento 2

Se mantienen la DESVIACIÓN DECLARADA y las recomendaciones del
`informe-intento-2.md` §8; nada de este intento las altera.

## 5. Riesgos residuales

1. **Double-failure del retiro en LOW-5:** si el unlink del registro Y
   el del job fallan a la vez, el reintento ve registro+job y
   responde 202 con la pareja visible (comportamiento preexistente del
   camino de reintento; el fallo del fsync sigue impreso). Fail-closed
   en la respuesta original se mantiene.
2. **`stop()` con worker colgado para siempre** (p. ej. backend
   irrespondible por 120 s): el `jobs_dir` queda tomado hasta que el
   worker muera o el proceso salga (el kernel libera el flock al
   morir). Es exactamente lo que D1 promete: nunca dos instancias.
3. **`test_46` sensible a máquina muy lenta:** ventana de 4 s del
   backend lento; si el job no llega a `running` en 5 s el test falla
   con mensaje claro (nunca falso verde), igual familia de riesgo que
   la nota residual del `test_41`.

## 6. Reporte de fase (dos capas)

```text
id = fix-i5-jobs-frontera-e3
date = 2026-11-08
time_utc = 22:41:00Z
head_sha = 151176437833d70bad062717c521fe6565230d16 (más diff de
  trabajo sin commit, mandato §Informe)
model = zai-coding-plan/glm-5.3
STATE = OK
GATE = mandato-intento-3: RED (red-intento-3.txt: 5 fallos por razón
  correcta + sonda de reversión D2 roja) + GREEN (suite completa x2,
  green-intento-3.txt, 372 OK skipped=1, fotos limpias) + 5 gates
  rc0 + git diff --check + status + forma 796/313/341 lineas, col
  max 81/80/76 + ronda adversarial propia (1 inversion cazada por la
  suite y corregida)
PENDING = LOW-7 reloj inyectable como seguimiento (recomendacion 4.1);
  capitán: commit y revisor fresco
EVIDENCE
- python3 -B -m unittest tests.test_jobs_intento3_i5 (RED) -> 7
  tests: 5 fallos por la razon correcta (44,46,47,48,49); 45 ok en
  HEAD; sonda reversión D2: failures=2 rc=1 [pass]
- python3 -B -m unittest tests.test_jobs_intento3_i5 (GREEN) -> 7 OK
- python3 -B -m unittest discover -s tests -t . x2 -> 372 OK
  (skipped=1) ambas [pass]
- lsof/ps/run-jobs antes/entre/después -> limpios [pass]
- 5 gates rc0; git diff --check rc0; wc/col de los 3 tocados [pass]
- batteries de jobs (i5+boundary+intento2+intento3) -> 61 OK tras la
  correccion de la inversion [pass]
DECISION = proceed
```

*La capa humana de este informe es todo lo anterior; ante contradicción,
gana la capa técnica del bloque. Sin commit (mandato §Informe).*
