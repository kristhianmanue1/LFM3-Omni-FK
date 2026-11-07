# SPEC I1-VV — Video corto en el gateway con límites y preguntas temporales

Estado: activo al cerrar el gate de I1-VV. Procedencia: PLAN LFM3-2
TAREA I1-VV; ADR-006 aceptado (enmienda de ADR-005: video corto sobre el
artefacto congelado permitido en loopback y `video: true` en
capabilities al cerrar el gate); ADR-006 §4 (inventario y verificación
del hash de `ffmpeg`/`ffprobe`). Extiende SPEC-i1, SPEC-i1-va,
SPEC-i1-vs y SPEC-i1-vr.

## 1. Dialecto de video en `POST /v1/chat/completions`

En `messages[].content[]` se admite la parte:
`{"type": "video_url", "video_url": {"url": "data:video/mp4;base64,..."}}`

- Claves exactas: `type == "video_url"`, objeto `video_url` con sólo la
  clave `"url"`.
- `url`: string que debe cumplir la expresión regular estricta
  `^data:video/mp4;base64,([A-Za-z0-9+/=\s]+)$`.
- Cualquier otra forma (ej. `http://...`, `https://...`, `file://...`,
  data URI de otro formato como `video/webm`, objeto `video_url` no dict,
  o claves extra como `detail`) -> **400 `unknown_content_type`** o
  **400 `external_url_rejected`** antes de tocar el motor (contador en 0).

## 2. Validación de frontera de video (fail-closed, antes del motor)

Sobre los bytes decodificados (`base64` estricto con `validate=True`):

- **Presupuesto de bytes:** `<= 16 MiB` (`MAX_VIDEO_BYTES = 16 * 1024 * 1024`).
- **Estructura del contenedor MP4:**
  - Longitud mínima de cabecera (`len >= 12`).
  - Firma MP4 de la caja `ftyp`: los bytes `4..8` deben ser `b"ftyp"`.
- **Inspección estructural con `ffprobe`:**
  - El gateway resuelve `ffprobe` con PATH fijado
    (`/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin` o el prefix del
    motor resuelto) y verifica que su `sha256` coincida con el hash
    inventariado en F0 §7 / scripts (`FFPROBE_SHA256 =
    "daba6e06838d10260602536a676069cef6d756345e1c6d66268ceb7f2d5e7c39"`,
    inactivable/inyectable sólo en tests).
  - Si el binario `ffprobe` falta o su hash difiere -> **502 `backend_error`**
    (`detail: "ffmpeg_hash_mismatch"`).
  - La inspección extrae streams de video mediante:
    `ffprobe -v error -select_streams v:0 -show_entries
    stream=width,height,r_frame_rate,nb_frames,duration -show_entries
    format=duration -of json input.mp4`.
  - Cotas normativas fail-closed:
    - Al menos un stream de video decodificable.
    - Duración `<= 10.0` s (`MAX_VIDEO_SEGUNDOS`).
    - Tasa de cuadros `<= 30.0` fps (`MAX_VIDEO_FPS`).
    - Cuadros totales `<= 120` (`MAX_VIDEO_FRAMES`).
    - Resolución `ancho * alto <= 2_073_600` píxeles (`MAX_VIDEO_PIXELES =
      1920 * 1080`).
  - Cualquier violación de cotas o fallo de parseo -> **400 `invalid_video`**
    antes de reenviar la petición al backend (contador en 0).

## 3. Preguntas temporales sintéticas fijadas antes de medir

Fijadas **ANTES de medir** (`PLAN-2` TAREA I1-VV, `iteraciones-servicio.md`
§I1-V):
- Tres videos sintéticos en `tests/medios-binarios/` generados con `ffmpeg`
  `lavfi` (sin cámara ni humanos, D-09):
  1. `corpus-vv-01.mp4`: rojo seguido de azul a 8 fps (4.25 s, 34 frames,
     160x120). Pregunta: "¿De qué color es el video al inicio y al final?".
     Orden requerido: "red" antes que "blue" / "rojo" antes que "azul".
  2. `corpus-vv-02.mp4`: verde seguido de amarillo a 8 fps (4.25 s, 34 frames,
     160x120). Pregunta: "¿De qué color es el video al inicio y al final?".
     Orden requerido: "green" antes que "yellow" / "verde" antes que "amarillo".
  3. `corpus-vv-03.mp4`: blanco seguido de negro a 8 fps (4.25 s, 34 frames,
     160x120). Pregunta: "¿De qué color es el video al inicio y al final?".
     Orden requerido: "white" antes que "black" / "blanco" antes que "negro".
- Criterio de pase: **100 % de los casos (3/3) responden con el orden
  temporal correcto**. Si no pasa, video no se anuncia en `capabilities`
  (`video: false`).

## 4. Capabilities al cerrar el gate (ADR-006 §1)

`GET /v1/capabilities` pasa a declarar:
- `entrada: ["texto", "imagen", "audio", "video"]`
- `salida: ["texto", "audio"]`
- `video: true`, `streaming: true`, `voz: true`, `transcripcion: true`,
  `audio: true`.

## 5. Matriz REQ-SPEC-test

| REQ | Propiedad | Verificación |
|---|---|---|
| VV1 | video_url MP4 válido llega al motor (contador 1) y responde | `test_gateway_vv::vv1` |
| VV2 | MP4 corrupto/truncado, firma ftyp ausente o base64 inválido -> 400 `invalid_video`, contador 0 | `test_gateway_vv::vv2*` |
| VV3 | duración >10s, fps >30, frames >120 o resolución >1080p -> 400 `invalid_video`, contador 0 | `test_gateway_vv::vv3` |
| VV4 | URL externa http(s), file o claves extra -> 400 antes del backend, contador 0 | `test_gateway_vv::vv4` |
| VV5 | binario ffprobe ausente o hash alterado -> 502 `ffmpeg_hash_mismatch` | `test_gateway_vv::vv5` |
| VV6 | capabilities anuncia `video: true` y `video` en entrada | `test_gateway_vv::vv6` |
| VV7 | gate temporal sintético 3/3 en orden correcto sobre motor vivo | `tests/medir_video_vv.py` |

## 6. Comandos exactos

```bash
python3.12 -m unittest tests.test_gateway_vv -v
bash run/serve.sh
python3.12 src/gateway_http.py &
python3.12 tests/medir_video_vv.py docs/reviews/evidence/i1-vv-sesion/video_vv.json
python3.12 examples/cliente_i1.py
```

## 7. Límites declarados

- Sólo contenedor MP4 (H.264/yuv420p decodificado por `libmtmd`/`ffmpeg`);
  sin mkv/avi/webm en loopback.
- Duración acotada a `<= 10.0` s y `<= 120` cuadros para contención de
  memoria y contexto del proyector multimodal (`mmproj`).
