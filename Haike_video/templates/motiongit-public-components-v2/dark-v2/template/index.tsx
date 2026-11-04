import React,{useEffect,useState} from 'react';
import {AbsoluteFill,Audio,Composition,continueRender,delayRender,Img,OffthreadVideo,registerRoot,Sequence,staticFile,useCurrentFrame,useVideoConfig} from 'remotion';
import type {Context,Props,Scene} from './types';
import {body,palette,phase,rect,text,mix,SceneClock,cue,storyPaper} from './shared';
import {presenterPose} from './presenter-clock';
import {GroupsA} from './GroupsA';
import {GroupsB} from './GroupsB';

const names=['开场与作品墙','九屏比较','接续聚焦','分类与镜头','身份与竞争','时间推进','流程与接力','对比与行动','打字与签名','独立成果审阅'];
const cuts=[0,8.8,25.9,40.4,52.7,69.4,78.1,89.7,102.92,108.4,122.4];
export const previewDefaults:Props={width:1920,height:1080,fps:60,durationFrames:7344,variant:'reference',brand:'MotionGit',header:'模板03 · 深色立体多屏展陈',footer:'完整动作开发预览',media:[],captions:[],scenes:names.map((title,i)=>({id:'group-'+(i+1),group:(i===9?'review':'s0'+(i+1)) as Scene['group'],from:Math.round(cuts[i]*60),frames:Math.round((cuts[i+1]-cuts[i])*60),title,mediaIds:[],content:{},sourceStart:i===9?110:cuts[i],sourceDuration:cuts[i+1]-cuts[i]}))};

const Fonts:React.FC<{p:Props;children:React.ReactNode}>=({p,children})=>{
 const [handle]=useState(()=>delayRender('Loading bound Chinese fonts'));
 useEffect(()=>{if(!p.fontAssets){continueRender(handle);return}Promise.all(Object.entries(p.fontAssets).map(async([name,src])=>{const f=new FontFace(name==='body'?'DarkFullBody':'DarkFullDisplay',`url(${staticFile(src)})`);await f.load();(document.fonts as FontFaceSet&{add:(face:FontFace)=>void}).add(f)})).then(()=>continueRender(handle)).catch(e=>{throw e})},[handle,p.fontAssets]);
 return <>{children}</>;
};

const SceneBody:React.FC<{p:Props;s:Scene}>=({p,s})=>{
 const frame=useCurrentFrame(),{fps}=useVideoConfig();
 const c:Context={p,s,frame,seconds:frame/fps,portrait:p.height>p.width,t:palette(p)};
 return <SceneClock.Provider value={c}>{['s01','s02','s03','s04'].includes(s.group)?<GroupsA c={c}/>:<GroupsB c={c}/>}</SceneClock.Provider>;
};

const ReferencePresenter:React.FC<{p:Props}>=({p})=>{
 const f=useCurrentFrame(),seconds=f/p.fps;if(!p.referencePortrait||p.variant==='native-story')return null;
 const out=phase(seconds,3.9,.75),identity=phase(seconds,52.7,.65)*(1-phase(seconds,57.7,.65)),ending=phase(seconds,98.6,.65)*(1-phase(seconds,102.92,.35));
 const large=Math.max(1-out,identity,ending),small={x:1670,y:105,w:190,h:190},big={x:1370,y:130,w:420,h:754};
 return <div style={{...rect(mix(small.x,big.x,large),mix(small.y,big.y,large),mix(small.w,big.w,large),mix(small.h,big.h,large)),borderRadius:mix(999,24,large),overflow:'hidden',boxShadow:'0 12px 35px #0005',border:large<.1?'3px solid #EEE':undefined}}><Img src={staticFile(p.referencePortrait)} style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:large>.9?'50% 50%':'50% 20%'}}/></div>;
};

const Presenter:React.FC<{p:Props}>=({p})=>{
 const f=useCurrentFrame(),{fps}=useVideoConfig(),clip=p.presenter;
 if(!clip)return null;
 const pose=presenterPose(clip,f,fps);
 const story=p.variant==='native-story',large=story?{x:892,y:445,w:460,h:576}:{x:820,y:480,w:530,h:830},small=story?{x:1120,y:168,w:232,h:232}:{x:1100,y:240,w:245,h:305};
 const b={x:mix(small.x,large.x,pose.large),y:mix(small.y,large.y,pose.large),w:mix(small.w,large.w,pose.large),h:mix(small.h,large.h,pose.large)};
 return <Sequence from={clip.from} durationInFrames={clip.frames} premountFor={fps}><div data-layer="presenter" data-mode={pose.mode} data-source-seconds={pose.sourceSeconds} style={{...rect(b.x,b.y,b.w,b.h),opacity:pose.visible?1:0,overflow:'hidden',borderRadius:story?mix(999,24,pose.large):16,border:story?'3px solid #FFFFFFB3':`3px solid ${palette(p).line}`,boxShadow:'0 20px 55px #00151040',background:story?'#0B101B':undefined}}><OffthreadVideo src={staticFile(clip.src)} trimBefore={Math.round(clip.offset*fps)} muted style={{width:'100%',height:'100%',objectFit:story?'cover':'contain',objectPosition:story?'50% 28%':undefined,transform:story?`scale(${mix(1.58,1,pose.large)})`:undefined,transformOrigin:'50% 31%'}}/>{story&&pose.large>.985&&<div style={{position:'absolute',top:18,left:18,padding:'7px 13px',borderRadius:99,background:'#05060DBD',...body(19,'#FFF')}}>{p.brand}</div>}</div></Sequence>;
};

