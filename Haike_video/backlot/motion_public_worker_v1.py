"""Add one fixed public-component route without modifying the legacy worker.

The inherited queue owns claims, leases, global serialization and completion.
This adapter does not certify arbitrary legacy source hashes as compatible.
"""
from backlot.production_queue_worker import ProductionQueueWorker


class MotionPublicProductionWorker(ProductionQueueWorker):
    def _run_investment_recompose(self, job):
        if job.get('frozen_request', {}).get('contract') == 'haike.motion-public-production/1':
            from backlot.motion_public_runtime import run
            return run(self.queue, job)
        return super()._run_investment_recompose(job)
