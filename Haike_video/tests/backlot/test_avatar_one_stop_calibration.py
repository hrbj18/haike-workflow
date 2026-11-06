"""Fixed-test reuse, isolation, and recovery before any full-text acceptance."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
import wave

import pytest

from backlot.avatar_one_stop_policy import CLONE_MODEL, fingerprint
from backlot.avatar_one_stop_tools import OneStopTools
from backlot.work_catalog import WorkError


def write_wav(path, seconds):
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(1000)
        audio.writeframes(b'\x01\x00' * round(seconds * 1000))
    return path


@pytest.fixture
def setup(tmp_path):
    tools = object.__new__(OneStopTools)
    tools.account = 'account-a'
    tools.verify_scope = lambda: tools.account
    tools.internal_audio = False
    tools.studio = SimpleNamespace(private=tmp_path / 'private')
    text = '测' * 92 + '，。'
    value = {'id': 'task-a', 'scope': fingerprint(tools.account), 'paid': {},
             'inputs': {'sample': {'sha256': 'original-recording'}},
             'script': {'text': '正式稿' * 100, 'text_sha256': 'formal-script'},
             'policy': {'speech_rate': {'calibration_mode': 'fixed_text_baseline',
                 'target_characters_per_second': 4.9,
                 'characters_per_five_seconds': {'minimum': 24, 'maximum': 25, 'target': 24.5},
                 'calibration_test': {'version': 'test-v1', 'text': text,
                    'text_sha256': hashlib.sha256(text.encode()).hexdigest(), 'effective_characters': 92}}},
             'stages': {'clone': {'result': {'voice_id': 'voice-a', 'model': 'haike/internal-tts', 'model_id': CLONE_MODEL}}}}
    calls = []
    def tts(shared, folder, name, script, rate, save):
        calls.append((name, script, rate))
        if name == 'calibration-baseline':
            assert rate == 1.0
        if name not in shared['paid']:
            shared['paid'][name] = {'quote': {'id': 'quote', 'operation_id': 'original-operation',
                                            'max_charge_micros': '20000'}, 'submitted': True, 'status': 'succeeded'}
            save()
        seconds = 19.68 if name == 'calibration-baseline' else (58.667 if rate == 1.05 else 60.48)
        return write_wav(folder / (name + '.wav'), seconds)
    tools._tts = tts
    return tools, value, calls


def test_fixed_test_is_generated_at_one_once_and_reused_for_other_business_text(tmp_path, setup):
    tools, value, calls = setup
    first_folder = tmp_path / 'first'
    first_folder.mkdir()
    first = tools.audition(value, first_folder, lambda: None)['result']
    assert first['sample_rate'] == 1.0 and first['rate'] == 1.05
    assert first['characters_per_five_seconds'] == pytest.approx(23.37398374)
    assert calls[0][1] == value['policy']['speech_rate']['calibration_test']['text']
    assert not first['cache_hit'] and first['full_narration_validation_required']
    assert 'quote' in value['paid']['audition']
    other = deepcopy(value)
    other.update(id='task-b', paid={})
    other['stages'].pop('audition')
    other['script']['text'] = '另一条完全不同的正式文案。'
    second_folder = tmp_path / 'second'
    second_folder.mkdir()
    second = tools.audition(other, second_folder, lambda: None)['result']
    assert second['cache_hit'] and len(calls) == 1
    assert second['calibration_key'] == first['calibration_key']
    assert (first_folder / 'audition.wav').read_bytes() == (second_folder / 'audition.wav').read_bytes()
    assert other['paid']['audition']['reused'] and 'quote' not in other['paid']['audition']


@pytest.mark.parametrize('changed', ['account', 'voice', 'model', 'test_version', 'test_text', 'source_sample', 'synthesis_seed'])
def test_measurement_cache_does_not_cross_changed_identity(tmp_path, setup, changed):
    tools, value, calls = setup
    first_folder, second_folder = tmp_path / 'first', tmp_path / 'second'
    first_folder.mkdir()
    second_folder.mkdir()
    first = tools.audition(value, first_folder, lambda: None)['result']
    other = deepcopy(value)
    other.update(id='task-b', paid={})
    other['stages'].pop('audition')
    if changed == 'account':
        tools.account = 'account-b'
        other['scope'] = fingerprint(tools.account)
    elif changed in {'voice', 'model'}:
        other['stages']['clone']['result']['voice_id' if changed == 'voice' else 'model_id'] = 'different'
    elif changed == 'test_version':
        other['policy']['speech_rate']['calibration_test']['version'] = 'test-v2'
    elif changed == 'test_text':
        test = other['policy']['speech_rate']['calibration_test']
        test['text'] = '另' * 92
        test['text_sha256'] = hashlib.sha256(test['text'].encode()).hexdigest()
    elif changed == 'synthesis_seed':
        other['policy']['speech_rate']['synthesis_seed'] = 17
        native_tts = tools._tts
        def seeded(shared, *args):
            assert shared['policy']['speech_rate']['synthesis_seed'] == 17
            return native_tts(shared, *args)
        tools._tts = seeded
    else:
        other['inputs']['sample']['sha256'] = 'updated-recording'
    second = tools.audition(other, second_folder, lambda: None)['result']
    assert len(calls) == 2 and first['calibration_key'] != second['calibration_key']


@pytest.mark.parametrize('failure', ['waiting', 'unknown'])
def test_pending_test_is_recovered_by_another_task_with_original_paid_intent(tmp_path, setup, failure):
    tools, value, calls = setup
    first_folder, second_folder = tmp_path / 'first', tmp_path / 'second'
    first_folder.mkdir()
    second_folder.mkdir()
    recovered_tts = tools._tts
    def pending(shared, folder, name, text, rate, save):
        shared['paid'][name] = {'quote': {'id': 'quote', 'operation_id': 'original-operation',
                                        'max_charge_micros': '20000'}, 'submitted': True, 'status': 'submission_unknown'}
        save()
        if failure == 'unknown':
            raise TimeoutError('provider acceptance unknown')
        return None
    tools._tts = pending
    if failure == 'unknown':
        with pytest.raises(TimeoutError):
            tools.audition(value, first_folder, lambda: None)
    else:
        assert tools.audition(value, first_folder, lambda: None)['status'] == 'waiting'
    other = deepcopy(value)
    other.update(id='task-b', paid={})
    other['stages'].pop('audition')
    def recover(shared, folder, name, text, rate, save):
        assert shared['paid'][name]['submitted']
        assert shared['paid'][name]['quote']['operation_id'] == 'original-operation'
        return recovered_tts(shared, folder, name, text, rate, save)
    tools._tts = recover
    assert tools.audition(other, second_folder, lambda: None)['status'] == 'succeeded'
    assert other['paid']['audition']['operation_id'] == 'original-operation' and len(calls) == 1


def test_damaged_cache_audio_recovers_original_operation_and_metadata_drift_blocks(tmp_path, setup):
    tools, value, calls = setup
    result = tools.audition(value, tmp_path, lambda: None)['result']
    cache = tools.studio.private / 'avatar-pace' / value['scope'][:32] / result['calibration_key'][:32]
    (cache / 'calibration-baseline.wav').write_bytes(b'damaged')
    original = tools._tts
    def recover(shared, folder, name, text, rate, save):
        assert shared['paid'][name]['quote']['operation_id'] == 'original-operation'
        return original(shared, folder, name, text, rate, save)
    tools._tts = recover
    assert tools.audition(value, tmp_path, lambda: None)['result']['audio_sha256'] == result['audio_sha256']
    assert len(calls) == 2
    path = cache / 'measurement.json'
    metadata = json.loads(path.read_text('utf-8'))
    metadata['identity']['voice_id'] = 'tampered'
    path.write_text(json.dumps(metadata), 'utf-8')
    tools._tts = lambda *args: pytest.fail('drift must never recreate a paid request')
    with pytest.raises(WorkError, match='缓存身份不符'):
        tools.audition(value, tmp_path, lambda: None)


def test_short_test_candidate_must_pass_full_narration_after_correction(tmp_path, setup):
    tools, value, calls = setup
    value['script'] = {'text': '字' * 299, 'text_sha256': 'same-299-script'}
    value['stages']['audition'] = tools.audition(value, tmp_path, lambda: None)
    outcome = tools.narration(value, tmp_path, lambda: None)['result']
    assert [call[2] for call in calls] == [1.0, 1.05, 1.0]
    assert outcome['rate'] == 1.0 and outcome['pace_check'] == 'within_five_second_band'
    assert outcome['characters_per_five_seconds'] == pytest.approx(24.71891534)
