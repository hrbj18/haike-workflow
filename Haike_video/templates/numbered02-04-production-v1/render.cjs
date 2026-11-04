const fs=require('fs'),path=require('path'),{createRequire}=require('module');
const shared=createRequire(path.resolve(__dirname,'../../remotion-composer/package.json'));
const {bundle}=shared('@remotion/bundler'),{openBrowser,selectComposition,renderStill,renderMedia}=shared('@remotion/renderer');
const [phase,data,output,browserExecutable,frameList='0']=process.argv.slice(2);
async function main(){
 const serveUrl=path.join(data,'bundle');
 if(phase==='bundle'){await bundle({entryPoint:path.join(__dirname,'index.tsx'),outDir:serveUrl,publicDir:path.join(data,'public'),enableCaching:false,webpackOverride:require('./webpack.cjs')});return}
 if(!['frames','render'].includes(phase))throw Error('Unsupported queued phase');
 const browser=await openBrowser('chrome',{browserExecutable,chromiumOptions:{gl:'angle'}});
 try{const composition=await selectComposition({serveUrl,id:'FullNumberedMotion',browserExecutable,puppeteerInstance:browser});
 const common={serveUrl,composition,browserExecutable,puppeteerInstance:browser,timeoutInMilliseconds:120000,chromiumOptions:{gl:'angle'},offthreadVideoThreads:4,offthreadVideoCacheSizeInBytes:512*1024*1024,mediaCacheSizeInBytes:128*1024*1024};
 if(phase==='frames'){fs.mkdirSync(output,{recursive:true});for(const frame of frameList.split(',').map(Number)){await renderStill({...common,frame,output:path.join(output,String(frame).padStart(5,'0')+'.png'),imageFormat:'png'});console.log('Actual frame '+frame)}}
 else{let last=-1;await renderMedia({...common,outputLocation:output,codec:'h264',videoBitrate:'22M',x264Preset:'fast',pixelFormat:'yuv420p',imageFormat:'jpeg',jpegQuality:100,concurrency:2,muted:true,
 ffmpegOverride:({args})=>{const out=[...args];out.splice(out.length-1,0,'-minrate','22M','-maxrate','22M','-bufsize','44M','-x264-params','nal-hrd=cbr:force-cfr=1');return out},onProgress:({progress})=>{const n=Math.floor(progress*20);if(n!==last){last=n;console.log('Rendered '+n*5+'%')}}})}
 }finally{await browser.close({silent:true})}
}main().catch(e=>{console.error(e);process.exitCode=1});
