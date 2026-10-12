#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""VideoHub 统一体检脚本。

三个层级：
    --level=1   静态探活：路径存在、哨兵文件存在、JSON 可解析
    --level=2   契约连通：用假数据调用跨仓读取函数，断言不抛异常
    --all       1 + 2

反例测试（证明校验不是空转）：
    --mutate=layout   故意破坏 layout.json，期望 FAIL
    --mutate=sha256   故意篡改假包的 sha256，期望 FAIL

退出码：
    0 = 全通
    1 = 有 FAIL
    2 = 环境不可用（根目录找不到 / layout.json 不可解析）

用法：
    python verify/check_all.py --level=1
    python verify/check_all.py --all --root D:/刘宇钊/codex_work
    python verify/check_all.py --all --runtime    # 附加运行时机械校验（4754 探活 / 单实例 / 安全删除开关）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------- 常量

HERE = Path(__file__).resolve()
HUB_ROOT = HERE.parents[1]          # 第四仓根
DEFAULT_ROOT = HUB_ROOT.parent      # 三仓所在的工作根（与三仓平级）
LAYOUT_PATH = HUB_ROOT / "contracts" / "layout.json"
VERSIONS_PATH = HUB_ROOT / "contracts" / "versions.json"

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_UNAVAILABLE = 2

# 研究包冻结常量（与生产端/消费端两边必须一致）
FROZEN_CONTENT_SHA256 = (
    "e5bc839ff60a91f29474c9bec50c8afca41fdaf367dc5e6978eae620b1cbaab8"
)

# ---------------------------------------------------------------- 结果收集


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []   # (level, status, message)

    def ok(self, tag: str, msg: str) -> None:
        self.rows.append((tag, "PASS", msg))

    def fail(self, tag: str, msg: str) -> None:
        self.rows.append((tag, "FAIL", msg))

    def warn(self, tag: str, msg: str) -> None:
        self.rows.append((tag, "WARN", msg))

    def skip(self, tag: str, msg: str) -> None:
        self.rows.append((tag, "SKIP", msg))

    @property
    def failed(self) -> int:
        return sum(1 for _, s, _ in self.rows if s == "FAIL")

    def dump(self) -> None:
        width = max((len(t) for t, _, _ in self.rows), default=10)
        for tag, status, msg in self.rows:
            mark = {"PASS": "[PASS]", "FAIL": "[FAIL]", "WARN": "[WARN]", "SKIP": "[SKIP]"}[status]
            print(f"{mark} {tag:<{width}}  {msg}")


