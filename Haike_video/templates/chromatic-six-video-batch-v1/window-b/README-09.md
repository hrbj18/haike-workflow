# 09 朱红冰蓝折页 · 真实视频新版

文档类型：video-template-runbook  
标准版本：video-template-v1  
模板规格：[规格](template-09.spec.json)  
编号/ID：09 / chromatic-09。版本1.1.0-candidate.1。implementation + specification，本机低清静音开发候选，用户审美及正式能力待验。

Scene.tsx导出`Template09({episode})`，原颜色、字号、画布主体尺寸和动效结构保留：书脊半页翻折、来源先读后驻留、三条注记发牌、局部曝光交接、双格压叠结论。09前次裁切修正保留：完整来源缩小至42%驻留左侧x48/宽242.76，注记x315/宽357。文字可停，源视频一直在走。

| 场景 | 实际视频格 | 源范围（30fps半开） |
|---|---|---|
| 开页0–210 | robot左页与封面、children右页 | 各[0,210)，封面与左页源同帧；从前到后不使用照片 |
| 驻留210–450 | children-long | [210,450)，衔接右页7秒源时间；原片真实代理524帧，不按旧12秒截断 |
| 曝光450–600 | robot A、children B | 各[210,360)，A推进、B拉出；交叠时两路均为原速视频 |
| 结论600–720 | duo主格、store副格 | 各[0,120)，源实际234/161帧，范围均足够 |

源范围、路径、cover裁切、全局/场景时钟见video-slots-09.json和实际episode.materialSlots。每槽sourceFrame=sourceFrom+(globalFrame-from)，Sequence映射源入点，speed1、无loop/Freeze/慢放/尾帧填充。亲子原片13.6/14.6秒已实际查看，孩子、家长和桌面机器狗动作可辨，与观察注记相符。dog表演不再作为“人的反应”的驻留来源。

画布720×1280/30fps、720帧。人物是原同源单条24秒，在0–210/600–720可见，全局连续；中段隐藏不重新启动。字幕为原示意cue，无ASR、语音或口型验收。所有活动主视频格均为Video；无静态图像素材，不把卡片翻动当视频内容运动。

操作契约：

1. 已授权原片/准备身份 → 项目Python运行prepare.py → 6路主视频代理、同源人物/字体、实际两份episode、preparation → 5路原始视频与全部所用视频完整解码，帧数与范围核对；缺视频/越界阻断，无图片回退。
2. 确定源 → build.cjs → 私有bundle及build-manifest → 原87项冻结不变；选型、依赖React18.3.1/Remotion4.0.506和实际输入/资产SHA一致；失败只重建本窗口。
3. 私有preview → 项目Python运行serve.py → [09预览](http://127.0.0.1:14955/?template=09) → loopback14955/Range，FontFace先载入/assets/b/font.ttf；不要重启其它窗口服务。
4. 实际浏览器定位与完整原速播放 → fullPage原图或明确标记的原生viewport截图、DOM矩形裁取、metrics/source内容对照/playback → 所有场主体/字幕/人物分区可读；已落定的右页110/140、驻留408/438、曝光后540/570、结论684/714隔一秒，内容真实变化。折页被遮住的前面/左面只作为入场运动检查，不冒充落定后的可见双帧证据。
5. evidence.py与records.py、相同标准检查器check_spec → 新版规格/VALIDATION/HANDOFF → 静态和视频内容证据一一对应。浏览器自然结束的显示帧滞后及719独立定位分别保存，不反复播放凑数字，不声明实时逐帧30fps。

恢复：来源不清楚时仅修改槽/裁切后复验；媒体时间不推进则核对Sequence的globalFrom与sourceFrom以及Range响应；不得循环或定格补长。结束事件仅记录状态，不同步seek，避免再次触发ended。最后719通过定位控件独立核验。源码与实际媒体时钟保持同一版本。

本轮没有新生成、付费、外网下载、正式MP4导出、TTS/数字人调用、发布或推送。用户审美、有声/口型、高清、生产队列/Studio、平台、异机、六套新版本统一比较均独立pending，旧照片版的结论不迁移。总控按HANDOFF.json引用同一Scene与真实episode聚合。
