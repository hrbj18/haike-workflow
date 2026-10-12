# 契约 `daily-hot-candidate-pool-v2`（每日热点候选池）

> **方向**：copy_skill（**生产端**）→ Haike（**消费端**）
> **用途**：把「今天什么值得做」的结论固化成一份带校验的素材包，交给 Haike 的科技简报链路。
> **与 `episode-research-pack-v1` 的区别**：候选池是**每日批量**的选题候选；研究包是**单一选题**的深度证据。

---

## 1. 身份常量

### 生产端
`copy_skill/copy_skill-main/src/douyin_intelligence/daily_hot_candidate_pool.py`（932 行）

```python
schema = "daily-hot-candidate-pool-v2"
```

### 消费端
`Haike_video/backlot/copy_skill_hotspot_feed.py`（557 行）

```python
CONTRACT_VERSION = "2.0"                                       # :20
POOL_SCHEMA = "daily-hot-candidate-pool-v2"                    # :21
DEFAULT_COPY_SKILL_HOTSPOT_ROOT = Path(
    os.environ.get("COPY_SKILL_HOTSPOT_ROOT") or "integrations/copy_skill_hotspot"
)                                                              # :22-24
REQUIRED_PACKAGE_FILES = (
    "_READY.json",
    "package-manifest.json",
    "candidate-pool.json",
    "raw-videos.json",
    "run-report.json",
    "昨日抖音科技热点候选.md",
)                                                              # :26
```

> ⚠️ **两个版本号不是一回事**：`CONTRACT_VERSION = "2.0"` 是**契约版本**，`POOL_SCHEMA = "daily-hot-candidate-pool-v2"` 是**schema 名**。消费端会同时校验两者。

---

## 2. 目录布局

```
<copy_skill_output_root>/                默认 output/每日新闻素材（见 config）
└── <business_date>_每日素材/             例：2026-09-21_每日素材
    ├── current.json                     ★ 指针
    ├── latest.json
    └── packs/
        └── <run_id>/                    run_id = run-<date>-<12位hex>
            ├── _READY.json              ★ 发布信号
            ├── package-manifest.json
            ├── candidate-pool.json
            ├── raw-videos.json
            ├── run-report.json
            ├── 昨日抖音科技热点候选.md
            ├── official-discovery.json
            ├── 全网选题候选池.json
            ├── 全网选题候选池.md
            ├── 每日科技热点榜.md
            ├── 昨日热点图文简报.md
            ├── 昨日热点素材简报.md
            ├── daily-material-pack.json
            ├── consumer-dry-run.json
            └── manifest.json
```

> **注意日期目录后缀**：`daily_material_exchange.date_directory()` 产出的是
> `f"{business_date}_每日素材"`（**每日素材**），而研究包用的是 `_研究包`。**两者不同，别混。**

`run_id` 构造：`f"run-{target.replace('-','')}-{uuid.uuid4().hex[:12]}"`

`current.json` 中的 `pack_relative_path` 形如 `f"packs/{run_id}"`。

---

## 3. 消费端必需六件套（`REQUIRED_PACKAGE_FILES`）

| 文件 | 作用 |
|---|---|
| `_READY.json` | 发布信号 + 元数据总汇 |
| `package-manifest.json` | 完整性清单（`{path, bytes, sha256}`） |
| `candidate-pool.json` | 结构化的候选池机器数据 |
| `raw-videos.json` | 原始视频数据 |
| `run-report.json` | 本次运行报告（含 `run_id`） |
| `昨日抖音科技热点候选.md` | 人读的候选清单 |

**缺任何一个 → 消费端拒绝加载。**

---

## 4. `_READY.json` 结构

关键字段：

```json
{
  "contract_version": "2.0",
  "producer": "copy_skill",
  "business_date": "YYYY-MM-DD",
  "run_id": "run-YYYYMMDD-xxxxxxxxxxxx",
  "generated_at": "...",
  "status": "...",
  "human_brief": {...},
  "consumer_hot_list": {...},
  "major_event_brief": {...},
  "technical_brief": {...},
  "public_web_candidate_pool": {...},
  "public_web_candidate_machine": {...},
  "official_discovery": {...},
  "machine_contract": {...},
  "manifest": "...",
  "package_manifest_sha256": "...",
  "counts": {...},
  "missing": [...],
  "promotion": {...},
  "openmontage_modified": false
}
```

**两个字段值得单独注意**：
- `truth_status: "not_checked"` —— 生产端**明确声明未核真**。消费端不得当成已核实事实。
- `openmontage_modified: false` —— 生产端声明未改动消费端仓库。这是**单向隔离的自证**。

---

## 5. ⚠️ 三方 sha256 一致性（最硬的一条校验）

