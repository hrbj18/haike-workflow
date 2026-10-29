# 发布契约 `publish-v1`

> 本文描述历史可选封面任务。三平台指定封面发布包使用 [publish-v2.md](publish-v2.md)；新适配器会先核对服务端 v2 能力。以下旧字段和 best-effort 语义只适用于 `contract_version=1`。

> **状态**：本文档是三个仓库里**唯一没有第二份副本**的知识。Haike 的 `skills/pipelines/*/publish-director.md` 只讲「标签清楚 / 元数据以信息为主 / 人工确认门」，**零 creatorhub 内容**；creatorhub 也不谈 Haike。两边靠人脑接上。
> **本文档的目的**：把这条「Haike 成片 → creatorhub 发布」的接线**固化成可执行契约**，使干净机器上的 Agent 不需要重新逆向 `app/main.py`。

---

## 0. 铁律（先读这条）

### 0.1 绝不调用 `run-now`

> **Haike 侧适配器只允许把任务推进到「待发队列」，绝不调用 `run-now`。**

依据：
- `Haike_video/AGENT_GUIDE.md:51` —— 「Preview and final render must share the same timeline... **Never publish a formal video automatically; automation may stop at a review-ready preview.**」
- `Haike_video/docs/handoff/DECISIONS.md:10` —— 「**自动流程只产出待审核预览，不自动发布。**」
- `Haike_video/skills/pipelines/avatar-spokesperson/publish-director.md` —— 「`human_approval_default: true`」+「Approval is per-gate — an earlier "go ahead" does not cover this gate.」

⇒ 适配器的默认行为是 `--dry-run`。

### 0.2 ⚠️⚠️ `POST /api/publish` 本身就是危险动作 —— **创建即执行**

**这是 2026-09-22 事故后实测确认的事实，修正了此前基于接口名（`submit_once` / `scope="publish"`）的错误假设。**

```
假设（错）：POST /api/publish  = 创建草稿，不执行
事实（对）：POST /api/publish 在默认引擎配置下 = 创建并立即进入执行
```

**实测证据**：
```
1. 只调 POST /api/publish（确实没有调 /run-now）
2. 返回的任务 status 直接是 "publishing"（不是 "draft"）
3. DELETE 立即被拒：409「任务正在执行或结果待核对」
   ⇒ 说明它已经进入执行态，不是待确认的草稿
```

**⇒ 推论（对适配器设计的约束）**：

| 闸 | 内容 |
|---|---|
| **G1** | `--commit` 前**强制探活** creatorhub（不可达则拒绝） |
| **G2** | 成片为 **0 字节** 直接阻断（无效媒体不得入队） |
| **G3** | `--commit` 必须同时给显式确认开关 |
| **G3b** | stdin 是 TTY 时**再问一次** `yes` |

**⇒ 若只想「准备 payload 不落库」，唯一正确做法是 `--dry-run`。**

---

## 1. 端点清单（源码级确认）

所有端点定义在 `creatorhub/app/main.py`。

| 方法 | 路径 | 行号 | 用途 |
|---|---|---|---|
| `POST` | `/api/publish/upload` | `:9013` | 上传本地媒体文件，返回服务端路径 |
| `GET` | `/api/publish` | `:9091` | 列出发布任务，可选 `?platform=` 过滤 |
| `POST` | `/api/publish` | `:9101` | **创建发布任务（核心）** |
| `PUT` | `/api/publish/{tid}` | `:9143` | 修改任务（仅特定状态允许） |
| `POST` | `/api/publish/{tid}/run-now` | `:9185` | **立即执行（适配器禁用）** |
| `DELETE` | `/api/publish/{tid}` | `:9192` | 删除任务（特定状态拒绝） |
| `GET` | `/api/publish/published` | `:9256` | ⚠️ **仅支持小红书** |
| `GET` | `/api/publish/note-media` | `:9398` | 作品媒体详情 |
| `GET` | `/api/publish/note-comments` | `:9470` | 作品评论 |

---

## 2. `POST /api/publish` 请求体完整字段

对应 `PublishIn`（`app/main.py:9029-9040`）：

```python
class PublishIn(BaseModel):
    account_id: int
    media_type: str = "images"            # images | video
    title: str = ""
    desc: str = ""
    topics: str = ""
    location: str = ""                    # 视频号:位置 POI(可选)
    media_paths: list[str] = []
    visibility: str = "public"            # 抖音:public | friends | private
    allow_save: bool = True               # 抖音:是否允许他人保存
    cover_path: str = ""                  # 抖音:竖封面图本地路径(3:4,best-effort)
    scheduled_at: str | None = None       # ISO 带偏移；无偏移按账号时区，空=尽快发
```

### 2.1 字段语义与约束

