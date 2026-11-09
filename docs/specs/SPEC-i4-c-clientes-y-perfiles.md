# SPEC-i4-c-clientes-y-perfiles: Perfiles de consumo W y D, y clientes SDK de referencia

- **Fase**: I4 (Fase 4 del PLAN LFM3-2: Servicio Compartido)
- **Estado**: Aceptado / En implementación
- **Procedencia**: S-06, S-10, perfiles W y D de `docs/contracts/perfiles-servicio-v2.md`
- **Fecha**: 2026-11-07
- **Autoridad**: Decisión del Operador (sesión 2026-11-07)

---

## 1. Contexto y objetivos

La Fase I3 entregó el servidor MCP remoto desacoplado con catálogo omnimodal
completo sobre `/mcp`. La Fase I4 formaliza y valida el consumo de la
plataforma desde dos clases de sistemas del ecosistema:

1. **Perfil W (Web, aplicaciones y humanos)**:
   - Clientes de backend (BFF) o scripts de integración en Python y
     JavaScript/Node.js que interactúan con el servicio compartido usando
     tokens de proyecto (`Authorization: Bearer <token>`).
   - Consumo integral de las capacidades omnimodales:
     * Inferencia de texto con esquemas estructurados (`response_format` v2-ext).
     * Percepción visual sobre imágenes (PNG/JPEG en base64).
     * Transcripción de audio (WAV 16 kHz en base64).
     * Síntesis de voz (`llama-tts`, WAV 24 kHz) con gestión de exclusión mutua.
     * Análisis de video corto temporal (MP4 base64 con muestreo de fotogramas).
     * Conversación multi-turno con streaming SSE y cancelación interactiva.
   - Reglas de seguridad para interfaces humanas: aislamiento de tokens de
     proyecto (nunca expuestos al navegador o móvil), saneamiento de salida
     para evitar ejecución no intencionada de HTML/scripts, y propagación
     de `client_request_id` para correlación sin confundirlo con identidad.

2. **Perfil D (Dispositivos, robots y edge)**:
   - Adaptador cliente seguro para robots y agentes embebidos.
   - Comunicación autenticada (`proyecto-beta`) contra el gateway HTTP/HTTPS.
   - Integración sensorial multimodal: cámara (`image_base64`) y telemetría.
   - Salvaguardas no negociables de seguridad física:
     * Deriva máxima de reloj: $\le 2.0\text{ s}$ entre observador y gateway.
     * Expiración pre-inferencia: descarte inmediato si `ahora >= expires_at`.
     * Expiración post-inferencia: descarte si la inferencia tardó más allá
       de `expires_at`, impidiendo actuar sobre información obsoleta.
     * Deduplicación estricta y secuencia monotónica de `observation_id`.
     * Descarte fail-closed ante salida truncada (`finish_reason != 'stop'`).
     * Validación en frontera contra enum cerrado de acciones (`allowed_kinds`).
     * Modo simulador seguro (sin conexión directa a actuadores físicos).

3. **Handoff formal a frontExpert (TAREA I4-UI)**:
   - Conforme a `docs/ruteo-ui-frontexpert.md`, este repositorio entrega
     contratos, esquemas y clientes de referencia, sin albergar código UI.
   - Se formaliza el paquete de handoff en `docs/contracts/handoff-frontexpert-v2.md`.

---

## 2. Arquitectura de integración

```
               [ Navegador / App Móvil ]
                          │
                   (Sesión de usuario)
                          ▼
            ┌───────────────────────────┐
            │  Backend W (BFF / Node/Py)│ ◄─── Perfil W
            │  - Autenticación humana   │
            │  - Saneamiento de salida  │
            │  - Manejo de token Bearer │
            └─────────────┬─────────────┘
                          │ (HTTPS / HTTP Bearer)
                          ▼
        ┌───────────────────────────────────┐
        │       LFM3-Omni Gateway           │
        │  /v1/chat/completions (H / W)     │
        │  /mcp (Streamable HTTP / M)       │
        │  /capabilities, /health           │
        └─────────────────▲─────────────────┘
                          │ (HTTPS / HTTP Bearer)
            ┌─────────────┴─────────────┐
            │  Adaptador Perfil D       │ ◄─── Perfil D
            │  - Validación temporal    │
            │  - Deduplicación          │
            │  - Control de actuadores  │
            └─────────────▲─────────────┘
                          │
               [ Simulador / Robot ]
```

---

## 3. Especificación de Perfil W: Clientes SDK de referencia

### 3.1 Cliente Python (`examples/cliente_perfil_w.py`)

