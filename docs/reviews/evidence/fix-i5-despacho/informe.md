# Informe del ejecutor — fix-i5-despacho, intento 1

- **Fecha:** 2026-11-09 (local; time_utc en el bloque técnico).
- **Rama:** `agent/fix-i5-despacho`, base `main` `7fd40fc`
  (trabajo como diff sin commit; mandato §7).
- **Mandato:** este expediente (`mandato.md`); prescripción exacta del
  Operador en `docs/reviews/evidence/fix-i5-jobs-frontera/aceptacion-riesgo.md`
  §Seguimiento y `disposicion-ronda4.md`.
- **Motor real:** nunca arrancado; sin `run/serve.sh`, sin `kill`,
  sin red externa; `lsof` limpio antes y después de las corridas
  (`green.txt`). Suite completa NO ejecutada (contiene
  `test_piloto_live_i2`, prohibido); se corrieron los módulos de §4 y
  los tres módulos de intentos que `grep -rl jobs_manager tests/`
  lista.
- **Veredicto:** 3 hallazgos cerrados (fixed), 0 injustificados.

## 1. Disposición de los hallazgos

### [RESIDUAL-MED] `202` sin despacho tras `OSError` en la ventana
### desencolar → persistir `running` → **fixed**

- **Causa (confirmada contra `main` `7fd40fc`):** si un `OSError`
  caía entre retirar el job de `work_queue` y persistir `running`,
  el job quedaba `queued` en disco, fuera de la cola y dentro de
  `_en_cola`; el reintento con la misma clave veía `job_id in
  _en_cola` en `_asegurar_despacho` y respondía `202` sin avance
  (202 eterno hasta purga por TTL o reinicio).
- **Fix (`src/jobs_manager.py`), prescripción ejecutada tal cual:**
  1. Nuevo `_reconciliar_abandono(project_id, job_id)`: relectura del
     job bajo `self.lock`; si sigue `queued`, lo saca de `_en_cola`
     para que el siguiente reintento lo reencole vía
     `_asegurar_despacho` (puntos 1 y 2 de la prescripción).
  2. Se llama desde los dos disparadores prescritos: (a) el
     `except OSError` del worker cuando `_reclamar` propaga un
     `OSError` real del claim (punto 1) y (b) el `except OSError`
     preexistente del worker (:593), que cubre el fallo al persistir
     `running` y el resto de la ventana (punto 1).
  3. Si la relectura no devuelve un `queued` legible, no se toca
     nada: comportamiento actual, fail-closed (punto 3).
- **`_reclamar` ya no traga OSErrors:** propagan al worker para la
  reconciliación; sólo la contención del flock
  (`EWOULDBLOCK`/`EAGAIN`) sigue devolviendo `None` sin reconciliar
  («lo tiene otro» no es un abandono; bajo D1 es inalcanzable y
  reconciliarla podría reencolar en bucle en un mundo no-D1).
- **Evidencia:** RED en `red.txt` — `test_27` (fallo en el claim),
  `test_28` (fallo al persistir `running`, la ruta :555) y `test_29`
  (fallo de admisión compartida) fallan hoy por la razón correcta:
  el job abandonado sigue en `_en_cola` («el siguiente reintento
  respondería 202 sin avance»). En GREEN los tres reencolan y
  ejecutan exactamente una vez (marcador del backend falso == 1).
  `test_30` es guarda de la transición de cierre por deadline
  (verde por diseño: `_cerrar` ya descarta de `_en_cola` antes de
  escribir; muerde si ese descarte desaparece).

### [LOW-1] `_resolver_rival` respondía `202` sin pasar por
### `_asegurar_despacho` → **fixed** (elección: alinear)

- **Elección (mandato §3 me la delega):** ALINEAR la rama con
  `_asegurar_despacho`, no anotarla como defensiva de D1. Razón: la
  propiedad «jamás un 202 sin avance comprobable» queda uniforme en
  todas las ramas que devuelven un job vivo; el coste es de 5 líneas;
  y anotar sólo pospone el defecto — si D1 se revisara alguna vez,
  la divergencia resucitaría exactamente el residual que esta tarea
  cierra. La rama sigue siendo inalcanzable vía `create_job` bajo D1
  (una sola instancia por `jobs_dir`; `lookup`→`commit` va bajo
  `self.lock`), lo que el propio test declara.
- **Prueba alcanzable:** llamada directa a `_resolver_rival`
  (precedente: `test_53` llama `_reclamar` y `_marcar_running`
  directo) con el estado que la rama debe reconciliar: rival
  `queued` en disco con su registro, escrito tras el arranque, fuera
  de la cola y de `_en_cola`. RED en `red.txt`: el 202 no encoló
  nada («202 sin avance (LOW-1)»). GREEN: el rival queda encolado,
  se ejecuta exactamente una vez y el job propio del rival queda
  descartado en disco.