| 字段 | 必填 | 适用平台 | 说明 |
|---|---|---|---|
| `account_id` | ✅ | 全部 | 必须是 creatorhub 里已登录的账号，且平台属于 `("xhs","kuaishou","douyin","shipinhao")` |
| `media_type` | — | 全部 | **Haike 出片一律用 `"video"`** |
| `title` | — | 全部 | ⚠️ **服务端强制截断到前 20 字**，见 §3 |
| `desc` | — | 全部 | 视频描述（**不是标题**） |
| `topics` | — | 全部 | 话题串 |
| `location` | — | 视频号 | 位置 POI，截断 60 字 |
| `media_paths` | ✅ | 全部 | 服务端逐条 `Path(p).is_file()` 过滤；过滤后为空 → 400 |
| `visibility` | — | 抖音 | `public` \| `friends` \| `private` |
| `allow_save` | — | 抖音 | 是否允许他人保存 |
| `cover_path` | — | 抖音 | 竖封面 3:4 本地路径，截断 500 字，**best-effort**；依赖本地 commit `d2a55c7` |
| `scheduled_at` | — | 全部 | ISO 8601；**无时区偏移则按账号时区解释** |

---

## 3. ⚠️ 截断规则（会静默丢数据，必须前置处理）

服务端对超长字段**直接切掉，不报错、不提示**：

```python
# app/main.py:9130-9132
title=body.title.strip()[:20]
location=body.location.strip()[:60]
cover_path=body.cover_path.strip()[:500]
```

**含义**：如果你的标题写了 30 个字，发出去的只有前 20 个，**没有任何报错**。

⇒ **Haike 侧适配器的责任**：在构造 payload 时**先自己截断**，并在 `--dry-run` 输出中被截断的字段用 `[TRUNCATED]` 标记，让人看得见。

> 这与记忆中的一条踩坑完全同源：**「管理页卡片文案 = 视频描述，不是标题」**。抖音后台展示的是 `desc`，标题被截到 20 字后往往不足以承载关键词，所以**关键词必须放在 `desc` 开头**。

---

## 4. 账号与登录态前置校验（`app/main.py:9107-9126`）

```
平台取值必须是 ("xhs", "kuaishou", "douyin", "shipinhao") 之一
  ├─ xhs        → 走 validate_publish_files()，失败返回 422
  │                登录态要求：creator_storage_state or has_creator_cookies(storage_state)
  └─ kuaishou / douyin / shipinhao
                → 走 Path(p).is_file() 过滤，过滤后为空返回 400「没有可用的媒体文件,请先上传」
                 登录态要求：creator_storage_state or storage_state
```

**⇒ 未登录的账号，创建任务时就会失败。干净机器上必须先完成一次扫码登录。**

---

## 5. ⚠️ `GET /api/publish/published` 仅支持小红书

```python
# app/main.py:9256 起
if not acc or acc.platform != "xhs":
    raise HTTPException(400, "请选择一个已登录的小红书账号")
```

**⇒ 不要用这个接口做通用回读校验。** 抖音 / 快手 / 视频号的发布结果只能：
1. 通过 `GET /api/publish` 读任务的 `status` / `result_url` / `error`，**或**
2. 到创作者后台人工核对。

Haike 侧适配器**不得**假设该接口对所有平台可用。

---

## 6. 状态流转与可操作边界

### 6.1 `PUT /api/publish/{tid}` 允许修改的状态
```
("draft", "pending", "failed", "canceled")
```
`publishing` / `uncertain` / `done` 状态下**不可修改**。

### 6.2 `DELETE /api/publish/{tid}` 拒绝的状态
```
("publishing", "uncertain")   → 409 Conflict
```

**⇒ `uncertain` 是危险状态**：表示「发出去了但没确认到底成没成」。此时既不能改也不能删，只能等或人工介入。**这也是为什么适配器绝不能自动执行**。

### 6.3 `PublishUpdate` 可改字段（`app/main.py:9043-9052`）
```
account_id / title / desc / topics / location / visibility / allow_save / cover_path / scheduled_at
（全部 Optional）
```

---

## 7. 任务对象输出结构（`_publish_dict`，`app/main.py:9055-9081`）

```json
{
  "id": 0, "platform": "", "account_id": 0,
  "media_type": "", "title": "", "desc": "", "topics": "", "location": "",
  "cover_path": "",
  "status": "", "result_url": "",
  "visibility": "", "allow_save": true,
  "error": null, "media_count": 0,
  "source_platform": null, "source_content_id": null,
  "scheduled_at": null,
  "schedule_needs_confirmation": false,
  "next_allowed_at": null,
  "blocked_reason": null,
  "created_at": ""
}
```

**快手特殊处理**：历史任务把「发布表单地址」存成结果地址，列表输出时**即时修正**为 `KS_MANAGE_URL`（判断依据：`result_url` 为空或路径含 `/article/publish/`）。

---

## 8. Haike 成片 → creatorhub 任务的映射表

