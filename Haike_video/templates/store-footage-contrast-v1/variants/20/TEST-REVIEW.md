# 纯实拍20 验收

2026-10-23，本机6秒开发样片。原生项目studio-edae8f4d812f12cc，冻结请求artifacts/store-manager-request.json。

技术：1440×1800/30fps/180帧，视频流20468064bps，完整解码通过；AAC -16.61LUFS，真峰值-4.07dBTP。使用上一轮已验母带，不改速，音乐侧链与两次音效保留；设备主观听审待用户试听。

视觉：查看0.5/1.5/2.95/3.05/4.1/5.1秒实际导出帧，覆盖所有三句字幕、镜头切换前后；无数字人画面，文字完整可读，门店实拍保持原始范围。源文件清单无avatar视频，所有实拍SHA与原片一致。抽帧证据位于根.local/codex-runs/store-footage-18-21-20261023/20/review.jpg。

成片SHA256：985111495ad2f96c64e28e516f4390437e2e10aba9bf5d668272dc6514b701de。已归档到店长账号/无数字人模板测试_18-21_20261023；原生输出保留。零新增云调用、未发布。完整30秒、异机与平台未验；阶段保持specification。

复刻：从仓库根运行Haike_video/.venv/Scripts/python.exe -X utf8 Haike_video/scripts/store_manager_template.py --request Haike_video/projects/studio-edae8f4d812f12cc/artifacts/store-manager-request.json --check。去掉--check复用归档，--fresh重新渲染。默认目录读.local/store-manager/defaults.json，测试另指定--output-dir。

