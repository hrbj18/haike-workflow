// Called only from the fixed production queue contract.
const fs=require('fs'),path=require('path'),{createRequire}=require('module');
const dep=createRequire(path.resolve(__dirname,'../../remotion-composer/package.json'));
const {bundle}=dep('@remotion/bundler'),{openBrowser,selectComposition,renderStill,renderMedia}=dep('@remotion/renderer');
const [phase,data,output,browserExecutable,frames='0']=process.argv.slice(2);
async function main(){
 if(phase==='bundle'){await bundle({entryPoint:path.join(__dirname,'index.tsx'),outDir:path.join(data,'bundle'),publicDir:path.join(data,'public'),enableCaching:false,webpackOverride:config=>{config.resolve.alias={...config.resolve.alias,react:dep.resolve('react'),'react-dom':dep.resolve('react-dom'),remotion:dep.resolve('remotion')};config.resolve.modules=[path.resolve(__dirname,'../../remotion-composer/node_modules'),'node_modules'];return config}});return}
 if(!['preview','render'].includes(phase))throw Error('Unknown public knowledge phase');const browser=await openBrowser('chrome',{browserExecutable});
 try{const composition=await selectComposition({serveUrl:path.join(data,'bundle'),id:'KnowledgeReferencePublic',browserExecutable,puppeteerInstance:browser});const common={serveUrl:path.join(data,'bundle'),composition,browserExecutable,puppeteerInstance:browser,timeoutInMilliseconds:120000};
 if(phase==='preview'){fs.mkdirSync(output,{recursive:true});for(const frame of frames.split(',').map(Number)){await renderStill({...common,frame,output:path.join(output,`${frame}`.padStart(6,'0')+'.png'),imageFormat:'png'});console.log('Actual public frame '+frame)}}
 else{let last=-1;await renderMedia({...common,outputLocation:output,codec:'h264',videoBitrate:'22M',x264Preset:'fast',imageFormat:'jpeg',jpegQuality:100,muted:true,concurrency:2,ffmpegOverride:({args})=>{const a=[...args];a.splice(a.length-1,0,'-minrate','22M','-maxrate','22M','-bufsize','44M','-x264-params','nal-hrd=cbr:force-cfr=1');return a},onProgress:({progress})=>{const n=Math.floor(progress*20);if(last!==n){last=n;console.log('Rendered '+n*5+'%')}}})}
 }finally{await browser.close({silent:true})}
}main().catch(e=>{console.error(e);process.exitCode=1});
