import test from 'node:test';
import assert from 'node:assert/strict';
import {api} from '../src/studio-api.js';
import {refinementError} from '../src/portrait-refinement-model.js';

test('本机精修接口缺失显示中文可操作提示，不冒充中转模型未开通', async()=>{
  const previous=globalThis.fetch;
  globalThis.fetch=async()=>new Response(JSON.stringify({detail:'Not Found'}),{status:404,headers:{'Content-Type':'application/json'}});
  try{
    await assert.rejects(api('/api/studio/refinement/prepare',{}),error=>{
      assert.equal(error.status,404);
      const text=refinementError(error,{preparing:true});
      assert.match(text,/服务版本与开通状态/);assert.match(text,/原图继续制作/);
      assert.ok(!text.includes('Not Found'));assert.ok(!text.includes('中转站未开通'));
      assert.match(refinementError(error),/保留原任务编号/);
      return true;
    });
  }finally{globalThis.fetch=previous;}
});
test('保留后端明确未开通/待确认价格的中文语义，英文网络错误不直接显示',()=>{
  const message='图片精修尚未开通；原图已保留，可使用原图继续';
  assert.equal(refinementError({status:503,message},{preparing:true}),message);
  assert.match(refinementError({status:403,message:'Forbidden'},{preparing:true}),/检查海客 Key/);
  const text=refinementError(new TypeError('Failed to fetch'),{preparing:true});
  assert.match(text,/检查连接/);assert.match(text,/原图继续制作/);assert.ok(!text.includes('Failed to fetch'));
});
