"""Conversación de voz híbrida — arquitectura ADR-007 con voz estable.

Micro (ffmpeg avfoundation) -> ASR (/v1/audio/transcriptions, motor
8091) -> chat (/v1/chat/completions, greedy por runbook) ->
llama-tts --tts-lang es --tts-voice <voz> -> afplay.

Por qué híbrida y no /v1/realtime (mediciones 2026-11-10, expediente
motor-2-31689): el audio de realtime es continuación de conversación —
sigue el registro del interlocutor y deriva en sesiones largas
(123->224 Hz reproducidos; 2/4 turnos femeninos con micrófono real) —
y por tanto NO puede garantizar voz fija. Esta vía sostiene el registro
elegido 6/6 turnos (masculina 130-156 Hz) al costo de recargar el
modelo por síntesis (~2-5 s por turno).

Uso: python3.12 examples/conversacion_voz_hibrida.py [--voz male|female]
Termina la conversación diciendo «adiós». Requiere motor vivo en 8091
(run/serve.sh), ffmpeg/llama-tts del inventario ADR-006 §4 y
consentimiento D-09 del Operador por ejecución (micrófono real).
"""

import argparse
import json
import math
import os
import shutil
import statistics
import struct
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

PUERTO = 8091
CHUNK = 3200            # 100 ms a 16 kHz s16 mono
MAX_TURNOS = 6
MAX_CAPTURA_S = 10.0
SILENIO_PARA_CORTE = 14  # ~1.4 s de silencio cierra el turno
MODELO_ID = "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M"
REVISION_ADR001 = "d508b88f08a5b4286f2d2805a6a8d69a0ff44c72"
SNAP = (Path.home() / ".cache" / "huggingface" / "hub"
        / "models--LiquidAI--LFM3-Omni-2B-GGUF" / "snapshots"
        / REVISION_ADR001)
MENSAJES = [{"role": "system", "content":
             "Eres la voz local de Kris. Conversación en español, breve "
             "y natural, una o dos frases."}]


def rms(buf):
    n = len(buf) // 2
    if not n:
        return 0
    vals = struct.unpack(f"<{n}h", buf)
    return math.sqrt(sum(v * v for v in vals) / n)


def f0_mediana(ruta):
    """F0 por autocorrelación (60-350 Hz); None si no hay tramas."""
    w = wave.open(ruta)
    sr = w.getframerate()
    n = w.getnframes()
    x = struct.unpack(f"<{n}h", w.readframes(n))
    w.close()
    tam = int(sr * 0.04)
    energias = [sum(v*v for v in x[i:i+tam])
                for i in range(0, n - tam, tam)]
    techo = max(energias) if energias else 0
    f0s = []
    for idx, e in enumerate(energias):
        if e < techo * 0.10:
            continue
        fr = x[idx*tam:(idx+1)*tam]
        mejor, mejor_corr = 0, 0
        for lag in range(68, 401):
            s = 0
            for j in range(0, tam - lag, 2):
                s += fr[j] * fr[j+lag]
            if s > mejor_corr:
                mejor_corr, mejor = s, lag
        if mejor:
            f0s.append(sr / mejor)
    return round(statistics.median(f0s), 1) if f0s else None


