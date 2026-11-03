#!/usr/bin/env python3
"""Servidor MCP stdio para LFM3-Omni.

Contrato: docs/contracts/mcp-tools-v1.md · Comportamiento: docs/specs/SPEC-2-mcp.md
Transporte stdio (ADR-002); delega en el motor por el CONTRATO
lfm3-omni/superficie-inferencia v1. La salida del motor es dato no
confiable (principio 7): forma cerrada validada en frontera, salida con
esquema pedido verificada contra un subconjunto declarado de JSON Schema,
y jamás se ejecuta ni se reenvía como instrucción. Stateless: no persiste
conversaciones.
"""

import base64
import binascii
import json
import sys
import urllib.error
import urllib.request

PROTO_DEFAULT = "2025-06-18"
PROTO_SOPORTADAS = ("2025-06-18", "2025-03-26")
MOTOR_URL = "http://127.0.0.1:8091"
MODELO = "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M"
INICIALIZADO = False

TOOLS = [
    {
        "name": "health",
        "description": "Estado del motor LFM3-Omni (up/down, model, port)",
        "inputSchema": {"type": "object", "properties": {},
                        "additionalProperties": False, "required": []},
    },
    {
        "name": "infer_text",
        "description": "Inferencia de texto con esquema de salida opcional",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "minLength": 1, "maxLength": 8000},
                "schema": {"type": "object"},
                "max_tokens": {"type": "integer", "minimum": 1, "maximum": 4096},
            },
            "additionalProperties": False,
            "required": ["prompt"],
        },
    },
    {
        "name": "infer_vision",
        "description": "Inferencia sobre imagen (PNG o JPEG en base64)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image_base64": {"type": "string"},
                "prompt": {"type": "string", "minLength": 1, "maxLength": 8000},
            },
            "additionalProperties": False,
            "required": ["image_base64", "prompt"],
        },
    },
]


def respond(msg_id, result=None, error=None):
    body = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        body["error"] = error
    else:
        body["result"] = result
    return json.dumps(body, ensure_ascii=False)


def _tool_result(data):
    return {
        "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
        "isError": False,
    }


def _tool_error(message):
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _http(method, path, payload=None, timeout=120):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        MOTOR_URL + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read())


def _motor_up():
    try:
        status, body = _http("GET", "/health", timeout=5)
        return status == 200 and isinstance(body, dict) and body.get("status") == "ok"
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError,
            TypeError, AttributeError):
        return False


# --- validador de esquema: subconjunto declarado, fail-closed ---

_TIPOS = {
    "object": dict, "string": str, "integer": int,
    "number": (int, float), "boolean": bool, "array": list, "null": type(None),
}
_CLAVES_SOPORTADAS = {"type", "properties", "required", "items"}


def _schema_conforme(dato, schema):
    """True si `dato` cumple el subconjunto soportado de JSON Schema.

    Un esquema con claves no soportadas lanza ValueError: fail-closed,
    preferimos rechazar a fingir validación (REQ-7).
    """
    desconocidas = set(schema) - _CLAVES_SOPORTADAS
    if desconocidas:
        raise ValueError(f"esquema con claves no soportadas: {sorted(desconocidas)}")
    tipo = schema.get("type")
    if tipo is not None:
        esperado = _TIPOS.get(tipo)
        if esperado is None:
            raise ValueError(f"tipo no soportado: {tipo}")
        if tipo == "integer" and isinstance(dato, bool):
            return False
        if not isinstance(dato, esperado):
            return False
    if "required" in schema and isinstance(dato, dict):
        for campo in schema["required"]:
            if campo not in dato:
                return False
    if "properties" in schema and isinstance(dato, dict):
        for campo, sub in schema["properties"].items():
            if campo in dato and not _schema_conforme(dato[campo], sub):
                return False
    if "items" in schema and isinstance(dato, list):
        if not all(_schema_conforme(item, schema["items"]) for item in dato):
            return False
    return True


# --- salidas del motor: forma cerrada, dato no confiable ---

def _extraer_texto(cuerpo):
    """Devuelve (contenido, usage) o lanza ValueError con detalle."""
    choices = cuerpo.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("respuesta sin choices utilizables")
    mensaje = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(mensaje, dict):
        raise ValueError("respuesta sin message utilizables")
    contenido = mensaje.get("content")
    if not isinstance(contenido, str):
        raise ValueError("content del motor no es string")
    usage = cuerpo.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("usage ausente o no es objeto")
    return contenido, usage


