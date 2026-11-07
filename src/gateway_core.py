"""Núcleo de políticas del gateway (SPEC I1, ADR-004/005).

Políticas puras, sin ningún import de transporte (frontera interna
verificada por test_g6): validación de payload, imágenes, schema y
salida del modelo; límites, allowlist de rutas y capabilities
declaradas. Este módulo es el núcleo compartible con un futuro
adaptador MCP v2 (S-05: igual política HTTP/MCP).
"""

import base64
import binascii
import json
import math
import re
import struct
import zlib

DEFAULT_BACKEND = "http://127.0.0.1:8091"
DEFAULT_PORT = 8092
MAX_BODY_BYTES = 32 * 1024 * 1024
MAX_IMAGEN_BYTES = 8 * 1024 * 1024
MAX_PIXELES = 16_777_216
MAX_AUDIO_BYTES = 4 * 1024 * 1024      # SPEC-i1-va §2
MAX_AUDIO_SEGUNDOS = 60.0              # SPEC-i1-va §2
MAX_TTS_CHARS = 600                    # SPEC-i1-vs §1
TTS_TIMEOUT_S = 120                    # SPEC-i1-vs §2
LLAMA_TTS_SHA256 = (                   # F0 §7 / SPEC-i1-vs §2
    "b983acbd59f89df0da0cce9665c75366b94f5736331470fc73d2b8bb5c84c377"
)
MAX_VIDEO_BYTES = 16 * 1024 * 1024     # SPEC-i1-vv §2
MAX_VIDEO_SEGUNDOS = 10.0              # SPEC-i1-vv §2
MAX_VIDEO_FPS = 30.0                   # SPEC-i1-vv §2
MAX_VIDEO_FRAMES = 120                 # SPEC-i1-vv §2
MAX_VIDEO_PIXELES = 1920 * 1080        # SPEC-i1-vv §2
FFPROBE_SHA256 = (                     # F0 §7 / SPEC-i1-vv §2
    "daba6e06838d10260602536a676069cef6d756345e1c6d66268ceb7f2d5e7c39"
)
MAX_PROPIEDADES = 32
MAX_PROPIEDADES_ANIDADO = 16
MAX_TOKENS = 4096
MAX_SSE_LINE_BYTES = 64 * 1024         # SPEC-i1-vr §2
BACKEND_TIMEOUT_S = 300

CLAVES_TOP = {
    "model", "messages", "tools", "tool_choice", "temperature",
    "top_p", "max_tokens", "response_format", "stream",
}
CLAVES_TTS = {"input", "language", "response_format", "model"}
CLAVES_NO_SOPORTADAS = set()
MAX_ENUM_ITEMS = 32
MAX_ARRAY_ITEMS = 64
ROLES = {"system", "user", "assistant"}
TIPOS_ESCALARES = {"string", "integer", "number", "boolean"}
TIPOS_SCHEMA = {"string", "integer", "number", "boolean", "array", "object"}
FIRMA_PNG = b"\x89PNG\r\n\x1a\n"
URL_IMAGEN_RE = re.compile(
    r"^data:image/(png|jpeg);base64,([A-Za-z0-9+/=\s]+)$")
URL_VIDEO_RE = re.compile(
    r"^data:video/mp4;base64,([A-Za-z0-9+/=\s]+)$")
DATA_RE = re.compile(r"^data:")

# Allowlist cerrado (SPEC-i1 §2): cualquier otra ruta es 404.
RUTAS_PERMITIDAS = (
    "POST /v1/chat/completions",
    "POST /v1/audio/speech",
    "GET /v1/models",
    "GET /v1/capabilities",
    "GET /healthz",
)
RUTAS_MCP = (
    "POST /mcp",
    "GET /mcp",
)

# Capabilities declaradas por SPEC, jamás derivadas del motor y jamás
# anunciando lo no activo (SPEC-i1 §3; ADR-006 §1: una modalidad se
# anuncia al cerrar su TAREA — transcripcion con I1-VA, voz/audio con
# I1-VS, streaming con I1-VR, video con I1-VV, SPEC-i1-vv §4).
CAPABILITIES = {
    "entrada": ["texto", "imagen", "audio", "video"],
    "salida": ["texto", "audio"],
    "streaming": True,
    "audio": True,
    "video": True,
    "voz": True,
    "transcripcion": True,
    "schema": "dialecto-v2",
    "version": "i1",
}


