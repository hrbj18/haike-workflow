"""Account-scoped fixed-text measurement and one recoverable shared TTS intent."""
from copy import deepcopy
import json
from pathlib import Path
import shutil

from backlot.avatar_one_stop_policy import (calibrate, calibration_test, digest,
                                           fingerprint, wav_duration)
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError
from lib.bailian_speech import operation_lock


def audition(tools, value, folder, save):
    policy = value['policy']['speech_rate']
    test = calibration_test(policy.get('calibration_test'))
    scope = fingerprint(str(tools.verify_scope()))
    if value['scope'] != scope:
        raise WorkError('当前账号已变化，请在原账号恢复语速测试', 'conflict')
    voice = value['stages']['clone']['result']
    identity = {'scope': scope, 'voice_id': voice['voice_id'], 'model': voice['model'],
                'model_id': voice['model_id'], 'test_version': test['version'],
                'text_sha256': test['text_sha256'], 'sample_rate': 1.0, 'purpose': 'production',
                'sample_sha256': value['inputs']['sample']['sha256']}
    seed = policy.get('synthesis_seed')
    if seed is not None:
        identity['synthesis_seed'] = seed
    if tools.internal_audio:
        profile = tools.center.runtime_profile(voice['voice_id'], 1.0)
        identity.update(runtime_profile_sha256=fingerprint(profile),
                        provider_identity=tools.center.backend.identity(profile['provider_id']))
    key = fingerprint(identity)
    parent = value['stages'].setdefault('audition', {})
    if parent.get('calibration_key', key) != key:
        raise WorkError('本次音色或测速规则已变化，请恢复原调用，不能覆盖已保存的测速意图', 'conflict')
    parent['calibration_key'] = key
    save()
    # Keep 128-bit directory IDs, as for one-stop task IDs, so Windows atomic
    # writes also fit beneath ordinary user/temp workspace paths.
    cache = Path(tools.studio.private) / 'avatar-pace' / scope[:32] / key[:32]
    cache.mkdir(parents=True, exist_ok=True)
    journal, audio = cache / 'measurement.json', cache / 'calibration-baseline.wav'
    with operation_lock(cache / 'lock'):
        if journal.exists():
            try:
                shared = json.loads(journal.read_text('utf-8'))
            except (ValueError, OSError):
                raise WorkError('固定测速缓存回执无法读取，请恢复原回执，不能重建付费调用', 'conflict') from None
            if shared.get('identity') != identity or shared.get('schema') != 'haike.speech-measurement/1':
                raise WorkError('固定测速缓存身份不符，请恢复原回执', 'conflict')
        else:
            shared = {'schema': 'haike.speech-measurement/1', 'identity': identity,
                      'owner_task_id': value['id'], 'paid': {},
                      'stages': {'clone': {'result': deepcopy(voice)}}}
            if seed is not None:
                shared['policy'] = {'speech_rate': {'synthesis_seed': seed}}

        def checkpoint():
            # Both the shared intent and its parent link precede any provider call.
            atomic_private(journal, shared)
            child = shared['paid'].get('calibration-baseline')
            if child:
                if shared['owner_task_id'] == value['id']:
                    value['paid']['audition'] = deepcopy(child) | {'calibration_key': key}
                else:
                    value['paid']['audition'] = {'reused': True, 'calibration_key': key,
                        'status': child.get('status', 'quoted'),
                        'operation_id': child['quote']['operation_id']}
            save()

        checkpoint()
        measured = shared.get('measurement')
        hit = bool(measured and audio.is_file() and digest(audio) == measured['audio_sha256'])
        if not hit:
            # Missing/damaged audio is recovered using this same paid journal.
            # A waiting/unknown request is shared across tasks, never requoted.
            audio = tools._tts(shared, cache, 'calibration-baseline', test['text'], 1.0, checkpoint)
            if audio is None:
                return {'status': 'waiting'}
            seconds = wav_duration(audio)
            measured = {'audio_sha256': digest(audio), 'duration_seconds': seconds,
                        'effective_characters': test['effective_characters']}
            shared['measurement'] = measured
            checkpoint()
        # Re-read frame duration so a corrupted measurement cannot select a rate.
        seconds = wav_duration(audio)
        if seconds != measured['duration_seconds'] or measured['effective_characters'] != test['effective_characters']:
            raise WorkError('固定测速回执与实际音频不一致，请核对原音频', 'conflict')
        target = Path(folder) / 'audition.wav'
        shutil.copy2(audio, target)
        result = calibrate(test['text'], seconds, target_cps=policy['target_characters_per_second'], sample_rate=1.0)
        result.update(audio_sha256=measured['audio_sha256'], text=test['text'],
                      test_version=test['version'], text_sha256=test['text_sha256'],
                      characters_per_five_seconds=result['measured_cps'] * 5,
                      calibration_key=key, cache_hit=hit, full_narration_validation_required=True)
        return {'status': 'succeeded', 'result': result}
