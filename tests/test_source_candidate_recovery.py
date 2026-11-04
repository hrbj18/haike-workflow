"""Isolated recovery: real ZIP bodies, SQLite catalogs and dirty Git index.

Python callbacks below are explicit orchestration seams, not runtime acceptance.
No callback result is evidence that the 18 component hooks or target ABI ran.
"""
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Haike_video'))
from portable import source_candidate_recovery as recovery
from backlot.studio import Studio
from backlot.work_catalog import WorkCatalog


def put(root,name,data):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(data if isinstance(data,bytes) else data.encode())
    return p


def sha(data):return hashlib.sha256(data).hexdigest()


def fixture(root):
    source=root/'old';target=root/'new';source.mkdir();target.mkdir()
    code=put(target,'app.py','print("new source")\n')
    body=b'actual immutable test runtime body\n'
    name='runtime/node/LICENSE'
    closure={'schema':'haike.motion-upgrade-closure/1','preferred_sha256':'a'*64,
        'files':{'app.py':{'size':code.stat().st_size,'sha256':recovery.core.digest(code)}},
        'resources':{name:{'size':len(body),'sha256':sha(body)}}}
    closure_path=put(target,recovery.CLOSURE,json.dumps(closure))
    closure_sha=recovery.core.digest(closure_path)
    declaration={'schema':'haike.complete-resource-recovery/1','kind':'content-addressed-resource-bodies',
        'baseline_dependency':None,'reuse_from_required':False,'target_transaction_plan_required':True,
        'component_manifest_sha256':closure_sha,'preferred_sha256':closure['preferred_sha256'],
        'program_source_tree_sha256':'b'*64,
        'files':[{'path':name,'sha256':sha(body),'size':len(body),'blob':'objects/'+sha(body)}]}
    archive=root/'resources.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('RESOURCES.json',json.dumps(declaration));z.writestr('objects/'+sha(body),body)
    receipt=put(root,'new.haike-upgrade.json',json.dumps({'schema':'haike.unified-upgrade-source/1',
        'status':'source-ready','activated':False,'original_root':str(source),'destination':str(target),'source_commit':'c'*40}))
    projects=source/'Haike_video/projects';projects.mkdir(parents=True)
    media=put(projects,'project-a/render.mp4',b'fixture media for catalog path checks')
    asset=put(projects,'draft-a/assets/still.png',b'fixture still bytes')
    put(projects,'project-a/frozen-request.json',json.dumps({'source_path':str(media),'semantic_event':'do not change'}))
    studio=Studio(projects)
    with studio.db() as db:
        draft={'id':'draft-a','revision':7,'title':'saved draft','input':{'frozen':str(media)}}
        db.execute('INSERT INTO studio_drafts VALUES(?,?,?)',('draft-a',7,json.dumps(draft)))
        db.execute('INSERT INTO studio_assets VALUES(?,?,?,?,?)',('asset-a','draft-a','still','image',str(asset)))
    catalog=WorkCatalog(projects)
    work={'work_id':'work-a','project_id':'project-a','title':'saved work','created_at':'2026-01-01',
        'final_version_id':'version-a','revision':9,'versions':[{'version_id':'version-a','paths':[str(media)],'sha256':recovery.core.digest(media)}],
        'assets':[],'materials':[]}
    with catalog.transaction() as db:db.execute('INSERT INTO works VALUES(?,?,?,?)',('work-a','project-a',9,json.dumps(work)))
    put(source,'Haike_video/.backlot/haike-api/client-config.json','{"synthetic_private_key":"never print contents"}')
    put(source,'tracked.txt','staged version')
    for args in [('init','-q'),('add','tracked.txt')]:
        subprocess.run(['git','-C',str(source),*args],check=True,capture_output=True)
    put(source,'tracked.txt','working version');put(source,'untracked.txt','keep untracked')
    kwargs={'archive_sha256':recovery.core.digest(archive),'archive_size':archive.stat().st_size,
        'closure_sha256':closure_sha,'program_tree_sha256':'b'*64,
        'prepare':lambda _: {'status':'passed','scope':'fixture-no-interpreter'},
        'base_probe':lambda _: {'status':'passed','scope':'fixture-no-abi'},'probe':model_probe}
    return source,target,receipt,archive,kwargs


