import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('public_release_check', Path(__file__).resolve().parents[1] / 'scripts/check-public-release.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class PublicReleaseBoundaryTests(unittest.TestCase):
    def test_nested_personal_motion_key_is_rejected(self):
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, 'w') as archive:
            archive.writestr('personal/motiongit.key.json', '{"key":"synthetic-test-only"}')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'templates.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('templates/example.motion', inner.getvalue())
            with self.assertRaisesRegex(ValueError, '个人凭据'):
                checker.check(path)

    def test_program_sources_are_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'program.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('payload/portable/update_service.py', '# source only')
                archive.writestr('UPDATE-MANIFEST.json', '{}')
            checker.check(path)


if __name__ == '__main__':
    unittest.main()
