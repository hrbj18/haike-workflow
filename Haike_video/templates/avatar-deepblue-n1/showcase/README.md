# N1 可分发无声开发样片

本目录仅使用项目自写的通用几何人物、素材说明卡与合成来源卡。没有真实人物照片、录音、克隆音色、旧成片或外部媒体。演示不是新闻事实、口型、有声同步或正式队列生产的验收。

`props.json` 固定15秒，四种模式各3.75秒。`generate.py` 原样复制上级实际 `index.tsx` 与 `layout.json` 到忽略的独立本地工作目录，使用已安装的 Remotion 渲染 `HaikeDeepblueN1`。人物SVG先转换为15秒无声视频，适配现有 Presenter；不修改生产组件。标题渐显、圆框互斥、截图红线及数据逐行显入均由同一实际组件执行。最后只保留视频流，去除渲染器可能附加的静音音轨。

在工作区根目录运行，使用已安装的 Node、Remotion、FFmpeg 与中文字体；不会下载依赖或调用云服务：

```powershell
.\Haike_video\.venv\Scripts\python.exe Haike_video/templates/avatar-deepblue-n1/showcase/generate.py --render
```

输出为前端 `public/assets/n1-public-sample-v1.mp4` 及四张 `n1-public-*.png` 实际帧；`n1-public-provenance.json` 记录输入、实现/布局、工具版本、文件SHA和技术检查。字幕采用明确手工演示时码，无ASR或配音。工作文件位于 `Haike_video/remotion-composer/.local/n1-public-showcase-v1`，不属于生产项目或作品库。

不加 `--render` 时只检查已有公开文件的SHA、绑定实现和视频技术指标。已有公开文件不相同时默认拒绝覆盖；确认重制后可明确加 `--replace`，并同步根分发器中的唯一文件/哈希白名单。不同操作系统字体和编码器可能改变像素或文件哈希，不能沿用旧SHA冒充同一产物。

私人旧样片及四帧继续留在根 `.local/release-private-previews-20261016`，与这里的公开来源和产物独立。模板3仍为版式示意，没有附带来源未确认的旧样片。
