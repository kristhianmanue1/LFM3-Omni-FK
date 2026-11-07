# Contrato de Handoff para frontExpert (Perfil W - lfm3-omni v2)

- **Fase**: I4 (Fase 4 del PLAN LFM3-2: Servicio Compartido)
- **Estado**: Aceptado / Listo para adopción externa
- **Procedencia**: `docs/ruteo-ui-frontexpert.md`, ADR-011, `docs/contracts/perfiles-servicio-v2.md`
- **Destino**: Repositorio de UI externa del ecosistema AGTexperts (construido sobre `frontExpert` v2 + `skevi`)

---

## 1. Regla de Ruteo y Límites de Repositorio

Conforme a la decisión del Operador registrada en `docs/ruteo-ui-frontexpert.md`:
1. **Ningún código de interfaz gráfica se aloja dentro de `LFM3-Omni`**: el motor
   y el gateway permanecen como servicios de backend e inferencia puros.
2. Todo encargo de interfaz de usuario (web, móvil o escritorio) se desarrollará
   en un repositorio independiente adoptando `frontExpert` mediante el contrato
   v2 (ADR-0014 upstream) y `skevi` como metodología normativa.
3. Este documento define la interfaz contractual, los esquemas y las garantías
   que el equipo de frontend puede asumir del servicio LFM3-Omni.

---

## 2. Arquitectura de Integración (Patrón BFF)

```
[ Navegador Web / Mobile App ]
             │
      (Cookie de sesión / JWT usuario final)
             ▼
┌──────────────────────────────────────────────┐
│  frontExpert BFF (Next.js / Node / FastAPI)  │
│  - Autenticación y control de usuario        │
│  - Guarda token Bearer de forma segura       │
│  - Saneamiento defensivo de respuestas       │
│  - Mapeo de errores y reintentos             │
└──────────────────────┬───────────────────────┘
                       │ (HTTPS Privado / Bearer Token)
                       ▼
┌──────────────────────────────────────────────┐
│            LFM3-Omni Gateway                 │
│        (https://127.0.0.1:8443)              │
│  /v1/chat/completions (Perfil H / W)         │
│  /capabilities, /health                      │
└──────────────────────────────────────────────┘
```

> [!IMPORTANT]
> **Fuga de credenciales**: El token `Bearer` de proyecto emitido por LFM3-Omni
> NUNCA debe entregarse al cliente web ni incrustarse en el bundle de frontend.
> Todas las llamadas deben originarse en el backend del proyecto UI (BFF).

---

## 3. Matriz de Capacidades Omnimodales para frontExpert

| Modalidad | Endpoint | Payload / Formato | Salida para UI |
|---|---|---|---|
| **Texto Libre** | `POST /v1/chat/completions` | `messages: [{role, content}]` | Markdown / texto saneado |
| **Streaming SSE** | `POST /v1/chat/completions` | `stream: true` | Flujo de tokens en tiempo real |
| **Esquema Estructurado** | `POST /v1/chat/completions` | `response_format: {json_schema}` | JSON tipado para render de widgets |
| **Visión (Imágenes)** | `POST /v1/chat/completions` | `image_url: {url: "data:image/..."}` | Análisis visual / OCR / descripción |
| **Audio (ASR)** | `POST /v1/chat/completions` | WAV 16kHz mono base64 + prompt | Texto transcrito editable |
| **Voz (TTS)** | `POST /v1/chat/completions` | Directiva TTS / síntesis | WAV 24kHz base64 para reproducción |
| **Video Corto** | `POST /v1/chat/completions` | MP4 base64 ($\le 10\text{ s}$) | Comprensión temporal de video |
| **Cancelación** | `DELETE /requests/{id}` | Parámetro `request_id` | Confirmación de cancelación |

---

## 4. Máquina de Estados Recomendada para la UI

Para una experiencia omnimodal fluida y robusta, el frontend debe implementar
los siguientes estados en su gestor de estado (React/Zustand o Vue/Pinia):

```
       ┌───────────┐
       │   IDLE    │ ◄────────────────────────┐
       └─────┬─────┘                          │
             │                                │
             ├─── [Grabar Voz] ──► RECORDING ─┘
             │                          │
             │                   (Audio capturado)
             │                          ▼
             │                    TRANSCRIBING
             │                          │
             │                   (Texto obtenido)
             ▼                          ▼
       THINKING / STREAMING ◄───────────┘
             │
             ├─── [Recibir Tokens] ──► Render Markdown incremental
             │
             ├─── [Opción TTS activa] ──► SPEAKING (Audio playback)
             │
             ├─── [Usuario presiona Stop] ──► CANCELLED ──► IDLE
             │
             └─── [Error de red / 429 / 503] ──► ERROR_STATE ──► IDLE
```

---

## 5. Manejo de Errores y Exclusiones de Concurrencia

1. **HTTP 503 (`tts_busy`)**:
   - Ocurre si dos usuarios solicitan síntesis de voz (`llama-tts`) simultáneamente.
   - La UI no debe entrar en pánico ni reintentar agresivamente: debe mostrar
     un indicador "Canal de voz ocupado, generando solo texto" y ofrecer un
     botón de "Reintentar audio" manual.
2. **HTTP 429 (`rate_limit_exceeded`)**:
   - El proyecto ha superado su cuota de ráfaga o peticiones por minuto.
   - El BFF debe propagar el tiempo de espera recomendado (`retry_after`) y la
     UI mostrar una cuenta regresiva.
3. **Cancelación**:
   - Cuando el usuario cancela una generación en progreso, la UI debe abortar el
     `AbortController` local e invocar inmediatamente el endpoint de cancelación
     del BFF para que el backend libere la ranura de inferencia en LFM3-Omni.

---

## 6. Saneamiento y Seguridad en el Renderizado

> [!CAUTION]
> **Datos no confiables**: La salida de cualquier LLM es dato no confiable
> (Principio 7 del estándar). No debe insertarse directamente mediante
> `dangerouslySetInnerHTML` ni renderizarse como HTML ejecutable sin filtrar.
> frontExpert debe usar bibliotecas de saneamiento probadas (`DOMPurify` o
> renderizadores de Markdown con soporte de sandbox).
