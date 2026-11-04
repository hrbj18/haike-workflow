"""Public-component presentation extension over the unchanged durable queue.

Admission, serialization, sanitization and lifecycle remain owned by the base.
Only the new fixed contract receives its authored public task title here.
"""
from backlot.production_queue import ProductionQueue, _safe_public


class MotionPublicProductionQueue(ProductionQueue):
    @classmethod
    def _public_row(cls, row):
        result = super()._public_row(row)
        private = cls._private_row(row)
        frozen = private.get('frozen_request') or {}
        if private['kind'] == 'studio_investment_recompose' and frozen.get('contract') == 'haike.motion-public-production/1':
            title = frozen.get('title')
            if not isinstance(title, str) or not title.strip():
                title = private.get('project_title') or '公开动效组件完整视频'
            result['title'] = _safe_public(title[:160])
        return result
