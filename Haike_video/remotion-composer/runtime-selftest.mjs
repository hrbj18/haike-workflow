// No network or media generation services. Use only this installation's tools.
import {createRequire} from 'node:module';
import {mkdirSync} from 'node:fs';
import path from 'node:path';

const [root, output] = process.argv.slice(2);
if (!root || !output || !path.isAbsolute(root) || !path.isAbsolute(output)) throw new Error('Expected absolute test paths');
const composer=path.join(root,'Haike_video','remotion-composer');
const require=createRequire(path.join(composer,'package.json'));
const {bundle}=require('@remotion/bundler');
const {selectComposition,renderStill}=require('@remotion/renderer');
const publicDir=path.join(output,'empty-public');mkdirSync(publicDir,{recursive:true});
const serveUrl=await bundle({entryPoint:path.join(composer,'src','RuntimeSelftest.tsx'),
  rootDir:composer,publicDir,outDir:path.join(output,'bundle'),enableCaching:false});
const browserExecutable=path.join(root,'runtime','browser','chrome-headless-shell.exe');
const composition=await selectComposition({serveUrl,id:'HaikeRuntimeCheck',browserExecutable,logLevel:'error'});
for(const frame of [0,1]) await renderStill({serveUrl,composition,frame,browserExecutable,
  imageFormat:'png',output:path.join(output,`frame-${frame}.png`),logLevel:'error'});
process.stdout.write(JSON.stringify({ok:true,scope:'two-pixel-probe-frames',frames:[0,1],node:process.versions.node})+'\n');
