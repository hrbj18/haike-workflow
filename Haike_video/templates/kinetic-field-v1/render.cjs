const fs=require('fs'),path=require('path'),{createRequire}=require('module');
const req=createRequire(path.resolve(__dirname,'../../remotion-composer/package.json'));
const {bundle}=req('@remotion/bundler');const {getCompositions,openBrowser,renderStill,renderMedia}=req('@remotion/renderer');
const [mode,data,out,exe]=process.argv.slice(2);const plan=require('./layout.json');
const {validateContent}=require('./content-contract.cjs');
async function run(){require('./verify-release.cjs').verify();const episode=JSON.parse(fs.readFileSync(path.join(data,'episode.json'),'utf8'));const inputProps={content:validateContent(episode.content)};const url=path.join(data,'bundle');if(mode==='bundle'){await bundle({entryPoint:path.join(__dirname,'index.tsx'),outDir:url,publicDir:path.join(data,'public'),enableCaching:false,webpackOverride:require('../warm-workbench-v1/webpack.cjs')});return;}
 fs.mkdirSync(out,{recursive:true});const browser=await openBrowser('chrome',{browserExecutable:exe,chromiumOptions:{gl:'angle'}});
 try{const composition=(await getCompositions(url,{browserExecutable:exe,puppeteerInstance:browser,inputProps}))[0];
 const common={serveUrl:url,composition,inputProps,scale:.5,browserExecutable:exe,puppeteerInstance:browser,offthreadVideoThreads:1,offthreadVideoCacheSizeInBytes:24*1024*1024,timeoutInMilliseconds:90000};
 if(mode==='stills'){for(const t of plan.review_seconds){const f=Math.min(383,Math.round(t*24));await renderStill({...common,frame:f,output:path.join(out,`frame-${String(f).padStart(3,'0')}.png`),imageFormat:'png'});}console.log('Actual keyframes completed');}
 else if(mode==='video'){await renderMedia({...common,outputLocation:path.join(out,'kinetic-field.mp4'),codec:'h264',videoBitrate:'850k',audioCodec:'aac',audioBitrate:'128k',imageFormat:'jpeg',jpegQuality:65,x264Preset:'ultrafast',concurrency:1});console.log('16-second test completed');}else throw Error('Unknown phase');
 }finally{await browser.close({silent:true});}}
run().catch(e=>{console.error(e);process.exitCode=1;});
