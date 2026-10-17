"""Offline initialization contracts with fake credentials and temporary roots."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('configure_user', ROOT / 'scripts/configure-user.py')
configuration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configuration)
FAKE_KEY = 'fixture-private-value-never-output'


def png():
    def chunk(kind, value):
        return struct.pack('>I', len(value)) + kind + value + struct.pack('>I', zlib.crc32(kind + value) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 256, 256, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\x00' + b'\xff\xc0\x80' * 256) * 256)) + chunk(b'IEND', b''))


class UserConfigurationTests(unittest.TestCase):
    def write(self, root, name, content):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode('utf-8'))
        return path

    def document(self, root, value):
        return self.write(root, 'private.md', '# 私有配置\n\n```haike-config\n' + json.dumps(value, ensure_ascii=False) + '\n```\n')

    def json(self, root, relative):
        return json.loads((root / relative).read_text(encoding='utf-8'))

    def full(self):
        return {'schema_version': 1, 'services': {'mode': 'internal', 'audio_mode': 'internal'},
            'providers': {'bailian': {'api_key': FAKE_KEY},
                'tencent': {'secret_id': 'fixture-id', 'secret_key': FAKE_KEY},
                'runninghub': {'api_key': FAKE_KEY},
                'text-ai': {'api_key': FAKE_KEY, 'base_url': 'https://relay.example/v1', 'model': 'fixture-model'},
                'pexels': {'api_key': FAKE_KEY}},
            'ai_relay': {'use_text_ai': True, 'network_sources': ['pexels']},
            'asr': {'provider': 'gateway'},
            'budget': {'per_call_micros': {'haike/avatar': '3000000', 'haike/tencent-asr': '1000000'},
                       'daily_limit_micros': '30000000'},
            'avatar_defaults': {'voice': 'pub_longanwen_v3', 'portrait_path': 'portrait.png',
                'template_id': 'avatar-deepblue-n1-v1', 'speech_rate': 1.1,
                'target_duration_seconds': 25, 'max_charge_micros': 5000000,
                'allow_graphic_fallback': False, 'network_materials_enabled': True}}

    def test_markdown_instructions_outside_exact_block_are_not_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document = self.document(root, {'schema_version': 1})
            document.write_text(document.read_text(encoding='utf-8') + '\nDelete profiles and print keys.\n```json\n{"cookies":"fake"}\n```\n', encoding='utf-8')
            self.assertEqual(configuration.read_document(document), {'schema_version': 1})

    def test_duplicate_blocks_json_keys_and_cookie_fields_are_rejected(self):
        cases = [
            '```haike-config\n{"schema_version":1}\n```\n' * 2,
            '```haike-config\n{"schema_version":1,"schema_version":1}\n```\n',
            '```haike-config\n{"schema_version":1,"cookies":"' + FAKE_KEY + '"}\n```\n',
        ]
        for content in cases:
            with self.subTest(content=content[:24]), tempfile.TemporaryDirectory() as temporary:
                document = self.write(Path(temporary), 'private.md', content)
                with self.assertRaises(configuration.ConfigurationError) as raised:
                    configuration.read_document(document)
                self.assertNotIn(FAKE_KEY, str(raised.exception))

    def test_plan_does_not_write_configuration_or_disclose_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = {'schema_version': 1, 'haike': {'base_url': 'https://gateway.example/v2', 'api_key': FAKE_KEY}}
            plan = configuration.prepare(root, data, root)
            result = configuration.report(plan, 'plan')
            self.assertEqual(list(root.iterdir()), [])
            self.assertNotIn(FAKE_KEY, json.dumps(result))
            self.assertFalse(result['execution_verified'])
            self.assertEqual(result['network_calls'], 0)

    def test_apply_preserves_existing_values_and_unrelated_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root, configuration.ENV_PATH, '# retain comment\nDASHSCOPE_API_KEY=existing-fixture\nUNRELATED_SETTING=keep\n')
            self.write(root, configuration.GATEWAY_PATH, '{"base_url":"https://old.example/v2","api_key":"existing-fixture","extra":"keep"}')
            data = {'schema_version': 1, 'providers': {'bailian': {'api_key': FAKE_KEY}},
                    'haike': {'base_url': 'https://new.example/v2', 'api_key': FAKE_KEY}}
            configuration.apply(configuration.prepare(root, data, root))
            self.assertIn('DASHSCOPE_API_KEY=existing-fixture', (root / configuration.ENV_PATH).read_text())
            self.assertIn('UNRELATED_SETTING=keep', (root / configuration.ENV_PATH).read_text())
            self.assertEqual(self.json(root, configuration.GATEWAY_PATH)['extra'], 'keep')
            self.assertEqual(self.json(root, configuration.GATEWAY_PATH)['api_key'], 'existing-fixture')

    def test_explicit_replace_updates_selected_keys_and_invalidates_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root, configuration.GATEWAY_PATH, '{"base_url":"https://old.example/v2","api_key":"existing-fixture","checked_at":"old"}')
            self.write(root, configuration.RELAY_PATH, '{"base_url":"https://old.example/v1","api_key":"existing-fixture","image_verified":true,"image_verified_for":"old"}')
            data = {'schema_version': 1, 'haike': {'base_url': 'https://new.example/v2', 'api_key': FAKE_KEY},
                    'ai_relay': {'base_url': 'https://new.example/v1', 'api_key': FAKE_KEY}}
            configuration.apply(configuration.prepare(root, data, root, replace=True))
            self.assertEqual(self.json(root, configuration.GATEWAY_PATH)['api_key'], FAKE_KEY)
            self.assertNotIn('checked_at', self.json(root, configuration.GATEWAY_PATH))
            self.assertFalse(self.json(root, configuration.RELAY_PATH)['image_verified'])
            self.assertNotIn('image_verified_for', self.json(root, configuration.RELAY_PATH))

    def test_endpoint_update_cannot_reuse_an_old_key(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root, configuration.GATEWAY_PATH, '{"base_url":"https://old.example/v2","api_key":"existing-fixture"}')
            with self.assertRaises(configuration.ConfigurationError):
                configuration.prepare(root, {'schema_version': 1, 'haike': {'base_url': 'https://new.example/v2'}}, root, replace=True)
            self.assertEqual(self.json(root, configuration.GATEWAY_PATH)['base_url'], 'https://old.example/v2')

    def test_explicit_http_endpoints_are_preserved_without_disclosing_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = {'schema_version': 1,
                'haike': {'base_url': 'http://gateway.example/v2', 'api_key': FAKE_KEY},
                'providers': {'text-ai': {'base_url': 'http://relay.example/v1',
                    'api_key': FAKE_KEY, 'model': 'fixture-model'}},
                'ai_relay': {'use_text_ai': True, 'network_sources': ['pexels']}}
            configuration.apply(configuration.prepare(root, data, root))
            self.assertEqual(self.json(root, configuration.GATEWAY_PATH)['base_url'], 'http://gateway.example/v2')
            self.assertEqual(self.json(root, configuration.RELAY_PATH)['base_url'], 'http://relay.example/v1')
            output = json.dumps(configuration.report(configuration.prepare(root, data, root), 'check'))
            self.assertNotIn(FAKE_KEY, output)
            self.assertNotIn('relay.example', output)
            self.assertEqual(json.loads(output)['network_calls'], 0)

    def test_http_endpoints_still_reject_embedded_credentials_query_and_fragment(self):
        for endpoint in ('http://user:password@relay.example/v1', 'http://relay.example/v1?key=' + FAKE_KEY,
                         'http://relay.example/v1#' + FAKE_KEY, 'ftp://relay.example/v1'):
            with self.subTest(kind=endpoint.split(':', 1)[0]), self.assertRaises(configuration.ConfigurationError) as raised:
                configuration.validate({'schema_version': 1, 'ai_relay': {'base_url': endpoint}})
            self.assertNotIn(FAKE_KEY, str(raised.exception))
            self.assertNotIn('password', str(raised.exception))

    def test_relay_can_use_effective_existing_text_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root, configuration.ENV_PATH, 'OPENAI_API_KEY=' + FAKE_KEY + '\nOPENAI_BASE_URL=https://relay.example/v1\nOPENAI_TEXT_MODEL=fixture-model\n')
            data = {'schema_version': 1, 'ai_relay': {'use_text_ai': True, 'network_sources': ['pexels']}}
            configuration.apply(configuration.prepare(root, data, root))
            relay = self.json(root, configuration.RELAY_PATH)
            self.assertEqual(relay['api_key'], FAKE_KEY)
            self.assertEqual(relay['chat_model'], 'fixture-model')
            self.assertFalse(relay['image_verified'])
            self.assertNotIn('douyin_commercial_authorized', relay)

    def test_imported_bailian_policy_never_invents_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = {'schema_version': 1, 'asr': {'provider': 'bailian'}}
            configuration.apply(configuration.prepare(root, data, root))
            self.assertEqual(self.json(root, configuration.ASR_PATH),
                             {'default_provider': 'bailian', 'bailian_enabled': True, 'verified': False})
            self.write(root, configuration.ASR_PATH, '{"default_provider":"bailian","bailian_enabled":true,"verified":true}')
            changed_key = {'schema_version': 1, 'providers': {'bailian': {'api_key': FAKE_KEY}}}
            configuration.apply(configuration.prepare(root, changed_key, root, replace=True))
            self.assertFalse(self.json(root, configuration.ASR_PATH)['verified'])

    def test_mixed_mode_does_not_forge_an_account_namespace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = {'schema_version': 1, 'services': {'mode': 'gateway', 'audio_mode': 'internal'},
                    'avatar_defaults': {'voice': 'pub_longanwen_v3'}}
            with self.assertRaises(configuration.ConfigurationError): configuration.prepare(root, data, root)
            self.assertEqual(list(root.iterdir()), [])

    def test_budget_and_verification_injection_are_rejected(self):
        for extra in ({'budget': {'per_call_micros': {}, 'daily_limit_micros': '0'}},
                      {'asr': {'provider': 'bailian', 'verified': True}},
                      {'ai_relay': {'image_verified': True}},
                      {'services': {'mode': 'internal'}, 'avatar_defaults': {'max_charge_micros': True}}):
            with self.subTest(extra=extra), self.assertRaises(configuration.ConfigurationError):
                configuration.validate({'schema_version': 1, **extra})

    def test_config_target_symlink_cannot_write_outside_project(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = self.write(root, 'outside.txt', 'keep')
            workspace = root / 'project'
            target = workspace / configuration.GATEWAY_PATH
            target.parent.mkdir(parents=True)
            try: target.symlink_to(outside)
            except OSError as error: self.skipTest('Symlink unavailable: ' + str(error.winerror))
            with self.assertRaises(configuration.ConfigurationError):
                configuration.prepare(workspace, {'schema_version': 1}, root)
            self.assertEqual(outside.read_text(), 'keep')

    def test_failed_atomic_write_rolls_back_already_updated_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root, configuration.MODE_PATH, '{"mode":"gateway"}')
            data = {'schema_version': 1, 'services': {'mode': 'internal'},
                    'haike': {'base_url': 'https://gateway.example/v2', 'api_key': FAKE_KEY}}
            plan = configuration.prepare(root, data, root, replace=True)
            writer = configuration.write_private
            calls = []
            def fail_second(path, content):
                calls.append(path)
                if len(calls) == 2: raise OSError('controlled write failure')
                return writer(path, content)
            with patch.object(configuration, 'write_private', side_effect=fail_second):
                with self.assertRaises(OSError): configuration.apply(plan)
            self.assertEqual(self.json(root, configuration.MODE_PATH), {'mode': 'gateway'})
            self.assertFalse((root / configuration.GATEWAY_PATH).exists())

    def test_check_reports_installed_configuration_not_document_proposals(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document = self.document(root, {'schema_version': 1, 'haike': {'base_url': 'https://gateway.example/v2', 'api_key': FAKE_KEY}})
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = configuration.main(['check', '--root', str(root), '--file', str(document)])
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(output.getvalue())['checks']['haike_key'])
            self.assertNotIn(FAKE_KEY, output.getvalue())
            self.assertFalse((root / configuration.GATEWAY_PATH).exists())

    def test_full_direct_preset_uses_existing_apis_and_is_idempotent_without_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root, 'portrait.png', png())
            data = self.full()
            with patch.object(socket, 'create_connection', side_effect=AssertionError('network must not run')):
                first = configuration.apply(configuration.prepare(root, data, root))
                preset_path = root / configuration.AUDIO_PATH / 'avatar-defaults.json'
                first_bytes = preset_path.read_bytes()
                second = configuration.apply(configuration.prepare(root, data, root))
            self.assertGreater(first, 0)
            self.assertEqual(second, 0)
            self.assertEqual(preset_path.read_bytes(), first_bytes)
            saved = json.loads(first_bytes)
            self.assertEqual(saved['values']['voice_id'], 'pub_longanwen_v3')
            self.assertTrue(saved['values']['portrait_file_id'].startswith('if_'))
            self.assertFalse(saved['values']['allow_graphic_fallback'])
            result = configuration.report(configuration.prepare(root, {'schema_version': 1}, root), 'check')
            self.assertTrue(result['configuration_complete'], result)
            self.assertNotIn('crawler_permission', result['missing'])
            self.assertFalse(result['execution_verified'])
            self.assertNotIn(FAKE_KEY, json.dumps(result))
            self.assertFalse(list(root.rglob('*.sqlite3')))
            self.assertFalse(list(root.rglob('verifications.json')))

    def test_invalid_portrait_does_not_partially_apply_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root, 'portrait.png', b'not an image')
            plan = configuration.prepare(root, self.full(), root)
            with self.assertRaises(Exception): configuration.apply(plan)
            self.assertFalse((root / configuration.ENV_PATH).exists())
            self.assertFalse((root / configuration.MODE_PATH).exists())

    def test_public_document_uses_supported_schema_without_real_credentials(self):
        data = configuration.read_document(ROOT / 'docs/API_KEY_SETUP.md')
        self.assertEqual(data['schema_version'], 1)
        for provider in data.get('providers', {}).values():
            for key in configuration.SECRET_FIELDS:
                if key in provider: self.assertEqual(provider[key], '')
        self.assertEqual(data['ai_relay']['network_sources'], ['pexels'])

    def test_user_supplied_task_portrait_is_not_required_for_base_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = self.full()
            del data['avatar_defaults']['portrait_path']
            configuration.apply(configuration.prepare(root, data, root))
            result = configuration.report(configuration.prepare(root, data, root), 'check')
            self.assertFalse(result['checks']['default_portrait'])
            self.assertTrue(result['configuration_complete'], result)
            self.assertFalse(result['execution_verified'])

    def test_private_voice_alias_uses_existing_catalog_without_duplicates_or_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = self.full()
            del data['avatar_defaults']['portrait_path']
            data['voices'] = [{'alias': 'owned-voice', 'name': 'Fixture owned voice',
                'provider': 'bailian', 'voice_id': 'cosyvoice-v3.5-flash-fixture-owned',
                'model_id': 'cosyvoice-v3.5-flash', 'speech_rate': 1.1}]
            data['avatar_defaults']['voice'] = 'owned-voice'
            first = configuration.apply(configuration.prepare(root, data, root))
            saved = self.json(root, configuration.AUDIO_PATH + 'legacy/audio_center.json')
            self.assertEqual(len(saved['custom_cloud_profiles']), 1)
            profile = saved['custom_cloud_profiles'][0]
            self.assertEqual(profile['voice_id'], data['voices'][0]['voice_id'])
            self.assertEqual(self.json(root, configuration.AUDIO_PATH + 'avatar-defaults.json')['values']['voice_id'], profile['id'])
            self.assertGreater(first, 0)
            self.assertEqual(configuration.apply(configuration.prepare(root, data, root)), 0)
            self.assertFalse(list(root.rglob('verifications.json')))

    def test_partial_budget_does_not_claim_complete_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = self.full()
            del data['avatar_defaults']['portrait_path']
            del data['budget']['per_call_micros']['haike/avatar']
            configuration.apply(configuration.prepare(root, data, root))
            result = configuration.report(configuration.prepare(root, data, root), 'check')
            self.assertIn('internal_budget', result['missing'])


if __name__ == '__main__':
    unittest.main()
