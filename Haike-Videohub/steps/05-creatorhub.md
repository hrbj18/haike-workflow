# Step 05 · creatorhub 安装与启动（可跳过）

> **目标**：发布面板在 `127.0.0.1:8000` 可访问。
> **可跳过**：只出片不发布时，整步跳过。

---

## 5.1 安装

```powershell
cd <工作根>\creatorhub
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**`requirements.txt` 的 18 个包**（已确认）：
```
fastapi==0.115.6          uvicorn[standard]==0.34.0   httpx[socks]==0.28.1
pyyaml==6.0.3             tzdata>=2025.2              sqlmodel==0.0.22
patchright==1.61.2        xhshow>=0.2.0               curl_cffi>=0.15.0
python-multipart>=0.0.9   openpyxl>=3.1.5             PyExecJS>=1.5.1
opencv-python-headless>=4.8  Pillow>=12.3.0           numpy>=1.24
websockets>=12            yt-dlp>=2025.1.15           imageio-ffmpeg>=0.5.1
```

> `patchright` 是 Playwright 的补丁版（反检测）。首次使用会下载 Chromium；
> 但**本项目配置为使用系统 Chrome**（见 `config.yaml`）。

---

## 5.2 ⚠️ 配置（必做，`config.yaml` 不在库里）

`config.yaml` 被 `.gitignore` 排除，**必须手动创建**：

```powershell
cd <工作根>\creatorhub
Copy-Item config.example.yaml config.yaml
```

**`config.example.yaml` 关键项**：
```yaml
server:
  host: 127.0.0.1
  port: 8000
engine:
  douyin_publish_mode: browser      # 注释：「发布当前仅 browser」
  xhs_publish_mode: browser
```

---

## 5.3 启动

```powershell
cd <工作根>\creatorhub
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

> ⚠️ **改完代码必须重启服务。** uvicorn 启动时**没有加 `--reload`**。

---

## 5.4 登录四个平台（要发布才做）

在面板里逐个账号扫码登录：

| 平台 | 前端标识 |
|---|---|
| 抖音 | `douyin` |
| 快手 | `kuaishou` |
| 视频号 | `shipinhao` |
| 小红书 | `xhs` |

**登录态保存在 `data/`**（已被 gitignore，**不会入库，也不应复制给其他机器**）。

### ⚠️ 视频号特别警告

> **视频号每条作品只允许改一次封面/描述，且不可撤回。**

⇒ 任何回填脚本的**猜测都不可接受**。必须 `--dry-run` 先行。

### ⚠️ 改封面/描述后必须重启服务

三平台封面代码位置：
```
抖音    app/platforms/douyin/cover.py
快手    app/platforms/kuaishou/cover.py
视频号  app/platforms/channels/publish.py   ( _confirm_cover 像素判据 )
```

**改完必须重启**（uvicorn 无 `--reload`），否则改动不生效。

---

## 5.5 发布 API 速查

详见 `contracts/publish-v1.md`。核心 4 条：

```
POST /api/publish/upload         上传媒体 → 返回服务端路径
POST /api/publish                创建任务（draft）
PUT  /api/publish/{tid}          修改（仅 draft/pending/failed/canceled）
POST /api/publish/{tid}/run-now  立即执行 ★适配器禁用
```

**⚠️ 两个必知**：
1. `title` 服务端强制截断到 **20 字**（`main.py:9130`），**不报错**
2. `GET /api/publish/published` **仅支持小红书**（其他平台返回 400）

---

## 5.6 不要跨越的红线

> **Haike 侧适配器只允许创建 draft 任务，绝不调用 `run-now`。**

依据：
- `Haike_video/AGENT_GUIDE.md:51`：「**Never publish a formal video automatically**」
- `Haike_video/docs/handoff/DECISIONS.md:10`：「自动流程只产出待审核预览，不自动发布。」

---

## 5.7 验证

```bash
# 端口探活
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000
# 期望：200

# 列出任务
curl -s http://127.0.0.1:8000/api/publish | head -c 200

# 统一体检
cd <videohub>
python verify/check_all.py --level=1
# 期望：creatorhub / creatorhub.sentinel 全 PASS
```

**下一步** → [06-mediacrawler](06-mediacrawler.md)