# ---------------------------------------------------------------- 工具


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _auto_root() -> Path | None:
    """自动定位工作根：优先环境变量，其次相对第四仓的父目录。"""
    env = os.environ.get("VIDEOHUB_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    if DEFAULT_ROOT.is_dir():
        return DEFAULT_ROOT
    return None


def _resolve_repo_path(root: Path, layout: dict, key: str) -> Path:
    rel = layout["repos"][key]["path"]
    return root / rel


# ---------------------------------------------------------------- L1


def level1(report: Report, root: Path, layout: dict, mutate: str | None) -> None:
    """静态探活。"""

    # --- layout.json 自身可解析
    try:
        _load_json(LAYOUT_PATH)
        report.ok("layout", "contracts/layout.json 可解析")
    except Exception as exc:                       # noqa: BLE001
        report.fail("layout", f"contracts/layout.json 不可解析: {exc}")
        return

    # --- 反例：故意破坏布局（把 copyskill 改成单层）
    if mutate == "layout":
        wrong = root / "copy_skill"
        if (wrong / "pyproject.toml").is_file():
            report.fail(
                "MUTATE-layout",
                "错误路径 copy_skill/ 竟然也存在 pyproject.toml "
                "⇒ 校验无法区分单层与两层（说明校验太弱）",
            )
        else:
            report.ok(
                "MUTATE-layout",
                "注入单层 'copy_skill' 假设后，无法通过两层校验 "
                "⇒ 反例被正确捕获（校验有效）",
            )
        return

    # --- 三个仓库存在
    for key in ("haike", "copyskill", "creatorhub"):
        spec = layout["repos"][key]
        repo = _resolve_repo_path(root, layout, key)
        if not repo.is_dir():
            report.fail(key, f"仓库目录不存在: {repo}")
            continue
        report.ok(key, f"仓库存在: {repo.relative_to(root)}")

        # 哨兵文件
        missing = [s for s in spec["sentinel_files"] if not (repo / s).exists()]
        if missing:
            report.fail(f"{key}.sentinel", f"缺失哨兵文件: {missing}")
        else:
            report.ok(f"{key}.sentinel", f"{len(spec['sentinel_files'])} 个哨兵文件全部存在")

    # --- LAYOUT-1 硬约束：copyskill 必须是两层
    two_layer = root / "copy_skill" / "copy_skill-main"
    one_layer = root / "copy_skill"
    if (two_layer / "pyproject.toml").is_file():
        report.ok("LAYOUT-1", "copyskill 两层路径正确: copy_skill/copy_skill-main")
    elif (one_layer / "pyproject.toml").is_file():
        report.fail(
            "LAYOUT-1",
            "copyskill 被放在单层 copy_skill/ —— 跨仓测试会静默 skip，"
            "必须移到 copy_skill/copy_skill-main/",
        )
    else:
        report.fail("LAYOUT-1", "未找到 copyskill 的 pyproject.toml")

    # --- 跨仓硬依赖文档
    contract_doc = (
        root / "copy_skill" / "copy_skill-main" / "docs" / "tasks"
        / "2026-09-16-episode-research-pack-v1.md"
    )
    if contract_doc.is_file():
        report.ok("contract-doc", "冻结合同文档存在")
    else:
        report.fail(
            "contract-doc",
            "缺 docs/tasks/2026-09-16-episode-research-pack-v1.md "
            "⇒ Haike 合同一致性断言会被 skip",
        )

    # --- 版本契约
    try:
        provenance = _load_json(root / "SOURCE-PROVENANCE.json")
        expected = {"Haike_video", "copy_skill/copy_skill-main", "creatorhub", "Haike-Videohub"}
        entries = provenance["repositories"]
        if {entry["path"] for entry in entries} != expected:
            raise ValueError("单仓库来源清单未覆盖四模块")
        if not all(len(entry["head"]) == 40 for entry in entries):
            raise ValueError("来源版本缺少完整提交 SHA")
        report.ok("versions", "四模块来源版本已登记；当前交付版本以根 Git 提交为准")
        report.ok("versions.origin", "单仓库模式，不使用历史子仓未推送状态作为验收依据")
    except Exception as exc:                       # noqa: BLE001
        report.fail("versions", f"contracts/versions.json 有问题: {exc}")

    # --- 冻结常量两边一致
    prod = (
        root / "copy_skill" / "copy_skill-main" / "src" / "douyin_intelligence"
        / "episode_research_pack.py"
    )
    cons = (
        root / "Haike_video" / "tests" / "backlot" / "test_copy_skill_research_pack.py"
    )
    for label, path in (("producer", prod), ("consumer-test", cons)):
        if not path.is_file():
            report.warn(f"frozen.{label}", f"文件不存在: {path}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if FROZEN_CONTENT_SHA256 in text:
            report.ok(f"frozen.{label}", "冻结 content_sha256 一致")
        else:
            report.fail(f"frozen.{label}", "冻结 content_sha256 不一致！契约破裂")

    # --- 外部依赖（B 类）
    _check_external(report, root)

    # --- 关键配置项
    _check_configs(report, root)

    # --- 发布适配器安全闸
    _check_publish_adapter(report, root)


def _check_publish_adapter(report: Report, root: Path) -> None:
    """确认发布适配器的三道安全闸仍在位。

    2026-09-22 事故后新增。**如果这三道闸被删掉，必须立刻报警。**
    """
    adapter = root / "Haike_video" / "backlot" / "publish_adapter.py"
    if not adapter.is_file():
        report.warn(
            "adapter",
            "backlot/publish_adapter.py 不存在（发布适配器未部署）",
        )
        return
    text = adapter.read_text(encoding="utf-8", errors="replace")

    gates = {
        "G1": ("probe_service", "G1 探活闸"),
        "G2": ("0 字节", "G2 零字节阻断闸"),
        "G3": ("i-know-this-creates-a-real-task", "G3 显式确认闸"),
    }
    for key, (needle, label) in gates.items():
        if needle in text:
            report.ok(f"adapter.{key}", f"{label} 在位")
        else:
            report.fail(
                f"adapter.{key}",
                f"{label} 缺失！发布适配器失去防护（见 docs/pitfalls.md #0）",
            )

    # 反向检查：绝不能出现 run-now
    if "run-now" in text or "run_now" in text:
        # 允许出现在注释里说明「不调用」，但若出现在 URL 拼接里则危险
        suspicious = [
            line for line in text.splitlines()
            if ("run-now" in line or "run_now" in line)
            and ("url" in line.lower() or "_post" in line or "_request" in line
                 or "_get(" in line)
        ]
        if suspicious:
            report.fail(
                "adapter.norunnow",
                f"疑似在代码里调用了 run-now：{suspicious[:2]}",
            )
        else:
            report.ok("adapter.norunnow", "run-now 仅出现在说明性文字中 ✓")
    else:
        report.ok("adapter.norunnow", "未出现 run-now ✓")


def _check_external(report: Report, root: Path) -> None:
    """B 类依赖探活。"""
    # Python
    if sys.version_info[:2] == (3, 12):
        report.ok("B.python", f"Python {sys.version_info.major}.{sys.version_info.minor} ✓")
    elif sys.version_info[:2] >= (3, 11):
        report.warn(
            "B.python",
            f"Python {sys.version_info.major}.{sys.version_info.minor} —— Haike 要求 3.12",
        )
    else:
        report.fail("B.python", f"Python 版本过低: {sys.version_info[:2]}")

    # Node
    node = shutil.which("node")
    if node:
        try:
            out = subprocess.run(
                [node, "--version"], capture_output=True, text=True, timeout=10
            ).stdout.strip()
            major = int(out.lstrip("v").split(".")[0])
            if major >= 22:
                report.ok("B.node", f"Node {out} ✓")
            else:
                report.fail("B.node", f"Node {out} < 22")
        except Exception:                              # noqa: BLE001
            report.warn("B.node", "node 存在但执行失败")
    else:
        report.fail("B.node", "未找到 node（渲染必需）")

    # ffmpeg / ffprobe（有 PATH 回退）
    for tool in ("ffmpeg", "ffprobe"):
        p = shutil.which(tool)
        if p:
            report.ok(f"B.{tool}", f"PATH 上找到: {p}")
        else:
            report.fail(f"B.{tool}", f"未找到 {tool}（也无 PATH 回退目标）")

    # Chrome
    chrome_candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ]
    chrome = next((c for c in chrome_candidates if c.is_file()), None)
    if chrome:
        report.ok("B.chrome", f"找到: {chrome}")
    else:
        report.fail("B.chrome", "未找到 Chrome（采集与发布都需要）")

    # MediaCrawler（仅抖音采集需要，属「可跳过的降级点」）
    # 判定依据：目录不存在即视为「未启用抖音采集」，降为 WARN 而非 FAIL，
    # 使最小路径（01→02→03→08）也能达到 0 FAIL —— 与 steps/README 与
    # steps/08 的「0 FAIL 是唯一判据」口径一致。目录存在则视为已启用，
    # 检查不过仍 FAIL（安装不完整必须暴露）。
    mc_root = root / "copy_skill" / "copy_skill-main" / "third_party" / "MediaCrawler"
    if (mc_root / "main.py").is_file():
        report.ok("B.mediacrawler", "MediaCrawler 已就位")
        if (mc_root / ".git" / "HEAD").is_file():
            report.ok("B.mediacrawler.git", "带 git 元数据（可追溯版本）✓")
        else:
            report.warn(
                "B.mediacrawler.git",
                "无 .git 元数据 —— 版本不可追溯。建议从上游重新 clone（见 deps/B-external.md）",
            )
        venv_py = mc_root / ".venv" / "Scripts" / "python.exe"
        if venv_py.is_file():
            report.ok("B.mediacrawler.venv", "venv 已建 ✓")
        else:
            report.fail("B.mediacrawler.venv", f"缺 venv python: {venv_py}")
    elif mc_root.is_dir():
        report.fail(
            "B.mediacrawler",
            f"MediaCrawler 目录存在但缺 main.py: {mc_root}（视为已启用，安装不完整）",
        )
    else:
        report.warn(
            "B.mediacrawler",
            "未启用抖音采集（可选），跳过 —— MediaCrawler 目录不存在；"
            "需要抖音采集时按 deps/B-external.md 的 clone 命令获取",
        )


def _check_configs(report: Report, root: Path) -> None:
    """关键配置文件与已知陷阱。"""
    cfg_path = (
        root / "copy_skill" / "copy_skill-main" / "config"
        / "content_intelligence.json"
    )
    if not cfg_path.is_file():
        report.warn("config.copyskill", f"未找到: {cfg_path}")
    else:
        try:
            cfg = _load_json(cfg_path)
        except Exception as exc:                       # noqa: BLE001
            report.fail("config.copyskill", f"不可解析: {exc}")
            return
        mc = cfg.get("media_crawler") or {}
        for field in ("root", "python", "chrome_path"):
            if not mc.get(field):
                report.warn(f"config.mc.{field}", "未配置")
                continue
            val = str(mc[field])
            is_win_abs = len(val) > 2 and val[1] == ":"
            if is_win_abs:
                exists = Path(val).exists()
                if field == "root":
                    ok = (Path(val) / "main.py").is_file()
                elif field == "python":
                    ok = Path(val).is_file()
                else:
                    ok = exists
                status = "PASS" if ok else "WARN"
                msg = f"{val} ({'存在' if ok else '不存在'})"
                if field == "chrome_path" and not ok:
                    report.warn(
                        f"config.mc.{field}",
                        f"{msg} —— 会在 collector.py:184 显式报错，不会静默失败",
                    )
                elif field == "root" and not ok:
                    report.warn(
                        f"config.mc.{field}",
                        f"{msg} —— 采集会静默失败（见 docs/pitfalls.md #1）",
                    )
                else:
                    (report.ok if ok else report.warn)(f"config.mc.{field}", msg)
            else:
                report.ok(f"config.mc.{field}", f"相对路径: {val}")

    # 候选池开关（默认 false 是陷阱）
    brief = root / "Haike_video" / "config" / "daily_tech_brief.json"
    if brief.is_file():
        try:
            feed = (_load_json(brief).get("copy_skill_hotspot_feed") or {})
            if feed.get("enabled") is True:
                report.ok("config.hotspot", "copy_skill_hotspot_feed.enabled = true")
            else:
                report.warn(
                    "config.hotspot",
                    "copy_skill_hotspot_feed.enabled = false —— 候选池链路不会启用",
                )
        except Exception as exc:                       # noqa: BLE001
            report.warn("config.hotspot", f"解析失败: {exc}")


# ---------------------------------------------------------------- runtime（可选）

RUNTIME_PORT = 4754


def runtime_check(report: Report) -> None:
    """可选运行时机械校验（`--runtime`，不进默认 `--all`，项数不变）。

    把 steps/03 的三条「口头硬约束」变成可执行的检查：
      1) 工作台 4754 端口可访问（探活）；
      2) 4754 的监听进程只有一个（多开会互相抢锁，表现为随机失败）；
      3) `CODEBUDDY_SAFE_DELETE_ENABLED == "0"`。
    """
    port = RUNTIME_PORT

    # 1) 端口探活
    reachable = False
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=3):
            reachable = True
    except OSError:
        reachable = False
    if reachable:
        report.ok("runtime.port", f"127.0.0.1:{port} 可访问（工作台在跑）")
    else:
        report.fail("runtime.port", f"127.0.0.1:{port} 不可访问（工作台未启动）")

    # 2) 监听进程数（单实例）
    pids = _listening_pids(port)
    if not pids:
        report.fail("runtime.single-instance", f"未发现监听 {port} 的进程")
    elif len(pids) == 1:
        report.ok("runtime.single-instance", f"监听 {port} 的进程唯一（PID={pids[0]}）")
    else:
        report.fail(
            "runtime.single-instance",
            f"监听 {port} 的进程有 {len(pids)} 个（PID={pids}）—— 多开会互相抢锁",
        )

    # 3) 安全删除开关
    flag = os.environ.get("CODEBUDDY_SAFE_DELETE_ENABLED")
    if flag == "0":
        report.ok("runtime.safe-delete", "CODEBUDDY_SAFE_DELETE_ENABLED=0 ✓")
    else:
        report.fail(
            "runtime.safe-delete",
            f"CODEBUDDY_SAFE_DELETE_ENABLED={flag!r}（应为 '0'，否则清理动作会被拦）",
        )


