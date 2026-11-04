const fs = require('fs');
const path = require('path');
const {createRequire} = require('module');
const composer = path.resolve(__dirname, '../../remotion-composer');
const shared = createRequire(path.join(composer, 'package.json'));
const library = path.resolve(__dirname, '../../motion-components/snapcn');
const webpack = shared('webpack');
const registry = JSON.parse(fs.readFileSync(path.join(library, 'upstream/registry/snap-cn/registry.json')));

module.exports = function configure(config) {
  const alias = {
    react: shared.resolve('react'), 'react-dom': shared.resolve('react-dom'),
    remotion: shared.resolve('remotion'),
    '@/lib/snap-cn-ui': path.join(library, 'upstream/registry/snap-cn-ui/core/index.ts'),
    '@/lib/customizer-config': path.join(library, 'upstream/lib/customizer-config.ts'),
    '@/lib/utils': path.join(library, 'upstream/lib/utils.ts'),
  };
  for (const name of [...registry.items.map(item => item.name), 'input', 'caret']) {
    const tier = ['input', 'caret'].includes(name) ? 'snap-cn-ui' : 'snap-cn';
    alias[`@/components/snap-cn/${name}$`] = path.join(library, 'upstream/registry', tier, name, 'index.tsx');
  }
  config.resolve.modules = [path.join(library, 'node_modules'), path.join(composer, 'node_modules'), 'node_modules'];
  config.resolve.alias = {...config.resolve.alias, ...alias};
  config.plugins.push(new webpack.NormalModuleReplacementPlugin(/^@remotion\/google-fonts\//, path.join(library, 'compat/font-loader.ts')));
  config.module.rules.unshift({test: /upstream[\\/]registry[\\/].*\.tsx?$/, enforce: 'pre', use: [path.join(library, 'compat/local-source-loader.cjs')]});
  return config;
};
