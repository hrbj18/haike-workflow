"""Import one private Markdown configuration without contacting any service.

The only accepted payload is one fenced ``haike-config`` JSON object. Existing
nonempty values win unless --replace is explicit. No account database, Cookie,
provider verification receipt or paid operation is imported.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = 'Haike_video/.backlot/'
MODE_PATH = PRIVATE + 'service-mode.json'
GATEWAY_PATH = PRIVATE + 'haike-api/client-config.json'
RELAY_PATH = PRIVATE + 'studio-ai/relay.json'
ASR_PATH = PRIVATE + 'studio-asr/policy.json'
BUDGET_PATH = PRIVATE + 'internal-services/budget-policy.json'
ENV_PATH = 'Haike_video/.env.secrets.local'
COPY_PATH = 'copy_skill/copy_skill-main/config/content_intelligence.local.json'
AUDIO_PATH = PRIVATE + 'audio-center-internal/local-machine/'
PROVIDERS = {
    'bailian': {'api_key': 'DASHSCOPE_API_KEY', 'workspace_id': 'DASHSCOPE_WORKSPACE_ID',
        'asr_storage': 'BAILIAN_ASR_STORAGE', 'oss_endpoint': 'BAILIAN_OSS_ENDPOINT',
        'oss_bucket': 'BAILIAN_OSS_BUCKET', 'oss_access_key_id': 'BAILIAN_OSS_ACCESS_KEY_ID',
        'oss_access_key_secret': 'BAILIAN_OSS_ACCESS_KEY_SECRET'},
    'tencent': {'secret_id': 'TENCENT_SECRET_ID', 'secret_key': 'TENCENT_SECRET_KEY',
        'tts_region': 'TENCENT_TTS_REGION', 'asr_region': 'TENCENT_ASR_REGION'},
    'runninghub': {'api_key': 'RUNNINGHUB_API_KEY', 'base_url': 'RUNNINGHUB_BASE_URL',
        'workflow_id': 'RUNNINGHUB_WORKFLOW_ID', 'workflow_profile': 'RUNNINGHUB_WORKFLOW_PROFILE',
        'workflow_template': 'RUNNINGHUB_WORKFLOW_TEMPLATE'},
    'text-ai': {'api_key': 'OPENAI_API_KEY', 'base_url': 'OPENAI_BASE_URL',
        'model': 'OPENAI_TEXT_MODEL', 'vision_model': 'OPENAI_VISION_MODEL'},
    'doubao-text': {'api_key': 'DOUBAO_API_KEY', 'base_url': 'DOUBAO_BASE_URL', 'model': 'DOUBAO_TEXT_MODEL'},
    'doubao-speech': {'api_key': 'DOUBAO_SPEECH_API_KEY', 'voice_type': 'DOUBAO_SPEECH_VOICE_TYPE',
        'resource_id': 'DOUBAO_SPEECH_PUBLIC_RESOURCE_ID'},
    'doubao-asr': {'api_key': 'DOUBAO_ASR_API_KEY', 'mode': 'DOUBAO_ASR_MODE',
        'flash_resource_id': 'DOUBAO_ASR_FLASH_RESOURCE_ID', 'standard_resource_id': 'DOUBAO_ASR_STANDARD_RESOURCE_ID',
        'public_base_url': 'BACKLOT_PUBLIC_BASE_URL', 'media_signing_secret': 'DOUBAO_ASR_MEDIA_SIGNING_SECRET'},
    'pexels': {'api_key': 'PEXELS_API_KEY'}, 'pixabay': {'api_key': 'PIXABAY_API_KEY'},
}
SECRET_FIELDS = {'api_key', 'secret_id', 'secret_key', 'oss_access_key_id',
                 'oss_access_key_secret', 'media_signing_secret'}
TOP = {'schema_version', 'services', 'haike', 'providers', 'ai_relay', 'crawler',
       'asr', 'budget', 'voices', 'avatar_defaults'}
PRESET = {'voice', 'portrait_path', 'speech_rate', 'template_id', 'target_duration_seconds',
          'max_charge_micros', 'allow_graphic_fallback', 'network_materials_enabled'}
MODEL_BUDGETS = {'haike/text', 'haike/avatar', 'haike/tencent-asr', 'haike/doubao-asr', 'haike/bailian-asr'}


class ConfigurationError(ValueError):
    """Only application-owned, redacted messages may be printed."""


def fail(message):
    raise ConfigurationError(message)


def shape(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        fail(label + ' 包含不支持的字段或不是对象')


def string(value, label, maximum=2048):
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 for c in value):
        fail(label + ' 需要不含控制字符的短文本')
    return value.strip()


def url(value, label, suffix=None):
    if not value:
        return
    try:
        parsed = urlsplit(value)
        valid = (parsed.hostname and not parsed.username and not parsed.password
                 and not parsed.query and not parsed.fragment and
                 parsed.scheme in {'http', 'https'})
        _ = parsed.port
    except ValueError:
        valid = False
    if not valid or (suffix is not None and parsed.path.rstrip('/') != suffix):
        fail(label + ' 需要不含账号密码、查询参数或片段的 HTTP(S) 地址，并使用正确接口路径')


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            fail('JSON 不允许重复字段')
        result[key] = value
    return result


def read_document(path):
    if path.suffix.lower() != '.md' or path.stat().st_size > 1024 * 1024:
        fail('配置文档需要 1 MB 内的 Markdown 文件')
    content = path.read_text(encoding='utf-8-sig')
    blocks = re.findall(r'^```haike-config[ \t]*\r?\n(.*?)^```[ \t]*\r?$', content, re.M | re.S)
    if len(blocks) != 1:
        fail('配置文档必须恰好包含一个 haike-config JSON 代码块')
    try:
        data = json.loads(blocks[0], object_pairs_hook=pairs,
                          parse_constant=lambda _: fail('JSON 不允许非有限数值'))
    except json.JSONDecodeError:
        fail('配置块不是有效 JSON；未显示文档内容')
    validate(data)
    return data


def validate(data):
    shape(data, TOP, '配置')
    if type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        fail('schema_version 必须为 1')
    mode = data.get('services', {})
    shape(mode, {'mode', 'audio_mode'}, 'services')
    if any(value not in {'gateway', 'internal'} for value in mode.values()):
        fail('services 模式只支持 gateway 或 internal')
    for section, suffix in (('haike', '/v2'), ('ai_relay', '/v1')):
        allowed = {'base_url', 'api_key'} | ({'use_text_ai', 'image_model', 'chat_model', 'network_sources'} if section == 'ai_relay' else set())
        values = data.get(section, {})
        shape(values, allowed, section)
        for name, value in values.items():
            if name == 'use_text_ai':
                if type(value) is not bool: fail('ai_relay.use_text_ai 需要布尔值')
            elif name == 'network_sources':
                if value not in [['pexels'], ['douyin', 'pexels']]: fail('network_sources 只支持 pexels 或 douyin 后接 pexels')
            else:
                value = string(value, section + '.' + name)
                if name == 'base_url': url(value, section + '.base_url', suffix)
                if name == 'api_key' and value and (len(value) < 8 or any(c.isspace() for c in value)):
                    fail(section + '.api_key 格式无效')
                if name == 'image_model' and value not in {'gpt-image-2', 'gpt-image-1.5', 'gpt-image-1'}:
                    fail('ai_relay.image_model 尚未接入')
                if name == 'chat_model' and not re.fullmatch(r'[A-Za-z0-9_./:-]{1,160}', value):
                    fail('ai_relay.chat_model 格式无效')
    providers = data.get('providers', {})
    shape(providers, PROVIDERS, 'providers')
    for provider, values in providers.items():
        shape(values, PROVIDERS[provider], 'providers.' + provider)
        for name, value in values.items():
            value = string(value, 'providers.' + provider + '.' + name)
            if name in SECRET_FIELDS and any(c.isspace() for c in value): fail('供应商凭据不允许空白字符')
            if name.endswith('base_url') or name == 'oss_endpoint': url(value, '供应商地址')
    crawler = data.get('crawler', {})
    shape(crawler, {'chrome_path', 'crawler_root', 'douyin_commercial_authorized', 'authorized_video_ids'}, 'crawler')
    for key in ('chrome_path', 'crawler_root'):
        if key in crawler: string(crawler[key], 'crawler.' + key)
    if 'douyin_commercial_authorized' in crawler and type(crawler['douyin_commercial_authorized']) is not bool:
        fail('采集许可配置需要布尔值')
    ids = crawler.get('authorized_video_ids', [])
    if not isinstance(ids, list) or len(ids) > 1000 or any(not isinstance(v, str) or not re.fullmatch(r'[0-9]{1,40}', v) for v in ids):
        fail('已获素材使用权的视频编号列表无效')
    asr = data.get('asr', {})
    shape(asr, {'provider'}, 'asr')
    if asr.get('provider', 'gateway') not in {'gateway', 'bailian'}: fail('asr.provider 只支持 gateway 或 bailian')
    if 'budget' in data:
        budget = data['budget']
        shape(budget, {'per_call_micros', 'daily_limit_micros', 'audio_pricing'}, 'budget')
        if not {'per_call_micros', 'daily_limit_micros'} <= set(budget): fail('budget 需要每次及每日采购上限')
        limits = budget['per_call_micros']
        shape(limits, MODEL_BUDGETS, 'budget.per_call_micros')
        for value in [budget['daily_limit_micros'], *limits.values()]:
            if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,9}', value) or int(value) > 10**9:
                fail('采购预算需要正整数微元字符串，最高 1000 元')
        pricing = budget.get('audio_pricing', {})
        if not isinstance(pricing, dict) or len(pricing) > 50: fail('音频价格配置无效')
        for name, tariff in pricing.items():
            if not re.fullmatch(r'(?:tts|clone):(?:bailian|tencent|doubao):[A-Za-z0-9_.:-]{1,100}', name):
                fail('音频价格必须绑定已支持的供应商与上游型号')
            shape(tariff, {'fixed_micros', 'per_character_micros', 'free_confirmed'}, '音频价格')
            if any(type(tariff.get(k, 0)) is not int or not 0 <= tariff.get(k, 0) <= 10**9 for k in ('fixed_micros', 'per_character_micros')):
                fail('音频价格需要非负整数微元')
            if 'free_confirmed' in tariff and type(tariff['free_confirmed']) is not bool: fail('免费价格必须明确确认')
            if not tariff.get('fixed_micros', 0) and not tariff.get('per_character_micros', 0) and tariff.get('free_confirmed') is not True:
                fail('未知音频价格不能记为免费')
    voices = data.get('voices', [])
    if not isinstance(voices, list) or len(voices) > 24: fail('voices 需要最多 24 个音色映射')
    aliases = set()
    for voice in voices:
        shape(voice, {'alias', 'name', 'provider', 'voice_id', 'model_id', 'resource_id', 'speech_rate'}, 'voices')
        if not {'alias', 'name', 'provider', 'voice_id'} <= set(voice): fail('音色映射缺少必需字段')
        for key in ('alias', 'name', 'provider', 'voice_id', 'model_id', 'resource_id'):
            if key in voice: string(voice[key], '音色映射.' + key, 256)
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,48}', voice['alias']) or voice['alias'] in aliases: fail('音色别名无效或重复')
        aliases.add(voice['alias'])
        if not voice['name'] or len(voice['name']) > 48 or voice['provider'] not in {'bailian', 'tencent', 'doubao'}:
            fail('音色名称或供应商无效')
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,256}', voice['voice_id']): fail('上游音色编号无效')
        if voice['provider'] == 'bailian' and voice.get('model_id') not in {'cosyvoice-v3.5-flash', 'qwen-audio-3.1-tts-flash'}:
            fail('百炼私人音色必须绑定其已支持的配音模型')
        if voice['provider'] == 'tencent' and not re.fullmatch(r'[0-9]{1,10}', voice['voice_id']): fail('腾讯音色编号需要数字')
        if 'speech_rate' in voice: number(voice['speech_rate'], .5, 2, '音色倍率')
    preset = data.get('avatar_defaults', {})
    shape(preset, PRESET, 'avatar_defaults')
    for key, value in preset.items():
        if key in {'voice', 'portrait_path', 'template_id'}: string(value, 'avatar_defaults.' + key)
        elif key == 'speech_rate': number(value, .5, 2, '默认倍率')
        elif key == 'target_duration_seconds': number(value, 1, 120, '默认时长')
        elif key == 'max_charge_micros':
            if type(value) is not int or not 1 <= value <= 10**9: fail('每条预算需要正整数微元')
        elif type(value) is not bool: fail('口播开关需要布尔值')


def number(value, low, high, label):
    if type(value) not in {int, float} or not math.isfinite(value) or not low <= value <= high:
        fail(label + ' 超出支持范围')


def local_path(root, relative):
    root = root.resolve()
    path = root / relative
    if not path.resolve().is_relative_to(root): fail('配置目标超出项目目录')
    for parent in [path, *path.parents]:
        if parent == root.parent: break
        if parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()):
            fail('配置目标不能是链接或联接目录')
    return path


def read_json(root, relative):
    path = local_path(root, relative)
    if not path.exists(): return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=pairs)
    except (ValueError, UnicodeError): fail('已有本地 JSON 配置无效；保留原文件')
    if not isinstance(data, dict): fail('已有本地配置不是对象；保留原文件')
    return data


def env_helper():
    spec = importlib.util.spec_from_file_location('_user_config_env', ROOT / 'Haike_video/scripts/configure_core_secrets.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


def render_json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def merge(current, requested, replace, prefix, actions):
    result = deepcopy(current)
    for key, value in requested.items():
        if value is None or value == '': continue
        label = prefix + '.' + key
        old = current.get(key)
        if isinstance(value, dict):
            if old is not None and not isinstance(old, dict): fail('已有配置字段类型冲突；保留原文件')
            result[key] = merge(old or {}, value, replace, label, actions)
        else:
            action = 'same' if old == value else 'create' if old is None or old == '' else 'update' if replace else 'preserve'
            actions.append({'field': label, 'action': action})
            if action in {'create', 'update'}: result[key] = value
    return result


def protect_endpoint(current, requested, replace):
    if (replace and current.get('api_key') and requested.get('base_url')
            and requested['base_url'].rstrip('/') != str(current.get('base_url', '')).rstrip('/')
            and not requested.get('api_key')):
        fail('更换接口地址必须同时明确提供该接口的 Key；不会向新地址复用旧 Key')


def prepare(root, data, document_dir, replace=False):
    """Create an in-memory write plan. No service imports, requests or writes."""
    validate(data)
    root, document_dir = Path(root).resolve(), Path(document_dir).resolve()
    actions, documents = [], {}
    helper = env_helper()
    old_env = helper.read_env(local_path(root, ENV_PATH))
    env_updates = {}
    for provider, values in data.get('providers', {}).items():
        mapping = PROVIDERS[provider]
        current = {name: old_env.get(variable, '') for name, variable in mapping.items()}
        protect_endpoint(current, values, replace)
        updated = merge(current, values, replace, 'providers.' + provider, actions)
        env_updates.update({mapping[key]: value for key, value in updated.items() if value and value != current.get(key)})
    environment = {**old_env, **env_updates}

    def configure(relative, value, label):
        old = read_json(root, relative)
        new = merge(old, value, replace, label, actions)
        if new != old: documents[relative] = new
        return new

    mode = configure(MODE_PATH, data.get('services', {}), 'services')
    effective_mode = mode.get('mode', 'gateway')
    if effective_mode == 'internal' and mode.get('audio_mode', 'internal') != 'internal':
        fail('全直连模式的 audio_mode 必须为 internal')
    gateway_data = data.get('haike', {})
    protect_endpoint(read_json(root, GATEWAY_PATH), gateway_data, replace)
    gateway = configure(GATEWAY_PATH, gateway_data, 'haike')
    if GATEWAY_PATH in documents:
        documents[GATEWAY_PATH].pop('checked_at', None)  # A saved Key is not a connection test.
    relay_data = {k: v for k, v in data.get('ai_relay', {}).items() if k != 'use_text_ai'}
    if data.get('ai_relay', {}).get('use_text_ai'):
        inherited = {'api_key': environment.get('OPENAI_API_KEY', ''), 'base_url': environment.get('OPENAI_BASE_URL', '')}
        if not all(inherited.values()): fail('use_text_ai 需要已有或本次配置的文本 Key 和地址')
        relay_data = {**inherited, **{k: v for k, v in relay_data.items() if v}}
        if environment.get('OPENAI_TEXT_MODEL') and not relay_data.get('chat_model'):
            relay_data['chat_model'] = environment['OPENAI_TEXT_MODEL']
        url(relay_data['base_url'], 'AI 分镜地址', '/v1')
    crawler = data.get('crawler', {})
    for name in ('chrome_path', 'crawler_root'):
        if crawler.get(name):
            path = Path(crawler[name])
            relay_data[name] = str(path if path.is_absolute() else root / path)
    if 'douyin_commercial_authorized' in crawler:
        relay_data['douyin_commercial_authorized'] = crawler['douyin_commercial_authorized']
    if 'authorized_video_ids' in crawler: relay_data['douyin_authorized_video_ids'] = crawler['authorized_video_ids']
    relay_old = read_json(root, RELAY_PATH)
    protect_endpoint(relay_old, relay_data, replace)
    relay = configure(RELAY_PATH, relay_data, 'ai_relay')
    if RELAY_PATH in documents and any(relay.get(k) != relay_old.get(k) for k in ('api_key', 'base_url', 'image_model')):
        documents[RELAY_PATH]['image_verified'] = False
        for key in ('image_verified_for', 'image_verification'): documents[RELAY_PATH].pop(key, None)
    if crawler.get('chrome_path'):
        configure(COPY_PATH, {'media_crawler': {'chrome_path': relay_data['chrome_path']}}, 'collection')
    asr_old = read_json(root, ASR_PATH)
    asr_data = {}
    if data.get('asr', {}).get('provider') == 'gateway': asr_data = {'default_provider': 'gateway'}
    elif data.get('asr', {}).get('provider') == 'bailian': asr_data = {'default_provider': 'bailian', 'bailian_enabled': True}
    asr = configure(ASR_PATH, asr_data, 'asr')
    if asr.get('default_provider') == 'bailian' and (not asr_old or any(k in env_updates for k in ('DASHSCOPE_API_KEY', 'DASHSCOPE_WORKSPACE_ID'))):
        asr = {**asr, 'verified': False}
        documents[ASR_PATH] = asr
    budget = configure(BUDGET_PATH, data.get('budget', {}), 'budget')
    if (data.get('voices') or data.get('avatar_defaults')) and effective_mode != 'internal':
        fail('音色映射与预设离线导入仅支持全直连 internal 模式；网关/混合模式必须先核验账号身份')
    if data.get('voices'): actions.append({'field': 'voices', 'action': 'merge_local_catalog'})
    if data.get('avatar_defaults'): actions.append({'field': 'avatar_defaults', 'action': 'update' if replace else 'fill_missing'})
    preset = deepcopy(data.get('avatar_defaults', {}))
    if preset.get('portrait_path'):
        path = Path(preset['portrait_path'])
        path = path if path.is_absolute() else document_dir / path
        if not path.is_file() or path.is_symlink() or path.suffix.lower() not in {'.png', '.jpg', '.jpeg'} or path.stat().st_size > 20 * 1024**2:
            fail('默认人物图需要可读的 20 MB 内 PNG/JPEG 本地文件')
        preset['portrait_path'] = str(path.resolve())
    return {'root': root, 'documents': documents, 'environment': environment, 'env_updates': env_updates,
            'actions': actions, 'data': deepcopy(data), 'preset': preset, 'replace': replace,
            'mode': effective_mode, 'gateway': gateway, 'relay': relay, 'asr': asr, 'budget': budget}


@contextmanager
def offline_environment(environment):
    previous = dict(os.environ)
    original_connect, original_connect_ex, original_getaddrinfo = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo
    def denied(*args, **kwargs): fail('离线初始化禁止访问网络或本机服务')
    try:
        for fields in PROVIDERS.values():
            for name in fields.values(): os.environ.pop(name, None)
        os.environ.update(environment)
        os.environ['PYTHON_DOTENV_DISABLED'] = '1'
        socket.socket.connect = socket.socket.connect_ex = socket.getaddrinfo = denied
        yield
    finally:
        socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = original_connect, original_connect_ex, original_getaddrinfo
        os.environ.clear()
        os.environ.update(previous)


def stage_audio(plan, staging):
    """Reuse local voice/preset APIs in a private scratch tree; never invent receipts."""
    data, root = plan['data'], plan['root']
    if not (data.get('voices') or data.get('avatar_defaults')): return
    source = str(ROOT / 'Haike_video')
    if source not in sys.path: sys.path.insert(0, source)
    with offline_environment(plan['environment']):
        from backlot.studio_audio_internal import InternalAudioCenter, LegacyAudioBackend
        from backlot.studio_avatar_defaults import AvatarDefaults
        private = staging / 'Haike_video/.backlot'
        private.mkdir(parents=True, exist_ok=True)
        (private / 'service-mode.json').write_bytes(render_json({'mode': 'internal', 'audio_mode': 'internal'}))
        directory = staging / AUDIO_PATH
        for name in ('legacy/audio_center.json', 'preferences.json', 'avatar-defaults.json'):
            existing = read_json(root, AUDIO_PATH + name)
            if existing:
                target = directory / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(local_path(root, AUDIO_PATH + name).read_bytes())
        backend = LegacyAudioBackend(directory)
        # Registration normally refreshes the old UI, including its Qwen probe.
        # This isolated backend is used only for the existing local record writer.
        backend.center.read_audio_center = lambda: {}
        center = InternalAudioCenter(SimpleNamespace(private=private), backend=backend)
        aliases = {}
        for voice in data.get('voices', []):
            profiles = backend.catalog()
            matching = [p for p in profiles if p.get('provider_id') == voice['provider']
                        and p.get('provider_voice_id') == voice['voice_id']
                        and (voice['provider'] != 'bailian' or p.get('model_id') == voice.get('model_id'))]
            if not matching:
                backend.center.add_custom_cloud_voice({key: value for key, value in voice.items() if key not in {'alias', 'speech_rate'}})
                matching = [p for p in backend.catalog() if p.get('provider_id') == voice['provider']
                            and p.get('provider_voice_id') == voice['voice_id']
                            and (voice['provider'] != 'bailian' or p.get('model_id') == voice.get('model_id'))]
            if len(matching) != 1: fail('音色映射不能唯一对应本机目录')
            ident = aliases[voice['alias']] = matching[0]['id']
            current = center._preferences().get('voices', {}).get(ident, {})
            if 'speech_rate' in voice and (plan['replace'] or 'speech_rate' not in current):
                center.preferences({'speech_rate': voice['speech_rate']}, ident)
        preset = dict(plan['preset'])
        requested = {k: v for k, v in preset.items() if k not in {'voice', 'portrait_path'}}
        if preset.get('voice'): requested['voice_id'] = aliases.get(preset['voice'], preset['voice'])
        defaults = AvatarDefaults(center)
        saved = defaults._saved()
        if preset.get('portrait_path') and (plan['replace'] or not saved['values'].get('portrait_file_id')):
            path = Path(preset['portrait_path'])
            requested['portrait_file_id'] = center.upload(path.read_bytes(), 'image', path.name)['id']
        updates = {k: v for k, v in requested.items() if (plan['replace'] or saved['values'].get(k) is None) and saved['values'].get(k) != v}
        if updates:
            defaults.save({'expected_revision': saved['revision'], 'expected_scope_id': defaults.scope_id, 'values': updates})
        final_voice = updates.get('voice_id', saved['values'].get('voice_id'))
        if final_voice and (plan['replace'] or not center._preferences().get('voice_id')):
            center.preferences({'voice_id': final_voice})


def apply(plan):
    """Validate/stage everything before atomically replacing any target file."""
    root = plan['root']
    with tempfile.TemporaryDirectory(prefix='haike-user-config-') as temporary:
        staging = Path(temporary)
        stage_audio(plan, staging)
        # The scratch mode is only for account-safe API calls; never overrides
        # the caller's merged service-mode configuration.
        (staging / MODE_PATH).unlink(missing_ok=True)
        for relative, data in plan['documents'].items():
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(render_json(data))
        if plan['env_updates']:
            target = staging / ENV_PATH
            target.parent.mkdir(parents=True, exist_ok=True)
            existing = local_path(root, ENV_PATH)
            if existing.exists(): target.write_bytes(existing.read_bytes())
            env_helper().update_env_file(target, plan['env_updates'])
        staged = [path for path in staging.rglob('*') if path.is_file() and path.name != '.lock']
        original = {}
        for path in staged:
            relative = path.relative_to(staging).as_posix()
            target = local_path(root, relative)
            if target.exists() and target.read_bytes() == path.read_bytes(): continue
            original[relative] = target.read_bytes() if target.exists() else None
        written = []
        try:
            for relative in original:
                write_private(local_path(root, relative), (staging / relative).read_bytes())
                written.append(relative)
        except Exception:
            for relative in reversed(written):
                target = local_path(root, relative)
                if original[relative] is None: target.unlink(missing_ok=True)
                else: write_private(target, original[relative])
            raise
    return len(written)


def write_private(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.configure-user-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def report(plan, command, written=0):
    env, root = plan['environment'], plan['root']
    mode, relay = plan['mode'], plan['relay']
    preset = read_json(root, AUDIO_PATH + 'avatar-defaults.json').get('values', {}) if mode == 'internal' else {}
    asr_provider = plan['asr'].get('default_provider', 'gateway')
    required_budget_models = {'haike/avatar', 'haike/bailian-asr' if asr_provider == 'bailian' else 'haike/tencent-asr'}
    per_call = plan['budget'].get('per_call_micros', {})
    def positive_budget(value):
        return isinstance(value, str) and bool(re.fullmatch(r'[1-9][0-9]{0,9}', value)) and int(value) <= 10**9
    voice_provider = 'bailian' if str(preset.get('voice_id', '')).startswith('pub_') else None
    if preset.get('voice_id') and voice_provider is None:
        profiles = read_json(root, AUDIO_PATH + 'legacy/audio_center.json').get('custom_cloud_profiles', [])
        voice_provider = next((p.get('provider_id') for p in profiles if isinstance(p, dict) and p.get('id') == preset['voice_id']), None)
    checks = {'haike_key': bool(plan['gateway'].get('api_key') and plan['gateway'].get('base_url')),
        'bailian_key': bool(env.get('DASHSCOPE_API_KEY')),
        'tencent_asr': bool(env.get('TENCENT_SECRET_ID') and env.get('TENCENT_SECRET_KEY')),
        'runninghub_key': bool(env.get('RUNNINGHUB_API_KEY')),
        'ai_relay': bool(relay.get('api_key') and relay.get('base_url')),
        'pexels_key': bool(env.get('PEXELS_API_KEY')),
        'internal_budget': (isinstance(per_call, dict) and all(positive_budget(per_call.get(k)) for k in required_budget_models)
                            and positive_budget(plan['budget'].get('daily_limit_micros'))),
        'default_voice': bool(voice_provider), 'default_portrait': bool(preset.get('portrait_file_id'))}
    checks['tts_credentials'] = bool({'bailian': env.get('DASHSCOPE_API_KEY'),
        'tencent': env.get('TENCENT_SECRET_ID') and env.get('TENCENT_SECRET_KEY'),
        'doubao': env.get('DOUBAO_SPEECH_API_KEY')}.get(voice_provider))
    missing = []
    if mode == 'internal':
        required = ['tts_credentials', 'runninghub_key', 'internal_budget']
        task_budget = preset.get('max_charge_micros')
        requested_budget = plan['preset'].get('max_charge_micros')
        if requested_budget is not None and (plan['replace'] or task_budget is None):
            task_budget = requested_budget
        if task_budget is not None:
            checks['default_task_budget'] = (
                type(task_budget) is int and checks['internal_budget']
                and sum(int(per_call[k]) for k in required_budget_models) < task_budget
            )
            required.append('default_task_budget')
        if asr_provider == 'bailian':
            checks['bailian_asr_verified'] = plan['asr'].get('verified') is True
            required += ['bailian_key', 'bailian_asr_verified']
        else: required.append('tencent_asr')
    else: required = ['haike_key']
    if preset.get('network_materials_enabled') or plan['preset'].get('network_materials_enabled'):
        sources = relay.get('network_sources', ['douyin', 'pexels'])
        required += ['ai_relay', 'pexels_key'] if mode == 'internal' and 'pexels' in sources else ['ai_relay']
        if 'douyin' in sources:
            crawler = Path(relay.get('crawler_root') or root / 'copy_skill/copy_skill-main/third_party/MediaCrawler')
            checks['crawler_installed'] = (crawler / 'main.py').is_file() and (crawler / '.venv/Scripts/python.exe').is_file()
            checks['chrome_path'] = bool(relay.get('chrome_path')) and Path(relay['chrome_path']).is_file()
            checks['crawler_permission'] = relay.get('douyin_commercial_authorized') is True
            required += ['crawler_installed', 'chrome_path', 'crawler_permission']
    if mode == 'internal':
        required.append('default_voice')
        if plan['preset'].get('portrait_path'): required.append('default_portrait')
    missing = [key for key in required if not checks[key]]
    return {'schema_version': 1, 'command': command, 'mode': mode, 'written_files': written,
        'configuration_complete': not missing, 'execution_verified': False, 'network_calls': 0,
        'checks': checks, 'missing': missing, 'actions': plan['actions'],
        'next': ['运行本地环境诊断', '扫码并分别检查素材和发布登录', '按授权验证单条及夜间批次，保存原回执']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['plan', 'apply', 'check'])
    parser.add_argument('--file', type=Path, required=True, help='含一个 haike-config 块的私有 Markdown')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--replace', action='store_true', help='只更新文档明确给出的字段；默认保留已有值')
    args = parser.parse_args(argv)
    try:
        data = read_document(args.file)
        # Portable Python supplies stdlib; image normalization and the existing
        # voice catalogue belong to the installed production environment.
        if args.command == 'apply' and (data.get('voices') or data.get('avatar_defaults')):
            interpreter = args.root.resolve() / 'Haike_video/.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            if interpreter.is_file() and interpreter.resolve() != Path(sys.executable).resolve():
                command = [str(interpreter), '-s', str(Path(__file__).resolve()), 'apply',
                           '--root', str(args.root.resolve()), '--file', str(args.file.resolve())]
                if args.replace: command.append('--replace')
                child_env = dict(os.environ, PYTHON_DOTENV_DISABLED='1')
                return subprocess.run(command, env=child_env, timeout=120).returncode
        plan = prepare(args.root, data, args.file.resolve().parent, args.replace)
        written = apply(plan) if args.command == 'apply' else 0
        if args.command == 'check':
            # Check the installed values, not the proposed missing credentials.
            installed = prepare(args.root, {'schema_version': 1}, args.file.resolve().parent)
            installed['preset'] = plan['preset']
            installed['actions'] = plan['actions']
            plan = installed
        result = report(plan, args.command, written)
        print(json.dumps(result, ensure_ascii=False))
        return 1 if args.command == 'check' and not result['configuration_complete'] else 0
    except ConfigurationError as error:
        print(json.dumps({'ok': False, 'error': str(error), 'network_calls': 0}, ensure_ascii=False))
    except Exception:
        print(json.dumps({'ok': False, 'error': '配置未完成；请核对文件格式、依赖与本地权限。未输出任何私有内容。', 'network_calls': 0}, ensure_ascii=False))
    return 2


if __name__ == '__main__':
    # A JSON result is also consumed by Agent/setup subprocesses on Windows.
    # Keep it UTF-8 independently of the console's current ANSI code page.
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
