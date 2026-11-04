// Per-episode copy; the approved motion, geometry and palette are not inputs.
const defaults=require('./content.json');
const limits=require('./input-contract.json').text_limits;
function validateContent(value=defaults){
 if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(k=>!Object.prototype.hasOwnProperty.call(limits,k)))throw Error('文案字段无效，请使用模板的固定文字槽。');
 const result={...defaults,...value};
 for(const [key,max] of Object.entries(limits)){
  const text=result[key];
  if(typeof text!=='string'||!text.trim()||/[\n\r。！？<>]/u.test(text))throw Error(`文字槽 ${key} 只接受非空短标签。`);
  const width=[...text].reduce((sum,c)=>sum+(c.charCodeAt(0)<128?.55:1),0);
  if(width>max)throw Error(`文字槽 ${key} 过长，请精简到约 ${max} 个中文字宽。`);
 }
 return result;
}
module.exports={validateContent,limits};
