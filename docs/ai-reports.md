# Saved AI reports

The advice answer now offers **บันทึกผลวิเคราะห์** and a **รายงานที่บันทึกไว้** dialog with month filtering, pagination, and frozen report detail. Saving is optional; chatting and exporting a prompt do not write reports.

## Data and trust

- `app/reports/` is separate from the existing feature modules. Existing `ai_reports` A:K headers are unchanged.
- After a validated, in-scope Gemini response, the backend creates a UUID candidate in owner-scoped Redis for 24 hours. The browser sends only this ID. Refusals, insufficient-data responses, errors and exported prompts have no candidate.
- The candidate contains the original sanitized question, topic, context/facts/version, conversation context and selected knowledge; the answer, usage and generation time; model, provider and prompt/calculation versions. `input_hash` is SHA-256 of canonical input JSON. `created_at` is the save time, separate from generation time.
- Exact answer-cache hits reuse the original candidate ID, provenance and generation time. Repeated saves, concurrent saves, and retries after an ambiguous Sheets write find the same row. A new generation after changed source data has a new ID.
- Saved reports are immutable. Editing bills/settings later does not alter old reports. The history renderer uses the stored snapshot, not current account data. Report contents use text nodes, never user-generated HTML.
- Every route checks the existing JWT/session/role dependency. List/detail/save enforce owner identity on the server; other accounts get 404 for an ID. Writes also use the existing same-origin JSON check. No credentials/account contacts are added to the model snapshot; user-created device names remain part of the analysis data.

## Endpoints

- `POST /api/advice/reports` `{ "report_id": "UUID" }`; accepts no answer or snapshot fields.
- `GET /api/advice/reports?month=2026-10&page=1&page_size=5` (month optional; max page size 50).
- `GET /api/advice/reports/{UUID}`.

No Gemini calls or chat quota consumption occur on these endpoints. An unsaved candidate expires after 24 hours; an already saved report remains readable and retries remain idempotent after candidate expiration.

## Redis and Sheets I/O

All workers share a 30-second reports source cache and a renewable per-sheet lock. Concurrent cold reads coalesce. A save checks the cache first for existing IDs, then refreshes Sheets under the write lock before an actual insert. Cache invalidation precedes mutation; a timeout after a committed write can be retried safely. Explicit string cells preserve JSON and prevent formula interpretation. Row insertion and native table expansion use one batchUpdate. Cells above 49,000 UTF-16 units are rejected before writing instead of truncating snapshots.

Sheets 429 triggers a shared ten-second reports cooldown and a retryable 503. Account checks retain the existing shared ten-second sanitized users cache and per-request session verification. Report reads do not introduce a new users lookup. This reduces source calls; it does not remove Google's shared service-account quota. New unique report saves still require a real Sheets read and write. Redis and Google Sheets remain scaling limits at larger production volumes.

## Verification (2026-10-22)

- Python report tests cover exact JSON/hash, immutable data, cached-answer identity, owner isolation, forged fields, concurrency, ambiguous commits, candidate expiry, origin/auth, cell bounds, month/page filtering, cold-read coalescing and 429 cooldown. Existing advice/export and the broader backend suite passed. Node tests cover save payload, errors/retry, text rendering and history controls; previous UI tests passed.
- `tests/run-reports-k6.sh synthetic`: 20 VUs, **9,627 requests**, **19,229/19,229 checks**, mixed report p95 **56.67 ms**, one repository write, two auth-source reads. Both accounts use real HTTP auth/session and isolated Redis; Sheets and Gemini are fixtures.
- Live Sheets test: two temporary accounts, **42 requests**, **58/58 checks**; warm mixed report p95 **6.15 ms**, overall HTTP p95 including real Sheets/auth setup **5.13 seconds**. No unexpected HTTP errors or Sheets 429 observed in this run. Expected 429 chat-quota and 404 owner-isolation checks were included.
- Browser verification clicked ask → save → success → history → detail against the isolated live-Sheets app. Two rows read back directly from Sheets had matching JSON hashes; the native table expanded to three rows. All fixture report columns were TEXT like production. Changing the fixture's settings, clearing the report cache, and re-reading preserved the saved snapshot; re-saving did not duplicate it (`tests/reports_live_smoke.py`).
- Gemini is a deterministic stub in load and report persistence tests, so these timings exclude model generation. This feature does not change the model prompt or its existing evaluation results. Dedicated test tabs and containers were removed after verification; production rows were not changed.

## Manual check

Refresh advice, ask an in-scope question for a month with data, and click **บันทึกผลวิเคราะห์** below the new answer. Open **รายงานที่บันทึกไว้**, filter the month and open its detail. Refresh or log out/in and confirm persistence. Ask the same cached question and save again: there should be only one row for that answer. Change settings and confirm the saved report retains the old values. Another account must see only its own reports. Saving should remain available when chat quota is zero and must not reduce it further.
