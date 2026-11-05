"""Pruebas de empaquetado, consentimiento, VAD y WS sin dispositivos reales."""
import array
import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import queue
import struct
import threading
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('live_voice', 'live_video', 'realtime_english',
         'continuous_english', 'continuous_unlimited')


def load(name):
    path = ROOT / 'examples/wsl' / (name + '.py')
    spec = importlib.util.spec_from_file_location('wsl_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WslExamples(unittest.TestCase):
    def test_imports_resolve_without_tmp_or_user_home(self):
        for name in NAMES:
            with self.subTest(name=name):
                module = load(name)
                source = Path(module.__file__).read_text()
                self.assertNotIn('/tmp/', source)
                self.assertNotIn('/home/', source)

    def test_missing_consent_never_opens_devices(self):
        for name in NAMES:
            with self.subTest(name=name), patch.dict(os.environ, {}, clear=True):
                module = load(name)
                with patch.object(module.subprocess, 'Popen') as spawn, \
                        patch.object(module.subprocess, 'run') as run:
                    with self.assertRaisesRegex(ValueError, 'D09'):
                        module.main()
                    spawn.assert_not_called()
                    run.assert_not_called()

    def test_ping_pong_preserves_payload_and_next_event(self):
        module = load('realtime_english')
        raw = json.dumps({'type': 'session.updated'}).encode()

        class Connection:
            data = bytearray(b'\x89\x02hi\x8a\x00' + bytes([0x81, len(raw)]) + raw)
            sent = b''

            def recv(self, size):
                result = bytes(self.data[:size])
                del self.data[:size]
                return result

            def sendall(self, data):
                self.sent += data

        connection = Connection()
        self.assertEqual(module.receive(connection), {'type': 'session.updated'})
        self.assertEqual(connection.sent[:2], b'\x8a\x82')
        mask = connection.sent[2:6]
        decoded = bytes(value ^ mask[i % 4]
                        for i, value in enumerate(connection.sent[6:]))
        self.assertEqual(decoded, b'hi')

    def test_oversized_ws_frame_rejected_before_payload_read(self):
        module = load('realtime_english')
        connection = Mock()
        connection.recv.side_effect = [b'\x81\x7f', struct.pack('>Q', 2**21 + 1)]
        with self.assertRaises(ValueError):
            module.receive(connection)
        self.assertEqual(connection.recv.call_count, 2)

    def test_voice_end_and_duration_cap_close_microphone(self):
        module = load('continuous_unlimited')
        silence, speech = bytes(3200), array.array('h', [1500] * 1600).tobytes()
        for frames, size in (([silence] * 300 + [speech] * 3 + [silence] * 10, 48000),
                             ([speech] * 205, 640000)):
            with self.subTest(size=size):
                process, session = Mock(), Mock()
                with patch.object(module.subprocess, 'Popen', return_value=process), \
                        patch.object(module.select, 'select', return_value=([process.stdout], [], [])), \
                        patch.object(module.os, 'read', side_effect=iter(frames)), \
                        patch.object(module.voice, 'stop') as stop:
                    result = module.listen(session)
                    self.assertEqual(len(result), size)
                    stop.assert_called_once_with(process)
                    if size == 48000:
                        self.assertGreater(session.check.call_count, 300)

    def test_interruption_closes_microphone(self):
        module = load('continuous_unlimited')
        process = Mock()
        with patch.object(module.subprocess, 'Popen', return_value=process), \
                patch.object(module.select, 'select', side_effect=KeyboardInterrupt), \
                patch.object(module.voice, 'stop') as stop:
            with self.assertRaises(KeyboardInterrupt):
                module.listen(Mock())
            stop.assert_called_once_with(process)

    def test_goodbye_detection_uses_local_asr_without_files(self):
        module = load('continuous_english')
        for text, expected in (('Goodbye.', True), ('Tell me about space.', False)):
            with self.subTest(text=text), patch.object(
                    module.urllib.request, 'urlopen',
                    return_value=io.BytesIO(json.dumps({'text': text}).encode())) as http:
                self.assertEqual(module.wants_to_end(bytes(32000)), expected)
                self.assertTrue(http.call_args.args[0].full_url.startswith('http://127.0.0.1:8091/'))

    def test_reader_handles_heartbeat_and_stops_on_close(self):
        module = load('continuous_unlimited')
        raw = json.dumps({'type': 'session.created'}).encode()

        class Socket:
            def __init__(self):
                self.data = bytearray(b'\x89\x00' + bytes([0x81, len(raw)]) + raw)
                self.closed = threading.Event()
                self.sent = b''

            def recv(self, size):
                if self.data:
                    result = bytes(self.data[:size])
                    del self.data[:size]
                    return result
                self.closed.wait(timeout=3)
                raise OSError('closed')

            def sendall(self, data):
                self.sent += data

            def shutdown(self, how):
                self.closed.set()

            def close(self):
                self.closed.set()

        session = module.Session.__new__(module.Session)
        session.socket = Socket()
        session.lock = threading.RLock()
        session.events = queue.Queue(maxsize=64)
        session.failure = None
        session.closed = threading.Event()
        session.reader = threading.Thread(target=session._read, daemon=True)
        session.reader.start()
        try:
            self.assertEqual(session.next()['type'], 'session.created')
            self.assertEqual(session.socket.sent[:2], b'\x8a\x80')
        finally:
            session.close()
        self.assertFalse(session.reader.is_alive())


if __name__ == '__main__':
    unittest.main()
