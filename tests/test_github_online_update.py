"""Network update contract: trusted source, bounded downloads and no token leak."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import Request
import zipfile

spec = importlib.util.spec_from_file_location('github_updater', Path(__file__).resolve().parents[1] / 'scripts/update-from-github.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class GitHubOnlineUpdateTests(unittest.TestCase):
    def feed(self):
        asset = {'url': 'https://github.com/hrbj18/haike-workflow/releases/download/v1.2.1/program.zip',
                 'size': 100, 'sha256': 'a'*64}
        return {'schema': 1, 'edition': 'haike-workflow-2', 'channel': 'stable', 'version': '1.2.1',
                'bootstrap': {'base_source_commit': updater.BASE_SOURCE, 'program': dict(asset), 'resources': dict(asset)}}

    def test_repository_and_release_url_resolve_stable_feed(self):
        self.assertIn('/releases/latest/download/', updater.feed_url('https://github.com/hrbj18/haike-workflow'))
        self.assertIn('/download/v1.2.1/', updater.feed_url('https://github.com/hrbj18/haike-workflow/releases/tag/v1.2.1'))
        for url in ['https://github.com/other/repo', 'http://github.com/hrbj18/haike-workflow',
                    'https://github.com.attacker.test/hrbj18/haike-workflow',
                    'https://user@github.com/hrbj18/haike-workflow']:
            with self.assertRaises(ValueError):
                updater.feed_url(url)

    def test_feed_requires_pinned_asset_identity_and_total_under_200mb(self):
        value = self.feed()
        updater.validate_feed(value)
        value['bootstrap']['resources']['size'] = 200_000_000
        with self.assertRaisesRegex(ValueError, '总量'):
            updater.validate_feed(value)
        value = self.feed(); value['bootstrap']['program']['sha256'] = 'bad'
        with self.assertRaisesRegex(ValueError, '摘要'):
            updater.validate_feed(value)

    def test_redirect_drops_github_credentials_before_cdn_request(self):
        original = Request('https://api.github.com/repos/hrbj18/private/releases/assets/123',
                           headers={'Authorization': 'Bearer unit-test-only'})
        redirected = updater.Redirect().redirect_request(original, None, 302, 'Found', {},
                                                        'https://release-assets.githubusercontent.com/payload.zip')
        self.assertFalse(redirected.has_header('Authorization'))
        with self.assertRaises(ValueError):
            updater.Redirect().redirect_request(original, None, 302, 'Found', {}, 'http://bad.test/file')

    def test_private_auth_never_goes_to_browser_download_urls(self):
        with patch.object(updater, 'github_token') as token:
            with self.assertRaisesRegex(ValueError, '认证'):
                updater.remote('https://github.com/hrbj18/haike-workflow/releases/download/v1.2.1/a.zip', 'github-cli')
            token.assert_not_called()

    def test_cached_verified_asset_is_reused_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); content = b'validated-program'
            asset = {'size': len(content), 'sha256': hashlib.sha256(content).hexdigest(), 'url': 'https://example.test/file'}
            with patch.object(updater, 'remote', return_value=io.BytesIO(content)) as network:
                path = updater.fetch_asset(root, asset)
                self.assertEqual(path.read_bytes(), content)
                network.assert_called_once()
            with patch.object(updater, 'remote', side_effect=AssertionError('must not redownload')):
                self.assertEqual(updater.fetch_asset(root, asset), path)

    def test_corrupt_or_oversized_download_never_creates_installable_zip(self):
        for data in [b'bad', b'too much data']:
            with self.subTest(data=data), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                asset = {'size': 3, 'sha256': hashlib.sha256(b'yes').hexdigest(), 'url': 'https://example.test/file'}
                with patch.object(updater, 'remote', return_value=io.BytesIO(data)):
                    with self.assertRaises(ValueError):
                        updater.fetch_asset(root, asset)
                self.assertFalse(list(root.rglob('*.zip')))
                self.assertFalse(list(root.rglob('*.part')))

    def test_zip_traversal_and_duplicate_names_are_rejected(self):
        for names in [['haike-update-1.2/../../outside.py'],
                      ['haike-update-1.2/A.py', 'haike-update-1.2/a.py']]:
            with self.subTest(names=names), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); archive = root / 'program.zip'
                with zipfile.ZipFile(archive, 'w') as zipped:
                    for name in names:
                        zipped.writestr(name, b'never execute')
                with self.assertRaises(ValueError):
                    updater.extract_program(root, archive)
                self.assertFalse((root / 'outside.py').exists())

    def test_installed_current_version_does_not_download_or_stop_services(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'PACKAGE-MANIFEST.json').write_text('{}')
            (root / 'RELEASE.json').write_text(json.dumps({'edition': 'haike-workflow-2', 'version': '1.2.1'}))
            with patch.object(updater, 'remote', return_value=io.BytesIO(json.dumps(self.feed()).encode())), \
                 patch.object(updater, 'fetch_asset', side_effect=AssertionError('no download')), \
                 patch.object(updater, 'stop_legacy', side_effect=AssertionError('no stop')):
                self.assertTrue(updater.run('https://github.com/hrbj18/haike-workflow', root)['already_current'])


if __name__ == '__main__':
    unittest.main()
