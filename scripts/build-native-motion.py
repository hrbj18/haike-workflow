"""Derive a separately identified Mac adapter; retain every frozen source byte.

Imports, native tool orchestration and an explicit BT.709 encode binding change.
Drawing JS/TSX, semantic clocks, sampling and approval/claim guards stay inherited.
The generated files are checked in so their complete diff can be reviewed.
"""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
BACKLOT = ROOT / 'Haike_video/backlot'
MANIFEST = ROOT / 'Haike_video/config/motion-native-v1.json'
MODULES = (
    'motion_public_execution_v2', 'motion_public_observed_v2',
    'motion_public_dark_v2', 'motion_public_dark_remotion_v2', 'motion_public_production_v2',
    'motion_public_poster_execution_v3', 'motion_public_poster_observed_v3', 'motion_public_poster_production_v3',
    'motion_replay_public_v2', 'motion_replay_public_v2_bound', 'motion_replay_public_poster_v3_bound',
    'motion_public_paper_execution_v3', 'motion_public_paper_observed_v3', 'motion_public_paper_production_v3',
    'motion_replay_public_paper_v3_bound',
    'motion_public_quote_execution_v3', 'motion_public_quote_observed_v3', 'motion_public_quote_production_v3',
    'motion_replay_public_quote_v3_bound',
    'motion_replay_field_notes_render', 'motion_replay_field_notes_video',
    'motion_replay_numbered_02_05_production', 'motion_replay_numbered_02_05_full',
    'motion_knowledge_public_production_v3', 'studio_promo_phase_v3',
)
RENDERERS = (
    'numbered02-04-production-v1', 'field-notes-video-v1',
    'knowledge-reference-public-v3', 'promo-reference-phase-v3',
)


def native_name(name):
    return 'motion_native_' + name.removeprefix('motion_')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def function(text, name, replacement):
    tree = ast.parse(text)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(nodes) != 1:
        raise ValueError('Expected one frozen function: ' + name)
    node = nodes[0]
    rows = text.splitlines(keepends=True)
    return ''.join(rows[:node.lineno-1]) + replacement.strip() + '\n' + ''.join(rows[node.end_lineno:])