### [LOW-7] Reloj no inyectable → **fixed**

- **Fix:** parámetro de constructor `reloj` (`Callable[[], datetime]`,
  `None` = reloj real `_ahora_utc`), usado por el barrido periódico
  (`_barrido_si_toca`), la purga (`_purgar_expirados`), el deadline
  de admisión (creación y vencimiento), el TTL (`_vencido`),
  `started_at`, `completed_at` y `expires_at`. `time.monotonic()` y
  los `datetime.now` del manager/mixin desaparecen; `import time`
  queda fuera de ambos módulos. `jobs_storage` no se tocó: su
  `limpiar_temporales` sigue con reloj real (fuera de alcance;
  un tmp legítimo vive milisegundos y el barrido de tmp no es objeto
  de test de tiempo aquí).
- **Tests de tiempo sin pausas reales:** `test_32` (el barrido no
  purga antes del intervalo y purga después, con reloj falso y
  avances explícitos), `test_33` (la purga responde al reloj),
  `test_34` (el deadline no cierra con el reloj congelado y cierra
  en `failed`/`admission_timeout` al adelantarlo; delta
  deadline−creación exactamente 60 s) y `test_35` — reescritura del
  `test_15` de la frontera, que esperaba 2,5 s reales: ahora un
  backend con puerta retiene la respuesta mientras el test adelanta
  el reloj 10 s dentro de la ejecución y afirma deltas exactos
  (creado→completado == 10; completado→expira == 60, §J).

## 2. Cambios por archivo

- `src/jobs_manager.py` (800/800 líneas): `import errno` y fuera
  `import time`; `_ahora_utc`; parámetro `reloj` en constructor y
  `_arrancar`; `_reconciliar_abandono`; `create_job` y las seis
  lecturas de reloj de pared migradas; `_reclamar` propaga OSError
  real y distingue contención por errno; worker reconcilia en sus
  dos disparadores; `_resolver_rival` alineado (LOW-1).
- `src/jobs_recovery.py` (140/800): atributo `reloj` documentado en
  el contrato del mixin; `_barrido_si_toca` compara segundos
  transcurridos del reloj inyectado (`.total_seconds()`); `_purgar_expirados`
  usa `self.reloj()`; imports ajustados (`timezone`/`time` fuera).
- `tests/test_jobs_boundary_i5.py` (783/800): docstring con
  referencia recíproca al módulo de la ola; `test_15` migrado como
  `test_35` (comentario en sitio). Ningún test existente editado más
  allá de esa migración; la suite de la frontera sigue en verde.
- `tests/test_jobs_despacho_i5.py` (nuevo, 548/800): tests 27-35,
  numeración continua de la frontera; helpers `RelojFalso` y
  `BackendPuerta`; importa `BackendFalso`, `RESPUESTA_VALIDA`,
  `_esperar_terminal` y `_escribir_job_en_disco` de la frontera
  (patrón del intento 4). Ver «Decisiones» 1.
- Este expediente: `mandato.md` (previo), `red.txt`, `green.txt`,
  `informe.md`.

## 3. Propiedades (pass | fail | inconclusive)

- OSError en el claim → el siguiente reintento reencola y ejecuta
  una vez, jamás 202 eterno: **pass** (RED test_27 → GREEN).
- OSError al persistir `running` → ídem: **pass** (RED test_28 →
  GREEN).
- OSError en admisión compartida → ídem: **pass** (RED test_29 →
  GREEN).
- OSError al cerrar por deadline → fallo explícito durable
  (`admission_timeout`), sin ejecución, sin 202 eterno: **pass**
  (guarda test_30; verde por diseño, mordible).
- Rival `queued` sin despacho constatable → 202 sólo con despacho
  asegurado y ejecución única: **pass** (RED test_31 → GREEN).
- Reloj inyectable gobierna barrido, purga y deadline sin pausas
  reales: **pass** (RED tests 32-34 por TypeError del constructor →
  GREEN con controles negativos y positivos).
- Retención §J desde el terminal sin pausas reales: **pass**
  (RED test_15 → GREEN test_35).
- Garantías cerradas preservadas (despacho garantizado tras doble
  fallo, purga con estado recargado bajo lock, D1 flock, RFC 8785,
  persistencia atómica; suites `test_jobs_i5`,
  `test_jobs_boundary_i5` e intentos 2-4): **pass** (73 tests x2,
  `green.txt`).
