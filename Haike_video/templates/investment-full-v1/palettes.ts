import type {PaletteVariant, TemplateNumber} from './types';

export const SANS = '"Microsoft YaHei", sans-serif';
export const SERIF = '"SimSun", serif';
export const BINDING:Record<PaletteVariant,TemplateNumber> = {
  'blue-beige':7, 'cyan-charcoal':8, 'black-pink':9,
};
export type Palette = {
  canvas:string; ink:string; mount:string; accent:string; secondary:string;
  captionSurface:string; captionText:string; graphSurface:string; graphText:string;
};
export const PALETTES:Record<PaletteVariant,Palette> = {
  'blue-beige':{canvas:'#0C3967',ink:'#EAD0B0',mount:'#092D53',accent:'#EAD0B0',secondary:'#B9B9B4',
    captionSurface:'#EAD0B0',captionText:'#0C3967',graphSurface:'#EAD0B0',graphText:'#0C3967'},
  'cyan-charcoal':{canvas:'#202425',ink:'#28CCC9',mount:'#153C3D',accent:'#28CCC9',secondary:'#C2D9D5',
    captionSurface:'#28CCC9',captionText:'#202425',graphSurface:'#28CCC9',graphText:'#202425'},
  'black-pink':{canvas:'#0E0E0E',ink:'#FD7B99',mount:'#292025',accent:'#FD7B99',secondary:'#F0CED7',
    captionSurface:'#FD7B99',captionText:'#0E0E0E',graphSurface:'#FD7B99',graphText:'#0E0E0E'},
};
