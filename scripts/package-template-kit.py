"""Build a private colleague handoff, not a public source release or Windows bundle.

Input is an explicit, locally reviewed media/render map. No accounts/configuration
directories are copied. Output directory must be new.
"""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MEDIA = {'.mp4', '.mov', '.webm', '.wav', '.mp3', '.png', '.jpg', '.jpeg', '.svg', '.webp'}


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def build(destination, mapping, serif):
    destination.mkdir(parents=True, exist_ok=False)
    records = []
    def copy(source, relative):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target

    kit = ROOT / 'Haike_video/template-kit'
    copy(kit / 'README.md', 'README.md')
    copy(kit / 'setup.command', 'setup.command')
    copy(kit / 'kit.py', 'tools/kit.py')
    copy(kit / 'font-loader.ts', 'tools/font-loader.ts')
    for p in kit.iterdir():
        if p.is_file() and p.suffix in ('.md', '.py', '.ts', '.command'):
            copy(p, 'source/Haike_video/template-kit/' + p.name)
    fontroot = ROOT / 'Haike_video/remotion-composer/a2e/public/fonts'
    copy(fontroot / 'NotoSansSC.ttf', 'fonts/NotoSansSC.ttf')
    copy(fontroot / 'LICENSE.md', 'fonts/NotoSansSC-LICENSE.md')
    copy(serif / 'NotoSerifSC.ttf', 'fonts/NotoSerifSC.ttf')
    copy(serif / 'NotoSerifSC-OFL.txt', 'fonts/NotoSerifSC-OFL.txt')
    copy(ROOT / 'Haike_video/LICENSE', 'LICENSES/Haike_video-LICENSE')
    for name in ('package.json', 'package-lock.json'):
        copy(ROOT / 'Haike_video/remotion-composer' / name, name)
    package = read(destination / 'package.json')
    package['scripts'] = {'check': 'python3 tools/kit.py doctor', 'list': 'python3 tools/kit.py list'}
    (destination / 'package.json').write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding='utf-8')
    remotion_license = ROOT / 'Haike_video/remotion-composer/node_modules/remotion/LICENSE.md'
    if not remotion_license.is_file():
        raise ValueError('Install locked Remotion dependencies before packaging its license')
    copy(remotion_license, 'LICENSES/Remotion-LICENSE.md')
    # Current visual sources and their portable documentation tree.
    for folder in ('Haike_video/templates', 'Haike-Videohub/agent-runbooks', 'Haike-Videohub/contracts'):
        for p in (ROOT / folder).rglob('*'):
            if p.is_file() and p.suffix.lower() in {'.md', '.json', '.py', '.ts', '.tsx', '.css', '.svg', '.png', '.wav'}:
                copy(p, 'source/' + p.relative_to(ROOT).as_posix())
    for folder in ('Haike_video/backlot', 'Haike_video/lib', 'Haike_video/scripts', 'Haike_video/tools'):
        for p in (ROOT / folder).rglob('*.py'):
            if not any(part in ('__pycache__', 'node_modules', '.venv') for part in p.parts):
                copy(p, 'source/' + p.relative_to(ROOT).as_posix())
    for name in ('Haike_video/docs/高质量数字人工作流.md', 'Haike_video/docs/VIDEO_QUALITY.md', 'Haike_video/skills/INDEX.md'):
        copy(ROOT / name, 'source/' + name)
    for p in (ROOT / 'prototypes/haike-avatar-generator/src').rglob('*'):
        if p.is_file() and p.suffix in ('.js', '.jsx', '.css'):
            copy(p, 'source/' + p.relative_to(ROOT).as_posix())
    # Original DSP tracks needed to remix new store-manager episodes.
    musicroot = ROOT / '.local/codex-runs/investment-full-three-20261021/audio'
    for name in ('PROVENANCE.json', 'SOUND-PLAN.md'):
        if (musicroot / name).is_file():
            copy(musicroot / name, 'sound/' + name)
    for sub in ('music', 'sfx'):
        for p in (musicroot / sub).rglob('*'):
            if p.is_file() and (p.suffix == '.wav' or p.name == 'PROVENANCE.json'):
                copy(p, 'sound/' + p.relative_to(musicroot).as_posix())

    catalog = read(ROOT / 'Haike_video/templates/library.json')['templates']
    base = [
        ('avatar-safe-circle-v1', '基础01 · 圆框口播', 'studio-avatar-v1'),
        ('avatar-full-width-v2', '基础02 · 全宽讲解', 'studio-avatar-v1'),
        ('avatar-template3-card-3x4-v001', '基础03 · 卡片讲解', 'avatar-card-explainer-v3'),
        ('avatar-investment-a-v6', '基础06 · 招商A', 'avatar-investment-a-v6'),
        ('avatar-deepblue-n1', '基础 · 深蓝视窗N1', 'avatar-deepblue-n1'),
    ]
    for identity, name, family in base:
        catalog.append({'id': identity, 'name': name, 'group': '基础口播', 'status': '源码与原生入口',
                        'runbook': 'Haike_video/templates/TEMPLATE-LIBRARY.md', 'family': family})
    for number, name in zip(range(22, 27), ['橙紫开幕', '冰蓝樱桃证据', '酸橙深蓝错层', '玫粉孔雀接力', '钴蓝杏黄满场']):
        p = ROOT / f'Haike_video/templates/store-opening-v1/variants/{number}/video-template-spec.json'
        spec = read(p)
        catalog.append({'id': spec['template_id'], 'name': f'开业{number} · {name}', 'group': '店长账号',
                        'status': '规格与源码（新模板，依规格验收）', 'family': 'store-opening-v1',
                        'runbook': 'Haike_video/templates/store-opening-v1/README.md',
                        'spec': p.relative_to(ROOT).as_posix()})

    pool = {}
    def asset(path):
        signature = sha(path)
        relative = 'assets/' + signature + path.suffix.lower()
        if relative not in pool:
            copy(path, relative)
            pool[relative] = {'file': relative, 'sha256': signature, 'bytes': path.stat().st_size}
        return pool[relative]

    jobs = []
    for identity, item in read(mapping).items():
        if not re.fullmatch(r'[a-zA-Z0-9-]+', identity):
            raise ValueError('Invalid example id')
        sample = Path(item['sample'])
        if sha(sample) != item['sha256']:
            raise ValueError('Sample changed: ' + identity)
        copy(sample, 'previews/' + identity + '.mp4')
        poster = Path(item['poster']) if item.get('poster') else None
        if poster and poster.is_file():
            copy(poster, 'previews/' + identity + poster.suffix.lower())
        row = next(i for i in catalog if i['id'] == identity)
        row['sample'] = 'previews/' + identity + '.mp4'
        row['poster'] = 'previews/' + identity + poster.suffix.lower() if poster else None
        folder = Path(item['render'])
        prefix = 'examples/' + identity
        for p in folder.iterdir():
            if p.is_file() and (p.suffix in ('.ts', '.tsx', '.css') or p.name in ('layout.json', 'tokens.json', 'palettes.json')):
                copy(p, prefix + '/source/' + p.name)
        copy(folder / 'props.json', prefix + '/props.json')
        entry = (folder / 'index.tsx').read_text(encoding='utf-8-sig')
        composition = re.findall(r'<Composition\s+id=["\x27]([^"\x27]+)', entry)[0]
        props = read(folder / 'props.json')
        assets = {p.relative_to(folder / 'public').as_posix(): asset(p)
                  for p in (folder / 'public').rglob('*') if p.is_file() and p.suffix.lower() in MEDIA}
        info = json.loads(subprocess.check_output([shutil.which('ffprobe'), '-v', 'error', '-show_streams',
            '-of', 'json', str(sample)], encoding='utf-8'))
        video = next(s for s in info['streams'] if s['codec_type'] == 'video')
        a, b = video['r_frame_rate'].split('/')
        audio = props.get('audioSrc') or props.get('audio')
        if audio and audio not in assets:
            raise ValueError('Missing master audio ' + identity)
        job = {'id': identity, 'source': prefix + '/source', 'entry': 'index.tsx',
               'props': prefix + '/props.json', 'assets': assets, 'composition': composition,
               'audio': audio, 'width': video['width'], 'height': video['height'],
               'fps': int(a) / int(b), 'frames': int(video['nb_frames']),
               'reference_sha256': item['sha256'], 'source_version': 'frozen-example',
               'target_font_profile': 'portable-ofl-v1'}
        jobs.append(job)
        print('Packed example:', identity, flush=True)

    data = {'contract': 'offline-template-reproduction-v1', 'date': '2026-10-25',
            'mac_physical_test': 'pending', 'catalog': catalog, 'jobs': jobs,
            'source_families': sorted(p.name for p in (ROOT / 'Haike_video/templates').iterdir() if p.is_dir()),
            'private_media': 'included for user-authorized colleague handoff only',
            'credentials': 'not included', 'video_reencoding_during_packaging': False}
    (destination / 'KIT.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    cards = []
    for row in catalog:
        title = html.escape(row['name'])
        preview = (f'<video controls preload="none" poster="{html.escape(row.get("poster") or "")}" src="{html.escape(row["sample"])}"></video>'
                   if row.get('sample') else '<div class="empty">源码与视觉说明<br>当前未打包实例预览</div>')
        command = f'python3 tools/kit.py render {row["id"]}' if any(j['id'] == row['id'] for j in jobs) else '先按手册准备本期输入并验收'
        cards.append(f'<article><h2>{title}</h2><p>{html.escape(row["status"])}</p>{preview}<p><a href="source/{html.escape(row["runbook"])}">打开视觉手册</a></p><code>{command}</code></article>')
    page = '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>海客全模板 Mac复刻包</title><style>body{font:16px/1.6 system-ui;background:#edf1f6;color:#203149;margin:28px}h1{font-size:32px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:20px}article{background:white;padding:18px;border-radius:12px}h2{font-size:19px}video{width:100%;height:330px;background:#172233}code{overflow-wrap:anywhere;font-size:12px}.empty{height:330px;display:grid;place-content:center;background:#e0e7ef}input{padding:12px;width:300px;max-width:90%;margin:10px 0 25px}</style><h1>海客全模板 · Mac复刻包</h1><p>先读 <a href="README.md">Mac使用说明</a>。实例保留原画质；新片使用当前源码。Mac真机验收待执行。</p><input aria-label="搜索模板" placeholder="搜索编号、配色或名称" oninput="document.querySelectorAll(\'article\').forEach(a=>a.hidden=!a.textContent.includes(this.value))"><main>'+''.join(cards)+'</main>'
    (destination / 'index.html').write_text(page, encoding='utf-8')
    (destination / 'AGENTS.md').write_text('# Mac模板包入口\n\n先读根README.md、KIT.json和所选Runbook。此处是offline-template-reproduction-v1，不运行source内Windows安装脚本。examples是历史冻结实例，source是当前模板。无密钥、无自动云调用、无发布授权。严格记录字体替代和Mac真机验收状态。\n', encoding='utf-8')
    # Initial manifest; refresh only after final validation documentation is added.
    for p in sorted(destination.rglob('*')):
        if p.is_file():
            records.append({'file': p.relative_to(destination).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)})
    (destination / 'SHA256-MANIFEST.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'folder': str(destination), 'catalog': len(catalog), 'jobs': len(jobs),
                      'unique_assets': len(pool), 'files': len(records)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--media-map', type=Path, required=True)
    p.add_argument('--serif-font-dir', type=Path, required=True)
    a = p.parse_args()
    build(a.output.resolve(), a.media_map.resolve(), a.serif_font_dir.resolve())
