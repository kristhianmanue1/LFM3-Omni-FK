#!/usr/bin/env python3
"""Medición del gate CER de I1-VA (SPEC-i1-va §3) contra el gateway
con motor vivo. Corpus y umbral declarados ANTES de medir en
tests/corpus_va.json; nada se decide aquí.

Uso: python3.12 tests/medir_cer_va.py [salida.json]
Requiere el motor en 8091 y el gateway en 8092 (LFM3_GATEWAY_PORT).
"""

import base64
import json
import os
import statistics
import sys
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CORPUS = RAIZ / "tests/corpus_va.json"
PUNTUACION = str.maketrans("", "", "¿?¡!.,;:\"'()[]«»")


def normalizar(texto):
    """Normalización declarada en el corpus: minúsculas, sin los signos
    listados, espacios colapsados y sin bordes."""
    limpio = " ".join(texto.lower().translate(PUNTUACION).split())
    return limpio


def _levenshtein(a, b):
    if len(a) < len(b):
        a, b = b, a
    previo = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        actual = [i]
        for j, cb in enumerate(b, 1):
            actual.append(min(previo[j] + 1, actual[j - 1] + 1,
                              previo[j - 1] + (ca != cb)))
        previo = actual
    return previo[-1]


def cer(prediccion, referencia):
    """CER por carácter sobre la longitud de referencia (0 si ambas
    vacías). Declarado en corpus.json §metodo."""
    p, r = normalizar(prediccion), normalizar(referencia)
    if not p and not r:
        return 0.0
    if not r:
        return 1.0
    return _levenshtein(p, r) / len(r)


def _chat(puerto, payload, timeout=120):
    req = urllib.request.Request(
        f"http://127.0.0.1:{puerto}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def main():
    manifiesto = json.loads(CORPUS.read_text(encoding="utf-8"))
    puerto = int(os.environ.get("LFM3_GATEWAY_PORT", "8092"))
    resultados = []
    for item in manifiesto["frases"]:
        wav = (RAIZ / "tests" / item["wav"]).read_bytes()
        estado, cuerpo = _chat(puerto, {
            "messages": [{"role": "user", "content": [
                {"type": "input_audio",
                 "input_audio": {"data": base64.b64encode(wav).decode(),
                                 "format": "wav"}},
                {"type": "text",
                 "text": "Transcribe exactamente el audio, sin comentarios."}]}],
            "max_tokens": 200, "temperature": 0})
        if estado != 200:
            print(f"BLOQ: {item['id']} -> HTTP {estado} {cuerpo}")
            return 2
        texto = cuerpo["choices"][0]["message"]["content"]
        resultados.append({"id": item["id"], "referencia": item["texto"],
                           "prediccion": texto, "cer": cer(texto, item["texto"])})
    valores = [r["cer"] for r in resultados]
    mediana = statistics.median(valores)
    peor = max(valores)
    # Criterio declarado en corpus.json ANTES de medir (no ajustable aquí)
    umbral_mediana = manifiesto["metodo"]["umbral_mediana"]
    umbral_caso = manifiesto["metodo"]["umbral_caso"]
    passe = mediana <= umbral_mediana and peor <= umbral_caso
    informe = {"criterio_pass": manifiesto["metodo"]["criterio_pass"],
               "mediana": mediana, "peor": peor, "pass": passe,
               "casos": resultados}
    for r in resultados:
        print(f"{r['id']}: CER {r['cer']:.3f} — {r['prediccion'][:60]!r}")
    print(f"mediana={mediana:.3f} peor={peor:.3f} "
          f"criterio={manifiesto['metodo']['criterio_pass']} -> "
          f"{'PASS' if passe else 'FAIL'}")
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(
            json.dumps(informe, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
    return 0 if passe else 1


if __name__ == "__main__":
    sys.exit(main())
