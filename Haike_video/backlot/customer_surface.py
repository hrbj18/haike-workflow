"""Keep internal supplier controls off the customer surface of legacy tools."""
from __future__ import annotations

import os

from fastapi.responses import JSONResponse, Response

INTERNAL_PREFIXES = (
    "/api/audio-center", "/audio-preview/", "/api/ai-text/config", "/api/ai-text/doubao/config",
    "/api/runninghub/config", "/api/bailian/config", "/api/tencent/config",
    "/api/asr/tencent/config", "/api/asr/doubao/config",
    "/api/ai-text/test", "/api/ai-text/providers", "/api/ai-text/doubao/test",
    "/api/bailian/test", "/api/bailian/test-audio", "/api/tencent/test",
    "/api/asr/tencent/test", "/api/asr/doubao/test",
)
LEGACY_PAGES = {"/legacy/projects"}


def install(app):
    internal = os.environ.get("HAIKE_INTERNAL_TESTING") == "1"

    @app.middleware("http")
    async def customer_surface(request, call_next):
        path = request.url.path.rstrip("/")
        if not internal and any(path == p.rstrip("/") or path.startswith(p.rstrip("/") + "/") for p in INTERNAL_PREFIXES):
            return JSONResponse({"detail": "供应商配置仅供内部服务管理；用户请使用API设置中的海客Key"}, status_code=403)
        response = await call_next(request)
        if request.method != "GET" or (path not in LEGACY_PAGES and not path.startswith("/p/")):
            return response
        if response.status_code != 200 or "text/html" not in response.headers.get("content-type", ""):
            return response
        body = b"".join([chunk async for chunk in response.body_iterator])
        html = body.decode("utf-8")
        extras = '<link rel="stylesheet" href="/ui/haike-brand.css"><link rel="stylesheet" href="/ui/navigation.css"><link rel="stylesheet" href="/ui/legacy-skin.css">'
        extras += '<script>window.__HAIKE_INTERNAL__=' + ("true" if internal else "false") + ';</script><script type="module" src="/ui/legacy-shell.js"></script>'
        html = html.replace("</head>", extras + "</head>")
        headers = dict(response.headers)
        headers.pop("content-length", None)
        headers["cache-control"] = "no-store"
        return Response(html, status_code=response.status_code, headers=headers)
