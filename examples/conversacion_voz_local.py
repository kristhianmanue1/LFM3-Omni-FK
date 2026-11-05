"""Conversación de voz casi en tiempo real con LFM3-Omni (loopback).

Exploratorio (ajuste PLAN LFM3-2, patrón de I1-VR; ADR-007): fin de turno
por silencio medido, respuesta SSE del motor 8091, voz frase por frase con
llama-tts --tts-lang es. Usa micrófono real: sólo con consentimiento del
Operador (D-09). El audio vive en un directorio temporal que se borra al
salir; las transcripciones de los turnos quedan retenidas en privado
(D-10, TAREA I1-VT): docs/reviews/evidence/privado/transcripciones/.
La salida del modelo es dato no confiable: sólo se reproduce, nunca se
ejecuta.

Uso: LFM3_CONSENTIMIENTO_D09=si python3.12 examples/conversacion_voz_local.py
     (macOS, micrófono :0)
"""
import sys

if sys.version_info < (3, 12):
    sys.exit("BLOQ: se requiere Python 3.12 o superior")

import array, atexit, hashlib, importlib.util, json, math, os, queue, re
import shutil, subprocess
import tempfile, threading, time, urllib.request, wave

DIR = tempfile.mkdtemp(prefix="lfm3-voz-")
atexit.register(shutil.rmtree, DIR, True)
BASE = "http://127.0.0.1:8091"
SNAP = os.path.expanduser("~/.cache/huggingface/hub/models--LiquidAI--"
                          "LFM3-Omni-2B-GGUF/snapshots/d508b88f08a5b4286f2d2805a6a8d69a0ff44c72")
MODELO = SNAP + "/LFM3-Omni-2B-Q4_K_M.gguf"
MMPROJ = SNAP + "/mmproj-LFM3-Omni-2B-Q4_0.gguf"
MIC, SR, TRAMO = ":0", 16000, 1600          # tramos de 100 ms
SILENCIO_FIN, MAX_TURNO, ESPERA_MAX = 0.9, 20.0, 12.0
TURNOS = 6
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

SISTEMA = ("Eres un asistente que conversa por voz en español con el "
           "Operador del proyecto LFM3-Omni. Responde en dos o tres frases "
           "cortas y naturales, sin listas, símbolos ni emojis.")