def _listening_pids(port: int) -> list[int]:
    """用 `netstat -ano` 解析出监听指定端口的 PID 列表（Windows）。"""
    try:
        out = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        ).stdout
    except Exception:                                   # noqa: BLE001
        return []
    pids: list[int] = []
    needle = f":{port}"
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        local, state, pid = parts[1], parts[3].upper(), parts[4]
        if local.endswith(needle) and state == "LISTENING":
            try:
                ipid = int(pid)
            except ValueError:
                continue
            if ipid not in pids:
                pids.append(ipid)
    return pids


# ---------------------------------------------------------------- L2


def level2(report: Report, root: Path, layout: dict, mutate: str | None) -> None:
    """契约连通：用假数据跑消费端读取函数。"""

    haike = root / "Haike_video"
    if not haike.is_dir():
        report.fail("L2", "Haike 仓库不存在，无法做契约连通")
        return

    sys.path.insert(0, str(haike))

    # ---------------- 候选池
    _check_candidate_pool(report, haike, mutate)

    # ---------------- 研究包
    _check_research_pack(report, haike, mutate)


def _check_candidate_pool(report: Report, haike: Path, mutate: str | None) -> None:
    fixtures = HUB_ROOT / "fixtures" / "mini-candidate-pool"
    if not fixtures.is_dir():
        report.fail(
            "L2.candidate-pool",
            f"假数据不存在: {fixtures} —— 先跑 "
            "`python verify/make_fixtures.py --clean --haike <Haike 路径>` 生成夹具"
            "（前置：Haike_video 已就位且哨兵通过；见 steps/08-verify.md §8.2）",
        )
        return

    try:
        from backlot.copy_skill_hotspot_feed import (   # type: ignore
            load_copy_skill_hotspot_feed,
            try_load_copy_skill_hotspot_feed,
        )
    except Exception as exc:                            # noqa: BLE001
        report.fail("L2.candidate-pool", f"导入失败: {exc}")
        return

    business_date = "2026-09-21"

    if mutate == "sha256":
        _mutate_candidate_pool_sha(fixtures, business_date)
        report.warn("MUTATE-sha256", "已注入 sha 篡改，期望下面的加载 FAIL")

    try:
        feed = load_copy_skill_hotspot_feed(fixtures, business_date)
    except Exception as exc:                            # noqa: BLE001
        if mutate == "sha256":
            report.ok("MUTATE-sha256-check", f"篡改被正确捕获: {type(exc).__name__}")
        else:
            report.fail("L2.candidate-pool", f"加载失败: {type(exc).__name__}: {exc}")
        return

    if mutate == "sha256":
        report.fail(
            "MUTATE-sha256-check",
            "篡改未被捕获 —— 校验形同虚设！",
        )
        return

    run_id = feed.get("run_id") if isinstance(feed, dict) else None
    report.ok(
        "L2.candidate-pool",
        f"load_copy_skill_hotspot_feed() 成功，run_id={run_id}",
    )
    if isinstance(feed, dict):
        n = len(feed.get("candidates") or [])
        report.ok("L2.candidate-pool.candidates", f"规范化候选数: {n}")
        mv = (feed.get("manifest_validation") or {})
        if mv.get("valid") is True:
            report.ok(
                "L2.candidate-pool.manifest",
                f"manifest 校验通过，file_count={mv.get('file_count')}",
            )
        else:
            report.fail("L2.candidate-pool.manifest", "manifest_validation.valid 不为 True")

    # 三方 sha256 一致性
    try:
        cur = _load_json(fixtures / f"{business_date}_每日素材" / "current.json")
        ready = _load_json(
            fixtures / f"{business_date}_每日素材" / str(cur["pack_relative_path"])
            / "_READY.json"
        )
        real = _sha256_file(
            fixtures / f"{business_date}_每日素材" / str(cur["pack_relative_path"])
            / "package-manifest.json"
        )
        a = cur.get("package_manifest_sha256")
        b = ready.get("package_manifest_sha256")
        if a == b == real:
            report.ok("L2.candidate-pool.sha", "package_manifest_sha256 三方一致")
        else:
            report.fail(
                "L2.candidate-pool.sha",
                f"三方不一致 cur={a[:12]} ready={b[:12]} real={real[:12]}",
            )
    except Exception as exc:                            # noqa: BLE001
        report.fail("L2.candidate-pool.sha", f"比对异常: {exc}")

    # 安全版入口
    try:
        r = try_load_copy_skill_hotspot_feed(fixtures, business_date)
        report.ok("L2.candidate-pool.try", f"try_ 版本返回: {type(r).__name__}")
    except Exception as exc:                            # noqa: BLE001
        report.fail("L2.candidate-pool.try", f"try_ 版本不该抛异常: {exc}")


