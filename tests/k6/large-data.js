import http from 'k6/http';
import {check,fail} from 'k6';
import {Trend} from 'k6/metrics';
const base='http://electricity_test_app:8000',latency=new Trend('large_data_read_ms',true);
const featureTimes=['dashboard','history','appliances','analysis','advice_context','reports','auth','chat_replay'].map(n=>new Trend('large_'+n+'_ms',true));
export const options={setupTimeout:'180s',scenarios:{all_features:{executor:'shared-iterations',vus:50,iterations:1800,maxDuration:'4m'}},thresholds:{checks:['rate==1'],http_req_failed:['rate==0'],large_data_read_ms:['p(95)<1500'],http_reqs:['count>=12000']}};
const uuid=()=> 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{const n=Math.floor(Math.random()*16);return(c==='x'?n:(n&3|8)).toString(16);});
function params(token,status=200){return {headers:{'Content-Type':'application/json'},cookies:token?{powertrack_access_token:{value:token,replace:true}}:{},timeout:'60s',responseCallback:http.expectedStatuses(status)};}
function request(a,method,path,body,status=200){const r=http.request(method,base+path,body?JSON.stringify(body):null,params(a?.token,status));if(!check(r,{'setup status correct':r=>r.status===status}))fail(method+' '+path+' status='+r.status);return r;}
export function setup(){const seeded=request(null,'POST','/_test/large-seed',{}).json();if(!seeded.isolated||seeded.accounts.length!==21)fail('Unsafe target');const accounts=seeded.accounts;
 for(const a of accounts){const login=request(null,'POST','/api/auth/login',{identifier:a.email,password:'LargeFixturePassword123!'});a.token=login.cookies.powertrack_access_token[0].value;
  a.body={question:'ช่วยวิเคราะห์ภาพรวมค่าไฟและจุดที่ควรเริ่มประหยัด',topic:'overview',month:'2026-05',request_id:uuid(),conversation_id:uuid()};
  for(let n=0;n<5;n++){const r=request(a,'POST','/api/advice/chat',n===0?a.body:{...a.body,request_id:uuid()});check(r,{'quota remains owner-specific':r=>r.json().quota.remaining===4-n,'AI context includes complete totals and bounded details':r=>{const x=r.json();return a.populated?x.context.facts.device_totals.items===24&&x.context.facts.devices.length===20&&Number(x.context.facts.bill.total_cost)===2330+8*a.index:x.context.facts.bill===null&&x.context.facts.devices.length===0&&x.answer.in_scope===false&&['insufficient_data','cache'].includes(x.source);}});if(n===0)a.report_id=r.json().report_candidate_id;}
  request(a,'POST','/api/advice/chat',{...a.body,request_id:uuid()},429);
  if(a.report_id)request(a,'POST','/api/advice/reports',{report_id:a.report_id});
 }
 request(accounts[1],'GET','/api/advice/reports/'+accounts[0].report_id,null,404);
 const exp=request(accounts[0],'POST','/api/advice/export-prompt',{month:'2026-05'}).json();check(exp,{'export identifies 24 total and 20 supplied details':x=>x.prompt.includes('24')&&x.prompt.includes('20')&&x.prompt.includes('247.55')});
 return {accounts};}
export default function(data){const a=data.accounts[(__VU+__ITER)%data.accounts.length],paths=['/api/dashboard?month=2026-05','/api/history?page=4','/api/appliances?billing_month=2026-05','/api/analysis?end_month=2026-05&months=12','/api/advice/context?month=2026-05','/api/advice/reports','/api/auth/me','/api/advice/chat'];
 for(let j=0;j<paths.length;j++){const r=j===7?http.post(base+paths[j],JSON.stringify(a.body),params(a.token)):http.get(base+paths[j],params(a.token));latency.add(r.timings.duration);featureTimes[j].add(r.timings.duration);check(r,{'all feature reads succeed':r=>r.status===200,'all feature ownership and math correct':r=>{if(r.status!==200)return false;const x=r.json();if(j===0)return a.populated?Number(x.total_cost)===2330+8*a.index&&x.average_bill_count===6:x.total_cost===null;
 if(j===1)return x.total===(a.populated?24:0)&&x.records.every(row=>row.user_id===a.id)&&(a.populated?x.page===4:true);
 if(j===2)return x.records.length===(a.populated?24:0)&&x.records.every(row=>a.usage_ids.includes(row.id));
 if(j===3)return a.populated?x.appliance_summary.items===24&&x.appliance_summary.unknown_items===2&&Number(x.appliance_summary.estimated_kwh)===247.55&&Number(x.latest.total_cost)===2330+8*a.index:x.latest===null&&x.appliances.length===0;
 if(j===4)return x.quota.remaining===0&&(a.populated?x.facts.device_totals.items===24&&x.facts.devices.length===20&&Number(x.facts.budget.monthly_budget)===2000+10*a.index:x.facts.bill===null);
 if(j===5)return x.total===(a.populated?1:0)&&x.items.every(row=>row.report_id===a.report_id);
 if(j===6)return x.user.user_id===a.id;
 return x.replayed===true&&x.quota.remaining===0&&(a.populated?Number(x.context.facts.bill.total_cost)===2330+8*a.index:x.answer.in_scope===false);}});}}
export function teardown(data){const stats=request(null,'GET','/_test/large-stats').json(),auth=request(null,'GET','/_test/auth-cache').json();check(stats,{'large fixture retained all rows':s=>s.bills===480&&s.masters===480&&s.usage===480,'no extra model calls on read load':s=>s.provider_calls===20,'report writes only when selected':s=>s.report_writes===20,'source reads coalesced':s=>s.bill_reads<=15&&s.appliance_reads<=15&&s.settings_reads<=15});check(auth,{'auth reads coalesced':s=>s.source_reads<=30});console.log(JSON.stringify({...stats,auth_reads:auth.source_reads}));for(const a of data.accounts)request(a,'POST','/api/auth/logout');}