const StoryChrome:React.FC<{p:Props;c:Context|null;caption?:string}>=({p,c,caption})=>{
 const light=!!c&&storyPaper(c),ink=light?'#12171D':'#F5F4FF',muted=light?'#6C747C':'#C1C0D1';
 return <><div style={{...rect(88,64,1264,50),...body(28,ink),display:'flex',justifyContent:'space-between',alignItems:'center',borderBottom:`1px solid ${light?'#13232918':'#FFFFFF18'}`,paddingBottom:24}}><span>{p.brand}</span><span style={{fontSize:24,color:muted}}>{p.header}</span></div><div data-element="caption-safe-band" style={{...rect(88,1535,1264,128),...text(66,ink,700),fontFamily:'DarkFullBody',display:'flex',alignItems:'center',justifyContent:'center',textAlign:'center',lineHeight:1.25,textShadow:light?'0 1px 2px #FFFFFFAA':'0 2px 7px #071121',borderTop:`1px solid ${light?'#13232918':'#FFFFFF18'}`}}>{caption||''}</div><div style={{...rect(88,1710,1264,38),...body(25,muted)}}>{p.footer}</div></>;
};

export const DarkFull:React.FC<Props>=p=>{
 const f=useCurrentFrame(),t=palette(p),social=p.height>p.width,cap=p.captions.find(x=>f/p.fps*1000>=x.startMs&&f/p.fps*1000<x.endMs),scene=p.scenes.find(s=>f>=s.from&&f<s.from+s.frames);
 const local=scene?(f-scene.from)/p.fps:0,light=p.variant==='reference'&&((scene?.group==='s04'&&!(local>=5.2&&local<8.1))||scene?.group==='s07'||(scene?.group==='s08'&&local>10.4));
 const referenceInk=light?'#424A4B':'#B1B4BE';
 const context=scene?{p,s:scene,frame:f-scene.from,seconds:local,portrait:social,t}:null;
 const at=(id:string,source:number)=>context?cue(context,id,source):0;
 const paper=scene?.group==='s07'||(scene?.group==='s04'&&!(local>=at('wall_expand',45.55)&&local<at('cross_out',49)-.25))||(scene?.group==='s08'&&local>=at('comments',100.1)+.35);
 const darkB=!!scene&&['s05','s08','s09','review'].includes(scene.group)&&!paper;
 const socialInk=paper?(p.variant==='hedgerow'?'#173D30':'#10213C'):scene?.group==='s06'?'#FFFFFF':darkB&&p.variant==='cobalt'?'#F7F9FB':t.ink;
 const socialMuted=paper?'#68735F':darkB&&p.variant==='cobalt'?'#BAC9DF':t.muted;
 return <Fonts p={p}><AbsoluteFill style={{fontFamily:'DarkFullBody,Microsoft YaHei,sans-serif',background:t.bg,overflow:'hidden'}}>
 {p.scenes.map(s=><Sequence key={s.id} from={s.from} durationInFrames={s.frames} premountFor={p.fps}><SceneBody p={p} s={s}/></Sequence>)}
 <Presenter p={p}/>
 <ReferencePresenter p={p}/>
 {p.variant==='native-story'?<StoryChrome p={p} c={context} caption={cap?.text}/>:social?<><div style={{...rect(88,64,1264,46),...body(30,socialInk),display:'flex',justifyContent:'space-between'}}><span>{p.brand}</span><span style={{color:socialMuted,fontSize:23}}>{p.header}</span></div><div style={{...rect(88,1450,1264,165),...text(70,socialInk,p.variant==='hedgerow'?500:700),fontFamily:'DarkFullBody',display:'flex',alignItems:'center',justifyContent:'center',textAlign:'center',borderTop:`1px solid ${paper?'#13232925':t.line}`}}>{cap?.text||''}</div><div style={{...rect(88,1690,1264,44),...body(25,socialMuted)}}>{p.footer}</div></>:<><div style={{...rect(80,58,1300,35),...body(19,referenceInk)}}>03 · {scene?.title||p.header}</div><div style={{...rect(1600,58,240,35),...body(19,referenceInk),textAlign:'right',fontFamily:'monospace'}}>{String(Math.floor(f/p.fps/60)).padStart(2,'0')}:{String(Math.floor(f/p.fps)%60).padStart(2,'0')}</div><div style={{...rect(180,980,1560,62),...body(35,'#9BDAFF'),textAlign:'center',textShadow:'0 1px 2px #071217,-1px 0 2px #071217'}}>{cap?.text||''}</div></>}
 {p.audio&&<Audio src={staticFile(p.audio)}/>}
 </AbsoluteFill></Fonts>;
};
const Root:React.FC=()=> <Composition id="DarkFull" component={DarkFull} width={1920} height={1080} fps={60} durationInFrames={7344} defaultProps={previewDefaults} calculateMetadata={({props})=>({width:props.width,height:props.height,fps:props.fps,durationInFrames:props.durationFrames})}/>;
registerRoot(Root);
