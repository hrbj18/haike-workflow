# Agent 入口（工作区根目录）

本目录包含多个独立 Git 仓库。先判断用户任务属于首次部署、视频生产、发布，还是普通开发；只读相应入口，不把历史手册当作本次运行状态。用户当前指令优先。

- 首次部署或跨仓配置：读 `Haike-Videohub/AGENT_SETUP.md`，再按其中的步骤和契约执行。
- 视频理解、快速分析、多宫格抽帧或参考片拆解：先读 `Haike_video/AGENTS.md`，再读 `Haike-Videohub/agent-runbooks/视频快速理解与分层分析.md`；按目标先概览、按需精查，分析结果不自动进入制片。
- 用户要求下载指定抖音视频：读 `Haike-Videohub/agent-runbooks/下载抖音视频.md`，默认使用工作区顶层 Cookie，用户指定路径优先，调用项目内置下载入口。
- 新建、修改或审查任何视频模板 runbook/规格：先读 `Haike-Videohub/agent-runbooks/视频模板编写标准.md`，再按标准读骨架及适用扩展；共享标准缺失时报告缺失并补齐依赖，不套用另一模板。
- 用户明确说「模板图文视频」（包括制作、返工或批量生产）时：先读 `Haike_video/AGENTS.md`，随后直接读 `Haike-Videohub/agent-runbooks/模板图文视频.md`。这个同名呼叫优先于通用视频类型推断；不得改走「窗口复刻」「素材复刻」或通用 Codex 原生制片。
- 视频生产、渲染或生产端开发：先读 `Haike_video/AGENTS.md`，按它转入 `AGENT_GUIDE.md`。
- 日常可重复的跨仓操作（如采集交付、发布）：先读 `Haike-Videohub/agent-runbooks/README.md` 索引，再读匹配的手册和相关契约；执行前核对本次授权、文件、账号和实时任务状态。
- 其他子仓任务：读该子仓的 `AGENTS.md`（如果存在）及该任务需要的权威文档。

任务结束时，若发现可复用的新步骤、故障恢复方法，或旧手册与当前行为不符，按知识库 README 提交发现与证据。默认只提案；仅在用户明确委托维护知识库并核对证据时修改正式手册。改动应替换旧结论、合并重复内容，并删除失效步骤；未验证的内容不得标为「已实测」。普通问答、无新发现的重复操作无需回写。手册不得包含密钥、Cookie 或运行产物。

本根目录不在任何子仓 Git 中。可共享的规则和手册属于 `Haike-Videohub/` 仓库；根目录文件须随完整工作区另行分发。

## AOCI 仓库上下文

进入子仓任务时，先读该仓 `AGENTS.md` 和 `AOCI_AGENT_RULES.md`，再使用其对应的 AOCI MCP。跨仓任务分别遵循所涉仓库的规则和当前 Guide。

| 子仓 | 工作区 MCP 名称 |
| --- | --- |
| `Haike_video` | `aoci_haike_video` |
| `copy_skill/copy_skill-main` | `aoci_copy_skill` |
| `creatorhub` | `aoci_creatorhub` |
| `Haike-Videohub` | `aoci_videohub` |

直接打开某个子 Git 仓库时，使用其项目配置中的 `aoci`。先核对服务返回的仓库根；初始化骨架不代表索引已生成。新会话尚未加载工具时，重新打开本工作区或目标子仓会话后再建索引。工作区顶层数据、分发包与第三方运行时不属于这四份业务索引。
