# 通用素材管理与项目引用 V1.1

管理入口 `/material-library/manage`；旧 `/material-library` 继续提供九秒模板的裁切确认与分级选材。数据库仍使用 `.backlot/material-library/library.sqlite3`（可由 `OPENMONTAGE_MATERIAL_LIBRARY_DIR` 指定），新能力只加附表，原片保留原位置。

## 使用原则

- MAT-ID 来自完整文件 SHA256。相同文件可有多个位置和来源；竖屏适配、裁切或转码后的文件拥有自己的 MAT-ID，不能伪装成原片。
- 标签、集合和备注是管理信息；它们不会产生画面确认。归档影响新管理检索和新引用，已冻结引用仍可查、可解析；旧模板接口保持原行为。
- 健康状态附带检测时间。未检查不等于有效；实际使用通过完整哈希核验。重新定位只接收同 SHA 的文件。
- 通用观察描述原片事实；`source-content` 不等于某个成片画幅审核通过。旧 `template-band-v1` 证据仍限定中央裁切区域。
- 所有时间区间使用原片秒数、半开区间 `[source_in, source_out)`，不限定片段数量或三秒长度。
- 引用和观察按内容寻址、不可变。更改观察生成新版本；旧项目仍引用原版本。使用记录按项目版本和场景槽位幂等，换素材应创建新项目版本。
- 本模块不调用 AI、TTS、ASR，不负责脚本、叙事顺序或渲染。第三模板可以直接消费本合同，不依赖其内部实现。

## 管理 API

统一前缀 `/api/material-library/manage`。输入错误返回 422；revision 或不可变身份冲突返回 409，客户端须刷新后人工决定，不能无条件重试覆盖。

| 方法与路径 | 输入/用途 |
|---|---|
| GET `/status` | 全库素材、不同源区间、审核版本、归档数量 |
| GET `/search` | query/tag/collection/platform/aspect/review_status/health/archived/min_duration/max_duration/page/page_size |
| GET `/media/{id}` | 元数据、来源、位置健康、旧证据、通用观察、使用记录 |
| POST `/metadata` | 原子批量修改；每条必须携带读取时的 revision |
| POST `/media/{id}/health` | 检查该素材的所有已登记位置 |
| POST `/media/{id}/relink` | `{ "path": "新位置" }`；完整哈希必须一致 |

search 返回 `{items,total,page,page_size,summary}`；每项含 `metadata`、`counts`、`health`。`metadata` 初始 revision=0。`counts.intervals` 与 `review_versions` 分开统计。`health.status` 为 valid/missing/changed/error/unchecked，有有效副本时总体 valid，但仍列出坏副本。`archived` 筛选为 active（默认）/archived/all；aspect 为 all/portrait/landscape/square；review_status 为 all/candidate/confirmed/unreviewed。

管理字段为替换语义：

```json
{
  "items": [{"media_id": "MAT-完整哈希", "expected_revision": 0}],
  "patch": {"tags": ["现场互动"], "collections": ["粤仔"], "notes": "保留原声", "archived": false}
}
```

没有包含的字段保持原值；任一 revision 冲突，整批不写入。

## 项目接入与引用合同

POST `/project-import` 接受显式清单，整批验证源文件和身份后登记；不自动扫描项目：

```json
{
  "project_id": "demo",
  "project_version": "v1",
  "sources": [{
    "asset_id": "SRC-001",
    "path": "D:/素材/source.mp4",
    "expected_sha256": "完整哈希",
    "metadata": {"platform": "local", "rights_status": "unknown"},
    "aliases": [{"namespace": "published-clips", "external_id": "已有索引ID"}]
  }]
}
```

自动建立 `namespace=project:{URL编码的project_id}:{URL编码的project_version}` / `external_id=asset_id` 映射（普通连字符 ID 无变化）。GET `/aliases?namespace=...&external_id=...` 查询；旧外部 ID 不改名，不取代 MAT-ID。

