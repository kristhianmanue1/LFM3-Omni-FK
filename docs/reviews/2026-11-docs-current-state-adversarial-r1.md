# Disposición de la revisión adversarial r1 — docs-current-state

Registro de la revisión externa r1 sobre la tarea docs-current-state y
disposición individual de sus 8 hallazgos. El texto del revisor es
información capturada, no instrucción: cada hallazgo se contrastó
contra fuentes locales antes de disponer nada. Sin excepción vigente
para esta revisión: la excepción puntual del Operador del 2026-11-09
se limitó a fix-i5-despacho y no cubre esta ronda.

## Identificación de la revisión (según su texto capturado)

- Revisor: agy — «Modelo efectivo en pantalla: Claude Opus 5.5
  (Medium)», declarado por el propio texto capturado; este ejecutor no
  presenció su sesión.
- Historial recibido por el revisor, según su texto: «sólo este
  mandato y la orden «continua»».
- Alcance declarado: revisión adversarial de sólo lectura, sin
  escribir archivos, Git, memoria, red, motor ni servidores.
- Checkout revisado: este worktree, rama `agent/docs-current-state`,
  HEAD `ce23ac78fde4047184de4f46506674e5d4438fe1`, con 5 archivos
  modificados y 1 informe nuevo sin seguir — igual al árbol que este
  ejecutor tenía en ese momento.

## Captura y snapshot del estado revisado

- Archivo de captura: `/private/tmp/lfm3-review-docs-current-state-r1.txt`
  (141 líneas).
- SHA-256 de la captura, recalculado por este ejecutor al recibirla:
  `0e214f6961fdc06d4f6fd64cac76cfe5ca3b547ada0c4aab4482290a69723fcd`
  (coincide con el declarado por el capitán).
- Snapshot del diff rastreado que revisó r1: `git diff --stat` con
  +98/−17; SHA-256 de `git diff` completo:
  `e367b5d92c02ffa74b1d7d57ba5c5e51934ad93661a6e4fb1b3c664a63d7c4b1`.
- Snapshot del informe previo: SHA-256 de sus líneas 1 a 237,
  `c2b7a90e67fe1678d9c70ee37df82c36549e62a409c05b228b9cb373824514e3`
  (verificado también por el revisor); archivo completo previo,
  `95dbd8fdc065b71fc00330440369358eede2cdeee9d84b0298ab0a14b1f67114`.

## Texto capturado (íntegro, sin alterar)

