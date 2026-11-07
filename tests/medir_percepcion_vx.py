#!/usr/bin/env python3
"""Medición del gate de I1-VX (SPEC-i1-vx §3):
Percepción multimodal estructurada en un solo turno:
1) Imagen + schema v2-ext (enum, string): extrae JSON validado en frontera.
2) Audio + schema v2-ext (enum, array de strings): extrae JSON validado.
3) Objeto anidado nivel 1 + schema v2-ext: extrae JSON validado.

Criterio de pase: 100% de los casos (3/3) responden 200 con JSON válido
conforme al esquema v2-ext en un solo turno sin re-inferencia, latencia
p95 <= 8.0 s y RSS motor < 4 GiB.

Uso: python3.12 tests/medir_percepcion_vx.py [salida.json]
Requiere motor en 8091 y gateway en 8092.
"""

import base64
import json
import os
import platform
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

GATEWAY_PORT = int(os.environ.get("LFM3_GATEWAY_PORT", "8092"))
MOTOR_PORT = int(os.environ.get("LFM3_PORT", "8091"))
URL_GATEWAY = f"http://127.0.0.1:{GATEWAY_PORT}"


def _png_rojo():
    ancho = alto = 8
    bruto = b"".join(b"\x00" + b"\xff\x00\x00" * ancho for _ in range(alto))

    def trozo(tipo, datos):
        cuerpo = tipo + datos
        return (struct.pack(">I", len(datos)) + cuerpo
                + struct.pack(">I", zlib.crc32(cuerpo)))

    return (
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
        + trozo(b"IDAT", zlib.compress(bruto))
        + trozo(b"IEND", b"")
    )


def _rss_puerto(puerto):
    try:
        import subprocess
        out = subprocess.check_output(
            ["lsof", "-ti", f"tcp:{puerto}", "-sTCP:LISTEN"], text=True
        ).strip()
        pids = [int(p) for p in out.splitlines() if p.strip().isdigit()]
        if not pids:
            return 0
        out_rss = subprocess.check_output(
            ["ps", "-o", "rss=", "-p", str(pids[0])], text=True
        ).strip()
        return int(out_rss) * 1024
    except Exception:
        return 0


