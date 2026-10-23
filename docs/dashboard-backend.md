# Dashboard data integration — 2026-10-23

`GET /api/dashboard?month=YYYY-MM` reads only the signed-in user's `electricity_records` through the existing shared electricity service/cache. `app/dashboard/` contains the separate route and summary calculation. No extra source table, Gemini call, database schema or Docker setting is required.

## Display rules

- Default to the newest available bill for this account; if there are no bills, select the current Bangkok calendar month. The dropdown contains this account's bill months and the current month.
- Usage is the selected bill's `units_used`; the cost card is explicitly **ค่าใช้จ่ายรวม**, including recorded service charge.
- Changes compare with the immediately preceding calendar month, never the previous available bill. Missing previous data or a zero denominator produces `null`, displayed as “–”. A real zero bill remains zero.
- The average uses actual bills in the six calendar months ending in the selected month, including the selected month when present. Missing months are excluded from the denominator; the UI states how many bills were used. A selected missing bill is never substituted with another month. The available historical chart and average may still exist for that window.
- Chart points use recorded totals and break the line at missing months. Axis limits adapt to the data; the chart also offers a readable monthly values table. Empty windows have an explicit no-bill label and no fabricated points.
- The doughnut uses recorded energy cost and service charge only. It has no invented “other” component. Zero total has undefined percentages and a neutral ring. Amounts and changes use Decimal arithmetic on the server; formatting and SVG drawing happen in JS.
- The insight is a deterministic comparison with the same period average. It does not claim which device caused a change from bill data alone, and links to the existing AI advice page.
- Loading/failure hides previous summaries, with a retry control. Request cancellation/sequence checks prevent an old response replacing a newer selection. Existing logout behavior remains; the old undefined `backButton` reference and current-user console logging were removed.

## Authentication, Redis and I/O

The route uses the existing `require_user`: current JWT/session checks and the approved shared ten-second sanitized users cache. Owner filtering precedes month metadata, comparisons, averages and chart data. It does not read users directly or add a per-page Sheets auth lookup.

The existing electricity source cache, renewable distributed lock, bounded Redis pool and source 429 cooldown are reused. Dashboard summaries are cheap calculations over the cached snapshot; no independently stale dashboard cache was added. Electricity creation and history edits/deletes already invalidate/refill this shared cache, so the next dashboard load sees the mutation. Reading the dashboard never writes to Sheets. HTTP responses use `Cache-Control: no-store`.

Redis reduces reads and coordinates cold fills; Google Sheets' shared quota and unique-write latency still apply. Direct edits made in Sheets may remain cached until the existing source TTL expires. Dashboard load does not auto-refresh continuously: use **โหลดข้อมูลล่าสุด**, change the selected month, or reload the page after editing elsewhere.

## Verification

- **184 Python tests passed** across the backend, including six dashboard tests covering totals, shares, precise calendar comparisons/average, missing and zero data, ownership, auth/role/input validation, failure recovery, cold-read coalescing, and visibility after create/edit/delete.
- **15 Node UI tests passed**, including dashboard values, safe text, gap-aware chart geometry, real cost slices, empty/error states and logout, plus existing feature UI tests. Dashboard tests passed again after axis/empty-chart visual refinements.
- Synthetic k6: **20 VUs**, **12,019 requests**, **24,007/24,007 checks**, mixed cached-read p95 **39.53 ms**, zero unexpected failures. The entire run, including six bill writes in setup, used **2 auth-source reads and 6 bill-source reads**. No additional source writes came from dashboard requests.
- Real Sheets k6: **2 accounts**, **37 requests**, **44/44 checks**. Warm mixed-read p95 **6.22 ms**; overall HTTP p95 including registration and actual Sheets mutation setup **4.25 seconds**. Correct refresh after edit, explicit missing month after delete, newest remaining default, and recreation were checked. No Sheets 429 observed in this run.
- `tests/dashboard_live_smoke.py` forced Redis source misses and compared the authenticated API with actual fixture Sheet records: owner A's May/September/October totals 100/200/300, mean 200, October change 50%; owner B had no bills and no leaked month metadata. It is guarded for dedicated test tabs only.
- Browser verification covered account A's real cards and graphs, selecting September (200 total, 150 average from two bills, no August comparison), refreshing to default October, logout, and account B's empty dashboard. Screenshots are in `tmp/screenshots/dashboard-live-data.png` and `dashboard-empty.png`.
- Production health and route registration passed; production exposes no fixture endpoints. Tests used dedicated hidden users/electricity tabs and isolated Redis/container/network; production records were unchanged. Disposable tabs and runtime resources were removed after verification.

Run load tests with `tests/run-dashboard-k6.sh synthetic`. Live testing requires the dedicated `test_users_20261023` and `test_electricity_20261023` fixture tabs, including the native electricity table. The runner never targets production users/electricity tabs. No model is called in dashboard tests.
