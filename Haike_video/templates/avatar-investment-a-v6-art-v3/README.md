# 模板6艺术扩展 v003

使用已有数字人口播原片，制作三种广告方向。Studio 模板 ID 保持 `avatar-investment-a-v6`，独立视觉实现为 `HaikeInvestmentArtV3`。本扩展通过 `investment-source-video-art-v1` 本地合同识别，不改变旧 v002 清晰字幕修正路线。

| 方向 | 适用内容与视觉 | 本期测试 |
|---|---|---|
| `community-showcase` 晴空社区橱窗 | 社区纸雕、楷体标题、绿色拱窗、黄色关键词字幕 | 01，4:5近景 |
| `blue-editorial` 锐蓝商业刊物 | 钴蓝折纸、刊物字级、朱红细线、浅色纸签字幕 | 02，9:16中景 |
| `optical-cinema` 曜黑光学科技 | 光学玻璃、铜色光轨、宋体标题、墨黑金色字幕 | 03，9:16中景 |

几何、字级、色板和动效参数以 `layout.json` / `index.tsx` 为真值。装饰 PNG 在 `assets/`，不含人物或文字，不代表真实门店；系统字体不随项目分发。人物、眼镜、服装、动作、口型和原背景属于原视频固化内容。

执行前读[同名 runbook](../../../Haike-Videohub/agent-runbooks/数字人口播模板6-招商A.md)和[生产契约](../../AGENT_GUIDE.md)。只通过 `scripts/avatar_investment_source_video.py` 准备、暂停入队并由原生 worker 认领；不得直接调用注册 runner 或为改版重新生成付费人物/声音。

输入为含 AAC 的原 MP4、绑定同一视频 SHA 的真实字幕数组、艺术配置、背景图 SHA、标题和品牌。字幕每行最多14字、最多两行，保留真实毫秒边界与语义换行。关键词色块是静态强调，整句5帧入场，不伪造逐字时间。

艺术配置只有 `direction/background_path/background_sha256/chapters/highlights/portrait_framing` 六个字段。每章只有 `kind/fromCue/toCue/heading/deck/points` 六个字段，cue 从0编号，章节连续覆盖所有字幕。章节从各自第一条字幕的真实起点切换，第一章从0开始、最后一章覆盖音轨尾部。`ai` 是内部章节类型，不能向没有员工内容的原稿添加 AI 员工承诺。

本次已验证输入使用两行标题、简短说明和不超过4字的社区要点（其他方向不超过6字）。入口允许的更长字段、其他人物景别或不同主题仍需实际出样检查，不能将自动字号缩小当成手机可读性通过。

声音从原片提取24kHz、PCM16、单声道，保持原速；最终封装只做一次 -2.5dB 线性降幅，不重复原素材已应用的语速，不增加音乐。最终 AAC 必须逐片实测真峰值、完整解码和字幕/作品绑定。

三条测试的实际验证范围见 `video-template-spec.json` 和 runbook。技术/视觉/本地作品接入分别记录，连续听看、音素口型、用户成片确认及真实平台仍独立验收。本扩展不包含发布。
