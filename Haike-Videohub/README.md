# haike-videohub

> **一个 Agent 驱动的装配仓库**：把三个独立的上游项目组合成「素材采集 → 视频制作 → 自动发布」的完整工作流。
> **给一台干净电脑 + 一个 Agent，就能复刻出完整能力。**

---

## 这是什么

三个上游仓库各自独立、彼此不知道对方存在：

| 仓库 | 职责 | 上游 |
|---|---|---|
| **Haike_video** | 视频生产工作台（分镜 → Remotion 渲染 → 配音 → 成片） | `hrbj18/Haike_video` |
| **copy_skill** | 素材采集与选题情报（B站/抖音采集、候选池、研究包） | `hrbj18/copy_skill` |
| **creatorhub** | 多平台发布面板（抖音/快手/视频号/小红书） | `3441293738/creatorhub` |

**本仓库不发代码，发契约。** 它把三者之间原本只存在于人脑中的接线固化下来：

- **布局契约** —— 三个仓库必须落在什么位置（写错会静默 skip）
- **数据契约** —— 两条跨仓数据流的精确字段与校验链
- **发布契约** —— Haike 成片如何映射到 creatorhub 的发布接口（**这是唯一没有任何地方写过的知识**）
- **依赖四分类** —— 哪些随仓库来、哪些必须下载、哪些必须人工给、哪些绝不复制
- **可执行验证** —— 38 项自动体检（未启用抖音采集时 36 项 + 2 条 WARN）+ 2 个反例自测

---

## 快速开始

### 给人看

```
1. 读 docs/pending-manual-checks.md  ← 先知道有哪些事自动化做不了
2. 按 steps/01 → steps/08 执行
3. 最后跑 verify/check_all.py --all
```

### 给 Agent 看

**从这里开始** → [`AGENT_SETUP.md`](AGENT_SETUP.md)

可复刻的 Agent 操作知识库 → [`agent-runbooks/README.md`](agent-runbooks/README.md)

---

## 最小路径（零 key、零扫码、零付费）

```
steps/01-prereq.md      装 Python 3.12 / Node 22 / Git / Chrome / ffmpeg
steps/02-clone-repos.md 摆放三个仓库（creatorhub 为人工预置依赖）
steps/03-haike.md       启动工作台
steps/08-verify.md      体检
```

**⇒ 这条路径已经能出片**，因为 B站源是纯标准库免登录的，Remotion 渲染完全本地。

---

## 目录结构

```
haike-videohub/
├── README.md                       ← 你在看的
├── AGENT_SETUP.md                  ← Agent 第一入口
├── SINGLE-DEVELOPMENT-GUIDE.md     ← 本次开发的指导文档与验收标准
├── contracts/                      ← 契约（机器可读优先）
│   ├── layout.json                 三仓布局硬约束
│   ├── versions.json               版本基线 + 未推送待办
│   ├── publish-v1.md               ★ 发布契约（唯一缺失的知识）
│   ├── research-pack-v1.md         研究包契约
│   └── candidate-pool-v2.md        候选池契约
├── deps/                           ← 依赖四分类
│   ├── A-in-repos.md               已随仓库分发
│   ├── B-external.md               必须下载
│   ├── C-human.md                  必须人工提供
│   └── D-never-copy.md             绝不复制
├── keys/                           ← 密钥与能力矩阵
│   ├── README.md                   人读版
│   └── capability-matrix.json      机读版
├── steps/                          ← 8 步部署手册
├── agent-runbooks/                 ← 可迭代的 Agent 操作知识库
├── verify/                         ← 可执行验证
│   ├── check_all.py                L1 静态探活 + L2 契约连通
│   └── make_fixtures.py            生成 L2 所需的假数据
├── fixtures/                       ← 假数据（由脚本生成）
└── docs/
    ├── pitfalls.md                 17 条踩坑记录
    ├── pending-manual-checks.md    ★ 必须人工完成的清单
    └── verification-report.md      验收记录
```

---

## 三层验证体系

| 级别 | 内容 | 能自动验? |
|---|---|---|
| **L1** | 静态探活：路径、哨兵文件、JSON、版本、外部依赖 | ✅ |
| **L2** | 契约连通：用**假数据**跑跨仓读取函数 | ✅ |
| **L3** | 端到端：真采集 + 真发布 + 干净机器复现 | ❌ 需人工 |

```bash
python verify/check_all.py --level=1                      # L1
python verify/make_fixtures.py --clean                    # 准备假数据
python verify/check_all.py --all                          # L1 + L2

# 反例自测（证明校验不是空转）
python verify/check_all.py --level=1 --mutate=layout
python verify/check_all.py --all --mutate=sha256
```

### 为什么 L2 用假数据有效

因为消费端是**严格自校验**的：它会亲自核对 sha256、重启指纹、三方一致
（`current.json` / `_READY.json` / 实际文件）。所以一份 sha256 正确的最小假包
能真实走完全部校验分支 —— 这等价于验证了「生产端输出格式 == 消费端期望格式」，
而这件事目前**没有任何自动化在管**。

---

## 最重要的四条红线

### 1. 绝不自动发布

> `Haike_video/AGENT_GUIDE.md:51`：「**Never publish a formal video automatically**」
> `Haike_video/docs/handoff/DECISIONS.md:10`：「自动流程只产出待审核预览，不自动发布。」

⇒ 适配器**默认 dry-run**；**绝不调 `/run-now`**。

### 2. ⚠️ `POST /api/publish` 创建即执行（实测，非推测）

**这是 2026-09-22 误触发一次真实发布后确认的事实：**

```
假设（错）：POST /api/publish = 创建草稿，不执行
事实（对）：默认引擎配置下 = 创建并立即进入 publishing
```

⇒ 所以「不调 run-now」**不足以**保证安全。
Haike 侧适配器因此加了**三道闸**（探活 / 0 字节阻断 / 显式确认开关），
详见 `contracts/publish-v1.md` §0.2 与 `docs/pitfalls.md` §0。

**⇒ 只想看 payload 就只用 `--dry-run`。**

### 3. `copy_skill/copy_skill-main` 必须两层

写错成单层 ⇒ Haike 的跨仓测试**静默 skip**，不报错。
（`test_copy_skill_research_pack.py:1316`）

### 4. 绝不整盘复制本机目录

会带上登录 Cookie、密钥、失效的绝对路径。
⇒ 全新 clone + 按 `steps/` 重建。见 `deps/D-never-copy.md`。

---

## 必须先知道的两件事

### ① creatorhub 有 10 个本地提交从未推送

**⇒ 别人 clone 上游拿不到抖音竖封面能力。**
**⇒ 这是「可复刻」链路最致命的一处断裂。**

详见 `docs/pending-manual-checks.md` 第 1 项（含完整 commit 链与推送命令）。

### ② MediaCrawler 不在任何仓库里

`.gitmodules` 里的声明**拉不下它**（没有 gitlink 记录）。
必须手动 clone。详见 `deps/B-external.md` B-1 与 `steps/06-mediacrawler.md`。

---

## 相关文档

| 我想... | 看这个 |
|---|---|
| 让 Agent 部署 | `AGENT_SETUP.md` |
| 知道哪些要人手做 | `docs/pending-manual-checks.md` |
| 看接口字段 | `contracts/publish-v1.md` |
| 排查故障 | `docs/pitfalls.md` |
| 知道哪些不能复制 | `deps/D-never-copy.md` |
| 知道要买什么 key | `keys/README.md` |
| 了解本次开发的验收标准 | `SINGLE-DEVELOPMENT-GUIDE.md` |