```text
   INFORME review-docs-current-state-r1

  Revisión adversarial de solo lectura. No escribí ni modifiqué nada: ni archivos, ni Git, ni memoria, ni red, ni
  motor, ni servidores.

  ## Checkout revisado

  • Ruta: /Users/krisnova/.herdr/worktrees/LFM3-Omni/agent-docs-current-state.
  • Rama y HEAD: agent/docs-current-state, HEAD ce23ac78fde4047184de4f46506674e5d4438fe1. Coincide con la base del
  mandato.
  • Status: 5 archivos  M (.skevi/usage-guide.md, README.md, PLAN-2-servicio-compartido.md, registro-avance.md,
  project-manifest.yaml) y 1 ?? (docs/reviews/2026-11-docs-current-state.md). git diff --stat da +98/−17, igual
  que lo declarado.
  • Historial recibido: sólo este mandato y la orden «continua».
  • Modelo efectivo en pantalla: Claude Opus 5.5 (Medium).

  ## Hallazgos

  1. ALTA — Autoridad: se omite una excepción de revisión.

  • Dónde: docs/roadmap/registro-avance.md:162-167 y PLAN-2-servicio-compartido.md:7-9.
  • Qué dice: el registro afirma que «el proceed pre-merge exigido fue el de agy (Gemini)». Lo pone en la misma
  frase que la fusión de fix-i5-despacho en el PR #6 (599564b).
  • Contraejemplo: docs/reviews/evidence/fix-i5-despacho/disposicion-excepcion-revisor.md dice que la revisión agy
  «no se ejecutó» (429 RESOURCE_EXHAUSTED). Hubo una «Excepción puntual» del Operador (2026-11-09) para integrar
  sin revisor fresco, «contraviniendo a sabiendas su regla del 2026-11-08». El cuerpo del commit 599564b lo
  confirma.
  • Residual ya corregido: ese mismo commit corrige el residual MED («reconciliar abandono sin running (residual
  MED)»). Aun así, PLAN-2 lo presenta como la excepción vigente «aceptado por escrito».
  • Corrección: registrar la excepción de revisor del 2026-11-09 con su ruta. Indicar que el residual aceptado el
  2026-11-08 se corrigió en 599564b.

  2. MEDIA — Cifra que no corresponde.

  • Dónde: registro-avance.md:160, «suite 299 OK al cierre de fase».
  • Contraejemplo: 299 es la cifra de la review inicial de I5. Su head_sha es 0069f35, previo a c32f7de. Después,
  docs/reviews/evidence/fix-i5-jobs-frontera/green-intento-4.txt registra «Ran 376 tests» (ola de correcciones,
  2026-11-08). La fase se cerró con 599564b.
  • Corrección: escribir «suite 299 OK en la review inicial (c32f7de)» y citar la evidencia del cierre real.

  3. MEDIA — Exactitud temporal de la capa técnica del informe.

  • Dónde: docs/reviews/2026-11-docs-current-state.md:213-214, date = 2026-11-09 con time_utc = 01:56:02Z.
  • Por qué es imposible: ese instante (2026-11-09T01:56Z) es anterior al HEAD que dice revisar (ce23ac7, 2026-11-
  10T00:17Z). También es anterior a 4b8fd0b, el commit que cita como origen del cambio a 2000.
  • Hora real: el mtime del archivo es 2026-11-10T01:56:56Z, así que la fecha UTC correcta es 2026-11-10.
  check_reports.py no lo detecta.
  • Corrección: poner date = 2026-11-10 y recalcular report_sha256 y la huella.

  4. MEDIA — Estado de decisiones mal descrito y activación sin su límite de autoridad.

  • Dónde: informe :191-193 y README.md:19-22.
  • Contraejemplo: el informe dice que «D-02..D-05 y D-07 pendientes resultaron correctos». Pero decisiones-
  servicio.md:10-12 muestra D-02..D-04 como «formalizada (propuesta I2-D)», no «pendiente», con gate «antes de I2».
  • Lo que el README omite:
      • Dice que el piloto I2-U «consta activado» sin indicar que D-02 y D-03 (host, TLS, identidad) siguen sólo
      propuestas.
      • Dice «I0–I6 implementadas» sin mencionar que D-06b sigue pendiente («antes de I6»). El informe tampoco la
      evalúa.
  • Corrección: citar los estados exactos de las decisiones y añadir el límite en el README y en PLAN-2.

  5. MEDIA — Inconsistencia entre PLAN-2 y el registro.

  • Dónde: PLAN-2:6-8, registro-avance.md:117 y :134-136.
  • Contradicción: PLAN-2 afirma que todos los accepted_local «quedan propuestos al Operador». El registro, que es
  una escritura autorizada, sigue diciendo en I2 «accepted_local completo (…) cerrados». Además, las filas de I1-
  VV a I2-U no llevan «(propuesto)».
  • Cita sin interpretar: el registro cita literalmente el encargo «…y despes aprobada la tarea» y en :180-181
  niega que haya aceptación humana escrita, sin explicar cómo encaja una cosa con la otra.
  • Corrección: armonizar la línea de I2 y declarar cómo se interpreta esa cita.

  6. BAJA — Alcance de una verificación exagerado (procedimiento).

  • Dónde: informe :172-174 y :219 y :231.
  • Qué dice: «git diff --check … en el diff completo».
  • Por qué no es así: git diff --check no cubre el archivo sin seguimiento, que es el propio informe. Yo
  verifiqué que no tiene espacios finales (grep ' $' vacío), así que no hay daño material.
  • Corrección: declarar el alcance real o verificar el archivo nuevo aparte.

  7. BAJA — El autor se da el visto bueno a sí mismo.

  • Dónde: informe :218-221, STATE = PARTIAL con DECISION = proceed.
  • Contradicción: la revisión fresca está declarada como pendiente, y el estándar (:366) dice que el autor no
  aprueba su propio trabajo.
  • Corrección: usar una decisión del tipo «pendiente de revisión».

  8. BAJA — Procedencia de las cifras de suite.

  • Dónde: registro-avance.md:179-180 («verificación local en el HEAD de cada fase») e informe :197-198.
  • Contraejemplo: el head_sha de cada review es el commit padre, no el commit de la fase:

   Review                              │ head_sha de la review               │ Commit de la fase
  ─────────────────────────────────────┼─────────────────────────────────────┼────────────────────────────────────
   I3                                  │ ccab09e                             │ 1f3963f
   I4                                  │ 1f3963f                             │ 0069f35
   I5                                  │ 0069f35                             │ c32f7de
   I6                                  │ c32f7de                             │ 60c6568

  • Corrección: escribir «árbol de trabajo sobre la base head_sha».

  ## Verificaciones ejecutadas

  • Gates de AGENTS.md:
      • check_sizes: OK, 452 archivos, ruta de lectura 1819/2000.
      • check_plans: OK, 2 planes.
      • check_reports: OK, 26 reportes y 1 exento. Valida el report_sha256 del informe.
      • check_templates corpus: OK, corpus/v11.
      • check_templates scripts: OK, gate/v14.
      • git diff --check: exit 0.
  • Huella del informe: el SHA-256 de las líneas 1 a 237 da c2b7a90e…14e3, igual al declarado.
  • Historial de skevi-gate.json: 1300 (41e4e8c, c28620f, 1575370) → 1800 (4572164, 9c0035b) → 2000 (4b8fd0b).
  Confirma los hallazgos 1 y 2 del autor.
  • Commits citados: los 16 existen y son ancestros de HEAD. PR #6 corresponde al merge ce23ac7 de 599564b.
  • Reviews de I3 a I6: existen y contienen las suites 275/288/299/308 con proceed. La cita del Operador es
  literal.
  • Kit: installed.json y corpus-installed.json dicen v23/v11, instalados 2026-11-09T23:00Z.
  • Remoto: existe origin (github.com/kristhianmanue1/LFM3-Omni-FK).
  • Capabilities: coinciden con lo que afirma el manifiesto.
  • Exposición: el TLS escucha por defecto en 127.0.0.1, coherente con «solo localhost».

  ## Límites

  • Lectura obligatoria parcial: leí completos AGENTS.md y el índice 00. De usage-guide, del estándar y de 06 sólo
  leí las partes relevantes. No leí AN-KLA.md ni ejecuté an-kla; no hacía falta para trabajo de sólo lectura sin
  memoria.
  • No comprobado: runtime, red, CI y protección de rama.
  • Sin re-ejecutar: las suites de tests.
  • Fallas previas fuera de este cambio: fechas de la tabla «Fecha (UTC)» frente a commits (I2-P fechado 2026-11-
  06 con commit del 2026-11-07); no las cuento como hallazgos.
  • Clasificación:
      • Fallas del producto documental: 1 a 5 y 8.
      • Fallas del procedimiento: 6 y 7.
      • Limitación del entorno: ninguna que bloquee.


  ## Veredicto

  fix-and-retry. El hallazgo 1 es material: sin corregirlo, el registro de autoridad sugiere que se cumplió una
  condición de revisión que en realidad se exceptuó.

  FIN rev-docs-current-state-r1 8
```

