"""Regenerate documentation specs from the authored layout manifest, never render media."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'index.tsx'
SHASUM = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
LAYOUTS = {
  22: {'name':'橙紫开幕','main':[42,206,1008,1302],'detail':None,'title':[1087,250,306,850],'title_size':113,'sub':[1096,1215,280,250],'sub_size':44,'palette':['#FF812B','#3D1C91','#FFFFFF'],'rule':'前120帧且无人像时，main改为[42,354,1356,1154]，title改为[52,108,1326,198]/140px并去换行；之后回右侧短旗。'},
  23: {'name':'冰蓝樱桃证据','main':[500,206,898,1302],'detail':[44,206,430,242],'title':[60,548,400,610],'title_size':100,'sub':[64,1240,395,244],'sub_size':43,'palette':['#CCF2F5','#9F2144','#FFFFFF'],'rule':'detail明确覆盖当前帧时，左上16:9窗显示横片；缺detail时隐藏，title上移至[60,320,400,870]。主窗尺寸保持通高。'},
  24: {'name':'酸橙深蓝错层','main':[46,242,838,1266],'detail':[908,660,486,848],'title':[940,250,420,350],'title_size':95,'sub':[54,94,1300,98],'sub_size':50,'palette':['#DDF357','#20395D','#FFFFFF'],'rule':'detail有覆盖才显示；无detail时主窗扩至[46,242,1040,1266]，title改为[1122,360,272,930]。两实拍窗不重叠。'},
  25: {'name':'玫粉孔雀接力','main':[264,198,1124,1310],'detail':None,'title':[42,284,184,990],'title_size':108,'sub':[289,76,1060,94],'sub_size':48,'palette':['#FFACC9','#00565C','#FFFFFF'],'rule':'主实拍与同音轨数字人短段共用右大窗；左侧标题窄柱每行一字，2—4字。'},
  26: {'name':'钴蓝杏黄满场','main':[42,264,1356,1244],'detail':[1002,320,344,442],'title':[62,76,1300,150],'title_size':106,'sub':[64,1400,1310,88],'sub_size':40,'palette':['#F7CF58','#264EC4','#FFFFFF'],'rule':'全宽大窗优先横片或已审cover；detail仅显式区间显示右上8px描边小窗；sub在主窗下缘深底白字。'},
}

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

for number, d in LAYOUTS.items():
    variant = HERE / 'variants' / str(number)
    variant.mkdir(parents=True, exist_ok=True)
    rows = [
      ('ground','background',[0,0,1440,1800],0,None,None),
      ('brand','text',[52,26,1336,48],1,30,None),
      ('main_backing','video',d['main'],2,None,'main_slot'),
      ('avatar_stream','avatar',d['main'],3,None,'avatar_slot'),
      ('title','text',d['title'],4,d['title_size'],'title_slot'),
      ('support','text',d['sub'],5,d['sub_size'],'support_slot'),
      ('speaker','text',[d['main'][0]+24,d['main'][1]+d['main'][3]-78,min(460,d['main'][2]-48),56],7,30,None),
      ('caption','subtitle',[54,1542,1332,132],8,56,'caption_slot'),
      ('location','text',[54,1700,1332,62],9,36,'location_slot'),
      ('master_audio','audio',[0,0,1,1],10,None,'audio_slot'),
    ]
    if d['detail'] is not None: rows.insert(6,('detail','video',d['detail'],6,None,'detail_slot'))
    elements=[]
    for eid, kind, box, z, size, binding in rows:
        desc = {
          'ground':f"纯色ground {d['palette'][0]}，无纹理、闪屏或循环装饰。",
          'brand':'固定品牌“海客AI社区服务站”，无外部logo和装饰性序号。',
          'main_backing':'props.shots main连续轨的源画面；src原文件不预压缩，固化招牌/人物不可编辑；按明确fit且静音；头像时暂由avatar_stream代替，不改变主轨全片时钟。',
          'avatar_stream':'props.avatarSegments匹配当前半开区间时替换主窗；视频局部从0开始，静音contain，不裁头、不变形。只允许本期介绍店长或用户指定开场。',
          'title':'props.chapters中from不大于当前帧的最后一条title；标题/sub属于同一语义组，章节文字单次短移后稳定。',
          'support':'当前chapter.sub；非空才显示，与标题表达同一个当前重点。',
          'detail':'仅显式detail轨覆盖当前帧才出现；没有输入时整窗隐藏，不复制主轨填充。',
          'speaker':'数字人可见区间显示固定身份“海客AI社区服务站店长”；其余时间隐藏。',
          'caption':'全片实际配音cue，startMs/endMs毫秒；end后延65ms，字数≤21；白字深底56px，166ms移动5px后稳定。',
          'location':'本期props.location，默认“新塘未来汇 · 海客AI社区服务站”；不使用历史门店地址。',
          'master_audio':'唯一完整主母带，包含已批准配音与本期混音；所有源视频静音，不能重叠原声或数字人声音。',
        }[eid]
        style = {'parameter_source':'../../index.tsx','geometry_rule':d['rule'],'overflow':'父框hidden；文字溢出修正文案/语义分行，源画面不拉伸。'}
        if size:
            style.update(font='SimHei' if eid=='title' else 'Microsoft YaHei',font_size=size,max_lines=(8 if eid=='title' else 3 if eid=='support' else 1))
        elements.append({'id':eid,'type':kind,'role':eid,'parent_id':None,'z_index':z,
          'content':{'mode':'editable' if binding else 'none','binding':binding,'asset_id':None,'description':desc},
          'layout':{'coordinate_space':'canvas','anchor':'top_left','box':box,'fit':'contain' if kind in ['video','avatar'] else 'none','clip':'self','style':style},
          'timing':{'relative_to':'global','start':0,'end':6},
          'states':[{'id':'visible','visible':True,'description':desc}],
          'transitions':[],'constraints':[],'fixed':['layout'],'replaceable':['content','timing'] if binding else [],
          'evidence_ids':['implementation'],'acceptance':[{'check':'actual_frames','method':'实际看开头/每章/人物入中出/副窗显隐/最长字幕/结尾','pass_condition':'本期品牌地址准确；主画面可读、人物完整、无意外遮挡、文字可读；图不代替连续听看。'}]})
    slots=[]
    for element in elements:
        if not element['content']['binding']:continue
        eid=element['id']; limits={'master_clock':'实际配音不变速，durationFrames=ceil(seconds×30)','source':'index.tsx及本模板README'}
        if eid in ['main_backing','detail']:limits.update(clip_max_frames=120,fit=['contain','已实际裁切审阅的cover'],coverage='main完整覆盖；detail仅显式区间')
        if eid=='avatar_stream':limits.update(max_total_frames=300,placement='本期店长介绍或明确开头；全片半开区间，人物局部从0开始',source_audio='对应本期完整母带的同一区间')
        if eid=='caption':limits.update(max_characters=21,font_pixels=56,cue_clock='真实ASR及已批准文案核对')
        if eid=='title':limits.update(max_characters={22:8,23:8,24:6,25:4,26:11}[number],lines='按本模板README显式分行；不自动缩字')
        if eid=='support':limits.update(max_characters=12 if number==22 else 20 if number in [24,25] else 22)
        if eid=='location':limits.update(max_characters=32)
        slots.append({'id':element['content']['binding'],'element_id':eid,'property':'content','value_type':'string' if eid=='location' else 'array' if eid!='master_audio' else 'asset',
          'required':eid not in ['detail','avatar_stream','support'],'limits':limits,
          'missing':'主时钟、主素材、字幕、标题缺失停止冻结；可选字段缺失按当前样式隐藏，不代填其他来源。',
          'overflow':'回到本期脚本/选材按语义重排并重新冻结；不得拉伸、冻结、循环或擅自缩字号补齐。'})
    spec={'schema_version':1,'standard_version':'video-template-v1','template_id':f'store-opening-{number}','template_version':'v001','template_type':'custom','spec_kind':'implementation','stage':'specification',
      'authority':{'runbook':'runbook.md','implementation_paths':['../../index.tsx'],'parameter_source':'../../index.tsx'},
      'canvas':{'width':1440,'height':1800,'fps':30,'duration_seconds':6,'clock':'规格开发proof名义6秒；每期durationFrames=ceil(已批准完整音频秒数×30)，本契约1—60秒，不对语音变速。','coordinate_system':'top_left_pixels'},
      'narrative':{'purpose':f'{number} {d["name"]}，以现场聚客证明开业热闹，短店长身份后回到现场。','information_hierarchy':['真实门店开业人群与体验','当前章节标题及完整口播字幕','新塘未来汇门店地点'],'structure':['开业现场引子','店长身份短段','人群与AI体验','到店邀约']},
      'scenes':[{'id':'proof_hook','start':0,'end':4,'purpose':'开场布局与真实人群证明','element_ids':[e['id'] for e in elements],'variant':str(number)},{'id':'proof_identity','start':4,'end':6,'purpose':'人物/章节/副窗边界开发proof','element_ids':[e['id'] for e in elements],'variant':str(number)}],
      'assets':[],'elements':elements,'slots':slots,
      'evidence':[{'id':'implementation','source_kind':'design','source':'本期用户批准五条音频、指定开业人气与新撞色结构；设计来自本目录视觉packet。','locator':f'index.tsx OPENING_LAYOUTS[{number}]及相应JSX','method':'源码与规格逐项核对；实际proof与全片结果随后单独记录。','file':'../../index.tsx','sha256':SHASUM}],
      'unknowns':[],
      'validation':{key:{'status':'pending','evidence_ids':['implementation'],'note':'规则已确定；当前仅规格与实现交接，需本期实际渲染/检查证据；未宣称短样、全片、听审、真机或队列已通过。'} for key in ['structure','technical','visual','audio','platform','user_review','production']},
      'extensions':{'custom':{'contract':'store-opening-v1','rules':{'implementation':'index.tsx','geometry':d['rule'],'render':'1440×1800/30fps；本地高保真母版后20Mbps及以上最终流；原片不预压缩。'}},
        'avatar':{'face_crop':'固定主窗contain，保留原4:5人物完整头身，不校准假裁切。','synchronization':'仅本期口播中介绍店长短段；对应完整音轨同区间生成高质量人物；局部源从0，全片主时钟不停止。'},
        'material_edit':{'source_ranges':'props.shots逐镜含src/from/frames/offset/fit及任务来源SHA，原片的内嵌字样作为固化内容；本目录不携带用户素材。','cut_policy':'1x原速，不循环、不冻结、每镜≤4秒；main完整覆盖；detail可选显隐；源视频全部静音。'},
        'audio':{'contract':'speech-led-v1','rules':{'clock':'已批准配音为主时钟，真实cue JSON；音频不重TTS或改变节奏。','mix':'唯一audio母带；音乐/声音事件由本期制作混音回执明确，最终声音峰值另行实测。'}}},
      'operations':[{'id':'freeze','input':'本期完整WAV、真实ASR、已观察的原片镜头、可选新口型、props、SHA与用户授权。','action':'通过本仓store-opening-v1适配器prepare冻结，本目录只提供视觉实现。','output':'本期request、来源和runtime指纹。','completion':'主轨覆盖、原片SHA、音轨与字幕时钟、头像区间、文字长度和布局proof全部通过后才生产。','recovery':'沿原队列与来源SHA恢复；素材或实现变化新冻结，仅重做受影响本地合成。','entrypoint':'../../../../backlot/studio_store_opening.py'},
       {'id':'review','input':'当前版本有限proof和完整成片、quality/result、真实视频帧。','action':'按README与视频模板验收量表检查所有章节和状态，记录技术、视觉、听看、真机范围。','output':'REVIEW.md及可验证文件/哈希，符合ready条件才明确升级规格。','completion':'必需项有对应证据，不把抽帧当听审或本机当真机；失败项修复后检查受影响范围。','recovery':'源码改动重做本地冻结；保留云端成功音频与人物；恢复入口沿本期原队列。','entrypoint':'../../README.md'}]}
    write(variant/'video-template-spec.json',spec)
    runbook=f'''# 店长账号模板{number}｜{d['name']}

文档类型：video-template-runbook
标准版本：video-template-v1
模板规格：[规格](video-template-spec.json)
状态：待实际proof验收，implementation + specification；未声明ready或全片通过。
最近核验：2026-10-25源码与规格静态核对；实际渲染待制作任务。
适用范围：新塘未来汇海客AI社区服务站开业，4:5、1440×1800、30fps、配音主时钟1—60秒；数字人仅本期已授权短段。
权威入口：[index.tsx](../../index.tsx)的OPENING_LAYOUTS[{number}]及相应JSX；执行契约见[系列入口](../../README.md)。

## 触发与输入

用户呼叫“店长账号模板{number} / {d['name']}”。spec_kind=implementation、stage=specification。采用custom、avatar、material_edit及audio组合扩展：主轨原片、可选同音轨数字人、全片字幕与唯一母带。受控正式复用前必须以实际proof、技术/视觉文件及哈希满足ready；本次已授权开发和全片任务可先制作有限proof补足验证。

必需props：style={number}、durationFrames、audio、captions、shots(main全覆盖)、chapters、location。avatarSegments和detail仅按本期需要填写。geometry、字号、配色真值不在runbook另存，读取规格elements及index.tsx。

## 结构与约束

{d['rule']}

全片坐标左上px；序列[from,from+frames)，from/frames为全片30fps帧；源offset为秒、进入后从该offset读取1x。人物局部从0开始且静音；结束回当前主轨帧，不重播主片。标题/sub为一个当前语义组，字幕为第二阅读重点。地点来自本期props，默认新塘未来汇，无旧地址继承。

原片contain为默认；cover必须对最终视图实际审阅。主轨不能缺帧或循环；detail缺失整窗隐藏。字幕56px、一行≤21字；不缩字号补长句。人物牌只在人物区间出现；未提供人物时完全实拍。

## 操作和恢复

1. 输入本期完整音频、ASR、原片/人物与props → 适配器prepare核对SHA、覆盖、时钟和本模板约束 → 得冻结request → gate为输入完整、来源与运行版本一致 → 有缺项补原输入，不绕过。
2. 输入有限proof → 通过原生统一队列生成并检查开头/每章/人物进出/detail变化/最长字幕/结尾 → 留实际帧与质量报告 → gate为对应技术和视觉证据充分，满足ready才升级 → 未过仅修受影响布局和重冻本地，保留成功云媒体。
3. 输入ready版本和本期完整冻结request → 相同队列执行完整片 → 读回MP4、quality与result → gate为完整解码、1440×1800/30fps、实测视频流≥20Mbps、主时钟及音画覆盖 → 查原job恢复，不重复付费任务。
4. 输入最终片与实际帧 → 按量表检查全片技术、覆盖性视觉、连续听看和目标设备 → 记录REVIEW.md、证据文件及SHA → gate为每个适用维度有真实结论 → 真机/用户确认未验时保持pending，不把本地模拟当通过。

## 验证矩阵

| 维度 | 当前状态 | 补证据要求 |
|---|---|---|
| 规格/静态 | 待检查器结果绑定 | video-template-spec.json与index.tsx身份 |
| 技术 | pending | 实际proof/全片ffprobe、全解码和音频测量 |
| 视觉 | pending | 实际看所有章节、人物进出、副窗与最长字幕 |
| 连续听看 | pending | 实际连续播放，检查原声/字幕同步、口型和叙事 |
| 平台/真机 | pending | 声明目标平台与设备的真实播放 |
| 用户确认 | pending | 本期完整成片的明确反馈 |
| 生产接入 | pending | 本期原生队列ID、request与完整产物SHA读回 |

## 已知风险与维护

宽窗放竖片容易变小：先换正确画幅的原片或使用明确审批过的cover，不加模糊边当高清。最长标题溢出时按本模板语义行数重写，字幕按真实cue拆句。字体缺失、素材SHA变化和额外人物段均阻断相应制作。

运行产物和私人路径留在本期任务；本目录不携带Key、用户原片或人物授权文件。最近修订为2026-10-25 v001；实现、主时钟、素材槽、版面或目标平台变化需重验受影响维度。
'''
    (variant/'runbook.md').write_text(runbook,encoding='utf-8')

tokens={'color':{},'type':{'title':{'$type':'typography','$value':{'fontFamily':['SimHei'],'fontSize':{'value':100,'unit':'px'},'fontWeight':900,'lineHeight':1.12}},'caption':{'$type':'typography','$value':{'fontFamily':['Microsoft YaHei'],'fontSize':{'value':56,'unit':'px'},'fontWeight':900,'lineHeight':1.2}}},'motion':{'duration':{'chapter':{'$type':'duration','$value':{'value':333,'unit':'ms'}},'caption':{'$type':'duration','$value':{'value':166,'unit':'ms'}}}}}
for number,d in LAYOUTS.items():
    tokens['color'][str(number)]={role:{'$type':'color','$value':{'colorSpace':'srgb','components':[int(value[i:i+2],16)/255 for i in (1,3,5)],'hex':value}} for role,value in zip(['ground','ink','onInk'],d['palette'])}
write(HERE/'tokens.json',tokens)
write(HERE/'layout-manifest.json',{'version':'v001','authority':'index.tsx','canvas':[1440,1800,30],'layouts':LAYOUTS,'caption':[54,1542,1332,132],'location':[54,1700,1332,62],'source_sha256':SHASUM})
print(json.dumps({'variants':list(LAYOUTS),'source_sha256':SHASUM},ensure_ascii=False))
