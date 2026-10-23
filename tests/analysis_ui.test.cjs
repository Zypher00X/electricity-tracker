const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
class Node {
 constructor(tag='div'){this.tag=tag;this.children=[];this.attrs={};this.style={};this.dataset={};this.value='';this.textContent='';this.listeners={};this.hidden=false;this.classList={add:()=>{},remove:()=>{}};}
 setAttribute(k,v){this.attrs[k]=String(v);}
 getAttribute(k){return this.attrs[k];}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=nodes;this.textContent='';}
 addEventListener(k,v){this.listeners[k]=v;}
 focus(){}
 click(){this.listeners.click?.();}
}
const fixture={has_data:true,start_month:'2026-09',end_month:'2026-11',latest:{month:'2026-11',total_cost:'1050',energy_cost:'1000',service_charge:'50',units_used:125,cost_change_percent:null,units_change_percent:null,previous_month:'2026-10',previous_total_cost:null},highest:{month:'2026-11',units_used:125},lowest:{month:'2026-09',units_used:100},series:[{month:'2026-09',units_used:100,total_cost:'850'},{month:'2026-10',units_used:null,total_cost:null},{month:'2026-11',units_used:125,total_cost:'1050'}],cost_breakdown:[{key:'energy_cost',amount:'1000',percent:'95.2'},{key:'service_charge',amount:'50',percent:'4.8'}],appliance_month:'2026-11',appliances:[{name:'Computer',quantity:2,source:'measured',estimated_kwh:'64'},{name:'Unknown',quantity:1,source:'unknown',estimated_kwh:null}],appliance_summary:{items:2,estimated_items:1,estimated_kwh:'64',meter_kwh:125}};
async function boot(data=fixture,fail=false){
 const nodes=new Map(),html=fs.readFileSync('Front__end/analysis/analysis.html','utf8');
 for(const match of html.matchAll(/id="([^"]+)"/g))nodes.set(match[1],new Node());
 nodes.get('period').value='3';nodes.get('chartMetric').value='units';
 const tabs=['summary','charts','advice'].map(view=>{const n=new Node('button');n.dataset.view=view;n.attrs['aria-controls']=view+'Panel';return n;});
 const document={getElementById:id=>{assert(nodes.has(id),'Missing HTML node '+id);return nodes.get(id);},createElement:tag=>new Node(tag),createElementNS:(ns,tag)=>new Node(tag),createTextNode:text=>({textContent:text}),querySelectorAll:selector=>selector==='[role=tab]'?tabs:[],addEventListener:(event,handler)=>handler()};
 const location={hash:'',replace:()=>{},assign:url=>{location.destination=url;}};
 vm.runInNewContext(fs.readFileSync('Front__end/analysis/analysis.js','utf8'),{document,window:{location,addEventListener:()=>{}},AbortController,URLSearchParams,Intl,console,fetch:async url=>({status:url==='/api/auth/me'?200:fail?503:200,ok:url==='/api/auth/me'||!fail,json:async()=>url==='/api/auth/me'?{user:{full_name:'Fixture',role:'user'}}:data})});
 for(let i=0;i<4;i++)await new Promise(setImmediate);
 nodes.tabs=tabs;nodes.location=location;
 return nodes;
}
test('chart uses API figures, gaps split lines, scales fit and no fake cost slice',async()=>{
 const nodes=await boot();assert.equal(nodes.get('latestCost').textContent,'1,050 บาท');
 const svg=nodes.get('trendChart').children[0];
 assert.equal(svg.children.filter(n=>n.tag==='rect').length,2);
 assert.equal(svg.children.filter(n=>n.tag==='polyline').length,2);
 for(const bar of svg.children.filter(n=>n.tag==='rect'))assert(Number(bar.attrs.y)>=28 && Number(bar.attrs.height)>=0);
 assert.equal(nodes.get('costLegend').children.length,2);
 assert.equal(nodes.get('applianceBars').children[1].children[2].textContent,'ข้อมูลไม่ครบ');
 assert.equal(nodes.get('analysisStatus').hidden,true);
});
test('empty data remains empty and retry is shown for storage failure',async()=>{
 const empty=await boot({...fixture,has_data:false,latest:null,highest:null,lowest:null,series:[],cost_breakdown:[],appliances:[],appliance_summary:{items:0,estimated_items:0,estimated_kwh:null,meter_kwh:null}});
 assert.equal(empty.get('latestCost').textContent,'–');assert.equal(empty.get('trendChart').children[0].tag,'p');assert.equal(empty.get('analysisStatus').hidden,false);
 const failed=await boot(fixture,true);assert.equal(failed.get('analysisRetry').hidden,false);assert.match(failed.get('analysisStatus').textContent,/โหลดข้อมูลวิเคราะห์ไม่สำเร็จ/);
});
test('top navigation opens advice and keeps summary and charts switching locally',async()=>{
 const nodes=await boot();
 nodes.tabs[1].click();assert.equal(nodes.get('chartsPanel').hidden,false);assert.equal(nodes.get('summaryPanel').hidden,true);
 nodes.tabs[0].click();assert.equal(nodes.get('summaryPanel').hidden,false);
 nodes.tabs[2].click();assert.equal(nodes.location.destination,'/frontend/advice/advice.html');
 const html=fs.readFileSync('Front__end/advice/advice.html','utf8');
 assert.match(html,/class="view-navigation"/);
 assert.match(html,/href="\/frontend\/analysis\/analysis.html#summary"/);
 assert.match(html,/href="\/frontend\/analysis\/analysis.html#charts"/);
 assert.match(html,/href="\/frontend\/advice\/advice.html" aria-current="page"/);
});
