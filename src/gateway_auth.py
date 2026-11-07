#!/usr/bin/env python3
"""Módulo de autenticación, cuotas y planificación justa del piloto I2.

Implementa las especificaciones de SPEC-i2-piloto-privado (§2, §4) y ADR-009:
- Registro de credenciales Bearer por proyecto con hash SHA-256 en config/tokens.json (0600).
- Recarga en caliente en memoria ante cambios en el archivo sin reiniciar el gateway.
- Validación determinista de scopes y cabecera obligatoria X-Project-ID.
- Limitador de tasa por Token Bucket por proyecto (429 rate_limit_exceeded).
- Planificación justa (Fair Queuing) para evitar inanición entre inquilinos
  (503 overloaded en saturación; 504 queue_timeout en expiración).
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Dict, Iterable, Optional, Set, Tuple, Union

from gateway_core import ErrorV2, _error

RE_PROJECT_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
DEFAULT_TOKENS_PATH = Path(__file__).resolve().parent.parent / "config" / "tokens.json"


class TokenRegistry:
    """Gestiona el registro de credenciales con recarga en caliente."""

    def __init__(self, ruta_archivo: Optional[Path | str] = None) -> None:
        self.ruta = Path(ruta_archivo or DEFAULT_TOKENS_PATH).resolve()
        self._lock = threading.Lock()
        self._mtime: float = 0.0
        self._data: Dict[str, Any] = {}
        self._cargar_si_cambio(forzar=True)

    def _cargar_si_cambio(self, forzar: bool = False) -> None:
        try:
            stat = self.ruta.stat()
            actual_mtime = stat.st_mtime
        except OSError:
            if forzar:
                self._data = {"version": 1, "projects": {}}
            return

        if not forzar and actual_mtime <= self._mtime:
            return

        try:
            with open(self.ruta, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "projects" in data and isinstance(data["projects"], dict):
                self._data = data
                self._mtime = actual_mtime
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._cargar_si_cambio()
            return self._data.get("projects", {}).get(project_id)

    def verify_request(
        self,
        auth_header: Optional[str],
        project_id_header: Optional[str],
        required_scopes: Optional[Union[str, Iterable[str]]] = None,
        required_scope: Optional[Union[str, Iterable[str]]] = None,
    ) -> Dict[str, Any]:
        """Valida token, project_id y scopes según SPEC-i2 (§2)."""
        scopes_check = required_scopes if required_scopes is not None else required_scope
        if not auth_header or not auth_header.strip():
            _error(401, "missing_token", "cabecera Authorization requerida",
                   type="auth_error", retryable=False, param="Authorization")

        partes = auth_header.strip().split(" ", 1)
        if len(partes) != 2 or partes[0].lower() != "bearer":
            _error(401, "invalid_token", "formato de token inválido; debe ser Bearer <token>",
                   type="auth_error", retryable=False, param="Authorization")

        token = partes[1].strip()
        if len(token) < 32 or len(token) > 64:
            _error(401, "invalid_token", "longitud de token fuera del rango permitido (32..64)",
                   type="auth_error", retryable=False, param="Authorization")

        if not project_id_header or not project_id_header.strip():
            _error(400, "missing_project_id", "cabecera X-Project-ID requerida",
                   type="invalid_request_error", retryable=False, param="X-Project-ID")

        project_id = project_id_header.strip()
        if not RE_PROJECT_ID.match(project_id):
            _error(400, "invalid_project_id", "formato de X-Project-ID inválido",
                   type="invalid_request_error", retryable=False, param="X-Project-ID")

        proj_info = self.get_project(project_id)
        if not proj_info:
            _error(403, "project_mismatch", "proyecto no registrado o discrepancia con token",
                   type="auth_error", retryable=False, param="X-Project-ID")

        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if token_hash != proj_info.get("token_sha256"):
            _error(403, "project_mismatch", "el token no coincide con el proyecto indicado",
                   type="auth_error", retryable=False, param="Authorization")

        if proj_info.get("revoked") is True:
            _error(403, "credential_revoked", "la credencial de este proyecto ha sido revocada",
                   type="auth_error", retryable=False, param="Authorization")

        if scopes_check:
            scopes_declarados = set(proj_info.get("scopes", []))
            if isinstance(scopes_check, str):
                necesarios = {scopes_check}
            else:
                necesarios = set(scopes_check)

            faltantes = necesarios - scopes_declarados
            if faltantes:
                scope_faltante = sorted(faltantes)[0]
                _error(403, "insufficient_scope",
                       f"el proyecto no posee el scope requerido: '{scope_faltante}'",
                       type="auth_error", retryable=False, param="scope")

        return proj_info


class TokenBucket:
    """Implementa el algoritmo Token Bucket para limitación de tasa por proyecto."""

    def __init__(self, requests_per_minute: int = 60, burst: int = 5) -> None:
        self.capacity = float(burst)
        self.tokens = float(burst)
        self.fill_rate = float(requests_per_minute) / 60.0
        self.last_update = time.monotonic()
        self._lock = threading.Lock()

    def update_config(self, requests_per_minute: int, burst: int) -> None:
        with self._lock:
            self.capacity = float(burst)
            self.fill_rate = float(requests_per_minute) / 60.0

    def acquire(self) -> Tuple[bool, float]:
        """Intenta adquirir 1 ficha.

        Retorna (True, 0.0) si fue admitido, o (False, retry_after) si fue limitado.
        """
        with self._lock:
            ahora = time.monotonic()
            delta = ahora - self.last_update
            self.last_update = ahora
            self.tokens = min(self.capacity, self.tokens + delta * self.fill_rate)

            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True, 0.0

            faltan = 1.0 - self.tokens
            retry_after = faltan / self.fill_rate if self.fill_rate > 0 else 1.0
            return False, max(0.1, retry_after)


class FairQueueDispatcher:
    """Despachador con planificación justa (Fair Queuing / Round-Robin) entre proyectos."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_projects: collections.deque[str] = collections.deque()
        self._queues: Dict[str, collections.deque[threading.Event]] = collections.defaultdict(collections.deque)
        self._in_flight: Dict[str, int] = collections.defaultdict(int)
        self._limiters: Dict[str, TokenBucket] = {}
        self._engine_in_use = False

    def get_limiter(self, project_id: str, rl_config: Dict[str, Any]) -> TokenBucket:
        with self._lock:
            if project_id not in self._limiters:
                rpm = rl_config.get("requests_per_minute", 60)
                burst = rl_config.get("burst", 5)
                self._limiters[project_id] = TokenBucket(rpm, burst)
            return self._limiters[project_id]

    def _schedule_next_unlocked(self) -> None:
        """Selecciona el siguiente turno de manera equitativa alternando proyectos."""
        if self._engine_in_use:
            return

        recorridos = 0
        total = len(self._active_projects)
        while recorridos < total:
            proj = self._active_projects[0]
            self._active_projects.rotate(-1)
            recorridos += 1

            cola = self._queues[proj]
            while cola:
                ev = cola.popleft()
                if not ev.is_set():
                    self._engine_in_use = True
                    self._in_flight[proj] += 1
                    ev.set()
                    return

            if not cola and proj in self._active_projects:
                try:
                    self._active_projects.remove(proj)
                    total -= 1
                except ValueError:
                    pass

    def acquire_slot(
        self,
        project_id: str,
        rl_config: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> None:
        """Adquiere el turno de ejecución respetando concurrencia y cola."""
        limiter = self.get_limiter(project_id, rl_config)
        allowed, retry_after = limiter.acquire()
        if not allowed:
            _error(429, "rate_limit_exceeded",
                   f"tasa de peticiones excedida; reintente en {retry_after:.1f} s",
                   type="rate_limit_error", retryable=True, retry_after=f"{retry_after:.1f}")

        max_queue = rl_config.get("max_queue", 2)
        timeout_segundos = timeout or rl_config.get("queue_timeout_seconds", 10.0)

        ev = threading.Event()
        with self._lock:
            cola = self._queues[project_id]
            if len(cola) >= max_queue:
                _error(503, "overloaded",
                       f"cola de peticiones del proyecto '{project_id}' saturada",
                       type="server_error", retryable=True)

            cola.append(ev)
            if project_id not in self._active_projects:
                self._active_projects.append(project_id)
            self._schedule_next_unlocked()

        admitido = ev.wait(timeout=timeout_segundos)
        if not admitido:
            with self._lock:
                ev.set()
                estaba_en_cola = False
                try:
                    self._queues[project_id].remove(ev)
                    estaba_en_cola = True
                except ValueError:
                    pass
                # Si estaba en cola, la peticion NUNCA llego a adquirir el motor.
                # Solo si NO estaba en cola significa que una carrera le concedio el turno justo
                # al expirar el wait. En ese caso (y solo en ese), debemos liberar el motor.
                if not estaba_en_cola:
                    if self._in_flight[project_id] > 0:
                        self._in_flight[project_id] -= 1
                    self._engine_in_use = False
                    self._schedule_next_unlocked()
            _error(504, "queue_timeout",
                   f"tiempo de espera en cola excedido ({timeout_segundos:.1f} s)",
                   type="server_error", retryable=True)

    def release_slot(self, project_id: str) -> None:
        """Libera el turno de inferencia y activa el siguiente proyecto en espera."""
        with self._lock:
            if self._in_flight[project_id] > 0:
                self._in_flight[project_id] -= 1
            self._engine_in_use = False
            self._schedule_next_unlocked()


GLOBAL_REGISTRY = TokenRegistry()
GLOBAL_DISPATCHER = FairQueueDispatcher()
