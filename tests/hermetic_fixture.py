"""Fixture hermético compartido para las pruebas de ciclo y parada
(fix-tests-hermeticos, intento 3).

Materializa el diseño cerrado del Operador (mandato-intento-3):

- entorno explícito mínimo, sin copiar ``os.environ``: nada del host
  (variables ni funciones Bash exportadas) llega a las copias de
  ``run/``; ``BASH_ENV`` apunta al ``fixture_env.sh`` propio;
- ``kill`` vigilado como función Bash: sólo señala PIDs inscritos en
  ``owned_pids`` (una línea «pid hora_de_inicio») cuya hora de inicio
  vigente (``/bin/ps -p PID -o lstart=``) coincida con la inscrita; toda
  negativa queda en ``kill_denied.log`` — un PID ajeno o reciclado jamás
  recibe señal (cierra los dos BLOCKER de la ronda 2). La señal 0 (sonda
  de existencia, no entrega señal) se delega sin registro: serve.sh
  sondea a su hijo recién nacido antes de que el wrapper termine de
  inscribirlo;
- procesos sustitutos sin puertos reales: viven en el registro de
  listeners (``listeners/PUERTO``) que consultan los sustitutos de
  ``lsof`` y ``curl``; el estado HTTP de un puerto (``http_state/PUERTO``
  = id del modelo servido) decide qué responde el ``curl`` sustituto;
- cada proceso del fixture inscribe su nacimiento: el motor sustituto lo
  hace solo (antes del ``exec``, el PID no cambia) y los lanzados por el
  test se inscriben con ``own()`` al obtener su handle;
- identidad de proceso: el motor sustituto se presenta ante ``ps`` como
  ``llama-server`` (argv[0]) vía ``exec -a``. Para eso hace falta node:
  el Python de macOS (build framework) reescribe argv[0] (hallazgo de
  este intento); con ``node_bin=None`` el sustituto corre en Python sin
  identidad — suficiente para los escenarios que no ejecutan stop.sh
  contra el motor;
- limpieza por handle ``Popen`` y por centinela, con verificación: si un
  proceso propio sigue vivo tras el plazo, la prueba FALLA con el PID y
  el motivo; nunca hay señal desde Python a un PID leído de archivo.
  Con supervivientes, el tmp y el centinela quedan conservados para
  diagnóstico (una sola limpieza con ``try/finally``); el borrado del
  tmp ocurre sólo cuando ya es seguro y sin silenciar sus fallos.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


# Entorno que bash carga en cada arranque no interactivo (BASH_ENV): la
# función kill vigilada. Los scripts copiados corren con
# /bin/bash --noprofile --norc, que no desactiva BASH_ENV: la vigilancia
# alcanza a cada bash del fixture, incluidos los propios sustitutos y el
# wrapper del motor.
FIXTURE_ENV = r"""# kill vigilado del fixture hermético (fix-tests-hermeticos i3): sólo
# señala PIDs inscritos en owned_pids cuya hora de inicio vigente
# coincida con la inscrita; toda negativa queda en kill_denied.log.
kill () {
  local sig="-TERM"
  local rc=0
  local pids=()
  local arg pid reg start
  for arg in "$@"; do
    case "$arg" in
      -*) sig="$arg" ;;
      *) pids+=("$arg") ;;
    esac
  done
  if [ "${#pids[@]}" -eq 0 ]; then
    echo "kill: uso: kill [-senal] pid..." >&2
    return 2
  fi
  if [ "$sig" = "-0" ]; then
    # Sonda de existencia (señal 0: no se entrega señal alguna): se
    # delega sin registro. serve.sh sondea a su hijo recién nacido antes
    # de que el wrapper del sustituto termine de inscribirlo en
    # owned_pids; negar el -0 ahí sería una carrera de arranque. Ningún
    # PID puede recibir señal por esta vía.
    builtin kill -0 "${pids[@]}"
    return
  fi
  for pid in "${pids[@]}"; do
    case "$pid" in
      ''|*[!0-9]*)
        echo "kill: pid no valido: $pid" >&2
        rc=1
        continue
        ;;
    esac
    reg="$(/usr/bin/sed -n "s/^$pid //p" "$STUB_DIR/owned_pids" 2>/dev/null | /usr/bin/head -n 1)"
    start="$(/bin/ps -p "$pid" -o lstart= 2>/dev/null | /usr/bin/sed 's/^ *//;s/ *$//')"
    if [ -z "$reg" ]; then
      printf '%s denied pid=%s reason=not-registered signal=%s\n' \
        "$(/bin/date '+%Y-%m-%dT%H:%M:%S')" "$pid" "$sig" \
        >> "$STUB_DIR/kill_denied.log"
      echo "kill: negado: pid $pid no inscrito por el fixture" >&2
      rc=1
      continue
    fi
    if [ "$start" != "$reg" ]; then
      printf '%s denied pid=%s reason=start-time-mismatch registered=[%s] actual=[%s] signal=%s\n' \
        "$(/bin/date '+%Y-%m-%dT%H:%M:%S')" "$pid" "$reg" "$start" "$sig" \
        >> "$STUB_DIR/kill_denied.log"
      echo "kill: negado: pid $pid reciclado (hora de inicio distinta)" >&2
      rc=1
      continue
    fi
  done
  [ "$rc" -eq 0 ] || return 1
  builtin kill "$sig" "${pids[@]}"
}
"""

_LSOF_SUBSTITUTE = r"""#!/bin/bash
# lsof sustituto del fixture hermético: sólo reporta PIDs listados en el
# registro propio (STUB_DIR/listeners/PUERTO) y aún vivos. Un proceso
# ajeno no aparece salvo que el propio test lo inscriba a propósito
# (control positivo del mandato-intento-3). Fiel al lsof real: un
# muerto-sin-recoger (zombie) ya no tiene sockets.
set -u
port=""
pids_only=0
for arg in "$@"; do
  case "$arg" in
    -t) pids_only=1 ;;
    -iTCP:*) port="${arg#-iTCP:}" ;;
  esac
