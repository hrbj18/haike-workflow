import React from 'react';
import {AbsoluteFill, Audio, Composition, Img, OffthreadVideo, registerRoot, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

type Cue = {text: string; startMs: number; endMs: number};
type Props = {template: string; duration: number; title: string; text: string; titleSize: number; accent: string; captions: Cue[]};
const defaults: Props = {template:'avatar-template3-card-3x4-v001',duration:7,title:'海客科技',text:'让创作更简单。一个接口，连接你的创作工作流。',titleSize:60,accent:'#316dd6',captions:[]};
const Avatar: React.FC<{style: React.CSSProperties}> = ({style}) => <div style={{position:'absolute',overflow:'hidden',borderRadius:'50%',border:'5px solid #dde1de',...style}}><OffthreadVideo muted src={staticFile('avatar.mp4')} style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:'50% 35%'}}/></div>;
const Brand = () => <Img src={staticFile('haike-logo.png')} style={{width:235,height:68,objectFit:'contain'}}/>;
const Video: React.FC<Props> = p => {
  const {fps,height}=useVideoConfig(); const frame=useCurrentFrame(), ms=frame/fps*1000;
  const cue=p.captions.find(c=>ms>=c.startMs&&ms<c.endMs);
  const points=p.text.split(/[。！？\n]/).map(s=>s.trim()).filter(Boolean);
  const count=Math.max(1,points.length), current=Math.min(count-1,Math.floor(frame/(p.duration*fps)*count));
  const card=p.template.startsWith('avatar-template3'), full=p.template==='avatar-full-width-v2';
  const currentText=points[current]||p.text;
  const pageText=currentText.length>90?currentText.slice(0,90)+'…':currentText;
  return <AbsoluteFill style={{fontFamily:'"PingFang SC","Microsoft YaHei",sans-serif',color:card?'#242c3b':'#fff',background:card?'linear-gradient(135deg,#cde1fb 0%,#f9edd0 48%,#bea6e0 77%,#f9ded6 100%)':'#081629'}}>
    {card?<div style={{position:'absolute',inset:'72px 64px 70px',borderRadius:42,background:'#fff',padding:44,boxShadow:'0 10px 40px #55608022'}}>
      <div style={{display:'flex',alignItems:'center',gap:20}}><Brand/><span style={{fontSize:24,color:'#7a8390'}}>创作工作流</span></div>
      <section style={{position:'absolute',left:48,right:48,top:130,height:640,borderRadius:32,background:'#f6f7fa',padding:32,boxSizing:'border-box'}}>
        <div style={{color:p.accent,fontSize:24,marginBottom:24}}>0{current+1} / {count} · 内容讲解</div>
        <h1 style={{margin:'0 0 32px',fontSize:p.titleSize,lineHeight:1.3,overflowWrap:'anywhere'}}>{p.title}</h1>
        <div style={{fontSize:38,lineHeight:1.75,color:'#596273',overflowWrap:'anywhere'}}>{pageText}</div>
      </section>
      <Avatar style={{left:44,top:812,width:320,height:320}}/>
      <div style={{position:'absolute',left:410,top:850,right:48,fontSize:30,lineHeight:1.7}}><div style={{color:'#8a909b',fontSize:22}}>海客创作 · {current+1} / {count}</div><strong style={{color:p.accent,fontSize:38}}>你的内容，清晰表达</strong><p style={{margin:'16px 0',fontSize:26}}>数字人口播<br/>按模板组织内容</p></div>
    </div>:<>
      <div style={{position:'absolute',left:125,top:120}}><Brand/></div>
      <div style={{position:'absolute',left:full?80:125,top:full?320:420,width:full?650:540}}><h1 style={{fontSize:p.titleSize,lineHeight:1.35,margin:0,overflowWrap:'anywhere'}}>{p.title}</h1></div>
      <Avatar style={full?{left:752,top:190,width:220,height:220}:{left:691,top:307,width:236,height:236}}/>
      <div style={{position:'absolute',left:full?0:110,top:full?600:625,width:full?1080:690,height:full?680:620,borderRadius:full?0:26,background:'#fff',color:'#242c3b',padding:full?90:48,boxSizing:'border-box',display:'flex',flexDirection:'column',justifyContent:'center'}}><div style={{fontSize:26,color:p.accent,marginBottom:25}}>内容 {current+1} / {count}</div><div style={{fontSize:full?50:44,lineHeight:1.65,overflowWrap:'anywhere'}}>{pageText}</div></div>
    </>}
    {cue&&<div style={{position:'absolute',left:card?100:120,width:card?880:790,top:card?1290:1342,minHeight:66,textAlign:'center',fontSize:42,fontWeight:700,lineHeight:1.5,color:card?p.accent:'#fff',textShadow:card?'none':'0 2px 4px #000, 2px 0 #000,-2px 0 #000',overflowWrap:'anywhere'}}>{cue.text}</div>}
    <Audio src={staticFile('narration.wav')}/>
  </AbsoluteFill>;
};
const Root = () => <Composition id="HaikeStudioAvatar" component={Video} width={1080} height={1440} fps={30} durationInFrames={210} defaultProps={defaults} calculateMetadata={({props})=>({durationInFrames:Math.max(1,Math.round(props.duration*30)),height:props.template.startsWith('avatar-template3')?1440:1920})}/>;
registerRoot(Root);
