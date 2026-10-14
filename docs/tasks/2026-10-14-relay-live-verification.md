# 2026-10-14：云端Key与素材链路实测

工作台已保存用户新提供的Key（仅后台0600，界面末四位snII），地址为`https://8.138.207.71:17894/v2`。TLS验证正常；Key日预算¥100、到期2027-01-12。供应商Key和客户Key均未提交Git。

## 云端调用

实测总授权上限¥0.01；每步报价、原调用意图及任务编号持久保存。重跑验收只查询原任务，不重新提交供应商。结果在账户中心「调用账单」可见。

| 能力 | 结果 | 金额/限制 |
|---|---|---|
| CosyVoice | 成功；10字符、音频1.44秒，完整下载和解码 | 实扣¥0.001200 |
| 腾讯配音 | submission_unknown，未取得结果 | 冻结¥0.000270，禁止重复提交 |
| 腾讯识别 | 单声道PCM准备及上传成功；submission_unknown | 冻结¥0.001459，禁止重复提交 |
| Pexels | failed，供应商确认失败 | ¥0；需云端管理员核对供应商配置 |
| RunningHub数字人 | 报价409/model_unavailable | 未开通，未提交付费任务 |
| 文本/视觉 | 报价409/model_unavailable | 未开通 |
| 插画 | 报价404/model_missing | 云端版本尚无haike/illustration |

本次共实扣¥0.001200、冻结¥0.001729，可用余额¥19.997071。冻结不等于消费，需管理员核对原供应商回执后结算/释放；本次未操作充值或手动调整账本。平台公开available代表配置/价格开通，不能代替真实交付验收。

CosyVoice返回HTTP OSS音频链接，原下载器只接收HTTPS；已为已知DashScope输出域名改为同域HTTPS，保留签名参数。又发现本机TUN将域名解析到198.18/15：仅对已知阿里/Pexels媒体域名使用Cloudflare HTTPS DNS核对公网IP，并固定实际连接IP、保持原域名证书校验；其他私网地址仍拒绝。已下载原付费音频，未再生成。公网IP固定也避免校验后重新DNS解析。

## 生图与抖音

- 用户指定的供应商/v1鉴权和25模型列表通过，包含gpt-image-2、gpt-image-1.5、gpt-image-1；gpt-6-luna图片理解已在前轮真实验收。
- 新的gpt-image-1.5及gpt-image-1各一次竖屏中等质量单图调用均502/upstream_error，没有图片。后台显示这两型号限流至10:28/10:29；gpt-image-1诊断日志为账号池仅一账号、筛选后没有可用账号。不能把列表存在当作可调用，也不能据此宣称采购费为零。原gpt-image-2未知请求没有重提。
- 默认备选配置现为gpt-image-1.5，插画补齐仍关闭。三个模型均支持管理员选择；切换不改旧任务/旧镜头模型。成功验收需绑定模型、地址和凭据，任何一项改变均失效；单图回执及图片尺寸验证通过才开放。
- 用户自行完成专用Chrome登录后，项目记录确认；一次MediaCrawler办公桌检索成功，返回14条候选元数据。没有下载第三方视频，保留逐条使用权审核。正常任务仍为用户素材→抖音→Pexels→明确允许的插画。

管理员单图验收命令（供应商消耗已确认后执行一次，原失败编号不能重提）：

```sh
python scripts/configure_studio_ai.py --image-model gpt-image-1.5
python scripts/configure_studio_ai.py --verify-image --verification-id after-provider-review-20261014-01 --confirm
```

命令在实际安装副本Haike_video执行；不把Key写命令行。先核对限流及原请求，再确定是否允许新的供应商消耗。正式客户包仍不能包含本机AI供应商Key；统一商用交付需要云端上线文本/插画适配、试用配额、报价续期，并核对腾讯/Pexels及数字人开通条件。本轮没有更新云端代码或开通价格。

## 验证

