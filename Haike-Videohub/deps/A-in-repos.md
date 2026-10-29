# A 类：已随三个仓库分发（无需额外获取）

> **判定依据**：`git ls-files` 能列出 ⇒ 已入库 ⇒ clone 即有。
> **本类不含任何需要下载或人工提供的东西。**

---

## A-1 Haike_video

| 资产 | 路径 | 说明 |
|---|---|---|
| 工作台源码 | `backlot/` | Python 生产调度 |
| Remotion 前端 | `remotion-composer/` | 动态画面渲染（**含独立 SVG 动画入口**） |
| 视频脚本 skill | `skills/` | Layer 2 知识层（含 `INDEX.md` 345 行） |
| Agent 技能 | `.agents/skills/` | Layer 3，47 个已安装 |
| 工具注册表 | `tools/tool_registry.py` | Layer 1 |
| 文档契约 | `docs/handoff/` | 8 份交接文档 + `context-policy.json` |
| 上下文审计 | `scripts/audit_context_handoff.py` | 字符预算审计 |
| 安装脚本 | `scripts/setup.ps1`<br>`scripts/preflight.ps1`<br>`scripts/start_backlot.ps1`<br>`启动工作台.bat`<br>`scripts/launch_backlot.py`<br>`scripts/setup_local_tts.ps1` | 全部入库 |
| 跨仓消费端 | `backlot/copy_skill_research_pack.py`<br>`backlot/research_pack_intake.py`<br>`backlot/copy_skill_hotspot_feed.py` | 权威校验层 |
| 编辑决策 CLI | `scripts/remake_editorial_cli.py` | fail-closed |
| 发布产物 schema | `schemas/artifacts/publish_log.schema.json` | v1.0 |
| 配置模板 | `.env.example`（203 行）<br>`config/daily_tech_brief.json` | 模板入库，**实值不入库** |

**入口约定**：
- Agent 第一入口：`AGENT_GUIDE.md`（98 行，8 节）
- 人第一入口：`START_HERE.md`（53 行，路由表 + 五分钟检查）
- 交付前必跑：`python scripts/audit_context_handoff.py`

---

## A-2 copy_skill（`copy_skill/copy_skill-main`）

| 资产 | 路径 | 说明 |
|---|---|---|
| 采集与情报源码 | `src/douyin_intelligence/` | 生产端全部逻辑 |
| 生产端契约 | `src/douyin_intelligence/episode_research_pack.py`<br>`src/douyin_intelligence/daily_hot_candidate_pool.py`<br>`src/douyin_intelligence/daily_material_exchange.py` | 932 行候选池等 |
| 免登录源 | `src/douyin_intelligence/sources/bilibili.py` | **纯标准库，无需 key** |
| 配置 | `config/content_intelligence.json` | 主配置 |
| 依赖声明 | `pyproject.toml`（27 行） | `uv` 管理 |
| Agent 规范 | `AGENTS.md`（75 行）<br>`docs/handoff/` | 含「单次开发指导文档」工作流 |
| 审计脚本 | `scripts/audit_handoff.py` | |
| 测试 | `tests/` + `tests/conftest.py` | |
| 冻结合同文档 | `docs/tasks/2026-09-16-episode-research-pack-v1.md` | ⚠️ **Haike 的跨仓测试会读它** |

> ⚠️ **`docs/tasks/2026-09-16-episode-research-pack-v1.md` 是跨仓硬依赖。** 缺它，Haike 的合同一致性断言会 `pytest.skip`。

---

## A-3 creatorhub

| 资产 | 路径 | 说明 |
|---|---|---|
| 服务端 | `app/main.py` | 6800+ 行，含全部发布 API |
| 平台适配 | `app/platforms/{douyin,kuaishou,channels,xhs}/` | 四平台 |
| 依赖声明 | `requirements.txt`（18 个包） | |
| 配置模板 | `config.example.yaml` | ⚠️ **`config.yaml` 被 gitignore，需手动复制** |
| 示例与文档 | `README.md` | |

**三个已入库的运维脚本**（本地二次开发带出）：见 `git log` 的 `922d5e4`。

---

## A-4 自检

```bash
# 逐个仓库确认关键文件在库
cd Haike_video && git ls-files --error-unmatch AGENT_GUIDE.md scripts/setup.ps1
cd copy_skill/copy_skill-main && git ls-files --error-unmatch pyproject.toml \
  docs/tasks/2026-09-16-episode-research-pack-v1.md
cd creatorhub && git ls-files --error-unmatch requirements.txt config.example.yaml
# 期望：三条都输出文件名，无 "did not match any file"
```

---

**下一步**：见 `deps/B-external.md`（必须下载的东西）。
