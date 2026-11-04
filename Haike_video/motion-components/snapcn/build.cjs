const fs = require('fs');
const path = require('path');
const {createRequire} = require('module');
const root = __dirname;
const composer = path.resolve(root, '../../remotion-composer');
const shared = createRequire(path.join(composer, 'package.json'));
const esbuild = shared('esbuild');
const registry = JSON.parse(fs.readFileSync(path.join(root, 'upstream/registry/snap-cn/registry.json')));
const out = path.resolve(process.argv[3] || path.join(root, '../../../.local/snapcn-gallery'));
const familyFor = require('./compat/local-font.cjs').familyFor;

const plugin = {name:'haike-local-snapcn',setup(build){
  build.onResolve({filter:/^@remotion\/google-fonts\//},args=>({path:args.path.split('/').pop(),namespace:'haike-font'}));
  build.onLoad({filter:/.*/,namespace:'haike-font'},args=>({contents:`export function loadFont(){return {fontFamily:${JSON.stringify(familyFor(args.path))},waitUntilDone:()=>Promise.resolve()}};export function getInfo(){return {fonts:{normal:{}}}}`,loader:'js'}));
  build.onLoad({filter:/upstream[\\/]registry[\\/].*\.tsx?$/},async args=>({contents:require('./compat/local-source.cjs')(fs.readFileSync(args.path,'utf8')),loader:args.path.endsWith('tsx')?'tsx':'ts'}));
  build.onResolve({filter:/^react(?:-dom)?(?:\/.*)?$/},args=>({path:shared.resolve(args.path)}));
  build.onResolve({filter:/^@\//},args=>{
    const p=args.path;
    if(p==='@/lib/snap-cn-ui')return {path:path.join(root,'upstream/registry/snap-cn-ui/core/index.ts')};
    if(p.startsWith('@/lib/'))return {path:path.join(root,'upstream',p.slice(2)+'.ts')};
    const m=p.match(/^@\/(?:components\/snap-cn|registry\/snap-cn-ui)\/([^/]+)$/);
    if(m){const tier=['caret','input'].includes(m[1])?'snap-cn-ui':'snap-cn';return {path:path.join(root,'upstream/registry',tier,m[1],'index.tsx')};}
    return null;
  });
}};
const common={bundle:true,plugins:[plugin],nodePaths:[path.join(root,'node_modules'),path.join(composer,'node_modules')],jsx:'automatic',define:{'process.env.NODE_ENV':'"production"'},logLevel:'warning'};
async function main(){
  fs.mkdirSync(out,{recursive:true});
  const definitions=registry.items.map((item,i)=>{
    const text=fs.readFileSync(path.join(root,'upstream/registry/snap-cn',item.name,'config.ts'),'utf8');
    const name=text.match(/componentName:\s*"([^"]+)"/)[1];
    const cfg=text.match(/export const (\w+Config)/)[1];
    return {item,name,cfg,i};
  });
  const imports=definitions.map(({item,name,cfg,i})=>`import {${name} as C${i}} from './upstream/registry/snap-cn/${item.name}';\nimport {${cfg} as P${i}} from './upstream/registry/snap-cn/${item.name}/config';`).join('\n');
  const rows=definitions.map(({item,i})=>`{id:${JSON.stringify(item.name)},title:${JSON.stringify(item.title)},component:C${i},config:P${i}}`).join(',\n');
  const generated=`// Generated from the pinned free registry by build.cjs.\n${imports}\nexport const definitions=[${rows}];\n`;
  fs.writeFileSync(path.join(root,'definitions.generated.ts'),generated);
  if(process.argv[2]==='metadata'){
    const result=await esbuild.build({...common,stdin:{contents:`${generated}\nconsole.log(JSON.stringify(definitions.map(({component,...d})=>d)));`,resolveDir:root,loader:'tsx'},write:false,platform:'node',format:'cjs',external:['react','react-dom','remotion']});
    const target=path.join(out,'metadata.cjs');fs.writeFileSync(target,result.outputFiles[0].contents);
    // Shared peer dependencies are explicitly supplied by the host composer.
    const {spawnSync}=require('child_process');const run=spawnSync(process.execPath,[target],{encoding:'utf8',env:{...process.env,NODE_PATH:path.join(composer,'node_modules')}});if(run.status!==0)throw Error(run.stderr);fs.writeFileSync(path.join(out,'metadata.json'),run.stdout);console.log('Metadata:',definitions.length);return;
  }
  await esbuild.build({...common,entryPoints:[path.join(root,'Gallery.tsx')],outfile:path.join(out,'gallery.js'),platform:'browser',format:'iife',minify:true,sourcemap:false});
  fs.copyFileSync(path.join(root,'index.html'),path.join(out,'index.html'));
  fs.copyFileSync(path.join(root,'gallery.css'),path.join(out,'gallery.css'));
  console.log(JSON.stringify({components:definitions.length,output:out}));
}
main().catch(e=>{console.error(e);process.exitCode=1});
