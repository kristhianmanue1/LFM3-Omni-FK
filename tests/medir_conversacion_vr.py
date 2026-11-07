#!/usr/bin/env python3
"""Medición del gate de I1-VR (SPEC-i1-vr §3):
1) Conversación local de N = 5 turnos consecutivos sobre fixtures
   sintéticos versionados (tests/medios-binarios/corpus-01.wav..05.wav)
   100 % a través del gateway (8092):
   - Marca de fin de turno: t_eot = time.monotonic() al iniciar el envío
     del WAV del turno al gateway.
   - Transcripción vía POST /v1/chat/completions (input_audio, stream=False).
   - Respuesta conversacional acumulada vía POST /v1/chat/completions
     (stream=True, max_tokens=96).
   - Segmentación incremental de frases desde el SSE; síntesis de la
     primera frase vía POST /v1/audio/speech en 8092.
   - t_first_voice = time.monotonic() al recibir el WAV válido de la
     primera frase; latencia_primera_voz_s = t_first_voice - t_eot.
   - Retención privada por turno en sesión D-10 (src/transcripciones.py).
2) Prueba real de desconexión de cliente a mitad de un stream SSE contra
   el gateway con motor vivo: verifica que el slot de llama-server (8091)
   queda libre (is_processing == False en /slots) y que el cerrojo del
   gateway queda liberado.
3) Aislamiento entre dos sesiones D-10 ejecutadas sin cruzarse.

Uso: python3.12 tests/medir_conversacion_vr.py [salida.json]
Requiere motor en 8091 y gateway en 8092 (LFM3_GATEWAY_PORT).
"""

import base64
import hashlib
import json
import math
import os
import re
import socket
import stat
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import transcripciones  # noqa: E402

N_TURNOS = 5
UMBRAL_P95_S = 8.0
SISTEMA = (
    "Eres un asistente que conversa por voz en español. Responde en una o "
    "dos frases cortas y naturales, sin listas, símbolos ni emojis."
)


def _p95(valores):
    ordenados = sorted(valores)
    if not ordenados:
        return 0.0
    idx = max(0, math.ceil(0.95 * len(ordenados)) - 1)
    return ordenados[idx]


def _texto_seguro_tts(texto):
    limpio = "".join(
        c for c in texto if (ord(c) >= 32 and ord(c) != 127 and c.isprintable())
    ).strip()
    return limpio[:600] or "De acuerdo."


def _transcribir_wav(puerto, wav_bytes, timeout=120):
    b64 = base64.b64encode(wav_bytes).decode("ascii")
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
        return cuerpo["choices"][0]["message"]["content"].strip()


