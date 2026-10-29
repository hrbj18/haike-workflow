#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""构造 L2 契约连通所需的假数据。

为什么用脚本而不是手写 JSON：
  研究包有 7 个语义文件 + manifest 双向覆盖 + content_sha256 冻结算法，
  手写极易出错。本脚本**直接 import 消费端模块**，用它的 content_sha256()
  来算哈希，因此产出的包天然满足消费端校验 —— 这正是「假数据能验证契约」
  的技术基础。

用法：
    python verify/make_fixtures.py            # 生成两个假包
    python verify/make_fixtures.py --clean    # 先清空再生成
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
HUB_ROOT = HERE.parents[1]
FIXTURES = HUB_ROOT / "fixtures"

BUSINESS_DATE = "2026-09-21"
EPISODE_ID = f"{BUSINESS_DATE}-最小假包"
REVISION = 1
PACK_ID = f"{EPISODE_ID}-r{REVISION}"
RUN_ID = "run-20260921-fixture0001"


# ------------------------------------------------------------------ 工具


def dump(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_consumer_module(haike: Path):
    """从 Haike 侧 import 消费端模块（拿它的 content_sha256 算法）。"""
    if str(haike) not in sys.path:
        sys.path.insert(0, str(haike))
    from backlot import copy_skill_research_pack as mod  # type: ignore

    return mod


# ------------------------------------------------------------------ 候选池


def build_candidate_pool() -> None:
    """构造 mini-candidate-pool。"""
    day_dir = FIXTURES / "mini-candidate-pool" / f"{BUSINESS_DATE}_每日素材"
    pack_dir = day_dir / "packs" / RUN_ID
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    pack_dir.mkdir(parents=True, exist_ok=True)

    # ---- 六件套中的 5 个 JSON
    ready = {
        "contract_version": "2.0",
        "producer": "copy_skill",
        "business_date": BUSINESS_DATE,
        "run_id": RUN_ID,
        "generated_at": f"{BUSINESS_DATE}T09:00:00+08:00",
        "status": "ready",
        "counts": {
            "candidates": 1,
            "target_day_videos": 1,
            "raw_records": 1,
            "images": 0,
        },
        "missing": [],
        # 稍后回填
        "package_manifest_sha256": "",
        "manifest": "package-manifest.json",
        "openmontage_modified": False,
    }
    dump(pack_dir / "_READY.json", ready)

    pool = {
        "contract_version": "2.0",
        "schema": "daily-hot-candidate-pool-v2",
        "business_date": BUSINESS_DATE,
        "run_id": RUN_ID,
        "status": "ready",
        "generated_at": f"{BUSINESS_DATE}T09:00:00+08:00",
        "truth_status": "not_checked",
        "disclaimer": "本包为第四仓契约验证用假数据，不来自真实采集。",
        "candidates": [
            {
                "event_id": "evt-fixture-0001",
                "story_id": "evt-fixture-0001",
                "rank": 1,
                "title": "假数据：某技术发布",
                "aliases": ["假数据别名"],
                "business_date": BUSINESS_DATE,
                "published_at_min": f"{BUSINESS_DATE}T00:00:00+08:00",
                "published_at_max": f"{BUSINESS_DATE}T12:00:00+08:00",
                "heat_score": 42.0,
                "score_components": {"mock": 1},
                "contributing_videos": [
                    {
                        "video_id": "vid-fixture-0001",
                        "title": "假数据视频",
                        "author": "假作者",
                        "account_id": "acc-fixture",
                        "share_url": "https://example.invalid/v/1",
                        "published_at": f"{BUSINESS_DATE}T08:00:00+08:00",
                        "interactions": {"like": 1},
                        "source_lanes": ["fixture"],
                        "matched_keywords": ["假数据"],
                    }
                ],
                "source_lanes": ["fixture"],
                "matched_keywords": ["假数据"],
                "video_count": 1,
                "account_count": 1,
                "aggregate_interactions": {"like": 1},
                "truth_status": "not_checked",
                "evidence_status": "not_checked",
                "disclaimer": "fixture",
                "image_status": {"attempted": False},
                "images": [],
            }
        ],
    }
    dump(pack_dir / "candidate-pool.json", pool)

    raw_videos = {
        "contract_version": "2.0",
        "business_date": BUSINESS_DATE,
        "run_id": RUN_ID,
        "videos": [
            {
                "video_id": "vid-fixture-0001",
                "title": "假数据视频",
                "author": "假作者",
                "account_id": "acc-fixture",
                "published_at": f"{BUSINESS_DATE}T08:00:00+08:00",
                "share_url": "https://example.invalid/v/1",
                "interactions": {"like": 1},
            }
        ],
        "excluded": [],
    }
    dump(pack_dir / "raw-videos.json", raw_videos)

    report = {
        "contract_version": "2.0",
        "business_date": BUSINESS_DATE,
        "run_id": RUN_ID,
        "status": "ready",
        "phases": ["official_discovery", "published"],
        "account_attempts": [],
        "errors": [],
    }
    dump(pack_dir / "run-report.json", report)

    # ---- 人读 md
    (pack_dir / "昨日抖音科技热点候选.md").write_text(
        "# 假数据候选（契约验证用）\n\n"
        "本文件由 `verify/make_fixtures.py` 生成，**不是真实采集结果**。\n\n"
        "1. 假数据：某技术发布\n",
        encoding="utf-8",
    )

    # ---- package-manifest.json（双向覆盖）
    excluded = {"package-manifest.json", "_READY.json"}
    files = []
    for child in sorted(pack_dir.rglob("*")):
        if not child.is_file():
            continue
        rel = child.relative_to(pack_dir).as_posix()
        if rel in excluded:
            continue
        files.append(
            {
                "path": rel,
                "bytes": child.stat().st_size,
                "sha256": sha256_file(child),
            }
        )
    manifest = {
        "contract_version": "2.0",
        "schema": "daily-hot-candidate-pool-package-manifest-v2",
        "business_date": BUSINESS_DATE,
        "run_id": RUN_ID,
        "files": files,
    }
    dump(pack_dir / "package-manifest.json", manifest)

    # ---- 回填三方一致的 sha
    msha = sha256_file(pack_dir / "package-manifest.json")
    ready["package_manifest_sha256"] = msha
    dump(pack_dir / "_READY.json", ready)

    day_current = {
        "contract_version": "2.0",
        "business_date": BUSINESS_DATE,
        "status": "ready",
        "pack_relative_path": f"packs/{RUN_ID}",
        "ready_relative_path": f"packs/{RUN_ID}/_READY.json",
        "package_manifest_sha256": msha,
        "updated_at": f"{BUSINESS_DATE}T09:00:00+08:00",
        "promotion": "fixture",
    }
    dump(day_dir / "current.json", day_current)
    dump(day_dir / "latest.json", day_current)

    print(f"[fixture] candidate-pool  -> {pack_dir}")
    print(f"          manifest_sha256  = {msha[:16]}...")


# ------------------------------------------------------------------ 研究包


def build_research_pack(haike: Path) -> None:
    """构造 mini-research-pack。

    关键：content_sha256 用**消费端自己的算法**算，保证逐字节一致。
    """
    mod = load_consumer_module(haike)

    ep_dir = FIXTURES / "mini-research-pack" / f"{BUSINESS_DATE}_研究包" / EPISODE_ID
    pack_dir = ep_dir / "packs" / PACK_ID
    if ep_dir.exists():
        shutil.rmtree(ep_dir)
    pack_dir.mkdir(parents=True, exist_ok=True)

    base = {
        "contract": "episode-research-pack-v1",
        "episode_id": EPISODE_ID,
        "business_date": BUSINESS_DATE,
    }

    # ---- episode.json
    episode = {
        **base,
        "production_mode": "single_topic_material_replication",
        "disposition": "ready",
        "theme": "假数据主题",
        "origin_ref": {
            "origin_contract": "material_replication_delivery",
            "manifest_sha256": "0" * 64,   # fixture 占位，仅需非空
            "authority": "material_only",
            "discovery_only": False,
            "items": [],
            "assets": [],
        },
    }
    dump(pack_dir / "episode.json", episode)

    # ---- sources.json
    #   约束：authority ∈ SOURCE_AUTHORITIES
    #         verification_state ∈ VERIFICATION_STATES
    #         heat_only 必须 bool
    #         freshness.observed_at 必填；freshness.policy ∈ FRESHNESS_POLICIES
    #         freshness.status_at_publish ∈ FRESHNESS_STATUSES
    sources = {
        **base,
        "sources": [
            {
                "source_id": "src-fixture-0001",
                "url": "https://example.invalid/a/1",
                "title": "假数据官方来源",
                "publisher": "fixture-publisher-1",
                "authority": "official",
                "verification_state": "verified",
                "heat_only": False,
                "freshness": {
                    "observed_at": f"{BUSINESS_DATE}T08:00:00+08:00",
                    "policy": "evergreen",
                    "status_at_publish": "fresh",
                },
            }
        ],
    }
    dump(pack_dir / "sources.json", sources)

    # ---- claims.json
    #   约束：evidence_status ∈ EVIDENCE_STATUSES
    #         wording_policy ∈ WORDING_POLICIES
    #         freshness_requirement ∈ FRESHNESS_REQUIREMENTS
    #         fact_sources_present == 复算的已核验非热度源数
    #         fact_sources_min == CONFIRMED_FACT_MIN[evidence_status]
    #         claims_to_verify / do_not_claim / material_refs 均需为 list
    #         material_refs ↔ segment.claim_ids 双向一致
    claims = {
        **base,
        "claims": [
            {
                "claim_id": "c1",
                "text": "假数据论据一",
                "source_ids": ["src-fixture-0001"],
                "evidence_status": "confirmed_official",
                "wording_policy": "assert",
                "freshness_requirement": "evergreen",
                "fact_sources_present": 1,
                "fact_sources_min": 1,
                "claims_to_verify": [],
                "do_not_claim": [],
                "material_refs": ["m1"],
            },
            {
                "claim_id": "c2",
                "text": "假数据论据二",
                "source_ids": ["src-fixture-0001"],
                "evidence_status": "confirmed_official",
                "wording_policy": "attribute",
                "freshness_requirement": "evergreen",
                "fact_sources_present": 1,
                "fact_sources_min": 1,
                "claims_to_verify": [],
                "do_not_claim": [],
                "material_refs": ["m1"],
            },
        ],
    }
    dump(pack_dir / "claims.json", claims)

    # ---- audience.json
    audience = {
        **base,
        "audience": {"primary": "假数据受众", "segments": []},
    }
    dump(pack_dir / "audience.json", audience)

    # ---- topics.json（★ 含非空 argument_graph.edges，专门覆盖边键）
    topics = {
        **base,
        "keyword_graph": {
            "seed": ["假数据"],
            "expanded": ["假数据扩展"],
            "subject_terms": ["假数据主体"],
            "event_terms": ["假数据事件"],
            "keywords_requested": ["假数据"],
            "keywords_used": ["假数据"],
            "keywords_truncated": [],
        },
        "topic_candidates": [
            {"topic_id": "t1", "title": "假数据选题", "score": 1.0}
        ],
        "selected_topic": {"topic_id": "t1", "title": "假数据选题"},
        "argument_graph": {
            "nodes": [
                {
                    "claim_id": "c1",
                    "dim": "event_core",
                    "claim": "假数据论据一",
                    "source_candidate_ids": ["evt-fixture-0001"],
                },
                {
                    "claim_id": "c2",
                    "dim": "evidence_detail",
                    "claim": "假数据论据二",
                    "source_candidate_ids": ["evt-fixture-0001"],
                },
            ],
            "edges": [
                {"from": "c1", "to": "c2", "relation": "supports"}
            ],
        },
    }
    dump(pack_dir / "topics.json", topics)

    # ---- materials.json
    #   约束：permitted_use == "b_roll_only"
    #         freshness_status ∈ FRESHNESS_STATUSES（可为 None）
    #         duration_ms 为整数且 >= 0
    #         segment: 0 <= start_ms < end_ms <= duration_ms
    #                  purpose ∈ SEGMENT_PURPOSES
    #                  transcript_excerpt 必须是 str
    #                  frame_evidence_ids 必须是 list
    materials = {
        **base,
        "materials": [
            {
                "material_id": "m1",
                "permitted_use": "b_roll_only",
                "freshness_status": "fresh",
                "duration_ms": 5000,
                "segments": [
                    {
                        "segment_id": "s1",
                        "start_ms": 0,
                        "end_ms": 5000,
                        "purpose": "visual_support",
                        "transcript_excerpt": "假数据转录片段",
                        "frame_evidence_ids": [],
                        "claim_ids": ["c1", "c2"],
                    }
                ],
            }
        ],
    }
    dump(pack_dir / "materials.json", materials)

    # ---- rights.json
    #   约束：asset_id 必填；asset_type ∈ ASSET_TYPES；origin ∈ RIGHTS_ORIGINS
    #         rights_status ∈ RIGHTS_STATUSES
    #         redistribution_allowed / render_eligible 必须是 bool
    #         prohibited 不得允许再分发/渲染；platform_content 不得 render_eligible
    #         每个 material 必须有对应 rights 记录
    rights = {
        **base,
        "rights": [
            {
                "rights_id": "r1",
                "asset_id": "asset-fixture-0001",
                "asset_type": "video",
                "origin": "producer_owned",
                "rights_status": "cleared",
                "redistribution_allowed": True,
                "render_eligible": True,
                "material_id": "m1",
            }
        ],
    }
    dump(pack_dir / "rights.json", rights)

    # ---- 人读 md
    (pack_dir / "每期研究证据包.md").write_text(
        "# 假数据研究包（契约验证用）\n\n"
        "本文件由 `verify/make_fixtures.py` 生成，**不是真实研究结果**。\n",
        encoding="utf-8",
    )

    # ---- revision.json
    dump(
        pack_dir / "revision.json",
        {
            **base,
            "revision": REVISION,
            "pack_id": PACK_ID,
            "disposition": "ready",
            "content_sha256": "",  # 回填
        },
    )

    # ---- run-report.json
    dump(
        pack_dir / "run-report.json",
        {**base, "status": "ready", "phases": ["fixture"]},
    )

    # ---- 用消费端算法算 content_sha256（关键！）
    payloads = {}
    for name in mod.SEMANTIC_FILES:
        payloads[name] = json.loads((pack_dir / name).read_text(encoding="utf-8"))
    csha = mod.content_sha256(payloads)

    rev = json.loads((pack_dir / "revision.json").read_text(encoding="utf-8"))
    rev["content_sha256"] = csha
    dump(pack_dir / "revision.json", rev)

    # ---- package-manifest.json（双向覆盖）
    excluded = set(mod.MANIFEST_EXCLUSIONS)
    files = []
    for child in sorted(pack_dir.rglob("*")):
        if not child.is_file():
            continue
        rel = child.relative_to(pack_dir).as_posix()
        if rel in excluded:
            continue
        files.append(
            {"path": rel, "bytes": child.stat().st_size, "sha256": sha256_file(child)}
        )
    manifest = {
        "schema": mod.MANIFEST_SCHEMA,
        "contract": mod.CONTRACT,
        "exclusions": list(mod.MANIFEST_EXCLUSIONS),
        "episode_id": EPISODE_ID,
        "business_date": BUSINESS_DATE,
        "revision": REVISION,
        "pack_id": PACK_ID,
        "content_sha256": csha,
        "files": files,
    }
    dump(pack_dir / "package-manifest.json", manifest)

    msha = sha256_file(pack_dir / "package-manifest.json")

    # ---- _READY.json（必须最后写，且不在 manifest 里）
    dump(
        pack_dir / "_READY.json",
        {
            "contract": mod.CONTRACT,
            "episode_id": EPISODE_ID,
            "business_date": BUSINESS_DATE,
            "revision": REVISION,
            "pack_id": PACK_ID,
            "content_sha256": csha,
            "manifest_sha256": msha,
            "file_count": len(files),
            "supersedes": None,
            "ready_at": f"{BUSINESS_DATE}T09:00:00+08:00",
            "disposition": "ready",
        },
    )

    # ---- current.json（唯一提交点）
    dump(
        ep_dir / "current.json",
        {
            "contract": mod.CONTRACT,
            "episode_id": EPISODE_ID,
            "business_date": BUSINESS_DATE,
            "revision": REVISION,
            "pack_id": PACK_ID,
            "content_sha256": csha,
            "manifest_sha256": msha,
            "disposition": "ready",
            "pack_path": f"packs/{PACK_ID}",
            "ready_path": f"packs/{PACK_ID}/_READY.json",
            "updated_at": f"{BUSINESS_DATE}T09:00:00+08:00",
        },
    )

    print(f"[fixture] research-pack   -> {pack_dir}")
    print(f"          content_sha256   = {csha[:16]}...")
    print(f"          manifest_sha256  = {msha[:16]}...")


# ------------------------------------------------------------------ main


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="make_fixtures.py")
    parser.add_argument("--clean", action="store_true", help="先清空 fixtures/")
    parser.add_argument(
        "--haike",
        type=Path,
        default=None,
        help="Haike 仓库路径（默认自动推断为第四仓的兄弟目录）",
    )
    args = parser.parse_args(argv)

    haike = args.haike or (HUB_ROOT.parent / "Haike_video")
    if not (haike / "backlot" / "copy_skill_research_pack.py").is_file():
        print(f"[FAIL] 找不到 Haike 消费端模块：{haike}")
        return 2

    if args.clean and FIXTURES.exists():
        shutil.rmtree(FIXTURES)
        print(f"[clean] 已清空 {FIXTURES}")

    build_candidate_pool()
    build_research_pack(haike)

    print()
    print("假数据生成完毕。下一步：")
    print("  python verify/check_all.py --all")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
