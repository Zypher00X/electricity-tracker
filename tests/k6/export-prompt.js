import http from 'k6/http';
import {check,fail} from 'k6';
import {Trend} from 'k6/metrics';
import {setup as adviceSetup,teardown as adviceTeardown} from './advice.js';
const base='http://electricity_test_app:8000',live=__ENV.TEST_MODE==='live',latency=new Trend('export_mixed_ms',true);
export const options={setupTimeout:'180s',scenarios:{pages:{executor:'shared-iterations',vus:live?2:20,iterations:live?4:2400,maxDuration:'50s'}},thresholds:{checks:['rate==1'],http_req_failed:['rate==0'],export_mixed_ms:[live?'p(95)<10000':'p(95)<500'],...(!live?{http_reqs:['count>=9600']}:{} )}};
function params(token,throttled=false){return {headers:{'Content-Type':'application/json'},cookies:{powertrack_access_token:{value:token,replace:true}},timeout:'30s',...(throttled?{responseCallback:http.expectedStatuses(429)}:{})};}
export function setup(){
 const data=adviceSetup(); // Real auth, both users already at their five-question chat limit.
 for(let i=0;i<data.accounts.length;i++){
  const account=data.accounts[i];
  for(let n=0;n<5;n++){
   const r=http.post(base+'/api/advice/export-prompt',JSON.stringify({month:'2026-10'}),params(account.token));
   if(!check(r,{'export works with exhausted chat quota':r=>r.status===200,'exact owner prompt':r=>r.status===200&&(i===0?r.json().prompt.includes('ยอดรวมบิล: 1600 บาท')&&r.json().prompt.includes('งบค่าไฟ: 1400 บาท'):r.json().prompt.includes('ไม่มีบิลในเดือนที่เลือก')&&!r.json().prompt.includes('ยอดรวมบิล: 1600 บาท')),'export minute count':r=>r.status===200&&r.json().rate_limit.remaining===4-n}))fail('Export setup '+r.status);
  }
  const over=http.post(base+'/api/advice/export-prompt','{"month":"2026-10"}',params(account.token,true));check(over,{'sixth export rejected':r=>r.status===429&&Number(r.headers['Retry-After'])>0});
 }
 return data;
}
export default function(data){
 const i=__VU%2,account=data.accounts[i];
 const calls=[()=>http.get(base+'/api/advice/context?month=2026-10',params(account.token)),()=>http.get(base+'/api/history',params(account.token)),()=>http.post(base+'/api/advice/export-prompt','{"month":"2026-10"}',params(account.token,true)),()=>http.get(base+'/api/settings',params(account.token)),()=>http.get(base+'/api/auth/me',params(account.token))];
 for(let j=0;j<calls.length;j++){
  const r=calls[j]();latency.add(r.timings.duration);check(r,{'expected mixed result':r=>r.status===(j===2?429:200),'data and quota isolated':r=>{
   if(j===2)return r.status===429&&Number(r.headers['Retry-After'])>0;
   if(r.status!==200)return false;const d=r.json();
   if(j===0)return d.quota.remaining===0&&(i===0?Number(d.facts.bill?.total_cost)===1600:d.facts.bill===null);
   if(j===1)return d.total===(i===0?1:0);
   if(j===3)return i===0?d.settings?.user_id===account.id:d.settings===null;
   return d.user.user_id===account.id;
  }});
 }
}
export function teardown(data){adviceTeardown(data);}
