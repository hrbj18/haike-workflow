# Step 03 · Haike_video 安装与启动

> **目标**：工作台在 `127.0.0.1:4754` 可访问，`preflight.ps1` 通过。

---

## 3.1 安装

```powershell
cd <工作根>\Haike_video
.\scripts\setup.ps1
```

> **Git Bash 等价**（无人值守/无 PowerShell 交互窗口时）：
> ```bash
> cd <工作根>/Haike_video
> powershell.exe -ExecutionPolicy Bypass -File ./scripts/setup.ps1
> ```

**`setup.ps1` 做什么**（已读源码确认）：
- 创建 `.venv`（Python 3.12）
- 安装 `requirements`
- 装 Remotion 前端依赖
- 装 `static-ffmpeg`
- 准备配置模板

### 可选：本地 TTS

```powershell
.\scripts\setup_local_tts.ps1
```

> **可以跳过。** `docs/handoff/DECISIONS.md:12-13`：「端口 `127.0.0.1:17494` 是内置 Qwen3-TTS」+「当前生产配音**统一走云端**（`doubao`/`tencent`）」。
> ⇒ 不装本地 TTS，配云端 key 即可（见 step 07）。

---

## 3.2 预检

```powershell
.\scripts\preflight.ps1
```

> **Git Bash 等价**：`powershell.exe -ExecutionPolicy Bypass -File ./scripts/preflight.ps1`

**期望**：无 FAIL。

---

## 3.3 启动工作台

三种方式，任选：

```powershell
# A) 双击批处理
.\启动工作台.bat

# B) PowerShell 脚本
.\scripts\start_backlot.ps1

# C) Python 分离启动（pythonw + DETACHED_PROCESS）
python .\scripts\launch_backlot.py
```

**端口**：`127.0.0.1:4754`

### ★ 可直接复制的启动命令模板

把两条运行时硬约束（无沙箱 / `CODEBUDDY_SAFE_DELETE_ENABLED=0`）与「4754 单实例」
一起固化。**无人值守直接复制下面这段**（Git Bash）：

```bash
# 1) 设安全删除开关（约束 2：必须为 0，否则清理动作被拦）
export CODEBUDDY_SAFE_DELETE_ENABLED=0

# 2) 确认 4754 没有旧实例（约束 3：单实例）
netstat -ano -p TCP | grep ':4754' || echo "4754 空闲，可启动"

# 3) 启动工作台（约束 1：必须在无沙箱环境执行）
cd <工作根>/Haike_video
python ./scripts/launch_backlot.py        # 或 .\scripts\start_backlot.ps1

# 4) 探活验证（与 §3.6 同款）
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:4754
# 期望：200 或 302
```

**机械校验**（让脚本盯住上面三条约束，而不是靠人记）：

```bash
cd <videohub>
CODEBUDDY_SAFE_DELETE_ENABLED=0 python verify/check_all.py --all --runtime
# 期望：runtime.port / runtime.single-instance / runtime.safe-delete 三项 PASS
# 注：--runtime 是可选标志，不进默认 --all（项数不变）
```

---

## 3.4 ⚠️ 启动时的两条硬约束

### 约束 1：必须无沙箱

工作台需要读写工作区外的路径（渲染、缓存、素材）。**在受限沙箱里会失败。**

### 约束 2：必须设 `CODEBUDDY_SAFE_DELETE_ENABLED=0`

否则某些清理动作会被拦。

### 约束 3：**端口 4754 只允许一个实例**

多开会互相抢锁，表现为随机失败。

```powershell
# 检查是否已有实例
Get-NetTCPConnection -LocalPort 4754 -ErrorAction SilentlyContinue
```

---

## 3.5 ⚠️ 僵尸状态识别（重要）

**症状**：没有队列进程在跑，但界面显示 `preview_render = generating`。

**这是僵尸状态，不是真在渲染。**

真值在 SQLite：
```
Haike_video/.backlot/production-queue.sqlite3  →  表 production_jobs
```

**恢复步骤**：
```
1. 停掉服务
2. 把 automation.status 改成 review_ready
3. 把 preview_render.status 改成 failed
4. 重启服务
```

---

## 3.6 验证

```bash
# 1) 端口探活
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:4754
# 期望：200 或 302

# 2) 统一体检
cd <videohub>
python verify/check_all.py --level=1
# 期望：haike / haike.sentinel / frozen.consumer-test 全 PASS
```

---

## 3.7 已知陷阱

| 陷阱 | 表现 | 处理 |
|---|---|---|
| pytest 参数缺失 | 导入冲突 | 必须 `--import-mode=importlib --basetemp=.p` |
| 多实例 | 随机锁失败 | 确认 4754 只有一个进程 |
| 僵尸 preview | 卡在 generating | 见 §3.5 |
| `.backlot/` 被删 | 队列历史丢失 | **不要删 `.backlot/`**，它是项目数据不是缓存 |

**下一步** → [04-copyskill](04-copyskill.md)
