# Revisión del plan de servicio compartido — 2026-11-04

## Encargo y superficie

El Operador autorizó producir y persistir el plan completo, afinar objetivo,
alcance, contratos y vigilancia, una ronda adversarial y después otra con
modelo externo mediante OpenCode configurado. No autorizó implementar,
activar red, instalar, commit, push, merge, tags ni escribir memoria.

Autor: agente principal de esta sesión. Primera revisión: subagente
plan_adversarial, fork_turns none. Recibió sólo encargo y rutas, sin historial
ni conclusiones del autor; leyó seis documentos, instrucciones y contratos
v1. Permitido: lectura y gates de documentación locales; sin red/escrituras,
modelo o Git mutativo. Su relectura recibió hallazgos y correcciones: conserva
separación de autoría, no es otra revisión fresca.

Segunda revisión: sesión OpenCode nueva, agente plan, modelo por defecto
configurado zai-coding-plan/glm-5.3-flash, sin --model ni --continue.
Carpeta efímera privada con packet adjunto numerado y hashes; no secretos,
historial ni conclusiones de la primera ronda. permission deny global y por
agente, sin tools, subagentes, red del modelo ni ediciones. El CLI requiere
acceso a su proveedor y almacenamiento de sesión; no es aislamiento OS.
La frescura comprobada es de sesión/entrada adjunta, no una auditoría del
prompt de sistema resuelto: pueden aplicar preferencias globales del CLI.
El acceso del runtime a configuración/log se autorizó por el entorno tras
EPERM inicial. La primera invocación --help no hizo revisión del plan.
Presupuesto: una pasada y como máximo una comprobación de correcciones;
paquete de 82 526 bytes, sin inferencia del motor local.

## Ronda fresca interna y disposiciones

| ID | Sev. | Problema e impacto | Corrección y estado |
|---|---|---|---|
| R1-01 | HIGH | Desconexión general cancelaba jobs asíncronos; un 202 perdido hacía inviable su recuperación | General limita desconexión a H/M interactivo; J fija admisión durable y recuperación por clave; fixture en I5. Cerrado por relectura |
| R1-02 | MED | Envelope terminal no representaba cancellation_pending; recepción podía confundirse con detención | cancel separa estado de operación, cancellation_status y target_state. Cerrado por relectura |
| R1-03 | HIGH | I6 exigía modalidad/canario incluso en actualización de motor o rechazo temprano | DoD condicional: rechazo documentado, promoción de motor/modelo y modalidad nueva separados. Cerrado por relectura |
| R1-04 | MED | Máquina de ciclo de vida aún no tenía triaged -> rejected | Transición con evidencia mínima sin descarga/benchmark/canario. Cerrado por relectura |

Decisión final del revisor interno: proceed documental; sin HIGH/BLOCKER ni
MED abiertos. No acreditó mediciones históricas ni propiedades del software
futuro. Los gates no refutan por sí mismos contradicciones semánticas.

## Precisiones del autor incorporadas antes de ronda externa

- I1 tiene credencial de prueba sólo loopback; I2 la sustituye por identidad
  revocable, sin modo de prueba remoto.
- Resultado de propuesta tool_calls representado, nunca ejecución.
- Registro de progreso por iteración con owner, reviewer, evidencia y gate;
  todas las iteraciones están not_started en esta planificación.

## Ronda externa

Entrada exacta y configuración: evidence/plan2-external-r1-input.json.
Packet SHA-256:
602323e487eda25644e279eded1a2d7dc21eb2dbfee4736a15254d929fdd8e2c.
Sesión: ses_e584e24baffelyzy2YfTE4pHIF.
Primera pasada externa completada: exit 0, fix-and-retry. Respuesta íntegra
saneada en evidence/plan2-external-r1.md, eventos de metering en
plan2-external-r1-runtime.json. Configuración del CLI comprobada; identidad
del modelo remoto no atestada por estos eventos, autodeclaración GLM.
El trace no contiene llamadas a herramientas. Incluye mensaje final de
modo plan además de la revisión; no se trata como otro revisor.

| ID externo | Sev. atribuida | Disposición del autor para comprobar |
|---|---|---|
| F-01 | ALTA | I0-R separa fixes compatibles v1 de nuevas restricciones sólo en adaptador v2; regresión por contrato |
| F-02 | ALTA | D-04 fija A: admisión con política final y tasa de rechazo; B: capacidad aislada autorizada. Sin bypass de producción |
| F-03 | MEDIA-ALTA | ADR I2-D asigna mecanismo/allowlist/permisos de egreso; I2-P implementa y verifica. Inviable bloquea remoto |
| F-04 | MEDIA | I0-D produce registro de decisiones, D-01 aceptada y posteriores pendientes hasta su gate |
| F-05 | MEDIA | Mapea cancel según estado objetivo y mecanismo nativo MCP; H DELETE explícito, identidad verificada |
| F-06 | MEDIA | Desacuerdo parcial: subconjunto OpenAI no exige ignorar parámetros. Rechazo explícito y fixtures por SDK/version/config; no promesa universal |
| F-07 | MEDIA | Payload normalizado/defaults y JCS RFC8785; reutilizar clave tras 24 h crea job nuevo |
| F-08 | MEDIA-BAJA | Backend W dueño de asociación usuario-request; H no promete identidad humana sin token delegado |
| F-09 | BAJA | Envelope de resultado J expresado en oración completa |
| F-10 | BAJA | I2-D mantenedor/suplente/canal; I2-V verifica; blocked es anotación con estado previo y resolución |
| F-11 | BAJA | SPEC I1-D fija puerto configurable y prueba colisión |
| F-12 | BAJA | Errores explican plazos por perfil/version y capabilities |

