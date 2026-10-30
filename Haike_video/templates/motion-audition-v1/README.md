# 实拍动效试镜库 v001

五款独立开发试镜，每款4.5秒、1440×1800、30fps，静音、无数字人。用于选择动效和校准素材结合方式，不代表成片模板已经接入生产队列。用户选中的编号可以作为后续镜头设计输入。

| 编号 | 效果 | 来源 | 时窗 |
| --- | --- | --- | --- |
| B01 | 甩镜 | Remocn whip-pan | 1.5–2.37秒 |
| B02 | 穿越推进 | Remocn push-through | 1.5–2.83秒 |
| B04 | 撕纸揭示 | Remocn paper-tear | 1.5–2.7秒 |
| B06 | 立体方块波 | Remocn grid-wave WebGL2 | 1.5–2.7秒 |
| A06 | 跟随触碰的冲击波 | PixiJS Filters ShockwaveFilter 6.1.5 | 0.4–1.8秒 |

## 输入和时钟

`index.tsx`的Props为参数真值。`a`和`b`分别含public目录内素材文件名`src`与秒偏移`offset`；仅白名单五种effect。各135帧，不拉伸、不补帧循环。两种GPU效果使用全局帧时钟，其余转场后镜头使用从转场开始计算的局部时钟；原片对照使用相同源时钟，转场中点硬切。全部素材contain完整显示，竖屏两侧保持深色留白。

`track`是`[帧号,归一化x,归一化y]`人工关键点；目前仅9:16源视频的映射经过校准。换镜头必须重新看帧标定，不是自动触碰识别；当前选段为孩子操作/拿取物件，不宣称识别到精确物理接触。定位圈仅显示前1.8秒。推进入镜是二维实拍缩放和透明度衔接，不是场景三维重建。

## 上游来源与适配边界

Remocn固定提交`7aebcbe6514ed9e54e3a4a6786f83f8425a4a9af`，源码路径`registry/remocn/{whip-pan,push-through,paper-tear,grid-wave,canvas-presentation}/index.tsx`，仓库 https://github.com/remocn/remocn 。版权见`vendor/LICENSE`，来源逐文件核对见`upstream-manifest.json`。

前三款直接保存上游组件。grid-wave保留原始片元着色器和scene-shader绘制逻辑，仅将原来的实验性HTML截图输入换为OffthreadVideo解码纹理；删除未使用的HTML fallback，不以淡入淡出冒充立体效果。缺少WebGL时失败。Pixi效果绑定同样逐帧解码纹理，关闭自主ticker，时间和波心来自帧号/轨迹。

## 本地恢复

当前输入与真实来源在仓库根`.local/motion-audition-20261027/`：`cases.json`、`props/`、`sources.json`、`public/`。源文件路径和素材不提交。原片来自用户指定批次中选出的老人围观机器狗、孩子操作机器人片段；具体路径和SHA以sources.json为准。

从仓库根执行：

```powershell
& Haike_video/.venv/Scripts/python.exe Haike_video/templates/motion-audition-v1/render_auditions.py --task .local/motion-audition-20261027
& Haike_video/.venv/Scripts/python.exe Haike_video/templates/motion-audition-v1/serve_gallery.py --directory .local/motion-audition-20261027/gallery --port 14877
```

渲染器为此次已授权开发试镜入口，输出5条效果、5条原片对照和1条定位对照。完整解码、135帧、尺寸及视频流≥20Mbps逐条测量，记录`render-receipts.json`。源实现和输入清单SHA记录`source-receipt.json`。已完成输出可恢复，输入/源码改变必须用新task目录或显式移走旧输出，不能复用旧结果。

`gallery.html`提供循环播放、慢速、并排对照、黄色定位圈、多选、复制编号和JSON导出；仅本机127.0.0.1服务，不公开上传素材。JSON只是选择清单，不自动生产。当前页面/输出与UI检查记录在任务根`acceptance.json`；审美由用户最终选择，不把技术通过当作偏好认可。

后续正式成片须按项目统一队列执行；源素材不足、轨迹未校准、WebGL失败时停止，不生成假成功替代品。
