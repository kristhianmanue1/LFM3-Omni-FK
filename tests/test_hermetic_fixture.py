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
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

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

    def test_minimal_env_without_host_inheritance(self):
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

    def test_fixture_lsof_precedence(self):
        # Control positivo de precedencia (hallazgo 1 de la ronda 2): en
        # el entorno hermético «lsof» resuelve al ejecutable del fixture,
        # no a una función ni a un binario del host.
        out = self.bash("type lsof")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn(f"{self.fx.bin_dir}/lsof", out.stdout)
        self.assertNotIn("function", out.stdout)

    def test_guarded_kill_defined_by_fixture(self):
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

    def test_kill_allows_registered_process(self):
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

    def test_kill_denies_unregistered_pid(self):
        process = self.sleeper()
        out = self.guarded_kill(process.pid)
        self.assertEqual(out.returncode, 1)
        self.assertIsNone(process.poll(),
                          "el kill vigilado señaló un PID ajeno al fixture")
        self.assert_denial(process.pid, "reason=not-registered")

    def test_kill_denies_recycled_pid(self):
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


class CleanupKeepsSceneForSurvivors(unittest.TestCase):
    """Con supervivientes, la limpieza conserva tmp y centinela.

    Control del hallazgo 2 de la ronda 3: si un proceso propio ignora
    el centinela, el test falla con su PID y la ruta conservada, y el
    directorio y el centinela siguen presentes. El sustituto termina
    al final POR SU HANDLE, nunca por un PID leído de archivo; sólo
    entonces el borrado procede. El caso interior se define DENTRO del
    método para que el cargador de unittest no lo recoja como test
    autónomo (está diseñado para fallar por su limpieza).
    """

    def test_survivor_keeps_tmp_and_sentinel(self):
        class IgnoringSubstituteCase(unittest.TestCase):
            """Un sustituto que ignora el centinela: forma hermética de
            un hijo nacido de serve.sh que no atiende la orden de
            salida (vive sin handle de limpieza propio; el fixture sólo
            puede liberarlo por centinela, que él ignora)."""

            def test_ignores_sentinel(inner):
                inner.fx = HermeticFixture(prefix="hermetic-cleanup-",
                                           verify_timeout=1.0)
                inner.fx.register_cleanup(inner)
                inner.survivor = subprocess.Popen(
                    [sys.executable, "-c", "import time; time.sleep(60)"],
                    env=inner.fx.env(), stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
                inner.fx.own(inner.survivor)
                self.assertTrue(inner.fx.pid_alive(inner.survivor.pid))

        case = IgnoringSubstituteCase("test_ignores_sentinel")
        result = unittest.TestResult()
        case.run(result)
        # red de seguridad del propio control: aunque cualquier aserción
        # de abajo falle, el sustituto termina por handle y la escena se
        # recoge cuando ya sea seguro
        if hasattr(case, "survivor"):
            self.addCleanup(case.fx.final_cleanup)
            self.addCleanup(case.fx.terminate_handle, case.survivor)
        self.assertEqual(len(result.failures), 1,
                         f"el caso interior debió fallar por su limpieza "
                         f"(superviviente vivo): {result.failures}")
        self.assertEqual(len(result.errors), 0, result.errors)
        failure_text = result.failures[0][1]
        self.assertIn(str(case.survivor.pid), failure_text,
                      "el fallo no nombra el PID del superviviente")
        self.assertIn(str(case.fx.tmp), failure_text,
                      "el fallo no nombra la ruta conservada")
        # la escena queda en pie: centinela y directorio presentes
        self.assertTrue(case.fx.sentinel_path.exists(),
                        "el centinela se borró con un superviviente vivo")
        self.assertTrue(case.fx.tmp.exists(),
                        "el tmp se borró con un superviviente vivo")
        # fin del control: el sustituto termina por su handle, nunca por
        # un PID leído de archivo
        case.fx.terminate_handle(case.survivor)
        self.assertIsNotNone(case.survivor.poll(),
                             "el sustituto no terminó por su handle")
        # ya sin supervivientes, el borrado procede (sin ignore_errors)
        case.fx.final_cleanup()
        self.assertFalse(case.fx.tmp.exists(),
                         "el tmp sobrevivió a una limpieza sin riesgos")


class SelfCleaningConstructor(unittest.TestCase):
    """La preparación del fixture se recoge sola si falla a mitad.

    Control del hallazgo MED de la ronda 4: el constructor crea el tmp y
    escribe los sustitutos ANTES de que un caller pueda registrar
    final_cleanup; un fallo durante esa preparación dejaría el tmp
    huérfano. El fixture debe borrarlo y propagar el error original.
    """

    def test_prepare_failure_deletes_tmp_and_propagates(self):
        prefix = "hermetic-selfclean-"
        root = Path(tempfile.gettempdir())
        before = set(root.glob(prefix + "*"))
        with mock.patch.object(
                HermeticFixture, "_write_substitutes",
                side_effect=OSError("fallo inducido en la preparación")):
            with self.assertRaises(OSError):
                HermeticFixture(prefix=prefix)
        leaked = set(root.glob(prefix + "*")) - before
        self.assertEqual(
            leaked, set(),
            f"la preparación fallida filtró su tmp: {leaked}")


if __name__ == "__main__":
    unittest.main()
