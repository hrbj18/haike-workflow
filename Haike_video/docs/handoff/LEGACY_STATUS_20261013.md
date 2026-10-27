# 当前项目状态

更新时间：2026-10-13

## 主线状态

- **百炼**：克隆入口并入音色管理，上传/恢复83项过；V2升级已验，真实OSS/创建未验。
- Qwen改为可选安装；RTX3050实测28秒，88项过；v3增补。
- **二剪**：按素材左/右避让＋字幕联动、稳定/锁定/不确定隐藏；D待审，零新云费；V3/V2保留。
- **素材解说**：`/material-commentary`；理解→选位，87项过；`docs/MATERIAL_COMMENTARY_V1.md`。
- **素材库V1.1**：`/material-library/manage`；CAS/修复/归档/冻结引用/台账；粤仔2原片2衍生、7段9镜头。`docs/MATERIAL_LIBRARY_MANAGEMENT_V1_1.md`。旧九秒保留；950/DevDay三可审、一fact_pending，ds4.1/新采未测。

- **统一队列**：SQLite单通道，优先级/FIFO/幂等/恢复；父串行，双主持落账后并行；`review_ready`待观看。
- **有数字人V1.8**：整数PCM+25FPS切割，Whisper仅诊断；`exact_frame_clock`阻断漂移。供应商仅记录当次`phases`，新任务重付费；换镜预览排`full_preview`。
- **无数字人V1.6**：`source_audio_only`支持逐条定时字幕；新项目−9、旧项目−14 LUFS。
- **多标题/新闻层V1.2**：`story_headline_overrides`与普通层共用revision/CAS/FFmpeg，保存仅重做本段。
- **二次精剪V7/推荐v2**：VAD间隙切口，字幕随语音；句间0.30秒，`gap_policy=any`；导出无字幕片/SRT/`cut-list-v1`/FCP7/OTIO；权重40/25/20/15，默认优先时间长。
- **成片二剪V1**：`/published-clips`，69转写、95候选/2确认，真值0/10，歌舞未验；选材/排序/切口/原声/CAS/冻结/队列已接，两源三段10.8秒待审；见`CODE_MAP.md`。
- **音频默认**：人声+8/BGM−6dB/成片−9LUFS；`highpass→EQ→volume(+10)→alimiter`；`I=min(目标,−2.0−波峰因数)`，见`backlot/*_preferences.py`。
- **竖屏文字层**：底边<0.80（64号/y0.75）；单层单色，不自动换行/裁字；改文案须测。不切ASCII串，行首整串上限2×预算。
- **研究包**：CopySkill只读；`current.json→pack_path`；不扫`.staging`/不入队列；`nodes:[]`，见有效决策。
- **素材复刻契约**：`schemas/remake-spec-v1.json`＋离线`backlot/remake_project.py`；选材权归项目（`MATERIAL_SELECTION_POLICY_V1_ZH-CN.md`）。
- **四平台分发**：后台核验发布；抖音3:4封面`cover_path`（`d2a55c7`；`backlot/publish_adapter.py`）。★视频号封面只改一次、不可撤回，先`--dry-run`。
- **窗口复刻**：同名手册；字幕开关待修。
- 口播图文29秒待听审。

## 生产合同

- InfiniteTalk `config/runninghub/workflow-2094449979141218305.api.json`；新任务Plus48GB，每角色一次；双角色冻结5元，旧任务沿冻结配置。
- 未知 RunningHub 响应进 `ambiguous` 并停止，禁止重复提交。
- 响度验收 `|I−target| ≤ 1.5` 且 `TP ≤ −1.0`；正式渲染不达标直接 raise。

## 阶段

`dev` 持续开发中；`main`/`v0.1.1` 仍为 `50352aaa`；私有数据不进 Git。

- **作品管理V1**：14756；旧台未重启。YC V4/历史9作入库，资料/交接/三平台账号已备；来源/发表授权待确认、未真发/删。`docs/HISTORY_WORKS_V1.md`。

- `gpt-claude-0923` v7：抖音87、快手88、视频号90已发，89取消。
- 9/24 `sub3-0924-nvidia-glass-substrate`：9秒/3景，待人工/版权复核、期限核实。
- **数字人口播（9/28）**：`meta-muse-amazon-yaya-20260928` v008 正式片 107.8 秒；抖音 #105、快手 #106 已入队，作品核验待完成。
- **檬檬＋原片（9/29）**：`musk-age-of-beyond-mengmeng-20260929` 195秒/11秒开场；三平台已发布、标题详情已更；视频号新作核验/旧作删；证据`artifacts/publishing/`。

## 最近验证

- **API/口播**：模板3可审、报价40测过；Key实扣待验。项目库已接口播页，上传/草稿过，生成待接（docs/ui）。
- 素材管理112项过；旧ASR文案断言1失败。旧工作台4失败（OpenCV5接口/静态重叠）未改；百炼32项过。
- 二次精剪 v7 三版 >0.30 秒空隙：25/18/24 处 → 0/1/0 处。
- ★ `final_review.audio_spotcheck` 归一化前取值误报；以 `loudness.integrated_lufs`/`true_peak_dbtp` 为准。

## 下一步

1. 人工观看本轮各版本预览，含 `gap_policy=any` 切口听辨，只到待审，不发布。
2. 产品决策：排序「优先时间长」与首次切片「单互动 ≤180 秒」冲突时跳过或放宽上限。
3. `dev` 独立副本/Linux预发布验收后合入 `main`。
4. 索引真值、长直播、歌舞未验。
