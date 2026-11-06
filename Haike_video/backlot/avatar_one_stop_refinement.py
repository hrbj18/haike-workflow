"""One journaled two-reference edit; uncertain upstream requests are never retried."""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

from PIL import Image, ImageOps

from backlot.avatar_one_stop_policy import digest, fingerprint
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError


def _image(content):
    with Image.open(io.BytesIO(content)) as value:
        mime = Image.MIME.get(value.format)
        if mime not in {'image/png', 'image/jpeg', 'image/webp'} or min(value.size) < 64:
            raise WorkError('精修输入需为有效的人物照片和固定参考图')
        value.verify()
    return mime


class TwoImageRefinement:
    def __init__(self, configuration, *, transport=None):
        self.configuration = configuration
        self.transport = transport

    def run(self, folder, source, reference, prompt):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        journal, raw, output = folder/'operation.json', folder/'raw-image', folder/'result.png'
        identity = {'source_sha256': digest(source), 'reference_sha256': digest(reference),
                    'prompt_sha256': fingerprint(prompt), 'output': [1024, 1280]}
        old = json.loads(journal.read_text('utf-8')) if journal.exists() else None
        if old and old['identity'] != identity:
            raise WorkError('原精修输入已冻结，请继续原图与固定参考', 'conflict')
        if old and old['status'] == 'succeeded':
            if not output.is_file() or digest(output) != old['output_sha256']:
                raise WorkError('原精修产物缺失或变化，请恢复原文件', 'conflict')
            return old
        if not raw.exists():
            if old:
                raise WorkError('原精修受理状态或结果待核对，已保留原意图，未重复付费', 'unavailable')
            config = self.configuration()
            if not config.get('api_key') or not config.get('base_url'):
                raise WorkError('现有图片精修通道尚未配置可用，请核对私有后台', 'unavailable')
            content = []
            for path in (source, reference):
                body = Path(path).read_bytes()
                if len(body) > 25*1024*1024:
                    raise WorkError('单张精修参考图最多25MB')
                mime = _image(body)
                content.append({'type': 'input_image', 'image_url':
                                'data:'+mime+';base64,'+base64.b64encode(body).decode('ascii')})
            content.insert(0, {'type': 'input_text', 'text':
                'Edit image 1 using image 2 only as the fixed skin/retouch reference. '
                'Call image_generation once and return one edited image.\n\n'+prompt})
            record = {'identity': identity, 'status': 'submitting', 'input_images': 2,
                      'provider': 'configured-image-refinement', 'image_model': config.get('image_model', 'gpt-image-2'),
                      'text_model': config.get('text_model', 'gpt-5.6'), 'actual_charge': None}
            payload = {'model': record['text_model'], 'stream': False, 'store': False,
                       'tools': [{'type': 'image_generation', 'model': record['image_model'], 'size': '1024x1280'}],
                       'tool_choice': {'type': 'image_generation'},
                       'input': [{'role': 'user', 'content': content}]}
            atomic_private(journal, record)  # durable before the only non-idempotent POST
            try:
                if self.transport:
                    result = self.transport(config, payload)
                else:
                    import requests
                    response = requests.post(config['base_url'].rstrip('/')+'/responses',
                        headers={'Authorization': 'Bearer '+config['api_key'], 'Content-Type': 'application/json'},
                        json=payload, timeout=(15, 600), allow_redirects=False)
                    response.raise_for_status()
                    result = response.json()
                calls = [v for v in result.get('output', []) if v.get('type') == 'image_generation_call']
                record.update(response_id=result.get('id'), tool_calls=len(calls), usage=result.get('usage'))
                if result.get('status') != 'completed' or len(calls) != 1 or calls[0].get('status') not in {'completed', 'succeeded'}:
                    raise ValueError('incomplete image result')
                encoded = calls[0].get('result')
                if not isinstance(encoded, str) or len(encoded) > 40*1024*1024:
                    raise ValueError('invalid image result')
                body = base64.b64decode(encoded, validate=True)
                _image(body)
                raw.write_bytes(body)
                record.update(status='received', raw_sha256=digest(raw))
                atomic_private(journal, record)
            except Exception:
                record.update(status='submission_unknown', error='原精修结果待核对；未自动重新提交')
                atomic_private(journal, record)
                raise WorkError('精修调用结果待核对；原意图已保留，未重复提交', 'unavailable') from None
        else:
            record = old
            if not record or record.get('raw_sha256') != digest(raw):
                raise WorkError('原精修结果身份不匹配，请核对原文件', 'conflict')
        try:
            with Image.open(raw) as value:
                image = ImageOps.exif_transpose(value).convert('RGBA')
                background = Image.new('RGBA', image.size, 'white')
                background.alpha_composite(image)
                image = ImageOps.fit(background.convert('RGB'), (1024, 1280), Image.Resampling.LANCZOS)
                temporary = folder/'result.tmp'
                image.save(temporary, 'PNG')
                temporary.replace(output)
        except (OSError, ValueError, Image.DecompressionBombError):
            raise WorkError('精修本地处理未完成，原始结果已保留，可恢复原任务', 'unavailable') from None
        record.update(status='succeeded', output_sha256=digest(output))
        atomic_private(journal, record)
        return record
