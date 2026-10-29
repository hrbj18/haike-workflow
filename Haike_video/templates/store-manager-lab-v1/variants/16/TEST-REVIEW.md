# 风格16 验收范围

2026-10-23；仅本机6秒开发样片，4:5，1440×1800，30fps。原生队列项目studio-cc82c6fff1957243，render store-manager-9d8c9c859ef4064719c4。冻结输入位于该项目artifacts/store-manager-request.json；输出与quality/result位于renders/store-manager-9d8c9c859ef4064719c4。

- 静态规格：video-template-v1检查通过。
- 技术：完整解码通过，视频流实测20468048bps；原素材与数字人按SHA复制，零云端调用，未发布。
- 视觉：查看实际成片0.5、1.5、2.95、3.05、4.1、5.1秒，共6帧，覆盖最长字幕、三句字幕和切换前后。未见文字溢出、脸部裁断或空画面。截图证据存根.local/codex-runs/store-manager-templates-14-17-20261023/16/review.jpg；不是逐帧完整视觉审阅。
- 声音技术：-16.61LUFS，AAC真峰值-4.07dBTP；单声道折叠无显著抵消，证据同任务audio-mono-qa.json。BGM侧链、开场dong、3秒whoosh、音乐尾淡出已写入混音回执。设备主观听审仍待用户试听。
- 交付：店长账号默认归档目录下模板测试_14-17_20261023，文件与原生输出SHA一致，页面提供四条独立播放。

复刻命令（仓库根）：

```powershell
Haike_video/.venv/Scripts/python.exe -X utf8 Haike_video/scripts/store_manager_template.py --request Haike_video/projects/studio-cc82c6fff1957243/artifacts/store-manager-request.json --check
```

正式30秒扩展、换文案/素材后的时间适配、异机、平台与用户确认均未验；保持specification开发阶段，不能直接当通用ready模板。

