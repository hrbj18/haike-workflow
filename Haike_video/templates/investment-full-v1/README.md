# 招商完整样片 · investment-full-v1

视觉参数与跨电脑复刻请先读[视觉Runbook入口](visual-runbooks/README.md)：07蓝米、08青炭v002、09黑粉各有独立说明、参数表与同版本源码快照。此交接包不含完整运行环境或私人素材，尚未完成另一台物理电脑验证。

三套独立完整片合同：30秒、4x5、1440×1800、30fps、900帧，数字人口播 + 本地实拍/图片 + 来源绑定图文 + BGM/动态音效。implementation + ready仅绑定本期三条round4冻结输入与同SHA成片；原生开发样片质量保持待审、未发布。

08青炭新增[显式45秒扩展](variants/08/45秒扩展.md)：仅本期EDL声明1350帧时启用，默认30秒和旧样片证据保持原范围；45秒完整输出独立验收。

- [07 蓝米剧场](variants/07/招商完整样片07-蓝米.md)：investment-full-07-blue-beige。
- [08 青炭折面](variants/08/招商完整样片08-青炭.md)：investment-full-08-cyan-charcoal。
- [09 黑粉字阵](variants/09/招商完整样片09-黑粉.md)：investment-full-09-black-pink。

数字/布局真值：[layout.json](layout.json)、[geometry.ts](geometry.ts)、[Full.tsx](Full.tsx)、[Shared.tsx](Shared.tsx)、[Graphics.tsx](Graphics.tsx)；颜色：[palettes.ts](palettes.ts)。Composition为HaikeInvestmentFull；新输入/原片/EDL/分镜/素材/音频或其他画幅必须新prepare并重验，不能继承本次通过。

操作入口：[scripts/investment_full.py](../../scripts/investment_full.py)。核对14756工作区与真实输入，prepare→submit(paused)→全局单lane run；已有任务先status，retryable按原目录resume。本次文档补证没有改动任何冻结request、prepare时规格快照或原生作品。

原MP4原字节导入，真实cue与原声画按同一AV EDL原速剪接；不足一帧的被删邻cue边缘只按真实ASR交集样本mask并留回执。素材全部静音、完整contain，单次最长4秒、来源标签独立。尾卡仅offer图文、静音人声与BGM淡出，人物不冻结或循环；图文不新增收益/限量承诺。

统一H26420M ABR目标、CRF null、PNG、slow、yuv420p、scale1、最终视频stream-copy；实际码率与母带/AAC指标记录在本轮同SHA技术报告，不用参数替代实测。

## 本期限定样片验证矩阵

| 维度 | 状态 | 本期范围 |
| --- | --- | --- |
| 结构 / 技术 | pass | 本条同SHA原生30秒成片、900帧、4:5、原片/EDL/字幕/素材、完整解码及实际音频测量 |
| 实际视觉 | pass（限定抽样） | Root实际查看同输出SHA的章节/素材/字幕/边界帧；精确帧号与范围见visual-review及frame manifest，未声称逐帧看完 |
| 原生接入 / 本地交付 | pass | queue/project/work/version、完整HTTP字节SHA、Range及桌面浏览器播放证据 |
| 主观连续听审 | pending | BGM/SFX、真实duck母线、母带/AAC峰值完成技术验证；不等于主观听感或逐音素口型验证 |
| 手机 / 目标平台 | pending | 桌面浏览器已验，未外推手机或目标平台 |
| 用户成片审美确认 | pending | 授权制作不等于认可成片 |
| 作品质量 / 发布 | 待审 / 未发布 | 保持原生开发样片状态；本脚本不确认、不设置final版本、不发布 |

请求和输出完整SHA、原生ID、执行runtime、原始源/EDL/分镜身份、实际帧manifest、Root查看范围与音频技术测量均在各spec所引用的私有spec-evidence汇总；旧12秒及前面仅prepared的请求未作为本期通过证据。

| 样片 | request SHA前12位 | output SHA前12位 |
| --- | --- | --- |
| 07 蓝米剧场 | `22d64bdcec6f` | `cbd964a381d6` |
| 08 青炭折面 | `62c5d96fd92a` | `8e77117bef32` |
| 09 黑粉字阵 | `6a4d7a0929c7` | `21e1b389ccc8` |

## 08可选实拍信息侧栏

2026-10-21新增实现：仅模板8／cyan-charcoal的media章节在`chapter.points`非空时启用。既有media外框保持1240×956；完整9:16来源在右侧537.75×956子框contain，右边距24，左侧信息框局部坐标36/100、宽570。deck使用46px／1.5行高、最多两行；支持信息至多两条，48px／1.45行高，青色细线分隔。文字与图片不重叠，来源标签、章节标题、字幕与人物不变；未启用章节及07／09沿用原布局。

几何与文字上界检查在`geometry.ts`，实际DOM对象在`Shared.tsx`，审查标记为`media-portrait-right`、`media-info-sidebar`、`media-info-deck`和`media-info-point`。这是新输入可选分支，不修改旧冻结request或扩大上表旧ready证据。新输入须重新prepare并完成实际预览／成片检查；静态几何通过不替代真实字形或画面验收。