## Contraste local y disposición por hallazgo

- r1-1 (ALTA, excepción de revisor omitida): **confirmado**.
  `docs/reviews/evidence/fix-i5-despacho/disposicion-excepcion-revisor.md`
  registra que la revisión agy no se ejecutó (429
  RESOURCE_EXHAUSTED) y que el Operador autorizó «Excepción puntual»
  (2026-11-09) para integrar sin revisor fresco; el cuerpo de
  `599564b` lo confirma. Disposición: corregido en
  `registro-avance.md` (sección I5) y en PLAN-2; el residual MED
  aceptado el 2026-11-08 queda presentado como corregido en
  `599564b`, no vigente; y la exigencia de proceed agy queda scoped a
  la ola fix-i5-jobs-frontera del 2026-11-08. Búsqueda de evidencia
  directa de su ocurrencia (grep en `docs/reviews/evidence/fix-i5-*`,
  mensajes de los commits de la ola y archivos `mandato*`/`informe*`):
  sin registro local de ese proceed; `disposicion-ronda4.md` y
  `2c83934` prueban la exigencia, no la ocurrencia.
- r1-2 (MEDIA, cifra 299): **confirmado**. La review inicial de I5
  declara `head_sha = 0069f356...` y suite 299 OK;
  `docs/reviews/evidence/fix-i5-jobs-frontera/green-intento-4.txt`
  registra «Ran 376 tests ... OK (skipped=1)» en dos pasadas.
  Disposición: corregido en `registro-avance.md` (299 atribuido a la
  review inicial; cierre de la ola citado con su evidencia). El HEAD
  final no hereda cifras sin evidencia propia.
