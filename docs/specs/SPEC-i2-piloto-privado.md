# SPEC-i2: Especificación técnica del piloto privado HTTPS (I2)

Estado: PROPUESTO para ejecución en TAREA I2-D (PLAN LFM3-2).
Base: contratos `servicio-general-v2.md` y `perfiles-servicio-v2.md` (§H).
Procedencia: S-02, S-03, S-04, S-07, S-08, S-10; ADR-005, ADR-008, ADR-009.
Límite de lectura: no forma parte de la ruta de lectura de skevi-gate.json.

## 1. Propósito y alcance del piloto

Esta especificación formaliza el marco técnico para la transición del
servicio loopback uniusuario (I1/I1-V) hacia un piloto privado multi-inquilino
por invitación (I2) con autenticación Bearer por proyecto, cuotas acotadas,
política estricta de no-egreso (anti-SSRF) y observabilidad estructurada.

El piloto privado opera exclusivamente sobre dos proyectos invitados:
1. `proyecto-alpha` (consumidor tipo Agente / CLI analítico de medios).
2. `proyecto-beta` (consumidor tipo Dispositivo / Robot Perfil D o UI frontExpert).

Queda explícitamente fuera del alcance de I2:
- Exposición pública anónima o registro abierto de usuarios.
- Passthrough libre o desprotegido de peticiones hacia el motor 8091.
- Conexión de actuadores físicos reales sin validación del controlador.
- Tráfico saliente desde el motor de inferencia hacia redes externas.

## 2. Modelo de identidad, autenticación y scopes

### 2.1 Formato de credencial y cabeceras
Todo acceso al servicio requiere autenticación vía cabecera HTTP estándar:
```http
Authorization: Bearer <token_secreto>
X-Project-ID: <id_proyecto_solicitante>
```

Invariantes de autenticación y validación de cabeceras:
- El token es una cadena alfanumérica opaca de 32 a 64 caracteres.
- Se prohíbe terminantemente aceptar tokens en parámetros de consulta (URL)
  o en el cuerpo JSON de la petición.
- El servidor extrae el token, calcula su digest `SHA-256` y busca el hash en
  el registro seguro de credenciales (`config/tokens.json`).
- Si la cabecera `Authorization` está ausente o no es un Bearer válido,
  responde `401 Unauthorized` con `WWW-Authenticate: Bearer` y código
  `missing_token` o `invalid_token`.
- La cabecera `X-Project-ID` es estrictamente obligatoria. Si está ausente o
  contiene caracteres no alfanuméricos / guiones (p. ej. `../`), responde `400`
  `invalid_request_error` con código `missing_project_id` o `invalid_project_id`.
- Si el token es válido pero `X-Project-ID` no coincide con el `project_id`
  asociado al hash en el registro, responde `403 Forbidden` (`project_mismatch`).
- Si el token posee la marca `"revoked": true`, el servidor rechaza la
  solicitud inmediatamente con `403 Forbidden` (`credential_revoked`).

### 2.2 Estructura del registro de credenciales (`config/tokens.json`)
El archivo reside en el host con permisos estrictos `0600` (sólo lectura/escritura
por el usuario del servicio):
```json
{
  "version": 1,
  "projects": {
    "proyecto-alpha": {
      "token_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "revoked": false,
      "scopes": ["infer:text", "infer:vision", "infer:audio", "speech:synthesize"],
      "rate_limit": {
        "requests_per_minute": 60,
        "burst": 5,
        "max_concurrent": 1,
        "max_queue": 2,
        "queue_timeout_seconds": 10.0
      }
    },
    "proyecto-beta": {
      "token_sha256": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
      "revoked": false,
      "scopes": ["infer:text", "infer:vision", "profile:d"],
      "rate_limit": {
        "requests_per_minute": 30,
        "burst": 3,
        "max_concurrent": 1,
        "max_queue": 2,
        "queue_timeout_seconds": 10.0
      }
    }
  }
}
```

La recarga del registro ante revocaciones se realiza en memoria sin necesidad de
reiniciar el proceso gateway ni interrumpir las conexiones de otros proyectos.

### 2.3 Matriz determinista de autorización por Scope
Cada operación exige un scope específico concedido en el registro:

