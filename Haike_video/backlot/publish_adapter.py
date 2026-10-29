"""成片和指定封面到 CreatorHub 严格发布任务的适配器。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib import error, request

# ---------------------------------------------------------------------------
# 契约常量（与 creatorhub/app/main.py 对齐）
# ---------------------------------------------------------------------------

#: creatorhub 支持的平台（main.py:9107-9126）
ALLOWED_PLATFORMS: tuple[str, ...] = ("xhs", "kuaishou", "douyin", "shipinhao")

#: 平台中文名，仅用于日志
PLATFORM_LABELS: dict[str, str] = {
    "douyin": "抖音",
    "kuaishou": "快手",
    "shipinhao": "视频号",
    "xhs": "小红书",
}

#: 服务端强制截断长度（main.py:9130-9132）
TITLE_MAX = 20
LOCATION_MAX = 60
COVER_PATH_MAX = 500

#: 抖音可见性取值
VISIBILITIES: tuple[str, ...] = ("public", "friends", "private")

#: 退出码（与 Haike 既有 CLI 风格一致）
EXIT_OK = 0
EXIT_INPUT = 2
EXIT_BLOCKED = 3
EXIT_NOT_CONFIGURED = 4

#: 封面期望宽高比 3:4
COVER_RATIO = 3 / 4
COVER_RATIO_TOLERANCE = 0.01

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


class PublishAdapterError(RuntimeError):
    """适配器错误。``code`` 用于机器判定。"""

    def __init__(self, message: str, *, code: str = "invalid") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class PublishIntent:
    """一次发布意图（尚未变成 creatorhub 任务）。"""

    account_id: int
    platform: str
    video_path: Path
    title: str = ""
    desc: str = ""
    topics: str = ""
    location: str = ""
    visibility: str = "public"
    allow_save: bool = True
    cover_path: str = ""
    scheduled_at: str | None = None
    cover_policy: str = "required"
    cover_origin: str = "provided_image"
    cover_proof_path: str = ""
    package_id: str = ""
    package_revision: int = 1
    source_rights_status: str = "unknown"

    def to_payload(self) -> dict[str, Any]:
        """转成 ``POST /api/publish`` 的请求体。"""
        built = build_publish_payload(self)
        if built.blocked:
            raise PublishAdapterError("；".join(built.blocked))
        return built.payload


@dataclass
class BuildResult:
    payload: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 校验 / 构造
# ---------------------------------------------------------------------------


def _truncate(value: str, limit: int) -> tuple[str, bool]:
    text = str(value or "")
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def build_publish_payload(intent: PublishIntent) -> BuildResult:
    """校验意图并构造 payload。

    所有校验都在**本地先做一遍**，因为服务端要么静默截断、要么返回难以理解的 400。
    """
    result = BuildResult()

    # --- 平台
    if intent.platform not in ALLOWED_PLATFORMS:
        result.blocked.append(
            f"平台 {intent.platform!r} 不在允许列表 {ALLOWED_PLATFORMS}"
        )
    if intent.account_id < 1:
        result.blocked.append("account_id 须为正整数")

    # --- 成片
    video = Path(intent.video_path)
    video_sha256 = ""
    if not video.is_file():
        result.blocked.append(f"成片不存在：{video}")
    else:
        # G2：0 字节文件绝不可以通过发布前校验。
        # （2026-09-22 事故：一个 0 字节 fake.mp4 被真的送进了发布队列。）
        try:
            size = video.stat().st_size
        except OSError as exc:
            result.blocked.append(f"成片无法读取大小：{exc}")
            size = -1
        if size == 0:
            result.blocked.append(
                f"成片是 0 字节空文件，拒绝入队：{video}。"
                "（发布前必须确认真实媒体存在）"
            )
        elif size > 0 and size < 1024:
            result.warnings.append(f"成片体积异常小（{size} 字节），请确认是真实视频")
        if size > 0:
            try:
                video_sha256 = _file_sha256(video)
            except OSError as exc:
                result.blocked.append(f"成片读取失败：{exc}")
        if video.suffix.lower() not in (".mp4", ".mov", ".mkv"):
            result.warnings.append(f"成片扩展名非预期：{video.suffix}")

    # --- 标题（★ 服务端会静默截断到 20 字）
    title, title_cut = _truncate(intent.title, TITLE_MAX)
    if title_cut:
        result.warnings.append(
            f"title 超过 {TITLE_MAX} 字，已在本地截断（服务端也会截断但不报错）"
            f"：[TRUNCATED] {intent.title!r} → {title!r}"
        )
    if intent.platform == "shipinhao":
        safe_title = re.sub(r"[，。！？；、,:;!?]", " ", title)
        safe_title = " ".join(safe_title.split())
        safe_title, short_cut = _truncate(safe_title, 16)
        if safe_title != title or short_cut:
            result.warnings.append(f"视频号短标题按页面限制规范化为：{safe_title!r}")
        title = safe_title

    # --- 描述（★ 后台卡片展示的是它，不是 title）
    desc = str(intent.desc or "")
    if desc and title and desc[:len(title)] != title:
        result.warnings.append(
            "关键词建议放在 desc 开头：抖音后台卡片展示的是 desc，不是 title"
        )

    # --- 位置
    location, loc_cut = _truncate(intent.location, LOCATION_MAX)
    if loc_cut:
        result.warnings.append(f"location 超过 {LOCATION_MAX} 字，已截断")

    # --- 封面
    cover = str(intent.cover_path or "")
    cover_sha256 = ""
    cover_proof_sha256 = ""
    if intent.cover_policy not in ("required", "optional"):
        result.blocked.append("cover_policy 须为 required 或 optional")
    if intent.cover_origin not in (
            "generated_ai", "provided_image", "approved_video_frame"):
        result.blocked.append("cover_origin 无效")
    if intent.cover_origin == "generated_ai" and intent.cover_policy != "required":
        result.blocked.append("AI 专属封面必须设置为 required")
    if intent.package_revision < 1:
        result.blocked.append("package_revision 须大于 0")
    if intent.source_rights_status not in ("unknown", "confirmed", "owned"):
        result.blocked.append("source_rights_status 无效")
    elif intent.source_rights_status == "unknown":
        result.warnings.append("来源素材使用范围尚未确认；仅可 dry-run，不能公开提交")
    if intent.cover_policy == "required" and not cover:
        result.blocked.append("指定封面为必需，不能使用平台自动选帧")
    if cover:
        cover, cover_cut = _truncate(cover, COVER_PATH_MAX)
        if cover_cut:
            result.blocked.append(f"cover_path 超过 {COVER_PATH_MAX} 字")
        cover_file = Path(cover)
        if not cover_file.is_file():
            result.blocked.append(f"封面文件不存在：{cover_file}")
        else:
            ratio_note = _check_cover_ratio(cover_file)
            if ratio_note:
                (result.blocked if intent.cover_policy == "required"
                 else result.warnings).append(ratio_note)
            try:
                cover_sha256 = _file_sha256(cover_file)
            except OSError as exc:
                result.blocked.append(f"封面读取失败：{exc}")

    # --- 可见性
    visibility = str(intent.visibility or "public")
    if visibility not in VISIBILITIES:
        result.blocked.append(f"visibility {visibility!r} 不在 {VISIBILITIES}")

    # --- 铁律自检（防御性）
    if intent.scheduled_at:
        result.warnings.append(
            "已设置 scheduled_at —— 请确认这是人工决定，而非自动流程"
        )

    if intent.cover_origin == "generated_ai" and not cover:
        result.blocked.append("AI 封面来源要求提供独立图片文件")
    if intent.cover_origin == "generated_ai":
        proof_path = Path(intent.cover_proof_path)
        if not intent.cover_proof_path or not proof_path.is_file():
            result.blocked.append("AI 专属封面缺少生成证据文件")
        else:
            try:
                proof = json.loads(proof_path.read_text(encoding="utf-8"))
                source = Path(proof["source_image_path"])
                if (proof.get("kind") != "ai_generated"
                        or not proof.get("model")
                        or proof.get("final_cover_sha256", "").upper() != cover_sha256
                        or not source.is_file()
                        or source.resolve() == video.resolve()
                        or _file_sha256(source) != proof.get("source_image_sha256", "").upper()):
                    raise ValueError("生成证据与原图或最终封面不一致")
                from PIL import Image
                with Image.open(source) as original:
                    original.verify()
                cover_proof_sha256 = _file_sha256(proof_path)
            except (OSError, KeyError, ValueError, TypeError) as exc:
                result.blocked.append(f"AI 封面生成证据无效：{exc}")
    package_id = intent.package_id or ("pkg-" + hashlib.sha256(
        f"{video_sha256}:{cover_sha256}".encode("ascii")).hexdigest()[:32])
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{15,127}", package_id):
        result.blocked.append("package_id 须为 16–128 位字母数字或 . _ : -")
    location_mode = ("set" if location else
                     "clear" if intent.platform == "shipinhao" else "keep")
    result.payload = {
        "account_id": int(intent.account_id),
        "media_type": "video",
        "title": title,
        "desc": desc,
        "topics": str(intent.topics or ""),
        "location": location,
        "media_paths": [str(video)],
        "visibility": visibility,
        "allow_save": bool(intent.allow_save),
        "cover_path": cover,
        "scheduled_at": intent.scheduled_at,
        "contract_version": 2,
        "package_id": package_id,
        "package_revision": intent.package_revision,
        "expected_platform": intent.platform,
        "cover_policy": intent.cover_policy,
        "cover_origin": intent.cover_origin,
        "cover_proof_path": intent.cover_proof_path,
        "cover_proof_sha256": cover_proof_sha256,
        "video_sha256": video_sha256,
        "cover_sha256": cover_sha256,
        "location_mode": location_mode,
        "source_rights_status": intent.source_rights_status,
    }
    return result


def _check_cover_ratio(path: Path) -> str | None:
    """严格检查图片可解码、尺寸和 3:4 比例。"""
    try:
        from PIL import Image  # type: ignore
    except Exception:  # noqa: BLE001
        return "缺少 Pillow，无法核验封面"
    try:
        with Image.open(path) as img:
            img.load()
            width, height = img.size
            if img.format not in ("JPEG", "PNG"):
                return "封面必须是 JPEG 或 PNG 图片"
    except Exception as exc:  # noqa: BLE001
        return f"封面尺寸读取失败：{exc}"
    if width < 600 or height < 800:
        return f"封面尺寸过小：{width}×{height}，至少需要 600×800"
    if not height:
        return "封面高度为 0"
    ratio = width / height
    if abs(ratio - COVER_RATIO) > COVER_RATIO_TOLERANCE:
        return (
            f"封面宽高比 {ratio:.3f} 偏离 3:4（{COVER_RATIO:.3f}）"
            f" —— 指定封面要求 3:4"
        )
    return None


# ---------------------------------------------------------------------------
# HTTP 和持久提交回执
# ---------------------------------------------------------------------------


def _post_json(base_url: str, path: str, payload: Mapping[str, Any], *,
               idempotency_key: str, timeout: float = 20.0):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url=f"{base_url.rstrip('/')}{path}",
        data=body,
        headers={"Content-Type": "application/json", "Idempotency-Key": idempotency_key},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise PublishAdapterError(
            f"creatorhub 返回 {exc.code}：{detail[:400]}", code="http"
        ) from exc
    except error.URLError as exc:
        raise PublishAdapterError(
            f"无法连接 creatorhub（{base_url}）：{exc.reason}", code="missing"
        ) from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def probe_service(base_url: str, *, timeout: float = 5.0) -> tuple[bool, str]:
    """G1：探测 creatorhub 是否存活。

    2026-09-22 事故：适配器测试 ``--commit`` 时未探测服务状态，
    而服务恰好在跑 ⇒ 真的创建并触发了一条发布任务。
    **所以 ``--commit`` 之前必须强制探活。**
    """
    url = f"{base_url.rstrip('/')}/api/publish"
    try:
        with request.urlopen(url, timeout=timeout) as resp:
            return True, f"HTTP {resp.status}"
    except error.HTTPError as exc:
        # 能收到 HTTP 响应就说明服务活着（4xx/5xx 也算活着）
        return True, f"HTTP {exc.code}"
    except error.URLError as exc:
        return False, str(exc.reason)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def require_strict_capability(base_url: str, platform: str, *, timeout: float = 5.0) -> None:
    url = f"{base_url.rstrip('/')}/api/publish/capabilities"
    try:
        with request.urlopen(url, timeout=timeout) as response:
            data = json.load(response)
    except (error.HTTPError, error.URLError, ValueError) as exc:
        raise PublishAdapterError(f"无法确认严格发布契约：{exc}", code="capability") from exc
    if (data.get("contract_version") != 2
            or platform not in data.get("required_cover_platforms", [])):
        raise PublishAdapterError(f"CreatorHub 不支持 {platform} 必需封面发布契约 v2", code="capability")


def submission_key(payload: Mapping[str, Any]) -> str:
    identity = ":".join(str(payload[name]) for name in (
        "package_id", "package_revision", "expected_platform", "account_id"))
    return "haike-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


def prepare_receipt(payload: Mapping[str, Any], receipt_dir: Path) -> tuple[Path, str]:
    """在请求前落盘；重跑时始终复用原编号，并检查提交内容未变化。"""
    key = submission_key(payload)
    fingerprint = hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest().upper()
    receipt_dir.mkdir(parents=True, exist_ok=True)
    path = receipt_dir / f"{key}.json"
    document = {"idempotency_key": key, "payload_sha256": fingerprint,
                "package_id": payload["package_id"], "platform": payload["expected_platform"],
                "account_id": payload["account_id"], "task_id": None}
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("payload_sha256") != fingerprint:
            raise PublishAdapterError("原提交回执与当前 payload 不一致；请修订发布包版本", code="conflict")
    else:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
    return path, key


def record_task_id(path: Path, task_id: Any) -> None:
    if task_id is None:
        return
    document = json.loads(path.read_text(encoding="utf-8"))
    document["task_id"] = task_id
    pending = path.with_suffix(".tmp")
    with pending.open("w", encoding="utf-8") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, path)


def create_publish_task(
    base_url: str,
    payload: Mapping[str, Any],
    *,
    idempotency_key: str,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """创建可能立即执行的真实发布任务；重试必须使用原编号。"""
    return _post_json(base_url, "/api/publish", payload,
                      idempotency_key=idempotency_key, timeout=timeout)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="publish_adapter.py",
        description=(
            "把 Haike 成片映射为 creatorhub 发布任务。"
            "默认 dry-run；--commit 会创建可能立即执行的真实发布任务。"
        ),
    )
    parser.add_argument("--video", type=Path, required=True, help="成片路径")
    parser.add_argument("--platform", required=True, choices=ALLOWED_PLATFORMS)
    parser.add_argument("--account-id", type=int, default=None, help="creatorhub 账号 ID")
    parser.add_argument("--title", default="", help=f"标题（本地截断到 {TITLE_MAX} 字）")
    parser.add_argument("--desc", default="", help="描述（关键词放开头）")
    parser.add_argument("--topics", default="", help="话题串")
    parser.add_argument("--cover", default="", help="竖封面 3:4 图片路径")
    parser.add_argument("--cover-policy", choices=("required", "optional"),
                        default="required", help="指定封面是否为发表前必需")
    parser.add_argument("--cover-origin", choices=("generated_ai", "provided_image", "approved_video_frame"),
                        default="provided_image", help="封面来源")
    parser.add_argument("--cover-proof", default="", help="AI 生成原图与最终封面哈希的证据 JSON")
    parser.add_argument("--package-id", default="", help="稳定发布包 ID；省略则由媒体哈希生成")
    parser.add_argument("--package-revision", type=int, default=1, help="发布包版本")
    parser.add_argument("--source-rights-status", choices=("unknown", "confirmed", "owned"),
                        default="unknown", help="来源素材使用范围核对结果")
    parser.add_argument("--receipt-dir", type=Path,
                        default=Path(__file__).resolve().parent.parent / ".backlot" / "publish-receipts",
                        help="提交回执目录")
    parser.add_argument("--location", default="", help="位置 POI（视频号）")
    parser.add_argument("--visibility", default="public", choices=VISIBILITIES)
    parser.add_argument("--no-allow-save", action="store_true", help="禁止他人保存（抖音）")
    parser.add_argument("--scheduled-at", default=None, help="ISO 8601；留空=尽快发")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="creatorhub 地址")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="只打印 payload，不发请求（默认开启）",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="实际创建任务（⚠️ 可能立即触发发布）。与 --dry-run 互斥。",
    )
    parser.add_argument(
        "--i-know-this-creates-a-real-task",
        dest="acknowledge",
        action="store_true",
        help="G3 闸：--commit 时必须同时提供，显式确认你理解这会真的落库。",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出 payload")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.commit:
        args.dry_run = False

    if args.account_id is None:
        print(
            "[BLOCKED] 未提供 --account-id。"
            "该值来自 creatorhub 的账号列表，无法自动推断（见 contracts/publish-v1.md）。",
            file=sys.stderr,
        )
        return EXIT_NOT_CONFIGURED

    intent = PublishIntent(
        account_id=args.account_id,
        platform=args.platform,
        video_path=args.video,
        title=args.title,
        desc=args.desc,
        topics=args.topics,
        location=args.location,
        visibility=args.visibility,
        allow_save=not args.no_allow_save,
        cover_path=args.cover,
        scheduled_at=args.scheduled_at,
        cover_policy=args.cover_policy,
        cover_origin=args.cover_origin,
        cover_proof_path=args.cover_proof,
        package_id=args.package_id,
        package_revision=args.package_revision,
        source_rights_status=args.source_rights_status,
    )

    result = build_publish_payload(intent)

    print("=" * 66)
    print(f"平台     : {PLATFORM_LABELS.get(args.platform, args.platform)} ({args.platform})")
    print(f"成片     : {args.video}")
    print(f"账号 ID  : {args.account_id}")
    print(f"模式     : {'DRY-RUN（不发请求）' if args.dry_run else 'CREATE REAL TASK（可能立即发表）'}")
    print("=" * 66)

    if result.warnings:
        print("\n警告：")
        for item in result.warnings:
            print(f"  [WARN] {item}")

    if result.blocked:
        print("\n阻断：")
        for item in result.blocked:
            print(f"  [BLOCKED] {item}")
        print("\n未创建任何任务。")
        return EXIT_BLOCKED

    print("\npayload：")
    print(json.dumps(result.payload, ensure_ascii=False, indent=2))

    if args.dry_run:
        print(
            "\nDRY-RUN 结束。未发送任何请求。\n"
            "确认无误后，必须同时加 --commit --i-know-this-creates-a-real-task。"
        )
        return EXIT_OK

    if args.source_rights_status == "unknown":
        print("\n[BLOCKED] 来源素材使用范围尚未确认，不创建公开发布任务。", file=sys.stderr)
        return EXIT_BLOCKED

    # ---------------- G3：显式确认 ----------------
    if not args.acknowledge:
        print(
            "\n[BLOCKED] 拒绝执行 --commit。\n"
            "  创建任务在 creatorhub 的默认引擎配置下**可能立即触发真实发布**。\n"
            "  如果你确认要落库，请同时提供：\n"
            "      --i-know-this-creates-a-real-task\n"
            "  （2026-09-22 曾因缺少此闸而误触发过一次真实发布，见 "
            "Haike-Videohub/docs/verification-report.md 事故记录）",
            file=sys.stderr,
        )
        return EXIT_BLOCKED

    # ---------------- G1：强制探活 ----------------
    alive, detail = probe_service(args.base_url)
    if not alive:
        print(
            f"\n[BLOCKED] creatorhub 不可达（{args.base_url}）：{detail}\n"
            "  见 steps/05-creatorhub.md。",
            file=sys.stderr,
        )
        return EXIT_NOT_CONFIGURED
    print(f"\n[G1] creatorhub 探活通过：{detail}")
    try:
        require_strict_capability(args.base_url, args.platform)
    except PublishAdapterError as exc:
        print(f"\n[BLOCKED] {exc}", file=sys.stderr)
        return EXIT_NOT_CONFIGURED
    print("[G2] CreatorHub 严格封面契约 v2 已确认")

    # ---------------- 二次确认（交互式；无人值守时应失败退出）----------------
    if sys.stdin.isatty():
        try:
            answer = input(
                f"即将在平台 {PLATFORM_LABELS.get(args.platform, args.platform)} "
                f"上创建真实任务。确认？输入 yes 继续："
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer != "yes":
            print("已取消。未创建任何任务。")
            return EXIT_BLOCKED
    else:
        print(
            "[G1b] 非交互式环境（stdin 非 TTY）—— 已通过 --i-know-this-creates-a-real-task 视为确认。",
        )

    try:
        receipt_path, key = prepare_receipt(result.payload, args.receipt_dir)
        created = create_publish_task(args.base_url, result.payload, idempotency_key=key)
        record_task_id(receipt_path, created.get("id"))
    except PublishAdapterError as exc:
        print(f"\n[FAIL] {exc}", file=sys.stderr)
        if exc.code == "missing":
            print("提示：creatorhub 未运行？见 steps/05-creatorhub.md", file=sys.stderr)
        return EXIT_INPUT
    except (OSError, ValueError) as exc:
        print(f"\n[FAIL] 回执写入失败：{exc}", file=sys.stderr)
        return EXIT_INPUT

    print("\n已创建任务：")
    print(json.dumps(created, ensure_ascii=False, indent=2)[:1500])
    print(
        "\n★ 请到 creatorhub 面板人工确认结果。\n"
        f"★ 提交回执：{receipt_path}。重试请沿用此回执。\n"
        "★ 若任务进入 publishing/uncertain，则既不能改也不能删（见 publish-v1.md §6.2）。"
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
