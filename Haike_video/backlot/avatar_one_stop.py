"""One durable dialogue-driven production task, shared by HTTP, CLI and Studio."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

from backlot.avatar_one_stop_policy import (CALIBRATION_MODE, POLICY, digest, fingerprint, load_policy,
                                           public_defaults, validate_rate)
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError
from lib.bailian_speech import operation_lock

IDENTITY = re.compile(r'os_[a-f0-9]{32}')
STAGES = ('refinement', 'clone', 'audition', 'narration', 'asr', 'storyboard',
          'avatar', 'composition', 'quality')
LABELS = {'refinement': '图片精修', 'clone': '克隆声音', 'audition': '测量试听与校准语速',
          'narration': '生成完整配音', 'asr': '识别字幕时间轴', 'storyboard': '分镜与素材挑选',
          'avatar': '高质量数字人', 'composition': '视频合成', 'quality': '成片检查'}


def now():
    return datetime.now(timezone.utc).isoformat()


class OneStop:
    def __init__(self, studio, *, tools=None, policy_path=POLICY):
        self.studio, self.policy_path = studio, Path(policy_path)
        if tools is None:
            from backlot.avatar_one_stop_tools import OneStopTools
            tools = OneStopTools(studio)
        self.tools = tools
        self.scope = fingerprint(str(tools.account))
        self.directory = studio.private/'avatar-one-stop'/self.scope[:32]

    def _folder(self, identity):
        if not isinstance(identity, str) or not IDENTITY.fullmatch(identity):
            raise WorkError('一条龙任务编号无效')
        return self.directory/identity

    def _read(self, identity):
        self.tools.verify_scope()
        path = self._folder(identity)/'task.json'
        if not path.is_file():
            raise WorkError('一条龙任务不存在或不属于当前账号', 'missing')
        value = json.loads(path.read_text('utf-8'))
        if value['scope'] != self.scope:
            raise WorkError('一条龙任务不属于当前账号', 'forbidden')
        return value

    def _verify_inputs(self, value):
        for source in [*value['inputs'].values(), value['reference']]:
            if not Path(source['path']).is_file() or digest(source['path']) != source['sha256']:
                raise WorkError('原任务输入已变化，请恢复原始素材后继续，不能替换后重复付费', 'conflict')
        if value['policy']['avatar_generation']['workflow_id'] != '2112180419025260546' or not 0 < value['budget_rh_coins'] <= 2000:
            raise WorkError('原任务的高质量工作流或累计预算无效', 'conflict')
        outputs = {'refinement': ('refinement/result.png', 'sha256'), 'audition': ('audition.wav', 'audio_sha256'),
                   'narration': ('narration.wav', 'audio_sha256'), 'asr': ('asr.json', 'sha256'),
                   'storyboard': ('storyboard-approved.json', 'sha256')}
        for name, (relative, field) in outputs.items():
            stage = value['stages'].get(name, {})
            expected = (stage.get('result') or {}).get(field)
            if stage.get('status') == 'succeeded' and expected:
                path = self._folder(value['id'])/relative
                if not path.is_file() or digest(path) != expected:
                    raise WorkError('已完成的'+LABELS[name]+'产物已变化，请恢复原产物后继续', 'conflict')

    def _save(self, value):
        value['updated_at'] = now()
        value['revision'] = value.get('revision', 0)+1
        atomic_private(self._folder(value['id'])/'task.json', value)

    def defaults(self):
        return public_defaults(load_policy(self.policy_path))

    def create(self, data):
        allowed = {'draft_id', 'portrait_id', 'audio_id', 'audio_role', 'request_id', 'consent', 'text', 'title', 'speech_rate'}
        if not isinstance(data, dict) or set(data)-allowed or data.get('consent') is not True:
            raise WorkError('请提供人物图和声音样本，并确认本次素材使用权')
        self.tools.verify_scope()
        policy = load_policy(self.policy_path)
        if 'speech_rate' in data:
            policy['speech_rate']['fixed_rate'] = validate_rate(data['speech_rate'])
            policy['speech_rate']['rate_source'] = 'explicit_user_request'
        preflight = getattr(self.tools, 'preflight', None)
        readiness = preflight(policy) if preflight else {}
        draft = self.studio.draft(data.get('draft_id'))
        if draft['kind'] != 'avatar':
            raise WorkError('一条龙任务需关联数字人口播草稿')
        paths = {kind: self.studio.asset(data.get(field), draft['id'])
                 for kind, field in (('portrait', 'portrait_id'), ('sample', 'audio_id'))}
        if paths['portrait'].suffix.lower() not in {'.jpg', '.jpeg', '.png'}:
            raise WorkError('人物图需为PNG或JPG照片')
        if paths['sample'].suffix.lower() not in {'.wav', '.mp3', '.m4a', '.ogg'}:
            raise WorkError('声音样本需为有效录音文件')
        role = data.get('audio_role', 'sample')
        if role not in {'sample', 'narration'}:
            raise WorkError('音频用途需为声音样本或完整口播')
        script = deepcopy(policy['script'])
        if 'text' in data:
            if not isinstance(data['text'], str) or not data['text'].strip() or len(data['text']) > 20000:
                raise WorkError('口播原文需为1至20000字')
            script['text'] = data['text'].strip()
            import hashlib
            script['text_sha256'] = hashlib.sha256(script['text'].encode()).hexdigest()
        if 'title' in data:
            if not isinstance(data['title'], str) or not data['title'].strip() or len(data['title']) > 80:
                raise WorkError('视频标题需为1至80字')
            script['title'] = data['title'].strip()
        request_id = data.get('request_id', '')
        if not isinstance(request_id, str) or len(request_id) > 100:
            raise WorkError('任务幂等编号无效')
        params = {key: policy[key] for key in ('image_refinement', 'voice_clone', 'speech_rate',
                                              'avatar_generation', 'template', 'paid_authorization')}
        signature = fingerprint({'portrait': digest(paths['portrait']), 'sample': digest(paths['sample']),
                                 'script': script, 'parameters': params, 'audio_role': role, 'request_id': request_id})
        identity = 'os_'+fingerprint([self.scope, signature])[:32]
        folder = self._folder(identity)
        with operation_lock(folder/'lock'):
            if (folder/'task.json').exists():
                return self.public(self._read(identity))
            inputs = folder/'inputs'
            inputs.mkdir(parents=True, exist_ok=True)
            for kind, path in paths.items():
                shutil.copy2(path, inputs/(kind+path.suffix.lower()))
            reference = Path(policy['image_refinement']['reference_image']['path'])
            shutil.copy2(reference, inputs/('skin-reference'+reference.suffix.lower()))
            value = {'schema': 'haike.avatar-one-stop-task/1', 'id': identity, 'scope': self.scope,
                     'draft_id': draft['id'], 'draft_revision': draft['revision'],
                     'created_at': now(), 'updated_at': now(), 'revision': 0,
                     'status': 'queued', 'stage': STAGES[0], 'signature': signature,
                     'audio_role': role,
                     'preflight': readiness,
                     'policy': policy, 'script': script,
                     'inputs': {kind: {'path': str(inputs/(kind+path.suffix.lower())), 'sha256': digest(path)}
                                for kind, path in paths.items()},
                     'reference': {'path': str(inputs/('skin-reference'+reference.suffix.lower())),
                                   'sha256': digest(reference)},
                     'stages': {}, 'paid': {}, 'reviews': {}, 'result': None,
                     'authorization': deepcopy(policy['paid_authorization']),
                     'budget_rh_coins': policy['avatar_generation']['budget_rh_coins_per_video']}
            self._save(value)
            return self.public(value)

    def public(self, value):
        labels = dict(LABELS)
        pace = value['policy']['speech_rate']
        if pace.get('calibration_mode') == CALIBRATION_MODE:
            labels.update(audition='固定文案测速', narration='整稿配音与语速校准')
        elif pace.get('calibration_mode') == 'full_text_baseline':
            labels.update(audition='确定整稿语速基准', narration='整稿配音与语速校准')
        if pace.get('fixed_rate') is not None:
            labels['audition'] = '采用指定语速'
        stages = [{'id': stage, 'label': labels[stage],
                   'status': value['stages'].get(stage, {}).get('status', 'pending')}
                  for stage in STAGES]
        current = value['stages'].get(value['stage'], {})
        candidate = (value['stages'].get('composition') or {}).get('result')
        result = value.get('result') or (candidate if (candidate or {}).get('finishing_contract') else None)
        media = {'source': f"/api/studio/one-stop/jobs/{value['id']}/files/source",
                 'sample': f"/api/studio/one-stop/jobs/{value['id']}/files/sample"}
        for stage, kind in [('refinement', 'refined'), ('audition', 'audition'), ('narration', 'narration')]:
            saved = value['stages'].get(stage, {})
            if saved.get('status') == 'succeeded' and not (saved.get('result') or {}).get('skipped'):
                media[kind] = f"/api/studio/one-stop/jobs/{value['id']}/files/{kind}"
        charges = [{'stage': key, 'provider': child.get('provider') or child['quote'].get('provider'),
                    'model': child.get('model') or child['quote'].get('provider_model'),
                    'status': child.get('status', 'quoted'),
                    'estimated_micros': child['quote']['max_charge_micros'], 'actual_cost': 'pending_receipt'}
                   for key, child in value['paid'].items() if 'quote' in child]
        avatar = value['paid'].get('avatar', {})
        narration = (value['stages'].get('narration', {}).get('result') or {})
        audition = (value['stages'].get('audition', {}).get('result') or {})
        return {'id': value['id'], 'draft_id': value['draft_id'], 'revision': value['revision'],
                'status': value['status'], 'stage': value['stage'], 'stage_label': labels[value['stage']],
                'message': value.get('message', ''), 'title': value['script']['title'],
                'stages': stages, 'next_action': current.get('agent_action') if value['status'] == 'awaiting_agent' else None,
                'media': media,
                'created_at': value['created_at'], 'updated_at': value['updated_at'],
                'template_name': '动效模板11 · 深蓝蜜桃路线',
                'budget_rh_coins': value['budget_rh_coins'],
                'charges': charges, 'avatar_usage_rh_coins': (
                    (avatar.get('known_usage_rh_coins') or 0)+avatar.get('prior_known_usage_rh_coins', 0)
                    if avatar.get('known_usage_rh_coins') is not None or avatar.get('prior_known_usage_rh_coins') else None),
                'avatar_reserved_rh_coins': (
                    (avatar.get('plan') or {}).get('reserve_coins', 0)+avatar.get('prior_exposure_rh_coins', 0)
                    if avatar.get('plan') else None),
                'revision_of': value.get('revision_of'),
                'pace': {'target': pace.get('characters_per_five_seconds'),
                         'calibration_mode': pace.get('calibration_mode'),
                         'full_characters_per_five_seconds': narration.get('characters_per_five_seconds',
                             narration['measured_cps'] * 5 if narration.get('measured_cps') is not None else None),
                         'test_characters_per_five_seconds': audition.get('characters_per_five_seconds'),
                         'test_cache_hit': audition.get('cache_hit'),
                         'full_text_accepted': narration.get('pace_check') == 'within_five_second_band'},
                'rate': (value['stages'].get('narration', {}).get('result') or {}).get('rate',
                    (value['stages'].get('audition', {}).get('result') or {}).get('rate')),
                'result': ({'work_id': result.get('work_id'),
                            'output_sha256': result['output_sha256'],
                            'review_status': 'checked' if value['status'] == 'completed' else 'pending',
                            'video_url': f"/api/studio/one-stop/jobs/{value['id']}/files/video?v={result['output_sha256']}",
                            'cover_url': f"/api/studio/one-stop/jobs/{value['id']}/files/cover?v={result['output_sha256']}"}
                           if result else None)}

    def revise(self, identity, data):
        """New immutable rate revision; reuse checked identity assets and one RH cap."""
        if (not isinstance(data, dict) or set(data)-{'speech_rate', 'reason', 'request_id', 'synthesis_seed'}
                or not isinstance(data.get('reason'), str) or not 4 <= len(data['reason']) <= 2000
                or not isinstance(data.get('request_id', ''), str) or len(data.get('request_id', '')) > 100):
            raise WorkError('语速修订需提供0.05档位倍率和本次明确修改依据')
        rate = validate_rate(data.get('speech_rate'))
        seed = data.get('synthesis_seed')
        if 'synthesis_seed' in data and (type(seed) is not int or not 0 <= seed <= 65535):
            raise WorkError('百炼合成种子需为0至65535的整数')
        original = self._read(identity)
        self._verify_inputs(original)
        if original.get('audio_role') == 'narration' or any(
                original['stages'].get(k, {}).get('status') != 'succeeded' for k in ('refinement', 'clone')):
            raise WorkError('当前任务尚无可复用的精修图/Plus音色，或输入为用户完整录音')
        revision_identity = [self.scope, identity, rate, data.get('request_id', '')]
        if seed is not None:
            revision_identity.append({'synthesis_seed': seed})
        revised_id = 'os_'+fingerprint(revision_identity)[:32]
        folder = self._folder(revised_id)
        with operation_lock(folder/'lock'):
            if (folder/'task.json').is_file():
                return self.public(self._read(revised_id))
            old_folder = self._folder(identity)
            for relative in ('inputs', 'refinement'):
                shutil.copytree(old_folder/relative, folder/relative, dirs_exist_ok=True)
            policy = deepcopy(original['policy'])
            # A new revision adopts today's explicitly configured pace target;
            # its source task and other frozen production choices stay intact.
            policy['speech_rate'] = deepcopy(load_policy(self.policy_path)['speech_rate'])
            policy['speech_rate'].update(fixed_rate=rate, rate_source='explicit_user_revision',
                                         revision_reason=data['reason'])
            if seed is not None:
                policy['speech_rate'].update(synthesis_seed=seed, rate_source='agent_pace_recovery')
            value = {key: deepcopy(original[key]) for key in ('schema', 'scope', 'draft_id', 'draft_revision',
                'audio_role', 'script', 'inputs', 'reference', 'authorization', 'budget_rh_coins')}
            preflight = getattr(self.tools, 'preflight', None)
            value['preflight'] = deepcopy(original.get('preflight')) or (preflight(policy) if preflight else {})
            for source in [*value['inputs'].values(), value['reference']]:
                source['path'] = str(folder/'inputs'/Path(source['path']).name)
            value.update(id=revised_id, policy=policy, revision=0, revision_of=identity,
                revision_reason=data['reason'], budget_group_id=original.get('budget_group_id', identity),
                signature=fingerprint([original['signature'], *revision_identity[2:]]),
                created_at=now(), updated_at=now(), status='queued', stage='audition',
                message='沿用已检查精修图和Plus音色，按本次明确倍率修订', result=None,
                stages={name:deepcopy(original['stages'][name]) for name in ('refinement', 'clone')},
                paid={}, reviews={'refinement':deepcopy(original['reviews'].get('refinement', {}))},
                reused_from={'task_id':identity, 'stages':['refinement','clone']})
            for name in ('sample_upload', 'clone'):
                if name in original['paid']:
                    value['paid'][name] = deepcopy(original['paid'][name])
                    value['paid'][name]['reused_from_task'] = identity
            if (old_folder/'storyboard-source-limits.json').is_file():
                limits = json.loads((old_folder/'storyboard-source-limits.json').read_text('utf-8'))
                # Source limits are proposed again against the new narration SHA.
                atomic_private(folder/'inherited-source-limits.json', limits)
            self._save(value)
            return self.public(value)

    def get(self, identity, *, private=False):
        value = self._read(identity)
        return value if private else self.public(value)

    def list(self, draft_id=None):
        self.tools.verify_scope()
        values = []
        for path in self.directory.glob('os_*/task.json'):
            value = self._read(path.parent.name)
            if draft_id is None or value['draft_id'] == draft_id:
                values.append(self.public(value))
        return sorted(values, key=lambda row: row['created_at'], reverse=True)

    def context(self, identity, *, private=False):
        value = self._read(identity)
        folder = self._folder(identity)
        current = value['stages'].get(value['stage'], {})
        result = {'task': self.public(value), 'script': value['script'],
                  'action': current.get('agent_action'), 'instructions': current.get('instructions')}
        if value['stage'] == 'refinement':
            result.update(prompt=value['policy']['image_refinement']['prompt'],
                          source_sha256=value['inputs']['portrait']['sha256'],
                          reference_sha256=value['reference']['sha256'])
        for name in ('asr.json', 'storyboard-proposal.json', 'storyboard-evidence.json', 'quality.json'):
            path = folder/name
            if path.is_file():
                document = json.loads(path.read_text('utf-8'))
                # Absolute media/source paths belong only in the local Agent/CLI view.
                if private:
                    result[name.removesuffix('.json')] = document
        if private:
            result['folder'] = str(folder)
            result['inputs'] = value['inputs']
            result['reference'] = value['reference']
        return result

    def advance(self, identity):
        folder = self._folder(identity)
        with operation_lock(folder/'lock'):
            value = self._read(identity)
            if value['status'] in {'completed', 'awaiting_input', 'stopped'}:
                return self.public(value)
            self._verify_inputs(value)
            for name in STAGES:
                stage = value['stages'].setdefault(name, {'status': 'pending'})
                if stage['status'] == 'succeeded':
                    continue
                value.update(stage=name, status='running', message='正在'+LABELS[name])
                stage.update(status='running')
                self._save(value)
                try:
                    self.tools.verify_scope()
                    outcome = getattr(self.tools, name)(value, folder, lambda: self._save(value))
                except WorkError as error:
                    stage.update(status='paused', error=str(error))
                    value.update(status='paused', message=str(error))
                    self._save(value)
                    return self.public(value)
                except Exception as error:
                    # Raw exceptions may contain signed URLs or supplier response data.
                    stage.update(status='paused', error='原任务已保留，请检查当前步骤并恢复')
                    value.update(status='paused', message=stage['error'])
                    atomic_private(folder/'last-error.json', {'stage': name, 'type': type(error).__name__})
                    self._save(value)
                    return self.public(value)
                stage.update(outcome)
                if stage['status'] != 'succeeded':
                    value.update(status='awaiting_agent' if stage.get('agent_action') else 'waiting',
                                 message=stage.get('message', '原步骤仍在处理，稍后继续原任务'))
                    self._save(value)
                    return self.public(value)
                self._save(value)
            value.update(status='completed', stage='quality', message='一条龙成片已完成')
            value['result'] = deepcopy(value['stages']['composition']['result'])
            self._save(value)
            return self.public(value)

    def apply(self, identity, data):
        if not isinstance(data, dict) or data.get('stage') not in {'refinement', 'storyboard', 'quality'}:
            raise WorkError('一条龙仅接收当前Agent的精修、分镜或成片检查结果')
        folder = self._folder(identity)
        with operation_lock(folder/'lock'):
            value = self._read(identity)
            self._verify_inputs(value)
            stage = data['stage']
            if value['stage'] != stage or value['status'] not in {'awaiting_agent', 'paused'}:
                raise WorkError('请先读取当前任务及其待办，再提交同一步骤结果', 'conflict')
            outcome = self.tools.apply(value, folder, data)
            value['reviews'][stage] = {k: deepcopy(data[k]) for k in
                ('reason', 'observed_sha256', 'reviewed_sheets', 'visual_passed', 'audio_review') if k in data}
            value['stages'][stage] = {**value['stages'].get(stage, {}), **outcome}
            value.update(status='queued', message='Agent检查结果已保存，可继续原任务')
            self._save(value)
            return self.public(value)

    def adopt_image(self, identity, path, *, observed_sha256, reason):
        """Local Agent adapter for built-in image tools; never exposed as a path HTTP API."""
        from PIL import Image, ImageOps
        value = self._read(identity)
        self._verify_inputs(value)
        if value['stage'] != 'refinement' or value['status'] not in {'awaiting_agent', 'paused'}:
            raise WorkError('原任务当前不在精修检查阶段，请先读取原任务', 'conflict')
        path = Path(path)
        if digest(path) != observed_sha256:
            raise WorkError('Agent检查过的图片与实际文件不同', 'conflict')
        folder = self._folder(identity)/'refinement/reviewed-assets'
        folder.mkdir(parents=True, exist_ok=True)
        original = folder/(observed_sha256+path.suffix.lower())
        if not original.is_file():
            shutil.copy2(path, original)
        target = folder/(observed_sha256+'-1024x1280.png')
        with Image.open(original) as image:
            image = ImageOps.exif_transpose(image)
            if min(image.size) < 256 or image.width*image.height > 40_000_000 or abs(image.width/image.height-.8) > .012:
                raise WorkError('精修图需为4:5附近的完整构图，请让图像工具重新输出；不能裁掉人物补尺寸')
            ImageOps.fit(image.convert('RGB'), (1024, 1280), method=Image.Resampling.LANCZOS).save(target)
        asset = self.studio.save_asset(value['draft_id'], 'agent-refined.png', 'image', target.read_bytes())
        atomic_private(folder/'adoption.json', {'agent_artifact_sha256': observed_sha256,
            'normalized_sha256': digest(target), 'asset_id': asset['id'], 'reason': reason})
        return self.apply(identity, {'stage': 'refinement', 'asset_id': asset['id'],
                                    'observed_sha256': digest(target), 'reason': reason})

    def file(self, identity, kind):
        value = self._read(identity)
        folder = self._folder(identity)
        if kind == 'source':
            return Path(value['inputs']['portrait']['path'])
        if kind == 'reference':
            return Path(value['reference']['path'])
        if kind == 'sample':
            return Path(value['inputs']['sample']['path'])
        paths = {'refined': folder/'refinement/result.png', 'audition': folder/'audition.wav',
                 'narration': folder/'narration.wav', 'cover': folder/'cover.jpg',
                 'contact-sheet': folder/'contact-sheet.jpg'}
        if kind == 'video':
            result = value.get('result') or value['stages'].get('composition', {}).get('result')
            if result and Path(result['output_path']).is_file() and digest(result['output_path']) == result['output_sha256']:
                return Path(result['output_path'])
        elif kind in paths and paths[kind].is_file():
            return paths[kind]
        raise WorkError('此步骤的实际产物尚未就绪', 'missing')
