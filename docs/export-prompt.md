# External AI prompt export — 2026-10-22

The advice page has an always-available prompt export path independent of the
five-question hourly chat allowance. It becomes prominent when chat quota is zero.
Preview the complete text in a modal before explicitly copying it. Copying does
not send data to an external AI; pasting it into that service is the user's action.

## Backend

`POST /api/advice/export-prompt`, JSON `{ "month": "2026-10" }` (or null/latest).
Requires the existing live JWT/Redis session, user role and same-origin JSON checks.
Owner IDs and arbitrary question fields are rejected. Successful responses include
prompt, selected month, generated_at, data_version, template_version and rate_limit.

The separate Redis limiter admits five generations per account in the preceding
60 seconds using Redis TIME and atomic Lua. Cache hits count. The sixth returns
429 with Retry-After before source I/O. Reloading, changing month or starting a
new chat cannot reset the server limit. Admitted failed generations can count;
the chat allowance is never consumed. Copying an already-generated preview is
local and does not call the backend or use another generation slot.

`app/advice/export_prompt.py` reuses the existing owner-scoped Context and its
electricity/appliance/settings source caches. It never calls Gemini or its global
permit counters. The deterministic body is cached for 300 seconds by account,
source version, selected facts and template version. Each generation reads the
current cached source snapshot, so application writes select a new body immediately;
manual Sheets edits retain the existing source-cache freshness of up to 30 seconds.
Creation timestamp is added per response and is not presented as a fresh Sheets read.

The text includes household context, bill and previous-month comparisons, budget
gap and percentage, estimated energy and provenance, known/unknown counts, meter
discrepancy, precomputed hypothetical savings with formulas, missing fields and
clear instructions for a practical week plan. It explicitly handles absent months,
zero values, infeasible budgets below fixed charges, unknown device energy and
estimates exceeding the meter. Existing selection limits (up to twenty devices,
three scenarios) are disclosed, with aggregate counts covering the source data.

Only selected facts are rendered; account names, IDs, contacts, credentials and
raw records are not exported. User-entered device labels remain quoted as data,
with obvious email/Thai telephone patterns masked. Arbitrary personal details in
user-defined names cannot all be recognized automatically, so the preview asks
the user to check those labels before sharing. Text is assigned to textarea.value,
not executed as HTML. The preview also explains that external answers are outside
PowerTrack's response validation.

No changes were made to chat limits, provider policy, calculations or other feature
services. Integration changes are the new route, one frontend state notification,
the export UI/script/styles, and asset versions. No environment changes are required.

## Verification

| Test | Result |
|---|---|
| Python suite | 149 passed, including 10 new export tests |
| Node UI/navigation suite | 9 passed, including 2 export tests |
| Synthetic k6 | 12,035 requests, 20 VUs, 24,056 checks, all expected outcomes passed |
| Synthetic mixed p95 | 63.67 ms; about 437.7 requests/s overall |
| Auth source reads during synthetic load | 3 |
| Two accounts / real Sheets k6 | 54 requests, 95 checks, all expected outcomes passed |
| Real Sheets warm mixed p95 | 9.95 ms; overall p95 including setup 3.69 s |
| Additional model calls from export | Zero, confirmed against stub counters |
| Browser | Actual fixture login, exhausted-chat highlight, successful generation, readable preview, copy success and close/focus restoration verified |

Both users first exhausted hourly chat, then generated five prompts each and were
independently throttled on the sixth. The high-volume workload then mixed ordinary
reads with expected export 429 responses. This verifies throttling/read throughput,
not thousands of successful generations despite a five-per-minute cap. Model calls
were stubbed during load tests. No Google Sheets 429 was observed; application 429
responses were expected and checked. Measurements use small fixtures and do not
guarantee production capacity.

The exported plain text was sent as the sole user message, without proprietary
tools/system instructions or a special response schema, to real external models:

| Case | Generation model | Result |
|---|---|---|
| Complete facts | gemini-3.5-flash-lite | Passed |
| Estimates exceed meter; unknown device | gemini-3.5-flash-lite | Passed |
| Selected month missing | gemini-3.5-flash-lite | Passed |
| Same prompt on another model | gemini-3.6-flash | Passed |

A Gemini 3.6 Flash evaluator checked the answers against the Python facts for
grounding, relevance, actionability, safety and clarity. All four cases met the
criteria, and manual review confirmed the discrepancy warning and calculations
such as 200-baht gap / 12.5%, and a 12-kWh / 96-baht hypothetical reduction. Only
synthetic data was transmitted. ChatGPT's UI/API was not tested; the export is
ordinary vendor-neutral text and can be pasted there. These sample evaluations
do not guarantee how every external model will answer.

Evidence: ignored `tmp/eval/export-prompt/` contains exact prompts, actual model
answers, usage and verdicts; `tmp/k6/export-*.json` and server logs contain load
results. Browser evidence: `tmp/screenshots/export-prompt-preview.png`.

Reproduce:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
node --test tests/export_prompt_ui.test.cjs tests/advice_ui.test.cjs tests/analysis_ui.test.cjs tests/settings_ui.test.cjs
.\.venv\Scripts\python.exe tests/export_prompt_eval.py
```

Live model evaluation uses the configured Gemini key and consumes upstream quota.
The export feature itself does not. k6 scripts are `tests/k6/export-prompt.js` and
`tests/run-export-k6.sh`; live mode requires disposable fixture tabs. Browser setup
checks are in `tests/export_live_smoke.py` and refuse production users worksheets.
All five temporary Sheets tabs and isolated Docker containers/network were removed
after verification. Production health and the new OpenAPI endpoint are available.
