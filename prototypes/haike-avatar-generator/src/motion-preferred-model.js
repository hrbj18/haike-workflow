export function motionSelection(card){
  const p=card.preferred_production;
  return {gallery_id:card.id,template_id:p.template_id,version:p.version,production_contract:p.production_contract};
}
export function productionInstruction(card,draftId=''){
  const p=card.preferred_production;
  const envelope=p.prepare_endpoint==='/api/studio/motion-replay/prepare'?`{template_id:"${p.template_id}",version:"${p.version}",request:本期输入}`:'{request:本期输入}';
  return `使用“${card.name}”，精确生产身份 ${p.template_id}@${p.version}。先读 START_HERE.md、Haike_video/AGENT_GUIDE.md、Haike_video/docs/MOTION_REPLAY_STANDARD.md。${draftId?`当前草稿 ${draftId}；读取原草稿与已上传音轨、人物、素材和参数，保持选择。`:''}沿固定合同 ${p.production_contract}，通过 ${p.prepare_endpoint} 传入 ${envelope} 做只读准备。保留已有完整声音、真实ASR、同声源人物和素材，不重复购买；缺输入明确指出，不换到受保护原包、试验桥或静态历史。所需输入：${p.required_inputs.map(x=>`${x.label}(${x.path})`).join('、')}。准备结果交给其中固定consumer或queue_admission，沿统一主队列冻结并执行原生产门禁。不要从装饰差异发起新版本或反复重渲；连续听看未完成如实说明。`;
}