def handle_initialize(msg):
    global INICIALIZADO
    pedido = (msg.get("params") or {}).get("protocolVersion", PROTO_DEFAULT)
    version = pedido if pedido in PROTO_SOPORTADAS else PROTO_DEFAULT
    INICIALIZADO = True
    return {
        "protocolVersion": version,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "lfm3-omni-mcp", "version": "0.1.0"},
    }


def _exige_sesion():
    if not INICIALIZADO:
        return {"code": -32002, "message": "initialize requerido como primer método"}
    return None


def handle_tools_list(_msg):
    return {"tools": TOOLS}


def handle_health(msg):
    args = (msg.get("params") or {}).get("arguments")
    if args not in (None, {}):
        return _tool_error("arguments inválidos: health no acepta campos")
    if not _motor_up():
        return _tool_result({"state": "down", "model": MODELO, "port": 8091})
    try:
        _, cuerpo = _http("GET", "/v1/models", timeout=10)
        servido = cuerpo["data"][0]["id"]
    except (urllib.error.URLError, OSError, json.JSONDecodeError,
            KeyError, IndexError, TypeError, ValueError):
        return _tool_result({"state": "down", "model": MODELO, "port": 8091})
    # Principio 3: el modelo se evidencia contra el motor, no se asume.
    if servido != MODELO:
        return _tool_result({"state": "down", "model": MODELO, "port": 8091})
    return _tool_result({"state": "up", "model": MODELO, "port": 8091})


def _campos_extra(args, declarados):
    extra = sorted(set(args) - declarados)
    if extra:
        return f"arguments inválidos: campos no declarados en el contrato: {extra}"
    return None


def _validar_prompt(valor, campo):
    if not isinstance(valor, str) or not 1 <= len(valor) <= 8000:
        return f"arguments inválidos: {campo} debe ser string de 1..8000 caracteres"
    return None


def _delegar(payload):
    """POST al motor con clasificación de errores. Devuelve _tool_* o tupla."""
    try:
        estado, cuerpo = _http("POST", "/v1/chat/completions", payload)
    except urllib.error.HTTPError as exc:
        try:
            cuerpo_err = json.loads(exc.read())
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            cuerpo_err = {}
        err = cuerpo_err.get("error") if isinstance(cuerpo_err, dict) else None
        detalle = err.get("message") if isinstance(err, dict) else None
        if not detalle:
            detalle = err if isinstance(err, str) else str(exc)
        if exc.code == 400:
            return _tool_error(f"motor rechazó la entrada: {detalle}")
        if exc.code == 503:
            return _tool_error(f"motor cargando, reintentable: {detalle}")
        return _tool_error(f"motor respondió {exc.code}: {detalle}")
    except (urllib.error.URLError, OSError) as exc:
        return _tool_error(f"motor no disponible: {exc}")
    except (json.JSONDecodeError, ValueError) as exc:
        return _tool_error(f"salida_invalida: respuesta del motor no parseable ({exc})")
    if estado != 200:
        detalle = (cuerpo.get("error") or {}).get("message", str(estado)) \
            if isinstance(cuerpo, dict) else str(estado)
        return _tool_error(f"motor respondió {estado}: {detalle}")
    try:
        contenido, usage = _extraer_texto(cuerpo)
    except ValueError as exc:
        return _tool_error(f"salida_invalida: {exc}")
    return None, contenido, usage


def handle_infer_text(msg):
    args = (msg.get("params") or {}).get("arguments")
    if not isinstance(args, dict):
        return _tool_error("arguments inválidos: debe ser un objeto")
    fallo = _campos_extra(args, {"prompt", "schema", "max_tokens"})
    if fallo:
        return _tool_error(fallo)
    fallo = _validar_prompt(args.get("prompt"), "prompt")
    if fallo:
        return _tool_error(fallo)
    max_tokens = args.get("max_tokens", 512)
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) \
            or not 1 <= max_tokens <= 4096:
        return _tool_error("arguments inválidos: max_tokens debe ser entero 1..4096")
    schema = args.get("schema")
    if "schema" in args and not isinstance(schema, dict):
        return _tool_error("arguments inválidos: schema debe ser un objeto JSON Schema")
    try:
        if schema is not None:
            _schema_conforme({}, schema)
    except (ValueError, RecursionError) as exc:
        return _tool_error(f"arguments inválidos: {exc}")
    payload = {
        "messages": [{"role": "user", "content": args["prompt"]}],
        "max_tokens": max_tokens,
    }
    if schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "salida", "schema": schema},
        }
    resultado = _delegar(payload)
    if isinstance(resultado, dict):
        return resultado
    _, contenido, usage = resultado
    if schema is not None:
        try:
            dato = json.loads(contenido)
        except (json.JSONDecodeError, RecursionError) as exc:
            return _tool_error(f"salida_invalida: la salida no es JSON válido ({exc})")
        try:
            conforme = _schema_conforme(dato, schema)
        except (ValueError, RecursionError) as exc:
            return _tool_error(f"salida_invalida: {exc}")
        if not conforme:
            return _tool_error("salida_invalida: la salida viola el esquema pedido")
        return _tool_result({"text": contenido, "validated": True, "usage": usage})
    return _tool_result({"text": contenido, "validated": False, "usage": usage})


