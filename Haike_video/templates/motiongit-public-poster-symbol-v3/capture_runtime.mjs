// Haike-owned deterministic metadata adapter. No private package is loaded.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL, fileURLToPath} from 'node:url';
const [projectArg, moduleArg, browserArg, outputArg] = process.argv.slice(2);
if (![projectArg,moduleArg,browserArg,outputArg].every(Boolean)) throw Error('Required project, verified Playwright, verified browser and new output');
const project=path.resolve(projectArg), output=path.resolve(outputArg);
if (fs.existsSync(output)) throw Error('Refusing an existing metadata receipt');
const {chromium}=await import(pathToFileURL(path.resolve(moduleArg,'index.mjs')).href);
const browser=await chromium.launch({executablePath:path.resolve(browserArg),headless:true});
const errors=[];
try {
  const page=await browser.newPage();
  page.on('pageerror',error=>errors.push(error.message));
  page.on('requestfailed',request=>errors.push('Resource failed: '+request.url()));
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.protocol==='data:')return route.continue();
    if(url.protocol==='file:'){
      const file=fileURLToPath(url), relative=path.relative(project,file);
      if(!relative.startsWith('..')&&!path.isAbsolute(relative)&&fs.existsSync(file)&&!fs.lstatSync(file).isSymbolicLink())return route.continue();
    }
    errors.push('Outside project resource rejected');await route.abort();
  });
  await page.goto(pathToFileURL(path.join(project,'index.html')).href,{waitUntil:'load',timeout:30000});
  const receipt=await page.evaluate(async()=>{
    await Promise.race([window.READY||Promise.resolve(),new Promise((_,reject)=>setTimeout(()=>reject(Error('Runtime readiness timed out')),30000))]);
    const end=Number(window.END),fps=Number(window.MACRO_PLAN?.fps);
    if(!Number.isFinite(end)||end<=0||!Number.isInteger(fps)||!Array.isArray(SFX))throw Error('Missing actual public runtime clock/SFX');
    return {schema:'haike.public-runtime-sfx/1',end,fps,sfx:SFX.map(event=>({...event})),source:'actual initialized public scene runtime'};
  });
  if(errors.length)throw Error(errors.join('\n'));
  fs.writeFileSync(output,JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
}finally{await browser.close();}
