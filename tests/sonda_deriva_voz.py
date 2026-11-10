# Experimento de deriva acustica en realtime multi-turno (ADR-014).
# Evidencia: voz-registros.txt bloques [2]-[4]. Sonda manual contra
# motor vivo (8091); no es unittest.
# Entrada sintetica (say, voz Carlos es_CO) -> realtime 8091.
# Modos: sesion_unica (historial acumula) | sesion_por_turno (sesion
# fresca por turno, mitiga la deriva). Mide F0 por turno. Sin micro.
import base64, json, math, os, socket, statistics, struct, subprocess, sys, time, wave

PUERTO = 8091
MODO = sys.argv[1] if len(sys.argv) > 1 else "sesion_por_turno"
VOZ_SAY = sys.argv[2] if len(sys.argv) > 2 else "Carlos (Enhanced)"
PREFIJO = sys.argv[3] if len(sys.argv) > 3 else "in"
PREGUNTAS = [
    "¿Qué hora es ahora mismo?",
    "Recomiéndame una película breve para esta noche.",
    "¿Cómo está el clima en la mañana de hoy?",
    "Cierra contando un chiste muy corto, por favor.",
]


def conectar():
    s = socket.create_connection(("127.0.0.1", PUERTO), timeout=300)
    k = base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET /v1/realtime HTTP/1.1\r\nHost: 127.0.0.1:{PUERTO}\r\n"
               "Upgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {k}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    h = b""
    while b"\r\n\r\n" not in h:
        h += s.recv(1)
    assert b"101" in h.split(b"\r\n")[0], h[:200]
    return s


def enviar(s, obj):
    p = json.dumps(obj).encode()
    m = os.urandom(4)
    n = len(p)
    if n < 126:
        hdr = bytes([0x81, 0x80 | n])
    elif n < 65536:
        hdr = bytes([0x81, 0x80 | 126]) + struct.pack(">H", n)
    else:
        hdr = bytes([0x81, 0x80 | 127]) + struct.pack(">Q", n)
    s.sendall(hdr + m + bytes(b ^ m[i % 4] for i, b in enumerate(p)))


def leer_exacto(s, n):
    b = b""
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise EOFError
        b += c
    return b


def recibir(s):
    b0, b1 = leer_exacto(s, 2)
    n = b1 & 0x7F
    if n == 126:
        n = struct.unpack(">H", leer_exacto(s, 2))[0]
    elif n == 127:
        n = struct.unpack(">Q", leer_exacto(s, 8))[0]
    return b0 & 0x0F, leer_exacto(s, n)


def f0_mediana(pcm, sr=24000):
    x = struct.unpack(f"<{len(pcm)//2}h", pcm)
    tam = int(sr * 0.04)
    energias = [sum(v*v for v in x[i:i+tam]) for i in range(0, len(x) - tam, tam)]
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


def nueva_sesion():
    s = conectar()
    recibir(s)
    enviar(s, {"type": "session.update", "session": {
        "type": "realtime", "output_modalities": ["text", "audio"],
        "instructions": "Conversacion en espanol, breve y natural, una o "
                        "dos frases. Eres la voz local de Kris.",
        "audio": {"output": {"voice": "male", "language": "es"}}}})
    return s


def turno(s, i, pcm_in):
    for j in range(0, len(pcm_in), 6400):
        enviar(s, {"type": "input_audio_buffer.append",
                   "audio": base64.b64encode(pcm_in[j:j+6400]).decode()})
    enviar(s, {"type": "input_audio_buffer.commit"})
    enviar(s, {"type": "response.create"})
    pcm = b""
    txt = ""
    t0 = time.time()
    while True:
        op, d = recibir(s)
        if op != 1:
            continue
        ev = json.loads(d)
        t = ev.get("type")
        if t == "response.output_audio.delta":
            pcm += base64.b64decode(ev["delta"])
        elif (t or "").endswith(".delta") and isinstance(ev.get("delta"), str):
            txt += ev["delta"]
        elif t == "error":
            return i, None, f"ERROR {json.dumps(ev, ensure_ascii=False)[:80]}", 0
        if t in ("response.done", "error"):
            break
    f0 = f0_mediana(pcm) if pcm else None
    reg = ("masc" if f0 and f0 < 155 else
           "amb" if f0 and f0 < 200 else "fem")
    print(f"  turno {i}: F0 {f0} Hz [{reg}] 1a-voz "
          f"{round(time.time()-t0, 2)}s :: {txt.strip()[:80]}", flush=True)
    return i, f0, txt.strip()[:60], len(pcm) / 48000


# Entradas sinteticas: say Carlos (es_CO) 16 kHz mono s16.
PCMS = []
for i, q in enumerate(PREGUNTAS, 1):
    wav = f"{PREFIJO}-{i}.wav"
    if not os.path.exists(wav):
        subprocess.run(["say", "-v", VOZ_SAY,
                        "--data-format=LEI16@16000", "-o", wav, q], check=True)
    w = wave.open(wav)
    assert w.getframerate() == 16000 and w.getnchannels() == 1
    PCMS.append(w.readframes(w.getnframes()))
    w.close()

print(f"modo: {MODO} — 4 turnos, voz masculina es", flush=True)
F0S = []
if MODO == "sesion_unica":
    s = nueva_sesion()
    for i, pcm_in in enumerate(PCMS, 1):
        _, f0, _, _ = turno(s, i, pcm_in)
        F0S.append(f0)
else:
    for i, pcm_in in enumerate(PCMS, 1):
        s = nueva_sesion()
        _, f0, _, _ = turno(s, i, pcm_in)
        F0S.append(f0)
        s.close()
        time.sleep(0.5)
valides = [f for f in F0S if f]
print(f"RESUMEN {MODO}: F0s={valides} "
      f"mediana={round(statistics.median(valides),1) if valides else None} Hz", flush=True)
