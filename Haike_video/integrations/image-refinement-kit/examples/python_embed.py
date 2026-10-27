"""Import into a host backend; creation does not submit paid requests."""

from pathlib import Path

from image_refinement.client import LocalClient
from image_refinement.provider import Settings
from image_refinement.service import RefinementService


def create_client(private_directory: Path) -> LocalClient:
    # The host loads IMAGE_REFINEMENT_* into its backend environment first.
    # Keep this singleton for the application lifetime; call client.close().
    return LocalClient(
        RefinementService(private_directory, settings=Settings.from_env())
    )


def submit_authorized_upload(
    client, content: bytes, *, account_id: str, project_id: str, confirmed: bool
):
    # account_id/project_id must come from the host's authorization result.
    namespace = f"{account_id}:{project_id}"
    job = client.submit(content, namespace, confirmed=confirmed)
    # Persist job.id with source asset ID/revision before returning to browser.
    return job


def custom_preset_service(private_directory: Path, prompt: str, version: str):
    return RefinementService(
        private_directory,
        settings=Settings.from_env(),
        prompt=prompt,
        preset_version=version,
    )
