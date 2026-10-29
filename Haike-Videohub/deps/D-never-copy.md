# D 类：绝不复制 / 绝不入库

> **判定依据**：含个人信息、含密钥、体积过大、或是本机独有的一次性状态。
> **本类是本方案的安全边界。任何自动化脚本都不得跨越。**
> ⚠️ **最重要的一条**：**不要把本机的这些目录「整盘复制」到干净机器，也不要提交进任何仓库。**

---

## D-1 浏览器登录态（个人信息 + 账号安全）

| 目录 | 所在仓库 | 内容 |
|---|---|---|
| `third_party/MediaCrawler/browser_data/` | copy_skill | **抖音登录 Cookie + 浏览器 profile** |
| `third_party/MediaCrawler/*_user_data_dir/` | copy_skill | 同上 |
| `data/` | creatorhub | **四平台登录态**（`creator_storage_state`） |

**证据**：
- `copy_skill/.gitignore:31-35` 明确排除 `browser_data/` 与 `*_user_data_dir/`
- `creatorhub/.gitignore` 排除 `data/`

**为什么不能复制**：
1. **等于转移账号控制权**。Cookie 就是登录凭证，复制过去对方就是你的账号。
2. **平台会检测异地登录**，可能触发风控甚至封号。
3. **干净机器上应当自己扫自己的码**——这才是「可复刻」的正确含义。

**⇒ 干净机器上的正确做法：在新机器上重新扫码登录。**

---

## D-2 密钥实值

| 路径 | 仓库 |
|---|---|
| `.env.local` / `.env.secrets.local` | Haike |
| `config.yaml` | creatorhub |
| `gcp-*.json` / `*-service-account.json` | Haike |

**证据**：`Haike_video/docs/handoff/DEPLOYMENT.md` 发布边界明确列出「禁提交 `.env*` 实值」。

**⇒ 干净机器上的正确做法：用 `.env.example` / `config.example.yaml` 做模板，人工填。**

---

## D-3 大体积产物（占空间 + 无复刻价值）

| 目录 | 仓库 | 内容 | 为什么不能复制 |
|---|---|---|---|
| `.backlot/` | Haike | 生产队列、账本、诊断 | **可重新生成**；且含真实项目数据 |
| `projects/` | Haike | 渲染运行时 | 体积极大 |
| `renders/` | Haike | 渲染产物 | 体积极大 |
| `content/` | Haike | 内容与素材库 | 可能含版权素材 |
| `output/` | copy_skill | 采集输出、候选池、研究包 | 可重新采集 |
| `logs/` | creatorhub | 运行日志 | 无价值 |
| `cache/` `temp/` | Haike | 缓存与临时 | 无价值 |
| `node_modules/` | Haike | 前端依赖 | **用 `npm install` 重建** |
| `.venv/` | copy_skill 的 MediaCrawler | 虚拟环境 | **用 `python -m venv` 重建** |
| `__pycache__/` | 全部 | 字节码 | 无价值 |
| `*.onnx` | Haike | 模型权重 | 体积极大，按需下载 |

**证据**：三仓各自的 `.gitignore` 均已排除。

**⇒ 干净机器上的正确做法：全部重建（`npm install` / `python -m venv` / 重新采集）。**

---

## D-4 个人素材与版权内容

| 类型 | 位置 | 为什么不能复制 |
|---|---|---|
| 个人黄金样稿 | Haike | 个人创作资产 |
| 私有音色 | Haike TTS 配置 | 个人声音克隆，涉及人格权 |
| 人物图 | Haike | 肖像权 |
| 音乐库 `music_library/` | Haike | **版权**（`music_library/` 被 gitignore） |
| 付费产物 | Haike | 已付费内容不应再分发 |
| 采集到的第三方视频 | copy_skill `output/` | **版权**，且平台条款禁止转存 |

**证据**：
- `Haike_video/.gitignore` 排除 `music_library/`、`corpus/`、`output/`、`internal/`
- `Haike_video/docs/handoff/DEPLOYMENT.md` 发布边界：禁提交「模型、私有音色、人物图、音乐、渲染、付费产物、审计证据、pytest 临时目录、个人黄金样稿」

