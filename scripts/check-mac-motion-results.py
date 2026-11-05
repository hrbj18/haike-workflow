"""Refuse Mac release if a shard/architecture/style is missing or duplicated."""
from pathlib import Path
import argparse
import json

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--root', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    expected = {(r['template_id'], r['version']) for r in json.loads((ROOT / 'Haike_video/config/motion-preferred-production.json').read_text('utf8'))['templates']}
    groups = {'arm64': [], 'x86_64': []}; sources = set(); derivations = set(); specs = set(); shards = set()
    for path in args.root.rglob('summary-*.json'):
        document = json.loads(path.read_text('utf8'))
        assert document['ok'] is True and document['arch'] in groups and document['paid_calls'] == 0
        key = (document['arch'], document['shard']); assert key not in shards; shards.add(key)
        assert document['template_count'] == len(document['results']) == 6 and document['shards'] == 3
        for row in document['results']:
            assert row['ok'] and row['full_decode'] == 'pass' and row['moving_picture']
            assert row['frames'] > 0 and row['full_duration'] > 10 and row['video_bitrate'] >= 20_000_000 and row['audio_peak_dbfs'] > -70
            assert len(row['encoded_sha256']) == len(row['contacts_sha256']) == 64
        groups[document['arch']].extend(document['results'])
        sources.add(document['source_commit']); derivations.add(document['derivation_sha256']); specs.add(document['runtime_spec_sha256'])
    for arch, rows in groups.items():
        assert len(rows) == 18 and {(r['template_id'], r['version']) for r in rows} == expected, 'Incomplete native motion validation: ' + arch
    assert len(sources) == len(derivations) == len(specs) == 1 and None not in sources
    result = {'ok': True, 'architectures': {arch: {'passed': 18, 'results': rows} for arch, rows in groups.items()},
              'source_commit': next(iter(sources)), 'derivation_sha256': next(iter(derivations)), 'runtime_spec_sha256': next(iter(specs)),
              'scope': '36 complete native synthetic renderer exports; visual contact review, real providers and colleague physical machine are separate', 'paid_calls': 0}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps({'ok': True, 'arm64': '18/18', 'x86_64': '18/18', 'source_commit': result['source_commit']}))


if __name__ == '__main__':
    main()
