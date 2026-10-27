import React, {useEffect, useState} from 'react';
import {
  AbsoluteFill, Audio, Composition, Easing, Img, OffthreadVideo, Sequence,
  cancelRender, continueRender, delayRender, interpolate, registerRoot,
  staticFile, useCurrentFrame,
} from 'remotion';
import geometryJson from './layout.json';
import type {Box, WallCard, WallGeometry, WallMoment, WallProps, WallState} from './types';

export type {WallCard, WallMoment, WallProps, WallState} from './types';

const geometry = geometryJson as WallGeometry;
const DISPLAY = 'HaikeMaterialWallDisplay';
const BODY = 'HaikeMaterialWallBody';
const fontLoads = new Map<string, Promise<void>>();
const clamp = {extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const};
const ease = Easing.bezier(.2, .78, .18, 1);
const progress = (frame: number, start: number, end: number) => interpolate(frame, [start, end], [0, 1], clamp);
const eased = (frame: number, start: number, end: number) => interpolate(frame, [start, end], [0, 1], {...clamp, easing: ease});
const rectangle = (box: Box): React.CSSProperties => ({position: 'absolute', left: box[0], top: box[1], width: box[2], height: box[3], boxSizing: 'border-box'});
const mixBox = (a: Box, b: Box, amount: number): Box => a.map((value, i) => value + (b[i] - value) * amount) as Box;

export function materialWallGridRect(index: number): Box {
  const g = geometry.grid;
  return [g.x + (index % g.columns) * (g.width + g.gapX),
    g.y + Math.floor(index / g.columns) * (g.height + g.gapY), g.width, g.height];
}

/** Pure state model: rendered identity, geometry and actual video clock share it. */
export function materialWallStateAt(p: WallProps, frame: number): WallState {
  let changeIndex = 0;
  for (let i = 0; i < p.tabChanges.length; i++) if (p.tabChanges[i].from <= frame) changeIndex = i;
  const change = p.tabChanges[changeIndex] || {from: 0, tabId: p.tabs[0]?.id || ''};
  const previous = p.tabChanges[Math.max(0, changeIndex - 1)] || change;
  const reorder = changeIndex === 0 ? 1 : eased(frame, change.from, change.from + geometry.tabTransitionFrames);
  const active = p.moments.find(m => frame >= m.cursorFrom && frame < m.end) || null;
  const selected = active && frame >= active.selectFrom ? active : null;
  let expand = 0;
  let phase: WallState['phase'] = frame < geometry.cascadeFrames + (p.cards.length - 1) * geometry.cascadeStagger ? 'cascade'
    : reorder < 1 ? 'reorder' : frame >= p.durationFrames - geometry.closingLeadFrames ? 'closing' : 'wall';
  if (active) {
    if (frame < active.selectFrom) phase = 'cursor';
    else if (frame < active.expandFrom) phase = 'selected';
    else if (frame < active.holdFrom) {phase = 'expand'; expand = eased(frame, active.expandFrom, active.holdFrom);}
    else if (frame < active.collapseFrom) {phase = 'play'; expand = 1;}
    else {phase = 'return'; expand = 1 - eased(frame, active.collapseFrom, active.end);}
  }
  const selectedTab = selected ? p.tabs.find(t => t.id === selected.tabId) : null;
  const selectedIndex = selectedTab && selected ? selectedTab.order.indexOf(selected.cardId) : -1;
  return {phase, tabId: change.tabId, previousTabId: previous.tabId, reorder, activeMoment: active,
    selectedCardId: selected?.cardId || null, expand,
    selectedRect: selectedIndex >= 0 ? mixBox(materialWallGridRect(selectedIndex), geometry.expanded, expand) : null};
}

const Fonts: React.FC<{assets: NonNullable<WallProps['fontAssets']>; children: React.ReactNode}> = ({assets, children}) => {
  const [hold] = useState(() => delayRender('Loading material-wall fonts', {timeoutInMilliseconds: 120000}));
  const key = `${assets.display}|${assets.body}`;
  useEffect(() => {
    if (!fontLoads.has(key)) fontLoads.set(key, (async () => {
      const display = new FontFace(DISPLAY, `url("${staticFile(assets.display)}")`, {weight: '700'});
      const body = new FontFace(BODY, `url("${staticFile(assets.body)}")`, {weight: '400'});
      document.fonts.add(await display.load());
      document.fonts.add(await body.load());
      await Promise.all([
        document.fonts.load(`700 70px ${DISPLAY}`, '走近身边的AI'),
        document.fonts.load(`400 28px ${BODY}`, '海客社区现场'),
      ]);
      if (!document.fonts.check(`700 70px ${DISPLAY}`) || !document.fonts.check(`400 28px ${BODY}`)) throw new Error('Material-wall font did not finish loading');
    })());
    fontLoads.get(key)!.then(() => continueRender(hold)).catch(cancelRender);
    return () => continueRender(hold);
  }, [assets.display, assets.body, hold, key]);
  return <>{children}</>;
};

