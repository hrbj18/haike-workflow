import React, {useCallback, useEffect, useMemo, useRef} from 'react';
import {OffthreadVideo, staticFile, useCurrentFrame, delayRender, continueRender, cancelRender} from 'remotion';
import {Application, Sprite, Texture} from 'pixi.js';
import {AdjustmentFilter, ShockwaveFilter} from 'pixi-filters';
import transitions from 'gl-transitions';
import createTransition from 'gl-transition';
import createTexture from 'gl-texture2d';
import type {Media} from './types';

// Integration only: upstream shaders/filters stay unchanged. Both engines are
// explicitly sought by the Remotion frame; no ticker or wall-clock animation.
export const EffectVideo:React.FC<{media:Media;width:number;height:number;effect:'warm'|'shock';transition?:string;background:string}>=({media,width,height,effect,transition,background})=>{
 const frame=useCurrentFrame(),host=useRef<HTMLCanvasElement>(null);
 const state=useRef<any>(null), latest=useRef<any>(null);
 const pending=useRef(new Set<number>());
 const handle=useMemo(()=>{const h=delayRender('Open-source GPU video frame',{timeoutInMilliseconds:120000});pending.current.add(h);return h},[frame]);
 const draw=useCallback(()=>{
  const s=state.current,v=latest.current;
  if(!s||!v||v.frame!==frame)return;
  try {
   const {ctx,input,app,sprite,filter,gl,bridge,from,to}=s;
   ctx.fillStyle=background;ctx.fillRect(0,0,width,height);
   const iw=v.image.videoWidth||v.image.naturalWidth||v.image.width,ih=v.image.videoHeight||v.image.naturalHeight||v.image.height;
   const scale=Math.min(width/iw,height/ih);ctx.drawImage(v.image,(width-iw*scale)/2,(height-ih*scale)/2,iw*scale,ih*scale);
   sprite.texture.source.update();
   if(effect==='shock')filter.time=Math.max(0,frame-12)/30;
   app.renderer.render(app.stage);
   const out=host.current!.getContext('2d')!;
   if(bridge&&frame<24){
    gl.bindBuffer(gl.ARRAY_BUFFER,s.buffer);gl.viewport(0,0,width,height);
    to.setPixels(app.canvas);bridge.draw(Math.min(1,frame/23),from,to,width,height);
    out.drawImage(gl.canvas,0,0);
   }else out.drawImage(app.canvas,0,0);
   for(const h of pending.current)continueRender(h);pending.current.clear();
  }catch(e){cancelRender(e as Error)}
 },[frame,width,height,effect,background]);
 const drawRef=useRef(draw);drawRef.current=draw;
 useEffect(()=>{
  let disposed=false;
  const app=new Application();
  (async()=>{
   await app.init({width,height,background,autoStart:false,preference:'webgl',preserveDrawingBuffer:true,antialias:true,resolution:1});app.stop();
   if(disposed){app.destroy(true);return}
   const input=document.createElement('canvas');input.width=width;input.height=height;
   const ctx=input.getContext('2d')!;
   const sprite=new Sprite(Texture.from(input));app.stage.addChild(sprite);
   const filter=effect==='shock'?new ShockwaveFilter({center:{x:width*.5,y:height*.52},amplitude:12,wavelength:110,speed:720,brightness:1.06,time:0}):new AdjustmentFilter({saturation:.85,contrast:1.04,red:1.025,blue:.97});
   sprite.filters=[filter];
   let gl:any,bridge:any,from:any,to:any,buffer:any;
   if(transition){
    const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
    gl=canvas.getContext('webgl',{preserveDrawingBuffer:true,alpha:false});if(!gl)throw new Error('GL Transitions requires WebGL');
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,true);buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,-1,4,4,-1]),gl.STATIC_DRAW);
    ctx.fillStyle=background;ctx.fillRect(0,0,width,height);
    from=createTexture(gl,input);to=createTexture(gl,input);from.minFilter=to.minFilter=gl.LINEAR;from.magFilter=to.magFilter=gl.LINEAR;
    const preset=transitions.find((t:any)=>t.name===transition);if(!preset)throw new Error('Unknown upstream transition '+transition);
    bridge=createTransition(gl,preset,{resizeMode:'stretch'});
   }
   state.current={input,ctx,app,sprite,filter,gl,bridge,from,to,buffer};drawRef.current();
  })().catch(cancelRender);
  return ()=>{disposed=true;const s=state.current;state.current=null;if(s){s.bridge?.dispose();s.from?.dispose();s.to?.dispose();s.gl?.getExtension('WEBGL_lose_context')?.loseContext();s.filter.destroy();s.app.destroy(true,{children:true,texture:true,textureSource:true})}for(const h of pending.current)continueRender(h);pending.current.clear()};
 },[media.src,width,height,effect,transition,background]);
 useEffect(()=>{draw()},[draw,handle]);
 const onFrame=useCallback((image:CanvasImageSource)=>{latest.current={image,frame};drawRef.current()},[frame]);
 return <><OffthreadVideo src={staticFile(media.src)} startFrom={Math.round(media.offset*30)} muted onVideoFrame={onFrame} style={{position:'absolute',width,height,opacity:0}}/><canvas ref={host} width={width} height={height} style={{width,height,display:'block'}}/></>;
};