def _mime_de_base64(imagen):
    """Devuelve (mime, bytes) o (None, motivo). Firma por bytes, no por fe."""
    try:
        bruto = base64.b64decode(imagen, validate=True)
    except (binascii.Error, ValueError):
        return None, "arguments inválidos: image_base64 no decodifica como base64"
    if bruto.startswith(b"\x89PNG"):
        return "image/png", bruto
    if bruto.startswith(b"\xff\xd8"):
        return "image/jpeg", bruto
    return None, "arguments inválidos: formato no soportado, se requiere PNG o JPEG"


def handle_infer_vision(msg):
    args = (msg.get("params") or {}).get("arguments")
    if not isinstance(args, dict):
        return _tool_error("arguments inválidos: debe ser un objeto")
    fallo = _campos_extra(args, {"image_base64", "prompt"})
    if fallo:
        return _tool_error(fallo)
    fallo = _validar_prompt(args.get("prompt"), "prompt")
    if fallo:
        return _tool_error(fallo)
    imagen = args.get("image_base64")
    if not isinstance(imagen, str) or not imagen:
        return _tool_error("arguments inválidos: image_base64 es obligatorio (string no vacío)")
    mime, motivo = _mime_de_base64(imagen)
    if mime is None:
        return _tool_error(motivo)
    payload = {
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{imagen}"}},
            {"type": "text", "text": args["prompt"]},
        ]}],
        # Techo interno declarado en el contrato (mcp-tools v1, invariantes).
        "max_tokens": 1024,
    }
    resultado = _delegar(payload)
    if isinstance(resultado, dict):
        return resultado
    _, descripcion, usage = resultado
    return _tool_result({"description": descripcion, "usage": usage})


TOOLS_HANDLERS = {
    "health": handle_health,
    "infer_text": handle_infer_text,
    "infer_vision": handle_infer_vision,
}


def handle_tools_call(msg):
    nombre = (msg.get("params") or {}).get("name")
    handler = TOOLS_HANDLERS.get(nombre)
    if handler is None:
        return {"error": {"code": -32602, "message": f"tool no conocida: {nombre}"}}
    return handler(msg)


DESPACHO = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
    "notifications/initialized": lambda _msg: None,
}


def procesar(linea):
    try:
        msg = json.loads(linea)
    except json.JSONDecodeError as exc:
        return respond(None, error={"code": -32700, "message": f"parse error: {exc}"})
    if not isinstance(msg, dict):
        return respond(None, error={
            "code": -32600, "message": "el mensaje debe ser un objeto JSON"})
    if "id" not in msg:
        return None  # notificación JSON-RPC: sin respuesta, cualquier método
    metodo = msg.get("method", "")
    handler = DESPACHO.get(metodo)
    if handler is None:
        return respond(
            msg.get("id"),
            error={"code": -32601, "message": f"método no conocido: {metodo}"},
        )
    if metodo != "initialize":
        sesion = _exige_sesion()
        if sesion is not None:
            return respond(msg.get("id"), error=sesion)
    params = msg.get("params")
    if params is not None and not isinstance(params, dict):
        return respond(msg.get("id"), error={
            "code": -32600, "message": "params debe ser un objeto"})
    try:
        resultado = handler(msg)
    except RecursionError:
        return respond(msg.get("id"), error={
            "code": -32603, "message": "error interno: profundidad excesiva"})
    except Exception as exc:  # barrera final: el proceso MCP jamás muere por dato no confiable
        return respond(msg.get("id"), error={
            "code": -32603, "message": f"error interno: {exc}"})
    if isinstance(resultado, dict) and "error" in resultado:
        return respond(msg.get("id"), error=resultado["error"])
    return respond(msg.get("id"), result=resultado)


def main():
    for linea in sys.stdin:
        linea = linea.strip()
        if not linea:
            continue
        respuesta = procesar(linea)
        if respuesta is None:
            continue
        # backslashreplace: un surrogate malicioso no mata el bucle (dato no confiable).
        sys.stdout.buffer.write((respuesta + "\n").encode("utf-8", "backslashreplace"))
        sys.stdout.flush()


if __name__ == "__main__":
    main()
