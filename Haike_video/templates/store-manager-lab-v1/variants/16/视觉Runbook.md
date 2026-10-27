# 店长账号风格16 六秒开发样片

文档类型：video-template-runbook；标准版本video-template-v1；implementation/specification。

参数真值：[index.tsx](../../index.tsx)中style=16分支。[规格](video-template-spec.json)列出元素和显隐状态。[设计计划与规则](../../README.md)记录配色、字体、素材、字幕、混音和原生队列。本模板仅6秒开发测试，不代表完整30秒已验。

输入为已确认第一条音频0–6秒、高质量人物原片、S052/S082与S083/S081原片。人物不重启，素材每3秒切换，字幕使用实际词时间戳。改素材或布局后重新冻结与检查实际裁切。

scripts/store_manager_template.py --request <冻结request> --check校验；去掉--check复用归档，--fresh重新渲染。目录读根.local/store-manager/defaults.json；测试片放子目录。完成证据见本目录TEST-REVIEW.md（验收后保存）。恢复先查原任务和SHA，不重发付费数字人。

