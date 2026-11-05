// Native portability harness. Drawing entries stay in their canonical locations.
const fs=require('fs'),path=require('path'),{createRequire}=require('module');
const root=path.resolve(__dirname,'..'),dep=createRequire(path.join(root,'Haike_video/remotion-composer/package.json'));
const {bundle}=dep('@remotion/bundler'),{openBrowser,selectComposition,renderMedia,renderStill}=dep('@remotion/renderer');
const [requestFile]=process.argv.slice(2),r=JSON.parse(fs.readFileSync(requestFile,'utf8'));
(async()=>{
 const serveUrl=await bundle({entryPoint:path.join(root,r.entry),outDir:path.join(r.folder,'bundle'),
  publicDir:r.public,enableCaching:false,webpackOverride:require(path.join(root,'Haike_video/templates/warm-workbench-v1/webpack.cjs'))});
 const browser=await openBrowser('chrome',{browserExecutable:r.browser});
 try{
  const composition=await selectComposition({serveUrl,id:r.composition,inputProps:r.props,browserExecutable:r.browser,puppeteerInstance:browser});
  if(composition.durationInFrames!==r.frames||composition.fps!==r.fps)throw Error('Actual composition does not consume the complete fixture clock');
  fs.writeFileSync(path.join(r.folder,'actual-composition.json'),JSON.stringify({id:composition.id,width:composition.width,height:composition.height,fps:composition.fps,durationInFrames:composition.durationInFrames}));
  if(r.mode==='stills'){
   for(const frame of r.testFrames)await renderStill({serveUrl,composition,inputProps:r.props,frame,output:path.join(r.folder,'check-'+frame+'.png'),browserExecutable:r.browser,puppeteerInstance:browser,imageFormat:'png'});
   return;
  }
  let last=-1;
  await renderMedia({serveUrl,composition,inputProps:r.props,outputLocation:r.output,browserExecutable:r.browser,puppeteerInstance:browser,
   timeoutInMilliseconds:120000,codec:'h264',imageFormat:r.mezzanine?'png':'jpeg',jpegQuality:100,concurrency:2,
   offthreadVideoThreads:2,offthreadVideoCacheSizeInBytes:192*1024*1024,mediaCacheSizeInBytes:64*1024*1024,
   pixelFormat:r.mezzanine?'yuv444p':'yuv420p',colorSpace:'bt709',x264Preset:'fast',muted:true,
   ...(r.mezzanine?{crf:1}:{videoBitrate:'22M',ffmpegOverride:({args})=>{const a=[...args];a.splice(a.length-1,0,'-minrate','22M','-maxrate','22M','-bufsize','44M','-x264-params','nal-hrd=cbr:force-cfr=1');return a}}),
   onProgress:({progress})=>{const n=Math.floor(progress*10);if(n!==last){last=n;console.log(r.templateId+' '+n*10+'%')}}});
 }finally{await browser.close({silent:true})}
})().catch(e=>{console.error(e.stack||String(e));process.exitCode=1});