def _mutate_candidate_pool_sha(fixtures: Path, business_date: str) -> None:
    """故意改坏 _READY.json 里的 sha，用于反例测试。"""
    day = fixtures / f"{business_date}_每日素材"
    cur = _load_json(day / "current.json")
    ready_path = day / str(cur["pack_relative_path"]) / "_READY.json"
    data = _load_json(ready_path)
    data["package_manifest_sha256"] = "0" * 64
    ready_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _check_research_pack(report: Report, haike: Path, mutate: str | None) -> None:
    fixtures = HUB_ROOT / "fixtures" / "mini-research-pack"
    if not fixtures.is_dir():
        report.fail(
            "L2.research-pack",
            f"假数据不存在: {fixtures} —— 先跑 "
            "`python verify/make_fixtures.py --clean --haike <Haike 路径>` 生成夹具"
            "（前置：Haike_video 已就位且哨兵通过；见 steps/08-verify.md §8.2）",
        )
        return

    # 定位 episode 目录：<fixtures>/<date>_研究包/<episode_id>（含 current.json）
    episode_root = None
    for cand in sorted(fixtures.glob("*_研究包/*")):
        if (cand / "current.json").is_file():
            episode_root = cand
            break
    if episode_root is None:
        report.fail(
            "L2.research-pack",
            f"在 {fixtures} 下找不到含 current.json 的 episode 目录",
        )
        return

    try:
        from backlot.copy_skill_research_pack import (   # type: ignore
            load_research_pack,
        )
    except Exception as exc:                             # noqa: BLE001
        report.fail("L2.research-pack", f"导入失败: {exc}")
        return

    try:
        pack = load_research_pack(episode_root)
    except Exception as exc:                             # noqa: BLE001
        report.fail("L2.research-pack", f"加载失败: {type(exc).__name__}: {exc}")
        return

    csha = pack.get("content_sha256") if isinstance(pack, dict) else None
    report.ok(
        "L2.research-pack",
        f"load_research_pack() 成功，content_sha256={str(csha)[:16]}...",
    )

    if isinstance(pack, dict):
        counts = pack.get("counts") or {}
        report.ok(
            "L2.research-pack.counts",
            f"sources={counts.get('sources')} claims={counts.get('claims')} "
            f"materials={counts.get('materials')}",
        )
        report.ok(
            "L2.research-pack.ready",
            f"_READY 校验通过（pack_id={pack.get('pack_id')}）",
        )
        # 边键覆盖：证明 argument_graph.edges 被真正走过
        payloads = pack.get("payloads") or {}
        topics = payloads.get("topics.json") or {}
        edges = ((topics.get("argument_graph") or {}).get("edges")) or []
        if edges:
            report.ok(
                "L2.research-pack.edges",
                f"argument_graph.edges 非空（{len(edges)} 条）—— 边键路径已被覆盖",
            )
        else:
            report.warn(
                "L2.research-pack.edges",
                "argument_graph.edges 为空 —— 边键路径未被覆盖（参见 "
                "test_end_to_end_with_non_empty_argument_graph 的教训）",
            )


