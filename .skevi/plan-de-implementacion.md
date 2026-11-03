# Plantilla — plan de implementación

> Artefacto de escala: existe sólo cuando el trabajo cruza múltiples tareas,
> sesiones o agentes — la norma y su umbral viven en `04` §1 y ADR-010; esta
> plantilla no legisla. Una tarea sola se ejecuta con su TAREA.
> Fuente única: cuando existe, la TAREA lo referencia y **el plan es dueño
> de los criterios** (DoD, steps).

```text
PLAN <id> — <nombre>
Autoriza: <ADR-<n> | CONTRATO | SPEC que lo habilita>
Clase de tarea: <Bounded | Architectural> — disparadores de 01 §2

Restricciones globales (verbatim del artefacto que autoriza):
- <línea copiada byte a byte, con su referencia de origen>

TAREAS:
TAREA <id-1>
  Consumes: <CONTRATO/SPEC existente al que resuelve — o "crea CONTRATO <x>">
  Produce:  <CONTRATO/SPEC/archivo que existirá al cerrar>
  Lote:     <folio del dossier de lote — sólo si la TAREA incluye push o merge>
  Steps:
  - [ ] <paso> — verificación: <comando real o criterio de paso explícito>
TAREA <id-n>
  (repetir la estructura completa: Consumes, Produce, Steps)

DoD: <checks ejecutables del plan completo>
Partición: <sólo si excede el límite: enlace al sub-plan>
```

Reglas:

- Cada Consumes/Produce resuelve a un CONTRATO/SPEC real del repo, o declara
  cuál creará — verificado como el check CONTRATO↔código de `04` §9, leyendo
  el código ahora, no de memoria.
- Cada step referencia un archivo, comando o test real del proyecto, con su
  criterio de paso. Un step sin verificación es prosa, no un step.
- Prohibido: código de producción, placeholders (`TBD`, `TODO`), "similar a
  la TAREA N", prosa sin criterio de verificación.
- En un plan, la TAREA que incluya `push` o `merge` declara `Lote:`. Si su
  campo `Permitido:` nombra esas operaciones, `check_plans` lo exige (regla
  E6, ADR-045). `Lote:` es el folio de un dossier de lote (estándar §4.3, `04`
  §7) presentado al gate **antes** del primer efecto. La aceptación se
  registra una vez, en un lugar consultable, contra ese folio; cada operación
  se revalida justo antes de su efecto. El campo no prueba la aceptación: sin
  ella registrada y vigente, la operación sigue gateada. Procedencia: ADR-044
  (lote) y ADR-045 (campo y regla); razón: dos integraciones de Skevi (PR
  #78/#79) se hicieron con permiso de sesión y sin aceptación por folio. Forma
  mínima (capa humana; la técnica sigue el reporte en dos capas):

  ```text
  LOTE <folio> — <rama> → <destino>
  1. commit(s) de la rama; condición: gates locales OK
  2. push ordinario <rama> → <remoto>/<rama>; condición: gates OK en el head
  3. PR <rama> → <destino>
  4. merge del PR con <método: merge | squash | rebase>; condición: CI
     requerido verde y revisión independiente registrada del head final,
     ambos sobre el mismo SHA
  Evidencia: <gates y checks ya ejecutados>. Riesgos: <lista>.
  Recomendación: <aceptar | no aceptar, y por qué>.
  Fuera del lote: force-push, rebase compartido, tags, releases, borrados.
  Vigencia: hasta <evento o fecha>; revocable en cualquier momento.
  Aceptación: quién, cuándo, «acepto <folio>», antes del paso 1; registro
  consultable: <comentario del PR | registro de revisión | otro>.
  ```

- Límite: 300 líneas como plantilla derivada (estándar §3.4). Si excede, se
  parte en sub-planes vinculados desde este encabezado.
- Hogar: `docs/plans/` o el equivalente declarado por el proyecto adoptante;
  si el adoptante activa la clave `plans` en `skevi-gate.json`, este formato
  es el que `scripts/check_plans.py` verifica (ADR-014).
