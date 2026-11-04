// Private local preview. Upstream TalkCraft code stays in the private installation/bundle.
const fs=require('fs'),path=require('path'),crypto=require('crypto'),{createRequire}=require('module');
const root=path.resolve(__dirname,'../../..'),shared=createRequire(path.join(root,'Haike_video/remotion-composer/package.json'));
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const snap=path.join(root,'Haike_video/motion-components/snapcn'),localSource=require(path.join(snap,'compat/local-source.cjs')),familyFor=require(path.join(snap,'compat/local-font.cjs')).familyFor;
const out=path.resolve(process.argv[2]||path.join(root,'.local/field-notes-v2-preview'));
const prepared=path.resolve(process.argv[3]||path.join(root,'.local/custom-template-field-notes'));
const plan=JSON.parse(fs.readFileSync(path.join(__dirname,'selection.json'),'utf8'));
const upstream=JSON.parse(fs.readFileSync(path.join(root,'.local/talkcraft-integration/state/config.json'),'utf8')).upstream;
const nativeFile=path.join(upstream,'template/cards/grid-to-hero.tsx');
const plugin={name:'local-motion-review',setup(b){
 b.onResolve({filter:/^talkcraft-private:grid-to-hero$/},()=>({path:nativeFile,namespace:'talkcraft-adapter'}));
 b.onLoad({filter:/.*/,namespace:'talkcraft-adapter'},a=>({contents:fs.readFileSync(a.path,'utf8').replace('* { margin: 0; padding: 0; box-sizing: border-box; }','.native-grid * { margin: 0; padding: 0; box-sizing: border-box; }').replace('background: "#ffffff"','background: "#F4F1E9"'),loader:'tsx',resolveDir:path.dirname(a.path)}));
 b.onResolve({filter:/^(react(?:-dom)?|remotion|@remotion\/player)(\/.*)?$/},a=>({path:shared.resolve(a.path)}));
 b.onResolve({filter:/^@remotion\/google-fonts\//},a=>({path:a.path.split('/').pop(),namespace:'local-font'}));
 b.onLoad({filter:/.*/,namespace:'local-font'},a=>({contents:`export function loadFont(){return {fontFamily:${JSON.stringify(familyFor(a.path))},waitUntilDone:()=>Promise.resolve()}}`,loader:'js'}));
 b.onLoad({filter:/upstream[\\/]registry[\\/].*\.tsx?$/},a=>({contents:localSource(fs.readFileSync(a.path,'utf8')),loader:a.path.endsWith('.tsx')?'tsx':'ts'}));
 b.onResolve({filter:/^@\//},a=>{
  if(a.path==='@/lib/snap-cn-ui')return {path:path.join(snap,'upstream/registry/snap-cn-ui/core/index.ts')};
  if(a.path.startsWith('@/lib/'))return {path:path.join(snap,'upstream',a.path.slice(2)+'.ts')};
  const m=a.path.match(/^@\/(?:components\/snap-cn|registry\/snap-cn-ui)\/([^/]+)$/);
  if(m)return {path:path.join(snap,'upstream/registry',['caret','input'].includes(m[1])?'snap-cn-ui':'snap-cn',m[1],'index.tsx')};
 });
}};
async function main(){
 if(fs.existsSync(path.join(__dirname,'release.json')))require('./verify-release.cjs').verify();
 require('child_process').execFileSync(path.join(root,'Haike_video/.venv/Scripts/python.exe'),[path.join(root,'Haike_video/scripts/motion_catalogue.py'),'check','--plan',path.join(__dirname,'selection.json')],{stdio:'pipe'});
 const original=require('../chromatic-motion-lab-v1/custom-recipes/verify-release.cjs').verify();
 if(out===prepared||!out.startsWith(path.join(root,'.local')+path.sep))throw Error('Candidate output must be a separate private .local directory');
 const prep=JSON.parse(fs.readFileSync(path.join(prepared,'preparation.json'),'utf8'));
 for(const item of prep.files){const source=path.resolve(prepared,item.path);if(!source.startsWith(prepared+path.sep)||hash(source)!==item.sha256)throw Error('Prepared source changed: '+item.path)}
 const catalogue=JSON.parse(fs.readFileSync(path.join(root,'Haike_video/motion-components/catalogue.json'),'utf8'));
 for(const s of plan.scenes)for(const choice of s.selections){
  const entry=catalogue.entries.find(e=>e.id===choice.id),file=path.join(upstream,entry.source.replace('talkcraft://',''));
  if(hash(file)!==choice.source_sha256||hash(file)!==entry.source_sha256)throw Error('TalkCraft source revision changed: '+choice.id);
 }
 const baseline=JSON.parse(fs.readFileSync(path.join(prepared,'episode.json'),'utf8'));
 if(baseline.durationInFrames!==720||baseline.mode!=='visual-preview'||baseline.previewQuality!=='low'||baseline.presenterClips?.length!==1||baseline.presenterClips[0].from!==0||baseline.presenterClips[0].to!==720)throw Error('Expected original continuous24s low silent input');
 const candidate={...baseline,segments:plan.scenes.map((s,i)=>({...baseline.segments[i],from:s.from,to:s.to,chapterFrom:s.from,chapterTo:s.to})),captions:plan.scenes.map((s,i)=>({...baseline.captions[i],from:s.from,to:s.to})),motionScheduleRevision:plan.revision};
 fs.mkdirSync(out,{recursive:true});fs.cpSync(path.join(prepared,'assets'),path.join(out,'assets'),{recursive:true});
 fs.writeFileSync(path.join(out,'baseline.json'),JSON.stringify(baseline,null,2));fs.writeFileSync(path.join(out,'episode.json'),JSON.stringify(candidate,null,2));
 const result=await shared('esbuild').build({entryPoints:[path.join(__dirname,'Preview.tsx')],outfile:path.join(out,'gallery.js'),bundle:true,platform:'browser',format:'iife',jsx:'automatic',plugins:[plugin],nodePaths:[path.join(snap,'node_modules'),path.join(root,'Haike_video/remotion-composer/node_modules')],define:{'process.env.NODE_ENV':'"production"'},minify:true,metafile:true,logLevel:'warning'});
 for(const f of ['index.html','gallery.css'])fs.copyFileSync(path.join(__dirname,f),path.join(out,f));
 const inputs=Object.keys(result.metafile.inputs).map(file=>file.startsWith('local-font:')?{path:file,virtual:true}:{path:file.startsWith('talkcraft-adapter:')?file.slice('talkcraft-adapter:'.length):path.resolve(file)}).map(item=>item.virtual?item:{...item,sha256:hash(item.path)});
 const sources=['Scene.tsx','Preview.tsx','selection.json','build.cjs','verify.py','index.html','gallery.css','../../scripts/motion_catalogue.py','../../motion-components/catalogue.json'].map(f=>({path:path.resolve(__dirname,f),sha256:hash(path.join(__dirname,f))}));
 const dependencies=Object.fromEntries(['react','react-dom','remotion','@remotion/player','gsap','esbuild'].map(n=>[n,JSON.parse(fs.readFileSync(shared.resolve(n+'/package.json'),'utf8')).version]));
 const assets=prep.files.filter(x=>x.path.startsWith('assets/')).map(x=>({path:x.path,sha256:hash(path.join(out,x.path))}));
 const outputs=['index.html','gallery.css','gallery.js','episode.json','baseline.json'].map(f=>({path:f,sha256:hash(path.join(out,f))}));
 fs.writeFileSync(path.join(out,'build-manifest.json'),JSON.stringify({schema:'haike.motion-candidate/1',templateId:plan.templateId,version:plan.version,original,scope:'formal template5; approved local24s low silent style; new inputs/production require separate validation',sources,inputs,dependencies,assets,outputs,preparedManifestSha256:hash(path.join(prepared,'preparation.json')),nativeAdapter:'scope CSS reset; paper background; .65 uniform scale; empty small labels; freeze frame202 after grid return; host React/Remotion',node:process.version},null,2));
 console.log(JSON.stringify({output:out,nativeCardImported:inputs.some(i=>i.path===nativeFile),original,dependencies}));
}
main().catch(e=>{console.error(e);process.exitCode=1});
