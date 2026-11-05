// Native BT.709 binding; canonical drawing and renderer remain frozen.
// Public independent renderer. No personal package/helper/envelope is loaded.
const path=require('path'),fs=require('fs'),crypto=require('crypto');
const [composer,folder,phase,browserExecutable]=process.argv.slice(2);
const {bundle}=require(path.join(composer,'node_modules/@remotion/bundler'));
const {selectComposition,renderStill,renderMedia}=require(path.join(composer,'node_modules/@remotion/renderer'));
const hash=f=>crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
(async()=>{
 const props=JSON.parse(fs.readFileSync(path.join(folder,'props.json'),'utf8'));
 const build=path.join(composer,'projects','promo-reference-full-'+hash(path.join(folder,'props.json')).slice(0,16));fs.mkdirSync(build,{recursive:true});
 for(const name of ['index.tsx','Board.tsx','types.ts'])fs.copyFileSync(path.join(folder,'template',name),path.join(build,name));
 const serveUrl=await bundle({entryPoint:path.join(build,'index.tsx'),publicDir:path.join(folder,'public'),webpackOverride:c=>c});
 const previewProps={...props,audio:undefined};
 const composition=await selectComposition({serveUrl,id:'PromoReferenceFull',inputProps:phase==='preview'?previewProps:props,browserExecutable});
 if(phase==='preview'){
  const times=new Set();for(const s of props.scenes){for(const t of [s.start+.1,s.start+.7,(s.start+s.end)/2,s.end-.12,...s.cues.map(t=>t+.7)])times.add(Math.min(props.durationFrames-1,Math.max(0,Math.round(t*props.fps))))}
  const detail=props.scenes.find(s=>s.recipe==='detail');for(const t of [detail.start-1.1,detail.start-.3,detail.start+.2,detail.start+.4,detail.start+1.1,detail.end-2.7,detail.end-2,detail.end-1.7])times.add(Math.round(t*props.fps));
  const out=path.join(folder,'preview');fs.mkdirSync(out,{recursive:true});const images=[];
  for(const frame of [...times].sort((a,b)=>a-b)){const name=String(frame).padStart(6,'0')+'.png',output=path.join(out,name);await renderStill({serveUrl,composition,inputProps:previewProps,frame,output,imageFormat:'png',browserExecutable,logLevel:'error'});images.push({name,frame,seconds:frame/props.fps,sha256:hash(output)})}
  fs.writeFileSync(path.join(folder,'preview.json'),JSON.stringify({profile:'haike.promo-reference-full-preview/1',propsSha256:hash(path.join(folder,'props.json')),images,reviewed:false},null,2));
 }else await renderMedia({colorSpace:'bt709',serveUrl,composition,inputProps:props,codec:'h264',outputLocation:path.join(folder,'mezzanine.mp4'),crf:1,pixelFormat:'yuv444p',imageFormat:'png',concurrency:2,browserExecutable,logLevel:'error'});
})().catch(e=>{console.error(String(e.stack||e));process.exitCode=1});


