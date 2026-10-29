/** Exercise the production frame adapter against the installed GSAP version. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const root = path.resolve(__dirname, '..');
const composerRequire = createRequire(path.join(root, 'remotion-composer/package.json'));
const ts = composerRequire('typescript');
const cache = new Map();
function load(file) {
  if (cache.has(file)) return cache.get(file);
  const mod = {exports: {}};
  cache.set(file, mod.exports);
  const js = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
  }).outputText;
  const localRequire = id => id.startsWith('.')
    ? load(path.resolve(path.dirname(file), id + '.ts')) : composerRequire(id);
  vm.runInThisContext(`(function(require,module,exports){${js}\n})`, {filename: file})(localRequire, mod, mod.exports);
  cache.set(file, mod.exports);
  return mod.exports;
}
const {buildMotion} = load(path.join(root, 'templates/hum-production-v1/dynamic/motion.ts'));
const items = n => Array.from({length: n}, (_, i) => ({id: String(i), img: `${i}.jpg`, width: i % 2 ? 16 : 9, height: i % 2 ? 9 : 16}));
const snap = m => JSON.stringify({states: m.states, cursor: m.cursor, camera: m.camera},
  (key, value) => key === '_gsap' ? undefined : typeof value === 'number' ? Number(value.toFixed(6)) : value);
let checks = 0;
for (const count of [3, 5, 9]) for (const playroom of [false, true]) {
  for (const action of ['click-open', 'waterfall', 'spatial-gallery', 'reflow']) {
    const m = buildMotion(action, items(count), count - 1, 150, playroom);
    m.timeline.time(2.5, false); const middle = snap(m);
    m.timeline.time(4.99, false); m.timeline.time(.1, false); m.timeline.time(2.5, false);
    assert.equal(snap(m), middle, `${action}: seeking must be deterministic`);
    if (action === 'click-open') {
      assert.ok(m.states[count - 1].w > m.originals[count - 1].w, 'selected card expands');
      m.timeline.time(4.99, false);
      m.states.forEach((s, i) => ['x', 'y', 'w', 'h', 'opacity'].forEach(k => assert.ok(Math.abs(s[k] - m.originals[i][k]) < .001, 'same cards return')));
    }
    if (action === 'waterfall') {
      m.timeline.time(1, false); const y = m.states[0].y;
      m.timeline.time(4, false); assert.ok(m.states[0].y > y + 100, 'wall moves continuously');
    }
    if (action === 'reflow') {
      m.timeline.time(4, false);
      const supporting = m.states.filter((_, i) => i !== count - 1);
      assert.ok(supporting.every(s => s.x >= 830 && s.y >= 0 && s.y + s.h <= 931));
      supporting.slice(1).forEach((s, i) => assert.ok(s.y >= supporting[i].y + supporting[i].h, 'supporting panels do not overlap'));
    }
    if (action === 'spatial-gallery') {
      m.timeline.time(.3, false); const y = m.camera.y;
      m.timeline.time(4.99, false); assert.ok(m.camera.y > y + 40 && m.camera.zoom > 1.1);
    }
    m.timeline.kill(); checks++;
  }
}
console.log(`PASS ${checks} motion cases: frame seeking, expansion/return, continuous wall, panel geometry and gallery camera`);
