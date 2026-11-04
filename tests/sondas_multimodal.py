"""Sondas multimodales reproducibles por hardware (ajuste PLAN LFM3-2).

Mide, contra el motor vivo en loopback, las capacidades que el artefacto
congelado (ADR-001) declara: ASR por input_audio, endpoint de
transcripción, B-T8 en su forma correcta, video temporal, voz por
/v1/realtime (documenta #31689) y voz por llama-tts con pico de memoria.
Registra hardware, versiones y hashes para comparar entre máquinas.

Es exploratorio: NO es gate. Los umbrales de cada TAREA I1-V se fijan en
su SPEC antes de medir; estas cifras son observación, no línea base.
Sólo fixtures sintéticos (WAV versionados en tests/golden/medios-binarios,
generados con `say` Paulina es_MX; video con ffmpeg lavfi): nunca voz ni
cámara del Operador (D-09). La salida del modelo es dato no confiable: se
registra, no se ejecuta. Plan por máquina: docs/roadmap/pruebas-hardware.md.

Uso: python3.12 tests/sondas_multimodal.py [--modelo GGUF] [--mmproj GGUF]
       [--salida DIR] [--sin-tts] [--sin-realtime] [--regenerar-fixtures]
Requiere: motor en 127.0.0.1:8091 con el mismo artefacto, ffmpeg y
llama-tts en PATH (macOS, Linux o Windows). --regenerar-fixtures sólo en
macOS (say). Escribe en DIR (default docs/reviews/evidence/sondas-<máquina>-
<fecha>/) un JSON de resultados, un resumen y, en medios-binarios/, los
WAV/MP4 producidos.
"""

import sys

if sys.version_info < (3, 12):
    sys.exit("BLOQ: se requiere Python 3.12 o superior")

import argparse
import base64
import datetime
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import struct
import subprocess
import time
import unicodedata
import urllib.error
import urllib.request
import wave
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8091"
SNAP = (Path.home() / ".cache/huggingface/hub/models--LiquidAI--"
        "LFM3-Omni-2B-GGUF/snapshots/d508b88f08a5b4286f2d2805a6a8d69a0ff44c72")
# Rutas por defecto = caché HF de la línea base; otra máquina usa
# --modelo/--mmproj o LFM3_MODELO/LFM3_MMPROJ (el hash se registra).
MODELO = Path(os.environ.get("LFM3_MODELO", SNAP / "LFM3-Omni-2B-Q4_K_M.gguf"))
MMPROJ = Path(os.environ.get("LFM3_MMPROJ", SNAP / "mmproj-LFM3-Omni-2B-Q4_0.gguf"))
FIXTURES = RAIZ / "tests" / "golden" / "medios-binarios"
HASHES_FIXTURES = RAIZ / "tests" / "golden" / "fixtures-audio-sha256.json"
VOZ_SAY = "Paulina"
# Corpus sintético es-MX sin cifras (los números escritos sesgan el CER).
CORPUS = [
    "El paquete llega el martes por la tarde.",
    "La reunión empieza mañana a las nueve.",
    "Necesito una mesa para cuatro personas.",
    "El tren sale de la estación central.",
    "Por favor apaga la luz de la cocina.",
    "Hoy hace mucho calor en la ciudad.",
    "Mi hermana estudia medicina en Puebla.",
    "El perro duerme debajo de la silla.",
    "Compramos pan y leche en la tienda.",
    "La biblioteca cierra los domingos.",
]


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def sh(args, timeout=180, **kw):
    """Subproceso con timeout (P-8 mostró un bucle de 215 s)."""
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, **kw)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def normalizar(texto):
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ ]", " ", t)).strip()


def cer(ref, hip):
    """Distancia de Levenshtein por carácter / longitud de la referencia."""
    a, b = normalizar(ref), normalizar(hip)
    previa = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        fila = [i]
        for j, cb in enumerate(b, 1):
            fila.append(min(previa[j] + 1, fila[j - 1] + 1,
                            previa[j - 1] + (ca != cb)))
        previa = fila
    return round(previa[-1] / max(1, len(a)), 4)


