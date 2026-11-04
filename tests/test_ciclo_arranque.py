"""Pruebas del ciclo de arranque (run/serve.sh, run/stop.sh) con motor
sustituto en PATH — SPEC I0 §7. Propiedades: doble arranque, cerrojo
con dueño vivo / huérfano / pid reciclado, puerto ajeno, entorno
adversario, readiness de modelo efectivo y parada sin matar ajenos.

Los fixtures no asumen el puerto libre: si 8091 está ocupado al
iniciar, la prueba se salta con motivo (no hay que asumir puerto
libre, guía PLAN LFM3-2)."""

import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUN = RAIZ / "run"
PUERTO = 8091
MODELO = "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M"
MARCADOR = "stub-invocaciones.log"

STUB = f"""#!/usr/bin/env python3
import json, os, socket, sys, time
marca = os.environ["STUB_DIR"] + "/{MARCADOR}"
with open(marca, "a") as f:
    f.write(json.dumps({{"pid": os.getpid(), "argv": sys.argv,
                          "env": sorted(k for k in os.environ
                                        if k.startswith("LLAMA_ARG_"))}}) + "\\n")
time.sleep(float(os.environ.get("STUB_LOAD_SECS", "0.5")))
servidor = socket.socket()
servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    servidor.bind(("127.0.0.1", {PUERTO}))
except OSError:
    sys.exit(3)
servidor.listen(8)
with open(os.environ["STUB_DIR"] + "/stub.pid", "w") as f:
    f.write(str(os.getpid()))
modelos = os.environ.get("STUB_MODELS_ID", "{MODELO}")
def responder():
    with servidor.accept()[0] as c:
        datos = c.recv(65536).decode("latin-1")
        ruta = datos.split(" ")[1] if " " in datos else "/"
        if ruta == "/health":
            cuerpo = b'{{"status":"ok"}}'
        elif ruta == "/v1/models":
            cuerpo = json.dumps({{"data": [{{"id": modelos}}]}}).encode()
        else:
            cuerpo = b'{{}}'
        c.sendall(b"HTTP/1.1 200 OK\\r\\nContent-Type: application/json\\r\\n"
                  + b"Content-Length: " + str(len(cuerpo)).encode() + b"\\r\\n"
                  + b"Connection: close\\r\\n\\r\\n" + cuerpo)
while True:
    responder()
"""


def puerto_libre():
    s = socket.socket()
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", PUERTO))
        return True
    except OSError:
        return False
    finally:
        s.close()


def salud_disponible(timeout=30):
    fin = time.time() + timeout
    while time.time() < fin:
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{PUERTO}/health", timeout=2) as r:
                if json.loads(r.read()).get("status") == "ok":
                    return True
        except Exception:
            time.sleep(0.3)
    return False


