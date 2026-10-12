"""Create local configuration without overwriting existing user settings."""
import json
from pathlib import Path
import shutil

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
        ff = root / 'runtime/ffmpeg'
        data = {
            'media_tools': {'ffmpeg': str(ff / 'ffmpeg.exe'), 'ffprobe': str(ff / 'ffprobe.exe')},
            'jobs': {'lock_root': '.locks', 'material_replication': {'episode_research_pack': {'consumer_root': '../../Haike_video'}},
                     'trusted_account_news': {'visual_ocr': {'ffmpeg_path': str(ff / 'ffmpeg.exe'), 'ffprobe_path': str(ff / 'ffprobe.exe')}}},
        }
        override.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Local templates created; existing user configuration preserved.')

if __name__ == '__main__':
    configure()
