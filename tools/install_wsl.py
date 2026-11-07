#!/usr/bin/env python3
"""Instalación WSL fijada por SPEC-wsl-install; Python stdlib 3.12+."""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "run/build/wsl"
PIN_FILE = ROOT / "run/wsl-artifacts.json"
MODEL_ID = "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M"


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def require_hash(path, expected):
    if sha256(path) != expected:
        raise ValueError(f"SHA-256 incorrecto: {path}")


def download(url, destination, expected):
    if destination.exists():
        require_hash(destination, expected)
        return
    # El lock de instalación protege el nombre final; el temporal es único.
    fd, name = tempfile.mkstemp(dir=destination.parent, prefix=".download-")
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as output:
            with urllib.request.urlopen(url, timeout=60) as source:
                shutil.copyfileobj(source, output, 1024 * 1024)
        require_hash(temporary, expected)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def extract(archive, destination):
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive, "r:gz") as source:
        for member in source.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"ruta de tar no admitida: {member.name}")
        source.extractall(destination, filter="data")


def inventory(root):
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() and not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"enlace fuera del runtime: {path}")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = sha256(path)
    return files


def verify_inventory(root, expected):
    if not expected or inventory(root) != expected:
        raise ValueError("runtime ausente o distinto del inventario instalado")


@contextmanager
def installation_lock(path):
    with path.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def runtime_env(runtime):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("LLAMA_ARG_") and key != "LD_PRELOAD"}
    env["PATH"] = "/usr/bin:/bin"
    libraries = sorted({str(p.parent) for p in runtime.rglob("*.so*")})
    env["LD_LIBRARY_PATH"] = ":".join(libraries + ["/usr/lib/wsl/lib"])
    return env


def executable(runtime, name):
    paths = [p for p in runtime.rglob(name) if p.is_file()]
    if len(paths) != 1 or not os.access(paths[0], os.X_OK):
        raise ValueError(f"se esperaba un único ejecutable {name} en {runtime}")
    return paths[0]


def verify_version(server, env):
    result = subprocess.run([str(server), "--version"], env=env,
                            capture_output=True, text=True, timeout=30)
    output = result.stdout + result.stderr
    if (result.returncode or "11960" not in output or "8642541b2" not in output):
        raise ValueError(f"versión distinta de b11960/8642541b2: {output.strip()}")
    print(output.strip(), flush=True)


def install(pins):
    BASE.mkdir(parents=True, exist_ok=True)
    with installation_lock(BASE / "install.lock"):
        cache = BASE / "cache"
        cache.mkdir(exist_ok=True)
        for asset in pins["assets"]:
            print(f"Verificando/descargando {asset['name']}", flush=True)
            download(asset["url"], cache / asset["name"], asset["sha256"])
        runtime = BASE / "runtime"
        if not runtime.exists():
            with tempfile.TemporaryDirectory(dir=BASE, prefix=".install-") as tmp:
                stage = Path(tmp) / "runtime"
                stage.mkdir()
                for asset in pins["assets"]:
                    if asset["kind"] == "archive":
                        extract(cache / asset["name"], stage / asset["name"][:-7])
                env = runtime_env(stage)
                verify_version(executable(stage, "llama-server"), env)
                executable(stage, "llama-tts")
                record = {"files": inventory(stage), "pins_sha256": sha256(PIN_FILE)}
                (stage / "installation.json").write_text(json.dumps(record, indent=2))
                stage.rename(runtime)
        verify_installed(pins)
    print("Artefactos instalados. Falta comprobar GPU, salud e inferencia reales.")


def verify_installed(pins):
    runtime = BASE / "runtime"
    record = json.loads((runtime / "installation.json").read_text())
    if record["pins_sha256"] != sha256(PIN_FILE):
        raise ValueError("el inventario pertenece a otra selección de artefactos")
    # El propio registro no puede incluir su hash sin recursión.
    expected = dict(record["files"])
    expected["installation.json"] = sha256(runtime / "installation.json")
    verify_inventory(runtime, expected)
    for asset in pins["assets"]:
        if asset["kind"] == "model":
            require_hash(BASE / "cache" / asset["name"], asset["sha256"])
    server = executable(runtime, "llama-server")
    executable(runtime, "llama-tts")
    env = runtime_env(runtime)
    verify_version(server, env)
    return server, env


def check_environment():
    errors = []
    for host in ("github.com", "huggingface.co"):
        try:
            socket.getaddrinfo(host, 443)
            print(f"DNS OK: {host}")
        except OSError as exc:
            errors.append(f"DNS {host}: {exc}")
    try:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
        print("Sockets loopback: OK")
    except OSError as exc:
        errors.append(f"sockets loopback: {exc}")
    nvidia = shutil.which("nvidia-smi")
    if not nvidia:
        errors.append("nvidia-smi no encontrado")
    else:
        result = subprocess.run([nvidia], capture_output=True, text=True, timeout=15)
        print(result.stdout.strip())
        if result.returncode:
            errors.append("GPU: nvidia-smi no puede acceder a la GPU")
    for name in ("ffmpeg", "ffprobe", "lsof"):
        if not shutil.which(name, path="/usr/bin:/bin"):
            errors.append(f"dependencia no disponible: {name}")
    if errors:
        raise ValueError("; ".join(errors))


def serve(pins):
    server, env = verify_installed(pins)
    devices = subprocess.run([str(server), "--list-devices"], env=env,
                             capture_output=True, text=True, timeout=30)
    if devices.returncode or "CUDA0" not in devices.stdout + devices.stderr:
        raise ValueError("el motor no detecta CUDA0; no se degrada a CPU")
    models = [BASE / "cache" / a["name"] for a in pins["assets"]
              if a["kind"] == "model"]
    model = next(p for p in models if not p.name.startswith("mmproj"))
    projector = next(p for p in models if p.name.startswith("mmproj"))
    print("Motor en primer plano: 127.0.0.1:8091; Ctrl+C para detener.", flush=True)
    os.execve(server, [str(server), "-m", str(model), "--mmproj", str(projector),
                      "--alias", MODEL_ID, "--reasoning", "off", "--temp", "0",
                      "--host", "127.0.0.1", "--port", "8091", "-ngl", "99"], env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true", help="diagnóstico sin instalar")
    modes.add_argument("--serve", action="store_true", help="motor CUDA en primer plano")
    args = parser.parse_args()
    try:
        if sys.version_info < (3, 12) or platform.system() != "Linux" \
                or platform.machine() != "x86_64":
            raise ValueError("requiere Linux x86_64 y Python 3.12+")
        pins = json.loads(PIN_FILE.read_text())
        if args.check:
            check_environment()
        elif args.serve:
            serve(pins)
        else:
            install(pins)
    except (OSError, ValueError, KeyError, tarfile.TarError,
            urllib.error.URLError, subprocess.SubprocessError) as exc:
        print(f"BLOQ: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