class ErrorV2(Exception):
    """Error estructurado de la frontera; nunca eco del payload."""

    def __init__(self, status, code, message, **extra):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra

    def cuerpo(self, request_id):
        tipo = self.extra.get("type")
        if not tipo:
            if self.status in (401, 403):
                tipo = "auth_error"
            elif self.status == 429:
                tipo = "rate_limit_error"
            elif self.status in (400, 404, 413):
                tipo = "invalid_request_error"
            else:
                tipo = "server_error"
        retryable = self.extra.get("retryable")
        if retryable is None:
            retryable = self.status in (429, 503, 504)
        error = {
            "code": self.code,
            "message": self.message,
            "type": tipo,
            "param": self.extra.get("param", None),
            "retryable": retryable,
            "request_id": request_id,
        }
        for k, v in self.extra.items():
            if k not in error:
                error[k] = v
        return {"error": error}


def _error(status, code, message, **extra):
    raise ErrorV2(status, code, message, **extra)


def _rechazar_constante(nombre):
    """parse_constant de JSON: NaN/Infinity no es JSON (RFC 8259)."""
    raise ValueError(f"constante no-JSON: {nombre}")


# ------------------------------------------------------------ imágenes

def validar_png(datos):
    if len(datos) > MAX_IMAGEN_BYTES:
        _error(400, "invalid_image", "imagen sobre el presupuesto de bytes")
    if len(datos) < 8 or not datos.startswith(FIRMA_PNG):
        _error(400, "invalid_image", "firma PNG ausente o falsa")
    offset = 8
    dims = None
    idat = 0
    iend = False
    while offset + 8 <= len(datos):
        longitud = struct.unpack(">I", datos[offset:offset + 4])[0]
        tipo = datos[offset + 4:offset + 8]
        fin = offset + 12 + longitud
        if fin > len(datos):
            _error(400, "invalid_image", "PNG truncado")
        cuerpo = datos[offset + 8:offset + 8 + longitud]
        crc_guardado = struct.unpack(">I", datos[fin - 4:fin])[0]
        if zlib.crc32(tipo + cuerpo) & 0xFFFFFFFF != crc_guardado:
            _error(400, "invalid_image", "CRC de chunk inválido")
        if tipo == b"IHDR":
            if longitud != 13:
                _error(400, "invalid_image", "IHDR inválido")
            ancho, alto = struct.unpack(">II", cuerpo[0:8])
            dims = (ancho, alto)
        elif tipo == b"IDAT":
            idat += 1
        elif tipo == b"IEND":
            iend = True
        offset = fin
    if dims is None or idat < 1 or not iend:
        _error(400, "invalid_image", "PNG incompleto")
    if offset != len(datos):
        _error(400, "invalid_image", "datos tras IEND")
    ancho, alto = dims
    if ancho * alto > MAX_PIXELES:
        _error(400, "invalid_image", "imagen sobre el presupuesto de píxeles")


def validar_jpeg(datos):
    if len(datos) > MAX_IMAGEN_BYTES:
        _error(400, "invalid_image", "imagen sobre el presupuesto de bytes")
    if len(datos) < 4 or not datos.startswith(b"\xff\xd8\xff"):
        _error(400, "invalid_image", "firma JPEG ausente o falsa")
    if not datos.endswith(b"\xff\xd9"):
        _error(400, "invalid_image", "JPEG truncado")
    dims = None
    i = 2
    while i + 4 < len(datos):
        if datos[i] != 0xFF:
            i += 1
            continue
        marcador = datos[i + 1]
        if marcador in (0xC0, 0xC2):  # SOF0 / SOF2: únicos del dialecto
            if i + 9 > len(datos):
                _error(400, "invalid_image", "JPEG truncado")
            alto, ancho = struct.unpack(">HH", datos[i + 5:i + 9])
            dims = (ancho, alto)
            break
        if 0xC0 <= marcador <= 0xCF and marcador not in (0xC4, 0xC8, 0xCC):
            _error(400, "invalid_image", "SOF no soportado por el dialecto")
        if marcador == 0xD8 or 0xD0 <= marcador <= 0xD7 or marcador == 0x01:
            i += 2
            continue
        longitud = struct.unpack(">H", datos[i + 2:i + 4])[0]
        i += 2 + longitud
    if dims is None:
        _error(400, "invalid_image", "JPEG sin SOF parseable")
    ancho, alto = dims
    if ancho * alto > MAX_PIXELES:
        _error(400, "invalid_image", "imagen sobre el presupuesto de píxeles")


