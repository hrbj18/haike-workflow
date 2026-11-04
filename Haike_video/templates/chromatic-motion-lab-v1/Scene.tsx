import React from 'react';
import {ChromaticScene as LegacyScene,type Episode} from './AvatarScene';
import {BookendScene} from './BookendScene';

export function ChromaticScene(props:{variant?:string;episode:Episode;previewMuted?:boolean}){
 return props.episode.presentation==='bookends'?<BookendScene {...props}/>:<LegacyScene {...props}/>;
}
