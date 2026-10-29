"""Vendor the installed, pinned Hallmark theme references, without running them."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '7ec868225c6caa040558c321ee0fefa0e73f83a8'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skill-dir', type=Path, required=True)
    parser.add_argument('--license-file', type=Path, required=True)
    args = parser.parse_args()
    skill = args.skill_dir.resolve()
    target = ROOT / 'Haike_video/design/hallmark'
    labels = json.loads((target / 'labels.zh.json').read_text(encoding='utf-8'))
    index = json.loads((skill / 'references/themes/index.json').read_text(encoding='utf-8'))
    themes = index['themes']
    if len(themes) != 48 or {t['slug'] for t in themes} != set(labels):
        raise SystemExit('Theme catalog and Chinese labels differ; review the upstream version first.')
    if 'version: 2.0.0' not in (skill / 'SKILL.md').read_text(encoding='utf-8'):
        raise SystemExit('Unexpected installed skill version.')
    files = {}
    for theme in themes:
        for key in ('file', 'picture'):
            source = (skill / theme[key]).resolve()
            if not source.is_relative_to(skill / 'references/themes') or not source.is_file():
                raise SystemExit('Missing or unsafe theme reference.')
            out = target / 'themes' / source.name
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, out)
            files[out.relative_to(target).as_posix()] = hashlib.sha256(out.read_bytes()).hexdigest()
        theme.update(name_zh=labels[theme['slug']][0], summary_zh=labels[theme['slug']][1],
                     video_use_zh=labels[theme['slug']][2])
    license_text = args.license_file.read_text(encoding='utf-8')
    if 'MIT License' not in license_text or 'Hallmark contributors' not in license_text:
        raise SystemExit('Expected upstream MIT attribution.')
    (target / 'LICENSE').write_text(license_text, encoding='utf-8')
    payload = {'version': '2.0.0', 'source_commit': COMMIT,
               'source_url': 'https://github.com/Nutlope/hallmark',
               'scope': 'visual-reference; not 48 rendered video templates', 'themes': themes}
    (target / 'catalog.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    rows = ['# Hallmark 48种风格', '', '原作者主题名称保留；中文说明和视频场景为本项目建议。原图为网页参考，成片需另行适配。', '',
            '| 风格 | 视觉特征 | 视频场景建议 |', '|---|---|---|']
    for t in themes:
        rows.append(f"| [{t['name']} · {t['name_zh']}](themes/{t['slug']}.jpg) | {t['summary_zh']} | {t['video_use_zh']} |")
    (target / 'CATALOG.md').write_text('\n'.join(rows) + '\n', encoding='utf-8')
    for name in ('catalog.json', 'labels.zh.json', 'LICENSE'):
        files[name] = hashlib.sha256((target / name).read_bytes()).hexdigest()
    provenance = {'source_commit': COMMIT, 'installed_skill_sha256': hashlib.sha256((skill / 'SKILL.md').read_bytes()).hexdigest(),
                  'files': files}
    (target / 'UPSTREAM.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'themes': len(themes), 'vendored_files': len(files), 'target': str(target)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
