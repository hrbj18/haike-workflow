// Native BT.709 binding; canonical drawing and renderer remain frozen.
// This renderer is called only by the admitted production queue handler.
const fs=require('fs'),path=require('path'),{createRequire}=require('module');
const shared=createRequire(path.resolve(__dirname,'../../remotion-composer/package.json'));
const {bundle}=shared('@remotion/bundler');
const {selectComposition,openBrowser,renderStill,renderMedia}=shared('@remotion/renderer');
const [phase,data,output,browserExecutable,frameList='0']=process.argv.slice(2);
async function main(){
 const serveUrl=path.join(data,'bundle');
 if(phase==='bundle'){
  await bundle({entryPoint:path.join(__dirname,'index.tsx'),outDir:serveUrl,publicDir:path.join(data,'public'),enableCaching:false,webpackOverride:require('./webpack.cjs')});return;
 }
 if(!['frames','render'].includes(phase))throw Error('Unknown admitted render phase');
 const browser=await openBrowser('chrome',{browserExecutable,chromiumOptions:{gl:'angle'}});
 try{
  const composition=await selectComposition({serveUrl,id:'FieldNotesVideo',browserExecutable,puppeteerInstance:browser});
  const common={serveUrl,composition,browserExecutable,puppeteerInstance:browser,chromiumOptions:{gl:'angle'},timeoutInMilliseconds:120000,offthreadVideoThreads:1,offthreadVideoCacheSizeInBytes:128*1024*1024,mediaCacheSizeInBytes:64*1024*1024};
  if(phase==='frames'){
   fs.mkdirSync(output,{recursive:true});
   for(const frame of frameList.split(',').map(Number)){
    await renderStill({...common,frame,output:path.join(output,String(frame).padStart(5,'0')+'.png'),imageFormat:'png'});
    console.log('Actual frame '+frame);
   }
  }else{
   let last=-1;
   await renderMedia({colorSpace:'bt709',...common,outputLocation:output,codec:'h264',videoBitrate:'22M',x264Preset:'fast',pixelFormat:'yuv420p',imageFormat:'jpeg',jpegQuality:100,muted:true,concurrency:1,
    ffmpegOverride:({args})=>{const changed=[...args];changed.splice(changed.length-1,0,'-minrate','22M','-maxrate','22M','-bufsize','44M','-x264-params','nal-hrd=cbr:force-cfr=1');return changed;},
    onProgress:({progress})=>{const now=Math.floor(progress*20);if(now!==last){last=now;console.log('Rendered '+now*5+'%')}}});
  }
 }finally{await browser.close({silent:true})}
}
main().catch(e=>{console.error(e);process.exitCode=1});