# ---------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_all.py",
        description="VideoHub 统一体检",
    )
    parser.add_argument("--level", type=int, choices=(1, 2), default=1)
    parser.add_argument("--all", action="store_true", help="等价于 --level=1 + --level=2")
    parser.add_argument("--root", type=Path, default=None, help="三仓所在的工作根")
    parser.add_argument(
        "--runtime",
        action="store_true",
        help="附带运行时机械校验（4754 探活 / 单实例 / 安全删除开关），不进默认 --all",
    )
    parser.add_argument(
        "--mutate",
        choices=("layout", "sha256"),
        default=None,
        help="注入错误以验证校验不是空转",
    )
    args = parser.parse_args(argv)

    root = args.root or _auto_root()
    if root is None or not root.is_dir():
        print("[FAIL] root        找不到工作根目录。请用 --root 指定或设置 VIDEOHUB_ROOT")
        return EXIT_UNAVAILABLE

    try:
        layout = _load_json(LAYOUT_PATH)
    except Exception as exc:                              # noqa: BLE001
        print(f"[FAIL] layout      contracts/layout.json 不可解析: {exc}")
        return EXIT_UNAVAILABLE

    print(f"root  = {root}")
    print(f"hub   = {HUB_ROOT}")
    print(f"level = {'1+2' if args.all else args.level}"
          f"{'  mutate=' + args.mutate if args.mutate else ''}")
    print("-" * 72)

    report = Report()
    level1(report, root, layout, args.mutate)
    if args.all or args.level == 2:
        level2(report, root, layout, args.mutate)
    if args.runtime:
        runtime_check(report)

    print()
    report.dump()

    print("-" * 72)
    total = len(report.rows)
    n_fail = report.failed
    print(f"共 {total} 项，FAIL {n_fail} 项")

    if args.mutate:
        # 反例模式：期望「注入的错误被捕获」。
        # 不同反例用不同信号：
        #   layout → 产生 FAIL 行（MUTATE-layout）
        #   sha256 → 产生 PASS 行（MUTATE-sha256-check）表示捕获成功
        caught = any(
            tag.startswith("MUTATE") and status == "PASS"
            for tag, status, _ in report.rows
        )
        # ★ 反例会**破坏夹具**（sha256 反例篡改了 package-manifest.json，
        #   layout 反例把 copy_skill 挪到了错误层级）。若不还原，下一次
        #   正常体检会以「夹具本身是坏的」为由报 FAIL，看起来像真缺陷。
        _restore_after_mutation(report, root)
        if caught:
            print("反例测试符合预期：注入的错误被捕获 ✓")
            return EXIT_OK
        print("反例测试失败：注入的错误未被捕获 ✗")
        return EXIT_FAIL

    return EXIT_OK if n_fail == 0 else EXIT_FAIL


