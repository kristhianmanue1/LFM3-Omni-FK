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
import re
import struct
import zlib

DEFAULT_BACKEND = "http://127.0.0.1:8091"
DEFAULT_PORT = 8092
MAX_BODY_BYTES = 32 * 1024 * 1024
MAX_IMAGEN_BYTES = 8 * 1024 * 1024
MAX_PIXELES = 16_777_216
MAX_PROPIEDADES = 32
MAX_TOKENS = 4096
BACKEND_TIMEOUT_S = 300

CLAVES_TOP = {
    "model", "messages", "tools", "tool_choice", "temperature",
    "top_p", "max_tokens", "response_format",
}
CLAVES_NO_SOPORTADAS = {"stream"}
ROLES = {"system", "user", "assistant"}
TIPOS_SCHEMA = {"string", "integer", "number", "boolean"}
FIRMA_PNG = b"\x89PNG\r\n\x1a\n"
URL_IMAGEN_RE = re.compile(
    r"^data:image/(png|jpeg);base64,([A-Za-z0-9+/=\s]+)$")
DATA_RE = re.compile(r"^data:")

# Allowlist cerrado (SPEC-i1 §2): cualquier otra ruta es 404.
RUTAS_PERMITIDAS = (
    "POST /v1/chat/completions",
    "GET /v1/models",
    "GET /v1/capabilities",
    "GET /healthz",
)

# Capabilities declaradas por SPEC, jamás derivadas del motor y jamás
# anunciando lo no activo (SPEC-i1 §3; cambiar exige SPEC nuevo).
CAPABILITIES = {
    "entrada": ["texto", "imagen"],
    "salida": ["texto"],
    "streaming": False,
    "audio": False,
    "video": False,
    "voz": False,
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
        error = {"code": self.code, "message": self.message,
                 "request_id": request_id}
        error.update(self.extra)
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
                or url.startswith("https://"):
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


# -------------------------------------------------------------- dialecto

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
        if not isinstance(definicion, dict) or set(definicion) != {"type"}:
            _error(400, "unsupported_schema",
                   "propiedad con keywords fuera del dialecto")
        if definicion["type"] not in TIPOS_SCHEMA:
            _error(400, "unsupported_schema", "tipo de propiedad no admitido")
    requeridos = schema.get("required", [])
    if not isinstance(requeridos, list) \
            or not all(isinstance(r, str) for r in requeridos) \
            or not set(requeridos).issubset(props):
        _error(400, "unsupported_schema", "required inválido")


def _numero(valor, bajo, alto, campo):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) \
            or not (bajo <= valor <= alto):
        _error(400, "unsupported_field_value",
               f"valor fuera de rango en {campo}")


def validar_payload(payload):
    if not isinstance(payload, dict):
        _error(400, "invalid_json", "el cuerpo debe ser un objeto JSON")
    if "stream" in payload:
        _error(400, "unsupported_field_value",
               "streaming no soportado en el gateway I0/I1")
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
            _error(400, "unknown_content_type", "parte de contenido no admitida")
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
    """Valida la salida del modelo contra el dialecto (guía 06 §5)."""
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
        tipo = props[clave]["type"]
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
                   f"tipo de '{clave}' no satisface {tipo}",
                   detail="schema_mismatch", raw_content=texto)
    return "valid"
