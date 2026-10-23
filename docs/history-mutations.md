# History editing and deletion

Users can edit their own bill's month, previous/current meter, unit price and service charge from history. The server recalculates units, energy cost and total with Decimal and the existing rounding rules. IDs, owner and creation time are preserved; update time is a monotonic microsecond revision. The UI previews the calculation and uses a native accessible dialog for editing and permanent-delete confirmation, with busy, success, failure and reload states.

Changing a bill's month moves only that bill; appliance usage remains in its original month. The owner's month must remain unique. Search/year filters and pagination are reloaded after mutation; deleting the last row of the last page clamps pagination to the available page.

## API and authorization

- `PUT /api/history/{record_id}` accepts the existing five bill source fields plus `expected_updated_at` and UUID `request_id`.
- `DELETE /api/history/{record_id}` accepts JSON `{expected_updated_at, request_id}`.
- Both use the existing `require_user` (JWT, live session and cached account validation) and same-origin JSON checks. The backend selects by both owner and record ID; an ID from another account returns 404. Clients cannot supply an owner, computed total or creation time.
- An outdated revision returns 409. The dialog offers **โหลดรายการล่าสุด** instead of overwriting a newer edit.
- New mutation attempts reaching the source are bounded to ten per rolling minute per account. Retry receipts are separate from advice quota. Completed duplicate requests return their original operation receipt without reading/writing Sheets or taking the sheet lock. A reused UUID with different data returns 409. Receipts expire after one hour.

The mutation code is in `Back__end/app/history/mutations.py`; frontend controls are in `Front__end/history/mutations.js`. Repository changes provide an indexed read and exact-row update/clear operations while preserving the old `load()` return contract for existing features.

## Sheets and Redis consistency

1. Redis can reject cached foreign/missing IDs or stale revisions without source I/O. Every actual new write obtains the same renewable distributed sheet lock as electricity creation and cold reads, then refreshes Sheets and checks owner, revision and uniqueness again.
2. Physical row indexes come from the fresh Sheets read, including gaps; they are never accepted from the browser or inferred from a compacted list.
3. Redis records cache is invalidated **before** mutation. After success the shared cache is populated with all owners' updated records. A failed refresh after a confirmed commit does not report the commit as failed; cold readers reload Sheets under the same lock.
4. Deletion clears `userEnteredValue` in only A:L of the selected row. A blank formatted row may remain in Sheets. Other rows, columns, validation, formatting and the native table remain in place. Blank rows are skipped on reads; future insertion remains compatible. This avoids moving another account's rows and preserves the existing twelve-column schema.
5. A server-owned pending receipt records the intended typed result before the write. A retry after a lost acknowledgement reads the source and recognizes an already committed update/deletion. Numeric reconciliation compares Decimal values because Sheets may return `850.00` as `850`. The same operation is not applied twice. If another edit intervened, the stale request conflicts rather than overwriting it.
6. History comparisons and analysis recompute from the shared electricity cache. Advice context hashes change with the owner's bills, so later questions cannot reuse an answer for the old context. Another owner's changes do not invalidate this owner's semantic context. Already saved `ai_reports` snapshots remain immutable. A completed chat request replay remains its original response, as before.
7. Sheets 429 starts a shared ten-second electricity source cooldown. Warm reads remain cached; cold reads and mutations fail with retryable 503 instead of repeatedly hitting Sheets. The existing ten-second sanitized users cache is unchanged; no new per-page users-table reads were introduced.

Google Sheets is still the persistence bottleneck for unique writes. Redis improves reads/retries and coordination; it does not eliminate Google's shared quotas or make Sheets an unlimited concurrent-write database. Direct manual edits in Sheets bypass application locks and may remain cached until TTL expires.

## Verification — 2026-10-22

- **178 Python tests passed** across the backend, including 18 history-mutation tests. Coverage includes calculations, month moves and duplicates, owner isolation, auth/origin/input validation, stale edits, concurrent writers, last-page deletion, Redis refresh failure, timeout before/after commit, numeric normalization, indexed blank rows, per-owner throttling and source 429 cooldown. Existing features passed regression checks.
- **13 Node UI tests passed**, including new edit/confirm/cancel/retry-payload tests plus existing analysis/advice/settings/export/report tests. JS syntax and patch formatting checks passed.
- Isolated synthetic k6: **20 VUs, 12,037 HTTP requests, 24,044/24,044 checks**, **p95 65.14 ms** for the mixed cached/replay workload, zero unexpected request failures. Six fixture bill writes total (initial bill plus setup mutations), no extra writes during replay load; only three auth-source reads. Removing unnecessary replay locking reduced p95 from about 323 ms in the initial run.
- Live Sheets k6: **two accounts, 56 requests, 82/82 checks**; warm mixed-request p95 **9.17 ms**. Overall HTTP p95 including actual registration/source writes/setup was **4.02 seconds**. Expected 429 chat quota and 404 ownership checks are included; no Sheets 429 observed. Gemini is a deterministic stub in this load harness; generation time is excluded.
- Browser verified the edit form's original values, preview **100 units / 800 baht energy / 850 baht total**, successful save, persisted values after refresh, and the custom delete confirmation/cancel flow. UI screenshot: `tmp/screenshots/history-delete-confirmation.png`.
- `tests/history_mutations_live_smoke.py` read the edited 850-baht bill directly from Sheets, deleted a middle fixture row, updated the other owner's later row to 325 baht without shifting or modifying the first owner's row, forced shared Redis cache misses, and checked history/analysis/advice. Deleting the last bill returned empty history. Saved AI snapshot still held its original 1,600-baht bill.
- `tests/history_mutations_reconcile_live.py` injected a lost acknowledgement **after a real fixture Sheets update**, then retried against normalized numeric cells. It confirmed one write, successful reconciliation and refreshed Redis, and restored the fixture value.
- Production health and OpenAPI verified the new routes and absence of test-only endpoints. Testing used dedicated hidden tabs, separate Redis/network/containers and disposable accounts. No production records were edited/deleted; all test tabs/containers were removed after verification.

Reproduce load testing with `tests/run-history-mutations-k6.sh synthetic`. Live mode requires all six dedicated `test_*` tabs and an isolated runtime; never point the fixture server at production user/data tabs. Live smoke scripts are intentionally guarded and run inside that isolated container.
