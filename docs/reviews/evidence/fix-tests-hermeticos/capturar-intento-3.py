#!/usr/bin/env python3
"""Envoltorio de captura de evidencia (fix-tests-hermeticos, intento 3).

Registra el estado de listeners (8091/8092/8443) y de procesos del
servicio antes y después de la corrida que se le pase, con la salida
íntegra de la propia corrida en medio y su código de retorno. El estado
usa los comandos del mandato (lsof de listeners y ps de procesos); la
línea del propio grep se excluye del ps para no ensuciar.
"""

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def estado():
    marca = datetime.now().isoformat(timespec="seconds")
    lsof = subprocess.run(
        ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"],
        capture_output=True, text=True).stdout
    listeners = [l for l in lsof.splitlines()
                 if re.search(r":(8091|8092|8443) ", l)]
    ps = subprocess.run(
        ["ps", "-ax", "-o", "pid,command"], capture_output=True,
        text=True).stdout
    procs = [l for l in ps.splitlines()
             if re.search(r"llama-server|gateway_(http|tls)", l)
             and "grep" not in l]
    cuerpo_l = "\n".join(listeners) if listeners else "  (ninguno)"
    cuerpo_p = "\n".join(procs) if procs else "  (ninguno)"
    return (f"== estado {marca} ==\n"
            f"lsof listeners 8091/8092/8443:\n{cuerpo_l}\n"
            f"ps procesos del servicio:\n{cuerpo_p}\n")


def main():
    if len(sys.argv) < 4 or sys.argv[1] != "-o":
        raise SystemExit(
            "uso: capturar-intento-3.py -o ARCHIVO -- COMANDO...")
    salida = Path(sys.argv[2])
    cmd = sys.argv[3:]
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    antes = estado()
    corrida = subprocess.run(cmd, capture_output=True, text=True)
    texto = "\n".join([
        antes,
        "== corrida: " + " ".join(cmd) + " ==",
        corrida.stdout.rstrip("\n"),
        corrida.stderr.rstrip("\n"),
        f"== rc={corrida.returncode} ==",
        estado(),
    ]) + "\n"
    salida.write_text(texto, encoding="utf-8")
    print(texto)
    return corrida.returncode


if __name__ == "__main__":
    raise SystemExit(main())
