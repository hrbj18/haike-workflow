# 验收报告

> 记录每次 `verify/check_all.py` 的执行结果，以及过程中发现的真实缺陷。
> **格式**：时间 | 命令 | 退出码 | 结论 | 备注

---

## ⚠️ 事故记录 2026-09-22 01:35

### 事件

在测试 Haike 侧发布适配器（`backlot/publish_adapter.py`）的 `--commit` 分支时，
**creatorhub 服务恰好在运行**（`127.0.0.1:8000`），导致适配器**真的创建并触发了一条发布任务**。

### 影响

| 项 | 值 |
|---|---|
| 任务 id | **78** |
| 平台 | 抖音 |
| 账号 id | 1 |
| 状态 | **`publishing`**（卡住，无法删除） |
| 标题 | 「标题」 |
| 媒体 | `fake.mp4`（**0 字节空文件**） |
| 创建时间 | `2026-09-22T01:35:16Z` |

### 处置尝试

```
DELETE /api/publish/78
→ HTTP 409 {"detail":"任务正在执行或结果待核对，请先确认平台结果"}
```

**被服务端拒绝**，符合 `contracts/publish-v1.md` §6.2 的约束：
`publishing` / `uncertain` 状态**既不能修改也不能删除**。

### 根因（我做错的两件事）

1. **测试 `--commit` 前没有探测服务是否存活。**
   我的设计假设「creatorhub 不会在跑」，但这个假设**未被程序校验**。
   ⇒ 这是一个**设计缺陷，不是意外**。

2. **没有校验成片文件大小。**
   `fake.mp4` 是 0 字节，但适配器只检查了 `is_file()` 和扩展名。
   ⇒ 0 字节文件**不应该通过任何发布前校验**。

### 修复（本次已实施）

在 `backlot/publish_adapter.py` 中增加三道闸：

| 闸 | 内容 |
|---|---|
| **G1** | `--commit` 前**强制探活** `base_url`；不可达则拒绝执行 |
| **G2** | 成片**必须 > 0 字节**，否则阻断（新增） |
| **G3** | `--commit` 必须**同时**提供 `--i-know-this-creates-a-real-task`，否则拒绝 |

### 遗留（需要人工）

**任务 id=78 的真实结果需要到抖音创作者后台核对。**

- 若后台**没有**出现该作品 ⇒ 说明发布失败，任务最终会转 `failed`，届时可删除
- 若后台**出现**了该作品 ⇒ 需要人工删除（因为它是无效媒体）

**⇒ 已登记进 `docs/pending-manual-checks.md` 第 0 项（最高优先级）。**

### 教训（写进 pitfalls）

> **对任何一个「默认 dry-run」的工具，测试它的「真执行」分支之前，
> 必须先验证执行目标的当前状态。**
> 「默认安全」不等于「分支安全」——安全必须**每一个分支各自成立**。

---

## 正式验收记录

### 2026-09-22 · L1 + L2 完整体检

| 项 | 结果 |
|---|---|
| 命令 | `python verify/check_all.py --all` |
| 退出码 | `0` |
| 总计 | **38 项** |
| PASS | 36 |
| WARN | 2 |
| **FAIL** | **0** |
| 结论 | ✅ 通过 |

**WARN 明细**（均为已知且可接受）：
```
[WARN] B.mediacrawler.git    无 .git 元数据 —— 版本不可追溯（本机现状，用户已确认接受）
[WARN] config.hotspot        copy_skill_hotspot_feed.enabled = false —— 默认关闭，未启用候选池链路
```

---

### 2026-09-22 · 反例自测 1（布局）

| 项 | 结果 |
|---|---|
| 命令 | `python verify/check_all.py --level=1 --mutate=layout` |
| 退出码 | `0` |
| 输出 | `反例测试符合预期：注入的错误被捕获 ✓` |
| 结论 | ✅ 校验器能区分单层与两层路径，**不是空转** |

---

### 2026-09-22 · 反例自测 2（sha256 篡改）

| 项 | 结果 |
|---|---|
| 命令 | `python verify/check_all.py --all --mutate=sha256` |
| 退出码 | `0` |
| 关键输出 | `[PASS] MUTATE-sha256-check 篡改被正确捕获: CopySkillHotspotFeedError` |
| 结论 | ✅ 三方一致性校验真的在工作 |

