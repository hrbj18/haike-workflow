# 契约 `episode-research-pack-v1`（每期研究包）

> **方向**：copy_skill（**生产端**）→ Haike（**消费端**）
> **用途**：把「选题研究」的结论固化成一份带完整性校验的证据包，交给 Haike 做素材复刻。
> **性质**：**单向**。Haike 从不写回研究包。

---

## 1. 身份常量（生产端）

来源：`copy_skill/copy_skill-main/src/douyin_intelligence/episode_research_pack.py`

```python
CONTRACT = "episode-research-pack-v1"                          # :70
MANIFEST_SCHEMA = "episode-research-pack-manifest-v1"          # :71
PRODUCTION_MODE = "single_topic_material_replication"          # :72
DEFAULT_OUTPUT_ROOT = "output/每期研究包"                       # :74
EPISODE_SUFFIX = "_研究包"                                      # :75
STAGING_DIRNAME = ".staging"                                   # :76
PACKS_DIRNAME = "packs"                                        # :77
NOTIFY_DIRNAME = "notify"                                      # :78
CURRENT_NAME = "current.json"                                  # :79
LATEST_NAME = "latest.json"                                    # :80
DELIVERY_MANIFEST_NAME = "清单.json"                            # :81
REVISION_NAME = "revision.json"                                # :94
RUN_REPORT_NAME = "run-report.json"                            # :95
README_NAME = "每期研究证据包.md"                                 # :96
MANIFEST_NAME = "package-manifest.json"                        # :97
READY_NAME = "_READY.json"                                     # :98
```

**消费端镜像**：`Haike_video/backlot/copy_skill_research_pack.py:41-44` 逐字声明同样的 `CONTRACT` / `MANIFEST_SCHEMA` / `PRODUCTION_MODE`，并额外提供 `CONTRACT_KIND = CONTRACT`（`:42`，兼容别名）。

---

## 2. 目录布局

```
<output_root>/                          默认 output/每期研究包
└── <business_date><EPISODE_SUFFIX>/    例：2026-09-21_研究包
    ├── current.json                    ★ 唯一提交点（指针）
    ├── .staging/<...>                  构建中的临时区
    └── packs/
        └── <pack_id>/                  一个具体版本
            ├── episode.json            ┐
            ├── sources.json            │
            ├── claims.json             │ SEMANTIC_FILES
            ├── audience.json           │ （顺序冻结）
            ├── topics.json             │
            ├── materials.json          │
            ├── rights.json             ┘
            ├── revision.json
            ├── run-report.json
            ├── 每期研究证据包.md
            ├── package-manifest.json
            └── _READY.json
```

路径构造（生产端 `episode_root_for()`）：
```python
root = project_path(config, str(output_root or DEFAULT_OUTPUT_ROOT))
return root / f"{business_date}{EPISODE_SUFFIX}" / episode_id
```

`episode_id` 默认构造（`default_episode_id()`）：
```python
f"{date}-{slug}"    # slug = sanitize_theme(theme, max_length=40) or "未命名主题"
```

---

## 3. 文件清单

### 3.1 `SEMANTIC_FILES`（顺序冻结）

```python
SEMANTIC_FILES = (
    "episode.json",
    "sources.json",
    "claims.json",
    "audience.json",
    "topics.json",
    "materials.json",
    "rights.json",
)
```

> ⚠️ **顺序是冻结的**，因为它决定了 `content_sha256` 的计算顺序。改动顺序 = 破坏契约。

### 3.2 `REQUIRED_PACK_FILES`（全部必须存在）

```python
REQUIRED_PACK_FILES = (
    *SEMANTIC_FILES,          # 7 个
    REVISION_NAME,            # revision.json
    RUN_REPORT_NAME,          # run-report.json
    README_NAME,              # 每期研究证据包.md
    MANIFEST_NAME,            # package-manifest.json
    READY_NAME,               # _READY.json
)
```

### 3.3 `MANIFEST_EXCLUSIONS`（不进 manifest 的两个）

```python
MANIFEST_EXCLUSIONS = (MANIFEST_NAME, READY_NAME)
```
理由：manifest 不能包含自己；`_READY.json` 是发布信号，必须在 manifest 之后写。

