import React from 'react';
import {Img, OffthreadVideo, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Box, Cue, Direction, Scene, VideoProps} from './types';
import layout from './layout.json';
import {hitPulse, motionProfile} from './Motion';
const clamp = {extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const};
const sans = '"Microsoft YaHei",sans-serif';
const position = (box: Box): React.CSSProperties => ({position: 'absolute', left: box.x, top: box.y, width: box.w, height: box.h, borderRadius: box.radius ?? 0, overflow: 'hidden'});

export const PresenterWindow: React.FC<{p: VideoProps; box: Box; objectPosition?: string; scale?: number; filter?: string}> = ({p, box, objectPosition = '50% 52%', scale = 1, filter}) => <div style={{...position(box), background: '#162127'}}><OffthreadVideo src={staticFile(p.avatarSrc)} muted style={{width: '100%', height: '100%', objectFit: 'cover', objectPosition, transform: `scale(${scale})`, filter}}/></div>;

export const MaterialWindow: React.FC<{scene: Scene; box: Box}> = ({scene, box}) => {
  const {fps} = useVideoConfig();
  const sharp: React.CSSProperties={position:'absolute',inset:0,width:'100%',height:'100%',objectFit:scene.fit};
  const extension: React.CSSProperties={...sharp,objectFit:'cover',filter:'blur(28px) brightness(.42)',transform:'scale(1.12)'};
  return <div style={{...position(box), background: '#111b20'}}>
    {scene.kind === 'video' ? <Sequence from={Math.round(scene.start * fps)} durationInFrames={Math.max(1, Math.ceil(scene.end * fps) - Math.round(scene.start * fps))} layout="none">{scene.fit==='contain'&&<OffthreadVideo src={staticFile(scene.src)} muted startFrom={Math.round(scene.offset * fps)} style={extension}/>}<OffthreadVideo src={staticFile(scene.src)} muted startFrom={Math.round(scene.offset * fps)} style={sharp}/></Sequence> : <>{scene.fit==='contain'&&<Img src={staticFile(scene.src)} style={extension}/>}<Img src={staticFile(scene.src)} style={sharp}/></>}
  </div>;
};

export const MotionTitle: React.FC<{lines: string[]; frame: number; fps: number; start: number; color: string; font?: string; size?: number; align?: 'left' | 'center'; width?: number}> = ({lines, frame, fps, start, color, font = sans, size = 112, align = 'left', width = 920}) => {
  const local = frame - Math.round(start * fps), ease = interpolate(local, [0, layout.motion.chapterRevealFrames], [0, 1], clamp);
  const fitted = Math.min(size, width / Math.max(...lines.map(l => [...l].length)));
  return <div style={{color, fontFamily: font, fontSize: fitted, fontWeight: 700, lineHeight: 1.15, letterSpacing: -2, textAlign: align, fontVariantNumeric: 'tabular-nums'}}>{lines.map((line, i) => <div key={line} style={{whiteSpace: 'nowrap',transformOrigin:align==='center'?'50% 60%':'0% 60%',translate:`0 ${interpolate(local-i*2,[0,4,10],[26,-3,0],clamp)}px`,scale:interpolate(local-i*2,[0,4,10],[.93,1.025,1],clamp)}}>{line}</div>)}</div>;
};

export type CaptionBeat = {text: string; startMs: number; endMs: number; words: Cue[]};
/** Split at supplied semantic line/punctuation boundaries and observed word
 * edges only. No interpolated word clocks and no omitted source characters. */
export const captionBeats = (p: VideoProps): CaptionBeat[] => {
  const out: CaptionBeat[] = [];
  for (const cue of p.captions) {
    const words = p.art.wordCues.filter(w => w.startMs >= cue.startMs - 1 && w.endMs <= cue.endMs + 1);
    if (!words.length) {out.push({...cue, words: []}); continue;}
    const semantic = cue.text.split(/[\n，。！？；：,!?;:]/).filter(Boolean);
    let offset = 0;
    for (const piece of semantic) {
      const count = [...piece.replace(/[\p{P}\p{Z}\s]/gu, '')].length;
      let remaining = count;
      while (remaining > 0 && offset < words.length) {
        const group: Cue[] = []; let length = 0;
        while (offset < words.length) {
          const w = words[offset], n = [...w.text.replace(/[\p{P}\p{Z}\s]/gu, '')].length;
          if (group.length && length + n > Math.min(remaining, layout.typography.maxBeatCharacters)) break;
          group.push(w); offset++; length += n;
          // Phrase-level holds: target nine characters, avoid an orphan tail.
          if (length >= layout.typography.targetBeatCharacters && remaining - length >= 4) break;
          if (length >= remaining) break;
        }
        if (!group.length) break;
        out.push({text: group.map(w => w.text).join(''), startMs: group[0].startMs, endMs: group[group.length-1].endMs, words: group});
        remaining -= length;
      }
    }
    if (offset < words.length) {const group = words.slice(offset); out.push({text: group.map(w=>w.text).join(''),startMs:group[0].startMs,endMs:group[group.length-1].endMs,words:group});}
  }
  return out;
};

