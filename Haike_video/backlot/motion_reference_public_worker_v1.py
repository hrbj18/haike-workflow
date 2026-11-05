"""Fixed routes for the new reference controllers; legacy worker is unchanged."""
from backlot.production_queue_worker import ProductionQueueWorker


class MotionReferencePublicProductionWorker(ProductionQueueWorker):
    def _run_investment_recompose(self, job):
        contract = job.get('frozen_request', {}).get('contract')
        import sys
        if sys.platform == 'darwin' and contract in {
            'haike.motion-public-production/2', 'haike.motion-public-poster-production/3',
            'haike.motion-public-paper-production/3', 'haike.motion-public-quote-production/3',
        }:
            from backlot.motion_replay_production import _producer
            return _producer(job['frozen_request']).run(self.queue, job)
        if contract == 'haike.motion-public-paper-production/3':
            from backlot.motion_public_paper_production_v3 import run
            return run(self.queue, job)
        if contract == 'haike.motion-public-quote-production/3':
            from backlot.motion_public_quote_production_v3 import run
            return run(self.queue, job)
        if contract == 'haike.motion-public-poster-production/3':
            from backlot.motion_public_poster_production_v3 import run
            return run(self.queue, job)
        if contract == 'haike.motion-public-production/2':
            from backlot.motion_public_production_v2 import run
            return run(self.queue, job)
        if contract == 'haike.knowledge-reference-public/1':
            from backlot.motion_knowledge_public_production_v1 import run
            return run(self.queue, job)
        if contract == 'haike.knowledge-reference-public/2':
            from backlot.motion_knowledge_public_production_v2 import run
            return run(self.queue, job)
        if contract == 'haike.knowledge-reference-public/3':
            from backlot.motion_knowledge_public_production_v3 import run
            return run(self.queue, job)
        if contract == 'haike.promo-reference-full/2':
            from backlot.studio_promo_phase_v2 import run
            return run(self.queue, job)
        if contract == 'haike.promo-reference-full/3':
            from backlot.studio_promo_phase_v3 import run
            return run(self.queue, job)
        if contract == 'haike.motion-public-production/1':
            from backlot.motion_public_runtime import run
            return run(self.queue, job)
        if contract == 'haike.promo-reference-full/1':
            from backlot.studio_imported_promo_reference import run
            return run(self.queue, job)
        return super()._run_investment_recompose(job)
