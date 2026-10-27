import test from 'node:test';
import assert from 'node:assert/strict';
import {resumeDouyinJob} from '../src/douyin-recovery-model.js';

test('scope and collector readiness precede queue retry',async()=>{
  const calls=[];
  const result=await resumeDouyinJob(async(path,data)=>{calls.push([path,data]);return calls.length===1?{douyin_login_confirmed:true,douyin_collection_ready:true}:{job_id:'test-job'};},'test-job');
  assert.equal(result.job_id,'test-job');
  assert.deepEqual(calls.map(item=>item[0]),['/api/studio/ai/douyin/login-confirmed','/api/production-queue/jobs/test-job/retry']);
});

for(const state of [{},{douyin_login_confirmed:false},{douyin_login_confirmed:true,douyin_collection_ready:false}]){
  test(`unconfirmed login or unavailable collector never retries: ${JSON.stringify(state)}`,async()=>{
    const calls=[];
    await assert.rejects(resumeDouyinJob(async path=>{calls.push(path);return state;},'test-job'));
    assert.equal(calls.length,1);
  });
}

test('failed account check does not retry the paid production job',async()=>{
  const calls=[];
  await assert.rejects(resumeDouyinJob(async path=>{calls.push(path);throw new Error('登录检查失败');},'test-job'),/登录检查失败/);
  assert.equal(calls.length,1);
});