**语义**：脚本把 `_READY.json` 的 `package_manifest_sha256` 改成全 0，
消费端抛出 `CopySkillHotspotFeedError` ⇒ 证明消费端**没有盲信** `_READY.json`，
而是亲自重算了 `package-manifest.json` 的哈希。

---

### 2026-09-22 · L2 契约连通明细

**候选池**（`load_copy_skill_hotspot_feed`）：
```
[PASS] run_id=run-20260921-fixture0001
[PASS] 规范化候选数: 1
[PASS] manifest 校验通过，file_count=4
[PASS] package_manifest_sha256 三方一致
[PASS] try_ 版本返回: dict
```

**研究包**（`load_research_pack`）：
```
[PASS] content_sha256=3e056988a4cdfa52...
[PASS] sources=1 claims=2 materials=1
[PASS] _READY 校验通过（pack_id=2026-09-21-最小假包-r1）
[PASS] argument_graph.edges 非空（1 条）—— 边键路径已被覆盖
```

> **最后一条特别重要**：`argument_graph.edges` 被刻意构造成**非空**。
> 因为 Haike 既有的跨仓用例历史上 `edges` **恒为空**，
> 导致「边键改名跑偏」这个 bug 长期没被发现
> （见 `test_end_to_end_with_non_empty_argument_graph` 的 docstring）。
> ⇒ 本仓的假数据**专门覆盖了这条路径**。

---

### 2026-09-22 · 发布适配器分支测试

| # | 场景 | 期望 | 实际 | 结果 |
|---|---|---|---|---|
| 1 | 超长标题 | 本地截断 + `[TRUNCATED]` 标记 | ✅ 一致 | PASS |
| 2 | 描述不含标题关键词 | 告警 | ✅ 告警 | PASS |
| 3 | 非平台（bilibili） | 阻断 | ✅ argparse 拒绝 | PASS |
| 4 | 成片不存在 | 阻断，退出码 3 | ✅ 退出码 3 | PASS |
| 5 | 缺 `--account-id` | 退出码 4 | ✅ 退出码 4 | PASS |
| 6 | 封面不存在 | 告警 + 留空 | ✅ 一致 | PASS |
| 7 | 正常 dry-run | 退出码 0，**不发请求** | ✅ 一致 | PASS |
| 8 | `--commit` | 创建 draft | ⚠️ **见事故记录** | **FAIL** |

**分支 8 是本次唯一的真实失败**，已修复（G1/G2/G3 三道闸）。

---

## 待补验收项

| 项 | 为什么没做 | 登记于 |
|---|---|---|
| MediaCrawler 真采集 | 可能扫码 / 风控 | `pending-manual-checks.md` #2 |
| 干净机器 L3 复现 | 需另一台机器 | `pending-manual-checks.md` #3 |
| 真发布验证 | 需人工确认 | `pending-manual-checks.md` #4 |
| creatorhub 10 个提交推送 | 需凭据 | `pending-manual-checks.md` #1 |
| **任务 id=78 结果核对** | 需平台后台 | `pending-manual-checks.md` #0 |

---

## 2026-09-22 01:50 收尾轮：三仓代码修复 + 记忆落盘

### 命令与结果

| 时间 | 命令 | 退出码 | 结论 |
|---|---|---|---|
| 01:41 | `Haike_video/.venv/Scripts/python.exe scripts/audit_context_handoff.py` | 0 | **全 OK**（`CURRENT_STATUS.md` 2411/2500） |
| 01:42 | `copy_skill/.venv/Scripts/python.exe -m pytest -k "search_collector or crawler or cli"` | 0 | **70 passed** |
| 01:53 | `copy_skill/.venv/Scripts/python.exe -m pytest`（全量） | 1 | 1133 项，**3 failed**（非本轮引入，见下） |

### 本轮修复

| 文件 | 改动 | 验证 |
|---|---|---|
| `copy_skill/src/douyin_intelligence/search_collector.py` | `DEVNULL` → `capture_output`；非零退出码填 `failure`；新增 `_crawler_output_tail()` | 70 项测试通过 |
| `copy_skill/src/douyin_intelligence/cli.py` | `_run_crawl_command()` 同款修复，失败打 stderr；返回契约不变 | 同上 |
| `copy_skill/tests/test_cli.py` | 两条**断言 DEVNULL** 的既有测试改为断言捕获参数 | 同上 |
| `Haike_video/docs/handoff/CURRENT_STATUS.md` | 删过时「无封面能力」；日期更到 09-21；从 2731 压到 **2411**（原本已超限） | 审计全 OK + 14 项判据存活 |