- Comportamiento del mundo no-D1 (dos instancias): **inconclusive**
  — exógeno: D1 prohíbe la segunda instancia (`JobsDirOcupado`) y
  probarla exigiría violar una decisión vigente. La reconciliación
  añadida no amplía la escritura concurrente (sólo lee bajo lock y
  toca el conjunto en memoria de su propia instancia).
- `fail`: ninguno.

## 4. Ronda adversarial propia (catálogo `.skevi/review-defect-catalog.md`)

Recorrido por las nueve clases contra el diff final. Contexto: ronda
propia del ejecutor; el revisor fresco de otra familia (agy, Gemini)
lo ordena el Operador después, según el mandato §6.4.

### Hallazgos

- [HIGH] El barrido comparaba `timedelta` con `float` tras la
  inyección del reloj (`self.reloj() - self._ultimo_barrido <
  self.intervalo_barrido_s`) → `TypeError` que MATABA el hilo worker
  en el primer barrido; los jobs quedaban queued para siempre.
  Impacto: pérdida total del servicio de jobs con el fix naive.
  Corrección aplicada: `(self.reloj() -
  self._ultimo_barrido).total_seconds()` (`jobs_recovery.py`). Estado:
  cerrado. Evidencia: la primera corrida GREEN lo destapó (stderr
  «Exception in thread jobs-worker», 6 fallos y 1 error, módulo en
  111,9 s — corrida observada en sesión, no archivada; el estado
  corregido queda archivado: focal 34 OK en 3,5 s y `green.txt`
  73 OK x2). Clase 4 (concurrencia) del catálogo.
- [MED] `test_29` instalaba un dispatcher que fallaba SIEMPRE: el
  reintento jamás podía ejecutar y la propiedad era inprovable incluso
  con el fix correcto. Corrección aplicada: fallo único (one-shot) y
  admisión normal después; la propiedad afirma progreso hasta
  terminal. Estado: cerrado. Evidencia: GREEN final con marcador de
  ejecución == 1. Clase 9 (test que no prueba el requisito).
- [LOW] Ventana estrecha de doble encolado: si la reconciliación del
  worker corre justo mientras un reintento (hilo HTTP, bajo lock)
  reencola, la relectura puede ver aún `queued` y descartar de
  `_en_cola` un job ya reencolado. Impacto: segundo elemento de cola
  del mismo job; la ejecución sigue siendo exactamente una (claim
  flock por job + máquina de estados: el segundo retiro ve
  no-`queued` y lo salta) y el conteo de cola por proyecto es sobre
  disco, no sobre la cola. Aceptado como residual con constancia
  (clase 4). Seguimiento opcional: reconfirmar `_en_cola` dentro de
  la misma sección crítica de relectura.
- [observación, pre-existente, fuera de prescripción]
  `_deadline_admision_vencido` traga el `OSError` de `_fallar`
  (`except (OSError, ValueError): return False`): si el cierre por
  deadline no puede persistir, el job sigue admisión-denegada y puede
  EJECUTARSE TARDE (nunca 202-eterno; la ventana del residual no se
  reabre). No se tocó: la prescripción no lo alcanza y cambiarlo
  altera comportamiento cerrado por rondas previas. Va a
  «Decisiones» 2.

Clases sin hallazgo: 1 (sin datos de terceros nuevos; el reloj lo
cablea el constructor, como el dispatcher), 2 (ninguna operación o
superficie nueva), 3 (sin secretos; mensajes sin eco de payload), 5
(fd del claim emparejado en ambos caminos de error), 6 (sin bucles
nuevos: la reconciliación no reencola por sí misma), 7 (el único
silencio nuevo es el punto 3 de la prescripción, fail-closed
prescrito), 8 (kwarg opcional con único caller actualizado; campos
persistidos byte a byte idénticos con el reloj por defecto).

## 5. Riesgos

1. Residual prescrito: si la RELECTURA del job abandonado también
   falla (disco caído), el job sigue respondiendo `202` sin avance
   hasta la purga por TTL o el reinicio — es el punto 3 de la
   prescripción (fail-closed), no una regresión.
2. Doble encolado estrecho (LOW de la ronda, arriba): sin doble
   ejecución demostrable por diseño del claim; registrado.
3. Mezcla de relojes: jobs/purga/deadline usan el reloj inyectado;
   los tombstones de idempotencia y los temporales siguen en reloj
   real (`jobs_storage`, fuera de alcance). Inocuo en producción
   (el defecto es el reloj real) y en tests (el falso arranca cerca
   del real).
4. `head_sha` del bloque técnico es la base `7fd40fc`: el trabajo va
   sin commit por mandato; la trazabilidad diff→informe la da este
   expediente.

## 6. Decisiones para el Operador