def validar_imagen(url):
    m = URL_IMAGEN_RE.match(url)
    if m is None:
        if DATA_RE.match(url) or url.startswith("http://") \
                or url.startswith("https://") or url.startswith("file://") \
                or url.startswith("ftp://"):
            _error(400, "external_url_rejected",
                   "sólo se acepta data:image/png|jpeg;base64; URLs externas "
                   "no salen de esta máquina")
        _error(400, "invalid_image", "URL de imagen no admitida")
    formato, crudo = m.group(1), m.group(2)
    try:
        datos = base64.b64decode(crudo, validate=True)
    except (binascii.Error, ValueError):
        _error(400, "invalid_image", "base64 de imagen inválido")
    if formato == "png":
        validar_png(datos)
    else:
        validar_jpeg(datos)


# ------------------------------------------------------------------ audio

def validar_wav(datos, exigir_muestras=False):
    """WAV PCM 16-bit bien formado y dentro de presupuesto (SPEC-i1-va
    §2; exigir_muestras=True en SPEC-i1-vs §2 para salida de síntesis).
    Fail-closed ante cualquier desvío estructural: un solo fmt y
    un solo data (duplicados = ambigüedad para el motor, se rechazan)
    y tamaño RIFF consistente con el archivo."""
    if len(datos) > MAX_AUDIO_BYTES:
        _error(400, "invalid_audio", "audio sobre el presupuesto de bytes")
    if len(datos) < 44 or datos[:4] != b"RIFF" or datos[8:12] != b"WAVE":
        _error(400, "invalid_audio", "firma RIFF/WAVE ausente o falsa")
    if struct.unpack("<I", datos[4:8])[0] != len(datos) - 8:
        _error(400, "invalid_audio", "tamaño RIFF inconsistente con el archivo")
    offset, fmt, data, visto_data = 12, None, 0, False
    while offset + 8 <= len(datos):
        longitud = struct.unpack("<I", datos[offset + 4:offset + 8])[0]
        tipo = datos[offset:offset + 4]
        fin = offset + 8 + longitud
        if fin > len(datos):
            _error(400, "invalid_audio", "chunk truncado")
        cuerpo = datos[offset + 8:fin]
        if tipo == b"fmt ":
            if longitud != 16:
                _error(400, "invalid_audio", "fmt inválido")
            if fmt is not None:
                _error(400, "invalid_audio", "chunk fmt duplicado")
            fmt = struct.unpack("<HHIIHH", cuerpo)
        elif tipo == b"data":
            if visto_data:
                _error(400, "invalid_audio", "chunk data duplicado")
            visto_data, data = True, longitud
        offset = fin
    if offset != len(datos):
        _error(400, "invalid_audio", "bytes sobrantes tras el último chunk")
    if fmt is None or not visto_data:
        _error(400, "invalid_audio", "WAV sin fmt o sin data")
    formato, canales, tasa, _byte_rate, _alineacion, bits = fmt
    if formato != 1:
        _error(400, "invalid_audio", "sólo PCM (formato 1)")
    if bits != 16:
        _error(400, "invalid_audio", "sólo muestras de 16 bits")
    if canales not in (1, 2):
        _error(400, "invalid_audio", "canales fuera del dialecto")
    if not 1 <= tasa <= 96000:
        _error(400, "invalid_audio", "tasa de muestreo fuera de rango")
    if exigir_muestras and (data <= 0 or data % (canales * 2) != 0):
        _error(400, "invalid_audio", "WAV sin muestras válidas")
    duracion = data / (tasa * canales * 2)
    if duracion > MAX_AUDIO_SEGUNDOS:
        _error(400, "invalid_audio", "audio sobre el presupuesto de duración")


