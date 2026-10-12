# Step 02 · 摆放三个仓库

> **目标**：让三仓落在 `contracts/layout.json` 规定的位置。
> ⚠️ **这一步最容易出错，而且错了不报错。**

---

## 2.1 目标布局

```
<工作根>/
├── Haike_video/                     ← 深度 1
├── copy_skill/
│   └── copy_skill-main/             ← 深度 2 ★
├── creatorhub/                      ← 深度 1
└── Haike-Videohub/                  ← 本仓库
```

**工作根示例**：`D:\刘宇钊\codex_work\`（可用环境变量 `VIDEOHUB_ROOT` 指定别的路径）

---

## 2.2 ⚠️ 为什么 `copy_skill/copy_skill-main` 必须是两层

Haike 的跨仓互操作测试是这样解析生产端模块的：

```python
# Haike_video/tests/backlot/test_copy_skill_research_pack.py:1310-1321
def _producer_module():
    import importlib, sys
    from lib.paths import REPO_ROOT
    src = Path(REPO_ROOT).parent / "copy_skill" / "copy_skill-main" / "src"
    if not (src / "douyin_intelligence" / "episode_research_pack.py").is_file():
        pytest.skip("CopySkill producer 仓库不在本机，跳过跨仓互操作")
    ...
```

以及合同文档路径（`:1385-1396`）：
```python
path = Path(REPO_ROOT).parent / "copy_skill" / "copy_skill-main" / "docs" / "tasks" / ...
```

**⇒ 路径写错时，pytest 走 `skip` 分支。**

**这不是"测试通过"，这是"测试没跑"。** 而且 skip 是静默的 —— 不看 `-v` 输出根本发现不了。这是本方案里最难自查的失败模式。

---

## 2.3 克隆（含可见性与凭据预案）

### 2.3.1 仓库可见性假设

| 仓库 | 上游 | 可见性假设 |
|---|---|---|
| Haike_video | `hrbj18/Haike_video` | **按私有对待** |
| copy_skill | `hrbj18/copy_skill` | **按私有对待** |
| creatorhub | 无可用远端（见 §2.3.4） | **人工预置** |

往私有仓 clone 会弹 git 凭据窗（`Select a credential helper`）。**无人值守场景下若弹窗无人应答，会永久卡住**（外套 `timeout` 时 git 子进程变孤儿、弹窗点不掉）。

### 2.3.2 凭据预案（按优先级）

1. **已配 `gh auth` ⇒ 用 `gh repo clone`**（走 token，不弹窗）
   ```bash
   gh auth status                        # 期望已登录
   gh repo clone hrbj18/Haike_video
   ```
2. **SSH key ⇒ 用 SSH 地址**（配好 key 后 git 不弹窗）
   ```bash
   git clone git@github.com:hrbj18/Haike_video.git
   ```
3. **人工预 clone**：由人在有凭据的机器上 clone 好，直接把目录放到 `<工作根>/` 下对应位置。

> ★ **无人值守前必须先用 ① 或 ② 验证无交互**：
> ```bash
> git ls-remote https://github.com/hrbj18/Haike_video.git HEAD
> # 期望：直接返回 sha，没有任何提示/弹窗。若卡住或要求输入密码，说明凭据没配好。
> ```
> 凭据未就绪时**不要**硬跑 clone —— 会留下点不掉的凭据弹窗。

### 2.3.3 克隆 Haike 与 copy_skill

```bash
# 1) 设定工作根（示例）
cd /d/刘宇钊/codex_work          # Git Bash
# 或 PowerShell: cd D:\刘宇钊\codex_work

# 2) Haike（私有，按 §2.3.2 选 ①/②/③）
git clone https://github.com/hrbj18/Haike_video.git

