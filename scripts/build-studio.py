"""Build the tracked studio frontend and install it into this source checkout."""
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    frontend = ROOT / 'prototypes/haike-avatar-generator'
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    if not npm:
        raise SystemExit('Install Node.js 22+ and npm, then rerun this command.')
    environment = dict(os.environ, HAIKE_EMBED_BASE='/ui/avatar-generator/')
    subprocess.run([npm, 'ci', '--no-audit', '--no-fund'], cwd=frontend, env=environment, check=True)
    subprocess.run([npm, 'run', 'build'], cwd=frontend, env=environment, check=True)
    source = frontend / 'dist/client'
    if not (source / 'index.html').is_file():
        raise SystemExit('Frontend build did not produce index.html.')
    destination = ROOT / 'Haike_video/backlot/ui/avatar-generator'
    shutil.copytree(source, destination, dirs_exist_ok=True)
    print(f'Installed studio frontend: {destination}')


if __name__ == '__main__':
    main()
