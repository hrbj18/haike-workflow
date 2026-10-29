# 模板6 v005：重建原创声音资源

本目录提供模板6 v005原创声音的源码重建入口。原DSP脚本、包装入口与本文在本期六条原生测试完成后新增；原先冻结的28个运行时文件（含README／PROVENANCE）保持不变，不放宽Git媒体白名单。完整成片的就绪范围由独立规格和同名runbook记录，声音重建不自动提升其他验证维度。

公共源码分发包含 `generate_sound_pack.py`、`rebuild_sound_pack.py`、`PROVENANCE.json` 和本文。七个canonical WAV继续受全局`*.wav`忽略规则管理，不假称公共Git源码已携带音频。用户人物、原声、真实互动视频和系统字体均不随模板公共资源分发。

`generate_sound_pack.py` 与本次原DSP脚本逐字节相同，SHA为 `e2477be1613aa6b6095ca2c10e7bd4305cab14df31f747582b685fd3a9354ee4`，与PROVENANCE一致；种子20261020、音符、合成、归一化、导出函数不改。包装器按已存在的 `Haike_video/lib/ffmpeg_locator.py` 定位项目，使用既有NumPy与FFmpeg，把输出指向调用者明确指定的绝对本地目录，不依赖本次任务目录深度。

## 重建与安装

先按仓库入口准备本机运行时。原包使用NumPy 2.5.3与本机FFmpeg；源WAV为48kHz、立体声、PCM24。不同NumPy、FFmpeg或系统的文件字节一致性未验，不因为代码／seed相同就声称异机复现通过。任何生成文件SHA不符必须保留诊断且不能安装；不要擅自把来源清单更新为新hash来绕过门槛。

仓库根完整生成，再核对并安装七个canonical到当前模板的ignored本地目录：

```powershell
Haike_video/.venv/Scripts/python.exe Haike_video/templates/avatar-investment-a-v6-art-v5/assets/sound/rebuild_sound_pack.py --output-dir "D:\本机输出\template6-original-sound" --install-canonical
```

仅在单独目录验证核心音效，可用：

```powershell
Haike_video/.venv/Scripts/python.exe Haike_video/templates/avatar-investment-a-v6-art-v5/assets/sound/rebuild_sound_pack.py --output-dir "D:\本机输出\template6-sfx-rebuild" --sfx-only
```

也可用 `--theme main-118`、`--theme red-124` 或 `--theme documentary-100` 单主题增量生成；同一显式输出目录可积累三主题及音效。没有`--install-canonical`不会写模板资源。安装前必须本地输出目录中七个注册文件全部存在并与PROVENANCE逐SHA一致；未知hash、缺文件或已有不同canonical文件都拒绝，不覆盖旧声音。输出目录不能位于模板源码目录或项目根。可选辅助音效虽会由原DSP一并生成，但不是本期七个安装文件。

本地输出包含分轨／母带、节拍网格、分析日志、manifest、asset-checks与包装器 `rebuild-receipt.json`。本期母带和技术记录只对应原实际文件；重建后的使用仍需重新准备请求／冻结SHA，不能把重建等同于旧队列身份。

## 已有原视频的默认复用路线

本期v005针对已有完整MP4做艺术重合成。后续同类已有原片任务优先使用v005的BGM／SFX／字幕动效版；保留v004供对比。模板6原图片＋音频的付费人物生成路径仍按v002合同，不能据此外推普通Studio UI已提供六风格选择或新收费人物路由。

声音主题与六风格映射：

| 风格 | 主题 | 本期BGM底增益 |
|---|---|---:|
| community-showcase | main-118 / 铜流 | -8.5dB |
| blue-editorial | main-118 / 铜流 | -9dB |
| optical-cinema | main-118 / 铜流 | -10dB |
| red-manifesto | red-124 / 即刻向前 | -7.5dB |
| silver-launch | main-118 / 铜流 | -10.5dB |
| documentary | documentary-100 / 日常向前 | -11dB |

这些底电平是本期真实输入的设计，不保证新原声同样合适。音乐侧链阈值／比例／attack／release、语音一次-2.5dB、母线限幅与最终AAC真峰门槛，从 `backlot/studio_investment_audio_v5.py` 的 `PROFILE` 读取。音乐铺在人声下面，实际人声驱动压低；音效每事件显式增益，音效过密或遮蔽时调整音效计划，不移动语音或词钟。混音预览与最终mux必须用同一个冻结的48k立体声PCM16母带，最后不再叠一次volume/loudnorm。

## 音频计划输入示例

下面是JSON形状示例，不包含可直接制作的占位SHA或假词索引。实际路径、七个SHA和source_label从本机canonical的PROVENANCE读取；每个锚点索引必须先查本期真实words／cue／chapter数组，不能照搬旧稿索引。`--audio-plan`为v5准备阶段必填输入。

```python
from pathlib import Path
import json

sound_dir = Path("Haike_video/templates/avatar-investment-a-v6-art-v5/assets/sound").resolve()
catalog = json.loads((sound_dir / "PROVENANCE.json").read_text(encoding="utf-8"))
assets = {a["id"]: a for a in catalog["assets"]}
theme = assets["red-124"]  # 改为本期方向对应的真实主题

def identified(a):
    return {"path": str(sound_dir / a["relative_path"]), "sha256": a["sha256"], "source_label": a["source_label"]}

plan = {
    "version": "sound-motion-v1", "mix_profile": "speech-led-v1",
    "music": {**identified(theme), "offset": 0, "loop": False, "gain_db": -7.5, "fade_in": .12, "fade_out": .75},
    "assets": [{"id": role, "role": role, **identified(assets[role]), "sync_ms": assets[role]["sync_ms"]}
               for role in ("dong", "impact", "whoosh", "tick")],
    "events": [],  # 完成真实索引选择后填入；空数组会被入口拒绝
}
# 例：查找到本期完整金额词的真实word索引money_word_index后，才追加：
# plan["events"].append({"id":"offer", "asset_id":"dong",
#     "anchor":{"type":"word", "index":money_word_index, "boundary":"start"},
#     "pattern":"triple-hit", "gain_db":-9})
```

raw事件严格只有 `id/asset_id/anchor/pattern/gain_db`；anchor严格只有 `type/index/boundary`，只支持真实word／cue／chapter的start或end。三击为同一锚点上0／0.12／0.24秒编辑重复，不是三个词；清单各项应分别single并取各自真实词索引。不要拿辅助预合成三连的0／0.14／0.29秒波形替代命名pattern。

whoosh的sync_ms430只将声音播放起点提前430ms，负起点裁素材头，原anchor／timeMs／视觉ceil帧及语音／字幕不动；其余三种核心音效sync_ms为0。对新的原片先检查原稿条件、词钟、片长、素材来源与声音计划，再沿v5CLI prepare→submit→run／resume，经统一单lane完成。技术、实际动态视觉、连续听看、音素口型、真实平台与用户确认分别验收。所有本地重建和重合成均不自动发布。

## 当前复现记录

原声音包已在本机生成并由来源清单保存七个canonical SHA。2026-10-20用包装入口在独立忽略目录执行 `--sfx-only`：原DSP生成七个音效，四个已注册核心音效与来源清单逐SHA相同，未执行安装。对应 `review/rebuild-smoke-sfx/rebuild-receipt.json` 保留实际指纹；本包装入口尚未重建三配乐主题，另一台机器复现也待验证。本文不提升成片QA、主观听审或发布批准状态。
