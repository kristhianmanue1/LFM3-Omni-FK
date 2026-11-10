# Sonda de /v1/realtime (fix #31689, PR #31982; ADR-014).
# Evidencia: docs/reviews/evidence/motor-2-31689/ (sonda-realtime.txt,
# voz-registros.txt). Sonda manual contra motor vivo; no es unittest.
# stdlib puro, solo loopback. Uso: probe_rt.py <puerto> <caso> [sesion_json]
# Metrica: instruccion de frase fija -> comparar canal de texto vs re-ASR.
import base64, json, os, socket, struct, subprocess, sys, time, wave

PUERTO = int(sys.argv[1])
CASO = sys.argv[2]
SESION_EXTRA = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
FRASE = "El paquete llega el martes a las tres de la tarde."


def conectar():
    s = socket.create_connection(("127.0.0.1", PUERTO), timeout=300)
    k = base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET /v1/realtime HTTP/1.1\r\nHost: 127.0.0.1:{PUERTO}\r\n"
               "Upgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {k}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    h = b""
    while b"\r\n\r\n" not in h:
        h += s.recv(1)
    linea = h.split(b"\r\n")[0].decode()
    if "101" not in linea:
        raise SystemExit(f"handshake fallo: {linea}")
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


def main():
    s = conectar()
    recibir(s)  # session.created
    ses = {
        "type": "realtime",
        "output_modalities": ["text", "audio"],
        "instructions": f'Di exactamente: "{FRASE}"',
    }
    ses.update(SESION_EXTRA)
    enviar(s, {"type": "session.update", "session": ses})
    enviar(s, {"type": "conversation.item.create", "item": {
        "type": "message", "role": "user",
        "content": [{"type": "input_text", "text": "Adelante."}]}})
    enviar(s, {"type": "response.create"})
    pcm = b""
    txt = ""
    t0 = time.time()
    primero = None
    error = None
    while True:
        op, d = recibir(s)
        if op != 1:
            continue
        ev = json.loads(d)
        t = ev.get("type")
        if t == "response.output_audio.delta":
            primero = primero or time.time() - t0
            pcm += base64.b64decode(ev["delta"])
        elif (t or "").endswith(".delta") and isinstance(ev.get("delta"), str):
            txt += ev["delta"]
        elif t == "error":
            error = ev
        if t in ("response.done", "error"):
            break
    s.close()
    asr = "(sin audio)"
    if pcm:
        wav = f"{CASO}.wav"
        wav16 = f"{CASO}16.wav"
        with wave.open(wav, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(pcm)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1",
                        wav, wav16], check=True)
        out = subprocess.run(
            ["curl", "-s", f"http://127.0.0.1:{PUERTO}/v1/audio/transcriptions",
             "-F", f"file=@{wav16}", "-F", "model=x"],
            capture_output=True, text=True).stdout
        try:
            asr = json.loads(out).get("text", out)
        except Exception:
            asr = out
    print(json.dumps({
        "caso": CASO,
        "sesion": SESION_EXTRA,
        "primer_audio_s": round(primero, 2) if primero else None,
        "audio_s": round(len(pcm) / 48000, 2),
        "texto_canal": txt.strip(),
        "re_asr": str(asr).strip(),
        "frase_esperada": FRASE,
        "error": error,
    }, ensure_ascii=False))


main()
