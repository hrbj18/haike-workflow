"""Prepare and launch an extracted Windows bundle without installing anything."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
REPOS = ("Haike_video", "copy_skill/copy_skill-main", "creatorhub")
CRAWLER = "copy_skill/copy_skill-main/third_party/MediaCrawler"
BROWSER = "runtime/browser/chrome-headless-shell.exe"
DLLS = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll")


def local_path(relative: str) -> Path:
    """Reject escaping paths and links before reading or changing bundle files."""
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Bundle path must stay inside the extracted directory")
    root = ROOT.resolve()
    target = root / path
    cursor = root
    for component in path.parts:
        cursor = cursor / component
        if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
            raise ValueError("Bundle paths cannot use symbolic links or junctions")
    if not target.resolve().is_relative_to(root):
        raise ValueError("Bundle path escapes the extracted directory")
    return target


def write_text(relative: str, value: str) -> None:
    target = local_path(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and target.read_text(encoding="utf-8-sig") == value:
        return
    fd, temporary = tempfile.mkstemp(prefix=".portable-", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_json(relative: str, value: object) -> None:
    write_text(relative, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read_json(relative: str, fallback=None):
    path = local_path(relative)
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise ValueError("Invalid local JSON: " + relative) from error


def system_chrome() -> Path | None:
    for name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        value = os.environ.get(name)
        if value:
            candidate = Path(value) / "Google/Chrome/Application/chrome.exe"
            if candidate.is_file():
                return candidate
    return None


def bundled_login_browser() -> Path | None:
    candidates = list(local_path("runtime/playwright").glob("chromium-*/chrome-win64/chrome.exe"))
    if len(candidates) != 1:
        return None
    return local_path(candidates[0].relative_to(ROOT.resolve()).as_posix())


def login_browser() -> Path | None:
    """Prefer installed Chrome; the full bundled Chromium is a search fallback."""
    return system_chrome() or bundled_login_browser()


def environment() -> dict[str, str]:
    env = os.environ.copy()
    paths = [ROOT / name for name in ("runtime/python", "runtime/node", "runtime/ffmpeg/bin",
                                     "runtime/hyperframes/node_modules/.bin")]
    paths.append(Path(env.get("SystemRoot", "C:/Windows")) / "System32")
    env["PATH"] = os.pathsep.join(map(str, paths)) + os.pathsep + env.get("PATH", "")
    env.pop("PYTHONHOME", None)
    env["PYTHONPATH"] = ""
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONNOUSERSITE="1",
               HAIKE_PORTABLE_OFFLINE="1", VIDEOHUB_ROOT=str(ROOT),
               DOUYIN_MSVC_RUNTIME_DIR=str(ROOT / "runtime/msvc"),
               FFMPEG_BINARY=str(ROOT / "runtime/ffmpeg/bin/ffmpeg.exe"),
               FFPROBE_BINARY=str(ROOT / "runtime/ffmpeg/bin/ffprobe.exe"),
               REMOTION_BROWSER_EXECUTABLE=str(ROOT / BROWSER),
               CHROME_PATH=str(ROOT / BROWSER),
               HYPERFRAMES_BROWSER_PATH=str(ROOT / BROWSER),
               PRODUCER_HEADLESS_SHELL_PATH=str(ROOT / BROWSER),
               HYPERFRAMES_FFMPEG_PATH=str(ROOT / "runtime/ffmpeg/bin/ffmpeg.exe"),
               HYPERFRAMES_FFPROBE_PATH=str(ROOT / "runtime/ffmpeg/bin/ffprobe.exe"),
               HYPERFRAMES_NO_TELEMETRY="1", HYPERFRAMES_NO_AUTO_INSTALL="1",
               HYPERFRAMES_NO_UPDATE_CHECK="1", PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD="1",
               PLAYWRIGHT_BROWSERS_PATH=str(ROOT / "runtime/playwright"),
               HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false",
               PIP_NO_INDEX="1", UV_OFFLINE="1", UV_PYTHON_DOWNLOADS="never",
               NPM_CONFIG_OFFLINE="true", BACKLOT_DETACHED="1")
    env["NO_PROXY"] = ",".join(filter(None, (env.get("NO_PROXY", ""), "localhost,127.0.0.1,::1")))
    return env


@contextmanager
def bundle_lock():
    target = local_path(".portable/start.lock")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + 45
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("另一个初始化或启动仍在执行，请稍后重试")
                time.sleep(.2)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def prepare() -> dict:
    started = time.monotonic()
    base = local_path("runtime/python")
    if not (base / "python.exe").is_file():
        raise RuntimeError("离线 Python 缺失，请完整解压发行包；不会在线安装")
    repos = list(REPOS)
    if local_path(CRAWLER + "/.venv").is_dir():
        repos.append(CRAWLER)
    for repo in repos:
        if not local_path(repo + "/.venv/Scripts/python.exe").is_file():
            raise RuntimeError("离线环境缺失：" + repo)
        write_text(repo + "/.venv/pyvenv.cfg",
                   f"home = {base}\ninclude-system-site-packages = false\nexecutable = {base / 'python.exe'}\n")
    copy = "copy_skill/copy_skill-main"
    libraries = local_path(copy + "/.venv/Lib/site-packages")
    for path in libraries.glob("__editable__.douyin_content_intelligence-*.pth"):
        write_text(path.relative_to(ROOT.resolve()).as_posix(), "../../../src\n")
    override_path = copy + "/config/content_intelligence.local.json"
    override = read_json(override_path, {})
    if not isinstance(override, dict):
        raise ValueError("采集本地配置必须是 JSON 对象，原文件已保留")
    # Set missing defaults only: existing user choices belong to this user.
    ff = "../../runtime/ffmpeg/bin/ffmpeg.exe"
    fp = "../../runtime/ffmpeg/bin/ffprobe.exe"
    def defaults(container, key, values):
        obj = container.setdefault(key, {})
        if not isinstance(obj, dict):
            raise ValueError("采集本地配置字段无效：" + key)
        for name, value in values.items():
            obj.setdefault(name, value)
        return obj
    defaults(override, "media_tools", {"ffmpeg": ff, "ffprobe": fp})
    jobs = defaults(override, "jobs", {"lock_root": ".locks"})
    replication = defaults(jobs, "material_replication", {})
    defaults(replication, "episode_research_pack", {"consumer_root": "../../Haike_video"})
    trusted = defaults(jobs, "trusted_account_news", {})
    defaults(trusted, "visual_ocr", {"ffmpeg_path": ff, "ffprobe_path": fp})
    if CRAWLER in repos:
        crawler = defaults(override, "media_crawler", {"root": "third_party/MediaCrawler",
                           "python": "third_party/MediaCrawler/.venv/Scripts/python.exe"})
        browser = login_browser()
        configured = crawler.get("chrome_path")
        if browser and (not configured or not Path(configured).is_file()):
            crawler["chrome_path"] = str(browser)
    write_json(override_path, override)
    for source, target in (("Haike_video/.env.example", "Haike_video/.env.local"),
                           ("creatorhub/config.example.yaml", "creatorhub/config.yaml")):
        if not local_path(target).exists():
            write_text(target, local_path(source).read_text(encoding="utf-8-sig"))
    for relative in (".portable/logs", "Haike_video/projects", "Haike_video/renders",
                     "Haike_video/cache", "Haike_video/temp", "Haike_video/work", "creatorhub/data"):
        local_path(relative).mkdir(parents=True, exist_ok=True)
    result = {"ok": True, "command": "prepare", "root": str(ROOT), "venvs": repos,
              "network_install": False, "local_tts": "optional_not_started",
              "seconds": round(time.monotonic() - started, 3)}
    write_json(".portable/prepared.json", result)
    return result


def integrity() -> int:
    manifest = read_json("PACKAGE-MANIFEST.json")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise ValueError("完整文件清单缺失或无效")
    count, seen = 0, set()
    for entry in manifest["files"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError("文件清单条目无效")
        name = entry["path"]
        path = local_path(name)
        if name in seen:
            raise ValueError("文件清单含重复路径")
        seen.add(name)
        if entry.get("mutable") is True:
            continue
        expected = entry.get("sha256")
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError("文件清单缺少 SHA256：" + name)
        if not path.is_file():
            raise RuntimeError("发行文件缺失：" + name)
        with path.open("rb") as handle:
            actual = hashlib.file_digest(handle, "sha256").hexdigest()
        if actual != expected:
            raise RuntimeError("发行文件校验失败：" + name)
        count += 1
    if not count:
        raise ValueError("文件清单没有不可变文件")
    return count


def run_probe(name: str, command: list[str], *, cwd=None, timeout=60, env=None) -> dict:
    try:
        completed = subprocess.run(command, cwd=cwd or ROOT, env=environment() if env is None else env, capture_output=True,
                                   timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("离线运行检查无法完成：" + name) from error
    if completed.returncode:
        # Do not print process output: configuration errors may contain local data.
        write_text(".portable/logs/diagnose-" + name + ".log",
                   completed.stderr.decode("utf-8", errors="replace"))
        raise RuntimeError("离线运行检查失败：" + name + "；请查看 .portable/logs")
    return {"name": name, "ok": True}


def run_launcher(command: list[str], *, env, timeout=200) -> None:
    # Detached services can inherit the launcher's output handles. A capture
    # pipe would then wait for those services to exit even after PowerShell
    # has returned. Files let us wait only for this launcher process.
    out_path = local_path(".portable/logs/launcher.out.log")
    err_path = local_path(".portable/logs/launcher.err.log")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    logs = ".portable/logs/launcher.out.log 与 .portable/logs/launcher.err.log"
    try:
        with out_path.open("ab") as out, err_path.open("ab") as err:
            completed = subprocess.run(
                command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                stdout=out, stderr=err, timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("启动器未能完成，请查看 " + logs) from error
    if completed.returncode:
        raise RuntimeError(f"启动器退出码 {completed.returncode}，请查看 " + logs)


def diagnose(full=False) -> dict:
    # Older full bundles require both components. New bundles may explicitly
    # declare either absent; never infer absence from a missing file.
    components = read_json("RUNTIME-INVENTORY.json", {}).get("optional_components", {})
    if (not isinstance(components, dict) or set(components) - {"hyperframes", "whisper_small"}
            or any(type(v) is not bool for v in components.values())):
        raise ValueError("运行环境组件清单无效")
    required = ["runtime/python/python.exe", "runtime/python/pythonw.exe", "runtime/node/node.exe",
                "runtime/ffmpeg/bin/ffmpeg.exe", "runtime/ffmpeg/bin/ffprobe.exe", BROWSER,
                "Haike_video/backlot/server.py", "Haike_video/backlot/ui/avatar-generator/index.html",
                "Haike_video/remotion-composer/node_modules/@remotion/cli/package.json"]
    if components.get("hyperframes", True):
        required.append("runtime/hyperframes/node_modules/hyperframes/package.json")
    required += ["runtime/msvc/" + name for name in DLLS]
    required += [repo + "/.venv/Scripts/" + name + ".exe" for repo in REPOS for name in ("python", "pythonw")]
    missing = [name for name in required if not local_path(name).is_file()]
    if missing:
        raise RuntimeError("发行包缺少必要文件：" + ", ".join(missing[:8]))
    models = list(local_path("runtime/models/whisper-small").glob("*/model.bin"))
    if components.get("whisper_small", True) and (len(models) != 1 or not all((models[0].parent / n).is_file()
                                 for n in ("config.json", "tokenizer.json", "vocabulary.txt"))):
        raise RuntimeError("离线 Whisper-small 模型不完整")
    bootstrap = ("import ctypes,os; "
                 "ctypes.windll.kernel32.SetErrorMode(0x8003) if os.name=='nt' else None; "
                 "import site; site.main(); import sys; assert sys.version_info[:2]==(3,12); ")
    imports = {"Haike_video": "import fastapi,uvicorn,onnxruntime,ctranslate2,faster_whisper; from faster_whisper.vad import get_speech_timestamps",
               "copy_skill/copy_skill-main": "import onnxruntime,ctranslate2,faster_whisper,douyin_intelligence",
               "creatorhub": "import fastapi,uvicorn,sqlmodel,patchright"}
    checks = []
    for repo, code in imports.items():
        checks.append(run_probe(repo.split('/')[0], [str(ROOT / repo / ".venv/Scripts/python.exe"),
                                "-S", "-c", bootstrap + code], cwd=ROOT / repo))
    model_code = (bootstrap + "from faster_whisper.vad import get_vad_model; get_vad_model(); "
                  "from faster_whisper import WhisperModel; "
                  "WhisperModel(sys.argv[1],device='cpu',compute_type='int8',local_files_only=True,cpu_threads=1,num_workers=1)")
    if components.get("whisper_small", True):
        model_dir = local_path(models[0].parent.relative_to(ROOT.resolve()).as_posix())
        checks.append(run_probe("whisper-small", [str(ROOT / "Haike_video/.venv/Scripts/python.exe"),
                                "-S", "-c", model_code, str(model_dir)]))
    for name, command in (("node", [str(ROOT / "runtime/node/node.exe"), "--version"]),
                          ("ffmpeg", [str(ROOT / "runtime/ffmpeg/bin/ffmpeg.exe"), "-version"]),
                          ("browser", [str(ROOT / BROWSER), "--version"])):
        checks.append(run_probe(name, command))
    result = {"ok": True, "command": "diagnose", "root": str(ROOT), "full": full,
              "checks": checks, "file_count": integrity() if full else None,
              "optional_components": {name: components.get(name, True) for name in ("hyperframes", "whisper_small")},
              "models": {"whisper_small": "loadable" if components.get("whisper_small", True) else "not_installed", "clean_install_default_asr": "gateway"},
              "browsers": {"system_chrome": system_chrome() is not None,
                           "bundled_interactive_browser": bundled_login_browser() is not None},
              "network_install": False, "physical_new_machine_tested": False}
    write_json(".portable/logs/diagnose.json", result)
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def http_json(port: int, path: str):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(f"http://127.0.0.1:{port}{path}", timeout=1.5) as response:
            return json.loads(response.read(1024 * 1024).decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return None


def own_service(port: int, kind: str) -> bool:
    if kind == "backlot":
        health = http_json(port, "/api/health")
        if not isinstance(health, dict) or health.get("ok") is not True or health.get("app") != "backlot" or health.get("edition") != "haike-workflow-2":
            return False
        try:
            return Path(health["workspace"]).resolve() == ROOT.resolve()
        except (KeyError, TypeError, ValueError):
            return False
    response = http_json(port, "/api/download-sessions")
    expected = hashlib.sha256(str((ROOT / "creatorhub").resolve()).replace("\\", "/").casefold().encode()).hexdigest()
    return isinstance(response, dict) and response.get("service_fingerprint") == expected


def choose_port(requested: int, kind: str, excluded=()) -> tuple[int, bool]:
    if not 1024 <= requested <= 65535:
        raise ValueError("端口必须在 1024 至 65535 之间")
    state = read_json(".portable/services.json", {})
    records = state.get("services", []) if isinstance(state, dict) else []
    previous = [r.get("port") for r in records if isinstance(r, dict) and r.get("kind") == kind]
    candidates = list(dict.fromkeys(previous + list(range(requested, min(requested + 100, 65536)))))
    for port in candidates:
        if type(port) is not int or not 1024 <= port <= 65535 or port in excluded:
            continue
        if own_service(port, kind):
            return port, True
        try:
            with socket.socket() as sock:
                if os.name == "nt":
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                sock.bind(("127.0.0.1", port))
            return port, False
        except OSError:
            continue
    raise RuntimeError(f"{requested} 附近无可用端口；未停止其他服务")


def start(port=14756, publisher_port=8000, no_browser=False) -> dict:
    prepare()
    diagnose()
    selected, _ = choose_port(port, "backlot")
    account_port, _ = choose_port(publisher_port, "creatorhub", {selected})
    env = environment()
    env["HAIKE_CREATORHUB_URL"] = f"http://127.0.0.1:{account_port}"
    env["BACKLOT_NO_BROWSER"] = "1"
    command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
               "-File", str(ROOT / "start-workbench.ps1"), "-Port", str(selected), "-NoBrowser"]
    run_launcher(command, timeout=200, env=env)
    # Use the selected account URL even when the shell inherited another value.
    # The existing launcher rechecks the same workspace identity before reusing.
    if not own_service(selected, "backlot") or not own_service(account_port, "creatorhub"):
        raise RuntimeError("启动器未返回当前副本的两个服务，请查看 .local/launcher 与 .backlot/logs")
    services = [{"kind": "backlot", "port": selected, "url": f"http://127.0.0.1:{selected}/avatar"},
                {"kind": "creatorhub", "port": account_port, "url": f"http://127.0.0.1:{account_port}/"}]
    result = {"ok": True, "command": "start", "root": str(ROOT), "services": services,
              "network_install": False, "local_tts": "optional_not_started"}
    write_json(".portable/services.json", result)
    if not no_browser:
        try:
            result["browser_opened"] = bool(webbrowser.open(services[0]["url"]))
        except (webbrowser.Error, OSError):
            result["browser_opened"] = False
    return result


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare")
    check = commands.add_parser("diagnose")
    check.add_argument("--full", action="store_true")
    launcher = commands.add_parser("start")
    launcher.add_argument("--port", type=int, default=14756)
    launcher.add_argument("--publisher-port", type=int, default=8000)
    launcher.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    try:
        with bundle_lock():
            if args.command == "prepare":
                result = prepare()
            elif args.command == "diagnose":
                prepare()
                result = diagnose(args.full)
            else:
                result = start(args.port, args.publisher_port, args.no_browser)
    except (OSError, ValueError, RuntimeError) as error:
        result = {"ok": False, "command": args.command, "message": str(error), "network_install": False}
        print(json.dumps(result, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
