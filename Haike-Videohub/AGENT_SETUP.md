# AGENT_SETUP.md

> **本文件是 Agent 部署本工作流的唯一入口。**
> **格式对标 `Haike_video/AGENT_GUIDE.md`（8 节结构）。**
> 人请读 [`README.md`](README.md)。

---

## 1 Context routing

初始化前向用户说明：本地 Qwen3-TTS 音频服务为可选功能，需另下载数 GB 依赖/模型；百炼云端克隆不依赖本地服务。询问是否安装，只有明确选择安装才启用；未答复不得下载。用户已有“跳过本地服务”的选择时沿用，不重复询问。便携包与 `Haike_video/scripts/setup.ps1` 使用 `-LocalTts skip` / `-LocalTts install` 明确传递选择；直接交互运行默认询问、回车跳过。此选项不卸载已安装的服务。

**读序（不可跳步）**：

```
1. 本文件（AGENT_SETUP.md）
2. contracts/layout.json          ← 三仓布局硬约束，先看这个
3. deps/A|B|C|D-*.md              ← 依赖四分类，知道什么要下载什么不要复制
4. steps/README.md                ← 步骤总览与可跳过点
5. steps/01 → steps/08            ← 逐步执行，每步有验证命令
6. docs/pending-manual-checks.md  ← 最后必须读，知道什么停下来找人类
```

**专项按需读（至多一个）**：
- 分发视频模板标准依赖后，在本仓根运行 `python verify/check_template_standards.py --workspace`，按输出核对规范文件与工作区路由；静态检查不代表媒体或生产验收通过。
- 要接发布 → `contracts/publish-v1.md`
- 要执行日常跨仓操作 → `agent-runbooks/README.md`（先核对实时状态与用户授权）
- 要读研究包 → `contracts/research-pack-v1.md`
- 要读候选池 → `contracts/candidate-pool-v2.md`
- 要配密钥 → `keys/README.md` + `keys/capability-matrix.json`
- 出故障 → `docs/pitfalls.md`

---

## 2 Request routing

| 用户说 | 你做 |
|---|---|
| 「部署这套工作流」 | 走 `steps/01` → `steps/08` |
| 「体检一下」 | `python verify/check_all.py --all` |
| 「为什么跑不起来」 | 先跑 `verify/check_all.py --all`，再查 `docs/pitfalls.md` |
| 「怎么发布」 | 先读 `contracts/publish-v1.md`，再按 `agent-runbooks/短视频三平台发布.md` 核对实时状态；创建任务可能立即执行 |
| 「怎么加素材」 | `deps/B-external.md` + `steps/06-mediacrawler.md` |
| 「做一条模板图文视频」 | 直接读 `agent-runbooks/模板图文视频.md`；同名呼叫优先，不得改走窗口复刻、素材复刻或通用 Codex 原生制片；核对身份闸门、登录态、采集源、主题词表与文案条目后再跑 |
| 「哪些要我自己做」 | `docs/pending-manual-checks.md` |

---

## 3 Video-production contract

**三个仓库的角色**：

```
copy_skill  ──[研究包 / 候选池]──▶  Haike_video  ──[成片]──▶  creatorhub
  采集与情报                        生产与渲染                  发布
```

### 3.1 两条跨仓数据流

**`episode-research-pack-v1`**（研究包）
```
生产端  copy_skill/src/douyin_intelligence/episode_research_pack.py
消费端  Haike_video/backlot/copy_skill_research_pack.py
提交点  current.json（唯一翻转点）
硬约束  冻结 content_sha256 = e5bc839f...（两边必须一致）
细节    contracts/research-pack-v1.md
```

**`daily-hot-candidate-pool-v2`**（候选池）
```
生产端  copy_skill/src/douyin_intelligence/daily_hot_candidate_pool.py
消费端  Haike_video/backlot/copy_skill_hotspot_feed.py
必需六件套  _READY.json / package-manifest.json / candidate-pool.json
            raw-videos.json / run-report.json / 昨日抖音科技热点候选.md
三方一致    package_manifest_sha256 在 current / _READY / 实际文件 三处一致
细节        contracts/candidate-pool-v2.md
```

### 3.2 生产门（必须遵守）

