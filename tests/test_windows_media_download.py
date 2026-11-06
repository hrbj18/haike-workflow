"""Exercise real HTTP range, fallback and integrity behavior without external services."""
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('media_download_test', ROOT / 'scripts/setup-windows-media.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
PAYLOAD = bytes(range(256)) * 100


@contextmanager
def server():
    class Handler(BaseHTTPRequestHandler):
        calls = []

        def log_message(self, *args):
            pass

        def do_GET(self):
            request_range = self.headers.get('Range', '')
            self.calls.append((self.path, request_range))
            if self.path == '/bad':
                self.send_response(206)
                self.send_header('Content-Range', 'bytes 0-1/9999999999')
                data = b'no'
            elif self.path == '/whole':
                self.send_response(200)
                data = PAYLOAD
            else:
                start, end = (int(value) for value in request_range.removeprefix('bytes=').split('-'))
                end = min(end, len(PAYLOAD) - 1)
                data = PAYLOAD[start:end + 1]
                self.send_response(206)
                self.send_header('Content-Range', f'bytes {start}-{end}/{len(PAYLOAD)}')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        with patch.object(setup, 'https_url', side_effect=lambda url: url), patch.object(setup, 'RANGE_SIZE', 4096):
            yield f'http://127.0.0.1:{http.server_port}', Handler.calls
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


class MediaDownloadTests(unittest.TestCase):
    def test_parallel_ranges_download_and_verify_the_complete_archive(self):
        with server() as (base, calls), tempfile.TemporaryDirectory() as folder:
            row = {'sha256': hashlib.sha256(PAYLOAD).hexdigest(), 'urls': [base + '/ranges']}
            result = setup.obtain(row, Path(folder))
            self.assertEqual(result.read_bytes(), PAYLOAD)
            self.assertGreater(len(calls), 1)
            calls.clear()
            self.assertEqual(setup.obtain(row, Path(folder)), result)
            self.assertEqual(calls, [])

    def test_bad_range_uses_next_mirror_and_whole_response(self):
        with server() as (base, calls), tempfile.TemporaryDirectory() as folder:
            row = {'sha256': hashlib.sha256(PAYLOAD).hexdigest(), 'urls': [base + '/bad', base + '/whole']}
            result = setup.obtain(row, Path(folder))
            self.assertEqual(result.read_bytes(), PAYLOAD)
            self.assertEqual([path for path, _ in calls], ['/bad', '/whole'])

    def test_wrong_digest_never_becomes_a_cached_archive(self):
        with server() as (base, _), tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            row = {'sha256': '0' * 64, 'urls': [base + '/ranges']}
            with self.assertRaisesRegex(ValueError, '均未下载成功'):
                setup.obtain(row, root)
            self.assertFalse((root / '.local/dependency-cache' / ('0' * 64 + '.zip')).exists())
            self.assertFalse(list((root / '.local/dependency-cache').glob('*.part')))


if __name__ == '__main__':
    unittest.main()
