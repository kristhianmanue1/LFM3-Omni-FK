#!/usr/bin/env python3
"""Medición del gate de I1-VS (SPEC-i1-vs §3):
1) Ida-vuelta TTS -> ASR sobre 5 frases en español fijadas antes de medir:
   POST /v1/audio/speech en el gateway (8092) -> conversión a 16 kHz mono
   PCM16 con ffmpeg si la tasa difiere -> POST /v1/chat/completions
   (input_audio) en el mismo gateway.
   Criterio de pase: CER mediano <= 0.15 y ningún caso > 0.30.
2) Pico RSS del subproceso llama-tts (/usr/bin/time -l en macOS) y RSS
   de llama-server (8091) tras la síntesis < 4 GiB (REQ-5 / B-T10
   ampliado), más registro de swap global antes y después.

Uso: python3.12 tests/medir_tts_vs.py [salida.json]
Requiere motor en 8091 y gateway en 8092 (LFM3_GATEWAY_PORT).
"""

import base64
import importlib.util
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from gateway_http import _resolver_entorno_tts  # noqa: E402

_spec_va = importlib.util.spec_from_file_location(
    "medir_cer_va", RAIZ / "tests/medir_cer_va.py")
medir_cer_va = importlib.util.module_from_spec(_spec_va)
_spec_va.loader.exec_module(medir_cer_va)
cer = medir_cer_va.cer

_spec_rg = importlib.util.spec_from_file_location(
    "run_golden", RAIZ / "tests/run_golden.py")
run_golden = importlib.util.module_from_spec(_spec_rg)
_spec_rg.loader.exec_module(run_golden)

FRASES_VS = [
    {
        "id": "vs-01",
        "texto": "Hola, ¿cómo estás hoy?",
        "procedencia": "corpus-01 de tests/corpus_va.json (fijado 2026-11-05)",
    },
    {
        "id": "vs-02",
        "texto": "El servicio de inferencia funciona en local.",
        "procedencia": "corpus-02 de tests/corpus_va.json (fijado 2026-11-05)",
    },
    {
        "id": "vs-03",
        "texto": "La reunión es a las cuatro de la tarde.",
        "procedencia": "corpus-03 de tests/corpus_va.json (fijado 2026-11-05)",
    },
    {
        "id": "vs-04",
        "texto": "Necesito un café antes de empezar.",
        "procedencia": "corpus-04 de tests/corpus_va.json (fijado 2026-11-05)",
    },
    {
        "id": "vs-05",
        "texto": "Gracias por escuchar mis palabras.",
        "procedencia": "corpus-08 de tests/corpus_va.json (fijado 2026-11-05)",
    },
]
UMBRAL_MEDIANA = 0.15
UMBRAL_CASO = 0.30
LIMITE_RSS_BYTES = 4 * 1024 * 1024 * 1024


def _post_speech(puerto, texto, timeout=150):
    req = urllib.request.Request(
        f"http://127.0.0.1:{puerto}/v1/audio/speech",
        data=json.dumps({"input": texto}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), time.time() - t0
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), time.time() - t0


def _chat_asr(puerto, wav_bytes, timeout=120):
    b64 = base64.b64encode(wav_bytes).decode()
    payload = {
        "messages": [{"role": "user", "content": [
            {"type": "input_audio",
             "input_audio": {"data": b64, "format": "wav"}},
            {"type": "text",
             "text": "Transcribe exactamente el audio, sin comentarios."},
        ]}],
        "max_tokens": 200,
        "temperature": 0,
    }
    req = urllib.request.Request(
        f"http://127.0.0.1:{puerto}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        cuerpo = json.loads(resp.read())
        return resp.status, cuerpo["choices"][0]["message"]["content"]


def _a_16k_wav(wav_bytes, env_path):
    """Convierte WAV (24 kHz de llama-tts) a 16 kHz mono PCM16 con el
    ffmpeg inventariado para evaluación ASR uniforme."""
    d = tempfile.mkdtemp(prefix="lfm3-vs-16k-")
    try:
        origen = Path(d) / "in.wav"
        destino = Path(d) / "out16k.wav"
        origen.write_bytes(wav_bytes)
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-i", str(origen), "-ar", "16000", "-ac", "1",
             "-sample_fmt", "s16", str(destino)],
            env={"PATH": env_path}, capture_output=True, text=True,
            timeout=60, check=False,
        )
        if r.returncode != 0 or not destino.is_file():
            raise OSError(f"ffmpeg falló: {r.stderr}")
        return destino.read_bytes()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _medir_pico_rss_subproceso(frase):
    """Mide pico RSS de llama-tts con /usr/bin/time -l (macOS) o -v
    (Linux) entregando el texto por archivo 0600 (-f)."""
    bin_tts, modelo, mmproj, env = _resolver_entorno_tts()
    d = tempfile.mkdtemp(prefix="lfm3-vs-rss-")
    try:
        os.chmod(d, 0o700)
        prompt_path = os.path.join(d, "prompt.txt")
        wav_path = os.path.join(d, "out.wav")
        fd = os.open(prompt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(frase)
        cmd = [
            bin_tts, "-m", modelo, "-mm", mmproj,
            "--tts-lang", "es", "--no-escape",
            "-f", prompt_path, "-o", wav_path,
        ]
        sistema = platform.system()
        if sistema == "Darwin":
            cmd = ["/usr/bin/time", "-l"] + cmd
        elif sistema == "Linux" and Path("/usr/bin/time").exists():
            cmd = ["/usr/bin/time", "-v"] + cmd
        t0 = time.time()
        r = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=150,
            check=False,
        )
        dt = time.time() - t0
        if r.returncode != 0:
            raise OSError(f"llama-tts falló ({r.returncode})")
        m = re.search(r"(\d+)\s+maximum resident set size", r.stderr)
        rss_bytes = int(m.group(1)) if m else None
        if rss_bytes is None:
            mk = re.search(
                r"Maximum resident set size \(kbytes\):\s*(\d+)", r.stderr)
            if mk:
                rss_bytes = int(mk.group(1)) * 1024
        return rss_bytes, round(dt, 2)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _rss_motor_8091():
    """Deriva el PID del listener en 8091 y verifica propiedad por
    basename y bandera --port 8091 igual que B-T10 (SPEC-i0 r19)."""
    pids = run_golden._listener_pids(8091)
    if len(pids) != 1:
        return None
    pid = pids[0]
    comando = run_golden._comando_pid(pid)
    binario = comando.split(" ", 1)[0]
    if os.path.basename(binario) != "llama-server" \
            or "--port 8091" not in comando:
        return None
    salida = run_golden._sh(["ps", "-p", str(pid), "-o", "rss="]).strip()
    return int(salida) * 1024 if salida.isdigit() else None


