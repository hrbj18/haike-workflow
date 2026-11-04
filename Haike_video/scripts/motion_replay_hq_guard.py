"""Use the unchanged portable HQ CLI with an explicit current-price guard.

Only reservation math is extended. Graph, submit, task identity, recovery and
download remain the package's implementations; no old package hashes change.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import math
import sys


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--price-receipt', required=True, type=Path)
    options, forwarded = parser.parse_known_args()
    price = json.loads(options.price_receipt.read_bytes())
    ceiling = price['max_coins_per_compute_second']
    if not isinstance(ceiling, (int, float)) or not .4 <= ceiling <= 2 or not price.get('source_sha256'):
        raise RuntimeError('需要明确当前价格来源与保守计算秒单价上限')
    root = Path(__file__).resolve().parents[1] / 'workflows/runninghub-high-quality'
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location('haike_original_portable_hq', root / 'agent_cli.py')
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    original = native.make_plan

    def make_plan(*args, **kwargs):
        plan = original(*args, **kwargs)
        for segment in plan['segments']:
            segment['reserve_coins'] = math.ceil(segment['max_compute_seconds'] * ceiling) + 14
        plan['reserve_coins'] = sum(segment['reserve_coins'] for segment in plan['segments'])
        plan['estimate_basis'] = 'current-price-bound %.4f RHcoins/compute-second; fixed project conversion is not a price guarantee' % ceiling
        plan['price_receipt_sha256'] = native.sha(options.price_receipt)
        return plan

    native.make_plan = make_plan
    sys.argv = [str(root / 'agent_cli.py'), *forwarded]
    try:
        native.main()
    except Exception as exc:
        native.say(state='stopped', error_class=type(exc).__name__,
                   message=native.clean(str(exc)) if type(exc) is RuntimeError else '原HQ任务保留；核对本地依赖/网络后用同名命令恢复，不重发',
                   automatic_paid_resubmit=False)
        return 1
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