```
1. 自动流程只产出待审核预览，不自动发布
   （DECISIONS.md:10）
2. 预览与成片必须共用同一条时间线
3. 付费调用前先声明 provider / model / 成本
   （AGENT_GUIDE.md 第 4 节）
4. 正式视频绝不自动发布；自动化最远停在 review-ready 预览
   （AGENT_GUIDE.md:51）
5. ⚠️ POST /api/publish 创建即执行（实测）—— 不调 run-now 不足以保证安全
   见 contracts/publish-v1.md §0.2
```

### 3.3 跨仓消费的红线

> **消费端校验不得严于冻结合同。**（`Haike_video/docs/handoff/DECISIONS.md:47-51`）

⇒ Haike 不能要求比契约更多的字段，否则生产端合法产出会被拒绝。

---

## 4 Providers-cost-failures

### 4.1 成本层级

| 层级 | 付费? | 说明 |
|---|---|---|
| B站采集 | **免费** | 纯标准库免登录 |
| Remotion 渲染 | **免费** | 完全本地 |
| 本地成片 | **免费** | static-ffmpeg |
| 云端 TTS | 按字符 | 要配音才需要 |
| ASR | 按时长 | 要加字幕才需要 |
| 视频生成 | **按秒（最贵）** | 进阶，可选 |

**⇒ 付费前必须声明 provider / model / 成本。**

### 4.2 零付费路径

```
B站源下载 → Remotion 渲染 → 不加 AI 配音 → 成片
```

**⇒ 完整可用，不产生任何付费调用。**

### 4.3 常见失败

| 症状 | 真因 | 处置 |
|---|---|---|
| 采集 `failed` 但无原因 | stderr 被 DEVNULL 吞掉 | 跑 doctor（`steps/04` §4.3） |
| 跨仓测试 `SKIPPED` | 布局路径写错 | 检查 `LAYOUT-1` |
| 有数据但读不到 | 候选池开关默认 false | 改 `daily_tech_brief.json` |
| `preview_render=generating` 卡住 | 僵尸状态 | 见 `docs/pitfalls.md` #7 |
| Chrome 找不到 | 路径不对 | **会显式报错**（`collector.py:184`） |

---

## 5 Quality gates

### 5.1 部署完成的唯一判据

```bash
python verify/check_all.py --all
```

**⇒ 38 项，0 FAIL**（未启用抖音采集时为 36 项 + 2 条 MediaCrawler WARN；且 Haike_video 需 ≥ `395890c`，否则 `adapter.*` 4 项塌为 1 条 WARN、总数 33）。WARN 可接受，FAIL 不可接受。

### 5.2 反例自测（必须跑，否则无法证明校验有效）

```bash
python verify/check_all.py --level=1 --mutate=layout
python verify/check_all.py --all --mutate=sha256
# 两个都应输出「反例测试符合预期：注入的错误被捕获 ✓」

python verify/make_fixtures.py --clean    # 反例 2 会破坏假包，要重建
```

### 5.3 视频质量门（生产时）

```
响度   人声 +8 / BGM −6 dB / 成片 −9 LUFS
验收   |I − target| ≤ 1.5、TP ≤ −1.0
       ★ BGM 只按说话间隙包络判（P5/P25 ≥ +2）
       ★ 不得用整片 200–800 Hz LUFS
       ★ 别把 finalize 默认值 -14 LUFS 当项目 target

字幕   竖屏底边必须 < 0.80（模板 y=0.89 不合规）
       改文字层后必须重跑 overlay → preview → approve → final

换镜   ★ 换镜后绝不跑 pp8.py retime（会静默覆盖）
       ★ pp8.py all 同样不可用
       正路：swap960.py → remake_retime_shots.py --patch --apply → 逐条重跑

B-roll 与台词非一一对应时须多来源、每 2.2–3.5 秒换画面
QC     用全片联系表，不只 4 帧
```

---

## 6 Repository work

### 6.1 布局（硬约束）

```
<工作根>/
├── Haike_video/                     ← 深度 1
├── copy_skill/copy_skill-main/      ← 深度 2 ★
├── creatorhub/                      ← 深度 1
└── Haike-Videohub/                  ← 本仓库
```

**`copy_skill/copy_skill-main` 必须两层。**
写错 ⇒ `pytest.skip` 静默跳过，不报错（`test_copy_skill_research_pack.py:1316`）。

