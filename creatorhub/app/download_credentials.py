"""Private download credentials shared by local consumers (standard library only).

Only metadata belongs in API responses. Cookie values and transport settings are
local authentication material; callers must never print ``read_record`` results.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


PLATFORM_DOMAINS = {
    "douyin": ("douyin.com", "iesdouyin.com", "amemv.com"),
    "kuaishou": ("kuaishou.com",),
    "shipinhao": ("weixin.qq.com",),
    "xhs": ("xiaohongshu.com",),
}
STATUS_MESSAGES = {
    "not_saved": "尚未保存下载登录，请打开登录窗口后检查",
    "ready": "下载登录检查通过",
    "stored_unverified": "已保存，仍需检查下载登录",
    "login_required": "下载登录已失效，请重新扫码后检查",
    "unconfirmed": "暂时无法确认下载登录，请完成页面验证后重试",
    "network_error": "平台暂时无法连接，请检查网络后重试",
    "profile_changed": "账号浏览器位置已更改，请重新检查下载登录",
}
_COOKIE_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_SELECTION_LOCK = threading.Lock()


class DownloadCredentialError(ValueError):
    """A user-facing error whose message never includes credential content."""


def resolve_store_root(workspace_root=None, *, db_path=None) -> Path:
    override = os.environ.get("HAIKE_DOWNLOAD_CREDENTIALS_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if db_path:
        return Path(db_path).expanduser().resolve().parent / "download-credentials"
    workspace = Path(workspace_root) if workspace_root else Path(__file__).resolve().parents[2]
    return workspace.resolve() / "creatorhub" / "data" / "download-credentials"


def platform_domain_allowed(platform: str, domain: str) -> bool:
    host = str(domain or "").lstrip(".").lower()
    if platform == "shipinhao":
        return (host == "weixin.qq.com" or host == "channels.weixin.qq.com"
                or host.endswith(".channels.weixin.qq.com"))
    return any(host == base or host.endswith("." + base)
               for base in PLATFORM_DOMAINS.get(platform, ()))


def profile_identity(profile_dir: str) -> str:
    if not profile_dir:
        return ""
    value = os.path.normcase(str(Path(profile_dir).expanduser().resolve()))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sanitize_download_cookies(platform: str, cookies, *, now=None) -> list[dict]:
    if platform not in PLATFORM_DOMAINS:
        raise DownloadCredentialError("暂不支持这个下载平台")
    if not isinstance(cookies, list) or len(cookies) > 3000:
        raise DownloadCredentialError("浏览器下载凭据格式无效")
    now = time.time() if now is None else now
    result = {}
    for source in cookies:
        if not isinstance(source, dict):
            continue
        name, value = source.get("name"), source.get("value")
        domain, path = source.get("domain"), source.get("path", "/")
        if (not isinstance(name, str) or not _COOKIE_NAME.fullmatch(name)
                or not isinstance(value, str) or not isinstance(domain, str)
                or not isinstance(path, str) or not path.startswith("/")
                or not platform_domain_allowed(platform, domain)
                or any(ord(char) < 32 or ord(char) == 127 for char in value + domain + path)):
            continue
        try:
            expires = float(source.get("expires", -1))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(expires) or (expires > 0 and expires <= now):
            continue
        cookie = {"name": name, "value": value, "domain": domain, "path": path,
                  "expires": source.get("expires", -1),
                  "secure": bool(source.get("secure", False)),
                  "httpOnly": bool(source.get("httpOnly", False))}
        if source.get("sameSite") in {"Strict", "Lax", "None"}:
            cookie["sameSite"] = source["sameSite"]
        # Retain partition information internally. Netscape cannot represent
        # it, so the temporary legacy export deliberately excludes these rows.
        if source.get("partitionKey"):
            cookie["partitionKey"] = source["partitionKey"]
        result[(name, domain.lstrip(".").lower(), path,
                str(cookie.get("partitionKey", "")))] = cookie
    return list(result.values())


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class DownloadCredentialStore:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()

    @staticmethod
    def _key(platform, account_id):
        if platform not in PLATFORM_DOMAINS:
            raise DownloadCredentialError("暂不支持这个下载平台")
        if type(account_id) is not int or account_id <= 0:
            raise DownloadCredentialError("下载账号无效")
        return f"{platform}-{account_id}"

    def _path(self, platform, account_id):
        return self.root / (self._key(platform, account_id) + ".json")

    @staticmethod
    def _load(path):
        try:
            if path.stat().st_size > 4 * 1024 * 1024:
                raise DownloadCredentialError("下载凭据文件异常，请重新检查登录")
            result = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError, ValueError):
            raise DownloadCredentialError("下载凭据无法读取，请重新检查登录") from None

    def _write(self, path, record):
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.root,
                                             prefix=".credential-", suffix=".tmp", delete=False) as out:
                temporary = Path(out.name)
                os.chmod(temporary, 0o600)
                json.dump(record, out, ensure_ascii=False, separators=(",", ":"))
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def read_record(self, platform, account_id, *, require_ready=True, profile_dir=None):
        """Internal only: includes secret cookies, UA and proxy configuration."""
        record = self._load(self._path(platform, account_id))
        if not record or record.get("version") != 1 or record.get("platform") != platform \
                or record.get("account_id") != account_id:
            raise DownloadCredentialError(STATUS_MESSAGES["not_saved"])
        if profile_dir is not None and record.get("profile_identity") != profile_identity(profile_dir):
            raise DownloadCredentialError(STATUS_MESSAGES["profile_changed"])
        if require_ready and record.get("status") != "ready":
            raise DownloadCredentialError(STATUS_MESSAGES.get(record.get("status"), STATUS_MESSAGES["unconfirmed"]))
        record["cookies"] = sanitize_download_cookies(platform, record.get("cookies", []))
        if require_ready and not record["cookies"]:
            raise DownloadCredentialError(STATUS_MESSAGES["login_required"])
        return record

    def read_cookies(self, platform, account_id, *, require_ready=True, profile_dir=None):
        return self.read_record(platform, account_id, require_ready=require_ready,
                                profile_dir=profile_dir)["cookies"]

    def metadata(self, platform, account_id, *, profile_dir=None):
        self._key(platform, account_id)
        record = self._load(self._path(platform, account_id)) or {}
        if record.get("platform") != platform or record.get("account_id") != account_id:
            record = {}
        cookies = sanitize_download_cookies(platform, record.get("cookies", []))
        status = record.get("status", "not_saved")
        if status == "ready" and not cookies:
            status = "login_required"
        if record and profile_dir is not None and record.get("profile_identity") != profile_identity(profile_dir):
            status = "profile_changed"
        return {"account_id": account_id, "platform": platform,
                "enabled": bool(record), "status": status,
                "saved_at": record.get("saved_at"),
                "last_checked_at": record.get("last_checked_at"),
                "captured_at": record.get("captured_at"), "cookie_count": len(cookies),
                "message": STATUS_MESSAGES.get(status, STATUS_MESSAGES["unconfirmed"]),
                "selected": self.selected_account(platform) == account_id}

    def save(self, platform, account_id, cookies, *, user_agent="", proxy="",
             verified=False, checked_at=None, profile_dir=""):
        cookies = sanitize_download_cookies(platform, cookies)
        if not cookies:
            raise DownloadCredentialError("浏览器没有可保存的该平台下载凭据，请先登录")
        record = {"version": 1, "platform": platform, "account_id": account_id,
                  "cookies": cookies, "user_agent": str(user_agent or ""),
                  "proxy": str(proxy or ""), "profile_identity": profile_identity(profile_dir),
                  "saved_at": _stamp(), "captured_at": _stamp(),
                  "last_checked_at": (checked_at or _stamp()) if verified else None,
                  "status": "ready" if verified else "stored_unverified"}
        self._write(self._path(platform, account_id), record)
        return self.metadata(platform, account_id, profile_dir=profile_dir)

    def update_status(self, platform, account_id, status, *, profile_dir=None):
        if status not in STATUS_MESSAGES or status in {"ready", "not_saved", "profile_changed"}:
            raise DownloadCredentialError("下载登录检查状态无效")
        record = self._load(self._path(platform, account_id)) or {
            "version": 1, "platform": platform, "account_id": account_id, "cookies": []}
        if profile_dir is not None:
            expected = profile_identity(profile_dir)
            if record.get("profile_identity") not in (None, "", expected):
                record = {"version": 1, "platform": platform, "account_id": account_id, "cookies": []}
            record["profile_identity"] = expected
        record["status"] = status
        record["last_checked_at"] = _stamp()
        self._write(self._path(platform, account_id), record)
        return self.metadata(platform, account_id)

    def refresh_snapshot(self, platform, account_id, cookies, *, profile_dir,
                         user_agent="", proxy=""):
        """Rotate an opted-in snapshot without upgrading its checked status."""
        record = self.read_record(platform, account_id, require_ready=False,
                                  profile_dir=profile_dir)
        cookies = sanitize_download_cookies(platform, cookies)
        if not cookies:
            return False
        record.update(cookies=cookies, captured_at=_stamp(),
                      user_agent=str(user_agent or ""), proxy=str(proxy or ""))
        self._write(self._path(platform, account_id), record)
        return True

    def selected_account(self, platform):
        if platform not in PLATFORM_DOMAINS:
            raise DownloadCredentialError("暂不支持这个下载平台")
        record = self._load(self.root / "selection.json") or {}
        value = record.get(platform)
        return value if type(value) is int and value > 0 else None

    def select(self, platform, account_id):
        self.read_record(platform, account_id)
        path = self.root / "selection.json"
        with _SELECTION_LOCK:
            selected = self._load(path) or {}
            selected[platform] = account_id
            self._write(path, selected)
        return self.metadata(platform, account_id)

    def delete(self, platform, account_id):
        self._path(platform, account_id).unlink(missing_ok=True)
        with _SELECTION_LOCK:
            selected = self._load(self.root / "selection.json") or {}
            if selected.get(platform) == account_id:
                selected.pop(platform)
                self._write(self.root / "selection.json", selected)

    @contextmanager
    def cookie_file(self, platform, account_id, *, profile_dir=None):
        """Yield a private Netscape file, including HttpOnly; always remove it."""
        cookies = self.read_cookies(platform, account_id, profile_dir=profile_dir)
        exported = [cookie for cookie in cookies if not cookie.get("partitionKey")]
        if not exported:
            raise DownloadCredentialError("该登录凭据不支持当前下载器，请重新检查")
        self.root.mkdir(parents=True, exist_ok=True)
        filename = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                             dir=self.root, prefix=".download-", suffix=".cookies.txt",
                                             delete=False) as out:
                filename = Path(out.name)
                os.chmod(filename, 0o600)
                out.write("# Netscape HTTP Cookie File\n")
                for cookie in exported:
                    domain = cookie["domain"]
                    subdomains = "TRUE" if domain.startswith(".") else "FALSE"
                    if cookie["httpOnly"]:
                        domain = "#HttpOnly_" + domain
                    expiry = max(0, int(float(cookie["expires"])))
                    out.write("\t".join((domain, subdomains, cookie["path"],
                                          "TRUE" if cookie["secure"] else "FALSE",
                                          str(expiry), cookie["name"], cookie["value"])) + "\n")
            yield filename
        finally:
            if filename is not None:
                filename.unlink(missing_ok=True)