Haike 侧的产物（`.backlot/` 或 `projects/` 下的成片与元数据）到 creatorhub payload 的对应关系：

| Haike 侧来源 | creatorhub 字段 | 处理规则 |
|---|---|---|
| 最终成片 `.mp4` 路径 | `media_paths` | 单元素数组；**必须先 `POST /api/publish/upload` 或确保路径对服务端可见** |
| `—` | `media_type` | **恒为 `"video"`** |
| 标题/文案 | `title` | **≤ 20 字**，超长本地截断 + 告警 |
| 视频描述 | `desc` | **关键词放开头**（后台卡片展示的是它） |
| 话题列表 | `topics` | 由 `topics` 数组 join |
| 发布账号 | `account_id` | 来自 Haike 配置的 platform→account_id 映射 |
| 封面图 | `cover_path` | 3:4 竖封面；无则留空（best-effort，不阻断） |
| `—` | `visibility` | 默认 `public`，可配置 |
| `—` | `scheduled_at` | **默认空 = 不自动发**（符合铁律） |

### 8.1 `upload` 与 `media_paths` 的关系（关键细节）

`POST /api/publish/upload`（`app/main.py:9013`）会把文件存到 `UPLOAD_DIR = Path("./data/uploads")`，返回：
```json
{ "files": [ { "path": "<服务端绝对路径>", "name": "<原文件名>" } ] }
```

**⇒ 两种路径策略**：
- **同机部署**（本方案默认）：Haike 与 creatorhub 在同一台机器，可直接把 Haike 的成片绝对路径填进 `media_paths`，无需 upload。
- **跨机部署**：必须先 upload，再把返回的 `path` 填进 `media_paths`。

Haike 侧适配器**默认走同机直填**，并在 `--dry-run` 输出中提示这一前提。

---

## 9. Haike 侧适配器（已实现）

**实现位置**：`Haike_video/backlot/publish_adapter.py`

```
输入：一个成片路径 + 发布意图（平台、账号、文案、话题、封面、可选定时）
输出：一个 payload（dry-run）或一个真实任务（需过三道闸）

默认行为：
  --dry-run                              ✅ 默认开启 —— 只打印 payload，不发请求
  禁止 /run-now                          ✅ 代码中根本没有这个调用
  title 本地截断到 20 字 + [TRUNCATED]     ✅
  desc 关键词位置告警                     ✅
  cover_path 非 3:4 告警（PIL 读尺寸）     ✅ 不阻断
  平台白名单校验                          ✅
  metadata 不完整 → 阻断（退出码 3）       ✅

★ 三道闸（2026-09-22 事故后新增）：
  G1  --commit 前强制探活 creatorhub      ✅ probe_service()
  G2  成片 0 字节直接阻断                  ✅
  G3  --commit 必须配 --i-know-this-creates-a-real-task  ✅
  G3b stdin 是 TTY 时再问一次 yes          ✅
```

**退出码约定**（与 Haike 既有 CLI 风格一致）：
```
0 = 成功（或 dry-run 完成）
2 = 输入错误（平台/路径/HTTP 失败）
3 = 被阻断（未 approve / 契约不满足 / 缺确认开关）
4 = 未配置（缺 account_id / 服务不可达）
```

**调用示例**：

```bash
# 安全：只生成 payload（默认）
python backlot/publish_adapter.py \
  --video renders/final.mp4 --platform douyin --account-id 1 \
  --title "二十字以内的标题" --desc "关键词放这里开头"

# 危险：真的落库（需三道闸全过）
python backlot/publish_adapter.py \
  --video renders/final.mp4 --platform douyin --account-id 1 \
  --title "标题" --commit --i-know-this-creates-a-real-task
```

---

## 10. 快速自检清单

部署完成后，逐条确认：

- [ ] creatorhub 服务在 `127.0.0.1:8000` 可访问
- [ ] 目标平台账号已登录（`creator_storage_state` 存在）
- [ ] `config.yaml` 已从 `config.example.yaml` 复制并填好
- [ ] `POST /api/publish` 用 `media_type: "video"` 能创建出 `draft` 任务
- [ ] `title` 超过 20 字时，返回值中被截断（预期行为，非 bug）
- [ ] 成片路径在 creatorhub 进程中可访问（同机部署）
- [ ] **未**调用 `/run-now`
- [ ] 确认 `GET /api/publish/published` 对非 xhs 平台返回 400（预期行为）

---

## 11. 未解决 / 需人工确认

1. **creatorhub 的 10 个本地提交未推送** ⇒ 干净机器 clone 上游拿不到 `cover_path` 能力。**必须先完成推送**（见 `docs/pending-manual-checks.md`）。
2. **真发布验证从未做过** ⇒ 本契约的字段映射是源码级推导，未经过一次真实发布验证。
3. **`upload` 接口的实际存储行为**未在本机实测（`data/` 被 gitignore，也从未调用过）。
