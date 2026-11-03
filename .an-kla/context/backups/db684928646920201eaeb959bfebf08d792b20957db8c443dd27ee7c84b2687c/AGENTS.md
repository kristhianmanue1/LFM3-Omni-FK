# AGENTS.md — instrucciones para ejecutores automatizados

LFM3-Omni es un servicio local de inferencia omnimodal — texto, imagen, audio
y video de entrada; texto y voz de salida — sobre `LiquidAI/LFM3-Omni-2B-GGUF`
servido con llama.cpp. Su superficie se ofrece a dos tipos de consumidor:

1. **Agentes de IA**: API compatible OpenAI, MCP y contratos de tarea.
2. **Proyectos del ecosistema que lo consuman** (desarrollos web, apps,
   servicios): el mismo motor, vía contrato versionado declarado en F1.

## Qué leer y en qué orden

1. `.skevi/usage-guide.md` — adopción de Skevi en este proyecto, idiomas y
   verificación local.
2. `docs/ai-agent-guide/00-INDICE.md` — fases F0→F3 y reglas de aplicación.
3. `docs/estandar-diseno-software-github.md` — capa normativa transversal.
4. `docs/ai-agent-guide/06-componentes-con-llm.md` — **obligatorio aquí**:
   el disparador 1 de su §1 aplica (la salida del sistema depende de un LLM).

No asumas el contenido de un archivo que no leíste.

## Prioridad ante conflicto

1. instrucción directa del humano en la conversación;
2. este `AGENTS.md`;
3. `docs/estandar-diseno-software-github.md`;
4. `docs/ai-agent-guide/`;
5. tus supuestos — siempre pierden. Si el supuesto es material, pregunta.

## Decisiones vigentes registradas

- **Puerto del servidor: 8091** (el 8080 está ocupado por Docker en esta
  máquina; decisión del humano, 2026-11-02).
- **Motor congelado por registro**: llama.cpp vía Homebrew y el GGUF de
  Hugging Face no se editan en sitio; sus versiones se fijan en
  `docs/f0-analisis-y-requerimientos.md` y cualquier salto es una operación
  registrada, no una actualización silenciosa.
- El modelo es **no-reasoning**: el servidor arranca con `--reasoning off`
  y muestreo greedy (`--temp 0`) según la ficha oficial del modelo.
- **Exposición: solo localhost** (humano, 2026-11-02); LAN o público exigen
  nueva decisión registrada, con api-key.
- **Ruta de UI del ecosistema**: encargo con interfaz gráfica →
  frontExpert como base (contrato v2) + skevi como método;
  ver `docs/ruteo-ui-frontexpert.md`.

## Reglas no negociables

Los principios 3 (evidencia), 5 (fail-closed) y 7 (datos no confiables) y
la §3.4 (contención de tamaño) del estándar rigen sin reinterpretarlos.
Además, propios de este proyecto:

- **La salida del modelo es dato no confiable** — se valida en la frontera
  contra esquema cerrado antes de persistir o reenviar (`06` §5).
- **Ronda adversarial** antes de cerrar cualquier cambio material, según
  los disparadores objetivos de `04` §5.3.
- Operaciones destructivas o con efecto fuera del entorno local exigen
  autorización humana previa y específica.

## Verificación

```bash
python3 scripts/check_sizes.py
python3 scripts/check_plans.py
python3 scripts/check_reports.py
```

Drift del kit adoptado (compara contra la copia local del manifiesto fuente):

```bash
python3 scripts/check_templates.py \
  --manifest docs/MANIFEST.json --installed .skevi/corpus-installed.json
python3 scripts/check_templates.py \
  --manifest scripts/MANIFEST.json --installed .skevi/scripts-installed.json
```

Registra la salida como evidencia antes de declarar terminado cualquier
cambio.

## Convenciones de edición

- Markdown, ~80 columnas. Idiomas: español en prosa y comentarios; inglés en
  identificadores, claves, ramas y código. Elecciones completas en
  `.skevi/usage-guide.md`.
- Un documento = un propósito y una vida útil.
- Al añadir una regla normativa, declara su procedencia y su razón.