def validar_audio_entrada(parte):
    """Parte input_audio del dialecto v2 (SPEC-i1-va §1): claves
    exactas, format wav, base64 estricto y WAV válido. El audio entra
    como datos; audio_url no existe en el dialecto (la parte cae en
    unknown_content_type antes del motor)."""
    if parte.get("format") != "wav":
        _error(400, "invalid_audio", "sólo format wav en el dialecto v2")
    crudo = parte.get("data")
    if not isinstance(crudo, str):
        _error(400, "invalid_audio", "data de audio inválido")
    try:
        datos = base64.b64decode(crudo, validate=True)
    except (binascii.Error, ValueError):
        _error(400, "invalid_audio", "base64 de audio inválido")
    validar_wav(datos)


def validar_payload_tts(payload):
    """Valida cuerpo de POST /v1/audio/speech (SPEC-i1-vs §1, ADR-007).
    Rechaza claves desconocidas (voice, speaker_ref, stream, etc.),
    exige input string 1..600 sin caracteres de control, language es y
    response_format wav. Devuelve el texto validado."""
    if not isinstance(payload, dict):
        _error(400, "invalid_json", "el cuerpo debe ser un objeto JSON")
    desconocidas = set(payload) - CLAVES_TTS
    if desconocidas:
        _error(400, "unknown_field",
               f"{len(desconocidas)} campo(s) no admitidos en /v1/audio/speech")
    texto = payload.get("input")
    if not isinstance(texto, str) or not (1 <= len(texto) <= MAX_TTS_CHARS):
        _error(400, "invalid_tts_input",
               f"input debe ser string de 1..{MAX_TTS_CHARS} caracteres")
    if any(ord(c) < 32 or ord(c) == 127 or not c.isprintable() for c in texto):
        _error(400, "invalid_tts_input",
               "input contiene caracteres de control o no imprimibles")
    if not texto.strip():
        _error(400, "invalid_tts_input",
               "input no puede contener sólo espacios")
    idioma = payload.get("language", "es")
    if idioma != "es":
        _error(400, "unsupported_field_value",
               "sólo language 'es' admitido en el dialecto v2")
    formato = payload.get("response_format", "wav")
    if formato != "wav":
        _error(400, "unsupported_field_value",
               "sólo response_format 'wav' admitido en el dialecto v2")
    modelo = payload.get("model")
    if modelo is not None and not isinstance(modelo, str):
        _error(400, "unsupported_field_value", "model debe ser string")
    return texto


def validar_mp4_bytes(datos):
    """Valida bytes de un MP4 en memoria (SPEC-i1-vv §2): límite de bytes
    y firma MP4 con caja ftyp presente."""
    if len(datos) > MAX_VIDEO_BYTES:
        _error(400, "invalid_video", "video sobre el presupuesto de bytes")
    if len(datos) < 12 or datos[4:8] != b"ftyp":
        _error(400, "invalid_video", "firma MP4/ftyp ausente o falsa")


def validar_video_entrada(url, inspector=None):
    """Parte video_url del dialecto v2 (SPEC-i1-vv §1): sólo data URI
    base64 estricto de MP4; URLs externas rechazadas; bytes y cotas
    validados antes del motor."""
    m = URL_VIDEO_RE.match(url)
    if m is None:
        if url.startswith("http://") or url.startswith("https://") \
                or url.startswith("file://") or url.startswith("ftp://"):
            _error(400, "external_url_rejected",
                   "sólo se acepta data:video/mp4;base64; URLs externas "
                   "no salen de esta máquina")
        if DATA_RE.match(url):
            _error(400, "invalid_video",
                   "sólo data:video/mp4;base64 admitido en el dialecto v2")
        _error(400, "invalid_video", "URL de video no admitida")
    crudo = m.group(1)
    try:
        datos = base64.b64decode(crudo, validate=True)
    except (binascii.Error, ValueError):
        _error(400, "invalid_video", "base64 de video inválido")
    validar_mp4_bytes(datos)
    if inspector is not None:
        inspector(datos)


# -------------------------------------------------------------- dialecto


