"""Build the tracked studio frontend and install it into this source checkout."""
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PREVIEWS = (
    'n1-cover.jpg', 'n1-presenter.jpg', 'n1-material.jpg',
    'n1-screenshot.jpg', 'n1-data.jpg', 'n1-sample.mp4',
    'template3-poster.png', 'presenter.png',
)


def remove_private_previews(destination):
    """Remove only retired private examples from an existing embedded build."""
    destination = destination.resolve()
    if not destination.is_relative_to(ROOT.resolve()):
        raise ValueError('Embedded frontend destination escapes this checkout.')
    for name in PRIVATE_PREVIEWS:
        target = destination / 'assets' / name
        if target.is_symlink() or not target.resolve().is_relative_to(destination):
            raise ValueError('Private preview path is not a regular checkout asset.')
        if target.exists():
            if not target.is_file():
                raise ValueError('Private preview path is not a file.')
            target.unlink()


def main():
    frontend = ROOT / 'prototypes/haike-avatar-generator'
    for name in PRIVATE_PREVIEWS:
        if (frontend / 'public/assets' / name).exists():
            raise SystemExit('Private preview found in public assets; preserve it under .local before building.')
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
    remove_private_previews(destination)
    shutil.copytree(source, destination, dirs_exist_ok=True)
    print(f'Installed studio frontend: {destination}')


if __name__ == '__main__':
    main()
