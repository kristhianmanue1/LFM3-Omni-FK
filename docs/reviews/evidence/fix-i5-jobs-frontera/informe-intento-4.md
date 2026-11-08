# Informe del ejecutor — fix-i5-jobs-frontera, intento 4

- **Fecha:** 2026-11-08
- **Rama:** `agent/fix-i5-jobs-frontera`, HEAD `50f9a5b`
  (reorganización ya en commit del capitán; los dos fixes como diff de
  trabajo sin commit, mandato §Informe y cierre).
- **Archivos tocados (fase 2):** `src/jobs_manager.py` (760/81),
  `src/jobs_recovery.py` (139/80), `tests/test_jobs_intento4_i5.py`
  (nuevo, 309/74), este expediente.
- **Motor real:** nunca arrancado; fotos `lsof`/`ps`/`run/jobs` limpias
  antes, entre y después de ambas corridas (`green-intento-4.txt`).
- **Diseño:** sin cambios; D1–D5 intactas y no reabiertas.

## 1. Reorganización pura (fase 1, commit `50f9a5b`)

Declarada y verificada en su momento: mixin `src/jobs_recovery.py`
(`startup_recover`, `_barrido_si_toca`, `_purgar_job`,
`_purgar_expirados`), suite 372 OK antes y después
(`refactor-antes-intento-4.txt` / `refactor-despues-intento-4.txt`).
Dejó `jobs_manager.py` en 708 líneas; los fixes de la fase 2 lo dejan
en 760/800 sin compresión.

## 2. Disposición de los 2 hallazgos (ronda 3, revi5d)

### [HIGH] Un `202` de reintento dejaba un job sin despacho → **fixed**

- **Causa:** tras `CommitTrasLinkError` con doble fallo de retiro
  (registro y job siguen en disco), el reintento caía en la rama del
  existente y respondía `202` sin comprobar que aquel `500` nunca
  encoló el job: quedaba `queued` para siempre con el worker ocioso.
- **Fix (`jobs_manager.py`):** `_asegurar_despacho`, llamado en la
  rama del existente bajo `self.lock` (ya tomado por `create_job`):
  un job `queued` cuyo despacho no consta en `self._en_cola` (registro
  en memoria de puestos en cola, alta en `create_job`,
  `startup_recover` y la propia reconciliación; baja en `_cerrar` y
  `_purgar_job`) se encola **una sola vez**; si ya consta, no se toca
  (sin doble encolado ni doble ejecución); si los identificadores son
  ilegibles, `500 storage_error` explícito — nunca un `202` sin
  avance.
- **Evidencia:** `test_50` (base del control del revisor) reproduce
  los dos retiros fallidos de verdad (commit que enlaza y falla,
  `retirar_registro` → `False`, `eliminar_job` no-op), afirma
  `primera=500`, `segunda=202` y el **estado terminal en disco**
  (`failed`/`execution_error` contra el puerto 1), no sólo el `202`.
  En RED quedó en `queued` para siempre (`red-intento-4.txt`).
  `test_51` es la guarda de «una sola vez»: worker detenido tras
  TOMAR el job de la cola, reintento durante la ventana, y afirma
  `work_queue.qsize()==0` y exactamente una ejecución en el backend
  falso. Verde contra HEAD por diseño (hoy el reintento no encola);
  muerde si el fix encola sin comprobar el despacho (precedente
  test_45/47b del intento 3).

### [MED] La purga con estado leído antes del lock sobrescribía
### un `running` → **fixed**

- **Causa:** `get_job` y `_purgar_expirados` decidían la purga con un
  snapshot leído sin el lock; el worker podía pasar el job a
  `running` (bajo lock) entre la lectura y el tombstone, que
  sobrescribía el estado nuevo con `expired`. `_marcar_running` no
  revalidaba el TTL: la ventana exigía claim anterior al vencimiento.
