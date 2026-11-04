// Verify the six design baselines. This is an identity check, not production approval.
const fs=require('fs'),path=require('path'),crypto=require('crypto'),{createRequire}=require('module');
function verify(){
 const root=path.resolve(__dirname,'../../..');
 const freeze=JSON.parse(fs.readFileSync(path.join(__dirname,'FROZEN.json'),'utf8'));
 if(freeze.schema!=='haike.six-design-freeze/1'||freeze.templates.length!==6||freeze.templates.map(t=>t.number).join(',')!=='6,7,8,9,10,11')throw Error('Six design identities required');
 for(const item of freeze.sources){
  const file=path.resolve(root,item.path),relative=path.relative(root,file);
  if(relative.startsWith('..')||path.isAbsolute(relative)||!fs.existsSync(file)||crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==item.sha256)throw Error('Frozen design changed: '+item.path+'; create a separate revision');
 }
 const shared=createRequire(path.join(root,'Haike_video/remotion-composer/package.json'));
 for(const [name,version] of Object.entries(freeze.dependencies))if(JSON.parse(fs.readFileSync(shared.resolve(name+'/package.json'),'utf8')).version!==version)throw Error('Frozen dependency changed: '+name);
 return {valid:true,templates:freeze.templates.length,sources:freeze.sources.length,scope:freeze.scope,productionApproved:false};
}
module.exports={verify};
if(require.main===module){try{console.log(JSON.stringify(verify()))}catch(e){console.error(e.message);process.exitCode=1}}
