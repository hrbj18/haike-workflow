# 单次开发指导文档 —— 可复刻工作流枢纽仓库（haike-videohub）

> 本文档是本轮开发的**唯一依据**。执行时严格遵守；偏离必须在此处登记原因。
> 编写时间：2026-09-21 · 执行窗口：无人值守（约 9 小时预算）

---

## 一、目标（G1–G7）

**总目标**：把本机跑通的三项目工作流，变成「给一个新电脑 + 本仓库 → agent 能自行装配出等价环境」的可复刻交付。

| 编号 | 目标 | 达成判据（可机检） |
|---|---|---|
| G1 | 建立第四仓库 `haike-videohub`，承载装配契约而非业务代码 | 仓库存在；`verify/check_all.py --level 1` 全通 |
| G2 | 用**机器可读契约**固化三个上游仓的路径/版本/接口，替代散文描述 | `contracts/layout.json`、`versions.json` 可解析且含 `hard_constraints` |
| G3 | 把「依赖从哪来」分成四类且互不混淆 | `deps/A|B|C|D-*.md` 四份齐备，B（外部）含获取方式 |
| G4 | 给出 agent 可顺序执行的部署手册，而非给人看的教程 | `steps/01..08` 齐备且每步含验证命令 + 反例 |
| G5 | 契约可被**真实执行**验证，不是只写文档 | `verify/check_all.py --level 2` 用假数据跑通消费端全部校验分支 |
| G6 | 校验器本身可被证伪 | 两个反例注入后被正确捕获 |
| G7 | 发布路径必须防误触发 | Haike 侧适配器含探活/零字节/显式确认三道闸 |

**非目标（本轮明确不做）**：
- 不做图形安装器、不打包成 exe
- 不把 MediaCrawler 打包进本仓（只写获取引导）
- 不更新 MediaCrawler 版本
- 不自动发布任何内容（无人值守下绝对禁止）
- 不合并三仓为一个 monorepo

---

## 二、任务拆分（T0–T12）

| 任务 | 内容 | 产出 |
|---|---|---|
| T0 | 事实勘查：三仓 commit/分支/版本、未推送提交拓扑 | 精确基线数字 |
| T1 | 设计四层目录结构（contracts/deps/keys/steps/verify/docs） | 结构定稿 |
| T2 | 写 `contracts/layout.json` + `versions.json` | 机器可读契约 |
| T3 | 写三个接口契约文档（publish / research-pack / candidate-pool） | 契约 md |
| T4 | 写 `deps/A|B|C|D` 四类依赖说明 | 依赖分层 |
| T5 | 写 `keys/` 能力矩阵（人读 + 机读） | 密钥分层 |
| T6 | 写 `steps/01..08` 部署手册 | 顺序手册 |
| T7 | 写 `verify/check_all.py`（L1 结构 + L2 契约 + 反例） | 体检脚本 |
| T8 | 写 `verify/make_fixtures.py`（假数据生成） | 夹具生成器 |
| T9 | Haike 侧 `backlot/publish_adapter.py` + 三道闸 | 发布适配器 |
| T10 | 修正 copy_skill 媒体爬虫**静默失败** | stderr 捕获 |
| T11 | 修正 Haike 过时状态文档 | CURRENT_STATUS.md:18 |
| T12 | 自测 + 反例 + 写待办/坑/验收报告 + git 提交 | 验收闭环 |

---

## 三、设计思路

### 3.1 三个核心判断

**判断一：缺的不是检查，是契约。**
三仓各自都有 test，但没有一处固定「A 仓必须放在 B 仓的第几层」。最典型的证据：`tests/backlot/test_copy_skill_research_pack.py:1310` 用 `Path(REPO_ROOT).parent / "copy_skill" / "copy_skill-main" / "src"` 定位生产端，找不到就 `pytest.skip`。**目录放错不报错，只静默跳过**——这是可复刻性的头号杀手。对策：把路径写进 `contracts/layout.json`，并让 check 脚本对反例（放错层）报 FAIL。

