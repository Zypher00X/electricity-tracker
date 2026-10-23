import http from 'k6/http';
import {check,sleep} from 'k6';
import {Rate,Trend} from 'k6/metrics';
const expected=new Rate('security_expected_responses'),latency=new Trend('security_read_ms');
const base=__ENV.BASE_URL||'http://electricity_test_app:8000';
export const options={scenarios:{spike:{executor:'ramping-vus',startVUs:0,stages:[{duration:'10s',target:10},{duration:'15s',target:50},{duration:'15s',target:100},{duration:'15s',target:100},{duration:'10s',target:0}],gracefulRampDown:'10s'}},thresholds:{checks:['rate==1'],security_expected_responses:['rate==1'],security_read_ms:['p(95)<2500']}};
export function setup(){
 const r=http.post(base+'/api/auth/login',JSON.stringify({identifier:'large-fixture-0@example.com',password:'LargeFixturePassword123!'}),{headers:{'Content-Type':'application/json'}});
 check(r,{'setup login succeeds':x=>x.status===200});if(r.status!==200)throw Error('fixture login unavailable');
 return {cookie:r.cookies.powertrack_access_token[0].value};
}
export default function(data){
 const headers={Cookie:'powertrack_access_token='+data.cookie};
 const paths=['/api/auth/me','/api/dashboard?month=2026-05','/api/history?year=2026&page=1','/api/analysis?end_month=2026-05','/api/advice/context?month=2026-05'];
 const r=http.get(base+paths[__ITER%paths.length],{headers});latency.add(r.timings.duration);expected.add(r.status===200);
 check(r,{'authenticated spike reads succeed':x=>x.status===200});sleep(0.25);
}
