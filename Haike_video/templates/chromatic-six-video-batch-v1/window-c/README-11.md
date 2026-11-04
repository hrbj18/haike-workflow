# 11 深蓝蜜桃路线 · 真实视频版

文档类型：video-template-runbook。标准video-template-v1。[规格](template-11.spec.json)。ID chromatic-six-11，版本1.1.0-candidate.1，implementation。仅本期720×1280/30fps/720帧低清静音候选，独立待用户评审。

保留已认可的深蓝/蜜桃/青色、760×1540纵向折返世界、相机两次向下巡游、步骤节点和片尾0.52整体回看。三站主素材都是原生视频，片尾节点保留约260×184实际素材尺寸，用cover和逐源焦点填满原框，非窄条contain。路线是体验顺序示意，非地理坐标。

唯一运行真值为[Scene.tsx](Scene.tsx)和[视频槽](video-slots-11.json)。props仍{episode}，导出Template11。Sequence按每段全局from局部化，视频startFrom为源帧入点；每帧sourceFrame=sourceStart+globalFrame−from，原速、不循环、不冻尾、不慢放。

| 槽 | 全局区间 | 源范围（帧，末端不含） |
|---|---|---|
| route-0 | 34–195 / 195–555 / 555–720 | store0–161 / children0–360 / robot0–165 |
| route-4 | 232–592 / 592–720 | robot0–360 / dog80–208 |
| route-2 | 446–720 | children60–334 |

较早节点在后续巡游中可能被viewport裁掉，但回看时仍继续匹配其全局源时钟。各次顺序剪接是不同现场内容的原速编辑，不是同段重复补长。store实际161帧，三条其它视频各360帧；preparation有实际全解码和SHA，禁止仅信旧“12秒”文字。

引出线改为整个视频框左边缘(10,636)，不用静态圈注伪装跟踪运动人脸/机器狗。标签为“现场，正在发生。”。人物复用同一24秒源、只首尾小窗，中段源继续原速但窗口与标签隐藏；字幕独立，不遮脸。

## 执行与gate

1. 已授权旧preparation及原片身份 → 根目录运行本窗prepare.py → 规范视频槽、episode-11、私有素材与preparation.json。gate：源范围覆盖完整可见时段、实际流帧数及完整解码通过。长度不足改选素材/声明剪接，不能冻结或循环。
2. prepare产物+同一Scene → node build.cjs → 同源bundle与build-manifest。gate：React18.3.1/Remotion4.0.506既有依赖及每个源/输出SHA；不升级依赖。
3. serve.py → [11预览](http://127.0.0.1:14956/?template=11)，仅127.0.0.1:14956、/assets/c/。gate：开场、切点与剪接195/555/592前后、随机定位、片尾及每场稳定后≥1秒两帧实际内容变化；同一完整播放到719，禁止seek冒充全片。fullPage原图非空后按DOM矩形裁取，空图不作证据。
4. verify.py → 本期独立VALIDATION、HANDOFF.json与冻结身份。换源/裁切/时钟/bundle后只定向复验关联段和证据；旧版冻结只读。

本地素材是授权原生视频的低清代理，未改速度和素材类型。图内人/设备/店招是固化内容，不提供编辑其内文字的槽。正式有声/ASR/口型、高清、生产/平台/异机、用户审美和新版六套15组比较单列pending；本窗口不继承照片版结论。本次无正式MP4导出、无新生成/TTS/人物、无付费/外网下载/发布或推送。
