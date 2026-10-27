# 店长账号模板26｜猩红蜜橙·开业邀约 v002

文档类型：video-template-runbook
标准版本：video-template-v1
状态：implementation，v002限定ready；本期当前冻结输入的完整原生成片技术检查及134个最终编码离散帧/9页实际视觉抽样通过并登记。连续听看、平台真机和用户最终确认保持pending。
规格：[video-template-spec.json](video-template-spec.json)
权威：[layout.json](../../layout.json)＋[index.tsx](../../index.tsx) openingLayoutAt，具体空间和文字不在手册另存数值副本。

## 目标与结构

猩红蜜橙·开业邀约。本期状态接力为：announcement → field/wide-pair → offer → invite/wide-pair。状态由当前全片帧、章节、可见源画幅、可选detail和店长区间确定；avatar优先于横片，横片优先于普通实拍状态。

[本期brief](../../../../../.local/codex-runs/store-opening-redesign-20261025/creative-brief.json)和[视觉方向包](../../visual-direction-v002.json)说明参考转译。仅学习双色反转、斜体字组和空间机制；参考图与作者标识不进入成片。

## 输入和受控替换

使用完整已确认配音的真实ASR时钟；本期五条主时钟分别971/858/952/954/885帧，当前编号按实际durationFrames，不定长6秒。props保留style、durationFrames、audio、captions、shots、avatarSegments、chapters、location，并必需fontAssets三固定别名。章节短标题的from沿原配音，当前新文字由任务design-props.json提供。

主轨原速连续全覆盖，每镜及相邻同源连续不超过4秒，无循环、冻结或拉伸。所有源视频静音，唯一master.wav承担声音。人物只使用原批准店长句区间，本期26不含人物。人物画幅独立全4:5；横片只在大宽窗成对使用，不是小PIP。

文字、字体、语义行数、色面、裁切和显隐共同受当前状态约束。字体加载失败阻断渲染；不可使用伪粗、额外skew或系统回退。改长句不得静默缩字号或截断；应修语义分行或构图，并复验。

## 操作与gate

1. 当前草案输入 → 唯一native执行者按proof计划渲染 → 原生PNG/375px联系图与SHA → 真实字体/主时钟/新裁切/文字和人物安全区实际查看；失败修当前范围。
2. 正式新裁切报告与实际proof → 统一adapter prepare/validate新冻结请求 → 输入、字体及运行时全链SHA与已看草案一致 → 作者限定ready并绑定作者/总控回执的full-render gate；旧v001通过不继承。
3. 新冻结请求 → 原生ProductionQueue完整导出 → quality/result/MP4 → 实测视频流≥20Mbps、1440×1800/30fps、帧数/时长、AAC峰值、全解码与最终画面抽查。
4. 完整片 → 连续播放/实际设备与用户反馈 → 分维度记录 → 未做的听看、平台真机和用户确认保持pending。

恢复以当前原编号、原SHA与成功媒体为准；本地版式或裁切重做不重新调用付费配音/人物。实现、字体、数据或几何变化后只复验受影响范围，但正式生产必须新冻结。

## 当前验证

当前v002声明范围和修复见[REVIEW](../../REVIEW.md)，当前冻结身份见本期ready-current.json/render-gate.json及对应编号request.json。完整成片的quality/result、134个实际编码帧/9页回执与WorkCatalog正式采样登记由规格final_v002_*及任务final-spec-evidence.json绑定文件SHA。完整技术与离散样本通过，没有把原生PNG当作完整输出，也没有把抽帧当作连续听看、音素口型、真机或用户确认。素材新裁切已由本期正式报告绑定当前源/几何/遮挡，不能只因原片SHA相同就沿用旧窗口审核。
