const ASR_MODELS=new Set(['haike/bailian-asr','haike/tencent-asr','haike/local-whisper']);
const UNAVAILABLE=new Set(['unconfigured','budget_required','blocked','disabled','unavailable']);
const FALLBACK_REASONS={invalid_key:'服务授权无效',insufficient_balance:'识别额度不足'};

export const isAsrCapability=item=>item?.capability==='asr'||ASR_MODELS.has(item?.model||item?.id);

export function asrPolicy(account) {
  const primary=account?.local_asr||{};
  const items=account?.capabilities?.items||[];
  const capability=items.find(item=>isAsrCapability(item)&&!UNAVAILABLE.has(item.status));
  const provider=primary.provider||'gateway';
  // The selected primary owns readiness. A ready fallback or unrelated old
  // gateway capability cannot approve it; readiness is separate from evidence.
  const explicitPrimary=provider==='bailian'||provider==='local-whisper';
  const ready=explicitPrimary?primary.ready===true:primary.ready===true||!!capability;
  const fallbackOn=[...new Set(Array.isArray(primary.fallback_on)?primary.fallback_on:[])]
    .filter(reason=>Object.hasOwn(FALLBACK_REASONS,reason));
  const fallbackReady=primary.fallback==='local-whisper'&&primary.fallback_ready===true;

  if(provider==='bailian') {
    const direct=primary.backend==='internal_asr';
    const firstRun=ready&&primary.verified===false;
    const condition=fallbackOn.map(reason=>FALLBACK_REASONS[reason]).join('或');
    let fallback=fallbackReady?'海客备用识别已就绪，当前未配置自动备用条件。'
      :primary.fallback==='local-whisper'?'海客备用识别尚未就绪。':'尚未配置海客备用识别。';
    if(primary.fallback==='local-whisper'&&condition) {
      fallback=fallbackReady?`仅在${condition}时尝试海客备用识别。`
        :`海客备用识别尚未就绪；遇到${condition}时请联系管理员检查海客识别服务。`;
    }
    return {provider,ready,capability,fallbackReady,fallbackOn,
      name:'海客ASR',detail:'音频识别与字幕提取',
      billing:direct?'费用预估 · 按报价确认':'按当次报价确认',
      readyLabel:firstRun?'可开始识别':'已就绪',unreadyLabel:'未就绪',
      notice:`${firstRun?'海客ASR可开始识别，尚未记录首次成功结果。':ready?'海客ASR为音频识别、字幕提取和分镜提供时间轴。':'海客ASR尚未就绪，请联系管理员检查识别服务。'}费用预估将在执行前展示。${fallback}`};
  }
  if(provider==='local-whisper') {
    return {provider,ready,capability,fallbackReady:false,fallbackOn:[],
      name:'海客ASR',detail:'音频识别与字幕提取',
      billing:'本地识别 · 无识别调用费用',readyLabel:'已就绪',unreadyLabel:'未就绪',
      notice:ready?'海客ASR当前使用本地识别，为字幕和分镜提供时间轴，不产生识别调用费用。新任务采用当前设置，历史任务保留原参数。'
        :'海客ASR尚未就绪，请联系管理员检查识别服务。'};
  }
  return {provider,ready,capability,fallbackReady:false,fallbackOn:[],
    name:'海客ASR',detail:'音频识别与字幕提取',billing:'费用以当次报价为准',
    readyLabel:provider==='gateway'?'已开通':'已就绪',unreadyLabel:'未开通',notice:''};
}