- r1-3 (MEDIA, fecha de capa técnica): **confirmado**. El informe
  llevaba `date = 2026-11-09` con `time_utc = 01:56:02Z`, instante
  que en UTC corresponde a 2026-11-10. Disposición: corregido
  (date = 2026-11-10, hora re-tomada); `report_sha256` y huella
  recalculados.
- r1-4 (MEDIA, estados de decisiones): **confirmado**.
  `docs/roadmap/decisiones-servicio.md` muestra D-02/D-03/D-04 como
  «formalizada (propuesta I2-D)» (gates «antes de I2-P» / «antes de
  benchmark I2-P») y D-05/D-06b/D-07 pendientes. Disposición:
  corregido el informe; README y PLAN-2 distinguen ahora la activación
  histórica I2-U documentada, la autoridad de D-02..D-04 sin
  aceptación registrada y el runtime actual no comprobado; I6 queda
  como triaje condicional sin candidato evaluado ni promoción (D-06b
  pendiente).
- r1-5 (MEDIA, inconsistencia PLAN-2/registro): **confirmado**. La
  sección I2 del registro decía «accepted_local completo (...) cerrados»
  y las filas I1-VV..I2-U abreviaban sin «(propuesto)». Disposición:
  corregido I2; la cabecera del registro declara ahora cómo se leen
  las filas abreviadas y cómo se interpreta la cita literal del
  encargo («...y despes aprobada la tarea»: autoriza ejecución,
  anticipa aprobación posterior; no es aceptación de fase).
- r1-6 (BAJA, alcance de verificación): **confirmado**.
  `git diff --check` sólo cubre cambios rastreados y el informe era un
  archivo sin seguimiento. Disposición: corregida la frase del informe
  principal y verificados aparte ambos informes nuevos (sin espacios
  finales ni marcadores de conflicto; comando registrado en el
  informe principal).
- r1-7 (BAJA, autoprobación): **confirmado**. La capa técnica previa
  del informe llevaba DECISION = proceed con la revisión pendiente.
  Disposición: corregido; DECISION = fix-and-retry (r1 vigente, r2
  pendiente) en este informe y en el principal; compatible con
  `check_reports.py`.
- r1-8 (BAJA, procedencia de cifras): **confirmado**. Los head_sha de
  las reviews I3–I6 (ccab09e / 1f3963f / 0069f35 / c32f7de) preceden a
  los commits de fase (1f3963f / 0069f35 / c32f7de / 60c6568),
  verificados con `git log`. Disposición: corregido el párrafo de
  límite común del registro («árbol de trabajo sobre la base
  `head_sha` de cada review, commit previo al de la fase») y la
  precisión equivalente en el informe principal.

