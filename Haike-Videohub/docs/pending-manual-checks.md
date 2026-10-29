# 必须人工完成的清单

> **本文件登记的是「自动化做不了 / 本次无人值守没做」的事。**
> **不藏、不假称已完成。** 每项都给出：为什么、怎么做、做完怎么验。

---

## 🔴 第 0 项（最紧急）：核对误触发的发布任务 id=78

✅ 已关闭（2026-09-22）：负责人核对抖音创作者后台（账号 id=1），未发现标题为「标题」的站内作品，判定 id=78 未造成实际发布，本项关闭。

### 背景

**2026-09-22 01:35，我在测试发布适配器的 `--commit` 分支时误触发了一次真实发布。**
完整事故记录见 `docs/verification-report.md`。

```
任务 id   : 78
平台      : douyin
账号 id   : 1
状态      : publishing（卡住，DELETE 返回 409）
标题      : 「标题」
媒体      : fake.mp4（0 字节空文件）
创建时间  : 2026-09-22T01:35:16Z
```

### 为什么必须你来处理

- `publishing` / `uncertain` 状态**既不能修改也不能删除**（409），见 `contracts/publish-v1.md` §6.2
- 需要**到抖音创作者后台人工核对**
- 我没有你的账号访问权限

### 怎么做

1. 登录**抖音创作者后台**，账号对应 creatorhub 的 `account_id = 1`
2. 查看是否多出一条以「标题」为题、媒体无效的作品
3. 分情况处理：

| 情况 | 处置 |
|---|---|
| 后台**没有**该作品 | 等任务转 `failed` 后可删除；或重启 creatorhub 后重试 DELETE |
| 后台**有**该作品（失败作品/草稿） | **人工删除**（它是 0 字节无效媒体） |
| 任务仍是 `publishing` | 可在 creatorhub 面板确认结果，或等待平台超时 |

### 做完怎么验

```bash
curl -s http://127.0.0.1:8000/api/publish | python -c "
import json,sys
d=json.load(sys.stdin)
print([ (t['id'],t['status']) for t in d if t['id']==78 ])
"
# 期望：状态不再是 publishing，或条目已消失
```

### 已做的防护（防止再犯）

`backlot/publish_adapter.py` 已加三道闸：

| 闸 | 作用 |
|---|---|
| **G1** | `--commit` 前强制探活 creatorhub，不可达就拒绝 |
| **G2** | 成片为 **0 字节** 直接阻断 |
| **G3** | `--commit` 必须同时给 `--i-know-this-creates-a-real-task` |
| **G3b** | stdin 是 TTY 时**再问一次** `yes` |

**⇒ 已验证：三道闸都有效，且不会再无意创建任务。**

### ★ 附带结论（重要）

> **`POST /api/publish` 在默认引擎配置下「创建即执行」。**
> 它不是「只创建草稿」。这个事实已补进 `contracts/publish-v1.md`。

---

## ★ 第 1 项（最高优先级）：推送 creatorhub 的 10 个本地提交

### 问题

本机 `creatorhub` 仓库：

```
remotes:
  origin    → （不存在）
  upstream  → https://github.com/3441293738/creatorhub.git

local main = 922d5e4
```

**⇒ 本地 10 个二次开发提交从未推送到任何仓库。**

### 后果

**任何人 clone 上游 `3441293738/creatorhub` 只能拿到官方版，拿不到抖音竖封面等本地能力。**
这是「可复刻」链路最致命的一处断裂。

### 丢掉的 10 个提交

