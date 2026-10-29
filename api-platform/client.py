"""One-key local Agent client with durable call intent and same-request recovery."""

import argparse
import getpass
import json
import os
import secrets
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

LOCAL = Path(__file__).parent / "data"


def save_private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
    temporary.replace(path)
    if os.name != "nt":
        path.chmod(0o600)


def config():
    stored = (
        json.loads((LOCAL / "client-config.json").read_text())
        if (LOCAL / "client-config.json").exists()
        else {}
    )
    base = os.environ.get(
        "HAIKE_API_BASE_URL", stored.get("base_url", "http://127.0.0.1:17894/v2")
    ).rstrip("/")
    parsed = urlsplit(base)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.path != "/v2"
        or parsed.username
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("M1 客户端仅允许本地 http://127.0.0.1:<port>/v2 地址")
    key = os.environ.get("HAIKE_API_KEY", stored.get("key"))
    if not key:
        raise ValueError("先运行 client.py configure 或设置 HAIKE_API_KEY")
    return base, key


def request(path, body=None, idem=None):
    base, key = config()
    headers = {"Authorization": "Bearer " + key}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if idem:
        headers["Idempotency-Key"] = idem
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
    )

    # No environment HTTP proxy or redirect may forward a Key to another host.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(req, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        result = json.load(error)
        raise ValueError(
            result.get("error", {}).get("message", "API 请求失败")
        ) from None


def submit_journal(path, journal):
    if journal.get("job_id"):
        return request("/jobs/" + journal["job_id"])
    body = {
        "quote_id": journal["quote"]["id"],
        "max_charge_micros": journal["quote"]["max_charge_micros"],
        "call_intent_id": journal["intent_id"],
        "currency": "CNY",
        "confirmed": True,
    }
    # Persisted quote/intent/idem survive a timeout; resume never creates a new paid task.
    result = request("/jobs", body, journal["idempotency_key"])
    journal["job_id"] = result["id"]
    save_private(path, journal)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="海客统一 Key 接入演示（不会调用真实供应商）"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("configure")
    sub.add_parser("summary")
    sub.add_parser("models")
    tts = sub.add_parser("demo-tts")
    tts.add_argument("--text-file", required=True, type=Path)
    tts.add_argument("--max-yuan", required=True)
    tts.add_argument("--project", default="Agent 接入演示")
    resume = sub.add_parser("resume")
    resume.add_argument("intent_id")
    args = parser.parse_args()
    try:
        if args.command == "configure":
            base = (
                input("本地 Base URL [http://127.0.0.1:17894/v2]: ").strip()
                or "http://127.0.0.1:17894/v2"
            )
            key = getpass.getpass("API Key（输入隐藏）: ").strip()
            # Validate before saving by using this process's temporary environment.
            os.environ["HAIKE_API_BASE_URL"], os.environ["HAIKE_API_KEY"] = base, key
            result = request("/account/summary")
            save_private(LOCAL / "client-config.json", {"base_url": base, "key": key})
            print(
                "已连接：", result["account_name"], "；私有配置已保存，Key 不会回显。"
            )
            return
        if args.command in {"summary", "models"}:
            result = request(
                "/account/summary" if args.command == "summary" else "/capabilities"
            )
        elif args.command == "demo-tts":
            from decimal import Decimal, InvalidOperation

            try:
                maximum = Decimal(args.max_yuan) * 1000000
                if (
                    not maximum.is_finite()
                    or maximum <= 0
                    or maximum != maximum.to_integral_value()
                ):
                    raise ValueError()
            except (InvalidOperation, ValueError):
                raise ValueError("max-yuan 必须为正数且最多六位小数") from None
            quote = request(
                "/quotes",
                {
                    "model": "demo/cosyvoice-characters",
                    "input": {
                        "text": args.text_file.read_text(encoding="utf-8"),
                        "demo_outcome": "succeeded",
                    },
                    "project_ref": args.project,
                },
            )
            if int(quote["max_charge_micros"]) > int(maximum):
                raise ValueError("报价超过授权上限，未提交、未扣款")
            intent = "cli_" + secrets.token_hex(16)
            path = LOCAL / "intents" / (intent + ".json")
            journal = {"intent_id": intent, "idempotency_key": intent, "quote": quote}
            save_private(path, journal)
            print("持久化请求编号：", intent, "；中断后用 resume 和此编号恢复。")
            result = submit_journal(path, journal)
        else:
            if (
                not args.intent_id.startswith("cli_")
                or not all(c in "0123456789abcdef" for c in args.intent_id[4:])
                or len(args.intent_id) != 36
            ):
                raise ValueError("请求编号格式不正确")
            path = LOCAL / "intents" / (args.intent_id + ".json")
            journal = json.loads(path.read_text())
            result = submit_journal(path, journal)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, urllib.error.URLError) as error:
        # No traceback contains Authorization headers or config secrets.
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