def main():
    puerto = int(os.environ.get("LFM3_GATEWAY_PORT", "8092"))
    _, _, _, env_tts = _resolver_entorno_tts()
    swap_antes = run_golden._swap_mib_usado()
    casos = []
    for item in FRASES_VS:
        st, wav, dt_tts = _post_speech(puerto, item["texto"])
        if st != 200:
            print(f"BLOQ: {item['id']} speech HTTP {st}")
            return 2
        wav_16k = _a_16k_wav(wav, env_tts["PATH"])
        st_asr, pred = _chat_asr(puerto, wav_16k)
        if st_asr != 200:
            print(f"BLOQ: {item['id']} ASR HTTP {st_asr}")
            return 2
        valor_cer = cer(pred, item["texto"])
        casos.append({
            "id": item["id"],
            "procedencia": item["procedencia"],
            "referencia": item["texto"],
            "prediccion": pred,
            "cer": round(valor_cer, 4),
            "tts_segundos": round(dt_tts, 2),
            "wav_bytes": len(wav),
        })
        print(f"{item['id']}: CER {valor_cer:.3f} ({dt_tts:.2f}s) -> {pred!r}")

    rss_tts_bytes, dt_rss = _medir_pico_rss_subproceso(FRASES_VS[0]["texto"])
    rss_motor_bytes = _rss_motor_8091()
    swap_despues = run_golden._swap_mib_usado()

    valores = [c["cer"] for c in casos]
    mediana = statistics.median(valores)
    peor = max(valores)
    cer_ok = mediana <= UMBRAL_MEDIANA and peor <= UMBRAL_CASO
    rss_tts_ok = (rss_tts_bytes is not None
                  and rss_tts_bytes < LIMITE_RSS_BYTES)
    rss_motor_ok = (rss_motor_bytes is not None
                    and rss_motor_bytes < LIMITE_RSS_BYTES)
    pasa = cer_ok and rss_tts_ok and rss_motor_ok

    informe = {
        "schema": "lfm3-omni/gate-vs/v1",
        "criterio_cer": "CER mediano <= 0.15 y ningun caso > 0.30",
        "criterio_memoria": "RSS subproceso llama-tts < 4 GiB y RSS motor 8091 < 4 GiB",
        "mediana_cer": round(mediana, 4),
        "peor_cer": round(peor, 4),
        "cer_pass": cer_ok,
        "rss_tts_bytes": rss_tts_bytes,
        "rss_tts_mib": round(rss_tts_bytes / (1024 * 1024), 1) if rss_tts_bytes else None,
        "rss_tts_pass": rss_tts_ok,
        "rss_motor_8091_bytes": rss_motor_bytes,
        "rss_motor_8091_mib": round(rss_motor_bytes / (1024 * 1024), 1) if rss_motor_bytes else None,
        "rss_motor_pass": rss_motor_ok,
        "swap_host_antes_mib": swap_antes,
        "swap_host_despues_mib": swap_despues,
        "pass": pasa,
        "casos": casos,
    }
    print(f"mediana_cer={mediana:.3f} peor_cer={peor:.3f} "
          f"rss_tts={informe['rss_tts_mib']}MiB "
          f"rss_motor={informe['rss_motor_8091_mib']}MiB "
          f"swap_host={swap_antes:.0f}->{swap_despues:.0f}MiB -> "
          f"{'PASS' if pasa else 'FAIL'}")
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(
            json.dumps(informe, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0 if pasa else 1


if __name__ == "__main__":
    sys.exit(main())