Impactos/contraejemplos completos permanecen en el informe externo. No se
aceptó la hipótesis de que todos los SDK envían muestreo por defecto como
hecho probado; el propio revisor la declaró hipótesis. Los fixtures deben
resolverlo antes de afirmar compatibilidad.

Comprobación externa de correcciones: nueva sesión con hallazgos previos,
disposición del autor y seis documentos actuales completos. No es ciega.
Entrada en evidence/plan2-external-r2-input.json. Completada con exit 0;
sesión ses_e5844c297ffeOUV5nwy13rytP6. Informe íntegro en
 evidence/plan2-external-r2.md: F-01..F-12 cerrados, disputa F-06 resuelta,
sin nuevos HIGH/BLOCKER; veredicto proceed. No ejecutó pruebas/gates.
El trace contiene sólo step_start/text/step_finish, ninguna tool call.
Model/provider en su texto son autodeclarados; la configuración sí fue
leída, pero no se exportó el prompt resuelto ni una atestación del proveedor.
Metering de step_finish R2: input 26067, output 2327, reasoning 10644,
cost 0; no representa factura comprobada ni total del texto final adicional.

Relectura interna de las correcciones externas: proceed, sin HIGH/BLOCKER
ni MED abiertos. LOW opcional: frase de secuencia aún decía sólo modalidad;
se corrigió a candidato o modalidad. Esa precisión posterior al packet R2
no cambia tareas, contratos ni DoD; se declara como delta y se incluye en
el manifiesto final evidence/plan2-final-artifacts.json.
Paquete de 84 344 bytes, SHA-256
48b49aa176089ed0c3ad624574b78a47a64cb21ad778eb8f84b050b3ac4a0bc3.

Metering parcial de la primera pasada: evento step_finish informa input
26369, output 2970, reasoning 16777 y cost 0; el texto final adicional no
trae otro evento de metering. No acredita factura cero ni conteo completo.

## Estado de la planificación

Plan propuesto: docs/plans/PLAN-2-servicio-compartido.md; seis documentos
de diseño/aceptación/ciclo de vida. Los v1 locales siguen vigentes.
Sin implementación, tests nuevos, vigilancia programada ni cambios de motor.
La autoridad pendiente de adopción/ejecución se enumera como D-01..D-07.

## Cierre y límites

Plan de 21 tareas, I0–I6, persistido; objetivo/alcance, contrato general,
perfiles y ciclo de vida separados por propósito. Cinco gates y chequeo
adicional de archivos nuevos se ejecutan sobre esta entrega documental.
Autor produjo; subagente fresco y GLM configurado revisaron. Relecturas
recibieron hallazgos/correcciones, no se presentan como revisiones ciegas.
No quedan hallazgos materiales abiertos del plan. Decisiones D-01..D-07
pertenecen a su futura adopción/ejecución: no son pruebas operativas hechas.
Vigilancia diseñada, no activada; todos los incrementos not_started.
No hubo commit/push/merge/tag/release, instalación ni escritura AN-KLA.
No se arrancó ni modificó motor/modelo. Los dos cambios documentales de la
sesión previa se conservaron y README enlaza el plan como propuesta.

## Capa técnica

Se añade tras verificar los gates finales; el hash cubre sólo el fence.

```text
id = lfm3-plan2-documentary-close
date = 2026-11-04
time_utc = 18:08:47Z
head_sha = 4572164270073431a765e53e1353a233b0897dec
model = author not attested; external zai-coding-plan/glm-5.3-flash configured and self-declared
session = internal plan_adversarial; external ses_e584e24baffelyzy2YfTE4pHIF; check ses_e5844c297ffeOUV5nwy13rytP6
STATE = OK
GATE = Complete proposed incremental plan, general contract and profiles, lifecycle watch design, fresh internal review and external configured-GLM review with dispositions; documentation only
EVIDENCE
- Six planning documents and 21 tasks -> pass
- Fresh internal review followed by correction verification: proceed -> pass
- OpenCode configured-default review: 12 findings resolved, final proceed, exit 0 -> pass
- Input packet archives reconstructed and SHA256 verified -> pass
- python3 scripts/check_sizes.py -> pass
- python3 scripts/check_plans.py -> pass
- python3 scripts/check_reports.py -> pass
- python3 scripts/check_templates.py --manifest docs/MANIFEST.json --installed .skevi/corpus-installed.json -> pass
- python3 scripts/check_templates.py --manifest scripts/MANIFEST.json --installed .skevi/scripts-installed.json -> pass
- git diff --check plus explicit new-authored-file whitespace and reference checks -> pass
DECISION = proceed
PENDING = none for documentary planning; D-01..D-07 remain execution/adoption decisions, not operational claims
AUTHORITY = Operator 2026-11-04: write plan and run internal/external reviews; no implementation or activation
RISK = No runtime capacity, isolation, compatibility, surveillance or domain validation demonstrated by this documentary close
report_sha256 = c2648c5b8e801d15e785b34044a96b94446d08503e40c9368d12a59ca470558e
```
