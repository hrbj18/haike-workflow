"""Source-bound console preparation; full movies use the existing native queue CLI."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backlot import studio_motion_console as console


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    build=sub.add_parser('build',help='Verify current source bindings and prepare owned inputs')
    build.add_argument('input',type=Path);build.add_argument('--out',required=True,type=Path)
    plan=sub.add_parser('plan',help='Run the official bounded semantic plan')
    plan.add_argument('build',type=Path)
    preview=sub.add_parser('preview',help='Prepare and preview after actual plan/source inspection')
    preview.add_argument('build',type=Path);preview.add_argument('--review',required=True,type=Path)
    preview.add_argument('--times',required=True,help='5 to12 comma-separated key-state seconds')
    manifest=sub.add_parser('manifest',help='Bind all actually viewed previews for existing queue freeze')
    manifest.add_argument('build',type=Path);manifest.add_argument('--review',required=True,type=Path)
    args=parser.parse_args()
    if args.action=='build':result=console.build(args.input,args.out)
    elif args.action=='plan':result=console.plan(args.build)
    elif args.action=='preview':result=console.prepare_and_preview(args.build,args.review,[float(t) for t in args.times.split(',')])
    else:result=console.manifest(args.build,args.review)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
