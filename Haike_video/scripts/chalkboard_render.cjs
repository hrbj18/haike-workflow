// The unified queue invokes this renderer with frozen props and owned assets.
const fs=require('node:fs'),path=require('node:path'),{createRequire}=require('node:module');
const root=path.resolve(__dirname,'..'),req=createRequire(path.join(root,'remotion-composer/package.json'));
const {bundle}=req('@remotion/bundler');
const {openBrowser,selectComposition,renderStill,renderMedia}=req('@remotion/renderer');
const encodingArgs=({type,args})=>type==='stitcher'?args:[...args.slice(0,-1),
 '-minrate','21M','-maxrate','21M','-bufsize','42M','-x264-params','nal-hrd=cbr:force-cfr=1:filler=1',
 '-vf','scale=in_range=pc:out_range=tv,format=yuv420p','-color_range','tv',
 '-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709',args.at(-1)];
module.exports={encodingArgs};
if(require.main===module)(async()=>{
 const [mode,propsFile,publicDir,output,frameJSON,rangeJSON]=process.argv.slice(2);
 if(!['preview','render'].includes(mode))throw Error('请选择预览或整片渲染');
 const inputProps=JSON.parse(fs.readFileSync(propsFile,'utf8'));
 const serveUrl=await bundle({entryPoint:path.join(root,'templates/chalkboard-explainer-v1/index.tsx'),publicDir,
  webpackOverride:c=>({...c,resolve:{...c.resolve,modules:[path.join(root,'remotion-composer/node_modules'),...(c.resolve.modules||[])]}})});
 const browserExecutable=process.env.REMOTION_BROWSER_EXECUTABLE||process.env.CHROME_PATH;
 const browser=await openBrowser('chrome',{browserExecutable,chromiumOptions:{gl:'angle'}});
 try{
  const composition=await selectComposition({serveUrl,id:'Chalkboard',inputProps,puppeteerInstance:browser});
  if(mode==='preview'){
   fs.mkdirSync(output,{recursive:true});
   const frames=JSON.parse(frameJSON);
   if(!Array.isArray(frames)||!frames.length||frames.length>128||frames.some(f=>!Number.isInteger(f)||f<0||f>=composition.durationInFrames))throw Error('预览帧越界');
   for(const frame of frames)await renderStill({serveUrl,composition,inputProps,frame,imageFormat:'png',scale:.6,output:path.join(output,frame+'.png'),puppeteerInstance:browser});
  }else{
   const frameRange=rangeJSON?JSON.parse(rangeJSON):null;
   if(frameRange&&(!Array.isArray(frameRange)||frameRange.length!==2||frameRange.some(f=>!Number.isInteger(f))||frameRange[0]<0||frameRange[1]<frameRange[0]||frameRange[1]>=composition.durationInFrames))throw Error('字幕修订帧范围无效');
   let previous=-1;
   await renderMedia({serveUrl,composition,inputProps,codec:'h264',pixelFormat:'yuv420p',
    frameRange,muted:Boolean(frameRange),
    videoBitrate:'21M',audioBitrate:'192k',x264Preset:'fast',imageFormat:'jpeg',jpegQuality:98,
    outputLocation:output,concurrency:4,puppeteerInstance:browser,
    ffmpegOverride:encodingArgs,
    onProgress:p=>{const n=Math.floor(p.progress*10);if(n!==previous){previous=n;process.stdout.write(JSON.stringify({progress:n*10})+'\n')}}});
  }
 }finally{await browser.close({silent:true})}
})().catch(e=>{process.stderr.write(String(e.stack||e));process.exit(1)});
