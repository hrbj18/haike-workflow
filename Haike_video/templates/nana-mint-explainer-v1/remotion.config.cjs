const path = require('path');
const {Config} = require(path.resolve(process.cwd(), 'node_modules/@remotion/cli/dist/config/index.js'));
Config.overrideWebpackConfig(require(path.resolve(process.cwd(), '../templates/nana-mint-explainer-v1/webpack.cjs')));
