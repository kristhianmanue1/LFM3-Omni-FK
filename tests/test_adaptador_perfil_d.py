#!/usr/bin/env python3
"""Pruebas del Adaptador local del perfil D (robots y dispositivos).

Verifica exhaustivamente los invariantes de tiempo real:
1. Deriva de reloj (|now - observed_at| > 2.0 s) descarta fail-closed.
2. Expiración pre-inferencia descarta sin llamar al gateway.
3. Expiración post-inferencia descarta propuesta vencida en tránsito.
4. Deduplicación por observation_id y rechazo de observaciones reordenadas.
5. Descarte si finish_reason != 'stop' (salida incompleta).
6. Descarte si proposal.kind está fuera de allowed_kinds autorizados.
7. Aceptación limpia de propuesta conforme.
"""

from datetime import datetime, timedelta, timezone
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from adaptador_perfil_d import RobotAdapterD  # noqa: E402


class AdaptadorPerfilDTests(unittest.TestCase):
    """Batería de pruebas de seguridad para perfil D."""

    def setUp(self):
        self.adaptador = RobotAdapterD(gateway_url="http://127.0.0.1:8092")
        self.adaptador.reset()
        self.t0 = datetime(2026, 11, 6, 12, 0, 0, tzinfo=timezone.utc)

    def _solicitud_base(self, obs_id="obs-001", delta_obs=0.0, delta_exp=5.0):
        t_obs = self.t0 + timedelta(seconds=delta_obs)
        t_exp = self.t0 + timedelta(seconds=delta_exp)
        return {
            "device_id": "robot-simulador-01",
            "observation_id": obs_id,
            "observed_at": t_obs.isoformat().replace("+00:00", "Z"),
            "expires_at": t_exp.isoformat().replace("+00:00", "Z"),
            "prompt": "Obstáculo al frente a 0.5 metros.",
            "allowed_kinds": ["detener", "girar_izquierda", "girar_derecha", "retroceder"],
        }

    @patch("urllib.request.urlopen")
    def test_observacion_valida_aceptada(self, mock_urlopen):
        propuesta_canned = {
            "id": "chatcmpl-robot-1",
            "choices": [{
                "finish_reason": "stop",
                "message": {
                    "content": json.dumps({
                        "kind": "detener",
                        "payload": {"velocidad": 0.0, "motivo": "obstaculo_cercano"},
                    })
                },
            }],
        }
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = json.dumps(propuesta_canned).encode("utf-8")

        sol = self._solicitud_base()
        res = self.adaptador.evaluar_observacion(sol, ahora_fn=lambda: self.t0)
        self.assertEqual(res["status"], "accepted")
        self.assertEqual(res["observation_id"], "obs-001")
        self.assertEqual(res["proposal"]["kind"], "detener")
        self.assertTrue(res["complete"])

    def test_deriva_reloj_mayor_2s_descartada_drift_clock(self):
        # Reloj del robot retrasado 2.5 segundos frente al nodo de inferencia
        sol = self._solicitud_base(delta_obs=-2.5, delta_exp=5.0)
        res = self.adaptador.evaluar_observacion(sol, ahora_fn=lambda: self.t0)
        self.assertEqual(res["status"], "discarded")
        self.assertEqual(res["reason"], "drift_clock")
        self.assertIn("deriva de reloj", res["detail"])

    def test_expirada_pre_inferencia_descartada(self):
        # Expiró hace 1 segundo
        sol = self._solicitud_base(delta_obs=-0.5, delta_exp=-0.1)
        res = self.adaptador.evaluar_observacion(sol, ahora_fn=lambda: self.t0)
        self.assertEqual(res["status"], "discarded")
        self.assertEqual(res["reason"], "expired_pre_inference")

    @patch("urllib.request.urlopen")
    def test_expirada_post_inferencia_descartada(self, mock_urlopen):
        # Caduca en 1.0 s, pero la llamada al gateway tarda 1.5 s
        sol = self._solicitud_base(delta_obs=0.0, delta_exp=1.0)
        propuesta_canned = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps({"kind": "detener", "payload": {}})},
            }],
        }
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = json.dumps(propuesta_canned).encode("utf-8")

        # Simular avance del tiempo durante la inferencia
        tiempos = [self.t0, self.t0 + timedelta(seconds=1.5)]

        def avanzar_tiempo():
            return tiempos.pop(0) if tiempos else self.t0 + timedelta(seconds=2.0)

        res = self.adaptador.evaluar_observacion(sol, ahora_fn=avanzar_tiempo)
        self.assertEqual(res["status"], "discarded")
        self.assertEqual(res["reason"], "expired_post_inference")

    @patch("urllib.request.urlopen")
    def test_observation_id_duplicado_descartado(self, mock_urlopen):
        propuesta_canned = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps({"kind": "detener", "payload": {}})},
            }],
        }
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = json.dumps(propuesta_canned).encode("utf-8")

        sol = self._solicitud_base(obs_id="obs-dup")
        res1 = self.adaptador.evaluar_observacion(sol, ahora_fn=lambda: self.t0)
        self.assertEqual(res1["status"], "accepted")

        # Segunda llamada con mismo id
        res2 = self.adaptador.evaluar_observacion(sol, ahora_fn=lambda: self.t0)
        self.assertEqual(res2["status"], "discarded")
        self.assertEqual(res2["reason"], "duplicate_observation")

    @patch("urllib.request.urlopen")
    def test_observacion_reordenada_descartada(self, mock_urlopen):
        propuesta_canned = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps({"kind": "detener", "payload": {}})},
            }],
        }
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = json.dumps(propuesta_canned).encode("utf-8")

        sol1 = self._solicitud_base(obs_id="obs-1", delta_obs=0.5)
        res1 = self.adaptador.evaluar_observacion(sol1, ahora_fn=lambda: self.t0)
        self.assertEqual(res1["status"], "accepted")

        # Siguiente observación tiene timestamp ANTERIOR al de obs-1 (0.2 < 0.5)
        sol2 = self._solicitud_base(obs_id="obs-2", delta_obs=0.2)
        res2 = self.adaptador.evaluar_observacion(sol2, ahora_fn=lambda: self.t0)
        self.assertEqual(res2["status"], "discarded")
        self.assertEqual(res2["reason"], "reordered_observation")

    @patch("urllib.request.urlopen")
    def test_finish_reason_distinto_stop_descartado_incomplete_output(self, mock_urlopen):
        propuesta_canned = {
            "choices": [{
                "finish_reason": "length",  # Se quedó sin tokens, truncado
                "message": {"content": json.dumps({"kind": "detener", "payload": {}})},
            }],
        }
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = json.dumps(propuesta_canned).encode("utf-8")

        sol = self._solicitud_base()
        res = self.adaptador.evaluar_observacion(sol, ahora_fn=lambda: self.t0)
        self.assertEqual(res["status"], "discarded")
        self.assertEqual(res["reason"], "incomplete_output")

    @patch("urllib.request.urlopen")
    def test_propuesta_kind_no_autorizado_descartado(self, mock_urlopen):
        # El modelo alucina una acción física no autorizada
        propuesta_canned = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps({"kind": "disparar_laser", "payload": {}})},
            }],
        }
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = json.dumps(propuesta_canned).encode("utf-8")

        sol = self._solicitud_base()
        res = self.adaptador.evaluar_observacion(sol, ahora_fn=lambda: self.t0)
        self.assertEqual(res["status"], "discarded")
        self.assertEqual(res["reason"], "unauthorized_proposal_kind")

    @patch("urllib.request.urlopen")
    def test_salida_modelo_no_dict_descartada_fail_closed(self, mock_urlopen):
        # El modelo responde un escalar o lista en vez de objeto JSON
        for salida_anomala in ('"detener"', "[1, 2]", "true", "null", "42"):
            with self.subTest(salida=salida_anomala):
                propuesta_canned = {
                    "choices": [{
                        "finish_reason": "stop",
                        "message": {"content": salida_anomala},
                    }],
                }
                mock_resp = mock_urlopen.return_value.__enter__.return_value
                mock_resp.read.return_value = json.dumps(propuesta_canned).encode("utf-8")

                sol = self._solicitud_base(obs_id=f"obs-{hash(salida_anomala)}")
                res = self.adaptador.evaluar_observacion(sol, ahora_fn=lambda: self.t0)
                self.assertEqual(res["status"], "discarded")
                self.assertEqual(res["reason"], "invalid_schema")
                self.assertIn("no es un objeto JSON", res["detail"])

    @patch("urllib.request.urlopen")
    def test_payload_propuesta_no_dict_descartado(self, mock_urlopen):
        propuesta_canned = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps({"kind": "detener", "payload": "no_dict"})},
            }],
        }
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = json.dumps(propuesta_canned).encode("utf-8")

        sol = self._solicitud_base()
        res = self.adaptador.evaluar_observacion(sol, ahora_fn=lambda: self.t0)
        self.assertEqual(res["status"], "discarded")
        self.assertEqual(res["reason"], "invalid_schema")
        self.assertIn("payload de propuesta debe ser un objeto", res["detail"])


if __name__ == "__main__":
    unittest.main()
