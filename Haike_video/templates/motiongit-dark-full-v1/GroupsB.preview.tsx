/** Developer-only isolated still entry. This is not a production render runner. */
import React from 'react';
import {Composition, registerRoot, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Context, GroupId, Props, Scene, Variant} from './types';
import {palette, SceneClock} from './shared';
import {GroupsB} from './GroupsB';

type CheckProps = {group: GroupId; portrait: boolean; variant: Variant; project?: Props; sceneIndex?: number};
const clocks: Partial<Record<GroupId, [number, number]>> = {
  s05: [52.7, 16.7], s06: [69.4, 8.7], s07: [78.1, 11.6],
  s08: [89.7, 13.22], s09: [102.92, 5.48], review: [110, 14],
};
const Check: React.FC<CheckProps> = ({group, portrait, variant, project, sceneIndex}) => {
  const frame = useCurrentFrame(), config = useVideoConfig();
  const [sourceStart, sourceDuration] = clocks[group] || [0, 14];
  const s: Scene = project ? project.scenes[sceneIndex ?? project.scenes.findIndex(s=>s.group===group)] : {id: `groups-b-still-${group}`, group, from: 0, frames: Math.round(sourceDuration * config.fps), mediaIds: [], content: {}, sourceStart, sourceDuration};
  const p: Props = project || {width: config.width, height: config.height, fps: config.fps, durationFrames: s.frames, variant, brand: '海客AI社区服务店', header: '', footer: '', scenes: [s], media: [], captions: []};
  const c: Context = {p, s, frame, seconds: frame / config.fps, portrait, t: palette(p)};
  return <><style>{"@font-face{font-family:DarkFullDisplay;src:local('Microsoft YaHei')}@font-face{font-family:DarkFullBody;src:local('Microsoft YaHei')}"}</style><SceneClock.Provider value={c}><GroupsB c={c}/></SceneClock.Provider></>;
};
const Root = () => <Composition id="GroupsBCheck" component={Check} width={1920} height={1080} fps={60} durationInFrames={1200} defaultProps={{group: 's07', portrait: false, variant: 'reference'}} calculateMetadata={({props}) => ({width: props.portrait ? 1440 : 1920, height: props.portrait ? 1800 : 1080, fps: props.portrait ? 30 : 60})}/>;
registerRoot(Root);
