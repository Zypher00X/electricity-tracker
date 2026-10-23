import http from 'k6/http';
import {check,fail} from 'k6';
import {Trend} from 'k6/metrics';
const base='http://electricity_test_app:8000',live=__ENV.TEST_MODE==='live',latency=new Trend('dashboard_mixed_ms',true);
export const options={setupTimeout:'180s',scenarios:{pages:{executor:'shared-iterations',vus:live?2:20,iterations:live?4:2400,maxDuration:'2m'}},thresholds:{checks:['rate==1'],http_req_failed:['rate==0'],dashboard_mixed_ms:[live?'p(95)<10000':'p(95)<500'],...(!live?{http_reqs:['count>=9600']}:{} )}};
const uuid=()=> 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{const n=Math.floor(Math.random()*16);return(c==='x'?n:(n&3|8)).toString(16);});
function params(token,status=200){return {headers:{'Content-Type':'application/json'},cookies:token?{powertrack_access_token:{value:token,replace:true}}:{},timeout:'45s',responseCallback:http.expectedStatuses(status)};}
function call(a,method,path,body,status=200){const r=http.request(method,base+path,body?JSON.stringify(body):null,params(a?.token,status));if(r.status!==status)fail(method+' '+path+' '+r.status);return r.json();}
export function setup(){const meta=call(null,'GET','/_test/auth-cache');if(!meta.isolated)fail('Nonisolated target');const accounts=[];
 for(let i=0;i<2;i++){const email=`dashboard-k6-${Date.now()}-${i}@example.com`,password='TestFixturePassword123!';const u=call(null,'POST','/api/auth/register',{full_name:'Dashboard Fixture '+i,email,phone:'08'+String(Date.now()).slice(-7)+i,password},201);const r=http.post(base+'/api/auth/login',JSON.stringify({identifier:email,password}),params(''));if(r.status!==200)fail('Login');accounts.push({id:u.user.user_id,token:r.cookies.powertrack_access_token[0].value});}
 const a=accounts[0];let row;for(const [month,units] of [['2026-05',100],['2026-09',200],['2026-10',300]])row=call(a,'POST','/api/electricity',{billing_month:month,previous_meter:0,current_meter:units,unit_price:'1',service_charge:'0'},201).record;
 const d=call(a,'GET','/api/dashboard');check(d,{'dashboard arithmetic':d=>d.month==='2026-10'&&Number(d.average_cost)===200&&d.average_bill_count===3&&Number(d.cost_change_percent)===50&&d.series.filter(x=>x.total_cost===null).length===3});
 const changed=call(a,'PUT','/api/history/'+row.record_id,{billing_month:'2026-10',previous_meter:0,current_meter:400,unit_price:'1',service_charge:'0',expected_updated_at:row.updated_at,request_id:uuid()}).record;
 check(call(a,'GET','/api/dashboard'),{'dashboard edit cache refreshed':d=>Number(d.total_cost)===400&&Number(d.cost_change_percent)===100});
 call(a,'DELETE','/api/history/'+row.record_id,{expected_updated_at:changed.updated_at,request_id:uuid()});
 check(call(a,'GET','/api/dashboard?month=2026-10'),{'deleted selected month not substituted':d=>d.has_bill===false&&d.total_cost===null});
 check(call(a,'GET','/api/dashboard'),{'default follows latest remaining bill':d=>d.month==='2026-09'&&Number(d.total_cost)===200});
 call(a,'POST','/api/electricity',{billing_month:'2026-10',previous_meter:0,current_meter:300,unit_price:'1',service_charge:'0'},201);
 return {accounts};}
export default function(d){const i=__VU%2,a=d.accounts[i];const paths=['/api/dashboard?month=2026-10','/api/dashboard','/api/history','/api/auth/me','/api/electricity'];
 for(let j=0;j<paths.length;j++){const r=http.get(base+paths[j],params(a.token));latency.add(r.timings.duration);check(r,{'mixed dashboard request succeeds':r=>r.status===200,'owner summary isolated':r=>{if(r.status!==200)return false;const b=r.json();if(j<2)return i===0?b.has_bill&&b.month==='2026-10'&&Number(b.total_cost)===300&&Number(b.average_cost)===200:!b.has_bill&&b.available_months.length===0&&b.total_cost===null;if(j===2)return b.total===(i===0?3:0);if(j===3)return b.user.user_id===a.id;return b.records.length===(i===0?3:0);}});}}
export function teardown(d){if(!live){const a=call(null,'GET','/_test/auth-cache'),s=call(null,'GET','/_test/info');check(a,{'auth source reads bounded':x=>x.source_reads<=8});check(s,{'no extra source writes from dashboard':x=>x.repository_writes===6,'source reads bounded':x=>x.repository_loads<=12});console.log('Auth reads='+a.source_reads+', bill reads='+s.repository_loads);}for(const a of d.accounts)call(a,'POST','/api/auth/logout');}