| Ruta HTTP | Método | Criterio de Payload / Modalidad | Scope Requerido |
|---|---|---|---|
| `/health` | `GET` | Verificación mínima de vitalidad (público) | *(Ninguno)* |
| `/capabilities` | `GET` | Consulta de modalidades activas | Cualquier token válido |
| `/v1/models` | `GET` | Catálogo de modelos activos | Cualquier token válido |
| `/v1/chat/completions` | `POST` | Mensajes con sólo texto | `infer:text` |
| `/v1/chat/completions` | `POST` | Mensajes con `image_url` o `video_url` | `infer:vision` |
| `/v1/chat/completions` | `POST` | Mensajes con `input_audio` | `infer:audio` |
| `/v1/chat/completions` | `POST` | Mensajes con schema/propuesta robótica | `profile:d` |
| `/v1/audio/speech` | `POST` | Síntesis de voz español (TTS) | `speech:synthesize` |
| `/requests/{id}` | `DELETE` | Cancelación de solicitud en vuelo propia | Token del proyecto dueño |

Si el proyecto no tiene el scope exigido para la modalidad solicitada, el
gateway rechaza la petición con `403 Forbidden` (`insufficient_scope`).

## 3. Topología de red, TLS y contención de egreso

### 3.1 Arquitectura de red en capas y terminador TLS
```text
[Cliente Externo Invitado]
       │ (HTTPS con TLS 1.3 / TLS 1.2 sobre puerto 8443)
       ▼
[Terminador TLS stdlib (src/gateway_tls.py)]
       │ (HTTP loopback limpio en 127.0.0.1:8092)
       ▼
[Gateway Modular LFM3 (src/gateway_http.py) — Auth, Quotas, Frontera]
       │ (HTTP interno en 127.0.0.1:8091 / CLI llama-tts en subproceso 0600)
       ▼
[Motor LFM3-Omni (llama-server 8091)]
```

- **Implementación de TLS**: Terminador en Python stdlib 3.12+ (`ssl.SSLContext`)
  sin librerías de terceros (cumpliendo Principio 1 y ADR-005).
- **Certificado y Confianza**: Certificado local con SAN `localhost` / `lfm3.local`,
  publicando su huella SHA-256 en la documentación del piloto para verificación
  estricta por los clientes, prohibiendo el uso de flags inseguras (`-k` / `insecure`).
- **Aislamiento de puertos**:
  - `8091`: `127.0.0.1` exclusivo para `llama-server`.
  - `8092`: `127.0.0.1` exclusivo para `gateway_http.py`.
  - `8443`: Interfaz privada autorizada para el piloto privado.

### 3.2 Contención estricta de egreso (Zero Egress y anti-SSRF)
Para prevenir ataques de falsificación de peticiones del lado del servidor (SSRF)
y exfiltración de información:
1. **Allowlist estricta de esquemas**: Todo medio binario (imagen, audio, video)
   debe suministrarse obligatoriamente como `data:<mime>;base64,...`.
   Cualquier esquema URI (`http://`, `https://`, `ftp://`, `file://`, etc.)
   es rechazado inmediatamente en la frontera con `400` `invalid_payload`.
2. **Aislamiento de procesos**: Los subprocesos del motor (`llama-server`,
   `llama-tts`, `ffmpeg`) operan sin permisos de red saliente (mediante
   perfiles de sandbox OS).
3. **Regla Fail-Closed por inviabilidad**: Si el mecanismo de sandbox a nivel OS
   no es viable o verificable en el entorno sin alterar el cortafuegos global,
   el sistema opera en modo fail-closed denegando la exposición remota y
   manteniendo el servicio confinado a loopback local.
4. **Mantenimiento**: Hugging Face y Homebrew se consultan exclusivamente de
   manera manual durante ventanas de mantenimiento fuera de inferencia activa.

## 4. Admisión, cuotas, colas y limitación de tasa

### 4.1 Algoritmo de Token Bucket por proyecto
Cada proyecto posee su propio cubo de fichas (*token bucket*):
- `capacidad`: valor de `burst` configurado.
- `tasa_relleno`: `requests_per_minute / 60.0` fichas por segundo.
- Cada petición admitida consume 1 ficha.
- Si el cubo está vacío, el servidor responde inmediatamente con código
  `429 Too Many Requests`, cabecera `Retry-After: <segundos>` y cuerpo JSON de
  error con código `rate_limit_exceeded`.

### 4.2 Control de concurrencia y prevención de inanición (*Fair Queuing*)
Dado que `LiquidAI/LFM3-Omni-2B-GGUF` es un motor mono-hilo de inferencia:
1. Concurrencia de ejecución activa por proyecto: `max_concurrent = 1`.
2. Capacidad máxima de cola por proyecto: `max_queue = 2`.
3. Tiempo máximo de espera en cola: `queue_timeout_seconds = 10.0` s para todos
   los proyectos (alineado con el SLO global).
