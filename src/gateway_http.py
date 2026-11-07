#!/usr/bin/env python3
"""Gateway HTTP del servicio compartido — transporte loopback
(SPEC I1, ADR-005; ampliado en I1-VA/I1-VS, ADR-006/007). Políticas en
gateway_core; aquí sólo transporte: enrutado con allowlist, límites de
transporte antes de costos (compresión y chunked rechazados sin leer),
proxy al motor v1, validación de salida estructurada y síntesis de voz
local vía llama-tts con exclusión mutua sin cola.

Sin dependencias: stdlib 3.12+. Puerto default 8092
(LFM3_GATEWAY_PORT para tests); colisión → BLOQ + exit 1.
"""

import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.error
import urllib.request

from gateway_core import (
    BACKEND_TIMEOUT_S, CAPABILITIES, DEFAULT_BACKEND, DEFAULT_PORT,
    FFPROBE_SHA256, LLAMA_TTS_SHA256, MAX_BODY_BYTES, MAX_SSE_LINE_BYTES,
    MAX_VIDEO_FPS, MAX_VIDEO_FRAMES, MAX_VIDEO_PIXELES, MAX_VIDEO_SEGUNDOS,
    RUTAS_JOBS, RUTAS_MCP, RUTAS_PERMITIDAS, TTS_TIMEOUT_S, ErrorV2, _error,
    _rechazar_constante, validar_payload, validar_payload_tts, validar_salida,
    validar_wav,
)
from gateway_auth import (
    GLOBAL_DISPATCHER, GLOBAL_REGISTRY, FairQueueDispatcher, TokenRegistry,
)

LOCK_TTS = threading.Lock()
LOCK_STREAM_SLOT = threading.Lock()
_SLOT_PENDIENTE = False
PATH_SISTEMA = "/usr/bin:/bin:/usr/sbin:/sbin"
SNAP_HF = (
    Path.home() / ".cache" / "huggingface" / "hub"
    / "models--LiquidAI--LFM3-Omni-2B-GGUF" / "snapshots"
    / "d508b88f08a5b4286f2d2805a6a8d69a0ff44c72"
)


def _determinar_scopes_chat(payload):
    """Determina los scopes requeridos según la modalidad y esquema del mensaje
    (SPEC-i2-piloto-privado §2.3)."""
    if not isinstance(payload, dict):
        return {"infer:text"}
    scopes = {"infer:text"}
    messages = payload.get("messages", [])
    if isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if isinstance(content, list):
                for parte in content:
                    if isinstance(parte, dict):
                        t = parte.get("type")
                        if t in ("image_url", "video_url"):
                            scopes.add("infer:vision")
                        elif t == "input_audio":
                            scopes.add("infer:audio")
    rf = payload.get("response_format")
    if isinstance(rf, dict) and rf.get("type") == "json_schema":
        js = rf.get("json_schema", {})
        schema = js.get("schema", {}) if isinstance(js, dict) else {}
        props = schema.get("properties", {}) if isinstance(schema, dict) else {}
        name = (js.get("name") or "").lower() if isinstance(js, dict) else ""
        if (
            "proposal" in props
            or {"observation_id", "action"}.issubset(set(props.keys()))
            or name in ("action_proposal", "robot_proposal", "perfil_d")
        ):
            scopes.add("profile:d")
    return scopes


def _enrutar(metodo, ruta):
    """Allowlist ÚNICO de enrutado (SPEC-i1 §2): una ruta sólo responde
    si el par método+ruta está en RUTAS_PERMITIDAS, RUTAS_MCP o RUTAS_JOBS;
    añadir un if/elif sin la tupla queda cortado aquí por diseño."""
    ruta_base = "/jobs" if ruta.startswith("/jobs/") else ruta
    clave = f"{metodo} {ruta_base}"
    if (
        f"{metodo} {ruta}" not in set(RUTAS_PERMITIDAS)
        and f"{metodo} {ruta}" not in set(RUTAS_MCP)
        and clave not in set(RUTAS_JOBS)
    ):
        _error(404, "not_found", "ruta fuera del allowlist")


