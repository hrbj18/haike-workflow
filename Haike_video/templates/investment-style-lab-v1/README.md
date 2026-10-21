# 招商视频模板3至10 · 四比例风格实验

本地原片重合成合同investment-style-lab-v1；本轮开发范围为8模板×4历史比例×12秒，共32条风格短样。当前各模板spec为implementation/ready，仅覆盖本轮32个实际12秒冻结输入；技术、Root scoped实际抽样视觉和原生作品接入通过，主观连续听审、真机和用户确认仍pending。旧卡片模板3、旧数字人口播模板6及其已完成合同保持独立。

## 艺术方向声明

八套由visual-style-direction和title-kinetic-typography设计机制落实为原创CSS/SVG；以下描述指向当前源码，不能替代实际成片审美通过。构图、材质、文字角色及运动至少三个维度应可辨；不是同一版式换色。

- [03 榛砂建筑](variants/03/招商视频模板3.md)：榛砂纸面与陶色阶梯构成建筑剖面；人物靠右矩形窗、宋体主标题和悬挑横梁形成正交负空间，沿构造轴装配后保持。
- [04 紫电声场](variants/04/招商视频模板4.md)：深紫唱片舞台、荧黄字幕带与倾斜椭圆轨带；人物为大圆角长窗，章节脉冲只作用装饰，11条等化器式图形按章节更新而非实时音频分析。
- [05 森林图鉴](variants/05/招商视频模板5.md)：绿墨图鉴、装订侧栏、五组矢量叶脉与错位浅纸底；人物为带纸边的完整照片窗，宋体题签与浅色字幕页维持观察手记气质。
- [06 琥珀票据](variants/06/招商视频模板6.md)：琥珀底上的奶油票据；虚线撕口、四个圆形冲孔、章节索引及细横线构成票面，直角人物窗与深棕字幕条稳定落位，不添加价格或虚构条款。
- [07 暗幕剧场](variants/07/招商视频模板7.md)：暗青黑剧场、铜色舞台细线和两侧暗幕；完整人物矩形窗在四拍间小幅重排，开场幕边收窄、末拍铜线收短，静止标题承担清楚阅读。
- [08 珊瑚折纸](variants/08/招商视频模板8.md)：珊瑚与米粉纸折面由五块背景多边形、照片切角及右侧斜条构成；青墨大字与完整人物照片窗彼此错位，几何重排不扭曲人物像素。
- [09 黑白字阵](variants/09/招商视频模板9.md)：黑白字体海报；环境字AI与窄长人物框、实体黑边栏形成张力，标题高字重、字幕反极性；只让一个黑栏与环境字形成少量结构变化。
- [10 酒红画册](variants/10/招商视频模板10.md)：米色摄影画册、酒红书脊和细页缝；宋体题签与大人物照片保持页边距，开场封面条退出、第三拍细框扩展、末拍书脊收窄。

## 执行和可替换输入

index.tsx注册HaikeInvestmentStyleLab与8个Studio预览Composition；这些Remotion预览ID不等于普通Studio选择器接通。唯一生产入口scripts/investment_style_lab.py→统一paused studio_investment_recompose队列→专属single-lane worker；不直接调用renderer绕过队列。

props为templateNumber、ratio、width/height/fps/durationInFrames、avatarSrc/source.mp4、audioSrc/mixed-master.wav、cues完整Caption兼容字段及start/end秒、brand、headline、cta、beatTitles[4]。每模板4拍标题均由本期beat_titles输入；headline等于首拍；非空cta可在phase3覆盖第四拍标题（03–06由shared.ReadableBeat、07–10由words实现）。本期32输入的cta全部为空，不添加源稿未说的引导，也不将非空CTA可选能力记为已测。品牌和字幕可替换，固定媒介题签/AI环境字/01–04章节号不是新商业主张。

参数唯一真值：layout.json声明30fps/360帧、四视觉拍[0,72,162,270]与四尺寸；shared.tsx声明metrics/contain/字画组件；两个style文件声明每个ratio构图及状态；后端render_profile固定20M ABR、CRF空、PNG、H264 slow/yuv420p/scale1。四比例输出1080×1920、1440×1800、1536×1536、1920×1080。输入原片字节复制且不变速，最终视频流复制，不为20M严格数值加入填充。

原声为主时钟，源视频静音；48k stereo真实母带来自既有v5本地混音器或严格来源复用。BGM/SFX素材、原声SHA、侧链/峰值/headroom和最后AAC测量必须有真实回执；无云调用、无付费再生、无发布。Windows系统字体仅本机使用并冻结存在文件SHA，不携带分发。原人物/场景和原内嵌内容是固化像素；不另生成门店、观众或证据图。

字幕整句入场后稳定，cue不足30帧取消入场；没有伪逐字时钟、模糊描边和数字人页脚。源码支持最多3显式行输入，本期短样目标≤2行须逐比例实看。45u底边clamp是本地画布规则，未声称平台安全；03–06下方字幕必须实际核验。实际字号、标题换行、可读hold与安全边界均以最终帧为准，设计包建议值不是实现证明。

每个variants/03..10含独立v1规格与runbook，清点实际独立对象/四状态/槽/音轨/操作恢复。执行runtime冻结TSX/types/layout/adapter/tool/FFmpeg及系统字体SHA；README/runbook/spec只作文档，prepare另记规格SHA，后补验证不会使旧请求失效。升ready须同一成片SHA的技术与实际视觉证据；连续听看、真机和用户确认分别记录，不从32条短样外推所有输入和平台。

## 方版几何快照修订

round2-square-spacing-20261020按实际源码同步：03、04、05、06、07、08的1:1人物窗下移或缩短，03–06标题上移，08方版标题字号基准降为78u再按行限宽；09/10人物和标题框保持；09左黑栏最大宽度由7%W收至4.8%W，避让6.5%W品牌锚点，扩展时钟仍为f162–170。相纸/细框随人物框派生，不移动原音轨或cue，不裁脸或改变contain。各runbook/spec保存对应四比例快照和最终源码SHA；名义9:16框不变。SourceWindow的空边使用各主题纸面/暗场色填补，源像素不重调色；09环境AI使用已冻结YaHei。

最终32请求集合为本任务`.local/codex-runs/investment-templates-03-10-20261020/jobs-final/round2/`；旧`jobs/`和`jobs-final/`根预片仅保留历史，不纳入最终样片通过范围。文档现以同一最终输出SHA的技术QA和Root scoped实际视觉补证ready，范围仅本轮最终32短样；连续听审、真机和用户确认仍待验证。已记录的CTA可选能力说明保持不变。

本轮规格为post-render补证；各variants规格final_validation和任务spec-finalization证据包绑定真实最终32请求/输出/原生job/work/version及完整HTTP同SHA。原prepare规格SHA快照与冻结requests/runtime保持原样；没有为补证重渲染、重复媒体审核、修改质量批准或发布。

本轮实测码率补证：32条均核验为20M ABR目标；09黑白字阵16x9的实际视频平均码率仅10.050515Mbps（15,379,794字节），不标称该文件实测20Mbps。原技术检查仍1312/1312通过；追加的是同一输出SHA的欠冲与量化观察事实，没有改媒体、原生结果、Root视觉、源代码或冻结请求，也未增加独立review/解码。其余实际值逐条见本期技术报告。
