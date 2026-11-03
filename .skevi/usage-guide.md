# Uso de Skevi en este proyecto

**Proyecto:** LFM3-Omni
**Fase actual:** F0
**Procedencia de las plantillas:** registrada en `installed.json`
(esquema `skevi/template-install/v1`), en este mismo directorio (`.skevi/`)
una vez copiado — única fuente de verdad de qué se copió, de dónde y con
qué versión; no la dupliques aquí.

## Qué leer primero

1. `AGENTS.md` en la raíz — punto de entrada, enlaza a este archivo.
2. `docs/ai-agent-guide/00-INDICE.md` — fases F0→F3 y reglas de aplicación.
3. `docs/estandar-diseno-software-github.md` — capa normativa transversal.

## Desviaciones de este proyecto respecto al estándar por defecto

Ninguna declarada todavía: rigen los límites por defecto (800 líneas por
archivo, 200 para instrucciones de agentes, 300 para README y plantillas).
El presupuesto de la ruta de lectura está en `skevi-gate.json` de la raíz.

## Idiomas elegidos

Fuente normativa: estándar §3.1 (ADR-015, precisión ADR-029).

- Comunicación humana predeterminada: español.
- Producto: documentación y contratos en español; interfaz API, esquemas e
  identificadores en inglés (compatibilidad OpenAI y MCP).
- Comentarios/docstrings: español.
- Excepciones a identificadores nuevos en inglés: ninguna.

La preferencia de conversación no modifica estas elecciones persistentes.

## Verificación local

```bash
python3 scripts/check_sizes.py
python3 scripts/check_plans.py
python3 scripts/check_reports.py
```

`check_plans` y `check_reports` son fail-closed por configuración: mientras
`skevi-gate.json` no declare sus claves (`plans`, `reports`), no comprueban
nada — se activarán en F1 al crear planes y rondas.

## Dónde están los ADRs y specs de F1

`docs/adr/` (índice en `docs/adr/00-INDICE.md`), `docs/specs/`,
`docs/contracts/` y el registro de rondas en `docs/reviews/`.

## Drift contra el canon

Los registros de instalación viven en `.skevi/`. La comparación corre contra
los manifiestos fuente copiados en este repositorio (`docs/MANIFEST.json` y
`scripts/MANIFEST.json`), no contra el origen en vivo:

```bash
python3 scripts/check_templates.py \
  --manifest /Users/krisnova/www/aria/skevi/templates/skevi/MANIFEST.json \
  --installed .skevi/installed.json
python3 scripts/check_templates.py \
  --manifest scripts/MANIFEST.json --installed .skevi/scripts-installed.json
python3 scripts/check_templates.py \
  --manifest /Users/krisnova/www/aria/skevi/docs/MANIFEST.json \
  --installed .skevi/corpus-installed.json
```

`OK` dice «coherente con esa copia local del manifiesto», no «al día contra
el origen ahora mismo». Actualizar la copia del manifiesto es una lectura
nueva del origen, deliberada y con autorización si el proyecto la exige.

## Gate de push (local) y gate en CI (opcional)

Activación local — config, no viaja con el clon; repetir en cada clon
fresco:

```bash
git config core.hooksPath scripts/hooks
```

Gate en CI: pendiente de decisión (el proyecto aún no tiene remoto ni
protección de rama; se definirá en F2/F3 con control positivo y check
requerido antes de contarlo como gate de verdad).

## Dependencias activas del ecosistema

- **AN-KLA Memory:** instalada (2026-11-03) — memoria local gobernada en
  `.an-kla/memory/`, pipeline propose → plan-write → commit-write-plan,
  sin bloque de contexto en `AGENTS.md` (lectura vía `an-kla retrieve`).
- Otras dependencias declaradas: llama.cpp (Homebrew) y el modelo
  `LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M` (Hugging Face) — artefactos externos
  de régimen congelado por registro; sus versiones vigentes y el comando de
  arranque viven en `docs/f0-analisis-y-requerimientos.md`.

## Plantilla opcional: árboles congelados

`frozen-trees.md` **no** se copió: hoy no hay árbol congelado dentro del
repositorio — el motor y los pesos son artefactos externos al árbol, y su
régimen se registra por versión en F0. Si en el futuro se vendorizan pesos
o código de terceros dentro del repo, cópiala entonces y sigue sus
instrucciones (ADR-033).
