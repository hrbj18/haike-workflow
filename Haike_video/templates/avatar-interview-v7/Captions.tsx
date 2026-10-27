import React from 'react';
import type {Caption} from '@remotion/captions';
import layout from './layout.json';

export const FONT = `${layout.fonts.family}, ${layout.fonts.fallback}`;

export const fittedSize = (text: string, max: number, min: number, width: number): number => {
  if (text.includes('\n')) throw new Error('单行文字包含换行；请在输入中明确拆行');
  const canvas = typeof document === 'undefined' ? null : document.createElement('canvas');
  const context = canvas?.getContext('2d');
  const measure = (size: number): number => {
    if (!context) return Array.from(text).reduce((sum, char) => sum + (/^[\x00-\x7F]$/.test(char) ? size * 0.62 : size), 0);
    context.font = `${layout.fonts.weight} ${size}px ${FONT}`;
    return context.measureText(text).width;
  };
  for (let size = max; size >= min; size--) if (measure(size) <= width) return size;
  throw new Error(`文字在最小字号${min}px仍越界，请拆句或缩短：${text}`);
};

export const Captions: React.FC<{cues: Caption[]; timeMs: number}> = ({cues, timeMs}) => {
  const cue = cues.find((item) => item.startMs <= timeMs && timeMs < item.endMs);
  if (!cue) return null;
  const style = layout.captions;
  const size = fittedSize(cue.text, style.font_size, style.min_font_size, style.width - 2 * style.stroke_width);
  return <div style={{position: 'absolute', left: style.x, top: style.y, width: style.width, height: style.height,
    display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: FONT, fontWeight: layout.fonts.weight,
    fontSize: size, lineHeight: 1.1, color: layout.palette.text, whiteSpace: 'pre',
    transform: `skewX(${style.skew_degrees}deg)`, WebkitTextStroke: `${style.stroke_width}px ${layout.palette.stroke}`,
    paintOrder: 'stroke fill', textShadow: `2px 3px 2px ${layout.palette.stroke}`}}>{cue.text}</div>;
};
