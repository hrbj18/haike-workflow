import base64
import io
import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from image_refinement.api import create_app
from image_refinement.client import LocalClient, RemoteClient
from image_refinement.provider import RefinementError, ResponsesProvider, Settings
from image_refinement.service import RefinementService


def picture(size=(640, 800), color="navy"):
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, "PNG")
    return output.getvalue()


class FakeProvider:
    def __init__(self):
        self.calls = []

    def edit(self, raw, mime, prompt):
        self.calls.append((raw, mime, prompt))
        return picture((800, 1000), "teal"), {"fixture": True}


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="refine-kit-")
        self.root = Path(self.temp.name)
        self.settings = Settings(api_key="test-placeholder")
        self.provider = FakeProvider()
        self.service = RefinementService(
            self.root, settings=self.settings, provider=self.provider
        )
        self.source = picture()

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def submit(self, **kwargs):
        return self.service.submit(
            self.source, "account:project", confirmed=True, **kwargs
        )

    def test_confirmation_required_before_queueing(self):
        with self.assertRaises(RefinementError):
            self.service.submit(self.source, "account:project")
        self.assertFalse(self.service.process_one())

    def test_delivery_preserves_source_and_raw(self):
        job = self.submit()
        self.service.process_one()
        self.assertEqual(
            self.service.get(job["id"], "account:project")["status"], "succeeded"
        )
        self.assertEqual(
            self.service.file(job["id"], "account:project", "source"), self.source
        )
        raw = self.service.file(job["id"], "account:project", "raw")
        result = self.service.file(job["id"], "account:project", "result")
        with Image.open(io.BytesIO(raw)) as image:
            self.assertEqual(image.size, (800, 1000))
        with Image.open(io.BytesIO(result)) as image:
            self.assertEqual((image.size, image.mode), ((1024, 1280), "RGB"))

    def test_duplicate_upload_deduplicates(self):
        first, second = self.submit(), self.submit()
        self.assertEqual(first["id"], second["id"])
        self.service.process_one()
        self.assertFalse(self.service.process_one())
        self.assertEqual(len(self.provider.calls), 1)

    def test_namespace_isolation(self):
        job = self.submit()
        with self.assertRaises(RefinementError):
            self.service.get(job["id"], "other:project")
        with self.assertRaises(RefinementError):
            self.service.submit(self.source, "../../escape", confirmed=True)

    def test_prompt_and_models_are_frozen_across_restart(self):
        old = RefinementService(
            self.root,
            settings=self.settings,
            provider=self.provider,
            prompt="Old frozen prompt",
            preset_version="custom-v1",
        )
        job = old.submit(self.source, "account:project", confirmed=True)
        changed = RefinementService(
            self.root,
            settings=self.settings,
            provider=self.provider,
            prompt="New prompt",
            preset_version="custom-v2",
        )
        changed.process_one()
        self.assertEqual(self.provider.calls[0][2], "Old frozen prompt")
        self.assertEqual(
            changed.get(job["id"], "account:project")["config"]["preset_version"],
            "custom-v1",
        )

    def test_unknown_outcome_never_retries_automatically(self):
        def uncertain(*args):
            self.provider.calls.append(args)
            raise RefinementError("Unknown fixture outcome", uncertain=True)

        self.provider.edit = uncertain
        job = self.submit()
        self.service.process_one()
        self.assertEqual(
            self.service.get(job["id"], "account:project")["status"], "ambiguous"
        )
        self.assertFalse(self.service.process_one())
        with self.assertRaises(RefinementError):
            self.submit(retry_of=job["id"])
        retried = self.submit(retry_of=job["id"], acknowledge_uncertain=True)
        self.assertEqual(
            self.submit(retry_of=job["id"], acknowledge_uncertain=True)["id"],
            retried["id"],
        )
        self.assertEqual(len(self.provider.calls), 1)

    def test_received_raw_is_reused_on_local_failure(self):
        job = self.submit()
        with patch(
            "image_refinement.service.normalize", side_effect=ValueError("fixture")
        ):
            self.service.process_one()
        self.assertEqual(
            self.service.get(job["id"], "account:project")["status"], "failed"
        )
        self.submit(retry_of=job["id"])
        self.service.process_one()
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(
            self.service.get(job["id"], "account:project")["status"], "succeeded"
        )

    def test_changed_credentials_do_not_dispatch_old_task(self):
        job = self.submit()
        changed = RefinementService(
            self.root,
            settings=Settings(api_key="other-test-account"),
            provider=self.provider,
        )
        changed.process_one()
        self.assertEqual(
            changed.get(job["id"], "account:project")["error_code"],
            "configuration_changed",
        )
        self.assertEqual(len(self.provider.calls), 0)

    def test_daily_limit(self):
        self.service.settings = Settings(api_key="test-placeholder", daily_limit=1)
        self.submit()
        self.service.process_one()
        job = self.service.submit(
            picture(color="red"), "account:project", confirmed=True
        )
        self.service.process_one()
        self.assertEqual(
            self.service.get(job["id"], "account:project")["error_code"], "daily_limit"
        )
        self.assertEqual(len(self.provider.calls), 1)

    def test_expired_running_lease_becomes_ambiguous(self):
        job = self.submit()
        with self.service.connect() as db:
            db.execute(
                "UPDATE jobs SET status='running',updated=0,dispatched=1 WHERE id=?",
                (job["id"],),
            )
        self.assertEqual(
            self.service.get(job["id"], "account:project")["status"], "ambiguous"
        )
        self.assertFalse(self.service.process_one())

    def test_two_workers_share_single_channel(self):
        started, release = threading.Event(), threading.Event()

        def slow(*args):
            started.set()
            release.wait(5)
            return picture(), {}

        self.provider.edit = slow
        self.submit()
        other = RefinementService(
            self.root, settings=self.settings, provider=self.provider
        )
        thread = threading.Thread(target=self.service.process_one)
        thread.start()
        try:
            self.assertTrue(started.wait(2))
            self.assertFalse(other.process_one())
        finally:
            release.set()
            thread.join(5)

    def test_http_auth_confirmation_ownership_and_files(self):
        app = create_app(self.service, token="internal-test-token")
        client = TestClient(app)
        headers = {
            "Authorization": "Bearer internal-test-token",
            "Content-Type": "application/octet-stream",
        }
        self.assertEqual(client.get("/v1/config").status_code, 401)
        self.assertEqual(
            client.post(
                "/v1/jobs?namespace=a", content=self.source, headers=headers
            ).status_code,
            409,
        )
        response = client.post(
            "/v1/jobs?namespace=a&confirmed=true", content=self.source, headers=headers
        )
        self.assertEqual(response.status_code, 200)
        identifier = response.json()["id"]
        self.service.process_one()
        self.assertEqual(
            client.get(
                f"/v1/jobs/{identifier}?namespace=b", headers=headers
            ).status_code,
            404,
        )
        result = client.get(
            f"/v1/jobs/{identifier}/files/result?namespace=a", headers=headers
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.headers["content-type"], "image/png")
        with self.assertRaises(ValueError):
            create_app(self.service, token="")

    def test_local_client_supports_confirmed_flag(self):
        client = LocalClient(self.service)
        with self.assertRaises(RefinementError):
            client.submit(self.source, "account:project")
        client.close()

    def test_host_router_requires_scope_and_hides_internal_configuration(self):
        path = Path(__file__).resolve().parents[1] / "examples/fastapi_router.py"
        spec = importlib.util.spec_from_file_location("host_bridge_example", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        def authorized(request):
            account = request.headers.get("x-fixture-account")
            if account not in {"a", "b"}:
                raise HTTPException(403, "fixture unauthorized")
            return account + ":project"

        app = FastAPI()
        app.include_router(module.make_router(self.service, authorized))
        client = TestClient(app)
        self.assertEqual(
            client.post(
                "/refinement/jobs?confirmed=true", content=self.source
            ).status_code,
            403,
        )
        response = client.post(
            "/refinement/jobs?confirmed=true",
            content=self.source,
            headers={"x-fixture-account": "a"},
        )
        self.assertEqual(response.status_code, 200)
        value = response.json()
        self.assertNotIn("base_url", value["config"])
        self.assertNotIn("credential_fingerprint", value["config"])
        self.assertEqual(
            client.get(
                "/refinement/jobs/" + value["id"], headers={"x-fixture-account": "b"}
            ).status_code,
            404,
        )

    def test_remote_client_carries_confirmation_without_exposing_key(self):
        client = RemoteClient("http://127.0.0.1:4765", "internal-test-token")
        reply = Mock()
        reply.read.return_value = b'{"id":"fixture"}'
        with patch("urllib.request.urlopen") as send:
            send.return_value.__enter__.return_value = reply
            self.assertEqual(
                client.submit(self.source, "a:p", confirmed=True)["id"], "fixture"
            )
        self.assertIn("confirmed=true", send.call_args.args[0].full_url)


class TransportTests(unittest.TestCase):
    def test_reference_image_responses_contract_single_attempt(self):
        raw = picture()
        value = {
            "id": "fixture-response",
            "status": "completed",
            "usage": {"input_tokens": 12},
            "output": [
                {
                    "id": "fixture-tool",
                    "type": "image_generation_call",
                    "status": "completed",
                    "result": base64.b64encode(raw).decode(),
                }
            ],
        }
        reply = Mock()
        reply.read.return_value = json.dumps(value).encode()
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = reply
        with patch("urllib.request.build_opener", return_value=opener):
            result, metadata = ResponsesProvider(
                Settings(api_key="test-placeholder")
            ).edit(raw, "image/png", "Preset")
        self.assertEqual(opener.open.call_count, 1)
        request = opener.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertTrue(request.full_url.endswith("/v1/responses"))
        self.assertEqual(payload["model"], "gpt-5.6")
        self.assertEqual(payload["tools"][0]["model"], "gpt-image-2")
        self.assertEqual(
            payload["input"][0]["content"][1]["image_url"],
            "data:image/png;base64," + base64.b64encode(raw).decode(),
        )
        self.assertEqual(result, raw)
        self.assertNotIn("test-placeholder", repr(metadata))

    def test_transport_timeout_is_unknown_and_not_retried(self):
        opener = Mock()
        opener.open.side_effect = TimeoutError("fixture")
        with patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaises(RefinementError) as result:
                ResponsesProvider(Settings(api_key="test-placeholder")).edit(
                    picture(), "image/png", "Preset"
                )
        self.assertTrue(result.exception.uncertain)
        self.assertEqual(opener.open.call_count, 1)

    def test_malformed_output_is_unknown(self):
        reply = Mock()
        reply.read.return_value = b'{"output":[null]}'
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = reply
        with patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaises(RefinementError) as result:
                ResponsesProvider(Settings(api_key="test-placeholder")).edit(
                    picture(), "image/png", "Preset"
                )
        self.assertTrue(result.exception.uncertain)


if __name__ == "__main__":
    unittest.main()
