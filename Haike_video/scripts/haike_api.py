"""Project/Agent entrypoint for the unified Haike API. Paid calls require an explicit cap."""

import argparse
import getpass
import json
import os
import sys
import urllib.error
from decimal import Decimal, InvalidOperation
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent / "api-platform"))
from client import save_private
from gateway_client import HaikeClient

PRIVATE = PROJECT_ROOT / ".backlot" / "haike-api"


def client():
    path = PRIVATE / "client-config.json"
    config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    base = os.environ.get("HAIKE_API_BASE_URL") or config.get(
        "base_url", "http://127.0.0.1:17894/v2"
    )
    key = os.environ.get("HAIKE_API_KEY") or config.get("api_key")
    if not key:
        raise ValueError("请先 configure 或设置 HAIKE_API_KEY")
    return HaikeClient(base, key, PRIVATE / "intents")


def main():
    parser = argparse.ArgumentParser(
        description="海客工作流统一 Key 接入；不会默认提交付费调用"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("configure")
    sub.add_parser("summary")
    sub.add_parser("models")
    upload = sub.add_parser("upload")
    upload.add_argument("--file", type=Path, required=True)
    upload.add_argument("--kind", choices=["audio", "image"], required=True)
    call = sub.add_parser("call")
    call.add_argument("--model", required=True)
    call.add_argument("--input-json", type=Path, required=True)
    call.add_argument("--project", default="")
    call.add_argument("--max-yuan", required=True)
    call.add_argument(
        "--confirm",
        action="store_true",
        help="明确确认本次真实调用，按 max-yuan 上限执行",
    )
    call.add_argument("--wait", action="store_true")
    resume = sub.add_parser("resume")
    resume.add_argument("intent_id")
    resume.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "configure":
            base = (
                input("海客 Base URL [http://127.0.0.1:17894/v2]: ").strip()
                or "http://127.0.0.1:17894/v2"
            )
            key = getpass.getpass("平台 API Key（输入隐藏）: ").strip()
            configured = HaikeClient(base, key, PRIVATE / "intents")
            summary = configured.request("/account/summary")
            save_private(
                PRIVATE / "client-config.json", {"base_url": base, "api_key": key}
            )
            print(
                "已连接账户：", summary["account_name"], "；Key 已私有保存，不会回显。"
            )
            return
        sdk = client()
        if args.command == "summary":
            result = sdk.request("/account/summary")
        elif args.command == "models":
            result = sdk.request("/capabilities")
        elif args.command == "upload":
            result = sdk.upload(args.file, args.kind)
        elif args.command == "call":
            try:
                amount = Decimal(args.max_yuan) * 1000000
                if (
                    not amount.is_finite()
                    or amount < 0
                    or amount > 10**12
                    or amount != amount.to_integral_value()
                ):
                    raise ValueError()
            except (ValueError, InvalidOperation):
                raise ValueError("费用上限须为非负数，最多六位小数") from None
            quote = sdk.quote(
                args.model,
                json.loads(args.input_json.read_text(encoding="utf-8")),
                args.project,
            )
            if int(quote["max_charge_micros"]) > int(amount):
                raise ValueError("报价超过授权上限，未提交、未扣费")
            if not args.confirm:
                result = {
                    "quote": quote,
                    "message": "仅取得报价。确认供应商、模型和费用上限后，使用 --confirm 提交。",
                }
            else:
                intent = sdk.confirm(quote, int(amount))
                print(
                    "持久调用编号：",
                    intent,
                    "；中断后 resume 此编号，不重复运行新的 call。",
                    flush=True,
                )
                result = sdk.wait(intent) if args.wait else sdk.resume(intent)
        else:
            result = (
                sdk.wait(args.intent_id) if args.wait else sdk.resume(args.intent_id)
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, urllib.error.URLError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
