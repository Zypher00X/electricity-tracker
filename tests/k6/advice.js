import http from 'k6/http';
import {check,fail} from 'k6';
import {Trend} from 'k6/metrics';
const base='http://electricity_test_app:8000',live=__ENV.TEST_MODE==='live',latency=new Trend('advice_mixed_ms',true);
export const options={setupTimeout:'180s',scenarios:{pages:{executor:'shared-iterations',vus:live?2:20,iterations:live?4:2400,maxDuration:'3m'}},thresholds:{checks:['rate==1'],http_req_failed:['rate==0'],advice_mixed_ms:[live?'p(95)<10000':'p(95)<500'],...(!live?{http_reqs:['count>=9600']}:{} )}};
const uuid=()=> 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{const n=Math.floor(Math.random()*16);return (c==='x'?n:(n&3|8)).toString(16);});
function params(token,expected=null){return {headers:{'Content-Type':'application/json'},cookies:token?{powertrack_access_token:{value:token,replace:true}}:{},timeout:'45s',...(expected?{responseCallback:http.expectedStatuses(...expected)}:{})};}
function ask(account,body){return http.post(base+'/api/advice/chat',JSON.stringify(body),params(account.token));}
export function setup(){
 const meta=http.get(base+'/_test/advice');if(meta.status!==200||!meta.json().isolated||meta.json().provider!=='load-test-stub-not-gemini')fail('Nonisolated provider');
 const accounts=[];
 for(let i=0;i<2;i++){
  const email=`advice-k6-${Date.now()}-${i}@example.com`,password='TestFixturePassword123!';
  const r=http.post(base+'/api/auth/register',JSON.stringify({full_name:'Advice Fixture '+i,email,phone:'08'+String(Date.now()).slice(-7)+i,password}),params(''));if(r.status!==201)fail('Register '+r.status);
  const login=http.post(base+'/api/auth/login',JSON.stringify({identifier:email,password}),params(''));if(login.status!==200)fail('Login '+login.status);
  accounts.push({token:login.cookies.powertrack_access_token[0].value,id:r.json().user.user_id});
 }
 const a=accounts[0];
 const bill=http.post(base+'/api/electricity',JSON.stringify({billing_month:'2026-10',previous_meter:0,current_meter:200,unit_price:'8',service_charge:'0'}),params(a.token));if(bill.status!==201)fail('Bill '+bill.status);
 const setting=http.put(base+'/api/settings',JSON.stringify({residence_type:'apartment',occupants:2,monthly_budget:'1400',expected_updated_at:null}),params(a.token));if(setting.status!==200)fail('Settings '+setting.status);
 for(let index=0;index<2;index++){
  const account=accounts[index];const body={question:'ช่วยวิเคราะห์ภาพรวมค่าไฟและจุดที่ควรเริ่มประหยัด',topic:'overview',month:'2026-10',conversation_id:uuid(),request_id:uuid()};account.body=body;
  for(let n=0;n<5;n++){
   const response=ask(account,n===0?body:{...body,request_id:uuid()});
   if(!check(response,{'five questions admitted':r=>r.status===200,'quota counts cache answers':r=>r.status===200&&r.json().quota.remaining===4-n}))fail('Advice '+response.status);
  }
  const sixth=http.post(base+'/api/advice/chat',JSON.stringify({...body,request_id:uuid()}),params(account.token,[429]));
  check(sixth,{'sixth rejected with retry':r=>r.status===429&&Number(r.headers['Retry-After'])>0});
 }
 return {accounts};
}
export default function(data){
 const i=__VU%2,a=data.accounts[i];
 const reads=[()=>http.get(base+'/api/auth/me',params(a.token)),()=>http.get(base+'/api/advice/context?month=2026-10',params(a.token)),()=>ask(a,a.body),()=>http.get(base+'/api/analysis?end_month=2026-10',params(a.token)),()=>http.get(base+'/api/history',params(a.token))];
 for(let j=0;j<reads.length;j++){
  const r=reads[j]();latency.add(r.timings.duration);check(r,{'mixed request succeeds':r=>r.status===200,'owner data isolated':r=>{
   if(r.status!==200)return false;const body=r.json();if(j===0)return body.user.user_id===a.id;
   if(j===1||j===2){const f=j===1?body.facts:body.context.facts;return i===0?Number(f.bill?.total_cost)===1600&&Number(f.budget.monthly_budget)===1400:f.bill===null&&f.devices.length===0;}
   if(j===3)return i===0?Number(body.latest?.total_cost)===1600:body.latest===null;
   return body.total===(i===0?1:0);
  }});
 }
}
export function teardown(data){
 const meta=http.get(base+'/_test/advice').json();check(meta,{'only one provider call for repeated questions':x=>x.provider_calls===1});console.log('Stub provider calls='+meta.provider_calls);
 if(!live){const auth=http.get(base+'/_test/auth-cache').json();check(auth,{'auth source reads bounded':x=>x.source_reads<=8});console.log('Auth source reads='+auth.source_reads);}
 for(const account of data.accounts)http.post(base+'/api/auth/logout',null,params(account.token));
}
