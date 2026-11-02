"""Cached selftest evidence cannot survive changed tools, pixels or location."""
from pathlib import Path

import pytest

from portable import app_update as core, template_selftest as smoke


@pytest.fixture
def receipt(tmp_path):
    root = tmp_path / '安装 空格'; folder = root / '.local/template-selftests/test-run'; folder.mkdir(parents=True)
    tools = {'python': 'runtime/python/python.exe', 'node': 'runtime/node/node.exe',
             'ffmpeg': 'runtime/ffmpeg/bin/ffmpeg.exe', 'ffprobe': 'runtime/ffmpeg/bin/ffprobe.exe',
             'browser': 'runtime/browser/chrome-headless-shell.exe'}
    for name in tools.values():
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(name.encode())
    files = ['codec.mp4', 'frame-0.png', 'frame-1.png']
    for name in files: (folder / name).write_bytes(name.encode())
    result = {'schema': 'haike.template-selftest/1', 'status': 'passed', 'capability_sha256': 'a' * 64,
              'install_root': str(root), 'scope': 'unit-test-only-not-render-proof',
              'tool_hashes': {k: core.digest(root / n) for k, n in tools.items()},
              'files': {n: core.digest(folder / n) for n in files}}
    (folder / 'result.json').write_bytes(core.json_bytes(result))
    (folder.parent / 'latest.json').write_bytes(core.json_bytes({'directory': folder.relative_to(root).as_posix(),
                                                                'sha256': core.digest(folder / 'result.json')}))
    return root, folder


def test_cached_receipt_binds_tools_files_and_capability(receipt):
    root, folder = receipt
    assert smoke.recorded(root, 'a' * 64)['status'] == 'passed'
    assert smoke.recorded(root, 'b' * 64)['status'] == 'pending'
    (folder / 'frame-1.png').write_bytes(b'changed')
    assert smoke.recorded(root, 'a' * 64)['status'] == 'pending'


def test_changed_tool_or_moved_location_requires_fresh_selftest(receipt):
    root, _ = receipt
    (root / 'runtime/node/node.exe').write_bytes(b'changed-node')
    assert smoke.recorded(root, 'a' * 64)['status'] == 'pending'
    moved = root.with_name('moved'); root.rename(moved)
    assert smoke.recorded(moved, 'a' * 64)['status'] == 'pending'


def test_selftest_environment_does_not_inherit_developer_paths(tmp_path, monkeypatch):
    monkeypatch.setenv('PYTHONHOME', 'C:/developer/python')
    monkeypatch.setenv('PYTHONPATH', 'C:/developer/modules')
    monkeypatch.setenv('PATH', 'C:/developer/tools')
    monkeypatch.setenv('API_KEY', 'unit-test-not-real')
    env = smoke.environment(tmp_path, tmp_path / 'output')
    assert 'PYTHONHOME' not in env and 'API_KEY' not in env
    assert 'developer' not in env['PATH'] and 'developer' not in env['PYTHONPATH']
    assert str(tmp_path / 'runtime/browser/chrome-headless-shell.exe') == env['CHROME_PATH']
