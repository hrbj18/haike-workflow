"""Verify the immutable template release; episode data stays outside this set."""
from pathlib import Path
import hashlib,json

HERE=Path(__file__).resolve().parent
def verify(root=None):
    root=Path(root) if root is not None else HERE
    release=json.loads((root/'release.json').read_bytes())
    if release.get('template_id')!='nana-mint-explainer-v1' or release.get('version')!='1.0.0':
        raise ValueError('动效模板3版本清单无效，请读取定稿记录。')
    for name,expected in release['files'].items():
        path=root/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('动效模板3定稿文件已改变：'+name+'；恢复定稿或另建版本，不覆盖哈希掩盖改动。')
    return release

def validate_style(content):
    profile=json.loads((HERE/'template-profile.json').read_bytes())
    if content['palette']!=profile['palette']:
        raise ValueError('动效模板3固定薄荷色板；改设计须另建版本。')

if __name__=='__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    print('动效模板3 v'+verify()['version']+' 定稿文件校验通过。')
