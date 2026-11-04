// Read-only release verification. Regenerate a release only for an approved version.
const fs=require('fs'),path=require('path'),crypto=require('crypto'),{createRequire}=require('module');
const project=path.resolve(__dirname,'../../../..');
function verify(){
 const release=JSON.parse(fs.readFileSync(path.join(__dirname,'release.json'),'utf8'));
 if(release.template_id!=='field-notes-v1'||release.version!=='1.0.0')throw Error('动效模板4定稿身份不匹配');
 for(const item of release.sources){
  const file=path.resolve(project,item.path);
  if(!file.startsWith(project+path.sep)||!fs.statSync(file).isFile()||crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==item.sha256)throw Error('动效模板4定稿源码已改变：'+item.path+'；恢复定稿或建立新版本');
 }
 const shared=createRequire(path.join(project,'Haike_video/remotion-composer/package.json'));
 for(const [name,version] of Object.entries(release.dependencies))if(JSON.parse(fs.readFileSync(shared.resolve(name+'/package.json'),'utf8')).version!==version)throw Error('动效模板4依赖版本已改变：'+name);
 return {valid:true,template_id:release.template_id,version:release.version,checkedSources:release.sources.length,scope:release.scope};
}
module.exports={verify};
if(require.main===module){try{console.log(JSON.stringify(verify()))}catch(e){console.error(e.message);process.exitCode=1}}
