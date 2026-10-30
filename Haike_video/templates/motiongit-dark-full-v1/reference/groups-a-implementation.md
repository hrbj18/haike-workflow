# s01–s04 可编辑组件说明

文档类型：implementation。2026-10-28。对应 `GroupsA.tsx`，不代替最终成片验收。

## 覆盖范围

| 组 | 已实现的连续状态 | 媒体时钟 |
| --- | --- | --- |
| s01 | 紫蓝渐变/细网格 → 两级大字与 STAGE 02 → 可编辑时间线 → 划除 → 黑底密集作品墙从纵深升起 → 两句主张 → 双色结论 | 墙使用封面，避免数百路视频同时解码；人物由全局层管理 |
| s02 | 九格阶梯入场 → B/A 分组与对应高亮 → 四个版本胶囊阶梯出现 → 九格逐一勾选 → 指标说明 → 滑块 → 数字滚动 → 次卡为中央卡让位 | 仅中央第5格绑定 `mainMedia` 的 live 窗口，其余封面 |
| s03 | 同一中央主卡推进到大框 → 聚焦/细节砸字 → 参考/方案并排 → 主卡回左/检查区建立 → 计时环 → 扫描线 → 三条说明 → 精度结论 → 副作品 | 主卡只保留一个 `Material` 节点，变换几何位置；跨 s02/s03 的源偏移交给 backend 的连续窗口 |
| s04 | 纸白底分词标题 → 四类素材卡依次展开 → 密集墙 → 单行/双色结论 → 回纸白反模板划除 → 主卡接镜头框 → 推进/跟拍/特写标签与辅助框 → 起承转合曲线 | 主素材节点从第一卡保留到镜头框，隐藏阶段也不重新挂载；镜头动作改变辅助图形，素材保持 contain |

原片全部关键 cue 均通过 `cue()` 读取；可在 `Scene.cueTimes` 覆盖局部启动时刻。单次入场、位移、划线和缓动使用固定秒数，没有按口播长度整体缩放。媒体解码始终使用 `Scene.videoWindows`，素材保持 contain，不重复挂载多路 live 视频。

竖版不是缩小横版：1440×1800 下九格重新分布到 y500–1319；分类卡改2×2；审阅说明横排于主画面下；镜头与叙事曲线纵向接力。全局品牌、人物、字幕、地址由 `index.tsx` 负责，组件未重复绘制。

## 内容字段

字段均在 `Scene.content`，纯文字保持 React 活字。以下长度是当前字号的建议门限，最终仍需浏览器排版检查。

| 组 | 字段 | 建议约束 |
| --- | --- | --- |
| s01 | `kicker`, `headlineFirst`, `headlineConnector`, `headlineAccent`, `timelineTitle`, `wallMeta`, `statementFirst`, `statementSecond`, `payoffFirst`, `payoffAccent` | 大标题整行约≤9字；两句主张各≤10字；payoff合计约≤8字；kicker≤24字 |
| s02 | `heading`, `headingNote`, `labels[]`, `groups[]`, `versions[]`, `itemNote`, `coverageLabel`, `qualityLabel`, `metricLabel`, `countValue`, `countLabel`，参考计数控制见下文 | labels9项、groups2项、versions4项；label≤6字、版本≤4字；`countValue` 是数字。海客默认数字为9格画面，不能改成无依据的客流/营收数据 |
| s03 | `heading`, `focusFirst`, `focusAccent`, `comparisonHeading`, `comparisonLabels[]`, `reviewTitle`, `reviewTimer`, `reviewTimerNote`, `reviewLabels[]`, `reviewComplete`, `precisionFirst`, `precisionAccent`, `previousLabel` | 比较标签2项、审阅说明3项且每项≤6字；大词各≤4字；计时环为可改的原片示意，不意味着真实耗时 |
| s04 | `scopePrefix`, `scopeSubject`, `scopeAccent`, `scopeConclusion`, `categories[]`, `categoryNotes[]`, `wallFirst`, `wallSecond`, `wallAccent`, `wallMeta`, `wallBadge`, `templateLine`, `templateChip`, `cameraPrefix`, `cameraTitle`, `cameraLabels[]`, `rhythmPrefix`, `rhythmTitle`, `rhythmParts[]` | categories/notes各4项、cameraLabels3项、rhythmParts4项；分类≤6字、说明≤8字；长标题需另分词。镜头名称由内容选择，不固定沿用技术词 |

默认 reference 文案依据本次实际可见原片，而非公开 guide 中较旧的 `sourceText`。原片作品墙出现389个/27个的示例计数；项目默认改为“可编辑示意素材墙 / 素材与文字均可替换”，以免把重新生成的封面数量或海客客流写成389。官方 native 还原可以通过公开参数恢复原演示文案。