function cardGridState(p: WallProps, state: WallState, card: WallCard) {
  const oldOrder = p.tabs.find(t => t.id === state.previousTabId)?.order || [];
  const newOrder = p.tabs.find(t => t.id === state.tabId)?.order || [];
  const oldIndex = oldOrder.indexOf(card.id);
  const nextIndex = newOrder.indexOf(card.id);
  const fallback = p.cards.findIndex(c => c.id === card.id);
  const oldBox = materialWallGridRect(oldIndex >= 0 ? oldIndex : nextIndex >= 0 ? nextIndex : fallback);
  const newBox = materialWallGridRect(nextIndex >= 0 ? nextIndex : oldIndex >= 0 ? oldIndex : fallback);
  const box = mixBox(oldBox, newBox, state.reorder);
  const visibility = oldIndex >= 0 && nextIndex >= 0 ? 1
    : oldIndex >= 0 ? 1 - state.reorder : nextIndex >= 0 ? state.reorder : 0;
  return {box, visibility, cascadeIndex: p.tabs[0]?.order.indexOf(card.id) ?? fallback};
}

const MaterialCard: React.FC<{p: WallProps; state: WallState; card: WallCard}> = ({p, state, card}) => {
  const frame = useCurrentFrame();
  const grid = cardGridState(p, state, card);
  const isSelected = state.selectedCardId === card.id;
  const moment = isSelected ? state.activeMoment : null;
  const box = isSelected && state.selectedRect ? state.selectedRect : grid.box;
  const enter = eased(frame, Math.max(0, grid.cascadeIndex) * geometry.cascadeStagger,
    Math.max(0, grid.cascadeIndex) * geometry.cascadeStagger + geometry.cascadeFrames);
  const expand = isSelected ? state.expand : 0;
  const select = moment ? eased(frame, moment.selectFrom, moment.expandFrom) : 0;
  const returnFade = moment && frame >= moment.collapseFrom ? 1 - progress(frame, moment.end - 7, moment.end) : 1;
  const displayFont = p.fontAssets ? DISPLAY : 'SimHei, Microsoft YaHei, sans-serif';
  const bodyFont = p.fontAssets ? BODY : 'Microsoft YaHei, sans-serif';
  const mediaHeight = box[3] - geometry.cardFooter;
  return <div data-element="material-card" data-card-id={card.id} data-selected={isSelected ? 'true' : 'false'}
    style={{...rectangle(box), opacity: enter * grid.visibility, zIndex: isSelected ? 20 : 1,
      transform: `translateY(${(1 - enter) * 34}px) scale(${.965 + .035 * enter})`, transformOrigin: '50% 50%',
      borderRadius: geometry.radius, backgroundColor: '#FFFFFF',
      boxShadow: `0 ${8 + select * 10}px ${22 + select * 36}px rgba(26, 36, 48, ${.07 + select * .13})`}}>
    <div data-element="card-media" style={{position: 'absolute', inset: `0 0 ${geometry.cardFooter}px 0`, overflow: 'hidden',
      borderRadius: `${geometry.radius}px ${geometry.radius}px 0 0`, backgroundColor: p.palette.line}}>
      <Img data-element="card-poster" src={staticFile(card.thumbnail)} style={{width: '100%', height: '100%',
        objectFit: card.imageFit || 'cover', objectPosition: card.imagePosition || '50% 50%'}} />
      {card.preview && !isSelected && <Sequence layout="none" from={card.preview.from} durationInFrames={card.preview.frames}>
        <OffthreadVideo data-element="card-preview" src={staticFile(card.src)} startFrom={Math.round(card.preview.offset * geometry.fps)} muted
          style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: card.imageFit || 'cover', objectPosition: card.imagePosition || '50% 50%'}} />
      </Sequence>}
      {moment && <Sequence layout="none" from={moment.expandFrom} durationInFrames={moment.end - moment.expandFrom}>
        <OffthreadVideo data-element="expanded-video" src={staticFile(card.src)} startFrom={Math.round(moment.sourceOffset * geometry.fps)} muted
          style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain',
            objectPosition: card.objectPosition || '50% 50%', backgroundColor: '#131A20'}} />
      </Sequence>}
      <div data-element="card-category" style={{position: 'absolute', left: 14, top: 14,
        fontFamily: bodyFont, fontSize: 19, lineHeight: 1.2, color: p.palette.ink, backgroundColor: 'rgba(255,255,255,.94)',
        padding: '7px 11px', borderRadius: 8, opacity: 1 - expand}}>{card.category}</div>
      <div data-element="card-badge" style={{position: 'absolute', right: 14, top: 14,
        fontFamily: bodyFont, fontSize: 18, lineHeight: 1.2, color: '#FFFFFF', backgroundColor: p.palette.blue,
        padding: '7px 10px', borderRadius: 8, opacity: 1 - expand}}>{card.badge}</div>
    </div>
    <div data-element="card-title" style={{position: 'absolute', top: mediaHeight, left: 17, right: 17, height: geometry.cardFooter,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 20, overflow: 'hidden',
      fontFamily: displayFont, fontWeight: 700, fontSize: geometry.cardTitleSize + expand * 10, color: p.palette.ink}}>
      <span style={{whiteSpace: 'nowrap'}}>{card.title}</span>
      {expand > .7 && <span style={{fontFamily: bodyFont, fontSize: 23, color: p.palette.muted, whiteSpace: 'nowrap'}}>{p.brand}</span>}
    </div>
    <div data-element="selection-border" style={{position: 'absolute', inset: -3, borderRadius: geometry.radius + 2,
      border: `4px solid ${p.palette.blue}`, opacity: select * returnFade, pointerEvents: 'none'}} />
  </div>;
};

