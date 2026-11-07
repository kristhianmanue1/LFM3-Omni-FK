# SPEC-i3: Especificación técnica del servidor MCP remoto desacoplado (I3)

Estado: PROPUESTO para ejecución en TAREA I3-D (PLAN LFM3-2).
Base: contratos `servicio-general-v2.md`, `perfiles-servicio-v2.md` (§M) y `mcp-tools-v2.md`.
Procedencia: S-02, S-05, S-06, S-10, S-12; ADR-002, ADR-006, ADR-008, ADR-009, ADR-010.
Límite de lectura: no forma parte de la ruta de lectura de skevi-gate.json.

## 1. Propósito y directiva de omnimodalidad

Esta especificación formaliza la arquitectura, contratos wire y mecanismos
operativos del **Servidor MCP Remoto Desacoplado** (Fase I3) para el servicio
`LFM3-Omni`.

El servidor expone la inferencia del modelo `LiquidAI/LFM3-Omni-2B-GGUF` a agentes
de software externos a través del estándar industrial **Model Context Protocol (MCP)**,
operando sobre una conexión de red privada segura con terminación TLS en el puerto 8443.

Por mandato directo del Operador (2026-11-07), el servidor remoto no se reduce a
un canal de texto plano: **aprovecha y publica integralmente todas las capacidades
omnimodales demostradas del modelo**, organizadas en un catálogo determinista de
herramientas:
1. **Texto libre y estructurado**: completado y extracción garantizada con schema v2-ext.
2. **Reconocimiento de imágenes**: inspección visual sobre imágenes PNG/JPEG en base64.
3. **Procesamiento de audio**: análisis y transcripción de voz sobre audio WAV PCM 16kHz.
4. **Síntesis de voz**: generación de audio hablado en español mediante `llama-tts`.
5. **Video corto**: comprensión temporal y espacial sobre clips MP4 inspeccionados con ffprobe.
6. **Conversación por turnos**: diálogo interactivo con streaming de texto y fragmentos de voz.

---

## 2. Transporte y ciclo de vida: Streamable HTTP

### 2.1 Endpoint y métodos de transporte
El servicio MCP remoto se publica bajo la ruta `/mcp` a través del terminador TLS (8443):

* **Peticiones de comando (POST /mcp)**:
  * Encabezados obligatorios:
    * `Content-Type: application/json`
    * `Authorization: Bearer <token>`
    * `X-Project-ID: <project_id>`
    * `Mcp-Session-Id: <uuid_v4>` (opcional en `initialize`; obligatorio en métodos posteriores)
  * Cuerpo: objeto JSON-RPC 2.0 válido (`jsonrpc: "2.0"`, `id`, `method`, `params`).
  * Respuestas: JSON-RPC 2.0 con código HTTP `200 OK` (salvo fallos de autenticación
    o transporte que devuelven `401`, `403` o `400`).

* **Canal de streaming y eventos (GET /mcp)**:
  * Encabezados obligatorios:
    * `Accept: text/event-stream`
    * `Authorization: Bearer <token>`
    * `X-Project-ID: <project_id>`
    * `Mcp-Session-Id: <uuid_v4>`
  * Cuerpo: flujo Server-Sent Events (SSE) para notificaciones y streaming incremental
    de turnos conversacionales.

### 2.2 Desacoplamiento de sesiones y concurrencia
* **Prohibición de estado global compartido**:
  A diferencia del servidor stdio uniusuario (donde una sola variable global
  registra el estado de inicialización), el servidor remoto desacopla el estado
  de cada cliente utilizando el identificador de sesión `Mcp-Session-Id`.
* **Aislamiento de proyectos**:
  Una sesión pertenece estrictamente al `project_id` autenticado al crearse. Peticiones
  posteriores con el mismo `Mcp-Session-Id` pero diferente `project_id` son
  rechazadas con `403 Forbidden` (`project_mismatch`).
* **Ciclo de vida de sesión**:
  1. `initialize`: cliente negocia la versión (`2024-11-05`, `2025-03-26`, `2025-06-18`).
     El servidor emite o ratifica el `Mcp-Session-Id` y registra las capacidades negociadas.
  2. Métodos operativos (`tools/list`, `tools/call`, `ping`): ejecutados dentro del
     contexto de la sesión.
  3. Cierre: desconexión de socket, timeout de inactividad (300 segundos) o llamada explícita.
     La expiración limpia los recursos en memoria sin afectar a otros proyectos.

---

## 3. Modelo de seguridad, identidad y scopes

### 3.1 Autenticación Bearer y verificación
Toda petición al endpoint `/mcp` se valida contra el registro seguro `config/tokens.json`
(permisos `0600`):
1. Extracción del token desde `Authorization: Bearer <token>`.
2. Cálculo del hash SHA-256 del token y búsqueda en el registro.
3. Validación de coincidencia con `X-Project-ID`.
4. Comprobación de vigencia (`"revoked": false`).
5. Evaluación de cuotas de tasa (token bucket) y límites de cola.

### 3.2 Matriz de scopes por herramienta MCP
El acceso a cada herramienta en `tools/call` exige que el proyecto cuente con el
scope correspondiente en su registro de credenciales:

| Herramienta MCP | Modalidad | Scope Requerido |
|---|---|---|
| `health` | Diagnóstico de salud | Token válido no revocado |
| `capabilities` | Catálogo de capacidades activas | Token válido no revocado |
| `infer_text` | Texto libre / estructurado con schema | `infer:text` o `mcp:tools` |
| `infer_vision` | Inspección visual de imágenes | `infer:vision` o `mcp:tools` |
| `infer_audio` | Procesamiento y transcripción de audio | `infer:audio` o `mcp:tools` |
| `synthesize_speech` | Síntesis de voz en español | `speech:synthesize` o `mcp:tools` |
| `infer_video` | Análisis temporal de video corto | `infer:video` o `mcp:tools` |
| `conversational_turn` | Turno conversacional con streaming | `infer:text` + `turn:stream` o `mcp:tools` |

Si el proyecto no posee el scope necesario, la llamada responde un objeto
`CallToolResult` con `isError: true` y detalle `insufficient_scope`.

### 3.3 Contención estricta de egreso (anti-SSRF)
* Todos los medios (imágenes, audios, videos) deben transferirse obligatoriamente
  en formato base64 dentro de los argumentos (`image_base64`, `audio_base64`,
  `video_base64`).
* Se prohíbe el uso de URIs (`http://`, `https://`, `ftp://`, `file://`). Cualquier
  argumento que contenga esquemas de URL externos o rutas locales es rechazado en
  frontera antes de tocar el motor con error `invalid_payload` (REQ-7).

---

## 4. Catálogo omnimodal detallado de herramientas (`tools/list`)

El servidor anuncia el siguiente catálogo normativo en `tools/list`:

### 4.1 `health`
* **Propósito**: Comprobar la disponibilidad operativa del gateway y el motor local.
* **Argumentos**: ninguno (`{}`).
* **Salida**:
  ```json
  {
    "status": "healthy",
    "model": "LiquidAI/LFM3-Omni-2B-GGUF",
    "gateway_port": 8092,
    "backend_port": 8091,
    "capabilities": {
      "text": true,
      "vision": true,
      "audio": true,
      "speech": true,
      "video": true,
      "conversation_stream": true
    }
  }
  ```

### 4.2 `capabilities`
* **Propósito**: Consultar las restricciones dimensionales y formatos admitidos.
* **Argumentos**: ninguno (`{}`).
* **Salida**: objeto con límites de tokens, formatos de medios (WAV 16kHz, PNG/JPEG, MP4),
  duración máxima de video (10 s) y dialecto schema v2-ext soportado.

### 4.3 `infer_text`
* **Propósito**: Generación de texto o extracción estructurada según schema cerrado.
* **Argumentos**:
  * `prompt` (string, 1..8000 caracteres, obligatorio).
  * `schema` (objeto JSON Schema dialecto v2-ext, opcional).
  * `max_tokens` (entero, 1..4096, defecto 512, opcional).
* **Salida**:
  ```json
  {
    "text": "Respuesta generada o JSON extraído",
    "validated": true,
    "usage": { "prompt_tokens": 42, "completion_tokens": 18, "total_tokens": 60 }
  }
  ```

### 4.4 `infer_vision`
* **Propósito**: Reconocimiento de imágenes y análisis visual detallado.
* **Argumentos**:
  * `image_base64` (string base64 verificado con firma PNG o JPEG, obligatorio).
  * `prompt` (string, 1..8000 caracteres, obligatorio).
  * `schema` (objeto JSON Schema dialecto v2-ext, opcional).
  * `max_tokens` (entero, 1..4096, defecto 1024, opcional).
* **Salida**:
  ```json
  {
    "description": "Descripción visual de los elementos observados",
    "validated": true,
    "usage": { "prompt_tokens": 128, "completion_tokens": 45, "total_tokens": 173 }
  }
  ```

### 4.5 `infer_audio`
* **Propósito**: Procesamiento y transcripción de voz/audio en español.
* **Argumentos**:
  * `audio_base64` (string base64 verificado RIFF/WAVE PCM 16kHz, <= 4 MiB, obligatorio).
  * `prompt` (string, 1..8000 caracteres, obligatorio).
  * `schema` (objeto JSON Schema dialecto v2-ext, opcional).
  * `max_tokens` (entero, 1..4096, defecto 1024, opcional).
* **Salida**:
  ```json
  {
    "text": "Transcripción o respuesta al audio recibido",
    "validated": true,
    "usage": { "prompt_tokens": 96, "completion_tokens": 30, "total_tokens": 126 }
  }
  ```

### 4.6 `synthesize_speech`
* **Propósito**: Síntesis de voz hablada en español neutro a partir de texto.
* **Argumentos**:
  * `input` (string, 1..600 caracteres legibles, obligatorio).
  * `voice` (string, defecto `"es_ES-davefx-medium"`, opcional).
  * `speed` (número, 0.5..2.0, defecto 1.0, opcional).
* **Salida**:
  ```json
  {
    "audio_base64": "<bytes WAV codificados en base64>",
    "format": "wav",
    "voice": "es_ES-davefx-medium",
    "chars": 54,
    "duration_est_s": 3.2
  }
  ```
