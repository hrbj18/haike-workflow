export function QuoteBilling({quote,internal=false}) {
  if(!internal&&!quote?.estimate_only)return null;
  return <div className="quote-billing"><dl className="summary-list"><div><dt>服务商</dt><dd>{quote?.provider||'内部服务'}</dd></div><div><dt>采购模型</dt><dd>{quote?.provider_model||'以报价说明为准'}</dd></div></dl><p className="helper">{quote?.billing_note||'费用为供应商采购估算，无法作为供应商最终扣费的硬上限；实际结算以供应商账单为准。'}</p></div>;
}
