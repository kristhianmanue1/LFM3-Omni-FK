#!/usr/bin/env python3
"""Demo I0-U contra el adaptador v2 (SPEC I0): texto, estructura e
imagen con errores controlados, desde un consumidor real HTTP. Imprime
una línea DEMO por caso y exit 0 sólo si todos pasan.

Uso (con motor + adaptador arriba):
  python3 examples/demo_i0.py [puerto_adaptador]
"""

import base64
import json
import struct
import sys
import urllib.error
import urllib.request
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


def post(payload, ruta="/v1/chat/completions", crudo=None):
    data = crudo if crudo is not None else json.dumps(payload).encode()
    req = urllib.request.Request(BASE + ruta, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def caso(nombre, condicion, detalle=""):
    RESULTADOS.append(condicion)
    marca = "OK " if condicion else "FAIL"
    print(f"DEMO {marca} {nombre}" + (f" — {detalle}" if detalle else ""))


def main():
    # 1. texto passthrough
    estado, cuerpo = post({"messages": [{"role": "user",
                                         "content": "Completa: 1, 2, 3, 4, 5…"}],
                           "max_tokens": 24})
    texto = cuerpo.get("choices", [{}])[0].get("message", {}).get("content", "")
    caso("texto_passthrough", estado == 200 and bool(texto),
         f"estado={estado}")

    # 2. salida estructurada válida
    schema = {"type": "object",
              "properties": {"nombre": {"type": "string"},
                             "edad": {"type": "integer"}},
              "required": ["nombre", "edad"]}
    estado, cuerpo = post({"messages": [{"role": "user", "content":
                                         "Registra a Ana de 34 años según el esquema."}],
                           "max_tokens": 48,
                           "response_format": {"type": "json_schema",
                                               "json_schema": {"name": "registro",
                                                               "schema": schema}}})
    datos = None
    try:
        datos = json.loads(cuerpo["choices"][0]["message"]["content"])
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    caso("estructura_valida", estado == 200 and isinstance(datos, dict)
         and isinstance(datos.get("edad"), int), f"estado={estado} datos={datos}")

    # 3. imagen válida
    url = "data:image/png;base64," + base64.b64encode(png_rojo()).decode()
    estado, cuerpo = post({"messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": url}},
        {"type": "text", "text": "¿De qué color es la imagen? Una palabra."}]}],
        "max_tokens": 16})
    texto = cuerpo.get("choices", [{}])[0].get("message", {}).get("content", "").lower()
    caso("imagen_valida", estado == 200 and ("rojo" in texto or "red" in texto),
         f"estado={estado}")

    # 4. error controlado: campo desconocido (antes del motor)
    estado, cuerpo = post({"messages": [{"role": "user", "content": "h"}],
                           "seed": 7})
    caso("error_campo_desconocido", estado == 400
         and cuerpo.get("error", {}).get("code") == "unknown_field",
         f"estado={estado}")

    # 5. error controlado: imagen truncada (antes del motor)
    truncado = png_rojo()[:-12]
    url = "data:image/png;base64," + base64.b64encode(truncado).decode()
    estado, cuerpo = post({"messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": url}},
        {"type": "text", "text": "desc"}]}]})
    caso("error_imagen_truncada", estado == 400
         and cuerpo.get("error", {}).get("code") == "invalid_image",
         f"estado={estado}")

    # 6. error controlado: schema anidado
    schema_malo = {"type": "object", "properties": {"a": {"type": "object"}}}
    estado, cuerpo = post({"messages": [{"role": "user", "content": "h"}],
                           "response_format": {"type": "json_schema",
                                               "json_schema": {"name": "x",
                                                               "schema": schema_malo}}})
    caso("error_schema_anidado", estado == 400
         and cuerpo.get("error", {}).get("code") == "unsupported_schema",
         f"estado={estado}")

    # 7. healthz del adaptador
    try:
        with urllib.request.urlopen(BASE + "/healthz", timeout=5) as resp:
            ok = resp.status == 200
    except Exception:
        ok = False
    caso("healthz", ok)

    fallos = RESULTADOS.count(False)
    print(f"DEMO resumen: {len(RESULTADOS) - fallos} OK, {fallos} FAIL")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
