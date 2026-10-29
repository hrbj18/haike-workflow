export const MATERIAL_API='/api/material-library';
export const healthLabel=value=>({valid:'文件可用',missing:'文件缺失',changed:'内容已变化',error:'检查失败',unchecked:'尚未检查'})[value]||'尚未检查';
export const materialLabels=value=>[...new Set(String(value||'').split(/[,，\n]/).map(v=>v.trim()).filter(Boolean))];
export function materialQuery({query='',archived='active',aspect='all',page=1}={}) {
  return new URLSearchParams({query:query.trim(),archived,aspect,page:String(page),page_size:'24'}).toString();
}
export function metadataUpdate(item,fields) {
  if(!item?.id||!Number.isInteger(item.metadata?.revision))throw new Error('请重新读取素材后再保存。');
  if(String(fields.notes||'').length>4000)throw new Error('备注最多4,000字。');
  return {items:[{media_id:item.id,expected_revision:item.metadata.revision}],patch:{tags:materialLabels(fields.tags),collections:materialLabels(fields.collections),notes:String(fields.notes||''),archived:fields.archived===true}};
}
export function materialImport({kind,path}) {
  if(!['file','folder','catalog'].includes(kind)||!String(path||'').trim())throw new Error('请选择导入方式，并填写本机完整路径。');
  return {kind,path:path.trim()};
}
