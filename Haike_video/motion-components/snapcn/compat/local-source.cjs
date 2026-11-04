module.exports=function localSource(source){
  if(!source.includes('https://cdn.jsdelivr.net/npm'))return source;
  const rewritten=source.replace(/["']https:\/\/cdn\.jsdelivr\.net\/npm([^"']*)["']/g,(_,suffix)=>`__haikeStaticFile(${JSON.stringify('assets/fontsource'+suffix)})`);
  return 'import {staticFile as __haikeStaticFile} from "remotion";\n'+rewritten;
};
