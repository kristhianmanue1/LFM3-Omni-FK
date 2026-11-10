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

import hashlib
import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUN = RAIZ / "run"
# Modelo efectivo registrado en el runbook (run/serve.sh MODELO_ID): el
# mismo id que publica el sustituto del fixture por defecto.
EFFECTIVE_MODEL_ID = "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M"
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

    def wait_for_invocations(self, minimum=1, timeout=10):
        deadline = time.time() + timeout
        while time.time() < deadline and len(self.fx.invocations()) < minimum:
            time.sleep(0.1)
        return self.fx.invocations()

    def wait_for_foreign_service(self, model_id):
        """Espera al servicio ajeno de control: listener VIVO y estado
        HTTP ya publicado. Sin el estado publicado el curl sustituto
        aún rehusaría /health y serve.sh tomaría la rama del puerto
        ocupado en vez de la del modelo (hallazgo HIGH ronda 4: la rama
        probada debe ser la correcta por construcción, no por suerte).
        """
        deadline = time.time() + 5
        while time.time() < deadline and not (
                self.fx.listener_alive(8091)
                and self.fx.http_state(8091) == model_id):
            time.sleep(0.05)
        self.assertTrue(self.fx.listener_alive(8091),
                        "el servicio ajeno de control no arrancó")
        self.assertEqual(self.fx.http_state(8091), model_id,
                         "el servicio ajeno no publicó su modelo efectivo")

    def assert_serve_up(self, process, message="", timeout=120):
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
        self.assertEqual(rc, 0, f"{message}: serve.sh no reportó éxito: "
                                f"{stdout}{stderr}")
        self.assertIn("arriba", stdout, message)
        self.assertTrue(self.fx.listener_alive(8091),
                        f"{message}: no quedó listener vivo del motor")
        return stdout

    def assertLimpio(self):
        self.assertFalse((self.fx.tmp / "serve.lock").exists(),
                         "el cerrojo quedó tras la salida")
        self.assertFalse((self.fx.tmp / "llama-server.pid").exists(),
                         "el pidfile quedó tras un fallo")


