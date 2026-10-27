import type {LabProps} from './types';

// Optional revisions are deliberately scoped to the three 4:5 tests.
// Legacy defaults remain literal, including secondary structures and mount fills.
export const PALETTE_TEMPLATE = {'blue-beige':7,'cyan-charcoal':8,'black-pink':9} as const;
export const activePalette = (p:LabProps) => {
  const variant=p.paletteVariant;
  if(variant===undefined||variant==='default')return undefined;
  if(!(variant in PALETTE_TEMPLATE)||PALETTE_TEMPLATE[variant]!==p.templateNumber||p.ratio!=='4x5'){
    throw new Error('Palette variant must match template 07, 08 or 09 and use 4x5');
  }
  return variant;
};

const DEFAULT_07={night:'#0E1820',light:'#F6EDDE',copper:'#C99867',depth:'#273B45',
  leftWing:'#17252D',rightWing:'#091116',sourceBorder:'#46515A',shadow:'#00000055',
  curtain:'#111C23',captionBg:'#15232D',mount:'#0e1820'};
const BLUE_BEIGE={night:'#0C3967',light:'#EAD0B0',copper:'#EAD0B0',depth:'#EAD0B047',
  leftWing:'#EAD0B00A',rightWing:'#00000018',sourceBorder:'#EAD0B080',shadow:'#00000055',
  curtain:'#0C3967',captionBg:'#0C3967',mount:'#0C3967'};
export const palette07=(p:LabProps)=>activePalette(p)==='blue-beige'?BLUE_BEIGE:DEFAULT_07;

const DEFAULT_08={paper:'#F3DDD2',ink:'#173D42',coral:'#CC624C',fold:'#B84F3C',light:'#FFF6ED',
  title:'#173D42',caption:'#FFF6ED',captionBg:'#173D42',captionAccent:'#FFF6ED',
  mount:'#fff6ed',titlePanel:undefined as string|undefined};
const CYAN_CHARCOAL={paper:'#202425',ink:'#28CCC9',coral:'#28CCC9',fold:'#28CCC980',light:'#28CCC933',
  title:'#28CCC9',caption:'#202425',captionBg:'#28CCC9',captionAccent:'#202425',
  mount:'#202425',titlePanel:'#202425'};
export const palette08=(p:LabProps)=>activePalette(p)==='cyan-charcoal'?CYAN_CHARCOAL:DEFAULT_08;

const DEFAULT_09={paper:'#F4F3EE',ink:'#151515',ambient:'#D0CFCA',ambientEnd:'#DAD9D4',
  caption:'#FFFFFF',captionBg:'#151515',captionAccent:'#FFFFFF',mount:'#f4f3ee'};
const BLACK_PINK={paper:'#0E0E0E',ink:'#FD7B99',ambient:'#FD7B9929',ambientEnd:'#FD7B9938',
  caption:'#0E0E0E',captionBg:'#FD7B99',captionAccent:'#0E0E0E',mount:'#0E0E0E'};
export const palette09=(p:LabProps)=>activePalette(p)==='black-pink'?BLACK_PINK:DEFAULT_09;

export const paletteMount=(p:LabProps,legacy:string):string=>{
  switch(activePalette(p)){
    case 'blue-beige':return BLUE_BEIGE.mount;
    case 'cyan-charcoal':return CYAN_CHARCOAL.mount;
    case 'black-pink':return BLACK_PINK.mount;
    default:return legacy;
  }
};
