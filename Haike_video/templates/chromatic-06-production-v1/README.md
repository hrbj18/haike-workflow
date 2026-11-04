# 06完整口播生产候选

精确身份`chromatic-06@1.2.0-candidate.1`。从原1.1.0蓝橙切面独立适配，原冻结文件/历史验收不改。1080×1920/30fps，原720×1280几何整体1.5倍绘制；实际音频是主时钟，单独词/句ASR锚点分别驱动切口、遮挡、推穿、灰阶分隔与说明显现。不是对24秒源片整体等比缩放。

实际执行映射在`Scene.tsx#ACTIONS`，键为统一合同的4个源动作ID。每个场景明确`actionId`及各必需内部`events`，缺动作/未知事件/错误ASR引用会在`backlot.motion_replay_chromatic_production.validate_props`阻断。标题、说明、标签与字幕为本候选真实消费的输入；全片真实视频镜头连续覆盖，不循环、不冻尾、不变速。首尾高质量数字人与完整原声有明确取段映射，中段不出人。

只能通过已注册`studio_investment_recompose`父队列、精确contract `motion-replay-chromatic-production-v1`制作。`prepare(queue,value)`绑定本期源码、媒体SHA、完整脚本/TTS/ASR/HQ回执与声轨，`submit`幂等入队暂停，`run(queue,job)`执行原生Remotion与最终20Mbps以上有声输出，并登记作品。无发布操作；重试保留上游已付费产物，不调用任何收费供应商。

源码checkout中的Python子进程需已有Node/npx与FFmpeg路径。启动专属本地worker前复用`tools.video.video_compose._ensure_npx_on_path()`及`_ensure_ffmpeg_on_path()`载入本项目已存在的运行时，不全局安装、不改真实安装副本。父队列专属`run_local_recompose(job_id)`保留单道闸门；本地环境失败只恢复原可重试父任务，上游TTS/ASR/HQ任务不得重走。

本机B6已完成独立60秒制作，交付与本轮scope在仓库根`.local/motion-production-20261103/B/DELIVERY.json`及`QA_REPORT.json`。真实输出为1080×1920、30fps、1800帧，视频流实测20,997,062bps；完整音轨与原稿31条字幕进入成片。已看24个代表帧及健康提示/片尾细节；连续听审与真人外放仍pending，不将抽帧或波形相关写为听审通过。原1.1.0画廊绑定不改变。

此候选的完整制作验收逐条记录，不继承1.1.0历史低清静音通过。脚本引语不冒充现场采访；缺少的具体产品镜头可用真实门店视频承载文字，不能生成伪采访/假检测画面。涉及体质检测的场景必须显示“AI体质检测：非医疗诊断。不看病不卖药，给您个参考。”。
