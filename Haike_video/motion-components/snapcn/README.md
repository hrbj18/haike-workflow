# Snapcn 本地动效积木

文档类型：video-template-runbook；标准版本：video-template-v1。
模板规格：[规格](video-template-spec.json)。本目录是53个独立效果的开发演示库，尚非一套自动编排口播模板。

## 来源和本地接口

免费组件与共用UI完整保存在`upstream/registry/`，上游提交、每文件SHA256和MIT许可见[UPSTREAM.json](UPSTREAM.json)与[许可证](upstream/LICENSE)。53项的中文名称、类别及用途见[catalogue.json](catalogue.json)，原生参数和时钟保留在各项`config.ts`。基础Input、Caret和主题工具作为内部依赖一并保存。

`definitions.generated.ts`由固定注册表生成；[Demo.tsx](Demo.tsx)绑定中文示例与本地素材；[Gallery.tsx](Gallery.tsx)提供分类、搜索、单播放器、自动连播和复制调用语句。Agent可调用`Haike_video/scripts/motion_components.py list`查询同一目录，或读取本地预览服务`GET /api/catalogue`。传入库外ID不执行代码。

原始源码不改写。别名、共享React/Remotion解析、离线字体和FontFace资源路径由`compat/`及两个构建器统一处理。中文使用调用方已加载的本地字体；常规Google拉丁字体采用本地字体回退，不能声称与上游字体逐像素一致。字体变换特效的16份FontFace资源缓存到本机，保留真实字体区别。

## 制作和恢复

1. **输入与核对。** 已有完整源码可离线读取，无需重新下载。`scripts/vendor_snapcn.py`仅为维护时刷新同一固定提交，已有文件不同会停止；它不安装或执行上游网站，也不获取Pro源码。`package.json`只声明组件必需的附加依赖，React与Remotion使用项目现有宿主。
2. **绑定素材。** `scripts/prepare_snapcn_demo.py --source-dir <本地演示输入目录> --output <私有预览目录> --ffmpeg <实际ffmpeg>`准备五路实拍、八张照片、本地字体和自主绘制的演示标志，并记录原始源SHA、派生素材与字体SHA。输入目录需要robot/store/children/dog/robot-duo.mp4和font.ttf，失败时保留已完成派生物，核对来源后继续。私有实拍与生成预览留在忽略目录；不随公共源码分发。
3. **交互预览。** 用项目实际Node运行`motion-components/snapcn/build.cjs build <私有预览目录>`；`scripts/motion_components.py serve --output <该目录>`返回仅绑定127.0.0.1的页面。播放器使用原生1280×720与各组件自己的24/30/60fps、帧数；音频关闭，不调用生成供应商。手机和图片等素材槽使用本地实拍，字幕与数据为示意。CSP限制所有媒体、字体和连接到本机。
4. **代表帧检查。** `render.cjs bundle <私有预览目录>`生成与播放器共用Demo的检查包。随后通过指定安装副本执行`scripts/motion_components_preview.py --install-root <安装根> --data <私有预览目录>`。该适配器登记到现有统一队列，冻结源码、依赖锁、素材和检查包SHA；领取本次精确暂停任务，生成每项22%/55%/83%位置的三张代表帧及封面。它不是绕过队列的独立制片命令。
5. **核对与交付。** 读回私有目录的`preview-job.json`定位原项目、队列和frames/results.json；逐项检查技术与实际画面后记录review.json。成功项写到preview-index.json供页面展示真实封面。源码、素材或字体规则变化要重建检查包并另冻请求，旧证据保留。构建或渲染中断先读原日志，不重复调用任何付费阶段。

## 当前交付范围

本轮浏览器逐一切换53项，当前演示调用同一固定版本的实际源码。技术帧生成、语义视觉检查及交互回执分别记录在工作区`.local/snapcn-gallery/`；以其中最新review.json为准。初版远程默认素材和渲染FontFace路径问题的旧队列保留，不作为修订版验收。

本轮只交付静音效果演示和本地可复用源码；任意新素材适配、口播时钟编排、正式模板前端上架、更新包与另一台物理机安装尚需各自验证。用户选择效果后，后续模板作者在现有音频/数字人/素材及统一队列上组合这些组件。

## 维护与检查

固定接口为组件ID、原生config和宿主传入props。新增素材槽在Demo绑定并记录来源；不要把上游默认远程URL当作本地素材。预览和检查包使用相同源码与资源改写方法。维护后运行`tests/backlot/test_motion_component_library.py`、根`scripts/check.py`，并核对实际播放器和受影响代表帧。
