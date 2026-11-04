# LFM3-Omni

Servicio local de inferencia sobre el modelo omnimodal
`LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M`, servido con llama.cpp en Apple
Silicon. El contrato v1 ofrece texto e imagen de entrada y texto de
salida para agentes de IA y proyectos consumidores del ecosistema
(web, apps): contratos versionados, API compatible OpenAI y MCP.
Audio, video y voz de salida no están ofrecidos por el contrato v1;
la voz realtime completa sigue aplazada.

Estado: v0.1.0 — F0–F3 cerrados con evidencia y rondas adversariales;
motor verificado, contratos v1 publicados y MCP implementado (F3-1).

Evolución propuesta a servicio compartido: ver
[PLAN LFM3-2](docs/plans/PLAN-2-servicio-compartido.md), con entregas
incrementales, contratos de consumo y ciclo de vida del modelo. Es un plan
para revisión y adopción; no acredita funcionalidades remotas activas.

## Requisitos

- macOS arm64 (Apple Silicon), 16 GB RAM recomendado.
- llama.cpp 0.8.0 (build 11960) vía Homebrew: `brew install llama.cpp`
  (motor congelado por registro — ADR-001; la versión bottled es la que
  exige la ficha del modelo).
- Los pesos se descargan solos en el primer arranque (GGUF Q4_K_M ~1.1 GB
  + proyector multimodal) a la caché de Hugging Face.
- Python 3 con stdlib para verificaciones y tests (sin dependencias
  externas; decisión de cascarón: sin gestor de paquetes porque el
  proyecto no tiene dependencias — ver abajo).

## Cómo correr

```bash
bash run/serve.sh    # arranca en 127.0.0.1:8091 (solo localhost) y espera salud
bash run/stop.sh     # detiene el servicio
curl http://127.0.0.1:8091/health   # → {"status":"ok"}
```

Runbook completo y restricciones: `docs/adr/ADR-001-motor-congelado-registrado.md`.

## Cómo probar

```bash
python3 tests/run_golden.py      # batería de propiedades contra el motor vivo
python3 scripts/check_sizes.py   # gate de estructura y tamaños
python3 scripts/check_plans.py   # gate de planes
python3 scripts/check_reports.py # gate de reportes
```

La batería declara 12 casos con su procedencia en `tests/golden/casos.json`;
B-T8 documenta una limitación vigente del build (audio de entrada
rechazado por chat — la voz va por `/v1/realtime`, fuera del contrato v1):
su propiedad de regresión es que el rechazo se sostenga.

## Cómo consumir

- API compatible OpenAI: `POST http://127.0.0.1:8091/v1/chat/completions`
  con `messages` (texto o imagen base64), `tools`, y `response_format`
  json_schema para salidas validadas en frontera.
- Contrato completo: `docs/contracts/superficie-inferencia-v1.md` —
  entradas, salidas, errores, invariantes y compatibilidad. Fail-closed
  estructural: JSON malformado, `messages` ausente o partes de contenido
  desconocidas → 400; los campos top-level no reconocidos se **ignoran
  con 2xx** — valida tu payload del lado consumidor.
- Paquete de onboarding para consumidores:
  `docs/onboarding-consumidor-v1.md` — guía paso a paso con comandos
  verificados (HTTP compatible OpenAI + registro MCP).
- MCP para agentes: `docs/contracts/mcp-tools-v1.md` (transporte stdio).
  Implementado: `python3 src/mcp_server.py` — lee JSON-RPC por stdin;
  tools `health`, `infer_text` (con esquema validado en frontera) e
  `infer_vision`. La voz va por `/v1/realtime` del motor, fuera del
  contrato v1.
- Especificaciones: `docs/specs/` · Decisiones: `docs/adr/00-INDICE.md`
  · Plan vigente: `docs/plans/PLAN-1-superficie-inferencia.md`.

## Decisiones de cascarón (03 §3)

- **Gestor de paquetes:** ninguno — el proyecto no tiene dependencias
  externas; todo el código es Python stdlib y bash. Sin manifiesto de
  paquetes ni lockfile porque no hay qué fijar; si algún día entra una
  dependencia, esta decisión se revierte con registro.
- **Runtime:** python3 (stdlib, probado con el python3 del sistema) y
  bash; motor fijado por ADR-001.
- **Linter/formateador:** ninguno por ahora (03 §3: sólo si el proyecto
  dura más de una sesión); decisión pendiente, sin herramienta adoptada.
- **CI:** ninguno — no hay remoto declarado (decisión del humano: no
  quemar créditos); un pipeline sin nada que comprobaría sería peor.
  Las decisiones de exposición de red viven en F0 (CERRADA-6).
- **Límites de tamaño:** heredados del estándar (800 líneas por archivo,
  200 para instrucciones de agentes, 300 para README); presupuesto de
  ruta de lectura en `skevi-gate.json` (1800, adopción de AN-KLA).
- **LICENSE:** pendiente — el repositorio no se publica hoy; el modelo
  que sirve está bajo LFM Open License v1.0 (umbral comercial de
  10 M USD; ver REQ-8/EV-10 en el contrato). Al decidir publicación,
  elegir LICENSE y registrar la decisión.

## Estructura

```text
├── AGENTS.md               # entrada para ejecutores automatizados
├── project-manifest.yaml   # qué ofrece y qué no, frente al ecosistema
├── skevi-gate.json         # config del gate (límites, ruta de lectura, planes)
├── run/                    # serve.sh / stop.sh (runbook operativo)
├── scripts/                # gates copiables de Skevi (versionados)
├── src/mcp_server.py       # servidor MCP stdio (implementado, F3-1)
├── tests/golden/casos.json # conjunto de referencia con procedencia
├── tests/run_golden.py     # runner de la batería
└── docs/                   # F0, specs, ADRs, contratos, planes, reviews
```
