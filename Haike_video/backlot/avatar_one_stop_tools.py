"""Existing project services behind the dialogue Agent's one-stop task."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageOps

from backlot.avatar_one_stop_policy import (CALIBRATION_MODE, CLONE_MODEL, calibrate,
                                           digest, effective_characters, validate_rate, wav_duration)
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError


def succeeded(result=None):
    return {'status': 'succeeded', 'result': result or {}}


def agent(action, instructions):
    return {'status': 'awaiting_agent', 'agent_action': action,
            'message': '当前对话Agent正在处理'+instructions, 'instructions': instructions}


def read(path):
    return json.loads(Path(path).read_text('utf-8'))


def media_command(arguments, *, timeout=180):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    pair = resolve_ffmpeg_pair()
    if not pair:
        raise WorkError('项目媒体运行时尚未安装，请运行项目诊断', 'unavailable')
    try:
        return subprocess.run([str(pair[0]), '-nostdin', '-y', '-v', 'error', *map(str, arguments)],
                              capture_output=True, check=True, timeout=timeout,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (subprocess.SubprocessError, OSError):
        raise WorkError('本地媒体处理未完成，已保留输入和原任务，请检查媒体运行时') from None


class OneStopTools:
    def __init__(self, studio, *, center=None, asr_client=None, queue=None, refinement=None):
        from backlot.studio_services import audio_mode, budget_policy, refresh_private_environment
        self.studio, self.queue, self._asr_client = studio, queue, asr_client
        refresh_private_environment()
        self.internal_audio = audio_mode(studio) == 'internal'
        if center is None:
            if self.internal_audio:
                from backlot.studio_audio_internal import InternalAudioCenter
                center = InternalAudioCenter(studio, pricing=budget_policy(studio).get('audio_pricing', {}))
            else:
                from backlot.studio_audio import AudioCenter
                center = AudioCenter(studio)
        self.center = center
        self.account = center.verify_scope()
        self.refiner = refinement

    def verify_scope(self):
        if self.center.verify_scope() != self.account:
            raise WorkError('当前账号已经变化，请回到原账号恢复一条龙任务', 'conflict')
        return self.account

    def preflight(self, policy):
        from backlot.motion_replay import resolve, verify_sources
        from backlot.avatar_one_stop_production import hq_executor
        from tools.video.video_compose import VideoCompose
        try:
            from portable.system_browser import resolve as resolve_browser
            resolve_browser()
            template = resolve(policy['template']['template_id'], policy['template']['version'])
            verify_sources(template)
            hq = hq_executor()
            hq.verify_package()
            if hq.config()['workflow_id'] != policy['avatar_generation']['workflow_id']:
                raise ValueError()
            renderer = VideoCompose()
            if not renderer._remotion_available() or not renderer._ffmpeg_available():
                raise ValueError()
        except Exception:
            raise WorkError('模板11、高清数字人执行器或媒体运行时预检未通过，请先修复本机环境', 'unavailable') from None
        return {'template_sources': 'verified', 'hq_package': 'verified', 'renderer': 'remotion',
                'media_runtime': 'available', 'provider_account_access': 'checked_at_submission'}

    def _sdk(self):
        if self._asr_client is None:
            from backlot.studio_internal_gateway import InternalClient
            self._asr_client = InternalClient(self.studio, audio_center=self.center, asr_only=True)
        return self._asr_client

    def refinement(self, value, folder, save):
        target = folder/'refinement/result.png'
        if target.is_file():
            # An Agent result is accepted only through apply(), with identity evidence.
            return agent('review_refinement', '核对现有精修图及双参考身份，采用后继续原任务')
        if self.refiner is not None:
            result = self.refiner.run(folder/'refinement', Path(value['inputs']['portrait']['path']),
                                      Path(value['reference']['path']), value['policy']['image_refinement']['prompt'])
            return agent('review_refinement', '核对双参考图精修结果；采用后继续原任务') | {'candidate': result}
        return agent('refine_portrait', '按人物原图与固定肤色参考图精修，保留身份、发型、衣着；'
                     '将1024×1280 PNG作为本草稿资产上传，并提交refinement检查回执')

    def _audio_paid(self, value, name, request, save):
        child = value['paid'].get(name)
        if child is None:
            quote = self.center.quote(request)
            if not quote.get('operation_id') or not quote.get('id'):
                raise WorkError('声音服务未返回可恢复的调用编号，请核对服务版本')
            child = value['paid'][name] = {'quote': quote, 'submitted': False,
                'provider': quote.get('provider'), 'model': quote.get('provider_model')}
            save()
        quote = child['quote']
        body = {'quote_id': quote['id'], 'operation_id': quote['operation_id'],
                'max_charge_micros': quote['max_charge_micros'], 'confirmed': True}
        if self.internal_audio:
            # Use the same machine procurement ledger as the native SDK. No new
            # RMB allowance or RH-to-RMB conversion is introduced by this flow.
            self._sdk()._reserve(quote['operation_id'], int(quote['max_charge_micros']))
        if not child['submitted']:
            child['submitted'] = True
            save()  # Parent and native child journals both precede the provider call.
            outcome = self.center.submit(body)
        else:
            try:
                self.center.operation(quote['operation_id'])
            except WorkError as error:
                if error.code != 'missing':
                    raise
                expires = quote.get('expires_at')
                if expires and datetime.fromisoformat(expires.replace('Z', '+00:00')) <= datetime.now(timezone.utc):
                    # Missing native operation proves that no provider request was made.
                    # Keep the original reservation: this content-addressed
                    # operation ID will also own the renewed quote.
                    del value['paid'][name]
                    save()
                    return self._audio_paid(value, name, request, save)
                outcome = self.center.submit(body)
            else:
                outcome = self.center.job(quote['operation_id'])
        child['status'] = outcome.get('status', 'submission_unknown')
        child['result'] = outcome.get('result') or {}
        if self.internal_audio:
            self._sdk()._complete_budget(quote['operation_id'], child['status'])
        save()
        if child['status'] == 'succeeded':
            return child['result']
        if child['status'] in {'failed', 'cancelled'}:
            raise WorkError('原声音调用未完成，已保留回执；请核对原调用，不能换编号重复扣费')
        return None

    def clone(self, value, folder, save):
        if value.get('audio_role') == 'narration':
            return succeeded({'skipped': True, 'reason': '使用用户提供的完整口播音轨'})
        request = value['paid'].setdefault('sample_upload', {})
        if not request:
            path = Path(value['inputs']['sample']['path'])
            request.update(self.center.upload(path.read_bytes(), 'audio', path.name))
            save()
        if self.internal_audio and 'clone' not in value['paid']:
            # A sample already cloned for this very account/model can reuse its
            # verified voice. Do not create a second name and incur another fee.
            content, _ = self.center.media(request['id'])
            sample_sha = hashlib.sha256(content).hexdigest()
            voices = {row['id']: row for row in self.center.voices().get('items', [])}
            for path in self.center.directory.glob('operations/call_*/operation.json'):
                original = read(path)
                source = original.get('request') or {}
                voice_id = ((original.get('result') or {}).get('voice') or {}).get('id')
                voice = voices.get(voice_id)
                if (original.get('status') == 'succeeded' and source.get('kind') == 'clone'
                        and source.get('audio_sha256') == sample_sha and source.get('model_id') == CLONE_MODEL
                        and voice and voice.get('model_id') == CLONE_MODEL):
                    return succeeded({'voice_id': voice_id, 'model': voice['model'], 'model_id': CLONE_MODEL,
                                      'reused_operation_id': original['id'], 'sample_sha256': sample_sha})
        result = self._audio_paid(value, 'clone', {'model': 'haike/voice-clone', 'input': {
            'name': '一条龙-'+value['id'][3:15], 'audio_file': request['id'],
            'target_model': CLONE_MODEL, 'consent': True}}, save)
        if result is None:
            return {'status': 'waiting'}
        voice_id = (result.get('voice') or {}).get('id')
        voices = self.center.voices().get('items', [])
        voice = next((row for row in voices if row['id'] == voice_id), None)
        if not voice or voice.get('model_id') != CLONE_MODEL:
            raise WorkError('克隆结果尚未确认为3.1 TTS Plus音色，请恢复原任务核对音色身份')
        return succeeded({'voice_id': voice_id, 'model': voice['model'], 'model_id': voice['model_id']})

    def _tts(self, value, folder, name, text, rate, save):
        voice = value['stages']['clone']['result']
        seed = value.get('policy', {}).get('speech_rate', {}).get('synthesis_seed')
        result = self._audio_paid(value, name, {'model': voice['model'], 'input': {
            'voice_id': voice['voice_id'], 'text': text, 'speech_rate': rate,
            'purpose': 'preview' if name == 'audition' else 'production',
            **({'synthesis_seed': seed} if seed is not None else {})}}, save)
        if result is None:
            return None
        source = self.center.preview(value['paid'][name]['quote']['operation_id'])
        target = folder/(name+'.wav')
        media_command(['-i', source, '-ac', '1', '-ar', '24000', '-c:a', 'pcm_s16le', target])
        return target

    def audition(self, value, folder, save):
        if value.get('audio_role') == 'narration':
            return succeeded({'skipped': True, 'rate': None, 'reason': '用户完整音轨保留原语速'})
        policy = value['policy']['speech_rate']
        if policy.get('fixed_rate') is not None:
            return succeeded({'skipped': True, 'rate': validate_rate(policy['fixed_rate']),
                              'reason': ('Agent依据整稿实测修订候选，仍须通过整稿字速检查'
                                         if policy.get('rate_source') == 'agent_pace_recovery' else
                                         '用户明确指定倍率，整稿使用该档位，不用短试听覆盖')})
        if policy.get('calibration_mode') == CALIBRATION_MODE:
            from backlot.avatar_one_stop_calibration import audition
            return audition(self, value, folder, save)
        if policy.get('calibration_mode') == 'full_text_baseline':
            return succeeded({'skipped': True, 'rate': 1.0,
                              'reason': '先合成完整稿1.00倍基准音频，在完整配音阶段按每5秒24–25字校准'})
        text = value['script']['text'][:150]
        source_rate = validate_rate(policy.get('audition_rate', 1))
        path = self._tts(value, folder, 'audition', text, source_rate, save)
        if path is None:
            return {'status': 'waiting'}
        result = calibrate(text, wav_duration(path),
                           target_cps=policy['target_characters_per_second'], sample_rate=source_rate)
        result.update(audio_sha256=digest(path), text=text)
        return succeeded(result)

    def narration(self, value, folder, save):
        text = value['script']['text']
        policy = value['policy']['speech_rate']
        target = policy['target_characters_per_second']
        if value.get('audio_role') == 'narration':
            path = folder/'narration.wav'
            media_command(['-i', value['inputs']['sample']['path'], '-ac', '1', '-ar', '24000',
                           '-c:a', 'pcm_s16le', path])
            rate, check = None, 'user_recording'
        else:
            fixed = policy.get('fixed_rate') is not None
            rate = validate_rate(policy['fixed_rate'] if fixed else (
                1.0 if policy.get('calibration_mode') == 'full_text_baseline' else
                value['stages']['audition']['result']['rate']))
            attempts = value['stages'].setdefault('narration', {}).setdefault('calibration_attempts', [])
            for index in range(3):
                name = 'narration' if index == 0 else f'narration-adjust-{index}'
                if len(attempts) <= index:
                    attempts.append({'name': name, 'rate': rate})
                    save()
                elif attempts[index]['rate'] != rate:
                    raise WorkError('原整稿校准档位发生变化，请恢复原调用', 'conflict')
                path = self._tts(value, folder, name, text, rate, save)
                if path is None:
                    return {'status': 'waiting'}
                duration = wav_duration(path)
                actual = effective_characters(text)/duration
                tolerance = max(3.0, .025/rate*100)
                band = policy.get('characters_per_five_seconds')
                accepted = (band['minimum'] <= actual*5 <= band['maximum'] if band else
                            fixed or abs((actual/target-1)*100) <= tolerance)
                attempts[index].update(audio_sha256=digest(path), duration_seconds=duration,
                                       measured_cps=actual, characters_per_five_seconds=actual*5, accepted=accepted)
                save()
                if accepted:
                    check = 'within_five_second_band' if band else ('explicit_rate' if fixed else 'within_tolerance')
                    final = folder/'narration.wav'
                    if path != final:
                        shutil.copy2(path, final)
                    break
                if fixed:
                    raise WorkError(f'指定倍率的整稿实测每5秒{actual*5:.2f}字，超出'
                        f'{band["minimum"]}–{band["maximum"]}字目标；保留音频，未继续ASR或数字人')
                adjusted = calibrate(text, duration, target_cps=target, sample_rate=rate)
                attempts[index]['next_rate'] = adjusted['rate']
                save()
                if adjusted['rate'] == rate or index == 2:
                    raise WorkError('整稿实测语速仍偏离参考，已保留原配音与全部校准回执；未继续ASR或数字人')
                rate = adjusted['rate']
        duration = wav_duration(path)
        actual = effective_characters(text)/duration
        return succeeded({'audio_sha256': digest(folder/'narration.wav'), 'duration_seconds': duration,
                          'script_sha256': value['script']['text_sha256'], 'speech_stretched': False,
                          'measured_cps': actual, 'target_cps': target,
                          'characters_per_five_seconds': actual*5,
                          'rate': rate, 'pace_check': check, 'deviation_percent': (actual/target-1)*100})

    def asr(self, value, folder, save):
        client = self._sdk()
        operation = value['paid'].get('asr')
        if operation is None:
            uploaded = client.prepare_asr_audio(folder/'narration.wav')
            quote = client.quote('haike/bailian-asr', {'audio_file': uploaded['id']}, project_ref=value['id'])
            operation = value['paid']['asr'] = {'quote': quote, 'intent_id': 'call_'+
                hashlib.sha256((value['id']+'asr').encode()).hexdigest()[:32]}
            save()
        intent = client.confirm(operation['quote'], operation['quote']['max_charge_micros'],
                                intent_id=operation['intent_id'])
        outcome = client.wait(intent, timeout=30)
        operation['status'] = outcome.get('status', 'submission_unknown')
        save()
        if operation['status'] != 'succeeded':
            if operation['status'] in {'failed', 'cancelled'}:
                raise WorkError('原字幕识别未完成，请核对原任务；完整配音已保留')
            return {'status': 'waiting'}
        result = outcome.get('result') or {}
        receipt = {'audio_sha256': digest(folder/'narration.wav'),
                   'approved_script_sha256': value['script']['text_sha256'],
                   'segments': result.get('segments', []), 'text': result.get('text', ''),
                   'metadata': {'words': result.get('words', []), 'provider': 'bailian',
                                'model': result.get('model'), 'operation_id': operation['quote']['operation_id']}}
        if not receipt['segments'] or not receipt['metadata']['words']:
            raise WorkError('识别结果缺少真实句词时间轴，请核对原ASR回执')
        atomic_private(folder/'asr.json', receipt)
        return succeeded({'sha256': digest(folder/'asr.json')})

    def storyboard(self, value, folder, save):
        from backlot.avatar_one_stop_production import propose, storyboard_evidence
        if not (folder/'storyboard-proposal.json').is_file():
            propose(value, folder)
        storyboard_evidence(read(folder/'storyboard-proposal.json'), folder)
        return agent('review_storyboard', '核对新配音的分镜、语义锚点、实际素材与首尾人物范围；'
                     '确认storyboard-proposal.json的SHA后提交storyboard检查回执')

    def avatar(self, value, folder, save):
        from backlot.avatar_one_stop_production import avatar
        return succeeded(avatar(value, folder, save))

    def composition(self, value, folder, save):
        from backlot.avatar_one_stop_production import compose
        return compose(self.studio, self.queue, value, folder, save)

    def quality(self, value, folder, save):
        from backlot.avatar_one_stop_production import quality
        from backlot.avatar_one_stop_finish import ensure_finished
        composition = value['stages']['composition']
        composition['result'] = ensure_finished(self.studio, self.queue, value, save)
        save()
        quality(value, folder)
        return agent('review_video', '查看实际新成片和代表帧，核对字幕、口型、素材、音轨与技术报告，'
                     '以成片SHA提交quality检查回执；不能把技术解码当作实际视听审阅')

    def apply(self, value, folder, data):
        stage = data['stage']
        allowed = {'stage', 'observed_sha256', 'reason', 'asset_id', 'visual_passed', 'audio_review', 'reviewed_sheets'}
        if set(data)-allowed or not isinstance(data.get('reason'), str) or not 4 <= len(data['reason']) <= 4000:
            raise WorkError('Agent检查需附实际检查结论')
        if stage == 'refinement':
            path = self.studio.asset(data.get('asset_id'), value['draft_id']) if data.get('asset_id') else folder/'refinement/result.png'
            if not path.is_file() or digest(path) != data.get('observed_sha256'):
                raise WorkError('精修检查回执与实际图片不同', 'conflict')
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image).convert('RGB')
                if image.size != (1024, 1280):
                    raise WorkError('精修结果需为1024×1280，不能静默拉伸人物')
                target = folder/'refinement/result.png'
                target.parent.mkdir(parents=True, exist_ok=True)
                image.save(target, format='PNG')
            return succeeded({'sha256': digest(target), 'source_sha256': value['inputs']['portrait']['sha256'],
                              'reference_sha256': value['reference']['sha256']})
        path = folder/'storyboard-proposal.json' if stage == 'storyboard' else Path(value['stages']['composition']['result']['output_path'])
        if digest(path) != data.get('observed_sha256'):
            raise WorkError('检查对象已经变化，请重新检查实际产物', 'conflict')
        if stage == 'storyboard':
            from backlot.avatar_one_stop_production import validate_plan
            validate_plan(value, folder, read(path))
            evidence = read(folder/'storyboard-evidence.json')
            from backlot.avatar_one_stop_policy import fingerprint
            expected = sorted(s['sha256'] for s in evidence['sheets'])
            if (evidence['plan_fingerprint'] != fingerprint(read(path)) or sorted(data.get('reviewed_sheets', [])) != expected
                    or any(digest(s['path']) != s['sha256'] for s in evidence['sheets'])):
                raise WorkError('请先查看本期全部素材裁切宫格，再提交对应检查回执', 'conflict')
            shutil.copy2(path, folder/'storyboard-approved.json')
        else:
            if data.get('visual_passed') is not True or data.get('audio_review') not in {'listened', 'technical_only'}:
                raise WorkError('请记录实际视觉检查和音轨检查方式，不能默认视听通过')
            quality = read(folder/'quality.json')
            if quality.get('output_sha256') != data['observed_sha256'] or quality.get('technical') != 'pass':
                raise WorkError('技术检查尚未通过或成片身份不同')
            quality.update(visual_review='pass', audio_review=data['audio_review'], agent_reason=data['reason'])
            atomic_private(folder/'quality.json', quality)
            from backlot.work_catalog import WorkCatalog
            catalog = WorkCatalog(self.studio.projects_root)
            work = catalog.get(value['stages']['composition']['result']['work_id'])
            version = next((v for v in work['versions'] if v['sha256'] == data['observed_sha256']), None)
            if version is None:
                raise WorkError('已检查成片尚未登记对应作品版本，保留原任务', 'conflict')
            catalog.change(work['work_id'], 'confirm', {'revision': work['revision'],
                'version_id': version['version_id'],
                'evidence': '一条龙Agent成片检查；音轨检查范围='+data['audio_review']+'；'+data['reason']},
                actor='avatar-one-stop-agent')
        return succeeded({'sha256': data['observed_sha256'], 'reason': data['reason'],
                          **({'audio_review': data['audio_review']} if stage == 'quality' else {})})
