import http from 'k6/http';
import {check,fail} from 'k6';
import {Trend} from 'k6/metrics';
const base='http://electricity_test_app:8000',live=__ENV.TEST_MODE==='live',time=new Trend('settings_mixed_read_ms',true);
export const options={setupTimeout:'120s',scenarios:{pages:{executor:'shared-iterations',vus:live?2:20,iterations:live?4:2400,maxDuration:'3m'}},thresholds:{checks:['rate==1'],http_req_failed:['rate==0'],settings_mixed_read_ms:[live?'p(95)<10000':'p(95)<500'],...(!live?{http_reqs:['count>=9600']}:{} )}};
function params(cookie){return {headers:{'Content-Type':'application/json'},cookies:cookie?{powertrack_access_token:{value:cookie.slice(cookie.indexOf('=')+1),replace:true}}:{},timeout:'30s'};}
export function setup(){
 const meta=http.get(base+'/_test/settings');if(meta.status!==200||!meta.json().isolated)fail('Nonisolated target');
 const accounts=[];
 for(let i=0;i<2;i++){
  const email=`settings-k6-${Date.now()}-${i}@example.com`,password='TestFixturePassword123!';
  const r=http.post(base+'/api/auth/register',JSON.stringify({full_name:'Settings Fixture '+i,email,phone:'08'+String(Date.now()).slice(-7)+i,password}),params(''));if(r.status!==201)fail('Register '+r.status);
  const login=http.post(base+'/api/auth/login',JSON.stringify({identifier:email,password}),params(''));if(login.status!==200)fail('Login '+login.status);
  accounts.push({cookie:'powertrack_access_token='+login.cookies.powertrack_access_token[0].value,id:r.json().user.user_id});
 }
 const account=accounts[0];
 const saved=http.put(base+'/api/settings',JSON.stringify({residence_type:'house',occupants:2,default_unit_price:'8.1234',default_service_charge:'0',monthly_budget:'1500',expected_updated_at:null}),params(account.cookie));
 if(saved.status!==200)fail('Settings save '+saved.status+' '+saved.body);
 const record=saved.json().settings;
 check(saved,{'decimal and explicit zero persisted':r=>Number(r.json().settings.default_unit_price)===8.1234&&Number(r.json().settings.default_service_charge)===0});
 const loaded=http.get(base+'/api/settings',params(account.cookie));check(loaded,{'save visible in summary data':r=>r.status===200&&r.json().settings.updated_at===record.updated_at});
 const empty=http.get(base+'/api/settings',params(accounts[1].cookie));check(empty,{'other account starts without settings':r=>r.status===200&&r.json().settings===null});
 return {accounts,version:record.updated_at};
}
export default function(data){
 const index=__VU%2,account=data.accounts[index];
 for(const path of ['/api/auth/me','/api/settings','/api/history','/api/appliances?billing_month=2026-10','/api/analysis?end_month=2026-10']){
  const response=http.get(base+path,params(account.cookie));time.add(response.timings.duration);
  check(response,{'page succeeds':r=>r.status===200,'account isolation':r=>{
   if(r.status!==200)return false;const body=r.json();
   if(path==='/api/auth/me')return body.user.user_id===account.id;
   if(path==='/api/settings')return index===0?body.settings?.user_id===account.id&&Number(body.settings.monthly_budget)===1500:body.settings===null;
   if(path==='/api/history')return body.total===0;
   if(path.startsWith('/api/analysis'))return body.latest===null&&body.appliances.length===0;
   return body.records.length===0;
  }});
 }
}
export function teardown(data){
 const cookie=data.accounts[0].cookie;
 const updated=http.put(base+'/api/settings',JSON.stringify({residence_type:'apartment',occupants:3,monthly_budget:'0',expected_updated_at:data.version}),params(cookie));
 check(updated,{'update keeps same owner and creation timestamp':r=>r.status===200&&r.json().settings.user_id===data.accounts[0].id&&Number(r.json().settings.monthly_budget)===0});
 const loaded=http.get(base+'/api/settings',params(cookie));check(loaded,{'updated settings immediately visible':r=>r.status===200&&r.json().settings.occupants===3&&r.json().settings.default_unit_price===null});
 if(!live){const a=http.get(base+'/_test/auth-cache').json(),s=http.get(base+'/_test/settings').json();check(a,{'auth source reads bounded':x=>x.source_reads<=6});check(s,{'settings source reads bounded':x=>x.loads<=4&&x.writes===2});console.log(`Source reads: auth=${a.source_reads}, settings=${s.loads}`);}
 for(const account of data.accounts)http.post(base+'/api/auth/logout',null,params(account.cookie));
}