```
922d5e4 chore: 定版快照 2026-09-21 —— 三平台封面链路修复 + 运维脚本归档
8783ef3 test(douyin): 对抗套件补落盘隔离,单独运行不再污染 data/debug
e2b95b8 test(douyin): 封面测试落盘改到临时目录，不再污染 data/debug
13f3e52 test(qa): ADV-7b 转正 —— 失败路径样式泄漏已修复
baac3c2 fix(douyin): 封面失败路径撤掉注入的 hover-show 样式
fb8713f test(qa): 抖音封面独立对抗验证
d2a55c7 feat(douyin): 发布时支持设置竖封面 3:4（任务级 cover_path，best-effort）  ★关键
99b59b3 test: 修正两条原理上不可能成立的既有断言（上游遗留，非本次合并引入）
f704ce9 Merge upstream v0.2.2 (3d7698f) into 本地二次开发
973c44b feat: 二次开发 —— 发布结果落真、登录态判定对齐业务码、消除窗口打扰  ★关键
```

**两个关键提交**：
- `d2a55c7` —— 抖音竖封面 `cover_path`（**上游没有的能力**，`contracts/publish-v1.md` 的对应字段依赖它）
- `973c44b` —— 发布结果落真、登录态判定对齐业务码

### 同时注意：本地落后上游 4 个提交

相对上游 `v0.2.3`，本地**缺**：
```
f48ff93 完善 Windows 客户端升级与旧库迁移
a71f2c4 忽略测试与临时产物
081c348 修复抖音粉丝接口并支持大规模关注列表
b72706d feat: 实现抖音陌生人私信 API
```
分叉规模：`git diff --stat 02232e67..HEAD` = **184 files, +24923/-2457**

> 这 4 个主要是客户端升级与私信/粉丝功能，**与发布链路关系不大**，
> 所以**不合并也可接受**。是否合并由你决定。

### 怎么做

```bash
cd <工作根>/creatorhub

# 1) 新建自己的仓库（GitHub 网页操作，或用 gh）
#    假定命名为 haike-creatorhub

# 2) 加 origin
git remote add origin https://github.com/<你的账号>/haike-creatorhub.git

# 3) 推送
git push -u origin main
git push origin --tags          # 可选：带上 v1.0.0 等本地 tag

# 4) 验证
git remote -v
git log --oneline -3 origin/main
```

> ⚠️ **这一步会弹凭据窗，需要你在场。** 这就是本次无人值守没做它的原因。
>
> ⚠️ 推送前确认 `.gitignore` 已排除：`data/`、`logs/`、`*.db`、`config.yaml`、`_diag/`、`.workbuddy/`
> （已实测确认这 6 项都被排除，**不会带账号数据**）

### 做完怎么验

```bash
# 在一个空目录
git clone https://github.com/<你的账号>/haike-creatorhub.git t
cd t && git log --oneline -3
# 期望：看到 922d5e4 chore: 定版快照 2026-09-21 ...

# 确认封面能力在
grep -rn "cover_path" app/main.py | head
# 期望：能看到 cover_path 字段
```

### 完成后要改本仓库的地方

1. `contracts/versions.json` → `repos.creatorhub.remotes.origin` 填上新 URL
2. `contracts/versions.json` → `push_status` 从 `"NEVER_PUSHED"` 改为 `"pushed"`
3. `steps/02-clone-repos.md` §2.3.4 → 把「人工预置依赖」改成你的私有远端 URL
4. `deps/B-external.md` → 若要新增 B 类项（自己仓库），补进去

---

## ★ 第 1b 项：创建远端并推送第四仓 haike-videohub

### 问题

第四仓目前**只有本地提交，没有远端**。已确定名称 `haike-videohub`，且要求**公开**仓库。

```
8b6765b chore: 初始化集成枢纽仓库（haike-videohub）首个快照
01fed85 docs: 补入单次开发指导文档（目标/任务拆分/验收标准/测试方法）
```

### 后果

| 影响 | 说明 |
|---|---|
| **不可复刻** | 别人无法 clone 本仓 ⇒ 整个「可复刻交付」的目标落不了地 |
| 不阻塞本地 | 三仓本地工作流完全正常，本仓也只是文档 |

⇒ **不阻塞开发，但阻塞交付。**

### 怎么做

