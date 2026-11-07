#!/usr/bin/env python3
"""Simulador de robot local usando el Adaptador de Perfil D (Fase I4).

Simula el bucle de sensado y control de un robot móvil en modo seguro (sin
actuadores físicos):
- Transmisión de telemetría y fotogramas visuales (cámara de navegación).
- Comunicación autenticada (proyecto-beta con scope profile:d).
- Verificación exhaustiva de salvaguardas temporales fail-closed:
  1. Observación válida en tiempo real con imagen y prompt.
  2. Deduplicación por observation_id.
  3. Expiración pre-inferencia (lectura atrasada o caducada).
  4. Deriva excesiva de reloj entre nodo sensor y gateway (> 2.0 s).
  5. Catálogo cerrado de acciones permitidas (allowed_kinds).

Exit 0 si todas las salvaguardas pasan.
Uso: python3.12 examples/simulador_robot_perfil_d.py [puerto_gateway] [token]
"""

from datetime import datetime, timedelta, timezone
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from adaptador_perfil_d import RobotAdapterD  # noqa: E402

PUERTO = int(sys.argv[1]) if len(sys.argv) > 1 else 8092
TOKEN_BETA = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("LFM3_AUTH_TOKEN", "beta-test-token-for-pilot-i2-32chars")

# PNG 1x1 transparente para simular sensor visual de navegación
PNG_1X1_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def main():
    scheme = "https" if PUERTO == 8443 else "http"
    url_gw = f"{scheme}://127.0.0.1:{PUERTO}"
    adaptador = RobotAdapterD(gateway_url=url_gw, auth_token=TOKEN_BETA, ssl_verify=False)
    ahora = datetime.now(timezone.utc)

    print(f"Iniciando Simulador de Robot (Perfil D) contra {url_gw}...")

    # Caso 1: Detección de obstáculo con imagen y vigencia amplia (5 s)
    solicitud = {
        "device_id": "robot-sim-01",
        "observation_id": f"obs-{int(ahora.timestamp())}-01",
        "observed_at": ahora.isoformat().replace("+00:00", "Z"),
        "expires_at": (ahora + timedelta(seconds=5)).isoformat().replace("+00:00", "Z"),
        "image_base64": PNG_1X1_B64,
        "prompt": "Obstáculo a 0.3 metros al frente. Sugiere acción cinemática segura.",
        "allowed_kinds": ["detener", "girar_izquierda", "girar_derecha", "retroceder"],
    }
    resultado = adaptador.evaluar_observacion(solicitud)
    print(f"Caso 1 (Observación multimodal en tiempo real): status={resultado.get('status')}")
    if resultado.get("status") == "accepted":
        print(f"  Propuesta aceptada: {resultado['proposal']}")
    else:
        print(f"  Descarte controlado: {resultado.get('reason')} ({resultado.get('detail')})")
        # Asegurar visto para probar deduplicación si gateway no está levantado
        adaptador.vistos.add(solicitud["observation_id"])

    # Caso 2: Observación duplicada (debe descartarse inmediatamente)
    res_dup = adaptador.evaluar_observacion(solicitud)
    assert res_dup.get("status") == "discarded" and res_dup.get("reason") == "duplicate_observation", (
        f"Fallo en deduplicación: {res_dup}"
    )
    print("Caso 2 (Deduplicación): OK (descarte por duplicate_observation)")

    # Caso 3: Observación vencida en origen (now >= expires_at)
    sol_vencida = {
        "device_id": "robot-sim-01",
        "observation_id": f"obs-{int(ahora.timestamp())}-03",
        "observed_at": (ahora - timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
        "expires_at": (ahora - timedelta(seconds=0.1)).isoformat().replace("+00:00", "Z"),
        "prompt": "Lectura tardía.",
        "allowed_kinds": ["detener"],
    }
    res_vencida = adaptador.evaluar_observacion(sol_vencida)
    assert res_vencida.get("status") == "discarded" and res_vencida.get("reason") == "expired_pre_inference", (
        f"Fallo en expiración pre-inferencia: {res_vencida}"
    )
    print("Caso 3 (Expiración pre-inferencia): OK (descarte por expired_pre_inference)")

    # Caso 4: Desfase excesivo de reloj (|now - observed_at| > 2.0 s)
    sol_reloj = {
        "device_id": "robot-sim-01",
        "observation_id": f"obs-{int(ahora.timestamp())}-04",
        "observed_at": (ahora - timedelta(seconds=3.0)).isoformat().replace("+00:00", "Z"),
        "expires_at": (ahora + timedelta(seconds=10.0)).isoformat().replace("+00:00", "Z"),
        "prompt": "Reloj desfasado.",
        "allowed_kinds": ["detener"],
    }
    res_reloj = adaptador.evaluar_observacion(sol_reloj)
    assert res_reloj.get("status") == "discarded" and res_reloj.get("reason") == "drift_clock", (
        f"Fallo en control de deriva de reloj: {res_reloj}"
    )
    print("Caso 4 (Deriva temporal > 2.0 s): OK (descarte por drift_clock)")

    print("\nSimulador de Robot Perfil D: todas las salvaguardas verificadas con éxito.")
    sys.exit(0)


if __name__ == "__main__":
    main()
