"""Operator-only trial configuration. No credentials in flags, logs or frontend."""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backlot.studio import Studio, atomic_private
from backlot.studio_storyboard import configuration, status


def main():
    p = argparse.ArgumentParser(description="配置AI免费试用后台；私有JSON文件含base_url和api_key")
    p.add_argument("--projects-root", type=Path, default=Path(__file__).resolve().parents[1] / "projects")
    p.add_argument("--file", type=Path)
    p.add_argument("--douyin-commercial-authorized", action="store_true")
    p.add_argument("--douyin-login-confirmed", action="store_true", help="完成抖音登录后由操作人明确确认")
    p.add_argument("--authorize-video", action="append", default=[], help="已取得使用权的抖音视频ID")
    p.add_argument("--crawler-root", type=Path)
    args = p.parse_args(); s = Studio(args.projects_root); c = configuration(s)
    if args.file:
        data = json.loads(args.file.read_text()); url = urlsplit(data.get("base_url", ""))
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment or url.path.rstrip("/") != "/v1":
            p.error("Base URL需要无凭据的/v1地址")
        if not isinstance(data.get("api_key"), str) or not 8 <= len(data["api_key"]) <= 512: p.error("私有配置需要有效api_key")
        c.update(base_url=data["base_url"].rstrip("/"),api_key=data["api_key"])
    if args.douyin_commercial_authorized: c["douyin_commercial_authorized"] = True
    if args.douyin_login_confirmed: c["douyin_login_confirmed"] = True
    if args.authorize_video: c["douyin_authorized_video_ids"] = sorted(set(c.get("douyin_authorized_video_ids", [])+args.authorize_video))
    if args.crawler_root: c["crawler_root"] = str(args.crawler_root.resolve())
    atomic_private(s.private / "studio-ai/relay.json", c)
    print(json.dumps(status(s),ensure_ascii=False))


if __name__ == "__main__": main()
