# 海客科技：数字人口播模板3

日期：2026-10-12。用户在已交付数字人测试片基础上，明确要求按照项目「数字人口播模板3」制作。本轮复用原人物、配音和海客科技标志，只执行本地排版与合成，新增云API费用0元。

## 成果

1080×1440、3:4、30FPS、210帧、7.000秒，H.264/AAC。原口播6.56秒，补0.44秒停帧与静音。白色外卡、柔和四色渐变、圆框人物、章节摘要和蓝色重点字幕来自确认基准 `avatar-template3-card-3x4-v001`；品牌及两章内容为本期替换：0–2.8秒「内容创作更简单」，2.8–7秒「一个接口连接工作流」。基准三个TSX的哈希均未改变。

文件位于运行安装包的 `Haike_video/projects/haike-avatar-smoke-20261012/`：

- `renders/海客科技-模板3-v001-delivery.mp4`：最终交付文件。
- `artifacts/delivery/haike-template3-v001.mp4`：同文件的本地浏览器入口，SHA256 `f9be82ec52390df2764472b8346ee05649729bde95ac9e343ae97a64aa272336`。
- `index.tsx`、`Root.tsx`、`Composition.tsx`、`art-direction.md`、`public/`：本期可编辑副本及同源媒体。
- `artifacts/template3/manifest.json`、`render-request.json`、`render-result.json`、`preflight.json`、`technical-qa.json`、`delivery-transcript.json`：来源、请求及最终文件验收记录。
- `snapshots/template3/final-contact-sheet.jpg`：9帧抽样；各原尺寸帧另存。

本地播放：http://127.0.0.1:14754/media/haike-avatar-smoke-20261012/artifacts/delivery/haike-template3-v001.mp4 。项目原始人物片及其供应商任务不变。

## 验证

原生 `CompositionValidator` 预检通过，严格TypeScript检查通过；使用 `VideoCompose.execute(operation=render)` 的Remotion Atelier路径制作短样片，没有直接调用注册的review/full-preview runner，也没有重做付费素材。

最终容器、视频、音频均为7.000秒，210帧；完整解码无报错。检查9张代表帧和原尺寸场景/话尾：没有阻断性缺图、裁头、文字越界或旧购物文案。人物采用448×448等比裁切，静音独立人物轨和同源配音轨避免双声。

最终音轨与同源配音比较：24kHz下延迟0采样，归一化相关0.999234；响度−19.28 LUFS，真峰值−1.68 dBTP。离线Whisper base转写最终交付文件，不提供原文提示，去除标点后与本期口播逐字一致。字幕按已知原文与实测停顿组织，底部字宽保护通过；不是逐字卡拉OK。

原生渲染器默认标记pass，但其AAC轨长7.061333秒。保留原渲染结果，用同源7秒WAV局部重封装交付，视频轨直接复制；最终manifest与QA指向修正后的同一版本。该恢复过程没有新增云调用。

本机离线转写遇到[上游同类PyAV参数兼容问题](https://github.com/SYSTRAN/faster-whisper/issues/1589)，改用FFmpeg解码的PCM数组；转写运行在隔离的uv环境，未修改便携项目依赖。

## 边界与知识库提案

交付为可观看的模板3短样片，保持review-ready；连续人工听辨和真实手机平台UI遮挡待用户审阅。本次没有发布，也不代表3:4模板已经接入工作台正式全片时间轴。统一Key商业扣款未在本次验证。

可供知识库维护者核验的新增证据：7秒新主题可以复用既有数字人完成原生模板3短样片；Remotion自动review应继续与最终流时长核对，尾包可保留视频轨、用同源音轨局部修正。共享手册未改。