- **Entorno**: Python $\ge 3.10$, utilizando exclusivamente la biblioteca
  estándar (`urllib.request`, `json`, `base64`, `ssl`).
- **Capacidades**:
  1. `health()` y `capabilities()` para negociación previa de versiones.
  2. `chat_text(prompt, system_prompt=None, max_tokens=256)`: texto libre.
  3. `chat_structured(prompt, schema_dict, schema_name="output")`: inferencia
     estructurada con validación local previa y posterior.
  4. `chat_vision(prompt, image_bytes_or_b64, schema_dict=None)`: visión.
  5. `transcribe_audio(audio_bytes_or_b64, prompt=None)`: ASR sobre audio WAV.
  6. `synthesize_speech(text)`: TTS con manejo de 503 y reintentos. Voz
     fija, sin parámetro `voice` (issue #2, decisión del Operador del
     2026-11-07; contrato `mcp-tools-v2.md`, «Voz fija y migración»).
  7. `chat_video(prompt, video_bytes_or_b64, max_duration_s=10)`: video corto.
  8. `chat_stream(messages, on_chunk_cb, client_request_id=None)`: streaming
     SSE con lectura continua de chunks y detección de `finish_reason`.
  9. `cancel_request(request_id)`: envío de `DELETE /requests/{request_id}`.
- **Saneamiento**: Módulo auxiliar `sanitize_for_display(text)` que escapa
  etiquetas HTML peligrosas y previene inyecciones en interfaces web.

### 3.2 Cliente JavaScript / Node.js (`examples/cliente_perfil_w.mjs`)

- **Entorno**: Node.js $\ge 18$ (soporte nativo de `fetch`, `AbortController`
  y `ReadableStream`). Formato ESM sin dependencias npm externas.
- **Capacidades equivalentes**:
  1. Conexión segura con token de autorización en cabecera `Authorization`.
  2. Soporte omnimodal para texto estructurado, visión, audio, voz y video.
  3. Streaming SSE continuo mediante `response.body.getReader()` y decodificador
     UTF-8 en tiempo real.
  4. Cancelación limpia mediante señal de `AbortController` o llamada a DELETE.
  5. Saneamiento de salida mediante escapado defensivo de caracteres HTML.

---

## 4. Especificación de Perfil D: Adaptador y simulador

### 4.1 Mejoras a `src/adaptador_perfil_d.py`

- Inclusión de cabecera `Authorization: Bearer <auth_token>` para operar
  tanto contra gateway local en pruebas como contra el piloto privado
  I2/I3 (puertos 8092 y 8443).
- Inclusión opcional de `client_request_id` autogenerado con prefijo `obs-`.
- Soporte de entrada multimodal:
  * Sensor visual: `image_base64` (fotograma de cámara de navegación).
  * Sensor de distancia/texto: `prompt` con telemetría formateada.
  * Esquema estructurado de salida garantizado: `kind` (en enum cerrado de
    `allowed_kinds`) y `payload` con parámetros cinemáticos (`velocidad`,
    `angulo`, `motivo`).

### 4.2 Simulador de dispositivo (`examples/simulador_robot_perfil_d.py`)

- Bucle de simulación representativo:
  * Caso A: Observación válida con visión y telemetría -> Propuesta aceptada.
  * Caso B: Observación duplicada (`observation_id` repetido) -> Descarte
    inmediato sin llamada al motor (`duplicate_observation`).
  * Caso C: Observación vencida en origen (`observed_at` expirado) -> Descarte
    inmediato sin cómputo (`expired_pre_inference`).
  * Caso D: Desfase excesivo de reloj del dispositivo ($> 2\text{ s}$) ->
    Descarte por deriva temporal (`drift_clock`).
  * Caso E: Salida incompleta o truncada (`finish_reason != 'stop'`) ->
    Descarte inmediato (`incomplete_output`).
  * Caso F: Propuesta con `kind` no autorizado -> Descarte inmediato
    (`unauthorized_proposal_kind`).

---

## 5. Criterios de Aceptación y Verificación

1. Todos los clientes (`cliente_perfil_w.py`, `cliente_perfil_w.mjs` y
   `simulador_robot_perfil_d.py`) son ejecutables directamente con exit 0.
2. Los clientes demuestran el aprovechamiento de todas las modalidades:
   texto, esquema estructurado, visión, audio, voz, video y streaming conversacional.
3. Se verifican las salvaguardas de Perfil D en la suite de pruebas unitarias.
4. El paquete de handoff a frontExpert queda completamente documentado sin
   introducir código UI en este repositorio.
5. Los cinco gates del estándar pasan limpiamente (`check_sizes.py`,
   `check_plans.py`, `check_reports.py`, `check_templates.py`, y test suite).
