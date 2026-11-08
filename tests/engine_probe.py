"""Sonda de motor para las guardas de la suite (fix-tests-hermeticos P2).

Distingue la ausencia verificada del motor (nada escucha en el puerto:
conexión rehusada) de un error de la sonda (respuesta malformada,
timeout, 5xx u otro error de transporte). Sólo la ausencia verificada
justifica saltar un test; un error de sonda debe hacer FALLAR la guarda
con su motivo, nunca esconderse como «sin motor».
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request


def probe_engine(url="http://127.0.0.1:8091/health", timeout=2.0):
    """Sondea la salud del motor y devuelve (up, reason).

    up=True, reason=None: el motor responde /health con status «ok».
    up=False, reason=None: ausencia verificada (conexión rehusada);
    es la única situación que justifica saltar un test.
    up=False, reason="...": la sonda falló por otra causa; el motivo
    explica cuál y la guarda que lo use debe fallar, no saltar.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                return False, f"/health respondió {resp.status}"
            body = resp.read()
    except urllib.error.HTTPError as exc:
        try:
            exc.close()
        except OSError:
            pass
        return False, f"/health respondió {exc.code}"
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ConnectionRefusedError):
            return False, None
        return False, f"error de sonda: {exc.reason!r}"
    except ConnectionRefusedError:
        return False, None
    except (TimeoutError, socket.timeout):
        return False, "timeout de la sonda"
    except OSError as exc:
        return False, f"error de transporte: {exc!r}"

    try:
        data = json.loads(body)
    except ValueError as exc:
        return False, f"respuesta malformada: {exc}"
    if not (isinstance(data, dict) and data.get("status") == "ok"):
        return False, f"status distinto de ok: {data!r}"
    return True, None