export const CaptionTrack: React.FC<{p: VideoProps; box: {x: number; y: number; w: number; h?: number}; skin?: Direction}> = ({p, box, skin = p.art.direction}) => {
  const frame = useCurrentFrame(), {fps} = useVideoConfig(), ms = frame * 1000 / fps;
  const beat = captionBeats(p).find(b => ms >= b.startMs && ms < b.endMs);
  if (!beat) return null;
  const theme = layout.palette[skin], profile = motionProfile(skin);
  const blue = skin === 'blue-editorial', green = skin === 'community-showcase', red = skin === 'red-manifesto', silver = skin === 'silver-launch';
  const age = (ms - beat.startMs) * fps / 1000;
  const revealFrames = Math.min(layout.motion.captionRevealFrames, Math.max(4, (beat.endMs-beat.startMs)*fps/1000*.32));
  const settle = interpolate(age,[0,revealFrames*.42,revealFrames*.75,revealFrames],[profile.startScale,profile.overshoot,.995,1],clamp);
  const travel = interpolate(age,[0,revealFrames*.5,revealFrames],[1,-.12,0],clamp);
  const audioHit = hitPulse(p,frame);
  const lines = [...beat.text].length > 13 ? [[...beat.text].slice(0,8).join(''),[...beat.text].slice(8).join('')] : [beat.text];
  const units = Math.max(...lines.map(line => [...line].reduce((sum,ch)=>sum+(/^[\x00-\x7F]$/.test(ch)?.6:1),0)));
  const size = Math.min([...beat.text].length > 10 ? 64 : 74,(box.w-110)/units);
  const keywords = p.art.highlights.filter(word=>beat.text.includes(word)).sort((a,b)=>b.length-a.length);
  let textOffset=0;
  const makeLine = (line: string) => {
    const parts: React.ReactNode[]=[]; let at=0;
    while(at<line.length) {
      const match=keywords.find(k=>line.startsWith(k,at));
      if(match) {
        const globalAt=textOffset+at; let length=0; const indices:number[]=[];
        beat.words.forEach((w,i)=>{const start=length;length+=w.text.length;if(length>globalAt&&start<globalAt+match.length)indices.push(i);});
        const first=beat.words[indices[0]], last=beat.words[indices[indices.length-1]];
        const wordAge=first?(ms-first.startMs)*fps/1000:-100;
        const punch=match===keywords[0]&&wordAge>=0&&wordAge<9?Math.sin(Math.PI*wordAge/9)*Math.exp(-wordAge/8):0;
        const spoken=first&&ms>=first.startMs&&ms<last.endMs;
        const chip=blue?'#1745d9':silver?'#c5edf2':theme.accent;
        parts.push(<span key={at} style={{display:'inline-block',position:'relative',background:chip,color:blue?'#fff':green?'#183d2c':red?'#201b15':silver?'#163647':'#14191b',borderRadius:green?8:silver?7:2,margin:'0 3px',padding:'0 5px 3px',fontWeight:900,scale:1+punch*profile.wordPunch,translate: '0 '+(-punch*6)+'px',rotate:red?(-punch*.7)+'deg':'0deg',transformOrigin:'50% 80%',boxShadow:spoken?'0 4px 0 '+(blue?'#de4930':silver?'#00728b':'#f4efdf'):undefined}}>{match}</span>);
        at+=match.length;
      } else {parts.push(<span key={at}>{line[at]}</span>);at++;}
    }
    textOffset+=line.length; return parts;
  };
  const radius=green?22:silver?16:red?1:6;
  const progress=Math.min(1,Math.max(0,(ms-beat.startMs)/(beat.endMs-beat.startMs)));
  const scale=Math.min(1.075,settle*(1+audioHit*(red?.035:.02)));
  return <div style={{position:'absolute',left:box.x,top:box.y,width:box.w,zIndex:40,fontFamily:sans,scale,translate: (travel*profile.sideTravel)+'px '+(travel*profile.travel-audioHit*3)+'px',rotate:(travel*profile.tilt)+'deg',transformOrigin:'50% 65%'}}>
    <div style={{position:'absolute',inset:0,borderRadius:radius,background:blue?'#1745d9':theme.accent,translate:(blue?6:3)+'px '+(5+audioHit*3)+'px',opacity:blue?.9:.7}}/>
    <div style={{position:'relative',padding:'15px 18px 20px',borderRadius:radius,background:theme.captionBase,color:theme.captionText,border:silver?'1px solid #adc6d0':blue?'1px solid #fff':'1px solid '+theme.accent+'55',textAlign:'center',fontSize:size,fontWeight:800,lineHeight:1.32,letterSpacing:0,fontVariantNumeric:'tabular-nums',boxShadow:green?'0 10px 20px #193c2925':silver?'0 12px 24px #17435924':'0 9px 22px #0003'}}>
      {blue&&<div style={{position:'absolute',left:0,top:12,bottom:12,width:6,background:'#de4930'}}/>}
      {lines.map((line,i)=><div key={i} style={{whiteSpace:'nowrap'}}>{makeLine(line)}</div>)}
      <div style={{position:'absolute',left:18,right:18,bottom:1,height:3,background:theme.accent,scale:progress+' 1',transformOrigin:'left',opacity:blue?.35:.7}}/>
    </div>
  </div>;
};
