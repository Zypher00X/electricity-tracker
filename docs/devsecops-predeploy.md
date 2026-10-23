# Pre-deploy security validation — 2026-10-23

Completed source review, regression, SAST, dependency/container scans, secrets scans, passive DAST, authenticated adversarial checks, synthetic load tests, and AI evaluations. Original application containers, real .env and existing Sheets rows were preserved.

## Changes

Added bounded request bodies, cross-origin mutation protection, security headers and production host checks. Restricted Sheets diagnostics to administrators and sanitized failures. Serialized registration uniqueness checks through Redis. Added a hash-locked runtime dependency set, patched dependency/OS packages, a non-root production image without pip, and a separate hardened production Compose example.

## Evidence

- Python regression: 194 passed; Node UI tests: 17 passed.
- Authenticated security HTTP smoke: 70 passed, including ownership, CSRF-origin controls, login throttling, quotas and revoked sessions.
- Production configuration smoke passed. Actual network HTTPS test: 10 passed, using a separate Nginx proxy and a locally generated test certificate explicitly trusted by the test client. Certificate hostname validation remained enabled. Secure/HttpOnly/SameSite cookie worked over HTTPS and was absent from a prepared HTTP request.
- k6 mixed load: 14,593 requests, 29,209 checks passed, 50 VUs, p95 974.57 ms. Spike: 4,888 requests/checks passed, peak 100 VUs, p95 1234.21 ms. No failed requests. Synthetic repositories and Gemini stub were used; these figures do not measure live Sheets or Gemini capacity.
- Runtime pip-audit: zero known vulnerabilities in the 41 locked packages. Final runtime Trivy: zero Python vulnerabilities and zero critical OS vulnerabilities; 44 HIGH OS package findings remain across eight unique advisories with no available fixes in the scan. These are unresolved risks, not waived findings.
- Bandit: zero findings after review of narrowly documented false positives; Ruff semantic checks passed. Formatting check reports 47 files needing formatting; unrelated files were not mass-reformatted.
- Gitleaks: zero findings in scanned Git history and exported non-ignored source snapshot. Local ignored credentials were not exported.
- ZAP passive baseline: zero FAIL, five WARN. The anti-CSRF-token warning requires review alongside the passing Origin/Sec-Fetch-Site authenticated mutation tests; passive scanning alone does not establish full OWASP coverage.
- AI specific-question evaluation: 10/10 passed; four additional injection/unsafe/toxic red-team scenarios passed. Some specific-question answers were reused from exact-signature evaluation caches. The judge used the same Gemini model by prior user approval; independence is limited.

Artifacts are under ../tmp/security/ including trivy-final.json, http-smoke.json, production-config.json, tls-smoke.json, k6-regression.json, k6-spike.json and zap/baseline.html. Charts under the strict CSP were visually checked (ui-csp-charts.png).

## HTTPS configuration

For existing http://localhost:8000, keep COOKIE_SECURE=false. This flag does not enable TLS. For a real deployment, configure a domain, certificate and TLS reverse proxy first, then use COOKIE_SECURE=true, COOKIE_SAMESITE=lax and the production template cookie name __Host-powertrack_access_token. Set PUBLIC_ORIGIN to the actual HTTPS origin and TRUSTED_PROXY_IPS only to trusted proxy source addresses. HttpOnly is applied by the backend. The isolated TLS test does not install a certificate or enable TLS on the user's real deployment.

## Release status

Not automatically cleared for deployment: unresolved upstream OS HIGH findings need risk review or a patched replacement base; the real production domain/certificate/proxy and external TLS validation remain to be completed. The running development image retains its original installed packages until rebuilt; fixes were validated in powertrack:security-reviewed and powertrack:security-test candidate images. No deployment was performed.
