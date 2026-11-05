# 纸感末场 /3 操作契约

文档类型：video-template-runbook
标准版本：video-template-v1
模板规格：[独立候选规格](template-spec.json)

精确合同、引擎及固定 pack/reference 见 COMPONENT.json；几何与时钟公式真值为
observed-paper-controls-v3.js 和 backlot/motion_public_paper_observed_v3.py。
template-spec.json 是实现规格，不把静态状态标为 ready。

1. 输入：旧纸感原 input 的完整脚本、WAV、ASR、真实视频、人物及来源回执。
   只改 engine 和独立 work_root，保存父来源关系；不要重用旧 /2 的请求/批准。
2. 核验：从仓库根运行
   `Haike_video/.venv/Scripts/python.exe -B Haike_video/scripts/motion_public_paper_production_v3.py --check --input <本期JSON>`。
   输出为 validated、3600帧/60秒（原输入），不启动浏览器/FFmpeg/模型、不入队。
3. 后续接线由主控登记固定只读 adapter/registry 与公共 worker/queue 后完成。
   独立 prepare 保存新身份；默认 preview。执行仍须主队列明确领取同一父，
   并在 preclaim/run、真实租约/取消、媒体前后、登记前后重验。
4. 后续授权预览保留所有原动作取样，并加入 duration-.92、-.2、-.1、尾帧；
   本期对应59.0833/59.8/59.9/59.9833秒。实际逐图审阅全清单后明确 approve，
   才能冻结 render 的具体批准。reject/changes_requested、缩清单或撤回均阻断。
5. 失败保留原父/场地；缓存检查、明确 render revision、具体批准和完整预览
   witness 沿 R2 原算法。缺真实输入、来源漂移或不足的人物窗口直接阻断，
   不变速/冻结补帧，不调用旧引擎作为回落。

完成条件：静态与接口通过仅表示候选可核验；新实际预览、完整编码、原样式
对照、连续听看和正式接入分别验收。当前不执行第3–5步的媒体或生产入队。
