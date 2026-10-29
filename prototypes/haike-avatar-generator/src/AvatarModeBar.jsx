import {AvatarTemplatePicker} from './AvatarTemplatePicker.jsx';
export function AvatarModeBar() {
  return <AvatarTemplatePicker templateId="avatar-template3-card-3x4-v001" onChoose={c=>{const q=new URLSearchParams(c.motion?{style:c.motion.style,layout:c.motion.layout}:{template:c.templateId});location.assign('/avatar?'+q.toString());}}/>;
}
