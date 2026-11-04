import React from 'react';
import {AbsoluteFill,Img,OffthreadVideo,staticFile,useVideoConfig} from 'remotion';
import {definitions} from './definitions.generated';
import names from './catalogue.json';
import {SnapCnUIProvider} from './upstream/registry/snap-cn-ui/core';

const a=(name:string)=>staticFile('assets/'+name);
const photos=Array.from({length:8},(_,i)=>a(`photo-${i+1}.jpg`));
const videos=['robot','store','children','dog','robot-duo'].map(n=>a(`video-${n}.mp4`));
const mark=a('haike-mark.svg');
const followers=Array.from({length:30},(_,i)=>({name:['体验家庭','现场老师','活动伙伴','社区邻居'][i%4]+(i+1),avatar:photos[i%photos.length]}));
const overrides:Record<string,Record<string,unknown>>={
  'answer-highlight':{question:'怎样让长辈轻松体验AI？',answer:'先看一看 机器人 再跟着老师 亲手 试一试 每一步 都有演示 遇到问题 随时提问',statement:'亲手 试一试',word:'试一试'},
  'agent-steps':{query:'用本地素材制作一条社区体验视频',steps:'读取素材 > 已读取本地素材; 整理文案 > 已整理口播文案; 安排镜头 > 已安排素材与人物; 检查效果 > 演示已准备好',result:'演示制作完成'},
  'announce-title':{eyebrow:'这个周末',title:'亲手体验AI',tagline:'看得见，摸得到，学得会。'},
  'answer-stream':{question:'长辈也可以学习AI吗？',answer:'当然可以。\n从现场演示开始，跟着老师一步一步试。\n手机操作、机器人互动，都能亲手体验。',headline:'从知道AI，到亲手体验',model:'现场演示'},
  'text-reveal':{text:'亲手 体验 AI 生活'},
  'text-highlight':{before:'一起 ',highlight:'看看',after:' AI',replaceWith:'体验',logoSrc:mark},
  'text-rewrite':{headline:'带上家人',append:'来体验AI'},
  'text-select':{headline:'让科技走进日常生活'},
  'text-swap':{fromText:'听别人讲AI',toText:'自己亲手体验'},
  'text-swell':{text:'看懂了，再试试'},
  'text-build':{text:'看一看 试一试 学一学'},
  'word-flip':{prefix:'一起体验',suffix:'新生活',words:['机器人','智能手机','AI工具']},
  'word-captions':{words:'带上 家人 一起 来 现场 亲手 体验 AI',preset:'pop',groupSize:3,maxWords:3,framesPerWord:12,fontSize:64,accentColor:'#ffe08a'},
  'karaoke-captions':{text:'机器人 就在 孩子 面前 一起 亲手 体验',emphasize:'体验',preset:'highlight',fontSize:58,baseColor:'#dce4eb',fillColor:'#ffffff',accentColor:'#ffe08a'},
  'logo-drift':{headline:'把科技带到生活里'},
  'logo-assemble':{logoSrc:mark,brandName:'海客AI',middleText:'亲手体验\n看见变化',images:photos},
  'logo-flicker':{logoSrc:mark,brandName:'海客AI',images:photos},
  'block-wordmark':{text:'海客AI'},
  'phone-frame':{screenSrc:videos[0],variant:'showcase',entrance:'float'},
  'laptop-frame':{screenSrc:videos[1],notchLabel:'本地实拍演示'},
  'terminal-simulator':{intro:'本地素材 一步一步 做成视频',command:{text:'读取 社区体验素材',managers:['本地制作']},lines:[{text:'找到机器人实拍',type:'log'},{text:'找到现场体验画面',type:'log'},{text:'已准备动效预览',type:'success'}]},
  'screen-recording':{src:videos[1]},
  'count-grid':{from:'5',to:'50',noun:'段素材',cards:photos},
  'roster-grant':{label:'一起参与',rows:Array.from({length:3},(_,r)=>Array.from({length:5},(_,i)=>({name:['现场老师','体验家庭','社区伙伴','志愿讲解','活动助手'][(i+r)%5],role:'一起认识AI'})))},
  'wordmark-cut':{word:'海客AI'},
  'follower-rush':{followers},
  'prompt-send':{text:'用这些现场素材，做一条清楚好懂的视频',placeholder:'说说你想制作的内容',chips:'现场体验, 机器人互动, 数字人口播, 大字字幕'},
  'prompt-zoom':{greeting:'想试试AI吗？',text:'帮我安排一次家庭体验',placeholder:'输入你的问题',model:'本地示意',effort:'清楚易懂'},
  'punch-lines':{script:'先看一看 / 再试一试 | 和家人一起 | 亲手体验AI',sizes:'1,1,1.35'},
  'orbit-gallery':{title:'看得见的AI体验',subtitle:'本地实拍 · 现场记录',buttonLabel:'一起体验',images:photos,footerLeft:'本地素材',footerCenter:'组件效果演示',footerRight:'海客AI'},
  'hero-launch':{image1:videos[0],image2:videos[2],heading:'和家人一起 亲手体验AI'},
  'moodboard-reveal':{leadIn:'带上家人',emphasis:'体验',tailIn:'AI生活',heroImage:photos[0],images:photos},
  'reel-collage':{topLine:'看得见',bottomLine:'真实体验',swapTop:'和家人一起',swapBottom:'走近AI',slides:[...photos],collage:videos.concat(photos[0])},
  'reel-wall':{videos},
  'phone-stack':{videos},
  'portal-intro':{lead:'从现场开始',trail:'亲手试试看',title:'一起走近',brand:'海客AI',image:photos[0],chipImage:photos[1],logoSrc:mark},
  'search-typing':{text:'附近哪里可以亲手体验机器人？',seed:'haike-local-demo'},
  'status-cycle':{prefix:'我们正在',statuses:'看现场,学操作,亲手试,一起体验',chips:'机器人,智能手机,家庭体验,社区活动,AI工具'},
  'type-morph':{lead:'从 ',emphasis:'知道AI',morphTo:'亲手体验',finally_:'体验'},
  'orb-swarm':{script:'带上家人 | 看一看 | 机器人 | 试一试 | 学起来 | 体验AI'},
  'word-gather':{text:'让 科技 走进 日常 生活'},
  'word-wheel':{headline:'一起体验',words:'机器人,智能手机,AI工具,亲子活动,社区生活'},
  'check-cycle':{headline:'从这里开始',words:'看看,提问,动手,学习,体验'},
  'font-shuffle':{lead:'Introducing',subject:'AI LIFE'},
  'button-press':{label:'开始体验',pending:'正在准备',done:'准备好了'},
  'click-type':{placeholder:'说说你想体验什么',prompt:'我想带家人体验机器人',hint:'本地演示'},
  'capture-reveal':{headline:'真实现场 | 亲手体验',capturing:'正在截取本地画面',copied:'画面准备好了',src:photos[0]},
  'channel-thread':{messages:`${photos[7]} > 体验老师 上午9:41 > 今天一起体验机器人吧 | 每一步都会讲清楚 | ${photos[6]} > 社区伙伴 上午9:42 > 我带家人过来 | 一起亲手试试看`},
  'logo-collapse':{images:photos.join('|'),mark,wordmark:'海客AI',background:''},
  'card-rail':{heading:'看看现场都有什么',cards:photos.map((p,i)=>`${p} > ${['机器人互动','现场体验','亲子活动','认识机器狗'][i%4]} > 本地实拍 > 海客AI`).join(' | '),backdrop:''},
};
export const catalogue=definitions.map(d=>{
  const label=(names as Record<string,string[]>)[d.id];
  const props={...Object.fromEntries(Object.entries(d.config.controls).map(([k,v]:any)=>[k,v.default])),fontFamily:'Haike Local',...(overrides[d.id]||{})};
  // Default theme controls must not replace authored dark-stage settings.
  return {...d,name:label[0],category:label[1],description:label[2],props,localMedia:['设备素材','图片场景','字幕'].includes(label[1])||['logo-assemble','logo-flicker','logo-collapse','follower-rush','channel-thread','pulsing-border','cursor-track','hero-launch','count-grid','portal-intro'].includes(d.id)};
});

export function Demo({id}:{id:string}){
  const d=catalogue.find(x=>x.id===id);const {fps}=useVideoConfig();
  if(!d)throw new Error('未知组件：'+id);
  const Component=d.component as React.ComponentType<any>;
  const bg=(d.config as any).previewBackdrop;
  const background=bg?.value||'#faf9f6';
  return <AbsoluteFill style={{background,fontFamily:'Haike Local',overflow:'hidden'}}>
    <style>{`@font-face{font-family:'Haike Local';src:url('${a('font.ttf')}')}*,*:before,*:after{box-sizing:border-box}`}</style>
    <SnapCnUIProvider>
      {['cursor-track','pulsing-border','word-captions','karaoke-captions'].includes(id)&&<><OffthreadVideo src={videos[id==='cursor-track'?1:0]} muted premountFor={fps} style={{width:'100%',height:'100%',objectFit:'cover'}}/>{id==='pulsing-border'&&<div style={{position:'absolute',inset:0,background:'#0004'}}/>}</>}
      <Component {...d.props}/>
    </SnapCnUIProvider>
  </AbsoluteFill>;
}
