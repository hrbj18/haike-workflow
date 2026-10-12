# Step 04 · copy_skill 安装与自检

> **目标**：`uv sync` 成功，`doctor` 能跑出结构化结论。
> ⚠️ **本仓用 `uv`，不是 pip。**

---

## 4.1 安装 uv

```powershell
# 官方安装
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 验证
uv --version
```

---

## 4.2 同步依赖

```bash
cd <工作根>/copy_skill/copy_skill-main
uv sync --dev
```

**`pyproject.toml` 关键信息**（已确认）：
```toml
name = "douyin-content-intelligence"
version = "0.3.0"
requires-python = ">=3.11"

dependencies = [
  "faster-whisper>=1.2.0",
  "httpx>=0.28.1",
  "opencv-python>=5.0.0.93",
  "Pillow>=11.0.0",
  "rapidocr>=3.4.2",
  "tzdata>=2025.2",
]

[project.scripts]
douyin-intelligence = "douyin_intelligence.cli:main"
```

> **注意**：本仓**没有 `VERSION` 文件**，版本号在 `pyproject.toml` 里。

---

## 4.3 跑 doctor（最能说明问题的一步）

`doctor` 会结构化报告 8 项必需能力：

```bash
cd <工作根>/copy_skill/copy_skill-main
uv run python -c "
import json, sys
sys.path.insert(0, 'src')
from douyin_intelligence.config import load_config
from douyin_intelligence.doctor import run_doctor
print(json.dumps(run_doctor(load_config()), ensure_ascii=False, indent=2))
"
```

**`run_doctor` 检查的 8 项**（`src/douyin_intelligence/doctor.py:21-62`）：
```
python / node / chrome / media_crawler / benchmark_accounts / ffmpeg / ffprobe / rapidocr
```
并汇总为：
```
ready_for_offline_pipeline   = 上述 8 项全 ok
ready_for_live_collection    = False（恒为 False —— 需要真实登录态）
authentication               = {"ok": False, "status": "not_probed",
                                "action": "首次真实采集时使用专用 Chrome 登录态或二维码；
                                           doctor 不读取 Cookie，也不访问抖音。"}
```

> **`ready_for_live_collection` 恒为 False 是设计如此**，不是故障。doctor **不读 Cookie、不访问抖音**。

---

## 4.4 ⚠️ MediaCrawler 相关：先读这条

如果 doctor 显示 `media_crawler.ok = False` 或 `venv_ok = False`：

**⇒ 去 [step 06](06-mediacrawler.md) 获取 MediaCrawler。**

**但即使没有 MediaCrawler，`ready_for_offline_pipeline` 也可能为 True** —— 因为 B站源是**纯标准库免登录**的（见 `sources/bilibili.py` docstring）。

---

## 4.5 采集失败时怎么看原因（锚点 `294d32d` 起已修复静默失败）

此前 `collect_search` 失败时**不给任何原因**（`stdout/stderr=DEVNULL` 且 `failure=None`）。
锚点 `294d32d`（2026-09-22）起，采集子进程**不再吞输出**：

- 非零退出：`failure` 带 `crawler exited with code N: <输出尾部>`（去空行、`" | "` 连接、截断 1200 字符）
- 超时：返回退出码 `124`，stderr 打印提示
- 非零退出且无输出：`failure` 直接提示「run the doctor check」

**⇒ 遇到 `failed` 先看 `failure` 字段；仍有疑问再跑 doctor（§4.3）。**

> 若你 clone 到的 copy_skill 比 `294d32d` 旧，则仍是静默失败 —— 按 step 02 §2.4.1 检出锚点。

详见 `docs/pitfalls.md` 第 1 条。

---

## 4.6 跑测试

```bash
cd <工作根>/copy_skill/copy_skill-main
uv run pytest -p no:cacheprovider
```

> `-p no:cacheprovider` 是作者约定的参数（见 `pyproject.toml` 的 `addopts`/测试配置）。

---

## 4.7 验证

```bash
cd <videohub>
python verify/check_all.py --level=1
```

**期望**：
```
[PASS] config.mc.root         相对路径: third_party/MediaCrawler
[PASS] config.mc.python       相对路径: third_party/MediaCrawler/.venv/Scripts/python.exe
[PASS] frozen.producer        冻结 content_sha256 一致
```

**下一步** → [05-creatorhub](05-creatorhub.md)
