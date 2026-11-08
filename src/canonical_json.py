#!/usr/bin/env python3
"""Serialización canónica RFC 8785 (JCS) — Perfil J, Fase I5.

Contrato: docs/contracts/perfiles-servicio-v2.md (§J)
Especificación: docs/specs/SPEC-i5-jobs.md §2.1
Expediente: docs/reviews/evidence/fix-i5-jobs-frontera/ (fix-i5)

Forma canónica exacta para el digest de idempotencia: claves ordenadas
por unidades de código UTF-16 (§3.2.2.3 del RFC; sorted() de Python
desordenaría los astrales), números en forma ES6 —la de
JSON.stringify—, escapes mínimos de cadena (§3.2.2.2) y enteros
acotados al rango exacto de dobles IEEE 754. Fixtures numéricos
verificados contra Node.js v26.7.0 (V8) el 2026-11-07; fuzz de
78.513 números sin divergencias byte a byte.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

_ENTERO_MAX = 2**53 - 1  # rango exacto de dobles IEEE 754

_ESCAPES_CORTOS = {
    '"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f",
    "\n": "\\n", "\r": "\\r", "\t": "\\t",
}


def _serializar_cadena(texto: str) -> str:
    """Escapes mínimos RFC 8785 §3.2.2.2 para controles y comillas."""
    partes = ['"']
    for caracter in texto:
        if caracter in _ESCAPES_CORTOS:
            partes.append(_ESCAPES_CORTOS[caracter])
        elif caracter < "\u0020":
            partes.append(f"\\u{ord(caracter):04x}")
        else:
            partes.append(caracter)
    partes.append('"')
    return "".join(partes)


def _digitos_cortos(valor: float) -> tuple[str, int]:
    """(digitos, exp) con valor == int(digitos)*10**exp (repr corta)."""
    tupla = Decimal(repr(valor)).as_tuple()
    digitos = "".join(str(d) for d in tupla.digits)
    exponente = tupla.exponent
    recorte = len(digitos) - len(digitos.rstrip("0"))
    if recorte:
        digitos = digitos[:-recorte]
        exponente += recorte
    return digitos, exponente


def _numero_es6(valor: float) -> str:
    """Número en forma ES6 (RFC 8785 §3.2.2.3), la de JSON.stringify."""
    if valor != valor or valor in (float("inf"), float("-inf")):
        raise ValueError("número no finito no es serializable en JSON")
    if valor == 0:
        return "0"  # incluye -0.0: JSON.stringify(-0) === "0"
    prefijo = "-" if valor < 0 else ""
    digitos, exponente = _digitos_cortos(abs(valor))
    n = exponente + len(digitos)  # valor == 0.d1..dk * 10**n
    k = len(digitos)
    if k <= n <= 21:
        return prefijo + digitos + "0" * (n - k)
    if 0 < n <= 21:
        return prefijo + digitos[:n] + "." + digitos[n:]
    if -6 < n <= 0:
        return prefijo + "0." + "0" * (-n) + digitos
    mantisa = digitos[0] + ("." + digitos[1:] if k > 1 else "")
    signo_e = "+" if n - 1 >= 0 else "-"
    return f"{prefijo}{mantisa}e{signo_e}{abs(n - 1)}"


def _serializar_valor(valor: Any) -> str:
    if valor is True:
        return "true"
    if valor is False:
        return "false"
    if valor is None:
        return "null"
    if isinstance(valor, int):
        if not (-_ENTERO_MAX <= valor <= _ENTERO_MAX):
            raise ValueError(
                f"entero {valor} fuera del rango exacto de dobles IEEE 754")
        return str(valor)
    if isinstance(valor, float):
        return _numero_es6(valor)
    if isinstance(valor, str):
        return _serializar_cadena(valor)
    if isinstance(valor, list):
        return "[" + ",".join(_serializar_valor(v) for v in valor) + "]"
    if isinstance(valor, dict):
        if not all(isinstance(clave, str) for clave in valor):
            raise TypeError("clave de objeto no es cadena")
        # RFC 8785 §3.2.2.3: orden por unidades de código UTF-16, no por
        # punto de código (sorted() de Python desordenaría los astrales).
        claves = sorted(valor, key=lambda c: c.encode("utf-16-be"))
        cuerpo = ",".join(
            _serializar_cadena(c) + ":" + _serializar_valor(valor[c])
            for c in claves)
        return "{" + cuerpo + "}"
    raise TypeError(f"tipo no serializable en JSON: {type(valor).__name__}")


def canonical_json_rfc8785(data: Any) -> bytes:
    """RFC 8785: claves UTF-16, números ES6, enteros en rango doble."""
    return _serializar_valor(data).encode("utf-8")
