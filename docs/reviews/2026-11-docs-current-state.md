# Conciliación documental del estado actual — 2026-11-09

Tarea: docs-current-state. Alcance: conciliar sólo contradicciones
documentales ACTUALES contra evidencia local, sin cambiar producto,
contratos técnicos ni historia. Checkout exacto: worktree
`agent-docs-current-state`, rama `agent/docs-current-state`, base
`main` en `ce23ac78fde4047184de4f46506674e5d4438fe1`. Árbol limpio al
inicio (`git status` sin salida). Sin commit: el diff queda sin
versionar para revisión del capitán.

## Estado

OK (cierre documental tras r2). Los diez hallazgos del ejecutor (siete
iniciales y tres de seguimiento) quedaron corregidos, los ocho de la
revisión r1 de agy quedaron dispuestos y la revisión r2 emitió
veredicto proceed sin hallazgos nuevos. Los cinco gates de AGENTS.md y
`git diff --check` pasan sobre el árbol final. El proceed de r2 es
cierre documental: no constituye aceptación humana, commit ni runtime;
el runtime vigente queda desconocido. Detalle en «Ronda adversarial
r1», «Cierre r2» y en los informes
`docs/reviews/2026-11-docs-current-state-adversarial-r1.md` y
`docs/reviews/2026-11-docs-current-state-adversarial-r2.md`.

## Método y fuentes

- Lectura obligatoria completa antes de editar: `AGENTS.md`,
  `AN-KLA.md`, `.skevi/usage-guide.md`,
  `docs/ai-agent-guide/00-INDICE.md`,
  `docs/estandar-diseno-software-github.md`,
  `docs/ai-agent-guide/06-componentes-con-llm.md`, `README.md`,
  PLAN-2 completo, registro de avance completo.
- Kit: `.skevi/installed.json` (plantillas/v23, instalado 2026-11-09),
  `.skevi/corpus-installed.json` (corpus/v11),
  `.skevi/scripts-installed.json` (gate/v14), `docs/MANIFEST.json`
  (corpus/v11), `scripts/MANIFEST.json` (gate/v14),
  `skevi-gate.json` (`reading_path.limit` = 2000), contrastados con
  `docs/reviews/evidence/kit-2026-11-09/registro.md`.
- Estado de plan/roadmap: sólo commits (`git log`/`git show`), ADRs
  (docs/adr/, ADR-001..013), SPECs, contratos, reviews y expedientes
  locales. Un checkbox histórico o un informe propio no se trataron
  como aceptación humana.
- AN-KLA: preflight `an-kla context status` → `ok: true`, plantilla
  0.1.0-beta.33, runtime 0.1.0b35, sin diagnósticos bloqueantes; aviso
  no bloqueante `context_manifest_missing`, propio del worktree
  enlazado (`integration status`: `repo_context linked_worktree`,
  `store_presence absent`; en el checkout principal la auditoría del
  capitán dio `ok: true` sin warning). Se reporta, no se repara aquí;
  detalle en el hallazgo 10. Escritura a AN-KLA y otras memorias:
  ninguna.

## Hallazgos y correcciones

1. README.md decía presupuesto de ruta de lectura «(1800, adopción de
   AN-KLA)». Evidencia local: `skevi-gate.json` vigente = 2000;
   historial de `skevi-gate.json` = 1300 (`41e4e8c`) → 1800
   (`4572164`) → 2000 (`4b8fd0b`, 2026-11-09). Corregido: 2000 desde
   el 2026-11-09, con la procedencia previa.
2. `.skevi/usage-guide.md` databa el re-base a 2000 «el 2026-11-07 al
   cerrar skevi-lfm3». Evidencia local: orden del Operador de
   2026-11-09 al adoptar corpus/v11 y plantillas/v23 (registro
   kit-2026-11-09; commit `4b8fd0b`). Corregido fecha y causa, y se
   añadió el puntero al registro de evidencia. Coincide con la
   corrección de memoria vigente (nunca hubo 2000 antes del
   2026-11-09).
