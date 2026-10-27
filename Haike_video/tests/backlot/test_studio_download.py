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


def test_explicit_download_cap_rejects_large_response_and_removes_partial(tmp_path, monkeypatch):
    class Opener:
        def open(self, request, timeout):
            return io.BytesIO(b'over-budget')
    monkeypatch.setattr(studio_avatar, 'build_opener', lambda *_: Opener())
    monkeypatch.setattr(studio_avatar, 'public_media_address', lambda *_: '8.8.8.8')
    target = tmp_path / 'sample.mp4'
    with pytest.raises(WorkError, match='大小上限'):
        studio_avatar.download_result('https://cdn.example/file.mp4', target, max_bytes=3)
    assert not target.exists() and not target.with_suffix('.mp4.part').exists()


@pytest.mark.parametrize('maximum', [True, 0, -1, 100 * 1024 * 1024 + 1])
def test_invalid_download_cap_cannot_expand_default_budget(tmp_path, monkeypatch, maximum):
    monkeypatch.setattr(studio_avatar, 'build_opener', lambda *_: pytest.fail('must fail before network'))
    with pytest.raises(WorkError, match='上限无效'):
        studio_avatar.download_result('https://cdn.example/file.mp4', tmp_path / 'sample.mp4', max_bytes=maximum)


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


def test_fake_dns_uses_verified_secondary_resolver_after_tls_failure(monkeypatch):
    import ssl
    from urllib.error import URLError
    monkeypatch.setattr(studio_avatar.socket,'getaddrinfo',lambda *_args,**_kw:[(2,1,6,'',('198.18.1.230',443))])
    requests=[]
    class Opener:
        def open(self,request,timeout):
            requests.append(request)
            if request.full_url.startswith('https://1.1.1.1/'):
                raise URLError(ssl.SSLCertVerificationError('fixture chain unavailable'))
            return io.BytesIO(b'{"Status":0,"Answer":[{"type":1,"data":"8.141.181.163"}]}')
    monkeypatch.setattr(studio_avatar,'build_opener',lambda *_:Opener())
    assert studio_avatar.public_media_address('dashscope-result-bj.oss-cn-beijing.aliyuncs.com',443)=='8.141.181.163'
    assert len(requests)==2 and requests[1].full_url.startswith('https://dns.alidns.com/resolve?')
    assert all(not request.has_header('Authorization') for request in requests)


def test_secondary_resolver_still_rejects_private_addresses(monkeypatch):
    from urllib.error import URLError
    monkeypatch.setattr(studio_avatar.socket,'getaddrinfo',lambda *_args,**_kw:[(2,1,6,'',('198.18.1.230',443))])
    class Opener:
        def open(self,request,timeout):
            if request.full_url.startswith('https://1.1.1.1/'):
                raise URLError('fixture unavailable')
            return io.BytesIO(b'{"Status":0,"Answer":[{"type":1,"data":"127.0.0.1"}]}')
    monkeypatch.setattr(studio_avatar,'build_opener',lambda *_:Opener())
    with pytest.raises(WorkError,match='真实公网'):
        studio_avatar.public_media_address('dashscope-result-bj.oss-cn-beijing.aliyuncs.com',443)


@pytest.mark.parametrize('host', ['www.douyin.com', 'v3-web.douyinvod.com', 'v26-web.douyinvod.com'])
def test_douyin_play_redirect_hosts_require_verified_public_dns(monkeypatch, host):
    monkeypatch.setattr(studio_avatar.socket, 'getaddrinfo',
                        lambda *_args, **_kw: [(2, 1, 6, '', ('198.18.0.9', 443))])
    requests = []
    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            return io.BytesIO(b'{"Status":0,"Answer":[{"type":1,"data":"8.8.8.8"}]}')
    monkeypatch.setattr(studio_avatar, 'build_opener', lambda *_: Opener())
    assert studio_avatar.public_media_address(host, 443) == '8.8.8.8'
    assert len(requests) == 1 and not requests[0].has_header('Authorization')


@pytest.mark.parametrize('host', ['www.douyin.com.evil.example',
                                 'v3-web.douyinvod.com.evil.example',
                                 'v-foo.douyinvod.com'])
def test_similar_douyin_names_do_not_gain_fake_dns_fallback(monkeypatch, host):
    monkeypatch.setattr(studio_avatar.socket, 'getaddrinfo',
                        lambda *_args, **_kw: [(2, 1, 6, '', ('198.18.0.9', 443))])
    monkeypatch.setattr(studio_avatar, 'build_opener', lambda *_: pytest.fail('untrusted host'))
    with pytest.raises(WorkError, match='本地网络'):
        studio_avatar.public_media_address(host, 443)
