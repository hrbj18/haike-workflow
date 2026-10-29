"""Open the browser after readiness, reuse an already-running local sandbox."""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

URL = "http://127.0.0.1:17894"


def ready():
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(URL + "/health", timeout=1) as response:
            result = json.load(response)
        return (
            result.get("mode") in {"local_simulation", "local_commercial"}
            and result.get("status") == "ok"
        )
    except (OSError, ValueError, urllib.error.URLError):
        return False


def main():
    if ready():
        webbrowser.open(URL)
        print("账户中心已经运行，已打开浏览器。")
        return 0
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("run.py"))]
    )
    try:
        for _ in range(50):
            if process.poll() is not None:
                return process.returncode
            if ready():
                webbrowser.open(URL)
                break
            time.sleep(0.2)
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait(timeout=10)
        return 0


if __name__ == "__main__":
    sys.exit(main())
