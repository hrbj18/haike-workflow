import React, {useEffect, useState} from 'react';
import {Audio, Img, OffthreadVideo, Sequence, cancelRender, continueRender, delayRender, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import plan from './layout.json';
export const W=540,H=960;
export type Design=typeof plan.directions[number];
export const limit=(x:number)=>Math.max(0,Math.min(1,x));
export const smooth=(x:number)=>{const p=limit(x);return p*p*(3-2*p);};
export const tween=(t:number,a:number,b:number,x:number,y:number)=>x+(y-x)*smooth((t-a)/(b-a));
export const sec=()=>useCurrentFrame()/useVideoConfig().fps;
export function Font(){const [handle]=useState(()=>delayRender('本地中文字体'));useEffect(()=>{new FontFace('Haike Sans',`url("${staticFile('font.ttf')}")`,{weight:'100 900'}).load().then(f=>{document.fonts.add(f);continueRender(handle);}).catch(cancelRender);},[handle]);return null;}
export function Sound(){return <Audio src={staticFile(plan.audio.file)} volume={plan.audio.gain}/>;}
export function Media({name,from=0,offset=0,still=false,position}:{name:string;from?:number;offset?:number;still?:boolean;position?:string}){
 const {fps}=useVideoConfig();
 const style:React.CSSProperties={position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'cover',objectPosition:position||(name.startsWith('host-')?'50% 25%':'50% 55%')};
 if(still)return <Img src={staticFile(name.replace('.mp4','.jpg'))} style={style}/>;
 return <Sequence from={Math.round(from*fps)} layout="none"><OffthreadVideo src={staticFile(name)} startFrom={Math.round(offset*fps)} muted style={style}/></Sequence>;
}
export function Topic({mode}:{mode:'phone'|'book'|'atlas'}){
 const base:React.CSSProperties={position:'absolute',zIndex:100,fontFamily:'Haike Sans',fontSize:22,fontWeight:850,lineHeight:1.3};
 if(mode==='phone')return <div style={{...base,top:32,left:24,padding:'10px 16px',background:'#F5FF57',color:'#163FEE',border:'3px solid #163FEE',boxShadow:'5px 5px 0 #163FEE'}}>亲子科技体验</div>;
 if(mode==='book')return <div style={{...base,top:25,left:21,color:'#FFF6DD',background:'#8C0E42',borderBottom:'3px solid #A9ECCB',padding:'7px 9px'}}>海客AI · 亲子探索</div>;
 return <div style={{...base,top:28,left:20,padding:'10px 13px',background:'#CEFF36',color:'#151D22',borderLeft:'9px solid #39A7F4'}}>亲子科技体验</div>;
}
export function PhaseLabel({text,color='#fff'}:{text:string;color?:string}){return <div style={{position:'absolute',bottom:35,right:24,color,fontFamily:'Haike Sans',fontSize:18,fontWeight:800,zIndex:90}}>{text}</div>;}
