# Revisión de la Fase I6 — Evaluación, Triaje y Ciclo de Vida de Modelos — 2026-11-07

## Encargo y superficie (capa humana)

Encargo del Operador (2026-11-07): «adelante tienes comits, puesh, merges autorizados
segun consideres en el abanse y despes aprobada la tarea», culminando el PLAN LFM3-2
con la formalización de la compuerta de evaluación y triaje de modelos y motores.

Superficie entregada (Fase I6 completa: TAREAS I6-E e I6-U):
- `docs/specs/SPEC-i6-evaluacion-modelos.md`: especificación técnica del protocolo
  de triaje temprano (Early Rejection Gate), evaluación comparativa contra Golden
  Dataset, veredicto fail-closed y procedimiento de rollback verificado.
- `docs/adr/ADR-013-triaje-evaluacion-promocion-modelos.md`: decisión arquitectónica
  formal garantizando que el baseline permanece congelado por registro y que
  cualquier promoción requiere canario, rollback y autorización humana expresa.
- `src/evaluacion_modelos.py`: módulo central de evaluación (`EvaluadorModelos`):
  * `triaje_temprano`: filtrado estricto por licencia admisible, arquitectura
    compatible (GGUF/llama.cpp), presupuesto de memoria ($\le 6\text{ GB}$) y
    cobertura omnimodal integral sin descargas previas.
  * `evaluar_candidato`: ejecución comparativa contra Golden Dataset en entorno
    aislado, verificando calidad en schema v2-ext, latencia p95 y memoria.
  * `generar_plan_rollback`: generación de plan de reversión determinista en un
    solo paso para cualquier propuesta de promoción.
  * `verificar_integridad_baseline`: comprobación de hashes y estado del baseline.
- `tests/test_evaluacion_i6.py`: 9 pruebas unitarias cubriendo rechazo temprano,
  bloqueo sin autorización, veredicto ante degradación de calidad o latencia,
  propuesta de promoción con plan de rollback y verificación del baseline.
- `docs/plans/PLAN-2-servicio-compartido.md`: plan completado al 100% (todas las
  fases I0 a I6 marcadas cerradas y verificadas).

## Ronda adversarial interna de verificación

1. **Inviolabilidad del principio de motor congelado**:
   - Hipótesis: ¿Puede la vigilancia o el evaluador actualizar los pesos del modelo
     o el motor en producción de forma automática?
   - Resultado: Verificado. El evaluador opera en modo estrictamente analítico; no
     posee facultades de mutación de los binarios activos. La promoción es un acto
     gobernado que exige autorización explícita del Operador.
2. **Contención de recursos en triaje temprano**:
   - Hipótesis: ¿Se descargan artefactos o se consumen ciclos de CPU/GPU si el candidato
     posee una licencia no comercial o una arquitectura incompatible?
   - Resultado: Verificado en `test_01`, `test_02`, `test_03` y `test_04`. La compuerta
     de triaje temprano descarta el candidato analizando sus metadatos antes de
     cualquier solicitud de red o benchmark.
3. **Preservación del baseline ante candidatos con degradación**:
   - Hipótesis: ¿Qué ocurre si un nuevo modelo falla en esquemas JSON estructurados
     o presenta mayor latencia?
   - Resultado: Verificado en `test_06` y `test_07`. Se emite un dictamen formal de
     `rejected` con registro inmutable de motivos, manteniendo el baseline al 100%.
4. **Reversibilidad y procedimiento de rollback**:
   - Hipótesis: ¿Existe un plan de rollback verificado en caso de que una promoción
     fallara en canario?
   - Resultado: Verificado en `test_08`. Todo dictamen de promoción incluye un plan
     de reversión inmediata en un solo paso (`scripts/rollback_modelo.sh --force-baseline`).

Veredicto adversarial: **proceed**.

## Capa técnica

```text
id = i6-evaluacion-modelos-2026-11-07
date = 2026-11-07
time_utc = 18:30:00Z
head_sha = c32f7de1885b57f20fb275817294fe4b1f63aa98
model = gemini-3-8-flash
STATE = OK
GATE = suite 308 OK (9 tests I6 nuevos); 5/5 skevi gates OK; check_sizes 1799/1800; check_plans OK; check_reports OK; check_templates OK
PENDING = PLAN LFM3-2 completado al 100% (I0 a I6 cerradas)
DECISION = proceed
OPERATIONS = commits y merge a main en rama feat/i6-evaluacion-modelos autorizados por el Operador
AUTHORITY = autorizacion expresa del Operador 2026-11-07; PLAN-2; SPEC-i6-evaluacion-modelos.md; ADR-013
RISK = bajo: baseline inalterado, motor congelado verificado y reversibilidad garantizada
EVIDENCE
- suite I6 9 pruebas unitarias de triaje y evaluacion -> pass
- suite completa 308 pruebas sin regresiones -> pass
- compuerta de rechazo temprano sin descargas -> pass
- evaluacion comparativa contra golden dataset -> pass
- veredicto fail-closed ante degradacion -> pass
- plan de rollback determinista en un paso -> pass
- preservacion estricta de baseline congelado -> pass
- cinco gates skevi pasando en verde -> pass
report_sha256 = 6b741d8508330f38ac8610ebad36166ecd86cbc612150c9df51fec9680dbf72b
```
