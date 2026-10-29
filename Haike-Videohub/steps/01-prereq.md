# Step 01 · 前置依赖安装

> **目标**：装好 5 个外部依赖，使 `verify/check_all.py --level=1` 的 B 类全部 PASS。

---

## 1.1 Python 3.12（64 位）

**为什么是 3.12 而不是 3.10+**：Haike 的 `docs/handoff/DEPLOYMENT.md` 明确要求 64 位 Python 3.12，其依赖集在 3.12 上验证过。

```powershell
# 下载安装（勾选 "Add python.exe to PATH"）
# https://www.python.org/downloads/release/python-3128/

# 验证
python --version          # 期望 Python 3.12.x
python -c "import struct; print(struct.calcsize('P')*8, 'bit')"   # 期望 64 bit
```

> ⚠️ 不要用 3.13。可能触发扩展编译失败。

---

## 1.2 Node.js 22+

**为什么**：Haike 的 `remotion-composer/` 需要 npm 与 Node 22+。

```powershell
# 下载 https://nodejs.org/ （选 LTS 22.x）
node --version            # 期望 v22.x
npm --version
```

**安装 Remotion 前端依赖**（`node_modules/` 不入库，必须自己装）：

```powershell
cd <工作根>\Haike_video\remotion-composer
npm install
```

**验证**：

```powershell
npx remotion --version        # 期望打印 Remotion 版本号
# 或检查 package.json 里的 scripts 是否可解析
node -e "console.log(Object.keys(require('./package.json').scripts))"
```

---

## 1.3 Git

**为什么**：三仓 clone，以及 MediaCrawler 获取。

```powershell
git --version             # 期望 git version 2.x
```

Windows 用户还需注意：三仓按私有对待（见 [step 02](02-clone-repos.md) §2.3.1），clone 私有仓库时 Git 会弹凭据窗。

**无人值守场景**：先配好凭据（`gh auth` 或 SSH key），并**必须**用下面命令验证「无交互通过」，再开始 clone：

```powershell
git ls-remote https://github.com/hrbj18/Haike_video.git HEAD
# 期望：直接返回 sha，无任何提示/弹窗；否则凭据未就绪（详见 step 02 §2.3.2 的凭据预案）
```

```powershell
git config --global credential.helper manager
```

---

## 1.4 Google Chrome

**为什么**：MediaCrawler 的 CDP 采集与 creatorhub 的 Patchright 发布**共用同一个 Chrome**。

```powershell
# 下载 https://www.google.com/chrome/
Test-Path "C:\Program Files\Google\Chrome\Application\chrome.exe"   # 期望 True
```

> 这是一条**有显式报错**的依赖 —— 路径不对会在 `collector.py:184` 明确抛
> `FileNotFoundError(f"Chrome 不存在：{chrome}")`，不会静默失败。

---

## 1.5 ffmpeg / ffprobe

**为什么**：copy_skill 抽帧、探测时长、生成联系表。

**推荐做法**：直接**加进系统 PATH**，不要改配置。

```powershell
# 下载 https://www.gyan.dev/ffmpeg/builds/  或
#      https://github.com/BtbN/FFmpeg-Builds/releases
# 解压后把 bin\ 加进 PATH

ffmpeg -version           # 期望 ffmpeg version ...
ffprobe -version
```

> **为什么推荐放进 PATH 而不是改配置**：
> `src/douyin_intelligence/media_tools.py:12-18` 的 `resolve_media_tool()` 是
> ```python
> configured = ...                      # 读配置里的绝对路径
> if configured 存在: return configured
> return shutil.which(name) or name     # ← PATH 回退
> ```
> ⇒ 放进 PATH 时**完全不需要改配置**；若你放在自定义位置又没进 PATH，
> 就会静默回退到 `which` 也找不到，最终报一个含糊的错误。

---

## 1.6 验证

```bash
cd <videohub>
python verify/check_all.py --level=1
```

**期望**：以下各项 PASS（其余可能因仓库未 clone 而 FAIL，属正常）
```
[PASS] B.python
[PASS] B.node
[PASS] B.ffmpeg
[PASS] B.ffprobe
[PASS] B.chrome
```

**下一步** → [02-clone-repos](02-clone-repos.md)