function targetFor(p: WallProps, moment: WallMoment): [number, number] {
  const index = p.tabs.find(t => t.id === moment.tabId)?.order.indexOf(moment.cardId) ?? 0;
  const box = materialWallGridRect(Math.max(0, index));
  return [box[0] + box[2] * .58, box[1] + box[3] * .48];
}

const Cursor: React.FC<{p: WallProps; state: WallState}> = ({p, state}) => {
  const frame = useCurrentFrame();
  const m = state.activeMoment;
  if (!m || frame >= m.expandFrom + 8) return null;
  const index = p.moments.indexOf(m);
  const origin: [number, number] = index > 0 ? targetFor(p, p.moments[index - 1]) : [1700, 230];
  const target = targetFor(p, m);
  const move = eased(frame, m.cursorFrom, m.selectFrom - 2);
  const x = origin[0] + (target[0] - origin[0]) * move;
  const y = origin[1] + (target[1] - origin[1]) * move;
  const click = progress(frame, m.selectFrom, m.selectFrom + 10);
  const opacity = frame < m.expandFrom ? 1 : 1 - progress(frame, m.expandFrom, m.expandFrom + 8);
  const press = interpolate(frame, [m.selectFrom - 1, m.selectFrom + 3, m.selectFrom + 9], [1, .82, 1], clamp);
  return <div data-element="cursor" style={{position: 'absolute', left: x, top: y, width: 52, height: 62,
    opacity, zIndex: 40, transform: `scale(${press})`, transformOrigin: '0 0'}}>
    {frame >= m.selectFrom && frame < m.selectFrom + 14 && <div data-element="click-ring" style={{position: 'absolute',
      left: -18 - click * 20, top: -18 - click * 20, width: 36 + click * 40, height: 36 + click * 40,
      borderRadius: '50%', border: `3px solid ${p.palette.orange}`, opacity: 1 - click}} />}
    <svg viewBox="0 0 52 62" width="52" height="62" style={{filter: 'drop-shadow(0 3px 3px rgba(0,0,0,.2))'}}>
      <path d="M4 3 L7 48 L19 37 L29 58 L39 53 L29 32 L46 31 Z" fill={p.palette.ink} stroke="#FFFFFF" strokeWidth="3" strokeLinejoin="round" />
    </svg>
  </div>;
};

