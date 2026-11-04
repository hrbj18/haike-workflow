"""Bound public covers/Snapcn bodies: real ZIP, install, conflict and rollback.

Only the final service probe is a test callback; no real media is rendered.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from portable import app_update as core
from portable import source_candidate_recovery as recovery
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('public_resource_legacy',ROOT/'portable/legacy_upgrade.py')
legacy=importlib.util.module_from_spec(spec)
with patch.dict(sys.modules,{'release_core':core}):spec.loader.exec_module(legacy)


def put(root,name,body):
    path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
    return path


class PublicResourceTests(unittest.TestCase):
    def test_exact_scopes_and_private_neighbors(self):
        for path in ('Haike_video/motion-components/snapcn/node_modules/culori/bundled/culori.cjs',
            'Haike_video/motion-components/snapcn/node_modules/motion-utils/package.json',
            'Haike_video/templates/public-covers/motion-package-mg-2150f84a4202e3ebd36a47fc.png',
            'Haike_video/templates/public-covers/investment-full-09-black-pink.webp',
            'Haike_video/templates/public-covers/chromatic-06.jpg',
            'Haike_video/templates/public-covers/store-opening-22.jpeg'):
            with self.subTest(path=path):
                self.assertTrue(legacy.allowed(path,True));self.assertTrue(recovery.resource_path(path))
                self.assertFalse(legacy.allowed(path,False),'resources must not become ordinary source patches')
        for path in ('Haike_video/motion-components/other/node_modules/culori/index.js',
            'Haike_video/motion-components/snapcn/source.tsx',
            'Haike_video/motion-components/snapcn/node_modules/.git/config',
            'Haike_video/motion-components/snapcn/node_modules/a/.env',
            'Haike_video/motion-components/snapcn/node_modules/a/profile/Default/Cookies',
            'Haike_video/motion-components/snapcn/node_modules/a/credentials.json',
            'Haike_video/templates/public-covers/nested/field-notes-v1.png',
            'Haike_video/templates/public-covers/private-cover.svg',
            'Haike_video/templates/public-covers/Field-Notes.png',
            'Haike_video/templates/public-covers/field_notes.png',
            'Haike_video/templates/public-covers/-field-notes.png',
            'Haike_video/templates/public-covers/abc.png',
            'Haike_video/templates/public-covers/'+('a'*81)+'.png',
            'Haike_video/templates/library-covers/private.png'):
            with self.subTest(path=path):
                self.assertFalse(legacy.allowed(path,True));self.assertFalse(recovery.resource_path(path))
        for path in ('Haike_video/templates/public-covers/../private.png',
                     'Haike_video/motion-components/snapcn/node_modules/../../config.yaml'):
            with self.subTest(path=path),self.assertRaises(ValueError):legacy.allowed(path,True)

    def fixture(self,root):
        target=root/'old';bundle=root/'bundle';target.mkdir();bundle.mkdir()
        put(target,'runtime/python/python.exe',b'fixture interpreter, never executed')
        put(target,'RELEASE.json',core.json_bytes({'source_commit':'a'*40}))
        inv=put(target,'PACKAGE-MANIFEST.json',core.json_bytes({'schema':1,'files':[]}))
        put(target,'Haike_video/templates/library-covers/private.png',b'user private original cover')
        payloads={'Haike_video/templates/public-covers/field-notes-v1.png':b'public cover fixture body',
            'Haike_video/motion-components/snapcn/node_modules/culori/bundled/culori.cjs':b'public package fixture body'}
        closure={'schema':'haike.motion-upgrade-closure/1','preferred_sha256':'b'*64,
            'resources':{n:{'size':len(b),'sha256':hashlib.sha256(b).hexdigest()} for n,b in payloads.items()}}
        path=put(bundle,'closure.json',core.json_bytes(closure))
        resources={'id':legacy.ID,'packages':[],'component_manifest_sha256':core.digest(path),
            'preferred_sha256':'b'*64,'files':[{'path':name,**closure['resources'][name],
                'blob':'objects/'+closure['resources'][name]['sha256'],'before_sha256':None} for name in payloads]}
        archive=root/'resources.zip'
        def save_resources():
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('RESOURCES.json',core.json_bytes(resources))
                for row in resources['files']:z.writestr(row['blob'],payloads[row['path']])
        save_resources()
        plan={'id':legacy.ID,'schema':1,'base_source_commit':'a'*40,'base_manifest_sha256':core.digest(inv),
            'required_files':[],'resources':{'sha256':core.digest(archive)},
            'files':[{'path':legacy.CLOSURE_PATH,'payload':'closure.json','size':path.stat().st_size,
                      'sha256':core.digest(path),'before_sha256':None}],
            'release':{'edition':'haike-workflow-2','version':'1.2.4','channel':'stable','runtime_id':'fixture',
                'data_schema':1,'platform':'windows-x64','source_commit':'c'*40}}
        put(bundle,'UPGRADE.json',core.json_bytes(plan))
        return target,bundle,archive,plan,resources,payloads,save_resources

    def test_real_install_repeat_rollback_and_private_cover_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            target,bundle,archive,_,_,payloads,_=self.fixture(Path(folder))
            private=target/'Haike_video/templates/library-covers/private.png';before=private.read_bytes()
            with patch.object(legacy,'stopped'):
                result=legacy.apply(bundle,target,archive,health_check=lambda _:{'ok':True,'templates':[]})
                self.assertTrue(legacy.apply(bundle,target,archive,health_check=lambda _:{'ok':True,'templates':[]})['already_current'])
            for path,body in payloads.items():self.assertEqual((target/path).read_bytes(),body)
            self.assertEqual(private.read_bytes(),before)
            legacy.restore(target,Path(result['backup']))
            for path in payloads:self.assertFalse((target/path).exists())
            self.assertEqual(private.read_bytes(),before)

    def test_same_name_user_cover_conflict_never_writes_any_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            target,bundle,archive,_,_,payloads,_=self.fixture(Path(folder))
            name=next(iter(payloads));private=put(target,name,b'user private same-name image')
            with self.assertRaisesRegex(ValueError,'本地修改'):
                legacy.preflight(bundle,target,archive,require_stopped=False)
            self.assertEqual(private.read_bytes(),b'user private same-name image')
            self.assertFalse((target/legacy.CLOSURE_PATH).exists())
            self.assertFalse((target/next(p for p in payloads if '/node_modules/' in p)).exists())

    def test_each_new_resource_requires_bound_closure_hash_size_and_body(self):
        for tamper in ('component','declared_sha','declared_size','missing_declaration','body'):
            with self.subTest(tamper=tamper),tempfile.TemporaryDirectory() as folder:
                target,bundle,archive,plan,resources,payloads,save=self.fixture(Path(folder))
                if tamper=='component':resources['component_manifest_sha256']='d'*64
                elif tamper in {'declared_sha','declared_size','missing_declaration'}:
                    closure=legacy.read(bundle/'closure.json');name=resources['files'][0]['path']
                    if tamper=='declared_sha':closure['resources'][name]['sha256']='e'*64
                    elif tamper=='declared_size':closure['resources'][name]['size']+=1
                    else:closure['resources'].pop(name)
                    put(bundle,'closure.json',core.json_bytes(closure))
                    plan['files'][0].update(size=(bundle/'closure.json').stat().st_size,sha256=core.digest(bundle/'closure.json'))
                    resources['component_manifest_sha256']=plan['files'][0]['sha256']
                else:payloads[resources['files'][0]['path']]=b'corrupted body'
                save();plan['resources']['sha256']=core.digest(archive);put(bundle,'UPGRADE.json',core.json_bytes(plan))
                with self.assertRaises(ValueError):legacy.preflight(bundle,target,archive,require_stopped=False)
                self.assertFalse((target/legacy.CLOSURE_PATH).exists())

    def test_complete_source_recovery_uses_same_json_authority(self):
        with tempfile.TemporaryDirectory() as folder:
            target,bundle,_,_,resources,payloads,_=self.fixture(Path(folder))
            closure=legacy.read(bundle/'closure.json');closure.update(files={})
            value={'schema':'haike.complete-resource-recovery/1','kind':'content-addressed-resource-bodies',
                'baseline_dependency':None,'reuse_from_required':False,'target_transaction_plan_required':True,
                'component_manifest_sha256':'a'*64,'preferred_sha256':closure['preferred_sha256'],
                'program_source_tree_sha256':'b'*64,'files':resources['files']}
            archive=Path(folder)/'complete.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('RESOURCES.json',core.json_bytes(value))
                for row in value['files']:z.writestr(row['blob'],payloads[row['path']])
            with zipfile.ZipFile(archive) as z:
                _,rows,_=recovery.manifest(z,closure,'a'*64,'b'*64)
                self.assertEqual(len(rows),2)
                closure['resources'].pop(value['files'][0]['path'])
                with self.assertRaisesRegex(ValueError,'不属于本期SHA绑定闭包'):
                    recovery.manifest(z,closure,'a'*64,'b'*64)


if __name__=='__main__':unittest.main()
