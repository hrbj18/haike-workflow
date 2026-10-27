import assert from 'node:assert/strict';
import test from 'node:test';
import {mountRefinement} from '../web/refinement-widget.js';

class Element {
  constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.disabled=false;this.textContent='';this.style={};}
  append(...children){this.children.push(...children);}
  setAttribute(key,value){this.attributes[key]=value;}
  removeAttribute(key){delete this.attributes[key];}
  remove(){this.removed=true;}
}
const byText=(root,text)=>root.children.find(element=>element.textContent===text);

test('candidate adoption is explicit; source is not silently replaced',async()=>{
  globalThis.document={createElement:tag=>new Element(tag)};
  const container=new Element('div');let submissions=0,adoptions=0;
  const widget=mountRefinement(container,{
    submit:async()=>{submissions++;return{id:'fixture',status:'succeeded'};},
    get:async()=>({id:'fixture',status:'succeeded',config:{preset_version:'test-v1'}}),
    file:async()=>new Blob(['candidate']),onAdopt:async value=>{adoptions++;assert.equal(value.presetVersion,'test-v1');},onOriginal:async()=>{},
  });
  const root=container.children[0],input=root.children[0];
  input.files=[new File(['source'],'fixture.png',{type:'image/png'})];input.onchange();
  assert.equal(submissions,0);
  await byText(root,'确认费用并优化').onclick();
  assert.equal(submissions,1);assert.equal(adoptions,0);
  assert.equal(byText(root,'采用优化图').disabled,false);
  await byText(root,'采用优化图').onclick();assert.equal(adoptions,1);
  widget.destroy();delete globalThis.document;
});

test('late results from an older upload never become the new candidate',async()=>{
  globalThis.document={createElement:tag=>new Element(tag)};
  let release;const delayed=new Promise(resolve=>{release=resolve;});
  const container=new Element('div');
  const widget=mountRefinement(container,{submit:async()=>delayed,get:async()=>{throw new Error('stale poll');},file:async()=>{throw new Error('stale file');},onAdopt:async()=>{},onOriginal:async()=>{}});
  const root=container.children[0],input=root.children[0];
  input.files=[new File(['old'],'old.png')];input.onchange();
  const pending=byText(root,'确认费用并优化').onclick();
  input.files=[new File(['new'],'new.png')];input.onchange();
  release({id:'old-task'});await pending;
  assert.equal(byText(root,'采用优化图').disabled,true);
  assert.equal(byText(root,'确认费用并优化').disabled,false);
  widget.destroy();delete globalThis.document;
});

test('lost submission disables another paid submit',async()=>{
  globalThis.document={createElement:tag=>new Element(tag)};
  const container=new Element('div');let count=0;
  const widget=mountRefinement(container,{submit:async()=>{count++;throw new Error('fixture');},get:async()=>{},file:async()=>{},onAdopt:async()=>{},onOriginal:async()=>{}});
  const root=container.children[0],input=root.children[0];input.files=[new File(['source'],'source.png')];input.onchange();
  await byText(root,'确认费用并优化').onclick();
  assert.equal(count,1);assert.equal(byText(root,'确认费用并优化').disabled,true);
  widget.destroy();delete globalThis.document;
});
