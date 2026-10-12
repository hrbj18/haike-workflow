# 代码地图

更新时间：2026-10-11

## 前端

- 启动/重载 启动工作台.bat、更新并重启工作台.bat、scripts/launch_backlot.py
- 服务与 API backlot/server.py；项目库 ui/index.html、library.js
- 自动生产 ui/automation.*；工作台 ui/workbench.*；配音 audio_center.py、ui/audio_center.*；日期/发布 library_index.py、ui/library_index.*；队列 production_queue*.py
- 作品 backlot/work_*.py、ui/works.*；scripts/work_catalog_cli.py；docs/HISTORY_WORKS_V1.md。
- 文字层 text_overlay_composition.py、workbench.py、tools/video/video_compose.py、CinematicRenderer.tsx

## 素材理解与切割

- 成片索引 published_clip_*.py、ui/published_clips.*；二剪 published_remix*.py、ui/published_remix.js、pipeline_defs/published-remix.yaml；test_published_*.py。
- 解说/避让：docs/MATERIAL_COMMENTARY_V1.md。

- 共享库/分级：material_library*.py、material_crop.py；scripts/material_library_cli.py；docs/MATERIAL_LIBRARY_V1.md。
- 管理：material_library_{management,refs,manage_api}.py、ui/material_library_manage.*；docs/MATERIAL_LIBRARY_MANAGEMENT_V1_1.md（CLI）；test_material_library_*.py。
- 概览/V2：scripts/video_understanding_cli.py、material_overview.py、media_index.py、ai_vision.py
- 画面目标/选材 visual_need_plan.py、autonomous_material_selection.py；导入 material_catalog_import.py

- 素材证据 material_evidence.py、material_audio_envelope.py、material_{motion_timeline,pause_evidence}.py
- 户外互动首次切片 material_interactions.py、material_interaction_{review,edit,render,candidates}.py、material_audio_evidence.py
- 短语单元 material_interaction_units.py；二次精剪 material_interaction_story.py、material_interaction_second_pass*.py；接线 workbench.py、server.py、task_center.py
- 并发 interaction_concurrency.py、scripts/benchmark_interaction_concurrency.py
- 导出 material_interaction_export.py（cut-list-v1/FCP7/OTIO/SRT）
- 推荐 material_interaction_recommend.py；ui/workbench.js::renderMaterialInteractionRankLayout

## 关键媒体模块

- 口播：skills/INDEX.md（圆框、卡片模板3）。
- RunningHub runninghub_avatar.py、avatar_cloud.py、avatar_audio_clock.py、runninghub_config.py；config/runninghub/；scripts/{build_runninghub_infinitetalk_48g_workflow,probe_infinitetalk_48g_variants}.py
- 数字人预览/OOM 恢复/安全点 avatar_review_preview_pipeline.py
- 配音：tencent_asr.py（分片/并发）、tencent_config.py、lib/tencent_cloud.py；openmontage_tts_{engine,server}.py、voicebox_tts.py
- 导入/切割 avatar_import.py；导演 visual_director.py、ai_text.py；Pexels tools/video/stock_sources/pexels.py
- 预览 tools/video/hyperframes_compose.py、review_preview_pipeline.py；合成 tools/video/video_compose.py、tools/audio/audio_mixer.py
- 声音 narration/music/output_loudness_preferences.py、workbench.py::NARRATION_PROCESSING_CHAIN
- 跨平台 lib/ffmpeg_locator.py、lib/subprocess_window.py；Remotion NewsAnchor.tsx、dark-tech-news.yaml

## 外站素材复刻

- 工作流 skills/creative/material-remake-workflow.md；政策 docs/MATERIAL_SELECTION_POLICY_V1_ZH-CN.md；样例 projects/apple-fold-duo-remake-1/
- remake_material_screen.py（screen|pick|verify|audit）、remake_reference_transcript.py（腾讯ASR三态防重费）、remake_build_project.py、remake_retime_shots.py（换镜零付费）、remake_subtitle_safe_area.py（字幕安全区）
- 契约 schemas/remake-spec-v1.json；离线规格→脚本/时间线 remake_project.py

## 跨仓研究包与编辑层

- 研究包校验 copy_skill_research_pack.py；冻结 research_pack_snapshot.py；入账 research_pack_intake.py；CLI scripts/remake_editorial_cli.py（退出码2/3/4）、python -m backlot research-pack
- 编辑层 remake_intake.py、remake_editorial.py、remake_editorial_verdict.py

## 每日科技快报

- 采集/调度/供应商门/预算账本 daily_automation.py；候选池 copy_skill_hotspot_feed.py；选题证据门 news_selection_v2.py；脚本/冷审 daily_script_v2.py；恢复 daily_text_resilience.py
- 配音/切割/失败槽恢复/合成/QA daily_pipeline.py；CLI daily_cli select-v2|script-v2、scripts/run_daily_automation.py；API /api/daily-automation/*；状态 .backlot/daily-runs/<日期>/daily_run.json

## 测试入口

- 每日自动化 test_daily_*.py、test_news_selection_v2.py；工作台与声音 test_{workbench,server,narration_preferences,audio_center}.py
- 素材理解与证据 test_{media_index,ai_vision}.py、test_material_evidence*.py、test_material_{audio_envelope,motion_timeline,pause_evidence}.py
- 二次精剪与 Cut V2 test_material_interaction_*.py、test_interaction_concurrency.py、test_tencent_asr_long_audio.py
- 复刻与研究包 test_remake_{intake,project,editorial,editorial_cli,editorial_verdict}.py、test_research_pack_{cross_repo,intake}.py、test_copy_skill_research_pack.py
- 上下文 tests/unit/test_context_handoff.py；云端 tests/tools/test_runninghub_avatar.py
