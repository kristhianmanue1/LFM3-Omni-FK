#!/usr/bin/env python3
"""Inventario del artefacto del motor (SPEC I0 §9).

Emite JSON a stdout con ruta, revisión reportada, sha256, bytes y
licencia declarada del binario llama-server, de los pesos GGUF y del
proyector multimodal (mmproj). Falla cerrado (exit 1) si falta un
artefacto esperado; nada se infiere de ausencias.

Uso: python3 scripts/inventario_motor.py
"""

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HUB = Path.home() / ".cache" / "huggingface" / "hub"
SNAPS = HUB / "models--LiquidAI--LFM3-Omni-2B-GGUF" / "snapshots"
MODELO_REV = "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M (rev. de snapshot en caché)"
LICENCIA_PESOS = "LFM Open License v1.0 (LiquidAI/LFM3-Omni-2B-GGUF)"
LICENCIA_MOTOR = "MIT (llama.cpp, Homebrew)"


def _sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _entrada(ruta, rol, revision, licencia):
    return {
        "rol": rol,
        "ruta": str(ruta),
        "bytes": ruta.stat().st_size,
        "sha256": _sha256(ruta),
        "revision_reportada": revision,
        "licencia": licencia,
    }


def _falla(motivo):
    print(json.dumps({"error": motivo}, ensure_ascii=False))
    sys.exit(1)


def main():
    binario = shutil.which("llama-server")
    if not binario:
        _falla("llama-server no está en PATH")
    binario = str(Path(binario).resolve())
    ver = subprocess.run([binario, "--version"], capture_output=True, text=True)
    revision = (ver.stdout + ver.stderr).strip().splitlines()
    revision = revision[0] if revision else "desconocida"

    artefactos = [_entrada(Path(binario), "motor", revision, LICENCIA_MOTOR)]
    ggufs = sorted(SNAPS.glob("*/*.gguf")) if SNAPS.is_dir() else []
    pesos = [g for g in ggufs if "mmproj" not in g.name]
    mmproj = [g for g in ggufs if "mmproj" in g.name]
    if not pesos:
        _falla("no hay pesos GGUF en la caché de Hugging Face")
    if not mmproj:
        _falla("no hay proyector mmproj en la caché de Hugging Face")
    for g in pesos:
        artefactos.append(_entrada(g, "pesos", MODELO_REV, LICENCIA_PESOS))
    for g in mmproj:
        artefactos.append(_entrada(g, "mmproj", MODELO_REV, LICENCIA_PESOS))

    print(json.dumps({
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "motor": {"binario": binario, "revision_reportada": revision},
        "artefactos": artefactos,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