- **Fix:** en `get_job` (`jobs_manager.py`) y en `_purgar_expirados`
  (`jobs_recovery.py`), estado y vencimiento se **recargan bajo
  `self.lock` justo antes de purgar**; un `running` (o `expired`, o
  un job que ya no vence, o desaparecido) no se purga. Ningún
  llamador de `_purgar_expirados` porta el lock (create_job:200,
  startup_recover, `_barrido_si_toca` en el finally del worker), así
  que la toma interna no interbloquea. `_marcar_running` revalida el
  TTL bajo el lock: un vencido sólo llega con el reclamo tomado antes
  de vencer (`_reclamar` rechaza los ya vencidos), y ese cruce queda
  constanciado en stderr; el cierre nunca entrega tras el TTL (§J).
- **Evidencia:** `test_53` (base del control del revisor): claim
  tomado con TTL vivo, cruce del TTL, `_marcar_running` intercalado
  entre la lectura del GET y su purga — el disco termina `running`
  (en RED: `expired`). `test_52` cubre la variante del **barrido**,
  que la ronda 3 dejó sin sonda propia: un «worker» escribe `running`
  durante la validación del vencimiento del snapshot (antes de
  cualquier lock); el barrido recarga bajo el lock, no purga
  (`purgados==0`, disco `running`; en RED purgó el snapshot viejo).
  Ambos deterministas, sin carreras de tiempo real.

## 3. Verificación (evidencia en el expediente)

- **RED** (`red-intento-4.txt`): 50, 52 y 53 fallan por la razón
  exacta de cada hallazgo (`queued != failed`, `expired != running`
  ×2); 51 verde por diseño (guarda declarada). rc=1.
- **GREEN** (`green-intento-4.txt`): suite completa `discover` ×2 →
  376 OK (skipped=1), rc 0 ambas (141,1 s y 137,6 s), fotos limpias
  antes, entre y después.
- **Incidente de proceso (transparente):** la primera corrida ×2 se
  descartó: el shell excedió 600 s con la suite a media marcha — el
  equipo se suspendió (mismo cuadro que el `test_r13` de la ronda 3).
  Repetida bajo `caffeinate -i`: diagnóstico de 376 OK en 138 s y
  luego las dos corridas válidas. El mandato ordena repetirla y así
  se hizo; la salida descartada no se usa como evidencia.
- **Gates** (`gates-intento-4.txt`): los 5 en rc 0 (sizes — 412
  archivos —, plans, reports, drift corpus, drift scripts),
  `git diff --check` limpio, `git status --porcelain` sólo con lo
  tocado, forma 760/81, 139/80, 309/74, sin código con `;`.
- **Ronda adversarial propia** sobre el diff con el catálogo
  (`.skevi/review-defect-catalog.md`): concurrencia (los dos reloads
  son átomo lock→lee→decide→purga; ningún llamador porta el lock;
  `_en_cola` sólo se toca bajo lock), entradas no confiables (el job
  recargado sólo se usa con `.get` + `isinstance` antes de encolar),
  errores silenciados (el fallo de purga sigue contado en
  `fallos_purga` y stderr; `_asegurar_despacho` ilegible → 500
  explícito), contrato (superficie HTTP y SPEC sin cambios; el
  conteo de `_purgar_expirados` ahora sólo cuenta purgas reales), y
  control positivo de los tests (el RED es la prueba de que muerden;
  test_51 muerde si se elimina la guarda del conjunto). Sin
  hallazgos abiertos tras el repaso.

## 4. Decisiones para el Operador (recomendación primero)

### 4.1 `_marcar_running` ante un vencido ya reclamado

- **Recomendada (implementada):** ejecutar con constancia en stderr:
  el reclamo precede al vencimiento (`_reclamar` rechaza vencidos),
  así que la transición a `running` es legítima y el cierre purga sin
  entregar tras el TTL (§J). Es además el desenlace que el control
  del revisor exige (disco en `running`).
- **Por qué:** con evidencia — rechazar dejaría el job `queued`
  vencido hasta el barrido, desperdiciaría la admisión ya reservada y
  contradiría el control copiado como base del RED.
- **Coste de la otra:** renegociar el control con el revisor y una
  ventana de no ejecución con reclamo tomado (cola ocupada sin
  avance).