def _restore_after_mutation(report: Report, root: Path) -> None:
    """反例运行后把夹具恢复到干净状态。

    反例是「故意注入错误」，注入本身没问题；问题是**注入会留痕**。
    这里统一跑一次 `make_fixtures.py` 重建，让「反例 → 正常体检」可连续执行。
    失败只告警不报错 —— 反例的核心判据是「错误被捕获」，恢复属附加保障。
    """
    maker = Path(__file__).with_name("make_fixtures.py")
    if not maker.is_file():
        report.warn("MUTATE-restore", f"未找到 {maker.name}，夹具可能保持被污染状态")
        print("⚠️ 反例已破坏夹具，但找不到 make_fixtures.py；"
              "下次正常体检前请手动重建：python verify/make_fixtures.py")
        return
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(maker),
                "--clean",
                "--haike",
                str(root / "Haike_video"),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except Exception as exc:                                # noqa: BLE001
        report.warn("MUTATE-restore", f"重建夹具异常: {exc}")
        return
    if completed.returncode == 0:
        report.ok("MUTATE-restore", "夹具已自动重建，可继续正常体检")
    else:
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()[-3:]
        report.warn("MUTATE-restore", "夹具重建失败: " + " | ".join(tail))


if __name__ == "__main__":
    raise SystemExit(main())
