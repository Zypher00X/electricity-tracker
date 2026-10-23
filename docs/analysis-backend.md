# Analysis backend — 2026-10-21

The analysis feature is isolated in `Back__end/app/analysis/`. main.py registers its router. Existing auth, electricity, history, appliances and their write paths are unchanged. Analysis is read-only and requires no new production worksheet, schema, or credentials. The UI now uses live authenticated data rather than fixtures; the advice tab remains a placeholder and does not call AI.

## API and definitions

`GET /api/analysis?months=12&end_month=2026-10`

Existing user cookie/session required. User role only; administrators are rejected. `months` accepts 3, 6 or 12. Optional `end_month` is Gregorian YYYY-MM with real calendar/range validation. Default end is the most recent billing or active, valid usage month belonging to this account, or the current Bangkok month when there is no data. The chosen window contains consecutive calendar months, including missing months.

Ownership is enforced before dates, joins, totals and metadata. Bills are filtered by user ID. Appliances are filtered independently by owner; monthly snapshots must have the same owner and a matching owned appliance identity. Cancelled snapshots are excluded. Archived appliance identities still permit their historical active usage snapshots; names, categories, counts and values come from monthly snapshots rather than current defaults. Orphan references and cross-account references do not enter analysis. Duplicate bill months or duplicate appliance/month snapshots fail rather than silently double count.

Response fields:

- `start_month`, `end_month`, `available_months`, `has_data`.
- `latest`: newest recorded bill inside the window, total/energy/service amounts, units, prior-calendar-month amount and cost/unit percentage changes. Previous comparisons may use a bill just outside the displayed window. Missing prior month or a zero denominator gives null, never a fabricated percentage.
- `highest`, `lowest`: usage extrema among recorded bills in the window. Missing months are not zero. Ties use latest month for highest, earliest for lowest.
- `series`: one entry per calendar month in ascending order, with null units/amounts for missing bills. Genuine zero stays zero.
- `cost_breakdown`: energy cost and service charge from the latest bill only. No invented third slice, taxes or tariff assumptions. Zero total gives null percentages. Percentages and comparisons use Decimal HALF_UP to one decimal; money values are decimal strings.
- `appliance_month`, `appliances`, `appliance_summary`: usage of the selected end month, including source, method, coverage, known total, meter units and signed estimate-minus-meter difference. A month can have appliances without a bill. All-unknown or empty estimates give null total; genuinely known zero gives zero. Partial estimates are explicitly counted and are not a reconciliation of the full household bill.

Appliance estimates are recomputed using the existing Decimal calculator and validated snapshot inputs rather than trusting a manually changed stored total. Rated watts are never automatically substituted for average watts. Mixed measured/estimated sources remain identified.

## Redis and capacity

Analysis reuses the existing electricity cache and the coherent appliances/usage cache, their bounded pool, lock and cache-fill coordination. It introduces no separate aggregate cache, preventing a second invalidation problem. Saving a bill or creating/editing/cancelling usage through existing APIs updates those source caches; the next analysis request sees the new values. Warm reads avoid all three data-sheet I/O. Manual Sheet edits can take the existing 30-second TTL to appear.

Electricity and appliance caches are separate snapshots, not a cross-feature transaction. Concurrent writes can straddle an analysis read; reload after writes have completed for a current combined view. Data is still normalized/filtered in memory and grows with worksheet volume. This feature does not turn Sheets into a high-write database.

The unchanged authentication dependency reads the current user from Sheets on every request. The first unpaced real-Sheets k6 run exceeded the service account read quota in `get_current_user -> find_user_by_id -> get_all_users`, returning a Sheets 429 and an auth-stage server error. It passed analysis read/calculation scenarios but failed final analysis read/logout. The failure logs/summary were retained under `tmp/k6/analysis-live-quota-failure*`. No auth caching or bypass was added, preserving immediate role/status revocation. The repeat live integration run was deliberately paced; substantial production concurrency still requires a separate auth/storage design decision. Synthetic throughput is not production capacity.