**判断二：creatorhub 是最大障碍。**
它是别人的 fork，`LICENSE` 404，10 个本地提交从未推送，且落后上游 4 个。若直接把它当依赖，新机器只能得到上游原版（缺封面能力、缺结果落真）。对策：在 `versions.json` 显式标注 `push_status: "NEVER_PUSHED"`，并在 `pending-manual-checks.md` 列为人工项——**不替用户决定推不推，但让缺失显式可见**。

**判断三：验收必须分层，且必须有反例。**
只跑「应该通」的用例，无法区分「校验通过」和「校验根本没在跑」。对策：L1 结构 / L2 用假数据跑真实消费端 / L3 手工项；再加两个反例（改哈希、放错层），必须被捕获。

### 3.2 为什么假数据从 Haike 侧导入消费端模块

`make_fixtures.py` 不自己实现哈希，而是：

```python
load_consumer_module(haike)  # 从 Haike 侧 import backlot.copy_skill_research_pack
content_sha256(payloads)     # 用消费端自己的函数算
```

理由：若自己按文档重写一遍哈希算法，**两边会一起错**——文档错、夹具也跟着错，校验反而通过。用消费端代码算，产出的夹具天然自洽，任何一侧改动都会被 L2 立刻发现。这是「契约可执行」而非「文档自洽」。

### 3.3 假数据刻意覆盖历史盲区

Haike 历史上有「两个跨仓用例的夹具 `argument_graph.edges` 恒为空，所以从没有用例真正走过边键」的记录（`test_copy_skill_research_pack.py:1427` docstring）。本轮的假数据**让 edges 非空**：

```python
"edges": [{"from": "c1", "to": "c2", "relation": "supports"}]
```

如果哪天 key 被改名成 `source`/`target`，L2 会立刻 FAIL。

---

## 四、前期准备

