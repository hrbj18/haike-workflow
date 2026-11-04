const fs=require('fs'),path=require('path'),crypto=require('crypto');
function verify(root=__dirname){
  const release=JSON.parse(fs.readFileSync(path.join(root,'release.json'),'utf8'));
  if(release.template_id!=='nana-mint-explainer-v1'||release.version!=='1.0.0')throw Error('动效模板3版本清单无效。');
  for(const [file,expected] of Object.entries(release.files)){
    const source=path.resolve(root,file);
    if(!fs.existsSync(source)||crypto.createHash('sha256').update(fs.readFileSync(source)).digest('hex')!==expected)throw Error(`动效模板3定稿文件已改变：${file}；恢复定稿或另建版本。`);
  }
  return release;
}
module.exports={verify};
if(require.main===module)console.log(`动效模板3 v${verify().version} 定稿文件校验通过。`);
