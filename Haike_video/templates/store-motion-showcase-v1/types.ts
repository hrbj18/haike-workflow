export type Box = [number, number, number, number];

export type ShowcaseLayout = 'wide' | 'portrait-left' | 'portrait-right' | 'portrait-center';

export type ShowcasePalette = {
  paper: string;
  ink: string;
  muted: string;
  blue: string;
  orange: string;
  line: string;
};

export type ShowcaseShot = {
  id: string;
  src: string;
  from: number;
  frames: number;
  offset: number;
  fit: 'contain' | 'cover';
  objectPosition?: string;
  layout: ShowcaseLayout;
  title: string;
  subtitle: string;
  kicker: string;
  chapter: string;
};

export type ShowcaseChapter = {id: string; from: number; label: string};

export type ShowcaseProps = {
  durationFrames: number;
  audio: string;
  brand: string;
  location: string;
  palette: ShowcasePalette;
  shots: ShowcaseShot[];
  chapters: ShowcaseChapter[];
  fontAssets?: {display: string; body: string};
  motion?: {enterFrames: number; exitFrames: number; lineFrames: number};
};

export type ShowcaseGeometry = {
  width: number;
  height: number;
  fps: number;
  brand: Box;
  topRule: Box;
  chapter: Box;
  progress: Box;
  location: Box;
  radius: number;
  layouts: Record<ShowcaseLayout, {
    footage: Box;
    title: Box;
    subtitle: Box;
    kicker: Box;
    titleSize: number;
    subtitleSize: number;
    align: 'left' | 'center';
  }>;
};