done
[ -n "$port" ] || exit 0
registry="$STUB_DIR/listeners/$port"
[ -f "$registry" ] || exit 0
alive=""
while read -r pid; do
  case "$pid" in
    ""|*[!0-9]*) continue ;;
  esac
  duplicate=0
  for seen in $alive; do
    if [ "$seen" = "$pid" ]; then
      duplicate=1
    fi
  done
  if [ "$duplicate" = 1 ]; then
    continue
  fi
  state="$(/bin/ps -p "$pid" -o stat= 2>/dev/null || true)"
  case "$state" in
    ""|Z*) continue ;;
  esac
  alive="$alive $pid"
done < "$registry"
[ -n "$alive" ] || exit 0
if [ "$pids_only" = 1 ]; then
  for pid in $alive; do
    printf '%s\n' "$pid"
  done
else
  printf 'COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\n'
  for pid in $alive; do
    printf 'fixture-stub %s fixture 6u IPv4 0t0 TCP 127.0.0.1:%s (LISTEN)\n' "$pid" "$port"
  done
fi
exit 0
"""

_CURL_SUBSTITUTE = r"""#!/bin/bash
# curl sustituto del fixture hermético: la «respuesta HTTP» de un puerto
# se decide por el mismo registro que lsof (listeners/PUERTO vivos) más
# el estado del servicio (http_state/PUERTO = id del modelo servido).
# Sin listener vivo: conexión rehusada (exit 7); listener vivo sin
# servicio HTTP (un ocupante ajeno): tampoco hay respuesta útil.
set -u
url=""
for arg in "$@"; do
  case "$arg" in
    http://*) url="$arg" ;;
  esac