def derive(name, raw):
    text = raw.decode('utf8').replace('\r\n', '\n')
    for original in MODULES:
        changed = native_name(original)
        text = re.sub(r'(?m)(from backlot import )' + original + r'\b', r'\g<1>' + changed, text)
        text = text.replace('from backlot.' + original + ' import ', 'from backlot.' + changed + ' import ')
        # Only executable consumer references change; action provenance retains its
        # canonical consumer and remains checked against the original contract.
        text = text.replace("'backlot." + original + ".prepare'", "'backlot." + changed + ".prepare'")
    if name in MODULES[:19] and '_execution_v' in name:
        text = function(text, '_ffmpeg', "def _ffmpeg(request):\n    return native.binary('ffmpeg')")
        text = function(text, '_ffprobe', "def _ffprobe(request):\n    return native.binary('ffprobe')")
        original_runtime = f'''def runtime():
    from importlib import import_module
    result = import_module('backlot.{name}').runtime()
    return {{**result, 'platform_adapter': native.identity()}}
'''
        text = function(text, 'runtime', original_runtime)
        replacement = '''def environment(tool_root, dependency_root, ffmpeg_root=None, *, engine=None):
    component()
    if engine == 'dark-remotion/2':
        from backlot.motion_native_public_dark_remotion_v2 import environment as dark_environment
        return dark_environment(tool_root, dependency_root, ffmpeg_root)
    return native.environment(tool_root, dependency_root, ffmpeg_root, template=TEMPLATE)
'''
        text = function(text, 'environment', replacement)
        text = text.replace("tools = read_json(TEMPLATE / 'TOOLS.json')['tools']", "tools = native.tools()['tools']")
    text = text.replace("tools / 'node/node.exe'", "native.binary('node')")
    text = text.replace("tools / 'browser/chrome-headless-shell.exe'", "native.binary('browser')")
    if name in MODULES[19:]:
        text = text.replace("str(TEMPLATE/'render.cjs')", "str(native.render_script(TEMPLATE / 'render.cjs'))")
    if name in {'motion_replay_numbered_02_05_production', 'motion_replay_field_notes_video'}:
        method = 'source_identity' if 'numbered' in name else '_sources'
        text = function(text, method, f'''def {method}():
    from importlib import import_module
    return {{**import_module('backlot.{name}').{method}(), **native.source_files()}}
''')
    if name == 'motion_knowledge_public_production_v3':
        text = text.replace("{'sources':execution.source_identity(),", "{'sources':{**execution.source_identity(), **native.source_files()},")
    if name == 'studio_promo_phase_v3':
        text = text.replace("return {str(p.resolve()): sha(p) for p in paths}",
                            "return {**{str(p.resolve()): sha(p) for p in paths}, **{str(native.ROOT / p): h for p, h in native.source_files().items()}}")
    if name == 'motion_public_dark_remotion_v2':
        text = function(text, 'descriptor', '''def descriptor():
    from backlot import motion_public_dark_remotion_v2 as original
    return native.dark_descriptor(original.descriptor())
''')
        text = function(text, 'environment', '''def environment(tool_root, dependency_root, ffmpeg_root):
    descriptor()
    return native.environment(tool_root, dependency_root, ffmpeg_root, dark=True)
''')
        needle = "e.require(folder.resolve().is_relative_to(runtime_root.resolve()), '原renderer作业须在该隔离外供树内解析固定npm依赖')"
        if text.count(needle) != 1:
            raise ValueError('Frozen dark dependency-location guard changed')
        text = text.replace(needle, 'native.link_dependencies(generated, runtime_root)')
        text = text.replace("'--pixel-format=yuv444p'", "'--pixel-format=yuv444p','--color-space=bt709'")
    # Fixed module imports, not a global import hook or process-wide monkey patch.
    header = '# Generated by scripts/build-native-motion.py; review provenance in config/motion-native-v1.json.\n'
    tree = ast.parse(text)
    after = 0
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == '__future__':
            after = node.end_lineno
    if not after and tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant):
        after = tree.body[0].end_lineno
    rows = text.splitlines(keepends=True)
    text = header + ''.join(rows[:after]) + '\nfrom backlot import motion_native_runtime as native\n' + ''.join(rows[after:])
    ast.parse(text)
    return text.encode('utf8')


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--check', action='store_true'); args = parser.parse_args()
    rows = []
    for name in MODULES:
        source = BACKLOT / (name + '.py'); target = BACKLOT / (native_name(name) + '.py')
        data = source.read_bytes(); result = derive(name, data)
        if args.check:
            if not target.is_file() or target.read_bytes() != result:
                raise ValueError('Native derivation drift: ' + target.name)
        else:
            target.write_bytes(result)
        rows.append({'canonical_module': 'backlot.' + name, 'native_module': 'backlot.' + native_name(name),
                     'source': source.relative_to(ROOT).as_posix(), 'source_sha256': sha(data),
                     'derived': target.relative_to(ROOT).as_posix(), 'derived_sha256': sha(result)})
    renderers = []
    for name in RENDERERS:
        source = ROOT / 'Haike_video/templates' / name / 'render.cjs'
        target = source.with_name('render.macos.cjs')
        data = source.read_bytes()
        original = data.decode('utf8').replace('\r\n', '\n')
        if original.count('renderMedia({') != 1:
            raise ValueError('Expected one fixed renderMedia call: ' + name)
        result = ('// Native BT.709 binding; canonical drawing and renderer remain frozen.\n' +
                  original.replace('renderMedia({', "renderMedia({colorSpace:'bt709',")).encode('utf8')
        if args.check:
            if not target.is_file() or target.read_bytes() != result:
                raise ValueError('Native renderer drift: ' + name)
        else:
            target.write_bytes(result)
        renderers.append({'source': source.relative_to(ROOT).as_posix(), 'source_sha256': sha(data),
                          'derived': target.relative_to(ROOT).as_posix(), 'derived_sha256': sha(result)})
    document = {'schema': 'haike.motion-native-adapter/1', 'platform': 'darwin', 'adapter_version': '1.1.0',
                'changes': ['fixed native imports', 'pinned native binaries and npm', 'explicit local dependency resolution', 'actual BT.709 color conversion at native encode'],
                'preserved': ['canonical source hashes', 'drawing sources', 'action IDs and clocks', 'claim/approval guards', 'full encoding and sound'],
                'generator_sha256': sha(Path(__file__).read_bytes()),
                'runtime_sha256': sha((BACKLOT / 'motion_native_runtime.py').read_bytes()), 'modules': rows, 'renderers': renderers}
    encoded = (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode('utf8')
    if args.check:
        if MANIFEST.read_bytes() != encoded:
            raise ValueError('Native derivation provenance drift')
    else:
        MANIFEST.write_bytes(encoded)
    print(json.dumps({'native_modules': len(rows), 'canonical_sources_modified': 0, 'checked': args.check}))


if __name__ == '__main__':
    main()