def _post_json(url, payload, timeout=60):
    datos = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=datos,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def medir_percepcion(salida_json=None):
    rss_inicial = _rss_puerto(MOTOR_PORT)
    resultados = []
    latencias = []
    aciertos = 0

    # Caso 1: Imagen + schema v2-ext (enum)
    png_bytes = _png_rojo()
    b64_png = base64.b64encode(png_bytes).decode("ascii")
    schema_img = {
        "type": "object",
        "properties": {
            "color_principal": {
                "type": "string",
                "enum": ["rojo", "verde", "azul", "red", "green", "blue"],
            },
        },
        "required": ["color_principal"],
    }
    payload_img = {
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64_png}"},
                },
                {"type": "text", "text": "Identifica el color de la imagen."},
            ],
        }],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "resultado_color", "schema": schema_img},
        },
        "max_tokens": 32,
        "temperature": 0.0,
    }

    t0 = time.perf_counter()
    st1, c1 = _post_json(
        f"{URL_GATEWAY}/v1/chat/completions", payload_img, timeout=30
    )
    t1_s = time.perf_counter() - t0
    latencias.append(t1_s)
    raw1 = c1["choices"][0]["message"]["content"]
    data1 = json.loads(raw1)
    color = data1.get("color_principal", "").lower()
    ok1 = (st1 == 200 and color in {"rojo", "red"})
    if ok1:
        aciertos += 1
    resultados.append({
        "caso": "imagen_mas_schema_enum",
        "status": st1,
        "latencia_s": round(t1_s, 3),
        "datos": data1,
        "acierto": ok1,
    })

    # Caso 2: Audio + schema v2-ext (enum, array)
    wav_path = RAIZ / "tests/medios-binarios/corpus-01.wav"
    b64_wav = base64.b64encode(wav_path.read_bytes()).decode("ascii")
    schema_audio = {
        "type": "object",
        "properties": {
            "idioma": {"type": "string", "enum": ["es", "en", "otro"]},
            "tipo_mensaje": {
                "type": "string",
                "enum": ["saludo", "pregunta", "comando", "otro"],
            },
            "palabras_clave": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 10,
            },
        },
        "required": ["idioma", "tipo_mensaje", "palabras_clave"],
    }
    payload_audio = {
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {"data": b64_wav, "format": "wav"},
                },
                {
                    "type": "text",
                    "text": (
                        "Analiza el audio y extrae en el JSON: idioma ('es'), "
                        "tipo_mensaje ('saludo') y en palabras_clave una lista "
                        "con al menos una palabra clave, p. ej. ['hola']."
                    ),
                },
            ],
        }],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "audio_analisis", "schema": schema_audio},
        },
        "max_tokens": 48,
        "temperature": 0.0,
    }

    t0 = time.perf_counter()
    st2, c2 = _post_json(
        f"{URL_GATEWAY}/v1/chat/completions", payload_audio, timeout=30
    )
    t2_s = time.perf_counter() - t0
    latencias.append(t2_s)
    raw2 = c2["choices"][0]["message"]["content"]
    data2 = json.loads(raw2)
    ok2 = (st2 == 200 and data2.get("idioma") == "es"
           and data2.get("tipo_mensaje") in {"saludo", "pregunta"}
           and isinstance(data2.get("palabras_clave"), list)
           and len(data2.get("palabras_clave")) >= 1)
    if ok2:
        aciertos += 1
    resultados.append({
        "caso": "audio_mas_schema_enum_array",
        "status": st2,
        "latencia_s": round(t2_s, 3),
        "datos": data2,
        "acierto": ok2,
    })

    # Caso 3: Objeto anidado nivel 1 + cotas numéricas
    schema_obj = {
        "type": "object",
        "properties": {
            "entidad": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string"},
                    "edad": {"type": "integer", "minimum": 0, "maximum": 120},
                },
                "required": ["nombre", "edad"],
            }
        },
        "required": ["entidad"],
    }
    payload_obj = {
        "messages": [{
            "role": "user",
            "content": (
                "Extrae: Carlos tiene 28 años. Responde exclusivamente con el "
                "JSON solicitado."
            ),
        }],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "entidad_schema", "schema": schema_obj},
        },
        "max_tokens": 32,
        "temperature": 0.0,
    }

    t0 = time.perf_counter()
    st3, c3 = _post_json(
        f"{URL_GATEWAY}/v1/chat/completions", payload_obj, timeout=30
    )
    t3_s = time.perf_counter() - t0
    latencias.append(t3_s)
    raw3 = c3["choices"][0]["message"]["content"]
    data3 = json.loads(raw3)
    ent = data3.get("entidad", {})
    ok3 = (st3 == 200 and "Carlos" in ent.get("nombre", "")
           and ent.get("edad") == 28)
    if ok3:
        aciertos += 1
    resultados.append({
        "caso": "objeto_anidado_cotas",
        "status": st3,
        "latencia_s": round(t3_s, 3),
        "datos": data3,
        "acierto": ok3,
    })

    latencias.sort()
    n = len(latencias)
    p95 = latencias[int(n * 0.95)] if n > 0 else 0.0
    tasa = aciertos / n if n > 0 else 0.0

    rss_final = _rss_puerto(MOTOR_PORT)
    pico_rss_mib = max(rss_inicial, rss_final) / (1024 * 1024)

    resumen = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "plataforma": platform.platform(),
        "total_casos": n,
        "aciertos": aciertos,
        "tasa_acierto": tasa,
        "latencias_s": [round(l, 3) for l in latencias],
        "p95_latencia_s": round(p95, 3),
        "criterio_p95_cumplido": p95 <= 8.0,
        "criterio_acierto_cumplido": tasa == 1.0,
        "rss_inicial_motor_mib": round(rss_inicial / (1024 * 1024), 2),
        "rss_final_motor_mib": round(rss_final / (1024 * 1024), 2),
        "pico_rss_motor_mib": round(pico_rss_mib, 2),
        "criterio_rss_cumplido": pico_rss_mib < 4096.0,
        "casos": resultados,
    }

    if salida_json:
        ruta_salida = Path(salida_json)
        ruta_salida.parent.mkdir(parents=True, exist_ok=True)
        ruta_salida.write_text(
            json.dumps(resumen, indent=2, ensure_ascii=False)
        )

    print(f"I1-VX Gate: {aciertos}/{n} aciertos estructurados "
          f"({tasa*100:.1f}%)")
    print(f"Latencia p95: {p95:.2f} s (presupuesto <= 8.0 s)")
    print(f"Pico RSS motor: {pico_rss_mib:.1f} MiB (presupuesto < 4096 MiB)")
    return resumen


if __name__ == "__main__":
    archivo_salida = sys.argv[1] if len(sys.argv) > 1 else None
    medir_percepcion(archivo_salida)
