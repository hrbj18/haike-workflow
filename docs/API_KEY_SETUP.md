# API Key 与一次导入配置

简易交付：安装ZIP与APIKey ZIP分别解压，保留并排的 `Haike_videoflow`、`Haike_APIKeys` 文件夹；双击安装目录 `00-install.cmd`，选择原服务或海客中转站，再双击 `02-start.cmd`。APIKey ZIP是用户明确授权的本地私有交付，仅该私有包含实际凭据，禁止上传GitHub；公开源码与安装ZIP继续使用空凭据模板。原服务配置可同时保存海客Key，实际路线由 `services` 决定。

本说明的“一个文档”可以集中填写多个 Key、服务地址和必要设置，由 Agent 一次导入。便携 ZIP 和 Git 中只放空凭据模板；填写真实值后的私有文档单独保存、单独交给用户，在用户本机读取，不放进 ZIP、Git、截图或报告。

完整解压后先准备下面的私有配置文档，再用第 3 节的一条命令初始化并导入。导入只写本机配置、离线检查，不调用付费服务，不克隆音色，不登录或发布平台账号。

## 1. 选择实际可用的服务路线

| 路线 | 配置含义 | 声音范围 |
| --- | --- | --- |
| 海客网关 | services.mode 和 audio_mode 均为 gateway，填写 haike 地址与 Key | 使用当前海客账号已开通的模型、音色和文件接口 |
| 全直连 | 两项均为 internal，填写自己的现有服务凭据 | 使用本机配置范围的直连音色，无需海客音色接口 |
| 网关＋直连配音 | mode: gateway、audio_mode: internal | 网关核验当前海客账号，直连配音和私有音色仍按该账号隔离 |

网关音色/克隆等接口未部署时，可明确使用已有直连路线；按实际选择配置和验收。直连费用是供应商成本估算，不是海客账户账单，供应商也不会替本应用强制执行预算。导入的限额用于本机报价与调用约束，实际费用以服务商结果和账单为准。

视觉分析默认由正在工作的 Agent 自身模型完成，`ai_relay.analysis_mode` 为 `agent`，无需配置文本或视觉中转 Key。Agent 必须实际查看素材代表帧和成片，再提交分镜与审核依据；离线配置检查不能证明这一步已经完成。配音、识别、数字人和素材下载仍使用对应服务。

