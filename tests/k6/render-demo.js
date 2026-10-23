import http from 'k6/http';
import {check, sleep} from 'k6';
const base=__ENV.BASE_URL||'http://electricity_test_app:8000';
export const options={vus:8,duration:'30s',thresholds:{checks:['rate==1'],http_req_failed:['rate==0'],http_req_duration:['p(95)<1500']}};
export function setup(){
 const accounts=[];
 for(let i=2;i<10;i++){
  const r=http.post(base+'/api/auth/login',JSON.stringify({identifier:`large-fixture-${i}@example.com`,password:'LargeFixturePassword123!'}),{headers:{'Content-Type':'application/json'}});
  if(r.status!==200)throw Error('fixture login failed');
  accounts.push({index:i,cookie:r.cookies.powertrack_access_token[0].value});
 }
 return {accounts,before:http.get(base+'/_test/large-stats').json()};
}
export default function(data){
 const a=data.accounts[__VU-1];
 const paths=['/api/dashboard?month=2026-05','/api/history?year=2026','/api/appliances?billing_month=2026-05','/api/analysis?end_month=2026-05','/api/advice/context?month=2026-05','/api/settings','/api/advice/reports','/api/auth/me'];
 const j=__ITER%paths.length;
 const r=http.get(base+paths[j],{headers:{Cookie:'powertrack_access_token='+a.cookie}});
 check(r,{'feature response succeeds':x=>x.status===200,'owner-specific bill math':x=>j!==0||(x.status===200&&Number(x.json().total_cost)===2330+8*a.index)});
 if(r.status!==200)console.error('unexpected '+r.status+' '+paths[j]);
 sleep(0.5);
}
export function teardown(data){
 const after=http.get(base+'/_test/large-stats').json();
 check(after,{'no provider calls during reads':x=>x.provider_calls===data.before.provider_calls,'sheet reads coalesced':x=>x.bill_reads-data.before.bill_reads<=3&&x.appliance_reads-data.before.appliance_reads<=3&&x.settings_reads-data.before.settings_reads<=3});
 console.log(JSON.stringify({before:data.before,after}));
}
