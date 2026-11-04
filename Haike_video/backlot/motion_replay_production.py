"""Common admission and explicit execution for owned motion parent producers."""
from importlib import import_module
from pathlib import Path

from backlot.motion_replay import ReplayError
from backlot.production_queue import _safe_public

PRODUCERS = {
    'haike-field-notes-video-production-v1': 'backlot.motion_replay_field_notes_video',
    'motion-replay-chromatic-production-v1': 'backlot.motion_replay_chromatic_production',
    'haike.motion-replay-imported-production/1': 'backlot.motion_replay_imported_production',
    'motion-replay-numbered-02-05-production-v1': 'backlot.motion_replay_numbered_02_05_production',
    'motion-replay-chromatic-suite-production-v1': 'backlot.motion_replay_chromatic_suite_production',
    'haike.knowledge-full/1': 'backlot.studio_imported_knowledge_full',
    'haike.native-knowledge-full/1': 'backlot.studio_imported_native_knowledge',
    'haike.motion-public-production/1': 'backlot.motion_public_runtime',
    'haike.motion-public-production/2': 'backlot.motion_public_production_v2',
    'haike.motion-public-poster-production/3': 'backlot.motion_public_poster_production_v3',
    'haike.motion-public-paper-production/3': 'backlot.motion_public_paper_production_v3',
    'haike.motion-public-quote-production/3': 'backlot.motion_public_quote_production_v3',
    'haike.promo-reference-full/1': 'backlot.studio_imported_promo_reference',
    'haike.knowledge-reference-public/1': 'backlot.motion_knowledge_public_production_v1',
    'haike.knowledge-reference-public/2': 'backlot.motion_knowledge_public_production_v2',
    'haike.knowledge-reference-public/3': 'backlot.motion_knowledge_public_production_v3',
    'haike.promo-reference-full/2': 'backlot.studio_promo_phase_v2',
    'haike.promo-reference-full/3': 'backlot.studio_promo_phase_v3',
}
KIND = 'studio_investment_recompose'


def _producer(request):
    if not isinstance(request, dict) or request.get('contract') not in PRODUCERS:
        raise ReplayError('此完整动效生产合同未登记，不能选择任意执行模块')
    try:
        return import_module(PRODUCERS[request['contract']])
    except ImportError as exc:
        raise ReplayError('此动效生产组件尚未准备齐全，请先修复对应组件再继续原任务') from exc


def _project(queue, request):
    identity = request.get('project_id')
    if not isinstance(identity, str) or not identity or Path(identity).name != identity or identity in {'.', '..'}:
        raise ReplayError('完整动效生产项目编号无效')
    root = Path(queue.projects_root).resolve()
    target = (root / identity).resolve()
    if not target.is_relative_to(root) or not target.is_dir():
        raise ReplayError('本期生产项目不存在或越界，请先由所属适配器冻结项目')


def submit_frozen(queue, request, *, phase=None):
    """Admit a previously frozen owned request; never runs a provider or renderer."""
    producer = _producer(request)
    _project(queue, request)
    contract = request['contract']
    if contract in {'haike-field-notes-video-production-v1', 'motion-replay-numbered-02-05-production-v1'}:
        if phase is not None and phase != request.get('phase'):
            raise ReplayError('阶段与原冻结请求不符，请由所属适配器冻结独立阶段')
        from backlot.motion_replay import WORKSPACE
        expected = producer.admit(WORKSPACE, request['data'], phase=request['phase'])
        if expected != request:
            raise ReplayError('本期冻结输入或源码已变化，保留原任务并核对恢复点')
        return queue.submit(project_id=request['project_id'], kind=KIND, source='codex',
            priority='normal', parent_job_id=request['render_id'], frozen_request=request,
            idempotency_key=contract + ':' + request['render_id'], start_paused=True)
    if contract in {'motion-replay-chromatic-production-v1', 'motion-replay-chromatic-suite-production-v1'}:
        if phase not in {None, 'render'}:
            raise ReplayError('此候选父视频仅接受完整渲染阶段')
        return producer.submit(queue, request)
    result = producer.submit(queue, request, phase=phase or 'preview')
    if isinstance(result, dict):
        extras = {key: _safe_public(result[key])
                  for key in ('availability', 'artifact_integrity') if key in result}
        return {**result, **extras}
    return result


