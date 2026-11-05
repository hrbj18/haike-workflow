/* Haike-owned implementation from observable reference frames/public inputs.
 * No MotionGit protected source was read. Fidelity is pending actual comparison.
 */
const INPUT=window.INPUT, SFX=[];
const W=1080,H=1920,stage=document.getElementById('stage');
const C={light:{bg:'#f8f9f3',ink:'#171b18',accent:'#376cea'},paper:{bg:'#f3f2e7',ink:'#243128',accent:'#329b78'},console:{bg:'#101416',ink:'#edf3f5',accent:'#97bfff'},poster:{bg:'#eae8db',ink:'#090909',accent:'#efff16'}}[INPUT.style];
// Self-authored candidate constrained by sparse observed states, not recovered native curves.
const QUOTE_V3=Object.freeze({
 reveal:Object.freeze({firstClear:.55,firstFade:.18,laterStart:.22,laterSpread:.38,laterClearDuration:.80,blur:6}),
 author:Object.freeze({lightStart:1.40,lightFade:.16,consoleStart:1.02,consoleFade:.36,opacity:.65}),
 glyph:Object.freeze({font:'Geist,NotoSource,sans-serif',size:180,openX:210,closeX:880,lightOpenY:265,consoleOpenY:266,closeY:910})
});
function quoteGlyph(node,style,closing=false){
 if(style!=='light'&&style!=='console')return;
 const p=QUOTE_V3.glyph;node.style.fontFamily=p.font;node.style.fontSize=p.size+'px';
 node.style.left=(closing?p.closeX:p.openX)+'px';
 node.style.top=(closing?p.closeY:style==='light'?p.lightOpenY:p.consoleOpenY)+'px';
 node.dataset.quoteRole=closing?'close':'open';
}
const clamp=x=>Math.max(0,Math.min(1,x)), out=x=>1-Math.pow(1-clamp(x),3), lerp=(a,b,t)=>a+(b-a)*t;
function el(parent,tag='div',css='',text){const e=document.createElement(tag);e.style.cssText='position:absolute;box-sizing:border-box;'+css;if(text!==undefined)e.textContent=text;parent.appendChild(e);return e;}
function label(parent,text,x,y,size=56,width=936,align='left',weight=800){return el(parent,'div',`left:${x}px;top:${y}px;width:${width}px;font:${weight} ${size}px/1.2 ${INPUT.style==='poster'?'Geist,NotoSource':'NotoSource'},sans-serif;letter-spacing:-1px;text-align:${align};white-space:pre-wrap;color:${C.ink}`,text);}
function media(parent,key,css){const box=el(parent,'div',css+';overflow:hidden;background:#15171b');const img=el(box,'img','inset:0;width:100%;height:100%;object-fit:contain');const data=INPUT.media[key];if(!data)throw Error('Missing bound real media: '+key);img.src=data.image||data.directory+'/f_00001.jpg';return {box,img,data};}
function frameMedia(item,t,live=true){const d=item.data;if(d.image)return;if(!live){const next=d.directory+'/f_00001.jpg';if(item.img.getAttribute('src')!==next)item.img.src=next;return;}const at=t-d.timelineStart;
 if(at<-.001||at>d.duration+.001)throw Error('Visible media outside verified source window: '+item.data.directory+' at '+t);
 const frame=Math.floor(Math.max(0,at)*d.fps+1e-6);if(frame>=d.frames)throw Error('No tail freeze permitted');const next=d.directory+'/f_'+String(frame+1).padStart(5,'0')+'.jpg';if(item.img.getAttribute('src')!==next)item.img.src=next;}