## Frontend

The existing layout and summary/charts tabs are retained. Select a 3/6/12-month window and end month. Charts use API data, automatic axis scales, separate units/currency axes, actual month/year labels and tooltips. Missing bills show dashes and break the line; they are never connected as continuous readings. Zero-only charts use a safe nonzero axis bound. Large axes use compact labels, and mobile charts scroll rather than crush labels. Cost donut has two genuine components. Appliance bars show unknown values as incomplete, with count/total/meter context. Raw amounts are formatted for display only, not recalculated as billing in JS.

Loading, no bills, no appliances, all-zero totals, partial estimates, failed load/retry, authentication redirects and superseded-request cancellation are handled. Identity comes from `/api/auth/me`. Both fetches use no-store and assets have versioned URLs. Browser back/forward cache triggers a refresh. Account data is absent from static HTML. Complete visual/manual browser verification remains for the user; automated JS tests use a lightweight DOM harness, not a full browser.

## Verification

- **96 Python tests passed:** 14 analysis cases plus 82 existing/recent electricity/history/appliance/navigation cases. Coverage includes comparisons/year boundaries, gap/zero handling, totals and shares, owner-scoped dates and joins, cancellation, orphans, archived identities, ignoring tampered stored estimates, source-cache reuse, immediate bill/save/edit/cancel visibility, malformed query bounds, role checks and storage errors. Existing write/auth regression cases also pass.
- **2 Node DOM tests passed:** API figures populate summary, chart bars fit their axes, missing months split the line, actual cost slices only, unknown appliance values, empty state and failed-load retry. `node --check` and diff whitespace checks pass. Browser visual inspection was not performed in this turn.
- **Final synthetic k6:** 20 concurrent VUs for 15 s; 8,567 HTTP requests, 34,221 checks passed, zero unexpected errors; overall ~565 HTTP requests/s; analysis p95 **45.09 ms**. Test server uses real HTTP/JWT/session/Redis, synthetic external repositories, two bills and two appliance snapshots. It checks new bill+usage visibility and analysis refresh immediately after cancellation. Source reads remain bounded (bills <=3; appliance datasets <=4) across the entire run; source writes are two bill writes and three appliance commits.
- **Paced real-Sheets k6:** two VUs, four measured analysis reads plus setup/teardown; 16 HTTP requests, **23/23 checks passed**, zero unexpected errors. Analysis GET p95 **3.14 s**, average 2.47 s. Explicit sleeps are outside the measured request trend. Small sample is integration evidence only, not a load capacity claim. The previous unpaced quota failure is reported above.
- Test writes used only four temporary hidden fixture worksheets and an isolated Redis/network. Production users/bills/appliance records were not used as fixture writes. Fixtures and containers/networks were removed after testing. Production API registration, health 200 and absence of test endpoints were checked.

Raw results/logs are ignored under `tmp/k6/analysis-synthetic.json` and `analysis-live.json`. Run Python tests with `.venv/Scripts/python.exe -m pytest tests/test_analysis.py tests/test_appliances.py tests/test_electricity.py tests/test_history.py tests/test_appliance_navigation.py -q`; frontend DOM tests with `node --test tests/analysis_ui.test.cjs`. Use `tests/run-analysis-k6.sh synthetic` through WSL for the isolated load scenario; live mode needs the four disposable worksheet names in that script provisioned first. Live setup/teardown is paced to respect shared quotas. Never point fixture tests at real production tabs/Redis.

Manual verification: hard-refresh analysis, compare the latest total/units against the recorded bill, select end month/window, check gaps and prior-calendar-month comparison, verify the two real cost components, then compare appliance bars/coverage with the active usage list for that end month. Edit or cancel usage, return and refresh analysis. Verify with a second account, and use Offline in browser dev tools to test retry. AI recommendations are outside this implementation.
