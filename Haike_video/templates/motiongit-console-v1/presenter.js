/* Haike-owned composition layer. Native scene animation and audio stay intact. */
(() => {
  'use strict';
  const config = window.HAIKE_PRESENTER;
  if (!config || config.schema !== 'haike.console-presenter/1') throw Error('Presenter policy missing');
  const previous = window.renderAt;
  if (typeof previous !== 'function') throw Error('Native output clock missing');
  const style = document.createElement('style');
  style.textContent = '.tkc{visibility:hidden!important}#haike-presenter{position:absolute;overflow:hidden;pointer-events:none;border:1px solid rgba(153,195,225,.35);box-sizing:border-box;box-shadow:0 16px 48px #0005}#haike-presenter img{position:absolute;max-width:none;object-fit:fill}';
  document.head.append(style);
  const card = document.createElement('div');
  card.id = 'haike-presenter';
  Object.assign(card.style, {left: `${config.left}px`, top: `${config.top}px`,
    width: `${config.diameter}px`, height: `${config.diameter}px`, borderRadius:'50%', opacity:'0'});
  const image = new Image();
  image.alt = '';
  // Keep the reviewed native 720x1280 full-head framing, enlarged uniformly.
  Object.assign(image.style, {left:'0px', top:'0px', width:`${config.diameter}px`, height:`${config.diameter * 1280 / 720}px`});
  card.append(image);
  document.getElementById('stage').append(card);
  const clamp = x => Math.max(0, Math.min(1, x));
  const smooth = x => {x=clamp(x); return x*x*(3-2*x);};
  window.renderAt = async t => {
    const result = await previous(t);
    const frame = Math.floor(t * config.fps + 1e-6);
    const enabled = config.mode !== 'hidden' && frame >= config.startFrame && frame < config.endFrame;
    const opacity = enabled ? Math.min(smooth((frame-config.startFrame+1)/config.fadeFrames),
      smooth((config.endFrame-frame)/config.fadeFrames)) : 0;
    card.style.opacity = String(opacity);
    card.style.transform = `translateY(${(1-opacity)*16}px)`;
    card.dataset.visible = String(opacity > 0);
    if (opacity > 0) {
      const next = talkSrc(t);
      if (image.getAttribute('src') !== next) {image.src = next; await image.decode();}
    }
    return result;
  };
  window.READY = Promise.resolve(window.READY).then(() => window.renderAt(0));
})();
