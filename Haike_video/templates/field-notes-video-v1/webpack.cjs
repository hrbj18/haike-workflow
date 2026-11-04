const path=require('path'),{createRequire}=require('module');
const composer=path.resolve(__dirname,'../../remotion-composer');
const shared=createRequire(path.join(composer,'package.json'));
module.exports=config=>{
 config.resolve.modules=[path.join(composer,'node_modules'),'node_modules'];
 config.resolve.alias={...config.resolve.alias,react:shared.resolve('react'),'react-dom':shared.resolve('react-dom'),remotion:shared.resolve('remotion')};
 return config;
};