T0 = [0.0]


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def escuchar(n):
    """Graba hasta detectar ~0.9 s de silencio tras haber oído voz."""
    p = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error",
                          "-f", "avfoundation", "-i", MIC, "-ar", str(SR),
                          "-ac", "1", "-f", "s16le", "-"],
                         stdout=subprocess.PIPE)
    ruido, calib, voz, sil, hablo, t = [], 5, [], 0.0, False, time.time()
    try:
        while True:
            b = p.stdout.read(TRAMO * 2)
            if not b:
                break
            a = array.array("h"); a.frombytes(b)
            rms = math.sqrt(sum(x * x for x in a) / len(a))
            if calib:                       # primeros 500 ms: ruido de fondo
                ruido.append(rms); calib -= 1
                if not calib:
                    umbral = max(400.0, 3.0 * (sum(ruido) / len(ruido)))
                    subprocess.Popen(["afplay", "/System/Library/Sounds/Ping.aiff"])
                    log(f"[turno {n}] habla (umbral {umbral:.0f})…")
                continue
            if rms > umbral:
                hablo, sil = True, 0.0
            elif hablo:
                sil += 0.1
            if hablo:
                voz.append(b)
            dur = time.time() - t
            if (hablo and sil >= SILENCIO_FIN) or dur > MAX_TURNO or \
                    (not hablo and dur > ESPERA_MAX):
                break
    finally:
        p.terminate(); p.wait()
    T0[0] = time.time()
    if not voz:
        return None
    wav = os.path.join(DIR, f"rt_{n:02d}_tu.wav")
    with wave.open(wav, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(b"".join(voz))
    return wav


def transcribir(wav):
    lim = "----lfm3"
    cuerpo = (f"--{lim}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\nx\r\n"
              f"--{lim}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\nes\r\n"
              f"--{lim}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"t.wav\"\r\n"
              f"Content-Type: audio/wav\r\n\r\n").encode() + open(wav, "rb").read() + \
             f"\r\n--{lim}--\r\n".encode()
    req = urllib.request.Request(BASE + "/v1/audio/transcriptions", data=cuerpo,
                                 headers={"Content-Type": f"multipart/form-data; boundary={lim}"})
    return json.load(urllib.request.urlopen(req, timeout=60))["text"].strip()


def frases_sse(historial):
    """Respuesta en streaming SSE, entregada frase por frase."""
    req = urllib.request.Request(
        BASE + "/v1/chat/completions",
        data=json.dumps({"messages": historial, "max_tokens": 120,
                         "stream": True}).encode(),
        headers={"Content-Type": "application/json"})
    buf = ""
    with urllib.request.urlopen(req, timeout=120) as r:
        for linea in r:
            linea = linea.decode().strip()
            if not linea.startswith("data: ") or linea == "data: [DONE]":
                continue
            delta = json.loads(linea[6:])["choices"][0]["delta"].get("content") or ""
            buf += delta
            while True:
                m = re.search(r"[.!?…](\s|$)", buf)
                if not m or len(buf[:m.end()].strip()) < 3:
                    break
                yield buf[:m.end()].strip(); buf = buf[m.end():]
    if buf.strip():
        yield buf.strip()


def sintetizar(texto, salida):
    # Texto por archivo 0600 (nunca argv: visible en ps; ADR-007).
    prompt = salida + ".txt"
    fd = os.open(prompt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(texto_seguro(texto))
    try:
        subprocess.run(["llama-tts", "-m", MODELO, "-mm", MMPROJ, "--tts-lang", "es",
                        "-f", prompt, "-o", salida], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True, timeout=120)
    finally:
        os.unlink(prompt)


def responder(historial, n):
    cola, partes = queue.Queue(), []

    def reproductor():
        primero = True
        while (wav := cola.get()) is not None:
            if primero:
                log(f"   ▶ primera voz a {time.time() - T0[0]:.1f} s de que callaste")
                primero = False
            subprocess.run(["afplay", wav])
    hilo = threading.Thread(target=reproductor); hilo.start()
    for i, frase in enumerate(frases_sse(historial)):
        partes.append(frase)
        log(f"   LFM3 [{time.time() - T0[0]:.1f} s]:", frase)
        wav = os.path.join(DIR, f"rt_{n:02d}_{i}.wav")
        sintetizar(frase, wav)
        cola.put(wav)
    cola.put(None); hilo.join()
    return " ".join(partes)


exigir_consentimiento("el micrófono")
# D-10: retención privada de transcripciones (TAREA I1-VT).
_espec = importlib.util.spec_from_file_location(
    "transcripciones",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "src", "transcripciones.py"))
transcripciones = importlib.util.module_from_spec(_espec)
_espec.loader.exec_module(transcripciones)
SESION = transcripciones.new_session()
historial = [{"role": "system", "content": SISTEMA}]
saludo = os.path.join(DIR, "rt_00.wav")
sintetizar("Hola de nuevo. Ahora habla cuando escuches el pitido, y yo "
           "contesto cuando termines.", saludo)
subprocess.run(["afplay", saludo])
for n in range(1, TURNOS + 1):
    wav = escuchar(n)
    if not wav:
        log("   (no te escuché; termino)"); break
    texto = transcribir(wav)
    log(f"Tú [{time.time() - T0[0]:.1f} s]:", texto)
    historial.append({"role": "user", "content": texto})
    historial.append({"role": "assistant", "content": responder(historial, n)})
    try:
        with open(wav, "rb") as fuente:
            huella = hashlib.sha256(fuente.read()).hexdigest()
        transcripciones.record_turn(
            SESION, user_text=texto, reply=historial[-1]["content"],
            params={"flow": "SSE frase por frase", "max_tokens": 120,
                    "tts": "llama-tts es"},
            hashes={"input_wav": huella})
    except ValueError as error:
        log("   (turno sin transcripción válida; fin por D-10)",
            type(error).__name__)
        break
    if re.search(r"\badi[oó]s\b", texto.lower()):
        break
log("fin de la conversación")
