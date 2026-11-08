#!/usr/bin/env python3
"""Sonda P1 sobre el cuerpo EJECUTADO del test_11 nuevo (intento 2).

Grabador de subprocess.run durante la corrida real de test_11: hoy
nada debe apuntar a run/ del checkout (las invocaciones son copias
temporales). La evidencia sólo vale si el test corrió y pasó; si se
saltó o falló, la sonda aborta con VACUA en vez de certificar una
ausencia sin control positivo.
"""

import subprocess
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]
RUN_CHECKOUT = RAIZ / "run"
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import test_piloto_live_i2 as modulo  # noqa: E402

registradas = []
run_real = subprocess.run


def run_grabador(*args, **kwargs):
    argv = list(args[0]) if args else kwargs.get("args", [])
    registradas.append(argv)
    if any(str(a).startswith(str(RUN_CHECKOUT)) for a in argv):
        raise SystemExit(f"VIOLA P1 (no ejecutar): {argv}")
    return run_real(*args, **kwargs)


subprocess.run = run_grabador

print("== P1 intento 2: test_11 con subprocess.run grabado ==")
suite = unittest.TestLoader().loadTestsFromName(
    "TestPilotoPrivadoLive.test_11_rollback_parada_limpia", modulo)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)

subprocess.run = run_real

print("\n== invocaciones subprocess.run registradas ==")
for argv in registradas:
    print("  ", argv)

hubo_serve = any(Path(str(a)).name == "serve.sh"
                 for argv in registradas for a in argv)
hubo_stop = any(Path(str(a)).name == "stop.sh"
                for argv in registradas for a in argv)
violacion = any(str(a).startswith(str(RUN_CHECKOUT))
                for argv in registradas for a in argv)

if resultado.errors or resultado.failures or resultado.skipped:
    print(f"RESULTADO P1: VACUA (errors={len(resultado.errors)} "
          f"failures={len(resultado.failures)} "
          f"skipped={len(resultado.skipped)}): el cuerpo no pasó")
    raise SystemExit(2)

print(f"serve.sh temporal registrada: {hubo_serve}")
print(f"stop.sh temporal registrada: {hubo_stop}")
ok = (not violacion) and hubo_serve and hubo_stop
print("RESULTADO P1:",
      "no violada (cuerpo ejecutado, copias temporales)" if ok
      else "VIOLADA")
raise SystemExit(0 if ok else 1)
