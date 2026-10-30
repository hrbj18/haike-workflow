export function selectedGroups(recipe){return (recipe?.shotPlan||recipe?.props?.scenes||[]).map(s=>s.group);}
export function toggleGroup(current,id,definitions){
  const next=new Set(current),remove=next.has(id);remove?next.delete(id):next.add(id);
  if(id==='s02'||id==='s03'){const pair=id==='s02'?'s03':'s02';remove?next.delete(pair):next.add(pair);}
  const ordered=definitions.filter(g=>next.has(g.id)).map(g=>g.id);
  return ordered;
}
export function withGroups(recipe,ids,definitions){
  const next=structuredClone(recipe),old=next.shotPlan||next.props?.scenes||[],main=old.find(s=>s.group==='s02')?.mainMediaId||old.find(s=>s.group==='s03')?.mainMediaId||old.find(s=>s.mainMediaId)?.mainMediaId||next.props?.media?.[0]?.id;
  next.props=next.props||{};next.props.scenes=[];
  next.shotPlan=ids.map((group,i)=>{
    const definition=definitions.find(g=>g.id===group),prior=old.find(s=>s.group===group),scene=prior?structuredClone(prior):{group,mediaIds:(next.props.media||[]).map(m=>m.id),mainMediaId:main,content:{}};
    if(scene.videoWindows?.length&&scene.frames)scene.clipPlan=scene.videoWindows.map(w=>({mediaId:w.mediaId,at:w.from/scene.frames,seconds:w.frames/(next.props.fps||30),offset:w.offset}));
    delete scene.from;delete scene.frames;delete scene.videoWindows;
    scene.id=`scene-${i+1}-${group}`;scene.weight=scene.weight||1;scene.title=scene.title||definition?.title||group;
    if(group==='s02'||group==='s03'){scene.mainMediaId=main;if(main&&!scene.mediaIds?.includes(main))scene.mediaIds=[...(scene.mediaIds||[]),main];}
    return scene;
  });
  return next;
}
export function captionRows(parsed){return parsed.map(c=>({text:c.text,startMs:Math.round(c.start*1000),endMs:Math.round(c.end*1000)}));}
export function draftBody(draft,recipe=draft.recipe){return {id:draft.id,revision:draft.revision,title:draft.title,theme:draft.theme,script:draft.script,recipe};}

