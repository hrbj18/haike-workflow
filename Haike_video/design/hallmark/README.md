# Hallmark 视觉参考库

上游 [Nutlope/hallmark](https://github.com/Nutlope/hallmark)，技能 v2.0.0；本次固定提交 `7ec868225c6caa040558c321ee0fefa0e73f83a8`（2026-10-22）。48套原版主题说明与网页参考图保存在 `themes/`，中文解释与视频使用场景为本项目编辑建议。MIT许可见 [LICENSE](LICENSE)；来源和本地文件摘要见 `UPSTREAM.json`。

这是48套网页视觉体系的参考库。主题选择持久保存为视频草稿的 `art_direction`；它不自动变更原包、镜头参数或产生48套已经验收的视频模板。实际中文排版、4:5构图和动效适配由 [Hallmark视频流程](../../skills/creative/hallmark-video.md) 进入对应模板。项目引用本地副本，运行时不依赖全局技能或联网。

## 使用

打开工作台 `/motiongit`，展开顶部“Hallmark 视觉参考库”。可以按类别和中文关键词筛选，查看样图、原版说明和视频适配计划。选定草稿后保存风格方向，复制草稿会保留。仅浏览不修改任何视频。

完整目录可从 `catalog.json`、[中文一览](CATALOG.md) 或 `python scripts/hallmark_video.py list` 读取（CLI在 `Haike_video` 下运行）。四类为上游 `genre` 的中文解释；具体视频场景属于本项目建议。

## 安装与升级

本机完整技能安装在 `C:/Users/Administrator/.codex/skills/hallmark`，通过系统 skill-installer 按上述提交安装，下一轮对话可加载。此绝对路径仅为本机安装回执；项目运行使用本目录。新机器若需要完整网页技能，按系统技能安装器从上游安装相同版本。

升级先核对上游版本、许可和48条中文标签是否仍匹配，再使用根 `scripts/sync-hallmark-reference.py --skill-dir <技能目录> --license-file <上游LICENSE>` 更新参考副本；脚本固定提交须随已检查版本一同更新。`python scripts/hallmark_video.py verify` 校验全部本地摘要。保留旧草稿的来源身份，版本变化后的选择须重新检查。

参考图用于设计对照，图内英文、数据和照片不成为本期事实或生产素材。上游照片与字体各自的许可仍适用；本次未导入其照片库或字体文件。真实生产使用本期已授权素材和可用中文字体。

## 本次验证范围

安装完整性、48条目录与99个参考/许可文件摘要、HTTP参考读取、草稿保存/清除/复制及旧草稿兼容、前端构建和实际页面检查均由本次记录单独确认。视频风格适配及成片审美仍须本期实际预览；选择参考本身不提高原模板的已验证范围。
