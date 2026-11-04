"""Display titles for new reference contracts using the existing redaction rules."""
from backlot.motion_promo_queue_v1 import MotionPromoProductionQueue
from backlot.production_queue import _safe_public


class MotionReferencePublicProductionQueue(MotionPromoProductionQueue):
    @classmethod
    def _public_row(cls, row):
        result = super()._public_row(row)
        private = cls._private_row(row)
        frozen = private.get('frozen_request') or {}
        if (private['kind'] == 'studio_investment_recompose'
                and frozen.get('contract') in {
                    'haike.motion-public-paper-production/3',
                    'haike.motion-public-quote-production/3',
                    'haike.motion-public-poster-production/3',
                    'haike.motion-public-production/2',
                    'haike.knowledge-reference-public/1', 'haike.knowledge-reference-public/2',
                    'haike.knowledge-reference-public/3',
                    'haike.promo-reference-full/2',
                    'haike.promo-reference-full/3'}):
            title = frozen.get('title')
            if not isinstance(title, str) or not title.strip():
                title = private.get('project_title') or '参考动效完整视频'
            result['title'] = _safe_public(title[:160])
        return result
