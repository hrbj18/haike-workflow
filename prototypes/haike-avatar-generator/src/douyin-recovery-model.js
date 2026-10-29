export async function resumeDouyinJob(api,jobId) {
  const state=await api('/api/studio/ai/douyin/login-confirmed',{confirmed:true});
  if(state?.douyin_login_confirmed!==true)throw new Error('抖音下载登录尚未检查通过，请先管理账号并检查。');
  if(state?.douyin_collection_ready!==true)throw new Error('抖音采集服务尚未就绪，请联系管理员或选择跳过抖音。');
  return api(`/api/production-queue/jobs/${jobId}/retry`,{});
}
