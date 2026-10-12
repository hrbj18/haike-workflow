"""Exercise actual Windows startup with a broken venv and an isolated HTTP board."""
from pathlib import Path
import os
import socket
import subprocess
import urllib.request

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parent


@pytest.mark.skipif(os.name != "nt", reason="Windows launcher")
def test_broken_venv_falls_back_and_detaches_a_real_server(tmp_path):
    import shutil
    fixture = tmp_path / "workspace"
    project = fixture / "Haike_video"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    (fixture / "dist").mkdir()
    (project / ".venv/Scripts").mkdir(parents=True)
    shutil.copyfile(ROOT / ".venv/Scripts/python.exe", project / ".venv/Scripts/python.exe")
    (project / ".venv/pyvenv.cfg").write_text("home = C:\\missing-haike-python\nversion = 3.12.8\n", encoding="utf-8")
    for name in ("start_backlot.ps1", "launch_backlot.py"):
        shutil.copyfile(ROOT / "scripts" / name, scripts / name)
    package = project / "backlot"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text('''
import json,sys,os
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(json.dumps({'ok':True,'app':'backlot'}).encode())
    def log_message(self,*args): pass
server=HTTPServer(('127.0.0.1',int(sys.argv[-1])),Handler)
Path('server.pid').write_text(str(os.getpid()))
server.serve_forever()
''', encoding="utf-8")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    real_bundle = WORKSPACE / "dist/haike-workflow-windows-x64-20261009"
    harness = fixture / "harness.ps1"
    # Only replace discovery, never interpreter execution, bind, spawn or HTTP.
    harness.write_text("""
function Get-ChildItem {
    param($LiteralPath,[switch]$Directory,$Filter)
    [PSCustomObject]@{FullName='BUNDLE'}
}
& 'STARTER' -Port PORT -NoBrowser -SkipLocalTts
exit $LASTEXITCODE
""".replace("BUNDLE", str(real_bundle).replace("'", "''"))
           .replace("STARTER", str(scripts / "start_backlot.ps1").replace("'", "''"))
           .replace("PORT", str(port)), encoding="utf-8-sig")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / ".venv/Lib/site-packages")
    try:
        run = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
                             env=env, capture_output=True, timeout=30)
        output = run.stdout.decode("utf-8", errors="replace")
        assert run.returncode == 0, output + run.stderr.decode(errors="replace")
        assert f"http://127.0.0.1:{port}/" in output
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=3) as response:
            assert response.status == 200
        pid = (project / "server.pid").read_text()
        # Repeat after the original launcher exits: service remains and is reused.
        again = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
                               env=env, capture_output=True, timeout=30)
        assert again.returncode == 0 and (project / "server.pid").read_text() == pid
    finally:
        pid_path = project / "server.pid"
        if pid_path.exists():
            own_pid = int(pid_path.read_text())
            subprocess.run(["powershell.exe", "-NoProfile", "-Command", f"Stop-Process -Id {own_pid} -ErrorAction SilentlyContinue"],
                           capture_output=True, timeout=10)