3. `project-manifest.yaml` declaraba el kit «plantillas/v22, gate/v14,
   corpus/v10». Evidencia local: plantillas/v23 y corpus/v11 desde el
   2026-11-09 (installed.json, corpus-installed.json, MANIFEST.json),
   gate/v14 sin cambio. Corregido.
4. `project-manifest.yaml` decía que audio/video/voz «por contrato
   todavía... se ofrecen sólo al cerrar los gates I1-V». Los gates
   I1-V cerraron (I1-V0..VX con commits y reviews del 2026-11-05/06;
   `src/gateway_core.py` anuncia entrada texto/imagen/audio/video y
   salida texto/audio, streaming, voz y transcripción). La condicional
   quedó obsoleta. Corregido: separa el contrato v1 publicado
   (texto+imagen → texto) de la implementación local verificada, y
   deja la exposición remota gateada por dossier.
5. PLAN-2 llevaba cabecera «Estado: PROPUESTO para ejecución»,
   incompatible con la ejecución registrada (commits y reviews de
   I0–I6). Corregida la línea de Estado: adopción por iteración (D-01
   ACEPTADA con alcance I0; encargos sucesivos citados en el registro
   de avance), estados `accepted_local` propuestos al Operador salvo
   el residual MED de I5 con aceptación escrita (2026-11-08), y
   límites explícitos de runtime y exposición remota. Los checkboxes y
   la historia del plan no se tocaron.
6. `docs/roadmap/registro-avance.md` declaraba en I1-V «I1-VM/VC
   `not_started`», contradiciendo su propia tabla (filas de 2026-11-06)
   y el commit `5a69110` que las registró. Corregido el estado.
7. El mismo registro declara «una sección por iteración» pero no
   tenía secciones de I3, I4, I5 ni I6, pese a commits, reviews y
   checkboxes del plan. Añadidas con procedencia declarada
   (reconstrucción a posteriori, 2026-11-09), sólo desde commits y
   reviews locales, con el límite común explícito: la aceptación
   humana plena por iteración no consta por escrito salvo el residual
   I5 (`docs/reviews/evidence/fix-i5-jobs-frontera/aceptacion-riesgo.md`,
   commit `2c83934`), y el runtime vigente no se comprueba.

### Seguimiento de auditoría del capitán (misma tarea)

8. `.skevi/usage-guide.md` afirmaba en la sección del gate en CI que
   «el proyecto aún no tiene remoto ni protección de rama».
   Evidencia local: `git remote -v` muestra `origin`
   (github.com/kristhianmanue1/LFM3-Omni-FK) y `origin/main` local;
   ADR-003 declara ese remoto. Corregido: remoto configurado; CI y
   protección de rama siguen pendientes de decisión, sin evidencia
   actual que los acredite ni los desmienta (sin consulta de red).
9. La precisión «Sin acreditación de runtime vigente ni exposición
   remota» (introducida en el hallazgo 5) borraba implícitamente la
   activación histórica del piloto privado I2-U (2026-11-07, con
   dossier y rollback registrados). Precisada en PLAN-2 y en el README
   a «exposición remota vigente», conservando la activación histórica
   en su fase.
10. Este informe citaba el aviso AN-KLA `context_manifest_missing`
    sin explicar su procedencia. Verificado en este worktree:
    `context status` e `integration status` dan `ok: true` con ese
    warning, `repo_context: linked_worktree` y `store_presence:
    absent`. La auditoría del capitán registra en el checkout
    principal preflight `ok: true` sin warning y `status`/`verify` en
    revisión 32. El aviso es propio del worktree enlazado (la tienda
    vive en el checkout principal), no evidencia daño en `AGENTS.md`
    ni en la tienda. Sin reparación de AN-KLA (fuera de alcance).

## Ronda adversarial r1 (agy) — disposiciones

Revisión de sólo lectura emitida por agy (Claude Opus 5.5 Medium,
según su texto capturado) con veredicto **fix-and-retry** y 8
hallazgos. Texto íntegro, snapshot, SHA de captura verificado y
disposición individual en
`docs/reviews/2026-11-docs-current-state-adversarial-r1.md`. Sin
excepción vigente para esta revisión: la excepción puntual del
2026-11-09 se limitó a fix-i5-despacho. Límites declarados por el
propio revisor: lectura parcial de guías, AN-KLA no leído ni
ejecutado; runtime, red, CI y protección de rama sin comprobar;
suites sin re-ejecutar. La revisión r2 posterior cerró estas
disposiciones (veredicto proceed; ver «Cierre r2»).