---

## 4. 完整性校验

### 4.1 `content_sha256`

对 7 个 `SEMANTIC_FILES` 按**冻结顺序**计算。生产端有冻结测试向量：

```
FROZEN_CONTENT_SHA256 = "e5bc839ff60a91f29474c9bec50c8afca41fdaf367dc5e6978eae620b1cbaab8"
# episode_research_pack.py:285
```

对应测试向量为 7 个最小 payload：
```json
{"a":1} / {"b":[1,2]} / {"c":"文"} / {"d":null} / {"e":true} / {"f":0} / {"g":{"h":"i"}}
```

**消费端也有同一常量**：`Haike_video/tests/backlot/test_copy_skill_research_pack.py:1290`
```python
PRODUCER_FROZEN_CONTENT_SHA256 = "e5bc839ff60a91f29474c9bec50c8afca41fdaf367dc5e6978eae620b1cbaab8"
```
并有断言 `test_content_sha256_pins_producer_frozen_vector()` 与 `test_producer_frozen_constant_still_matches_algorithm()`。
⇒ **两边不一致就是契约破裂**，这是最硬的一条判据。

### 4.2 `current.json` 指针结构

```json
{
  "contract": "episode-research-pack-v1",
  "episode_id": "...",
  "business_date": "YYYY-MM-DD",
  "pack_id": "...",
  "revision": N,
  "content_sha256": "...",
  "manifest_sha256": "...",
  "disposition": "...",
  "pack_path": "packs/<pack_id>",
  "ready_path": "...",
  "updated_at": "..."
}
```

### 4.3 发布提交点

`flip_episode_current_pointer()` —— **`current.json` 是唯一的提交点**。在它被翻转之前，整个包对外不存在。

`_best_effort_latest_notify()` 额外写 `latest.json` + `notify/<episode_id>.json`，**best-effort，失败不 raise**（即：通知丢失不影响包的有效性）。

---

## 5. 生产端 API

| 函数 | 用途 |
|---|---|
| `publish_episode_research_pack()` | 发布入口 |
| `validate_episode_pack_stage(stage)` | 校验，返回 `{"status": "pass"/"fail", ...}`，**fail 必须阻断发布** |
| `inspect_episode_pack()` | 只读检查入口 |
| `episode_root_for()` | 路径构造 |
| `default_episode_id()` | ID 生成 |
| `flip_episode_current_pointer()` | 翻转提交点 |

`publish_episode_research_pack()` 返回值：
```
status          "noop" | "reused" | "published"
episode_id
pack_id
revision
pack_path
content_sha256
manifest_sha256
disposition
validation
advisories
warnings
```

---

## 6. 消费端行为（Haike）

`Haike_video/backlot/copy_skill_research_pack.py`

### 6.1 `load_research_pack(source, *, now=None, max_attempts=DEFAULT_MAX_READ_ATTEMPTS)`

**严格只读**，读序：
```
current-A → READY → manifest → 全部文件 → current-B
```
**两次 `current.json` 指纹不一致 ⇒ 丢弃重试**；超过 `max_attempts` 抛 `ResearchPackUnstableError`。

这个设计防的是「读到一半时生产端翻转了指针」的撕裂读。**⇒ 消费端不会读到半成品包。**

### 6.2 `_resolve_episode_from_source(source)`

接受两种输入：
- episode 目录（`<date>_研究包/<episode_id>`）
- `current.json` 路径

### 6.3 账本（intake）

`Haike_video/backlot/research_pack_intake.py`

```python
LEDGER_SCHEMA = "episode-research-pack-intake-v1"              # :38
LEDGER_VERSION = 1                                             # :39
DEFAULT_LEDGER_PATH = REPO_ROOT/".backlot"/"research_pack_intake.json"      # :40
DEFAULT_SNAPSHOT_ROOT = REPO_ROOT/".backlot"/"research-pack-snapshots"      # :41
EPISODE_SUFFIX = "_研究包"                                      # :42
STATES = ("discovered","validated","admitted","failed","rejected","stale")   # :45
DECISIONS = (
    "ingest","noop","stale_revision","revision_collision",
    "revision_gap","invalid_contract",
)                                                              # :48
_MAX_EVENTS = 200                                              # :57
```

