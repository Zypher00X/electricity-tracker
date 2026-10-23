# Settings backend

Implemented 2026-10-21. Open `/frontend/settings/settings.html` while signed in.

## API and persistence

- `GET /api/settings` returns `{settings: null}` for an account with no settings, otherwise its saved record.
- `PUT /api/settings` creates or updates one row per authenticated user in `user_settings!A:J`. The caller cannot choose the owner. Existing `created_at` is retained.
- The body contains `residence_type`, optional `occupants`, `default_unit_price`, `default_service_charge`, `monthly_budget`, and required `expected_updated_at` (null for first save; latest returned timestamp for updates). Stale versions return 409; reload before retrying.
- Residence options: unknown, dormitory, apartment, house, other. Occupants: integer 1–1000; unit price: >0 through 10000, four decimal places; service charge: 0–1000000, two decimal places; budget: 0–1000000000, two decimal places. Blank optional values are null; zero charge/budget is preserved. THB and Asia/Bangkok are server controlled.
- Sheets writes use literal strings and numeric values, clearing optional cells when requested. Row and native table range are updated in one atomic Sheets batch. No production schema migration was necessary.

## Cache and concurrency

Settings use the existing bounded Redis connection pool with a separate namespace derived from spreadsheet and tab. A 30-second source snapshot caches both existing settings and missing-account results. A renewable, token-safe distributed lock coalesces concurrent cold reads and serializes writes. Writes read fresh source data, check the optimistic version, invalidate cache before commit, and refresh after success. A failed cache refresh does not turn a confirmed write into a failed save.

An upstream settings read 429 activates a shared 10-second cooldown rather than repeatedly reading Sheets. Storage failures return 503 with Retry-After. Existing auth uses the previously approved shared 10-second safe-user cache; JWT and Redis session checks remain active for every request. No additional per-page user-table reads were introduced.

The UI loads saved settings and summary, shows loading/save/error status, prevents duplicate submissions, and offers explicit reload after an uncertain save or conflict. Reset restores the saved draft. This change stores defaults for later consumption; it does not change historical bills or calculations in other features.

## Verification

- ` .venv/Scripts/python.exe -m pytest tests -q`: **125 passed**, including 22 settings cases. Coverage includes owner isolation, input validation, optional/zero fields, concurrent first saves, cold-read coalescing, version conflicts, ambiguous commits, auth/origin protection, and atomic repository writes.
- `node --test tests/settings_ui.test.cjs tests/analysis_ui.test.cjs`: **4 passed**. DOM tests cover API-driven summaries, optional fields, zero budgets, reset, and load failure. Full interactive browser testing was not performed.
- Synthetic k6: **12,014 requests**, 20 VUs, 24,007 checks, 0 failed requests/checks. Mixed read latency p95 **39.35 ms**, about **677.5 requests/s** overall. Auth source reads: 2; settings source reads: 2.
- Real Sheets k6: **32 requests**, two accounts, 45 checks, 0 failed requests/checks and **no observed 429**. Mixed read p95 **1.22 s**; overall HTTP p95 including registration, login and writes **4.17 s**. Both accounts opened profile/settings/history/appliances/analysis; one had settings and the other none. Create, immediate read, update, optional-cell clearing and zero budget passed.
- Read-back of the real disposable settings table confirmed exactly one updated row, numeric occupants/budget, cleared optional prices, and preserved creation timestamp. All five hidden fixture tabs were deleted afterward. Production account/data rows were not used for writes.
- Production health returned ok; OpenAPI contains GET/PUT settings and no test routes.

Load scripts: `tests/run-settings-k6.sh`, `tests/k6/settings.js`; synthetic fixtures live only in `tests/settings_runtime.py`. Live mode requires disposable test tabs with the documented headers in `app/settings/repository.py` and other feature repositories. The runner removes its own Docker containers/network. Reports are in ignored `tmp/k6/settings-*.json` and server logs.

These small-fixture benchmarks measure this test environment, not production capacity. Shared Sheets quotas and external traffic can still cause 429; caching reduces repeated reads but cannot remove upstream quotas or write limits.
