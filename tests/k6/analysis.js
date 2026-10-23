import http from 'k6/http';
import {check,fail,sleep} from 'k6';
import {Trend} from 'k6/metrics';
import {setup as setupAppliances} from './appliances.js';
const base='http://electricity_test_app:8000',live=__ENV.TEST_MODE==='live';
const time=new Trend('analysis_read_ms',true);
export const options={setupTimeout:'180s',teardownTimeout:'90s',scenarios:live?{reads:{executor:'shared-iterations',vus:2,iterations:4}}:{reads:{executor:'constant-vus',vus:20,duration:'15s'}},thresholds:{checks:['rate==1'],http_req_failed:['rate==0'],analysis_read_ms:[live?'p(95)<10000':'p(95)<500']}};
function params(cookie){return {headers:{Cookie:cookie,'Content-Type':'application/json'},timeout:'30s'};}
export function setup(){
 const data=setupAppliances();
 for(const [month,units] of [['2026-09',100],['2026-10',125]]){
  if(live)sleep(3);
  const response=http.post(base+'/api/electricity',JSON.stringify({billing_month:month,previous_meter:0,current_meter:units,unit_price:'8',service_charge:'50'}),params(data.cookie));
  if(response.status!==201)fail('Bill fixture failed '+response.status);
 }
 if(live)sleep(3);
 const read=http.get(base+'/api/analysis?months=3&end_month=2026-10',params(data.cookie));
 check(read,{'new bill and usage visible together':r=>r.status===200 && Number(r.json().latest.total_cost)===1050 && Number(r.json().appliance_summary.estimated_kwh)===64});
 return data;
}
export default function(data){
 if(live)sleep(4);
 const months=[3,6,12][__ITER%3];const response=http.get(base+`/api/analysis?months=${months}&end_month=2026-10`,params(data.cookie));time.add(response.timings.duration);
 check(response,{
  'analysis succeeds':r=>r.status===200,
  'billing calculation and comparison':r=>r.status===200 && Number(r.json().latest.total_cost)===1050 && Number(r.json().latest.cost_change_percent)===23.5,
  'missing months remain null':r=>r.status===200 && r.json().series.length===months && r.json().series[0].units_used===null,
  'appliance total and coverage':r=>r.status===200 && Number(r.json().appliance_summary.estimated_kwh)===64 && r.json().appliance_summary.unknown_items===1,
 });
}
export function teardown(data){
 if(live)sleep(4);
 const cancelled=http.post(base+'/api/appliances/'+data.id+'/cancel',JSON.stringify({revision:1}),{...params(data.cookie),headers:{...params(data.cookie).headers,'Idempotency-Key':'32345678-1234-4234-8234-123456789abc'}});
 check(cancelled,{'cancel succeeds':r=>r.status===200});
 if(live)sleep(4);
 const final=http.get(base+'/api/analysis?end_month=2026-10',params(data.cookie));
 check(final,{'analysis sees cancellation immediately':r=>r.status===200 && r.json().appliance_summary.items===1 && r.json().appliance_summary.estimated_kwh===null});
 if(!live){const a=http.get(base+'/_test/appliances').json(),e=http.get(base+'/_test/info').json();check(a,{'appliance source reads bounded':x=>x.loads<=4 && x.writes===3});check(e,{'bill source reads bounded':x=>x.repository_loads<=3 && x.repository_writes===2});}
 if(live)sleep(4);
 http.post(base+'/api/auth/logout',null,params(data.cookie));
}
