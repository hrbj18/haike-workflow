import type {Caption} from '@remotion/captions';

export type TemplateNumber = 7 | 8 | 9;
export type PaletteVariant = 'blue-beige' | 'cyan-charcoal' | 'black-pink';
export type Cue = Caption & {start: number; end: number};
export type Box = {x: number; y: number; w: number; h: number};
export type SourceEdit = {
  id: string; sourceStartFrame: number; sourceEndFrame: number;
  startFrame: number; endFrame: number;
};
export type Chapter = {
  id: string; startFrame: number; endFrame: number;
  kind: 'presenter' | 'media' | 'graphic';
  heading: string[]; deck: string; points: string[];
};
export type Shot = {
  id: string; src: string; kind: 'video' | 'image';
  startFrame: number; endFrame: number; sourceOffsetFrames: number;
  fit: 'contain' | 'cover'; sourceLabel: string;
};
export type Graphic = {
  id: string; chapterId: string; kind: 'metric' | 'list' | 'process' | 'offer';
  heading: string; items: string[]; sourceCueIndices: number[];
};
export type SoundEvent = {
  id: string; role: 'dong' | 'impact' | 'whoosh' | 'tick'; timeMs: number;
  startFrame: number; endFrame: number; strength: number;
};
export type FullProps = {
  templateNumber: TemplateNumber; paletteVariant: PaletteVariant;
  ratio: '4x5'; width: 1440; height: 1800; fps: 30;
  duration: 30 | 45; durationInFrames: 900 | 1350; contentEndFrame: number; tailHoldFrames: number;
  avatarSrc: string; audioSrc: string; brand: string;
  presenterVideo?: {src:string;segments:{id:string;startFrame:number;endFrame:number;sourceOffsetFrames:number}[]};
  sourceEdits: SourceEdit[]; cues: Cue[]; chapters: Chapter[];
  shots: Shot[]; graphics: Graphic[]; soundEvents: SoundEvent[];
};
