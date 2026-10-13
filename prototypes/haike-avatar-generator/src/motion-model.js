export const GROUP_NAMES = {
  'claim-into-container':'主张、方法与回应','claim-and-response':'主张与人物回应','evidence-focus':'证据与三项观察','evidence-and-focus':'证据与焦点',
  'decompose-and-consolidate':'拆解与归纳','three-items-consolidate':'三项归纳','apparent-tension-to-value':'对立、价值与行动',
  'cards-to-network':'资料聚合成网络','calendar-to-delivery':'计划到交付','recap-to-evidence-to-incident':'回顾、证据与事件','transfer-and-consequence':'转移与后果',
  'claim-to-evolving-timeline':'主张与演进时间线','simplify-and-interrupt':'简化与打断','evidence-to-handbook':'证据到手册','animated-contents':'动态目录',
  'closing-with-invitation':'总结与邀请','basic-keyword':'关键词强调','basic-points':'三个要点','basic-summary':'总结卡片',
  'independent-artifact-review':'单项成果审阅','fusion-success':'输入融合','three-step-chat':'三个步骤','manual-agents-delivery':'协作交付',
  'delivery-reading-complete':'交付与阅读','keyword-to-conclusion':'关键词到结论','prepared-to-reuse':'准备与接力','feedback-to-update':'反馈与升级',
  'prepared-to-reuse-natural-end':'接力与自然收束','feedback-to-update-natural-end':'升级与自然收束','answer-to-question':'回答与提问',
  'steps-to-uniformity':'步骤与统一','echo-focus':'回声标题','cost-to-verdict':'成本与结论',
  s01:'主张开场',s02:'多屏作品比较',s03:'聚焦中央作品',s04:'多组比较',s05:'软件演示',s06:'能力与来源',s07:'流程变化',s08:'成果与回应',s09:'总结收束',
};
export const WORDS = {claim:'主张',method:'方法',distribution:'分发',proof:'证明',response:'回应',overview:'概览',detail:'细节',result:'结果',observations:'观察',conclusion:'结论',concept:'概念',decomposition:'拆解',consolidation:'归纳',handoff:'交接',title:'标题',keyword:'关键词',points:'要点',summary:'总结',entry:'开场',context:'背景',heading:'标题',line1:'第一行',line2:'第二行',line3:'第三行',label:'标签',value:'数值',parts:'部分',before:'之前',after:'之后',receivers:'接收者',container:'容器',chain:'链路',resolve:'收束',setup:'铺垫',impact:'强调',name:'名称',type:'类型',contents:'内容',status:'状态',steps:'步骤',cards:'卡片',prompt:'邀请',media:'媒体素材',items:'条目',text:'文字',chapter:'章节',speaker:'人物',badge:'角标',entity:'对象'};
export const groupName = group => group?.label || GROUP_NAMES[group?.id?.split(':').slice(1).join(':')] || group?.id?.split(':').slice(1).join(' · ') || '选择镜头组';
export const fieldName = (f, i) => f.label || (f.inputPath ? f.inputPath.split('.').map(p=>roleLabel(p)).join(' · ') : f.type==='talk'?'口播人物':`画面文字 ${i+1}`);
Object.assign(WORDS, {reading:'阅读',acceleration:'加速',account:'账号',accumulation:'累积',action:'行动',aggregation:'聚合',answer:'回答',burden:'负担',bye:'结束',calendar:'日历',camera:'人物',language:'表达',capabilities:'能力',categories:'分类',category:'分类',ceiling:'上限',change:'变化',choose:'选择',address:'地址',file:'文件',or:'或',closing:'收尾',code:'代码',collect:'收集',comments:'反馈',comparison:'比较',competition:'竞争',competitors:'对手',complete:'完成',seven:'七项',six:'六项',three:'三项',compression:'压缩',confirmation:'确认',consequence:'后果',continue:'继续',cost:'成本',coverage:'覆盖',cross:'交接',define:'定义',manual:'手册',deliver:'交付',deliveries:'交付项',delivery:'交付',draft:'草稿',emotional:'情绪',reversal:'反转',establish:'建立',evidence:'证据',execute:'执行',checks:'检查',explanation:'解释',features:'特点',feedback:'反馈',first:'第一项',focus:'焦点',folder:'文件夹',friction:'阻碍',goal:'目标',groups:'分组',group:'分组',growth:'增长',handbook:'手册',hook:'开场',identity:'身份',illustration:'示意',incident:'事件',inputs:'输入',input:'输入',interrupt:'打断',introduce:'介绍',executors:'执行者',invitation:'邀请',iteration:'迭代',merge:'合并',metrics:'指标',narrative:'叙事',negative:'负面',network:'网络',observe:'观察',output:'输出',payoff:'结果',permanence:'保留',plan:'计划',portfolio:'作品',positive:'正面',precision:'精准',preparation:'准备',previous:'此前',production:'制作',progression:'演进',project:'项目',quality:'质量',question:'问题',recap:'回顾',receive:'接收',rejection:'拒绝',reuse:'复用',review:'审阅',rules:'规则',rule:'规则',second:'第二项',shrink:'收缩',signature:'签名',signoff:'收束',software:'软件',strike:'划去',submit:'提交',success:'成功',tension:'对立',tiles:'卡片',timeline:'时间线',tool:'工具',transfer:'转移',transition:'过渡',two:'双项',introduction:'引入',unbox:'开箱',uniformity:'统一',update:'升级',verdict:'结论',versions:'版本',version:'版本',wall:'作品墙',warning:'提示',withdraw:'退出',work:'作品',item:'条目',line:'行',card:'卡片',step:'步骤',left:'左侧',right:'右侧',number:'数字',feature:'要点',quote:'结论',arrival:'到达',checked:'检查完成',all:'全部',call:'邀请',to:'转到',commit:'确认',board:'看板',consolidate:'归纳',decompose:'拆解',executor:'执行者',execution:'执行',completion:'完成',creator:'创作者',giver:'交付者',grid:'网格',opening:'开场',procedure:'流程',process:'处理',reasoning:'推理',receipt:'回执',out:'划去',close:'收尾',note:'说明',hero:'主标题',from:'来自',show:'展示',progress:'进度',processing:'处理',start:'开始',slam:'强调',word:'文字',a:'甲',b:'乙',statement:'陈述',time:'时间',shift:'切换',expand:'展开',video:'视频',artifacts:'成果',artifact:'成果',context:'背景',role:'角色',prefix:'前缀',agents:'协作角色',agent:'协作角色',annotation:'标注',attribution:'来源',audience:'受众',augmentation:'补充',avatar:'人物',brand:'品牌',sample:'样例',capacity:'容量',count:'数量',chat:'对话',contrast:'对比',connector:'连接',creation:'创作',currency:'币种',day:'天',days:'天数',unit:'单位',deliverables:'交付物',description:'说明',destination:'目标',direction:'方向',disclaimer:'说明',disclosure:'标记',done:'完成',duration:'时长',end:'结束',engine:'引擎',era:'阶段',evaluation:'评估',factor:'因素',figure:'人物',meta:'信息',index:'编号',followers:'关注人数',format:'格式',grain:'颗粒',texture:'纹理',high:'高位',low:'低位',hours:'小时',hour:'小时',icon:'图标',income:'收入',initial:'初始',instruction:'操作说明',interruptions:'打断',intro:'引入',keywords:'关键词',kicker:'提示',labels:'标签',lead:'引导',lens:'镜头',logo:'标识',mark:'标记',message:'消息',meter:'进度',minutes:'分钟',minute:'分钟',observation:'观察',object:'对象',opponent:'对方',opposition:'对立',outputs:'输出',pain:'问题',part:'部分',participants:'参与者',path:'素材',playback:'播放',presenter:'人物',products:'产品',product:'产品',push:'推进',reaction:'回应',receiver:'接收者',record:'记录',recording:'录屏',reference:'参考',reflection:'反思',rhythm:'节奏',scope:'范围',self:'自己',simplify:'简化',source:'来源',stack:'堆叠',stages:'阶段',stage:'阶段',subject:'主体',subtitle:'字幕',tagline:'标语',template:'模板',tier:'档位',timeframe:'时间范围',token:'用量',tokens:'用量',topic:'主题',track:'音轨',ultra:'重点',url:'地址',wide:'宽幅',workflow:'工作流',working:'处理中',alternative:'备选',alert:'提示',threshold:'阈值'});
export const roleLabel = value => WORDS[value] || value.replace(/([a-z])([A-Z])/g,'$1-$2').split(/[_-]/).map(p=>WORDS[p]||(/^\d+$/.test(p)?`第${Number(p)+1}项`:p)).join(' · ');
export function issueLabel(value) {
  const text=typeof value==='string'?value:JSON.stringify(value);
  const anchor=text.match(/^anchor ([\w-]+)(?: \(([^)]+)\))?$/);
  if(anchor)return `补充“${roleLabel(anchor[2]||anchor[1])}”动作落点（从本段开始计时）。`;
  const slot=text.match(/^slot ([\w-]+)$/);
  if(slot){const name=WORDS[slot[1]]||slot[1].replace(/^body-(\d+)$/,(_,n)=>`第${Number(n)+1}项文字`);return `填写或上传“${name}”对应的画面内容。`;}
  return `该配置尚未满足模板要求：${text}`;
}
export function motionRenderRevision(job) {
  const match=job?.parent_job_id?.match(/^studio-([1-9]\d*)$/);
  return match?Number(match[1]):job?.frozen_request?.draft?.revision;
}
export function parseSrt(text) {
  const rows = text.replace(/^\uFEFF/,'').replace(/\r/g,'').trim().split(/\n\s*\n/), out=[];
  const time = t => {const m=t.match(/^(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})$/);if(!m||Number(m[2])>59||Number(m[3])>59)throw new Error('字幕时间格式无效');return Number(m[1])*3600+Number(m[2])*60+Number(m[3])+Number(m[4])/1000;};
  for(const block of rows){const lines=block.split('\n'),n=lines.findIndex(x=>x.includes('-->'));if(n<0)throw new Error('请上传标准SRT字幕，包含开始与结束时间');const [a,b]=lines[n].split(/\s*-->\s*/);const start=time(a),end=time(b),body=lines.slice(n+1).join('\n');if(!body||start>=end)throw new Error('字幕原文或时间无效');out.push({start,end,text:body,en:''});}
  if(!out.length)throw new Error('字幕文件为空');return out;
}
export function validateMotion(input, text) {
  if(!input.source) return '先上传口播视频，或从已有作品选择口播母版。';
  if(!text.trim()) return '请填写与口播对应的完整文案。';
  if(!input.segments.length) return '请增加至少一个分镜。';
  if(input.segments.map(x=>x.text).join('')!==text) return '分镜原文须按顺序完整覆盖文案，不能丢句或重复。';
  if(!input.music?.mode) return '请选择本期配乐，或明确选择不使用背景音乐。';
  if(input.music.mode==='track'&&!input.music.asset) return '请上传本期背景音乐。';
  return '';
}
