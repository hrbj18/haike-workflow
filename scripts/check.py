"""Offline source-delivery checks. No imports of business services or network calls."""
import ast
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    'AGENTS.md', 'README.md', 'SOURCE-PROVENANCE.json',
    'Haike_video/config.yaml', 'Haike_video/.env.example',
    'Haike_video/backlot/server.py', 'Haike_video/backlot/work_catalog.py',
    'Haike_video/backlot/material_commentary.py', 'Haike_video/backlot/material_library.py',
    'Haike_video/remotion-composer/package-lock.json',
    'Haike_video/content/templates/project.yaml',
    'copy_skill/copy_skill-main/uv.lock',
    'copy_skill/copy_skill-main/config/content_intelligence.json',
    'copy_skill/copy_skill-main/docs/tasks/2026-09-16-episode-research-pack-v1.md',
    'creatorhub/app/main.py', 'creatorhub/app/publish_contract.py',
    'creatorhub/config.example.yaml', 'creatorhub/package-lock.json',
    'Haike-Videohub/contracts/layout.json', 'Haike-Videohub/contracts/publish-v2.md',
    'Haike-Videohub/agent-runbooks/模板图文视频.md',
]
FORBIDDEN_PARTS = {'.git', '.venv', 'node_modules', '__pycache__', '.backlot', '.workbuddy',
                   '.portable', '.local', 'private-transfer', 'browser_data', 'runtime', 'dist', 'test_artifacts'}

def check_paths(root, names):
    errors = []
    for name in names:
        path = Path(name)
        if path.is_absolute() or '..' in path.parts:
            errors.append(f'Unsafe source path: {name}')
            continue
        if any(p in FORBIDDEN_PARTS or p.endswith('_user_data_dir') for p in path.parts):
            errors.append(f'Runtime/state file: {name}')
        lower = path.name.lower()
        if (lower.startswith('.env') and lower != '.env.example') or lower.endswith(('.pem','.key','.db','.sqlite','.log','.mp4','.mp3','.wav','.onnx')) or '.bak' in lower:
            errors.append(f'Private/generated file: {name}')
        if name == 'creatorhub/config.yaml' or lower == 'content_intelligence.local.json' or ('cookies' in lower and path.suffix == '.txt'):
            errors.append(f'Local credentials/config: {name}')
        file = root / path
        if file.is_symlink() or (file.exists() and not file.resolve().is_relative_to(root.resolve())):
            errors.append(f'Outside source tree: {name}')
        if not file.is_file():
            errors.append(f'Missing source: {name}')
        elif file.stat().st_size > 40 * 1024 * 1024:
            errors.append(f'Source exceeds project 40 MiB budget: {name}')
    return errors

def source_names(root):
    result = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root, capture_output=True, timeout=30)
    if result.returncode == 0:
        return sorted(set(x for x in result.stdout.decode('utf-8').split('\0') if x))
    # Source ZIP has no .git; check its files before setup creates ignored state.
    return sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()
                  and not any(x in FORBIDDEN_PARTS or x in {'data','cache','temp','models','third_party','output','projects','renders','.p','.pytest_cache'} for x in p.relative_to(root).parts)
                  and not p.name.startswith('.env.local') and p.name != 'content_intelligence.local.json'
                  and p.relative_to(root).as_posix() != 'creatorhub/config.yaml')

def main():
    names = source_names(ROOT)
    errors = check_paths(ROOT, names)
    for name in REQUIRED:
        if name not in names: errors.append(f'Required file not in delivery: {name}')
    for module in ['Haike_video','creatorhub','copy_skill/copy_skill-main','Haike-Videohub']:
        if (ROOT / module / '.git').exists(): errors.append(f'Nested Git metadata: {module}')
    layout = json.loads((ROOT / 'Haike-Videohub/contracts/layout.json').read_text(encoding='utf-8'))
    if layout['repos']['copyskill']['path'] != 'copy_skill/copy_skill-main': errors.append('CopySkill layout changed')
    compiled = 0
    for name in names:
        file = ROOT / name
        if file.suffix == '.py' and not name.startswith(('Haike_video/.agents/','Haike_video/skills/')):
            try: ast.parse(file.read_text(encoding='utf-8-sig'), filename=name)
            except (SyntaxError, UnicodeError) as error: errors.append(f'Python syntax: {name}: {error}')
            compiled += 1
    cfg = json.loads((ROOT / 'copy_skill/copy_skill-main/config/content_intelligence.json').read_text(encoding='utf-8'))
    def walk(value, key='config'):
        if isinstance(value, dict):
            for k, v in value.items(): walk(v, key + '.' + k)
        elif isinstance(value, list):
            for v in value: walk(v, key)
        elif isinstance(value, str) and re.match(r'^[A-Za-z]:[/\\]', value): errors.append(f'Machine-specific path: {key}')
    walk(cfg)
    if errors:
        print('\n'.join(errors))
        return 1
    print(f'Source checks passed: {len(names)} files, {compiled} Python files; required layout/config present.')
    return 0

if __name__ == '__main__': sys.exit(main())
