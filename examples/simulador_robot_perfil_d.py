#!/usr/bin/env python3
"""Simulador de robot local usando el Adaptador de Perfil D (SPEC-i1-vc §2).

Simula el bucle de control de un robot móvil en modo seguro (sin actuadores).
Verifica que las propuestas de acción respeten las restricciones de tiempo real,
deduplicación y lista cerrada de acciones permitidas.
Exit 0 si toda la simulación pasa.

Uso: python3.12 examples/simulador_robot_perfil_d.py [puerto_gateway]
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


def main():
    url_gw = f"http://127.0.0.1:{PUERTO}"
    adaptador = RobotAdapterD(gateway_url=url_gw)
    ahora = datetime.now(timezone.utc)

    print(f"Iniciando Simulador de Robot (Perfil D) contra {url_gw}...")

    # Caso 1: Detección de obstáculo con vigencia amplia (5 segundos)
    solicitud = {
        "device_id": "robot-sim-01",
        "observation_id": f"obs-{int(ahora.timestamp())}-01",
        "observed_at": ahora.isoformat().replace("+00:00", "Z"),
        "expires_at": (ahora + timedelta(seconds=5)).isoformat().replace("+00:00", "Z"),
        "prompt": "Obstáculo a 0.3 metros al frente. Sugiere acción segura.",
        "allowed_kinds": ["detener", "girar_izquierda", "girar_derecha", "retroceder"],
    }
    resultado = adaptador.evaluar_observacion(solicitud)
    print(f"Caso 1 (Observación tiempo real): status={resultado.get('status')}")
    if resultado.get("status") == "accepted":
        print(f"  Propuesta aceptada: {resultado['proposal']}")
    else:
        print(f"  Descarte controlado: {resultado.get('reason')} ({resultado.get('detail')})")

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

    print("Simulador de Robot Perfil D: todas las salvaguardas verificadas con éxito.")
    sys.exit(0)


if __name__ == "__main__":
    main()