1. 在 GitHub 创建**公开**仓库 `haike-videohub`（不要勾选任何初始化文件）。
2. 加远端并推送：
   ```bash
   cd "D:/刘宇钊/codex_work/Haike-Videohub"
   git remote add origin https://github.com/<你的账号>/haike-videohub.git
   git branch -M main
   git push -u origin main
   ```
   ⚠️ 推送私有仓库可能弹出 `CredentialHelperSelector` 窗口；若外套了 `timeout`，
   超时后 git 子进程会变孤儿、弹窗点不掉（见用户级记忆）。

### ★ 推送前必须再确认一次「没有敏感内容」

```bash
git ls-files | grep -E "\.env|config\.yaml|\.key$|secret"   # 期望无输出
```

`.gitignore` 已排除 `fixtures/`、`.env*`、`config.yaml`、`gcp-*.json`、`output/`、`logs/`、`.workbuddy/`，
但**新增文件后仍需复查**。

### 做完怎么验

```bash
git remote -v                    # 应有 origin，且是公开地址
git ls-remote origin HEAD        # 能返回 sha
```
然后修 `contracts/versions.json` 的 `hub.remote.origin`（现在写的是 `null`）。

---

## ★ 第 2 项：MediaCrawler 真采集验证

### 为什么不能自动做

- 首次采集**可能需要扫码**
- 反复尝试可能**触发平台风控**
- 会**留下登录态**（副作用）

### 怎么做

```bash
cd <工作根>/copy_skill/copy_skill-main

# 1) 先跑 doctor 确认前置
uv run python -c "
import json, sys; sys.path.insert(0,'src')
from douyin_intelligence.config import load_config
from douyin_intelligence.doctor import run_doctor
print(json.dumps(run_doctor(load_config())['media_crawler'], ensure_ascii=False, indent=2))
"
# 期望：ok=True, venv_ok=True

# 2) 执行一次真实搜索采集（会弹浏览器，可能要扫码）
uv run douyin-intelligence collect-search --help
# 按 help 给出的参数实际跑一次
```

### 做完怎么验

1. **采集有产出**：检查输出目录有 jsonl 文件
2. **不是静默失败**：`status` 应为 `"success"`（而非 `"failed"`）
3. **若失败**：不要猜，重跑 doctor，对比哪一项从 True 变了

### ⚠️ 附带任务：修复静默失败（建议做）

**当前问题**（见 `docs/pitfalls.md` #1）：
```python
# search_collector.py:100-107
subprocess.run(..., stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
# search_collector.py:121-131
else:
    status = "failed"
    # failure 保持 None
```

**建议修复**（低风险，只加捕获不改控制流）：
- `capture_output=True` 代替 `DEVNULL`
- 非零退出码时把 stderr 尾部填进 `failure`
- 错误信息中提示「运行 doctor」

**⇒ 已在 `contracts/versions.json` 登记。** 本次无人值守**未改动三仓业务代码**。

---

## ★ 第 3 项：干净机器端到端复现（L3）

### 为什么不能自动做

需要**另一台机器**。本机无法自我验证「在别处能否重建」。

### 怎么做

1. 找一台干净 Windows 机器（**不要复制本机任何目录**）
2. clone 本仓库
3. 严格按 `steps/01` → `steps/08` 执行
4. 记录每一步的偏差

### 做完怎么验

```bash
python verify/check_all.py --all
# 期望：38 项，0 FAIL

python verify/check_all.py --level=1 --mutate=layout
python verify/check_all.py --all --mutate=sha256
# 期望：两个反例都被捕获
```

**⇒ 然后人工走一遍完整链路**：采一条素材 → 渲染 → 出片 → （可选）送发布队列。

### 预期的坑

| 可能的问题 | 原因 |
|---|---|
| 依赖装不上 | 版本漂移（`requirements.txt` 已 pin，但系统依赖未 pin） |
| 路径失效 | 本机存在绝对路径配置（`content_intelligence.json:4-7` 的 ffmpeg） |
| 分支不对 | Haike 默认分支是 `dev` 不是 `main` |
| 跨仓测试 skip | `copy_skill/copy_skill-main` 两层路径没摆对 |

