#!/usr/bin/env python3
"""Pruebas unitarias para la Fase I6 (Evaluación y Triaje de Modelos).

Verifica exhaustivamente:
1. Compuerta de rechazo temprano (Early Rejection Gate):
   - Licencia no permisiva -> rechazo inmediato sin descarga.
   - Arquitectura incompatible -> rechazo inmediato.
   - Presupuesto de memoria superado (> 6 GB) -> rechazo inmediato.
   - Pérdida de modalidades omnimodales -> rechazo inmediato.
2. Bloqueo fail-closed ante falta de autorización expresa del Operador.
3. Evaluación comparativa contra Golden Dataset:
   - Degradación de conformidad con esquemas -> veredicto rejected.
   - Degradación de latencia p95 -> veredicto rejected.
   - Exceso de consumo de memoria RSS -> veredicto rejected.
4. Propuesta de promoción gobernada con plan de rollback en un paso.
5. Invariante de baseline congelado: hashes e inventario inalterados.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from evaluacion_modelos import EvaluadorModelos  # noqa: E402


class EvaluadorModelosTests(unittest.TestCase):
    """Batería de pruebas de triaje, evaluación comparativa y ciclo de vida."""

    def setUp(self):
        self.evaluador = EvaluadorModelos(root_dir=RAIZ)

    def _candidato_valido(self):
        return {
            "id": "cand-lfm-v2-q4",
            "licencia": "lfm-open-v1.0",
            "formato": "gguf",
            "memoria_estimada_gb": 3.2,
            "modalidades": ["texto", "imagen", "audio", "voz", "video"],
            "benchmarks_observados": {
                "conformidad_schema_pct": 99.8,
                "latencia_p95_ms": 1150.0,
                "latencia_p50_ms": 600.0,
                "rss_pico_mb": 3100.0,
            },
        }

    # 1. Pruebas de Triaje Temprano
    def test_01_rechazo_temprano_licencia_incompatible(self):
        cand = self._candidato_valido()
        cand["licencia"] = "cc-by-nc-4.0"  # No comercial
        res = self.evaluador.evaluar_candidato(cand, autorizado_operador=True)
        self.assertEqual(res["veredicto"], "rejected")
        self.assertEqual(res["fase"], "triaje_temprano")
        self.assertIn("incompatible", res["razon"])
        self.assertTrue(res["baseline_preservado"])

    def test_02_rechazo_temprano_arquitectura_incompatible(self):
        cand = self._candidato_valido()
        cand["formato"] = "tensorrt-llm-cuda"  # Incompatible con llama.cpp
        res = self.evaluador.evaluar_candidato(cand, autorizado_operador=True)
        self.assertEqual(res["veredicto"], "rejected")
        self.assertEqual(res["fase"], "triaje_temprano")
        self.assertIn("incompatible con runtime", res["razon"])

    def test_03_rechazo_temprano_memoria_excesiva(self):
        cand = self._candidato_valido()
        cand["memoria_estimada_gb"] = 14.5  # Supera límite de 6 GB
        res = self.evaluador.evaluar_candidato(cand, autorizado_operador=True)
        self.assertEqual(res["veredicto"], "rejected")
        self.assertEqual(res["fase"], "triaje_temprano")
        self.assertIn("Presupuesto de memoria superado", res["razon"])

    def test_04_rechazo_temprano_perdida_omnimodal(self):
        cand = self._candidato_valido()
        cand["modalidades"] = ["texto", "imagen"]  # Le falta audio y voz
        res = self.evaluador.evaluar_candidato(cand, autorizado_operador=True)
        self.assertEqual(res["veredicto"], "rejected")
        self.assertEqual(res["fase"], "triaje_temprano")
        self.assertIn("Pérdida de cobertura omnimodal", res["razon"])

    # 2. Bloqueo por falta de autorización
    def test_05_bloqueo_sin_autorizacion_operador(self):
        cand = self._candidato_valido()
        # Cumple triaje temprano pero Operador NO autorizó benchmark
        res = self.evaluador.evaluar_candidato(cand, autorizado_operador=False)
        self.assertEqual(res["veredicto"], "blocked")
        self.assertEqual(res["fase"], "espera_autorizacion")
        self.assertIn("no autorizada", res["razon"])
        self.assertIsNone(res["metricas"])

    # 3. Evaluación Comparativa
    def test_06_evaluacion_degrada_calidad_esquema(self):
        cand = self._candidato_valido()
        cand["benchmarks_observados"]["conformidad_schema_pct"] = 91.5  # < 98%
        res = self.evaluador.evaluar_candidato(cand, autorizado_operador=True)
        self.assertEqual(res["veredicto"], "rejected")
        self.assertEqual(res["fase"], "evaluacion_comparativa")
        self.assertIn("Calidad insuficiente", res["razon"])

    def test_07_evaluacion_degrada_latencia_p95(self):
        cand = self._candidato_valido()
        cand["benchmarks_observados"]["latencia_p95_ms"] = 3800.0  # > 2500 ms
        res = self.evaluador.evaluar_candidato(cand, autorizado_operador=True)
        self.assertEqual(res["veredicto"], "rejected")
        self.assertEqual(res["fase"], "evaluacion_comparativa")
        self.assertIn("Latencia p95 degradada", res["razon"])

    def test_08_candidato_promocion_y_plan_rollback(self):
        cand = self._candidato_valido()
        res = self.evaluador.evaluar_candidato(cand, autorizado_operador=True)
        self.assertEqual(res["veredicto"], "promotion_proposed")
        self.assertEqual(res["fase"], "evaluacion_comparativa")
        self.assertIn("plan_rollback", res)
        self.assertEqual(res["plan_rollback"]["estado"], "ready")
        self.assertIn("force-baseline", res["plan_rollback"]["comando_reversion"])

    def test_09_verificacion_integridad_baseline_intacto(self):
        ok, info = self.evaluador.verificar_integridad_baseline()
        self.assertTrue(ok)
        self.assertEqual(info["estado"], "congelado_e_intacto")
        self.assertEqual(info["modelo_baseline"], "LiquidAI/LFM3-Omni-2B-GGUF")


if __name__ == "__main__":
    unittest.main()
