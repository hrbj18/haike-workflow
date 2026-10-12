# Step 06 · MediaCrawler 获取（可跳过）

> **目标**：`third_party/MediaCrawler/` 就位，且 venv 可用。
> **可跳过**：不用抖音采集时（B站源免登录），整步跳过。

---

## 6.1 先搞清楚一件事

**MediaCrawler 不在 copy_skill 仓库里，而且 git 拉不到。**

这不是配置问题，是**作者本人的设计**。三处证据（逐字）：

### 证据 1 — `copy_skill/.gitignore:27-35`
```
# Third-party MediaCrawler: declared as a submodule in .gitmodules.
# The bundled copy was shipped as a ZIP with .git stripped, so it cannot be
# recorded as a gitlink (it would resolve to 0000000). Ignore the tree and
# re-obtain it with: git submodule update --init third_party/MediaCrawler
third_party/MediaCrawler/
third_party/MediaCrawler/.venv/
third_party/MediaCrawler/data/
third_party/MediaCrawler/browser_data/
third_party/MediaCrawler/*_user_data_dir/
```

### 证据 2 — `copy_skill/README.md:38`
> MediaCrawler 在 `.gitmodules` 里被声明为子模块（上游 `https://github.com/NanmiCoder/MediaCrawler.git`），但**本仓库并没有把它记录成 gitlink**：`git submodule status` 输出为空，`git ls-tree HEAD third_party/` 亦为空。因此 `git clone --recurse-submodules` 与 `git submodule update --init` **都不会把它拉下来**——首次克隆用普通克隆即可

### 证据 3 — `copy_skill/README.md:46`
> 确实需要 MediaCrawler 时，请按 `.gitmodules` 里的 URL 自行获取并放到 `third_party/MediaCrawler/`。该路径（连同 `data/`、`browser_data/`、`*_user_data_dir/`）已被 `.gitignore` 忽略，不会进入版本库。

---

## 6.2 ⚠️ 三个常见误解

| 误解 | 事实 |
|---|---|
| ❌「`git clone --recurse-submodules` 会拉下来」 | **不会。** `.gitmodules` 只是声明，没有 gitlink 记录 |
| ❌「`git submodule update --init` 会拉下来」 | **不会。** 同上 |
| ❌「本地有 = 仓库里有」 | **不是。** 本地有是当初手工放的；`.gitignore` 明确排除 |

**⇒ 必须手动 clone。**

---

## 6.3 获取

```bash
cd <工作根>/copy_skill/copy_skill-main

git clone https://github.com/NanmiCoder/MediaCrawler.git third_party/MediaCrawler
```

**网络受限时的备选**：
```bash
curl -L https://github.com/NanmiCoder/MediaCrawler/archive/refs/heads/main.zip -o /tmp/mc.zip
unzip /tmp/mc.zip -d third_party/
mv third_party/MediaCrawler-main third_party/MediaCrawler
```

> ⚠️ **不要执行 `git submodule add`。** 那会把 MediaCrawler 记成 gitlink，
> 改变仓库结构，与作者的设计相悖。**直接 clone 到被 gitignore 的路径即可。**

---

## 6.4 建立独立 venv

MediaCrawler 需要**自己的 Python 环境**，不要和 copy_skill 的 uv 环境混用：

```bash
cd <工作根>/copy_skill/copy_skill-main/third_party/MediaCrawler
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

> Windows 下是 `.venv/Scripts/`，Linux/macOS 是 `.venv/bin/`。
> `config/content_intelligence.json` 里写死的是 **Windows 形式**。

---

## 6.5 许可证

`third_party/MediaCrawler/LICENSE` 首行：
```
NON-COMMERCIAL LEARNING LICENSE 1.1
```
- 条件 2：「limited to learning and research purposes only」
- 条件 3：「may not be used for any commercial purposes」

**⇒ 与本项目「内部学习研究」的定位一致。**
**⇒ 但不得用于商业用途，不得对外提供服务。**

---

## 6.6 首次采集需要扫码（要采集才做）

配置见 `content_intelligence.json` 的 `media_crawler` 段：
```json
{
  "root": "third_party/MediaCrawler",
  "python": "third_party/MediaCrawler/.venv/Scripts/python.exe",
  "chrome_path": "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "user_data_dir": "third_party/MediaCrawler/browser_data/cdp_dy_user_data_dir",
  "keep_open_on_needs_login": true,
  "reuse_persistent_profile": true
}
```

**⇒ 首次采集时会弹二维码等你扫。`keep_open_on_needs_login: true` 保证浏览器不自动关。**
**⇒ `reuse_persistent_profile: true` 意味着扫一次可长期复用。**

---

## 6.7 ⚠️ 静默失败机制（必读）

**MediaCrawler 调用失败时默认没有任何错误信息。**

```python
# search_collector.py:46-77   构造命令
# search_collector.py:100-107 执行（★ stderr 被吞）
subprocess.run(command, cwd=..., check=False, timeout=timeout_seconds,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# search_collector.py:108-131 结果判定
if TimeoutExpired:        failure = f"crawler timed out after {timeout_seconds} seconds"
elif returncode == 0 and files:  status = "success"
elif returncode == 0:            status = "empty" ; failure = "crawler completed without output files"
else:                            status = "failed"
                                 # ★ failure 保持 None —— 没有任何错误信息！
```

同样问题：`cli.py:82-95` 的 `_run_crawl_command()`（也是 DEVNULL；timeout 返回 124）。

**崩点**（`mediacrawler_runner.py:44-55`）：
```python
os.chdir(root)
sys.path.insert(0, str(root))
import config                                    # ← root 不存在时在此崩
from media_platform.douyin.client import DouYinClient
```

**⇒ 遇到 `failed` 且无原因时，不要猜，直接跑 doctor（[step 04 §4.3](04-copyskill.md)）。**

---

## 6.8 验证

```bash
# 1) 文件探活
cd <工作根>/copy_skill/copy_skill-main
ls third_party/MediaCrawler/main.py
ls third_party/MediaCrawler/.venv/Scripts/python.exe

# 2) 统一体检
cd <videohub>
python verify/check_all.py --level=1
```

**期望**：
```
[PASS] B.mediacrawler        MediaCrawler 已就位
[PASS] B.mediacrawler.git    带 git 元数据（可追溯版本）✓     ← 用 clone 方式就会 PASS
[PASS] B.mediacrawler.venv   venv 已建 ✓
```

> 若显示 `[WARN] B.mediacrawler.git 无 .git 元数据`：
> 说明你是用 ZIP 方式装的。功能可用，但**版本不可追溯**。
> 建议改用 clone 方式重装。

**下一步** → [07-keys](07-keys.md)
