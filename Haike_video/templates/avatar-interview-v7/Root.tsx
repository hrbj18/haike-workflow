import React from 'react';
import {Composition} from 'remotion';
import layout from './layout.json';
import {AvatarTemplate7, type Template7Props} from './Composition';

export const Root: React.FC = () => (
  <Composition
    id="AvatarTemplate7Sample"
    component={AvatarTemplate7}
    width={layout.canvas.width}
    height={layout.canvas.height}
    fps={layout.canvas.fps}
    durationInFrames={20 * layout.canvas.fps}
    defaultProps={{
      duration_seconds: 20,
      title_lines: ['数字人模板7', '访谈视觉结构测试'],
      title_emphasis: [],
      brand: '海客 AI 观察',
      tagline: ['人物讲解 · 证据素材 · 重点字幕'],
      context_pill: '视觉结构测试',
      source_pill: '来源：用户参考片',
      footer_note: '数字人模板7 · 本地结构验证',
      development_label: '结构开发样片 · 引用原片音画',
      media: {avatar: 'avatar.mp4', broll: 'broll.mp4', audio: 'audio.wav'},
      scenes: [],
      cues: [],
    } satisfies Template7Props}
    calculateMetadata={({props}) => ({durationInFrames: Math.round(props.duration_seconds * layout.canvas.fps)})}
  />
);
