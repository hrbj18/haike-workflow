// A separate local Player bundle. Never calls renderMedia or a production runner.
const fs=require('fs'),path=require('path'),crypto=require('crypto'),{createRequire}=require('module');
const root=path.resolve(__dirname,'../../..'),shared=createRequire(path.join(root,'Haike_video/remotion-composer/package.json'));
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
async function build(preparation,out){
 const doc=JSON.parse(fs.readFileSync(preparation,'utf8'));
 if(doc.status!=='prepared'||!['field-notes-v1','field-notes-v2'].includes(doc.template_id))throw Error('Expected a prepared field-notes contract');
 require('./action-bindings.cjs').resolve(doc.template_id,doc.version,doc.props.actionIds);
 out=path.resolve(out);
 if(!out.startsWith(path.join(root,'.local')+path.sep)||fs.existsSync(out))throw Error('Use a new separate .local preview directory');
 // Reverify the preparation input immediately before consuming it. No rendering.
 const cp=require('child_process'),request=JSON.stringify({data:doc.inputs.data,action_ids:doc.props.actionIds});
 const script="import json,sys;from backlot import motion_replay;r=motion_replay.prepare(sys.argv[1],sys.argv[2],json.loads(sys.argv[3]));print(json.dumps(r,ensure_ascii=False))";
 const fresh=JSON.parse(cp.execFileSync(path.join(root,'Haike_video/.venv/Scripts/python.exe'),['-c',script,doc.template_id,doc.version,request],{cwd:path.join(root,'Haike_video'),encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8'}}));
 if(JSON.stringify(fresh.props)!==JSON.stringify(doc.props))throw Error('Prepared props no longer match their source inputs');
 const snap=path.join(root,'Haike_video/motion-components/snapcn'),localSource=require(path.join(snap,'compat/local-source.cjs')),familyFor=require(path.join(snap,'compat/local-font.cjs')).familyFor;
 let nativeFile;
 const plugin={name:'motion-replay-local',setup(b){
  b.onResolve({filter:/^\.\/FieldNotes$/},a=>({path:path.join(__dirname,doc.template_id==='field-notes-v1'?'FieldNotesV1.tsx':'FieldNotes.tsx')}));
  b.onResolve({filter:/^talkcraft-private:grid-to-hero$/},()=>{
   nativeFile=path.join(JSON.parse(fs.readFileSync(path.join(root,'.local/talkcraft-integration/state/config.json'),'utf8')).upstream,'template/cards/grid-to-hero.tsx');
   return {path:nativeFile,namespace:'talkcraft-adapter'};
  });
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
 fs.mkdirSync(out,{recursive:true});
 fs.cpSync(path.join(doc.inputs.data,'assets'),path.join(out,'assets'),{recursive:true});
 fs.writeFileSync(path.join(out,'motion-replay-props.json'),JSON.stringify(fresh.props));
 const result=await shared('esbuild').build({entryPoints:[path.join(__dirname,'Preview.tsx')],outfile:path.join(out,'motion-replay.js'),bundle:true,platform:'browser',format:'iife',jsx:'automatic',plugins:[plugin],nodePaths:[path.join(snap,'node_modules'),path.join(root,'Haike_video/remotion-composer/node_modules')],define:{'process.env.NODE_ENV':'"production"'},minify:true,metafile:true,logLevel:'warning'});
 fs.writeFileSync(path.join(out,'index.html'),'<!doctype html><meta charset="utf-8"><title>Motion replay · local silent inspection</title><style>html,body{margin:0;background:#ddd}*{box-sizing:border-box}</style><div id="root"></div><script src="/motion-replay.js"></script>');
 const sources=Object.keys(result.metafile.inputs).filter(x=>!x.startsWith('local-font:')).map(x=>{const p=x.replace(/^talkcraft-adapter:/,'');return {path:path.resolve(p),sha256:hash(p)}});
 fs.writeFileSync(path.join(out,'motion-replay-build.json'),JSON.stringify({template_id:doc.template_id,version:doc.version,scope:'local Player only; no queued production or export',preparation_sha256:hash(preparation),sources,outputs:['index.html','motion-replay.js','motion-replay-props.json'].map(p=>({path:p,sha256:hash(path.join(out,p))}))},null,2));
 console.log(JSON.stringify({output:out,template_id:doc.template_id,sourceCount:sources.length,production_submitted:false}));
}
module.exports={build};
if(require.main===module)build(process.argv[2],process.argv[3]).catch(e=>{console.error(e.message);process.exitCode=1});
