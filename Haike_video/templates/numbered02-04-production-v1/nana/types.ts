// Generated additive adaptation; see build_sources.py and derivation.json.
export type Cue = {text: string; startMs: number; endMs: number; timestampMs: number | null; confidence: number | null};
export type Media = {file: string; width: number; height: number; kind?: 'image' | 'video';role?:'avatar'|'footage'};
export type Scene = {id: string; start: number; end: number; chapter: number; title: string; media?: Media; presenter?: Media; overlay?: Media; labels?: string[]; note?: string; cues?: Record<string, number>};
export type Episode = {version: 1; title: string; brand: string; partner: string; duration: number; fps: number; chapters: string[]; scenes: Scene[]; captions: Cue[]; voice: string; font: string; reference?: string; referenceClock?: {duration: number; anchors: [number, number][]; scope: string}; phrase: string; cards: string[]; palette: {paper: string; ink: string; accent: string; line: string; sheet: string}};
export type TemplateProps = {episodeFile: string; episode?: Episode};
