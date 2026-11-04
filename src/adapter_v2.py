#!/usr/bin/env python3
"""Adaptador v2 de I0 — fachada de compatibilidad sobre el gateway I1.

El punto de entrada vigente es `src/gateway_http.py` (SPEC-i1, ADR-005):
las políticas viven en `gateway_core` y el transporte en
`gateway_http`. Este módulo conserva la superficie que consumían las
pruebas y la demo de I0 sin cambio de comportamiento; SPEC-i1 declara
la reorganización.
"""

from gateway_core import (
    CLAVES_NO_SOPORTADAS, CLAVES_TOP, DEFAULT_BACKEND, DEFAULT_PORT,
    MAX_BODY_BYTES, MAX_IMAGEN_BYTES, MAX_PIXELES, MAX_PROPIEDADES,
    MAX_TOKENS, ROLES, TIPOS_SCHEMA, ErrorV2, validar_imagen, validar_jpeg,
    validar_payload, validar_png, validar_salida, validar_schema,
)
from gateway_http import ManejadorGateway, ServidorGateway, build_server, main

# Alias históricos de I0 (los nombres de la fachada original).
ManejadorV2 = ManejadorGateway
ServidorV2 = ServidorGateway

__all__ = [
    "CLAVES_NO_SOPORTADAS", "CLAVES_TOP", "DEFAULT_BACKEND", "DEFAULT_PORT",
    "ErrorV2", "MAX_BODY_BYTES", "MAX_IMAGEN_BYTES", "MAX_PIXELES",
    "MAX_PROPIEDADES", "MAX_TOKENS", "ManejadorV2", "ROLES", "ServidorV2",
    "TIPOS_SCHEMA", "build_server", "main", "validar_imagen", "validar_jpeg",
    "validar_payload", "validar_png", "validar_salida", "validar_schema",
]

if __name__ == "__main__":
    main()
