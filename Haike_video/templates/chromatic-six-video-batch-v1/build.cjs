const fs=require('fs'),path=require('path'),crypto=require('crypto'),{createRequire}=require('module');
const root=path.resolve(__dirname,'../../..'),out=path.join(root,'.local/chromatic-six-video-batch'),shared=createRequire(path.join(root,'Haike_video/remotion-composer/package.json'));
const hash=f=>crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
async function main(){
 const baseline=require('../chromatic-six-batch-v1/verify-freeze.cjs').verify();
 const binding=JSON.parse(fs.readFileSync(path.join(out,'input-bindings.json'),'utf8'));
 if(binding.templates.length!==6)throw Error('Six delivered video inputs required');
 for(const t of binding.templates)for(const [file,sha] of [[t.source,t.sourceSha256],[t.episode,t.episodeSha256],[t.manifest,t.manifestSha256],[t.handoff,t.handoffSha256]])if(hash(file)!==sha)throw Error('Delivered window identity changed: '+file);
 const assets=JSON.parse(fs.readFileSync(path.join(out,'assets-manifest.json'),'utf8'));
 for(const asset of assets)if(hash(path.join(out,asset.path))!==asset.sha256)throw Error('Video asset identity changed');
 const plugin={name:'shared-runtime',setup(b){b.onResolve({filter:/^(react(?:-dom)?|remotion|@remotion\/player)(\/.*)?$/},a=>({path:shared.resolve(a.path)}))}};
 const result=await shared('esbuild').build({entryPoints:[path.join(__dirname,'Preview.tsx')],outfile:path.join(out,'gallery.js'),bundle:true,platform:'browser',format:'iife',jsx:'automatic',plugins:[plugin],nodePaths:[path.join(root,'Haike_video/remotion-composer/node_modules')],define:{'process.env.NODE_ENV':'"production"'},minify:true,metafile:true,logLevel:'warning'});
 for(const f of ['index.html','gallery.css'])fs.copyFileSync(path.join(__dirname,f),path.join(out,f));
 const inputs=Object.keys(result.metafile.inputs).map(f=>({path:path.resolve(f),sha256:hash(path.resolve(f))}));
 const files=['Preview.tsx','prepare.py','collect.py','build.cjs','catalogue.json','index.html','gallery.css'];
 for(const window of ['a','b','c'])for(const name of fs.readdirSync(path.join(__dirname,'window-'+window)))if(/(?:selection|spec).*\.json$/.test(name))files.push('window-'+window+'/'+name);
 const sources=files.map(f=>({path:path.join(__dirname,f),sha256:hash(path.join(__dirname,f))}));
 const outputs=['gallery.js','gallery.css','index.html','input-bindings.json','assets-manifest.json',...binding.templates.map(t=>t.target)].map(f=>({path:f,sha256:hash(path.join(out,f))}));
 const dependencies=Object.fromEntries(['react','react-dom','remotion','@remotion/player','esbuild'].map(n=>[n,JSON.parse(fs.readFileSync(shared.resolve(n+'/package.json'),'utf8')).version]));
 fs.writeFileSync(path.join(out,'build-manifest.json'),JSON.stringify({schema:'haike.six-real-video-build/1',templateId:'chromatic-six-video-batch-v1',version:'1.1.0-candidate.1',baseline,scope:'six actual window renderers and exact low silent video inputs',sources,inputs,assets,outputs,dependencies},null,2));
 console.log(JSON.stringify({output:out,inputs:inputs.length,assets:assets.length}));
}
main().catch(e=>{console.error(e);process.exitCode=1});
