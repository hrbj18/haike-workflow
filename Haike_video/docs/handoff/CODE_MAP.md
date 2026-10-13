# 代码地图

更新时间：2026-10-13

## 当前工作台V2

- 主服务器backlot/server.py；API路由studio_api.py；底层域模型/Key/资产/草稿/发布日历studio.py。
- 新前端：仓库根prototypes/haike-avatar-generator/src/{StudioApp,App}.jsx；UI构建backlot/ui/avatar-generator；共享navigation.*和haike-brand.css。
- 路由：/graphic、/avatar、/projects、/calendar、/settings。旧工具GET跳新页；旧独立UI已归档移除。workbench.*保留历史项目维护。
- 图文：studio_render.py复用scripts/template_video/build_923.py和_paths.py，参数化safe_v2/9秒/三景、资产指纹、文字边界和FFmpeg完整解码。
- 口播：studio_avatar.py统一Key报价/预算/持久付费意图/ASR时钟；studio_composition.py和templates/studio-avatar-v1参数化三模板。旧模板3基线不修改。
- 动效：studio_motion.py固定ADu目录/时钟/素材/规划/冻结/导出，studio_motion_quick.py九TPL白名单；Motion.jsx/motion-model.js/motion.css共用ui.jsx和AvatarModeBar。/api/studio/motion/*、drafts/*/motion-{source,plan,job,project}。
- 原生队列：production_queue.py/production_queue_worker.py；studio_graphic、studio_avatar、studio_motion处理器，所有产物登记作品台账。
- 作品：work_catalog.py、work_api.py、work_publish.py；版本选择、人工确认、资料/封面/授权、冻结发布包和幂等提交。
- 发布：CreatorHub app/main.py中POST /api/publish/{id}/cancel，engine/monitor.py条件状态更新；日历同步/取消/提交互斥。
- 统一网关：根api-platform/、Haike_video/scripts/haike_api.py；Key私有配置.backlot/haike-api/client-config.json（不读取或提交秘密）。
- 产品/清理/边界：根docs/PRODUCT_STUDIO_V2.md；视觉QA：prototypes/haike-avatar-generator/design-qa.md及qa/studio-v2。

## 保留的原制作依赖

- 启动scripts/launch_backlot.py；API/workbench/task_center；文字层text_overlay_composition.py、tools/video/video_compose.py和CinematicRenderer.tsx。
- 旧数字人avatar_cloud.py、runninghub_avatar.py、avatar_audio_clock.py、runninghub_config.py；预览avatar_review_preview_pipeline.py；config/runninghub/冻结参数。
- 配音/转写：tencent_asr.py、tencent_config.py、lib/tencent_cloud.py、openmontage_tts_*、voicebox_tts.py；声音策略*_loudness_preferences.py和narration/music_preferences.py。
- 基础媒体：lib/ffmpeg_locator.py、lib/subprocess_window.py；tools/video/{video_compose,hyperframes_compose}.py和tools/audio/audio_mixer.py。
- 素材管理/证据/互动切割：material_library*.py、material_crop.py、material_interaction*.py；原二剪published_clip_*.py、published_remix*.py，旧独立UI已删除。
- 外站复刻/研究包：remake_*.py、copy_skill_research_pack.py、research_pack_*.py；每日科技后端daily_*.py保留内部历史依赖。
- 原完整路径/历史功能地图见LEGACY_CODE_MAP_20261013.md，不把保留后台误认为仍有对应主菜单。

## 验证入口

- 新制作/日历/付费恢复：tests/backlot/test_studio.py。
- 队列/作品：test_production_queue*.py、test_work_catalog.py。
- 发布合同：根creatorhub/tests/test_publish_contract_v2.py。
- 前端：tests/generator-model.test.mjs和tests/sites-worker.test.mjs。
- 动效：tests/backlot/test_studio_motion.py；前端tests/motion.test.mjs、gateway-config.test.mjs；真实队列scripts/studio_motion_smoke.py。产品与验收根docs/PRODUCT_AVATAR_MOTION.md、docs/tasks/2026-10-13-adu-integration.md。
- 本地四模板合成：scripts/studio_local_smoke.py；证据.backlot/studio-v2-local-smoke/summary.json。
- 实际工作台零费图文：.backlot/studio-v2-live-smoke.json，作品待用户审核。
- 源码检查：根scripts/check.py（Python3.12）；上下文预算：scripts/audit_context_handoff.py。
