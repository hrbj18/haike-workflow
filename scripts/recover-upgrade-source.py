"""Recover exact runtime and supported user data into a receipt-owned candidate."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from portable.source_candidate_recovery import recover


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--receipt',required=True,type=Path)
    p.add_argument('--archive',required=True,type=Path)
    p.add_argument('--archive-sha256',required=True)
    p.add_argument('--archive-size',required=True,type=int)
    p.add_argument('--closure-sha256',required=True)
    p.add_argument('--program-tree-sha256',required=True)
    p.add_argument('--runtime-source',type=Path,help='仅复制精确清单绑定的合法基础运行时；不读取该来源的用户资料')
    p.add_argument('--runtime-manifest-sha256')
    p.add_argument('--online',action='store_true',help='缺件时按目标精确锁复用既有依赖恢复器；仅写隔离目标')
    a=p.parse_args(argv)
    try:
        result=recover(a.receipt,a.archive,archive_sha256=a.archive_sha256,archive_size=a.archive_size,
            closure_sha256=a.closure_sha256,program_tree_sha256=a.program_tree_sha256,
            runtime_source=a.runtime_source,runtime_manifest_sha256=a.runtime_manifest_sha256,online=a.online)
        print(json.dumps({'status':result['status'],'runtime_ready':result['runtime_ready'],'target':result['target'],
            'unknown_data_items':len(result['data']['unknown']),'services_started':False,'provider_calls':0},ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps({'status':'blocked','error_type':type(error).__name__,'runtime_ready':False,
                         'message':'保留原目录及隔离恢复回执；未启动服务、发布或调用provider。'},ensure_ascii=False),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
