import io

import pytest

from backlot import studio_avatar
from backlot.work_catalog import WorkError


def test_saved_cosyvoice_http_receipt_downloads_over_verified_https(tmp_path, monkeypatch):
    requests = []
    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            return io.BytesIO(b'original-paid-audio')
    monkeypatch.setattr(studio_avatar, 'build_opener', lambda *_: Opener())
    monkeypatch.setattr(studio_avatar.socket, 'getaddrinfo', lambda *_args, **_kw: [(2, 1, 6, '', ('8.8.8.8',443))])
    target = tmp_path/'narration.wav'
    studio_avatar.download_result('http://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/audio.wav?signature=fixture', target)
    assert target.read_bytes() == b'original-paid-audio'
    assert requests[0].full_url == 'https://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/audio.wav?signature=fixture'
    assert not requests[0].has_header('Authorization')
    assert requests[0].get_header('User-agent') == 'HaikeVideo/1.0'


@pytest.mark.parametrize('url',[
    'http://example.com/audio.wav',
    'http://dashscope-result-bj.oss-cn-beijing.aliyuncs.com.evil.example/audio.wav',
    'http://user:password@dashscope-result-bj.oss-cn-beijing.aliyuncs.com/audio.wav',
    'http://dashscope-result-bj.oss-cn-beijing.aliyuncs.com:8080/audio.wav',
])
def test_cosyvoice_compatibility_does_not_enable_other_http_or_credentials(tmp_path, url):
    with pytest.raises(WorkError, match='地址无效'):
        studio_avatar.download_result(url, tmp_path/'audio.wav')


def test_upgraded_oss_address_still_rejects_private_dns(tmp_path,monkeypatch):
    monkeypatch.setattr(studio_avatar.socket,'getaddrinfo',lambda *_args,**_kw:[(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(WorkError,match='本地网络'):
        studio_avatar.download_result('http://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/audio.wav',tmp_path/'audio.wav')


def test_fake_dns_requires_known_host_and_public_doh_answer(monkeypatch):
    monkeypatch.setattr(studio_avatar.socket,'getaddrinfo',lambda *_args,**_kw:[(2,1,6,'',('198.18.0.9',443))])
    requests=[]
    class Opener:
        def open(self,request,timeout):
            requests.append(request)
            return io.BytesIO(b'{"Status":0,"Answer":[{"type":1,"data":"127.0.0.1"}]}')
    monkeypatch.setattr(studio_avatar,'build_opener',lambda *_:Opener())
    with pytest.raises(WorkError,match='本地网络'):studio_avatar.public_media_address('unknown.example',443)
    assert not requests
    with pytest.raises(WorkError,match='真实公网'):studio_avatar.public_media_address('videos.pexels.com',443)
    assert requests[0].full_url.startswith('https://1.1.1.1/dns-query?') and not requests[0].has_header('Authorization')


def test_media_socket_uses_checked_ip_and_original_tls_hostname(monkeypatch):
    from types import SimpleNamespace
    connected=[];wrapped=[]
    sock=object()
    monkeypatch.setattr(studio_avatar.socket,'create_connection',lambda target,*_args:(connected.append(target) or sock))
    handler=studio_avatar.media_https_handler('8.8.8.8')
    def open_connection(connection,request,**_kwargs):
        conn=connection('videos.pexels.com')
        conn._context=SimpleNamespace(wrap_socket=lambda value,server_hostname:(wrapped.append((value,server_hostname)) or value))
        conn.connect()
    handler.do_open=open_connection
    handler.https_open(studio_avatar.Request('https://videos.pexels.com/file.mp4'))
    assert connected==[('8.8.8.8',443)] and wrapped==[(sock,'videos.pexels.com')]


def test_runninghub_verified_bucket_resolves_fake_dns_without_trusting_other_hosts(monkeypatch):
    monkeypatch.setattr(studio_avatar.socket,'getaddrinfo',lambda *_args,**_kw:[(2,1,6,'',('198.18.0.9',443))])
    requests=[]
    class Opener:
        def open(self,request,timeout):
            requests.append(request)
            return io.BytesIO(b'{"Status":0,"Answer":[{"type":1,"data":"8.8.8.8"}]}')
    monkeypatch.setattr(studio_avatar,'build_opener',lambda *_:Opener())
    assert studio_avatar.public_media_address('rh-comfyui01.tos-cn-beijing.volces.com',443)=='8.8.8.8'
    assert not requests[0].has_header('Authorization')
    with pytest.raises(WorkError,match='本地网络'):
        studio_avatar.public_media_address('rh-comfyui01.tos-cn-beijing.volces.com.evil.example',443)
    assert len(requests)==1
