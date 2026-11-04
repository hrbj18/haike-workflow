/* Exercises actual source-derived functions and real-media clock separation. */
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const {createRequire}=require('module');
const root=path.resolve(__dirname,'../../..'),shared=createRequire(path.join(root,'Haike_video/remotion-composer/package.json'));
const out=path.join(root,'.local/motion-full-delivery-20261104/B');
const plugin={name:'controlled-remotion',setup(b){
 b.onResolve({filter:/^remotion$/},()=>({path:'remotion',namespace:'qa'}));
 b.onLoad({filter:/.*/,namespace:'qa'},()=>({loader:'js',contents:`import React from 'react';export const useCurrentFrame=()=>globalThis.realFrame;
 export const staticFile=x=>x;export const AbsoluteFill=({children,...p})=>React.createElement('div',p,children);
 export const Sequence=({children,from=0,durationInFrames=Infinity})=>globalThis.realFrame>=from&&globalThis.realFrame<from+durationInFrames?React.createElement(React.Fragment,null,children):null;
 export const OffthreadVideo=({startFrom,endAt,playbackRate,src,...p})=>React.createElement('video',{'data-start':startFrom,'data-end':endAt,'data-rate':playbackRate,src,...p});
 export const Video=OffthreadVideo;export const Composition=()=>null;export const registerRoot=()=>{};export const delayRender=()=>1;export const continueRender=()=>{};export const cancelRender=()=>{};`}));
 b.onResolve({filter:/^(react(?:-dom)?)(\/.*)?$/},a=>({path:a.path,external:true}));
}};
(async()=>{
 const outfile=path.join(out,'dispatch.cjs');
 await shared('esbuild').build({stdin:{contents:`export {ACTIONS} from './Scene';export {Context,Media,motionAt} from './Runtime';`,resolveDir:__dirname,loader:'tsx'},outfile,bundle:true,format:'cjs',platform:'node',plugins:[plugin],nodePaths:[path.join(root,'Haike_video/remotion-composer/node_modules')],logLevel:'warning',external:['react','react-dom','react-dom/server']});
 // External React must be the same instance in the renderer and the bundle.
 const Module=require('module'),original=Module._resolveFilename;
 const resolutions=Object.fromEntries(['react','react/jsx-runtime','react-dom','react-dom/server'].map(n=>[n,shared.resolve(n)]));
 Module._resolveFilename=function(n,...args){return resolutions[n]||original.call(this,n,...args)};
 const React=shared('react'),render=shared('react-dom/server').renderToStaticMarkup;
 const {ACTIONS,Context,Media,motionAt}=require(outfile);let checks=0;
 const index=JSON.parse(fs.readFileSync(path.join(out,'INPUT_INDEX.json')));
 const evidence=[];
 for(const row of index){const p=JSON.parse(fs.readFileSync(row.input)).props;
  for(const s of p.scenes){
   const frames=[s.from,...s.knots.slice(1,-1).map(k=>k.target),s.to-1];let samples=[];
   for(const f of frames){globalThis.realFrame=f;const motion=motionAt(s.knots,f);
    const element=ACTIONS[s.actionId]({p,scene:s,motion});
    const html=render(React.createElement(Context.Provider,{value:{p,s,globalFrame:f,motionFrame:motion}},element));
    assert(html.includes('video')||motion===s.sourceFrom);checks++;
    assert(!html.includes('NaN'));checks++;
    samples.push({frame:f,motion,markup_sha256:require('crypto').createHash('sha256').update(html).digest('hex')});
   }
   assert(new Set(samples.map(x=>x.markup_sha256)).size>1);checks++;
   globalThis.realFrame=s.from+1;
   const slot=Object.keys(p.slots[s.id])[0];
   const media=m=>render(React.createElement(Context.Provider,{value:{p,s,globalFrame:globalThis.realFrame,motionFrame:m}},React.createElement(Media,{id:slot})));
   assert.equal(media(0),media(9999));checks++;
   assert(media(0).includes('data-rate="1"'));checks++;
   evidence.push({action:s.actionId,frames:samples});
  }
 }
 assert.equal(Object.keys(ACTIONS).length,20);checks++;
 const sourceMap=JSON.parse(fs.readFileSync(path.join(__dirname,'SOURCE_MAP.json')));
 for(const r of sourceMap)for(const prefix of ['source','derived']){assert.equal(require('crypto').createHash('sha256').update(fs.readFileSync(path.join(root,r[prefix]))).digest('hex'),r[prefix+'_sha256']);checks++;}
 const result={pass:true,checks,actual_actions:20,scope:'actual derived functions at every independent semantic knot; real media sample invariant under motion coordinate; original/derived hashes',evidence};
 fs.writeFileSync(path.join(out,'STRUCTURAL_JS_QA.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({pass:true,checks,actual_actions:20}));
})().catch(e=>{console.error(e);process.exitCode=1});