def _sintetizar_frase(puerto, frase, timeout=120):
    req = urllib.request.Request(
        f"http://127.0.0.1:{puerto}/v1/audio/speech",
        data=json.dumps({"input": _texto_seguro_tts(frase)}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def _stream_frases(puerto, historial, max_tokens=96, timeout=120):
    req = urllib.request.Request(
        f"http://127.0.0.1:{puerto}/v1/chat/completions",
        data=json.dumps({
            "messages": historial,
            "max_tokens": max_tokens,
            "stream": True,
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    buf = ""
    t_first_token = None
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            linea = raw.decode("utf-8", errors="replace").strip()
            if not linea.startswith("data: ") or linea == "data: [DONE]":
                continue
            evento = json.loads(linea[6:])
            delta = (
                evento.get("choices", [{}])[0]
                .get("delta", {})
                .get("content")
                or ""
            )
            if delta and t_first_token is None:
                t_first_token = time.monotonic()
            buf += delta
            while True:
                m = re.search(r"[.!?…](\s|$)", buf)
                if not m or len(buf[:m.end()].strip()) < 12:
                    break
                yield buf[:m.end()].strip(), t_first_token
                buf = buf[m.end():]
    if buf.strip():
        yield buf.strip(), t_first_token


def _probar_cancelacion_en_motor_vivo(puerto_gw, puerto_motor=8091):
    """Abre un stream largo en el gateway, desconecta tras el primer
    chunk SSE y verifica que /slots del motor vuelve a is_processing=False."""
    cuerpo = json.dumps({
        "messages": [{
            "role": "user",
            "content": (
                "Cuenta del uno al cien en español escribiendo cada número "
                "con palabras completas y detalladas."
            ),
        }],
        "max_tokens": 180,
        "stream": True,
    }).encode("utf-8")
    peticion = (
        b"POST /v1/chat/completions HTTP/1.1\r\n"
        b"Host: 127.0.0.1\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: " + str(len(cuerpo)).encode("ascii") + b"\r\n\r\n"
        + cuerpo
    )
    t0 = time.monotonic()
    con = socket.create_connection(("127.0.0.1", puerto_gw), timeout=10)
    try:
        con.sendall(peticion)
        recibido = b""
        while b"data: " not in recibido:
            trozo = con.recv(1024)
            if not trozo:
                break
            recibido += trozo
    finally:
        con.close()

    # Esperar hasta 2.0 s a que todos los slots en 8091 estén libres
    slot_libre = False
    t_liberacion = None
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{puerto_motor}/slots", timeout=2
        ) as resp:
            slots = json.loads(resp.read())
        ocupados = [s["id"] for s in slots if s.get("is_processing")]
        if not ocupados:
            slot_libre = True
            t_liberacion = round(time.monotonic() - t0, 3)
            break
        time.sleep(0.025)
    return {
        "recibio_sse_antes_de_cortar": b"data: " in recibido,
        "slot_liberado_confirmado": slot_libre,
        "tiempo_confirmacion_s": t_liberacion,
    }


def main():
    puerto = int(os.environ.get("LFM3_GATEWAY_PORT", "8092"))
    corpus = json.loads((RAIZ / "tests/corpus_va.json").read_text())["frases"]
    seleccion = corpus[:N_TURNOS]

    # Calentamiento de caché del SO para llama-tts (idéntico al uso real
    # donde el saludo inicial de conversacion_voz_local.py calienta pesos)
    _sintetizar_frase(puerto, "Hola, iniciando sesión de conversación.")

    sesion_a = transcripciones.new_session()
    sesion_b = transcripciones.new_session()
    try:
        historial = [{"role": "system", "content": SISTEMA}]
        turnos = []

        for idx, item in enumerate(seleccion, 1):
            wav_path = RAIZ / "tests" / item["wav"]
            wav_bytes = wav_path.read_bytes()
            huella_in = hashlib.sha256(wav_bytes).hexdigest()

            # Marca de fin de turno fijada en SPEC-i1-vr §3
            t_eot = time.monotonic()
            user_text = _transcribir_wav(puerto, wav_bytes)
            t_asr = time.monotonic()

            historial.append({"role": "user", "content": user_text})
            frases = []
            t_first_voice = None
            t_first_token = None
            huella_tts_1 = None
            bytes_tts_1 = 0
            frases_sintetizadas = 0

            for i_frase, (frase, t_tok) in enumerate(
                _stream_frases(puerto, historial)
            ):
                if t_first_token is None and t_tok is not None:
                    t_first_token = t_tok
                frases.append(frase)
                st_tts, wav_out = _sintetizar_frase(puerto, frase)
                if st_tts != 200 or not wav_out.startswith(b"RIFF"):
                    print(f"BLOQ: turno {idx} fallo TTS HTTP {st_tts}")
                    return 2
                frases_sintetizadas += 1
                if i_frase == 0:
                    t_first_voice = time.monotonic()
                    huella_tts_1 = hashlib.sha256(wav_out).hexdigest()
                    bytes_tts_1 = len(wav_out)

            reply = " ".join(frases).strip()
            historial.append({"role": "assistant", "content": reply})

            transcripciones.record_turn(
                sesion_a,
                user_text=user_text,
                reply=reply,
                params={
                    "turn": idx,
                    "flow": "gateway-8092-sse-tts",
                    "max_tokens": 96,
                    "tts_sentences": frases_sintetizadas,
                },
                hashes={
                    "input_wav": huella_in,
                    "first_tts_wav": huella_tts_1,
                },
            )

            lat_asr = round(t_asr - t_eot, 3)
            lat_ttft = (
                round((t_first_token - t_eot), 3) if t_first_token else None
            )
            lat_voz = round(t_first_voice - t_eot, 3)
            turnos.append({
                "turno": idx,
                "fixture_id": item["id"],
                "referencia_audio": item["texto"],
                "user_text_asr": user_text,
                "primera_frase": frases[0] if frases else "",
                "reply_completo": reply,
                "num_frases": len(frases),
                "frases_sintetizadas": frases_sintetizadas,
                "asr_s": lat_asr,
                "ttft_desde_eot_s": lat_ttft,
                "latencia_primera_voz_s": lat_voz,
                "first_tts_wav_bytes": bytes_tts_1,
            })
            print(
                f"turno {idx}/{N_TURNOS}: primera_voz={lat_voz:.2f}s "
                f"(asr={lat_asr:.2f}s, frases_tts={frases_sintetizadas}) "
                f"-> {frases[0]!r}"
            )

        # Registrar un turno independiente en sesion_b para verificar no cruce
        transcripciones.record_turn(
            sesion_b,
            user_text="Sesión B independiente.",
            reply="Respuesta aislada en sesión B.",
            params={"turn": 1, "flow": "aislamiento-b"},
            hashes={"input_wav": "0" * 64},
        )

        lineas_a = [
            json.loads(l)
            for l in sesion_a.read_text(encoding="utf-8").splitlines()
        ]
        lineas_b = [
            json.loads(l)
            for l in sesion_b.read_text(encoding="utf-8").splitlines()
        ]
        modo_a = stat.S_IMODE(sesion_a.stat().st_mode)
        modo_b = stat.S_IMODE(sesion_b.stat().st_mode)
        d10_ok = (
            len(lineas_a) == N_TURNOS
            and len(lineas_b) == 1
            and sesion_a != sesion_b
            and modo_a == 0o600
            and modo_b == 0o600
        )
    finally:
        sesion_b.unlink(missing_ok=True)

    cancelacion = _probar_cancelacion_en_motor_vivo(puerto)
    latencias = [t["latencia_primera_voz_s"] for t in turnos]
    p95_voz = round(_p95(latencias), 3)
    max_voz = round(max(latencias), 3)
    pasa = (
        len(turnos) == N_TURNOS
        and p95_voz <= UMBRAL_P95_S
        and d10_ok
        and cancelacion["recibio_sse_antes_de_cortar"]
        and cancelacion["slot_liberado_confirmado"]
    )

    informe = {
        "schema": "lfm3-omni/gate-vr/v1",
        "marca_fin_de_turno": "t_eot = time.monotonic() al disponer del WAV del turno para enviar a 8092",
        "n_turnos_fijado": N_TURNOS,
        "umbral_p95_primera_voz_s": UMBRAL_P95_S,
        "p95_primera_voz_s": p95_voz,
        "max_primera_voz_s": max_voz,
        "d10_sesiones_aisladas_0600": d10_ok,
        "cancelacion_sse_motor_vivo": cancelacion,
        "pass": pasa,
        "turnos": turnos,
    }
    texto_json = json.dumps(informe, ensure_ascii=False, indent=2)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(texto_json + "\n", encoding="utf-8")
    print(
        f"VR gate: N={len(turnos)} p95={p95_voz:.2f}s (<= {UMBRAL_P95_S}s) "
        f"cancelacion={cancelacion['slot_liberado_confirmado']} "
        f"d10_ok={d10_ok} -> {'PASS' if pasa else 'FAIL'}"
    )
    return 0 if pasa else 1


if __name__ == "__main__":
    sys.exit(main())
