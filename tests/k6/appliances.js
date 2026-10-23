import http from 'k6/http';
import {check,fail,sleep} from 'k6';
import {Trend} from 'k6/metrics';
const base='http://electricity_test_app:8000', live=__ENV.TEST_MODE==='live';
const readTime=new Trend('appliance_read_ms',true);
export const options={scenarios:live ? {reads:{executor:'shared-iterations',vus:2,iterations:4}} : {reads:{executor:'constant-vus',vus:20,duration:'15s'}},thresholds:{checks:['rate==1'],http_req_failed:['rate==0'],appliance_read_ms:[live?'p(95)<10000':'p(95)<500']}};
function params(cookie,key){return {headers:{'Content-Type':'application/json','Cookie':cookie,...(key?{'Idempotency-Key':key}:{})},timeout:'30s'};}
const payload={billing_month:'2026-10',appliance_name:'K6 Fixture',category:'other',category_custom:'เครื่องทดสอบ',quantity:2,average_power_w:'200',hours_per_day:'8',days_used:20,source:'measured'};
export function setup(){
 const meta=http.get(base+'/_test/appliances');if(meta.status!==200 || !meta.json().isolated)fail('Non-isolated target');
 const email='appliance-k6-'+Date.now()+'@example.com',password='TestFixturePassword123!';
 const registration=http.post(base+'/api/auth/register',JSON.stringify({full_name:'K6 Appliance Fixture',email,phone:'089'+String(Date.now()).slice(-7),password}),params(''));
 if(registration.status!==201)fail('Registration '+registration.status);
 if(live)sleep(3);
 const login=http.post(base+'/api/auth/login',JSON.stringify({identifier:email,password}),params(''));
 if(login.status!==200)fail('Login '+login.status);
 if(live)sleep(3);
 const cookie='powertrack_access_token='+login.cookies.powertrack_access_token[0].value;
 const key='12345678-1234-4234-8234-123456789abc';
 const saved=http.post(base+'/api/appliances',JSON.stringify(payload),params(cookie,key));
 if(saved.status!==201)fail('Save failed '+saved.status+' '+saved.body);
 if(live)sleep(3);
 check(saved,{'calculation 64 kWh':r=>Number(r.json().record.estimated_kwh)===64,'custom category':r=>r.json().record.category_custom==='เครื่องทดสอบ'});
 const repeated=http.post(base+'/api/appliances',JSON.stringify(payload),params(cookie,key));
 check(repeated,{'idempotent save':r=>r.status===201 && r.json().record.id===saved.json().record.id});
 if(live)sleep(3);
 const minimal=http.post(base+'/api/appliances',JSON.stringify({billing_month:'2026-10',appliance_name:'Unknown Watts',category:'air_conditioner'}),params(cookie,'22345678-1234-4234-8234-123456789abc'));
 check(minimal,{'optional blank remains unknown':r=>r.status===201 && r.json().record.estimated_kwh===null});
 return {cookie,id:saved.json().record.id};
}
export default function(data){
 const response=http.get(base+'/api/appliances?billing_month=2026-10',params(data.cookie));readTime.add(response.timings.duration);
 check(response,{'saved items visible':r=>r.status===200 && r.json().records.length===2,'saved calculation retained':r=>r.status===200 && r.json().records.some(x=>x.id===data.id && Number(x.estimated_kwh)===64)});
}
export function teardown(data){
 const cancelled=http.post(base+'/api/appliances/'+data.id+'/cancel',JSON.stringify({revision:1}),params(data.cookie,'32345678-1234-4234-8234-123456789abc'));
 check(cancelled,{'soft cancel':r=>r.status===200 && r.json().record.status==='cancelled'});
 const read=http.get(base+'/api/appliances?billing_month=2026-10',params(data.cookie));check(read,{'cancelled item hidden':r=>r.status===200 && r.json().records.length===1});
 const info=http.get(base+'/_test/appliances').json();if(!live)check(info,{'only three storage commits':x=>x.writes===3,'warm reads avoid source IO':x=>x.loads<6});
 http.post(base+'/api/auth/logout',null,params(data.cookie));
}
