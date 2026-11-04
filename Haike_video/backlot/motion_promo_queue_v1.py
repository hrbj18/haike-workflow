"""Add the independent promo title without changing either prior queue class."""
from backlot.motion_public_queue_v1 import MotionPublicProductionQueue
from backlot.production_queue import _safe_public


class MotionPromoProductionQueue(MotionPublicProductionQueue):
    @classmethod
    def _public_row(cls, row):
        result = super()._public_row(row)
        private = cls._private_row(row)
        frozen = private.get('frozen_request') or {}
        if private['kind'] == 'studio_investment_recompose' and frozen.get('contract') == 'haike.promo-reference-full/1':
            title = frozen.get('title')
            if not isinstance(title, str) or not title.strip():
                title = private.get('project_title') or '流程演示完整视频'
            result['title'] = _safe_public(title[:160])
        return result
