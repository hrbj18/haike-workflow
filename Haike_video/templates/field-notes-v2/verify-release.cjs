// Formal template5 source/dependency identity. Does not call a media provider.
const fs=require('fs'),path=require('path'),crypto=require('crypto'),{createRequire}=require('module');
function verify(){
 const root=path.resolve(__dirname,'../../..'),release=JSON.parse(fs.readFileSync(path.join(__dirname,'release.json'),'utf8'));
 if(release.template_id!=='field-notes-v2'||release.number!==5||release.version!=='2.0.0')throw Error('动效模板5定稿身份不匹配');
 for(const item of release.sources){const file=path.resolve(root,item.path);if(!file.startsWith(root+path.sep)||crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==item.sha256)throw Error('动效模板5定稿来源已改变：'+item.path+'；建立新版本并重验');}
 const shared=createRequire(path.join(root,'Haike_video/remotion-composer/package.json'));
 for(const [name,version] of Object.entries(release.dependencies))if(JSON.parse(fs.readFileSync(shared.resolve(name+'/package.json'),'utf8')).version!==version)throw Error('动效模板5依赖已改变：'+name);
 return {valid:true,template_id:release.template_id,number:5,version:release.version,checkedSources:release.sources.length,scope:release.scope};
}
module.exports={verify};if(require.main===module){try{console.log(JSON.stringify(verify()))}catch(e){console.error(e.message);process.exitCode=1}}
