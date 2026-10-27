"""Offline authorization/recovery contracts for budget-only batch amendments."""
import copy
import hashlib
import json

import pytest

from backlot.codex_batch import BatchError, CodexBatch, canonical, fingerprint
from tests.backlot.test_codex_batch import API, preset_setup, setup  # noqa: F401


class BudgetAPI(API):
    """The queue's CAS and event-replay contract; no worker or supplier exists."""

    def __init__(self, root):
        super().__init__(root)
        self.amendments = {}
        self.reject_validation = None
        self.invalid_validation = None
        self.validation_fault = 'not-validated'
        self.lose_response = None
        self.applied = []

    def call(self, path, data=None, **kwargs):
        if not path.endswith('/budget-amend'):
            return super().call(path, data, **kwargs)
        self.calls.append(('POST', path, copy.deepcopy(data)))
        job_id = path.split('/')[-2]
        job = self.jobs[job_id]
        evidence_sha = hashlib.sha256(data['authorization_evidence'].strip().encode()).hexdigest()
        receipt = {
            'previous_max_charge_micros': data['previous_max_charge_micros'],
            'max_charge_micros': data['max_charge_micros'],
            'authorization_sha256': evidence_sha,
            'validated': True,
        }
        if data['validate_only'] and self.reject_validation == job_id:
            raise BatchError('原付费阶段未确认成功', status=409)
        previous = self.amendments.get(job_id)
        if previous:
            assert previous == receipt
            return {**copy.deepcopy(job), 'budget_amendment': {
                **receipt, 'applied': True, 'replayed': True}}
        assert job['revision'] == data['expected_revision']
        assert job['max_charge_micros'] == data['previous_max_charge_micros']
        if data['validate_only']:
            result = {**copy.deepcopy(job), 'budget_amendment': {
                **receipt, 'applied': False, 'replayed': False}}
            if self.invalid_validation == job_id:
                if self.validation_fault == 'not-dict':
                    return None
                if self.validation_fault == 'wrong-job':
                    result['job_id'] = 'PQ-foreign'
                elif self.validation_fault == 'missing-receipt':
                    result.pop('budget_amendment')
                else:
                    key, value = {
                        'not-validated': ('validated', False),
                        'wrong-hash': ('authorization_sha256', '0' * 64),
                        'wrong-cap': ('max_charge_micros', 201),
                    }[self.validation_fault]
                    result['budget_amendment'][key] = value
            return result
        self.amendments[job_id] = copy.deepcopy(receipt)
        self.applied.append(job_id)
        job.update(status='queued', max_charge_micros=data['max_charge_micros'],
                   revision=job['revision'] + 1)
        if self.lose_response == job_id:
            self.lose_response = None
            raise BatchError('API响应未确认；核对原任务', unknown=True)
        return {**copy.deepcopy(job), 'budget_amendment': {
            **receipt, 'applied': True, 'replayed': False}}


@pytest.fixture
def prepared(preset_setup):
    """Three original failed jobs with a real, immutable preset snapshot."""
    from backlot.codex_batch_defaults import resolve_spec_defaults

    spec, root, original, _preset = preset_setup
    spec = resolve_spec_defaults(spec, root=root, api=original)
    first = spec['items'][0]
    for number in (2, 3):
        spec['items'].append({**copy.deepcopy(first), 'slot_id': f'n{number}',
                              'topic_key': f'fixture-event-{number}', 'title': f'主题{number}'})
    spec['limit_micros'] = 300
    api = BudgetAPI(root)
    batch = CodexBatch(spec, root=root, api=api)
    batch.init()
    batch.prepare()
    batch.submit()
    for job in api.jobs.values():
        job.update(status='failed', revision=4, max_charge_micros=100,
                   error={'message': '原任务预算不足'})
    evidence = {
        'batch_id': spec['batch_id'], 'spec_sha256': batch.spec_hash,
        'authorized': True, 'reason': '用户明确提高原三条预算，继续原任务',
        'limit_micros': 660,
        'items': [{'slot_id': item['slot_id'], 'previous_max_charge_micros': 100,
                   'max_charge_micros': 200, 'prior_exposure_micros': 20,
                   'authorized_item_limit_micros': 220} for item in spec['items']],
    }
    api.calls.clear()
    return batch, api, evidence