---

## ★ 第 4 项：真发布验证

### 为什么不能自动做

- 违反「**Never publish a formal video automatically**」（`AGENT_GUIDE.md:51`）
- 需要**人工确认**（`publish-director.md` 的 `human_approval_default: true`）
- 需要到**创作者后台核对**
- **视频号每条作品只允许改一次封面/描述且不可撤回**

### 怎么做

```bash
# 1) 确认 creatorhub 在跑，且目标平台已扫码登录
curl -s http://127.0.0.1:8000/api/publish | head -c 200

# 2) 用 Haike 侧适配器 dry-run 生成 payload（不发请求）
#    （适配器设计见 contracts/publish-v1.md §9）

# 3) 人工确认 payload 正确后，再创建 draft 任务
#    ★ 绝不调用 /run-now
```

### 做完怎么验

1. `GET /api/publish` 能看到任务，`status` 为 `draft`
2. 人工在创作者后台核对发布结果与 `result_url`

### ⚠️ 特别注意

| 平台 | 特别事项 |
|---|---|
| 视频号 | **改一次不可撤回** ⇒ 必须 dry-run 先看 |
| 全部 | `title` 会被截断到 20 字 ⇒ 关键词放 `desc` 开头 |
| 全部 | `GET /api/publish/published` **只支持小红书** |

---

## 第 5 项：确认相对上游是否需要合并

见第 1 项的「本地落后上游 4 个提交」段。

**建议**：先不合并，等发布链路稳定后再说。

---

## 第 6 项（可选）：启用候选池链路

`Haike_video/config/daily_tech_brief.json` 里 `copy_skill_hotspot_feed.enabled` 默认是 `false`。

**要启用候选池 → 每日科技简报链路时**，需要：
1. 把 `enabled` 改成 `true`
2. 把 `root` 指向 copy_skill 的实际输出目录（或设 `COPY_SKILL_HOTSPOT_ROOT` 环境变量）
3. 跑 `verify/check_all.py` 确认 `config.hotspot` 变 PASS

---

## 汇总

| # | 项 | 优先级 | 需要什么 | 无人值守可做? |
|---|---|---|---|---|
| 0 | **核对误触发的发布任务 id=78** | 已关闭 | 抖音创作者后台看一眼 | ❌ |
| 1 | 推送 creatorhub 10 个提交 | ★★★ | 一次凭据输入 | ❌ |
| 1b | 创建远端并推送第四仓 | ★★★ | 一次凭据输入 | ❌ |
| 2 | MediaCrawler 真采集 | ★★ | 可能扫码 | ❌ |
| 3 | 干净机器端到端复现 | ★★★ | 另一台机器 | ❌ |
| 4 | 真发布验证 | ★★ | 人工确认 + 后台核对 | ❌ |
| 5 | 决定是否合并上游 4 提交 | ★ | 判断 | ❌ |
| 6 | 启用候选池链路 | ★ | 一次配置改动 | ✅ 可做 |

### 建议顺序

1. **第 0 项**——先确认有没有多出一条站内作品（可能已经在抖音上），这是唯一「已经发生」的事。
2. **第 1 项 + 第 1b 项**——两件都是「一次凭据输入」，放一起做。不做它们，
   别人 clone 到的 creatorhub 是缺功能的官方版、且根本拿不到本仓，整个「可复刻」目标是空的。
3. 其余按需。

### 已完成的收尾（2026-09-22 01:50，无需人工）

- ✅ 三仓代码修复（copy_skill 静默失败消除 + Haike 过时状态文档更正）
- ✅ 四份记忆落盘（`2026-09-21.md` / `MEMORY.md` 3000/3000 / `MEMORY-DETAIL.md §六`）
- ✅ 第四仓两个提交（`8b6765b`、`01fed85`）
- ✅ 38 项体检 0 FAIL + 两个反例均被捕获
- ✅ `docs/handoff/CURRENT_STATUS.md` 从超限 2731 压到合规 2411，14 项判据存活
