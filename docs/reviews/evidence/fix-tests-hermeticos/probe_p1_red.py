#!/usr/bin/env python3
"""Sonda RED para P1 (fix-tests-hermeticos, intento 1).

Demuestra SIN EJECUTAR NADA REAL que test_11 de
tests/test_piloto_live_i2.py invoca los scripts run/ del checkout:
subprocess.run queda parcheado con un grabador; si alguna invocación
apunta dentro de <raíz>/run/, la propiedad P1 está violada hoy.
"""

import subprocess
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]
RUN_CHECKOUT = RAIZ / "run"
sys.path.insert(0, str(RAIZ / "tests"))

import test_piloto_live_i2 as modulo  # noqa: E402


class ResultadoFalso:
    returncode = 0
    stdout = "detenido: sin escucha (grabador, nada ejecutado)"


registradas = []
run_real = subprocess.run


def run_grabador(*args, **kwargs):
    argv = list(args[0]) if args else kwargs.get("args", [])
    registradas.append(argv)
    # Delegar sólo lo que NO apunta a run/ del checkout (p. ej. openssl
    # del fixture, hermético); los scripts del checkout no se ejecutan.
    if any(str(a).startswith(str(RUN_CHECKOUT)) for a in argv):
        return ResultadoFalso()
    return run_real(*args, **kwargs)


subprocess.run = run_grabador

suite = unittest.TestLoader().loadTestsFromName(
    "TestPilotoPrivadoLive.test_11_rollback_parada_limpia", modulo)
print("== P1 RED: test_11 con subprocess.run grabado (nada se ejecuta) ==")
unittest.TextTestRunner(verbosity=2).run(suite)

print("\n== invocaciones subprocess.run registradas ==")
violacion = False
for argv in registradas:
    print("  ", argv)
    for a in argv:
        if str(a).startswith(str(RUN_CHECKOUT)):
            violacion = True
            print(f"    -> VIOLA P1: {a} está dentro de run/ del checkout")
print("RESULTADO P1:",
      "VIOLADA" if violacion else "no violada")
