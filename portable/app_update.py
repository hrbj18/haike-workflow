"""Transactional, dependency-compatible application patches for portable installs.

Only shipped program files are replaced.  User directories are never copied,
deleted, migrated, or included in a backup.  The external update worker owns
stopping services and supplies the post-restart health check.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from uuid import uuid4
import zipfile


EDITION = "haike-workflow-2"
PLATFORM = "windows-x64"
RUNTIME_ID = "haike-windows-x64-v1"
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_EXPANDED_BYTES = 768 * 1024 * 1024
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_FILES = 20000
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_PACKAGE_MANIFEST_BYTES = 64 * 1024 * 1024
METADATA = {"VERSION.json", "RELEASE.json", "PACKAGE-MANIFEST.json"}
_SHA = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_RESERVED = {"con", "prn", "aux", "nul", *("com" + str(n) for n in range(1, 10)),
             *("lpt" + str(n) for n in range(1, 10))}
_PRIVATE_PARTS = {".local", ".backlot", ".portable", ".git", ".venv", "venv", "runtime",
                  "node_modules", "__pycache__", "data", "browser_data", "projects", "media",
                  "renders", "output", "cache", "temp", "logs", "backups", "models",
                  "third_party", "library-covers", "private-transfer", ".haike-archives"}
_SOURCE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".css", ".html",
                      ".json", ".md", ".txt", ".toml", ".yaml", ".yml", ".ps1", ".cmd", ".svg"}
_PROGRAM_PREFIXES = ("Haike_video/backlot/", "Haike_video/lib/", "Haike_video/tools/",
                     "Haike_video/scripts/", "Haike_video/templates/", "Haike_video/skills/",
                     "Haike_video/docs/", "Haike_video/design/", "Haike_video/workflows/",
                     "Haike_video/remotion-composer/",
                     "Haike_video/tests/", "tests/",
                     "prototypes/haike-avatar-generator/src/", "prototypes/haike-avatar-generator/dist/",
                     "prototypes/haike-avatar-generator/tests/", "portable/", "scripts/", "docs/",
                     "Haike-Videohub/agent-runbooks/", "Haike-Videohub/contracts/")
_ROOT_PROGRAMS = {"start-workbench.ps1", "一键启动工作台.cmd", "02-start.cmd", "README.md",
                  "START_HERE.md", "使用说明.txt"}
_PUBLIC_BITMAPS = {"Haike_video/backlot/ui/brand/haike-company-logo.png"}


class UpdateError(ValueError):
    """A Chinese, user-facing update or recovery failure."""


def version_tuple(version):
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise UpdateError("版本号无效，需要正式版本号，例如 1.0.1")
    return tuple(int(part) for part in version.split("."))


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise UpdateError("更新清单包含重复字段")
        result[key] = value
    return result


def _json(data):
    try:
        value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_object)
        if not isinstance(value, dict):
            raise UpdateError("更新清单格式错误")
        return value
    except (UnicodeError, json.JSONDecodeError) as error:
        raise UpdateError("更新清单无法读取") from error


def _read(path):
    path = Path(path)
    limit = MAX_PACKAGE_MANIFEST_BYTES if path.name == "PACKAGE-MANIFEST.json" else MAX_MANIFEST_BYTES
    if path.stat().st_size > limit:
        raise UpdateError("更新清单超过大小限制")
    return _json(path.read_bytes())


def _parts(name):
    if not isinstance(name, str) or not name or len(name) > 500:
        raise UpdateError("更新文件路径无效")
    rel = PurePosixPath(name)
    parts = name.split("/")
    if (rel.is_absolute() or "\\" in name or any(ord(c) < 32 for c in name)
            or any(part in ("", ".", "..") or part.endswith((".", " "))
                   or any(c in part for c in ':*?"<>|')
                   or part.split(".")[0].casefold() in _RESERVED for part in parts)):
        raise UpdateError("更新包含不安全路径：" + name)
    return tuple(parts)


def safe_path(root, name):
    parts = _parts(name)
    root = Path(root).resolve()
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise UpdateError("更新不能经过符号链接或目录联接：" + name)
    if not current.resolve().is_relative_to(root):
        raise UpdateError("更新文件超出安装目录：" + name)
    return current


def is_dependency_path(name):
    try:
        base = _parts(name)[-1].casefold()
    except UpdateError:
        return False
    return (base in {"package.json", "package-lock.json", "npm-shrinkwrap.json", "pyproject.toml",
                     "uv.lock", "poetry.lock", "yarn.lock", "pnpm-lock.yaml", "pipfile", "pipfile.lock"}
            or (base.startswith("requirements") and base.endswith(".txt")))


def is_program_path(name):
    """True only for replaceable public code, never runtime or private assets."""
    try:
        parts = _parts(name)
    except UpdateError:
        return False
    lowered = [part.casefold() for part in parts]
    base = lowered[-1]
    if (name in METADATA or is_dependency_path(name) or any(part in _PRIVATE_PARTS for part in lowered)
            or any(part.startswith(".env") or part.endswith("_user_data_dir") for part in lowered)
            or "config" in lowered or base in {"config.yaml", "config.yml", "storage_state.json"}
            or any(marker in base for marker in (".private.", ".local.", "cookies", "storage_state"))
            or Path(name).suffix.casefold() not in _SOURCE_EXTENSIONS and name not in _PUBLIC_BITMAPS):
        return False
    return name in _ROOT_PROGRAMS or name in _PUBLIC_BITMAPS or name.startswith(_PROGRAM_PREFIXES)


def _atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".haike-update-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _time():
    return datetime.now(timezone.utc).isoformat()


def read_release(root):
    root = Path(root).resolve()
    value = {"edition": EDITION, "version": None, "channel": "stable"}
    for name in ("VERSION.json", "RELEASE.json"):
        path = safe_path(root, name)
        if path.is_file():
            value.update(_read(path))
    return value


def pending_receipts(root):
    """Return interrupted transactions; they must be recovered before updating."""
    folder = safe_path(root, ".local/app-updates")
    result = []
    if not folder.is_dir():
        return result
    for directory in folder.iterdir():
        if not directory.is_dir():
            continue
        safe_path(root, directory.relative_to(Path(root).resolve()).as_posix())
        receipt = safe_path(directory, "receipt.json")
        if not receipt.is_file():
            continue
        value = _read(receipt)
        if value.get("status") in {"prepared", "installing", "applying", "checking"}:
            result.append({"backup": str(directory), "status": value["status"],
                           "version": value.get("version"), "base_version": value.get("base_version")})
    return result


def _plan(value):
    if (type(value.get("schema")) is not int or value.get("schema") != 1 or value.get("edition") != EDITION
            or value.get("platform") != PLATFORM or not isinstance(value.get("runtime_id"), str)
            or not value["runtime_id"] or type(value.get("data_schema")) is not int
            or value.get("data_schema") < 1):
        raise UpdateError("此更新包不适用于当前海客版本")
    if version_tuple(value.get("version")) <= version_tuple(value.get("base_version")):
        raise UpdateError("更新版本必须高于当前基线版本")
    if value.get("channel", "stable") != "stable":
        raise UpdateError("第一版更新器只接受正式稳定版")
    if "source_commit" in value and (not isinstance(value["source_commit"], str)
            or not re.fullmatch(r"[0-9a-f]{40}", value["source_commit"])):
        raise UpdateError("更新包缺少有效的源码构建标识")
    if "published_at" in value and (not isinstance(value["published_at"], str) or len(value["published_at"]) > 100):
        raise UpdateError("更新包发布时间无效")
    files = value.get("files")
    locks = value.get("required_locks", [])
    if not isinstance(files, list) or not files or len(files) > MAX_FILES or not isinstance(locks, list):
        raise UpdateError("更新文件清单为空或格式无效")
    seen = set()
    for item in files:
        if not isinstance(item, dict) or not is_program_path(item.get("path")):
            raise UpdateError("更新包尝试修改受保护文件：" + str(item.get("path") if isinstance(item, dict) else ""))
        if (type(item.get("size")) is not int or not 0 <= item["size"] <= MAX_FILE_BYTES
                or not isinstance(item.get("sha256"), str) or not _SHA.fullmatch(item["sha256"])):
            raise UpdateError("更新文件校验信息无效")
        if "before_sha256" in item and item["before_sha256"] is not None and (
                not isinstance(item["before_sha256"], str) or not _SHA.fullmatch(item["before_sha256"])):
            raise UpdateError("更新文件基线校验信息无效")
        key = item["path"].casefold()
        if key in seen:
            raise UpdateError("更新包包含重复或大小写冲突的文件")
        seen.add(key)
    if sum(item["size"] for item in files) > MAX_EXPANDED_BYTES:
        raise UpdateError("更新包解压大小超过限制")
    seen = set()
    for item in locks:
        if (not isinstance(item, dict) or not is_dependency_path(item.get("path"))
                or not isinstance(item.get("sha256"), str) or not _SHA.fullmatch(item["sha256"])):
            raise UpdateError("依赖兼容性清单无效")
        key = item["path"].casefold()
        if key in seen:
            raise UpdateError("依赖兼容性清单包含重复文件")
        seen.add(key)
    if value.get("delete") or value.get("deletes") or value.get("migrations"):
        raise UpdateError("第一版更新器不支持删除程序文件或数据迁移，请使用完整升级")
    return value


def preflight(bundle_dir, root):
    """Validate the entire patch before creating a backup or changing a file."""
    bundle_dir, root = Path(bundle_dir).resolve(), Path(root).resolve(strict=True)
    if (root / ".git").exists() or (root / ".git").is_symlink():
        raise UpdateError("源码开发副本不能自动覆盖，请通过版本管理更新")
    if not safe_path(root, "Haike_video/backlot/server.py").is_file():
        raise UpdateError("目标不是完整海客安装目录")
    if not safe_path(root, "RELEASE.json").is_file() or not safe_path(root, "PACKAGE-MANIFEST.json").is_file():
        raise UpdateError("安装版本信息不完整，请先使用完整新版包")
    if pending_receipts(root):
        raise UpdateError("上次更新被中断，请先从更新备份恢复，再检查新版本")
    plan = _plan(_read(safe_path(bundle_dir, "UPDATE-MANIFEST.json")))
    release = _read(safe_path(root, "RELEASE.json"))
    if release.get("channel") != "stable":
        raise UpdateError("当前安装不是正式稳定版，请使用完整新版包")
    for name in ("edition", "runtime_id", "data_schema", "platform"):
        if release.get(name) != plan[name]:
            raise UpdateError("运行环境或数据版本不兼容，请使用完整升级")
    current = release.get("version")
    if current not in (plan["base_version"], plan["version"]):
        raise UpdateError("此更新包不支持当前安装版本，请重新检查更新")
    version_tuple(current)
    installed = _read(safe_path(root, "PACKAGE-MANIFEST.json"))
    if type(installed.get("schema")) is not int or installed.get("schema") != 1 or not isinstance(installed.get("files"), list):
        raise UpdateError("安装文件清单无效，请修复完整安装")
    entries = {}
    folded = set()
    for item in installed["files"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise UpdateError("安装文件清单无效")
        _parts(item["path"])
        key = item["path"].casefold()
        if key in folded:
            raise UpdateError("安装文件清单包含重复路径")
        folded.add(key)
        entries[item["path"]] = item
    locks = {item["path"]: item for item in plan.get("required_locks", [])}
    expected = {name for name in entries if is_dependency_path(name)}
    if not expected.issubset(locks):
        raise UpdateError("更新包缺少依赖兼容性检查，请重新下载正式更新包")
    for name, item in locks.items():
        path = safe_path(root, name)
        if not path.is_file() or digest(path) != item["sha256"]:
            raise UpdateError("依赖版本不兼容，请使用完整升级：" + name)
    already_current = current == plan["version"]
    for item in plan["files"]:
        name = item["path"]
        source, destination = safe_path(bundle_dir / "payload", name), safe_path(root, name)
        if not source.is_file() or source.stat().st_size != item["size"] or digest(source) != item["sha256"]:
            raise UpdateError("更新包文件损坏：" + name)
        if destination.exists() and not destination.is_file():
            raise UpdateError("程序文件位置被其他目录占用：" + name)
        if already_current:
            if not destination.is_file() or digest(destination) != item["sha256"]:
                raise UpdateError("已安装版本的程序文件有变化，请修复安装")
        elif destination.is_file():
            before = digest(destination)
            entry = entries.get(name)
            if not entry or entry.get("mutable") or entry.get("sha256") != before:
                raise UpdateError("本机程序文件已被修改，已停止覆盖：" + name)
            if "before_sha256" in item and item["before_sha256"] != before:
                raise UpdateError("程序文件与更新基线不匹配：" + name)
        elif name in entries or item.get("before_sha256") is not None:
            raise UpdateError("更新基线中的程序文件缺失：" + name)
    return plan


@contextmanager
def _install_lock(root):
    path = safe_path(root, ".local/app-updates/installer.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    # An OS lock is released even after a power failure or killed process.  Do
    # not unlink the file: another process could already have opened that inode.
    stream = path.open("a+b")
    try:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise UpdateError("另一次安装或恢复尚未结束，请先检查更新记录") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        stream.close()


def _new_metadata(root, plan):
    release = _read(safe_path(root, "RELEASE.json"))
    release.update({key: plan[key] for key in ("edition", "version", "runtime_id", "data_schema", "platform")})
    release.update(channel="stable", updated_at=_time())
    for key in ("source_commit", "published_at"):
        if key in plan:
            release[key] = plan[key]
    release_bytes = json_bytes(release)
    manifest = _read(safe_path(root, "PACKAGE-MANIFEST.json"))
    entries = {item["path"]: item for item in manifest["files"]}
    for item in plan["files"]:
        entries[item["path"]] = {key: item[key] for key in ("path", "size", "sha256")}
        entries[item["path"]]["mutable"] = False
    entries["RELEASE.json"] = {"path": "RELEASE.json", "size": len(release_bytes),
                               "sha256": hashlib.sha256(release_bytes).hexdigest(), "mutable": False}
    manifest["files"] = [entries[name] for name in sorted(entries)]
    return {"RELEASE.json": release_bytes, "PACKAGE-MANIFEST.json": json_bytes(manifest)}


def apply_update(bundle_dir, root, health_check=None):
    """Apply atomically per file; roll all files back if installation/restart fails.

    ``health_check(root, plan)`` must return a truthy value after restarting and
    verifying the service.  Before calling this, the worker must quiesce it.
    The receipt is persisted before the first replacement, so rollback also
    understands an interrupted process which wrote only part of the patch.
    """
    bundle_dir, root = Path(bundle_dir).resolve(), Path(root).resolve()
    plan = preflight(bundle_dir, root)
    if read_release(root).get("version") == plan["version"]:
        return {"ok": True, "already_current": True, "status": "complete", "version": plan["version"], "files_updated": 0}
    with _install_lock(root):
        plan = preflight(bundle_dir, root)
        directory = safe_path(root, ".local/app-updates/" + plan["version"] + "-" + uuid4().hex)
        directory.mkdir(parents=True, exist_ok=False)
        contents = {item["path"]: safe_path(bundle_dir / "payload", item["path"]).read_bytes() for item in plan["files"]}
        contents.update(_new_metadata(root, plan))
        rows = []
        for name, content in contents.items():
            original = safe_path(root, name)
            row = {"path": name, "existed": original.is_file(), "after_sha256": hashlib.sha256(content).hexdigest()}
            if row["existed"]:
                backup = safe_path(directory / "files", name)
                backup.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write(backup, original.read_bytes())
                row["before_sha256"] = digest(backup)
            rows.append(row)
        receipt = {"schema": 1, "installation": str(root), "status": "prepared", "created_at": _time(),
                   "base_version": plan["base_version"], "version": plan["version"], "files": rows}
        receipt_path = directory / "receipt.json"
        _atomic_write(receipt_path, json_bytes(receipt))
        try:
            receipt["status"] = "applying"
            _atomic_write(receipt_path, json_bytes(receipt))
            for name, content in contents.items():
                _atomic_write(safe_path(root, name), content)
            receipt["status"] = "checking"
            _atomic_write(receipt_path, json_bytes(receipt))
            if health_check is not None and not health_check(root, plan):
                raise UpdateError("新版工作台启动检查未通过")
            receipt.update(status="complete", completed_at=_time())
            _atomic_write(receipt_path, json_bytes(receipt))
        except Exception as error:
            try:
                # The outer lock is still held; no second updater can write.
                _rollback(root, directory, check_hashes=True)
            except Exception as recovery_error:
                raise UpdateError("更新失败，自动恢复未完成；请保留更新备份并恢复：" + str(directory)) from recovery_error
            raise UpdateError("更新失败，程序已回退到原版本：" + str(error)) from error
        return {"ok": True, "status": "complete", "version": plan["version"], "backup": str(directory),
                "files_updated": len(plan["files"])}


def _rollback(root, backup_dir, check_hashes=True):
    root = Path(root).resolve(strict=True)
    backup_dir = Path(backup_dir).resolve(strict=True)
    container = safe_path(root, ".local/app-updates")
    if backup_dir == container or not backup_dir.is_relative_to(container):
        raise UpdateError("备份不属于当前安装目录")
    relative = backup_dir.relative_to(root).as_posix()
    safe_path(root, relative)
    receipt = _read(safe_path(backup_dir, "receipt.json"))
    if receipt.get("schema") != 1 or receipt.get("installation") != str(root) or not isinstance(receipt.get("files"), list):
        raise UpdateError("更新回执不属于当前安装或已损坏")
    rows, seen = receipt["files"], set()
    for row in rows:
        name = row.get("path") if isinstance(row, dict) else None
        if not isinstance(name, str) or not (is_program_path(name) or name in {"RELEASE.json", "PACKAGE-MANIFEST.json"}):
            raise UpdateError("恢复回执包含受保护路径")
        if name.casefold() in seen:
            raise UpdateError("恢复回执包含重复文件")
        seen.add(name.casefold())
        if type(row.get("existed")) is not bool or not _SHA.fullmatch(str(row.get("after_sha256", ""))):
            raise UpdateError("更新恢复记录无效")
        current = safe_path(root, name)
        if current.exists() and not current.is_file():
            raise UpdateError("恢复路径被目录占用：" + name)
        if row["existed"]:
            source = safe_path(backup_dir / "files", name)
            if (not _SHA.fullmatch(str(row.get("before_sha256", ""))) or not source.is_file()
                    or digest(source) != row["before_sha256"]):
                raise UpdateError("更新备份校验失败：" + name)
        if check_hashes:
            current_hash = digest(current) if current.is_file() else None
            accepted = {row["after_sha256"], row.get("before_sha256") if row["existed"] else None}
            if current_hash not in accepted:
                raise UpdateError("更新后文件又被修改，已停止覆盖：" + name)
    for row in rows:
        destination = safe_path(root, row["path"])
        if row["existed"]:
            _atomic_write(destination, safe_path(backup_dir / "files", row["path"]).read_bytes())
        else:
            destination.unlink(missing_ok=True)
    receipt.update(status="rolled_back", restored_at=_time())
    _atomic_write(backup_dir / "receipt.json", json_bytes(receipt))
    return {"ok": True, "status": "rolled_back", "version": receipt.get("base_version"),
            "backup": str(backup_dir), "restored_files": len(rows)}


def rollback(root, backup_dir, check_hashes=True):
    """Restore a complete or partially applied receipt without touching user data."""
    with _install_lock(root):
        return _rollback(root, backup_dir, check_hashes=check_hashes)


def extract_bundle(zip_path, destination):
    """Extract a bounded, exact manifest payload; never follow archive links."""
    zip_path, destination = Path(zip_path), Path(destination)
    if zip_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise UpdateError("更新压缩包超过大小限制")
    if destination.is_symlink() or (hasattr(destination, "is_junction") and destination.is_junction()):
        raise UpdateError("更新解压目录不能是链接")
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise UpdateError("更新解压目录必须为空")
    destination = destination.resolve()
    try:
        with zipfile.ZipFile(zip_path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILES + 100:
                raise UpdateError("更新压缩包文件数量超过限制")
            seen, files = set(), {}
            expanded = 0
            for info in infos:
                name = info.filename.rstrip("/") if info.is_dir() else info.filename
                _parts(name)
                key = name.casefold()
                if key in seen:
                    raise UpdateError("更新压缩包包含重复路径")
                seen.add(key)
                mode = info.external_attr >> 16
                if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise UpdateError("更新压缩包不允许链接或特殊文件")
                if stat.S_IFMT(mode) == stat.S_IFDIR and not info.is_dir():
                    raise UpdateError("更新压缩包文件类型无效")
                if info.flag_bits & 1:
                    raise UpdateError("更新压缩包不能加密")
                if info.is_dir():
                    if name != "payload" and not name.startswith("payload/"):
                        raise UpdateError("更新压缩包目录无效")
                    continue
                if name != "UPDATE-MANIFEST.json" and not name.startswith("payload/"):
                    raise UpdateError("更新压缩包含未知文件")
                limit = MAX_MANIFEST_BYTES if name == "UPDATE-MANIFEST.json" else MAX_FILE_BYTES
                expanded += info.file_size
                if info.file_size > limit or expanded > MAX_EXPANDED_BYTES:
                    raise UpdateError("更新压缩包展开大小超过限制")
                if info.file_size > 1024 * 1024 and info.file_size > max(info.compress_size, 1) * 300:
                    raise UpdateError("更新压缩包压缩比例异常")
                files[name] = info
            if "UPDATE-MANIFEST.json" not in files:
                raise UpdateError("更新压缩包缺少版本清单")
            manifest_bytes = archive.read(files["UPDATE-MANIFEST.json"])
            plan = _plan(_json(manifest_bytes))
            expected = {"UPDATE-MANIFEST.json", *("payload/" + item["path"] for item in plan["files"])}
            if set(files) != expected:
                raise UpdateError("更新压缩包文件与清单不一致")
            destination.mkdir(parents=True, exist_ok=True)
            for name, info in files.items():
                target = safe_path(destination, name)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
            for item in plan["files"]:
                path = safe_path(destination / "payload", item["path"])
                if path.stat().st_size != item["size"] or digest(path) != item["sha256"]:
                    raise UpdateError("更新包文件校验失败：" + item["path"])
            return plan
    except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError) as error:
        raise UpdateError("更新包无法完整解压，请重新下载") from error
