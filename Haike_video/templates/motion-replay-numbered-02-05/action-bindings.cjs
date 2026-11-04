// Executable binding guard. These are the fixed original stage implementations.
const bindings={
 'field-notes-v1': {version:'1.0.0',source:'../chromatic-motion-lab-v1/RecipeStage.tsx',symbol:'RecipeStage',stages:[
  ['haike.field-notes-v1.arrive',0,180,'Stage(hero)'],
  ['haike.field-notes-v1.compare',180,360,'Stage(duet)'],
  ['haike.field-notes-v1.connect',360,540,'Stage(cards)'],
  ['haike.field-notes-v1.recap',540,720,'Stage(summary)']]},
 'field-notes-v2': {version:'2.0.0',source:'../field-notes-v2/Scene.tsx',symbol:'CandidateScene',stages:[
  ['haike.field-notes-v2.arrive',0,180,'Arrive'],
  ['haike.field-notes-v2.compare',180,420,'Compare'],
  ['haike.field-notes-v2.connect',420,570,'Connect'],
  ['haike.field-notes-v2.converge',570,720,'Converge']]}
};
function resolve(templateId,version,actionIds){
 const binding=bindings[templateId];
 if(!binding||version!==binding.version)throw Error('Unsupported exact motion replay version');
 const expected=binding.stages.map(s=>s[0]);
 if(actionIds!==undefined&&JSON.stringify(actionIds)!==JSON.stringify(expected))throw Error('Frozen actions cannot be replaced, omitted or reordered');
 return binding;
}
function actionFrame(templateId,version,actionId,localFrame){
 const binding=resolve(templateId,version),stage=binding.stages.find(s=>s[0]===actionId);
 if(!stage||!Number.isInteger(localFrame)||localFrame<0||localFrame>=stage[2]-stage[1])throw Error('Action or local frame outside original implementation');
 return stage[1]+localFrame;
}
module.exports={bindings,resolve,actionFrame};
