import http from 'k6/http';
import {check,fail} from 'k6';
import {Trend} from 'k6/metrics';
import {setup as adviceSetup,teardown as adviceTeardown} from './advice.js';
const base='http://electricity_test_app:8000',live=__ENV.TEST_MODE==='live',latency=new Trend('reports_mixed_ms',true);
export const options={setupTimeout:'180s',scenarios:{pages:{executor:'shared-iterations',vus:live?2:20,iterations:live?4:2400,maxDuration:'2m'}},thresholds:{checks:['rate==1'],http_req_failed:['rate==0'],reports_mixed_ms:[live?'p(95)<10000':'p(95)<500'],...(!live?{http_reqs:['count>=9600']}:{} )}};
function params(token,status=200){return {headers:{'Content-Type':'application/json'},cookies:{powertrack_access_token:{value:token,replace:true}},timeout:'40s',responseCallback:http.expectedStatuses(status)};}
export function setup(){const d=adviceSetup(),a=d.accounts[0];const r=http.post(base+'/api/advice/chat',JSON.stringify(a.body),params(a.token));d.reportId=r.json().report_candidate_id;if(!d.reportId)fail('Missing server candidate');
 const save=http.post(base+'/api/advice/reports',JSON.stringify({report_id:d.reportId}),params(a.token));if(!check(save,{'save with exhausted chat quota':r=>r.status===200&&!r.json().already_saved}))fail('Save '+save.status);
 const detail=http.get(base+'/api/advice/reports/'+d.reportId,params(a.token));if(!check(detail,{'saved snapshot exact owner bill':r=>r.status===200&&Number(r.json().input_snapshot.context.facts.bill.total_cost)===1600&&Number(r.json().input_snapshot.context.facts.budget.monthly_budget)===1400,'original model recorded':r=>r.json().model==='load-test-stub-not-gemini'}))fail('Snapshot');return d;}
export default function(d){const i=__VU%2,a=d.accounts[i];
 const calls=[()=>http.get(base+'/api/advice/reports',params(a.token)),()=>http.get(base+'/api/advice/reports/'+d.reportId,params(a.token,i===0?200:404)),()=>http.post(base+'/api/advice/reports',JSON.stringify({report_id:d.reportId}),params(a.token,i===0?200:404)),()=>http.get(base+'/api/auth/me',params(a.token))];
 for(let j=0;j<calls.length;j++){const r=calls[j]();latency.add(r.timings.duration);check(r,{'expected isolated report result':r=>r.status===((j===1||j===2)&&i===1?404:200),'report data isolated and deduplicated':r=>{
 if(j===0)return r.status===200&&r.json().total===(i===0?1:0);
 if(j===1)return i===0?Number(r.json().input_snapshot.context.facts.bill.total_cost)===1600:r.status===404;
 if(j===2)return i===0?r.json().already_saved===true:r.status===404;
 return r.json().user.user_id===a.id;}});}}
export function teardown(d){const meta=http.get(base+'/_test/reports').json();if(!live)check(meta,{'one Sheets-equivalent write only':m=>m.writes===1,'report source reads coalesced':m=>m.loads<=8});adviceTeardown(d);}