class DobleArranque(CicloArranqueBase):
    def test_r13_segundo_arranque_bloquea_con_un_solo_motor(self):
        primero = self.lanzar_serve(STUB_LOAD_SECS="2")
        self.assertTrue(self.wait_for_invocations(),
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
        self.assert_serve_up(p, "un cerrojo huérfano bloqueó el arranque")
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
        self.assert_serve_up(p2, "un pid ajeno vivo del cerrojo bloqueó el "
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
        self.assert_serve_up(p)
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
        adversarial_path = os.pathsep.join(
            [str(veneno), str(self.fx.bin_dir),
             "/usr/bin:/bin:/usr/sbin:/sbin"])
        p = self.lanzar_serve(STUB_LOAD_SECS="0.2", PATH=adversarial_path)
        self.assert_serve_up(p)
        inv = self.fx.invocations()
        self.assertEqual(len(inv), 1)
        path_motor = inv[0]["path"].split(os.pathsep)
        # La lista de directorios de sistema se duplica a propósito: si
        # serve.sh cambia el PATH fijado, este test DEBE romper (alarma),
        # no adaptarse en silencio (I1-V0, ADR-006 §4). La alarma se
        # atendió con registro en ADR-014: /opt/homebrew/bin entra tras
        # el dir del motor para que ffmpeg/ffprobe/llama-tts (fijados
        # por ADR-006 §4) sigan resolviendo junto al binario de fuente.
        self.assertEqual(path_motor[0], str(self.fx.bin_dir),
                         f"el PATH del motor no arranca en el dir del "
                         f"motor: {path_motor}")
        self.assertEqual(path_motor[1:],
                         ["/opt/homebrew/bin", "/usr/bin", "/bin",
                          "/usr/sbin", "/sbin"],
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
        self.wait_for_foreign_service("modelo-equivocado")
        p = self.lanzar_serve()
        rc = p.wait(timeout=60)
        stdout = p.stdout.read()
        stderr = p.stderr.read()
        p.stdout.close()
        p.stderr.close()
        self.assertNotEqual(rc, 0, "el atajo idempotente declaró arriba "
                                   "sin el modelo efectivo")
        self.assertNotIn("arriba", stdout)
        # Hallazgo HIGH ronda 4: exigir el motivo BLOQ exacto prueba que
        # se tomó la rama del modelo equivocado (run/serve.sh:20-31) y
        # no la de puerto ocupado (:36-39), que también haría fallar
        # sin «arriba» y sin lanzar el motor.
        self.assertIn("responde /health pero sin el modelo efectivo",
                      stderr,
                      "el BLOQ llegó por otra rama (esperado el rechazo "
                      f"por modelo efectivo): {stderr}")
        self.assertEqual(len(self.fx.invocations()), 0,
                         "el atajo lanzó un segundo motor")

    def test_r17c_idempotent_shortcut_with_effective_model(self):
        # Control positivo del hallazgo HIGH ronda 4: el atajo
        # idempotente también debe ACEPTAR. Un servicio ajeno que ya
        # sirve el modelo efectivo registrado produce éxito sin lanzar
        # ningún motor.
        foreign = self.fx.launch_foreign(listen=True,
                                         models_id=EFFECTIVE_MODEL_ID)
        self.addCleanup(self.fx.terminate_handle, foreign)
        self.wait_for_foreign_service(EFFECTIVE_MODEL_ID)
        p = self.lanzar_serve()
        rc = p.wait(timeout=60)
        stdout = p.stdout.read()
        stderr = p.stderr.read()
        p.stdout.close()
        p.stderr.close()
        self.assertEqual(rc, 0, "el atajo idempotente rechazó un servicio "
                                 "ya arriba con el modelo efectivo: "
                                 f"{stdout}{stderr}")
        self.assertIn("arriba: /health y modelo efectivo OK", stdout)
        self.assertEqual(len(self.fx.invocations()), 0,
                         "el atajo idempotente lanzó un motor pese al "
                         "servicio ya arriba")


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
        stop_run = self.fx.run_script(self.stop, timeout=60)
        self.assertEqual(stop_run.returncode, 0,
                         stop_run.stderr + stop_run.stdout)
        self.assertIsNone(victima.poll(),
                          "stop.sh mató un proceso ajeno con el patrón en "
                          "el comando")
        self.assertFalse((self.fx.tmp / "llama-server.pid").exists(),
                         "stop.sh no retiró el pidfile ajeno")
        # la regla de propiedad rehusó antes de intentar señal alguna
        self.assertEqual(self.fx.denials(), [])


if __name__ == "__main__":
    unittest.main()


class EscaleraMotor(CicloArranqueBase):
    """Selección de motor por pierna (ADR-014; ronda adversarial
    2026-11-10): override explícito, binario hermano del repo, legado
    con AVISO y guard de hash en las piernas fijadas. La salida
    observable es la línea «arriba: ... motor: <ruta>» que serve.sh
    imprime con el binario resuelto."""

    def _stub_sha(self):
        stub = self.fx.bin_dir / "llama-server"
        return hashlib.sha256(stub.read_bytes()).hexdigest()

    def _lanzar(self, script, **extra):
        process = self.fx.popen_script(script, **extra)
        self.addCleanup(self.fx.terminate_handle, process)
        return process

    def test_leg1_override_explicito_se_respeta(self):
        stub = self.fx.bin_dir / "llama-server"
        p = self.lanzar_serve(LFM3_MOTOR_BIN=str(stub),
                              LFM3_MOTOR_SHA_REGISTRADO=self._stub_sha(),
                              STUB_LOAD_SECS="0.2")
        out = self.assert_serve_up(p, "override LFM3_MOTOR_BIN ignorado")
        self.assertIn(f"motor: {stub}", out,
                      "la línea arriba no nombra el binario resuelto")

    def test_leg2_hermano_del_repo_se_resuelve(self):
        stub = self.fx.bin_dir / "llama-server"
        raiz = self.fx.tmp / "externos"
        (raiz / "LFM3-Omni" / "run").mkdir(parents=True)
        candidato = (raiz / "llamacpp-candidate-31689" / "src" /
                     "build" / "bin")
        candidato.mkdir(parents=True)
        (candidato / "llama-server").write_bytes(stub.read_bytes())
        (candidato / "llama-server").chmod(0o755)
        serve = raiz / "LFM3-Omni" / "run" / "serve.sh"
        shutil.copy2(RUN / "serve.sh", serve)
        esperado = candidato / "llama-server"
        p = self._lanzar(serve,
                         LFM3_MOTOR_SHA_REGISTRADO=self._stub_sha(),
                         STUB_LOAD_SECS="0.2")
        out = self.assert_serve_up(p, "la pierna 2 no resolvió el "
                                      "hermano del repo")
        self.assertIn(f"motor: {esperado}", out,
                      "no se lanzó el binario hermano fijado")

    def test_guard_hash_bloquea_binario_distinto(self):
        stub = self.fx.bin_dir / "llama-server"
        p = self.lanzar_serve(LFM3_MOTOR_BIN=str(stub),
                              STUB_LOAD_SECS="0.2")
        rc = p.wait(timeout=120)
        stdout = p.stdout.read()
        stderr = p.stderr.read()
        p.stdout.close()
        p.stderr.close()
        self.assertNotEqual(rc, 0,
                            "el guard de hash dejó pasar un binario "
                            f"no registrado: {stdout}{stderr}")
        self.assertIn("hash", stderr.lower(),
                      "el BLOQ no menciona el guard de hash")
        self.assertLimpio()

    def test_leg3_legado_arranca_con_aviso(self):
        # Sin override ni candidato hermano: la pierna 3 toma el
        # llama-server del PATH (sustituto del fixture) y DEBE avisar
        # en stderr que no es el par declarado (HIGH-1, ronda 1).
        p = self.lanzar_serve(STUB_LOAD_SECS="0.2")
        rc = p.wait(timeout=120)
        stdout = p.stdout.read()
        stderr = p.stderr.read()
        p.stdout.close()
        p.stderr.close()
        self.assertEqual(rc, 0,
                         f"pierna 3 legado no arrancó: {stdout}{stderr}")
        self.assertIn("arriba", stdout)
        self.assertIn("motor:", stdout, "falta el binario resuelto")
        self.assertIn("AVISO", stderr,
                      "la pierna 3 legada pasó en silencio")
        self.assertEqual(len(self.fx.invocations()), 1)
