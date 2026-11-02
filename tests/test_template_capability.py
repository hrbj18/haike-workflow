"""Actual delivery hashes and corruption recovery, without any paid runtime."""
from copy import deepcopy
import importlib.util
import io
import json
import re
from pathlib import Path
import shutil
from unittest.mock import patch

import pytest

from portable import app_update as core
from portable import template_capability as capability

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('capability_online_updater', ROOT / 'scripts/update-from-github.py')
updater = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(updater)


@pytest.fixture
def stage(tmp_path):
    root = tmp_path / '中文 空格安装'
    manifest = json.loads((ROOT / capability.MANIFEST).read_text(encoding='utf-8'))
    names = {capability.MANIFEST, *capability.TRANSPORT}
    for row in manifest['presets']:
        names.add('Haike_video/templates/motion-presets/' + row['recipe'])
        names.update(row['engine_files'])
    for name in names:
        target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    ui = root / 'Haike_video/backlot/ui/avatar-generator'
    ui.mkdir(parents=True); (ui / 'index.html').write_text('<html>compiled entry</html>', encoding='utf-8')
    (ui / 'chunk.js').write_text('export const built=true;', encoding='utf-8')
    expected = capability.write(root)
    (root / 'RELEASE.json').write_bytes(core.json_bytes({'version': '1.2.2', 'template_capability': expected}))
    return root, expected


def test_delivery_verifies_exact_files_and_contains_no_personal_inputs(stage):
    root, expected = stage
    result = capability.verify(root)
    assert result['status'] == 'verified' and len(result['presets']) == 2
    assert result['runtime_selftest'] == 'pending'
    files = capability._read(root / capability.PATH)['files']
    assert all(capability.is_delivery_path(name) for name in files)
    assert not any('.local' in name or name.endswith('.motion') for name in files)
    assert updater.verify_template_capability(root, expected)['presets'] == result['presets']


@pytest.mark.parametrize('name', [capability.PATH, capability.MANIFEST,
    'Haike_video/backlot/ui/avatar-generator/chunk.js', 'Haike_video/backlot/studio_motion_presets.py',
    'Haike_video/templates/hum-production-v1/quest/Mechanisms.tsx',
    'Haike_video/templates/hum-production-v1/quest/MotionState.ts'])
def test_missing_or_changed_delivery_blocks_success(stage, name):
    root, expected = stage
    path = root / name
    path.write_bytes(path.read_bytes() + b'changed')
    with pytest.raises(ValueError): capability.verify(root)
    with pytest.raises(ValueError): updater.verify_template_capability(root, expected)
    path.unlink()
    with pytest.raises(ValueError): capability.verify(root)
    with pytest.raises(ValueError): updater.verify_template_capability(root, expected)


def test_moving_install_does_not_change_relative_delivery(stage, tmp_path):
    root, expected = stage
    moved = tmp_path / '移动后的 海客'
    root.rename(moved)
    assert capability.verify(moved, expected)['status'] == 'verified'


def test_bluewhite_identity_covers_all_local_imports_of_actual_entry(stage):
    root, _ = stage
    files = capability._read(root / capability.PATH)['files']
    pending = [root / 'Haike_video/templates/hum-production-v1/index.tsx']
    inspected = set()
    while pending:
        path = pending.pop()
        if path in inspected: continue
        inspected.add(path)
        assert path.relative_to(root).as_posix() in files
        if path.suffix == '.json': continue
        imports = re.findall(r"""from\s+['"](\.[^'"]+)['"]""", path.read_text(encoding='utf-8'))
        for local in imports:
            target = path.parent / local
            choices = [target, *(Path(str(target) + suffix) for suffix in ['.ts', '.tsx', '.json'])]
            resolved = next((p.resolve() for p in choices if p.is_file()), None)
            assert resolved is not None, f'missing actual import: {local} in {path.name}'
            pending.append(resolved)


