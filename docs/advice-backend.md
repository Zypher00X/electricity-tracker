# Advice backend — 22 October 2026

The advice page now calls the backend and Gemini with account-scoped data. Open
`http://localhost:8000/frontend/advice/advice.html` after signing in.

## Model and environment

The real key was checked without printing it. Eligible model discovery was followed
by actual generation probes: `gemini-2.5-flash-lite` returned 404,
`gemini-3.1-flash-lite` returned 503, and **gemini-3.5-flash-lite** generated a valid
response. This is the production default. Model discovery alone does not establish
access, price, or an account's remaining free quota. No automatic model switching
or unbounded retries occur in production.

`compose.yaml` already loads `.env`. The backend container was recreated to receive
the new key; production Redis was not restarted. Optional settings are:

```dotenv
GEMINI_API_KEY=your_private_key_here
GEMINI_MODEL=gemini-3.5-flash-lite
ADVICE_PROVIDER_RPM=10
ADVICE_PROVIDER_DAILY_LIMIT=100
```

The last two are additional application-wide provider call safeguards, not Google's
quota or a billing hard cap. At most two provider calls run concurrently, with
expiring Redis leases. Daily counters use UTC. No evaluation tools are installed
in the production container; the provider uses Python's standard HTTPS client.

## Endpoints and flow

- `GET /api/advice/context?month=2026-10`: deterministic facts and current quota;
  does not consume a question or invoke Gemini. Omit month to use the latest month
  present in the account's data. An explicitly selected missing month never borrows
  a different month's bill.
- `POST /api/advice/chat`: JSON with `question`, `topic`, `month`, UUID
  `conversation_id`, and UUID `request_id`. Topics: overview, devices, budget, plan,
  custom. Fixed topics must use the canonical question in `app/advice/service.py`;
  arbitrary text belongs to custom. Owner identity always comes from the verified
  JWT/Redis session. Unknown body fields, including user_id, are rejected.

The flow is auth/session/role and same-origin validation → account lock and rolling
quota → existing source caches → Python calculations → owner/context-aware answer
cache → curated guidance and Gemini on a miss → schema/claim checks → Redis and UI.

Responses identify `source` (gemini, cache, scope, insufficient_data), selected
context, model when relevant, quota, generated_at, usage counters for a real model
call, and prompt/knowledge versions. Errors expose generic text rather than prompts,
credentials, upstream response bodies, or another user's data. No-store is set on
successful API responses. A user with no bill and no usage gets an explicit request
to add data without calling Gemini. Clearly unrelated questions are redirected
locally; ambiguous relevant questions are also constrained by the model policy.

## Quota, caching, and history

- **Five admitted questions per account in the preceding 3,600 seconds**, enforced
  atomically with Redis TIME and a sorted set. The sixth returns 429 + Retry-After.
  Cache answers, no-data questions and scope refusals count. Admitted requests that
  fail later also count; the UI explains this. Malformed/unauthorized requests and
  context reads do not consume the quota.
- A matching completed request_id is replayed without another admission/model call.
  Reusing it with another payload returns 409. An incomplete/failed recorded
  request is not blindly retried against Gemini; it returns a temporary error.
- A renewable per-account lock coalesces concurrent duplicates. Account limits
  remain independent, including when using the same conversation UUID.
- Answer cache: one hour, keyed by account, month/facts, own source-data hash,
  normalized question, fixed topic or recent custom-chat context, model, prompt
  version, and guidance version. Numbers are preserved in question normalization.
  This is exact/context caching; it does not guess semantic equivalence between
  different numerical requests.
- Bill, appliance, usage, and settings changes affect the fingerprint; old answers
  cannot match new facts. Existing source caches have up to 30-second freshness
  for external manual edits; successful application writes refresh/invalidate them.
  Other users' writes do not change this owner's fingerprint.
- Temporary conversation context is at most four question/answer pairs within the
  last hour and only for the same source version/month. It is not permanent chat
  history and is not written to ai_reports. Starting a new chat does not reset quota.
- Existing shared auth cache remains 10 seconds, with live session checks. Advice
  reuses the electricity/appliance/settings caches and does not add uncached
  per-page users-table reads. Provider 429 causes a shared 60-second cooldown.

## Numerical and response contract

`app/advice/context.py` performs ownership filtering before joins and computes
bills, budget gap/reduction percentage, target kWh under the recorded unit rate,
known/unknown appliance energy, and hypothetical savings. Foreign/orphan appliance
references are excluded. A budget below the bill's fixed charge is flagged as
infeasible under that recorded rate. Settings prices are only a labeled fallback
when no bill exists; historical bills are not recalculated from new settings.

Preset scenarios reduce eligible devices' estimated operating time by ten percent,
using average watts × reduced hours × days × quantity. They exclude refrigeration
and unknown/missing power. Monthly-kWh estimates do not imply constant wattage.
Money assumes the recorded flat unit rate, not a new Thai stepped-tariff simulation.
Scenarios are independent hypotheticals, not additive guaranteed savings.

