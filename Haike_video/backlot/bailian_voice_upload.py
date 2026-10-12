"""Bounded reference intake for cloud enrollment; never accept a server path."""
import asyncio
from pathlib import Path
import tempfile

from fastapi import HTTPException, Request
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException

from backlot import bailian_voice_clone as clone
from backlot.audio_center import AudioCenterError
from backlot.local_voice_upload import _VoiceMultipartParser, _UploadTooLarge
from lib.bailian_speech import BailianSpeechError, safe_error


class _CloudParser(_VoiceMultipartParser):
    max_audio_bytes = clone.MAX_UPLOAD_BYTES
    size_error = "云端克隆参考录音不能超过 10 MB"


async def receive_cloud_clone(request: Request) -> dict:
    if request.headers.get("content-type", "").split(";", 1)[0].lower().strip() != "multipart/form-data":
        raise HTTPException(415, "请上传录音表单")
    limit = clone.MAX_UPLOAD_BYTES + 64 * 1024
    try:
        declared = int(request.headers.get("content-length", "0"))
    except ValueError:
        raise HTTPException(400, "上传请求大小无效") from None
    if declared < 0:
        raise HTTPException(400, "上传请求大小无效")
    if declared > limit:
        raise HTTPException(413, _CloudParser.size_error)

    async def stream():
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > limit:
                raise _UploadTooLarge(_CloudParser.size_error)
            for offset in range(0, len(chunk), 64 * 1024):
                yield chunk[offset:offset + 64 * 1024]

    parser = _CloudParser(request.headers, stream(), max_files=1, max_fields=3)
    parser.max_part_size = 24 * 1024
    form = None
    try:
        form = await parser.parse()
        if sorted(k for k, _ in form.multi_items()) != ["audio", "consent", "model_id", "name"]:
            raise HTTPException(422, "仅接受名称、模型、上传授权确认和一份录音")
        name, model = clone.validate_fields(form.get("name"), form.get("model_id"), form.get("consent"))
        audio = form.get("audio")
        if not isinstance(audio, UploadFile) or Path(audio.filename or "").suffix.lower() not in {".wav", ".mp3", ".m4a"}:
            raise HTTPException(422, "请上传 WAV、MP3 或 M4A 参考录音")
        with tempfile.TemporaryDirectory(prefix="haike-cloud-upload-") as scratch:
            path = Path(scratch) / "reference.audio"
            count = 0
            with path.open("wb") as handle:
                while chunk := await audio.read(64 * 1024):
                    count += len(chunk)
                    if count > clone.MAX_UPLOAD_BYTES:
                        raise _UploadTooLarge(_CloudParser.size_error)
                    handle.write(chunk)
            return await asyncio.to_thread(clone.create_voice, name, model, path, "yes")
    except _UploadTooLarge:
        raise HTTPException(413, _CloudParser.size_error) from None
    except MultiPartException:
        raise HTTPException(422, "录音表单无效，只能上传一份录音，并填写名称、模型和授权确认") from None
    except (AudioCenterError, BailianSpeechError) as exc:
        raise HTTPException(422, safe_error(exc)) from exc
    except OSError:
        raise HTTPException(422, "录音保存失败，请检查临时目录权限与可用空间") from None
    finally:
        if form is not None:
            await form.close()
        else:
            for handle in parser._files_to_close_on_error:
                handle.close()
