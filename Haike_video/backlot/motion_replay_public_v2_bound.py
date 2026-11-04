"""Freeze the semantic replay identity through existing source_receipts.

The earlier read-only candidate is preserved. This patch changes provenance,
not renderer input geometry, media, cues or audio.
"""
from copy import deepcopy

from backlot import motion_replay_public_v2 as original

BINDINGS = original.BINDINGS
WORKSPACE = original.WORKSPACE
VERSION = '1.0.1-public.2'


def prepare(template, request, *, workspace):
    original.require(template.get('version') == VERSION, '此公开模板的精确绑定版本尚未适配')
    value = (request or {}).get('input')
    original.require(isinstance(value, dict) and isinstance(value.get('source_receipts', {}), dict),
                     '本期来源回执须为对象')
    # Reuse only the fixed predecessor's unchanged validation/consumer behavior.
    compatible = deepcopy(template)
    compatible['version'] = original.VERSION
    prepared = original.prepare(compatible, request, workspace=workspace)
    binding = {'schema': 'haike.motion-replay-production-binding/1',
        'template_id': template['template_id'], 'version': VERSION,
        'gallery_id': prepared['gallery_id'], 'production_contract': prepared['production_contract'],
        'implementation': prepared['implementation'], 'source_identity': deepcopy(template.get('sources', [])),
        'action_bindings': deepcopy(prepared['action_bindings']),
        'resolved_events': deepcopy(prepared['resolved_events']), 'render_profile': deepcopy(prepared['render_profile'])}
    consumer = deepcopy(prepared['consumer'])
    receipts = consumer['input'].setdefault('source_receipts', {})
    existing = receipts.get('motion_replay')
    original.require(existing is None or existing == binding,
                     '输入已有其他模板、版本、源码或动作绑定；请保留原请求并重新按精确契约准备')
    receipts['motion_replay'] = deepcopy(binding)
    return {**prepared, 'consumer': consumer, 'replay_binding': binding,
        'binding_consumption': 'Producer freezes source_receipts.motion_replay into the actual parent identity; renderer consumes the matched composition actions and clocks. No project or job created here.'}
