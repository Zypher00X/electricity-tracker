# Advice specificity and follow-up validation — 2026-10-23

## Resulting behavior

Prompt `powertrack-advice-6` and guidance `energy-guidance-2` distinguish temperature questions, detailed procedures, chronological plans and expansion of a prior action. The first summary sentence must answer the question. Narrow questions should keep actions about the requested appliance rather than add unrelated devices.

The former prohibition on every numeric character prevented answering “กี่องศา”. Only the exact phrase **26–27 องศาเซลเซียส** is now allowed as reviewed general AC guidance, with a fan when comfortable and adaptation to health/room conditions. It is not a measured household setting or a promised saving. Source: [EGAT guidance](https://www.egat.co.th/home/save-energy-for-all-20220503/). Other generated numeric claims remain prohibited; account figures and scenarios still originate in backend calculations.

Device context now carries recorded average watts, hours per day and days used, joined by the same owner-filtered appliance IDs. No identifiers are sent as device facts. Temporary chat retains bounded action details, not just a short summary. Expanding the first action sends that precise prior action separately to the provider. Context still expires, is scoped to account/conversation/data version/month, and excludes local scope refusals from substantive follow-up history. Without usable context, a short reference asks the user to identify the device/step instead of inventing context.

Custom questions show matching device figures directly from the returned facts and collapse the full graphs under “ดูตัวเลขและกราฟประกอบ”. Quick overview/device/budget buttons retain the existing graphs. Frontend renders text safely. Existing quota, explicit report saving, owner filtering, session checks, Sheets caching and export endpoints are retained. Cache keys include the new prompt/guidance versions; production Redis was not flushed and user quota was not reset.

The guarantee detector was also corrected: explicit phrases such as “ไม่สามารถรับประกันยอดประหยัด” and “ไม่ใช่การรับประกัน” no longer trigger a false rejection. An affirmative promise elsewhere in the same text is still rejected.

## Tests

- **189 Python tests passed**, including recorded usage fields, allowed temperature versus fabricated numbers, negative/affirmative guarantees, action-detail retention, month isolation and repeated ambiguous requests without real context.
- **17 Node UI tests passed**, including collapsed custom-question evidence and recorded watts/kWh displayed independently of generated quantities. Other feature UI regressions remain covered.
- DeepEval custom contract/energy-quality metrics: **10/10 cases passed** with explicit directness checks for temperature and detailed meter-verification steps. Nine cases used live Gemini responses; one tested the actual local scope clarification. Cases: temperature, detailed steps, expanding the first action, uncalculated temperature savings, no-context reference, refrigerator use/safety, unknown appliance energy, seven-day plan, budget limitations and injected requests for secrets/other-account data.
- A separate negative control containing the original vague “ตั้งอุณหภูมิให้เหมาะสม” answer was correctly rejected (relevance/actionability below the pass requirement).
- The original independent judge `gemini-3.6-flash` returned repeated HTTP 429. With the user's explicit selection, evaluation used **gemini-3.5-flash-lite** for both generation and a separate judge request. This is less independent; passing does not guarantee all future answers. Deterministic checks and manual review supplement the judge. Manual review led to stronger explicit action expansion and local clarification rather than relying solely on generous judge scores.
- Earlier iterations exposed missing measurement instructions, empty actionable lists on uncalculated savings, and false guarantee rejection. These were revised and retested. A directness assertion was corrected to recognize “ผู้อยู่อาศัย” as well as “คน”. No pass threshold was lowered.

## Load and operational checks

Final isolated k6 workload: **50 concurrent VUs**, 21 accounts, 480 rows in each core data table, **14,593 HTTP requests**, **29,209/29,209 checks passed**, no unexpected HTTP failures. Mixed read/replay p95 **931.08 ms**, average **447.89 ms**; advice context p95 **1,230.78 ms**; chat replay p95 **717.81 ms**. These timings describe application/cache traffic, not live Gemini generation latency.

The workload uses a deterministic provider stub. Actual quality calls above were sequential and used synthetic data only. Source cache reads were coalesced; replay did not invoke the provider again. Test-only containers/network were removed. Production health returned HTTP 200; no production data or account quota was changed by these tests. The source-cache/auth architecture was not changed, so no per-request Sheets auth reads were introduced. This does not remove Google provider limits or establish unlimited Sheets capacity.

Evidence: `tmp/eval/advice-specific/results.json`, per-case JSON, `negative-control.json`; `tmp/k6/advice-specific-load.json`, `advice-specific-console.log`, `advice-specific-load-server.log` (no tracebacks/errors found). Older abandoned `ambiguous.json` is exploratory output and is not part of the final ten-case results manifest.

Live evaluation: `tests/advice_specific_eval.py`; negative control: `tests/advice_specific_negative_eval.py`. Both use `.env` internally without printing credentials. Evaluation snapshots are synthetic only. Ordinary pytest does not call Gemini.

To try the change, refresh advice and start a new conversation. Try “ควรเปิดแอร์กี่องศา”, “ขอวิธีลดไฟแอร์แบบละเอียดและตรวจผลอย่างไร”, then “ช่วยขยายข้อแรก”. Existing hourly quota still applies. For recorded numeric facts try “คอมใช้ไฟกี่วัตต์” in a month containing that appliance. Review individual answers before acting; wording can still vary.
