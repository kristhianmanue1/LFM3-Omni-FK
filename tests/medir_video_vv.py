#!/usr/bin/env python3
"""Medición del gate de I1-VV (SPEC-i1-vv §3):
1) Video corto sobre 3 secuencias temporales sintéticas fijadas en el corpus:
   POST /v1/chat/completions en el gateway (8092) con video_url en data URI.
   Criterio de pase: 100% de los casos responden 200, detectan los dos colores
   en el orden temporal correcto (esperado_primero antes de esperado_despues),
   y latencia p95 <= 8.0 s.
2) RSS de llama-server (8091) tras la inferencia de video < 4 GiB (REQ-5).

Uso: python3.12 tests/medir_video_vv.py [salida.json]
Requiere motor en 8091 y gateway en 8092 (LFM3_GATEWAY_PORT).
"""

import base64
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

GATEWAY_PORT = int(os.environ.get("LFM3_GATEWAY_PORT", "8092"))
MOTOR_PORT = int(os.environ.get("LFM3_PORT", "8091"))
URL_GATEWAY = f"http://127.0.0.1:{GATEWAY_PORT}"
URL_MOTOR = f"http://127.0.0.1:{MOTOR_PORT}"

SINONIMOS_COLOR = {
    "red": ["red", "rojo"],
    "blue": ["blue", "azul"],
    "green": ["green", "verde"],
    "yellow": ["yellow", "amarillo"],
    "white": ["white", "blanco"],
    "black": ["black", "negro"],
}


def _encontrar_posicion_color(texto, color_en):
    sinonimos = SINONIMOS_COLOR.get(color_en, [color_en])
    posiciones = [texto.find(s) for s in sinonimos if texto.find(s) != -1]
    return min(posiciones) if posiciones else -1


def _rss_pid(pid):
    try:
        out = subprocess.check_output(
            ["ps", "-o", "rss=", "-p", str(pid)], text=True
        ).strip()
        return int(out) * 1024
    except Exception:
        return 0


def _obtener_pid_puerto(puerto):
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", f"tcp:{puerto}", "-sTCP:LISTEN"], text=True
        ).strip()
        pids = [int(p) for p in out.splitlines() if p.strip().isdigit()]
        return pids[0] if pids else None
    except Exception:
        return None


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


def medir_video(salida_json=None):
    pid_motor = _obtener_pid_puerto(MOTOR_PORT)
    rss_inicial_motor = _rss_pid(pid_motor) if pid_motor else 0

    ruta_corpus = RAIZ / "tests/corpus_vv.json"
    with open(ruta_corpus, "r", encoding="utf-8") as f:
        corpus = json.load(f)

    # Verificar capabilities del gateway
    req_caps = urllib.request.Request(f"{URL_GATEWAY}/v1/capabilities")
    with urllib.request.urlopen(req_caps, timeout=5) as resp:
        caps = json.loads(resp.read().decode("utf-8"))
    assert caps.get("video") is True, "El gateway no anuncia video: true"

    resultados = []
    latencias = []
    aciertos_temporales = 0

    for caso in corpus["casos"]:
        cid = caso["id"]
        ruta_mp4 = RAIZ / "tests" / caso["archivo"]
        bytes_mp4 = ruta_mp4.read_bytes()

        # Comprobar hash del corpus
        sha_calculado = hashlib.sha256(bytes_mp4).hexdigest()
        assert sha_calculado == caso["sha256"], (
            f"Hash corrupto en {caso['archivo']}: {sha_calculado} vs "
            f"{caso['sha256']}"
        )

        b64_video = base64.b64encode(bytes_mp4).decode("ascii")
        data_uri = f"data:video/mp4;base64,{b64_video}"

        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "video_url",
                            "video_url": {"url": data_uri},
                        },
                        {
                            "type": "text",
                            "text": caso.get(
                                "pregunta",
                                "¿Qué color aparece primero en el video y qué "
                                "color aparece después? Responde brevemente."
                            ),
                        },
                    ],
                }
            ],
            "max_tokens": 64,
            "temperature": 0.0,
        }

        t0 = time.perf_counter()
        st, cuerpo = _post_json(
            f"{URL_GATEWAY}/v1/chat/completions", payload, timeout=30
        )
        t_ms = (time.perf_counter() - t0) * 1000.0
        latencias.append(t_ms / 1000.0)

        assert st == 200, f"Error HTTP {st}: {cuerpo}"
        texto_resp = cuerpo["choices"][0]["message"]["content"].lower()

        esperado_1 = caso["esperado_primero"].lower()
        esperado_2 = caso["esperado_despues"].lower()

        idx_1 = _encontrar_posicion_color(texto_resp, esperado_1)
        idx_2 = _encontrar_posicion_color(texto_resp, esperado_2)

        orden_correcto = (idx_1 != -1 and idx_2 != -1 and idx_1 < idx_2)
        if orden_correcto:
            aciertos_temporales += 1

        resultados.append({
            "id": cid,
            "archivo": caso["archivo"],
            "esperado_primero": esperado_1,
            "esperado_despues": esperado_2,
            "texto_respuesta": cuerpo["choices"][0]["message"]["content"],
            "indice_primero": idx_1,
            "indice_despues": idx_2,
            "orden_correcto": orden_correcto,
            "latencia_ms": round(t_ms, 2),
            "usage": cuerpo.get("usage", {}),
        })

    latencias.sort()
    n = len(latencias)
    p95 = latencias[int(n * 0.95)] if n > 0 else 0.0
    tasa_acierto = aciertos_temporales / n if n > 0 else 0.0

    rss_final_motor = _rss_pid(pid_motor) if pid_motor else 0
    pico_rss_motor_mib = max(rss_inicial_motor, rss_final_motor) / (1024 * 1024)

    resumen = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "plataforma": platform.platform(),
        "total_casos": n,
        "aciertos_temporales": aciertos_temporales,
        "tasa_acierto": tasa_acierto,
        "latencias_s": [round(l, 3) for l in latencias],
        "p95_latencia_s": round(p95, 3),
        "criterio_p95_cumplido": p95 <= 8.0,
        "criterio_acierto_cumplido": tasa_acierto == 1.0,
        "rss_inicial_motor_mib": round(rss_inicial_motor / (1024 * 1024), 2),
        "rss_final_motor_mib": round(rss_final_motor / (1024 * 1024), 2),
        "pico_rss_motor_mib": round(pico_rss_motor_mib, 2),
        "criterio_rss_cumplido": pico_rss_motor_mib < 4096.0,
        "casos": resultados,
    }

    if salida_json:
        ruta_salida = Path(salida_json)
        ruta_salida.parent.mkdir(parents=True, exist_ok=True)
        ruta_salida.write_text(
            json.dumps(resumen, indent=2, ensure_ascii=False)
        )

    print(f"I1-VV Gate: {aciertos_temporales}/{n} aciertos temporales "
          f"({tasa_acierto*100:.1f}%)")
    print(f"Latencia p95: {p95:.2f} s (presupuesto <= 8.0 s)")
    print(f"Pico RSS motor: {pico_rss_motor_mib:.1f} MiB "
          "(presupuesto < 4096 MiB)")
    return resumen


if __name__ == "__main__":
    archivo_salida = sys.argv[1] if len(sys.argv) > 1 else None
    medir_video(archivo_salida)
