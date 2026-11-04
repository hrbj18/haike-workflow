"""Isolated real download/filesystem/Git tests; no installed service is started."""
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import shutil
import threading
import unittest
import zipfile
from unittest.mock import patch
from urllib import parse, request

from portable import unified_upgrade as unified


@contextmanager
def release_server(payloads):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(self.path)
            data = payloads.get(self.path)
            self.send_response(200 if data is not None else 404)
            self.end_headers()
            if data is not None:
                self.wfile.write(data)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:'+str(server.server_port), calls
    finally:
        server.shutdown(); server.server_close(); thread.join(5)


class UnifiedUpgradeTests(unittest.TestCase):
    def portable(self, root, version=None, source=None):
        (root/'Haike_video/backlot').mkdir(parents=True)
        (root/'Haike_video/backlot/server.py').write_text('# app', 'utf8')
        (root/'PACKAGE-MANIFEST.json').write_text('{"schema":1,"files":[]}', 'utf8')
        data = {'edition': 'haike-workflow-2', 'source_commit': source or 'a'*40}
        if version:
            data['version'] = version
        (root/'RELEASE.json').write_text(json.dumps(data), 'utf8')

    def feed(self):
        u = unified.online()
        asset = {'url': unified.OFFICIAL+'/releases/download/v1.2.2/resource.zip', 'size': 2, 'sha256': 'a'*64}
        return {'schema': 1, 'edition': 'haike-workflow-2', 'channel': 'stable', 'version': '1.2.2',
            'source_commit': 'b'*40, 'bootstrap': {'base_source_commit': u.BASE_SOURCE, 'program': dict(asset), 'resources': dict(asset)}}

    def test_bounded_nested_family_and_fixed_routes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'Haike_videoflow'/'haike_videoflow'
            self.portable(root, source=unified.online().BASE_SOURCE)
            self.assertEqual(unified.plan(folder, feed=self.feed())['route'], '1027-transaction')
            data = json.loads((root/'RELEASE.json').read_text())
            data.update(version='1.2.1', source_commit='c'*40)
            (root/'RELEASE.json').write_text(json.dumps(data))
            self.assertEqual(unified.plan(root, feed=self.feed())['route'], 'application-api')
            feed = self.feed(); feed['bootstrap']['modern_bases'] = [{'version':'1.2.1','source_commit':'c'*40}]
            self.assertEqual(unified.plan(root, feed=feed)['route'], 'migration-transaction')
            feed['bootstrap']['project_compatibility'] = {'schema':1,'edition':'haike-workflow-2','platform':'windows-x64','data_schema':1}
            data['source_commit'] = 'd'*40; (root/'RELEASE.json').write_text(json.dumps(data))
            self.assertEqual(unified.plan(root, feed=feed)['route'], 'project-transaction')
            with self.assertRaises(ValueError):
                unified.plan(root, 'https://github.com/not/official')

    def test_compatibility_never_overwrites_user_program_or_cache(self):
        u = unified.online()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); p = root/'Haike_video/backlot/app.py'; p.parent.mkdir(parents=True)
            p.write_bytes(b'original')
            (root/'PACKAGE-MANIFEST.json').write_text(json.dumps({'files':[{'path':p.relative_to(root).as_posix(),'sha256':u.sha(p)}]}))
            row = {'path':p.relative_to(root).as_posix(),'sha256':hashlib.sha256(b'new').hexdigest()}
            u.verify_installed_program(root, {'files':[row]})
            p.write_bytes(b'user edit')
            with self.assertRaisesRegex(ValueError, '用户修改'):
                u.verify_installed_program(root, {'files':[row]})
            with self.assertRaisesRegex(ValueError, '用户修改'):
                u.verify_installed_program(root, {'files':[]}, [row])
            self.assertEqual(p.read_bytes(), b'user edit')

    def test_real_candidate_two_archives_download_install_repeat_and_rollback(self):
        from test_legacy_upgrade import LegacyUpgradeTests
        fixture = LegacyUpgradeTests()
        fixture.setUp()
        try:
            root, bundle = fixture.target, fixture.bundle
            u = unified.online()
            (root/'UNIFIED-UPGRADE-SANDBOX.json').write_text(json.dumps({'schema':1,'isolated_target':str(root.resolve())}))
            code_root = Path(__file__).resolve().parents[1]
            for name, source in {'legacy_upgrade.py':'portable/legacy_upgrade.py', 'release_core.py':'portable/app_update.py',
                                 'audio_update_guard.py':'portable/audio_update_guard.py', 'motion_runtime.py':'portable/motion_runtime.py',
                                 'queue_update_guard.py':'portable/queue_update_guard.py',
                                 'update_dependencies.py':'portable/update_dependencies.py',
                                 'dependency-downloads.json':'portable/dependency-downloads.json'}.items():
                (bundle/name).write_bytes((code_root/source).read_bytes())
            program = fixture.root/'candidate-program.zip'
            with zipfile.ZipFile(program,'w',compression=zipfile.ZIP_DEFLATED) as z:
                for p in bundle.rglob('*'):
                    if p.is_file(): z.write(p,'haike-update-1.2/'+p.relative_to(bundle).as_posix())
            feed = self.feed(); feed['version'] = fixture.plan['release']['version']
            feed['candidate_only'] = True
            feed['candidate_provenance'] = {'tree_sha256':hashlib.sha256(program.read_bytes()).hexdigest(),
                                            'base_git_commit':'a'*40, 'scope':'synthetic isolated source fixture'}
            payloads = {}
            for key,p in [('program',program),('resources',fixture.resource)]:
                url = unified.OFFICIAL+'/releases/download/v'+feed['version']+'/'+p.name
                feed['bootstrap'][key] = {'url':url,'size':p.stat().st_size,'sha256':u.sha(p)}
                payloads[parse.urlsplit(url).path] = p.read_bytes()
            feed_path = fixture.root/'candidate.json'; feed_path.write_text(json.dumps(feed))
            private = [root/'Haike_video/config.local.yaml',root/'Haike_video/projects/user-work.txt']
            before = {str(p):p.read_bytes() for p in private}
            program_before = (root/'Haike_video/backlot/legacy_test.py').read_bytes()
            healthy = lambda _: {'ok':True,'templates':[], 'scope':'explicit isolated health seam, no service or media'}
            with release_server(payloads) as (server,calls):
                result = unified.apply_candidate(root,feed_path,test_release_base=server,health_check=healthy)
                self.assertTrue(result['ok']); self.assertTrue(result['candidate_only']); self.assertFalse(result['published'])
                backup = result['backup']
                self.assertEqual((root/'Haike_video/backlot/legacy_test.py').read_bytes(),b'new program')
                self.assertTrue(unified.apply_candidate(root,feed_path,test_release_base=server,health_check=healthy)['already_current'])
                self.assertEqual(len(calls),2)  # both SHA-verified cached assets reused
                self.assertTrue(unified.apply_candidate(root,feed_path,test_release_base=server,rollback=backup)['ok'])
            self.assertEqual((root/'Haike_video/backlot/legacy_test.py').read_bytes(),program_before)
            for p in private: self.assertEqual(p.read_bytes(),before[str(p)])
        finally:
            fixture.doCleanups()

    def test_actual_loopback_download_core_transaction_repeat_and_rollback(self):
        # Only the service/worker seam is substituted. HTTP bytes, zip SHA,
        # extraction, preflight, backups, writes and rollback are real.
        from test_app_update import AppUpdateTests, update as core
        helper = AppUpdateTests()
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); root, bundle, original, plan = helper.fixture(base)
            archive = helper.zip_bundle(base, bundle)
            content = archive.read_bytes(); u = unified.online()
            asset = {'url':unified.OFFICIAL+'/releases/download/v1.2.2/program.zip',
                     'size':len(content),'sha256':hashlib.sha256(content).hexdigest()}
            feed = self.feed(); feed['bootstrap']['program'] = asset
            payloads = {'/repos/feed':json.dumps(feed).encode(), '/releases/download/v1.2.2/program.zip':content}
            state = {}
            def apply_existing(url, target, start=True):
                downloaded = u.fetch_asset(root, asset)
                if not state:
                    core.extract_bundle(downloaded, base/'extracted')
                    state['bundle'] = base/'extracted'
                result = core.apply_update(state['bundle'], root)
                state['result'] = result
                return result
            with release_server(payloads) as (server, calls), patch.object(unified, 'online', return_value=u), \
                 patch.object(u, 'remote', side_effect=lambda url, authentication=None: request.urlopen(server+('/repos/feed' if url.endswith('haike-update.json') else '/releases/'+parse.urlsplit(url).path.split('/releases/',1)[1]))), \
                 patch.object(u, 'run', side_effect=apply_existing):
                # This fixture is a historical 1.0 layout; explicit route seam
                # binds to the same old compatible transaction for this test.
                with patch.object(unified, 'plan', return_value={'target':str(root),'route':'application-api','family':'portable'}):
                    done = unified.execute(root)
                    self.assertTrue(done['ok']); backup = done['backup']
                    self.assertTrue(unified.execute(root)['already_current'])
                self.assertEqual(calls.count('/releases/download/v1.2.2/program.zip'), 1)
            self.assertEqual((root/'creatorhub/config.yaml').read_bytes(), original['creatorhub/config.yaml'])
            self.assertEqual((root/'Haike_video/projects/synthetic/renders/final.mp4').read_bytes(), original['Haike_video/projects/synthetic/renders/final.mp4'])
            core.rollback(root, backup); helper.assert_original(root, original)

    def git(self, root, *args):
        r = subprocess.run(['git','-c','core.longpaths=true','-C',str(root),*args],capture_output=True,check=True)
        return r.stdout.decode('utf8').strip()

    def test_real_dirty_git_index_preserved_worktree_and_repeat(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); root = base/'海客 source'; root.mkdir()
            self.git(root,'init'); self.git(root,'config','user.name','Synthetic'); self.git(root,'config','user.email','synthetic@example.invalid')
            (root/'a.txt').write_text('old'); (root/'.gitignore').write_text('.local/\n')
            self.git(root,'add','.'); self.git(root,'commit','-m','old'); old = self.git(root,'rev-parse','HEAD')
            (root/'a.txt').write_text('new'); self.git(root,'commit','-am','new'); new = self.git(root,'rev-parse','HEAD')
            bare = base/'remote.git'; subprocess.run(['git','clone','--bare',str(root),str(bare)],capture_output=True,check=True)
            self.git(root,'checkout','--detach',old)
            self.git(root,'remote','add','origin',unified.OFFICIAL+'.git')
            self.git(root,'config','url.'+bare.as_uri()+'.insteadOf',unified.OFFICIAL+'.git')
            (root/'a.txt').write_text('staged'); self.git(root,'add','a.txt'); (root/'a.txt').write_text('unstaged')
            (root/'untracked.txt').write_text('private untracked'); (root/'.local').mkdir(); (root/'.local/work.mp4').write_bytes(b'private work')
            before = unified.git_snapshot(root)
            feed = self.feed(); feed['source_commit'] = new
            info = unified.plan(root, feed=feed); target = base/'新 candidate'
            result = unified.source_candidate(info, feed, target)
            self.assertEqual(unified.git_snapshot(root), before)
            self.assertEqual((target/'a.txt').read_text(), 'new')
            self.assertTrue(result['original_git_unchanged']); self.assertFalse(result['activated'])
            self.assertTrue(unified.source_candidate(info, feed, target)['already_current_candidate'])
            self.assertEqual((root/'.local/work.mp4').read_bytes(), b'private work')
            (target/'a.txt').write_text('candidate user edit')
            with self.assertRaisesRegex(ValueError, '用户修改'):
                unified.source_candidate(info, feed, target)
            self.assertEqual(unified.git_snapshot(root), before)

    def test_long_program_backup_and_preparation_failure_are_safe(self):
        from test_app_update import AppUpdateTests, update as core
        helper = AppUpdateTests()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            root, bundle, original, plan = helper.fixture(Path(folder))
            name = 'Haike_video/backlot/'+'/'.join(['nested_component']*7)+'/long_program.py'
            old, new = b'old long program', b'new long program'
            core._atomic_write(core.safe_path(root,name),old)
            core._atomic_write(core.safe_path(bundle/'payload',name),new)
            manifest = core._read(root/'PACKAGE-MANIFEST.json'); manifest['files'].append({'path':name,'sha256':hashlib.sha256(old).hexdigest(),'size':len(old),'mutable':False})
            core._atomic_write(root/'PACKAGE-MANIFEST.json',core.json_bytes(manifest))
            plan['files'].append({'path':name,'size':len(new),'sha256':hashlib.sha256(new).hexdigest(),'before_sha256':hashlib.sha256(old).hexdigest()})
            helper.rewrite_plan(bundle,plan)
            done = core.apply_update(bundle,root); backup = Path(done['backup'])
            self.assertGreater(len(str(backup/'files'/name)),259)
            self.assertFalse(str(backup).startswith('\\\\?\\'))
            core.rollback(root,backup); self.assertEqual(core.native_path(root/name).read_bytes(),old)
            real_write = core._atomic_write
            def fail_backup(path, content):
                if 'files' in Path(path).parts:
                    raise OSError('synthetic backup failure')
                return real_write(path,content)
            with patch.object(core,'_atomic_write',side_effect=fail_backup):
                with self.assertRaises(OSError): core.apply_update(bundle,root)
            receipts = [core._read(p) for p in (root/'.local/app-updates').glob('*/receipt.json')]
            failed = next(r for r in receipts if r['status']=='preparation_failed')
            self.assertFalse(failed['backup_complete']); self.assertFalse(failed['program_changes_started'])
            self.assertEqual(core.pending_receipts(root),[])
            self.assertEqual((root/'Haike_video/backlot/server.py').read_bytes(),original['Haike_video/backlot/server.py'])
            # Explicit native cleanup of this exact owned temp root; Python's
            # ordinary cleanup otherwise cannot remove >MAX_PATH backup files.
            temp_root = Path(folder).resolve()
            self.assertEqual(temp_root.parent, Path(tempfile.gettempdir()).resolve())
            shutil.rmtree(core.native_path(temp_root))

    def test_public_config_exceptions_are_finite_and_schema_checked(self):
        from test_app_update import update as core
        self.assertTrue(core.is_program_path(core.PREFERRED_ROUTE))
        self.assertTrue(core.is_program_path('Haike_video/config/motion-replay/imported-public-v2-bound.json'))
        for name in ['Haike_video/config/private.json','Haike_video/config/motion-replay/private.json',
                     'Haike_video/config/motion-replay/../account.json']:
            self.assertFalse(core.is_program_path(name))
        with self.assertRaises(core.UpdateError):
            core.validate_public_route(core.PREFERRED_ROUTE,b'{"schema":"account","templates":[]}')
        core.validate_public_route(core.PREFERRED_ROUTE,json.dumps({'schema':'haike.motion-preferred-production/1',
            'templates':[{'template_id':'kinetic-field-v1','version':'2.0.0','production_contract':'fixed-route'}]}).encode())


if __name__ == '__main__':
    unittest.main()