# 3) copy_skill（★ 注意目录层级；私有，按 §2.3.2 选 ①/②/③）
mkdir -p copy_skill
cd copy_skill
git clone https://github.com/hrbj18/copy_skill.git copy_skill-main
cd ..
```

### 2.3.4 creatorhub 是「人工预置依赖」（★ 不要从上游 clone）

**creatorhub 的上游 `3441293738/creatorhub` 不是可用来源。**

上游**不含本地 10 个提交**（含发布契约必需的 `d2a55c7` —— 抖音竖封面 `cover_path` 能力）。

> ⚠️ **从上游 clone 将导致 `contracts/publish-v1.md` 的 `cover_path` 契约落空、发布链路不可用。**

**主路线 —— 与 cookies 同级的「人工预置依赖」**：

| 方式 | 说明 |
|---|---|
| 从负责人本机拷贝 | 由人把 `<工作根>/creatorhub` 整个目录拷过来 |
| 负责人提供的私有远端 | 按负责人给的私有 URL clone（**本文档不虚构任何 URL**） |

**版本锚点：`922d5e4`（`main` 分支）。** 拿到后必须核对（见 §2.6）：

```bash
cd <工作根>/creatorhub
git log --oneline -1                       # 期望：922d5e4 chore: 定版快照 2026-09-21 ...
grep -rn "cover_path" app/main.py | head   # 期望：能看到 cover_path 字段
```

**待办依赖**：`docs/pending-manual-checks.md` 第 1 项（推送私有远端）完成后，本节可换成负责人提供的私有远端 URL。

> 该仓是别人的 fork，上游 `LICENSE` 404、**不可分发**；仅作内部使用。

---

## 2.4 分支确认

| 仓库 | 期望分支 |
|---|---|
| Haike_video | `dev`（**不是 main**） |
| copy_skill/copy_skill-main | `main` |
| creatorhub | `main` |

```bash
cd Haike_video && git branch --show-current            # 期望 dev
cd ../copy_skill/copy_skill-main && git branch --show-current   # 期望 main
cd ../../creatorhub && git branch --show-current       # 期望 main
```

> **Haike 的默认分支是 `dev`。** `origin` 未指定默认分支时，`git clone` 会取远端 HEAD；
> 若拿到 `main` 而你要的开发版在 `dev`，需 `git checkout dev`。

### 2.4.1 版本锚点核对（★ 只验分支名不够）

clone 拿到的是**远端 HEAD**，可能 ≠ `contracts/versions.json` 登记的基线 commit。
必须逐一核对、不符就 checkout：

```bash
cd Haike_video                   && git rev-parse --short HEAD   # 期望 = versions.json haike.local_commit（当前 395890c）
cd ../copy_skill/copy_skill-main && git rev-parse --short HEAD   # 期望 = copyskill.local_commit（当前 294d32d）
cd ../../creatorhub              && git rev-parse --short HEAD   # 期望 = creatorhub.local_commit（当前 922d5e4）

# 任一不符：
git fetch --all && git checkout <versions.json 里登记的 sha>
```

> 锚点值以 `contracts/versions.json` 的 `local_commit` 为准（会随基线推进更新）。
> ★ Haike 锚点 ≥ `395890c` 才含 `backlot/publish_adapter.py`（体检 `adapter.*` 4 项依赖它随仓分发）。
> 检出具体 SHA 会进入 detached HEAD —— 这是**刻意的版本锚定**；要回分支头再 `git checkout dev`（或 `main`）。

---

## 2.5 关键：`docs/tasks/` 合同文档必须存在

Haike 的合同一致性断言会读：
```
copy_skill/copy_skill-main/docs/tasks/2026-09-16-episode-research-pack-v1.md
```

```bash
ls copy_skill/copy_skill-main/docs/tasks/2026-09-16-episode-research-pack-v1.md
# 期望：文件存在。缺失则对应断言会被 pytest.skip
```

---

## 2.6 验证

```bash
cd <videohub>
python verify/check_all.py --level=1
```

**期望**：
```
[PASS] haike                  仓库存在: Haike_video
[PASS] haike.sentinel         7 个哨兵文件全部存在
[PASS] copyskill              仓库存在: copy_skill\copy_skill-main
[PASS] copyskill.sentinel     6 个哨兵文件全部存在
[PASS] creatorhub             仓库存在: creatorhub
[PASS] creatorhub.sentinel    3 个哨兵文件全部存在
[PASS] LAYOUT-1               copyskill 两层路径正确: copy_skill/copy_skill-main
[PASS] contract-doc           冻结合同文档存在
[PASS] versions               creatorhub 未推送 commit 数已登记: 10
[PASS] frozen.producer        冻结 content_sha256 一致
[PASS] frozen.consumer-test   冻结 content_sha256 一致
```

### 反例自测（强烈建议跑一次）

```bash
python verify/check_all.py --level=1 --mutate=layout
# 期望：MUTATE-layout PASS，并输出"反例被正确捕获"
```

这条命令的作用是**证明体检脚本真的能区分单层与两层路径**。一个永远返回 PASS 的校验器没有价值。

**下一步** → [03-haike](03-haike.md)
