const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ROOT=path.resolve(__dirname,'../..');
const ts=require(path.join(ROOT,'remotion-composer/node_modules/typescript'));
const src=fs.readFileSync(path.join(ROOT,'templates/motiongit-dark-full-v1/presenter-clock.ts'),'utf8');
const compiled=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const context={exports:{}};vm.runInNewContext(compiled,context);
const pose=context.exports.presenterPose;
const clip={src:'presenter.mp4',from:120,frames:150,offset:2,modes:[
 {from:120,frames:30,mode:'large'},{from:150,frames:30,mode:'small'},
 {from:180,frames:30,mode:'hidden'},{from:210,frames:60,mode:'large'}]};
assert.equal(pose(clip,120,30).large,1);
assert.equal(pose(clip,179,30).large,0);
assert.equal(pose(clip,195,30).visible,false);
assert.equal(pose(clip,239,30).large,1);
assert.equal(pose(clip,240,30).sourceSeconds,6);
assert.equal(pose(clip,195,30).sourceSeconds,4.5);
assert.equal(pose(clip,239,30).sourceSeconds-pose(clip,209,30).sourceSeconds,1);
assert.equal(pose(clip,270,30).visible,false);
console.log('8 presenter mode/global-clock assertions passed');
