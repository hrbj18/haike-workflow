"""Keep new account writes out of this installation's update window."""
import json
from pathlib import Path
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class SourceUpdateMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, root):
        super().__init__(app)
        self.folder = Path(root) / '.local/app-updates'

    def blocked(self):
        state_path = self.folder / 'state.json'
        try:
            if not state_path.is_file():
                return False
            operation = json.loads(state_path.read_text(encoding='utf-8')).get('operation', {})
            if operation.get('status') in {'waiting', 'installing', 'restarting'}:
                return True
            identity = operation.get('id', '')
            if re.fullmatch('[0-9a-f]{24}', identity):
                receipt = self.folder / identity / 'receipt.json'
                if receipt.is_file():
                    return json.loads(receipt.read_text(encoding='utf-8')).get('status') in {'prepared', 'applying', 'installing', 'checking'}
            return False
        except (OSError, ValueError, TypeError, AttributeError):
            return True

    async def dispatch(self, request, call_next):
        mutation = request.method not in {'GET', 'HEAD', 'OPTIONS'}
        if mutation:
            if self.blocked():
                return JSONResponse({'detail': '本副本正在等待或安装更新，请稍后重试；原任务和账号保留。'}, status_code=503)
            request.app.state.haike_update_inflight = getattr(request.app.state, 'haike_update_inflight', 0) + 1
        try:
            return await call_next(request)
        finally:
            if mutation:
                request.app.state.haike_update_inflight -= 1
