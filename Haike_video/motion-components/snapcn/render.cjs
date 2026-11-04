// Fixed local preview producer; invoked by the registered project queue adapter.
const fs=require('fs');const path=require('path');const {createRequire}=require('module');
const root=__dirname;const composer=path.resolve(root,'../../remotion-composer');const shared=createRequire(path.join(composer,'package.json'));
const {bundle}=shared('@remotion/bundler');const {getCompositions,openBrowser,renderStill}=shared('@remotion/renderer');const webpack=shared('webpack');
const [action,data,output,browserExecutable,selectedIds]=process.argv.slice(2);
const reg=JSON.parse(fs.readFileSync(path.join(root,'upstream/registry/snap-cn/registry.json')));
const alias={react:shared.resolve('react'),'react-dom':shared.resolve('react-dom'),remotion:shared.resolve('remotion'),'@/lib/snap-cn-ui':path.join(root,'upstream/registry/snap-cn-ui/core/index.ts'),'@/lib/customizer-config':path.join(root,'upstream/lib/customizer-config.ts'),'@/lib/utils':path.join(root,'upstream/lib/utils.ts')};
for(const name of [...reg.items.map(i=>i.name),'caret','input']){const tier=['caret','input'].includes(name)?'snap-cn-ui':'snap-cn';for(const prefix of ['@/components/snap-cn/','@/registry/snap-cn-ui/'])alias[prefix+name+'$']=path.join(root,'upstream/registry',tier,name,'index.tsx');}
async function main(){
 const serveUrl=data+'-render-bundle';
 if(action==='bundle'){
  await bundle({entryPoint:path.join(root,'Compositions.tsx'),outDir:serveUrl,publicDir:data,enableCaching:false,webpackOverride:c=>{c.resolve.modules=[path.join(root,'node_modules'),path.join(composer,'node_modules'),'node_modules'];c.resolve.alias={...c.resolve.alias,...alias};c.plugins.push(new webpack.NormalModuleReplacementPlugin(/^@remotion\/google-fonts\//,path.join(root,'compat/font-loader.ts')));c.module.rules.unshift({test:/upstream[\\/]registry[\\/].*\.tsx?$/,enforce:'pre',use:[path.join(root,'compat/local-source-loader.cjs')]});return c;}});
  console.log('Render bundle ready');return;
 }
 if(action!=='stills')throw Error('Unsupported action');
 fs.mkdirSync(output,{recursive:true});
 const browser=await openBrowser('chrome',{browserExecutable,chromiumOptions:{gl:'angle'}});
 const results=[];
 try{
  const allCompositions=await getCompositions(serveUrl,{browserExecutable,puppeteerInstance:browser});
  const wanted=selectedIds?selectedIds.split(','):reg.items.map(i=>i.name);
  if(wanted.some(id=>!reg.items.some(i=>i.name===id)))throw Error('Unknown selected component');
  const compositions=allCompositions.filter(c=>wanted.includes(c.id));
  for(const composition of compositions){
   const frames=[.22,.55,.83].map(p=>Math.floor((composition.durationInFrames-1)*p));const entry={id:composition.id,frames,images:[],status:'pass'};
   for(const frame of frames){
    const target=path.join(output,`${composition.id}-${frame}.jpg`);
    try{await renderStill({serveUrl,composition,frame,output:target,imageFormat:'jpeg',jpegQuality:94,browserExecutable,puppeteerInstance:browser,chromiumOptions:{gl:'angle'},timeoutInMilliseconds:45000});entry.images.push(target)}
    catch(e){entry.status='fail';entry.error=String(e);break}
   }
   results.push(entry);fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(results,null,2));console.log(composition.id,entry.status,entry.images.length);
  }
 }finally{await browser.close({silent:true})}
 if(results.length!==(selectedIds?selectedIds.split(',').length:reg.items.length)||results.some(r=>r.status!=='pass'))process.exitCode=2;
}
main().catch(e=>{console.error(e);process.exitCode=1});
