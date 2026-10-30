import test from 'node:test';
import assert from 'node:assert/strict';
import {captionRows,draftBody,selectedGroups,toggleGroup,withGroups} from '../src/dark-full-model.js';

const catalog=['s01','s02','s03','s04','s05','s06','s07','s08','s09','review'].map(id=>({id,title:id}));
test('nine-grid and focus are selected and removed atomically in source order',()=>{
 assert.deepEqual(toggleGroup(['s04'],'s03',catalog),['s02','s03','s04']);
 assert.deepEqual(toggleGroup(['s02','s03','s04'],'s02',catalog),['s04']);
 assert.deepEqual(toggleGroup(['s01','s04','s07'],'s02',catalog),['s01','s02','s03','s04','s07']);
 assert.deepEqual(catalog.reduce((ids,g)=>ids.includes(g.id)?ids:toggleGroup(ids,g.id,catalog),[]),catalog.map(g=>g.id));
});
test('new selection preserves source windows and primary identity without mutating saved recipe',()=>{
 const recipe={props:{fps:30,media:[{id:'a'}],scenes:[{group:'s04',mainMediaId:'a',frames:300,from:0,videoWindows:[{mediaId:'a',from:30,frames:90,offset:4}],content:{title:'已审文案'}}]}};
 const next=withGroups(recipe,['s02','s03','s04'],catalog);
 assert.equal(recipe.props.scenes.length,1);assert.deepEqual(selectedGroups(next),['s02','s03','s04']);
 assert.equal(next.shotPlan[0].mainMediaId,next.shotPlan[1].mainMediaId);
 assert.deepEqual(next.shotPlan[2].clipPlan,[{mediaId:'a',at:.1,seconds:3,offset:4}]);assert.equal(next.shotPlan[2].content.title,'已审文案');
 assert.equal(next.shotPlan[2].frames,undefined);
 const paired=withGroups({props:{media:[{id:'a'},{id:'b'}],scenes:[{group:'s01',mainMediaId:'a'},{group:'s02',mainMediaId:'b',mediaIds:['b']},{group:'s03',mainMediaId:'b',mediaIds:['b']}]}},['s01','s02','s03'],catalog);
 assert.equal(paired.shotPlan[1].mainMediaId,'b');assert.equal(paired.shotPlan[2].mainMediaId,'b');
});
test('actual captions retain milliseconds and persistence excludes public binding metadata',()=>{
 assert.deepEqual(captionRows([{text:'原文',start:.021,end:2.381}]),[{text:'原文',startMs:21,endMs:2381}]);
 assert.deepEqual(Object.keys(draftBody({id:'x',revision:2,title:'t',theme:'child',script:'s',recipe:{},bindings:[{}]})),['id','revision','title','theme','script','recipe']);
});