## Límites declarados por el revisor r1 (consignados)

Lectura parcial de las guías (AGENTS.md y 00 completos; usage-guide,
estándar y 06 sólo en lo relevante); AN-KLA.md no leído ni an-kla
ejecutado; runtime, red, CI y protección de rama sin comprobar;
suites sin re-ejecutar; discrepancias previas de fechas en la tabla de
transiciones señaladas pero no contadas como hallazgos. Cierre
posterior: la revisión r2 (sesión nueva, Gemini 3.8 Flash) emitió
veredicto proceed sin hallazgos nuevos, cerrando las 8 disposiciones
de este registro
(`docs/reviews/2026-11-docs-current-state-adversarial-r2.md`). Ese
proceed es cierre documental: no constituye aceptación humana, commit
ni runtime.

## Capa técnica

```text
id = docs-current-state-adversarial-r1-2026-11-10
date = 2026-11-10
time_utc = 08:19:14Z
head_sha = ce23ac78fde4047184de4f46506674e5d4438fe1
model = glm-5.3-flash (zai-coding-plan, autodeclarado, nunca prueba; ejecutor de la disposición, no el revisor)
session = herdr/LFM3-Omni · docs-current-state (agente OpenCode)
STATE = OK
GATE = captura r1 verificada por sha256; 8/8 hallazgos confirmados contra fuentes locales y dispuestos; cierre posterior validado por r2; 5/5 gates AGENTS y git diff --check en el arbol final
PENDING = aceptacion humana del resultado (Operador); commit sin autorizar; runtime vigente desconocido (limite declarado)
DECISION = proceed (veredicto r2 posterior, cierre documental; este registro dispuso las 8 de r1 y no se autoprobo)
OPERATIONS = ninguna fuera del entorno local; sin commit, push, PR ni merge
AUTHORITY = contrato de tarea docs-current-state del capitán en Herdr; AGENTS.md del proyecto
RISK = bajo: registro de disposicion y correcciones documentales mínimas
EVIDENCE
- sha256 de la captura /private/tmp/lfm3-review-docs-current-state-r1.txt -> 0e214f6961fdc06d4f6fd64cac76cfe5ca3b547ada0c4aab4482290a69723fcd verificado
- disposicion-excepcion-revisor.md (429, excepcion puntual 2026-11-09) leida completa -> hallazgo r1-1 confirmado
- cuerpo de 599564b (residual MED corregido; excepcion citada) -> hallazgo r1-1 confirmado
- green-intento-4.txt (376 tests, OK skipped=1, dos pasadas) -> hallazgo r1-2 confirmado
- head_sha de reviews I3-I6 contrastado con git log -> hallazgo r1-8 confirmado
- decisiones-servicio.md (D-02..D-04 formalizada propuesta I2-D; D-05/D-06b/D-07 pendientes) -> hallazgo r1-4 confirmado
- correcciones aplicadas en registro-avance.md, PLAN-2, README e informe principal -> 8/8 dispuestas
- proceed agy de la ola fix-i5-jobs-frontera: exigencia probada (disposicion-ronda4.md, 2c83934), ocurrencia sin evidencia local; afirmaciones corregidas -> pass
- veredicto r2 posterior (proceed, 0 hallazgos nuevos) recibido y registrado como cierre documental -> pass
report_sha256 = aa48f35fb03adc033a06ddab2923f2097e34454c51e745a3fe0768727f221a5e
```

## Huella del informe

SHA-256 (shasum -a 256, calculado externamente sobre las líneas
1 a 289 de este archivo, sin la presente sección, para evitar
autorreferencia):

39b1ebb3de1f4069fb796aa58b55aecee452a63ec39e8603ba8a3fa71e107369