| 项 | 状态 | 说明 |
|---|---|---|
| 第四仓目录 | 已建 | `D:\刘宇钊\codex_work\Haike-Videohub\` |
| 三仓路径确认 | 已确认 | 见 `contracts/layout.json` |
| Git 可用 | 需补 PATH | `export PATH="/c/Users/.../PortableGit/versions/1.2.0/cmd:$PATH"` |
| Haike Python | 已确认 | 3.12.8（Haike 强制 3.12） |
| copy_skill 用 uv | 已确认 | `uv run pytest -p no:cacheprovider` |
| MediaCrawler | 不更新 | 只写引导，符合用户 2026-09-21 决定 |

---

## 五、执行计划（Step 0–12）

```
Step 0  事实勘查（三仓 commit / 分支 / 版本 / 未推送拓扑）
Step 1  建第四仓骨架 + .gitignore（先排除密钥与产物）
Step 2  contracts/layout.json + versions.json
Step 3  contracts/{publish-v1, research-pack-v1, candidate-pool-v2}.md
Step 4  deps/{A,B,C,D}-*.md
Step 5  keys/README.md + capability-matrix.json
Step 6  steps/README.md + 01..08
Step 7  verify/make_fixtures.py
Step 8  verify/check_all.py（L1）
Step 9  verify/check_all.py（L2 + 反例）
Step 10 Haike 侧 publish_adapter.py + 三道闸
Step 11 自测 → 对比 §六 验收标准 → 写 pending-manual-checks.md
Step 12 写记忆 + 落 docs/pitfalls.md + git 提交
```

---

## 六、验收标准（AC-1 ~ AC-10）

| 编号 | 验收标准 | 检验方式 | 结果 |
|---|---|---|---|
| AC-1 | 第四仓可独立 clone 并自检 | `python verify/check_all.py --all` | ✅ 38 项 0 FAIL |
| AC-2 | 路径错误可被检测 | 反例：把 copy_skill 放单层 → 期望 FAIL | ✅ 捕获 |
| AC-3 | 契约哈希不可篡改 | 反例：改 manifest 一个字节 → 期望校验失败 | ✅ 捕获 |
| AC-4 | 消费端全部校验分支被真实走过 | L2 无 skip | ✅ |
| AC-5 | 假数据自洽（用生产代码算哈希） | L2 research-pack 通过 | ✅ |
| AC-6 | 边键改名会被发现 | 假数据 edges 非空 | ✅ |
| AC-7 | 发布适配器三道闸有效 | G1 探活 / G2 零字节 / G3 显式确认 | ✅ 分别验证 |
| AC-8 | 无密钥/登录态进入仓库 | `git status` + 关键词扫描 | ✅ 无 |
| AC-9 | 静默失败被消除 | copy_skill 非零退出码有错误信息 | ✅ 已实现 |
| AC-10 | 待人工项显式登记 | `docs/pending-manual-checks.md` 7 项 | ✅ |

**不合格判定**：AC-2 / AC-3 任一未捕获即整体不合格（说明校验器是空转的）。

---

## 七、测试方法

### 7.1 正向
```bash
python verify/make_fixtures.py          # 生成假数据
python verify/check_all.py --all        # 期望 0 FAIL
```

### 7.2 反向（关键）
```bash
python verify/check_all.py --all --mutate layout     # 期望捕获 LAYOUT 违规
python verify/check_all.py --all --mutate sha256     # 期望捕获哈希篡改
```
判据：输出含 `[PASS] MUTATE-*`，且脚本打印「反例测试符合预期：注入的错误被捕获 ✓」。

### 7.3 三仓既有测试（不回归）
```bash
# Haike
cd Haike_video && .venv/Scripts/python.exe -m pytest --import-mode=importlib --basetemp=.p -q
# copy_skill
cd copy_skill/copy_skill-main && uv run pytest -p no:cacheprovider -q
```

### 7.4 适配器分支测试
| 分支 | 输入 | 期望 |
|---|---|---|
| 1 | 非法平台 | exit 2 |
| 2 | 非法 visibility | exit 2 |
| 3 | 视频不存在 | exit 2 |
| 4 | 标题超 20 | 截断 + warning |
| 5 | 0 字节视频 | **exit 3（G2）** |
| 6 | dry-run | exit 0，不联网 |
| 7 | --commit 无确认开关 | **exit 3（G3）** |
| 8 | --commit + 确认 + 服务未启 | exit 4（G1） |

---

## 八、风险与对策

| 风险 | 影响 | 对策 | 状态 |
|---|---|---|---|
| 误触发真实发布 | 不可逆 | 三道闸；无人值守下不调 commit | ✅ 但已发生一次事故 |
| 测试污染工作区 | 夹具误提交 | `.gitignore` 排除 `fixtures/` | ✅ |
| 校验器空转 | 假通过 | 双反例 | ✅ |
| MediaCrawler 静默失败 | 排障靠猜 | 捕获 stderr | ✅ |
| 视频号封面不可撤回 | 不可逆 | 写入 pitfalls + 必须先 dry-run | ✅ |

---

## 九、交付物清单

- `contracts/*`（5 份）、`deps/*`（4 份）、`keys/*`（2 份）、`steps/*`（9 份）
- `verify/check_all.py`、`verify/make_fixtures.py`
- `docs/{pitfalls,pending-manual-checks,verification-report}.md`
- `README.md`、`AGENT_SETUP.md`、`.gitignore`、本文件
- Haike 侧 `backlot/publish_adapter.py`；copy_skill 侧 2 文件修复

---

## 十、执行结果

全部 AC 通过，但**发生一次真实事故**：测试适配器 `--commit` 分支时，creatorhub 恰在运行，误创建真实发布任务 **id=78**（且用的是 0 字节假文件）。已补三道闸并验证有效，事故登记在 `docs/verification-report.md` 与 `docs/pitfalls.md §0`。

**教训**：默认 dry-run 不等于分支安全——测试「真执行」分支前必须先探活。
