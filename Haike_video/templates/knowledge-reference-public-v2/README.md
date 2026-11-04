# 纸笔与粉笔：公开参考实现 v2 候选

文档类型：video-template-runbook；标准：video-template-v1。

规格：[纸笔](paper.spec.json)、[粉笔](chalk.spec.json)。身份为 `knowledge-reference-public-v2 / 5.1.0-independent.1`，生产契约为 `haike.knowledge-reference-public/2`，动作命名空间为 `haike.public-knowledge-v2.*`。当前为 `implementation + specification`：静态、几何和隔离队列门槛已有验证；v2 实际画面、全片、听审和异机仍待验。注册草案不等于已接线，也不表示 ready。

v1 的三份真实预览共 341 张图均为 `changes_requested`。本版本保留其源码、父请求、图片及审核，另建输入与项目；只定向复验原失败状态。B6 原全文、字幕时码、分段边界和完整音频字节不变。科学机制是单独静音 `previewOnly` 开发示例，不能强套到 B6 门店稿，也不能正式输出。

## 身份、来源与参数

卡片身份继承现有目录：纸笔 `motion-package-mg-178e6870ae932019c6bf2fe9`，粉笔 `motion-package-mg-5b31b7dd6e6709861dc6ac88`。模板 ID 分别为 `knowledge-explainer-sketchnote`、`knowledge-explainer-chalkboard`，不能代替 gallery ID。新增版本不覆盖旧冻结。

观察来源是官方公开 gallery 的 12 张纸笔、24 张粉笔图片及合法现存原生预览。所有纹理、笔、形状、镜头和绘制代码独立编写；不读取受保护实现，不把原截图、材质、原笔或图标包放进渲染器。源码遵循仓库许可，字体单独遵循附带的 OFL；不授予原个人包再分发权。

参数真值分工如下，规格不再复制一套参数：

| 入口 | 持有的规则 |
| --- | --- |
| `geometry.json` | 单/多对象纸页范围、对焦、网格、灯泡轮廓、科学视图位置与射线默认实例 |
| `drawing.ts`、`backgrounds.ts` | 真实字体、逐字揭示、原创向量笔/便签/图形、确定种子点阵与擦拭材质 |
| `paper.ts` | 持久对象 ID、焦点与总览、独立绘制、修订、明确端点回看；两对象虚线、更多对象局部回环 |
| `geometry.ts`、`chalk.ts` | 四类真实模型、同一三维状态投影、圆交集遮挡、最近射线交点、独立条件判断；稀疏通用五布局 |
| `types.ts`、`motion_knowledge_public_execution_v2.py` | 开放输入形状、精确家族字段/事件、实际字体测宽与完整主时钟校验 |
| `motion_knowledge_public_production_v2.py` | 冻结身份、定向抽帧、领取/租约/取消/批准绑定、原父幂等与恢复 |

只开放文本、对象 ID、有限模型参数及绝对帧事件。纸笔每对象独立 `camera/write/highlight/draw/annotation`；总览、结论、关系、修订和回看独立控制。通用粉笔独立控制 heading/item/answer/connection/tab/note；科学模型逐家族拒绝未消费字段，surface-view 和 shadow-overlap 使用 inspect，三条件分别使用自己的揭示事件。模型表见粉笔规格扩展。动作时间是基于可见状态的独立近似，不是原包参数导出。

v2 修订单对象总览、灯泡上轮廓/上扇射线/透纸填色、纸页网格、回看虚线、字体层级与粉笔擦拭分布。科学表面视图放大同一对象并缩小原系统，保留下方相位；遮挡为放大的独立截面；因果为上下两个条件；投影使用同一三维位置；射线命中真实最近遮板。模型单位尚未标定为原物理厘米，字体版本及未观察的中间镜头时序仍存在差异，不能声称逐像素或原演出一致。

字体是本目录实资源。`font-provenance.json` 记录上游固定身份和完整许可；Long Cang、Fraunces、JetBrains Mono 与公开声明摘要一致。霞鹜文楷完整 Medium TTF 与参考 500 WOFF 的字节/版本不同，实际字距不得据家族名推定相同。离线渲染不回退系统字体，不安装/更新共享依赖。

## 输入到冻结

输入是私有 `.local` 下的 `public/episode.json`、完整原声/可选授权音乐、公开字体、`preparation.json`、`production.json`，项目预先通过既有 checkpoint 初始化。准备清单绑定批准稿件、真实 ASR 句证据和同一声音 SHA。默认无人，不开放人物、照片、B-roll。超宽标签拒绝并显式拆分画面文字，不能删原声/字幕或静默缩字。完整医疗边界在最后实际 note/conclusion 中校验；没有额外常驻底部说明层。

调用 `backlot.motion_knowledge_public_production_v2.prepare(queue,{data})` 得到冻结父请求，不入队、不调用媒体或供应商。公共只读适配器是 `backlot.motion_knowledge_public_execution_v2.prepare`。冻结绑定全部本版本源码、规格、字体、依赖锁、私有输入及运行时 SHA。定向修订另外绑定 v1 原父与实际 changes_requested 审核，限定每组不超过 96 帧、原分段与声音不变。缺运行组件直接阻断，不安装或替换。

## 公共阶段与恢复

1. **preview**：总控登记固定允许列表与路由后，通过 `Haike_video/scripts/motion_replay_production.py submit --request <冻结JSON> --phase preview`，再对原编号 `execute --job-id <原编号> --confirmed`。沿全局单道执行；禁止直接调用本目录 render.cjs。v2 定向清单为纸笔 20、粉笔 16、科学 36 帧，目标是修订失败状态。
2. **review**：仅接受同身份已完成父、完整真实 PNG/回执、实际查看声明、观察及明确 `approve|reject|changes_requested`。完整性验证不代表保真；拒绝和要求修改不授权成片。预览重复提交复用原父，缺产物返回完整性修复信息，不自动重画。
3. **render**：只有当前明确批准才能入队，并冻结具体预览/每张图片/审核 SHA。公共执行在真正领取前调用只读 `validate_claim(queue,job_id)`；未批准/撤回/取消时原父保持未领取。领取后核对 running 状态、完整冻结、worker、attempt 与实时租约，媒体前、主导出返回后和最终音频导出后再核批准/取消。失败不能写 QA/作品成功。previewOnly 禁止本阶段。
4. **交付**：1080×1920、60fps、目标视频至少 20Mbps、完整原速音轨及真实 ASR 字幕；实际解码、画面对照、混音和连续听看分别验收。队列完成不提升未验维度。本版本尚未完成真实 preview/render。

每阶段复用稳定幂等键；换审核意见不能新建旧阶段父。源码/输入变化会使旧冻结失效。修复缺失产物需恢复原精确字节，或显式建立新 revision 的 data/project 后重新准备，保留旧候选及原编号。批准撤回、取消及租约失效保留已完成产物，从明确本地失败点恢复，不重复购买原声或 ASR。公开返回脱敏；看图和审核只用私有原清单，不能依赖公开路径字段。

## 验证边界

43 项 Python 几何/真实隔离 SQLite 阶段测试通过；外部媒体进程在阶段测试中替身，不是画面证据。TypeScript 严格无输出检查使用已有 Remotion 4.0.506 与真实 DOM/JSON 模块类型，不升级安装。规格静态检查只证明可检查约束。本候选仍需公共接线后的定向真实图片、逐失败状态视觉判断、获准后的完整渲染及适用听看/环境验证，未通过前维持 specification。
