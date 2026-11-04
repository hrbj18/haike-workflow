// Media production is invoked by scripts/nana_mint_preview.py's unified queue.
const fs = require('fs');
const path = require('path');
const {createRequire} = require('module');
const shared = createRequire(path.resolve(__dirname, '../../remotion-composer/package.json'));
const {bundle} = shared('@remotion/bundler');
const {selectComposition, openBrowser, renderMedia, renderStill} = shared('@remotion/renderer');
const [action, data, output, browserExecutable, frames = '30'] = process.argv.slice(2);
async function main() {
  require('./verify-release.cjs').verify();
  const serveUrl = path.join(data, 'bundle');
  if (action === 'bundle') {
    await bundle({entryPoint: path.join(__dirname, 'index.tsx'), outDir: serveUrl, publicDir: path.join(data, 'public'), enableCaching: false, webpackOverride: require('./webpack.cjs')});
    console.log('Nana template bundle ready'); return;
  }
  if (!['frames', 'render'].includes(action)) throw Error('Unknown action');
  const browser = await openBrowser('chrome', {browserExecutable, chromiumOptions: {gl: 'angle'}});
  try {
    const composition = await selectComposition({serveUrl, id: 'NanaTemplate', browserExecutable, puppeteerInstance: browser});
    const options = {serveUrl, composition, browserExecutable, puppeteerInstance: browser, chromiumOptions: {gl: 'angle'}, timeoutInMilliseconds: 90000, offthreadVideoCacheSizeInBytes: 96 * 1024 * 1024, offthreadVideoThreads: 1, mediaCacheSizeInBytes: 64 * 1024 * 1024};
    if (action === 'frames') {
      fs.mkdirSync(output, {recursive: true});
      for (const frame of frames.split(',').map(Number)) {
        await renderStill({...options, frame, output: path.join(output, `${String(frame).padStart(4, '0')}.png`), imageFormat: 'png'});
        console.log('Frame', frame);
      }
    } else {
      let previous = -1;
      await renderMedia({...options, codec: 'h264', videoBitrate: '22M', x264Preset: 'fast', pixelFormat: 'yuv420p', imageFormat: 'jpeg', jpegQuality: 100, outputLocation: output, concurrency: 1, muted: true,
        ffmpegOverride: ({args}) => {const changed = [...args]; changed.splice(changed.length - 1, 0, '-minrate', '22M', '-maxrate', '22M', '-bufsize', '44M', '-x264-params', 'nal-hrd=cbr:force-cfr=1'); return changed;},
        onProgress: ({progress}) => {const p = Math.floor(progress * 20); if (p !== previous) {previous = p; console.log('Rendered', p * 5 + '%');}},
      });
    }
  } finally {await browser.close({silent: true});}
}
main().catch(error => {console.error(error); process.exitCode = 1;});
