import http from 'k6/http';
import {check,fail} from 'k6';
import {Trend} from 'k6/metrics';
const base='http://electricity_test_app:8000',live=__ENV.TEST_MODE==='live',time=new Trend('mixed_page_ms',true);
export const options={setupTimeout:'120s',scenarios:{pages:live?{executor:'shared-iterations',vus:2,iterations:4}:{executor:'constant-vus',vus:20,duration:'15s'}},thresholds:{checks:['rate==1'],http_req_failed:['rate==0'],mixed_page_ms:[live?'p(95)<10000':'p(95)<500']}};
function params(cookie){return {headers:{'Content-Type':'application/json'},cookies:cookie?{powertrack_access_token:{value:cookie.slice(cookie.indexOf('=')+1),replace:true}}:{},timeout:'30s'};}
export function setup(){
 const meta=http.get(base+'/_test/auth-cache');if(meta.status!==200 || !meta.json().isolated)fail('Nonisolated target');
 const accounts=[];
 for(let i=0;i<2;i++){
  const email=`auth-cache-${Date.now()}-${i}@example.com`,password='TestFixturePassword123!';
  const r=http.post(base+'/api/auth/register',JSON.stringify({full_name:'Quota Test '+i,email,phone:'08'+String(Date.now()).slice(-7)+i,password}),params(''));
  if(r.status!==201)fail('Register '+r.status);
  const login=http.post(base+'/api/auth/login',JSON.stringify({identifier:email,password}),params(''));
  if(login.status!==200)fail('Login '+login.status);
  accounts.push({cookie:'powertrack_access_token='+login.cookies.powertrack_access_token[0].value,id:r.json().user.user_id});
 }
 const saved=http.post(base+'/api/electricity',JSON.stringify({billing_month:'2026-10',previous_meter:0,current_meter:125,unit_price:'8',service_charge:'50'}),params(accounts[0].cookie));
 if(saved.status!==201)fail('Seed '+saved.status);
 return {accounts};
}
export default function(data){
 const index=__VU%2,account=data.accounts[index];
 for(const path of ['/api/auth/me','/api/history','/api/appliances?billing_month=2026-10','/api/analysis?end_month=2026-10']){
  const response=http.get(base+path,params(account.cookie));time.add(response.timings.duration);
  check(response,{'page succeeds':r=>r.status===200,'account isolation':r=>{
   if(r.status!==200)return false;const body=r.json();
   if(path==='/api/auth/me')return body.user.user_id===account.id;
   if(path==='/api/history')return body.total===(index===0?1:0);
   if(path.startsWith('/api/analysis'))return index===0?!!body.latest && Number(body.latest.total_cost)===1050:body.latest===null;
   return body.records.length===0;
  }});
 }
}
export function teardown(data){
 if(!live){const info=http.get(base+'/_test/auth-cache').json();check(info,{'auth source reads coalesced':x=>x.source_reads<=4});console.log('Auth source reads='+info.source_reads);}
 for(const account of data.accounts)http.post(base+'/api/auth/logout',null,params(account.cookie));
}