def status(queue, job_id):
    """Keep the historical queue state separate from checked asset availability."""
    public = queue.get(job_id)
    private = queue.get(job_id, include_private=True)
    request = private.get('frozen_request') or {}
    if (private.get('kind') == KIND
            and request.get('contract') in {'haike.motion-public-paper-production/3', 'haike.motion-public-quote-production/3', 'haike.motion-public-poster-production/3', 'haike.motion-public-production/2', 'haike.promo-reference-full/2', 'haike.promo-reference-full/3'}):
        return {**public, 'availability': _safe_public(_producer(request).health(queue, request))}
    return public


def execute(queue, job_id, *, confirmed=False, resume_local=False):
    """Explicitly claim one original paused parent; no automatic retry/revival."""
    if confirmed is not True:
        raise ReplayError('执行前须明确确认本期费用授权与本地渲染范围')
    job = queue.get(job_id, include_private=True)
    if job.get('kind') != KIND:
        raise ReplayError('此入口只执行已登记的完整动效父视频')
    producer = _producer(job.get('frozen_request'))
    _project(queue, job['frozen_request'])
    if job['status'] == 'completed':
        return status(queue, job_id)
    request = job['frozen_request']
    local_phase = (request['contract'] not in {'haike-field-notes-video-production-v1', 'motion-replay-numbered-02-05-production-v1'}
                   or request.get('phase') in {'frames', 'render'})
    recover_local = (resume_local is True and job['status'] == 'failed'
                     and job.get('retryable') is True and local_phase)
    if job['status'] != 'paused' and not recover_local:
        raise ReplayError('原任务不是暂停待领取状态；请核对原任务，不自动恢复或重复提交')
    if request['contract'] in {'haike.motion-public-paper-production/3', 'haike.motion-public-quote-production/3', 'haike.motion-public-poster-production/3', 'haike.motion-public-production/2', 'haike.promo-reference-full/3', 'haike.knowledge-reference-public/2', 'haike.knowledge-reference-public/3'}:
        producer.validate_claim(queue, job_id)
    if request['contract'] in {'haike.motion-public-paper-production/3', 'haike.motion-public-quote-production/3', 'haike.motion-public-poster-production/3', 'haike.motion-public-production/2', 'haike.knowledge-reference-public/1', 'haike.knowledge-reference-public/2', 'haike.knowledge-reference-public/3', 'haike.promo-reference-full/2', 'haike.promo-reference-full/3'}:
        from backlot.motion_reference_public_worker_v1 import MotionReferencePublicProductionWorker
        worker = MotionReferencePublicProductionWorker(queue, queue.projects_root)
    elif request['contract'] == 'haike.promo-reference-full/1':
        from backlot.motion_promo_worker_v1 import MotionPromoProductionWorker
        worker = MotionPromoProductionWorker(queue, queue.projects_root)
    elif request['contract'] == 'haike.motion-public-production/1':
        from backlot.motion_public_worker_v1 import MotionPublicProductionWorker
        worker = MotionPublicProductionWorker(queue, queue.projects_root)
    else:
        from backlot.production_queue_worker import ProductionQueueWorker
        worker = ProductionQueueWorker(queue, queue.projects_root)
    result = worker.run_local_recompose(job_id)
    if request['contract'] in {'haike.motion-public-paper-production/3', 'haike.motion-public-quote-production/3', 'haike.motion-public-poster-production/3', 'haike.motion-public-production/2', 'haike.promo-reference-full/2', 'haike.promo-reference-full/3'}:
        return status(queue, job_id)
    return result