实际制作时先由原任务取得音轨与真实 ASR，再读取草稿的 agent-materials 上下文。Agent 按实际转录、cue 编号和候选代表帧提交分镜及素材判断，收到 `resume_original_job` 后恢复原队列，复用已完成的配音和识别。操作顺序见[接入教程第 6 节](../START_HERE.md#6-恢复和联网素材)，字段及 `material-context`、`material-apply` 命令见[制作端规范](../Haike_video/docs/CODEX_VIDEO_BATCH.md)。

## 2. 填写一个私有 Markdown 文档

复制本说明为用户指定私有目录中的文件，例如 .local/user-setup/用户配置.private.md，填写下面唯一的 haike-config 块。它是 JSON，保留字段名、双引号及布尔值格式。可选项直接省略；空字符串视为未提供，保留已有非空值。

下面是默认全直连模板：当前 Agent 分析，百炼提供配音、克隆与字幕识别，RunningHub 制作数字人。核心只需自己的百炼与 RunningHub 凭据；腾讯、GPT 中转和海客网关 Key 均非默认必需。Pexels 是可选备用素材源，空 Key 可跳过，Agent 也可提交已授权且实际查看过的素材。把空凭据和服务设置改为自己的值；人物图可到制作任务时再提供。**示例预算为每日 15 元、每条 5 元，仅说明微元格式；执行前由用户确定本次预算和发布授权。** douyin_commercial_authorized 只有在用户实际具备对应使用授权时才设为 true。

```haike-config
{
  "schema_version": 1,
  "services": {"mode": "internal", "audio_mode": "internal"},
  "providers": {
    "bailian": {"api_key": ""},
    "runninghub": {
      "api_key": "",
      "base_url": "https://www.runninghub.cn",
      "workflow_id": "2094449979141218305",
      "workflow_profile": "infinitetalk_448x560_exact_clock_v2",
      "workflow_template": "config/runninghub/workflow-2094449979141218305.api.json"
    },
    "pexels": {"api_key": ""}
  },
  "ai_relay": {"analysis_mode": "agent", "network_sources": ["pexels"]},
  "crawler": {"douyin_commercial_authorized": false},
  "asr": {"provider": "bailian"},
  "budget": {
    "per_call_micros": {
      "haike/avatar": "4000000",
      "haike/bailian-asr": "100000"
    },
    "daily_limit_micros": "15000000"
  },
  "voices": [],
  "avatar_defaults": {
    "voice": "pub_longanwen_v3",
    "speech_rate": 1.15,
    "template_id": "avatar-deepblue-n1-v1",
    "target_duration_seconds": 25,
    "max_charge_micros": 5000000,
    "allow_graphic_fallback": false,
    "network_materials_enabled": true
  }
}
```

默认 asr.provider: bailian 明确选择百炼识别。导入只记录已选择、已启用与配置齐全，不伪造真实验收；首次授权任务可在 Key 和采购预算齐全后执行，verified 仍保留真实状态。兼容选项 gateway 沿当前服务路由执行：全直连时使用腾讯识别，网关模式使用网关识别，只有选择这一路线才需要对应配置。已有任务保留冻结引擎；失败仅按既有明确拒绝规则选择已冻结的本地备用，不自动换服务重发未知任务。

单条预算要覆盖各阶段合计。上例给数字人预留 4 元、字幕识别预留 0.1 元，单条 5 元中仍有配音余量；这些是本机预算，不是供应商实价。离线检查会拒绝阶段预留已经占满或超过单条上限的默认组合。

按实际需要补充同一个块中的以下配置，完整可用字段以 scripts/configure-user.py 的校验为准：

| 配置项 | 填写内容和条件 |
| --- | --- |
| haike | base_url、api_key；默认网关 https://8.138.207.71:17894/v2。只在所选路线需要时填写 |
| providers.bailian | api_key，可选 workspace_id；识别音频存储需要时配置 asr_storage、oss_endpoint、oss_bucket、oss_access_key_id、oss_access_key_secret |
| providers.tencent | 兼容选填：secret_id、secret_key，可选 asr_region、tts_region；默认百炼路线无需填写 |
| providers.runninghub | api_key、可选consumer_api_key、base_url、workflow_id、workflow_profile、workflow_template；默认性价比2094449979141218305，另一消费级Key仅供明确选择的高质量执行器使用，导入不切换默认 |
| providers.text-ai | 可选兼容路线：api_key、兼容 /v1 的 base_url、model，可选 vision_model；仅明确使用中转时填写，沿用服务实际地址。Agent 分析无需此配置 |
| providers.doubao-text | api_key、base_url、model，按用户已开通的文本服务填写 |
| providers.doubao-speech | api_key、voice_type、resource_id，按上游实际音色/资源填写 |
| providers.doubao-asr | api_key、mode、flash_resource_id、standard_resource_id；需公开音频地址的模式另填 public_base_url、media_signing_secret |
| providers.pexels / providers.pixabay | 备用素材来源的可选 api_key；Agent 模式缺少 Pexels Key 不阻断基础配置。实际选用该源搜索时须补齐 Key，否则提示补 Key 或自备素材，不降为纯图文 |
| ai_relay | analysis_mode 缺省为 agent；network_sources 推荐 ["pexels"]，已有合法采集环境/授权可用 ["douyin", "pexels"]。来源配置独立于分析服务。仅明确选 relay 兼容路线时，填 base_url、api_key、chat_model，或 use_text_ai: true 复用可选文本配置；image_model 与图片生成需另行配置、验收 |
| crawler | 可选 chrome_path、crawler_root、douyin_commercial_authorized、authorized_video_ids（视频 ID 的数字字符串数组）。授权与实际扫码登录分别检查 |
| voices | 已有私有音色映射数组，每项包含 alias、name、provider、voice_id，按上游需要填 model_id、resource_id、speech_rate。百炼私有音色需绑定其实际 model_id；腾讯 voice_id 使用数字字符串。alias 可供预设的 voice 引用；音色必须确实属于用户可用账户 |
| budget | per_call_micros 与 daily_limit_micros 使用正整数字符串；audio_pricing 可按具体供应商/型号记录克隆、配音估价。1 元为 1,000,000 微元。haike/text 预算仅供明确选用的旧文本调用，Agent 分析无需配置它 |
| avatar_defaults | voice 引用映射别名或公共音色 ID；可选 portrait_path 导入默认人物图，也可在制作时提供图片。其余字段如上，这里的 max_charge_micros 使用 JSON 整数 |

已有音色映射、图片导入和预设的离线初始化只适用于全直连 mode: internal。网关及混合模式要在实际账户身份核验后经现有音色中心配置，避免把私有音色写到错误账号。公共音色无需创建 voices 映射；导入映射只登记用户已有音色，不会购买或创建新音色。

## 3. Agent 一次导入并读回

便携包推荐在解压根目录的 PowerShell 一次执行：

```powershell
.\01-setup.cmd -ConfigDocument 'D:\用户私有配置\用户配置.private.md' -Full
```

替换为私有文档的实际绝对路径。该入口依次执行 prepare、plan、apply、check、完整 diagnose，任何一步失败都停止。默认保留已有非空配置；明确更新文档指定的字段时可加 `-ReplaceConfig`。

可直接把以下指令和私有文档路径交给本机 Agent：

> 项目位于【解压目录】，我的配置在【私有 Markdown 路径】。请先读根 AGENTS.md、START_HERE.md 和 docs/PORTABLE.md，用本说明的 01-setup.cmd -ConfigDocument 命令一次初始化并导入；使用其中明确选择的服务、音色、预设与业务配置，报告只显示字段状态。随后协助我完成三平台扫码，并在我已授权的预算、账号和时间范围内验收单条、夜间三条制作发布与汇报。沿用原任务编号，只有实际缺失且阻断执行的参数再向我询问。

需要分步检查时，Agent 在解压根目录运行以下三条 CLI；--file 指向填写后的私有 Markdown。便携包使用包内 Python，源码安装使用当前已准备好的 Python 环境：

```powershell
. .\portable\portable-env.ps1
& .\runtime\python\python.exe -s .\scripts\configure-user.py plan --file '.local/user-setup/用户配置.private.md'
& .\runtime\python\python.exe -s .\scripts\configure-user.py apply --file '.local/user-setup/用户配置.private.md'
& .\runtime\python\python.exe -s .\scripts\configure-user.py check --file '.local/user-setup/用户配置.private.md'
```

依次检查退出码和状态。默认保留本机已有非空值；要替换文档明确给出的字段，在先核对 plan 后为本次命令加 --replace。指定其他解压根目录时使用 --root；先核对目标目录，避免配置到正在使用的另一副本。输出仅记录字段路径和状态，报告只保存这些脱敏结果。

plan/apply/check 都是离线操作。check 用 configuration_complete 和 missing 报告配置缺项，配置完整时退出码为 0，并输出当前 analysis_mode。默认 Agent＋百炼路线下，ai_relay、tencent_asr、haike_key、pexels_key 或 bailian_asr_verified 为 false 均不表示基础配置缺项；百炼 Key、启用状态和预算仍须齐全。未设默认人物图可显示 default_portrait: false，制作时再提供即可。execution_verified 仍为 false，因为这里不验证 Key 的云端有效性、不伪造音色/ASR 验证、Agent 视觉审核或平台登录，也不发起制作发布。导入后启动或重启本副本，再从现有接口读取本次服务能力、音色和预设；根据结果推进下面的真实验收。

仍可在工作台“API 设置”→“统一 API 接入”手动录入海客网关与 Key，点击“保存并测试连接”。这一步查询 Key、额度和已开通能力，不产生制作费用；直连路线使用导入的现有服务配置，不要求先部署海客云端音色接口。

## 4. 三个平台分别扫码

在“API 设置”下方的“平台账号”中，依次打开抖音、快手、视频号的“管理登录”，选择平台并扫码，按提示完成手机确认或平台验证。登录记录保存在这台电脑，用户无需复制 Cookie。

点击“检查登录状态”，分别查看素材与“视频发布”。绿灯“最近检查正常”表示最近 8 小时有成功检查记录；搜索、下载和发布前仍验证实时状态。黄色表示待确认，红色“需登录”表示平台明确要求重新登录。

新用户可明确使用 Pexels 联网画面来源，提供自己的 Pexels Key，无需为此代填抖音采集授权。当前联网素材门禁仍会真实检查已选择的抖音素材账号，请扫码后选作素材账号。另选抖音画面时，还需可选采集环境、Chrome 路径及适用的业务/视频使用授权；快手和视频号提供分享链接下载及发布能力。开启联网素材后找不到合适画面会暂停待补，不悄悄改为纯图文。

## 5. 单条与夜间三条的验收

1. **单条。** 提供自己有权使用的人物图、一个音频和一句制作要求。完整口播音轨直接制作数字人，无需先克隆或 TTS；声音样本则由 Agent 先写实际稿件，克隆/选择可用音色，再配音制作。读报价并在授权预算内执行，核对实际成片、作品和原队列结果。
2. **夜间三条。** Agent 读取本次预设，冻结三条选题/稿件或完整音轨、预算、目标账号和授权时段，按根 START_HERE.md 的批次入口推进制作、检查和原计划发布。夜间唤醒由 Agent 宿主提供，每次可用 advance 推进原任务并写出报告。最终交付三条成片/封面、逐平台回执和 report_path 指向的汇报文档，排队、提交、公开确认分别写明。

人物图使用 PNG/JPEG，宽高至少 256 像素、文件不超过 20 MB。完整音轨支持 WAV、MP3、M4A、OGG，数字人路线最终音轨不超过 120 秒；克隆样音建议使用 5 至 60 秒清晰单人讲话 PCM WAV。批次 CLI 支持“实际稿件＋音色”，也支持 audio_path 完整录音，无需为完整音轨另填音色/配音模型/倍率。

两项核心验收的通过条件和恢复规则见根 START_HERE.md 第 8 节。只做 mock、静态导入或取得“任务已创建”结果时，明确记录对应范围；真实付费、发布和公开核验使用实际回执证明。保留原任务编号和已完成产物，失败从原恢复点继续。
