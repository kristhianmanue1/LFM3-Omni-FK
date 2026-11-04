"""Pruebas de B-T10 (recursos) — SPEC I0 §8. Contrato: sin PID de
listener no hay pass; el pid deriva del listener con verificación de
propiedad; se miden RSS, swap y artefactos mmapeados."""

import io
import unittest
from unittest import mock

from tests import run_golden as rg

# La medición pura es el contrato de test: sin cargar el motor.
BT10 = rg._bt10_medir

LSOF_CON_LISTENER = (
    "COMMAND     PID USER   FD   TYPE             DEVICE SIZE/OFF NODE\n"
    "llama-serv 4242 kris    5u  IPv4  0xdeadbeef      0t0  TCP 127.0.0.1:8091 (LISTEN)\n"
)
LSOF_VACIO = "COMMAND     PID USER   FD   TYPE DEVICE SIZE/OFF NODE\n"
PS_LLAMA = ("/opt/homebrew/bin/llama-server -hf LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M"
            " --host 127.0.0.1 --port 8091 --reasoning off --temp 0\n")
PS_AJENO = ("/bin/sh -c sleep 60 # llama-server --port 8091\n")
SWAP_OK = "vm.swapusage: total = 2048.00MiB  used = 128.00MiB  free = 1920.00MiB\n"
SWAP_MAL = "vm.swapusage: total = 4096.00MiB  used = 3072.00MiB  free = 1024.00MiB\n"


def _fake_run(cmd, **_):
    """Sustituto de subprocess.run con salidas canned por comando."""
    class R:
        def __init__(self, out):
            self.stdout = out

    c = cmd[0]
    if c == "lsof":
        return R(_fake_run.lsof)
    if c == "ps" and "-o" in cmd and "command=" in cmd:
        return R(_fake_run.ps_command)
    if c == "ps":
        return R(_fake_run.ps_rss)
    if c == "sysctl":
        return R(_fake_run.swap)
    return R("")


class Bt10(unittest.TestCase):
    def setUp(self):
        _fake_run.lsof = LSOF_CON_LISTENER
        _fake_run.ps_command = PS_LLAMA
        _fake_run.ps_rss = "1048576"  # 1024 MiB en KiB
        _fake_run.swap = SWAP_OK

    def _con_fixtures(self):
        return mock.patch.object(rg.subprocess, "run", _fake_run)

    def test_r19_sin_pid_de_listener_no_hay_pass(self):
        _fake_run.lsof = LSOF_VACIO
        with self._con_fixtures():
            self.assertFalse(BT10(),
                             "B-T10 pasó sin pid de listener")

    def test_r19_dos_listeners_no_hay_pass(self):
        _fake_run.lsof = LSOF_CON_LISTENER + LSOF_CON_LISTENER
        with self._con_fixtures():
            self.assertFalse(BT10())

    def test_r19_pid_reciclado_o_ajeno_no_hay_pass(self):
        _fake_run.ps_command = PS_AJENO
        with self._con_fixtures():
            self.assertFalse(BT10(),
                             "B-T10 midió un pid que no es del motor")

    def test_r19_rss_sobre_umbral_falla(self):
        _fake_run.ps_rss = str(5 * 1024 * 1024)  # 5 GiB en KiB
        with self._con_fixtures():
            self.assertFalse(BT10())

    def test_r19_swap_se_reporta_sin_atribuir_ni_umbral(self):
        """El swap es global del host: se reporta, no revierte el pass
        ni se atribuye al motor (SPEC I0 §8, enmienda)."""
        _fake_run.swap = SWAP_MAL
        buffer = io.StringIO()
        with self._con_fixtures(), \
                mock.patch.object(rg, "_artefactos_bytes", return_value=1_200_000_000), \
                mock.patch("sys.stdout", buffer):
            self.assertTrue(BT10(),
                            "el swap del host no debe revertir el gate atribuible")
        self.assertIn("swap", buffer.getvalue())
        self.assertIn("no atribuible", buffer.getvalue())

    def test_r19_condicion_sana_pasa_y_reporta(self):
        with self._con_fixtures(), \
                mock.patch.object(rg, "_artefactos_bytes", return_value=1_200_000_000):
            self.assertTrue(BT10())

    def test_r19_rss_vacio_no_hay_pass(self):
        _fake_run.ps_rss = ""
        with self._con_fixtures():
            self.assertFalse(BT10(),
                             "RSS vacío (pid desaparecido entre lsof y ps) "
                             "no puede pasar")

    def test_red_comportamiento_actual_con_pgrep_vacio(self):
        """Regresión del defecto original (RED de I0): el runner viejo
        medía con pgrep laxo y pasaba vacuo sin pid. El contrato vigente
        exige False con listener vacío, sea cual sea la fuente."""
        def solo_pgrep(cmd, **_):
            class R:
                stdout = "" if cmd[0] == "pgrep" else ""
            return R()

        with mock.patch.object(rg.subprocess, "run", solo_pgrep):
            self.assertFalse(BT10(),
                             "el runner vigente pasa sin pid: defecto confirmado")


if __name__ == "__main__":
    unittest.main()