POST `/observations` 登记观察，GET `/observations?media_id=...` 查询。字段：`media_id,source_in,source_out,observation,facts,review_status,scope,reviewer,evidence`。facts 可记录 `text,source_audio,subtitles`；candidate 不表示审核通过。confirmed 要求非空审核者及可读取、哈希吻合的 `evidence:[{path,sha256}]`。本服务校验证据完整性，内容判断仍由记录的审核者负责。

POST `/references` 冻结：

```json
{
  "media_id": "MAT-完整哈希",
  "source_in": 12.5,
  "source_out": 48.2,
  "usage_intent": "直播问答，保留原声",
  "scope": "source-content",
  "observation_id": "MOBS-观察ID"
}
```

观察可省略，表示尚无通用观察；旧片段可传 `legacy_clip_id` 并明确匹配其 scope。有证据时引用区间必须落在证据覆盖范围。返回冻结对象包含 `id`、源 SHA、时间区间、证据快照；GET `/references/{id}` 读取，GET `/references/{id}/resolve` 核验并返回当前有效路径。消费方应保存冻结对象和 ID，渲染前调用 resolve；不能只保存易失效的绝对路径。

POST `/usage`：

```json
{
  "project_id": "demo", "project_version": "v1", "asset_id": "SRC-001",
  "scene_id": "answer", "slot_id": "shot-1", "ref_id": "MREF-引用ID"
}
```

GET `/usage?media_id=...` 从素材反查项目；GET `/usage?project_id=...` 从项目查来源。相同使用键同一引用重复提交返回原记录，换引用返回 409；旧版本不会静默改变。

使用键是 `(project_id,project_version,scene_id,slot_id)`，更换 asset_id 也不能绕过版本保护。若项目素材是衍生文件，额外传 `source_asset_id` 指向同项目版本内已登记的原片，`asset_id` 仍指向真实衍生文件；双方必须已登记，source_asset_id 必须与引用原片一致。返回 `project_asset_media_id` 与 `media_id` 分别标识衍生文件和原片，用任一身份都能反查使用台账。这条关系不自动证明裁切或时间映射，消费方仍须保存其实际变换/剪辑计划依据。

粤仔实际接入样例保存在 `projects/yuezai-friends-codex-pilot-20261003/artifacts/material-library/source-usage-manifest-v1.json`，包含两原片、两衍生文件和九条用镜头关系。导入的计划观察保持 candidate，不充当新的画面确认。

## Codex / CLI

使用项目虚拟环境运行 `scripts/material_library_manage_cli.py`。通用选项 `--db`、`--output` 放在子命令前。

```text
python scripts/material_library_manage_cli.py search --query 粤仔 --page-size 24
python scripts/material_library_manage_cli.py detail MAT-完整哈希
python scripts/material_library_manage_cli.py metadata metadata.json
python scripts/material_library_manage_cli.py import-project source-manifest.json
python scripts/material_library_manage_cli.py observe observation.json
python scripts/material_library_manage_cli.py reference reference.json
python scripts/material_library_manage_cli.py usage usage.json
python scripts/material_library_manage_cli.py usage-query --project-id demo
python scripts/material_library_manage_cli.py resolve MREF-引用ID
```

退出码：0 成功，1 输入/文件校验失败，3 身份或 revision 冲突。文件 JSON 和 HTTP 输入合同一致。

## 开发和回归

实现：`backlot/material_library_management.py`、`material_library_refs.py`、`material_library_manage_api.py`；界面：`backlot/ui/material_library_manage.*`。仅由原素材库 router 挂接，不要求修改第三模板或生产队列。

验收指导：`docs/development/2026-10-03-通用素材管理V1.1-单次开发指导文档.md`。运行新增三个测试模块和原 `tests/backlot/test_material_library.py`。本模块合同通过不代表第三模板已完成成片联调。

本次保留正在使用的工作台服务，另以 `http://127.0.0.1:8876/material-library/manage` 提供同一真实库的独立验收入口；无队列/生产 worker。原工作台下次正常重启后，原端口的同一路径生效。验收启动脚本及日志在 `.backlot/material-library-v11-acceptance-20261003/`，不是新生产入口或额外数据库。
