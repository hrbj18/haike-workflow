"""Authenticated account voice APIs; provider voice identifiers stay server-side."""

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from . import voice_sources, voices
from .store import Problem, owned


class VoicePreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    speech_rate: float | None = Field(default=None, ge=0.5, le=2)
    image_file_id: str | None = Field(default=None, max_length=80)


class VoiceDefault(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    voice_id: str | None = Field(max_length=80)


class VoiceReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    upstream_voice_id: str = Field(min_length=1, max_length=256)
    evidence: str = Field(min_length=10, max_length=500)


def router(store, vault, api_user, admin_user):
    routes = APIRouter()

    @routes.get("/v2/voice-sources/{job_id}")
    def sample(job_id: str, expires: str = "", signature: str = ""):
        # Only an opaque job-bound short-lived capability authorizes supplier fetches.
        # This route never accepts file IDs or a caller-provided storage path.
        return Response(
            voice_sources.read_reference(store, job_id, expires, signature),
            media_type="audio/wav",
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @routes.post("/admin/v1/gateway-jobs/{job_id}/voice-receipt")
    def receipt(job_id: str, body: VoiceReceipt, user=Depends(admin_user)):
        return voices.attach_receipt(
            store, user["id"], job_id, body.upstream_voice_id, body.evidence
        )

    @routes.get("/v2/voices")
    def catalogue(user=Depends(api_user)):
        return voices.catalogue(store, vault, user["id"])

    @routes.get("/v2/voice-preferences")
    def preferences(user=Depends(api_user)):
        with store.read() as db:
            return {"voice_id": voices.default_voice(db, user["id"])}

    @routes.put("/v2/voice-preferences")
    def default(body: VoiceDefault, user=Depends(api_user)):
        return voices.set_default(store, user["id"], body.voice_id)

    @routes.put("/v2/voices/{voice_id}/preferences")
    def configure(voice_id: str, body: VoicePreferences, user=Depends(api_user)):
        values = body.model_dump(exclude_unset=True)
        if values.get("speech_rate", 1.0) is None:
            raise Problem(422, "speech_rate_invalid", "语速倍率不能为空")
        return voices.set_preferences(store, user["id"], voice_id, values)

    @routes.delete("/v2/voices/{voice_id}")
    def disable(voice_id: str, user=Depends(api_user)):
        return voices.disable(store, user["id"], voice_id)

    @routes.get("/v2/files/{file_id}")
    def media(file_id: str, user=Depends(api_user)):
        with store.read() as db:
            row = owned(db, "gateway_files", file_id, user["id"])
        path = store.path.parent / "files" / row["id"]
        if not path.is_file():
            raise Problem(404, "file_missing", "文件已不可用，请重新上传")
        data = path.read_bytes()
        mime = (
            "audio/wav"
            if row["kind"] == "audio"
            else "image/png"
            if data.startswith(b"\x89PNG")
            else "image/jpeg"
        )
        return Response(
            data,
            media_type=mime,
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return routes
