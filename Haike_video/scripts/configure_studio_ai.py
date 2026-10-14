"""Operator-only trial configuration. No credentials in flags, logs or frontend."""
import argparse
import base64
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backlot.studio import Studio, atomic_private
from backlot.studio_storyboard import IMAGE_MODELS, TrialRelay, configuration, image_identity, status


def verify_image(studio, verification_id):
    """One explicit, durable test; a failed intent never automatically retries."""
    from PIL import Image
    c = configuration(studio)
    identity = image_identity(c)
    folder = studio.private / "studio-ai/image-verification" / verification_id
    intent = folder / "configuration.safe"
    if intent.exists() and json.loads(intent.read_text())["identity"] != identity:
        raise ValueError("此验收编号已绑定原模型和渠道，请使用新的验收编号")
    atomic_private(intent, {"identity": identity, "model": c.get("image_model", IMAGE_MODELS[0])})
    result = TrialRelay(studio, folder).call("verify-image", {
        "model": c.get("image_model", IMAGE_MODELS[0]), "prompt": "视频示意插画：橙色书本放在白色桌上，淡黄色背景，无文字、无人物、无品牌。",
        "n": 1, "size": "1024x1536", "quality": "medium"}, image=True)
    raw = base64.b64decode(result["data"][0]["b64_json"], validate=True)
    if len(raw) > 16 * 1024 * 1024: raise ValueError("验收图片超过16MB，原响应已保留")
    with Image.open(io.BytesIO(raw)) as image: image.verify()
    with Image.open(io.BytesIO(raw)) as image:
        if image.size != (1024, 1536): raise ValueError("验收图片尺寸不符合竖屏插画配置，原响应已保留")
    (folder / "verified.png").write_bytes(raw)
    current = configuration(studio)
    if image_identity(current) != identity: raise ValueError("验收时配置发生变化，未开放旧渠道")
    current.update(image_verified=True, image_verified_for=identity,
                   image_verification={"id": verification_id, "sha256": hashlib.sha256(raw).hexdigest(), "usage": result.get("usage")})
    atomic_private(studio.private / "studio-ai/relay.json", current)


def main():
    p = argparse.ArgumentParser(description="配置AI免费试用后台；私有JSON文件含base_url和api_key")
    p.add_argument("--projects-root", type=Path, default=Path(__file__).resolve().parents[1] / "projects")
    p.add_argument("--file", type=Path)
    p.add_argument("--douyin-commercial-authorized", action="store_true")
    p.add_argument("--douyin-login-confirmed", action="store_true", help="完成抖音登录后由操作人明确确认")
    p.add_argument("--authorize-video", action="append", default=[], help="已取得使用权的抖音视频ID")
    p.add_argument("--crawler-root", type=Path)
    p.add_argument("--image-model", choices=IMAGE_MODELS, help="只为新插画意图选择模型；旧意图保留原模型")
    pause = p.add_mutually_exclusive_group()
    pause.add_argument("--pause-images", action="store_true", help="暂缓生图，新任务不能补图；旧回执保留")
    pause.add_argument("--resume-images", action="store_true", help="操作人明确恢复生图验收；仍需成功图片证明")
    p.add_argument("--verify-image", action="store_true", help="明确发送一次竖屏单图验收，通过后才开放插画补齐")
    p.add_argument("--verification-id", help="验收意图编号；失败后沿用编号不会重新提交")
    p.add_argument("--confirm", action="store_true", help="确认供应商单张验收消耗；客户试用费为零，采购成本未知")
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
    if args.image_model and args.image_model != c.get("image_model", IMAGE_MODELS[0]):
        c.update(image_model=args.image_model, image_verified=False)
    if args.pause_images: c["image_paused"] = True
    if args.resume_images: c["image_paused"] = False
    if args.verify_image and c.get("image_paused"): p.error("生图已暂缓，请先明确--resume-images，旧请求不会重提")
    if args.verify_image and (not args.confirm or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", args.verification_id or "")):
        p.error("单张验收需要--confirm及1至64字符--verification-id；不自动重提原失败请求")
    if args.verify_image:
        if not c.get("api_key"): p.error("请先导入后台私有中转配置")
        c["image_verified"] = False
    atomic_private(s.private / "studio-ai/relay.json", c)
    if args.verify_image:
        try: verify_image(s, args.verification_id)
        except Exception: p.exit(1, "插画验收未通过，原请求已保留；插画补齐保持关闭，请核对中转状态。\n")
    print(json.dumps(status(s),ensure_ascii=False))


if __name__ == "__main__": main()
