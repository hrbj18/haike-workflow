import React from 'react';
import type {Caption} from '@remotion/captions';
import {AbsoluteFill, Audio, Easing, OffthreadVideo, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import layout from './layout.json';
import {Captions, FONT, fittedSize} from './Captions';

export type Template7Scene = {
  id: string;
  start: number;
  end: number;
  mode: 'presenter' | 'broll';
  fit: 'contain' | 'cover';
  source_in: number;
  avatar_in: number;
  pip_in: number;
  summary?: {kicker?: string; title: string; body?: string};
  focus?: {value: string; label: string; color?: 'yellow' | 'red'};
};

export type Template7Props = {
  duration_seconds: number;
  title_lines: string[];
  title_emphasis?: string[];
  brand: string;
  tagline: string[];
  context_pill: string;
  source_pill: string;
  footer_note: string;
  development_label: string;
  media: {avatar: string; avatar_pip?: string; broll?: string; audio: string};
  scenes: Template7Scene[];
  cues: Caption[];
};

const palette = layout.palette;

const Highlighted: React.FC<{text: string; emphasis: string[]}> = ({text, emphasis}) => {
  const ordered = emphasis.filter(Boolean).sort((a, b) => b.length - a.length);
  const result: React.ReactNode[] = [];
  for (let index = 0; index < text.length;) {
    const match = ordered.find((word) => text.startsWith(word, index));
    if (match) {
      result.push(<span key={index} style={{color: palette.title_accent}}>{match}</span>);
      index += match.length;
    } else {
      result.push(<React.Fragment key={index}>{text[index]}</React.Fragment>);
      index++;
    }
  }
  return <>{result}</>;
};

const SceneWindow: React.FC<{scene: Template7Scene; media: Template7Props['media']}> = ({scene, media}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const main = layout.regions.main;
  const pip = layout.presenter_pip;
  const primarySource = scene.mode === 'presenter' ? media.avatar : media.broll!;
  const primaryIn = scene.mode === 'presenter' ? scene.avatar_in : scene.source_in;
  const enter = interpolate(frame, [0, layout.motion.card_enter_seconds * fps], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(...layout.motion.ease_out_cubic as [number, number, number, number]),
  });
  const cardMotion: React.CSSProperties = {opacity: enter, transform: `translateY(${(1 - enter) * layout.motion.card_enter_offset_y}px)`};
  return <AbsoluteFill style={{overflow: 'hidden', backgroundColor: palette.header}}>
    {scene.fit === 'contain' ? <OffthreadVideo src={staticFile(primarySource)} startFrom={Math.round(primaryIn * fps)} muted
      style={{position: 'absolute', width: '100%', height: '100%', objectFit: 'cover',
        filter: `blur(${layout.main_contain_background.blur_px}px) brightness(${layout.main_contain_background.brightness})`,
        transform: `scale(${layout.main_contain_background.scale})`}} /> : null}
    <OffthreadVideo
      src={staticFile(primarySource)}
      startFrom={Math.round(primaryIn * fps)}
      muted
      style={{position: 'absolute', width: '100%', height: '100%', objectFit: scene.fit}}
    />
    {scene.mode === 'broll' ? <div style={{position: 'absolute', left: pip.x - main.x, top: pip.y - main.y, width: pip.width, height: pip.height,
      borderRadius: '50%', overflow: 'hidden', border: `${pip.border_width}px solid ${palette.text}`, boxSizing: 'border-box', backgroundColor: palette.header}}>
      <OffthreadVideo src={staticFile(media.avatar_pip ?? media.avatar)} startFrom={Math.round(scene.pip_in * fps)} muted
        style={{width: '100%', height: '100%', objectFit: 'cover', objectPosition: pip.object_position}} />
    </div> : null}
    {scene.summary ? <div style={{position: 'absolute', left: layout.summary.x - main.x, top: layout.summary.y - main.y,
      width: layout.summary.width, height: layout.summary.height, padding: layout.summary.padding, boxSizing: 'border-box',
      borderRadius: layout.summary.radius, backgroundColor: palette.card, border: `1px solid ${palette.cyan}77`, ...cardMotion}}>
      {scene.summary.kicker ? <div style={{fontSize: layout.summary.kicker_size, color: palette.cyan, marginBottom: 10}}>{scene.summary.kicker}</div> : null}
      <div style={{fontSize: fittedSize(scene.summary.title, layout.summary.title_size, layout.summary.title_min_size, layout.summary.width - layout.summary.padding * 2), lineHeight: 1.2}}>{scene.summary.title}</div>
      {scene.summary.body ? <div style={{fontSize: fittedSize(scene.summary.body, layout.summary.body_size, layout.summary.body_min_size, layout.summary.width - layout.summary.padding * 2), color: palette.muted, marginTop: 17, lineHeight: 1.35, whiteSpace: 'nowrap'}}>{scene.summary.body}</div> : null}
    </div> : null}
    {scene.focus ? <div style={{position: 'absolute', left: layout.focus.x - main.x, top: layout.focus.y - main.y,
      width: layout.focus.width, height: layout.focus.height, textAlign: 'center', ...cardMotion}}>
      <div style={{position: 'absolute', top: layout.focus.number_top, width: '100%', opacity: layout.focus.number_opacity,
        color: palette.text, fontSize: fittedSize(scene.focus.value, layout.focus.value_size, layout.focus.value_min_size, layout.focus.width), lineHeight: 1}}>{scene.focus.value}</div>
      <div style={{position: 'absolute', top: layout.focus.label_top, width: '100%', color: scene.focus.color === 'red' ? palette.red : palette.title_accent,
        fontSize: fittedSize(scene.focus.label, layout.focus.label_size, layout.focus.label_min_size, layout.focus.width - 2 * layout.focus.stroke_width),
        lineHeight: 1.2, whiteSpace: 'nowrap', WebkitTextStroke: `${layout.focus.stroke_width}px ${palette.stroke}`,
        paintOrder: 'stroke fill', textShadow: `3px 4px 1px ${palette.stroke}`}}>{scene.focus.label}</div>
    </div> : null}
  </AbsoluteFill>;
};