### ★ 3 个既有 FAIL 与本轮无关（已核实）

```
tests/test_replication_theme.py::test_shipped_override_tables_are_effective
tests/test_workbench_launcher.py::test_missing_virtualenv_is_visible_nonzero_and_never_uses_system_python
tests/test_workbench_launcher.py::test_package_import_failure_is_logged_and_visible_without_silent_exit
```

**核实方式**：这两个测试文件**均不引用**本轮改动的任何符号
（`grep search_collector|_run_crawl_command|_crawler_output_tail` 无命中）。
且 `git status` 显示该仓存在**大量非本轮改动**（`AGENTS.md`、`replication_*.py`、`report_doc.py` 等），
属此前会话遗留的未提交工作。

⇒ **结论：本轮改动未引入回归。**

### 一个值得记录的反向发现

`tests/test_cli.py` 原有的两条断言：

```python
assert observed["stdout"] is subprocess.DEVNULL
assert observed["stderr"] is subprocess.DEVNULL
```

**说明「静默失败」曾被当作规格固化下来**——即当时认为「爬虫输出不该出现在我们的日志里」。
这正是排障困难的根源：非零退出码时调用方只拿到 `status="failed"`，`failure` 却是 `None`。
本轮把断言反转成 `assert "stdout" not in observed` + `assert observed["capture_output"] is True`，
让测试从「保护静默」变成「保护可诊断」。

### 记忆落盘

| 文件 | 长度 | 内容 |
|---|---|---|
| `Haike_video/.workbuddy/memory/2026-09-21.md` | 913 行 | 追加本轮全记录（含事故、两个被推翻的结论、三仓改动） |
| `Haike_video/.workbuddy/memory/MEMORY.md` | **3000/3000** | 新增「第四仓」节 + `POST /api/publish 创建即执行` 红线 |
| `Haike_video/.workbuddy/memory/MEMORY-DETAIL.md` | 77104+ | 新增 §六（第四仓 9 小节：目录职责/两层路径/假数据原理/自检/creatorhub 拓扑/静默失败/创建即执行/判据清单） |

★ 压 `MEMORY.md` 时执行了「关键判据存活检查」：12 项（`0.80`/`−9 LUFS`/`gap_policy`/`P5/P25`/
`groundAt`/`retime`/`dry-run`/`ok=false`/`id=78`/`922d5e4`/`pytest.skip`/`G1/G2/G3`）**全部命中**。

### 提交

```
01fed85 docs: 补入单次开发指导文档（目标/任务拆分/验收标准/测试方法）
8b6765b chore: 初始化集成枢纽仓库（haike-videohub）首个快照
```

工作区干净；暂存区无敏感文件（`fixtures/`、`.env*`、`config.yaml`、`*.key` 均被 `.gitignore` 拦下）。

---

## 2026-09-22 02:05 修复「反例污染夹具」

### 发现

在提交前的最终体检中，跑完两个反例**再**跑正常体检，出现残留 FAIL：

```
[FAIL] L2.candidate-pool  COPYSkillHotspotFeedError: READY manifest hash 不匹配：
      期望 cd32b250...，实际 000000...0
```

### 诊断

不是真缺陷 —— 是 `--mutate sha256` **故意**把 `package-manifest.json` 改成全 0，
而反例**只注入、不还原**。所以「反例 → 正常体检」必然看到脏状态。

### 修复

`verify/check_all.py` 新增 `_restore_after_mutation()`，在反例分支返回前
自动跑 `make_fixtures.py --clean --haike <root>/Haike_video` 重建夹具。

### 验证（连续执行，验证状态不残留）

| # | 命令 | 结果 |
|---|---|---|
| 1 | `--all --mutate sha256` | 35 项 / FAIL 0 / **反例被捕获 ✓** |
| 2 | `--all` | **38 项 / FAIL 0** ← 无残留 |
| 3 | `--all --mutate layout` | 11 项 / FAIL 0 / **反例被捕获 ✓** |
| 4 | `--all` | **38 项 / FAIL 0** ← 无残留 |

✅ 全通。已同步登记到 `docs/pitfalls.md §0b`。

### 判据

**反例跑完后 `--all` 必须仍是 38 项 0 FAIL。** 若出现残留 FAIL，
先跑 `python verify/make_fixtures.py --clean` 再判断，不要直接去改代码。
