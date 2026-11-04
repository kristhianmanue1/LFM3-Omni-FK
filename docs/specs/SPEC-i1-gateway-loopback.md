# SPEC I1 — Gateway común en loopback

Estado: activo (I1-D con ADR-005). Procedencia: PLAN LFM3-2 TAREA
I1-D/I1-A/I1-U; `docs/roadmap/iteraciones-servicio.md` §I1; D-01
aceptada; encargo «adelante con pendientes» (2026-11-04). Evolución
del adaptador I0 (SPEC-i0): mismo dialecto de peticiones, imágenes,
schema y errores — lo no redefinido aquí rige el SPEC-i0.

## 1. Arquitectura (modular, ADR-005)

- `src/gateway_core.py`: políticas puras (validación de payload,
  imágenes, schema, salida), constantes de límites, allowlist de
  rutas y declaración de capabilities. SIN imports de transporte
  (frontera interna verificada por test).
- `src/gateway_http.py`: transporte (Manejador, Servidor, build_server,
  main). Puerto default 8092 (`LFM3_GATEWAY_PORT` para tests);
  colisión al arrancar → BLOQ + exit 1.
- `src/adapter_v2.py`: fachada de compatibilidad de I0 — expone
  `build_server` delegando en los módulos nuevos; sus pruebas y demo
  siguen pasando sin cambios de comportamiento.
- Backend: motor v1 en 8091 (`LFM3_BACKEND`). Loopback exclusivamente.

## 2. Superficie (allowlist cerrado)

| Método y ruta | Comportamiento |
|---|---|
| POST /v1/chat/completions | validación I0 → proxy → validación de salida |
| GET /v1/models | proxy directo al motor |
| GET /v1/capabilities | declaración local, sin tocar el motor |
| GET /healthz | salud del gateway |
| Cualquier otra (incluidas `/props`, `/slots`, `/metrics`, `/`, UI embebida) | 404 `not_found`, contador del motor en 0 |

El enrutado se deriva de `RUTAS_PERMITIDAS` (gateway_core) mediante
`_enrutar`: un par método+ruta sólo responde si está en la tupla.
Métodos no soportados (PUT/DELETE/PATCH/OPTIONS) responden 404 JSON;
HEAD queda a la normalización de la stdlib (501). Alias `//ruta` se
colapsan en la stdlib 3.12 (gh-87389) y caen en una ruta permitida;
`/ruta/`, `?query` y mayúsculas son 404.

## 3. Capabilities (jamás anuncian lo no activo)

`GET /v1/capabilities` → claves cerradas:
`entrada: [texto, imagen]`, `salida: [texto]`, `streaming: false`,
`audio: false`, `video: false`, `voz: false`, `schema: dialecto-v2`,
`version: i1`. No se derivan del motor: se declaran por este SPEC
(cambiar capabilities exige SPEC nuevo).

## 4. Transporte: límites antes de costos

- `Content-Encoding` distinto de identity/ausente → 400
  `payload_too_large` (detalle `compressed_input_rejected`) ANTES de
  leer el cuerpo (sin descompresión ni decodificación costosa).
- `Transfer-Encoding` presente (chunked, con o sin Content-Length) →
  400 `payload_too_large` (detalle `content_length_required`); sin
  `Content-Length` → el mismo rechazo. La cota de 32 MiB se aplica
  sobre la cabecera antes de leer.
- Respuestas sin compresión; sin streaming (I0/I1).

## 5. Matriz de conformidad (perfil H — subconjunto OpenAI)

Campos de petición admitidos (los demás → 400, SPEC-i0 §2): `model`,
`messages`, `tools`, `tool_choice`, `temperature`, `top_p`,
`max_tokens`, `response_format`. Forma de respuesta: passthrough del
motor (OpenAI-compatible) + cabeceras `X-V2-*`. Errores con forma
única y `request_id` (SPEC-i0 §6).

SDK externos comprobados: ninguno — la instalación de dependencias
está fuera de alcance local sin autoridad específica; la conformidad
se acredita con la batería propia de propiedades (tests) y el cliente
de referencia de este SPEC. Declarado como límite, no como omisión.

## 6. Cliente de referencia (`examples/cliente_i1.py`)

Mínimo, stdlib-only, sin dependencias: `salud()`, `capabilities()`,
`modelos()`, `chat_texto()`, `chat_schema()`, `chat_imagen()`; errores
de la frontera impresos con su código estable. Es la demo I1-U: debe
completar texto, JSON e imagen contra el gateway con motor vivo y
mostrar un rechazo controlado.

## 7. Matriz REQ-SPEC-test (nueva respecto a I0)

| REQ | Propiedad | Verificación |
|---|---|---|
| G1 | `/v1/capabilities` declara sin voz/video/streaming | `test_gateway_i1::g1` |
| G2 | chunked (sin Content-Length) → 400, contador 0 | `test_gateway_i1::g2` |
| G3 | Content-Encoding comprimido → 400 antes de leer, contador 0 | `test_gateway_i1::g3` |
| G4 | `/props /slots /metrics / /ui` → 404, contador 0 | `test_gateway_i1::g4` |
| G5 | colisión de puerto → BLOQ exit 1, sin excepción cruda | `test_gateway_i1::g5` |
| G6 | gateway_core no importa transporte | `test_gateway_i1::g6` |
| G7 | fachada I0 conserva build_server | suite I0 completa en verde |
| G8 | cliente de referencia completa texto/JSON/imagen + rechazo | demo I1-U |

## 8. Comandos exactos

```bash
python3.12 -m unittest tests.test_gateway_i1 tests.test_adapter_v2 \
  tests.test_recursos_bt10 tests.test_ciclo_arranque -v
bash run/serve.sh
python3.12 tests/run_golden.py --rapido
python3.12 src/gateway_http.py &   # gateway con LFM3_GATEWAY_PORT si procede
python3.12 examples/cliente_i1.py
bash run/stop.sh
```

## 9. Rollback y compatibilidad

- Gateway: detener proceso; nada persiste. La fachada I0 garantiza que
  el comportamiento aceptado en I0 no cambia (suite I0 en verde).
- Motor y contratos v1 intactos. Reversión: revert del commit de la
  TAREA I1.

## 10. Límites declarados

- Sin streaming/SSE, sin auth, sin cuotas (I2/I3); concurrencia por
  hilos stdlib; rendimiento concurrente modesto aceptado por ADR-005.
- Conformidad con SDK externos no acreditada (sin instalar
  dependencias); acreditada por batería propia + cliente de referencia.
