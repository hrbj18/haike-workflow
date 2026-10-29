"""Project-owned presenter composition captured before final review and freezing.

The official package, native HTML and native preview receipts stay unchanged.
A separate capture layer uses imported talk frames and the same output clock.
"""
import json
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import threading

from backlot.studio import atomic_private
from backlot.work_catalog import WorkError, read_json, sha

SCRIPT = Path(__file__).resolve().parents[1] / 'templates/motiongit-console-v1/presenter.js'
MODES = {'auto', 'opening', 'closing', 'hidden'}


def identity():
    """Changes to the composition layer require a separate prepared version."""
    return {'adapter_sha256': sha(__file__), 'script_sha256': sha(SCRIPT)}


def policy(console, frames):
    mode = console.get('presenterMode', 'auto')
    if mode not in MODES:
        raise WorkError('控制台人物出镜方式无效')
    if mode != 'auto' and console.get('layout') != 'portrait':
        raise WorkError('开场、结尾和隐藏人物当前只支持4:5')
    segments = console.get('segments', [])
    if mode == 'opening':
        start, end = 0, min(segments[0]['durationFrames'], 300)
    elif mode == 'closing':
        start, end = frames - min(segments[-1]['durationFrames'], 300), frames
    else:
        start, end = 0, 0
    return {'schema': 'haike.console-presenter/1', 'mode': mode, 'startFrame': start,
            'endFrame': end, 'fps': 60, 'diameter': 440, 'left': 320, 'top': 952,
            'fadeFrames': 15}


def install(project, console, frames):
    settings = policy(console, frames)
    if settings['mode'] == 'auto':
        return
    folder = Path(project) / 'project'
    composition = Path(project) / 'haike-composition'
    index = folder / 'index.html'
    receipt = Path(project) / 'haike-presenter.json'
    source = SCRIPT.read_bytes()
    config = ('window.HAIKE_PRESENTER=' + json.dumps(settings, separators=(',', ':')) + ';\n').encode()
    expected = {'policy': settings, 'script_sha256': sha(SCRIPT)}
    if receipt.exists():
        old = read_json(receipt)
        if (old.get('policy') != settings or old.get('script_sha256') != sha(SCRIPT)
                or old.get('index_sha256') != sha(index)
                or (composition / 'haike-presenter.js').read_bytes() != source
                or (composition / 'haike-presenter-config.js').read_bytes() != config):
            raise WorkError('出镜方案已变化，请另建本期预览版本')
        return
    if not index.is_file():
        raise WorkError('须先通过官方有界预览生成原生画面工程')
    expected['original_index_sha256'] = sha(index)
    composition.mkdir(exist_ok=True)
    (composition / 'haike-presenter.js').write_bytes(source)
    (composition / 'haike-presenter-config.js').write_bytes(config)
    # Load the extension at capture time. Native HTML and its official receipt
    # remain byte-identical and can still use the official sound renderer.
    expected['index_sha256'] = sha(index)
    atomic_private(receipt, expected)


@contextmanager
def capture_page(project, browser):
    from playwright.sync_api import sync_playwright
    folder=Path(project)/'project'
    composition=Path(project)/'haike-composition'
    receipt=read_json(Path(project)/'haike-presenter.json')
    if receipt.get('script_sha256')!=sha(composition/'haike-presenter.js') or receipt.get('index_sha256')!=sha(folder/'index.html'):
        raise WorkError('人物画面工程与审核版本不一致')
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(folder)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as pw:
            launched=pw.chromium.launch(executable_path=str(browser) if browser else None,headless=True,
                args=['--allow-file-access-from-files','--disable-dev-shm-usage'])
            try:
                page=launched.new_page(viewport={'width':1080,'height':1920},device_scale_factor=1)
                page.goto(f'http://127.0.0.1:{server.server_port}/index.html',wait_until='load')
                page.evaluate('async () => { await window.READY; await document.fonts.ready; }')
                page.add_script_tag(content='window.HAIKE_PRESENTER='+json.dumps(receipt['policy'])+';')
                page.add_script_tag(path=str(composition/'haike-presenter.js'))
                page.evaluate('async () => await window.READY')
                yield page
            finally:launched.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)


def preview(project, times, browser):
    project=Path(project);native=read_json(project/'preview.json');target=project/'haike-preview.json'
    receipt=read_json(target)
    if receipt:
        if receipt.get('times_s')!=times or receipt.get('native_preview_sha256')!=sha(project/'preview.json'):
            raise WorkError('人物预览来源已变化，请重新准备')
        return target
    folder=project/'haike-stills';folder.mkdir(exist_ok=True)
    rows=[{**row,'label':'原生基础画面（对照）'} for row in native['stills']]
    with capture_page(project,browser) as page:
        for i,t in enumerate(times):
            page.evaluate('async t => { await window.renderAt(t); await document.fonts.ready; }',t)
            path=folder/f'{i:03d}.png';page.screenshot(path=str(path),animations='allow')
            rows.append({'path':path.relative_to(project).as_posix(),'sha256':sha(path),'label':'调整后的交付画面','at':t})
    atomic_private(target,{'schema':'haike.console-presenter-preview/1','reviewed':False,
        'parameterSha256':native['parameterSha256'],'sourceLockSha256':native['sourceLockSha256'],
        'native_preview_sha256':sha(project/'preview.json'),'native_count':len(native['stills']),
        'times_s':times,'stills':rows,'presenter':read_json(project/'haike-presenter.json')})
    return target


def render(project, output, expected, ffmpeg, browser):
    """Queue-owned visual pass; official native audio remains the sound source."""
    output=Path(output);log_path=output.with_suffix('.log')
    command=[str(ffmpeg),'-nostdin','-y','-v','error','-f','image2pipe','-vcodec','png','-framerate','60',
        '-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','14','-pix_fmt','yuv420p',str(output)]
    with log_path.open('wb') as log, capture_page(project,browser) as page:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stderr=log,stdout=log,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            for frame in range(expected['frames']):
                page.evaluate('async t => await window.renderAt(t)',frame/expected['fps'])
                process.stdin.write(page.screenshot(type='png',animations='allow'))
            process.stdin.close()
            if process.wait(timeout=120)!=0:raise WorkError('人物画面导出失败，请保留本期日志')
        except BaseException:
            if process.poll() is None:process.terminate();process.wait(timeout=15)
            raise
    atomic_private(output.with_suffix('.json'),{'schema':'haike.console-presenter-render/1',
        'output_sha256':sha(output),'frames':expected['frames'],'fps':expected['fps'],
        'presenter':read_json(Path(project)/'haike-presenter.json'),'audio':'none; official native audio used by parent queue'})
    return output
