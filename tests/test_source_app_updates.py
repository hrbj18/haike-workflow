"""Source installs must discover main independently from portable Releases."""
import io
import json
import tempfile
import unittest
import subprocess
import os
import socket
import sqlite3
import sys
import time
from contextlib import closing
from urllib.parse import urlsplit
from pathlib import Path
from unittest.mock import patch, Mock

from portable import (app_update as core, update_service as service,
                      source_app_update as source, source_update_worker as source_worker, update_worker as worker)

SERVER = '''import http.server,json,os,sys,uuid,subprocess,socketserver
from pathlib import Path
root=Path.cwd().parent.resolve(); instance=uuid.uuid4().hex
if (root/'fail-start').exists(): raise SystemExit(3)
class LoopbackServer(http.server.HTTPServer):
 def server_bind(self):
  socketserver.TCPServer.server_bind(self)
  self.server_name='localhost';self.server_port=self.server_address[1]
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_GET(self):
  release=json.loads((root/'VERSION.json').read_text())
  if self.path=='/api/health': value={'ok':True,'edition':'haike-workflow-2','workspace':str(root),'pid':os.getpid(),'instance_id':instance,'version':release['version'],'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()}
  elif self.path=='/api/studio/app-update/readiness': value={'ready':True}
  elif self.path=='/api/studio/templates': value={'templates':[]}
  else:
   self.send_response(200);self.end_headers();self.wfile.write(b'<html>synthetic UI</html>');return
  self.send_response(200);self.end_headers();self.wfile.write(json.dumps(value).encode())
LoopbackServer(('127.0.0.1',int(sys.argv[-1])),Handler).serve_forever()
'''

PUBLISHER = '''import hashlib,http.server,json,os,sys,uuid,socketserver
from pathlib import Path
module=Path.cwd().resolve(); instance=uuid.uuid4().hex
build=(module/'version.txt').read_text()
fingerprint=hashlib.sha256(str(module).replace(chr(92),'/').casefold().encode()).hexdigest()
class LoopbackServer(http.server.HTTPServer):
 def server_bind(self):
  socketserver.TCPServer.server_bind(self)
  self.server_name='localhost';self.server_port=self.server_address[1]
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_GET(self):
  value={'status':'ok','pid':os.getpid(),'instance_id':instance,'service_fingerprint':fingerprint,'update_inflight':0,'build':build}
  self.send_response(200);self.end_headers();self.wfile.write(json.dumps(value).encode())
LoopbackServer(('127.0.0.1',int(sys.argv[-1])),Handler).serve_forever()
'''


