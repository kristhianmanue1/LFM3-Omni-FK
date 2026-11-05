#!/usr/bin/env python3
"""Runner del conjunto de referencia (golden set) de LFM3-Omni.

Ejecuta los casos de tests/golden/casos.json contra el motor vivo en
127.0.0.1:8091 y reporta pass / fail / known-fail por caso. Reglas de
06-componentes-con-llm.md: propiedades binarias, umbrales declarados
en el registro, la salida del modelo es dato no confiable.

Salida esperada con el motor vigente: 12 pass, 0 fail. B-T8 (corregido
I1-V0, 2026-11-05): input_audio es aceptado por el build y audio_url
rechazado (audio_url no existe en el formato OpenAI); si alguna de las
dos propiedades deja de cumplirse, el runner la marca FAIL como alarma
de cambio contractual (v2).

Uso: python3 tests/run_golden.py [--rapido]
  --rapido omite B-T5 (throughput, ~90 s) y lo reporta omitido.
"""

import base64
import json
import math
import os
import shutil
import statistics
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CASOS = RAIZ / "tests" / "golden" / "casos.json"
CONTRATO = RAIZ / "docs" / "contracts" / "superficie-inferencia-v1.md"
BASE = "http://127.0.0.1:8091"
MODELO = "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M"
PROMPT_SERIE = "Completa exactamente: 1, 2, 3, 4, 5, 6, 7, 8, 9, ..."


def chat(payload, timeout=120):
    req = urllib.request.Request(
        BASE + "/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def png_rojo():
    ancho = alto = 8
    bruto = b"".join(b"\x00" + b"\xff\x00\x00" * ancho for _ in range(alto))

    def trozo(tipo, datos):
        cuerpo = tipo + datos
        return struct.pack(">I", len(datos)) + cuerpo + struct.pack(">I", zlib.crc32(cuerpo))

    png = (
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
        + trozo(b"IDAT", zlib.compress(bruto))
        + trozo(b"IEND", b"")
    )
    return base64.b64encode(png).decode()


def wav_seno():
    # WAV válido y autónomo: 16 kHz, mono, 16-bit, 0.6 s de seno suave.
    # La propiedad de B-T8 es de aceptación estructural, no de calidad:
    # el CER se mide en I1-VA con corpus y umbral fijados en SPEC.
    sr, dur = 16000, 0.6
    muestras = b"".join(
        struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * t / sr)))
        for t in range(int(sr * dur))
    )
    return (b"RIFF" + struct.pack("<I", 36 + len(muestras)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, sr, sr * 2, 2, 16)
            + b"data" + struct.pack("<I", len(muestras)) + muestras)


def bt1_salud():
    req = urllib.request.Request(BASE + "/health")
    with urllib.request.urlopen(req, timeout=5) as resp:
        cuerpo = json.loads(resp.read())
    return resp.status == 200 and cuerpo.get("status") == "ok"


def bt2_modelo():
    with urllib.request.urlopen(BASE + "/v1/models", timeout=5) as resp:
        ids = [m["id"] for m in json.loads(resp.read())["data"]]
    return ids == [MODELO]


def bt3_esquema():
    estado, cuerpo = chat({
        "messages": [{"role": "user", "content": "Registra a Ana de 34 años según el esquema."}],
        "max_tokens": 48,
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "registro",
            "schema": {"type": "object", "properties": {
                "nombre": {"type": "string"}, "edad": {"type": "integer"}},
                "required": ["nombre", "edad"]}},
    }})
    if estado != 200:
        return False
    try:
        datos = json.loads(cuerpo["choices"][0]["message"]["content"])
    except (json.JSONDecodeError, KeyError):
        return False
    return isinstance(datos.get("nombre"), str) and isinstance(datos.get("edad"), int)


def _serie():
    estado, cuerpo = chat({
        "messages": [{"role": "user", "content": PROMPT_SERIE}],
        "max_tokens": 24,
    })
    return estado, cuerpo["choices"][0]["message"]["content"]


def bt4_determinismo():
    salidas = [_serie()[1] for _ in range(3)]
    return salidas[0] == salidas[1] == salidas[2]


