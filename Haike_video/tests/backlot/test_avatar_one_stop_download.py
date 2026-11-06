from types import SimpleNamespace
from pathlib import Path
import pytest

from backlot import avatar_one_stop_download as download
from backlot.work_catalog import WorkError


def test_verified_ranges_assemble_exact_object_without_relaxing_tls(tmp_path,monkeypatch):
    data=b'original-video-byte-pattern'*(1024*1024//26+1)
    calls=[]
    def run(args,**kwargs):
        assert '--insecure' not in args and '-k' not in args
        assert args[-1]=='https://trusted.example/same-object'
        first,last=map(int,args[args.index('--range')+1].split('-'))
        last=min(last,len(data)-1)
        calls.append((first,last))
        Path(args[args.index('--output')+1]).write_bytes(data[first:last+1])
        Path(args[args.index('--dump-header')+1]).write_text(
            f'HTTP/1.1 206 Partial Content\r\nContent-Range: bytes {first}-{last}/{len(data)}\r\n','latin-1')
        return SimpleNamespace(returncode=0,stdout=b'206')
    monkeypatch.setattr(download.subprocess,'run',run)
    target=tmp_path/'same-original.mp4'
    download.download_ranges(Path('system-curl.exe'),'https://trusted.example/same-object',target)
    assert target.read_bytes()==data and len(calls)==2


def test_mismatched_range_never_becomes_a_completed_artifact(tmp_path,monkeypatch):
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        Path(args[args.index('--output')+1]).write_bytes(b'x'*15)
        Path(args[args.index('--dump-header')+1]).write_text('Content-Range: bytes 1-15/16\r\n','latin-1')
        return SimpleNamespace(returncode=0,stdout=b'206')
    monkeypatch.setattr(download.subprocess,'run',run)
    monkeypatch.setattr(download.time,'sleep',lambda seconds:None)
    target=tmp_path/'must-not-exist.mp4'
    with pytest.raises(WorkError,match='未重新生成'):
        download.download_ranges(Path('system-curl.exe'),'https://trusted.example/object',target)
    assert len(calls)==3 and not target.exists()