export const AvatarTemplate7: React.FC<Template7Props> = (props) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const title = layout.title;
  const main = layout.regions.main;
  const footer = layout.regions.footer;
  return <AbsoluteFill style={{fontFamily: FONT, fontWeight: layout.fonts.weight, color: palette.text, background: palette.header}}>
    <div style={{position: 'absolute', ...layout.regions.header, left: layout.regions.header.x, top: layout.regions.header.y, overflow: 'hidden'}}>
      {Array.from({length: layout.stars.count}, (_, index) => <div key={index} style={{position: 'absolute',
        left: (index * 193 + 47) % layout.canvas.width, top: (index * 137 + 31) % layout.regions.header.height,
        width: 1 + index % layout.stars.max_radius, height: 1 + index % layout.stars.max_radius,
        borderRadius: '50%', backgroundColor: index % 5 === 0 ? palette.cyan : palette.text, opacity: layout.stars.opacity}} />)}
      <div style={{position: 'absolute', left: title.x, top: title.y, width: title.width, height: title.height,
        display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center',
        lineHeight: title.line_height, transform: `skewX(${title.skew_degrees}deg)`, textShadow: '0 3px 12px #000'}}>
        {props.title_lines.map((line, index) => <div key={index} style={{fontSize: fittedSize(line, title.font_size, title.min_font_size, title.width), whiteSpace: 'nowrap'}}><Highlighted text={line} emphasis={props.title_emphasis ?? []} /></div>)}
      </div>
    </div>
    {props.scenes.map((scene) => <Sequence key={scene.id} from={Math.round(scene.start * fps)}
      durationInFrames={Math.round(scene.end * fps) - Math.round(scene.start * fps)} premountFor={fps}
      style={{left: main.x, top: main.y, width: main.width, height: main.height}}>
      <SceneWindow scene={scene} media={props.media} />
    </Sequence>)}
    <div style={{position: 'absolute', left: footer.x, top: footer.y, width: footer.width, height: footer.height,
      background: `linear-gradient(180deg, ${palette.footer_top}, ${palette.footer_bottom})`}} />
    <div style={{position: 'absolute', left: 0, top: layout.dividers.top_y, width: layout.canvas.width, height: layout.dividers.height, backgroundColor: layout.dividers.color}} />
    <div style={{position: 'absolute', left: 0, top: layout.dividers.bottom_y, width: layout.canvas.width, height: layout.dividers.height, backgroundColor: layout.dividers.color}} />
    <div style={{position: 'absolute', left: layout.brand.x, top: layout.brand.y, width: layout.brand.width, height: layout.brand.height,
      fontSize: fittedSize(props.brand, layout.brand.font_size, layout.brand.min_font_size, layout.brand.width), textAlign: 'center', lineHeight: 1.35, letterSpacing: 3}}>{props.brand}</div>
    {(['context_pill', 'source_pill'] as const).map((name) => <div key={name} style={{position: 'absolute', left: layout[name].x, top: layout[name].y,
      width: layout[name].width, height: layout[name].height, fontSize: fittedSize(props[name], layout[name].font_size, layout[name].min_font_size, layout[name].width - 30),
      display: 'flex', alignItems: 'center', justifyContent: 'center', color: palette.text, backgroundColor: '#111019AA', borderRadius: layout[name].radius,
      border: '1px solid #FFFFFF44'}}>{props[name]}</div>)}
    <div style={{position: 'absolute', left: layout.footer_note.x, top: layout.footer_note.y, width: layout.footer_note.width, height: layout.footer_note.height,
      fontSize: fittedSize(props.footer_note, layout.footer_note.font_size, layout.footer_note.min_font_size, layout.footer_note.width - 32),
      display: 'flex', alignItems: 'center', justifyContent: 'center', color: palette.cyan, backgroundColor: '#FFFFFF0D', borderRadius: layout.footer_note.radius,
      border: `1px solid ${palette.cyan}44`}}>{props.footer_note}</div>
    <div style={{position: 'absolute', left: layout.tagline.x, top: layout.tagline.y, width: layout.tagline.width, height: layout.tagline.height,
      textAlign: 'center', color: palette.muted, lineHeight: layout.tagline.line_height}}>
      {props.tagline.map((line, index) => <div key={index} style={{fontSize: fittedSize(line, layout.tagline.font_size, layout.tagline.min_font_size, layout.tagline.width), whiteSpace: 'nowrap'}}>{line}</div>)}
    </div>
    <Captions cues={props.cues} timeMs={frame / fps * 1000} />
    <div style={{position: 'absolute', left: layout.development_label.x, top: layout.development_label.y, width: layout.development_label.width,
      height: layout.development_label.height, fontSize: layout.development_label.font_size, color: palette.muted, fontWeight: 500}}>{props.development_label}</div>
    <Audio src={staticFile(props.media.audio)} />
  </AbsoluteFill>;
};
