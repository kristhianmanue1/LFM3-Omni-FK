#!/usr/bin/env python3
"""Frontera HTTP del Perfil J (rutas /jobs) — Fase I5.

Contrato: docs/contracts/perfiles-servicio-v2.md (§J)
Especificación: docs/specs/SPEC-i5-jobs.md §2
Expediente: docs/reviews/evidence/fix-i5-jobs-frontera/ (fix-i5)

Transporte puro delegado desde gateway_http (reorganización del
expediente, §3.3 del estándar: mover sin cambiar comportamiento):
autenticación con jobs:read/cancel/create más el scope de la
modalidad de la operación (SPEC-i5 §2.1), sobre completo validado
(raíz objeto, ttl_seconds entero en 60..86400) y payload por el
núcleo de validación de H (validar_payload, sin passthrough).
"""

from __future__ import annotations

import json

from gateway_core import _error, validar_payload


# Scope de la modalidad por operación del Perfil J (SPEC-i5 §2.1): el
# mismo scope que exige H para ese contenido (SPEC-i2 §2.3).
SCOPE_POR_OPERACION = {
    "infer_text": "infer:text",
    "infer_vision": "infer:vision",
    "infer_audio": "infer:audio",
    "infer_video": "infer:vision",
}


def manejar_get_job(handler) -> None:
    """GET /jobs/{id}: consulta aislada por proyecto (SPEC-i5 §2.2)."""
    jm = getattr(handler.server, "jobs_manager", None)
    if jm is None:
        _error(501, "not_implemented", "jobs no inicializado")
    proj_id = handler.project_id or "default"
    if getattr(handler.server, "auth_enabled", False):
        auth_h = handler.headers.get("Authorization")
        proj_h = handler.headers.get("X-Project-ID")
        handler.server.tokens_registry.verify_request(
            auth_h, proj_h, required_scopes={"jobs:read"}
        )
        proj_id = proj_h.strip()
    job_id = handler.path[len("/jobs/"):]
    status, res = jm.get_job(proj_id, job_id)
    handler._json(status, json.dumps(res).encode())


def manejar_post_job(handler, payload) -> None:
    """POST /jobs: admisión con frontera de H y scope de modalidad
    (SPEC-i5 §2.1). Sin passthrough: el payload pasa por el núcleo."""
    # Import diferido: gateway_http importa este módulo al construir el
    # servidor; sería circular en sentido contrario (mismo patrón que
    # mcp_remote con la síntesis de voz).
    from gateway_http import _determinar_scopes_chat, _inspeccionar_mp4_ffprobe

    jm = getattr(handler.server, "jobs_manager", None)
    if jm is None:
        _error(501, "not_implemented", "jobs no inicializado")
    if not isinstance(payload, dict):
        _error(400, "invalid_json", "el cuerpo debe ser un objeto JSON")
    idemp_key = handler.headers.get("Idempotency-Key") or ""
    proj_id = handler.project_id or "default"
    op = payload.get("operation")
    job_payload = payload.get("payload", {})
    ttl = payload.get("ttl_seconds", 3600)
    if isinstance(ttl, bool) or not isinstance(ttl, int) \
            or not (60 <= ttl <= 86400):
        _error(400, "unsupported_field_value",
               "ttl_seconds debe ser entero en 60..86400")
    if getattr(handler.server, "auth_enabled", False):
        auth_h = handler.headers.get("Authorization")
        proj_h = handler.headers.get("X-Project-ID")
        # SPEC-i5 §2.1: jobs:create + scope de modalidad.
        scopes_req = {"jobs:create"} | _determinar_scopes_chat(job_payload)
        if isinstance(op, str) and op in SCOPE_POR_OPERACION:
            scopes_req.add(SCOPE_POR_OPERACION[op])
        handler.server.tokens_registry.verify_request(
            auth_h, proj_h, required_scopes=scopes_req)
        proj_id = proj_h.strip()
    # Sin passthrough (BLOCKER-1): núcleo de validación de H.
    validar_payload(
        job_payload,
        inspector_video=lambda d: _inspeccionar_mp4_ffprobe(
            d, getattr(handler.server, "probe_runner", None)))
    status, res = jm.create_job(
        proj_id, op, job_payload, idemp_key, ttl_seconds=ttl)
    handler._json(status, json.dumps(res).encode())


def manejar_delete_job(handler) -> None:
    """DELETE /jobs/{id}: cancelación (SPEC-i5 §2.3)."""
    jm = getattr(handler.server, "jobs_manager", None)
    if jm is None:
        _error(501, "not_implemented", "jobs no inicializado")
    proj_id = "default"
    if getattr(handler.server, "auth_enabled", False):
        auth_h = handler.headers.get("Authorization")
        proj_h = handler.headers.get("X-Project-ID")
        handler.server.tokens_registry.verify_request(
            auth_h, proj_h, required_scopes={"jobs:cancel"}
        )
        proj_id = proj_h.strip()
    job_id = handler.path[len("/jobs/"):]
    status, res = jm.cancel_job(proj_id, job_id)
    handler._json(status, json.dumps(res).encode())


def construir_jobs_manager(servidor, jobs_dir=None):
    """Cablea el JobsManager del servidor: el worker comparte admisión
    con H/M vía el dispatcher y los límites por proyecto (HIGH-1).
    jobs_dir inyectable (MED-9): los tests pasan uno temporal; la
    producción lo declara explícito en main()."""
    from jobs_manager import JobsManager

    def limites_de_proyecto(project_id):
        info = servidor.tokens_registry.get_project(project_id) or {}
        return info.get("rate_limit") or {}

    return JobsManager(
        jobs_dir=jobs_dir,
        backend_url=servidor.backend,
        dispatcher=servidor.dispatcher,
        rate_limit_lookup=limites_de_proyecto,
    )
