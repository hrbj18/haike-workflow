"""Run the loopback account backend, optionally behind an HTTPS cloud proxy."""

import argparse
from pathlib import Path

import uvicorn

from platform_app.app import create_app
from platform_app.deployment import serve_redirect


def main():
    parser = argparse.ArgumentParser(description="海客 API 中心（本地账户、额度与统一网关）")
    parser.add_argument("--port", type=int, default=17894)
    parser.add_argument("--public-origin", help="HTTPS origin served by the trusted local reverse proxy")
    parser.add_argument(
        "--db", type=Path, default=Path(__file__).parent / "data" / "platform.sqlite3"
    )
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be 1024–65535")
    migrated = args.db.parent / "cloud-origin.txt"
    if migrated.exists() and not args.public_origin:
        print("本机入口已迁移到云端，不再启动本机账本。")
        serve_redirect(migrated.read_text().strip(), args.port)
        return
    print(f"海客 API 中心：{args.public_origin or f'http://127.0.0.1:{args.port}'}")
    uvicorn.run(
        create_app(args.db, public_origin=args.public_origin),
        host="127.0.0.1",
        port=args.port,
        proxy_headers=bool(args.public_origin),
        forwarded_allow_ips="127.0.0.1",
        access_log=False,
    )


if __name__ == "__main__":
    main()
