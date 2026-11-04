import React from 'react';
import {Composition,registerRoot} from 'remotion';
import {catalogue,Demo} from './Demo';
// One generated catalogue owns all registrations; edit Demo/catalogue, not individual JSX.
const Root=()=> <>{catalogue.map(d=><Composition key={d.id} id={d.id} component={Demo} defaultProps={{id:d.id}} width={d.config.compositionWidth} height={d.config.compositionHeight} durationInFrames={d.config.durationInFrames} fps={d.config.fps}/>)}</>;
registerRoot(Root);
