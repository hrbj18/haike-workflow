import type React from 'react';
import type {Caption} from '@remotion/captions';

export type Ratio = '9x16' | '4x5' | '1x1' | '16x9';
export type Cue = Caption & {start: number; end: number};
export type Box = {x: number; y: number; w: number; h: number};
export type LabProps = {
  templateNumber: number; ratio: Ratio; width: number; height: number;
  fps: number; durationInFrames: number; avatarSrc: string; audioSrc: string;
  cues: Cue[]; brand: string; headline: string; cta: string; beatTitles: string[];
};
export type StyleComponent = React.FC<LabProps>;
