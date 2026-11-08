"""Pruebas del ciclo de arranque (run/serve.sh, run/stop.sh) con fixture
hermético — SPEC I0 §7, fix-tests-hermeticos intento 3.

Propiedades: doble arranque, cerrojo con dueño vivo / huérfano / pid
reciclado, puerto ajeno, entorno adversario, readiness de modelo efectivo
y parada sin matar ajenos. Ningún proceso enlaza puerto real alguno: los
listeners viven en el registro del fixture (tests/hermetic_fixture.py),
las copias de run/ corren con /bin/bash --noprofile --norc bajo un
entorno explícito mínimo (sin herencia del host) y todo kill queda
vigilado por registro de PIDs propios con hora de inicio.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUN = RAIZ / "run"
sys.path.insert(0, str(RAIZ))

from tests.hermetic_fixture import HermeticFixture  # noqa: E402


class CicloArranqueBase(unittest.TestCase):
    """Copias de run/ ejecutadas sobre el fixture hermético compartido."""

    def setUp(self):
        self.fx = HermeticFixture(prefix="hermetic-ciclo-")
        self.fx.register_cleanup(self)
        self.serve = self.fx.tmp / "serve.sh"
        self.stop = self.fx.tmp / "stop.sh"
        shutil.copy2(RUN / "serve.sh", self.serve)
        shutil.copy2(RUN / "stop.sh", self.stop)

    def lanzar_serve(self, **extra):
        process = self.fx.popen_script(self.serve, **extra)
        self.addCleanup(self.fx.terminate_handle, process)
        return process

    def esperar_invocaciones(self, minimo=1, timeout=10):
        deadline = time.time() + timeout
        while time.time() < deadline and len(self.fx.invocations()) < minimo:
            time.sleep(0.1)
        return self.fx.invocations()

    def assertArriba(self, process, mensaje="", timeout=120):
        """Espera el fin de serve.sh y exige éxito con readiness efectiva.

        La readiness hermética: serve.sh sólo imprime «arriba» tras ver
        /health y /v1/models a través de los sustitutos, y el listener
        del motor queda vivo en el registro del fixture.
        """
        rc = process.wait(timeout=timeout)
        stdout = process.stdout.read()
        stderr = process.stderr.read()
        process.stdout.close()
        process.stderr.close()
        self.assertEqual(rc, 0, f"{mensaje}: serve.sh no reportó éxito: "
                                f"{stdout}{stderr}")
        self.assertIn("arriba", stdout, mensaje)
        self.assertTrue(self.fx.listener_alive(8091),
                        f"{mensaje}: no quedó listener vivo del motor")
        return stdout

    def assertLimpio(self):
        self.assertFalse((self.fx.tmp / "serve.lock").exists(),
                         "el cerrojo quedó tras la salida")
        self.assertFalse((self.fx.tmp / "llama-server.pid").exists(),
                         "el pidfile quedó tras un fallo")


class DobleArranque(CicloArranqueBase):
    def test_r13_segundo_arranque_bloquea_con_un_solo_motor(self):
        primero = self.lanzar_serve(STUB_LOAD_SECS="2")
        self.assertTrue(self.esperar_invocaciones(),
                        "el primer motor nunca arrancó")
        segundo = self.lanzar_serve()
        rc2 = segundo.wait(timeout=120)
        segundo.stdout.close()
        segundo.stderr.close()
        rc1 = primero.wait(timeout=120)
        self.assertEqual(rc1, 0)
        self.assertNotEqual(rc2, 0, "el segundo arranque reportó éxito")
        self.assertEqual(len(self.fx.invocations()), 1,
                         "se intentó lanzar un segundo motor: carrera del "
                         "cerrojo")
        self.assertTrue(self.fx.listener_alive(8091),
                        "el primer motor no llegó a readiness")


class Cerrojo(CicloArranqueBase):
    def test_r14_huerfano_y_pid_reciclado_se_recuperan(self):
        # huérfano: pid muerto en el cerrojo
        muerto = subprocess.Popen(["/bin/sh", "-c", "exit 0"])
        muerto.wait()
        (self.fx.tmp / "serve.lock").mkdir()
        (self.fx.tmp / "serve.lock" / "pid").write_text(str(muerto.pid))
        p = self.lanzar_serve()
        self.assertArriba(p, "un cerrojo huérfano bloqueó el arranque")
        # Parar el servicio del primer escenario: baja del listener en el
        # registro (el servicio deja de responder: el segundo arranque
        # debe ejercitar el cerrojo, no el atajo idempotente) y
        # verificación de que el sustituto salió solo al verse dado de
        # baja. Forma hermética del _matar_todo original: sin señales.
        engine1 = int((self.fx.tmp / "llama-server.pid").read_text())
        self.fx.deregister_listener(8091, engine1)
        deadline = time.time() + 5
        while time.time() < deadline and self.fx.pid_alive(engine1):
            time.sleep(0.1)
        self.assertFalse(self.fx.pid_alive(engine1),
                         f"el motor del primer escenario sigue vivo tras "
                         f"su baja del registro (pid {engine1})")
        # pid reciclado: pid vivo de un proceso ajeno al arranque
        ajeno = subprocess.Popen(["/bin/sh", "-c", "sleep 60"])
        self.addCleanup(self.fx.terminate_handle, ajeno)
        (self.fx.tmp / "serve.lock").mkdir()
        (self.fx.tmp / "serve.lock" / "pid").write_text(str(ajeno.pid))
        p2 = self.lanzar_serve()
        self.assertArriba(p2, "un pid ajeno vivo del cerrojo bloqueó el "
                              "arranque")


class PuertoAjeno(CicloArranqueBase):
    def test_r15_puerto_ocupado_por_ajeno_bloquea_limpio(self):
        # ocupante ajeno: listener en el registro del fixture, sin
        # servicio HTTP y sin inscripción como proceso propio
        ocupante = subprocess.Popen(["/bin/sh", "-c", "sleep 60"])
        self.addCleanup(self.fx.terminate_handle, ocupante)
        self.fx.append_listener(8091, ocupante.pid)
        p = self.lanzar_serve()
        rc = p.wait(timeout=60)
        self.assertNotEqual(rc, 0)
        self.assertEqual(len(self.fx.invocations()), 0,
                         "se lanzó el motor pese a haber un ocupante ajeno")
        self.assertLimpio()


class EntornoAdverso(CicloArranqueBase):
    def test_r16_env_neutralizado_y_host_explicito(self):
        p = self.lanzar_serve(LLAMA_ARG_HOST="0.0.0.0", LLAMA_ARG_PORT="8080",
                              STUB_LOAD_SECS="0.2")
        self.assertArriba(p)
        inv = self.fx.invocations()
        self.assertEqual(len(inv), 1)
        self.assertEqual(inv[0]["env"], [],
                         f"LLAMA_ARG_* llegó al motor: {inv[0]['env']}")
        argv = inv[0]["argv"]
        self.assertIn("--host", argv)
        self.assertEqual(argv[argv.index("--host") + 1], "127.0.0.1",
                         "el host explícito falta o no es loopback")

    def test_r16b_path_fijado_al_lanzar_el_motor(self):
        # I1-V0 (ADR-006 §4): el PATH heredado no decide qué ffmpeg/ffprobe
        # corre junto al motor (libmtmd los lanza desde PATH). El arranque
        # fija PATH a dir del motor + directorios del sistema; un directorio
        # envenenado al frente del PATH heredado no debe llegar al motor.
        veneno = self.fx.tmp / "veneno"
        veneno.mkdir()
        (veneno / "ffmpeg").write_text("#!/bin/sh\nexit 7\n")
        (veneno / "ffmpeg").chmod(0o755)
        adverso = os.pathsep.join([str(veneno), str(self.fx.bin_dir),
                                   "/usr/bin:/bin:/usr/sbin:/sbin"])
        p = self.lanzar_serve(STUB_LOAD_SECS="0.2", PATH=adverso)
        self.assertArriba(p)
        inv = self.fx.invocations()
        self.assertEqual(len(inv), 1)
        path_motor = inv[0]["path"].split(os.pathsep)
        # La lista de directorios de sistema se duplica a propósito: si
        # serve.sh cambia el PATH fijado, este test DEBE romper (alarma),
        # no adaptarse en silencio (I1-V0, ADR-006 §4).
        self.assertEqual(path_motor[0], str(self.fx.bin_dir),
                         f"el PATH del motor no arranca en el dir del "
                         f"motor: {path_motor}")
        self.assertEqual(path_motor[1:],
                         ["/usr/bin", "/bin", "/usr/sbin", "/sbin"],
                         f"el PATH del motor no es el fijado: {path_motor}")
        self.assertNotIn(str(veneno), path_motor,
                         "el directorio envenenado llegó al motor")


class Readiness(CicloArranqueBase):
    def test_r17_readiness_exige_modelo_efectivo(self):
        p = self.lanzar_serve(STUB_MODELS_ID="modelo-equivocado",
                              STUB_LOAD_SECS="0.2", LFM3_WAIT_BUDGET="2")
        rc = p.wait(timeout=60)
        stdout = p.stdout.read()
        p.stdout.close()
        self.assertNotEqual(rc, 0, "declaró arriba sin el modelo efectivo")
        self.assertNotIn("arriba", stdout)
        self.assertLimpio()

    def test_r17b_atajo_idempotente_exige_modelo(self):
        # Un servicio ajeno (o con modelo equivocado) ya arriba en 8091:
        # el arranque debe BLOQ sin declarar arriba ni lanzar otro motor.
        ajeno = self.fx.launch_foreign(listen=True,
                                       models_id="modelo-equivocado")
        self.addCleanup(self.fx.terminate_handle, ajeno)
        deadline = time.time() + 5
        while time.time() < deadline and not self.fx.listener_alive(8091):
            time.sleep(0.05)
        self.assertTrue(self.fx.listener_alive(8091),
                        "el servicio ajeno de control no arrancó")
        p = self.lanzar_serve()
        rc = p.wait(timeout=60)
        stdout = p.stdout.read()
        p.stdout.close()
        self.assertNotEqual(rc, 0, "el atajo idempotente declaró arriba "
                                   "sin el modelo efectivo")
        self.assertNotIn("arriba", stdout)
        self.assertEqual(len(self.fx.invocations()), 0,
                         "el atajo lanzó un segundo motor")


class Parada(CicloArranqueBase):
    def test_r18_stop_no_mata_ajenos(self):
        # Proceso ajeno cuyo comando menciona el patrón del motor pero
        # cuyo binario real es otro: la regla de propiedad de stop.sh
        # (primer token del comando) debe rehusarlo antes de señalar; si
        # alguna día lo intentara, el kill vigilado negaría la señal.
        victima = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)",
             "llama-server", "--port", "8091"])
        self.addCleanup(self.fx.terminate_handle, victima)
        self.assertTrue(victima.poll() is None)
        comando = subprocess.run(
            ["/bin/ps", "-p", str(victima.pid), "-o", "command="],
            capture_output=True, text=True).stdout
        self.assertIn("llama-server --port 8091", comando,
                      "la víctima no presenta el patrón hostil en su "
                      "comando")
        (self.fx.tmp / "llama-server.pid").write_text(str(victima.pid))
        parada = self.fx.run_script(self.stop, timeout=60)
        self.assertEqual(parada.returncode, 0,
                         parada.stderr + parada.stdout)
        self.assertIsNone(victima.poll(),
                          "stop.sh mató un proceso ajeno con el patrón en "
                          "el comando")
        self.assertFalse((self.fx.tmp / "llama-server.pid").exists(),
                         "stop.sh no retiró el pidfile ajeno")
        # la regla de propiedad rehusó antes de intentar señal alguna
        self.assertEqual(self.fx.denials(), [])


if __name__ == "__main__":
    unittest.main()
