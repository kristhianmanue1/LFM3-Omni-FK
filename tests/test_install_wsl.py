"""Integridad de descargas y contención de archivos del instalador WSL."""

import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "install_wsl", Path(__file__).resolve().parents[1] / "scripts/install_wsl.py")
wsl = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wsl)


class InstallationIntegrity(unittest.TestCase):
    def test_download_corrupt_never_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "model.gguf"
            with patch.object(wsl.urllib.request, "urlopen",
                              return_value=io.BytesIO(b"corrupt")):
                with self.assertRaises(ValueError):
                    wsl.download("https://example.invalid/model", dest,
                                 hashlib.sha256(b"expected").hexdigest())
            self.assertFalse(dest.exists())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_cached_corrupt_not_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "model.gguf"
            dest.write_bytes(b"corrupt")
            with patch.object(wsl.urllib.request, "urlopen") as network:
                with self.assertRaises(ValueError):
                    wsl.download("https://example.invalid/model", dest,
                                 hashlib.sha256(b"expected").hexdigest())
                network.assert_not_called()
            self.assertEqual(dest.read_bytes(), b"corrupt")

    def test_valid_download_then_offline_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "model.gguf"
            expected = hashlib.sha256(b"valid").hexdigest()
            with patch.object(wsl.urllib.request, "urlopen",
                              return_value=io.BytesIO(b"valid")) as network:
                wsl.download("https://example.invalid/model", dest, expected)
                wsl.download("https://example.invalid/model", dest, expected)
                self.assertEqual(network.call_count, 1)
            self.assertEqual(dest.read_bytes(), b"valid")

    def test_tar_traversal_and_symlink_escape_rejected(self):
        for name, link in (("../escaped", None), ("/escaped", None),
                           ("link", "../../escaped")):
            with self.subTest(name=name, link=link), tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp) / "input.tar.gz"
                with tarfile.open(archive, "w:gz") as out:
                    entry = tarfile.TarInfo(name)
                    if link:
                        entry.type = tarfile.SYMTYPE
                        entry.linkname = link
                    out.addfile(entry)
                with self.assertRaises((ValueError, tarfile.FilterError)):
                    wsl.extract(archive, Path(tmp) / "destination")
                self.assertFalse((Path(tmp) / "escaped").exists())

    def test_runtime_tampering_and_added_files_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "llama-server").write_bytes(b"binary")
            inventory = wsl.inventory(root)
            wsl.verify_inventory(root, inventory)
            (root / "extra.so").write_bytes(b"extra")
            with self.assertRaises(ValueError):
                wsl.verify_inventory(root, inventory)
            (root / "extra.so").unlink()
            (root / "llama-server").write_bytes(b"changed")
            with self.assertRaises(ValueError):
                wsl.verify_inventory(root, inventory)

    def test_installation_lock_rejects_second_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "install.lock"
            with wsl.installation_lock(lock):
                with self.assertRaises(BlockingIOError):
                    with wsl.installation_lock(lock):
                        self.fail("segundo escritor admitido")


if __name__ == "__main__":
    unittest.main()
