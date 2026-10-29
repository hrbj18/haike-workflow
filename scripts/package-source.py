"""Package committed source, never the working directory or ignored secrets."""
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def main():
    subprocess.run([sys.executable, str(ROOT / 'scripts/check.py')], cwd=ROOT, check=True, timeout=120)
    status = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT, timeout=30)
    if status.strip():
        raise SystemExit('Commit or resolve source changes before packaging. Nothing was packaged.')
    revision = subprocess.check_output(['git', 'rev-parse', '--short=12', 'HEAD'], cwd=ROOT, timeout=30).decode().strip()
    dest = ROOT / 'dist' / f'haike-workflow-source-{revision}.zip'
    if dest.exists():
        raise SystemExit('Package already exists; refusing to overwrite.')
    dest.parent.mkdir(exist_ok=True)
    subprocess.run(['git', 'archive', '--format=zip', '--prefix=haike-workflow/', '-o', str(dest), 'HEAD'], cwd=ROOT, check=True, timeout=120)
    with dest.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    dest.with_suffix('.zip.sha256').write_text(f'{checksum}  {dest.name}\n', encoding='ascii')
    print(dest)

if __name__ == '__main__': main()