const WallContent: React.FC<WallProps> = p => {
  const frame = useCurrentFrame();
  const state = materialWallStateAt(p, frame);
  const closingFrom = p.durationFrames - geometry.closingLeadFrames;
  const close = progress(frame, closingFrom, closingFrom + 12);
  const displayFont = p.fontAssets ? DISPLAY : 'SimHei, Microsoft YaHei, sans-serif';
  const bodyFont = p.fontAssets ? BODY : 'Microsoft YaHei, sans-serif';
  let tabX = 0;
  return <AbsoluteFill data-element="canvas" data-template="store-material-wall-v1" data-phase={state.phase}
    style={{backgroundColor: p.palette.paper, color: p.palette.ink, fontFamily: bodyFont, fontSynthesis: 'none'}}>
    <div data-element="brand" style={{...rectangle(geometry.brand), display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      fontSize: 28, zIndex: 30}}><span>{p.brand}</span><span style={{fontSize: 22, color: p.palette.muted, letterSpacing: 3}}>HAIKE AI</span></div>
    <div data-element="main-title" style={{...rectangle(geometry.title), zIndex: 5, fontFamily: displayFont, fontWeight: 700,
      fontSize: geometry.titleSize, letterSpacing: -1, whiteSpace: 'nowrap', lineHeight: 1.2,
      opacity: 1 - state.expand * .9}}>
      <span style={{opacity: 1 - close}}>{p.title}</span>
      <span data-element="closing-title" style={{position: 'absolute', left: 0, top: 0, opacity: close,
        transform: `translateY(${(1 - close) * 12}px)`}}>{p.closingTitle}</span>
    </div>
    <div data-element="category-tabs" style={{...rectangle(geometry.tabs), zIndex: 5}}>
      {p.tabs.map(tab => {
        const width = 48 + [...tab.label].reduce((sum, ch) => sum + (/^[\x00-\x7F]$/.test(ch) ? .58 : 1), 0) * geometry.tabSize;
        const x = tabX;
        tabX += width + 18;
        const active = tab.id === state.tabId;
        return <div key={tab.id} data-element="category-tab" data-tab-id={tab.id} data-active={active ? 'true' : 'false'}
          style={{position: 'absolute', left: x, top: 0, width, height: geometry.tabs[3], borderRadius: 28,
            border: `1px solid ${active ? p.palette.blue : p.palette.line}`, backgroundColor: active ? p.palette.blue : '#FFFFFF',
            color: active ? '#FFFFFF' : p.palette.ink, fontSize: geometry.tabSize, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>{tab.label}</div>;
      })}
    </div>
    {p.cards.map(card => <MaterialCard key={card.id} p={p} card={card} state={state} />)}
    <div data-element="focus-scrim" style={{position: 'absolute', inset: 0, zIndex: 10,
      backgroundColor: p.palette.paper, opacity: state.expand * .88, pointerEvents: 'none'}} />
    <Cursor p={p} state={state} />
    <div data-element="footer" style={{...rectangle(geometry.footer), display: 'flex', justifyContent: 'space-between',
      alignItems: 'center', fontSize: 25, color: p.palette.muted, zIndex: 5}}>
      <span>{p.footer || '真实门店 · 实拍记录'}</span><span>{state.phase === 'closing' ? p.brand : '门头 · 机器人 · 亲子体验 · 店内日常'}</span>
    </div>
    {p.audio && <Audio src={staticFile(p.audio)} />}
  </AbsoluteFill>;
};

export const StoreMaterialWall: React.FC<WallProps> = p => p.fontAssets
  ? <Fonts assets={p.fontAssets}><WallContent {...p} /></Fonts>
  : <WallContent {...p} />;

const defaults: WallProps = {
  durationFrames: 840, audio: '', brand: '海客AI社区服务站', title: '走近身边的AI，先从这里看看', closingTitle: '来店里，看看AI',
  footer: '真实门店 · 实拍记录', palette: {paper: '#F6F5EF', ink: '#172027', muted: '#58616B', blue: '#3152D9', orange: '#E96835', line: '#D9DDD8'},
  tabs: [], cards: [], moments: [], tabChanges: [],
};

const Root: React.FC = () => <Composition id="StoreMaterialWall" component={StoreMaterialWall} width={geometry.width} height={geometry.height}
  fps={geometry.fps} durationInFrames={840} defaultProps={defaults}
  calculateMetadata={({props}) => ({durationInFrames: props.durationFrames})} />;

registerRoot(Root);
