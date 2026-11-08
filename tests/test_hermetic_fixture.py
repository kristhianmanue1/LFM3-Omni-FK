"""Controles deterministas del fixture hermético (fix-tests-hermeticos,
intento 3).

Fija las dos propiedades que cierran los BLOCKER de la ronda 2: el
entorno de las copias de run/ es explícito y mínimo (sin herencia del
host, sin funciones Bash exportadas, con el lsof del fixture por
precedencia) y el kill vigilado sólo señala PIDs inscritos con hora de
inicio vigente: un PID ajeno, o uno inscrito con hora falsa (reciclado),
recibe una negativa registrada y sobrevive.
"""

from __future__ import annotations

import subprocess
import sys
import time
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tests.hermetic_fixture import HermeticFixture  # noqa: E402


class HermeticEnvironment(unittest.TestCase):
    """El entorno de las copias: explícito, mínimo y con kill vigilado."""

    def setUp(self):
        self.fx = HermeticFixture(prefix="hermetic-env-")
        self.fx.register_cleanup(self)

    def bash(self, code):
        return subprocess.run(
            ["/bin/bash", "--noprofile", "--norc", "-c", code],
            env=self.fx.env(), capture_output=True, text=True)

    def test_minimal_env_sin_herencia_del_host(self):
        out = self.bash("env")
        self.assertEqual(out.returncode, 0, out.stderr)
        seen = {}
        for line in out.stdout.splitlines():
            key, _, value = line.partition("=")
            seen[key] = value
        expected = {
            "PATH": f"{self.fx.bin_dir}:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(self.fx.tmp),
            "TMPDIR": str(self.fx.tmp),
            "STUB_DIR": str(self.fx.tmp),
            "LANG": "C",
            "BASH_ENV": str(self.fx.tmp / "fixture_env.sh"),
        }
        for key, value in expected.items():
            self.assertEqual(seen.get(key), value,
                             f"la clave base {key} llegó alterada")
        # bash añade en runtime PWD, SHLVL y _ (último comando): lo único
        # admitido fuera de la base explícita del fixture
        extra = sorted(set(seen) - set(expected))
        self.assertEqual(extra, ["PWD", "SHLVL", "_"],
                         "el entorno heredó variables del host")
        inherited = [key for key in seen if key.startswith("BASH_FUNC_")]
        self.assertEqual(inherited, [],
                         "funciones Bash exportadas del host en el entorno")

    def test_precedencia_del_lsof_del_fixture(self):
        # Control positivo de precedencia (hallazgo 1 de la ronda 2): en
        # el entorno hermético «lsof» resuelve al ejecutable del fixture,
        # no a una función ni a un binario del host.
        out = self.bash("type lsof")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn(f"{self.fx.bin_dir}/lsof", out.stdout)
        self.assertNotIn("function", out.stdout)

    def test_kill_vigilado_definido_por_el_fixture(self):
        out = self.bash("type kill")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("is a function", out.stdout,
                      "el kill vigilado no quedó definido vía BASH_ENV")


class KillGuard(unittest.TestCase):
    """El kill vigilado: el dueño inscrito pasa; ajeno y reciclado no."""

    def setUp(self):
        self.fx = HermeticFixture(prefix="hermetic-kill-")
        self.fx.register_cleanup(self)

    def sleeper(self):
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.fx.terminate_handle, process)
        return process

    def guarded_kill(self, pid):
        return subprocess.run(
            ["/bin/bash", "--noprofile", "--norc", "-c", f"kill {pid}"],
            env=self.fx.env(), capture_output=True, text=True)

    def assert_denial(self, pid, reason):
        self.assertTrue(
            any(f"pid={pid} " in line and reason in line
                for line in self.fx.denials()),
            f"la negativa ({reason}) no quedó registrada: "
            f"{self.fx.denials()}")

    def test_kill_permite_proceso_inscrito(self):
        process = self.sleeper()
        self.fx.own(process)
        out = self.guarded_kill(process.pid)
        self.assertEqual(out.returncode, 0, out.stderr)
        deadline = time.time() + 5
        while time.time() < deadline and process.poll() is None:
            time.sleep(0.05)
        self.assertIsNotNone(process.poll(),
                             "el kill vigilado no terminó al inscrito")
        self.assertEqual(self.fx.denials(), [])

    def test_kill_niega_pid_no_inscrito(self):
        process = self.sleeper()
        out = self.guarded_kill(process.pid)
        self.assertEqual(out.returncode, 1)
        self.assertIsNone(process.poll(),
                          "el kill vigilado señaló un PID ajeno al fixture")
        self.assert_denial(process.pid, "reason=not-registered")

    def test_kill_niega_pid_reciclado(self):
        # Control del mandato-intento-3: PID inscrito con una hora de
        # inicio falsa (la de un proceso anterior que recicló el PID): el
        # kill vigilado debe negarse y el proceso actual sobrevivir.
        process = self.sleeper()
        with self.fx.owned_pids_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{process.pid} Mon Jan  1 00:00:00 2000\n")
        out = self.guarded_kill(process.pid)
        self.assertEqual(out.returncode, 1)
        self.assertIsNone(process.poll(),
                          "el kill vigilado señaló un PID reciclado")
        self.assert_denial(process.pid, "reason=start-time-mismatch")


if __name__ == "__main__":
    unittest.main()