def capturar(num):
    mic = subprocess.Popen(
        ["ffmpeg", "-nostdin", "-f", "avfoundation", "-i", ":0",
         "-f", "s16le", "-ar", "16000", "-ac", "1", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    piso, muestras, habla, silencio = 0.0, 0, False, 0
    capturado = b""
    t0 = time.time()
    while True:
        buf = mic.stdout.read(CHUNK)
        if not buf or len(buf) < CHUNK:
            break
        capturado += buf
        r = rms(buf)
        if muestras < 8:
            piso = max(piso, r)
        else:
            if r > piso * 3 + 250:
                habla, silencio = True, 0
            elif habla:
                silencio += 1
                if silencio >= SILENIO_PARA_CORTE:
                    break
        muestras += 1
        if time.time() - t0 > MAX_CAPTURA_S:
            break
    mic.terminate()
    t_cap = time.time() - t0
    wav = f"voz-entrada-{num}.wav"
    with wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(capturado)
    return wav, t_cap


def asr(wav):
    out = subprocess.run(
        ["curl", "-s", f"http://127.0.0.1:{PUERTO}/v1/audio/transcriptions",
         "-F", f"file=@{wav}", "-F", "model=x"],
        capture_output=True, text=True).stdout
    try:
        return json.loads(out).get("text", "")
    except Exception:
        return ""


def responder(texto):
    MENSAJES.append({"role": "user", "content": texto})
    cuerpo = json.dumps({"model": MODELO_ID,
                         "messages": MENSAJES[-9:]}).encode()
    p = subprocess.run(
        ["curl", "-s", f"http://127.0.0.1:{PUERTO}/v1/chat/completions",
         "-H", "Content-Type: application/json", "-d", cuerpo],
        capture_output=True, text=True)
    try:
        contenido = json.loads(
            p.stdout)["choices"][0]["message"]["content"].strip()
    except Exception:
        contenido = "(sin respuesta)"
    MENSAJES.append({"role": "assistant", "content": contenido})
    return contenido


def sintetizar(num, texto, voz, bin_tts):
    """Texto por archivo 0600 (nunca argv: visible en ps; ADR-007)."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt",
                                     delete=False) as f:
        f.write(texto)
        prompt_path = f.name
    os.chmod(prompt_path, 0o600)
    out_path = f"voz-salida-{num}"   # llama-tts no añade extensión
    subprocess.run(
        [bin_tts, "-m", str(SNAP / "LFM3-Omni-2B-Q4_K_M.gguf"),
         "-mm", str(SNAP / "mmproj-LFM3-Omni-2B-Q4_0.gguf"),
         "--tts-lang", "es", "--tts-voice", voz, "--no-escape",
         "-f", prompt_path, "-o", out_path],
        capture_output=True, text=True)
    os.unlink(prompt_path)
    return out_path if os.path.exists(out_path) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voz", choices=["male", "female"], default="male")
    args = ap.parse_args()
    bin_tts = shutil.which("llama-tts")
    if not bin_tts:
        print("BLOQ: llama-tts no está en PATH (ADR-006 §4)", flush=True)
        return 1
    print(f"híbrida ADR-007 lista — voz {args.voz} garantizada; di "
          f"«adiós» para terminar ({MAX_TURNOS} turnos max)", flush=True)
    for i in range(1, MAX_TURNOS + 1):
        print(f"--- turno {i}: habla (corto con ~1.4 s de silencio) ---",
              flush=True)
        wav, t_cap = capturar(i)
        t0 = time.time()
        texto = asr(wav)
        t_asr = time.time() - t0
        if not texto.strip():
            print("    (sin voz detectada)", flush=True)
            continue
        t1 = time.time()
        respuesta = responder(texto)
        t_llm = time.time() - t1
        t2 = time.time()
        voz_out = sintetizar(i, respuesta, args.voz, bin_tts)
        t_tts = time.time() - t2
        f0 = f0_mediana(voz_out) if voz_out else None
        print(f"    oído: {texto.strip()[:160]}", flush=True)
        print(f"    respuesta: {respuesta[:160]}", flush=True)
        print(f"    latencias: ASR {t_asr:.1f}s + LLM {t_llm:.1f}s + "
              f"TTS {t_tts:.1f}s = {t_asr + t_llm + t_tts:.1f}s | "
              f"F0 {f0} Hz", flush=True)
        if voz_out:
            subprocess.run(["afplay", voz_out], check=False)
        if "adios" in texto.lower() or "adiós" in texto.lower():
            print("FIN (adiós detectado)", flush=True)
            return 0
    print("FIN de la conversación", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
