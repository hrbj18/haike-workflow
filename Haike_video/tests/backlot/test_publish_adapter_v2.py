"""Strict offline adapter checks without a CreatorHub connection."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from backlot.publish_adapter import (
    PublishAdapterError, PublishIntent, build_publish_payload, _file_sha256,
    prepare_receipt, record_task_id, submission_key,
    require_strict_capability,
)
from backlot.publish_package import build_package, save_package


class PublishAdapterV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.video = self.root / "video.mp4"
        self.video.write_bytes(b"video fixture data")
        self.cover = self.root / "cover.jpg"
        Image.new("RGB", (600, 800), "#123456").save(self.cover)
        self.raw = self.root / "raw.png"
        Image.new("RGB", (800, 800), "#123456").save(self.raw)
        self.proof = self.root / "proof.json"
        self.proof.write_text(json.dumps({
            "kind": "ai_generated", "model": "fixture-model",
            "source_image_path": str(self.raw),
            "source_image_sha256": _file_sha256(self.raw),
            "final_cover_sha256": _file_sha256(self.cover),
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def _intent(self):
        return PublishIntent(account_id=1, platform="douyin", video_path=self.video,
                             title="fixture", cover_path=str(self.cover),
                             cover_origin="generated_ai", cover_proof_path=str(self.proof),
                             source_rights_status="owned")

    def test_required_cover_and_hash(self):
        result = build_publish_payload(self._intent())
        self.assertEqual(result.blocked, [])
        self.assertEqual(result.payload["contract_version"], 2)
        self.assertEqual(len(result.payload["cover_sha256"]), 64)
        self.assertEqual(result.payload["cover_origin"], "generated_ai")
        self.assertTrue(build_publish_payload(PublishIntent(
            account_id=1, platform="douyin", video_path=self.video,
            cover_origin="generated_ai")).blocked)
        self.cover.write_bytes(b"bad image")
        self.assertTrue(build_publish_payload(self._intent()).blocked)

    def test_receipt_reuses_key_and_rejects_changed_payload(self):
        payload = build_publish_payload(self._intent()).payload
        first, key = prepare_receipt(payload, self.root / "receipts")
        again, same_key = prepare_receipt(payload, self.root / "receipts")
        self.assertEqual((first, key), (again, same_key))
        self.assertEqual(key, submission_key(payload))
        record_task_id(first, 99)
        self.assertEqual(json.loads(first.read_text(encoding="utf-8"))["task_id"], 99)
        with self.assertRaises(PublishAdapterError):
            prepare_receipt({**payload, "title": "changed"}, self.root / "receipts")

    def test_three_platform_package_is_versioned_and_immutable(self):
        intents = {platform: PublishIntent(
            account_id=index + 1, platform=platform, video_path=self.video,
            title="阿里真武V900", cover_path=str(self.cover),
            cover_origin="generated_ai", cover_proof_path=str(self.proof),
            source_rights_status="unknown")
            for index, platform in enumerate(("douyin", "kuaishou", "shipinhao"))}
        package = build_package("v900-fixture", intents,
                                [{"source": "clip", "rights_status": "unknown"}])
        path = self.root / "package.json"
        save_package(path, package)
        save_package(path, package)
        self.assertEqual(len(package["platforms"]), 3)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["package_id"],
                         package["package_id"])
        with self.assertRaises(ValueError):
            save_package(path, {**package, "package_revision": 2})
        for intent in intents.values():
            intent.source_rights_status = "confirmed"
        with self.assertRaises(ValueError):
            build_package("v900-fixture", intents,
                          [{"source": "clip", "rights_status": "unknown"}])

    def test_old_service_capability_is_rejected(self):
        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return b'{"contract_version": 1}'
        with patch("backlot.publish_adapter.request.urlopen", return_value=FakeResponse()):
            with self.assertRaises(PublishAdapterError):
                require_strict_capability("http://127.0.0.1:8000", "douyin")


if __name__ == "__main__":
    unittest.main()