def _validar_propiedad_escalar(def_prop):
    if not isinstance(def_prop, dict):
        _error(400, "unsupported_schema", "definición de propiedad no es dict")
    tipo = def_prop.get("type")
    if not isinstance(tipo, str) or tipo not in TIPOS_ESCALARES:
        _error(400, "unsupported_schema", f"tipo no escalar: {tipo}")
    claves_permitidas = {"type"}
    if "enum" in def_prop:
        claves_permitidas.add("enum")
        enums = def_prop["enum"]
        if not isinstance(enums, list) \
                or not (1 <= len(enums) <= MAX_ENUM_ITEMS):
            _error(400, "unsupported_schema",
                   f"enum debe ser lista de 1..{MAX_ENUM_ITEMS} elementos")
        vistos = []
        for e in enums:
            if tipo == "string":
                if not isinstance(e, str):
                    _error(400, "unsupported_schema",
                           "elemento enum no es string")
            elif tipo == "boolean":
                if not isinstance(e, bool):
                    _error(400, "unsupported_schema",
                           "elemento enum no es boolean")
            elif tipo == "integer":
                if isinstance(e, bool) or not isinstance(e, int):
                    _error(400, "unsupported_schema",
                           "elemento enum no es integer")
            elif tipo == "number":
                if isinstance(e, bool) or not isinstance(e, (int, float)):
                    _error(400, "unsupported_schema",
                           "elemento enum no es number")
            for v in vistos:
                if (tipo == "number" and v == e) \
                        or (type(v) is type(e) and v == e):
                    _error(400, "unsupported_schema",
                           "elementos de enum duplicados")
            vistos.append(e)

    if "minimum" in def_prop or "maximum" in def_prop:
        if tipo not in {"integer", "number"}:
            _error(400, "unsupported_schema",
                   "minimum/maximum sólo permitidos en integer y number")
        min_v = def_prop.get("minimum")
        max_v = def_prop.get("maximum")
        if min_v is not None:
            claves_permitidas.add("minimum")
            if isinstance(min_v, bool) or not isinstance(min_v, (int, float)) \
                    or not math.isfinite(min_v):
                _error(400, "unsupported_schema",
                       "minimum debe ser numérico finito")
        if max_v is not None:
            claves_permitidas.add("maximum")
            if isinstance(max_v, bool) or not isinstance(max_v, (int, float)) \
                    or not math.isfinite(max_v):
                _error(400, "unsupported_schema",
                       "maximum debe ser numérico finito")
        if min_v is not None and max_v is not None and min_v > max_v:
            _error(400, "unsupported_schema",
                   "minimum no puede ser mayor que maximum")

    sobrantes = set(def_prop) - claves_permitidas
    if sobrantes:
        _error(400, "unsupported_schema",
               f"keywords no permitidas en propiedad escalar: {sobrantes}")