Gemini receives compact facts and selected reviewed guidance, no user_id, email,
phone, passwords, tokens, or raw source rows. It returns a short Thai summary, up to
three actions, assumptions, missing data, and optional references to precomputed
scenarios. Numerical characters in generated prose, unsupported scenario IDs,
markup/URLs, malformed JSON, incomplete output and explicit guarantees fail closed.
Time-reduction scenarios are detached from unrelated cleaning/sleep-mode advice.
The UI draws charts and numerical cards only from Python facts and renders all
text through textContent. Model output is never executed as HTML/JavaScript.

The prompt distinguishes data from instructions, rejects other-domain requests,
does not expose tools/database access, and forbids unsafe wiring/meter modifications
or disconnecting food/medicine refrigeration. Seven-day plans have baseline, trial,
and review stages and consider weather/occupancy. No vector database was added in
this first flow: `knowledge.py` is a small versioned reviewed library. It is not
presented as independent external retrieval or fabricated citations.

## Verification results

| Check | Result |
|---|---|
| Python suite | **139 passed**, including 14 advice tests |
| Node DOM/navigation suite | **7 passed** |
| Synthetic k6 | **12,023 HTTP requests**, 20 VUs, 24,024 checks, all expected outcomes passed |
| Synthetic mixed p95 | **157.27 ms**, about **357 requests/s** overall |
| Synthetic I/O | Auth source reads 4; model stub called once for repeated questions |
| Two accounts / real Sheets k6 | **42 HTTP requests**, 63 checks, all expected outcomes passed |
| Real Sheets mixed p95 | **15.06 ms** for warm reads/replays; overall p95 including fixture setup **3.82 s** |
| Real Gemini HTTP smoke | Passed full HTTP → session → real fixture Sheets → calculation → Gemini → validated JSON → Redis |
| Final smoke model tokens | Input 1,314; output 311; thinking 0; total 1,625; replay/cache did not invoke Gemini |
| Browser smoke | Fixture login, account facts (1,600 / 200 kWh / 1,400 budget), cached answer, 200-baht / 12.5% cards and exhausted-quota disabled controls verified |

Load benchmarks substitute the model to test the application's throughput without
flooding Gemini. The real-model smoke is separate and does not establish Gemini
throughput. Expected application 429 responses for the sixth question were tested;
**no Sheets 429 was observed**. These small-fixture measurements do not guarantee
production capacity or eliminate shared upstream quotas.

DeepEval 4.3.1 was installed only in the local virtual environment. The final suite
uses custom BaseMetric/LLMTestCase metrics: deterministic schema/numerical/scenario
provenance and a separate **gemini-3.6-flash** judge for grounding, relevance,
actionability, safety, and concision. The judge was verified to reject an intentionally
unsafe, false answer (score **0.24**). Threshold: aggregate at least 0.8, grounding
and safety exactly 5/5, other dimensions at least 4/5.

Final prompt `powertrack-advice-5`: **7/7 cases passed**, each final judged score 1.0:
overview, budget, chronological week plan, cycling/unknown watts, injection, scope
refusal, missing selected-month data. Five cases generated real model answers; the
last two evaluate deliberate local no-call branches. Manual review caught weak
ranking and plan/weather wording that the initial same-model judge missed; the
prompt and rubric were refined and the judge separated before the final run.
These are observed sample results, not a guarantee of universally correct answers.
No evaluation data was uploaded to Confident AI; telemetry was disabled. Only
synthetic fixture facts went to generation/judge APIs.

Final evaluation generation tokens total **12,143**, excluding judge calls, probes,
earlier iterations, and smoke tests. Billing cost was not estimated from token counts.
Raw local results are in ignored `tmp/eval/advice-*.json`; k6 results/logs in ignored
`tmp/k6/advice-*.json` and `*.log`.

## Reproduce and operations

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
node --test tests/advice_ui.test.cjs tests/analysis_ui.test.cjs tests/settings_ui.test.cjs
.\.venv\Scripts\python.exe -m pip install -r tests/requirements-eval.txt
.\.venv\Scripts\python.exe tests/advice_eval.py
```

Live evaluation makes billable/quota-consuming calls and caches synthetic answers
locally. To regenerate a case intentionally, remove only its `tmp/eval/advice-<case>.json`.
The k6 runner is `tests/run-advice-k6.sh` (synthetic or live); live requires disposable
tabs with the exact headers used by the existing repositories. Real-provider HTTP
smoke instructions are in `tests/advice_live_smoke.py`; it asserts fixture sheet and
email prefixes and uses a temporary container entrypoint rather than modifying
production authentication. Test routes/stubs are only imported by isolated test
entrypoints. Production OpenAPI contains no `/_test` endpoints and health is ok.

All five hidden disposable Sheets tabs and the isolated Docker containers/network
were removed after verification. Production data/schema and other feature services
were preserved. New files are isolated under `Back__end/app/advice`; integration
changes are router registration, backend-only environment defaults, and advice UI.
