#!/usr/bin/env python3
"""Cliente de referencia del gateway I1 (SPEC-i1 §6) — stdlib-only.

Demo I1-U: completa texto, JSON e imagen contra el gateway con motor
vivo, consulta capabilities/modelos y muestra un rechazo controlado.
Exit 0 sólo si toda la demo pasa.

Uso: python3.12 examples/cliente_i1.py [puerto_gateway]
"""

import base64
import json
import struct
import sys
import urllib.error
import urllib.request
from pathlib import Path
import zlib

PUERTO = int(sys.argv[1]) if len(sys.argv) > 1 else 8092
BASE = f"http://127.0.0.1:{PUERTO}"
RESULTADOS = []


def png_rojo():
    ancho = alto = 8
    bruto = b"".join(b"\x00" + b"\xff\x00\x00" * ancho for _ in range(alto))

    def trozo(tipo, datos):
        cuerpo = tipo + datos
        return struct.pack(">I", len(datos)) + cuerpo + struct.pack(
            ">I", zlib.crc32(cuerpo))

    return (
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
        + trozo(b"IDAT", zlib.compress(bruto))
        + trozo(b"IEND", b"")
    )


def _get(ruta):
    with urllib.request.urlopen(BASE + ruta, timeout=15) as resp:
        return resp.status, json.loads(resp.read())


def _post(payload):
    req = urllib.request.Request(
        BASE + "/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def salud():
    return _get("/healthz")


def capabilities():
    return _get("/v1/capabilities")


def modelos():
    return _get("/v1/models")


def chat_texto(mensaje, max_tokens=24):
    return _post({"messages": [{"role": "user", "content": mensaje}],
                  "max_tokens": max_tokens})


def chat_schema(mensaje, schema, max_tokens=48):
    return _post({"messages": [{"role": "user", "content": mensaje}],
                  "max_tokens": max_tokens,
                  "response_format": {"type": "json_schema",
                                      "json_schema": {"name": "registro",
                                                      "schema": schema}}})


def chat_imagen(url_png, pregunta, max_tokens=16):
    url = "data:image/png;base64," + base64.b64encode(url_png).decode()
    return _post({"messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": url}},
        {"type": "text", "text": pregunta}]}],
        "max_tokens": max_tokens})


def chat_transcripcion(wav, max_tokens=200):
    """Transcripción vía input_audio (SPEC-i1-va): WAV en bytes."""
    return _post({"messages": [{"role": "user", "content": [
        {"type": "input_audio",
         "input_audio": {"data": base64.b64encode(wav).decode(),
                         "format": "wav"}},
        {"type": "text",
         "text": "Transcribe exactamente el audio, sin comentarios."}]}],
        "max_tokens": max_tokens})


def caso(nombre, condicion, detalle=""):
    RESULTADOS.append(condicion)
    marca = "OK " if condicion else "FAIL"
    print(f"CLIENTE {marca} {nombre}" + (f" — {detalle}" if detalle else ""))


def main():
    try:
        _demo()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"CLIENTE FAIL gateway inalcanzable en {BASE} ({exc})")
        sys.exit(1)


def _demo():
    estado, cuerpo = salud()
    caso("salud", estado == 200 and cuerpo.get("status") == "ok",
         f"estado={estado}")

    estado, caps = capabilities()
    caso("capabilities", estado == 200 and caps.get("voz") is False
         and "imagen" in caps.get("entrada", []), f"estado={estado}")

    estado, cuerpo = modelos()
    ids = [m["id"] for m in cuerpo.get("data", [])]
    caso("modelos", estado == 200 and len(ids) == 1, f"ids={ids}")

    estado, cuerpo = chat_texto("Completa: 1, 2, 3, 4, 5…")
    texto = cuerpo.get("choices", [{}])[0].get("message", {}).get("content", "")
    caso("chat_texto", estado == 200 and bool(texto), f"estado={estado}")

    schema = {"type": "object",
              "properties": {"nombre": {"type": "string"},
                             "edad": {"type": "integer"}},
              "required": ["nombre", "edad"]}
    estado, cuerpo = chat_schema("Registra a Ana de 34 años según el esquema.",
                                 schema)
    try:
        datos = json.loads(cuerpo["choices"][0]["message"]["content"])
    except (json.JSONDecodeError, KeyError, TypeError):
        datos = None
    caso("chat_schema", estado == 200 and isinstance(datos, dict)
         and isinstance(datos.get("edad"), int), f"estado={estado} datos={datos}")

    estado, cuerpo = chat_imagen(png_rojo(),
                                 "¿De qué color es la imagen? Una palabra.")
    texto = cuerpo.get("choices", [{}])[0].get("message", {}).get("content", "").lower()
    caso("chat_imagen", estado == 200 and ("rojo" in texto or "red" in texto),
         f"estado={estado}")

    # transcripción (SPEC-i1-va) con un caso del corpus sintético
    wav = (Path(__file__).resolve().parent.parent
           / "tests/medios-binarios/corpus-01.wav").read_bytes()
    estado, cuerpo = chat_transcripcion(wav)
    texto = cuerpo.get("choices", [{}])[0].get("message", {}).get("content", "")
    caso("chat_transcripcion", estado == 200 and "hola" in texto.lower(),
         f"estado={estado} texto={texto!r}")

    # rechazo controlado con código estable, sin tocar el motor
    estado, cuerpo = _post({"messages": [{"role": "user", "content": "h"}],
                            "seed": 7})
    caso("rechazo_controlado", estado == 400
         and cuerpo.get("error", {}).get("code") == "unknown_field",
         f"estado={estado}")

    # WAV corrupto: rechazo de frontera antes del motor (SPEC-i1-va §2)
    estado, cuerpo = _post({"messages": [{"role": "user", "content": [
        {"type": "input_audio",
         "input_audio": {"data": base64.b64encode(b"RIFF roto").decode(),
                         "format": "wav"}},
        {"type": "text", "text": "x"}]}]})
    caso("rechazo_audio_roto", estado == 400
         and cuerpo.get("error", {}).get("code") == "invalid_audio",
         f"estado={estado}")

    fallos = RESULTADOS.count(False)
    print(f"CLIENTE resumen: {len(RESULTADOS) - fallos} OK, {fallos} FAIL")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
