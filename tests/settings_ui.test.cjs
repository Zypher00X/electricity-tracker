const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
async function boot(fail=false){
 const nodes=new Map();
 for(const match of fs.readFileSync('Front__end/settings/settings.html','utf8').matchAll(/id="([^"]+)"/g))nodes.set(match[1],{value:'',validity:{valid:true},listeners:{},addEventListener(k,v){this.listeners[k]=v;}});
 const submit={},form=nodes.get('settingsForm'),requests=[];
 form.querySelector=()=>submit;form.reportValidity=()=>true;
 nodes.get('residenceType').value='unknown';
 let record=null;
 const document={getElementById:id=>{assert(nodes.has(id),id);return nodes.get(id);},querySelectorAll:()=>[],addEventListener:(event,handler)=>handler()};
 vm.runInNewContext(fs.readFileSync('Front__end/settings/settings.js','utf8'),{document,window:{location:{replace:()=>{}},addEventListener:()=>{}},fetch:async(url,options={})=>{
  requests.push({url,options});
  if(url==='/api/auth/me')return {status:200,ok:true,json:async()=>({user:{role:'user',full_name:'Fixture'}})};
  if(fail)return {status:503,ok:false,json:async()=>({detail:'Unavailable'})};
  if(options.method==='PUT')record={...JSON.parse(options.body),updated_at:'version-1'};
  return {status:200,ok:true,json:async()=>({settings:record})};
 }});
 for(let i=0;i<4;i++)await new Promise(setImmediate);
 return {nodes,requests,submit};
}
test('loads empty settings, saves optional blanks and explicit zero, renders server summary',async()=>{
 const {nodes,requests,submit}=await boot();assert.equal(submit.disabled,false);
 assert.equal(nodes.get('summaryBudget').textContent,'ยังไม่กำหนดงบ');
 nodes.get('residenceType').value='house';nodes.get('occupants').value='2';nodes.get('monthlyBudget').value='0';
 await nodes.get('settingsForm').listeners.submit({preventDefault(){}});
 const payload=JSON.parse(requests.find(r=>r.options.method==='PUT').options.body);
 assert.equal(payload.expected_updated_at,null);assert.equal(payload.default_unit_price,null);assert.equal(payload.monthly_budget,'0');
 assert.equal(nodes.get('summaryBudget').textContent,'0.00 บาท');assert.equal(nodes.get('summaryOccupants').textContent,'2 คน');
 assert.equal(nodes.get('settingsSuccess').hidden,false);
 nodes.get('occupants').value='9';nodes.get('resetSettings').listeners.click();assert.equal(nodes.get('occupants').value,2);
});
test('read failure displays retry and prevents saving unloaded settings',async()=>{
 const {nodes,submit}=await boot(true);assert.equal(nodes.get('settingsRetry').hidden,false);
 assert.equal(nodes.get('settingsError').hidden,false);assert.equal(submit.disabled,true);
});
