export type Box = [number, number, number, number];

export type PilotPalette = {
  paper: string;
  ink: string;
  muted: string;
  blue: string;
  orange: string;
  line: string;
  dark: string;
  light: string;
};

export type PilotMedia = {
  id: string;
  src: string;
  thumbnail: string;
  label?: string;
  offset: number;
  fit: 'contain';
  objectPosition?: string;
  orientation?: 'portrait' | 'landscape';
};

export type PilotPresenter = {
  src: string;
  from: number;
  frames: number;
  offset: number;
  fit: 'contain';
  objectPosition?: string;
};

export type PresenterMode = {from: number; frames: number; mode: 'large' | 'small'};

export type PilotSelection = {
  cursorFrom: number;
  selectFrom: number;
  expandFrom: number;
  holdFrom: number;
};

export type PilotScene = {
  id: string;
  from: number;
  frames: number;
  module: 'statement' | 'select' | 'focus' | 'wall';
  theme: 'dark' | 'paper';
  title: string;
  subtitle?: string;
  mediaId?: string;
  secondaryMediaId?: string;
  selection?: PilotSelection;
  wallMediaIds?: string[];
};

export type PilotCaption = {text: string; startMs: number; endMs: number};

export type NarratedPilotProps = {
  visualStyle?: 'original' | 'hum';
  durationFrames: number;
  audio: string;
  brand: string;
  footer: string;
  wallCategories?: string[];
  palette: PilotPalette;
  presenter?: PilotPresenter;
  presenterModes?: PresenterMode[];
  media: PilotMedia[];
  scenes: PilotScene[];
  captions: PilotCaption[];
  fontAssets?: {display: string; body: string};
};

export type PilotGeometry = {
  width: number;
  height: number;
  fps: number;
  brand: Box;
  footer: Box;
  captions: Box;
  captionSize: number;
  statement: {title: Box; subtitle: Box; line: Box; titleSize: number};
  sceneHeader: {title: Box; subtitle: Box; titleSize: number};
  select: {primary: Box; secondary: Box; expanded: Box; portraitExpanded: Box; footerHeight: number; radius: number};
  focus: {entry: Box; expanded: Box; label: Box; portraitEntry: Box; portraitExpanded: Box; portraitLabel: Box};
  presenter: {large: Box; small: Box; plate: Box; title: Box; transitionFrames: number};
};
