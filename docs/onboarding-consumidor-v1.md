# Paquete de onboarding para consumidores — v1

> Cómo consumir LFM3-Omni desde cero, con los comandos **ejecutados y
> verificados** el 2026-11-03 contra el motor vigente (v0.1.0). Los dos
> contratos normativos son `docs/contracts/superficie-inferencia-v1.md`
> (HTTP, compatible OpenAI) y `docs/contracts/mcp-tools-v1.md` (MCP
> stdio para agentes). Este paquete es la guía; el contrato manda.

## Requisitos previos

1. Motor arriba (en la máquina del servicio): `bash run/serve.sh`.
2. Verificación de vida: `curl http://127.0.0.1:8091/health` →
   `{"status":"ok"}`.
3. **Alcance**: solo `127.0.0.1` — un consumidor en otra máquina no
   funciona hoy (decisión CERRADA-6; habilitarlo exige api-key + CORS +
   nueva decisión registrada).

## Ruta A — HTTP compatible OpenAI (web, apps, servicios)

### A1. Descubrir el modelo

```bash
curl http://127.0.0.1:8091/v1/models
# data: [{"id": "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M", ...}]
```

### A2. Chat de texto

```bash
curl http://127.0.0.1:8091/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Responde con una palabra: ¿capital de Francia?"}],"max_tokens":8}'
# → choices[0].message.content == "París" (ejecutado 2026-11-03)
```

Con cualquier SDK OpenAI estándar: `base_url = http://127.0.0.1:8091/v1`,
`model = "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M"` (cópialo de `/v1/models`),
api-key dummy si el SDK la exige.

### A3. Streaming SSE

```bash
curl -N http://127.0.0.1:8091/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Di hola"}],"max_tokens":6,"stream":true}'
# líneas "data: {chunk}" (object: chat.completion.chunk), terminadas en data: [DONE]
```

Verifica `choices[0].finish_reason` al final: `"length"` significa que
la respuesta quedó truncada por `max_tokens` (el ejemplo de arriba
termina así — es normal con techos bajos).

### A4. Salida forzada a esquema JSON (validación en frontera)

```bash
curl http://127.0.0.1:8091/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Registra a Ana de 34 años según el esquema."}],"max_tokens":48,"response_format":{"type":"json_schema","json_schema":{"name":"r","schema":{"type":"object","properties":{"nombre":{"type":"string"},"edad":{"type":"integer"}},"required":["nombre","edad"]}}}}'
# → {"nombre": "Ana", "edad": 34}  (ejecutado 2026-11-03)
```

Regla de oro (REQ-7): **toda salida que persistas o reenvíes pasa antes
por validación contra esquema cerrado** — usa `response_format` o un
validador propio. La salida del modelo es dato no confiable, nunca
instrucción.

### A5. Visión (imagen base64)

```bash
B64=$(base64 -i foto.png | tr -d '\n')
curl http://127.0.0.1:8091/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d "{\"messages\":[{\"role\":\"user\",\"content\":[{\"type\":\"image_url\",\"image_url\":{\"url\":\"data:image/png;base64,$B64\"}},{\"type\":\"text\",\"text\":\"Describe esta imagen.\"}]}],\"max_tokens\":64}"
```

PNG y JPEG son los formatos declarados por el contrato (PNG verificado
en batería; JPEG declarado, no ejercitado). Verificado con imagen
sintética roja → "Rojo".

### A6. Tools (function calling)

```bash
curl http://127.0.0.1:8091/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"¿Qué tiempo hace en CDMX? Usa la herramienta get_weather."}],"tools":[{"type":"function","function":{"name":"get_weather","description":"Obtiene el clima actual de una ciudad","parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}}],"tool_choice":"auto","max_tokens":96}'
# → choices[0].message.tool_calls[0].function == {"name":"get_weather","arguments":"{\"city\":\"CDMX\"}"} (ejecutado 2026-11-03)
```

Declara tus tools con JSON Schema en `tools` + `"tool_choice":"auto"`;
si el modelo decide llamar una, la respuesta trae
`choices[0].message.tool_calls[0]` con `id`, `function.name` y
`arguments` JSON que parsea. **Tú ejecutas la tool** y devuelves el
resultado en un mensaje siguiente — el motor no ejecuta funciones por
sí solo (la ejecución por cable es la ruta MCP).