def authorization_path(batch):
    return (batch.root / 'Haike_video/.backlot/codex-batches' /
            ('batch-' + fingerprint(batch.spec['batch_id'])[:24]) / 'budget-authorization.json')


def mutations(api):
    return [call for call in api.calls if call[0] != 'GET'
            and not (call[1].endswith('/budget-amend') and call[2]['validate_only'])]


@pytest.mark.parametrize('change', [
    lambda e: e.update(authorized=False),
    lambda e: e.update(authorized=1),
    lambda e: e.update(reason='  '),
    lambda e: e.update(spec_sha256='0' * 64),
    lambda e: e.update(batch_id='different-batch'),
    lambda e: e.update(limit_micros=600),  # 600 new + 60 old exposure exceeds total.
    lambda e: e['items'][0].update(authorized_item_limit_micros=200),
    lambda e: e['items'][0].update(prior_exposure_micros=-1),
    lambda e: e['items'][0].update(prior_exposure_micros=True),
    lambda e: e['items'][0].update(max_charge_micros=100),
    lambda e: e['items'][0].update(previous_max_charge_micros=99),
    lambda e: e['items'].pop(),
    lambda e: e['items'][1].update(slot_id='n1'),
    lambda e: e['items'][1].update(slot_id='unknown'),
    lambda e: e.update(api_key='forbidden-fixture'),
], ids=['not-authorized', 'not-boolean', 'empty-reason', 'wrong-spec-sha', 'wrong-batch',
        'old-exposure-total', 'old-exposure-item', 'negative-prior', 'boolean-prior',
        'not-an-increase', 'wrong-original-cap', 'missing-slot', 'duplicate-slot',
        'foreign-slot', 'secret-field'])
def test_invalid_authorization_is_rejected_before_any_http(prepared, change):
    batch, api, evidence = prepared
    change(evidence)
    with pytest.raises(BatchError):
        batch.amend_budget(evidence)
    assert api.calls == []
    assert not authorization_path(batch).exists()


def test_all_slots_validate_before_any_task_or_queue_mutation(prepared):
    batch, api, evidence = prepared
    api.reject_validation = 'PQ-3'
    before = copy.deepcopy((api.tasks, api.jobs))
    with pytest.raises(BatchError, match='未确认成功'):
        batch.amend_budget(evidence)
    assert len([c for c in api.calls if c[1].endswith('/budget-amend')]) == 3
    assert mutations(api) == []
    assert (api.tasks, api.jobs) == before
    assert not authorization_path(batch).exists()


@pytest.mark.parametrize('fault', ['not-validated', 'wrong-job', 'wrong-hash', 'wrong-cap', 'missing-receipt', 'not-dict'])
def test_unconfirmed_validate_only_receipt_cannot_admit_any_queue(prepared, fault):
    batch, api, evidence = prepared
    api.invalid_validation = 'PQ-3'
    api.validation_fault = fault
    with pytest.raises(BatchError, match='确认|校验|验证'):
        batch.amend_budget(evidence)
    assert mutations(api) == []
    assert api.applied == []
    assert not authorization_path(batch).exists()


