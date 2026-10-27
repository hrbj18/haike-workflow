"""CA relocation and native transport errors are tested without network access."""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from curl_cffi.requests.exceptions import SSLError

from app import tls_runtime
from app.platforms.douyin import client as douyin_client
from app.platforms.douyin import resolve as douyin_resolve


@pytest.fixture
def ca_files(tmp_path, monkeypatch):
    for name in ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE"):
        monkeypatch.delenv(name, raising=False)
    source = tmp_path / "中文安装目录" / "cacert.pem"
    source.parent.mkdir()
    payload = b"-----BEGIN CERTIFICATE-----\nfixture-public-ca\n-----END CERTIFICATE-----\n"
    source.write_bytes(payload)
    cache = tmp_path / "user-runtime"
    monkeypatch.setattr(tls_runtime, "_default_ca_path", lambda: str(source))
    monkeypatch.setattr(tls_runtime, "_cache_roots", lambda: [cache])
    return source, payload, cache


def test_non_ascii_source_is_copied_to_ascii_exact_content_cache(ca_files):
    source, payload, cache = ca_files
    result = Path(tls_runtime.curl_verify_path())
    assert str(result).isascii() and result.parent == cache
    assert result.read_bytes() == payload and source.read_bytes() == payload
    assert tls_runtime.curl_verify_path() == str(result)


def test_ascii_source_keeps_existing_trust_path(ca_files, tmp_path, monkeypatch):
    _, payload, cache = ca_files
    source = tmp_path / "ascii-ca.pem"
    source.write_bytes(payload)
    monkeypatch.setattr(tls_runtime, "_default_ca_path", lambda: str(source))
    assert tls_runtime.curl_verify_path() == str(source.resolve())
    assert not cache.exists()


def test_explicit_custom_trust_uses_session_precedence_and_preserves_environment(ca_files, tmp_path, monkeypatch):
    source, payload, _ = ca_files
    other = tmp_path / "other.pem"
    other.write_bytes(payload + b"# other CA set\n")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(source))
    monkeypatch.setenv("CURL_CA_BUNDLE", str(other))
    monkeypatch.setenv("SSL_CERT_FILE", str(other))
    before = {key: tls_runtime.os.environ[key]
              for key in ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE")}
    assert Path(tls_runtime.curl_verify_path()).read_bytes() == payload
    assert before == {key: tls_runtime.os.environ[key] for key in before}


def test_missing_explicit_trust_never_falls_back_to_default(ca_files, monkeypatch):
    source, _, _ = ca_files
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(source.parent / "missing.pem"))
    with pytest.raises(tls_runtime.CertificateBundleError, match="证书"):
        tls_runtime.curl_verify_path()


def test_cache_is_revalidated_and_corruption_replaced_from_source(ca_files):
    _, payload, _ = ca_files
    cached = Path(tls_runtime.curl_verify_path())
    cached.write_bytes(b"tampered-certificates")
    assert tls_runtime.curl_verify_path() == str(cached)
    assert cached.read_bytes() == payload
    assert not list(cached.parent.glob(".ca-*"))


def test_updated_source_gets_a_different_content_addressed_cache(ca_files):
    source, payload, _ = ca_files
    old = Path(tls_runtime.curl_verify_path())
    source.write_bytes(payload + b"# public CA update\n")
    new = Path(tls_runtime.curl_verify_path())
    assert new != old and new.read_bytes() == source.read_bytes()
    assert old.read_bytes() == payload


def test_no_ascii_runtime_or_invalid_pem_fails_closed(ca_files, tmp_path, monkeypatch):
    source, payload, _ = ca_files
    monkeypatch.setattr(tls_runtime, "_cache_roots", lambda: [tmp_path / "中文缓存"])
    with pytest.raises(tls_runtime.CertificateBundleError):
        tls_runtime.curl_verify_path()
    source.write_bytes(b"not a CA bundle")
    with pytest.raises(tls_runtime.CertificateBundleError):
        tls_runtime.curl_verify_path()
    assert source.read_bytes() != payload


@pytest.mark.parametrize("code,expected", [(77, "证书文件"), (60, "证书校验"),
    (28, "超时"), (6, "域名"), (7, "连接"), (35, "TLS")])
def test_native_error_never_contains_cookie_signed_url_or_raw_exception(code, expected):
    error = SSLError("Cookie=PRIVATE_COOKIE https://cdn.example/v?signature=PRIVATE_SIGNED_URL", code=code)
    message = tls_runtime.native_request_message(error)
    assert expected in message and str(code) in message
    assert "PRIVATE" not in message and "https://" not in message and "Cookie" not in message


def test_douyin_session_and_read_use_verified_ascii_bundle(ca_files, monkeypatch):
    sessions = []
    session = AsyncMock()
    session.get.return_value.status_code = 200
    session.get.return_value.content = b'{}'
    session.get.return_value.json = lambda: {}

    def create(**kwargs):
        sessions.append(kwargs)
        return session

    monkeypatch.setattr(douyin_client, "AsyncSession", create)
    monkeypatch.setattr(douyin_client, "gen_real_ms_token", AsyncMock(return_value="fixture-token"))
    client = douyin_client.DouyinClient("sessionid=FIXTURE", "Chrome/130.0.0.0")
    async def exercise():
        async with client.session_scope():
            assert await client._get_json("/fixture", {}) == {}
    asyncio.run(exercise())
    assert len(sessions) == 1 and isinstance(sessions[0]["verify"], str)
    assert sessions[0]["verify"].isascii()
    assert Path(sessions[0]["verify"]).read_bytes() == ca_files[1]
    assert sessions[0]["impersonate"] == client.impersonate
    session.close.assert_awaited_once()


def test_transport_error_records_only_type_and_numeric_code(ca_files, monkeypatch, capsys):
    session = AsyncMock()
    session.get.side_effect = SSLError("PRIVATE_COOKIE PRIVATE_SIGNED_URL", code=77)
    monkeypatch.setattr(douyin_client, "AsyncSession", lambda **_: session)
    monkeypatch.setattr(douyin_client, "gen_real_ms_token", AsyncMock(return_value="fixture-token"))
    client = douyin_client.DouyinClient("fixture", "Chrome/130.0.0.0")
    with pytest.raises(SSLError):
        asyncio.run(client._get_json("/fixture", {}))
    assert client.last_error == "network:SSLError:curl_77"
    captured = capsys.readouterr()
    assert "PRIVATE" not in captured.out + captured.err
    session.close.assert_awaited_once()


def test_short_link_ca_failure_never_masquerades_as_unsupported_url(monkeypatch):
    def fail():
        raise tls_runtime.CertificateBundleError("PRIVATE_CA_PATH")
    monkeypatch.setattr(douyin_resolve, "curl_verify_path", fail)
    with pytest.raises(tls_runtime.CertificateBundleError):
        asyncio.run(douyin_resolve.resolve_aweme_id("https://v.douyin.com/fixture/", "fixture-UA"))