### S02 参考计数与单位费用

2026-10-28 补正：横版 `reference` 的计数面板位于1920×1080的 `(1378,760,450,174)`，从公开 `cost` cue（源23.8秒）开始。`Scene.content` 默认值为 `countValue:240`、`counterSeconds:1.7`、`countPower:1.6`、`unitCost:0.1`、`countLabel:"示意计数"`、`costLabel:"单位"`、`costPrefix:"$"`。局部归一化进度取 `clamp((seconds-costCue)/counterSeconds)`，原始量为 `countValue*progress**countPower`。大数字四舍五入到整数，费用从**未取整的原始量**乘以 `unitCost` 后保留两位小数；因此源25.0秒是137与$13.75，25.35秒是207与$20.70，25.6秒已到240与$24.00并淡出。

`alertThreshold:120`、`alertColor:"#EF4444"`、`countColor`（默认主文字色）控制颜色。源24.900秒120仍白，24.9167秒123已红；120是匹配这两观察帧的视觉等价值，不声称取得作者隐藏阈值。`counterFadeDelay:1.45`、`counterFadeSeconds:0.45` 为相对cost cue的淡出延迟/时长；淡出与模糊拟合25.35可读、25.6淡出这两个观察锚点，公开契约没有提供原作者退出曲线。数字采用通用等宽字栈，未声称原字体精确恢复。上述项目控制字段不扩大原包公开API能力。

`hedgerow`/`cobalt` 继续以9“格画面”为过程事实，横/竖版均不绘制单位费用行。口播时长只映射cue起点，计数动作时长仍由 `counterSeconds` 控制；四格媒体、九格接力和s02→s03主卡连续策略没有改变。本轮未修改s01、s03或s04。

实际核验资料位于本机 `C:/Users/Administrator/Documents/HaikeCache/motion-full-20261028/s02-counter-qa/`：5张参考计数帧（24.9、24.9167、25.0、25.35、25.6秒）、2张社交4:5默认帧，以及原片/重建同坐标对照板。均为限定时刻媒体渲染；没有浏览器工作台视觉自动化验收。`change-scope.json` 对照修改前副本确认其他三个组逐段相同。

## 时长门禁建议

公开 `minFrames` 描述官方运行契约，不能直接当作本组件在任意文本下的可读性证明。

- s01：最后 payoff 启动后至少保留0.42秒完成动作，另留约0.35秒安静停留；长主张需要更多停留。
- s02：四个版本0.36秒间隔、各0.32秒入场；最后一个完成后再开启下一大段。9格勾选总约0.64秒；指标与数字不能同一帧出现即离开。s02必须接s03，主素材使用同一源和连续偏移。
- s03：初次同卡放大需要1.1秒；比较板0.65秒，检查区0.7秒；每条说明入场0.38秒后留阅读区；末尾副作品出现后至少0.5秒完成动作。不能为压缩总长重播主素材或把整组快放。
- s04：第4卡入场0.4秒。原始 `category_4→wall_expand` 只有0.45秒，若线性映射为官方最短7.63秒，会只剩约0.28秒；此时需用 `cueTimes` 保护末卡完成，或给该组约11.5–12.3秒。镜头框至少0.55秒、叙事曲线至少0.65秒完成；曲线4个点须全部出现，不能在曲线半途切走。

完整状态覆盖与口播语义同时优先。30秒成片可把时长分给3组完整动作；不要为了凑4组裁掉组内后半段。

## 实际检查

私有 QA 根：`.local/motion-full-20261028/reference/project-a-qa/`。`render.cjs` 使用真实 Remotion 浏览器，对组件固定局部时钟采样；15个横版1920×1080状态、6个竖版1440×1800状态已生成并实际查看。涵盖s01墙前后、s02九格/分组/指标、s03推进/比较/审阅、s04四卡/墙/反模板/镜头曲线。`qa-metadata.json` 记录各图尺寸与时刻。Cobalt的墙增加纸白层以保证深色标题可读；竖版镜头标题在y240、主框在y470–1168、叙事图在y1230–1375，字幕区保持空出。

本次几何 QA 使用本机 Microsoft YaHei 的显式字体 fallback，没有据此声明原片字体。所有素材槽为空时由明确标记的可编辑 `Study` 图形占位；这证明排版与动作状态，不证明真实素材匹配、连续听音、数字人口型或最终编码成片通过。正式字体、真实素材、配乐音效与人物的联合 QA 仍由总流程验收。

组件经独立复制到 composer 子目录后通过 strict TypeScript 检查。未修改 shared/types/index/backend。首次 QA 脚本浏览器关闭参数错误发生在20张静帧全部生成后；已修正并重跑成功，最终 QA 元数据对应成功运行。
