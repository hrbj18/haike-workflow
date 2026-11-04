// Local browser preview only. No render, provider, publishing or queue actions.
const fs=require('fs'),path=require('path'),{createRequire}=require('module');
const root=__dirname,composer=path.resolve(root,'../../remotion-composer'),snap=path.resolve(root,'../../motion-components/snapcn');
const shared=createRequire(path.join(composer,'package.json')),esbuild=shared('esbuild');
const out=path.resolve(process.argv[2]||path.join(root,'../../../.local/chromatic-motion-lab-v1'));
const custom=process.argv[3]==='--custom';
const localSource=require(path.join(snap,'compat/local-source.cjs')),familyFor=require(path.join(snap,'compat/local-font.cjs')).familyFor;
const plugin={name:'haike-local-components',setup(build){
 build.onResolve({filter:/^@remotion\/google-fonts\//},args=>({path:args.path.split('/').pop(),namespace:'local-font'}));
 build.onLoad({filter:/.*/,namespace:'local-font'},args=>({contents:`export function loadFont(){return {fontFamily:${JSON.stringify(familyFor(args.path))},waitUntilDone:()=>Promise.resolve()}}`,loader:'js'}));
 build.onLoad({filter:/upstream[\\/]registry[\\/].*\.tsx?$/},args=>({contents:localSource(fs.readFileSync(args.path,'utf8')),loader:args.path.endsWith('.tsx')?'tsx':'ts'}));
 build.onResolve({filter:/^react(?:-dom)?(?:\/.*)?$/},args=>({path:shared.resolve(args.path)}));
 build.onResolve({filter:/^@\//},args=>{
  if(args.path==='@/lib/snap-cn-ui')return {path:path.join(snap,'upstream/registry/snap-cn-ui/core/index.ts')};
  if(args.path.startsWith('@/lib/'))return {path:path.join(snap,'upstream',args.path.slice(2)+'.ts')};
  const m=args.path.match(/^@\/(?:components\/snap-cn|registry\/snap-cn-ui)\/([^/]+)$/);
  if(m)return {path:path.join(snap,'upstream/registry',['caret','input'].includes(m[1])?'snap-cn-ui':'snap-cn',m[1],'index.tsx')};
 });
}};
(async()=>{
 const crypto=require('crypto'),hash=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
 if(custom)require('./custom-recipes/verify-release.cjs').verify();
 const preparation=JSON.parse(fs.readFileSync(path.join(out,'preparation.json'),'utf8'));
 if(preparation.schema!=='haike.chromatic-preparation/1'||preparation.recipeSha256!==hash(path.join(root,'recipes.json')))throw Error('Recipe changed: run prepare.py again');
 for(const f of preparation.files){const file=path.resolve(out,f.path);if(!file.startsWith(out+path.sep)||hash(file)!==f.sha256)throw Error('Prepared input changed: '+f.path)}
 if(custom){
  const recipe=JSON.parse(fs.readFileSync(path.join(root,'custom-recipes/field-notes.json'),'utf8'));
  const episode=JSON.parse(fs.readFileSync(path.join(out,'episode.json'),'utf8'));
  const pairs={hero:'parallax',duet:'paired-reveal',cards:'reflow',summary:'highlight'};
  if(episode.mode!=='visual-preview'||episode.durationInFrames!==720||episode.segments?.length!==recipe.stages.length)throw Error('Custom preview requires four chapters covering24 seconds');
  recipe.stages.forEach((stage,i)=>{
   const segment=episode.segments[i],timing=recipe.timing;
   if(stage.effect!==pairs[stage.layout]||stage.photoOrder.some(n=>!Number.isInteger(n)||n<0||n>=episode.photos.length))throw Error('Unsupported custom effect or missing photo');
   if(segment.to-segment.from-timing.noteFrom-timing.noteFrames<timing.minHoldFrames||timing.mediaFrom<timing.titleFrames||timing.noteFrom<timing.mediaFrom+timing.actionFrames)throw Error('Custom motion/read timing overlaps or is too short');
  });
 }
 const sampleFiles=new Map();
 const catalogue=path.join(out,'examples.json');
 if(fs.existsSync(catalogue)){
  sampleFiles.set('examples.json',hash(catalogue));
  const examples=JSON.parse(fs.readFileSync(catalogue,'utf8'));
  if(!Array.isArray(examples))throw Error('Invalid sample catalogue');
  for(const example of examples){
   if(!/^(episode\.json|episodes\/[a-z0-9-]+\/episode\.json)$/.test(example.path)||typeof example.label!=='string')throw Error('Invalid prepared sample path');
   const directory=path.dirname(path.resolve(out,example.path)),prepPath=path.join(directory,'preparation.json');
   const sample=JSON.parse(fs.readFileSync(prepPath,'utf8'));
   if(sample.schema!=='haike.chromatic-preparation/1'||sample.recipeSha256!==preparation.recipeSha256)throw Error('Sample recipe changed: '+example.path);
   sampleFiles.set(path.relative(out,prepPath).split(path.sep).join('/'),hash(prepPath));
   for(const record of sample.files){const file=path.resolve(directory,record.path);if(!file.startsWith(directory+path.sep)||hash(file)!==record.sha256)throw Error('Prepared sample changed: '+example.path);sampleFiles.set(path.relative(out,file).split(path.sep).join('/'),record.sha256)}
  }
 }
 const result=await esbuild.build({entryPoints:[path.join(root,custom?'CustomPreview.tsx':'Gallery.tsx')],outfile:path.join(out,'gallery.js'),bundle:true,platform:'browser',format:'iife',jsx:'automatic',plugins:[plugin],nodePaths:[path.join(snap,'node_modules'),path.join(composer,'node_modules')],define:{'process.env.NODE_ENV':'"production"'},minify:true,metafile:true,logLevel:'warning'});
 for(const file of ['index.html','gallery.css'])fs.copyFileSync(path.join(root,custom?(file==='index.html'?'custom.html':'custom.css'):file),path.join(out,file));
 const inputs=Object.keys(result.metafile.inputs).map(file=>file.startsWith('local-font:')?{path:file,virtual:true,fontFamily:familyFor(file.slice(11))}:{path:file,sha256:hash(path.resolve(file))});
 const dependencies=Object.fromEntries(['react','react-dom','remotion','@remotion/player','gsap','esbuild'].map(name=>[name,JSON.parse(fs.readFileSync(shared.resolve(name+'/package.json'),'utf8')).version]));
 const context={workingDirectory:process.cwd(),toolSources:['verify.py','timeline.py','story_plan.py','prepare_v2.py','index.tsx','remotion.config.cjs','webpack.cjs','../warm-workbench-v1/webpack.cjs','../../motion-components/snapcn/compat/local-source.cjs','../../motion-components/snapcn/compat/local-font.cjs',...(custom?['custom.html','custom.css','custom-recipes/release.json','custom-recipes/verify-release.cjs']:['index.html','gallery.css'])].map(file=>({path:file,sha256:hash(path.join(root,file))}))};
 fs.writeFileSync(path.join(out,'build-manifest.json'),JSON.stringify({schema:'haike.chromatic-preview/2',source:root,workingDirectory:context.workingDirectory,recipeRevision:JSON.parse(fs.readFileSync(path.join(root,'recipes.json'),'utf8')).revision,toolSources:[...context.toolSources,...['prepare.py','build.cjs','serve.py'].map(file=>({path:file,sha256:hash(path.join(root,file))}))],preparationSha256:hash(path.join(out,'preparation.json')),assets:preparation.files,sampleFiles:[...sampleFiles].map(([path,sha256])=>({path,sha256})),dependencies,node:process.version,inputs,outputs:['gallery.js','gallery.css','index.html'].map(file=>({path:file,sha256:hash(path.join(out,file))})),output:out},null,2));
 console.log(JSON.stringify({output:out,components:Object.keys(result.metafile.inputs).filter(x=>x.includes('snap-cn/')||x.includes('remocn/')||x.endsWith('dynamic/motion.ts'))}));
})().catch(e=>{console.error(e);process.exitCode=1});
