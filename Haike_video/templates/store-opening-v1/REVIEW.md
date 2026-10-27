# 新塘未来汇开业模板22—26｜v002当前验收

文档类型：video-template-review
版本：v002；2026-10-25。
状态：v002实施规格限定ready，本期5个新原生完整输出技术检查及703个最终编码离散帧/46页实际视觉抽样均通过，已完成真实采样审核登记。连续听看、平台真机与用户最终确认保持pending。v001审美已被用户否定，其历史通过状态不适用于当前实现。

## 已取得的实际证据

- 用户指定参考已下载为六张2160×3018 WebP图文。作者已实际查看六张原图和联系表；原图只作配色关系与字体/空间机制分析，不进入海客成片。
- v001目录20文件及各SHA完整保存于本期任务snapshots/template-v001。
- 当前最终原生批成功生成30张1440×1800 PNG，覆盖5条真实主时钟的开头、人物、所有主要状态、最长字幕、权益及结尾。对应任务proof-draft/results.json与phone-375/ffc2cc6ebe064973/phone-proof-manifest.json；必须按当前源码、runtime和props身份筛选，历史批次不混用。
- 作者和总控分别实际查看当前全部5张375px联系图（共30张原生proof的等比衍生）。字幕、语义大字和五套空间关系相比v001有明确变化；没有以编译或字体请求成功替代视觉结论。实际回执为本期native-author-review.json和proof-final-root-review.json。
- 当前源码SHA为e0596c4f7eee01c36bcbf8519bd176866a7b05109b59886e56253052511968a9，layout为9db5881462fced8a8b03961fa47726c4834ba9765499bcf8c1cfac2eca30d95d；runtime为ffc2cc6ebe064973d30a4cfcc33341a2bc6820cdbf9bcc5499fa8cbb8609810a。当前回执逐条绑定props、PNG和phone联系图SHA。
- 本期5份正式材料crop_review_status均passed，明确绑定当前源PTS、实际窗口/遮挡、native代表帧及当前实现/布局SHA。统一适配器prepare/validate完成5个新请求，正式props/源文件/字体/已批准音轨与实际PNG草案逐字节一致；详细身份见任务projects.json、各编号request.json和native-proof-technical-current.json。
- ready-current.json与render-gate.json已写入当前5个request_sha256及作者/总控实际回执SHA。该PNG/裁切gate保留原身份不回写；新完整MP4使用独立的最终编码采样、quality/result与正式登记证据。

## 当前完整原生输出

五条新片已完成原生统一队列导出，共4620帧/154秒。全部1440×1800、30fps、H.264 yuv420p，实际视频流均大于20Mbps；AAC48kHz双声道及峰值≤-1.5dBTP、全解码和源拷贝SHA通过。最终输出、冻结请求、quality/result、采样manifest和实际视觉回执逐项一致，未重新生成批准配音、ASR或付费人物，未公开发布。

|片号/模板|时长/帧数|视频流bps|实际编码抽样|实际审阅者|
|---|---|---|---|---|
|01/22 金黄极黑|32.366667秒/971|20,494,373|144帧/9页|material_shot_plan|
|02/23 荧光玫红|28.600000秒/858|20,493,595|139帧/9页|material_shot_plan|
|03/24 柠绿橘红|31.733333秒/952|20,494,261|141帧/9页|material_shot_plan|
|04/25 亮青极黑|31.800000秒/954|20,494,271|145帧/10页|opening_redesign_audit|
|05/26 猩红蜜橙|29.500000秒/885|20,493,802|134帧/9页|opening_redesign_audit|

以上46页已由对应作者全部实际查看，共703个最终编码离散帧。计划包含全程1fps、全部main/detail与章节入出±1帧、由真实openingLayoutAt解析的全部布局状态边界、进入后3/6/12帧、开头每3帧、适用人物入/中/出、最长字幕首/中/尾及末帧。样本来自当前最终MP4真实解码PTS，没有用native PNG或源窗投影替代成片；大字短暂半字出现在计划遮罩进入阶段，稳定停留完整。未见新的文字溢出、关键主体遮挡、样本黑帧或结尾缺失。

本期[final-spec-evidence.json](../../../.local/codex-runs/store-opening-redesign-20261025/final-spec-evidence.json)汇总各影片/正式review SHA，[review-registration.json](../../../.local/codex-runs/store-opening-redesign-20261025/review-registration.json)包含5条registered技术与实际视觉采样handoff；各variant的final_v002_*证据绑定对应质量、结果、采样manifest、视觉回执和正式登记文件及SHA。WorkCatalog仍待用户确认，没有确认或发布动作。

## 本轮修复及实际复验

|项|实际发现|当前修复与复验|
|---|---|---|
|人物发顶|上一批identity顶部310px色面触到发顶|已改紧凑220px头板，身份标题与品牌横向并排；当前人物代表帧发顶完整且有余量|
|站名大小|上一批站名54px在375px约14px|已与地点同级64px；当前5组375px画面全站名可读|
|新裁切|上一批部分offer/invite候选镜头偏重天花，面孔落在色面边缘|材料作者按最终几何与源PTS调整objectPosition；当前native代表帧人群与主要体验主体已抬出底部色面，正式源窗报告单独绑定|

上一轮b856dd77/8f28f291、runtime5726ff4eeedc的30张PNG保留为修复历史，未冒充当前产物。当前实现和已看props已锁定，不再追加装饰或无证据改版；本轮未重新生成付费配音或HQ人物。

## 分维度当前结论

|维度|结论|
|---|---|
|静态结构|5份v002 schema/引用已检查通过；源码及新布局存在|
|当前原生PNG技术|passed，当前30帧均exit0；逐PNG完整像素解码、1440×1800尺寸/SHA及当前冻结身份已校验|
|当前视觉|passed，限当前30帧native/375px代表状态；作者与总控双回执|
|新裁切|passed，材料作者5份正式报告绑定当前显式遮挡/源PTS与native代表帧；源窗投影与native PNG清楚区分|
|当前冻结/限定ready|passed，5个新请求均通过统一adapter.validate；规格和render-gate逐条绑定当前request SHA|
|新完整视频技术|passed，当前5个MP4的实际尺寸/帧钟/视频流/AAC峰值/全解码/源SHA及quality/result均通过|
|最终编码视觉样本|passed，703帧/46页全部实际看完；限计划离散样本，不等于连续动态或听看|
|原生生产/正式登记|passed，5条当前WorkCatalog采样审核handoff已登记；未确认、未发布|
|连续听看/音素口型|pending，原配音已批准不等于新片已实际连续听看|
|目标平台/真机/用户确认|pending|
|公开发布|本期未授权|

本目录数字真值由layout.json和index.tsx提供。最终编码输出已进入上述真实抽样范围；当前视觉结论仍不覆盖未抽中的帧、连续动态、连续声音/音素口型或实际设备，不以离散抽样替代连续听看和平台验收。其他输入、字体、画幅、镜头或实现变化需新冻结并复验受影响范围。