## Cierre r2 (agy)

Revisión r2 de agy en sesión nueva (Gemini 3.8 Flash; captura
verificada sha256 `ee024cf9...cf66`; diff congelado `50eff6ca...b9ee`;
informes previos `5bcff861...800c0` y `081ec1c8...566`): veredicto
**proceed**, 0 hallazgos nuevos, 8/8 de r1 cerradas. Registro
completo en
`docs/reviews/2026-11-docs-current-state-adversarial-r2.md`.
Sobreafirmación del revisor consignada y no heredada: escribió «el
sistema se declara inactivo» sin comprobar runtime; sólo se acredita
runtime actual desconocido. El proceed es cierre documental de la
ronda: no constituye aceptación humana, commit ni runtime.

Disposiciones (todas contrastadas contra fuentes locales):

- r1-1 (excepción de revisor omitida): corregido. El registro y
  PLAN-2 distinguen ahora la exigencia de proceed agy pre-merge de la
  ola fix-i5-jobs-frontera (2026-11-08; `disposicion-ronda4.md`
  registra la exigencia del Operador, no la ocurrencia de ese proceed)
  de la excepción puntual sin agy de fix-i5-despacho (2026-11-09;
  `docs/reviews/evidence/fix-i5-despacho/disposicion-excepcion-revisor.md`;
  cuerpo de `599564b`). El residual MED aceptado el 2026-11-08 quedó
  corregido en `599564b` y ya no se presenta vigente.
- r1-2 (cifra 299 fuera de lugar): corregido. «299 OK» queda
  atribuido a la review inicial de I5 (base `0069f35`); el cierre de
  la ola de correcciones consta 376 tests OK (skipped=1) en dos
  pasadas (`green-intento-4.txt`); el HEAD final no hereda cifras sin
  evidencia (no se re-ejecutaron suites).
- r1-3 (fecha de la capa técnica): corregido. date = 2026-11-10 (UTC
  real) y time_utc re-tomado; `report_sha256` y huella recalculados.
- r1-4 (estados de decisiones y límites de activación): corregido.
  Informe, README y PLAN-2 citan los estados exactos: D-02..D-04
  «formalizada (propuesta I2-D)», sin aceptación registrada;
  D-05/D-06b/D-07 pendientes; activación histórica I2-U separada de la
  autoridad de D-02..D-04 y del runtime actual; I6 sin candidato
  evaluado ni promoción (D-06b pendiente).
- r1-5 (inconsistencia PLAN-2/registro): corregido. I2 dice ahora
  «(propuesto al Operador)» y la cabecera del registro declara cómo se
  leen las filas abreviadas y las citas de encargos (autorizan
  ejecución; no son aceptación de fase).
- r1-6 (alcance de `git diff --check`): corregido. La frase se limita
  a «cambios rastreados»; los informes nuevos sin seguimiento se
  verificaron aparte (espacios finales y marcadores de conflicto: sin
  hallazgos).
- r1-7 (autoprobación): corregido. La capa técnica de este informe usa
  DECISION = fix-and-retry (r1 vigente, r2 pendiente); ningún acto del
  ejecutor se cuenta como aprobación.
- r1-8 (procedencia de cifras de suite): corregido. El registro dice
  «árbol de trabajo sobre la base `head_sha` de cada review (commit
  previo al de la fase)»; la correspondencia head_sha/commit de fase
  consta en el informe r1.

## Verificados sin hallazgo (ronda propia)

- README: 12 casos golden (`tests/golden/casos.json`), motor
  llama.cpp 0.8.0 (b11960) contra F0, puerto 8091 contra
  `run/serve.sh`, tools MCP v1 (`health`, `infer_text`,
  `infer_vision`) contra `src/mcp_server.py`, «PLAN-1 cerrado en
  v0.1.0» — consistentes.
