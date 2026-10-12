"""Fetch the explicitly requested small YuNet model; never TTS/ASR weights."""
import hashlib
import json
from pathlib import Path
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

def main():
    spec = json.loads((ROOT / 'config/external-models.json').read_text(encoding='utf-8'))['yunet']
    target = ROOT / spec['destination']
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == spec['sha256'] and target.with_suffix('.LICENSE').is_file():
        print('YuNet already installed and verified.')
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as directory:
        temporary = Path(directory) / target.name
        with urllib.request.urlopen(spec['url'], timeout=60) as response:
            data = response.read(4 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != spec['sha256']:
            raise SystemExit('YuNet checksum mismatch; model not installed.')
        temporary.write_bytes(data)
        with urllib.request.urlopen(spec['license_url'], timeout=60) as response:
            license_text = response.read(128 * 1024)
        if not license_text.strip(): raise SystemExit('Model license download is empty.')
        target.with_suffix('.LICENSE').write_bytes(license_text)
        temporary.replace(target)
    print('YuNet installed with source license and verified SHA256.')

if __name__ == '__main__': main()
