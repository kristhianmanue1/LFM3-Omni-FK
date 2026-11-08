#!/usr/bin/env python3
"""Controles de limpieza del fixture de test_11 (intento 2).

Tres caminos de fallo, cada uno con recuento de restos tras la corrida:
A) node ausente (skip antes de cualquier adquisición);
B) error de preparación tras lanzar los sustitutos (copy2 roto);
C) timeout del arranque con motor sustituto ya huérfano
   (STUB_BROKEN=1: nunca registra listener, serve.sh no ve readiness).
Un resto es un directorio i2-parada-* vivo en TMPDIR o un proceso
stub_llama/foreign_llama/gateway_{http,tls} del fixture.
"""

import glob
import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import test_piloto_live_i2 as modulo  # noqa: E402

MARCAS = ("stub_llama.js", "foreign_llama.js",
          "gateway_http.py", "gateway_tls.py")


def restos():
    dirs = sorted(glob.glob(os.path.join(
        os.environ.get("TMPDIR", "/tmp"), "i2-parada-*")))
    ps = subprocess.run(["ps", "-ax", "-o", "pid,command"],
                        capture_output=True, text=True).stdout
    procs = [l for l in ps.splitlines()
             if any(marca in l for marca in MARCAS) and "grep" not in l]
    return dirs, procs


def correr():
    suite = unittest.TestLoader().loadTestsFromName(
        "TestPilotoPrivadoLive.test_11_rollback_parada_limpia", modulo)
    return unittest.TextTestRunner(verbosity=0).run(suite)


def caso_a_node_ausente():
    which_real = shutil.which
    shutil.which = lambda name: None if name == "node" else which_real(name)
    try:
        return correr()
    finally:
        shutil.which = which_real


def caso_b_error_preparacion():
    copy2_real = shutil.copy2

    def copy2_roto(src, dst, *args, **kwargs):
        if str(dst).endswith("stop.sh"):
            raise OSError("control B: fallo de preparación deliberado")
        return copy2_real(src, dst, *args, **kwargs)

    shutil.copy2 = copy2_roto
    try:
        return correr()
    finally:
        shutil.copy2 = copy2_real


def caso_c_timeout_arranque():
    os.environ["STUB_BROKEN"] = "1"
    run_real = subprocess.run

    def run_con_timeout(*args, **kwargs):
        argv = list(args[0]) if args else kwargs.get("args", [])
        if any(str(a).endswith("serve.sh") for a in argv):
            kwargs["timeout"] = 8
        return run_real(*args, **kwargs)

    subprocess.run = run_con_timeout
    try:
        return correr()
    finally:
        subprocess.run = run_real
        del os.environ["STUB_BROKEN"]


def main():
    fallos = 0
    dirs, procs = restos()
    print(f"== línea base: dirs={len(dirs)} procs={len(procs)} ==")
    if dirs or procs:
        print("  avisos:", dirs, procs)
    time.sleep(0.5)

    for nombre, caso, esperado in (
            ("A node ausente", caso_a_node_ausente, "skipped"),
            ("B error de preparación", caso_b_error_preparacion, "errors"),
            ("C timeout de arranque", caso_c_timeout_arranque, "errors")):
        res = caso()
        time.sleep(0.8)  # margen para centinela y señales
        dirs, procs = restos()
        conteo = (f"skipped={len(res.skipped)} "
                  f"errors={len(res.errors)} failures={len(res.failures)}")
        limpio = not dirs and not procs
        print(f"== caso {nombre} == {conteo} | "
              f"restos: dirs={len(dirs)} procs={len(procs)}")
        if dirs:
            print("   dirs:", dirs)
        if procs:
            print("   procs:", procs)
        if len(getattr(res, esperado)) != 1 or not limpio:
            fallos += 1
            print(f"   FALLO: se esperaba 1 {esperado} y restos cero")

    print("RESULTADO LIMPIEZA:", "OK" if fallos == 0
          else f"FALLO ({fallos} casos)")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