- La fila D-10 «pendiente cablear en SSE (I1-VR)» no es contradictoria:
  el gateway SSE no cablea `src/transcripciones.py`; sólo lo hace
  `examples/conversacion_voz_local.py`.
- El checkbox de I4-UI no contradice D-05 (pendiente): I4-UI produce el
  handoff en este repo (`docs/contracts/handoff-frontexpert-v2.md`);
  la adopción de UI ocurre en frontExpert con D-05 y encargo separado.
- El alcance de D-01 («no autoriza... ninguna iteración posterior»)
  obligó a precisar la redacción: la ejecución quedó autorizada por
  encargos sucesivos por fase, no por D-01 sola.

## Diff y HEAD

- HEAD sin cambiar: `ce23ac78fde4047184de4f46506674e5d4438fe1`.
- Rutas cambiadas (todas dentro de la lista autorizada): `README.md`,
  `project-manifest.yaml`, `.skevi/usage-guide.md`,
  `docs/roadmap/registro-avance.md`,
  `docs/plans/PLAN-2-servicio-compartido.md` y este informe nuevo.
- Totales del diff (sin los informes): 5 archivos con +119
  inserciones y 18 eliminaciones (`git diff --stat`); este informe y
  el de la ronda r1 son archivos nuevos sin rastrear. Revisión línea
  a línea del diff contra la base realizada.

## Gates (salidas reales sobre el árbol final)

Comandos exactos de AGENTS.md, ejecutados desde la raíz del worktree;
`alcance` resume qué valida cada uno según su propio gate:

```text
$ python3 scripts/check_sizes.py
OK — 453 archivos de texto dentro de límites; estructura y hogares
canónicos verificados; ruta de lectura 1819/2000; gate/v14
(2026-11-07) — exit 0
alcance: límites por archivo, exenciones, archivos requeridos, hogares
canónicos y presupuesto de ruta de lectura.

$ python3 scripts/check_plans.py
OK — 2 plan(es) verificados (estructura E1-E6) — exit 0
alcance: estructura E1-E6 de los planes declarados (PLAN-1 y PLAN-2).

$ python3 scripts/check_templates.py --manifest docs/MANIFEST.json --installed .skevi/corpus-installed.json
OK — al día: versión vigente corpus/v11 — exit 0
alcance: corpus instalado contra la copia local del manifiesto.

$ python3 scripts/check_templates.py --manifest scripts/MANIFEST.json --installed .skevi/scripts-installed.json
OK — al día: versión vigente gate/v14 — exit 0
alcance: scripts de gate instalados contra su manifiesto local.

$ git diff --check
(sin salida) — exit 0
alcance: whitespace roto y marcadores de conflicto en los cambios
rastreados; los informes nuevos sin seguimiento se verificaron aparte
(espacios finales y marcadores de conflicto: sin hallazgos).

$ python3 scripts/check_reports.py
OK — 27 reporte(s) con capa técnica verificada; 1 exento(s) — exit 0
alcance: forma de las capas técnicas en docs/reviews/, incluidas las
de este informe y del registro r1 (report_sha256 reproducible).
```

## Límites de la conciliación

- Runtime no comprobado: ningún servidor arrancado ni sondado; el
  estado vigente de motor (8091), gateway (8092) y piloto (8443) queda
  fuera de lo acreditado.
- Omisiones documentales no contradictorias, dejadas por minimalismo y
  listadas como pendiente: la sección «Estructura» y «Cómo consumir»
  del README no mencionan las superficies v2 (gateway 8092, MCP v2,
  CLI, jobs, vigilancia, evaluación) ni `run/serve_pilot.sh`.
- `docs/roadmap/decisiones-servicio.md` no está en las escrituras
  autorizadas: sin cambios (contraste r1: D-02..D-04 constan
  «formalizada (propuesta I2-D)», no como pendientes ni aceptadas;
  D-05/D-06b/D-07 pendientes).
- El corpus y los manifiestos del kit van sellados por hash: no se
  editan ni se re-copian; el gate de plantillas dice «al día contra la
  copia local del manifiesto», no contra el origen en vivo.