def _validar_propiedad_v2_ext(def_prop, nivel=0):
    if not isinstance(def_prop, dict):
        _error(400, "unsupported_schema", "definición de propiedad no es dict")
    tipo = def_prop.get("type")
    if not isinstance(tipo, str):
        _error(400, "unsupported_schema", "type debe ser string")
    if tipo in TIPOS_ESCALARES:
        _validar_propiedad_escalar(def_prop)
        return

    if nivel > 0:
        _error(400, "unsupported_schema",
               "profundidad mayor a 1 no admitida en dialecto v2-ext")

    if tipo == "array":
        sobrantes = set(def_prop) - {"type", "items", "minItems", "maxItems"}
        if sobrantes:
            _error(400, "unsupported_schema",
                   f"keywords no permitidas en array: {sobrantes}")
        items = def_prop.get("items")
        if not isinstance(items, dict):
            _error(400, "unsupported_schema", "items de array debe ser objeto")
        min_i = def_prop.get("minItems")
        max_i = def_prop.get("maxItems")
        if min_i is not None:
            if isinstance(min_i, bool) or not isinstance(min_i, int) \
                    or not (0 <= min_i <= MAX_ARRAY_ITEMS):
                _error(400, "unsupported_schema",
                       f"minItems debe ser entero 0..{MAX_ARRAY_ITEMS}")
        if max_i is not None:
            if isinstance(max_i, bool) or not isinstance(max_i, int) \
                    or not (0 <= max_i <= MAX_ARRAY_ITEMS):
                _error(400, "unsupported_schema",
                       f"maxItems debe ser entero 0..{MAX_ARRAY_ITEMS}")
        if min_i is not None and max_i is not None and min_i > max_i:
            _error(400, "unsupported_schema",
                   "minItems no puede superar maxItems")

        tipo_items = items.get("type")
        if not isinstance(tipo_items, str):
            _error(400, "unsupported_schema", "items.type debe ser string")
        if tipo_items in TIPOS_ESCALARES:
            _validar_propiedad_escalar(items)
        elif tipo_items == "object":
            sobrantes_obj = set(items) - {"type", "properties", "required"}
            if sobrantes_obj:
                _error(400, "unsupported_schema",
                       f"keywords no permitidas en items object: "
                       f"{sobrantes_obj}")
            props_items = items.get("properties")
            if not isinstance(props_items, dict) \
                    or not (1 <= len(props_items) <= MAX_PROPIEDADES_ANIDADO):
                _error(400, "unsupported_schema",
                       f"properties de items object debe tener "
                       f"1..{MAX_PROPIEDADES_ANIDADO} propiedades")
            for d_p in props_items.values():
                _validar_propiedad_escalar(d_p)
            req_items = items.get("required", [])
            if not isinstance(req_items, list) \
                    or not all(isinstance(r, str) for r in req_items) \
                    or not set(req_items).issubset(props_items):
                _error(400, "unsupported_schema",
                       "required de items object inválido")
        else:
            _error(400, "unsupported_schema",
                   f"tipo de items de array no admitido: {tipo_items}")
        return

    if tipo == "object":
        sobrantes = set(def_prop) - {"type", "properties", "required"}
        if sobrantes:
            _error(400, "unsupported_schema",
                   f"keywords no permitidas en object anidado: {sobrantes}")
        props_anid = def_prop.get("properties")
        if not isinstance(props_anid, dict) \
                or not (1 <= len(props_anid) <= MAX_PROPIEDADES_ANIDADO):
            _error(400, "unsupported_schema",
                   f"properties de object anidado debe tener "
                   f"1..{MAX_PROPIEDADES_ANIDADO} propiedades")
        for d_p in props_anid.values():
            _validar_propiedad_escalar(d_p)
        req_anid = def_prop.get("required", [])
        if not isinstance(req_anid, list) \
                or not all(isinstance(r, str) for r in req_anid) \
                or not set(req_anid).issubset(props_anid):
            _error(400, "unsupported_schema",
                   "required de object anidado inválido")
        return

    _error(400, "unsupported_schema", f"tipo de propiedad no admitido: {tipo}")


def validar_schema(schema):
    if not isinstance(schema, dict):
        _error(400, "unsupported_schema", "schema no es un objeto")
    if set(schema) - {"type", "properties", "required"}:
        _error(400, "unsupported_schema",
               "keywords fuera del dialecto (incluido additionalProperties)")
    if schema.get("type") != "object":
        _error(400, "unsupported_schema", "sólo type object en la raíz")
    props = schema.get("properties")
    if not isinstance(props, dict) or not (1 <= len(props) <= MAX_PROPIEDADES):
        _error(400, "unsupported_schema", "properties inválido")
    for nombre, definicion in props.items():
        _validar_propiedad_v2_ext(definicion, nivel=0)
    requeridos = schema.get("required", [])
    if not isinstance(requeridos, list) \
            or not all(isinstance(r, str) for r in requeridos) \
            or not set(requeridos).issubset(props):
        _error(400, "unsupported_schema", "required inválido")


def _validar_valor_escalar(valor, def_prop, nombre, texto_raw):
    tipo = def_prop["type"]
    ok = (
        (tipo == "string" and isinstance(valor, str))
        or (tipo == "integer" and isinstance(valor, int)
            and not isinstance(valor, bool))
        or (tipo == "number" and isinstance(valor, (int, float))
            and not isinstance(valor, bool))
        or (tipo == "boolean" and isinstance(valor, bool))
    )
    if not ok:
        _error(502, "output_not_valid",
               f"tipo de '{nombre}' no satisface {tipo}",
               detail="schema_mismatch", raw_content=texto_raw)
    if "enum" in def_prop:
        if tipo == "number":
            coincide = any(
                isinstance(e, (int, float)) and not isinstance(e, bool)
                and e == valor for e in def_prop["enum"]
            )
        else:
            coincide = any(
                type(e) is type(valor) and e == valor for e in def_prop["enum"]
            )
        if not coincide:
            _error(502, "output_not_valid",
                   f"valor de '{nombre}' fuera de enum",
                   detail="schema_mismatch", raw_content=texto_raw)
    if "minimum" in def_prop:
        if valor < def_prop["minimum"]:
            _error(502, "output_not_valid",
                   f"valor de '{nombre}' menor que minimum",
                   detail="schema_mismatch", raw_content=texto_raw)
    if "maximum" in def_prop:
        if valor > def_prop["maximum"]:
            _error(502, "output_not_valid",
                   f"valor de '{nombre}' mayor que maximum",
                   detail="schema_mismatch", raw_content=texto_raw)


