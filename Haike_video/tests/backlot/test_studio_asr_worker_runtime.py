"""Offline worker boundary: fake decoder/model, actual ndarray and UTF-8 output."""
import importlib.util
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/studio_asr_worker.py"


@pytest.fixture
def worker(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("offline_studio_worker_fixture",SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "本地音轨.wav"
    source.write_bytes(b"offline source fixture")
    monkeypatch.setattr(module,"resolve_ffmpeg",lambda:"fixture-local-ffmpeg")
    return SimpleNamespace(module=module,source=source,root=tmp_path)


def test_decoder_hands_model_a_real_float32_mono_array_instead_of_a_pyav_file_path(worker,monkeypatch):
    calls=[]
    def decode(command,**kwargs):
        calls.append((command,kwargs))
        return SimpleNamespace(returncode=0,stdout=np.array([0,.5,-.5],dtype="<f4").tobytes(),stderr=b"")
    monkeypatch.setattr(subprocess,"run",decode)
    samples=worker.module.decode_for_whisper(worker.source)
    np.testing.assert_array_equal(samples,np.array([0,.5,-.5],dtype=np.float32))
    assert samples.ndim==1 and samples.dtype==np.float32
    command,options=calls[0]
    assert command[command.index("-i")+1]==str(worker.source)
    assert command[command.index("-ar")+1]=="16000"
    assert command[command.index("-ac")+1]=="1"
    assert options["timeout"]<=60 and options["capture_output"] is True
    assert float(command[command.index("-t")+1])<=121


@pytest.mark.parametrize("content", [b"",b"bad",np.array([np.nan],dtype="<f4").tobytes(),b"\0"*(int(120.5*16000)*4)],
                         ids=["empty","unaligned","nonfinite","overlong"])
def test_decoder_rejects_empty_bad_nonfinite_and_overlong_pcm_without_partial_result(worker,monkeypatch,content):
    monkeypatch.setattr(subprocess,"run",lambda *a,**k:SimpleNamespace(returncode=0,stdout=content,stderr=b"SECRET_DECODER_DETAILS"))
    with pytest.raises(RuntimeError) as caught:
        worker.module.decode_for_whisper(worker.source)
    assert "SECRET" not in str(caught.value)
    assert not list(worker.root.glob("*.json"))


def test_decoder_timeout_is_safe_and_does_not_launch_recognition(worker,monkeypatch):
    def timeout(*args,**kwargs):
        raise subprocess.TimeoutExpired("SECRET_COMMAND",60)
    monkeypatch.setattr(subprocess,"run",timeout)
    with pytest.raises(RuntimeError) as caught:
        worker.module.decode_for_whisper(worker.source)
    assert "SECRET" not in str(caught.value)


def test_worker_writes_exact_chinese_and_emoji_word_clock_as_utf8_under_ansi_default(worker,monkeypatch):
    monkeypatch.setattr(subprocess,"run",lambda *a,**k:SimpleNamespace(returncode=0,stdout=np.zeros(16000,dtype="<f4").tobytes(),stderr=b""))
    captured={}
    class WhisperModel:
        def __init__(self,*args,**kwargs):
            captured["model_options"]=kwargs
        def transcribe(self,audio,**kwargs):
            assert isinstance(audio,np.ndarray), "Passing a file path would re-enter incompatible PyAV"
            assert audio.shape==(16000,)
            captured["transcribe_options"]=kwargs
            words=[SimpleNamespace(start=.1,end=.4,word="海客",probability=.9),SimpleNamespace(start=.4,end=.8,word="🤖",probability=.8)]
            return [SimpleNamespace(start=.1,end=.8,text="海客🤖",words=words)],None
    monkeypatch.setitem(sys.modules,"faster_whisper",SimpleNamespace(WhisperModel=WhisperModel))
    original=os.fdopen
    def ansi_default(fd,mode="r",*args,**kwargs):
        if "b" not in mode and "encoding" not in kwargs:
            kwargs["encoding"]="cp936"
        return original(fd,mode,*args,**kwargs)
    monkeypatch.setattr(os,"fdopen",ansi_default)
    output=worker.root/"result.json"
    monkeypatch.setattr(sys,"argv",[str(SCRIPT),"--model-dir",str(worker.root/"model"),"--audio",str(worker.source),"--output",str(output)])
    worker.module.main()
    result=json.loads(output.read_text(encoding="utf-8"))
    assert result=={"segments":[{"start":.1,"end":.8,"text":"海客🤖","words":[
        {"start":.1,"end":.4,"text":"海客","probability":.9},
        {"start":.4,"end":.8,"text":"🤖","probability":.8}]}]}
    assert captured["model_options"]["local_files_only"] is True
    assert captured["transcribe_options"]["word_timestamps"] is True
    assert not output.with_suffix(".tmp").exists()


def test_worker_cli_errors_are_safe_without_internal_exception_trace(worker,monkeypatch,capsys):
    from lib import ffmpeg_locator
    monkeypatch.setattr(ffmpeg_locator,"resolve_ffmpeg",lambda:"fixture-local-ffmpeg")
    monkeypatch.setattr(subprocess,"run",lambda *a,**k:SimpleNamespace(returncode=1,stdout=b"",stderr=b"SECRET_INTERNAL_DECODER_ERROR"))
    output=worker.root/"result.json"
    monkeypatch.setattr(sys,"argv",[str(SCRIPT),"--model-dir",str(worker.root/"model"),"--audio",str(worker.source),"--output",str(output)])
    with pytest.raises(SystemExit) as caught:
        runpy.run_path(str(SCRIPT),run_name="__main__")
    assert caught.value.code==1
    stderr=capsys.readouterr().err
    assert "本地字幕识别未完成" in stderr
    assert "SECRET" not in stderr and "Traceback" not in stderr
    assert not output.exists()