class CicloArranqueBase(unittest.TestCase):
    def setUp(self):
        if not puerto_libre():
            self.skipTest(f"puerto {PUERTO} ocupado; el fixture no asume puerto libre")
        self.tmp = Path(tempfile.mkdtemp(prefix="i0-ciclo-"))
        self.bin_dir = self.tmp / "bin"
        self.bin_dir.mkdir()
        self.stub_path = self.bin_dir / "llama-server"
        self.stub_path.write_text(STUB)
        self.stub_path.chmod(0o755)
        self.serve = self.tmp / "serve.sh"
        self.stop = self.tmp / "stop.sh"
        shutil.copy2(RUN / "serve.sh", self.serve)
        shutil.copy2(RUN / "stop.sh", self.stop)
        self.procesos = []

    def tearDown(self):
        self._matar_todo()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def entorno(self, **extra):
        env = dict(os.environ)
        env["PATH"] = str(self.bin_dir) + os.pathsep + env["PATH"]
        env["STUB_DIR"] = str(self.tmp)
        env.update(extra)
        return env

    def lanzar_serve(self, **extra):
        p = subprocess.Popen(["/bin/bash", str(self.serve)], env=self.entorno(**extra),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, start_new_session=True)
        self.procesos.append(p)
        return p

    def invocaciones_stub(self):
        f = self.tmp / MARCADOR
        if not f.exists():
            return []
        return [json.loads(l) for l in f.read_text().splitlines() if l.strip()]

    def _matar_todo(self):
        for p in self.procesos:
            if p.poll() is None:
                try:
                    os.killpg(os.getpgid(p.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            for flujo in (p.stdout, p.stderr):
                if flujo is not None:
                    try:
                        flujo.close()
                    except (OSError, ValueError):
                        pass
        stub_pid = self.tmp / "stub.pid"
        if stub_pid.exists():
            try:
                os.kill(int(stub_pid.read_text()), signal.SIGKILL)
            except (ProcessLookupError, ValueError):
                pass
        # dejar el puerto efectivamente libre para la siguiente prueba
        fin = time.time() + 5
        while time.time() < fin and not puerto_libre():
            time.sleep(0.2)
        if not puerto_libre():
            print(f"\nAVISO fixture: el puerto {PUERTO} sigue ocupado tras la limpieza")

    def assertLimpio(self):
        self.assertFalse((self.tmp / "serve.lock").exists(),
                         "el cerrojo quedó tras la salida")
        self.assertFalse((self.tmp / "llama-server.pid").exists(),
                         "el pidfile quedó tras un fallo")


class DobleArranque(CicloArranqueBase):
    def test_r13_segundo_arranque_bloquea_con_un_solo_motor(self):
        primero = self.lanzar_serve(STUB_LOAD_SECS="3")
        fin = time.time() + 15
        while time.time() < fin and not self.invocaciones_stub():
            time.sleep(0.1)
        self.assertTrue(self.invocaciones_stub(), "el primer motor nunca arrancó")
        segundo = self.lanzar_serve(STUB_LOAD_SECS="0.5")
        rc2 = segundo.wait(timeout=120)
        self.assertTrue(salud_disponible(), "el primer motor no llegó a salud")
        rc1 = primero.wait(timeout=30)
        self.assertEqual(rc1, 0)
        self.assertNotEqual(rc2, 0, "el segundo arranque reportó éxito")
        self.assertEqual(len(self.invocaciones_stub()), 1,
                         "se intentó lanzar un segundo motor: carrera del cerrojo")


class Cerrojo(CicloArranqueBase):
    def test_r14_huerfano_y_pid_reciclado_se_recuperan(self):
        # huérfano: pid muerto
        muerto = subprocess.Popen(["/bin/sh", "-c", "exit 0"])
        muerto.wait()
        (self.tmp / "serve.lock").mkdir()
        (self.tmp / "serve.lock" / "pid").write_text(str(muerto.pid))
        p = self.lanzar_serve()
        self.assertEqual(p.wait(timeout=180), 0, "un cerrojo huérfano bloqueó el arranque")
        self.assertTrue(salud_disponible())
        # parar el motor del primer escenario: el segundo debe ejercitar
        # el cerrojo, no el atajo idempotente (health ya responde)
        self._matar_todo()
        # pid reciclado: pid vivo de un proceso ajeno al arranque
        ajeno = subprocess.Popen(["/bin/sh", "-c", "sleep 30"])
        try:
            (self.tmp / "serve.lock").mkdir()
            (self.tmp / "serve.lock" / "pid").write_text(str(ajeno.pid))
            p = self.lanzar_serve()
            self.assertEqual(p.wait(timeout=180), 0,
                             "un pid ajeno vivo del cerrojo bloqueó el arranque")
            self.assertTrue(salud_disponible())
        finally:
            ajeno.terminate()
            ajeno.wait()


class PuertoAjeno(CicloArranqueBase):
    def test_r15_puerto_ocupado_por_ajeno_bloquea_limpio(self):
        ocupante = socket.socket()
        ocupante.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ocupante.bind(("127.0.0.1", PUERTO))
        ocupante.listen(1)
        try:
            p = self.lanzar_serve()
            rc = p.wait(timeout=60)
            self.assertNotEqual(rc, 0)
            self.assertEqual(len(self.invocaciones_stub()), 0,
                             "se lanzó el motor pese a haber un ocupante ajeno")
            self.assertLimpio()
        finally:
            ocupante.close()


class EntornoAdverso(CicloArranqueBase):
    def test_r16_env_neutralizado_y_host_explicito(self):
        p = self.lanzar_serve(LLAMA_ARG_HOST="0.0.0.0", LLAMA_ARG_PORT="8080",
                              STUB_LOAD_SECS="0.5")
        self.assertEqual(p.wait(timeout=180), 0)
        self.assertTrue(salud_disponible())
        inv = self.invocaciones_stub()
        self.assertEqual(len(inv), 1)
        self.assertEqual(inv[0]["env"], [],
                         f"LLAMA_ARG_* llegó al motor: {inv[0]['env']}")
        argv = inv[0]["argv"]
        self.assertIn("--host", argv)
        self.assertEqual(argv[argv.index("--host") + 1], "127.0.0.1",
                         "el host explícito falta o no es loopback")


class Readiness(CicloArranqueBase):
    def test_r17_readiness_exige_modelo_efectivo(self):
        p = self.lanzar_serve(STUB_MODELS_ID="modelo-equivocado",
                              STUB_LOAD_SECS="0.2", LFM3_WAIT_BUDGET="2")
        salida = p.stdout.read() if p.poll() is not None else ""
        rc = p.wait(timeout=60)
        salida += p.stdout.read()
        self.assertNotEqual(rc, 0, "declaró arriba sin el modelo efectivo")
        self.assertNotIn("arriba", salida)

    def test_r17b_atajo_idempotente_exige_modelo(self):
        # Un servicio ajeno (o con modelo equivocado) ya arriba en 8091:
        # el arranque debe BLOQ sin declarar arriba ni lanzar otro motor.
        stub = subprocess.Popen(
            ["/usr/bin/env", "python3", str(self.stub_path)],
            env=self.entorno(STUB_MODELS_ID="modelo-equivocado",
                             STUB_LOAD_SECS="0"),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        self.procesos.append(stub)
        self.assertTrue(salud_disponible(timeout=15))
        p = self.lanzar_serve()
        salida = p.stdout.read() if p.poll() is not None else ""
        rc = p.wait(timeout=60)
        salida += p.stdout.read()
        self.assertNotEqual(rc, 0, "el atajo idempotente declaró arriba "
                                   "sin el modelo efectivo")
        self.assertNotIn("arriba", salida)
        self.assertEqual(len(self.invocaciones_stub()), 1,
                         "el atajo lanzó un segundo motor")


class Parada(CicloArranqueBase):
    def test_r18_stop_no_mata_ajenos(self):
        # Proceso ajeno cuyo argv menciona el patrón del motor: ni el
        # grep del pidfile ni el pkill amplio deben matarlo. Un sh -c
        # con el patrón en comentario no sirve (exec y el patrón
        # desaparece del comando real).
        victima = subprocess.Popen([
            "/usr/bin/python3", "-c",
            "import time; time.sleep(60)",
            "llama-server", "--port", "8091"])
        try:
            self.assertTrue(victima.poll() is None)
            comando = subprocess.run(["ps", "-p", str(victima.pid), "-o", "command="],
                                     capture_output=True, text=True).stdout
            self.assertIn("llama-server --port 8091", comando,
                          "la víctima no presenta el patrón hostil en su comando")
            (self.tmp / "llama-server.pid").write_text(str(victima.pid))
            p = subprocess.run(["/bin/bash", str(self.stop)],
                               env=self.entorno(), capture_output=True, text=True,
                               timeout=60)
            self.assertEqual(p.returncode, 0)
            self.assertIsNone(victima.poll(),
                              "stop.sh mató un proceso ajeno con el patrón en el comando")
        finally:
            if victima.poll() is None:
                victima.terminate()
            victima.wait()


if __name__ == "__main__":
    unittest.main()
