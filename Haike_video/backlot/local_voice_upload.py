"""Bounded multipart intake for private local voice references."""
from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile

from fastapi import HTTPException, Request
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from backlot.audio_center import (
    AudioCenterError,
    MAX_LOCAL_VOICE_UPLOAD_BYTES,
    add_local_clone_voice,
    validate_local_clone_fields,
)

_CHUNK_BYTES = 64 * 1024
_FORM_OVERHEAD_BYTES = 64 * 1024
_MAX_FIELD_BYTES = 24 * 1024


class _UploadTooLarge(MultiPartException):
    pass


class _VoiceMultipartParser(MultiPartParser):
    """Enforce file size before Starlette writes any overflow to its spool."""

    max_audio_bytes = MAX_LOCAL_VOICE_UPLOAD_BYTES
    size_error = "参考录音不能超过 20 MB"

    def on_part_begin(self) -> None:
        super().on_part_begin()
        self._voice_part_bytes = 0

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        self._voice_part_bytes += end - start
        if self._current_part.file is not None:
            if self._voice_part_bytes > self.max_audio_bytes:
                raise _UploadTooLarge(self.size_error)
        elif self._voice_part_bytes > _MAX_FIELD_BYTES:
            raise MultiPartException("音色名称或参考录音原文过长")
        super().on_part_data(data, start, end)


async def receive_local_clone_voice(request: Request) -> dict:
    """Read only name/text/audio; no client-supplied server path is accepted."""
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "multipart/form-data":
        raise HTTPException(status_code=415, detail="请使用表单上传参考录音、音色名称和逐字原文")
    max_request_bytes = MAX_LOCAL_VOICE_UPLOAD_BYTES + _FORM_OVERHEAD_BYTES
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            declared_bytes = int(declared)
        except ValueError:
            raise HTTPException(status_code=400, detail="上传请求大小无效") from None
        if declared_bytes < 0:
            raise HTTPException(status_code=400, detail="上传请求大小无效")
        if declared_bytes > max_request_bytes:
            raise HTTPException(status_code=413, detail="参考录音不能超过 20 MB")

    async def limited_stream():
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > max_request_bytes:
                raise _UploadTooLarge("参考录音不能超过 20 MB")
            # Bound each parser write even when an ASGI implementation hands
            # the application a whole upload as one large receive event.
            for offset in range(0, len(chunk), _CHUNK_BYTES):
                yield chunk[offset:offset + _CHUNK_BYTES]

    parser = _VoiceMultipartParser(request.headers, limited_stream(), max_files=1, max_fields=2)
    parser.max_part_size = _MAX_FIELD_BYTES
    form = None
    try:
        form = await parser.parse()
        if sorted(key for key, _value in form.multi_items()) != ["audio", "name", "reference_text"]:
            raise HTTPException(status_code=422, detail="仅接受音色名称、逐字原文和一份参考录音")
        name, text = validate_local_clone_fields(form.get("name"), form.get("reference_text"))
        audio = form.get("audio")
        if not isinstance(audio, UploadFile):
            raise HTTPException(status_code=422, detail="请上传参考录音文件")
        with tempfile.TemporaryDirectory(prefix="haike-local-voice-upload-") as scratch:
            temporary = Path(scratch) / "reference.audio"
            received = 0
            with temporary.open("wb") as handle:
                while chunk := await audio.read(_CHUNK_BYTES):
                    received += len(chunk)
                    if received > MAX_LOCAL_VOICE_UPLOAD_BYTES:
                        raise _UploadTooLarge("参考录音不能超过 20 MB")
                    handle.write(chunk)
            return await asyncio.to_thread(add_local_clone_voice, name, text, temporary)
    except _UploadTooLarge as exc:
        raise HTTPException(status_code=413, detail=exc.message) from None
    except MultiPartException:
        raise HTTPException(status_code=422, detail="录音表单无效，名称和原文必填，且只能上传一份参考录音") from None
    except AudioCenterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError:
        raise HTTPException(status_code=422, detail="无法保存参考录音临时文件，请检查本机临时目录权限与可用空间") from None
    finally:
        if form is not None:
            await form.close()
        else:
            # Also support Starlette releases that only close multipart files
            # for MultiPartException rather than disconnect/cancellation.
            for temporary_file in parser._files_to_close_on_error:
                temporary_file.close()