- Los números de suite (275/288/299/308) se citan de las reviews de
  cada fase, observados en árboles de trabajo sobre la base head_sha
  de cada review (commit previo al de la fase); 299 corresponde a la
  review inicial de I5 y el cierre de su ola consta 376 tests OK
  (skipped=1) x2 en `green-intento-4.txt`. No se re-ejecutaron suites
  en esta tarea (prohibido por el contrato).

## Pendientes

- Aceptación humana del resultado documental: pendiente; el proceed de
  r2 no la sustituye.
- Sin commit: requiere autorización vigente del Operador.
- Aviso `context_manifest_missing` del preflight AN-KLA: reportado al
  capitán; su reparación no corresponde a esta tarea (procedencia y
  límite en el hallazgo 10).

## Capa técnica

```text
id = docs-current-state-2026-11-10-cierre-r2
date = 2026-11-10
time_utc = 08:32:40Z
head_sha = ce23ac78fde4047184de4f46506674e5d4438fe1
model = glm-5.3-flash (zai-coding-plan, autodeclarado, nunca prueba)
session = herdr/LFM3-Omni · docs-current-state (agente OpenCode)
STATE = OK
GATE = 5/5 gates AGENTS OK y git diff --check limpio sobre los cambios rastreados; informes nuevos verificados aparte; check_reports valida la capa tecnica de este informe
PENDING = aceptacion humana del resultado (Operador); commit sin autorizar; runtime vigente desconocido (limite declarado, no comprobado)
DECISION = proceed (veredicto r2 de agy, cierre documental; sin aceptacion humana, commit ni runtime)
OPERATIONS = ninguna fuera del entorno local; sin commit, push, PR ni merge
AUTHORITY = contrato de tarea docs-current-state del capitán en Herdr; AGENTS.md del proyecto; revisiones r1 y r2 capturadas (sha256 0e214f69...23fcd y ee024cf9...cf66)
RISK = bajo: cambios documentales mínimos, sin producto, contratos ni historia
EVIDENCE
- python3 scripts/check_sizes.py sobre el arbol final -> pass
- python3 scripts/check_plans.py sobre el arbol final -> pass
- python3 scripts/check_reports.py sobre el arbol final -> pass
- check_templates corpus (docs/MANIFEST.json) sobre el arbol final -> pass
- check_templates scripts (scripts/MANIFEST.json) sobre el arbol final -> pass
- git diff --check sobre los cambios rastreados -> pass
- informes nuevos sin seguimiento verificados aparte (espacios finales y marcadores) -> pass
- captura r1 verificada (sha256 0e214f6961fd...23fcd coincidente) -> pass
- exigencia del proceed agy (disposicion-ronda4.md, 2c83934) distinguida de su ocurrencia, sin evidencia local de esta; frases corregidas -> pass
- excepcion 2026-11-09 contrastada con disposicion-excepcion-revisor.md y cuerpo de 599564b -> pass
- cierre de ola I5 contrastado con green-intento-4.txt (376 tests, skipped=1, dos pasadas) -> pass
- captura r2 verificada (sha256 ee024cf9932...cf66 coincidente) -> pass
- veredicto r2 proceed con 0 hallazgos nuevos y 8/8 r1 cerradas -> pass
- sobreafirmacion de runtime del revisor r2 consignada y no heredada -> pass
- rutas cambiadas dentro de la lista autorizada del contrato -> pass
- historial skevi-gate.json 1300/1800/2000 verificado con git log -p -> pass
- registro kit-2026-11-09 contrastado con installed.json y MANIFESTs -> pass
- estados plan/roadmap reconstruidos solo desde commits y reviews -> pass
report_sha256 = e3d7293d7ca4acf6412fa3f15deaac9769799a90e16e4ee5d402411763a489d4
```

## Huella del informe

SHA-256 (shasum -a 256, calculado externamente sobre las líneas
1 a 322 de este archivo, sin la presente sección, para evitar
autorreferencia):

466a866aed890cf605b90ff96c20602de3897b09b520942e889bacf5a6213ff1