4. **Planificación Justa (Fair Queuing)**: El despachador atiende peticiones
   en cola alternando turnos entre proyectos activos (round-robin / interleaving).
   Una ráfaga de peticiones largas de `proyecto-alpha` no puede bloquear
   indefinidamente las peticiones de `proyecto-beta`.
5. **Rechazo por cola llena**: Si la cola del proyecto está llena, el servidor
   responde `503 Service Unavailable` con código `overloaded` (respetando
   `servicio-general-v2.md`).
6. **Expiración de cola**: Si la espera supera `queue_timeout_seconds`, se expulsa
   y responde `504 Gateway Timeout` con código `queue_timeout`.
7. **Liberación garantizada**: Si el cliente se desconecta durante la espera o
   generación, se cancela la tarea en el motor (vía `/slots` en 8091) y se libera
   el cupo en menos de 500 ms, sin dejar slots fantasma.

## 5. Matriz de errores cerrada

Todos los errores del piloto devuelven el sobre normativo de error compatible
OpenAI y contrato general v2 con `request_id` y `retryable`:
```json
{
  "error": {
    "message": "Descripción clara orientada a la acción",
    "type": "invalid_request_error | auth_error | rate_limit_error | server_error",
    "code": "identificador_estable",
    "param": "campo_relevante_o_null",
    "retryable": false,
    "request_id": "req-12345678"
  }
}
```

| HTTP Status | error.type | error.code | retryable | Motivo / Acción esperada |
|---|---|---|---|---|
| `400` | `invalid_request_error` | `invalid_payload` / `unknown_field` | `false` | Schema, campo o URI no permitida en frontera |
| `400` | `invalid_request_error` | `missing_project_id` / `invalid_project_id` | `false` | Cabecera X-Project-ID ausente o formato inválido |
| `401` | `auth_error` | `missing_token` / `invalid_token` | `false` | Cabecera Authorization ausente o token erróneo |
| `403` | `auth_error` | `project_mismatch` / `credential_revoked` | `false` | Token no corresponde al proyecto o fue revocado |
| `403` | `auth_error` | `insufficient_scope` | `false` | Token carece del scope para la modalidad pedida |
| `404` | `invalid_request_error` | `not_found` | `false` | Recurso o request_id ajeno o inexistente |
| `413` | `invalid_request_error` | `payload_too_large` | `false` | Bytes de medios o JSON exceden cotas máximas |
| `429` | `rate_limit_error` | `rate_limit_exceeded` | `true` | Límite por minuto superado (reintentar tras Retry-After) |
| `500` | `server_error` | `internal_error` | `false` | Fallo no controlado del gateway |
| `502` | `server_error` | `output_not_valid` | `false` | Salida del motor no supera validación de esquema |
| `503` | `server_error` | `overloaded` | `true` | Cola del proyecto saturada (reintentar con backoff) |
| `503` | `server_error` | `tts_busy` / `slot_not_released` | `true` | Recurso no reentrante ocupado (reintentar con backoff) |
| `504` | `server_error` | `queue_timeout` / `engine_timeout` | `true` | Tiempo de espera en cola o inferencia excedido |

## 6. Arquitectura de doble evaluación de carga (D-04)

De acuerdo con el requisito normativo D-04 y S-08, las mediciones de rendimiento
se dividen de forma estricta en dos experimentos no combinables:

### 6.1 Experimento A: Admisión y comportamiento del piloto (End-to-End)
- **Objetivo**: Medir la capacidad real de admisión, retención de colas,
  aislamiento A/B y latencia bajo la configuración exacta de despliegue.
- **Configuración**: Concurrencia de entrada ofrecida 1, 2, 4 y 8 clientes.
- **Métricas obligatorias registradas**:
  - Tasa de admisión real vs. tasa de rechazo controlado (`429` y `503`).
  - Tiempo de espera en cola (p50, p95).
  - TTFT (*Time To First Token*) en solicitudes admitidas.
  - Tiempo total de respuesta (p50, p95).
  - Verificación empírica de equidad inter-inquilinos (Proyecto B no sufre
    inanición ante ráfagas de Proyecto A).

### 6.2 Experimento B: Capacidad aislada del backend (Engine Benchmark)
- **Objetivo**: Conocer el límite físico del motor `llama-server` y `llama-tts`
  en el hardware anfitrión sin sobrecarga del gateway.
- **Entorno**: Ejecución aislada en ventana dedicada, con datos sintéticos fijados
  y registro térmico del procesador / GPU / memoria.
- **Invariante**: Los resultados del Experimento B **nunca** se emplean para
  afirmar capacidad disponible en el piloto sin pasar por el Experimento A.
