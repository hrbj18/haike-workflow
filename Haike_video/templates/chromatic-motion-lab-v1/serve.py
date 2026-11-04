"""Serve the built visual preview on loopback; never expose source/config roots."""
import argparse
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

class Handler(SimpleHTTPRequestHandler):
    def send_head(self):
        requested = self.headers.get('Range')
        path = Path(self.translate_path(self.path))
        if requested and path.is_file():
            size = path.stat().st_size
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
            if not match or not size:
                self.send_error(416)
                return None
            start = int(match[1]) if match[1] else max(0,size-int(match[2] or 0))
            end = min(size-1,int(match[2])) if match[1] and match[2] else size-1
            if start > end or start >= size:
                self.send_response(416)
                self.send_header('Content-Range',f'bytes */{size}')
                self.end_headers()
                return None
            stream = path.open('rb')
            stream.seek(start)
            self.range_remaining = end-start+1
            self.send_response(206)
            self.send_header('Content-Type',self.guess_type(str(path)))
            self.send_header('Accept-Ranges','bytes')
            self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.send_header('Content-Length',str(self.range_remaining))
            self.end_headers()
            return stream
        self.range_remaining = None
        return super().send_head()

    def copyfile(self, source, outputfile):
        remaining = getattr(self,'range_remaining',None)
        if remaining is None:
            return super().copyfile(source,outputfile)
        while remaining:
            chunk = source.read(min(65536,remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'")
        super().end_headers()

    def list_directory(self, path):
        self.send_error(404)
        return None

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data', required=True, type=Path)
    parser.add_argument('--port', type=int, default=14942)
    args=parser.parse_args()
    root=args.data.resolve()
    if not (root/'index.html').is_file() or not (root/'gallery.js').is_file():
        parser.error('Build the preview before starting the server.')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,directory=str(root)))
    print(f'http://127.0.0.1:{server.server_port}/',flush=True)
    server.serve_forever()
