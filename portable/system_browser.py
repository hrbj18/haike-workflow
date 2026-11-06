"""Discover an installed browser without downloading it or opening a window."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import sys


def candidates(env=None, platform=None):
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    explicit = env.get('HAIKE_BROWSER_PATH') or env.get('CHROME_PATH')
    if explicit:
        yield Path(explicit)
    if platform == 'win32':
        for variable in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            base = env.get(variable)
            if base:
                yield Path(base) / 'Google/Chrome/Application/chrome.exe'
        try:
            import winreg
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                    try:
                        with winreg.OpenKey(hive, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe',
                                            0, winreg.KEY_READ | view) as key:
                            yield Path(winreg.QueryValue(key, None).strip('"'))
                    except OSError:
                        pass
        except ImportError:
            pass
        for variable in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            if env.get(variable):
                yield Path(env[variable]) / 'Microsoft/Edge/Application/msedge.exe'
    elif platform == 'darwin':
        for base in (Path('/Applications'), Path.home() / 'Applications'):
            yield base / 'Google Chrome.app/Contents/MacOS/Google Chrome'
            yield base / 'Microsoft Edge.app/Contents/MacOS/Microsoft Edge'
    for name in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'chrome', 'msedge'):
        found = shutil.which(name, path=env.get('PATH', ''))
        if found:
            yield Path(found)
    # Retain explicit, already installed legacy runtimes; discovery never obtains one.
    if env.get('REMOTION_BROWSER_EXECUTABLE'):
        yield Path(env['REMOTION_BROWSER_EXECUTABLE'])


def resolve(env=None, *, required=True, platform=None):
    env = os.environ if env is None else env
    explicit = env.get('HAIKE_BROWSER_PATH') or env.get('REMOTION_BROWSER_EXECUTABLE') or env.get('CHROME_PATH')
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return path.resolve()
        if required:
            raise ValueError('配置的本地浏览器不存在；请选择已安装的Chrome/Edge，海客不会自动下载浏览器。')
        return None
    for path in candidates(env, platform):
        if path.is_file():
            return path.resolve()
    if required:
        raise ValueError('未找到本机 Chrome 或 Edge，请安装浏览器后重试；海客不会自动下载浏览器。')
    return None


def identity(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'sha256': checksum, 'source': 'existing-local-browser'}


def environment(base=None, *, required=True):
    env = dict(os.environ if base is None else base)
    path = resolve(env, required=required)
    if path:
        for name in ('REMOTION_BROWSER_EXECUTABLE', 'CHROME_PATH', 'HYPERFRAMES_BROWSER_PATH',
                     'PRODUCER_HEADLESS_SHELL_PATH'):
            env[name] = str(path)
    env.update(PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD='1', PUPPETEER_SKIP_DOWNLOAD='true',
               HYPERFRAMES_NO_AUTO_INSTALL='1')
    return env
