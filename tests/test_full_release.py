"""Full bootstrap releases are discoverable without offering patch install."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("full_release", ROOT / "scripts/package-full-release.py")
full = importlib.util.module_from_spec(spec)
spec.loader.exec_module(full)


class FullReleaseTests(unittest.TestCase):
    def test_real_archive_metadata_and_checksum(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            release = json.loads((ROOT / "VERSION.json").read_text(encoding="utf-8"))
            release['version'] = '7.4.2'
            release["source_commit"] = "a" * 40
            archive = root / "haike-video-v7.4.2-windows-x64.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("Haike_videoflow/RELEASE.json", json.dumps(release))
            output = root / "haike-update.json"
            result = full.build(archive, output, "https://example.test/haike.zip", "首个正式版本")
            feed = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(feed["package"]["kind"], "full")
            self.assertEqual(feed["base_version"], "0.0.0")
            self.assertEqual(feed["version"], "7.4.2")
            self.assertEqual(feed["package"]["sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertTrue(Path(str(archive) + ".sha256").is_file())
            with self.assertRaises(ValueError):
                full.build(archive, output, "https://example.test/haike.zip")

    def test_unsafe_url_or_unidentified_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "empty.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("README.txt", "not an application")
            for url in ("http://example.test/update.zip", "https://example.test/update.zip"):
                with self.assertRaises(ValueError):
                    full.build(archive, root / "haike-update.json", url)
            self.assertFalse((root / "haike-update.json").exists())


if __name__ == "__main__":
    unittest.main()