def post(ruta, cuerpo, tipo="application/json", timeout=180):
    datos = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo).encode()
    req = urllib.request.Request(BASE + ruta, data=datos,
                                 headers={"Content-Type": tipo})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r), time.time() - t
    except urllib.error.HTTPError as exc:
        return exc.code, {"error": exc.read()[:300].decode("utf-8", "replace")}, time.time() - t


def get(ruta):
    with urllib.request.urlopen(BASE + ruta, timeout=10) as r:
        return json.load(r)


# ---------------------------------------------------------------- entorno

def _hardware():
    """CPU/RAM/GPU sin dependencias; nunca hostname ni usuario (repo público)."""
    sistema = platform.system()
    hw = {"sistema": sistema, "modelo": "", "cpu": platform.processor(),
          "nucleos": str(os.cpu_count()), "ram_bytes": 0, "gpu": None}
    if sistema == "Darwin":
        def sysctl(k):
            return sh(["sysctl", "-n", k]).stdout.strip()
        hw.update(modelo=sysctl("hw.model"), cpu=sysctl("machdep.cpu.brand_string"),
                  ram_bytes=int(sysctl("hw.memsize") or 0))
    elif sistema == "Linux":
        info = Path("/proc/cpuinfo").read_text(errors="replace")
        m = re.search(r"^model name\s*:\s*(.+)$", info, re.M)
        hw["cpu"] = m.group(1).strip() if m else hw["cpu"]
        m = re.search(r"^MemTotal:\s*(\d+) kB", Path("/proc/meminfo").read_text(), re.M)
        hw["ram_bytes"] = int(m.group(1)) * 1024 if m else 0
        hw["virtualizado"] = "microsoft" in platform.release().lower() and "WSL2" or None
    elif sistema == "Windows":
        import ctypes

        class _Mem(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        mem = _Mem(); mem.dwLength = ctypes.sizeof(_Mem)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
        hw["ram_bytes"] = int(mem.ullTotalPhys)
    if shutil.which("nvidia-smi"):
        r = sh(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader"], timeout=20)
        hw["gpu"] = r.stdout.strip() or None
    hw["modelo"] = hw["modelo"] or re.sub(r"[^A-Za-z0-9]+", "-", f"{sistema}-{hw['cpu']}")[:60]
    return hw


def entorno():
    for ruta in (MODELO, MMPROJ):
        if not ruta.is_file():
            sys.exit(f"BLOQ: artefacto no encontrado: {ruta} (usa --modelo/--mmproj)")
    binarios = {}
    for nombre in ("llama-server", "llama-tts", "ffmpeg", "ffprobe"):
        ruta = shutil.which(nombre)
        if ruta:
            real = os.path.realpath(ruta)
            binarios[nombre] = {"ruta": real, "sha256": sha256(real)}
    lineas_version = sh(["llama-server", "--version"]).stderr.splitlines()
    versiones = {
        "llama-server": next((l.strip() for l in lineas_version if l.startswith("version:")), None),
        "ffmpeg": (sh(["ffmpeg", "-version"]).stdout.splitlines() or [""])[0],
    }
    props = get("/props")
    return {
        "fecha_utc": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "hardware": _hardware(),
        "so": {"plataforma": platform.platform(terse=True), "python": platform.python_version()},
        "versiones": versiones, "binarios": binarios,
        "artefacto": {"modelo_sha256": sha256(MODELO), "mmproj_sha256": sha256(MMPROJ),
                      "mmproj": MMPROJ.name},
        "motor": {"build_info": props.get("build_info"), "modalities": props.get("modalities"),
                  "total_slots": props.get("total_slots")},
    }


# ---------------------------------------------------------------- fixtures

def exigir_voz_say():
    """Sin la voz es-MX el CER no es comparable entre máquinas: fallo cerrado."""
    if not re.search(rf"^{VOZ_SAY}\s.*es_MX", sh(["say", "-v", "?"]).stdout, re.M):
        sys.exit(f"BLOQ: voz say «{VOZ_SAY}» (es_MX) no disponible")


def regenerar_fixtures():
    """Sólo macOS: rehace los WAV del corpus con say Paulina es_MX."""
    exigir_voz_say()
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for i, texto in enumerate(CORPUS):
        aiff = FIXTURES / f"asr_es_{i:02d}.aiff"
        if sh(["say", "-v", VOZ_SAY, "-o", str(aiff), texto]).returncode != 0:
            sys.exit(f"BLOQ: say -v {VOZ_SAY} falló")
        a_16k(aiff, FIXTURES / f"asr_es_{i:02d}.wav")
        aiff.unlink(missing_ok=True)
    nuevos = {p.name: sha256(p) for p in sorted(FIXTURES.glob("asr_es_*.wav"))}
    HASHES_FIXTURES.write_text(json.dumps({"origen": f"say -v {VOZ_SAY} (es_MX), regenerado",
                                            "sha256": nuevos}, ensure_ascii=False, indent=1) + "\n",
                               encoding="utf-8")


def fixture(i):
    wav = FIXTURES / f"asr_es_{i:02d}.wav"
    if not wav.is_file():
        sys.exit(f"BLOQ: fixture ausente {wav} (macOS: --regenerar-fixtures)")
    return wav


def verificar_fixtures():
    """D-1: un WAV alterado (CRLF, copia corrupta) haría incomparable el CER."""
    esperados = json.loads(HASHES_FIXTURES.read_text(encoding="utf-8"))["sha256"]
    for nombre, h in esperados.items():
        if not (FIXTURES / nombre).is_file() or sha256(FIXTURES / nombre) != h:
            sys.exit(f"BLOQ: fixture {nombre} ausente o con hash distinto al versionado")
    return esperados


def a_16k(origen, destino):
    """WAV PCM16 mono 16 kHz con ffmpeg (portable; antes afconvert)."""
    r = sh(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(origen),
            "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", str(destino)])
    if r.returncode != 0:
        raise OSError(f"ffmpeg no convirtió {Path(origen).name}")
    return destino


def chat_audio(wav, sistema="Perform ASR in Spanish.", tipo="input_audio"):
    b = base64.b64encode(Path(wav).read_bytes()).decode()
    parte = ({"type": "input_audio", "input_audio": {"data": b, "format": "wav"}}
             if tipo == "input_audio" else
             {"type": "audio_url", "audio_url": {"url": "data:audio/wav;base64," + b}})
    return post("/v1/chat/completions", {"messages": [
        {"role": "system", "content": sistema},
        {"role": "user", "content": [parte]}], "max_tokens": 64})


def transcribir_multipart(wav):
    lim = "----sondas"
    cuerpo = (f"--{lim}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\nx\r\n"
              f"--{lim}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\nes\r\n"
              f"--{lim}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.wav\"\r\n"
              "Content-Type: audio/wav\r\n\r\n").encode() + Path(wav).read_bytes() + \
             f"\r\n--{lim}--\r\n".encode()
    return post("/v1/audio/transcriptions", cuerpo, f"multipart/form-data; boundary={lim}")


# ---------------------------------------------------------------- sondas

def sonda_asr(dir_):
    filas = []
    for i, frase in enumerate(CORPUS):
        wav = fixture(i)
        st, d, dt = chat_audio(wav)
        hip = d["choices"][0]["message"]["content"] if st == 200 else ""
        filas.append({"ref": frase, "hip": hip, "status": st, "s": round(dt, 2),
                      "cer": cer(frase, hip) if hip else 1.0})
        log(f"ASR {i}: cer={filas[-1]['cer']} {dt:.2f}s {hip!r}")
    cers = [f["cer"] for f in filas]
    return {"filas": filas, "cer_medio": round(sum(cers) / len(cers), 4),
            "s_mediana": sorted(f["s"] for f in filas)[len(filas) // 2]}


def sonda_bt8_y_multipart(dir_):
    wav = fixture(0)
    st_url, _, _ = chat_audio(wav, tipo="audio_url")
    st_in, d_in, _ = chat_audio(wav)
    st_mp, d_mp, dt_mp = transcribir_multipart(wav)
    return {"audio_url_status": st_url, "input_audio_status": st_in,
            "bt8_forma_correcta": st_url == 400 and st_in == 200,
            "multipart_status": st_mp, "multipart_s": round(dt_mp, 2),
            "multipart_texto": d_mp.get("text") if st_mp == 200 else None,
            "input_audio_texto": d_in["choices"][0]["message"]["content"] if st_in == 200 else None}


def sonda_video(dir_):
    mp4 = dir_ / "video_rojo_azul.mp4"
    sh(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=160x120:d=2,format=yuv420p",
        "-f", "lavfi", "-i", "color=c=blue:s=160x120:d=2,format=yuv420p",
        "-filter_complex", "[0][1]concat=n=2:v=1", "-r", "8", str(mp4)])
    b = base64.b64encode(mp4.read_bytes()).decode()
    st, d, dt = post("/v1/chat/completions", {"messages": [
        {"role": "system", "content": "Answer questions about the video using what you see."},
        {"role": "user", "content": [
            {"type": "video_url", "video_url": {"url": "data:video/mp4;base64," + b}},
            {"type": "text", "text": "What color is the video at the start and at the end?"}]}],
        "max_tokens": 40})
    texto = d["choices"][0]["message"]["content"] if st == 200 else ""
    t = texto.lower()
    # Orden temporal: «red» debe aparecer antes que «blue» (inicio→fin).
    return {"status": st, "s": round(dt, 2), "respuesta": texto,
            "prompt_tokens": d.get("usage", {}).get("prompt_tokens"),
            "temporal_correcta": _orden(t, "red", "blue")}


def _orden(texto, primero, despues):
    """Palabras completas (N-1: «colored» no cuenta como red) y en orden."""
    a = re.search(rf"\b{primero}\b", texto)
    b = re.search(rf"\b{despues}\b", texto)
    return bool(a and b and a.start() < b.start())


def _ws(path="/v1/realtime"):
    s = socket.create_connection(("127.0.0.1", 8091), timeout=180)
    k = base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:8091\r\nUpgrade: websocket\r\n"
               f"Connection: Upgrade\r\nSec-WebSocket-Key: {k}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    h = b""
    while b"\r\n\r\n" not in h:
        c = s.recv(1)
        if not c:
            raise EOFError("handshake WS cortado")
        h += c
    if not h.startswith(b"HTTP/1.1 101"):
        raise ConnectionError("handshake WS sin 101: " + h.split(b"\r\n")[0].decode("latin-1"))
    return s


def _enviar(s, obj):
    p = json.dumps(obj).encode(); m = os.urandom(4); n = len(p)
    if n < 126:
        cab = bytes([0x81, 0x80 | n])
    elif n < 65536:
        cab = bytes([0x81, 0x80 | 126]) + struct.pack(">H", n)
    else:
        cab = bytes([0x81, 0x80 | 127]) + struct.pack(">Q", n)
    s.sendall(cab + m + bytes(c ^ m[i % 4] for i, c in enumerate(p)))


def _exacto(s, n):
    b = b""
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise EOFError
        b += c
    return b


def _recibir(s):
    b0, b1 = _exacto(s, 2); n = b1 & 0x7F
    if n == 126:
        n = struct.unpack(">H", _exacto(s, 2))[0]
    elif n == 127:
        n = struct.unpack(">Q", _exacto(s, 8))[0]
    return b0 & 0x0F, _exacto(s, n)


def sonda_realtime(dir_):
    """Voz por /v1/realtime en modo mixto; documenta #31689 (sin lang)."""
    frase = "La reunión empieza mañana a las nueve."
    s = _ws(); _recibir(s)
    _enviar(s, {"type": "session.update", "session": {"type": "realtime",
                "output_modalities": ["text", "audio"], "instructions": "Responde en español, breve."}})
    _enviar(s, {"type": "conversation.item.create", "item": {"type": "message", "role": "user",
                "content": [{"type": "input_text", "text": "Repite exactamente: " + frase}]}})
    _enviar(s, {"type": "response.create"})
    pcm, texto, t0, primero = b"", "", time.time(), None
    while time.time() - t0 < 120:
        op, d = _recibir(s)
        if op != 1:
            continue
        ev = json.loads(d)
        if ev["type"] == "response.output_audio.delta":
            primero = primero or time.time() - t0
            pcm += base64.b64decode(ev["delta"])
        elif ev["type"].endswith(".delta") and isinstance(ev.get("delta"), str):
            texto += ev["delta"]
        if ev["type"] in ("response.done", "error"):
            break
    s.close()
    wav = dir_ / "realtime_mixed.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
    hip = ""
    if pcm:
        st, d, _ = transcribir_multipart(a_16k(wav, dir_ / "realtime_mixed_16k.wav"))
        hip = d.get("text", "") if st == 200 else ""
    return {"texto": texto, "voz_s": round(len(pcm) / 48000, 2),
            "primer_audio_s": primero and round(primero, 2), "re_asr": hip,
            "cer_voz": cer(frase, hip) if hip else 1.0,
            "nota": "sin lang/voice en server-realtime (ggml-org/llama.cpp#31689)"}


def sonda_tts(dir_):
    filas = []
    for i, frase in enumerate(CORPUS[:3]):
        wav = dir_ / f"tts_{i:02d}.wav"
        t = time.time()
        cmd = ["llama-tts", "-m", str(MODELO), "-mm", str(MMPROJ),
               "--tts-lang", "es", "-p", frase, "-o", str(wav)]  # frase fija del corpus, no salida del modelo
        # Pico RSS: macOS `time -l` (bytes), Linux GNU `time -v` (kB); Windows sin medir.
        sistema = platform.system()
        if sistema == "Darwin":
            cmd = ["/usr/bin/time", "-l"] + cmd
        elif sistema == "Linux" and Path("/usr/bin/time").exists():
            cmd = ["/usr/bin/time", "-v"] + cmd
        r = sh(cmd)
        if r.returncode != 0:
            raise OSError(f"llama-tts falló (exit {r.returncode})")
        dt = time.time() - t
        m = re.search(r"(\d+)\s+maximum resident set size", r.stderr)
        if not m:
            mk = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", r.stderr)
            m = mk and re.match(r"(\d+)", str(int(mk.group(1)) * 1024))
        st, d, _ = transcribir_multipart(a_16k(wav, dir_ / f"tts_{i:02d}_16k.wav"))
        hip = d.get("text", "") if st == 200 else ""
        filas.append({"texto": frase, "s": round(dt, 2), "rss_max_bytes": int(m.group(1)) if m else None,
                      "re_asr": hip, "cer": cer(frase, hip) if hip else 1.0})
        log(f"TTS {i}: {dt:.1f}s cer={filas[-1]['cer']} rss={filas[-1]['rss_max_bytes']}")
    rss = [f["rss_max_bytes"] for f in filas if f["rss_max_bytes"]]
    return {"filas": filas, "rss_max_bytes": max(rss) if rss else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida")
    ap.add_argument("--sin-tts", action="store_true")
    ap.add_argument("--sin-realtime", action="store_true")
    ap.add_argument("--modelo")
    ap.add_argument("--mmproj")
    ap.add_argument("--regenerar-fixtures", action="store_true")
    a = ap.parse_args()
    global MODELO, MMPROJ
    MODELO = Path(a.modelo) if a.modelo else MODELO
    MMPROJ = Path(a.mmproj) if a.mmproj else MMPROJ
    if a.regenerar_fixtures:
        regenerar_fixtures()
    env = entorno()
    hw = env["hardware"]["modelo"].replace(",", "-") or "desconocido"
    dir_ = Path(a.salida) if a.salida else (
        RAIZ / "docs/reviews/evidence" / f"sondas-{hw}-{env['fecha_utc'][:10]}")
    dir_.mkdir(parents=True, exist_ok=True)
    medios = dir_ / "medios-binarios"  # binarios: skip_dirs del gate de tamaños
    medios.mkdir(exist_ok=True)
    log("entorno:", env["hardware"], env["motor"]["build_info"])
    env["fixtures"] = verificar_fixtures()
    res = {"schema": "lfm3-omni/sondas-multimodal/v1", "entorno": env, "errores": {}}
    sondas = [("asr", sonda_asr), ("bt8_y_multipart", sonda_bt8_y_multipart),
              ("video", sonda_video)]
    if not a.sin_realtime:
        sondas.append(("realtime", sonda_realtime))
    if not a.sin_tts:
        sondas.append(("tts", sonda_tts))
    for nombre, fn in sondas:
        try:  # una sonda caída no borra las demás: se registra su error
            res[nombre] = fn(medios)
        except (OSError, EOFError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            res["errores"][nombre] = f"{type(exc).__name__}: {exc}"[:300]
            log(f"sonda {nombre} falló: {res['errores'][nombre]}")
    (dir_ / "resultados.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n",
                                          encoding="utf-8")
    r = res
    vacio = {"cer_medio": None, "s_mediana": None, "bt8_forma_correcta": None,
             "multipart_status": None, "multipart_s": None,
             "temporal_correcta": None, "respuesta": None, "prompt_tokens": None}
    for clave in ("asr", "bt8_y_multipart", "video"):
        r.setdefault(clave, vacio)
    gpu = f", GPU {env['hardware']['gpu']}" if env["hardware"]["gpu"] else ""
    lineas = [
        f"# Sondas multimodales — {env['hardware']['modelo']} ({env['hardware']['cpu']}, "
        f"{env['hardware']['ram_bytes'] // 2**30} GB{gpu}) — {env['fecha_utc']}", "",
        "Exploratorio, no gate (ver docstring de tests/sondas_multimodal.py).", "",
        f"- motor: {env['motor']['build_info']}; modalities {env['motor']['modalities']}",
        f"- ASR input_audio: CER medio {r['asr']['cer_medio']} sobre {len(CORPUS)} frases; "
        f"mediana {r['asr']['s_mediana']} s",
        f"- B-T8 forma correcta (audio_url 400, input_audio 200): {r['bt8_y_multipart']['bt8_forma_correcta']}",
        f"- /v1/audio/transcriptions: {r['bt8_y_multipart']['multipart_status']} en "
        f"{r['bt8_y_multipart']['multipart_s']} s",
        f"- video temporal rojo→azul correcto: {r['video']['temporal_correcta']} "
        f"({r['video']['respuesta']!r}; prompt_tokens={r['video']['prompt_tokens']})",
    ]
    if r["errores"]:
        lineas.append(f"- errores de sonda: {r['errores']}")
    if "realtime" in r:
        lineas.append(f"- realtime mixto: CER de voz {r['realtime']['cer_voz']}; primer audio "
                      f"{r['realtime']['primer_audio_s']} s ({r['realtime']['nota']})")
    if "tts" in r:
        cers = [f["cer"] for f in r["tts"]["filas"]]
        lineas.append(f"- llama-tts es: CER re-ASR {cers}; tiempos {[f['s'] for f in r['tts']['filas']]} s; "
                      + (f"RSS máx {r['tts']['rss_max_bytes'] / 2**30:.2f} GiB"
                         if r["tts"]["rss_max_bytes"] else "RSS sin medir en esta plataforma"))
    (dir_ / "resumen.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas))
    print("salida:", dir_)


if __name__ == "__main__":
    main()
