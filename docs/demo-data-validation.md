# Demo data and system validation — 2026-10-23

## Production data appended

Owner: `dd3e76ab-6478-4fb5-b055-08217ae80534`.

| Table | New rows | Before → after | Appended range |
|---|---:|---:|---|
| electricity_records | 24 | 5 → 29 | A7:L30 |
| appliances | 24 | 4 → 28 | A6:R29 |
| appliance_usage_monthly | 24 | 4 → 28 | A6:Z29 |

Bills cover June 2024–May 2026. All new appliance usage belongs to **May 2026 (พฤษภาคม 2569)**. Select that month in appliances, analysis/charts and advice. History now has five pages at six records per page. Default/current months can still show the original data instead.

New names start with `[จำลอง]`; notes carry `DEMO:demo-20261023-v1`. The synthetic meter sequence is separate from the original test readings; it must not be treated as real historical meter continuity. Original rows were preserved exactly, with before/after prefix hashes checked. Native table ranges, inherited formatting and dropdown validation were checked after the atomic append. Existing settings, users and saved reports were not changed.

May expectations: 24 items / 31 devices, 22 estimated items, two unknown items, one known-zero item. Known estimates total **247.55 kWh**, compared with **285 kWh** on the bill. At 8 baht/kWh plus 50 baht service, total is **2,330 baht**. Estimate minus meter is **−37.45 kWh**. Unknown values are not zero. AI context retains totals for all 24 items, includes 20 detailed items and three calculated scenarios, and discloses truncation.

New row IDs and ranges: [demo-data-manifest-20261023.json](demo-data-manifest-20261023.json). Full original backup and append plan remain in ignored `tmp/demo-seed-20261023/`. Keep the manifest to identify this demo set later; do not delete records merely by row number if rows have since moved.

## Validation results

- 186 Python regression tests passed; 15 Node UI tests passed.
- Read-only verification against real Sheets and production Redis passed: all 29 owner bills, five history pages, appliance totals, dashboard, analysis, AI context and exported prompt agreed with expected values. Owner filtering was checked through production services. It did not invoke Gemini or consume the user's chat quota.
- Browser checks on an isolated fixture passed for dashboard, history last page, appliances with all 24 items, analysis summary, charts showing all items including unknown/zero, and advice context/saved report access with exhausted chat quota.
- k6: **50 concurrent virtual users**, 21 isolated accounts (20 populated, one empty), 480 rows in each of the three data tables. **14,593 HTTP requests**, **29,209/29,209 checks passed**, no unexpected HTTP failures. Mixed read/replay p95 **917.30 ms**, average **440.27 ms**; maximum about 4.95 seconds.
- Feature p95: dashboard 483.34 ms; history 606.85 ms; appliances 598.05 ms; analysis 779.11 ms; advice context 1.21 seconds; reports 556.53 ms; auth 412.06 ms; chat replay 669.49 ms.
- Shared source-cache reads during the load: electricity five, appliances five, settings five; auth 13 with its existing short TTL. Report reads 25 include 20 post-save refreshes plus five cache fills. Explicit report saves produced 20 writes. Redis coalesced reads across accounts rather than issuing a Sheets read per request.
- Each populated account used five chat requests; the sixth was rejected. Idempotent replay did not consume another quota unit or call the model again. Account/report isolation, prompt export and empty-account behavior passed.
- DeepEval custom contract and energy-quality metrics: **5/5 cases passed**, score 1.0 each, using real `gemini-3.5-flash-lite` responses and separate `gemini-3.6-flash` judge calls. Cases: overview, budget, seven-day plan, estimates above meter, and unknown/truncated appliance details. Evaluation used synthetic facts only.

The k6 provider was a deterministic stub: this measures application/cache behavior under concurrency, not 50 simultaneous real Gemini requests. Actual Gemini quality calls were sequential. LLM judging and this data volume cannot guarantee every future answer or eliminate Google provider quotas. The isolated load cannot prove unlimited real Sheets capacity; actual Sheets checks verified the appended data and production service results without flooding its shared quota.

The first load run exposed a test assertion that did not accept a cached local insufficient-data answer. The expected source was corrected; no production behavior was changed. A readback test also changed float-to-Decimal parsing to use strings. No production backend/frontend changes were needed for this task.

## Evidence and cleanup

- Load results: `tmp/k6/large-data-synthetic.json`; final server log: `tmp/k6/large-data-final-server.log` (no tracebacks, quota-exceeded errors or unexpected server errors found).
- AI results: `tmp/eval/large-data/results.json` and five per-case JSON files.
- Source inventory: `tmp/demo-seed-20261023/project-audit.json` (93 source files inspected).
- Screenshots: `tmp/screenshots/demo-native-{bills,appliances,usage}.png`, `large-data-appliances.png`, `large-data-charts.png`.
- Temporary load containers and network were removed. Production backend/Redis stayed running; OpenAPI returned HTTP 200 and contained no test routes. The 72 requested demo rows remain in the real spreadsheet.

Reproduction helpers: `tests/seed_demo_data.py` (guarded/idempotent append), `tests/verify_seeded_account.py` (read-only actual data), `tests/run-large-data-k6.sh`, `tests/large_data_eval.py`.
