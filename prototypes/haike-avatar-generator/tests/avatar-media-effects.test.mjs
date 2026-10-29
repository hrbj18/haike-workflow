import test from 'node:test';
import assert from 'node:assert/strict';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {existsSync} from 'node:fs';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {basename,join,resolve,sep} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {build} from 'esbuild';

const root=resolve(fileURLToPath(new URL('..',import.meta.url)));
const chrome=[process.env.HAIKE_TEST_CHROME,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  '/usr/bin/google-chrome','/usr/bin/chromium','/usr/bin/chromium-browser',
].find(path=>path&&existsSync(path));

test('真实浏览器执行媒体effect：旧草稿伪File不白屏，File/Blob预览与释放正常',
  {skip:chrome?false:'需要本机Chrome；不会下载浏览器或使用个人Profile',timeout:30000},async()=>{
  const directory=await mkdtemp(join(tmpdir(),'haike-avatar-media-effects-'));
  try{
    const entry=`
      import React,{act} from 'react';
      import {createRoot} from 'react-dom/client';
      import {useAssetUrl} from './src/App.jsx';
      import {normalizeAvatarMedia} from './src/generator-model.js';
      import {PortraitRefinement} from './src/PortraitRefinement.jsx';
      globalThis.IS_REACT_ACT_ENVIRONMENT=true;
      const failures=[];window.addEventListener('error',event=>failures.push(event.message));
      window.addEventListener('unhandledrejection',event=>failures.push(String(event.reason)));
      const nativeCreate=URL.createObjectURL.bind(URL),nativeRevoke=URL.revokeObjectURL.bind(URL);
      const created=[],revoked=[];
      URL.createObjectURL=file=>{const value=nativeCreate(file);created.push(value);return value;};
      URL.revokeObjectURL=url=>{revoked.push(url);nativeRevoke(url);};
      const host=document.getElementById('probe'),root=createRoot(host);
      function Probe({asset}){const url=useAssetUrl(asset,'/placeholder.svg');return React.createElement('output',null,url);}
      function check(condition,message){if(!condition)throw new Error(message);}
      async function render(asset){await act(async()=>root.render(React.createElement(Probe,{asset})));return host.textContent;}
      async function run(){
        check(await render(null)==='/placeholder.svg','null default');
        const server={id:'owned',url:'/api/studio/assets/owned',file:{name:'serialized.png'}};
        check(await render(normalizeAvatarMedia({portrait:server}).portrait)===server.url,'server asset with serialized File');
        check(created.length===0,'ordinary objects must never reach native createObjectURL');
        check(await render({file:{name:'old.wav'}})==='/placeholder.svg','legacy metadata fallback');
        const local={file:new File(['local bytes'],'local.wav',{type:'audio/wav'})};
        check((await render(local)).startsWith('blob:'),'real File preview');
        check(created.length===1,'one local object URL');
        check(await render(server)===server.url,'switch back to owned server URL');
        check(revoked.length===1&&revoked[0]===created[0],'cleanup prior File URL');
        check((await render({file:new Blob(['blob bytes'])})).startsWith('blob:'),'real Blob preview');
        check(created.length===2,'one Blob URL');
        URL.createObjectURL=()=>{throw new TypeError('simulated unavailable object URL');};
        check(await render({...local,url:server.url})===server.url,'URL creation failure falls back without crashing');
        check(revoked.length===2&&revoked[1]===created[1],'cleanup prior Blob URL');
        await act(async()=>root.unmount());
        let pending=null,requests=0,response={status:404,detail:'Not Found'};
        globalThis.fetch=async path=>{
          check(path==='/api/studio/refinement/prepare','unexpected request beyond local preparation');requests++;
          return new Response(JSON.stringify({detail:response.detail}),{status:response.status,headers:{'Content-Type':'application/json'}});
        };
        const refinement=createRoot(host),show=async id=>{
          await act(async()=>{
            refinement.render(React.createElement(PortraitRefinement,{draftId:'fixture-draft',portrait:{id},onPending:value=>{pending=value;},onAdopt:()=>{throw new Error('must not adopt without result');}}));
            await new Promise(resolve=>setTimeout(resolve,0));
          });
          for(let step=0;step<8&&pending!==false;step++)await act(async()=>{await new Promise(resolve=>setTimeout(resolve,0));});
        };
        await show('fixture-original');
        check(pending===false,'unavailable optional refinement must not block the original portrait');
        check(host.textContent.includes('服务版本与开通状态')&&host.textContent.includes('原图继续制作'),'actionable Chinese 404');
        check(!host.textContent.includes('Not Found')&&!host.textContent.includes('确认费用并优化图片'),'no raw 404 or paid action');
        response={status:503,detail:'图片精修尚未开通；原图已保留，可使用原图继续'};
        await show('fixture-original-two');
        check(pending===false&&host.textContent.includes(response.detail),'explicit unavailable backend preserves original use');
        check(requests===2,'only two local preparation requests, no upload or paid submission');
        await act(async()=>refinement.unmount());
        check(failures.length===0,failures.join(';'));
        return {passed:true,created:created.length,revoked:revoked.length,errors:failures.length,portrait_refinement_pending:pending};
      }
      run().then(result=>{document.getElementById('result').textContent=JSON.stringify(result);document.body.dataset.status='pass';})
        .catch(error=>{document.getElementById('result').textContent=String(error.stack||error);document.body.dataset.status='fail';});
    `;
    const bundle=await build({stdin:{contents:entry,resolveDir:root,sourcefile:'avatar-media-browser-test.jsx',loader:'jsx'},bundle:true,write:false,
      format:'iife',platform:'browser',jsx:'automatic',define:{'import.meta.env.BASE_URL':'"/"'},loader:{'.css':'empty'}});
    const html=join(directory,'index.html');
    await writeFile(html,`<!doctype html><html><body data-status="pending"><div id="probe"></div><pre id="result"></pre><script>${bundle.outputFiles[0].text}</script></body></html>`);
    const {stdout}=await promisify(execFile)(chrome,[
      '--headless=new','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-extensions',
      '--disable-sync','--disable-gpu','--mute-audio',`--user-data-dir=${join(directory,'profile')}`,
      '--dump-dom','--virtual-time-budget=3000',pathToFileURL(html).href,
    ],{timeout:20000,windowsHide:true,maxBuffer:4*1024*1024});
    const result=stdout.match(/<pre id="result">([\s\S]*?)<\/pre>/)?.[1]||'missing browser result';
    assert.equal(/<body data-status="pass">/.test(stdout),true,result.slice(0,2000));
    assert.match(result,/"passed":true/);assert.match(result,/"created":2/);assert.match(result,/"revoked":2/);assert.match(result,/"errors":0/);
  }finally{
    const absolute=resolve(directory),temporary=resolve(tmpdir());
    assert.ok(absolute.startsWith(temporary+sep)&&basename(absolute).startsWith('haike-avatar-media-effects-'));
    await rm(absolute,{recursive:true,force:true,maxRetries:3,retryDelay:200});
  }
});
