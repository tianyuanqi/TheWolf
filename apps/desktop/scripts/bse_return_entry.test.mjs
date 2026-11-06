import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from '../node_modules/typescript/lib/typescript.js';
const source=readFileSync(new URL('../src/browserHost.ts',import.meta.url),'utf8');
const js=ts.transpile(source.replace(/^import .*;\n/gm,''),{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}).replace(/export /g,'');
test('fresh root binding never replaces an explicit identity or bypasses descriptor validation',async()=>{
 const run='11111111-1111-4111-8111-111111111111',instance='22222222-2222-4222-8222-222222222222';
 async function probe(hash='',extra={}) {
  let replacements=0; const location={pathname:'/',search:'',hash,...extra.location};
  const descriptor={connection_mode:'managed',run_id:run,expected_instance_id:instance};
  const context={URLSearchParams,DOMException,location,history:{replaceState(_a,_b,url){replacements++;location.hash=url;}},
   parseDescriptor(value){if(extra.badDescriptor)throw Error('version mismatch');return value;},
   fetch:async()=>({ok:true,headers:new Map([['content-type','application/json']]),json:async()=>descriptor})};
  const ctx=vm.createContext(context);vm.runInContext(js,ctx);
  const signal={aborted:!!extra.aborted};let error;
  try{await ctx.connectionDescriptor(signal);}catch(e){error=e.message;}
  return {location,replacements,error};
 }
 const fresh=await probe();assert.equal(fresh.replacements,1);assert.ok(fresh.location.hash.includes(run));assert.equal(fresh.error,undefined);
 const good=await probe(fresh.location.hash);assert.equal(good.replacements,0);assert.equal(good.error,undefined);
 for(const hash of ['#wolf-run=old','#wolf-instance='+instance,'#wolf-run='+run+'&wolf-run='+run+'&wolf-instance='+instance,'#overview','#wolf-run='+run+'&wolf-instance=old']){
  const result=await probe(hash);assert.equal(result.replacements,0);assert.match(result.error,/身份不符/);
 }
 for(const extra of [{location:{search:'?x=1'}},{location:{pathname:'/other'}}])assert.match((await probe('',extra)).error,/身份不符/);
 assert.equal((await probe('',{badDescriptor:true})).replacements,0);
 assert.equal((await probe('',{aborted:true})).replacements,0);
});