class SourceDiscoveryTests(unittest.TestCase):
    def test_same_version_new_main_commit_is_an_available_source_update(self):
        old, new = 'a' * 40, 'b' * 40
        current = dict(version='1.2.3', source_commit=old, package_type='source',
                       development=True, dirty=False, edition='haike-workflow-2')
        urls = []

        def response(url, **kwargs):
            urls.append(url)
            if url.endswith('/commits/main'):
                value = dict(sha=new, commit=dict(message='Checked source update',
                             committer=dict(date='2026-11-06T00:00:00Z')))
            elif url.endswith('/VERSION.json'):
                value = dict(version='1.2.3', edition='haike-workflow-2', data_schema=1)
            else:
                raise AssertionError('Source discovery must not require a Release package: ' + url)
            return io.BytesIO(json.dumps(value).encode())

        with tempfile.TemporaryDirectory() as folder, \
             patch.object(service, 'current_release', return_value=current), \
             patch.object(service, 'remote_open', side_effect=response):
            snapshot = service.UpdateService(Path(folder)).check()
        self.assertEqual(snapshot['update']['status'], 'available')
        self.assertEqual(snapshot['update']['source_commit'], new)
        self.assertEqual(snapshot['update']['channel'], 'main')
        self.assertFalse(any('/releases/' in url for url in urls))

    def test_offline_source_never_reports_latest(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(service, 'current_release', return_value=dict(package_type='source', source_commit='a'*40)), \
             patch.object(service, 'remote_open', side_effect=OSError('offline')):
            self.assertEqual(service.UpdateService(folder).check()['update']['status'], 'unavailable')


@unittest.skipUnless(sys.platform in {'win32', 'darwin'}, 'Windows / Mac desktop update transaction')
class SourceTransactionTests(unittest.TestCase):
    def fixture(self, root, failure=None, publisher=False):
        root = Path(root)
        source.git(root, 'init', '-b', 'main')
        source.git(root, 'config', 'user.email', 'fixture@example.test')
        source.git(root, 'config', 'user.name', 'Fixture')
        source.git(root, 'remote', 'add', 'origin', source.REPOSITORY)
        ignore = (Path(__file__).resolve().parents[1] / '.gitignore').read_text(encoding='utf-8')
        (root / '.gitignore').write_text(ignore + '\n*.env\n', encoding='utf-8')
        (root / 'VERSION.json').write_text(json.dumps(dict(version='1.2.3', edition=core.EDITION, data_schema=1)))
        backlot = root / 'Haike_video/backlot'
        backlot.mkdir(parents=True)
        (backlot / '__init__.py').touch()
        (backlot / '__main__.py').write_text(SERVER)
        scripts = root / 'scripts'
        scripts.mkdir()
        (scripts / 'update-source-dependencies.py').write_text('print("synthetic dependency refresh")\n')
        (root / 'program.txt').write_text('old')
        if publisher:
            module = root / 'creatorhub'
            module.mkdir()
            (module / 'uvicorn.py').write_text(PUBLISHER)
            (module / 'version.txt').write_text('old')
            subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(module / '.venv')], check=True, timeout=60)
        source.git(root, 'add', '.')
        source.git(root, 'commit', '-m', 'old source')
        old = source.git(root, 'rev-parse', 'HEAD').stdout.strip()
        (root / 'program.txt').write_text('new')
        if publisher:
            (root / 'creatorhub/version.txt').write_text('new')
        if failure == 'start':
            (root / 'fail-start').touch()
        elif failure == 'dependencies':
            (scripts / 'update-source-dependencies.py').write_text('raise SystemExit(2)\n')
        source.git(root, 'add', '.')
        source.git(root, 'commit', '-m', 'new source same version')
        new = source.git(root, 'rev-parse', 'HEAD').stdout.strip()
        source.switch(root, old)
        private = root / 'Haike_video/.backlot'
        private.mkdir()
        with closing(sqlite3.connect(private / 'studio.sqlite3')) as db:
            db.execute('create table drafts (id text primary key, value text)')
            db.execute('insert into drafts values (?,?)', ('original', 'keep this draft'))
            db.commit()
        media = root / 'Haike_video/projects/existing.mp4'
        media.parent.mkdir()
        media.write_bytes(b'original paid movie' * 1000)
        (media.parent / 'draft.json').write_text('{"asset_path":"' + str(media).replace('\\', '/') + '"}')
        (root / 'private.env').write_text('SYNTHETIC_FIXTURE=kept')
        candidate = dict(kind='source', repository=source.REPOSITORY, base_commit=old, source_commit=new,
                         version='1.2.3', edition=core.EDITION, data_schema=1)
        return old, new, media, candidate

    def command(self, root, candidate, base, health):
        identity = 'a' * 24
        service.write_json(service.private_path(root), dict(
            operation=dict(id=identity, status='downloading', target_version='1.2.3',
                           target_commit=candidate['source_commit'], updated_at=service.utcnow())))
        service.write_json(service.private_path(root, identity + '/operation.json'), dict(
            id=identity, candidate=candidate, base_url=base, instance_id=health['instance_id'],
            server_pid=health['pid'], token='synthetic-private-token'))
        return identity

    def run_case(self, failure=None, publisher=False):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old, new, media, candidate = self.fixture(root, failure, publisher)
            media_stat = media.stat()
            media_hash = core.digest(media)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            base = 'http://127.0.0.1:' + str(port)
            publisher_base = None
            publisher_child = None
            if publisher:
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1', 0))
                    publisher_base = 'http://127.0.0.1:' + str(sock.getsockname()[1])
                publisher_child, original_publisher = source_worker.start_publisher(root, publisher_base)
            child = worker.start_server(root, port)
            try:
                health = worker.wait_server(base, root, child, '1.2.3', timeout=15, source_commit=old)
                if publisher and sys.platform == 'darwin':
                    service.write_json(root / '.local/mac-services.json', dict(root=str(root.resolve()),
                        studio_port=port, publisher_port=urlsplit(publisher_base).port, pids=[original_publisher['pid'], health['pid']]))
                identity = self.command(root, candidate, base, health)
                original_git = source.git
                fetches = []

                def controlled_git(where, *args, **kwargs):
                    if args[0] == 'fetch':
                        fetches.append(args)
                        self.assertEqual(args[-2:], (source.REPOSITORY, new))
                        original_git(where, 'fetch', '--no-tags', '.', new)
                        return subprocess.CompletedProcess(args, 0, '', '')
                    return original_git(where, *args, **kwargs)

                ci = dict(workflow_runs=[dict(id=1, head_sha=new, head_branch='main',
                                             event='push', conclusion='success')])
                with patch.object(source, 'git', side_effect=controlled_git), \
                     patch.object(source_worker, 'remote_open', side_effect=lambda *a, **k: io.BytesIO(json.dumps(ci).encode())), \
                     patch.dict(os.environ, {'HAIKE_CREATORHUB_URL': publisher_base} if publisher else {}):
                    source_worker.run_source_update(root, identity)
                snapshot = service.UpdateService(root).snapshot()
                expected = old if failure else new
                self.assertEqual(snapshot['operation']['status'], 'rolled_back' if failure else 'complete')
                self.assertEqual(source.git(root, 'rev-parse', 'HEAD').stdout.strip(), expected)
                self.assertEqual(worker.local_get(base, '/api/health')['source_commit'], expected)
                self.assertEqual((root / 'program.txt').read_text(), 'old' if failure else 'new')
                self.assertEqual(media_hash, core.digest(media))
                self.assertEqual(media_stat.st_mtime_ns, media.stat().st_mtime_ns)
                with closing(sqlite3.connect(root / 'Haike_video/.backlot/studio.sqlite3')) as db:
                    self.assertEqual(db.execute('select value from drafts').fetchone()[0], 'keep this draft')
                backup = service.private_path(root, identity + '/receipt.json').parent
                self.assertFalse(list(backup.rglob('*.mp4')))
                with closing(sqlite3.connect(backup / 'metadata/Haike_video/.backlot/studio.sqlite3')) as db:
                    self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual((root / 'private.env').read_text(), 'SYNTHETIC_FIXTURE=kept')
                self.assertEqual(source.git(root, 'status', '--porcelain').stdout.strip(), '')
                self.assertTrue(fetches)
                if publisher:
                    health = source_worker.publisher_identity(root, publisher_base)
                    self.assertEqual(health['build'], 'old' if failure else 'new')
                    self.assertNotEqual(health['instance_id'], original_publisher['instance_id'])
                    if sys.platform == 'darwin':
                        actual = service.read_json(root / '.local/mac-services.json')
                        self.assertEqual(actual['pids'], [health['pid'], worker.local_get(base, '/api/health')['pid']])
            finally:
                try:
                    health = worker.local_get(base, '/api/health')
                    worker.stop_verified(base, root, health['instance_id'], health['pid'])
                except (OSError, ValueError):
                    pass
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=10)
                if publisher_base:
                    try:
                        health = source_worker.publisher_identity(root, publisher_base)
                        source_worker.stop_publisher(root, publisher_base, health)
                    except (OSError, ValueError):
                        pass
                if publisher_child and publisher_child.poll() is None:
                    publisher_child.terminate()
                    publisher_child.wait(timeout=10)

    def test_real_git_switch_restart_and_metadata_preservation(self):
        self.run_case()

    def test_boot_health_identity_reports_same_version_and_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old, new, media, candidate = self.fixture(root)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            base = 'http://127.0.0.1:' + str(port)
            child = worker.start_server(root, port)
            try:
                try:
                    worker.wait_server(base, root, child, '1.2.3', timeout=5, source_commit=old)
                except Exception as error:
                    import http.client
                    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
                    try:
                        connection.request('GET', '/api/health')
                        direct = connection.getresponse().read().decode()
                    except Exception as detail:
                        direct = repr(detail)
                    finally:
                        connection.close()
                    try:
                        health = worker.local_get(base, '/api/health')
                    except Exception as detail:
                        health = repr(detail)
                    log = service.private_path(root, 'restart.log').read_text(encoding='utf-8', errors='replace')[-2000:]
                    self.fail(f'{error}; root={root.resolve()}; python={sys.executable}; child={child.poll()}; direct={direct}; health={health}; log={log}')
            finally:
                try:
                    health = worker.local_get(base, '/api/health')
                    worker.stop_verified(base, root, health['instance_id'], health['pid'])
                except (OSError, ValueError):
                    pass
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=10)

    def test_derived_mac_fonts_keep_install_clean_without_hiding_custom_source(self):
        with tempfile.TemporaryDirectory() as folder:
            self.fixture(folder)
            fonts = Path(folder) / '_distribution-tools/motion-html/fonts'
            fonts.mkdir(parents=True)
            for name in ('NotoSansSC.ttf', 'NotoSansMono.ttf', 'notosansmono-OFL.txt', 'notosanssc-OFL.txt'):
                (fonts / name).write_text('synthetic generated font')
            self.assertTrue(source.inspect(folder)['can_install'])
            (fonts / 'user-custom-font.ttf').write_text('user-owned addition')
            self.assertFalse(source.inspect(folder)['can_install'])

    def test_failed_new_server_rolls_back_and_restarts_old_commit(self):
        self.run_case('start')

    def test_failed_dependency_install_rolls_back_and_restarts_old_commit(self):
        self.run_case('dependencies')

    def test_changed_publisher_is_restarted_with_the_same_workbench(self):
        self.run_case(publisher=True)

    def test_failed_workbench_restores_and_restarts_both_owned_services(self):
        self.run_case('start', publisher=True)

    def test_same_workspace_old_instance_cannot_confirm_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            health = dict(ok=True, edition=core.EDITION, workspace=folder, version='1.2.3',
                          source_commit='a'*40, instance_id='old')
            child = Mock()
            child.poll.return_value = 1
            with patch.object(worker, 'verify_templates', return_value={}), \
                 patch.object(worker, 'local_get', return_value=health), \
                 self.assertRaises(core.UpdateError):
                worker.wait_server('http://127.0.0.1:1234', folder, child, '1.2.3',
                                   source_commit='a'*40, previous_instance='old')

    def test_cleanup_can_stop_the_owned_venv_launcher_tree_without_health(self):
        with tempfile.TemporaryDirectory() as folder:
            self.fixture(folder)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            base = 'http://127.0.0.1:' + str(port)
            child = worker.start_server(Path(folder), port)
            try:
                health = worker.wait_server(base, folder, child, '1.2.3', timeout=10)
                with patch.object(worker, 'local_get', side_effect=OSError('unresponsive')):
                    worker.terminate_started(child)
                self.assertFalse(service.process_alive(health['pid']))
            finally:
                worker.terminate_started(child)
                # Windows tree termination may finish the launcher before the
                # child's pending file handles close. Do not race temp cleanup.
                if os.name == 'nt':
                    log = service.private_path(folder, 'restart.log')
                    deadline = time.monotonic() + 3
                    while log.exists():
                        try:
                            log.unlink()
                        except PermissionError:
                            if time.monotonic() >= deadline:
                                raise
                            time.sleep(.05)

    def test_dirty_index_is_preserved_and_blocks_install(self):
        with tempfile.TemporaryDirectory() as folder:
            old, new, media, candidate = self.fixture(folder)
            root = Path(folder)
            (root / 'program.txt').write_text('staged user change')
            source.git(root, 'add', 'program.txt')
            (root / 'program.txt').write_text('unstaged user change')
            before = (source.git(root, 'diff').stdout, source.git(root, 'diff', '--cached').stdout,
                      (root / '.git/index').read_bytes())
            self.assertFalse(source.inspect(root)['can_install'])
            after = (source.git(root, 'diff').stdout, source.git(root, 'diff', '--cached').stdout,
                     (root / '.git/index').read_bytes())
            self.assertEqual(before, after)

    def test_unpassed_main_ci_cannot_change_program(self):
        with tempfile.TemporaryDirectory() as folder:
            old, new, media, candidate = self.fixture(folder)
            with self.assertRaisesRegex(core.UpdateError, '检查尚未通过'), \
                 patch.object(source, 'remote_json', return_value=dict(workflow_runs=[])):
                source.prepare(folder, candidate, lambda url: None)
            self.assertEqual(source.git(folder, 'rev-parse', 'HEAD').stdout.strip(), old)

    def test_install_binds_confirmation_to_commit_not_just_version(self):
        with tempfile.TemporaryDirectory() as folder:
            old, new, media, candidate = self.fixture(folder)
            updater = service.UpdateService(folder)
            service.write_json(service.private_path(folder), dict(update=dict(
                source='main', status='available', version='1.2.3', source_commit=new, candidate=candidate)))
            with self.assertRaisesRegex(core.UpdateError, '目标源码提交已变化'):
                updater.install('1.2.3', 'http://127.0.0.1:1234', 'instance', 1234, True,
                                launch=False, source_commit='0'*40)
            snapshot = updater.install('1.2.3', 'http://127.0.0.1:1234', 'instance', 1234, True,
                                       launch=False, source_commit=new)
            self.assertEqual(snapshot['operation']['target_commit'], new)
            self.assertNotIn('token', json.dumps(snapshot))

    def test_source_version_ignores_stale_portable_release_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            old, new, media, candidate = self.fixture(folder)
            (Path(folder) / 'RELEASE.json').write_text('{"version":"1.0.0"}')
            self.assertEqual(service.current_release(folder)['version'], '1.2.3')

    def test_external_git_switch_cannot_report_new_code_as_running(self):
        with tempfile.TemporaryDirectory() as folder:
            old, new, media, candidate = self.fixture(folder)
            updater = service.UpdateService(folder, running_release=dict(version='1.2.3', source_commit=old))
            source.switch(folder, new)
            with patch.object(service, 'remote_open') as remote:
                snapshot = updater.check()
            remote.assert_not_called()
            self.assertEqual(snapshot['update']['status'], 'restart-required')
            self.assertFalse(snapshot['capability']['can_install'])
            self.assertEqual(snapshot['current']['source_commit'], old)
            self.assertEqual(snapshot['current']['installed_source_commit'], new)
            self.assertEqual((Path(folder) / 'program.txt').read_text(), 'new')

    def test_other_publisher_identity_cannot_be_stopped(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(worker, 'local_get', return_value=dict(status='ok', pid=1234,
                          instance_id='foreign', service_fingerprint='foreign')), \
             patch.object(source_worker.os, 'kill') as kill:
            with self.assertRaises(core.UpdateError):
                source_worker.stop_publisher(folder, 'http://127.0.0.1:1234', {})
            kill.assert_not_called()


if __name__ == '__main__':
    unittest.main()
