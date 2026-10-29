"""Private template relocation preserves dependency identities and user files."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from portable.template_assets import MANIFEST, encoded, materialize


class TemplateAssetsTests(unittest.TestCase):
    def fixture(self, root):
        folder = root / '.local/motion-console/assets'
        folder.mkdir(parents=True)
        media = folder / 'sample.bin'
        media.write_bytes(b'private-media')
        proof = json.dumps({'asset': {'path': 'sample.bin', 'sha256': hashlib.sha256(media.read_bytes()).hexdigest()}}, indent=2).replace('\n', '\r\n') + '\r\n'
        seed = json.dumps({'proof': {'path': 'proof.json', 'sha256': hashlib.sha256(proof.encode()).hexdigest()}})
        documents = {'.local/motion-console/assets/proof.json': proof, '.local/motion-console/assets/seed.json': seed}
        (root / MANIFEST).write_bytes(encoded({'schema': 1, 'documents': documents}))
        return folder

    def test_crlf_identity_idempotence_and_relocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp) / 'first', Path(tmp) / 'second'
            folder = self.fixture(first)
            user = first / '.local/user-preset.json'
            user.write_bytes(b'user-owned')
            self.assertEqual(materialize(first), 2)
            self.assertEqual(materialize(first), 0)
            seed = json.loads((folder / 'seed.json').read_bytes())
            self.assertEqual(seed['proof']['sha256'], hashlib.sha256((folder / 'proof.json').read_bytes()).hexdigest())
            shutil.copytree(first, second)
            self.assertEqual(materialize(second), 2)
            moved = json.loads((second / '.local/motion-console/assets/proof.json').read_bytes())
            self.assertEqual(Path(moved['asset']['path']), second / '.local/motion-console/assets/sample.bin')
            self.assertEqual((second / '.local/user-preset.json').read_bytes(), b'user-owned')

    def test_invalid_input_leaves_all_generated_documents_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = self.fixture(root)
            materialize(root)
            before = {p: p.read_bytes() for p in folder.glob('*.json')}
            (folder / 'sample.bin').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, '校验失败'):
                materialize(root)
            self.assertEqual(before, {p: p.read_bytes() for p in folder.glob('*.json')})

    def test_document_tamper_and_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            plan = json.loads((root / MANIFEST).read_bytes())
            name = '.local/motion-console/assets/proof.json'
            plan['documents'][name] += ' '
            (root / MANIFEST).write_bytes(encoded(plan))
            with self.assertRaisesRegex(ValueError, '身份不一致'):
                materialize(root)
            plan['documents']['../outside.json'] = '{}'
            (root / MANIFEST).write_bytes(encoded(plan))
            with self.assertRaisesRegex(ValueError, '越过安装目录'):
                materialize(root)


if __name__ == '__main__':
    unittest.main()