def _numero(valor, bajo, alto, campo):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) \
            or not (bajo <= valor <= alto):
        _error(400, "unsupported_field_value",
               f"valor fuera de rango en {campo}")


def validar_payload(payload, inspector_video=None):
    if not isinstance(payload, dict):
        _error(400, "invalid_json", "el cuerpo debe ser un objeto JSON")
    if "stream" in payload and not isinstance(payload.get("stream"), bool):
        _error(400, "unsupported_field_value",
               "stream debe ser booleano (true o false)")
    if payload.get("stream") is True \
            and payload.get("response_format") is not None:
        _error(400, "unsupported_field_value",
               "streaming no compatible con response_format json_schema")
    desconocidas = set(payload) - CLAVES_TOP
    if desconocidas:
        _error(400, "unknown_field",
               f"{len(desconocidas)} campo(s) no admitidos por el dialecto v2")
    mensajes = payload.get("messages")
    if not isinstance(mensajes, list) or not mensajes:
        _error(400, "missing_messages", "messages debe ser una lista no vacía")
    for mensaje in mensajes:
        if not isinstance(mensaje, dict) or mensaje.get("role") not in ROLES:
            _error(400, "unknown_content_type", "mensaje con role inválido")
        contenido = mensaje.get("content")
        if isinstance(contenido, str):
            continue
        if not isinstance(contenido, list):
            _error(400, "unknown_content_type", "content inválido")
        for parte in contenido:
            if not isinstance(parte, dict):
                _error(400, "unknown_content_type", "parte inválida")
            tipo = parte.get("type")
            if tipo == "text" and set(parte) == {"type", "text"} \
                    and isinstance(parte.get("text"), str):
                continue
            if tipo == "image_url" and set(parte) == {"type", "image_url"} \
                    and isinstance(parte.get("image_url"), dict) \
                    and set(parte["image_url"]) == {"url"}:
                url = parte["image_url"].get("url")
                if not isinstance(url, str):
                    _error(400, "invalid_image", "URL de imagen inválida")
                validar_imagen(url)
                continue
            if tipo == "input_audio" and set(parte) == {"type", "input_audio"} \
                    and isinstance(parte.get("input_audio"), dict) \
                    and set(parte["input_audio"]) == {"data", "format"}:
                validar_audio_entrada(parte["input_audio"])
                continue
            if tipo == "video_url" and set(parte) == {"type", "video_url"} \
                    and isinstance(parte.get("video_url"), dict) \
                    and set(parte["video_url"]) == {"url"}:
                url = parte["video_url"].get("url")
                if not isinstance(url, str):
                    _error(400, "invalid_video", "URL de video inválida")
                validar_video_entrada(url, inspector=inspector_video)
                continue
            _error(400, "unknown_content_type",
                   "parte de contenido no admitida")
    max_tokens = payload.get("max_tokens")
    if max_tokens is not None:
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) \
                or not (1 <= max_tokens <= MAX_TOKENS):
            _error(400, "unsupported_field_value", "max_tokens fuera de rango")
    if payload.get("temperature") is not None:
        _numero(payload["temperature"], 0, 2, "temperature")
    if payload.get("top_p") is not None:
        _numero(payload["top_p"], 0, 1, "top_p")
    if payload.get("model") is not None \
            and not isinstance(payload["model"], str):
        _error(400, "unsupported_field_value", "model debe ser string")
    formato = payload.get("response_format")
    if formato is not None:
        if not isinstance(formato, dict) \
                or formato.get("type") != "json_schema" \
                or not isinstance(formato.get("json_schema"), dict):
            _error(400, "unsupported_schema",
                   "sólo response_format json_schema en el dialecto v2")
        envoltorio = formato["json_schema"]
        if not isinstance(envoltorio.get("name"), str):
            _error(400, "unsupported_schema", "json_schema.name inválido")
        validar_schema(envoltorio.get("schema"))