def test_amendment_preserves_original_spec_snapshot_drafts_and_paid_confirmations(prepared):
    batch, api, evidence = prepared
    spec_before, drafts_before = copy.deepcopy(batch.spec), copy.deepcopy(api.drafts)
    files = {path: path.read_bytes() for path in batch.projects.rglob('spec.json')}
    assert len(files) == 3
    assert all(item['avatar_defaults_snapshot']['values']['max_charge_micros'] == 100
               for item in batch.spec['items'])
    counts = api.quotes, api.uploads, api.submissions
    task_ids, job_ids = set(api.tasks), set(api.jobs)
    result = batch.amend_budget(evidence)
    assert batch.spec == spec_before and api.drafts == drafts_before
    assert all(path.read_bytes() == data for path, data in files.items())
    assert (api.quotes, api.uploads, api.submissions) == counts == (3, 3, 3)
    assert set(api.tasks) == task_ids and set(api.jobs) == job_ids
    assert not any(call[1].endswith(('/generate', '/quote', '/retry', '/publish')) for call in api.calls)
    actions = [(path.rsplit('/', 2)[-2], data['validate_only'])
               for _method, path, data in api.calls if path.endswith('/budget-amend')]
    assert actions == [('PQ-1', True), ('PQ-2', True), ('PQ-3', True),
                       ('PQ-1', False), ('PQ-2', False), ('PQ-3', False)]
    assert api.applied == ['PQ-1', 'PQ-2', 'PQ-3']
    assert result['spec_sha256'] == fingerprint(spec_before)
    assert result['budget'] == {
        'limit_micros': 660, 'allocated_micros': 600, 'prior_exposure_micros': 60,
        'combined_allocated_micros': 660, 'actual_micros': None,
        'reserved_micros': None, 'estimated_micros': None,
    }
    receipt = json.loads(authorization_path(batch).read_text(encoding='utf-8'))
    assert receipt['authorization'] == evidence
    assert receipt['authorization_sha256'] == fingerprint(evidence)
    assert receipt['original_spec_unchanged'] is True
    assert all(task['budget']['limit_micros'] == 200 for task in api.tasks.values())


def test_report_and_recreated_batch_keep_old_exposure_without_inventing_actual(prepared):
    batch, api, evidence = prepared
    for index, task in enumerate(api.tasks.values(), 1):
        task['budget'].update(reserved_micros=index * 3, estimated_micros=index * 5)
    batch.amend_budget(evidence)
    recreated = CodexBatch(batch.spec, root=batch.root, api=api)
    result = recreated.report()
    assert result['budget'] == {
        'limit_micros': 660, 'allocated_micros': 600, 'prior_exposure_micros': 60,
        'combined_allocated_micros': 660, 'actual_micros': None,
        'reserved_micros': 18, 'estimated_micros': 30,
    }
    assert [row['max_charge_micros'] for row in result['items']] == [200] * 3
    subset = recreated.status('n1')['budget']
    assert subset['prior_exposure_micros'] == 60
    assert subset['combined_allocated_micros'] == 660
    assert subset['actual_micros'] is subset['reserved_micros'] is subset['estimated_micros'] is None


def test_lost_response_replays_same_authorization_and_original_queues_once(prepared):
    batch, api, evidence = prepared
    api.lose_response = 'PQ-2'
    with pytest.raises(BatchError) as caught:
        batch.amend_budget(evidence)
    assert caught.value.unknown is True
    assert api.applied == ['PQ-1', 'PQ-2']
    receipt_before = authorization_path(batch).read_bytes()
    recreated = CodexBatch(batch.spec, root=batch.root, api=api)
    result = recreated.amend_budget(evidence)
    recreated.amend_budget(copy.deepcopy(evidence))
    assert api.applied == ['PQ-1', 'PQ-2', 'PQ-3']
    assert api.submissions == 3 and len(api.jobs) == len(api.tasks) == 3
    assert authorization_path(batch).read_bytes() == receipt_before
    assert result['budget']['actual_micros'] is None
    assert all(job['revision'] == 5 for job in api.jobs.values())


def test_a_changed_spec_cannot_relabel_the_original_authorization(prepared):
    batch, api, evidence = prepared
    batch.amend_budget(evidence)
    changed = copy.deepcopy(batch.spec)
    changed['items'][0]['text'] = '另一个文案，不能冒充原冻结规格。'
    alternate = CodexBatch(changed, root=batch.root, api=api)
    api.calls.clear()
    with pytest.raises(BatchError, match='原规格'):
        alternate.amend_budget(evidence)
    assert api.calls == []
    with pytest.raises(BatchError, match='原规格'):
        alternate.status()
    assert mutations(api) == []
    altered_evidence = {**copy.deepcopy(evidence), 'spec_sha256': alternate.spec_hash}
    with pytest.raises(BatchError, match='不同预算修订'):
        alternate.amend_budget(altered_evidence)
    assert mutations(api) == []


