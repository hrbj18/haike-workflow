// CLI bundles its config: resolve the adapter at runtime from the documented
// remotion-composer working directory so its own __dirname stays source-owned.
const path=require('path');
const {Config}=require(path.resolve(process.cwd(),'node_modules/@remotion/cli/dist/config/index.js'));
Config.overrideWebpackConfig(require(path.resolve(process.cwd(),'../templates/chromatic-motion-lab-v1/webpack.cjs')));