def test_old_install_without_this_feature_keeps_old_update_contract(tmp_path):
    (tmp_path / 'RELEASE.json').write_text('{}', encoding='utf-8')
    assert capability.verify(tmp_path)['status'] == 'not-declared'
    assert updater.verify_template_capability(tmp_path)['status'] == 'not-declared'
    with pytest.raises(ValueError, match='缺少本次模板能力'):
        updater.verify_template_capability(tmp_path, required={'schema': 'haike.motion-capability/1'})


def test_same_version_with_missing_capability_is_not_reported_current(stage):
    root, expected = stage
    asset = {'url': 'https://github.com/hrbj18/haike-workflow/releases/download/v1.2.2/program.zip',
             'size': 100, 'sha256': 'a' * 64}
    feed = {'schema': 1, 'edition': 'haike-workflow-2', 'channel': 'stable', 'version': '1.2.2',
            'template_capability': expected,
            'bootstrap': {'base_source_commit': updater.BASE_SOURCE, 'program': asset, 'resources': asset}}
    def remote(*_): return io.BytesIO(json.dumps(feed).encode())
    with patch.object(updater, 'supported', return_value=True), patch.object(updater, 'remote', side_effect=remote), \
         patch.object(updater, 'confirm_template_runtime', side_effect=lambda root, delivery: delivery):
        assert updater.run('https://github.com/hrbj18/haike-workflow', root)['template_delivery']['status'] == 'verified'
        (root / 'Haike_video/backlot/ui/avatar-generator/chunk.js').unlink()
        with pytest.raises(ValueError, match='模板文件缺失'):
            updater.run('https://github.com/hrbj18/haike-workflow', root)


def test_capability_disallows_private_paths_and_duplicate_presets(stage):
    root, expected = stage
    changed = deepcopy(expected); changed['presets'].append(changed['presets'][0])
    with pytest.raises(ValueError): capability.validate_expectation(changed)
    with pytest.raises(ValueError): updater.validate_template_capability(changed)
    value = capability._read(root / capability.PATH)
    value['files']['.local/private.json'] = 'a' * 64
    value['sha256'] = capability._fingerprint(value['files'])
    (root / capability.PATH).write_bytes(core.json_bytes(value))
    changed = capability.expectation(value, core.digest(root / capability.PATH))
    with pytest.raises(ValueError, match='路径'):
        capability.verify(root, changed)
    with pytest.raises(ValueError, match='路径'):
        updater.verify_template_capability(root, changed)


def test_template_health_failure_rolls_back_program_and_release(tmp_path, stage):
    spec = importlib.util.spec_from_file_location('template_update_fixture', ROOT / 'tests/test_app_update.py')
    fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
    case = fixture.AppUpdateTests()
    root, bundle, original, plan = case.fixture(tmp_path / 'transaction')
    update = fixture.update
    plan['template_capability'] = stage[1]
    (bundle / 'UPDATE-MANIFEST.json').write_bytes(update.json_bytes(plan))
    before = (root / 'RELEASE.json').read_bytes()
    server_before = (root / 'Haike_video/backlot/server.py').read_bytes()
    with pytest.raises(ValueError, match='模板交付清单'):
        update.apply_update(bundle, root, health_check=lambda target, _: capability.verify(target))
    assert (root / 'RELEASE.json').read_bytes() == before
    assert (root / 'Haike_video/backlot/server.py').read_bytes() == server_before


def test_bootstrap_allows_only_the_two_declared_helper_versions():
    import sys
    with patch.dict(sys.modules, {'release_core': core}):
        spec = importlib.util.spec_from_file_location('template_bootstrap', ROOT / 'portable/legacy_upgrade.py')
        bootstrap = importlib.util.module_from_spec(spec); spec.loader.exec_module(bootstrap)
    assert bootstrap.allowed('.local/motiongit/tools/1.0.0-rc.54/motion.mjs', resource=True)
    assert bootstrap.allowed('.local/motiongit/tools/1.0.0-rc.50/motion.mjs', resource=True)
    assert not bootstrap.allowed('.local/motiongit/tools/unknown/motion.mjs', resource=True)
