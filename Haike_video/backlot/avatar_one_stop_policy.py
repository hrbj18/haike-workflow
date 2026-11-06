"""Frozen one-stop defaults and speech calibration, with no provider calls."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import math
from pathlib import Path
import unicodedata
import wave

from backlot.work_catalog import WorkError

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / '.local/avatar-agent-production/policy.private.json'
TEMPLATE_ID = 'chromatic-six-11'
VERSION = '1.2.0-candidate.1'
WORKFLOW_ID = '2112180419025260546'
CLONE_MODEL = 'qwen-audio-3.1-tts-plus'
CALIBRATION_MODE = 'fixed_text_baseline'
SPEECH_RATE_RULE = {
    'calibration_mode': CALIBRATION_MODE,
    'baseline_rate': 1.0,
    'target_characters_per_second': 4.9,
    'characters_per_five_seconds': {'minimum': 23.5, 'maximum': 25.5, 'target': 24.5},
    'max_full_text_attempts': 3,
}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def effective_characters(text):
    return sum(char.isalnum() for char in unicodedata.normalize('NFKC', text))


def calibration_test(value):
    """Validate the pinned spoken test, independently of the production script."""
    if not isinstance(value, dict):
        raise WorkError('请在本机一条龙规则中配置固定测速文案', 'unavailable')
    text, version = value.get('text'), value.get('version')
    if (not isinstance(text, str) or not isinstance(version, str) or not version.strip()
            or len(version) > 100 or not 90 <= effective_characters(text) <= 110):
        raise WorkError('固定测速文案需有版本号及约100个有效字')
    actual = hashlib.sha256(text.encode()).hexdigest()
    count = effective_characters(text)
    if value.get('text_sha256') != actual or value.get('effective_characters') != count:
        raise WorkError('固定测速文案内容或字数与已确认身份不符', 'conflict')
    return {key: deepcopy(value[key]) for key in ('version', 'text', 'text_sha256', 'effective_characters')}


def wav_duration(path):
    try:
        with wave.open(str(path), 'rb') as audio:
            if audio.getnframes() <= 0 or audio.getframerate() <= 0:
                raise ValueError()
            return audio.getnframes() / audio.getframerate()
    except (OSError, ValueError, wave.Error, EOFError):
        raise WorkError('配音音轨无法读取，请恢复原任务的完整WAV', 'unavailable') from None


def validate_rate(value):
    try:
        rate = Decimal(str(value))
        if type(value) is bool or not rate.is_finite() or not Decimal('.5') <= rate <= Decimal('2') or rate % Decimal('.05'):
            raise ValueError()
        return float(rate)
    except (InvalidOperation, ValueError, TypeError):
        raise WorkError('语速需在0.50至2.00之间，并按0.05档位调整') from None


def calibrate(text, duration_seconds, *, target_cps, sample_rate=1):
    try:
        values = [Decimal(str(value)) for value in (duration_seconds, target_cps, sample_rate)]
    except (InvalidOperation, ValueError):
        raise WorkError('语速校准参数无效') from None
    if any(type(value) is bool for value in (duration_seconds, target_cps, sample_rate)):
        raise WorkError('语速校准参数无效')
    if any(not value.is_finite() or value <= 0 for value in values):
        raise WorkError('语速校准需要有效的实际时长、目标语速和原倍率')
    seconds, target, current = values
    if not Decimal('.5') <= current <= Decimal('2'):
        raise WorkError('试听倍率需在0.50至2.00之间')
    count = effective_characters(text)
    if not count:
        raise WorkError('试听原文没有可计数的有效文字')
    measured = Decimal(count) / seconds
    raw = current * target / measured
    snapped = (raw / Decimal('.05')).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * Decimal('.05')
    selected = min(Decimal('2.00'), max(Decimal('.50'), snapped))
    return {'effective_characters': count, 'duration_seconds': float(seconds),
            'sample_rate': float(current), 'measured_cps': float(measured),
            'target_cps': float(target), 'raw_rate': float(raw),
            'rate': float(selected), 'increment': .05, 'clamped': selected != snapped,
            'rounding': 'nearest_half_up',
            'predicted_cps': float(measured * selected / current)}


def load_policy(path=POLICY):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        if value.get('schema') != 'haike.avatar-agent-production-policy/1':
            raise ValueError()
        if value['template']['template_id'] != TEMPLATE_ID or value['template']['version'] != VERSION:
            raise WorkError('一条龙当前支持已登记的动效模板11完整有声版本')
        if value['avatar_generation']['workflow_id'] != WORKFLOW_ID:
            raise WorkError('一条龙任务需使用已指定的高质量数字人工作流')
        budget = value['avatar_generation']['budget_rh_coins_per_video']
        if type(budget) not in (int, float) or not math.isfinite(budget) or not 0 < budget <= 2000:
            raise WorkError('每条数字人的累计上限需为0至2000 RH币')
        auth = value['paid_authorization']
        if auth.get('standing_authorized') is not True or auth.get('other_paid_stages_authorized') is not True:
            raise WorkError('本机一条龙制作授权尚未配置', 'unavailable')
        if value['voice_clone']['model'] != CLONE_MODEL:
            raise WorkError('一条龙声音克隆需使用指定的3.1 TTS Plus')
        script_ref = value['default_script']
        script_path = Path(script_ref['script_json'])
        if digest(script_path) != script_ref['script_json_sha256']:
            raise WorkError('默认原稿身份发生变化，请核对本机规则', 'conflict')
        script = json.loads(script_path.read_text(encoding='utf-8-sig'))
        if hashlib.sha256(script['text'].encode()).hexdigest() != script_ref['text_sha256']:
            raise WorkError('默认原稿内容发生变化，请恢复已确认版本', 'conflict')
        reference = value['image_refinement']['reference_image']
        if digest(reference['path']) != reference['sha256']:
            raise WorkError('固定肤色肤质参考图发生变化，请核对原参考', 'conflict')
        result = deepcopy(value)
        # Only newly created/revised tasks load current rules. Existing tasks
        # retain their frozen snapshots and original paid-operation journals.
        result['speech_rate'].update(deepcopy(SPEECH_RATE_RULE))
        result['speech_rate']['calibration_test'] = calibration_test(result['speech_rate'].get('calibration_test'))
        result['script'] = {'title': script['title'], 'text': script['text'],
                            'text_sha256': script_ref['text_sha256'],
                            'required_overlay': script.get('required_overlay', '')}
        return result
    except WorkError:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        raise WorkError('一条龙本机规则或默认素材尚未配置完整，请检查私有配置', 'unavailable') from None


def public_defaults(policy):
    return {'configured': True, 'call_sign': '一条龙视频生成流程',
            'template': {'id': TEMPLATE_ID, 'version': VERSION,
                         'name': '动效模板11 · 深蓝蜜桃路线'},
            'title': policy['script']['title'], 'text': policy['script']['text'],
            'clone_model': CLONE_MODEL, 'target_cps': policy['speech_rate']['target_characters_per_second'],
            'calibration_mode': policy['speech_rate']['calibration_mode'],
            'baseline_rate': policy['speech_rate']['baseline_rate'],
            'calibration_test': {key: policy['speech_rate']['calibration_test'][key]
                                 for key in ('version', 'effective_characters')},
            'characters_per_five_seconds': deepcopy(policy['speech_rate']['characters_per_five_seconds']),
            'rate_increment': .05, 'workflow_id': WORKFLOW_ID,
            'budget_rh_coins': policy['avatar_generation']['budget_rh_coins_per_video'],
            'paid_stages_authorized': True}
