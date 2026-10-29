export type Box = [number, number, number, number];

export type WallPalette = {
  paper: string;
  ink: string;
  muted: string;
  blue: string;
  orange: string;
  line: string;
};

export type WallCard = {
  id: string;
  title: string;
  category: string;
  badge: string;
  thumbnail: string;
  src: string;
  offset: number;
  fit: 'contain';
  objectPosition?: string;
  imageFit?: 'cover' | 'contain';
  imagePosition?: string;
  preview?: {from: number; frames: number; offset: number};
};

export type WallTab = {id: string; label: string; order: string[]};
export type WallTabChange = {from: number; tabId: string};

/** Global output-frame boundaries. Video plays continuously expandFrom..end. */
export type WallMoment = {
  id: string;
  cardId: string;
  tabId: string;
  cursorFrom: number;
  selectFrom: number;
  expandFrom: number;
  holdFrom: number;
  collapseFrom: number;
  end: number;
  sourceOffset: number;
};

export type WallProps = {
  durationFrames: number;
  audio: string;
  brand: string;
  title: string;
  closingTitle: string;
  footer?: string;
  palette: WallPalette;
  tabs: WallTab[];
  cards: WallCard[];
  moments: WallMoment[];
  tabChanges: WallTabChange[];
  fontAssets?: {display: string; body: string};
};

export type WallGeometry = {
  width: number;
  height: number;
  fps: number;
  brand: Box;
  title: Box;
  tabs: Box;
  grid: {x: number; y: number; columns: number; width: number; height: number; gapX: number; gapY: number};
  expanded: Box;
  footer: Box;
  cardFooter: number;
  radius: number;
  cascadeFrames: number;
  cascadeStagger: number;
  tabTransitionFrames: number;
  closingLeadFrames: number;
  titleSize: number;
  tabSize: number;
  cardTitleSize: number;
};

export type WallPhase = 'cascade' | 'wall' | 'reorder' | 'cursor' | 'selected' | 'expand' | 'play' | 'return' | 'closing';

export type WallState = {
  phase: WallPhase;
  tabId: string;
  previousTabId: string;
  reorder: number;
  activeMoment: WallMoment | null;
  selectedCardId: string | null;
  expand: number;
  selectedRect: Box | null;
};