### 6.2 分支

| 仓库 | 默认分支 |
|---|---|
| Haike_video | **`dev`**（不是 main） |
| copy_skill | `main` |
| creatorhub | `main` |

### 6.3 运行时

| 仓库 | 环境 |
|---|---|
| Haike | **Python 3.12**（不是 3.10+）；pytest 必须 `--import-mode=importlib --basetemp=.p` |
| copy_skill | **`uv`**（不是 pip）：`uv sync --dev` / `uv run pytest -p no:cacheprovider` |
| creatorhub | `pip install -r requirements.txt`；uvicorn **无 --reload** |

### 6.4 改代码的约束

- **creatorhub**：只改 `studio/` 目录内文件（`PathBinder.allow_outside=False`）
- **改封面代码后必须重启服务**（uvicorn 无 reload）
- **改 `AGENT_GUIDE.md` 或 `docs/handoff/*` 后必须跑** `python scripts/audit_context_handoff.py`

### 6.5 `.gitignore` 已覆盖（不会误提交）

| 仓库 | 已排除 |
|---|---|
| Haike | `.env*`、`.backlot/`、`projects/`、`renders/`、`output/`、`music_library/`、`*.onnx`、`.venv/`、`node_modules/` |
| copy_skill | `third_party/MediaCrawler/`、`browser_data/`、`*_user_data_dir/` |
| creatorhub | `data/`、`logs/`、`*.db`、`config.yaml`、`docs/`、`_diag/`、`.workbuddy/` |

### 6.6 ⚠️ 唯一例外

**`copy_skill/config/content_intelligence.json` 是入库文件。**
往里面写 API key = **直接推到 public 仓库**。
**⇒ key 必须走环境变量。**

---

## 7 Skills and communication

### 7.1 必须停下来找人类的时刻

```
★ 需要扫码（抖音采集 / 四平台发布登录）
★ 需要推送 creatorhub 的 10 个提交（会弹凭据窗）
★ 需要真发布（人工确认门）
★ 需要另一台机器做 L3 验证
```

**⇒ 完整清单见 `docs/pending-manual-checks.md`。**

### 7.2 无人值守时的红线

```
❌ 不真跑采集（可能扫码 / 触发风控）
❌ 不调 POST /api/publish（创建即执行，会真发布）
❌ 不调 /api/publish/{tid}/run-now
❌ 不尝试交互式 git 凭据输入
❌ 不整盘复制本机目录
❌ 不删 .backlot/ 与 .workbuddy/
```

> **测试任何「真执行」分支之前，必须先探测执行目标的当前状态。**
> 「默认 dry-run」不等于「所有分支安全」——
> 2026-09-22 曾因为测试 `--commit` 时未探活而误触发一次真实发布。
> 见 `docs/pitfalls.md` §0。

### 7.3 报告方式

完成部署后，输出：
1. `verify/check_all.py --all` 的完整结果
2. 未通过项及原因
3. 需要人类做的剩余步骤（引用 `docs/pending-manual-checks.md`）

---

## 8 Authoritative detail sources

| 主题 | 权威来源 |
|---|---|
| 三仓布局 | `contracts/layout.json` |
| 版本基线 | `contracts/versions.json` |
| 发布接口 | `contracts/publish-v1.md` |
| 研究包 | `contracts/research-pack-v1.md` |
| 候选池 | `contracts/candidate-pool-v2.md` |
| 依赖分类 | `deps/A|B|C|D-*.md` |
| 密钥 | `keys/README.md` + `keys/capability-matrix.json` |
| 部署步骤 | `steps/README.md` + `steps/01..08` |
| 故障 | `docs/pitfalls.md` |
| 人工待办 | `docs/pending-manual-checks.md` |
| 本次开发标准 | `SINGLE-DEVELOPMENT-GUIDE.md` |
| **三个上游仓库内部** | 见各自仓库的 `AGENT_GUIDE.md` / `AGENTS.md` |

---

## 附：一句话总结

> **本仓库不发代码，发契约。**
> 三个上游项目各自能用，但不知道对方存在。本仓库把「它们之间怎么接」这件事
> 从人脑搬进文件，并配上一套能自动跑的验证 —— 让干净机器上的 Agent
> 不需要重新逆向 6800 行的 `main.py` 就能完成装配。