def bt5_throughput():
    picos = []
    for _ in range(3):
        _, cuerpo = chat({
            "messages": [{"role": "user",
                          "content": "Escribe los números del 1 al 40, uno por línea, sin comentarios."}],
            "max_tokens": 64,
        })
        picos.append(cuerpo["timings"]["predicted_per_second"])
        time.sleep(20)
    mediana = statistics.median(picos)
    print(f"    (throughput medido: {picos} -> mediana {mediana:.1f} tok/s)")
    return mediana >= 15


def bt6_tools():
    estado, cuerpo = chat({
        "messages": [{"role": "user", "content": "¿Qué tiempo hace en CDMX? Usa la herramienta get_weather."}],
        "tools": [{"type": "function", "function": {
            "name": "get_weather",
            "description": "Obtiene el clima actual de una ciudad",
            "parameters": {"type": "object",
                           "properties": {"city": {"type": "string"}},
                           "required": ["city"]}}}],
        "tool_choice": "auto",
        "max_tokens": 96,
    })
    llamada = cuerpo["choices"][0]["message"].get("tool_calls")
    if estado != 200 or not llamada:
        return False
    funcion = llamada[0]["function"]
    argumentos = json.loads(funcion["arguments"])
    return funcion["name"] == "get_weather" and isinstance(argumentos.get("city"), str)


def bt7_vision():
    estado, cuerpo = chat({
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + png_rojo()}},
            {"type": "text", "text": "¿De qué color es esta imagen? Responde con una sola palabra."}]}],
        "max_tokens": 32,
    })
    texto = cuerpo["choices"][0]["message"]["content"].lower()
    return estado == 200 and ("rojo" in texto or "red" in texto)


def bt8_audio_entrada():
    # Corregido (I1-V0, 2026-11-05): el build acepta audio en chat por la
    # parte input_audio (formato OpenAI); audio_url no existe en el
    # formato y se rechaza con 400 (sondas P-2/P-4 del ajuste multimodal).
    # El caso original probaba sólo audio_url y documentaba una limitación
    # inexistente. Propiedad estructural; sin medir calidad de ASR.
    b64 = base64.b64encode(wav_seno()).decode()
    estado, cuerpo = chat({
        "messages": [{"role": "user", "content": [
            {"type": "input_audio", "input_audio": {"data": b64, "format": "wav"}},
            {"type": "text", "text": "Transcribe."}]}],
        "max_tokens": 16,
    })
    if estado != 200:
        return False
    contenido = cuerpo["choices"][0]["message"]["content"]
    if not isinstance(contenido, str):
        return False
    estado2, cuerpo2 = chat({
        "messages": [{"role": "user", "content": [
            {"type": "audio_url", "audio_url": {"url": "data:audio/wav;base64," + b64}},
            {"type": "text", "text": "Transcribe."}]}],
        "max_tokens": 16,
    })
    if estado2 != 400:
        return False
    mensaje = (cuerpo2.get("error") or {}).get("message", "")
    return "unsupported content[].type" in mensaje


def bt9_fail_closed():
    req = urllib.request.Request(
        BASE + "/v1/chat/completions", data=b"{invalid",
        headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5)
        return False
    except urllib.error.HTTPError as exc:
        if exc.code != 400:
            return False
        cuerpo = json.loads(exc.read())
        if not isinstance(cuerpo.get("error"), dict):
            return False
    estado, cuerpo = chat({})
    return estado == 400 and isinstance(cuerpo.get("error"), dict)


def _sh(comando):
    """Subproceso de lectura con salida de texto (punto único para tests)."""
    return subprocess.run(comando, capture_output=True, text=True).stdout


def _listener_pids(puerto=8091):
    """PIDs del LISTENER en el puerto, derivados de lsof — no de pgrep
    laxo (SPEC I0 r19)."""
    pids = []
    for linea in _sh(["lsof", "-nP", "-iTCP:%d" % puerto,
                      "-sTCP:LISTEN"]).splitlines():
        if "(LISTEN)" not in linea:
            continue
        partes = linea.split()
        if len(partes) > 1:
            pids.append(partes[1])
    return pids


def _comando_pid(pid):
    return _sh(["ps", "-p", str(pid), "-o", "command="]).strip()


def _swap_mib_usado():
    partes = _sh(["sysctl", "-n", "vm.swapusage"]).split()
    for i, token in enumerate(partes):
        if token == "used" and i + 2 < len(partes):
            valor = partes[i + 2]
            numero = "".join(c for c in valor if c.isdigit() or c == ".")
            if numero:
                return float(numero) * (1024 if valor.endswith("GiB") else 1)
    return float("inf")  # sin dato: falla cerrado (no hay pass a ciegas)


