import React from 'react';
import {Composition} from 'remotion';
import {AvatarTemplate3Sample} from './Composition';

export const Root: React.FC = () => (
  <Composition
    id="AvatarTemplate3Sample"
    component={AvatarTemplate3Sample}
    width={1080}
    height={1440}
    fps={30}
    durationInFrames={450}
    defaultProps={{
      avatar: 'avatar.mp4',
      broll: null,
      audio: 'narration.wav',
      cues: [],
    }}
  />
);
