import React from 'react';
import {Template06, Template07} from '../chromatic-six-video-batch-v1/window-a/Scene';
import {Template08, Template09} from '../chromatic-six-video-batch-v1/window-b/Scene';
import {Template10, Template11} from '../chromatic-six-video-batch-v1/window-c/Scene';
import bindings from './bindings.json';

const components = {
  Template06, Template07, Template08, Template09, Template10, Template11,
};
type Replay = {templateId: string; version: string; actionIds: string[]};
type ActionBinding = {id:string; templateId:string; version:string; component:string;
  ordinal:number; source:string; symbol:string; from:number; to:number;
  internalEvents:{id:string;from:number;to:number;meaning:string}[]};
const actionTable = new Map<string, ActionBinding>();
for (const recipe of Object.values(bindings)) {
  for (const action of recipe.actions) actionTable.set(action.id, action);
}

// A caller can locate an action in the unmodified source composition and seek
// its Player to initialFrame. Internal events are individually addressable.
// Never trim/restart the component: 11's world and presenter use global time.
export function locateAction(actionId: string, eventId?: string) {
  const action = actionTable.get(actionId);
  if (!action) throw new Error('未知动作编号');
  const event = eventId === undefined ? undefined : action.internalEvents.find(e=>e.id===eventId);
  if (eventId !== undefined && !event) throw new Error('未知内部动作事件');
  const Component = components[action.component as keyof typeof components];
  if (!Component) throw new Error('动作未绑定可调用实现');
  return {...action, Component, initialFrame:event?.from ?? action.from,
    viewWindow:event ? {from:event.from,to:event.to} : {from:action.from,to:action.to},
    composition:{width:720,height:1280,fps:30,durationInFrames:720}};
}

// Action IDs select a source composition, never a data-* annotation. A fixed
// recipe remains atomic: removing/reordering internal actions is unsupported.
export function resolveReplay(replay: Replay) {
  if (!replay || !Object.hasOwn(bindings, replay.templateId) || replay.version !== '1.1.0') {
    throw new Error('未适配的模板或精确版本');
  }
  const id = replay.templateId as keyof typeof bindings;
  const expected = bindings[id].actionIds;
  if (!Array.isArray(replay.actionIds) || replay.actionIds.length !== expected.length ||
      expected.some((action, i) => replay.actionIds[i] !== action)) {
    throw new Error('固定编排仅接受原动作全集及原顺序');
  }
  const selected = replay.actionIds.map(actionId=>locateAction(actionId));
  const first = selected[0];
  if (selected.some((a,i)=>a.templateId!==replay.templateId || a.version!==replay.version ||
      a.ordinal!==i || a.Component!==first.Component)) throw new Error('动作跨编排或顺序不一致');
  return first.Component;
}

export function ReplayNumbered({episode, replay}: {episode: any; replay: Replay}) {
  const Component = resolveReplay(replay);
  if (!episode || episode.durationInFrames !== 720 || episode.fps !== 30) {
    throw new Error('仅支持原720帧/30fps历史参考输入');
  }
  // Forward the same episode object; no nested frame clock, scaling or motion.
  return <Component episode={episode}/>;
}
