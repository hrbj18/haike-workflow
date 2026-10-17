import assert from 'node:assert/strict';
import test from 'node:test';
import {RefinementClient} from '../adapters/node-client.mjs';

test('confirmed upload, polling, files and explicit retry follow the internal API',async()=>{
  const calls=[];
  const client=new RefinementClient({baseUrl:'http://127.0.0.1:4765',token:'internal-test-token',fetchImpl:async(url,options)=>{
    calls.push([url,options]);return new Response(url.includes('/files/')?new Uint8Array([1,2,3]):JSON.stringify({id:'fixture',status:'queued'}));
  }});
  await client.submit(new Uint8Array([1]),'a:p',{confirmed:true});
  assert.match(calls[0][0],/confirmed=true/);
  assert.equal(calls[0][1].redirect,'error');
  await client.get('fixture','a:p');assert.equal(calls[1][1].method,'GET');
  assert.deepEqual(await client.file('fixture','a:p'),new Uint8Array([1,2,3]));
  await client.retry('fixture','a:p',{confirmed:true,acknowledgeUncertain:true});
  assert.deepEqual(JSON.parse(calls[3][1].body),{confirmed:true,acknowledge_uncertain:true});
});

test('uncertain submission is never automatically retried',async()=>{
  let count=0;
  const client=new RefinementClient({baseUrl:'http://127.0.0.1:4765',token:'internal-test-token',fetchImpl:async()=>{count++;throw new Error('fixture');}});
  await assert.rejects(client.submit(new Uint8Array([1]),'a:p',{confirmed:true}),/勿自动重发/);
  assert.equal(count,1);
});

test('server failures are sanitized',async()=>{
  const client=new RefinementClient({baseUrl:'http://127.0.0.1:4765',token:'internal-test-token',fetchImpl:async()=>new Response('private upstream content',{status:500})});
  await assert.rejects(client.get('fixture','a:p'),error=>error.status===500&&!error.message.includes('private upstream'));
});
