"""Describe con voz en español lo que ve la cámara (loopback, exploratorio).

Patrón probado en el ajuste PLAN LFM3-2 (percepción visual, perfil D sin
actuadores): una foto con ffmpeg/avfoundation, descripción por visión del
motor 8091 (image_url data URI) y voz con llama-tts --tts-lang es.
Usa cámara real: sólo con consentimiento del Operador (D-09). La foto y
el audio viven en un directorio temporal borrado al salir. La descripción
es dato no confiable: se reproduce y se imprime, nunca se actúa sobre ella.

Uso: LFM3_CONSENTIMIENTO_D09=si python3.12 examples/describir_camara.py [--camara 0]
"""
import sys

if sys.version_info < (3, 12):
    sys.exit("BLOQ: se requiere Python 3.12 o superior")

import argparse
import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request

BASE = "http://127.0.0.1:8091"
SNAP = os.path.expanduser("~/.cache/huggingface/hub/models--LiquidAI--"
                          "LFM3-Omni-2B-GGUF/snapshots/d508b88f08a5b4286f2d2805a6a8d69a0ff44c72")
SISTEMA = ("Describe en español lo que ves en la imagen, en dos o tres frases "
           "cortas y naturales, sin listas. Si no estás seguro de algo, dilo.")


MAX_TEXTO_TTS = 600


def texto_seguro(texto):
    """Salida del modelo = dato no confiable (AGENTS, 06 §5): esquema cerrado
    mínimo antes de reenviarla a llama-tts (ADR-007): sin caracteres de
    control y con longitud acotada."""
    limpio = "".join(c for c in texto if c.isprintable() or c == " ").strip()
    # N-2: vacío o sólo control -> mensaje claro, no un fallo mudo de llama-tts.
    return limpio[:MAX_TEXTO_TTS] or "Sin respuesta del modelo."


def exigir_consentimiento(dispositivo):
    """D-09 pendiente: micrófono/cámara reales sólo con consentimiento
    explícito del Operador en esta ejecución."""
    if os.environ.get("LFM3_CONSENTIMIENTO_D09") != "si":
        sys.exit(f"BLOQ: usa {dispositivo} real; exporta "
                 "LFM3_CONSENTIMIENTO_D09=si para confirmar consentimiento")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camara", default="0", help="índice avfoundation de video")
    a = ap.parse_args()
    exigir_consentimiento("la cámara")
    tmp = tempfile.mkdtemp(prefix="lfm3-cam-")
    try:
        foto, voz = os.path.join(tmp, "foto.jpg"), os.path.join(tmp, "voz.wav")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "avfoundation", "-framerate", "30",
                        "-video_size", "1280x720", "-pixel_format", "nv12",
                        "-i", f"{a.camara}:none", "-frames:v", "1",
                        "-vf", r"select=gte(n\,15),scale=640:-2", "-q:v", "4",
                        foto], check=True, timeout=30)
        t0 = time.time()
        b = base64.b64encode(open(foto, "rb").read()).decode()
        cuerpo = {"messages": [
            {"role": "system", "content": SISTEMA},
            {"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": "data:image/jpeg;base64," + b}},
                {"type": "text", "text": "¿Qué ves?"}]}], "max_tokens": 120}
        req = urllib.request.Request(BASE + "/v1/chat/completions",
                                     data=json.dumps(cuerpo).encode(),
                                     headers={"Content-Type": "application/json"})
        d = json.load(urllib.request.urlopen(req, timeout=120))
        texto = d["choices"][0]["message"]["content"].strip()
        print(f"descripción [{time.time() - t0:.1f} s]: {texto}")
        # Texto por archivo 0600 en el directorio temporal (ADR-007).
        prompt = os.path.join(tmp, "prompt.txt")
        fd = os.open(prompt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto_seguro(texto))
        subprocess.run(["llama-tts", "-m", SNAP + "/LFM3-Omni-2B-Q4_K_M.gguf",
                        "-mm", SNAP + "/mmproj-LFM3-Omni-2B-Q4_0.gguf",
                        "--tts-lang", "es", "-f", prompt, "-o", voz],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=True, timeout=120)
        print(f"voz lista [{time.time() - t0:.1f} s]")
        subprocess.run(["afplay", voz])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