def test_tampered_authorization_receipt_is_not_reported_as_effective(prepared):
    batch, api, evidence = prepared
    batch.amend_budget(evidence)
    path = authorization_path(batch)
    receipt = json.loads(path.read_text(encoding='utf-8'))
    receipt['authorization']['reason'] = '被改写的授权理由'
    path.write_text(json.dumps(receipt), encoding='utf-8')
    api.calls.clear()
    with pytest.raises(BatchError, match='收据校验失败'):
        batch.status()
    assert mutations(api) == []


@pytest.mark.parametrize('binding', ['foreign-project', 'foreign-kind', 'foreign-revision', 'already-published'])
def test_original_queue_binding_and_unpublished_requirement_precede_mutations(prepared, binding):
    batch, api, evidence = prepared
    if binding == 'already-published':
        api.tasks['TC-3']['facts']['execution']['publication_receipts'] = [{'task_id': 81, 'state': 'submitted'}]
    else:
        key, value = {
            'foreign-project': ('project_id', 'another-project'),
            'foreign-kind': ('kind', 'studio_graphic'),
            'foreign-revision': ('parent_job_id', 'studio-999'),
        }[binding]
        api.jobs['PQ-3'][key] = value
    with pytest.raises(BatchError, match='尚未发布的原数字人队列'):
        batch.amend_budget(evidence)
    assert mutations(api) == []
    assert not authorization_path(batch).exists()


def install_cli(prepared, tmp_path, monkeypatch):
    from scripts import codex_video_batch as cli
    batch, api, evidence = prepared
    spec_path, evidence_path = tmp_path / 'original-spec.json', tmp_path / 'budget-evidence.json'
    spec_path.write_text(canonical(batch.spec), encoding='utf-8')
    evidence_path.write_text(canonical(evidence), encoding='utf-8')
    monkeypatch.setattr(cli, 'LocalAPI', lambda _base: api)
    monkeypatch.setattr(cli, 'CodexBatch', lambda spec, api: CodexBatch(spec, root=batch.root, api=api))
    return cli, spec_path, evidence_path


def test_cli_budget_amend_uses_original_files_without_regeneration(prepared, tmp_path, monkeypatch, capsys):
    batch, api, evidence = prepared
    cli, spec_path, evidence_path = install_cli(prepared, tmp_path, monkeypatch)
    before = spec_path.read_bytes(), evidence_path.read_bytes()
    assert cli.main(['budget-amend', '--spec', str(spec_path), '--evidence', str(evidence_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['spec_sha256'] == batch.spec_hash
    assert result['budget']['combined_allocated_micros'] == 660
    assert (spec_path.read_bytes(), evidence_path.read_bytes()) == before
    assert api.submissions == 3


@pytest.mark.parametrize('option', ['missing-evidence', 'single-slot', 'not-authorized'])
def test_cli_invalid_amendment_makes_no_http(prepared, tmp_path, monkeypatch, capsys, option):
    _batch, api, _evidence = prepared
    cli, spec_path, evidence_path = install_cli(prepared, tmp_path, monkeypatch)
    args = ['budget-amend', '--spec', str(spec_path)]
    if option != 'missing-evidence':
        args += ['--evidence', str(evidence_path)]
    if option == 'single-slot':
        args += ['--slot', 'n1']
    if option == 'not-authorized':
        evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
        evidence['authorized'] = False
        evidence_path.write_text(canonical(evidence), encoding='utf-8')
    assert cli.main(args) == 2
    output = capsys.readouterr()
    assert json.loads(output.err)['ok'] is False and output.out == ''
    assert api.calls == []
