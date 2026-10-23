const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(){this.value='';this.disabled=false;this.listeners={};this.open=false;this.classList={toggle:(key,value)=>{this[key]=value;}};}
 addEventListener(k,v){this.listeners[k]=v;}
 showModal(){this.open=true;}
 close(){this.open=false;}
 focus(){this.focused=true;}
 select(){this.selected=true;}
}
function boot({remaining=0,clipboard=true,throttle=false}={}){
 const nodes=new Map(),events={},requests=[],copies=[],timers=[];
 for(const match of fs.readFileSync('Front__end/advice/advice.html','utf8').matchAll(/id="([^"]+)"/g))nodes.set(match[1],new Element());
 nodes.get('adviceMonth').value='2026-10';
 const document={getElementById:id=>{assert(nodes.has(id),id);return nodes.get(id);},addEventListener:(k,v)=>v()};
 const window={addEventListener:(k,v)=>events[k]=v,location:{replace:()=>{}}};
 vm.runInNewContext(fs.readFileSync('Front__end/advice/export_prompt.js','utf8'),{document,window,Date,JSON,Number,Math,clearTimeout:()=>{},setTimeout:callback=>{timers.push(callback);return timers.length;},navigator:clipboard?{clipboard:{writeText:async text=>copies.push(text)}}:{},fetch:async(url,options)=>{
  requests.push({url,options});return {status:throttle?429:200,ok:!throttle,headers:{get:()=> '60'},json:async()=>throttle?{detail:'รอหนึ่งนาที'}:{prompt:'ข้อมูลจริง 850 บาท\n<script>ไม่ใช่ HTML</script>',month:'2026-10',generated_at:'2026-10-22T10:00:00+07:00',rate_limit:{remaining:4,retry_after:0}}};
 }});
 events['advice:state']({detail:{ready:true,pending:false,remaining,month:'2026-10'}});
 return {nodes,requests,copies,timers};
}
test('export is available and prominent with exhausted chat; preview before local copy',async()=>{
 const {nodes,requests,copies}=boot();assert.equal(nodes.get('generatePrompt').disabled,false);assert.equal(nodes.get('exportCard')['is-exhausted'],true);
 await nodes.get('generatePrompt').listeners.click();assert.equal(nodes.get('promptDialog').open,true);assert.equal(copies.length,0);
 assert.equal(requests[0].url,'/api/advice/export-prompt');assert.deepEqual(JSON.parse(requests[0].options.body),{month:'2026-10'});
 assert.match(nodes.get('exportPromptText').value,/850 บาท/);
 await nodes.get('copyPrompt').listeners.click();assert.equal(copies[0],nodes.get('exportPromptText').value);assert.equal(requests.length,1);
 await nodes.get('copyPrompt').listeners.click();assert.equal(requests.length,1);
 nodes.get('closePrompt').listeners.click();assert.equal(nodes.get('promptDialog').open,false);
});
test('minute throttling has its own wait and no stale text; clipboard fallback selects text',async()=>{
 const throttled=boot({remaining:5,throttle:true});await throttled.nodes.get('generatePrompt').listeners.click();assert.equal(throttled.nodes.get('generatePrompt').disabled,true);assert.equal(throttled.nodes.get('copyPrompt').disabled,true);assert.match(throttled.nodes.get('exportRate').textContent,/60 วินาที/);
 const manual=boot({clipboard:false});await manual.nodes.get('generatePrompt').listeners.click();await manual.nodes.get('copyPrompt').listeners.click();assert.equal(manual.nodes.get('exportPromptText').selected,true);assert.match(manual.nodes.get('promptStatus').textContent,/Ctrl\+C/);
});
