# 10 黑柠节拍画报 · 真实视频版

文档类型：video-template-runbook。标准video-template-v1。[规格](template-10.spec.json)。ID chromatic-six-10，版本1.1.0-candidate.1，implementation。仅本期720帧低清静音候选；正式有声/口型、高清、生产、平台/异机和用户审美分别pending。

保留冻结照片版的黑/柠黄/暖白、冲击开场、水平动词胶片、首词补句和末尾三格收束。所有主素材格为原生Video；真实人、机器人、机器狗持续原速运动，标签/卡片/数字人运动不是素材运动的替代。旧版目录及SHA不修改。

参数真值：[Scene.tsx](Scene.tsx)和[视频槽](video-slots-10.json)。选型：[selection](selection-10.json)。Episode为旧类型兼容输入并增加videoSlots，导出Template10({episode})。每片段全局[from,to)、sourceStart/sourceEnd均为30fps整数帧，sourceFrame=sourceStart+globalFrame−from；sourceEnd不超实际解码帧数，切点不循环、不冻尾、不慢放。

0–149门店视频（store仅161帧，使用0–150）；150–437五格横向胶片分别使用children/robot/dog/children/robot、各自源入点0/0/0/60/30，所有部分可见的相邻格也是真视频；438–569互动视频source180–312；570–719三格分别robot90–240、children180–330、dog100–250。精确值以视频槽JSON为准，不把同一12秒源撑到24秒。

主素材采用cover+独立焦点，原机器人/机器狗/互动主体在实际浏览器帧中核对；末尾窄格接近源竖屏比例。人物复用原24秒同源视频，首尾[0,150)、[570,720)显示，中段窗口/标签CSS隐藏但源继续计时。字幕y1110独立，示意内容不是ASR/口型验收。

## 执行与恢复

1. 输入既有授权preparation和源媒体 → 根目录 `Haike_video/.venv/Scripts/python.exe -X utf8 Haike_video/templates/chromatic-six-video-batch-v1/window-c/prepare.py` → 私有preparation.json、episode-10/11和规范视频槽。gate为逐字节SHA、原生完整解码、真实帧数、全部源范围合法。失败重新选择合法源范围，不生成补长。
2. 已准备输入 → 同目录 `node build.cjs` → preview/build-manifest与bundle。gate为既有依赖、输出/资产/episode身份一致。失败只改本窗口，不重启其他服务。
3. 同一组件和输入 → `serve.py`仅127.0.0.1:14956，媒体/assets/c/ → [10预览](http://127.0.0.1:14956/?template=10)。gate为Range206、实际字体解码、每格视频ready且时钟匹配；每场落定后相隔至少1秒图像有内容变化，场景/剪接/人物边界、随机跳转与完整0→719播放。保留失败记录，不seek冒充尾段播放。
4. `verify.py`核对当前规格、选型、实际依赖、原素材长度、输出SHA和本次视频证据。实际结论见VALIDATION.json；原照片版比较不能作为本版验收。

本期交付为同一React组件的可播放浏览器预览，没有正式MP4、付费、新TTS/数字人、外网下载或发布。运行素材仅在本窗.local；公开源码不复制私有人物与上游源码。输入/源/裁切/时钟或bundle变化后重验关联段和身份。
