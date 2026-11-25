# LFM3-Omni

Servicio local de inferencia sobre el modelo omnimodal
`LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M`, servido con llama.cpp en Apple
Silicon y WSL2/CUDA (Dell G7 7700/RTX 2060 verificado). El contrato v1
ofrece texto e imagen de entrada y texto de
salida para agentes de IA y proyectos consumidores del ecosistema
(web, apps): contratos versionados, API compatible OpenAI y MCP.
Audio, video y voz de salida no están ofrecidos por el contrato v1;
la voz realtime completa sigue aplazada. Nota (2026-11-25): el piloto
privado I2 ofrece síntesis de voz (TTS WAV, voz fija) detrás de
credenciales, sin cambiar el contrato v1 — ver
`docs/specs/SPEC-i2-piloto-privado.md`.

Estado: v0.1.0 — F0–F3 cerrados con evidencia y rondas adversariales;
motor verificado, contratos v1 publicados y MCP implementado (F3-1).
Desde el cierre, el servicio evolucionó en mantenimiento: gateway
común I1 (8092), piloto privado I2 con TLS 8443 y credenciales por
proyecto, jobs duraderos y síntesis de voz en el piloto (SPEC-i2;
contratos v2). En el Dell G7 el motor opera bajo demanda desde el
2026-11-24 — ver [relevo de etapa](docs/relevo-2026-11-25.md).

Evolución propuesta a servicio compartido: ver
[PLAN LFM3-2](docs/plans/PLAN-2-servicio-compartido.md), con entregas
incrementales, contratos de consumo y ciclo de vida del modelo. Es un plan
para revisión y adopción; no acredita funcionalidades remotas activas.

## Requisitos

- macOS arm64 (Apple Silicon), 16 GB RAM recomendado; ruta alternativa
  WSL2/CUDA verificada: [retomar Dell G7](docs/retomar-dell-g7.md).
- llama.cpp, motor congelado por registro. Par vigente: el par 2
  (master 54cde710, construido de fuente; ADR-014, salto registrado
  2026-11-10, desbloqueo de realtime). El par 1 (Homebrew 0.8.0
  b11960, ADR-001) quedó registrado en F0; un salto nuevo de motor es
  operación registrada, no actualización silenciosa.
- Los pesos se descargan solos en el primer arranque (GGUF Q4_K_M ~1.1 GB
  + proyector multimodal) a la caché de Hugging Face.
- Python 3.12 o superior con stdlib para verificaciones y tests
  (decisión del Operador, 2026-11-04: runtime 3.12+; hoy la pila local
  del piloto corre con `python3` → 3.15.2 de Homebrew y el gate de
  push exige 3.12+; sin dependencias externas — ver decisiones de
  cascarón abajo).

## Cómo correr

Para la PC con Windows/WSL2 y CUDA, ver
[instalación local WSL](docs/instalacion-wsl.md). El instalador fija el
build y los hashes del plan de hardware. El cierre y los resultados
posteriores están en [retomar Dell G7](docs/retomar-dell-g7.md).

Nota (2026-11-25): en el Dell G7 el servicio ya no arranca con la
máquina: opera bajo demanda desde el 2026-11-24 19:54Z (unidades
`lfm3-motor`/`lfm3-gateway` de Malintzin, `disabled` por defecto;
carga con `malintzin-lfm3 cargar`, ~15 s, apagado automático tras
600 s sin peticiones; avisar antes de cargar). Estado completo:
[relevo de etapa](docs/relevo-2026-11-25.md).

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
B-T8 (corregido en I1-V0) exige que el build acepte audio en chat por la
parte `input_audio` y rechace `audio_url` con 400 — la voz de salida
sigue fuera del contrato v1 (va por `/v1/realtime`, no ofrecido).

## Cómo consumir

- API compatible OpenAI: `POST http://127.0.0.1:8091/v1/chat/completions`
  con `messages` (texto o imagen base64), `tools`, y `response_format`
  json_schema para salidas validadas en frontera.
- Piloto con credenciales (I2, nota 2026-11-25): gateway
  `http://127.0.0.1:8092` y `https://127.0.0.1:8443` con
  `Authorization: Bearer` + `X-Project-ID`, perfiles y scopes por
  proyecto, y síntesis de voz (TTS WAV) — dialecto v2 del piloto
  (`docs/specs/SPEC-i2-piloto-privado.md`; los contratos v2 generales
  siguen en propuesta: `docs/contracts/servicio-general-v2.md` y
  `docs/contracts/perfiles-servicio-v2.md`); alta de credenciales en
  `config/tokens.json` (sólo hash sha256, nunca el token en claro).
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
  · Plan vigente: `docs/plans/PLAN-2-servicio-compartido.md` (PLAN-1
  cerrado en v0.1.0).

## Decisiones de cascarón (03 §3)

- **Gestor de paquetes:** ninguno — el proyecto no tiene dependencias
  externas; todo el código es Python stdlib y bash. Sin manifiesto de
  paquetes ni lockfile porque no hay qué fijar; si algún día entra una
  dependencia, esta decisión se revierte con registro.
- **Runtime:** python 3.12+ (stdlib; decisión del Operador,
  2026-11-04: actualizar el piso desde el python3 del sistema 3.9;
  sin gestor de paquetes); motor fijado por ADR-001.
- **Linter/formateador:** ninguno por ahora (03 §3: sólo si el proyecto
  dura más de una sesión); decisión pendiente, sin herramienta adoptada.
- **CI:** ninguno — el remoto de publicación está declarado (ADR-003),
  pero sin CI ni workflows (decisión del humano: no quemar créditos);
  un pipeline sin nada que comprobaría sería peor. Las decisiones de
  exposición de red viven en F0 (CERRADA-6).
- **Límites de tamaño:** heredados del estándar (800 líneas por archivo,
  200 para instrucciones de agentes, 300 para README); presupuesto de
  ruta de lectura en `skevi-gate.json` (2000; re-base del 2026-11-07
  al cerrar skevi-lfm3).
- **LICENSE:** Apache-2.0 para el contenido del repositorio (código,
  docs, contratos; copyright kristhianmanue1). Los pesos del modelo NO
  se relicencian ni se redistribuyen: siguen bajo LFM Open License v1.0
  (umbral comercial de 10 M USD; REQ-8/EV-10) y se descargan de
  Hugging Face en el primer arranque. Remoto de publicación declarado:
  `github.com/kristhianmanue1/LFM3-Omni-FK` (ADR-003). La memoria
  local `.an-kla/` no se versiona (ADR-003).

## Estructura

```text
├── AGENTS.md               # entrada para ejecutores automatizados
├── project-manifest.yaml   # qué ofrece y qué no, frente al ecosistema
├── skevi-gate.json         # config del gate (límites, ruta de lectura, planes)
├── run/                    # serve.sh / serve_pilot.sh / stop.sh (runbook)
├── scripts/                # gates copiables de Skevi (versionados)
├── src/mcp_server.py       # servidor MCP stdio (implementado, F3-1)
├── tests/golden/casos.json # conjunto de referencia con procedencia
├── tests/run_golden.py     # runner de la batería
└── docs/                   # F0, specs, ADRs, contratos, planes, reviews
```
