"""Fixed independent-promo route over the unchanged legacy queue worker."""
from backlot.production_queue_worker import ProductionQueueWorker


class MotionPromoProductionWorker(ProductionQueueWorker):
    def _run_investment_recompose(self, job):
        if job.get('frozen_request', {}).get('contract') == 'haike.promo-reference-full/1':
            from backlot.studio_imported_promo_reference import run
            return run(self.queue, job)
        return super()._run_investment_recompose(job)
