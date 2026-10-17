# 便携包初始化与启动

根目录同时有 `PACKAGE-MANIFEST.json`、`runtime/` 和 `portable/` 的 ZIP 使用本文。包内已包含声明的 Windows x64 运行环境和前端产物；初始化使用包内 Python，不需要先执行源码的 `scripts/setup.ps1`。没有该清单的源码 checkout 使用根 [README.md](../README.md) 的安装流程。

## 首次解压

1. 完整解压到自己可写的本地目录，保留根目录和各模块的相对位置。先核对随 ZIP 交付的 SHA256；解压后完整性由下方诊断检查。
2. 按 [API Key 与一次导入](API_KEY_SETUP.md) 准备单独的私有 Markdown 配置文档。在解压根目录的 PowerShell 执行下方命令，一次完成环境重定位、配置计划/导入/检查和完整诊断；每步出错即停止。默认保留已有非空配置。
3. 确认命令退出码为 0、配置结果 `configuration_complete: true`，最后诊断 `ok: true`。日后可运行 `03-check.cmd -Full` 重新核对清单和运行依赖。暂时只有空模板时，可先双击 `01-setup.cmd` 做基础初始化，再准备自己的配置。
4. 双击 `02-start.cmd` 打开数字人口播工作台。启动器只复用身份属于本解压目录的服务；默认工作台端口 14756、账号服务端口 8000，占用时自动选择附近空闲端口。
5. 按 [API Key 与一次导入](API_KEY_SETUP.md) 的第 4 节在本机扫码登录平台账号。确认本次所需服务后，按根 [START_HERE.md](../START_HERE.md) 第 8 节分别验收单条制作和夜间三条制作/发布/汇报。

```powershell
.\01-setup.cmd -ConfigDocument 'D:\用户私有配置\用户配置.private.md' -Full
```

将命令中的路径换为自己的实际绝对路径。明确更新文档指定字段时可加 `-ReplaceConfig`；先核对文档和目标副本。含真实 Keys 的文档独立保存，不加入交付 ZIP。

初始化和诊断不联网安装依赖、不生成付费视频、不提交真实发布。数字人、云端识别/配音等需要联网访问已开通的云服务；平台登录、素材获取和发布也需要联网。包内本地识别模型是可选离线资源，干净默认识别路线仍为海客网关。

## 给 Agent 的命令

推荐先用上面的 `01-setup.cmd -ConfigDocument` 完成一次初始化。以下 PowerShell 命令用于分别诊断、启动或由 Agent 调用底层入口：

```powershell
& .\runtime\python\python.exe -s .\portable\portable.py prepare
& .\runtime\python\python.exe -s .\portable\portable.py diagnose --full
& .\runtime\python\python.exe -s .\portable\portable.py start --no-browser
```

逐条检查退出码和返回的 `ok`。`start` 返回的 `services` 中，`kind: "backlot"` 的 `url` 是实际工作台地址，`kind: "creatorhub"` 是本副本账号服务；同一结果保存在 `.portable/services.json`。后续 HTTP 调用和批次 `--base` 使用实际工作台根地址，移除 `/avatar` 路径部分。

需要显式起始端口时使用 `start --port 14756 --publisher-port 8000`。端口占用会继续寻找空闲端口，不停止其他项目的进程。换目录后重新执行 `01-setup.cmd`，再启动当前副本。

模块 CLI 仍使用各模块自己的 `.venv/Scripts/python.exe`。在当前 PowerShell 会话先载入包内环境，继而按根 [START_HERE.md](../START_HERE.md) 调用已有工具：

```powershell
. .\portable\portable-env.ps1
& .\Haike_video\.venv\Scripts\python.exe .\Haike_video\scripts\codex_video_batch.py --help
```

Agent 应先读根 `AGENTS.md` 和 `START_HERE.md`，再按对应模块规则工作。完整音轨和声音样本是两条输入路线，不能互换。单一配置文档的导入与检查按 [API Key 与一次导入](API_KEY_SETUP.md) 执行；夜间任务仍依赖 Agent 宿主定时唤醒。

## 检查失败与交付边界

诊断结果在 `.portable/logs/diagnose.json`；初始化记录在 `.portable/prepared.json`。启动失败先保留这些记录及 `.local/launcher/` 的对应日志，核对是否完整解压、当前目录是否可写、文件是否被安全软件隔离，再运行 `03-check.cmd -Full`。向 Agent 提供错误摘要和路径，私人配置和完整凭据留在本机。

`PACKAGE-MANIFEST.json` 记录包内文件及哈希；初始化后需要变更的少量路径标为 `mutable`，其余分发文件由完整诊断校验。包内包括的具体依赖以该清单为准，保留各组件许可与来源声明。日常使用产生的账号、Cookie、Key、草稿、素材和作品属于本用户，后续升级应单独备份这些数据。

包内不附带制作机器的 Key、Cookie、浏览器会话、私人音色/人物图、历史项目和任务。源码配置模板保持空凭据；含真实 Keys 的私有配置文档独立交给用户，保存在用户指定的本地私有目录，排除在 Git、ZIP 和报告外。模板示例是可分发资源，新用户的人物图和音频由本人导入。

可选择已开通的海客网关或明确配置自己的现有直连服务。联网素材/AI 分镜的独立中转配置、抖音采集可选环境/授权及所选服务的实际检查方法，见 [API Key 与一次导入](API_KEY_SETUP.md)。扫码、导入和静态检查不代替真实制作发布验收。

离线初始化、完整性检查和本地服务启动的结果分别记录。本机隔离目录检查通过不等于另一台物理机已验收，也不证明新账户的云端制作或真实平台发布已跑通。第一次完整生产验证使用用户明确授权的素材、预算和发布范围。
