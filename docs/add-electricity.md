# Add Electricity — implementation and verification

Verified on 2026-10-07. Existing Add Electricity HTML/CSS are retained; its JavaScript now saves through the authenticated backend. Authentication repositories, sessions, OAuth, and roles are unchanged.

## API and storage

- `POST /api/electricity`: authenticated user only. Accepts `billing_month` (`YYYY-MM`), integer `previous_meter` and `current_meter`, `unit_price`, and `service_charge`. Rejects extra fields, negative values, invalid months, fractional meters, and current meters below previous meters. Price supports four decimal places and service charge two. Send money as decimal strings.
- The server derives the user ID from the existing authenticated session, generates a UUID, calculates units and costs with Decimal and HALF_UP rounding, and stores timestamps with UTC+07:00 offset. The calculation is the UI's flat unit price plus service charge; it does not calculate a utility's tiered tariff, Ft, or VAT.
- `GET /api/electricity`: returns only the current user's records, newest billing month first. No pagination yet.
- One record per user/month; duplicates return 409. Validation returns 422, unauthenticated requests 401, wrong role 403, and unavailable storage 503 with Retry-After. Responses use no-store. Browser writes require same origin and JSON.
- Worksheet `electricity_records` has 12 columns in this exact order: `record_id,user_id,billing_month,previous_meter,current_meter,units_used,unit_price,service_charge,energy_cost,total_cost,created_at,updated_at`. Writes update the row and native table range in one atomic Sheets batch. Existing table/header mismatches fail without writing.

Example payload:

```json
{"billing_month":"2026-10","previous_meter":100,"current_meter":200,"unit_price":"8","service_charge":"50"}
```

Result: 100 kWh, energy cost 800.00 THB, total 850.00 THB.

## Redis behavior and limits

The isolated feature package is `Back__end/app/electricity/`. Only a router registration was added to main.py. The feature uses existing Redis configuration through a separate bounded connection pool and a namespace derived from spreadsheet ID and worksheet name.

The normalized worksheet cache defaults to 30 seconds. Warm reads and known duplicates avoid electricity worksheet I/O. Cache misses use a shared lock to prevent multiple concurrent fills. Every new write loads the source afresh under a renewable, token-safe sheet lock, rechecks uniqueness, invalidates cache before persistence, then refreshes cache. Separate workers coordinate through Redis. Network calls have timeouts. If Redis cannot provide a lock, writes fail closed. If caching fails after a confirmed Sheets write, the successful save still returns 201.

The lock coordinates this application only: manual edits and other integrations must not write concurrently to the same worksheet. A remote write whose response times out is ambiguous; the API does not automatically retry it, and the UI reads back before offering a retry. Distributed lock leases cannot provide database-style uniqueness through arbitrary Redis failover or prolonged process suspension.

Manual sheet edits can take the cache TTL to appear. The entire worksheet is cached and filtered per request, so memory/CPU grow with total records. Sheets writes remain serialized and quota-limited. Crucially, the existing authentication dependency still reads the current user from Sheets on every request to retain immediate role/status revocation. Redis improves electricity storage I/O but does not remove this existing authentication bottleneck. Large production traffic needs a separate auth/data storage migration; these results do not establish production capacity.

Optional environment configuration (existing credentials and Redis variables are reused):

```text
GOOGLE_ELECTRICITY_SHEET=electricity_records
ELECTRICITY_CACHE_SECONDS=30
```

The UI retains its layout, loads identity and saved months, validates meters, disables submission while saving, shows server-calculated results, and blocks repeated months even after reload. The existing button now reads คำนวณและบันทึก. The month selector covers current year + 1 through current year - 5. Dashboard charts/history and appliance/AI features are not connected by this change.

## Verification results

30 pytest cases passed: calculation/rounding, input tampering, invalid values, owner isolation, authentication/role changes, register/login/logout regression, same-origin enforcement, 40 concurrent same-month requests, cache miss coalescing, TTL, ambiguous commits, storage failures, and atomic row/table persistence. JavaScript syntax check passed.

Browser smoke test used the existing register/login and Add Electricity pages in an isolated server with real Redis and synthetic Sheet repositories. Saving 100 → 200 at 8 THB plus 50 THB produced 850.00 THB. Reloading retained duplicate-month detection. Screenshot: `add-electricity-ui-test.jpg`.

| k6 scenario | Result |
| --- | --- |
| Synthetic Sheet repositories; real HTTP/auth/session/Redis; 20 concurrent VUs | 12,300 HTTP requests in 20.1 s, ~611 requests/s overall, 0 unexpected errors |
| Synthetic warm GET | p95 30.84 ms |
| Synthetic duplicate burst, 100 requests | p95 62.17 ms; exactly one new row |
| Synthetic storage calls across run | 2 loads and 2 writes |
| Actual Google Sheets, isolated hidden test tabs, 2 concurrent VUs | All 18 checks passed; 14 requests, 0 unexpected errors |
| Actual Sheets GET, 4 samples | p95 1.89 s |
| Actual Sheets initial save, 1 sample | 3.94 s |
| Actual Sheets duplicate burst, 4 samples | p95 3.24 s; exactly one new row |

409 is an expected duplicate response, not an unexpected failure. The live run is a small integration test to respect shared Google API quotas, not a high-load production benchmark. Hidden test tabs contained only a generated test account and two electricity records; they were verified then removed. Real `users` and `electricity_records` were not used as test-write targets. Test containers/networks were removed. Raw k6 summaries are local ignored files in `tmp/k6/synthetic.json` and `tmp/k6/live.json`.

## Running tests

```powershell
.venv/Scripts/python.exe -m pip install -r tests/requirements-dev.txt
.venv/Scripts/python.exe -m pytest tests/test_electricity.py -q
wsl bash -c "sed 's/\r$//' /mnt/c/electricity_tracker/tests/run-k6.sh | bash -s -- synthetic"
```

k6 requires the existing `electricity_tracker-backend:latest`, Redis 7 image, and Docker in WSL. Its containers use their own Redis/network and localhost port 8001. The synthetic run does not call Google Sheets. `synthetic serve` starts an isolated UI test server without running k6; remove the named `powertrack_test_app_synthetic`, `powertrack_test_redis_synthetic` containers and `powertrack_test_synthetic` network afterward.

To repeat `live`, first provision the disposable hidden worksheets named in `tests/run-k6.sh`: users headers matching the existing auth schema, electricity headers above, and a native table over the electricity headers. Use only synthetic accounts, remove those test worksheets afterward, and keep production Redis isolated. `tests/runtime_app.py` refuses to start without a supported test mode and test worksheet names. The `/_test/info` endpoint is absent from the production app.
