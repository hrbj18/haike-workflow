"""Separate loopback management app; never mounted on the customer workbench."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backlot.studio import Studio, atomic_private
from backlot.work_api import call


def create_app(projects_root=None):
    from lib.paths import PROJECTS_DIR
    studio = Studio(projects_root or PROJECTS_DIR)
    studio.internal_admin_enabled = True
    studio.internal_bind_host = '127.0.0.1'
    app = FastAPI(title='海客内部服务配置', docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]'])

    @app.middleware('http')
    async def local_only(request, call_next):
        if request.client and request.client.host not in {'127.0.0.1', '::1', 'testclient'}:
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail': '内部配置仅允许本机访问'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    def mutation(request):
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            raise HTTPException(403, '请从本机内部配置页面提交')
        if 'application/json' not in request.headers.get('content-type', ''):
            raise HTTPException(415, '请求需要JSON格式')

    @app.get('/api/health')
    def health():
        return {'ok': True, 'app': 'haike-internal-services', 'workspace': str(Path(__file__).resolve().parents[2])}

    @app.get('/')
    def page():
        return FileResponse(Path(__file__).parent / 'ui/internal_services.html')

    @app.get('/api/internal/services')
    async def settings():
        from backlot.studio_services import settings as read
        return await asyncio.to_thread(call, read, studio)

    @app.put('/api/internal/services/{provider}')
    async def configure(provider: str, request: Request, data: dict = Body(...)):
        mutation(request)
        from backlot.studio_services import update_provider
        return await asyncio.to_thread(call, update_provider, studio, provider, data)

    @app.put('/api/internal/mode')
    def mode(request: Request, data: dict = Body(...)):
        mutation(request)
        if set(data) != {'mode'} or data['mode'] not in {'internal', 'gateway'}:
            raise HTTPException(422, '服务模式无效')
        import json
        path = studio.private / 'service-mode.json'
        previous = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
        atomic_private(path, {**previous, **data})
        return {'mode': data['mode'], 'message': '服务模式已保存，请刷新工作台'}

    @app.get('/api/internal/budgets')
    def budgets():
        from backlot.studio_services import budget_policy
        return call(budget_policy, studio)

    @app.put('/api/internal/budgets')
    def save_budgets(request: Request, data: dict = Body(...)):
        mutation(request)
        from backlot.studio_services import update_budget_policy
        return call(update_budget_policy, studio, data)

    app.mount('/ui/brand', StaticFiles(directory=Path(__file__).parent / 'ui/brand'), name='brand')
    return app


if __name__ == '__main__':
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=14757)
    options = parser.parse_args()
    os.environ['PYTHONUTF8'] = '1'
    uvicorn.run(create_app(), host='127.0.0.1', port=options.port, access_log=False)
