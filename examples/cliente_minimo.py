#!/usr/bin/env python3
"""Cliente mínimo del CONTRATO lfm3-omni/superficie-inferencia v1.

Tres verificaciones contra el motor vivo, en este orden:
1. descubre el modelo servido (GET /v1/models);
2. completa texto forzado a esquema JSON (response_format);
3. completa con imagen (PNG rojo sintético de procedencia registrada).

Salida del modelo = dato no confiable: el paso 2 valida en frontera.
Uso: python3 examples/cliente_minimo.py
"""

import base64
import json
import struct
import sys
import urllib.request
import zlib

BASE = "http://127.0.0.1:8091"


def post(ruta, payload):
    req = urllib.request.Request(
        BASE + ruta,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def png_rojo():
    ancho = alto = 8
    bruto = b"".join(b"\x00" + b"\xff\x00\x00" * ancho for _ in range(alto))

    def trozo(tipo, datos):
        cuerpo = tipo + datos
        return struct.pack(">I", len(datos)) + cuerpo + struct.pack(">I", zlib.crc32(cuerpo))

    return base64.b64encode(
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
        + trozo(b"IDAT", zlib.compress(bruto))
        + trozo(b"IEND", b"")
    ).decode()


def main():
    with urllib.request.urlopen(BASE + "/v1/models", timeout=5) as resp:
        modelos = json.loads(resp.read())
    print("1. modelos servidos:", [m["id"] for m in modelos["data"]])

    registro = post("/v1/chat/completions", {
        "messages": [{"role": "user", "content": "Registra a Ana de 34 años según el esquema."}],
        "max_tokens": 48,
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "registro",
            "schema": {"type": "object", "properties": {
                "nombre": {"type": "string"}, "edad": {"type": "integer"}},
                "required": ["nombre", "edad"]}},
    }})
    texto = registro["choices"][0]["message"]["content"]
    print("2. texto con esquema:", texto.strip(), "-> parsea:", bool(json.loads(texto)))

    vision = post("/v1/chat/completions", {
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + png_rojo()}},
            {"type": "text", "text": "¿De qué color es esta imagen? Responde con una sola palabra."}]}],
        "max_tokens": 32,
    })
    print("3. visión:", vision["choices"][0]["message"]["content"].strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