* **Contención de concurrencia**: Si el sintetizador `llama-tts` se encuentra ocupado
  por otra petición concurrente, responde inmediatamente `isError: true` con código
  `tts_busy` (sin colas infinitas ni retención de memoria).

### 4.7 `infer_video`
* **Propósito**: Percepción temporal y espacial sobre clips de video corto.
* **Argumentos**:
  * `video_base64` (string base64 contenedor MP4 con caja ftyp verificado por ffprobe;
    <= 16 MiB, duración <= 10 s, fps <= 30, frames <= 120, obligatorio).
  * `prompt` (string, 1..8000 caracteres, obligatorio).
  * `schema` (objeto JSON Schema dialecto v2-ext, opcional).
  * `max_tokens` (entero, 1..4096, defecto 1024, opcional).
* **Salida**:
  ```json
  {
    "description": "Análisis de eventos temporales observados en el video",
    "validated": true,
    "usage": { "prompt_tokens": 250, "completion_tokens": 55, "total_tokens": 305 }
  }
  ```

### 4.8 `conversational_turn`
* **Propósito**: Diálogo conversacional por turnos con capacidad de streaming de texto
  y síntesis de audio hablada por fragmentos.
* **Argumentos**:
  * `messages` (lista de objetos `{ "role": "user"|"assistant"|"system", "content": "..." }`,
    mínimo 1, máximo 20 turnos, obligatorio).
  * `stream` (booleano, defecto `false`; si `true`, los fragmentos de texto y audio
    se emiten sobre el canal SSE de la sesión).
  * `synthesize_voice` (booleano, defecto `false`; genera audio hablado de la respuesta).
* **Salida síncrona (stream=false)**:
  ```json
  {
    "text": "Respuesta conversacional del asistente",
    "audio_base64": "<opcional si synthesize_voice=true>",
    "usage": { "prompt_tokens": 85, "completion_tokens": 24, "total_tokens": 109 }
  }
  ```
* **Salida streaming (stream=true)**: Los chunks viajan por SSE con eventos
  `turn.chunk` y finalizan con `turn.done`.

---

## 5. Gestión de errores y cancelaciones

### 5.1 Convención de respuestas de error en MCP
Toda invocación fallida a una herramienta responde en la envoltura `CallToolResult`:
```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"error\": \"<codigo_error>\", \"message\": \"<descripcion_segura>\"}"
    }
  ],
  "isError": true
}
```

Códigos de error normativos:
* `missing_token` / `invalid_token` (HTTP 401 a nivel de transporte).
* `insufficient_scope`: el proyecto carece del permiso para la modalidad solicitada.
* `tts_busy`: el motor de voz está en uso; reintento recomendado tras breve pausa.
* `invalid_payload`: argumentos mal formados, tamaño excedido o medio sin firma válida.
* `salida_invalida`: la inferencia del modelo no superó la validación del schema.
* `model_busy`: la cola de inferencia del proyecto se encuentra saturada (429/503).

### 5.2 Cancelación limpia de operaciones
1. El cliente puede enviar la notificación JSON-RPC `notifications/cancelled`
   con el `requestId` de una solicitud en curso.
2. Al recibirla, el gateway interrumpe inmediatamente el slot del motor `llama-server`
   mediante petición al backend local y libera la ranura de concurrencia del proyecto.
3. Si el cliente interrumpe o cierra la conexión TCP/TLS durante un streaming SSE,
   el terminador detecta el cierre y propaga la señal de cancelación al gateway.

---

## 6. Clientes de referencia y protocolo de pruebas negativas

Para la validación de la Fase I3 se fijan dos clientes objetivos de evaluación:

1. **Cliente A (Integración con agente / runtime MCP estándar)**:
   * Consumo mediante cliente MCP Streamable HTTP estándar con cabeceras de autorización
     y sesión (`Mcp-Session-Id`).
   * Verificación de `initialize`, `tools/list` y llamadas a herramientas de texto y visión.
2. **Cliente B (Suite de pruebas deterministas de integración `test_mcp_remote_client.py`)**:
   * Implementación en Python stdlib que ejecuta la matriz completa de casos omnimodales:
     * Consulta a `health` y `capabilities`.
     * Generación de texto estructurado con schema v2-ext.
     * Análisis visual de imagen sintética PNG.
     * Transcripción de audio sintético WAV.
     * Síntesis de voz y verificación del WAV devuelto.
     * Análisis temporal de clip de video MP4.
     * Turno conversacional con y sin voz.
   * **Batería de pruebas negativas**:
     * Rechazo por omisión de `Authorization` (401).
     * Rechazo por `X-Project-ID` discordante (403).
     * Rechazo de `infer_video` por token con scopes restringidos (`insufficient_scope`).
     * Rechazo de audio con URL en lugar de base64 (`invalid_payload`).
     * Exclusión mutua de TTS con colisión forzada (`tts_busy`).
     * Rechazo de salida JSON sintéticamente corrupta frente al schema (`salida_invalida`).
     * Cancelación en vuelo y verificación de liberación de recursos.
