# 店长账号模板18—21完整片

文档类型：video-template-runbook；标准版本：video-template-v1。完整片扩展v002，保留v001六秒样片的配色和结构。规格在variants/18至21的video-template-spec.json；像素、颜色及绘制顺序真值是index.tsx。实际参数随原生项目的store-manager-request.json冻结，不能只凭本说明猜测字幕或切点。

## 输入、时钟与版式

画布1440×1800、30fps、4:5。已确认完整WAV为主时钟，durationFrames=ceil(音频秒数×30)，不改变语速或删停顿。当前适配器容许1—60秒；本轮验收约29—31秒。props包含style、durationFrames、audio、shots、captions、chapters；20/21可额外提供avatar对象。

18橙紫：主素材窗(380,295,1005,1200)，左侧三行巨字，顶部横题。19冰蓝樱桃：并排双窗(38,390,674,1090)/(728,390,674,1090)。20酸橙深蓝：主窗(330,120,780,1070)，下方横切标题带。21玫粉孔雀：主窗(450,0,990,1280)，副窗(38,660,600,835)，左上竖排题与右下短句。全部源画面contain，保留人物和门头；素材原声静音。

chapters按全片帧from升序定义，取当前帧之前最后一项。title、side、sub和secondary控制源码对应文本，18标题最多9字、侧字三行每行1字；19两条标题分别最多9字；20标题最多8字；21左标题最多3行每行3字，右下最多2行每行5字。长文本应在冻结前改写，不能缩成不可读小字。章节切换采用直接换字，避免标题飞动影响读图；片头12帧easeOutCubic位移动效保留。

## 实拍与店长短段

shots为独立选段：id、lane(left/right)、src、from/frames(全片30fps)、offset(原片秒)、fit。主轨完整覆盖全片；19/21副轨也必须完整覆盖。不重叠、不留空、不冻结、无循环或变速。每镜最多120帧，本轮90帧；同一来源连续使用须合并计时后仍≤4秒。用索引选段后实际查看代表帧，优先干净的门头、完整机器人、现场操作，人物反应配合作为副画面。回到原片，SHA一致，不使用低清精剪替代。

20/21的avatar={src,from,frames}为可选短段，最多240帧；18/19禁用。启用时只在主素材窗临时替换实拍，副轨持续播放；结束恢复主实拍，字幕及整条master.wav不切换。默认4:5造型02，高质量RunningHub2112180419025260546/Plus48G，25fps、长边1536。按已批准WAV精确截取一句并保留前后静音余量，起止取0.2秒网格对齐25/30fps，不重配音、不伸缩。原生生成视频静音嵌入，嘴型跟同一WAV区间。人物不裁头、不变形，不调用短样旧音频的数字人冒充新口型。

## 字幕、BGM与音效

captions为Caption JSON，起止来自本期百炼qwen-audio-3.1-asr-flash-filetrans的真实词时钟，逐句对照已确认文案。字幕框(55,1560,1330,140)，微软雅黑58px/900，单行最多21字，优先语义分句到18字以内。18/19/21白字深底，20深蓝字酸橙底；6帧easeOutCubic上移6px后稳定，结束延65ms，无重影描边，不用逐字震动。

配音原文件只做−2.5dB增益。使用已授权本地原创音乐，按曲目响度校准；本轮音乐−5dB、淡入0.18s/淡出0.65s，超过曲长显式loop。speech-led-v1侧链threshold0.05、ratio2.5、attack15ms、release180ms，目标在说话时仍听见音乐。不要机械套增益代替测量。dong在首cue起点−15dB，whoosh在章节切点−19dB并按音源sync_ms对齐峰值，tick在末句起点−19dB。单一48kHz立体声PCM母带用于预览和导出，不再叠加原片或数字人音轨。最终AAC真峰值≤−1.5dBTP；检查单声道折叠和语音时音乐电平。设备实际外放未听验须单独标记。

## 制作、检查与恢复

输入核对→backlot/studio_store_footage.py prepare冻结原片SHA与实现→submit进入原生统一队列→ProductionQueueWorker.run_local_recompose→VideoCompose/Remotion渲染。复用入口scripts/store_manager_template.py --request <原请求> --check；去掉--check恢复已有产物，--fresh以新实现重新冻结。不能直接调用外部渲染绕过队列。

先PNG/CRF1/YUV444p高保真母版，再同一任务H264 slow、20.5M CBR、2M缓冲、YUV420p、AAC192k/48k立体声，ffprobe实测视频流≥20Mbps。该编码为高质量有损交付；原片字节不变。完整解码、分辨率、帧数、时长、视频流码率、字幕越界、每镜入出点及声音峰值通过后查看实际成片：开头、每章、数字人入出与结尾。

交付C:\Users\Administrator\Videos\成片10-23\店长账号，四条各自文件，不覆盖历史样片。本轮证据在根.local/codex-runs/store-four-full-20261023/，每期保存props、ASR、音频回执、request、queue、delivery与QA。云端恢复固定原任务名；本地问题只重做受影响合成，不重复配音或数字人付费调用。完成含可播放交付；用户与平台真机确认单独记录，未授权发布。
