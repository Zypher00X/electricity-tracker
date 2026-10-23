import http from "k6/http";
import { check, fail } from "k6";
import { Counter, Trend } from "k6/metrics";

const BASE = __ENV.BASE_URL || "http://electricity_test_app:8000";
const LIVE = __ENV.TEST_MODE === "live";
const created = new Counter("duplicate_burst_created");
const readTime = new Trend("electricity_read_ms", true);
const duplicateTime = new Trend("electricity_duplicate_ms", true);
const writeTime = new Trend("electricity_write_ms", true);
const historyTime = new Trend("history_read_ms", true);
http.setResponseCallback(http.expectedStatuses(200, 201, 409));

export const options = {
  scenarios: LIVE ? {
    duplicates: {executor:"shared-iterations", vus:2, iterations:4, exec:"duplicate"},
    reads: {executor:"shared-iterations", vus:2, iterations:4, startTime:"8s", exec:"read"},
  } : {
    duplicates: {executor:"shared-iterations", vus:20, iterations:100, exec:"duplicate"},
    reads: {executor:"constant-vus", vus:20, duration:"15s", startTime:"5s", exec:"read"},
  },
  thresholds: {
    checks:["rate==1"], http_req_failed:["rate==0"],
    duplicate_burst_created:["count==1"],
    electricity_read_ms:[LIVE ? "p(95)<10000" : "p(95)<500"],
    history_read_ms:[LIVE ? "p(95)<10000" : "p(95)<500"],
    electricity_duplicate_ms:[LIVE ? "p(95)<15000" : "p(95)<2000"],
  },
};

function params(cookie) {
  return {headers:{"Content-Type":"application/json", "Cookie":cookie}, timeout:"30s"};
}
const payload = month => ({billing_month:month, previous_meter:100, current_meter:200,
  unit_price:"8", service_charge:"50"});

export function setup() {
  const meta = http.get(BASE + "/_test/info");
  if (meta.status !== 200 || !meta.json().isolated || meta.json().mode !== (LIVE ? "live" : "synthetic")) {
    fail("Refusing to load-test a non-isolated server");
  }
  const name = "k6-" + Date.now();
  const email = name + "@example.com";
  const password = "TestFixturePassword123!";
  const registration = http.post(BASE+"/api/auth/register", JSON.stringify({full_name:"K6 Test Fixture",
    email, phone:"089"+String(Date.now()).slice(-7), password}), {headers:{"Content-Type":"application/json"}});
  if (registration.status !== 201) fail("Fixture registration failed: " + registration.status);
  const login = http.post(BASE+"/api/auth/login", JSON.stringify({identifier:email,password}),
    {headers:{"Content-Type":"application/json"}});
  if (login.status !== 200) fail("Fixture login failed: " + login.status);
  const cookie = "powertrack_access_token=" + login.cookies.powertrack_access_token[0].value;
  const saved = http.post(BASE+"/api/electricity", JSON.stringify(payload("2026-01")), params(cookie));
  if (saved.status !== 201) fail("Initial write failed: " + saved.status + " " + saved.body);
  writeTime.add(saved.timings.duration);
  check(saved, {"backend calculation": r => Number(r.json().record.total_cost) === 850 && r.json().record.units_used === 100});
  const history = http.get(BASE+'/api/history?year=2026&page_size=1', params(cookie));
  check(history, {'new save immediately in history': r => r.status === 200 && r.json().total === 1 && r.json().records[0].record_id === saved.json().record.record_id});
  return {cookie, userId:registration.json().user.user_id};
}

export function duplicate(data) {
  const response = http.post(BASE+"/api/electricity", JSON.stringify(payload("2026-02")), params(data.cookie));
  duplicateTime.add(response.timings.duration);
  created.add(response.status === 201 ? 1 : 0);
  check(response, {"duplicate burst returns 201/409": r => r.status === 201 || r.status === 409});
}

export function read(data) {
  const history = http.get(BASE+'/api/history?year=2026&q=2026&page_size=1&page=1', params(data.cookie));
  historyTime.add(history.timings.duration);
  check(history, {
    'history owner and pagination': r => r.status === 200 && r.json().total === 2 && r.json().total_pages === 2 && r.json().records.length === 1 && r.json().records[0].user_id === data.userId,
    'history previous month comparison': r => r.status === 200 && Number(r.json().records[0].change_percent) === 0,
  });
  const response = http.get(BASE+"/api/electricity", params(data.cookie));
  readTime.add(response.timings.duration);
  check(response, {
    "read succeeds": r => r.status === 200,
    "only owner records": r => r.status === 200 && r.json().records.every(x => x.user_id === data.userId),
    "exactly two months": r => r.status === 200 && r.json().records.length === 2,
  });
}

export function teardown(data) {
  const final = http.get(BASE+"/api/electricity", params(data.cookie));
  if (final.status !== 200) console.log('Final verification HTTP status='+final.status);
  check(final, {"single row per month after burst": r => r.status === 200 && r.json().records.length === 2});
  if (!LIVE) {
    const meta = http.get(BASE+"/_test/info").json();
    check(meta, {"only two repository writes": x => x.repository_writes === 2,
      "cache avoids repeated sheet reads": x => x.repository_loads <= 3});
    console.log("Fixture repository loads="+meta.repository_loads+", writes="+meta.repository_writes);
  }
  http.post(BASE+"/api/auth/logout", null, params(data.cookie));
}
