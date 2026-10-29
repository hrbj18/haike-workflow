// Bounded stills from the same component, props and source directory as export.
const path = require('path');
const fs = require('fs');
const {createRequire} = require('module');
const root = path.resolve(__dirname, '..');
const projectRequire = createRequire(path.join(root, 'remotion-composer/package.json'));
const {bundle} = projectRequire('@remotion/bundler');
const {selectComposition, renderStill, openBrowser} = projectRequire('@remotion/renderer');
(async () => {
  const [output, publicDir, jsonFrames] = process.argv.slice(2);
  const frames = JSON.parse(jsonFrames);
  if (!Array.isArray(frames) || !frames.length || frames.length > 12 || frames.some(f => !Number.isInteger(f) || f < 0)) throw Error('预览帧无效');
  const inputProps = JSON.parse(fs.readFileSync(path.join(output, 'props.json'), 'utf8'));
  const serveUrl = await bundle({entryPoint: path.join(root, 'templates/motiongit-dark-full-v1/index.tsx'), publicDir,
    webpackOverride: config => ({...config, cache: {...config.cache, type: 'filesystem', cacheDirectory: path.join(output, 'webpack-cache')}})});
  const browser = await openBrowser('chrome', {chromiumOptions: {gl: 'angle'}});
  try {
    const composition = await selectComposition({serveUrl, id: 'DarkFull', inputProps, puppeteerInstance: browser});
    for (const frame of frames) await renderStill({serveUrl, composition, inputProps, frame, scale: .5,
      imageFormat: 'jpeg', output: path.join(output, frame+'.jpg'), puppeteerInstance: browser, chromiumOptions: {gl: 'angle'}});
  } finally {await browser.close({silent: true});}
})().catch(e => {process.stderr.write(String(e.stack || e)); process.exit(1);});