幂等键：
```python
idempotency_key(episode_id, content_sha256) = f"{CONTRACT_KIND}:{episode_id}:{content_sha256}"
```
⇒ **同一 episode 的同一内容版本只会被收编一次。**

---

## 7. 编辑决策 CLI

`Haike_video/scripts/remake_editorial_cli.py`

```python
prog = "remake_editorial_cli.py"
DEFAULT_SPEC_DIR = REPO / ".backlot" / "remake-specs"
EXIT_OK = 0
EXIT_INPUT = 2
EXIT_BLOCKED = 3
EXIT_NOT_SCRIPTED = 4
OFFLINE_PROBE_PROVIDER = "offline-estimate"
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--episode-root` | **必填** | 研究包 episode 目录 |
| `--out-dir` | — | 输出目录 |
| `--ledger-path` | intake 默认 | 账本路径 |
| `--snapshot-root` | intake 默认 | 快照根 |
| `--project-id` | — | 项目 ID |
| `--title` | — | 标题 |
| `--brief` | — | 简述 |
| `--style-playbook` | `clean-professional` | 风格手册 |
| `--material-root` | — | 素材根 |
| `--fps` | `30` | 帧率 |
| `--aspect` | `portrait` | 画幅 |
| `--min-supported-claims` | — | 最少支撑论据数 |
| `--copywriter` | **缺省 = 不注入 ⇒ 退出码 4** | 文案注入器 |
| `--probe-seconds` | `4.0` | 探测秒数 |
| `--allow-partial` | — | 允许部分 |
| `--now` | — | 注入当前时间（测试用） |
| `--no-write` | — | 不落盘 |
| `--json` | — | JSON 输出 |

**退出码语义**：`0` 成功 / `2` 输入错误 / `3` 被阻断 / `4` 未配置 copywriter（**fail-closed**）。

---

## 8. 消费端的红线

> **消费端校验不得严于冻结合同。**

出处：`Haike_video/docs/handoff/DECISIONS.md:47-51`

**含义**：Haike 作为消费端**不能**要求比契约更多的字段或更严的约束。否则生产端合法产出会被消费端拒绝，链路断裂而双方各自「测试通过」。

另有一条：**研究包不进生产队列**（同处）。即研究包是「编辑决策的输入」，不是「渲染任务」。

---

## 9. 自检命令

```bash
# 1) 冻结常量两边一致
grep -n "e5bc839ff60a91f29474c9bec50c8afca41fdaf367dc5e6978eae620b1cbaab8" \
  copy_skill/copy_skill-main/src/douyin_intelligence/episode_research_pack.py \
  Haike_video/tests/backlot/test_copy_skill_research_pack.py
# 期望：两处都命中

# 2) 跑跨仓互操作用例（注意必须带这两个参数）
cd Haike_video
python -m pytest tests/backlot/test_copy_skill_research_pack.py \
  --import-mode=importlib --basetemp=.p -v
# 期望：跨仓用例不 skip（若 skip，检查 layout.json 的 LAYOUT-1）
```

---

## 10. 已知陷阱

1. **合同文档路径**：`test_copy_skill_research_pack.py:1385-1396` 直接读
   `Path(REPO_ROOT).parent/"copy_skill"/"copy_skill-main"/"docs"/"tasks"/"2026-09-16-episode-research-pack-v1.md"`
   缺失时 `pytest.skip("CopySkill 冻结合同文档不在本机，跳过合同一致性断言")`。
2. **边键曾长期未被覆盖**：`test_end_to_end_with_non_empty_argument_graph()`（`:1427-1440`）的 docstring 记载：既有两个跨仓用例的 `argument_graph.edges` **恒为空**，所以从没有用例真正走过边键，改名跑偏正是钻了这个空子。
   ⇒ 断言必须是 `"edges[{from,to,relation}]" in text` 且 `"from_claim_id" not in text`。
3. **`_READY.json` 必须最后写**，且在 `MANIFEST_EXCLUSIONS` 里。
