"""Scoped libcurl CA paths; keep the selected trust bytes and TLS verification."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile


class CertificateBundleError(RuntimeError):
    """Preparing the existing local CA trust failed; never disable TLS."""


def _default_ca_path():
    from curl_cffi.curl import DEFAULT_CACERT
    return DEFAULT_CACERT


def _cache_roots():
    roots = []
    if os.environ.get("LOCALAPPDATA"):
        roots.append(Path(os.environ["LOCALAPPDATA"]) / "HaikeWorkflow/runtime/tls")
    if os.environ.get("XDG_CACHE_HOME"):
        roots.append(Path(os.environ["XDG_CACHE_HOME"]) / "haike-workflow/tls")
    roots.append(Path.home() / ("AppData/Local/HaikeWorkflow/runtime/tls"
                               if os.name == "nt" else ".cache/haike-workflow/tls"))
    user_key = hashlib.sha256(str(Path.home()).encode("utf-8")).hexdigest()[:16]
    roots.append(Path(tempfile.gettempdir()) / ("haike-tls-" + user_key))
    return roots


def _read_bundle(path):
    with path.open("rb") as stream:
        payload = stream.read(16 * 1024 * 1024 + 1)
    if (not payload or len(payload) > 16 * 1024 * 1024
            or b"-----BEGIN CERTIFICATE-----" not in payload
            or b"-----END CERTIFICATE-----" not in payload):
        raise CertificateBundleError("本机证书文件不可用，请修复原有证书配置后重试")
    return payload


def curl_verify_path() -> str:
    """Use an identical ASCII CA file, without changing process environment.

    Match AsyncSession's CA override precedence. DEFAULT_CACERT already includes
    libcurl's SSL_CERT_FILE/system/certifi selection. An invalid explicit override
    remains an error, rather than silently choosing a different trust source.
    """
    selected = (os.environ.get("REQUESTS_CA_BUNDLE")
                or os.environ.get("CURL_CA_BUNDLE") or _default_ca_path())
    try:
        source = Path(selected).expanduser().resolve()
        payload = _read_bundle(source)
        if str(source).isascii():
            return str(source)
        digest = hashlib.sha256(payload).hexdigest()
        for candidate in _cache_roots():
            root = Path(candidate).expanduser().resolve()
            if not str(root).isascii():
                continue
            temporary = None
            try:
                root.mkdir(parents=True, exist_ok=True, mode=0o700)
                target = root / ("cacert-" + digest + ".pem")
                if target.is_symlink():
                    continue
                if target.is_file() and hashlib.sha256(_read_bundle(target)).hexdigest() == digest:
                    return str(target)
            except CertificateBundleError:
                # A corrupt cache can be replaced only with the original bytes.
                pass
            except OSError:
                continue
            try:
                with tempfile.NamedTemporaryFile(dir=root, prefix=".ca-", suffix=".pem", delete=False) as out:
                    temporary = Path(out.name)
                    out.write(payload)
                    out.flush()
                    os.fsync(out.fileno())
                if target.is_symlink():
                    continue
                temporary.replace(target)
                if hashlib.sha256(_read_bundle(target)).hexdigest() != digest:
                    continue
                return str(target)
            except (OSError, CertificateBundleError):
                continue
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
    except (OSError, TypeError, ValueError):
        raise CertificateBundleError("本机证书文件不可读，请修复原有证书配置后重试") from None
    raise CertificateBundleError("没有可用的ASCII证书缓存目录，请检查当前用户的运行目录权限")


def native_request_message(error) -> str:
    """Map native errors without interpolating URLs, headers or exception text."""
    if isinstance(error, CertificateBundleError):
        return "本机证书文件准备失败，请检查证书配置和用户运行目录后重试"
    code = getattr(error, "code", None)
    code = int(code) if isinstance(code, int) and not isinstance(code, bool) else 0
    reason = {
        77: "本机证书文件不可读，请检查证书配置和用户运行目录",
        60: "远端证书校验未通过，请检查网络或代理的证书信任配置",
        28: "平台请求超时，请检查网络后重试",
        6: "平台域名解析失败，请检查网络和DNS设置",
        7: "平台连接失败，请检查网络或代理设置",
        35: "TLS连接失败，请检查网络或代理设置",
    }.get(code, "平台网络请求失败，请检查网络设置后重试")
    return f"{reason}（curl {code}）" if code else reason
