const fs=require('fs'),path=require('path'),crypto=require('crypto');
function verify(){
 const release=JSON.parse(fs.readFileSync(path.join(__dirname,'release.json'),'utf8'));
 for(const [file,expected] of Object.entries(release.files)){
  const actual=crypto.createHash('sha256').update(fs.readFileSync(path.resolve(__dirname,file))).digest('hex');
  if(actual!==expected)throw Error(`动效模板2定稿文件已变化：${file}。请恢复定稿文件；改设计须另建版本。`);
 }
 return release;
}
module.exports={verify};
if(require.main===module)console.log(`动效模板2 · 活力现场 v${verify().version} 文件校验通过。`);