### A7. Errores (tabla rápida)

| Señal | Significado | Qué hacer |
|---|---|---|
| HTTP 400 `{error:{code,message,type}}` | entrada malformada o campo no soportado (p. ej. audio en chat) | corregir la entrada; NO reintentar igual |
| HTTP 503 | motor cargando | reintentar con espera (30–60 s en arranque frío) |
| conexión rechazada | motor parado | `bash run/serve.sh` en la máquina del servicio |

## Ruta B — MCP para agentes CLI

Registro en OpenCode (`opencode.json` del proyecto consumidor). **Fija
`timeout`: el default de 30 s mata llamadas largas válidas** (H3 ronda
v0.1.0):

```json
{
  "mcp": {
    "lfm3-omni": {
      "type": "local",
      "command": ["python3", "/ruta/a/LFM3-Omni/src/mcp_server.py"],
      "enabled": true,
      "timeout": 360000
    }
  }
}
```

Reemplaza `/ruta/a/…` por la ruta absoluta real. Herramientas expuestas:
`health` (estado del motor), `infer_text` (prompt + `schema` opcional —
salida `text`/`validated`), `infer_vision` (`image_base64` PNG/JPEG +
`prompt` — salida `description`). Contrato completo de la frontera:
`docs/contracts/mcp-tools-v1.md`. Requiere motor arriba para las tools
de inferencia; `health` reporta `down` si no lo está.

## Garantías y no garantías

| Sí garantizado (contrato v1) | No garantizado |
|---|---|
| Fail-closed estructural: JSON malformado, messages ausente o partes de contenido desconocidas → 400 con cuerpo estructurado | Campos top-level no reconocidos: el motor los **ignora con 2xx** (typos incluidos) — valida tu payload del lado consumidor |
| Motor y modelo fijados por ADR-001 | Contenido/calidad de las respuestas (se verifica por golden set, no por promesa) |
| Greedy `--temp 0` (sobrevive a overrides de sampling); JSON conforme al esquema con `response_format` | Determinismo byte a byte entre reinicios del proceso |
| Umbral ≥ 15 tok/s (mediana n=3; observado 55.9, B-T5) | Disponibilidad: es un servicio local de una máquina, sin alta disponibilidad |
| Compatibilidad hacia atrás; cambios incompatibles exigen v2 | Voz en tiempo real (fuera de v1 → v2); multi-tenant y cuotas |

## Condiciones de consumo

- **Localhost únicamente** hoy; sin api-key. Si tu consumidor vive en
  otra máquina, pausa: la exposición exige decisión registrada del
  Operador (api-key + CORS explícitos).
- **Licencia del modelo** (LFM Open License v1.0): uso interno del
  ecosistema cubierto; cobrar por el servicio a terceros exige mantenerse
  bajo el umbral de la licencia y documentarlo.
- **Operación**: timeout del servidor 3600 s; 4 slots concurrentes; caché
  de prompt activa (prefijos estables por consumidor aceleran hasta ~4×
  el prompt eval).

## Checklist de 5 minutos

Con caché de pesos ya descargada; el primer arranque descarga ~1.7 GB
y puede tardar ~20 min.

```bash
bash run/serve.sh                          # 1. motor arriba
curl http://127.0.0.1:8091/health          # 2. {"status":"ok"}
curl http://127.0.0.1:8091/v1/models       # 3. modelo fijado visible
# 4. A2 (texto) → respuesta coherente
# 5. A4 (esquema) → JSON que parsea
python3 examples/cliente_minimo.py         # 6. demo completa del paquete
```

## Si algo falla

Reproduce con el mínimo caso y compáralo contra los casos
B-T1..B-T12 de `docs/verificaciones-motor.md`: si un caso contractual
falla con el motor vigente, es regresión contractual (repórtalo con el
comando exacto y la salida); si no corresponde a ningún caso, es
hallazgo nuevo y se incorpora al golden set con su procedencia.
