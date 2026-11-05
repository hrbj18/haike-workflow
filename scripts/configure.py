"""Create local configuration without overwriting existing user settings."""
import json
from pathlib import Path
import shutil
import os
import sys

ROOT = Path(__file__).resolve().parents[1]

def configure(root=ROOT):
    for source, target in [
        ('Haike_video/.env.example', 'Haike_video/.env.local'),
        ('creatorhub/config.example.yaml', 'creatorhub/config.yaml'),
    ]:
        if not (root / target).exists():
            shutil.copyfile(root / source, root / target)
    copy = root / 'copy_skill/copy_skill-main'
    override = copy / 'config/content_intelligence.local.json'
    if not override.exists():
        ffmpeg = os.environ.get('FFMPEG_BINARY') or str(root / 'runtime/ffmpeg/bin' / ('ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg'))
        ffprobe = os.environ.get('FFPROBE_BINARY') or str(root / 'runtime/ffmpeg/bin' / ('ffprobe.exe' if sys.platform == 'win32' else 'ffprobe'))
        data = {
            'media_tools': {'ffmpeg': ffmpeg, 'ffprobe': ffprobe},
            'jobs': {'lock_root': '.locks', 'material_replication': {'episode_research_pack': {'consumer_root': '../../Haike_video'}},
                     'trusted_account_news': {'visual_ocr': {'ffmpeg_path': ffmpeg, 'ffprobe_path': ffprobe}}},
        }
        override.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Local templates created; existing user configuration preserved.')

if __name__ == '__main__':
    configure()
