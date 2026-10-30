import React,{useCallback,useEffect,useMemo,useRef} from 'react';
import {AbsoluteFill,Composition,OffthreadVideo,Sequence,continueRender,delayRender,cancelRender,registerRoot,staticFile,useCurrentFrame} from 'remotion';
import {TransitionSeries,linearTiming} from '@remotion/transitions';
import {Application,Sprite,Texture} from 'pixi.js';
import {ShockwaveFilter} from 'pixi-filters';
import {whipPan} from './vendor/whip-pan';
import {pushThrough} from './vendor/push-through';
import {paperTear} from './vendor/paper-tear';
import {gridWaveShader} from './vendor/grid-wave';

export type Clip={src:string;offset:number};
export type Props={id:string;name:string;effect:'whip'|'push'|'tear'|'grid'|'touch';a:Clip;b:Clip;baseline?:boolean;trace?:boolean;track?:number[][]};
const W=1440,H=1800,N=135,START=45;
const duration=(p:Props)=>p.effect==='whip'?26:p.effect==='push'?40:36;
const progress=(f:number,d:number)=>Math.min(1,Math.max(0,(f-START)/(d-1)));
export function trackAt(points:number[][],frame:number){
 const next=points.findIndex(p=>p[0]>=frame);if(next===0)return points[0].slice(1);if(next<0)return points[points.length-1].slice(1);
 const a=points[next-1],b=points[next],t=(frame-a[0])/(b[0]-a[0]);return [a[1]+(b[1]-a[1])*t,a[2]+(b[2]-a[2])*t];
}
const Live:React.FC<{clip:Clip}>=({clip})=><AbsoluteFill style={{background:'#101314'}}><OffthreadVideo src={staticFile(clip.src)} startFrom={Math.round(clip.offset*30)} muted style={{width:'100%',height:'100%',objectFit:'contain'}}/></AbsoluteFill>;
const GPU:React.FC<{p:Props}>=({p})=>{
 const f=useCurrentFrame(),canvas=useRef<HTMLCanvasElement>(null),engine=useRef<any>(null),images=useRef<any>({}),pending=useRef(new Set<number>());
 const handle=useMemo(()=>{const h=delayRender('Verified footage texture',{timeoutInMilliseconds:120000});pending.current.add(h);return h},[f]);
 const draw=useCallback(()=>{
  const s=engine.current;if(!s||images.current.a?.frame!==f||(p.effect==='grid'&&images.current.b?.frame!==f))return;
  try{
   const fill=(key:string)=>{const img=images.current[key].image,ctx=s[key].getContext('2d');const iw=img.naturalWidth||img.videoWidth||img.width,ih=img.naturalHeight||img.videoHeight||img.height;const scale=Math.min(W/iw,H/ih);ctx.fillStyle='#101314';ctx.fillRect(0,0,W,H);ctx.drawImage(img,(W-iw*scale)/2,(H-ih*scale)/2,iw*scale,ih*scale)};
   fill('a');const out=canvas.current!.getContext('2d')!;
   if(p.effect==='grid'){
    fill('b');s.shader.draw({from:s.a,to:s.b,width:W,height:H,progress:progress(f,36),passedProps:{tileSize:150,waveWidth:.13,lift:3,gap:.12,tint:'#e1b55a',direction:'left'}});out.drawImage(s.surface,0,0);
   }else{
    const pt=trackAt(p.track!,f),x=(W-H*9/16)/2+pt[0]*H*9/16,y=pt[1]*H;
    s.filter.center={x,y};s.filter.time=Math.max(0,f-12)/30;s.sprite.filters=f>=12&&f<=54?[s.filter]:[];
    s.sprite.texture.source.update();s.app.renderer.render(s.app.stage);out.drawImage(s.app.canvas,0,0);
    if(p.trace&&f<=54){out.strokeStyle='#ffdf3e';out.lineWidth=5;out.beginPath();out.arc(x,y,22,0,Math.PI*2);out.stroke();out.fillStyle='#ffdf3e';out.font='32px sans-serif';out.fillText('手部操作点',Math.min(x+35,W-230),y-35)}
   }
   for(const h of pending.current)continueRender(h);pending.current.clear();
  }catch(e){cancelRender(e as Error)}
 },[f,p]);
 const drawRef=useRef(draw);drawRef.current=draw;
 useEffect(()=>{
  let stopped=false;const a=new OffscreenCanvas(W,H),b=new OffscreenCanvas(W,H);
  if(p.effect==='grid'){const surface=new OffscreenCanvas(W,H);engine.current={a,b,surface,shader:gridWaveShader(surface)};drawRef.current()}
  else{const app=new Application();app.init({width:W,height:H,autoStart:false,preference:'webgl',preserveDrawingBuffer:true,resolution:1}).then(()=>{if(stopped){app.destroy(true);return}app.stop();const sprite=new Sprite(Texture.from(a));app.stage.addChild(sprite);const filter=new ShockwaveFilter({speed:550,amplitude:24,wavelength:150,brightness:1.08,radius:520,time:0});engine.current={a,app,sprite,filter};drawRef.current()}).catch(cancelRender)}
  return()=>{stopped=true;const s=engine.current;engine.current=null;s?.shader?.cleanup();s?.filter?.destroy();s?.app?.destroy(true,{children:true,texture:true,textureSource:true});for(const h of pending.current)continueRender(h);pending.current.clear()};
 },[p.effect]);
 useEffect(()=>draw(),[draw,handle]);
 const onA=useCallback((image:CanvasImageSource)=>{images.current.a={image,frame:f};drawRef.current()},[f]);
 const onB=useCallback((image:CanvasImageSource)=>{images.current.b={image,frame:f};drawRef.current()},[f]);
 return <><OffthreadVideo src={staticFile(p.a.src)} startFrom={Math.round(p.a.offset*30)} muted onVideoFrame={onA} style={{opacity:0,position:'absolute',width:W,height:H}}/>{p.effect==='grid'&&<OffthreadVideo src={staticFile(p.b.src)} startFrom={Math.round(p.b.offset*30)} muted onVideoFrame={onB} style={{opacity:0,position:'absolute',width:W,height:H}}/>}<canvas ref={canvas} width={W} height={H} style={{width:W,height:H}}/></>;
};
export const Audition:React.FC<Props>=p=>{
 const f=useCurrentFrame(),d=duration(p),cut=START+Math.round(d/2);
 let content:React.ReactNode;
 if(p.baseline){content=p.effect==='touch'?<Live clip={p.a}/>:p.effect==='grid'?<Live key={f<cut?'a':'b'} clip={f<cut?p.a:p.b}/>:<><Sequence durationInFrames={cut}><Live clip={p.a}/></Sequence><Sequence from={cut} durationInFrames={N-cut}><Live clip={{...p.b,offset:p.b.offset+(cut-START)/30}}/></Sequence></>}
 else if(p.effect==='grid'||p.effect==='touch')content=<GPU p={p}/>;
 else{const presentation=p.effect==='whip'?whipPan({direction:'left',blur:30}):p.effect==='push'?pushThrough({zoom:2.6,blur:18}):paperTear({seed:12,roughness:.65,impact:.75});content=<TransitionSeries><TransitionSeries.Sequence durationInFrames={START+d}><Live clip={p.a}/></TransitionSeries.Sequence><TransitionSeries.Transition<any> timing={linearTiming({durationInFrames:d})} presentation={presentation}/><TransitionSeries.Sequence durationInFrames={N-START}><Live clip={p.b}/></TransitionSeries.Sequence></TransitionSeries>}
 return <AbsoluteFill style={{background:'#101314',overflow:'hidden'}}>{content}<div style={{position:'absolute',left:30,top:28,background:'rgba(16,19,20,.8)',color:'white',padding:'12px 20px',fontFamily:'Microsoft YaHei, sans-serif',fontSize:30}}>{p.id}　{p.name}{p.baseline?' · 原片对照':p.trace?' · 定位对照':''}</div></AbsoluteFill>;
};
const defaults:Props={id:'B01',name:'甩镜',effect:'whip',a:{src:'s023.mp4',offset:.2},b:{src:'s027.mp4',offset:.5}};
registerRoot(()=> <Composition id="MotionAudition" component={Audition} width={W} height={H} fps={30} durationInFrames={N} defaultProps={defaults}/>);

