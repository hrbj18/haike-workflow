"""Native installation/HTTP/render proof. No provider call or publication."""
from pathlib import Path
import importlib.util
import json
import os
import subprocess
import sys
import urllib.request
import asyncio

ROOT = Path(__file__).resolve().parents[1]


def main():
    spec = importlib.util.spec_from_file_location('mac_deployment', ROOT / 'scripts/mac-deploy.py')
    deploy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deploy)
    arch = deploy.architecture()
    env = deploy.environment(arch)
    browser_probe = '''import asyncio
from patchright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<h1>Local deployment test</h1>')
        assert await page.locator('h1').inner_text() == 'Local deployment test'
        print(browser.version)
        await browser.close()
asyncio.run(main())
'''
    browser_version = subprocess.check_output([str(deploy.python_for('creatorhub')), '-c', browser_probe],
                                              env=env, text=True, timeout=60).strip()
    expected_browser = next(row['version'] for row in deploy.read(deploy.SPEC)['assets'] if row['id'] == 'browser' and row['arch'] == arch)
    assert browser_version == expected_browser
    crawler_py = deploy.python_for('copy_skill/copy_skill-main/third_party/MediaCrawler')
    collector_version = None
    if crawler_py.is_file():
        collector_version = subprocess.check_output([str(crawler_py), '-c', browser_probe.replace('patchright.async_api', 'playwright.async_api')],
                                                   env=env, text=True, timeout=60).strip()
        assert collector_version == expected_browser
    folder = ROOT / '.local/mac-smoke'
    folder.mkdir(parents=True, exist_ok=True)
    cli = ROOT / 'Haike_video/remotion-composer/node_modules/.bin/remotion'
    movie = folder / 'template-video.mp4'
    subprocess.run([str(cli), 'render', 'src/index.tsx', 'HeroTitle', str(movie), '--frames=0-29',
                    '--scale=0.5', '--concurrency=1', '--log=error',
                    '--browser-executable=' + env['REMOTION_BROWSER_EXECUTABLE']],
                   cwd=ROOT / 'Haike_video/remotion-composer', env=env, check=True, timeout=900)
    output = folder / 'installation-test.mp4'
    subprocess.run([env['FFMPEG_BINARY'], '-y', '-v', 'error', '-i', str(movie), '-f', 'lavfi',
                    '-i', 'sine=frequency=440:sample_rate=48000:duration=1', '-c:v', 'copy',
                    '-c:a', 'aac', '-shortest', str(output)], check=True, env=env)
    probe = json.loads(subprocess.check_output([env['FFPROBE_BINARY'], '-v', 'error', '-show_streams',
                                               '-show_format', '-of', 'json', str(output)], env=env))
    assert {s['codec_type'] for s in probe['streams']} >= {'audio', 'video'}
    framehashes = subprocess.check_output([env['FFMPEG_BINARY'], '-v', 'error', '-i', str(output),
                                           '-map', '0:v:0', '-f', 'framemd5', '-'], env=env, text=True)
    hashes = [line.rsplit(',', 1)[-1].strip() for line in framehashes.splitlines() if not line.startswith('#')]
    assert len(set(hashes)) > 1, 'Rendered composition must actually move'
    result = deploy.start(type('Args', (), {'port': 18456, 'publisher_port': 18457, 'no_browser': True})())
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = result['url'].removesuffix('/avatar')
    with opener.open(base + '/avatar', timeout=10) as response:
        assert response.status == 200
    with opener.open(base + '/api/studio/template-library', timeout=10) as response:
        catalog = json.load(response)
    rows = catalog['templates']
    covers = 0
    for row in rows:
        url = row.get('poster')
        if url:
            with opener.open(base + url, timeout=10) as response:
                assert response.status == 200 and response.headers.get_content_type().startswith('image/')
            covers += 1
    assert covers >= 61, 'Existing real completed-video/fixed covers must be served'
    receipt = {'ok': True, 'arch': arch, 'version': deploy.version(), 'http_templates': len(rows),
               'http_covers': covers, 'actual_renderer': 'existing HeroTitle / Remotion',
               'video_has_motion': True, 'audio_and_video': True, 'paid_calls': 0,
               'bundled_login_browser_version': browser_version,
               'collector_browser_version': collector_version,
               'full_18_template_execution': 'not tested by this smoke', 'physical_colleague_machine': False}
    deploy.write(ROOT / '.local/mac-smoke.json', receipt)
    print(json.dumps(receipt))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
