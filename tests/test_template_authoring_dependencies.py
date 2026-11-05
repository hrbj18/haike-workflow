"""The authoring instructions must work from the bytes shipped by Git."""
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TemplateAuthoringDependenciesTests(unittest.TestCase):
    def test_project_skills_and_all_fixed_references_match_their_contract(self):
        contract = json.loads((ROOT / 'Haike-Videohub/contracts/template-authoring-dependencies-v1.json').read_text(encoding='utf-8'))
        self.assertEqual(contract['path_base'], 'workspace_root')
        for skill in contract['skills']:
            with self.subTest(skill=skill['id']):
                data = (ROOT / skill['path']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), skill['sha256'])
                references = skill.get('references')
                if not references:
                    continue
                manifest = (ROOT / references['integrity_manifest']).read_bytes()
                self.assertEqual(hashlib.sha256(manifest).hexdigest(), references['integrity_manifest_sha256'])
                files = json.loads(manifest)['files']
                self.assertEqual(len(files), 99)
                for name, expected in files.items():
                    with self.subTest(reference=name):
                        path = ROOT / references['root'] / name
                        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)
        for name, value in contract['project'].items():
            if isinstance(value, str):
                with self.subTest(project=name):
                    self.assertTrue((ROOT / value).exists(), value)


if __name__ == '__main__':
    unittest.main()