def _artefactos_bytes():
    """Piso de memoria mmapeada: binario + pesos + proyector."""
    total = 0
    binario = shutil.which("llama-server")
    if binario:
        total += os.path.getsize(os.path.realpath(binario))
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    for ruta in hub.glob(
            "models--LiquidAI--LFM3-Omni-2B-GGUF/snapshots/*/*.gguf"):
        total += ruta.stat().st_size
    return total


def bt10_recursos():
    chat({"messages": [{"role": "user",
                        "content": "Escribe los números del 1 al 40, uno por línea."}],
          "max_tokens": 64})
    return _bt10_medir()


def _bt10_medir():
    """Medición pura (tests unitarios la ejercitan sin motor).
    Gate sólo en lo atribuible al proceso (SPEC I0 §8, enmienda): el
    swap de `sysctl` es global del host (footprint per-pid exige root)
    y se REPORTA sin atribuir ni usar como umbral."""
    pids = _listener_pids()
    if len(pids) != 1:
        print(f"    (B-T10: listeners en 8091: {pids or 'ninguno'}; sin pid "
              f"atribuible no hay pass)")
        return False
    pid = pids[0]
    comando = _comando_pid(pid)
    binario = comando.split(" ", 1)[0]
    if os.path.basename(binario) != "llama-server" \
            or "--port 8091" not in comando:
        print(f"    (B-T10: pid {pid} no es del motor: {comando[:60]!r})")
        return False
    rss_salida = _sh(["ps", "-p", str(pid), "-o", "rss="]).strip()
    if not rss_salida or not rss_salida.isdigit():
        print(f"    (B-T10: sin RSS atribuible al pid {pid}; el proceso "
              f"desapareció entre lsof y ps)")
        return False
    rss_kib = int(rss_salida)
    swap_mib = _swap_mib_usado()
    artefactos_mib = _artefactos_bytes() // (1024 * 1024)
    print(f"    (pid {pid}: RSS {rss_kib // 1024} MiB bajo mmap; artefactos "
          f"~{artefactos_mib} MiB; swap del HOST {swap_mib:.0f} MiB — global, "
          f"no atribuible al motor)")
    return rss_kib < 4 * 1024 * 1024


def bt11_licencia():
    texto = CONTRATO.read_text(encoding="utf-8")
    return "REQ-8" in texto and "EV-10" in texto


def bt12_binding():
    salida = subprocess.run(["lsof", "-nP", "-iTCP:8091", "-sTCP:LISTEN"],
                            capture_output=True, text=True).stdout
    lineas = [l for l in salida.splitlines() if "(LISTEN)" in l]
    return bool(lineas) and all("127.0.0.1:8091" in l for l in lineas)


CHECKS = {
    "B-T1": bt1_salud, "B-T2": bt2_modelo, "B-T3": bt3_esquema,
    "B-T4": bt4_determinismo, "B-T5": bt5_throughput, "B-T6": bt6_tools,
    "B-T7": bt7_vision, "B-T8": bt8_audio_entrada, "B-T9": bt9_fail_closed,
    "B-T10": bt10_recursos, "B-T11": bt11_licencia, "B-T12": bt12_binding,
}


def main():
    rapido = "--rapido" in sys.argv
    declarados = json.loads(CASOS.read_text(encoding="utf-8"))["casos"]
    pasan = conocidos = fallan = 0
    for caso in declarados:
        cid = caso["id"]
        if rapido and cid == "B-T5":
            print(f"{cid} omitido — (--rapido)")
            continue
        resultado = CHECKS[cid]()
        if resultado:
            pasan += 1
            print(f"{cid} pass — {caso['titulo']}")
        elif caso.get("documenta_limitacion"):
            fallan += 1
            print(f"{cid} FAIL — {caso['titulo']}: la limitación ya no se sostiene; cambio contractual (v2)")
        else:
            fallan += 1
            print(f"{cid} FAIL — {caso['titulo']}")
    print(f"resumen: {pasan} pass, {fallan} fail")
    return 1 if fallan else 0


if __name__ == "__main__":
    sys.exit(main())
