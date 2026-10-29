# 模板6 · 六种广告视觉方向（art-v4）

本目录保存模板6的六套独立广告版式。旧 `art-v2`、`art-v3` 及其历史成片独立保留。

|direction|视觉方向|实现|
|---|---|---|
|community-showcase|晴空社区橱窗|RefinedDirections.tsx|
|blue-editorial|锐蓝商业刊物|RefinedDirections.tsx|
|optical-cinema|曜黑光学科技|RefinedDirections.tsx|
|red-manifesto|赤红商业宣言|NewDirections.tsx|
|silver-launch|银白产品发布|NewDirections.tsx|
|documentary|实景品牌纪实|NewDirections.tsx|

入口为 `index.tsx`，Remotion composition 为 `HaikeInvestmentArtV4`。画布为 1080×1920、30fps；版式与字体约束见 `layout.json`。`shared.tsx` 管理原人物窗口、带来源的真实素材窗口，以及按实测词时钟分组的短句字幕。contain 素材用同源模糊画面补边，清晰前景保留原比例。

从仓库根使用 `Haike_video/scripts/avatar_investment_source_art_v4.py` 接入原生单 lane 队列，传入原视频、已核对的 cue、绑定原视频 SHA 的 word-clock、art-config。新三方向允许代码背景，旧三方向要求已登记装饰 PNG。scene 的原文件、SHA、kind、cue 范围、offset、fit、source_label 必须逐一提供；不得把插画或产品示例描述为门店实拍。

复用原音轨和数字人，不改变脚本、口型或语速；素材窗静音。最终音频在统一合成路径只应用一次 -2.5dB。完整视频导出必须通过统一队列；证明 PNG 可用 Remotion still。

六种方向目前通过本地 CLI/config 选择。此目录本身不代表工作台已提供六风格选择控件，也不代表真实发布或商业素材授权已经验收。