`package_manifest_sha256` 必须在**三处**一致：

1. `<date_root>/current.json` 的 `package_manifest_sha256`
2. `<pack_dir>/_READY.json` 的 `package_manifest_sha256`
3. 实际 `package-manifest.json` 文件的 sha256

消费端 `load_copy_skill_hotspot_feed()` 会亲自重算第 3 项并比对前两项。**任一不一致 → 拒绝加载。**

此外，`manifest` 中列出的**每一个文件**都会被逐条校验：`_safe_child` 防目录穿越 + `bytes` 比对 + `sha256` 比对。

---

## 6. 消费端校验链（逐步）

`Haike_video/backlot/copy_skill_hotspot_feed.py::load_copy_skill_hotspot_feed(root, business_date, *, snapshot_dir=None)`

```
 1. business_date 格式校验
 2. day_dir = root_path / f"{business_date}_每日素材"
 3. 读 day_dir/current.json
 4. _expect(current.contract_version, "2.0")
 5. _expect(current.business_date, <入参>)
 6. pack_dir = _safe_child(day_dir, current.pack_relative_path)
 7. ready_path = _safe_child(day_dir, current.ready_relative_path)
 8. 断言 ready_path.parent == pack_dir
 9. 六件套存在性检查
10. 读取 ready / pool / raw_videos / report / manifest
11. run_id = ready.run_id
12. contract_version + schema 一致性
13. 四个文档的 business_date 一致性
14. candidate-pool + run-report 的 run_id 一致性
15. manifest_sha256 = _sha256(manifest_path) 与 current / ready 三方比对
16. manifest_files 逐条 _safe_child + bytes + sha256 校验
```

**异常类型**：
```python
class CopySkillHotspotFeedError(RuntimeError):
    # code: "invalid" | "missing"
```

**安全加载入口**：`try_load_copy_skill_hotspot_feed(...)` —— 不抛异常版本，适合巡检。

---

## 7. 消费端函数清单

```
_read_json
_sha256
_safe_child
_expect
_atomic_json_if_changed
_coverage_details
_normalize_image
_normalize_candidate
_snapshot_feed
load_copy_skill_hotspot_feed      ← 主入口（严格）
try_load_copy_skill_hotspot_feed  ← 安全版（不抛）
feed_to_heat_signals              ← 转成 Haike 的热点信号
feed_to_discovery_candidates      ← 转成 Haike 的发现候选
```

---

## 8. Haike 侧配置

`Haike_video/config/daily_tech_brief.json`：

```json
{
  "copy_skill_hotspot_feed": {
    "enabled": false,
    "root": "integrations/copy_skill_hotspot"
  }
}
```

> ⚠️ **默认 `enabled: false`**。干净机器上必须显式打开并把 `root` 指向 copy_skill 的实际输出目录（相对 Haike 仓，或用环境变量 `COPY_SKILL_HOTSPOT_ROOT` 覆盖）。

---

## 9. 生产端阶段（`state.update(phase=...)`）

按执行顺序：

```
official_discovery
public_web_discovery
approved_accounts
supplemental_keywords
story_enrichment
consumer_hot_list
public_article_details
official_brief_localization
official_douyin_signals
top3_images
published / published_not_promoted     ← 终态
```

主入口：`run_daily_hot_candidate_pool(config, *, business_date=None, clock=time.monotonic)`

**离线修复路径**：`promote_existing_v2_pack(config, business_date, run_id, override=False)`
—— 当包已生成但指针没翻转时，用它补翻指针，**不需要重跑采集**。

---

## 10. 自检命令

```bash
# 生产端产出后，从 Haike 侧验证能否加载
cd Haike_video
python -c "
import sys; sys.path.insert(0, '.')
from backlot.copy_skill_hotspot_feed import try_load_copy_skill_hotspot_feed
r = try_load_copy_skill_hotspot_feed('integrations/copy_skill_hotspot', '2026-09-21')
print(r)
"

# 或跑第四仓的统一体检
python <videohub>/verify/check_all.py --level=2
```

---

## 11. 已知陷阱

1. **日期目录后缀是 `_每日素材`**，不是 `_研究包`。两者在同一天并存，容易搞混。
2. **`current.json` 的 `pack_relative_path` 是相对 `<date_root>` 的**（`packs/<run_id>`），不是相对仓库根。
3. **`enabled: false` 默认关闭** —— 忘记打开会表现为「明明有数据但读不到」，而不是报错。
4. **`_safe_child` 会拒绝越界路径** —— 如果 `pack_relative_path` 里出现 `..`，会抛 `invalid` 而非 `missing`。
5. **`truth_status: "not_checked"`** —— 候选池的数据**未经核真**，Haike 侧如果拿它当已核实事实使用，责任在消费端。