def validar_salida(texto, schema):
    """Valida la salida del modelo contra el dialecto v2-ext (guía 06 §5)."""
    try:
        datos = json.loads(texto, parse_constant=_rechazar_constante)
    except (json.JSONDecodeError, ValueError):
        _error(502, "output_not_valid", "salida incompleta o no JSON",
               detail="incomplete_output", raw_content=texto)
    if not isinstance(datos, dict):
        _error(502, "output_not_valid", "la salida no es un objeto",
               detail="schema_mismatch", raw_content=texto)
    props = schema["properties"]
    requeridos = schema.get("required", [])
    faltan = [r for r in requeridos if r not in datos]
    sobran = [k for k in datos if k not in props]
    if faltan or sobran:
        _error(502, "output_not_valid",
               f"salida fuera del schema ({len(faltan)} faltan, "
               f"{len(sobran)} sobran)",
               detail="schema_mismatch", raw_content=texto)
    for clave, valor in datos.items():
        def_prop = props[clave]
        tipo = def_prop["type"]
        if tipo in TIPOS_ESCALARES:
            _validar_valor_escalar(valor, def_prop, clave, texto)
        elif tipo == "array":
            if not isinstance(valor, list):
                _error(502, "output_not_valid",
                       f"'{clave}' debe ser una lista",
                       detail="schema_mismatch", raw_content=texto)
            min_i = def_prop.get("minItems")
            max_i = def_prop.get("maxItems")
            limite_max = max_i if max_i is not None else MAX_ARRAY_ITEMS
            if min_i is not None and len(valor) < min_i:
                _error(502, "output_not_valid",
                       f"array '{clave}' menor que minItems",
                       detail="schema_mismatch", raw_content=texto)
            if len(valor) > limite_max:
                _error(502, "output_not_valid",
                       f"array '{clave}' supera maxItems ({limite_max})",
                       detail="schema_mismatch", raw_content=texto)
            item_def = def_prop["items"]
            item_tipo = item_def["type"]
            for idx, elem in enumerate(valor):
                if item_tipo in TIPOS_ESCALARES:
                    _validar_valor_escalar(
                        elem, item_def, f"{clave}[{idx}]", texto
                    )
                elif item_tipo == "object":
                    if not isinstance(elem, dict):
                        _error(502, "output_not_valid",
                               f"elemento {idx} de '{clave}' debe ser objeto",
                               detail="schema_mismatch", raw_content=texto)
                    obj_props = item_def["properties"]
                    obj_req = item_def.get("required", [])
                    faltan_elem = [r for r in obj_req if r not in elem]
                    sobran_elem = [k for k in elem if k not in obj_props]
                    if faltan_elem or sobran_elem:
                        _error(502, "output_not_valid",
                               f"objeto {idx} de '{clave}' fuera de schema",
                               detail="schema_mismatch", raw_content=texto)
                    for k_sub, v_sub in elem.items():
                        _validar_valor_escalar(
                            v_sub, obj_props[k_sub],
                            f"{clave}[{idx}].{k_sub}", texto
                        )
        elif tipo == "object":
            if not isinstance(valor, dict):
                _error(502, "output_not_valid",
                       f"'{clave}' debe ser un objeto",
                       detail="schema_mismatch", raw_content=texto)
            obj_props = def_prop["properties"]
            obj_req = def_prop.get("required", [])
            faltan_sub = [r for r in obj_req if r not in valor]
            sobran_sub = [k for k in valor if k not in obj_props]
            if faltan_sub or sobran_sub:
                _error(502, "output_not_valid",
                       f"objeto anidado '{clave}' fuera de schema",
                       detail="schema_mismatch", raw_content=texto)
            for k_sub, v_sub in valor.items():
                _validar_valor_escalar(
                    v_sub, obj_props[k_sub], f"{clave}.{k_sub}", texto
                )
    return "valid"