67项制作/分镜/下载合同、74项网关、13项前端共154项通过；嵌入构建、源码检查通过。下载测试覆盖已知OSS HTTPS升级、私网/伪装域名/凭据拒绝、fake-DNS公网核对和固定IP原域名TLS；模型切换测试覆盖验收凭据绑定、旧未知意图和全任务模型冻结。测试本身使用假供应商；上述真实操作为本次用户授权的独立验收。

## 后续调整：移除腾讯TTS、核对GPT识别

用户要求移除腾讯精品配音：工作台/API设置不再展示，后端在上传和报价之前拒绝新腾讯TTS请求，旧报价也不能创建新的生成任务。旧草稿明确提示重选CosyVoice或上传音频，不自动换模型；原受理任务、报价和未知账单保留，腾讯ASR共享凭据未删除。能力计数仅计算工作台展示的五项。

生图顺序为gpt-image-2→gpt-image-1.5→gpt-image-1，管理员通过私有配置选择和单图验收；未知提交不自动跨模型重做。此前两个备选的502和当时限流是原测试记录，不代表限流一直持续。当前没有成功图片验收，未开放插画补齐。

GPT识别实测：供应商模型列表包含gpt-6.1-sol，无专用whisper-1、gpt-transcribe、gpt-4o-transcribe系列。使用原CosyVoice已生成的1.44秒普通测试音频（不是用户人声）发一次multipart `/v1/audio/transcriptions`，指定6.1-sol、verbose_json和segment；连接被关闭，未返回转写文字或时间戳。意图及摘要已私有保存，状态unknown_no_retry，未重提；不把采购消耗记作已知零元。

[官方gpt-6.1-sol规格](https://developers.openai.com/api/docs/models/gpt-6.1-sol)只支持文字/图片输入与文字输出，没有音频输入和转写端点。[官方转写指南](https://developers.openai.com/api/docs/guides/transcription#choose-a-specialized-capability)把词级时间戳/SRT/VTT列为Whisper专用能力。因此目前不能直接换成6.1-sol；可用专用ASR/Whisper或本地识别对齐取得真实时钟，再用6.1-sol校对文字和安排分镜。

落地尚需：上游提供真实转写接口和模型、句级/词级时间戳或强制对齐、云端统一Key适配及赞助配额/后续账单策略、真实音频验收。当前继续保留ASR门，云端数字人未开通和Pexels失败仍是原有阻塞。

本轮44项后台和14项前端测试通过；构建、源码检查及交接文档预算通过。实际14754页面仅列CosyVoice，API设置去除腾讯TTS后为3/5项配置开通；配置开通不代表所有供应商真实交付通过。源码/安装副本/嵌入前端已同步，发布服务正常，未修改用户草稿。

## 后续配置：RunningHub 与 Pexels

用户新提供的RunningHub Key只在私有文件保存，并通过官方`POST https://www.runninghub.cn/uc/openapi/accountStatus`验证：HTTP200、code0、NORMAL账户、有可用额度。未上传人物/声音，未创建收费任务。参考[官方账户接口](https://www.runninghub.cn/runninghub-api-doc-cn/api-425748943)。

云端管理员已保存该Key到RunningHub供应商加密配置，地址`https://www.runninghub.cn`，工作流`2094449979141218305`，档案`infinitetalk_448x560_exact_clock_v2`，开关开启。保存后的供应商页显示已保存/开启。`haike/avatar`仍为cost_pending：缺实际采购计价，没有擅自填零或将旧双主持费用上限当采购成本。已向用户询问单次成本或计价方式，计划按既定1.5倍率发布售价。

[Pexels官方API页面](https://www.pexels.com/api/)现在明确显示“New API key issuance is currently paused”，Get Started禁用。Chrome已打开并保留Pexels登录窗口，等待用户登录核对现有Key；没有提交注册条款或操作密码。原上传文件含Pexels Key，本机一次带Key的视频检索HTTP403；无Key的公开诊断请求也403，text/plain，不能据此宣称Key无效。未替换云端Pexels配置、未下载素材。可先验证已有Key和访问限制；无已有Key则需等待或联系Pexels官方，不能保证登录后马上获发新Key。