def model_probe(target,expected):
    """Actual application models read the target; no HTTP/component claim."""
    projects=target/'Haike_video/projects';studio=Studio(projects);catalog=WorkCatalog(projects)
    assert set(expected['drafts']) <= {d['id'] for d in studio.drafts()}
    assert set(expected['works']) <= {w['work_id'] for w in catalog.list()}
    for asset in expected['assets']:assert studio.asset(asset).resolve().is_relative_to(projects)
    for work in expected['works']:assert catalog.media_path(work).resolve().is_relative_to(projects)
    return {'status':'passed','scope':'actual-Studio-and-WorkCatalog-models-only','media_rendered':False}


class SourceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='hsrc-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.source,self.target,self.receipt,self.archive,self.kw=fixture(self.root)

    def run_recovery(self,**overrides):
        return recovery.recover(self.receipt,self.archive,**{**self.kw,**overrides})

    def test_actual_catalog_binding_git_index_and_repeat(self):
        before=recovery.source_git(self.source)
        frozen='Haike_video/projects/project-a/frozen-request.json'
        frozen_sha=recovery.core.digest(self.source/frozen)
        state=self.run_recovery()
        self.assertEqual(state['status'],'fixture-passed');self.assertTrue(state['data_binding_complete'])
        self.assertFalse(state['runtime_ready']);self.assertFalse(state['production_acceptance'])
        self.assertEqual(recovery.source_git(self.source),before)
        self.assertEqual(recovery.core.digest(self.target/frozen),frozen_sha)
        self.assertEqual(Studio(self.target/'Haike_video/projects').draft('draft-a')['revision'],7)
        self.assertEqual(WorkCatalog(self.target/'Haike_video/projects').get('work-a')['revision'],9)
        old=self.source/'Haike_video/.backlot/haike-api/client-config.json'
        self.assertEqual(old.read_bytes(),(self.target/old.relative_to(self.source)).read_bytes())
        snapshots=list((self.target/'.local/source-recovery').glob('*/snapshot-*'))
        self.assertTrue(self.run_recovery()['already_recovered'])
        self.assertEqual(snapshots,list((self.target/'.local/source-recovery').glob('*/snapshot-*')))

    def test_failed_probe_rolls_back_all_data_and_retry(self):
        def fail(*_):raise recovery.RecoveryError('injected health failure')
        with self.assertRaises(recovery.RecoveryError):self.run_recovery(probe=fail)
        self.assertFalse((self.target/'Haike_video/projects/project-a/render.mp4').exists())
        state=self.run_recovery()
        self.assertEqual(state['status'],'fixture-passed')

    def test_all_data_conflicts_preflight_before_any_data_write(self):
        p=put(self.target,'Haike_video/projects/project-a/render.mp4','different user file')
        with self.assertRaises(recovery.RecoveryError):self.run_recovery()
        self.assertEqual(p.read_text(),'different user file')
        self.assertFalse((self.target/'Haike_video/.backlot/studio.sqlite3').exists())

    def test_base_missing_not_runtime_ready_and_no_data_written(self):
        with self.assertRaises(recovery.RecoveryError):
            self.run_recovery(base_probe=lambda _: {'status':'blocked','missing':['fastapi:missing']})
        path=next((self.target/'.local/source-recovery').glob('*/receipt.json'))
        state=recovery.read(path)
        self.assertFalse(state['runtime_ready']);self.assertEqual(state['base_probe']['missing'],['fastapi:missing'])
        self.assertFalse((self.target/'Haike_video/.backlot/studio.sqlite3').exists())

    def test_bad_body_before_runtime_publication(self):
        with zipfile.ZipFile(self.archive) as z:value=json.loads(z.read('RESOURCES.json'))
        with zipfile.ZipFile(self.archive,'w') as z:
            z.writestr('RESOURCES.json',json.dumps(value));z.writestr(value['files'][0]['blob'],b'x'*value['files'][0]['size'])
        with self.assertRaises(recovery.RecoveryError):
            self.run_recovery(archive_sha256=recovery.core.digest(self.archive),archive_size=self.archive.stat().st_size)
        self.assertFalse((self.target/'runtime/node/LICENSE').exists())

    def test_archive_hash_and_program_tamper(self):
        with self.assertRaises(recovery.RecoveryError):self.run_recovery(archive_sha256='0'*64)
        put(self.target,'app.py','edited source')
        with self.assertRaises(recovery.RecoveryError):self.run_recovery()

    def test_target_receipt_must_be_exact_sibling(self):
        wrong=put(self.root,'foreign.json',self.receipt.read_bytes())
        with self.assertRaises(recovery.RecoveryError):recovery.context(wrong,self.kw['closure_sha256'])

    def test_unresolved_asset_path_preserved_and_pending(self):
        studio=Studio(self.source/'Haike_video/projects')
        with studio.db() as db:db.execute('UPDATE studio_assets SET path=?',('Z:/external/private.png',))
        state=self.run_recovery(probe=lambda *_:{'status':'passed','scope':'fixture-no-runtime'})
        self.assertEqual(state['status'],'fixture-passed-data-review');self.assertFalse(state['data_binding_complete'])
        self.assertEqual(state['data']['unknown'][0]['kind'],'unresolved_ui_path')

    def test_unknown_database_and_tracked_config_remain_pending(self):
        put(self.source,'Haike_video/config.yaml','llm:\n  model: old-private-setting\n')
        config=put(self.target,'Haike_video/config.yaml','llm:\n  model: new-default\n')
        closure=recovery.read(self.target/recovery.CLOSURE)
        closure['files']['Haike_video/config.yaml']={'sha256':recovery.core.digest(config),'size':config.stat().st_size}
        put(self.target,recovery.CLOSURE,json.dumps(closure));self.kw['closure_sha256']=recovery.core.digest(self.target/recovery.CLOSURE)
        with zipfile.ZipFile(self.archive) as z:value=json.loads(z.read('RESOURCES.json'));body=z.read(value['files'][0]['blob'])
        value['component_manifest_sha256']=self.kw['closure_sha256']
        with zipfile.ZipFile(self.archive,'w') as z:
            z.writestr('RESOURCES.json',json.dumps(value));z.writestr(value['files'][0]['blob'],body)
        self.kw.update(archive_sha256=recovery.core.digest(self.archive),archive_size=self.archive.stat().st_size)
        db=self.source/'Haike_video/.backlot/unknown.db'
        with closing(sqlite3.connect(db)) as c:c.execute('CREATE TABLE custom (payload TEXT)');c.commit()
        original=config.read_bytes();state=self.run_recovery()
        self.assertEqual(config.read_bytes(),original)
        self.assertEqual({r['kind'] for r in state['data']['unknown']},{'tracked_config_merge_pending','unrecognized_database_preserved'})
        self.assertEqual(state['status'],'fixture-passed-data-review')

    def test_runtime_donor_missing_corrupt_conflict_and_copy(self):
        donor=self.root/'donor';donor.mkdir()
        body=b'example package';name='Haike_video/.venv/Lib/site-packages/example.py'
        put(donor,name,body)
        inv=put(donor,'PACKAGE-MANIFEST.json',json.dumps({'schema':1,'files':[{'path':name,'sha256':sha(body),'size':len(body)}]}))
        folder=self.target/'.local/donor';folder.mkdir(parents=True)
        with self.assertRaises(recovery.RecoveryError):recovery.supplement_runtime(self.target,donor,'0'*64,folder)
        put(self.target,name,b'conflict')
        with self.assertRaises(recovery.RecoveryError):recovery.supplement_runtime(self.target,donor,recovery.core.digest(inv),folder)
        (self.target/name).unlink()
        result=recovery.supplement_runtime(self.target,donor,recovery.core.digest(inv),folder)
        self.assertEqual(result['copied'],1);self.assertEqual((self.target/name).read_bytes(),body)
        self.assertEqual((donor/name).read_bytes(),body)
        self.assertTrue(recovery.verified_base_cache(self.target,donor,recovery.core.digest(inv),result))
        put(self.target,name,b'changed target')
        self.assertFalse(recovery.verified_base_cache(self.target,donor,recovery.core.digest(inv),result))

    def test_probe_environment_keeps_caches_inside_recipient(self):
        env=recovery.probe_environment(self.target)
        self.assertNotIn('PYTHONHOME',env)
        for name in ('USERPROFILE','APPDATA','LOCALAPPDATA','TEMP','TMP','UV_CACHE_DIR'):
            self.assertTrue(Path(env[name]).is_relative_to(self.target))
        self.assertNotIn(str(self.source),env['PYTHONPATH'])

    def test_manifest_rejects_extra_traversal_and_private_paths(self):
        with zipfile.ZipFile(self.archive) as z:value=json.loads(z.read('RESOURCES.json'));body=z.read(value['files'][0]['blob'])
        for extra in ('extra','../escape'):
            with self.subTest(extra=extra):
                bad=self.root/'bad.zip'
                with zipfile.ZipFile(bad,'w') as z:
                    z.writestr('RESOURCES.json',json.dumps(value));z.writestr(value['files'][0]['blob'],body);z.writestr(extra,b'x')
                with zipfile.ZipFile(bad) as z,self.assertRaises((ValueError,KeyError)):
                    recovery.manifest(z,recovery.read(self.target/recovery.CLOSURE),self.kw['closure_sha256'],'b'*64)
        for path in ('runtime/python/.env','Haike_video/projects/a.mp4','runtime/python/../secret','runtime/python/cookies'):
            with self.subTest(path=path):
                try:allowed=recovery.resource_path(path)
                except ValueError:allowed=False
                self.assertFalse(allowed)

    def test_held_queue_frozen_fields_preserved_without_reexecution(self):
        p=self.source/'Haike_video/.backlot/production-queue.sqlite3'
        frozen=json.dumps({'semantic_events':[{'at':1.2,'action':'keep'}],'original_path':str(self.source)})
        with closing(sqlite3.connect(p)) as db:
            db.execute('CREATE TABLE production_jobs(job_id TEXT,status TEXT,worker_id TEXT,lease_expires_at TEXT,frozen_request TEXT)')
            db.execute('INSERT INTO production_jobs VALUES(?,?,?,?,?)',('held-a','paused',None,None,frozen));db.commit()
        original=p.read_bytes();self.run_recovery()
        with closing(sqlite3.connect(self.target/p.relative_to(self.source))) as db:
            self.assertEqual(db.execute('SELECT frozen_request FROM production_jobs').fetchone()[0],frozen)
        self.assertEqual(p.read_bytes(),original)

    def test_active_queue_blocks_before_resource_write(self):
        p=self.source/'Haike_video/.backlot/production-queue.sqlite3'
        with closing(sqlite3.connect(p)) as db:
            db.execute('CREATE TABLE production_jobs(job_id TEXT,status TEXT,worker_id TEXT,lease_expires_at TEXT)')
            db.execute('INSERT INTO production_jobs VALUES(?,?,?,?)',('running-a','running','worker','2099'));db.commit()
        with self.assertRaises(ValueError):self.run_recovery()
        self.assertFalse((self.target/'runtime/node/LICENSE').exists())

    def test_long_runtime_stage_path(self):
        folder=self.target/('.local/'+'deep-a-'*12)/('deep-b-'*12)
        recovery.core.native_path(folder).mkdir(parents=True)
        target=folder/'packages'/'example-1.0.0.dist-info'/'INSTALLER'
        def cleanup_long_fixture():
            assert target.resolve().is_relative_to(self.root)
            recovery.core.native_path(target).unlink(missing_ok=True)
            cursor=target.parent
            while cursor != self.target/'.local':
                recovery.core.native_path(cursor).rmdir();cursor=cursor.parent
        self.addCleanup(cleanup_long_fixture)
        body=b'real long path stream'
        self.assertGreater(len(str(target)),260)
        recovery.copy_new(target,io.BytesIO(body),sha(body),len(body))
        self.assertEqual(recovery.core.native_path(target).read_bytes(),body)
        recovery.copy_new(target,io.BytesIO(body),sha(body),len(body))

    def test_long_data_snapshot_sqlite_and_binding(self):
        folder=self.target/'.local'/('snapshot-a-'*8)/('snapshot-b-'*8)
        self.assertTrue(folder.resolve().is_relative_to(self.target))
        recovery.core.native_path(folder).mkdir(parents=True)
        self.addCleanup(shutil.rmtree,recovery.core.native_path(folder))
        entries=recovery.snapshot_data(self.source,self.target,folder)
        self.assertGreater(max(len(str(folder/'data'/r['path'])) for r in entries),260)
        plan=recovery.plan_data(self.source,self.target,folder,entries,recovery.read(self.target/recovery.CLOSURE))
        recovery.apply_data(self.target,plan)
        self.assertEqual(model_probe(self.target,plan['expected_visible'])['status'],'passed')


if __name__=='__main__':unittest.main()