1. **Partida del módulo de tests (§3.4 del estándar).** Recomendado:
   ACEPTAR `tests/test_jobs_despacho_i5.py` (nuevo, fuera de la
   lista literal de §4 del mandato). Por qué: el gate de tamaños es
   no negociable (`AGENTS.md`: «rige sin reinterpretarlos»), los
   tests nuevos mandados para `test_jobs_boundary_i5.py` lo llevaban
   a 1269 líneas y `jobs_manager.py` a 813; el estándar prescribe
   partir (§3.4, preferencias 2-3) y el repo ya tiene el patrón de
   una ola = un módulo (`test_jobs_intento{2,3,4}_i5.py`, este último
   importa helpers de la frontera igual que el nuevo). Alternativa:
   exención registrada del boundary (§3.4 preferencia 4) — cuesta
   tocar `skevi-gate.json` (fuera de alcance del mandato) y contradice
   el propio §3.4 («uno que sigue creciendo se parte»); la tercera
   alternativa, comprimir los tests hasta caber, exigiría borrar
   propiedades RED mandadas. La salida BLOQ del gate antes de la
   partida quedó registrada en sesión y resuelta con la partida.
2. **`_deadline_admision_vencido` que traga el `OSError` del cierre.**
   Recomendado: ABRIR SEGUIMIENTO, sin tocarlo en esta tarea. Por qué
   con evidencia: hoy el job cuyo cierre falla puede ejecutarse tarde
   en vez de cerrarse `failed` (test_30 lo ejercita con la primera
   persistencia inyectada como fallo y el job termina
   `succeeded`/tarde o falla en el reintento del ciclo siguiente);
   es fail-open acotado y pre-existente, confirmado contra
   `7fd40fc`. Alternativa: propagar el `OSError` al worker para que
   la nueva reconciliación lo trate — cuesta cambiar el contrato de
   ese método (hoy devuelve False y el ciclo reintenta), abrir una
   ventana nueva sin prescripción del Operador y otra ronda de
   revisión sobre ella.

## 7. Reporte de fase (dos capas)

```text
id = fix-i5-despacho-e1
date = 2026-11-09
time_utc = 06:14:30Z
head_sha = 7fd40fc7328bcb87a44e418de455a67d52022df9
model = zai-coding-plan/glm-5.3-flash
STATE = OK
GATE = mandato fix-i5-despacho §6: RED (red.txt, 9 rojos por la razón correcta) + GREEN x2 (green.txt, 73 OK ambas, lsof limpio) + 5 gates rc0 + git diff --check + status + ronda adversarial propia con catálogo (1 HIGH y 1 MED cerrados en el propio GREEN, 1 LOW aceptado y registrado, trabajo sin commit sobre 7fd40fc)
PENDING = capitán: revisor fresco agy (Gemini) y commit; decisión 1 (partida del módulo de tests) y seguimiento 2 (swallow del deadline) para el Operador; D3 (cifrado) sigue bloqueando exponer /jobs; test_r13 (reloj de pared) sigue con stop-pidfile según disposicion-ronda4
EVIDENCE
- python3.12 -m unittest tests.test_jobs_boundary_i5 (RED, pre-fix) -> 9 rojos por la razón correcta: 27/28/29/31 fallos de propiedad (202 sin avance, rival sin despacho) y 15/30/32/33/34 TypeError sin reloj [pass]
- python3.12 -m unittest tests.test_jobs_despacho_i5 tests.test_jobs_boundary_i5 tests.test_jobs_i5 tests.test_jobs_intento2_i5 tests.test_jobs_intento3_i5 tests.test_jobs_intento4_i5 x2 -> 73 OK ambas corridas (green.txt) [pass]
- lsof -nP -iTCP -sTCP:LISTEN antes y después -> sin escuchas en 8091/8092/8443 [pass]
- python3.12 scripts/check_sizes.py -> OK 422 archivos, ruta 1799/1800, gate/v14 [pass]
- python3.12 scripts/check_plans.py -> OK 2 planes [pass]
- python3.12 scripts/check_reports.py -> OK 25 reportes, 1 exento [pass]
- python3.12 scripts/check_templates.py corpus+scripts -> al día corpus/v10 y gate/v14 [pass]
- git diff --check -> limpio [pass]
- git status --porcelain -> 3 modificados del alcance + expediente + test nuevo (decisión 1) [pass]
- wc -l de los 4 tocados -> 800/140/783/548 dentro del límite 800 [pass]
DECISION = proceed
report_sha256 = c8bb6417cc8ecb7915b6904e8b0577a802819acdc1ae6a1c6ce11ecd0065f0ae
```

*La capa humana de este informe es todo lo anterior; ante
contradicción, gana la capa técnica del bloque. Sin commit
(mandato §7).*
