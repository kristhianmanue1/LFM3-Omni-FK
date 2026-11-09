# Registro de adopción de kit — corpus/v11 + plantillas/v23 (2026-11-09)

## Origen

- Hub: `/Users/krisnova/www/aria/skevi` @ `d6cb3066a269a24ac427580fd20cd521eb5c3d2c`.
- `docs/MANIFEST.json` del hub: `corpus/v11` (2026-11-08T12:55Z).
- `templates/skevi/MANIFEST.json` del hub: `plantillas/v23` (2026-11-08T12:55Z).
- `scripts/MANIFEST.json` del hub: `gate/v14` — sin cambio; no se toca.

## Delta corpus v10 → v11

- Un archivo: `docs/ai-agent-guide/04-ejecucion-y-verificacion.md`
  (286 → 306 líneas). Añade: regla de archivos `Ruling:` para planes de
  varias tareas (ADR-049) y vocabulario de disposiciones por ronda
  (ADR-050). Verificación: los 8 archivos del corpus coinciden byte a
  byte con los hashes del manifiesto v11.

## Delta plantillas v22 → v23

- `.skevi/plan-de-implementacion.md`: re-copiado del hub (añade la
  sección opcional «Review Focus», ADR-051; el diff contra la copia
  previa era 0 eliminaciones, copia v22 exacta).
- `frozen-trees.md`: NO adoptado — el propio archivo es opt-in («sólo si
  tu proyecto tiene árboles congelados») y este proyecto no los tiene
  (el motor congelado de ADR-001 es artefacto externo, no un árbol del
  repo).
- `.skevi/usage-guide.md`: NO se re-copia — es la instancia llenada del
  proyecto (elecciones locales), no la plantilla vacía.
- `installed.json`: regenerado como `skevi/template-install/v1` versión
  `plantillas/v23`, con las copias propias del proyecto y
  `customized` declarando los records propios (usage-guide,
  scripts-installed, corpus-installed, installed).

## Presupuesto de ruta de lectura: 1800 → 2000

- **Procedencia: orden del Operador, 2026-11-09**, consultado
  explícitamente al constatar que adoptar corpus/v11 da 1819 líneas
  sobre un límite vigente de 1800.
- El registro de memoria del proyecto que afirmaba «subido a 2000 con la
  adopción gate/v14 (2026-11-07)» **no consta en el repo**: el historial
  de `skevi-gate.json` sólo muestra 1300 → 1800 (ajuste multimodal
  I1-V). Manda el estado verificado del repo.

## Gates tras la adopción

Ver `gates.txt`: sizes (421 archivos, ruta de lectura 1819/2000),
plans, reports, y las tres líneas de kit (corpus/v11, gate/v14,
plantillas/v23) en «al día», sin avisos de re-copia; `git diff --check`
limpio.