### 4.2 Seguimiento del despacho: conjunto en memoria

- **Recomendada (implementada):** `self._en_cola` en memoria, con
  alta en cada `put` y baja en terminal/tombstone. Con D1 (una
  instancia por `jobs_dir`) la memoria es autoridad dentro de la
  vida del proceso y `startup_recover` la reconstruye al arrancar.
- **Coste de la otra (campo persistido `dispatched_at`):** cambio de
  esquema y de contrato interno sin ganancia — un crash borra la
  memoria PERO también mata al worker, y el arranque reencola por
  disco; el campo sobra bajo D1.

### 4.3 `caffeinate` en las corridas largas de este equipo

- **Recomendada:** verificar la suite completa bajo `caffeinate -i`
  (o evitar suspensiones de otra forma) en esta máquina.
- **Por qué:** dos incidentes ya (test_r13 en la ronda 3; la corrida
  descartada de hoy, 600 s de shell para 138 s de suite). Coste de no
  hacerlo: corridas inválidas repetidas.

## 5. Riesgos residuales

1. **Heredado (declarado desde el intento 2):** doble fallo con
   registro retirado y job huérfano → el proyecto ve 429 hasta
   reiniciar (`eliminar_job` best-effort; el arranque reconcilia con
   `admission_unconfirmed`). Esta rama no cambió.
2. **`_cerrar` vencido purga el job que cierra el propio worker**
   (posible estado `running` en ese instante): es la promesa §J de no
   entregar tras el TTL en la vía de cierre, no una purga con estado
   viejo; sin cambios aquí.
3. **`_en_cola` con fallo transitorio de claim (OSError del flock de
   reclamo):** el job queda `queued` con despacho «constado» y el
   reintento no reencola hasta terminal/purga/reinicio — idéntico al
   comportamiento previo al fix (el reintento nunca encoló); sólo
   bajo fallo de disco.
4. **GET con job desaparecido entre lectura y lock:** responde 410
   desde el primer snapshot (semántica preexistente); el fix evita
   además resucitar como tombstone un job borrado.

## 6. Reporte de fase (dos capas)

```text
id = fix-i5-jobs-frontera-e4
date = 2026-11-08
time_utc = 2026-11-08T21:40:00Z
head_sha = 50f9a5bf88f8fe1105c03791f86aba69c15ffb35 (más diff de
  trabajo sin commit, mandato §Informe y cierre)
model = zai-coding-plan/glm-5.3
STATE = OK
GATE = mandato-intento-4: RED (red-intento-4.txt: 50/52/53 rojos por
  la razón correcta; 51 guarda verde por diseño) + GREEN (suite
  completa x2 bajo caffeinate, green-intento-4.txt, 376 OK skipped=1
  rc0 ambas, fotos limpias; primera x2 descartada por suspensión del
  equipo y repetida) + 5 gates rc0 + git diff --check + status +
  forma 760/139/309 lineas, col max 81/80/74 + ronda adversarial
  propia con catálogo, sin hallazgos abiertos
PENDING = capitán: commit y revisor fresco; D3 (cifrado) sigue como
  requisito bloqueante para exponer /jobs; LOW-7 reloj inyectable
  sigue como seguimiento (informe-intento-3 §4.1)
EVIDENCE
- python3 -B -m unittest tests.test_jobs_intento4_i5 (RED) -> 4
  tests: 3 fallos por la razón correcta (50,52,53); 51 ok [pass]
- python3 -B -m unittest tests.test_jobs_intento4_i5 (GREEN) -> 4 OK
- python3 -B -m unittest discover -s tests -t . x2 -> 376 OK
  (skipped=1) ambas [pass]
- lsof/ps/run-jobs antes/entre/después -> limpios [pass]
- 5 gates rc0; git diff --check rc0; wc/col de los 3 tocados [pass]
DECISION = proceed
```

*La capa humana de este informe es todo lo anterior; ante contradicción,
gana la capa técnica del bloque. Sin commit (mandato).*
