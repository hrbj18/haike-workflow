import React from 'react';
import {interpolate} from 'remotion';
import type {Direction, SoundEvent, VideoProps} from './types';
import layout from './layout.json';

export const clamp = {extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const};
export const motionProfile = (direction: Direction) => layout.motion.profiles[direction];

/** A selected sound transient drives one damped gesture; no continuous shake. */
export const hitPulse = (p: VideoProps, frame: number, roles: SoundEvent['role'][] = ['dong', 'impact', 'tick']) =>
  Math.max(0, ...(p.art.soundEvents ?? []).filter(e => roles.includes(e.role)).map(e => {
    const age = frame - e.startFrame;
    return age >= 0 && age <= 11 ? Math.exp(-age / 3.1) * Math.min(1, e.strength / .32) : 0;
  }));

export const phraseStart = (p: VideoProps, text: string, from: number, end: number) => {
  const words = p.art.wordCues.filter(w => w.startMs >= from * 1000 - 1 && w.endMs <= end * 1000 + 1);
  for (let i = 0; i < words.length; i++) {
    let joined = '';
    for (let j = i; j < Math.min(words.length, i + text.length + 1); j++) {
      joined += words[j].text;
      if (joined === text) return words[i].startMs;
      if (joined.length >= text.length) break;
    }
  }
  return null;
};

/** A business point lands once on the matching real word, if there is one. */
export const PointMotion: React.FC<{p: VideoProps; text: string; start: number; end: number; frame: number; fps: number; children?: React.ReactNode}> = ({p,text,start,end,frame,fps,children}) => {
  const ms = phraseStart(p, text, start, end), profile = motionProfile(p.art.direction);
  const age = ms === null ? -1 : frame - Math.ceil(ms * fps / 1000);
  const bump = age >= 0 && age < 10 ? Math.sin(Math.PI * age / 10) * Math.exp(-age / 9) : 0;
  return <span style={{display:'inline-block',scale:1 + bump * profile.pointPunch,translate:`0 ${-bump * 5}px`,transformOrigin:'center'}}>{children ?? text}</span>;
};

/** Brief edge marks acknowledge audible hits without covering the presenter. */
export const SoundPunctuation: React.FC<{p: VideoProps;frame:number}> = ({p,frame}) => {
  const pulse = hitPulse(p,frame,['dong','impact']), theme=layout.palette[p.art.direction];
  if (!pulse) return null;
  return <svg viewBox="0 0 1080 1920" style={{position:'absolute',inset:0,width:'100%',height:'100%',zIndex:42,pointerEvents:'none'}} aria-hidden="true">
    <g stroke={theme.accent} strokeWidth={3 + pulse * 3} fill="none" opacity={pulse * .85}>
      <path d={`M${67-pulse*11} 1584v46M${67-pulse*11} 1584h25M${1013+pulse*11} 1584v46M${1013+pulse*11} 1584h-25`}/>
      <path d={`M${69-pulse*8} 1767v-22M${69-pulse*8} 1767h28M${1011+pulse*8} 1767v-22M${1011+pulse*8} 1767h-28`}/>
    </g>
    <path d="M80 176H1000" stroke={theme.accent} strokeWidth="3" opacity={pulse*.7} strokeDasharray={`${interpolate(pulse,[0,1],[25,920])} 920`}/>
  </svg>;
};
