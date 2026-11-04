"""Complete declared runtime closure, without accepting account or user data."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
_previous_path = list(sys.path)
sys.path.insert(0, str(ROOT/'portable'))
import app_update as core
import legacy_upgrade as legacy
sys.path[:] = _previous_path
spec = importlib.util.spec_from_file_location('closure_online_test', ROOT/'scripts/update-from-github.py')
online = importlib.util.module_from_spec(spec); spec.loader.exec_module(online)


class UpgradeClosurePolicyTests(unittest.TestCase):
    def test_actual_required_public_program_types(self):
        for name in ['Haike_video/LICENSE', 'Haike_video/requirements.txt',
            'Haike_video/schemas/__init__.py', 'Haike_video/schemas/artifacts/__init__.py',
            'Haike_video/styles/playbook_loader.py',
            'Haike_video/templates/motiongit-public-components-v1/upstream/package-lock.json',
            'Haike_video/templates/motiongit-public-components-v1/upstream/scripts/face_track.sh',
            'Haike_video/templates/motiongit-public-components-v1/upstream/scripts/face_track.swift']:
            self.assertTrue(core.is_program_path(name), name)

    def test_actual_closed_runtime_paths_and_private_neighbors(self):
        for name in ['runtime/python/Lib/pathlib.py', 'runtime/python/DLLs/_sqlite3.pyd',
            'runtime/node/node_modules/npm/lib/npm.js', 'runtime/browser/locales/zh-CN.pak',
            'runtime/motion-public/dark/node_modules/remotion/dist/index.js',
            'runtime/motion-public/html/node_modules/playwright-core/package.json',
            'Haike_video/.venv/Lib/site-packages/PIL/Image.py',
            'runtime/python/Lib/site-packages/scipy/__init__.py',
            'Haike_video/templates/knowledge-reference-public-v3/public/fonts/LongCang.ttf']:
            self.assertTrue(legacy.allowed(name, True), name)
        for name in ['Haike_video/config.yaml', 'creatorhub/config.yaml',
            'Haike_video/projects/final.mp4', '.local/account.json',
            'runtime/browser/profile/Default/Cookies', 'runtime/python/.env',
            'Haike_video/.venv/Lib/site-packages/private-account.json']:
            self.assertFalse(legacy.allowed(name, True), name)
        for name in legacy.APPROVED_DESIGN_COVERS:
            self.assertTrue(legacy.allowed(name, True), name)
        self.assertFalse(legacy.allowed('Haike_video/templates/library-covers/private.png', True))

    def test_real_closure_sizes_remain_bounded(self):
        self.assertGreater(getattr(online, 'MAX_PROGRAM_EXPANDED_BYTES', 100_000_000), 118_122_337)
        self.assertGreaterEqual(getattr(legacy, 'MAX_RESOURCE_FILES', 30000), 44394)
        self.assertGreater(getattr(legacy, 'MAX_INSTALL_EXPANDED_BYTES', 2_000_000_000), 2_295_867_504)

    def test_dependency_change_still_requires_full_transaction(self):
        # Classification for the complete installer does not silently make a
        # normal same-runtime program patch into a dependency migration.
        self.assertTrue(core.is_program_path('Haike_video/requirements.txt'))
        self.assertTrue(core.is_dependency_path('Haike_video/requirements.txt'))
        plan = {'schema':1, 'edition':core.EDITION, 'platform':core.PLATFORM,
            'version':'1.2.3', 'base_version':'1.2.2', 'runtime_id':core.RUNTIME_ID, 'data_schema':1,
            'files':[{'path':'Haike_video/requirements.txt','size':3,'sha256':'a'*64}], 'required_locks':[]}
        with self.assertRaisesRegex(core.UpdateError, '普通程序补丁不能迁移依赖'):
            core._plan(plan)

    def test_closed_resource_requires_exact_program_manifest_and_digest(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle = Path(folder)
            resource = {'path':'runtime/python/Lib/pathlib.py','size':3,'sha256':'a'*64}
            closure = {'schema':'haike.motion-upgrade-closure/1', 'preferred_sha256':'b'*64,
                       'resources':{resource['path']:{'size':3,'sha256':'a'*64}}}
            file = bundle/'closure.json'; file.write_text(json.dumps(closure))
            digest = core.digest(file)
            plan = {'files':[{'path':legacy.CLOSURE_PATH,'payload':'closure.json','sha256':digest}]}
            resources = {'files':[resource],'component_manifest_sha256':digest,'preferred_sha256':'b'*64}
            legacy.verify_declared_closure(bundle, plan, resources)
            cover, digest_cover = next(iter(legacy.APPROVED_DESIGN_COVERS.items()))
            resources['files'] = [resource, {'path':cover, 'sha256':digest_cover, 'size':123}]
            legacy.verify_declared_closure(bundle, plan, resources)
            resources['files'][-1]['sha256'] = '0'*64
            with self.assertRaisesRegex(ValueError, '设计封面的SHA改变'):
                legacy.verify_declared_closure(bundle, plan, resources)
            resources['files'] = [{**resource,'sha256':'c'*64}]
            with self.assertRaisesRegex(ValueError, 'SHA改变'):
                legacy.verify_declared_closure(bundle, plan, resources)
            resources['component_manifest_sha256'] = 'd'*64
            with self.assertRaisesRegex(ValueError, '闭包SHA'):
                legacy.verify_declared_closure(bundle, plan, resources)


if __name__ == '__main__':
    unittest.main()
