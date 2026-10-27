import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const require=createRequire(import.meta.url);
const result=await build({entryPoints:[fileURLToPath(new URL('../src/QuoteBilling.jsx',import.meta.url))],bundle:true,write:false,format:'cjs',platform:'node',packages:'external',jsx:'automatic'});
const compiled={exports:{}};new Function('require','module','exports',result.outputFiles[0].text)(require,compiled,compiled.exports);
const {QuoteBilling}=compiled.exports;
test('内部费用确认如实展示服务商、采购模型和估算说明',()=>{
 const text=renderToStaticMarkup(React.createElement(QuoteBilling,{internal:true,quote:{estimate_only:true,provider:'百炼',provider_model:'cosyvoice-v3-flash',billing_note:'采购估算，不是硬封顶。'}}));
 for(const phrase of ['百炼','cosyvoice-v3-flash','采购估算，不是硬封顶。'])assert.ok(text.includes(phrase));
 assert.ok(!text.includes('冻结额度'));assert.ok(!text.includes('云余额'));
 const fallback=renderToStaticMarkup(React.createElement(QuoteBilling,{internal:true,quote:{}}));
 assert.match(fallback,/实际结算以供应商账单为准/);
 assert.equal(renderToStaticMarkup(React.createElement(QuoteBilling,{quote:{max_charge_micros:1}})),'');
});
