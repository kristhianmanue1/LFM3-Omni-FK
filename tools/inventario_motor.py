#!/usr/bin/env python3
"""Inventario del artefacto del motor (SPEC I0 §9; I1-V0 lo amplía).

Emite JSON a stdout con ruta, revisión reportada, sha256, bytes y
licencia declarada del binario llama-server, de los pesos GGUF, del
proyector multimodal (mmproj) y de las herramientas de ejecución que el
motor o el servicio lanza (ffmpeg, ffprobe, llama-tts). Falla cerrado
(exit 1) si falta un artefacto esperado; nada se infiere de ausencias.

Las herramientas se resuelven con el mismo PATH fijado que run/serve.sh
(I1-V0, ADR-006 §4): directorio del propio motor + directorios del
sistema. El hash registrado es así el del binario que el motor usaría,
no el que el PATH heredado del entorno decidiera.

Uso: python3 tools/inventario_motor.py
"""

import hashlib
import json
import os
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
LICENCIA_FFMPEG = "GPL/LGPL según build (FFmpeg, Homebrew)"
PATH_SISTEMA = "/usr/bin:/bin:/usr/sbin:/sbin"

# (nombre, argv de versión, rol, licencia) — I1-V0, ADR-006 §4/ADR-007.
HERRAMIENTAS = [
    ("ffmpeg", ["-version"], "ffmpeg", LICENCIA_FFMPEG),
    ("ffprobe", ["-version"], "ffprobe", LICENCIA_FFMPEG),
    ("llama-tts", ["--version"], "tts", LICENCIA_MOTOR),
]


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


def _version(ruta, argv_ver):
    ver = subprocess.run([str(ruta)] + argv_ver, capture_output=True, text=True)
    lineas = (ver.stdout + ver.stderr).strip().splitlines()
    return lineas[0] if lineas else "desconocida"


def main():
    binario_logico = shutil.which("llama-server")
    if not binario_logico:
        _falla("llama-server no está en PATH")
    binario = str(Path(binario_logico).resolve())
    revision = _version(binario, ["--version"])

    # PATH fijado igual que serve.sh (I1-V0): del directorio lógico donde
    # command -v/which halló el motor (prefix estable, p. ej.
    # /opt/homebrew/bin), no del Cellar versionado ni del entorno heredado.
    path_fijado = str(Path(binario_logico).parent) + os.pathsep + PATH_SISTEMA

    artefactos = [_entrada(Path(binario), "motor", revision, LICENCIA_MOTOR)]
    for nombre, argv_ver, rol, licencia in HERRAMIENTAS:
        ruta = shutil.which(nombre, path=path_fijado)
        if not ruta:
            _falla(f"{nombre} no está en el PATH fijado ({path_fijado})")
        ruta = Path(ruta).resolve()
        artefactos.append(_entrada(ruta, rol, _version(ruta, argv_ver), licencia))

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
        "path_fijado": path_fijado,
        "artefactos": artefactos,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
