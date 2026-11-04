# 现场笔记完整视频候选2.1.0

精确身份为`field-notes-v2 / 2.1.0`，画廊默认照片版`2.0.0`及其冻结文件保持不变。本候选保留纸色、青珊瑚、标题让位、网格聚焦/返回、线绘制、来源汇聚四阶段关系；主体改为原速实拍视频，完整主旁白开启。本候选为独立视频改编，不宣称与旧照片版逐像素相同，也不声称执行了旧版私有GridToHero。

公共`motion_replay.prepare('field-notes-v2','2.1.0',{'data':...})`核对版本、公开执行源码、输入清单、完整原稿/原生配音/真实ASR、原视频及高质量人物母片。只接受准备目录与可选完整四动作顺序。`Scene.tsx`的`ACTIONS[scene.actionId]`实际调用四个组件；内部语义事件读`scene.events`的全片绝对帧。几何、曲线、裁切仍由源代码持有，未开放任意动作替换或场景重排。

每期私有目录需要`production.json`、`payment-ledger.json`、`audio-result.json`、`narration.wav`、`asr-transcript.json`、`timing.json`、`avatar-result.json`、`avatar-master.mp4`、素材和混音来源证据，以及`preparation.json`绑定的`public/episode.json`、完整`master.wav`、字体与真实视频。主时钟为完整旁白向上取整到30fps；不拉伸声音，不循环/定格补视频。人物仅消费本期真实出镜窗，不能拿任意旧口型替代。

从仓库根运行：

```powershell
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/motion_replay_field_notes_video.py --data <本期私有目录> --phase frames
```

实际检查语义事件、段落边界和人物窗口的PNG后，将`latest-frame-job.json`的精确`identity`与实际图片SHA、审查结论写入本期`design-review.json`，`status`为`pass`。同入口`--phase render`生成1080×1920/30fps完整有声视频，核对视频流≥20Mbps及全片解码，再登记作品。预览和整片消费同一个episode/bundle。入口只沿`studio_investment_recompose`的暂停入队、专属领取、精确合同`haike-field-notes-video-production-v1`执行；缺审查或身份变化停止，不绕过队列。

`production.json`可显式指定现有`node_executable`、`browser_executable`或`runtime_root`，本实现不下载安装运行时。音频和人物付费阶段只供已授权总控使用，必须先有单独报价/预留与持久化原任务回执；公共视频入口不自动购买新语音或人物。

结构、关键帧、完整编码、外放听感和平台发布分别记录。实际成片及每期证据留私有目录；登记生产入口不代表本期已通过视觉或设备听审。
