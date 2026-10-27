"""Launch only the private loopback configuration app, with no production worker."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    options = parser.parse_args()
    url = 'http://127.0.0.1:14757'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url + '/api/health', timeout=2) as response:
            state = json.load(response)
        if state.get('app') != 'haike-internal-services' or Path(state['workspace']).resolve() != ROOT.resolve():
            raise RuntimeError('Port 14757 belongs to another workspace; nothing was stopped.')
    except urllib.error.URLError:
        logs = ROOT / 'Haike_video/.backlot/logs'
        logs.mkdir(parents=True, exist_ok=True)
        python = ROOT / 'Haike_video/.venv/Scripts' / ('pythonw.exe' if os.name == 'nt' else 'python')
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS if os.name == 'nt' else 0
        with (logs / 'internal-services.out.log').open('ab') as out, (logs / 'internal-services.err.log').open('ab') as err:
            subprocess.Popen([str(python), '-X', 'utf8', '-m', 'backlot.internal_services'],
                             cwd=ROOT / 'Haike_video', stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                             creationflags=flags, env=dict(os.environ, PYTHONUTF8='1'))
    if not options.no_browser:
        webbrowser.open(url)
    print('Internal configuration: ' + url)


if __name__ == '__main__':
    main()
