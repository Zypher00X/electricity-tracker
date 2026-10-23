# Electricity history

Implementation verified on 2026-10-07. Feature code is isolated in `Back__end/app/history/`; main.py registers its router. Existing authentication, Add Electricity calculations, Sheet persistence and Redis cache behavior are reused without changing their implementations.

## API

`GET /api/history?q=&year=2026&page=1&page_size=6`

User cookie/session required; administrators cannot access user history. Ownership filtering occurs before search, comparisons, year metadata or pagination. The response includes `records`, `total`, `page`, `page_size`, `total_pages`, and `available_years` (Gregorian years belonging only to the signed-in account). Records are newest first. Each contains the original electricity record plus nullable `change_percent`. The UI displays Buddhist years.

Search accepts Thai month names/abbreviations, Thai digits, Gregorian/Buddhist year labels, YYYY-MM and MM/YYYY. Spaces and date punctuation are normalized. `year` is Gregorian; q has a 100-character limit, page is 1..1,000,000 and page_size is 1..100. Out-of-range pages clamp to the last page. Empty results return total_pages 0, page 1 and records [].

Comparison uses total_cost including service_charge: `(current - previous) / previous * 100`, Decimal HALF_UP rounding to one decimal place. The previous record must be the actual preceding calendar month of the same owner, including December across a year boundary. Comparisons use all owner records before filtering/pagination. Missing prior month or a prior total of zero returns null (UI “–”); unchanged totals display 0.0%.

## UI

History uses authenticated API data and current account identity. Years come from the API; no sample records remain. Loading, empty/search-empty and error/retry states are supported. Search is debounced 300 ms. Superseded requests are aborted and sequence-checked to prevent older responses overwriting current results. Pagination uses at most five numbered buttons and ellipses. Browser responses use no-store; the script URL has a version suffix. Returning via browser back/forward cache reloads history. A successful Add Electricity save refreshes the shared cache, so subsequent history reads see the new record immediately.

Open `/frontend/history/history.html` through the existing sidebar links. Its static HTML contains no account data; account data is provided only by authenticated APIs. No new database table or credentials are needed.

## Redis and capacity

History shares the existing namespaced electricity cache (30 s default), renewable lock and connection pool. A cold cache uses one worksheet load for concurrent readers; warm filtered/paginated requests avoid electricity worksheet calls. A second history cache was deliberately not introduced, avoiding separate invalidation and stale lists after saves. Manual Sheet edits may take the TTL to appear.

The whole normalized worksheet is still cached, then ownership/search/pagination are computed in memory. API response size is bounded, but processing grows with record count. Existing authentication still reads current users from Sheets each request to preserve immediate status/role revocation. Sheets API quotas, serialized writes and this authentication I/O constrain production concurrency. Synthetic k6 results measure local API/cache performance with two records; they do not establish capacity for a large production dataset.

## Verification

51 pytest cases passed (30 existing Add Electricity and 21 history cases). Coverage includes owner/metadata isolation, unauthenticated/admin access, status revocation, month/year searches, pagination bounds and empties, calendar gaps/year boundaries, zero denominators, unchanged totals, rounding, storage failure, immediate visibility after save, and 40 parallel cold-cache history requests resulting in one source load. Existing register/login/logout and Add Electricity cases also pass.

Browser smoke: register/login in isolated server, empty history, save through existing Add Electricity form, then history displays 100 units, 800.00 energy cost, 50.00 service charge and 850.00 total, with “–” for the missing previous month. Screenshot `history-backend-test.jpg` uses a generated fixture account.

Synthetic k6: 20 concurrent VUs, 12,122 HTTP requests, 30,140/30,140 checks passed, no unexpected errors. Overall combined HTTP throughput ~564 requests/s; history p95 33.33 ms, existing electricity reads p95 28.34 ms. Source repository counters: two loads/two writes. Combined script exercises save-to-history, owner/pagination, zero-percent comparison, existing reads, duplicate bursts and logout. Raw result `tmp/k6/history-synthetic.json` is ignored.

Real Sheets repeat run: all 27 checks and thresholds passed; 19 requests, zero unexpected errors. History p95 1.88 s (four history read samples), existing electricity reads p95 1.81 s. This is a small integration run with two concurrent VUs, not a production capacity benchmark. An earlier live run passed all history scenarios but failed its final verification and logout, with a connection reset observed on logout. The original server log was not retained, so the exact cause remains unconfirmed. A repeat with server-log capture passed. The earlier summary is retained locally as `tmp/k6/history-live-first.json`; do not describe both runs as uniformly successful.

Live test writes targeted only disposable hidden test worksheets, with a separate Redis/network and generated accounts. Production records were not modified by the test. Test worksheets and containers/networks were removed afterward. Raw summaries and captured server logs are ignored under tmp/. JavaScript syntax and diff whitespace checks passed.

Run unit tests with `.venv/Scripts/python.exe -m pytest tests/test_electricity.py tests/test_history.py -q`. Run k6 through `tests/run-k6.sh` in WSL using the documented isolated environment in `add-electricity.md`; this now writes `history-synthetic.json` / `history-live.json`. Live mode needs its disposable test worksheets provisioned first. Never load-test production using this script or mount real worksheets as fixtures.
