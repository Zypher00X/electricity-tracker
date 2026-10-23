import http from 'k6/http';
import {check,fail} from 'k6';
import {Trend} from 'k6/metrics';
import {setup as adviceSetup,teardown as adviceTeardown} from './advice.js';
const base='http://electricity_test_app:8000',live=__ENV.TEST_MODE==='live',latency=new Trend('history_mixed_ms',true);
export const options={setupTimeout:'180s',scenarios:{pages:{executor:'shared-iterations',vus:live?2:20,iterations:live?4:2400,maxDuration:'2m'}},thresholds:{checks:['rate==1'],http_req_failed:['rate==0'],history_mixed_ms:[live?'p(95)<10000':'p(95)<500'],...(!live?{http_reqs:['count>=9600']}:{} )}};
const uuid=()=> 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{const n=Math.floor(Math.random()*16);return(c==='x'?n:(n&3|8)).toString(16);});
function params(token,status=200){return {headers:{'Content-Type':'application/json'},cookies:{powertrack_access_token:{value:token,replace:true}},timeout:'45s',responseCallback:http.expectedStatuses(status)};}
function call(token,method,path,body,status=200){const r=http.request(method,base+path,body?JSON.stringify(body):null,params(token,status));if(!check(r,{'setup mutation result':r=>r.status===status}))fail(method+' '+path+' '+r.status+' '+r.body);return r.json();}
export function setup(){const d=adviceSetup(),a=d.accounts[0],b=d.accounts[1];
 const candidate=call(a.token,'POST','/api/advice/chat',a.body).report_candidate_id;
 call(a.token,'POST','/api/advice/reports',{report_id:candidate});d.reportId=candidate;
 a.record=call(a.token,'GET','/api/history').records[0];
 a.change={billing_month:'2026-10',previous_meter:0,current_meter:350,unit_price:'8',service_charge:'50',expected_updated_at:a.record.updated_at,request_id:uuid()};
 const edited=call(a.token,'PUT','/api/history/'+a.record.record_id,a.change);
 check(edited,{'recalculated bill correct':x=>Number(x.record.total_cost)===2850&&x.record.units_used===350});
 check(call(a.token,'GET','/api/advice/context?month=2026-10'),{'advice cache follows edit':x=>Number(x.facts.bill.total_cost)===2850});
 check(call(a.token,'GET','/api/advice/reports/'+candidate),{'saved AI snapshot remains original':x=>Number(x.input_snapshot.context.facts.bill.total_cost)===1600});
 const spare=call(a.token,'POST','/api/electricity',{billing_month:'2026-09',previous_meter:0,current_meter:100,unit_price:'8',service_charge:'0'},201).record;
 check(call(a.token,'GET','/api/history'),{'comparison recalculated after preceding bill added':x=>Number(x.records[0].change_percent)===256.3});
 call(a.token,'DELETE','/api/history/'+spare.record_id,{expected_updated_at:spare.updated_at,request_id:uuid()});
 check(call(a.token,'GET','/api/history'),{'comparison cleared after preceding bill removed':x=>x.records.length===1&&x.records[0].change_percent===null});
 b.record=call(b.token,'POST','/api/electricity',{billing_month:'2026-10',previous_meter:0,current_meter:50,unit_price:'4',service_charge:'0'},201).record;
 b.change={expected_updated_at:b.record.updated_at,request_id:uuid()};
 call(b.token,'DELETE','/api/history/'+b.record.record_id,b.change);
 check(call(b.token,'GET','/api/advice/context?month=2026-10'),{'deleted bill absent from advice':x=>x.facts.bill===null});
 return d;}
export default function(d){const i=__VU%2,a=d.accounts[i],foreign=d.accounts[1-i];const operations=[
 ()=>http.get(base+'/api/history',params(a.token)),
 ()=>http.get(base+'/api/analysis?end_month=2026-10',params(a.token)),
 ()=>http.get(base+'/api/advice/context?month=2026-10',params(a.token)),
 ()=>http.request(i===0?'PUT':'DELETE',base+'/api/history/'+a.record.record_id,JSON.stringify(a.change),params(a.token)),
 ()=>http.request('DELETE',base+'/api/history/'+foreign.record.record_id,JSON.stringify({expected_updated_at:foreign.record.updated_at,request_id:uuid()}),params(a.token,404))];
 for(let j=0;j<operations.length;j++){const r=operations[j]();latency.add(r.timings.duration);check(r,{'mixed history requests expected':r=>r.status===(j===4?404:200),'fresh owner data and safe replay':r=>{if(j===4)return r.status===404;if(r.status!==200)return false;const x=r.json();if(j===0)return x.total===(i===0?1:0)&&(i===1||Number(x.records[0].total_cost)===2850);if(j===1)return i===0?Number(x.latest?.total_cost)===2850:x.latest===null;if(j===2)return x.quota.remaining===0&&(i===0?Number(x.facts.bill?.total_cost)===2850:x.facts.bill===null);return x.replayed===true&&x.record_id===a.record.record_id;}});}}
export function teardown(d){const counts=http.get(base+'/_test/info').json();if(!live)check(counts,{'mutation retries did not write again':x=>x.repository_writes===6});adviceTeardown(d);}
