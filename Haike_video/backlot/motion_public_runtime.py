"""Fixed host interface for the new public-source execution identity.

Queue lifecycle and root dispatch stay outside this file. No legacy hash is
exempted: this new request pins execution and this host adapter independently.
"""
from copy import deepcopy
from pathlib import Path
import re
import shutil

from backlot import motion_public_execution_v1 as execution
from backlot.motion_public_io_v1 import atomic_private, fingerprint, read_json, sha
from backlot.motion_public_execution_v1 import component, bound, require, real_clock, semantic_spec, preflight

CONTRACT = 'haike.motion-public-production/1'
KIND = 'studio_investment_recompose'
REQUEST_FILE = 'motion-public-request.json'
BINDINGS_FILE = 'motion-public-bindings.json'
TRANSPORT_ABI = 'haike.motion-public-parent/1'


def runtime():
    return {'execution': execution.runtime(),
            'transport': {'abi': TRANSPORT_ABI, 'adapter_sha256': sha(Path(__file__)),
                'prepare_cli_sha256': sha(execution.ROOT / 'scripts/motion_public_production_v1.py'),
                'host_dependencies': {name: sha(execution.ROOT / name) for name in ['lib/checkpoint.py', 'backlot/work_catalog.py']}}}


def prepare(queue, value):
    n = preflight(value)
    sources = {**n['paths'], 'script.json': n['script'], 'asr.json': n['asr']}
    core = {'contract': CONTRACT, 'title': value['title'], 'pack_key': value['pack_key'], 'spec': n['spec'],
            'input_engine': n.get('input_engine', 'public-scenes/1'),
            'reference': n['reference'], 'original_package_equivalence': False,
            'source_receipts': deepcopy(value.get('source_receipts', {})),
            'external_fonts': deepcopy(value.get('external_fonts', {})),
            'transcription_corrections': deepcopy(value.get('caption_corrections', [])),
            'environment': n['environment'], 'runtime': runtime(), 'duration': n['duration'], 'frames': n['frames'],
            'origins': {name: {'sha256': sha(path)} for name, path in sources.items()},
            'publication': False, 'paid_calls': 0}
    core['project_id'] = 'studio-' + fingerprint(core)[:16]
    digest = fingerprint(core)
    request = {**core, 'request_sha256': digest, 'render_id': 'motion-public-' + digest[:20]}
    from lib.checkpoint import init_project
    project = queue.projects_root / request['project_id']
    record = project / 'artifacts' / REQUEST_FILE
    if not record.exists():
        init_project(request['project_id'], title=request['title'], pipeline_type='animated-explainer', pipeline_dir=queue.projects_root)
        destination = project / 'assets/motion-public'
        destination.mkdir(parents=True, exist_ok=True)
        for name, path in sources.items():
            shutil.copy2(path, destination / name)
        work_root = Path(value.get('work_root', execution.ROOT.parent / '.local/motion-public-work')).resolve()
        require(work_root.is_relative_to((execution.ROOT.parent / '.local').resolve()), '作业缓存须在本副本忽略目录内')
        atomic_private(project / 'artifacts' / BINDINGS_FILE, {
            'tool_root': str(Path(value['tool_root']).resolve()),
            'dependency_root': str(Path(value['dependency_root']).resolve()),
            'work_root': str(work_root),
            'ffmpeg_root': str(Path(value['ffmpeg_root']).resolve()) if value.get('ffmpeg_root') else None,
            'origin_locators': {name: str(path) for name, path in sources.items()}})
        atomic_private(record, request)
    validate(queue, request)
    return request