function tail(row,t){if(row.t1===INPUT.duration)return 1;return t<row.t1?1-.9*out((t-(row.t1-.4))/.4):.1*(1-out((t-row.t1)/.12));}
function phase(row,t){const intro=row.t0===0?out((t+.0167)/.34):.04+.96*Math.pow(clamp((t-row.t0+.1)/.36),2);return intro*tail(row,t);}
function cueIndex(row,t){return Math.max(0,row.cues.filter(at=>at<=t+.0001).length-1);}
function arrowShape(parent,x,y,size,color){const box=el(parent,'div',`left:${x}px;top:${y}px;width:${size}px;height:${size}px;filter:drop-shadow(0 0 16px ${color}66)`);box.innerHTML=`<svg viewBox="0 0 200 200" width="100%" height="100%"><path d="M100 15V170M35 105L100 172L165 105" stroke="${color}" stroke-width="27" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>`;return box;}
const backdrop=el(stage,'div','inset:0');
const layers=[],avatars=[];
for(const row of INPUT.segments){
 const layer=el(stage,'div','inset:0;opacity:0;overflow:hidden'),p=row.props,style=INPUT.style, poster=style==='poster';
 let update=()=>{};
 if(row.control==='title'||row.control==='kinetic'){
   const centered=style==='paper',left=centered?72:72;
   const lines=p.lines||[p.line1,p.line2];
   const kicker=label(layer,p.kicker||'',left,262,21,936,centered?'center':'left',500);kicker.style.letterSpacing='5px';kicker.style.color=poster?'#fff':C.ink;kicker.style.opacity='.65';
   const first=label(layer,lines[0]||'',left,300,poster?172:120,936,centered?'center':'left',800);
   const second=label(layer,lines[1]||'',poster?66:left,poster?465:442,poster?172:120,936,centered?'center':'left',800);
   second.style.color=poster?'#efff16':C.accent;
   if(style==='console'){second.style.background='linear-gradient(100deg,#81d4f6,#aa91ff 72%)';second.style.backgroundClip='text';second.style.color='transparent';second.style.filter='drop-shadow(0 5px 20px #6a9fd522)';}
   if(poster){first.style.left='66px';first.style.width='max-content';first.style.color='#f0ecdc';second.style.webkitTextStroke='2px #efff16';second.style.color='transparent';}
   const underline=centered?el(layer,'div',`left:72px;top:596px;width:936px;height:2px;background:${C.accent};opacity:.45`):null;
   const cursor=style==='light'?el(layer,'div',`left:540px;top:310px;width:26px;height:142px;background:${C.accent}`):null;
   update=t=>{const secondAt=row.cues[1]??row.t0+.6;const a=out((t-secondAt)/.42);second.style.opacity=String(a);second.style.filter=`blur(${(1-a)*22}px)`;second.style.transform=`translateY(${(1-a)*24}px)`;if(poster){first.style.top=(297.5-2.4*(t-row.t0))+'px';second.style.top=(465-2.4*(t-row.t0))+'px';}if(underline)underline.style.transform=`scaleX(${a})`;if(cursor)cursor.style.opacity=t<row.t0+.8?'1':'0';};
 }else if(row.control==='steps'){
   label(layer,p.title||'',style==='light'?96:90,style==='poster'?246:530,64,900,'left',850);
   const list=p.steps,items=[];
   const track=el(layer,'div',`left:${poster?173:118}px;top:${poster?520:690}px;width:2px;height:0;background:${poster?'#4b2be8':C.accent};opacity:.6`);
   list.forEach((text,i)=>{const y=poster?470+i*400:650+i*140;
     const circle=el(layer,'div',`left:${poster?150:96}px;top:${y+32}px;width:46px;height:46px;border:2px solid ${C.accent};border-radius:50%;opacity:.22`);
     const box=el(layer,'div',`left:${poster?260:180}px;top:${y}px;width:${poster?750:800}px;height:${poster?170:110}px;`);
     if(style==='paper'){box.style.cssText+='background:#faf9ee;border:1px solid #26342818;box-shadow:3px 16px 20px #26342815;';el(box,'div','right:0;bottom:0;border:12px solid transparent;border-right-color:#d8dacb;border-bottom-color:#d8dacb');}
     if(style==='console')box.style.cssText+='width:800px;height:110px;background:#20262b;border:1px solid #88a2ae33;border-radius:16px;box-shadow:0 0 45px #3c8dcb0c;';
     if(poster)box.style.cssText+='border:2px solid #96968b;background:#eae8db;box-shadow:12px 12px #a8a79e;';
     const number=label(box,String(i+1).padStart(2,'0'),24,poster?22:40,20,54,'left',450);number.style.letterSpacing='4px';
     const textEl=label(box,text,poster?25:84,poster?75:22,poster?56:52,poster?680:700,'left',800);
     items.push({circle,box,textEl,number});});
   update=t=>{const n=cueIndex(row,t);track.style.height=(n*(poster?400:140))+'px';items.forEach((item,i)=>{const a=out((t-(row.cues[i]??row.t0+.2*i)+.18)/.32);item.box.style.opacity=String(style==='light'?1:.18+.82*a*(style==='console'&&i<n?.48:1));item.textEl.style.opacity=String(a);item.number.style.opacity=String(.2+.8*a);item.box.style.transform=`translateX(${(1-a)*30}px)`;item.circle.style.opacity=String(i<=n?.6:.15);if(poster){const focus=out((t-(row.cues[n]??row.t0))/.35),current=i===n?focus:0;item.box.style.left=(290-40*current)+'px';item.box.style.width=lerp(675,750,current)+'px';item.box.style.opacity=String(i<n?.5:i===n?1:.4);item.box.style.borderColor=i===n?'#111':'#96968b';item.box.style.boxShadow='12px 12px '+(i===n?'#111':'#a8a79e');item.circle.style.opacity='1';item.circle.style.background=i<n?'#4b2be8':i===n?'#d9f5ff':'#a9adb0';item.circle.style.borderColor=i<=n?'#111':'#929896';}});};
 }else if(row.control==='media'){
   const browser=el(layer,'div',`left:${poster?54:72}px;top:${poster?310:330}px;width:${poster?972:936}px;height:570px;border-radius:14px;overflow:hidden;background:#15171b;box-shadow:0 42px 60px #0005`);
   el(browser,'div','left:0;right:0;top:0;height:42px;background:linear-gradient(90deg,#30343d,#252a32)');
   ['#ff666e','#f3c742','#42d454'].forEach((color,i)=>el(browser,'div',`left:${18+i*22}px;top:15px;width:12px;height:12px;background:${color};border-radius:50%`));
   label(browser,p.title||'',96,9,19,780,'left',500).style.color='#edf1f5';
   const item=media(browser,row.mediaKey,'left:0;top:42px;width:100%;height:528px');if(poster)item.img.style.objectFit='cover';
   const scan=el(item.box,'div',`left:0;top:0;width:100%;height:3px;background:${poster?'#efff16':C.accent};box-shadow:0 0 20px ${C.accent}`);
   update=t=>{frameMedia(item,t,t>=item.data.timelineStart);const u=out((t-row.t0)/.55);browser.style.transform=`perspective(1500px) rotateY(${row.variant==='tilt'?lerp(-8,0,u):0}deg) rotateZ(${row.variant==='tilt'?lerp(-3,0,u):0}deg) scale(${row.variant==='zoom'?lerp(.92,1,u):1})`;scan.style.top=(clamp((t-row.t0)/1.4)*100)+'%';scan.style.opacity=row.variant==='scan'&&t<row.t0+1.5?'1':'0';};
 }else if(row.control==='device'){
   el(layer,'div',`left:500px;top:278px;width:80px;height:5px;background:${C.accent};box-shadow:0 0 16px ${C.accent}`);
   label(layer,p.title||'',72,310,60,936,'center',850);label(layer,p.sub||'',72,398,34,936,'center',450).style.opacity='.7';
   const monitor=row.variant==='monitor',tablet=row.variant==='tablet';
   const x=monitor?90:tablet?200:310,y=monitor?630:tablet?530:495,w=monitor?900:tablet?680:460,h=monitor?540:tablet?900:940;
   const body=el(layer,'div',`left:${x}px;top:${y}px;width:${w}px;height:${h}px;background:linear-gradient(135deg,#40434a,#171a20);border:8px solid #353940;border-radius:${monitor?12:tablet?42:90}px;box-shadow:0 35px 65px #0006`);
   const item=media(body,row.mediaKey,`left:${monitor?10:20}px;top:${monitor?10:tablet?20:90}px;width:${w-(monitor?36:56)}px;height:${h-(monitor?36:tablet?56:170)}px;border-radius:${monitor?2:tablet?24:12}px`);
   if(!monitor&&!tablet)el(body,'div','left:50%;top:30px;transform:translateX(-50%);width:210px;height:36px;background:#000;border-radius:25px');
   if(monitor){el(layer,'div','left:490px;top:1170px;width:100px;height:110px;background:linear-gradient(90deg,#20242a,#3b424a,#1b1f26)');el(layer,'div','left:370px;top:1270px;width:340px;height:28px;background:#292f36;border-radius:20px;box-shadow:0 12px 18px #0004');}
   update=t=>{frameMedia(item,t,t>=item.data.timelineStart);body.style.transform=`perspective(2000px) rotateY(${lerp(-8,0,out((t-row.t0)/.7))}deg)`;};
 }else if(row.control==='gallery'||row.control==='polaroid'){
   const film=row.control==='polaroid';if(!film)label(layer,p.title||'',72,poster?290:270,58,936,style==='paper'?'left':'center',850);
   if(film)el(layer,'div','left:0;right:0;top:480px;height:540px;background:#111;box-shadow:0 30px 50px #0005');
   if(style==='console'||poster&&!film){el(layer,'div',`left:190px;top:${poster?650:520}px;width:700px;height:700px;border:2px solid ${poster?'#fff7':'#8dceea77'};border-radius:50%;background:radial-gradient(ellipse at 50% 80%,${poster?'#d7d0ff66':'#317b981c'},transparent 70%);box-shadow:0 100px 180px ${poster?'#e1d4ff66':'#51799524'}`);}
   const cards=p.items.map((item,i)=>{const x=film?i*650:style==='paper'?[72,550,310][i]:540, y=film?480:style==='paper'?[460,460,910][i]:poster?940:650;
     const m=media(layer,row.mediaKeys[i],`left:${x}px;top:${y}px;width:${film?640:style==='paper'?460:590}px;height:${film?540:style==='paper'?370:430}px;border-radius:${film||style==='light'?0:18}px;box-shadow:0 28px 48px #0005;border:${style==='light'?'10px solid #f5f4e9':film?'34px solid #111':'2px solid #ffffff13'}`);
     if(poster)m.img.style.objectFit='cover';
     if(style==='paper')m.caption=label(layer,item.caption||'',x,y+380,25,460,'center',450);
     if(film){m.box.style.borderTopWidth='48px';m.box.style.borderBottomWidth='48px';m.holes=[];for(const at of [495,985]){const holes=el(layer,'div',`left:${x}px;top:${at}px;width:640px;height:20px;display:flex;justify-content:space-around;pointer-events:none`);for(let n=0;n<18;n++)el(holes,'i','position:relative;width:15px;height:20px;background:#eee');m.holes.push(holes);}}
     return m;});
   const caption=label(layer,'',72,film?1060:1400,film?56:44,936,'center',750);if(style==='paper')caption.style.display='none';
   update=t=>{const focus=Math.min(cards.length-1,cueIndex(row,t)),travel=focus?focus-1+out((t-row.cues[focus])/.6):0;caption.textContent=p.items[focus]?.caption||'';
     cards.forEach((item,i)=>{const live=t>=item.data.timelineStart&&t<item.data.timelineStart+item.data.duration;frameMedia(item,t,live);
       if(film){const d=((i-travel+4.5)%3)-1.5;item.box.style.left=(200+d*650)+'px';item.holes.forEach(holes=>holes.style.left=item.box.style.left);}
       else if(style!=='paper'){const d=((i-travel+4.5)%3)-1.5;item.box.style.left=(540+d*(poster?420:290))+'px';item.box.style.transform=`translateX(-50%) perspective(1600px) rotateY(${row.variant==='carousel'?d*-28:0}deg) rotateZ(${row.variant==='stack'?d*8-4:0}deg) scale(${lerp(1,.82,clamp(Math.abs(d)))})`;item.box.style.zIndex=String(10-Math.abs(i-focus));item.box.style.opacity=String(lerp(1,style==='light'?.85:.48,clamp(Math.abs(d))));}
       else{const appear=out((t-row.cues[i]+.15)/.35);item.box.style.opacity=String(appear*(i===focus?1:.72));item.caption.style.opacity=String(appear*.6);item.box.style.borderColor=i===focus?C.accent:'#ffffff22';item.box.style.transform=`scale(${i===focus?1.06:1})`;}});};
 }else if(row.control==='quote'){
   const card=row.variant==='card',top=poster?360:style==='console'?380:400;
   if(card)el(layer,'div',`left:${poster?90:110}px;top:${top}px;width:${poster?900:860}px;height:${poster?1000:style==='console'?960:1040}px;border-radius:${style==='light'?22:style==='console'?18:2}px;background:${style==='console'?'linear-gradient(#25292d,#1b1e22)':style==='paper'?'#faf9ef':poster?C.bg:'#fff'};border:${poster?'2px solid #101010':style==='console'?'1px solid #b1c1cd44':style==='paper'?'1px solid #56644c22':'none'};box-shadow:${poster?'12px 12px #111':style==='console'?'0 24px 60px #0005':'0 18px 35px #2634280c'}`);
   const mark=label(layer,poster?'❝':'“',poster?65:210,top-135,180,760,'left',900);mark.style.color=poster?'#8b7bd2':C.accent;mark.style.opacity=poster?'1':'.4';quoteGlyph(mark,style);
   if(card){const close=label(layer,poster?'❞':'”',poster?900:880,top+510,180,200,'left',900);close.style.color=poster?'#8b7bd2':C.accent;close.style.opacity=poster?'1':'.4';quoteGlyph(close,style,true);}
   const staged=style==='light'&&row.variant==='reveal';
   const body=label(layer,staged?'':p.text||'',poster?148:160,card?top+(poster?72:70):480,poster?78:76,760,'left',800);body.style.textWrap=p.lines?'wrap':'balance';body.style.lineHeight='1.45';if(poster){body.style.letterSpacing='1px';if(p.lines)body.textContent=p.lines.join('\n');}
   let groups=[];
   if(staged){
     if(!Array.isArray(p.reveal_groups)||!p.reveal_groups.length||p.reveal_groups.join('')!==p.text)throw Error('Missing or invalid prepared quote groups');
     body.dataset.quoteBody='staged';
     groups=p.reveal_groups.map((text,i)=>{const n=el(body,'span','position:relative;display:inline-block;vertical-align:top;white-space:pre;opacity:0',text);n.dataset.quoteGroup=String(i);return n;});
   }
   const author=label(layer,'— '+(p.who||''),poster?150:160,card?top+(style==='console'?840:930):1330,28,760,'left',450);author.dataset.quoteAuthor='true';
   const delayed=staged||style==='console'&&card;author.style.opacity=delayed?'0':'.65';if(delayed)author.style.visibility='hidden';
   update=t=>{const elapsed=t-(row.cues[0]??row.t0),a=out(elapsed/.9);
     if(staged){
       body.style.opacity='1';body.style.filter='none';
       groups.forEach((node,i)=>{const start=i===0?0:QUOTE_V3.reveal.laterStart+QUOTE_V3.reveal.laterSpread*i/Math.max(1,groups.length-1);
         const clear=clamp((elapsed-start)/(i===0?QUOTE_V3.reveal.firstClear:QUOTE_V3.reveal.laterClearDuration));
         node.style.opacity=String(clamp((elapsed-start)/QUOTE_V3.reveal.firstFade));node.style.filter=`blur(${QUOTE_V3.reveal.blur*(1-clear)}px)`;});
     }else if(row.variant==='type'){body.textContent=Array.from(p.text||'').slice(0,Math.floor(Math.max(0,elapsed)*8+.25)).join('');author.style.opacity=String(.65*out((Math.max(0,elapsed)-Array.from(p.text||'').length/8-.5)/.35));}
     else{body.style.opacity=String(.3+.7*a);body.style.filter=`blur(${(1-a)*5}px)`;if(style==='paper'||poster)author.style.opacity=String(.65*out((t-row.t0-1.8)/.35));}
     if(delayed){const start=staged?QUOTE_V3.author.lightStart:QUOTE_V3.author.consoleStart,fade=staged?QUOTE_V3.author.lightFade:QUOTE_V3.author.consoleFade;
       const alpha=QUOTE_V3.author.opacity*out((elapsed-start)/fade);author.style.opacity=String(alpha);author.style.visibility=alpha>0?'visible':'hidden';}
   };
 }else if(row.control==='cta'){
   const paper=style==='paper',light=style==='light';
   label(layer,p.kicker||'',72,paper?550:light?350:poster?560:220,21,936,'center',500).style.opacity='.65';
   const button=light?el(layer,'div',`left:210px;top:390px;width:660px;height:160px;background:linear-gradient(120deg,#6f88ff,${C.accent});border-radius:100px;box-shadow:0 0 80px #456de755`):null;
   const text=label(layer,p.text||'',72,paper?610:light?420:poster?625:280,light?92:poster?128:136,936,'center',800);text.style.color=light?'#111':style==='console'?'#fff':C.ink;
   label(layer,p.sub||'',72,paper?790:light?600:poster?800:460,42,936,'center',500).style.opacity='.7';
   const arrow=paper?el(layer,'div','left:485px;top:200px;width:110px;height:260px;background:#283b35;border-radius:80px;box-shadow:0 22px 45px #172d3244'):light?null:arrowShape(layer,440,poster?900:550,200,poster?'#e70013':'#86d1f8');
   if(paper){el(arrow,'div','left:20px;top:20px;width:70px;height:70px;border-radius:50%;background:radial-gradient(circle at 40% 35%,#eaffea,#84c5ab 65%,#41866b);box-shadow:0 0 45px #b2f6d9');label(arrow,'⌃\n⌃',24,95,62,65,'center',700).style.color='#329b78';}
   const smallArrows=[];if(!light&&!paper)for(let i=0;i<3;i++)smallArrows.push(arrowShape(layer,515,(poster?1200:800)+i*70,50,poster?'#e70013':'#86d1f8'));
   const pointer=light?el(layer,'div','left:700px;top:430px;width:65px;height:65px;transform:rotate(-15deg)'):null;
   if(pointer)pointer.innerHTML='<svg viewBox="0 0 64 64" width="100%" height="100%"><path d="M10 5L51 38L32 42L23 60Z" fill="white" stroke="#151a22" stroke-width="4"/></svg>';
   const ring=light?el(layer,'div',`left:620px;top:360px;width:240px;height:240px;border:3px solid ${C.accent};border-radius:50%`):null;
   update=t=>{const a=out((t-row.t0-.12)/.7);text.style.opacity=String(a);if(button){button.style.transform=`scale(${lerp(.45,1,a)})`;text.style.transform=`scale(${lerp(.45,1,a)})`;}if(arrow)arrow.style.transform=`translateY(${Math.sin((t-row.t0)*3)*12}px)`;
     smallArrows.forEach((item,i)=>item.style.opacity=String(.25+.75*(.5+.5*Math.sin((t-row.t0)*3-i))));
     if(pointer){const clicked=out((t-(row.cues[1]??row.t0+2))/.3);pointer.style.opacity=String(clicked);ring.style.opacity=String(clicked*.5);ring.style.transform=`scale(${1+.15*Math.sin((t-row.t0)*3)})`;}};
 }else throw Error('Unsupported implemented control: '+row.control);
 if(row.presenter==='card'){
   const avatarLayer=el(stage,'div','inset:0;display:none;z-index:8;pointer-events:none');
   const paper=style==='paper',avatar=media(avatarLayer,row.presenterMediaKey,`left:${paper?240:style==='console'?240:280}px;top:${paper?650:style==='console'?654:750}px;width:${paper||style==='console'?600:520}px;height:${paper||style==='console'?756:656}px;border-radius:${style==='console'?2:28}px;box-shadow:0 30px 60px #0004;background:#15171b`);
   avatar.img.style.objectFit='cover';avatar.img.style.objectPosition='50% 36%';
   if(!paper){avatar.img.style.transform='scale(1.4)';avatar.img.style.transformOrigin='50.5% 0';}
   el(avatar.box,'div','left:18px;top:16px;padding:6px 12px;font:500 18px/1 NotoSource,sans-serif;color:#fff;background:#344a5288;border-radius:20px',INPUT.presenter?.badge||'AI数字人讲述');
   avatars.push({row,layer:avatarLayer,media:avatar});
 }
 layers.push({row,layer,update});
 row.cues.forEach((at,i)=>SFX.push({type:i?'tick':'whoosh',t:at,eventId:row.id+'.'+i,sceneInstanceId:row.id,soundFamily:INPUT.style==='paper'?'paper':INPUT.style==='console'?'instrument':INPUT.style==='poster'?'kinetic':'performance',source:'independently authored observed-control event'}));
}
const timer=el(stage,'div','right:78px;top:96px;z-index:20;font:400 28px/1 GeistMono,NotoSource,monospace;color:#949a9b;text-shadow:0 1px 0 #fff');
const fixed=INPUT.style==='poster'?label(stage,INPUT.captions[0]?.text||'',130,92,28,820,'center',450):null;
const posterDashes=INPUT.style==='poster'?el(stage,'div','left:0;right:0;bottom:145px;height:6px;background:repeating-linear-gradient(90deg,#75806a22 0 90px,transparent 90px 192px)'):null;
const subtitle=el(stage,'div','left:65px;right:65px;bottom:198px;z-index:20;text-align:center;pointer-events:none');
const subtitleText=el(subtitle,'span','position:relative;display:inline-block;max-width:950px;white-space:pre-wrap;font:650 44px/1.35 NotoSource,sans-serif;padding:5px 22px;border-radius:10px');
subtitleText.style.background=INPUT.style==='poster'?'transparent':'#0009';subtitleText.style.color=INPUT.style==='poster'?'#090909':'#fff';
window.END=INPUT.frames/INPUT.fps;window.MACRO_PLAN={fps:INPUT.fps};
window.renderAt=t=>{
 let active=INPUT.segments.find(row=>t>=row.t0&&t<row.t1)||INPUT.segments.at(-1);
 backdrop.style.background=INPUT.style==='poster'?(active.control==='kinetic'?'#df0014':active.control==='cta'?'#d8ff36':C.bg):C.bg;
 if(INPUT.style==='light'||INPUT.style==='console'){backdrop.style.backgroundImage=`linear-gradient(${INPUT.style==='console'?'#89d2ff0e':'#43514215'} 1px,transparent 1px),linear-gradient(90deg,${INPUT.style==='console'?'#89d2ff0e':'#43514215'} 1px,transparent 1px)`;backdrop.style.backgroundSize=INPUT.style==='console'?'160px 1800px':'240px 240px';backdrop.style.backgroundPosition=INPUT.style==='console'?'95px 0':'0 0';}
 for(const item of layers){const end=['media','device','gallery','polaroid'].includes(item.row.control)?item.row.t1:Math.min(INPUT.duration,item.row.t1+.12);const visible=t>=Math.max(0,item.row.t0-.4)&&t<end;item.layer.style.display=visible?'block':'none';if(visible){const a=phase(item.row,t);item.layer.style.opacity=String(a);item.layer.style.filter=`blur(${(1-a)*18}px)`;item.update(t);}}
 for(const item of avatars){const d=item.media.data,visible=t>=d.timelineStart&&t<d.timelineStart+d.duration;item.layer.style.display=visible?'block':'none';if(visible){const intro=item.row.t0===0?out((t-.18)/.4):out((t-d.timelineStart+.0167)/.4);const a=intro*tail(item.row,t);item.layer.style.opacity=String(a);item.layer.style.filter=`blur(${(1-a)*18}px)`;
   if(item.row.control==='cta'&&INPUT.style!=='light'){const paper=INPUT.style==='paper',u=out((t-item.row.t0-.1)/.6),b=item.media.box;b.style.left=lerp(240,paper?330:370,u)+'px';b.style.top=lerp(paper?650:654,paper?980:1050,u)+'px';b.style.width=lerp(600,paper?420:340,u)+'px';b.style.height=lerp(756,paper?420:340,u)+'px';b.style.borderRadius=lerp(paper?28:2,paper?28:999,u)+'px';}
   frameMedia(item.media,t);}}
 const caption=INPUT.captions.find(c=>t>=c.s&&t<c.e);subtitleText.textContent=caption?.text||'';subtitleText.style.display=caption?'inline-block':'none';
 if(INPUT.style==='poster'){subtitleText.style.color=active.control==='kinetic'?'#f2ecdc':'#090909';posterDashes.style.opacity=active.control==='kinetic'?'.3':'1';}
 timer.textContent=String(Math.floor(t/60)).padStart(2,'0')+':'+String(Math.floor(t)%60).padStart(2,'0');
 if(fixed){fixed.style.color=active.control==='kinetic'?'#f2ecdc':'#101010';fixed.style.opacity=['kinetic','polaroid','gallery'].includes(active.control)?String(tail(active,t)): '0';}
};
window.READY=document.fonts.ready.then(()=>window.renderAt(0));
