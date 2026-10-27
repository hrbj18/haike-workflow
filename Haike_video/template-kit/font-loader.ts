import React, {useEffect, useState} from 'react';
import {delayRender, continueRender, cancelRender, staticFile, registerRoot} from 'remotion';

// Explicit portable font profile. Original Windows fonts are not redistributed.
const fonts = [
  ['Microsoft YaHei', 'NotoSansSC.ttf'],
  ['SimHei', 'NotoSansSC.ttf'],
  ['SimSun', 'NotoSerifSC.ttf'],
  ['Noto Sans SC', 'NotoSansSC.ttf'],
];
let loaded: Promise<void[]> | undefined;
const KitFonts: React.FC<{children?: React.ReactNode}> = ({children}) => {
  const [hold] = useState(() => delayRender('Loading packaged OFL fonts', {timeoutInMilliseconds: 120000}));
  useEffect(() => {
    loaded ??= Promise.all(fonts.map(async ([family, file]) => {
      const face = new FontFace(family, `url("${staticFile('kit-fonts/' + file)}")`, {weight: '100 900'});
      document.fonts.add(await face.load());
    }));
    loaded.then(() => continueRender(hold)).catch(cancelRender);
    return () => continueRender(hold);
  }, [hold]);
  return React.createElement(React.Fragment, null, children);
};
export const registerRootWithFonts = (Root: React.ComponentType) =>
  registerRoot(() => React.createElement(KitFonts, null, React.createElement(Root)));
