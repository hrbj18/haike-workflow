"""Trusted-feed source continuation admission; no network, Git commits or media."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from portable import app_update as core,source_candidate_recovery as recovery,source_upgrade,unified_upgrade as unified


def feed_fixture():
    online=unified.online();prefix=unified.OFFICIAL+'/releases/download/v1.2.3/'
    templates=[{'template_id':name,'version':version,'registry':online.REPLAY_PREFIX+group,'execution':'supported'}
        for group,items in online.MOTION_BASE_IDENTITIES.items() for name,version in items]
    cap={'schema':'haike.motion-capability/1','sha256':'a'*64,
        'presets':[{'id':'old-native-preset','version':'1.0.0','sha256':'b'*64,'protocol':'native','requires_package':True}],
        'motion_upgrade':{'schema':'haike.motion-replay-delivery/2','closure_sha256':'c'*64,'preferred_sha256':'d'*64,'templates':templates}}
    program={'url':prefix+'program.zip','size':10,'sha256':'e'*64}
    complete={'url':prefix+'complete.zip','size':10,'sha256':'f'*64}
    return {'schema':1,'edition':'haike-workflow-2','channel':'stable','version':'1.2.3','source_commit':'a'*40,
        'bootstrap':{'base_source_commit':online.BASE_SOURCE,'program':program,'resources':complete},
        'template_capability':cap,'source_recovery':{'schema':'haike.source-recovery-feed/1',
            'program_tree_sha256':'a'*64,'closure_sha256':'c'*64,'resources':complete,
            'base_lock':{'path':recovery.BASE_LOCK,'sha256':'b'*64},
            'implementation':{'path':'portable/source_candidate_recovery.py','sha256':'c'*64}}}


class SourceUpgradeTests(unittest.TestCase):
    def test_same_feed_requires_real_source_tree_closure_lock_and_official_asset(self):
        online=unified.online();feed=feed_fixture();online.validate_feed(feed)
        for mutation in ('closure','source_tree','helper','lock_path','foreign','api_repo','size','count','duplicate'):
            with self.subTest(mutation=mutation):
                value=copy.deepcopy(feed);sr=value['source_recovery']
                if mutation=='closure':sr['closure_sha256']='0'*64
                elif mutation=='source_tree':sr['program_tree_sha256']='invented commit'
                elif mutation=='helper':sr['implementation']['sha256']='no SHA'
                elif mutation=='lock_path':sr['base_lock']['path']='.local/private.txt'
                elif mutation=='foreign':sr['resources']['url']='https://example.org/complete.zip'
                elif mutation=='api_repo':sr['resources']['url']='https://api.github.com/repos/other/repo/releases/assets/1'
                elif mutation=='size':sr['resources']['size']=online.MAX_DOWNLOAD
                elif mutation=='count':value['template_capability']['motion_upgrade']['templates'].pop()
                else:value['template_capability']['motion_upgrade']['templates'][1]=value['template_capability']['motion_upgrade']['templates'][0]
                with self.assertRaises(ValueError):online.validate_feed(value)

    def program(self,root):
        feed=feed_fixture();descriptor=feed['source_recovery'];names=source_upgrade.REQUIRED_PROGRAM|{recovery.CLOSURE}
        rows=[]
        for name in sorted(names):
            p=core.safe_path(root,'payload/'+name)
            core._atomic_write(p,b'{}\n' if p.suffix=='.json' else b'# public source fixture\n')
            rows.append({'path':name,'payload':'payload/'+name,'size':p.stat().st_size,'sha256':core.digest(p)})
        frozen=[{k:r[k] for k in ('path','size','sha256')} for r in rows]
        descriptor['program_tree_sha256']=recovery.identity(frozen)
        actual={r['path']:r for r in rows};descriptor['closure_sha256']=actual[recovery.CLOSURE]['sha256']
        descriptor['base_lock']['sha256']=actual[recovery.BASE_LOCK]['sha256']
        descriptor['implementation']['sha256']=actual['portable/source_candidate_recovery.py']['sha256']
        feed['template_capability']['motion_upgrade']['closure_sha256']=descriptor['closure_sha256']
        plan={'release':{'version':feed['version'],'source_commit':feed['source_commit'],'template_capability':feed['template_capability']},'files':rows}
        core._atomic_write(root/'UPGRADE.json',core.json_bytes(plan))
        return feed,plan

    def test_program_complete_identity_and_required_delivery(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);feed,plan=self.program(root)
            _,rows,frozen=source_upgrade.program_rows(root,feed,feed['source_recovery'])
            self.assertEqual(len(rows),len(source_upgrade.REQUIRED_PROGRAM)+1)
            self.assertEqual(recovery.identity(frozen),feed['source_recovery']['program_tree_sha256'])
            core._atomic_write(root/'payload/portable/source_candidate_recovery.py',b'tampered')
            with self.assertRaisesRegex(ValueError,'正文SHA不符'):source_upgrade.program_rows(root,feed,feed['source_recovery'])

    def test_missing_lock_or_helper_never_becomes_source_ready(self):
        for missing in (recovery.BASE_LOCK,'scripts/recover-upgrade-source.py'):
            with self.subTest(missing=missing),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);feed,plan=self.program(root)
                plan['files']=[r for r in plan['files'] if r['path']!=missing]
                feed['source_recovery']['program_tree_sha256']=recovery.identity([{k:r[k] for k in ('path','size','sha256')} for r in plan['files']])
                core._atomic_write(root/'UPGRADE.json',core.json_bytes(plan))
                with self.assertRaisesRegex(ValueError,'未交付必需恢复器/CLI/基础锁'):
                    source_upgrade.program_rows(root,feed,feed['source_recovery'])

    def test_missing_trusted_recovery_description_does_not_checkout_or_write_target(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'old';source.mkdir();core._atomic_write(source/'Haike_video/backlot/server.py',b'old')
            target=Path(folder)/'new';feed=feed_fixture();feed.pop('source_recovery')
            with patch.object(unified,'load_feed',return_value=feed),self.assertRaisesRegex(ValueError,'源码恢复发行描述无效'):
                unified.execute(source,destination=target)
            self.assertFalse(target.exists());self.assertEqual((source/'Haike_video/backlot/server.py').read_bytes(),b'old')

    def test_apply_dispatches_actual_source_continuation_instead_of_checkout_only(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder);core._atomic_write(source/'Haike_video/backlot/server.py',b'historical')
            with patch.object(unified,'load_feed',return_value=feed_fixture()),patch.object(unified,'source_runtime_candidate',return_value={'ok':True,'runtime_ready':True}) as runner,patch.object(unified,'source_candidate') as checkout:
                self.assertTrue(unified.execute(source)['runtime_ready'])
            runner.assert_called_once();checkout.assert_not_called()

    def test_current18_inputs_do_not_inherit_old_native_needs_setup(self):
        value=unified.production_inputs({'ok':True,'component_check':{'status':'passed','template_count':18},
            'templates':[{'id':'old-native-preset','status':'needs_setup'}]},feed_fixture())['production_input_preparation']
        self.assertEqual(value['current18']['template_count'],18)
        self.assertEqual(value['current18']['component_status'],'passed')
        self.assertFalse(value['current18']['legacy_native_setup_blocks_current18'])
        self.assertEqual(value['current18']['status'],'awaiting-episode-inputs')
        self.assertFalse(value['legacy_native_presets']['affects_current18'])

    def test_base_locks_are_full_source_delivery_but_never_ordinary_patch(self):
        for name in (recovery.BASE_LOCK,'_distribution-tools/locks/creatorhub.txt'):
            self.assertTrue(core.is_program_path(name));self.assertTrue(core.is_dependency_path(name))
        self.assertFalse(core.is_program_path('_distribution-tools/locks/private-account.txt'))


if __name__=='__main__':unittest.main()
