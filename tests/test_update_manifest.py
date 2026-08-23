import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.build_update_manifest import build_manifest


class UpdateManifestBuilderTests(unittest.TestCase):
    def test_manifest_hash_is_generated_from_installer_bytes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            installer = Path(temp_dir) / "setup.exe"
            installer.write_bytes(b"real installer bytes")
            manifest = build_manifest(
                installer,
                "2.1.0",
                "https://updates.example/setup.exe",
                "Reliable release",
            )
            self.assertEqual(
                manifest["sha256"],
                hashlib.sha256(b"real installer bytes").hexdigest(),
            )
            self.assertEqual(manifest["installer"], "setup.exe")

    def test_manifest_rejects_non_https_or_non_installer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "setup.bin"
            file_path.write_bytes(b"x")
            with self.assertRaises(ValueError):
                build_manifest(file_path, "2.1.0", "https://updates.example/setup", "")


if __name__ == "__main__":
    unittest.main()
