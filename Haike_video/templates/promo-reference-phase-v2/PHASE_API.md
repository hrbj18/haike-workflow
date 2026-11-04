# Promo阶段控制v2候选

新合同`haike.promo-reference-full/2`；固定module为`backlot.studio_promo_phase_v2`，KIND仍为`studio_investment_recompose`。root负责公共prepare/queue/worker/registry固定接线，本候选不改原v1任何源码、请求或产物。

新登记精确版本`3.0.0-reference-public.2`，template_id保留`motiongit-promo-user`，canonical gallery_id从原imported.json/2.6.4读取并固定为`motion-package-mg-8d3e5baeef9310e4b49b41de`。不从临时v1展示sidecar猜ID；展示元数据不进入props、声音或renderer字节。root的登记草案见私有`B/phase-v2/REGISTRY_CANDIDATE.json`，尚未接入公共registry。

## 继承范围与验收

`INHERITANCE.json`绑定C最终SOURCE_FROZEN及六份原字节文件（Board/index/types/render/README/LICENSE）；`upstream-producer.py`是仅供源码溯源的C原字节副本，不被import或执行。当前目录README也是同字节上游说明；阶段契约以本文件为准。

preflight/toolchain/bound的AST与C冻结实现一致；用C最终v003真实输入核对props、完整声音计划、主钟、reference、来源回执、evidence全部一致。assets映射、renderer命令、duration、FFmpeg export表达式与mix_master调用也按AST核对一致。preview_revision不进入任何画面props或声音公式。没有读取保护核心。

这证明阶段控制继承的源码与输入公式；未实际调用v2 renderer，不代表v2出片、视觉/听觉、跨机及完整可安装依赖闭包已验收。源码校验失败不会豁免旧SHA。

## 固定接口

| 入口 | 输入、行为与返回 |
| --- | --- |
| `prepare_contract(template,request,workspace=...)` | 新只读adapter：要求上述精确版本/canonical ID/workflow `promo-reference-phase-v2`，返回固定v2 consumer。只做完整输入预检，不建项目/入队/渲染。缺input返回blocked。 |
| `prepare(queue,value)` | 同C v1开放制作输入；preflight→严格runtime→冻结新v2项目/资产。返回无phase的原冻结request；不入队、不渲染、不付费。 |
| `validate(queue,r,execution=True)` | 验证request/原记录、资产和执行源码/工具SHA，返回`(project,folder)`。`execution=False`仅供只读health分开检查缓存；submit/run不使用它绕过执行门禁。 |
| `submit(queue,r,phase='preview')` | preview键仅CONTRACT+request SHA+phase。render要求唯一completed preview父、真实图片/回执和当前review，冻结具体review_binding。返回标准公开queue job加`availability`，不清取消/失败/未知状态，不执行。 |
| `review(queue,r,evidence)` | evidence为`preview_sha256`、`inspected_images`（完整有序`name/sha256`列表）、非空`reviewer`及可选note；要求原preview父completed。所有PNG可解码且SHA完整。保存具体binding，元数据不参与render身份。 |
| `run(queue,job)` | 仅真实claimed/running父可执行，取消请求阻断；重新验证源与render binding。已有健康缓存只读复用；不完整/未知现场保留且失败，不覆盖重渲。新render只在空输出空间运行。 |
| `health(queue,r)` | 只读返回`frozen_inputs`、`execution`、`preview`、`review`、`output`各自状态。output实际核MP4/quality完整SHA、请求/props/review身份；preview图片缺失不自动否定一个已核对的最终缓存，执行依赖不齐也不冒称缓存丢失。 |
| `new_preview_revision(queue,r,reason=...,confirmed=True)` | 显式新后端revision、新项目/输出空间，链接previous_request_sha256、复制同SHA资产、props/audio不变；原父/现场/成片/审核保留。新revision须重新preview与review。不入队或执行。 |

阶段父查找不使用公开列表上限；同完整payload有多个旧父时明确报歧义。真实queue稳定key与SQLite事务保证并发同身份只入一个父，返回前再核frozen内容，不能用碰撞的已有key返回另一个payload。

## 状态与恢复

- completed只是历史状态。缺预览显示availability缺失/损坏，原父不转failed、不自动重做；用户明确重做时新revision，不复活completed父。
- failed/ambiguous/cancelled原父按原状态返回；不能改review元数据绕过去。render不跨过失败、未知或取消的preview父。当前新run对无法明确安全恢复的现场返回非重试失败，保留safe_resume_point，后续显式revision；不会自动调用供应商。
- 缺MP4/result/quality、摘要或审核身份不一致均显示具体output错误。run不以`result.json`存在或queue completed代替文件验证，也不覆盖残缺文件。
- cached输出、预览健康、执行就绪和发布/视听验收分开。调用方应展示availability；公共execute现有completed快路径不能替代本module.health。
- 原v1仍通过原固定路由运行；不可将v1 JSON塞入v2或修改contract后伪造旧身份。root接线需要固定新合同，不接受JSON指定任意module。
