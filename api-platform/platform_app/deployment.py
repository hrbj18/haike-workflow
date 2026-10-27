"""Explicit public origin for the loopback backend behind the HTTPS proxy."""

from urllib.parse import urlsplit


def public_origin(value):
    if value is None:
        return None
    parsed = urlsplit(value.rstrip("/"))
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("Invalid public origin port") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
        or any(c.isspace() for c in value)
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ValueError("Public origin must be an HTTPS origin without a path")
    return parsed.geturl()


def serve_redirect(origin, port):
    """Keep the former local entry point without maintaining a second ledger."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    origin = public_origin(origin)

    class Redirect(BaseHTTPRequestHandler):
        def redirect(self):
            self.send_response(307)
            self.send_header("Location", origin + self.path)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = redirect

        def log_message(self, *_args):
            pass

    ThreadingHTTPServer(("127.0.0.1", port), Redirect).serve_forever()