> ⚠️ **特别注意**：`third_party/MediaCrawler/` 本身也**不要复制**。
> 不是因为版权（它允许学习使用），而是因为：
> 1. 它应该是从上游 clone 的，带自己的 `.git`
> 2. 复制过去的那份**会带上你的 `browser_data/`**
> 3. 版本无法追溯
> **⇒ 干净机器上从 `deps/B-external.md` 的 URL 重新 clone。**

---

## D-5 审计与临时证据

| 路径 | 为什么不能复制 |
|---|---|
| `_diag/` | 诊断脚本与中间产物（creatorhub/copy_skill 均 gitignore） |
| `.pytest-lib` `.p` `_pytestlib` | pytest 临时目录 |
| `_*.txt` `_*.json` `_*.pyc` | creatorhub 的 `scripts/` 下被排除的临时文件 |
| `_restart_0918.cmd` | creatorhub 排除的一次性脚本 |

**证据**：`creatorhub/.gitignore` 明确排除 `_diag/`、`scripts/*.log|*.txt|*.patch|_*.json|_*.pyc`、`_restart_0918.cmd`。

---

## D-6 WorkBuddy 项目数据

| 路径 | 说明 |
|---|---|
| `.workbuddy/` | WorkBuddy 的项目数据与记忆（**不是临时缓存，但也不应跨机复制**） |

**证据**：`creatorhub/.gitignore` 排除 `.workbuddy/`；记忆系统也说明「`.workbuddy` 文件夹存储项目相关数据，不是临时缓存，请勿删除」。

**⇒ 保留在本机，但不复制给别的机器。** 新机器上会自己生成。

---

## D-7 一份「整盘复制」为什么必然失败

如果直接把本机的 `D:\刘宇钊\codex_work\` 整盘拷过去，会发生：

| 后果 | 原因 |
|---|---|
| **账号泄露** | 带上 `browser_data/` 与 `data/`，Cookie 直接可用 |
| **密钥泄露** | 带上 `.env.local`、`config.yaml` |
| **路径全部失效** | 配置文件里大量绝对路径指向 `D:\刘宇钊\codex_work\...`（如 `content_intelligence.json:4-7` 的 ffmpeg 路径、`:839` 的 `consumer_root`） |
| **状态不一致** | `.backlot/` 队列里是上一台机器的项目，可能与新机器不匹配 |
| **体积巨大** | `node_modules/`、`.venv/`、`renders/`、`output/` 可达数十 GB |
| **无法追溯** | 复制来的 MediaCrawler 没有 `.git`，不知道是哪个版本 |
| **垃圾污染** | `_diag/`、`__pycache__/`、`.pytest-lib` 混进新环境 |

**⇒ 正确做法：全新 clone + 按 `steps/` 顺序重建。这就是第四仓存在的意义。**

---

## D-8 自检：确认没有越界

```bash
# 1) 确认关键目录确实被 gitignore
cd Haike_video && git check-ignore -v .env.local .backlot renders node_modules
cd copy_skill/copy_skill-main && git check-ignore -v third_party/MediaCrawler \
  third_party/MediaCrawler/browser_data output
cd creatorhub && git check-ignore -v data config.yaml logs _diag

# 2) 确认仓库里没有残留的密钥样式字符串
cd Haike_video && git grep -nE '(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})' -- . | head
# 期望：无匹配

# 3) 确认没有大文件被误提交
cd Haike_video && git ls-files | xargs -I{} du -h {} 2>/dev/null | sort -rh | head -10
```

---

## D-9 汇总：四类边界一览

| 类别 | 数量级 | 干净机器上的动作 |
|---|---|---|
| **A 已随仓库分发** | 代码 + 配置模板 + 文档 | `git clone` 即有 |
| **B 必须下载** | 7 项（3 项硬依赖） | 按 `steps/` 手动 + `verify` 自动检查 |
| **C 人工提供** | TTS key（必需）+ 可选 key + 3 处扫码 | 人工填 + 扫码 |
| **D 绝不复制** | 登录态 / 密钥 / 大产物 / 版权素材 / 临时文件 | **重新生成或重新获取** |

---

**返回**：`deps/A-in-repos.md` · `deps/B-external.md` · `deps/C-human.md`
