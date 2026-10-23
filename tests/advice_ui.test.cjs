const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(){this.children=[];this.listeners={};this.value='';this.style={};this.dataset={};this.hidden=false;}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=children;}
 addEventListener(k,v){this.listeners[k]=v;}
 remove(){}
}
const facts={month:'2026-10',bill:{total_cost:'850',units_used:100},budget:{monthly_budget:'700',gap_baht:'150',reduction_percent:'17.65'},household:{residence_type:'house',occupants:2},device_totals:{items:1,estimated_items:1},devices:[{name:'<script>alert(1)</script>',category:'computer',estimated_kwh:'64',average_power_w:'200',hours_per_day:'8',days_used:20}],scenarios:[],missing_data:[],notes:['เครื่องใช้เป็นค่าประมาณ']};
async function boot({fail=false,remaining=5}={}){
 const nodes=new Map(),requests=[];
 for(const match of fs.readFileSync('Front__end/advice/advice.html','utf8').matchAll(/id="([^"]+)"/g))nodes.set(match[1],new Element());
 const buttons=['overview','devices','budget','plan'].map(topic=>{const e=new Element();e.dataset.topic=topic;return e;});
 const document={getElementById:id=>{assert(nodes.has(id),id);return nodes.get(id);},createElement:()=>new Element(),querySelectorAll:()=>buttons,addEventListener:(k,v)=>v()};
 let count=remaining;
 vm.runInNewContext(fs.readFileSync('Front__end/advice/advice.js','utf8'),{document,window:{location:{replace:()=>{}}},crypto:{randomUUID:()=>String(Math.random())},Date,encodeURIComponent,fetch:async(url,options={})=>{
  requests.push({url,options});const auth=url==='/api/auth/me',chat=url==='/api/advice/chat';
  if(chat)count--;
  return {status:auth?200:fail?503:200,ok:auth||!fail,headers:{get:()=>null},json:async()=>auth?{user:{role:'user',full_name:'Fixture'}}:fail?{detail:'ลองใหม่'}:chat?{answer:{in_scope:true,summary:'ปิดคอมเมื่อเลิกใช้',actions:[{title:'เริ่มจากเวลาเปิดทิ้ง',instruction:'ปิดเครื่องหลังเลิกงาน',reason:'ลดการใช้ที่ไม่จำเป็น',scenario_id:null}],assumptions:[],missing_data:[]},context:{facts},quota:{remaining:count,limit:5,retry_after:3600},source:'gemini',model:'fixture',generated_at:new Date().toISOString()}: {facts,quota:{remaining:count,limit:5,retry_after:3600}}};
 }});
 for(let i=0;i<6;i++)await new Promise(setImmediate);
 return {nodes,buttons,requests};
}
test('real API context loads, quick topic sends canonical request and chart labels remain text',async()=>{
 const {nodes,buttons,requests}=await boot();assert.equal(nodes.get('adviceMonth').value,'2026-10');assert.equal(nodes.get('sendMessage').disabled,false);
 await buttons[2].listeners.click();for(let i=0;i<6;i++)await new Promise(setImmediate);
 const body=JSON.parse(requests.find(r=>r.url==='/api/advice/chat').options.body);
 assert.equal(body.topic,'budget');assert.equal(body.month,'2026-10');assert.equal(body.question,'อยากลดค่าไฟให้ถึงงบ ควรทำอย่างไร?');assert(body.request_id&&body.conversation_id);
 assert.match(nodes.get('quotaLabel').textContent,/เหลือ 4/);
 const output=JSON.stringify(nodes.get('conversation').children);assert.match(output,/<script>alert\(1\)<\/script>/);assert.match(output,/ปิดคอมเมื่อเลิกใช้/);
 nodes.get('newChat').listeners.click();assert.match(nodes.get('quotaLabel').textContent,/เหลือ 4/);
});
test('quota exhaustion and read errors prevent sending, with explicit reload',async()=>{
 const empty=await boot({remaining:0});assert.equal(empty.nodes.get('sendMessage').disabled,true);assert.match(empty.nodes.get('quotaLabel').textContent,/60 นาที/);
 const failed=await boot({fail:true});assert.equal(failed.nodes.get('sendMessage').disabled,true);assert.match(failed.nodes.get('contextStatus').textContent,/โหลดข้อมูลล่าสุด/);assert.equal(failed.nodes.get('reloadContext').disabled,false);
});
test('custom questions keep account charts inside a collapsed evidence disclosure',async()=>{
 const {nodes,requests}=await boot();nodes.get('chatInput').value='ควรเปิดแอร์กี่องศา';
 await nodes.get('chatForm').listeners.submit({preventDefault(){}});
 for(let i=0;i<6;i++)await new Promise(setImmediate);
 const body=JSON.parse(requests.find(r=>r.url==='/api/advice/chat').options.body);
 assert.equal(body.topic,'custom');
 const messages=nodes.get('conversation').children;
 const details=messages.flatMap(n=>n.children||[]).find(n=>n.className==='answer-evidence');
 assert(details);assert(!details.open);assert.match(JSON.stringify(details),/ดูตัวเลขและกราฟประกอบ/);
});
test('specific watt questions display recorded numeric facts without model-generated quantities',async()=>{
 const {nodes}=await boot();nodes.get('chatInput').value='คอมใช้ไฟกี่วัตต์';
 await nodes.get('chatForm').listeners.submit({preventDefault(){}});for(let i=0;i<6;i++)await new Promise(setImmediate);
 const output=JSON.stringify(nodes.get('conversation').children);assert.match(output,/200 W/);assert.match(output,/64 kWh/);assert.match(output,/กำลังไฟเฉลี่ยต่อเครื่อง/);
});
