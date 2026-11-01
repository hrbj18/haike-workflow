"""Pinned resources, safe venv generation and moved-install recovery."""
from pathlib import Path
import shutil

import pytest

from portable import app_update as core
from portable import motion_runtime as runtime


@pytest.fixture
def installed(tmp_path, monkeypatch):
    root = tmp_path / '旧安装 空格'; root.mkdir()
    helper = core.safe_path(root, runtime.HELPER); helper.parent.mkdir(parents=True)
    helper.write_bytes(b'pinned-test-helper')
    monkeypatch.setattr(runtime, 'HELPER_SHA', core.digest(helper))
    monkeypatch.setattr(runtime, 'HELPER_BYTES', helper.stat().st_size)
    rows = []
    for identity, data in runtime.PROFILES.items():
        source = tmp_path / identity
        (source / data['venv'] / 'Scripts').mkdir(parents=True)
        (source / data['venv'] / 'Scripts/python.exe').write_bytes(b'generic-venv-launcher')
        (source / data['venv'] / 'Scripts/pip.exe').write_bytes(b'old-absolute-path-launcher')
        (source / data['venv'] / 'pyvenv.cfg').write_text('home = C:/another-person/python')
        if data['workflow'] == 'motion-kit':
            for name in ['package.json', 'package-lock.json', 'kit-dependencies.json']:
                (source / name).write_text('{}')
        row, files = runtime.build_profile(identity, source)
        rows.append(row)
        for name, file in files:
            destination = core.safe_path(root, name); destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, destination)
    manifest = runtime.validate({'schema': runtime.SCHEMA, 'profiles': rows})
    path = core.safe_path(root, runtime.PATH); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(core.json_bytes(manifest))
    for name, content in runtime.configuration_writes(root, manifest):
        core._atomic_write(core.safe_path(root, name), content)
    return root, manifest


def test_venv_is_bound_to_this_install_without_foreign_launchers(installed):
    root, manifest = installed
    assert runtime.verify(root)['status'] == 'verified'
    for row in manifest['profiles']:
        assert not any(name.endswith('pyvenv.cfg') or name.endswith('pip.exe') for name in row['files'])
        path = root / row['cache'] / row['venv'] / 'pyvenv.cfg'
        assert str(root / 'runtime/python') in path.read_text(encoding='utf-8')
        assert 'another-person' not in path.read_text(encoding='utf-8')


def test_moved_install_only_rebinds_owned_configuration(installed, tmp_path):
    root, _ = installed
    moved = tmp_path / '新安装 中文'; root.rename(moved)
    with pytest.raises(ValueError, match='绑定当前安装位置'):
        runtime.verify(moved)
    assert runtime.relocate(moved)['configurations_updated'] == 2
    assert runtime.verify(moved)['status'] == 'verified'
    assert runtime.relocate(moved)['configurations_updated'] == 0


def test_foreign_cfg_and_tampered_dependency_are_not_silently_repaired(installed):
    root, manifest = installed
    row = manifest['profiles'][0]
    cfg = root / row['cache'] / row['venv'] / 'pyvenv.cfg'
    cfg.write_text('home = C:/user-owned-python')
    with pytest.raises(ValueError, match='其他环境配置'):
        runtime.relocate(root)
    assert cfg.read_text() == 'home = C:/user-owned-python'
    file = root / row['cache'] / row['venv'] / 'Scripts/python.exe'
    file.write_bytes(b'changed')
    with pytest.raises(ValueError, match='依赖缺失或已改变'):
        runtime.verify(root)


def test_only_exact_template_versions_can_resolve_a_runtime(installed):
    root, _ = installed
    p = {'template_id': 'knowledge-explainer-sketchnote', 'version': '2.7.3', 'helper_version': '1.0.0-rc.54'}
    assert runtime.resolve(root, p, 'native')['cache_path'] == str(root / runtime.PROFILES['knowledge-rc54-v1']['cache'])
    p['version'] = '2.7.4'
    assert runtime.resolve(root, p, 'native') is None
    for name in ['.local/config/key.json', '.local/md/unknown/evil.exe', runtime.PROFILES['paper-rc54-v1']['cache'] + '/.venv/pyvenv.cfg']:
        assert not runtime.public_resource(name)