def _proxy(backend, ruta, cuerpo=None, timeout=BACKEND_TIMEOUT_S):
    req = urllib.request.Request(
        backend + ruta,
        data=cuerpo,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        _error(502, "backend_error", "motor inalcanzable",
               detail="backend_unreachable")


def _esperar_liberacion_slot(backend, timeout=2.0):
    """Tras desconexión o final incompleto de un stream SSE, consulta
    GET /slots del backend hasta confirmar que al menos un slot existe
    y todos reportan is_processing == False (ADR-006 §2, SPEC-i1-vr §2)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                    backend + "/slots", timeout=1.0) as resp:
                slots = json.loads(resp.read())
            if isinstance(slots, list) and len(slots) > 0 and all(
                    isinstance(s, dict)
                    and isinstance(s.get("is_processing"), bool)
                    and s["is_processing"] is False
                    for s in slots):
                return True
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            pass
        time.sleep(0.025)
    return False


def _asegurar_slot_confirmado(backend):
    """Con LOCK_STREAM_SLOT adquirido: si un stream previo terminó sin
    [DONE] y el motor no había confirmado liberación, vuelve a verificar
    /slots y rechaza con 503 overloaded si sigue sin confirmar."""
    global _SLOT_PENDIENTE
    if not _SLOT_PENDIENTE:
        return
    if _esperar_liberacion_slot(backend, timeout=0.5):
        _SLOT_PENDIENTE = False
        return
    _error(503, "overloaded",
           "slot del motor pendiente de confirmación de liberación",
           detail="slot_not_released")


def _sha256_archivo(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _resolver_ffprobe():
    """Resuelve ffprobe con PATH fijado y comprueba hash registrado en
    F0 §7 (SPEC-i1-vv §2)."""
    motor_logico = shutil.which("llama-server") or shutil.which("ffprobe")
    if not motor_logico:
        raise OSError("ffprobe no está en PATH")
    path_fijado = str(Path(motor_logico).parent) + os.pathsep + PATH_SISTEMA
    bin_probe = shutil.which("ffprobe", path=path_fijado)
    if not bin_probe:
        raise OSError("ffprobe no está en el PATH fijado")
    real_probe = Path(bin_probe).resolve()
    if _sha256_archivo(real_probe) != FFPROBE_SHA256:
        raise OSError("hash de ffprobe difiere del inventario congelado")
    return str(real_probe), path_fijado


def _inspeccionar_mp4_ffprobe(datos, probe_runner=None):
    """Inspecciona con ffprobe el contenedor MP4 y valida cotas de
    duración, FPS, frames y resolución antes de llamar al motor
    (SPEC-i1-vv §2)."""
    if probe_runner is not None:
        probe_runner(datos)
        return
    try:
        bin_probe, path_fijado = _resolver_ffprobe()
    except OSError:
        _error(502, "backend_error", "ffprobe alterado o ausente",
               detail="ffmpeg_hash_mismatch")
    dir_tmp = None
    try:
        dir_tmp = tempfile.mkdtemp(prefix="lfm3-probe-")
        os.chmod(dir_tmp, 0o700)
        mp4_path = os.path.join(dir_tmp, "in.mp4")
        fd = os.open(mp4_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(datos)
        cmd = [
            bin_probe, "-v", "error", "-select_streams", "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,nb_frames,duration",
            "-show_entries", "format=duration", "-of", "json", mp4_path,
        ]
        try:
            res = subprocess.run(
                cmd, env={"PATH": path_fijado}, capture_output=True, text=True,
                timeout=15, check=False,
            )
        except (subprocess.SubprocessError, OSError):
            _error(400, "invalid_video",
                   "ffprobe no pudo analizar el video en el tiempo límite")
        if res.returncode != 0:
            _error(400, "invalid_video", "ffprobe no pudo analizar el video")
        try:
            info = json.loads(res.stdout)
        except json.JSONDecodeError:
            _error(400, "invalid_video", "salida de ffprobe ilegible")
        streams = info.get("streams", [])
        if not streams or not isinstance(streams[0], dict):
            _error(400, "invalid_video",
                   "el archivo no contiene stream de video")
        v = streams[0]
        ancho = v.get("width")
        alto = v.get("height")
        if not isinstance(ancho, int) or not isinstance(alto, int) \
                or ancho <= 0 or alto <= 0 \
                or ancho * alto > MAX_VIDEO_PIXELES:
            _error(400, "invalid_video",
                   "resolución de video sobre el presupuesto")
        dur_str = v.get("duration") or info.get("format", {}).get("duration")
        try:
            duracion = float(dur_str) if dur_str else 0.0
        except (ValueError, TypeError):
            duracion = 0.0
        if duracion <= 0.0 or duracion > MAX_VIDEO_SEGUNDOS:
            _error(400, "invalid_video",
                   "video sobre el presupuesto de duración")
        r_fps = v.get("r_frame_rate", "0/1")
        fps = 0.0
        if "/" in str(r_fps):
            num, den = str(r_fps).split("/", 1)
            try:
                fps = float(num) / float(den) if float(den) > 0 else 0.0
            except ValueError:
                pass
        else:
            try:
                fps = float(r_fps)
            except (ValueError, TypeError):
                fps = 0.0
        if fps <= 0.0 or fps > MAX_VIDEO_FPS:
            _error(400, "invalid_video", "video sobre el presupuesto de FPS")
        nb_frames = v.get("nb_frames")
        frames = 0
        if nb_frames and str(nb_frames).isdigit():
            frames = int(nb_frames)
        elif duracion > 0 and fps > 0:
            frames = int(duracion * fps)
        if frames <= 0 or frames > MAX_VIDEO_FRAMES:
            _error(400, "invalid_video",
                   "video sobre el presupuesto de frames")
    finally:
        if dir_tmp is not None:
            shutil.rmtree(dir_tmp, ignore_errors=True)


def _resolver_entorno_tts():
    """Resuelve llama-tts con PATH fijado, comprueba hash registrado en
    F0 §7 y localiza los pesos GGUF y mmproj del snapshot congelado
    (SPEC-i1-vs §2; sin overrides por variables de entorno)."""
    motor_logico = shutil.which("llama-server") or shutil.which("llama-tts")
    if not motor_logico:
        raise OSError("llama-tts no está en PATH")
    path_fijado = str(Path(motor_logico).parent) + os.pathsep + PATH_SISTEMA
    bin_tts = shutil.which("llama-tts", path=path_fijado)
    if not bin_tts:
        raise OSError("llama-tts no está en el PATH fijado")
    real_tts = Path(bin_tts).resolve()
    if _sha256_archivo(real_tts) != LLAMA_TTS_SHA256:
        raise OSError("hash de llama-tts difiere del inventario congelado")
    modelo = SNAP_HF / "LFM3-Omni-2B-Q4_K_M.gguf"
    mmproj = SNAP_HF / "mmproj-LFM3-Omni-2B-Q4_0.gguf"
    if not modelo.is_file() or not mmproj.is_file():
        raise OSError("pesos GGUF o mmproj no encontrados")
    env = {
        k: v for k, v in os.environ.items()
        if not k.startswith("LLAMA_ARG_")
    }
    env["PATH"] = path_fijado
    return str(real_tts), str(modelo), str(mmproj), env


def _ejecutar_tts_real(argv, _prompt_path, _wav_path, env):
    proc = subprocess.run(
        argv, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=TTS_TIMEOUT_S, check=False,
    )
    if proc.returncode != 0:
        raise OSError(f"llama-tts terminó con código {proc.returncode}")


def _sintetizar_wav(texto, runner=None):
    """Ejecuta una síntesis con exclusión mutua sin cola (ADR-007,
    SPEC-i1-vs §2). Texto en archivo 0600 y limpieza garantizada."""
    if not LOCK_TTS.acquire(blocking=False):
        _error(503, "overloaded",
               "síntesis de voz en curso; reintente sin cola")
    dir_tmp = None
    try:
        try:
            dir_tmp = tempfile.mkdtemp(prefix="lfm3-tts-")
            os.chmod(dir_tmp, 0o700)
            prompt_path = os.path.join(dir_tmp, "prompt.txt")
            wav_path = os.path.join(dir_tmp, "out.wav")
            fd = os.open(
                prompt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(texto)
            if runner is not None:
                argv = [
                    "llama-tts", "-m", "modelo.gguf", "-mm", "mmproj.gguf",
                    "--tts-lang", "es", "--no-escape",
                    "-f", prompt_path, "-o", wav_path,
                ]
                runner(argv, prompt_path, wav_path, {"PATH": PATH_SISTEMA})
            else:
                bin_tts, modelo, mmproj, env = _resolver_entorno_tts()
                argv = [
                    bin_tts, "-m", modelo, "-mm", mmproj,
                    "--tts-lang", "es", "--no-escape",
                    "-f", prompt_path, "-o", wav_path,
                ]
                _ejecutar_tts_real(argv, prompt_path, wav_path, env)
            if not os.path.isfile(wav_path):
                raise OSError("llama-tts no produjo archivo WAV")
            datos = Path(wav_path).read_bytes()
        except (OSError, subprocess.SubprocessError):
            _error(502, "backend_error", "fallo en síntesis de voz",
                   detail="tts_failed")
        try:
            validar_wav(datos, exigir_muestras=True)
        except ErrorV2:
            _error(502, "backend_error", "salida WAV de síntesis inválida",
                   detail="invalid_tts_output")
        return datos
    finally:
        if dir_tmp is not None:
            shutil.rmtree(dir_tmp, ignore_errors=True)
        LOCK_TTS.release()


class ManejadorGateway(BaseHTTPRequestHandler):
    server_version = "lfm3-gateway-i1/0.1"

    def _json(self, status, crudo, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(crudo)))
        self.send_header("X-Request-Id", self.request_id)
        self.send_header("X-Service-Contract", "2")
        if getattr(self, "project_id", None):
            self.send_header("X-Project-Id", self.project_id)
        for clave, valor in (headers or {}).items():
            self.send_header(clave, valor)
        self.end_headers()
        self.wfile.write(crudo)

    def _binario(self, status, tipo, datos, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("X-Request-Id", self.request_id)
        self.send_header("X-Service-Contract", "2")
        if getattr(self, "project_id", None):
            self.send_header("X-Project-Id", self.project_id)
        for clave, valor in (headers or {}).items():
            self.send_header(clave, valor)
        self.end_headers()
        self.wfile.write(datos)

    def _cuerpo_error(self, exc):
        crudo = json.dumps(exc.cuerpo(self.request_id)).encode()
        self.close_connection = True
        self.send_response(exc.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(crudo)))
        self.send_header("X-Request-Id", self.request_id)
        self.send_header("X-Service-Contract", "2")
        if getattr(self, "project_id", None):
            self.send_header("X-Project-Id", self.project_id)
        if exc.status == 429 and "retry_after" in exc.extra:
            self.send_header("Retry-After", str(exc.extra["retry_after"]))
        elif exc.status == 401:
            self.send_header("WWW-Authenticate", "Bearer")
        self.end_headers()
        self.wfile.write(crudo)

    def _proxy_sse(self, cuerpo):
        """Stream SSE sin buffering hacia el cliente (SPEC-i1-vr §2,
        ADR-006 §2). Si el cliente se desconecta o el stream no alcanza
        data: [DONE], cierra la conexión con el motor y exige
        confirmación de /slots antes de permitir otra inferencia."""
        global _SLOT_PENDIENTE
        if not LOCK_STREAM_SLOT.acquire(timeout=2.5):
            _error(503, "overloaded",
                   "stream de inferencia en curso; reintente",
                   detail="stream_in_progress")
        try:
            _asegurar_slot_confirmado(self.server.backend)
            req = urllib.request.Request(
                self.server.backend + "/v1/chat/completions",
                data=cuerpo,
                headers={"Content-Type": "application/json"},
            )
            try:
                resp = urllib.request.urlopen(req, timeout=BACKEND_TIMEOUT_S)
            except urllib.error.HTTPError as exc:
                exc.close()
                _error(502, "backend_error", "el motor rechazó la petición",
                       detail=f"backend_status_{exc.code}")
            except (urllib.error.URLError, TimeoutError, OSError):
                _error(502, "backend_error", "motor inalcanzable",
                       detail="backend_unreachable")
            vio_done = False
            try:
                if resp.status != 200:
                    _error(502, "backend_error",
                           "el motor rechazó la petición",
                           detail=f"backend_status_{resp.status}")
                self.close_connection = True
                self.send_response(200)
                self.send_header("Content-Type",
                                 "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Accel-Buffering", "no")
                self.send_header("Connection", "close")
                self.send_header("X-Request-Id", self.request_id)
                self.send_header("X-V2-Mode", "sse-passthrough")
                self.end_headers()
                while True:
                    linea = resp.readline(MAX_SSE_LINE_BYTES + 1)
                    if not linea:
                        break
                    if len(linea) > MAX_SSE_LINE_BYTES:
                        break
                    self.wfile.write(linea)
                    self.wfile.flush()
                    if linea.strip() == b"data: [DONE]":
                        vio_done = True
                        break
            except (BrokenPipeError, ConnectionResetError, OSError,
                    http.client.HTTPException):
                pass
            finally:
                resp.close()
                if not vio_done:
                    _SLOT_PENDIENTE = True
                    if _esperar_liberacion_slot(self.server.backend):
                        _SLOT_PENDIENTE = False
        finally:
            LOCK_STREAM_SLOT.release()

    def _leer_json_post(self):
        """Límites de transporte antes de costo (SPEC-i1 §4): compresión
        y Transfer-Encoding rechazados sin leer; Content-Length <= 32 MiB."""
        if (self.headers.get("Transfer-Encoding") or "").strip():
            _error(400, "payload_too_large",
                   "Transfer-Encoding no admitido",
                   detail="content_length_required")
        codificacion = (self.headers.get("Content-Encoding")
                        or "identity").strip().lower()
        if codificacion not in ("identity", ""):
            _error(400, "payload_too_large",
                   "entrada comprimida no admitida",
                   detail="compressed_input_rejected")
        longitud = self.headers.get("Content-Length")
        if longitud is None or not longitud.isascii() \
                or not longitud.isdigit():
            _error(400, "payload_too_large",
                   "Content-Length requerido (chunked no admitido)",
                   detail="content_length_required")
        if int(longitud) > MAX_BODY_BYTES:
            _error(413, "payload_too_large", "cuerpo sobre el presupuesto")
        crudo = self.rfile.read(int(longitud))
        try:
            return json.loads(crudo, parse_constant=_rechazar_constante)
        except (json.JSONDecodeError, ValueError):
            _error(400, "invalid_json",
                   "JSON malformado o con constantes no-JSON")

    def do_GET(self):
        self.request_id = uuid.uuid4().hex
        self.project_id = None
        try:
            _enrutar("GET", self.path)
            if getattr(self.server, "auth_enabled", False) and self.path != "/healthz":
                auth_h = self.headers.get("Authorization")
                proj_h = self.headers.get("X-Project-ID")
                self.server.tokens_registry.verify_request(auth_h, proj_h, required_scope=None)
                self.project_id = proj_h.strip()
            if self.path == "/healthz":
                self._json(200, b'{"status": "ok", "mode": "gateway-i1"}')
            elif self.path == "/v1/capabilities":
                self._json(200, json.dumps(CAPABILITIES).encode())
            elif self.path == "/v1/models":
                estado, cuerpo = _proxy(self.server.backend, "/v1/models",
                                        timeout=10)
                self._json(estado, cuerpo)
            elif self.path == "/mcp":
                handler = getattr(self.server, "mcp_remote_handler", None)
                if handler is None:
                    _error(501, "not_implemented", "mcp remoto no inicializado")
                handler.handle_get(self)
                return
            elif self.path.startswith("/jobs/"):
                jm = getattr(self.server, "jobs_manager", None)
                if jm is None:
                    _error(501, "not_implemented", "jobs no inicializado")
                proj_id = self.project_id or "default"
                if getattr(self.server, "auth_enabled", False):
                    auth_h = self.headers.get("Authorization")
                    proj_h = self.headers.get("X-Project-ID")
                    self.server.tokens_registry.verify_request(
                        auth_h, proj_h, required_scopes={"jobs:read"}
                    )
                    proj_id = proj_h.strip()
                job_id = self.path[len("/jobs/"):]
                status, res = jm.get_job(proj_id, job_id)
                self._json(status, json.dumps(res).encode())
                return
            else:
                _error(404, "not_found", "ruta fuera del allowlist")
        except ErrorV2 as exc:
            self._cuerpo_error(exc)

    def do_POST(self):
        self.request_id = uuid.uuid4().hex
        self.project_id = None
        slot_adquirido = False
        try:
            _enrutar("POST", self.path)
            # Validación previa de identidad antes de procesar cuerpo (SPEC-i2 §2)
            proj_info = None
            if getattr(self.server, "auth_enabled", False):
                auth_h = self.headers.get("Authorization")
                proj_h = self.headers.get("X-Project-ID")
                proj_info = self.server.tokens_registry.verify_request(
                    auth_h, proj_h, required_scopes=None
                )
                self.project_id = proj_h.strip()

            payload = self._leer_json_post()

            if self.path == "/mcp":
                handler = getattr(self.server, "mcp_remote_handler", None)
                if handler is None:
                    _error(501, "not_implemented", "mcp remoto no inicializado")
                handler.handle_post(self, proj_info, payload=payload)
                return

            if self.path == "/jobs":
                jm = getattr(self.server, "jobs_manager", None)
                if jm is None:
                    _error(501, "not_implemented", "jobs no inicializado")
                idemp_key = self.headers.get("Idempotency-Key") or ""
                proj_id = self.project_id or "default"
                if getattr(self.server, "auth_enabled", False):
                    auth_h = self.headers.get("Authorization")
                    proj_h = self.headers.get("X-Project-ID")
                    self.server.tokens_registry.verify_request(
                        auth_h, proj_h, required_scopes={"jobs:create"}
                    )
                    proj_id = proj_h.strip()
                op = payload.get("operation")
                job_payload = payload.get("payload", {})
                ttl = payload.get("ttl_seconds", 3600)
                status, res = jm.create_job(proj_id, op, job_payload, idemp_key, ttl_seconds=ttl)
                self._json(status, json.dumps(res).encode())
                return

            if getattr(self.server, "auth_enabled", False) and proj_info is not None:
                auth_h = self.headers.get("Authorization")
                proj_h = self.headers.get("X-Project-ID")
                if self.path == "/v1/audio/speech":
                    scopes_req = {"speech:synthesize"}
                else:
                    scopes_req = _determinar_scopes_chat(payload)
                self.server.tokens_registry.verify_request(
                    auth_h, proj_h, required_scopes=scopes_req
                )
                rl_cfg = proj_info.get("rate_limit", {})
                self.server.dispatcher.acquire_slot(self.project_id, rl_cfg)
                slot_adquirido = True
            try:
                if self.path == "/v1/audio/speech":
                    texto = validar_payload_tts(payload)
                    runner = getattr(self.server, "tts_runner", None)
                    wav = _sintetizar_wav(texto, runner=runner)
                    self._binario(200, "audio/wav", wav, {"X-V2-Mode": "tts-wav"})
                    return
                validar_payload(
                    payload,
                    inspector_video=lambda d: _inspeccionar_mp4_ffprobe(
                        d, getattr(self.server, "probe_runner", None)
                    ),
                )
                try:
                    limpio = json.dumps(payload, allow_nan=False)
                except (TypeError, ValueError):
                    _error(400, "invalid_json",
                           "el cuerpo contiene valores no representables en JSON")
                if payload.get("stream") is True:
                    self._proxy_sse(limpio.encode("utf-8"))
                    return
                if not LOCK_STREAM_SLOT.acquire(timeout=2.5):
                    _error(503, "overloaded",
                           "stream de inferencia en curso; reintente",
                           detail="stream_in_progress")
                try:
                    _asegurar_slot_confirmado(self.server.backend)
                finally:
                    LOCK_STREAM_SLOT.release()
                formato = payload.get("response_format")
                estado, cuerpo = _proxy(self.server.backend,
                                        "/v1/chat/completions",
                                        limpio.encode("utf-8"))
                if estado != 200:
                    _error(502, "backend_error", "el motor rechazó la petición",
                           detail=f"backend_status_{estado}")
                if formato is None:
                    self._json(200, cuerpo, {"X-V2-Mode": "passthrough"})
                    return
                schema = formato["json_schema"]["schema"]
                try:
                    respuesta = json.loads(cuerpo,
                                           parse_constant=_rechazar_constante)
                    contenido = respuesta["choices"][0]["message"]["content"]
                except (json.JSONDecodeError, KeyError, IndexError, TypeError,
                        ValueError):
                    _error(502, "backend_error", "respuesta del motor ilegible",
                           detail="backend_shape")
                if not isinstance(contenido, str):
                    _error(502, "backend_error", "respuesta del motor ilegible",
                           detail="backend_shape")
                validar_salida(contenido, schema)
                self._json(200, cuerpo, {"X-V2-Output-Validation": "valid"})
            finally:
                if slot_adquirido and getattr(self, "project_id", None):
                    self.server.dispatcher.release_slot(self.project_id)
        except ErrorV2 as exc:
            self._cuerpo_error(exc)

    def do_DELETE(self):
        self.request_id = uuid.uuid4().hex
        self.project_id = None
        try:
            _enrutar("DELETE", self.path)
            if self.path.startswith("/jobs/"):
                jm = getattr(self.server, "jobs_manager", None)
                if jm is None:
                    _error(501, "not_implemented", "jobs no inicializado")
                proj_id = "default"
                if getattr(self.server, "auth_enabled", False):
                    auth_h = self.headers.get("Authorization")
                    proj_h = self.headers.get("X-Project-ID")
                    self.server.tokens_registry.verify_request(
                        auth_h, proj_h, required_scopes={"jobs:cancel"}
                    )
                    proj_id = proj_h.strip()
                job_id = self.path[len("/jobs/"):]
                status, res = jm.cancel_job(proj_id, job_id)
                self._json(status, json.dumps(res).encode())
                return
            _error(404, "not_found", "ruta fuera del allowlist")
        except ErrorV2 as exc:
            self._cuerpo_error(exc)

    def _metodo_no_soportado(self):
        self.request_id = uuid.uuid4().hex
        try:
            _error(404, "not_found", "método fuera del allowlist")
        except ErrorV2 as exc:
            self._cuerpo_error(exc)

    do_PUT = _metodo_no_soportado
    do_PATCH = _metodo_no_soportado
    do_OPTIONS = _metodo_no_soportado

    def log_message(self, formato, *args):  # sin paths ni payload en logs
        pass


class ServidorGateway(ThreadingHTTPServer):
    daemon_threads = True


def build_server(
    direccion,
    backend=DEFAULT_BACKEND,
    auth_enabled=None,
    tokens_registry=None,
    dispatcher=None,
):
    global _SLOT_PENDIENTE
    _SLOT_PENDIENTE = False
    servidor = ServidorGateway(direccion, ManejadorGateway)
    servidor.backend = backend
    servidor.tts_runner = None
    servidor.probe_runner = None
    servidor.auth_enabled = (
        auth_enabled if auth_enabled is not None
        else os.environ.get("LFM3_AUTH_ENABLED") == "1"
    )
    servidor.tokens_registry = tokens_registry or GLOBAL_REGISTRY
    servidor.dispatcher = dispatcher or GLOBAL_DISPATCHER
    from mcp_remote import MCPRemoteHandler
    servidor.mcp_remote_handler = MCPRemoteHandler(backend_url=backend)
    from jobs_manager import JobsManager
    servidor.jobs_manager = JobsManager(backend_url=backend)
    return servidor


def main():
    # Puerto: affordance vigente LFM3_GATEWAY_PORT, con compatibilidad
    # de la affordance histórica LFM3_ADAPTER_PORT (SPEC-i0 §1).
    bruto = (os.environ.get("LFM3_GATEWAY_PORT")
             or os.environ.get("LFM3_ADAPTER_PORT")
             or str(DEFAULT_PORT))
    backend = os.environ.get("LFM3_BACKEND", DEFAULT_BACKEND)
    try:
        puerto = int(bruto)
        servidor = build_server(("127.0.0.1", puerto), backend)
    except (OSError, ValueError, OverflowError) as exc:
        print(f"BLOQ: puerto {bruto!r} no disponible ({exc}); "
              f"no se asume puerto libre", file=sys.stderr)
        sys.exit(1)
    print(f"gateway i1 en 127.0.0.1:{puerto} -> {backend}", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
