# 纸笔与粉笔 v3：已定位画面缺陷候选

文档类型：video-template-runbook。
标准版本：video-template-v1。
模板规格：[纸笔](paper.spec.json)、[粉笔](chalk.spec.json)。

独立身份 `knowledge-reference-public-v3 / 5.1.1-independent.1`，生产契约 `haike.knowledge-reference-public/3`，动作前缀 `haike.public-knowledge-v3.*`。当前 `implementation + specification`：源码/输入/静态/隔离阶段门槛已检查，**尚无本版本实际图片，不是 ready 或完整复刻交付**。总控负责新公共登记/路由，静态检查不授予媒体执行；不直接调用 render.cjs。

本候选只修已在 v2 的 72 张定向帧中实际定位、经总控复核的灯泡轮廓、绿板材质和便签内容锐利重影。保留 v1/v2 注册源、原父、图片及明确审核，新建自身源码与输入。没有读取受保护核心、复制原背景/笔/图标图片、安装依赖或新付费调用；独立程序纹理不要求与原私有尘点像素一致。

## 修订范围与真值

| 入口 | 本版改动与不变范围 |
| --- | --- |
| `geometry.json`、`drawing.ts` | 既有灯泡锚点经独立三次插值细分，保留端点、逐弧长揭示和原事件窗口，单独细化灯泡线宽；便签纸投影后清空阴影全部状态，文字和胶带不继承偏移重影 |
| `geometry.json`、`backgrounds.ts` | 原创绿板色调、真实像素尺度确定性细粒、交错纵向/弧形/短横向擦拭；不使用截图或原材质，不用宽暗横条代替纹理 |
| `paper.ts`、`chalk.ts`、`geometry.ts` | 保留 v2 已实际出现的页/便签/镜头/稀疏正文几何和四类科学模型，不重做版式或引擎；科学单位继续诚实标模型单位 |
| `types.ts`、执行/生产模块 | 仅新身份与受控定向计划变化；完整原文、声音、字幕时码、所有场景/事件/模型内容须与原 v2 父逐字段相同 |

参数真值由上述源及几何 JSON 持有；规格引用入口，不复制参数表。开放内容仍由 episode 和 `motion_knowledge_public_execution_v3.validate_episode` 限定。默认无人，不开放图片/B-roll。B6 完整医疗边界保留在末段实际 note/conclusion，字幕来自同一真实 ASR，完整原声原速，不裁切、拉伸或重买。字体仍为相同四份真实 OFL 文件与完整许可；WenKai TTF/原 WOFF 的版本差异如实保留，不要求伪称相同字节。

原卡片身份不变：纸笔 `motion-package-mg-178e6870ae932019c6bf2fe9`、粉笔 `motion-package-mg-5b31b7dd6e6709861dc6ac88`。模板 ID 为 `knowledge-explainer-sketchnote`、`knowledge-explainer-chalkboard`，不能混用。

## 输入、阶段与恢复

1. **准备**：私有 data 包含 episode、preparation、production、同 SHA 原声/音乐/字体及授权稿件/句证据。初始化独立 project 后，`backlot.motion_knowledge_public_production_v3.prepare(queue,{data})` 只冻结当前源码/规格/字体/依赖锁/输入/运行时，不入队。只读适配为 `backlot.motion_knowledge_public_execution_v3.prepare`。缺运行组件阻断，不安装或换版本。
2. **限定复验**：targeted-revision/2 绑定原 v2 父和实际 changes_requested 审核。除了三项身份元数据，episode 全部字段、所有对象/模型/事件必须相同；声音/音乐字节也须与原冻结相同。只允许 paper.bulb-smoothing + paper.sticky-shadow 或 chalk.material，不再强制遍历所有场景。纸笔6帧、粉笔2帧仅复核已定位状态，不能开第三轮泛审。科学功能沿用 v2 正确采样机制；没有新科学输入，不因未观察原中间参数而永久阻断它，也不伪称原物理厘米已标定。
3. **公共执行**：总控新增固定允许表/registry 并交接媒体时段后，使用 `Haike_video/scripts/motion_replay_production.py submit --request <冻结JSON> --phase preview`，再 `execute --job-id <原编号> --confirmed`。沿原父和全局单道；未接线不运行 private handler/renderer。
4. **审核**：完整实际 PNG/回执、逐项身份/尺寸/可解码性、实际查看声明、观察和 `approve|reject|changes_requested` 缺一不可。定向审核结合未改的 v2 已看机制证据，不能将微差扩大成原私有像素硬门槛，也不能以静态测试替代实际缺陷复验。
5. **整片**：只在当前明确批准后入队 render，冻结具体原预览/全部图/审核 SHA。公共 execute 先 `validate_claim(queue,job_id)` 再真领取；run 核完整冻结、running/worker/attempt/实时租约/取消，并在媒体前、主导出后及最终音频/封面后再核批准，变化不记 QA/作品成功。保持 v2 已验证阶段门槛，科学 previewOnly 永不完整输出。
6. **交付与恢复**：1080×1920/60fps，目标视频至少20Mbps，原完整原速音轨和字幕；实际解码、视觉、混音、连续听看及目标环境分别记录。稳定阶段键复用原父；完整性损坏恢复原字节或显式新 revision，不静默重画、不因新审核建第二父。源码或输入变化使旧冻结失效，保留旧版本不就地改 SHA。

## 验证边界

继承门槛的43项真实隔离 Python 测试、7模块严格 TypeScript 和实际 TS 几何/曲线/Canvas状态记录测试用于代码验证。阴影测试用记录型上下文证明纸投影存在而胶带/字形无偏移，不是图片或保真证明。绿板材质、平滑主轮廓和无重影必须在获准后的8张真实目标图中实际查看。未执行媒体、听看、整片和异机的维度保持 pending；独立笔图、网格的允许微差不新增修订范围。
