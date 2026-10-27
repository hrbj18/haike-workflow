export type Direction = 'community-showcase' | 'blue-editorial' | 'optical-cinema' | 'red-manifesto' | 'silver-launch' | 'documentary';
export type Cue = {text: string; startMs: number; endMs: number; timestampMs?: number | null; confidence?: number | null};
export type Chapter = {kind: 'hook' | 'story' | 'ai' | 'offer' | 'cta'; fromCue: number; toCue: number; heading: string[]; deck: string; points: string[]; start: number; end: number};
export type Scene = {id: string; src: string; kind: 'video' | 'image'; start: number; end: number; offset: number; fit: 'cover' | 'contain'; sourceLabel: string};
export type PhraseHighlight = {text: string; fromWord: number; toWord: number; startMs: number; endMs: number};
export type VideoProps = {duration: number; avatarSrc: string; audioSrc: string; brand: string; captions: Cue[]; art: {direction: Direction; backgroundSrc: string | null; chapters: Chapter[]; highlights: string[]; portraitFraming: 'close-4x5' | 'medium-9x16'; wordCues: Cue[]; phraseHighlights: PhraseHighlight[]; scenes: Scene[]}};
export type SceneProps = {p: VideoProps; chapter: Chapter; chapterIndex: number; frame: number; fps: number};
export type Box = {x: number; y: number; w: number; h: number; radius?: number | string};
