# 08 紫黄轨道 · 真实视频新版

文档类型：video-template-runbook  
标准版本：video-template-v1  
模板规格：[规格](template-08.spec.json)  
编号/ID：08 / chromatic-08。版本1.1.0-candidate.1。implementation + specification，本机低清静音开发候选，用户审美及正式能力待验。

权威源码为Scene.tsx的`Template08({episode})`，仍从原AvatarScene type-only导入Episode。所有几何、颜色和主动效保留照片版：紫黄空心轨道、两站展厅巡览、立面体验记录、环场回看。原照片版及其87项FROZEN来源只读。新版没有导入旧Scene，也没有照片后备；没有Img或Freeze。素材内容的实际运动由Video承担，卡片运动只组织视线。

时钟：720×1280/30fps、720帧；场景[0,150)/[150,420)/[420,570)/[570,720)。每槽sourceFrame=sourceFrom+(globalFrame-from)，全局Sequence与源trim绑定，playbackRate1、不循环、不定格补长。人物同一288×360原视频全局连续，仅首尾可见，外框180×225，cover50%35%；中段visibility hidden。字幕是原示意cue，无ASR或口型通过声明。

| 场景 | 实际视频格 | 来源范围（30fps半开） |
|---|---|---|
| 环场建立0–150 | store/robot/children/dog各一格 | 各[0,150)，store实际161帧，非360帧 |
| 展厅150–420 | children/robot各一格 | 各[90,360)，两格随相机运动同时原速播放 |
| 立面420–570 | dog | [150,300) |
| 环场回看570–720 | duo/robot/children/dog | [0,150)/[180,330)/[180,330)/[210,360) |

逐格精确裁切和路径见video-slots-08.json及实际episode.materialSlots。图像cover裁切按原主体尺寸，store50%35%、robot50%62%、children50%58%、dog50%67%、duo50%60%。回看有意取后续片段作为编辑回顾；没有在一个槽中重头循环，也没有在源尾冻结。每个活动素材格都是真实视频；纸面、标题和中心结论可停稳。

操作：

1. 输入授权本机原片及现有代理 → 项目Python运行prepare.py → 私有preparation、两份episode和/assets/b资源 → 原始SHA、实际帧数、5路原片和所用视频代理/人物完整解码通过；不足立即阻断，不按旧12秒文字估长度。恢复先读现有清单，不新增付费调用。
2. 新源及准备结果 → `node Haike_video/templates/chromatic-six-video-batch-v1/window-b/build.cjs` → preview/build-manifest → 冻结87项来源不变、19槽范围合法、选型与源/依赖/资产SHA通过。保留旧版，不覆盖其它窗口。
3. 项目Python运行serve.py → 仅127.0.0.1:14955，支持Range → [08预览](http://127.0.0.1:14955/?template=08)。端口被别人占用时停下并报告，不结束其它服务。
4. 内置浏览器逐场定位/原速播放 → 新review过程图、metrics、源内容一秒对照与playback → 主体裁切/人脸/字幕/人物避让通过；入场后源时间推进且内容实际变化；719独立解码。浏览器UI最后显示帧滞后与补定位前后分别记录，不能宣称实时逐帧30fps。
5. evidence.py、records.py及相同标准检查器check_spec → 新版规格与验证记录 → 本地检查完成后交HANDOFF.json/MD。恢复只修失败槽/裁切/控制器，复验受影响段及新身份。

验收范围见VALIDATION.json。本轮技术、视觉和逻辑完整播放只覆盖这一实际输入的低清静音Player；未导出正式MP4。用户审美、有声/口型、高清、正式队列/Studio、平台真机、异机均pending。新六套的统一15组比较由总控独立执行，不能继承旧照片版通过。

源码、准备清单、实际episode、build-manifest和媒体路径通过HANDOFF.json交总控。字体先加载/assets/b/font.ttf；媒体必须保留/assets/b前缀。Scene是同一实际预览实现，聚合不得用另一套简化总览。