def validate(queue, request):
    core = {k: v for k, v in request.items() if k not in {'request_sha256', 'render_id', 'phase', 'review_binding'}}
    require(request.get('contract') == CONTRACT and fingerprint(core) == request['request_sha256'], '公开组件冻结请求改变')
    require(re.fullmatch(r'studio-[0-9a-f]{16}', request['project_id'])
            and request['render_id'] == 'motion-public-' + request['request_sha256'][:20], '公开项目或输出身份无效')
    require(all(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', name) for name in request['origins']), '冻结资产逻辑路径无效')
    project = queue.projects_root / request['project_id']
    require(read_json(project / 'artifacts' / REQUEST_FILE) == {k: v for k, v in request.items() if k not in {'phase', 'review_binding'}}, '公开组件冻结记录改变')
    require(all((project / 'assets/motion-public' / name).is_file()
                and not (project / 'assets/motion-public' / name).is_symlink()
                and sha(project / 'assets/motion-public' / name) == row['sha256']
                for name, row in request['origins'].items()), '冻结素材改变')
    require(runtime() == request['runtime'], '执行或host adapter字节改变；保留旧实现，不豁免SHA')
    bindings = read_json(project / 'artifacts' / BINDINGS_FILE)
    _, identities = execution.environment(bindings['tool_root'], bindings['dependency_root'], bindings.get('ffmpeg_root'),
                                         engine=request.get('input_engine'))
    require(identities == request['environment'], '外部工具或实际依赖改变；位置映射不能改变字节')
    work_root = Path(bindings['work_root']).resolve()
    require(work_root.is_relative_to((execution.ROOT.parent / '.local').resolve()) and not work_root.is_symlink(), '作业缓存映射越界')
    folder = work_root / request['render_id']
    if request.get('phase') == 'render':
        require(request.get('review_binding') == _review_binding(folder, request), '正式导出未绑定当前有效预览审核')
    return project, folder


def _review_binding(folder, request):
    preview = read_json(folder / 'preview.json')
    approval = read_json(folder / 'visual-review.json')
    require(preview and preview.get('request_sha256') == request['request_sha256']
            and approval.get('preview_sha256') == sha(folder / 'preview.json')
            and approval.get('inspected_images') == preview['images'] and preview['images'], '须先实际审阅当前完整动作预览')
    require(approval.get('decision') == 'allow-local-candidate-export-for-comparison', '当前预览审核未批准本地候选整片导出')
    require(all(re.fullmatch(r'[A-Za-z0-9_.-]+', row['name']) and not (folder / 'preview' / row['name']).is_symlink()
                and sha(folder / 'preview' / row['name']) == row['sha256'] for row in preview['images']), '当前预览图片改变')
    return {'request_sha256': request['request_sha256'], 'preview_sha256': sha(folder / 'preview.json'), 'images': preview['images']}


def submit(queue, request, *, phase='preview'):
    _, folder = validate(queue, request)
    require(phase in {'preview', 'render'}, '制作阶段无效')
    if phase == 'render' and request.get('input_engine') == 'dark-remotion/1':
        from backlot.motion_public_dark_remotion_v1 import require_full_export_scope
        require_full_export_scope(request)
    binding = _review_binding(folder, request) if phase == 'render' else None
    # A reviewer name, note or timestamp never changes pixels or preview identity.
    # Preview remains the same original parent before and after later review.
    key = 'motion-public:' + request['request_sha256'] + ':' + phase
    frozen = {**request, 'phase': phase}
    if binding is not None:
        key += ':' + fingerprint(binding)
        frozen['review_binding'] = binding
    return queue.submit(kind=KIND, project_id=request['project_id'], source='codex', priority='normal',
        parent_job_id=request['render_id'], frozen_request=frozen, start_paused=True, idempotency_key=key)


def review(queue, request, evidence):
    _, folder = validate(queue, request)
    receipt = read_json(folder / 'preview.json')
    require(receipt and evidence.get('preview_sha256') == sha(folder / 'preview.json') and evidence.get('reviewer')
            and evidence.get('inspected_images') == receipt['images'], '审核须绑定本期全部实际动作预览')
    require(evidence.get('decision') in {'allow-local-candidate-export-for-comparison', 'changes_requested'}, '审核须明确批准候选导出或要求修改')
    require(all(sha(folder / 'preview' / row['name']) == row['sha256'] for row in receipt['images']), '预览图片改变')
    atomic_private(folder / 'visual-review.json', {**evidence, 'continuous_watching': 'pending', 'continuous_listening': 'pending'})
    return {'reviewed': True, 'candidate_export_approved': evidence['decision'] == 'allow-local-candidate-export-for-comparison',
            'scope': 'sampled-public-component-preview', 'original_fidelity': 'pending'}


def run(queue, job):
    request = job['frozen_request']
    try:
        require(job['kind'] == KIND and job['project_id'] == request['project_id'], '父队列身份不一致')
        project, folder = validate(queue, request)
        bindings = read_json(project / 'artifacts' / BINDINGS_FILE)
        invocation = {**request, 'tool_root': bindings['tool_root'], 'dependency_root': bindings['dependency_root'], 'ffmpeg_root': bindings.get('ffmpeg_root')}
        folder.mkdir(parents=True, exist_ok=True)
        execution.build_project(project, folder, invocation)
        result = execution.render_project(project, folder, invocation)
        if request['phase'] == 'render' and result['status'] == 'completed':
            from backlot.work_catalog import WorkCatalog
            produced = Path(result['result']['output_path'])
            managed = project / 'renders' / request['render_id'] / 'motion-public.mp4'
            managed.parent.mkdir(parents=True, exist_ok=True)
            if not managed.exists():shutil.copy2(produced, managed)
            require(sha(managed) == result['result']['output_sha256'], '托管作品与实际编码SHA不符')
            result['result']['output_path'] = str(managed)
            work = WorkCatalog(queue.projects_root).register(request['project_id'], managed,
                work_key='main', mode='manual', event_id=job['job_id'], quality_passed=False, actor=CONTRACT, title=request['title'],
                ffprobe=execution._ffprobe(invocation))
            result['result']['work_id'] = work['work_id']
        return result
    except Exception as exc:
        return {'status': 'failed', 'stage': '公开组件本地阶段未完成，原源与输入保留',
                'error': {'type': type(exc).__name__, 'message': str(exc)[:1000]},
                'retryable': True, 'safe_resume_point': 'motion-public-local'}