done
[ -n "$url" ] || exit 22
rest="${url#http://}"
host_port="${rest%%/*}"
port="${host_port##*:}"
registry="$STUB_DIR/listeners/$port"
[ -f "$registry" ] || exit 7
alive=0
while read -r pid; do
  case "$pid" in
    ""|*[!0-9]*) continue ;;
  esac
  state="$(/bin/ps -p "$pid" -o stat= 2>/dev/null || true)"
  case "$state" in
    ""|Z*) continue ;;
  esac
  alive=1
  break
done < "$registry"
[ "$alive" = 1 ] || exit 7
service="$STUB_DIR/http_state/$port"
[ -f "$service" ] || exit 7
case "$url" in
  */health)
    printf '%s\n' '{"status":"ok"}'
    ;;
  */v1/models)
    printf '{"data":[{"id":"%s"}]}\n' "$(/bin/cat "$service")"
    ;;
  *)
    exit 22
    ;;
esac
"""

# Wrapper del motor: la inscripción del nacimiento ocurre ANTES del exec
# (el PID no cambia) y la identidad argv[0]=llama-server la pone exec -a.
# __TARGET__ se sustituye por el intérprete+stub elegido al construir el
# fixture (node con identidad, python sin ella).
_ENGINE_WRAPPER = r'''#!/bin/bash
# Sustituto del motor (fixture hermético): inscribe su nacimiento en
# owned_pids ANTES del exec (el PID no cambia) y presenta la identidad de
# proceso del motor real (argv[0]=llama-server vía exec -a) para que las
# reglas de propiedad de stop.sh se ejerzan sobre un proceso de verdad.
lstart="$(/bin/ps -p $$ -o lstart= | /usr/bin/sed 's/^ *//;s/ *$//')"
printf '%s %s\n' "$$" "$lstart" >> "$STUB_DIR/owned_pids"
exec -a llama-server __TARGET__ "$@"
'''

_STUB_ENGINE = r'''#!/usr/bin/env python3
# Sustituto del motor (fixture hermético, variante Python sin identidad
# de argv[0]): deja constancia de su invocación (argv, entorno
# LLAMA_ARG_*, PATH), tarda STUB_LOAD_SECS en «cargar» y sólo entonces se
# inscribe como listener 8091 y publica su modelo efectivo
# (STUB_MODELS_ID). Sale solo al ver el centinela o al ser dado de baja
# del registro de listeners (el servicio dejó de escuchar).
import json
import os
import sys
import time

stub_dir = os.environ["STUB_DIR"]
pid = os.getpid()
with open(os.path.join(stub_dir, "invocations.log"), "a") as handle:
    handle.write(json.dumps({
        "pid": pid,
        "argv": sys.argv[1:],
        "env": sorted(k for k in os.environ if k.startswith("LLAMA_ARG_")),
        "path": os.environ.get("PATH", ""),
    }) + "\n")
time.sleep(float(os.environ.get("STUB_LOAD_SECS", "0.2")))
model_id = os.environ.get(
    "STUB_MODELS_ID", "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M")
listener = os.path.join(stub_dir, "listeners", "8091")
with open(listener, "a") as handle:
    handle.write(str(pid) + "\n")
with open(os.path.join(stub_dir, "http_state", "8091"), "w") as handle:
    handle.write(model_id)
sentinel = os.path.join(stub_dir, "shutdown")
while not os.path.exists(sentinel):
    if not any(line.strip() == str(pid) for line in
               open(listener).read().splitlines()):
        break  # baja del registro: el servicio dejó de escuchar
    time.sleep(0.1)
'''

_STUB_ENGINE_JS = r'''// Sustituto del motor (fixture hermético, variante node CON identidad
// de argv[0]: node respeta el exec -a; el Python de macOS lo reescribe).
// Igual que la variante Python: carga (STUB_LOAD_SECS), listener 8091,
// modelo efectivo (STUB_MODELS_ID), salida por centinela o por baja del
// registro de listeners.
const fs = require("fs");
const path = require("path");
const dir = process.env.STUB_DIR;
const pid = String(process.pid);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
(async () => {
  await sleep(parseFloat(process.env.STUB_LOAD_SECS || "0") * 1000);
  const model_id = process.env.STUB_MODELS_ID ||
      "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M";
  const listener = path.join(dir, "listeners", "8091");
  fs.appendFileSync(listener, pid + "\n");
  fs.writeFileSync(path.join(dir, "http_state", "8091"), model_id);
  const sentinel = path.join(dir, "shutdown");
  for (;;) {
    if (fs.existsSync(sentinel)) process.exit(0);
    let lines = "";
    try { lines = fs.readFileSync(listener, "utf8"); } catch (error) {}
    if (!lines.split("\n").includes(pid)) process.exit(0);
    await sleep(100);
  }
})();
'''

_FOREIGN_ENGINE = r'''#!/usr/bin/env python3
# Proceso «ajeno» de control (fixture hermético): simula un servicio
# externo en 8091. NUNCA se inscribe en owned_pids: el kill vigilado debe
# negarse a señalarlo aunque el lsof sustituto lo reporte. Con
# FOREIGN_LISTEN=1 se registra como listener 8091; con FOREIGN_MODELS_ID
# publica ese modelo efectivo (ocupante o servicio equivocado). Vive
# hasta el centinela o hasta que el test lo termine por handle.
import os
import time

stub_dir = os.environ["STUB_DIR"]
pid = os.getpid()
if os.environ.get("FOREIGN_LISTEN") == "1":
    with open(os.path.join(stub_dir, "listeners", "8091"), "a") as handle:
        handle.write(str(pid) + "\n")
model_id = os.environ.get("FOREIGN_MODELS_ID")
if model_id:
    with open(os.path.join(stub_dir, "http_state", "8091"), "w") as handle:
        handle.write(model_id)
while not os.path.exists(os.path.join(stub_dir, "shutdown")):
    time.sleep(0.1)
'''

_FOREIGN_ENGINE_JS = r'''// Proceso «ajeno» de control con identidad de argv[0]=llama-server
// (node): comando que pasa el patrón de stop.sh pero jamás inscrito en
// owned_pids. Vive hasta el centinela o hasta que el test lo termine
// por handle.
const fs = require("fs");
const path = require("path");
const dir = process.env.STUB_DIR;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
(async () => {
  const sentinel = path.join(dir, "shutdown");
  for (;;) {
    if (fs.existsSync(sentinel)) process.exit(0);
    await sleep(100);
  }
})();
'''

_LISTENER_SUBSTITUTE = r'''#!/usr/bin/env python3
# Sustituto de __FILENAME__ (fixture hermético): listener __PORT__ sólo en
# el registro del fixture (STUB_DIR/listeners); sin puertos reales. Vive
# hasta el centinela o hasta que el test lo termine por handle.
import os
import time

stub_dir = os.environ["STUB_DIR"]
listener = os.path.join(stub_dir, "listeners", "__PORT__")
with open(listener, "a") as handle:
    handle.write(str(os.getpid()) + "\n")
sentinel = os.path.join(stub_dir, "shutdown")
while not os.path.exists(sentinel):
    time.sleep(0.1)
'''


class HermeticFixture:
    """Escenario hermético: tmp propio, bin_dir con sustitutos y entorno
    explícito mínimo para ejecutar copias de los scripts de ``run/``.

    Con ``node_bin`` el motor sustituto y el ajeno de control corren bajo
    node y presentan ``argv[0]=llama-server`` ante ``ps`` (identidad que
    exigen las reglas de propiedad de stop.sh); sin él, el motor corre en
    Python sin identidad — válido para escenarios sin stop.sh contra el
    motor.
    """

    def __init__(self, prefix="hermetic-", node_bin=None,
                 verify_timeout=10.0):
        self.tmp = Path(tempfile.mkdtemp(prefix=prefix))
        self.bin_dir = self.tmp / "bin"
        self.listeners_dir = self.tmp / "listeners"
        self.http_state_dir = self.tmp / "http_state"
        for directory in (self.bin_dir, self.listeners_dir,
                          self.http_state_dir):
            directory.mkdir()
        self.owned_pids_path = self.tmp / "owned_pids"
        self.owned_pids_path.write_text("", encoding="utf-8")
        self.kill_denied_path = self.tmp / "kill_denied.log"
        self.sentinel_path = self.tmp / "shutdown"
        self.invocations_path = self.tmp / "invocations.log"
        self.node_bin = node_bin
        # Plazo de stop_and_verify para la salida de los procesos propios
        # tras el centinela (los controles del fixture lo acortan).
        self.verify_timeout = verify_timeout
        self._write_substitutes()

    # -- entorno y ejecución de las copias -----------------------------

    def env(self, **extra):
        """Entorno explícito mínimo; ``extra`` enumera lo que cada test
        necesita además de la base. No se copia ``os.environ``: ninguna
        variable ni función Bash del host puede filtrarse."""
        environment = {
            "PATH": f"{self.bin_dir}:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(self.tmp),
            "TMPDIR": str(self.tmp),
            "STUB_DIR": str(self.tmp),
            "LANG": "C",
            "BASH_ENV": str(self.tmp / "fixture_env.sh"),
        }
        environment.update(extra)
        return environment

    @staticmethod
    def bash_argv(script):
        """Invocación canónica de las copias (mandato-intento-3 §2)."""
        return ["/bin/bash", "--noprofile", "--norc", str(script)]

    def run_script(self, script, timeout=120, **extra):
        return subprocess.run(
            self.bash_argv(script), env=self.env(**extra),
            capture_output=True, text=True, timeout=timeout)

    def popen_script(self, script, **extra):
        return subprocess.Popen(
            self.bash_argv(script), env=self.env(**extra),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=True)

    # -- registro de procesos propios ---------------------------------

    @staticmethod
    def read_start_time(pid):
        out = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "lstart="],
            capture_output=True, text=True,
            env={"LANG": "C"}).stdout
        return out.strip()

    def own(self, process):
        """Inscribe un proceso del fixture (PID + hora de inicio).

        Acepta un ``Popen`` o un PID entero. La hora se lee también con
        ``LANG=C``, igual que la lee el ``kill`` vigilado: la comparación
        es exacta. Un proceso muerto antes de inscribirse es un error del
        fixture, no algo que silenciar.
        """
        pid = process if isinstance(process, int) else process.pid
        start_time = self.read_start_time(pid)
        if not start_time:
            raise RuntimeError(
                f"pid {pid} sin hora de inicio: murió antes de inscribirse")
        with self.owned_pids_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{pid} {start_time}\n")
        return pid

    def owned(self):
        pids = []
        for line in self.owned_pids_path.read_text(
                encoding="utf-8").splitlines():
            fields = line.split(None, 1)
            if fields:
                pids.append(int(fields[0]))
        return pids

    @staticmethod
    def process_state(pid):
        out = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "stat="],
            capture_output=True, text=True).stdout.strip()
        return out

    @classmethod
    def pid_alive(cls, pid):
        """True si el proceso existe y no es zombie: un zombie ya no
        hace nada (no escucha, no responde), sólo espera ser recogido."""
        state = cls.process_state(pid)
        return state != "" and not state.startswith("Z")

    @staticmethod
    def command_of(pid):
        """Línea de comando del proceso según ps (sólo consulta)."""
        return subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "command="],
            capture_output=True, text=True).stdout.strip()

    @classmethod
    def wait_identity(cls, pid, argv0, timeout=5):
        """Espera (acotado) a que el proceso presente argv0 ante ps.

        Un hijo lanzado vía exec -a atraviesa una ventana en la que ps
        aún ve al intérprete del wrapper: la identidad sólo es estable
        cuando el exec ya ocurrió. Devuelve la línea de comando final.
        """
        deadline = time.time() + timeout
        command = cls.command_of(pid)
        while time.time() < deadline and command.split()[:1] != [argv0]:
            time.sleep(0.05)
            command = cls.command_of(pid)
        return command

    # -- registro de listeners y evidencia -----------------------------

    def listener_file(self, port):
        return self.listeners_dir / str(port)

    def append_listener(self, port, pid):
        with self.listener_file(port).open("a", encoding="utf-8") as handle:
            handle.write(f"{pid}\n")

    def deregister_listener(self, port, pid):
        """Da de baja un PID del registro de listeners del puerto.

        El sustituto correspondiente lo notará y saldrá solo (dejar de
        escuchar es morir para el servicio); lsof/curl dejan de verlo de
        inmediato. Ninguna señal interviene.
        """
        registry = self.listener_file(port)
        if not registry.exists():
            return
        lines = registry.read_text(encoding="utf-8").splitlines()
        kept = [line for line in lines if line.strip() != str(pid)]
        registry.write_text("\n".join(kept) + ("\n" if kept else ""),
                            encoding="utf-8")

    def listener_alive(self, port):
        registry = self.listener_file(port)
        if not registry.exists():
            return False
        for line in registry.read_text(encoding="utf-8").splitlines():
            pid = line.strip()
            if pid and self.pid_alive(int(pid)):
                return True
        return False

    def denials(self):
        if not self.kill_denied_path.exists():
            return []
        return [line for line in self.kill_denied_path.read_text(
            encoding="utf-8").splitlines() if line.strip()]

    def invocations(self):
        if not self.invocations_path.exists():
            return []
        lines = self.invocations_path.read_text(
            encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    # -- procesos de control -------------------------------------------

    def launch_foreign(self, listen=False, models_id=None):
        """Lanza un proceso «ajeno» con la identidad del motor (exec -a).

        Jamás se inscribe en ``owned_pids``: simula un servicio externo
        cuyo comando pasa el patrón de ``stop.sh``. Con ``listen=True`` se
        registra como listener 8091; con ``models_id`` publica ese modelo
        efectivo. Bajo node presenta ``argv[0]=llama-server`` (sin node no
        hay identidad: sólo para escenarios sin stop.sh).
        """
        extra = {"FOREIGN_LISTEN": "1" if listen else "0"}
        if models_id is not None:
            extra["FOREIGN_MODELS_ID"] = models_id
        if self.node_bin:
            code = (f'exec -a llama-server "{self.node_bin}" '
                    '"$STUB_DIR/foreign_llama.js" --port 8091')
        else:
            code = ('exec -a llama-server "__PYTHON__" '
                    '"$STUB_DIR/foreign_engine.py" --port 8091').replace(
                        "__PYTHON__", sys.executable)
        return subprocess.Popen(
            ["/bin/bash", "--noprofile", "--norc", "-c", code],
            env=self.env(**extra),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def write_listener_substitute(self, filename, port):
        """Escribe un sustituto de proceso de servicio para stop.sh.

        El nombre del archivo es el que exige el patrón de ``stop.sh``
        (p. ej. ``gateway_http.py``); el proceso se inscribe como listener
        del puerto sólo en el registro del fixture.
        """
        script = _LISTENER_SUBSTITUTE.replace(
            "__FILENAME__", filename).replace("__PORT__", str(port))
        path = self.tmp / filename
        path.write_text(script, encoding="utf-8")
        return path

    # -- limpieza -------------------------------------------------------

    @staticmethod
    def terminate_handle(process):
        """Termina un hijo directo POR SU HANDLE, nunca por PID leído."""
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass

    def _survivors(self):
        alive = []
        for line in self.owned_pids_path.read_text(
                encoding="utf-8").splitlines():
            fields = line.split(None, 1)
            if fields and self.pid_alive(int(fields[0])):
                alive.append(line)
        return alive

    def stop_and_verify(self):
        """Escribe el centinela y EXIGE la salida de todo proceso propio.

        Ninguna señal sale de aquí: los hijos directos ya se terminaron
        por handle en limpiezas previas (LIFO) y los nacidos de serve.sh
        salen solos al ver el centinela. Si algo sigue vivo tras el
        plazo (``verify_timeout``), la prueba FALLA con el PID, su hora
        de inicio inscrita y la ruta del tmp conservado; el centinela
        no se borra nunca antes de confirmar.
        """
        self.sentinel_path.write_text("", encoding="utf-8")
        deadline = time.time() + self.verify_timeout
        survivors = self._survivors()
        while time.time() < deadline and survivors:
            time.sleep(0.1)
            survivors = self._survivors()
        if survivors:
            raise AssertionError(
                "procesos del fixture vivos tras el centinela (pid, hora "
                f"de inicio inscrita): {survivors}; tmp y centinela "
                f"conservados para diagnóstico: {self.tmp}; motivo: un "
                "proceso nacido de serve.sh ignoró el centinela o un "
                "handle propio no se terminó en su limpieza")

    def register_cleanup(self, testcase):
        """Registra la limpieza completa en el TestCase: UNA sola pieza.

        Hallazgo 2 de la ronda 3: con dos limpiezas separadas, un fallo
        de ``stop_and_verify`` no impedía que la limpieza siguiente
        borrara el tmp (y con él el centinela) antes de que los hijos
        pudieran observarlo. Ahora un único cleanup con ``try/finally``
        conserva la escena mientras haya supervivientes y borra sólo
        cuando ya es seguro.
        """
        testcase.addCleanup(self.final_cleanup)

    def final_cleanup(self):
        """Centinela, verificación y borrado del tmp, en una sola pieza.

        Idempotente: si el tmp ya no existe, no hay nada que hacer. El
        borrado ocurre sólo cuando ya es seguro (sin supervivientes) y
        sin ``ignore_errors``: un fallo de borrado se propaga como error
        de limpieza, nunca se silencia.
        """
        if not self.tmp.exists():
            return
        try:
            self.stop_and_verify()
        finally:
            # Con supervivientes el tmp y el centinela se conservan
            # (diagnóstico): el fallo ya viaja en la excepción de
            # stop_and_verify y la escena debe seguir en pie.
            if not self._survivors():
                shutil.rmtree(self.tmp)

    # -- escritura de sustitutos ---------------------------------------

    def _write_substitutes(self):
        (self.bin_dir / "lsof").write_text(_LSOF_SUBSTITUTE,
                                           encoding="utf-8")
        (self.bin_dir / "curl").write_text(_CURL_SUBSTITUTE,
                                           encoding="utf-8")
        if self.node_bin:
            engine_target = f'"{self.node_bin}" "$STUB_DIR/stub_llama.js"'
            (self.tmp / "stub_llama.js").write_text(
                _STUB_ENGINE_JS, encoding="utf-8")
            (self.tmp / "foreign_llama.js").write_text(
                _FOREIGN_ENGINE_JS, encoding="utf-8")
        else:
            engine_target = f'"{sys.executable}" "$STUB_DIR/stub_engine.py"'
            (self.tmp / "stub_engine.py").write_text(
                _STUB_ENGINE, encoding="utf-8")
            (self.tmp / "foreign_engine.py").write_text(
                _FOREIGN_ENGINE, encoding="utf-8")
        (self.bin_dir / "llama-server").write_text(
            _ENGINE_WRAPPER.replace("__TARGET__", engine_target),
            encoding="utf-8")
        for name in ("lsof", "curl", "llama-server"):
            (self.bin_dir / name).chmod(0o755)
        (self.tmp / "fixture_env.sh").write_text(FIXTURE_ENV,
                                                 encoding="utf-8")
